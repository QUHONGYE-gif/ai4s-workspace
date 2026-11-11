# -*- coding: utf-8 -*-
"""生成一条「约定⑤ 决策记录」样例（联调期用）。

正式记录由吴昱慧的决策扩展点产出；本脚本只把**真实的候选数据**按 ⑤ 的结构
组织成一条记录，用于：
1. 验证查询接口的 /api/decision；
2. 在决策扩展点尚未接通时，让站 10 的网页有可读数据。

用法：
    python examples/make_sample_decision.py --node 170 \
        --request-id req-6f1c2a9e-3b7d-4c51-9a0e-1d2f3c4b5a6e \
        --policy allow_reuse --out ~/runs/decisions

不写 AiiDA 节点，只在旁路目录写一个 JSON。
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from aiida import load_profile

from ai4s_query import candidates


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True, help="参照结果节点（UUID 或 PK）")
    parser.add_argument("--request-id", dest="request_id", required=True)
    parser.add_argument("--policy", default="allow_reuse",
                        choices=("allow_reuse", "force_rerun", "new_sample"))
    parser.add_argument("--seed", type=int, default=37, help="原种子")
    parser.add_argument("--out", default=str(Path.home() / "runs" / "decisions"))
    args = parser.parse_args(argv)

    load_profile()

    result = candidates.by_node(args.node)
    cands = result["candidates"]
    qualified = [c for c in cands if c["qualified"]]
    ref = result["reference"]

    # 按 ⑤ 的规则决定动作
    here = candidates._current_profile()
    cross = [c for c in qualified if c["profile"] != here]  # 优先复用其他成员的合格结果
    if args.policy == "allow_reuse" and qualified:
        pick = (cross or qualified)[0]
        action, code, text = "reuse", "R01", "策略为允许复用，存在合格候选，按规则选中第一条"
        selected = pick["uuid"]
        text += f"（成员 {pick['member']}）"
        seed = args.seed
    elif args.policy == "force_rerun":
        action, code, text = "rerun", "R03", "用户选择强制重算，忽略已有候选，使用原参数、原种子重新运行"
        selected, seed = None, args.seed
    elif args.policy == "new_sample":
        seed = random.randint(10000, 99999)
        action, code, text = "new_sample", "R04", "用户选择新采样，忽略候选，更换种子运行"
        selected = None
    else:
        action, code, text = "rerun", "R02", "候选为空或全部不合格，降级为重算"
        selected, seed = None, args.seed

    # 参与比较的候选：优先列出其他成员的结果，再补本人结果，最多 8 条
    pool, seen = [], set()
    for c in cross + [c for c in cands if c["profile"] == here] + cands:
        if c["uuid"] in seen:
            continue
        seen.add(c["uuid"])
        pool.append(c)
        if len(pool) >= 8:
            break

    record = {
        "request_id": args.request_id,
        "process_uuid": ref["process_uuid"],
        "reuse_policy": args.policy,
        "candidate_compare_list": [
            {k: c[k] for k in ("uuid", "fingerprint", "member", "qualified", "reason")}
            for c in pool
        ],
        "final_decision": {
            "action": action,
            "selected_candidate_uuid": selected,
            "effective_seed": seed,
        },
        "reason": {"reason_code": code, "reason_text": text},
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_meta": {
            "generated_by": "ai4s_query.examples.make_sample_decision",
            "note": "联调样例：候选数据取自真实节点，决策本身待扩展点产出",
            "fingerprint": ref["fingerprint"],
            "candidates_total": len(cands),
            "candidates_qualified": len(qualified),
        },
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{args.request_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[已写入 {path}]")
    print(f"  策略 {args.policy} → 动作 {action}（{code}）")
    print(f"  候选 {len(cands)} 条，合格 {len(qualified)} 条")
    if selected:
        print(f"  选中 {selected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
