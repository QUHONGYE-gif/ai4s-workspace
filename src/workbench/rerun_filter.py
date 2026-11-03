# 下游重算入口：复用已有MPNN结果，只重新执行筛选，不重新启动模型
from aiida.orm import load_node, Dict, Bool
from aiida.engine import run
from workbench.workchains.protein_mpnn_filter import ProteinMPNNFilterWorkChain

def rerun_filter_only(old_wc_pk, new_top_k=None, new_threshold=None):
    """
    基于已跑完的老WorkChain，只改筛选参数，不重新跑MPNN
    :param old_wc_pk: 老的workchain节点pk
    :param new_top_k: 新的top_k值，不传就沿用老值
    :param new_threshold: 新的阈值，不传就沿用老值
    """
    old_wc = load_node(old_wc_pk)
    # ✅ 核心：复用【已经生成好的MPNN输出节点】，而不是pdb/推理参数
    reused_mpnn_result = old_wc.outputs["mpnn_raw_output"]
    old_filter = old_wc.inputs.filter_params

    # 构造新筛选参数
    new_filter = Dict({
        "top_k": new_top_k if new_top_k is not None else old_filter["top_k"],
        "threshold": new_threshold if new_threshold is not None else old_filter["threshold"]
    }).store()

    builder = ProteinMPNNFilterWorkChain.get_builder()
    # 开启复用模式
    builder.reuse_mpnn = Bool(True)
    builder.mpnn_raw_output = reused_mpnn_result
    builder.filter_params = new_filter

    # 注意：daemon没启动时用run；有daemon再换回submit
    # new_wc = submit(builder)
    result, new_wc = run(builder)
    print(f"重算完成：新workchain pk={new_wc.pk}")
    print("✅ 复用上游MPNN结果，没有启动模型推理")
    return new_wc.pk
