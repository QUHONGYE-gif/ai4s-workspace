# -*- coding: utf-8 -*-
"""报告导出：JSON（机器可读）与文本（人可读）。"""
from __future__ import annotations

import json


def to_json(info: dict, path: str | None = None) -> str:
    text = json.dumps(info, ensure_ascii=False, indent=2, default=str)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text


def to_text(info: dict, path: str | None = None) -> str:
    lines = []
    add = lines.append

    add("=" * 62)
    add("AiiDA 节点查询报告")
    add("=" * 62)
    add(f"UUID        : {info['uuid']}")
    add(f"PK          : {info['pk']}")
    add(f"类型        : {info['node_type']}")
    add(f"标签        : {info['label'] or '(无)'}")
    add(f"创建时间    : {info['ctime']}")
    add("")

    add("[运行状态]")
    proc = info["process"]
    if proc:
        add(f"  状态           : {proc['process_state']}"
            + (f"（{proc['process_status']}）" if proc.get("process_status") else ""))
        add(f"  正常结束       : {proc['is_finished_ok']}")
        if proc.get("exit_code") is not None:
            add(f"  退出码         : {proc['exit_code']}  {proc['exit_message']}")
        if proc.get("is_created_from_cache"):
            add(f"  缓存命中       : 是（实际计算在来源节点 {proc['cache_source']}）")
        else:
            add("  缓存命中       : 否（本次为真实执行）")
    else:
        add("  （非过程节点：无运行状态，本节点为数据）")
    add("")

    failures = info["issues"].get("failures") or []
    if failures:
        add("[失败诊断]")
        for f in failures:
            add(f"  状态           : {f['state']}")
            if f.get("exit_code") is not None:
                add(f"  退出码         : {f['exit_code']}  {f.get('message') or ''}")
            if f.get("exception"):
                add(f"  异常           : {f['exception']}")
            if f.get("log"):
                add(f"  日志尾部（{f['log']['path']}）：")
                for line in f["log"]["tail"].strip().splitlines()[-8:]:
                    add(f"    | {line}")
        add("")

    add("[输入]")
    if info["inputs"]:
        for r in info["inputs"]:
            src = f" <- 由节点 {r['creator_uuid'][:12]}… 产生" if r.get("creator_uuid") else ""
            add(f"  {r['port']:<14} {r['node_type']:<28} uuid={r['uuid'][:12]}…{src}")
    else:
        add("  （无输入链接）")
    add("")

    add("[输出 / 产物]")
    if info["outputs"]:
        for r in info["outputs"]:
            add(f"  {r['port']:<14} {r['node_type']:<28} uuid={r['uuid'][:12]}…")
    else:
        add("  （无输出链接）")
    add("")

    add("[仓库文件与校验记录]")
    add(f"  节点内容哈希 : {info['checksum'].get('node_hash') or '(不可计算)'}")
    repo = info["repository"]
    if repo.get("error"):
        add(f"  仓库不可读   : {repo['error']}")
    elif not repo.get("has_repository"):
        add("  （该节点类型无仓库，例如 calcfunction 过程节点）")
    elif not repo["files"]:
        add("  （仓库为空）")
    else:
        for f in repo["files"]:
            kind = f.get("kind")
            if kind == "error":
                add(f"  {f['path']}  [读取失败] {f.get('error', '')}")
                continue
            add(f"  {f['path']}  size={f.get('size')}B  sha256={str(f.get('sha256'))[:16]}…  [{kind}]")
            if f.get("preview"):
                add(f"      预览: {f['preview']}")
            if f.get("note"):
                add(f"      说明: {f['note']}")
            add(f"      读取: {f['read']['cli']}")
    add("")

    add("[血缘 · 上游]（反查来源：从本节点回溯到最初输入）")
    if info["lineage"]["upstream"]:
        for step in info["lineage"]["upstream"]:
            add("  " + "  " * step["depth"]
                + f"^-- {step['node_type']} uuid={step['node_uuid'][:12]}…"
                + f"（端口 {step['via_port']}）")
    else:
        add("  （本节点是源头，无上游）")
    add("")

    add("[血缘 · 下游]（谁在用本节点的数据）")
    if info["lineage"]["downstream"]:
        for step in info["lineage"]["downstream"]:
            add("  " + "  " * step["depth"]
                + f"--> [{step.get('relation', '?')}] {step['node_type']}"
                + f" uuid={step['node_uuid'][:12]}…（端口 {step['via_port']}）")
    else:
        add("  （暂无下游使用）")
    add("")

    add("[缺失与不可读]")
    iss = info["issues"]
    if iss["unrecorded"]:
        add("  未记录信息：")
        for item in iss["unrecorded"]:
            add(f"    - {item}")
    if iss["unreadable_files"]:
        add("  不可读文件：")
        for item in iss["unreadable_files"]:
            add(f"    - {item}")
    if not iss["unrecorded"] and not iss["unreadable_files"]:
        add("  无：关键字段齐全，仓库可读")
    add("=" * 62)

    text = "\n".join(lines)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text
