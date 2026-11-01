"""Deterministic API/integrity tests; TestModel is NOT real LLM acceptance."""

import asyncio
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from ai4s_demo.app import create_app
from ai4s_demo.models import ChangeAudit, ChatRequest, ImportDecision, ImportRequest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    app = create_app(tmp_path)
    # Tests should never inherit a real provider/key or perform a paid call.
    app.state.gateway.settings.private = lambda: {"model": "test", "api_key": ""}
    with TestClient(app) as client:
        yield client


def workflow(client, template="protein"):
    r = client.post("/api/workflows", json={"template": template})
    assert r.status_code == 201
    return r.json()["draft"]


def test_agent_assets_and_api_work_under_preview_prefix(tmp_path):
    # Uvicorn restores the mount prefix stripped by the workbench proxy.
    with TestClient(create_app(tmp_path), root_path="/agent") as client:
        page = client.get("/agent/", follow_redirects=False)
        assert page.status_code == 307
        assert page.headers["location"] == "../#/workflows/new?mode=ai"
        workspace = client.get("/agent/assets/workspace.html")
        assert workspace.status_code == 200
        assert 'class="sidebar"' not in workspace.text
        assert 'id="apply-workflow"' in workspace.text
        assert client.get("/agent/assets/app.js").status_code == 200
        assert client.get("/agent/api/health").json()["adapter"] == "not_connected"
        assert client.post("/agent/api/workflows", json={"template": "protein"}).status_code == 201


def change(client, draft, operations, **overrides):
    body = {"expected_revision": draft["revision"], "operation_id": "op-test", "operations": operations, **overrides}
    return client.post(f"/api/workflows/{draft['id']}/changes", json=body)


def read(client, draft):
    return client.get(f"/api/workflows/{draft['id']}").json()


def test_atomic_edit_and_invalid_field_no_partial_save(client):
    draft = workflow(client)
    r = change(client, draft, [
        {"type": "update_params", "node_id": "mpnn-1", "changes": {"sampling_temp": 0.2}},
        {"type": "update_params", "node_id": "mpnn-1", "changes": {"unknown_field": 16}},
    ])
    assert r.status_code == 422
    after = read(client, draft)["draft"]
    assert after == draft


@pytest.mark.parametrize("value", [-1, 0, 1.5, True, "4"])
def test_sequence_count_type_and_range(client, value):
    draft = workflow(client)
    assert change(client, draft, [{"type": "update_params", "node_id": "mpnn-1", "changes": {"num_seq_per_target": value}}]).status_code == 422
    assert read(client, draft)["draft"]["revision"] == 0


def test_revision_idempotency_and_undo(client):
    draft = workflow(client)
    ops = [{"type": "update_params", "node_id": "mpnn-1", "changes": {"sampling_temp": 0.2, "num_seq_per_target": 16}}]
    result = change(client, draft, ops)
    assert result.status_code == 200
    assert result.json()["state"]["draft"]["revision"] == 1
    assert change(client, draft, ops).json()["state"]["draft"]["revision"] == 1
    assert change(client, draft, ops, operation_id="different-op").status_code == 409
    assert change(client, draft, [{"type": "rename", "name": "different"}]).status_code == 409
    path = f"/api/workflows/{draft['id']}/undo"
    assert client.post(path, json={"expected_revision": 0, "operation_id": "undo-old"}).status_code == 409
    undone = client.post(path, json={"expected_revision": 1, "operation_id": "undo-current"})
    assert undone.status_code == 200
    restored = undone.json()["state"]["draft"]
    assert restored["revision"] == 2
    assert restored["nodes"] == draft["nodes"]
    assert client.post(path, json={"expected_revision": 2, "operation_id": "undo-again"}).status_code == 409


def test_registration_snapshot_and_stale_request(client):
    draft = workflow(client)
    base = f"/api/workflows/{draft['id']}"
    missing = client.post(base + "/registrations", json={"expected_revision": 0, "operation_id": "reg-missing", "node_ids": ["mpnn-1"]})
    assert missing.status_code == 422
    reg = client.post(base + "/registrations", json={"expected_revision": 0, "operation_id": "reg-ok", "node_ids": ["rfd-1"]}).json()["registration"]
    request = client.post(base + "/requests", json={"registration_id": reg["id"]}).json()["request"]
    assert request["steps"][0]["params"]["length"] == 80
    assert request["execution_status"] == "not_submitted"
    assert request["ready_for_submission"] is False
    assert "adapter_not_connected" in request["blocking_issues"]
    result = change(client, draft, [{"type": "update_params", "node_id": "rfd-1", "changes": {"length": 90}}])
    assert result.status_code == 200
    assert result.json()["state"]["requests"][0]["stale"] is True
    assert result.json()["state"]["registrations"][0]["snapshot"]["steps"][0]["params"]["length"] == 80
    assert client.post(base + "/requests", json={"registration_id": reg["id"]}).status_code == 409


def test_connections_delete_confirmation_and_node_reuse(client):
    draft = workflow(client)
    result = change(client, draft, [{"type": "connect", "source": "boltz-1", "source_port": "structure", "target": "mpnn-1", "target_port": "backbone"}])
    assert result.status_code == 422
    assert change(client, draft, [{"type": "remove_node", "node_id": "mpnn-1"}]).status_code == 422
    result = change(client, draft, [{"type": "remove_node", "node_id": "mpnn-1"}], confirmed=True)
    assert result.status_code == 200
    new = result.json()["state"]["draft"]
    assert len(new["nodes"]) == 2 and new["edges"] == []
    assert "sequence" not in new["nodes"][1]["inputs"]


def test_real_pdb_chain_validation_and_snapshot(client):
    draft = workflow(client)
    pdb = Path(__file__).parents[1] / "tests/fixtures/backbone.pdb"
    uploaded = client.post("/api/files", files={"file": ("backbone.pdb", pdb.read_bytes())})
    assert uploaded.status_code == 201
    info = uploaded.json()
    assert info["chains"] == {"A": 2, "B": 1}
    ops = [{"type": "set_input", "node_id": "mpnn-1", "port": "backbone", "value": {"kind": "file", "file_id": info["id"]}},
           {"type": "set_chains", "node_id": "mpnn-1", "policy": {"mode": "selected", "chains": ["Z"]}}]
    assert change(client, draft, ops).status_code == 422
    assert read(client, draft)["draft"] == draft
    ops[1]["policy"] = {"mode": "all"}
    result = change(client, draft, ops)
    assert result.status_code == 200
    assert result.json()["state"]["checks"]["mpnn-1"]["missing"] == []


def test_fasta_design_record_and_msa_identity(client):
    draft = workflow(client)
    fasta = b">native, score=1\nGGGG\n>sample=1, score=2\nACDE\n"
    info = client.post("/api/files", files={"file": ("seq.fa", fasta)}).json()
    assert info["records"][0]["selectable"] is False
    op = {"type": "set_input", "node_id": "boltz-1", "port": "sequence", "value": {"kind": "file", "file_id": info["id"], "record_id": "record-1"}}
    assert change(client, draft, [op]).status_code == 422
    op["value"]["record_id"] = "record-2"
    msa = client.post("/api/files", files={"file": ("wrong.a3m", b">q\nAAAA\n>s\nAAAA\n")}).json()
    result = change(client, draft, [op, {"type": "update_params", "node_id": "boltz-1", "changes": {"msa_mode": "precomputed"}},
                                   {"type": "set_input", "node_id": "boltz-1", "port": "msa", "value": {"kind": "file", "file_id": msa["id"]}}])
    assert result.status_code == 200
    assert "A3M 首条查询序列与当前蛋白不一致" in result.json()["state"]["checks"]["boltz-1"]["missing"]
    assert client.post("/api/files", files={"file": ("bad.a3m", b">q\nACDE\n>s\nACD\n")}).status_code == 422


def test_import_requires_exact_evidence_and_confirmation(client):
    draft = workflow(client)
    service = client.app.state.service
    request = ImportRequest(model_id="proteinmpnn", content="--sampling_temp 0.2", source="示例")
    extracted = ImportDecision(parameters=[{"field": "sampling_temp", "value": 0.2, "category": "example", "quote": "--sampling_temp 0.2"}], notes="示例")
    preview = service.save_preview(draft["id"], request, extracted, {"provider": "unit-test"})
    op = {"type": "apply_import", "node_id": "mpnn-1", "preview_id": preview["id"]}
    assert change(client, draft, [op]).status_code == 422
    result = change(client, draft, [op], confirmed=True)
    assert result.status_code == 200
    assert result.json()["state"]["draft"]["nodes"][1]["provenance"]["sampling_temp"]["kind"] == "example"
    extracted.parameters[0].quote = "not in supplied document"
    invalid = service.save_preview(draft["id"], request, extracted, {})
    assert invalid["errors"] and invalid["accepted"] == []


def test_api_key_never_returned_or_exported(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with TestClient(create_app(tmp_path)) as client:
        key = "sk-unit-test-not-a-real-key"
        response = client.post("/api/settings/model", json={"model": "deepseek-flash", "api_key": key})
        assert response.status_code == 200 and response.json()["has_key"] is True
        draft = workflow(client)
        for response in [response, client.get("/api/settings/model"), client.get("/api/health"), client.get(f"/api/workflows/{draft['id']}")]:
            assert key not in response.text
        malformed = client.post("/api/settings/model", json={"model": "invalid model", "api_key": key})
        assert malformed.status_code == 422 and key not in malformed.text
        private = tmp_path / "settings/deepseek.json"
        if os.name == "posix":
            # Windows maps chmod(0o600) to the readonly user attribute only, so the
            # strict owner-only bit check is meaningful on POSIX systems alone.
            assert private.stat().st_mode & 0o777 == 0o600
        else:
            # Windows chmod(0o600) only clears the readonly attribute; the file is
            # still owner-only because it lives under the user profile directory.
            assert private.exists() and json.loads(private.read_text(encoding="utf-8"))["api_key"] == key
        assert client.post("/api/settings/model", json={"model": "deepseek-v4-pro"}).json()["has_key"] is True
        assert client.post("/api/settings/model", json={"remove_key": True}).json()["has_key"] is False
        assert client.post("/api/settings/model", json={"api_key": key}, headers={"Origin": "https://other.example"}).status_code == 403


def test_reload_persistence_and_single_process_lock(tmp_path):
    with TestClient(create_app(tmp_path)) as first:
        draft = workflow(first)
        assert change(first, draft, [{"type": "update_params", "node_id": "rfd-1", "changes": {"length": 100}}]).status_code == 200
        with pytest.raises(RuntimeError, match="一个服务进程"):
            with TestClient(create_app(tmp_path)):
                pass
    with TestClient(create_app(tmp_path)) as second:
        stored = read(second, draft)["draft"]
        assert stored["revision"] == 1 and stored["nodes"][0]["params"]["length"] == 100


def test_agent_answer_and_change_contract_without_network(client):
    """Fake model validates integration mechanics, NOT language understanding."""
    draft = workflow(client)
    gateway = client.app.state.gateway
    output = {"intent": "answer", "reply": "解释温度", "operations": [], "needs_confirmation": False}
    gateway._model = lambda: TestModel(call_tools=[], custom_output_args=output)
    path = f"/api/workflows/{draft['id']}/messages"
    message = {"expected_revision": 0, "operation_id": "chat-1", "message": "温度0.2是什么意思", "selected_node_id": "mpnn-1"}
    result = client.post(path, json=message)
    assert result.status_code == 200, result.text
    assert result.json()["state"]["draft"] == draft
    assert client.post(path, json=message).json()["state"]["messages"] == result.json()["state"]["messages"]
    output.update(intent="change", reply="提案", operations=[{"type": "update_params", "node_id": "mpnn-1", "changes": {"sampling_temp": 0.2, "num_seq_per_target": 16}}])
    async def approved_review(*args):
        return ChangeAudit(explicit_request=True, complete_and_consistent=True, reason="unit-test contract"), {
            "requests": 0, "input_tokens": 0, "output_tokens": 0, "elapsed_seconds": 0}
    gateway._review_change = approved_review
    result = client.post(path, json={**message, "operation_id": "chat-2", "message": "改成0.2和16"})
    assert result.status_code == 200, result.text
    after = result.json()["state"]["draft"]
    assert after["revision"] == 1 and after["nodes"][1]["params"]["num_seq_per_target"] == 16


def test_incomplete_agent_proposal_is_not_applied(client):
    draft = workflow(client)
    gateway = client.app.state.gateway
    output = {"intent": "change", "reply": "只改温度", "operations": [{"type": "update_params", "node_id": "mpnn-1", "changes": {"sampling_temp": 0.3}}]}
    gateway._model = lambda: TestModel(call_tools=[], custom_output_args=output)
    async def blocked_review(*args):
        return ChangeAudit(explicit_request=True, complete_and_consistent=False, reason="数量非法，整批没有保存"), {
            "requests": 0, "input_tokens": 0, "output_tokens": 0, "elapsed_seconds": 0}
    gateway._review_change = blocked_review
    result = client.post(f"/api/workflows/{draft['id']}/messages", json={"expected_revision": 0, "operation_id": "incomplete", "message": "温度0.3，序列数-1，一起修改", "selected_node_id": "mpnn-1"})
    assert result.status_code == 200
    assert result.json()["state"]["draft"] == draft
    assert result.json()["message"]["intent"] == "clarify"


def test_missing_key_is_explicit_not_offline_fake(client):
    assert client.post("/api/settings/model/test").status_code == 503
    draft = workflow(client)
    result = client.post(f"/api/workflows/{draft['id']}/messages", json={"expected_revision": 0, "operation_id": "missing-key", "message": "你好"})
    assert result.status_code == 503
    assert read(client, draft)["draft"] == draft


def test_multiple_model_instances_cannot_be_silently_chosen(client):
    draft = workflow(client)
    result = change(client, draft, [{"type": "add_node", "node_id": "boltz-2", "model_id": "boltz", "label": "第二个结构预测"}])
    draft = result.json()["state"]["draft"]
    gateway = client.app.state.gateway
    output = {"intent": "change", "reply": "选择第一个", "operations": [{"type": "update_params", "node_id": "boltz-1", "changes": {"diffusion_samples": 3}}]}
    gateway._model = lambda: TestModel(call_tools=[], custom_output_args=output)
    result = client.post(f"/api/workflows/{draft['id']}/messages", json={"expected_revision": 1, "operation_id": "ambiguous", "message": "把Boltz采样数改为3", "selected_node_id": "mpnn-1"})
    assert result.status_code == 200
    assert result.json()["message"]["intent"] == "clarify"
    assert result.json()["state"]["draft"] == draft


def test_visual_operations_preserve_science_and_registration(client):
    draft = workflow(client)
    base = f"/api/workflows/{draft['id']}"
    reg = client.post(base + '/registrations', json={"expected_revision":0,"operation_id":"visual-reg","node_ids":["rfd-1"]}).json()['registration']
    operations = [{"type":"move_node","node_id":"rfd-1","x":-100,"y":300},
                  {"type":"set_layout","layout":"circle"}]
    preview = client.post(base + '/changes/preview', json={"expected_revision":0,"operation_id":"preview","operations":operations})
    assert preview.status_code == 200
    assert read(client,draft)['draft'] == draft
    result = change(client,draft,operations).json()['state']
    assert result['draft']['nodes'] == draft['nodes']
    assert result['draft']['edges'] == draft['edges']
    assert result['draft']['visual'] == {"layout":"circle","positions":{}}
    assert next(r for r in result['registrations'] if r['id'] == reg['id'])['current']
    assert client.get('/api/graph-contract').json()['changes']['$defs']['AddRelation']


def test_branch_and_feedback_are_distinct_and_atomic(client):
    draft = workflow(client)
    ops = [{"type":"add_node","node_id":"mpnn-branch","model_id":"proteinmpnn","label":"分支设计"},
           {"type":"connect","source":"rfd-1","source_port":"backbone","target":"mpnn-branch","target_port":"backbone"},
           {"type":"add_relation","relation_id":"review","source":"boltz-1","source_port":"confidence","target":"rfd-1","kind":"feedback","label":"评估后重新设计"}]
    response = change(client,draft,ops)
    assert response.status_code == 200
    current = response.json()['state']['draft']
    assert len([e for e in current['edges'] if e['source']=='rfd-1']) == 2
    assert current['nodes'][0]['inputs'] == {}
    base = f"/api/workflows/{draft['id']}"
    registration = client.post(base + '/registrations',json={"expected_revision":1,"operation_id":"feedback-reg","node_ids":["rfd-1"]}).json()['registration']
    request = client.post(base + '/requests',json={"registration_id":registration['id']}).json()['request']
    assert request['design_relations'][0]['id'] == 'review'
    assert 'design_relations_not_executable' in request['blocking_issues']
    invalid = change(client,current,[{"type":"move_node","node_id":"rfd-1","x":20,"y":20},
                                    {**ops[-1],"relation_id":"bad","source_port":"nonexistent"}],operation_id='invalid-visual')
    assert invalid.status_code == 422
    assert read(client,draft)['draft'] == current
    removed = change(client,current,[{"type":"remove_node","node_id":"boltz-1"}],operation_id='remove-visual',confirmed=True)
    assert removed.status_code == 200
    assert removed.json()['state']['draft']['visual']['relations'] == []
