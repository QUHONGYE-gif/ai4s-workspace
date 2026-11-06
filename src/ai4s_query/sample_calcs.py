"""Query demo calculations; run in-process without a model or daemon."""
from aiida.engine import calcfunction
from aiida.orm import Bool, Dict, Int, Str


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
