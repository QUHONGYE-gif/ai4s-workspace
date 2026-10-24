"""Same-origin demo API and static frontend, using only Python's standard library."""

from __future__ import annotations

import argparse
import http.client
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit
from xmlrpc.client import Error as PyMOLError

from .storage import ConflictError, SnapshotStore
from .pymol import PyMOLSession

ROOT = Path(__file__).resolve().parents[2]
MAX_BODY = 2 * 1024 * 1024


class DemoHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, store, fixtures, directory, pymol, agent_port, **kwargs):
        self.store = store
        self.pymol = pymol
        self.fixtures = fixtures
        self.agent_port = agent_port
        self.frontend = Path(directory).resolve()
        super().__init__(*args, directory=str(self.frontend), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def reply(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/agent" or path.startswith("/agent/"):
            return self.proxy_agent()
        try:
            if path == "/api/tools/pymol":
                try:
                    return self.reply(200, self.pymol.status())
                except (OSError, PyMOLError):
                    return self.reply(503, {"error": "PyMOL 会话未启动或暂不可用"})
            if path == "/api/health":
                return self.reply(
                    200, {"status": "ok", "mode": "simulation", "state_version": 1}
                )
            if path == "/api/demo/bootstrap":
                return self.reply(
                    200, {"mode": "simulation", "fixtures": self.fixtures}
                )
            if path == "/api/demo/state":
                return self.reply(
                    200, self.store.load(self.headers.get("X-Demo-Session"))
                )
            if path.startswith("/api/"):
                return self.reply(404, {"error": "Unknown API endpoint"})
            # Serve only frontend files, including protection against symlink escape.
            target = Path(self.translate_path(self.path)).resolve()
            if not target.is_relative_to(self.frontend):
                return self.send_error(HTTPStatus.NOT_FOUND)
            return super().do_GET()
        except ValueError as error:
            return self.reply(400, {"error": str(error)})
        except (OSError, json.JSONDecodeError):
            return self.reply(
                500,
                {
                    "error": "Demo snapshot unavailable; export browser changes before retrying"
                },
            )

    def do_HEAD(self):
        path = urlsplit(self.path).path
        if path == "/agent" or path.startswith("/agent/"):
            return self.proxy_agent()
        if urlsplit(self.path).path.startswith("/api/"):
            return self.do_GET()
        target = Path(self.translate_path(self.path)).resolve()
        if not target.is_relative_to(self.frontend):
            return self.send_error(HTTPStatus.NOT_FOUND)
        return super().do_HEAD()

    def do_PUT(self):
        if urlsplit(self.path).path.startswith("/agent/"):
            return self.proxy_agent()
        if urlsplit(self.path).path != "/api/demo/state":
            return self.reply(404, {"error": "Unknown API endpoint"})
        if self.headers.get_content_type() != "application/json":
            return self.reply(415, {"error": "Content-Type must be application/json"})
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if length < 0:
                return self.reply(411, {"error": "Content-Length is required"})
            if length > MAX_BODY:
                self.close_connection = True
                return self.reply(413, {"error": "Demo state exceeds 2 MiB"})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Request must be an object")
            result = self.store.save(
                self.headers.get("X-Demo-Session"),
                payload.get("revision"),
                payload.get("state"),
            )
            return self.reply(200, result)
        except ConflictError as error:
            return self.reply(409, {"error": str(error)})
        except (ValueError, UnicodeDecodeError) as error:
            return self.reply(400, {"error": str(error)})
        except OSError:
            return self.reply(
                500, {"error": "Snapshot could not be saved; export browser changes"}
            )

    def do_POST(self):
        path = urlsplit(self.path).path
        if path.startswith("/agent/"):
            return self.proxy_agent()
        if path not in (
            "/api/tools/pymol/load", "/api/tools/pymol/style",
            "/api/tools/pymol/mode", "/api/tools/pymol/command",
        ):
            return self.reply(404, {"error": "Unknown API endpoint"})
        if self.headers.get_content_type() != "application/json":
            return self.reply(415, {"error": "Content-Type must be application/json"})
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if length < 0:
                return self.reply(411, {"error": "Content-Length is required"})
            if length > MAX_BODY:
                self.close_connection = True
                return self.reply(413, {"error": "请选择不超过 1 MiB 的结构文件"})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Request must be an object")
            if path.endswith("/load"):
                result = self.pymol.load(
                    payload.get("filename"), payload.get("content"),
                    payload.get("style", "cartoon")
                )
            elif path.endswith("/style"):
                result = self.pymol.set_style(payload.get("style"))
            elif path.endswith("/mode"):
                result = self.pymol.set_mode(payload.get("full_ui"))
            else:
                result = self.pymol.execute(payload.get("command"))
            return self.reply(200, result)
        except (ValueError, UnicodeDecodeError) as error:
            return self.reply(400, {"error": str(error)})
        except (OSError, PyMOLError):
            return self.reply(503, {"error": "PyMOL 操作未返回，请检查会话；耗时命令可能仍在运行"})

    def proxy_agent(self):
        """Forward only the fixed Agent service; preserve the browser's Host/Origin."""
        if urlsplit(self.path).path == "/agent":
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", "./agent/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, {"error": "Invalid Content-Length"})
        if length < 0 or length > 6 * 1024 * 1024:
            self.close_connection = True
            return self.reply(413, {"error": "Agent request exceeds 6 MiB"})
        if self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            return self.reply(400, {"error": "Content-Length is required"})
        connection = http.client.HTTPConnection("127.0.0.1", self.agent_port, timeout=120)
        excluded = {"connection", "keep-alive", "transfer-encoding", "upgrade", "proxy-connection"}
        headers = {k: v for k, v in self.headers.items() if k.lower() not in excluded}
        try:
            connection.request(self.command, self.path,
                               self.rfile.read(length) if length else None, headers)
            response = connection.getresponse()
            body = response.read()
        except (OSError, http.client.HTTPException):
            return self.reply(503, {"error": "智能体服务暂不可用，请检查联合服务及其日志"})
        finally:
            connection.close()
        self.send_response(response.status)
        for key, value in response.getheaders():
            if key.lower() not in excluded | {"content-length", "server", "date"}:
                self.send_header(key, value)
        content_length = response.getheader("Content-Length", "0") if self.command == "HEAD" else str(len(body))
        self.send_header("Content-Length", content_length)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def list_directory(self, path):
        self.send_error(HTTPStatus.NOT_FOUND)
        return None

    def log_message(self, format, *args):
        # No session identifiers or bodies are written to request logs.
        super().log_message(format, *args)


def create_server(host="127.0.0.1", port=3000, data_dir=None, agent_port=3002):
    fixtures = json.loads(
        (ROOT / "configs/workbench-demo.json").read_text(encoding="utf-8")
    )
    store = SnapshotStore(Path(data_dir) if data_dir else ROOT / ".local/workbench-api")
    handler = partial(
        DemoHandler, store=store, fixtures=fixtures, directory=ROOT / "web/demo",
        pymol=PyMOLSession(store.directory.parent / "pymol-inputs"), agent_port=agent_port
    )
    return ThreadingHTTPServer((host, port), handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=3000, type=int)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".local/workbench-api")
    args = parser.parse_args()
    server = create_server(args.host, args.port, args.data_dir)
    print(
        f"Demo frontend and API at http://{args.host}:{server.server_port}/", flush=True
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
