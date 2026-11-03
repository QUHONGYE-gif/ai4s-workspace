from aiida.engine import WorkChain, ToContext, while_
from aiida.orm import Dict, SinglefileData
from aiida.engine.processes.exit_code import ExitCode

# 现在调试用mock；等A侧交付后改成 from .calculations.mpnn import ProteinMPNNCalcJob
from workbench.calculations.mock_mpnn import MockMPNNCalcJob


class ProteinMPNNFilterWorkChain(WorkChain):
    """
    C模块主WorkChain：生成 → 校验 → 筛选
    参数分离：model_params（推理）、filter_params（筛选）
    自带最多2次有限重试、失败拦截、ctx持久化
    """
    MAX_RETRY = 2

    @classmethod
    def define(cls, spec):
        super().define(spec)

        # ========== 输入端口，严格分开两组参数 ==========
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("model_params", valid_type=Dict)
        spec.input("filter_params", valid_type=Dict)

        # ========== 输出端口 ==========
        spec.output("raw_generation_data", valid_type=Dict)
        spec.output("filtered_result", valid_type=Dict)

       # 定义流程顺序：先校验 → 跑推理（带重试）→ 跑筛选 → 结束
        spec.outline(
            cls.validate_input,
            while_(cls.need_retry)(
                cls.run_mpnn_infer,
            ),
            cls.run_filter,
            cls.finalize,
        )

        # 定义两个标准化退出码，方便排查
        spec.exit_code(400, "ERROR_VERSION_NOT_SUPPORTED", message="MPNN版本不在支持清单内")
        spec.exit_code(401, "ERROR_MPNN_FAILED", message="MPNN推理连续失败2次，终止任务")

    def init_ctx(self):
        """初始化持久上下文，daemon重启不会丢失"""
        self.ctx.retry_count = 0
        self.ctx.mpnn_node = None
        self.ctx.mpnn_output = None

    def need_retry(self):
        """重试判断条件：没到上限、并且上游还没成功产出数据"""
        if self.ctx.retry_count >= self.MAX_RETRY:
            return False
        if self.ctx.mpnn_output is not None:
            return False
        return True

    def submit_mpnn_job(self):
        """原生提交CalcJob，WorkChain自动等待任务完成"""
        self.ctx.retry_count += 1
        builder = MockMPNNCalcJob.get_builder()
        builder.pdb_file = self.inputs.pdb_file
        builder.model_params = self.inputs.model_params
        future = self.submit(builder)
        return ToContext(mpnn_calc=future)

    def check_mpnn_result(self):
        """闸门校验：全部通过才往下走；失败则进入重试循环"""
        calc = self.ctx.mpnn_calc

        # 1. 判断计算是否正常结束
        if not calc.is_finished_ok:
            self.report(f"第{self.ctx.retry_count}次MPNN任务失败")
            return self.exit_codes.ERROR_MPNN_FAILED

        # 2. 版本校验
        model_ver = self.inputs.model_params["model_version"]
        SUPPORTED_VERSIONS = ["v1.0"]
        if model_ver not in SUPPORTED_VERSIONS:
            return self.exit_codes.ERROR_VERSION_INVALID

        # 3. 校验输出key齐全
        if "sequences" not in calc.outputs.raw_data:
            return self.exit_codes.ERROR_OUTPUT_MISSING

        self.ctx.mpnn_output = calc.outputs.raw_data
        self.ctx.mpnn_node = calc

    def run_filter_stage(self):
        """第二阶段：筛选，纯轻量逻辑，不提交CalcJob"""
        raw_data = self.ctx.mpnn_output
        filter_cfg = self.inputs.filter_params

        top_k = filter_cfg["top_k"]
        score_thresh = filter_cfg["score_threshold"]
        seq_list = raw_data["sequences"]

        filtered_seq = [s for s in seq_list if s["score"] >= score_thresh][:top_k]
        self.ctx.filter_result = Dict(dict={"filtered": filtered_seq})

    def package_results(self):
        self.out("raw_generation_data", self.ctx.mpnn_output)
        self.out("filtered_result", self.ctx.filter_result)
    
        def validate_input(self):
        """门禁1：先校验版本，不支持直接终止，不跑计算"""
        ver = self.inputs.infer_params["version"]
        if ver not in SUPPORTED_MPNN_VERSIONS:
            return self.exit_codes.ERROR_VERSION_NOT_SUPPORTED
        # 持久化重试计数，daemon重启也不丢
        self.ctx.retry_count = 0
        self.ctx.mpnn_job_ids = []  # 记录每次MPNN尝试的作业pk

    def need_retry(self):
        """判断要不要继续重试：没跑成功、且重试次数没到2次就继续"""
        return not self.ctx.get("mpnn_success", False) and self.ctx.retry_count < MAX_RETRY

    def run_mpnn_infer(self):
    self.ctx.retry_count += 1
    builder = MockMPNNCalcJob.get_builder()
    builder.pdb_file = self.inputs.pdb_file
    builder.params = self.inputs.infer_params
    future = self.submit(builder)
    self.ctx.mpnn_job_ids.append(future.pk)
    return ToContext(mpnn_node=future)

def run_filter(self):
    # 校验上游calcjob是否成功
    if self.ctx.mpnn_node.is_finished_ok:
        self.ctx.mpnn_success = True
    else:
        self.ctx.mpnn_success = False
        self.report(f"MPNN 任务 pk={self.ctx.mpnn_node.pk} 失败，准备重试")
        return
    # 成功才进入筛选逻辑
    raw = self.ctx.mpnn_node.outputs.result
    top_k = self.inputs.filter_params["top_k"]
    threshold = self.inputs.filter_params["threshold"]
    seqs = [s for s in raw["sequences"] if s["score"] >= threshold][:top_k]
    self.ctx.filtered_node = Dict({
        "top_k": top_k,
        "threshold": threshold,
        "selected": seqs
    }).store()


    def finalize(self):
        """输出最终结果"""
        self.out("mpnn_raw_output", self.ctx.mpnn_node.outputs.result)
        self.out("filtered_result", self.ctx.filtered_node)



class ReFilterWorkChain(WorkChain):
    """
    下游重算入口：只做筛选，复用上一轮上游产出
    只改top_k/阈值，不会重新跑MPNN
    """
    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input("raw_generation_data", valid_type=Dict, help="复用之前MPNN输出的原始数据节点")
        spec.input("filter_params", valid_type=Dict, help="新的筛选参数")
        spec.output("filtered_result", valid_type=Dict)
        spec.outline(cls.run_filter)

    def run_filter(self):
        raw_data = self.inputs.raw_generation_data
        filter_cfg = self.inputs.filter_params

        top_k = filter_cfg["top_k"]
        score_thresh = filter_cfg["score_threshold"]
        seq_list = raw_data["sequences"]

        filtered_seq = [s for s in seq_list if s["score"] >= score_thresh][:top_k]
        self.out("filtered_result", Dict(dict={"filtered": filtered_seq}))
