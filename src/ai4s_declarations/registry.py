"""Contract ① checks and atomic startup loading; never imports AiiDA or runs commands."""

import copy
import json
import math
from pathlib import Path
import re

SCHEMA = "ai4s-task-declaration-1"
RELEASE = "8907e667-py312-torch260cu124"
SOURCE_REVISION = "8b9569f627957cfde6879cddd01e802d4619e778"
PARAMETERS = {
    "inference": {
        "chains": {"type": "string", "required": True, "minLength": 1},
        "num_sequences": {"type": "integer", "required": True, "minimum": 1},
        "sampling_temperature": {
            "type": "number",
            "required": True,
            "exclusiveMinimum": 0,
        },
        "seed": {
            "type": "integer",
            "required": True,
            "minimum": 1,
            "maximum": 4294967295,
        },
        "model_name": {
            "type": "string",
            "required": False,
            "default": "v_48_020",
            "enum": ["v_48_002", "v_48_010", "v_48_020", "v_48_030"],
        },
        "batch_size": {
            "type": "integer",
            "required": False,
            "default": 1,
            "minimum": 1,
        },
        "save_probabilities": {"type": "boolean", "required": False, "default": True},
    },
    "filter": {
        "score_threshold": {"type": "number", "required": True},
        "top_k": {"type": "integer", "required": True, "minimum": 1},
    },
}
PORTS = {
    "result": ("inference", "Dict", "manifest", None, None),
    "artifacts.sequences": (
        "inference",
        "SinglefileData",
        "primary",
        "FASTA",
        "design.fa",
    ),
    "artifacts.scores": (
        "inference",
        "SinglefileData",
        "auxiliary",
        "NPZ",
        "scores.npz",
    ),
    "artifacts.probabilities": (
        "inference",
        "SinglefileData",
        "auxiliary",
        "NPZ",
        "probabilities.npz",
    ),
    "retrieved": ("inference", "FolderData", "diagnostic", None, None),
    "selected_sequences": ("filter", "Dict", "primary", None, None),
    "sample_table": ("filter", "Dict", "auxiliary", None, None),
    "selection_report": ("filter", "Dict", "report", None, None),
}
EXECUTION = {
    "calculation_entry_point": "ai4s.proteinmpnn",
    "workflow_entry_point": "ai4s.protein-mpnn-filter",
    "inference_parameter_port": {"single": "params", "mpnn_filter": "mpnn_params"},
    "filter_parameter_port": "filter_params",
    "code_binding": "engine_configured",
}
CONSTRAINT = {
    "rule": "num_sequences_multiple_of_batch_size",
    "scope": "inference",
    "message": "num_sequences 必须为 batch_size 的整数倍。",
}


class DeclarationError(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__("；".join(i["path"] + ": " + i["message"] for i in issues))


def strict_equal(a, b):
    """JSON equality without treating true, 1 and 1.0 as interchangeable."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(
            strict_equal(value, b[key]) for key, value in a.items()
        )
    if isinstance(a, list):
        return len(a) == len(b) and all(strict_equal(x, y) for x, y in zip(a, b))
    return a == b


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("重复 JSON 字段：" + key)
        result[key] = value
    return result


def validate_values(values, group, *, partial=False):
    issues = []

    def error(path, message):
        issues.append({"path": path, "message": message, "code": "invalid"})

    if not isinstance(values, dict):
        return [{"path": "params." + group, "message": "必须为对象", "code": "invalid"}]
    rules = PARAMETERS[group]
    for key in values.keys() - rules.keys():
        error(f"params.{group}.{key}", "不支持的参数")
    effective = {k: r["default"] for k, r in rules.items() if "default" in r}
    effective.update(values)
    for key, rule in rules.items():
        path = f"params.{group}.{key}"
        if key not in effective:
            if not partial:
                error(path, "必填参数未提供")
            continue
        value = effective[key]
        kind = rule["type"]
        valid = (
            type(value) is int
            if kind == "integer"
            else type(value) in (int, float) and math.isfinite(value)
            if kind == "number"
            else type(value) is bool
            if kind == "boolean"
            else isinstance(value, str) and bool(value.strip())
        )
        if not valid:
            error(path, "类型错误或值为空／非有限数")
            continue
        if "enum" in rule and value not in rule["enum"]:
            error(path, "不支持的取值")
        for bound, test in [
            ("minimum", lambda x, y: x < y),
            ("maximum", lambda x, y: x > y),
            ("exclusiveMinimum", lambda x, y: x <= y),
        ]:
            if bound in rule and test(value, rule[bound]):
                error(path, f"不满足 {bound}={rule[bound]}")
    n, b = effective.get("num_sequences"), effective.get("batch_size")
    if group == "inference" and type(n) is int and type(b) is int and b > 0 and n % b:
        error("params.inference.num_sequences", "必须为 batch_size 的整数倍")
    return issues


def validate_declaration(document):
    """Return all field issues. Missing fields can be retained in an editing draft."""
    issues = []

    def issue(path, message, code="invalid"):
        issues.append({"path": path, "message": message, "code": code})

    def object_fields(value, path, allowed, required):
        if not isinstance(value, dict):
            issue(path, "必须为对象")
            return False
        for key in sorted(value.keys() - set(allowed)):
            issue(path + "." + key, "未知字段")
        for key in sorted(set(required) - value.keys()):
            issue((path + "." if path else "") + key, "缺少必填定义", "missing")
        return True

    def exact(container, key, expected, path):
        if key not in container:
            issue(path, "缺少必填定义", "missing")
        elif not strict_equal(container[key], expected):
            issue(path, "与已核实的真实任务接口不一致")

    def text(value, path):
        if not isinstance(value, str) or not value.strip() or len(value) > 4000:
            issue(path, "须为非空文字（不超过4000字）")

    fields = {
        "schema_version",
        "task_id",
        "version",
        "name",
        "model",
        "workflow_modes",
        "inputs",
        "parameters",
        "constraints",
        "execution",
        "outputs",
        "example",
        "source_reference",
    }
    if not object_fields(document, "", fields, fields - {"example"}):
        return issues
    exact(document, "schema_version", SCHEMA, "schema_version")
    exact(document, "task_id", "proteinmpnn", "task_id")
    if "version" in document and (
        not isinstance(document["version"], str)
        or not re.fullmatch(r"[1-9][0-9]{0,7}", document["version"])
    ):
        issue("version", "接口版本必须为正整数字符串")
    if "name" in document:
        text(document["name"], "name")
    exact(
        document,
        "model",
        {"model_id": "proteinmpnn", "release": RELEASE, "weights_family": "vanilla"},
        "model",
    )
    exact(document, "workflow_modes", ["single", "mpnn_filter"], "workflow_modes")
    exact(document, "execution", EXECUTION, "execution")
    exact(document, "constraints", [CONSTRAINT], "constraints")
    inputs = document.get("inputs", {})
    if (
        object_fields(inputs, "inputs", {"pdb_file"}, {"pdb_file"})
        and "pdb_file" in inputs
    ):
        info = inputs["pdb_file"]
        if object_fields(
            info,
            "inputs.pdb_file",
            {"label", "aiida_type", "format", "required"},
            {"label", "aiida_type", "format", "required"},
        ):
            for key, value in {
                "aiida_type": "SinglefileData",
                "format": "PDB",
                "required": True,
            }.items():
                exact(info, key, value, "inputs.pdb_file." + key)
            if "label" in info:
                text(info["label"], "inputs.pdb_file.label")
    parameters = document.get("parameters", {})
    if object_fields(parameters, "parameters", PARAMETERS, PARAMETERS):
        for group, rules in PARAMETERS.items():
            values = parameters.get(group, {})
            if not object_fields(values, "parameters." + group, rules, rules):
                continue
            for key, rule in rules.items():
                if key not in values:
                    continue
                info = values[key]
                path = f"parameters.{group}.{key}"
                required = set(rule) | {"label", "description", "category"}
                if not object_fields(info, path, required, required):
                    continue
                for name, value in {**rule, "category": group}.items():
                    exact(info, name, value, path + "." + name)
                for name in ("label", "description"):
                    if name in info:
                        text(info[name], path + "." + name)
    outputs = document.get("outputs", {})
    if object_fields(outputs, "outputs", PORTS, PORTS):
        for port, (owner, kind, role, format_, filename) in PORTS.items():
            if port not in outputs:
                continue
            expected = {
                "owner": owner,
                "aiida_type": kind,
                "role": role,
                "required": port not in ("retrieved", "artifacts.probabilities"),
            }
            if format_:
                expected.update(format=format_, filename=filename)
            if port == "result":
                expected["schema_version"] = "ai4s-artifacts-1"
            if port == "artifacts.probabilities":
                expected["required_if"] = {
                    "path": "params.inference.save_probabilities",
                    "equals": True,
                }
            info = outputs[port]
            path = "outputs." + port
            if object_fields(
                info,
                path,
                set(expected) | {"description"},
                set(expected) | {"description"},
            ):
                for key, value in expected.items():
                    exact(info, key, value, path + "." + key)
                if "description" in info:
                    text(info["description"], path + ".description")
    reference = document.get("source_reference", {})
    if object_fields(
        reference,
        "source_reference",
        {"repository", "revision", "paths"},
        {"repository", "revision", "paths"},
    ):
        exact(
            reference,
            "repository",
            "QUHONGYE-gif/ai4s-workspace",
            "source_reference.repository",
        )
        exact(reference, "revision", SOURCE_REVISION, "source_reference.revision")
        required_paths = {
            "docs/aiida_tasks.md",
            "src/ai4s_tasks/proteinmpnn.py",
            "src/ai4s_tasks/proteinmpnn_outputs.py",
            "src/ai4s_workflows/workflows.py",
            "src/ai4s_workflows/filtering.py",
            "src/ai4s_tasks/submit.py",
            "pyproject.toml",
        }
        if "paths" in reference and (
            not isinstance(reference["paths"], list)
            or any(not isinstance(p, str) for p in reference["paths"])
            or set(reference["paths"]) != required_paths
            or len(reference["paths"]) != len(required_paths)
        ):
            issue("source_reference.paths", "依据文件不完整或不受支持")
    if "example" in document:
        example = document["example"]
        if object_fields(
            example,
            "example",
            {"input_description", "workflow", "params"},
            {"input_description", "workflow", "params"},
        ):
            if "input_description" in example:
                text(example["input_description"], "example.input_description")
            mode = example.get("workflow")
            if mode not in ("single", "mpnn_filter"):
                issue("example.workflow", "不支持的流程")
            params = example.get("params", {})
            groups = {"inference", "filter"} if mode == "mpnn_filter" else {"inference"}
            if object_fields(params, "example.params", groups, groups):
                for group in groups:
                    if group in params:
                        for error in validate_values(params[group], group):
                            issues.append({**error, "path": "example." + error["path"]})
    return issues


class DeclarationRegistry:
    """Trusted file registry. Build fully before publishing; fail closed on invalid files."""

    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self._items = {}
        for path in sorted(self.directory.rglob("*.json")):
            if len(path.relative_to(self.directory).parts) != 2:
                raise DeclarationError(
                    [
                        {
                            "path": str(path),
                            "message": "声明必须位于 task_id/version.json",
                            "code": "invalid",
                        }
                    ]
                )
            if path.is_symlink() or self.directory not in path.resolve().parents:
                raise DeclarationError(
                    [{"path": str(path), "message": "声明路径越界", "code": "invalid"}]
                )
            try:
                document = json.loads(
                    path.read_text(encoding="utf-8"), object_pairs_hook=unique_object
                )
            except (ValueError, OSError) as exc:
                raise DeclarationError(
                    [
                        {
                            "path": str(path),
                            "message": "无法读取合法 JSON",
                            "code": "invalid",
                        }
                    ]
                ) from exc
            issues = validate_declaration(document)
            if issues:
                raise DeclarationError(issues)
            key = (document["task_id"], document["version"])
            if path.parent.name != key[0] or path.stem != key[1]:
                raise DeclarationError(
                    [
                        {
                            "path": str(path),
                            "message": "路径与任务标识／版本不一致",
                            "code": "invalid",
                        }
                    ]
                )
            if key in self._items:
                raise DeclarationError(
                    [{"path": str(path), "message": "重复声明标识", "code": "invalid"}]
                )
            self._items[key] = document
        if ("proteinmpnn", "1") not in self._items:
            raise DeclarationError(
                [
                    {
                        "path": "registry",
                        "message": "缺少 proteinmpnn/1.json",
                        "code": "missing",
                    }
                ]
            )

    def get(self, task_id="proteinmpnn", version="1"):
        try:
            return copy.deepcopy(self._items[(task_id, version)])
        except KeyError:
            raise KeyError("invalid_declaration") from None

    def list(self):
        return [
            {"task_id": k[0], "version": k[1], "name": v["name"]}
            for k, v in self._items.items()
        ]
