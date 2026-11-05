import asyncio
from unittest.mock import patch

import pytest

from ai4s_demo.experiment_agent import DraftDecision, ExperimentChat, respond
from ai4s_demo.storage import Problem


class Gateway:
    def __init__(self, decision):
        self.decision = decision

    def _model(self):
        return None

    def _settings(self):
        return {}

    async def _run(self, *args, **kwargs):
        return self.decision, {"provider": "test"}


def invoke(decision):
    request = ExperimentChat(message="把筛选数量改成3条", context={"selectedNode": {
        "id": "filter", "parameters": [{"key": "count", "type": "number", "min": 1, "max": 5, "step": 1}],
        "values": {"count": 5}}})
    with patch("ai4s_demo.experiment_agent.Agent"):
        return asyncio.run(respond(Gateway(DraftDecision.model_validate(decision)), request))


def test_change_keeps_old_value_and_live_mode():
    result = invoke({"intent": "change", "reply": "改为3", "operations": [
        {"type": "update_params", "node_id": "filter", "changes": {"count": 3}}]})
    assert result["operations"][0]["old_values"] == {"count": 5}
    assert result["mode"] == "live"


@pytest.mark.parametrize("changes", [{"unknown": 3}, {"count": 50}, {"count": 1.5}, {"count": True}])
def test_invalid_proposals_are_rejected(changes):
    with pytest.raises(Problem):
        invoke({"intent": "change", "reply": "修改", "operations": [
            {"type": "update_params", "node_id": "filter", "changes": changes}]})


def test_answer_cannot_modify_draft():
    result = invoke({"intent": "answer", "reply": "解释", "operations": [
        {"type": "update_params", "node_id": "filter", "changes": {"count": 3}}]})
    assert result["operations"] == []
