"""
样例数据与验证辅助：生成测试 PDB、统计模型启动次数。

统计基于 AiiDA 原生节点（数据库中的子 CalcJob 节点数），符合
「C 可用原生查询独立验收」。
"""
import os
import tempfile

from aiida.orm import QueryBuilder, Node, CalcJobNode


def make_test_pdb(path=None):
    """生成一个最小可用的测试 PDB 文本，返回路径。"""
    content = (
        "ATOM      1  N   ALA A   1       1.000   1.000   1.000  1.00  0.00           N\n"
        "ATOM      2  CA  ALA A   1       1.500   1.000   1.000  1.00  0.00           C\n"
        "ATOM      3  C   ALA A   1       2.000   1.000   1.000  1.00  0.00           C\n"
        "TER\nEND\n"
    )
    if path is None:
        fd, path = tempfile.mkstemp(suffix=".pdb")
        os.close(fd)
    with open(path, "w") as f:
        f.write(content)
    return path


def count_infer_launches(wc_node):
    """统计一个 WorkChain 下实际启动的推理 CalcJob 数量（模型外部启动次数）。

    通过 WorkChain 的后代节点计数：从筛选结果反查模型是否再次启动，
    是「只改筛选参数、模型启动次数不增加」这一验收点的量化证据。
    """
    qb = QueryBuilder()
    qb.append(Node, tag="wc", filters={"id": wc_node.pk})
    qb.append(CalcJobNode, tag="job", with_ancestors="wc")
    return qb.count()
