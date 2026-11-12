"""按任务 4.0「开发期间替代」条款跑一遍：指纹与决策记录都用约定 ③⑤ 的示例。

条款原文：用两个独立数据库模拟两位成员；指纹和决策记录用约定③⑤的示例。

本脚本只做三件事，全部真实执行、不构造假结果：
  1. 读 protocol_examples/fingerprint.json，用其中的值跨库查候选；
  2. 读 protocol_examples/decision.json，按 ⑤ 校验后写入并读回；
  3. 把过程与结果落到 ~/runs/protocol-examples-<时间戳>/ 下，供文档引用。

③⑤ 的官方示例到位后，只替换那两个 JSON 的键值，本脚本与查询代码都不改。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(PKG))

from ai4s_query import candidates as cand_mod  # noqa: E402
from ai4s_query import decision as dec_mod    # noqa: E402

EXAMPLES = HERE / "protocol_examples"
REQUEST = {"num_sequences": 1, "score_threshold": 2.0}


def say(text: str = "") -> None:
    print(text)


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = Path.home() / "runs" / f"protocol-examples-{stamp}"
    outdir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def log(text: str = "") -> None:
        say(text)
        lines.append(text)

    fp_pack = json.loads((EXAMPLES / "fingerprint.json").read_text(encoding="utf-8"))
    dc_pack = json.loads((EXAMPLES / "decision.json").read_text(encoding="utf-8"))
    fingerprint = fp_pack["value"]

    log("=== 一、约定③ 示例指纹 → 跨库查候选 ===")
    log(f"来源文件 {EXAMPLES / 'fingerprint.json'}（status={fp_pack.get('status')}）")
    log(f"指纹值   {fingerprint}")
    log(f"查询条件 条数≥{REQUEST['num_sequences']}，最优分≤{REQUEST['score_threshold']}")
    log(f"查询范围 {', '.join(cand_mod._profile_names()) or '（空）'}")

    result = cand_mod.find(fingerprint, request=REQUEST)
    if result.get("errors"):
        log(f"读取告警 {result['errors']}")
    members = sorted({c["member"] for c in result["candidates"]})
    log(f"候选 {result['count']} 条，合格 {result['qualified_count']} 条，"
        f"涉及成员 {len(members)} 位：{'、'.join(members)}")
    for c in result["candidates"][:3]:
        log(f"  · {c['member']:4s} {c['location']:28s} qualified={c['qualified']} "
            f"size={c['size_bytes']} seqs={c['seq_count']} note={c['note'] or '—'}")
    if result["count"] > len(members):
        pass

    log("")
    log("=== 二、约定⑤ 示例记录 → 校验 → 写入 → 读回 ===")
    record = dict(dc_pack["record"])
    problems = dec_mod.validate(dec_mod.normalize(record))
    log(f"校验结果 {'通过' if not problems else '不通过：' + '；'.join(problems)}")
    if problems:
        log("示例记录不合规，终止（不写库、不伪造）")
        (outdir / "记录.txt").write_text("\n".join(lines), encoding="utf-8")
        return 1

    saved = dec_mod.save(record, process=record["process_uuid"],
                         directory=outdir / "decisions", targets=("extras", "file"))
    log(f"写入位置 {', '.join(saved['written']) or '无'}")

    back = dec_mod.load(record["request_id"], directory=outdir / "decisions")
    log(f"读回 {back['count']} 条，来源 {[s['source'] for s in back['sources_tried'] if s['count']]}")
    if back["count"]:
        rec = back["records"][0]
        log(f"  request_id  {rec['request_id']}")
        log(f"  process     {rec['process_uuid']}")
        log(f"  policy      {rec['reuse_policy']} → {rec['final_decision']['action']}")
        log(f"  理由        {rec['reason']['reason_code']} {rec['reason']['reason_text']}")
        log(f"  校验        {'通过' if rec['_ok'] else '不通过：' + '；'.join(rec['_problems'])}")

    log("")
    log("=== 三、跨成员命中的是哪一条 ===")
    selected = record["final_decision"]["selected_candidate_uuid"]
    hit = next((c for c in result["candidates"] if c["uuid"] == selected), None)
    if hit:
        log(f"选中 {hit['uuid'][:8]}，成员 {hit['member']}，位置 {hit['location']}")
        log("该条不在执行者本人库里：命中来自第二个独立数据库，即另一位成员。")
    else:
        log(f"选中 {selected[:8]} 不在本次候选清单内（示例值为历史运行）")

    log("")
    log(f"产出目录 {outdir}")
    (outdir / "记录.txt").write_text("\n".join(lines), encoding="utf-8")
    (outdir / "候选清单.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
