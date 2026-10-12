#!/usr/bin/env python3
"""Render wizard diagram SVGs to sketches/ for visual review.

Uses the same stair_diagrams functions the browser calls, so what is written
here is what the wizard shows. Includes extreme values to check fit.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stair_diagrams import get_diagram  # noqa: E402

SKETCH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sketches")

CASES = [
    ("step0_straight", "step0_stair_type", {"staircase_type": "straight"}),
    ("step0_single_winder", "step0_stair_type", {"staircase_type": "single_winder"}),
    ("step0_double_winder", "step0_stair_type", {"staircase_type": "double_winder"}),
    ("step0_half_landing", "step0_stair_type", {"staircase_type": "half_landing"}),
    ("step1_2200", "step1_height", {"floor_to_floor": 2200}),
    ("step1_2700", "step1_height", {"floor_to_floor": 2700}),
    ("step1_3200", "step1_height", {"floor_to_floor": 3200}),
    ("step2_default", "step2_risers_going", {}),
    ("step2_steep", "step2_risers_going", {"floor_to_floor": 3200, "num_risers": 10, "going": 220}),
    ("step2_shallow", "step2_risers_going", {"floor_to_floor": 2200, "num_risers": 18, "going": 300, "nosing": 0}),
    ("step3_default", "step3_treads_risers", {}),
    ("step3_thick", "step3_treads_risers", {"floor_to_floor": 3200, "num_risers": 10, "going": 300,
                                            "tread_thickness": 40, "riser_thickness": 18, "nosing": 25}),
    ("step3_no_riser", "step3_treads_risers", {"riser_thickness": 0}),
    ("step4_straight", "step4_width_sides", {"staircase_type": "straight"}),
    ("step4_straight_inverted", "step4_width_sides",
     {"staircase_type": "straight", "left_condition": "wall", "right_condition": "balustrade"}),
    ("step4_single", "step4_width_sides", {"staircase_type": "single_winder"}),
    ("step4_single_right", "step4_width_sides", {"staircase_type": "single_winder", "turn1_direction": "right",
                                                 "turn2_direction": "right"}),
    ("step4_double", "step4_width_sides", {"staircase_type": "double_winder"}),
    ("step4_half_landing", "step4_width_sides", {"staircase_type": "half_landing"}),
    ("step4_half_landing_inner_wall", "step4_width_sides",
     {"staircase_type": "half_landing", "left_condition": "wall"}),
    ("step5_single_landing", "step5_corners", {"staircase_type": "single_winder"}),
    ("step5_single_winders", "step5_corners", {"staircase_type": "single_winder", "turn1_enabled": True}),
    ("step5_double_mixed", "step5_corners", {"staircase_type": "double_winder", "turn1_enabled": True}),
    ("step5_double_right", "step5_corners", {"staircase_type": "double_winder", "turn1_direction": "right",
                                             "turn2_direction": "right", "turn2_enabled": True}),
    ("step5_half_landing", "step5_corners", {"staircase_type": "half_landing"}),
    ("step6_left", "step6_winder_setout", {"staircase_type": "single_winder", "turn1_enabled": True}),
    ("step6_right_large", "step6_winder_setout", {"staircase_type": "single_winder", "turn1_enabled": True,
                                                  "turn1_direction": "right", "turn2_direction": "right",
                                                  "winder_x": 60, "winder_y": 120}),
    ("step6_double_turn2", "step6_winder_setout", {"staircase_type": "double_winder", "turn2_enabled": True}),
]


def main():
    os.makedirs(SKETCH_DIR, exist_ok=True)
    for name, diagram, params in CASES:
        path = os.path.join(SKETCH_DIR, f"{name}.svg")
        with open(path, "w") as f:
            f.write(get_diagram(diagram, params))
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
