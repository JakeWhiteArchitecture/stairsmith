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
    p["newel_size"] = float(params.get("newel_size", 80))
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
    # Shift flight 1 back so it terminates at the post face
    flight1_shift_y = -hp if actual_winders > 0 else 0.0

    # Flight 1 treads (shifted back to post face)
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
            turn_dir, i, actual_winders)
        meshes.append({
            "type": "winder_polygon",
            "profile": [[pt[0], pt[1]] for pt in profile],
            "z": winder_z,
            "thickness": tread_t,
            "color": "#d4a574",
        })

    # Newel post (fixed position, Step 2)
    meshes.append(_box_mesh(
        corner_x, corner_y, p["floor_to_floor"] / 2,
        ns, ns, p["floor_to_floor"], "#8B7355"
    ))

    # Flight 2 treads (perpendicular, aligned so first tread's leading edge
    # meets the last winder's exit edge at the opposite post face)
    flight2_start_riser = winder_start_riser + actual_winders
    flight2_shift = hp + nosing + riser_t / 2 if actual_winders > 0 else 0.0
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

    riser_idx = 0
    flight1_shift_y = -hp if actual_winders1 > 0 else 0.0

    # Flight 1 (shifted back to post face)
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

    for i in range(actual_winders1):
        winder_z = (riser_idx + i) * rise - tread_t
        profile = _winder_profiles_from_construction(
            corner1_x, corner1_y, ns, width,
            turn1_dir, i, actual_winders1)
        meshes.append({
            "type": "winder_polygon",
            "profile": [[pt[0], pt[1]] for pt in profile],
            "z": winder_z,
            "thickness": tread_t,
            "color": "#d4a574",
        })

    # Newel post at turn 1
    meshes.append(_box_mesh(
        corner1_x, corner1_y, p["floor_to_floor"] / 2,
        ns, ns, p["floor_to_floor"], "#8B7355"
    ))

    riser_idx += actual_winders1

    # Flight 2 (perpendicular, aligned so first tread's leading edge
    # meets the last winder's exit edge at the opposite post face)
    flight2_shift = hp + nosing + riser_t / 2 if actual_winders1 > 0 else 0.0
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

    riser_idx += flight2_treads

    # Turn 2 winders — construction-based profiles
    # Place turn 2 post hp beyond flight 2's end (matching how flight 1
    # terminates at turn 1's post face)
    if turn1_dir == "left":
        flight2_end_x = -(flight2_treads * going) - flight2_shift
        corner2_x = flight2_end_x - hp
    else:
        flight2_end_x = width + flight2_treads * going + flight2_shift
        corner2_x = flight2_end_x + hp
    corner2_y = corner1_y

    # Turn 2 rotation: flight 2 approaches along -X (left) or +X (right)
    turn2_rotation = 90 if turn1_dir == "left" else -90

    for i in range(actual_winders2):
        winder_z = (riser_idx + i) * rise - tread_t
        profile = _winder_profiles_from_construction(
            corner2_x, corner2_y, ns, width,
            turn2_dir, i, actual_winders2,
            rotation=turn2_rotation)
        meshes.append({
            "type": "winder_polygon",
            "profile": [[pt[0], pt[1]] for pt in profile],
            "z": winder_z,
            "thickness": tread_t,
            "color": "#d4a574",
        })

    # Newel post at turn 2
    meshes.append(_box_mesh(
        corner2_x, corner2_y, p["floor_to_floor"] / 2,
        ns, ns, p["floor_to_floor"], "#8B7355"
    ))

    riser_idx += actual_winders2

    # Flight 3 — align nosing of first tread with turn 2 winder exit edge
    flight3_shift_y = -(hp + riser_t) if actual_winders2 > 0 else 0.0

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

    return meshes


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
