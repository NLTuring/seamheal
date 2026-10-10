import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient
import numpy as np
import trimesh
import server
from model_io import load_scene, isolate, parts, replace_part, select_part, world_mesh


class SceneTests(unittest.TestCase):
    def test_stl_units_and_up_axis(self):
        box = trimesh.creation.box(extents=[30, 20, 10])
        scene, _ = load_scene(box.export(file_type='stl'), 'stl', 'mm')
        np.testing.assert_allclose(scene.extents, [.03, .01, .02])
        np.testing.assert_allclose(world_mesh(scene, print_axes=True).extents, [.03, .02, .01])

    def test_scene_selection_and_isolation(self):
        scene = trimesh.Scene()
        scene.add_geometry(trimesh.creation.box(), node_name='a')
        scene.add_geometry(trimesh.creation.box(), node_name='b', transform=trimesh.transformations.translation_matrix([4, 0, 0]))
        subset = isolate(scene, 'part-1')
        np.testing.assert_allclose(subset.bounds, [[3.5, -.5, -.5], [4.5, .5, .5]])
        with self.assertRaises(ValueError):
            select_part(scene)
        node, _, mesh, _ = select_part(scene, 'part-0')
        replacement = mesh.copy()
        replacement.vertices *= .8
        result = replace_part(scene, node, replacement)
        np.testing.assert_array_equal(world_mesh(result, 'part-1').vertices, world_mesh(scene, 'part-1').vertices)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='seamheal_flow_')
        self.root = Path(self.temp.name)
        self.patches = [patch.object(server, k, self.root) for k in ('OUTPUTS', 'UPLOADS')]
        self.patches.append(patch.object(server, 'CATALOG', self.root / 'models.json'))
        for p in self.patches:
            p.start()
        self.client = TestClient(server.app)
        self.original_models = dict(server.MODELS)
        server.MODELS.clear()
        server.MODELS.update({key:value for key,value in self.original_models.items() if not key.startswith('import-')})

    def tearDown(self):
        server.MODELS.clear(); server.MODELS.update(self.original_models)
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_import_persistence_and_parts(self):
        data = trimesh.creation.box(extents=[30, 20, 10]).export(file_type='stl')
        response = self.client.post('/api/models?filename=cube.stl&units=mm', content=data)
        self.assertEqual(response.status_code, 200, response.text)
        model = response.json()
        self.assertEqual(len(json.loads(server.CATALOG.read_text(encoding='utf-8'))), 1)
        response = self.client.get(f'/api/models/{model["id"]}/parts')
        self.assertEqual(len(response.json()['parts']), 1)
        check = self.client.post('/api/manufacturing/check', json={'model_id': model['id']})
        self.assertEqual(check.status_code, 200, check.text)
        np.testing.assert_allclose(check.json()['dimensions_mm'], [30, 20, 10], rtol=1e-5)
        del server.MODELS[model['id']]
        server.restore_catalog()
        self.assertEqual(server.MODELS[model['id']]['title'], 'cube.stl')
        self.assertTrue(server.MODELS[model['id']]['path'].exists())
        self.client.delete(f'/api/models/{model["id"]}')
        del server.MODELS[model['id']]
        server.restore_catalog()
        self.assertTrue(server.MODELS[model['id']]['archived'])
        self.assertNotIn(model['id'], [m['id'] for m in self.client.get('/api/samples').json()['samples']])

    def test_obj_and_ply_units(self):
        box = trimesh.creation.box(extents=[3, 2, 1])
        for extension in ('obj', 'ply'):
            with self.subTest(extension=extension):
                data = box.export(file_type=extension)
                if isinstance(data, str):
                    data = ('mtllib missing.mtl\n' + data).encode('utf-8')
                response = self.client.post(f'/api/models?filename=cube.{extension}&units=cm', content=data)
                self.assertEqual(response.status_code, 200, response.text)
                model = response.json()
                if extension == 'obj':
                    self.assertTrue(model['import_warnings'])
                check = self.client.post('/api/manufacturing/check', json={'model_id':model['id']})
                self.assertEqual(check.status_code, 200, check.text)
                np.testing.assert_allclose(check.json()['dimensions_mm'], [30, 20, 10], rtol=1e-5)

    def test_chained_scene_repairs_preserve_other_parts(self):
        scene = trimesh.Scene()
        for index, name in enumerate(('a', 'b', 'c')):
            mesh = trimesh.creation.box(extents=[.03,.02,.01])
            if name != 'c':
                mesh.update_faces(np.arange(len(mesh.faces)-2))
            scene.add_geometry(mesh, node_name=name,
                               transform=trimesh.transformations.translation_matrix([index*.1,0,0]))
        response = self.client.post('/api/models?filename=scene.glb', content=scene.export(file_type='glb'))
        self.assertEqual(response.status_code, 200, response.text)
        model_id = response.json()['id']
        original,_ = load_scene(server.MODELS[model_id]['path'].read_bytes())
        self.assertEqual(self.client.post('/api/repair', json={'model_id':model_id}).status_code, 422)
        first = self.client.post('/api/repair', json={'model_id':model_id,'part_id':'part-0'})
        self.assertEqual(first.status_code, 200, first.text)
        intermediate,_ = load_scene((server.OUTPUTS/(first.json()['result_id']+'.glb')).read_bytes())
        for part in ('part-1','part-2'):
            np.testing.assert_array_equal(world_mesh(original,part).vertices,world_mesh(intermediate,part).vertices)
            np.testing.assert_array_equal(world_mesh(original,part).faces,world_mesh(intermediate,part).faces)
        second = self.client.post('/api/repair', json={'model_id':model_id,'part_id':'part-1',
                                                     'result_id':first.json()['result_id']})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()['report']['parent_result_id'],first.json()['result_id'])
        output,_ = load_scene((server.OUTPUTS/(second.json()['result_id']+'.glb')).read_bytes())
        self.assertEqual([p['name'] for p in parts(output)], ['a','b','c'])
        for part in ('part-0','part-1','part-2'):
            self.assertTrue(world_mesh(output,part).is_watertight)
        for part in ('part-0','part-2'):
            np.testing.assert_array_equal(world_mesh(intermediate,part).vertices,world_mesh(output,part).vertices)
            np.testing.assert_array_equal(world_mesh(intermediate,part).faces,world_mesh(output,part).faces)

    def test_legacy_result_continuation_and_bundle(self):
        token = 'a'*32
        data = server.MODELS['panel']['path'].read_bytes()
        (server.OUTPUTS/(token+'.glb')).write_bytes(data)
        (server.OUTPUTS/(token+'.json')).write_text(json.dumps({'model_id':'panel'}),encoding='utf-8')
        response = self.client.post('/api/diagnose',json={'model_id':'panel','result_id':token})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.get('/api/results/'+token)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['kind'],'repair')
        with zipfile.ZipFile(server.OUTPUTS/(token+'.zip')) as archive:
            self.assertEqual(archive.read('model.glb'),data)
            self.assertIn('part-1.stl',archive.namelist())

    def test_parameterized_joint_bundle(self):
        response = self.client.post('/api/manufacturing/sample', json={})
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        self.assertTrue(all(p['watertight'] for p in value['report']['parts']))
        self.assertTrue((server.OUTPUTS / (value['result_id']+'.zip')).exists())
        self.assertEqual(len(value['stl_urls']), 2)

    def test_texture_and_history(self):
        response = self.client.post('/api/texture/repair', json={'model_id': 'panel', 'rectangle': [200,200,230,230]})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertTrue(result['report']['outside_mask_preserved'])
        self.assertFalse(result['report']['reference_used'])
        history = self.client.get('/api/history?model_id=panel').json()['history']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['result_id'], result['result_id'])


if __name__ == '__main__':
    unittest.main()
