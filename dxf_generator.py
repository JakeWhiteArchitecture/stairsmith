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

import tempfile
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union


# ── Layer definitions ────────────────────────────────────────────
LAYERS = {
    "STAIR_TREADS": {"color": 7, "linetype": "CONTINUOUS"},
    "STAIR_RISERS": {"color": 8, "linetype": "DASHED"},
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
    max_x = 0
    min_y = 0
    for _z, poly in items:
        bounds = poly.bounds  # (minx, miny, maxx, maxy)
        if bounds[2] > max_x:
            max_x = bounds[2]
        if bounds[1] < min_y:
            min_y = bounds[1]
    text_x = max_x + 60
    text_y = min_y
    _LINE1 = "StairSmith \u2014 Preliminary design aid only."
    _LINE2 = "User must verify all outputs before use."
    dxf.add_text(_LINE1, (text_x, text_y), height=60.0, layer="0")
    dxf.add_text(_LINE2, (text_x, text_y - 80), height=60.0, layer="0")

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
