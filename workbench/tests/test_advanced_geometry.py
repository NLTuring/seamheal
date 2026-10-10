import unittest
from pathlib import Path
import numpy as np
import trimesh
from engine.mesh_repair import repair_advanced_mesh, _constrained_patch
from engine.quality import compare_reference


class AdvancedTests(unittest.TestCase):
    def test_cleanup_duplicates_degenerates_and_winding(self):
        mesh = trimesh.creation.box()
        faces = mesh.faces.copy(); faces[0] = faces[0,::-1]
        mesh.faces = np.concatenate([faces,faces[:1],[[0,0,1]]])
        fixed,report = repair_advanced_mesh(mesh)
        self.assertTrue(report['after']['watertight'])
        self.assertTrue(report['after']['winding_consistent'])
        self.assertEqual(report['cleanup']['removed_duplicate_faces'],1)
        self.assertEqual(report['cleanup']['removed_degenerate_faces'],1)
        np.testing.assert_array_equal(fixed.vertices,mesh.vertices)

    def test_concave_polygon_retains_collinear_boundary(self):
        ring = np.array([[0,0],[1,0],[2,0],[2,2],[1,1],[0,2]],dtype=float)
        points,faces = _constrained_patch(ring)
        edges = np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1)
        unique,counts = np.unique(edges,axis=0,return_counts=True)
        self.assertEqual({tuple(e) for e in unique[counts==1]},
                         {tuple(sorted((i,(i+1)%len(ring)))) for i in range(len(ring))})

    def test_seam_does_not_worsen_or_move_original(self):
        path = Path(__file__).resolve().parents[2]/'assets/sakura_courtyard/exports/roof_damaged.glb'
        mesh = next(iter(trimesh.load(path,force='scene',process=False).geometry.values()))
        result,report = repair_advanced_mesh(mesh)
        self.assertEqual(report['seam_after']['edge_count'],108)
        self.assertLessEqual(report['seam_after']['mean_angle_deg'],report['seam_before']['mean_angle_deg']+1e-8)
        self.assertLessEqual(report['seam_after']['max_angle_deg'],report['seam_before']['max_angle_deg']+1e-8)
        np.testing.assert_array_equal(result.vertices[:len(mesh.vertices)],mesh.vertices)
        np.testing.assert_array_equal(result.visual.uv[:len(mesh.vertices)],mesh.visual.uv)

    def test_reference_evaluation_is_deterministic(self):
        mesh = trimesh.creation.box()
        same = compare_reference(mesh,mesh,samples=32)
        self.assertLess(same['max_distance'],1e-12)
        shifted = mesh.copy(); shifted.apply_translation([.05,0,0])
        first = compare_reference(mesh,shifted,samples=32)
        self.assertEqual(first,compare_reference(mesh,shifted,samples=32))
        self.assertGreater(first['max_distance'],.04)


if __name__=='__main__': unittest.main()
