"""Read and check ProteinMPNN output files without depending on AiiDA.

ProteinMPNN writes one FASTA file per input structure. The first record is the
native sequence; every following record is one designed sample.
"""

import math
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
        if type(parameters[name]) is not int or parameters[name] < 1:
            return f"{name} must be a positive integer"
    if parameters["num_sequences"] % parameters["batch_size"]:
        return "num_sequences must be a multiple of batch_size"
    # Seed 0 lets ProteinMPNN pick a random seed, which breaks reproducibility.
    if type(parameters["seed"]) is not int or not 1 <= parameters["seed"] < 2**32:
        return "seed must be an integer between 1 and 2**32 - 1"
    temperature = parameters["sampling_temperature"]
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not math.isfinite(temperature) or temperature <= 0:
        return "sampling_temperature must be one finite positive number"
    if not isinstance(parameters["model_name"], str) or not re.fullmatch(r"v_48_0(?:02|10|20|30)", parameters["model_name"]):
        return "model_name must name a supported vanilla ProteinMPNN model"
    unknown = parameters.keys() - {*REQUIRED_PARAMETERS, *PARAMETER_DEFAULTS}
    if unknown:
        return f"unsupported parameters: {', '.join(sorted(unknown))}"
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
    if sample_ids != [f"s{index:03d}" for index in range(1, len(designs) + 1)]:
        return "sample numbers must follow the score/probability array order"
    if native["seed"] != parameters["seed"]:
        return f"FASTA reports seed {native['seed']}, requested {parameters['seed']}"
    if native["model_name"] != parameters["model_name"]:
        return f"FASTA reports model {native['model_name']}, requested {parameters['model_name']}"
    if not native["sequence"] or any(not chain or set(chain) - set("ACDEFGHIKLMNPQRSTVWYX") for chain in native["sequence"].split("/")):
        return "native sequence contains empty chains or invalid amino acids"
    if not all(math.isfinite(native[key]) for key in ("score", "global_score")):
        return "native scores must be finite"
    for design in designs:
        if len(design["sequence"]) != len(native["sequence"]):
            return f"{design['sample_id']} length differs from the native sequence"
        if any(not chain or set(chain) - set("ACDEFGHIKLMNPQRSTVWYX") for chain in design["sequence"].split("/")):
            return f"{design['sample_id']} contains invalid amino acids"
        if [len(chain) for chain in design["sequence"].split("/")] != [len(chain) for chain in native["sequence"].split("/")]:
            return f"{design['sample_id']} chain lengths differ from native"
        if not all(math.isfinite(design[key]) for key in ("temperature", "score", "global_score", "seq_recovery")):
            return f"{design['sample_id']} contains non-finite numeric fields"
        if not 0 <= design["seq_recovery"] <= 1:
            return f"{design['sample_id']} seq_recovery must be between 0 and 1"
        if abs(design["temperature"] - parameters["sampling_temperature"]) > 1e-9:
            return f"{design['sample_id']} used temperature {design['temperature']}"
    return None


def score_problem(designs, scores, global_scores):
    """Check that the score arrays match the scores printed in FASTA headers.

    FASTA headers keep four decimals, so values are compared within 1e-4.
    """
    if getattr(scores, "ndim", 1) != 1 or getattr(global_scores, "ndim", 1) != 1:
        return "score arrays must be one-dimensional"
    if len(scores) != len(designs) or len(global_scores) != len(designs):
        return f"score arrays have {len(scores)} entries for {len(designs)} designs"
    for design, score, global_score in zip(designs, scores, global_scores):
        if not all(math.isfinite(value) for value in (score, global_score, design["score"], design["global_score"])):
            return f"{design['sample_id']} scores must be finite"
        if abs(design["score"] - float(score)) > 1e-4:
            return f"{design['sample_id']} score differs between FASTA and score file"
        if abs(design["global_score"] - float(global_score)) > 1e-4:
            return f"{design['sample_id']} global score differs between FASTA and score file"
    return None


def probability_problem(probabilities, count, length):
    """Validate the requested per-residue categorical distributions."""
    import numpy

    expected = (count, length, 21)
    if probabilities.shape != expected:
        return f"shape {probabilities.shape}, expected {expected}"
    if not numpy.isfinite(probabilities).all():
        return "probabilities must be finite"
    if ((probabilities < 0) | (probabilities > 1)).any():
        return "probabilities must be between 0 and 1"
    if not numpy.allclose(probabilities.sum(axis=-1), 1, rtol=1e-5, atol=1e-5):
        return "probabilities must sum to 1 along the amino-acid axis"
    return None


def probability_sample_problem(arrays, native, designs, chains):
    """Match NPZ sampled amino-acid indices to FASTA samples and chain order."""
    sampled = arrays["S"]
    native_chains = native["sequence"].split("/")
    chain_names = sorted(chains.split())
    if len(chain_names) != len(native_chains):
        return "requested chains do not match FASTA chain count"
    lengths = dict(zip(chain_names, map(len, native_chains)))
    length = sum(lengths.values())
    if sampled.shape != (len(designs), length) or sampled.dtype.kind not in "iu":
        return "sampled amino-acid indices have invalid shape or dtype"
    if ((sampled < 0) | (sampled > 20)).any():
        return "sampled amino-acid indices are outside the ProteinMPNN alphabet"
    order = arrays["chain_order"]
    if order.ndim != 2 or not len(order):
        return "chain_order must contain the model's per-batch chain order"
    alphabet = "ACDEFGHIKLMNPQRSTVWYX"
    for index, design in enumerate(designs):
        chain_order = order[index % len(order)].tolist()
        if sorted(chain_order) != chain_names:
            return "NPZ chain_order differs from requested chains"
        offset, sequences = 0, {}
        for name in chain_order:
            size = lengths[name]
            sequences[name] = "".join(alphabet[aa] for aa in sampled[index, offset:offset + size])
            offset += size
        if "/".join(sequences[name] for name in chain_names) != design["sequence"]:
            return f"{design['sample_id']} sequence differs between FASTA and probability file"
    return None
