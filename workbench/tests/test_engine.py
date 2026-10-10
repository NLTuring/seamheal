"""End-to-end geometry invariants; reference meshes are never algorithm inputs."""
import unittest
from pathlib import Path

import numpy as np
import trimesh

from engine.mesh_repair import diagnose_mesh, repair_mesh

ASSETS = Path(__file__).resolve().parents[2] / 'assets/sakura_courtyard/exports'


class RepairTests(unittest.TestCase):
    def test_courtyard_samples(self):
        for name, edges in [('panel', 72), ('roof', 108)]:
            with self.subTest(name=name):
                scene = trimesh.load(ASSETS / f'{name}_damaged.glb', force='scene', process=False)
                original = next(iter(scene.geometry.values()))
                before = diagnose_mesh(original)
                self.assertEqual(before['boundary_edges'], edges)
                self.assertEqual(before['boundary_loops'], 2)
                repaired, report = repair_mesh(original)
                self.assertTrue(report['after']['watertight'])
                self.assertTrue(report['after']['winding_consistent'])
                self.assertEqual(report['after']['degenerate_triangles'], 0)
                self.assertEqual(report['filled_loops'], 2)
                self.assertGreater(report['added_triangles'], 0)
                np.testing.assert_array_equal(repaired.vertices[:len(original.vertices)], original.vertices)
                np.testing.assert_array_equal(repaired.faces[:len(original.faces)], original.faces)
                np.testing.assert_array_equal(repaired.visual.uv[:len(original.vertices)], original.visual.uv)
                # Check the actual exported artifact, including UV and embedded material.
                reloaded = trimesh.load(file_obj=__import__('io').BytesIO(repaired.export(file_type='glb')),
                                        file_type='glb', force='scene', process=False)
                after = diagnose_mesh(next(iter(reloaded.geometry.values())))
                self.assertTrue(after['watertight'])
                self.assertTrue(after['has_uv'])

    def test_generic_box_and_closed_noop(self):
        box = trimesh.creation.box()
        full, report = repair_mesh(box)
        self.assertEqual(report['added_triangles'], 0)
        box.update_faces(np.arange(len(box.faces)) != 0)
        repaired, report = repair_mesh(box)
        self.assertTrue(report['after']['watertight'])
        self.assertTrue(repaired.is_winding_consistent)

    def test_nonmanifold_rejected(self):
        mesh = trimesh.creation.box()
        mesh.faces = np.concatenate([mesh.faces, mesh.faces[:1]])
        with self.assertRaises(ValueError):
            repair_mesh(mesh)

    def test_nonfinite_rejected(self):
        mesh = trimesh.creation.box()
        mesh.vertices[0, 0] = np.nan
        with self.assertRaises(ValueError):
            repair_mesh(mesh)


if __name__ == '__main__':
    unittest.main()
