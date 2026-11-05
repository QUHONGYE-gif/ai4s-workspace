# -*- coding: utf-8 -*-
"""示例 2：缓存命中演示——区分「缓存复用」与「直接复用旧 Data」。

在已配置 profile 的 AiiDA 环境中运行（仓库根目录下 PYTHONPATH=src）：

    python src/ai4s_query/examples/run_cache_demo.py

输出对照场景「缓存来源」：同参数重复提交，
第二次过程节点 is_created_from_cache=True，并给出缓存来源节点。
"""
from aiida import load_profile
from aiida.engine import run
from aiida.manage.caching import enable_caching
from aiida.orm import Str

from ai4s_query.sample_calcs import seq_stats, unwrap_single

load_profile()

SEQ = Str("MKTAYIAKQRQISFVKSHFSRQ")
SEQ.store()  # 缓存命中要求输入是已入库（store）的节点

print("=== 第一次运行（开启缓存记录）===")
# 注意：若 profile 里已有同过程、同输入的历史运行，第一次也会命中缓存
# （缓存键跨 run 生效）。在全新 profile（如 Coder 上的 ai4s）首次运行时，
# 这里应显示 False，第二次运行显示 True。
with enable_caching():
    stats1 = unwrap_single(run(seq_stats, seq=SEQ))
proc1 = stats1.creator
print(f"  过程节点 uuid = {proc1.uuid}")
print(f"  is_created_from_cache = {proc1.base.caching.is_created_from_cache}")

print()
print("=== 第二次运行（同过程、同输入 -> 应命中缓存）===")
with enable_caching():
    stats2 = unwrap_single(run(seq_stats, seq=SEQ))
proc2 = stats2.creator
cache = proc2.base.caching
print(f"  过程节点 uuid = {proc2.uuid}")
print(f"  is_created_from_cache = {cache.is_created_from_cache}")
if cache.is_created_from_cache:
    print(f"  缓存来源节点 uuid       = {cache.get_cache_source()}")

print()
print("=== 对照：直接复用旧 Data（不是缓存）===")
print(f"  第一次的产物 Data uuid = {stats1.uuid}")
print("  把它作为新过程的输入传入，属于语义层复用：")
print("  新过程照常执行、照常新建节点，只是输入节点与旧过程共享——")
print("  与缓存命中（新过程不执行、直接接管旧输出）机制不同。")

print()
print("验证命令：")
print(f"  python -m ai4s_query.cli show {proc2.uuid} --text 缓存命中报告.txt")
