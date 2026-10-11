"""
StairSmith wizard diagrams — SVG strings drawn from the current parameters.

Each public function takes a params dict and returns an SVG string.
Drawing helpers and palette ported from the handoff make_sketches.py.
"""

import math

# ── Palette (matches app.html dark theme) ──────────────────────────
INK = "#c9c9d4"
ACC = "#00ccff"
ACC_T = "#4fdcff"
DIM = "#8a93ad"
TITLE = "#e0e0e0"
PANEL = "#16213e"
FIELD = "#1a1a2e"
HATCH = "#5b6688"
APP_RED = "#e94560"
FONT = 'font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"'


# ── SVG helpers (ported from make_sketches.py) ─────────────────────

def _svg(body, w=400, h=300):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}">\n'
        f'<defs>\n'
        f'<marker id="a" viewBox="0 0 10 10" refX="10" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,1 L10,5 L0,9" fill="none" stroke="{DIM}" stroke-width="1.5"/></marker>\n'
        f'<marker id="aa" viewBox="0 0 10 10" refX="10" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,1 L10,5 L0,9" fill="none" stroke="{ACC}" stroke-width="1.5"/></marker>\n'
        f'<pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" '
        f'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" '
        f'stroke="{HATCH}" stroke-width="1"/></pattern>\n'
        f'</defs>\n'
        f'{body}</svg>'
    )


def _line(x1, y1, x2, y2, c=INK, w=2, dash=None, end=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#{end})"' if end else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{c}" stroke-width="{w}"{d}{m}/>\n'


def _poly(pts, c=INK, w=2, fill="none", close=True, end=None):
    tag = "polygon" if close else "polyline"
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    m = f' marker-end="url(#{end})"' if end else ""
    return f'<{tag} points="{p}" fill="{fill}" stroke="{c}" stroke-width="{w}" stroke-linejoin="round"{m}/>\n'


def _rect(x, y, w, h, c=INK, sw=2, fill="none"):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{c}" stroke-width="{sw}"/>\n'


def _text(x, y, s, size=13, c=INK, bold=False, anchor="middle", rot=None):
    b = ' font-weight="600"' if bold else ""
    r = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot is not None else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" {FONT} font-size="{size}" fill="{c}" text-anchor="{anchor}"{b}{r}>{s}</text>\n'


def _proj(x1, y1, x2, y2):
    return _line(x1, y1, x2, y2, DIM, 1, "4 3")


def _ticked(x1, y1, x2, y2, active):
    c = ACC if active else DIM
    w = 1.4 if active else 1.2
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    run = 4
    s = _line(x1 - ux * run, y1 - uy * run, x2 + ux * run, y2 + uy * run, c, w)
    k = 0.7071
    tx, ty = (ux * k - uy * k) * 5, (ux * k + uy * k) * 5
    for (px, py) in ((x1, y1), (x2, y2)):
        s += _line(px - tx, py - ty, px + tx, py + ty, c, 1.8)
    return s


def _mm(v):
    return f"{v:.0f}" if abs(v - round(v)) < 0.05 else f"{v:.1f}"


def _hdim(x1, x2, y, label, active=False, above=True, note=None, size=13, lx=None, anchor="middle"):
    small = abs(x2 - x1) < 30
    s = _ticked(x1, y, x2, y, active)
    if lx is None:
        lx_val, ty = (x1 + x2) / 2, (y - 5 if above else y + 14)
        nty = ty + (-14 if above else 13)
    else:
        lx_val, ty, nty = lx, y + 4, y + 19
    s += _text(lx_val, ty, label, size, ACC_T if active else INK, bold=True, anchor=anchor)
    if note:
        s += _text(lx_val, nty, note, 11, DIM, anchor=anchor)
    return s


def _vdim(x, y1, y2, label, active=False, right=True, note=None, size=13):
    s = _ticked(x, y1, x, y2, active)
    tx = x + 7 if right else x - 7
    anchor = "start" if right else "end"
    my = (y1 + y2) / 2
    s += _text(tx, my + 4, label, size, ACC_T if active else INK, bold=True, anchor=anchor)
    if note:
        s += _text(tx, my + 19, note, 11, DIM, anchor=anchor)
    return s


# ── Step 0: Stair type ─────────────────────────────────────────────

def step0_stair_type(params):
    """Four plan icons, selected one in cyan, arrows showing travel direction."""
    selected = params.get("staircase_type", "straight")
    s_factor = 0.055
    W = 900 * s_factor
    G = 227 * s_factor
    body = ""
    names = ["Straight", "Single winder (L)", "Double winder (U)", "Half-landing (U)"]
    keys = ["straight", "single_winder", "double_winder", "half_landing"]
    for i, (name, key) in enumerate(zip(names, keys)):
        cx, base = 100 + i * 200, 340
        sel = (key == selected)
        c = ACC if sel else INK
        ac, am = (ACC_T, "aa") if sel else (DIM, "a")
        if i == 0:
            n = 13
            x0 = cx - W / 2
            body += _rect(x0, base - n * G, W, n * G, c)
            for k in range(1, n):
                body += _line(x0, base - k * G, x0 + W, base - k * G, c, 1)
            arrow = [(cx, base - 6), (cx, base - n * G + 8)]
        elif i == 1:
            n1, n2 = 9, 3
            x0 = cx - (W + n2 * G) / 2
            top = base - n1 * G
            body += _rect(x0, top, W, n1 * G, c)
            for k in range(1, n1):
                body += _line(x0, base - k * G, x0 + W, base - k * G, c, 1)
            body += _rect(x0, top - W, W, W, c)
            body += _rect(x0 + W, top - W, n2 * G, W, c)
            for k in range(1, n2):
                body += _line(x0 + W + k * G, top - W, x0 + W + k * G, top, c, 1)
            arrow = [(x0 + W / 2, base - 6), (x0 + W / 2, top - W / 2), (x0 + W + n2 * G - 6, top - W / 2)]
        elif i == 2:
            n1, n2 = 6, 2
            span = 2 * W + n2 * G
            x0 = cx - span / 2
            x1 = x0 + W + n2 * G
            top = base - n1 * G
            for xx in (x0, x1):
                body += _rect(xx, top, W, n1 * G, c)
                for k in range(1, n1):
                    body += _line(xx, base - k * G, xx + W, base - k * G, c, 1)
                body += _rect(xx, top - W, W, W, c)
            body += _rect(x0 + W, top - W, n2 * G, W, c)
            for k in range(1, n2):
                body += _line(x0 + W + k * G, top - W, x0 + W + k * G, top, c, 1)
            arrow = [(x0 + W / 2, base - 6), (x0 + W / 2, top - W / 2),
                     (x1 + W / 2, top - W / 2), (x1 + W / 2, base - 8)]
        else:
            n1, gap = 6, 6
            x0 = cx - W - gap / 2
            x1 = x0 + W + gap
            top = base - n1 * G
            for xx in (x0, x1):
                body += _rect(xx, top, W, n1 * G, c)
                for k in range(1, n1):
                    body += _line(xx, base - k * G, xx + W, base - k * G, c, 1)
            body += _rect(x0, top - W, 2 * W + gap, W, c)
            body += _text(cx, top - W - 8, "landing", 10, DIM)
            arrow = [(x0 + W / 2, base - 6), (x0 + W / 2, top - W / 2),
                     (x1 + W / 2, top - W / 2), (x1 + W / 2, base - 8)]
        body += _poly(arrow, ac, 1.4, close=False, end=am)
        body += _text(cx, base + 30, name, 13, ACC_T if sel else INK, bold=True)
    body += _text(400, 405, "Corners start as flat landings; winders are chosen on the Corners step. Hand mirrors the turning types.", 11, DIM)
    return _svg(body, 800, 460)


# ── Step 1: Height ─────────────────────────────────────────────────

def step1_height(params):
    """Section through a two-storey house with the floor-to-floor dimension."""
    ftf = float(params.get("floor_to_floor", 2700))
    num_risers = int(params.get("num_risers", 14))
    going = float(params.get("going", 227))
    rise = ftf / num_risers

    s_factor = 0.07
    r, g = rise * s_factor, going * s_factor
    n = num_risers
    house_w = 7500
    upper = 2400
    joist = 250
    roof_rise_val = (house_w / 2) * math.tan(math.radians(30))

    xl, gy = 90, 565
    xr = xl + house_w * s_factor
    fy = gy - ftf * s_factor
    ey = fy - upper * s_factor
    ry = ey - roof_rise_val * s_factor
    tw, tr_val, ov = 300 * s_factor, 250 * s_factor, 300 * s_factor
    slab, found = 150 * s_factor, 450 * s_factor
    jz = joist * s_factor
    tan30 = math.tan(math.radians(30))
    xm = (xl + xr) / 2
    up = tr_val / math.cos(math.radians(30))

    body = ""

    # ground floor surface
    body += _line(xl + tw, gy, xr - tw, gy, INK, 2)
    body += _line(60, gy + slab, xl, gy + slab, INK, 2)
    body += _line(xr, gy + slab, 760, gy + slab, INK, 2)

    def yin(x):
        return ey - (x - xl) * tan30 if x <= xm else ey - (xr - x) * tan30

    li = (xl - ov, yin(xl - ov))
    ri = (xr + ov, yin(xr + ov))
    ai = (xm, yin(xm))

    # roof top surface and eaves ends
    body += _poly([(li[0], li[1] - up), (ai[0], ai[1] - up), (ri[0], ri[1] - up)], INK, 2, close=False)
    body += _line(li[0], li[1], li[0], li[1] - up, INK, 2)
    body += _line(ri[0], ri[1], ri[0], ri[1] - up, INK, 2)

    # roof underside
    body += _line(li[0], li[1], xl, yin(xl), INK, 2)
    body += _line(xr, yin(xr), ri[0], ri[1], INK, 2)
    body += _poly([(xl + tw, yin(xl + tw)), ai, (xr - tw, yin(xr - tw))], INK, 2, close=False)

    # walls
    for x in (xl, xr):
        body += _line(x, gy + slab, x, yin(x), INK, 2)
    for x in (xl + tw, xr - tw):
        body += _line(x, yin(x), x, fy, INK, 2)
        body += _line(x, fy + jz, x, gy, INK, 2)

    # stair, starting 1m off the inside face of the left wall
    x0 = xl + tw + 1000 * s_factor
    pts = [(x0, gy)]
    sx, sy = x0, gy
    for k in range(n):
        sy -= r
        pts.append((sx, sy))
        if k < n - 1:
            sx += g
            pts.append((sx, sy))
    body += _poly(pts, INK, 1.4, close=False)

    # first floor zone with stairwell opening
    xt = x0 + (n - 1) * g
    open_l = xt - 2600 * s_factor
    body += _line(xl + tw, fy, open_l, fy, INK, 2)
    body += _line(xl + tw, fy + jz, open_l, fy + jz, INK, 2)
    body += _line(open_l, fy, open_l, fy + jz, INK, 2)
    body += _line(xt, fy, xr - tw, fy, INK, 2)
    body += _line(xt, fy + jz, xr - tw, fy + jz, INK, 2)
    body += _line(xt, fy, xt, fy + jz, INK, 2)

    # floor to floor dimension
    dx = xr + 40
    body += _proj(xr, gy, dx + 4, gy)
    body += _proj(xr, fy, dx + 4, fy)
    body += _vdim(dx, gy, fy, f"{_mm(ftf)}", active=True, note="floor to floor, mm")

    body += _text(xr - tw - 10, gy - 10, "ground floor", 11, DIM, anchor="end")
    body += _text(xr - tw - 10, fy - 10, "first floor", 11, DIM, anchor="end")

    return _svg(body, 800, 640)


# ── Dispatch ───────────────────────────────────────────────────────

_DIAGRAM_FUNCTIONS = {
    "step0_stair_type": step0_stair_type,
    "step1_height": step1_height,
}


def get_diagram(step_id, params):
    fn = _DIAGRAM_FUNCTIONS.get(step_id)
    if fn:
        return fn(params)
    return ""
