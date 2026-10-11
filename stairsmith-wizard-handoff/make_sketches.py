"""Reference sketches for the StairSmith wizard.

Draws each wizard step's diagram from StairSmith's default parameters, so
every dimension label is true to its line. Run with the StairSmith repo
path as the first argument; writes SVGs next to this script.
"""
import math
import os
import sys

sys.path.insert(0, sys.argv[1])
from stair_winder_geometry import _winder_profiles_from_construction  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))

# StairSmith defaults (stair_constants._parse)
P = dict(floor_to_floor=2700, num_risers=14, going=227, stair_width=900,
         nosing=16, tread_thickness=22, riser_thickness=9, threshold_depth=100,
         newel_size=90, winder_x=25, winder_y=50, newel_to_newel=140, handrail_width=70)
RISE = P["floor_to_floor"] / P["num_risers"]
PITCH = math.degrees(math.atan(RISE / P["going"]))

# StairSmith dark theme (app.html): panel #16213e, page #1a1a2e, borders #0f3460, text #e0e0e0, accent #e94560
INK = "#c9c9d4"      # context linework
ACC = "#00ccff"      # what this step sets (StairSmith cyan)
APP_RED = "#e94560"  # StairSmith button accent, used only for mock UI controls
ACC_T = "#4fdcff"    # accent text, lifted slightly for legibility on the panel
DIM = "#8a93ad"      # dimensions, projectors and reference values
TITLE = "#e0e0e0"    # headings and primary labels
PANEL = "#16213e"    # wizard panel; also the fill that masks lines behind newels
FIELD = "#1a1a2e"    # unselected toggle background
HATCH = "#5b6688"    # wall hatch
FONT = 'font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"'


def svg(title, body, note, w=800, h=460):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
<defs>
<marker id="a" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,1 L10,5 L0,9" fill="none" stroke="{DIM}" stroke-width="1.5"/></marker>
<marker id="aa" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,1 L10,5 L0,9" fill="none" stroke="{ACC}" stroke-width="1.5"/></marker>
<pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" stroke="{HATCH}" stroke-width="1"/></pattern>
</defs>
<text x="24" y="34" {FONT} font-size="20" font-weight="600" fill="{TITLE}">{title}</text>
{body}<text x="{w / 2}" y="{h - 18}" {FONT} font-size="11" fill="{DIM}" text-anchor="middle">{note}</text>
</svg>'''


def line(x1, y1, x2, y2, c=INK, w=2, dash=None, end=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#{end})"' if end else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{c}" stroke-width="{w}"{d}{m}/>\n'


def poly(pts, c=INK, w=2, fill="none", close=True, end=None):
    tag = "polygon" if close else "polyline"
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    m = f' marker-end="url(#{end})"' if end else ""
    return f'<{tag} points="{p}" fill="{fill}" stroke="{c}" stroke-width="{w}" stroke-linejoin="round"{m}/>\n'


def rect(x, y, w, h, c=INK, sw=2, fill="none"):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{c}" stroke-width="{sw}"/>\n'


def text(x, y, s, size=13, c=INK, bold=False, anchor="middle", rot=None):
    b = ' font-weight="600"' if bold else ""
    r = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot is not None else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" {FONT} font-size="{size}" fill="{c}" text-anchor="{anchor}"{b}{r}>{s}</text>\n'


def proj(x1, y1, x2, y2):
    return line(x1, y1, x2, y2, DIM, 1, "4 3")


def _ticked(x1, y1, x2, y2, active):
    """Dimension line with oblique (45 degree) ticks at each end, running slightly past them."""
    c = ACC if active else DIM
    w = 1.4 if active else 1.2
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    run = 4
    s = line(x1 - ux * run, y1 - uy * run, x2 + ux * run, y2 + uy * run, c, w)
    k = 0.7071
    tx, ty = (ux * k - uy * k) * 5, (ux * k + uy * k) * 5
    for (px, py) in ((x1, y1), (x2, y2)):
        s += line(px - tx, py - ty, px + tx, py + ty, c, 1.8)
    return s


def _arrowline(x1, y1, x2, y2, active):
    return _ticked(x1, y1, x2, y2, active)


def _outside(x1, y1, x2, y2, active):
    return _ticked(x1, y1, x2, y2, active)


def hdim(x1, x2, y, label, active=False, above=True, note=None, size=13, lx=None, anchor="middle"):
    small = abs(x2 - x1) < 30
    s = _outside(x1, y, x2, y, active) if small else _arrowline(x1, y, x2, y, active)
    if lx is None:
        lx, ty = (x1 + x2) / 2, (y - 5 if above else y + 14)
        nty = ty + (-14 if above else 13)
    else:
        ty, nty = y + 4, y + 19
    s += text(lx, ty, label, size, ACC_T if active else INK, bold=True, anchor=anchor)
    if note:
        s += text(lx, nty, note, 11, DIM, anchor=anchor)
    return s


def vdim(x, y1, y2, label, active=False, right=True, note=None, size=13):
    small = abs(y2 - y1) < 30
    s = _outside(x, y1, x, y2, active) if small else _arrowline(x, y1, x, y2, active)
    tx = x + 7 if right else x - 7
    anchor = "start" if right else "end"
    my = (y1 + y2) / 2
    s += text(tx, my + 4, label, size, ACC_T if active else INK, bold=True, anchor=anchor)
    if note:
        s += text(tx, my + 19, note, 11, DIM, anchor=anchor)
    return s


def mm(v):
    return f"{v:.0f}" if abs(v - round(v)) < 0.05 else f"{v:.1f}"


# ---------------------------------------------------------------- step 0
def step0_types():
    s = 0.055
    W, G = P["stair_width"] * s, P["going"] * s
    body = ""
    names = ["Straight", "Single winder (L)", "Double winder (U)", "Half-landing (U)"]
    for i, name in enumerate(names):
        cx, base = 100 + i * 200, 340
        sel = i == 0
        c = ACC if sel else INK
        ac, am = (ACC_T, "aa") if sel else (DIM, "a")
        if i == 0:
            n, x0 = 13, cx - W / 2
            body += rect(x0, base - n * G, W, n * G, c)
            for k in range(1, n):
                body += line(x0, base - k * G, x0 + W, base - k * G, c, 1)
            arrow = [(cx, base - 6), (cx, base - n * G + 8)]
        elif i == 1:
            # flight 1, flat landing, flight 2 (corners start as landings, no winders)
            n1, n2 = 9, 3
            x0 = cx - (W + n2 * G) / 2
            top = base - n1 * G
            body += rect(x0, top, W, n1 * G, c)
            for k in range(1, n1):
                body += line(x0, base - k * G, x0 + W, base - k * G, c, 1)
            body += rect(x0, top - W, W, W, c)
            body += rect(x0 + W, top - W, n2 * G, W, c)
            for k in range(1, n2):
                body += line(x0 + W + k * G, top - W, x0 + W + k * G, top, c, 1)
            arrow = [(x0 + W / 2, base - 6), (x0 + W / 2, top - W / 2), (x0 + W + n2 * G - 6, top - W / 2)]
        elif i == 2:
            # flight 1, landing, flight 2 across, landing, flight 3 back down
            n1, n2 = 6, 2
            span = 2 * W + n2 * G
            x0 = cx - span / 2
            x1 = x0 + W + n2 * G
            top = base - n1 * G
            for xx in (x0, x1):
                body += rect(xx, top, W, n1 * G, c)
                for k in range(1, n1):
                    body += line(xx, base - k * G, xx + W, base - k * G, c, 1)
                body += rect(xx, top - W, W, W, c)
            body += rect(x0 + W, top - W, n2 * G, W, c)
            for k in range(1, n2):
                body += line(x0 + W + k * G, top - W, x0 + W + k * G, top, c, 1)
            arrow = [(x0 + W / 2, base - 6), (x0 + W / 2, top - W / 2), (x1 + W / 2, top - W / 2), (x1 + W / 2, base - 8)]
        else:
            n1, gap = 6, 6
            x0 = cx - W - gap / 2
            x1 = x0 + W + gap
            top = base - n1 * G
            for xx in (x0, x1):
                body += rect(xx, top, W, n1 * G, c)
                for k in range(1, n1):
                    body += line(xx, base - k * G, xx + W, base - k * G, c, 1)
            body += rect(x0, top - W, 2 * W + gap, W, c)
            body += text(cx, top - W - 8, "landing", 10, DIM)
            arrow = [(x0 + W / 2, base - 6), (x0 + W / 2, top - W / 2), (x1 + W / 2, top - W / 2), (x1 + W / 2, base - 8)]
        body += poly(arrow, ac, 1.4, close=False, end=am)
        body += text(cx, base + 30, name, 13, ACC_T if sel else INK, bold=True)
    body += text(400, 405, "Corners start as flat landings; winders are chosen on the Corners step. Hand mirrors the turning types.", 11, DIM)
    return svg("0  Stair type", body,
               "Plan icons. Selected type in the accent colour; arrows show the direction of travel up.")


# ---------------------------------------------------------------- step 1
def step1_height():
    # Simple two-storey house in section, stair inside. One scale throughout.
    s = 0.07
    ftf = P["floor_to_floor"]
    house_w, upper, joist = 7500, 2400, 250
    roof_rise = (house_w / 2) * math.tan(math.radians(30))
    r, g = RISE * s, P["going"] * s
    n = P["num_risers"]
    xl, gy = 90, 565                        # left wall, ground floor level
    xr = xl + house_w * s
    fy = gy - ftf * s                       # first floor finished level
    ey = fy - upper * s                     # eaves
    ry = ey - roof_rise * s                 # ridge
    tw, tr, ov = 300 * s, 250 * s, 300 * s  # wall thickness, roof thickness, overhang
    slab, found = 150 * s, 450 * s          # ground slab depth; walls cut off below it
    jz = joist * s
    # ground floor surface between the inner faces; slab, walls and ground read as one mass
    body = line(xl + tw, gy, xr - tw, gy, INK, 2)
    body += line(60, gy + slab, xl, gy + slab, INK, 2) + line(xr, gy + slab, 760, gy + slab, INK, 2)
    tan30 = math.tan(math.radians(30))
    xm = (xl + xr) / 2
    up = tr / math.cos(math.radians(30))

    def yin(x):  # underside of roof; bears on the outer wall faces at eaves level
        return ey - (x - xl) * tan30 if x <= xm else ey - (xr - x) * tan30

    li, ri, ai = (xl - ov, yin(xl - ov)), (xr + ov, yin(xr + ov)), (xm, yin(xm))
    # roof top surface and eaves ends
    body += poly([(li[0], li[1] - up), (ai[0], ai[1] - up), (ri[0], ri[1] - up)], INK, 2, close=False)
    body += line(li[0], li[1], li[0], li[1] - up, INK, 2) + line(ri[0], ri[1], ri[0], ri[1] - up, INK, 2)
    # roof underside: soffits outside the walls, ceiling line between inner faces
    body += line(*li, xl, yin(xl), INK, 2) + line(xr, yin(xr), *ri, INK, 2)
    body += poly([(xl + tw, yin(xl + tw)), ai, (xr - tw, yin(xr - tw))], INK, 2, close=False)
    # walls run into the roof, first floor and ground slab with no line between them
    for x in (xl, xr):
        body += line(x, gy + slab, x, yin(x), INK, 2)
    for x in (xl + tw, xr - tw):
        body += line(x, yin(x), x, fy, INK, 2)
        body += line(x, fy + jz, x, gy, INK, 2)
    # stair, starting 1 m off the inside face of the left wall
    x0 = xl + tw + 1000 * s
    xt = x0 + (n - 1) * g
    pts, x, y = [(x0, gy)], x0, gy
    for k in range(n):
        y -= r
        pts.append((x, y))
        if k < n - 1:
            x += g
            pts.append((x, y))
    body += poly(pts, INK, 1.4, close=False)
    # first floor zone with the stairwell opening over the stair
    open_l = xt - 2600 * s
    body += line(xl + tw, fy, open_l, fy, INK, 2) + line(xl + tw, fy + jz, open_l, fy + jz, INK, 2)
    body += line(open_l, fy, open_l, fy + jz, INK, 2)
    body += line(xt, fy, xr - tw, fy, INK, 2) + line(xt, fy + jz, xr - tw, fy + jz, INK, 2)
    body += line(xt, fy, xt, fy + jz, INK, 2)
    # floor to floor
    dx = xr + 40
    body += proj(xr, gy, dx + 4, gy) + proj(xr, fy, dx + 4, fy)
    body += vdim(dx, gy, fy, f"{mm(ftf)}", active=True, note="floor to floor, mm")
    body += text(xr - tw - 10, gy - 10, "ground floor", 11, DIM, anchor="end")
    body += text(xr - tw - 10, fy - 10, "first floor", 11, DIM, anchor="end")
    return svg("1  Height", body, "Section through a simple two-storey house. Finished floor to finished floor.", h=640)


# ---------------------------------------------------------------- step 2
def step2_risers_going_width():
    s = 0.5
    r, g, nos, tt = RISE * s, P["going"] * s, P["nosing"] * s, P["tread_thickness"] * s
    body = ""
    x0, y0 = 150, 385
    body += line(x0 - 40, y0, x0 + 3 * g + 30, y0, INK, 1)
    for k in range(3):
        rx, ry = x0 + k * g, y0 - k * r
        body += line(rx, ry, rx, ry - r + tt, INK, 2)
        body += rect(rx - nos, ry - r, g + nos if k < 2 else g + nos + 30, tt, INK, 1.6)
    # pitch line through nosings
    body += line(x0 - nos, y0 - r, x0 + 2 * g - nos + 0.4 * g, y0 - 3 * r - 0.4 * r, DIM, 1, "4 3")
    body += text(x0 + 0.3 * g, y0 - 2 * r, f"pitch {PITCH:.1f}°", 12, DIM, anchor="end")
    # going: nosing to nosing, dimensioned below the section
    gx1, gx2 = x0 + g - nos, x0 + 2 * g - nos   # nosing to nosing
    body += proj(gx1, y0 - 2 * r, gx1, y0 + 20) + proj(gx2, y0 - 3 * r, gx2, y0 + 20)
    body += hdim(gx1, gx2, y0 + 16, f"going {P['going']}", active=True, above=False)
    # rise: right of the top step
    rxx = x0 + 3 * g + 50
    body += proj(x0 + 2 * g + g, y0 - 2 * r, rxx + 4, y0 - 2 * r) + proj(x0 + 3 * g + 30, y0 - 3 * r, rxx + 4, y0 - 3 * r)
    body += vdim(rxx, y0 - 2 * r, y0 - 3 * r, f"rise {mm(RISE)}", note="reference")
    # nosing: top tread
    nx1, nx2 = x0 + 2 * g - nos, x0 + 2 * g
    ny = y0 - 3 * r - 28
    body += proj(nx1, y0 - 3 * r, nx1, ny - 4) + proj(nx2, y0 - 3 * r, nx2, ny - 4)
    body += hdim(nx1, nx2, ny, f"nosing {P['nosing']}", active=True, size=12)
    body += text(560, 360, f"risers {P['num_risers']}", 14, ACC_T, bold=True, anchor="start")
    body += text(560, 377, f"treads {P['num_risers'] - 1}  ·  rise {mm(RISE)}  ·  pitch {PITCH:.1f}°", 11, DIM, anchor="start")
    return svg("2  Risers and going", body,
               "Accent: values set on this step. Grey: reference values only, not a compliance check.")


# ---------------------------------------------------------------- step 3
def step3_construction():
    # One tread and riser in accent, set within the flight (neighbours in charcoal, cut ends open)
    s = 1.1
    r, g, nos = RISE * s, P["going"] * s, P["nosing"] * s
    tt, rt = P["tread_thickness"] * s, P["riser_thickness"] * s
    x0, y0 = 300, 390                      # face of this riser, top of the tread below
    ty = y0 - r                            # top of this tread
    cut = 150
    body = ""
    # tread below: open at its front (left), riser sits on its back edge
    body += line(x0 - cut, y0, x0 + rt, y0, INK, 2) + line(x0 - cut, y0 + tt, x0 + rt, y0 + tt, INK, 2)
    body += line(x0 + rt, y0, x0 + rt, y0 + tt, INK, 2)
    # this riser and this tread
    body += rect(x0, ty + tt, rt, y0 - ty - tt, ACC)
    body += rect(x0 - nos, ty, nos + g + rt, tt, ACC)
    # next riser rising off the back edge of this tread, cut open above
    xb = x0 + g
    body += line(xb, ty, xb, ty - 110, INK, 2) + line(xb + rt, ty, xb + rt, ty - 110, INK, 2)
    # dimensions
    tx = x0 - nos - 44
    body += proj(x0 - nos, ty, tx - 4, ty) + proj(x0 - nos, ty + tt, tx - 4, ty + tt)
    body += vdim(tx, ty, ty + tt, f"tread {P['tread_thickness']}", active=True, right=False)
    body += hdim(x0, x0 + rt, y0 - r / 2, f"riser {P['riser_thickness']}", active=True, lx=x0 + rt + 26, anchor="start")
    body += proj(x0 - nos, ty, x0 - nos, ty - 26) + proj(x0, ty, x0, ty - 26)
    body += hdim(x0 - nos, x0, ty - 22, f"nosing {P['nosing']}", note="set on step 2")
    return svg("3  Treads and risers", body, "Section through the flight, close up. Accent: the tread and riser being set.")


# ---------------------------------------------------------------- step 4
def step4_sides():
    s = 0.15
    n = P["num_risers"] - 1
    g, W, ns = P["going"] * s, P["stair_width"] * s, P["newel_size"] * s
    L = n * g
    x0, y0 = 190, 150
    body = rect(x0, y0, L, W, INK)
    for k in range(1, n):
        body += line(x0 + k * g, y0, x0 + k * g, y0 + W, INK, 1)
    body += line(x0, y0 + ns / 2, x0 + L, y0 + ns / 2, ACC, 3)
    body += rect(x0 - ns, y0, ns, ns, ACC, 2, PANEL)
    body += rect(x0 + L, y0, ns, ns, ACC, 2, PANEL)
    body += rect(x0 - 10, y0 + W, L + 20, 14, "none", 0, "url(#hatch)")
    body += line(x0 - 10, y0 + W, x0 + L + 10, y0 + W, INK, 2)
    body += text(x0 + L / 2, y0 - 16, "left side: balustrade", 12, ACC_T, bold=True)
    body += text(x0 + L / 2, y0 + W + 36, "right side: wall", 12, INK, bold=True)
    body += line(x0 + L / 2 - 60, y0 + W / 2 + 6, x0 + L / 2 + 60, y0 + W / 2 + 6, DIM, 1.4, end="a")
    body += text(x0 + L / 2, y0 + W / 2 - 6, "up", 11, DIM)
    # width, outside to outside
    wx = x0 - 50
    body += proj(x0 - ns, y0, wx - 4, y0) + proj(x0, y0 + W, wx - 4, y0 + W)
    body += vdim(wx, y0, y0 + W, f"width {P['stair_width']}", active=True, right=False, note="outside to outside")
    # newel enlargement
    es = 0.9
    E = P["newel_size"] * es
    ex, ey = 680, 250
    body += rect(ex, ey, E, E, ACC, 2)
    body += proj(x0 + L + ns, y0 + ns, ex, ey)
    body += proj(ex, ey + E, ex, ey + E + 24) + proj(ex + E, ey + E, ex + E, ey + E + 24)
    body += hdim(ex, ex + E, ey + E + 20, f"newel {P['newel_size']}", active=True, above=False)
    body += text(ex + E / 2, ey - 10, "enlarged", 11, DIM)
    return svg("4  Width, sides and newels", body,
               "Plan. Each side toggles between wall and balustrade; newels appear where there is a balustrade.")


# ---------------------------------------------------------------- step 5
def step5_corner():
    # Close-up of a left quarter-turn winder corner around the newel, cropped.
    # The flight risers meet the newel faces at the Y marks; winder lines start at the X marks.
    s = 0.68
    ns, W, G = P["newel_size"], P["stair_width"], P["going"]
    hp, bi = ns / 2, P["handrail_width"] / 2
    X, Y = P["winder_x"], P["winder_y"]
    crop = (-380, -445, 445, 430)                  # x0, y0, x1, y1 in mm, post centre at origin
    ox = 400 - ((crop[0] + crop[2]) / 2) * s
    oy = 368 + ((crop[1] + crop[3]) / 2) * s

    def T(x, y):
        return (ox + x * s, oy - y * s)

    (cx0, cy0), (cx1, cy1) = T(crop[0], crop[3]), T(crop[2], crop[1])
    body = f'<clipPath id="w_crop"><rect x="{cx0:.1f}" y="{cy0:.1f}" width="{cx1 - cx0:.1f}" height="{cy1 - cy0:.1f}"/></clipPath>\n'
    g = ""
    pc = (hp, hp)                                  # inside corner of the newel
    m1, m2 = (hp, hp - X), (hp - X, hp)            # X marks on the two faces
    wc = (hp - X, hp - X)                          # winder centre
    yY = hp - X - Y                                # Y mark on the face meeting flight 1
    xY = hp - X - Y                                # Y mark on the face meeting flight 2
    far = 2000
    # flight 1 risers: the top one meets the newel face at the Y mark
    for k in range(0, 4):
        yk = yY - k * G
        g += line(*T(hp if k == 0 else bi, yk), *T(far, yk), INK if k else ACC, 1.2 if k else 1.8)
    # flight 2 risers: the first one leaves the newel's other face at its Y mark
    for k in range(0, 4):
        xk = xY - k * G
        g += line(*T(xk, hp if k == 0 else bi), *T(xk, far), INK if k else ACC, 1.2 if k else 1.8)
    # winder division lines: from the X marks, along rays from the winder centre
    for (mx, my), ang in ((m1, 30), (m2, 60)):
        a = math.radians(ang)
        t = far
        g += line(*T(mx, my), *T(wc[0] + math.cos(a) * t, wc[1] + math.sin(a) * t), ACC, 1.8)
    # balustrade into the newel from both flights
    for off in (-bi, bi):
        g += line(*T(off, -far), *T(off, -hp), ACC, 1.6)
        g += line(*T(-far, off), *T(-hp, off), ACC, 1.6)
    nx, ny = T(-hp, hp)
    g += rect(nx, ny, ns * s, ns * s, INK, 2, PANEL)
    body += f'<g clip-path="url(#w_crop)">{g}</g>\n'
    # X and Y down the newel face that meets flight 1
    fx = T(hp, 0)[0]
    y0, y1, y2 = T(0, hp)[1], T(0, hp - X)[1], T(0, yY)[1]
    dxl = fx + 34
    for yy in (y0, y1, y2):
        body += proj(fx + 4, yy, dxl + 4, yy)
    body += _ticked(dxl, y0, dxl, y1, True) + _ticked(dxl, y1, dxl, y2, True)
    body += text(dxl + 9, (y0 + y1) / 2 + 5, f"X {X}", 13, ACC_T, bold=True, anchor="start")
    body += text(dxl + 9, (y1 + y2) / 2 + 5, f"Y {Y}", 13, ACC_T, bold=True, anchor="start")
    lx, ly = T(250, -380)
    body += text(lx, ly, "flight 1", 11, DIM)
    lx, ly = T(-330, 380)
    body += text(lx, ly, "flight 2", 11, DIM, anchor="start")
    return svg("6  Winder set-out", body,
               "Close-up of the newel at a left quarter turn. Winders start at the X marks; the flights meet the newel at the Y marks.", h=700)


def step5_half_landing():
    # Same plan engine as step 4, larger, with the half-landing set-out dimensioned.
    s = 0.18
    lay = _stair_layouts()["Half-landing (U)"]
    W, ns = P["stair_width"], P["newel_size"]
    gap = P["newel_to_newel"] - ns
    xb = -gap
    top = max(p[1] for p in lay["right"])
    n1G = top - W
    minx = xb - W
    ox = 400 - ((minx + W) / 2) * s
    oy = 545

    def T(x, y):
        return (ox + x * s, oy - y * s)

    body = _plan(lay, T, s, {"left": "balustrade", "right": "wall"})
    # newel to newel, centre to centre, below the flights
    ca, cb = T(ns / 2, 0)[0], T(xb - ns / 2, 0)[0]
    yb = T(0, lay["left"][-1][1])[1]
    body += proj(ca, T(0, n1G)[1], ca, yb + 26) + proj(cb, T(0, n1G)[1], cb, yb + 26)
    body += hdim(cb, ca, yb + 22, f"newel to newel {P['newel_to_newel']}", active=True,
                 note="centre to centre", lx=ca + 40, anchor="start")
    # landing width across the top
    lx1, lx2 = T(minx, top)[0], T(W, top)[0]
    ly = T(0, top)[1]
    body += proj(lx1, ly - 14, lx1, ly - 40) + proj(lx2, ly - 14, lx2, ly - 40)
    body += hdim(lx1, lx2, ly - 36, "landing width", active=True, note="plus any oversize")
    return svg("5  Corners: half-landing", body,
               "Plan. Half-landing type only: newel spacing and any landing oversize.", h=640)


SKETCHES = {
    "step0_stair_type.svg": step0_types,
    "step1_height.svg": step1_height,
    "step2_risers_going_width.svg": step2_risers_going_width,
    "step3_treads_risers_threshold.svg": step3_construction,
    "step4_sides_newels.svg": step4_sides,
    "step5_corners_winder.svg": step5_corner,
    "step5_corners_half_landing.svg": step5_half_landing,
}

# ---------------------------------------------------------------- step 4 options (plan per stair type)
def _offset_path(pts, d, side):
    """Offset an axis-aligned polyline by d mm. side=+1 offsets to the right of travel, -1 to the left."""
    segs = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        L = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        nx, ny = uy * side, -ux * side          # right-hand normal when side=+1 (y up)
        segs.append(((x1 + nx * d, y1 + ny * d), (x2 + nx * d, y2 + ny * d), (ux, uy)))
    out = [segs[0][0]]
    for a, b in zip(segs, segs[1:]):
        (ax, ay), _, (aux, auy) = a
        (bx, by), _, _ = b
        # axis-aligned: corner takes the varying coordinate from each segment
        out.append((ax, by) if abs(aux) < 1e-9 else (bx, ay))
    out.append(segs[-1][1])
    return out


def _stair_layouts(counts=None):
    counts = counts or {}
    W, G = P["stair_width"], P["going"]
    L = {}
    n = P["num_risers"] - 1
    L["Straight"] = dict(
        flights=[dict(rect=(0, 0, W, n * G), dir="y+", n=n)], landings=[],
        left=[(0, 0), (0, n * G)], right=[(W, 0), (W, n * G)],
        path=[(W / 2, 60), (W / 2, n * G - 60)])
    n1, n2 = counts.get("L", (9, 3))
    L["Single winder (L)"] = dict(
        flights=[dict(rect=(0, 0, W, n1 * G), dir="y+", n=n1),
                 dict(rect=(-n2 * G, n1 * G, n2 * G, W), dir="x-", n=n2)],
        landings=[(0, n1 * G, W, W)],
        left=[(0, 0), (0, n1 * G), (-n2 * G, n1 * G)],
        right=[(W, 0), (W, n1 * G + W), (-n2 * G, n1 * G + W)],
        path=[(W / 2, 60), (W / 2, n1 * G + W / 2), (-n2 * G + 60, n1 * G + W / 2)])
    n1, n2, n3 = counts.get("U", (5, 2, 5))
    x2 = -n2 * G
    L["Double winder (U)"] = dict(
        flights=[dict(rect=(0, 0, W, n1 * G), dir="y+", n=n1),
                 dict(rect=(x2, n1 * G, n2 * G, W), dir="x-", n=n2),
                 dict(rect=(x2 - W, n1 * G - n3 * G, W, n3 * G), dir="y-", n=n3)],
        landings=[(0, n1 * G, W, W), (x2 - W, n1 * G, W, W)],
        left=[(0, 0), (0, n1 * G), (x2, n1 * G), (x2, n1 * G - n3 * G)],
        right=[(W, 0), (W, n1 * G + W), (x2 - W, n1 * G + W), (x2 - W, n1 * G - n3 * G)],
        path=[(W / 2, 60), (W / 2, n1 * G + W / 2), (x2 - W / 2, n1 * G + W / 2), (x2 - W / 2, n1 * G - n3 * G + 60)])
    n1 = n2 = 6
    gap = P["newel_to_newel"] - P["newel_size"]
    xb = -gap
    L["Half-landing (U)"] = dict(
        flights=[dict(rect=(0, 0, W, n1 * G), dir="y+", n=n1),
                 dict(rect=(xb - W, n1 * G - n2 * G, W, n2 * G), dir="y-", n=n2)],
        landings=[(xb - W, n1 * G, 2 * W + gap, W)],
        left=[(0, 0), (0, n1 * G), (xb, n1 * G), (xb, n1 * G - n2 * G)],
        right=[(W, 0), (W, n1 * G + W), (xb - W, n1 * G + W), (xb - W, n1 * G - n2 * G)],
        path=[(W / 2, 60), (W / 2, n1 * G + W / 2), (xb - W / 2, n1 * G + W / 2), (xb - W / 2, n1 * G - n2 * G + 60)])
    return L


_CLIP_N = [0]


def _plan(lay, T, s, conds):
    """Draw one stair plan. conds = {'left': 'balustrade'|'wall', 'right': ...}."""
    ns, hw = P["newel_size"], P["handrail_width"]
    trim_b = ns / 2 + hw / 2                     # inner balustrade line, from the outside edge
    # clip that admits everything except the stair footprint, so wall hatch never crosses treads
    _CLIP_N[0] += 1
    clip_id = f"outside{_CLIP_N[0]}"
    d = "M-2000,-2000 H4000 V4000 H-2000 Z "
    for (x, y, w, h) in [f["rect"] for f in lay["flights"]] + list(lay["landings"]):
        (ax, ay), (bx, by) = T(x, y), T(x + w, y + h)
        d += f"M{ax:.1f},{ay:.1f} H{bx:.1f} V{by:.1f} H{ax:.1f} Z "
    body = f'<clipPath id="{clip_id}"><path d="{d}" clip-rule="evenodd"/></clipPath>\n'
    # No outlines: flight ends and landing edges come from the cross lines and the sides.
    for f in lay["flights"]:
        x, y, w, h = f["rect"]
        d = f["dir"]
        # which rect edge is the walker's left?
        left_edge = {"y+": "xmin", "y-": "xmax", "x-": "ymin", "x+": "ymax"}[d]
        tl = trim_b if conds["left"] == "balustrade" else 0
        tr = trim_b if conds["right"] == "balustrade" else 0
        G = P["going"]
        for k in range(0, f["n"] + 1):
            if d in ("y+", "y-"):
                yy = y + k * G
                a, b = x, x + w
                a += tl if left_edge == "xmin" else tr
                b -= tr if left_edge == "xmin" else tl
                body += line(*T(a, yy), *T(b, yy), INK, 1)
            else:
                xx = x + k * G
                a, b = y, y + h
                a += tl if left_edge == "ymin" else tr
                b -= tr if left_edge == "ymin" else tl
                body += line(*T(xx, a), *T(xx, b), INK, 1)
    # sides
    for side, sgn in (("left", +1), ("right", -1)):
        pts = lay[side]
        if conds[side] == "wall":
            out = _offset_path(pts, 110, -sgn)
            body += (f'<g clip-path="url(#{clip_id})">'
                     + poly([T(*p) for p in pts] + [T(*p) for p in reversed(out)], "none", 0, "url(#hatch)") + '</g>\n')
            body += poly([T(*p) for p in pts], INK, 2.2, close=False)
        else:
            for dd in (ns / 2 - hw / 2, ns / 2 + hw / 2):
                body += poly([T(*p) for p in _offset_path(pts, dd, sgn)], ACC, 1.6, close=False)
            cl = _offset_path(pts, ns / 2, sgn)
            # newels: start, each corner, end (start and end pulled in by half a newel)
            def pull(p, q, d):
                L = math.hypot(q[0] - p[0], q[1] - p[1])
                return (p[0] + (q[0] - p[0]) / L * d, p[1] + (q[1] - p[1]) / L * d)
            centres = [pull(cl[0], cl[1], ns / 2)] + cl[1:-1] + [pull(cl[-1], cl[-2], ns / 2)]
            for cx, cy in centres:
                px, py = T(cx - ns / 2, cy + ns / 2)
                body += rect(px, py, ns * s, ns * s, ACC, 1.6, PANEL)
    # line of travel
    body += poly([T(*p) for p in lay["path"]], DIM, 1.2, close=False, end="a")
    return body


def step4_options(conds=None):
    s = 0.09
    lays = _stair_layouts()
    conds = conds or {"left": "balustrade", "right": "wall"}
    cells = [(0, 0), (1, 0), (0, 1), (1, 1)]
    body = ""
    W = P["stair_width"]
    for (name, lay), (cx, cy) in zip(lays.items(), cells):
        xs = [p[0] for p in lay["right"] + lay["left"]]
        ys = [p[1] for p in lay["right"] + lay["left"]]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        cw, ch = 400, 375
        ox = cx * cw + (cw - (maxx - minx) * s) / 2 - minx * s
        base = 70 + cy * ch + ch - 70             # bottom of the plan within the cell
        oy = base + miny * s

        def T(x, y, ox=ox, oy=oy):
            return (ox + x * s, oy - y * s)

        body += _plan(lay, T, s, conds)
        # width across the first flight, outside to outside
        x1, y1 = T(0, miny)
        x2, _ = T(W, miny)
        body += proj(x1, y1, x1, y1 + 22) + proj(x2, y1, x2, y1 + 22)
        body += hdim(x1, x2, y1 + 18, f"width {W}", active=True, above=False, size=11)
        body += text(cx * cw + cw / 2, 70 + cy * ch + 6, name, 13, INK, bold=True)
    cap = f"Left side: {conds['left']}. Right side: {conds['right']}. Left turns shown."
    body += text(400, 815, cap, 11, DIM)
    return svg("4  Width, sides and newels: plan per stair type", body,
               "Treads stop at the inner balustrade line. Corners shown as flat landings.", h=860)


SKETCHES["step4_options.svg"] = step4_options
if __name__ == "__main__":
    for name, fn in SKETCHES.items():
        with open(os.path.join(OUT, name), "w") as f:
            f.write(fn())
        print("wrote", name)
    with open(os.path.join(OUT, "step4_options.svg"), "w") as f:
        f.write(step4_options())
    with open(os.path.join(OUT, "step4_options_inverted.svg"), "w") as f:
        f.write(step4_options({"left": "wall", "right": "balustrade"}))


# ---------------------------------------------------------------- step 5 corners (whole plan + per-corner toggles)
def _corner_defs():
    """Landing squares that can become winders: (rect, newel centre, start angle of the turn quadrant)."""
    W, G, ns = P["stair_width"], P["going"], P["newel_size"]
    n1, n2 = 9, 3
    L = {"Single winder (L)": [((0, n1 * G, W, W), (ns / 2, n1 * G + ns / 2), 0)]}
    n1, n2 = 5, 2
    x2 = -n2 * G
    L["Double winder (U)"] = [((0, n1 * G, W, W), (ns / 2, n1 * G + ns / 2), 0),
                              ((x2 - W, n1 * G, W, W), (x2 - ns / 2, n1 * G + ns / 2), 90)]
    return L


def _ray_to_rect(px, py, ang, rect):
    x, y, w, h = rect
    dx, dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    ts = []
    for edge, t in (("x", (x - px) / dx if abs(dx) > 1e-9 else None), ("x", (x + w - px) / dx if abs(dx) > 1e-9 else None),
                    ("y", (y - py) / dy if abs(dy) > 1e-9 else None), ("y", (y + h - py) / dy if abs(dy) > 1e-9 else None)):
        if t is not None and t > 1e-6:
            qx, qy = px + dx * t, py + dy * t
            if x - 1e-6 <= qx <= x + w + 1e-6 and y - 1e-6 <= qy <= y + h + 1e-6:
                ts.append(t)
    t = min(ts)
    return px + dx * t, py + dy * t


def _toggle(x, y, label, winders):
    """Mock segmented control: 'Corner n  [Winders | Flat landing]'."""
    s = text(x, y + 15, label, 12, INK, bold=True, anchor="start")
    bx = x + 70
    for i, (name, on) in enumerate((("Winders", winders), ("Flat landing", not winders))):
        w = 70 if i == 0 else 92
        fill = APP_RED if on else FIELD
        s += f'<rect x="{bx:.1f}" y="{y:.1f}" width="{w}" height="22" fill="{fill}" stroke="#555555" stroke-width="1"/>\n'
        s += text(bx + w / 2, y + 15, name, 11, "#ffffff" if on else "#aaaaaa", bold=True)
        bx += w
    return s


def step5_corners():
    s = 0.088
    lays = _stair_layouts()
    cdefs = _corner_defs()
    ns = P["newel_size"]
    panels = [("Single winder (L)", [False], "L, corner as landing"),
              ("Single winder (L)", [True], "L, corner as winders"),
              ("Double winder (U)", [True, False], "U, corner 1 winders, corner 2 landing")]
    body = ""
    for i, (name, states, cap) in enumerate(panels):
        lay = lays[name]
        xs = [p[0] for p in lay["right"] + lay["left"]]
        ys = [p[1] for p in lay["right"] + lay["left"]]
        minx, maxx, miny = min(xs), max(xs), min(ys)
        cw = 800 / 3
        ox = i * cw + (cw - (maxx - minx) * s) / 2 - minx * s
        oy = 385 + miny * s

        def T(x, y, ox=ox, oy=oy):
            return (ox + x * s, oy - y * s)

        body += _plan(lay, T, s, {"left": "balustrade", "right": "wall"})
        for n, ((rect_, (cx, cy), a0), wind) in enumerate(zip(cdefs[name], states), start=1):
            mid = math.radians(a0 + 45)
            sx, sy = (1 if math.cos(mid) > 0 else -1), (1 if math.sin(mid) > 0 else -1)
            pcx, pcy = cx + sx * ns / 2, cy + sy * ns / 2
            if wind:
                # StairSmith set-out: inner ends fixed at the X marks on the two newel faces,
                # outer ends on rays from the winder centre (where the two marks intersect).
                X = P["winder_x"]

                def dvec(a):
                    return math.cos(math.radians(a)), math.sin(math.radians(a))
                m1 = (pcx + X * dvec(a0 - 90)[0], pcy + X * dvec(a0 - 90)[1])
                m2 = (pcx + X * dvec(a0 + 180)[0], pcy + X * dvec(a0 + 180)[1])
                wcx, wcy = pcx + X * (dvec(a0 - 90)[0] + dvec(a0 + 180)[0]), pcy + X * (dvec(a0 - 90)[1] + dvec(a0 + 180)[1])
                for (mx, my), a in ((m1, a0 + 30), (m2, a0 + 60)):
                    qx, qy = _ray_to_rect(wcx, wcy, a, rect_)
                    body += line(*T(mx, my), *T(qx, qy), ACC, 1.6)
            # corner number near the outer corner of the turn
            rx, ry, rw, rh = rect_
            ocx = rx + rw + 280 if sx > 0 else rx - 280
            ocy = ry + rh + 280
            tx, ty = T(ocx, ocy)
            body += f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="9" fill="{PANEL}" stroke="{INK}" stroke-width="1.2"/>\n'
            body += text(tx, ty + 4, str(n), 11, INK, bold=True)
        # toggles under each plan
        for n, wind in enumerate(states, start=1):
            body += _toggle(i * cw + 20, 410 + (n - 1) * 32, f"Corner {n}", wind)
        body += text(i * cw + cw / 2, 60, cap, 12, INK, bold=True)
    return svg("5  Corners", body,
               "Toggle each corner, or click it on the plan. Winder lines here are indicative; step 6 sets them out.", h=520)


SKETCHES["step5_corners.svg"] = step5_corners
if __name__ == "__main__":
    with open(os.path.join(OUT, "step5_corners.svg"), "w") as f:
        f.write(step5_corners())


# ---------------------------------------------------------------- step 5 with flight distribution
def _corners_from_layout(name, lay):
    W, ns = P["stair_width"], P["newel_size"]
    out = []
    for i, (x, y, w, h) in enumerate(lay["landings"]):
        if i == 0:
            out.append(((x, y, w, h), (x + ns / 2, y + ns / 2), 0))
        else:
            out.append(((x, y, w, h), (x + w - ns / 2, y + ns / 2), 90))
    return out


def _dist_widget(x, y, counts, moved=None):
    """Wizard version of StairSmith's flight distribution track: cyan counts, roomier arrow buttons."""
    s = ""
    cx = x
    bw, gap, side = 32, 6, 30
    for i, n in enumerate(counts):
        s += text(cx, y + 20, str(n), 22, ACC_T, bold=True)
        s += text(cx, y + 36, f"FLIGHT {i + 1}", 10, "#888888")
        if i < len(counts) - 1:
            bx = cx + side
            for j, glyph in enumerate(("&#9664;", "&#9654;")):
                s += f'<rect x="{bx + j * (bw + gap):.1f}" y="{y:.1f}" width="{bw}" height="40" rx="4" fill="#0f3460" stroke="#1a4a80" stroke-width="1"/>\n'
                s += text(bx + j * (bw + gap) + bw / 2, y + 24, glyph, 12, "#e0e0e0")
            cx = bx + 2 * bw + gap + side
    return s


def step5_corners_dist():
    s = 0.088
    ns = P["newel_size"]
    panels = [("Single winder (L)", {"L": (9, 3)}, [False], (9, 3), None, "L, automatic split"),
              ("Single winder (L)", {"L": (7, 5)}, [False], (7, 5), (0, 1), "L, two steps moved to flight 2"),
              ("Double winder (U)", {"U": (5, 2, 5)}, [True, False], (5, 2, 5), None, "U, corner 1 winders, corner 2 landing")]
    body = ""
    cw = 960 / 3
    for i, (name, counts, states, nums, moved, cap) in enumerate(panels):
        lay = _stair_layouts(counts)[name]
        xs = [p[0] for p in lay["right"] + lay["left"]]
        ys = [p[1] for p in lay["right"] + lay["left"]]
        minx, maxx, miny = min(xs), max(xs), min(ys)
        ox = i * cw + (cw - (maxx - minx) * s) / 2 - minx * s
        oy = 385 + miny * s

        def T(x, y, ox=ox, oy=oy):
            return (ox + x * s, oy - y * s)

        body += _plan(lay, T, s, {"left": "balustrade", "right": "wall"})
        # flights that changed length are traced in the accent
        if moved:
            for fi in moved:
                fx, fy, fw, fh = lay["flights"][fi]["rect"]
                body += poly([T(fx, fy), T(fx + fw, fy), T(fx + fw, fy + fh), T(fx, fy + fh)], ACC, 1.4).replace("/>", ' stroke-dasharray="5 3"/>')
        for n, ((rect_, (cx, cy), a0), wind) in enumerate(zip(_corners_from_layout(name, lay), states), start=1):
            mid = math.radians(a0 + 45)
            sx, sy = (1 if math.cos(mid) > 0 else -1), (1 if math.sin(mid) > 0 else -1)
            pcx, pcy = cx + sx * ns / 2, cy + sy * ns / 2
            if wind:
                X = P["winder_x"]

                def dvec(a):
                    return math.cos(math.radians(a)), math.sin(math.radians(a))
                m1 = (pcx + X * dvec(a0 - 90)[0], pcy + X * dvec(a0 - 90)[1])
                m2 = (pcx + X * dvec(a0 + 180)[0], pcy + X * dvec(a0 + 180)[1])
                wcx = pcx + X * (dvec(a0 - 90)[0] + dvec(a0 + 180)[0])
                wcy = pcy + X * (dvec(a0 - 90)[1] + dvec(a0 + 180)[1])
                for (mx, my), a in ((m1, a0 + 30), (m2, a0 + 60)):
                    qx, qy = _ray_to_rect(wcx, wcy, a, rect_)
                    body += line(*T(mx, my), *T(qx, qy), ACC, 1.6)
            rx, ry, rw, rh = rect_
            tx, ty = T(rx + rw + 280 if sx > 0 else rx - 280, ry + rh + 280)
            body += f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="9" fill="{PANEL}" stroke="{INK}" stroke-width="1.2"/>\n'
            body += text(tx, ty + 4, str(n), 11, INK, bold=True)
        for n, wind in enumerate(states, start=1):
            body += _toggle(i * cw + 20, 410 + (n - 1) * 32, f"Corner {n}", wind)
        # distribution track, centred in the panel
        span = (len(nums) - 1) * (2 * 30 + 2 * 32 + 6)
        body += text(i * cw + 20, 488, "Treads per flight", 11, DIM, anchor="start")
        body += _dist_widget(i * cw + cw / 2 - span / 2, 500, nums, moved)
        body += text(i * cw + cw / 2, 60, cap, 12, INK, bold=True)
    return svg("5  Corners", body,
               "Corner toggles, then treads per flight. Starts on the automatic split; the plan redraws as steps move.", w=960, h=600)


SKETCHES["step5_corners_dist.svg"] = step5_corners_dist
if __name__ == "__main__":
    with open(os.path.join(OUT, "step5_corners_dist.svg"), "w") as f:
        f.write(step5_corners_dist())
