"""Contract checks for demo persistence and the actual HTTP boundary."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from workbench.server import MAX_BODY, create_server
from workbench.storage import ConflictError, SnapshotStore

SESSION_A = 'a' * 32
SESSION_B = 'b' * 32
STATE = {'version': 1, 'catalog': [], 'experiments': [], 'drafts': {}, 'next': 1}


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SnapshotStore(Path(self.directory.name))

    def test_namespace_isolation_and_restart_persistence(self):
        self.store.save(SESSION_A, 0, STATE)
        self.assertIsNone(self.store.load(SESSION_B)['state'])
        restarted = SnapshotStore(Path(self.directory.name))
        self.assertEqual(restarted.load(SESSION_A), {'revision': 1, 'state': STATE})

    def test_stale_revision_cannot_overwrite_newer_snapshot(self):
        self.store.save(SESSION_A, 0, STATE)
        with self.assertRaises(ConflictError):
            self.store.save(SESSION_A, 0, dict(STATE, next=99))
        self.assertEqual(self.store.load(SESSION_A)['state']['next'], 1)

    def test_paths_and_invalid_schema_rejected_before_write(self):
        with self.assertRaises(ValueError):
            self.store.save('../escape', 0, STATE)
        with self.assertRaises(ValueError):
            self.store.save(SESSION_A, 0, dict(STATE, catalog=[{'id': 'x'}, {'id': 'x'}]))
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.server = create_server(port=0, data_dir=cls.directory.name)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.directory.cleanup()

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        body = json.dumps(data).encode() if data is not None else None
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        result = response.status, {k.lower():v for k,v in response.getheaders()}, response.read()
        connection.close()
        return result

    def test_health_and_bootstrap_distinguish_simulation(self):
        status, _, data = self.request('GET', '/api/health')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['mode'], 'simulation')
        status, _, data = self.request('GET', '/api/demo/bootstrap')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['fixtures']['proteinSteps'][3]['deps'], ['embedding', 'msa'])

    def test_state_round_trip_and_conflict(self):
        headers = {'X-Demo-Session': 'c' * 32, 'Content-Type': 'application/json'}
        status, _, data = self.request('GET', '/api/demo/state', headers=headers)
        self.assertEqual(json.loads(data), {'revision': 0, 'state': None})
        status, _, data = self.request('PUT', '/api/demo/state', {'revision': 0, 'state': STATE}, headers)
        self.assertEqual((status, json.loads(data)), (200, {'revision': 1}))
        status, _, _ = self.request('PUT', '/api/demo/state', {'revision': 0, 'state': STATE}, headers)
        self.assertEqual(status, 409)
        status, _, data = self.request('GET', '/api/demo/state', headers={'X-Demo-Session': 'd' * 32})
        self.assertIsNone(json.loads(data)['state'])

    def test_missing_namespace_and_content_type_are_rejected(self):
        status, _, _ = self.request('GET', '/api/demo/state')
        self.assertEqual(status, 400)
        status, _, _ = self.request('PUT', '/api/demo/state', {})
        self.assertEqual(status, 415)

    def test_oversize_request_is_rejected_without_consuming_body(self):
        status, _, _ = self.request('PUT', '/api/demo/state', {}, {
            'Content-Type': 'application/json', 'Content-Length': str(MAX_BODY + 1),
            'X-Demo-Session': SESSION_A})
        self.assertEqual(status, 413)

    def test_only_frontend_is_served_and_assets_have_correct_types(self):
        status, headers, data = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(b'./assets/app.js', data)
        self.assertNotIn(b'<style>', data)
        status, headers, _ = self.request('GET', '/assets/styles.css')
        self.assertEqual(status, 200)
        self.assertIn('text/css', headers['content-type'])
        for path in ('/../.env', '/src/workbench/server.py', '/assets/', '/api/unknown'):
            status, _, _ = self.request('GET', path)
            self.assertEqual(status, 404, path)


if __name__ == '__main__':
    unittest.main()
