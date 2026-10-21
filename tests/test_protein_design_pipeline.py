"""Check data boundaries against small hand-written examples, without model mocks."""

import importlib.util
import gzip
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


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

    def test_gpu_search_uses_gpu_and_does_not_pass_cpu_sensitivity(self):
        m = {"backend": "gpu", "sensitivity": 7.0, "evalue": 0.001,
             "max_sequences": 500, "threads": 10, "min_identity": 0.3,
             "query_coverage": 0.8}
        args = pipeline.mmseqs_search_args("query", "target_gpu", "hits", "tmp", m)
        self.assertEqual(args[:5], ["search", "query", "target_gpu", "hits", "tmp"])
        self.assertIn("--gpu", args)
        self.assertEqual(args[args.index("--gpu") + 1], 1)
        self.assertNotIn("-s", args)

    def test_cpu_search_keeps_configured_sensitivity(self):
        m = {"backend": "cpu", "sensitivity": 7.0, "evalue": 0.001,
             "max_sequences": 500, "threads": 10, "min_identity": 0.3,
             "query_coverage": 0.8}
        args = pipeline.mmseqs_search_args("query", "target", "hits", "tmp", m)
        self.assertIn("-s", args)
        self.assertEqual(args[args.index("-s") + 1], 7.0)
        self.assertNotIn("--gpu", args)

    def test_cpu_build_reaches_createdb_after_unpacking_fasta(self):
        source = self.root / "input.fasta.gz"
        with gzip.open(source, "wt") as f:
            f.write(">query\nACDE\n")
        prefix = self.root / "db/swissprot"
        c = {"root": str(self.root), "msa": {"database": str(prefix)}}
        # Stop at the external tool boundary; no scientific program runs here.
        with patch.object(pipeline.subprocess, "run", side_effect=RuntimeError("tool boundary")) as run:
            with self.assertRaisesRegex(RuntimeError, "tool boundary"):
                pipeline.build_database(SimpleNamespace(fasta_gz=source), c)
        self.assertEqual(prefix.with_suffix(".fasta").read_text(), ">query\nACDE\n")
        self.assertEqual(run.call_args.args[0], [str(self.root / "tools/mmseqs/bin/mmseqs"),
                                              "createdb", str(prefix.with_suffix(".fasta")), str(prefix)])

    def test_gpu_build_preserves_existing_staging_before_unpacking(self):
        prefix = self.root / "db/swissprot"
        staging = prefix.parent / ".mmseqs-build-source/swissprot"
        staging.parent.mkdir(parents=True)
        staging.write_text("previous database")
        c = {"root": str(self.root), "msa": {"database": str(prefix), "backend": "gpu"}}
        with self.assertRaisesRegex(FileExistsError, "staging prefix"):
            pipeline.build_database(SimpleNamespace(fasta_gz=self.root / "absent.gz"), c)
        self.assertEqual(staging.read_text(), "previous database")
        self.assertFalse(prefix.with_suffix(".fasta").exists())

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
