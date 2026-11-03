# C模块核心：两阶段（MPNN生成→筛选）WorkChain，带门禁、有限重试、上游数据复用
from aiida.engine import WorkChain, ToContext, while_
from aiida.orm import Dict, SinglefileData, Bool
from aiida.engine.processes.exit_code import ExitCode
from workbench.calculations.mock_mpnn import MockMPNNCalcJob

# 常量配置
SUPPORTED_VERSIONS = ["v1.0", "v1.1"]  # 支持的MPNN版本白名单
MAX_RETRY = 2  # 最多允许重试2次

class ProteinMPNNFilterWorkChain(WorkChain):
    @classmethod
    def define(cls, spec):
        super().define(spec)
        # —— 对外输入端口（和builder完全对应）——
        spec.input("pdb_file", valid_type=SinglefileData, required=False, help="输入PDB结构，从头跑MPNN时必填")
        spec.input("infer_params", valid_type=Dict, required=False, help="MPNN推理参数（version、temperature等）")
        spec.input("filter_params", valid_type=Dict, help="筛选参数 top_k / threshold")
        spec.input("reuse_mpnn", valid_type=Bool, required=False, default=lambda: Bool(False), help="是否复用已有MPNN结果")
        spec.input("mpnn_raw_output", valid_type=Dict, required=False, help="复用模式：传入已经跑完的MPNN结果")

        # —— 对外输出端口 ——
        spec.output("mpnn_raw_output", valid_type=Dict, help="上游MPNN的原始结果，供重算复用")
        spec.output("filtered_result", valid_type=Dict, help="筛选后的序列结果")

        # —— 退出码（报错时给明确原因）——
        spec.exit_code(400, "ERROR_VERSION_NOT_SUPPORTED", message="MPNN版本不在支持清单内")
        spec.exit_code(401, "ERROR_MPNN_FAILED", message="MPNN达到最大重试次数，任务终止")
        spec.exit_code(402, "ERROR_REUSE_INPUT_INVALID", message="reuse_mpnn=True时必须提供mpnn_raw_output")

        # —— 固定执行流程 ——
        spec.outline(
            cls.validate_input,                 # 步骤1：输入门禁校验
            cls.branch_mpnn_or_reuse,           # 分支：复用旧结果 / 走MPNN生成+重试
            while_(cls.need_retry)(             # 重试循环：提交+检查
                cls.run_mpnn_infer,
                cls.check_mpnn_success,
            ),
            cls.check_final_mpnn_status,        # 循环结束后，判定是否成功
            cls.run_filter,                     # 步骤4：筛选阶段
            cls.finalize,                       # 步骤5：输出最终结果
        )

    def validate_input(self):
        """门禁：校验版本、复用模式参数合法性，不合法直接终止"""
        reuse = self.inputs.reuse_mpnn.value
        if reuse:
            if "mpnn_raw_output" not in self.inputs:
                self.exit(self.exit_codes.ERROR_REUSE_INPUT_INVALID)
                return
            # 复用模式，不需要pdb、infer_params
            self.ctx.reuse_mode = True
            self.report("【复用模式】使用已有MPNN结果，不会启动模型推理")
        else:
            self.ctx.reuse_mode = False
            # 从头跑模式，校验版本
            ver = self.inputs.infer_params["version"]
            if ver not in SUPPORTED_VERSIONS:
                self.exit(self.exit_codes.ERROR_VERSION_NOT_SUPPORTED)
                return
            # 初始化持久化上下文（daemon重启也不丢）
            self.ctx.retry_count = 0
            self.ctx.mpnn_job_ids = []  # 记录每次尝试的MPNN作业pk，留痕验收用
            self.ctx.mpnn_success = False

    def branch_mpnn_or_reuse(self):
        if self.ctx.reuse_mode:
            # 直接把传入的mpnn结果放进ctx，跳过MPNN循环
            self.ctx.mpnn_node = self.inputs.mpnn_raw_output
            self.ctx.mpnn_success = True
            self.report("复用上游MPNN数据完成，直接进入筛选")

    def need_retry(self):
        """判断要不要继续重试：未成功、次数没到上限，且不是复用模式"""
        if self.ctx.get("reuse_mode", False):
            return False
        return not self.ctx.get("mpnn_success", False) and self.ctx.retry_count < MAX_RETRY

    def run_mpnn_infer(self):
        """第一阶段：提交MPNN计算任务，记录每次作业身份"""
        self.ctx.retry_count += 1
        self.report(f"开始第{self.ctx.retry_count}次MPNN推理尝试")
        builder = MockMPNNCalcJob.get_builder()
        builder.pdb_file = self.inputs.pdb_file
        builder.params = self.inputs.infer_params
        # 补上必须的资源配置，本地mock用最小配置
        builder.options = {
            "resources": {"num_machines": 1, "tot_num_mpiprocs": 1},
            "withmpi": False,
        }
        future = self.submit(builder)
        self.ctx.mpnn_job_ids.append(future.pk)
        return ToContext(mpnn_node=future)

    def check_mpnn_success(self):
        """核对外部任务真实状态（不凭本地标记判断，满足要求）"""
        if self.ctx.mpnn_node.is_finished_ok:
            self.ctx.mpnn_success = True
            self.report(f"MPNN推理成功，作业pk={self.ctx.mpnn_node.pk}，停止重试")
        else:
            self.ctx.mpnn_success = False
            self.report(f"MPNN推理失败，作业pk={self.ctx.mpnn_node.pk}，准备重试")

    def check_final_mpnn_status(self):
        """while循环结束后统一检查：全部重试失败则退出"""
        if not self.ctx.mpnn_success:
            self.report(f"MPNN重试{MAX_RETRY}次全部失败，终止流程")
            self.exit(self.exit_codes.ERROR_MPNN_FAILED)

    def run_filter(self):
        """第二阶段：只有MPNN成功才执行筛选"""
        raw = self.ctx.mpnn_node
        top_k = self.inputs.filter_params["top_k"]
        threshold = self.inputs.filter_params["threshold"]
        # 按阈值过滤、按top_k截断
        filtered = [s for s in raw["sequences"] if s["score"] >= threshold][:top_k]
        self.ctx.filtered_node = Dict({
            "top_k": top_k,
            "threshold": threshold,
            "selected": filtered
        }).store()
        self.report(f"筛选完成，保留{len(filtered)}条序列")

    def finalize(self):
        """输出所有结果"""
        self.out("mpnn_raw_output", self.ctx.mpnn_node)
        self.out("filtered_result", self.ctx.filtered_node)
