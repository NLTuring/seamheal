"""Dimensional print checks and closed solid dovetail subdivision.

Geometry is checked in millimetres. Boolean output returns to the input world
coordinates. Reports describe the checks performed; they are not strength
certificates or a replacement for a slicer/material test.
"""
from itertools import permutations

import numpy as np
import trimesh
from shapely.geometry import Polygon
from .intersections import self_intersections


_MM_PER_UNIT = {'m': 1000., 'cm': 10., 'mm': 1.}


def _number(value, name, low=None, high=None, inclusive_low=False):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name}必须为有限数值。') from exc
    if not np.isfinite(number):
        raise ValueError(f'{name}必须为有限数值。')
    if low is not None and (number < low if inclusive_low else number <= low):
        raise ValueError(f'{name}超出允许范围。')
    if high is not None and number > high:
        raise ValueError(f'{name}超出允许范围。')
    return number


def _mesh_mm(mesh, units):
    if units not in _MM_PER_UNIT:
        raise ValueError('单位必须为 m、cm 或 mm。')
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
        raise ValueError('模型中没有可处理的三角面。')
    if len(mesh.faces) > 500_000 or len(mesh.vertices) > 600_000:
        raise ValueError('制造工具支持最多 50 万个三角面，请先简化模型。')
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    if not np.isfinite(vertices).all() or faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError('模型包含无效坐标或三角面索引。')
    scale = _MM_PER_UNIT[units]
    center = (vertices.min(axis=0) + vertices.max(axis=0)) * .5
    points = (vertices - center) * scale
    extent = float(np.max(np.ptp(points, axis=0)))
    if extent <= 1e-6 or extent > 1e7:
        raise ValueError('模型尺寸超出 0.000001–10000000 mm 的处理范围，请检查单位。')
    # GLB splits positions at UV seams. Weld only the working geometry copy.
    _, representatives, inverse = np.unique(
        np.round(points / (extent * 1e-9)).astype(np.int64),
        axis=0, return_index=True, return_inverse=True)
    result = trimesh.Trimesh(vertices=points[representatives], faces=inverse[faces], process=False)
    if np.any(result.area_faces < extent * extent * 1e-16):
        raise ValueError('模型包含退化三角面，请先清理网格。')
    return result, center, scale


def _sample_thickness(mesh, minimum):
    """Nearest inward ray hits at deterministic area weighted face centroids."""
    limitation = '面心向内射线抽样估计；抽样最小值可能高于真实最小壁厚，无法排除未采样薄壁。'
    if not mesh.is_volume:
        return {'status': 'not_checked', 'samples': 0, 'sampled_min_mm': None,
                'sampled_median_mm': None, 'below_minimum_samples': 0,
                'method': 'inward_face_rays', 'limitation': limitation,
                'reason': '需要闭合、朝外且绕序一致的实体。'}
    if len(mesh.faces) > 100_000:
        return {'status': 'not_checked', 'samples': 0, 'sampled_min_mm': None,
                'sampled_median_mm': None, 'below_minimum_samples': 0,
                'method': 'inward_face_rays', 'limitation': limitation,
                'reason': '壁厚射线检查限 10 万面，当前模型仅执行其余打印检查。'}
    areas = mesh.area_faces
    count = min(96, len(areas))
    cumulative = np.cumsum(areas)
    indices = np.unique(np.searchsorted(cumulative, (np.arange(count) + .5) / count * cumulative[-1]))
    triangles = mesh.triangles
    edge1, edge2 = triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    epsilon = max(float(np.max(mesh.extents)) * 1e-8, 1e-7)
    thicknesses = []
    for index in indices:
        direction = -mesh.face_normals[index]
        origin = mesh.triangles_center[index] + direction * epsilon
        cross = np.cross(np.broadcast_to(direction, edge2.shape), edge2)
        determinant = np.einsum('ij,ij->i', edge1, cross)
        valid = np.abs(determinant) > 1e-12
        inverse = np.zeros_like(determinant)
        inverse[valid] = 1. / determinant[valid]
        offset = origin - triangles[:, 0]
        u = np.einsum('ij,ij->i', offset, cross) * inverse
        q = np.cross(offset, edge1)
        v = (q @ direction) * inverse
        distance = np.einsum('ij,ij->i', edge2, q) * inverse
        hit = valid & (u >= -1e-8) & (v >= -1e-8) & (u + v <= 1. + 1e-8) & (distance > epsilon)
        hit[index] = False
        if hit.any():
            thicknesses.append(float(np.min(distance[hit]) + epsilon))
    values = np.asarray(thicknesses)
    return {'status': 'estimated' if len(values) else 'not_checked',
            'method': 'inward_face_rays', 'samples': len(values),
            'attempted_samples': len(indices),
            'sampled_min_mm': float(values.min()) if len(values) else None,
            'sampled_median_mm': float(np.median(values)) if len(values) else None,
            'below_minimum_samples': int(np.sum(values < minimum)),
            'minimum_wall_mm': minimum, 'limitation': limitation}


def print_check(mesh_world, minimum_wall_mm=1.0, build_volume_mm=(220, 220, 250),
                units='m', overhang_angle_deg=45):
    """Return measured print constraints for the current orientation (+Z up)."""
    minimum = _number(minimum_wall_mm, '最小壁厚', 0, 10000)
    angle = _number(overhang_angle_deg, '悬垂角度', 0, 89.9)
    try:
        build = np.asarray(build_volume_mm, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError('打印空间必须为三个正数，单位 mm。') from exc
    if build.shape != (3,) or not np.isfinite(build).all() or (build <= 0).any():
        raise ValueError('打印空间必须为三个正数，单位 mm。')
    mesh, _, _ = _mesh_mm(mesh_world, units)
    dimensions = mesh.extents
    watertight, winding = bool(mesh.is_watertight), bool(mesh.is_winding_consistent)
    outward = bool(watertight and winding and mesh.volume > 0)
    fits = bool(np.all(dimensions <= build + 1e-7))
    fits_rotated = any(np.all(dimensions[list(order)] <= build + 1e-7) for order in permutations(range(3)))
    bed_epsilon = max(float(np.max(dimensions)) * 1e-7, 1e-6)
    on_bed = np.all(mesh.triangles[:, :, 2] <= mesh.bounds[0, 2] + bed_epsilon, axis=1)
    overhang = (mesh.face_normals[:, 2] < -np.sin(np.deg2rad(angle))) & ~on_bed
    overhang_area = float(mesh.area_faces[overhang].sum())
    wall = _sample_thickness(mesh, minimum)
    warnings = []
    if not watertight:
        warnings.append('模型未闭合，体积和壁厚结果不可用，请先修复。')
    if not outward:
        warnings.append('未确认一致朝外的封闭实体；请检查面朝向。')
    if not fits:
        warnings.append('当前朝向超出打印空间。' + ('可尝试轴向旋转。' if fits_rotated else '建议缩放或分块。'))
    if wall['below_minimum_samples']:
        warnings.append('射线抽样发现低于设定最小壁厚的位置。')
    if overhang_area > 0:
        warnings.append('存在超过设定角度的悬垂面，请在切片器中检查支撑。')
    intersections = self_intersections(mesh)
    if intersections['intersection_pairs']:
        warnings.append(f"发现 {intersections['intersection_pairs']} 对非相邻三角面相交或接触，需处理后再打印。")
    if intersections['status'] != 'checked':
        warnings.append('非相邻面相交检查未覆盖全部候选面，未检查部分需要复核。')
    warnings.append('相邻面重叠、打印材料标定与有限元强度分析不在本次检查范围内。')
    return {
        'units': units, 'dimensions_mm': dimensions.tolist(), 'build_volume_mm': build.tolist(),
        'watertight': watertight, 'winding_consistent': winding, 'outward_normals': outward,
        'volume_mm3': float(mesh.volume) if outward else None,
        'surface_area_mm2': float(mesh.area), 'fits_build_volume': fits,
        'fits_with_axis_rotation': bool(fits_rotated), 'minimum_wall_mm': minimum,
        'passes_checked_constraints': bool(outward and fits and wall['status'] == 'estimated'
                                          and wall['below_minimum_samples'] == 0 and overhang_area == 0
                                          and intersections['status']=='checked' and intersections['intersection_pairs']==0),
        'overhang': {'area_ratio': overhang_area / float(mesh.area), 'area_mm2': overhang_area,
                     'triangle_count': int(overhang.sum()), 'angle_deg': angle, 'build_axis': 'z',
                     'bed_contact_excluded': True,
                     'method': '当前 +Z 打印方向，向下法向与竖直墙面偏角超过阈值；排除最低平面接触面。'},
        'wall_thickness': wall, 'self_intersection': intersections,
        'strength': {'status': 'not_calibrated'}, 'warnings': warnings,
    }


def _manifold(mesh):
    try:
        import manifold3d as md
    except ImportError as exc:
        raise ValueError('缺少 manifold3d，请安装 requirements-manufacturing.txt。') from exc
    solid = md.Manifold(md.Mesh(np.asarray(mesh.vertices, dtype=np.float32),
                                np.asarray(mesh.faces, dtype=np.uint32)))
    if solid.status() != md.Error.NoError or solid.is_empty():
        raise ValueError('布尔内核拒绝此网格，请先修复闭合性与面朝向。')
    return solid


def _prism(polygon, z_min, z_max):
    import manifold3d as md
    # Shapely buffers can reverse ring winding; explicitly request even/odd fill.
    return md.CrossSection([np.asarray(polygon.exterior.coords)[:-1]],
                           md.FillRule.EvenOdd).extrude(z_max - z_min).translate([0, 0, z_min])


def _world_mesh(solid, order, center, scale, color):
    raw = solid.to_mesh()
    vertices = np.empty((len(raw.vert_properties), 3))
    vertices[:, order] = np.asarray(raw.vert_properties[:, :3])
    mesh = trimesh.Trimesh(vertices=vertices / scale + center,
                           faces=np.asarray(raw.tri_verts), process=False)
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, face_colors=color)
    return mesh


def split_with_joint(mesh_world, axis='x', fraction=.5, joint='dovetail',
                     clearance_mm=.2, units='m', angle_deg=12):
    """Cut a closed single shell and optionally add a through sliding dovetail.

    Dovetails require an uninterrupted solid corridor along the slide axis.
    This condition is verified with a solid difference, so thin/curved/holed
    hosts are rejected instead of silently generating an unsafe connection.
    """
    if axis not in ('x', 'y', 'z'):
        raise ValueError('切分轴必须为 x、y 或 z。')
    ratio = _number(fraction, '切分比例', 0, 1)
    if ratio >= 1:
        raise ValueError('切分比例必须严格位于 0 和 1 之间。')
    clearance = _number(clearance_mm, '装配间隙', 0, 5, inclusive_low=True)
    angle = _number(angle_deg, '燕尾角度', 1, 35, inclusive_low=True)
    if joint not in ('none', 'dovetail'):
        raise ValueError('支持的接头为 none 或 dovetail。')
    mesh, center, scale = _mesh_mm(mesh_world, units)
    if not mesh.is_volume:
        raise ValueError('分块需要闭合、朝外且绕序一致的实体，请先修复模型。')
    if len(mesh.split(only_watertight=False)) != 1:
        raise ValueError('分块装配当前需要单个连通封闭实体，请选择一个独立部件。')
    axis_index = 'xyz'.index(axis)
    order = [axis_index, (axis_index + 1) % 3, (axis_index + 2) % 3]
    local = trimesh.Trimesh(vertices=mesh.vertices[:, order], faces=mesh.faces, process=False)
    low, high = local.bounds
    size = high - low
    cut = float(low[0] + size[0] * ratio)
    if min(cut - low[0], high[0] - cut) <= max(clearance, .05):
        raise ValueError('切分位置距边缘过近或间隙过大，无法生成两个有效部件。')
    solid = _manifold(local)
    _, left = solid.split_by_plane([1, 0, 0], cut - clearance / 2)
    right, _ = solid.split_by_plane([1, 0, 0], cut + clearance / 2)
    joint_depth = 0.
    safety_wall = 0.
    if joint == 'dovetail':
        safety_wall = max(1., clearance * 3)
        joint_depth = min((cut - low[0]) * .3, (high[0] - cut) * .3, size[1] * .22)
        neck_width = min(size[1] * .24, joint_depth * 1.5)
        embed = min(1., joint_depth * .2)
        # Include the embedded neck in the flank run so the exported angle
        # equals the requested angle, including nonzero assembly clearance.
        flank_run = joint_depth + clearance / 2 + embed
        tip_width = neck_width + 2 * flank_run * np.tan(np.deg2rad(angle))
        if (joint_depth < max(2., clearance * 5) or neck_width < 2 * safety_wall
                or tip_width + 2 * (clearance + safety_wall) >= size[1]
                or size[2] < max(2., clearance * 5)):
            raise ValueError('切分区域空间不足，无法布置具有安全厚度的燕尾，请调整切分位置或尺寸。')
        tongue_polygon = Polygon([(cut - clearance / 2 - embed, -neck_width / 2),
                                  (cut + joint_depth, -tip_width / 2),
                                  (cut + joint_depth, tip_width / 2),
                                  (cut - clearance / 2 - embed, neck_width / 2)])
        socket_polygon = tongue_polygon.buffer(clearance, join_style='mitre') if clearance else tongue_polygon
        envelope_polygon = socket_polygon.buffer(safety_wall, join_style='mitre')
        envelope = _prism(envelope_polygon, low[2], high[2])
        missing = float((envelope - solid).volume())
        if missing > max(float(envelope.volume()) * 1e-5, 1e-5):
            raise ValueError('该切面缺少贯穿的实体燕尾安装区（可能为曲面、薄壁或带孔结构），请选择其他切面或无接头分块。')
        tongue = _prism(tongue_polygon, low[2], high[2])
        socket = _prism(socket_polygon, low[2] - 1, high[2] + 1)
        left = left + tongue
        right = right - socket
    solids = [left, right]
    if any(part.is_empty() or len(part.decompose()) != 1 for part in solids):
        raise ValueError('切分产生空部件或碎片，请调整切分轴、位置或接头。')
    overlap_volume = float((left ^ right).volume())
    if overlap_volume > max(solid.volume() * 1e-7, 1e-6):
        raise ValueError('装配部件存在实体重叠，已停止输出。')
    gap = float(left.min_gap(right, max(1., clearance * 2)))
    if clearance and gap < clearance * .98:
        raise ValueError('实际装配间隙低于要求，已停止输出。')
    scene, part_reports = trimesh.Scene(), []
    for index, (part, color) in enumerate(zip(solids, ([83, 174, 187, 255], [235, 158, 95, 255]))):
        name = 'part_a_male' if index == 0 else 'part_b_female'
        output = _world_mesh(part, order, center, scale, color)
        if not output.is_volume:
            raise ValueError('输出部件未通过封闭实体校验，已停止输出。')
        scene.add_geometry(output, geom_name=name, node_name=name)
        part_reports.append({'name': name, 'triangles': len(output.faces), 'watertight': True,
                             'volume_mm3': float(part.volume())})
    input_volume = float(solid.volume())
    output_volume = sum(p['volume_mm3'] for p in part_reports)
    warnings = ['布尔分块重建几何并使用部件颜色，原 UV 和贴图不保留。',
                '尺寸和间隙为几何值，实际打印需按材料、喷嘴和设备误差试装标定。',
                '未执行载荷、材料或有限元强度验证。']
    if joint == 'dovetail':
        warnings.append('贯穿滑入式燕尾需要沿装配轴滑动装入；端部锁止需另行设计。')
    return scene, {
        'joint': joint, 'axis': axis, 'fraction': ratio, 'clearance_mm': clearance,
        'angle_deg': angle, 'units': units, 'parts': part_reports,
        'input_volume_mm3': input_volume, 'output_volume_mm3': output_volume,
        'removed_volume_mm3': max(0., input_volume - output_volume),
        'overlap_volume_mm3': overlap_volume, 'measured_gap_mm': gap,
        'joint_depth_mm': joint_depth, 'minimum_host_wall_mm': safety_wall,
        'assembly_axis': 'xyz'[order[2]], 'texture_preserved': False,
        'boolean_engine': 'manifold3d', 'warnings': warnings,
    }


def make_joint_sample(width_mm=60, depth_mm=30, height_mm=12,
                      clearance_mm=.2, angle_deg=12):
    """Create a parameterized two-part sliding dovetail specimen in metres."""
    width = _number(width_mm, '试件宽度', 10, 1000, inclusive_low=True)
    depth = _number(depth_mm, '试件深度', 10, 1000, inclusive_low=True)
    height = _number(height_mm, '试件高度', 2, 1000, inclusive_low=True)
    box = trimesh.creation.box(extents=np.array([width, depth, height]) / 1000.)
    scene, report = split_with_joint(box, clearance_mm=clearance_mm, angle_deg=angle_deg)
    report['sample_dimensions_mm'] = [width, depth, height]
    return scene, report
