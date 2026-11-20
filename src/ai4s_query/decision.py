# -*- coding: utf-8 -*-
"""Agreement-5 query adapter.

New records share extras.ai4s_decision_records with the kernel and WorkChain.
Legacy ai4s_decision and sidecar files remain readable for historical reports.
Node writes always pass the canonical C-module validator.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

FIELDS = ["request_id", "process_uuid", "reuse_policy", "candidate_compare_list",
          "final_decision", "reason", "timestamp"]

POLICIES = ("allow_reuse", "force_rerun", "new_sample")
ACTIONS = ("reuse", "rerun", "new_sample")

# ⑤ 2.2 理由编码 -> 允许的 action
REASON_CODES = {
    "R01": ("允许复用，存在合格候选，按规则选中一条", ("reuse",)),
    "R02": ("候选为空或全部不合格，降级为重算", ("rerun",)),
    "R03": ("用户指定强制重算，保留原参数与种子", ("rerun",)),
    "R04": ("用户指定新采样，更换种子运行", ("new_sample",)),
    "R05": ("自定义决策器给出的决定（扩展点预留）", ACTIONS),
}


def default_dir() -> Path:
    return Path(os.environ.get("AI4S_DECISIONS_DIR", Path.home() / "runs" / "decisions"))


# ---------------------------------------------------------------- 归一化

def normalize(raw: dict) -> dict:
    """补齐缺失字段（值为 None）并保留原始键，便于核对来源。"""
    rec = {k: raw.get(k) for k in FIELDS}
    fd = rec.get("final_decision") or {}
    rec["final_decision"] = {
        "action": fd.get("action"),
        "selected_candidate_uuid": fd.get("selected_candidate_uuid"),
        "effective_seed": fd.get("effective_seed"),
    }
    rs = rec.get("reason") or {}
    rec["reason"] = {
        "reason_code": rs.get("reason_code"),
        "reason_text": rs.get("reason_text"),
    }
    rec["candidate_compare_list"] = list(rec.get("candidate_compare_list") or [])
    rec["_extra"] = {k: v for k, v in raw.items() if k not in FIELDS}
    return rec


def validate(rec: dict) -> list:
    """逐条检查 ⑤ 的硬约束，返回问题列表（空列表表示通过）。"""
    problems = []
    for key in FIELDS:
        if rec.get(key) in (None, ""):
            problems.append(f"缺少必填字段 {key}")
    if rec.get("reuse_policy") and rec["reuse_policy"] not in POLICIES:
        problems.append(f"reuse_policy 取值非法：{rec['reuse_policy']}")

    action = (rec.get("final_decision") or {}).get("action")
    if action and action not in ACTIONS:
        problems.append(f"final_decision.action 取值非法：{action}")

    code = (rec.get("reason") or {}).get("reason_code")
    if code:
        if code not in REASON_CODES:
            problems.append(f"reason_code 不在枚举内：{code}")
        elif action and action not in REASON_CODES[code][1]:
            problems.append(f"reason_code {code} 不允许 action={action}")

    policy = rec.get("reuse_policy")
    if policy in ("force_rerun", "new_sample") and action == "reuse":
        problems.append(f"{policy} 不应出现 reuse")
    if policy == "new_sample" and action == "new_sample":
        seed = (rec.get("final_decision") or {}).get("effective_seed")
        if seed is None:
            problems.append("new_sample 必须给出 effective_seed")
    if action == "reuse" and not (rec.get("final_decision") or {}).get(
            "selected_candidate_uuid"):
        problems.append("reuse 必须给出 selected_candidate_uuid")

    # 候选列表里必须有不合格项的原因（若存在不合格项）
    for cand in rec["candidate_compare_list"]:
        if cand.get("qualified") is False and not cand.get("reason"):
            problems.append(f"不合格候选 {str(cand.get('uuid'))[:8]} 缺少 reason")
    return problems


def _decorate(rec: dict, source: str) -> dict:
    rec = normalize(rec)
    rec["_source"] = source
    rec["_problems"] = validate(rec)
    rec["_ok"] = not rec["_problems"]
    return rec


# ---------------------------------------------------------------- 三种来源

def _from_node(identifier, profile: str | None = None):
    """从 AiiDA 过程节点读决策记录。"""
    from aiida.orm.nodes.process.process import ProcessNode

    from . import query

    if str(identifier).startswith("req-"):
        from ai4s_workflows.decision import find_decisions_by_request
        records = find_decisions_by_request(identifier)
        if records:
            return [_decorate(item, "extras.ai4s_decision_records") for item in records]
    try:
        node = query.resolve(identifier)
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(node, ProcessNode):
        # 结果节点 -> 找它的产出过程；过程节点本身没有 creator 属性
        try:
            node = node.creator
        except Exception:  # noqa: BLE001
            return []
    if node is None:
        return []
    records = node.base.extras.get("ai4s_decision_records", [])
    if records:
        return [_decorate(item, "extras.ai4s_decision_records") for item in records]
    out = []
    for holder, name in ((getattr(node.base, "attributes", None), "attributes"),
                         (getattr(node.base, "extras", None), "extras")):
        if holder is None:
            continue
        try:
            raw = holder.get("ai4s_decision")
        except Exception:  # noqa: BLE001
            continue
        if not raw:
            continue
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            if isinstance(item, dict):
                out.append(_decorate(item, f"{name}@{profile or ''}".strip("@")))
    return out


def _from_files(identifier: str, directory: Path | None = None):
    """从旁路文件读决策记录（联调期由吴昱慧一侧写入）。"""
    directory = Path(directory) if directory else default_dir()
    if not directory.exists():
        return []
    out = []
    key = str(identifier).replace("-", "").lower()
    for path in directory.glob("*.json"):
        if key not in path.stem.replace("-", "").lower():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        items = data if isinstance(data, list) else [data]
        out.extend(_decorate(i, f"file:{path.name}") for i in items if isinstance(i, dict))
    jsonl = directory / "decisions.jsonl"
    if jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            blob = json.dumps(data, ensure_ascii=False).replace("-", "").lower()
            if key and key in blob:
                out.append(_decorate(data, "file:decisions.jsonl"))
    return out


def load(identifier: str, profile: str | None = None, directory: Path | None = None) -> dict:
    """按 request_id 或 process_uuid 或节点 UUID 读取决策记录。"""
    records, tried = [], []

    if not str(identifier or "").strip():
        return {"identifier": identifier, "profile": profile, "count": 0, "records": [],
                "sources_tried": [], "missing": "未提供标识：请给出 request_id、过程 UUID 或结果节点 UUID"}

    for loader, label in ((lambda: _from_node(identifier, profile), "节点属性"),
                          (lambda: _from_files(identifier, directory), "旁路文件")):
        found = loader()
        tried.append({"source": label, "count": len(found)})
        records.extend(found)
        if records:
            break

    return {
        "identifier": identifier,
        "profile": profile,
        "count": len(records),
        "records": records,
        "sources_tried": tried,
        "missing": None if records else
        ("该请求尚无决策记录：节点上未写 ai4s_decision，旁路目录也没有对应文件。"
         "按约定⑤，记录由决策扩展点产出；联调前请确认写入位置。"),
    }


# ---------------------------------------------------------------- 写入端（供站 ⑧）
#
# 站 ⑨ 只读；但约定⑤ 的载体一直没定稿，站 ⑧ 如果每次都为「写哪儿」来问，
# 接入就被卡住。所以这里给一个写入工具：校验通过后同时写两处，
# 站点 ⑨ 的读取顺序（attributes → 旁路文件）保证写哪边都能立刻查到。
# 载体现定稿时，只改 _targets() 的默认值，调用方不动。

STORE_ENV = "AI4S_DECISION_STORE"      # attributes / file / both
_DEFAULT_TARGETS = ("attributes", "file")


def _targets(targets=None) -> tuple:
    if targets:
        return tuple(targets)
    raw = (os.environ.get(STORE_ENV) or "both").strip().lower()
    if raw in ("attributes", "attr", "node"):
        return ("attributes",)
    if raw in ("file", "files", "dir"):
        return ("file",)
    return _DEFAULT_TARGETS


def template() -> dict:
    """空白记录骨架（给站 ⑧ 照着填，字段与 ⑤ 一致）。"""
    return {
        "request_id": "<请求编号>",
        "process_uuid": "<过程 UUID>",
        "reuse_policy": "allow_reuse",
        "candidate_compare_list": [
            {"uuid": "<候选节点 UUID>", "fingerprint": "<指纹>", "member": "<成员姓名>",
             "qualified": True, "reason": None},
        ],
        "final_decision": {"action": "reuse",
                           "selected_candidate_uuid": "<选中候选 UUID>",
                           "effective_seed": None},
        "reason": {"reason_code": "R01",
                   "reason_text": "允许复用，存在合格候选，按规则选中一条"},
        "timestamp": "2026-11-11T00:00:00Z",
    }


def _clean(record: dict) -> dict:
    return {k: v for k, v in record.items() if not str(k).startswith("_")}


def _merge(existing, record: dict) -> list:
    """按 request_id 去重：同一次请求重写就替换，不堆重复。"""
    if isinstance(existing, dict):
        seq = [existing]
    elif isinstance(existing, list):
        seq = [r for r in existing if isinstance(r, dict)]
    else:
        seq = []
    rid = record.get("request_id")
    kept = [r for r in seq if r.get("request_id") != rid]
    kept.append(record)
    return kept


def _write_file(record: dict, directory: Path | None) -> Path:
    target = Path(directory) if directory else default_dir()
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{record.get('request_id') or 'decision'}.json"
    old = None
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            old = None
    seq = _merge(old, record)
    payload = seq[0] if len(seq) == 1 else seq
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_node(ref, record: dict) -> tuple:
    """New records use the same canonical carrier as the kernel and C module."""
    from . import query
    from ai4s_workflows.decision import save_decision_record
    node = query.resolve(ref)
    save_decision_record(node, record)
    return node.uuid, "extras.ai4s_decision_records"


def save(record: dict, process=None, directory=None, targets=None, force: bool = False) -> dict:
    """校验并写入一条决策记录（站 ⑧ 用）。

    - 先按 ⑤ 校验；有问题默认**拒绝写入**（避免脏记录进库），``force=True`` 可强写。
    - 载体由 ``targets`` 或环境变量 ``AI4S_DECISION_STORE`` 决定，默认两处都写：
      extras.ai4s_decision_records + 可选旁路文件。
    """
    raw = _clean(record)
    problems = validate(normalize(raw))
    result = {"request_id": raw.get("request_id"), "written": [], "problems": problems,
              "ok": not problems, "skipped": None}
    if problems and not force:
        result["skipped"] = "校验未通过，未写入；确需写入请加 force=True"
        return result

    wanted = _targets(targets)
    if "file" in wanted:
        path = _write_file(raw, directory)
        result["written"].append(f"file:{path}")
    # attributes is a legacy CLI alias; node writes use canonical extras.
    if "extras" in wanted or "attributes" in wanted:
        ref = process or raw.get("process_uuid")
        if ref:
            uid, holder = _write_node(ref, raw)
            result["written"].append(f"{holder}@{uid}")
        else:
            result["written"].append("节点属性:跳过（未给过程节点）")
    return result
