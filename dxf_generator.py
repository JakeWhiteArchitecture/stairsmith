"""
DXF Plan View Generator — produces a 2D DXF plan-view drawing from stair meshes.

Uses ezdxf for reliable, spec-compliant DXF output that opens correctly
in AutoCAD, BricsCAD, LibreCAD, and other viewers.

Public entry point:
    meshes_to_dxf(meshes, params) -> str   # returns path to temp DXF file
"""

import math
import os
import tempfile

import ezdxf
from ezdxf.math import Vec2


# ── Layer definitions: (name, colour-index, linetype) ──────────────
LAYERS = {
    "STAIR_TREADS":    {"color": 7, "linetype": "Continuous"},
    "STAIR_RISERS":    {"color": 9, "linetype": "DASHED"},
    "STAIR_STRINGERS": {"color": 3, "linetype": "Continuous"},
    "STAIR_HANDRAIL":  {"color": 5, "linetype": "Continuous"},
    "STAIR_NEWELS":    {"color": 1, "linetype": "Continuous"},
    "STAIR_SPINDLES":  {"color": 8, "linetype": "Continuous"},
    "STAIR_LANDINGS":  {"color": 7, "linetype": "Continuous"},
    "STAIR_BASERAIL":  {"color": 8, "linetype": "Continuous"},
}

# Map ifc_type to layer name
IFC_TYPE_TO_LAYER = {
    "tread":        "STAIR_TREADS",
    "riser":        "STAIR_RISERS",
    "threshold":    "STAIR_TREADS",
    "landing":      "STAIR_LANDINGS",
    "newel":        "STAIR_NEWELS",
    "winder_tread": "STAIR_TREADS",
    "winder_riser": "STAIR_RISERS",
    "stringer":     "STAIR_STRINGERS",
    "handrail":     "STAIR_HANDRAIL",
    "baserail":     "STAIR_BASERAIL",
    "spindle":      "STAIR_SPINDLES",
}


def _layer_for(mesh):
    """Return the DXF layer name for a given mesh."""
    ifc_type = mesh.get("ifc_type", "")
    return IFC_TYPE_TO_LAYER.get(ifc_type, "0")


def _add_box_plan(msp, mesh):
    """Add a box mesh as a rectangle in plan view (XY projection).

    Box meshes have ifc_center=[cx, cy, cz] and ifc_size=[sx, sy, sz]
    in Z-up IFC coordinates.  Plan view = XY plane.
    """
    center = mesh.get("ifc_center")
    size = mesh.get("ifc_size")
    if not center or not size:
        return

    cx, cy, cz = center
    sx, sy, sz = size

    # Half-extents in plan
    hx = sx / 2.0
    hy = sy / 2.0

    points = [
        (cx - hx, cy - hy),
        (cx + hx, cy - hy),
        (cx + hx, cy + hy),
        (cx - hx, cy + hy),
    ]

    layer = _layer_for(mesh)
    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})


def _add_winder_polygon_plan(msp, mesh):
    """Add a winder_polygon mesh as a closed polygon in plan view.

    profile is already a list of [x, y] points in the plan plane.
    """
    profile = mesh.get("profile")
    if not profile or len(profile) < 3:
        return

    points = [(p[0], p[1]) for p in profile]
    layer = _layer_for(mesh)
    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})


def _add_stringer_plan(msp, mesh):
    """Add a stringer-type mesh as a rectangle in plan view.

    Stringer meshes define a 2D profile in a vertical plane plus an
    extrusion position and thickness.  In plan view we project to a
    rectangle spanning the Y-range (or X-range) of the profile
    and the thickness direction.
    """
    profile = mesh.get("profile")
    thickness = mesh.get("thickness", 0)
    if not profile or thickness == 0:
        return

    layer = _layer_for(mesh)
    axis = mesh.get("axis")

    if axis == "y":
        # Profile is in the X-Z plane, extruded along Y
        # Plan view: rectangle from (min_x, y) to (max_x, y + thickness)
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
        # Profile is in the Y-Z plane, extruded along X
        # Plan view: rectangle from (x, min_y) to (x + thickness, max_y)
        ys = [p[0] for p in profile]
        x_start = mesh.get("x", 0)
        min_y, max_y = min(ys), max(ys)
        points = [
            (x_start, min_y),
            (x_start + thickness, min_y),
            (x_start + thickness, max_y),
            (x_start, max_y),
        ]

    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})


def meshes_to_dxf(meshes, params):
    """Generate a DXF plan-view file from stair preview meshes.

    Args:
        meshes: list of mesh dicts from generate_preview_geometry()
        params: raw parameter dict from the UI

    Returns:
        str: path to temporary DXF file
    """
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM

    # Set up linetypes
    doc.linetypes.add("DASHED", pattern=[10.0, 6.35, -3.175])

    # Set up layers
    for name, props in LAYERS.items():
        doc.layers.add(name, color=props["color"], linetype=props["linetype"])

    msp = doc.modelspace()

    for mesh in meshes:
        mtype = mesh.get("type", "")

        if mtype == "box":
            _add_box_plan(msp, mesh)
        elif mtype == "winder_polygon":
            _add_winder_polygon_plan(msp, mesh)
        elif mtype == "stringer":
            _add_stringer_plan(msp, mesh)

    # Write to temp file
    fd, filepath = tempfile.mkstemp(suffix=".dxf")
    os.close(fd)
    doc.saveas(filepath)
    return filepath
