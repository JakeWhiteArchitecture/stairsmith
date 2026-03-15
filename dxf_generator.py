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

import re
import tempfile
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union


# ── Layer definitions ────────────────────────────────────────────
LAYERS = {
    "STAIR_TREADS": {"color": 7, "linetype": "CONTINUOUS"},
    "STAIR_RISERS": {"color": 8, "linetype": "DASHED"},
    "ELEVATION":     {"color": 7, "linetype": "CONTINUOUS"},
    "HIDDEN":        {"color": 8, "linetype": "DASHED"},
    "SECTION_CUT":   {"color": 7, "linetype": "CONTINUOUS"},
    "SECTION_BEYOND":{"color": 8, "linetype": "CONTINUOUS"},
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
            a("  1"); a(text)
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


def _mesh_to_elev_poly(mesh, view):
    """Return *(Polygon, min_depth, is_stringer)* for *mesh* in *view*.

    Returns *(None, None, False)* if the mesh cannot be projected.
    """
    mtype = mesh.get("type", "")
    ifc_type = mesh.get("ifc_type", "")
    is_str = ifc_type in _STRINGER_IFC

    try:
        if mtype == "box":
            center = mesh.get("ifc_center")
            size = mesh.get("ifc_size")
            if not center or not size:
                return None, None, False
            cx, cy, cz = center
            sx, sy, sz = size
            corners = []
            for dx in (-1, 1):
                for dy in (-1, 1):
                    for dz in (-1, 1):
                        corners.append(_project_point(
                            cx + dx * sx / 2,
                            cy + dy * sy / 2,
                            cz + dz * sz / 2, view))
            min_vx = min(c[0] for c in corners)
            max_vx = max(c[0] for c in corners)
            min_vy = min(c[1] for c in corners)
            max_vy = max(c[1] for c in corners)
            min_d = min(c[2] for c in corners)
            poly = Polygon([(min_vx, min_vy), (max_vx, min_vy),
                            (max_vx, max_vy), (min_vx, max_vy)])
            return poly, min_d, is_str

        if mtype == "stringer":
            profile = mesh.get("profile")
            thickness = mesh.get("thickness", 0)
            if not profile or len(profile) < 3 or thickness == 0:
                return None, None, False
            axis = mesh.get("axis")

            if axis == "y":
                # Profile in XZ, extruded along Y from y0
                y0 = mesh.get("y", 0)
                proj_all = []
                for xv, zv in profile:
                    proj_all.append(_project_point(xv, y0, zv, view))
                    proj_all.append(_project_point(xv, y0 + thickness, zv, view))
                if view in ("front", "back"):
                    # Looking along Y → see profile (XZ) shape
                    pts = [_project_point(xv, y0, zv, view)[:2]
                           for xv, zv in profile]
                    poly = Polygon(pts)
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    if poly.is_empty:
                        return None, None, False
                    return poly, min(p[2] for p in proj_all), True
                else:
                    # Perpendicular → bounding rectangle
                    return _rect_from_projected(proj_all, True)

            else:
                # Profile in YZ, extruded along X from x0
                x0 = mesh.get("x", 0)
                proj_all = []
                for yv, zv in profile:
                    proj_all.append(_project_point(x0, yv, zv, view))
                    proj_all.append(_project_point(x0 + thickness, yv, zv, view))
                if view in ("right", "left"):
                    # Looking along X → see profile (YZ) shape
                    pts = [_project_point(x0, yv, zv, view)[:2]
                           for yv, zv in profile]
                    poly = Polygon(pts)
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    if poly.is_empty:
                        return None, None, False
                    return poly, min(p[2] for p in proj_all), True
                else:
                    return _rect_from_projected(proj_all, True)

        if mtype == "winder_polygon":
            fp = mesh.get("profile")
            if not fp or len(fp) < 3:
                return None, None, False
            z = mesh.get("z", 0)
            thick = mesh.get("thickness", 0)
            proj_all = []
            for pt in fp:
                proj_all.append(_project_point(pt[0], pt[1], z, view))
                proj_all.append(_project_point(pt[0], pt[1], z + thick, view))
            return _rect_from_projected(proj_all, is_str)

    except Exception:
        pass

    return None, None, False


def _rect_from_projected(proj_pts, is_stringer):
    """Build a bounding rectangle Polygon from projected points."""
    if not proj_pts:
        return None, None, False
    min_vx = min(p[0] for p in proj_pts)
    max_vx = max(p[0] for p in proj_pts)
    min_vy = min(p[1] for p in proj_pts)
    max_vy = max(p[1] for p in proj_pts)
    min_d = min(p[2] for p in proj_pts)
    if max_vx - min_vx < _MIN_LENGTH or max_vy - min_vy < _MIN_LENGTH:
        return None, None, False
    poly = Polygon([(min_vx, min_vy), (max_vx, min_vy),
                    (max_vx, max_vy), (min_vx, max_vy)])
    return poly, min_d, is_stringer


def _safe_difference(geom, coverage):
    """Compute geom.difference(coverage), surviving GEOS TopologyException.

    In Pyodide/WASM the C++ TopologyException from GEOS is not always
    caught by Python ``try/except``.  We mitigate by pre-buffering the
    coverage polygon when the raw call fails validation.
    """
    if coverage.is_empty:
        return geom
    try:
        # Fast path — works in the vast majority of cases.
        return geom.difference(coverage)
    except Exception:
        pass
    try:
        return geom.difference(coverage.buffer(0))
    except Exception:
        return geom  # give up, draw anyway


def _emit_geometry_offset(dxf, geom, layer, ox, oy):
    """Draw a Shapely geometry as DXF LINEs with an (ox, oy) offset."""
    if geom.is_empty:
        return
    gt = geom.geom_type
    if gt == "LineString":
        coords = list(geom.coords)
        for i in range(len(coords) - 1):
            dxf.add_line((coords[i][0] + ox, coords[i][1] + oy),
                         (coords[i + 1][0] + ox, coords[i + 1][1] + oy),
                         layer=layer)
    elif gt in ("MultiLineString", "GeometryCollection"):
        for g in geom.geoms:
            _emit_geometry_offset(dxf, g, layer, ox, oy)


def _compute_view_bounds(meshes, view):
    """Return *(min_vx, min_vy, max_vx, max_vy)* bounding box in view coords."""
    xs, ys = [], []
    for mesh in meshes:
        poly, _d, _s = _mesh_to_elev_poly(mesh, view)
        if poly is None:
            continue
        b = poly.bounds
        xs.extend([b[0], b[2]])
        ys.extend([b[1], b[3]])
    if not xs:
        return (0, 0, 0, 0)
    return (min(xs), min(ys), max(xs), max(ys))


def _clip_against_list(seg, polys):
    """Remove parts of *seg* inside any polygon in *polys*.

    Clips against individual polygons one at a time (no union needed),
    which avoids GEOS TopologyException in Pyodide/WASM.
    """
    remaining = seg
    for poly in polys:
        if remaining.is_empty:
            break
        try:
            if not poly.intersects(remaining):
                continue
            remaining = remaining.difference(poly)
        except Exception:
            # Single-polygon difference almost never fails, but be safe.
            continue
    return remaining


def _tread_visible_in_view(mesh, view):
    """Return True if a tread/riser should be drawn in this elevation view.

    Treads are only shown when the stringer of their flight is perpendicular
    to the viewing direction (i.e., we're looking at the stair from the side).

    For box treads, flight direction is inferred from aspect ratio:
    - sx > sy → tread spans X → flight runs along Y → visible in left/right
    - sy > sx → tread spans Y → flight runs along X → visible in front/back
    """
    ifc_type = mesh.get("ifc_type", "")
    if ifc_type not in _TREAD_RISER_IFC:
        return True  # non-tread/riser meshes are always visible
    mtype = mesh.get("type", "")
    if mtype == "box":
        size = mesh.get("ifc_size")
        if not size:
            return True
        sx, sy, _sz = size
        if sx > sy:
            # Tread spans X → flight along Y → show in left/right (perpendicular)
            return view in ("left", "right")
        else:
            # Tread spans Y → flight along X → show in front/back (perpendicular)
            return view in ("front", "back")
    # Winder polygons: show in all views (transitional elements)
    return True


def _draw_elevation(dxf, meshes, view, ox, oy):
    """Draw one orthographic elevation with solid-occlusion.

    Visible edges → ELEVATION layer (white).
    Tread/riser edges hidden *only* by stringers → HIDDEN layer (dashed grey).

    Uses per-polygon clipping (no union) to avoid GEOS TopologyException
    that cannot be caught in Pyodide/WASM.
    """
    items = []  # (depth, poly, is_stringer, is_tread_riser)
    for mesh in meshes:
        if not _tread_visible_in_view(mesh, view):
            continue
        poly, depth, is_str = _mesh_to_elev_poly(mesh, view)
        if poly is None or not poly.is_valid or poly.is_empty:
            continue
        is_tr = mesh.get("ifc_type", "") in _TREAD_RISER_IFC
        items.append((depth, poly, is_str, is_tr))

    items.sort(key=lambda t: t[0])

    # Build coverage lists incrementally (no union needed).
    all_polys = []      # all polygons closer than current
    nostr_polys = []    # non-stringer polygons closer than current

    for _d, poly, is_str, is_tr in items:
        exterior = list(poly.exterior.coords)

        for i in range(len(exterior) - 1):
            seg = LineString([exterior[i], exterior[i + 1]])
            if seg.length < _MIN_LENGTH:
                continue
            visible = _clip_against_list(seg, all_polys)
            if visible.is_empty:
                continue
            if hasattr(visible, "length") and visible.length < _MIN_LENGTH:
                continue
            _emit_geometry_offset(dxf, visible, "ELEVATION", ox, oy)

        # Hidden-through-stringer pass for treads / risers.
        if is_tr:
            for i in range(len(exterior) - 1):
                seg = LineString([exterior[i], exterior[i + 1]])
                if seg.length < _MIN_LENGTH:
                    continue
                vis_no_str = _clip_against_list(seg, nostr_polys)
                if vis_no_str.is_empty:
                    continue
                vis_all = _clip_against_list(seg, all_polys)
                if vis_all.is_empty:
                    hidden = vis_no_str
                else:
                    hidden = _clip_against_list(vis_no_str, [vis_all]) \
                        if vis_all.geom_type in ("LineString", "MultiLineString") \
                        else vis_no_str
                    # vis_all is a line geometry; we need the AREA that hides.
                    # Simpler: hidden = parts in vis_no_str not in vis_all.
                    # Since both are line subsets of the same original seg,
                    # hidden = vis_no_str minus the visible portions.
                    try:
                        hidden = vis_no_str.difference(vis_all)
                    except Exception:
                        hidden = vis_no_str
                if hidden.is_empty:
                    continue
                if hasattr(hidden, "length") and hidden.length < _MIN_LENGTH:
                    continue
                _emit_geometry_offset(dxf, hidden, "HIDDEN", ox, oy)

        all_polys.append(poly)
        if not is_str:
            nostr_polys.append(poly)


# ── Section helpers ──────────────────────────────────────────────

def _mesh_extent(mesh, axis):
    """Return *(lo, hi)* of mesh extent along *axis* ('x' or 'y'), or None."""
    mtype = mesh.get("type", "")
    idx = 0 if axis == "x" else 1

    if mtype == "box":
        c = mesh.get("ifc_center")
        s = mesh.get("ifc_size")
        if not c or not s:
            return None
        h = s[idx] / 2.0
        return (c[idx] - h, c[idx] + h)

    if mtype == "stringer":
        profile = mesh.get("profile")
        thickness = mesh.get("thickness", 0)
        if not profile:
            return None
        ma = mesh.get("axis")
        if ma == "y":
            if axis == "y":
                y0 = mesh.get("y", 0)
                return (y0, y0 + thickness)
            vals = [p[0] for p in profile]
            return (min(vals), max(vals))
        else:
            if axis == "x":
                x0 = mesh.get("x", 0)
                return (x0, x0 + thickness)
            vals = [p[0] for p in profile]
            return (min(vals), max(vals))

    if mtype == "winder_polygon":
        fp = mesh.get("profile")
        if not fp:
            return None
        vals = [p[idx] for p in fp]
        return (min(vals), max(vals))

    return None


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
        if len(centers) < 2:
            continue
        xs = [c[0] for c in centers]
        ys = [c[1] for c in centers]
        if (max(ys) - min(ys)) > (max(xs) - min(xs)):
            result.append({"flight": fnum, "cut_axis": "x",
                           "cut_pos": sum(xs) / len(xs), "direction": "y"})
        else:
            result.append({"flight": fnum, "cut_axis": "y",
                           "cut_pos": sum(ys) / len(ys), "direction": "x"})
    return result


def _mesh_cut_profile_2d(mesh, cut_axis, cut_pos, view):
    """Return a Polygon in *view* coords for the cross-section, or None."""
    mtype = mesh.get("type", "")
    TOL = 1.0  # mm tolerance

    try:
        if mtype == "box":
            c = mesh.get("ifc_center")
            s = mesh.get("ifc_size")
            if not c or not s:
                return None
            cx, cy, cz = c
            sx, sy, sz = s
            if cut_axis == "x":
                if not (cx - sx / 2 - TOL <= cut_pos <= cx + sx / 2 + TOL):
                    return None
                pts = [(cut_pos, cy - sy / 2, cz - sz / 2),
                       (cut_pos, cy + sy / 2, cz - sz / 2),
                       (cut_pos, cy + sy / 2, cz + sz / 2),
                       (cut_pos, cy - sy / 2, cz + sz / 2)]
            else:
                if not (cy - sy / 2 - TOL <= cut_pos <= cy + sy / 2 + TOL):
                    return None
                pts = [(cx - sx / 2, cut_pos, cz - sz / 2),
                       (cx + sx / 2, cut_pos, cz - sz / 2),
                       (cx + sx / 2, cut_pos, cz + sz / 2),
                       (cx - sx / 2, cut_pos, cz + sz / 2)]
            pts2 = [_project_point(*p, view)[:2] for p in pts]
            return Polygon(pts2)

        if mtype == "stringer":
            profile = mesh.get("profile")
            thickness = mesh.get("thickness", 0)
            if not profile or len(profile) < 3 or thickness == 0:
                return None
            ma = mesh.get("axis")
            if ma == "y":
                y0 = mesh.get("y", 0)
                if cut_axis == "y":
                    if not (y0 - TOL <= cut_pos <= y0 + thickness + TOL):
                        return None
                    pts = [(xv, cut_pos, zv) for xv, zv in profile]
                else:
                    xs = [p[0] for p in profile]
                    if not (min(xs) - TOL <= cut_pos <= max(xs) + TOL):
                        return None
                    zs = [p[1] for p in profile]
                    pts = [(cut_pos, y0, min(zs)),
                           (cut_pos, y0 + thickness, min(zs)),
                           (cut_pos, y0 + thickness, max(zs)),
                           (cut_pos, y0, max(zs))]
            else:
                x0 = mesh.get("x", 0)
                if cut_axis == "x":
                    if not (x0 - TOL <= cut_pos <= x0 + thickness + TOL):
                        return None
                    pts = [(cut_pos, yv, zv) for yv, zv in profile]
                else:
                    ys = [p[0] for p in profile]
                    if not (min(ys) - TOL <= cut_pos <= max(ys) + TOL):
                        return None
                    zs = [p[1] for p in profile]
                    pts = [(x0, cut_pos, min(zs)),
                           (x0 + thickness, cut_pos, min(zs)),
                           (x0 + thickness, cut_pos, max(zs)),
                           (x0, cut_pos, max(zs))]
            pts2 = [_project_point(*p, view)[:2] for p in pts]
            poly = Polygon(pts2)
            if not poly.is_valid:
                poly = poly.buffer(0)
            return poly if not poly.is_empty else None

        if mtype == "winder_polygon":
            fp = mesh.get("profile")
            if not fp or len(fp) < 3:
                return None
            z = mesh.get("z", 0)
            thick = mesh.get("thickness", 0)
            fp_poly = Polygon([(p[0], p[1]) for p in fp])
            if cut_axis == "x":
                ys = [p[1] for p in fp]
                cut_line = LineString([(cut_pos, min(ys) - 100),
                                      (cut_pos, max(ys) + 100)])
            else:
                xs = [p[0] for p in fp]
                cut_line = LineString([(min(xs) - 100, cut_pos),
                                      (max(xs) + 100, cut_pos)])
            inter = fp_poly.intersection(cut_line)
            if inter.is_empty:
                return None
            ic = _collect_points(inter)
            if len(ic) < 2:
                return None
            if cut_axis == "x":
                yvals = [c[1] for c in ic]
                pts = [(cut_pos, min(yvals), z),
                       (cut_pos, max(yvals), z),
                       (cut_pos, max(yvals), z + thick),
                       (cut_pos, min(yvals), z + thick)]
            else:
                xvals = [c[0] for c in ic]
                pts = [(min(xvals), cut_pos, z),
                       (max(xvals), cut_pos, z),
                       (max(xvals), cut_pos, z + thick),
                       (min(xvals), cut_pos, z + thick)]
            pts2 = [_project_point(*p, view)[:2] for p in pts]
            poly = Polygon(pts2)
            return poly if poly.is_valid and not poly.is_empty else None

    except Exception:
        pass
    return None


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

    # 1. Cut profiles (white, SECTION_CUT) — always fully drawn.
    #    Track which meshes are cut so we can skip them from beyond pass.
    cut_ids = set()
    for idx, mesh in enumerate(meshes):
        cpoly = _mesh_cut_profile_2d(mesh, cut_axis, cut_pos, view)
        if cpoly is None or cpoly.is_empty:
            continue
        cut_ids.add(idx)
        try:
            ext = list(cpoly.exterior.coords)
        except Exception:
            continue
        for i in range(len(ext) - 1):
            dxf.add_line((ext[i][0] + ox, ext[i][1] + oy),
                         (ext[i + 1][0] + ox, ext[i + 1][1] + oy),
                         layer="SECTION_CUT")

    # 2. Beyond geometry (grey, SECTION_BEYOND) with occlusion.
    #    Skip meshes already drawn as cut profiles to avoid duplicate lines.
    items = []
    for idx, mesh in enumerate(meshes):
        if idx in cut_ids:
            continue
        ext_range = _mesh_extent(mesh, cut_axis)
        if ext_range is None:
            continue
        if look_positive and ext_range[1] <= cut_pos + 1:
            continue
        if not look_positive and ext_range[0] >= cut_pos - 1:
            continue
        poly, depth, _s = _mesh_to_elev_poly(mesh, view)
        if poly is None or not poly.is_valid or poly.is_empty:
            continue
        items.append((depth, poly))

    items.sort(key=lambda t: t[0])
    covered = []

    for _d, poly in items:
        exterior = list(poly.exterior.coords)
        for i in range(len(exterior) - 1):
            seg = LineString([exterior[i], exterior[i + 1]])
            if seg.length < _MIN_LENGTH:
                continue
            visible = _clip_against_list(seg, covered)
            if visible.is_empty:
                continue
            if hasattr(visible, "length") and visible.length < _MIN_LENGTH:
                continue
            _emit_geometry_offset(dxf, visible, "SECTION_BEYOND", ox, oy)
        covered.append(poly)


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

    # Step 5 — add disclaimer text to the bottom-right of the stair geometry.
    plan_max_x = 0
    plan_min_y = 0
    plan_min_x = 0
    for _z, poly in items:
        bounds = poly.bounds  # (minx, miny, maxx, maxy)
        if bounds[2] > plan_max_x:
            plan_max_x = bounds[2]
        if bounds[1] < plan_min_y:
            plan_min_y = bounds[1]
        if bounds[0] < plan_min_x:
            plan_min_x = bounds[0]
    text_x = plan_max_x + 60
    text_y = plan_min_y
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
        # Label below the view.
        dxf.add_text(label, (elev_x, elev_y_top - vh - 150),
                     height=80.0, layer="0")
        bottom = elev_y_top - vh - 150 - 100
        if bottom < elev_bottom:
            elev_bottom = bottom
        elev_x += vw + 2000

    # Step 7 — Section views (2 per flight, cut along tread centreline).
    flight_info = _identify_flights(meshes)
    if flight_info:
        sect_y_top = elev_bottom - 3000
        sect_x = plan_min_x
        sect_labels = iter("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

        for fi in flight_info:
            ca = fi["cut_axis"]
            cp = fi["cut_pos"]
            fnum = fi["flight"]

            for look_pos in (True, False):
                lbl_char = next(sect_labels, "?")
                view = _section_view_for(ca, look_pos)
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
                label = "SECTION %s-%s  (Flight %d)" % (lbl_char, lbl_char, fnum)
                dxf.add_text(label, (sect_x, sect_y_top - vh - 150),
                             height=80.0, layer="0")
                sect_x += vw + 2000

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
