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


def invoke(decision, extra_context=None):
    request = ExperimentChat(message="把筛选数量改成3条", context={"selectedNode": {
        "id": "filter", "parameters": [{"key": "count", "type": "number", "min": 1, "max": 5, "step": 1}],
        "values": {"count": 5}}})
    request.context.update(extra_context or {})
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


def test_snapshot_is_read_only():
    with pytest.raises(Problem):
        invoke({'intent':'change','reply':'修改','operations':[
            {'type':'update_params','node_id':'filter','changes':{'count':3}}]}, {'readOnly':True})


def test_rescreen_targets_only_filter_and_selected_sequence():
    decision = {'intent':'change','reply':'新筛选草稿','operations':[
        {'type':'create_experiment_draft','node_id':'filter','input_artifact_id':'ART-1'}]}
    context = {'currentArtifact':{'id':'ART-1','kind':'FASTA'},'availableFilterNodes':[{'id':'filter'}]}
    result = invoke(decision, context)
    assert result['operations'][0]['requestedStepIds'] == ['filter']
    assert result['operations'][0]['intent'] == 'replay'
    with pytest.raises(Problem):
        invoke(decision, {**context, 'currentArtifact':{'id':'ART-other','kind':'FASTA'}})


def test_experiment_route_uses_the_existing_gateway_and_settings(tmp_path):
    from fastapi.testclient import TestClient
    from ai4s_demo.app import create_app
    class SharedGateway(Gateway):
        def __init__(self, settings, service):
            super().__init__(DraftDecision(intent='answer', reply='共用模型配置'))
            self.settings = settings
            self.models = []
        def _model(self):
            self.models.append(self.settings.public()['model'])
            return None
    app = create_app(tmp_path, gateway_factory=SharedGateway)
    with patch('ai4s_demo.experiment_agent.Agent'), TestClient(app) as client:
        client.post('/api/settings/model', json={'model': 'shared-test-model', 'api_key': 'test-key'})
        response = client.post('/api/experiments/messages', json={'message': '解释当前参数', 'context': {}})
        assert response.status_code == 200
        assert response.json()['reply'] == '共用模型配置'
        assert app.state.gateway.models == ['shared-test-model']
        assert 'test-key' not in response.text
