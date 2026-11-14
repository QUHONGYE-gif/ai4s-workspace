from types import SimpleNamespace

from fastapi.testclient import TestClient

from ai4s_demo.app import create_app
from ai4s_demo.models import ChangeAudit
from ai4s_demo.policy import PolicyReply
from ai4s_demo.policy_simulation import simulate
from ai4s_engine.policy import read_policy


def test_confirmation_persists_exact_config_and_preserves_audit_on_undo(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        state = client.get("/api/policy").json()
        updated = state["config"] | {
            "reuse_policy": "force_rerun",
            "transfer_limit_seconds": 5,
            "storage_limit_bytes": 7_000_000,
            "retention": "cost",
        }
        preview = client.post("/api/policy/preview", json={"expected_revision": 0, "config": updated})
        proposal = preview.json()["proposal"]
        assert read_policy(tmp_path)["config"] == state["config"]
        request = {"expected_revision": 0, "proposal_id": proposal["id"]}
        assert client.post("/api/policy/confirm", json=request).status_code == 200
        assert client.post("/api/policy/confirm", json=request).json()["revision"] == 1
        assert read_policy(tmp_path)["config"] == updated
        assert client.post("/api/policy/preview", json={"expected_revision": 0, "config": updated}).status_code == 409
        simulation = client.get("/api/policy/simulation").json()
        allowed = updated | {"reuse_policy": "allow_reuse"}
        assert simulate(allowed)["action"] == "rerun"
        assert simulate(allowed | {"transfer_limit_seconds": 6})["action"] == "reuse"
        assert simulate(allowed | {"retention": "lru"})["evicted"] == ["示例 A"]
        assert (simulation["revision"], simulation["action"], simulation["evicted"]) == (1, "rerun", ["示例 B"])
        undo = client.post("/api/policy/undo-preview", json={"expected_revision": 1}).json()["proposal"]
        reverted = client.post("/api/policy/confirm", json={"expected_revision": 1, "proposal_id": undo["id"]}).json()
        assert reverted["config"] == state["config"]
        assert [event["source"] for event in reverted["history"]] == ["manual", "undo"]
        assert reverted["history"][0]["actor"] == state["actor"]


def test_agent_answers_cannot_write_and_changes_wait_for_confirmation(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    replies = iter([
        PolicyReply(intent="answer", reply="解释", changes={"reuse_policy": "force_rerun"}),
        PolicyReply(intent="change", reply="提案", changes={"reuse_policy": "force_rerun"}),
        ChangeAudit(explicit_request=True, complete_and_consistent=True, reason="明确要求修改"),
    ])

    async def run(*args, **kwargs):
        return next(replies), dict(requests=1, input_tokens=1, output_tokens=1, elapsed_seconds=0.1)

    monkeypatch.setattr(app.state.gateway, "_model", lambda: SimpleNamespace())
    monkeypatch.setattr("ai4s_demo.policy.Agent", lambda *args, **kwargs: object())
    monkeypatch.setattr(app.state.gateway, "_run", run)
    with TestClient(app) as client:
        question = client.post("/api/policy/messages", json={"expected_revision": 0, "message": "强制重算是什么？"})
        assert question.json()["proposal"] is None
        proposed = client.post("/api/policy/messages", json={"expected_revision": 0, "message": "默认改成强制重算"})
        proposal = proposed.json()["proposal"]
        assert proposal["diff"] == [{"field": "reuse_policy", "before": "allow_reuse", "after": "force_rerun"}]
        assert read_policy(tmp_path)["revision"] == 0
        assert client.post("/api/policy/confirm", json={"expected_revision": 0, "proposal_id": proposal["id"]}).status_code == 200
        assert read_policy(tmp_path)["history"][0]["source"] == "agent"
