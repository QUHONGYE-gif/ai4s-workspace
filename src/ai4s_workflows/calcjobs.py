"""
C 模块自建的轻量 CalcJob：模拟 ProteinMPNN 单任务（生成 4 条设计序列）。

设计目标（对应分工文档 C 的「自建可等待、可失败的轻量 CalcJob」）：
  - 原生 CalcJob 形态，经 computer + code 提交，可被调度、可等待。
  - 通过 `attempt` / `fail_if_le` 输入，可让前 N 次尝试失败，用于验证有限重试。
  - 输出公共接口：artifacts.sequences / artifacts.scores / 产物清单 manifest，
    与 A 侧真实任务保持相同端口，接真实任务时只需替换 `submit_infer` 里的类。

A 侧真实任务就绪后，本类仅作对照；WorkChain 换用真实 CalcJob 即可。
"""
from aiida.engine import CalcJob
from aiida.orm import Dict, SinglefileData, Int, Float
from aiida.common import CalcInfo


class LightMPNNCalcJob(CalcJob):
    """轻量 ProteinMPNN 模拟任务：输入 PDB，输出 4 条序列 + 分数 + 清单。"""

    @classmethod
    def define(cls, spec):
        super().define(spec)

        # ---- 输入（公共接口：与 A 侧对齐）----
        spec.input("pdb", valid_type=SinglefileData, required=True, help="输入 PDB 结构文件")
        spec.input(
            "params",
            valid_type=Dict,
            required=True,
            help="推理参数：version / temperature / batch_size / seed",
        )
        spec.input("attempt", valid_type=Int, required=False, default=None,
                   help="本次尝试编号，用于可控失败与启动计数")
        spec.input("fail_if_le", valid_type=Int, required=False, default=lambda: Int(0),
                   help="attempt <= fail_if_le 时模拟失败（默认 0=不失败）")
        spec.input("sleep", valid_type=Float, required=False, default=lambda: Float(0.0),
                   help="模拟计算耗时（秒），用于 daemon 中断恢复验证")

        # ---- 输出 ----
        spec.output("sequences", valid_type=SinglefileData, help="设计序列 fasta（artifacts.sequences）")
        spec.output("scores", valid_type=Dict, help="样本 id 与分数（artifacts.scores）")
        spec.output("manifest", valid_type=Dict, help="产物清单（ai4s-artifacts-1）")

        # ---- 退出码 ----
        spec.exit_code(300, "ERROR_MOCK_FAIL", message="mock 模拟推理失败")

    def prepare_for_submission(self, folder):
        """把 PDB 拷入工作目录，拼好 mock 可执行程序的命令行。"""
        from aiida.common import datastructures

        code = self.inputs.code  # CalcJob 内置的 code 输入
        calcinfo = CalcInfo()

        # 输入文件：PDB 进入 pdb/input.pdb
        calcinfo.local_copy_list = [
            (self.inputs.pdb.uuid, self.inputs.pdb.filename, "pdb/input.pdb"),
        ]

        # 检索输出目录
        calcinfo.retrieve_list = ["outputs/"]

        attempt = int(self.inputs.attempt) if self.inputs.attempt else 1
        cmdline = [
            "--pdb", "pdb/input.pdb",
            "--seqout", "outputs/design.fa",
            "--scoreout", "outputs/scores.json",
            "--manifestout", "outputs/manifest.json",
            "--attempt", str(attempt),
            "--fail-if-le", str(int(self.inputs.fail_if_le)),
            "--sleep", str(float(self.inputs.sleep)),
        ]
        calcinfo.codes_info = [
            datastructures.CodeInfo(
                code_uuid=code.uuid,
                cmdline_params=cmdline,
                stdout_name="outputs/aiida.out",
                stderr_name="outputs/aiida.err",
            )
        ]
        return calcinfo

    def parse(self, folder):
        """读取 mock 输出，构造 Data 节点；若存在失败标记则返回失败退出码。"""
        import json
        import os
        import pathlib

        outdir = pathlib.Path(folder.get_abs_path("outputs"))
        fail_marker = outdir / "_FAILED"

        if fail_marker.exists():
            # 失败标记存在：模拟任务失败
            return self.exit_codes.ERROR_MOCK_FAIL

        # sequences fasta -> SinglefileData
        fa = outdir / "design.fa"
        seq_data = SinglefileData(fa).store()

        # scores.json -> Dict
        with open(outdir / "scores.json") as f:
            scores_dict = json.load(f)
        scores_data = Dict(scores_dict).store()

        # manifest.json -> Dict
        with open(outdir / "manifest.json") as f:
            manifest_dict = json.load(f)
        manifest_data = Dict(manifest_dict).store()

        self.out("sequences", seq_data)
        self.out("scores", scores_data)
        self.out("manifest", manifest_data)
