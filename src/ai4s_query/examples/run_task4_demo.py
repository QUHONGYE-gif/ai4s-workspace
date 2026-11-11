# -*- coding: utf-8 -*-
"""任务 4.0 一站演示：跨成员候选查找 + 查询接口的证据生成。

一次运行产出五份材料到 ``~/runs/task4-demo-<时间戳>/``：
    00-索引.txt            本次用到的 UUID、指纹与复现命令
    01-候选-跨成员.txt      同一指纹在多个 profile 中被找到（含其他成员）
    02-候选-不合格.txt      故意失败的组：候选照列，带枚举原因
    03-决策记录.txt        约定⑤ 记录的读取与校验结果
    04-接口清单.txt        可直接 curl 的端点与示例

只为演示与记录，不写 AiiDA 节点。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from aiida import load_profile

from ai4s_query import candidates, decision


def _pick_group(all_cands):
    """挑一组最能说明「跨成员」的指纹：覆盖成员数优先，其次合格数、总数。"""
    groups = {}
    for c in all_cands:
        groups.setdefault(c["fingerprint"], []).append(c)
    if not groups:
        return None, []
    best = max(groups.items(),
               key=lambda kv: (len({c["member"] for c in kv[1]}),
                               sum(1 for c in kv[1] if c["qualified"]),
                               len(kv[1])))
    return best[0], best[1]


def main(argv=None) -> int:
    load_profile()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path.home() / "runs" / f"task4-demo-{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    every = candidates.find()
    print(f"[1/4] 扫描完成：{every['scope']['profiles']} 共 {every['count']} 个过程")

    fp_ok, ok_group = _pick_group([c for c in every["candidates"] if c["qualified"]])
    bad_groups = {}
    for c in every["candidates"]:
        if not c["qualified"]:
            bad_groups.setdefault(c["fingerprint"], []).append(c)
    fp_bad = (max(bad_groups.items(), key=lambda kv: len(kv[1]))[0]
              if bad_groups else None)

    # 首次扫描受 max_per_profile 截断，选定指纹后重新完整查一次，数字才对得上
    res_ok = candidates.find(fingerprint=fp_ok) if fp_ok else None
    res_bad = candidates.find(fingerprint=fp_bad) if fp_bad else None

    lines = ["任务 4.0 演示记录", f"生成时间 {stamp}", ""]
    lines.append(f"profile 范围 : {every['scope']['profiles']}")
    lines.append(f"成员映射     : {every['scope']['members']}")
    lines.append("")
    if res_ok:
        members = sorted({c["member"] for c in res_ok["candidates"]})
        lines.append(f"合格组指纹   : {fp_ok}")
        lines.append(f"  候选 {res_ok['count']} 条（合格 {res_ok['qualified_count']}），"
                     f"来自成员 {members}")
        lines.append(f"  复现：python -m ai4s_query.cli candidates --fingerprint {fp_ok[:16]}")
    if fp_bad:
        lines.append(f"不合格组指纹 : {fp_bad}")
        lines.append(f"  复现：python -m ai4s_query.cli candidates --fingerprint {fp_bad[:16]}")
    lines.append("")
    lines.append("启动接口：python -m ai4s_query.cli serve --port 8848")
    (out / "00-索引.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"[2/4] 索引已写入 00-索引.txt")

    if res_ok:
        (out / "01-候选-跨成员.txt").write_text(candidates.text_view(res_ok), encoding="utf-8")
        (out / "01-候选-跨成员.json").write_text(
            json.dumps(res_ok, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        others = sorted({c["member"] for c in res_ok["candidates"]})
        print(f"      跨成员候选 {res_ok['count']} 条，涉及成员 {others}")

    if res_bad:
        (out / "02-候选-不合格.txt").write_text(candidates.text_view(res_bad), encoding="utf-8")
        print(f"      不合格候选 {res_bad['count']} 条，全部带枚举原因")

    # 决策记录：取 demo 目录里最新一条，或读旁路目录
    rec = decision.load(fp_ok[:16] if fp_ok else "")
    dec_dir = decision.default_dir()
    sample = sorted(dec_dir.glob("*.json")) if dec_dir.exists() else []
    if not rec["records"] and sample:
        rec = decision.load(sample[-1].stem)
    body = [f"查询 {rec['identifier']}：{rec['count']} 条"]
    for r in rec["records"]:
        body += ["", f"  请求 {r['request_id']}", f"  过程 {r['process_uuid']}",
                 f"  策略 {r['reuse_policy']} → 动作 {r['final_decision']['action']}",
                 f"  理由 {r['reason']['reason_code']} {r['reason']['reason_text']}",
                 f"  校验 {'通过' if r['_ok'] else r['_problems']}"]
    if rec["missing"]:
        body += ["", rec["missing"]]
    (out / "03-决策记录.txt").write_text("\n".join(body), encoding="utf-8")
    print(f"[3/4] 决策记录 {'已读到 %d 条' % rec['count'] if rec['count'] else '暂无（待扩展点产出）'}")

    api = [
        "curl localhost:8848/api/health",
        "curl localhost:8848/api/node/<UUID>",
        "curl localhost:8848/api/trace/<UUID>?depth=12",
        f"curl 'localhost:8848/api/candidates?fingerprint={fp_ok[:16] if fp_ok else '<指纹>'}'",
        "curl 'localhost:8848/api/decision?request_id=<请求编号>'",
    ]
    (out / "04-接口清单.txt").write_text("\n".join(api), encoding="utf-8")
    print(f"[4/4] 接口清单已写入")
    print(f"\n全部材料在 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
