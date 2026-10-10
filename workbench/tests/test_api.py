import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import server


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.temp = tempfile.TemporaryDirectory(prefix='seamheal_test_')
        self.outputs = patch.object(server, 'OUTPUTS', Path(self.temp.name))
        self.outputs.start()

    def tearDown(self):
        self.outputs.stop()
        self.temp.cleanup()

    def test_real_pipeline(self):
        before = self.client.post('/api/diagnose', json={'model_id': 'panel'})
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.json()['diagnosis']['boundary_edges'], 72)
        repaired = self.client.post('/api/repair', json={'model_id': 'panel'})
        self.assertEqual(repaired.status_code, 200, repaired.text)
        data = repaired.json()
        self.assertTrue(data['report']['after']['watertight'])
        self.assertFalse(data['report']['reference_used'])
        self.assertEqual(len(list(Path(self.temp.name).glob('*.glb'))), 1)
        self.assertEqual(len(list(Path(self.temp.name).glob('*.json'))), 1)

    def test_reject_untrusted_request(self):
        result = self.client.post('/api/repair', json={'model_id': 'panel'}, headers={'Origin': 'https://example.com'})
        self.assertEqual(result.status_code, 403)

    def test_unknown_and_showcase(self):
        self.assertEqual(self.client.post('/api/repair', json={'model_id': 'missing'}).status_code, 404)
        self.assertEqual(self.client.post('/api/repair', json={'model_id': 'courtyard'}).status_code, 422)

    def test_invalid_upload(self):
        self.assertEqual(self.client.post('/api/models?filename=bad.exe', content=b'bad').status_code, 415)
        self.assertEqual(self.client.post('/api/models?filename=bad.glb', content=b'bad').status_code, 422)

    def test_busy_worker_rejects_parallel_jobs(self):
        server.WORKER.acquire()
        try:
            self.assertEqual(self.client.post('/api/repair', json={'model_id': 'panel'}).status_code, 429)
            data = (server.ASSETS / 'exports/panel_damaged.glb').read_bytes()
            self.assertEqual(self.client.post('/api/models?filename=panel.glb', content=data).status_code, 429)
        finally:
            server.WORKER.release()

    def test_external_resource_rejected(self):
        import struct
        doc = json.dumps({'asset': {'version': '2.0'}, 'buffers': [{'uri': 'file:///private.bin'}]}).encode()
        doc += b' ' * (-len(doc) % 4)
        data = struct.pack('<5I', 0x46546C67, 2, 20+len(doc), len(doc), 0x4E4F534A) + doc
        response = self.client.post('/api/models?filename=model.glb', content=data)
        self.assertEqual(response.status_code, 422)
        self.assertIn('内嵌', response.json()['detail'])


if __name__ == '__main__':
    unittest.main()
