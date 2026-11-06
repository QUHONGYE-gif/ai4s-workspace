"""Checks for ProteinMPNN output parsing (no AiiDA or model needed)."""

from ai4s_tasks.proteinmpnn_outputs import (
    complete_parameters,
    design_problem,
    parameter_problem,
    parse_fasta,
    score_problem,
    probability_problem,
    probability_sample_problem,
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


def test_nonfinite_parameters_sequences_and_scores_are_rejected():
    native, designs = parse_fasta(FASTA)
    for value in (float("nan"), float("inf"), -float("inf")):
        assert parameter_problem({**PARAMETERS, "sampling_temperature": value})
        assert score_problem(designs, [value, 0.81], [0.7792, 0.8])
        assert design_problem(native, [{**designs[0], "score": value}, designs[1]], PARAMETERS)
    assert parameter_problem({**PARAMETERS, "seed": True})
    assert design_problem(native, [{**designs[0], "sequence": "!" * 46}, designs[1]], PARAMETERS)
    assert design_problem(native, list(reversed(designs)), PARAMETERS)


def test_probability_values_and_sample_mapping():
    try:
        import numpy
    except ImportError:
        from unittest import SkipTest
        raise SkipTest("NumPy comes from the separate AiiDA environment")
    probs = numpy.full((2, 3, 21), 1 / 21)
    assert probability_problem(probs, 2, 3) is None
    for invalid in (numpy.full_like(probs, numpy.nan), numpy.zeros_like(probs), numpy.full_like(probs, -1)):
        assert probability_problem(invalid, 2, 3)
    # NPZ stores B before A; FASTA writes chains sorted by chain name.
    arrays = {"S": numpy.array([[2, 0, 1], [4, 1, 2]]), "chain_order": numpy.array([["B", "A"]])}
    native = {"sequence": "AC/D"}
    designs = [{"sample_id": "s001", "sequence": "AC/D"}, {"sample_id": "s002", "sequence": "CD/F"}]
    assert probability_sample_problem(arrays, native, designs, "A B") is None
    arrays["S"] = arrays["S"][::-1]
    assert "s001" in probability_sample_problem(arrays, native, designs, "A B")
