"""Run the R008 cost-decision acceptance against a real AiiDA profile.

The script submits real ProteinMPNN WorkChains and CalcJobs. It never converts
an offline decision test into runtime evidence: every phase waits for native
AiiDA termination and records the resulting process tree.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from aiida import load_profile, orm
from aiida.engine import submit
from aiida.manage import get_manager
from aiida.orm import Dict, List, SinglefileData, Str, load_code, load_node
from aiida.plugins import CalculationFactory

from ai4s_query.candidates import build_candidate
from ai4s_workflows.cost_decision import COST_DECISION_FUNCTION
from ai4s_workflows.decision import find_decisions_by_process
from ai4s_workflows.workflows import ProteinMPNNFilterWorkChain


PDB_PATH = Path(
    "/opt/ai4s/proteinmpnn/releases/8907e667-py312-torch260cu124/examples/1CRN.pdb"
)
CODE_LABEL = "proteinmpnn-8907e667@localhost"
MPNN_PARAMS = {
    "chains": "A",
    "num_sequences": 4,
    "sampling_temperature": 0.1,
    "seed": 41,
    "model_name": "v_48_020",
    "batch_size": 1,
    "save_probabilities": True,
}
FILTER_PARAMS = {"score_threshold": 10.0, "top_k": 2}
LOW_COST_POLICY = {
    "schema_version": "ai4s-cost-policy-1",
    "enabled": True,
    "transfer_fixed_seconds": 0.5,
    "transfer_bytes_per_second": 1048576,
    "materialization_seconds": 0.2,
    "min_savings_seconds": 1.0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_time(value) -> str | None:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if value else None


def process_record(node) -> dict:
    return {
        "pk": node.pk,
        "uuid": node.uuid,
        "label": node.label,
        "process_type": node.process_type,
        "process_state": node.process_state.value if node.process_state else None,
        "process_status": node.process_status,
        "exit_status": node.exit_status,
        "exit_message": node.exit_message,
        "is_finished_ok": node.is_finished_ok,
        "created_at": iso_time(node.ctime),
        "ended_at": iso_time(node.mtime),
        "cache_source": node.base.caching.get_cache_source(),
    }


def calcjobs_of(workchain) -> list:
    return [
        process
        for process in workchain.called_descendants
        if isinstance(process, orm.CalcJobNode)
    ]


def decision_for(workchain) -> dict | None:
    records = find_decisions_by_process(workchain.uuid)
    if len(records) != 1:
        raise AssertionError(
            f"expected exactly one decision record for {workchain.uuid}, got {len(records)}"
        )
    return records[0]


def wait_for(node, timeout_seconds: int = 1200):
    deadline = time.monotonic() + timeout_seconds
    while not node.is_terminated:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"process {node.uuid} did not terminate in time")
        time.sleep(2)
        node = load_node(node.uuid)
    return load_node(node.uuid)


def request_id() -> str:
    return f"req-{uuid4()}"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def common_workchain_builder(code, pdb_file, params: dict, label: str):
    builder = ProteinMPNNFilterWorkChain.get_builder()
    builder.code = code
    builder.pdb_file = pdb_file
    builder.mpnn_params = Dict(dict=params)
    builder.filter_params = Dict(dict=FILTER_PARAMS)
    builder.metadata.label = label
    return builder


def submit_source(code, pdb_file, label: str):
    builder = common_workchain_builder(code, pdb_file, MPNN_PARAMS, label)
    builder.request_id = Str(request_id())
    builder.reuse_policy = Str("force_rerun")
    builder.reuse_candidates = List(list=[])
    builder.candidate_results = Dict(dict={})
    return submit(builder)


def submit_reuse(
    code,
    pdb_file,
    *,
    label: str,
    policy: str,
    candidates: list[dict],
    candidate_results: dict,
    cost_function: bool,
):
    builder = common_workchain_builder(code, pdb_file, MPNN_PARAMS, label)
    builder.request_id = Str(request_id())
    builder.reuse_policy = Str(policy)
    builder.reuse_candidates = List(list=candidates)
    builder.candidate_results = Dict(dict=candidate_results)
    if cost_function:
        builder.decision_function = Str(COST_DECISION_FUNCTION)
    return submit(builder)


def capture_workchain(workchain, decision: dict | None = None) -> dict:
    calcjobs = calcjobs_of(workchain)
    report = (
        workchain.outputs.selection_report.get_dict()
        if "selection_report" in workchain.outputs
        else None
    )
    result = {
        "process": process_record(workchain),
        "decision_record": decision,
        "selection_report": report,
        "calcjobs": [process_record(calcjob) for calcjob in calcjobs],
        "failed_calcjobs": [
            process_record(calcjob)
            for process in workchain.called_descendants
            if isinstance(process, orm.CalcJobNode) and not process.is_finished_ok
            for calcjob in [process]
        ],
    }
    if "selected_sequences" in workchain.outputs:
        result["selected_sequences_uuid"] = workchain.outputs.selected_sequences.uuid
    if "sample_table" in workchain.outputs:
        result["sample_table_uuid"] = workchain.outputs.sample_table.uuid
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def restore_finished_phase(previous: dict, name: str):
    """Reload a completed phase and rebuild its evidence from native AiiDA state."""
    phase = previous.get("phases", {}).get(name)
    if not phase or not phase.get("process"):
        return None
    workchain = load_node(phase["process"]["uuid"])
    require(workchain.is_finished_ok, f"resumed {name} WorkChain is not successful")
    decision = decision_for(workchain)
    restored = capture_workchain(workchain, decision)
    require(
        restored["process"]["uuid"] == phase["process"]["uuid"],
        f"resumed {name} WorkChain UUID changed",
    )
    return workchain, decision, restored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy-file", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument(
        "--resume-from",
        type=Path,
        help="Resume completed phases from an earlier interrupted evidence file",
    )
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.policy_file = args.policy_file.resolve()
    if args.resume_from:
        args.resume_from = args.resume_from.resolve()
    if args.output.exists():
        raise FileExistsError(args.output)

    load_profile()
    profile = get_manager().get_profile().name
    code = load_code(CODE_LABEL)
    require(PDB_PATH.is_file(), f"missing PDB: {PDB_PATH}")

    evidence = {
        "schema_version": "ai4s-r008-cost-decision-acceptance-1",
        "status": "running",
        "started_at": utc_now(),
        "profile": profile,
        "code": {
            "label": code.label,
            "uuid": code.uuid,
            "pk": code.pk,
            "plugin": code.default_calc_job_plugin,
        },
        "inputs": {
            "pdb_path": str(PDB_PATH),
            "pdb_sha256": __import__("hashlib").sha256(PDB_PATH.read_bytes()).hexdigest(),
            "mpnn_params": MPNN_PARAMS,
            "filter_params": FILTER_PARAMS,
        },
        "policy_file": str(args.policy_file),
        "phases": {},
        "checks": {},
    }

    def save() -> None:
        evidence["updated_at"] = utc_now()
        write_json(args.output, evidence)

    save()

    previous = (
        json.loads(args.resume_from.read_text(encoding="utf-8"))
        if args.resume_from
        else None
    )
    if previous:
        source = previous["phases"]["source"]
        source_calc = load_node(source["calcjob"]["uuid"])
        source_workchain = load_node(source["process"]["uuid"])
        require(source_workchain.is_finished_ok, "resumed source WorkChain is not successful")
        require(source_calc.is_finished_ok, "resumed source CalcJob is not successful")
        require(
            source_calc.base.caching.get_cache_source() is None,
            "resumed source CalcJob came from the AiiDA cache",
        )
        request = {
            "num_sequences": MPNN_PARAMS["num_sequences"],
            "score_threshold": FILTER_PARAMS["score_threshold"],
        }
        candidate = build_candidate(source_calc, profile, request)
        previous_candidate = previous["source_candidate"]
        for field in (
            "uuid",
            "fingerprint",
            "qualified",
            "cached",
            "elapsed_s",
            "size_bytes",
        ):
            require(
                candidate[field] == previous_candidate[field],
                f"resumed source candidate field {field} changed",
            )
        source_phase = capture_workchain(source_workchain)
        source_phase["calcjob"] = process_record(source_calc)
        evidence["resumed_from"] = str(args.resume_from)
        evidence["phases"]["source"] = source_phase
        evidence["source_candidate"] = candidate
        save()
    else:
        source_workchain = wait_for(
            submit_source(code, SinglefileData(file=PDB_PATH), f"r008-source-{uuid4()}"),
            args.timeout,
        )
        require(source_workchain.is_finished_ok, "source WorkChain did not finish successfully")
        source_calcs = calcjobs_of(source_workchain)
        require(len(source_calcs) == 1, f"source must launch one CalcJob, got {len(source_calcs)}")
        source_calc = source_calcs[0]
        require(source_calc.is_finished_ok, "source CalcJob did not finish successfully")
        require(
            source_calc.base.caching.get_cache_source() is None,
            "source CalcJob unexpectedly came from the AiiDA cache",
        )
        request = {
            "num_sequences": MPNN_PARAMS["num_sequences"],
            "score_threshold": FILTER_PARAMS["score_threshold"],
        }
        candidate = build_candidate(source_calc, profile, request)
        require(candidate["qualified"] is True, f"source candidate unqualified: {candidate['reason']}")
        require(candidate["cached"] is False, "source candidate is marked as cached")
        require(candidate["elapsed_s"] > 0, "source candidate has no measured elapsed_s")
        require(candidate["size_bytes"] > 0, "source candidate has no materialized bytes")
        require(candidate["uuid"] == source_calc.outputs.result.uuid, "candidate UUID is not the result UUID")
        source_phase = capture_workchain(source_workchain)
        source_phase["calcjob"] = process_record(source_calc)
        evidence["phases"]["source"] = source_phase
        evidence["source_candidate"] = candidate
        save()

    fingerprint = candidate["fingerprint"]
    result_uuid = candidate["uuid"]
    candidate_results = {f"{result_uuid}::{fingerprint}": result_uuid}
    pdb_file = SinglefileData(file=PDB_PATH)

    restored_default = (
        restore_finished_phase(previous, "default_reuse") if previous else None
    )
    if restored_default:
        default_workchain, default_decision, default_phase = restored_default
    else:
        default_workchain = wait_for(
            submit_reuse(
                code,
                pdb_file,
                label=f"r008-default-reuse-{uuid4()}",
                policy="allow_reuse",
                candidates=[candidate],
                candidate_results=candidate_results,
                cost_function=False,
            ),
            args.timeout,
        )
        require(default_workchain.is_finished_ok, "default reuse WorkChain failed")
        default_decision = decision_for(default_workchain)
        default_phase = capture_workchain(default_workchain, default_decision)
    evidence["phases"]["default_reuse"] = default_phase
    save()

    low_policy = (
        previous["phases"].get("low_cost_policy", LOW_COST_POLICY)
        if previous
        else dict(LOW_COST_POLICY)
    )
    args.policy_file.write_text(
        json.dumps(low_policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    evidence["phases"]["low_cost_policy"] = low_policy
    save()

    restored_low = (
        restore_finished_phase(previous, "cost_reuse") if previous else None
    )
    if restored_low:
        low_workchain, low_decision, low_phase = restored_low
    else:
        low_workchain = wait_for(
            submit_reuse(
                code,
                pdb_file,
                label=f"r008-cost-reuse-{uuid4()}",
                policy="allow_reuse",
                candidates=[candidate],
                candidate_results=candidate_results,
                cost_function=True,
            ),
            args.timeout,
        )
        require(low_workchain.is_finished_ok, "low-cost reuse WorkChain failed")
        low_decision = decision_for(low_workchain)
        low_phase = capture_workchain(low_workchain, low_decision)
    evidence["phases"]["cost_reuse"] = low_phase
    save()

    if previous and "high_cost_policy" in previous["phases"]:
        high_policy = previous["phases"]["high_cost_policy"]
    else:
        high_fixed = max(40.0, math.ceil(float(candidate["elapsed_s"]) + 10.0))
        high_policy = {
            "schema_version": "ai4s-cost-policy-1",
            "enabled": True,
            "transfer_fixed_seconds": high_fixed,
            "transfer_bytes_per_second": 1048576,
            "materialization_seconds": 0.0,
            "min_savings_seconds": 1.0,
        }
    args.policy_file.write_text(
        json.dumps(high_policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    evidence["phases"]["high_cost_policy"] = high_policy
    save()

    restored_high = (
        restore_finished_phase(previous, "cost_rerun") if previous else None
    )
    if restored_high:
        high_workchain, high_decision, high_phase = restored_high
    else:
        high_workchain = wait_for(
            submit_reuse(
                code,
                pdb_file,
                label=f"r008-cost-rerun-{uuid4()}",
                policy="allow_reuse",
                candidates=[candidate],
                candidate_results=candidate_results,
                cost_function=True,
            ),
            args.timeout,
        )
        require(high_workchain.is_finished_ok, "high-cost rerun WorkChain failed")
        high_decision = decision_for(high_workchain)
        high_phase = capture_workchain(high_workchain, high_decision)
    evidence["phases"]["cost_rerun"] = high_phase
    save()

    restored_sample = (
        restore_finished_phase(previous, "new_sample") if previous else None
    )
    if restored_sample:
        sample_workchain, sample_decision, sample_phase = restored_sample
    else:
        sample_workchain = wait_for(
            submit_reuse(
                code,
                pdb_file,
                label=f"r008-new-sample-{uuid4()}",
                policy="new_sample",
                candidates=[candidate],
                candidate_results=candidate_results,
                cost_function=False,
            ),
            args.timeout,
        )
        require(sample_workchain.is_finished_ok, "new-sample WorkChain failed")
        sample_decision = decision_for(sample_workchain)
        sample_phase = capture_workchain(sample_workchain, sample_decision)
    evidence["phases"]["new_sample"] = sample_phase
    save()

    invalid_pdb_path = args.output.parent / "invalid-input.pdb"
    invalid_pdb_path.write_text("This is not a PDB file.\n", encoding="ascii")
    invalid_builder = CalculationFactory("ai4s.proteinmpnn").get_builder()
    invalid_builder.code = code
    invalid_builder.pdb_file = SinglefileData(file=invalid_pdb_path)
    invalid_builder.params = Dict(dict=MPNN_PARAMS)
    invalid_builder.metadata.label = f"r008-invalid-mpnn-{uuid4()}"
    invalid_calc = wait_for(submit(invalid_builder), args.timeout)
    require(not invalid_calc.is_finished_ok, "invalid PDB unexpectedly succeeded")
    failed_candidate = build_candidate(invalid_calc, profile, {
        "num_sequences": MPNN_PARAMS["num_sequences"],
        "score_threshold": FILTER_PARAMS["score_threshold"],
    })
    require(failed_candidate["qualified"] is False, "failed candidate was unexpectedly qualified")
    require(
        failed_candidate["reason"].startswith("not_finished:"),
        f"failed candidate reason is not not_finished: {failed_candidate['reason']}",
    )
    evidence["failed_candidate"] = failed_candidate
    evidence["phases"]["failed_candidate"] = {
        "calcjob": process_record(invalid_calc),
        "candidate_reason": failed_candidate["reason"],
    }
    save()

    excluded_workchain = wait_for(
        submit_reuse(
            code,
            pdb_file,
            label=f"r008-excluded-failed-{uuid4()}",
            policy="allow_reuse",
            candidates=[failed_candidate],
            candidate_results={},
            cost_function=True,
        ),
        args.timeout,
    )
    require(excluded_workchain.is_finished_ok, "failed-candidate exclusion WorkChain failed")
    excluded_decision = decision_for(excluded_workchain)
    excluded_phase = capture_workchain(excluded_workchain, excluded_decision)
    evidence["phases"]["failed_candidate_exclusion"] = excluded_phase
    save()

    checks = {
        "source_is_real_measured": candidate["elapsed_s"] > 0 and candidate["size_bytes"] > 0,
        "default_reuse_R01_no_calc": (
            default_decision["reason"]["reason_code"] == "R01"
            and default_decision["final_decision"]["action"] == "reuse"
            and not default_phase["calcjobs"]
            and default_phase["selection_report"]["model_launches"] == 0
        ),
        "cost_reuse_R05_no_calc": (
            low_decision["reason"]["reason_code"] == "R05"
            and low_decision["final_decision"]["action"] == "reuse"
            and low_decision["final_decision"]["selected_candidate_uuid"] == result_uuid
            and not low_phase["calcjobs"]
            and low_phase["selection_report"]["model_launches"] == 0
            and "cost_source=estimated" in low_decision["reason"]["reason_text"]
        ),
        "cost_rerun_R05_one_calc": (
            high_decision["reason"]["reason_code"] == "R05"
            and high_decision["final_decision"]["action"] == "rerun"
            and high_decision["final_decision"]["selected_candidate_uuid"] is None
            and len(high_phase["calcjobs"]) == 1
            and high_phase["selection_report"]["model_launches"] == 1
            and high_phase["calcjobs"][0]["cache_source"] is None
            and "节省未达到阈值" in high_decision["reason"]["reason_text"]
        ),
        "new_sample_R04_new_seed_one_calc": (
            sample_decision["reason"]["reason_code"] == "R04"
            and sample_decision["final_decision"]["action"] == "new_sample"
            and sample_decision["final_decision"]["effective_seed"] != MPNN_PARAMS["seed"]
            and len(sample_phase["calcjobs"]) == 1
            and sample_phase["selection_report"]["model_launches"] == 1
            and sample_phase["selection_report"]["effective_seed"]
                == sample_decision["final_decision"]["effective_seed"]
        ),
        "failed_candidate_excluded_and_safe_rerun": (
            excluded_decision["reason"]["reason_code"] == "R05"
            and excluded_decision["final_decision"]["action"] == "rerun"
            and excluded_decision["final_decision"]["selected_candidate_uuid"] is None
            and any(
                entry["uuid"] == failed_candidate["uuid"]
                and entry["qualified"] is False
                for entry in excluded_decision["candidate_compare_list"]
            )
            and len(excluded_phase["calcjobs"]) == 1
            and excluded_phase["selection_report"]["model_launches"] == 1
        ),
    }
    evidence["checks"] = checks
    evidence["status"] = "passed" if all(checks.values()) else "failed"
    evidence["finished_at"] = utc_now()
    save()
    if evidence["status"] != "passed":
        raise AssertionError(f"acceptance checks failed: {checks}")


if __name__ == "__main__":
    main()
