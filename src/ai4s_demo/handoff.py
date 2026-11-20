"""Immutable registration-to-experiment view. Does not alter registrations."""
import copy
import hashlib

from .catalog import CATALOG
from .service import fingerprint
from .storage import Problem

FILTER_FIELDS = [{"key": "filter_count", "label": "筛选数量", "type": "number",
                  "min": 1, "max": 512, "step": 1, "default": 5,
                  "category": "filter", "required": True,
                  "description": "按已有序列记录顺序保留前 N 条；模拟筛选，不计算科学评分。"}]


MAX_EXPERIMENT_STEPS = 64


def build_workflow(name, snapshot, source, file_loader=None):
    nodes = snapshot["steps"]
    nodes = list({n["id"]: n for n in snapshot.get("dependencies", []) + nodes}.values())
    pending = {n["id"]: n for n in nodes}
    ordered = []
    while pending:
        ready = [n for n in pending.values() if all(r.get("node_id") not in pending
                 for r in n.get("inputs", {}).values() if r.get("kind") == "node_output")]
        if not ready:
            raise Problem(422, "登记快照存在循环依赖")
        for n in ready:
            ordered.append(n)
            del pending[n["id"]]
    reserved = {n["id"] for n in nodes}

    def synthetic_id(preferred):
        candidate, suffix = preferred, 2
        while candidate in reserved:
            candidate = f"{preferred}-{suffix}"
            suffix += 1
        reserved.add(candidate)
        return candidate

    def input_identity(ref):
        ref = copy.deepcopy(ref)
        if ref.get("kind") == "file":
            if file_loader is None:
                raise Problem(422, "登记输入缺少文件内容校验，无法交接")
            metadata = file_loader(ref.pop("file_id"))
            ref.update(sha256=metadata["sha256"], format=metadata["format"])
        elif ref.get("kind") == "sequence":
            sequence = "".join(ref.pop("sequence").split()).upper()
            ref["sha256"] = hashlib.sha256(sequence.encode()).hexdigest()
        return ref

    steps, defaults = [], {"input": "registered-input", "seed": 42, "remote": False}
    for n in ordered:
        model = CATALOG[n["model_id"]]
        fields = []
        for field in model["fields"]:
            key = f"{n['id']}__{field['key']}"
            fields.append({**field, "key": key, "modelKey": field["key"],
                           "default": n["params"][field["key"]], "category": "inference",
                           "required": True, "provenance": n.get("provenance", {}).get(field["key"])})
            defaults[key] = n["params"][field["key"]]
        port, kind = next(iter(model["outputs"].items()))
        kind = "mmCIF" if kind == "CIF" else kind
        deps = list(dict.fromkeys(r["node_id"] for r in n.get("inputs", {}).values()
                                 if r.get("kind") == "node_output"))
        step = {"id": n["id"], "name": f"{model['name']} · {n['label']}", "model": n["model_id"],
                "parameters": fields, "paramKeys": [f["key"] for f in fields],
                "file": f"{n['id']}.{ {'PDB':'pdb','FASTA':'fasta','mmCIF':'cif'}.get(kind,'json')}",
                "kind": kind, "deps": deps, "cost": 120, "load": 3, "size": 0.01,
                "icon": "grid" if n["model_id"] == "proteinmpnn" else "atom",
                "inputs": copy.deepcopy(n.get("inputs", {})), "inputRequirements": model["inputs"],
                "inputIdentity": {port: input_identity(ref) for port, ref in sorted(n.get("inputs", {}).items())},
                "chainPolicy": copy.deepcopy(n.get("design_chain_policy")),
                "codeIdentity": model["code_identity"], "description": model["scenario"]}
        steps.append(step)
        if n["model_id"] == "proteinmpnn":
            filter_id = synthetic_id(n["id"] + "-filter")
            fields = [{**f, "key": f"{filter_id}__{f['key']}", "modelKey": f["key"]} for f in FILTER_FIELDS]
            defaults.update({f["key"]: f["default"] for f in fields})
            steps.append({"id": filter_id, "name": "序列筛选", "model": "sequence_filter", "parameters": fields,
                          "paramKeys": [f["key"] for f in fields], "deps": [n["id"]], "file": "selected.fasta",
                          "kind": "FASTA", "icon": "file", "cost": 1, "load": 1, "size": 0.001,
                          "inputRequirements": {"sequences": "FASTA"},
                          "description": "保留前 N 条已有序列；筛选记录为模拟数据，不代表科学评分。"})
    # Preserve model bindings; the final workbench report joins the terminal branches.
    if steps:
        consumed = {dep for step in steps for dep in step['deps']}
        terminals = [step for step in steps if step['id'] not in consumed]
        analysis_id = synthetic_id('result-analysis')
        steps.append({'id': analysis_id, 'name': '结果分析', 'model': 'result_analysis',
                      'parameters': [], 'paramKeys': [], 'deps': [s['id'] for s in terminals],
                      'file': 'summary.json', 'kind': 'JSON', 'icon': 'file',
                      'cost': 1, 'load': 1, 'size': 0.001, 'codeIdentity': 'result-summary-v1',
                      'inputRequirements': {s['id']: s['kind'] for s in terminals},
                      'description': '汇总本次流程的产物来源、序列数量和结构输出。仅展示模拟记录，不计算科学评分或模型置信度。'})
    if len(steps) > MAX_EXPERIMENT_STEPS:
        raise Problem(422, f"展开后的实验步骤超过 {MAX_EXPERIMENT_STEPS} 个，请减少登记节点")
    profiles = [{"id": s["id"], "version": s.get("codeIdentity", "filter-v1"), "command": "simulation-only",
                 "modelPath": s["model"], "input": ",".join(s.get("inputRequirements", {}).values()),
                 "output": s["file"]} for s in steps]
    identity = fingerprint({'source': source, 'view_version': 3})[:20]
    return {"id": "registered-" + identity, "name": name, "short": name, "template": "custom", "custom": True,
            "english": "REGISTERED WORKFLOW", "tags": ["登记参数", "实验配置", "模拟执行"], "color": "green",
            "description": "读取不可变登记快照；实验修改与登记默认值分开保存。", "steps": steps,
            "defaults": defaults, "registrationSource": source,
            "executionDefinition": {"inputPath": "registered-input", "environment": "simulation",
                                    "steps": profiles}}


def registrations(service):
    result = []
    with service.store.lock:
        for path in sorted((service.store.root / "workflows").glob("*.json")):
            envelope = service._read(path.stem)
            for registration in envelope["registrations"]:
                if service.registration_current(envelope, registration):
                    result.append(build_workflow(envelope["draft"]["name"], registration["snapshot"],
                        {"kind": "registration", "workflowId": envelope["draft"]["id"],
                         "registrationId": registration["id"], "revision": registration["revision"],
                         "fingerprint": registration["fingerprint"]}, service._file))
    return result
