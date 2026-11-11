"""Fast checks for agreement 5 decisions and persisted audit records."""

import copy
import json
import re

import pytest

from ai4s_workflows.decision import (
    DecisionError,
    decision_records_from_nodes,
    load_decision_function,
    make_decision_record,
    save_decision_record,
    validate_decision_record,
)


REQUEST_ID = "req-6f1c2a9e-3b7d-4c51-9a0e-1d2f3c4b5a6e"
PROCESS_UUID = "2f49ef2c-7e42-4f88-8d54-3320e4cf1f1a"
OTHER_PROCESS_UUID = "5ba9ba38-6291-412b-acfa-5319fcbbbf0f"
CANDIDATE_A = "f9633fef-132c-47d0-b81d-8f3644763518"
CANDIDATE_B = "6d078da7-3963-4e53-acec-1fb51dc84531"
TIMESTAMP = "2026-11-09T08:10:30Z"


def candidate(uuid=CANDIDATE_A, fingerprint="fe5efe41b0d1fd42", qualified=True, reason=None):
    return {
        "uuid": uuid,
        "fingerprint": fingerprint,
        "member": "陈思睿",
        "location": f"profile://ai4s/{uuid}/result.json",
        "size_bytes": 128,
        "elapsed_s": 0,
        "qualified": qualified,
        "reason": reason,
        "note": "cached_from=source" if qualified else "",
    }


def make_record(reuse_policy, candidates=None, **overrides):
    values = {
        "request_id": REQUEST_ID,
        "process_uuid": PROCESS_UUID,
        "reuse_policy": reuse_policy,
        "candidates": [] if candidates is None else candidates,
        "original_seed": 37,
        "timestamp": TIMESTAMP,
    }
    values.update(overrides)
    return make_decision_record(**values)


def test_allow_reuse_selects_first_qualified_candidate_and_builds_full_record():
    unqualified = candidate(
        CANDIDATE_B,
        qualified=False,
        reason="below_threshold: 最优分数 1.42 > 阈值 1.20",
    )
    record = make_record("allow_reuse", [unqualified, candidate()])

    assert record["final_decision"] == {
        "action": "reuse",
        "selected_candidate_uuid": CANDIDATE_A,
        "effective_seed": 37,
    }
    assert record["reason"]["reason_code"] == "R01"
    assert record["candidate_compare_list"] == [unqualified, candidate()]
    assert record["process_uuid"] == PROCESS_UUID.lower()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", record["timestamp"])
    assert json.loads(json.dumps(record, ensure_ascii=False)) == record


@pytest.mark.parametrize("candidates", [[], [candidate(qualified=False, reason="not_finished: killed")]])
def test_allow_reuse_without_qualified_candidate_degrades_to_rerun(candidates):
    record = make_record("allow_reuse", candidates)

    assert record["final_decision"] == {
        "action": "rerun",
        "selected_candidate_uuid": None,
        "effective_seed": 37,
    }
    assert record["reason"]["reason_code"] == "R02"


def test_force_rerun_preserves_original_seed_and_candidate_audit_list():
    candidates = [candidate()]
    record = make_record("force_rerun", candidates)

    assert record["final_decision"]["action"] == "rerun"
    assert record["final_decision"]["effective_seed"] == 37
    assert record["reason"]["reason_code"] == "R03"
    assert record["candidate_compare_list"] == candidates


def test_new_sample_uses_a_different_valid_seed():
    record = make_record("new_sample", [candidate()], seed_factory=lambda _: 52817)

    assert record["final_decision"] == {
        "action": "new_sample",
        "selected_candidate_uuid": None,
        "effective_seed": 52817,
    }
    assert record["reason"]["reason_code"] == "R04"
    assert record["candidate_compare_list"] == [candidate()]


def test_custom_decision_function_uses_r05_and_cannot_select_unqualified_candidate():
    def reject_all(context):
        return {
            "action": "rerun",
            "selected_candidate_uuid": None,
            "effective_seed": context["original_seed"],
            "reason_text": "人工策略认为当前候选质量证据不足",
        }

    record = make_record("allow_reuse", [candidate(qualified=False, reason="manual_reject: 待复核")], decision_function=reject_all)
    assert record["reason"]["reason_code"] == "R05"
    assert record["final_decision"]["action"] == "rerun"

    def select_unqualified(context):
        return {
            "action": "reuse",
            "selected_candidate_uuid": CANDIDATE_A,
            "effective_seed": context["original_seed"],
            "reason_text": "错误地选择不合格候选",
        }

    with pytest.raises(DecisionError, match="unqualified"):
        make_record(
            "allow_reuse",
            [candidate(qualified=False, reason="manual_reject: 用户否决")],
            decision_function=select_unqualified,
        )

    def select_with_changed_seed(context):
        return {
            "action": "reuse",
            "selected_candidate_uuid": CANDIDATE_A,
            "effective_seed": context["original_seed"] + 1,
            "reason_text": "错误地同时复用并更换种子",
        }

    with pytest.raises(DecisionError, match="preserve the original seed"):
        make_record(
            "allow_reuse",
            [candidate()],
            decision_function=select_with_changed_seed,
        )


@pytest.mark.parametrize(
    ("reuse_policy", "action", "effective_seed", "selected_uuid"),
    [
        ("force_rerun", "reuse", 37, CANDIDATE_A),
        ("force_rerun", "new_sample", 52817, None),
        ("new_sample", "reuse", 37, CANDIDATE_A),
        ("new_sample", "rerun", 37, None),
    ],
)
def test_custom_decision_cannot_bypass_user_policy(
    reuse_policy,
    action,
    effective_seed,
    selected_uuid,
):
    def choose(context):
        return {
            "action": action,
            "selected_candidate_uuid": selected_uuid,
            "effective_seed": effective_seed,
            "reason_text": "试图绕过用户选择的复用策略",
        }

    with pytest.raises(
        DecisionError,
        match=rf"reuse_policy {reuse_policy} does not allow action {action}",
    ):
        make_record(reuse_policy, [candidate()], decision_function=choose)


@pytest.mark.parametrize(
    ("reuse_policy", "action", "effective_seed", "selected_uuid"),
    [
        ("allow_reuse", "reuse", 37, CANDIDATE_A),
        ("allow_reuse", "rerun", 37, None),
        ("force_rerun", "rerun", 37, None),
        ("new_sample", "new_sample", 52817, None),
    ],
)
def test_custom_decision_allows_only_policy_compatible_actions(
    reuse_policy,
    action,
    effective_seed,
    selected_uuid,
):
    def choose(context):
        return {
            "action": action,
            "selected_candidate_uuid": selected_uuid,
            "effective_seed": effective_seed,
            "reason_text": "在用户策略允许范围内自定义决策",
        }

    record = make_record(reuse_policy, [candidate()], decision_function=choose)

    assert record["reason"]["reason_code"] == "R05"
    assert record["reuse_policy"] == reuse_policy
    assert record["final_decision"]["action"] == action


def test_decision_record_validation_rejects_tampered_policy_action_pair():
    def rerun(context):
        return {
            "action": "rerun",
            "selected_candidate_uuid": None,
            "effective_seed": context["original_seed"],
            "reason_text": "人工判断后选择重算",
        }

    record = make_record("allow_reuse", [candidate()], decision_function=rerun)
    record["reuse_policy"] = "new_sample"

    with pytest.raises(
        DecisionError,
        match="reuse_policy new_sample does not allow action rerun",
    ):
        validate_decision_record(record)


def test_candidate_uniqueness_uses_uuid_and_fingerprint():
    same_node_different_fingerprint = [
        candidate(fingerprint="fingerprint-a"),
        candidate(fingerprint="fingerprint-b"),
    ]
    record = make_record("allow_reuse", same_node_different_fingerprint)
    assert record["final_decision"]["selected_candidate_uuid"] == CANDIDATE_A

    with pytest.raises(DecisionError, match=r"\(uuid, fingerprint\)"):
        make_record("allow_reuse", [candidate(), candidate()])


def test_candidate_validation_requires_agreement_4_fields_and_formats():
    incomplete = candidate()
    del incomplete["member"]
    with pytest.raises(DecisionError, match="missing fields: member"):
        make_record("allow_reuse", [incomplete])

    malformed_uuid = candidate(uuid="not-a-uuid")
    with pytest.raises(DecisionError, match="UUID string"):
        make_record("allow_reuse", [malformed_uuid])

    malformed_reason = candidate(qualified=False, reason="looks good")
    with pytest.raises(DecisionError, match="known reason code"):
        make_record("allow_reuse", [malformed_reason])


def test_decision_record_validation_enforces_reason_policy_pairs():
    record = make_record("force_rerun", [candidate()])
    record["final_decision"]["action"] = "reuse"
    record["final_decision"]["selected_candidate_uuid"] = CANDIDATE_A
    with pytest.raises(DecisionError, match="R03"):
        validate_decision_record(record)

    record = make_record("allow_reuse", [candidate()])
    record["reason"] = {"reason_code": "R02", "reason_text": "错误理由"}
    record["final_decision"] = {
        "action": "rerun",
        "selected_candidate_uuid": None,
        "effective_seed": 37,
    }
    with pytest.raises(DecisionError, match="R02 requires"):
        validate_decision_record(record)

    record = make_record("force_rerun", [candidate()])
    record["reason"] = {"reason_code": "R02", "reason_text": "伪造的无候选说明"}
    with pytest.raises(DecisionError, match="R02 requires reuse_policy allow_reuse"):
        validate_decision_record(record)

    record = make_record("allow_reuse", [])
    record["reason"] = {"reason_code": "R03", "reason_text": "伪造的强制重算说明"}
    with pytest.raises(DecisionError, match="R03 requires reuse_policy force_rerun"):
        validate_decision_record(record)


def test_decision_record_rejects_malformed_timestamp_and_missing_fields():
    record = make_record("force_rerun", [candidate()])
    record["timestamp"] = "2026-11-09 08:10:30"
    with pytest.raises(DecisionError, match="ISO 8601"):
        validate_decision_record(record)

    incomplete = make_record("force_rerun", [candidate()])
    del incomplete["reuse_policy"]
    with pytest.raises(DecisionError, match="missing fields"):
        validate_decision_record(incomplete)


def test_decision_function_loader_supports_module_colon_function():
    function = load_decision_function("ai4s_workflows.decision:default_reuse_decision")
    assert callable(function)


class _Extras:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = copy.deepcopy(value)


class _FakeNode:
    def __init__(self):
        self.base = type("Base", (), {"extras": _Extras()})()


def test_save_and_query_records_replace_replays_and_keep_separate_processes():
    node = _FakeNode()
    first = make_record("force_rerun", [candidate()])
    save_decision_record(node, first)

    replay = copy.deepcopy(first)
    replay["reason"]["reason_text"] = "同一过程的重放更新了说明"
    save_decision_record(node, replay)
    assert decision_records_from_nodes([node], request_id=REQUEST_ID) == [replay]

    second = make_record(
        "new_sample",
        [candidate()],
        process_uuid=OTHER_PROCESS_UUID,
        seed_factory=lambda _: 52817,
    )
    save_decision_record(node, second)
    records = decision_records_from_nodes([node], request_id=REQUEST_ID)
    assert len(records) == 2
    assert {record["process_uuid"] for record in records} == {PROCESS_UUID, OTHER_PROCESS_UUID}
    assert decision_records_from_nodes([node], process_uuid=OTHER_PROCESS_UUID) == [second]
