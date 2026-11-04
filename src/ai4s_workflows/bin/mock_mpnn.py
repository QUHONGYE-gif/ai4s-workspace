#!/usr/bin/env python3
"""
轻量 Mock：模拟 ProteinMPNN 的外部可执行程序，供 C 模块独立开发使用。

行为（与真实 ProteinMPNN 的公共接口对齐）：
  - 输入一个 PDB 文件 + 参数（单温度、batch_size、seed）
  - 输出 4 条设计序列 + 匹配分数 + 产物清单 manifest.json
  - 可配置「前 fail_if_le 次尝试失败」，用于验证有限重试
  - 可配置 sleep，用于验证 daemon 中断后的恢复

用法（由 LightMPNNCalcJob 在 prepare_for_submission 里拼好 argv）：
  python mock_mpnn.py --pdb INPUT.pdb --seqout design.fa --scoreout scores.json \
      --manifestout manifest.json --attempt N --fail-if-le K --sleep S
"""
import argparse
import json
import pathlib
import sys
import time

# 与文档人工验收样例一致的分数：阈值 1.10/top_k=2 -> s001,s002；top_k=3 -> +s003；阈值 0.70 -> 空
SAMPLE_IDS = ["s001", "s002", "s003", "s004"]
SAMPLE_SCORES = [0.85, 1.00, 1.05, 1.20]   # 分数越低越好（≤ score_threshold 入选）
SAMPLE_SEQS = ["AAAA", "BBBB", "CCCC", "DDDD"]
SCHEMA_VERSION = "ai4s-artifacts-1"
CONTRACT_VERSION = "1"


def main() -> int:
    parser = argparse.ArgumentParser(description="mock proteinmpnn")
    parser.add_argument("--pdb", required=True)
    parser.add_argument("--seqout", required=True)
    parser.add_argument("--scoreout", required=True)
    parser.add_argument("--manifestout", required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--fail-if-le", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=0.0)
    args = parser.parse_args()

    if args.sleep > 0:
        time.sleep(args.sleep)

    outdir = pathlib.Path(args.seqout).parent
    outdir.mkdir(parents=True, exist_ok=True)

    # 可控失败：当本次尝试编号 <= fail_if_le 时模拟失败
    if args.attempt <= args.fail_if_le:
        with open(outdir / "_FAILED", "w") as f:
            f.write(f"mock simulated failure on attempt {args.attempt}\n")
        print(f"mock: simulated failure on attempt {args.attempt}", file=sys.stderr)
        return 1

    # 写 fasta
    with open(args.seqout, "w") as f:
        for sid, seq in zip(SAMPLE_IDS, SAMPLE_SEQS):
            f.write(f">{sid}\n{seq}\n")

    # 写分数
    scores = {"sample_ids": SAMPLE_IDS, "scores": SAMPLE_SCORES}
    with open(args.scoreout, "w") as f:
        json.dump(scores, f, indent=2)

    # 写清单（对齐文档示例，files 为 Repository 相对路径）
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "task_id": "proteinmpnn",
        "contract_version": CONTRACT_VERSION,
        "validation": {
            "passed": True,
            "validator_version": "proteinmpnn-1",
        },
        "artifacts": [
            {
                "port": "artifacts.sequences",
                "role": "primary",
                "format": "fasta",
                "files": ["design.fa"],
                "sample_count": len(SAMPLE_IDS),
                "sample_ids": SAMPLE_IDS,
            },
            {
                "port": "artifacts.scores",
                "role": "primary",
                "format": "json",
                "files": ["scores.json"],
                "sample_count": len(SAMPLE_IDS),
                "sample_ids": SAMPLE_IDS,
            },
        ],
    }
    with open(args.manifestout, "w") as f:
        json.dump(manifest, f, indent=2)

    print("mock: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
