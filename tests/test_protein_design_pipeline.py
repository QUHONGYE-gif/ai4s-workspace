"""Check data boundaries against small hand-written examples, without model mocks."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "scripts/protein_design_pipeline.py"
SPEC = importlib.util.spec_from_file_location("protein_pipeline", SOURCE)
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class PipelineBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_mpnn_uses_sample_not_native(self):
        fasta = self.root / "sample.fa"
        fasta.write_text(">native\nGGGG\n>T=0.1, sample=1\nACDE\n")
        self.assertEqual(pipeline.design_sequence(fasta, 4), "ACDE")
        with self.assertRaises(ValueError):
            pipeline.design_sequence(fasta, 5)
        fasta.write_text(">native\nGGGG\n")
        with self.assertRaises(ValueError):
            pipeline.design_sequence(fasta, 4)

    def test_a3m_insertions_do_not_add_aligned_columns(self):
        a3m = self.root / "alignment.a3m"
        a3m.write_text(">query\nACDE\n>hit\nACg-E\n")
        self.assertEqual(pipeline.check_a3m(a3m, "ACDE"), 2)
        with self.assertRaises(ValueError):
            pipeline.check_a3m(a3m, "ACDF")
        a3m.write_text(">query\nACDE\n>hit\nACgE\n")
        with self.assertRaises(ValueError):
            pipeline.check_a3m(a3m, "ACDE")

    def test_hits_must_pass_all_screens_and_be_unique(self):
        a3m, tsv, filtered = [self.root / name for name in ("raw.a3m", "hits.tsv", "filtered.a3m")]
        a3m.write_text(">query\nACDE\n>good\nACDF\n>duplicate\nACDF\n>self\nACDE\n>low_cov\nA--E\n>low_id\nGGGG\n>bad_e\nACDA\n")
        tsv.write_text(
            "query\tgood\t0.75\t4\t1.0\t1.0\t1e-10\t50\n"
            "query\tduplicate\t0.75\t4\t1.0\t1.0\t1e-10\t50\n"
            "query\tself\t1.0\t4\t1.0\t1.0\t1e-10\t50\n"
            "query\tlow_cov\t0.5\t2\t0.5\t1.0\t1e-10\t50\n"
            "query\tlow_id\t0.0\t4\t1.0\t1.0\t1e-10\t50\n"
            "query\tbad_e\t0.75\t4\t1.0\t1.0\t0.1\t50\n"
        )
        stats = pipeline.filter_a3m(a3m, tsv, filtered, "ACDE", 0.3, 0.8, 0.001)
        self.assertEqual(stats["retained_unique_sequences"], 1)
        self.assertEqual(filtered.read_text(), ">query\nACDE\n>good\nACDF\n")
        tsv.write_text("")
        stats = pipeline.filter_a3m(a3m, tsv, filtered, "ACDE", 0.3, 0.8, 0.001)
        self.assertEqual(stats["retained_unique_sequences"], 0)
        self.assertEqual(pipeline.check_a3m(filtered, "ACDE"), 1)

    def test_previous_run_is_never_overwritten(self):
        out = self.root / "existing"
        out.mkdir()
        sentinel = out / "keep.txt"
        sentinel.write_text("previous scientific evidence")
        with self.assertRaises(FileExistsError):
            pipeline.Run(out, {})
        self.assertEqual(sentinel.read_text(), "previous scientific evidence")

    def test_missing_prediction_is_not_success(self):
        out = self.root / "missing_prediction"
        (out / "rfd").mkdir(parents=True)
        # A genuine, already verified backbone allows this check to target the
        # missing Boltz result rather than inventing a successful model output.
        artifact = SOURCE.parents[1] / "experiments/R001-protein-design-smoke/evidence/backbone.pdb"
        (out / "rfd/backbone.pdb").write_bytes(artifact.read_bytes())
        with self.assertRaisesRegex(ValueError, "without a predicted PDB"):
            pipeline.validate_outputs(out, 80, "A" * 80)


if __name__ == "__main__":
    unittest.main()
