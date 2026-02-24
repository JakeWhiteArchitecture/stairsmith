"""
Stair Preview Engine — winder geometry helpers.

compute_winder_geometry, _winder_profiles_from_construction,
and _winder_riser_meshes.
"""

import math


def compute_winder_geometry(newel_size, stair_width):
    """Compute winder construction geometry following the 4-step sequence.

    Step 1: Abstract layout — two flights at 90°, inner strings cross at junction.
    Step 2: Newel post centred on junction point (fixed, never moves).
    Step 3: Calculate offset and shift flights away from corner.
    Step 4: Determine winder division lines from post face marks.

    Returns a dict with:
        offset: how far each flight shifts along its axis
        effective_width: stair_width minus offset (warn if < 600mm)
        winder_centre_offset: offset from post centreline to winder centre point
        face_marks: [25mm, 75mm] from corner on each post face
        kite_going: 50mm (25+25 wrapped around corner)
        flank_going: 50mm (75-25 on each face)
        min_post_warning: True if newel_size < 75mm
    """
    half_post = newel_size / 2.0
    corner_allowance = 25.0  # mm from corner of post face
    min_going = 50.0  # mm minimum winder going

    # Step 3: offset = N/2 - 25mm
    offset = half_post - corner_allowance

    # Effective width at the turn after shifting
    effective_width = stair_width - offset

    # Winder centre point offset from post centreline
    winder_centre_offset = offset  # same as flight offset from centreline

    # Face marks from corner: 25mm (kite edge) and 75mm (flank edge)
    mark_kite = corner_allowance  # 25mm from corner
    mark_flank = corner_allowance + min_going  # 75mm from corner

    # Verify goings
    kite_going = corner_allowance + corner_allowance  # 25mm wraps around corner = 50mm
    flank_going = mark_flank - mark_kite  # 75 - 25 = 50mm

    return {
        "offset": offset,
        "effective_width": effective_width,
        "winder_centre_offset": winder_centre_offset,
        "mark_kite": mark_kite,
        "mark_flank": mark_flank,
        "kite_going": kite_going,
        "flank_going": flank_going,
        "min_post_warning": newel_size < 75.0,
        "width_warning": effective_width < 600.0,
    }


def _winder_profiles_from_construction(post_cx, post_cy, newel_size, stair_width,
                                         turn_direction, winder_index, num_winders=3,
                                         rotation=0, riser_extension=0,
                                         flight_extension=0, winder_x=25.0):
    """Generate winder tread profile using angular division lines.

    Division lines radiate from the winder centre point at equal angles
    (90° / num_winders). The winder centre is the intersection of the 25mm
    marks on the two post faces at the turn corner.

    The kite winder preserves the 25×25mm contact with the newel post corner.

    rotation: degrees to rotate the entire profile around (post_cx, post_cy).
              0 = flight approaches along +Y (turn 1 standard).
              -90 = flight approaches along -X (turn 2 after left turn 1).

    riser_extension: mm to extend the upper boundary of non-last winders
                     past the division line, so the riser above can sit on the tread.

    Angles measured from 0° (flight-1 outer string direction, along X)
    to 90° (flight-2 outer string direction, along Y).

    Args:
        post_cx, post_cy: post centreline position (fixed, Step 2)
        newel_size: post dimension (square)
        stair_width: nominal stair width
        turn_direction: 'left' or 'right'
        winder_index: 0-based index of this winder
        num_winders: total winders in this turn (2-4)
    Returns:
        list of (x, y) tuples defining the tread profile polygon
    """
    hp = newel_size / 2.0
    x_sign = 1.0 if turn_direction == "left" else -1.0

    # Post corner nearest turn interior (Face A and Face B meet here)
    pc_x = post_cx + x_sign * hp
    pc_y = post_cy + hp

    # Winder centre: intersection of winder_x marks on both post faces
    wc_x = pc_x - x_sign * winder_x
    wc_y = pc_y - winder_x

    # Outer string positions
    outer_f1_x = post_cx + x_sign * stair_width
    outer_f2_y = post_cy + stair_width

    # Post face edges
    post_bottom_y = post_cy - hp
    post_opp_x = post_cx - x_sign * hp

    # Angular division: 90° split into num_winders equal segments.
    # Inner contact points are FIXED at 25mm marks on the post faces.
    # Only the OUTER points follow angular rays from the winder centre.
    angle_step = (math.pi / 2.0) / num_winders

    def ray_outer(angle):
        """Where a ray from winder centre at angle hits the outer L-boundary."""
        dx = x_sign * math.cos(angle)
        dy = math.sin(angle)
        t_f1 = (outer_f1_x - wc_x) / dx if abs(dx) > 1e-9 else float('inf')
        t_f2 = (outer_f2_y - wc_y) / dy if abs(dy) > 1e-9 else float('inf')
        if t_f1 < 0: t_f1 = float('inf')
        if t_f2 < 0: t_f2 = float('inf')
        t = min(t_f1, t_f2)
        return (wc_x + dx * t, wc_y + dy * t)

    a0 = winder_index * angle_step
    a1 = (winder_index + 1) * angle_step

    outer_s = ray_outer(a0)
    outer_e = ray_outer(a1)

    # Angle to outer L-corner
    oc_dx = (outer_f1_x - wc_x) / x_sign
    oc_dy = outer_f2_y - wc_y
    a_outer_corner = math.atan2(oc_dy, oc_dx)
    straddles_outer = a0 < a_outer_corner < a1

    # Fixed 25mm inner marks on post faces
    mark_a = (pc_x, wc_y)   # 25mm mark on Face A (vertical face)
    mark_b = (wc_x, pc_y)   # 25mm mark on Face B (horizontal face)

    # Pre-compute riser extension points for non-last winders.
    # These extend the upper boundary (at a1) by riser_extension past
    # the division line so the riser above can sit on the tread.
    ext_inner = ext_outer = None
    if riser_extension > 0 and winder_index < num_winders - 1:
        a_ic = math.atan2(winder_x, winder_x)
        if a1 < a_ic - 1e-6:
            inner_a1 = mark_a
        elif a1 > a_ic + 1e-6:
            inner_a1 = mark_b
        else:
            inner_a1 = (pc_x, pc_y)
        dlx = outer_e[0] - inner_a1[0]
        dly = outer_e[1] - inner_a1[1]
        dl = math.sqrt(dlx * dlx + dly * dly)
        if dl > 1e-9:
            pnx = x_sign * (-dly / dl) * riser_extension
            pny = x_sign * (dlx / dl) * riser_extension
            ext_inner = (inner_a1[0] + pnx, inner_a1[1] + pny)
            # Clamp ext_inner to post face, preserving perpendicular
            # distance from the division line by sliding along it.
            ex, ey = ext_inner
            if abs(inner_a1[0] - pc_x) < 1e-6:
                # inner_a1 is on Face A — slide along division line to x = pc_x
                if abs(ex - pc_x) > 1e-6 and abs(dlx) > 1e-9:
                    t = (pc_x - ex) / dlx
                    ex = pc_x
                    ey = ey + t * dly
                else:
                    ex = pc_x
                ey = min(ey, pc_y)
            elif abs(inner_a1[1] - pc_y) < 1e-6:
                # inner_a1 is on Face B — slide along division line to y = pc_y
                if abs(ey - pc_y) > 1e-6 and abs(dly) > 1e-9:
                    t = (pc_y - ey) / dly
                    ex = ex + t * dlx
                    ey = pc_y
                else:
                    ey = pc_y
                if x_sign > 0:
                    ex = max(ex, post_opp_x)
                else:
                    ex = min(ex, post_opp_x)
            else:
                # At post corner — no inner extension needed
                ex = pc_x
                ey = pc_y
            ext_inner = (ex, ey)
            # Trace from ext_inner along division line to hit the outer
            # L-boundary so the tread extension is flush with the wall
            t_f1 = (outer_f1_x - ext_inner[0]) / dlx if abs(dlx) > 1e-9 else float('inf')
            t_f2 = (outer_f2_y - ext_inner[1]) / dly if abs(dly) > 1e-9 else float('inf')
            if t_f1 < 0: t_f1 = float('inf')
            if t_f2 < 0: t_f2 = float('inf')
            t = min(t_f1, t_f2)
            ext_outer = (ext_inner[0] + dlx * t, ext_inner[1] + dly * t)

    # First winder (flight-1 side flank)
    if winder_index == 0:
        # Extend leading edge toward flight 1 by flight_extension
        entry_y = post_bottom_y - flight_extension

        if flight_extension > 0:
            # Winder extends below post — full flight width with L-shaped
            # inner edge that wraps around the post bottom face
            profile = [
                (post_cx, entry_y),          # inner bottom at flight width
                (outer_f1_x, entry_y),       # outer bottom
            ]
        else:
            # Winder doesn't extend below post — inner edge at post face
            profile = [
                (pc_x, entry_y),             # inner bottom at post face
                (outer_f1_x, entry_y),       # outer bottom
            ]

        # outer_s is at a0=0 which is along flight-1 axis
        if straddles_outer:
            profile.append((outer_f1_x, outer_f2_y))
        profile.append(outer_e)          # angled outer point
        if ext_outer:
            profile.append(ext_outer)
            profile.append(ext_inner)
        profile.append(mark_a)           # fixed 25mm mark on Face A

        if flight_extension > 0:
            # Close the L-shape: down post face to post bottom, jog to flight edge
            profile.append((pc_x, post_bottom_y))
            profile.append((post_cx, post_bottom_y))

    # Last winder (flight-2 side flank)
    elif winder_index == num_winders - 1:
        # Extend rear edge toward flight 2 so it runs under flight 2's
        # first riser. Total extension = flight_extension + riser_extension.
        total_exit_ext = flight_extension + riser_extension
        exit_x = post_opp_x - x_sign * total_exit_ext

        if total_exit_ext > 0:
            # Exit extends past post — full flight width with L-shaped
            # inner edge that wraps around the post opposite face
            profile = [
                mark_b,                          # fixed 25mm mark on Face B
                (post_opp_x, pc_y),              # along post face to post edge
                (post_opp_x, post_cy),           # jog to flight inner edge
                (exit_x, post_cy),               # continue at flight width
                (exit_x, outer_f2_y),            # exit outer
            ]
        else:
            # Exit doesn't extend past post — inner edge at post face
            profile = [
                mark_b,                          # fixed 25mm mark on Face B
                (exit_x, pc_y),                  # exit edge inner
                (exit_x, outer_f2_y),            # exit edge outer
            ]

        # outer_e is at a1=90° which is along flight-2 axis
        if straddles_outer:
            profile.append((outer_f1_x, outer_f2_y))
        profile.append(outer_s)              # angled outer point

    # Middle winders (kite or half-kite)
    else:
        # Determine which part of the inner L-shape this winder gets.
        ic_dx = (pc_x - wc_x) / x_sign if x_sign != 0 else 1.0
        ic_dy = pc_y - wc_y
        a_inner_corner = math.atan2(ic_dy, ic_dx)
        a_mid = (a0 + a1) / 2.0

        if a_mid < a_inner_corner - 1e-6:
            # Face A side only (before post corner)
            profile = [mark_a, (pc_x, pc_y)]
        elif a_mid > a_inner_corner + 1e-6:
            # Face B side only (after post corner)
            profile = [(pc_x, pc_y), mark_b]
        else:
            # Straddles corner — full L-shape (kite)
            profile = [mark_a, (pc_x, pc_y), mark_b]

        # Insert extension before outer_e so tread extends past division line
        if ext_inner:
            profile.append(ext_inner)
            profile.append(ext_outer)
        profile.append(outer_e)
        if straddles_outer:
            profile.append((outer_f1_x, outer_f2_y))
        profile.append(outer_s)

    # Apply rotation around post centre if needed (for turn 2)
    if rotation != 0:
        rad = math.radians(rotation)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        rotated = []
        for (px, py) in profile:
            dx = px - post_cx
            dy = py - post_cy
            rx = cos_r * dx - sin_r * dy + post_cx
            ry = sin_r * dx + cos_r * dy + post_cy
            rotated.append((rx, ry))
        profile = rotated

    return profile


def _winder_riser_meshes(corner_x, corner_y, ns, width, turn_dir,
                         num_winders, winder_start_riser, rise, tread_t,
                         riser_t, nosing=0, rotation=0, winder_x=25.0):
    """Generate riser meshes between consecutive winder treads.

    Returns a list of winder_polygon mesh dicts (thin strips along division
    lines, extruded vertically by riser_h).
    """
    if num_winders < 2 or riser_t <= 0:
        return []

    riser_h = rise - tread_t
    hp = ns / 2.0
    x_sign = 1.0 if turn_dir == "left" else -1.0

    pc_x = corner_x + x_sign * hp
    pc_y = corner_y + hp
    wc_x = pc_x - x_sign * winder_x
    wc_y = pc_y - winder_x

    outer_f1_x = corner_x + x_sign * width
    outer_f2_y = corner_y + width

    mark_a = (pc_x, wc_y)
    mark_b = (wc_x, pc_y)

    angle_step = (math.pi / 2.0) / num_winders
    a_inner_corner = math.atan2(winder_x, winder_x)  # pi/4

    def ray_outer(angle):
        dx = x_sign * math.cos(angle)
        dy = math.sin(angle)
        t_f1 = (outer_f1_x - wc_x) / dx if abs(dx) > 1e-9 else float('inf')
        t_f2 = (outer_f2_y - wc_y) / dy if abs(dy) > 1e-9 else float('inf')
        if t_f1 < 0: t_f1 = float('inf')
        if t_f2 < 0: t_f2 = float('inf')
        t = min(t_f1, t_f2)
        return (wc_x + dx * t, wc_y + dy * t)

    meshes = []
    for j in range(num_winders - 1):
        a_boundary = (j + 1) * angle_step

        # Inner point on post face
        if a_boundary < a_inner_corner - 1e-6:
            inner = mark_a
        elif a_boundary > a_inner_corner + 1e-6:
            inner = mark_b
        else:
            inner = (pc_x, pc_y)

        outer = ray_outer(a_boundary)

        # Division line direction and perpendicular
        lx = outer[0] - inner[0]
        ly = outer[1] - inner[1]
        length = math.sqrt(lx * lx + ly * ly)
        if length < 1e-9:
            continue

        # Unit normal toward upper winder
        unx = x_sign * (-ly / length)
        uny = x_sign * (lx / length)

        # Nosing setback: shift entire riser toward upper winder by nosing,
        # so the nosing of the tread above overhangs past the riser front face.
        # Then the back face is riser_t further toward the upper winder.
        front_off = nosing              # toward upper winder
        back_off = nosing + riser_t     # riser_t past front face

        inner_front = (inner[0] + unx * front_off, inner[1] + uny * front_off)

        # Clamp the front inner point to the post face by sliding along the
        # division line, so the riser doesn't penetrate the newel post.
        post_opp_x = corner_x - x_sign * hp
        def _clamp_to_post(pt):
            ex, ey = pt
            if abs(inner[0] - pc_x) < 1e-6:
                # inner is on Face A — slide along division line to x = pc_x
                if abs(ex - pc_x) > 1e-6 and abs(lx) > 1e-9:
                    base_x = inner[0] + front_off * unx
                    base_y = inner[1] + front_off * uny
                    t = (pc_x - base_x) / lx
                    ex = pc_x
                    ey = base_y + t * ly
                else:
                    ex = pc_x
                ey = min(ey, pc_y)
            elif abs(inner[1] - pc_y) < 1e-6:
                # inner is on Face B — slide along division line to y = pc_y
                if abs(ey - pc_y) > 1e-6 and abs(ly) > 1e-9:
                    base_x = inner[0] + front_off * unx
                    base_y = inner[1] + front_off * uny
                    t = (pc_y - base_y) / ly
                    ex = base_x + t * lx
                    ey = pc_y
                else:
                    ey = pc_y
                if x_sign > 0:
                    ex = max(ex, post_opp_x)
                else:
                    ex = min(ex, post_opp_x)
            else:
                # At post corner
                ex = pc_x
                ey = pc_y
            return (ex, ey)
        inner_front = _clamp_to_post(inner_front)
        # Derive inner_back from the clamped front point so the riser always
        # has full riser_t perpendicular thickness.  Independent clamping of
        # inner_back using back_off collapsed both points to the post corner
        # for the first winder boundary (< 45°), producing a zero-thickness
        # degenerate triangle instead of a proper riser quadrilateral.
        inner_back = (inner_front[0] + unx * riser_t, inner_front[1] + uny * riser_t)

        # Trace both outer points along division line to hit the wall
        def _trace_to_wall(pt):
            tf1 = (outer_f1_x - pt[0]) / lx if abs(lx) > 1e-9 else float('inf')
            tf2 = (outer_f2_y - pt[1]) / ly if abs(ly) > 1e-9 else float('inf')
            if tf1 < 0: tf1 = float('inf')
            if tf2 < 0: tf2 = float('inf')
            t = min(tf1, tf2)
            return (pt[0] + lx * t, pt[1] + ly * t)

        outer_front = _trace_to_wall(inner_front)
        outer_back = _trace_to_wall(inner_back)

        # Riser polygon: front face set back by nosing from division line,
        # back face riser_t further, both outer ends flush with wall
        strip = [
            inner_back,     # back face, inner end
            outer_back,     # back face, outer end (on the wall)
            outer_front,    # front face, outer end (on the wall)
            inner_front,    # front face, inner end
        ]

        # Apply rotation if needed (turn 2)
        if rotation != 0:
            rad = math.radians(rotation)
            cos_r = math.cos(rad)
            sin_r = math.sin(rad)
            rotated = []
            for (px, py) in strip:
                dx = px - corner_x
                dy = py - corner_y
                rx = cos_r * dx - sin_r * dy + corner_x
                ry = sin_r * dx + cos_r * dy + corner_y
                rotated.append((rx, ry))
            strip = rotated

        z_bottom = (winder_start_riser + j) * rise
        meshes.append({
            "type": "winder_polygon",
            "profile": [[pt[0], pt[1]] for pt in strip],
            "z": z_bottom,
            "thickness": riser_h,
            "color": "#e8dcc8",
            "name": f"Winder Riser {j+1}",
            "ifc_type": "winder_riser",
        })

    return meshes
