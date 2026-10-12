"""
StairSmith wizard diagrams — SVG strings drawn from the current parameters.

Each public stepN function takes a params dict and returns an SVG string.
From step 2 onwards, values come from StairSmith's own parsing and geometry
(stair_constants._parse, and stair_plan.plan_geometry for the plans) so the
drawing and the 3D model agree.
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


# ── Plan drawings (steps 4 to 6) ───────────────────────────────────
# Everything below is drawn from stair_plan.plan_geometry(), i.e. from the
# meshes StairSmith builds for the 3D model.

_HATCH_DEPTH = 110.0   # mm of wall hatch shown outside a wall line


def _lines_of(geom):
    """Coordinate lists for every line in a shapely geometry."""
    if geom is None or geom.is_empty:
        return []
    t = geom.geom_type
    if t == "LineString":
        return [list(geom.coords)]
    if t == "LinearRing":
        return [list(geom.coords)]
    if t == "Polygon":
        return [list(geom.exterior.coords)] + [list(r.coords) for r in geom.interiors]
    out = []
    for g in getattr(geom, "geoms", []):
        out.extend(_lines_of(g))
    return out


def _polys_of(geom):
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]


def _path_d(poly, T):
    d = ""
    for ring in [poly.exterior] + list(poly.interiors):
        pts = [T(x, y) for x, y in ring.coords]
        d += "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z "
    return d


def _plan_parts(g):
    """Visible plan linework in model mm, split by what it belongs to."""
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union

    cover = None
    edges_by_kind = {"corner": [], "other": []}
    corner_names = set()
    for e in g["elements"]:
        if e["kind"] == "winder" or (e["kind"] == "landing" and e["name"] != "Half Landing"):
            corner_names.add(e["name"])
    # Top down: each surface shows only the outline not already hidden by a higher one.
    for e in sorted(g["elements"], key=lambda e: -e["z"]):
        ring = e["poly"].boundary
        vis = ring if cover is None else ring.difference(cover)
        edges_by_kind["corner" if e["name"] in corner_names else "other"].append(vis)
        cover = e["poly"] if cover is None else cover.union(e["poly"])

    newels = unary_union(g["newels"]) if g["newels"] else None
    wall_lines, bands, cuts = [], [], []
    for s in g["stringers"]:
        if not s["wall"]:
            continue
        x0, y0, x1, y1 = s["rect"].bounds
        nx, ny = s["outward"]
        if s["axis"] == "y":
            face, c = (x1 if nx > 0 else x0), (x0 + x1) / 2
            wall_lines.append(LineString([(face, y0), (face, y1)]))
            bands.append(box(min(face, face + nx * _HATCH_DEPTH), y0 - _HATCH_DEPTH,
                             max(face, face + nx * _HATCH_DEPTH), y1 + _HATCH_DEPTH))
            cuts.append(box(min(c, face + nx * 3), y0, max(c, face + nx * 3), y1))
        else:
            face, c = (y1 if ny > 0 else y0), (y0 + y1) / 2
            wall_lines.append(LineString([(x0, face), (x1, face)]))
            bands.append(box(x0 - _HATCH_DEPTH, min(face, face + ny * _HATCH_DEPTH),
                             x1 + _HATCH_DEPTH, max(face, face + ny * _HATCH_DEPTH)))
            cuts.append(box(x0, min(c, face + ny * 3), x1, max(c, face + ny * 3)))
    # Nothing is drawn beyond the inner handrail line or the wall face, or inside a newel.
    cut = unary_union(list(g["handrails"]) + cuts + ([newels] if newels is not None else []))
    edges = {}
    for k, parts in edges_by_kind.items():
        geom = unary_union(parts) if parts else None
        if geom is not None and not cut.is_empty:
            geom = geom.difference(cut)
        edges[k] = geom
    hatch = unary_union(bands).difference(g["footprint"]) if bands else None
    wall = unary_union(wall_lines) if wall_lines else None
    if newels is not None:
        if hatch is not None:
            hatch = hatch.difference(newels)
        if wall is not None:
            wall = wall.difference(newels)
    return {"edges": edges, "hatch": hatch, "wall": wall, "path": _travel_path(g)}


def _travel_path(g):
    """Line of travel along each flight's centreline, turning where centrelines meet."""
    from shapely.geometry import LineString
    runs = []   # consecutive treads of one flight, in walking order
    for e in g["elements"]:
        if e["kind"] != "tread":
            continue
        if runs and runs[-1]["flight"] == e["flight"]:
            runs[-1]["treads"].append(e)
        else:
            runs.append({"flight": e["flight"], "treads": [e]})
    if not runs:
        return None
    for r in runs:
        a, b = r["treads"][0]["poly"], r["treads"][-1]["poly"]
        x0, y0, x1, y1 = a.bounds
        if len(r["treads"]) > 1:
            along_y = abs(b.centroid.y - a.centroid.y) >= abs(b.centroid.x - a.centroid.x)
        else:
            along_y = (x1 - x0) >= (y1 - y0)       # a tread is wider than it is deep
        r["along_y"] = along_y
        r["lat"] = a.centroid.x if along_y else a.centroid.y
        r["start"] = a.centroid.y if along_y else a.centroid.x
        r["end"] = b.centroid.y if along_y else b.centroid.x

    def pt(r, along):
        return (r["lat"], along) if r["along_y"] else (along, r["lat"])

    pts = [pt(runs[0], runs[0]["start"])]
    for r, nxt in zip(runs, runs[1:]):
        if r["along_y"] != nxt["along_y"]:
            pts.append((r["lat"], nxt["lat"]) if r["along_y"] else (nxt["lat"], r["lat"]))
        else:
            # parallel flights either side of a half-landing: cross at the landing's middle
            between = [e for e in g["elements"] if e["kind"] == "landing"
                       and r["treads"][-1]["z"] < e["z"] < nxt["treads"][0]["z"]]
            if between:
                c = between[0]["poly"].centroid
                mid = c.y if r["along_y"] else c.x
                pts += [pt(r, mid), pt(nxt, mid)]
    pts.append(pt(runs[-1], runs[-1]["end"]))
    return LineString(pts) if len(pts) > 1 else None


def _fit(bounds, x0, y0, w, h, max_scale=0.2):
    """Uniform plan-to-SVG transform fitting model bounds into a box, y up."""
    bx0, by0, bx1, by1 = bounds
    s = min(w / max(bx1 - bx0, 1), h / max(by1 - by0, 1), max_scale)
    ox = x0 + (w - (bx1 - bx0) * s) / 2 - bx0 * s
    oy = y0 + (h - (by1 - by0) * s) / 2 + by1 * s

    def T(x, y):
        return (ox + x * s, oy - y * s)
    return T, s


def _plan_bounds(g, parts):
    from shapely.ops import unary_union
    geoms = [g["footprint"]] + list(g["newels"]) + list(g["handrails"])
    if parts["hatch"] is not None and not parts["hatch"].is_empty:
        geoms.append(parts["hatch"])
    return unary_union(geoms).bounds


def _draw_plan(g, parts, T, s, rail_c=ACC, corner_c=INK):
    body = ""
    for poly in _polys_of(parts["hatch"]):
        body += f'<path d="{_path_d(poly, T)}" fill="url(#wz-hatch)" stroke="none" fill-rule="evenodd"/>\n'
    for pts in _lines_of(parts["edges"]["other"]):
        body += _poly([T(*p) for p in pts], INK, 1, close=False)
    for pts in _lines_of(parts["edges"]["corner"]):
        body += _poly([T(*p) for p in pts], corner_c, 1.4 if corner_c != INK else 1, close=False)
    for pts in _lines_of(parts["wall"]):
        body += _poly([T(*p) for p in pts], INK, 2.2, close=False)
    for r in g["handrails"]:
        body += f'<path d="{_path_d(r, T)}" fill="{PANEL}" stroke="{rail_c}" stroke-width="1.4"/>\n'
    for n in g["newels"]:
        body += f'<path d="{_path_d(n, T)}" fill="{PANEL}" stroke="{rail_c}" stroke-width="1.6"/>\n'
    if parts["path"] is not None:
        body += _poly([T(*p) for p in parts["path"].coords], DIM, 1.2, close=False, end="a")
    return body


def _first_flight_faces(g):
    """Outside faces of the first tread across its width, and its direction of travel."""
    t = g["first_tread"]
    if t is None:
        return None
    x0, y0, x1, y1 = t["poly"].bounds
    across_x = (x1 - x0) >= (y1 - y0)
    st = g["stringer_thickness"] / 2
    later = [e for e in g["elements"] if e["z"] > t["z"]]
    c = t["poly"].centroid
    n = later[0]["poly"].centroid if later else c
    if across_x:
        return {"across": "x", "a": x0 - st, "b": x1 + st, "dir": 1 if n.y >= c.y else -1}
    return {"across": "y", "a": y0 - st, "b": y1 + st, "dir": 1 if n.x >= c.x else -1}


def _plan_or_message(params, w, h):
    try:
        from stair_plan import plan_geometry
        return plan_geometry(params), None
    except Exception as err:   # the wizard keeps working if the plan can't be drawn
        return None, _svg(_text(w / 2, h / 2, f"Plan unavailable: {type(err).__name__}", 13, DIM), (0, 0, w, h))


# ── Step 4: Width, sides and newels ────────────────────────────────

def step4_width_sides(params):
    W, H = 720, 470
    g, msg = _plan_or_message(params, W, H)
    if msg:
        return msg
    parts = _plan_parts(g)
    T, s = _fit(_plan_bounds(g, parts), 60, 20, W - 120, H - 110)
    body = _draw_plan(g, parts, T, s)
    f = _first_flight_faces(g)
    if f and f["across"] == "x":
        bx0, by0, bx1, by1 = _plan_bounds(g, parts)
        start_y = g["first_tread"]["poly"].bounds[1]
        xa, ya = T(f["a"], start_y)
        xb, _ = T(f["b"], start_y)
        dy = T(0, by0)[1] + 26
        body += _proj(xa, ya, xa, dy + 4) + _proj(xb, ya, xb, dy + 4)
        body += _hdim(xa, xb, dy, f"width {_mm(g['params']['stair_width'])}", active=True, above=False,
                      note="outside to outside")
        # flight 1 runs +Y in the model, so the walker's left is -X
        left_x, right_x = (xa, xb) if f["dir"] > 0 else (xb, xa)
        body += _text(left_x - 10, dy + 4, "left", 11, DIM, anchor="end")
        body += _text(right_x + 10, dy + 4, "right", 11, DIM, anchor="start")
    body += _text(W / 2, H - 8, "Left and right as you walk up. Treads stop at the inner handrail line.", 11, DIM)
    return _svg(body, (0, 0, W, H))


# ── Step 5: Corners ────────────────────────────────────────────────

def _corner_label_pos(g, poly, T):
    """A point just outside the plan, diagonally out from the corner's newel."""
    c = poly.centroid
    newel = min(g["newels"], key=lambda n: n.distance(poly)) if g["newels"] else None
    ux, uy = (c.x - newel.centroid.x, c.y - newel.centroid.y) if newel is not None else (1.0, 1.0)
    sx, sy = (1 if ux >= 0 else -1), (1 if uy >= 0 else -1)
    x0, y0, x1, y1 = poly.bounds
    px, py = T(x1 if sx > 0 else x0, y1 if sy > 0 else y0)
    return px + sx * 22, py - sy * 22


def _step5_half_landing(g, parts, W, H):
    T, s = _fit(_plan_bounds(g, parts), 60, 60, W - 120, H - 150)
    body = _draw_plan(g, parts, T, s)
    hl = next((e for e in g["elements"] if e["name"] == "Half Landing"), None)
    if hl is not None:
        x0, y0, x1, y1 = hl["poly"].bounds
        lx0, ly = T(x0, y1)
        lx1, _ = T(x1, y1)
        top = T(0, _plan_bounds(g, parts)[3])[1] - 18
        body += _proj(lx0, ly, lx0, top - 4) + _proj(lx1, ly, lx1, top - 4)
        body += _hdim(lx0, lx1, top, f"landing width {_mm(x1 - x0)}", active=True)
        # the two newels either side of the well: same line, nearest pair
        ns = sorted(g["newels"], key=lambda n: hl["poly"].distance(n))[:6]
        pairs = [(a, b) for i, a in enumerate(ns) for b in ns[i + 1:]
                 if abs(a.centroid.y - b.centroid.y) < 1.0]
        if pairs:
            a, b = min(pairs, key=lambda ab: abs(ab[0].centroid.x - ab[1].centroid.x))
            ca, cb = sorted((a.centroid.x, b.centroid.x))
            ntn = cb - ca
            base = T(0, _plan_bounds(g, parts)[1])[1] + 24
            xa, ya = T(ca, a.centroid.y)
            xb, _ = T(cb, a.centroid.y)
            body += _proj(xa, ya, xa, base + 4) + _proj(xb, ya, xb, base + 4)
            body += _hdim(xa, xb, base, f"newel to newel {_mm(ntn)}", active=True,
                          note="centre to centre", lx=xb + 14, anchor="start")
    body += _text(W / 2, H - 8, "Half-landing: newel spacing and landing width, as built.", 11, DIM)
    return _svg(body, (0, 0, W, H))


def step5_corners(params):
    W, H = 720, 470
    g, msg = _plan_or_message(params, W, H)
    if msg:
        return msg
    parts = _plan_parts(g)
    if g["params"]["staircase_type"] == "half_landing":
        return _step5_half_landing(g, parts, W, H)
    T, s = _fit(_plan_bounds(g, parts), 70, 50, W - 140, H - 100)
    body = _draw_plan(g, parts, T, s, corner_c=ACC)
    for turn in sorted(g["corners"]):
        c = g["corners"][turn]
        hit = "".join(f'<path d="{_path_d(poly, T)}" fill="#000" fill-opacity="0" stroke="none"/>'
                      for poly in _polys_of(c["poly"]))
        lx, ly = _corner_label_pos(g, c["poly"], T)
        mark = (f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="11" fill="{PANEL}" stroke="{ACC}" stroke-width="1.4"/>\n'
                + _text(lx, ly + 4.5, str(turn), 12, ACC_T, bold=True))
        flip = "false" if c["kind"] == "winders" else "true"
        body += (f'<g data-param="turn{turn}_enabled" data-value="{flip}" style="cursor:pointer">'
                 f'<title>Corner {turn}: click to switch to {"flat landing" if flip == "false" else "winders"}</title>\n'
                 f'{hit}{mark}</g>\n')
    body += _text(W / 2, H - 8, "Click a corner, or use the toggles. Corners are numbered in walking order.", 11, DIM)
    return _svg(body, (0, 0, W, H))


# ── Step 6: Winder set-out ─────────────────────────────────────────

def step6_winder_setout(params):
    from shapely.geometry import box
    W, H = 720, 470
    g, msg = _plan_or_message(params, W, H)
    if msg:
        return msg
    winder_turns = sorted(t for t, c in g["corners"].items() if c["kind"] == "winders")
    if not winder_turns or not g["newels"]:
        return _svg(_text(W / 2, H / 2, "No winder corner to show.", 13, DIM), (0, 0, W, H))
    corner = g["corners"][winder_turns[0]]["poly"]
    newel = min(g["newels"], key=lambda n: n.distance(corner))
    ncx, ncy = newel.centroid.x, newel.centroid.y
    wc = corner.centroid
    sx, sy = (1 if wc.x >= ncx else -1), (1 if wc.y >= ncy else -1)
    nx0, ny0, nx1, ny1 = newel.bounds
    icx, icy = (nx1 if sx > 0 else nx0), (ny1 if sy > 0 else ny0)    # inside corner
    half = 430.0
    cx, cy = ncx + sx * 40, ncy + sy * 40
    win = (cx - half, cy - half, cx + half, cy + half)
    parts = _plan_parts(g)
    T, s = _fit(win, 60, 15, W - 120, H - 30, max_scale=1.0)
    (ax, ay), (bx, by) = T(win[0], win[3]), T(win[2], win[1])
    body = (f'<clipPath id="wz-crop"><rect x="{ax:.1f}" y="{ay:.1f}" width="{bx - ax:.1f}" '
            f'height="{by - ay:.1f}"/></clipPath>\n')
    body += f'<g clip-path="url(#wz-crop)">{_draw_plan(g, parts, T, s, corner_c=ACC)}</g>\n'
    p = g["params"]
    X, Y = p["winder_x"], p["winder_y"]
    # X and Y down the newel face that meets flight 1 (flight 1 runs along Y)
    fx = T(icx, 0)[0]
    y0, y1, y2 = T(0, icy)[1], T(0, icy - sy * X)[1], T(0, icy - sy * (X + Y))[1]
    dx = fx + sx * 36
    for yy in (y0, y1, y2):
        body += _proj(fx + sx * 4, yy, dx + sx * 4, yy)
    body += _ticked(dx, y0, dx, y1, True) + _ticked(dx, y1, dx, y2, True)
    anchor = "start" if sx > 0 else "end"
    body += _text(dx + sx * 9, (y0 + y1) / 2 + 6, f"X {_mm(X)}", 18, ACC_T, bold=True, anchor=anchor)
    body += _text(dx + sx * 9, (y1 + y2) / 2 + 12, f"Y {_mm(Y)}", 18, ACC_T, bold=True, anchor=anchor)
    # flight labels where each flight leaves the crop window
    for k, label in ((1, "flight 1"), (2 if winder_turns[0] == 1 else 3, f"flight {2 if winder_turns[0] == 1 else 3}")):
        ts = [e for e in g["elements"] if e["flight"] == k]
        if not ts:
            continue
        clip = box(*win)
        inside = [e for e in ts if e["poly"].intersects(clip)]
        if not inside:
            continue
        from shapely.ops import unary_union
        visible = unary_union([e["poly"] for e in inside]).intersection(clip)
        c = visible.centroid
        tx, ty = T(c.x, c.y)
        body += _text(tx, ty + 5, label, 15, DIM)
    return _svg(body, (0, 0, W, H))


# ── Dispatch ───────────────────────────────────────────────────────

_DIAGRAM_FUNCTIONS = {
    "step0_stair_type": step0_stair_type,
    "step1_height": step1_height,
    "step2_risers_going": step2_risers_going,
    "step3_treads_risers": step3_treads_risers,
    "step4_width_sides": step4_width_sides,
    "step5_corners": step5_corners,
    "step6_winder_setout": step6_winder_setout,
}


def available_diagrams():
    return list(_DIAGRAM_FUNCTIONS)


def get_diagram(step_id, params):
    fn = _DIAGRAM_FUNCTIONS.get(step_id)
    return fn(params) if fn else ""
