"""MPNN生成、产物校验和筛选；支持有限尝试、失败记录与上游结果复用。"""

import hashlib
import math

from aiida.engine import (
    ReuseConfiguration,
    ReuseDecisionError,
    ReuseMaterialization,
    ToContext,
    WorkChain,
    get_reuse_decision_records,
    while_,
)
from aiida.orm import (
    AbstractCode,
    CalcJobNode,
    Dict,
    List,
    QueryBuilder,
    SinglefileData,
    Str,
    load_node,
)
from aiida.plugins import CalculationFactory

from ai4s_tasks.proteinmpnn_outputs import complete_parameters

from .decision import load_decision_function
from .filtering import filter_sequences, record_failure_report

# v1.0/v1.1 来自 mock；8907e667-... 为共用 ProteinMPNN 的真实版本（A 侧 ai4s.proteinmpnn）。
SUPPORTED_VERSIONS = ["v1.0", "v1.1", "8907e667-py312-torch260cu124"]
# 固定最多两次提交：一次首次尝试和一次重试。保留 MAX_RETRY 供已有调用方读取。
MAX_ATTEMPTS = 2
MAX_RETRY = MAX_ATTEMPTS - 1
# Code 未声明默认插件时使用真实 ProteinMPNN；mock Code 声明 ai4s.light-mpnn。
DEFAULT_MPNN_CALCULATION = "ai4s.proteinmpnn"
ATTEMPT_LABEL_PREFIX = "ai4s-mpnn"
WORKCHAIN_PROCESS_TYPE = "aiida.workflows:ai4s.protein-mpnn-filter"
REUSE_DECISION_PORT_NAMES = (
    "request_id",
    "reuse_policy",
    "reuse_candidates",
    "candidate_results",
    "decision_function",
)
REUSE_POLICY_ACTIONS = {
    "allow_reuse": {"reuse", "rerun"},
    "force_rerun": {"rerun"},
    "new_sample": {"new_sample"},
}


def process_state_value(process):
    """Return the native state, treating an unlaunched stored node as created."""
    state = process.process_state
    return "created" if state is None else state.value


def validate_filter_params(value, _context):
    params = value.get_dict()
    threshold, top_k = params.get("score_threshold"), params.get("top_k")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold):
        return "score_threshold must be finite"
    if type(top_k) is not int or top_k < 1:
        return "top_k must be a positive integer"


def attempt_label(workchain_uuid, attempt_number):
    """Return the stable native label used to reconcile an uncertain submission."""
    return f"{ATTEMPT_LABEL_PREFIX}:{workchain_uuid}:{attempt_number:02d}"


def find_calcjobs_by_label(label):
    """Find native CalcJob nodes by their persisted label without submitting work."""
    query = QueryBuilder()
    query.append(CalcJobNode, filters={"label": label})
    return list(query.all(flat=True))


def validation_manifest_problem(result):
    """Describe a manifest that is malformed or already known to be invalid."""
    if not isinstance(result, dict):
        return "manifest must be a dictionary"
    if result.get("schema_version") != "ai4s-artifacts-1":
        return "manifest schema_version differs from ai4s-artifacts-1"
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return "manifest has no artifacts"

    validation = result.get("validation")
    if not isinstance(validation, dict) or validation.get("passed") is not True:
        return "manifest validation did not pass"
    if validation.get("invalidates_cache") is True:
        return "manifest is marked as known to invalidate reuse"
    for field in ("errors", "issues", "known_issues"):
        if validation.get(field):
            return f"manifest contains known validation issues in {field}"

    ports = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not artifact.get("port"):
            return "every artifact must declare a port"
        ports.append(artifact["port"])
    if len(set(ports)) != len(ports):
        return "manifest contains duplicate artifact ports"
    return None


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
    if source.inputs.code.base.caching.compute_hash() != code.base.caching.compute_hash():
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
    manifest_problem = validation_manifest_problem(result)
    if manifest_problem:
        return manifest_problem
    validation = result["validation"]
    if result.get("task_id") != "proteinmpnn" or result.get("contract_version") != "1":
        return "upstream task or contract differs from ProteinMPNN contract 1"
    artifacts = result["artifacts"]
    sequence = [entry for entry in artifacts if entry.get("port") == "artifacts.sequences"]
    if len(sequence) != 1 or not sequence[0].get("samples"):
        return "exactly one non-empty sequence artifact is required"
    samples = sequence[0]["samples"]
    if any(not isinstance(sample, dict) for sample in samples):
        return "upstream samples must be dictionaries"
    ids = [sample.get("sample_id") for sample in samples]
    if any(not isinstance(sample_id, str) or not sample_id for sample_id in ids):
        return "upstream samples need non-empty identities"
    if len(set(ids)) != len(ids) or sequence[0].get("sample_count") != len(samples):
        return "upstream sample identities or count are inconsistent"
    if any(not math.isfinite(sample.get("score", math.nan)) for sample in samples):
        return "upstream sample scores must be finite"
    if any(not (sample.get("seq") or sample.get("sequence")) for sample in samples):
        return "upstream samples need non-empty sequences"
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
            files = by_port[port].get("files")
            if (
                not isinstance(output, SinglefileData)
                or files != [output.filename]
                or len(output.get_content(mode="rb")) <= 0
            ):
                return f"artifact file does not match native output {port}"
            if by_port[port].get("sample_ids") != ids or by_port[port].get("sample_count") != len(samples):
                return f"sample mapping differs for {port}"
    return None


class ProteinMPNNFilterWorkChain(WorkChain):
    """最多两次提交；已有上游结果也需通过同一套门禁。"""

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input("code", valid_type=AbstractCode)
        spec.input("pdb_file", valid_type=SinglefileData)
        spec.input("mpnn_params", valid_type=Dict)
        spec.input("filter_params", valid_type=Dict, validator=validate_filter_params)
        spec.input("existing_mpnn_result", valid_type=Dict, required=False)
        spec.input("request_id", valid_type=Str, required=False)
        spec.input("reuse_policy", valid_type=Str, required=False)
        spec.input("reuse_candidates", valid_type=List, required=False)
        spec.input("candidate_results", valid_type=Dict, required=False)
        spec.input("decision_function", valid_type=Str, required=False)

        spec.output("selected_sequences", valid_type=Dict)
        spec.output("sample_table", valid_type=Dict)
        spec.output("selection_report", valid_type=Dict)

        spec.exit_code(201, "VERSION_NOT_SUPPORTED", message="MPNN版本不在支持白名单")
        spec.exit_code(202, "MAX_ATTEMPTS_REACHED", message="达到最大尝试次数，任务终止")
        spec.exit_code(203, "MISSING_MPNN_OUTPUT", message="MPNN输出缺失artifacts")
        spec.exit_code(204, "INVALID_ARTIFACT_SCHEMA", message="产物schema_version不匹配ai4s-artifacts-1")
        spec.exit_code(205, "MPNN_CALC_FAILED", message="MPNN计算失败")
        spec.exit_code(206, "UNQUALIFIED_UPSTREAM", message="上游资格或请求身份不匹配：{reason}")
        spec.exit_code(207, "SUBMISSION_STATE_UNCERTAIN", message="提交状态不明，已先核对原生作业，不自动重复提交")
        spec.exit_code(208, "INVALID_REUSE_REQUEST", message="复用请求不完整或无效：{reason}")
        spec.exit_code(209, "REUSE_RESULT_UNAVAILABLE", message="复用候选结果不可用：{reason}")

        spec.outline(
            cls.initialize_ctx,
            cls.maybe_skip_inference,
            while_(cls.should_retry)(cls.submit_mpnn, cls.on_mpnn_done),
            cls.validate_mpnn_result,
            cls.run_filter,
        )

    @classmethod
    def _present_reuse_ports(cls, inputs):
        """Return the reuse-related input ports present on a request."""
        return [name for name in REUSE_DECISION_PORT_NAMES if name in inputs]

    @classmethod
    def _reuse_request_problem(cls, inputs, *, allow_kernel_rewrite=False):
        """Validate the reusable request shape before consulting the kernel.

        The kernel adds ``existing_mpnn_result`` while rewriting a legitimate
        ``reuse`` request. Only that already-rewritten request may contain both
        the reuse ports and the injected result.
        """
        present = cls._present_reuse_ports(inputs)
        if not present:
            return None
        if "existing_mpnn_result" in inputs and not allow_kernel_rewrite:
            return "reuse decision ports cannot be combined with existing_mpnn_result"
        missing = [name for name in ("request_id", "reuse_policy") if name not in inputs]
        if missing:
            return "request_id and reuse_policy must be supplied together"
        if "mpnn_params" not in inputs:
            return "mpnn_params is required for a reuse decision"

        try:
            reuse_policy = inputs.reuse_policy.value
        except AttributeError:
            return "reuse_policy must be an AiiDA Str"
        if reuse_policy not in REUSE_POLICY_ACTIONS:
            allowed = ", ".join(sorted(REUSE_POLICY_ACTIONS))
            return f"reuse_policy must be one of: {allowed}"

        try:
            params = inputs.mpnn_params.get_dict()
        except AttributeError:
            return "mpnn_params must be an AiiDA Dict"
        if not isinstance(params, dict) or "seed" not in params:
            return "mpnn_params.seed is required for a reuse decision"
        return None

    def get_reuse_configuration(self):
        """Return the kernel reuse configuration for this WorkChain request."""
        if not self._present_reuse_ports(self.inputs):
            return None
        if self._reuse_request_problem(self.inputs):
            return None
        if "existing_mpnn_result" in self.inputs:
            return None

        try:
            params = self.inputs.mpnn_params.get_dict()
            candidates = (
                self.inputs.reuse_candidates.get_list()
                if "reuse_candidates" in self.inputs
                else []
            )
            decision_function = (
                load_decision_function(self.inputs.decision_function.value)
                if "decision_function" in self.inputs
                else None
            )
            return ReuseConfiguration(
                request_id=self.inputs.request_id.value,
                reuse_policy=self.inputs.reuse_policy.value,
                original_seed=params["seed"],
                input_rewriter=self._rewrite_reuse_inputs,
                candidates=candidates,
                decision_function=decision_function,
                materialization=ReuseMaterialization.CONSUME_CANDIDATE,
            )
        except Exception:
            return None

    def _rewrite_reuse_inputs(self, inputs, decision):
        """Apply the kernel decision to the concrete WorkChain inputs."""
        rewritten = dict(inputs)
        rewritten.pop("existing_mpnn_result", None)
        action = decision.action.value

        try:
            if action == "reuse":
                candidate_results = inputs.get("candidate_results")
                if not isinstance(candidate_results, Dict):
                    raise ReuseDecisionError(
                        "candidate_results is required to materialize a reused result"
                    )
                selected_uuid = decision.selected_candidate_uuid
                matches = [
                    candidate
                    for candidate in decision.candidate_compare_list
                    if candidate.get("uuid") == selected_uuid
                ]
                if len(matches) != 1:
                    raise ReuseDecisionError(
                        "candidate_compare_list must uniquely identify the selected UUID"
                    )
                fingerprint = matches[0].get("fingerprint")
                if not isinstance(fingerprint, str) or not fingerprint:
                    raise ReuseDecisionError(
                        "selected candidate must provide a non-empty fingerprint"
                    )
                lookup_key = f"{selected_uuid}::{fingerprint}"
                result_uuid = candidate_results.get_dict().get(lookup_key)
                if result_uuid != selected_uuid:
                    raise ReuseDecisionError(
                        "candidate_results must map the selected candidate to its result UUID"
                    )
                result = load_node(result_uuid)
                if not isinstance(result, Dict):
                    raise ReuseDecisionError(
                        "selected candidate result must be an AiiDA Dict"
                    )
                rewritten["existing_mpnn_result"] = result
            elif action == "new_sample":
                params_data = inputs.get("mpnn_params")
                if not isinstance(params_data, Dict):
                    raise ReuseDecisionError("mpnn_params must be an AiiDA Dict")
                params = dict(params_data.get_dict())
                params["seed"] = decision.effective_seed
                rewritten["mpnn_params"] = Dict(dict=params).store()
            elif action != "rerun":
                raise ReuseDecisionError(f"unsupported reuse action: {action}")
        except ReuseDecisionError:
            raise
        except Exception as error:
            raise ReuseDecisionError(f"failed to rewrite reuse inputs: {error}") from error

        return rewritten

    def initialize_ctx(self):
        self.ctx.attempts = []
        self.ctx.model_launches = 0
        self.ctx.mpnn_success = False
        self.ctx.skip_submit = False
        self.ctx.cached_from = None
        self.ctx.mpnn_cache_source = None
        self.ctx.decision_record = None
        self.ctx.request_id = None
        self.ctx.reuse_policy = None
        self.ctx.effective_seed = self.inputs.mpnn_params.get_dict().get("seed")
        self.ctx.effective_mpnn_params = self.inputs.mpnn_params

        if not self._present_reuse_ports(self.inputs):
            return
        try:
            records = get_reuse_decision_records(self.node)
        except Exception as error:
            return self.invalid_reuse_request(
                f"cannot read kernel reuse decision record: {error}"
            )
        request_problem = self._reuse_request_problem(
            self.inputs, allow_kernel_rewrite=bool(records)
        )
        if request_problem:
            return self.invalid_reuse_request(request_problem)
        if len(records) != 1:
            return self.invalid_reuse_request(
                f"kernel reuse decision records must contain exactly one entry; got {len(records)}"
            )

        record = records[0]
        request_id = self.inputs.request_id.value
        reuse_policy = self.inputs.reuse_policy.value
        if record.get("request_id") != request_id:
            return self.invalid_reuse_request(
                "kernel decision request_id does not match the request input"
            )
        if record.get("reuse_policy") != reuse_policy:
            return self.invalid_reuse_request(
                "kernel decision reuse_policy does not match the request input"
            )
        if record.get("process_uuid") != self.node.uuid:
            return self.invalid_reuse_request(
                "kernel decision process_uuid does not match this WorkChain"
            )

        final_decision = record.get("final_decision")
        if not isinstance(final_decision, dict):
            return self.invalid_reuse_request("kernel final_decision must be a mapping")
        action = final_decision.get("action")
        if action not in REUSE_POLICY_ACTIONS[reuse_policy]:
            return self.invalid_reuse_request(
                f"kernel action {action!r} is not allowed by policy {reuse_policy!r}"
            )

        effective_seed = final_decision.get("effective_seed")
        if type(effective_seed) is not int or not 1 <= effective_seed < 2**32:
            return self.invalid_reuse_request(
                "kernel effective_seed must be an integer between 1 and 2**32 - 1"
            )
        params = self.inputs.mpnn_params.get_dict()
        if params.get("seed") != effective_seed:
            return self.invalid_reuse_request(
                "kernel effective_seed was not applied to mpnn_params"
            )

        if action == "reuse":
            selected_uuid = final_decision.get("selected_candidate_uuid")
            if not isinstance(selected_uuid, str) or not selected_uuid:
                return self.invalid_reuse_request(
                    "kernel reuse decision must select a candidate result"
                )
            if "existing_mpnn_result" not in self.inputs:
                return self.invalid_reuse_request(
                    "kernel selected reuse but no candidate result was injected"
                )
            result = self.inputs.existing_mpnn_result
            if not isinstance(result, Dict) or result.uuid != selected_uuid:
                return self.invalid_reuse_request(
                    "injected reuse result does not match the selected candidate UUID"
                )
        elif "existing_mpnn_result" in self.inputs:
            return self.invalid_reuse_request(
                "rerun and new_sample requests must not retain an existing result"
            )

        self.ctx.request_id = request_id
        self.ctx.reuse_policy = reuse_policy
        self.ctx.decision_record = record
        self.ctx.effective_seed = effective_seed
        self.ctx.effective_mpnn_params = self.inputs.mpnn_params
        self.report(
            f"kernel reuse decision completed: action={action}, "
            f"reason={record.get('reason', {}).get('reason_code')}, "
            f"effective_seed={effective_seed}"
        )

    def invalid_reuse_request(self, reason):
        self.output_failure_report("invalid_reuse_request", reason)
        return self.exit_codes.INVALID_REUSE_REQUEST.format(reason=reason)

    def maybe_skip_inference(self):
        # Keep the legacy filter-only path separate from kernel-controlled reuse.
        if self.ctx.decision_record is None:
            if "existing_mpnn_result" in self.inputs:
                self.ctx.mpnn_result = self.inputs.existing_mpnn_result
                self.ctx.skip_submit = True
            return

        final_decision = self.ctx.decision_record["final_decision"]
        if final_decision["action"] != "reuse":
            return

        selected_uuid = final_decision.get("selected_candidate_uuid")
        if "existing_mpnn_result" not in self.inputs:
            return self.reuse_result_unavailable(
                "kernel selected reuse but no candidate result was injected"
            )
        result = self.inputs.existing_mpnn_result
        if not isinstance(result, Dict) or result.uuid != selected_uuid:
            return self.reuse_result_unavailable(
                "injected reuse result does not match the selected candidate UUID"
            )
        source_process = getattr(result, "creator", None)
        if source_process is None:
            return self.reuse_result_unavailable(
                "injected reuse result has no recorded source process"
            )

        self.ctx.mpnn_result = result
        self.ctx.cached_from = source_process.uuid
        self.ctx.mpnn_cache_source = source_process.uuid
        self.ctx.skip_submit = True
        self.report(f"复用内核选中的合格候选结果 {result.uuid}，不启动 MPNN")

    def reuse_result_unavailable(self, reason):
        self.output_failure_report("reuse_result_unavailable", reason)
        return self.exit_codes.REUSE_RESULT_UNAVAILABLE.format(reason=reason)

    def should_retry(self):
        return (
            not self.ctx.skip_submit
            and not self.ctx.mpnn_success
            and len(self.ctx.attempts) < MAX_ATTEMPTS
        )

    def submit_mpnn(self):
        attempt_number = len(self.ctx.attempts) + 1
        label = attempt_label(self.uuid, attempt_number)
        attempt = {
            "attempt": attempt_number,
            "label": label,
            "model_launches_before": self.ctx.model_launches,
            "model_launches_after": self.ctx.model_launches,
            "status": "submitting",
        }
        self.ctx.attempts.append(attempt)

        entry_point = self.inputs.code.default_calc_job_plugin or DEFAULT_MPNN_CALCULATION
        builder = CalculationFactory(entry_point).get_builder()
        builder.code = self.inputs.code
        builder.pdb_file = self.inputs.pdb_file
        builder.params = self.ctx.effective_mpnn_params
        if self.ctx.decision_record is not None:
            builder.metadata.disable_cache = True
        builder.metadata.label = label
        self.report(f"提交MPNN推理，第 {attempt_number} 次尝试，label={label}")
        try:
            calculation = self.submit(builder)
        except Exception as error:
            attempt["submit_error"] = f"{type(error).__name__}: {error}"
            self.ctx.mpnn_calc = None
            try:
                matches = find_calcjobs_by_label(label)
            except Exception as query_error:
                attempt["reconciliation_error"] = f"{type(query_error).__name__}: {query_error}"
                self.ctx.submission_uncertain = True
                attempt["status"] = "submission_uncertain"
                return

            attempt["external_matches"] = [self._calcjob_identity(node) for node in matches]
            if matches:
                attempt.update(self._calcjob_identity(matches[0]))
                self.ctx.submission_uncertain = True
                self.ctx.model_launches += 1
                attempt["status"] = "submission_recovered_needs_operator"
            else:
                attempt["status"] = "submit_failed_no_external_match"
            attempt["model_launches_after"] = self.ctx.model_launches
            return

        self.ctx.model_launches += 1
        attempt["model_launches_after"] = self.ctx.model_launches
        attempt["calcjob_pk"] = calculation.pk
        attempt["calcjob_uuid"] = calculation.uuid
        attempt["status"] = "submitted"
        return ToContext(mpnn_calc=calculation)

    def on_mpnn_done(self):
        calculation = self.ctx.get("mpnn_calc")
        if calculation is None:
            if self.ctx.get("submission_uncertain"):
                reason = "提交调用异常；已按稳定 label 核对原生作业，需人工确认或恢复，未自动重复提交"
                self.output_failure_report("submission_uncertain", reason)
                return self.exit_codes.SUBMISSION_STATE_UNCERTAIN
            if len(self.ctx.attempts) >= MAX_ATTEMPTS:
                reason = self.ctx.attempts[-1].get("submit_error", "提交未产生原生作业")
                self.output_failure_report("failed_max_attempts", reason)
                return self.exit_codes.MAX_ATTEMPTS_REACHED
            return

        attempt = self.ctx.attempts[-1]
        attempt.update(self._calcjob_identity(calculation))
        attempt["cache_source"] = self._cache_source(calculation)
        # Excepted/Killed也不是成功；is_failed只覆盖Finished且非零退出。
        if not calculation.is_finished_ok:
            reason = (
                f"CalcJob未成功：state={attempt.get('process_state')}, "
                f"exit_status={attempt.get('exit_status')}"
            )
            attempt["status"] = "failed"
            attempt["reason"] = reason
            self.report(reason)
            if len(self.ctx.attempts) >= MAX_ATTEMPTS:
                self.output_failure_report("failed_max_attempts", reason)
                return self.exit_codes.MAX_ATTEMPTS_REACHED
            return

        if "result" not in calculation.outputs:
            reason = "成功的CalcJob没有发布result输出"
            attempt["status"] = "failed"
            attempt["reason"] = reason
            self.output_failure_report("missing_output", reason)
            return self.exit_codes.MISSING_MPNN_OUTPUT

        attempt["status"] = "succeeded"
        self.ctx.mpnn_result = calculation.outputs.result
        self.ctx.mpnn_success = True
        # 缓存命中时模型没有真正运行，记录来源以免把它算作一次新的模型执行。
        self.ctx.mpnn_cache_source = attempt["cache_source"]

    def validate_mpnn_result(self):
        result = self.ctx.mpnn_result.get_dict()
        if result.get("schema_version") != "ai4s-artifacts-1":
            reason = "产物schema_version不匹配ai4s-artifacts-1"
            self.output_failure_report("invalid_schema", reason)
            return self.exit_codes.INVALID_ARTIFACT_SCHEMA
        if not result.get("artifacts"):
            reason = "清单没有artifacts"
            self.output_failure_report("missing_output", reason)
            return self.exit_codes.MISSING_MPNN_OUTPUT
        manifest_problem = validation_manifest_problem(result)
        if manifest_problem:
            self.output_failure_report("invalid_manifest", manifest_problem)
            return self.exit_codes.UNQUALIFIED_UPSTREAM.format(reason=manifest_problem)
        if result.get("version") not in SUPPORTED_VERSIONS:
            reason = f"MPNN版本不在支持白名单：{result.get('version')}"
            self.output_failure_report("unsupported_version", reason)
            return self.exit_codes.VERSION_NOT_SUPPORTED
        try:
            problem = upstream_problem(
                self.ctx.mpnn_result,
                self.inputs.code,
                self.inputs.pdb_file,
                self.ctx.effective_mpnn_params,
            )
        except (AttributeError, KeyError, TypeError, ValueError, OSError) as error:
            problem = f"malformed upstream: {error}"
        if problem:
            self.output_failure_report("unqualified_upstream", problem)
            return self.exit_codes.UNQUALIFIED_UPSTREAM.format(reason=problem)

    def _calcjob_identity(self, calculation):
        return {
            "calcjob_pk": calculation.pk,
            "calcjob_uuid": calculation.uuid,
            "label": calculation.label,
            "process_state": process_state_value(calculation),
            "exit_status": calculation.exit_status,
        }

    @staticmethod
    def _cache_source(calculation):
        try:
            return calculation.base.caching.get_cache_source()
        except Exception:
            return None

    def _report_details(self):
        attempts = [dict(attempt) for attempt in self.ctx.get("attempts", [])]
        decision_record = self.ctx.get("decision_record") or {}
        final_decision = decision_record.get("final_decision", {})
        reason = decision_record.get("reason", {})
        return {
            "attempts": attempts,
            "attempt_count": len(attempts),
            "max_attempts": MAX_ATTEMPTS,
            "retry_attempt": max(0, len(attempts) - 1),
            "model_launches": self.ctx.model_launches,
            "calcjob_submissions": sum(1 for attempt in attempts if attempt.get("calcjob_uuid")),
            "request_id": self.ctx.get("request_id"),
            "reuse_policy": self.ctx.get("reuse_policy"),
            "reuse_decision": final_decision.get("action"),
            "reason_code": reason.get("reason_code"),
            "selected_candidate_uuid": final_decision.get("selected_candidate_uuid"),
            "effective_seed": self.ctx.get("effective_seed"),
            "cached_from": self.ctx.get("cached_from"),
        }

    def output_failure_report(self, status, reason):
        details = self._report_details()
        details.update({"status": status, "reason": reason})
        self.out("selection_report", record_failure_report(details))

    def run_filter(self):
        execution_report = self._report_details()
        execution_report.update({
            "status": "completed",
            "mpnn_cache_source": self.ctx.get("mpnn_cache_source"),
            "upstream_result_uuid": self.ctx.mpnn_result.uuid,
            "filter_params": self.inputs.filter_params.get_dict(),
        })
        outputs = filter_sequences(
            self.ctx.mpnn_result, self.inputs.filter_params, Dict(dict=execution_report)
        )
        self.out_many(outputs)
        self.report("两阶段workchain全部执行完成")
