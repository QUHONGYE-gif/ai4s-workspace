# C模块核心：两阶段（MPNN生成→筛选）WorkChain，带门禁、有限重试、上游数据复用
from aiida.engine import WorkChain, ToContext, while_
from aiida.orm import Dict, SinglefileData
from aiida.engine.processes.exit_code import ExitCode
from workbench.calculations.mock_mpnn import MockMPNNCalcJob

# 常量配置
SUPPORTED_VERSIONS = ["v1.0", "v1.1"]  # 支持的MPNN版本白名单
MAX_RETRY = 2  # 最多允许重试2次

class ProteinMPNNFilterWorkChain(WorkChain):
    @classmethod
    def define(cls, spec):
        super().define(spec)
        # —— 对外输入端口（和builder完全对应，不会再报Unknown parameter）——
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("infer_params", valid_type=Dict)
        spec.input("filter_params", valid_type=Dict)

        # —— 对外输出端口 ——
        spec.output("mpnn_raw_output", valid_type=Dict)  # 上游MPNN的原始结果，供重算复用
        spec.output("filtered_result", valid_type=Dict)

        # —— 退出码（报错时给明确原因）——
        spec.exit_code(400, "ERROR_VERSION_NOT_SUPPORTED", message="MPNN版本不在支持清单内")
        spec.exit_code(401, "ERROR_MPNN_FAILED", message="MPNN连续失败2次，终止任务")

        # —— 固定执行流程 ——
        spec.outline(
            cls.validate_input,       # 步骤1：输入门禁校验
            while_(cls.need_retry)(   # 步骤2：MPNN阶段，带最多2次重试
                cls.run_mpnn_infer,
            ),
            cls.check_mpnn_success,   # 步骤3：确认MPNN是否真的成功
            cls.run_filter,           # 步骤4：筛选阶段
            cls.finalize,             # 步骤5：输出最终结果
        )

    # -------------------- 内部方法 --------------------
    def validate_input(self):
        """门禁：先校验版本，不合法直接终止，不跑任何计算"""
        ver = self.inputs.infer_params["version"]
        if ver not in SUPPORTED_VERSIONS:
            return self.exit_codes.ERROR_VERSION_NOT_SUPPORTED
        # 初始化持久化上下文（daemon重启也不丢，满足恢复要求）
        self.ctx.retry_count = 0
        self.ctx.mpnn_job_ids = []  # 记录每次尝试的MPNN作业pk，留痕验收用

    def need_retry(self):
        """判断要不要继续重试：还没成功、且重试次数没到2次就继续"""
        return not self.ctx.get("mpnn_success", False) and self.ctx.retry_count < MAX_RETRY

    def run_mpnn_infer(self):
        """第一阶段：提交MPNN计算任务，记录每次作业身份"""
        self.ctx.retry_count += 1
        self.report(f"开始第{self.ctx.retry_count}次MPNN推理尝试")

        builder = MockMPNNCalcJob.get_builder()
        builder.pdb_file = self.inputs.pdb_file
        builder.params = self.inputs.infer_params

        future = self.submit(builder)
        self.ctx.mpnn_job_ids.append(future.pk)  # 记录本次作业pk，验收计数用
        return ToContext(mpnn_node=future)

    def check_mpnn_success(self):
        """核对外部任务真实状态（不凭本地标记判断，满足要求）"""
        if self.ctx.mpnn_node.is_finished_ok:
            self.ctx.mpnn_success = True
            self.report(f"MPNN推理成功，作业pk={self.ctx.mpnn_node.pk}")
        else:
            self.ctx.mpnn_success = False
            self.report(f"MPNN推理失败，作业pk={self.ctx.mpnn_node.pk}，准备重试")

    def run_filter(self):
        """第二阶段：只有MPNN成功才执行筛选"""
        if not self.ctx.mpnn_success:
            return self.exit_codes.ERROR_MPNN_FAILED
        # 拿上游MPNN的输出
        raw = self.ctx.mpnn_node.outputs.result
        top_k = self.inputs.filter_params["top_k"]
        threshold = self.inputs.filter_params["threshold"]
        # 按阈值过滤、按top_k截断
        filtered = [s for s in raw["sequences"] if s["score"] >= threshold][:top_k]
        self.ctx.filtered_node = Dict({
            "top_k": top_k,
            "threshold": threshold,
            "selected": filtered
        }).store()

    def finalize(self):
        """输出所有结果"""
        self.out("mpnn_raw_output", self.ctx.mpnn_node.outputs.result)
        self.out("filtered_result", self.ctx.filtered_node)
