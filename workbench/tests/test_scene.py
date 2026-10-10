import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
import numpy as np
import server
from model_io import load_scene, parts, select_part


class WholeSceneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='seamheal_scene_')
        self.outputs = patch.object(server,'OUTPUTS',Path(self.temp.name))
        self.outputs.start()
        self.client = TestClient(server.app)

    def tearDown(self):
        self.outputs.stop()
        self.temp.cleanup()

    def test_whole_scene_diagnosis_lists_recommended_and_other_issues(self):
        response = self.client.post('/api/scene/diagnose',json={'model_id':'courtyard'})
        self.assertEqual(response.status_code,200,response.text)
        report = response.json()
        self.assertEqual(report['total_parts'],56)
        self.assertEqual(len(report['recommended_part_ids']),2)
        self.assertGreater(report['issue_parts'],2)
        self.assertFalse(report['diagnosis']['watertight'])
        targets = [p for p in report['parts'] if p['id'] in report['recommended_part_ids']]
        self.assertEqual(sum(p['diagnosis']['boundary_edges'] for p in targets),180)

    def test_whole_scene_repair_preserves_other_components_and_reports_scope(self):
        source = server.MODELS['courtyard']['path'].read_bytes()
        before,_ = load_scene(source)
        selected = [p['id'] for p in parts(before) if p['repair_target']]
        response = self.client.post('/api/scene/repair',json={'model_id':'courtyard','part_ids':selected})
        self.assertEqual(response.status_code,200,response.text)
        data = response.json()
        report = data['report']
        self.assertEqual(report['scope_type'],'scene')
        self.assertFalse(report['reference_used'])
        self.assertFalse(report['after']['watertight'])
        self.assertEqual(report['scene_after']['issue_parts'],report['scene_before']['issue_parts']-2)
        self.assertTrue(all(p['report']['after']['watertight'] for p in report['part_reports']))
        self.assertEqual(len(data['stl_urls']),2)
        after,_ = load_scene((server.OUTPUTS/(data['result_id']+'.glb')).read_bytes())
        self.assertEqual([p['name'] for p in parts(before)],[p['name'] for p in parts(after)])
        for part in parts(before):
            _,_,old,old_matrix = select_part(before,part['id'])
            _,_,new,new_matrix = select_part(after,part['id'])
            np.testing.assert_array_equal(old_matrix,new_matrix)
            if part['id'] not in selected:
                np.testing.assert_array_equal(old.vertices,new.vertices)
                np.testing.assert_array_equal(old.faces,new.faces)
                np.testing.assert_array_equal(getattr(old.visual,'uv',None),getattr(new.visual,'uv',None))
        with zipfile.ZipFile(server.OUTPUTS/(data['result_id']+'.zip')) as archive:
            self.assertEqual(json.loads(archive.read('report.json'))['scope_type'],'scene')
            self.assertIsNone(archive.testzip())
        self.assertEqual(hashlib.sha256(source).hexdigest(),hashlib.sha256(server.MODELS['courtyard']['path'].read_bytes()).hexdigest())
        continued = self.client.post('/api/diagnose',json={'model_id':'courtyard','part_id':selected[0],'result_id':data['result_id']})
        self.assertEqual(continued.status_code,200,continued.text)
        self.assertEqual(continued.json()['diagnosis']['boundary_edges'],0)

    def test_invalid_batch_selection_does_not_create_result(self):
        for selection in ([],['part-999'],['part-36','part-36']):
            response = self.client.post('/api/scene/repair',json={'model_id':'courtyard','part_ids':selection})
            self.assertEqual(response.status_code,422,response.text)
        self.assertFalse(list(server.OUTPUTS.glob('*')))

    def test_failed_component_does_not_save_partial_scene(self):
        diagnosed = self.client.post('/api/scene/diagnose',json={'model_id':'courtyard'}).json()
        unsupported = next(p['id'] for p in diagnosed['parts'] if p['diagnosis']['nonmanifold_edges']>0)
        response = self.client.post('/api/scene/repair',json={'model_id':'courtyard','part_ids':[diagnosed['recommended_part_ids'][0],unsupported]})
        self.assertEqual(response.status_code,422,response.text[:1000])
        self.assertIn('未保存',response.json()['detail'])
        self.assertFalse(list(server.OUTPUTS.glob('*')))


if __name__=='__main__':
    unittest.main()
