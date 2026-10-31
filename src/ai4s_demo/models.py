"""Public contracts. Unknown fields are rejected rather than silently ignored."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")]
ModelId = Literal["rfdiffusion", "proteinmpnn", "boltz"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class InputRef(Contract):
    kind: Literal["file", "node_output", "sequence"]
    file_id: Identifier | None = None
    node_id: Identifier | None = None
    port: str | None = None
    sequence: str | None = None
    record_id: str | None = None

    @model_validator(mode="after")
    def fields_match_kind(self):
        values = self.model_dump(exclude_none=True)
        allowed = {
            "file": {"kind", "file_id", "record_id"},
            "node_output": {"kind", "node_id", "port", "record_id"},
            "sequence": {"kind", "sequence"},
        }
        required = {"file": {"file_id"}, "node_output": {"node_id", "port"}, "sequence": {"sequence"}}
        if set(values) - allowed[self.kind] or not required[self.kind] <= set(values):
            raise ValueError("输入引用的字段与 kind 不匹配")
        return self


class ChainPolicy(Contract):
    mode: Literal["all", "selected"]
    chains: list[str] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def selected_chains(self):
        if self.mode == "selected" and (not self.chains or any(len(c) != 1 for c in self.chains)):
            raise ValueError("选择设计链时需要实际的单字符链标识")
        if self.mode == "all" and self.chains:
            raise ValueError("设计全部链时不要同时指定部分链")
        return self


class UpdateParams(Contract):
    type: Literal["update_params"]
    node_id: Identifier
    changes: dict[str, Any]


class SetInput(Contract):
    type: Literal["set_input"]
    node_id: Identifier
    port: str
    value: InputRef | None


class SetChains(Contract):
    type: Literal["set_chains"]
    node_id: Identifier
    policy: ChainPolicy


class AddNode(Contract):
    type: Literal["add_node"]
    node_id: Identifier
    model_id: ModelId
    label: str = Field(min_length=1, max_length=80)


class RemoveNode(Contract):
    type: Literal["remove_node"]
    node_id: Identifier


class Connect(Contract):
    type: Literal["connect"]
    source: Identifier
    source_port: str
    target: Identifier
    target_port: str
    record_id: str | None = None


class Disconnect(Contract):
    type: Literal["disconnect"]
    target: Identifier
    target_port: str


class MoveNode(Contract):
    type: Literal["move_node"]
    node_id: Identifier
    x: float = Field(ge=-100000, le=100000)
    y: float = Field(ge=-100000, le=100000)


class SetLayout(Contract):
    type: Literal["set_layout"]
    layout: Literal["layered", "circle"]


class AddRelation(Contract):
    """Design relation only; never binds an executable model input."""
    type: Literal["add_relation"]
    relation_id: Identifier
    source: Identifier
    source_port: str
    target: Identifier
    kind: Literal["feedback", "reference"]
    label: str = Field(min_length=1, max_length=80)


class RemoveRelation(Contract):
    type: Literal["remove_relation"]
    relation_id: Identifier


class Rename(Contract):
    type: Literal["rename"]
    name: str = Field(min_length=1, max_length=80)
    node_id: Identifier | None = None


class ApplyImport(Contract):
    type: Literal["apply_import"]
    node_id: Identifier
    preview_id: Identifier


Operation = Annotated[
    UpdateParams | SetInput | SetChains | AddNode | RemoveNode | Connect | Disconnect | Rename | ApplyImport
    | MoveNode | SetLayout | AddRelation | RemoveRelation,
    Field(discriminator="type"),
]


class ChangeRequest(Contract):
    expected_revision: int = Field(ge=0)
    operation_id: Identifier
    operations: list[Operation] = Field(min_length=1, max_length=20)
    confirmed: bool = False


class CreateWorkflow(Contract):
    name: str = Field(default="蛋白质设计示例", min_length=1, max_length=80)
    template: Literal["protein", "empty"] = "protein"


class RevisionRequest(Contract):
    expected_revision: int = Field(ge=0)
    operation_id: Identifier


class RegisterRequest(RevisionRequest):
    node_ids: list[Identifier] | None = None


class GenerateRequest(Contract):
    registration_id: Identifier


class ChatRequest(RevisionRequest):
    message: str = Field(min_length=1, max_length=8000)
    selected_node_id: Identifier | None = None


class ImportRequest(Contract):
    model_id: ModelId
    content: str = Field(min_length=1, max_length=40000)
    source: str = Field(default="用户资料（版本待核实）", max_length=2000)


class AgentDecision(Contract):
    intent: Literal["answer", "clarify", "change"]
    reply: str
    operations: list[Operation] = Field(default_factory=list)
    needs_confirmation: bool = False
    focus_node_id: Identifier | None = None

    @model_validator(mode="after")
    def intent_matches(self):
        if (self.intent == "change") != bool(self.operations):
            raise ValueError("只有明确 change 意图可包含非空修改列表")
        return self


class ExtractedParameter(Contract):
    field: str
    value: Any
    category: Literal["official_default", "example", "user", "unknown"]
    quote: str


class ImportDecision(Contract):
    parameters: list[ExtractedParameter]
    notes: str


class ChangeAudit(Contract):
    explicit_request: bool
    complete_and_consistent: bool
    reason: str
