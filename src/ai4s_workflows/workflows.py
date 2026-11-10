"""MPNN生成、产物校验和筛选；支持有限重试与上游结果复用。"""

import hashlib
import math

from aiida.engine import ToContext, WorkChain, while_
from aiida.orm import AbstractCode, CalcJobNode, Dict, SinglefileData
from aiida.plugins import CalculationFactory

from .filtering import filter_sequences, record_failure_report
from ai4s_tasks.proteinmpnn_outputs import complete_parameters

# v1.0/v1.1 来自 mock；8907e667-... 为共用 ProteinMPNN 的真实版本（A 侧 ai4s.proteinmpnn）。
SUPPORTED_VERSIONS = ["v1.0", "v1.1", "8907e667-py312-torch260cu124"]
MAX_RETRY = 2
# Code 未声明默认插件时使用真实 ProteinMPNN；mock Code 声明 ai4s.light-mpnn。
DEFAULT_MPNN_CALCULATION = "ai4s.proteinmpnn"


def validate_filter_params(value, _context):
    params = value.get_dict()
    threshold, top_k = params.get("score_threshold"), params.get("top_k")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold):
        return "score_threshold must be finite"
    if type(top_k) is not int or top_k < 1:
        return "top_k must be a positive integer"


def upstream_problem(node, code, pdb_file, params):
    """Verify native provenance and this request before consuming an old result."""
    source = node.creator
    if not isinstance(source, CalcJobNode) or not source.is_finished_ok:
        return "upstream result must come from a successful CalcJob"
    if "result" not in source.outputs or source.outputs.result.uuid != node.uuid:
        return "upstream result is not the creator's result output"
    plugin = code.default_calc_job_plugin or DEFAULT_MPNN_CALCULATION
    if source.process_type != f"aiida.calculations:{plugin}":
        return "upstream calculation plugin differs from requested plugin"
    if source.inputs.code.uuid != code.uuid:
        return "upstream Code differs from requested Code"
    def pdb_hash(data):
        with data.open(mode="rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    if pdb_hash(source.inputs.pdb_file) != pdb_hash(pdb_file):
        return "upstream PDB content differs from requested PDB"
    old_params, new_params = source.inputs.params.get_dict(), params.get_dict()
    if plugin == "ai4s.proteinmpnn":
        old_params, new_params = complete_parameters(old_params), complete_parameters(new_params)
    if old_params != new_params:
        return "upstream parameters differ from requested parameters"
    result = node.get_dict()
    validation = result.get("validation", {})
    if validation.get("passed") is not True:
        return "upstream validation did not pass"
    if result.get("task_id") != "proteinmpnn" or result.get("contract_version") != "1":
        return "upstream task or contract differs from ProteinMPNN contract 1"
    artifacts = result["artifacts"]
    sequence = [entry for entry in artifacts if entry.get("port") == "artifacts.sequences"]
    if len(sequence) != 1 or not sequence[0].get("samples"):
        return "exactly one non-empty sequence artifact is required"
    samples = sequence[0]["samples"]
    ids = [sample["sample_id"] for sample in samples]
    if len(set(ids)) != len(ids) or sequence[0].get("sample_count") != len(samples):
        return "upstream sample identities or count are inconsistent"
    if any(not math.isfinite(sample["score"]) for sample in samples):
        return "upstream sample scores must be finite"
    if plugin == "ai4s.proteinmpnn":
        from ai4s_tasks.proteinmpnn import VALIDATOR_VERSION
        if validation.get("validator_version") != VALIDATOR_VERSION:
            return "upstream needs validation with the current ProteinMPNN validator"
        required = {"artifacts.sequences", "artifacts.scores"}
        if new_params["save_probabilities"]:
            required.add("artifacts.probabilities")
        by_port = {entry["port"]: entry for entry in artifacts}
        if len(by_port) != len(artifacts) or not required <= by_port.keys():
            return "required file artifact ports are missing or duplicated"
        for port in required:
            output = source.outputs
            for component in port.split("."):
                output = output[component]
            if not isinstance(output, SinglefileData) or by_port[port].get("files") != [output.filename]:
                return f"artifact file does not match native output {port}"
            if by_port[port].get("sample_ids") != ids or by_port[port].get("sample_count") != len(samples):
                return f"sample mapping differs for {port}"
    return None


class ProteinMPNNFilterWorkChain(WorkChain):
    """最多重试两次；已有上游结果也需通过同一套门禁。"""

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input("code", valid_type=AbstractCode)
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("mpnn_params", valid_type=Dict)
        spec.input("filter_params", valid_type=Dict, validator=validate_filter_params)
        spec.input("existing_mpnn_result", valid_type=Dict, required=False)

        spec.output("selected_sequences", valid_type=Dict)
        spec.output("sample_table", valid_type=Dict)
        spec.output("selection_report", valid_type=Dict)

        spec.exit_code(201, "VERSION_NOT_SUPPORTED", message="MPNN版本不在支持白名单")
        spec.exit_code(202, "MAX_RETRY_REACHED", message="达到最大重试次数，任务终止")
        spec.exit_code(203, "MISSING_MPNN_OUTPUT", message="MPNN输出缺失artifacts")
        spec.exit_code(204, "INVALID_ARTIFACT_SCHEMA", message="产物schema_version不匹配ai4s-artifacts-1")
        spec.exit_code(205, "MPNN_CALC_FAILED", message="MPNN计算失败")
        spec.exit_code(206, "UNQUALIFIED_UPSTREAM", message="上游资格或请求身份不匹配：{reason}")

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
        entry_point = self.inputs.code.default_calc_job_plugin or DEFAULT_MPNN_CALCULATION
        builder = CalculationFactory(entry_point).get_builder()
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
        # 缓存命中时模型没有真正运行，记录来源以免把它算作一次新的模型执行。
        self.ctx.mpnn_cache_source = calculation.base.caching.get_cache_source()

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
        try:
            problem = upstream_problem(
                self.ctx.mpnn_result, self.inputs.code, self.inputs.pdb_file, self.inputs.mpnn_params
            )
        except (AttributeError, KeyError, TypeError, ValueError, OSError) as error:
            problem = f"malformed upstream: {error}"
        if problem:
            self.output_failure_report("unqualified_upstream")
            return self.exit_codes.UNQUALIFIED_UPSTREAM.format(reason=problem)

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
            "mpnn_cache_source": self.ctx.get("mpnn_cache_source"),
        })
        outputs = filter_sequences(
            self.ctx.mpnn_result, self.inputs.filter_params, execution_report
        )
        self.out_many(outputs)
        self.report("两阶段workchain全部执行完成")
