"""Debug script: Generate L-shape stair DXF and capture winder debug output."""
import sys
import os

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from stair_preview import generate_preview_geometry
from stair_booleans import apply_boolean_ops
from dxf_generator import meshes_to_dxf

params = {
    "floor_to_floor": 2700,
    "stair_width": 900,
    "num_risers": 14,
    "going": 227,
    "tread_thickness": 22,
    "riser_thickness": 9,
    "nosing": 16,
    "threshold_depth": 100,
    "staircase_type": "single_winder",
    "turn1_direction": "left",
    "turn1_enabled": True,
    "turn2_direction": "left",
    "turn2_enabled": False,
    "newel_size": 90,
    "winder_x": 25,
    "winder_y": 50,
    "flight1_steps": -1,
    "flight2_steps": -1,
    "flight3_steps": -1,
    "handrail_width": 70,
    "handrail_height": 40,
    "handrail_rise": 900,
    "baserail_width": 50,
    "baserail_height": 30,
    "spindle_width": 32,
    "left_condition": "balustrade",
    "right_condition": "wall",
}

print("=== Generating preview geometry ===", flush=True)
meshes = generate_preview_geometry(params)

# Show winder-related meshes before boolean ops
print(f"\n=== Total meshes before booleans: {len(meshes)} ===", flush=True)
for i, m in enumerate(meshes):
    if "winder" in m.get("type", "").lower() or "winder" in m.get("ifc_type", "").lower():
        print(f"  mesh[{i}]: type={m.get('type')!r} ifc_type={m.get('ifc_type')!r} name={m.get('name')!r}", flush=True)

print("\n=== Applying boolean ops ===", flush=True)
meshes = apply_boolean_ops(meshes)

# Show winder-related meshes after boolean ops
print(f"\n=== Total meshes after booleans: {len(meshes)} ===", flush=True)
for i, m in enumerate(meshes):
    if "winder" in m.get("type", "").lower() or "winder" in m.get("ifc_type", "").lower():
        print(f"  mesh[{i}]: type={m.get('type')!r} ifc_type={m.get('ifc_type')!r} name={m.get('name')!r}", flush=True)

print("\n=== Generating DXF (winder debug output follows) ===", flush=True)
dxf_path = meshes_to_dxf(meshes, params)
print(f"\n=== DXF exported to: {dxf_path} ===", flush=True)
