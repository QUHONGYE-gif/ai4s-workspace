"""Versioned support boundary, distinct from scientific execution validation."""

from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field

from .models import Contract


class Params(Contract):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class RFDParams(Params):
    length: int = Field(ge=20, le=512)
    num_designs: int = Field(ge=1, le=64)
    rfd_steps: int = Field(ge=1, le=50)


class MPNNParams(Params):
    num_seq_per_target: int = Field(ge=1, le=512)
    sampling_temp: float = Field(gt=0, le=2)
    seed: int = Field(ge=0, le=2147483647)


class BoltzParams(Params):
    recycling_steps: int = Field(ge=0, le=20)
    sampling_steps: int = Field(ge=1, le=1000)
    diffusion_samples: int = Field(ge=1, le=32)
    msa_mode: Literal["empty", "precomputed"]


PARAM_TYPES = {"rfdiffusion": RFDParams, "proteinmpnn": MPNNParams, "boltz": BoltzParams}
RFD_COMMIT = "86507b6538f51fce57b5a72477165f03999ed7ae"
MPNN_COMMIT = "8907e6671bfbfc92303b5f79c4b5e6ce47cdef57"


def field(key, label, kind="number", **extra):
    return {"key": key, "label": label, "type": kind, **extra}


CATALOG = {
    "rfdiffusion": {
        "name": "RFdiffusion", "role": "骨架生成", "definition_version": "demo-1",
        "scenario": "单链无条件设计；长度 20–512 为本演示支持范围",
        "code_identity": RFD_COMMIT,
        "source_url": f"https://github.com/RosettaCommons/RFdiffusion/blob/{RFD_COMMIT}/config/inference/base.yaml",
        "fields": [field("length", "骨架长度", min=20, max=512, step=1),
                   field("num_designs", "生成骨架数", min=1, max=64, step=1),
                   field("rfd_steps", "扩散步数", min=1, max=50, step=1)],
        "sample_params": {"length": 80, "num_designs": 1, "rfd_steps": 50},
        "inputs": {}, "outputs": {"backbone": "PDB", "metadata": "TRB"},
        "output_roles": {"backbone": "primary", "metadata": "auxiliary"},
        "mapping": {"length": "contigmap.contigs=[L-L]", "num_designs": "inference.num_designs", "rfd_steps": "diffuser.T"},
    },
    "proteinmpnn": {
        "name": "ProteinMPNN", "role": "序列设计", "definition_version": "demo-1",
        "scenario": "单骨架序列设计；一个采样温度；512 条上限为演示限制",
        "code_identity": MPNN_COMMIT,
        "source_url": f"https://github.com/dauparas/ProteinMPNN/blob/{MPNN_COMMIT}/protein_mpnn_run.py",
        "fields": [field("num_seq_per_target", "设计序列数", min=1, max=512, step=1),
                   field("sampling_temp", "采样温度", min=0, max=2, step="any"),
                   field("seed", "随机种子", min=0, max=2147483647, step=1)],
        "sample_params": {"num_seq_per_target": 8, "sampling_temp": 0.1, "seed": 42},
        "inputs": {"backbone": "PDB"}, "outputs": {"sequences": "FASTA", "scores": "NPZ"},
        "output_roles": {"sequences": "primary", "scores": "auxiliary"},
        "mapping": {"num_seq_per_target": "--num_seq_per_target", "sampling_temp": "--sampling_temp（单温度字符串）", "seed": "--seed"},
    },
    "boltz": {
        "name": "Boltz", "role": "结构预测", "definition_version": "demo-1",
        "scenario": "Boltz 2.2.1 单条蛋白序列；显式空 MSA 或提供 A3M；上限为演示限制",
        "code_identity": "package:boltz==2.2.1",
        "source_url": "https://github.com/jwohlwend/boltz/blob/v2.2.1/src/boltz/main.py",
        "fields": [field("recycling_steps", "循环次数", min=0, max=20, step=1),
                   field("sampling_steps", "采样步数", min=1, max=1000, step=1),
                   field("diffusion_samples", "预测样本数", min=1, max=32, step=1),
                   field("msa_mode", "MSA 来源", "select", options=[["empty", "空 MSA · 单序列"], ["precomputed", "提供已有 A3M"]])],
        "sample_params": {"recycling_steps": 3, "sampling_steps": 200, "diffusion_samples": 1, "msa_mode": "empty"},
        "inputs": {"sequence": "FASTA", "msa": "A3M"}, "outputs": {"structure": "CIF", "confidence": "JSON"},
        "output_roles": {"structure": "primary", "confidence": "auxiliary"},
        "mapping": {"recycling_steps": "--recycling_steps", "sampling_steps": "--sampling_steps", "diffusion_samples": "--diffusion_samples", "msa_mode": "输入 YAML 的 protein.msa（产品选项）"},
    },
}


def validate_params(model_id, params, *, partial=False):
    cls = PARAM_TYPES[model_id]
    if partial:
        # Validate all supplied fields using the same full model; missing values are
        # filled only for validation, never persisted as extracted/default values.
        candidate = {**CATALOG[model_id]["sample_params"], **params}
    else:
        candidate = params
    return cls.model_validate(candidate).model_dump()


def knowledge(model_id):
    return (Path(__file__).parent / "knowledge" / f"{model_id}.md").read_text()
