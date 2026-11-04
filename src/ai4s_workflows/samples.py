"""
测试工具：生成测试 PDB、辅助统计
"""
from aiida.orm import SinglefileData


def make_test_pdb() -> SinglefileData:
    """生成测试用 PDB 内容节点"""
    pdb_content = (
        "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00\n"
        "ATOM      2  CA  ALA A   1       1.400   0.000   0.000  1.00  0.00\n"
        "ATOM      3  C   ALA A   1       2.000   1.300   0.000  1.00  0.00\n"
        "ATOM      4  O   ALA A   1       1.400   2.300   0.000  1.00  0.00\n"
        "END\n"
    )
    return SinglefileData.from_string(pdb_content)
