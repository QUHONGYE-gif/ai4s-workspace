"""Authoritative workflow changes, validation, confirmation and request generation."""

import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

from .catalog import CATALOG, validate_params
from .files import protein
from .models import ChangeRequest, ChainPolicy, Connect, InputRef
from .storage import Problem


def uid(prefix):
    return prefix + "-" + uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def node(draft, node_id):
    for item in draft["nodes"]:
        if item["id"] == node_id:
            return item
    raise Problem(422, f"节点不存在：{node_id}")


def new_node(node_id, model_id, label):
    return {"id": node_id, "model_id": model_id, "label": label, "definition_version": "demo-1",
            "params": copy.deepcopy(CATALOG[model_id]["sample_params"]), "inputs": {},
            "design_chain_policy": None,
            "provenance": {key: {"kind": "example", "source": "内置演示值（非统一官方默认）"}
                           for key in CATALOG[model_id]["sample_params"]}}


class WorkflowService:
    def __init__(self, store):
        self.store = store

    def create(self, request):
        workflow_id = uid("wf")
        draft = {"schema_version": "0.1-demo", "id": workflow_id, "name": request.name,
                 "revision": 0, "nodes": [], "edges": []}
        if request.template == "protein":
            for model_id, node_id in (("rfdiffusion", "rfd-1"), ("proteinmpnn", "mpnn-1"), ("boltz", "boltz-1")):
                draft["nodes"].append(new_node(node_id, model_id, CATALOG[model_id]["role"] + " 1"))
            self._connect(draft, Connect(type="connect", source="rfd-1", source_port="backbone", target="mpnn-1", target_port="backbone"))
            self._connect(draft, Connect(type="connect", source="mpnn-1", source_port="sequences", target="boltz-1", target_port="sequence"))
        envelope = {"draft": draft, "messages": [], "registrations": [], "requests": [], "previews": {},
                    "operations": {}, "events": [], "last_change": None}
        with self.store.lock:
            self.store.write("workflows", workflow_id, envelope)
        return self.view(envelope)

    def _read(self, workflow_id):
        return self.store.read("workflows", workflow_id)

    def get(self, workflow_id):
        with self.store.lock:
            return self.view(self._read(workflow_id))

    def _file(self, file_id):
        info = self.store.read("files", file_id)
        path = self.store.root / "uploads" / file_id
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
            raise Problem(422, "输入文件缺失或内容已变化，请重新上传")
        return info

    def _validate_ref(self, item, port, ref):
        expected = CATALOG[item["model_id"]]["inputs"].get(port)
        if expected is None:
            raise Problem(422, f"{item['label']} 不支持输入端口 {port}")
        if ref.kind == "sequence":
            if expected != "FASTA":
                raise Problem(422, "该端口不接受直接序列")
            protein(ref.sequence)
        elif ref.kind == "file":
            metadata = self._file(ref.file_id)
            if metadata["format"] != expected:
                raise Problem(422, f"{port} 需要 {expected}，实际文件为 {metadata['format']}")
            if expected == "FASTA":
                self._record(metadata, ref.record_id)

    def _record(self, metadata, record_id):
        if not record_id:
            raise Problem(422, "请选择 FASTA 中的一条明确记录")
        for record in metadata["records"]:
            if record["id"] == record_id:
                if not record["selectable"]:
                    raise Problem(422, "检测到 ProteinMPNN 多记录输出，请选择 sample 设计记录")
                return record
        raise Problem(422, "选定的 FASTA 记录不存在")

    def _connect(self, draft, op):
        source, target = node(draft, op.source), node(draft, op.target)
        pair = (source["model_id"], op.source_port, target["model_id"], op.target_port)
        supported = {("rfdiffusion", "backbone", "proteinmpnn", "backbone"),
                     ("proteinmpnn", "sequences", "boltz", "sequence")}
        if source is target or pair not in supported:
            raise Problem(422, "不支持该端口连接（仅支持 RFD backbone→MPNN backbone 和 MPNN sequences→Boltz sequence）")
        self._disconnect(draft, op.target, op.target_port)
        ref = {"kind": "node_output", "node_id": op.source, "port": op.source_port}
        if op.record_id:
            ref["record_id"] = op.record_id
        target["inputs"][op.target_port] = ref
        draft["edges"].append({"source": op.source, "source_port": op.source_port, "target": op.target,
                               "target_port": op.target_port, "record_id": op.record_id,
                               "transform": "sequence_to_boltz_yaml" if target["model_id"] == "boltz" else None})
        self._acyclic(draft)

    def _disconnect(self, draft, target, port):
        node(draft, target)["inputs"].pop(port, None)
        draft["edges"] = [e for e in draft["edges"] if (e["target"], e["target_port"]) != (target, port)]

    def _acyclic(self, draft):
        visited, active = set(), set()

        def visit(item):
            if item in active:
                raise Problem(422, "工作流不允许形成循环")
            if item in visited:
                return
            active.add(item)
            for edge in draft["edges"]:
                if edge["source"] == item:
                    visit(edge["target"])
            active.remove(item)
            visited.add(item)
        for item in draft["nodes"]:
            visit(item["id"])

    def _apply(self, envelope, operations, origin):
        draft = envelope["draft"]
        summaries = []
        for op in operations:
            if op.type == "add_node":
                if any(n["id"] == op.node_id for n in draft["nodes"]):
                    raise Problem(422, "节点 ID 已存在")
                draft["nodes"].append(new_node(op.node_id, op.model_id, op.label))
                summaries.append(f"新增 {op.label}")
            elif op.type == "remove_node":
                item = node(draft, op.node_id)
                for edge in list(draft["edges"]):
                    if op.node_id in (edge["source"], edge["target"]):
                        self._disconnect(draft, edge["target"], edge["target_port"])
                draft["nodes"].remove(item)
                visual = draft.get("visual", {})
                visual.get("positions", {}).pop(op.node_id, None)
                visual["relations"] = [r for r in visual.get("relations", []) if op.node_id not in (r["source"], r["target"])]
                summaries.append(f"删除 {item['label']} 及其连接")
            elif op.type == "move_node":
                node(draft, op.node_id)
                draft.setdefault("visual", {}).setdefault("positions", {})[op.node_id] = {"x": op.x, "y": op.y}
                summaries.append(f"移动 {op.node_id} 到 ({op.x:g}, {op.y:g})")
            elif op.type == "set_layout":
                visual = draft.setdefault("visual", {})
                visual.update(layout=op.layout, positions={})
                summaries.append(f"重新布局：{op.layout}")
            elif op.type == "add_relation":
                source, target = node(draft, op.source), node(draft, op.target)
                if op.source_port not in CATALOG[source["model_id"]]["outputs"]:
                    raise Problem(422, "关系的来源必须是实际输出端口")
                relations = draft.setdefault("visual", {}).setdefault("relations", [])
                if any(r["id"] == op.relation_id for r in relations):
                    raise Problem(422, "关系 ID 已存在")
                relations.append({"id": op.relation_id, "source": source["id"], "source_port": op.source_port,
                                  "target": target["id"], "kind": op.kind, "label": op.label})
                summaries.append(f"添加{op.kind}设计关系：{op.label}（不绑定执行输入）")
            elif op.type == "remove_relation":
                relations = draft.setdefault("visual", {}).setdefault("relations", [])
                if not any(r["id"] == op.relation_id for r in relations):
                    raise Problem(422, "关系不存在")
                relations[:] = [r for r in relations if r["id"] != op.relation_id]
                summaries.append(f"移除设计关系 {op.relation_id}")
            elif op.type == "update_params":
                item = node(draft, op.node_id)
                validate_params(item["model_id"], {**item["params"], **op.changes})
                for key, value in op.changes.items():
                    summaries.append(f"{item['label']} · {key}：{item['params'].get(key)} → {value}")
                    item["provenance"][key] = {"kind": "user", "source": origin}
                item["params"].update(op.changes)
            elif op.type == "set_input":
                item = node(draft, op.node_id)
                if op.value and op.value.kind == "node_output":
                    self._connect(draft, Connect(type="connect", source=op.value.node_id, source_port=op.value.port,
                                                target=op.node_id, target_port=op.port, record_id=op.value.record_id))
                else:
                    if op.port not in CATALOG[item["model_id"]]["inputs"]:
                        raise Problem(422, "未知输入端口")
                    if op.value:
                        self._validate_ref(item, op.port, op.value)
                    self._disconnect(draft, op.node_id, op.port)
                    if op.value:
                        item["inputs"][op.port] = op.value.model_dump(exclude_none=True)
                summaries.append(f"{item['label']} · 更新输入 {op.port}")
            elif op.type == "set_chains":
                item = node(draft, op.node_id)
                if item["model_id"] != "proteinmpnn":
                    raise Problem(422, "只有 ProteinMPNN 使用设计链策略")
                item["design_chain_policy"] = op.policy.model_dump()
                summaries.append(f"{item['label']} · 设计链策略：{op.policy.mode}")
            elif op.type == "connect":
                self._connect(draft, op)
                summaries.append(f"连接 {op.source} → {op.target}")
            elif op.type == "disconnect":
                self._disconnect(draft, op.target, op.target_port)
                summaries.append(f"断开 {op.target} 的 {op.target_port}")
            elif op.type == "rename":
                target = node(draft, op.node_id) if op.node_id else draft
                target["label" if op.node_id else "name"] = op.name
                summaries.append(f"重命名为 {op.name}")
            elif op.type == "apply_import":
                preview = envelope["previews"].get(op.preview_id)
                item = node(draft, op.node_id)
                if not preview or item["model_id"] != preview["model_id"]:
                    raise Problem(422, "资料候选不存在或模型不匹配")
                if preview["errors"]:
                    raise Problem(422, "资料候选存在未通过的字段，请修正资料后重新识别", details=preview["errors"])
                if not preview["accepted"]:
                    raise Problem(422, "没有可应用的参数")
                changes = {p["field"]: p["value"] for p in preview["accepted"]}
                validate_params(item["model_id"], {**item["params"], **changes})
                for p in preview["accepted"]:
                    key = p["field"]
                    summaries.append(f"{item['label']} · {key}：{item['params'].get(key)} → {p['value']}")
                    item["params"][key] = p["value"]
                    item["provenance"][key] = {"kind": p["category"], "quote": p["quote"],
                                               "source": preview["source"], "preview_id": op.preview_id}
        # A chains edit is checked against any available PDB; unresolved upstream
        # chains remain a preparation issue, not a fabricated chain list.
        for item in draft["nodes"]:
            if item["model_id"] == "proteinmpnn" and item["design_chain_policy"]:
                policy = ChainPolicy.model_validate(item["design_chain_policy"])
                ref = item["inputs"].get("backbone", {})
                if policy.mode == "selected" and ref.get("kind") == "file":
                    chains = self._file(ref["file_id"])["chains"]
                    if set(policy.chains) - set(chains):
                        raise Problem(422, f"所选链不在实际 PDB 中；可用链：{list(chains)}")
        return summaries

    def preview_changes(self, workflow_id, operations):
        with self.store.lock:
            envelope = copy.deepcopy(self._read(workflow_id))
        try:
            return self._apply(envelope, operations, "Agent 提案（未保存）")
        except ValidationError as exc:
            raise Problem(422, "参数不符合模型定义", details=exc.errors(include_input=False, include_context=False)) from None

    def change(self, workflow_id, request, *, origin="用户界面"):
        with self.store.lock:
            envelope = self._read(workflow_id)
            digest = fingerprint({"kind": "changes", **request.model_dump(exclude={"operation_id"})})
            cached = self._cached(envelope, request.operation_id, digest)
            if cached:
                return {**cached, "state": self.view(envelope)}
            self._revision(envelope, request.expected_revision)
            if any(op.type in ("remove_node", "apply_import") for op in request.operations) and not request.confirmed:
                raise Problem(422, "删除或导入覆盖需要明确确认")
            before = copy.deepcopy(envelope["draft"])
            try:
                summary = self._apply(envelope, request.operations, origin)
            except ValidationError as exc:
                raise Problem(422, "参数不符合模型定义", details=exc.errors(include_input=False, include_context=False)) from None
            changed = envelope["draft"] != before
            if changed:
                envelope["draft"]["revision"] += 1
                envelope["last_change"] = {"revision": envelope["draft"]["revision"], "before": before}
                envelope["events"].append({"time": now(), "operation_id": request.operation_id, "origin": origin,
                                           "revision": envelope["draft"]["revision"], "summary": summary})
            result = {"summary": summary, "changed": changed, "revision": envelope["draft"]["revision"]}
            envelope["operations"][request.operation_id] = {"digest": digest, "result": result}
            self.store.write("workflows", workflow_id, envelope)
            return {**result, "state": self.view(envelope)}

    def _cached(self, envelope, operation_id, digest):
        cached = envelope["operations"].get(operation_id)
        if cached and cached["digest"] != digest:
            raise Problem(409, "同一操作标识不能用于不同请求")
        return cached["result"] if cached else None

    def _revision(self, envelope, expected):
        if envelope["draft"]["revision"] != expected:
            raise Problem(409, "配置已被修改，请读取最新状态后重试", details={"revision": envelope["draft"]["revision"]})

    def undo(self, workflow_id, request):
        with self.store.lock:
            envelope = self._read(workflow_id)
            digest = fingerprint({"kind": "undo", **request.model_dump(exclude={"operation_id"})})
            cached = self._cached(envelope, request.operation_id, digest)
            if cached:
                return {**cached, "state": self.view(envelope)}
            self._revision(envelope, request.expected_revision)
            last = envelope["last_change"]
            if not last or last["revision"] != request.expected_revision:
                raise Problem(409, "没有可撤销的最近一次修改")
            envelope["draft"] = last["before"]
            envelope["draft"]["revision"] = request.expected_revision + 1
            envelope["last_change"] = None
            result = {"summary": ["已撤销最近一次修改"], "revision": envelope["draft"]["revision"]}
            envelope["operations"][request.operation_id] = {"digest": digest, "result": result}
            envelope["events"].append({"time": now(), **result, "origin": "撤销"})
            self.store.write("workflows", workflow_id, envelope)
            return {**result, "state": self.view(envelope)}

    def check_node(self, draft, item):
        missing, pending = [], []
        try:
            validate_params(item["model_id"], item["params"])
        except ValidationError:
            missing.append("参数未通过模型定义检查")
        model_id = item["model_id"]
        required = {"rfdiffusion": [], "proteinmpnn": ["backbone"], "boltz": ["sequence"]}[model_id]
        if model_id == "boltz" and item["params"].get("msa_mode") == "precomputed":
            required.append("msa")
        for port in required:
            ref = item["inputs"].get(port)
            if not ref:
                missing.append(f"请提供 {port} 输入")
                continue
            try:
                ref = InputRef.model_validate(ref)
                self._validate_ref(item, port, ref)
                if ref.kind == "node_output":
                    upstream = node(draft, ref.node_id)
                    pending.append(f"{port} 等待上游输出物化")
                    if not ref.record_id:
                        # Numeric record selectors are user intentions to be
                        # checked against the actual output by the adapter.
                        missing.append(f"请选择 {port} 的上游输出记录（例如 0 或 sample=1）")
                    if upstream["model_id"] == "proteinmpnn":
                        pending.append("sequence_to_boltz_yaml 尚未接入")
            except (Problem, ValidationError) as exc:
                missing.append(exc.message if isinstance(exc, Problem) else "输入引用格式错误")
        if model_id == "proteinmpnn" and not item["design_chain_policy"]:
            missing.append("请确认设计全部链或选择部分链")
        if model_id == "proteinmpnn" and item["design_chain_policy"] and item["inputs"].get("backbone", {}).get("kind") != "file":
            pending.append("设计链需要在实际上游 PDB 上复核")
        if model_id == "boltz" and item["params"].get("msa_mode") == "precomputed" and not missing:
            seq_ref, msa_ref = item["inputs"].get("sequence", {}), item["inputs"].get("msa", {})
            if seq_ref.get("kind") != "node_output":
                seq = (protein(seq_ref["sequence"]) if seq_ref["kind"] == "sequence" else
                       self._record(self._file(seq_ref["file_id"]), seq_ref.get("record_id"))["sequence"])
                msa = self._file(msa_ref["file_id"])
                if msa["records"][0]["aligned"] != seq:
                    missing.append("A3M 首条查询序列与当前蛋白不一致")
        if model_id == "boltz":
            pending.append("Boltz YAML 生成与执行映射需适配层验证")
        return {"missing": missing, "preparation_issues": pending}

    def projection(self, draft, ids):
        selected = set(ids)
        ancestors = set()
        while True:
            more = {e["source"] for e in draft["edges"] if e["target"] in selected | ancestors} - selected - ancestors
            if not more:
                break
            ancestors |= more
        result = {"steps": [n for n in draft["nodes"] if n["id"] in selected],
                "bindings": [e for e in draft["edges"] if e["target"] in selected],
                "dependencies": [n for n in draft["nodes"] if n["id"] in ancestors]}
        relations = [r for r in draft.get("visual", {}).get("relations", [])
                     if r["source"] in selected | ancestors or r["target"] in selected | ancestors]
        if relations:
            result["design_relations"] = copy.deepcopy(relations)
        return result

    def registration_current(self, envelope, registration):
        ids = registration["node_ids"]
        if not set(ids) <= {n["id"] for n in envelope["draft"]["nodes"]}:
            return False
        return fingerprint(self.projection(envelope["draft"], ids)) == registration["fingerprint"]

    def register(self, workflow_id, request):
        with self.store.lock:
            envelope = self._read(workflow_id)
            digest = fingerprint({"kind": "register", **request.model_dump(exclude={"operation_id"})})
            cached = self._cached(envelope, request.operation_id, digest)
            if cached:
                return {**cached, "state": self.view(envelope)}
            self._revision(envelope, request.expected_revision)
            draft = envelope["draft"]
            ids = request.node_ids if request.node_ids is not None else [n["id"] for n in draft["nodes"]]
            if not ids or len(ids) != len(set(ids)):
                raise Problem(422, "请选择至少一个不重复的节点")
            problems = {i: self.check_node(draft, node(draft, i))["missing"] for i in ids}
            if any(problems.values()):
                raise Problem(422, "配置仍有缺项，暂不能登记", details=problems)
            snapshot = self.projection(draft, ids)
            registration = {"id": uid("reg"), "time": now(), "node_ids": ids, "revision": draft["revision"],
                            "snapshot": snapshot, "fingerprint": fingerprint(snapshot)}
            envelope["registrations"].append(registration)
            result = {"registration": registration}
            envelope["operations"][request.operation_id] = {"digest": digest, "result": result}
            self.store.write("workflows", workflow_id, envelope)
            return {**result, "state": self.view(envelope)}

    def generate(self, workflow_id, registration_id):
        with self.store.lock:
            envelope = self._read(workflow_id)
            registration = next((r for r in envelope["registrations"] if r["id"] == registration_id), None)
            if not registration or not self.registration_current(envelope, registration):
                raise Problem(409, "登记不存在或相关配置已变化，请重新确认登记")
            issues = ["adapter_not_connected", "execution_profile_unverified"]
            relations = registration["snapshot"].get("design_relations", [])
            if relations:
                issues.append("design_relations_not_executable")
            for item in registration["snapshot"]["steps"]:
                checked = self.check_node(envelope["draft"], item)
                if checked["missing"]:
                    raise Problem(422, "登记后的输入准备情况已变化", details=checked)
                issues.extend(checked["preparation_issues"])
            result = {"id": uid("req"), "schema_version": "0.1-demo", "workflow_id": workflow_id,
                      "workflow_revision": registration["revision"], "generated_at_revision": envelope["draft"]["revision"],
                      "registration_id": registration_id, "configuration_status": "validated",
                      "execution_status": "not_submitted", "ready_for_submission": False,
                      "adapter": {"target_engine": "aiida", "connection_status": "not_connected"},
                      "blocking_issues": list(dict.fromkeys(issues)),
                      "scope": {"node_ids": registration["node_ids"]},
                      "steps": [{**n, "code_identity": CATALOG[n["model_id"]]["code_identity"], "execution_profile": None}
                                for n in registration["snapshot"]["steps"]],
                      "bindings": registration["snapshot"]["bindings"], "design_relations": relations}
            envelope["requests"].append(result)
            self.store.write("workflows", workflow_id, envelope)
            return {"request": result, "state": self.view(envelope)}

    def save_preview(self, workflow_id, request, extracted, usage):
        accepted, errors, seen = [], [], set()
        for parameter in extracted.parameters:
            p = parameter.model_dump()
            if p["field"] in seen:
                errors.append(f"重复字段：{p['field']}")
                continue
            seen.add(p["field"])
            if not p["quote"].strip() or p["quote"] not in request.content:
                errors.append(f"{p['field']} 的原文依据不在所提供资料中")
                continue
            if p["category"] == "unknown":
                errors.append(f"{p['field']} 的值没有明确依据")
                continue
            try:
                validate_params(request.model_id, {p["field"]: p["value"]}, partial=True)
            except ValidationError:
                errors.append(f"不支持的字段或非法值：{p['field']}")
                continue
            accepted.append(p)
        preview = {"id": uid("preview"), "model_id": request.model_id, "content": request.content,
                   "source": request.source, "time": now(), "accepted": accepted, "errors": errors,
                   "notes": extracted.notes, "usage": usage}
        with self.store.lock:
            envelope = self._read(workflow_id)
            envelope["previews"][preview["id"]] = preview
            self.store.write("workflows", workflow_id, envelope)
        return preview

    def view(self, envelope):
        draft = copy.deepcopy(envelope["draft"])
        checks = {n["id"]: self.check_node(draft, n) for n in draft["nodes"]}
        registrations = [{**r, "current": self.registration_current(envelope, r)} for r in envelope["registrations"]]
        for n in draft["nodes"]:
            confirmed = any(r["current"] and n["id"] in r["node_ids"] for r in registrations)
            checks[n["id"]]["status"] = "待补充" if checks[n["id"]]["missing"] else ("已登记" if confirmed else "待登记")
        return {"draft": draft, "checks": checks, "registrations": registrations,
                "requests": [{**r, "stale": r["generated_at_revision"] != draft["revision"]} for r in envelope["requests"]],
                "messages": envelope["messages"], "events": envelope["events"][-30:],
                "can_undo": bool(envelope["last_change"] and envelope["last_change"]["revision"] == draft["revision"])}
