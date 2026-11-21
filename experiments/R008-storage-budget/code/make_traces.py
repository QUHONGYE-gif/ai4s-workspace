# -*- coding: utf-8 -*-
"""跑两种策略，导出可回放的事件轨迹与对比数据（供汇报页内嵌）。

产出 traces.json：
  meta      实验设定（序列长度、产物总量、配额、时间缩放）
  catalog   产物清单（指纹 / 名称 / 体积 / 重算成本 / 是否固定）
  sequence  访问序列（26 次请求，离线构造）
  runs      {配额: {lru|scored: 指标 + 事件流}}
  compare   {配额: {lru|scored: 四项指标}}
"""
import json
from pathlib import Path

import engine

MB = engine.MB
QUOTAS = [32.0, 40.0, 46.0]
REPLAY_QUOTA = 46.0
OUT = Path("traces.json")


def trace_run(policy, quota):
    trace = []
    r = engine.replay(policy, quota, trace=trace)

    # 事件流补齐「此刻占用」与「因淘汰多花的时间」：
    # 重算耗时扣掉本来读取也要花的 READ_SECONDS，剩下的才是淘汰造成的净损失。
    used = 0
    extra_total = 0.0
    for ev in trace:
        size_b = int(round(ev.get("size_mb", 0) * MB))
        if ev["type"] == "eviction":
            used = max(0, used - size_b)
            ev["used_after"] = used
        else:
            if ev["action"] in ("compute", "restore"):
                used += size_b
            ev["used_after"] = used
            if ev["action"] == "restore":
                extra = max(0.0, ev["cost_s"] - engine.READ_SECONDS)
                ev["extra_s"] = round(extra, 1)
                extra_total += extra
            else:
                ev["extra_s"] = 0.0

    return {
        "policy": policy,
        "quota_mb": quota,
        "peak_mb": round(r["peak_bytes"] / MB, 2),
        "evictions": r["evictions"],
        "restores": r["restores"],
        "recompute_s": round(r["recompute_real_s"], 1),
        "extra_s": round(extra_total, 1),
        "hits": r["hits"],
        "computed": r["computed"],
        "events": trace,
    }


def metrics(run):
    return {k: run[k] for k in ("peak_mb", "evictions", "restores",
                                "recompute_s", "extra_s", "hits", "computed")}


if __name__ == "__main__":
    engine.init()
    runs = {}
    for q in QUOTAS:
        runs[str(int(q))] = {p: trace_run(p, q) for p in ("lru", "scored")}

    data = {
        "meta": {
            "sequence_len": len(engine.SEQUENCE),
            "catalog_mb": round(sum(c[2] for c in engine.CATALOG), 1),
            "time_scale": engine.TIME_SCALE,
            "read_seconds": engine.READ_SECONDS,
            "quota_mb": REPLAY_QUOTA,
        },
        "catalog": [{"fingerprint": c[0], "label": c[1], "size_mb": c[2],
                     "cost_s": c[3], "pinned": bool(c[4])} for c in engine.CATALOG],
        "sequence": engine.SEQUENCE,
        "runs": runs,
        "compare": {q: {p: metrics(runs[q][p]) for p in ("lru", "scored")} for q in runs},
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    for q in runs:
        for p, r in runs[q].items():
            print(f"quota {q}MB {p:6s} peak={r['peak_mb']:5.1f} ev={r['evictions']:2d} "
                  f"rs={r['restores']:2d} t={r['recompute_s']:5.0f}s extra={r['extra_s']:5.0f}s "
                  f"hits={r['hits']:2d} events={len(r['events'])}")
    print("saved", OUT, OUT.stat().st_size, "bytes")
