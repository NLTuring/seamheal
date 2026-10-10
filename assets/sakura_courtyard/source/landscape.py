"""Terrain, stream, paths, garden furniture and an independent dovetail sample."""
import math
import random
import bpy
import bmesh
from mathutils import Vector

COL = None
MATS = None
OBJECTS = []


def ground_height(x, y):
    z = .60 + .13*(y+4.8) + .18*math.sin(x*.45)*math.cos(y*.55) + .07*math.sin(x*1.4+y*.8)
    if y < -1.05:
        stream_x = 1.02 + .19*math.sin((y+4.8)*2.0)
        z -= .12*math.exp(-((x-stream_x)/.40)**2)
    return z


def mesh(name, vertices, faces, mat, indices=None, uv=None, smooth=False):
    data = bpy.data.meshes.new(name+'_Mesh')
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    for key in ([mat] if isinstance(mat,str) else mat):
        data.materials.append(MATS[key])
    bm=bmesh.new(); bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bm.to_mesh(data); bm.free()
    data.update()
    layer = data.uv_layers.new(name='UVMap')
    for p in data.polygons:
        p.use_smooth = smooth
        if indices is not None: p.material_index=indices[p.index]
        for li in p.loop_indices:
            vi=data.loops[li].vertex_index
            co=data.vertices[vi].co
            if uv is not None: coord=uv[vi]
            elif abs(p.normal.z)>.5: coord=(co.x*.24,co.y*.24)
            elif abs(p.normal.y)>.5: coord=(co.x*.25,co.z*.5)
            else: coord=(co.y*.25,co.z*.5)
            layer.data[li].uv=coord
    OBJECTS.append(obj)
    return obj


def box(name, center, size, mat, bevel=.015):
    x,y,z=center; a,b,c=[v/2 for v in size]
    v=[(x-a,y-b,z-c),(x+a,y-b,z-c),(x+a,y+b,z-c),(x-a,y+b,z-c),
       (x-a,y-b,z+c),(x+a,y-b,z+c),(x+a,y+b,z+c),(x-a,y+b,z+c)]
    f=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    o=mesh(name,v,f,mat)
    if bevel:
        mod=o.modifiers.new('Rounded artisan edges','BEVEL');mod.width=bevel;mod.segments=2
    return o


def beam(name,a,b,r,mat,r2=None,segments=8):
    a,b=Vector(a),Vector(b); direction=(b-a).normalized()
    axis=direction.cross(Vector((0,0,1)))
    if axis.length<.01: axis=direction.cross(Vector((0,1,0)))
    axis.normalize(); other=direction.cross(axis).normalized()
    verts=[]
    for center,radius in [(a,r),(b,r if r2 is None else r2)]:
        verts.extend(tuple(center+radius*(math.cos(i*math.tau/segments)*axis+math.sin(i*math.tau/segments)*other)) for i in range(segments))
    faces=[tuple(reversed(range(segments))),tuple(range(segments,segments*2))]
    faces += [(i,(i+1)%segments,(i+1)%segments+segments,i+segments) for i in range(segments)]
    return mesh(name,verts,faces,mat,smooth=True)


def terrain():
    nx,ny=80,64
    verts=[]
    for j in range(ny+1):
        v=j/ny*2-1
        for i in range(nx+1):
            u=i/nx*2-1
            x=u*6*(1-.035*abs(v)**10)
            y=v*4.8*(1-.035*abs(u)**10)
            verts.append((x,y,ground_height(x,y)))
    faces=[]; inds=[]
    for j in range(ny):
        for i in range(nx):
            a=j*(nx+1)+i
            faces.append((a,a+1,a+nx+2,a+nx+1)); inds.append(0)
    boundary=list(range(nx+1))
    boundary += [j*(nx+1)+nx for j in range(1,ny+1)]
    boundary += [ny*(nx+1)+i for i in range(nx-1,-1,-1)]
    boundary += [j*(nx+1) for j in range(ny-1,0,-1)]
    previous=boundary
    for level in range(1,7):
        ring=[]
        for k,top in enumerate(boundary):
            x,y,z=verts[top]
            t=level/6
            rock=.04*math.sin(k*1.73+level*2.13)*math.sin(t*math.pi)
            ring.append(len(verts))
            verts.append((x*(1-.025*t)+rock,y*(1-.025*t)+rock,z*(1-t)-.92*t))
        for k in range(len(ring)):
            q=(k+1)%len(ring)
            faces.append((previous[q],previous[k],ring[k],ring[q]));inds.append(1)
        previous=ring
    faces.append(tuple(reversed(previous)));inds.append(1)
    return mesh('Terrain_ClosedRockPlinth',verts,faces,['ground','stone'],inds)


def catmull(points, steps=12):
    q=[Vector(points[0])]+[Vector(p) for p in points]+[Vector(points[-1])]
    result=[]
    for k in range(1,len(q)-2):
        p0,p1,p2,p3=q[k-1:k+3]
        for t in [i/steps for i in range(steps)]:
            result.append(.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t))
    result.append(Vector(points[-1]))
    return result


def ribbon(name,points,width,mat,raise_z=.02):
    points=catmull(points)
    verts=[]
    for i,p in enumerate(points):
        tangent=(points[min(i+1,len(points)-1)]-points[max(0,i-1)]).normalized()
        normal=Vector((-tangent.y,tangent.x))
        for side in (-1,1):
            x,y=p+normal*width*.5*side
            verts.append((x,y,ground_height(x,y)+raise_z))
    count=len(verts)
    verts += [(x,y,z-.035) for x,y,z in verts]
    faces=[]
    for i in range(len(points)-1):
        a=2*i
        faces += [(a,a+2,a+3,a+1),(a+count+1,a+count+3,a+count+2,a+count),
                  (a,a+count,a+count+2,a+2),(a+3,a+count+3,a+count+1,a+1)]
    faces += [(0,1,count+1,count),(count-2,count*2-2,count*2-1,count-1)]
    return mesh(name,verts,faces,mat)


def rock(name,x,y,size,seed):
    rng=random.Random(seed)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,radius=1)
    obj=bpy.context.object;obj.name=name
    for c in list(obj.users_collection):c.objects.unlink(obj)
    COL.objects.link(obj)
    for v in obj.data.vertices:
        wobble=rng.uniform(.84,1.16)
        v.co.x*=size*wobble;v.co.y*=size*.76*wobble;v.co.z*=size*.52*wobble
        v.co += Vector((x,y,ground_height(x,y)+size*.15))
    obj.data.materials.append(MATS['stone'])
    layer=obj.data.uv_layers.new(name='UVMap')
    for loop in obj.data.loops:
        v=obj.data.vertices[loop.vertex_index].co
        layer.data[loop.index].uv=(v.x*.6,v.z*.6)
    bevel=obj.modifiers.new('Weathered stone corners','BEVEL');bevel.width=.025;bevel.segments=2
    OBJECTS.append(obj)
    return obj


def lantern(x,y,index):
    z=ground_height(x,y)
    label=f'GardenLantern_{index:02d}'
    box(label+'_foot',(x,y,z+.06),(.38,.38,.12),'stone',.025)
    beam(label+'_shaft',(x,y,z+.12),(x,y,z+.73),.065,'stone',.08)
    box(label+'_tray',(x,y,z+.75),(.34,.34,.09),'stone',.02)
    box(label+'_warm_glass',(x,y,z+.91),(.21,.21,.26),'lantern_glow',.015)
    for dx in (-.13,.13):
        for dy in (-.13,.13):
            box(label+'_post',(x+dx,y+dy,z+.91),(.035,.035,.29),'wood_dark',.004)
    v=[(x-.28,y-.28,z+1.09),(x+.28,y-.28,z+1.09),(x+.28,y+.28,z+1.09),(x-.28,y+.28,z+1.09),
       (x-.11,y-.11,z+1.24),(x+.11,y-.11,z+1.24),(x+.11,y+.11,z+1.24),(x-.11,y+.11,z+1.24)]
    mesh(label+'_cap',v,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],'roof_trim')
    beam(label+'_finial',(x,y,z+1.24),(x,y,z+1.37),.06,'brass',.018)


def bridge():
    cx,cy=1.08,-2.48
    width,length=.82,2.15
    for i in range(17):
        t=i/16
        x=cx+(t-.5)*length
        z=ground_height(cx,cy)+.28+.22*math.sin(t*math.pi)
        box(f'Bridge_Deck_{i:02d}',(x,cy,z),(.12,width,.075),'wood',.012)
    for side in (-1,1):
        y=cy+side*(width*.5+.045)
        for i in range(5):
            t=i/4;x=cx+(t-.5)*length
            z=ground_height(cx,cy)+.28+.22*math.sin(t*math.pi)
            beam('Bridge_RailPost',(x,y,z),(x,y,z+.47),.025,'redwood',segments=8)
        for i in range(16):
            t1,t2=i/16,(i+1)/16
            a=(cx+(t1-.5)*length,y,ground_height(cx,cy)+.74+.22*math.sin(t1*math.pi))
            b=(cx+(t2-.5)*length,y,ground_height(cx,cy)+.74+.22*math.sin(t2*math.pi))
            beam('Bridge_CurvedHandrail',a,b,.027,'redwood')
    return cx,cy


def tufts():
    rng=random.Random(92)
    verts=[];faces=[]
    centers=[(-5.6,-1.6),(-4.5,-4.3),(-3.2,-3.2),(-2.1,-.45),(.2,-4.1),(1.85,-3.5),(2.05,-1.6),(5.1,1.4),(4.9,-4.2),(-.5,3.9)]
    for cx,cy in centers:
        for _ in range(17):
            x,y=cx+rng.uniform(-.27,.27),cy+rng.uniform(-.22,.22)
            z=ground_height(x,y)+.015
            angle=rng.random()*math.tau;h=rng.uniform(.10,.33);w=.018
            dx,dy=math.cos(angle),math.sin(angle)
            i=len(verts)
            verts += [(x-dy*w,y+dx*w,z),(x+dy*w,y-dx*w,z),(x+dx*h*.45,y+dy*h*.45,z+h),
                      (x,y,z+.009)]
            faces += [(i,i+1,i+2),(i+1,i,i+3),(i+2,i+1,i+3),(i,i+2,i+3)]
    mesh('Garden_GrassTufts',verts,faces,'leaf')


def create_landscape(materials):
    global COL,MATS,OBJECTS
    MATS=materials;OBJECTS=[]
    COL=bpy.data.collections.new('Landscape');bpy.context.scene.collection.children.link(COL)
    terrain()
    ribbon('Garden_GravelPath',[(-5,-4.3),(-4.1,-2.5),(-2.8,-.9),(-1.25,-.1),(.35,.06)],.67,'path')
    ribbon('Path_TeaPavilion',[(1.95,-2.48),(2.6,-2.45),(3.7,-2.2)],.54,'path')
    ribbon('Stream_JadeWater',[(1.05,-4.66),(1.21,-4.1),(.95,-3.3),(1.08,-2.48),(1.13,-1.8),(.95,-1.12)],.48,'water',.028)
    bridge()
    for index,(x,y) in enumerate([(-4.5,-3.9),(-3.1,-1.2),(-.8,.45),(2.4,-1.55),(4.3,-2.05),(4.65,2.6)]):
        lantern(x,y,index)
    rng=random.Random(88)
    for i in range(39):
        if i<22:
            y=rng.uniform(-4.5,-1.15);x=1.04+(1 if i%2 else -1)*rng.uniform(.35,.55)
        else:
            x,y=rng.choice([(-5.3,-1.5),(-3.2,-3.4),(-1.5,.8),(4.9,1.8)])
            x+=rng.uniform(-.5,.5);y+=rng.uniform(-.4,.4)
        rock(f'GardenStone_{i:02d}',x,y,rng.uniform(.12,.35),i+30)
    # Fence and bench make the scale legible without distracting from the house.
    for i in range(9):
        x=2.35+i*.30;y=-.86;z=ground_height(x,y)
        box('GardenFence_Post',(x,y,z+.34),(.065,.075,.68),'wood_dark',.008)
    for height in (.24,.52):
        a=(2.30,-.86,ground_height(2.30,-.86)+height)
        b=(4.83,-.86,ground_height(4.83,-.86)+height)
        beam('GardenFence_Rail',a,b,.039,'redwood')
    bx,by=-3.4,-2.8;bz=ground_height(bx,by)
    for dx in (-.49,.49): box('Bench_Leg',(bx+dx,by,bz+.19),(.1,.35,.38),'wood_dark')
    for j in range(3):box('Bench_Seat',(bx,by+(j-1)*.115,bz+.42),(1.24,.1,.07),'wood')
    tufts()
    return list(OBJECTS)


def make_joint_sample(materials):
    global COL,MATS,OBJECTS
    MATS=materials;OBJECTS=[]
    COL=bpy.data.collections.new('Joint_Study');bpy.context.scene.collection.children.link(COL)
    shapes=[('Dovetail_A',[(-1.6,-.42),(0,-.42),(0,-.14),(.28,-.27),(.28,.27),(0,.14),(0,.42),(-1.6,.42)],'wood'),
            ('Dovetail_B',[(.015,-.42),(1.6,-.42),(1.6,.42),(.015,.42),(.015,.16),(.30,.29),(.30,-.29),(.015,-.16)],'roof_trim')]
    for name,poly,material in shapes:
        n=len(poly);verts=[(x,y,z) for z in (0,.24) for x,y in poly]
        faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        obj=mesh(name,verts,faces,material)
        obj['purpose']='Illustrative keyed assembly sample; no strength calibration'
        obj['design_clearance_mm']=.3
    return list(OBJECTS)
