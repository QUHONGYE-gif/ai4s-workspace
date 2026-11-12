"""Native kernel/Parser checks in a disposable profile.

Run directly with the isolated engine Python. Ordinary pytest skips this file.
No model command is executed; these cases test identity and rejection rules.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class KernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('AI4S_KERNEL_TEST') != '1':
            raise unittest.SkipTest('Run this file directly for a disposable profile')
        from aiida import load_profile, orm
        subprocess.run([sys.executable, '-m', 'aiida', 'presto', '--non-interactive', '--use-zeromq',
                        '--profile-name', 'kernel-tests', '--email', 'kernel-test@ai4s.invalid'], check=True)
        load_profile('kernel-tests')
        from aiida.engine.runners import Runner
        cls.runner = Runner(communicator=None)
        cls.addClassCleanup(cls.runner.close)
        cls.orm = orm
        cls.computer = orm.load_computer('localhost')
        cls.identity = dict(model_id='proteinmpnn', release='8907e667-py312-torch260cu124',
                            source_commit='8907e6671bfbfc92303b5f79c4b5e6ce47cdef57',
                            model_name='v_48_020', weights_family='vanilla', weights_sha256='a' * 64)
        cls.pdb = orm.SinglefileData(file=io.BytesIO(b'ATOM synthetic kernel input\n'), filename='input.pdb').store()

    def calculation(self, identity=None, seed=41, unresolved=None):
        from aiida.engine.utils import instantiate_process
        from aiida.manage import get_manager
        from aiida.plugins import CalculationFactory
        code = self.orm.InstalledCode(computer=self.computer, filepath_executable='/usr/bin/true',
                                      default_calc_job_plugin='ai4s.proteinmpnn')
        if identity:
            code.model_identity = identity
        if unresolved:
            code.base.attributes.set('ai4s_identity_unresolved', unresolved)
        code.store()
        params = self.orm.Dict(dict(chains='A', num_sequences=4, sampling_temperature=0.1,
                                    seed=seed, model_name='v_48_020', batch_size=1, save_probabilities=True))
        process = instantiate_process(self.runner, CalculationFactory('ai4s.proteinmpnn'),
                                      code=code, pdb_file=self.pdb, params=params)
        self.addCleanup(process.close)
        return process.node

    def test_identity_and_seed_enter_native_hash(self):
        a = self.calculation(self.identity)
        b = self.calculation(dict(reversed(list(self.identity.items()))))
        version = self.calculation({**self.identity, 'release':'changed-release'})
        weights = self.calculation({**self.identity, 'weights_sha256':'b'*64})
        seed = self.calculation(self.identity, seed=42)
        self.assertEqual(a.base.caching.get_hash(), b.base.caching.get_hash())
        for changed in [version, weights, seed]:
            self.assertNotEqual(a.base.caching.get_hash(), changed.base.caching.get_hash())
        self.assertEqual(a.base.attributes.get('ai4s_model_identity'), self.identity)
        self.assertEqual(a.base.extras.get('ai4s_identity_digest'), seed.base.extras.get('ai4s_identity_digest'))

    def test_unresolved_identity_cannot_read_or_supply_cache(self):
        from plumpy import ProcessState
        node = self.calculation(unresolved='missing weights manifest')
        self.assertFalse(node.base.caching.should_use_cache())
        node.set_process_state(ProcessState.FINISHED)
        node.set_exit_status(0)
        node.seal()
        self.assertFalse(node.base.caching.is_valid_cache)
        self.assertEqual(node.base.attributes.get('ai4s_identity_unresolved'), 'missing weights manifest')

    def parse_identity_mismatch(self, changes):
        from aiida.common.links import LinkType
        from ai4s_tasks.proteinmpnn import ProteinMPNNParser
        node = self.calculation(self.identity)
        record = dict(status='completed', exit_code=0, release=self.identity['release'],
                      source_commit=self.identity['source_commit'], effective_seeds=[41],
                      inputs={'pdb_path':{'sha256':hashlib.sha256(b'ATOM synthetic kernel input\n').hexdigest()}},
                      weights={'path':'/fixed/vanilla_model_weights/v_48_020.pt', 'sha256':'a'*64})
        record.update(changes)
        retrieved = self.orm.FolderData()
        retrieved.base.repository.put_object_from_filelike(io.BytesIO(json.dumps(record).encode()), 'outputs/run.json')
        retrieved.base.links.add_incoming(node, LinkType.CREATE, 'retrieved')
        retrieved.store()
        return ProteinMPNNParser(node).parse().status

    def test_parser_rejects_changed_weights(self):
        self.assertEqual(self.parse_identity_mismatch({'weights':{'path':'/fixed/v_48_020.pt', 'sha256':'b'*64}}), 303)

    def test_parser_rejects_changed_source_commit(self):
        self.assertEqual(self.parse_identity_mismatch({'source_commit':'different-commit'}), 302)


if __name__ == '__main__':
    if os.environ.get('AI4S_KERNEL_TEST') == '1':
        unittest.main()
    else:
        with tempfile.TemporaryDirectory(prefix='ai4s-kernel-tests-') as directory:
            environment = dict(os.environ, AIIDA_PATH=directory, AI4S_KERNEL_TEST='1')
            raise SystemExit(subprocess.call([sys.executable, __file__], env=environment))
