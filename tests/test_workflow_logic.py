"""Fast checks for manifest gates and attempt bookkeeping; no daemon or model."""

import builtins
import types

import pytest

pytest.importorskip("aiida")

from aiida.common.extendeddicts import AttributeDict

import ai4s_workflows.workflows as workflows
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



class _FakeDict:
    """Small AiiDA-Dict stand-in for pure logic tests without a profile."""

    def __init__(self, data=None, *, uuid=None, creator=None, dict=None):
        raw_data = dict if dict is not None else (data or {})
        self._data = builtins.dict(raw_data)
        self.uuid = uuid
        self.creator = creator

    def get_dict(self):
        return dict(self._data)

    def store(self):
        return self


class _FakeList:
    def __init__(self, values):
        self._values = list(values)

    def get_list(self):
        return list(self._values)


def _str(value):
    return types.SimpleNamespace(value=value)


def _inputs(**overrides):
    inputs = {"mpnn_params": _FakeDict({"seed": 37})}
    inputs.update(overrides)
    return AttributeDict(inputs)


REQUEST_ID = "req-6f1c2a9e-3b7d-4c51-9a0e-1d2f3c4b5a6e"
PROCESS_UUID = "89fea7d1-1fdd-41c8-904d-788b674ab888"
CANDIDATE_UUID = "f9633fef-132c-47d0-b81d-8f3644763518"
SOURCE_UUID = "77f45c98-8471-4f88-8034-1e0198b3e0e7"


def _record(
    *,
    request_id=REQUEST_ID,
    process_uuid=PROCESS_UUID,
    reuse_policy="allow_reuse",
    action="reuse",
    selected_candidate_uuid=CANDIDATE_UUID,
    effective_seed=37,
):
    return {
        "request_id": request_id,
        "process_uuid": process_uuid,
        "reuse_policy": reuse_policy,
        "candidate_compare_list": [
            {
                "uuid": CANDIDATE_UUID,
                "fingerprint": "fe5efe41b0d1fd42",
                "qualified": True,
            }
        ],
        "final_decision": {
            "action": action,
            "selected_candidate_uuid": selected_candidate_uuid,
            "effective_seed": effective_seed,
        },
        "reason": {"reason_code": "R01", "reason_text": "命中合格候选"},
        "timestamp": "2026-11-11T00:00:00Z",
    }


def _bind_workchain_helpers(owner):
    """Attach the class helpers that the production WorkChain receives by inheritance."""
    owner._present_reuse_ports = lambda inputs: ProteinMPNNFilterWorkChain._present_reuse_ports(inputs)
    owner._reuse_request_problem = lambda inputs, **kwargs: ProteinMPNNFilterWorkChain._reuse_request_problem(
        inputs, **kwargs
    )
    return owner


def _owner(monkeypatch, inputs, records=()):
    monkeypatch.setattr(
        workflows,
        "get_reuse_decision_records",
        lambda _node: [dict(record) for record in records],
    )
    owner = types.SimpleNamespace(
        ctx=AttributeDict(),
        inputs=inputs,
        node=types.SimpleNamespace(uuid=PROCESS_UUID),
        invalid_reuse_request=lambda reason: ("invalid_reuse_request", reason),
        reuse_result_unavailable=lambda reason: ("reuse_result_unavailable", reason),
        report=lambda _message: None,
    )
    return _bind_workchain_helpers(owner)


def test_plain_run_does_not_consult_kernel(monkeypatch):
    def unexpected_query(_node):
        raise AssertionError("kernel must not be queried without reuse ports")

    monkeypatch.setattr(workflows, "get_reuse_decision_records", unexpected_query)
    owner = _bind_workchain_helpers(
        types.SimpleNamespace(
            ctx=AttributeDict(),
            inputs=_inputs(),
            report=lambda _message: None,
        )
    )

    assert ProteinMPNNFilterWorkChain.initialize_ctx(owner) is None
    assert owner.ctx.decision_record is None
    assert owner.ctx.effective_seed == 37


@pytest.mark.parametrize(
    "inputs",
    [
        {"reuse_policy": _str("allow_reuse")},
        {"request_id": _str(REQUEST_ID)},
        {"candidate_results": _FakeDict({})},
    ],
)
def test_partial_reuse_ports_are_rejected(monkeypatch, inputs):
    owner = _owner(monkeypatch, _inputs(**inputs), records=[])

    outcome = ProteinMPNNFilterWorkChain.initialize_ctx(owner)

    assert outcome[0] == "invalid_reuse_request"
    assert "request_id and reuse_policy must be supplied together" in outcome[1]


def test_reuse_ports_and_existing_result_are_not_mixed_without_kernel_record(monkeypatch):
    owner = _owner(
        monkeypatch,
        _inputs(
            request_id=_str(REQUEST_ID),
            reuse_policy=_str("allow_reuse"),
            existing_mpnn_result=object(),
        ),
        records=[],
    )

    outcome = ProteinMPNNFilterWorkChain.initialize_ctx(owner)

    assert outcome[0] == "invalid_reuse_request"
    assert "cannot be combined" in outcome[1]


@pytest.mark.parametrize("records", [[], [_record(), _record()]])
def test_kernel_must_persist_exactly_one_decision_record(monkeypatch, records):
    owner = _owner(
        monkeypatch,
        _inputs(
            request_id=_str(REQUEST_ID),
            reuse_policy=_str("allow_reuse"),
        ),
        records=records,
    )

    outcome = ProteinMPNNFilterWorkChain.initialize_ctx(owner)

    assert outcome[0] == "invalid_reuse_request"
    assert "exactly one" in outcome[1]


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (_record(request_id="req-11111111-1111-4111-8111-111111111111"), "request_id"),
        (_record(reuse_policy="force_rerun"), "reuse_policy"),
        (
            _record(process_uuid="599e385a-cb5a-4de7-9180-0ffdde836a8f"),
            "process_uuid",
        ),
    ],
)
def test_kernel_record_identity_must_match_the_workchain(monkeypatch, record, expected):
    owner = _owner(
        monkeypatch,
        _inputs(
            request_id=_str(REQUEST_ID),
            reuse_policy=_str("allow_reuse"),
        ),
        records=[record],
    )

    outcome = ProteinMPNNFilterWorkChain.initialize_ctx(owner)

    assert outcome[0] == "invalid_reuse_request"
    assert expected in outcome[1]


def test_kernel_cannot_override_explicit_force_rerun_policy(monkeypatch):
    owner = _owner(
        monkeypatch,
        _inputs(
            request_id=_str(REQUEST_ID),
            reuse_policy=_str("force_rerun"),
        ),
        records=[_record(reuse_policy="force_rerun", action="reuse")],
    )

    outcome = ProteinMPNNFilterWorkChain.initialize_ctx(owner)

    assert outcome[0] == "invalid_reuse_request"
    assert "not allowed by policy" in outcome[1]


def test_rewritten_effective_seed_must_be_present_in_mpnn_params(monkeypatch):
    owner = _owner(
        monkeypatch,
        _inputs(
            request_id=_str(REQUEST_ID),
            reuse_policy=_str("new_sample"),
        ),
        records=[
            _record(
                reuse_policy="new_sample",
                action="new_sample",
                selected_candidate_uuid=None,
                effective_seed=99,
            )
        ],
    )

    outcome = ProteinMPNNFilterWorkChain.initialize_ctx(owner)

    assert outcome[0] == "invalid_reuse_request"
    assert "effective_seed was not applied" in outcome[1]


def test_kernel_reuse_records_candidate_and_source(monkeypatch):
    result = _FakeDict(
        {"schema_version": "ai4s-artifacts-1"},
        uuid=CANDIDATE_UUID,
        creator=types.SimpleNamespace(uuid=SOURCE_UUID),
    )
    monkeypatch.setattr(workflows, "Dict", _FakeDict)
    owner = _owner(
        monkeypatch,
        _inputs(
            request_id=_str(REQUEST_ID),
            reuse_policy=_str("allow_reuse"),
            candidate_results=_FakeDict(
                {f"{CANDIDATE_UUID}::fe5efe41b0d1fd42": CANDIDATE_UUID}
            ),
            existing_mpnn_result=result,
        ),
        records=[_record()],
    )

    assert ProteinMPNNFilterWorkChain.initialize_ctx(owner) is None
    assert ProteinMPNNFilterWorkChain.maybe_skip_inference(owner) is None

    assert owner.ctx.skip_submit is True
    assert owner.ctx.mpnn_result is result
    assert owner.ctx.cached_from == SOURCE_UUID
    assert owner.ctx.mpnn_cache_source == SOURCE_UUID
    report = ProteinMPNNFilterWorkChain._report_details(owner)
    assert report["reuse_decision"] == "reuse"
    assert report["cached_from"] == SOURCE_UUID


def test_legacy_filter_only_path_still_accepts_existing_result():
    result = object()
    owner = types.SimpleNamespace(
        ctx=AttributeDict({"decision_record": None}),
        inputs=AttributeDict({"existing_mpnn_result": result}),
    )

    ProteinMPNNFilterWorkChain.maybe_skip_inference(owner)

    assert owner.ctx.mpnn_result is result
    assert owner.ctx.skip_submit is True


def test_kernel_rerun_keeps_original_seed():
    inputs = _inputs()
    decision = types.SimpleNamespace(
        action=types.SimpleNamespace(value="rerun"),
        effective_seed=37,
        selected_candidate_uuid=None,
        candidate_compare_list=[],
    )

    rewritten = ProteinMPNNFilterWorkChain._rewrite_reuse_inputs(None, inputs, decision)

    assert rewritten["mpnn_params"].get_dict()["seed"] == 37


def test_kernel_new_sample_uses_effective_seed(monkeypatch):
    monkeypatch.setattr(workflows, "Dict", _FakeDict)
    inputs = _inputs(mpnn_params=_FakeDict({"seed": 37}))
    decision = types.SimpleNamespace(
        action=types.SimpleNamespace(value="new_sample"),
        effective_seed=99,
        selected_candidate_uuid=None,
        candidate_compare_list=[],
    )

    rewritten = ProteinMPNNFilterWorkChain._rewrite_reuse_inputs(None, inputs, decision)

    assert rewritten["mpnn_params"].get_dict()["seed"] == 99


def test_kernel_reuse_rewrite_injects_the_selected_result(monkeypatch):
    result = _FakeDict({}, uuid=CANDIDATE_UUID, creator=types.SimpleNamespace(uuid=SOURCE_UUID))
    monkeypatch.setattr(workflows, "Dict", _FakeDict)
    monkeypatch.setattr(workflows, "load_node", lambda uuid_value: result)
    inputs = _inputs(
        candidate_results=_FakeDict(
            {f"{CANDIDATE_UUID}::fe5efe41b0d1fd42": CANDIDATE_UUID}
        )
    )
    decision = types.SimpleNamespace(
        action=types.SimpleNamespace(value="reuse"),
        effective_seed=37,
        selected_candidate_uuid=CANDIDATE_UUID,
        candidate_compare_list=[
            {"uuid": CANDIDATE_UUID, "fingerprint": "fe5efe41b0d1fd42"}
        ],
    )

    rewritten = ProteinMPNNFilterWorkChain._rewrite_reuse_inputs(None, inputs, decision)

    assert rewritten["existing_mpnn_result"] is result
