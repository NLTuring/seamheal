"""Layered sakura trees with volumetric petals, curved branches and no alpha cards."""
import math
import random
import bpy
from mathutils import Vector


class Builder:
    def __init__(self):
        self.v=[];self.f=[];self.mi=[]

    def face(self, face, material=0):
        self.f.append(tuple(face));self.mi.append(material)

    def tube(self, path, radii, sides=9):
        start=len(self.v)
        for j,p in enumerate(path):
            p=Vector(p)
            tangent=(Vector(path[min(j+1,len(path)-1)])-Vector(path[max(j-1,0)])).normalized()
            axis=tangent.cross(Vector((0,1,0)))
            if axis.length<.01:axis=tangent.cross(Vector((1,0,0)))
            axis.normalize();other=tangent.cross(axis).normalized()
            for k in range(sides):
                a=k*math.tau/sides
                self.v.append(tuple(p+radii[j]*(math.cos(a)*axis+math.sin(a)*other)))
        self.face(tuple(start+i for i in reversed(range(sides))))
        self.face(tuple(start+(len(path)-1)*sides+i for i in range(sides)))
        for j in range(len(path)-1):
            for k in range(sides):
                a=start+j*sides+k;b=start+j*sides+(k+1)%sides
                self.face((a,b,b+sides,a+sides),1 if k%5==0 else 0)

    def petal(self, center, long_axis, wide_axis, normal, r, material):
        center=Vector(center);i=len(self.v)
        outline=[(-.48,0),(-.12,-.37),(.35,-.34),(.57,0),(.35,.34),(-.12,.37)]
        self.v += [tuple(center+long_axis*r*x+wide_axis*r*y+normal*r*(.10+max(x,0)*.18)) for x,y in outline]
        self.v += [tuple(center+normal*r*.26),tuple(center-normal*r*.035)]
        for k in range(6):
            self.face((i+k,i+(k+1)%6,i+6),material)
            self.face((i+(k+1)%6,i+k,i+7),material)

    def flower(self,p,r,rng):
        p=Vector(p)
        n=Vector((rng.uniform(-1,1),rng.uniform(-1,1),rng.uniform(.1,1))).normalized()
        x=n.cross(Vector((0,0,1)))
        if x.length<.01:x=Vector((1,0,0))
        x.normalize();y=n.cross(x).normalized()
        angle=rng.random()*math.tau
        choice=rng.random();m=0 if choice<.48 else (1 if choice<.94 else 2)
        for j in range(5):
            a=angle+j*math.tau/5
            long_axis=x*math.cos(a)+y*math.sin(a)
            wide_axis=-x*math.sin(a)+y*math.cos(a)
            self.petal(p+long_axis*r*.49,long_axis,wide_axis,n,r,m)
        # A tiny deep-pink center ties the five petals together.
        i=len(self.v)
        self.v += [tuple(p+x*r*.12),tuple(p+y*r*.12),tuple(p-x*r*.12),tuple(p-y*r*.12),tuple(p+n*r*.12),tuple(p-n*r*.07)]
        for j in range(4):
            self.face((i+j,i+(j+1)%4,i+4),2)
            self.face((i+(j+1)%4,i+j,i+5),2)

    def object(self,name,collection,materials,smooth=True):
        data=bpy.data.meshes.new(name+'_Mesh');data.from_pydata(self.v,[],self.f);data.update()
        o=bpy.data.objects.new(name,data);collection.objects.link(o)
        for material in materials:data.materials.append(material)
        uv=data.uv_layers.new(name='UVMap')
        for p in data.polygons:
            p.material_index=self.mi[p.index];p.use_smooth=smooth
            for li in p.loop_indices:
                co=data.vertices[data.loops[li].vertex_index].co
                uv.data[li].uv=(co.x*.2,co.z*.2)
        o['role']='decorative_vegetation'
        o['geometry_note']='Volumetric petal geometry; intersecting pieces, not a fused printable solid'
        return o


def create_vegetation(materials, ground_height):
    collection=bpy.data.collections.new('Sakura_Garden')
    bpy.context.scene.collection.children.link(collection)
    objects=[]
    trees=[('AncientSakura',-4.05,3.10,7.15,3.00,1750,702),
           ('FrontSakura',-4.65,-3.00,4.10,1.55,650,705),
           ('EastSakura',4.8,-.7,4.70,1.65,750,713),
           ('YoungSakura',-2.3,-2.0,2.90,1.04,350,729)]
    fallen=Builder()
    for name,cx,cy,h,crown,flower_count,seed in trees:
        rng=random.Random(seed);z0=ground_height(cx,cy)
        wood=Builder();flowers=Builder();leaves=Builder()
        def trunk(t):
            return Vector((cx+math.sin(t*3.4)*h*.035,cy+math.sin(t*4.5)*h*.025,z0+t*h))
        stem=[trunk(t) for t in (0,.16,.33,.51,.69,.85,.99)]
        radii=[h*r for r in (.043,.036,.029,.021,.012,.005,.0007)]
        wood.tube(stem,radii,12)
        clusters=[]
        for j in range(11):
            t=.28+j*.052
            a=j*2.399+rng.uniform(-.25,.25)
            direction=Vector((math.cos(a),math.sin(a),0))
            base=trunk(t)
            reach=crown*(1.07-.44*j/10)*rng.uniform(.90,1.07)
            end=base+direction*reach+Vector((0,0,h*rng.uniform(.10,.19)))
            mid=base+direction*reach*.47+Vector((0,0,h*.035))
            curve=[(1-t)**2*base+2*(1-t)*t*mid+t*t*end for t in [i/7 for i in range(8)]]
            base_radius=h*(.016-.008*j/10)
            wood.tube(curve,[base_radius*(1-i/7)**1.15+.004 for i in range(8)],9)
            for k in range(4):
                progress=.36+k*.19
                start=base.lerp(end,progress)
                side=(-1 if k%2 else 1)
                theta=a+side*rng.uniform(.38,.87)
                twig_dir=Vector((math.cos(theta),math.sin(theta),0))
                tip=start+twig_dir*crown*rng.uniform(.20,.36)+Vector((0,0,h*rng.uniform(.06,.14)))
                middle=start.lerp(tip,.55)+Vector((0,0,-h*.015))
                curve=[(1-t)**2*start+2*(1-t)*t*middle+t*t*tip for t in [i/5 for i in range(6)]]
                wood.tube(curve,[h*.0048*(1-i/5)+.002 for i in range(6)],7)
                clusters.append((tip,crown*rng.uniform(.13,.21),h*rng.uniform(.035,.060)))
                for side2 in (-1,1):
                    sp=start.lerp(tip,.67)
                    twig_end=tip+Vector((-twig_dir.y,twig_dir.x,.4))*side2*crown*.085
                    wood.tube([sp,twig_end],[h*.0018,.0018],5)
        clusters += [(trunk(.91),crown*.21,h*.075),(trunk(.99),crown*.16,h*.043)]
        for _ in range(flower_count):
            center,spread,vertical=rng.choice(clusters)
            angle=rng.random()*math.tau
            radius=spread*math.sqrt(rng.random())
            p=center+Vector((math.cos(angle)*radius,math.sin(angle)*radius,rng.uniform(-vertical,vertical)))
            flowers.flower(p,rng.uniform(.085,.125)*(h/4.5)**.16,rng)
            if rng.random()<.13:
                long=Vector((math.cos(angle),math.sin(angle),rng.uniform(.1,.4))).normalized()
                wide=Vector((-long.y,long.x,0)).normalized()
                leaves.petal(p-long*.07,long,wide,Vector((0,0,1)),rng.uniform(.11,.18),0)
        for k in range(6):
            a=k*math.tau/6+rng.random()*.4
            start=trunk(.07)
            end=Vector((cx+math.cos(a)*h*.10,cy+math.sin(a)*h*.10,ground_height(cx+math.cos(a)*h*.10,cy+math.sin(a)*h*.10)+.02))
            wood.tube([start,start.lerp(end,.65),end],[h*.025,h*.011,.004],8)
        objects += [wood.object(name+'_Branches',collection,[materials['bark'],materials['bark_light']]),
                    flowers.object(name+'_Blossoms',collection,[materials['blossom_pale'],materials['blossom_pink'],materials['blossom_deep']]),
                    leaves.object(name+'_YoungLeaves',collection,[materials['leaf']])]
        for _ in range(65):
            a=rng.random()*math.tau;r=rng.random()*crown
            x,y=cx+math.cos(a)*r,cy+math.sin(a)*r
            if abs(x)>5.8 or abs(y)>4.6:continue
            z=ground_height(x,y)+.022
            u=Vector((math.cos(a),math.sin(a),0));v=Vector((-math.sin(a),math.cos(a),0))
            fallen.petal((x,y,z),u,v,Vector((0,0,1)),rng.uniform(.045,.080),rng.randrange(2))
    objects.append(fallen.object('Sakura_FallenPetals',collection,[materials['blossom_pale'],materials['blossom_pink']]))
    return objects
