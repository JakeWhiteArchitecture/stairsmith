"""
Plan of the stair exactly as StairSmith builds it, for the wizard diagrams.

plan_geometry() runs the same generate_preview_geometry() that drives the 3D
preview, IFC and DXF, and returns the plan footprints of the parts a plan
diagram needs. Nothing here works out the stair independently, so a diagram
drawn from it always agrees with the 3D model.
"""

import re

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from stair_constants import STRINGER_THICKNESS, _parse
from stair_preview import generate_preview_geometry

_FLIGHT_TREAD = re.compile(r"^Flight (\d+) Tread \d+$")
_TURN = re.compile(r"^Turn(\d+) ")


def _box_rect(m):
    (cx, cy, _), (sx, sy, _) = m["ifc_center"], m["ifc_size"]
    return box(cx - sx / 2, cy - sy / 2, cx + sx / 2, cy + sy / 2)


def _box_top(m):
    return m["ifc_center"][2] + m["ifc_size"][2] / 2


def _extruded_rect(m):
    """Plan footprint of a 'stringer'-type mesh (profile extruded across its thickness)."""
    us = [pt[0] for pt in m["profile"]]
    if m.get("axis") == "y":
        return box(min(us), m["y"], max(us), m["y"] + m["thickness"]), "x"
    return box(m["x"], min(us), m["x"] + m["thickness"], max(us)), "y"


def plan_geometry(params):
    """Plan footprints of the computed stair.

    Returns a dict:
      elements  — walking surfaces (treads, winders, landings, threshold), each
                  {"kind", "name", "flight", "turn", "poly", "z"} with z the top level
      newels    — list of shapely boxes
      handrails — list of shapely boxes
      stringers — list of {"rect", "axis", "wall", "outward"}; wall is True where no
                  handrail runs over it, outward is the unit normal away from the treads
      flight_treads — {flight number: tread count} as built
      corners   — {turn number: {"kind": "winders"|"landing", "poly"}}
      footprint — union of the walking surfaces
      first_tread — the lowest tread element, or None
      params    — the parsed parameters
    """
    p = _parse(params)
    meshes = generate_preview_geometry(params)
    elements, newels, handrails, stringer_meshes = [], [], [], []
    for m in meshes:
        kind = m.get("ifc_type", "")
        name = m.get("name", "")
        if m["type"] == "box" and kind in ("tread", "landing", "threshold"):
            f = _FLIGHT_TREAD.match(name)
            elements.append({"kind": kind, "name": name, "flight": int(f.group(1)) if f else None,
                             "turn": None, "poly": _box_rect(m), "z": _box_top(m)})
        elif m["type"] == "winder_polygon" and kind in ("winder_tread", "landing"):
            t = _TURN.match(name)
            elements.append({"kind": "winder" if kind == "winder_tread" else "landing", "name": name,
                             "flight": None, "turn": int(t.group(1)) if t else None,
                             "poly": Polygon(m["profile"]).buffer(0), "z": m["z"] + m["thickness"]})
        elif m["type"] == "box" and kind == "newel":
            newels.append(_box_rect(m))
        elif m["type"] == "stringer" and kind == "handrail":
            handrails.append(_extruded_rect(m)[0])
        elif m["type"] == "stringer" and kind == "stringer":
            stringer_meshes.append(m)

    # Flat landings: "Landing" (single) or "Landing 1" / "Landing 2" (double).
    corners = {}
    for e in elements:
        if e["kind"] == "landing" and e["name"] != "Half Landing":
            num = re.search(r"(\d+)$", e["name"])
            corners[int(num.group(1)) if num else 1] = {"kind": "landing", "poly": e["poly"]}
    winders = {}
    for e in elements:
        if e["kind"] == "winder" and e["turn"]:
            winders.setdefault(e["turn"], []).append(e["poly"])
    for turn, polys in winders.items():
        corners[turn] = {"kind": "winders", "poly": unary_union(polys)}

    footprint = unary_union([e["poly"] for e in elements])
    rail_union = unary_union(handrails) if handrails else None
    newel_union = unary_union(newels) if newels else None
    stringers = []
    for m in stringer_meshes:
        rect, axis = _extruded_rect(m)
        x0, y0, x1, y1 = rect.bounds
        if axis == "y":
            centre = LineString([((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)])
            normals = ((-1.0, 0.0), (1.0, 0.0))
            half = (x1 - x0) / 2
        else:
            centre = LineString([(x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)])
            normals = ((0.0, -1.0), (0.0, 1.0))
            half = (y1 - y0) / 2
        # Judge wall vs balustrade on the length clear of newels: a short stringer
        # between two newels (the half-landing well) has rail only in the gap.
        clear = centre.difference(newel_union) if newel_union is not None else centre
        covered = rail_union.intersection(clear).length if rail_union is not None else 0.0
        mid = centre.interpolate(0.5, normalized=True)
        # Outward is the side farther from the walking surfaces.
        dists = [footprint.distance(box(mid.x + nx * (half + 2) - 0.5, mid.y + ny * (half + 2) - 0.5,
                                        mid.x + nx * (half + 2) + 0.5, mid.y + ny * (half + 2) + 0.5))
                 for nx, ny in normals]
        outward = normals[0] if dists[0] > dists[1] else normals[1]
        stringers.append({"rect": rect, "axis": axis, "centre": centre, "outward": outward,
                          "wall": clear.length > 1.0 and covered < 0.5 * clear.length})

    flight_treads = {}
    for e in elements:
        if e["flight"]:
            flight_treads[e["flight"]] = flight_treads.get(e["flight"], 0) + 1
    treads = [e for e in elements if e["kind"] == "tread"]
    return {
        "elements": sorted(elements, key=lambda e: e["z"]),
        "newels": newels,
        "handrails": handrails,
        "stringers": stringers,
        "flight_treads": flight_treads,
        "corners": corners,
        "footprint": footprint,
        "first_tread": min(treads, key=lambda e: e["z"]) if treads else None,
        "stringer_thickness": STRINGER_THICKNESS,
        "params": p,
    }


def flight_tread_counts(params):
    """Treads per flight as built, e.g. {1: 6, 2: 6}. JSON-friendly."""
    return {str(k): v for k, v in sorted(plan_geometry(params)["flight_treads"].items())}
