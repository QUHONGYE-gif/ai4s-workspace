"""Agreement-2 requests, persistent idempotency and native AiiDA submission.

The HTTP server serializes ORM access because AiiDA's manager is process-global.
The daemon executes processes independently; HTTP polling only reads native state.
"""
import hashlib
import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from aiida import orm
from aiida.engine import submit
from aiida.manage import get_manager
from aiida.plugins import CalculationFactory, WorkflowFactory
from ai4s_declarations.registry import DeclarationRegistry, validate_values
from ai4s_tasks.proteinmpnn_outputs import complete_parameters, parameter_problem
from ai4s_workflows.decision import default_seed_factory, find_decisions_by_request, validate_reuse_policy
from .identity import identity_digest, resolve_identity
from .policy import read_policy


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class RequestError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class EngineService:
    def __init__(self, directory, declarations, model_root='/opt/ai4s/proteinmpnn', *, member=None, peers=(), policy_data=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.uploads = self.directory / 'uploads'
        self.uploads.mkdir(exist_ok=True)
        self.registry = DeclarationRegistry(declarations)
        self.model_root = model_root
        self.policy_data = policy_data
        self.profile = get_manager().get_profile().name
        self.member = member or self.profile
        self.peers = list(peers)
        self.db = sqlite3.connect(self.directory / 'requests.sqlite')
        self.db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, member TEXT, client_ref TEXT, payload TEXT, status TEXT, UNIQUE(member, client_ref))')
        self.db.commit()

    def health(self):
        import aiida
        from aiida.engine.daemon.client import get_daemon_client
        running = get_daemon_client().is_daemon_running
        return {'status': 'ok' if running else 'unavailable', 'profile': self.profile,
                'aiida_version': aiida.__version__, 'daemon_running': running,
                'member': self.member, 'peers': [peer['member'] for peer in self.peers]}

    def upload(self, filename, content):
        if not isinstance(filename, str) or not filename.lower().endswith('.pdb'):
            raise RequestError('input_not_found', '请选择 PDB 文件')
        if not content or len(content) > 1024 * 1024:
            raise RequestError('input_not_found', 'PDB must contain 1–1048576 bytes')
        if b'ATOM  ' not in content:
            raise RequestError('input_not_found', 'PDB does not contain ATOM records')
        upload_id = 'up-' + str(uuid4())
        (self.uploads / upload_id).write_bytes(content)
        return {'upload_id': upload_id, 'sha256': hashlib.sha256(content).hexdigest(), 'size_bytes': len(content)}

    def _input(self, reference):
        if not isinstance(reference, dict):
            raise RequestError('input_not_found', 'PDB reference must be an object')
        if reference.get('source') == 'upload':
            upload_id = reference.get('upload_id', '')
            try:
                UUID(upload_id.removeprefix('up-'))
            except ValueError:
                raise RequestError('input_not_found', 'invalid upload_id')
            path = self.uploads / upload_id
            if not path.is_file():
                raise RequestError('input_not_found', 'upload not found')
            return orm.SinglefileData(file=io.BytesIO(path.read_bytes()), filename='input.pdb')
        if reference.get('source') == 'node':
            try:
                node = orm.load_node(uuid=reference['uuid'])
            except Exception as error:
                raise RequestError('input_not_found', 'input node not found') from error
            if not isinstance(node, orm.SinglefileData):
                raise RequestError('input_not_found', 'input node must be SinglefileData')
            return node
        raise RequestError('input_not_found', 'unsupported PDB source')

    def _code(self, model_name):
        reason = None
        try:
            identity = resolve_identity(self.model_root, model_name)
        except (OSError, ValueError, KeyError) as error:
            identity, reason = None, f'{type(error).__name__}: {error}'
        digest = identity_digest(identity) if identity else None
        device = os.environ.get('AI4S_ENGINE_DEVICE', 'cuda')
        label = 'engine-v2-proteinmpnn-' + device + '-' + (digest[:20] if digest else str(uuid4()))
        matches = orm.QueryBuilder().append(orm.InstalledCode, filters={'label': label}).all()
        if matches:
            code = matches[0][0]
            if code.model_identity != identity:
                raise RequestError('engine_unavailable', 'Code identity collision')
        else:
            code = orm.InstalledCode(label=label, computer=orm.load_computer('localhost'),
                                     filepath_executable='/usr/local/bin/proteinmpnn',
                                     default_calc_job_plugin='ai4s.proteinmpnn')
            if device == 'cpu':
                code.prepend_text = ('export CUDA_VISIBLE_DEVICES=""\n'
                                     'export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1')
            if identity:
                code.model_identity = identity
            else:
                code.base.attributes.set('ai4s_identity_unresolved', reason)
            code.store()
        return code, identity, digest, reason

    def submit(self, payload):
        requester_input = payload.get('requester', {})
        member = requester_input.get('member_id') if isinstance(requester_input, dict) else None
        if not isinstance(member, str):
            member = None
        ref = payload.get('client_ref')
        if ref is not None and (not isinstance(ref, str) or not ref or len(ref) > 200):
            raise RequestError('invalid_params', 'client_ref must contain 1–200 characters')
        if ref and member:
            row = self.db.execute('SELECT id,payload FROM requests WHERE member=? AND client_ref=?', (member, ref)).fetchone()
            if row:
                if json.loads(row[1]) != payload:
                    raise RequestError('invalid_params', 'client_ref already belongs to a different request')
                return self.status(row[0])
        request_id = 'req-' + str(uuid4())
        status = {'request_id': request_id, 'state': 'accepted', 'submitted_at': now(), 'updated_at': now(),
                  'finished_at': None, 'decision': None, 'process': None, 'cached_from': None,
                  'effective': None, 'outputs': None, 'error': None}
        self.db.execute('INSERT INTO requests VALUES (?,?,?,?,?)', (request_id, member, ref, json.dumps(payload), json.dumps(status)))
        self.db.commit()
        try:
            if payload.get('schema_version') != 'ai4s-request-1':
                raise RequestError('invalid_params', 'unsupported request schema')
            requester = payload.get('requester')
            if not isinstance(requester, dict) or not all(isinstance(requester.get(k), str) and requester[k].strip() for k in ('member_id', 'display_name')):
                raise RequestError('invalid_params', 'requester requires member_id and display_name')
            declaration_ref = payload.get('declaration', {})
            try:
                declaration = self.registry.get(declaration_ref['task_id'], declaration_ref['version'])
            except (KeyError, TypeError):
                raise RequestError('invalid_declaration', 'unknown task declaration or version')
            workflow = payload.get('workflow')
            if workflow not in declaration['workflow_modes']:
                raise RequestError('invalid_declaration', 'unsupported workflow')
            params = payload.get('params', {})
            if not isinstance(params, dict) or not isinstance(payload.get('inputs'), dict):
                raise RequestError('invalid_params', 'params and inputs must be objects')
            inference = complete_parameters(params.get('inference', {}))
            issues = validate_values(inference, 'inference')
            problem = parameter_problem(inference)
            if issues or problem:
                raise RequestError('invalid_params', problem or str(issues))
            if 'reuse_policy' in payload:
                policy = payload['reuse_policy']
                policy_source = {'source': 'request', 'reuse_policy': policy}
            elif self.policy_data is not None:
                saved = read_policy(self.policy_data)
                policy = saved['config']['reuse_policy']
                policy_source = {'source': 'workspace', 'revision': saved['revision'], 'reuse_policy': policy}
            else:
                raise RequestError('invalid_params', 'reuse_policy is required unless workspace policy is configured')
            validate_reuse_policy(policy)
            status['policy'] = policy_source
            original_seed = inference['seed']
            if workflow == 'mpnn_filter':
                issues = validate_values(params.get('filter', {}), 'filter')
                if issues:
                    raise RequestError('invalid_params', str(issues))
            pdb = self._input(payload.get('inputs', {}).get('pdb_file', {}))
            code, identity, digest, unresolved = self._code(inference['model_name'])
            if identity and identity['release'] != declaration['model']['release']:
                raise RequestError('invalid_declaration', 'declaration does not support deployed model release')
            if not self.health()['daemon_running']:
                raise RequestError('engine_unavailable', 'isolated AiiDA daemon is not running')
            from .sharing import search_request, collect_candidates
            query = search_request(code, pdb, inference, params.get('filter') if workflow == 'mpnn_filter' else None)
            candidate_list, peer_errors = collect_candidates(self, query, policy) if not unresolved else ([], [])
            status['sharing'] = {'peer_errors': peer_errors, 'candidates': candidate_list}
            if policy == 'new_sample':
                inference['seed'] = default_seed_factory(original_seed)
            context = dict(request_id=request_id, reuse_policy=policy, original_seed=original_seed,
                           effective_seed=inference['seed'], requester=requester, profile=self.profile,
                           num_sequences=inference['num_sequences'])
            context['shared_candidates'] = candidate_list
            if workflow == 'single':
                builder = CalculationFactory('ai4s.proteinmpnn').get_builder()
                builder.code, builder.pdb_file, builder.params = code, pdb, orm.Dict(inference)
                builder.metadata.ai4s_context = context
            else:
                # The C WorkChain owns its persisted policy and new-sample seed.
                inference['seed'] = original_seed
                builder = WorkflowFactory('ai4s.protein-mpnn-filter').get_builder()
                builder.code, builder.pdb_file = code, pdb
                builder.mpnn_params, builder.filter_params = orm.Dict(inference), orm.Dict(params['filter'])
                builder.request_id, builder.reuse_policy = orm.Str(request_id), orm.Str(policy)
                result_map = {item['uuid'] + '::' + item['fingerprint']: item['uuid']
                              for item in candidate_list if item['qualified'] and policy == 'allow_reuse'}
                builder.reuse_candidates, builder.candidate_results = orm.List(list=candidate_list), orm.Dict(result_map)
            builder.metadata.label = request_id
            node = submit(builder)
            node.base.extras.set('ai4s_requester', requester)
            status['state'] = 'submitted'
            status['process'] = self._process(node)
            status['effective'] = {'seed': inference['seed'], 'identity_digest': digest, 'fingerprint': None,
                                   'identity_unresolved': unresolved}
        except RequestError as error:
            status.update(state='failed', finished_at=now(), error={'code': error.code, 'message': str(error)})
        except (ValueError, TypeError, KeyError) as error:
            status.update(state='failed', finished_at=now(), error={'code': 'invalid_params', 'message': str(error)})
        except Exception as error:
            # Never automatically resubmit after an uncertain transport/daemon failure.
            status.update(state='failed', finished_at=now(), error={'code': 'engine_unavailable', 'message': f'{type(error).__name__}: {error}; check native process label before retrying'})
        self._save(request_id, status)
        return self.status(request_id)

    @staticmethod
    def _process(node):
        return {'uuid': node.uuid, 'pk': node.pk, 'label': node.label,
                'process_state': node.process_state.value if node.process_state else None,
                'exit_status': node.exit_status, 'exit_message': node.exit_message}

    def _save(self, request_id, status):
        status['updated_at'] = now()
        self.db.execute('UPDATE requests SET status=? WHERE id=?', (json.dumps(status), request_id))
        self.db.commit()

    def status(self, request_id):
        row = self.db.execute('SELECT status FROM requests WHERE id=?', (request_id,)).fetchone()
        if not row:
            raise KeyError(request_id)
        status = json.loads(row[0])
        if not status['process']:
            return status
        node = orm.load_node(uuid=status['process']['uuid'])
        status['process'] = self._process(node)
        calc = node if isinstance(node, orm.CalcJobNode) else next((p for p in node.called_descendants if isinstance(p, orm.CalcJobNode)), None)
        records = find_decisions_by_request(request_id)
        if records:
            decision = records[-1]
            status['decision'] = {'action': decision['final_decision']['action'], **decision['reason']}
            status['effective']['seed'] = decision['final_decision']['effective_seed']
            if decision['final_decision']['action'] == 'reuse' and calc is None:
                result = orm.load_node(uuid=decision['final_decision']['selected_candidate_uuid'])
                calc = result.creator
                status['cached_from'] = calc.uuid
        if calc:
            status['cached_from'] = status['cached_from'] or calc.base.caching.get_cache_source()
            status['effective']['fingerprint'] = calc.base.caching.get_hash()
            status['effective']['identity_digest'] = calc.base.extras.get('ai4s_identity_digest', status['effective']['identity_digest'])
        if node.is_terminated:
            status['process'] = self._process(node)
            status['state'] = 'finished' if node.is_finished_ok else 'failed'
            status['finished_at'] = node.mtime.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            if not node.is_finished_ok:
                status['error'] = {'code': 'process_failed', 'message': node.exit_message or str(node.process_state)}
            else:
                outputs = {'artifacts': {}}
                if calc and 'result' in calc.outputs:
                    outputs['result'] = calc.outputs.result.uuid
                    outputs['artifacts'] = {k: value.uuid for k, value in calc.outputs.artifacts.items()}
                if not isinstance(node, orm.CalcJobNode):
                    outputs.update({link.link_label: link.node.uuid for link in node.base.links.get_outgoing().all() if isinstance(link.node, orm.Data)})
                status['outputs'] = outputs
        elif node.process_state and node.process_state.value == 'running':
            status['state'] = 'running'
        # Observe termination before reading terminal outputs. A process may
        # finish during this HTTP request; early reads can miss its report.
        children = [node] if isinstance(node, orm.CalcJobNode) else [
            child for child in node.called_descendants if isinstance(child, orm.CalcJobNode)]
        status['execution'] = {'calcjobs': [dict(self._process(child), cache_source=child.base.caching.get_cache_source())
                                          for child in children]}
        if 'selection_report' in node.outputs:
            status['execution']['selection_report'] = node.outputs.selection_report.get_dict()
        self._save(request_id, status)
        return status
