"""
DXF Plan View Generator — solid-occlusion approach.

Generates a DXF R12 (AC1009) plan view that shows what you would see looking
straight down at a SOLID staircase — not a wireframe.

Algorithm
---------
1. Each tread, newel post, and stringer is converted to a 2D polygon (XY at Z=0)
   together with its top-Z height.
2. Polygons are processed from HIGHEST Z to LOWEST (top of stair first).
3. A running *coverage* polygon accumulates the opaque area already drawn.
   For each shape its boundary segments are clipped against the coverage so
   that only the portions visible from above survive.
4. Only those surviving LINE segments are emitted into the DXF on the
   STAIR_TREADS layer with continuous linetype.

No dashed lines, no risers, no hidden detail.

Public entry points
-------------------
    meshes_to_dxf_string(meshes, params) -> str   # DXF file content
    meshes_to_dxf(meshes, params) -> str           # path to temp DXF file
"""

import math
import re
import tempfile
from shapely.geometry import Polygon, LineString, box as shapely_box
from shapely.ops import unary_union


# ── Layer definitions ────────────────────────────────────────────
LAYERS = {
    "STAIR_TREADS": {"color": 7, "linetype": "CONTINUOUS"},
    "STAIR_RISERS": {"color": 8, "linetype": "DASHED"},
    "ELEVATION":     {"color": 7, "linetype": "CONTINUOUS"},
    "HIDDEN":        {"color": 8, "linetype": "DASHED"},
    "SECTION_CUT":   {"color": 7, "linetype": "CONTINUOUS"},
    "SECTION_BEYOND":{"color": 8, "linetype": "CONTINUOUS"},
    "FLOOR_LINE":    {"color": 8, "linetype": "CONTINUOUS"},
    "DIMENSIONS":    {"color": 7, "linetype": "CONTINUOUS"},
}

# IFC types that participate in solid-occlusion (not risers).
_SOLID_IFC_TYPES_EXCLUDED = frozenset({"riser", "winder_riser"})

# IFC types whose front/back faces are drawn as dashed hidden lines.
_RISER_IFC_TYPES = frozenset({"riser", "winder_riser"})

# Segments shorter than this (mm) are discarded (floating-point noise).
_MIN_LENGTH = 0.01


# ── Minimal DXF R12 writer ──────────────────────────────────────

class _DxfWriter:
    """Builds a DXF R12 (AC1009) string from LINE entities.

    R12 is the simplest DXF format — no handles, no ownership, no BLOCKS
    or OBJECTS sections required.  Universally compatible.
    """

    def __init__(self):
        self._entities = []
        self._texts = []
        self._layers = {}
        self._linetypes = {}

    def add_linetype(self, name, pattern):
        self._linetypes[name] = pattern

    def add_layer(self, name, color=7, linetype="CONTINUOUS"):
        self._layers[name] = {"color": color, "linetype": linetype}

    def add_line(self, start, end, layer="0"):
        self._entities.append((start, end, layer))

    def add_text(self, text, position, height=5.0, layer="0"):
        self._texts.append((text, position, height, layer))

    # ── serialisation ──

    def to_string(self):
        lines = []
        a = lines.append

        # HEADER
        a("  0"); a("SECTION")
        a("  2"); a("HEADER")
        a("  9"); a("$ACADVER")
        a("  1"); a("AC1009")
        a("  9"); a("$MEASUREMENT")
        a(" 70"); a("     1")
        a("  0"); a("ENDSEC")

        # TABLES
        a("  0"); a("SECTION")
        a("  2"); a("TABLES")

        # LTYPE table
        a("  0"); a("TABLE")
        a("  2"); a("LTYPE")
        a(" 70"); a("     %d" % (len(self._linetypes) + 1))
        # CONTINUOUS (always present)
        a("  0"); a("LTYPE")
        a("  2"); a("CONTINUOUS")
        a(" 70"); a("     0")
        a("  3"); a("Solid line")
        a(" 72"); a("    65")
        a(" 73"); a("     0")
        a(" 40"); a("0.0")
        # Custom linetypes
        for lt_name, pattern in self._linetypes.items():
            a("  0"); a("LTYPE")
            a("  2"); a(lt_name)
            a(" 70"); a("     0")
            a("  3"); a("")
            a(" 72"); a("    65")
            a(" 73"); a("     %d" % (len(pattern) - 1))
            a(" 40"); a("%.4f" % pattern[0])
            for val in pattern[1:]:
                a(" 49"); a("%.4f" % val)
        a("  0"); a("ENDTAB")

        # LAYER table
        a("  0"); a("TABLE")
        a("  2"); a("LAYER")
        a(" 70"); a("     %d" % (len(self._layers) + 1))
        # Default layer 0
        a("  0"); a("LAYER")
        a("  2"); a("0")
        a(" 70"); a("     0")
        a(" 62"); a("     7")
        a("  6"); a("CONTINUOUS")
        for lname, lprops in self._layers.items():
            a("  0"); a("LAYER")
            a("  2"); a(lname)
            a(" 70"); a("     0")
            a(" 62"); a("     %d" % lprops["color"])
            a("  6"); a(lprops["linetype"])
        a("  0"); a("ENDTAB")

        a("  0"); a("ENDSEC")

        # ENTITIES
        a("  0"); a("SECTION")
        a("  2"); a("ENTITIES")
        for start, end, layer in self._entities:
            a("  0"); a("LINE")
            a("  8"); a(layer)
            a(" 10"); a("%.6f" % start[0])
            a(" 20"); a("%.6f" % start[1])
            a(" 30"); a("0.0")
            a(" 11"); a("%.6f" % end[0])
            a(" 21"); a("%.6f" % end[1])
            a(" 31"); a("0.0")
        for text, pos, height, tlayer in self._texts:
            a("  0"); a("TEXT")
            a("  8"); a(tlayer)
            a(" 10"); a("%.6f" % pos[0])
            a(" 20"); a("%.6f" % pos[1])
            a(" 30"); a("0.0")
            a(" 40"); a("%.6f" % height)
            a("  1"); a(text.replace("\n", " "))
        a("  0"); a("ENDSEC")

        # EOF
        a("  0"); a("EOF")
        return "\r\n".join(lines) + "\r\n"


# ── Geometry helpers ─────────────────────────────────────────────

def _mesh_to_poly_and_z(mesh):
    """Return *(Polygon, top_z)* for *mesh*, or *(None, None)*.

    The polygon is the 2D XY footprint; top_z is the highest Z coordinate
    (used to sort elements from top to bottom).
    """
    mtype = mesh.get("type", "")

    if mtype == "box":
        center = mesh.get("ifc_center")
        size = mesh.get("ifc_size")
        if not center or not size:
            return None, None
        cx, cy, cz = center
        sx, sy, sz = size
        hx, hy = sx / 2.0, sy / 2.0
        coords = [
            (cx - hx, cy - hy),
            (cx + hx, cy - hy),
            (cx + hx, cy + hy),
            (cx - hx, cy + hy),
        ]
        return Polygon(coords), cz + sz / 2.0

    if mtype == "winder_polygon":
        profile = mesh.get("profile")
        if not profile or len(profile) < 3:
            return None, None
        coords = [(p[0], p[1]) for p in profile]
        z = mesh.get("z", 0)
        thickness = mesh.get("thickness", 0)
        return Polygon(coords), z + thickness

    if mtype == "stringer":
        profile = mesh.get("profile")
        thickness = mesh.get("thickness", 0)
        if not profile or thickness == 0:
            return None, None
        axis = mesh.get("axis")
        if axis == "y":
            xs = [p[0] for p in profile]
            y0 = mesh.get("y", 0)
            coords = [
                (min(xs), y0),
                (max(xs), y0),
                (max(xs), y0 + thickness),
                (min(xs), y0 + thickness),
            ]
        else:
            ys = [p[0] for p in profile]
            x0 = mesh.get("x", 0)
            coords = [
                (x0, min(ys)),
                (x0 + thickness, min(ys)),
                (x0 + thickness, max(ys)),
                (x0, max(ys)),
            ]
        top_z = max(p[1] for p in profile)
        return Polygon(coords), top_z

    return None, None


def _riser_front_back(mesh):
    """Return the front and back face lines of a riser as ((x1,y1),(x2,y2)) pairs.

    Box risers project to a rectangle in plan; the front and back faces are
    the two width-spanning (long) edges.  Flight orientation is detected by
    comparing sx vs sy — the thin dimension is the riser thickness.
    Winder-polygon risers have 4 vertices [inner_back, outer_back,
    outer_front, inner_front]; front = edge 2→3, back = edge 0→1.
    """
    mtype = mesh.get("type", "")
    if mtype == "box":
        center = mesh.get("ifc_center")
        size = mesh.get("ifc_size")
        if not center or not size:
            return []
        cx, cy, cz = center
        sx, sy, sz = size
        hx, hy = sx / 2.0, sy / 2.0
        if sx >= sy:
            # Riser spans X (flight travels along Y) — horizontal lines.
            front = ((cx - hx, cy - hy), (cx + hx, cy - hy))
            back = ((cx - hx, cy + hy), (cx + hx, cy + hy))
        else:
            # Riser spans Y (flight travels along X) — vertical lines.
            front = ((cx - hx, cy - hy), (cx - hx, cy + hy))
            back = ((cx + hx, cy - hy), (cx + hx, cy + hy))
        return [front, back]
    if mtype == "winder_polygon":
        profile = mesh.get("profile")
        if not profile or len(profile) < 4:
            return []
        pts = [(p[0], p[1]) for p in profile]
        back = (pts[0], pts[1])
        front = (pts[2], pts[3])
        return [front, back]
    return []


def _collect_points(geom):
    """Recursively extract (x, y) tuples from a Shapely geometry."""
    pts = []
    gt = geom.geom_type
    if gt == "Point":
        pts.append((geom.x, geom.y))
    elif gt == "MultiPoint":
        for pt in geom.geoms:
            pts.append((pt.x, pt.y))
    elif gt == "LineString":
        for c in geom.coords:
            pts.append((c[0], c[1]))
    elif gt in ("MultiLineString", "GeometryCollection"):
        for g in geom.geoms:
            pts.extend(_collect_points(g))
    return pts


def _build_trim_boundaries(meshes):
    """Build separate outline geometries for stringers, handrails, and newels.

    Returns ``{ifc_type: boundary_geometry}`` where *boundary_geometry* is
    the union of polygon outlines for that element type.
    """
    groups = {"stringer": [], "handrail": [], "newel": []}
    for mesh in meshes:
        ifc_type = mesh.get("ifc_type", "")
        if ifc_type not in groups:
            continue
        poly, _ = _mesh_to_poly_and_z(mesh)
        if poly is None or not poly.is_valid or poly.is_empty:
            continue
        groups[ifc_type].append(poly.exterior)

    boundaries = {}
    for key, outlines in groups.items():
        if outlines:
            boundaries[key] = unary_union(outlines)
    return boundaries


def _project_intersections(extended, boundary, mid_x, mid_y, nx, ny):
    """Return list of (projection, x, y) for all intersection points."""
    hits = extended.intersection(boundary)
    if hits.is_empty:
        return []
    points = _collect_points(hits)
    result = []
    for px, py in points:
        proj = (px - mid_x) * nx + (py - mid_y) * ny
        result.append((proj, px, py))
    return result


def _pick_trim_for_end(crossings, is_start, half_len):
    """Pick the trim point for one end of a riser line.

    Finds the **innermost** (closest-to-center) crossing from ANY
    boundary type within range.  This automatically selects the correct
    element for each side condition:

    * **Balustrade straight flight** — the handrail inner edge is closer
      to center than the stringer, so it wins.
    * **Balustrade at winder turn** — the newel-post face is closer to
      center than any stray handrail from an adjacent flight, so it wins.
    * **Wall side** — only the stringer is present, so it wins by default.

    *half_len* is half the riser length (= original endpoint projection).
    A 150 mm cap prevents picking up boundary elements from adjacent
    flights at turn areas.
    """
    max_dist = 150  # mm beyond original endpoint to search
    best = None

    for btype in ("handrail", "newel", "stringer"):
        if btype not in crossings:
            continue
        pts = crossings[btype]
        if is_start:
            lo = -half_len - max_dist
            candidates = [p for p in pts if lo < p[0] < -_MIN_LENGTH]
            if candidates:
                innermost = max(candidates, key=lambda p: p[0])
                if best is None or innermost[0] > best[0]:
                    best = innermost
        else:
            hi = half_len + max_dist
            candidates = [p for p in pts if _MIN_LENGTH < p[0] < hi]
            if candidates:
                innermost = min(candidates, key=lambda p: p[0])
                if best is None or innermost[0] < best[0]:
                    best = innermost

    return best


def _trim_riser_line(start, end, boundaries):
    """Trim a riser line to the correct boundary on each side.

    Each end is evaluated independently:

    * **Wall side** (only a stringer is present) → trims to the stringer
      inner face.
    * **Balustrade straight flight** (handrail present) → trims to the
      handrail inner edge.
    * **Balustrade at winder turn** (newel present, no handrail) → trims
      to the nearest newel-post face.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = (dx ** 2 + dy ** 2) ** 0.5
    if length < _MIN_LENGTH:
        return None
    nx, ny = dx / length, dy / length
    mid_x = (start[0] + end[0]) / 2.0
    mid_y = (start[1] + end[1]) / 2.0

    ext_start = (mid_x - nx * 50000, mid_y - ny * 50000)
    ext_end = (mid_x + nx * 50000, mid_y + ny * 50000)
    extended = LineString([ext_start, ext_end])

    # Get projected intersections for each boundary type.
    crossings = {}
    for btype, boundary in boundaries.items():
        pts = _project_intersections(extended, boundary,
                                     mid_x, mid_y, nx, ny)
        if pts:
            crossings[btype] = pts

    # Trim each end independently.
    half_len = length / 2.0
    new_start = _pick_trim_for_end(crossings, is_start=True, half_len=half_len)
    new_end = _pick_trim_for_end(crossings, is_start=False, half_len=half_len)

    ts = (new_start[1], new_start[2]) if new_start else start
    te = (new_end[1], new_end[2]) if new_end else end

    return (ts, te)


def _emit_geometry(dxf, geom, layer):
    """Draw a shapely geometry as DXF LINE entities.

    Handles LineString, MultiLineString, and GeometryCollection.
    """
    if geom.is_empty:
        return
    gt = geom.geom_type
    if gt == "LineString":
        coords = list(geom.coords)
        for i in range(len(coords) - 1):
            dxf.add_line(coords[i][:2], coords[i + 1][:2], layer=layer)
    elif gt in ("MultiLineString", "GeometryCollection"):
        for g in geom.geoms:
            _emit_geometry(dxf, g, layer)


# ── Elevation & Section helpers ──────────────────────────────────

_STRINGER_IFC = frozenset({"stringer"})
_TREAD_RISER_IFC = frozenset({"tread", "winder_tread", "riser", "winder_riser"})


def _project_point(x, y, z, view):
    """Project IFC coords (X-right, Y-forward, Z-up) → (view_x, view_y, depth).

    Depth convention: smaller depth = closer to viewer.
    """
    if view == "front":  return (x, z, y)
    if view == "right":  return (y, z, -x)
    if view == "back":   return (-x, z, -y)
    if view == "left":   return (-y, z, x)
    return (x, z, y)


# Every preview mesh is an axis-aligned prism: a 2D profile polygon
# extruded along one world axis.  All elevation/section logic works on
# this single representation instead of per-mesh-type special cases.
#
#   prism = {"axis": 'x'|'y'|'z',   extrusion axis
#            "poly": Polygon,        profile in the two other coords
#            "lo": float, "hi":      extrusion interval along axis
#            "ifc_type": str,
#            "is_rect": bool}        True → profile is an axis-aligned rect
#
# Profile coordinate order per axis (matches the mesh dict conventions):
_PROFILE_AXES = {"x": ("y", "z"), "y": ("x", "z"), "z": ("x", "y")}

# view → (vx world axis, vx sign, depth world axis, depth sign).
# Mirrors _project_point; vy is always +z.
_VIEW_INFO = {
    "front": ("x", 1.0, "y", 1.0),
    "right": ("y", 1.0, "x", -1.0),
    "back":  ("x", -1.0, "y", -1.0),
    "left":  ("y", -1.0, "x", 1.0),
}

# Two surfaces within this depth (mm) of each other do not occlude one
# another (prevents coplanar faces from hiding their own edges).
_DEPTH_TOL = 0.5


def _world_point(axis, u, w, a):
    """Map profile coords *(u, w)* + extrusion coord *a* to world (x, y, z)."""
    if axis == "z":
        return (u, w, a)
    if axis == "y":
        return (u, a, w)
    return (a, u, w)


def _iter_polygons(geom):
    """Yield all Polygon parts of a shapely geometry."""
    if geom.is_empty:
        return
    if geom.geom_type == "Polygon":
        yield geom
    elif geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        for g in geom.geoms:
            yield from _iter_polygons(g)


def _iter_linestrings(geom):
    """Yield all LineString parts of a shapely geometry."""
    if geom.is_empty:
        return
    if geom.geom_type == "LineString":
        yield geom
    elif geom.geom_type in ("MultiLineString", "GeometryCollection"):
        for g in geom.geoms:
            yield from _iter_linestrings(g)


def _as_prisms(mesh):
    """Convert a preview mesh dict to a list of prisms (usually one)."""
    mtype = mesh.get("type", "")
    ifc = mesh.get("ifc_type", "")
    try:
        if mtype == "box":
            c = mesh.get("ifc_center")
            s = mesh.get("ifc_size")
            if not c or not s:
                return []
            poly = shapely_box(c[0] - s[0] / 2, c[1] - s[1] / 2,
                               c[0] + s[0] / 2, c[1] + s[1] / 2)
            return [{"axis": "z", "poly": poly,
                     "lo": c[2] - s[2] / 2, "hi": c[2] + s[2] / 2,
                     "ifc_type": ifc, "is_rect": True}]

        if mtype == "stringer":
            profile = mesh.get("profile")
            thickness = mesh.get("thickness", 0)
            if not profile or len(profile) < 3 or thickness == 0:
                return []
            axis = "y" if mesh.get("axis") == "y" else "x"
            lo = mesh.get(axis, 0)
            poly = Polygon([(p[0], p[1]) for p in profile])
        elif mtype == "winder_polygon":
            profile = mesh.get("profile")
            if not profile or len(profile) < 3:
                return []
            axis = "z"
            lo = mesh.get("z", 0)
            thickness = mesh.get("thickness", 0)
            poly = Polygon([(p[0], p[1]) for p in profile])
        else:
            return []

        if not poly.is_valid:
            poly = poly.buffer(0)
        return [{"axis": axis, "poly": g, "lo": lo, "hi": lo + thickness,
                 "ifc_type": ifc, "is_rect": False}
                for g in _iter_polygons(poly)]
    except Exception:
        return []


def _profile_depth_fn(poly, isec, sec_from_vy, sec_sign, idep, d_sign):
    """Depth function for a prism whose depth varies across its silhouette.

    At a view point, the world coordinate ``(vy if sec_from_vy else vx) *
    sec_sign`` selects a 1D section through the profile polygon (taken on
    profile coord *isec*); the nearest depth there is the minimum of
    ``d_sign * coord[idep]`` over that section.
    """
    b = poly.bounds
    dlo, dhi = (b[0], b[2]) if idep == 0 else (b[1], b[3])
    near_global = min(d_sign * dlo, d_sign * dhi)

    def depth_fn(vx, vy):
        coord = (vy if sec_from_vy else vx) * sec_sign
        if isec == 0:
            line = LineString([(coord, b[1] - 10), (coord, b[3] + 10)])
        else:
            line = LineString([(b[0] - 10, coord), (b[2] + 10, coord)])
        try:
            inter = poly.intersection(line)
        except Exception:
            return near_global
        pts = _collect_points(inter)
        if not pts:
            return near_global
        return min(d_sign * p[idep] for p in pts)

    return depth_fn


def _prism_silhouette(prism, view):
    """Return *(silhouette Polygon in view coords, depth_fn)* or (None, None).

    The silhouette is exact for an axis-aligned prism in an axis-aligned
    orthographic view; *depth_fn(vx, vy)* gives the prism's nearest depth
    at a 2D view point (smaller = closer to the viewer).
    """
    vx_axis, vx_sign, d_axis, d_sign = _VIEW_INFO[view]
    axis = prism["axis"]
    poly = prism["poly"]
    lo, hi = prism["lo"], prism["hi"]
    b = poly.bounds

    try:
        if axis == "z":
            # Vertical prism: vy spans [lo, hi]; vx is one profile coord.
            u_axis, _w = _PROFILE_AXES[axis]
            iu = 0 if u_axis == vx_axis else 1
            idd = 1 - iu
            umin, umax = (b[0], b[2]) if iu == 0 else (b[1], b[3])
            vx0, vx1 = sorted((vx_sign * umin, vx_sign * umax))
            if vx1 - vx0 < _MIN_LENGTH or hi - lo < _MIN_LENGTH:
                return None, None
            sil = shapely_box(vx0, lo, vx1, hi)
            if prism.get("is_rect"):
                dlo, dhi = (b[0], b[2]) if idd == 0 else (b[1], b[3])
                near = min(d_sign * dlo, d_sign * dhi)
                return sil, (lambda vx, vy, _n=near: _n)
            return sil, _profile_depth_fn(poly, iu, False, vx_sign,
                                          idd, d_sign)

        if axis == d_axis:
            # Extruded along the view direction → silhouette is the profile
            # itself (profile coords are (horizontal, z)).
            pts = [(vx_sign * u, w) for u, w in poly.exterior.coords]
            sil = Polygon(pts)
            if not sil.is_valid:
                sil = sil.buffer(0)
            polys = list(_iter_polygons(sil))
            if not polys:
                return None, None
            sil = max(polys, key=lambda g: g.area)
            near = min(d_sign * lo, d_sign * hi)
            return sil, (lambda vx, vy, _n=near: _n)

        # axis == vx_axis: extruded across the view → bounding rectangle;
        # depth varies with vy (= the profile's second coord).
        vx0, vx1 = sorted((vx_sign * lo, vx_sign * hi))
        if vx1 - vx0 < _MIN_LENGTH or b[3] - b[1] < _MIN_LENGTH:
            return None, None
        sil = shapely_box(vx0, b[1], vx1, b[3])
        return sil, _profile_depth_fn(poly, 1, True, 1.0, 0, d_sign)
    except Exception:
        return None, None


def _compute_view_bounds(meshes, view):
    """Return *(min_vx, min_vy, max_vx, max_vy)* bounding box in view coords."""
    xs, ys = [], []
    for mesh in meshes:
        for prism in _as_prisms(mesh):
            sil, _d = _prism_silhouette(prism, view)
            if sil is None:
                continue
            b = sil.bounds
            xs.extend([b[0], b[2]])
            ys.extend([b[1], b[3]])
    if not xs:
        return (0, 0, 0, 0)
    return (min(xs), min(ys), max(xs), max(ys))


# ── Depth-aware hidden-line occlusion ────────────────────────────
#
# Each drawn segment is tracked as parameter intervals [(t0, t1)] along
# its own straight line, and an occluder removes an interval only where
# it is genuinely IN FRONT of the segment's owner at that point.  This
# replaces global painter's-algorithm sorting, which fails whenever
# depth ranges overlap (winders vs. diagonal stringers, newels vs.
# winder treads, ...).  Interval arithmetic also avoids the repeated
# shapely line differences that triggered GEOS TopologyException in
# Pyodide/WASM.

def _geom_param_intervals(a, b, geom, seg_len):
    """Parameter intervals of segment *a*→*b* covered by line parts of *geom*."""
    if seg_len < _MIN_LENGTH:
        return []
    abx = b[0] - a[0]
    aby = b[1] - a[1]
    inv_len2 = 1.0 / (seg_len * seg_len)
    out = []
    for ls in _iter_linestrings(geom):
        coords = list(ls.coords)
        ts = [((c[0] - a[0]) * abx + (c[1] - a[1]) * aby) * inv_len2
              for c in coords]
        t0 = max(0.0, min(ts))
        t1 = min(1.0, max(ts))
        if t1 - t0 > _MIN_LENGTH / seg_len:
            out.append((t0, t1))
    return out


def _subtract_intervals(base, cuts):
    """Subtract *cuts* intervals from *base* intervals (both [(t0, t1)])."""
    out = []
    for b0, b1 in base:
        pieces = [(b0, b1)]
        for c0, c1 in cuts:
            nxt = []
            for s0, s1 in pieces:
                if c1 <= s0 or c0 >= s1:
                    nxt.append((s0, s1))
                    continue
                if c0 > s0:
                    nxt.append((s0, c0))
                if c1 < s1:
                    nxt.append((c1, s1))
            pieces = nxt
        out.extend(pieces)
    return [iv for iv in out if iv[1] - iv[0] > 1e-9]


def _visible_intervals(a, b, own_depth_fn, occluders):
    """Visible parameter intervals of segment *a*→*b* against *occluders*.

    *occluders* is a list of ``(silhouette Polygon, depth_fn)``.  A part of
    the segment is hidden only where an occluder's depth at that point is
    smaller (closer) than the owner's by more than ``_DEPTH_TOL``.
    """
    seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
    if seg_len < _MIN_LENGTH:
        return []
    seg = LineString([a, b])
    sb = seg.bounds
    vis = [(0.0, 1.0)]
    for poly, dfn in occluders:
        if not vis:
            break
        pb = poly.bounds
        if pb[0] > sb[2] or pb[2] < sb[0] or pb[1] > sb[3] or pb[3] < sb[1]:
            continue
        try:
            inter = poly.intersection(seg)
        except Exception:
            continue
        cuts = []
        for t0, t1 in _geom_param_intervals(a, b, inter, seg_len):
            tm = (t0 + t1) / 2.0
            mx = a[0] + (b[0] - a[0]) * tm
            my = a[1] + (b[1] - a[1]) * tm
            if dfn(mx, my) < own_depth_fn(mx, my) - _DEPTH_TOL:
                cuts.append((t0, t1))
        if cuts:
            vis = _subtract_intervals(vis, cuts)
    return vis


def _emit_intervals(dxf, a, b, intervals, layer, ox, oy):
    """Draw parameter intervals of segment *a*→*b* as DXF lines."""
    seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
    for t0, t1 in intervals:
        if (t1 - t0) * seg_len < _MIN_LENGTH:
            continue
        p = (a[0] + (b[0] - a[0]) * t0 + ox, a[1] + (b[1] - a[1]) * t0 + oy)
        q = (a[0] + (b[0] - a[0]) * t1 + ox, a[1] + (b[1] - a[1]) * t1 + oy)
        dxf.add_line(p, q, layer=layer)


def _draw_dim_line(dxf, p1, p2, offset, layer="DIMENSIONS", label=None, norm=None):
    """Draw a simple linear dimension between *p1* and *p2*.

    *offset* — perpendicular distance from the geometry (always positive).
    *norm*   — explicit (nx, ny) unit normal for the offset direction.
               If not given, a perpendicular is computed (may point inward).
    Draws extension lines, a dimension line with ticks, and a centred text label.
    If *label* is given it replaces the default numeric text.
    """
    import math
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return
    # Unit normal perpendicular to the dimension direction
    if norm:
        nx, ny = norm
    else:
        nx = -dy / length
        ny = dx / length
    abs_offset = abs(offset)
    # Dimension line endpoints (offset from geometry along the normal)
    d1 = (p1[0] + nx * abs_offset, p1[1] + ny * abs_offset)
    d2 = (p2[0] + nx * abs_offset, p2[1] + ny * abs_offset)
    # Extension lines (from geometry to just past dimension line)
    ext_gap = 30.0  # gap between geometry and extension line start
    ext_over = 50.0  # overshoot past dimension line
    e1_start = (p1[0] + nx * ext_gap, p1[1] + ny * ext_gap)
    e1_end = (p1[0] + nx * (abs_offset + ext_over), p1[1] + ny * (abs_offset + ext_over))
    e2_start = (p2[0] + nx * ext_gap, p2[1] + ny * ext_gap)
    e2_end = (p2[0] + nx * (abs_offset + ext_over), p2[1] + ny * (abs_offset + ext_over))
    dxf.add_line(e1_start, e1_end, layer=layer)
    dxf.add_line(e2_start, e2_end, layer=layer)
    # Dimension line
    dxf.add_line(d1, d2, layer=layer)
    # Tick marks (small 45° slashes)
    tick = 40.0
    tdx = (dx / length) * tick * 0.5
    tdy = (dy / length) * tick * 0.5
    tnx = nx * tick * 0.5
    tny = ny * tick * 0.5
    dxf.add_line((d1[0] - tdx - tnx, d1[1] - tdy - tny),
                 (d1[0] + tdx + tnx, d1[1] + tdy + tny), layer=layer)
    dxf.add_line((d2[0] - tdx - tnx, d2[1] - tdy - tny),
                 (d2[0] + tdx + tnx, d2[1] + tdy + tny), layer=layer)
    # Text label centred on dimension line
    text = label if label is not None else "%.0f" % length
    text = text.replace("\n", " ")
    mid = ((d1[0] + d2[0]) / 2 + nx * 30, (d1[1] + d2[1]) / 2 + ny * 30)
    dxf.add_text(text, mid, height=50.0, layer=layer)


def _draw_floor_line(dxf, vb, ox, oy, extension=500.0):
    """Draw a horizontal floor-level line at Z=0 (view_y=0) with extensions.

    *vb* is the view bounds (min_vx, min_vy, max_vx, max_vy).
    The line extends *extension* mm beyond the geometry on both sides.
    Z=0 in IFC projects to view_y=0 in all elevation/section views.
    """
    floor_vy = 0.0  # Z=0 in all orthographic views
    x_left = vb[0] - extension
    x_right = vb[2] + extension
    dxf.add_line((x_left + ox, floor_vy + oy),
                 (x_right + ox, floor_vy + oy),
                 layer="FLOOR_LINE")


def _draw_elevation(dxf, meshes, view, ox, oy):
    """Draw one orthographic elevation with depth-aware hidden-line removal.

    Visible edges → ELEVATION layer (white).
    Tread/riser edges hidden *only* by stringers → HIDDEN layer (dashed grey).
    """
    items = []
    for mesh in meshes:
        for prism in _as_prisms(mesh):
            sil, dfn = _prism_silhouette(prism, view)
            if sil is None or sil.is_empty or not sil.is_valid:
                continue
            ifc = prism["ifc_type"]
            items.append({"sil": sil, "depth": dfn,
                          "is_str": ifc in _STRINGER_IFC,
                          "is_tr": ifc in _TREAD_RISER_IFC})

    for it in items:
        occl_all = [(o["sil"], o["depth"]) for o in items if o is not it]
        occl_nostr = [(o["sil"], o["depth"]) for o in items
                      if o is not it and not o["is_str"]]
        exterior = list(it["sil"].exterior.coords)
        for i in range(len(exterior) - 1):
            a, b = exterior[i], exterior[i + 1]
            vis_all = _visible_intervals(a, b, it["depth"], occl_all)
            _emit_intervals(dxf, a, b, vis_all, "ELEVATION", ox, oy)
            if it["is_tr"]:
                # Parts hidden only by stringers → dashed grey.
                vis_nostr = _visible_intervals(a, b, it["depth"], occl_nostr)
                hidden = _subtract_intervals(vis_nostr, vis_all)
                _emit_intervals(dxf, a, b, hidden, "HIDDEN", ox, oy)


# ── Section helpers ──────────────────────────────────────────────

_BIG = 1e7  # half-plane extent for clipping


def _clip_prism(prism, cut_axis, cut_pos, keep_positive):
    """Clip *prism* to one side of the axis-aligned vertical cut plane.

    Returns a list of prisms: empty if nothing remains, several if the cut
    splits the profile into pieces (all pieces are kept — discarding the
    smaller ones loses geometry, e.g. kite-shaped winder treads).
    """
    TOL = 1.0  # mm
    axis = prism["axis"]
    try:
        if cut_axis == axis:
            # Cut along the extrusion axis — clamp the interval.
            lo, hi = prism["lo"], prism["hi"]
            if keep_positive:
                lo = max(lo, cut_pos)
            else:
                hi = min(hi, cut_pos)
            if hi - lo < TOL:
                return []
            out = dict(prism)
            out["lo"] = lo
            out["hi"] = hi
            return [out]

        # Cut crosses the profile plane — half-plane intersection.
        u_axis, _w = _PROFILE_AXES[axis]
        idx = 0 if cut_axis == u_axis else 1
        if idx == 0:
            rect = shapely_box(cut_pos, -_BIG, _BIG, _BIG) if keep_positive \
                else shapely_box(-_BIG, -_BIG, cut_pos, _BIG)
        else:
            rect = shapely_box(-_BIG, cut_pos, _BIG, _BIG) if keep_positive \
                else shapely_box(-_BIG, -_BIG, _BIG, cut_pos)
        clipped = prism["poly"].intersection(rect)
        out = []
        for g in _iter_polygons(clipped):
            if g.area < TOL:
                continue
            p = dict(prism)
            p["poly"] = g
            out.append(p)
        return out
    except Exception:
        return []


def _identify_flights(meshes):
    """Return list of ``{flight, cut_axis, cut_pos, direction}`` dicts."""
    flights = {}
    for mesh in meshes:
        ifc_type = mesh.get("ifc_type", "")
        if ifc_type not in ("tread", "winder_tread"):
            continue
        m = re.search(r"[Ff]light\s*(\d+)", mesh.get("name", ""))
        if not m:
            continue
        fnum = int(m.group(1))
        flights.setdefault(fnum, []).append(mesh)

    result = []
    for fnum in sorted(flights):
        centers = []
        for t in flights[fnum]:
            if t.get("type") == "box":
                c = t.get("ifc_center")
                if c:
                    centers.append(c)
            elif t.get("type") == "winder_polygon":
                fp = t.get("profile", [])
                if fp:
                    cx = sum(p[0] for p in fp) / len(fp)
                    cy = sum(p[1] for p in fp) / len(fp)
                    centers.append((cx, cy, t.get("z", 0)))
        if len(centers) < 1:
            continue
        xs = [c[0] for c in centers]
        ys = [c[1] for c in centers]
        if len(centers) >= 2:
            # Determine direction from spread of tread centres
            if (max(ys) - min(ys)) > (max(xs) - min(xs)):
                result.append({"flight": fnum, "cut_axis": "x",
                               "cut_pos": sum(xs) / len(xs), "direction": "y"})
            else:
                result.append({"flight": fnum, "cut_axis": "y",
                               "cut_pos": sum(ys) / len(ys), "direction": "x"})
        else:
            # Single tread — infer direction from tread box dimensions
            t = flights[fnum][0]
            s = t.get("ifc_size")
            if s and s[1] > s[0]:
                # Tread is longer in Y → it spans across, flight runs along X
                result.append({"flight": fnum, "cut_axis": "y",
                               "cut_pos": ys[0], "direction": "x"})
            else:
                # Tread is longer in X → it spans across, flight runs along Y
                result.append({"flight": fnum, "cut_axis": "x",
                               "cut_pos": xs[0], "direction": "y"})
    return result


def _prism_cut_profiles(prism, cut_axis, cut_pos, view):
    """Return Polygons (view coords) where the cut plane slices *prism*.

    One polygon per chord when the plane crosses the profile (a concave
    profile can be entered/exited more than once), or the projected
    profile itself when the plane is perpendicular to the extrusion axis.
    """
    TOL = 1.0  # mm tolerance
    axis = prism["axis"]
    poly = prism["poly"]
    lo, hi = prism["lo"], prism["hi"]

    try:
        if cut_axis == axis:
            # Plane perpendicular to extrusion → cross-section is the profile.
            if not (lo - TOL <= cut_pos <= hi + TOL):
                return []
            pts = [_world_point(axis, u, w, cut_pos)
                   for u, w in poly.exterior.coords]
            p2 = Polygon([_project_point(*p, view)[:2] for p in pts])
            if not p2.is_valid:
                p2 = p2.buffer(0)
            return list(_iter_polygons(p2))

        # Plane crosses the profile plane — slice the profile polygon.
        u_axis, _w = _PROFILE_AXES[axis]
        idx = 0 if cut_axis == u_axis else 1
        b = poly.bounds
        if idx == 0:
            cut_line = LineString([(cut_pos, b[1] - 100), (cut_pos, b[3] + 100)])
        else:
            cut_line = LineString([(b[0] - 100, cut_pos), (b[2] + 100, cut_pos)])
        inter = poly.intersection(cut_line)
        out = []
        for chord in _iter_linestrings(inter):
            cs = list(chord.coords)
            p0, p1 = cs[0], cs[-1]
            if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) < _MIN_LENGTH:
                continue
            corners = [_world_point(axis, p0[0], p0[1], lo),
                       _world_point(axis, p1[0], p1[1], lo),
                       _world_point(axis, p1[0], p1[1], hi),
                       _world_point(axis, p0[0], p0[1], hi)]
            cp = Polygon([_project_point(*p, view)[:2] for p in corners])
            if cp.is_valid and not cp.is_empty:
                out.append(cp)
        return out
    except Exception:
        return []


def _section_view_for(cut_axis, look_positive):
    """Map (cut_axis, look_direction) to one of the 4 standard views."""
    if cut_axis == "x":
        return "left" if look_positive else "right"
    else:
        return "front" if look_positive else "back"


def _draw_section(dxf, meshes, cut_axis, cut_pos, look_positive, ox, oy):
    """Draw one section view at offset *(ox, oy)*.

    *cut_axis*: 'x' or 'y' — perpendicular to the cut plane.
    *cut_pos*: coordinate of the cut along *cut_axis*.
    *look_positive*: True → look toward +axis from the cut plane.
    """
    view = _section_view_for(cut_axis, look_positive)
    prisms = [p for mesh in meshes for p in _as_prisms(mesh)]

    # 1. Cut profiles (white, SECTION_CUT) — the slice through everything
    #    crossing the plane, always fully drawn.  They also seed occlusion
    #    for the beyond pass so grey lines don't duplicate the white ones.
    cut_polys = []
    for prism in prisms:
        for cpoly in _prism_cut_profiles(prism, cut_axis, cut_pos, view):
            cut_polys.append(cpoly)
            ext = list(cpoly.exterior.coords)
            for i in range(len(ext) - 1):
                dxf.add_line((ext[i][0] + ox, ext[i][1] + oy),
                             (ext[i + 1][0] + ox, ext[i + 1][1] + oy),
                             layer="SECTION_CUT")

    # 2. Beyond geometry (grey, SECTION_BEYOND): remove the half of the
    #    stair in front of the plane, project the rest, and occlude with
    #    per-point depth comparison.
    items = []
    for prism in prisms:
        for clipped in _clip_prism(prism, cut_axis, cut_pos, look_positive):
            sil, dfn = _prism_silhouette(clipped, view)
            if sil is None or sil.is_empty or not sil.is_valid:
                continue
            items.append((sil, dfn))

    # Cut profiles sit on the plane itself — in front of all beyond
    # geometry, so they occlude unconditionally.
    at_cut = -_BIG
    occl_cut = [(c, (lambda vx, vy, _d=at_cut: _d)) for c in cut_polys]

    for sil, dfn in items:
        occl = occl_cut + [(s, d) for s, d in items if s is not sil]
        exterior = list(sil.exterior.coords)
        for i in range(len(exterior) - 1):
            a, b = exterior[i], exterior[i + 1]
            vis = _visible_intervals(a, b, dfn, occl)
            _emit_intervals(dxf, a, b, vis, "SECTION_BEYOND", ox, oy)


# ── Plan dimension helpers ──────────────────────────────────────

def _flight1_front_edge(meshes, flight_dir, flight_bbox):
    """Return the front-edge coordinate of flight 1 along *flight_dir*.

    This is the outermost position of the first riser or any bottom newel
    near flight 1, whichever projects further forward.  Used to anchor
    dimension lines to the physical front of the staircase.
    """
    if not flight_bbox:
        return None
    vals = []
    # First riser of flight 1
    for m in meshes:
        if m.get("ifc_type") != "riser":
            continue
        name = m.get("name", "")
        if "F1-1" not in name:
            continue
        c = m.get("ifc_center")
        s = m.get("ifc_size")
        if c and s:
            if flight_dir == "y":
                vals.append(c[1] - s[1] / 2)
            else:
                vals.append(c[0] - s[0] / 2)
    # Bottom newels near flight 1's perpendicular range
    for m in meshes:
        if m.get("ifc_type") != "newel":
            continue
        c = m.get("ifc_center")
        s = m.get("ifc_size")
        if not c or not s:
            continue
        if flight_dir == "y":
            # Check the newel is near flight 1's X range
            nx_lo, nx_hi = c[0] - s[0] / 2, c[0] + s[0] / 2
            margin = 100
            if nx_hi < flight_bbox[0] - margin or nx_lo > flight_bbox[1] + margin:
                continue
            ny_lo = c[1] - s[1] / 2
            # Only include newels near the base (below the first tread)
            if ny_lo < flight_bbox[2] + 50:
                vals.append(ny_lo)
        else:
            ny_lo, ny_hi = c[1] - s[1] / 2, c[1] + s[1] / 2
            margin = 100
            if ny_hi < flight_bbox[2] - margin or ny_lo > flight_bbox[3] + margin:
                continue
            nx_lo = c[0] - s[0] / 2
            if nx_lo < flight_bbox[0] + 50:
                vals.append(nx_lo)
    return min(vals) if vals else None


def _stringer_extent_along(meshes, flight_dir, flight_bbox=None):
    """Return *(lo, hi)* along *flight_dir* for flight 1 stringers.

    For a Y-direction flight, return the min/max Y of the stringer profiles.
    For an X-direction flight, return the min/max X.
    Uses the same flight_bbox filter as _stringer_extent_perp.
    """
    from stair_constants import STRINGER_THICKNESS
    st = STRINGER_THICKNESS
    vals = []
    for m in meshes:
        if m.get("ifc_type") != "stringer" or m.get("type") != "stringer":
            continue
        axis = m.get("axis", "x")
        profile = m.get("profile", [])
        if flight_dir == "y" and axis != "y":
            x0 = m.get("x", 0)
            x1 = x0 + m.get("thickness", st)
            if flight_bbox:
                fb_xlo, fb_xhi = flight_bbox[0], flight_bbox[1]
                margin = st * 2
                if x1 < fb_xlo - margin or x0 > fb_xhi + margin:
                    continue
            # Profile Y coords give extent along flight direction
            for pt in profile:
                vals.append(pt[1])
        elif flight_dir == "x" and axis == "y":
            y0 = m.get("y", 0)
            y1 = y0 + m.get("thickness", st)
            if flight_bbox:
                fb_ylo, fb_yhi = flight_bbox[2], flight_bbox[3]
                margin = st * 2
                if y1 < fb_ylo - margin or y0 > fb_yhi + margin:
                    continue
            for pt in profile:
                vals.append(pt[0])
    if not vals:
        return None
    return (min(vals), max(vals))


def _stringer_extent_perp(meshes, flight_dir, flight_bbox=None):
    """Return *(lo, hi)* of stringer outer faces perpendicular to *flight_dir*.

    For a Y-direction flight the stringers are at various X positions;
    return the min and max X of all stringer outer faces.
    For an X-direction flight return min/max Y of stringer outer faces.

    If *flight_bbox* ``(x_lo, x_hi, y_lo, y_hi)`` is provided, only include
    stringers whose perpendicular position overlaps the flight's own extent
    (filters out stringers belonging to other flights).
    """
    from stair_constants import STRINGER_THICKNESS
    st = STRINGER_THICKNESS
    vals = []
    for m in meshes:
        if m.get("ifc_type") != "stringer" or m.get("type") != "stringer":
            continue
        axis = m.get("axis", "x")  # extrusion axis: 'y'→profile in XZ, 'x'→profile in YZ
        if flight_dir == "y" and axis != "y":
            # Y-direction flight → stringer extruded along X → outer faces in X
            x0 = m.get("x", 0)
            x1 = x0 + m.get("thickness", st)
            # Filter: stringer must overlap flight's X range
            if flight_bbox:
                fb_xlo, fb_xhi = flight_bbox[0], flight_bbox[1]
                margin = st * 2
                if x1 < fb_xlo - margin or x0 > fb_xhi + margin:
                    continue
            vals.extend([x0, x1])
        elif flight_dir == "x" and axis == "y":
            # X-direction flight → stringer extruded along Y → outer faces in Y
            y0 = m.get("y", 0)
            y1 = y0 + m.get("thickness", st)
            if flight_bbox:
                fb_ylo, fb_yhi = flight_bbox[2], flight_bbox[3]
                margin = st * 2
                if y1 < fb_ylo - margin or y0 > fb_yhi + margin:
                    continue
            vals.extend([y0, y1])
    if not vals:
        return None
    return (min(vals), max(vals))


def _last_riser_rear_face(meshes, flight_num, flight_dir):
    """Return the coordinate of the rear face of the last riser in *flight_num*.

    For a Y-direction flight this is the maximum Y of the riser box.
    For an X-direction flight this is the extreme X (min or max depending
    on turn direction).
    """
    best = None
    for m in meshes:
        ifc = m.get("ifc_type", "")
        if ifc != "riser":
            continue
        name = m.get("name", "")
        fm = re.search(r"F(\d+)-(\d+)", name)
        if not fm or int(fm.group(1)) != flight_num:
            continue
        c = m.get("ifc_center")
        s = m.get("ifc_size")
        if not c or not s:
            continue
        if flight_dir == "y":
            face = c[1] + s[1] / 2  # rear = max Y
            if best is None or face > best:
                best = face
        else:
            # X-direction: rear could be min-X or max-X depending on turn
            face_lo = c[0] - s[0] / 2
            face_hi = c[0] + s[0] / 2
            if best is None:
                best = (face_lo, face_hi)
            else:
                best = (min(best[0], face_lo), max(best[1], face_hi))
    if flight_dir != "y" and best is not None:
        # Return the extreme X furthest from the origin
        return best[0] if abs(best[0]) > abs(best[1]) else best[1]
    return best


def _compute_plan_dimensions(meshes, params, plan_min_x, plan_min_y):
    """Return a list of dimension specs ``{p1, p2, offset, label}``."""
    # Compute plan bounding box from treads and winders ONLY.
    # Excludes risers (closing riser can extend beyond the last tread),
    # stringers, balustrades, and newels.
    all_x, all_y = [], []
    for m in meshes:
        ifc_type = m.get("ifc_type", "")
        if ifc_type not in ("tread", "winder_tread"):
            continue
        if m.get("type") == "box":
            c = m.get("ifc_center")
            s = m.get("ifc_size")
            if c and s:
                all_x.extend([c[0] - s[0] / 2, c[0] + s[0] / 2])
                all_y.extend([c[1] - s[1] / 2, c[1] + s[1] / 2])
        elif m.get("type") == "winder_polygon":
            fp = m.get("profile", [])
            for pt in fp:
                all_x.append(pt[0])
                all_y.append(pt[1])
    if not all_x or not all_y:
        return []
    bbox_min_x, bbox_max_x = min(all_x), max(all_x)
    bbox_min_y, bbox_max_y = min(all_y), max(all_y)

    flight_info = _identify_flights(meshes)
    stair_type = params.get("staircase_type", params.get("stair_type", "straight"))
    dims = []
    dim_offset = 300.0

    if not flight_info:
        return dims

    # Determine topmost flight number and which end the top flight's
    # treads are on (to replace that endpoint with the last riser face).
    top_fnum = max(fi["flight"] for fi in flight_info)

    # Work out which end of the bbox the top flight extends towards.
    # Treads of the top flight are at the "far" end; the last riser's
    # rear face replaces that extent limit.
    top_fi = [fi for fi in flight_info if fi["flight"] == top_fnum][0]
    top_tread_centers = []
    for m in meshes:
        if m.get("ifc_type") not in ("tread",):
            continue
        name = m.get("name", "")
        fm = re.search(r"[Ff]light\s*%d" % top_fnum, name)
        if not fm:
            continue
        c = m.get("ifc_center")
        if c:
            top_tread_centers.append(c)

    # Compute per-flight bounding boxes so we can place dimensions on
    # the outer edge of each flight (not the full stair bbox).
    flight_bboxes = {}
    for fi in flight_info:
        fnum = fi["flight"]
        fxs, fys = [], []
        for m in meshes:
            name = m.get("name", "")
            fm = re.search(r"[Ff]light\s*%d" % fnum, name)
            if not fm:
                # Also include winders/landing that belong to this flight
                if m.get("ifc_type") in ("winder_tread",) and re.search(r"F%d" % fnum, name):
                    pass  # include
                else:
                    continue
            if m.get("type") == "box":
                c = m.get("ifc_center")
                s = m.get("ifc_size")
                if c and s:
                    fxs.extend([c[0] - s[0] / 2, c[0] + s[0] / 2])
                    fys.extend([c[1] - s[1] / 2, c[1] + s[1] / 2])
            elif m.get("type") == "winder_polygon":
                fp = m.get("profile", [])
                for pt in fp:
                    fxs.append(pt[0])
                    fys.append(pt[1])
        if fxs and fys:
            flight_bboxes[fnum] = (min(fxs), max(fxs), min(fys), max(fys))

    # Plan centroid (bbox is already plan-only)
    plan_cx = (bbox_min_x + bbox_max_x) / 2
    plan_cy = (bbox_min_y + bbox_max_y) / 2

    # Compute the front-edge position of flight 1 (first riser or bottom
    # newel, whichever projects further forward).  Used to anchor the
    # flight 1 dim and stringer-to-stringer dim to the physical stair front.
    f1_fb = flight_bboxes.get(flight_info[0]["flight"]) if flight_info else None
    f1_front = _flight1_front_edge(
        meshes, flight_info[0]["direction"], f1_fb
    ) if flight_info else None

    # For each flight, create a length dimension along its direction.
    for fi in flight_info:
        fnum = fi["flight"]
        fdir = fi["direction"]  # "x" or "y" — direction treads run along
        fb = flight_bboxes.get(fnum)
        if not fb:
            continue

        # For flights 1 and 2, span the full plan bbox extent along the
        # flight direction.  Flight 3 (U-shape return) also spans the full
        # extent in double-winder stairs (it includes the winder 2 area);
        # the two Y-direction dims don't collide because flight 1 is on
        # the right edge and flight 3 is on the left edge.
        use_own_extent = (fnum >= 3 and stair_type != "double_winder")

        if fdir == "y":
            if use_own_extent:
                y_lo, y_hi = fb[2], fb[3]
            else:
                y_lo, y_hi = bbox_min_y, bbox_max_y
            # For flight 1, anchor the start to the stringer base so the
            # dim ties to the physical stair, not to other flights' treads.
            if fnum == 1 and f1_front is not None:
                y_lo = f1_front
            # Only clip to last riser for the top flight in straight stairs.
            # For winder stairs the dimension must include the winder box.
            if fnum == top_fnum and stair_type not in ("single_winder", "double_winder"):
                rr = _last_riser_rear_face(meshes, fnum, "y")
                if rr is not None:
                    y_hi = rr
            # Position: on the outer side of this flight (away from plan
            # centroid in X), using the flight's own X bbox.
            f_cx = (fb[0] + fb[1]) / 2
            if f_cx >= plan_cx:
                dim_x = fb[1]
                norm = (1, 0)   # push right (positive X)
            else:
                dim_x = fb[0]
                norm = (-1, 0)  # push left (negative X)
            dims.append({"p1": (dim_x, y_lo), "p2": (dim_x, y_hi),
                         "offset": dim_offset, "norm": norm})
        else:
            if use_own_extent:
                x_lo, x_hi = fb[0], fb[1]
            else:
                x_lo, x_hi = bbox_min_x, bbox_max_x
            if fnum == 1 and f1_front is not None:
                x_lo = f1_front
            if fnum == top_fnum and stair_type not in ("single_winder", "double_winder"):
                rr = _last_riser_rear_face(meshes, fnum, "x")
                if rr is not None:
                    if top_tread_centers:
                        avg_x = sum(c[0] for c in top_tread_centers) / len(top_tread_centers)
                        mid_x = (bbox_min_x + bbox_max_x) / 2
                        if avg_x < mid_x:
                            x_lo = rr
                        else:
                            x_hi = rr
                    else:
                        if abs(rr - x_lo) < abs(rr - x_hi):
                            x_lo = rr
                        else:
                            x_hi = rr
            # Position: on the outer side of this flight (away from plan
            # centroid in Y), using the flight's own Y bbox.
            f_cy = (fb[2] + fb[3]) / 2
            if f_cy >= plan_cy:
                dim_y = fb[3]
                norm = (0, 1)   # push up (positive Y in IFC)
            else:
                dim_y = fb[2]
                norm = (0, -1)  # push down (negative Y in IFC)
            dims.append({"p1": (x_lo, dim_y), "p2": (x_hi, dim_y),
                         "offset": dim_offset, "norm": norm})

    # If a winder stair has only 1 flight detected (the other flight has
    # 0 treads), add a dimension for the perpendicular extent (winder area).
    # This shows how far the turn projects from flight 1's outer edge.
    if len(flight_info) == 1 and stair_type in ("single_winder", "double_winder"):
        f1 = flight_info[0]
        f1dir = f1["direction"]
        fb1 = flight_bboxes.get(f1["flight"])
        if fb1:
            if f1dir == "y":
                # Flight 1 runs along Y; dimension the X extent (perpendicular).
                # Position at the top of the plan bbox (above all winders).
                dims.append({"p1": (bbox_min_x, bbox_max_y), "p2": (bbox_max_x, bbox_max_y),
                             "offset": dim_offset, "norm": (0, 1)})
            else:
                # Flight 1 runs along X; dimension the Y extent.
                dims.append({"p1": (bbox_max_x, bbox_min_y), "p2": (bbox_max_x, bbox_max_y),
                             "offset": dim_offset, "norm": (1, 0)})

    # Add stringer-to-stringer width dimension for the bottom flight (flight 1).
    # Pass flight 1's bbox so only stringers near flight 1 are included.
    # Position at flight 1's stringer base (not bbox_min which may include
    # other flights' treads further back).
    bottom_fi = flight_info[0]
    bdir = bottom_fi["direction"]
    fb1 = flight_bboxes.get(bottom_fi["flight"])
    ext = _stringer_extent_perp(meshes, bdir, flight_bbox=fb1)
    if ext:
        width_val = ext[1] - ext[0]
        lbl = "%.0f O/A\nStringer to Stringer" % width_val
        if bdir == "y":
            # Width is in X direction; place at the front edge of flight 1
            base_y = f1_front if f1_front is not None else bbox_min_y
            dims.append({"p1": (ext[0], base_y), "p2": (ext[1], base_y),
                         "offset": dim_offset, "norm": (0, -1), "label": lbl})
        else:
            base_x = f1_front if f1_front is not None else bbox_min_x
            dims.append({"p1": (base_x, ext[0]), "p2": (base_x, ext[1]),
                         "offset": dim_offset, "norm": (-1, 0), "label": lbl})

    return dims


# ── Public entry points ─────────────────────────────────────────

def meshes_to_dxf_string(meshes, params):
    """Generate a DXF plan-view string using solid-occlusion.

    *meshes* — list of stair preview mesh dicts.
    *params* — the raw parameter dict (kept for API compat; not used here).

    Returns:
        str: complete DXF file content.
    """
    dxf = _DxfWriter()
    dxf.add_linetype("DASHED", [10.0, 6.35, -3.175])
    for name, props in LAYERS.items():
        dxf.add_layer(name, color=props["color"], linetype=props["linetype"])
    layer = "STAIR_TREADS"

    # Step 1 — convert each non-riser mesh to (top_z, polygon).
    items = []
    for mesh in meshes:
        if mesh.get("ifc_type", "") in _SOLID_IFC_TYPES_EXCLUDED:
            continue
        poly, top_z = _mesh_to_poly_and_z(mesh)
        if poly is None or not poly.is_valid or poly.is_empty:
            continue
        items.append((top_z, poly))

    # Step 2 — sort highest-first (top of stair drawn first).
    items.sort(key=lambda t: -t[0])

    # Step 3 — draw visible edges with coverage tracking.
    coverage = Polygon()  # starts empty

    for _z, poly in items:
        exterior = list(poly.exterior.coords)
        for i in range(len(exterior) - 1):
            seg = LineString([exterior[i], exterior[i + 1]])
            if seg.length < _MIN_LENGTH:
                continue

            # Clip: remove the portion already covered by higher geometry.
            visible = seg if coverage.is_empty else seg.difference(coverage)

            if visible.is_empty:
                continue
            if hasattr(visible, "length") and visible.length < _MIN_LENGTH:
                continue

            _emit_geometry(dxf, visible, layer)

        # Expand the opaque coverage mask.
        coverage = poly if coverage.is_empty else coverage.union(poly)

    # Step 4 — dashed riser front/back lines trimmed per-side.
    # Build separate boundaries for stringers, handrails, and newels so
    # each end of the riser trims to the correct element type.
    boundaries = _build_trim_boundaries(meshes)

    for mesh in meshes:
        if mesh.get("ifc_type", "") not in _RISER_IFC_TYPES:
            continue
        for start, end in _riser_front_back(mesh):
            if boundaries:
                result = _trim_riser_line(start, end, boundaries)
                if result is None:
                    continue
                start, end = result
            dxf.add_line(start, end, layer="STAIR_RISERS")

    # Step 5 — compute plan bounds and add disclaimer text.
    plan_max_x = 0
    plan_min_y = 0
    plan_min_x = 0
    plan_max_y = 0
    for _z, poly in items:
        bounds = poly.bounds  # (minx, miny, maxx, maxy)
        if bounds[2] > plan_max_x:
            plan_max_x = bounds[2]
        if bounds[3] > plan_max_y:
            plan_max_y = bounds[3]
        if bounds[1] < plan_min_y:
            plan_min_y = bounds[1]
        if bounds[0] < plan_min_x:
            plan_min_x = bounds[0]
    # Disclaimer: below-right, offset enough to clear dimension lines
    text_x = plan_max_x + 500
    text_y = plan_min_y - 500
    _LINE1 = "StairSmith \u2014 Preliminary design aid only."
    _LINE2 = "User must verify all outputs before use."
    dxf.add_text(_LINE1, (text_x, text_y), height=60.0, layer="0")
    dxf.add_text(_LINE2, (text_x, text_y - 80), height=60.0, layer="0")

    # Step 6 — Orthographic elevation views (Front, Right, Back, Left).
    _ELEV_VIEWS = ["front", "right", "back", "left"]
    _ELEV_LABELS = ["FRONT ELEVATION", "RIGHT ELEVATION",
                    "BACK ELEVATION", "LEFT ELEVATION"]

    elev_bounds = {}
    for v in _ELEV_VIEWS:
        elev_bounds[v] = _compute_view_bounds(meshes, v)

    elev_y_top = plan_min_y - 3000
    elev_x = plan_min_x
    elev_bottom = elev_y_top  # track lowest point of elevation row

    for v, label in zip(_ELEV_VIEWS, _ELEV_LABELS):
        vb = elev_bounds[v]
        if vb == (0, 0, 0, 0):
            continue
        vw = vb[2] - vb[0]
        vh = vb[3] - vb[1]
        # Place so top-left of view bounds maps to (elev_x, elev_y_top).
        ox = elev_x - vb[0]
        oy = elev_y_top - vb[3]
        try:
            _draw_elevation(dxf, meshes, v, ox, oy)
        except Exception:
            pass
        _draw_floor_line(dxf, vb, ox, oy)
        # Label below the view.
        dxf.add_text(label, (elev_x, elev_y_top - vh - 150),
                     height=80.0, layer="0")
        bottom = elev_y_top - vh - 150 - 100
        if bottom < elev_bottom:
            elev_bottom = bottom
        elev_x += vw + 2000

    # Step 7 — Section views (2 per flight, cut along tread centreline).
    #   Left/right section pairs for each flight are grouped with 2x spacing
    #   between flights so paired views are easy to compare.
    flight_info = _identify_flights(meshes)
    if flight_info:
        sect_y_top = elev_bottom - 3000
        sect_x = plan_min_x
        sect_labels = iter("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        _SECT_GAP = 2000  # standard gap between adjacent sections
        prev_fnum = None

        for fi in flight_info:
            ca = fi["cut_axis"]
            cp = fi["cut_pos"]
            fnum = fi["flight"]

            # Double gap between flight groups (but not before the first)
            if prev_fnum is not None and fnum != prev_fnum:
                sect_x += _SECT_GAP  # extra gap (total 2x since loop adds 1x)
            prev_fnum = fnum

            for look_idx, look_pos in enumerate((True, False)):
                lbl_char = next(sect_labels, "?")
                view = _section_view_for(ca, look_pos)
                facing = "Left" if look_pos else "Right"
                vb = _compute_view_bounds(meshes, view)
                if vb == (0, 0, 0, 0):
                    continue
                vw = vb[2] - vb[0]
                vh = vb[3] - vb[1]
                ox = sect_x - vb[0]
                oy = sect_y_top - vb[3]
                try:
                    _draw_section(dxf, meshes, ca, cp, look_pos, ox, oy)
                except Exception:
                    pass
                _draw_floor_line(dxf, vb, ox, oy)
                label = "Flight %d (%s facing section)" % (fnum, facing)
                dxf.add_text(label, (sect_x, sect_y_top - vh - 150),
                             height=80.0, layer="0")
                sect_x += vw + _SECT_GAP

    # Step 8 — Plan dimensions following flight directions.
    #   Each flight gets an "along direction" length dimension.
    #   Plus one stringer-to-stringer width dimension for the bottom flight.
    #   The topmost flight's dimension stops at the rear face of the last riser.
    plan_dims = _compute_plan_dimensions(meshes, params, plan_min_x, plan_min_y)
    for pd in plan_dims:
        _draw_dim_line(dxf, pd["p1"], pd["p2"], pd["offset"],
                       label=pd.get("label"), norm=pd.get("norm"))

    return dxf.to_string()


def meshes_to_dxf(meshes, params):
    """Generate a DXF plan-view file and return its path.

    Thin wrapper around :func:`meshes_to_dxf_string` for the Flask route
    which needs a file path to pass to ``send_file``.
    """
    content = meshes_to_dxf_string(meshes, params)
    tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    tmp.write(content.encode("utf-8"))
    tmp.close()
    return tmp.name
