"""Cost-aware reuse decisions for the agreement-5 extension point.

The decision is deliberately time based.  A result is reused only when the
estimated time to read and materialize it is lower than the measured cost of
recomputing it by at least the configured safety margin.  The module has no
AiiDA dependency so its policy can be tested independently from the daemon.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .decision import (
    DecisionError,
    DecisionFunction,
    SeedFactory,
    default_reuse_decision,
    default_seed_factory,
)


COST_POLICY_ENV = "AI4S_COST_POLICY_FILE"
COST_POLICY_SCHEMA_VERSION = "ai4s-cost-policy-1"
COST_DECISION_FUNCTION = "ai4s_workflows.cost_decision:choose_by_cost"
COST_SOURCES = frozenset({"measured", "estimated", "missing"})


class CostPolicyError(DecisionError):
    """Raised when a cost policy file or a supported cost value is invalid."""


@dataclass(frozen=True)
class CostPolicy:
    """Configuration for a simple, auditable time-cost comparison.

    ``elapsed_s`` in an agreement-4 candidate is the measured source run time.
    A caller may additionally provide ``reuse_elapsed_s`` when it has measured
    the actual read/materialization time.  Otherwise the reuse time is estimated
    as fixed transfer overhead plus size/bandwidth plus materialization time.
    """

    enabled: bool = False
    transfer_fixed_seconds: float = 0.5
    transfer_bytes_per_second: float = 1024 * 1024
    materialization_seconds: float = 0.2
    min_savings_seconds: float = 1.0

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise CostPolicyError("enabled must be boolean")
        for name in (
            "transfer_fixed_seconds",
            "materialization_seconds",
            "min_savings_seconds",
        ):
            _require_non_negative_number(name, getattr(self, name))
        _require_positive_number(
            "transfer_bytes_per_second", self.transfer_bytes_per_second
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CostPolicy":
        """Build and validate a policy from a decoded JSON object."""
        if not isinstance(value, Mapping):
            raise CostPolicyError("cost policy must be a JSON object")

        allowed_fields = {
            "schema_version",
            "enabled",
            "transfer_fixed_seconds",
            "transfer_bytes_per_second",
            "materialization_seconds",
            "min_savings_seconds",
        }
        unknown = sorted(str(field) for field in set(value) - allowed_fields)
        if unknown:
            raise CostPolicyError(
                "cost policy contains unknown fields: " + ", ".join(unknown)
            )
        if value.get("schema_version") != COST_POLICY_SCHEMA_VERSION:
            raise CostPolicyError(
                "schema_version must be " + COST_POLICY_SCHEMA_VERSION
            )

        enabled = value.get("enabled", False)
        if type(enabled) is not bool:
            raise CostPolicyError("enabled must be boolean")
        return cls(
            enabled=enabled,
            transfer_fixed_seconds=value.get("transfer_fixed_seconds", 0.5),
            transfer_bytes_per_second=value.get(
                "transfer_bytes_per_second", 1024 * 1024
            ),
            materialization_seconds=value.get("materialization_seconds", 0.2),
            min_savings_seconds=value.get("min_savings_seconds", 1.0),
        )


def _is_finite_number(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _require_non_negative_number(name: str, value: Any) -> float:
    if not _is_finite_number(value) or value < 0:
        raise CostPolicyError(f"{name} must be a non-negative finite number")
    return float(value)


def _require_positive_number(name: str, value: Any) -> float:
    if not _is_finite_number(value) or value <= 0:
        raise CostPolicyError(f"{name} must be a positive finite number")
    return float(value)


def load_cost_policy(path: str | Path | None = None) -> CostPolicy:
    """Load a cost policy, or return a disabled policy when no path is given.

    When ``path`` is omitted, ``AI4S_COST_POLICY_FILE`` is used.  A missing
    environment variable means the feature is disabled and is not an error.
    An explicitly configured but unreadable or malformed file raises so a
    deployment typo cannot silently change reuse behavior.
    """
    if path is None:
        path = os.environ.get(COST_POLICY_ENV)
        if not path:
            return CostPolicy()
    elif not str(path).strip():
        raise CostPolicyError("cost policy path must not be empty")

    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise CostPolicyError(f"cannot read cost policy file {path}: {error}") from error
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise CostPolicyError(f"cost policy file {path} is not valid JSON: {error}") from error
    return CostPolicy.from_mapping(value)


def load_configured_cost_policy() -> CostPolicy | None:
    """Return an enabled policy from the deployment environment, if any."""
    path = os.environ.get(COST_POLICY_ENV)
    if not path:
        return None
    policy = load_cost_policy(path)
    return policy if policy.enabled else None


def configured_cost_decision_path() -> str | None:
    """Return the import path for the WorkChain decision port when enabled."""
    return COST_DECISION_FUNCTION if load_configured_cost_policy() is not None else None


def configured_cost_decision_function() -> DecisionFunction | None:
    """Return a cost decision callable for the single-task cache callback."""
    policy = load_configured_cost_policy()
    if policy is None:
        return None

    def choose(context: Mapping[str, Any]) -> dict[str, Any]:
        return decide_by_cost(context, policy)

    return choose


@dataclass(frozen=True)
class _CandidateCost:
    index: int
    candidate: Mapping[str, Any]
    rerun_seconds: float
    reuse_seconds: float
    rerun_source: str
    reuse_source: str

    @property
    def savings_seconds(self) -> float:
        return self.rerun_seconds - self.reuse_seconds

    @property
    def cost_source(self) -> str:
        if self.rerun_source == "measured" and self.reuse_source == "measured":
            return "measured"
        return "estimated"


def _finite_number(value: Any) -> bool:
    return _is_finite_number(value)


def _candidate_cost(
    index: int,
    candidate: Mapping[str, Any],
    policy: CostPolicy,
) -> tuple[_CandidateCost | None, str | None]:
    """Return one candidate's comparable costs, or a missing-data reason."""
    candidate_uuid = str(candidate.get("uuid", f"candidate-{index}"))
    elapsed = candidate.get("elapsed_s")
    if not _finite_number(elapsed) or elapsed <= 0:
        return None, f"{candidate_uuid}: elapsed_s 缺失或不为正"

    rerun_source = candidate.get("elapsed_source", "measured")
    if rerun_source == "missing":
        return None, f"{candidate_uuid}: elapsed_s 来源标记为 missing"
    if rerun_source not in ("measured", "estimated"):
        return None, f"{candidate_uuid}: elapsed_source 必须是 measured 或 estimated"

    if "reuse_elapsed_s" in candidate:
        reuse_seconds = candidate["reuse_elapsed_s"]
        if not _finite_number(reuse_seconds) or reuse_seconds < 0:
            return None, f"{candidate_uuid}: reuse_elapsed_s 缺失或为负数"
        reuse_source = candidate.get("reuse_elapsed_source", "measured")
        if reuse_source == "missing":
            return None, f"{candidate_uuid}: reuse_elapsed_s 来源标记为 missing"
        if reuse_source not in ("measured", "estimated"):
            return None, (
                f"{candidate_uuid}: reuse_elapsed_source 必须是 measured 或 estimated"
            )
    else:
        size_bytes = candidate.get("size_bytes")
        if type(size_bytes) is not int or size_bytes < 0:
            return None, f"{candidate_uuid}: size_bytes 缺失或不是非负整数"
        try:
            transfer_seconds = size_bytes / policy.transfer_bytes_per_second
        except OverflowError:
            return None, f"{candidate_uuid}: size_bytes 过大，无法估算搬运时间"
        reuse_seconds = (
            policy.transfer_fixed_seconds
            + transfer_seconds
            + policy.materialization_seconds
        )
        if not _finite_number(reuse_seconds):
            return None, f"{candidate_uuid}: 搬运与物化时间估算结果不是有限数"
        reuse_source = "estimated"

    return (
        _CandidateCost(
            index=index,
            candidate=candidate,
            rerun_seconds=float(elapsed),
            reuse_seconds=float(reuse_seconds),
            rerun_source=str(rerun_source),
            reuse_source=str(reuse_source),
        ),
        None,
    )


def _append_missing_source(reason_text: str, detail: str) -> str:
    return f"{reason_text}；cost_source=missing；{detail}"


def _fallback_to_default(
    context: Mapping[str, Any],
    seed_factory: SeedFactory,
    detail: str,
) -> dict[str, Any]:
    outcome = dict(default_reuse_decision(context, seed_factory=seed_factory))
    outcome["reason_text"] = _append_missing_source(outcome["reason_text"], detail)
    return outcome


def _cost_summary(cost: _CandidateCost, policy: CostPolicy) -> str:
    return (
        f"重算预计 {cost.rerun_seconds:.3f}s，复用预计 {cost.reuse_seconds:.3f}s，"
        f"预计节省 {cost.savings_seconds:.3f}s（阈值 {policy.min_savings_seconds:.3f}s）；"
        f"policy_fixed={policy.transfer_fixed_seconds:.3f}s；"
        f"policy_bandwidth={policy.transfer_bytes_per_second:.3f}B/s；"
        f"policy_materialization={policy.materialization_seconds:.3f}s；"
        f"cost_source={cost.cost_source}；rerun_source={cost.rerun_source}；"
        f"reuse_source={cost.reuse_source}"
    )


def decide_by_cost(
    context: Mapping[str, Any],
    policy: CostPolicy,
    *,
    seed_factory: SeedFactory = default_seed_factory,
) -> dict[str, Any]:
    """Choose reuse or rerun by comparing time costs.

    Only ``allow_reuse`` participates in the comparison.  ``force_rerun`` and
    ``new_sample`` are delegated unchanged to the existing decision function.
    Unqualified candidates are never considered, which excludes failed,
    interrupted, and validation-rejected results.
    """
    if not policy.enabled:
        return default_reuse_decision(context, seed_factory=seed_factory)

    reuse_policy = context["reuse_policy"]
    if reuse_policy != "allow_reuse":
        return default_reuse_decision(context, seed_factory=seed_factory)

    candidates = context["candidate_compare_list"]
    qualified = [
        (index, candidate)
        for index, candidate in enumerate(candidates)
        if candidate.get("qualified") is True
    ]
    if not qualified:
        return _fallback_to_default(
            context,
            seed_factory,
            "没有合格候选，失败、运行中断或检查不通过的结果不参与成本比较",
        )

    costs: list[_CandidateCost] = []
    missing: list[str] = []
    for index, candidate in qualified:
        cost, issue = _candidate_cost(index, candidate, policy)
        if cost is None:
            if issue is not None:
                missing.append(issue)
        else:
            costs.append(cost)

    if not costs:
        detail = "；".join(missing[:3])
        if len(missing) > 3:
            detail += f"；另有 {len(missing) - 3} 个候选缺少成本数据"
        return _fallback_to_default(context, seed_factory, detail)

    # Highest saving wins; max() keeps the first candidate on an exact tie.
    best = max(costs, key=lambda item: (item.savings_seconds, -item.index))
    missing_note = ""
    if missing:
        missing_note = f"；另有 {len(missing)} 个合格候选成本数据不完整，已跳过"

    if (
        best.savings_seconds > 0
        and best.savings_seconds >= policy.min_savings_seconds
    ):
        reason_text = (
            "成本策略选择 "
            f"{best.candidate['uuid']} 复用：{_cost_summary(best, policy)}"
            f"{missing_note}"
        )
        return {
            "action": "reuse",
            "selected_candidate_uuid": best.candidate["uuid"],
            "effective_seed": context["original_seed"],
            "reason_text": reason_text,
        }

    reason_text = (
        "成本策略比较后选择重算：最佳候选 "
        f"{best.candidate['uuid']} 的预计节省未达到阈值；"
        f"{_cost_summary(best, policy)}{missing_note}"
    )
    return {
        "action": "rerun",
        "selected_candidate_uuid": None,
        "effective_seed": context["original_seed"],
        "reason_text": reason_text,
    }


def choose_by_cost(context: Mapping[str, Any]) -> dict[str, Any]:
    """Decision-function entry point used by configuration.

    This function is only installed when the deployment policy is enabled.
    Calling it without an enabled policy is a configuration error rather than
    a silent change to the existing reason codes.
    """
    policy = load_configured_cost_policy()
    if policy is None:
        raise CostPolicyError(
            f"{COST_POLICY_ENV} must point to an enabled cost policy before "
            "choose_by_cost can be used"
        )
    return decide_by_cost(context, policy)
