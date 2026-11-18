import copy

from fastapi.testclient import TestClient

from ai4s_demo.app import create_app
from ai4s_demo.catalog import CATALOG
from ai4s_demo.handoff import build_workflow


def catalog_snapshot():
    """Three-model chain whose parameters come from the registered catalog."""
    nodes = []
    for model_id, node_id in (("rfdiffusion", "rfd-1"), ("proteinmpnn", "mpnn-1"), ("boltz", "boltz-1")):
        nodes.append({"id": node_id, "model_id": model_id, "label": CATALOG[model_id]["role"],
                      "params": copy.deepcopy(CATALOG[model_id]["sample_params"]), "inputs": {}})
    nodes[1]["inputs"] = {"backbone": {"kind": "node_output", "node_id": "rfd-1", "port": "backbone"}}
    nodes[2]["inputs"] = {"sequence": {"kind": "node_output", "node_id": "mpnn-1", "port": "sequences"}}
    return {"steps": nodes}


def test_handoff_reads_model_types_defaults_and_namespaces():
    workflow = build_workflow("模型参数体验流程", catalog_snapshot(), {"kind": "test"})
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


def test_input_identity_tracks_content_record_and_chain_policy():
    snapshot = catalog_snapshot()
    snapshot['steps'] = [snapshot['steps'][1]]
    node = snapshot['steps'][0]
    node['inputs'] = {'backbone': {'kind': 'file', 'file_id': 'upload-a'}}
    node['design_chain_policy'] = {'mode': 'selected', 'chains': ['A']}
    metadata = {'upload-a': {'sha256': 'a' * 64, 'format': 'PDB'},
                'upload-same': {'sha256': 'a' * 64, 'format': 'PDB'},
                'upload-other': {'sha256': 'b' * 64, 'format': 'PDB'}}
    first = build_workflow('A', snapshot, {}, metadata.__getitem__)['steps'][0]
    node['inputs']['backbone']['file_id'] = 'upload-same'
    same = build_workflow('Renamed', snapshot, {}, metadata.__getitem__)['steps'][0]
    assert first['inputIdentity'] == same['inputIdentity']
    node['inputs']['backbone']['file_id'] = 'upload-other'
    other = build_workflow('B', snapshot, {}, metadata.__getitem__)['steps'][0]
    assert first['inputIdentity'] != other['inputIdentity']
    assert first['chainPolicy'] == {'mode': 'selected', 'chains': ['A']}
    assert first['inputs']['backbone']['file_id'] == 'upload-a'
    node['inputs'] = {'sequence': {'kind': 'file', 'file_id': 'upload-a', 'record_id': 'record-2'}}
    record = build_workflow('Record', snapshot, {}, metadata.__getitem__)['steps'][0]
    assert record['inputIdentity']['sequence']['record_id'] == 'record-2'


def test_synthetic_ids_reserve_all_user_nodes_and_expanded_limit():
    import pytest
    from ai4s_demo.storage import Problem
    snapshot = catalog_snapshot()
    snapshot['steps'][0]['id'] = 'mpnn-1-filter'
    snapshot['steps'][1]['inputs']['backbone']['node_id'] = 'mpnn-1-filter'
    snapshot['steps'][2]['id'] = 'result-analysis'
    workflow = build_workflow('Collisions', snapshot, {})
    ids = [s['id'] for s in workflow['steps']]
    assert len(ids) == len(set(ids))
    assert next(s for s in workflow['steps'] if s['model'] == 'sequence_filter')['id'] == 'mpnn-1-filter-2'
    assert workflow['steps'][-1]['id'] == 'result-analysis-2'
    template = snapshot['steps'][0]
    snapshot = {'steps': [{**copy.deepcopy(template), 'id': f'rfd-{i}'} for i in range(12)]}
    assert len(build_workflow('Twelve', snapshot, {})['steps']) == 13
    snapshot['steps'] = [{**copy.deepcopy(template), 'id': f'rfd-{i}'} for i in range(64)]
    with pytest.raises(Problem, match='64'):
        build_workflow('Too large', snapshot, {})


def test_handoff_rechecks_uploaded_bytes(tmp_path):
    from ai4s_demo.files import upload
    from ai4s_demo.handoff import registrations
    from ai4s_demo.models import ChangeRequest, CreateWorkflow, RegisterRequest
    from ai4s_demo.service import WorkflowService
    from ai4s_demo.storage import Store, Problem
    import pytest
    service = WorkflowService(Store(tmp_path))
    data = b'ATOM      1  CA  ALA A   1       1.000   2.000   3.000  1.00 20.00           C  \nEND\n'
    file = upload(service.store, 'input.pdb', data)
    state = service.create(CreateWorkflow(name='File input', template='empty'))
    workflow_id = state['draft']['id']
    state = service.change(workflow_id, ChangeRequest.model_validate({'expected_revision': 0,
        'operation_id': 'setup', 'operations': [
            {'type': 'add_node', 'node_id': 'mpnn', 'model_id': 'proteinmpnn', 'label': 'MPNN'},
            {'type': 'set_input', 'node_id': 'mpnn', 'port': 'backbone', 'value': {'kind': 'file', 'file_id': file['id']}},
            {'type': 'set_chains', 'node_id': 'mpnn', 'policy': {'mode': 'all', 'chains': []}}]}))['state']
    service.register(workflow_id, RegisterRequest(expected_revision=state['draft']['revision'], operation_id='register', node_ids=['mpnn']))
    assert registrations(service)[0]['steps'][0]['inputIdentity']['backbone']['sha256'] == file['sha256']
    (tmp_path / 'uploads' / file['id']).write_bytes(b'changed')
    with pytest.raises(Problem, match='内容已变化'):
        registrations(service)
