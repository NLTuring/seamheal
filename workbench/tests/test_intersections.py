import unittest
import numpy as np
import trimesh
from engine.intersections import self_intersections


class IntersectionTests(unittest.TestCase):
    def test_closed_box_has_no_nonadjacent_intersections(self):
        result=self_intersections(trimesh.creation.box())
        self.assertEqual(result['status'],'checked')
        self.assertEqual(result['intersection_pairs'],0)

    def test_crossing_and_coplanar_triangles(self):
        a=np.array([[0,0,0],[2,0,0],[0,2,0]])
        for b in [np.array([[.5,.5,-1],[.5,.5,1],[1.5,.5,0]]),a+[.3,.3,0]]:
            mesh=trimesh.Trimesh(vertices=np.concatenate([a,b]),faces=[[0,1,2],[3,4,5]],process=False)
            self.assertEqual(self_intersections(mesh)['intersection_pairs'],1)
        shifted=trimesh.Trimesh(vertices=np.concatenate([a,a+[3,0,0]]),faces=[[0,1,2],[3,4,5]],process=False)
        self.assertEqual(self_intersections(shifted)['intersection_pairs'],0)

    def test_budget_is_not_reported_as_pass(self):
        mesh=trimesh.util.concatenate([trimesh.creation.box(),trimesh.creation.box(transform=trimesh.transformations.translation_matrix([.1,.1,.1]))])
        self.assertEqual(self_intersections(mesh,max_pairs=0)['status'],'partial')
