"""
IFC Staircase Generator — Flask Application

A locally-hosted web application that generates valid IFC 2x3 files
for parametric staircases (straight, single-winder, double-winder).
"""

import os
import json
from flask import Flask, render_template, request, jsonify, send_file
from ifc_generator import create_ifc_staircase, check_building_regs

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
    import math as _math
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
    p["newel_size"] = float(params.get("newel_size", 80))
    p["rise"] = p["floor_to_floor"] / p["num_risers"]
    p["num_treads"] = p["num_risers"] - 1
    p["num_risers_val"] = p["num_risers"]

    # Winder offset calculation (same as ifc_generator)
    hp = p["newel_size"] / 2.0
    g_min = 50.0
    if p["staircase_type"] in ("single_winder", "double_winder"):
        theta1 = (_math.pi / 2.0) / max(p["turn1_winders"], 1)
        p["turn1_offset"] = hp + g_min / _math.tan(theta1)
    if p["staircase_type"] == "double_winder":
        theta2 = (_math.pi / 2.0) / max(p["turn2_winders"], 1)
        p["turn2_offset"] = hp + g_min / _math.tan(theta2)

    return p


def _box_mesh(x, y, z, w, d, h, color):
    """Create a box mesh definition for Three.js."""
    return {
        "type": "box",
        "position": [x, z, -y],  # swap Y/Z for Three.js (Y-up)
        "size": [w, h, d],
        "color": color,
    }


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

    hp = p["newel_size"] / 2.0
    d = p.get("turn1_offset", hp) if actual_winders > 0 else 0.0
    inner_r = d - hp
    outer_r = width + hp - d

    # Flight 1 shifted: inner at x=hp for left turn
    f1_x = hp if turn_dir == "left" else 0.0
    for i in range(flight1_treads):
        tread_y = i * going - nosing
        tread_z = (i + 1) * rise - tread_t
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            f1_x + width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c"
        ))

    riser_h = rise - tread_t
    for i in range(flight1_treads + 1):
        if riser_t > 0:
            meshes.append(_box_mesh(
                f1_x + width / 2, i * going + riser_t / 2, i * rise + riser_h / 2,
                width, riser_t, riser_h, "#e8dcc8"
            ))

    winder_start_riser = flight1_treads + 1
    corner_y_int = flight1_treads * going

    # Winder centre: offset from internal corner
    if turn_dir == "left":
        cx = d
        cy = corner_y_int + d
    else:
        cx = width - d
        cy = corner_y_int + d

    # Post centre at internal corner
    post_cx = 0 if turn_dir == "left" else width
    post_cy = corner_y_int

    angle_per = (math.pi / 2) / max(actual_winders, 1)
    for i in range(actual_winders):
        winder_z = (winder_start_riser + i) * rise - tread_t
        meshes.append({
            "type": "winder",
            "position": [cx, winder_z, -cy],
            "outerR": outer_r,
            "innerR": inner_r,
            "thickness": tread_t,
            "angleStart": i * angle_per,
            "angleEnd": (i + 1) * angle_per,
            "color": "#d4a574",
            "turnDirection": turn_dir,
        })

    # Newel post at internal corner
    ns = p["newel_size"]
    meshes.append(_box_mesh(
        post_cx, post_cy, p["floor_to_floor"] / 2,
        ns, ns, p["floor_to_floor"], "#8B7355"
    ))

    # Flight 2: inner at y = corner_y_int + hp
    flight2_start_riser = winder_start_riser + actual_winders
    f2_y = corner_y_int + hp
    for i in range(flight2_treads):
        tread_z = (flight2_start_riser + i) * rise - tread_t
        if turn_dir == "left":
            tread_x = hp - (i * going) - going / 2 + nosing / 2
        else:
            tread_x = (width - hp) + i * going + going / 2 - nosing / 2
        meshes.append(_box_mesh(
            tread_x, f2_y + width / 2, tread_z + tread_t / 2,
            going + nosing + riser_t, width, tread_t, "#c8a87c"
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

    hp = p["newel_size"] / 2.0
    ns = p["newel_size"]
    d1 = p.get("turn1_offset", hp) if actual_winders1 > 0 else 0.0
    d2 = p.get("turn2_offset", hp) if actual_winders2 > 0 else 0.0
    inner_r1 = d1 - hp
    outer_r1 = width + hp - d1
    inner_r2 = d2 - hp
    outer_r2 = width + hp - d2

    riser_idx = 0

    # Flight 1: shifted so inner string at post face
    f1_x = hp if turn1_dir == "left" else 0.0
    for i in range(flight1_treads):
        tread_y = i * going - nosing
        tread_z = (i + 1) * rise - tread_t
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            f1_x + width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c"
        ))

    riser_h = rise - tread_t
    for i in range(flight1_treads + 1):
        if riser_t > 0:
            meshes.append(_box_mesh(
                f1_x + width / 2, i * going + riser_t / 2, i * rise + riser_h / 2,
                width, riser_t, riser_h, "#e8dcc8"
            ))

    riser_idx = flight1_treads + 1

    # Turn 1
    corner1_y_int = flight1_treads * going
    post1_cx = 0 if turn1_dir == "left" else width
    post1_cy = corner1_y_int
    if turn1_dir == "left":
        cx1 = d1
        cy1 = corner1_y_int + d1
    else:
        cx1 = width - d1
        cy1 = corner1_y_int + d1

    meshes.append(_box_mesh(
        post1_cx, post1_cy, p["floor_to_floor"] / 2,
        ns, ns, p["floor_to_floor"], "#8B7355"
    ))

    angle_per1 = (math.pi / 2) / max(actual_winders1, 1)
    for i in range(actual_winders1):
        winder_z = (riser_idx + i) * rise - tread_t
        meshes.append({
            "type": "winder",
            "position": [cx1, winder_z, -cy1],
            "outerR": outer_r1,
            "innerR": inner_r1,
            "thickness": tread_t,
            "angleStart": i * angle_per1,
            "angleEnd": (i + 1) * angle_per1,
            "color": "#d4a574",
            "turnDirection": turn1_dir,
        })

    riser_idx += actual_winders1

    # Flight 2: inner at y = corner1_y_int + hp
    f2_y = corner1_y_int + hp
    for i in range(flight2_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        if turn1_dir == "left":
            tread_x = hp - (i * going) - going / 2 + nosing / 2
        else:
            tread_x = (width - hp) + i * going + going / 2 - nosing / 2
        meshes.append(_box_mesh(
            tread_x, f2_y + width / 2, tread_z + tread_t / 2,
            going + nosing + riser_t, width, tread_t, "#c8a87c"
        ))

    riser_idx += flight2_treads

    # Turn 2
    if turn1_dir == "left":
        flight2_end_x = hp - (flight2_treads * going)
    else:
        flight2_end_x = (width - hp) + flight2_treads * going

    corner2_x_int = flight2_end_x
    corner2_y_int = corner1_y_int

    if turn1_dir == "left" and turn2_dir == "left":
        post2_cx = corner2_x_int
        post2_cy = corner2_y_int
        cx2 = corner2_x_int - d2
        cy2 = corner2_y_int - d2
    elif turn1_dir == "left" and turn2_dir == "right":
        post2_cx = corner2_x_int
        post2_cy = corner2_y_int + width
        cx2 = corner2_x_int - d2
        cy2 = corner2_y_int + width + d2
    elif turn1_dir == "right" and turn2_dir == "right":
        post2_cx = corner2_x_int
        post2_cy = corner2_y_int
        cx2 = corner2_x_int + d2
        cy2 = corner2_y_int - d2
    else:
        post2_cx = corner2_x_int
        post2_cy = corner2_y_int + width
        cx2 = corner2_x_int + d2
        cy2 = corner2_y_int + width + d2

    meshes.append(_box_mesh(
        post2_cx, post2_cy, p["floor_to_floor"] / 2,
        ns, ns, p["floor_to_floor"], "#8B7355"
    ))

    angle_per2 = (math.pi / 2) / max(actual_winders2, 1)
    for i in range(actual_winders2):
        winder_z = (riser_idx + i) * rise - tread_t
        meshes.append({
            "type": "winder_turn2",
            "position": [cx2, winder_z, -cy2],
            "outerR": outer_r2,
            "innerR": inner_r2,
            "thickness": tread_t,
            "angleStart": i * angle_per2,
            "angleEnd": (i + 1) * angle_per2,
            "color": "#d4a574",
            "turn1Direction": turn1_dir,
            "turn2Direction": turn2_dir,
        })

    riser_idx += actual_winders2

    # Flight 3
    if turn1_dir == "left" and turn2_dir == "left":
        flight3_start_x = post2_cx - hp - width
        flight3_start_y = post2_cy - hp
    elif turn1_dir == "right" and turn2_dir == "right":
        flight3_start_x = post2_cx + hp
        flight3_start_y = post2_cy - hp
    elif turn1_dir == "left" and turn2_dir == "right":
        flight3_start_x = post2_cx - hp
        flight3_start_y = post2_cy + hp
    else:
        flight3_start_x = post2_cx + hp - width
        flight3_start_y = post2_cy + hp

    for i in range(flight3_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        tread_y = flight3_start_y - (i + 1) * going - nosing
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            flight3_start_x + width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c"
        ))

    return meshes


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
