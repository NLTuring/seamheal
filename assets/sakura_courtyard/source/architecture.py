"""Original Sakura Court architecture, authored for SeamHeal demonstration.

The two repair targets are closed, indexed grid shells with conventional UVs.
The architectural ensemble contains intersecting separate construction pieces;
it is a display scene, not a claim of a single printable solid.
"""
import math
from collections import Counter

import bpy
import bmesh
from mathutils import Vector


_COLLECTION = None
_OBJECTS = []
_MATERIALS = {}


def _mesh(name, vertices, faces, material, uvcoords=None, smooth=False):
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        polygon.use_smooth = smooth
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            if uvcoords is not None:
                uv = uvcoords[vertex_index]
            else:
                co = mesh.vertices[vertex_index].co
                normal = polygon.normal
                if abs(normal.z) >= max(abs(normal.x), abs(normal.y)):
                    uv = (co.x * .45, co.y * .45)
                elif abs(normal.y) >= abs(normal.x):
                    uv = (co.x * .45, co.z * .45)
                else:
                    uv = (co.y * .45, co.z * .45)
            layer.data[loop_index].uv = uv
    obj = bpy.data.objects.new(name, mesh)
    _COLLECTION.objects.link(obj)
    obj.data.materials.append(_MATERIALS[material])
    _OBJECTS.append(obj)
    return obj


def _recalc(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


_BOX_FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
              (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def _box_data(center, size, yaw=0):
    cx, cy, cz = center
    hx, hy, hz = [v / 2 for v in size]
    cs, sn = math.cos(yaw), math.sin(yaw)
    vertices = []
    for x, y, z in [(-hx, -hy, -hz), (hx, -hy, -hz),
                    (hx, hy, -hz), (-hx, hy, -hz),
                    (-hx, -hy, hz), (hx, -hy, hz),
                    (hx, hy, hz), (-hx, hy, hz)]:
        vertices.append((cx + cs*x - sn*y, cy + sn*x + cs*y, cz + z))
    return vertices, _BOX_FACES


def _boxes(name, items, material):
    verts, faces = [], []
    for item in items:
        center, size = item[:2]
        yaw = item[2] if len(item) > 2 else 0
        v, f = _box_data(center, size, yaw)
        start = len(verts)
        verts.extend(v)
        faces.extend(tuple(start + i for i in face) for face in f)
    return _mesh(name, verts, faces, material)


def _box(name, center, size, material, yaw=0, bevel=0):
    obj = _boxes(name, [(center, size, yaw)], material)
    if bevel:
        modifier = obj.modifiers.new("Soft hand-finished edges", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
        modifier.affect = 'EDGES'
    return obj


def _tube(name, points, radius, material, sides=8):
    """Closed tube following a centerline; only used on nondegenerate paths."""
    vertices, faces = [], []
    for index, xyz in enumerate(points):
        pos = Vector(xyz)
        tangent = Vector(points[min(index + 1, len(points)-1)]) - Vector(points[max(0, index-1)])
        tangent.normalize()
        reference = Vector((0, 0, 1)) if abs(tangent.z) < .95 else Vector((0, 1, 0))
        axis_a = tangent.cross(reference).normalized()
        axis_b = tangent.cross(axis_a).normalized()
        for side in range(sides):
            angle = side * 2 * math.pi / sides
            vertices.append(tuple(pos + radius * (axis_a*math.cos(angle) + axis_b*math.sin(angle))))
    for ring in range(len(points)-1):
        for side in range(sides):
            a = ring*sides + side
            b = ring*sides + (side+1) % sides
            faces.append((a, b, b+sides, a+sides))
    faces.append(tuple(reversed(range(sides))))
    faces.append(tuple((len(points)-1)*sides + i for i in range(sides)))
    obj = _mesh(name, vertices, faces, material, smooth=True)
    _recalc(obj)
    return obj


def _shell(name, vertices, faces, uvcoords, offset, material):
    """Thicken an open sheet without duplicating or merging its grid vertices."""
    count = len(vertices)
    lower = [(x+offset[0], y+offset[1], z+offset[2]) for x, y, z in vertices]
    shell_faces = list(faces)
    shell_faces.extend(tuple(i+count for i in reversed(face)) for face in faces)
    edges = Counter()
    directed = {}
    for face in faces:
        for a, b in zip(face, face[1:]+face[:1]):
            key = tuple(sorted((a, b)))
            edges[key] += 1
            directed[key] = (a, b)
    for edge, uses in edges.items():
        if uses == 1:
            a, b = directed[edge]
            shell_faces.append((b, a, a+count, b+count))
    obj = _mesh(name, vertices+lower, shell_faces, material, uvcoords+uvcoords)
    _recalc(obj)
    return obj


def _roof_height(t, edge, eave, rise, curl):
    return eave + rise*(.27*t + .73*t*t) + curl*(abs(edge)**8)*(1-t)**2


def _roof_slope(name, cx, cy, width, depth, ridge, eave, rise,
                sign, nx=40, ny=16, target=False):
    hw, hd, rr = width/2, depth/2, ridge/2
    vertices, uvcoords, faces = [], [], []
    for j in range(ny+1):
        t = j/ny
        half = hw*(1-t) + rr*t
        for i in range(nx+1):
            u = i/nx
            edge = 2*u-1
            # A tiny integrated barrel profile adds depth without hiding a hole.
            rib = .009 * math.sin(u * 22 * math.pi)**2 * math.sin(math.pi*t)
            vertices.append((cx+edge*half, cy+sign*hd*(1-t),
                             _roof_height(t, edge, eave, rise, .17)+rib))
            uvcoords.append((u, t))
    for j in range(ny):
        for i in range(nx):
            a = j*(nx+1)+i
            faces.append((a, a+1, a+nx+2, a+nx+1))
    obj = _shell(name, vertices, faces, uvcoords, (0, 0, -.095), "roof")
    # The closed sides stay flat and make the physical roof thickness visible.
    for poly in obj.data.polygons[:nx*ny]:
        poly.use_smooth = True
    region = None
    if target:
        selected = [j*nx+i for j in range(ny) for i in range(nx)
                    if .34 <= (i+.5)/nx <= .55 and .26 <= (j+.5)/ny <= .63]
        region = {
            "object": obj.name,
            "kind": "closed curved roof grid",
            "grid_columns": nx, "grid_rows": ny,
            "top_face_ids": selected,
            "bottom_face_ids": [i+nx*ny for i in selected],
            "through_hole_face_ids": selected+[i+nx*ny for i in selected],
            "uv_bounds": [.34, .26, .55, .63],
            "notes": "Top and bottom indices describe the same roof patch. Remove both for a through-hole. No overlay geometry covers this patch.",
        }
        obj["repair_target"] = "roof_geometry_and_uv"
        obj["grid_columns"] = nx
        obj["grid_rows"] = ny
    return obj, region


def _roof_hip(name, cx, cy, width, depth, ridge, eave, rise, sign, n=20):
    hw, hd, rr = width/2, depth/2, ridge/2
    vertices, uvcoords, faces, starts = [], [], [], []
    for j in range(n+1):
        t = j/n
        count = n-j
        starts.append(len(vertices))
        for i in range(count+1):
            edge = 2*i/count-1 if count else 0
            vertices.append((cx+sign*(hw*(1-t)+rr*t),
                             cy+hd*(1-t)*edge,
                             _roof_height(t, edge, eave, rise, .17)))
            uvcoords.append(((edge+1)/2*(1-t)+t/2, t))
    for j in range(n):
        count = n-j
        for i in range(count):
            a, b = starts[j]+i, starts[j+1]+i
            if i < count-1:
                faces.append((a, a+1, b+1, b))
            else:
                faces.append((a, a+1, b))
    obj = _shell(name, vertices, faces, uvcoords, (0, 0, -.095), "roof")
    for p in obj.data.polygons[:len(faces)]:
        p.use_smooth = True
    return obj


def _hip_roof(label, cx, cy, width, depth, ridge, eave, rise, target=False):
    front, region = _roof_slope("Roof_RepairTarget" if target else label+"_Front",
                               cx, cy, width, depth, ridge, eave, rise,
                               -1, nx=72 if target else 44, ny=30 if target else 17, target=target)
    _roof_slope(label+"_Rear", cx, cy, width, depth, ridge, eave, rise, 1,
                nx=48, ny=18)
    _roof_hip(label+"_EastHip", cx, cy, width, depth, ridge, eave, rise, 1)
    _roof_hip(label+"_WestHip", cx, cy, width, depth, ridge, eave, rise, -1)
    # Rolled eave edges and raised ceramic hip ridges form the silhouette.
    for side in (-1, 1):
        points = [(cx+(2*i/32-1)*width/2, cy+side*depth/2,
                   eave + .17*abs(2*i/32-1)**8-.025) for i in range(33)]
        _tube(label+f"_Eave_{side}", points, .048, "roof_trim")
        points = [(cx+side*width/2, cy+(2*i/24-1)*depth/2,
                   eave+.17*abs(2*i/24-1)**8-.025) for i in range(25)]
        _tube(label+f"_EndEave_{side}", points, .047, "roof_trim")
        for end in (-1, 1):
            points = []
            for i in range(25):
                t = i/24
                points.append((cx+end*(width/2*(1-t)+ridge/2*t),
                               cy+side*depth/2*(1-t),
                               _roof_height(t, 1, eave, rise, .17)+.054))
            _tube(label+f"_HipRidge_{side}_{end}", points, .072, "roof_trim", 10)
    # Curved ridge-end finials are deliberately modest at miniature scale.
    points = []
    for i in range(39):
        u = i/38
        xx = (u*2-1)*(ridge/2+.14)
        tip = .17*max(0, (abs(xx)-ridge*.36)/(ridge*.14+.14))**2
        points.append((cx+xx, cy, eave+rise+.11+tip))
    _tube(label+"_CrownRidge", points, .092, "roof_trim", 12)
    for side in (-1, 1):
        _tube(label+f"_RidgeBrassCap_{side}",
              [(cx+side*(ridge/2+.10), cy, eave+rise+.245),
               (cx+side*(ridge/2+.20), cy, eave+rise+.305)], .067, "brass", 10)
    # Wooden soffit beams are restricted to the roof perimeter.
    beams = []
    for side in (-1, 1):
        beams.append(((cx, cy+side*(depth/2-.13), eave-.14),
                      (width-.25, .13, .13)))
    _boxes(label+"_SoffitBeams", beams, "wood_dark")
    return front, region


def _window(name, center, width, height, yaw=0, divisions=8):
    cx, cy, cz = center
    cs, sn = math.cos(yaw), math.sin(yaw)
    def world(x, y, z):
        return cx+cs*x-sn*y, cy+sn*x+cs*y, cz+z
    _box(name+"_Paper", world(0, .025, 0), (width, .035, height), "glass", yaw)
    frame = []
    for x in (-width/2, width/2):
        frame.append((world(x, -.02, 0), (.06, .08, height+.08), yaw))
    for z in (-height/2, height/2):
        frame.append((world(0, -.025, z), (width+.08, .08, .065), yaw))
    for i in range(1, divisions):
        frame.append((world(-width/2+width*i/divisions, -.027, 0),
                      (.018, .035, height), yaw))
    rows = max(4, round(height/.14))
    for i in range(1, rows):
        frame.append((world(0, -.028, -height/2+height*i/rows),
                      (width, .035, .018), yaw))
    _boxes(name+"_CedarLattice", frame, "wood_dark")
    _box(name+"_Sill", world(0, -.08, -height/2-.065),
         (width+.19, .19, .07), "wood", yaw)


def _panel(cx, cy, cz, width=2.12, height=1.12):
    nx, nz = 40, 24
    vertices, faces, uvs = [], [], []
    for j in range(nz+1):
        for i in range(nx+1):
            u, v = i/nx, j/nz
            vertices.append((cx+(u-.5)*width, cy, cz+(v-.5)*height))
            uvs.append((u, v))
    for j in range(nz):
        for i in range(nx):
            a = j*(nx+1)+i
            faces.append((a, a+1, a+nx+2, a+nx+1))
    obj = _shell("Panel_RepairTarget", vertices, faces, uvs, (0, .075, 0), "painted_panel")
    obj["repair_target"] = "painted_surface_and_uv"
    selected = [j*nx+i for j in range(nz) for i in range(nx)
                if .37 <= (i+.5)/nx <= .60 and .33 <= (j+.5)/nz <= .72]
    frame = []
    for x in (-width/2-.025, width/2+.025):
        frame.append(((cx+x, cy-.023, cz), (.065, .12, height+.16)))
    for z in (-height/2-.03, height/2+.03):
        frame.append(((cx, cy-.024, cz+z), (width+.11, .12, .065)))
    _boxes("MainHall_PaintedPanelFrame", frame, "wood_dark")
    _box("MainHall_PaintedPanelLowerTrim", (cx, cy-.05, cz-height/2-.12),
         (width+.20, .17, .06), "wood")
    region = {
        "object": obj.name, "kind": "closed painted panel grid",
        "grid_columns": nx, "grid_rows": nz,
        "front_face_ids": selected,
        "back_face_ids": [i+nx*nz for i in selected],
        "through_hole_face_ids": selected+[i+nx*nz for i in selected],
        "uv_bounds": [.37, .33, .60, .72],
        "notes": "Front surface has a single continuous 0..1 UV layout. The original blossom painting remains visible around the patch.",
    }
    return obj, region


def _posts_and_brackets(label, cx, cy, width, depth, bottom, top, spacing=.9):
    columns, brackets = [], []
    num = max(2, round(width/spacing))
    for side in (-1, 1):
        for i in range(num+1):
            x, y = cx-width/2+width*i/num, cy+side*depth/2
            columns.append(((x, y, (bottom+top)/2), (.13, .13, top-bottom)))
            brackets.extend([
                ((x, y, top-.18), (.33, .23, .10)),
                ((x, y, top-.08), (.48, .30, .085)),
                ((x, y, bottom+.065), (.21, .21, .13)),
            ])
    _boxes(label+"_Posts", columns, "wood")
    _boxes(label+"_BracketCapitals", brackets, "wood_dark")
    items = []
    for side in (-1, 1):
        items.append(((cx, cy+side*depth/2, top), (width+.18, .17, .17)))
        items.append(((cx+side*width/2, cy, top), (.17, depth+.15, .17)))
    _boxes(label+"_Lintels", items, "wood")


def _lantern(name, x, y, z, scale=1):
    _box(name+"_Glow", (x, y, z), (.18*scale, .18*scale, .27*scale), "glass", bevel=.009)
    slats = []
    for dx in (-.096, .096):
        for dy in (-.096, .096):
            slats.append(((x+dx*scale, y+dy*scale, z), (.025*scale, .025*scale, .33*scale)))
    for dz in (-.16, .16):
        slats.append(((x, y, z+dz*scale), (.235*scale, .235*scale, .035*scale)))
    _boxes(name+"_Frame", slats, "wood_dark")
    _tube(name+"_Hanger", [(x, y, z+.18*scale), (x, y, z+.40*scale)], .012*scale, "brass", 6)


def _main_hall(ground_height):
    cx, cy, width, depth = 1.30, 1.70, 5.40, 3.30
    g = ground_height(cx, cy)
    floor = g+.30
    _box("MainHall_StonePlinth", (cx, cy, g+.10), (width+.38, depth+.45, .34), "stone", bevel=.05)
    _box("MainHall_DarkFoundation", (cx, cy, g+.31), (width+.24, depth+.29, .18), "wood_dark", bevel=.025)
    _box("MainHall_PlasterBody", (cx, cy, floor+.90), (width-.08, depth-.10, 1.80), "plaster")
    # Boarded veranda on the southern and eastern elevations.
    planks = []
    for i in range(28):
        x = cx-width/2-.18+(width+.36)*(i+.5)/28
        planks.append(((x, cy-depth/2-.24, floor+.045), ((width+.36)/28-.013, .62, .09)))
    for i in range(18):
        y = cy-depth/2+depth*(i+.5)/18
        planks.append(((cx+width/2+.22, y, floor+.045), (.52, depth/18-.012, .09)))
    _boxes("MainHall_VerandaBoards", planks, "wood")
    _posts_and_brackets("MainHall", cx, cy, width, depth, floor, g+2.10, spacing=.91)
    # Fascia and wainscot divide the cream walls into crafted timber panels.
    belts = []
    for z, h in [(floor+.20, .29), (floor+1.60, .11)]:
        belts.extend([
            ((cx, cy-depth/2-.015, z), (width, .075, h)),
            ((cx+width/2+.015, cy, z), (.075, depth, h)),
            ((cx, cy+depth/2+.015, z), (width, .075, h)),
        ])
    _boxes("MainHall_Wainscot", belts, "wood_dark")
    panel, panel_region = _panel(cx-1.17, cy-depth/2-.069, floor+.97)
    # Main entrance, and lattice windows along the east wall.
    _window("MainHall_EntryLeft", (cx+1.00, cy-depth/2-.105, floor+.99), .66, 1.43, divisions=5)
    _window("MainHall_EntryRight", (cx+1.72, cy-depth/2-.105, floor+.99), .66, 1.43, divisions=5)
    for j in range(3):
        _window("MainHall_EastWindow_"+str(j),
                (cx+width/2+.075, cy-depth/2+.61+j*1.04, floor+1.00),
                .77, 1.12, yaw=math.pi/2, divisions=7)
    for i in range(3):
        _box("MainHall_EntryStep_"+str(i),
             (cx+1.34, cy-depth/2-.67-.17*i, floor-.06-.11*i),
             (1.62+.14*i, .43+.02*i, .13), "stone", bevel=.025)
    for side in (-1, 1):
        _lantern("MainHall_EntranceLantern_"+str(side), cx+1.34+side*.89,
                 cy-depth/2-.26, floor+1.62, .78)
    _hip_roof("MainHall_LowerRoof", cx, cy, 6.19, 4.28, 3.62,
              g+2.16, .98)
    # Clerestory above the surrounding lower roof gives the double-tier silhouette.
    upper_bottom, upper_top = g+2.71, g+3.65
    upper_width, upper_depth = 4.35, 2.02
    _box("MainHall_ClerestoryPlaster", (cx, cy, (upper_bottom+upper_top)/2),
         (upper_width, upper_depth, upper_top-upper_bottom), "plaster")
    _posts_and_brackets("MainHall_Clerestory", cx, cy, upper_width, upper_depth,
                        upper_bottom, upper_top, spacing=.82)
    band = []
    for z in (upper_bottom+.17, upper_top-.15):
        for side in (-1, 1):
            band.append(((cx, cy+side*upper_depth/2, z), (upper_width+.12, .10, .07)))
    _boxes("MainHall_ClerestoryBands", band, "wood_dark")
    roof, roof_region = _hip_roof("MainHall_UpperRoof", cx, cy, 5.72, 3.65, 3.04,
                                  g+3.71, 1.19, target=True)
    return roof, panel, roof_region, panel_region


def _pavilion(label, cx, cy, width, depth, ground_height, enclosed=False):
    g = ground_height(cx, cy)
    floor, top = g+.24, g+1.77
    _box(label+"_StoneBase", (cx, cy, g+.06), (width+.25, depth+.25, .20), "stone", bevel=.035)
    _box(label+"_DeckRim", (cx, cy, floor-.05), (width+.19, depth+.20, .17), "wood_dark")
    boards = []
    for i in range(15):
        boards.append(((cx-width/2+width*(i+.5)/15, cy, floor+.04),
                       (width/15-.01, depth, .075)))
    _boxes(label+"_DeckBoards", boards, "wood")
    _posts_and_brackets(label, cx, cy, width-.16, depth-.15, floor, top, spacing=width*.60)
    if enclosed:
        _box(label+"_RearPlaster", (cx, cy+depth/2-.09, floor+.68),
             (width-.15, .11, 1.36), "plaster")
        _box(label+"_EastPlaster", (cx+width/2-.09, cy+.14, floor+.68),
             (.11, depth-.35, 1.36), "plaster")
        _window(label+"_RearLattice", (cx, cy+depth/2-.17, floor+.89),
                width*.76, .66, divisions=9)
        _window(label+"_FrontScreen", (cx+width*.22, cy-depth/2+.04, floor+.80),
                width*.38, 1.25, divisions=5)
    else:
        # Raised bench and low rail leave the airy tea shelter open to the camera.
        _box(label+"_RearBench", (cx, cy+depth*.27, floor+.40),
             (width*.82, .34, .085), "redwood", bevel=.018)
        for side in (-1, 1):
            _box(label+f"_BenchLeg_{side}",
                 (cx+side*width*.29, cy+depth*.27, floor+.23), (.12, .24, .36), "wood_dark")
        _box(label+"_TeaTable", (cx-.15, cy-.12, floor+.42), (.57, .44, .075), "wood", bevel=.035)
        _box(label+"_TableStem", (cx-.15, cy-.12, floor+.25), (.16, .17, .33), "wood_dark")
    rails = []
    for side in (-1, 1):
        for z in (floor+.20, floor+.64):
            rails.append(((cx+side*(width/2-.04), cy, z), (.065, depth-.12, .065)))
        for i in range(1, 6):
            rails.append(((cx+side*(width/2-.04), cy-depth/2+depth*i/6, floor+.42),
                          (.042, .035, .40)))
    _boxes(label+"_SideBalustrades", rails, "wood")
    _hip_roof(label+"_Roof", cx, cy, width+.65, depth+.61, width*.52,
              top+.08, .80 if width>2 else .67)
    for i in range(2):
        _box(label+"_FrontStep_"+str(i), (cx-width*.20, cy-depth/2-.17-i*.16, floor-.07-i*.10),
             (width*.56+.12*i, .31, .13), "stone", bevel=.02)
    _lantern(label+"_HangingLantern", cx-width*.22, cy-depth/2-.07, top-.27, .65)


def create_architecture(materials, ground_height):
    """Build all architecture and return objects and exact repair region metadata.

    Material keys: roof, roof_trim, wood, wood_dark, plaster, painted_panel,
    stone, brass, glass, redwood. ground_height(x, y) returns scene-space z.
    """
    global _COLLECTION, _OBJECTS, _MATERIALS
    _MATERIALS = materials
    _OBJECTS = []
    _COLLECTION = bpy.data.collections.get("Architecture")
    if _COLLECTION is None:
        _COLLECTION = bpy.data.collections.new("Architecture")
        bpy.context.scene.collection.children.link(_COLLECTION)
    roof, panel, roof_region, panel_region = _main_hall(ground_height)
    _pavilion("WestStudio", -3.35, .70, 2.20, 1.80, ground_height, enclosed=True)
    _pavilion("TeaPavilion", 3.70, -3.10, 1.70, 1.45, ground_height, enclosed=False)
    return {
        "objects": list(_OBJECTS),
        "repair_targets": {"roof": roof, "panel": panel},
        "regions": {"roof": roof_region, "panel": panel_region},
    }
