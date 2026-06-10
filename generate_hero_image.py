"""Generate static/stairsmith-screenshot.png — an app-style screenshot
composited from a real isometric render of the preview geometry."""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stair_preview import generate_preview_geometry
from PIL import Image, ImageDraw

W, H = 1600, 1000
BG = (26, 26, 46)        # #1a1a2e
PANEL = (22, 33, 62)     # #16213e
LINEC = (15, 52, 96)     # #0f3460
FIELD = (31, 43, 77)
ACCENT = (233, 69, 96)   # #e94560

meshes = generate_preview_geometry({"staircase_type": "double_winder",
                                    "turn1_enabled": True, "turn2_enabled": True})

def hex2rgb(h):
    h = h.lstrip("#")
    if len(h) != 6: return (232, 220, 200)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def faces_of(m):
    t = m.get("type")
    col = hex2rgb(m.get("color", "#e8dcc8"))
    out = []  # (verts3d list, normal_axis, col)
    if t == "box":
        c, s = m["ifc_center"], m["ifc_size"]
        x0,x1 = c[0]-s[0]/2, c[0]+s[0]/2
        y0,y1 = c[1]-s[1]/2, c[1]+s[1]/2
        z0,z1 = c[2]-s[2]/2, c[2]+s[2]/2
        out.append(([(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)], 'z', col))
        out.append(([(x0,y0,z0),(x1,y0,z0),(x1,y0,z1),(x0,y0,z1)], 'y', col))
        out.append(([(x1,y0,z0),(x1,y1,z0),(x1,y1,z1),(x1,y0,z1)], 'x', col))
        out.append(([(x0,y1,z0),(x1,y1,z0),(x1,y1,z1),(x0,y1,z1)], 'y', col))
        out.append(([(x0,y0,z0),(x0,y1,z0),(x0,y1,z1),(x0,y0,z1)], 'x', col))
    elif t == "winder_polygon":
        fp = m["profile"]; z0 = m["z"]; z1 = z0 + m["thickness"]
        out.append(([(p[0],p[1],z1) for p in fp], 'z', col))
        n = len(fp)
        for i in range(n):
            a, b = fp[i], fp[(i+1)%n]
            dx, dy = b[0]-a[0], b[1]-a[1]
            ax = 'y' if abs(dx) > abs(dy) else 'x'
            out.append(([(a[0],a[1],z0),(b[0],b[1],z0),(b[0],b[1],z1),(a[0],a[1],z1)], ax, col))
    elif t == "stringer":
        prof = m["profile"]; th = m["thickness"]; ax = m.get("axis")
        if ax == "y":
            y0 = m.get("y", 0)
            w3 = [(p[0], y0, p[1]) for p in prof]
            w3b = [(p[0], y0+th, p[1]) for p in prof]
        else:
            x0 = m.get("x", 0)
            w3 = [(x0, p[0], p[1]) for p in prof]
            w3b = [(x0+th, p[0], p[1]) for p in prof]
        out.append((w3, 'y' if ax=='y' else 'x', col))
        out.append((w3b, 'y' if ax=='y' else 'x', col))
        n = len(prof)
        for i in range(n):
            a, b = w3[i], w3[(i+1)%n]
            a2, b2 = w3b[i], w3b[(i+1)%n]
            out.append(([a, b, b2, a2], 'z', col))
    return out

# isometric projection
c30, s30 = math.cos(math.radians(30)), math.sin(math.radians(30))
def proj(p):
    x, y, z = p
    u = (x - y) * c30
    v = (x + y) * s30 - z
    return u, v, x + y + z

allf = []
for m in meshes:
    for verts, nax, col in faces_of(m):
        pv = [proj(p) for p in verts]
        depth = sum(p[2] for p in pv) / len(pv)
        shade = {'z': 1.0, 'y': 0.78, 'x': 0.58}[nax]
        c = tuple(min(255, int(ch * shade)) for ch in col)
        allf.append((depth, [(p[0], p[1]) for p in pv], c))

allf.sort(key=lambda f: f[0])
us = [p[0] for _,poly,_ in allf for p in poly]
vs = [p[1] for _,poly,_ in allf for p in poly]
u0,u1,v0,v1 = min(us),max(us),min(vs),max(vs)

# viewport region of the fake app frame
PANEL_W = 340
vp_x0, vp_y0, vp_x1, vp_y1 = PANEL_W, 0, W, H
pad = 90
sc = min((vp_x1-vp_x0-2*pad)/(u1-u0), (vp_y1-vp_y0-2*pad)/(v1-v0))
ox = vp_x0 + (vp_x1-vp_x0 - (u1-u0)*sc)/2 - u0*sc
oy = vp_y0 + (vp_y1-vp_y0 - (v1-v0)*sc)/2 - v0*sc

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# faint grid in viewport
for gx in range(vp_x0, W, 56):
    d.line([(gx, 0), (gx, H)], fill=(31, 33, 56), width=1)
for gy in range(0, H, 56):
    d.line([(vp_x0, gy), (W, gy)], fill=(31, 33, 56), width=1)

# stair render
for _, poly, c in allf:
    pts = [(p[0]*sc+ox, p[1]*sc+oy) for p in poly]
    edge = tuple(max(0, ch-38) for ch in c)
    d.polygon(pts, fill=c, outline=edge)

# fake left control panel
d.rectangle([0, 0, PANEL_W, H], fill=PANEL)
d.line([(PANEL_W, 0), (PANEL_W, H)], fill=LINEC, width=2)
d.text((24, 26), "StairSmith", fill=ACCENT)
d.text((24, 48), "Parametric Staircase Design", fill=(136,136,136))
yy = 92
import random
random.seed(7)
for i in range(9):
    d.text((24, yy), ["Staircase Type","Total Rise","Floor-to-Floor","Stair Width","Going","Number of Risers","Winder Turn","Newel Size","Balustrade"][i], fill=(160,165,180))
    yy += 22
    d.rounded_rectangle([24, yy, PANEL_W-24, yy+34], radius=6, fill=FIELD, outline=LINEC)
    if i in (0, 6):
        d.polygon([(PANEL_W-44, yy+14),(PANEL_W-32, yy+14),(PANEL_W-38, yy+22)], fill=(120,126,150))
    yy += 50
d.rounded_rectangle([24, H-150, PANEL_W-24, H-110], radius=8, fill=ACCENT)
d.text((PANEL_W//2-52, H-138), "Download IFC", fill=(255,255,255))
d.rounded_rectangle([24, H-98, PANEL_W-24, H-58], radius=8, fill=FIELD, outline=ACCENT)
d.text((PANEL_W//2-56, H-86), "Download DXF", fill=(233,69,96))

img.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "stairsmith-screenshot.png"), optimize=True)
print("saved", img.size)
