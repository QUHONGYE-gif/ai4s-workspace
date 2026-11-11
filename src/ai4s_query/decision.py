# -*- coding: utf-8 -*-
"""约定⑤ 决策记录的读取与校验（开发任务 4.0 · 站 9）。

约定⑤ 规定了记录的 7 个字段，但没有规定存放载体；因此本模块只做「适配」，
把任意来源归一化成 ⑤ 的结构，接口层（server）不必关心记录从哪来。

支持三种来源，按顺序尝试：
1. 过程节点 attributes 的 ``ai4s_decision``（推荐：天然绑定 process_uuid）；
2. 过程节点 extras 的同名键；
3. 旁路文件：``<decisions-dir>/<request_id>.json``、``<process_uuid>.json``、
   或 ``decisions.jsonl`` 一行一条。

只读；找不到记录时返回空列表并给出 ``missing`` 原因，绝不编造。
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
