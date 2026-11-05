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


if __name__ == "__main__":
    if os.environ.get("AI4S_ISOLATED_WORKFLOW_TEST") == "1":
        unittest.main(verbosity=2)
    else:
        with tempfile.TemporaryDirectory(prefix="ai4s-wf-") as directory:
            environment = dict(os.environ, AIIDA_PATH=directory, AI4S_ISOLATED_WORKFLOW_TEST="1")
            outcome = subprocess.run([sys.executable, str(Path(__file__).resolve())], env=environment)
        sys.exit(outcome.returncode)
