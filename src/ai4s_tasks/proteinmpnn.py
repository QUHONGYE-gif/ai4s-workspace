"""AiiDA CalcJob and Parser for the shared ProteinMPNN installation.

The CalcJob calls the shared `proteinmpnn` wrapper, which writes outputs plus a
`run.json` record holding the release, input and weight SHA-256 values. The
Parser only publishes outputs after every check below has passed.
"""

import hashlib
import json
from zipfile import BadZipFile

import numpy
from aiida.common.datastructures import CalcInfo, CodeInfo
from aiida.engine import CalcJob
from aiida.orm import Dict, SinglefileData
from aiida.parsers import Parser

from .proteinmpnn_outputs import (
    complete_parameters,
    design_problem,
    parameter_problem,
    parse_fasta,
    probability_problem,
    probability_sample_problem,
    score_problem,
)

EXPECTED_RELEASE = "8907e667-py312-torch260cu124"
SCHEMA_VERSION = "ai4s-artifacts-1"
CONTRACT_VERSION = "1"
VALIDATOR_VERSION = "proteinmpnn-3"

INPUT_PDB = "input.pdb"
OUTPUT_FOLDER = "outputs"
RUN_RECORD = f"{OUTPUT_FOLDER}/run.json"
RUN_LOG = f"{OUTPUT_FOLDER}/run.log"
# ProteinMPNN names its files after the input structure.
SEQUENCES_FILE = f"{OUTPUT_FOLDER}/seqs/input.fa"
SCORES_FILE = f"{OUTPUT_FOLDER}/scores/input.npz"
PROBABILITIES_FILE = f"{OUTPUT_FOLDER}/probs/input.npz"


def validate_params(value, _context):
    """AiiDA input validator: return an error message or None."""
    return parameter_problem(value.get_dict())


class ProteinMPNNCalculation(CalcJob):
    """Design sequences for one PDB structure with the shared ProteinMPNN."""

    CACHE_VERSION = 3

    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input("pdb_file", valid_type=SinglefileData, help="Input backbone structure (PDB).")
        spec.input("params", valid_type=Dict, validator=validate_params,
                   help="chains, num_sequences, sampling_temperature, seed; "
                        "optional model_name, batch_size, save_probabilities.")

        options = spec.inputs["metadata"]["options"]
        options["resources"].default = {"num_machines": 1, "num_mpiprocs_per_machine": 1}
        options["withmpi"].default = False
        options["max_wallclock_seconds"].default = 3600
        options["parser_name"].default = "ai4s.proteinmpnn"

        spec.output("result", valid_type=Dict,
                    help=f"{SCHEMA_VERSION} manifest with samples, scores and run identity.")
        spec.output("artifacts.sequences", valid_type=SinglefileData, help="Native and designed FASTA.")
        spec.output("artifacts.scores", valid_type=SinglefileData, help="Per-sample score arrays.")
        spec.output("artifacts.probabilities", valid_type=SinglefileData, required=False,
                    help="Per-residue probabilities, when requested.")

        # Failed results must never be reused through the AiiDA cache.
        spec.exit_code(300, "ERROR_MISSING_RUN_RECORD", message="run.json was not retrieved.",
                       invalidates_cache=True)
        spec.exit_code(301, "ERROR_MODEL_FAILED", message="ProteinMPNN did not complete: {reason}",
                       invalidates_cache=True)
        spec.exit_code(302, "ERROR_RELEASE_MISMATCH", message="Unexpected ProteinMPNN release: {release}",
                       invalidates_cache=True)
        spec.exit_code(303, "ERROR_INPUT_MISMATCH", message="The model read a different input: {reason}",
                       invalidates_cache=True)
        spec.exit_code(304, "ERROR_MISSING_OUTPUT", message="Required output file missing: {path}",
                       invalidates_cache=True)
        spec.exit_code(305, "ERROR_INVALID_DESIGNS", message="Designs do not match the request: {reason}",
                       invalidates_cache=True)
        spec.exit_code(306, "ERROR_INVALID_SCORES", message="Score file does not match: {reason}",
                       invalidates_cache=True)
        spec.exit_code(307, "ERROR_INVALID_PROBABILITIES", message="Probability file does not match: {reason}",
                       invalidates_cache=True)
        spec.exit_code(308, "ERROR_MALFORMED_OUTPUT", message="Malformed model output: {reason}",
                       invalidates_cache=True)

    def prepare_for_submission(self, folder):
        parameters = complete_parameters(self.inputs.params.get_dict())

        with self.inputs.pdb_file.open(mode="rb") as source, folder.open(INPUT_PDB, "wb") as target:
            target.write(source.read())

        code_info = CodeInfo()
        code_info.code_uuid = self.inputs.code.uuid
        code_info.stdout_name = "aiida.out"
        code_info.cmdline_params = [
            "--pdb_path", INPUT_PDB,
            "--pdb_path_chains", parameters["chains"],
            "--num_seq_per_target", str(parameters["num_sequences"]),
            "--batch_size", str(parameters["batch_size"]),
            "--sampling_temp", str(parameters["sampling_temperature"]),
            "--seed", str(parameters["seed"]),
            "--model_name", parameters["model_name"],
            "--save_score", "1",
            "--save_probs", "1" if parameters["save_probabilities"] else "0",
            "--out_folder", OUTPUT_FOLDER,
        ]

        calc_info = CalcInfo()
        calc_info.codes_info = [code_info]
        nested_files = [RUN_RECORD, RUN_LOG, SEQUENCES_FILE, SCORES_FILE]
        if parameters["save_probabilities"]:
            nested_files.append(PROBABILITIES_FILE)
        # A plain string would be stored by its file name only, and the two
        # input.npz files would overwrite each other; keep the full path instead.
        calc_info.retrieve_list = ["aiida.out"] + [
            (path, ".", path.count("/") + 1) for path in nested_files
        ]
        return calc_info


class ProteinMPNNParser(Parser):
    """Check run identity, designs and score files, then publish outputs."""

    CACHE_VERSION = 3

    def parse(self, **kwargs):
        try:
            return self._parse_outputs()
        except (ValueError, KeyError, TypeError, IndexError, AttributeError, OSError, EOFError, BadZipFile) as error:
            return self.exit_codes.ERROR_MALFORMED_OUTPUT.format(reason=str(error))

    def _parse_outputs(self):
        parameters = complete_parameters(self.node.inputs.params.get_dict())
        retrieved = self.retrieved

        # 1. The wrapper's record must show a finished run of the expected release.
        if not self._has_file(RUN_RECORD):
            return self.exit_codes.ERROR_MISSING_RUN_RECORD
        record = json.loads(retrieved.get_object_content(RUN_RECORD))
        if record.get("status") != "completed" or record.get("exit_code") != 0:
            reason = f"status={record.get('status')}, exit_code={record.get('exit_code')}"
            return self.exit_codes.ERROR_MODEL_FAILED.format(reason=reason)
        if record.get("release") != EXPECTED_RELEASE:
            return self.exit_codes.ERROR_RELEASE_MISMATCH.format(release=record.get("release"))

        # 2. The model must have read exactly the input node and the requested weights.
        with self.node.inputs.pdb_file.open(mode="rb") as handle:
            input_sha256 = hashlib.sha256(handle.read()).hexdigest()
        if record["inputs"]["pdb_path"]["sha256"] != input_sha256:
            return self.exit_codes.ERROR_INPUT_MISMATCH.format(reason="PDB SHA-256 differs")
        if not record["weights"]["path"].endswith(f"/{parameters['model_name']}.pt"):
            return self.exit_codes.ERROR_INPUT_MISMATCH.format(reason="weights file differs from model_name")
        if record.get("effective_seeds") != [parameters["seed"]]:
            return self.exit_codes.ERROR_INPUT_MISMATCH.format(
                reason=f"effective seeds {record.get('effective_seeds')}")

        # Compare execution observations with the identity captured before cache lookup.
        identity = self.node.base.attributes.get("ai4s_model_identity", None)
        if identity:
            if record.get("release") != identity["release"] or record.get("source_commit") != identity["source_commit"]:
                return self.exit_codes.ERROR_RELEASE_MISMATCH.format(release=record.get("release"))
            if record["weights"]["sha256"] != identity["weights_sha256"]:
                return self.exit_codes.ERROR_INPUT_MISMATCH.format(reason="weights SHA-256 differs from submitted identity")

        # 3. Designs, scores and optional probabilities must match the request.
        required = [SEQUENCES_FILE, SCORES_FILE]
        if parameters["save_probabilities"]:
            required.append(PROBABILITIES_FILE)
        for path in required:
            if not self._has_file(path):
                return self.exit_codes.ERROR_MISSING_OUTPUT.format(path=path)

        native, designs = parse_fasta(retrieved.get_object_content(SEQUENCES_FILE))
        problem = design_problem(native, designs, parameters)
        if problem:
            return self.exit_codes.ERROR_INVALID_DESIGNS.format(reason=problem)

        with retrieved.open(SCORES_FILE, "rb") as handle:
            with numpy.load(handle, allow_pickle=False) as score_arrays:
                problem = score_problem(designs, score_arrays["score"], score_arrays["global_score"])
        if problem:
            return self.exit_codes.ERROR_INVALID_SCORES.format(reason=problem)

        if parameters["save_probabilities"]:
            length = len(native["sequence"].replace("/", ""))
            with retrieved.open(PROBABILITIES_FILE, "rb") as handle:
                with numpy.load(handle, allow_pickle=False) as arrays:
                    problem = probability_problem(arrays["probs"], len(designs), length)
                    if not problem:
                        problem = probability_sample_problem(arrays, native, designs, parameters["chains"])
            if problem:
                return self.exit_codes.ERROR_INVALID_PROBABILITIES.format(reason=problem)

        # 4. All checks passed: publish files and the manifest.
        manifest = Dict(self._manifest(record, native, designs, parameters))
        self.out("artifacts.sequences", self._file_node(SEQUENCES_FILE, "design.fa"))
        self.out("artifacts.scores", self._file_node(SCORES_FILE, "scores.npz"))
        if parameters["save_probabilities"]:
            self.out("artifacts.probabilities", self._file_node(PROBABILITIES_FILE, "probabilities.npz"))
        self.out("result", manifest)
        return None

    def _has_file(self, path):
        try:
            self.retrieved.get_object(path)
        except FileNotFoundError:
            return False
        return True

    def _file_node(self, path, filename):
        with self.retrieved.open(path, "rb") as handle:
            return SinglefileData(file=handle, filename=filename)

    @staticmethod
    def _manifest(record, native, designs, parameters):
        sample_ids = [design["sample_id"] for design in designs]
        artifacts = [
            {
                "port": "artifacts.sequences",
                "role": "primary",
                "format": "fasta",
                "files": ["design.fa"],
                "sample_count": len(designs),
                "sample_ids": sample_ids,
                "samples": designs,
            },
            {
                "port": "artifacts.scores",
                "role": "primary",
                "format": "npz",
                "files": ["scores.npz"],
                "sample_count": len(designs),
                "sample_ids": sample_ids,
            },
        ]
        if parameters["save_probabilities"]:
            artifacts.append({
                "port": "artifacts.probabilities",
                "role": "optional",
                "format": "npz",
                "files": ["probabilities.npz"],
                "sample_count": len(designs),
                "sample_ids": sample_ids,
            })
        return {
            "schema_version": SCHEMA_VERSION,
            "task_id": "proteinmpnn",
            "contract_version": CONTRACT_VERSION,
            "version": record["release"],
            "validation": {"passed": True, "validator_version": VALIDATOR_VERSION},
            "artifacts": artifacts,
            "native": native,
            "run": {
                "release": record["release"],
                "source_commit": record["source_commit"],
                "input_pdb_sha256": record["inputs"]["pdb_path"]["sha256"],
                "weights": {
                    "model_name": parameters["model_name"],
                    "sha256": record["weights"]["sha256"],
                },
                "requested_seed": record["requested_seed"],
                "effective_seeds": record["effective_seeds"],
                "started_at": record["started_at"],
                "finished_at": record["finished_at"],
            },
        }
