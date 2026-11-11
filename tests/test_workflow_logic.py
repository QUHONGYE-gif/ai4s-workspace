"""Fast checks for manifest gates and attempt bookkeeping; no daemon or model."""

import types

import pytest

pytest.importorskip("aiida")

from aiida.common.extendeddicts import AttributeDict

from ai4s_workflows.workflows import (
    MAX_ATTEMPTS,
    MAX_RETRY,
    ProteinMPNNFilterWorkChain,
    attempt_label,
    process_state_value,
    validation_manifest_problem,
)


def valid_manifest():
    return {
        "schema_version": "ai4s-artifacts-1",
        "version": "v1.0",
        "task_id": "proteinmpnn",
        "contract_version": "1",
        "validation": {"passed": True},
        "artifacts": [{"port": "artifacts.sequences", "samples": []}],
    }


def test_attempt_limit_is_two_total_submissions():
    assert MAX_ATTEMPTS == 2
    assert MAX_RETRY == 1
    assert attempt_label("workflow-uuid", 1).endswith(":01")


def test_unlaunched_process_is_reported_as_created():
    assert process_state_value(types.SimpleNamespace(process_state=None)) == "created"
    assert process_state_value(
        types.SimpleNamespace(process_state=types.SimpleNamespace(value="waiting"))
    ) == "waiting"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda data: data.update(schema_version="other"), "schema_version"),
        (lambda data: data.update(validation={"passed": False}), "did not pass"),
        (lambda data: data["validation"].update(invalidates_cache=True), "invalidate reuse"),
        (lambda data: data["validation"].update(errors=["bad"]), "known validation issues"),
        (lambda data: data["artifacts"].append({"port": "artifacts.sequences"}), "duplicate"),
    ],
)
def test_manifest_gate_rejects_known_invalid_conditions(change, expected):
    manifest = valid_manifest()
    change(manifest)
    assert expected in validation_manifest_problem(manifest)


def test_manifest_gate_accepts_complete_valid_manifest():
    assert validation_manifest_problem(valid_manifest()) is None


def test_report_details_preserve_each_attempt_and_counts():
    owner = AttributeDict({
        "ctx": AttributeDict({
            "attempts": [
                {"attempt": 1, "calcjob_uuid": "first", "status": "failed"},
                {"attempt": 2, "calcjob_uuid": "second", "status": "succeeded"},
            ],
            "model_launches": 2,
        }),
    })
    report = ProteinMPNNFilterWorkChain._report_details(owner)
    assert report["attempt_count"] == 2
    assert report["retry_attempt"] == 1
    assert report["model_launches"] == 2
    assert report["calcjob_submissions"] == 2
    assert [attempt["calcjob_uuid"] for attempt in report["attempts"]] == ["first", "second"]


def test_report_details_expose_reuse_decision_and_effective_seed():
    owner = AttributeDict({
        "ctx": AttributeDict({
            "attempts": [],
            "model_launches": 0,
            "request_id": "req-6f1c2a9e-3b7d-4c51-9a0e-1d2f3c4b5a6e",
            "reuse_policy": "allow_reuse",
            "decision_record": {
                "final_decision": {
                    "action": "reuse",
                    "selected_candidate_uuid": "f9633fef-132c-47d0-b81d-8f3644763518",
                    "effective_seed": 37,
                },
                "reason": {"reason_code": "R01", "reason_text": "命中合格候选"},
            },
            "effective_seed": 37,
            "cached_from": "2f49ef2c-7e42-4f88-8d54-3320e4cf1f1a",
        }),
    })

    report = ProteinMPNNFilterWorkChain._report_details(owner)
    assert report["reuse_decision"] == "reuse"
    assert report["reason_code"] == "R01"
    assert report["selected_candidate_uuid"] == "f9633fef-132c-47d0-b81d-8f3644763518"
    assert report["effective_seed"] == 37
    assert report["cached_from"] == "2f49ef2c-7e42-4f88-8d54-3320e4cf1f1a"



class _DictData:
    def __init__(self, data):
        self._data = dict(data)

    def get_dict(self):
        return dict(self._data)


def _decision_input_owner(inputs):
    return types.SimpleNamespace(
        ctx=AttributeDict(),
        inputs=AttributeDict({
            "mpnn_params": _DictData({"seed": 37}),
            **inputs,
        }),
        invalid_reuse_request=lambda reason: ("invalid_reuse_request", reason),
    )


@pytest.mark.parametrize(
    ("inputs", "expected"),
    [
        (
            {"reuse_policy": types.SimpleNamespace(value="allow_reuse")},
            "必须同时提供",
        ),
        (
            {"request_id": types.SimpleNamespace(value="req-6f1c2a9e-3b7d-4c51-9a0e-1d2f3c4b5a6e")},
            "必须同时提供",
        ),
        (
            {"candidate_results": _DictData({})},
            "必须与 request_id、reuse_policy 一同提供",
        ),
        (
            {
                "request_id": types.SimpleNamespace(value="req-6f1c2a9e-3b7d-4c51-9a0e-1d2f3c4b5a6e"),
                "reuse_policy": types.SimpleNamespace(value="allow_reuse"),
                "existing_mpnn_result": object(),
            },
            "不能同时使用",
        ),
    ],
)
def test_reuse_decision_ports_are_required_together_and_exclusive(inputs, expected):
    outcome = ProteinMPNNFilterWorkChain.initialize_ctx(_decision_input_owner(inputs))

    assert outcome[0] == "invalid_reuse_request"
    assert expected in outcome[1]


@pytest.mark.parametrize(
    ("candidate_results", "expected"),
    [
        ({}, "唯一定位"),
        (
            {
                "f9633fef-132c-47d0-b81d-8f3644763518::fe5efe41b0d1fd42":
                    "6d078da7-3963-4e53-acec-1fb51dc84531"
            },
            "不一致",
        ),
    ],
)
def test_reuse_requires_an_unambiguous_candidate_result_mapping(candidate_results, expected):
    decision_record = {
        "final_decision": {
            "action": "reuse",
            "selected_candidate_uuid": "f9633fef-132c-47d0-b81d-8f3644763518",
            "effective_seed": 37,
        },
        "candidate_compare_list": [
            {
                "uuid": "f9633fef-132c-47d0-b81d-8f3644763518",
                "fingerprint": "fe5efe41b0d1fd42",
                "qualified": True,
            }
        ],
    }
    owner = types.SimpleNamespace(
        ctx=AttributeDict({"decision_record": decision_record}),
        inputs=AttributeDict({"candidate_results": _DictData(candidate_results)}),
        reuse_result_unavailable=lambda reason: ("reuse_result_unavailable", reason),
    )

    outcome = ProteinMPNNFilterWorkChain.maybe_skip_inference(owner)

    assert outcome[0] == "reuse_result_unavailable"
    assert expected in outcome[1]
