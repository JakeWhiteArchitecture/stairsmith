"""
StairSmith setup wizard — step definitions as plain data.

Each step is a dict with:
  id        — short string key
  title     — heading shown in the wizard
  fields    — list of field dicts (param, label, unit, default, min, max, step)
  toggles   — list of toggle-group dicts (param, label, options)
  show      — callable(params) -> bool; whether the step is visible
  diagram   — name of the diagram function in stair_diagrams.py

The JavaScript wizard reads these through Pyodide and builds the UI.
"""

import math


def _always(_p):
    return True


def _is_turning(p):
    t = p.get("staircase_type", "straight")
    return t in ("single_winder", "double_winder")


def _has_winders(p):
    if not _is_turning(p):
        return False
    return bool(p.get("turn1_enabled")) or bool(p.get("turn2_enabled"))


def _is_half_landing(p):
    return p.get("staircase_type") == "half_landing"


def _is_turning_or_half(p):
    return _is_turning(p) or _is_half_landing(p)


STEPS = [
    {
        "id": "stair_type",
        "title": "Stair type",
        "fields": [],
        "toggles": [
            {
                "param": "staircase_type",
                "label": "Layout",
                "options": [
                    {"value": "straight", "label": "Straight Flight"},
                    {"value": "single_winder", "label": "Single Winder (L-shape)"},
                    {"value": "double_winder", "label": "Double Winder (U-shape)"},
                    {"value": "half_landing", "label": "Half-Landing (U-shape)"},
                ],
            },
            {
                "param": "mirror",
                "label": "Hand",
                "options": [
                    {"value": "left", "label": "Left turn"},
                    {"value": "right", "label": "Right turn"},
                ],
            },
        ],
        "show": _always,
        "diagram": "step0_stair_type",
    },
    {
        "id": "height",
        "title": "Height",
        "fields": [
            {
                "param": "floor_to_floor",
                "label": "Floor to floor height",
                "unit": "mm",
                "default": 2700,
                "min": 2200,
                "max": 3200,
                "step": 10,
            },
        ],
        "toggles": [],
        "show": _always,
        "diagram": "step1_height",
    },
    {
        "id": "risers_going",
        "title": "Risers and going",
        "fields": [
            {
                "param": "num_risers",
                "label": "Number of risers",
                "unit": "",
                "default": 14,
                "min": 10,
                "max": 18,
                "step": 1,
            },
            {
                "param": "going",
                "label": "Individual going",
                "unit": "mm",
                "default": 227,
                "min": 220,
                "max": 300,
                "step": 1,
            },
            {
                "param": "nosing",
                "label": "Nosing overhang",
                "unit": "mm",
                "default": 16,
                "min": 0,
                "max": 25,
                "step": 1,
            },
        ],
        "toggles": [],
        "ref_values": ["rise", "treads", "pitch"],
        "show": _always,
        "diagram": "step2_risers_going",
    },
    {
        "id": "treads_risers",
        "title": "Treads and risers",
        "fields": [
            {
                "param": "tread_thickness",
                "label": "Tread thickness",
                "unit": "mm",
                "default": 22,
                "min": 18,
                "max": 40,
                "step": 1,
            },
            {
                "param": "riser_thickness",
                "label": "Riser thickness",
                "unit": "mm",
                "default": 9,
                "min": 0,
                "max": 18,
                "step": 1,
            },
        ],
        "toggles": [],
        "show": _always,
        "diagram": "step3_treads_risers",
    },
    {
        "id": "width_sides",
        "title": "Width, sides and newels",
        "fields": [
            {
                "param": "stair_width",
                "label": "Stair width (outside to outside)",
                "unit": "mm",
                "default": 900,
                "min": 600,
                "max": 1200,
                "step": 10,
            },
            {
                "param": "newel_size",
                "label": "Newel post size",
                "unit": "mm",
                "default": 90,
                "min": 75,
                "max": 120,
                "step": 5,
            },
        ],
        "toggles": [
            {
                "param": "left_condition",
                "label": "Left side",
                "options": [
                    {"value": "balustrade", "label": "Balustrade"},
                    {"value": "wall", "label": "Wall"},
                ],
            },
            {
                "param": "right_condition",
                "label": "Right side",
                "options": [
                    {"value": "balustrade", "label": "Balustrade"},
                    {"value": "wall", "label": "Wall"},
                ],
            },
        ],
        "show": _always,
        "diagram": "step4_width_sides",
    },
    {
        "id": "corners",
        "title": "Corners",
        "fields": [],
        "toggles": [],
        "show": _is_turning_or_half,
        "diagram": "step5_corners",
    },
    {
        "id": "winder_setout",
        "title": "Winder set-out",
        "fields": [
            {
                "param": "winder_x",
                "label": "Winder X",
                "unit": "mm",
                "default": 25,
                "min": 25,
                "max": 120,
                "step": 1,
            },
            {
                "param": "winder_y",
                "label": "Winder Y",
                "unit": "mm",
                "default": 50,
                "min": 50,
                "max": 200,
                "step": 1,
            },
        ],
        "toggles": [],
        "show": _has_winders,
        "diagram": "step6_winder_setout",
    },
]


def get_steps_for_type(params):
    """Return the list of step dicts applicable to the given params."""
    return [s for s in STEPS if s["show"](params)]


def get_step_ids_for_type(params):
    """Return just the step IDs applicable to the given params."""
    return [s["id"] for s in STEPS if s["show"](params)]


def compute_ref_values(params):
    """Compute the reference values shown in the wizard."""
    ftf = float(params.get("floor_to_floor", 2700))
    risers = int(params.get("num_risers", 14))
    going = float(params.get("going", 227))
    rise = ftf / risers
    treads = risers - 1
    pitch = math.degrees(math.atan2(rise, going))
    return {
        "rise": round(rise, 1),
        "treads": treads,
        "pitch": round(pitch, 1),
    }
