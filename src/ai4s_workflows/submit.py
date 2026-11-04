"""
C 模块提交入口：从真实 PDB + 参数提交两阶段 WorkChain。

提供：
  - `submit_workchain(...)`：Python 函数入口，返回节点/结果
  - `--main` 命令行入口：`python -m ai4s_workflows.submit --pdb x.pdb ...`

示例（verdi shell）：
    from ai4s_workflows.submit import submit_workchain
    wc = submit_workchain(pdb_path="x.pdb", code_label="mock-mpnn@localhost")
"""
import argparse

from aiida.engine import run, submit
from aiida.orm import SinglefileData, Dict, Bool, Int, Float, load_code

from .workflows import ProteinMPNNFilterWorkChain

DEFAULT_INFER = {"version": "v1.0", "temperature": 0.1, "batch_size": 1, "seed": 42}
DEFAULT_FILTER = {"score_threshold": 1.10, "top_k": 2}


def submit_workchain(pdb_path, code_label, infer_params=None, filter_params=None,
                     fail_if_le=0, sleep=0.0, background=False):
    """提交两阶段 WorkChain。

    Args:
        pdb_path: 本地 PDB 文件路径。
        code_label: 已注册 code 的 label，如 'mock-mpnn@localhost'。
        infer_params: dict 覆盖默认推理参数。
        filter_params: dict 覆盖默认筛选参数。
        fail_if_le: 前 N 次推理尝试模拟失败（故障样例用）。
        sleep: 模拟计算耗时（秒），daemon 恢复验证用。
        background: True 用 submit(需 daemon)，False 用 run(同步)。
    """
    params = dict(DEFAULT_INFER)
    params.update(infer_params or {})
    fparams = dict(DEFAULT_FILTER)
    fparams.update(filter_params or {})

    pdb = SinglefileData(pdb_path).store()
    infer = Dict(params).store()
    filt = Dict(fparams).store()
    code = load_code(code_label)

    builder = ProteinMPNNFilterWorkChain.get_builder()
    builder.pdb = pdb
    builder.code = code
    builder.infer_params = infer
    builder.filter_params = filt
    builder.reuse = Bool(False)
    builder.fail_if_le = Int(fail_if_le)
    builder.sleep = Float(sleep)

    if background:
        node = submit(builder)
        print(f"[提交] 后台提交完成，WorkChain pk={node.pk}")
        return node

    results, wc = run(builder)
    print(f"[提交] 完成，WorkChain pk={wc.pk}")
    print(f"[提交] 筛选报告: {results['selection_report'].get_dict()}")
    return results, wc


def main():
    ap = argparse.ArgumentParser(description="提交 C 模块两阶段 WorkChain")
    ap.add_argument("--pdb", required=True, help="PDB 文件路径")
    ap.add_argument("--code", default="mock-mpnn@localhost", help="推理 code label")
    ap.add_argument("--top-k", type=int, default=None)
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--fail-if-le", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--background", action="store_true", help="后台提交(需daemon)")
    args = ap.parse_args()

    fparams = {}
    if args.top_k is not None:
        fparams["top_k"] = args.top_k
    if args.threshold is not None:
        fparams["score_threshold"] = args.threshold

    submit_workchain(
        pdb_path=args.pdb,
        code_label=args.code,
        filter_params=fparams or None,
        fail_if_le=args.fail_if_le,
        sleep=args.sleep,
        background=args.background,
    )


if __name__ == "__main__":
    main()
