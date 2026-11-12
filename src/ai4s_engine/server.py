"""Run with the dedicated AiiDA environment: python -m ai4s_engine.server."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from aiida import load_profile, orm
from ai4s_workflows.decision import find_decisions_by_request
from .service import EngineService, RequestError

ROOT = Path(__file__).resolve().parents[2]
MAX_BODY = 2 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        raw = json.dumps(body, ensure_ascii=False, allow_nan=False, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
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
                request_id = parse_qs(route.query).get('request_id', [''])[0]
                return self.reply(200, {'records': find_decisions_by_request(request_id)})
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
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if self.headers.get('Transfer-Encoding') or not 0 <= length <= MAX_BODY:
                self.close_connection = True
                return self.reply(413, {'error': 'request exceeds 2 MiB or has no Content-Length'})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('request must be an object')
            path = urlsplit(self.path).path
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
    args = parser.parse_args()
    import aiida
    if aiida.__version__ != '2.9.4+ai4s.1':
        raise RuntimeError('Use the isolated aiida-core 2.9.4+ai4s.1 environment')
    load_profile(args.profile)
    server = HTTPServer((args.host, args.port), Handler)
    server.service = EngineService(args.data_dir, ROOT / 'configs/task_declarations', args.model_root)
    print(f'AI4S engine on {args.host}:{args.port}, profile={args.profile}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
