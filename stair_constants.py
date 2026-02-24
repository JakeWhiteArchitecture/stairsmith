"""
Stair Preview Engine — shared constants, parameter parsing, and _box_mesh helper.
"""


STRINGER_THICKNESS = 32.0        # mm
STRINGER_HEIGHT = 275.0          # mm
STRINGER_PITCH_OFFSET = 25.0     # mm – stringer top sits this far above the pitch line
STRINGER_DROP = 75.0             # landing stringer top above tread plane
WALL_STRINGER_EXTENSION = 70.0   # mm – stringer extends past nosing when wall (no newel)
STRINGER_COLOR = "#b5a48a"

HANDRAIL_WIDTH = 70.0            # mm
HANDRAIL_HEIGHT = 40.0           # mm
HANDRAIL_RISE = 900.0            # mm – vertical from nosing pitch line to top of handrail
HANDRAIL_COLOR = "#8B7355"

SPINDLE_SIZE = 32.0              # mm – square cross-section
SPINDLE_MAX_GAP = 99.0           # mm – max clear gap between spindles (building regs: 100mm sphere)

_BOX_COLOR_TO_IFC = {
    "#c8a87c": "tread",       # treads, landings, thresholds (override for landing/threshold)
    "#e8dcc8": "riser",       # risers
    "#d4a574": "winder_tread",
    "#8B7355": "newel",       # newel posts
}


def _box_mesh(x, y, z, w, d, h, color, name="", ifc_type=""):
    """Create a box mesh definition for Three.js.

    Stores both Three.js coords (Y-up) and IFC-native coords (Z-up) so
    the mesh list can drive both the preview and the IFC converter.
    ifc_type is auto-inferred from color if not provided.
    """
    if not ifc_type:
        ifc_type = _BOX_COLOR_TO_IFC.get(color, "")
    return {
        "type": "box",
        "position": [x, z, -y],  # swap Y/Z for Three.js (Y-up)
        "size": [w, h, d],
        "ifc_center": [x, y, z],  # IFC Z-up native coords
        "ifc_size": [w, d, h],    # [width_x, depth_y, height_z]
        "color": color,
        "name": name,
        "ifc_type": ifc_type,
    }


def _parse(params):
    p = {}
    p["floor_to_floor"] = float(params.get("floor_to_floor", 2700))
    p["stair_width"] = float(params.get("stair_width", 900))
    p["num_risers"] = int(params.get("num_risers", 14))
    p["going"] = float(params.get("going", 227))
    p["tread_thickness"] = float(params.get("tread_thickness", 22))
    p["riser_thickness"] = float(params.get("riser_thickness", 9))
    p["nosing"] = float(params.get("nosing", 16))
    p["staircase_type"] = params.get("staircase_type", "double_winder")
    p["turn1_direction"] = params.get("turn1_direction", "left")
    p["turn1_winders"] = 3  # Building regs: 90° corners must be triple winder or flat landing
    p["turn2_direction"] = params.get("turn2_direction", "left")
    p["turn2_winders"] = 3  # Building regs: 90° corners must be triple winder or flat landing
    p["turn1_enabled"] = bool(params.get("turn1_enabled", False))
    p["turn2_enabled"] = bool(params.get("turn2_enabled", False))
    p["newel_size"] = float(params.get("newel_size", 90))
    # Winder X: distance from internal corner of newel along post face (min 25, max newel_size)
    raw_x = float(params.get("winder_x", 25))
    p["winder_x"] = max(25.0, min(p["newel_size"], raw_x))
    # Winder Y: going from X endpoint toward flight (min 50)
    raw_y = float(params.get("winder_y", 50))
    p["winder_y"] = max(50.0, raw_y)
    # Same X/Y applies to both turns
    p["winder_x2"] = p["winder_x"]
    p["winder_y2"] = p["winder_y"]
    p["threshold_depth"] = float(params.get("threshold_depth", 100))
    # Flight distribution overrides (-1 = auto / equal split)
    # JS may send null (Python None) when value is NaN; treat as -1 (auto).
    _f1 = params.get("flight1_steps", -1)
    _f2 = params.get("flight2_steps", -1)
    _f3 = params.get("flight3_steps", -1)
    p["flight1_steps"] = int(_f1) if _f1 is not None else -1
    p["flight2_steps"] = int(_f2) if _f2 is not None else -1
    p["flight3_steps"] = int(_f3) if _f3 is not None else -1
    # Balustrade dimensions
    p["handrail_width"] = float(params.get("handrail_width", 70))
    p["handrail_height"] = float(params.get("handrail_height", 40))
    p["handrail_rise"] = float(params.get("handrail_rise", 900))
    p["baserail_width"] = float(params.get("baserail_width", 50))
    p["baserail_height"] = float(params.get("baserail_height", 30))
    p["spindle_width"] = float(params.get("spindle_width", 32))
    p["left_condition"] = params.get("left_condition", "balustrade")
    p["right_condition"] = params.get("right_condition", "wall")
    p["rise"] = p["floor_to_floor"] / p["num_risers"]
    p["num_treads"] = p["num_risers"] - 1
    p["num_risers_val"] = p["num_risers"]
    return p
