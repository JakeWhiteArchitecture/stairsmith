"""
Stair Preview Engine — thin facade module for Pyodide.

Imports all sub-modules and exposes the public entry points:
  generate_preview_geometry(params) -> list[mesh]
  check_building_regs(params)       -> list[check]
"""

import math

from stair_constants import _parse, _box_mesh, _BOX_COLOR_TO_IFC
from stair_winder_geometry import compute_winder_geometry
from stair_flights import (
    _preview_straight,
    _preview_single_winder,
    _preview_double_winder,
    _preview_y_shaped,
)


def generate_preview_geometry(params):
    """
    Generate Three.js-compatible geometry data for live preview.
    Returns lists of meshes with vertices and faces.
    """
    p = _parse(params)

    stair_type = p["staircase_type"]

    if stair_type == "straight":
        return _preview_straight(p)
    elif stair_type == "single_winder":
        return _preview_single_winder(p)
    elif stair_type == "double_winder":
        return _preview_double_winder(p)
    elif stair_type == "y_shaped":
        return _preview_y_shaped(p)

    return []


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
