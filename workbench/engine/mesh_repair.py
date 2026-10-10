"""Conservative local hole filling. No reference mesh or asset metadata is read.

Original corners, UVs and faces stay untouched. A position-welded copy is used
only to trace boundaries. Patches use fixed boundaries, local surface fitting
and harmonic interpolation in the projected domain.
"""
from time import perf_counter

import numpy as np
import trimesh
from scipy.spatial import Delaunay, QhullError
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from shapely import contains_xy
from shapely.geometry import Polygon


def _topology(mesh):
    if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
        raise ValueError('模型中没有可处理的三角面。')
    if len(mesh.faces) > 500_000 or len(mesh.vertices) > 600_000:
        raise ValueError('当前版本支持最多 50 万个三角面，请先拆分模型。')
    v, f = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    if not np.isfinite(v).all() or f.min() < 0 or f.max() >= len(v):
        raise ValueError('模型包含无效坐标或面索引。')
    scale = float(np.linalg.norm(np.ptp(v, axis=0)))
    if scale <= 1e-12:
        raise ValueError('模型尺寸为零。')
    # Float32 GLB round trips may contain split corners at the same position.
    _, representatives, inverse = np.unique(
        np.round((v - v.min(axis=0)) / (scale * 1e-8)).astype(np.int64),
        axis=0, return_index=True, return_inverse=True)
    faces = inverse[f]
    directed = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    corners = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    edges, edge_inverse, counts = np.unique(np.sort(directed, axis=1), axis=0,
                                           return_inverse=True, return_counts=True)
    mask = counts[edge_inverse] == 1
    boundary = directed[mask]
    original_boundary = corners[mask]
    signed = np.where(directed[:, 0] < directed[:, 1], 1, -1)
    sums = np.bincount(edge_inverse, weights=signed, minlength=len(edges))
    winding = bool(np.all(sums[counts == 2] == 0))
    next_edge = {}
    valid = len(set(boundary[:, 0])) == len(boundary) and len(set(boundary[:, 1])) == len(boundary)
    loops = []
    if valid:
        next_edge = {int(a): (int(b), int(c), int(d))
                     for (a, b), (c, d) in zip(boundary, original_boundary)}
        remaining = set(next_edge)
        while remaining:
            start = min(remaining)
            current, loop = start, []
            while current in remaining:
                remaining.remove(current)
                loop.append(current)
                current = next_edge[current][0]
            if current != start:
                valid = False
                break
            loops.append(loop)
    uv = getattr(mesh.visual, 'uv', None)
    has_uv = uv is not None and len(uv) == len(v) and bool(np.isfinite(uv).all())
    if uv is not None and not has_uv:
        raise ValueError('模型的 UV 坐标不完整或包含无效值。')
    degenerate = int(np.sum(mesh.area_faces < scale * scale * 1e-14))
    diagnosis = {
        'vertices': len(v), 'triangles': len(f), 'boundary_edges': len(boundary),
        'boundary_loops': len(loops) if valid else 0,
        'nonmanifold_edges': int(np.sum(counts > 2)),
        'degenerate_triangles': degenerate,
        'watertight': bool(np.all(counts == 2)), 'winding_consistent': winding,
        'has_uv': has_uv,
        'boundary_segments': v[original_boundary].tolist(),
    }
    return diagnosis, (representatives, inverse, faces, edges, next_edge, loops, valid, scale)


def diagnose_mesh(mesh):
    return _topology(mesh)[0]


def _harmonic(points, triangles, boundary_values):
    """Cotangent Laplacian in 2D: affine UV maps are reproduced exactly."""
    n, fixed = len(points), len(boundary_values)
    if fixed == n:
        return np.empty((0, boundary_values.shape[1]))
    rows, cols, values = [], [], []
    for triangle in triangles:
        p = points[triangle]
        for k in range(3):
            i, j = (k + 1) % 3, (k + 2) % 3
            u, v = p[i] - p[k], p[j] - p[k]
            cross = abs(u[0] * v[1] - u[1] * v[0])
            weight = float(np.dot(u, v) / max(cross, 1e-15)) * .5
            a, b = int(triangle[i]), int(triangle[j])
            rows.extend([a, b, a, b]); cols.extend([a, b, b, a])
            values.extend([weight, weight, -weight, -weight])
    matrix = coo_matrix((values, (rows, cols)), shape=(n, n)).tocsr()
    result = spsolve(matrix[fixed:, fixed:], -matrix[fixed:, :fixed] @ boundary_values)
    result = np.asarray(result).reshape(n - fixed, boundary_values.shape[1])
    if not np.isfinite(result).all():
        raise ValueError('补片插值未收敛，请手工检查孔洞边界。')
    return result


def _features(xy):
    x, y = xy.T
    return np.column_stack([np.ones(len(x)), x, y, x*x, x*y, y*y])


def _constrained_patch(boundary):
    """Earcut plus restoration of collinear boundary vertices and centroid refinement."""
    import mapbox_earcut
    triangles = mapbox_earcut.triangulate_float64(np.asarray(boundary,dtype=np.float64),
                                                 np.array([len(boundary)],dtype=np.uint32)).reshape(-1,3).tolist()
    n = len(boundary)
    # Earcut can omit collinear ring corners. Split spanning boundary edges to
    # restore every original edge exactly, including long straight wall rims.
    for _ in range(n):
        changed = False
        new_triangles = []
        for tri in triangles:
            split = False
            for k in range(3):
                a,b,c = tri[k],tri[(k+1)%3],tri[(k+2)%3]
                if (a-b)%n in (1,n-1): continue
                for direction in (1,-1):
                    chain = [a]; cursor = (a+direction)%n
                    while cursor!=b and len(chain)<=n:
                        chain.append(cursor); cursor = (cursor+direction)%n
                    chain.append(b)
                    if len(chain)<=2: continue
                    vec = boundary[b]-boundary[a]
                    norm = np.dot(vec,vec)
                    if norm<1e-20: continue
                    positions = boundary[chain[1:-1]]-boundary[a]
                    cross = np.abs(positions[:,0]*vec[1]-positions[:,1]*vec[0])
                    t = positions@vec/norm
                    if np.all(cross<1e-9) and np.all((t>0)&(t<1)):
                        new_triangles.extend([[u,v,c] for u,v in zip(chain[:-1],chain[1:])])
                        split = changed = True; break
                if split: break
            if not split: new_triangles.append(tri)
        triangles = new_triangles
        if not changed: break
    points = list(np.asarray(boundary)); refined = []
    for a,b,c in triangles:
        u,v = boundary[b]-boundary[a],boundary[c]-boundary[a]
        if u[0]*v[1]-u[1]*v[0]<0: b,c=c,b
        index = len(points); points.append((boundary[a]+boundary[b]+boundary[c])/3)
        refined.extend([[a,b,index],[b,c,index],[c,a,index]])
    return np.asarray(points),np.asarray(refined,dtype=np.int64)


def _patch(mesh, loop, topology, max_boundary=512):
    representatives, inverse, faces, edges, next_edge, _, _, scale = topology
    if not 3 <= len(loop) <= max_boundary:
        raise ValueError(f'当前自动补洞支持 3–{max_boundary} 个顶点的简单边界环。')
    boundary_indices = np.array([next_edge[i][1] for i in loop])
    xyz = np.asarray(mesh.vertices)[boundary_indices]
    uv = getattr(mesh.visual, 'uv', None)
    if uv is not None:
        # A discontinuous UV chart needs per-corner patch parameterization.
        for i, vertex in enumerate(loop):
            incoming = next_edge[loop[i - 1]][2]
            outgoing = next_edge[vertex][1]
            if not np.allclose(uv[incoming], uv[outgoing], atol=1e-6, rtol=0):
                raise ValueError('孔洞跨越 UV 接缝，当前版本需要先拆分纹理区域。')
    origin = xyz.mean(axis=0)
    _, singular, axes = np.linalg.svd(xyz - origin, full_matrices=False)
    if singular[1] < scale * 1e-8:
        raise ValueError('孔洞边界接近直线，无法形成有效补片。')
    extent = float(np.max(np.linalg.norm(xyz - origin, axis=1)))
    projected = (xyz - origin) @ axes[:2].T / extent
    polygon = Polygon(projected)
    if not polygon.is_valid or polygon.area < 1e-10:
        raise ValueError('孔洞投影自交或面积过小，需要人工处理。')
    if singular[-1] / singular[1] > .35:
        raise ValueError('孔洞弯曲程度超出当前局部补洞能力。')
    # Keep a comparable tessellation density; cap computation for sparse rims.
    spacing = float(np.median(np.linalg.norm(np.roll(projected, -1, axis=0) - projected, axis=1)))
    spacing = max(spacing, np.sqrt(polygon.area / 1600))
    low, high = projected.min(axis=0), projected.max(axis=0)
    grid = np.array(np.meshgrid(np.arange(low[0] + spacing*.5, high[0], spacing),
                               np.arange(low[1] + spacing*.5, high[1], spacing))).reshape(2, -1).T
    inside = grid[contains_xy(polygon.buffer(-1e-8), grid[:, 0], grid[:, 1])]
    points = np.concatenate([projected, inside])
    try:
        candidates = Delaunay(points).simplices
    except QhullError as exc:
        raise ValueError('孔洞三角化失败，请检查边界形状。') from exc
    cover = polygon.buffer(1e-9)
    triangles = np.array([t for t in candidates if cover.covers(Polygon(points[t]))], dtype=np.int64)
    if not len(triangles):
        raise ValueError('未生成有效补片。')
    tri_edges = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]],
                                       triangles[:, [2, 0]]]), axis=1)
    unique_edges, counts = np.unique(tri_edges, axis=0, return_counts=True)
    actual = {tuple(e) for e in unique_edges[counts == 1]}
    expected = {tuple(sorted((i, (i + 1) % len(loop)))) for i in range(len(loop))}
    if actual != expected or len(np.unique(triangles)) != len(points):
        points,triangles = _constrained_patch(projected)
        inside = points[len(loop):]
        edges2 = np.sort(np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]]),axis=1)
        unique2,counts2 = np.unique(edges2,axis=0,return_counts=True)
        if {tuple(e) for e in unique2[counts2==1]} != expected:
            raise ValueError('无法完整保留此孔洞的边界约束，已停止自动补洞。')
    # Gather only the adjacent sheet, avoiding the opposite side of thin walls.
    neighborhood = set(loop)
    for _ in range(3):
        selected = np.any(np.isin(edges, list(neighborhood)), axis=1)
        neighborhood.update(edges[selected].reshape(-1).tolist())
    neighbors = np.asarray(mesh.vertices)[representatives[sorted(neighborhood)]]
    local = (neighbors - origin) @ axes.T / extent
    coefficients, _, rank, _ = np.linalg.lstsq(_features(local[:, :2]), local[:, 2], rcond=None)
    if rank < 6:
        coefficients = np.zeros(6)
    height_boundary = ((xyz - origin) @ axes[2] / extent)
    residual = height_boundary - _features(projected) @ coefficients
    height = _features(inside) @ coefficients + _harmonic(points, triangles, residual[:, None]).ravel()
    # A failed/excessive polynomial extrapolation must not produce a spike.
    if len(height) and np.max(np.abs(height)) > 1:
        raise ValueError('拟合补片偏离局部表面过远，已停止自动补洞。')
    new_xyz = origin + (inside @ axes[:2] + height[:, None] * axes[2]) * extent
    new_uv = _harmonic(points, triangles, np.asarray(uv)[boundary_indices]) if uv is not None else None
    signed_area = np.sum(projected[:, 0] * np.roll(projected[:, 1], -1) -
                         projected[:, 1] * np.roll(projected[:, 0], -1))
    # scipy Delaunay is CCW. Patch edges must oppose original boundary edges.
    if signed_area > 0:
        triangles = triangles[:, ::-1]
    return boundary_indices, new_xyz, new_uv, triangles


def repair_mesh(mesh, *, max_boundary=512):
    started = perf_counter()
    before, topology = _topology(mesh)
    if before['nonmanifold_edges'] or before['degenerate_triangles'] or not before['winding_consistent']:
        raise ValueError('请先处理非流形边、退化面或法向不一致，再执行局部补洞。')
    if not topology[6]:
        raise ValueError('边界存在分叉或未闭合，不能自动生成补片。')
    if len(topology[5]) > 32:
        raise ValueError('孔洞超过 32 个，请先拆分模型。')
    vertices, faces = [np.array(mesh.vertices)], [np.array(mesh.faces)]
    original_uv = getattr(mesh.visual, 'uv', None)
    uvs = [np.array(original_uv)] if original_uv is not None else None
    offset = len(mesh.vertices)
    for loop in topology[5]:
        boundary, new_xyz, new_uv, triangles = _patch(mesh, loop, topology, max_boundary=max_boundary)
        mapping = np.concatenate([boundary, np.arange(offset, offset + len(new_xyz))])
        vertices.append(new_xyz); faces.append(mapping[triangles])
        if uvs is not None:
            uvs.append(new_uv)
        offset += len(new_xyz)
    result = mesh.copy()
    result.vertices = np.concatenate(vertices)
    result.faces = np.concatenate(faces)
    if uvs is not None:
        result.visual = trimesh.visual.texture.TextureVisuals(uv=np.concatenate(uvs),
                                                               material=mesh.visual.material.copy())
    elif mesh.visual.kind == 'vertex':
        from scipy.spatial import cKDTree
        original_colors = np.asarray(mesh.visual.vertex_colors)
        nearest = cKDTree(mesh.vertices).query(result.vertices[len(mesh.vertices):])[1]
        result.visual = trimesh.visual.ColorVisuals(mesh=result,vertex_colors=np.concatenate([original_colors,original_colors[nearest]]))
    elif mesh.visual.kind == 'face':
        from scipy.spatial import cKDTree
        original_colors = np.asarray(mesh.visual.face_colors)
        nearest = cKDTree(mesh.triangles_center).query(result.triangles_center[len(mesh.faces):])[1]
        result.visual = trimesh.visual.ColorVisuals(mesh=result,face_colors=np.concatenate([original_colors,original_colors[nearest]]))
    after = diagnose_mesh(result)
    if not after['watertight'] or not after['winding_consistent'] or after['degenerate_triangles']:
        raise ValueError('补后网格未通过闭合与法向检查，未输出修复结果。')
    report = {
        'before': before, 'after': after,
        'added_vertices': len(result.vertices) - len(mesh.vertices),
        'added_triangles': len(result.faces) - len(mesh.faces),
        'filled_loops': len(topology[5]), 'elapsed_ms': round((perf_counter() - started) * 1000, 1),
        'method': '固定边界局部曲面拟合 + 三角化 + 调和 UV 插值',
        'warnings': ['保留并复用原始贴图；未生成缺失的纹理像素。',
                     '闭合检查不涵盖自相交、最小壁厚、强度或可打印性。'],
        'original_vertices_preserved': bool(np.array_equal(result.vertices[:len(mesh.vertices)], mesh.vertices)),
        'original_uv_preserved': bool(np.array_equal(result.visual.uv[:len(mesh.vertices)], original_uv))
                                 if original_uv is not None else None,
    }
    return result, report


def repair_advanced_mesh(mesh, cleanup=True, optimize=True):
    """Clean reversible topology defects, repair, and measure patch-only optimization."""
    from .quality import optimize_seam, seam_quality
    started = perf_counter()
    before = diagnose_mesh(mesh)
    working = mesh.copy()
    cleanup_report = {'enabled':cleanup,'removed_duplicate_faces':0,'removed_degenerate_faces':0,'flipped_faces':0}
    if cleanup:
        scale = float(np.linalg.norm(mesh.extents))
        _,inverse = np.unique(np.round(mesh.vertices/(scale*1e-8)).astype(np.int64),axis=0,return_inverse=True)
        welded_faces = inverse[mesh.faces]
        keep = mesh.area_faces>=scale*scale*1e-14
        cleanup_report['removed_degenerate_faces'] = int(np.sum(~keep))
        candidates = np.flatnonzero(keep)
        _,first = np.unique(np.sort(welded_faces[keep],axis=1),axis=0,return_index=True)
        keep[:] = False; keep[candidates[first]] = True
        cleanup_report['removed_duplicate_faces'] = len(candidates)-len(first)
        working.update_faces(keep)
        if not len(working.faces): raise ValueError('清理后没有有效三角面。')
        # Determine face flips using a welded topology while retaining source UV corners.
        _,representatives,inverse = np.unique(np.round(working.vertices/(scale*1e-8)).astype(np.int64),axis=0,return_index=True,return_inverse=True)
        original_faces = inverse[working.faces]
        welded = trimesh.Trimesh(vertices=working.vertices[representatives],faces=original_faces,process=False)
        trimesh.repair.fix_normals(welded,multibody=True)
        flipped = np.any(welded.faces!=original_faces,axis=1)
        new_faces = np.array(working.faces); new_faces[flipped] = new_faces[flipped,::-1]
        working.faces = new_faces; cleanup_report['flipped_faces'] = int(np.sum(flipped))
    result,report = repair_mesh(working,max_boundary=2048)
    if optimize:
        result,seam_before,seam_after,optimization = optimize_seam(working,result)
    else:
        seam_before = seam_after = seam_quality(working,result)
        optimization = {'applied':False,'moved_vertices':0,'method':'用户未启用接缝优化'}
    report.update({'before':before,'after':diagnose_mesh(result),'cleanup':cleanup_report,
                   'seam_before':seam_before,'seam_after':seam_after,'seam_optimization':optimization,
                   'seam_segments':seam_after['seam_segments'],'elapsed_ms':round((perf_counter()-started)*1000,1),
                   'original_faces_preserved':not any(cleanup_report[k] for k in ('removed_duplicate_faces','removed_degenerate_faces','flipped_faces'))})
    return result,report
