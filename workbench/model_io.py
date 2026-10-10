"""Bounded, self-contained model IO. Working scene coordinates are metres/Y-up."""
import io
import json
import re
import struct

import numpy as np
import trimesh

MAX_UPLOAD = 32 * 1024 * 1024


def load_scene(data, extension='glb', units='mm'):
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError('文件为空或超过 32 MB。')
    warnings = []
    if extension == 'glb':
        if len(data) < 20:
            raise ValueError('文件不是有效的 GLB。')
        magic, version, size, length, kind = struct.unpack_from('<5I', data)
        if magic != 0x46546C67 or version != 2 or size != len(data) or kind != 0x4E4F534A or 20+length > len(data):
            raise ValueError('GLB 文件头或长度不正确。')
        document = json.loads(data[20:20+length])
        for item in document.get('buffers', []) + document.get('images', []):
            if 'uri' in item and not str(item['uri']).startswith('data:'):
                raise ValueError('请将所有贴图与缓冲区内嵌到 GLB，再导入。')
        if sum(a.get('count', 0) for a in document.get('accessors', [])) > 8_000_000:
            raise ValueError('GLB 数据规模超过当前处理限制。')
        scene = trimesh.load(io.BytesIO(data), file_type='glb', force='scene', process=False)
        _stable_primitive_nodes(scene, document)
    elif extension in ('stl', 'obj', 'ply'):
        if units not in ('mm', 'cm', 'm'):
            raise ValueError('无单位格式需指定 mm、cm 或 m。')
        if extension == 'ply':
            header = data[:65536].split(b'end_header')[0]
            for name, limit in [(b'vertex', 600_000), (b'face', 500_000)]:
                found = re.search(rb'element\s+' + name + rb'\s+(\d+)', header)
                if found and int(found[1]) > limit:
                    raise ValueError('PLY 顶点或面数超过限制。')
        if extension == 'obj' and (b'mtllib ' in data or b'usemtl ' in data):
            warnings.append('OBJ 按几何导入；外部 MTL/贴图未读取，带纹理模型请使用内嵌 GLB。')
        scene = trimesh.load(io.BytesIO(data), file_type=extension, force='scene', process=False,
                             resolver=None, skip_materials=True)
        scale = {'mm': .001, 'cm': .01, 'm': 1}[units]
        # STL/OBJ/PLY import convention: +Z up, transformed to glTF +Y up.
        transform = np.array([[scale, 0, 0, 0], [0, 0, scale, 0], [0, -scale, 0, 0], [0, 0, 0, 1.]])
        scene.apply_transform(transform)
    else:
        raise ValueError('支持 GLB、STL、OBJ 与 PLY。')
    validate_scene(scene)
    return scene, warnings


def _stable_primitive_nodes(scene, document):
    """Replace only loader-generated primitive UUID nodes with deterministic names.

    glTF multi-material meshes become several child nodes in Trimesh. Stable node
    names keep part IDs and reference matching consistent across independent loads.
    Names explicitly present in the file, including previous exports, are retained.
    """
    explicit = {str(n.get('name', i)) for i,n in enumerate(document.get('nodes', []))}
    edges = scene.graph.to_edgelist()
    groups = {}
    for parent, child, attrs in edges:
        if ('geometry' in attrs and child not in explicit
                and re.fullmatch(re.escape(str(parent)) + r'_[a-f0-9]{6}', str(child))):
            groups.setdefault(parent, []).append((child, attrs['geometry']))
    names = set(scene.graph.nodes)
    renames = {}
    for parent, children in groups.items():
        for index, (child, _) in enumerate(sorted(children, key=lambda item:item[1])):
            candidate = f'{parent}_primitive_{index:02d}'
            while candidate in names:
                candidate += '_'
            names.add(candidate)
            renames[child] = candidate
    if renames:
        graph = trimesh.scene.transforms.SceneGraph(base_frame=scene.graph.base_frame)
        for parent, child, attrs in edges:
            graph.update(frame_from=renames.get(parent,parent),frame_to=renames.get(child,child),**attrs)
        scene.graph = graph


def validate_scene(scene):
    if not isinstance(scene, trimesh.Scene) or not scene.geometry:
        raise ValueError('文件中没有网格几何体。')
    if len(scene.graph.nodes_geometry) > 128:
        raise ValueError('构件数量超过 128，请拆分场景。')
    triangles = 0
    for node in scene.graph.nodes_geometry:
        matrix, key = scene.graph[node]
        mesh = scene.geometry[key]
        if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
            raise ValueError('当前支持三角网格，请先将曲线/点云转换为网格。')
        triangles += len(mesh.faces)
        if len(mesh.vertices) > 600_000 or not np.isfinite(mesh.vertices).all():
            raise ValueError('构件坐标无效或顶点数量超过限制。')
        if mesh.faces.min() < 0 or mesh.faces.max() >= len(mesh.vertices):
            raise ValueError('面索引无效。')
        if not np.isfinite(matrix).all() or abs(np.linalg.det(matrix[:3, :3])) < 1e-18:
            raise ValueError('模型变换矩阵无效。')
        uv = getattr(mesh.visual, 'uv', None)
        if uv is not None and (len(uv) != len(mesh.vertices) or not np.isfinite(uv).all()):
            raise ValueError('UV 坐标无效。')
    if triangles > 500_000:
        raise ValueError('当前版本支持最多 50 万个三角面。')


def parts(scene):
    result = []
    for i, node in enumerate(sorted(scene.graph.nodes_geometry)):
        matrix, key = scene.graph[node]
        mesh = scene.geometry[key]
        result.append({'id': f'part-{i}', 'name': str(node), 'triangles': len(mesh.faces),
                       'has_uv': getattr(mesh.visual, 'uv', None) is not None,
                       'repair_target': 'RepairTarget' in str(node)})
    return result


def select_part(scene, part_id=None):
    listing = parts(scene)
    if part_id is None:
        if len(listing) != 1:
            raise ValueError('请先从构件列表中选择一个待处理构件。')
        part_id = listing[0]['id']
    record = next((p for p in listing if p['id'] == part_id), None)
    if not record:
        raise ValueError('未找到选中的构件，请重新选择。')
    node = record['name']
    matrix, key = scene.graph[node]
    return node, key, scene.geometry[key], matrix


def isolate(scene, part_id):
    node, key, mesh, matrix = select_part(scene, part_id)
    result = trimesh.Scene(base_frame='world')
    result.add_geometry(mesh.copy(), node_name=node, geom_name=key, transform=matrix)
    return result


def replace_part(scene, node, mesh):
    result = scene.copy()
    matrix, old_key = result.graph[node]
    users = [n for n in result.graph.nodes_geometry if result.graph[n][1] == old_key]
    if len(users) == 1:
        result.geometry[old_key] = mesh
    else:
        new_key = old_key + '_edited_' + str(len(result.geometry))
        result.geometry[new_key] = mesh
        result.graph.update(frame_to=node, frame_from=result.graph.base_frame, matrix=matrix, geometry=new_key)
    return result


def world_mesh(scene, part_id=None, print_axes=False):
    _, _, mesh, matrix = select_part(scene, part_id)
    output = mesh.copy()
    output.apply_transform(matrix)
    if print_axes:
        output.apply_transform(Y_UP_TO_Z_UP)
    return output


Y_UP_TO_Z_UP = np.array([[1., 0, 0, 0], [0, 0, -1., 0], [0, 1., 0, 0], [0, 0, 0, 1.]])
Z_UP_TO_Y_UP = np.linalg.inv(Y_UP_TO_Z_UP)
