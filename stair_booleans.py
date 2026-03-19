"""
Boolean operations for stair geometry export.

Applies CSG-style boolean subtractions before DXF/IFC export so that
exported geometry has proper joinery (mortice holes, housing notches)
rather than overlapping volumes.

Hierarchy (highest priority drawn first, subtracts from lower):
  1. Newel posts  — subtract from winder treads, winder risers, and stringers
  2. Flight treads/risers & winder treads/risers — subtract from stringers
  3. Stringers    — subtract from flight treads/risers (trim boxes at stringer edges)

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
    stringers = [m for m in meshes
                 if m.get("type") == "stringer" and m.get("ifc_type") == "stringer"]

    # 1. Newels subtract from winder treads and winder risers (XY boolean, Z-overlap gated)
    for wt in winder_treads:
        _subtract_boxes_from_winder(wt, newels)
    for wr in winder_risers:
        _subtract_boxes_from_winder(wr, newels)

    # 1b. Clip winder treads at corner-newel faces so they don't extend
    #     past the newel into the flight zone.  Clipped area is transferred
    #     to the adjacent winder so there is no gap.
    _clip_winders_at_newel_faces(winder_treads, newels)

    # 2. Newels subtract from stringers (profile-plane boolean)
    #    Then flight treads/risers subtract from stringers
    #    Then winder treads/risers subtract from stringers
    for m in stringers:
        _subtract_boxes_from_stringer(m, newels)
        _subtract_boxes_from_stringer(m, flight_parts)
        _subtract_winders_from_stringer(m, winder_treads + winder_risers)

    # 3. Stringers trim flight treads/risers (trim box edges where they
    #    overlap stringers, same concept as winder treads cut by newels)
    _trim_boxes_by_stringers(flight_parts, stringers)

    return meshes


# ── stringer subtraction ────────────────────────────────────

def _safe_subtract(profile_poly, rect):
    """Subtract *rect* from *profile_poly*, protecting against through-cuts.

    If the subtraction would split the profile into multiple pieces
    (MultiPolygon), try progressively shrinking the rect.  If the cut
    cannot be made without splitting, return the profile unchanged and
    False; otherwise return (result, True).
    """
    result = profile_poly.difference(rect)
    if result.is_empty:
        return profile_poly, False
    if not isinstance(result, MultiPolygon):
        return result, True

    # Through-cut detected — try shrinking the rect to avoid splitting
    for shrink in (1.0, 2.0, 4.0, 8.0):
        smaller = rect.buffer(-shrink)
        if smaller.is_empty:
            break
        r2 = profile_poly.difference(smaller)
        if r2.is_empty:
            break
        if not isinstance(r2, MultiPolygon):
            return r2, True

    # Could not avoid split — skip this cut entirely
    return profile_poly, False


def _subtract_boxes_from_stringer(stringer, boxes):
    """Subtract box-type meshes from a stringer profile.

    Each box is projected onto the stringer's profile plane (YZ or XZ)
    and subtracted from the profile polygon, but only if the box
    overlaps the stringer's extrusion range.  Through-cuts that would
    split the stringer are prevented.
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
            profile_poly, did_cut = _safe_subtract(profile_poly, rect)
            if did_cut:
                changed = True

    if changed:
        _write_profile(stringer, profile_poly, fmt="list")


def _subtract_winders_from_stringer(stringer, winders):
    """Subtract winder-polygon meshes from a stringer profile.

    Each winder is an XY polygon extruded in Z.  We clip the winder
    polygon to the stringer's extrusion band first, so only the actual
    overlap region is projected — this prevents the full bounding-box
    from creating through-cuts.
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

        # Clip the winder XY polygon to the stringer's extrusion band.
        # This gives us only the sliver of the winder that actually sits
        # inside the stringer volume, producing much tighter projection
        # bounds and preventing through-cuts.
        if axis == "y":
            # Stringer extruded along Y — clip winder to Y band
            clip = shapely_box(-1e9, ext_lo, 1e9, ext_hi)
            clipped = w_poly_xy.intersection(clip)
            if clipped.is_empty:
                continue
            xmin, ymin, xmax, ymax = clipped.bounds
            # Project clipped overlap onto XZ
            rect = shapely_box(xmin, z_lo, xmax, z_hi)
        else:
            # Stringer extruded along X — clip winder to X band
            clip = shapely_box(ext_lo, -1e9, ext_hi, 1e9)
            clipped = w_poly_xy.intersection(clip)
            if clipped.is_empty:
                continue
            xmin, ymin, xmax, ymax = clipped.bounds
            # Project clipped overlap onto YZ
            rect = shapely_box(ymin, z_lo, ymax, z_hi)

        if profile_poly.intersects(rect):
            profile_poly, did_cut = _safe_subtract(profile_poly, rect)
            if did_cut:
                changed = True

    if changed:
        _write_profile(stringer, profile_poly, fmt="list")


# ── flight tread/riser trimming by stringers ───────────────

def _trim_boxes_by_stringers(boxes, stringers):
    """Trim flight tread/riser boxes where they overlap with stringers.

    For each box, if it overlaps a stringer in the stringer's extrusion
    axis, shrink the box so it no longer intrudes into the stringer volume.
    This is analogous to how winder treads are cut by newel posts.
    """
    for box in boxes:
        for stringer in stringers:
            # Re-read box dimensions each iteration (may have been trimmed
            # by a previous stringer)
            cx, cy, cz = box["ifc_center"]
            w, d, h = box["ifc_size"]

            axis = stringer.get("axis")
            if axis == "y":
                s_lo = float(stringer["y"])
            else:
                s_lo = float(stringer["x"])
            s_hi = s_lo + float(stringer["thickness"])

            # Quick Z overlap check against stringer profile
            z_vals = [float(p[1]) for p in stringer["profile"]]
            prof_z_lo, prof_z_hi = min(z_vals), max(z_vals)
            box_z_lo, box_z_hi = cz - h / 2.0, cz + h / 2.0
            if box_z_hi <= prof_z_lo + 0.5 or box_z_lo >= prof_z_hi - 0.5:
                continue

            if axis == "y":
                # Stringer extrudes along Y
                b_lo, b_hi = cy - d / 2.0, cy + d / 2.0
                if b_hi <= s_lo + 0.5 or b_lo >= s_hi - 0.5:
                    continue
                # Check profile first-coord (X) overlap
                x_vals = [float(p[0]) for p in stringer["profile"]]
                prof_fc_lo, prof_fc_hi = min(x_vals), max(x_vals)
                box_fc_lo, box_fc_hi = cx - w / 2.0, cx + w / 2.0
                if box_fc_hi <= prof_fc_lo + 0.5 or box_fc_lo >= prof_fc_hi - 0.5:
                    continue
                # Trim the box in Y (the stringer's extrusion axis)
                s_center = (s_lo + s_hi) / 2.0
                if s_center < cy:
                    # Stringer on the low-Y side of box — trim low end
                    new_lo = s_hi
                    new_d = b_hi - new_lo
                    if new_d > 1.0:
                        new_cy = new_lo + new_d / 2.0
                        box["ifc_center"][1] = new_cy
                        box["ifc_size"][1] = new_d
                        box["position"][2] = -new_cy
                        box["size"][2] = new_d
                else:
                    # Stringer on the high-Y side of box — trim high end
                    new_hi = s_lo
                    new_d = new_hi - b_lo
                    if new_d > 1.0:
                        new_cy = b_lo + new_d / 2.0
                        box["ifc_center"][1] = new_cy
                        box["ifc_size"][1] = new_d
                        box["position"][2] = -new_cy
                        box["size"][2] = new_d
            else:
                # Stringer extrudes along X
                b_lo, b_hi = cx - w / 2.0, cx + w / 2.0
                if b_hi <= s_lo + 0.5 or b_lo >= s_hi - 0.5:
                    continue
                # Check profile first-coord (Y) overlap
                y_vals = [float(p[0]) for p in stringer["profile"]]
                prof_fc_lo, prof_fc_hi = min(y_vals), max(y_vals)
                box_fc_lo, box_fc_hi = cy - d / 2.0, cy + d / 2.0
                if box_fc_hi <= prof_fc_lo + 0.5 or box_fc_lo >= prof_fc_hi - 0.5:
                    continue
                # Trim the box in X (the stringer's extrusion axis)
                s_center = (s_lo + s_hi) / 2.0
                if s_center < cx:
                    # Stringer on the low-X side of box — trim low end
                    new_lo = s_hi
                    new_w = b_hi - new_lo
                    if new_w > 1.0:
                        new_cx = new_lo + new_w / 2.0
                        box["ifc_center"][0] = new_cx
                        box["ifc_size"][0] = new_w
                        box["position"][0] = new_cx
                        box["size"][0] = new_w
                else:
                    # Stringer on the high-X side of box — trim high end
                    new_hi = s_lo
                    new_w = new_hi - b_lo
                    if new_w > 1.0:
                        new_cx = b_lo + new_w / 2.0
                        box["ifc_center"][0] = new_cx
                        box["ifc_size"][0] = new_w
                        box["position"][0] = new_cx
                        box["size"][0] = new_w


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


# ── winder face-clipping ───────────────────────────────────

def _clip_winders_at_newel_faces(winder_treads, newels):
    """Clip winder treads that extend past a corner-newel face.

    When a winder tread extends significantly past a newel face (more
    than the newel size), it is clipped at that face line.  The clipped
    area is transferred to the adjacent winder tread (the next one up
    in Z) so that no gap is left on the stair surface.

    Only the first and last winder treads overlapping each newel are
    considered — middle winders do not extend past the newel.
    """
    if len(winder_treads) < 2 or not newels:
        return

    # Sort winder treads by Z to know adjacency
    sorted_wt = sorted(winder_treads, key=lambda w: float(w.get("z", 0)))

    for newel in newels:
        cx, cy, cz = newel["ifc_center"]
        nw, nd, nh = newel["ifc_size"]
        nz_lo, nz_hi = cz - nh / 2.0, cz + nh / 2.0
        newel_rect = shapely_box(cx - nw / 2.0, cy - nd / 2.0,
                                 cx + nw / 2.0, cy + nd / 2.0)

        # Find winder treads that overlap this newel (Z-gated, XY-intersecting)
        overlapping_idx = []
        for idx, wt in enumerate(sorted_wt):
            z_lo = float(wt["z"])
            z_hi = z_lo + float(wt["thickness"])
            if nz_hi <= z_lo + 0.5 or nz_lo >= z_hi - 0.5:
                continue
            wpts = [(float(p[0]), float(p[1])) for p in wt["profile"]]
            if len(wpts) < 3:
                continue
            w_poly = Polygon(wpts)
            if w_poly.is_valid and w_poly.intersects(newel_rect):
                overlapping_idx.append(idx)

        if len(overlapping_idx) < 2:
            continue

        # Process the FIRST winder (lowest Z) — the one adjacent to the
        # incoming flight.  It may extend past the newel face in the
        # flight direction.
        first_idx = overlapping_idx[0]
        second_idx = overlapping_idx[1]
        _clip_one_winder_at_face(sorted_wt, first_idx, second_idx, newel)

        # Process the LAST winder (highest Z) — may extend past the
        # newel face in the outgoing flight direction.
        if len(overlapping_idx) >= 3:
            last_idx = overlapping_idx[-1]
            second_last_idx = overlapping_idx[-2]
            _clip_one_winder_at_face(sorted_wt, last_idx, second_last_idx, newel)


def _clip_one_winder_at_face(sorted_wt, clip_idx, transfer_idx, newel):
    """Clip one winder at the newel face it extends past, transferring
    the clipped area to the adjacent winder.
    """
    cx, cy = newel["ifc_center"][0], newel["ifc_center"][1]
    nw, nd = newel["ifc_size"][0], newel["ifc_size"][1]

    winder = sorted_wt[clip_idx]
    wpts = [(float(p[0]), float(p[1])) for p in winder["profile"]]
    if len(wpts) < 3:
        return
    w_poly = Polygon(wpts)
    if w_poly.is_empty or not w_poly.is_valid:
        w_poly = w_poly.buffer(0)
        if w_poly.is_empty:
            return

    xmin, ymin, xmax, ymax = w_poly.bounds

    # Check each newel face for significant extension (> newel size)
    faces = []
    face_y_hi = cy + nd / 2.0
    face_y_lo = cy - nd / 2.0
    face_x_hi = cx + nw / 2.0
    face_x_lo = cx - nw / 2.0

    if ymax - face_y_hi > nd:
        faces.append(("y+", ymax - face_y_hi,
                       shapely_box(-1e9, face_y_hi, 1e9, 1e9)))
    if face_y_lo - ymin > nd:
        faces.append(("y-", face_y_lo - ymin,
                       shapely_box(-1e9, -1e9, 1e9, face_y_lo)))
    if xmax - face_x_hi > nw:
        faces.append(("x+", xmax - face_x_hi,
                       shapely_box(face_x_hi, -1e9, 1e9, 1e9)))
    if face_x_lo - xmin > nw:
        faces.append(("x-", face_x_lo - xmin,
                       shapely_box(-1e9, -1e9, face_x_lo, 1e9)))

    if not faces:
        return

    # Pick the face with the SMALLEST extension.  The winder naturally
    # spans the full stair width (large extension in that axis) but only
    # partially extends past the newel in the flight direction (smaller
    # extension).  Choosing the smallest correctly targets the flight-
    # direction face rather than the stair-width face.
    faces.sort(key=lambda f: f[1])
    _face_name, _extent, clip_away = faces[0]

    # Clip the winder
    clipped_area = w_poly.intersection(clip_away)
    remaining = w_poly.difference(clip_away)

    if remaining.is_empty:
        return
    if isinstance(remaining, MultiPolygon):
        remaining = max(remaining.geoms, key=lambda g: g.area)
    if remaining.geom_type != "Polygon" or remaining.is_empty:
        return

    _write_profile(winder, remaining, fmt="nested")

    # Transfer the clipped area to the adjacent winder
    if clipped_area.is_empty:
        return

    adj = sorted_wt[transfer_idx]
    adj_pts = [(float(p[0]), float(p[1])) for p in adj["profile"]]
    if len(adj_pts) < 3:
        return
    adj_poly = Polygon(adj_pts)
    if adj_poly.is_empty or not adj_poly.is_valid:
        adj_poly = adj_poly.buffer(0)
        if adj_poly.is_empty:
            return

    expanded = adj_poly.union(clipped_area)
    if isinstance(expanded, MultiPolygon):
        expanded = max(expanded.geoms, key=lambda g: g.area)
    if expanded.geom_type == "Polygon" and not expanded.is_empty:
        _write_profile(adj, expanded, fmt="nested")


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
