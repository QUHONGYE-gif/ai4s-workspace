"""Workspace policy edits and confirmation for the existing DeepSeek Agent."""

import json
from typing import Literal
from uuid import uuid4

from pydantic import Field
from pydantic_ai import Agent, ToolOutput

from ai4s_engine.policy import read_policy, workspace_actor
from .models import ChangeAudit, Contract
from .service import now
from .storage import Problem


class Policy(Contract):
    reuse_policy: Literal["allow_reuse", "force_rerun", "new_sample"]
    transfer_limit_seconds: float | None = Field(ge=0, strict=True)
    storage_limit_bytes: int | None = Field(gt=0, le=2**53 - 1, strict=True)
    retention: Literal["lru", "cost"]

    @classmethod
    def from_changes(cls, current, changes):
        try:
            return cls.model_validate(current | changes).model_dump()
        except ValueError:
            raise Problem(422, "策略字段、取值或单位无效") from None


class PolicyRevision(Contract):
    expected_revision: int = Field(ge=0, strict=True)


class PolicyPreview(PolicyRevision):
    config: Policy


class PolicyConfirm(PolicyRevision):
    proposal_id: str = Field(min_length=1, max_length=80)


class PolicyChat(PolicyRevision):
    message: str = Field(min_length=1, max_length=2000)


class PolicyReply(Contract):
    intent: Literal["answer", "clarify", "change"]
    reply: str
    changes: dict = Field(default_factory=dict)


class PolicyService:
    def __init__(self, store):
        self.store = store
        self.proposals = {}
        self.actor = workspace_actor()

    def read(self):
        return {**read_policy(self.store.root), "actor": self.actor}

    def check(self, revision):
        state = self.read()
        if state["revision"] != revision:
            raise Problem(409, "策略已更新，请读取最新版本后重新核对")
        return state

    def preview(self, revision, changes, source):
        with self.store.lock:
            state = self.check(revision)
            candidate = Policy.from_changes(state["config"], changes)
            diff = [
                {"field": key, "before": value, "after": candidate[key]}
                for key, value in state["config"].items() if candidate[key] != value
            ]
            if not diff:
                return None
            proposal_id = str(uuid4())
            proposal = {"id": proposal_id, "revision": revision, "diff": diff, "source": source}
            if len(self.proposals) >= 64:
                self.proposals.pop(next(iter(self.proposals)))
            self.proposals[proposal_id] = (proposal, candidate)
            return proposal

    def commit(self, state, config, source, proposal_id=None):
        revision = state["revision"] + 1
        event = {
            "revision": revision,
            "actor": self.actor,
            "time": now(),
            "source": source,
            "before": state["config"],
            "after": config,
            "proposal_id": proposal_id,
        }
        value = {"config": config, "revision": revision, "history": [*state["history"], event]}
        self.store.write("policies", "workspace", value)
        self.proposals.clear()
        return {**value, "actor": self.actor}

    def confirm(self, request):
        with self.store.lock:
            current = self.read()
            if any(event["proposal_id"] == request.proposal_id for event in current["history"]):
                return current
            state = self.check(request.expected_revision)
            saved = self.proposals.get(request.proposal_id)
            if not saved or saved[0]["revision"] != state["revision"]:
                raise Problem(409, "提案已失效，请重新预览")
            proposal, candidate = saved
            return self.commit(state, candidate, proposal["source"], request.proposal_id)

    def undo_preview(self, revision):
        with self.store.lock:
            state = self.check(revision)
            if not state["history"]:
                raise Problem(422, "没有可撤回的修改")
            return self.preview(revision, state["history"][-1]["before"], "undo")

    async def chat(self, gateway, request):
        state = self.check(request.expected_revision)
        prompt = json.dumps({
            "message": request.message,
            "current": state["config"],
            "constraints": Policy.model_json_schema(),
        }, ensure_ascii=False)
        agent = Agent(
            gateway._model(), output_type=ToolOutput(PolicyReply, strict=False),
            model_settings=gateway._settings(), retries=1,
            instructions="""你协助管理 AI4S 工作区的默认策略。只提出待确认修改，不写入或运行实验。
普通询问、假设、否定用 answer，changes 空对象。缺字段、数值或单位时先澄清。
明确修改用 change，changes 只包含用户指定的字段，不能省掉任何要求。
reuse_policy 接受 allow_reuse（允许复用）、force_rerun（强制重算）、new_sample（新采样）。
强制重算跳过候选复用，使用原参数和种子，已有结果继续保留。新采样跳过候选复用并换种子。
不要把跳过复用描述为丢弃、删除或替换旧结果。也不要承诺两次结果一定相同，或新样本统计独立。
transfer_limit_seconds 为搬运耗时上限（秒）；storage_limit_bytes 为占用上限（字节）。
GB 按 10^9 字节，GiB 按 2^30 字节。用户明确取消上限时保存 null。
retention 接受 lru（最久未用先淘汰）或 cost（项目策略）。
预算、阈值和保留策略当前用于模拟自测。逐项核对请求，未知字段或混合非法要求一起澄清。""",
        )
        answer, usage = await gateway._run(agent, prompt, requests=2)
        proposal = None
        if answer.intent == "change":
            reviewer = Agent(
                gateway._model(), output_type=ToolOutput(ChangeAudit, strict=False),
                model_settings=gateway._settings(), retries=1,
                instructions="""只检查提案。明确要求改变持久策略时 explicit_request 才为 true。
逐项核对范围、单位和数值。一项遗漏、多改、猜测、错值或用户只在提问时不通过。""",
            )
            audit, review_usage = await gateway._run(
                reviewer, json.dumps({"context": json.loads(prompt), "changes": answer.changes}, ensure_ascii=False),
                requests=2,
            )
            for key in ("requests", "input_tokens", "output_tokens", "elapsed_seconds"):
                usage[key] += review_usage[key]
            if not (audit.explicit_request and audit.complete_and_consistent):
                return {"reply": audit.reason, "proposal": None, "usage": usage}
            proposal = self.preview(request.expected_revision, answer.changes, "agent")
            reply = "请核对以下改动，确认后保存。" if proposal else "当前策略已经符合这项要求。"
            return {"reply": reply, "proposal": proposal, "usage": usage}
        return {"reply": answer.reply, "proposal": None, "usage": usage}
