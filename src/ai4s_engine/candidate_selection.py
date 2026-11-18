"""Pure helpers for selecting candidates before transferring their archives.

The engine receives remote candidate metadata before it has a local AiiDA node.
Cost decisions must therefore be made on that metadata first; only the chosen
remote candidate should be materialized. Keeping this selection logic free of
AiiDA imports makes the transfer order directly testable.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping


class CandidateSelectionError(ValueError):
    """Raised when a decision cannot identify one materializable candidate."""


def candidate_key(candidate: Mapping[str, Any]) -> tuple[str, str]:
    """Return the agreement-5 identity used by candidate result maps."""
    return str(candidate.get("uuid")), str(candidate.get("fingerprint"))


def native_source_available(candidate: Mapping[str, Any]) -> bool:
    """Return whether a native AiiDA source already exists in this profile."""
    return candidate.get("native_source_available", True) is True


def prepare_remote_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Copy remote metadata and mark timing as a cross-member estimate.

    A source machine's wall-clock measurement is useful context, but it is not a
    measurement of the requester's recomputation cost. Preserve the original
    classification for audit while making ``elapsed_source`` suitable for the
    current cost comparison.
    """
    prepared = dict(candidate)
    prepared["native_source_available"] = False
    origin_source = prepared.get("elapsed_source")
    if origin_source is None:
        # Older peer responses may carry elapsed_s without its provenance.
        # Treating that value as a local measurement would understate the
        # uncertainty of a cross-member cost comparison.
        prepared["elapsed_origin_source"] = "unknown"
        prepared["elapsed_source"] = "estimated"
        detail = "跨成员历史耗时来源未标注；按估计值处理"
        existing = prepared.get("elapsed_source_detail")
        prepared["elapsed_source_detail"] = (
            f"{existing}；{detail}" if isinstance(existing, str) and existing else detail
        )
    elif origin_source == "measured":
        prepared["elapsed_origin_source"] = "measured"
        prepared["elapsed_source"] = "estimated"
        detail = "跨成员历史耗时；重算成本按当前请求的估计值处理"
        existing = prepared.get("elapsed_source_detail")
        prepared["elapsed_source_detail"] = (
            f"{existing}；{detail}" if isinstance(existing, str) and existing else detail
        )
    return prepared


def reject_identity_unresolved_candidates(
    candidates: list[dict[str, Any]], detail: str
) -> None:
    """Make every hash-matched candidate unusable when model identity is unknown.

    AiiDA's native cache can match a process hash even when the deployed model
    release cannot be identified. That hash alone is not enough evidence for a
    scientific reuse decision, so the safe outcome is an explicit rerun.
    """
    reason = f"format_error: model identity unresolved: {detail}"
    for candidate in candidates:
        if candidate.get("qualified") is True:
            candidate["qualified"] = False
            candidate["reason"] = reason


def reject_unmaterialized_candidates(
    candidates: list[dict[str, Any]],
    reason: str = "missing_file: not materialized by cost preselection",
) -> None:
    """Make every remote candidate without a native local source unusable.

    The service decides from metadata before submitting the AiiDA process. If a
    later policy read differs, the process must not be able to select a remote
    candidate that was never transferred. Marking those entries unqualified
    makes the worst case a safe recalculation instead of a reference to missing
    local data.
    """
    reason_code = reason.split(":", 1)[0].strip()
    if reason_code not in {"missing_file", "format_error"}:
        raise CandidateSelectionError("rejection reason must start with a known code")
    for candidate in candidates:
        if native_source_available(candidate):
            continue
        if candidate.get("qualified") is True:
            candidate["qualified"] = False
            candidate["reason"] = reason


def materialize_selected_candidate(
    candidates: list[dict[str, Any]],
    context: Mapping[str, Any],
    decision_function: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    materialize: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Decide on metadata and materialize at most the selected remote result.

    If transfer of the selected result fails, it becomes an unqualified
    candidate and the decision is repeated without it. This preserves the rule
    that a failed transfer is never reused while allowing the next eligible
    candidate to be considered. A successful decision that selects a candidate
    already available locally performs no transfer.
    """
    remaining = len(candidates) + 1
    while remaining > 0:
        remaining -= 1
        decision_context = dict(context)
        decision_context["candidate_compare_list"] = candidates
        outcome = dict(decision_function(decision_context))
        if outcome.get("action") != "reuse":
            return outcome

        selected_uuid = outcome.get("selected_candidate_uuid")
        if not isinstance(selected_uuid, str) or not selected_uuid:
            raise CandidateSelectionError(
                "reuse decision must provide selected_candidate_uuid"
            )
        matches = [
            candidate for candidate in candidates if candidate.get("uuid") == selected_uuid
        ]
        if len(matches) != 1:
            raise CandidateSelectionError(
                "cost preselection must uniquely identify one candidate UUID"
            )
        selected = matches[0]
        if native_source_available(selected):
            return outcome

        try:
            materialize(selected)
        except Exception as error:  # noqa: BLE001 - failure must become explicit evidence
            selected["native_source_available"] = False
            selected["qualified"] = False
            selected["reason"] = f"missing_file: archive transfer failed: {error}"
            selected["transfer_error"] = f"{type(error).__name__}: {error}"
            continue

        selected["native_source_available"] = True
        return outcome

    return {
        "action": "rerun",
        "selected_candidate_uuid": None,
        "effective_seed": context["original_seed"],
        "reason_text": "所有远程候选均因搬运失败被排除，使用原参数、原种子重算",
    }
