"""Original procedural textures for the SeamHeal Sakura Courtyard asset.

Run with Python + Pillow + NumPy. No screenshot pixels or third-party textures
are used. Outputs are deterministic and packed by build_scene.py.
"""
from pathlib import Path
import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[1] / "textures"
OUT.mkdir(exist_ok=True)
RNG = np.random.default_rng(2046)


def noise(n, octaves=(8, 24, 64, 180), weights=(.45, .3, .17, .08)):
    result = np.zeros((n, n), dtype=np.float32)
    for s, weight in zip(octaves, weights):
        a = (RNG.random((s, s)) * 255).astype(np.uint8)
        im = Image.fromarray(a).resize((n, n), Image.Resampling.BICUBIC)
        result += np.asarray(im, dtype=np.float32) / 255 * weight
    return result


def save_rgb(name, array):
    Image.fromarray(np.clip(array, 0, 255).astype(np.uint8)).save(OUT / name)


def normal_map(name, height, power=2):
    gy, gx = np.gradient(height)
    vectors = np.stack((-gx * power, -gy * power, np.ones_like(gx)), -1)
    vectors /= np.linalg.norm(vectors, axis=-1, keepdims=True)
    save_rgb(name, (vectors * .5 + .5) * 255)


def make_roof(n=1024):
    yy, xx = np.mgrid[:n, :n] / n
    col = np.floor(xx * 22).astype(int)
    row = np.floor(yy * 13).astype(int)
    u, v = (xx * 22) % 1, (yy * 13) % 1
    grain = noise(n)
    tile_random = RNG.random((14, 23))[row, col]
    barrel = np.sin(u * math.pi) ** .65
    relief = .5 * barrel + .15 * np.exp(-((v - .88) / .10) ** 2)
    joints = ((u < .045) | (u > .97) | (v < .045)).astype(float)
    light = .69 + barrel * .25 + tile_random * .18 + (grain - .5) * .20
    light *= 1 - joints * .32
    color = np.array([69., 88., 99.])[None, None, :] * light[..., None]
    moss = np.clip((noise(n, (5, 19, 65), (.55, .3, .15)) - .57) * 6, 0, .60)
    moss *= np.clip((v - .67) * 4, 0, 1)
    color = color * (1 - moss[..., None]) + np.array([95, 112, 63]) * moss[..., None]
    save_rgb("roof_tiles_basecolor.png", color)
    normal_map("roof_tiles_normal.png", relief - joints * .5, 10)
    save_rgb("roof_tiles_roughness.png", np.repeat((.66 + grain * .21)[..., None] * 255, 3, -1))


def make_wood(n=1024):
    yy, xx = np.mgrid[:n, :n] / n
    n0 = noise(n)
    warp = xx + .010 * np.sin(yy * 16) + .025 * n0
    grain = .45 * np.sin(warp * 620) + .20 * np.sin(warp * 1880 + yy * 6)
    light = .79 + .14 * grain + .38 * (n0 - .45)
    color = np.array([132, 81, 53])[None, None, :] * light[..., None]
    save_rgb("cedar_wood_basecolor.png", color)
    save_rgb("cherry_bark_basecolor.png", color * np.array([.73, .76, .80]))
    normal_map("cedar_wood_normal.png", grain * .07 + n0 * .04, 1.3)


def make_ground(n=1024):
    n0, detail = noise(n), noise(n, (24, 64, 160, 360), (.2, .3, .3, .2))
    moss = np.clip((n0 - .37) * 3.1, 0, 1)
    soil = np.array([137, 119, 83.]) * (.82 + detail[..., None] * .34)
    grass = np.array([100, 120, 67.]) * (.80 + detail[..., None] * .44)
    save_rgb("moss_ground_basecolor.png", soil * (1 - moss[..., None]) + grass * moss[..., None])
    normal_map("moss_ground_normal.png", detail * .25, 2)


def make_stone(n=1024):
    yy, xx = np.mgrid[:n, :n] / n
    n0, detail = noise(n), noise(n, (36, 96, 270, 500), (.3, .25, .3, .15))
    strata = .05 * np.sin(yy * 70 + n0 * 8)
    color = np.array([129., 125., 114.]) * (.71 + .52 * n0[..., None] + strata[..., None])
    color += (detail[..., None] - .5) * 20
    save_rgb("weathered_stone_basecolor.png", color)
    save_rgb("warm_gravel_basecolor.png", color * np.array([1.26, 1.17, .99]))
    normal_map("weathered_stone_normal.png", n0 * .55 + detail * .30 + strata, 3)


def bezier(points, count=100):
    a, b, c, d = [np.array(p) for p in points]
    return [tuple((1-t)**3*a + 3*(1-t)**2*t*b + 3*(1-t)*t*t*c + t**3*d)
            for t in np.linspace(0, 1, count)]


def make_painting():
    w, h = 2048, 1024
    bg = np.zeros((h, w, 3), dtype=np.float32)
    grain = RNG.normal(0, 1.3, (h, w, 1))
    bg[:] = [231, 218, 190]
    bg += grain
    im = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(im)
    ink, gold, leaf1, leaf2 = (78, 77, 64), (171, 134, 73), (76, 116, 99), (121, 151, 119)
    d.rounded_rectangle((22, 22, w-22, h-22), 12, outline=gold, width=8)
    d.rectangle((42, 42, w-42, h-42), outline=(164, 144, 108), width=2)
    # A stylized moon and two botanical branches, composed specifically for this asset.
    d.ellipse((w*.65, h*.11, w*.65+390, h*.11+390), fill=(211, 192, 144), outline=(185, 157, 103), width=4)
    rnd = random.Random(6127)
    routes = [((95, 985),(340,610),(970,520),(1540,175)),
              ((1850,985),(1610,780),(1270,760),(930,355)),
              ((250,810),(390,700),(360,420),(640,140)),
              ((660,650),(780,500),(870,290),(850,100))]
    anchors = []
    for k, route in enumerate(routes):
        curve = bezier(route)
        for j in range(len(curve)-1):
            thick = max(3, int((1-j/len(curve)) * (23 if k<2 else 11)))
            d.line((curve[j],curve[j+1]), fill=ink, width=thick)
        for t in np.linspace(.26,.94,8):
            ix = int(t*(len(curve)-1))
            x,y = curve[ix]
            side = -1 if rnd.random()<.5 else 1
            end = (x+side*rnd.uniform(45,115), y-rnd.uniform(35,115))
            d.line(((x,y),end),fill=ink,width=3)
            anchors.append(end)
            lx,ly = (x+end[0])*.5,(y+end[1])*.5
            d.polygon([(lx,ly),(lx+side*42,ly-48),(lx+side*61,ly-36),(lx+side*15,ly+4)],fill=leaf1 if k%2 else leaf2)
    for x,y in anchors:
        for _ in range(rnd.randint(2,5)):
            px,py = x+rnd.uniform(-42,42), y+rnd.uniform(-35,35)
            r = rnd.uniform(14,27)
            petal_color = rnd.choice([(206,136,132),(224,170,158),(236,191,177),(200,118,118)])
            for k in range(5):
                a=k*math.tau/5
                cx,cy=px+math.cos(a)*r*.76,py+math.sin(a)*r*.76
                d.ellipse((cx-r*.62,cy-r*.62,cx+r*.62,cy+r*.62),fill=petal_color)
            d.ellipse((px-4,py-4,px+4,py+4),fill=gold)
    # Sparse diagonal gold marks give the panel a recognizable UV continuity pattern.
    for k in range(12):
        x,y=120+k*151,870-(k%3)*42
        d.line((x,y,x+39,y-28),fill=gold,width=3)
    im.convert("RGB").save(OUT/"sakura_painted_panel_basecolor.png")


if __name__ == "__main__":
    make_roof(); make_wood(); make_ground(); make_stone(); make_painting()
    print("Original textures saved:")
    for p in sorted(OUT.glob("*.png")):
        print(p.name, p.stat().st_size)
