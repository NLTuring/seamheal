"""Texture restoration invariants, including masks and material round trips."""
import io
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
import trimesh
from trimesh.visual.material import PBRMaterial, SimpleMaterial

from engine.texture_repair import (
    make_mask, repair_texture, replace_basecolor, texture_image,
)


class TextureRepairTests(unittest.TestCase):
    def setUp(self):
        self.pixels = np.full((64, 64, 3), [168, 122, 76], dtype=np.uint8)
        self.mask = make_mask((64, 64), rectangle=(26, 26, 38, 38))
        self.selected = np.asarray(self.mask) == 255
        self.pixels[self.selected] = 0
        self.image = Image.fromarray(self.pixels)

    def test_real_inpainting_preserves_all_unselected_pixels(self):
        result, report = repair_texture(self.image, self.mask)
        restored = np.asarray(result)
        self.assertGreater(float(restored[self.selected].mean()), 110)
        self.assertLess(float(np.abs(restored[self.selected].astype(float) - [168, 122, 76]).mean()), 6)
        np.testing.assert_array_equal(restored[~self.selected], self.pixels[~self.selected])
        np.testing.assert_array_equal(np.asarray(self.image), self.pixels)
        self.assertEqual(report['masked_pixels'], 144)
        self.assertTrue(report['outside_mask_preserved'])
        self.assertIn('TELEA', report['method'])
        self.assertIn('预测', report['warning'])

    def test_alpha_preserved_inside_and_outside_mask(self):
        alpha = np.arange(4096, dtype=np.uint8).reshape((64, 64))
        source = np.dstack([self.pixels, alpha])
        result, report = repair_texture(Image.fromarray(source), self.mask, radius=2.5)
        self.assertEqual(result.mode, 'RGBA')
        np.testing.assert_array_equal(np.asarray(result)[:, :, 3], alpha)
        self.assertTrue(report['alpha_preserved'])
        self.assertGreater(np.asarray(result)[self.selected, :3].mean(), 110)

    def test_grayscale_and_grayscale_alpha_supported(self):
        for mode in ('L', 'LA'):
            with self.subTest(mode=mode):
                source = self.image.convert(mode)
                result, _ = repair_texture(source, self.mask)
                self.assertEqual(result.mode, mode)
                np.testing.assert_array_equal(np.asarray(result)[~self.selected], np.asarray(source)[~self.selected])

    def test_empty_mask_is_copy_without_changes(self):
        result, report = repair_texture(self.image, Image.new('L', self.image.size))
        np.testing.assert_array_equal(np.asarray(result), self.pixels)
        self.assertIsNot(result, self.image)
        self.assertEqual(report['masked_pixels'], 0)
        self.assertEqual(report['method'], 'no-op')

    def test_rejects_full_mask_and_more_than_thirty_percent(self):
        for mask in (Image.new('L', (64, 64), 255), make_mask((64, 64), rectangle=(0, 0, 32, 64))):
            with self.assertRaisesRegex(ValueError, '30%'):
                repair_texture(self.image, mask)

    def test_rejects_bad_mask_dimensions_mode_and_values(self):
        for mask in (Image.new('L', (32, 32)), Image.new('RGB', (64, 64)), Image.new('L', (64, 64), 127)):
            with self.subTest(mode=mask.mode, size=mask.size):
                with self.assertRaises(ValueError):
                    repair_texture(self.image, mask)

    def test_binary_mode_mask_and_edge_region(self):
        edge_mask = make_mask((64, 64), rectangle=(0, 0, 5, 5)).convert('1')
        result, report = repair_texture(self.image, edge_mask)
        self.assertEqual(report['masked_pixels'], 25)
        self.assertEqual(result.size, self.image.size)

    def test_rejects_invalid_radius_and_image_mode(self):
        for radius in (0, -1, 16, float('nan'), float('inf'), True, '3'):
            with self.subTest(radius=radius):
                with self.assertRaises(ValueError):
                    repair_texture(self.image, self.mask, radius=radius)
        with self.assertRaises(ValueError):
            repair_texture(self.image.convert('CMYK'), self.mask)
        with self.assertRaises(ValueError):
            repair_texture(self.pixels, self.mask)

    def test_resource_limits_checked(self):
        with patch('engine.texture_repair.MAX_TEXTURE_PIXELS', 100):
            with self.assertRaisesRegex(ValueError, '像素'):
                repair_texture(self.image, self.mask)
            with self.assertRaises(ValueError):
                make_mask((64, 64), rectangle=(0, 0, 1, 1))
        with patch('engine.texture_repair.MAX_MASKED_PIXELS', 100):
            with self.assertRaisesRegex(ValueError, '像素'):
                repair_texture(self.image, self.mask)

    def test_pixel_rectangle_is_half_open_and_uv_origin_is_bottom(self):
        mask = make_mask((8, 8), rectangle=(1, 2, 4, 5))
        self.assertEqual(np.count_nonzero(mask), 9)
        self.assertEqual(np.asarray(mask)[2, 1], 255)
        self.assertEqual(np.asarray(mask)[5, 4], 0)
        uv_mask = np.asarray(make_mask((8, 8), uv_rect=(0, 0, .5, .5)))
        self.assertEqual(np.count_nonzero(uv_mask), 16)
        self.assertTrue(np.all(uv_mask[4:, :4] == 255))
        self.assertTrue(np.all(uv_mask[:4] == 0))

    def test_rejects_ambiguous_or_out_of_range_rectangles(self):
        cases = [
            {}, {'rectangle': (0, 0, 1, 1), 'uv_rect': (0, 0, 1, 1)},
            {'rectangle': (-1, 0, 1, 1)}, {'rectangle': (0, 0, 9, 1)},
            {'rectangle': (0, 0, 0, 1)}, {'rectangle': (0, 0, .5, 1)},
            {'rectangle': (0, 0, 1)}, {'uv_rect': (0, 0, 1.1, 1)},
            {'uv_rect': (0, 0, float('nan'), 1)},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    make_mask((8, 8), **kwargs)
        for size in ((0, 1), (4.5, 8), (True, 8), (8,)):
            with self.assertRaises(ValueError):
                make_mask(size, rectangle=(0, 0, 1, 1))


class TextureMaterialTests(unittest.TestCase):
    def setUp(self):
        self.mesh = trimesh.creation.box()
        pixels = np.zeros((16, 16, 4), dtype=np.uint8)
        pixels[:, :, :3] = [20, 30, 40]
        pixels[:, :, 3] = np.arange(256, dtype=np.uint8).reshape(16, 16)
        self.source = Image.fromarray(pixels)
        material = PBRMaterial(
            name='Preserve all channels', baseColorTexture=self.source,
            baseColorFactor=[128, 160, 192, 230], metallicFactor=.3, roughnessFactor=.7,
            normalTexture=Image.new('RGB', (16, 16), (128, 128, 255)),
            metallicRoughnessTexture=Image.new('RGB', (16, 16), (255, 80, 40)),
            emissiveTexture=Image.new('RGB', (16, 16), (10, 20, 30)),
            occlusionTexture=Image.new('L', (16, 16), 180),
            alphaMode='MASK', alphaCutoff=.2, doubleSided=True,
        )
        self.mesh.visual = trimesh.visual.texture.TextureVisuals(
            uv=np.zeros((len(self.mesh.vertices), 2)), material=material,
        )

    def test_basecolor_replacement_preserves_material_geometry_uv_and_alpha(self):
        original_normals = self.mesh.vertex_normals.copy()
        output = replace_basecolor(self.mesh, Image.new('RGB', (16, 16), 'red'))
        self.assertIsNot(output, self.mesh)
        np.testing.assert_array_equal(output.vertices, self.mesh.vertices)
        np.testing.assert_array_equal(output.faces, self.mesh.faces)
        np.testing.assert_array_equal(output.visual.uv, self.mesh.visual.uv)
        np.testing.assert_allclose(output.vertex_normals, original_normals)
        np.testing.assert_array_equal(np.asarray(texture_image(self.mesh)), np.asarray(self.source))
        replaced = np.asarray(texture_image(output))
        np.testing.assert_array_equal(replaced[:, :, 3], np.asarray(self.source)[:, :, 3])
        self.assertTrue(np.all(replaced[:, :, 0] == 255))
        for field in ('baseColorFactor', 'metallicFactor', 'roughnessFactor', 'alphaMode', 'alphaCutoff', 'doubleSided', 'name'):
            np.testing.assert_equal(getattr(output.visual.material, field), getattr(self.mesh.visual.material, field))
        for field in ('normalTexture', 'metallicRoughnessTexture', 'emissiveTexture', 'occlusionTexture'):
            np.testing.assert_array_equal(np.asarray(getattr(output.visual.material, field)), np.asarray(getattr(self.mesh.visual.material, field)))
        reloaded = trimesh.load(io.BytesIO(output.export(file_type='glb')), file_type='glb', force='scene', process=False)
        loaded = next(iter(reloaded.geometry.values()))
        np.testing.assert_array_equal(np.asarray(texture_image(loaded)), replaced)
        self.assertEqual(loaded.visual.material.alphaMode, 'MASK')

    def test_simple_material_and_defensive_image_copy(self):
        self.mesh.visual.material = SimpleMaterial(image=Image.new('RGB', (16, 16), 'blue'))
        extracted = texture_image(self.mesh)
        extracted.putpixel((0, 0), (255, 0, 0))
        self.assertEqual(texture_image(self.mesh).getpixel((0, 0)), (0, 0, 255))
        output = replace_basecolor(self.mesh, Image.new('RGB', (16, 16), 'green'))
        self.assertEqual(texture_image(output).getpixel((0, 0)), (0, 128, 0))

    def test_missing_texture_wrong_mesh_and_dimension_rejected(self):
        for mesh in (trimesh.creation.box(), trimesh.Scene()):
            with self.assertRaises(ValueError):
                texture_image(mesh)
        with self.assertRaises(ValueError):
            replace_basecolor(self.mesh, Image.new('RGB', (8, 8)))


if __name__ == '__main__':
    unittest.main()
