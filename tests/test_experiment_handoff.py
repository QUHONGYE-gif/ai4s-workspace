import copy

from fastapi.testclient import TestClient

from ai4s_demo.app import create_app
from ai4s_demo.handoff import build_workflow, example_workflow


def test_example_reads_model_types_defaults_and_namespaces():
    workflow = example_workflow()
    mpnn = next(s for s in workflow['steps'] if s['model'] == 'proteinmpnn')
    temperature = next(p for p in mpnn['parameters'] if p['modelKey'] == 'sampling_temp')
    assert temperature['key'] == 'mpnn-1__sampling_temp'
    assert temperature['default'] == 0.1
    assert workflow['defaults'][temperature['key']] == 0.1
    filtering = next(s for s in workflow['steps'] if s['model'] == 'sequence_filter')
    assert filtering['deps'] == ['mpnn-1']
    assert filtering['parameters'][0]['category'] == 'filter'
    assert mpnn['inputRequirements'] == {'backbone': 'PDB'}
    analysis = workflow['steps'][-1]
    assert analysis['model'] == 'result_analysis'
    assert analysis['kind'] == 'JSON'
    assert set(analysis['deps']) == {'mpnn-1-filter', 'boltz-1'}
    assert analysis['parameters'] == []
    assert len(workflow['steps']) == 5
    assert all(dep in {s['id'] for s in workflow['steps'][:-1]} for dep in analysis['deps'])


def test_registration_handoff_preserves_source_and_ignores_later_edits(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        state = client.post('/api/workflows', json={'template':'protein'}).json()
        workflow_id = state['draft']['id']
        registration = client.post(f'/api/workflows/{workflow_id}/registrations', json={
            'expected_revision':0, 'operation_id':'register-rfd', 'node_ids':['rfd-1']})
        assert registration.status_code == 200
        response = client.get('/api/experiments/workflows')
        assert response.status_code == 200
        exported = response.json()['workflows'][0]
        original = copy.deepcopy(exported)
        assert exported['registrationSource']['registrationId'] == registration.json()['registration']['id']
        assert exported['defaults']['rfd-1__length'] == 80
        client.post(f'/api/workflows/{workflow_id}/changes', json={
            'expected_revision':0, 'operation_id':'change-length', 'operations':[
                {'type':'update_params','node_id':'rfd-1','changes':{'length':100}}]})
        assert client.get('/api/experiments/workflows').json()['workflows'] == []
        assert original['defaults']['rfd-1__length'] == 80


def test_multiple_model_nodes_have_independent_keys():
    snapshot = {'steps': [{'id': i, 'model_id':'rfdiffusion', 'label':i,
                           'params':{'length':80,'num_designs':1,'rfd_steps':50}, 'inputs':{}}
                          for i in ['rfd-a','rfd-b']]}
    workflow = build_workflow('Two nodes',snapshot,{'kind':'test'})
    assert 'rfd-a__length' in workflow['defaults']
    assert 'rfd-b__length' in workflow['defaults']
