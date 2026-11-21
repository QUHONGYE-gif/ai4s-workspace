# -*- coding: utf-8 -*-
"""同一访问序列下两种保留策略的对比，输出 compare.json 与 compare.md。

四项指标：最高占用、淘汰次数、淘汰后重算次数、重算总耗时。
另附「净多花时间」= 重算耗时 − 该次本可读取的 READ_SECONDS。

用法：
    python compare.py            # 32 / 40 / 46 三档
    python compare.py 30 50      # 指定配额
"""
import json
import sys
from pathlib import Path

import engine

MB = engine.MB
POLICIES = ("lru", "scored")


def run(quota_mb):
    rows = {}
    for policy in POLICIES:
        trace = []
        r = engine.replay(policy, quota_mb, reset_first=True, trace=trace)
        extra = sum(max(0.0, e["cost_s"] - engine.READ_SECONDS)
                    for e in trace if e.get("action") == "restore")
        rows[policy] = {
            "peak_mb": round(r["peak_bytes"] / MB, 2),
            "evictions": r["evictions"],
            "restores": r["restores"],
            "recompute_s": round(r["recompute_real_s"], 1),
            "extra_s": round(extra, 1),
            "hits": r["hits"],
            "computed": r["computed"],
        }
    return rows


def markdown(out):
    lines = [
        "# 同一访问序列下的策略对比",
        "",
        f"- 序列长度：{out['sequence_len']} 次请求",
        f"- 工作集：{out['catalog_mb']} MB（{out['artifacts']} 个产物）",
        f"- 时间缩放：{out['time_scale']}（表内耗时为折算真实秒数）",
        "",
        "| 配额 | 策略 | 最高占用 | 淘汰次数 | 淘汰后重算 | 重算耗时 | 净多花 | 命中复用 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for q, row in out["quota"].items():
        for p in POLICIES:
            m = row[p]
            lines.append(f"| {q} MB | {p} | {m['peak_mb']} MB | {m['evictions']} | {m['restores']} | "
                         f"{m['recompute_s']} s | {m['extra_s']} s | {m['hits']} |")
    lines += [
        "",
        f"口径：净多花 = 重算耗时 − 该次本可读取的 {engine.READ_SECONDS} 秒。",
        "候选集与淘汰规则相同，仅排序键不同（LRU 按上次使用时间，打分按保留价值）。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    engine.init()
    quotas = [float(x) for x in (sys.argv[1:] or ["32", "40", "46"])]
    out = {"quota": {}, "sequence_len": len(engine.SEQUENCE),
           "catalog_mb": round(sum(c[2] for c in engine.CATALOG), 1),
           "artifacts": len(engine.CATALOG), "time_scale": engine.TIME_SCALE}
    for q in quotas:
        out["quota"][str(int(q))] = run(q)
        print(f"quota {int(q)}MB ->", json.dumps(out["quota"][str(int(q))], ensure_ascii=False))
    Path("compare.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("compare.md").write_text(markdown(out), encoding="utf-8")
    print("saved compare.json / compare.md")
