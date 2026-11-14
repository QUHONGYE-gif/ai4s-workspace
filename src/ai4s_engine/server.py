"""Run with the dedicated AiiDA environment: python -m ai4s_engine.server."""
import argparse
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from aiida import load_profile, orm
from ai4s_workflows.decision import find_decisions_by_request, find_decisions_by_process
from .service import EngineService, RequestError

ROOT = Path(__file__).resolve().parents[2]
MAX_BODY = 2 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def authorized(self):
        token = self.server.peer_token
        if self.client_address[0] in ('127.0.0.1', '::1'):
            return True
        return bool(token) and hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)

    def binary(self, raw, content_type='application/octet-stream'):
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('X-Content-SHA256', hashlib.sha256(raw).hexdigest())
        self.end_headers()
        self.wfile.write(raw)

    def reply(self, status, body):
        raw = json.dumps(body, ensure_ascii=False, allow_nan=False, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self.authorized():
            return self.reply(403, {'error': 'member peer token required'})
        route = urlsplit(self.path)
        path = route.path
        service = self.server.service
        try:
            if path == '/api/engine/health':
                health = service.health()
                return self.reply(200 if health['daemon_running'] else 503, health)
            if path == '/api/engine/declarations':
                return self.reply(200, service.registry.list())
            if path.startswith('/api/engine/declarations/'):
                task, version = path.rsplit('/', 2)[-2:]
                return self.reply(200, service.registry.get(task, version))
            if path.startswith('/api/engine/requests/'):
                request_id = path.rsplit('/', 1)[-1]
                return self.reply(200, service.status(request_id))
            if path == '/api/engine/decisions':
                parameters = parse_qs(route.query)
                records = (find_decisions_by_request(parameters['request_id'][0]) if 'request_id' in parameters
                           else find_decisions_by_process(parameters['process_uuid'][0]))
                return self.reply(200, {'records': records})
            if path.startswith('/api/engine/archives/'):
                from .sharing import export_result
                return self.binary(export_result(path.rsplit('/', 1)[-1], service.directory))
            if path.startswith('/api/engine/trace/'):
                from ai4s_query import query
                return self.reply(200, {'steps': query.trace(path.rsplit('/', 1)[-1])})
            if path.startswith('/api/engine/nodes/'):
                from ai4s_query import query
                return self.reply(200, query.describe(path.rsplit('/', 1)[-1]))
            if path.startswith('/api/engine/files/'):
                node = orm.load_node(uuid=path.rsplit('/', 1)[-1])
                if not isinstance(node, orm.SinglefileData):
                    raise KeyError('file not found')
                raw = node.get_content(mode='rb')
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', 'attachment; filename="' + Path(node.filename).name.replace('"', '') + '"')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            return self.reply(404, {'error': 'unknown engine endpoint'})
        except (KeyError, ValueError) as error:
            return self.reply(404, {'error': str(error)})
        except Exception as error:
            return self.reply(503, {'error': {'code': 'engine_unavailable', 'message': f'{type(error).__name__}: {error}'}})

    def do_POST(self):
        if not self.authorized():
            return self.reply(403, {'error': 'member peer token required'})
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if self.headers.get('Transfer-Encoding') or not 0 <= length <= MAX_BODY:
                self.close_connection = True
                return self.reply(413, {'error': 'request exceeds 2 MiB or has no Content-Length'})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('request must be an object')
            path = urlsplit(self.path).path
            if path == '/api/engine/shared-candidates':
                from .sharing import local_candidates
                candidates = local_candidates(payload, self.server.service.profile, self.server.service.member)
                return self.reply(200, {'candidates': candidates})
            if path == '/api/engine/uploads':
                content = payload.get('content')
                if not isinstance(content, str):
                    raise ValueError('upload content must be PDB text')
                return self.reply(201, self.server.service.upload(payload.get('filename'), content.encode()))
            if path == '/api/engine/requests':
                return self.reply(202, self.server.service.submit(payload))
            return self.reply(404, {'error': 'unknown engine endpoint'})
        except RequestError as error:
            return self.reply(400, {'error': {'code': error.code, 'message': str(error)}})
        except (ValueError, TypeError) as error:
            return self.reply(400, {'error': {'code': 'invalid_params', 'message': str(error)}})
        except Exception as error:
            return self.reply(503, {'error': {'code': 'engine_unavailable', 'message': f'{type(error).__name__}: {error}'}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=3003)
    parser.add_argument('--profile', default='ai4s-engine')
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--model-root', default='/opt/ai4s/proteinmpnn')
    parser.add_argument('--member', help='Producer display name for this member service')
    parser.add_argument('--peers', type=Path, help='Private JSON list: member, url, token')
    args = parser.parse_args()
    import aiida
    if aiida.__version__ != '2.9.4+ai4s.2':
        raise RuntimeError('Use the isolated aiida-core 2.9.4+ai4s.2 environment')
    peers = json.loads(args.peers.read_text()) if args.peers else []
    for peer in peers:
        parsed = urlsplit(peer['url'])
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or not peer['token']:
            raise ValueError('peer requires an operator-configured HTTP URL and token')
    token = os.environ.get('AI4S_PEER_TOKEN', '')
    if args.host not in ('127.0.0.1', 'localhost', '::1') and not token:
        raise ValueError('non-loopback engine binding requires AI4S_PEER_TOKEN')
    load_profile(args.profile)
    server = HTTPServer((args.host, args.port), Handler)
    server.peer_token = token
    server.service = EngineService(args.data_dir, ROOT / 'configs/task_declarations', args.model_root,
                                   member=args.member, peers=peers)
    print(f'AI4S engine on {args.host}:{args.port}, profile={args.profile}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
