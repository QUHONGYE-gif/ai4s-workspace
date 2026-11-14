"""Find member results and transfer their native AiiDA provenance archives.

Peers are configured by the operator, never by an experiment request. Each peer
queries its own profile; private databases are not mounted in other containers.
"""
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.request import Request, ProxyHandler, build_opener

from aiida import orm
from aiida.tools.archive import create_archive, import_archive
from ai4s_query.candidates import build_candidate
from ai4s_tasks.proteinmpnn_outputs import complete_parameters
from ai4s_workflows.workflows import upstream_problem

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


def file_digest(node):
    with node.open(mode='rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def search_request(code, pdb, inference, filter_params=None):
    return {'model_identity': code.model_identity,
            'code_hash': code.base.caching.compute_hash(),
            'pdb_sha256': file_digest(pdb), 'inference': inference,
            'qualification': {'num_sequences': inference['num_sequences'], **(filter_params or {})}}


def local_candidates(query, profile, member):
    """Use the shared ④ builder, then enforce the actual A-module gate."""
    if not query.get('model_identity'):
        return []
    candidates = []
    rows = orm.QueryBuilder().append(
        orm.CalcJobNode, filters={'process_type': 'aiida.calculations:ai4s.proteinmpnn'}).all()
    for (source,) in rows:
        if source.inputs.code.model_identity != query['model_identity']:
            continue
        if source.inputs.code.base.caching.compute_hash() != query['code_hash']:
            continue
        if complete_parameters(source.inputs.params.get_dict()) != query['inference']:
            continue
        if file_digest(source.inputs.pdb_file) != query['pdb_sha256']:
            continue
        candidate = build_candidate(source, profile, query['qualification'])
        producer = source.base.extras.get('ai4s_requester', {})
        origin = source.base.extras.get('ai4s_origin', {})
        candidate['member'] = origin.get('display_name') or producer.get('display_name') or member
        candidate['origin_profile'] = origin.get('profile', profile)
        if 'result' not in source.outputs:
            candidate.update(qualified=False, reason=candidate['reason'] or 'missing_file: result manifest missing')
        if candidate['qualified']:
            problem = upstream_problem(source.outputs.result, source.inputs.code,
                                       source.inputs.pdb_file, source.inputs.params)
            if problem or not source.base.caching.is_valid_cache:
                candidate.update(qualified=False, reason='format_error: ' + (problem or 'native cache invalid'))
        if candidate.get('fingerprint'):
            candidates.append(candidate)
    return candidates


def export_result(result_uuid, directory):
    """Export one validated calculation, its inputs and all native outputs."""
    result = orm.load_node(uuid=result_uuid)
    source = result.creator
    if not isinstance(result, orm.Dict) or not isinstance(source, orm.CalcJobNode):
        raise ValueError('shared result must be a CalcJob manifest')
    problem = upstream_problem(result, source.inputs.code, source.inputs.pdb_file,
                               source.inputs.params)
    if problem or not source.base.caching.is_valid_cache:
        raise ValueError(problem or 'source is not a valid cache')
    archive_dir = Path(directory) / 'exports'
    archive_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=archive_dir) as temporary:
        path = Path(temporary) / 'result.aiida'
        create_archive([source], filename=path, include_authinfos=False,
                       call_calc_backward=False, call_work_backward=False)
        raw = path.read_bytes()
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError('shared archive exceeds 64 MiB')
    return raw


def peer_request(peer, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(peer['url'].rstrip('/') + path, data=data,
                      headers={'Authorization': 'Bearer ' + peer['token'],
                               'Content-Type': 'application/json'})
    # Container-to-container traffic stays on the configured project network.
    with build_opener(ProxyHandler({})).open(request, timeout=30) as response:
        raw = response.read(MAX_ARCHIVE_BYTES + 1)
        if len(raw) > MAX_ARCHIVE_BYTES:
            raise ValueError('peer response exceeds 64 MiB')
        return raw, response.headers.get('X-Content-SHA256')


def collect_candidates(service, query, policy):
    """Keep rejected candidates visible; only import usable allow_reuse results."""
    candidates = local_candidates(query, service.profile, service.member)
    seen = {(item['uuid'], item['fingerprint']) for item in candidates}
    errors = []
    for peer in service.peers:
        try:
            raw, _ = peer_request(peer, '/api/engine/shared-candidates', query)
            remote = json.loads(raw)['candidates']
        except Exception as error:
            errors.append({'member': peer['member'], 'error': f'{type(error).__name__}: {error}'})
            continue
        for candidate in remote:
            key = (candidate['uuid'], candidate['fingerprint'])
            if key in seen:
                continue
            seen.add(key)
            if candidate['qualified'] and policy == 'allow_reuse':
                try:
                    materialize(service, peer, candidate, query)
                except Exception as error:
                    candidate.update(qualified=False, reason=f'missing_file: archive transfer failed: {error}')
            candidates.append(candidate)
    return candidates, errors


def materialize(service, peer, candidate, query):
    """Import once, then verify UUID, fingerprint, inputs and formal file outputs."""
    transfer_dir = service.directory / 'transfers'
    transfer_dir.mkdir(exist_ok=True)
    raw, expected = peer_request(peer, '/api/engine/archives/' + candidate['uuid'])
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected:
        raise ValueError('archive SHA-256 mismatch')
    with tempfile.TemporaryDirectory(dir=transfer_dir) as temporary:
        path = Path(temporary) / 'result.aiida'
        path.write_bytes(raw)
        import_archive(path, include_authinfos=False, create_group=False)
    result = orm.load_node(uuid=candidate['uuid'])
    source = result.creator
    if source.base.caching.compute_hash() != candidate['fingerprint']:
        raise ValueError('imported native fingerprint mismatch')
    if file_digest(source.inputs.pdb_file) != query['pdb_sha256']:
        raise ValueError('imported PDB mismatch')
    if source.inputs.code.model_identity != query['model_identity']:
        raise ValueError('imported model identity mismatch')
    if source.inputs.code.base.caching.compute_hash() != query['code_hash']:
        raise ValueError('imported Code configuration mismatch')
    problem = upstream_problem(result, source.inputs.code, source.inputs.pdb_file, orm.Dict(dict=query['inference']))
    if problem:
        raise ValueError(problem)
    # AiiDA deliberately omits cached hash extras during archive import. Only
    # index this foreign process after verifying it against this request.
    source.base.caching.rehash()
    source.base.extras.set('ai4s_origin', {'display_name': candidate['member'],
                                        'profile': candidate['origin_profile'], 'peer': peer['member']})
    receipt = {'result_uuid': result.uuid, 'process_uuid': source.uuid, 'peer': peer['member'],
               'sha256': digest, 'size_bytes': len(raw), 'fingerprint': candidate['fingerprint']}
    (transfer_dir / (result.uuid + '.json')).write_text(json.dumps(receipt, indent=2))
