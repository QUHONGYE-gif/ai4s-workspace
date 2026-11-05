# -*- coding: utf-8 -*-
"""原生两步计算样例（不依赖真实模型）。

镜像真实流程的形状：序列 -> 统计（seq_stats） -> 筛选（filter_by_length）。
对应「自建原生两步计算例子」，纯 calcfunction，进程内即可运行，
不需要 daemon 与外部程序。
"""
from aiida.engine import calcfunction
from aiida.orm import Bool, Dict, Int, Str

# 验收小样本口径：单链、单温度、4 条序列之一即可用 Str 传入


def unwrap_single(out, key: str = "result"):
    """兼容 run() 的两种返回形态：{'result': node} 或直接返回节点。

    AiiDA 2.9 对单输出 calcfunction 的 run() 直接返回输出节点；
    多输出或其他 Process 仍返回按链接名索引的字典。
    """
    if isinstance(out, dict) and key in out:
        return out[key]
    return out


@calcfunction
def seq_stats(seq: Str) -> Dict:
    """第一步：统计设计序列的长度与氨基酸组成。

    :param seq: 设计序列字符串（如 ProteinMPNN 输出的一条序列）
    :return: Dict，含 length 与 composition（各氨基酸计数）
    """
    s = seq.value.upper().strip()
    composition = {}
    for ch in s:
        composition[ch] = composition.get(ch, 0) + 1
    return Dict(dict={
        "length": len(s),
        "composition": composition,
        "sequence": s,
    })


@calcfunction
def filter_by_length(stats: Dict, min_len: Int) -> Bool:
    """第二步：按最小长度阈值筛选。

    :param stats: seq_stats 的输出（同一上游 Data 可被多次复用）
    :param min_len: 阈值，改这个参数即触发「局部重算」场景
    :return: Bool，是否通过筛选
    """
    return Bool(stats["length"] >= min_len.value)


@calcfunction
def strict_length_check(stats: Dict, min_len: Int) -> Int:
    """故意失败的样例：长度不足阈值时抛异常，用于生成「失败诊断」真实样本。

    与 filter_by_length 的区别：它不返回 False，而是直接失败，
    因此过程节点状态为 excepted，可用来演示「成功/失败原因可查询」。
    """
    length = int(stats["length"])
    if length < int(min_len.value):
        raise ValueError(f"序列长度 {length} 小于阈值 {min_len.value}，该设计不可用")
    return Int(length)
