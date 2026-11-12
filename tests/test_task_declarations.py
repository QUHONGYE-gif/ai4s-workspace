"""Contract ① integrity and proposal isolation; fake models never call a paid API."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from ai4s_declarations import (
    DeclarationError,
    DeclarationRegistry,
    validate_declaration,
)
from ai4s_declarations.registry import validate_values
from ai4s_demo.app import create_app

REGISTRY = Path(__file__).resolve().parents[1] / "configs/task_declarations"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    app = create_app(tmp_path)
    app.state.gateway.settings.private = lambda: {"model": "test", "api_key": ""}
    with TestClient(app) as test_client:
        yield test_client


def create(client, template="empty"):
    response = client.post("/api/declaration-drafts", json={"template": template})
    assert response.status_code == 201
    return response.json()


def request(state, **extra):
    return {"expected_revision": state["revision"], "operation_id": "op-test", **extra}


def endpoint(state, suffix=""):
    return "/api/declaration-drafts/" + state["id"] + ("/" + suffix if suffix else "")


def preview(client, state, declaration, **extra):
    return client.post(
        endpoint(state, "preview"),
        json=request(state, declaration=declaration, **extra),
    )


def test_published_definition_matches_contract_appendix():
    document = DeclarationRegistry(REGISTRY).get()
    assert validate_declaration(document) == []
    markdown = (REGISTRY.parents[1] / "docs/task_declaration_contract.md").read_text()
    # Independent delivery copies must agree, rather than checking UI-generated evidence.
    appendix = markdown.rsplit("```json", 1)[1].split("```", 1)[0]
    assert json.loads(appendix) == document
    document["parameters"]["inference"].clear()
    assert (
        DeclarationRegistry(REGISTRY).get()["parameters"]["inference"]["seed"][
            "minimum"
        ]
        == 1
    )


def test_registration_catalog_does_not_claim_execution(client):
    catalog = client.get("/api/task-catalog").json()
    assert catalog["engine_status"] == "not_connected"
    assert [task["task_id"] for task in catalog["tasks"]] == ["proteinmpnn"]
    version = catalog["tasks"][0]["versions"][0]
    assert version["definition_status"] == "repository_loaded"
    assert version["adapter_status"] == "source_supported"
    assert version["web_execution_connected"] is False
    assert {task["task_id"] for task in catalog["planned"]} == {"rfdiffusion", "boltz", "mmseqs2"}
    before = client.get("/api/declaration-drafts").json()
    for task_id, version in [("boltz", "1"), ("proteinmpnn", "999")]:
        response = client.post("/api/declaration-drafts", json={"task_id": task_id, "version": version})
        assert response.status_code == 422
    assert client.get("/api/declaration-drafts").json() == before


def test_export_status_is_tied_to_exact_draft_revision(client):
    state = create(client, "complete")
    assert state["reference"] == {"task_id": "proteinmpnn", "version": "1"}
    assert state["status"] == "draft"
    exported = client.post(endpoint(state, "export"), json=request(state))
    assert exported.status_code == 200
    listed = client.get("/api/declaration-drafts").json()["drafts"][0]
    assert listed["task_id"] == "proteinmpnn"
    assert listed["version"] == "1"
    assert listed["status"] == "exported_not_deployed"
    assert listed["issue_count"] == 0
    updated = copy.deepcopy(state["declaration"])
    updated["version"] = "2"
    proposal = preview(client, state, updated).json()["proposal"]
    confirmed = client.post(endpoint(state, "confirm"), json=request(state, proposal_id=proposal["id"], operation_id="confirm-version"))
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "draft"
    assert confirmed.json()["reference"]["version"] == "1"
    assert client.get("/api/task-declarations/proteinmpnn/1").json() == state["declaration"]


@pytest.mark.parametrize("kind", ["invalid", "duplicate_key", "wrong_path", "missing"])
def test_registry_fails_closed(tmp_path, kind):
    directory = tmp_path / "proteinmpnn"
    directory.mkdir()
    document = DeclarationRegistry(REGISTRY).get()
    path = directory / "1.json"
    if kind == "invalid":
        document["outputs"]["selected_sequences"]["aiida_type"] = "SinglefileData"
    if kind == "wrong_path":
        path = directory / "2.json"
    text = json.dumps(document)
    if kind == "duplicate_key":
        text = text.replace(
            '"task_id": "proteinmpnn"', '"task_id": "other", "task_id": "proteinmpnn"'
        )
    if kind != "missing":
        path.write_text(text)
    with pytest.raises(DeclarationError):
        DeclarationRegistry(tmp_path)


@pytest.mark.parametrize(
    "changes",
    [
        {"seed": 0},
        {"seed": True},
        {"seed": 1.0},
        {"seed": "41"},
        {"sampling_temperature": 0},
        {"sampling_temperature": float("inf")},
        {"num_sequences": 3, "batch_size": 2},
        {"chains": "  "},
        {"sampling_temp": 0.1},
    ],
)
def test_inference_rejects_illegal_values(changes):
    values = {
        "chains": "A",
        "num_sequences": 4,
        "sampling_temperature": 0.1,
        "seed": 41,
    }
    assert validate_values({**values, **changes}, "inference")


def test_filter_has_no_invented_bounds_and_unknowns_are_rejected():
    assert validate_values({"score_threshold": 2.1, "top_k": 100}, "filter") == []
    assert validate_values({"score_threshold": -0.5, "top_k": 1}, "filter") == []
    assert validate_values({"score_threshold": 0.82, "top_k": True}, "filter")
    assert validate_values({"score_threshold": 0.82, "top_k": 2, "extra": 1}, "filter")


def test_confirm_is_only_write_and_is_idempotent(client):
    state = create(client)
    complete = client.get("/api/task-declarations/proteinmpnn/1").json()
    response = preview(client, state, complete)
    assert response.status_code == 200, response.text
    proposal = response.json()["proposal"]
    assert client.get(endpoint(state)).json()["declaration"] == state["declaration"]
    assert preview(client, state, complete).json()["proposal"]["id"] == proposal["id"]
    altered = copy.deepcopy(complete)
    altered["name"] = "另一个名称"
    assert preview(client, state, altered).status_code == 409
    body = request(state, proposal_id=proposal["id"], operation_id="confirm-1")
    confirmed = client.post(endpoint(state, "confirm"), json=body)
    assert confirmed.status_code == 200
    assert confirmed.json()["revision"] == 1
    assert confirmed.json()["declaration"] == complete
    assert client.post(endpoint(state, "confirm"), json=body).json()["revision"] == 1
    exported = client.post(endpoint(state, "export"), json=request(confirmed.json()))
    assert exported.json()["declaration"] == complete
    assert exported.json()["status"] == "exported_not_deployed"
    assert (
        exported.json()["deployment_path"]
        == "configs/task_declarations/proteinmpnn/1.json"
    )


def test_cancel_stale_and_invalid_edits_are_atomic(client):
    state = create(client)
    assert (
        client.post(endpoint(state, "export"), json=request(state)).status_code == 422
    )
    complete = client.get("/api/task-declarations/proteinmpnn/1").json()
    invalid = copy.deepcopy(complete)
    invalid["example"]["params"]["inference"]["seed"] = 0
    invalid["name"] = "不能部分保存"
    assert preview(client, state, invalid).status_code == 422
    assert client.get(endpoint(state)).json()["declaration"] == state["declaration"]
    one = preview(client, state, complete).json()["proposal"]
    two = preview(client, state, complete, operation_id="preview-2").json()["proposal"]
    cancelled = client.post(
        endpoint(state, "cancel"), json=request(state, proposal_id=one["id"])
    )
    assert cancelled.json()["revision"] == 0
    assert (
        client.post(
            endpoint(state, "confirm"),
            json=request(state, proposal_id=one["id"], operation_id="apply-cancelled"),
        ).status_code
        == 409
    )
    changed = client.post(
        endpoint(state, "confirm"),
        json=request(state, proposal_id=two["id"], operation_id="apply-2"),
    ).json()
    assert (
        preview(client, state, complete, operation_id="stale-edit").status_code == 409
    )
    assert changed["revision"] == 1


def test_same_published_version_is_immutable(client):
    state = create(client, "complete")
    modified = copy.deepcopy(state["declaration"])
    modified["name"] = "团队显示名"
    p = preview(client, state, modified).json()["proposal"]
    state = client.post(
        endpoint(state, "confirm"), json=request(state, proposal_id=p["id"])
    ).json()
    assert (
        client.post(endpoint(state, "export"), json=request(state)).status_code == 409
    )
    modified["version"] = "2"
    p = preview(client, state, modified, operation_id="preview-v2").json()["proposal"]
    state = client.post(
        endpoint(state, "confirm"),
        json=request(state, proposal_id=p["id"], operation_id="confirm-v2"),
    ).json()
    assert (
        client.post(endpoint(state, "export"), json=request(state))
        .json()["deployment_path"]
        .endswith("/2.json")
    )
    assert (
        client.get("/api/task-declarations/proteinmpnn/2").status_code == 404
    )  # export isn't deployment


def test_real_definition_restore_handles_dotted_ports_and_source_conflict(client):
    from ai4s_demo.declarations import DefinitionEdit

    service = client.app.state.declarations
    state = create(client)
    restored = service.candidate(
        state["declaration"],
        [DefinitionEdit(action="restore", path="outputs.artifacts.sequences")],
    )
    assert restored["outputs"]["artifacts.sequences"]["aiida_type"] == "SinglefileData"
    with pytest.raises(Exception, match="原文依据"):
        service.candidate(
            state["declaration"],
            [DefinitionEdit(action="set", path="name", value="x")],
            "unrelated text",
        )


def test_agent_q_and_a_never_mutates_and_change_only_proposes(client):
    state = create(client)
    gateway = client.app.state.gateway
    output = {"intent": "answer", "reply": "种子必须大于0", "edits": []}
    gateway._model = lambda: TestModel(call_tools=[], custom_output_args=output)
    response = client.post(
        endpoint(state, "messages"), json=request(state, message="为什么种子不能为0")
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"]["declaration"] == state["declaration"]
    output.update(
        intent="change", reply="请确认", edits=[{"action": "restore", "path": "inputs"}]
    )
    models = iter(
        [
            TestModel(call_tools=[], custom_output_args=output),
            TestModel(
                call_tools=[],
                custom_output_args={
                    "explicit_request": True,
                    "complete_and_consistent": True,
                    "reason": "明确补齐输入",
                },
            ),
        ]
    )
    gateway._model = lambda: next(models)
    body = request(state, message="补齐真实输入定义", operation_id="agent-change")
    result = client.post(endpoint(state, "messages"), json=body)
    assert result.status_code == 200, result.text
    assert result.json()["message"]["proposal"]["diff"][0]["path"] == "inputs.pdb_file"
    assert result.json()["state"]["declaration"] == state["declaration"]
    assert client.post(endpoint(state, "messages"), json=body).json() == result.json()


def test_new_drafts_do_not_change_old_workflows_and_prefix_assets(client):
    legacy = client.post("/api/workflows", json={}).json()
    create(client)
    assert (
        client.get("/api/workflows/" + legacy["draft"]["id"]).json()["draft"]
        == legacy["draft"]
    )
    assert client.get("/assets/declaration.js").status_code == 200
    assert client.get("/assets/declaration.css").status_code == 200
    assert (
        client.get("/api/task-declarations/unknown/1").json()["error"]
        == "invalid_declaration"
    )


def test_restore_only_fills_missing_and_preserves_user_edits(client):
    from ai4s_demo.declarations import DefinitionEdit

    state = create(client, "complete")
    document = state["declaration"]
    document["parameters"]["inference"]["chains"]["label"] = "团队自定义链名称"
    del document["parameters"]["inference"]["seed"]
    service = client.app.state.declarations
    candidate = service.candidate(
        document, [DefinitionEdit(action="restore", path="parameters")]
    )
    assert candidate["parameters"]["inference"]["chains"]["label"] == "团队自定义链名称"
    assert candidate["parameters"]["inference"]["seed"]["minimum"] == 1


@pytest.mark.parametrize("approved", [False, True])
def test_agent_rejects_incomplete_or_illegal_batch_without_partial_save(
    client, approved
):
    state = create(client, "complete")
    gateway = client.app.state.gateway
    models = iter(
        [
            TestModel(
                call_tools=[],
                custom_output_args={
                    "intent": "change",
                    "reply": "修改提案",
                    "edits": [
                        {
                            "action": "set",
                            "path": "example.params.inference.sampling_temperature",
                            "value": 0.2,
                        },
                        {
                            "action": "set",
                            "path": "example.params.inference.seed",
                            "value": 0,
                        },
                    ],
                },
            ),
            TestModel(
                call_tools=[],
                custom_output_args={
                    "explicit_request": True,
                    "complete_and_consistent": approved,
                    "reason": "必须整批合法",
                },
            ),
        ]
    )
    gateway._model = lambda: next(models)
    response = client.post(
        endpoint(state, "messages"),
        json=request(state, message="示例温度改0.2，种子改0"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["message"]["intent"] == "clarify"
    assert "proposal" not in response.json()["message"]
    assert response.json()["state"]["revision"] == 0
    assert response.json()["state"]["declaration"] == state["declaration"]


@pytest.mark.parametrize("kind", ["declaration-drafts", "workflows"])
def test_deleted_drafts_are_isolated_recoverable_and_revision_protected(client, kind):
    payload = {"template": "complete"} if kind == "declaration-drafts" else {"template": "protein"}
    first = client.post(f"/api/{kind}", json=payload).json()
    second = client.post(f"/api/{kind}", json=payload).json()
    body = first if kind == "declaration-drafts" else first["draft"]
    other = second if kind == "declaration-drafts" else second["draft"]
    url = f"/api/{kind}/{body['id']}"
    published = client.get("/api/task-declarations/proteinmpnn/1").json()
    request_body = {"expected_revision": body["revision"] + 1, "operation_id": "delete-record"}
    assert client.post(url + "/delete", json=request_body).status_code == 409
    assert client.get(url).status_code == 200
    request_body["expected_revision"] = body["revision"]
    removed = client.post(url + "/delete", json=request_body)
    assert removed.status_code == 200
    assert client.get(url).status_code == 404
    list_key = "drafts" if kind == "declaration-drafts" else "workflows"
    assert [item["id"] for item in client.get(f"/api/{kind}").json()[list_key]] == [other["id"]]
    trash = client.get(f"/api/{kind}?deleted=true").json()[list_key]
    assert len(trash) == 1 and trash[0]["id"] == body["id"]
    # Deleted records cannot be edited or exported by stale pages.
    suffix = "export" if kind == "declaration-drafts" else "undo"
    assert client.post(url + "/" + suffix, json=request_body).status_code == 404
    assert client.post(url + "/restore", json=request_body).status_code == 409
    request_body["expected_revision"] = removed.json()["revision"]
    assert client.post(url + "/restore", json=request_body).status_code == 200
    restored = client.get(url).json()
    restored_body = restored if kind == "declaration-drafts" else restored["draft"]
    assert restored_body["revision"] == body["revision"] + 2
    if kind == "declaration-drafts":
        assert restored["declaration"] == first["declaration"]
        assert restored["reference"] == first["reference"]
    else:
        for key in ("nodes", "edges", "name"):
            assert restored_body[key] == body[key]
    assert client.get(f"/api/{kind}?deleted=true").json()[list_key] == []
    assert client.get("/api/task-declarations/proteinmpnn/1").json() == published
    assert client.get(f"/api/{kind}/{other['id']}").json() == second
