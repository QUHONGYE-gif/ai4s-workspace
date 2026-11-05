from aiida.orm import load_node, Dict
from aiida.engine import submit
from .workflows import ProteinMPNNFilterWorkChain


def rerun_filter_only(old_wc_pk: int, new_top_k=None, new_threshold=None):
    """
    C模块重算入口：只修改筛选参数，复用上游MPNN输出，不会提交新MPNN计算任务
    :param old_wc_pk: 原始成功跑完的workchain pk
    :param new_top_k: 新top_k；None沿用旧值
    :param new_threshold: 新score_threshold；None沿用旧值
    :return: 新提交workchain实例
    """
    old_wc = load_node(old_wc_pk)
    if not old_wc.is_finished_ok:
        raise RuntimeError("原始WorkChain必须成功完成，才允许重筛选")

    # 从原始workchain的called子节点取出【成功结束】的上游MPNN结果
    upstream_mpnn_result = None
    for child in old_wc.called:
        if child.is_finished_ok and hasattr(child, "outputs") and hasattr(child.outputs, "result"):
            upstream_mpnn_result = child.outputs.result
            break
    if upstream_mpnn_result is None:
        raise RuntimeError("无法从原始workchain获取上游MPNN结果，不能执行重筛选")

    old_filter_params = old_wc.inputs.filter_params.get_dict()
    new_filter_dict = {
        "score_threshold": new_threshold if new_threshold is not None else old_filter_params["score_threshold"],
        "top_k": new_top_k if new_top_k is not None else old_filter_params["top_k"]
    }

    builder = ProteinMPNNFilterWorkChain.get_builder()
    builder.code = old_wc.inputs.code
    builder.pdb_file = old_wc.inputs.pdb_file
    builder.mpnn_params = old_wc.inputs.mpnn_params
    builder.filter_params = Dict(new_filter_dict)
    builder.existing_mpnn_result = upstream_mpnn_result

    new_wc = submit(builder)
    print(f"重筛选流程提交完成，新workchain pk={new_wc.pk}")
    return new_wc
