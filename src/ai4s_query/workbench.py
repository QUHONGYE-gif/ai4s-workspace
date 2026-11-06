# -*- coding: utf-8 -*-
"""把 AiiDA 节点的查询结果导出为「研序」工作台可导入的记录文件。

研序（web/demo）的实验记录是一份前端状态 JSON，结构固定：

    {version, catalog, experiments, drafts, next, selectedWorkflow, ...}

本模块只做映射，不改动 web/ 下任何代码：
- AiiDA 的 Data 节点      -> catalog 里的产物记录（带 uuid 与内容哈希）
- AiiDA 的 Process 节点   -> 实验的 plan 步骤（区分「真实执行」与「缓存命中」）
- 一条主干轨迹           -> 一条 experiment（实验记录）

导出结果通过研序页面的「导入」按钮加载；导入会替换当前记录，因此支持
--base 参数把已有导出合并进来再追加。
"""
from __future__ import annotations

import json
import time

from . import query

WORKFLOW_ID = "protein"
WORKFLOW_NAME = "蛋白质设计流程"
OWNER_ID = "unrecorded"
OWNER_NAME = "未记录归属"

# 前端 experimentPage 直接读 e.policyRules.name / e.policyRules.storage，
# 缺这个字段会让实验详情页抛 TypeError，整页回落到「页面暂时无法显示」。
# 结构与 configs/workbench-demo.json 的 policies 保持一致。
UNRECORDED_POLICY = {
    "id": "unrecorded", "name": "未记录", "reuse": None, "storage": None,
    "description": "原生记录未提供工作台存储策略。",
}

_EXT_KIND = {
    "pdb": "PDB", "cif": "mmCIF", "fa": "FASTA", "fasta": "FASTA",
    "json": "JSON", "log": "LOG", "npz": "NumPy", "npy": "NumPy",
    "a3m": "A3M", "sdf": "SDF",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _kind_of(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _EXT_KIND.get(ext, ext.upper()[:8] or "数据")


def _status(info):
    """Keep unfinished and failed native processes distinct from success."""
    state = str(info.get("process_state") or "").split(".")[-1].lower()
    if info.get("is_finished_ok") is True:
        return "completed"
    if state in ("excepted", "killed", "finished"):
        return "failed"
    if state == "running":
        return "running"
    if state in ("created", "waiting"):
        return "waiting"
    return "unknown"


def _artifact(node, idx: int, run_id: str, step_id: str = "") -> dict:
    """Data 节点 -> catalog 产物记录。

    文件类节点（SinglefileData/FolderData）按仓库文件记录；
    标量节点（Str/Dict/Int…）没有仓库，用内联值当名称，状态仍算完整。
    """
    repo = query._artifacts(node)
    files = [f for f in repo.get("files", []) if f.get("readable")]
    inline = query._inline(node)
    has_value = inline.get("kind") != "unknown"
    if files:
        name = files[0]["path"]
    else:
        text = (inline.get("text") or "").strip()
        name = query._short(text, 40) if text else (
            node.label or node.node_type.rstrip(".").split(".")[-1])
    size_bytes = sum(f.get("size") or 0 for f in files)
    digest = repo.get("node_hash") or ""
    created = int(node.ctime.timestamp() * 1000) if node.ctime else _now_ms()
    return {
        "id": f"ART-A4S-{idx:03d}",
        "key": "ai4s-" + (digest[:12] or node.uuid[:8]),
        "workflowId": WORKFLOW_ID,
        "workflowName": WORKFLOW_NAME,
        "family": "protein",
        "stepId": step_id,
        "name": name,
        "kind": _kind_of(name) if files else "值",
        "size": round(size_bytes / (1024 * 1024), 4),
        "version": node.node_type.rstrip(".").split(".")[-1],
        "config": {},
        "deps": [],
        "parentArtifactIds": [],
        "runId": run_id,
        "ownerId": OWNER_ID,
        "ownerName": OWNER_NAME,
        "scope": "unknown",
        "status": "complete" if (files or has_value) else "missing",
        # JSON carries metadata; files remain in the source AiiDA Repository.
        "accessible": False,
        "retained": False,
        "source": "aiida",
        "pinned": False,
        "lastUsed": _now_ms(),
        "createdAt": created,
        "provenance": {
            "uuid": node.uuid,
            "pk": node.pk,
            "node_type": node.node_type,
            "node_hash": digest,
            "repository_readable": bool(files or has_value),
            "files": [{"path": f["path"], "size": f.get("size"), "sha256": f.get("sha256")}
                      for f in files],
        },
    }


def _plan_step(proc_step: dict, step_id: str, artifact_name: str | None) -> dict:
    """Process 节点 -> 实验 plan 里的一步。"""
    info = proc_step.get("process") or {}
    cached = bool(info.get("is_created_from_cache"))
    source = info.get("cache_source")
    if cached:
        action, reason = "reuse", f"缓存命中：过程未执行，结果来自 {source}"
    else:
        action = "compute"
        code = info.get("exit_code")
        state = info.get("process_state")
        reason = f"原生过程（状态 {state}" + (f"，exit_code={code}）" if code is not None else "）")
        if state in ("created", "running", "waiting"):
            action = "wait"
    label = proc_step.get("label") or proc_step.get("node_type", "").rstrip(".").split(".")[-1]
    params = {}
    for p in proc_step.get("params") or []:
        val = (p.get("value") or {}).get("value")
        if isinstance(val, (str, int, float, bool)):
            params[p["port"]] = val
        elif isinstance(val, dict):
            params.update(val)
    return {
        "id": step_id,
        "name": label,
        "file": artifact_name or "",
        "kind": _kind_of(artifact_name or ""),
        "size": 0,
        "deps": [],
        "position": "",
        "cost": 0,
        "load": 0,
        "description": reason,
        "key": "ai4s-" + proc_step["uuid"][:8],
        "valid": info.get("is_finished_ok") is True,
        "reuse": cached,
        "action": action,
        "artifact": None,
        "candidates": [],
        "time": 0,
        "reason": reason,
        "parameters": params,
        "provenance": {
            "uuid": proc_step["uuid"],
            "pk": proc_step.get("pk"),
            "node_type": proc_step.get("node_type"),
            "cached_from": source,
            "process": info,
        },
    }


def build_experiment(identifier, seq: int = 1) -> tuple[dict, list]:
    """单条主干轨迹 -> (实验记录, 产物列表)。

    关键点：研序的流程图用 `experiment.outputs` 判断一步是否完成
    （见 app.js 的 flowStepState：outputs 里有该 stepId 才算 complete）。
    所以每个过程步骤都必须登记自己的产物，且 mode 要与该步的
    action（compute/reuse）一致；否则会出现「步骤显示尚未执行」
    「缓存命中却写成本次生成」这类自相矛盾的界面。
    """
    steps = query.trace(identifier)
    run_id = f"EXP-A4S-{seq:03d}"
    base = (seq - 1) * 100
    catalog, plan, outputs = [], [], []
    art_by_uuid: dict[str, dict] = {}
    art_seq = 0

    def art_for(node, step_id: str = "") -> dict:
        """同一节点只登记一次；被过程产出时补上它所属的 stepId。"""
        nonlocal art_seq
        art = art_by_uuid.get(node.uuid)
        if art is None:
            art_seq += 1
            art = _artifact(node, base + art_seq, run_id, step_id)
            art_by_uuid[node.uuid] = art
            catalog.append(art)
        elif step_id and not art["stepId"]:
            art["stepId"] = step_id
        return art

    # 1) 数据步骤先登记为产物（第一个通常是外部输入，没有生产者）
    for step in steps:
        if step["kind"] == "data":
            art_for(query.resolve(step["uuid"]))

    # 2) 过程步骤 -> plan；产物按 create 链接挂到对应步骤上
    step_seq = 0
    prev_step_id = None
    failed_step = None
    states = []
    recorded_params = {}
    seeds = set()
    for step in steps:
        if step["kind"] != "process":
            continue
        step_seq += 1
        step_id = f"step-{base + step_seq:03d}"
        out_arts = []
        for o in step.get("outputs") or []:
            try:
                out_arts.append(art_for(query.resolve(o["uuid"]), step_id))
            except Exception:
                continue
        pstep = _plan_step(step, step_id, out_arts[0]["name"] if out_arts else None)
        pstep["deps"] = [prev_step_id] if prev_step_id else []
        pstep["artifact"] = out_arts[0]["id"] if out_arts else None
        plan.append(pstep)

        info = step.get("process") or {}
        process_status = _status(info)
        states.append(process_status)
        recorded_params[step["uuid"]] = {p["port"]: (p.get("value") or {}).get("value") for p in step.get("params", [])}
        for value in recorded_params[step["uuid"]].values():
            if isinstance(value, dict) and isinstance(value.get("seed"), (int, str)):
                seeds.add(value["seed"])
        for art in out_arts:
            art["provenance"]["role"] = "diagnostic"
            if process_status == "failed":
                art["status"] = "failed"
        if process_status == "failed":
            failed_step = step_id
        elif info.get("is_finished_ok") is True:
            for art in out_arts:
                port = next((o["port"] for o in step.get("outputs", []) if o["uuid"] == art["provenance"]["uuid"]), "")
                art["provenance"]["role"] = "diagnostic" if port in ("retrieved", "remote_folder") else "output"
                if art["provenance"]["role"] == "output":
                    outputs.append({"stepId": step_id, "artifactId": art["id"],
                                    "mode": pstep["action"]})
        prev_step_id = step_id

    status = "unknown"
    for candidate in ("failed", "running", "waiting", "unknown"):
        if candidate in states:
            status = candidate
            break
    else:
        if states:
            status = "completed"

    head = steps[0] if steps else {}
    input_name = None
    if head.get("kind") == "data":
        input_name = (head.get("value") or {}).get("text", "")
    entry = query.resolve(identifier)
    entry_uuid = entry.uuid
    title = entry.label or entry_uuid[:8]

    exp = {
        "id": run_id,
        "name": f"AiiDA 记录 {seq:02d} · {title}",
        "ownerId": OWNER_ID,
        "ownerName": OWNER_NAME,
        "workflowId": WORKFLOW_ID,
        "workflowSnapshot": {
            "name": WORKFLOW_NAME,
            "short": "蛋白质设计",
            "description": "由 AiiDA 节点自动导出的执行轨迹（真实运行记录）。",
            "template": "protein",
            "steps": [
                {"id": s["id"], "name": s["name"], "file": s.get("file", ""),
                 "kind": s.get("kind", ""), "deps": s.get("deps") or [], "cost": 0,
                 "load": 0, "size": 0}
                for s in plan
            ] or [{"id": "step-000", "name": "无计算步骤", "file": "", "kind": "", "deps": []}],
        },
        "config": {"input": input_name or entry_uuid,
                   "seed": next(iter(seeds)) if len(seeds) == 1 else None,
                   "process_inputs": recorded_params},
        "intent": "replay",
        "reuseScope": "unknown",
        "shareOutput": "unknown",
        "inputSource": "path",
        "inputArtifactId": "",
        "inputMeta": None,
        "policy": "unrecorded",
        "policyRules": dict(UNRECORDED_POLICY),
        "plan": plan,
        "outputs": outputs,
        "log": [
            "本记录由 ai4s_query 从 AiiDA 节点导出，内容为真实运行数据（非模拟）。",
            f"入口节点 UUID：{entry_uuid}",
            "产物记录里保留了节点 UUID、节点哈希与逐文件 sha256，可在终端用 ai4s_query show 复核。",
            "缓存命中的步骤标记为「复用已有结果」，其来源节点记录在 provenance.cached_from。",
        ],
        "status": status,
        "currentStep": max(len(plan) - 1, 0),
        "failedStep": failed_step,
        "fixture": False,
        "source": "aiida",
        "readOnly": True,
        "provenance": {"entry_uuid": entry_uuid, "trace_kind": "single_spine"},
        "createdAt": _now_ms(),
        # 前端「复用 / 等待 / 重算」这一行读的是 metrics.reuse / metrics.wait，
        # 不是从 plan 里数。缺字段会被 `|| 0` 兜成 0，界面上就永远显示"复用 0"。
        "metrics": {
            "total": 0,
            "compute": sum(1 for s in plan if s.get("action") == "compute"),
            "reuse": sum(1 for s in plan if s.get("action") == "reuse"),
            "wait": sum(1 for s in plan if s.get("action") == "wait"),
            "load": 0,
        },
        "storage": {"saved": 0, "evicted": 0, "skipped": 0},
    }
    return exp, catalog


def export_state(identifiers, base: dict | None = None) -> dict:
    """把若干入口节点导出为研序可导入的状态 JSON。"""
    if base:
        state = {
            "version": 1,
            "catalog": list(base.get("catalog") or []),
            "experiments": list(base.get("experiments") or []),
            "drafts": dict(base.get("drafts") or {}),
            "next": int(base.get("next") or 1),
            "selectedWorkflow": base.get("selectedWorkflow") or WORKFLOW_ID,
            "customWorkflows": dict(base.get("customWorkflows") or {}),
            "customPolicies": list(base.get("customPolicies") or []),
        }
    else:
        state = {
            "version": 1,
            "catalog": [],
            "experiments": [],
            "drafts": {},
            "next": 100,
            "selectedWorkflow": WORKFLOW_ID,
            "customWorkflows": {},
            "customPolicies": [],
        }

    used = {e["id"] for e in state["experiments"]}
    seq = 1
    for ident in identifiers:
        while f"EXP-A4S-{seq:03d}" in used:
            seq += 1
        exp, arts = build_experiment(ident, seq)
        state["experiments"].append(exp)
        state["catalog"].extend(arts)
        used.add(exp["id"])
        seq += 1

    state["next"] = max(int(state["next"]), 100 + len(state["experiments"]) * 10)
    return state


def dumps(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False, indent=2)
