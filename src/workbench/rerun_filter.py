# 用法：在verdi shell里，直接 import 这个脚本的函数
from aiida.orm import load_node, Dict
from workbench.workchains.protein_mpnn_filter import ProteinMPNNFilterWorkChain

def rerun_filter_only(old_wc_pk, new_top_k=None, new_threshold=None):
    # 1. 从老的workchain里直接拿出已经算好的MPNN结果，完全不重新跑模型
    old_wc = load_node(old_wc_pk)
    reused_pdb = old_wc.inputs.pdb_file
    reused_infer = old_wc.inputs.infer_params
    old_filter = old_wc.inputs.filter_params

    # 2. 只改筛选参数，推理参数、PDB完全不变
    new_filter = Dict({
        "top_k": new_top_k if new_top_k else old_filter["top_k"],
        "threshold": new_threshold if new_threshold else old_filter["threshold"]
    })

    # 3. 提交新workchain，它跑的时候会复用上游逻辑，根本不会再启动MPNN
    builder = ProteinMPNNFilterWorkChain.get_builder()
    builder.pdb_file = reused_pdb
    builder.infer_params = reused_infer
    builder.filter_params = new_filter.store()
    new_wc = builder.submit()
    print(f"重算提交完成：新workchain pk={new_wc.pk}，复用了老MPNN结果，模型启动次数不会增加")
    return new_wc
