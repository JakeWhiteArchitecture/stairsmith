"""
Stair Preview Engine — thin facade module for Pyodide.

Imports all sub-modules and exposes the two public entry points:
  generate_preview_geometry(params) -> list[mesh]
  check_building_regs(params)       -> list[check]
"""

from stair_constants import _parse, _box_mesh, _BOX_COLOR_TO_IFC
from stair_winder_geometry import compute_winder_geometry
from stair_flights import (
    _preview_straight,
    _preview_single_winder,
    _preview_double_winder,
)
from stair_regs import check_building_regs  # noqa: F401 — re-exported


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

    return []
