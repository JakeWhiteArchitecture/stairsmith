"""
StairSmith wizard diagrams — SVG strings drawn from the current parameters.

Each public stepN function takes a params dict and returns an SVG string.
From step 2 onwards, values come from StairSmith's own parsing and geometry
(stair_constants._parse) so the drawing and the 3D model agree.
Drawing helpers and palette ported from the handoff make_sketches.py.
"""

import math

from stair_constants import _parse, pitch_degrees

# ── Palette (matches app.html dark theme) ──────────────────────────
INK = "#c9c9d4"      # context linework
ACC = "#00ccff"      # what the current step sets
ACC_T = "#4fdcff"    # accent text
DIM = "#8a93ad"      # dimensions, projectors, reference values
TITLE = "#e0e0e0"    # headings
PANEL = "#16213e"    # wizard panel; also masks lines behind newels
FIELD = "#1a1a2e"    # inactive toggle background
HATCH = "#5b6688"    # wall hatch
APP_RED = "#e94560"  # active toggle, mock UI only
FONT = 'font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"'

# Fixed values for diagrams that do not follow the parameters.
_REF_FTF = 2700.0
_REF_RISERS = 14
_REF_GOING = 227.0
_REF_WIDTH = 900.0


# ── SVG helpers ────────────────────────────────────────────────────

def _svg(body, viewbox):
    x, y, w, h = viewbox
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {w} {h}" '
        f'width="{w}" height="{h}">\n'
        f'<defs>\n'
        f'<marker id="wz-a" viewBox="0 0 10 10" refX="10" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,1 L10,5 L0,9" fill="none" stroke="{DIM}" stroke-width="1.5"/></marker>\n'
        f'<marker id="wz-aa" viewBox="0 0 10 10" refX="10" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,1 L10,5 L0,9" fill="none" stroke="{ACC}" stroke-width="1.5"/></marker>\n'
        f'<pattern id="wz-hatch" width="8" height="8" patternUnits="userSpaceOnUse" '
        f'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" '
        f'stroke="{HATCH}" stroke-width="1"/></pattern>\n'
        f'</defs>\n'
        f'{body}</svg>'
    )


def _line(x1, y1, x2, y2, c=INK, w=2, dash=None, end=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#wz-{end})"' if end else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{c}" stroke-width="{w}"{d}{m}/>\n'


def _poly(pts, c=INK, w=2, fill="none", close=True, end=None):
    tag = "polygon" if close else "polyline"
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    m = f' marker-end="url(#wz-{end})"' if end else ""
    return f'<{tag} points="{p}" fill="{fill}" stroke="{c}" stroke-width="{w}" stroke-linejoin="round"{m}/>\n'


def _rect(x, y, w, h, c=INK, sw=2, fill="none"):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{c}" stroke-width="{sw}"/>\n'


def _text(x, y, s, size=13, c=INK, bold=False, anchor="middle"):
    b = ' font-weight="600"' if bold else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" {FONT} font-size="{size}" fill="{c}" text-anchor="{anchor}"{b}>{s}</text>\n'


def _proj(x1, y1, x2, y2):
    return _line(x1, y1, x2, y2, DIM, 1, "4 3")


def _ticked(x1, y1, x2, y2, active):
    """Dimension line with oblique (45 degree) ticks, running slightly past them."""
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
    s = _ticked(x1, y, x2, y, active)
    if lx is None:
        lx, ty = (x1 + x2) / 2, (y - 5 if above else y + 14)
        nty = ty + (-14 if above else 13)
    else:
        ty, nty = y + 4, y + 19
    s += _text(lx, ty, label, size, ACC_T if active else INK, bold=True, anchor=anchor)
    if note:
        s += _text(lx, nty, note, 11, DIM, anchor=anchor)
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


def _pick(param, value, x, y, w, h, inner):
    """Wrap a group so the wizard can make it clickable to set param=value."""
    hit = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#000" fill-opacity="0"/>\n'
    return (f'<g data-param="{param}" data-value="{value}" style="cursor:pointer">\n'
            f'{hit}{inner}</g>\n')


# ── Step 0: Stair type ─────────────────────────────────────────────

def step0_stair_type(params):
    """Fixed plan icons, the selected type in the accent colour, arrows for the line of travel."""
    selected = params.get("staircase_type", "straight")
    sc = 0.055
    W, G = _REF_WIDTH * sc, _REF_GOING * sc
    body = ""
    names = ["Straight", "Single winder (L)", "Double winder (U)", "Half-landing (U)"]
    keys = ["straight", "single_winder", "double_winder", "half_landing"]
    for i, (name, key) in enumerate(zip(names, keys)):
        cx, base = 100 + i * 200, 340
        sel = key == selected
        c = ACC if sel else INK
        ac, am = (ACC_T, "aa") if sel else (DIM, "a")
        g = ""
        if i == 0:
            n = _REF_RISERS - 1
            x0 = cx - W / 2
            g += _rect(x0, base - n * G, W, n * G, c)
            for k in range(1, n):
                g += _line(x0, base - k * G, x0 + W, base - k * G, c, 1)
            arrow = [(cx, base - 6), (cx, base - n * G + 8)]
        elif i == 1:
            n1, n2 = 9, 3
            x0 = cx - (W + n2 * G) / 2
            top = base - n1 * G
            g += _rect(x0, top, W, n1 * G, c)
            for k in range(1, n1):
                g += _line(x0, base - k * G, x0 + W, base - k * G, c, 1)
            g += _rect(x0, top - W, W, W, c)
            g += _rect(x0 + W, top - W, n2 * G, W, c)
            for k in range(1, n2):
                g += _line(x0 + W + k * G, top - W, x0 + W + k * G, top, c, 1)
            arrow = [(x0 + W / 2, base - 6), (x0 + W / 2, top - W / 2), (x0 + W + n2 * G - 6, top - W / 2)]
        elif i == 2:
            n1, n2 = 6, 2
            x0 = cx - (2 * W + n2 * G) / 2
            x1 = x0 + W + n2 * G
            top = base - n1 * G
            for xx in (x0, x1):
                g += _rect(xx, top, W, n1 * G, c)
                for k in range(1, n1):
                    g += _line(xx, base - k * G, xx + W, base - k * G, c, 1)
                g += _rect(xx, top - W, W, W, c)
            g += _rect(x0 + W, top - W, n2 * G, W, c)
            for k in range(1, n2):
                g += _line(x0 + W + k * G, top - W, x0 + W + k * G, top, c, 1)
            arrow = [(x0 + W / 2, base - 6), (x0 + W / 2, top - W / 2),
                     (x1 + W / 2, top - W / 2), (x1 + W / 2, base - 8)]
        else:
            n1, gap = 6, 6
            x0 = cx - W - gap / 2
            x1 = x0 + W + gap
            top = base - n1 * G
            for xx in (x0, x1):
                g += _rect(xx, top, W, n1 * G, c)
                for k in range(1, n1):
                    g += _line(xx, base - k * G, xx + W, base - k * G, c, 1)
            g += _rect(x0, top - W, 2 * W + gap, W, c)
            g += _text(cx, top - W - 8, "landing", 10, DIM)
            arrow = [(x0 + W / 2, base - 6), (x0 + W / 2, top - W / 2),
                     (x1 + W / 2, top - W / 2), (x1 + W / 2, base - 8)]
        g += _poly(arrow, ac, 1.4, close=False, end=am)
        g += _text(cx, base + 30, name, 13, ACC_T if sel else INK, bold=True)
        body += _pick("staircase_type", key, cx - 95, 165, 190, base + 40 - 165, g)
    body += _text(400, 405, "Corners start as flat landings; winders are chosen on the Corners step. "
                            "Hand mirrors the turning types.", 11, DIM)
    return _svg(body, (40, 160, 720, 260))


# ── Step 1: Height ─────────────────────────────────────────────────

def step1_height(params):
    """Fixed section through a two-storey house; only the floor-to-floor figure follows the value."""
    ftf_label = float(params.get("floor_to_floor", _REF_FTF))
    s = 0.07
    ftf, n = _REF_FTF, _REF_RISERS
    r, g = (ftf / n) * s, _REF_GOING * s
    house_w, upper, joist = 7500, 2400, 250
    xl, gy = 90, 565
    xr = xl + house_w * s
    fy = gy - ftf * s
    ey = fy - upper * s
    tw, tr, ov = 300 * s, 250 * s, 300 * s
    slab = 150 * s
    jz = joist * s
    tan30 = math.tan(math.radians(30))
    xm = (xl + xr) / 2
    up = tr / math.cos(math.radians(30))

    def yin(x):
        return ey - (x - xl) * tan30 if x <= xm else ey - (xr - x) * tan30

    body = _line(xl + tw, gy, xr - tw, gy, INK, 2)
    body += _line(60, gy + slab, xl, gy + slab, INK, 2) + _line(xr, gy + slab, 760, gy + slab, INK, 2)
    li, ri, ai = (xl - ov, yin(xl - ov)), (xr + ov, yin(xr + ov)), (xm, yin(xm))
    body += _poly([(li[0], li[1] - up), (ai[0], ai[1] - up), (ri[0], ri[1] - up)], INK, 2, close=False)
    body += _line(li[0], li[1], li[0], li[1] - up, INK, 2) + _line(ri[0], ri[1], ri[0], ri[1] - up, INK, 2)
    body += _line(*li, xl, yin(xl), INK, 2) + _line(xr, yin(xr), *ri, INK, 2)
    body += _poly([(xl + tw, yin(xl + tw)), ai, (xr - tw, yin(xr - tw))], INK, 2, close=False)
    for x in (xl, xr):
        body += _line(x, gy + slab, x, yin(x), INK, 2)
    for x in (xl + tw, xr - tw):
        body += _line(x, yin(x), x, fy, INK, 2)
        body += _line(x, fy + jz, x, gy, INK, 2)
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
    body += _poly(pts, INK, 1.4, close=False)
    # first floor zone with the stairwell opening over the stair
    open_l = xt - 2600 * s
    body += _line(xl + tw, fy, open_l, fy, INK, 2) + _line(xl + tw, fy + jz, open_l, fy + jz, INK, 2)
    body += _line(open_l, fy, open_l, fy + jz, INK, 2)
    body += _line(xt, fy, xr - tw, fy, INK, 2) + _line(xt, fy + jz, xr - tw, fy + jz, INK, 2)
    body += _line(xt, fy, xt, fy + jz, INK, 2)
    dx = xr + 40
    body += _proj(xr, gy, dx + 4, gy) + _proj(xr, fy, dx + 4, fy)
    body += _vdim(dx, gy, fy, _mm(ftf_label), active=True, note="floor to floor, mm")
    body += _text(xr - tw - 10, gy - 10, "ground floor", 11, DIM, anchor="end")
    body += _text(xr - tw - 10, fy - 10, "first floor", 11, DIM, anchor="end")
    return _svg(body, (40, 20, 740, 570))


# ── Step 2: Risers and going ───────────────────────────────────────

def step2_risers_going(params):
    """Three steps in section from the live values; going dimensioned nosing to nosing."""
    p = _parse(params)
    rise, going, nosing, tt_mm = p["rise"], p["going"], p["nosing"], p["tread_thickness"]
    pitch = pitch_degrees(rise, going)
    # Same scale as the sketch for usual values; shrinks only if three rises would not fit.
    s = min(0.5, 290.0 / (3 * rise), 150.0 / going)
    r, g, nos, tt = rise * s, going * s, nosing * s, tt_mm * s
    x0, y0 = 150, 385
    body = _line(x0 - 40, y0, x0 + 3 * g + 30, y0, INK, 1)
    for k in range(3):
        rx, ry = x0 + k * g, y0 - k * r
        body += _line(rx, ry, rx, ry - r + tt, INK, 2)
        body += _rect(rx - nos, ry - r, g + nos if k < 2 else g + nos + 30, tt, INK, 1.6)
    # pitch line through the nosings
    body += _line(x0 - nos, y0 - r, x0 + 2.4 * g - nos, y0 - 3.4 * r, DIM, 1, "4 3")
    body += _text(x0 + 0.3 * g, y0 - 2 * r, f"pitch {pitch:.1f}°", 12, DIM, anchor="end")
    # going: nosing to nosing, below the section
    gx1, gx2 = x0 + g - nos, x0 + 2 * g - nos
    body += _proj(gx1, y0 - 2 * r, gx1, y0 + 20) + _proj(gx2, y0 - 3 * r, gx2, y0 + 20)
    body += _hdim(gx1, gx2, y0 + 16, f"going {_mm(going)}", active=True, above=False)
    # rise: right of the top step, reference only
    rxx = x0 + 3 * g + 50
    body += _proj(x0 + 3 * g, y0 - 2 * r, rxx + 4, y0 - 2 * r)
    body += _proj(x0 + 3 * g + 30, y0 - 3 * r, rxx + 4, y0 - 3 * r)
    body += _vdim(rxx, y0 - 2 * r, y0 - 3 * r, f"rise {_mm(rise)}", note="reference")
    # nosing on the top tread
    nx1, nx2 = x0 + 2 * g - nos, x0 + 2 * g
    ny = y0 - 3 * r - 28
    body += _proj(nx1, y0 - 3 * r, nx1, ny - 4) + _proj(nx2, y0 - 3 * r, nx2, ny - 4)
    body += _hdim(nx1, nx2, ny, f"nosing {_mm(nosing)}", active=True, size=12)
    body += _text(560, 360, f"risers {p['num_risers']}", 14, ACC_T, bold=True, anchor="start")
    body += _text(560, 377, f"treads {p['num_treads']}  ·  rise {_mm(rise)}  ·  pitch {pitch:.1f}°",
                  11, DIM, anchor="start")
    body += _text(400, 442, "Accent: values set on this step. Grey: reference values only, "
                            "not a compliance check.", 11, DIM)
    return _svg(body, (60, 30, 720, 425))


# ── Step 3: Treads and risers ──────────────────────────────────────

def step3_treads_risers(params):
    """One tread and riser close up in section, set within the flight, neighbours cut open."""
    p = _parse(params)
    s = min(1.1, 225.0 / p["rise"], 300.0 / p["going"])
    r, g, nos = p["rise"] * s, p["going"] * s, p["nosing"] * s
    tt, rt = p["tread_thickness"] * s, p["riser_thickness"] * s
    x0, y0 = 300, 390          # face of this riser, top of the tread below
    ty = y0 - r                # top of this tread
    cut = 150
    # tread below: open at its front, this riser sits on its back edge
    body = _line(x0 - cut, y0, x0 + rt, y0, INK, 2) + _line(x0 - cut, y0 + tt, x0 + rt, y0 + tt, INK, 2)
    body += _line(x0 + rt, y0, x0 + rt, y0 + tt, INK, 2)
    # this riser and this tread
    body += _rect(x0, ty + tt, rt, y0 - ty - tt, ACC)
    body += _rect(x0 - nos, ty, nos + g + rt, tt, ACC)
    # next riser rising off the back edge of this tread, cut open above
    xb = x0 + g
    body += _line(xb, ty, xb, ty - 110, INK, 2) + _line(xb + rt, ty, xb + rt, ty - 110, INK, 2)
    # dimensions
    tx = x0 - nos - 44
    body += _proj(x0 - nos, ty, tx - 4, ty) + _proj(x0 - nos, ty + tt, tx - 4, ty + tt)
    body += _vdim(tx, ty, ty + tt, f"tread {_mm(p['tread_thickness'])}", active=True, right=False)
    body += _hdim(x0, x0 + rt, y0 - r / 2, f"riser {_mm(p['riser_thickness'])}", active=True,
                  lx=x0 + rt + 26, anchor="start")
    body += _proj(x0 - nos, ty, x0 - nos, ty - 26) + _proj(x0, ty, x0, ty - 26)
    body += _hdim(x0 - nos, x0, ty - 22, f"nosing {_mm(p['nosing'])}", note="set on step 2")
    return _svg(body, (110, 40, 580, 400))


# ── Dispatch ───────────────────────────────────────────────────────

_DIAGRAM_FUNCTIONS = {
    "step0_stair_type": step0_stair_type,
    "step1_height": step1_height,
    "step2_risers_going": step2_risers_going,
    "step3_treads_risers": step3_treads_risers,
}


def available_diagrams():
    return list(_DIAGRAM_FUNCTIONS)


def get_diagram(step_id, params):
    fn = _DIAGRAM_FUNCTIONS.get(step_id)
    return fn(params) if fn else ""
