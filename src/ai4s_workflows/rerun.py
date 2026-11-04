"""
下游重算入口：复用上游 Data，不重跑模型
- rerun_filter_only：只改筛选参数，复用已有 MPNN 结果
- count_infer_launches：统计某 WorkChain 下 MPNN 模型启动次数
"""
from aiida.orm import load_node, Dict
from aiida.engine import submit
from .workflows import ProteinMPNNFilterWorkChain
from .calcjobs import LightMPNNCalcJob
from aiida.orm.querybuilder import QueryBuilder


def rerun_filter_only(old_wc_pk: int,
                      new_top_k: int = None,
                      new_threshold: float = None) -> object:
    """
    重算入口：复用上游 MPNN 产物，只重新筛选
    :param old_wc_pk: 原有已完成 WorkChain 的 pk
    :param new_top_k: 新的 top_k
    :param new_threshold: 新的 score_threshold
    :return: 新提交的 WorkChain 节点
    """
    old_wc = load_node(old_wc_pk)

    if not old_wc.is_finished_ok:
        raise RuntimeError(
            f"原始 WorkChain (pk={old_wc_pk}) 未正常完成，"
            f"状态 = {old_wc.process_state}，无法重筛选"
        )

    # 取出上游已有的 MPNN 结果（复用，不重跑）
    old_mpnn_result = old_wc.outputs.mpnn_result
    old_filter_params = old_wc.inputs.filter_params.get_dict()

    # 合并新筛选参数
    new_fp = {
        "score_threshold": new_threshold
        if new_threshold is not None
        else old_filter_params["score_threshold"],
        "top_k": new_top_k
        if new_top_k is not None
        else old_filter_params["top_k"],
    }

    # 构造新 WorkChain，传入 existing_mpnn_result 跳过 MPNN 阶段
    builder = ProteinMPNNFilterWorkChain.get_builder()
    builder.code = old_wc.inputs.code
    builder.pdb_file = old_wc.inputs.pdb_file
    builder.mpnn_params = old_wc.inputs.mpnn_params
    builder.filter_params = Dict(new_fp)
    # 关键：传入已有 MPNN 结果，WorkChain 内部会跳过推理阶段
    builder.existing_mpnn_result = old_mpnn_result

    new_wc = submit(builder)
    print(f"重筛选 WorkChain 已提交，pk = {new_wc.pk}")
    print("✅ 验证点：model_launches 应为 0（复用上游，不启动模型）")
    return new_wc


def count_infer_launches(wc_pk: int) -> int:
    """
    统计某 WorkChain 下 MPNN 模型（LightMPNNCalcJob）的启动次数
    用于验收：重筛前后 model_launches 不变
    """
    qb = QueryBuilder()
    qb.append(
        ProteinMPNNFilterWorkChain,
        filters={"id": wc_pk},
        tag="wc",
    )
    qb.append(LightMPNNCalcJob, with_incoming="wc")
    return qb.count()
