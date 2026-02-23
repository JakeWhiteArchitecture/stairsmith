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


# ── Layer definitions ────────────────────────────────────────────
LAYERS = {
    "STAIR_TREADS": {"color": 7, "linetype": "CONTINUOUS"},
}

# IFC types excluded from the plan view (not visible looking straight down).
_EXCLUDED_IFC_TYPES = frozenset({"riser", "winder_riser"})

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
        self._layers = {}

    def add_layer(self, name, color=7, linetype="CONTINUOUS"):
        self._layers[name] = {"color": color, "linetype": linetype}

    def add_line(self, start, end, layer="0"):
        self._entities.append((start, end, layer))

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

        # LTYPE table — CONTINUOUS only
        a("  0"); a("TABLE")
        a("  2"); a("LTYPE")
        a(" 70"); a("     1")
        a("  0"); a("LTYPE")
        a("  2"); a("CONTINUOUS")
        a(" 70"); a("     0")
        a("  3"); a("Solid line")
        a(" 72"); a("    65")
        a(" 73"); a("     0")
        a(" 40"); a("0.0")
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
    for name, props in LAYERS.items():
        dxf.add_layer(name, color=props["color"], linetype=props["linetype"])
    layer = "STAIR_TREADS"

    # Step 1 — convert each non-riser mesh to (top_z, polygon).
    items = []
    for mesh in meshes:
        if mesh.get("ifc_type", "") in _EXCLUDED_IFC_TYPES:
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
