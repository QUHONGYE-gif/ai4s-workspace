"""Deterministic experiment-configuration assistant used by the demo UI.

The production Agent in dev-ckz is model-backed.  The workbench deliberately
keeps a local, dependency-free adapter so the same request/operation contract
can be exercised when the demo is run without the Agent service.
"""

from __future__ import annotations

import re
from typing import Any


def _param(node: dict[str, Any], *terms: str) -> dict[str, Any] | None:
    for item in node.get("parameters", []) or []:
        haystack = " ".join(
            str(item.get(key, "")) for key in ("key", "label", "description")
        ).lower()
        if any(term in haystack for term in terms):
            return item
    return None


def _node_context(payload: dict[str, Any]) -> dict[str, Any]:
    context = payload.get("context")
    if isinstance(context, dict):
        node = context.get("selectedNode")
        if isinstance(node, dict):
            return node
    node = payload.get("selectedNode")
    return node if isinstance(node, dict) else {}


def respond(payload: dict[str, Any]) -> dict[str, Any]:
    """Return an Agent-like decision for the current experiment draft."""

    message = str(payload.get("message", "")).strip()
    node = _node_context(payload)
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    if not message:
        return {
            "intent": "clarify",
            "reply": "请告诉我想了解哪个参数，或要修改哪一项配置。",
            "operations": [],
            "needsConfirmation": False,
        }

    lowered = message.lower()
    if any(term in lowered for term in ("temperature", "温度", "采样温度")):
        parameter = _param(node, "temperature", "temp", "温度")
        value = parameter.get("default") if parameter else None
        detail = (
            f"当前节点的{parameter.get('label', 'sampling_temp')}控制采样随机性"
            if parameter
            else "温度参数通常控制采样随机性：值越高结果越多样，值越低结果越稳定。"
        )
        if value is not None:
            detail += f" 当前默认值为 {value}。"
        return {
            "intent": "answer",
            "reply": detail + "这次不会修改实验配置。",
            "operations": [],
            "needsConfirmation": False,
        }

    count_match = re.search(r"(?:筛选|过滤|保留|top\s*)[^0-9]{0,18}(\d+)", message, re.I)
    if count_match:
        if not node:
            return {
                "intent": "clarify",
                "reply": "请先点击要修改的工作流节点，我需要知道筛选参数属于哪一步。",
                "operations": [],
                "needsConfirmation": False,
            }
        parameter = _param(node, "filter", "count", "top", "筛选", "数量", "保留")
        if not parameter:
            return {
                "intent": "clarify",
                "reply": f"“{node.get('name', '当前节点')}”没有登记筛选数量参数，无法安全修改。",
                "operations": [],
                "needsConfirmation": False,
            }
        key = str(parameter.get("key"))
        old = node.get("values", {}).get(key, node.get("config", {}).get(key, parameter.get("default", "")))
        new = int(count_match.group(1))
        return {
            "intent": "change",
            "reply": f"已将{parameter.get('label', key)}从 {old} 改为 {new}，流程图和参数表会同步更新。",
            "operations": [{
                "type": "update_params",
                "node_id": node.get("id"),
                "changes": {key: new},
                "old_values": {key: old},
            }],
            "needsConfirmation": False,
        }

    if any(term in lowered for term in ("重新筛选", "重新生成", "再生成", "regenerate", "this input", "这次生成")):
        artifact_id = context.get("inputArtifactId") or context.get("artifactId")
        if not artifact_id:
            return {
                "intent": "clarify",
                "reply": "当前输入还没有可引用的已登记产物；请先选择一个可复用产物，或直接创建新实验。",
                "operations": [],
                "needsConfirmation": False,
            }
        return {
            "intent": "change",
            "reply": f"已生成引用产物 {artifact_id} 的新实验草稿，原实验和产物不会被覆盖。请先检查创建前摘要。",
            "operations": [{
                "type": "create_experiment_draft",
                "source_artifact_id": artifact_id,
                "input_artifact_id": artifact_id,
                "intent": "fresh",
            }],
            "needsConfirmation": False,
        }

    if any(term in lowered for term in ("为什么", "失败", "报错", "fail", "reason")):
        status = str(context.get("status", ""))
        logs = context.get("logs") or context.get("log") or []
        if status == "failed" and logs:
            reason = str(logs[-1])
            return {
                "intent": "answer",
                "reply": f"当前状态为失败。最近一条运行日志是：{reason}",
                "operations": [],
                "needsConfirmation": False,
            }
        return {
            "intent": "answer",
            "reply": "当前上下文没有提供足够的失败状态或运行日志，暂时无法判断原因。请打开对应实验结果并提供运行日志。",
            "operations": [],
            "needsConfirmation": False,
        }

    return {
        "intent": "clarify",
        "reply": "我可以解释当前节点参数、修改筛选数量，或根据已登记产物生成新实验草稿。请说明目标。",
        "operations": [],
        "needsConfirmation": False,
    }
