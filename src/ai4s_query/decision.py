# -*- coding: utf-8 -*-
"""约定⑤ 决策记录的读取与校验（开发任务 4.0 · 站 9）。

约定⑤ 规定了记录的 7 个字段，但没有规定存放载体；因此本模块只做「适配」，
把任意来源归一化成 ⑤ 的结构，接口层（server）不必关心记录从哪来。

支持三种来源，按顺序尝试：
1. 过程节点 extras 的 ``ai4s_decision``（**实际可用**：sealed 节点的 extras 仍可写）；
2. 过程节点 attributes 的同名键（仅对未 seal 的过程有效，实际较少见）；
3. 旁路文件：``<decisions-dir>/<request_id>.json``、``<process_uuid>.json``、
   或 ``decisions.jsonl`` 一行一条。

为什么不是 attributes：过程节点一旦终止就会 seal，sealed 节点的 attributes 不可再改
（``ModificationNotAllowed: attributes of a sealed node are immutable``），
而 extras 不受此限制。这一点是接站 ⑧ 时实测出来的，写在这里免得多试一次。

只读；找不到记录时返回空列表并给出 ``missing`` 原因，绝不编造。
写入端见 ``save()``：校验通过后同时写节点与旁路文件，载体现定稿只改 ``_targets()``。
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
    """把记录挂到过程节点上，返回 (uuid, 载体名)。

    这里有个硬约束：**过程节点一旦终止就 seal，sealed 节点的 attributes 不可再改**
    （ModificationNotAllowed: attributes of a sealed node are immutable）。
    所以 attributes 那条路只对未 seal 的节点有效；实际能写的是 ``extras``——
    extras 不受 seal 限制，读取端也一并读它，因此优先写 extras。
    """
    from aiida.orm.nodes.process.process import ProcessNode

    from . import query

    node = query.resolve(ref)
    if not isinstance(node, ProcessNode):
        try:
            node = node.creator
        except Exception:  # noqa: BLE001
            node = None
    if node is None:
        raise ValueError(f"{ref} 不是过程节点，也没有产出过程，无法写入决策记录")

    def _read(holder):
        try:
            return holder.get("ai4s_decision")
        except (AttributeError, KeyError):
            return None

    # 先 extras（sealed 节点也允许），实在不行再 attributes（仅未 seal 的过程）
    for holder, label in ((node.base.extras, "extras"), (node.base.attributes, "attributes")):
        try:
            holder.set("ai4s_decision", _merge(_read(holder), record))
            return node.uuid, label
        except Exception:  # noqa: BLE001  含 ModificationNotAllowed
            continue
    raise RuntimeError("过程节点 attributes 与 extras 均不可写（节点状态异常）")


def save(record: dict, process=None, directory=None, targets=None, force: bool = False) -> dict:
    """校验并写入一条决策记录（站 ⑧ 用）。

    - 先按 ⑤ 校验；有问题默认**拒绝写入**（避免脏记录进库），``force=True`` 可强写。
    - 载体由 ``targets`` 或环境变量 ``AI4S_DECISION_STORE`` 决定，默认两处都写：
      attributes（随节点走）+ 旁路文件（不依赖内核改造）。
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
    if "attributes" in wanted:
        ref = process or raw.get("process_uuid")
        if ref:
            uid, holder = _write_node(ref, raw)
            result["written"].append(f"{holder}@{uid}")
        else:
            result["written"].append("节点属性:跳过（未给过程节点）")
    return result
