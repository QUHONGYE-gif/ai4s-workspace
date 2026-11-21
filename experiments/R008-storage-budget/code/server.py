"""常驻查询服务（任务 5.0 要求 3）。

一条命令起服务，一个地址看页面：

    python server.py                # http://127.0.0.1:8765/
    python server.py --port 8800

只监听回环地址，无鉴权，只在实验目录内读写。
"""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import engine

ROOT = Path(__file__).resolve().parent
SESSION = engine.LAB / "session.json"
MB = engine.MB

STATE = {"policy": "scored", "quota_mb": 46.0, "run_id": "server"}
LOCK = threading.RLock()

ALLOWED_FILES = {"index.html": "text/html; charset=utf-8",
                 "policy-diagram.svg": "image/svg+xml; charset=utf-8"}


# ---------------------------------------------------------------- 会话状态

def load_session():
    if SESSION.exists():
        try:
            data = json.loads(SESSION.read_text(encoding="utf-8"))
            STATE["policy"] = data.get("policy", "scored")
            STATE["quota_mb"] = float(data.get("quota_mb", 46.0))
        except (ValueError, OSError):
            pass


def save_session():
    SESSION.write_text(json.dumps(STATE, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- 查询

def artifact_view(row, used_policy):
    """一个结果一条结论：保留还是已淘汰，以及为什么。"""
    ev = row.get("eviction")
    if row["status"] == "active":
        if row["pinned"]:
            verdict, why = "保留", "固定项：显式标记不参与淘汰。"
        else:
            why = (f"保留：保留价值 {row['score']}，复用 {row['use_count']} 次、"
                   f"重算成本 {int(row['cost_s'])} 秒、{row['size_mb']} MB。")
            verdict = "保留"
    else:
        verdict = "已淘汰"
        why = ev["explain"] if ev else "已淘汰：淘汰记录缺失。"
    return {"fingerprint": row["fingerprint"], "label": row["label"],
            "size_mb": row["size_mb"], "cost_s": row["cost_s"],
            "use_count": row["use_count"], "pinned": row["pinned"],
            "status": row["status"], "retained": row["status"] == "active",
            "verdict": verdict, "reason": why,
            "score": row["score"], "last_used_at": row["last_used_at"],
            "evicted_at": ev["at"] if ev else None,
            "evicted_by": ev["policy"] if ev else None}


def status_payload():
    with LOCK:
        snap = engine.snapshot()
        arts = [artifact_view(a, STATE["policy"]) for a in snap["artifacts"]]
        used = snap["used_bytes"]
        quota_b = int(STATE["quota_mb"] * MB)
        return {
            "policy": STATE["policy"],
            "quota_mb": STATE["quota_mb"],
            "soft_target_mb": round(STATE["quota_mb"] * 0.85, 2),
            "used_mb": round(used / MB, 2),
            "used_bytes": used,
            "quota_bytes": quota_b,
            "over_quota": used > quota_b,
            "counts": {
                "total": len(arts),
                "retained": sum(1 for a in arts if a["retained"]),
                "evicted": sum(1 for a in arts if not a["retained"]),
                "pinned": sum(1 for a in arts if a["pinned"]),
            },
            "artifacts": arts,
            "evictions": snap["evictions"][:20],
            "restores": snap["restores"][:20],
        }


def do_request(fingerprint):
    """触发一次真实请求：命中复用 / 命中墓碑后重算。"""
    with LOCK:
        if not any(c[0] == fingerprint for c in engine.CATALOG):
            raise KeyError(fingerprint)
        engine.init()
        conn = engine.connect()
        stats = {"hits": 0, "restores": 0, "computed": 0, "evictions": 0, "recompute_real_s": 0.0}
        try:
            result = engine.handle_request(conn, STATE["run_id"], STATE["policy"],
                                           int(STATE["quota_mb"] * MB), fingerprint, stats)
        finally:
            conn.close()
        if result["action"] == "reuse":
            verdict, why, extra = "保留", "命中未淘汰的产物，直接读取。", 0.0
        elif result["action"] == "restore":
            extra = round(max(0.0, engine.spec(fingerprint)["cost_s"] - engine.READ_SECONDS), 1)
            verdict = "已淘汰 → 重算"
            why = f"墓碑命中：按原输入重算补回，净多花 {extra} 秒（读取本来只需 {engine.READ_SECONDS} 秒）。"
        else:
            verdict, why, extra = "未计算", "首次请求，正常计算。", 0.0
        return {"fingerprint": fingerprint, "action": result["action"], "verdict": verdict,
                "reason": why, "extra_s": extra, "evicted_now": result["evicted_now"],
                "elapsed": result["elapsed"],
                "policy": STATE["policy"], "quota_mb": STATE["quota_mb"]}


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "EvictLab/1.0"

    def log_message(self, fmt, *args):
        pass  # 保持控制台只输出启动信息与错误

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, indent=1)
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                f = ROOT / "index.html"
                if not f.exists():
                    return self._send(404, "index.html 不存在", "text/plain; charset=utf-8")
                return self._send(200, f.read_bytes(), ALLOWED_FILES["index.html"])
            if path.lstrip("/") in ALLOWED_FILES:
                f = ROOT / path.lstrip("/")
                if not f.exists():
                    return self._send(404, "not found", "text/plain; charset=utf-8")
                return self._send(200, f.read_bytes(), ALLOWED_FILES[path.lstrip("/")])
            if path == "/api/status":
                return self._send(200, status_payload())
            if path == "/api/artifacts":
                payload = status_payload()
                want = qs.get("filter", ["all"])[0]
                if want == "evicted":
                    payload["artifacts"] = [a for a in payload["artifacts"] if not a["retained"]]
                elif want == "retained":
                    payload["artifacts"] = [a for a in payload["artifacts"] if a["retained"]]
                return self._send(200, payload)
            if path == "/api/evictions":
                limit = int(qs.get("limit", ["20"])[0])
                return self._send(200, engine.snapshot()["evictions"][:limit])
            if path == "/api/restores":
                return self._send(200, engine.snapshot()["restores"][:20])
            if path == "/api/compare":
                f = ROOT / "traces.json"
                data = json.loads(f.read_text(encoding="utf-8"))
                return self._send(200, {"meta": data["meta"], "compare": data["compare"]})
            if path == "/api/policy":
                name = qs.get("name", [""])[0]
                with LOCK:
                    if name in ("lru", "scored"):
                        STATE["policy"] = name
                        save_session()
                    return self._send(200, {"policy": STATE["policy"]})
            if path == "/api/quota":
                try:
                    mb = float(qs.get("mb", ["0"])[0])
                except ValueError:
                    mb = 0
                with LOCK:
                    if mb > 0:
                        STATE["quota_mb"] = mb
                        save_session()
                    return self._send(200, {"quota_mb": STATE["quota_mb"]})
            if path == "/api/request":
                fp = qs.get("fp", [""])[0]
                return self._send(200, do_request(fp))
            if path == "/api/reset":
                with LOCK:
                    engine.reset()
                return self._send(200, {"ok": True, "used_mb": 0})
            return self._send(404, {"error": "unknown endpoint", "path": path})
        except KeyError as exc:
            return self._send(400, {"error": f"未知产物：{exc}"})
        except Exception as exc:  # 服务不因单次异常退出
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self):
        return self.do_GET()


def main():
    ap = argparse.ArgumentParser(description="保留策略 · 常驻查询服务")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    engine.init()
    load_session()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"保留策略实验台 · 常驻服务：http://{args.host}:{args.port}/")
    print(f"  策略 {STATE['policy']} · 配额 {STATE['quota_mb']} MB · 实验目录 {engine.LAB}")
    print("  端点 /api/status /api/artifacts /api/evictions /api/restores "
          "/api/compare /api/request?fp= /api/policy?name= /api/quota?mb= /api/reset")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
