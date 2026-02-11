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
    p["turn1_winders"] = int(params.get("turn1_winders", 3))
    p["turn2_direction"] = params.get("turn2_direction", "left")
    p["turn2_winders"] = int(params.get("turn2_winders", 3))
    p["turn1_enabled"] = bool(params.get("turn1_enabled", True))
    p["turn2_enabled"] = bool(params.get("turn2_enabled", True))
    p["newel_size"] = float(params.get("newel_size", 90))
    # Winder X: distance from internal corner of newel along post face (min 25, max newel_size)
    raw_x = float(params.get("winder_x", 25))
    p["winder_x"] = max(25.0, min(p["newel_size"], raw_x))
    # Winder Y: going from X endpoint toward flight (min 50)
    raw_y = float(params.get("winder_y", 50))
    p["winder_y"] = max(50.0, raw_y)
    # Turn 2 winder X/Y (default to turn 1 values)
    raw_x2 = float(params.get("winder_x2", params.get("winder_x", 25)))
    p["winder_x2"] = max(25.0, min(p["newel_size"], raw_x2))
    raw_y2 = float(params.get("winder_y2", params.get("winder_y", 50)))
    p["winder_y2"] = max(50.0, raw_y2)
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

    # Flight 2 treads (perpendicular, offset by X+Y from internal corner)
    flight2_start_riser = winder_start_riser + actual_winders
    flight2_shift = (wx + wy - hp + nosing + riser_t / 2) if actual_winders > 0 else 0.0
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
                riser_x = -(i * going) + hp - wx - wy - nosing - riser_t / 2
            else:
                riser_x = width + i * going - hp + wx + wy + nosing + riser_t / 2
            meshes.append(_box_mesh(
                riser_x, corner_y + width / 2, riser_z,
                riser_t, width, riser_h, "#e8dcc8"
            ))

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

    # Newel post at turn 1
    meshes.append(_box_mesh(
        corner1_x, corner1_y, p["floor_to_floor"] / 2,
        ns, ns, p["floor_to_floor"], "#8B7355"
    ))

    riser_idx += actual_winders1
    flight2_riser_start = riser_idx

    # Flight 2 (perpendicular, offset by X+Y from internal corner)
    flight2_shift = (wx + wy - hp + nosing + riser_t / 2) if actual_winders1 > 0 else 0.0
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
                riser_x = -(i * going) + hp - wx - wy - nosing - riser_t / 2
            else:
                riser_x = width + i * going - hp + wx + wy + nosing + riser_t / 2
            meshes.append(_box_mesh(
                riser_x, corner1_y + width / 2, riser_z,
                riser_t, width, riser_h, "#e8dcc8"
            ))

    riser_idx += flight2_treads

    # Turn 2 winders — corner2 links flight 2 top riser (wx/wy) to turn 2 entry (wx2/wy2)
    if turn1_dir == "left":
        corner2_x = -(flight2_treads * going) + 2 * hp - wx - wy - wx2 - wy2
    else:
        corner2_x = width + flight2_treads * going - 2 * hp + wx + wy + wx2 + wy2
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

    # Newel post at turn 2
    meshes.append(_box_mesh(
        corner2_x, corner2_y, p["floor_to_floor"] / 2,
        ns, ns, p["floor_to_floor"], "#8B7355"
    ))

    riser_idx += actual_winders2
    flight3_riser_start = riser_idx

    # Flight 3 — shift by X2+Y2 from turn 2's internal corner
    flight3_shift_y = (hp - wx2 - wy2 - riser_t) if actual_winders2 > 0 else 0.0

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

    return meshes


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
