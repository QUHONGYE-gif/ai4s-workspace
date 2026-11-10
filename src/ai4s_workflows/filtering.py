"""Calculation functions that create the workflow's final data nodes."""

from aiida.engine import calcfunction
from aiida.orm import Dict


@calcfunction
def filter_sequences(mpnn_result, filter_params, execution_report):
    """Record filtering inputs and create outputs with a calculation creator."""
    parameters = filter_params.get_dict()
    threshold = parameters["score_threshold"]
    top_k = parameters["top_k"]
    samples = next(
        artifact["samples"] for artifact in mpnn_result.get_dict()["artifacts"]
        if artifact["port"] == "artifacts.sequences"
    )
    accepted = [sample for sample in samples if sample["score"] <= threshold]
    accepted.sort(key=lambda sample: (sample["score"], sample["sample_id"]))
    selected = accepted[:top_k]

    report = execution_report.get_dict()
    report["selected_count"] = len(selected)
    return {
        "selected_sequences": Dict(dict={"entries": selected}),
        "sample_table": Dict(dict={
            "rows": selected, "score_threshold": threshold, "top_k": top_k
        }),
        "selection_report": Dict(dict=report),
    }


@calcfunction
def record_failure_report(details):
    """Persist a terminal failure report through a calculation process."""
    return Dict(dict=details.get_dict())
