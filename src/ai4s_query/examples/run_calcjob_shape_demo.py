# -*- coding: utf-8 -*-
"""接入就绪演示：把「站 ③④ 的 CalcJob 产物」与「站 ⑥⑧ 的决策记录」两种形状
在本机造出来，证明两边接入时**不需要改站 5/9 的代码**。

跑法（在已配置 profile 的 AiiDA 环境里）：

    export PYTHONPATH=$PWD/src
    python src/ai4s_query/examples/run_calcjob_shape_demo.py [--profile ai4s]

它做三件事：
1. 造一个「CalcJob 形状」的过程：产物是 FolderData（seqs/design.fa + scores/*.npz），
   FASTA header 带 score=/global_score=，与真实 ProteinMPNN 输出同构；
2. 用 candidates 查它，看 ④ 的 9 个字段怎么填、条数与分数怎么算出来；
3. 造一条 ⑤ 决策记录写到 attributes + 旁路文件，再用 decision.load 读回来校验。

全部输出落在 ``~/runs/integration-<时间戳>/``。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def make_calcjob_shape(seq: str, num: int = 2):
    """造一个与真实 ProteinMPNN CalcJob 同构的过程节点。

    真实 CalcJob 的产物是 ``FolderData``（retrieved/seqs/design.fa + scores/*.npz），
    这里用 calcfunction 返回同样的 FolderData，因此站 5 面对的是同一种节点形状；
    区别只在 CalcJob 还多一个 exit_status，判定逻辑用 ``exit_code in (None, 0)`` 兼容两者。
    """
    from aiida.engine import calcfunction
    from aiida.orm import Dict, FolderData, Int, Str

    @calcfunction
    def mpnn_like(sequence, n):
        n = n.value
        folder = FolderData()
        lines = []
        for i in range(n):
            score = round(1.20 + 0.11 * i, 3)
            global_score = round(score + 0.07, 3)
            lines.append(
                f">T=0.1, sample={i + 1}, score={score}, "
                f"global_score={global_score}, seq_recovery=0.48")
            lines.append(seq)
        folder.put_object_from_filelike(
            io.BytesIO(("\n".join(lines) + "\n").encode()), "seqs/design.fa")
        folder.put_object_from_filelike(
            io.BytesIO(b"\x93NUMPY fake-scores-bytes" + b"0" * 64), "scores/design.npz")
        folder.put_object_from_filelike(
            io.BytesIO(json.dumps({"model": "proteinmpnn", "T": 0.1}).encode()),
            "run.json")
        stats = Dict({"num_sequences": n, "input_length": len(sequence.value)})
        return {"results": folder, "stats": stats}

    _, node = mpnn_like.run_get_node(Str(seq), Int(num))
    return node


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    ap.add_argument("--seq", default="MKTAYIAKQRQISFVKSHFSRQ")
    ap.add_argument("--num", type=int, default=2)
    args = ap.parse_args(argv)

    from aiida import load_profile

    load_profile(args.profile) if args.profile else load_profile()

    from ai4s_query import candidates as cand_mod
    from ai4s_query import decision as dec_mod

    outdir = Path.home() / "runs" / f"integration-{_now()}"
    outdir.mkdir(parents=True, exist_ok=True)
    log = []

    def say(line=""):
        print(line)
        log.append(line)

    say("=== 一、CalcJob 形状的产物能不能被读成候选 ===")
    proc = make_calcjob_shape(args.seq, args.num)
    # 关键：by_node 会切 profile，切换后这个对象与存储会话脱钩，必须先取成字符串
    proc_uuid, proc_pk = proc.uuid, proc.pk
    say(f"过程 {proc_pk} {proc_uuid}（{proc.process_type.split(':')[-1]}）")
    bundle = cand_mod._bundle(proc)
    say(f"产物节点种类 {bundle['out_kinds']}　文件 {bundle['file_count']} 个　"
        f"共 {bundle['size_bytes']} B")
    say(f"FASTA 条数 {bundle['seq_count']}　最优 score={bundle['best_score']}　"
        f"最优 global_score={bundle['best_global_score']}")
    for f in bundle["files"]:
        say(f"    · {f['path']}  {f['size']} B")

    ok, reason, text = cand_mod.qualify(proc, bundle, {})
    say(f"判定（无请求约束）：合格={ok} 原因={reason or '—'}")

    result = cand_mod.by_node(proc_uuid, {"num_sequences": 2, "score_threshold": 1.5})
    cand = next(c for c in result["candidates"] if c["process_uuid"] == proc_uuid)
    say("")
    say("按约定④ 填出来的字段：")
    for key in ("uuid", "fingerprint", "member", "location", "size_bytes",
                "elapsed_s", "qualified", "reason", "note"):
        value = cand[key]
        if key == "fingerprint" and value:
            value = str(value)[:32] + "…"
        say(f"    {key:<12} {value}")

    say("")
    say("=== 二、判定在边界上的行为（不依赖节点类型）===")
    # by_node 切过 profile，之前那个 proc 对象已失效；重新载入后再演示判定
    from aiida.orm import load_node

    proc = load_node(proc_pk)
    cases = [
        ("值型产物（Dict 无文件）", {"out_count": 1, "out_kinds": ["Dict"], "has_value": True,
                                    "has_archive": False, "file_count": 0, "size_bytes": 0,
                                    "seq_count": 0, "best_score": None}),
        ("仓库型产物但没文件", {"out_count": 1, "out_kinds": ["FolderData"], "has_archive": True,
                                "file_count": 0, "size_bytes": 0, "seq_count": 0,
                                "best_score": None}),
        ("RemoteData 未 retrieve", {"out_count": 1, "out_kinds": ["RemoteData"],
                                    "has_archive": True, "unretrieved": True, "file_count": 0,
                                    "size_bytes": 0, "seq_count": 0, "best_score": None}),
        ("有 FASTA 但条数不够", {"out_count": 1, "out_kinds": ["FolderData"], "has_archive": True,
                                 "file_count": 2, "size_bytes": 512, "seq_count": 2,
                                 "best_score": 1.2}),
    ]
    for name, b in cases:
        ok, reason, text = cand_mod.qualify(proc, b, {"num_sequences": 8})
        say(f"    {name:<22} → {'合格' if ok else text}")

    say("")
    say("=== 三、决策记录：一条命令写入，立刻能读回 ===")
    record = {
        "request_id": f"req-integ-{proc_pk}",
        "process_uuid": proc_uuid,
        "reuse_policy": "allow_reuse",
        "candidate_compare_list": [
            {"uuid": cand["uuid"], "fingerprint": cand["fingerprint"],
             "member": cand["member"], "qualified": True, "reason": None},
        ],
        "final_decision": {"action": "reuse",
                           "selected_candidate_uuid": cand["uuid"],
                           "effective_seed": None},
        "reason": {"reason_code": "R01",
                   "reason_text": "允许复用，存在合格候选，按规则选中一条"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    saved = dec_mod.save(record, process=proc_uuid, directory=outdir)
    say(f"写入结果：ok={saved['ok']}　问题={saved['problems'] or '无'}")
    for w in saved["written"]:
        say(f"    → {w}")

    back_from_node = dec_mod.load(proc_uuid, directory=outdir)
    say(f"按过程 UUID 读回：{back_from_node['count']} 条，来源 "
        f"{back_from_node['records'][0]['_source'] if back_from_node['count'] else '—'}，"
        f"校验 {'通过' if back_from_node['count'] and back_from_node['records'][0]['_ok'] else '未通过'}")

    bad = dict(record, request_id=f"req-bad-{proc.pk}",
               final_decision={"action": "rerun", "selected_candidate_uuid": None,
                               "effective_seed": None})
    rejected = dec_mod.save(bad, process=proc_uuid, directory=outdir)
    say(f"故意写一条自相矛盾的记录（R01 + rerun）：ok={rejected['ok']}　"
        f"{rejected['skipped']}　原因={rejected['problems']}")

    say("")
    say("=== 四、接入体检 preflight ===")
    pf = cand_mod.preflight(limit=5)
    for it in pf["items"][:5]:
        mark = {"ready": "✔", "partial": "△", "blocked": "✘"}.get(it["status"], "?")
        say(f"    {mark} pk={it['pk']} {it.get('label') or ''} "
            f"out={','.join(it.get('out_kinds') or [])} files={it.get('file_count')} "
            f"seqs={it.get('seq_count')}")
        for h in it.get("hints") or []:
            say(f"        · {h}")

    (outdir / "接入就绪记录.txt").write_text("\n".join(log), encoding="utf-8")
    (outdir / "候选节点.json").write_text(
        json.dumps(cand, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (outdir / "决策记录.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[记录已写入 {outdir}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
