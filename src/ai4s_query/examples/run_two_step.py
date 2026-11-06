# -*- coding: utf-8 -*-
"""示例 1：跑通原生两步计算，并演示「直接复用旧 Data」。

在已配置 profile 的 AiiDA 环境中运行（仓库根目录下 PYTHONPATH=src）：

    python src/ai4s_query/examples/run_two_step.py

运行后打印每个节点的 UUID，可直接交给查询模块：

    python -m ai4s_query.cli show <UUID>
"""
from aiida import load_profile
from aiida.engine import run
from aiida.orm import Int, Str

from ai4s_query.sample_calcs import filter_by_length, seq_stats, unwrap_single

load_profile()  # 使用默认 profile（Coder 上为 ai4s）

SEQ = "MKTAYIAKQRQISFVKSHFSRQ"  # 示例设计序列（单链）

print("=== 第一步：seq_stats ===")
stats = unwrap_single(run(seq_stats, seq=Str(SEQ)))
print(f"  过程节点 uuid = {stats.creator.uuid}")
print(f"  产物 Data  uuid = {stats.uuid}")
print(f"  内容            = {stats.get_dict()}")

print()
print("=== 第二步：filter_by_length（阈值 10，应通过）===")
passed = unwrap_single(run(filter_by_length, stats=stats, min_len=Int(10)))
print(f"  过程节点 uuid = {passed.creator.uuid}")
print(f"  结果            = {passed.value}")

print()
print("=== 局部重算演示：只改阈值（10 -> 30），上游 seq_stats 不重跑 ===")
passed2 = unwrap_single(run(filter_by_length, stats=stats, min_len=Int(30)))
print(f"  新过程节点 uuid = {passed2.creator.uuid}  （与上次不同）")
print(f"  上游 Data  uuid = {stats.uuid}             （与上次相同，未重算）")
print(f"  结果            = {passed2.value}")

print()
print("=== 直接复用旧 Data 演示 ===")
print(f"  两次 filter 共用同一上游 Data：{stats.uuid}")
n_out = sum(1 for _ in stats.base.links.get_outgoing())
print(f"  stats 节点共有 {n_out} 条输出链接"
      "（多个下游过程引用同一数据节点 = 直接复用，非缓存）")
print()
print("把任一过程节点 UUID 交给查询模块即可生成报告：")
print(f"  python -m ai4s_query.cli show {passed2.creator.uuid} --text 报告.txt")
