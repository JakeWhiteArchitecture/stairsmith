"""
Stair Preview Engine — Client-side geometry module for Pyodide.

Pure Python (no Flask, no IfcOpenShell) — generates Three.js-compatible
mesh data and runs building-regulations checks.
"""

import math


def generate_preview_geometry(params):
    """
    Generate Three.js-compatible geometry data for live preview.
    Returns lists of meshes with vertices and faces.
    """
    import math

    p = _parse(params)
    meshes = []

    stair_type = p["staircase_type"]
    width = p["stair_width"]
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    num_risers = p["num_risers"]

    if stair_type == "straight":
        meshes = _preview_straight(p)
    elif stair_type == "single_winder":
        meshes = _preview_single_winder(p)
    elif stair_type == "double_winder":
        meshes = _preview_double_winder(p)

    return meshes


def _parse(params):
    p = {}
    p["floor_to_floor"] = float(params.get("floor_to_floor", 2700))
    p["stair_width"] = float(params.get("stair_width", 865))
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
    p["turn1_enabled"] = bool(params.get("turn1_enabled", True))
    p["turn2_enabled"] = bool(params.get("turn2_enabled", True))
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
    p["flight1_steps"] = int(params.get("flight1_steps", -1))
    p["flight2_steps"] = int(params.get("flight2_steps", -1))
    p["flight3_steps"] = int(params.get("flight3_steps", -1))
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


STRINGER_THICKNESS = 32.0        # mm
STRINGER_HEIGHT = 275.0          # mm
STRINGER_PITCH_OFFSET = 25.0     # mm – stringer top sits this far above the pitch line
STRINGER_DROP = 75.0                    # landing stringer top above tread plane
WALL_STRINGER_EXTENSION = 70.0          # mm – stringer extends past nosing when wall (no newel)
STRINGER_COLOR = "#b5a48a"

HANDRAIL_WIDTH = 70.0            # mm
HANDRAIL_HEIGHT = 40.0           # mm
HANDRAIL_RISE = 900.0            # mm – vertical from nosing pitch line to top of handrail
HANDRAIL_COLOR = "#8B7355"


def _stringer_flight_y(x_pos, y_start, z_start, y_end, z_end, name="Stringer", ifc_type="stringer", clip_z_min=None):
    """Stringer along a flight that runs in the Y direction.

    Returns a stringer mesh dict.  The profile is a parallelogram in the
    Y-Z plane, extruded by STRINGER_THICKNESS in X centred on *x_pos*.

    If *clip_z_min* is set the profile is clipped so nothing extends below
    that Z value (e.g. ground-floor level = 0).
    """
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off
    pts = [
        [y_start, z_start - drop],
        [y_end,   z_end - drop],
        [y_end,   z_end + off],
        [y_start, z_start + off],
    ]
    if clip_z_min is not None:
        clipped = []
        n = len(pts)
        for i in range(n):
            curr = pts[i]
            nxt = pts[(i + 1) % n]
            c_in = curr[1] >= clip_z_min
            n_in = nxt[1] >= clip_z_min
            if c_in:
                clipped.append(curr)
            if c_in != n_in:
                dy = nxt[0] - curr[0]
                dz = nxt[1] - curr[1]
                if abs(dz) > 1e-9:
                    t = (clip_z_min - curr[1]) / dz
                    clipped.append([curr[0] + t * dy, clip_z_min])
        if clipped:
            pts = clipped
    profile = pts
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }


def _stringer_flight_x(y_pos, x_start, z_start, x_end, z_end, name="Stringer", ifc_type="stringer"):
    """Stringer along a flight that runs in the X direction.

    Profile is in the X-Z plane, extruded by STRINGER_THICKNESS in Y
    centred on *y_pos*.
    """
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off
    profile = [
        [x_start, z_start - drop],
        [x_end,   z_end - drop],
        [x_end,   z_end + off],
        [x_start, z_start + off],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }


def _stringer_landing_y(x_pos, y_start, y_end, z, name="Landing Stringer", ifc_type="stringer"):
    """Flat (horizontal) stringer across a landing, running in Y.

    The stringer top sits at base rail bottom (to support it properly).
    """
    z_top = z + STRINGER_DROP + STRINGER_PITCH_OFFSET
    z_bot = z_top - STRINGER_HEIGHT
    profile = [
        [y_start, z_bot],
        [y_end,   z_bot],
        [y_end,   z_top],
        [y_start, z_top],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }


def _stringer_landing_x(y_pos, x_start, x_end, z, name="Landing Stringer", ifc_type="stringer"):
    """Flat (horizontal) stringer across a landing, running in X.

    The stringer top sits at base rail bottom (to support it properly).
    """
    z_top = z + STRINGER_DROP + STRINGER_PITCH_OFFSET
    z_bot = z_top - STRINGER_HEIGHT
    profile = [
        [x_start, z_bot],
        [x_end,   z_bot],
        [x_end,   z_top],
        [x_start, z_top],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }


SPINDLE_SIZE = 32.0              # mm – square cross-section
SPINDLE_MAX_GAP = 99.0           # mm – max clear gap between spindles (building regs: 100mm sphere)


def _handrail_flight_y(x_pos, y_start, z_start, y_end, z_end, name="Handrail", **kw):
    """Pitched handrail along Y.  z_start/z_end are nosing pitch-line z values."""
    w = kw.get("hr_width", HANDRAIL_WIDTH)
    h = kw.get("hr_height", HANDRAIL_HEIGHT)
    r = kw.get("hr_rise", HANDRAIL_RISE)
    profile = [
        [y_start, z_start + r - h],
        [y_end,   z_end + r - h],
        [y_end,   z_end + r],
        [y_start, z_start + r],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "handrail",
    }


def _handrail_flight_x(y_pos, x_start, z_start, x_end, z_end, name="Handrail", **kw):
    """Pitched handrail along X.  z_start/z_end are nosing pitch-line z values."""
    w = kw.get("hr_width", HANDRAIL_WIDTH)
    h = kw.get("hr_height", HANDRAIL_HEIGHT)
    r = kw.get("hr_rise", HANDRAIL_RISE)
    profile = [
        [x_start, z_start + r - h],
        [x_end,   z_end + r - h],
        [x_end,   z_end + r],
        [x_start, z_start + r],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "handrail",
    }


def _baserail_flight_y(x_pos, y_start, z_start, y_end, z_end, name="Baserail", **kw):
    """Base rail along Y sitting on top of the inner stringer."""
    w = kw.get("br_width", HANDRAIL_WIDTH)
    h = kw.get("br_height", HANDRAIL_HEIGHT)
    bot = STRINGER_PITCH_OFFSET
    top = STRINGER_PITCH_OFFSET + h
    profile = [
        [y_start, z_start + bot],
        [y_end,   z_end + bot],
        [y_end,   z_end + top],
        [y_start, z_start + top],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "baserail",
    }


def _baserail_flight_x(y_pos, x_start, z_start, x_end, z_end, name="Baserail", **kw):
    """Base rail along X sitting on top of the inner stringer."""
    w = kw.get("br_width", HANDRAIL_WIDTH)
    h = kw.get("br_height", HANDRAIL_HEIGHT)
    bot = STRINGER_PITCH_OFFSET
    top = STRINGER_PITCH_OFFSET + h
    profile = [
        [x_start, z_start + bot],
        [x_end,   z_end + bot],
        [x_end,   z_end + top],
        [x_start, z_start + top],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "baserail",
    }


def _handrail_landing_y(x_pos, y_start, y_end, z, name="Landing Handrail", **kw):
    """Flat (horizontal) handrail across a landing, running in Y.

    z is the landing tread plane height.
    Handrail sits at landing_stringer_top + handrail_rise.
    """
    w = kw.get("hr_width", HANDRAIL_WIDTH)
    h = kw.get("hr_height", HANDRAIL_HEIGHT)
    r = kw.get("hr_rise", HANDRAIL_RISE)
    # Landing stringer top is at z + STRINGER_DROP
    z_hr_bot = z + STRINGER_DROP + r - h
    z_hr_top = z + STRINGER_DROP + r
    profile = [
        [y_start, z_hr_bot],
        [y_end, z_hr_bot],
        [y_end, z_hr_top],
        [y_start, z_hr_top],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "handrail",
    }


def _handrail_landing_x(y_pos, x_start, x_end, z, name="Landing Handrail", **kw):
    """Flat (horizontal) handrail across a landing, running in X.

    z is the landing tread plane height.
    Handrail sits at landing_stringer_top + handrail_rise.
    """
    w = kw.get("hr_width", HANDRAIL_WIDTH)
    h = kw.get("hr_height", HANDRAIL_HEIGHT)
    r = kw.get("hr_rise", HANDRAIL_RISE)
    # Landing stringer top is at z + STRINGER_DROP
    z_hr_bot = z + STRINGER_DROP + r - h
    z_hr_top = z + STRINGER_DROP + r
    profile = [
        [x_start, z_hr_bot],
        [x_end, z_hr_bot],
        [x_end, z_hr_top],
        [x_start, z_hr_top],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "handrail",
    }


def _baserail_landing_y(x_pos, y_start, y_end, z, name="Landing Baserail", **kw):
    """Flat (horizontal) baserail across a landing, running in Y."""
    w = kw.get("br_width", HANDRAIL_WIDTH)
    h = kw.get("br_height", HANDRAIL_HEIGHT)
    z_top = z + STRINGER_DROP
    bot = STRINGER_PITCH_OFFSET
    top = STRINGER_PITCH_OFFSET + h
    profile = [
        [y_start, z_top + bot],
        [y_end, z_top + bot],
        [y_end, z_top + top],
        [y_start, z_top + top],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "baserail",
    }


def _baserail_landing_x(y_pos, x_start, x_end, z, name="Landing Baserail", **kw):
    """Flat (horizontal) baserail across a landing, running in X."""
    w = kw.get("br_width", HANDRAIL_WIDTH)
    h = kw.get("br_height", HANDRAIL_HEIGHT)
    z_top = z + STRINGER_DROP
    bot = STRINGER_PITCH_OFFSET
    top = STRINGER_PITCH_OFFSET + h
    profile = [
        [x_start, z_top + bot],
        [x_end, z_top + bot],
        [x_end, z_top + top],
        [x_start, z_top + top],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "baserail",
    }


def _spindles_flight_y(x_pos, y_start, z_start, y_end, z_end, name_prefix="Spindle", **kw):
    """Spindles along a Y-direction flight with pitched top/bottom surfaces.

    Gaps between spindles (and between spindles and newel post faces at each
    end) are all equal and as close to 99 mm as possible without exceeding it.
    Each spindle is a parallelogram in the Y-Z plane (sloped to match pitch),
    extruded by spindle_size in X.
    """
    import math
    meshes = []
    sp = kw.get("spindle_size", SPINDLE_SIZE)
    br_h = kw.get("br_height", HANDRAIL_HEIGHT)
    hr_h = kw.get("hr_height", HANDRAIL_HEIGHT)
    hr_r = kw.get("hr_rise", HANDRAIL_RISE)
    br_top_off = STRINGER_PITCH_OFFSET + br_h
    hr_bot_off = hr_r - hr_h
    dy = y_end - y_start
    length = abs(dy)
    if length < 1e-9:
        return meshes
    # k spindles produce k+1 equal gaps: gap = (L - k*sp) / (k+1)
    # We need gap <= 99, so k >= ceil((L - 99) / (99 + sp))
    k = max(0, math.ceil((length - SPINDLE_MAX_GAP) / (SPINDLE_MAX_GAP + sp)))
    if k == 0:
        return meshes
    gap = (length - k * sp) / (k + 1)
    first_centre = gap + sp / 2
    centre_step = gap + sp
    slope = (z_end - z_start) / dy  # dz/dy — pitch slope
    dz_half = slope * sp / 2
    for i in range(k):
        pos = first_centre + i * centre_step
        t = pos / length
        y = y_start + t * dy
        z = z_start + t * (z_end - z_start)
        z_bot = z + br_top_off
        z_top = z + hr_bot_off
        if z_top - z_bot > sp:
            meshes.append({
                "type": "stringer",
                "profile": [
                    [y - sp / 2, z_bot - dz_half],
                    [y + sp / 2, z_bot + dz_half],
                    [y + sp / 2, z_top + dz_half],
                    [y - sp / 2, z_top - dz_half],
                ],
                "x": x_pos - sp / 2,
                "thickness": sp,
                "color": HANDRAIL_COLOR,
                "name": f"{name_prefix} {i+1}",
                "ifc_type": "spindle",
            })
    return meshes


def _spindles_flight_x(y_pos, x_start, z_start, x_end, z_end, name_prefix="Spindle", **kw):
    """Spindles along an X-direction flight with pitched top/bottom surfaces."""
    import math
    meshes = []
    sp = kw.get("spindle_size", SPINDLE_SIZE)
    br_h = kw.get("br_height", HANDRAIL_HEIGHT)
    hr_h = kw.get("hr_height", HANDRAIL_HEIGHT)
    hr_r = kw.get("hr_rise", HANDRAIL_RISE)
    br_top_off = STRINGER_PITCH_OFFSET + br_h
    hr_bot_off = hr_r - hr_h
    dx = x_end - x_start
    length = abs(dx)
    if length < 1e-9:
        return meshes
    k = max(0, math.ceil((length - SPINDLE_MAX_GAP) / (SPINDLE_MAX_GAP + sp)))
    if k == 0:
        return meshes
    gap = (length - k * sp) / (k + 1)
    first_centre = gap + sp / 2
    centre_step = gap + sp
    slope = (z_end - z_start) / dx  # dz/dx — pitch slope
    dz_half = slope * sp / 2
    for i in range(k):
        pos = first_centre + i * centre_step
        t = pos / length
        x = x_start + t * dx
        z = z_start + t * (z_end - z_start)
        z_bot = z + br_top_off
        z_top = z + hr_bot_off
        if z_top - z_bot > sp:
            meshes.append({
                "type": "stringer",
                "profile": [
                    [x - sp / 2, z_bot - dz_half],
                    [x + sp / 2, z_bot + dz_half],
                    [x + sp / 2, z_top + dz_half],
                    [x - sp / 2, z_top - dz_half],
                ],
                "y": y_pos - sp / 2,
                "thickness": sp,
                "axis": "y",
                "color": HANDRAIL_COLOR,
                "name": f"{name_prefix} {i+1}",
                "ifc_type": "spindle",
            })
    return meshes


def _spindles_landing_y(x_pos, y_start, y_end, z, name_prefix="Landing Spindle", **kw):
    """Vertical spindles along a Y-direction landing (flat/horizontal).

    Spindles run from base rail top to handrail bottom.
    z is the landing tread plane height.
    """
    import math
    meshes = []
    sp = kw.get("spindle_size", SPINDLE_SIZE)
    br_h = kw.get("br_height", HANDRAIL_HEIGHT)
    hr_h = kw.get("hr_height", HANDRAIL_HEIGHT)
    hr_r = kw.get("hr_rise", HANDRAIL_RISE)

    # Baserail and handrail use z + STRINGER_DROP as reference
    z_ref = z + STRINGER_DROP
    z_bot = z_ref + STRINGER_PITCH_OFFSET + br_h  # base rail top
    z_top = z_ref + hr_r - hr_h  # handrail bottom

    dy = y_end - y_start
    length = abs(dy)
    if length < 1e-9 or z_top - z_bot < sp:
        return meshes

    # Calculate number of spindles to keep gaps <= 99mm
    k = max(0, math.ceil((length - SPINDLE_MAX_GAP) / (SPINDLE_MAX_GAP + sp)))
    if k == 0:
        return meshes

    gap = (length - k * sp) / (k + 1)
    first_centre = gap + sp / 2
    centre_step = gap + sp

    for i in range(k):
        pos = first_centre + i * centre_step
        if dy >= 0:
            y = y_start + pos
        else:
            y = y_start - pos

        meshes.append({
            "type": "stringer",
            "profile": [
                [y - sp / 2, z_bot],
                [y + sp / 2, z_bot],
                [y + sp / 2, z_top],
                [y - sp / 2, z_top],
            ],
            "x": x_pos - sp / 2,
            "thickness": sp,
            "color": HANDRAIL_COLOR,
            "name": f"{name_prefix} {i+1}",
            "ifc_type": "spindle",
        })
    return meshes


def _spindles_landing_x(y_pos, x_start, x_end, z, name_prefix="Landing Spindle", **kw):
    """Vertical spindles along an X-direction landing (flat/horizontal).

    Spindles run from base rail top to handrail bottom.
    z is the landing tread plane height.
    """
    import math
    meshes = []
    sp = kw.get("spindle_size", SPINDLE_SIZE)
    br_h = kw.get("br_height", HANDRAIL_HEIGHT)
    hr_h = kw.get("hr_height", HANDRAIL_HEIGHT)
    hr_r = kw.get("hr_rise", HANDRAIL_RISE)

    # Baserail and handrail use z + STRINGER_DROP as reference
    z_ref = z + STRINGER_DROP
    z_bot = z_ref + STRINGER_PITCH_OFFSET + br_h  # base rail top
    z_top = z_ref + hr_r - hr_h  # handrail bottom

    dx = x_end - x_start
    length = abs(dx)
    if length < 1e-9 or z_top - z_bot < sp:
        return meshes

    # Calculate number of spindles to keep gaps <= 99mm
    k = max(0, math.ceil((length - SPINDLE_MAX_GAP) / (SPINDLE_MAX_GAP + sp)))
    if k == 0:
        return meshes

    gap = (length - k * sp) / (k + 1)
    first_centre = gap + sp / 2
    centre_step = gap + sp

    for i in range(k):
        pos = first_centre + i * centre_step
        if dx >= 0:
            x = x_start + pos
        else:
            x = x_start - pos

        meshes.append({
            "type": "stringer",
            "axis": "y",
            "profile": [
                [x - sp / 2, z_bot],
                [x + sp / 2, z_bot],
                [x + sp / 2, z_top],
                [x - sp / 2, z_top],
            ],
            "y": y_pos - sp / 2,
            "thickness": sp,
            "color": HANDRAIL_COLOR,
            "name": f"{name_prefix} {i+1}",
            "ifc_type": "spindle",
        })
    return meshes


def _stringer_flight_y_notched(x_pos, y_start, z_start, y_end, z_end, ftf, y_back, tread_t,
                               name="Stringer", ifc_type="stringer"):
    """Pitched stringer along Y with a notch at the top for landing threshold.

    The stringer bottom continues at pitch to y_end (riser back face), then a
    vertical cut rises to ftf - tread_t (threshold underside).  The overrun
    extends to y_back with its top flush with the pitched stringer surface.
    """
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off
    overrun_bot = ftf - tread_t
    # Extend pitch line to y_back so overrun top is flush with stringer surface
    dy = y_end - y_start
    slope = (z_end - z_start) / dy if dy != 0 else 0
    z_back_top = z_end + off + slope * (y_back - y_end)
    profile = [
        [y_start, z_start - drop],      # 0  bottom at start
        [y_end,   z_end - drop],         # 1  bottom at riser back
        [y_end,   overrun_bot],          # 2  vertical cut to threshold underside
        [y_back,  overrun_bot],          # 3  horizontal to threshold back
        [y_back,  z_back_top],           # 4  up to pitch line at threshold back
        [y_start, z_start + off],        # 5  pitch line back to start
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }


def _stringer_flight_x_notched(y_pos, x_start, z_start, x_end, z_end, ftf, x_back, tread_t,
                               name="Stringer", ifc_type="stringer"):
    """Pitched stringer along X with a notch at the top for landing threshold."""
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off
    overrun_bot = ftf - tread_t
    dx = x_end - x_start
    slope = (z_end - z_start) / dx if dx != 0 else 0
    z_back_top = z_end + off + slope * (x_back - x_end)
    profile = [
        [x_start, z_start - drop],
        [x_end,   z_end - drop],
        [x_end,   overrun_bot],
        [x_back,  overrun_bot],
        [x_back,  z_back_top],
        [x_start, z_start + off],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }


def _winder_riser_meshes(corner_x, corner_y, ns, width, turn_dir,
                         num_winders, winder_start_riser, rise, tread_t,
                         riser_t, nosing=0, rotation=0, winder_x=25.0):
    """Generate riser meshes between consecutive winder treads.

    Returns a list of winder_polygon mesh dicts (thin strips along division
    lines, extruded vertically by riser_h).
    """
    import math
    if num_winders < 2 or riser_t <= 0:
        return []

    riser_h = rise - tread_t
    hp = ns / 2.0
    x_sign = 1.0 if turn_dir == "left" else -1.0

    pc_x = corner_x + x_sign * hp
    pc_y = corner_y + hp
    wc_x = pc_x - x_sign * winder_x
    wc_y = pc_y - winder_x

    outer_f1_x = corner_x + x_sign * width
    outer_f2_y = corner_y + width

    mark_a = (pc_x, wc_y)
    mark_b = (wc_x, pc_y)

    angle_step = (math.pi / 2.0) / num_winders
    a_inner_corner = math.atan2(winder_x, winder_x)  # pi/4

    def ray_outer(angle):
        dx = x_sign * math.cos(angle)
        dy = math.sin(angle)
        t_f1 = (outer_f1_x - wc_x) / dx if abs(dx) > 1e-9 else float('inf')
        t_f2 = (outer_f2_y - wc_y) / dy if abs(dy) > 1e-9 else float('inf')
        if t_f1 < 0: t_f1 = float('inf')
        if t_f2 < 0: t_f2 = float('inf')
        t = min(t_f1, t_f2)
        return (wc_x + dx * t, wc_y + dy * t)

    meshes = []
    for j in range(num_winders - 1):
        a_boundary = (j + 1) * angle_step

        # Inner point on post face
        if a_boundary < a_inner_corner - 1e-6:
            inner = mark_a
        elif a_boundary > a_inner_corner + 1e-6:
            inner = mark_b
        else:
            inner = (pc_x, pc_y)

        outer = ray_outer(a_boundary)

        # Division line direction and perpendicular
        lx = outer[0] - inner[0]
        ly = outer[1] - inner[1]
        length = math.sqrt(lx * lx + ly * ly)
        if length < 1e-9:
            continue

        # Unit normal toward upper winder
        unx = x_sign * (-ly / length)
        uny = x_sign * (lx / length)

        # Nosing setback: shift entire riser toward upper winder by nosing,
        # so the nosing of the tread above overhangs past the riser front face.
        # Then the back face is riser_t further toward the upper winder.
        front_off = nosing              # toward upper winder
        back_off = nosing + riser_t     # riser_t past front face

        inner_front = (inner[0] + unx * front_off, inner[1] + uny * front_off)
        inner_back = (inner[0] + unx * back_off, inner[1] + uny * back_off)

        # Clamp inner riser ends to post face, preserving perpendicular
        # distance from the division line by sliding along it.
        post_opp_x = corner_x - x_sign * hp
        def _clamp_to_post(pt, offset):
            ex, ey = pt
            if abs(inner[0] - pc_x) < 1e-6:
                # inner is on Face A — slide along division line to x = pc_x
                if abs(ex - pc_x) > 1e-6 and abs(lx) > 1e-9:
                    base_x = inner[0] + offset * unx
                    base_y = inner[1] + offset * uny
                    t = (pc_x - base_x) / lx
                    ex = pc_x
                    ey = base_y + t * ly
                else:
                    ex = pc_x
                ey = min(ey, pc_y)
            elif abs(inner[1] - pc_y) < 1e-6:
                # inner is on Face B — slide along division line to y = pc_y
                if abs(ey - pc_y) > 1e-6 and abs(ly) > 1e-9:
                    base_x = inner[0] + offset * unx
                    base_y = inner[1] + offset * uny
                    t = (pc_y - base_y) / ly
                    ex = base_x + t * lx
                    ey = pc_y
                else:
                    ey = pc_y
                if x_sign > 0:
                    ex = max(ex, post_opp_x)
                else:
                    ex = min(ex, post_opp_x)
            else:
                # At post corner
                ex = pc_x
                ey = pc_y
            return (ex, ey)
        inner_front = _clamp_to_post(inner_front, front_off)
        inner_back = _clamp_to_post(inner_back, back_off)

        # Trace both outer points along division line to hit the wall
        def _trace_to_wall(pt):
            tf1 = (outer_f1_x - pt[0]) / lx if abs(lx) > 1e-9 else float('inf')
            tf2 = (outer_f2_y - pt[1]) / ly if abs(ly) > 1e-9 else float('inf')
            if tf1 < 0: tf1 = float('inf')
            if tf2 < 0: tf2 = float('inf')
            t = min(tf1, tf2)
            return (pt[0] + lx * t, pt[1] + ly * t)

        outer_front = _trace_to_wall(inner_front)
        outer_back = _trace_to_wall(inner_back)

        # Riser polygon: front face set back by nosing from division line,
        # back face riser_t further, both outer ends flush with wall
        strip = [
            inner_back,     # back face, inner end
            outer_back,     # back face, outer end (on the wall)
            outer_front,    # front face, outer end (on the wall)
            inner_front,    # front face, inner end
        ]

        # Apply rotation if needed (turn 2)
        if rotation != 0:
            rad = math.radians(rotation)
            cos_r = math.cos(rad)
            sin_r = math.sin(rad)
            rotated = []
            for (px, py) in strip:
                dx = px - corner_x
                dy = py - corner_y
                rx = cos_r * dx - sin_r * dy + corner_x
                ry = sin_r * dx + cos_r * dy + corner_y
                rotated.append((rx, ry))
            strip = rotated

        z_bottom = (winder_start_riser + j) * rise
        meshes.append({
            "type": "winder_polygon",
            "profile": [[pt[0], pt[1]] for pt in strip],
            "z": z_bottom,
            "thickness": riser_h,
            "color": "#e8dcc8",
            "name": f"Winder Riser {j+1}",
            "ifc_type": "winder_riser",
        })

    return meshes


def _preview_straight(p):
    import math
    meshes = []
    width = p["stair_width"]
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    num_risers = p["num_risers_val"]

    for i in range(num_treads):
        tread_y = i * going - nosing
        tread_z = (i + 1) * rise - tread_t
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c",
            name=f"Flight 1 Tread {i+1}", ifc_type="tread",
        ))

    riser_h = rise - tread_t
    for i in range(num_risers):
        riser_y = i * going
        riser_z = i * rise
        if riser_t > 0:
            meshes.append(_box_mesh(
                width / 2, riser_y + riser_t / 2, riser_z + riser_h / 2,
                width, riser_t, riser_h, "#e8dcc8",
                name=f"Riser F1-{i+1}", ifc_type="riser",
            ))

    # --- Landing threshold strip ---
    ftf = num_risers * rise
    threshold_d = p["threshold_depth"]
    threshold_y = num_treads * going - nosing            # front (nosing overhang)
    threshold_back = num_treads * going - nosing + threshold_d
    meshes.append(_box_mesh(
        width / 2, threshold_y + threshold_d / 2, ftf - tread_t + tread_t / 2,
        width, threshold_d, tread_t, "#c8a87c",
        name="Threshold", ifc_type="threshold",
    ))

    # --- Stringers and balustrade ---
    nzs = rise * nosing / going
    ns = p["newel_size"]
    hp = ns / 2.0
    y0 = 0.0
    y1 = num_treads * going + riser_t / 2       # flush with riser back face
    y1_nf = num_treads * going                  # non-flushed (at last riser)
    z0 = rise + nzs
    z1 = (num_treads + 1) * rise + nzs + riser_t * rise / (2 * going)
    z1_nf = (num_treads + 1) * rise + nzs

    hr_kw = {"hr_width": p["handrail_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"]}
    br_kw = {"br_width": p["baserail_width"], "br_height": p["baserail_height"]}
    sp_kw = {"spindle_size": p["spindle_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"], "br_height": p["baserail_height"]}

    NEWEL_CAP = 150.0
    hr_rise_val = p["handrail_rise"]
    bottom_post_y = -nosing
    top_post_y = threshold_y

    for side_idx, (x_pos, condition) in enumerate([(0.0, p["left_condition"]), (width, p["right_condition"])]):
        side = "Left" if side_idx == 0 else "Right"
        if condition == "balustrade":
            bot_face_y = bottom_post_y + hp
            top_face_y = top_post_y - hp
            dy = y1 - y0
            # Stringer extends past bottom post toward floor (base extension)
            _slope = (z1 - z0) / (y1 - y0) if abs(y1 - y0) > 1e-9 else 0
            y0_ext = y0 - WALL_STRINGER_EXTENSION
            z0_ext = z0 - WALL_STRINGER_EXTENSION * _slope
            drop = STRINGER_HEIGHT - STRINGER_PITCH_OFFSET
            if z0_ext - drop < 0 and _slope > 1e-9:
                max_ext = (z0 - drop) / _slope
                max_ext = max(0.0, max_ext)
                y0_ext = y0 - max_ext
                z0_ext = z0 - max_ext * _slope
            # Clip handrail/baserail/spindle start at bottom post face
            y0_c, z0_c = y0, z0
            if abs(dy) > 1e-9 and bot_face_y > y0:
                t_c = min(1.0, (bot_face_y - y0) / dy)
                y0_c = y0 + t_c * dy
                z0_c = z0 + t_c * (z1 - z0)
            # Clip end at top post face
            y1_c, z1_c = y1, z1
            if abs(dy) > 1e-9 and top_face_y < y1:
                t_c = max(0.0, (top_face_y - y0) / dy)
                y1_c = y0 + t_c * dy
                z1_c = z0 + t_c * (z1 - z0)
            meshes.append(_stringer_flight_y(x_pos, y0_ext, z0_ext, y1_c, z1_c,
                                             name=f"{side} Stringer F1", clip_z_min=0))
            # Handrail clip (using non-flushed endpoint)
            dy_nf = y1_nf - y0
            y1_hr, z1_hr = y1_nf, z1_nf
            if abs(dy_nf) > 1e-9 and top_face_y < y1_nf:
                t_c = max(0.0, (top_face_y - y0) / dy_nf)
                y1_hr = y0 + t_c * dy_nf
                z1_hr = z0 + t_c * (z1_nf - z0)
            meshes.append(_handrail_flight_y(x_pos, y0_c, z0_c, y1_hr, z1_hr,
                                             name=f"{side} Handrail F1", **hr_kw))
            meshes.append(_baserail_flight_y(x_pos, y0_c, z0_c, y1_c, z1_c,
                                             name=f"{side} Baserail F1", **br_kw))
            if abs(dy_nf) > 1e-9:
                t_sp0 = (bot_face_y - y0) / dy_nf
                t_sp1 = (top_face_y - y0) / dy_nf
                sp_z0 = z0 + t_sp0 * (z1_nf - z0)
                sp_z1 = z0 + t_sp1 * (z1_nf - z0)
                meshes.extend(_spindles_flight_y(x_pos, bot_face_y, sp_z0, top_face_y, sp_z1,
                                                 name_prefix=f"{side} Spindle F1", **sp_kw))
            # Newel posts
            hr_bot = rise + nzs + hr_rise_val
            bot_h = hr_bot + NEWEL_CAP
            meshes.append(_box_mesh(x_pos, bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355",
                                    name=f"{side} Bottom Post", ifc_type="newel"))
            # Top newel extends FROM cutting plane (150mm below stringer bottom) UPWARD
            # Stringer bottom = pitch_line - 250mm
            # Newel bottom = pitch_line - 400mm (150mm below stringer bottom)
            # Newel top = pitch_line + handrail_rise + NEWEL_CAP
            pitch_line = ftf + nzs
            newel_bottom = pitch_line - 400.0
            newel_top = pitch_line + hr_rise_val + NEWEL_CAP
            top_h = newel_top - newel_bottom
            top_z_center = (newel_bottom + newel_top) / 2
            meshes.append(_box_mesh(x_pos, top_post_y, top_z_center, ns, ns, top_h, "#8B7355",
                                    name=f"{side} Top Post", ifc_type="newel"))
        else:
            # Wall condition: notched stringer with base extension (no newel to terminate to)
            _slope = (z1 - z0) / (y1 - y0) if abs(y1 - y0) > 1e-9 else 0
            y0_w = y0 - WALL_STRINGER_EXTENSION
            z0_w = z0 - WALL_STRINGER_EXTENSION * _slope
            # Clip so stringer bottom doesn't go below ground
            drop = STRINGER_HEIGHT - STRINGER_PITCH_OFFSET
            if z0_w - drop < 0 and _slope > 1e-9:
                max_ext = (z0 - drop) / _slope
                max_ext = max(0.0, max_ext)
                y0_w = y0 - max_ext
                z0_w = z0 - max_ext * _slope
            meshes.append(_stringer_flight_y_notched(x_pos, y0_w, z0_w, y1, z1, ftf, threshold_back, tread_t,
                                                     name=f"{side} Stringer F1"))

    return meshes


def _preview_single_winder(p):
    import math
    meshes = []
    width = p["stair_width"]
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    winders = p["turn1_winders"]
    turn_dir = p["turn1_direction"]
    turn1_enabled = p.get("turn1_enabled", True)

    # Balustrade keyword dicts
    hr_kw = {"hr_width": p["handrail_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"]}
    br_kw = {"br_width": p["baserail_width"], "br_height": p["baserail_height"]}
    sp_kw = {"spindle_size": p["spindle_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"], "br_height": p["baserail_height"]}

    # Map left/right conditions to inner/outer based on turn direction
    # Left turn: left (x=0) = inner, right (x=width) = outer
    # Right turn: left (x=0) = outer, right (x=width) = inner
    if p["turn1_direction"] == "left":
        render_inner = p["left_condition"] == "balustrade"
        render_outer = p["right_condition"] == "balustrade"
    else:
        render_inner = p["right_condition"] == "balustrade"
        render_outer = p["left_condition"] == "balustrade"

    actual_winders = winders if turn1_enabled else 0
    straight_treads = num_treads - actual_winders
    # Use custom flight distribution if provided and valid
    f1_ov, f2_ov = p.get("flight1_steps", -1), p.get("flight2_steps", -1)
    if f1_ov >= 0 and f2_ov >= 0 and f1_ov + f2_ov == straight_treads:
        flight1_treads = f1_ov
        flight2_treads = f2_ov
    else:
        flight1_treads = straight_treads // 2
        flight2_treads = straight_treads - flight1_treads

    # Step 3: Calculate offset and half-post
    ns = p["newel_size"]
    hp = ns / 2.0
    wg = compute_winder_geometry(ns, width)
    offset = wg["offset"]
    wx = p["winder_x"]  # distance from internal corner along post face
    wy = p["winder_y"]  # going from X endpoint toward flight

    # Flight shift: X+Y measured from internal corner (at hp above post centre)
    flight1_shift_y = (hp - wx - wy + nosing) if actual_winders > 0 else 0.0
    bottom_post_y = flight1_shift_y - nosing

    # Flight 1 treads
    for i in range(flight1_treads):
        tread_y = i * going - nosing + flight1_shift_y
        tread_z = (i + 1) * rise - tread_t
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c"
        ))

    # Flight 1 risers
    riser_h = rise - tread_t
    for i in range(flight1_treads + 1):
        if riser_t > 0:
            meshes.append(_box_mesh(
                width / 2, i * going + riser_t / 2 + flight1_shift_y, i * rise + riser_h / 2,
                width, riser_t, riser_h, "#e8dcc8"
            ))

    # Winder treads — construction-based profiles
    winder_start_riser = flight1_treads + 1
    corner_y = flight1_treads * going
    corner_x = 0 if turn_dir == "left" else width

    for i in range(actual_winders):
        winder_z = (winder_start_riser + i) * rise - tread_t
        profile = _winder_profiles_from_construction(
            corner_x, corner_y, p["newel_size"], width,
            turn_dir, i, actual_winders,
            riser_extension=riser_t + nosing,
            flight_extension=wx + wy - 2 * hp,
            winder_x=wx)
        meshes.append({
            "type": "winder_polygon",
            "profile": [[pt[0], pt[1]] for pt in profile],
            "z": winder_z,
            "thickness": tread_t,
            "color": "#d4a574",
            "name": f"Winder {i+1}",
            "ifc_type": "winder_tread",
        })

    # Winder risers (between consecutive winder treads)
    meshes.extend(_winder_riser_meshes(
        corner_x, corner_y, ns, width, turn_dir,
        actual_winders, winder_start_riser, rise, tread_t, riser_t,
        nosing=nosing, winder_x=wx))

    # Landing tread when winders are off
    if actual_winders == 0:
        landing_z = winder_start_riser * rise - tread_t
        # Both nosing edges centred on the newel post.
        # Departure side extends under flight 2's first riser by (nosing + riser_t).
        ext = nosing + riser_t
        landing_w = width + ext
        if turn_dir == "left":
            landing_cx = (width - ext) / 2
        else:
            landing_cx = (width + ext) / 2
        meshes.append(_box_mesh(
            landing_cx,
            corner_y + width / 2,
            landing_z + tread_t / 2,
            landing_w, width, tread_t, "#c8a87c",
            name="Landing", ifc_type="landing",
        ))

    # Flight 2 treads (perpendicular, offset by X+Y from internal corner)
    flight2_start_riser = winder_start_riser + actual_winders
    # When winders are off, the landing consumes 1 rise — shift flight 2 up
    if actual_winders == 0:
        flight2_start_riser += 1
        flight2_treads = max(0, flight2_treads - 1)
    winder_offset = (wx + wy - hp) if actual_winders > 0 else 0.0
    flight2_shift = winder_offset + nosing + riser_t / 2
    for i in range(flight2_treads):
        tread_z = (flight2_start_riser + i) * rise - tread_t
        if turn_dir == "left":
            tread_x = -(i * going) - going / 2 + nosing / 2 - flight2_shift
        else:
            tread_x = width + i * going + going / 2 - nosing / 2 + flight2_shift
        meshes.append(_box_mesh(
            tread_x, corner_y + width / 2, tread_z + tread_t / 2,
            going + nosing + riser_t, width, tread_t, "#c8a87c"
        ))

    # Flight 2 risers (perpendicular — thin in X, spanning width in Y)
    if riser_t > 0:
        for i in range(flight2_treads + 1):
            riser_z = (flight2_start_riser + i - 1) * rise + riser_h / 2
            if turn_dir == "left":
                riser_x = -(i * going) - winder_offset - nosing - riser_t / 2
            else:
                riser_x = width + i * going + winder_offset + nosing + riser_t / 2
            meshes.append(_box_mesh(
                riser_x, corner_y + width / 2, riser_z,
                riser_t, width, riser_h, "#e8dcc8"
            ))

    # --- Landing threshold strip ---
    ftf = (num_treads + 1) * rise
    threshold_d = p["threshold_depth"]
    if turn_dir == "left":
        thresh_front = -(flight2_treads * going) - winder_offset + nosing
        thresh_back = thresh_front - threshold_d
    else:
        thresh_front = width + flight2_treads * going + winder_offset - nosing
        thresh_back = thresh_front + threshold_d
    meshes.append(_box_mesh(
        (thresh_front + thresh_back) / 2, corner_y + width / 2, ftf - tread_t / 2,
        threshold_d, width, tread_t, "#c8a87c",
        name="Threshold", ifc_type="threshold",
    ))

    # --- Balustrade helpers ---
    c_ns = max(ns, 100.0) if (flight1_treads == 0 or flight2_treads == 0) else ns
    c_hp = c_ns / 2.0
    top_post_x = thresh_front

    # --- Stringers (only for flat landings) ---
    if actual_winders == 0:
        # Flight 1: runs along +Y. Inner side = corner_x (0 for left, width for right),
        # outer side = width - corner_x.
        inner_x = corner_x  # 0 for left, width for right
        outer_x = width - corner_x  # width for left, 0 for right
        f1_y0 = flight1_shift_y  # first riser Y
        f1_y1 = flight1_treads * going + flight1_shift_y  # last riser Y
        nzs = rise * nosing / going  # nosing z-shift: pitch line offset at nosing vs riser
        f1_z0 = rise + nzs
        f1_z1 = (flight1_treads + 1) * rise + nzs

        landing_z_base = winder_start_riser * rise
        land_top = landing_z_base + STRINGER_DROP
        # Extend outer flight 1 along pitch until top edge meets landing stringer top
        z_ext = land_top - STRINGER_PITCH_OFFSET
        dy = f1_y1 - f1_y0
        dz = f1_z1 - f1_z0
        f1_y1_ext = f1_y1 + (z_ext - f1_z1) * dy / dz if abs(dz) > 1e-9 else f1_y1

        # Flight 2 coordinates + outer extension
        inner_y = corner_y
        outer_y = corner_y + width
        if turn_dir == "left":
            f2_x0 = -winder_offset - nosing - riser_t / 2
            f2_x1 = -(flight2_treads * going) - winder_offset - nosing - riser_t / 2
        else:
            f2_x0 = width + winder_offset + nosing + riser_t / 2
            f2_x1 = width + flight2_treads * going + winder_offset + nosing + riser_t / 2
        f2_z0 = flight2_start_riser * rise + nzs
        f2_z1 = (flight2_start_riser + flight2_treads) * rise + nzs
        z_ext2 = land_top - STRINGER_PITCH_OFFSET
        dx2 = f2_x1 - f2_x0
        dz2 = f2_z1 - f2_z0
        f2_x0_ext = f2_x0 + (z_ext2 - f2_z0) * dx2 / dz2 if abs(dz2) > 1e-9 else f2_x0

        # Flight 1 stringers
        bot_face_y = bottom_post_y + hp
        dy1 = f1_y1 - f1_y0
        if flight1_treads > 0:
            if render_inner:
                f1_y0_c, f1_z0_c = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_c = f1_y0 + t_c * dy1
                    f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
                meshes.append(_stringer_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1))
                meshes.append(_handrail_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1, **hr_kw))
                meshes.append(_baserail_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1, **br_kw))
                c_face_y = corner_y - c_hp
                if abs(dy1) > 1e-9:
                    t_sp = (c_face_y - f1_y0) / dy1
                    f1_sp_z1 = f1_z0 + t_sp * (f1_z1 - f1_z0)
                else:
                    f1_sp_z1 = f1_z1
                meshes.extend(_spindles_flight_y(inner_x, f1_y0_c, f1_z0_c, c_face_y, f1_sp_z1, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(inner_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))
            if render_outer:
                # Outer flight 1: clipped at outer bottom/pitch-change newel faces
                f1_y0_oc, f1_z0_oc = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_oc = f1_y0 + t_c * dy1
                    f1_z0_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
                meshes.append(_stringer_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1))
                meshes.append(_handrail_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **hr_kw))
                meshes.append(_baserail_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **br_kw))
                # Spindles: from bottom post face to pitch-change newel face (at f1_y1)
                pc_face_y = f1_y1 - hp  # pitch-change newel -Y face
                if abs(dy1) > 1e-9:
                    t_sp = (pc_face_y - f1_y0) / dy1
                    f1_sp_z1 = f1_z0 + t_sp * (f1_z1 - f1_z0)
                else:
                    f1_sp_z1 = f1_z1
                meshes.extend(_spindles_flight_y(outer_x, f1_y0_oc, f1_z0_oc, pc_face_y, f1_sp_z1, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(outer_x, f1_y0_w, f1_z0_w, f1_y1_ext, z_ext, clip_z_min=0))

        # Landing flat stringers — outer endpoints linked to flight stringer extensions
        st2 = STRINGER_THICKNESS / 2
        if turn_dir == "left":
            meshes.append(_stringer_landing_x(corner_y, f2_x0, inner_x, landing_z_base))
            # Outer landing stringers, handrails, and baserails
            meshes.append(_stringer_landing_y(outer_x, f1_y1_ext, corner_y + width + st2, landing_z_base))
            meshes.append(_stringer_landing_x(corner_y + width, f2_x0_ext, outer_x - st2, landing_z_base))
            if render_outer:
                # Add handrails and baserails for landing when balustrade is present
                meshes.append(_handrail_landing_y(outer_x, f1_y1_ext, corner_y + width + st2, landing_z_base, **hr_kw))
                meshes.append(_handrail_landing_x(corner_y + width, f2_x0_ext, outer_x - st2, landing_z_base, **hr_kw))
                meshes.append(_baserail_landing_y(outer_x, f1_y1_ext, corner_y + width + st2, landing_z_base, **br_kw))
                meshes.append(_baserail_landing_x(corner_y + width, f2_x0_ext, outer_x - st2, landing_z_base, **br_kw))
                # Add spindles for landing
                meshes.extend(_spindles_landing_y(outer_x, f1_y1_ext, corner_y + width + st2, landing_z_base, **sp_kw))
                meshes.extend(_spindles_landing_x(corner_y + width, f2_x0_ext, outer_x - st2, landing_z_base, **sp_kw))
        else:
            meshes.append(_stringer_landing_x(corner_y, inner_x, f2_x0, landing_z_base))
            # Outer landing stringers, handrails, and baserails
            meshes.append(_stringer_landing_y(outer_x, f1_y1_ext, corner_y + width + st2, landing_z_base))
            meshes.append(_stringer_landing_x(corner_y + width, outer_x + st2, f2_x0_ext, landing_z_base))
            if render_outer:
                # Add handrails and baserails for landing when balustrade is present
                meshes.append(_handrail_landing_y(outer_x, f1_y1_ext, corner_y + width + st2, landing_z_base, **hr_kw))
                meshes.append(_handrail_landing_x(corner_y + width, outer_x + st2, f2_x0_ext, landing_z_base, **hr_kw))
                meshes.append(_baserail_landing_y(outer_x, f1_y1_ext, corner_y + width + st2, landing_z_base, **br_kw))
                meshes.append(_baserail_landing_x(corner_y + width, outer_x + st2, f2_x0_ext, landing_z_base, **br_kw))
                # Add spindles for landing
                meshes.extend(_spindles_landing_y(outer_x, f1_y1_ext, corner_y + width + st2, landing_z_base, **sp_kw))
                meshes.extend(_spindles_landing_x(corner_y + width, outer_x + st2, f2_x0_ext, landing_z_base, **sp_kw))

        # Flight 2 stringers (notched for threshold, flush with riser back)
        if flight2_treads > 0:
            z_fl = riser_t * rise / (2 * going)
            f2_x1_fl = f2_x1 + (-riser_t / 2 if turn_dir == "left" else riser_t / 2)
            f2_z1_fl = f2_z1 + z_fl
            if turn_dir == "left":
                top_face_x = top_post_x + hp
                c_face_x = corner_x - c_hp
            else:
                top_face_x = top_post_x - hp
                c_face_x = corner_x + c_hp
            if render_inner:
                dx_s = f2_x1_fl - f2_x0
                f2_x1_c, f2_z1_c = f2_x1_fl, f2_z1_fl
                if abs(dx_s) > 1e-9:
                    t_c = max(0.0, min(1.0, (top_face_x - f2_x0) / dx_s))
                    f2_x1_c = f2_x0 + t_c * dx_s
                    f2_z1_c = f2_z0 + t_c * (f2_z1_fl - f2_z0)
                meshes.append(_stringer_flight_x(inner_y, f2_x0, f2_z0, f2_x1_c, f2_z1_c))
                dx_h = f2_x1 - f2_x0
                f2_x1_hr, f2_z1_hr = f2_x1, f2_z1
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (top_face_x - f2_x0) / dx_h))
                    f2_x1_hr = f2_x0 + t_c * dx_h
                    f2_z1_hr = f2_z0 + t_c * (f2_z1 - f2_z0)
                meshes.append(_handrail_flight_x(inner_y, f2_x0, f2_z0, f2_x1_hr, f2_z1_hr, **hr_kw))
                meshes.append(_baserail_flight_x(inner_y, f2_x0, f2_z0, f2_x1_c, f2_z1_c, **br_kw))
                dx_h = f2_x1 - f2_x0
                if abs(dx_h) > 1e-9:
                    t0 = (c_face_x - f2_x0) / dx_h
                    t1 = (top_face_x - f2_x0) / dx_h
                    f2_sp_z0 = f2_z0 + t0 * (f2_z1 - f2_z0)
                    f2_sp_z1 = f2_z0 + t1 * (f2_z1 - f2_z0)
                    meshes.extend(_spindles_flight_x(inner_y, c_face_x, f2_sp_z0, top_face_x, f2_sp_z1, **sp_kw))
                else:
                    meshes.extend(_spindles_flight_x(inner_y, f2_x0, f2_z0, f2_x1, f2_z1, **sp_kw))
            else:
                meshes.append(_stringer_flight_x_notched(inner_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl, ftf, thresh_back, tread_t))
            if render_outer:
                # Outer flight 2: clipped at pitch-change newel face and top post face
                if turn_dir == "left":
                    out_top_face_x = top_post_x - hp  # top newel +X face (flight approaches from +X)
                    pc2_face_x = f2_x0 - hp  # pitch-change newel +X face
                else:
                    out_top_face_x = top_post_x + hp  # top newel -X face
                    pc2_face_x = f2_x0 + hp  # pitch-change newel -X face
                dx_h = f2_x1 - f2_x0
                f2_x1_oc, f2_z1_oc = f2_x1, f2_z1
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (out_top_face_x - f2_x0) / dx_h))
                    f2_x1_oc = f2_x0 + t_c * dx_h
                    f2_z1_oc = f2_z0 + t_c * (f2_z1 - f2_z0)
                f2_x0_oc, f2_z0_oc = f2_x0, f2_z0
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (pc2_face_x - f2_x0) / dx_h))
                    f2_x0_oc = f2_x0 + t_c * dx_h
                    f2_z0_oc = f2_z0 + t_c * (f2_z1 - f2_z0)
                meshes.append(_stringer_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc))
                meshes.append(_handrail_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **hr_kw))
                meshes.append(_baserail_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **br_kw))
                if abs(dx_h) > 1e-9:
                    meshes.extend(_spindles_flight_x(outer_y, pc2_face_x, f2_z0_oc, out_top_face_x, f2_z1_oc, **sp_kw))
            else:
                meshes.append(_stringer_flight_x_notched(outer_y, f2_x0_ext, z_ext2, f2_x1_fl, f2_z1_fl, ftf, thresh_back, tread_t))

    # --- Pitched stringers for winder flights ---
    if actual_winders > 0:
        inner_x = corner_x
        outer_x = width - corner_x
        nzs = rise * nosing / going

        # Flight 1
        f1_y0 = flight1_shift_y
        f1_y1 = flight1_treads * going + flight1_shift_y
        f1_z0 = rise + nzs
        f1_z1 = (flight1_treads + 1) * rise + nzs
        bot_face_y = bottom_post_y + hp
        dy1 = f1_y1 - f1_y0
        if flight1_treads > 0:
            if render_inner:
                f1_y0_c, f1_z0_c = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_c = f1_y0 + t_c * dy1
                    f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
                meshes.append(_stringer_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1))
                meshes.append(_handrail_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1, **hr_kw))
                meshes.append(_baserail_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1, **br_kw))
                c_face_y = corner_y - c_hp
                if abs(dy1) > 1e-9:
                    t_sp = (c_face_y - f1_y0) / dy1
                    f1_sp_z1 = f1_z0 + t_sp * (f1_z1 - f1_z0)
                else:
                    f1_sp_z1 = f1_z1
                meshes.extend(_spindles_flight_y(inner_x, f1_y0_c, f1_z0_c, c_face_y, f1_sp_z1, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(inner_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))

        # Flight 2 coordinates
        inner_y = corner_y
        outer_y = corner_y + width
        if turn_dir == "left":
            f2_x0 = -winder_offset - nosing - riser_t / 2
            f2_x1 = -(flight2_treads * going) - winder_offset - nosing - riser_t / 2
        else:
            f2_x0 = width + winder_offset + nosing + riser_t / 2
            f2_x1 = width + flight2_treads * going + winder_offset + nosing + riser_t / 2
        f2_z0 = flight2_start_riser * rise + nzs
        f2_z1 = (flight2_start_riser + flight2_treads) * rise + nzs
        z_fl = riser_t * rise / (2 * going)
        f2_x1_fl = f2_x1 + (-riser_t / 2 if turn_dir == "left" else riser_t / 2)
        f2_z1_fl = f2_z1 + z_fl

        # Winder outer stringer geometry (needed by both outer paths)
        outer_corner_y = corner_y + width
        wy_len = abs(outer_corner_y - f1_y1)
        wx_len = abs(outer_x - f2_x0)
        total_path = wy_len + wx_len
        z_winder = f2_z0 - f1_z1
        z_corner = f1_z1 + z_winder * wy_len / total_path if total_path > 1e-9 else f1_z1

        if turn_dir == "left":
            top_face_x = top_post_x + hp
            c_face_x = corner_x - c_hp
        else:
            top_face_x = top_post_x - hp
            c_face_x = corner_x + c_hp

        if flight2_treads > 0:
            if render_inner:
                dx_s = f2_x1_fl - f2_x0
                f2_x1_c, f2_z1_c = f2_x1_fl, f2_z1_fl
                if abs(dx_s) > 1e-9:
                    t_c = max(0.0, min(1.0, (top_face_x - f2_x0) / dx_s))
                    f2_x1_c = f2_x0 + t_c * dx_s
                    f2_z1_c = f2_z0 + t_c * (f2_z1_fl - f2_z0)
                meshes.append(_stringer_flight_x(inner_y, f2_x0, f2_z0, f2_x1_c, f2_z1_c))
                dx_h = f2_x1 - f2_x0
                f2_x1_hr, f2_z1_hr = f2_x1, f2_z1
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (top_face_x - f2_x0) / dx_h))
                    f2_x1_hr = f2_x0 + t_c * dx_h
                    f2_z1_hr = f2_z0 + t_c * (f2_z1 - f2_z0)
                meshes.append(_handrail_flight_x(inner_y, f2_x0, f2_z0, f2_x1_hr, f2_z1_hr, **hr_kw))
                meshes.append(_baserail_flight_x(inner_y, f2_x0, f2_z0, f2_x1_c, f2_z1_c, **br_kw))
                dx_h = f2_x1 - f2_x0
                if abs(dx_h) > 1e-9:
                    t0 = (c_face_x - f2_x0) / dx_h
                    t1 = (top_face_x - f2_x0) / dx_h
                    f2_sp_z0 = f2_z0 + t0 * (f2_z1 - f2_z0)
                    f2_sp_z1 = f2_z0 + t1 * (f2_z1 - f2_z0)
                    meshes.extend(_spindles_flight_x(inner_y, c_face_x, f2_sp_z0, top_face_x, f2_sp_z1, **sp_kw))
                else:
                    meshes.extend(_spindles_flight_x(inner_y, f2_x0, f2_z0, f2_x1, f2_z1, **sp_kw))
            else:
                meshes.append(_stringer_flight_x_notched(inner_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl, ftf, thresh_back, tread_t))

        if render_outer:
            if flight1_treads > 0:
                # Outer flight 1: clipped at bottom and pitch-change newel faces
                f1_y0_oc, f1_z0_oc = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_oc = f1_y0 + t_c * dy1
                    f1_z0_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
                meshes.append(_stringer_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1))
                meshes.append(_handrail_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **hr_kw))
                meshes.append(_baserail_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **br_kw))
                pc_face_y = f1_y1 - hp
                if abs(dy1) > 1e-9:
                    t_sp = (pc_face_y - f1_y0) / dy1
                    f1_sp_z1 = f1_z0 + t_sp * (f1_z1 - f1_z0)
                else:
                    f1_sp_z1 = f1_z1
                meshes.extend(_spindles_flight_y(outer_x, f1_y0_oc, f1_z0_oc, pc_face_y, f1_sp_z1, **sp_kw))
            # Winder Y-piece: handrail/baserail/spindles from pitch-change newel to outer corner newel
            # Terminate Y-piece flush with front face of X-piece stringer (upper masters lower)
            st2 = STRINGER_THICKNESS / 2
            dy_w = outer_corner_y - f1_y1
            y_ext = outer_corner_y - st2
            z_y_ext = z_corner - st2 * (z_corner - f1_z1) / dy_w if abs(dy_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_y(outer_x, f1_y1, f1_z1, y_ext, z_y_ext,
                                             clip_z_min=0 if flight1_treads == 0 else None))
            pc1_face_y_end = f1_y1 + hp  # +Y face of pitch-change newel
            oc_face_y = outer_corner_y - hp  # -Y face of outer corner newel
            meshes.append(_handrail_flight_y(outer_x, pc1_face_y_end, f1_z1, outer_corner_y, z_corner, **hr_kw))
            meshes.append(_baserail_flight_y(outer_x, pc1_face_y_end, f1_z1, outer_corner_y, z_corner, **br_kw))
            meshes.extend(_spindles_flight_y(outer_x, pc1_face_y_end, f1_z1, oc_face_y, z_corner, **sp_kw))
            # Winder X-piece: handrail/baserail/spindles from outer corner newel to pitch-change newel
            # X-piece extends to Y-piece outer face so upper flight masters at corner
            x_ext = (outer_x + st2) if turn_dir == "left" else (outer_x - st2)
            dx_w = f2_x0 - outer_x
            z_x_ext = z_corner + (x_ext - outer_x) * (f2_z0 - z_corner) / dx_w if abs(dx_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y, x_ext, z_x_ext, f2_x0, f2_z0))
            if turn_dir == "left":
                oc_face_x = outer_x - hp  # -X face
                pc2_face_x = f2_x0 + hp  # +X face of pitch-change newel at f2_x0
            else:
                oc_face_x = outer_x + hp  # +X face
                pc2_face_x = f2_x0 - hp  # -X face
            meshes.append(_handrail_flight_x(outer_corner_y, outer_x, z_corner, f2_x0, f2_z0, **hr_kw))
            meshes.append(_baserail_flight_x(outer_corner_y, outer_x, z_corner, f2_x0, f2_z0, **br_kw))
            meshes.extend(_spindles_flight_x(outer_corner_y, oc_face_x, z_corner, pc2_face_x, f2_z0, **sp_kw))
            # Outer flight 2: from pitch-change newel to top post
            if flight2_treads > 0:
                if turn_dir == "left":
                    out_top_face_x = top_post_x - hp
                    pc2_start_x = f2_x0 - hp
                else:
                    out_top_face_x = top_post_x + hp
                    pc2_start_x = f2_x0 + hp
                dx_h = f2_x1 - f2_x0
                f2_x1_oc, f2_z1_oc = f2_x1, f2_z1
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (out_top_face_x - f2_x0) / dx_h))
                    f2_x1_oc = f2_x0 + t_c * dx_h
                    f2_z1_oc = f2_z0 + t_c * (f2_z1 - f2_z0)
                f2_x0_oc, f2_z0_oc = f2_x0, f2_z0
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (pc2_start_x - f2_x0) / dx_h))
                    f2_x0_oc = f2_x0 + t_c * dx_h
                    f2_z0_oc = f2_z0 + t_c * (f2_z1 - f2_z0)
                meshes.append(_stringer_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc))
                meshes.append(_handrail_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **hr_kw))
                meshes.append(_baserail_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **br_kw))
                if abs(dx_h) > 1e-9:
                    meshes.extend(_spindles_flight_x(outer_y, pc2_start_x, f2_z0_oc, out_top_face_x, f2_z1_oc, **sp_kw))
        else:
            # Extend winder corner stringers: upper flight masters lower
            st2 = STRINGER_THICKNESS / 2
            dy_w = outer_corner_y - f1_y1
            y_ext = outer_corner_y - st2
            z_y_ext = z_corner - st2 * (z_corner - f1_z1) / dy_w if abs(dy_w) > 1e-9 else z_corner
            if flight1_treads > 0:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(outer_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))
                meshes.append(_stringer_flight_y(outer_x, f1_y1, f1_z1, y_ext, z_y_ext))
            else:
                # Merge wall extension into winder Y-piece
                yp_slope = (z_corner - f1_z1) / (outer_corner_y - f1_y1) if abs(outer_corner_y - f1_y1) > 1e-9 else 0
                yp_y_start = f1_y1 - WALL_STRINGER_EXTENSION
                yp_z_start = f1_z1 - WALL_STRINGER_EXTENSION * yp_slope
                meshes.append(_stringer_flight_y(outer_x, yp_y_start, yp_z_start, y_ext, z_y_ext, clip_z_min=0))
            x_ext = (outer_x + st2) if turn_dir == "left" else (outer_x - st2)
            dx_w = f2_x0 - outer_x
            z_x_ext = z_corner + (x_ext - outer_x) * (f2_z0 - z_corner) / dx_w if abs(dx_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y, x_ext, z_x_ext, f2_x0, f2_z0))
            if flight2_treads > 0:
                meshes.append(_stringer_flight_x_notched(outer_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl, ftf, thresh_back, tread_t))

    # --- Newel posts (top = 150mm above highest abutting handrail) ---
    NEWEL_CAP = 150.0
    hr_rise = p["handrail_rise"]
    nzs_hr = rise * nosing / going
    inner_x = corner_x
    outer_x = width - corner_x
    outer_y_pos = corner_y + width

    # Inner newel posts
    if render_inner:
        if flight1_treads > 0:
            hr_bot = rise + nzs_hr + hr_rise
            bot_h = hr_bot + NEWEL_CAP
            meshes.append(_box_mesh(inner_x, bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355"))
        hr_c_f1 = (flight1_treads + 1) * rise + nzs_hr + hr_rise
        hr_c_f2 = flight2_start_riser * rise + nzs_hr + hr_rise
        c_h = max(hr_c_f1, hr_c_f2) + NEWEL_CAP
        meshes.append(_box_mesh(inner_x, corner_y, c_h / 2, c_ns, c_ns, c_h, "#8B7355"))
        if flight2_treads > 0:
            # Top newel extends FROM cutting plane (150mm below stringer bottom) UPWARD
            pitch_line_top = (flight2_start_riser + flight2_treads) * rise + nzs_hr
            newel_bottom = pitch_line_top - 400.0
            newel_top = pitch_line_top + hr_rise + NEWEL_CAP
            top_h = newel_top - newel_bottom
            top_z_center = (newel_bottom + newel_top) / 2
            meshes.append(_box_mesh(top_post_x, corner_y, top_z_center, ns, ns, top_h, "#8B7355"))
    else:
        # Wall condition on inner side: add stub newel at corner (no stringers)
        # Stub newel extends from landing tread surface to stringer top
        pitch_f1 = (flight1_treads + 1) * rise + nzs_hr
        pitch_f2 = flight2_start_riser * rise + nzs_hr
        highest_abutment = max(pitch_f1, pitch_f2)
        # Stub top at stringer top surface
        stub_top = highest_abutment + STRINGER_PITCH_OFFSET
        # Stub bottom at landing tread surface
        landing_tread_surface = winder_start_riser * rise - tread_t
        stub_bottom = landing_tread_surface
        stub_h = stub_top - stub_bottom
        stub_z_center = (stub_top + stub_bottom) / 2
        meshes.append(_box_mesh(inner_x, corner_y, stub_z_center, ns, ns, stub_h, "#8B7355"))
        # Note: Stub stringers removed - they were causing green artifacts

    # Outer newel posts (bottom, pitch-change at f1_y1, outer corner, pitch-change at f2_x0, top)
    if render_outer:
        nzs_w = rise * nosing / going
        if flight1_treads > 0:
            hr_bot = rise + nzs_w + hr_rise
            bot_h = hr_bot + NEWEL_CAP
            meshes.append(_box_mesh(outer_x, bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355"))
        # Pitch-change newel where flight 1 meets winder/landing on outer wall
        f1_y1_val = flight1_treads * going + flight1_shift_y
        hr_pc1 = (flight1_treads + 1) * rise + nzs_w + hr_rise
        pc1_h = hr_pc1 + NEWEL_CAP
        meshes.append(_box_mesh(outer_x, f1_y1_val, pc1_h / 2, ns, ns, pc1_h, "#8B7355"))
        # Outer corner newel (where Y-run meets X-run)
        oc_hr = max(hr_pc1, flight2_start_riser * rise + nzs_w + hr_rise)
        oc_h = oc_hr + NEWEL_CAP
        meshes.append(_box_mesh(outer_x, outer_y_pos, oc_h / 2, ns, ns, oc_h, "#8B7355"))
        # Pitch-change newel where winder/landing meets flight 2 on outer wall
        f2_x0_val = (-winder_offset - nosing - riser_t / 2) if turn_dir == "left" \
            else (width + winder_offset + nosing + riser_t / 2)
        hr_pc2 = flight2_start_riser * rise + nzs_w + hr_rise
        pc2_h = hr_pc2 + NEWEL_CAP
        meshes.append(_box_mesh(f2_x0_val, outer_y_pos, pc2_h / 2, ns, ns, pc2_h, "#8B7355"))
        # Top newel - extends FROM cutting plane (150mm below stringer bottom) UPWARD
        if flight2_treads > 0:
            pitch_line_top = (flight2_start_riser + flight2_treads) * rise + nzs_w
            newel_bottom = pitch_line_top - 400.0
            newel_top = pitch_line_top + hr_rise + NEWEL_CAP
            top_h = newel_top - newel_bottom
            top_z_center = (newel_bottom + newel_top) / 2
            meshes.append(_box_mesh(top_post_x, outer_y_pos, top_z_center, ns, ns, top_h, "#8B7355"))

    return meshes


def _preview_double_winder(p):
    import math
    meshes = []
    width = p["stair_width"]
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    winders1 = p["turn1_winders"]
    winders2 = p["turn2_winders"]
    turn1_dir = p["turn1_direction"]
    turn2_dir = p["turn2_direction"]
    turn1_enabled = p.get("turn1_enabled", True)
    turn2_enabled = p.get("turn2_enabled", True)

    # Balustrade keyword dicts (passed to handrail/baserail/spindle helpers)
    hr_kw = {"hr_width": p["handrail_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"]}
    br_kw = {"br_width": p["baserail_width"], "br_height": p["baserail_height"]}
    sp_kw = {"spindle_size": p["spindle_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"], "br_height": p["baserail_height"]}

    # Map left/right conditions to inner/outer based on turn1 direction
    if turn1_dir == "left":
        render_inner = p["left_condition"] == "balustrade"
        render_outer = p["right_condition"] == "balustrade"
    else:
        render_inner = p["right_condition"] == "balustrade"
        render_outer = p["left_condition"] == "balustrade"

    actual_winders1 = winders1 if turn1_enabled else 0
    actual_winders2 = winders2 if turn2_enabled else 0
    total_winders = actual_winders1 + actual_winders2
    straight_treads = num_treads - total_winders
    # Use custom flight distribution if provided and valid
    f1_ov = p.get("flight1_steps", -1)
    f2_ov = p.get("flight2_steps", -1)
    f3_ov = p.get("flight3_steps", -1)
    if f1_ov >= 0 and f2_ov >= 0 and f3_ov >= 0 and f1_ov + f2_ov + f3_ov == straight_treads:
        flight1_treads = f1_ov
        flight2_treads = f2_ov
        flight3_treads = f3_ov
    else:
        flight1_treads = straight_treads // 3
        flight2_treads = straight_treads // 3
        flight3_treads = straight_treads - flight1_treads - flight2_treads

    # Step 3: Calculate offset and half-post
    ns = p["newel_size"]
    hp = ns / 2.0
    wg = compute_winder_geometry(ns, width)
    offset = wg["offset"]
    wx = p["winder_x"]
    wy = p["winder_y"]
    wx2 = p["winder_x2"]
    wy2 = p["winder_y2"]

    riser_idx = 0
    flight1_shift_y = (hp - wx - wy + nosing) if actual_winders1 > 0 else 0.0

    # Flight 1 (offset by X+Y from internal corner)
    for i in range(flight1_treads):
        tread_y = i * going - nosing + flight1_shift_y
        tread_z = (i + 1) * rise - tread_t
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c"
        ))

    riser_h = rise - tread_t
    for i in range(flight1_treads + 1):
        if riser_t > 0:
            meshes.append(_box_mesh(
                width / 2, i * going + riser_t / 2 + flight1_shift_y, i * rise + riser_h / 2,
                width, riser_t, riser_h, "#e8dcc8"
            ))

    riser_idx = flight1_treads + 1

    # Turn 1 winders — construction-based profiles
    corner1_y = flight1_treads * going
    corner1_x = 0 if turn1_dir == "left" else width

    turn1_winder_start = riser_idx
    for i in range(actual_winders1):
        winder_z = (riser_idx + i) * rise - tread_t
        profile = _winder_profiles_from_construction(
            corner1_x, corner1_y, ns, width,
            turn1_dir, i, actual_winders1,
            riser_extension=riser_t + nosing,
            flight_extension=wx + wy - 2 * hp,
            winder_x=wx)
        meshes.append({
            "type": "winder_polygon",
            "profile": [[pt[0], pt[1]] for pt in profile],
            "z": winder_z,
            "thickness": tread_t,
            "color": "#d4a574",
            "name": f"Turn1 Winder {i+1}",
            "ifc_type": "winder_tread",
        })

    # Turn 1 winder risers
    meshes.extend(_winder_riser_meshes(
        corner1_x, corner1_y, ns, width, turn1_dir,
        actual_winders1, turn1_winder_start, rise, tread_t, riser_t,
        nosing=nosing, winder_x=wx))

    # Newel post at turn 1 — placed at end with handrail-based height

    # Bottom newel post (foot of staircase, centred on first tread nosing line)
    bottom_post_y = flight1_shift_y - nosing

    # Turn 1 landing tread when winders are off
    if actual_winders1 == 0:
        landing1_z = turn1_winder_start * rise - tread_t
        ext = nosing + riser_t
        landing1_w = width + ext
        if turn1_dir == "left":
            landing1_cx = (width - ext) / 2
        else:
            landing1_cx = (width + ext) / 2
        meshes.append(_box_mesh(
            landing1_cx,
            corner1_y + width / 2,
            landing1_z + tread_t / 2,
            landing1_w, width, tread_t, "#c8a87c",
            name="Landing 1", ifc_type="landing",
        ))

    riser_idx += actual_winders1
    # When turn 1 winders are off, the landing consumes 1 rise — shift flight 2 up
    if actual_winders1 == 0:
        riser_idx += 1
        flight2_treads = max(0, flight2_treads - 1)
    flight2_riser_start = riser_idx

    # Flight 2 (perpendicular, offset by X+Y from internal corner)
    winder_offset1 = (wx + wy - hp) if actual_winders1 > 0 else 0.0
    flight2_shift = winder_offset1 + nosing + riser_t / 2
    for i in range(flight2_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        if turn1_dir == "left":
            tread_x = -(i * going) - going / 2 + nosing / 2 - flight2_shift
        else:
            tread_x = width + i * going + going / 2 - nosing / 2 + flight2_shift
        meshes.append(_box_mesh(
            tread_x, corner1_y + width / 2, tread_z + tread_t / 2,
            going + nosing + riser_t, width, tread_t, "#c8a87c"
        ))

    # Flight 2 risers
    if riser_t > 0:
        for i in range(flight2_treads + 1):
            riser_z = (flight2_riser_start + i - 1) * rise + riser_h / 2
            if turn1_dir == "left":
                riser_x = -(i * going) - winder_offset1 - nosing - riser_t / 2
            else:
                riser_x = width + i * going + winder_offset1 + nosing + riser_t / 2
            meshes.append(_box_mesh(
                riser_x, corner1_y + width / 2, riser_z,
                riser_t, width, riser_h, "#e8dcc8"
            ))

    riser_idx += flight2_treads

    # Turn 2 winders — corner2 links flight 2 top riser (offset1) to turn 2 entry (offset2)
    winder_offset2 = (wx2 + wy2 - hp) if actual_winders2 > 0 else 0.0
    if turn1_dir == "left":
        corner2_x = -(flight2_treads * going) - winder_offset1 - winder_offset2
    else:
        corner2_x = width + flight2_treads * going + winder_offset1 + winder_offset2
    corner2_y = corner1_y

    # Turn 2 rotation: flight 2 approaches along -X (left) or +X (right)
    turn2_rotation = 90 if turn1_dir == "left" else -90

    turn2_winder_start = riser_idx
    for i in range(actual_winders2):
        winder_z = (riser_idx + i) * rise - tread_t
        profile = _winder_profiles_from_construction(
            corner2_x, corner2_y, ns, width,
            turn2_dir, i, actual_winders2,
            rotation=turn2_rotation,
            riser_extension=riser_t + nosing,
            flight_extension=wx2 + wy2 - 2 * hp,
            winder_x=wx2)
        meshes.append({
            "type": "winder_polygon",
            "profile": [[pt[0], pt[1]] for pt in profile],
            "z": winder_z,
            "thickness": tread_t,
            "color": "#d4a574",
            "name": f"Turn2 Winder {i+1}",
            "ifc_type": "winder_tread",
        })

    # Turn 2 winder risers
    meshes.extend(_winder_riser_meshes(
        corner2_x, corner2_y, ns, width, turn2_dir,
        actual_winders2, turn2_winder_start, rise, tread_t, riser_t,
        nosing=nosing, rotation=turn2_rotation, winder_x=wx2))

    # Newel post at turn 2 — placed at end with handrail-based height

    riser_idx += actual_winders2
    # When turn 2 winders are off, the landing consumes 1 rise — shift flight 3 up
    if actual_winders2 == 0:
        riser_idx += 1
        flight3_treads = max(0, flight3_treads - 1)
    flight3_riser_start = riser_idx

    if turn1_dir == "left" and turn2_dir == "left":
        flight3_start_x = corner2_x - width
        flight3_start_y = corner2_y
    elif turn1_dir == "right" and turn2_dir == "right":
        flight3_start_x = corner2_x
        flight3_start_y = corner2_y
    elif turn1_dir == "left" and turn2_dir == "right":
        flight3_start_x = corner2_x
        flight3_start_y = corner2_y + width
    else:
        flight3_start_x = corner2_x - width
        flight3_start_y = corner2_y + width

    # Turn 2 landing tread when winders are off
    if actual_winders2 == 0:
        landing2_z = turn2_winder_start * rise - tread_t
        ext = nosing + riser_t  # extension under first riser of flight 3
        # Both nosing edges centred on newel post; departure extends under flight 3's first riser
        landing2_cx = flight3_start_x + width / 2
        meshes.append(_box_mesh(
            landing2_cx,
            corner2_y + (width - ext) / 2,
            landing2_z + tread_t / 2,
            width, width + ext, tread_t, "#c8a87c",
            name="Landing 2", ifc_type="landing",
        ))

    # Flight 3 shift — nosing centred on post when winders off
    if actual_winders2 > 0:
        flight3_shift_y = -(winder_offset2 + riser_t)
    else:
        flight3_shift_y = -(flight3_start_y - corner2_y) - riser_t

    for i in range(flight3_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        tread_y = flight3_start_y - (i + 1) * going - nosing + flight3_shift_y
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            flight3_start_x + width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c"
        ))

    # Flight 3 risers (going in -Y direction)
    if riser_t > 0:
        for i in range(flight3_treads + 1):
            riser_z = (flight3_riser_start + i - 1) * rise + riser_h / 2
            riser_y = flight3_start_y - i * going - nosing + riser_t / 2 + flight3_shift_y
            meshes.append(_box_mesh(
                flight3_start_x + width / 2, riser_y, riser_z,
                width, riser_t, riser_h, "#e8dcc8"
            ))

    # --- Landing threshold strip (flight 3 top) ---
    ftf = (num_treads + 1) * rise
    threshold_d = p["threshold_depth"]
    thresh_riser_y = flight3_start_y - flight3_treads * going + flight3_shift_y
    thresh_front_y = thresh_riser_y + nosing
    thresh_back_y = thresh_front_y - threshold_d
    meshes.append(_box_mesh(
        flight3_start_x + width / 2,
        (thresh_front_y + thresh_back_y) / 2,
        ftf - tread_t / 2,
        width, threshold_d, tread_t, "#c8a87c",
        name="Threshold", ifc_type="threshold",
    ))

    # Top newel post y position (centred on threshold nosing line)
    top_post_y = thresh_front_y

    # Corner / end post half-sizes (auto-enlarged to 100mm when absorbing
    # a 0-tread flight's newel)
    c1_ns = max(ns, 100.0) if flight1_treads == 0 else ns
    c2_ns = max(ns, 100.0) if flight3_treads == 0 else ns
    c1_hp = c1_ns / 2.0
    c2_hp = c2_ns / 2.0

    # --- Stringers (only for flat landings) ---
    if actual_winders1 == 0 or actual_winders2 == 0:
        # Stringer X positions: inner (newel side) and outer (wall side)
        # Flight 1 inner = corner1_x, outer = width - corner1_x
        f1_inner_x = corner1_x          # 0 for left, width for right
        f1_outer_x = width - corner1_x  # width for left, 0 for right
        f2_x_last_ext = None  # set below if flight 2 outer extends to landing 2
        nzs = rise * nosing / going  # nosing z-shift: pitch line offset at nosing vs riser

        if actual_winders1 == 0:
            # === Flight 1 coordinates ===
            f1_y0 = flight1_shift_y
            f1_y1 = flight1_treads * going + flight1_shift_y
            f1_z0 = rise + nzs
            f1_z1 = (flight1_treads + 1) * rise + nzs

            landing1_z = turn1_winder_start * rise
            land1_top = landing1_z + STRINGER_DROP
            # Flight 1 outer extension along pitch
            z_ext1 = land1_top - STRINGER_PITCH_OFFSET
            dy1 = f1_y1 - f1_y0
            dz1 = f1_z1 - f1_z0
            f1_y1_ext = f1_y1 + (z_ext1 - f1_z1) * dy1 / dz1 if abs(dz1) > 1e-9 else f1_y1

            # === Flight 2 coordinates + extensions (computed before landing stringers) ===
            f2_inner_y = corner1_y
            f2_outer_y = corner1_y + width
            if turn1_dir == "left":
                f2_x_first = -winder_offset1 - nosing - riser_t / 2
                f2_x_last = -(flight2_treads * going) - winder_offset1 - nosing - riser_t / 2
            else:
                f2_x_first = width + winder_offset1 + nosing + riser_t / 2
                f2_x_last = width + flight2_treads * going + winder_offset1 + nosing + riser_t / 2
            f2_z_first = flight2_riser_start * rise + nzs
            f2_z_last = (flight2_riser_start + flight2_treads) * rise + nzs
            # Clip far end at corner2 post centre if turn 2 also has a landing
            if actual_winders2 == 0 and flight2_treads > 0:
                dx = f2_x_last - f2_x_first
                if abs(dx) > 1e-9:
                    t_clip = (corner2_x - f2_x_first) / dx
                    t_clip = max(0.0, min(1.0, t_clip))
                    f2_x_last = f2_x_first + t_clip * dx
                    f2_z_last = f2_z_first + t_clip * (f2_z_last - f2_z_first)
            # Flight 2 outer extensions
            f2_dx = f2_x_last - f2_x_first
            f2_dz = f2_z_last - f2_z_first
            f2_x_first_ext, f2_z_first_ext = f2_x_first, f2_z_first
            f2_x_last_ext_v, f2_z_last_ext = f2_x_last, f2_z_last
            if abs(f2_dz) > 1e-9:
                z_ext_s = land1_top - STRINGER_PITCH_OFFSET
                f2_x_first_ext = f2_x_first + (z_ext_s - f2_z_first) * f2_dx / f2_dz
                f2_z_first_ext = z_ext_s
            if actual_winders2 == 0 and abs(f2_dz) > 1e-9:
                land2_top_pre = turn2_winder_start * rise + STRINGER_DROP
                z_ext_e = land2_top_pre - STRINGER_PITCH_OFFSET
                f2_x_last_ext_v = f2_x_last + (z_ext_e - f2_z_last) * f2_dx / f2_dz
                f2_z_last_ext = z_ext_e
            f2_x_last_ext = f2_x_last_ext_v  # share with turn 2 section

            # === Flight 1 stringers ===
            bot_face_y = bottom_post_y + hp
            dy1 = f1_y1 - f1_y0
            if render_inner:
                f1_y0_c, f1_z0_c = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_c = f1_y0 + t_c * dy1
                    f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
                meshes.append(_stringer_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1))
                meshes.append(_handrail_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1, **hr_kw))
                meshes.append(_baserail_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1, **br_kw))
                c1_face_y = corner1_y - c1_hp
                if abs(dy1) > 1e-9:
                    t_sp = (c1_face_y - f1_y0) / dy1
                    f1_sp_z1 = f1_z0 + t_sp * (f1_z1 - f1_z0)
                else:
                    f1_sp_z1 = f1_z1
                meshes.extend(_spindles_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, c1_face_y, f1_sp_z1, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(f1_inner_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))
            if render_outer:
                f1_y0_oc, f1_z0_oc = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_oc = f1_y0 + t_c * dy1
                    f1_z0_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
                meshes.append(_stringer_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1))
                meshes.append(_handrail_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **hr_kw))
                meshes.append(_baserail_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **br_kw))
                pc_face_y = f1_y1 - hp
                if abs(dy1) > 1e-9:
                    t_sp = (pc_face_y - f1_y0) / dy1
                    f1_sp_z1 = f1_z0 + t_sp * (f1_z1 - f1_z0)
                else:
                    f1_sp_z1 = f1_z1
                meshes.extend(_spindles_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, pc_face_y, f1_sp_z1, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(f1_outer_x, f1_y0_w, f1_z0_w, f1_y1_ext, z_ext1, clip_z_min=0))

            # === Turn 1 landing stringers — outer endpoints linked to extensions ===
            st2 = STRINGER_THICKNESS / 2
            if turn1_dir == "left":
                meshes.append(_stringer_landing_x(corner1_y, f2_x_first, f1_inner_x, landing1_z))
                # Outer landing stringers, handrails, and baserails
                meshes.append(_stringer_landing_y(f1_outer_x, f1_y1_ext, corner1_y + width + st2, landing1_z))
                meshes.append(_stringer_landing_x(corner1_y + width, f2_x_first_ext, f1_outer_x - st2, landing1_z))
                if render_outer:
                    # Add handrails and baserails for landing when balustrade is present
                    meshes.append(_handrail_landing_y(f1_outer_x, f1_y1_ext, corner1_y + width + st2, landing1_z, **hr_kw))
                    meshes.append(_handrail_landing_x(corner1_y + width, f2_x_first_ext, f1_outer_x - st2, landing1_z, **hr_kw))
                    meshes.append(_baserail_landing_y(f1_outer_x, f1_y1_ext, corner1_y + width + st2, landing1_z, **br_kw))
                    meshes.append(_baserail_landing_x(corner1_y + width, f2_x_first_ext, f1_outer_x - st2, landing1_z, **br_kw))
                    # Add spindles for landing
                    meshes.extend(_spindles_landing_y(f1_outer_x, f1_y1_ext, corner1_y + width + st2, landing1_z, **sp_kw))
                    meshes.extend(_spindles_landing_x(corner1_y + width, f2_x_first_ext, f1_outer_x - st2, landing1_z, **sp_kw))
            else:
                meshes.append(_stringer_landing_x(corner1_y, f1_inner_x, f2_x_first, landing1_z))
                # Outer landing stringers, handrails, and baserails
                meshes.append(_stringer_landing_y(f1_outer_x, f1_y1_ext, corner1_y + width + st2, landing1_z))
                meshes.append(_stringer_landing_x(corner1_y + width, f1_outer_x + st2, f2_x_first_ext, landing1_z))
                if render_outer:
                    # Add handrails and baserails for landing when balustrade is present
                    meshes.append(_handrail_landing_y(f1_outer_x, f1_y1_ext, corner1_y + width + st2, landing1_z, **hr_kw))
                    meshes.append(_handrail_landing_x(corner1_y + width, f1_outer_x + st2, f2_x_first_ext, landing1_z, **hr_kw))
                    meshes.append(_baserail_landing_y(f1_outer_x, f1_y1_ext, corner1_y + width + st2, landing1_z, **br_kw))
                    meshes.append(_baserail_landing_x(corner1_y + width, f1_outer_x + st2, f2_x_first_ext, landing1_z, **br_kw))
                    # Add spindles for landing
                    meshes.extend(_spindles_landing_y(f1_outer_x, f1_y1_ext, corner1_y + width + st2, landing1_z, **sp_kw))
                    meshes.extend(_spindles_landing_x(corner1_y + width, f1_outer_x + st2, f2_x_first_ext, landing1_z, **sp_kw))

            # === Flight 2 stringers ===
            f2_dx = f2_x_last - f2_x_first
            if render_inner:
                meshes.append(_stringer_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))
                meshes.append(_handrail_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **hr_kw))
                meshes.append(_baserail_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **br_kw))
                if abs(f2_dx) > 1e-9:
                    if turn1_dir == "left":
                        c1_face_x = corner1_x - c1_hp
                        c2_face_x = corner2_x + c2_hp
                    else:
                        c1_face_x = corner1_x + c1_hp
                        c2_face_x = corner2_x - c2_hp
                    t0 = (c1_face_x - f2_x_first) / f2_dx
                    t1 = (c2_face_x - f2_x_first) / f2_dx
                    f2_sp_z0 = f2_z_first + t0 * (f2_z_last - f2_z_first)
                    f2_sp_z1 = f2_z_first + t1 * (f2_z_last - f2_z_first)
                    meshes.extend(_spindles_flight_x(f2_inner_y, c1_face_x, f2_sp_z0, c2_face_x, f2_sp_z1, **sp_kw))
                else:
                    meshes.extend(_spindles_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **sp_kw))
            else:
                meshes.append(_stringer_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))
            if render_outer:
                # Outer flight 2: clipped at pitch-change newel faces
                if turn1_dir == "left":
                    pc1_face_x = f2_x_first + hp  # +X face of pitch-change newel at f2 start
                    pc2_face_x = f2_x_last - hp if actual_winders2 > 0 else f2_x_last + hp  # face toward f2
                else:
                    pc1_face_x = f2_x_first - hp
                    pc2_face_x = f2_x_last + hp if actual_winders2 > 0 else f2_x_last - hp
                f2_x0_oc, f2_z0_oc = f2_x_first, f2_z_first
                f2_x1_oc, f2_z1_oc = f2_x_last, f2_z_last
                if abs(f2_dx) > 1e-9:
                    t_c = max(0.0, min(1.0, (pc1_face_x - f2_x_first) / f2_dx))
                    f2_x0_oc = f2_x_first + t_c * f2_dx
                    f2_z0_oc = f2_z_first + t_c * (f2_z_last - f2_z_first)
                    t_c2 = max(0.0, min(1.0, (pc2_face_x - f2_x_first) / f2_dx))
                    f2_x1_oc = f2_x_first + t_c2 * f2_dx
                    f2_z1_oc = f2_z_first + t_c2 * (f2_z_last - f2_z_first)
                meshes.append(_stringer_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc))
                meshes.append(_handrail_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **hr_kw))
                meshes.append(_baserail_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **br_kw))
                if abs(f2_dx) > 1e-9:
                    meshes.extend(_spindles_flight_x(f2_outer_y, pc1_face_x, f2_z0_oc, pc2_face_x, f2_z1_oc, **sp_kw))
            else:
                meshes.append(_stringer_flight_x(f2_outer_y, f2_x_first_ext, f2_z_first_ext,
                                                 f2_x_last_ext_v, f2_z_last_ext))

        if actual_winders2 == 0:
            landing2_z = turn2_winder_start * rise
            land2_top = landing2_z + STRINGER_DROP

            # Flight 3: outer = wall side, inner = newel side
            # f3_wall_x is the outer (wall) edge — inner/outer are swapped vs flight 1
            if turn1_dir == turn2_dir:
                f3_outer_x = flight3_start_x + corner1_x        # wall side
                f3_inner_x = flight3_start_x + width - corner1_x  # newel side
            else:
                f3_outer_x = flight3_start_x + width - corner1_x  # wall side
                f3_inner_x = flight3_start_x + corner1_x          # newel side

            # Flight 3 coordinates + clipping + outer extension
            f3_y_first = flight3_start_y - nosing + riser_t / 2 + flight3_shift_y
            f3_y_last = flight3_start_y - flight3_treads * going - nosing + riser_t / 2 + flight3_shift_y
            f3_z_first = flight3_riser_start * rise + nzs
            f3_z_last = (flight3_riser_start + flight3_treads) * rise + nzs
            # Clip near end at corner2 post centre Y
            if flight3_treads > 0:
                dy = f3_y_last - f3_y_first
                if abs(dy) > 1e-9:
                    t_clip = (corner2_y - f3_y_first) / dy
                    t_clip = max(0.0, min(1.0, t_clip))
                    f3_y_first = f3_y_first + t_clip * dy if t_clip > 0 else f3_y_first
                    f3_z_first = f3_z_first + t_clip * (f3_z_last - f3_z_first) if t_clip > 0 else f3_z_first
            # Flight 3 outer extension along pitch
            f3_y_first_ext, f3_z_first_ext = f3_y_first, f3_z_first
            f3_dy = f3_y_last - f3_y_first
            f3_dz = f3_z_last - f3_z_first
            if abs(f3_dz) > 1e-9:
                z_ext3 = land2_top - STRINGER_PITCH_OFFSET
                f3_y_first_ext = f3_y_first + (z_ext3 - f3_z_first) * f3_dy / f3_dz
                f3_z_first_ext = z_ext3

            # === Turn 2 landing stringers — outer endpoints linked to extensions ===
            st2 = STRINGER_THICKNESS / 2
            # Outer landing stringers, handrails, and baserails
            meshes.append(_stringer_landing_y(f3_outer_x, f3_y_first_ext, corner2_y + width + st2, landing2_z))
            x_inner_end = f2_x_last_ext if f2_x_last_ext is not None else corner2_x
            if f3_outer_x < x_inner_end:
                meshes.append(_stringer_landing_x(corner2_y + width, x_inner_end, f3_outer_x + st2, landing2_z))
                if render_outer:
                    meshes.append(_handrail_landing_x(corner2_y + width, x_inner_end, f3_outer_x + st2, landing2_z, **hr_kw))
                    meshes.append(_baserail_landing_x(corner2_y + width, x_inner_end, f3_outer_x + st2, landing2_z, **br_kw))
                    meshes.extend(_spindles_landing_x(corner2_y + width, x_inner_end, f3_outer_x + st2, landing2_z, **sp_kw))
            else:
                meshes.append(_stringer_landing_x(corner2_y + width, x_inner_end, f3_outer_x - st2, landing2_z))
                if render_outer:
                    meshes.append(_handrail_landing_x(corner2_y + width, x_inner_end, f3_outer_x - st2, landing2_z, **hr_kw))
                    meshes.append(_baserail_landing_x(corner2_y + width, x_inner_end, f3_outer_x - st2, landing2_z, **br_kw))
                    meshes.extend(_spindles_landing_x(corner2_y + width, x_inner_end, f3_outer_x - st2, landing2_z, **sp_kw))
            if render_outer:
                # Add Y-direction landing handrail and baserail
                meshes.append(_handrail_landing_y(f3_outer_x, f3_y_first_ext, corner2_y + width + st2, landing2_z, **hr_kw))
                meshes.append(_baserail_landing_y(f3_outer_x, f3_y_first_ext, corner2_y + width + st2, landing2_z, **br_kw))
                meshes.extend(_spindles_landing_y(f3_outer_x, f3_y_first_ext, corner2_y + width + st2, landing2_z, **sp_kw))

            # === Flight 3 stringers (notched for threshold, flush with riser back) ===
            z_fl = riser_t * rise / (2 * going)
            f3_y_last_fl = f3_y_last - riser_t / 2
            f3_z_last_fl = f3_z_last + z_fl
            top_face_y = top_post_y + hp
            dy3h = f3_y_last - f3_y_first
            if render_inner:
                dy3s = f3_y_last_fl - f3_y_first
                f3_y_end_c, f3_z_end_c = f3_y_last_fl, f3_z_last_fl
                if abs(dy3s) > 1e-9 and top_face_y > f3_y_last_fl:
                    t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3s))
                    f3_y_end_c = f3_y_first + t_c * dy3s
                    f3_z_end_c = f3_z_first + t_c * (f3_z_last_fl - f3_z_first)
                f3_y_hr_c, f3_z_hr_c = f3_y_last, f3_z_last
                if abs(dy3h) > 1e-9 and top_face_y > f3_y_last:
                    t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3h))
                    f3_y_hr_c = f3_y_first + t_c * dy3h
                    f3_z_hr_c = f3_z_first + t_c * (f3_z_last - f3_z_first)
                meshes.append(_stringer_flight_y(f3_inner_x, f3_y_first, f3_z_first,
                                                 f3_y_end_c, f3_z_end_c))
                meshes.append(_handrail_flight_y(f3_inner_x, f3_y_first, f3_z_first,
                                                 f3_y_hr_c, f3_z_hr_c, **hr_kw))
                meshes.append(_baserail_flight_y(f3_inner_x, f3_y_first, f3_z_first,
                                                 f3_y_end_c, f3_z_end_c, **br_kw))
                c2_face_f3 = (corner2_y + c2_hp) if f3_y_first > corner2_y else (corner2_y - c2_hp)
                dy3_full = f3_y_last - f3_y_first
                if abs(dy3_full) > 1e-9:
                    t_sp3 = (c2_face_f3 - f3_y_first) / dy3_full
                    f3_sp_z0 = f3_z_first + t_sp3 * (f3_z_last - f3_z_first)
                else:
                    f3_sp_z0 = f3_z_first
                meshes.extend(_spindles_flight_y(f3_inner_x, c2_face_f3, f3_sp_z0,
                                                 f3_y_hr_c, f3_z_hr_c, **sp_kw))
            else:
                meshes.append(_stringer_flight_y_notched(f3_inner_x, f3_y_first, f3_z_first,
                                                         f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))
            if render_outer:
                # Outer flight 3: from pitch-change newel face to top newel face
                pc_face_f3 = f3_y_first - hp  # -Y face (toward flight)
                top_face_y_out = top_post_y + hp  # +Y face (toward flight)
                f3_y0_oc, f3_z0_oc = f3_y_first, f3_z_first
                f3_y1_oc, f3_z1_oc = f3_y_last, f3_z_last
                if abs(dy3h) > 1e-9:
                    t_c0 = max(0.0, min(1.0, (pc_face_f3 - f3_y_first) / dy3h))
                    f3_y0_oc = f3_y_first + t_c0 * dy3h
                    f3_z0_oc = f3_z_first + t_c0 * (f3_z_last - f3_z_first)
                    t_c1 = max(0.0, min(1.0, (top_face_y_out - f3_y_first) / dy3h))
                    f3_y1_oc = f3_y_first + t_c1 * dy3h
                    f3_z1_oc = f3_z_first + t_c1 * (f3_z_last - f3_z_first)
                meshes.append(_stringer_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc))
                meshes.append(_handrail_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc, **hr_kw))
                meshes.append(_baserail_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc, **br_kw))
                if abs(dy3h) > 1e-9:
                    meshes.extend(_spindles_flight_y(f3_outer_x, pc_face_f3, f3_z0_oc, top_face_y_out, f3_z1_oc, **sp_kw))
            else:
                meshes.append(_stringer_flight_y_notched(f3_outer_x, f3_y_first_ext, f3_z_first_ext,
                                                         f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))

    # --- Pitched stringers for winder flights ---
    if actual_winders1 > 0:
        nzs = rise * nosing / going
        f1_inner_x = corner1_x
        f1_outer_x = width - corner1_x

        # Flight 1 stringers
        f1_y0 = flight1_shift_y
        f1_y1 = flight1_treads * going + flight1_shift_y
        f1_z0 = rise + nzs
        f1_z1 = (flight1_treads + 1) * rise + nzs
        bot_face_y = bottom_post_y + hp
        dy1 = f1_y1 - f1_y0
        if flight1_treads > 0:
            if render_inner:
                f1_y0_c, f1_z0_c = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_c = f1_y0 + t_c * dy1
                    f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
                meshes.append(_stringer_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1))
                meshes.append(_handrail_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1, **hr_kw))
                meshes.append(_baserail_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1, **br_kw))
                c1_face_y = corner1_y - c1_hp
                if abs(dy1) > 1e-9:
                    t_sp = (c1_face_y - f1_y0) / dy1
                    f1_sp_z1 = f1_z0 + t_sp * (f1_z1 - f1_z0)
                else:
                    f1_sp_z1 = f1_z1
                meshes.extend(_spindles_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, c1_face_y, f1_sp_z1, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(f1_inner_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))

        # Turn 1 winder outer stringer geometry
        outer_corner_y1 = corner1_y + width
        f2_inner_y = corner1_y
        f2_outer_y = corner1_y + width
        if turn1_dir == "left":
            f2_x_first = -winder_offset1 - nosing - riser_t / 2
            f2_x_last = -(flight2_treads * going) - winder_offset1 - nosing - riser_t / 2
        else:
            f2_x_first = width + winder_offset1 + nosing + riser_t / 2
            f2_x_last = width + flight2_treads * going + winder_offset1 + nosing + riser_t / 2
        f2_z_first = flight2_riser_start * rise + nzs
        f2_z_last = (flight2_riser_start + flight2_treads) * rise + nzs
        wy_len = abs(outer_corner_y1 - f1_y1)
        wx_len = abs(f1_outer_x - f2_x_first)
        total_path = wy_len + wx_len
        z_winder = f2_z_first - f1_z1
        z_corner = f1_z1 + z_winder * wy_len / total_path if total_path > 1e-9 else f1_z1

        if render_outer:
            if flight1_treads > 0:
                # Outer flight 1: clipped at bottom and pitch-change newel faces
                f1_y0_oc, f1_z0_oc = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_oc = f1_y0 + t_c * dy1
                    f1_z0_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
                meshes.append(_stringer_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1))
                meshes.append(_handrail_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **hr_kw))
                meshes.append(_baserail_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **br_kw))
                pc_face_y = f1_y1 - hp
                if abs(dy1) > 1e-9:
                    t_sp = (pc_face_y - f1_y0) / dy1
                    f1_sp_z1 = f1_z0 + t_sp * (f1_z1 - f1_z0)
                else:
                    f1_sp_z1 = f1_z1
                meshes.extend(_spindles_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, pc_face_y, f1_sp_z1, **sp_kw))
            # Winder Y-piece: handrail/baserail/spindles from pitch-change newel to outer corner newel
            # Terminate Y-piece flush with front face of X-piece stringer (X-piece masters)
            st2 = STRINGER_THICKNESS / 2
            dy_w = outer_corner_y1 - f1_y1
            y_ext = outer_corner_y1 - st2
            z_y_ext = z_corner - st2 * (z_corner - f1_z1) / dy_w if abs(dy_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_y(f1_outer_x, f1_y1, f1_z1, y_ext, z_y_ext,
                                             clip_z_min=0 if flight1_treads == 0 else None))
            pc1_face_y_end = f1_y1 + hp
            oc_face_y = outer_corner_y1 - hp
            meshes.append(_handrail_flight_y(f1_outer_x, pc1_face_y_end, f1_z1, outer_corner_y1, z_corner, **hr_kw))
            meshes.append(_baserail_flight_y(f1_outer_x, pc1_face_y_end, f1_z1, outer_corner_y1, z_corner, **br_kw))
            meshes.extend(_spindles_flight_y(f1_outer_x, pc1_face_y_end, f1_z1, oc_face_y, z_corner, **sp_kw))
            # Winder X-piece: handrail/baserail/spindles from outer corner newel to pitch-change newel
            # X-piece extends to Y-piece outer face so upper flight masters at corner
            dx_w = f2_x_first - f1_outer_x
            x_ext = (f1_outer_x + st2) if turn1_dir == "left" else (f1_outer_x - st2)
            z_x_ext = z_corner + (x_ext - f1_outer_x) * (f2_z_first - z_corner) / dx_w if abs(dx_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y1, x_ext, z_x_ext, f2_x_first, f2_z_first))
            if turn1_dir == "left":
                oc_face_x = f1_outer_x - hp
                pc2_face_x = f2_x_first + hp
            else:
                oc_face_x = f1_outer_x + hp
                pc2_face_x = f2_x_first - hp
            meshes.append(_handrail_flight_x(outer_corner_y1, f1_outer_x, z_corner, f2_x_first, f2_z_first, **hr_kw))
            meshes.append(_baserail_flight_x(outer_corner_y1, f1_outer_x, z_corner, f2_x_first, f2_z_first, **br_kw))
            meshes.extend(_spindles_flight_x(outer_corner_y1, oc_face_x, z_corner, pc2_face_x, f2_z_first, **sp_kw))
            # Outer flight 2: from pitch-change newel to next pitch-change/top newel
            f2_dx = f2_x_last - f2_x_first
            if turn1_dir == "left":
                pc2_start_x = f2_x_first - hp
                pc2_end_x = f2_x_last + hp if actual_winders2 > 0 else f2_x_last + hp
            else:
                pc2_start_x = f2_x_first + hp
                pc2_end_x = f2_x_last - hp if actual_winders2 > 0 else f2_x_last - hp
            f2_x0_oc, f2_z0_oc = f2_x_first, f2_z_first
            f2_x1_oc, f2_z1_oc = f2_x_last, f2_z_last
            if abs(f2_dx) > 1e-9:
                t_c = max(0.0, min(1.0, (pc2_start_x - f2_x_first) / f2_dx))
                f2_x0_oc = f2_x_first + t_c * f2_dx
                f2_z0_oc = f2_z_first + t_c * (f2_z_last - f2_z_first)
                t_c2 = max(0.0, min(1.0, (pc2_end_x - f2_x_first) / f2_dx))
                f2_x1_oc = f2_x_first + t_c2 * f2_dx
                f2_z1_oc = f2_z_first + t_c2 * (f2_z_last - f2_z_first)
            meshes.append(_stringer_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc))
            meshes.append(_handrail_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **hr_kw))
            meshes.append(_baserail_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **br_kw))
            if abs(f2_dx) > 1e-9:
                meshes.extend(_spindles_flight_x(f2_outer_y, pc2_start_x, f2_z0_oc, pc2_end_x, f2_z1_oc, **sp_kw))
        else:
            # Extend winder corner stringers: upper flight masters lower
            st2 = STRINGER_THICKNESS / 2
            dy_w = outer_corner_y1 - f1_y1
            y_ext = outer_corner_y1 - st2
            z_y_ext = z_corner - st2 * (z_corner - f1_z1) / dy_w if abs(dy_w) > 1e-9 else z_corner
            if flight1_treads > 0:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(f1_outer_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))
                meshes.append(_stringer_flight_y(f1_outer_x, f1_y1, f1_z1, y_ext, z_y_ext))
            else:
                # Merge wall extension into winder Y-piece
                yp_slope = (z_corner - f1_z1) / (outer_corner_y1 - f1_y1) if abs(outer_corner_y1 - f1_y1) > 1e-9 else 0
                yp_y_start = f1_y1 - WALL_STRINGER_EXTENSION
                yp_z_start = f1_z1 - WALL_STRINGER_EXTENSION * yp_slope
                meshes.append(_stringer_flight_y(f1_outer_x, yp_y_start, yp_z_start, y_ext, z_y_ext, clip_z_min=0))
            dx_w = f2_x_first - f1_outer_x
            x_ext = (f1_outer_x + st2) if turn1_dir == "left" else (f1_outer_x - st2)
            z_x_ext = z_corner + (x_ext - f1_outer_x) * (f2_z_first - z_corner) / dx_w if abs(dx_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y1, x_ext, z_x_ext, f2_x_first, f2_z_first))
            meshes.append(_stringer_flight_x(f2_outer_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))

        # Flight 2 inner stringers
        if render_inner:
            meshes.append(_stringer_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))
            meshes.append(_handrail_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **hr_kw))
            meshes.append(_baserail_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **br_kw))
            f2_dx = f2_x_last - f2_x_first
            if abs(f2_dx) > 1e-9:
                if turn1_dir == "left":
                    c1_face_x = corner1_x - c1_hp
                    c2_face_x = corner2_x + c2_hp
                else:
                    c1_face_x = corner1_x + c1_hp
                    c2_face_x = corner2_x - c2_hp
                t0 = (c1_face_x - f2_x_first) / f2_dx
                t1 = (c2_face_x - f2_x_first) / f2_dx
                f2_sp_z0 = f2_z_first + t0 * (f2_z_last - f2_z_first)
                f2_sp_z1 = f2_z_first + t1 * (f2_z_last - f2_z_first)
                meshes.extend(_spindles_flight_x(f2_inner_y, c1_face_x, f2_sp_z0, c2_face_x, f2_sp_z1, **sp_kw))
            else:
                meshes.extend(_spindles_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **sp_kw))
        else:
            meshes.append(_stringer_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))

    if actual_winders2 > 0:
        nzs = rise * nosing / going
        # Flight 3 X positions
        if turn1_dir == turn2_dir:
            f3_outer_x = flight3_start_x + corner1_x
            f3_inner_x = flight3_start_x + width - corner1_x
        else:
            f3_outer_x = flight3_start_x + width - corner1_x
            f3_inner_x = flight3_start_x + corner1_x

        # Flight 3 coordinates
        f3_y_first = flight3_start_y - nosing + riser_t / 2 + flight3_shift_y
        f3_y_last = flight3_start_y - flight3_treads * going - nosing + riser_t / 2 + flight3_shift_y
        f3_z_first = flight3_riser_start * rise + nzs
        f3_z_last = (flight3_riser_start + flight3_treads) * rise + nzs
        z_fl = riser_t * rise / (2 * going)
        f3_y_last_fl = f3_y_last - riser_t / 2
        f3_z_last_fl = f3_z_last + z_fl
        top_face_y = top_post_y + hp
        dy3h = f3_y_last - f3_y_first

        if flight3_treads > 0:
            if render_inner:
                dy3s = f3_y_last_fl - f3_y_first
                f3_y_end_c, f3_z_end_c = f3_y_last_fl, f3_z_last_fl
                if abs(dy3s) > 1e-9 and top_face_y > f3_y_last_fl:
                    t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3s))
                    f3_y_end_c = f3_y_first + t_c * dy3s
                    f3_z_end_c = f3_z_first + t_c * (f3_z_last_fl - f3_z_first)
                f3_y_hr_c, f3_z_hr_c = f3_y_last, f3_z_last
                if abs(dy3h) > 1e-9 and top_face_y > f3_y_last:
                    t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3h))
                    f3_y_hr_c = f3_y_first + t_c * dy3h
                    f3_z_hr_c = f3_z_first + t_c * (f3_z_last - f3_z_first)
                meshes.append(_stringer_flight_y(f3_inner_x, f3_y_first, f3_z_first,
                                                 f3_y_end_c, f3_z_end_c))
                meshes.append(_handrail_flight_y(f3_inner_x, f3_y_first, f3_z_first,
                                                 f3_y_hr_c, f3_z_hr_c, **hr_kw))
                meshes.append(_baserail_flight_y(f3_inner_x, f3_y_first, f3_z_first,
                                                 f3_y_end_c, f3_z_end_c, **br_kw))
                c2_face_f3 = (corner2_y + c2_hp) if f3_y_first > corner2_y else (corner2_y - c2_hp)
                dy3_full = f3_y_last - f3_y_first
                if abs(dy3_full) > 1e-9:
                    t_sp3 = (c2_face_f3 - f3_y_first) / dy3_full
                    f3_sp_z0 = f3_z_first + t_sp3 * (f3_z_last - f3_z_first)
                else:
                    f3_sp_z0 = f3_z_first
                meshes.extend(_spindles_flight_y(f3_inner_x, c2_face_f3, f3_sp_z0,
                                                 f3_y_hr_c, f3_z_hr_c, **sp_kw))
            else:
                meshes.append(_stringer_flight_y_notched(f3_inner_x, f3_y_first, f3_z_first,
                                                         f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))

        # Turn 2 winder outer stringer geometry
        if turn1_dir == "left":
            f2_x_end = -(flight2_treads * going) - winder_offset1 - nosing - riser_t / 2
        else:
            f2_x_end = width + flight2_treads * going + winder_offset1 + nosing + riser_t / 2
        f2_z_end = (flight2_riser_start + flight2_treads) * rise + nzs
        outer_corner_y2 = corner2_y + width
        wx_len = abs(f3_outer_x - f2_x_end)
        wy_len = abs(outer_corner_y2 - f3_y_first)
        total_path = wx_len + wy_len
        z_winder = f3_z_first - f2_z_end
        z_corner = f2_z_end + z_winder * wx_len / total_path if total_path > 1e-9 else f2_z_end

        if render_outer:
            # Winder X-piece with balustrade (from pitch-change newel at f2 end to outer corner)
            # Extend stringer past corner by STRINGER_THICKNESS/2 to fill gap
            st2 = STRINGER_THICKNESS / 2
            dx_w2 = f3_outer_x - f2_x_end
            x_ext2 = f3_outer_x + (-st2 if dx_w2 > 0 else st2) if abs(dx_w2) > 1e-9 else f3_outer_x
            z_x_ext2 = z_corner - st2 * (z_corner - f2_z_end) / abs(dx_w2) if abs(dx_w2) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y2, f2_x_end, f2_z_end, x_ext2, z_x_ext2))
            if turn1_dir == "left":
                pc_f2end_face_x = f2_x_end - hp  # -X face toward X-piece
                oc2_face_x = f3_outer_x + hp  # +X face of outer corner newel
            else:
                pc_f2end_face_x = f2_x_end + hp
                oc2_face_x = f3_outer_x - hp
            meshes.append(_handrail_flight_x(outer_corner_y2, f2_x_end, f2_z_end, f3_outer_x, z_corner, **hr_kw))
            meshes.append(_baserail_flight_x(outer_corner_y2, f2_x_end, f2_z_end, f3_outer_x, z_corner, **br_kw))
            xw_dx = f3_outer_x - f2_x_end
            if abs(xw_dx) > 1e-9:
                meshes.extend(_spindles_flight_x(outer_corner_y2, pc_f2end_face_x, f2_z_end, oc2_face_x, z_corner, **sp_kw))
            # Winder Y-piece with balustrade (from outer corner to pitch-change newel at f3 start)
            # Extend stringer past corner by STRINGER_THICKNESS/2 to fill gap
            dy_w2 = f3_y_first - outer_corner_y2
            y_ext2 = outer_corner_y2 + st2
            z_y_ext2 = z_x_ext2  # match X-piece end height so top surfaces align at corner
            meshes.append(_stringer_flight_y(f3_outer_x, y_ext2, z_y_ext2, f3_y_first, f3_z_first))
            oc2_face_y = outer_corner_y2 - hp  # -Y face of outer corner newel
            pc_f3_face_y = f3_y_first + hp  # +Y face of pitch-change newel
            meshes.append(_handrail_flight_y(f3_outer_x, oc2_face_y, z_corner, f3_y_first, f3_z_first, **hr_kw))
            meshes.append(_baserail_flight_y(f3_outer_x, oc2_face_y, z_corner, f3_y_first, f3_z_first, **br_kw))
            meshes.extend(_spindles_flight_y(f3_outer_x, oc2_face_y, z_corner, pc_f3_face_y, f3_z_first, **sp_kw))
            if flight3_treads > 0:
                # Outer flight 3: from pitch-change newel face to top newel face
                pc_face_f3 = f3_y_first - hp
                top_face_y_out = top_post_y + hp
                f3_y0_oc, f3_z0_oc = f3_y_first, f3_z_first
                f3_y1_oc, f3_z1_oc = f3_y_last, f3_z_last
                if abs(dy3h) > 1e-9:
                    t_c0 = max(0.0, min(1.0, (pc_face_f3 - f3_y_first) / dy3h))
                    f3_y0_oc = f3_y_first + t_c0 * dy3h
                    f3_z0_oc = f3_z_first + t_c0 * (f3_z_last - f3_z_first)
                    t_c1 = max(0.0, min(1.0, (top_face_y_out - f3_y_first) / dy3h))
                    f3_y1_oc = f3_y_first + t_c1 * dy3h
                    f3_z1_oc = f3_z_first + t_c1 * (f3_z_last - f3_z_first)
                meshes.append(_stringer_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc))
                meshes.append(_handrail_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc, **hr_kw))
                meshes.append(_baserail_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc, **br_kw))
                if abs(dy3h) > 1e-9:
                    meshes.extend(_spindles_flight_y(f3_outer_x, pc_face_f3, f3_z0_oc, top_face_y_out, f3_z1_oc, **sp_kw))
        else:
            # Extend winder corner stringers by STRINGER_THICKNESS/2 to fill gap
            st2 = STRINGER_THICKNESS / 2
            dx_w2 = f3_outer_x - f2_x_end
            x_ext2 = f3_outer_x + (-st2 if dx_w2 > 0 else st2) if abs(dx_w2) > 1e-9 else f3_outer_x
            z_x_ext2 = z_corner - st2 * (z_corner - f2_z_end) / abs(dx_w2) if abs(dx_w2) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y2, f2_x_end, f2_z_end, x_ext2, z_x_ext2))
            dy_w2 = f3_y_first - outer_corner_y2
            y_ext2 = outer_corner_y2 + st2
            z_y_ext2 = z_x_ext2  # match X-piece end height so top surfaces align at corner
            if flight3_treads == 0:
                # Merge Y-piece with threshold notch into one stringer
                meshes.append(_stringer_flight_y_notched(f3_outer_x, y_ext2, z_y_ext2,
                                                         f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))
            else:
                meshes.append(_stringer_flight_y(f3_outer_x, y_ext2, z_y_ext2, f3_y_first, f3_z_first))
                meshes.append(_stringer_flight_y_notched(f3_outer_x, f3_y_first, f3_z_first,
                                                         f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))

    # --- Newel posts (top = 150mm above highest abutting handrail) ---
    NEWEL_CAP = 150.0
    hr_rise = p["handrail_rise"]
    nzs_hr = rise * nosing / going

    # Inner newel posts
    if render_inner:
        if flight1_treads > 0:
            hr_bot = rise + nzs_hr + hr_rise
            bot_h = hr_bot + NEWEL_CAP
            meshes.append(_box_mesh(corner1_x, bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355"))
        hr_c1_f1 = (flight1_treads + 1) * rise + nzs_hr + hr_rise
        hr_c1_f2 = flight2_riser_start * rise + nzs_hr + hr_rise
        c1_h = max(hr_c1_f1, hr_c1_f2) + NEWEL_CAP
        meshes.append(_box_mesh(corner1_x, corner1_y, c1_h / 2, c1_ns, c1_ns, c1_h, "#8B7355"))
        hr_c2_f2 = (flight2_riser_start + flight2_treads) * rise + nzs_hr + hr_rise
        hr_c2_f3 = flight3_riser_start * rise + nzs_hr + hr_rise
        c2_h = max(hr_c2_f2, hr_c2_f3) + NEWEL_CAP
        meshes.append(_box_mesh(corner2_x, corner2_y, c2_h / 2, c2_ns, c2_ns, c2_h, "#8B7355"))
        if flight3_treads > 0:
            # Top newel extends FROM cutting plane (150mm below stringer bottom) UPWARD
            pitch_line_top = (flight3_riser_start + flight3_treads) * rise + nzs_hr
            newel_bottom = pitch_line_top - 400.0
            newel_top = pitch_line_top + hr_rise + NEWEL_CAP
            top_h = newel_top - newel_bottom
            top_z_center = (newel_bottom + newel_top) / 2
            meshes.append(_box_mesh(corner2_x, top_post_y, top_z_center, ns, ns, top_h, "#8B7355"))
    else:
        # Wall condition on inner side: add stub newels at corners (no stringers)
        # Corner 1 stub newel - extends from landing 1 tread surface to stringer top
        pitch_c1_f1 = (flight1_treads + 1) * rise + nzs_hr
        pitch_c1_f2 = flight2_riser_start * rise + nzs_hr
        highest_abutment_c1 = max(pitch_c1_f1, pitch_c1_f2)
        stub_top_c1 = highest_abutment_c1 + STRINGER_PITCH_OFFSET
        landing1_tread_surface = turn1_winder_start * rise - tread_t
        stub_bottom_c1 = landing1_tread_surface
        stub_h_c1 = stub_top_c1 - stub_bottom_c1
        stub_z_center_c1 = (stub_top_c1 + stub_bottom_c1) / 2
        meshes.append(_box_mesh(corner1_x, corner1_y, stub_z_center_c1, ns, ns, stub_h_c1, "#8B7355"))
        # Corner 2 stub newel - extends from landing 2 tread surface to stringer top
        pitch_c2_f2 = (flight2_riser_start + flight2_treads) * rise + nzs_hr
        pitch_c2_f3 = flight3_riser_start * rise + nzs_hr
        highest_abutment_c2 = max(pitch_c2_f2, pitch_c2_f3)
        stub_top_c2 = highest_abutment_c2 + STRINGER_PITCH_OFFSET
        landing2_tread_surface = turn2_winder_start * rise - tread_t
        stub_bottom_c2 = landing2_tread_surface
        stub_h_c2 = stub_top_c2 - stub_bottom_c2
        stub_z_center_c2 = (stub_top_c2 + stub_bottom_c2) / 2
        meshes.append(_box_mesh(corner2_x, corner2_y, stub_z_center_c2, ns, ns, stub_h_c2, "#8B7355"))
        # Note: Stub stringers removed - they were causing green artifacts

    # Outer newel posts
    if render_outer:
        nzs_w = rise * nosing / going
        outer_x = width - corner1_x
        outer_y_pos = corner1_y + width
        if turn1_dir == turn2_dir:
            f3_outer_x_val = flight3_start_x + corner1_x
        else:
            f3_outer_x_val = flight3_start_x + width - corner1_x
        if turn1_dir == "left":
            f2_x0_val = -winder_offset1 - nosing - riser_t / 2
            f2_x_end_val = -(flight2_treads * going) - winder_offset1 - nosing - riser_t / 2
        else:
            f2_x0_val = width + winder_offset1 + nosing + riser_t / 2
            f2_x_end_val = width + flight2_treads * going + winder_offset1 + nosing + riser_t / 2
        f1_y1_val = flight1_treads * going + flight1_shift_y
        f3_y_first_val = flight3_start_y - nosing + riser_t / 2 + flight3_shift_y

        # Bottom newel
        if flight1_treads > 0:
            hr_bot = rise + nzs_w + hr_rise
            bot_h = hr_bot + NEWEL_CAP
            meshes.append(_box_mesh(outer_x, bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355"))

        # Turn 1 pitch-change at flight 1 end
        hr_pc1 = (flight1_treads + 1) * rise + nzs_w + hr_rise
        pc1_h = hr_pc1 + NEWEL_CAP
        meshes.append(_box_mesh(outer_x, f1_y1_val, pc1_h / 2, ns, ns, pc1_h, "#8B7355"))

        if actual_winders1 > 0:
            # Outer corner 1 (where Y-run meets X-run) - at last flight 1 tread level
            oc1_hr = (turn1_winder_start - 1) * rise + nzs_w + hr_rise
            oc1_h = oc1_hr + NEWEL_CAP
            meshes.append(_box_mesh(outer_x, outer_y_pos, oc1_h / 2, ns, ns, oc1_h, "#8B7355"))
            # Pitch-change at flight 2 start
            hr_pc_f2s = flight2_riser_start * rise + nzs_w + hr_rise
            pc_f2s_h = hr_pc_f2s + NEWEL_CAP
            meshes.append(_box_mesh(f2_x0_val, outer_y_pos, pc_f2s_h / 2, ns, ns, pc_f2s_h, "#8B7355"))
        else:
            # Flat landing at turn 1: outer corner at landing tread level
            oc1_hr = (turn1_winder_start - 1) * rise + nzs_w + hr_rise
            oc1_h = oc1_hr + NEWEL_CAP
            meshes.append(_box_mesh(outer_x, outer_y_pos, oc1_h / 2, ns, ns, oc1_h, "#8B7355"))
            hr_pc_f2s = flight2_riser_start * rise + nzs_w + hr_rise
            pc_f2s_h = hr_pc_f2s + NEWEL_CAP
            meshes.append(_box_mesh(f2_x0_val, outer_y_pos, pc_f2s_h / 2, ns, ns, pc_f2s_h, "#8B7355"))

        if actual_winders2 > 0:
            # Pitch-change at flight 2 end
            hr_pc_f2e = (flight2_riser_start + flight2_treads) * rise + nzs_w + hr_rise
            pc_f2e_h = hr_pc_f2e + NEWEL_CAP
            outer_corner_y2_val = corner2_y + width
            meshes.append(_box_mesh(f2_x_end_val, outer_corner_y2_val, pc_f2e_h / 2, ns, ns, pc_f2e_h, "#8B7355"))
            # Outer corner 2 (where X-run meets Y-run) - at last flight 2 tread level
            oc2_hr = (turn2_winder_start - 1) * rise + nzs_w + hr_rise
            oc2_h = oc2_hr + NEWEL_CAP
            meshes.append(_box_mesh(f3_outer_x_val, outer_corner_y2_val, oc2_h / 2, ns, ns, oc2_h, "#8B7355"))
            # Pitch-change at flight 3 start
            hr_pc_f3s = flight3_riser_start * rise + nzs_w + hr_rise
            pc_f3s_h = hr_pc_f3s + NEWEL_CAP
            meshes.append(_box_mesh(f3_outer_x_val, f3_y_first_val, pc_f3s_h / 2, ns, ns, pc_f3s_h, "#8B7355"))
        else:
            # Flat landing at turn 2: pitch-change at f2 end, outer corner, and f3 start
            outer_corner_y2_val = corner2_y + width
            hr_pc_t2a = (flight2_riser_start + flight2_treads) * rise + nzs_w + hr_rise
            pc_t2a_h = hr_pc_t2a + NEWEL_CAP
            meshes.append(_box_mesh(f2_x_end_val, outer_corner_y2_val, pc_t2a_h / 2, ns, ns, pc_t2a_h, "#8B7355"))
            # Outer corner 2 - at landing tread level
            oc2_hr = (turn2_winder_start - 1) * rise + nzs_w + hr_rise
            oc2_h = oc2_hr + NEWEL_CAP
            meshes.append(_box_mesh(f3_outer_x_val, outer_corner_y2_val, oc2_h / 2, ns, ns, oc2_h, "#8B7355"))
            # Pitch-change at flight 3 start
            hr_pc_t2b = flight3_riser_start * rise + nzs_w + hr_rise
            pc_t2b_h = hr_pc_t2b + NEWEL_CAP
            meshes.append(_box_mesh(f3_outer_x_val, f3_y_first_val, pc_t2b_h / 2, ns, ns, pc_t2b_h, "#8B7355"))

        # Top newel - extends FROM cutting plane (150mm below stringer bottom) UPWARD
        if flight3_treads > 0:
            pitch_line_top = (flight3_riser_start + flight3_treads) * rise + nzs_w
            newel_bottom = pitch_line_top - 400.0
            newel_top = pitch_line_top + hr_rise + NEWEL_CAP
            top_h = newel_top - newel_bottom
            top_z_center = (newel_bottom + newel_top) / 2
            meshes.append(_box_mesh(f3_outer_x_val, top_post_y, top_z_center, ns, ns, top_h, "#8B7355"))

    return meshes




# ────────────────────────────────────────────────────────────
# SHARED FUNCTIONS (from ifc_generator.py, no IfcOpenShell needed)
# ────────────────────────────────────────────────────────────

def compute_winder_geometry(newel_size, stair_width):
    """Compute winder construction geometry following the 4-step sequence.

    Step 1: Abstract layout — two flights at 90°, inner strings cross at junction.
    Step 2: Newel post centred on junction point (fixed, never moves).
    Step 3: Calculate offset and shift flights away from corner.
    Step 4: Determine winder division lines from post face marks.

    Returns a dict with:
        offset: how far each flight shifts along its axis
        effective_width: stair_width minus offset (warn if < 600mm)
        winder_centre_offset: offset from post centreline to winder centre point
        face_marks: [25mm, 75mm] from corner on each post face
        kite_going: 50mm (25+25 wrapped around corner)
        flank_going: 50mm (75-25 on each face)
        min_post_warning: True if newel_size < 75mm
    """
    half_post = newel_size / 2.0
    corner_allowance = 25.0  # mm from corner of post face
    min_going = 50.0  # mm minimum winder going

    # Step 3: offset = N/2 - 25mm
    offset = half_post - corner_allowance

    # Effective width at the turn after shifting
    effective_width = stair_width - offset

    # Winder centre point offset from post centreline
    winder_centre_offset = offset  # same as flight offset from centreline

    # Face marks from corner: 25mm (kite edge) and 75mm (flank edge)
    mark_kite = corner_allowance  # 25mm from corner
    mark_flank = corner_allowance + min_going  # 75mm from corner

    # Verify goings
    kite_going = corner_allowance + corner_allowance  # 25mm wraps around corner = 50mm
    flank_going = mark_flank - mark_kite  # 75 - 25 = 50mm

    return {
        "offset": offset,
        "effective_width": effective_width,
        "winder_centre_offset": winder_centre_offset,
        "mark_kite": mark_kite,
        "mark_flank": mark_flank,
        "kite_going": kite_going,
        "flank_going": flank_going,
        "min_post_warning": newel_size < 75.0,
        "width_warning": effective_width < 600.0,
    }


def _winder_profiles_from_construction(post_cx, post_cy, newel_size, stair_width,
                                         turn_direction, winder_index, num_winders=3,
                                         rotation=0, riser_extension=0,
                                         flight_extension=0, winder_x=25.0):
    """Generate winder tread profile using angular division lines.

    Division lines radiate from the winder centre point at equal angles
    (90° / num_winders). The winder centre is the intersection of the 25mm
    marks on the two post faces at the turn corner.

    The kite winder preserves the 25×25mm contact with the newel post corner.

    rotation: degrees to rotate the entire profile around (post_cx, post_cy).
              0 = flight approaches along +Y (turn 1 standard).
              -90 = flight approaches along -X (turn 2 after left turn 1).

    riser_extension: mm to extend the upper boundary of non-last winders
                     past the division line, so the riser above can sit on the tread.

    Angles measured from 0° (flight-1 outer string direction, along X)
    to 90° (flight-2 outer string direction, along Y).

    Args:
        post_cx, post_cy: post centreline position (fixed, Step 2)
        newel_size: post dimension (square)
        stair_width: nominal stair width
        turn_direction: 'left' or 'right'
        winder_index: 0-based index of this winder
        num_winders: total winders in this turn (2-4)
    Returns:
        list of (x, y) tuples defining the tread profile polygon
    """
    import math

    hp = newel_size / 2.0
    x_sign = 1.0 if turn_direction == "left" else -1.0

    # Post corner nearest turn interior (Face A and Face B meet here)
    pc_x = post_cx + x_sign * hp
    pc_y = post_cy + hp

    # Winder centre: intersection of winder_x marks on both post faces
    wc_x = pc_x - x_sign * winder_x
    wc_y = pc_y - winder_x

    # Outer string positions
    outer_f1_x = post_cx + x_sign * stair_width
    outer_f2_y = post_cy + stair_width

    # Post face edges
    post_bottom_y = post_cy - hp
    post_opp_x = post_cx - x_sign * hp

    # Angular division: 90° split into num_winders equal segments.
    # Inner contact points are FIXED at 25mm marks on the post faces.
    # Only the OUTER points follow angular rays from the winder centre.
    angle_step = (math.pi / 2.0) / num_winders

    def ray_outer(angle):
        """Where a ray from winder centre at angle hits the outer L-boundary."""
        dx = x_sign * math.cos(angle)
        dy = math.sin(angle)
        t_f1 = (outer_f1_x - wc_x) / dx if abs(dx) > 1e-9 else float('inf')
        t_f2 = (outer_f2_y - wc_y) / dy if abs(dy) > 1e-9 else float('inf')
        if t_f1 < 0: t_f1 = float('inf')
        if t_f2 < 0: t_f2 = float('inf')
        t = min(t_f1, t_f2)
        return (wc_x + dx * t, wc_y + dy * t)

    a0 = winder_index * angle_step
    a1 = (winder_index + 1) * angle_step

    outer_s = ray_outer(a0)
    outer_e = ray_outer(a1)

    # Angle to outer L-corner
    oc_dx = (outer_f1_x - wc_x) / x_sign
    oc_dy = outer_f2_y - wc_y
    a_outer_corner = math.atan2(oc_dy, oc_dx)
    straddles_outer = a0 < a_outer_corner < a1

    # Fixed 25mm inner marks on post faces
    mark_a = (pc_x, wc_y)   # 25mm mark on Face A (vertical face)
    mark_b = (wc_x, pc_y)   # 25mm mark on Face B (horizontal face)

    # Pre-compute riser extension points for non-last winders.
    # These extend the upper boundary (at a1) by riser_extension past
    # the division line so the riser above can sit on the tread.
    ext_inner = ext_outer = None
    if riser_extension > 0 and winder_index < num_winders - 1:
        a_ic = math.atan2(winder_x, winder_x)
        if a1 < a_ic - 1e-6:
            inner_a1 = mark_a
        elif a1 > a_ic + 1e-6:
            inner_a1 = mark_b
        else:
            inner_a1 = (pc_x, pc_y)
        dlx = outer_e[0] - inner_a1[0]
        dly = outer_e[1] - inner_a1[1]
        dl = math.sqrt(dlx * dlx + dly * dly)
        if dl > 1e-9:
            pnx = x_sign * (-dly / dl) * riser_extension
            pny = x_sign * (dlx / dl) * riser_extension
            ext_inner = (inner_a1[0] + pnx, inner_a1[1] + pny)
            # Clamp ext_inner to post face, preserving perpendicular
            # distance from the division line by sliding along it.
            ex, ey = ext_inner
            if abs(inner_a1[0] - pc_x) < 1e-6:
                # inner_a1 is on Face A — slide along division line to x = pc_x
                if abs(ex - pc_x) > 1e-6 and abs(dlx) > 1e-9:
                    t = (pc_x - ex) / dlx
                    ex = pc_x
                    ey = ey + t * dly
                else:
                    ex = pc_x
                ey = min(ey, pc_y)
            elif abs(inner_a1[1] - pc_y) < 1e-6:
                # inner_a1 is on Face B — slide along division line to y = pc_y
                if abs(ey - pc_y) > 1e-6 and abs(dly) > 1e-9:
                    t = (pc_y - ey) / dly
                    ex = ex + t * dlx
                    ey = pc_y
                else:
                    ey = pc_y
                if x_sign > 0:
                    ex = max(ex, post_opp_x)
                else:
                    ex = min(ex, post_opp_x)
            else:
                # At post corner — no inner extension needed
                ex = pc_x
                ey = pc_y
            ext_inner = (ex, ey)
            # Trace from ext_inner along division line to hit the outer
            # L-boundary so the tread extension is flush with the wall
            t_f1 = (outer_f1_x - ext_inner[0]) / dlx if abs(dlx) > 1e-9 else float('inf')
            t_f2 = (outer_f2_y - ext_inner[1]) / dly if abs(dly) > 1e-9 else float('inf')
            if t_f1 < 0: t_f1 = float('inf')
            if t_f2 < 0: t_f2 = float('inf')
            t = min(t_f1, t_f2)
            ext_outer = (ext_inner[0] + dlx * t, ext_inner[1] + dly * t)

    # First winder (flight-1 side flank)
    if winder_index == 0:
        # Extend leading edge toward flight 1 by flight_extension
        entry_y = post_bottom_y - flight_extension

        if flight_extension > 0:
            # Winder extends below post — full flight width with L-shaped
            # inner edge that wraps around the post bottom face
            profile = [
                (post_cx, entry_y),          # inner bottom at flight width
                (outer_f1_x, entry_y),       # outer bottom
            ]
        else:
            # Winder doesn't extend below post — inner edge at post face
            profile = [
                (pc_x, entry_y),             # inner bottom at post face
                (outer_f1_x, entry_y),       # outer bottom
            ]

        # outer_s is at a0=0 which is along flight-1 axis
        if straddles_outer:
            profile.append((outer_f1_x, outer_f2_y))
        profile.append(outer_e)          # angled outer point
        if ext_outer:
            profile.append(ext_outer)
            profile.append(ext_inner)
        profile.append(mark_a)           # fixed 25mm mark on Face A

        if flight_extension > 0:
            # Close the L-shape: down post face to post bottom, jog to flight edge
            profile.append((pc_x, post_bottom_y))
            profile.append((post_cx, post_bottom_y))

    # Last winder (flight-2 side flank)
    elif winder_index == num_winders - 1:
        # Extend rear edge toward flight 2 so it runs under flight 2's
        # first riser. Total extension = flight_extension + riser_extension.
        total_exit_ext = flight_extension + riser_extension
        exit_x = post_opp_x - x_sign * total_exit_ext

        if total_exit_ext > 0:
            # Exit extends past post — full flight width with L-shaped
            # inner edge that wraps around the post opposite face
            profile = [
                mark_b,                          # fixed 25mm mark on Face B
                (post_opp_x, pc_y),              # along post face to post edge
                (post_opp_x, post_cy),           # jog to flight inner edge
                (exit_x, post_cy),               # continue at flight width
                (exit_x, outer_f2_y),            # exit outer
            ]
        else:
            # Exit doesn't extend past post — inner edge at post face
            profile = [
                mark_b,                          # fixed 25mm mark on Face B
                (exit_x, pc_y),                  # exit edge inner
                (exit_x, outer_f2_y),            # exit edge outer
            ]

        # outer_e is at a1=90° which is along flight-2 axis
        if straddles_outer:
            profile.append((outer_f1_x, outer_f2_y))
        profile.append(outer_s)              # angled outer point

    # Middle winders (kite or half-kite)
    else:
        # Determine which part of the inner L-shape this winder gets.
        ic_dx = (pc_x - wc_x) / x_sign if x_sign != 0 else 1.0
        ic_dy = pc_y - wc_y
        a_inner_corner = math.atan2(ic_dy, ic_dx)
        a_mid = (a0 + a1) / 2.0

        if a_mid < a_inner_corner - 1e-6:
            # Face A side only (before post corner)
            profile = [mark_a, (pc_x, pc_y)]
        elif a_mid > a_inner_corner + 1e-6:
            # Face B side only (after post corner)
            profile = [(pc_x, pc_y), mark_b]
        else:
            # Straddles corner — full L-shape (kite)
            profile = [mark_a, (pc_x, pc_y), mark_b]

        # Insert extension before outer_e so tread extends past division line
        if ext_inner:
            profile.append(ext_inner)
            profile.append(ext_outer)
        profile.append(outer_e)
        if straddles_outer:
            profile.append((outer_f1_x, outer_f2_y))
        profile.append(outer_s)

    # Apply rotation around post centre if needed (for turn 2)
    if rotation != 0:
        rad = math.radians(rotation)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        rotated = []
        for (px, py) in profile:
            dx = px - post_cx
            dy = py - post_cy
            rx = cos_r * dx - sin_r * dy + post_cx
            ry = sin_r * dx + cos_r * dy + post_cy
            rotated.append((rx, ry))
        profile = rotated

    return profile


def check_building_regs(params):
    """
    Check parameters against Approved Document K (England & Wales) for private dwellings.
    Returns a list of check results.
    """
    p = _parse(params)
    checks = []

    rise = p["rise"]
    going = p["going"]
    width = p["stair_width"]
    num_winders = 0
    if p["staircase_type"] in ("single_winder", "double_winder"):
        num_winders = p["turn1_winders"]
    if p["staircase_type"] == "double_winder":
        num_winders += p["turn2_winders"]

    # Individual Rise: max 200mm warn, max 220mm block
    rise_status = "pass"
    rise_msg = f"Individual rise: {rise:.1f}mm"
    if rise > 220:
        rise_status = "fail"
        rise_msg += " — Exceeds absolute maximum of 220mm"
    elif rise > 200:
        rise_status = "warn"
        rise_msg += " — Exceeds recommended maximum of 200mm"
    checks.append({"name": "Individual Rise", "status": rise_status, "message": rise_msg, "value": round(rise, 1)})

    # Individual Going: min 220mm
    going_status = "pass"
    going_msg = f"Individual going: {going:.1f}mm"
    if going < 220:
        going_status = "warn"
        going_msg += " — Below minimum 220mm"
    checks.append({"name": "Individual Going", "status": going_status, "message": going_msg, "value": round(going, 1)})

    # Pitch: max 42° for straight flights
    pitch_rad = math.atan2(rise, going)
    pitch_deg = math.degrees(pitch_rad)
    pitch_status = "pass"
    pitch_msg = f"Pitch: {pitch_deg:.1f}°"
    if pitch_deg > 42:
        pitch_status = "warn"
        pitch_msg += " — Exceeds maximum 42° for private staircase"
    checks.append({"name": "Pitch", "status": pitch_status, "message": pitch_msg, "value": round(pitch_deg, 1)})

    # 2R + G formula: should be 550-700mm
    two_r_g = 2 * rise + going
    formula_status = "pass"
    formula_msg = f"2R + G = {two_r_g:.0f}mm"
    if two_r_g < 550 or two_r_g > 700:
        formula_status = "warn"
        formula_msg += f" — Outside comfortable range 550-700mm"
    checks.append({"name": "2R + G", "status": formula_status, "message": formula_msg, "value": round(two_r_g, 0)})

    # Stair Width: min 600mm
    width_status = "pass"
    width_msg = f"Stair width: {width:.0f}mm"
    if width < 600:
        width_status = "warn"
        width_msg += " — Below minimum 600mm for private dwellings"
    checks.append({"name": "Stair Width", "status": width_status, "message": width_msg, "value": round(width, 0)})

    # Newel post size: min 75mm to meet 50mm + 25mm bearing requirement
    has_winders = (p["staircase_type"] in ("single_winder", "double_winder")
                   and (p.get("turn1_enabled", True) or p.get("turn2_enabled", True)))
    if has_winders:
        newel = p["newel_size"]
        newel_status = "pass"
        newel_msg = f"Newel post size: {newel:.0f}mm"
        if newel < 75:
            newel_status = "warn"
            newel_msg += " — Below 75mm minimum (50mm bearing + 25mm corner wrap)"
        checks.append({"name": "Newel Post Size", "status": newel_status, "message": newel_msg,
                       "value": round(newel, 0)})

    # Winder going at narrow end using 4-step construction geometry
    return checks
