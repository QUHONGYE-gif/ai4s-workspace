"""Read and check ProteinMPNN output files without depending on AiiDA.

ProteinMPNN writes one FASTA file per input structure. The first record is the
native sequence; every following record is one designed sample.
"""

import re

PARAMETER_DEFAULTS = {
    "model_name": "v_48_020",
    "batch_size": 1,
    "save_probabilities": True,
}
REQUIRED_PARAMETERS = ("chains", "num_sequences", "sampling_temperature", "seed")
HEADER_FIELD = re.compile(r"(\w+)=([^,]+)")


def complete_parameters(parameters):
    """Return the parameters with defaults filled in."""
    return {**PARAMETER_DEFAULTS, **parameters}


def parameter_problem(parameters):
    """Describe the first invalid parameter, or return None when all are usable."""
    missing = [name for name in REQUIRED_PARAMETERS if name not in parameters]
    if missing:
        return f"missing parameters: {', '.join(missing)}"
    parameters = complete_parameters(parameters)
    if not isinstance(parameters["chains"], str) or not parameters["chains"].strip():
        return "chains must be a non-empty string such as 'A'"
    for name in ("num_sequences", "batch_size"):
        if not isinstance(parameters[name], int) or parameters[name] < 1:
            return f"{name} must be a positive integer"
    if parameters["num_sequences"] % parameters["batch_size"]:
        return "num_sequences must be a multiple of batch_size"
    # Seed 0 lets ProteinMPNN pick a random seed, which breaks reproducibility.
    if not isinstance(parameters["seed"], int) or parameters["seed"] == 0:
        return "seed must be a non-zero integer"
    temperature = parameters["sampling_temperature"]
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or temperature <= 0:
        return "sampling_temperature must be one positive number"
    if not isinstance(parameters["save_probabilities"], bool):
        return "save_probabilities must be true or false"
    return None


def parse_header(header):
    """Turn 'T=0.1, sample=1, score=0.77' into a dictionary of strings."""
    return {key: value.strip() for key, value in HEADER_FIELD.findall(header)}


def parse_fasta(text):
    """Split ProteinMPNN FASTA text into the native record and designed records."""
    records = []
    for block in text.split(">")[1:]:
        lines = block.strip().splitlines()
        records.append({"header": lines[0], "sequence": "".join(lines[1:]).strip()})
    if not records:
        raise ValueError("FASTA file has no records")

    native_fields = parse_header(records[0]["header"])
    native = {
        "sequence": records[0]["sequence"],
        "score": float(native_fields["score"]),
        "global_score": float(native_fields["global_score"]),
        "seed": int(native_fields["seed"]),
        "model_name": native_fields["model_name"],
    }

    designs = []
    for record in records[1:]:
        fields = parse_header(record["header"])
        sample_number = int(fields["sample"])
        designs.append({
            "sample_id": f"s{sample_number:03d}",
            "sequence": record["sequence"],
            "temperature": float(fields["T"]),
            "score": float(fields["score"]),
            "global_score": float(fields["global_score"]),
            "seq_recovery": float(fields["seq_recovery"]),
        })
    return native, designs


def design_problem(native, designs, parameters):
    """Describe the first mismatch between parsed designs and the request."""
    if len(designs) != parameters["num_sequences"]:
        return f"expected {parameters['num_sequences']} designs, found {len(designs)}"
    sample_ids = [design["sample_id"] for design in designs]
    if len(set(sample_ids)) != len(sample_ids):
        return "duplicate sample numbers in FASTA headers"
    if native["seed"] != parameters["seed"]:
        return f"FASTA reports seed {native['seed']}, requested {parameters['seed']}"
    if native["model_name"] != parameters["model_name"]:
        return f"FASTA reports model {native['model_name']}, requested {parameters['model_name']}"
    for design in designs:
        if len(design["sequence"]) != len(native["sequence"]):
            return f"{design['sample_id']} length differs from the native sequence"
        if abs(design["temperature"] - parameters["sampling_temperature"]) > 1e-9:
            return f"{design['sample_id']} used temperature {design['temperature']}"
    return None


def score_problem(designs, scores, global_scores):
    """Check that the score arrays match the scores printed in FASTA headers.

    FASTA headers keep four decimals, so values are compared within 1e-4.
    """
    if len(scores) != len(designs) or len(global_scores) != len(designs):
        return f"score arrays have {len(scores)} entries for {len(designs)} designs"
    for design, score, global_score in zip(designs, scores, global_scores):
        if abs(design["score"] - float(score)) > 1e-4:
            return f"{design['sample_id']} score differs between FASTA and score file"
        if abs(design["global_score"] - float(global_score)) > 1e-4:
            return f"{design['sample_id']} global score differs between FASTA and score file"
    return None
