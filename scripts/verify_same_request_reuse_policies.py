"""Run one real same-request verification for all three reuse policies.

The script expects an isolated AiiDA profile backed by the team's aiida-core
fork. It submits three WorkChains with one request_id:

1. force_rerun creates a real result;
2. allow_reuse reuses that result without creating a CalcJob;
3. new_sample creates a second CalcJob with a different effective seed.

The resulting native PKs, UUIDs, selection reports and decision records are
written to a JSON evidence file. This script does not create or migrate AiiDA
profiles and refuses the shared ``ai4s`` profile by default.
"""

import argparse
import getpass
import hashlib
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDB = "/opt/ai4s/proteinmpnn/releases/8907e667-py312-torch260cu124/examples/1CRN.pdb"
DEFAULT_CODE = "proteinmpnn-8907e667@localhost"
DEFAULT_REQUEST_ID = "req-" + str(uuid.uuid4())


class VerificationError(RuntimeError):
    """Report an unmet same-request acceptance condition."""


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", required=True, help="Isolated AiiDA profile name; shared ai4s is refused.")
    parser.add_argument("--request-id", default=DEFAULT_REQUEST_ID, help="One request ID shared by all three runs.")
    parser.add_argument("--code", default=DEFAULT_CODE, help="Installed ProteinMPNN code label.")
    parser.add_argument("--pdb", default=DEFAULT_PDB, help="Input PDB path.")
    parser.add_argument("--chains", default="A")
    parser.add_argument("--num-sequences", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=41, help="Original non-zero seed.")
    parser.add_argument("--score-threshold", type=float, default=0.82)
    parser.add_argument("--top-k", type=int, default=2)
    parser.add_argument("--member", default=getpass.getuser(), help="Candidate owner recorded in the compare list.")
    parser.add_argument("--timeout", type=float, default=1800, help="Per-WorkChain timeout in seconds.")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--output", type=Path, help="Evidence JSON path; defaults to a request-specific new file.")
    parser.add_argument(
        "--allow-shared-profile",
        action="store_true",
        help="Explicitly allow profile ai4s; use only when the profile owner has authorized it.",
    )
    args = parser.parse_args(argv)
    if args.output is None:
        tag = args.request_id.removeprefix("req-")[:8] or "custom"
        args.output = PROJECT_ROOT / "experiments/R005-aiida-proteinmpnn" / f"same-request-{tag}.json"
    return args


def canonical_payload(result):
    return json.dumps(result.get_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8")


def cache_source(node):
    try:
        return node.base.caching.get_cache_source()
    except Exception:  # noqa: BLE001 - cache source is diagnostic metadata only
        return None


def node_identity(node):
    return {
        "pk": node.pk,
        "uuid": node.uuid,
        "label": node.label,
        "process_state": None if node.process_state is None else node.process_state.value,
        "exit_status": node.exit_status,
        "cache_source": cache_source(node),
    }


def wait_for_workchain(node, timeout, poll_interval):
    from aiida import orm

    deadline = time.monotonic() + timeout
    while not node.is_terminated:
        if time.monotonic() >= deadline:
            raise VerificationError(
                f"WorkChain pk={node.pk} did not terminate within {timeout:g}s; inspect verdi process report {node.pk}"
            )
        time.sleep(poll_interval)
        node = orm.load_node(node.pk)
    if not node.is_finished_ok:
        raise VerificationError(
            f"WorkChain pk={node.pk} failed: process_state={node.process_state.value}, "
            f"exit_status={node.exit_status}; inspect verdi process report {node.pk}"
        )
    return node


def check(condition, message, checks, name):
    if not condition:
        raise VerificationError(message)
    checks[name] = "passed"


def run_policy(orm, workflow_class, submit, args, policy, inputs, candidates=None, candidate_results=None):
    builder = workflow_class.get_builder()
    builder.code = orm.load_code(args.code)
    builder.pdb_file = inputs["pdb_file"]
    builder.mpnn_params = inputs["mpnn_params"]
    builder.filter_params = inputs["filter_params"]
    builder.request_id = orm.Str(args.request_id)
    builder.reuse_policy = orm.Str(policy)
    if candidates is not None:
        builder.reuse_candidates = candidates
        builder.candidate_results = candidate_results
    request_tag = args.request_id.removeprefix("req-")[:8]
    builder.metadata.label = f"same-request-{request_tag}-{policy.replace('_', '-')}"
    node = submit(builder)
    print(f"submitted policy={policy} workchain_pk={node.pk} uuid={node.uuid}", flush=True)
    node = wait_for_workchain(node, args.timeout, args.poll_interval)
    print(f"finished  policy={policy} workchain_pk={node.pk}", flush=True)
    return node


def run_verification(args, state):
    from aiida import __file__ as aiida_file
    from aiida import __version__, load_profile, orm
    from aiida.engine import get_reuse_decision_records, submit

    from ai4s_workflows import find_decisions_by_request
    from ai4s_workflows.decision import validate_original_seed, validate_request_id
    from ai4s_workflows.workflows import ProteinMPNNFilterWorkChain

    profile = load_profile(args.profile)
    state["profile"] = {
        "name": profile.name,
        "aiida_version": __version__,
        "aiida_file": str(Path(aiida_file).resolve()),
    }
    check(
        profile.name != "ai4s" or args.allow_shared_profile,
        "profile ai4s is shared; pass --allow-shared-profile only with explicit authorization",
        state["checks"],
        "isolated_profile",
    )
    validate_request_id(args.request_id)
    validate_original_seed(args.seed)
    check(
        Path(args.pdb).is_file(),
        f"PDB does not exist: {args.pdb}",
        state["checks"],
        "pdb_exists",
    )

    pdb_file = orm.SinglefileData(file=args.pdb).store()
    mpnn_params = orm.Dict(dict={
        "chains": args.chains,
        "num_sequences": args.num_sequences,
        "sampling_temperature": args.temperature,
        "seed": args.seed,
        "model_name": "v_48_020",
        "batch_size": 1,
        "save_probabilities": True,
    }).store()
    filter_params = orm.Dict(dict={
        "score_threshold": args.score_threshold,
        "top_k": args.top_k,
    }).store()
    inputs = {"pdb_file": pdb_file, "mpnn_params": mpnn_params, "filter_params": filter_params}
    state["inputs"] = {
        "code": args.code,
        "pdb": str(Path(args.pdb).resolve()),
        "chains": args.chains,
        "num_sequences": args.num_sequences,
        "temperature": args.temperature,
        "original_seed": args.seed,
        "score_threshold": args.score_threshold,
        "top_k": args.top_k,
    }

    forced = run_policy(orm, ProteinMPNNFilterWorkChain, submit, args, "force_rerun", inputs)
    forced_report = forced.outputs.selection_report.get_dict()
    forced_children = sorted(
        (node for node in forced.called if isinstance(node, orm.CalcJobNode)), key=lambda node: node.pk
    )
    check(forced_report.get("reuse_decision") == "rerun", "force_rerun did not select rerun", state["checks"], "force_action")
    check(forced_report.get("reason_code") == "R03", "force_rerun reason is not R03", state["checks"], "force_reason")
    check(forced_report.get("effective_seed") == args.seed, "force_rerun changed the seed", state["checks"], "force_seed")
    check(len(forced_children) == 1, "force_rerun did not create exactly one CalcJob", state["checks"], "force_calcjob")
    check(
        forced_children[0].inputs.params.get_dict().get("seed") == args.seed,
        "force_rerun CalcJob did not receive the original seed",
        state["checks"],
        "force_calcjob_seed",
    )
    check(forced_children[0].base.caching.get_cache_source() is None, "force_rerun used native cache", state["checks"], "force_no_cache")
    state["runs"].append({
        "policy": "force_rerun",
        "workchain": node_identity(forced),
        "selection_report": forced_report,
        "calcjobs": [node_identity(node) for node in forced_children],
    })

    source_calc = forced_children[0]
    check("result" in source_calc.outputs, "force_rerun CalcJob has no result output", state["checks"], "force_result")
    source_result = source_calc.outputs.result
    check(isinstance(source_result, orm.Dict), "force_rerun result is not an AiiDA Dict", state["checks"], "force_result_type")
    payload = canonical_payload(source_result)
    fingerprint = hashlib.sha256(payload).hexdigest()[:16]
    elapsed_s = max(0, int((source_calc.mtime - source_calc.ctime).total_seconds()))
    candidate = {
        "uuid": source_result.uuid,
        "fingerprint": fingerprint,
        "member": args.member,
        "location": f"profile://{profile.name}/{source_result.uuid}/result.json",
        "size_bytes": len(payload),
        "elapsed_s": elapsed_s,
        "qualified": True,
        "reason": None,
        "note": f"source_workchain={forced.uuid}; source_calcjob={source_calc.uuid}",
    }
    candidates = orm.List(list=[candidate]).store()
    candidate_results = orm.Dict(dict={
        f"{source_result.uuid}::{fingerprint}": source_result.uuid,
    }).store()
    state["candidate"] = {
        "result_uuid": source_result.uuid,
        "source_calcjob_pk": source_calc.pk,
        "source_calcjob_uuid": source_calc.uuid,
        "fingerprint": fingerprint,
        "candidate": candidate,
    }

    reused = run_policy(
        orm, ProteinMPNNFilterWorkChain, submit, args, "allow_reuse", inputs, candidates, candidate_results
    )
    reuse_report = reused.outputs.selection_report.get_dict()
    reuse_children = [node for node in reused.called if isinstance(node, orm.CalcJobNode)]
    check(reuse_report.get("reuse_decision") == "reuse", "allow_reuse did not reuse", state["checks"], "reuse_action")
    check(reuse_report.get("reason_code") == "R01", "allow_reuse reason is not R01", state["checks"], "reuse_reason")
    check(reuse_report.get("model_launches") == 0, "allow_reuse launched a model", state["checks"], "reuse_no_launch")
    check(not reuse_children, "allow_reuse created a CalcJob", state["checks"], "reuse_no_calcjob")
    check(
        reuse_report.get("selected_candidate_uuid") == source_result.uuid,
        "allow_reuse selected a different result",
        state["checks"],
        "reuse_candidate",
    )
    check(
        reuse_report.get("cached_from") == source_calc.uuid,
        "allow_reuse source CalcJob differs from force_rerun output",
        state["checks"],
        "reuse_source",
    )
    state["runs"].append({
        "policy": "allow_reuse",
        "workchain": node_identity(reused),
        "selection_report": reuse_report,
        "calcjobs": [node_identity(node) for node in reuse_children],
    })

    sampled = run_policy(
        orm, ProteinMPNNFilterWorkChain, submit, args, "new_sample", inputs, candidates, candidate_results
    )
    sample_report = sampled.outputs.selection_report.get_dict()
    sample_children = sorted(
        (node for node in sampled.called if isinstance(node, orm.CalcJobNode)), key=lambda node: node.pk
    )
    effective_seed = sample_report.get("effective_seed")
    check(sample_report.get("reuse_decision") == "new_sample", "new_sample did not select new_sample", state["checks"], "sample_action")
    check(sample_report.get("reason_code") == "R04", "new_sample reason is not R04", state["checks"], "sample_reason")
    check(effective_seed != args.seed, "new_sample reused the original seed", state["checks"], "sample_new_seed")
    check(len(sample_children) == 1, "new_sample did not create exactly one CalcJob", state["checks"], "sample_calcjob")
    check(
        sample_children[0].inputs.params.get_dict().get("seed") == effective_seed,
        "new_sample effective seed differs from the CalcJob seed",
        state["checks"],
        "sample_calcjob_seed",
    )
    check(sample_children[0].base.caching.get_cache_source() is None, "new_sample used native cache", state["checks"], "sample_no_cache")
    state["runs"].append({
        "policy": "new_sample",
        "workchain": node_identity(sampled),
        "selection_report": sample_report,
        "calcjobs": [node_identity(node) for node in sample_children],
    })

    expected_processes = {forced.uuid, reused.uuid, sampled.uuid}
    for node in (forced, reused, sampled):
        records = get_reuse_decision_records(node)
        check(len(records) == 1, f"WorkChain pk={node.pk} does not have exactly one kernel record", state["checks"], f"kernel_record_{node.pk}")
        check(records[0]["request_id"] == args.request_id, f"WorkChain pk={node.pk} has wrong request_id", state["checks"], f"request_id_{node.pk}")
    records = find_decisions_by_request(args.request_id)
    check(len(records) == 3, f"expected 3 decision records, found {len(records)}", state["checks"], "three_records")
    check(
        {record["reuse_policy"] for record in records} == {"allow_reuse", "force_rerun", "new_sample"},
        "decision records do not cover all three policies",
        state["checks"],
        "three_policies",
    )
    check(
        {record["process_uuid"] for record in records} == expected_processes,
        "decision records do not match the three WorkChain UUIDs",
        state["checks"],
        "three_processes",
    )
    state["decision_records"] = records
    return state


def write_evidence(path, evidence):
    if path.exists():
        raise VerificationError(f"refusing to overwrite existing evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv=None):
    args = parse_args(argv)
    state = {
        "status": "running",
        "started_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request_id": args.request_id,
        "checks": {},
        "inputs": {},
        "runs": [],
        "decision_records": [],
    }
    try:
        run_verification(args, state)
        state["status"] = "passed"
    except Exception as error:  # noqa: BLE001 - failures must also be written as evidence
        state["status"] = "failed"
        state["finished_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        state["error"] = f"{type(error).__name__}: {error}"
        print(state["error"], file=sys.stderr)
        try:
            write_evidence(args.output, state)
        except VerificationError as write_error:
            print(str(write_error), file=sys.stderr)
            return 1
        return 1

    state["finished_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        write_evidence(args.output, state)
    except VerificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"evidence: {args.output.resolve()}")
    print(json.dumps({
        "request_id": args.request_id,
        "status": state["status"],
        "policies": [run["policy"] for run in state["runs"]],
        "decision_record_count": len(state["decision_records"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
