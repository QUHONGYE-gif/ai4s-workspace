"""Small input inspection for configuration, not scientific validation."""

import hashlib
import re
import uuid
from pathlib import Path

from .storage import Problem

AMINO = set("ACDEFGHIKLMNPQRSTVWYX")


def protein(sequence):
    sequence = "".join(sequence.split()).upper()
    if not sequence or len(sequence) > 10000 or set(sequence) - AMINO:
        raise Problem(422, "本版需要 1–10000 个标准氨基酸／X 字符，不能输入空序列或修饰表达式")
    return sequence


def parse_fasta(text, *, a3m=False):
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            header = line[1:].strip()
            if not header:
                raise Problem(422, "FASTA/A3M 记录需要名称")
            records.append({"id": f"record-{len(records)+1}", "header": header, "sequence": ""})
        elif records:
            records[-1]["sequence"] += line
        else:
            raise Problem(422, "FASTA/A3M 需要以 >记录名 开始")
    if not records or any(not r["sequence"] for r in records):
        raise Problem(422, "没有完整的 FASTA/A3M 记录")
    if a3m:
        for r in records:
            aligned = re.sub(r"[a-z.]", "", r["sequence"])
            if not aligned or set(aligned) - AMINO - {"-"}:
                raise Problem(422, "A3M 包含不支持的字符")
            r["aligned"] = aligned
        width = len(records[0]["aligned"])
        if any(len(r["aligned"]) != width for r in records):
            raise Problem(422, "A3M 对齐列数不一致")
        if "-" in records[0]["aligned"]:
            raise Problem(422, "本版 A3M 首条查询序列不能有 gap")
    else:
        for r in records:
            r["sequence"] = protein(r["sequence"])
    has_samples = any("sample=" in r["header"] for r in records)
    for r in records:
        r["selectable"] = not has_samples or "sample=" in r["header"]
    return records


def inspect_file(name, data):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Problem(422, "输入文件需为 UTF-8 文本") from None
    suffix = Path(name).suffix.lower()
    if suffix == ".pdb":
        if sum(line.startswith("MODEL ") for line in text.splitlines()) > 1:
            raise Problem(422, "本演示只接受单个结构模型的 PDB")
        chains = {}
        for line in text.splitlines():
            if line.startswith("ATOM  ") and line[12:16].strip() == "CA":
                try:
                    coordinates = [float(line[a:b]) for a, b in ((30, 38), (38, 46), (46, 54))]
                except ValueError:
                    raise Problem(422, "PDB 坐标列格式错误") from None
                import math
                if not all(math.isfinite(c) for c in coordinates):
                    raise Problem(422, "PDB 坐标必须是有限数")
                key = line[21:22]
                chains.setdefault(key, set()).add(line[22:27])
        if not chains:
            raise Problem(422, "PDB 没有可读取的 ATOM / CA 坐标")
        return {"format": "PDB", "chains": {k: len(v) for k, v in chains.items()},
                "inspection": "仅检查单模型、CA 坐标与链；不是完整科学输入验证"}
    if suffix in (".fa", ".fasta", ".faa", ".a3m"):
        a3m = suffix == ".a3m"
        return {"format": "A3M" if a3m else "FASTA", "records": parse_fasta(text, a3m=a3m)}
    raise Problem(422, "输入支持 .pdb、.fa、.fasta、.faa、.a3m")


def upload(store, name, data):
    if not data or len(data) > 5 * 1024 * 1024:
        raise Problem(413, "文件不能为空，单文件上限为 5 MiB")
    metadata = inspect_file(name, data)
    file_id = "file-" + uuid.uuid4().hex
    # Original filenames never participate in the on-disk path.
    metadata.update(id=file_id, name=Path(name).name[:160], bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    with store.lock:
        directory = store.root / "uploads"
        directory.mkdir(exist_ok=True, mode=0o700)
        path = directory / file_id
        with path.open("xb") as stream:
            stream.write(data)
        path.chmod(0o600)
        store.write("files", file_id, metadata)
    return metadata
