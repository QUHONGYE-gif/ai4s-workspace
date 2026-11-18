"""Independent tests for the cost-aware reuse decision.

Run without pytest from the repository root:

    $env:PYTHONPATH = "src"
    python tests/test_cost_decision.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# These modules are deliberately AiiDA-free. Loading them through a package
# stub keeps the direct unittest run independent of the optional AiiDA runtime.
WORKFLOWS_PACKAGE = types.ModuleType("ai4s_workflows")
WORKFLOWS_PACKAGE.__path__ = [str(ROOT / "src" / "ai4s_workflows")]
sys.modules.setdefault("ai4s_workflows", WORKFLOWS_PACKAGE)

from ai4s_engine.candidate_selection import (  # noqa: E402
    materialize_selected_candidate,
    prepare_remote_candidate,
    reject_identity_unresolved_candidates,
    reject_unmaterialized_candidates,
)
from ai4s_workflows.cost_decision import (  # noqa: E402
    COST_POLICY_ENV,
    COST_POLICY_SCHEMA_VERSION,
    CostPolicy,
    CostPolicyError,
    choose_by_cost,
    configured_cost_decision_function,
    configured_cost_decision_path,
    decide_by_cost,
    load_configured_cost_policy,
    load_cost_policy,
)
from ai4s_workflows.decision import make_decision_record  # noqa: E402


REQUEST_ID = "req-6f1c2a9e-3b7d-4c51-9a0e-1d2f3c4b5a6e"
PROCESS_UUID = "2f49ef2c-7e42-4f88-8d54-3320e4cf1f1a"
CANDIDATE_A = "f9633fef-132c-47d0-b81d-8f3644763518"
CANDIDATE_B = "6d078da7-3963-4e53-acec-1fb51dc84531"


def candidate(
    uuid: str = CANDIDATE_A,
    *,
    size_bytes: int = 2022,
    elapsed_s: float = 31,
    qualified: bool = True,
    reason: str | None = None,
    **extra,
) -> dict:
    value = {
        "uuid": uuid,
        "fingerprint": "fe5efe41b0d1fd42",
        "member": "测试成员",
        "location": f"profile://test/{uuid}/result.json",
        "size_bytes": size_bytes,
        "elapsed_s": elapsed_s,
        "qualified": qualified,
        "reason": reason,
        "note": "R005 fixture",
    }
    value.update(extra)
    return value


def context(policy: str = "allow_reuse", candidates: list[dict] | None = None) -> dict:
    return {
        "request_id": REQUEST_ID,
        "process_uuid": PROCESS_UUID,
        "reuse_policy": policy,
        "candidate_compare_list": candidates if candidates is not None else [candidate()],
        "original_seed": 41,
    }


def enabled_policy(**overrides) -> CostPolicy:
    values = {
        "enabled": True,
        "transfer_fixed_seconds": 0.5,
        "transfer_bytes_per_second": 1024 * 1024,
        "materialization_seconds": 0.2,
        "min_savings_seconds": 1.0,
    }
    values.update(overrides)
    return CostPolicy(**values)


class CostDecisionTests(unittest.TestCase):
    def test_r005_record_reuses_when_reuse_is_cheaper(self):
        fixture_path = (
            ROOT
            / "experiments"
            / "R005-aiida-proteinmpnn"
            / "same-request-f433676d.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        r005_candidate = fixture["candidate"]["candidate"]
        result = decide_by_cost(
            {
                "request_id": fixture["request_id"],
                "process_uuid": PROCESS_UUID,
                "reuse_policy": "allow_reuse",
                "candidate_compare_list": [r005_candidate],
                "original_seed": 41,
            },
            enabled_policy(),
        )

        self.assertEqual(result["action"], "reuse")
        self.assertEqual(
            result["selected_candidate_uuid"],
            "0e78b564-4df5-46c3-9db9-7ee966728801",
        )
        self.assertEqual(result["effective_seed"], 41)
        self.assertIn("cost_source=estimated", result["reason_text"])
        self.assertIn("rerun_source=measured", result["reason_text"])
        self.assertIn("reuse_source=estimated", result["reason_text"])
        self.assertIn("预计节省 30.298s", result["reason_text"])

    def test_transfer_cost_can_make_recalculation_preferable(self):
        result = decide_by_cost(
            context(),
            enabled_policy(transfer_fixed_seconds=40, materialization_seconds=0),
        )

        self.assertEqual(result["action"], "rerun")
        self.assertIsNone(result["selected_candidate_uuid"])
        self.assertIn("预计节省未达到阈值", result["reason_text"])

    def test_reason_records_the_policy_values_used_for_the_decision(self):
        result = decide_by_cost(
            context(),
            enabled_policy(
                transfer_fixed_seconds=2.5,
                transfer_bytes_per_second=128,
                materialization_seconds=0.75,
            ),
        )

        self.assertIn("policy_fixed=2.500s", result["reason_text"])
        self.assertIn("policy_bandwidth=128.000B/s", result["reason_text"])
        self.assertIn("policy_materialization=0.750s", result["reason_text"])

    def test_minimum_savings_threshold_changes_the_decision(self):
        cheap = decide_by_cost(context(), enabled_policy(min_savings_seconds=1))
        strict = decide_by_cost(context(), enabled_policy(min_savings_seconds=40))

        self.assertEqual(cheap["action"], "reuse")
        self.assertEqual(strict["action"], "rerun")

    def test_multiple_candidates_choose_the_largest_estimated_saving(self):
        first = candidate()
        second = candidate(CANDIDATE_B, size_bytes=1, elapsed_s=100)
        result = decide_by_cost(
            context(candidates=[first, second]),
            enabled_policy(),
        )

        self.assertEqual(result["selected_candidate_uuid"], CANDIDATE_B)

    def test_equal_savings_keep_the_original_candidate_order(self):
        first = candidate()
        second = candidate(CANDIDATE_B)
        result = decide_by_cost(
            context(candidates=[first, second]),
            enabled_policy(),
        )

        self.assertEqual(result["selected_candidate_uuid"], CANDIDATE_A)

    def test_partial_missing_costs_skip_only_incomplete_candidates(self):
        incomplete = candidate(CANDIDATE_A, elapsed_s=0)
        complete = candidate(CANDIDATE_B, elapsed_s=100)
        result = decide_by_cost(
            context(candidates=[incomplete, complete]),
            enabled_policy(),
        )

        self.assertEqual(result["action"], "reuse")
        self.assertEqual(result["selected_candidate_uuid"], CANDIDATE_B)
        self.assertIn("另有 1 个合格候选成本数据不完整，已跳过", result["reason_text"])

    def test_unqualified_results_are_never_reused(self):
        bad = candidate(
            qualified=False,
            reason="not_finished: process was killed",
        )
        result = decide_by_cost(context(candidates=[bad]), enabled_policy())

        self.assertEqual(result["action"], "rerun")
        self.assertIsNone(result["selected_candidate_uuid"])
        self.assertIn("cost_source=missing", result["reason_text"])

    def test_all_unqualified_failure_reasons_are_excluded(self):
        failure_reasons = (
            "not_finished: process failed",
            "format_error: schema mismatch",
            "below_threshold: score rejected",
            "manual_reject: reviewer vetoed",
        )
        for reason in failure_reasons:
            with self.subTest(reason=reason):
                result = decide_by_cost(
                    context(candidates=[candidate(qualified=False, reason=reason)]),
                    enabled_policy(),
                )
                self.assertEqual(result["action"], "rerun")
                self.assertIsNone(result["selected_candidate_uuid"])
                self.assertIn("cost_source=missing", result["reason_text"])

    def test_disabled_cost_policy_preserves_the_original_decision(self):
        result = decide_by_cost(
            context(),
            enabled_policy(enabled=False),
        )

        self.assertEqual(result["action"], "reuse")
        self.assertNotIn("cost_source=", result["reason_text"])

    def test_unrepresentable_size_falls_back_instead_of_crashing(self):
        result = decide_by_cost(
            context(candidates=[candidate(size_bytes=10**1000)]),
            enabled_policy(),
        )

        self.assertEqual(result["action"], "reuse")
        self.assertEqual(result["selected_candidate_uuid"], CANDIDATE_A)
        self.assertIn("size_bytes 过大", result["reason_text"])
        self.assertIn("cost_source=missing", result["reason_text"])

    def test_missing_cost_data_falls_back_to_the_original_rule_and_is_marked(self):
        no_elapsed = candidate(elapsed_s=0)
        result = decide_by_cost(context(candidates=[no_elapsed]), enabled_policy())

        self.assertEqual(result["action"], "reuse")
        self.assertEqual(result["selected_candidate_uuid"], CANDIDATE_A)
        self.assertIn("cost_source=missing", result["reason_text"])

    def test_explicit_missing_elapsed_source_falls_back(self):
        marked_missing = candidate(elapsed_source="missing")
        result = decide_by_cost(
            context(candidates=[marked_missing]),
            enabled_policy(),
        )

        self.assertEqual(result["action"], "reuse")
        self.assertIn("elapsed_s 来源标记为 missing", result["reason_text"])
        self.assertIn("cost_source=missing", result["reason_text"])

    def test_estimated_rerun_time_is_preserved_in_the_reason(self):
        estimated = candidate(elapsed_source="estimated")
        result = decide_by_cost(context(candidates=[estimated]), enabled_policy())

        self.assertEqual(result["action"], "reuse")
        self.assertIn("cost_source=estimated", result["reason_text"])
        self.assertIn("rerun_source=estimated", result["reason_text"])

    def test_measured_reuse_time_produces_a_measured_cost_source(self):
        measured = candidate(reuse_elapsed_s=5)
        result = decide_by_cost(context(candidates=[measured]), enabled_policy())

        self.assertEqual(result["action"], "reuse")
        self.assertIn("cost_source=measured", result["reason_text"])
        self.assertIn("reuse_source=measured", result["reason_text"])

    def test_user_selected_force_rerun_and_new_sample_are_not_cost_controlled(self):
        forced = decide_by_cost(
            context("force_rerun"),
            enabled_policy(transfer_fixed_seconds=1000),
        )
        self.assertEqual(forced["action"], "rerun")
        self.assertEqual(forced["effective_seed"], 41)

        sampled = decide_by_cost(
            context("new_sample"),
            enabled_policy(transfer_fixed_seconds=1000),
            seed_factory=lambda original: original + 1,
        )
        self.assertEqual(sampled["action"], "new_sample")
        self.assertEqual(sampled["effective_seed"], 42)

    def test_cost_preselection_materializes_only_the_selected_remote_candidate(self):
        first = candidate(
            CANDIDATE_A, elapsed_s=10, native_source_available=False
        )
        second = candidate(
            CANDIDATE_B, size_bytes=1, elapsed_s=100, native_source_available=False
        )
        transfers = []

        result = materialize_selected_candidate(
            [first, second],
            context(candidates=[first, second]),
            lambda value: decide_by_cost(value, enabled_policy()),
            lambda selected: transfers.append(selected["uuid"]),
        )

        self.assertEqual(result["action"], "reuse")
        self.assertEqual(result["selected_candidate_uuid"], CANDIDATE_B)
        self.assertEqual(transfers, [CANDIDATE_B])
        self.assertTrue(second["native_source_available"])
        self.assertFalse(first["native_source_available"])

    def test_cost_preselection_does_not_transfer_when_rerun_is_cheaper(self):
        remote = candidate(native_source_available=False)
        transfers = []

        result = materialize_selected_candidate(
            [remote],
            context(candidates=[remote]),
            lambda value: decide_by_cost(
                value,
                enabled_policy(transfer_fixed_seconds=1000),
            ),
            lambda selected: transfers.append(selected["uuid"]),
        )

        self.assertEqual(result["action"], "rerun")
        self.assertEqual(transfers, [])

    def test_failed_transfer_is_rejected_and_decision_tries_the_next_candidate(self):
        first = candidate(
            CANDIDATE_A, size_bytes=1, elapsed_s=100, native_source_available=False
        )
        second = candidate(
            CANDIDATE_B, size_bytes=1, elapsed_s=200, native_source_available=False
        )
        transfers = []

        def transfer(selected):
            transfers.append(selected["uuid"])
            if selected["uuid"] == CANDIDATE_B:
                raise OSError("peer unavailable")

        result = materialize_selected_candidate(
            [first, second],
            context(candidates=[first, second]),
            lambda value: decide_by_cost(value, enabled_policy()),
            transfer,
        )

        self.assertEqual(result["action"], "reuse")
        self.assertEqual(result["selected_candidate_uuid"], CANDIDATE_A)
        self.assertEqual(transfers, [CANDIDATE_B, CANDIDATE_A])
        self.assertFalse(second["qualified"])
        self.assertTrue(second["reason"].startswith("missing_file:"))
        self.assertTrue(first["native_source_available"])

    def test_all_remote_transfers_failing_forces_rerun(self):
        first = candidate(
            CANDIDATE_A, size_bytes=1, elapsed_s=100, native_source_available=False
        )
        second = candidate(
            CANDIDATE_B, size_bytes=1, elapsed_s=200, native_source_available=False
        )

        def transfer(selected):
            raise OSError(f"peer unavailable for {selected['uuid']}")

        result = materialize_selected_candidate(
            [first, second],
            context(candidates=[first, second]),
            lambda value: decide_by_cost(value, enabled_policy()),
            transfer,
        )

        self.assertEqual(result["action"], "rerun")
        self.assertIsNone(result["selected_candidate_uuid"])
        self.assertEqual(result["effective_seed"], 41)
        self.assertIn("cost_source=missing", result["reason_text"])
        self.assertFalse(first["qualified"])
        self.assertFalse(second["qualified"])

    def test_materialization_loop_exhaustion_returns_rerun_not_none(self):
        remote = candidate(native_source_available=False)
        transfers = []

        def always_select(value):
            return {
                "action": "reuse",
                "selected_candidate_uuid": CANDIDATE_A,
                "effective_seed": value["original_seed"],
                "reason_text": "test decision always selects the candidate",
            }

        def transfer(selected):
            transfers.append(selected["uuid"])
            raise OSError("peer unavailable")

        result = materialize_selected_candidate(
            [remote],
            context(candidates=[remote]),
            always_select,
            transfer,
        )

        self.assertEqual(result["action"], "rerun")
        self.assertIsNone(result["selected_candidate_uuid"])
        self.assertEqual(result["effective_seed"], 41)
        self.assertIn("所有远程候选均因搬运失败被排除", result["reason_text"])
        self.assertFalse(remote["qualified"])
        self.assertTrue(transfers)

    def test_native_candidate_is_selected_without_a_transfer(self):
        local = candidate(native_source_available=True)
        transfers = []

        result = materialize_selected_candidate(
            [local],
            context(candidates=[local]),
            lambda value: decide_by_cost(value, enabled_policy()),
            lambda selected: transfers.append(selected["uuid"]),
        )

        self.assertEqual(result["action"], "reuse")
        self.assertEqual(result["selected_candidate_uuid"], CANDIDATE_A)
        self.assertEqual(transfers, [])

    def test_remote_measured_time_becomes_an_estimate_and_keeps_origin(self):
        remote = prepare_remote_candidate(candidate(elapsed_source="measured"))

        self.assertFalse(remote["native_source_available"])
        self.assertEqual(remote["elapsed_source"], "estimated")
        self.assertEqual(remote["elapsed_origin_source"], "measured")
        self.assertIn("跨成员历史耗时", remote["elapsed_source_detail"])

    def test_remote_unmarked_time_is_not_treated_as_a_measurement(self):
        remote = candidate()
        remote.pop("elapsed_source", None)

        prepared = prepare_remote_candidate(remote)

        self.assertEqual(prepared["elapsed_source"], "estimated")
        self.assertEqual(prepared["elapsed_origin_source"], "unknown")
        self.assertIn("来源未标注", prepared["elapsed_source_detail"])

    def test_unresolved_identity_forces_every_qualified_candidate_to_rerun(self):
        local = candidate(native_source_available=True)
        remote = candidate(
            CANDIDATE_B,
            native_source_available=False,
            qualified=False,
            reason="not_finished: process failed",
        )

        reject_identity_unresolved_candidates([local, remote], "missing release")

        self.assertFalse(local["qualified"])
        self.assertTrue(local["reason"].startswith("format_error:"))
        self.assertEqual(remote["reason"], "not_finished: process failed")

    def test_unmaterialized_remote_candidate_is_rejected_without_touching_local(self):
        local = candidate(CANDIDATE_A, native_source_available=True)
        remote = candidate(CANDIDATE_B, native_source_available=False)

        reject_unmaterialized_candidates([local, remote])

        self.assertTrue(local["qualified"])
        self.assertFalse(remote["qualified"])
        self.assertTrue(remote["reason"].startswith("missing_file:"))

    def test_cost_function_is_r05_in_the_existing_decision_record(self):
        record = make_decision_record(
            request_id=REQUEST_ID,
            process_uuid=PROCESS_UUID,
            reuse_policy="allow_reuse",
            candidates=[candidate()],
            original_seed=41,
            decision_function=lambda value: decide_by_cost(value, enabled_policy()),
            timestamp="2026-11-18T00:00:00Z",
        )

        self.assertEqual(record["reason"]["reason_code"], "R05")
        self.assertEqual(record["final_decision"]["action"], "reuse")
        self.assertIn("cost_source=", record["reason"]["reason_text"])

    def test_policy_configuration_is_validated(self):
        valid = {
            "schema_version": COST_POLICY_SCHEMA_VERSION,
            "enabled": True,
            "transfer_fixed_seconds": 1,
            "transfer_bytes_per_second": 1024,
            "materialization_seconds": 0,
            "min_savings_seconds": 0,
        }
        policy = CostPolicy.from_mapping(valid)
        self.assertTrue(policy.enabled)

        for field, value in (
            ("unknown", True),
            ("transfer_fixed_seconds", -1),
            ("transfer_fixed_seconds", 10**1000),
            ("transfer_bytes_per_second", 0),
            ("min_savings_seconds", float("inf")),
        ):
            invalid = dict(valid)
            invalid[field] = value
            with self.assertRaises(CostPolicyError):
                CostPolicy.from_mapping(invalid)

    def test_configured_cost_feature_is_disabled_without_environment(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI4S_COST_POLICY_FILE", None)
            self.assertIsNone(load_configured_cost_policy())
            self.assertIsNone(configured_cost_decision_function())
            self.assertIsNone(configured_cost_decision_path())

    def test_choose_by_cost_requires_an_enabled_deployment_policy(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(COST_POLICY_ENV, None)
            with self.assertRaises(CostPolicyError):
                choose_by_cost(context())

    def test_invalid_policy_files_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            with self.assertRaises(CostPolicyError):
                load_cost_policy(missing)

            malformed = Path(directory) / "malformed.json"
            malformed.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(CostPolicyError):
                load_cost_policy(malformed)

    def test_configured_cost_feature_loads_an_enabled_policy_file(self):
        policy = {
            "schema_version": COST_POLICY_SCHEMA_VERSION,
            "enabled": True,
            "transfer_fixed_seconds": 0,
            "transfer_bytes_per_second": 1000,
            "materialization_seconds": 0,
            "min_savings_seconds": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cost-policy.json"
            path.write_text(json.dumps(policy), encoding="utf-8")
            with patch.dict(os.environ, {"AI4S_COST_POLICY_FILE": str(path)}):
                loaded = load_cost_policy()
                self.assertTrue(loaded.enabled)
                self.assertEqual(
                    configured_cost_decision_path(),
                    "ai4s_workflows.cost_decision:choose_by_cost",
                )
                choose = configured_cost_decision_function()
                self.assertIsNotNone(choose)
                result = choose(context())
                self.assertEqual(result["action"], "reuse")


if __name__ == "__main__":
    unittest.main()
