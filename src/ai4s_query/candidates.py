# -*- coding: utf-8 -*-
"""跨成员候选查找（开发任务 4.0 · 站 5）。

职责：把「候选查找」从只查本人数据库，扩展到共享范围，并按约定④返回候选列表。
共享方式：多库查找 —— 一个 AiiDA profile 视为一位成员，逐个 profile 用同一条
指纹查询，结果合并。理由与对比见 docs/task4-shared-scope.md。

实现要点（都是踩过的坑）：
- 指纹取自节点 extras 的 ``_aiida_hash``，这是 AiiDA 写入缓存键的原始字段；
  用 JSON 路径等值过滤（``filters={"extras._aiida_hash": {"==": fp}}``），
  SQLite 后端可用，已验证。
- profile 切换是进程级全局状态，因此查询串行执行，并在结束时切回原 profile。
- 只读：不写节点、不改属性、不触发重算。
"""
from __future__ import annotations

import contextlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import query

# 约定④ 3.3 的不合格原因枚举
REASONS = {
    "missing_file": "产物文件缺失或不可读",
    "format_error": "产物格式无法解析",
    "insufficient": "结果条数不足",
    "below_threshold": "未达质量阈值",
    "not_finished": "过程未正常结束（excepted／killed）",
    "manual_reject": "人工否决",
}

_FASTA_SUFFIX = (".fa", ".fasta", ".faa", ".fas")
_SCORE_RE = re.compile(r"score\s*=\s*(-?\d+(?:\.\d+)?)")


# ---------------------------------------------------------------- 成员与 profile

def _member_map() -> dict:
    """profile 名 -> 成员姓名。

    优先级：环境变量 ``AI4S_MEMBERS``（JSON）> 模块同目录 members.json > profile 名。
    这是跨库场景里唯一的「人」来源：节点本身只记 user_id，不记姓名。
    """
    import json

    for raw in (os.environ.get("AI4S_MEMBERS"),):
        if raw:
            try:
                return {str(k): str(v) for k, v in json.loads(raw).items()}
            except Exception:  # noqa: BLE001
                pass
    path = Path(__file__).with_name("members.json")
    if path.exists():
        try:
            return {str(k): str(v) for k, v in
                    json.loads(path.read_text(encoding="utf-8")).items()}
        except Exception:  # noqa: BLE001
            pass
    return {}


def _profile_names() -> list:
    from aiida.manage.configuration import get_config

    return [p.name for p in get_config().profiles]


def _current_profile() -> str | None:
    try:
        from aiida.manage import get_manager

        prof = get_manager().get_profile()
        return prof.name if prof is not None else None
    except Exception:  # noqa: BLE001
        return None


@contextlib.contextmanager
def using_profile(name: str):
    """临时切到另一个 profile，退出时切回。避免调用方残留全局状态。

    关键点：``load_profile`` 默认 ``allow_switch=False``，跨成员查找必然抛
    ``InvalidOperation: cannot switch to profile ...``；必须显式传 True。
    """
    prev = _current_profile()
    if prev == name:
        yield
        return
    from aiida import load_profile

    try:
        load_profile(name, allow_switch=True)
    except TypeError:  # 旧版本没有该关键字
        load_profile(name)
    try:
        yield
    finally:
        if prev and prev != name:
            with contextlib.suppress(Exception):
                load_profile(prev, allow_switch=True)


# ---------------------------------------------------------------- 指纹

def fingerprint_of(node) -> str | None:
    """计算指纹。优先取 extras 里 AiiDA 写入的缓存键，取不到时现算。"""
    try:
        fp = node.base.extras.get("_aiida_hash")
        if fp:
            return str(fp)
    except Exception:  # noqa: BLE001
        pass
    with contextlib.suppress(Exception):
        return node.base.caching.get_hash()
    return None


# ---------------------------------------------------------------- 产物定位

def _output_nodes(proc) -> list:
    """过程产出的数据节点（create / return 链接）。"""
    from aiida.orm import Node

    outs = []
    for triple in proc.base.links.get_outgoing():
        if query._lt(triple.link_type) in ("create", "return") and isinstance(triple.node, Node):
            outs.append(triple.node)
    return outs


def _primary_file(node):
    """在产物节点的仓库里挑一个「代表文件」。

    优先级：design.fa / seqs/*.fa（ProteinMPNN 约定）> 目录中最小的文本文件 > 第一个文件。
    返回 (path, size, sha256) 或 None。
    """
    try:
        names = list(query._iter_files(node.base.repository))
    except Exception:  # noqa: BLE001
        return None
    if not names:
        return None
    pref = [n for n in names if n.lower().endswith(_FASTA_SUFFIX)]
    if not pref:
        pref = [n for n in names if not n.lower().endswith((".npz", ".pt", ".bin"))] or names
    name = sorted(pref, key=lambda n: (0 if "design" in n.lower() else 1, len(n)))[0]
    entry = {"path": name, "size": 0, "sha256": None}
    try:
        raw = node.base.repository.get_object_content(name, mode="rb")
        import hashlib

        entry["size"] = len(raw)
        entry["sha256"] = hashlib.sha256(raw).hexdigest()
    except Exception:  # noqa: BLE001
        pass
    return entry


def _bundle(proc) -> dict:
    """汇总一次过程的全部产物：总字节数、代表文件、FASTA 条数与最优分数。

    注意「仅有值」的情形：calcfunction 产出 Dict/Int 这类节点时没有仓库文件，
    约定④ 允许其作为候选存在（size_bytes 记 0，note 写“仅值”），
    因此 out_count > 0 且 file_count = 0 不能判为 missing_file。
    """
    total, files, seq_count, scores = 0, [], 0, []
    outs = _output_nodes(proc)
    for node in outs:
        try:
            names = list(query._iter_files(node.base.repository))
        except Exception:  # noqa: BLE001
            continue
        for name in names:
            try:
                raw = node.base.repository.get_object_content(name, mode="rb")
            except Exception:  # noqa: BLE001
                continue
            total += len(raw)
            files.append({"node_uuid": node.uuid, "path": name, "size": len(raw)})
            if name.lower().endswith(_FASTA_SUFFIX):
                text = raw.decode("utf-8", "replace")
                seq_count += sum(1 for ln in text.splitlines() if ln.startswith(">"))
                scores.extend(float(m) for m in _SCORE_RE.findall(text))
    primary = None
    for node in outs:
        primary = _primary_file(node)
        if primary:
            primary["node_uuid"] = node.uuid
            break
    return {
        "out_count": len(outs),
        "size_bytes": total,
        "file_count": len(files),
        "files": files,
        "primary": primary,
        "seq_count": seq_count,
        "best_score": min(scores) if scores else None,
    }


# ---------------------------------------------------------------- 合格判定

def _elapsed(proc, cached: bool) -> float:
    if cached:
        return 0
    with contextlib.suppress(Exception):
        return round((proc.mtime - proc.ctime).total_seconds(), 1)
    return 0


def qualify(proc, bundle: dict, request: dict | None = None):
    """约定④ 3.1 的五级判定：任一级不通过即停，返回 (是否合格, 原因枚举, 说明)。"""
    request = request or {}
    info = query._process_info(proc) or {}

    # 1 结束状态
    if info.get("process_state") != "finished" or (info.get("exit_code") not in (None, 0)):
        detail = info.get("exit_message") or info.get("exception") or info.get("process_state")
        return False, "not_finished", f"not_finished: {detail}"

    # 2 文件可用（「仅有值」的结果不算缺失：④ 允许 size_bytes=0 + note「仅值」）
    if bundle.get("out_count", 0) == 0:
        return False, "missing_file", "missing_file: 过程没有产出任何结果节点"
    if bundle["file_count"] > 0 and bundle["size_bytes"] == 0:
        return False, "format_error", "format_error: 产物为空，无法解析"

    # 3 完整性（只对有序列文件的结果适用）
    want = request.get("num_sequences")
    if want and bundle["seq_count"] and bundle["seq_count"] < int(want):
        return False, "insufficient", \
            f"insufficient: 仅 {bundle['seq_count']} 条序列 < 要求 {want} 条"

    # 4 质量门限（蛋白设计：分数越低越好，按升序取前 N）
    thr = request.get("score_threshold")
    if thr is not None and bundle["best_score"] is not None:
        if float(bundle["best_score"]) > float(thr):
            return False, "below_threshold", \
                f"below_threshold: 最优分数 {bundle['best_score']} > 阈值 {thr}"

    # 5 人工复核
    if request.get("manual_reject"):
        return False, "manual_reject", \
            f"manual_reject: {request.get('manual_reject_reason') or '人工否决'}"

    return True, None, None


# ---------------------------------------------------------------- 候选构造

def build_candidate(proc, profile: str, request: dict | None = None) -> dict:
    """按约定④ 的字段构造一条候选记录。"""
    members = _member_map()
    info = query._process_info(proc) or {}
    cached = bool(info.get("is_created_from_cache"))
    bundle = _bundle(proc)
    ok, reason, reason_text = qualify(proc, bundle, request)

    primary = bundle["primary"] or {}
    node_uuid = primary.get("node_uuid") or proc.uuid
    location = f"profile://{profile}/{node_uuid}/{primary.get('path', '')}".rstrip("/")

    note = []
    if cached:
        note.append(f"cached_from={info.get('cache_source')}")
    if bundle["size_bytes"] == 0:
        note.append("仅值（无文件产物）")

    cand = {
        # —— 约定④ 的 9 个字段
        "uuid": node_uuid,
        "fingerprint": fingerprint_of(proc),
        "member": members.get(profile, profile),
        "location": location,
        "size_bytes": bundle["size_bytes"],
        "elapsed_s": _elapsed(proc, cached),
        "qualified": ok,
        "reason": reason_text,
        "note": "; ".join(note),
        # —— 扩展字段：供约定⑤ 引用与人工核对，不改变 ④ 的语义
        "process_uuid": proc.uuid,
        "process_pk": proc.pk,
        "process_label": proc.label,
        "process_state": info.get("process_state"),
        "profile": profile,
        "cached": cached,
        "cached_from": info.get("cache_source"),
        "seq_count": bundle["seq_count"],
        "best_score": bundle["best_score"],
        "created": str(proc.ctime),
    }
    return cand


# ---------------------------------------------------------------- 查询入口

def _match_fp(node_hash, fingerprint) -> bool:
    """指纹匹配。支持完整 64 位与前缀（界面展示只给前 16 位）。

    不用 ``filters={"extras._aiida_hash": {"like": ...}}``：JSON 路径上的 like
    在 sqlite_dos 后端行为不稳定，改为取回 extras 后在 Python 侧比对，
    节点规模（数百）下开销可忽略。
    """
    if not fingerprint:
        return True
    if not node_hash:
        return False
    h = str(node_hash)
    return h == fingerprint or h.startswith(fingerprint)


def find(fingerprint: str | None = None,
         profiles: list | None = None,
         request: dict | None = None,
         include_unqualified: bool = True,
         max_per_profile: int = 50) -> dict:
    """在共享范围内查找候选。

    fingerprint 为空时，返回范围内全部过程（用于「看全貌」，不作为复用依据）；
    给前缀时按前缀匹配。
    """
    from aiida.orm import QueryBuilder, load_node
    from aiida.orm.nodes.process.process import ProcessNode

    names = profiles or _profile_names()
    members = _member_map()
    cands, errors = [], []

    for name in names:
        try:
            with using_profile(name):
                rows = QueryBuilder().append(
                    ProcessNode, project=["pk", "extras"]).all()
                pks = [pk for pk, extras in rows
                       if _match_fp((extras or {}).get("_aiida_hash"), fingerprint)]
                pks = pks[:max_per_profile]
                for pk in pks:
                    proc = load_node(pk)
                    cand = build_candidate(proc, name, request)
                    if cand["qualified"] or include_unqualified:
                        cands.append(cand)
        except Exception as exc:  # noqa: BLE001
            errors.append({"profile": name, "error": f"{type(exc).__name__}: {exc}"})

    # 合格优先，其次按最优分数升序（分数越低越好），再按时间新到旧
    cands.sort(key=lambda c: (not c["qualified"],
                              c["best_score"] if c["best_score"] is not None else 9e9,
                              c["created"]),
               reverse=False)

    return {
        "fingerprint": fingerprint,
        "scope": {
            "mode": "multi-profile",
            "profiles": names,
            "members": {n: members.get(n, n) for n in names},
        },
        "request": request or {},
        "count": len(cands),
        "qualified_count": sum(1 for c in cands if c["qualified"]),
        "reasons": REASONS,
        "candidates": cands,
        "errors": errors,
        "queried_at": datetime.now(timezone.utc).isoformat(),
    }


def by_node(identifier, request: dict | None = None) -> dict:
    """以某个结果节点为参照，按它的指纹去找跨成员候选。

    注意：所有属性必须在调用 find() 之前读完。find 会切换 profile，
    切换后原先的节点对象会与存储会话脱钩，再访问 uuid 会抛异常。
    """
    node = query.resolve(identifier)
    try:
        creator = node.creator  # 数据节点才有产出者；过程节点会抛 AttributeError
    except Exception:  # noqa: BLE001
        creator = None
    ref = {
        "input": str(identifier),
        "uuid": node.uuid,
        "process_uuid": creator.uuid if creator is not None else node.uuid,
        "fingerprint": fingerprint_of(creator) if creator is not None else fingerprint_of(node),
    }
    out = find(fingerprint=ref["fingerprint"], request=request)
    out["reference"] = ref
    return out


def text_view(result: dict) -> str:
    """把候选列表渲染成终端可读的表格（现场演示用）。"""
    lines = []
    scope = result["scope"]
    lines.append(f"指纹 {result.get('fingerprint') or '（未指定，列出全部过程）'}")
    lines.append(f"范围 {scope['mode']}：{'、'.join(scope['profiles'])}")
    lines.append(f"候选 {result['count']} 条，其中合格 {result['qualified_count']} 条")
    lines.append("")
    header = f"{'成员':<6} {'合格':<4} {'产物':<34} {'大小':>9} {'耗时':>7}  原因"
    lines.append(header)
    lines.append("-" * len(header))
    for c in result["candidates"]:
        ok = "是" if c["qualified"] else "否"
        loc = c["location"].replace("profile://", "")
        if len(loc) > 33:
            loc = loc[:30] + "..."
        lines.append(f"{c['member']:<6} {ok:<4} {loc:<34} "
                     f"{c['size_bytes']:>9} {c['elapsed_s']:>7}  {c['reason'] or ''}")
    if result["errors"]:
        lines.append("")
        for e in result["errors"]:
            lines.append(f"[跳过] {e['profile']}: {e['error']}")
    return "\n".join(lines)
