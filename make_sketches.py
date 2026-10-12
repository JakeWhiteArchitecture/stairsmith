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
