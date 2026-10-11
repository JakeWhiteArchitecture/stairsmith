#!/usr/bin/env python3
"""Render wizard diagram SVGs to sketches/ for visual review."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stair_diagrams import step0_stair_type, step1_height

SKETCH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sketches")


def main():
    os.makedirs(SKETCH_DIR, exist_ok=True)

    for type_id in ("straight", "single_winder", "double_winder", "half_landing"):
        svg = step0_stair_type({"staircase_type": type_id})
        path = os.path.join(SKETCH_DIR, f"step0_{type_id}.svg")
        with open(path, "w") as f:
            f.write(svg)
        print(f"  wrote {path}")

    for ftf in (2200, 2700, 3200):
        svg = step1_height({"floor_to_floor": ftf})
        path = os.path.join(SKETCH_DIR, f"step1_{ftf}.svg")
        with open(path, "w") as f:
            f.write(svg)
        print(f"  wrote {path}")

    print(f"\nDone. {len(os.listdir(SKETCH_DIR))} files in {SKETCH_DIR}/")


if __name__ == "__main__":
    main()
