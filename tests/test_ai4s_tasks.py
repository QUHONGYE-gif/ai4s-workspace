"""Checks for ProteinMPNN output parsing (no AiiDA or model needed)."""

from ai4s_tasks.proteinmpnn_outputs import (
    complete_parameters,
    design_problem,
    parameter_problem,
    parse_fasta,
    score_problem,
)

# Header layout copied from a real ProteinMPNN 8907e667 run on 1CRN.
FASTA = """>1CRN, score=1.5334, global_score=1.5334, fixed_chains=[], designed_chains=['A'], model_name=v_48_020, git_hash=unknown, seed=42
TTCCPSIVARSNFNVCRLPGTPEAICATYTGCIIIPGATCPGDYAN
>T=0.1, sample=1, score=0.7792, global_score=0.7792, seq_recovery=0.5435
TVCCPSEEAKKKYEECRKSGTPDEECAKKTGCIIIPGTKCPPDYPY
>T=0.1, sample=2, score=0.8100, global_score=0.8000, seq_recovery=0.5000
TVCCPSEEAKKKYEECRKSGTPDEECAKKTGCIIIPGTKCPPDYPA
"""
PARAMETERS = complete_parameters(
    {"chains": "A", "num_sequences": 2, "sampling_temperature": 0.1, "seed": 42}
)


def test_parse_fasta_separates_native_and_designs():
    native, designs = parse_fasta(FASTA)
    assert native["seed"] == 42 and native["model_name"] == "v_48_020"
    assert [design["sample_id"] for design in designs] == ["s001", "s002"]
    assert designs[0]["score"] == 0.7792 and designs[1]["global_score"] == 0.8


def test_designs_match_request():
    native, designs = parse_fasta(FASTA)
    assert design_problem(native, designs, PARAMETERS) is None
    assert "expected 4 designs" in design_problem(native, designs, {**PARAMETERS, "num_sequences": 4})
    assert "seed" in design_problem(native, designs, {**PARAMETERS, "seed": 7})


def test_scores_must_match_fasta_headers():
    _, designs = parse_fasta(FASTA)
    assert score_problem(designs, [0.77923, 0.81], [0.77923, 0.8]) is None
    assert "s002 score" in score_problem(designs, [0.7792, 0.9], [0.7792, 0.8])
    assert "2 designs" in score_problem(designs, [0.7792], [0.7792])


def test_parameters_require_fixed_nonzero_seed():
    assert parameter_problem(PARAMETERS) is None
    assert "seed" in parameter_problem({**PARAMETERS, "seed": 0})
    assert "missing" in parameter_problem({"chains": "A"})
    assert "multiple" in parameter_problem({**PARAMETERS, "num_sequences": 3, "batch_size": 2})
