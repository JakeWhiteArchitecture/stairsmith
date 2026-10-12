"""
StairSmith setup wizard — step definitions as plain data.

Each step is a dict with:
  id        — short string key
  title     — heading shown in the wizard
  subtitle  — one plain line under the heading
  subtitle_by_type — optional {staircase_type: subtitle} overriding subtitle
  fields    — list of number-field dicts (param, label, unit, default, min, max, step,
              optional show_for_types)
  toggles   — list of toggle-group dicts (param, label, options, optional show_for_types)
  widgets   — optional list of {id, label, show_for_types} for controls the UI provides
              itself (flight_distribution: treads per flight)
  ref_values — optional list of reference values shown in grey (see compute_ref_values)
  show      — callable(params) -> bool; whether the step applies to the chosen stair
  diagram   — name of the diagram function in stair_diagrams.py

Parameter names are those used by getParams() in app.html and _parse() in
stair_constants.py. The browser and the IngeTrazo extension both build their
wizard UI from this definition.
"""

from stair_constants import _parse, pitch_degrees

# The wizard sets corners to flat landings when it first opens; winders are
# chosen on the Corners step (the sidebar on its own defaults to winders).
WIZARD_START = {"turn1_enabled": False, "turn2_enabled": False}

TURNING_TYPES = ("single_winder", "double_winder", "half_landing")


def _always(_p):
    return True


def _is_turning(p):
    return p.get("staircase_type", "straight") in ("single_winder", "double_winder")


def _has_winders(p):
    t = p.get("staircase_type", "straight")
    if t == "single_winder":
        return bool(p.get("turn1_enabled"))     # an L has no second corner
    if t == "double_winder":
        return bool(p.get("turn1_enabled")) or bool(p.get("turn2_enabled"))
    return False


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
        "subtitle_by_type": {
            "half_landing": "Spacing of the newels either side of the well, and any extra landing width.",
        },
        "fields": [
            {
                "param": "landing_oversize",
                "label": "Landing oversize",
                "unit": "mm",
                "default": 0,
                "min": 0,
                "max": 2000,
                "step": 10,
                "show_for_types": ["half_landing"],
            },
        ],
        "toggles": [
            {
                # true means winders, as in getParams() and _parse()
                "param": "turn1_enabled",
                "label": "Corner 1",
                "show_for_types": ["single_winder", "double_winder"],
                "options": [
                    {"value": True, "label": "Winder Treads"},
                    {"value": False, "label": "Flat Landing"},
                ],
            },
            {
                "param": "turn2_enabled",
                "label": "Corner 2",
                "show_for_types": ["double_winder"],
                "options": [
                    {"value": True, "label": "Winder Treads"},
                    {"value": False, "label": "Flat Landing"},
                ],
            },
        ],
        # Treads per flight, using the sidebar's transferStep() and its limits.
        "widgets": [
            {"id": "flight_distribution", "label": "Treads per flight",
             "show_for_types": ["single_winder", "double_winder"]},
        ],
        "show": _is_turning_or_half,
        "diagram": "step5_corners",
    },
    {
        "id": "winder_setout",
        "title": "Winder set-out",
        "subtitle": "Measured down the newel face from its inside corner: winders start at X, "
                    "the flights meet the newel at Y. Applies to every winder corner.",
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


def wizard_start_values():
    """Values the wizard applies when it first opens on page load."""
    return dict(WIZARD_START)


def compute_ref_values(params):
    """Reference values shown in grey on the risers and going step."""
    p = _parse(params)
    return {
        "rise": round(p["rise"], 1),
        "treads": p["num_treads"],
        "pitch": round(pitch_degrees(p["rise"], p["going"]), 1),
    }
