# 下游重算入口：复用已有MPNN结果，只重新执行筛选，不重新启动模型
from aiida.orm import load_node, Dict
from workbench.workchains.protein_mpnn_filter import ProteinMPNNFilterWorkChain

def rerun_filter_only(old_wc_pk, new_top_k=None, new_threshold=None):
    """
    基于已跑完的老WorkChain，只改筛选参数，不重新跑MPNN
    :param old_wc_pk: 老的workchain节点pk
    :param new_top_k: 新的top_k值，不传就沿用老值
    :param new_threshold: 新的阈值，不传就沿用老值
    """
    old_wc = load_node(old_wc_pk)
    # 直接复用老的输入（PDB、MPNN参数），完全不重新提交MPNN
    reused_pdb = old_wc.inputs.pdb_file
    reused_infer = old_wc.inputs.infer_params
    old_filter = old_wc.inputs.filter_params

    # 只改筛选参数
    new_filter = Dict({
        "top_k": new_top_k if new_top_k else old_filter["top_k"],
        "threshold": new_threshold if new_threshold else old_filter["threshold"]
    }).store()

    builder = ProteinMPNNFilterWorkChain.get_builder()
    builder.pdb_file = reused_pdb
    builder.infer_params = reused_infer
    builder.filter_params = new_filter
    new_wc = builder.submit()

    print(f"重算已提交：新workchain pk={new_wc.pk}，复用上游MPNN结果，模型启动次数不会增加")
    return new_wc.pk
