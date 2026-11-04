"""
C 模块核心：两阶段 WorkChain（ProteinMPNN 生成 → 检查门禁 → 简单筛选）。

对应分工文档 C「编排、重算与恢复」：
  1. 推理与筛选参数分开，按公共端口连接 Data。
  2. 门禁：计算成功(is_finished_ok) + 支持版本清单校验 + 必需端口齐全 + 无已知失效，
     全部通过才启动下游；否则记录原因并终止或重试。
  3. 有限重试：最多 MAX_RETRIES 次重试，保留每次尝试的作业身份/状态/启动计数。
  4. 提交状态不明时，用 is_finished_ok 核对外部任务再决定是否重提。

下游重算入口见 rerun.py；提交入口见 submit.py。
"""
from aiida.engine import WorkChain, ToContext, while_
from aiida.orm import Dict, SinglefileData, Bool, Int, Float
from aiida.orm.nodes.data.code import Code

# 支持的 ProteinMPNN 版本白名单（A 侧提供；清单 schema 版本）
SUPPORTED_VERSIONS = ["v1.0"]
SUPPORTED_SCHEMA = "ai4s-artifacts-1"
# 最多两次有限重试（首次 + 2 次重试 = 最多 3 次尝试）
MAX_RETRIES = 2


class ProteinMPNNFilterWorkChain(WorkChain):
    """两阶段 WorkChain：inference -> gate -> filter。"""

    @classmethod
    def define(cls, spec):
        super().define(spec)

        # ---------------- 输入：推理参数与筛选参数分开 ----------------
        spec.input("pdb", valid_type=SinglefileData, required=True, help="输入 PDB 结构")
        spec.input("code", valid_type=Code, required=True,
                   help="推理任务的 Code（当前用 mock，A 侧就绪后换真实 code）")
        spec.input(
            "infer_params",
            valid_type=Dict,
            required=True,
            help="推理参数：version / temperature / batch_size / seed",
        )
        spec.input(
            "filter_params",
            valid_type=Dict,
            required=True,
            help="筛选参数：score_threshold / top_k",
        )
        # 轻量任务专用：可控失败（attempt <= fail_if_le 时失败）与等待
        spec.input("fail_if_le", valid_type=Int, required=False, default=lambda: Int(0),
                   help="前 N 次推理尝试模拟失败（默认 0=不失败）")
        spec.input("sleep", valid_type=Float, required=False, default=lambda: Float(0.0),
                   help="模拟计算耗时（秒）")
        # 复用上游模式：置 True 并传入已合格的上游 Data，则只跑筛选、不重跑推理
        spec.input("reuse", valid_type=Bool, required=False, default=lambda: Bool(False),
                   help="复用已合格上游结果，只重算筛选")
        spec.input("sequences_in", valid_type=SinglefileData, required=False,
                   help="复用模式：上游已合格的设计序列 fasta")
        spec.input("scores_in", valid_type=Dict, required=False,
                   help="复用模式：上游已合格的分数")

        # ---------------- 输出（公共接口） ----------------
        spec.output("sequences", valid_type=SinglefileData, help="artifacts.sequences")
        spec.output("scores", valid_type=Dict, help="artifacts.scores")
        spec.output("selected_sequences", valid_type=SinglefileData, help="artifacts.selected_sequences")
        spec.output("sample_table", valid_type=Dict, help="artifacts.sample_table")
        spec.output("selection_report", valid_type=Dict, help="artifacts.selection_report")

        # ---------------- 退出码 ----------------
        spec.exit_code(400, "ERROR_VERSION_UNSUPPORTED", message="推理版本不在支持清单内")
        spec.exit_code(401, "ERROR_MANIFEST_INVALID", message="产物清单校验未通过")
        spec.exit_code(402, "ERROR_INFER_FAILED", message="推理达到最大重试次数仍失败")
        spec.exit_code(403, "ERROR_REUSE_INPUT_MISSING", message="复用模式缺少上游 Data")
        spec.exit_code(404, "ERROR_NO_ELIGIBLE", message="筛选后无合格样本（允许 selected_count=0）")

        # ---------------- 执行流程 ----------------
        spec.outline(
            cls.validate_input,                 # 门禁1：版本/参数/复用输入校验
            cls.branch_reuse_or_infer,          # 分支：复用 或 进入推理重试循环
            while_(cls.need_retry)(
                cls.submit_infer,               # 提交推理（记录 attempt + job pk）
                cls.check_infer,                # 门禁2：is_finished_ok + 清单 + 端口齐全
            ),
            cls.check_final_infer,              # 重试完后最终判定，失败则终止
            cls.run_filter,                     # 用上游 Data 做筛选
            cls.finalize,                       # 输出最终结果
        )

    # ---------------- 步骤实现 ----------------

    def validate_input(self):
        """门禁1：推理参数、版本、复用模式输入合法性校验。"""
        if self.inputs.reuse.value:
            if "sequences_in" not in self.inputs or "scores_in" not in self.inputs:
                self.report("复用模式缺少上游 sequences_in / scores_in，终止")
                return self.exit_codes.ERROR_REUSE_INPUT_MISSING
            self.ctx.reuse = True
            self.report("复用模式：使用已合格上游 Data，不启动模型推理")
        else:
            self.ctx.reuse = False
            ver = self.inputs.infer_params["version"]
            if ver not in SUPPORTED_VERSIONS:
                self.report(f"版本 {ver} 不在支持清单 {SUPPORTED_VERSIONS}，终止")
                return self.exit_codes.ERROR_VERSION_UNSUPPORTED
            # 持久化上下文（daemon 重启也不丢）
            self.ctx.attempt_count = 0
            self.ctx.infer_job_ids = []   # 每次推理 CalcJob 的 pk，启动计数
            self.ctx.infer_success = False

    def branch_reuse_or_infer(self):
        """复用模式：直接把合格上游 Data 放入 ctx，跳过推理循环。"""
        if self.ctx.reuse:
            self.ctx.sequences = self.inputs.sequences_in
            self.ctx.scores = self.inputs.scores_in
            self.ctx.manifest_ok = True
            self.ctx.infer_success = True
            self.report("已复用上游 Data，直接进入筛选")

    def need_retry(self):
        """是否继续重试：非复用模式、未成功、且重试次数未到上限。"""
        if self.ctx.get("reuse", False):
            return False
        if self.ctx.get("infer_success", False):
            return False
        return self.ctx.attempt_count < MAX_RETRIES

    def submit_infer(self):
        """提交一次推理任务，记录尝试编号与作业身份。"""
        from .calcjobs import LightMPNNCalcJob

        self.ctx.attempt_count += 1
        self.report(f"第 {self.ctx.attempt_count} 次推理尝试（上限 {MAX_RETRIES} 次重试）")

        builder = LightMPNNCalcJob.get_builder()
        builder.code = self.inputs.code
        builder.pdb = self.inputs.pdb
        builder.params = self.inputs.infer_params
        builder.attempt = Int(self.ctx.attempt_count)
        builder.fail_if_le = Int(self.inputs.fail_if_le)
        builder.sleep = Float(self.inputs.sleep)
        builder.options = {
            "resources": {"num_machines": 1, "tot_num_mpiprocs": 1},
            "withmpi": False,
        }

        future = self.submit(builder)
        self.ctx.infer_job_ids.append(future.pk)  # 启动计数留痕
        return ToContext(infer_node=future)

    def check_infer(self):
        """门禁2：核对外部任务真实状态 + 清单校验 + 必需端口齐全。"""
        node = self.ctx.infer_node
        if not node.is_finished_ok:
            # 提交状态不明/失败：核对外部任务后决定重试，不盲目重提
            self.ctx.infer_success = False
            self.report(f"推理任务 pk={node.pk} 未成功(is_finished_ok=False)，准备重试/终止")
            return

        # is_finished_ok 通过：再做清单与端口齐全校验
        manifest = node.outputs.manifest
        ok = self._check_manifest(manifest)
        if not ok:
            self.ctx.infer_success = False
            self.report(f"推理任务 pk={node.pk} 清单校验未通过")
            return

        self.ctx.sequences = node.outputs.sequences
        self.ctx.scores = node.outputs.scores
        self.ctx.infer_success = True
        self.report(f"推理成功 pk={node.pk}，清单与端口校验通过")

    @staticmethod
    def _check_manifest(manifest):
        """校验产物清单：schema 版本 + validation.passed + 必需端口齐全。"""
        try:
            d = manifest.get_dict()
        except Exception:
            return False
        if d.get("schema_version") != SUPPORTED_SCHEMA:
            return False
        if not d.get("validation", {}).get("passed", False):
            return False
        ports = {a.get("port") for a in d.get("artifacts", [])}
        if "artifacts.sequences" not in ports or "artifacts.scores" not in ports:
            return False
        return True

    def check_final_infer(self):
        """重试循环结束后统一判定：仍失败则终止，记录原因。"""
        if not self.ctx.get("infer_success", False):
            self.report(
                f"推理重试 {self.ctx.attempt_count} 次后仍失败，"
                f"已记录作业身份 {self.ctx.infer_job_ids}，终止流程"
            )
            return self.exit_codes.ERROR_INFER_FAILED

    def run_filter(self):
        """第二阶段：用上游 Data 做筛选（分数 ≤ 阈值，升序取 top_k，同分按 sample_id）。"""
        scores = self.ctx.scores.get_dict()
        sample_ids = scores["sample_ids"]
        score_vals = scores["scores"]
        threshold = float(self.inputs.filter_params["score_threshold"])
        top_k = int(self.inputs.filter_params["top_k"])

        # 分数 ≤ score_threshold 入选；升序排序，同分按 sample_id
        eligible = [
            (sid, sc) for sid, sc in zip(sample_ids, score_vals) if sc <= threshold
        ]
        eligible.sort(key=lambda x: (x[1], x[0]))
        selected = eligible[:top_k]
        selected_ids = [sid for sid, _ in selected]

        # 读取上游序列，选出对应的行生成 selected fasta
        fa_path = self.ctx.sequences.get_absolute_path()
        records = self._read_fasta(fa_path)
        seq_by_id = {rid: seq for rid, seq in records}
        selected_lines = "".join(f">{sid}\n{seq_by_id.get(sid, '')}\n" for sid in selected_ids)
        selected_data = SinglefileData.from_string(selected_lines, filename="selected.fa").store()

        sample_table = Dict({
            "schema_version": "ai4s-artifacts-1",
            "threshold": threshold,
            "top_k": top_k,
            "selected_count": len(selected_ids),
            "selected_ids": selected_ids,
            "selected_scores": [sc for _, sc in selected],
        }).store()

        selection_report = Dict({
            "schema_version": "ai4s-artifacts-1",
            "selected_count": len(selected_ids),
            "threshold": threshold,
            "top_k": top_k,
            "infer_job_ids": self.ctx.get("infer_job_ids", []),
            "model_launches": len(self.ctx.get("infer_job_ids", [])),
            "reused": bool(self.ctx.get("reuse", False)),
        }).store()

        self.ctx.selected_sequences = selected_data
        self.ctx.sample_table = sample_table
        self.ctx.selection_report = selection_report
        self.report(f"筛选完成：阈值 {threshold}，top_k {top_k}，选中 {len(selected_ids)} 条")

    def finalize(self):
        """输出所有公共端口结果。"""
        self.out("sequences", self.ctx.sequences)
        self.out("scores", self.ctx.scores)
        self.out("selected_sequences", self.ctx.selected_sequences)
        self.out("sample_table", self.ctx.sample_table)
        self.out("selection_report", self.ctx.selection_report)

    # ---------------- 工具 ----------------

    @staticmethod
    def _read_fasta(path):
        """解析 fasta，返回 [(id, seq), ...] 列表。"""
        records = []
        cur_id = None
        chunks = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith(">"):
                    if cur_id is not None:
                        records.append((cur_id, "".join(chunks)))
                    cur_id = line[1:].strip()
                    chunks = []
                else:
                    chunks.append(line)
        if cur_id is not None:
            records.append((cur_id, "".join(chunks)))
        return records
