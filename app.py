"""
IFC Staircase Generator — Flask Application

A locally-hosted web application that generates valid IFC 2x3 files
for parametric staircases (straight, single-winder, double-winder).
"""

import os
import json
from flask import Flask, render_template, request, jsonify, send_file
from ifc_generator import (create_ifc_staircase, check_building_regs,
                           compute_winder_geometry, _winder_profiles_from_construction)

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/preview", methods=["POST"])
def preview():
    """
    Return 3D geometry data as JSON for the Three.js preview.
    This generates the staircase geometry as mesh data without creating an IFC file.
    """
    params = request.get_json()
    try:
        geometry = generate_preview_geometry(params)
        return jsonify({"success": True, "geometry": geometry})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/check", methods=["POST"])
def check():
    """Run building regulations compliance checks."""
    params = request.get_json()
    try:
        results = check_building_regs(params)
        return jsonify({"success": True, "checks": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/download", methods=["POST"])
def download():
    """Generate and download an IFC file."""
    params = request.get_json()
    try:
        filepath = create_ifc_staircase(params)
        return send_file(
            filepath,
            as_attachment=True,
            download_name="staircase.ifc",
            mimetype="application/x-step",
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


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
    p["floor_to_floor"] = float(params.get("floor_to_floor", 2600))
    p["stair_width"] = float(params.get("stair_width", 810))
    p["num_risers"] = int(params.get("num_risers", 13))
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
    p["rise"] = p["floor_to_floor"] / p["num_risers"]
    p["num_treads"] = p["num_risers"] - 1
    p["num_risers_val"] = p["num_risers"]
    return p


def _box_mesh(x, y, z, w, d, h, color):
    """Create a box mesh definition for Three.js."""
    return {
        "type": "box",
        "position": [x, z, -y],  # swap Y/Z for Three.js (Y-up)
        "size": [w, h, d],
        "color": color,
    }


STRINGER_THICKNESS = 32.0        # mm
STRINGER_HEIGHT = 275.0          # mm
STRINGER_PITCH_OFFSET = 25.0     # mm – stringer top sits this far above the pitch line
STRINGER_DROP = 75.0                    # landing stringer top above tread plane
STRINGER_COLOR = "#b5a48a"

HANDRAIL_WIDTH = 70.0            # mm
HANDRAIL_HEIGHT = 40.0           # mm
HANDRAIL_RISE = 900.0            # mm – vertical from nosing pitch line to top of handrail
HANDRAIL_COLOR = "#8B7355"


def _stringer_flight_y(x_pos, y_start, z_start, y_end, z_end):
    """Stringer along a flight that runs in the Y direction.

    Returns a stringer mesh dict.  The profile is a parallelogram in the
    Y-Z plane, extruded by STRINGER_THICKNESS in X centred on *x_pos*.
    """
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off
    profile = [
        [y_start, z_start - drop],
        [y_end,   z_end - drop],
        [y_end,   z_end + off],
        [y_start, z_start + off],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
    }


def _stringer_flight_x(y_pos, x_start, z_start, x_end, z_end):
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
    }


def _stringer_landing_y(x_pos, y_start, y_end, z):
    """Flat (horizontal) stringer across a landing, running in Y.

    The stringer top sits STRINGER_DROP above z (the tread plane).
    """
    z_top = z + STRINGER_DROP
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
    }


def _stringer_landing_x(y_pos, x_start, x_end, z):
    """Flat (horizontal) stringer across a landing, running in X.

    The stringer top sits STRINGER_DROP above z (the tread plane).
    """
    z_top = z + STRINGER_DROP
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
    }


def _handrail_flight_y(x_pos, y_start, z_start, y_end, z_end):
    """Pitched handrail along Y.  z_start/z_end are nosing pitch-line z values.
    Top of handrail sits HANDRAIL_RISE above the pitch line.
    """
    top = HANDRAIL_RISE
    bot = HANDRAIL_RISE - HANDRAIL_HEIGHT
    profile = [
        [y_start, z_start + bot],
        [y_end,   z_end + bot],
        [y_end,   z_end + top],
        [y_start, z_start + top],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - HANDRAIL_WIDTH / 2,
        "thickness": HANDRAIL_WIDTH,
        "color": HANDRAIL_COLOR,
    }


def _handrail_flight_x(y_pos, x_start, z_start, x_end, z_end):
    """Pitched handrail along X.  z_start/z_end are nosing pitch-line z values."""
    top = HANDRAIL_RISE
    bot = HANDRAIL_RISE - HANDRAIL_HEIGHT
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
        "y": y_pos - HANDRAIL_WIDTH / 2,
        "thickness": HANDRAIL_WIDTH,
        "color": HANDRAIL_COLOR,
    }


def _stringer_flight_y_notched(x_pos, y_start, z_start, y_end, z_end, ftf, y_back, tread_t):
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
    }


def _stringer_flight_x_notched(y_pos, x_start, z_start, x_end, z_end, ftf, x_back, tread_t):
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
            width, tread_length, tread_t, "#c8a87c"
        ))

    riser_h = rise - tread_t
    for i in range(num_risers):
        riser_y = i * going
        riser_z = i * rise
        if riser_t > 0:
            meshes.append(_box_mesh(
                width / 2, riser_y + riser_t / 2, riser_z + riser_h / 2,
                width, riser_t, riser_h, "#e8dcc8"
            ))

    # --- Landing threshold strip ---
    ftf = num_risers * rise
    threshold_d = p["threshold_depth"]
    threshold_y = num_treads * going - nosing            # front (nosing overhang)
    threshold_back = num_treads * going - nosing + threshold_d
    meshes.append(_box_mesh(
        width / 2, threshold_y + threshold_d / 2, ftf - tread_t + tread_t / 2,
        width, threshold_d, tread_t, "#c8a87c"
    ))

    # --- Stringers (notched at top for threshold) ---
    nzs = rise * nosing / going
    y0 = 0.0
    y1 = num_treads * going + riser_t / 2       # flush with riser back face
    z0 = rise + nzs
    z1 = (num_treads + 1) * rise + nzs + riser_t * rise / (2 * going)
    meshes.append(_stringer_flight_y_notched(0.0, y0, z0, y1, z1, ftf, threshold_back, tread_t))
    meshes.append(_stringer_flight_y_notched(width, y0, z0, y1, z1, ftf, threshold_back, tread_t))

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
        })

    # Winder risers (between consecutive winder treads)
    meshes.extend(_winder_riser_meshes(
        corner_x, corner_y, ns, width, turn_dir,
        actual_winders, winder_start_riser, rise, tread_t, riser_t,
        nosing=nosing, winder_x=wx))

    # Newel post (fixed position, Step 2)
    meshes.append(_box_mesh(
        corner_x, corner_y, p["floor_to_floor"] / 2,
        ns, ns, p["floor_to_floor"], "#8B7355"
    ))

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
            landing_w, width, tread_t, "#c8a87c"
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
        threshold_d, width, tread_t, "#c8a87c"
    ))

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
        meshes.append(_stringer_flight_y(inner_x, f1_y0, f1_z0, f1_y1, f1_z1))
        meshes.append(_stringer_flight_y(outer_x, f1_y0, f1_z0, f1_y1_ext, z_ext))

        # Landing flat stringers — outer endpoints linked to flight stringer extensions
        t = STRINGER_THICKNESS
        if turn_dir == "left":
            meshes.append(_stringer_landing_x(corner_y, f2_x0, inner_x, landing_z_base))
            meshes.append(_stringer_landing_y(outer_x, f1_y1_ext, corner_y + width, landing_z_base))
            meshes.append(_stringer_landing_x(corner_y + width, f2_x0_ext, outer_x - t, landing_z_base))
        else:
            meshes.append(_stringer_landing_x(corner_y, inner_x, f2_x0, landing_z_base))
            meshes.append(_stringer_landing_y(outer_x, f1_y1_ext, corner_y + width, landing_z_base))
            meshes.append(_stringer_landing_x(corner_y + width, outer_x + t, f2_x0_ext, landing_z_base))

        # Flight 2 stringers (notched for threshold, flush with riser back)
        z_fl = riser_t * rise / (2 * going)
        f2_x1_fl = f2_x1 + (-riser_t / 2 if turn_dir == "left" else riser_t / 2)
        f2_z1_fl = f2_z1 + z_fl
        meshes.append(_stringer_flight_x_notched(inner_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl, ftf, thresh_back, tread_t))
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
        meshes.append(_stringer_flight_y(inner_x, f1_y0, f1_z0, f1_y1, f1_z1))
        meshes.append(_stringer_flight_y(outer_x, f1_y0, f1_z0, f1_y1, f1_z1))

        # Flight 2
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
        meshes.append(_stringer_flight_x_notched(inner_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl, ftf, thresh_back, tread_t))
        meshes.append(_stringer_flight_x_notched(outer_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl, ftf, thresh_back, tread_t))

        # Winder outer stringers (2 pieces along outer wall: Y then X)
        outer_corner_y = corner_y + width
        wy_len = abs(outer_corner_y - f1_y1)
        wx_len = abs(outer_x - f2_x0)
        total_path = wy_len + wx_len
        z_winder = f2_z0 - f1_z1
        z_corner = f1_z1 + z_winder * wy_len / total_path if total_path > 1e-9 else f1_z1
        # Y-piece (along flight 1 outer wall)
        meshes.append(_stringer_flight_y(outer_x, f1_y1, f1_z1, outer_corner_y, z_corner))
        # X-piece (along flight 2 outer wall)
        meshes.append(_stringer_flight_x(outer_corner_y, outer_x, z_corner, f2_x0, f2_z0))

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
            landing1_w, width, tread_t, "#c8a87c"
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
            width, width + ext, tread_t, "#c8a87c"
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
        width, threshold_d, tread_t, "#c8a87c"
    ))

    # Top newel post y position (centred on threshold nosing line)
    top_post_y = thresh_front_y

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
            # Clip inner stringer/handrail start at bottom post +Y face
            bot_face_y = bottom_post_y + hp
            f1_y0_c, f1_z0_c = f1_y0, f1_z0
            dy1 = f1_y1 - f1_y0
            if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                f1_y0_c = f1_y0 + t_c * dy1
                f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
            meshes.append(_stringer_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1))
            meshes.append(_handrail_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1))
            meshes.append(_stringer_flight_y(f1_outer_x, f1_y0, f1_z0, f1_y1_ext, z_ext1))

            # === Turn 1 landing stringers — outer endpoints linked to extensions ===
            t = STRINGER_THICKNESS
            if turn1_dir == "left":
                meshes.append(_stringer_landing_x(corner1_y, f2_x_first, f1_inner_x, landing1_z))
                meshes.append(_stringer_landing_y(f1_outer_x, f1_y1_ext, corner1_y + width, landing1_z))
                meshes.append(_stringer_landing_x(corner1_y + width, f2_x_first_ext, f1_outer_x - t, landing1_z))
            else:
                meshes.append(_stringer_landing_x(corner1_y, f1_inner_x, f2_x_first, landing1_z))
                meshes.append(_stringer_landing_y(f1_outer_x, f1_y1_ext, corner1_y + width, landing1_z))
                meshes.append(_stringer_landing_x(corner1_y + width, f1_outer_x + t, f2_x_first_ext, landing1_z))

            # === Flight 2 stringers ===
            meshes.append(_stringer_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))
            meshes.append(_handrail_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))
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
            t = STRINGER_THICKNESS
            # Y segment at f3_outer_x — start at flight 3 extended endpoint
            meshes.append(_stringer_landing_y(f3_outer_x, f3_y_first_ext, corner2_y + width, landing2_z))
            # X segment at outer Y — butt into Y stringer
            x_inner_end = f2_x_last_ext if f2_x_last_ext is not None else corner2_x
            if f3_outer_x < x_inner_end:
                meshes.append(_stringer_landing_x(corner2_y + width, x_inner_end, f3_outer_x + t, landing2_z))
            else:
                meshes.append(_stringer_landing_x(corner2_y + width, x_inner_end, f3_outer_x - t, landing2_z))

            # === Flight 3 stringers (notched for threshold, flush with riser back) ===
            z_fl = riser_t * rise / (2 * going)
            f3_y_last_fl = f3_y_last - riser_t / 2
            f3_z_last_fl = f3_z_last + z_fl
            # Inner stringer/handrail terminate at top post +Y face
            top_face_y = top_post_y + hp
            dy3s = f3_y_last_fl - f3_y_first
            f3_y_end_c, f3_z_end_c = f3_y_last_fl, f3_z_last_fl
            if abs(dy3s) > 1e-9 and top_face_y > f3_y_last_fl:
                t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3s))
                f3_y_end_c = f3_y_first + t_c * dy3s
                f3_z_end_c = f3_z_first + t_c * (f3_z_last_fl - f3_z_first)
            dy3h = f3_y_last - f3_y_first
            f3_y_hr_c, f3_z_hr_c = f3_y_last, f3_z_last
            if abs(dy3h) > 1e-9 and top_face_y > f3_y_last:
                t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3h))
                f3_y_hr_c = f3_y_first + t_c * dy3h
                f3_z_hr_c = f3_z_first + t_c * (f3_z_last - f3_z_first)
            meshes.append(_stringer_flight_y(f3_inner_x, f3_y_first, f3_z_first,
                                             f3_y_end_c, f3_z_end_c))
            meshes.append(_handrail_flight_y(f3_inner_x, f3_y_first, f3_z_first,
                                             f3_y_hr_c, f3_z_hr_c))
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
        # Clip inner stringer/handrail start at bottom post +Y face
        bot_face_y = bottom_post_y + hp
        f1_y0_c, f1_z0_c = f1_y0, f1_z0
        dy1 = f1_y1 - f1_y0
        if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
            t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
            f1_y0_c = f1_y0 + t_c * dy1
            f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
        meshes.append(_stringer_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1))
        meshes.append(_handrail_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1, f1_z1))
        meshes.append(_stringer_flight_y(f1_outer_x, f1_y0, f1_z0, f1_y1, f1_z1))

        # Flight 2 stringers
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
        meshes.append(_stringer_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))
        meshes.append(_handrail_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))
        meshes.append(_stringer_flight_x(f2_outer_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))

        # Turn 1 winder outer stringers (Y then X along outer wall)
        outer_corner_y1 = corner1_y + width
        wy_len = abs(outer_corner_y1 - f1_y1)
        wx_len = abs(f1_outer_x - f2_x_first)
        total_path = wy_len + wx_len
        z_winder = f2_z_first - f1_z1
        z_corner = f1_z1 + z_winder * wy_len / total_path if total_path > 1e-9 else f1_z1
        meshes.append(_stringer_flight_y(f1_outer_x, f1_y1, f1_z1, outer_corner_y1, z_corner))
        meshes.append(_stringer_flight_x(outer_corner_y1, f1_outer_x, z_corner, f2_x_first, f2_z_first))

    if actual_winders2 > 0:
        nzs = rise * nosing / going
        # Flight 3 X positions
        if turn1_dir == turn2_dir:
            f3_outer_x = flight3_start_x + corner1_x
            f3_inner_x = flight3_start_x + width - corner1_x
        else:
            f3_outer_x = flight3_start_x + width - corner1_x
            f3_inner_x = flight3_start_x + corner1_x

        # Flight 3 stringers (notched for threshold, flush with riser back)
        f3_y_first = flight3_start_y - nosing + riser_t / 2 + flight3_shift_y
        f3_y_last = flight3_start_y - flight3_treads * going - nosing + riser_t / 2 + flight3_shift_y
        f3_z_first = flight3_riser_start * rise + nzs
        f3_z_last = (flight3_riser_start + flight3_treads) * rise + nzs
        z_fl = riser_t * rise / (2 * going)
        f3_y_last_fl = f3_y_last - riser_t / 2
        f3_z_last_fl = f3_z_last + z_fl
        # Inner stringer/handrail terminate at top post +Y face
        top_face_y = top_post_y + hp
        dy3s = f3_y_last_fl - f3_y_first
        f3_y_end_c, f3_z_end_c = f3_y_last_fl, f3_z_last_fl
        if abs(dy3s) > 1e-9 and top_face_y > f3_y_last_fl:
            t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3s))
            f3_y_end_c = f3_y_first + t_c * dy3s
            f3_z_end_c = f3_z_first + t_c * (f3_z_last_fl - f3_z_first)
        dy3h = f3_y_last - f3_y_first
        f3_y_hr_c, f3_z_hr_c = f3_y_last, f3_z_last
        if abs(dy3h) > 1e-9 and top_face_y > f3_y_last:
            t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3h))
            f3_y_hr_c = f3_y_first + t_c * dy3h
            f3_z_hr_c = f3_z_first + t_c * (f3_z_last - f3_z_first)
        meshes.append(_stringer_flight_y(f3_inner_x, f3_y_first, f3_z_first,
                                         f3_y_end_c, f3_z_end_c))
        meshes.append(_handrail_flight_y(f3_inner_x, f3_y_first, f3_z_first,
                                         f3_y_hr_c, f3_z_hr_c))
        meshes.append(_stringer_flight_y_notched(f3_outer_x, f3_y_first, f3_z_first,
                                                 f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))

        # Turn 2 winder outer stringers (X then Y along outer wall)
        # Recompute flight 2 end position for this section
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
        # X-piece (along flight 2 outer wall)
        meshes.append(_stringer_flight_x(outer_corner_y2, f2_x_end, f2_z_end, f3_outer_x, z_corner))
        # Y-piece (along flight 3 outer wall)
        meshes.append(_stringer_flight_y(f3_outer_x, outer_corner_y2, z_corner, f3_y_first, f3_z_first))

    # --- Newel posts (top = 150mm above highest abutting handrail) ---
    NEWEL_CAP = 150.0
    nzs_hr = rise * nosing / going

    # Bottom newel: only flight 1 handrail abuts (at its start endpoint)
    hr_bot = rise + nzs_hr + HANDRAIL_RISE
    bot_h = hr_bot + NEWEL_CAP
    meshes.append(_box_mesh(
        corner1_x, bottom_post_y, bot_h / 2,
        ns, ns, bot_h, "#8B7355"
    ))

    # Corner 1: flight 1 end + flight 2 start — use the higher
    hr_c1_f1 = (flight1_treads + 1) * rise + nzs_hr + HANDRAIL_RISE
    hr_c1_f2 = flight2_riser_start * rise + nzs_hr + HANDRAIL_RISE
    c1_h = max(hr_c1_f1, hr_c1_f2) + NEWEL_CAP
    meshes.append(_box_mesh(
        corner1_x, corner1_y, c1_h / 2,
        ns, ns, c1_h, "#8B7355"
    ))

    # Corner 2: flight 2 end + flight 3 start — use the higher
    hr_c2_f2 = (flight2_riser_start + flight2_treads) * rise + nzs_hr + HANDRAIL_RISE
    hr_c2_f3 = flight3_riser_start * rise + nzs_hr + HANDRAIL_RISE
    c2_h = max(hr_c2_f2, hr_c2_f3) + NEWEL_CAP
    meshes.append(_box_mesh(
        corner2_x, corner2_y, c2_h / 2,
        ns, ns, c2_h, "#8B7355"
    ))

    # Top newel: only flight 3 handrail abuts (at its end endpoint)
    hr_top = (flight3_riser_start + flight3_treads) * rise + nzs_hr + HANDRAIL_RISE
    top_h = hr_top + NEWEL_CAP
    meshes.append(_box_mesh(
        corner2_x, top_post_y, top_h / 2,
        ns, ns, top_h, "#8B7355"
    ))

    return meshes


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
