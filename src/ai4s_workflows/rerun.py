from aiida.engine import submit
from aiida.orm import CalcJobNode, Dict, load_node
from .workflows import WORKCHAIN_PROCESS_TYPE, ProteinMPNNFilterWorkChain


def rerun_filter_only(old_wc_pk: int, new_top_k=None, new_threshold=None):
    """
    C模块重算入口：只修改筛选参数，复用上游MPNN输出，不会提交新MPNN计算任务
    :param old_wc_pk: 原始成功跑完的workchain pk
    :param new_top_k: 新top_k；None沿用旧值
    :param new_threshold: 新score_threshold；None沿用旧值
    :return: 新提交workchain实例
    """
    old_wc = load_node(old_wc_pk)
    if not isinstance(old_wc, ProteinMPNNFilterWorkChain) and old_wc.process_type != WORKCHAIN_PROCESS_TYPE:
        raise TypeError("old_wc_pk 必须指向 ProteinMPNNFilterWorkChain")
    if not old_wc.is_finished_ok:
        raise RuntimeError("原始WorkChain必须成功完成，才允许重筛选")

    # 重筛选流程没有推理子任务；其原生输入继续指向同一上游 Data。
    upstream_mpnn_result = (
        old_wc.inputs.existing_mpnn_result if "existing_mpnn_result" in old_wc.inputs else None
    )
    if upstream_mpnn_result is None:
        inference_children = [
            child for child in old_wc.called
            if isinstance(child, CalcJobNode)
            and child.is_finished_ok
            and "result" in child.outputs
        ]
        if len(inference_children) != 1:
            raise RuntimeError(
                f"原始workchain应恰有一个成功推理子任务，实际为 {len(inference_children)} 个"
            )
        upstream_mpnn_result = inference_children[0].outputs.result
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
    builder.metadata.label = f"ai4s-filter-rerun:{old_wc.uuid}"

    new_wc = submit(builder)
    print(f"重筛选流程提交完成，新workchain pk={new_wc.pk}")
    return new_wc
