#!/usr/bin/env python3
"""Opt-in live DeepSeek acceptance against a running local demo (incurs API use)."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly enable real provider calls")
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    parser.add_argument("--output", required=True, help="Private JSON report path (not a key file)")
    args = parser.parse_args()
    if not args.live:
        parser.error("需 --live 明确启用真实 API 验收；会消耗已配置账号的 API 额度")
    checks = []
    report = {"started": datetime.now(timezone.utc).isoformat(), "kind": "real_provider_acceptance", "checks": checks}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    with httpx.Client(base_url=args.url, timeout=115) as client:
        def post(path, data=None, **kwargs):
            response = client.post(path, json=data, **kwargs)
            if not response.is_success:
                report.setdefault("http_failures", []).append({"endpoint": path, "status": response.status_code,
                                                                "response": response.json()})
                save()
            response.raise_for_status()
            return response.json()

        def check(name, condition, **evidence):
            checks.append({"name": name, "passed": bool(condition), **evidence})
            print(f"{'PASS' if condition else 'FAIL'} {name}", flush=True)
            save()
            if not condition:
                raise AssertionError(name)

        report["provider_config"] = client.get("/api/settings/model").json()
        connected = post("/api/settings/model/test")
        check("真实 DeepSeek 连接与结构化返回", connected["ok"], usage=connected["usage"])
        state = post("/api/workflows", {"name": "真实 API 验收（独立测试工作流）", "template": "protein"})
        wid = state["draft"]["id"]
        report["workflow_id"] = wid
        base = f"/api/workflows/{wid}"
        counter = 0

        def mutate(ops):
            nonlocal state, counter
            counter += 1
            result = post(base + "/changes", {"expected_revision": state["draft"]["revision"],
                          "operation_id": f"verify-op-{counter}", "operations": ops, "confirmed": True})
            state = result["state"]
            return result

        def chat(name, message, selected, changed, expected=None):
            nonlocal state, counter
            counter += 1
            before = state["draft"]
            response = post(base + "/messages", {"expected_revision": before["revision"],
                         "operation_id": f"verify-chat-{counter}", "message": message, "selected_node_id": selected})
            state = response["state"]
            actual_changed = state["draft"] != before
            condition = actual_changed == changed and (expected(state) if expected else True)
            check(name, condition, prompt=message, intent=response["message"]["intent"],
                  reply=response["message"]["text"], summary=response["message"]["summary"],
                  tools=response["message"]["tools"], usage=response["message"]["usage"],
                  before_revision=before["revision"], after_revision=state["draft"]["revision"])

        def item(s, node_id):
            return next(n for n in s["draft"]["nodes"] if n["id"] == node_id)

        pdb = Path(__file__).resolve().parents[1] / "experiments/R001-protein-design-smoke/evidence/backbone.pdb"
        uploaded = client.post("/api/files", files={"file": ("acceptance-backbone.pdb", pdb.read_bytes())})
        uploaded.raise_for_status()
        mutate([{"type": "set_input", "node_id": "mpnn-1", "port": "backbone", "value": {"kind": "file", "file_id": uploaded.json()["id"]}}])
        doc = "ProteinMPNN 调用示例（不是默认值声明）：\npython protein_mpnn_run.py --num_seq_per_target 8 --sampling_temp 0.1 --seed 42\n"
        preview = post(base + "/import-preview", {"model_id": "proteinmpnn", "content": doc, "source": "验收用调用示例；官方入口修订见模型定义"})
        extracted = {p["field"]: p["value"] for p in preview["accepted"]}
        check("真实资料识别与原文依据", not preview["errors"] and extracted == {"num_seq_per_target": 8, "sampling_temp": 0.1, "seed": 42}
              and all(p["category"] == "example" for p in preview["accepted"]), parameters=preview["accepted"], usage=preview["usage"])
        mutate([{"type": "apply_import", "node_id": "mpnn-1", "preview_id": preview["id"]}])
        chat("数字问答不改配置", "温度 0.2 是什么意思？不要修改当前参数。", "mpnn-1", False)
        chat("真实对话批量改参", "请把当前节点采样温度改成 0.2，设计序列数量改为 16。", "mpnn-1", True,
             lambda s: item(s, "mpnn-1")["params"]["sampling_temp"] == 0.2 and item(s, "mpnn-1")["params"]["num_seq_per_target"] == 16)
        chat("对话补充缺少的链策略", "这个 PDB 我要设计全部链，请登记这个链策略到草稿。", "mpnn-1", True,
             lambda s: item(s, "mpnn-1")["design_chain_policy"]["mode"] == "all")
        reg = post(base + "/registrations", {"expected_revision": state["draft"]["revision"], "operation_id": "verify-register", "node_ids": ["mpnn-1"]})
        state = reg["state"]
        generated = post(base + "/requests", {"registration_id": reg["registration"]["id"]})
        state = generated["state"]
        request = generated["request"]
        check("登记、参数和最终请求一致", request["steps"][0]["params"] == item(state, "mpnn-1")["params"]
              and request["execution_status"] == "not_submitted" and not request["ready_for_submission"], request_id=request["id"])
        chat("跨模型修改 RFdiffusion", "把 RFdiffusion 的骨架长度改为 90，骨架数量改成 2。", "mpnn-1", True,
             lambda s: item(s, "rfd-1")["params"]["length"] == 90 and item(s, "rfd-1")["params"]["num_designs"] == 2)
        chat("跨模型修改 Boltz", "把 Boltz 的 diffusion_samples 设成 2。", "mpnn-1", True,
             lambda s: item(s, "boltz-1")["params"]["diffusion_samples"] == 2)
        chat("含糊修改先澄清", "当前节点温度再高一点。", "mpnn-1", False)
        chat("非法批量要求不局部写入", "当前 ProteinMPNN 的温度改成0.3，序列数设为-1，两个一起改。", "mpnn-1", False)
        mutate([{"type": "add_node", "node_id": "boltz-2", "model_id": "boltz", "label": "第二个结构预测"}])
        chat("同模型多个节点歧义先澄清", "把 Boltz 的采样数改为3。", "mpnn-1", False)
        chat("明确只问不修改", "不要改任何参数，只解释 ProteinMPNN 的 seed=0 是什么意思。", "mpnn-1", False)
        check("后续修改令原请求过期", state["requests"][0]["stale"])
        report["finished"] = datetime.now(timezone.utc).isoformat()
        report["passed"] = all(c["passed"] for c in checks)
        save()
        print(f"{len(checks)} live checks passed; report: {output}", flush=True)


if __name__ == "__main__":
    main()
