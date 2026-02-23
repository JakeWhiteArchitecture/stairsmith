"""
DXF Plan View Generator — produces a 2D DXF plan-view drawing from stair meshes.

Pure-Python implementation (no external dependencies) so it runs in Pyodide.
Generates DXF R12 (AC1009) output — the most universally compatible format,
opens correctly in AutoCAD, BricsCAD, LibreCAD, and all other DXF viewers.

Public entry point:
    meshes_to_dxf_string(meshes, params) -> str   # returns DXF file content
"""

from stair_constants import _parse, STRINGER_THICKNESS


# ── Layer definitions: (name, colour-index, linetype) ──────────────
LAYERS = {
    "STAIR_TREADS":    {"color": 7, "linetype": "CONTINUOUS"},
    "STAIR_RISERS":    {"color": 9, "linetype": "DASHED"},
    "STAIR_STRINGERS": {"color": 7, "linetype": "CONTINUOUS"},
    "STAIR_HANDRAIL":  {"color": 7, "linetype": "CONTINUOUS"},
}

# Map ifc_type to layer name
IFC_TYPE_TO_LAYER = {
    "tread":        "STAIR_TREADS",
    "riser":        "STAIR_RISERS",
    "threshold":    "STAIR_TREADS",
    "landing":      "STAIR_TREADS",
    "newel":        "STAIR_HANDRAIL",
    "winder_tread": "STAIR_TREADS",
    "winder_riser": "STAIR_RISERS",
    "stringer":     "STAIR_STRINGERS",
    "handrail":     "STAIR_HANDRAIL",
    "baserail":     "STAIR_HANDRAIL",
    "spindle":      "STAIR_HANDRAIL",
}


# ── Minimal DXF R12 writer ────────────────────────────────────────

class _DxfWriter:
    """Builds a DXF R12 (AC1009) string using POLYLINE/VERTEX and LINE.

    R12 is the simplest DXF format — no handles, no ownership, no BLOCKS
    or OBJECTS sections required.  Universally compatible.
    """

    def __init__(self):
        self._entities = []
        self._layers = {}
        self._linetypes = {}

    def add_linetype(self, name, pattern):
        self._linetypes[name] = pattern

    def add_layer(self, name, color=7, linetype="CONTINUOUS"):
        self._layers[name] = {"color": color, "linetype": linetype}

    def add_polyline(self, points, close=True, layer="0"):
        self._entities.append(("POLYLINE", points, close, layer))

    def add_line(self, start, end, layer="0"):
        self._entities.append(("LINE", start, end, layer))

    def to_string(self):
        lines = []
        a = lines.append

        # ── HEADER ──
        a("  0"); a("SECTION")
        a("  2"); a("HEADER")
        a("  9"); a("$ACADVER")
        a("  1"); a("AC1009")
        a("  9"); a("$MEASUREMENT")
        a(" 70"); a("     1")
        a("  0"); a("ENDSEC")

        # ── TABLES ──
        a("  0"); a("SECTION")
        a("  2"); a("TABLES")

        # LTYPE table
        a("  0"); a("TABLE")
        a("  2"); a("LTYPE")
        a(" 70"); a("     %d" % (len(self._linetypes) + 1))

        # Continuous (always present)
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

        # ── ENTITIES ──
        a("  0"); a("SECTION")
        a("  2"); a("ENTITIES")

        for ent in self._entities:
            if ent[0] == "POLYLINE":
                _, points, close, layer = ent
                # POLYLINE header
                a("  0"); a("POLYLINE")
                a("  8"); a(layer)
                a(" 66"); a("     1")
                a(" 70"); a("     %d" % (1 if close else 0))
                # Vertices
                for x, y in points:
                    a("  0"); a("VERTEX")
                    a("  8"); a(layer)
                    a(" 10"); a("%.6f" % x)
                    a(" 20"); a("%.6f" % y)
                    a(" 30"); a("0.0")
                # SEQEND
                a("  0"); a("SEQEND")
                a("  8"); a(layer)

            elif ent[0] == "LINE":
                _, start, end, layer = ent
                a("  0"); a("LINE")
                a("  8"); a(layer)
                a(" 10"); a("%.6f" % start[0])
                a(" 20"); a("%.6f" % start[1])
                a(" 30"); a("0.0")
                a(" 11"); a("%.6f" % end[0])
                a(" 21"); a("%.6f" % end[1])
                a(" 31"); a("0.0")

        a("  0"); a("ENDSEC")

        # ── EOF ──
        a("  0"); a("EOF")

        return "\r\n".join(lines) + "\r\n"


# ── Geometry helpers ──────────────────────────────────────────────

def _layer_for(mesh):
    ifc_type = mesh.get("ifc_type", "")
    return IFC_TYPE_TO_LAYER.get(ifc_type, "0")


def _add_box_plan(dxf, mesh):
    center = mesh.get("ifc_center")
    size = mesh.get("ifc_size")
    if not center or not size:
        return
    cx, cy, cz = center
    sx, sy, sz = size
    hx = sx / 2.0
    hy = sy / 2.0
    points = [
        (cx - hx, cy - hy),
        (cx + hx, cy - hy),
        (cx + hx, cy + hy),
        (cx - hx, cy + hy),
    ]
    dxf.add_polyline(points, close=True, layer=_layer_for(mesh))


def _add_winder_polygon_plan(dxf, mesh):
    profile = mesh.get("profile")
    if not profile or len(profile) < 3:
        return
    points = [(p[0], p[1]) for p in profile]
    dxf.add_polyline(points, close=True, layer=_layer_for(mesh))


def _add_stringer_plan(dxf, mesh):
    profile = mesh.get("profile")
    thickness = mesh.get("thickness", 0)
    if not profile or thickness == 0:
        return
    layer = _layer_for(mesh)
    axis = mesh.get("axis")
    if axis == "y":
        xs = [p[0] for p in profile]
        y_start = mesh.get("y", 0)
        min_x, max_x = min(xs), max(xs)
        points = [
            (min_x, y_start),
            (max_x, y_start),
            (max_x, y_start + thickness),
            (min_x, y_start + thickness),
        ]
    else:
        ys = [p[0] for p in profile]
        x_start = mesh.get("x", 0)
        min_y, max_y = min(ys), max(ys)
        points = [
            (x_start, min_y),
            (x_start + thickness, min_y),
            (x_start + thickness, max_y),
            (x_start, max_y),
        ]
    dxf.add_polyline(points, close=True, layer=layer)


def _draw_straight_tread_nosings(dxf, p):
    width = p["stair_width"] - STRINGER_THICKNESS
    going = p["going"]
    nosing = p["nosing"]
    riser_t = p["riser_thickness"]
    num_treads = p["num_treads"]
    tread_depth = going + nosing + riser_t
    layer = "STAIR_TREADS"
    for i in range(num_treads):
        front_y = i * going - nosing
        dxf.add_line((0, front_y), (width, front_y), layer=layer)
        if i == num_treads - 1:
            back_y = front_y + tread_depth
            dxf.add_line((0, back_y), (width, back_y), layer=layer)


# ── Public entry point ────────────────────────────────────────────

def meshes_to_dxf_string(meshes, params):
    """Generate a DXF plan-view string from stair preview meshes.

    Returns:
        str: DXF file content (ready to save or convert to blob)
    """
    dxf = _DxfWriter()

    # Set up linetypes
    dxf.add_linetype("DASHED", [10.0, 6.35, -3.175])

    # Set up layers
    for name, props in LAYERS.items():
        dxf.add_layer(name, color=props["color"], linetype=props["linetype"])

    p = _parse(params)
    stair_type = p["staircase_type"]

    # ── Tread nosing lines for straight stairs (from params) ──
    if stair_type == "straight":
        _draw_straight_tread_nosings(dxf, p)

    # ── Generic mesh loop ──
    for mesh in meshes:
        ifc_type = mesh.get("ifc_type", "")
        # For straight stairs, treads are drawn explicitly above
        if stair_type == "straight" and ifc_type in ("tread", "threshold"):
            continue
        mtype = mesh.get("type", "")
        if mtype == "box":
            _add_box_plan(dxf, mesh)
        elif mtype == "winder_polygon":
            _add_winder_polygon_plan(dxf, mesh)
        elif mtype == "stringer":
            _add_stringer_plan(dxf, mesh)

    return dxf.to_string()
