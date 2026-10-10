"""Check exported assets independently of Blender's source-mesh checks."""
from pathlib import Path
import hashlib
import json
import struct
import numpy as np
import trimesh

ROOT=Path(__file__).resolve().parents[1]


def glb_document(path):
    data=path.read_bytes()
    magic,version,length=struct.unpack_from('<III',data)
    assert magic==0x46546C67 and version==2 and length==len(data),path.name
    json_length,kind=struct.unpack_from('<II',data,12)
    assert kind==0x4E4F534A
    document=json.loads(data[20:20+json_length])
    return data,document


def uv_keys(mesh):
    uv=getattr(mesh.visual,'uv',None)
    assert uv is not None and len(uv)==len(mesh.vertices)
    return {tuple(row) for row in np.round(np.column_stack((mesh.vertices,uv)),6)}


def topology(mesh):
    merged=mesh.copy()
    merged.merge_vertices(merge_tex=True,merge_norm=True)
    counts=np.bincount(merged.edges_unique_inverse,minlength=len(merged.edges_unique))
    return {'vertices_merged':len(merged.vertices),'triangles':len(merged.faces),
            'watertight_after_position_merge':bool(merged.is_watertight),
            'winding_consistent':bool(merged.is_winding_consistent),
            'boundary_edges':int(np.sum(counts==1)),
            'nonmanifold_edges':int(np.sum(counts>2)),
            'degenerate_triangles':int(np.sum(merged.area_faces<1e-12))}


def run():
    results={};scenes={}
    for path in sorted((ROOT/'exports').glob('*.glb')):
        data,doc=glb_document(path)
        scene=trimesh.load(path,force='scene',process=False)
        scenes[path.name]=scene
        triangles=sum(len(g.faces) for g in scene.geometry.values())
        for name,g in scene.geometry.items():
            assert np.isfinite(g.vertices).all(),(path.name,name)
            assert np.isfinite(g.visual.uv).all(),(path.name,name,'UV')
            assert g.faces.min()>=0 and g.faces.max()<len(g.vertices),(path.name,name)
        assert all('bufferView' in image and 'uri' not in image for image in doc.get('images',[])),path.name
        assert all('TEXCOORD_0' in p['attributes'] for mesh in doc['meshes'] for p in mesh['primitives']),path.name
        results[path.name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                           'gltf_meshes':len(doc['meshes']),'primitives':sum(len(m['primitives']) for m in doc['meshes']),
                           'triangles':triangles,'embedded_images':len(doc.get('images',[])),
                           'finite_vertices_and_uv':True,'no_external_texture_dependencies':True}
    cases={}
    for key in ('roof','panel'):
        complete=next(iter(scenes[key+'_intact.glb'].geometry.values()))
        broken=next(iter(scenes[key+'_damaged.glb'].geometry.values()))
        full_keys,broken_keys=uv_keys(complete),uv_keys(broken)
        a,b=topology(complete),topology(broken)
        assert a['watertight_after_position_merge'] and a['winding_consistent'],(key,a)
        assert not b['watertight_after_position_merge'] and b['boundary_edges']>0,(key,b)
        assert a['degenerate_triangles']==b['degenerate_triangles']==0,(key,a,b)
        assert broken_keys.issubset(full_keys),(key,'surviving geometry/UV changed')
        cases[key]={'intact':a,'damaged':b,'all_surviving_positions_and_uv_match':True,
                    'missing_triangles':len(complete.faces)-len(broken.faces)}
    for name,g in scenes['dovetail_assembled.glb'].geometry.items():
        result=topology(g)
        assert result['watertight_after_position_merge'] and result['degenerate_triangles']==0,(name,result)
    report={'status':'passed','files':results,'repair_cases':cases,
            'scope':'File integrity, embedded textures, geometry, source-to-GLB topology and unchanged UV outside synthetic holes. No browser FPS, print or mechanical validation is claimed.'}
    (ROOT/'reports'/'export_verification.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'status':'passed','files':len(results),'repair_cases':cases},ensure_ascii=False,indent=2))


if __name__=='__main__':run()
