from aiida.engine import submit
from aiida.orm import Dict
from aiida.orm import load_code
from .workflows import ProteinMPNNFilterWorkChain
from .samples import make_test_pdb


def submit_workchain(code_label: str, threshold: float, top_k: int, version="v1.0"):
    """
    文档4.1 正常两阶段流程对外入口：MPNN生成 → 筛选
    :param code_label: mock code标签，例如 mock-mpnn@localhost
    :param threshold: score_threshold 分数阈值
    :param top_k: top_k 筛选保留条数
    :param version: mpnn版本，支持 v1.0 / v1.1
    :return: 提交后的workchain对象
    """
    try:
        code = load_code(label=code_label)
    except Exception as e:
        raise RuntimeError(f"找不到code：{code_label}，先 verdi code setup 注册！") from e

    pdb = make_test_pdb()
    mpnn_params = Dict({"version": version, "num_seq": 4})
    filter_params = Dict({"score_threshold": threshold, "top_k": top_k})

    builder = ProteinMPNNFilterWorkChain.get_builder()
    builder.code = code
    builder.pdb_file = pdb
    builder.mpnn_params = mpnn_params
    builder.filter_params = filter_params

    wc = submit(builder)
    print(f"4.1两阶段WorkChain提交成功 pk={wc.pk}")
    return wc
