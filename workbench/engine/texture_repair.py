"""Local texture inpainting using only the supplied image and binary mask.

The two OpenCV predictions are feathered within the selected region: Navier
Stokes at its edge and TELEA toward its interior. Damaged source pixels are
never mixed back into the patch. Every unselected byte and every alpha byte
is retained. This predicts nearby color structure, not original artwork.
"""
from numbers import Integral, Real
from time import perf_counter

import cv2
import numpy as np
from PIL import Image
import trimesh


MAX_TEXTURE_PIXELS = 4096 * 4096
MAX_MASKED_PIXELS = 500_000
MAX_MASK_RATIO = .30
WARNING = '局部纹理补全根据邻近像素预测颜色与花纹，不能保证恢复真实原始花纹；透明通道保持原样。'


def _validate_size(size):
    if (not isinstance(size, (tuple, list)) or len(size) != 2
            or any(isinstance(x, bool) or not isinstance(x, Integral) or x < 1 for x in size)):
        raise ValueError('纹理尺寸必须包含两个正整数。')
    width, height = (int(x) for x in size)
    if width * height > MAX_TEXTURE_PIXELS or max(width, height) > 8192:
        raise ValueError(f'纹理最多支持 {MAX_TEXTURE_PIXELS:,} 个像素，单边不超过 8192。')
    return width, height


def _validate_image(image):
    if not isinstance(image, Image.Image):
        raise ValueError('请传入 PIL 纹理图像。')
    _validate_size(image.size)


def make_mask(size, rectangle=None, uv_rect=None):
    """Build a binary L mask from one pixel rectangle or one UV rectangle.

    ``rectangle=(left, top, right, bottom)`` uses image coordinates and an
    exclusive right/bottom boundary. ``uv_rect=(u0, v0, u1, v1)`` uses UV
    coordinates from 0 to 1 with an origin at the bottom left. The two forms
    are mutually exclusive. This helper permits large selections so the
    caller can display them; repair_texture enforces the repair area limit.
    """
    width, height = _validate_size(size)
    if (rectangle is None) == (uv_rect is None):
        raise ValueError('请指定一个像素矩形或一个 UV 矩形。')
    bounds = rectangle if rectangle is not None else uv_rect
    if (not isinstance(bounds, (tuple, list, np.ndarray)) or len(bounds) != 4
            or any(isinstance(x, bool) or not isinstance(x, Real) or not np.isfinite(x) for x in bounds)):
        raise ValueError('矩形必须包含四个有限坐标。')
    x0, y0, x1, y1 = bounds
    if rectangle is not None:
        if any(int(x) != x for x in bounds) or not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError('像素矩形必须使用图像范围内的整数坐标，且面积大于零。')
        left, top, right, bottom = (int(x) for x in bounds)
    else:
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError('UV 矩形必须位于 0 到 1 之间，且面积大于零。')
        left, right = int(np.floor(x0 * width)), int(np.ceil(x1 * width))
        top, bottom = int(np.floor((1 - y1) * height)), int(np.ceil((1 - y0) * height))
    mask = Image.new('L', (width, height), 0)
    mask.paste(255, (left, top, right, bottom))
    return mask


def repair_texture(image, mask, radius=3):
    """Return ``(repaired_image, report)`` without mutating either input.

    RGB, RGBA, L and LA images are supported. The mask is a same-size PIL
    image in L or 1 mode; 255 selects repair and 0 preserves the pixel.
    Radius is a finite value from 1 to 15 pixels. Empty masks return a copy.
    """
    start = perf_counter()
    _validate_image(image)
    if image.mode not in ('RGB', 'RGBA', 'L', 'LA'):
        raise ValueError('纹理补全支持 RGB、RGBA、L 或 LA 图像。')
    if (not isinstance(mask, Image.Image) or mask.size != image.size
            or mask.mode not in ('L', '1')):
        raise ValueError('蒙版必须是与纹理同尺寸的单通道 L 或 1 图像。')
    if (isinstance(radius, bool) or not isinstance(radius, Real)
            or not np.isfinite(radius) or not 1 <= radius <= 15):
        raise ValueError('补全半径必须是 1 到 15 之间的有限数值。')
    binary = np.asarray(mask.convert('L'))
    if np.any((binary != 0) & (binary != 255)):
        raise ValueError('蒙版必须为二值图：0 保留，255 补全。')
    selected = binary == 255
    count = int(np.count_nonzero(selected))
    fraction = count / selected.size
    if fraction > MAX_MASK_RATIO:
        raise ValueError('补全区域不能超过纹理面积的 30%；请缩小选区或分步处理。')
    if count > MAX_MASKED_PIXELS:
        raise ValueError(f'单次最多补全 {MAX_MASKED_PIXELS:,} 个像素，请缩小选区。')
    report = {
        'masked_pixels': count,
        'masked_fraction': round(fraction, 6),
        'method': 'no-op',
        'radius': float(radius),
        'outside_mask_preserved': True,
        'alpha_preserved': True,
        'warning': WARNING,
        'image_size': list(image.size),
    }
    if count == 0:
        report['elapsed_ms'] = round((perf_counter() - start) * 1000, 2)
        return image.copy(), report

    # Work within the selected bounding box plus a known-pixel collar. This
    # bounds auxiliary allocations for small patches in large textures.
    rows, cols = np.nonzero(selected)
    padding = int(np.ceil(radius)) * 3 + 3
    top, bottom = max(0, int(rows.min()) - padding), min(image.height, int(rows.max()) + padding + 1)
    left, right = max(0, int(cols.min()) - padding), min(image.width, int(cols.max()) + padding + 1)
    original = np.asarray(image)
    region = original[top:bottom, left:right]
    local_mask = np.ascontiguousarray(binary[top:bottom, left:right])
    if image.mode == 'LA':
        color = np.ascontiguousarray(region[:, :, 0])
    elif image.mode == 'RGBA':
        color = np.ascontiguousarray(region[:, :, :3])
    else:
        color = np.ascontiguousarray(region)

    telea = cv2.inpaint(color, local_mask, float(radius), cv2.INPAINT_TELEA)
    navier_stokes = cv2.inpaint(color, local_mask, float(radius), cv2.INPAINT_NS)
    distance = cv2.distanceTransform(local_mask, cv2.DIST_L2, 3)
    weight = np.clip((distance - .9) / max(float(radius), 1.), 0, 1)
    # Smoothstep avoids an abrupt transition between the two predictions.
    weight = weight * weight * (3 - 2 * weight)
    if color.ndim == 3:
        weight = weight[:, :, None]
    prediction = np.rint(telea.astype(np.float32) * weight
                         + navier_stokes.astype(np.float32) * (1 - weight)).clip(0, 255).astype(np.uint8)
    result = original.copy()
    region_result = result[top:bottom, left:right]
    local_selected = local_mask == 255
    if image.mode == 'LA':
        region_result[:, :, 0][local_selected] = prediction[local_selected]
    elif image.mode == 'RGBA':
        region_result[:, :, :3][local_selected] = prediction[local_selected]
    else:
        region_result[local_selected] = prediction[local_selected]
    report['method'] = 'OpenCV TELEA + Navier-Stokes, feathered inside mask'
    report['elapsed_ms'] = round((perf_counter() - start) * 1000, 2)
    return Image.fromarray(result), report


def _basecolor_source(mesh):
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError('请选择单个网格后处理纹理。')
    material = getattr(mesh.visual, 'material', None)
    source = getattr(material, 'baseColorTexture', None)
    if source is None:
        source = getattr(material, 'image', None)
    if not isinstance(source, Image.Image):
        raise ValueError('所选网格没有可补全的底色纹理。')
    _validate_image(source)
    return source


def texture_image(mesh):
    """Return an independent RGB/RGBA copy of a PBR or simple base texture."""
    source = _basecolor_source(mesh)
    has_alpha = 'A' in source.getbands() or 'transparency' in source.info
    return source.convert('RGBA' if has_alpha else 'RGB')


def replace_basecolor(mesh, image):
    """Copy a mesh, replace base color, and keep alpha and other channels.

    UVs, vertex normals, material factors and all non-base-color textures
    remain intact. Replacement dimensions must match the existing texture.
    Original texture alpha is retained even if a supplied image changes it.
    """
    source = texture_image(mesh)
    _validate_image(image)
    if image.size != source.size:
        raise ValueError('新纹理尺寸必须与原底色纹理一致。')
    replacement = image.convert(source.mode)
    if source.mode == 'RGBA':
        replacement.putalpha(source.getchannel('A'))
    output = mesh.copy(include_cache=True)
    material = output.visual.material
    if hasattr(material, 'baseColorTexture'):
        material.baseColorTexture = replacement
    else:
        material.image = replacement
    return output
