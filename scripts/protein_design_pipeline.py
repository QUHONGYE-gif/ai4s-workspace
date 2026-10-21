#!/usr/bin/env python3
"""One unconditional backbone -> one sequence -> local MSA search -> Boltz-2.

The controller uses only the Python standard library. Model code runs in the
existing Linux Conda environments. Each run requires a new output directory.
"""

import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile


AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")
RESIDUES = dict(zip(
    "ALA CYS ASP GLU PHE GLY HIS ILE LYS LEU MET ASN PRO GLN ARG SER THR VAL TRP TYR".split(),
    "ACDEFGHIKLMNPQRSTVWY",
))


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def mmseqs_snapshot(prefix):
    prefix = Path(prefix)
    files = sorted(p for p in prefix.parent.glob(prefix.name + "*")
                   if p.is_file() and not p.name.endswith(".source.json"))
    if not files or not Path(str(prefix) + ".dbtype").exists():
        raise ValueError(f"Incomplete MMseqs2 database: {prefix}")
    return {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in files}


def read_fasta(path):
    records = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            records.append([line[1:], ""])
        elif records:
            records[-1][1] += line
        else:
            raise ValueError(f"Sequence before FASTA header: {path}")
    if not records or any(not seq for _, seq in records):
        raise ValueError(f"Empty FASTA record: {path}")
    return records


def design_sequence(path, length):
    records = read_fasta(path)
    # The first record describes the input backbone, often all GLY.
    if len(records) != 2 or "sample=1" not in records[1][0]:
        raise ValueError("Expected native record plus exactly one ProteinMPNN sample")
    sequence = records[1][1]
    if len(sequence) != length or not set(sequence) <= AMINO_ACIDS:
        raise ValueError("Designed sequence is not the expected single protein chain")
    return sequence


def check_a3m(path, sequence):
    records = read_fasta(path)
    if records[0][1] != sequence:
        raise ValueError("A3M first sequence does not match the current query")
    for _, aligned in records:
        if not re.fullmatch(r"[A-Za-z.\-]+", aligned):
            raise ValueError("Invalid character in A3M")
        if len(re.sub(r"[a-z.]", "", aligned)) != len(sequence):
            raise ValueError("A3M alignment columns differ from query length")
    return len(records)


def filter_a3m(source, hits_tsv, target, sequence, min_identity, min_coverage, max_evalue):
    accepted = {}
    for line in Path(hits_tsv).read_text().splitlines():
        fields = line.split("\t")
        if len(fields) != 8:
            raise ValueError("Unexpected MMseqs2 tabular output format")
        _, target_id, identity, _, query_coverage, _, evalue, _ = fields
        if (float(identity) >= min_identity and float(query_coverage) >= min_coverage
                and float(evalue) <= max_evalue):
            accepted[target_id] = True
    records = read_fasta(source)
    seen = {sequence}
    kept = [(records[0][0], records[0][1])]
    for header, aligned in records[1:]:
        target_id = header.split()[0].split("::")[0]
        ungapped = re.sub(r"[a-z.\-]", "", aligned).upper()
        if target_id not in accepted or ungapped in seen:
            continue
        seen.add(ungapped)
        kept.append((header, aligned))
    Path(target).write_text("".join(f">{header}\n{aligned}\n" for header, aligned in kept))
    return {"aligned_records": len(records), "candidate_hits": len(accepted),
            "retained_unique_sequences": len(kept) - 1}


def pdb_sequence(path):
    sequence, positions = [], set()
    for line in Path(path).read_text().splitlines():
        if line.startswith("ATOM  ") and line[12:16].strip() == "CA":
            if line[16] not in " A":
                continue
            key = (line[21], line[22:27])
            if key in positions:
                raise ValueError("Duplicate C-alpha residue in PDB")
            positions.add(key)
            sequence.append(RESIDUES[line[17:20]])
    if not sequence or len({chain for chain, _ in positions}) != 1:
        raise ValueError("Expected one nonempty chain in PDB")
    return "".join(sequence)


def validate_outputs(out, length, sequence):
    if len(pdb_sequence(out / "rfd" / "backbone.pdb")) != length:
        raise ValueError("Backbone residue count differs from requested length")
    pred = out / "boltz/boltz_results_design/predictions/design"
    structures = sorted(pred.glob("design_model_*.pdb"))
    if not structures:
        raise ValueError("Boltz returned without a predicted PDB")
    confidences = []
    for structure in structures:
        if pdb_sequence(structure) != sequence:
            raise ValueError("Predicted PDB sequence differs from ProteinMPNN sequence")
        suffix = structure.stem
        confidence = json.loads((pred / f"confidence_{suffix}.json").read_text())
        for key in ("confidence_score", "ptm", "complex_plddt"):
            if not math.isfinite(confidence[key]):
                raise ValueError(f"Nonfinite {key}")
        confidences.append(confidence)
        for field in ("plddt", "pae", "pde"):
            with zipfile.ZipFile(pred / f"{field}_{suffix}.npz") as archive:
                if not archive.namelist() or archive.testzip() is not None:
                    raise ValueError(f"Invalid {field} NPZ")
    return {"residues": length, "prediction_count": len(structures),
            "sequence_matches": True, "confidence": confidences}


def load_config(path):
    c = json.loads(Path(path).read_text())
    for key in ("root", "conda", "rfd_env", "boltz_env"):
        if not Path(c[key]).is_absolute():
            raise ValueError(f"{key} must be an absolute Linux path")
    for key in ("length", "rfd_steps", "mpnn_seed", "boltz_sampling_steps", "boltz_diffusion_samples"):
        if not isinstance(c[key], int) or c[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    if c["rfd_seed"] < 0 or c["boltz_seed"] < 0 or c["boltz_recycling_steps"] < 0:
        raise ValueError("Seeds and recycling steps must be nonnegative")
    if c["mpnn_temperature"] <= 0 or not re.fullmatch(r"\d+", c["gpu"]):
        raise ValueError("Positive temperature and one GPU index are required")
    m = c["msa"]
    if m["mode"] not in ("empty", "swissprot"):
        raise ValueError("msa.mode must be empty or swissprot")
    if m["mode"] == "swissprot":
        if not Path(m["database"]).is_absolute():
            raise ValueError("msa.database must be absolute")
        if not (0 < m["query_coverage"] <= 1 and m["evalue"] > 0
                and 0 <= m["min_identity"] <= 1):
            raise ValueError("Invalid MSA coverage or E-value")
        if any(not isinstance(m[k], int) or m[k] <= 0 for k in ("threads", "max_sequences")):
            raise ValueError("MSA threads and max_sequences must be positive integers")
    return c


class Run:
    def __init__(self, out, config):
        self.out = Path(out).resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        (self.out / "logs").mkdir()
        self.data = {"status": "running", "started": now(), "config": config,
                     "commands": [], "scope": "one unconditional monomer; no function validation"}
        self.save()

    def save(self):
        write_json(self.out / "manifest.json", self.data)

    def command(self, name, argv, cwd, env=None):
        entry = {"name": name, "argv": [str(x) for x in argv], "cwd": str(cwd),
                 "started": now(), "log": f"logs/{name}.log", "status": "running"}
        self.data["commands"].append(entry)
        self.save()
        print(f"[{name}] {entry['log']}", flush=True)
        t0 = time.monotonic()
        with (self.out / entry["log"]).open("w") as log:
            result = subprocess.run(entry["argv"], cwd=cwd, env=env,
                                    stdout=log, stderr=subprocess.STDOUT)
        entry.update(returncode=result.returncode, ended=now(),
                     seconds=round(time.monotonic() - t0, 3),
                     status="completed" if result.returncode == 0 else "failed")
        self.save()
        if result.returncode:
            raise RuntimeError(f"{name} failed ({result.returncode}); see {entry['log']}")

    def finish(self):
        files = {}
        for p in sorted(self.out.rglob("*")):
            if p.is_file() and p.name != "manifest.json":
                files[str(p.relative_to(self.out))] = {"bytes": p.stat().st_size, "sha256": sha256(p)}
        self.data.update(status="completed", ended=now(), files=files)
        self.save()


def conda(c, env, *args):
    return [c["conda"], "run", "--no-capture-output", "-p", c[env], *map(str, args)]


def build_database(args, c):
    prefix = Path(c["msa"]["database"])
    prefix.parent.mkdir(parents=True, exist_ok=True)
    if list(prefix.parent.glob(prefix.name + "*")):
        raise FileExistsError("Database prefix already exists; choose a new prefix")
    fasta = prefix.with_suffix(".fasta")
    with gzip.open(args.fasta_gz, "rb") as source, fasta.open("xb") as dest:
        shutil.copyfileobj(source, dest)
    binary = Path(c["root"]) / "tools/mmseqs/bin/mmseqs"
    with prefix.with_suffix(".build.log").open("w") as log:
        subprocess.run([str(binary), "createdb", str(fasta), str(prefix)], check=True,
                       stdout=log, stderr=subprocess.STDOUT)
    version = subprocess.check_output([str(binary), "version"], text=True).strip()
    write_json(str(prefix) + ".source.json", {
        "status": "completed", "created": now(), "source": str(Path(args.fasta_gz).resolve()),
        "source_sha256": sha256(args.fasta_gz), "fasta_sha256": sha256(fasta),
        "mmseqs_version": version, "mmseqs_sha256": sha256(binary),
        "command": [str(binary), "createdb", str(fasta), str(prefix)],
        "database": str(prefix), "database_files": mmseqs_snapshot(prefix),
    })
    print(f"Database ready: {prefix}")


def register_database(args, c):
    """Record an already-built database when its source and tool version are known."""
    prefix = Path(c["msa"]["database"])
    fasta_gz = Path(args.fasta_gz)
    binary = Path(c["root"]) / "tools/mmseqs/bin/mmseqs"
    version = subprocess.check_output([str(binary), "version"], text=True).strip()
    if version != c["msa"]["mmseqs_version"]:
        raise ValueError("Installed MMseqs2 version differs from the configured version")
    if not fasta_gz.is_file():
        raise FileNotFoundError(fasta_gz)
    metadata = {
        "status": "completed", "created": now(), "source": str(fasta_gz.resolve()),
        "source_sha256": sha256(fasta_gz), "mmseqs_version": version,
        "mmseqs_sha256": sha256(binary), "database": str(prefix),
        "database_files": mmseqs_snapshot(prefix),
        "registered_existing_database": True,
        "note": "Existing database registered from the archived R002 snapshot; not rebuilt.",
    }
    write_json(str(prefix) + ".source.json", metadata)
    print(f"Registered database: {prefix}")


def run_pipeline(args, c):
    root = Path(c["root"])
    if args.dry_run:
        print(json.dumps({"config": c, "out": str(Path(args.out).resolve()),
                          "steps": ["preflight", "RFdiffusion", "ProteinMPNN", c["msa"]["mode"], "Boltz-2", "validate"],
                          "note": "Plan only; no environment or model validation performed"}, indent=2))
        return
    run = Run(args.out, c)
    out = run.out
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": c["gpu"], "DGLBACKEND": "pytorch",
           "OMP_NUM_THREADS": str(c["msa"].get("threads", 10))}
    rfd_env = {**env, "LD_LIBRARY_PATH": str(Path(c["rfd_env"]) / "lib") + ":" + env.get("LD_LIBRARY_PATH", "")}
    try:
        shutil.copy2(__file__, out / "pipeline.py")
        write_json(out / "config.json", c)
        run.data["execution_env"] = {k: env[k] for k in ("CUDA_VISIBLE_DEVICES", "DGLBACKEND", "OMP_NUM_THREADS")}
        run.save()
        run.command("gpu", ["nvidia-smi"], root, env)
        for environment in ("rfd_env", "boltz_env"):
            selected_env = rfd_env if environment == "rfd_env" else env
            run.command(environment + "-gpu", conda(c, environment, "python", "-c",
                        "import torch; print(torch.__version__, torch.version.cuda); assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"), root, selected_env)
            run.data["execution_env"][environment] = {k: selected_env[k] for k in ("CUDA_VISIBLE_DEVICES", "DGLBACKEND", "OMP_NUM_THREADS", "LD_LIBRARY_PATH") if k in selected_env}
            run.command(environment + "-freeze", conda(c, environment, "python", "-m", "pip", "freeze"), root, selected_env)
            expected = {"torch": c["rfd_torch" if environment == "rfd_env" else "boltz_torch"]}
            expected["dgl" if environment == "rfd_env" else "boltz"] = c["rfd_dgl" if environment == "rfd_env" else "boltz_version"]
            code = ("import importlib.metadata as m; expected=" + repr(expected)
                    + "; actual={k:m.version(k) for k in expected}; print(actual); assert actual==expected, (actual, expected)")
            run.command(environment + "-versions", conda(c, environment, "python", "-c", code), root, selected_env)
        for model in ("RFdiffusion", "ProteinMPNN"):
            path = root / "src" / model
            run.command(model + "-git", ["git", "log", "-1", "--format=%H"], path, env)
            run.command(model + "-status", ["git", "status", "--porcelain"], path, env)
            run.command(model + "-patch", ["git", "diff", "HEAD", "--binary"], path, env)
            expected = c["rfd_commit" if model == "RFdiffusion" else "mpnn_commit"]
            if (out / f"logs/{model}-git.log").read_text().strip() != expected:
                raise ValueError(f"{model} commit differs from the pinned configuration")
            status_lines = (out / f"logs/{model}-status.log").read_text().splitlines()
            # Hydra's default run directory is generated output, not source.
            source_changes = [line for line in status_lines
                              if not (model == "RFdiffusion" and line == "?? outputs/")]
            if source_changes:
                raise ValueError(f"{model} source is modified; review and snapshot before running")
        weight_paths = [root / "src/RFdiffusion/models/Base_ckpt.pt",
                        root / f"src/ProteinMPNN/vanilla_model_weights/{c['mpnn_model']}.pt",
                        root / "cache/boltz/boltz2_conf.ckpt"]
        run.data["weights"] = {str(p): sha256(p) for p in weight_paths}
        run.save()
        for directory in ("rfd", "mpnn", "inputs", "msa"):
            (out / directory).mkdir()
        prefix = out / "rfd/design"
        run.command("rfd", conda(c, "rfd_env", "python", "scripts/run_inference.py",
                    f"contigmap.contigs=[{c['length']}-{c['length']}]",
                    f"inference.output_prefix={prefix}", "inference.num_designs=1",
                    f"inference.model_directory_path={root / 'src/RFdiffusion/models'}",
                    "inference.deterministic=True", f"inference.design_startnum={c['rfd_seed']}",
                    f"diffuser.T={c['rfd_steps']}", "inference.write_trajectory=True"), root / "src/RFdiffusion", rfd_env)
        backbone = Path(str(prefix) + f"_{c['rfd_seed']}.pdb")
        shutil.copy2(backbone, out / "rfd/backbone.pdb")
        if len(pdb_sequence(backbone)) != c["length"]:
            raise ValueError("RFdiffusion backbone length mismatch")
        run.command("mpnn", conda(c, "rfd_env", "python", "protein_mpnn_run.py",
                    "--pdb_path", backbone, "--out_folder", out / "mpnn", "--num_seq_per_target", 1,
                    "--batch_size", 1, "--sampling_temp", c["mpnn_temperature"], "--seed", c["mpnn_seed"],
                    "--model_name", c["mpnn_model"], "--backbone_noise", 0.0,
                    "--save_score", 1, "--save_probs", 1), root / "src/ProteinMPNN", rfd_env)
        sequence = design_sequence(out / f"mpnn/seqs/{backbone.stem}.fa", c["length"])
        query = out / "inputs/design.fasta"
        query.write_text(">design\n" + sequence + "\n")
        msa_path = "empty"
        msa_info = {"mode": c["msa"]["mode"], "used_by_boltz": False}
        if c["msa"]["mode"] == "swissprot":
            m = c["msa"]
            database = Path(m["database"])
            provenance = Path(str(database) + ".source.json")
            if not provenance.exists() or not Path(str(database) + ".dbtype").exists():
                raise ValueError("Run register-db or build-db first; database provenance is required")
            shutil.copy2(provenance, out / "msa/database.source.json")
            mmseqs = root / "tools/mmseqs/bin/mmseqs"
            db_info = json.loads(provenance.read_text())
            if (sha256(mmseqs) != db_info["mmseqs_sha256"]
                    or db_info["mmseqs_version"] != m["mmseqs_version"]
                    or mmseqs_snapshot(database) != db_info["database_files"]):
                raise ValueError("MMseqs2 binary or database differs from its recorded provenance")
            def mm(name, *params):
                run.command(name, [mmseqs, *params], out, env)
            mm("msa-createdb", "createdb", query, out / "msa/query")
            mm("msa-search", "search", out / "msa/query", database, out / "msa/hits", out / "msa/tmp",
               "-s", m["sensitivity"], "-e", m["evalue"], "--max-seqs", m["max_sequences"],
               "--threads", m["threads"], "-a", 1, "--alignment-mode", 3,
               "--min-seq-id", m["min_identity"], "-c", m["query_coverage"], "--cov-mode", 2)
            mm("msa-tsv", "convertalis", out / "msa/query", database, out / "msa/hits", out / "msa/hits.tsv",
               "--format-output", "query,target,fident,alnlen,qcov,tcov,evalue,bits")
            mm("msa-export", "result2msa", out / "msa/query", database, out / "msa/hits", out / "msa/alignment", "--msa-format-mode", 5)
            mm("msa-unpack", "unpackdb", out / "msa/alignment", out / "msa/a3m", "--unpack-name-mode", 1, "--unpack-suffix", ".a3m")
            raw_a3m = out / "msa/a3m/0.a3m"
            filtered_a3m = out / "msa/design.filtered.a3m"
            filter_stats = filter_a3m(raw_a3m, out / "msa/hits.tsv", filtered_a3m, sequence,
                                      m["min_identity"], m["query_coverage"], m["evalue"])
            records = check_a3m(filtered_a3m, sequence)
            msa_info.update(**filter_stats, records=records,
                            search_hits=len((out / "msa/hits.tsv").read_text().splitlines()),
                            min_identity=m["min_identity"], query_coverage=m["query_coverage"],
                            evalue=m["evalue"], database_source_sha256=sha256(provenance))
            if records > 1:
                msa_path = str(filtered_a3m)
                msa_info["used_by_boltz"] = True
                msa_info["reason"] = "search candidates passed identity, query coverage, and E-value screens; homology requires biological review"
            else:
                msa_info["reason"] = "no candidates passed identity, coverage, and E-value screens; use single-sequence mode"
        write_json(out / "msa/summary.json", msa_info)
        write_json(out / "inputs/design.yaml", {"version": 1, "sequences": [{"protein": {
            "id": "A", "sequence": sequence, "msa": msa_path}}]})
        # JSON is a subset of YAML; using it avoids adding a controller dependency.
        run.command("boltz", conda(c, "boltz_env", "boltz", "predict", out / "inputs/design.yaml",
                    "--out_dir", out / "boltz", "--cache", root / "cache/boltz", "--model", "boltz2",
                    "--accelerator", "gpu", "--devices", 1, "--output_format", "pdb",
                    "--no_kernels", "--num_workers", 0, "--seed", c["boltz_seed"],
                    "--recycling_steps", c["boltz_recycling_steps"], "--sampling_steps", c["boltz_sampling_steps"],
                    "--diffusion_samples", c["boltz_diffusion_samples"]), out, env)
        checks = validate_outputs(out, c["length"], sequence)
        if checks["prediction_count"] != c["boltz_diffusion_samples"]:
            raise ValueError("Boltz prediction count differs from requested samples")
        write_json(out / "checks.json", {**checks, "msa": msa_info})
        run.finish()
        print(f"Completed: {out / 'manifest.json'}")
    except BaseException as error:
        run.data.update(status="failed", ended=now(), error=f"{type(error).__name__}: {error}")
        run.save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-db", help="Build a new MMseqs2 database from a local gzipped FASTA")
    build.add_argument("--config", required=True)
    build.add_argument("--fasta-gz", required=True)
    register = sub.add_parser("register-db", help="Register an existing MMseqs2 database with provenance")
    register.add_argument("--config", required=True)
    register.add_argument("--fasta-gz", required=True)
    run = sub.add_parser("run", help="Run one monomer design in a new output directory")
    run.add_argument("--config", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    c = load_config(args.config)
    if args.command == "build-db":
        build_database(args, c)
    elif args.command == "register-db":
        register_database(args, c)
    else:
        run_pipeline(args, c)


if __name__ == "__main__":
    main()
