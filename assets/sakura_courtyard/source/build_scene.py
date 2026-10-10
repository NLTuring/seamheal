"""Build and verify the original Sakura Courtyard Blender/GLB asset pack.

Blender 4.5 LTS:
  blender --background --factory-startup --python build_scene.py -- --draft
The complete meshes are synthetic ground truth, not algorithm repair results.
"""
from pathlib import Path
import sys
import math
import json
import time
import argparse
from collections import Counter

import bpy
import bmesh
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'source'))
from architecture import create_architecture
from vegetation import create_vegetation
from landscape import create_landscape, ground_height, make_joint_sample

SCALE=.02  # A design unit is 20 mm; glTF coordinates are in metres.


def log(message):
    print(f'[SeamHeal {time.strftime("%H:%M:%S")}] {message}',flush=True)


def rgba(hex_color):
    values=[int(hex_color[i:i+2],16)/255 for i in (0,2,4)]
    linear=[v/12.92 if v<.04045 else ((v+.055)/1.055)**2.4 for v in values]
    return (*linear,1)


def material(name,color,roughness=.65,metallic=0,texture=None,normal=None,normal_strength=.25,emission=0):
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    mat.diffuse_color=rgba(color)
    bsdf=mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value=rgba(color)
    bsdf.inputs['Roughness'].default_value=roughness
    bsdf.inputs['Metallic'].default_value=metallic
    if texture:
        tex=mat.node_tree.nodes.new('ShaderNodeTexImage')
        tex.image=bpy.data.images.load(str(ROOT/'textures'/texture),check_existing=True)
        tex.image.colorspace_settings.name='sRGB';tex.image.pack()
        mat.node_tree.links.new(tex.outputs['Color'],bsdf.inputs['Base Color'])
    if normal:
        tex=mat.node_tree.nodes.new('ShaderNodeTexImage')
        tex.image=bpy.data.images.load(str(ROOT/'textures'/normal),check_existing=True)
        tex.image.colorspace_settings.name='Non-Color';tex.image.pack()
        n=mat.node_tree.nodes.new('ShaderNodeNormalMap');n.inputs['Strength'].default_value=normal_strength
        mat.node_tree.links.new(tex.outputs['Color'],n.inputs['Color'])
        mat.node_tree.links.new(n.outputs['Normal'],bsdf.inputs['Normal'])
    if emission:
        bsdf.inputs['Emission Color'].default_value=rgba(color)
        bsdf.inputs['Emission Strength'].default_value=emission
    return mat


def make_materials():
    return {
        'roof':material('01 Blue grey glazed clay','526670',.63,texture='roof_tiles_basecolor.png',normal='roof_tiles_normal.png',normal_strength=.30),
        'roof_trim':material('02 Charcoal ridge tiles','3C5157',.54),
        'wood':material('03 Weathered cedar','855435',.68,texture='cedar_wood_basecolor.png',normal='cedar_wood_normal.png'),
        'wood_dark':material('04 Dark end grain','50372C',.79),
        'redwood':material('05 Red cedar rails','824C3F',.63),
        'plaster':material('06 Warm lime plaster','E7DFC9',.9),
        'painted_panel':material('07 Original sakura mural UV','E8D7B7',.76,texture='sakura_painted_panel_basecolor.png'),
        'stone':material('08 Weathered limestone','858279',.9,texture='weathered_stone_basecolor.png',normal='weathered_stone_normal.png',normal_strength=.35),
        'brass':material('09 Antique brass','B59251',.36,.72),
        'glass':material('10 Blue grey window glass','637B77',.3,.12),
        'ground':material('11 Moss and soil','798350',.94,texture='moss_ground_basecolor.png',normal='moss_ground_normal.png',normal_strength=.33),
        'path':material('12 Warm gravel','B8A584',.98,texture='warm_gravel_basecolor.png'),
        'water':material('13 Jade stream','547F7C',.48,0),
        'bark':material('14 Cherry bark','63452F',.87,texture='cherry_bark_basecolor.png',normal='cedar_wood_normal.png',normal_strength=.5),
        'bark_light':material('15 Bark ridges','7D563C',.87,texture='cherry_bark_basecolor.png'),
        'blossom_pale':material('16 Sakura pearl pink','F2BFCB',.61),
        'blossom_pink':material('17 Sakura rose','E39EB5',.65),
        'blossom_deep':material('18 Sakura magenta centre','BB6380',.65),
        'leaf':material('19 Young jade leaf','698C60',.77),
        'lantern_glow':material('20 Warm lantern paper','F4CD90',.68,emission=.16),
    }


def mesh_stats(obj):
    mesh=obj.data;mesh.calc_loop_triangles()
    bm=bmesh.new();bm.from_mesh(mesh)
    boundary=[e for e in bm.edges if e.is_boundary]
    abnormal=[e for e in bm.edges if len(e.link_faces) not in (1,2)]
    remaining=set(boundary);components=0
    while remaining:
        components+=1;stack=[remaining.pop()]
        while stack:
            e=stack.pop()
            for v in e.verts:
                for neighbor in v.link_edges:
                    if neighbor in remaining:
                        remaining.remove(neighbor);stack.append(neighbor)
    volume=bm.calc_volume(signed=True)
    result={'object':obj.name,'vertices':len(mesh.vertices),'triangles':len(mesh.loop_triangles),
            'boundary_edges':len(boundary),'boundary_components':components,'nonmanifold_or_wire_edges':len(abnormal),
            'degenerate_faces':sum(f.calc_area()<1e-12 for f in bm.faces),
            'watertight':not boundary and not abnormal,'uv_layers':len(mesh.uv_layers),
            'signed_volume_design_units':round(volume,6)}
    bm.free();return result


def select_objects(objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.hide_set(False);obj.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]


def export_glb(name,objects,parent=None):
    select_objects(([parent] if parent else [])+objects)
    options=dict(filepath=str(ROOT/'exports'/name),export_format='GLB',use_selection=True,
                 export_yup=True,export_apply=True,export_extras=True,export_animations=False,
                 export_cameras=False,export_lights=False,export_materials='EXPORT')
    props=bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    bpy.ops.export_scene.gltf(**{k:v for k,v in options.items() if k in props})
    log(f'Exported {name}')


def look_at(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()


def studio():
    col=bpy.data.collections.new('Studio_only_not_exported');bpy.context.scene.collection.children.link(col)
    def link(obj):
        for c in list(obj.users_collection):c.objects.unlink(obj)
        col.objects.link(obj)
    bpy.ops.mesh.primitive_plane_add(size=200*SCALE,location=(0,0,-.97*SCALE))
    floor=bpy.context.object;floor.name='Studio floor';link(floor)
    floor.data.materials.append(material('Studio porcelain background','EDE8DE',.87))
    bpy.ops.object.camera_add(location=Vector((16,-24,18))*SCALE)
    camera=bpy.context.object;camera.name='Camera_Hero';link(camera)
    camera.data.type='ORTHO';camera.data.ortho_scale=19.4*SCALE
    camera.data.clip_start=.001;camera.data.clip_end=20
    look_at(camera,Vector((0,0,3.95))*SCALE)
    bpy.context.scene.camera=camera
    def area(name,location,power,size,color):
        data=bpy.data.lights.new(name,'AREA');data.energy=power*SCALE*SCALE;data.shape='DISK';data.size=size*SCALE;data.color=color
        obj=bpy.data.objects.new(name,data);col.objects.link(obj);obj.location=Vector(location)*SCALE
        look_at(obj,Vector((0,0,3))*SCALE)
    area('Large warm key',(-7,-10,18),2100,9,(1,.88,.76))
    area('Cool fill',(11,-1,10),1500,8,(.82,.91,1))
    area('Sakura rim',(-5,9,15),2400,7,(1,.80,.76))
    world=bpy.data.worlds.new('Warm gallery ambience');world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(.72,.78,.85,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=.45
    bpy.context.scene.world=world
    return camera,col


def setup_render(draft):
    scene=bpy.context.scene;scene.render.engine='CYCLES'
    scene.cycles.samples=32 if draft else 96
    scene.cycles.use_denoising=True
    scene.cycles.max_bounces=6;scene.cycles.transparent_max_bounces=4
    try:
        prefs=bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type='OPTIX';prefs.get_devices()
        gpu=False
        for dev in prefs.devices:
            dev.use=dev.type=='OPTIX';gpu|=dev.use
        if gpu:scene.cycles.device='GPU'
        log('Cycles device '+scene.cycles.device)
    except Exception as e:
        log('Using Cycles CPU: '+str(e))
    scene.render.resolution_x=1100 if draft else 1800
    scene.render.resolution_y=1000 if draft else 1600
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.view_settings.view_transform='AgX'
    try:scene.view_settings.look='AgX - Medium High Contrast'
    except TypeError:pass
    scene.view_settings.exposure=.35
    scene.render.film_transparent=False
    scene.render.image_settings.color_mode='RGBA'


def render(name):
    bpy.context.scene.render.filepath=str(ROOT/'previews'/name)
    log('Rendering '+name)
    bpy.ops.render.render(write_still=True)


def damage(obj,face_indices):
    bm=bmesh.new();bm.from_mesh(obj.data);bm.faces.ensure_lookup_table()
    faces=[bm.faces[i] for i in face_indices]
    bmesh.ops.delete(bm,geom=faces,context='FACES')
    loose=[e for e in bm.edges if not e.link_faces]
    if loose:bmesh.ops.delete(bm,geom=loose,context='EDGES')
    loose=[v for v in bm.verts if not v.link_edges]
    if loose:bmesh.ops.delete(bm,geom=loose,context='VERTS')
    bm.to_mesh(obj.data);bm.free();obj.data.update()


def join_export_groups(objects,targets):
    """Reduce draw submissions while leaving repair targets individually selectable."""
    targets=set(targets)
    groups={}
    result=[]
    for obj in objects:
        if obj in targets or obj.name.startswith(('AncientSakura','FrontSakura','EastSakura','YoungSakura','Sakura_','Terrain_')):
            result.append(obj);continue
        if obj.name.startswith(('Main_','MainHouse','Upper','Lower','Entry')):group='MainHouse_Static'
        elif obj.name.startswith(('Pavilion','Tea','Study')):group='Pavilions_Static'
        elif any(c.name=='Architecture' for c in obj.users_collection):group='Architecture_Static'
        else:group='Garden_Details'
        groups.setdefault(group,[]).append(obj)
    for group,members in groups.items():
        if len(members)==1:result+=members;continue
        # Apply bevels before joining to preserve every piece's geometry.
        for obj in members:
            select_objects([obj])
            for modifier in list(obj.modifiers):
                bpy.ops.object.modifier_apply(modifier=modifier.name)
        select_objects(members);bpy.ops.object.join()
        obj=bpy.context.object;obj.name=group;result.append(obj)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--draft',action='store_true')
    parser.add_argument('--all-views',action='store_true')
    parser.add_argument('--no-render',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    for folder in ('exports','previews','reports'):(ROOT/folder).mkdir(exist_ok=True)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    for c in list(bpy.data.collections):
        if c.users==0:bpy.data.collections.remove(c)
    bpy.context.preferences.filepaths.save_version=0
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
    mats=make_materials()
    log('Building terrain and garden details')
    landscape=create_landscape(mats)
    log('Building architecture')
    architecture=create_architecture(mats,ground_height)
    log('Building volumetric sakura blossoms')
    plants=create_vegetation(mats,ground_height)
    objects=landscape+architecture['objects']+plants
    parent=bpy.data.objects.new('SeamHeal_SakuraCourtyard',None);scene.collection.objects.link(parent)
    parent.scale=(SCALE,)*3
    parent['asset']='Original Sakura Courtyard for SeamHeal'
    parent['variant']='intact_synthetic_ground_truth'
    parent['units']='metres; construction design unit = 20 mm'
    parent['note']='Complete reference asset, not an output of a repair algorithm'
    for obj in objects:obj.parent=parent
    targets=architecture['repair_targets']
    for key,obj in targets.items():
        obj['repair_case_id']=key;obj['variant']='intact';obj['selectable_repair_target']=True
    bpy.context.view_layer.update()
    report={'asset':'SeamHeal Sakura Courtyard','authoring':'Original procedural geometry and textures; reference images used for composition only',
            'blender_version':bpy.app.version_string,'scale_m_per_design_unit':SCALE,
            'repair_targets_intact':{k:mesh_stats(o) for k,o in targets.items()},
            'regions_blender_face_indices':architecture['regions'],
            'known_limits':['Decorative multi-object scene has intersecting construction pieces and flower parts.',
                            'Only repair targets and joint coupons are individually checked for watertightness.',
                            'Complete meshes are synthetic ground truth, not measured repair or strength results.',
                            'Face indices refer to Blender source topology, not glTF triangle order.']}
    for key,stats in report['repair_targets_intact'].items():
        if not stats['watertight'] or stats['degenerate_faces']:
            raise RuntimeError(f'Invalid intact repair target {key}: {stats}')
    camera,studio_collection=studio();setup_render(args.draft)
    # Start the native file in a useful camera view.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.region_3d.view_perspective='CAMERA'
                area.spaces.active.shading.type='MATERIAL'
    select_objects([targets['roof']])
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'sakura_courtyard_master.blend'))
    log('Saved editable master')
    objects=join_export_groups(objects,targets.values())
    report['web_mesh_objects']=len(objects)
    report['web_triangles']=sum(mesh_stats(o)['triangles'] for o in objects)
    world_points=[o.matrix_world@Vector(v) for o in objects for v in o.bound_box]
    report['overall_dimensions_mm']=[round((max(v[a] for v in world_points)-min(v[a] for v in world_points))*1000,2) for a in range(3)]
    export_glb('sakura_courtyard_intact.glb',objects,parent)
    pristine={k:o.data.copy() for k,o in targets.items()}
    for key,obj in targets.items():export_glb(f'{key}_intact.glb',[obj],parent)
    if not args.no_render:render('courtyard_intact.png')
    for key,obj in targets.items():
        damage(obj,architecture['regions'][key]['through_hole_face_ids'])
        obj['variant']='synthetic_missing_faces'
    parent['variant']='synthetic_missing_faces'
    report['repair_targets_damaged']={k:mesh_stats(o) for k,o in targets.items()}
    for key,stats in report['repair_targets_damaged'].items():
        if not stats['boundary_edges'] or stats['degenerate_faces']:
            raise RuntimeError(f'Invalid damaged repair target {key}: {stats}')
    export_glb('sakura_courtyard_damaged.glb',objects,parent)
    for key,obj in targets.items():export_glb(f'{key}_damaged.glb',[obj],parent)
    select_objects([targets['roof']])
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'sakura_courtyard_damaged.blend'))
    if args.all_views and not args.no_render:
        render('courtyard_damaged.png')
        scene.render.resolution_x=1100 if args.draft else 1600
        scene.render.resolution_y=850 if args.draft else 1200
        for key in ('roof','panel'):
            obj=targets[key]
            region=architecture['regions'][key]
            intact_mesh=pristine[key]
            selected_ids=region.get('top_face_ids',region.get('front_face_ids',[]))
            center=sum((intact_mesh.polygons[i].center for i in selected_ids),Vector())/max(len(selected_ids),1)
            # The panel is viewed from the front, roof from above the front right.
            center=obj.matrix_world@center
            offset=Vector((2.2,-5.4,4.4) if key=='roof' else (1.0,-5.0,1.0))*SCALE
            camera.location=center+offset;look_at(camera,center)
            camera.data.ortho_scale=(4.4 if key=='roof' else 2.75)*SCALE
            render(f'{key}_damaged_detail.png')
            damaged=obj.data;obj.data=pristine[key]
            render(f'{key}_intact_detail.png');obj.data=damaged
    # Restore complete geometry in memory for the source variants and assembly export.
    for key,obj in targets.items():obj.data=pristine[key];obj['variant']='intact'
    parent['variant']='intact_synthetic_ground_truth'
    joint_objects=make_joint_sample(mats)
    joint_root=bpy.data.objects.new('SeamHeal_DovetailStudy',None);scene.collection.objects.link(joint_root);joint_root.scale=(SCALE,)*3
    for obj in joint_objects:obj.parent=joint_root
    joint_root['note']='Assembly geometry study only; no mechanical prediction'
    bpy.context.view_layer.update()
    report['joint_samples']={o.name:mesh_stats(o) for o in joint_objects}
    export_glb('dovetail_assembled.glb',joint_objects,joint_root)
    joint_objects[0].location.x=-.52;joint_objects[1].location.x=.52
    export_glb('dovetail_exploded.glb',joint_objects,joint_root)
    if args.all_views and not args.no_render:
        for obj in objects:obj.hide_render=True
        bpy.data.objects['Studio floor'].location.z=-.008*SCALE
        camera.location=Vector((4.2,-5.4,5.1))*SCALE
        look_at(camera,Vector((0,0,.12))*SCALE);camera.data.ortho_scale=5.4*SCALE
        render('dovetail_exploded.png')
    report['outputs']={p.name:p.stat().st_size for p in (ROOT/'exports').glob('*.glb')}
    (ROOT/'reports'/'asset_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    log('COMPLETE '+json.dumps({k:report[k] for k in ('web_mesh_objects','web_triangles','overall_dimensions_mm')},ensure_ascii=False))


if __name__=='__main__':main()
