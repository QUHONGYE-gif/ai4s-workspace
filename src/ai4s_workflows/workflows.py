"""MPNN生成、产物校验和筛选；支持有限重试与上游结果复用。"""

from aiida.engine import ToContext, WorkChain, while_
from aiida.orm import AbstractCode, Dict, SinglefileData

from .calcjobs import LightMPNNCalcJob
from .filtering import filter_sequences, record_failure_report

SUPPORTED_VERSIONS = ["v1.0", "v1.1"]
MAX_RETRY = 2


class ProteinMPNNFilterWorkChain(WorkChain):
    """最多重试两次；已有上游结果也需通过同一套门禁。"""

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input("code", valid_type=AbstractCode)
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("mpnn_params", valid_type=Dict)
        spec.input("filter_params", valid_type=Dict)
        spec.input("existing_mpnn_result", valid_type=Dict, required=False)

        spec.output("selected_sequences", valid_type=Dict)
        spec.output("sample_table", valid_type=Dict)
        spec.output("selection_report", valid_type=Dict)

        spec.exit_code(201, "VERSION_NOT_SUPPORTED", message="MPNN版本不在支持白名单")
        spec.exit_code(202, "MAX_RETRY_REACHED", message="达到最大重试次数，任务终止")
        spec.exit_code(203, "MISSING_MPNN_OUTPUT", message="MPNN输出缺失artifacts")
        spec.exit_code(204, "INVALID_ARTIFACT_SCHEMA", message="产物schema_version不匹配ai4s-artifacts-1")
        spec.exit_code(205, "MPNN_CALC_FAILED", message="MPNN计算失败")

        spec.outline(
            cls.initialize_ctx,
            cls.maybe_skip_inference,
            while_(cls.should_retry)(cls.submit_mpnn, cls.on_mpnn_done),
            cls.validate_mpnn_result,
            cls.run_filter,
        )

    def initialize_ctx(self):
        self.ctx.retry_count = 0
        self.ctx.model_launches = 0
        self.ctx.mpnn_success = False
        self.ctx.skip_submit = False

    def maybe_skip_inference(self):
        if "existing_mpnn_result" in self.inputs:
            self.ctx.mpnn_result = self.inputs.existing_mpnn_result
            self.ctx.skip_submit = True

    def should_retry(self):
        return (
            not self.ctx.skip_submit
            and not self.ctx.mpnn_success
            and self.ctx.retry_count <= MAX_RETRY
        )

    def submit_mpnn(self):
        builder = LightMPNNCalcJob.get_builder()
        builder.code = self.inputs.code
        builder.pdb_file = self.inputs.pdb_file
        builder.params = self.inputs.mpnn_params
        self.report(f"提交MPNN推理，第 {self.ctx.retry_count + 1} 次尝试")
        calculation = self.submit(builder)
        self.ctx.model_launches += 1
        return ToContext(mpnn_calc=calculation)

    def on_mpnn_done(self):
        calculation = self.ctx.mpnn_calc
        # Excepted/Killed也不是成功；is_failed只覆盖Finished且非零退出。
        if not calculation.is_finished_ok:
            self.report(f"MPNN未成功，状态={calculation.process_state}")
            if self.ctx.retry_count >= MAX_RETRY:
                self.output_failure_report("failed_max_retry")
                return self.exit_codes.MAX_RETRY_REACHED
            self.ctx.retry_count += 1
            return

        if "result" not in calculation.outputs:
            self.output_failure_report("missing_output")
            return self.exit_codes.MISSING_MPNN_OUTPUT

        self.ctx.mpnn_result = calculation.outputs.result
        self.ctx.mpnn_success = True

    def validate_mpnn_result(self):
        result = self.ctx.mpnn_result.get_dict()
        if result.get("schema_version") != "ai4s-artifacts-1":
            self.output_failure_report("invalid_schema")
            return self.exit_codes.INVALID_ARTIFACT_SCHEMA
        if not result.get("artifacts"):
            self.output_failure_report("missing_output")
            return self.exit_codes.MISSING_MPNN_OUTPUT
        if result.get("version") not in SUPPORTED_VERSIONS:
            self.output_failure_report("unsupported_version")
            return self.exit_codes.VERSION_NOT_SUPPORTED

    def output_failure_report(self, status):
        details = Dict(dict={
            "model_launches": self.ctx.model_launches,
            "retry_attempt": self.ctx.retry_count,
            "status": status,
        })
        self.out("selection_report", record_failure_report(details))

    def run_filter(self):
        execution_report = Dict(dict={
            "model_launches": self.ctx.model_launches,
            "retry_attempt": self.ctx.retry_count,
        })
        outputs = filter_sequences(
            self.ctx.mpnn_result, self.inputs.filter_params, execution_report
        )
        self.out_many(outputs)
        self.report("两阶段workchain全部执行完成")
