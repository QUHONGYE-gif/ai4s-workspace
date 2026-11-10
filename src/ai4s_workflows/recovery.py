"""Read-only native inspection for workflow recovery and acceptance checks."""

import argparse
import json

from aiida.orm import CalcJobNode, load_node

from .workflows import WORKCHAIN_PROCESS_TYPE, ProteinMPNNFilterWorkChain, find_calcjobs_by_label


def calcjob_identity(node):
    """Return stable identity, state, and cache information for one native CalcJob."""
    return {
        "pk": node.pk,
        "uuid": node.uuid,
        "label": node.label,
        "process_state": getattr(node.process_state, "value", str(node.process_state)),
        "exit_status": node.exit_status,
        "cache_source": node.base.caching.get_cache_source(),
    }


def reconcile_submission(label):
    """Return external CalcJobs matching a persisted attempt label without submitting."""
    return [calcjob_identity(node) for node in find_calcjobs_by_label(label)]


def workflow_report(workchain_pk):
    """Build a read-only recovery report from native WorkChain and CalcJob records."""
    workchain = load_node(workchain_pk)
    if not isinstance(workchain, ProteinMPNNFilterWorkChain) and workchain.process_type != WORKCHAIN_PROCESS_TYPE:
        raise TypeError(f"pk {workchain_pk} does not point to ProteinMPNNFilterWorkChain")

    calcjobs = [
        calcjob_identity(node)
        for node in workchain.called
        if isinstance(node, CalcJobNode)
    ]
    report = {
        "workchain": {
            "pk": workchain.pk,
            "uuid": workchain.uuid,
            "label": workchain.label,
            "process_state": getattr(workchain.process_state, "value", str(workchain.process_state)),
            "exit_status": workchain.exit_status,
        },
        "calcjobs": sorted(calcjobs, key=lambda item: item["pk"]),
        "selection_report": None,
        "upstream_result_uuid": None,
    }
    if "selection_report" in workchain.outputs:
        report["selection_report"] = workchain.outputs.selection_report.get_dict()
    if "existing_mpnn_result" in workchain.inputs:
        report["upstream_result_uuid"] = workchain.inputs.existing_mpnn_result.uuid
    return report


def main():
    parser = argparse.ArgumentParser(description="Inspect an AI4S WorkChain using native AiiDA records")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--workchain", type=int, help="WorkChain pk")
    target.add_argument("--label", help="persisted attempt label to reconcile")
    arguments = parser.parse_args()

    from aiida import load_profile

    load_profile()

    if arguments.workchain is not None:
        output = workflow_report(arguments.workchain)
    else:
        output = {"label": arguments.label, "matches": reconcile_submission(arguments.label)}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
