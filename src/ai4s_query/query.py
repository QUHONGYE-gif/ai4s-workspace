# -*- coding: utf-8 -*-
"""查询模块核心：节点描述、血缘、产物与缺失信息。

实现约定（对应任务书与共用引擎指南）：
- 不使用 QueryBuilder 的 has_key / contains（SQLite profile 不支持）。
- 节点查找：uuid 等值或 like 前缀；血缘遍历用 ORM 链接 API。
- 只读，不修改任何节点。
"""
from __future__ import annotations

import hashlib

from aiida.orm import Node, QueryBuilder, load_node
from aiida.orm.nodes.process.process import ProcessNode

# 链接类型分组，用于报告归类
_INPUT_LIKE = {"input_calc", "input_work", "create", "return", "input_calcfunction",
               "input_workfunction", "call_calc", "call_work", "call_calcfunction",
               "call_workfunction"}


# ---------------------------------------------------------------- 节点定位

def _exact_uuid(candidates) -> Node | None:
    """按 uuid 精确匹配。数据库可能带或不带连字符存储，两种都试。"""
    for c in candidates:
        res = QueryBuilder().append(Node, filters={"uuid": {"==": c}}).all()
        if res:
            return res[0][0]
    return None


def resolve(identifier) -> Node:
    """按 UUID（完整或 >=8 位前缀）或 PK 定位节点。"""
    if isinstance(identifier, int):
        return load_node(identifier)
    s = str(identifier).strip()
    if s.isdigit():
        return load_node(int(s))
    if len(s) == 32 or (len(s) == 36 and "-" in s):
        node = _exact_uuid({s, s.replace("-", "")})
        if node:
            return node
    if len(s) >= 8:
        # 前缀匹配：like 按存储原样匹配，连字符原样保留与去掉两种模式都试
        hits = {}
        for pattern in {s + "%", s.replace("-", "") + "%"}:
            for row in QueryBuilder().append(
                    Node, filters={"uuid": {"like": pattern}},
                    project=["uuid", "*"]).all():
                hits[row[0]] = row[1]
        unique = list(hits.values())
        if len(unique) == 1:
            return unique[0]
        if len(unique) > 1:
            raise ValueError(f"UUID 前缀 {s} 命中 {len(unique)} 个节点，请加长前缀")
    raise ValueError(f"找不到节点：{identifier}")


# ---------------------------------------------------------------- 基础信息

def _lt(link_type) -> str:
    """LinkType 枚举 -> 字符串。"""
    return link_type.value if hasattr(link_type, "value") else str(link_type)


def _creator_uuid(node):
    """数据节点 creator；无 CREATE 链接的节点（外部输入）返回 None。"""
    try:
        c = node.creator
    except AttributeError:
        return None
    return c.uuid if c is not None else None


def _short(text, limit: int = 48) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _inline(node: Node) -> dict:
    """把节点的实际值内联成摘要，让报告里直接看到值而不是只有 UUID。

    覆盖四类最常见的输入：参数字典（Dict）、阈值（Int/Float）、
    序列（Str）、结构文件（SinglefileData / FolderData）。
    """
    nt = node.node_type.rstrip(".")  # AiiDA 的 node_type 带结尾点，如 data.core.str.Str.

    # 过程节点没有“值”可内联。注意 CalcFunctionNode 的仓库里会有一份 source_file，
    # 那是 AiiDA 为可复现保存的函数源码快照，不是该过程的取值，不能当成值显示。
    if isinstance(node, ProcessNode):
        return {"kind": "process", "text": ""}

    try:
        if nt.endswith("dict.Dict"):
            data = node.get_dict()
            pairs = []
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    pairs.append(f"{k}=<{type(v).__name__}({len(v)})>")
                else:
                    pairs.append(f"{k}={_short(v, 24)}")
            return {"kind": "dict", "value": data, "text": ", ".join(pairs)}
        if nt.endswith("list.List"):
            val = node.get_list()
            return {"kind": "list", "value": val,
                    "text": "[" + ", ".join(_short(v, 12) for v in val[:8]) + "]"}
        if nt.endswith("bool.Bool"):
            return {"kind": "bool", "value": bool(node.value), "text": str(node.value)}
        if nt.endswith("int.Int"):
            return {"kind": "int", "value": int(node.value), "text": str(node.value)}
        if nt.endswith("float.Float"):
            return {"kind": "float", "value": float(node.value), "text": str(node.value)}
        if nt.endswith("str.Str"):
            val = node.value
            return {"kind": "str", "value": val,
                    "text": f'"{_short(val)}"（{len(val)} 字符）'}
    except Exception:
        pass

    # 文件类：任何带仓库的数据节点（PDB、序列文件、产物目录）
    try:
        files = list(_iter_files(node.base.repository))
    except Exception:
        files = []
    if files:
        entry = {"path": files[0], "size": None, "sha256": None, "count": len(files)}
        try:
            raw = node.base.repository.get_object_content(files[0], mode="rb")
            entry["size"] = len(raw)
            entry["sha256"] = hashlib.sha256(raw).hexdigest()
        except Exception:
            pass
        text = entry["path"]
        if entry["size"] is not None:
            text += f"（{entry['size']}B"
            if entry["sha256"]:
                text += f", sha256={entry['sha256'][:12]}…"
            text += "）"
        if len(files) > 1:
            text += f" 等 {len(files)} 个文件"
        return {"kind": "file", "file": entry, "files": files[:10], "text": text}
    return {"kind": "unknown", "text": nt}


def _link_rows(links, direction: str):
    """把链接列表转成报告行。direction: 'in'/'out'。"""
    rows = []
    for triple in links:
        other = triple.node
        row = {
            "port": triple.link_label,
            "link_type": _lt(triple.link_type),
            "label": other.label,
            "uuid": other.uuid,
            "pk": other.pk,
            "node_type": other.node_type,
            "creator_uuid": _creator_uuid(other) if direction == "in" else None,
        }
        if direction == "in":
            row["value"] = _inline(other)
        rows.append(row)
    rows.sort(key=lambda r: (r["link_type"], r["port"]))
    return rows


def _process_info(node: Node):
    """过程节点的运行状态信息（任务书要求 1：状态与成败原因）。"""
    if not isinstance(node, ProcessNode):
        return None
    info = {
        "process_state": str(node.process_state).split(".")[-1].lower(),
        "process_state_raw": str(node.process_state),
        "process_status": getattr(node, "process_status", None),
        "is_finished_ok": node.is_finished_ok,
        "is_terminated": node.is_terminated,
        "exception": getattr(node, "exception", None),
    }
    ec = node.exit_code
    if ec is not None:
        info["exit_code"] = ec.status
        info["exit_message"] = ec.message
    else:
        info["exit_code"] = None
        info["exit_message"] = None
    # 缓存信息（任务书要求 4）
    caching = node.base.caching
    info["is_created_from_cache"] = caching.is_created_from_cache
    info["cache_source"] = caching.get_cache_source() if caching.is_created_from_cache else None
    return info


def _node_hash(node: Node):
    """节点内容哈希（校验记录）：过程节点为输入 hash，数据节点为内容 hash。"""
    try:
        return node.base.caching.get_hash()
    except Exception:
        return None


def _iter_files(repo, prefix: str = ""):
    """递归列出仓库内所有文件（ProteinMPNN 的产物是 seqs/、scores/ 子目录）。"""
    try:
        names = repo.list_object_names(prefix or None)
    except Exception:
        return
    for name in names:
        path = f"{prefix}/{name}" if prefix else name
        try:
            children = repo.list_object_names(path)
        except Exception:
            children = None
        if children:
            yield from _iter_files(repo, path)
        else:
            yield path


def _read_entry(node: Node, path: str) -> dict:
    """单个仓库文件的读取入口（任务书要求 1：提供文件读取入口）。"""
    return {
        "cli": f"verdi node repo cat {node.uuid} {path}",
        "python": f"node.base.repository.get_object_content({path!r})",
        "export": (f"python -m ai4s_query.cli cat {node.uuid} {path} "
                   f"--out {path.split('/')[-1]}"),
    }


def _artifacts(node: Node):
    """产物清单：仓库文件、大小、sha256、可读性与读取入口。

    kind 取值：text（可按文本读）/ binary（二进制，可导出）/ error（读取失败）。
    过程节点若没有仓库（如 calcfunction），返回 has_repository=False，不记为“不可读”。
    """
    info = {"has_repository": False, "error": None, "node_hash": _node_hash(node), "files": []}
    try:
        repo = node.base.repository
        names = list(_iter_files(repo))
    except AttributeError:
        return info
    except Exception as exc:
        info["error"] = repr(exc)
        return info
    info["has_repository"] = True
    is_function = isinstance(node, ProcessNode) and "function" in node.node_type
    for name in names:
        entry = {"path": name, "read": _read_entry(node, name)}
        if is_function and name == "source_file":
            # calcfunction 的仓库里只有 AiiDA 自动保存的函数源码，不是计算产物
            entry["role"] = "function_source"
            entry["note"] = ("calcfunction 源码快照（AiiDA 为可复现自动保存），"
                             "不是本次计算的产物")
        try:
            raw = repo.get_object_content(name, mode="rb")
        except Exception as exc:
            entry.update({"readable": False, "kind": "error", "error": repr(exc)})
            info["files"].append(entry)
            continue
        entry.update({
            "readable": True,
            "kind": "text",
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
        try:
            text = raw.decode("utf-8")
            entry["preview"] = " / ".join(text.splitlines()[:2])[:160]
        except UnicodeDecodeError:
            entry["kind"] = "binary"
            entry["note"] = "二进制，按文本不可读，可按字节导出"
        info["files"].append(entry)
    return info


# ---------------------------------------------------------------- 血缘

def _upstream(node: Node, max_depth: int = 10):
    """沿输入方向回溯：本节点 <- 输入 <- 产生输入的过程 <- ..."""
    seen = set()
    chain = []

    def walk(n, depth):
        if depth > max_depth or n.uuid in seen:
            return
        seen.add(n.uuid)
        for triple in n.base.links.get_incoming():
            lt = _lt(triple.link_type)
            if lt in ("input_calc", "input_work",
                      "input_calcfunction", "input_workfunction"):
                src = triple.node
                chain.append({
                    "depth": depth,
                    "via_port": triple.link_label,
                    "node_uuid": src.uuid,
                    "node_pk": src.pk,
                    "node_type": src.node_type,
                    "label": src.label,
                    "creator_uuid": _creator_uuid(src),
                })
                walk(src, depth + 1)
            elif lt.startswith("call_"):
                chain.append({
                    "depth": depth,
                    "via_port": triple.link_label + " (called)",
                    "node_uuid": triple.node.uuid,
                    "node_pk": triple.node.pk,
                    "node_type": triple.node.node_type,
                    "label": triple.node.label,
                    "creator_uuid": _creator_uuid(triple.node),
                })

    walk(node, 0)
    return chain


_USE_LINKS = {"input_calc", "input_work"}
_PRODUCE_LINKS = {"create", "return"}
_CALL_LINKS = {"call_calc", "call_work"}


def _relation(lt: str):
    """把链接类型翻译成方向语义。

    关键区别（易错点）：数据被过程使用走 input_calc / input_work，
    create 只出现在「过程 -> 输出数据」方向，return 用于工作流返回值。
    """
    if lt in _USE_LINKS:
        return "used_by"
    if lt in _PRODUCE_LINKS:
        return "produced"
    if lt in _CALL_LINKS:
        return "calls"
    return None


def _downstream(node: Node, max_depth: int = 10):
    """沿使用方向追踪：本节点的数据被哪些后续过程使用（任务书要求 2 反向）。"""
    rows = []
    seen_edge = set()
    visited = set()

    def walk(n, depth):
        if depth > max_depth or n.uuid in visited:
            return
        visited.add(n.uuid)
        for triple in n.base.links.get_outgoing():
            lt = _lt(triple.link_type)
            relation = _relation(lt)
            if relation is None:
                continue
            dst = triple.node
            key = (dst.uuid, relation, triple.link_label)
            if key not in seen_edge:
                seen_edge.add(key)
                rows.append({
                    "depth": depth,
                    "relation": relation,
                    "via_port": triple.link_label,
                    "link_type": lt,
                    "node_uuid": dst.uuid,
                    "node_pk": dst.pk,
                    "node_type": dst.node_type,
                    "label": dst.label,
                })
            walk(dst, depth + 1)

    walk(node, 0)
    rows.sort(key=lambda r: (r["depth"], r["relation"], r["node_uuid"]))
    return rows


# ---------------------------------------------------------------- 主干轨迹

def _creating_process(node: Node):
    """数据节点是由哪个过程产出的（CREATE 链接）。"""
    for triple in node.base.links.get_incoming():
        if _lt(triple.link_type) == "create":
            return triple.node
    return None


def _spine_input(proc):
    """在过程的多个输入里挑出「主干」那一个：优先选本身由上游过程产生的。"""
    ins = [t.node for t in proc.base.links.get_incoming()
           if _lt(t.link_type).startswith("input_")]
    if not ins:
        return None
    produced = [n for n in ins if _creator_uuid(n)]
    return sorted(produced or ins, key=lambda n: n.pk)[0]


def _step_process(proc) -> dict:
    params = []
    for triple in proc.base.links.get_incoming():
        if not _lt(triple.link_type).startswith("input_"):
            continue
        params.append({
            "port": triple.link_label,
            "node_type": triple.node.node_type,
            "uuid": triple.node.uuid,
            "value": _inline(triple.node),
        })
    params.sort(key=lambda r: r["port"])
    outs = [{"port": t.link_label, "node_type": t.node.node_type, "uuid": t.node.uuid}
            for t in proc.base.links.get_outgoing()
            if _lt(t.link_type) in ("create", "return")]
    return {
        "kind": "process",
        "uuid": proc.uuid,
        "pk": proc.pk,
        "node_type": proc.node_type,
        "label": proc.label,
        "process": _process_info(proc),
        "params": params,
        "outputs": outs,
    }


def _step_data(node: Node) -> dict:
    repo = _artifacts(node)
    return {
        "kind": "data",
        "uuid": node.uuid,
        "pk": node.pk,
        "node_type": node.node_type,
        "label": node.label,
        "creator_uuid": _creator_uuid(node),
        "value": _inline(node),
        "file_count": len(repo.get("files") or []),
        "node_hash": repo.get("node_hash"),
    }


def trace(identifier, max_depth: int = 12) -> list:
    """把节点所在的主干重排成一条竖线：输入 → 计算 → 产物 → 计算 → 产物。"""
    node = resolve(identifier)
    steps, seen = [], set()
    cur = node
    while cur is not None and cur.uuid not in seen and len(steps) < max_depth:
        seen.add(cur.uuid)
        if isinstance(cur, ProcessNode):
            steps.append(_step_process(cur))
            cur = _spine_input(cur)
        else:
            steps.append(_step_data(cur))
            cur = _creating_process(cur)
    steps.reverse()
    return steps


# ---------------------------------------------------------------- 汇总

def describe(identifier) -> dict:
    """生成单个节点的完整描述字典。"""
    node = resolve(identifier)
    repository = _artifacts(node)
    info = {
        "uuid": node.uuid,
        "pk": node.pk,
        "node_type": node.node_type,
        "label": node.label,
        "description": node.description,
        "ctime": str(node.ctime),
        "mtime": str(node.mtime),
        "creator_uuid": _creator_uuid(node),
        "process": _process_info(node),
        "inputs": _link_rows(node.base.links.get_incoming(), "in"),
        "outputs": _link_rows(node.base.links.get_outgoing(), "out"),
        "repository": repository,
        "checksum": {
            "node_hash": repository.get("node_hash"),
            "files": [{"path": f["path"], "size": f.get("size"), "sha256": f.get("sha256")}
                      for f in repository["files"] if f.get("sha256")],
        },
        "lineage": {
            "upstream": _upstream(node),
            "downstream": _downstream(node),
        },
        "attributes": {k: node.base.attributes.get(k)
                       for k in node.base.attributes.keys()},
        "extras": {k: node.base.extras.get(k)
                   for k in node.base.extras.keys()
                   if not k.startswith("_aiida_cached_from")},
    }
    info["issues"] = _issues(info, node)
    return info


def _log_tail(node: Node, limit: int = 800):
    """从仓库里取日志文件尾部，作为失败诊断的第一手材料。"""
    try:
        names = list(_iter_files(node.base.repository))
    except Exception:
        return None
    for name in names:
        if not name.lower().endswith((".log", ".out", ".err")):
            continue
        try:
            raw = node.base.repository.get_object_content(name, mode="rb")
            return {"path": name, "tail": raw.decode("utf-8", "replace")[-limit:]}
        except Exception:
            continue
    return None


def _issues(info: dict, node: Node) -> dict:
    """任务书要求 3：区分正式产物 / 失败诊断 / 未记录信息 / 不可读文件。"""
    issues = {"failures": [], "unrecorded": [], "unreadable_files": []}
    proc = info["process"]

    if proc is None:
        if info.get("creator_uuid") is None:
            issues["unrecorded"].append("无产生过程（外部输入或手工创建），来源不可考")
    else:
        failed = proc["process_state"] in ("excepted", "killed") or \
            (proc.get("exit_code") not in (None, 0))
        if failed:
            entry = {
                "state": proc["process_state"],
                "exit_code": proc.get("exit_code"),
                "message": proc.get("exit_message"),
                "exception": proc.get("exception"),
            }
            tail = _log_tail(node)
            if tail:
                entry["log"] = tail
            issues["failures"].append(entry)
        if proc["process_state"] == "running":
            issues["unrecorded"].append("过程尚未结束（running），当前结果不完整")
        if not info["inputs"]:
            issues["unrecorded"].append("未记录输入（无输入链接）")
        if "CalcJob" in info["node_type"] and not any(
                r["port"] == "parameters" for r in info["inputs"]):
            issues["unrecorded"].append("未记录计算参数（inputs 中没有 parameters）")

    repo = info["repository"]
    if repo.get("error"):
        issues["unreadable_files"].append("仓库整体不可读：" + str(repo["error"]))
    for f in repo["files"]:
        if f["kind"] == "error":
            issues["unreadable_files"].append(
                f"{f['path']}：读取失败 {f.get('error', '')}")
        elif f["kind"] == "binary":
            issues["unreadable_files"].append(
                f"{f['path']}：二进制产物，按文本不可读（{f.get('size')}B，可导出）")
    return issues
