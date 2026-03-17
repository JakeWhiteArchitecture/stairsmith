"""
Boolean operations for stair geometry export.

Applies CSG-style boolean subtractions before DXF/IFC export so that
exported geometry has proper joinery (mortice holes, housing notches)
rather than overlapping volumes.

Hierarchy (highest priority drawn first, subtracts from lower):
  1. Newel posts  — subtract from stringers and overlapping winder treads
  2. Flight treads/risers & winder treads — subtract from stringers
  3. Stringers    — receive subtractions, lowest priority

The preview model is NOT modified; only the exported copy is processed.
"""

import copy
from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry import box as shapely_box


# ── public API ──────────────────────────────────────────────

def apply_boolean_ops(meshes):
    """Return a deep copy of *meshes* with boolean subtractions applied.

    Does not modify the input list.
    """
    meshes = [copy.deepcopy(m) for m in meshes]

    # Classify meshes by role
    newels = [m for m in meshes if m.get("ifc_type") == "newel" and m.get("type") == "box"]
    flight_parts = [m for m in meshes
                    if m.get("ifc_type") in ("tread", "riser") and m.get("type") == "box"]
    winder_treads = [m for m in meshes
                     if m.get("ifc_type") == "winder_tread" and m.get("type") == "winder_polygon"]
    winder_risers = [m for m in meshes
                     if m.get("ifc_type") == "winder_riser" and m.get("type") == "winder_polygon"]

    # 1. Newels subtract from winder treads (XY boolean, Z-overlap gated)
    for wt in winder_treads:
        _subtract_boxes_from_winder(wt, newels)

    # 2. Newels subtract from stringers (profile-plane boolean)
    #    Then flight treads/risers subtract from stringers
    #    Then winder treads/risers subtract from stringers
    for m in meshes:
        if m.get("type") != "stringer" or m.get("ifc_type") != "stringer":
            continue
        _subtract_boxes_from_stringer(m, newels)
        _subtract_boxes_from_stringer(m, flight_parts)
        _subtract_winders_from_stringer(m, winder_treads + winder_risers)

    return meshes


# ── stringer subtraction ────────────────────────────────────

def _subtract_boxes_from_stringer(stringer, boxes):
    """Subtract box-type meshes from a stringer profile.

    Each box is projected onto the stringer's profile plane (YZ or XZ)
    and subtracted from the profile polygon, but only if the box
    overlaps the stringer's extrusion range.
    """
    profile_pts = [(float(p[0]), float(p[1])) for p in stringer["profile"]]
    profile_poly = Polygon(profile_pts)
    if profile_poly.is_empty or not profile_poly.is_valid:
        profile_poly = profile_poly.buffer(0)
        if profile_poly.is_empty:
            return

    axis = stringer.get("axis")
    if axis == "y":
        ext_lo = float(stringer["y"])
    else:
        ext_lo = float(stringer["x"])
    ext_hi = ext_lo + float(stringer["thickness"])

    changed = False
    for box in boxes:
        cx, cy, cz = box["ifc_center"]
        w, d, h = box["ifc_size"]

        if axis == "y":
            # Profile in XZ, extruded along Y
            b_lo, b_hi = cy - d / 2.0, cy + d / 2.0
            if b_hi <= ext_lo + 0.5 or b_lo >= ext_hi - 0.5:
                continue
            rect = shapely_box(cx - w / 2.0, cz - h / 2.0,
                               cx + w / 2.0, cz + h / 2.0)
        else:
            # Profile in YZ, extruded along X
            b_lo, b_hi = cx - w / 2.0, cx + w / 2.0
            if b_hi <= ext_lo + 0.5 or b_lo >= ext_hi - 0.5:
                continue
            rect = shapely_box(cy - d / 2.0, cz - h / 2.0,
                               cy + d / 2.0, cz + h / 2.0)

        if profile_poly.intersects(rect):
            result = profile_poly.difference(rect)
            if not result.is_empty:
                profile_poly = result
                changed = True

    if changed:
        _write_profile(stringer, profile_poly, fmt="list")


def _subtract_winders_from_stringer(stringer, winders):
    """Subtract winder-polygon meshes from a stringer profile.

    Each winder is an XY polygon extruded in Z.  We project its 3-D
    volume onto the stringer's profile plane and subtract.
    """
    profile_pts = [(float(p[0]), float(p[1])) for p in stringer["profile"]]
    profile_poly = Polygon(profile_pts)
    if profile_poly.is_empty or not profile_poly.is_valid:
        profile_poly = profile_poly.buffer(0)
        if profile_poly.is_empty:
            return

    axis = stringer.get("axis")
    if axis == "y":
        ext_lo = float(stringer["y"])
    else:
        ext_lo = float(stringer["x"])
    ext_hi = ext_lo + float(stringer["thickness"])

    changed = False
    for winder in winders:
        wpts = [(float(p[0]), float(p[1])) for p in winder["profile"]]
        if len(wpts) < 3:
            continue
        w_poly_xy = Polygon(wpts)
        if w_poly_xy.is_empty or not w_poly_xy.is_valid:
            w_poly_xy = w_poly_xy.buffer(0)
            if w_poly_xy.is_empty:
                continue

        z_lo = float(winder["z"])
        z_hi = z_lo + float(winder["thickness"])

        # Compute the winder's bounding box in the stringer's extrusion axis
        # to check for overlap
        xmin, ymin, xmax, ymax = w_poly_xy.bounds

        if axis == "y":
            # Stringer extruded along Y; check Y overlap
            if ymax <= ext_lo + 0.5 or ymin >= ext_hi - 0.5:
                continue
            # Project winder onto XZ: X range from polygon bounds, Z from extrusion
            rect = shapely_box(xmin, z_lo, xmax, z_hi)
        else:
            # Stringer extruded along X; check X overlap
            if xmax <= ext_lo + 0.5 or xmin >= ext_hi - 0.5:
                continue
            # Project winder onto YZ: Y range from polygon bounds, Z from extrusion
            rect = shapely_box(ymin, z_lo, ymax, z_hi)

        if profile_poly.intersects(rect):
            result = profile_poly.difference(rect)
            if not result.is_empty:
                profile_poly = result
                changed = True

    if changed:
        _write_profile(stringer, profile_poly, fmt="list")


# ── winder tread subtraction ────────────────────────────────

def _subtract_boxes_from_winder(winder, boxes):
    """Subtract box meshes from a winder-polygon tread in the XY plane.

    Only subtracts when the box's Z range overlaps the winder's Z range.
    """
    wpts = [(float(p[0]), float(p[1])) for p in winder["profile"]]
    wt_poly = Polygon(wpts)
    if wt_poly.is_empty or not wt_poly.is_valid:
        wt_poly = wt_poly.buffer(0)
        if wt_poly.is_empty:
            return

    z_lo = float(winder["z"])
    z_hi = z_lo + float(winder["thickness"])

    changed = False
    for box in boxes:
        cx, cy, cz = box["ifc_center"]
        w, d, h = box["ifc_size"]
        nz_lo, nz_hi = cz - h / 2.0, cz + h / 2.0
        if nz_hi <= z_lo + 0.5 or nz_lo >= z_hi - 0.5:
            continue
        newel_rect = shapely_box(cx - w / 2.0, cy - d / 2.0,
                                 cx + w / 2.0, cy + d / 2.0)
        if wt_poly.intersects(newel_rect):
            result = wt_poly.difference(newel_rect)
            if not result.is_empty:
                wt_poly = result
                changed = True

    if changed:
        _write_profile(winder, wt_poly, fmt="nested")


# ── helpers ─────────────────────────────────────────────────

def _write_profile(mesh, poly, fmt="list"):
    """Write a Shapely result back into the mesh dict.

    fmt="list"   → profile as [[a,b],[a,b],…]   (stringer convention)
    fmt="nested" → profile as [[x,y],[x,y],…]   (winder_polygon convention)

    If the result is a MultiPolygon, takes the largest piece.
    Stores interior rings in mesh["_holes"] for the IFC exporter to pick up.
    """
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: g.area)
    if poly.geom_type != "Polygon" or poly.is_empty:
        return

    coords = list(poly.exterior.coords[:-1])  # drop closing duplicate
    if fmt == "nested":
        mesh["profile"] = [[c[0], c[1]] for c in coords]
    else:
        mesh["profile"] = [list(c) for c in coords]

    holes = list(poly.interiors)
    if holes:
        if fmt == "nested":
            mesh["_holes"] = [[[c[0], c[1]] for c in h.coords[:-1]] for h in holes]
        else:
            mesh["_holes"] = [[list(c) for c in h.coords[:-1]] for h in holes]
    elif "_holes" in mesh:
        del mesh["_holes"]
