"""流程定义 + 执行器：读取 FASTA → 规范化序列 → 输出长度统计。

设计取舍：
1. 缓存键 = sha256(步骤名, 步骤版本, 参数, 每个输入端口的产物内容哈希)
   —— 不依赖时间戳/文件名，所以"用户把同一份文件改个名再提交"也能命中。
2. 依赖关系在运行时由 step_io 记录，不按工具名硬拼
   —— 符合《AI4S概述》里"依赖关系应根据真实代码确定"的要求。
3. 命中缓存也写一条 step 记录（status=reused），否则统计不出复用收益。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from db import MetaDB, dumps
from store import ObjectStore

# 允许的氨基酸字母（标准 20 种 + B/Z/X/J/U/O 等模糊/特殊残基）
AA_ALPHABET = "ACDEFGHIKLMNPQRSTVWYBXZJUO"


# --------------------------------------------------------------------------
# 三个任务（真实项目里这里会是 RFdiffusion / ProteinMPNN / AlphaFold 的封装）
# --------------------------------------------------------------------------
def parse_fasta(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    rid: str | None = None
    desc = ""
    buf: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if rid is not None:
                records.append({"id": rid, "desc": desc, "seq": "".join(buf)})
            header = line[1:].strip()
            parts = header.split(None, 1)
            rid = parts[0] if parts else f"seq{len(records) + 1}"
            desc = parts[1] if len(parts) > 1 else ""
            buf = []
        else:
            if rid is None:
                raise ValueError("FASTA 解析失败：首个非空行不是 '>' 开头的序列头")
            buf.append(line)
    if rid is not None:
        records.append({"id": rid, "desc": desc, "seq": "".join(buf)})
    return records


def task_read_fasta(inputs: dict[str, bytes], params: dict) -> dict[str, bytes]:
    """读取 FASTA → 结构化序列集合（JSON）。"""
    text = inputs["fasta"].decode("utf-8", errors="replace")
    records = parse_fasta(text)
    if params.get("max_records"):
        records = records[: int(params["max_records"])]
    payload = {"records": records, "source_records": len(records)}
    return {"sequences": json.dumps(payload, ensure_ascii=False).encode("utf-8")}


def task_normalize(inputs: dict[str, bytes], params: dict) -> dict[str, bytes]:
    """规范化序列：大小写、去空白、去 gap、可选剔除非法字符记录。"""
    data = json.loads(inputs["sequences"])
    allowed = set(params.get("alphabet", AA_ALPHABET))
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    invalid_map: dict[str, list[str]] = {}

    for rec in data["records"]:
        seq = str(rec.get("seq", ""))
        if params.get("uppercase", True):
            seq = seq.upper()
        seq = "".join(ch for ch in seq if not ch.isspace())
        if params.get("strip_gaps", True):
            seq = seq.replace("-", "").replace(".", "")
        if params.get("strip_stops", True):
            seq = seq.replace("*", "")

        bad = sorted({ch for ch in seq if ch not in allowed})
        if bad:
            invalid_map[rec["id"]] = bad
            if params.get("drop_invalid", True):
                dropped.append(rec["id"])
                continue
        kept.append({"id": rec["id"], "desc": rec.get("desc", ""), "seq": seq, "length": len(seq)})

    payload = {
        "records": kept,
        "dropped": dropped,
        "invalid_chars": invalid_map,
        "count": len(kept),
    }
    return {"normalized": json.dumps(payload, ensure_ascii=False).encode("utf-8")}


def task_length_stats(inputs: dict[str, bytes], params: dict) -> dict[str, bytes]:
    """输出长度统计（示例里的"最终产物"）。"""
    data = json.loads(inputs["normalized"])
    digits = int(params.get("round_digits", 1))
    lengths = {r["id"]: int(r["length"]) for r in data["records"]}
    vals = sorted(lengths.values())
    n = len(vals)
    if n == 0:
        stats = {"count": 0, "total_length": 0, "min": 0, "max": 0,
                 "mean": 0.0, "median": 0.0, "lengths": {}}
    else:
        mid = n // 2
        median = vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2
        stats = {
            "count": n,
            "total_length": sum(vals),
            "min": vals[0],
            "max": vals[-1],
            "mean": round(sum(vals) / n, digits),
            "median": round(float(median), digits),
            "lengths": lengths,
        }
    stats["dropped"] = data.get("dropped", [])
    return {"stats": json.dumps(stats, ensure_ascii=False, indent=2).encode("utf-8")}


# --------------------------------------------------------------------------
# 步骤声明
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class OutSpec:
    kind: str
    policy: str = "cache"          # keep | cache | meta_only
    media_type: str = "application/json"


@dataclass(frozen=True)
class StepDef:
    name: str
    version: str
    inputs: dict[str, str]         # 输入端口 -> "@文件名" 或上游输出端口
    outputs: dict[str, OutSpec]
    params: dict[str, Any]
    fn: Callable[[dict[str, bytes], dict], dict[str, bytes]]


PIPELINE: list[StepDef] = [
    StepDef(
        name="read_fasta",
        version="0.1.0",
        inputs={"fasta": "@fasta"},
        outputs={"sequences": OutSpec("sequence_set")},
        params={"max_records": 0},
        fn=task_read_fasta,
    ),
    StepDef(
        name="normalize_sequence",
        version="0.1.2",
        inputs={"sequences": "sequences"},
        outputs={"normalized": OutSpec("sequence_set")},
        params={
            "uppercase": True,
            "strip_gaps": True,
            "strip_stops": True,
            "drop_invalid": True,
            "alphabet": AA_ALPHABET,
        },
        fn=task_normalize,
    ),
    StepDef(
        name="length_stats",
        version="0.1.0",
        inputs={"normalized": "normalized"},
        outputs={"stats": OutSpec("stats", policy="cache")},
        params={"round_digits": 1},
        fn=task_length_stats,
    ),
]


def code_digest(steps: list[StepDef]) -> str:
    """流程结构指纹：步骤名/版本/端口/依赖的哈希。结构一变就是新工作流版本。"""
    blob = dumps([
        {
            "name": s.name,
            "version": s.version,
            "inputs": s.inputs,
            "outputs": {p: [o.kind, o.policy] for p, o in s.outputs.items()},
        }
        for s in steps
    ])
    return hashlib.sha256(blob.encode()).hexdigest()


def cache_key(step: StepDef, params: dict, input_hashes: dict[str, str]) -> str:
    blob = dumps({
        "step": step.name,
        "version": step.version,
        "params": params,
        "inputs": input_hashes,
    })
    return hashlib.sha256(blob.encode()).hexdigest()


# --------------------------------------------------------------------------
# 执行器
# --------------------------------------------------------------------------
@dataclass
class StepResult:
    name: str
    status: str                    # computed | reused
    cache_key: str
    artifact_ids: dict[str, int]
    duration_ms: float
    note: str


class Executor:
    def __init__(
        self,
        db: MetaDB,
        store: ObjectStore,
        steps: list[StepDef] | None = None,
        workflow_name: str = "fasta_len_demo",
        workflow_version: str = "0.1.0",
        description: str = "读取 FASTA → 规范化序列 → 输出长度统计（虚拟数据验证用）",
    ) -> None:
        self.db = db
        self.store = store
        self.steps = steps or PIPELINE
        self.workflow_name = workflow_name
        self.workflow_version = workflow_version
        self.description = description
        self.workflow_id = db.upsert_workflow(
            workflow_name, workflow_version, description, code_digest(self.steps)
        )

    # ---- 内部 ----
    def _register_external(self, name: str, path: Path) -> int:
        data = path.read_bytes()
        digest, obj_path, size = self.store.put(data)
        return self.db.upsert_artifact(digest, "fasta", "text/x-fasta", size, obj_path, "keep")

    def _outputs_available(self, step_id: int) -> bool:
        outs = self.db.outputs_of_step(step_id)
        if not outs:
            return False
        return all(self.store.exists(a["object_path"]) for a in outs)

    def _reuse_reason(self, row, step_id: int) -> str:
        owner = self.db.conn.execute(
            "SELECT run_id FROM step WHERE id=?", (int(row["id"]),)
        ).fetchone()
        return (
            f"缓存命中：cache_key={row['cache_key'][:12]}… "
            f"复用步骤 #{int(row['id'])}（run #{owner['run_id'] if owner else '?'}）"
        )

    # ---- 主流程 ----
    def run(
        self,
        *,
        user_id: str,
        intent: str,
        external_inputs: dict[str, Path],
        overrides: dict[str, dict] | None = None,
        run_params: dict | None = None,
        force: bool = False,
    ) -> tuple[int, list[StepResult]]:
        overrides = overrides or {}
        run_id = self.db.create_run(self.workflow_id, user_id, intent, run_params or {})
        results: list[StepResult] = []
        ext_art: dict[str, int] = {}
        resolved: dict[str, int] = {}   # 输出端口 -> artifact_id

        try:
            for step in self.steps:
                params = dict(step.params)
                params.update(overrides.get(step.name, {}))

                input_art: dict[str, int] = {}
                input_hashes: dict[str, str] = {}
                for port, src in step.inputs.items():
                    if src.startswith("@"):
                        key = src[1:]
                        if key not in ext_art:
                            ext_art[key] = self._register_external(key, external_inputs[key])
                        aid = ext_art[key]
                    else:
                        aid = resolved[src]
                    input_art[port] = aid
                    input_hashes[port] = self.db.get_artifact(aid)["content_hash"]

                ck = cache_key(step, params, input_hashes)
                # 即便 --force 也查一次，只为把"为什么没用缓存"记清楚
                hit = self.db.find_reusable_step(ck)

                if hit and not force and self._outputs_available(int(hit["id"])):
                    step_id = self.db.add_step(
                        run_id, step.name, step.version, params, ck,
                        "reused", int(hit["id"]), 0.0,
                    )
                    note = self._reuse_reason(hit, step_id)
                    status = "reused"
                    prev_out = {a["port"]: int(a["id"]) for a in self.db.outputs_of_step(int(hit["id"]))}
                    artifact_ids = {}
                    for port in step.outputs:
                        assert port in prev_out, f"历史步骤 #{hit['id']} 缺少输出端口 {port}"
                        aid = prev_out[port]
                        artifact_ids[port] = aid
                        self.db.link(step_id, "output", port, aid)
                        resolved[port] = aid
                    for port, aid in input_art.items():
                        self.db.link(step_id, "input", port, aid)
                    duration = 0.0
                else:
                    payloads: dict[str, bytes] = {}
                    for port, aid in input_art.items():
                        art = self.db.get_artifact(aid)
                        if not self.store.exists(art["object_path"]):
                            raise RuntimeError(
                                f"步骤 {step.name} 的输入 {port}（artifact #{aid}）内容已被清理，"
                                f"无法重算——真实系统应回退到上游重算"
                            )
                        payloads[port] = self.store.get(art["object_path"])

                    # 只统计任务本身的计算耗时（不含落盘/写库），复用时为 0
                    t0 = time.perf_counter()
                    out_payloads = step.fn(payloads, params)
                    duration = (time.perf_counter() - t0) * 1000

                    artifact_ids = {}
                    for port, spec in step.outputs.items():
                        data = out_payloads[port]
                        digest, obj_path, size = self.store.put(data)
                        aid = self.db.upsert_artifact(
                            digest, spec.kind, spec.media_type, size, obj_path, spec.policy
                        )
                        artifact_ids[port] = aid
                        resolved[port] = aid

                    step_id = self.db.add_step(
                        run_id, step.name, step.version, params, ck,
                        "computed", None, duration,
                    )
                    for port, aid in input_art.items():
                        self.db.link(step_id, "input", port, aid)
                    for port, aid in artifact_ids.items():
                        self.db.link(step_id, "output", port, aid)
                    note = "强制重算（--force 忽略缓存）" if (force and hit) else (
                        "首次计算" if not hit else "缓存存在但产物已被清理（按策略），重新计算"
                    )
                    status = "computed"

                results.append(StepResult(step.name, status, ck, artifact_ids, duration, note))

            computed = sum(1 for r in results if r.status == "computed")
            self.db.finish_run(run_id, "success", computed, len(results) - computed)
            return run_id, results
        except Exception as exc:  # noqa: BLE001
            self.db.finish_run(run_id, "failed",
                               sum(1 for r in results if r.status == "computed"),
                               sum(1 for r in results if r.status == "reused"))
            raise exc
