"""Standalone CPU integration checks: python tests/test_aiida_workflows.py.

The parent process creates a temporary profile and launches an isolated worker.
Ordinary pytest collection skips these checks instead of using a member profile.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest


class WorkflowIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("AI4S_ISOLATED_WORKFLOW_TEST") != "1":
            raise unittest.SkipTest("Run this file directly to create an isolated AiiDA profile")
        from aiida import load_profile, orm
        from aiida.engine import submit
        from ai4s_workflows import calcjobs
        cls.orm = orm
        cls.submit = staticmethod(submit)
        cls.root = Path(os.environ["AIIDA_PATH"])
        subprocess.run([
            sys.executable, "-m", "aiida", "presto", "--non-interactive", "--use-zeromq",
            "--profile-name", "workflow-tests", "--email", "workflow-test@ai4s.invalid",
        ], check=True)
        load_profile()
        cls.computer = orm.load_computer("localhost")
        cls.computer.set_workdir(str(cls.root / "work"))
        cls.computer.store()
        cls.mock = Path(calcjobs.__file__).parent / "bin/mock_mpnn.py"
        cls.normal = None
        subprocess.run([sys.executable, "-m", "aiida", "daemon", "start", "1"], check=True)
        from aiida.manage import get_manager
        for attempt in range(6):
            try:
                get_manager().get_communicator()
                break
            except ConnectionError:
                if attempt == 5:
                    raise
                time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        subprocess.run([sys.executable, "-m", "aiida", "daemon", "stop"], check=True)

    @classmethod
    def code(cls, label, failures=0, invalid_json=False):
        counter = cls.root / (label + ".count")
        executable = cls.root / label
        body = f'''#!{sys.executable}
from pathlib import Path
import random,runpy,sys
counter=Path({str(counter)!r})
count=int(counter.read_text())+1 if counter.exists() else 1
counter.write_text(str(count))
if count <= {failures}:sys.exit(101)
if {invalid_json!r}:
 Path("result.json").write_text("invalid-json")
 sys.exit(0)
random.random=lambda:0.9
runpy.run_path({str(cls.mock)!r},run_name="__main__")
'''
        executable.write_text(body)
        executable.chmod(0o755)
        return cls.orm.InstalledCode(
            label=label, computer=cls.computer, filepath_executable=str(executable),
            default_calc_job_plugin="ai4s.light-mpnn",
        ).store()

    @classmethod
    def wait(cls, node):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            node = cls.orm.load_node(node.pk)
            if node.is_terminated:
                return node
            time.sleep(0.5)
        raise AssertionError(f"Process {node.pk} did not finish in 120 seconds")

    @classmethod
    def workflow(cls, code, **extra):
        from ai4s_workflows.samples import make_test_pdb
        from ai4s_workflows.workflows import ProteinMPNNFilterWorkChain
        return cls.wait(cls.submit(
            ProteinMPNNFilterWorkChain,
            code=code, pdb_file=make_test_pdb(),
            mpnn_params=cls.orm.Dict(dict={"version": "v1.0", "num_seq": 4}),
            filter_params=cls.orm.Dict(dict={"score_threshold": 1.08, "top_k": 2}),
            **extra,
        ))

    @classmethod
    def successful_workflow(cls):
        if cls.normal is None:
            cls.normal = cls.workflow(cls.code("success"))
        return cls.normal

    def diagnostics(self, node):
        result = []
        for process in [node] + list(node.called):
            row = {"pk": process.pk, "state": str(process.process_state),
                   "exit_status": process.exit_status, "exception": process.exception}
            if isinstance(process, self.orm.CalcJobNode) and "retrieved" in process.outputs:
                repository = process.outputs.retrieved.base.repository
                for filename in ["_scheduler-stderr.txt", "_scheduler-stdout.txt"]:
                    if filename in repository.list_object_names():
                        row[filename] = repository.get_object_content(filename)
            result.append(row)
        return result

    def assert_ok(self, node):
        self.assertTrue(node.is_finished_ok, self.diagnostics(node))

    def test_success_and_provenance(self):
        from ai4s_workflows.samples import count_mpnn_launches
        node = self.successful_workflow()
        self.assert_ok(node)
        selected = node.outputs.selected_sequences.get_dict()["entries"]
        self.assertEqual([row["sample_id"] for row in selected], ["s001", "s002"])
        self.assertEqual(node.outputs.selection_report.get_dict(), {
            "model_launches": 1, "retry_attempt": 0, "selected_count": 2,
            "mpnn_cache_source": None,
        })
        children = [n for n in node.called if isinstance(n, self.orm.CalcJobNode)]
        self.assertEqual(len(children), 1)
        self.assertEqual(count_mpnn_launches(node.pk), 1)
        calc = children[0]
        self.assert_ok(calc)
        self.assertEqual(calc.outputs.result.creator.pk, calc.pk)
        self.assertIn("result.json", calc.outputs.retrieved.base.repository.list_object_names())
        self.assertEqual(json.loads(calc.base.repository.get_object_content("params.json")), {
            "version": "v1.0", "num_seq": 4,
        })
        self.assertEqual(calc.base.repository.get_object_content("input.pdb"), "TEST PDB\nATOM 1 N ALA A 1")
        for output in [node.outputs.selected_sequences, node.outputs.sample_table, node.outputs.selection_report]:
            self.assertIsInstance(output.creator, self.orm.CalcFunctionNode)

    def test_filter_only_reuses_upstream(self):
        from ai4s_workflows.rerun import rerun_filter_only
        from ai4s_workflows.samples import count_mpnn_launches
        original = self.successful_workflow()
        self.assert_ok(original)
        before = (self.root / "success.count").read_text()
        rerun = self.wait(rerun_filter_only(original.pk, new_top_k=1))
        self.assert_ok(rerun)
        self.assertEqual(rerun.outputs.selection_report.get_dict()["model_launches"], 0)
        self.assertEqual([n for n in rerun.called if isinstance(n, self.orm.CalcJobNode)], [])
        self.assertEqual(count_mpnn_launches(rerun.pk), 0)
        self.assertEqual((self.root / "success.count").read_text(), before)
        self.assertEqual([row["sample_id"] for row in rerun.outputs.selected_sequences.get_dict()["entries"]], ["s001"])
        second = self.wait(rerun_filter_only(rerun.pk, new_top_k=2))
        self.assert_ok(second)
        self.assertEqual(second.inputs.existing_mpnn_result.uuid, rerun.inputs.existing_mpnn_result.uuid)
        self.assertEqual(second.outputs.selection_report.get_dict()["model_launches"], 0)
        self.assertEqual((self.root / "success.count").read_text(), before)

    def test_retry_then_success(self):
        node = self.workflow(self.code("retry-once", failures=1))
        self.assert_ok(node)
        report = node.outputs.selection_report.get_dict()
        self.assertEqual((report["model_launches"], report["retry_attempt"]), (2, 1))

    def test_retry_limit_returns_exit_code(self):
        node = self.workflow(self.code("always-fail", failures=100))
        self.assertEqual(node.process_state.value, "finished")
        self.assertEqual(node.exit_status, 202)
        self.assertEqual(node.outputs.selection_report.get_dict(), {
            "model_launches": 3, "retry_attempt": 2, "status": "failed_max_retry",
        })
        children = [n for n in node.called if isinstance(n, self.orm.CalcJobNode)]
        self.assertEqual(len(children), 3)
        self.assertEqual([child.exit_status for child in children], [101, 101, 101], self.diagnostics(node))
        self.assertIsInstance(node.outputs.selection_report.creator, self.orm.CalcFunctionNode)

    def test_invalid_json_is_a_failed_calculation(self):
        from ai4s_workflows.calcjobs import LightMPNNCalcJob
        from ai4s_workflows.samples import make_test_pdb
        node = self.wait(self.submit(
            LightMPNNCalcJob, code=self.code("invalid-json", invalid_json=True),
            pdb_file=make_test_pdb(), params=self.orm.Dict(dict={"version": "v1.0"}),
        ))
        self.assertTrue(node.is_failed, self.diagnostics(node))
        self.assertEqual(node.exit_status, 102)
        self.assertNotIn("result", node.outputs)

    def test_excepted_child_does_not_enter_success_branch(self):
        from aiida.common.extendeddicts import AttributeDict
        from aiida.engine import ProcessState
        from ai4s_workflows.workflows import ProteinMPNNFilterWorkChain
        child = types.SimpleNamespace(is_finished_ok=False, is_failed=False, process_state=ProcessState.EXCEPTED)
        owner = types.SimpleNamespace(
            ctx=AttributeDict({"mpnn_calc": child, "retry_count": 0}), report=lambda message: None,
        )
        self.assertIsNone(ProteinMPNNFilterWorkChain.on_mpnn_done(owner))
        self.assertEqual(owner.ctx.retry_count, 1)

    def test_reused_result_passes_the_same_schema_gate(self):
        result = self.orm.Dict(dict={"schema_version": "invalid", "version": "v1.0", "artifacts": [{}]})
        node = self.workflow(self.code("unused"), existing_mpnn_result=result)
        self.assertEqual(node.process_state.value, "finished")
        self.assertEqual(node.exit_status, 204)
        self.assertEqual(node.outputs.selection_report.get_dict()["model_launches"], 0)
        self.assertFalse((self.root / "unused.count").exists())

    def test_unvalidated_result_and_different_request_are_rejected(self):
        original = self.successful_workflow()
        child = next(n for n in original.called if isinstance(n, self.orm.CalcJobNode))
        # A hand-created Dict has no eligible successful CalcJob creator.
        forged = self.orm.Dict(dict={**child.outputs.result.get_dict(), "validation": {"passed": False}})
        rejected = self.workflow(child.inputs.code, existing_mpnn_result=forged)
        self.assertEqual(rejected.exit_status, 206, self.diagnostics(rejected))
        rejected = self.workflow(self.code("different-code"), existing_mpnn_result=child.outputs.result)
        self.assertEqual(rejected.exit_status, 206, self.diagnostics(rejected))
        from ai4s_workflows.workflows import upstream_problem
        self.assertIn("PDB", upstream_problem(child.outputs.result, child.inputs.code,
                          self.orm.SinglefileData(file=__import__('io').BytesIO(b'different PDB'), filename='different.pdb'), child.inputs.params))
        self.assertIn("parameters", upstream_problem(child.outputs.result, child.inputs.code,
                          child.inputs.pdb_file, self.orm.Dict(dict={"version": "v1.1", "num_seq": 4})))

    def test_query_and_readonly_export_preserve_native_states(self):
        from ai4s_query import query, workbench
        original = self.successful_workflow()
        output = original.outputs.selected_sequences
        info = query.describe(output.uuid)
        self.assertTrue(info["lineage"]["upstream"])
        self.assertEqual(info["creator_uuid"], output.creator.uuid)
        original_count = self.orm.QueryBuilder().append(self.orm.Node).count()
        exported = workbench.export_state([output.uuid])
        self.assertEqual(self.orm.QueryBuilder().append(self.orm.Node).count(), original_count)
        exp = exported["experiments"][0]
        self.assertEqual(exp["status"], "completed")
        self.assertIsNone(exp["config"]["seed"])
        self.assertEqual(exp["policyRules"]["name"], "未记录")
        self.assertTrue(all(not a["accessible"] for a in exported["catalog"]))
        for state, exit_status, expected in [("finished", 301, "failed"), ("running", None, "running"), ("waiting", None, "waiting")]:
            node = self.orm.CalcJobNode(process_type="aiida.calculations:ai4s.proteinmpnn").store()
            node.set_process_state(state)
            if exit_status is not None:
                node.set_exit_status(exit_status)
            record, _ = workbench.build_experiment(node.uuid)
            self.assertEqual(record["status"], expected)
            self.assertEqual(record["outputs"], [])

    def test_real_parser_rejects_corrupt_arrays_before_publishing(self):
        """Synthetic files exercise the real Parser; no model or GPU is run."""
        import hashlib
        import io
        import numpy
        from aiida.common import LinkType
        from ai4s_tasks.proteinmpnn import ProteinMPNNParser, EXPECTED_RELEASE, VALIDATOR_VERSION
        from ai4s_tasks.proteinmpnn_outputs import parse_fasta
        from test_ai4s_tasks import FASTA, PARAMETERS

        native, designs = parse_fasta(FASTA)
        alphabet = "ACDEFGHIKLMNPQRSTVWYX"
        sampled = numpy.array([[alphabet.index(aa) for aa in design["sequence"]] for design in designs])
        record = {"status": "completed", "exit_code": 0, "release": EXPECTED_RELEASE,
                  "inputs": {"pdb_path": {"sha256": hashlib.sha256(b"PDB").hexdigest()}},
                  "weights": {"path": "/weights/v_48_020.pt", "sha256": "synthetic-test"},
                  "effective_seeds": [42], "requested_seed": 42, "source_commit": "synthetic-test",
                  "started_at": "synthetic-test", "finished_at": "synthetic-test"}
        def archive(**arrays):
            handle = io.BytesIO()
            numpy.savez(handle, **arrays)
            handle.seek(0)
            return handle
        for case, expected in [("valid", None), ("nan-scores", 306), ("nan-probs", 307),
                               ("sample-order", 307), ("invalid-json", 308), ("missing-probs-key", 308),
                               ("missing-run-field", 308), ("invalid-npz", 308)]:
            with self.subTest(case=case):
                calc = self.orm.CalcJobNode(process_type="aiida.calculations:ai4s.proteinmpnn", computer=self.computer)
                calc.base.links.add_incoming(self.orm.Dict(dict=PARAMETERS).store(), LinkType.INPUT_CALC, "params")
                calc.base.links.add_incoming(self.orm.SinglefileData(file=io.BytesIO(b"PDB"), filename="input.pdb").store(), LinkType.INPUT_CALC, "pdb_file")
                calc.store()
                retrieved = self.orm.FolderData()
                run_record = dict(record)
                if case == "missing-run-field": del run_record["source_commit"]
                retrieved.base.repository.put_object_from_filelike(io.StringIO("invalid-json" if case == "invalid-json" else json.dumps(run_record)), "outputs/run.json")
                retrieved.base.repository.put_object_from_filelike(io.StringIO(FASTA), "outputs/seqs/input.fa")
                scores = numpy.array([design["score"] for design in designs])
                global_scores = numpy.array([design["global_score"] for design in designs])
                if case == "nan-scores": scores[0] = numpy.nan
                retrieved.base.repository.put_object_from_filelike(archive(score=scores, global_score=global_scores), "outputs/scores/input.npz")
                probs = numpy.full((2, len(native["sequence"]), 21), 1 / 21)
                if case == "nan-probs": probs[0, 0, 0] = numpy.nan
                arrays = {"probs": probs, "S": sampled[::-1] if case == "sample-order" else sampled,
                          "chain_order": numpy.array([["A"]])}
                if case == "missing-probs-key": del arrays["probs"]
                retrieved.base.repository.put_object_from_filelike(io.BytesIO(b"invalid-npz") if case == "invalid-npz" else archive(**arrays), "outputs/probs/input.npz")
                retrieved.base.links.add_incoming(calc, LinkType.CREATE, "retrieved")
                retrieved.store()
                parser = ProteinMPNNParser(calc)
                outcome = parser.parse()
                self.assertEqual(outcome.status if outcome else None, expected)
                if expected is None:
                    self.assertEqual(parser.outputs["result"].get_dict()["validation"]["validator_version"], VALIDATOR_VERSION)
                else:
                    self.assertFalse(parser.outputs)


if __name__ == "__main__":
    if os.environ.get("AI4S_ISOLATED_WORKFLOW_TEST") == "1":
        unittest.main(verbosity=2)
    else:
        with tempfile.TemporaryDirectory(prefix="ai4s-wf-") as directory:
            environment = dict(os.environ, AIIDA_PATH=directory, AI4S_ISOLATED_WORKFLOW_TEST="1")
            outcome = subprocess.run([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env=environment)
        sys.exit(outcome.returncode)
