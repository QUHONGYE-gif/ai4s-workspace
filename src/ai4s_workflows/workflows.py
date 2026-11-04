"""
两阶段 WorkChain：ProteinMPNN 生成 → 门禁校验 → 筛选
- 最多 2 次有限重试，保留每次作业身份 / 状态 / 启动计数
- 门禁 4 条：is_finished_ok + 清单 schema + 必需端口齐全 + 无已知失效
- 筛选规则：score ≤ threshold，升序取 top_k，同分按 sample_id
- 输出：selected_sequences / sample_table / selection_report
- 支持重算：传入 existing_mpnn_result 时跳过推理，model_launches = 0
"""
from aiida.engine import WorkChain, ToContext
from aiida.orm import Dict
from .calcjobs import LightMPNNCalcJob

SUPPORTED_VERSIONS = ["v1.0", "v1.1"]
MAX_RETRIES = 2
REQUIRED_MPNN_KEYS = ["version", "sequences", "scores"]


class ProteinMPNNFilterWorkChain(WorkChain):
    """
    C 模块核心 WorkChain
    输入：code / pdb_file / mpnn_params / filter_params
    可选输入：existing_mpnn_result（重算场景，复用上游 MPNN 结果）
    输出：mpnn_result / selected_sequences / sample_table / selection_report
    """

    @classmethod
    def define(cls, spec):
        super().define(spec)
        # ===== 输入端口 =====
        spec.input("code", valid_type=__import__("aiida.orm").Code)
        spec.input("pdb_file", valid_type=__import__("aiida.orm").SinglefileData)
        spec.input("mpnn_params", valid_type=Dict)
        spec.input("filter_params", valid_type=Dict)
        # 可选：传入已有 MPNN 结果，跳过重推理（用于重算场景）
        spec.input("existing_mpnn_result", valid_type=Dict, required=False)

        # ===== 输出端口 =====
        spec.output("mpnn_result", valid_type=Dict, required=True)
        spec.output("selected_sequences", valid_type=Dict, required=True)
        spec.output("sample_table", valid_type=Dict, required=True)
        spec.output("selection_report", valid_type=Dict, required=True)

        # ===== 流程入口 =====
        spec.outline(
            cls.run,
            cls.setup_mpnn,
            cls.check_mpnn_result,
            cls.run_filter,
            cls.finalize,
        )

        # ===== 退出码 =====
        spec.exit_code(201, "ERROR_VERSION_NOT_SUPPORTED",
                       message="MPNN 版本不在支持白名单")
        spec.exit_code(202, "ERROR_MAX_RETRY_REACHED",
                       message="达到最大重试次数，任务终止")
        spec.exit_code(203, "ERROR_OUTPUT_SCHEMA_INVALID",
                       message="MPNN 输出清单 schema 校验失败")
        spec.exit_code(204, "ERROR_FILTER_EMPTY",
                       message="筛选后无结果")

    def run(self):
        """初始化上下文"""
        self.ctx.retry_count = 0
        self.ctx.infer_job_ids = []  # 记录每次 MPNN 作业的 pk
        self.ctx.model_launches = 0   # 模型启动次数计数
        self.ctx.has_existing = "existing_mpnn_result" in self.inputs
        self.report("两阶段 WorkChain 启动")

    def setup_mpnn(self):
        """
        准备 MPNN：
        - 若传入 existing_mpnn_result，直接复用（重算场景）
        - 否则提交 LightMPNNCalcJob 推理
        """
        if self.ctx.has_existing:
            self.ctx.mpnn_result = self.inputs.existing_mpnn_result
            self.report(
                "检测到 existing_mpnn_result，复用上游产物，"
                "跳过 MPNN 推理（model_launches = 0）"
            )
            return

        # 提交第一次推理
        return self._submit_inference()

    def _submit_inference(self):
        """提交 MPNN 推理 CalcJob"""
        builder = LightMPNNCalcJob.get_builder()
        builder.code = self.inputs.code
        builder.pdb_file = self.inputs.pdb_file
        builder.params = self.inputs.mpnn_params
        future = self.submit(builder)
        self.ctx.model_launches += 1
        self.report(
            f"第 {self.ctx.retry_count + 1} 次 MPNN 推理已提交，"
            f"model_launches = {self.ctx.model_launches}"
        )
        return ToContext(mpnn_calc=future)

    def check_mpnn_result(self):
        """
        门禁校验（4 条全实现）：
        1. is_finished_ok：CalcJob 是否正常完成
        2. 清单 schema：输出是否包含必需字段
        3. 必需端口齐全：所有必需输出端口都有值
        4. 无已知失效：版本是否在白名单内
        失败则重试，最多 MAX_RETRIES 次
        """
        # 重算场景：直接复用，跳过门禁
        if self.ctx.has_existing:
            self.report("重算场景，跳过门禁校验")
            return

        calc = self.ctx.mpnn_calc

        # --- 门禁 1：is_finished_ok ---
        if not calc.is_finished_ok:
            self.report(
                f"门禁 1 失败：CalcJob 未正常完成，状态 = {calc.process_state}"
            )
            self.ctx.retry_count += 1
            self.ctx.infer_job_ids.append(calc.pk)
            if self.ctx.retry_count >= MAX_RETRIES:
                self.report("达到最大重试次数，终止")
                return self.exit(self.exit_codes.ERROR_MAX_RETRY_REACHED)
            self.report(f"进行第 {self.ctx.retry_count + 1} 次重试")
            return self._submit_inference()

        # 记录本次成功的作业 id
        self.ctx.infer_job_ids.append(calc.pk)

        # --- 取输出 ---
        mpnn_out = calc.outputs.result
        mpnn_dict = mpnn_out.get_dict()

        # --- 门禁 2：清单 schema ---
        missing = [k for k in REQUIRED_MPNN_KEYS if k not in mpnn_dict]
        if missing:
            self.report(f"门禁 2 失败：输出缺少字段 {missing}")
            return self.exit(self.exit_codes.ERROR_OUTPUT_SCHEMA_INVALID)

        # --- 门禁 3：必需端口齐全 ---
        if mpnn_out is None:
            self.report("门禁 3 失败：必需输出端口 result 为空")
            return self.exit(self.exit_codes.ERROR_OUTPUT_SCHEMA_INVALID)

        # --- 门禁 4：无已知失效（版本白名单） ---
        version = mpnn_dict.get("version")
        if version not in SUPPORTED_VERSIONS:
            self.report(
                f"门禁 4 失败：版本 {version} 不在支持白名单 {SUPPORTED_VERSIONS}"
            )
            return self.exit(self.exit_codes.ERROR_VERSION_NOT_SUPPORTED)

        self.report("4 条门禁全部通过，进入筛选阶段")
        self.ctx.mpnn_result = mpnn_out

    def run_filter(self):
        """
        筛选阶段：
        规则：score ≤ score_threshold，升序取 top_k，同分按 sample_id
        """
        mpnn_dict = self.ctx.mpnn_result.get_dict()
        f_params = self.inputs.filter_params.get_dict()

        threshold = f_params["score_threshold"]
        top_k = f_params["top_k"]

        sequences = mpnn_dict["sequences"]
        scores = mpnn_dict["scores"]

        # 组装候选列表
        candidates = []
        for i, (seq, score) in enumerate(zip(sequences, scores)):
            sample_id = f"sample_{i:03d}"
            candidates.append({
                "sample_id": sample_id,
                "sequence": seq,
                "score": score,
            })

        # 筛选：score ≤ threshold
        filtered = [c for c in candidates if c["score"] <= threshold]

        # 排序：升序（score 小的在前），同分按 sample_id
        filtered.sort(key=lambda x: (x["score"], x["sample_id"]))

        # 取 top_k
        selected = filtered[:top_k]

        if not selected:
            self.report("筛选后无结果")
            return self.exit(self.exit_codes.ERROR_FILTER_EMPTY)

        # 构造输出
        self.ctx.selected_sequences = Dict({
            "sequences": [s["sequence"] for s in selected],
            "count": len(selected),
        })

        self.ctx.sample_table = Dict({
            "columns": ["sample_id", "sequence", "score"],
            "rows": [[s["sample_id"], s["sequence"], s["score"]] for s in selected],
            "selected_ids": [s["sample_id"] for s in selected],
        })

        self.report(f"筛选完成，选出 {len(selected)} 条序列")

    def finalize(self):
        """输出全部结果端口"""
        self.out("mpnn_result", self.ctx.mpnn_result)
        self.out("selected_sequences", self.ctx.selected_sequences)
        self.out("sample_table", self.ctx.sample_table)

        # selection_report：记录作业身份、启动计数、重试次数
        report = Dict({
            "infer_job_ids": self.ctx.infer_job_ids,
            "retry_count": self.ctx.retry_count,
            "model_launches": self.ctx.model_launches,
            "supported_versions": SUPPORTED_VERSIONS,
            "max_retries": MAX_RETRIES,
        })
        self.out("selection_report", report)

        self.report(
            f"WorkChain 完成。"
            f"model_launches = {self.ctx.model_launches}, "
            f"retry_count = {self.ctx.retry_count}"
        )
