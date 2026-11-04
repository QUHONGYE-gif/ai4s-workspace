from aiida.orm import load_node, Dict
from aiida.engine import submit
from .workflows import ProteinMPNNFilterWorkChain


def rerun_filter_only(old_wc_pk: int, new_top_k=None, new_threshold=None):
    """
    C模块重算入口：只修改筛选参数，复用上游MPNN输出，**不会提交新MPNN计算任务**
    :param old_wc_pk: 原始成功跑完的workchain pk
    :param new_top_k: 新top_k；None代表沿用旧值
    :param new_threshold: 新score_threshold；None代表沿用旧值
    :return: 新提交workchain实例
    """
    old_wc = load_node(old_wc_pk)
    if not old_wc.is_finished_ok:
        raise RuntimeError("原始WorkChain必须成功完成，才允许重筛选")

    # 取出上游已经生成好的MPNN结果
    upstream_mpnn_result = old_wc.inputs.existing_mpnn_result if "existing_mpnn_result" in old_wc.inputs else None
    if upstream_mpnn_result is None:
        upstream_mpnn_result = old_wc.outputs.selected_sequences  # 从原始输出回溯，实际应当使用原推理输出
        upstream_mpnn_result = old_wc.outputs["mpnn_result"] if "mpnn_result" in old_wc.outputs else None

    # 获取旧筛选参数
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
    # 关键：传入已有MPNN结果，workchain直接跳过MPNN提交
    builder.existing_mpnn_result = upstream_mpnn_result

    new_wc = submit(builder)
    print(f"重筛选流程提交完成，新workchain pk={new_wc.pk}")
    return new_wc
