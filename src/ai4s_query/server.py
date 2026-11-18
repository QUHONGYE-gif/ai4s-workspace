# -*- coding: utf-8 -*-
"""只读查询服务（开发任务 4.0 · 站 9）。

网页从这里实时读取来源、产物与决策记录，取代此前的「手动导出 JSON 快照」。
只用标准库（http.server + json），与工作台后端保持一致，不引入框架依赖。

启动：
    python -m ai4s_query.server --host 127.0.0.1 --port 8848

端点（全部 GET，全部只读）：
    /api/health                              服务与环境
    /api/node/<UUID|前缀|PK>                 单节点：状态、参数、产物、血缘
    /api/trace/<UUID>?depth=12               主干轨迹：输入 → 计算 → 产物
    /api/candidates?fingerprint=..&node=..   约定④ 候选列表（跨成员）
    /api/decision?request_id=..&process_uuid=..  约定⑤ 决策记录

约定：始终返回 JSON；跨域放行 ``*``，便于本地前端联调。
"""
from __future__ import annotations

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

_LOCK = threading.Lock()  # profile 切换是全局状态，查询串行化
_DECISIONS_DIR = None
_VERSION = "ai4s-query/4.0"


def _json_default(obj):
    if isinstance(obj, (set, tuple)):
        return list(obj)
    return str(obj)


def api_health(params, _body):
    from aiida.manage.configuration import get_config

    from . import candidates

    cfg = get_config()
    return {
        "ok": True,
        "service": _VERSION,
        "current_profile": candidates._current_profile(),
        "profiles": [p.name for p in cfg.profiles],
        "members": candidates._member_map(),
        "decisions_dir": str(_DECISIONS_DIR) if _DECISIONS_DIR else
        str(__import__("ai4s_query.decision", fromlist=["x"]).default_dir()),
    }


def api_node(params, _body):
    from . import query

    ident = params.get("id")
    info = query.describe(ident)
    info["ok"] = True
    return info


def api_trace(params, _body):
    from . import query

    ident = params.get("id")
    depth = int(params.get("depth") or 12)
    steps = query.trace(ident, max_depth=depth)
    return {"ok": True, "uuid": steps[-1]["uuid"] if steps else None,
            "steps": steps, "count": len(steps)}


def api_candidates(params, _body):
    from . import candidates

    request = {}
    if params.get("num_sequences"):
        request["num_sequences"] = int(params["num_sequences"])
    if params.get("score_threshold"):
        request["score_threshold"] = float(params["score_threshold"])
    if params.get("manual_reject"):
        request["manual_reject"] = True
        request["manual_reject_reason"] = params.get("manual_reject")

    if params.get("node"):
        return {**candidates.by_node(params["node"], request), "ok": True}
    result = candidates.find(
        fingerprint=params.get("fingerprint") or None,
        profiles=[p for p in (params.get("profiles") or "").split(",") if p] or None,
        request=request,
        include_unqualified=params.get("include_unqualified", "1") != "0",
    )
    result["ok"] = True
    return result


def api_decision(params, _body):
    from . import decision

    ident = params.get("request_id") or params.get("process_uuid") or params.get("uuid")
    if not ident:
        raise ValueError("需要 request_id 或 process_uuid 或 uuid 之一")
    out = decision.load(ident, profile=params.get("profile"), directory=_DECISIONS_DIR)
    out["ok"] = True
    return out


ROUTES = {
    "/api/health": api_health,
    "/api/candidates": api_candidates,
    "/api/decision": api_decision,
}

PREFIX_ROUTES = [
    ("/api/node/", api_node),
    ("/api/trace/", api_trace),
]

INDEX = """<!doctype html><meta charset="utf-8"><title>ai4s 查询服务</title>
<style>body{font:14px/1.9 -apple-system,"Segoe UI",sans-serif;max-width:760px;margin:48px auto;color:#1a1a1a}
code{background:#f3f4f6;padding:1px 5px;border-radius:3px}h1{font-size:20px}
td{padding:2px 12px 2px 0}</style>
<h1>ai4s 查询服务 · 只读</h1>
<p>用于网页实时读取 AiiDA 节点的来源、产物与决策记录。所有端点均为 GET。</p>
<table>
<tr><td><code>/api/health</code></td><td>服务状态、profile 清单、成员映射</td></tr>
<tr><td><code>/api/node/&lt;UUID&gt;</code></td><td>单节点：状态、参数、产物、血缘</td></tr>
<tr><td><code>/api/trace/&lt;UUID&gt;?depth=12</code></td><td>主干轨迹：输入 → 计算 → 产物</td></tr>
<tr><td><code>/api/candidates?fingerprint=..</code></td><td>约定④ 候选列表（跨成员）</td></tr>
<tr><td><code>/api/candidates?node=&lt;UUID&gt;</code></td><td>以该结果为参照找候选</td></tr>
<tr><td><code>/api/decision?request_id=..</code></td><td>约定⑤ 决策记录</td></tr>
</table>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "ai4s-query"

    def _send(self, status: int, payload):
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False, indent=2,
                              default=_json_default).encode("utf-8")
            ctype = "application/json; charset=utf-8"
        else:
            body = str(payload).encode("utf-8")
            ctype = "text/html; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        if path in ("/", "/index.html"):
            return self._send(200, INDEX)

        handler = ROUTES.get(path)
        if handler is None:
            for prefix, fn in PREFIX_ROUTES:
                if path.startswith(prefix):
                    params["id"] = path[len(prefix):].strip("/")
                    handler = fn
                    break
        if handler is None:
            return self._send(404, {"ok": False, "error": f"未知端点 {path}",
                                    "endpoints": list(ROUTES) + [p for p, _ in PREFIX_ROUTES]})
        try:
            with _LOCK:
                payload = handler(params, None)
            return self._send(200, payload)
        except ValueError as exc:
            return self._send(400, {"ok": False, "error": str(exc), "path": path})
        except Exception as exc:  # noqa: BLE001
            return self._send(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                                    "traceback": traceback.format_exc()[-1200:],
                                    "path": path})

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}", flush=True)


def serve(host: str = "127.0.0.1", port: int = 8848,
          profile: str | None = None, decisions_dir=None):
    global _DECISIONS_DIR
    from pathlib import Path

    from aiida import load_profile

    load_profile(profile)
    _DECISIONS_DIR = Path(decisions_dir) if decisions_dir else None

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"[ai4s-query] 服务已启动 http://{host}:{port}", flush=True)
    print(f"[ai4s-query] 端点清单见根路径；Ctrl+C 停止", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[ai4s-query] 已停止", flush=True)
    finally:
        httpd.server_close()


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m ai4s_query.server",
        description="只读查询服务：给网页实时读取来源、产物与决策记录")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8848, help="端口（默认 8848）")
    parser.add_argument("--profile", help="AiiDA profile 名，缺省用默认 profile")
    parser.add_argument("--decisions-dir", dest="decisions_dir",
                        help="约定⑤ 决策记录的旁路目录（默认 ~/runs/decisions）")
    args = parser.parse_args(argv)
    serve(args.host, args.port, args.profile, args.decisions_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
