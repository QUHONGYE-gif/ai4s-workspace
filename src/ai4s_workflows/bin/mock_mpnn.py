#!/usr/bin/env python3
"""
Mock ProteinMPNN 可执行脚本
被 AiiDA Code 调用，模拟 MPNN 推理过程
- 读取 params.json 和 input.pdb
- 输出 result.json（含 version / sequences / scores）
- 支持随机失败（用于测试重试机制）
"""
import json
import sys
import os
import random


def main():
    # 读取参数
    params_path = "params.json"
    if not os.path.exists(params_path):
        print("ERROR: params.json not found", file=sys.stderr)
        sys.exit(101)

    with open(params_path, "r", encoding="utf-8") as f:
        params = json.load(f)

    version = params.get("version", "v1.0")
    num_seq = params.get("num_seq", 3)

    # 模拟随机失败（30% 概率），用于测试重试
    if random.random() < 0.3:
        print(f"[MOCK] Simulated failure at version={version}", file=sys.stderr)
        sys.exit(101)

    # 生成模拟序列和分数
    # 分数范围：0.8 ~ 1.3，便于测试 threshold 筛选
    sequences = []
    scores = []
    for i in range(num_seq):
        seq = "".join(random.choices("ACDEFGHIKLMNPQRSTVWY", k=20))
        score = round(random.uniform(0.8, 1.3), 3)
        sequences.append(seq)
        scores.append(score)

    result = {
        "version": version,
        "sequences": sequences,
        "scores": scores,
    }

    # 输出 result.json
    with open("result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"[MOCK] ProteinMPNN completed, version={version}, num_seq={num_seq}")


if __name__ == "__main__":
    main()
