# -*- coding: utf-8 -*-
"""一键演示：在真实 profile 里造出四类节点，并生成汇报用报告。

用法（仓库根目录）：

    PYTHONPATH=src python src/ai4s_query/examples/run_demo.py

只用 AiiDA 原生 calcfunction，不依赖外部程序、不需要 Code、不需要 daemon，
因此不依赖任何尚未就绪的模型插件，可独立运行与演示。

产出目录 ~/runs/query-demo-<时间戳>/：
  01-trace-完整轨迹.txt/.json   主干竖线：输入 -> 计算 -> 产物 -> 计算 -> 产物
  02-show-过程详情.txt/.json    状态、参数值、产物、校验、缺失
  03-show-缓存命中.txt/.json    缓存命中（过程未执行）vs 真实执行
  04-show-失败诊断.txt/.json    exit_code 与异常原文
  05-show-数据复用.txt/.json    同一 Data 被两个下游使用（数据级复用）
  00-索引.txt                   每条报告对应的 UUID 与一句话说明
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aiida import load_profile
from aiida.engine import run
from aiida.manage.caching import enable_caching
from aiida.orm import Int, QueryBuilder, Str, load_node
from aiida.orm.nodes.process.process import ProcessNode

from ai4s_query import query, report
from ai4s_query.sample_calcs import (
    filter_by_length,
    seq_stats,
    strict_length_check,
    unwrap_single,
)

load_profile()

SEQ = "MKTAYIAKQRQISFVKSHFSRQ"

OUT = Path.home() / "runs" / ("query-demo-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
OUT.mkdir(parents=True, exist_ok=True)

INDEX = []


def _pks() -> set:
    return {row[0] for row in QueryBuilder().append(ProcessNode, project=["pk"]).all()}


def _latest_new(before: set):
    new = sorted(_pks() - before)
    return load_node(new[-1]) if new else None


def dump(tag: str, node, note: str) -> None:
    base = OUT / tag
    info = query.describe(node.uuid)
    report.to_text(info, str(base) + ".txt")
    report.to_json(info, str(base) + ".json")
    INDEX.append((tag, node.uuid, note))
    print(f"  {base.name}.txt / .json    uuid={node.uuid}")


def dump_trace(tag: str, node, note: str) -> None:
    base = OUT / tag
    steps = query.trace(node.uuid)
    report.trace_text(steps, str(base) + ".txt")
    report.to_json({"uuid": node.uuid, "trace": steps}, str(base) + ".json")
    INDEX.append((tag, node.uuid, note))
    print(f"  {base.name}.txt / .json    uuid={node.uuid}")


print("=" * 60)
print("AiiDA 查询模块演示：自建两步计算 + 缓存 + 失败 + 复用")
print("=" * 60)

# ---------------------------------------------------------------- 1. 两步计算
print("\n[1/5] 两步原生计算（seq_stats -> filter_by_length）")
stats = unwrap_single(run(seq_stats, seq=Str(SEQ)))
print(f"  seq_stats 产物      uuid={stats.uuid}  值={stats.get_dict()['length']} 残基")

passed_10 = unwrap_single(run(filter_by_length, stats=stats, min_len=Int(10)))
proc_10 = passed_10.creator
print(f"  filter(阈值10)      uuid={proc_10.uuid}  结果={passed_10.value}（通过）")

# 只改阈值 -> 局部重算：新过程、真执行，但上游 Data 是同一个
passed_30 = unwrap_single(run(filter_by_length, stats=stats, min_len=Int(30)))
proc_30 = passed_30.creator
print(f"  filter(阈值30)      uuid={proc_30.uuid}  结果={passed_30.value}（不通过）")
print(f"  两次筛选共用上游 Data：{stats.uuid}（数据级复用，非缓存）")

# ---------------------------------------------------------------- 2. 缓存命中
print("\n[2/5] 缓存命中（同过程、同输入跑两次）")
seq_stored = Str(SEQ)
seq_stored.store()
with enable_caching():
    first = unwrap_single(run(seq_stats, seq=seq_stored))
with enable_caching():
    second = unwrap_single(run(seq_stats, seq=seq_stored))
cached_proc = second.creator
is_cached = cached_proc.base.caching.is_created_from_cache
print(f"  第二次 is_created_from_cache = {is_cached}")
if is_cached:
    print(f"  缓存来源                    = {cached_proc.base.caching.get_cache_source()}")
else:
    print("  （首次运行该输入，未命中属正常；再跑一次本脚本即可看到命中）")

# ---------------------------------------------------------------- 3. 失败节点
print("\n[3/5] 故意失败（阈值 100 > 序列长度 23）")
before = _pks()
try:
    run(strict_length_check, stats=stats, min_len=Int(100))
except Exception as exc:  # calcfunction 失败会把异常抛回调用方
    print(f"  预期失败：{type(exc).__name__}: {exc}")
failed_proc = _latest_new(before)
print(f"  失败过程节点 uuid={failed_proc.uuid if failed_proc else '(未捕获)'}")

# ---------------------------------------------------------------- 4. 出报告
print("\n[4/5] 生成报告")
dump_trace("01-trace-完整轨迹", passed_30,
           "一条竖线看完整条链：输入序列 -> 统计 -> 字典 -> 筛选 -> 布尔结果")
dump("02-show-过程详情", proc_30,
     "单节点报告：状态、参数值 min_len=30、产物、校验哈希")
dump("03-show-缓存命中", cached_proc,
     "缓存命中：过程未执行，附来源节点 UUID")
if failed_proc is not None:
    dump("04-show-失败诊断", failed_proc,
         "失败诊断：process_state=excepted，异常原文可查")
dump("05-show-数据复用", stats,
     "数据级复用：同一个 Dict 被两个 filter 过程使用（两条 used_by）")

# ---------------------------------------------------------------- 5. 索引
print("\n[5/5] 写入索引")
lines = [
    "AiiDA 查询模块演示索引",
    f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
    f"产出目录：{OUT}",
    "",
    "报告文件对应关系：",
]
for tag, uuid, note in INDEX:
    lines.append(f"  {tag}")
    lines.append(f"      uuid : {uuid}")
    lines.append(f"      说明 : {note}")
lines += [
    "",
    "复现单条报告：",
    "  PYTHONPATH=src python -m ai4s_query.cli trace %s" % (INDEX[0][1] if INDEX else "<uuid>"),
    "  PYTHONPATH=src python -m ai4s_query.cli show  %s" % (INDEX[1][1] if len(INDEX) > 1 else "<uuid>"),
]
(OUT / "00-索引.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))

print("\n" + "=" * 60)
print(f"完成。产出目录：{OUT}")
print("=" * 60)
