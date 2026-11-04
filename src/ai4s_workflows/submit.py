"""
提交入口：封装 builder，对外统一提交函数
"""
from aiida.engine import submit
from aiida.orm import Dict, load_code
from .workflows import ProteinMPNNFilterWorkChain
from .samples import make_test_pdb


def submit_workchain(code_label: str,
                     threshold: float = 1.10,
                     top_k: int = 2,
                     version: str = "v1.0",
                     num_seq: int = 3) -> object:
    """
    对外提交函数（文档 4.1 测试入口）
    :param code_label: Code 标签，如 "mock-mpnn@localhost"
    :param threshold: 筛选阈值 score_threshold
    :param top_k: 取前 k 条
    :param version: MPNN 模型版本
    :param num_seq: 生成序列数
    :return: WorkChain 节点
    """
    code = load_code(label=code_label)
    pdb = make_test_pdb()

    mpnn_params = Dict({
        "version": version,
        "num_seq": num_seq,
    })
    filter_params = Dict({
        "score_threshold": threshold,
        "top_k": top_k,
    })

    builder = ProteinMPNNFilterWorkChain.get_builder()
    builder.code = code
    builder.pdb_file = pdb
    builder.mpnn_params = mpnn_params
    builder.filter_params = filter_params

    wc = submit(builder)
    print(f"ProteinMPNNFilterWorkChain 已提交，pk = {wc.pk}")
    return wc
