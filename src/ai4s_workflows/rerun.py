"""
下游重算入口（C 模块核心交付之一）。

目标：只改 top_k 或 score_threshold 时，创建新的筛选过程、复用相同的上游 Data，
      且模型（ProteinMPNN）的外部启动次数不增加。

实现：复用旧 WorkChain 的 `sequences` / `scores` 输出节点，作为新 WorkChain 的
      `sequences_in` / `scores_in` 输入，并置 `reuse=True`。WorkChain 走复用分支，
      不提交任何推理 CalcJob，因此模型启动次数不变。

用法（verdi shell）：
    from ai4s_workflows import rerun_filter_only
    new_pk = rerun_filter_only(old_wc_pk, new_top_k=3, new_threshold=1.10)
"""
from aiida.engine import run, submit
from aiida.orm import load_node, Dict, Bool, SinglefileData

from .workflows import ProteinMPNNFilterWorkChain


def rerun_filter_only(old_wc_pk, new_top_k=None, new_threshold=None, background=False):
    """基于已跑完的 WorkChain，仅重算筛选，复用上游 Data，不重跑模型。

    Args:
        old_wc_pk: 已跑完的旧 WorkChain 节点 pk。
        new_top_k: 新的 top_k，None 则沿用旧值。
        new_threshold: 新的 score_threshold，None 则沿用旧值。
        background: True 用 submit(需 daemon)，False 用 run(同步，调试)。

    Returns:
        新 WorkChain 的 pk（background=True 时返回 pk；False 时返回 (results, wc)）。
    """
    old_wc = load_node(old_wc_pk)

    # 复用旧 WorkChain 已合格的上游输出（公共接口：sequences / scores）
    reused_sequences = old_wc.outputs["sequences"]
    reused_scores = old_wc.outputs["scores"]

    old_filter = old_wc.inputs.filter_params.get_dict()
    new_filter = Dict({
        "top_k": int(new_top_k) if new_top_k is not None else int(old_filter["top_k"]),
        "score_threshold": float(new_threshold) if new_threshold is not None
                           else float(old_filter["score_threshold"]),
    }).store()

    builder = ProteinMPNNFilterWorkChain.get_builder()
    builder.reuse = Bool(True)
    builder.sequences_in = reused_sequences
    builder.scores_in = reused_scores
    builder.filter_params = new_filter
    # code / pdb / infer_params 在复用分支不会被使用，可不填

    if background:
        node = submit(builder)
        print(f"[重算] 后台提交完成，新 WorkChain pk={node.pk}，复用上游 Data，模型启动次数不增加")
        return node.pk

    results, wc = run(builder)
    print(f"[重算] 完成，新 WorkChain pk={wc.pk}")
    print(f"[重算] 筛选报告: {results['selection_report'].get_dict()}")
    print(f"[重算] 复用上游 Data，未启动模型推理（model_launches 来自旧流程）")
    return results, wc
