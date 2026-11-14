"""Editable declaration drafts, server-held proposals, confirmation and checked export."""

import copy
import json

from pydantic import Field, model_validator
from typing import Any, Literal

from ai4s_declarations.registry import validate_declaration, strict_equal
from .models import Contract, Identifier, RevisionRequest
from .service import fingerprint, uid, now
from .storage import Problem


class DeclarationCreate(Contract):
    template: Literal["complete", "empty"] = "empty"
    task_id: Identifier = "proteinmpnn"
    version: str = Field(default="1", pattern=r"^[1-9][0-9]{0,7}$")


class DeclarationPreview(RevisionRequest):
    declaration: dict[str, Any]


class DeclarationConfirm(RevisionRequest):
    proposal_id: Identifier


class DeclarationChat(RevisionRequest):
    message: str = Field(min_length=1, max_length=8000)
    source_text: str = Field(default="", max_length=30000)


class DefinitionEdit(Contract):
    action: Literal["restore", "set", "remove"]
    path: str = Field(min_length=1, max_length=200)
    value: Any = None
    quote: str | None = None


class DefinitionDecision(Contract):
    intent: Literal["answer", "clarify", "change"]
    reply: str
    edits: list[DefinitionEdit] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def consistent(self):
        if (self.intent == "change") != bool(self.edits):
            raise ValueError("只有明确修改可含非空 edits")
        return self


def differences(before, after, path=""):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            child = (path + "." if path else "") + key
            if key not in before:
                result.append(
                    {"path": child, "old": None, "new": after[key], "action": "add"}
                )
            elif key not in after:
                result.append(
                    {"path": child, "old": before[key], "new": None, "action": "remove"}
                )
            else:
                result.extend(differences(before[key], after[key], child))
        return result
    return (
        []
        if strict_equal(before, after)
        else [{"path": path, "old": before, "new": after, "action": "replace"}]
    )


class DeclarationService:
    def __init__(self, store, registry):
        self.store, self.registry = store, registry

    def list(self, *, deleted=False):
        with self.store.lock:
            return [
                {
                    "id": value["id"],
                    "revision": value["revision"],
                    "name": value["declaration"].get("name", "未命名声明"),
                    "task_id": value["declaration"].get("task_id"),
                    "version": value["declaration"].get("version"),
                    "status": self.lifecycle(value),
                    "issue_count": len(self.issues(value["declaration"])),
                }
                for path in sorted(
                    (self.store.root / "declaration_drafts").glob("*.json"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if bool((value := self.store.read("declaration_drafts", path.stem, include_deleted=True)).get("deleted")) == deleted
            ]

    def create(self, request):
        try:
            declaration = self.registry.get(request.task_id, request.version)
        except KeyError:
            raise Problem(
                422, "该任务版本尚无受支持的声明，不能建立可校验声明"
            ) from None
        if request.template == "empty":
            declaration["inputs"] = {}
            declaration["parameters"] = {group: {} for group in declaration["parameters"]}
            declaration["outputs"] = {}
        value = {
            "id": uid("decl"),
            "revision": 0,
            "declaration": declaration,
            "reference": {"task_id": request.task_id, "version": request.version},
            "messages": [],
            "proposals": {},
            "operations": {},
            "events": [],
        }
        with self.store.lock:
            self.store.write("declaration_drafts", value["id"], value)
        return self.view(value)

    def read(self, draft_id):
        return self.store.read("declaration_drafts", draft_id)

    def get(self, draft_id):
        with self.store.lock:
            return self.view(self.read(draft_id))

    def revision(self, value, expected):
        if value["revision"] != expected:
            raise Problem(
                409,
                "声明已被修改，请读取最新版本后重新提出修改",
                details={"revision": value["revision"]},
            )

    def issues(self, document):
        return validate_declaration(document)

    def reference(self, value):
        # Old drafts predate this metadata and use the original verified version.
        key = value.get(
            "reference", {"task_id": value["declaration"]["task_id"], "version": "1"}
        )
        return self.registry.get(key["task_id"], key["version"])

    def lifecycle(self, value):
        exported = value.get("last_export", {})
        if (
            exported.get("revision") == value["revision"]
            and exported.get("sha256") == fingerprint(value["declaration"])
        ):
            return "exported_not_deployed"
        return "draft"

    def view(self, value):
        return {
            key: copy.deepcopy(value[key])
            for key in ("id", "revision", "declaration", "messages", "events")
        } | {
            "issues": self.issues(value["declaration"]),
            "reference": copy.deepcopy(value.get(
                "reference", {"task_id": value["declaration"]["task_id"], "version": "1"}
            )),
            "status": self.lifecycle(value),
        }

    def candidate(self, document, edits, source_text="", *, reference=None):
        result = copy.deepcopy(document)
        canonical = reference or self.registry.get(document["task_id"], "1")
        for edit in edits:
            tokens = edit.path.split(".")
            if any(
                not token or token in ("__proto__", "constructor", "prototype")
                for token in tokens
            ):
                raise Problem(422, "无效字段路径")
            if tokens[0] not in canonical:
                raise Problem(422, "未知声明字段")
            # Normalize using the trusted port catalog even when the draft is empty.
            # A dotted output port is one JSON key, not nested objects.
            if tokens[0] == "outputs" and len(tokens) > 1:
                suffix = edit.path[len("outputs.") :]
                for port in sorted(canonical["outputs"], key=len, reverse=True):
                    if suffix == port or suffix.startswith(port + "."):
                        tail = suffix[len(port) :].lstrip(".")
                        tokens = ["outputs", port] + (tail.split(".") if tail else [])
                        break

            def resolve(parent, parts, create=False):
                for key in parts[:-1]:
                    if key not in parent:
                        if not create:
                            raise Problem(422, "依据中不存在该字段：" + edit.path)
                        parent[key] = {}
                    if not isinstance(parent[key], dict):
                        raise Problem(422, "字段路径不能穿过非对象值")
                    parent = parent[key]
                return parent, parts[-1]

            if edit.action == "restore":
                parent, key = resolve(canonical, tokens[:])
                if key not in parent:
                    raise Problem(422, "真实定义中没有该字段")
                val = copy.deepcopy(parent[key])
            else:
                val = copy.deepcopy(edit.value)
                if (
                    source_text
                    and edit.action == "set"
                    and (not edit.quote or edit.quote not in source_text)
                ):
                    raise Problem(422, "资料修改缺少可逐字核对的原文依据")
            parent, key = resolve(result, tokens[:], create=True)
            if edit.action == "remove":
                parent.pop(key, None)
            else:
                if edit.action == "restore" and key in parent:
                    # Restoring missing definitions must not erase prior user labels or values.
                    def fill_missing(target, trusted):
                        if isinstance(target, dict) and isinstance(trusted, dict):
                            for child, trusted_value in trusted.items():
                                if child not in target:
                                    target[child] = copy.deepcopy(trusted_value)
                                else:
                                    fill_missing(target[child], trusted_value)

                    fill_missing(parent[key], val)
                else:
                    parent[key] = val
        invalid = [i for i in self.issues(result) if i["code"] != "missing"]
        if invalid:
            raise Problem(422, "提案与真实接口不符，整批没有写入", details=invalid)
        return result

    def propose(self, value, candidate, origin, evidence=None):
        try:
            size = len(json.dumps(candidate, ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError):
            raise Problem(422, "声明必须为标准 JSON，不能包含非有限数") from None
        if size > 100000:
            raise Problem(413, "声明过大")
        invalid = [i for i in self.issues(candidate) if i["code"] != "missing"]
        if invalid:
            raise Problem(422, "声明存在非法值，整批没有写入", details=invalid)
        diff = differences(value["declaration"], candidate)
        if not diff:
            raise Problem(422, "配置没有变化")
        proposal = {
            "id": uid("proposal"),
            "expected_revision": value["revision"],
            "candidate": copy.deepcopy(candidate),
            "diff": diff,
            "origin": origin,
            "evidence": evidence
            or {
                "source_revision": self.reference(value)["source_reference"]["revision"],
                "kind": "verified_definition",
            },
            "status": "pending",
            "time": now(),
        }
        value["proposals"][proposal["id"]] = proposal
        return {
            k: copy.deepcopy(proposal[k])
            for k in ("id", "expected_revision", "diff", "status", "origin", "evidence")
        }

    def preview(self, draft_id, request):
        with self.store.lock:
            value = self.read(draft_id)
            digest = fingerprint(request.model_dump(exclude={"operation_id"}))
            cached = value.setdefault("preview_operations", {}).get(
                request.operation_id
            )
            if cached:
                if cached["digest"] != digest:
                    raise Problem(409, "预览编号不能用于不同内容")
                proposal = value["proposals"][cached["proposal_id"]]
                public = {
                    k: copy.deepcopy(proposal[k])
                    for k in (
                        "id",
                        "expected_revision",
                        "diff",
                        "status",
                        "origin",
                        "evidence",
                    )
                }
                return {"proposal": public, "state": self.view(value)}
            self.revision(value, request.expected_revision)
            proposal = self.propose(value, request.declaration, "用户表单")
            value["preview_operations"][request.operation_id] = {
                "digest": digest,
                "proposal_id": proposal["id"],
            }
            self.store.write("declaration_drafts", draft_id, value)
            return {"proposal": proposal, "state": self.view(value)}

    def confirm(self, draft_id, request, *, cancel=False):
        with self.store.lock:
            value = self.read(draft_id)
            digest = fingerprint(
                {"cancel": cancel, **request.model_dump(exclude={"operation_id"})}
            )
            previous = value["operations"].get(request.operation_id)
            if previous:
                if previous["digest"] != digest:
                    raise Problem(409, "同一操作编号不能用于不同内容")
                return self.view(value)
            self.revision(value, request.expected_revision)
            proposal = value["proposals"].get(request.proposal_id)
            if not proposal or proposal["status"] != "pending":
                raise Problem(409, "提案不存在、已取消或已使用")
            if proposal["expected_revision"] != value["revision"]:
                raise Problem(409, "提案已过期，请重新核对")
            if cancel:
                proposal["status"] = "cancelled"
            else:
                invalid = [
                    i
                    for i in self.issues(proposal["candidate"])
                    if i["code"] != "missing"
                ]
                if invalid:
                    raise Problem(422, "提案不合法", details=invalid)
                value["declaration"] = proposal["candidate"]
                value["revision"] += 1
                proposal["status"] = "applied"
            value["events"].append(
                {
                    "time": now(),
                    "proposal_id": proposal["id"],
                    "status": proposal["status"],
                    "revision": value["revision"],
                    "diff": proposal["diff"],
                }
            )
            value["operations"][request.operation_id] = {"digest": digest}
            for message in value["messages"]:
                if message.get("proposal", {}).get("id") == proposal["id"]:
                    message["proposal"]["status"] = proposal["status"]
            self.store.write("declaration_drafts", draft_id, value)
            return self.view(value)

    def export(self, draft_id, expected):
        with self.store.lock:
            value = self.read(draft_id)
            self.revision(value, expected)
            document = value["declaration"]
            issues = self.issues(document)
            if issues:
                raise Problem(422, "声明不完整或不合法，不能导出", details=issues)
            try:
                published = self.registry.get(document["task_id"], document["version"])
            except KeyError:
                published = None
            if published and not strict_equal(published, document):
                raise Problem(409, "同一发布版本内容不可改写，请使用新的接口版本后导出")
            value["last_export"] = {
                "revision": value["revision"],
                "sha256": fingerprint(document),
                "time": now(),
            }
            self.store.write("declaration_drafts", draft_id, value)
            return {
                "declaration": copy.deepcopy(document),
                "sha256": fingerprint(document),
                "deployment_path": f"configs/task_declarations/{document['task_id']}/{document['version']}.json",
                "status": "exported_not_deployed",
                "revision": value["revision"],
            }
