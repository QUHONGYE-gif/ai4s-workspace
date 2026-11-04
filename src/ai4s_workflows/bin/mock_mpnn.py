#!/usr/bin/env python3
import json
import sys
import random


def main():
    with open("params.json", "r", encoding="utf‑8") as f:
        params = json.load(f)

    # 40%概率模拟失败，用于验证重试逻辑
    if random.random() < 0.40:
        print("MOCK ERROR: MPNN runtime crash", file=sys.stderr)
        sys.exit(101)

    ver = params["version"]
    # 严格按照文档的artifacts schema输出JSON
    output_data = {
        "schema_version": "ai4s-artifacts-1",
        "version": ver,
        "task_id": "proteinmpnn",
        "contract_version": "1",
        "validation": {"passed": True, "validator_version": "proteinmpnn‑1"},
        "artifacts": [
            {
                "port": "artifacts.sequences",
                "role": "primary",
                "sample_count": 4,
                "samples": [
                    {"sample_id": "s001", "seq": "AAAA", "score": 0.95},
                    {"sample_id": "s002", "seq": "BBBB", "score": 1.00},
                    {"sample_id": "s003", "seq": "CCCC", "score": 1.08},
                    {"sample_id": "s004", "seq": "DDDD", "score": 1.20}
                ]
            }
        ]
    }

    with open("result.json", "w", encoding="utf‑8") as f:
        json.dump(output_data, f)


if __name__ == "__main__":
    main()
