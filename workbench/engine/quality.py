"""Measured patch seams and bounded, reproducible reference evaluation."""
import numpy as np
import trimesh


def seam_pairs(original, repaired):
    scale = max(float(np.linalg.norm(repaired.extents)),1e-12)
    _,inverse = np.unique(np.round(repaired.vertices/(scale*1e-8)).astype(np.int64),axis=0,return_inverse=True)
    faces = inverse[repaired.faces]
    edges = np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]])
    owners = np.tile(np.arange(len(faces)),3)
    corners = np.concatenate([repaired.faces[:,[0,1]],repaired.faces[:,[1,2]],repaired.faces[:,[2,0]]])
    _,group,counts = np.unique(np.sort(edges,axis=1),axis=0,return_inverse=True,return_counts=True)
    order = np.argsort(group,kind='stable')
    offsets = np.r_[0,np.cumsum(counts)[:-1]]
    valid = np.flatnonzero(counts==2)
    left,right = order[offsets[valid]],order[offsets[valid]+1]
    a,b = owners[left],owners[right]
    crossing = (a<len(original.faces)) != (b<len(original.faces))
    a,b,left = a[crossing],b[crossing],left[crossing]
    old = np.where(a<len(original.faces),a,b)
    new = np.where(a<len(original.faces),b,a)
    return old,new,corners[left]


def seam_quality(original,repaired):
    old,new,edges = seam_pairs(original,repaired)
    angles = np.degrees(np.arccos(np.clip(np.einsum('ij,ij->i',repaired.face_normals[old],repaired.face_normals[new]),-1,1)))
    uv = getattr(repaired.visual,'uv',None)
    stretch = []; degenerate = 0
    if uv is not None:
        for face in repaired.faces[len(original.faces):]:
            xyz = repaired.vertices[face]; tex = np.asarray(uv)[face]
            a,b = xyz[1]-xyz[0],xyz[2]-xyz[0]
            length = np.linalg.norm(a); x = np.dot(a,b)/max(length,1e-15)
            y = np.sqrt(max(np.dot(b,b)-x*x,0))
            du,dv = tex[1]-tex[0],tex[2]-tex[0]
            if length*y<1e-16 or abs(du[0]*dv[1]-du[1]*dv[0])<1e-14:
                degenerate += 1; continue
            jacobian = np.column_stack([du,dv]) @ np.linalg.inv([[length,x],[0,y]])
            singular = np.linalg.svd(jacobian,compute_uv=False)
            stretch.append(float(singular[0]/max(singular[1],1e-15)))
    return {'edge_count':len(edges),'mean_angle_deg':float(np.mean(angles)) if len(angles) else None,
            'max_angle_deg':float(np.max(angles)) if len(angles) else None,
            'uv_stretch_mean':float(np.mean(stretch)) if stretch else None,
            'uv_stretch_max':float(np.max(stretch)) if stretch else None,'uv_degenerate_triangles':degenerate,
            'seam_segments':repaired.vertices[edges].tolist(),
            'definition':'原面与新增面交界二面角；UV 指标为补片映射奇异值比，1 表示局部各向同性。'}


def optimize_seam(original,repaired):
    before = seam_quality(original,repaired)
    old,new,edges = seam_pairs(original,repaired)
    count = len(original.vertices)
    constraints = {}
    for a,b,edge in zip(old,new,edges):
        for vertex in repaired.faces[b]:
            if vertex>=count:
                normal = repaired.face_normals[a]
                value = np.dot(normal,repaired.vertices[edge[0]]-repaired.vertices[vertex])
                constraints.setdefault(int(vertex),[]).append((normal,value))
    delta = np.zeros_like(repaired.vertices)
    for vertex,items in constraints.items():
        normals = np.array([p[0] for p in items]); values = np.array([p[1] for p in items])
        delta[vertex] = np.linalg.solve(normals.T@normals + .1*np.eye(3),normals.T@values)
    # Propagate the fitted displacement into the patch while pinning original corners.
    patch_edges = np.unique(np.sort(np.concatenate([repaired.faces[len(original.faces):,[0,1]],
                                         repaired.faces[len(original.faces):,[1,2]],
                                         repaired.faces[len(original.faces):,[2,0]]]),axis=1),axis=0)
    free = np.arange(count,len(repaired.vertices)); ring = set(constraints)
    adjacency = {int(v):[] for v in free}
    for a,b in patch_edges:
        if a>=count: adjacency[int(a)].append(int(b))
        if b>=count: adjacency[int(b)].append(int(a))
    for _ in range(4):
        previous = delta.copy()
        for vertex,neighbors in adjacency.items():
            if vertex not in ring and neighbors: delta[vertex] = previous[neighbors].mean(axis=0)
    best = repaired; quality = before; chosen = 0
    for weight in (.25,.5,1.):
        candidate = repaired.copy(); candidate.vertices = repaired.vertices + weight*delta
        if np.any(candidate.area_faces<np.linalg.norm(candidate.extents)**2*1e-14): continue
        if np.any(np.einsum('ij,ij->i',candidate.face_normals,repaired.face_normals)<.25): continue
        measured = seam_quality(original,candidate)
        if (measured['mean_angle_deg'] is not None and quality['mean_angle_deg'] is not None
            and measured['mean_angle_deg']<quality['mean_angle_deg']-1e-6
            and measured['max_angle_deg']<=before['max_angle_deg']+1e-6
            and measured['uv_degenerate_triangles']<=before['uv_degenerate_triangles']):
            best,quality,chosen = candidate,measured,weight
    return best,before,quality,{'applied':chosen>0,'weight':chosen,'moved_vertices':int(np.sum(np.linalg.norm(best.vertices-repaired.vertices,axis=1)>1e-12)),
                               'method':'边界原面切平面约束 + 补片内位移扩散；仅接受平均接缝角下降且最大角不增加的候选'}


def compare_reference(repaired,reference,samples=256,seed=42):
    if not 16<=samples<=512: raise ValueError('评估采样数量需在 16–512 之间。')
    if max(len(repaired.faces),len(reference.faces))>100_000: raise ValueError('参考评估限单构件 10 万面以内。')
    distances = []
    for source,target in [(repaired,reference),(reference,repaired)]:
        points,_ = trimesh.sample.sample_surface(source,samples,seed=seed)
        for i in range(0,len(points),8):
            _,distance,_ = trimesh.proximity.closest_point_naive(target,points[i:i+8]); distances.extend(distance)
    values = np.asarray(distances)
    return {'mean_distance':float(values.mean()),'rms_distance':float(np.sqrt(np.mean(values**2))),
            'max_distance':float(values.max()),'p95_distance':float(np.percentile(values,95)),
            'samples_per_direction':samples,'seed':seed,'units':'model_units','method':'bidirectional_sampled_point_to_surface'}
