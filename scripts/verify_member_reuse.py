"""Verify real reuse through two member HTTP services and independent profiles.

Run with an operator-owned private config containing source/target objects with
url and token fields. Existing evidence is never overwritten. Actual requests,
states, decisions and downloaded file hashes are retained, excluding tokens.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.error import URLError
from urllib.request import Request, ProxyHandler, build_opener
from uuid import uuid4


def call(peer, path, payload=None, *, binary=False):
    request = Request(peer['url'].rstrip('/') + '/api/engine/' + path,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Authorization': 'Bearer ' + peer['token'], 'Content-Type': 'application/json'})
    with build_opener(ProxyHandler({})).open(request, timeout=90) as response:
        raw = response.read()
    return raw if binary else json.loads(raw)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def wait_health(peer):
    deadline = time.monotonic() + 90
    while True:
        try:
            return call(peer, 'health')
        except URLError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--pdb', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=41)
    parser.add_argument('--resume', type=Path, help='Reuse the previous run ID and uploads; write a new evidence file')
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    config = json.loads(args.config.read_text())
    source, target = config['source'], config['target']
    evidence = {'status': 'running', 'run_id': str(uuid4()), 'requests': {}, 'runs': {}, 'checks': {}}
    previous = json.loads(args.resume.read_text()) if args.resume else None
    if previous:
        require(previous['requests']['source']['params']['inference']['seed'] == args.seed, 'resume seed differs')
        evidence['run_id'] = previous['run_id']
        evidence['resumed_from'] = args.resume.name

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))

    def execute(label, peer, upload, policy, workflow='mpnn_filter', threshold=10.0, model='v_48_020'):
        params = {'inference': {'chains': 'A', 'num_sequences': 4, 'sampling_temperature': 0.1,
                                'seed': args.seed, 'model_name': model, 'batch_size': 1, 'save_probabilities': True}}
        if workflow == 'mpnn_filter':
            params['filter'] = {'score_threshold': threshold, 'top_k': 2}
        payload = {'schema_version': 'ai4s-request-1', 'client_ref': evidence['run_id'] + ':' + label,
                   'requester': peer['requester'], 'declaration': {'task_id': 'proteinmpnn', 'version': '1'},
                   'workflow': workflow, 'inputs': {'pdb_file': {'source': 'upload', 'upload_id': upload['upload_id']}},
                   'params': params, 'reuse_policy': policy}
        evidence['requests'][label] = payload
        result = call(peer, 'requests', payload)
        evidence['runs'][label] = result
        save()
        deadline = time.monotonic() + 900
        while result['state'] not in ('finished', 'failed'):
            require(time.monotonic() < deadline, label + ' timed out')
            time.sleep(2)
            result = call(peer, 'requests/' + result['request_id'])
            evidence['runs'][label] = result
            save()
        evidence['runs'][label]['records'] = call(peer, 'decisions?request_id=' + result['request_id'])['records']
        save()
        print(label, result['state'], result['decision'], flush=True)
        return result

    try:
        save()
        evidence['source_health'] = wait_health(source)
        evidence['target_health'] = wait_health(target)
        require(evidence['source_health']['profile'] != evidence['target_health']['profile'], 'profiles must differ')
        require(all(evidence[key]['aiida_version'] == '2.9.4+ai4s.2'
                    for key in ('source_health', 'target_health')), 'unified kernel required')
        source_upload = (previous['uploads']['source'] if previous else
                         call(source, 'uploads', {'filename': args.pdb.name, 'content': args.pdb.read_text()}))
        target_upload = (previous['uploads']['target'] if previous else
                         call(target, 'uploads', {'filename': args.pdb.name, 'content': args.pdb.read_text()}))
        evidence['uploads'] = {'source': source_upload, 'target': target_upload}
        first = execute('source', source, source_upload, 'force_rerun', workflow='single')
        require(first['state'] == 'finished', 'source model failed')
        reused = execute('cross_member_filter', target, target_upload, 'allow_reuse')
        require(reused['state'] == 'finished', 'cross-member filtering failed')
        require(reused['decision']['action'] == 'reuse', 'remote candidate not reused')
        require(reused['cached_from'] == first['process']['uuid'], 'wrong source process')
        require(reused['execution']['calcjobs'] == [], 'reuse launched a CalcJob')
        require(reused['execution']['selection_report']['selected_count'] == 2, 'filter output differs')
        require(reused['records'][0]['final_decision']['selected_candidate_uuid'] == first['outputs']['result'],
                'wrong selected manifest')
        evidence['checks']['cross_member_filter'] = 'passed'
        hashes = {}
        for port, node_uuid in first['outputs']['artifacts'].items():
            original = call(source, 'files/' + node_uuid, binary=True)
            received = call(target, 'files/' + reused['outputs']['artifacts'][port], binary=True)
            require(original == received, 'transferred file differs: ' + port)
            hashes[port] = hashlib.sha256(received).hexdigest()
        evidence['file_sha256'] = hashes
        require(len(hashes) == 3, 'missing formal file output')
        cached = execute('cross_member_single', target, target_upload, 'allow_reuse', workflow='single')
        require(cached['state'] == 'finished' and cached['cached_from'] == first['process']['uuid'],
                'native cross-member cache failed')
        require(cached['effective']['fingerprint'] == first['effective']['fingerprint'], 'native hashes differ')
        evidence['checks']['cross_member_single'] = 'passed'
        for label, policy in [('force', 'force_rerun'), ('new_sample', 'new_sample')]:
            run = execute(label, target, target_upload, policy)
            require(run['state'] == 'finished' and len(run['execution']['calcjobs']) == 1, label + ' did not execute')
            require(run['execution']['calcjobs'][0]['cache_source'] is None, label + ' used cache')
            require((run['effective']['seed'] == args.seed) == (label == 'force'), 'effective seed differs')
            evidence['checks'][label] = 'passed'
        rejected = execute('below_threshold', target, target_upload, 'allow_reuse', threshold=-1.0)
        record = rejected['records'][0]
        require(record['final_decision']['action'] == 'rerun', 'unqualified result reused')
        require(record['candidate_compare_list'] and all(not candidate['qualified']
                for candidate in record['candidate_compare_list']), 'rejected candidates not retained')
        require(all(candidate['reason'].startswith('below_threshold:')
                    for candidate in record['candidate_compare_list']), 'threshold reasons missing')
        evidence['checks']['below_threshold'] = 'passed'
        changed = execute('changed_weights', target, target_upload, 'allow_reuse', model='v_48_030')
        require(changed['state'] == 'finished' and changed['decision']['action'] == 'rerun', 'changed weights reused')
        require(changed['effective']['identity_digest'] != first['effective']['identity_digest'], 'weights identity unchanged')
        evidence['checks']['changed_weights'] = 'passed'
        evidence['status'] = 'passed'
    except Exception as error:
        evidence['status'] = 'failed'
        evidence['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
