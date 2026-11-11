# -*- coding: utf-8 -*-
"""命令行入口。

用法（在已激活的 AiiDA 环境中）：
  python -m ai4s_query.cli show  <UUID或PK> [--json 出.json] [--text 出.txt]
  python -m ai4s_query.cli trace <UUID或PK> [--depth 12] [--text 出.txt]
  python -m ai4s_query.cli tree  <UUID或PK> [--depth 5]
  python -m ai4s_query.cli cat   <UUID或PK> <仓库路径> [--out 导出文件]
  python -m ai4s_query.cli candidates [--fingerprint 摘要] [--node UUID] [--profiles a,b]
  python -m ai4s_query.cli decision <request_id 或 过程 UUID> [--dir 决策记录目录]
  python -m ai4s_query.cli serve [--host --port --profile]
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

    p_trace = sub.add_parser("trace", help="打印主干轨迹（输入→计算→产物 一条竖线）")
    p_trace.add_argument("identifier", help="UUID（完整或前缀）或 PK")
    p_trace.add_argument("--depth", type=int, default=12, help="主干最大步数（默认 12）")
    p_trace.add_argument("--json", dest="json_path", help="导出轨迹 JSON 到此路径")
    p_trace.add_argument("--text", dest="text_path", help="导出轨迹报告到此路径")

    p_cat = sub.add_parser("cat", help="读取节点的仓库文件（文本直接打印，二进制用 --out 导出）")
    p_cat.add_argument("identifier", help="UUID（完整或前缀）或 PK")
    p_cat.add_argument("path", help="仓库内路径，例如 run.json")
    p_cat.add_argument("--out", help="二进制文件的导出路径")

    p_wb = sub.add_parser("workbench", help="导出为「研序」工作台可导入的记录 JSON")
    p_wb.add_argument("identifiers", nargs="+", help="一个或多个入口节点（UUID 或 PK）")
    p_wb.add_argument("--out", required=True, help="导出的 JSON 路径")
    p_wb.add_argument("--base", help="已有的研序导出文件，先读入再把新记录追加进去")

    p_cand = sub.add_parser("candidates", help="跨成员候选查找（输出约定④ 的候选列表）")
    p_cand.add_argument("--fingerprint", help="计算指纹（extras 的 _aiida_hash）")
    p_cand.add_argument("--node", help="以该结果节点为参照，按它的指纹找候选")
    p_cand.add_argument("--profiles", help="限定 profile，逗号分隔；缺省为全部")
    p_cand.add_argument("--num-sequences", dest="num_sequences", type=int,
                        help="请求要求的序列条数（完整性判定）")
    p_cand.add_argument("--score-threshold", dest="score_threshold", type=float,
                        help="质量门限：最优分数不得高于该值")
    p_cand.add_argument("--qualified-only", action="store_true",
                        help="只列合格候选（默认也列不合格的，带原因）")
    p_cand.add_argument("--json", dest="json_path", help="导出 JSON 到此路径")

    p_dec = sub.add_parser("decision", help="读取约定⑤ 的决策记录")
    p_dec.add_argument("identifier", help="request_id、过程 UUID 或结果节点 UUID")
    p_dec.add_argument("--dir", dest="decisions_dir", help="旁路决策记录目录")
    p_dec.add_argument("--json", dest="json_path", help="导出 JSON 到此路径")

    p_srv = sub.add_parser("serve", help="启动只读查询服务（供网页实时读取）")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=8848)
    p_srv.add_argument("--profile", help="AiiDA profile 名")
    p_srv.add_argument("--decisions-dir", dest="decisions_dir")

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

    if args.cmd == "trace":
        steps = query.trace(args.identifier, max_depth=args.depth)
        print(report.trace_text(steps))
        if args.json_path:
            report.to_json({"uuid": steps[-1]["uuid"] if steps else None, "trace": steps},
                           args.json_path)
            print(f"[轨迹 JSON 已写入 {args.json_path}]", file=sys.stderr)
        if args.text_path:
            report.trace_text(steps, args.text_path)
            print(f"[轨迹报告已写入 {args.text_path}]", file=sys.stderr)
        return 0

    if args.cmd == "workbench":
        import json

        from . import workbench

        base = None
        if args.base:
            with open(args.base, encoding="utf-8") as fh:
                base = json.load(fh)
        state = workbench.export_state(args.identifiers, base=base)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(workbench.dumps(state))
        print(f"[研序记录已写入 {args.out}："
              f"{len(state['experiments'])} 条实验 / {len(state['catalog'])} 个产物]",
              file=sys.stderr)
        return 0

    if args.cmd == "candidates":
        import json

        from . import candidates as cand_mod

        request = {}
        if args.num_sequences:
            request["num_sequences"] = args.num_sequences
        if args.score_threshold is not None:
            request["score_threshold"] = args.score_threshold
        profiles = [p for p in (args.profiles or "").split(",") if p] or None

        if args.node:
            result = cand_mod.by_node(args.node, request)
        else:
            result = cand_mod.find(fingerprint=args.fingerprint, profiles=profiles,
                                   request=request,
                                   include_unqualified=not args.qualified_only)
        print(cand_mod.text_view(result))
        if args.json_path:
            with open(args.json_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            print(f"[候选 JSON 已写入 {args.json_path}]", file=sys.stderr)
        return 0

    if args.cmd == "decision":
        import json

        from . import decision as dec_mod

        result = dec_mod.load(args.identifier, directory=args.decisions_dir)
        print(f"查询 {args.identifier}：{result['count']} 条决策记录")
        for rec in result["records"]:
            fd, rs = rec["final_decision"], rec["reason"]
            print("")
            print(f"  请求 {rec['request_id']}")
            print(f"  过程 {rec['process_uuid']}")
            print(f"  选择 {rec['reuse_policy']}  →  动作 {fd['action']}"
                  f"（候选 {len(rec['candidate_compare_list'])} 条）")
            print(f"  理由 {rs['reason_code']} {rs['reason_text']}")
            print(f"  时间 {rec['timestamp']}    校验 {'通过' if rec['_ok'] else rec['_problems']}")
        if result["missing"]:
            print(result["missing"])
        if args.json_path:
            with open(args.json_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            print(f"[决策记录 JSON 已写入 {args.json_path}]", file=sys.stderr)
        return 0

    if args.cmd == "serve":
        from . import server

        server.serve(args.host, args.port, args.profile, args.decisions_dir)
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
