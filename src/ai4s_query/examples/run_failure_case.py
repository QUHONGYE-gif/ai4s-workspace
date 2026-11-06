# -*- coding: utf-8 -*-
"""示例 3：生成「失败诊断」与「不可读文件 / 未记录信息」的真实节点。

用途：任务书要求 3 的四分类，需要真实样本来验证，而不是靠描述。
本脚本产生两类节点：

1. 执行失败的过程节点（calcfunction 抛异常）——用于「失败诊断」；
2. 含二进制产物的数据节点（模拟 MPNN 的 scores/*.npz），且没有产生它的过程
   —— 同时用于「不可读文件」与「未记录信息」两类。

运行：

    python src/ai4s_query/examples/run_failure_case.py

脚本会打印 UUID，交给查询模块即可出报告。
"""
from __future__ import annotations

import io

from aiida import load_profile
from aiida.engine import run
from aiida.orm import FolderData, Int, QueryBuilder, Str
from aiida.orm.nodes.process.calculation.calcfunction import CalcFunctionNode

from ai4s_query.sample_calcs import seq_stats, strict_length_check, unwrap_single

load_profile()

SEQ = "MKTAYIAKQRQISFVKSHFSRQ"  # 22 残基


def _calcfunc_uuids():
    return {node.uuid for node, in QueryBuilder().append(CalcFunctionNode).all()}


print("=== 样例 A：二进制产物 + 无产生过程 ===")
folder = FolderData()
folder.put_object_from_filelike(
    io.BytesIO(b"\x93NUMPY\x00\x01\x00\x00fake-scores-payload"), "scores/1CRN.npz")
folder.put_object_from_filelike(
    io.StringIO("ProteinMPNN simulated output\n2 sequences written\n"), "run.log")
folder.label = "MPNN 产物目录（模拟）"
folder.description = "含二进制分数文件与文本日志；无产生它的过程"
folder.store()
print(f"  数据节点 uuid = {folder.uuid}")
print("  预期分类：scores/1CRN.npz 为二进制（不可读文件）；无 creator（未记录信息）")

print()
print("=== 样例 B：故意失败的计算 ===")
stats = unwrap_single(run(seq_stats, seq=Str(SEQ)))
print(f"  上游统计 uuid = {stats.uuid}（length={stats.get_dict()['length']}）")

before = _calcfunc_uuids()
try:
    run(strict_length_check, stats=stats, min_len=Int(50))
except Exception as exc:  # 预期失败：长度 22 < 阈值 50
    print(f"  已按预期失败：{type(exc).__name__}: {exc}")

failed = _calcfunc_uuids() - before
if not failed:
    raise SystemExit("未找到新建的失败节点")
failed_uuid = failed.pop()
print(f"  失败过程 uuid = {failed_uuid}")

print()
print("查询示例：")
print(f"  python -m ai4s_query.cli show {folder.uuid} --text 二进制产物.txt")
print(f"  python -m ai4s_query.cli show {failed_uuid} --text 失败节点.txt")
