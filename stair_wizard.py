"""
StairSmith setup wizard — step definitions as plain data.

Each step is a dict with:
  id        — short string key
  title     — heading shown in the wizard
  subtitle  — one plain line under the heading
  fields    — list of number-field dicts (param, label, unit, default, min, max, step)
  toggles   — list of toggle-group dicts (param, label, options, optional show_for_types)
  ref_values — optional list of reference values shown in grey (see compute_ref_values)
  show      — callable(params) -> bool; whether the step applies to the chosen stair
  diagram   — name of the diagram function in stair_diagrams.py

Parameter names are those used by getParams() in app.html and _parse() in
stair_constants.py. The browser and the IngeTrazo extension both build their
wizard UI from this definition.
"""

from stair_constants import _parse, pitch_degrees

TURNING_TYPES = ("single_winder", "double_winder", "half_landing")


def _always(_p):
    return True


def _is_turning(p):
    return p.get("staircase_type", "straight") in ("single_winder", "double_winder")


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
        "subtitle": "Choose the layout and, for turning stairs, the hand.",
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
                # Sets turn1_direction and turn2_direction together (the sidebar mirror).
                "param": "turn1_direction",
                "label": "Hand",
                "show_for_types": list(TURNING_TYPES),
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
        "subtitle": "Finished floor to finished floor.",
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
        "subtitle": "Rise, treads and pitch are worked out for you and shown for information.",
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
                "label": "Going",
                "unit": "mm",
                "default": 227,
                "min": 220,
                "max": 300,
                "step": 1,
            },
            {
                "param": "nosing",
                "label": "Nosing",
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
        "subtitle": "Board thicknesses for the treads and risers.",
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
        "subtitle": "Overall width, what is on each side, and the newel size.",
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
        "subtitle": "Winders or a flat landing at each corner, then treads per flight.",
        "fields": [],
        "toggles": [],
        "show": _is_turning_or_half,
        "diagram": "step5_corners",
    },
    {
        "id": "winder_setout",
        "title": "Winder set-out",
        "subtitle": "Where the winders meet the newel. Applies to every winder corner.",
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


def steps_for_ui(params, available_diagrams=None):
    """Applicable steps as JSON-safe dicts (no callables).

    available_diagrams limits the list to steps whose diagram exists, so the
    wizard only offers steps that have been built.
    """
    out = []
    for s in get_steps_for_type(params):
        if available_diagrams is not None and s["diagram"] not in available_diagrams:
            continue
        out.append({k: v for k, v in s.items() if k != "show"})
    return out


def compute_ref_values(params):
    """Reference values shown in grey on the risers and going step."""
    p = _parse(params)
    return {
        "rise": round(p["rise"], 1),
        "treads": p["num_treads"],
        "pitch": round(pitch_degrees(p["rise"], p["going"]), 1),
    }
