"""Manufacturing checks use actual geometry and dimensional tolerances."""
import unittest

import numpy as np
import trimesh

from engine.manufacturing import make_joint_sample, print_check, split_with_joint


class PrintCheckTests(unittest.TestCase):
    def test_dimensions_volume_and_bed_contact(self):
        mesh = trimesh.creation.box(extents=[.06, .03, .012])
        report = print_check(mesh)
        np.testing.assert_allclose(report['dimensions_mm'], [60, 30, 12])
        self.assertAlmostEqual(report['volume_mm3'], 21600)
        self.assertTrue(report['watertight'])
        self.assertTrue(report['fits_build_volume'])
        self.assertEqual(report['overhang']['area_ratio'], 0)
        self.assertAlmostEqual(report['wall_thickness']['sampled_min_mm'], 12, places=4)
        self.assertEqual(report['self_intersection']['status'], 'checked')
        self.assertEqual(report['self_intersection']['intersection_pairs'], 0)

    def test_thin_wall_and_units(self):
        report = print_check(trimesh.creation.box(extents=[20, 20, .4]), units='mm')
        self.assertGreater(report['wall_thickness']['below_minimum_samples'], 0)
        self.assertFalse(report['passes_checked_constraints'])

    def test_open_mesh_is_reported(self):
        box = trimesh.creation.box()
        box.update_faces(np.arange(12) != 0)
        report = print_check(box)
        self.assertFalse(report['watertight'])
        self.assertIsNone(report['volume_mm3'])
        self.assertEqual(report['wall_thickness']['status'], 'not_checked')

    def test_overhang_excludes_only_bed_contact(self):
        bottom = trimesh.creation.box(extents=[.01, .01, .01])
        top = trimesh.creation.box(extents=[.03, .03, .005])
        top.apply_translation([0, 0, .015])
        report = print_check(trimesh.util.concatenate([bottom, top]))
        self.assertGreater(report['overhang']['area_ratio'], 0)

    def test_print_parameter_validation(self):
        for kwargs in ({'units': 'feet'}, {'minimum_wall_mm': 0},
                       {'build_volume_mm': [1, 2]}, {'overhang_angle_deg': 95},
                       {'minimum_wall_mm': float('nan')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                print_check(trimesh.creation.box(), **kwargs)


class JointTests(unittest.TestCase):
    def setUp(self):
        self.box = trimesh.creation.box(extents=[.06, .03, .012])
        self.box.apply_translation([1, 2, 3])

    def test_plain_split_volume_and_coordinates(self):
        scene, report = split_with_joint(self.box, joint='none', clearance_mm=0)
        self.assertEqual(len(scene.geometry), 2)
        self.assertTrue(all(m.is_volume for m in scene.geometry.values()))
        self.assertAlmostEqual(sum(m.volume for m in scene.geometry.values()), self.box.volume)
        np.testing.assert_allclose(scene.bounds, self.box.bounds)
        self.assertEqual(report['joint'], 'none')

    def test_dovetail_is_disjoint_closed_and_with_clearance(self):
        scene, report = split_with_joint(self.box, clearance_mm=.2)
        a, b = scene.geometry.values()
        self.assertTrue(a.is_volume and b.is_volume)
        self.assertGreater(report['joint_depth_mm'], 0)
        self.assertGreaterEqual(report['measured_gap_mm'], .199)
        self.assertLess(report['output_volume_mm3'], report['input_volume_mm3'])
        self.assertLess(report['removed_volume_mm3'], report['input_volume_mm3'] * .05)
        overlap = trimesh.boolean.intersection([a, b], engine='manifold')
        self.assertEqual(len(overlap.faces), 0)
        np.testing.assert_allclose(scene.bounds, self.box.bounds)

    def test_all_axes_and_sample_parameters(self):
        for axis in ('x', 'y', 'z'):
            scene, report = split_with_joint(trimesh.creation.box(extents=[.06]*3), axis=axis)
            self.assertEqual(len(scene.geometry), 2)
            self.assertGreaterEqual(report['measured_gap_mm'], .199)
        scene, report = make_joint_sample(width_mm=80, depth_mm=35, height_mm=10,
                                          clearance_mm=.3, angle_deg=18)
        np.testing.assert_allclose(scene.extents * 1000, [80, 35, 10])
        self.assertEqual(report['angle_deg'], 18)
        male = next(iter(scene.geometry.values()))
        normals = male.face_normals
        flank = normals[(np.abs(normals[:, 0]) > .01) & (np.abs(normals[:, 1]) > .01)]
        self.assertGreater(len(flank), 0)
        actual_angles = np.rad2deg(np.arctan2(np.abs(flank[:, 0]), np.abs(flank[:, 1])))
        np.testing.assert_allclose(actual_angles, 18, atol=1e-4)

    def test_reject_invalid_joint_and_parameters(self):
        for kwargs in ({'axis': 'a'}, {'fraction': 0}, {'fraction': 1},
                       {'fraction': float('nan')}, {'joint': 'magic'},
                       {'clearance_mm': -.2}, {'clearance_mm': 20},
                       {'units': 'feet'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                split_with_joint(self.box, **kwargs)
        for kwargs in ({'width_mm': 0}, {'height_mm': float('inf')},
                       {'angle_deg': 0}, {'angle_deg': 60}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                make_joint_sample(**kwargs)

    def test_reject_nonclosed_multiple_shell_and_unsafe_host(self):
        open_box = self.box.copy()
        open_box.update_faces(np.arange(12) != 0)
        second = self.box.copy()
        second.apply_translation([.1, 0, 0])
        for mesh in (open_box, trimesh.util.concatenate([self.box, second]),
                     trimesh.creation.icosphere(radius=.03)):
            with self.subTest(mesh=mesh), self.assertRaises(ValueError):
                split_with_joint(mesh)


if __name__ == '__main__':
    unittest.main()
