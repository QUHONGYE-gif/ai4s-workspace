# -*- coding: utf-8 -*-
"""命令行入口。

用法（在已激活的 AiiDA 环境中）：
  python -m ai4s_query.cli show <UUID或PK> [--json 出.json] [--text 出.txt]
  python -m ai4s_query.cli tree <UUID或PK> [--depth 5]
  python -m ai4s_query.cli cat  <UUID或PK> <仓库路径> [--out 导出文件]
"""
from __future__ import annotations

import argparse
import sys

from . import query, report


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ai4s-query", description="AiiDA 运行结果与来源查询")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show", help="输出单节点完整报告")
    p_show.add_argument("identifier", help="UUID（完整或前缀）或 PK")
    p_show.add_argument("--json", dest="json_path", help="导出 JSON 到此路径")
    p_show.add_argument("--text", dest="text_path", help="导出可读报告到此路径")

    p_tree = sub.add_parser("tree", help="打印血缘树（上游+下游）")
    p_tree.add_argument("identifier", help="UUID（完整或前缀）或 PK")
    p_tree.add_argument("--depth", type=int, default=5, help="递归深度（默认 5）")

    p_cat = sub.add_parser("cat", help="读取节点的仓库文件（文本直接打印，二进制用 --out 导出）")
    p_cat.add_argument("identifier", help="UUID（完整或前缀）或 PK")
    p_cat.add_argument("path", help="仓库内路径，例如 run.json")
    p_cat.add_argument("--out", help="二进制文件的导出路径")

    args = parser.parse_args(argv)

    # CLI 是独立进程，必须先加载默认 profile（Coder 上为 ai4s）
    from aiida import load_profile
    load_profile()

    if args.cmd == "show":
        info = query.describe(args.identifier)
        out = report.to_text(info)
        print(out)
        if args.json_path:
            report.to_json(info, args.json_path)
            print(f"[JSON 已写入 {args.json_path}]", file=sys.stderr)
        if args.text_path:
            report.to_text(info, args.text_path)
            print(f"[报告已写入 {args.text_path}]", file=sys.stderr)
        return 0

    if args.cmd == "tree":
        info = query.describe(args.identifier)
        print(f"节点 {info['uuid'][:12]}…（{info['node_type']}）")
        print("\n上游：")
        for step in info["lineage"]["upstream"]:
            print("  " + "  " * step["depth"]
                  + f"^-- {step['node_type']} uuid={step['node_uuid'][:12]}…（{step['via_port']}）")
        print("\n下游：")
        for step in info["lineage"]["downstream"]:
            print("  " + "  " * step["depth"]
                  + f"--> [{step.get('relation', '?')}] {step['node_type']}"
                  + f" uuid={step['node_uuid'][:12]}…（{step['via_port']}）")
        return 0

    if args.cmd == "cat":
        import hashlib

        node = query.resolve(args.identifier)
        try:
            print(node.base.repository.get_object_content(args.path), end="")
            return 0
        except UnicodeDecodeError:
            raw = node.base.repository.get_object_content(args.path, mode="rb")
            digest = hashlib.sha256(raw).hexdigest()
            if args.out:
                with open(args.out, "wb") as fh:
                    fh.write(raw)
                print(f"[二进制 {len(raw)}B 已导出到 {args.out}，sha256={digest}]", file=sys.stderr)
            else:
                print(f"[二进制 {len(raw)}B，sha256={digest}；加 --out 可导出]", file=sys.stderr)
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
