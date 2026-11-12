"""按约定②实现的模拟引擎服务，供网页联调与自测使用。

真实引擎（开发任务4.0 站 3）上线后，把工作台的 AI4S_ENGINE_URL 指向它即可，
页面与后端无需改动。本服务只实现约定②的四个接口、约定④的候选结构与
约定⑤的决策记录，不运行任何科学模型。
"""

import argparse
import hashlib
import json
import os
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECLARATION_DIR = ROOT / "configs/task_declarations"
STATE_DIR = ROOT / ".local/mock-engine"

# 模拟运行的时间线（秒）：accepted -> submitted -> running -> finished
SUBMITTED_AFTER = 0.5
RUNNING_AFTER = 1.5
FINISHED_AFTER = 4.0

# 约定③ 模型身份中由部署解析的部分；模拟服务使用真实 3.0 运行的取值。
MOCK_WEIGHTS_SHA256 = "c9cb4a671d79604111231f8dbfc7c590e06f1197453b7a6854ac6661a642f5bd"
MOCK_SOURCE_COMMIT = "8907e6671bfbfc92303b5f79c4b5e6ce47cdef57"


def canonical(value):
    """约定③要求按键名排序、不含空格的 JSON 序列化。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_declaration(task_id, version):
    path = DECLARATION_DIR / str(task_id) / f"{version}.json"
    if not path.is_file():
        return None
    try:
        declaration = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if declaration.get("task_id") != task_id or declaration.get("version") != version:
        return None
    return declaration


def parameter_rules(declaration, group):
    return declaration.get("parameters", {}).get(group, {})


def fill_defaults(declaration, params):
    """按约定①补齐可选项默认值；补齐后同义请求才得到同一指纹。"""
    filled = {"inference": dict((params or {}).get("inference") or {}),
              "filter": dict((params or {}).get("filter") or {})}
    for key, rule in parameter_rules(declaration, "inference").items():
        if not rule.get("required") and key not in filled["inference"] and "default" in rule:
            filled["inference"][key] = rule["default"]
    return filled


def validate(declaration, workflow, params):
    """返回错误文字列表；空列表表示通过。只实现约定①列出的规则。"""
    errors = []
    inference = (params or {}).get("inference") or {}
    filtering = (params or {}).get("filter") or {}
    if workflow not in declaration.get("workflow_modes", []):
        errors.append(f"不支持的 workflow：{workflow}")
    for group_name, values in (("inference", inference), ("filter", filtering)):
        rules = parameter_rules(declaration, group_name)
        for key in values:
            if key not in rules:
                errors.append(f"{group_name} 存在未知参数：{key}")
        for key, rule in rules.items():
            if group_name == "filter" and workflow != "mpnn_filter":
                # single 流程不使用筛选参数，也不要求它们必填。
                continue
            if rule.get("required") and values.get(key) in (None, ""):
                errors.append(f"缺少必填参数：{key}")
    if workflow == "single" and filtering:
        errors.append("single 流程不接受筛选参数")

    def number(name, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{name} 必须是数字")
            return None
        return float(value)

    if "chains" in inference and not str(inference.get("chains") or "").strip():
        errors.append("chains 不能为空")
    if "num_sequences" in inference:
        try:
            sequences = int(inference["num_sequences"])
            if sequences < 1:
                errors.append("num_sequences 必须大于等于 1")
            batch = int(inference.get("batch_size", 1))
            if batch >= 1 and sequences % batch:
                errors.append("num_sequences 必须为 batch_size 的整数倍")
        except (TypeError, ValueError):
            errors.append("num_sequences 必须是整数")
    if "sampling_temperature" in inference:
        temperature = number("sampling_temperature", inference["sampling_temperature"])
        if temperature is not None and temperature <= 0:
            errors.append("sampling_temperature 必须为有限正数")
    if "seed" in inference:
        try:
            seed = int(inference["seed"])
            if seed < 1 or seed > 4294967295:
                errors.append("seed 必须为非零整数（1-4294967295）")
        except (TypeError, ValueError):
            errors.append("seed 必须为非零整数（1-4294967295）")
    if workflow == "mpnn_filter":
        for key in ("score_threshold", "top_k"):
            if filtering.get(key) in (None, ""):
                errors.append(f"mpnn_filter 需要筛选参数：{key}")
        if "top_k" in filtering:
            try:
                if int(filtering["top_k"]) < 1:
                    errors.append("top_k 必须大于等于 1")
            except (TypeError, ValueError):
                errors.append("top_k 必须是整数")
        if "score_threshold" in filtering:
            number("score_threshold", filtering["score_threshold"])
    return errors


def model_identity(declaration, params):
    """约定③：6 个字段构成模型身份摘要。"""
    inference = params["inference"]
    return {
        "model_id": declaration["model"]["model_id"],
        "model_name": inference.get("model_name", "v_48_020"),
        "release": declaration["model"]["release"],
        "source_commit": MOCK_SOURCE_COMMIT,
        "weights_family": declaration["model"]["weights_family"],
        "weights_sha256": MOCK_WEIGHTS_SHA256,
    }


def compute_fingerprint(identity_digest, params, pdb_sha256):
    """约定③：模型身份 + 输入文件内容 + 参数（含种子）共同构成计算指纹。"""
    return sha256_text(canonical({
        "identity_digest": identity_digest,
        "params": params,
        "pdb_sha256": pdb_sha256,
    }))


class Engine:
    """内存中的请求、候选与决策记录；进程重启即清空，避免伪造历史。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.requests = {}
        self.uploads = {}
        self.decisions = []

    # -- 上传 ---------------------------------------------------------------
    def add_upload(self, name, data):
        upload_id = f"up-{uuid.uuid4()}"
        record = {"upload_id": upload_id, "name": name,
                  "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        self.uploads[upload_id] = record
        return record

    def upload(self, upload_id):
        return self.uploads.get(upload_id)

    # -- 提交 ---------------------------------------------------------------
    def submit(self, payload):
        declaration_ref = payload.get("declaration") or {}
        declaration = load_declaration(declaration_ref.get("task_id", ""),
                                       declaration_ref.get("version", ""))
        if declaration is None:
            return self.failed("invalid_declaration", "任务声明不存在或版本不符")
        workflow = payload.get("workflow")
        params = fill_defaults(declaration, payload.get("params"))
        errors = validate(declaration, workflow, params)
        if errors:
            return self.failed("invalid_params", "；".join(errors))
        policy = payload.get("reuse_policy")
        if policy not in ("allow_reuse", "force_rerun", "new_sample"):
            return self.failed("invalid_params", "reuse_policy 必须是 allow_reuse／force_rerun／new_sample")

        pdb_ref = (payload.get("inputs") or {}).get("pdb_file") or {}
        upload = self.upload(pdb_ref.get("upload_id"))
        if upload is None:
            return self.failed("input_not_found", "上传编号不存在")

        identity = model_identity(declaration, params)
        identity_digest = sha256_text(canonical(identity))
        seed = params["inference"]["seed"]
        fingerprint = compute_fingerprint(identity_digest, params, upload["sha256"])
        request_id = f"req-{uuid.uuid4()}"
        created = time.time()

        candidates = self.find_candidates(fingerprint)
        if policy == "new_sample":
            seed = self.next_seed(fingerprint, seed)
            fingerprint = compute_fingerprint(identity_digest, {**params, "inference": {**params["inference"], "seed": seed}}, upload["sha256"])
        decision = self.decide(policy, candidates, seed)

        record = {
            "request_id": request_id,
            "state": "accepted",
            "payload": payload,
            "params": params,
            "workflow": workflow,
            "reuse_policy": policy,
            "requester": payload.get("requester") or {},
            "upload": upload,
            "identity": identity,
            "identity_digest": identity_digest,
            "fingerprint": fingerprint,
            "seed": seed,
            "decision": decision,
            "candidates": candidates,
            "created": created,
            "process_uuid": str(uuid.uuid4()),
            "cached_from": None,
            "outputs": None,
            "error": None,
            "started": created,
        }
        if decision["action"] == "reuse":
            source = next((c for c in candidates if c["uuid"] == decision["selected_candidate_uuid"]), None)
            record["cached_from"] = (source or {}).get("cached_from")
            record["process_uuid"] = str(uuid.uuid4())
            record["state"] = "finished"
            record["started"] = created
            record["finished_at"] = created
            record["outputs"] = self.make_outputs(record)
        if record["state"] == "finished" and record["error"] is None:
            record["state"] = "finished"
        self.requests[request_id] = record
        self.decisions.append(self.decision_record(record))
        if record["state"] == "finished":
            record["process_state"] = "finished"
        return self.status(record)

    def failed(self, code, message):
        return {
            "request_id": f"req-{uuid.uuid4()}",
            "state": "failed",
            "submitted_at": None, "updated_at": None, "finished_at": None,
            "decision": None, "process": None, "cached_from": None,
            "effective": None, "outputs": None,
            "error": {"code": code, "message": message},
        }

    # -- 候选与决策 ---------------------------------------------------------
    def find_candidates(self, fingerprint):
        result = []
        for record in self.requests.values():
            if record["state"] != "finished" or record["fingerprint"] != fingerprint:
                continue
            result.append({
                "uuid": record["process_uuid"],
                "fingerprint": fingerprint[:16],
                "member": (record.get("requester") or {}).get("display_name", "未知成员"),
                "location": f"profile://mock/{record['process_uuid']}/design.fa",
                "size_bytes": 2312,
                "elapsed_s": 0,
                "qualified": True,
                "reason": None,
                "note": "",
                "cached_from": record["process_uuid"],
            })
        return result

    def next_seed(self, fingerprint, seed):
        used = {record["seed"] for record in self.requests.values() if record["fingerprint"] == fingerprint}
        candidate = seed + 1
        while candidate in used:
            candidate += 1
        return candidate

    def decide(self, policy, candidates, seed):
        qualified = [c for c in candidates if c["qualified"]]
        if policy == "allow_reuse" and qualified:
            return {"action": "reuse", "selected_candidate_uuid": qualified[0]["uuid"],
                    "reason_code": "R01", "reason_text": "策略为允许复用，候选列表中存在合格候选，选中合格候选复用"}
        if policy == "allow_reuse":
            return {"action": "rerun", "selected_candidate_uuid": None,
                    "reason_code": "R02", "reason_text": "策略为允许复用，但没有合格候选，降级为重算"}
        if policy == "force_rerun":
            return {"action": "rerun", "selected_candidate_uuid": None,
                    "reason_code": "R03", "reason_text": "用户选择强制重算，忽略已有候选，使用原参数、原种子重新运行"}
        return {"action": "new_sample", "selected_candidate_uuid": None,
                "reason_code": "R04", "reason_text": f"用户选择新采样，忽略候选，更换新种子 {seed} 进行推理"}

    def decision_record(self, record):
        return {
            "request_id": record["request_id"],
            "reuse_policy": record["reuse_policy"],
            "candidate_compare_list": record["candidates"],
            "final_decision": {"action": record["decision"]["action"],
                               "selected_candidate_uuid": record["decision"]["selected_candidate_uuid"]},
            "reason": {"reason_code": record["decision"]["reason_code"],
                       "reason_text": record["decision"]["reason_text"]},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record["created"])),
        }

    # -- 状态推进 -----------------------------------------------------------
    def advance(self, record):
        if record["state"] in ("finished", "failed"):
            return
        elapsed = time.time() - record["created"]
        if elapsed >= FINISHED_AFTER:
            record["state"] = "finished"
            record["finished_at"] = time.time()
            record["outputs"] = self.make_outputs(record)
        elif elapsed >= RUNNING_AFTER:
            record["state"] = "running"
        elif elapsed >= SUBMITTED_AFTER:
            record["state"] = "submitted"

    def make_outputs(self, record):
        prefix = f"node-{record['process_uuid'][:8]}"
        outputs = {"result": f"{prefix}-result",
                   "artifacts": {"sequences": f"{prefix}-sequences",
                                 "scores": f"{prefix}-scores"}}
        if record["params"]["inference"].get("save_probabilities", True):
            outputs["artifacts"]["probabilities"] = f"{prefix}-probabilities"
        if record["workflow"] == "mpnn_filter":
            kept = min(int(record["params"]["filter"].get("top_k", 1)),
                       int(record["params"]["inference"].get("num_sequences", 1)))
            outputs["selected_sequences"] = f"{prefix}-selected"
            outputs["selection_report"] = f"{prefix}-report"
            outputs["selected_count"] = max(kept, 0)
        return outputs

    def status(self, record):
        self.advance(record)
        process_state = {"accepted": None, "submitted": "created", "running": "running",
                         "finished": "finished", "failed": "finished"}[record["state"]]
        elapsed = (record.get("finished_at") or time.time()) - record["created"]
        return {
            "request_id": record["request_id"],
            "state": record["state"],
            "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record["created"])),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "finished_at": (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record["finished_at"]))
                            if record.get("finished_at") else None),
            "decision": {"action": record["decision"]["action"],
                         "reason_code": record["decision"]["reason_code"]},
            "process": {"uuid": record["process_uuid"], "pk": 42,
                        "label": f"proteinmpnn-{record['upload']['name']}",
                        "process_state": process_state,
                        "exit_status": 0 if record["state"] == "finished" else None,
                        "exit_message": None},
            "cached_from": record["cached_from"],
            "effective": {"seed": record["seed"],
                          "identity_digest": record["identity_digest"],
                          "fingerprint": record["fingerprint"]},
            "elapsed_s": round(elapsed, 1),
            "outputs": record["outputs"],
            "error": record["error"],
        }


ENGINE = Engine()


class Handler(BaseHTTPRequestHandler):
    server_version = "MockEngine/1.0"

    def log_message(self, format, *args):
        pass

    def _json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/api/engine/health":
            return self._json({"status": "ok", "profile": "mock", "daemon": "running",
                               "engine": "mock", "requests": len(ENGINE.requests)})
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 4 and parts[:3] == ["api", "engine", "requests"]:
            record = ENGINE.requests.get(parts[3])
            if record is None:
                return self._json({"error": {"code": "input_not_found", "message": "请求不存在"}},
                                  HTTPStatus.NOT_FOUND)
            if len(parts) == 4:
                return self._json(ENGINE.status(record))
            if parts[4] == "decisions":
                return self._json({"decisions": [d for d in ENGINE.decisions
                                                 if d["request_id"] == record["request_id"]]})
            if parts[4] == "candidates":
                return self._json({"candidates": record["candidates"]})
        return self._json({"error": {"code": "not_found", "message": path}}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/api/engine/uploads":
            length = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(length) if length else b""
            name = self.headers.get("X-File-Name") or "input.pdb"
            with ENGINE.lock:
                record = ENGINE.add_upload(name, data)
            return self._json(record, HTTPStatus.CREATED)
        if path == "/api/engine/requests":
            payload = self._body()
            if not isinstance(payload, dict):
                return self._json({"error": {"code": "invalid_params", "message": "请求体不是合法 JSON"}},
                                  HTTPStatus.BAD_REQUEST)
            if payload.get("schema_version") != "ai4s-request-1":
                return self._json({"error": {"code": "invalid_params",
                                             "message": "schema_version 必须为 ai4s-request-1"}},
                                  HTTPStatus.BAD_REQUEST)
            with ENGINE.lock:
                status = ENGINE.submit(payload)
            return self._json(status, HTTPStatus.ACCEPTED)
        return self._json({"error": {"code": "not_found", "message": path}}, HTTPStatus.NOT_FOUND)


def main():
    parser = argparse.ArgumentParser(description="约定②的模拟引擎服务（不运行真实模型）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=3010, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"mock engine at http://{args.host}:{server.server_port}/api/engine/health", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
