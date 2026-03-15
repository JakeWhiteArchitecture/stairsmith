"""
Stair Preview Engine — flight builder functions.

_preview_straight, _preview_single_winder, _preview_double_winder.
"""

import math

from stair_constants import (
    STRINGER_THICKNESS, STRINGER_HEIGHT, STRINGER_PITCH_OFFSET, STRINGER_DROP,
    WALL_STRINGER_EXTENSION, _box_mesh,
)
from stair_balustrade import (
    _stringer_flight_y, _stringer_flight_x,
    _stringer_landing_y, _stringer_landing_x,
    _stringer_flight_y_notched, _stringer_flight_x_notched,
    _handrail_flight_y, _handrail_flight_x,
    _handrail_landing_y, _handrail_landing_x,
    _baserail_flight_y, _baserail_flight_x,
    _baserail_landing_y, _baserail_landing_x,
    _spindles_flight_y, _spindles_flight_x,
    _spindles_landing_y, _spindles_landing_x,
)
from stair_winder_geometry import (
    compute_winder_geometry,
    _winder_profiles_from_construction,
    _winder_riser_meshes,
)


def _preview_straight(p):
    import math
    meshes = []
    width = p["stair_width"] - STRINGER_THICKNESS
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    num_risers = p["num_risers_val"]

    for i in range(num_treads):
        tread_y = i * going - nosing
        tread_z = (i + 1) * rise - tread_t
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c",
            name=f"Flight 1 Tread {i+1}", ifc_type="tread",
        ))

    riser_h = rise - tread_t
    for i in range(num_risers):
        riser_y = i * going
        riser_z = i * rise
        if riser_t > 0:
            meshes.append(_box_mesh(
                width / 2, riser_y + riser_t / 2, riser_z + riser_h / 2,
                width, riser_t, riser_h, "#e8dcc8",
                name=f"Riser F1-{i+1}", ifc_type="riser",
            ))

    # --- Landing threshold strip ---
    ftf = num_risers * rise
    threshold_d = p["threshold_depth"]
    threshold_y = num_treads * going - nosing            # front (nosing overhang)
    threshold_back = num_treads * going - nosing + threshold_d
    meshes.append(_box_mesh(
        width / 2, threshold_y + threshold_d / 2, ftf - tread_t + tread_t / 2,
        width, threshold_d, tread_t, "#c8a87c",
        name="Threshold", ifc_type="threshold",
    ))

    # --- Stringers and balustrade ---
    nzs = rise * nosing / going
    ns = p["newel_size"]
    hp = ns / 2.0
    y0 = 0.0
    y1 = num_treads * going + riser_t / 2       # flush with riser back face
    y1_nf = num_treads * going                  # non-flushed (at last riser)
    z0 = rise + nzs
    z1 = (num_treads + 1) * rise + nzs + riser_t * rise / (2 * going)
    z1_nf = (num_treads + 1) * rise + nzs

    hr_kw = {"hr_width": p["handrail_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"]}
    br_kw = {"br_width": p["baserail_width"], "br_height": p["baserail_height"]}
    sp_kw = {"spindle_size": p["spindle_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"], "br_height": p["baserail_height"]}

    NEWEL_CAP = 150.0
    hr_rise_val = p["handrail_rise"]
    bottom_post_y = -nosing
    top_post_y = threshold_y

    for side_idx, (x_pos, condition) in enumerate([(0.0, p["left_condition"]), (width, p["right_condition"])]):
        side = "Left" if side_idx == 0 else "Right"
        if condition == "balustrade":
            bot_face_y = bottom_post_y + hp
            top_face_y = top_post_y - hp
            dy = y1 - y0
            # For balustrade, stringer terminates at rear face of bottom post (no extension)
            _slope = (z1 - z0) / (y1 - y0) if abs(y1 - y0) > 1e-9 else 0
            y0_stringer = bot_face_y
            if abs(y1 - y0) > 1e-9:
                t_stringer = (bot_face_y - y0) / (y1 - y0)
                z0_stringer = z0 + t_stringer * (z1 - z0)
            else:
                z0_stringer = z0
            # Clip handrail/baserail/spindle start at bottom post face
            y0_c, z0_c = y0, z0
            if abs(dy) > 1e-9 and bot_face_y > y0:
                t_c = min(1.0, (bot_face_y - y0) / dy)
                y0_c = y0 + t_c * dy
                z0_c = z0 + t_c * (z1 - z0)
            # Clip end at top post face
            y1_c, z1_c = y1, z1
            if abs(dy) > 1e-9 and top_face_y < y1:
                t_c = max(0.0, (top_face_y - y0) / dy)
                y1_c = y0 + t_c * dy
                z1_c = z0 + t_c * (z1 - z0)
            meshes.append(_stringer_flight_y(x_pos, y0_stringer, z0_stringer, y1_c, z1_c,
                                             name=f"{side} Stringer F1", clip_z_min=0))
            # Handrail clip (using non-flushed endpoint)
            dy_nf = y1_nf - y0
            y1_hr, z1_hr = y1_nf, z1_nf
            if abs(dy_nf) > 1e-9 and top_face_y < y1_nf:
                t_c = max(0.0, (top_face_y - y0) / dy_nf)
                y1_hr = y0 + t_c * dy_nf
                z1_hr = z0 + t_c * (z1_nf - z0)
            meshes.append(_handrail_flight_y(x_pos, y0_c, z0_c, y1_hr, z1_hr,
                                             name=f"{side} Handrail F1", **hr_kw))
            meshes.append(_baserail_flight_y(x_pos, y0_c, z0_c, y1_c, z1_c,
                                             name=f"{side} Baserail F1", **br_kw))
            if abs(dy_nf) > 1e-9:
                t_sp0 = (bot_face_y - y0) / dy_nf
                t_sp1 = (top_face_y - y0) / dy_nf
                sp_z0 = z0 + t_sp0 * (z1_nf - z0)
                sp_z1 = z0 + t_sp1 * (z1_nf - z0)
                meshes.extend(_spindles_flight_y(x_pos, bot_face_y, sp_z0, top_face_y, sp_z1,
                                                 name_prefix=f"{side} Spindle F1", **sp_kw))
            # Newel posts
            hr_bot = rise + nzs + hr_rise_val
            bot_h = hr_bot + NEWEL_CAP
            meshes.append(_box_mesh(x_pos, bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355",
                                    name=f"{side} Bottom Post", ifc_type="newel"))
            # Top newel extends FROM cutting plane (150mm below stringer bottom) UPWARD
            # Stringer bottom = pitch_line - 250mm
            # Newel bottom = pitch_line - 400mm (150mm below stringer bottom)
            # Newel top = pitch_line + handrail_rise + NEWEL_CAP
            pitch_line = ftf + nzs
            newel_bottom = pitch_line - 400.0
            newel_top = pitch_line + hr_rise_val + NEWEL_CAP
            top_h = newel_top - newel_bottom
            top_z_center = (newel_bottom + newel_top) / 2
            meshes.append(_box_mesh(x_pos, top_post_y, top_z_center, ns, ns, top_h, "#8B7355",
                                    name=f"{side} Top Post", ifc_type="newel"))
        else:
            # Wall condition: notched stringer with base extension (no newel to terminate to)
            _slope = (z1 - z0) / (y1 - y0) if abs(y1 - y0) > 1e-9 else 0
            y0_w = y0 - WALL_STRINGER_EXTENSION
            z0_w = z0 - WALL_STRINGER_EXTENSION * _slope
            meshes.append(_stringer_flight_y_notched(x_pos, y0_w, z0_w, y1, z1, ftf, threshold_back, tread_t,
                                                     name=f"{side} Stringer F1", clip_z_min=0))

    return meshes




def _preview_single_winder(p):
    import math
    meshes = []
    width = p["stair_width"] - STRINGER_THICKNESS
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    winders = p["turn1_winders"]
    turn_dir = p["turn1_direction"]
    turn1_enabled = p.get("turn1_enabled", True)

    # Balustrade keyword dicts
    hr_kw = {"hr_width": p["handrail_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"]}
    br_kw = {"br_width": p["baserail_width"], "br_height": p["baserail_height"]}
    sp_kw = {"spindle_size": p["spindle_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"], "br_height": p["baserail_height"]}

    # Map left/right conditions to inner/outer based on turn direction
    # Left turn: left (x=0) = inner, right (x=width) = outer
    # Right turn: left (x=0) = outer, right (x=width) = inner
    if p["turn1_direction"] == "left":
        render_inner = p["left_condition"] == "balustrade"
        render_outer = p["right_condition"] == "balustrade"
    else:
        render_inner = p["right_condition"] == "balustrade"
        render_outer = p["left_condition"] == "balustrade"

    actual_winders = winders if turn1_enabled else 0
    straight_treads = num_treads - actual_winders
    # Use custom flight distribution if provided and valid
    f1_ov, f2_ov = p.get("flight1_steps", -1), p.get("flight2_steps", -1)
    if f1_ov >= 0 and f2_ov >= 0 and f1_ov + f2_ov == straight_treads:
        flight1_treads = f1_ov
        flight2_treads = f2_ov
    else:
        flight1_treads = straight_treads // 2
        flight2_treads = straight_treads - flight1_treads

    # Step 3: Calculate offset and half-post
    ns = p["newel_size"]
    hp = ns / 2.0
    wg = compute_winder_geometry(ns, width)
    offset = wg["offset"]
    wx = p["winder_x"]  # distance from internal corner along post face
    wy = p["winder_y"]  # going from X endpoint toward flight

    # Flight shift: X+Y measured from internal corner (at hp above post centre)
    flight1_shift_y = (hp - wx - wy + nosing) if actual_winders > 0 else 0.0
    bottom_post_y = flight1_shift_y - nosing

    # Flight 1 treads
    for i in range(flight1_treads):
        tread_y = i * going - nosing + flight1_shift_y
        tread_z = (i + 1) * rise - tread_t
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c",
            name=f"Flight 1 Tread {i+1}", ifc_type="tread",
        ))

    # Flight 1 risers
    riser_h = rise - tread_t
    for i in range(flight1_treads + 1):
        if riser_t > 0:
            meshes.append(_box_mesh(
                width / 2, i * going + riser_t / 2 + flight1_shift_y, i * rise + riser_h / 2,
                width, riser_t, riser_h, "#e8dcc8",
                name=f"Riser F1-{i+1}", ifc_type="riser",
            ))

    # Winder treads — construction-based profiles
    winder_start_riser = flight1_treads + 1
    corner_y = flight1_treads * going
    corner_x = 0 if turn_dir == "left" else width

    # Landing position — shifted forward by nosing when flat landing replaces winders
    # This ensures the landing overhangs the last flight 1 riser correctly
    landing_y = corner_y - nosing if actual_winders == 0 else corner_y

    for i in range(actual_winders):
        winder_z = (winder_start_riser + i) * rise - tread_t
        profile = _winder_profiles_from_construction(
            corner_x, corner_y, p["newel_size"], width,
            turn_dir, i, actual_winders,
            riser_extension=riser_t + nosing,
            flight_extension=wx + wy - 2 * hp,
            winder_x=wx)
        meshes.append({
            "type": "winder_polygon",
            "profile": [[pt[0], pt[1]] for pt in profile],
            "z": winder_z,
            "thickness": tread_t,
            "color": "#d4a574",
            "name": f"Winder {i+1}",
            "ifc_type": "winder_tread",
        })

    # Winder risers (between consecutive winder treads)
    meshes.extend(_winder_riser_meshes(
        corner_x, corner_y, ns, width, turn_dir,
        actual_winders, winder_start_riser, rise, tread_t, riser_t,
        nosing=nosing, winder_x=wx))

    # Landing tread when winders are off
    if actual_winders == 0:
        landing_z = winder_start_riser * rise - tread_t
        # Landing extends asymmetrically to reach back face of flight 2's first riser
        # Extends by nosing + riser_t on the wall side only
        hp = ns / 2
        landing_w = width + nosing + riser_t
        if turn_dir == "right":
            landing_cx = (width + nosing + riser_t) / 2
        else:  # left turn
            landing_cx = (width - nosing - riser_t) / 2
        landing_depth = width + nosing
        landing_cy = landing_y + landing_depth / 2
        meshes.append(_box_mesh(
            landing_cx,
            landing_cy,
            landing_z + tread_t / 2,
            landing_w, landing_depth, tread_t, "#c8a87c",
            name="Landing", ifc_type="landing",
        ))

    # Flight 2 Y center position — matches landing center when flat landing is used
    flight2_y_center = landing_y + (width + nosing) / 2 if actual_winders == 0 else landing_y + width / 2

    # Flight 2 treads (perpendicular, offset by X+Y from internal corner)
    flight2_start_riser = winder_start_riser + actual_winders
    # When winders are off, the landing consumes 1 rise — shift flight 2 up
    if actual_winders == 0:
        flight2_start_riser += 1
        flight2_treads = max(0, flight2_treads - 1)
    winder_offset = (wx + wy - hp) if actual_winders > 0 else 0.0
    flight2_shift = winder_offset + nosing + riser_t / 2
    for i in range(flight2_treads):
        tread_z = (flight2_start_riser + i) * rise - tread_t
        if turn_dir == "left":
            tread_x = -(i * going) - going / 2 + nosing / 2 - flight2_shift
        else:
            tread_x = width + i * going + going / 2 - nosing / 2 + flight2_shift
        meshes.append(_box_mesh(
            tread_x, flight2_y_center, tread_z + tread_t / 2,
            going + nosing + riser_t, width, tread_t, "#c8a87c",
            name=f"Flight 2 Tread {i+1}", ifc_type="tread",
        ))

    # Flight 2 risers (perpendicular — thin in X, spanning width in Y)
    if riser_t > 0:
        for i in range(flight2_treads + 1):
            riser_z = (flight2_start_riser + i - 1) * rise + riser_h / 2
            if turn_dir == "left":
                riser_x = -(i * going) - winder_offset - nosing - riser_t / 2
            else:
                riser_x = width + i * going + winder_offset + nosing + riser_t / 2
            meshes.append(_box_mesh(
                riser_x, flight2_y_center, riser_z,
                riser_t, width, riser_h, "#e8dcc8",
                name=f"Riser F2-{i+1}", ifc_type="riser",
            ))

    # --- Landing threshold strip ---
    ftf = (num_treads + 1) * rise
    threshold_d = p["threshold_depth"]
    if turn_dir == "left":
        thresh_front = -(flight2_treads * going) - winder_offset + nosing
        thresh_back = thresh_front - threshold_d
    else:
        thresh_front = width + flight2_treads * going + winder_offset - nosing
        thresh_back = thresh_front + threshold_d
    meshes.append(_box_mesh(
        (thresh_front + thresh_back) / 2, flight2_y_center, ftf - tread_t / 2,
        threshold_d, width, tread_t, "#c8a87c",
        name="Threshold", ifc_type="threshold",
    ))

    # --- Balustrade helpers ---
    c_ns = max(ns, 100.0) if (flight1_treads == 0 or flight2_treads == 0) else ns
    c_hp = c_ns / 2.0
    top_post_x = thresh_front

    # --- Stringers (only for flat landings) ---
    if actual_winders == 0:
        # Flight 1: runs along +Y. Inner side = corner_x (0 for left, width for right),
        # outer side = width - corner_x.
        inner_x = corner_x  # 0 for left, width for right
        outer_x = width - corner_x  # width for left, 0 for right
        f1_y0 = flight1_shift_y  # first riser Y
        f1_y1 = flight1_treads * going + flight1_shift_y  # last riser Y
        nzs = rise * nosing / going  # nosing z-shift: pitch line offset at nosing vs riser
        f1_z0 = rise + nzs
        f1_z1 = (flight1_treads + 1) * rise + nzs

        landing_z_base = winder_start_riser * rise
        land_top = landing_z_base + STRINGER_DROP
        # Extend outer flight 1 along pitch until top edge meets landing stringer top
        z_ext = land_top - STRINGER_PITCH_OFFSET
        dy = f1_y1 - f1_y0
        dz = f1_z1 - f1_z0
        f1_y1_ext = f1_y1 + (z_ext - f1_z1) * dy / dz if abs(dz) > 1e-9 else f1_y1

        # Flight 2 coordinates + outer extension
        inner_y = landing_y
        outer_y = landing_y + width
        if turn_dir == "left":
            f2_x0 = -winder_offset - nosing - riser_t / 2
            f2_x1 = -(flight2_treads * going) - winder_offset - nosing - riser_t / 2
        else:
            f2_x0 = width + winder_offset + nosing + riser_t / 2
            f2_x1 = width + flight2_treads * going + winder_offset + nosing + riser_t / 2
        f2_z0 = flight2_start_riser * rise + nzs
        f2_z1 = (flight2_start_riser + flight2_treads) * rise + nzs
        z_ext2 = land_top - STRINGER_PITCH_OFFSET
        dx2 = f2_x1 - f2_x0
        dz2 = f2_z1 - f2_z0
        f2_x0_ext = f2_x0 + (z_ext2 - f2_z0) * dx2 / dz2 if abs(dz2) > 1e-9 else f2_x0

        # Flight 1 stringers
        bot_face_y = bottom_post_y + hp
        dy1 = f1_y1 - f1_y0
        if flight1_treads > 0:
            # Calculate trimmed top position at pitch-change newel face
            pc_face_y = f1_y1 - hp
            if abs(dy1) > 1e-9:
                t_top = (pc_face_y - f1_y0) / dy1
                f1_y1_trim = pc_face_y
                f1_z1_trim = f1_z0 + t_top * (f1_z1 - f1_z0)
            else:
                f1_y1_trim = f1_y1
                f1_z1_trim = f1_z1

            if render_inner:
                f1_y0_c, f1_z0_c = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_c = f1_y0 + t_c * dy1
                    f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
                # Stringer terminates at rear face of bottom post (no extension for balustrade)
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_stringer = bot_face_y
                if abs(f1_y1 - f1_y0) > 1e-9:
                    t_stringer = (bot_face_y - f1_y0) / (f1_y1 - f1_y0)
                    f1_z0_stringer = f1_z0 + t_stringer * (f1_z1 - f1_z0)
                else:
                    f1_z0_stringer = f1_z0
                meshes.append(_stringer_flight_y(inner_x, f1_y0_stringer, f1_z0_stringer, f1_y1_trim, f1_z1_trim, clip_z_min=0))
                meshes.append(_handrail_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **hr_kw))
                meshes.append(_baserail_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **br_kw))
                meshes.extend(_spindles_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(inner_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))
            if render_outer:
                # Outer flight 1: clipped at outer bottom/pitch-change newel faces
                f1_y0_oc, f1_z0_oc = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_oc = f1_y0 + t_c * dy1
                    f1_z0_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
                # Stringer terminates at rear face of bottom post (no extension for balustrade)
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_stringer_outer = bot_face_y
                if abs(f1_y1 - f1_y0) > 1e-9:
                    t_stringer = (bot_face_y - f1_y0) / (f1_y1 - f1_y0)
                    f1_z0_stringer_outer = f1_z0 + t_stringer * (f1_z1 - f1_z0)
                else:
                    f1_z0_stringer_outer = f1_z0
                meshes.append(_stringer_flight_y(outer_x, f1_y0_stringer_outer, f1_z0_stringer_outer, f1_y1_trim, f1_z1_trim, clip_z_min=0))
                meshes.append(_handrail_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1_trim, f1_z1_trim, **hr_kw))
                meshes.append(_baserail_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1_trim, f1_z1_trim, **br_kw))
                # Spindles: from bottom post face to pitch-change newel face
                meshes.extend(_spindles_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1_trim, f1_z1_trim, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(outer_x, f1_y0_w, f1_z0_w, f1_y1_ext, z_ext, clip_z_min=0))

        # Landing flat stringers — outer endpoints linked to flight stringer extensions
        st2 = STRINGER_THICKNESS / 2
        # Outer corner newel position
        outer_corner_y = landing_y + width
        # Landing stringer endpoints: use newel face when balustrade present, extended position otherwise
        if turn_dir == "left":
            f2_landing_x_end = f2_x0 + hp if render_outer else f2_x0_ext
        else:
            f2_landing_x_start = f2_x0 - hp if render_outer else f2_x0_ext
        # Y-direction landing stringer masters the X stringer: extends through the full X
        # stringer thickness to its rear edge (+st2 past the X stringer centre).
        # Handrail/baserail/spindles still terminate at the newel post face (hp).
        f1_landing_y_start = (f1_y1 + hp) if render_outer else f1_y1_ext
        f1_landing_y_end = outer_corner_y + st2
        # In wall condition, drop landing stringers to align top edge with flight stringers
        landing_z_stringer = landing_z_base if render_outer else (landing_z_base - STRINGER_PITCH_OFFSET)
        if turn_dir == "left":
            meshes.append(_stringer_landing_x(landing_y, f2_x0, inner_x, landing_z_base))
            # Outer landing stringers - Y runs newel-to-newel, X stops flush with Y stringer face
            meshes.append(_stringer_landing_y(outer_x, f1_landing_y_start, f1_landing_y_end, landing_z_stringer))
            meshes.append(_stringer_landing_x(outer_corner_y, f2_landing_x_end, outer_x - st2, landing_z_stringer))
            if render_outer:
                # Add handrails and baserails for landing when balustrade is present
                # Run from newel post face to newel post face to eliminate gaps
                meshes.append(_handrail_landing_y(outer_x, f1_y1 + hp, landing_y + width - hp, landing_z_base, **hr_kw))
                meshes.append(_handrail_landing_x(landing_y + width, f2_x0 + hp, outer_x - hp, landing_z_base, **hr_kw))
                meshes.append(_baserail_landing_y(outer_x, f1_y1 + hp, landing_y + width - hp, landing_z_base, **br_kw))
                meshes.append(_baserail_landing_x(landing_y + width, f2_x0 + hp, outer_x - hp, landing_z_base, **br_kw))
                # Add spindles for landing
                meshes.extend(_spindles_landing_y(outer_x, f1_y1 + hp, landing_y + width - hp, landing_z_base, **sp_kw))
                meshes.extend(_spindles_landing_x(landing_y + width, f2_x0 + hp, outer_x - hp, landing_z_base, **sp_kw))
        else:
            meshes.append(_stringer_landing_x(landing_y, inner_x, f2_x0, landing_z_base))
            # Outer landing stringers - Y runs newel-to-newel, X stops flush with Y stringer face
            meshes.append(_stringer_landing_y(outer_x, f1_landing_y_start, f1_landing_y_end, landing_z_stringer))
            meshes.append(_stringer_landing_x(outer_corner_y, outer_x + st2, f2_landing_x_start, landing_z_stringer))
            if render_outer:
                # Add handrails and baserails for landing when balustrade is present
                # Run from newel post face to newel post face to eliminate gaps
                meshes.append(_handrail_landing_y(outer_x, f1_y1 + hp, landing_y + width - hp, landing_z_base, **hr_kw))
                meshes.append(_handrail_landing_x(landing_y + width, outer_x + hp, f2_x0 - hp, landing_z_base, **hr_kw))
                meshes.append(_baserail_landing_y(outer_x, f1_y1 + hp, landing_y + width - hp, landing_z_base, **br_kw))
                meshes.append(_baserail_landing_x(landing_y + width, outer_x + hp, f2_x0 - hp, landing_z_base, **br_kw))
                # Add spindles for landing
                meshes.extend(_spindles_landing_y(outer_x, f1_y1 + hp, landing_y + width - hp, landing_z_base, **sp_kw))
                meshes.extend(_spindles_landing_x(landing_y + width, outer_x + hp, f2_x0 - hp, landing_z_base, **sp_kw))

        # Flight 2 stringers (notched for threshold, flush with riser back)
        if flight2_treads > 0:
            z_fl = riser_t * rise / (2 * going)
            f2_x1_fl = f2_x1 + (-riser_t / 2 if turn_dir == "left" else riser_t / 2)
            f2_z1_fl = f2_z1 + z_fl
            if turn_dir == "left":
                top_face_x = top_post_x + hp
                c_face_x = corner_x - c_hp
            else:
                top_face_x = top_post_x - hp
                c_face_x = corner_x + c_hp
            if render_inner:
                # Extend/trim start to corner newel face
                dx_h = f2_x1 - f2_x0
                if abs(dx_h) > 1e-9:
                    t_c0 = min(1.0, (c_face_x - f2_x0) / dx_h)
                    f2_x0_ic = f2_x0 + t_c0 * dx_h
                    f2_z0_ic = f2_z0 + t_c0 * (f2_z1 - f2_z0)
                else:
                    f2_x0_ic, f2_z0_ic = f2_x0, f2_z0
                # Trim end at top post face (stringer line)
                dx_s = f2_x1_fl - f2_x0
                f2_x1_c, f2_z1_c = f2_x1_fl, f2_z1_fl
                if abs(dx_s) > 1e-9:
                    t_c = max(0.0, min(1.0, (top_face_x - f2_x0) / dx_s))
                    f2_x1_c = f2_x0 + t_c * dx_s
                    f2_z1_c = f2_z0 + t_c * (f2_z1_fl - f2_z0)
                meshes.append(_stringer_flight_x(inner_y, f2_x0_ic, f2_z0_ic, f2_x1_c, f2_z1_c))
                # Trim end at top post face (handrail line)
                f2_x1_hr, f2_z1_hr = f2_x1, f2_z1
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (top_face_x - f2_x0) / dx_h))
                    f2_x1_hr = f2_x0 + t_c * dx_h
                    f2_z1_hr = f2_z0 + t_c * (f2_z1 - f2_z0)
                meshes.append(_handrail_flight_x(inner_y, f2_x0_ic, f2_z0_ic, f2_x1_hr, f2_z1_hr, **hr_kw))
                meshes.append(_baserail_flight_x(inner_y, f2_x0_ic, f2_z0_ic, f2_x1_c, f2_z1_c, **br_kw))
                meshes.extend(_spindles_flight_x(inner_y, f2_x0_ic, f2_z0_ic, f2_x1_c, f2_z1_c, **sp_kw))
            else:
                meshes.append(_stringer_flight_x_notched(inner_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl, ftf, thresh_back, tread_t))
            if render_outer:
                # Outer flight 2: clipped at pitch-change newel face and top post face
                if turn_dir == "left":
                    out_top_face_x = top_post_x - hp  # top newel +X face (flight approaches from +X)
                    pc2_face_x = f2_x0 - hp  # pitch-change newel +X face
                else:
                    out_top_face_x = top_post_x + hp  # top newel -X face
                    pc2_face_x = f2_x0 + hp  # pitch-change newel -X face
                dx_h = f2_x1 - f2_x0
                f2_x1_oc, f2_z1_oc = f2_x1, f2_z1
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (out_top_face_x - f2_x0) / dx_h))
                    f2_x1_oc = f2_x0 + t_c * dx_h
                    f2_z1_oc = f2_z0 + t_c * (f2_z1 - f2_z0)
                f2_x0_oc, f2_z0_oc = f2_x0, f2_z0
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (pc2_face_x - f2_x0) / dx_h))
                    f2_x0_oc = f2_x0 + t_c * dx_h
                    f2_z0_oc = f2_z0 + t_c * (f2_z1 - f2_z0)
                meshes.append(_stringer_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc))
                meshes.append(_handrail_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **hr_kw))
                meshes.append(_baserail_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **br_kw))
                meshes.extend(_spindles_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **sp_kw))
            else:
                meshes.append(_stringer_flight_x_notched(outer_y, f2_x0_ext, z_ext2, f2_x1_fl, f2_z1_fl, ftf, thresh_back, tread_t))

    # --- Pitched stringers for winder flights ---
    if actual_winders > 0:
        inner_x = corner_x
        outer_x = width - corner_x
        nzs = rise * nosing / going

        # Flight 1
        f1_y0 = flight1_shift_y
        f1_y1 = flight1_treads * going + flight1_shift_y
        f1_z0 = rise + nzs
        f1_z1 = (flight1_treads + 1) * rise + nzs
        bot_face_y = bottom_post_y + hp
        dy1 = f1_y1 - f1_y0
        if flight1_treads > 0:
            if render_inner:
                f1_y0_c, f1_z0_c = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_c = f1_y0 + t_c * dy1
                    f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
                # Stringer terminates at rear face of bottom post (no extension for balustrade)
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_stringer = bot_face_y
                if abs(f1_y1 - f1_y0) > 1e-9:
                    t_stringer = (bot_face_y - f1_y0) / (f1_y1 - f1_y0)
                    f1_z0_stringer = f1_z0 + t_stringer * (f1_z1 - f1_z0)
                else:
                    f1_z0_stringer = f1_z0
                # Trim top end at corner newel -Y face
                c_face_y_f1 = corner_y - c_hp
                if abs(dy1) > 1e-9:
                    t_top = max(0.0, min(1.0, (c_face_y_f1 - f1_y0) / dy1))
                    f1_y1_ic = f1_y0 + t_top * dy1
                    f1_z1_ic = f1_z0 + t_top * (f1_z1 - f1_z0)
                else:
                    f1_y1_ic, f1_z1_ic = f1_y1, f1_z1
                meshes.append(_stringer_flight_y(inner_x, f1_y0_stringer, f1_z0_stringer, f1_y1_ic, f1_z1_ic, clip_z_min=0))
                meshes.append(_handrail_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1_ic, f1_z1_ic, **hr_kw))
                meshes.append(_baserail_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1_ic, f1_z1_ic, **br_kw))
                meshes.extend(_spindles_flight_y(inner_x, f1_y0_c, f1_z0_c, f1_y1_ic, f1_z1_ic, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(inner_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))

        # Flight 2 coordinates
        inner_y = landing_y
        outer_y = landing_y + width
        if turn_dir == "left":
            f2_x0 = -winder_offset - nosing - riser_t / 2
            f2_x1 = -(flight2_treads * going) - winder_offset - nosing - riser_t / 2
        else:
            f2_x0 = width + winder_offset + nosing + riser_t / 2
            f2_x1 = width + flight2_treads * going + winder_offset + nosing + riser_t / 2
        f2_z0 = flight2_start_riser * rise + nzs
        f2_z1 = (flight2_start_riser + flight2_treads) * rise + nzs
        z_fl = riser_t * rise / (2 * going)
        f2_x1_fl = f2_x1 + (-riser_t / 2 if turn_dir == "left" else riser_t / 2)
        f2_z1_fl = f2_z1 + z_fl

        # Winder outer stringer geometry (needed by both outer paths)
        outer_corner_y = landing_y + width
        wy_len = abs(outer_corner_y - f1_y1)
        wx_len = abs(outer_x - f2_x0)
        total_path = wy_len + wx_len
        z_winder = f2_z0 - f1_z1
        z_corner = f1_z1 + z_winder * wy_len / total_path if total_path > 1e-9 else f1_z1

        if turn_dir == "left":
            top_face_x = top_post_x + hp
            c_face_x = corner_x - c_hp
        else:
            top_face_x = top_post_x - hp
            c_face_x = corner_x + c_hp

        if flight2_treads > 0:
            if render_inner:
                # Extend/trim start to corner newel face
                dx_h = f2_x1 - f2_x0
                if abs(dx_h) > 1e-9:
                    t_c0 = min(1.0, (c_face_x - f2_x0) / dx_h)
                    f2_x0_ic = f2_x0 + t_c0 * dx_h
                    f2_z0_ic = f2_z0 + t_c0 * (f2_z1 - f2_z0)
                else:
                    f2_x0_ic, f2_z0_ic = f2_x0, f2_z0
                # Trim end at top post face (stringer line)
                dx_s = f2_x1_fl - f2_x0
                f2_x1_c, f2_z1_c = f2_x1_fl, f2_z1_fl
                if abs(dx_s) > 1e-9:
                    t_c = max(0.0, min(1.0, (top_face_x - f2_x0) / dx_s))
                    f2_x1_c = f2_x0 + t_c * dx_s
                    f2_z1_c = f2_z0 + t_c * (f2_z1_fl - f2_z0)
                meshes.append(_stringer_flight_x(inner_y, f2_x0_ic, f2_z0_ic, f2_x1_c, f2_z1_c))
                # Trim end at top post face (handrail line)
                f2_x1_hr, f2_z1_hr = f2_x1, f2_z1
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (top_face_x - f2_x0) / dx_h))
                    f2_x1_hr = f2_x0 + t_c * dx_h
                    f2_z1_hr = f2_z0 + t_c * (f2_z1 - f2_z0)
                meshes.append(_handrail_flight_x(inner_y, f2_x0_ic, f2_z0_ic, f2_x1_hr, f2_z1_hr, **hr_kw))
                meshes.append(_baserail_flight_x(inner_y, f2_x0_ic, f2_z0_ic, f2_x1_c, f2_z1_c, **br_kw))
                meshes.extend(_spindles_flight_x(inner_y, f2_x0_ic, f2_z0_ic, f2_x1_c, f2_z1_c, **sp_kw))
            else:
                meshes.append(_stringer_flight_x_notched(inner_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl, ftf, thresh_back, tread_t))

        if render_outer:
            if flight1_treads > 0:
                # Outer flight 1: clipped at bottom and pitch-change newel faces
                f1_y0_oc, f1_z0_oc = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_oc = f1_y0 + t_c * dy1
                    f1_z0_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
                # Stringer terminates at rear face of bottom post (no extension for balustrade)
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_stringer_outer = bot_face_y
                if abs(f1_y1 - f1_y0) > 1e-9:
                    t_stringer = (bot_face_y - f1_y0) / (f1_y1 - f1_y0)
                    f1_z0_stringer_outer = f1_z0 + t_stringer * (f1_z1 - f1_z0)
                else:
                    f1_z0_stringer_outer = f1_z0
                meshes.append(_stringer_flight_y(outer_x, f1_y0_stringer_outer, f1_z0_stringer_outer, f1_y1, f1_z1, clip_z_min=0))
                meshes.append(_handrail_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **hr_kw))
                meshes.append(_baserail_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **br_kw))
                meshes.extend(_spindles_flight_y(outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **sp_kw))
            # Winder Y-piece: handrail/baserail/spindles from pitch-change newel to outer corner newel
            # Terminate Y-piece flush with front face of X-piece stringer (upper masters lower)
            st2 = STRINGER_THICKNESS / 2
            dy_w = outer_corner_y - f1_y1
            y_ext = outer_corner_y - st2
            z_y_ext = z_corner - st2 * (z_corner - f1_z1) / dy_w if abs(dy_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_y(outer_x, f1_y1, f1_z1, y_ext, z_y_ext,
                                             clip_z_min=0 if flight1_treads == 0 else None))
            pc1_face_y_end = f1_y1 + hp  # +Y face of pitch-change newel
            oc_face_y = outer_corner_y - hp  # -Y face of outer corner newel
            if abs(dy_w) > 1e-9:
                t_oc_y = (oc_face_y - f1_y1) / dy_w
                z_oc_y = f1_z1 + t_oc_y * (z_corner - f1_z1)
            else:
                z_oc_y = z_corner
            meshes.append(_handrail_flight_y(outer_x, pc1_face_y_end, f1_z1, oc_face_y, z_oc_y, **hr_kw))
            meshes.append(_baserail_flight_y(outer_x, pc1_face_y_end, f1_z1, oc_face_y, z_oc_y, **br_kw))
            meshes.extend(_spindles_flight_y(outer_x, pc1_face_y_end, f1_z1, oc_face_y, z_oc_y, **sp_kw))
            # Winder X-piece: handrail/baserail/spindles from outer corner newel to pitch-change newel
            # X-piece extends to Y-piece outer face so upper flight masters at corner
            x_ext = (outer_x + st2) if turn_dir == "left" else (outer_x - st2)
            dx_w = f2_x0 - outer_x
            z_x_ext = z_corner + (x_ext - outer_x) * (f2_z0 - z_corner) / dx_w if abs(dx_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y, x_ext, z_x_ext, f2_x0, f2_z0))
            if turn_dir == "left":
                oc_face_x = outer_x - hp  # -X face
                pc2_face_x = f2_x0 + hp  # +X face of pitch-change newel at f2_x0
            else:
                oc_face_x = outer_x + hp  # +X face
                pc2_face_x = f2_x0 - hp  # -X face
            if abs(dx_w) > 1e-9:
                t_oc_x = (oc_face_x - outer_x) / dx_w
                z_oc_x = z_corner + t_oc_x * (f2_z0 - z_corner)
                t_pc_x = (pc2_face_x - outer_x) / dx_w
                z_pc_x = z_corner + t_pc_x * (f2_z0 - z_corner)
            else:
                z_oc_x, z_pc_x = z_corner, f2_z0
            meshes.append(_handrail_flight_x(outer_corner_y, oc_face_x, z_oc_x, pc2_face_x, z_pc_x, **hr_kw))
            meshes.append(_baserail_flight_x(outer_corner_y, oc_face_x, z_oc_x, pc2_face_x, z_pc_x, **br_kw))
            meshes.extend(_spindles_flight_x(outer_corner_y, oc_face_x, z_oc_x, pc2_face_x, z_pc_x, **sp_kw))
            # Outer flight 2: from pitch-change newel to top post
            if flight2_treads > 0:
                if turn_dir == "left":
                    out_top_face_x = top_post_x - hp
                    pc2_start_x = f2_x0 - hp
                else:
                    out_top_face_x = top_post_x + hp
                    pc2_start_x = f2_x0 + hp
                dx_h = f2_x1 - f2_x0
                f2_x1_oc, f2_z1_oc = f2_x1, f2_z1
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (out_top_face_x - f2_x0) / dx_h))
                    f2_x1_oc = f2_x0 + t_c * dx_h
                    f2_z1_oc = f2_z0 + t_c * (f2_z1 - f2_z0)
                f2_x0_oc, f2_z0_oc = f2_x0, f2_z0
                if abs(dx_h) > 1e-9:
                    t_c = max(0.0, min(1.0, (pc2_start_x - f2_x0) / dx_h))
                    f2_x0_oc = f2_x0 + t_c * dx_h
                    f2_z0_oc = f2_z0 + t_c * (f2_z1 - f2_z0)
                meshes.append(_stringer_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc))
                meshes.append(_handrail_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **hr_kw))
                meshes.append(_baserail_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **br_kw))
                meshes.extend(_spindles_flight_x(outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **sp_kw))
        else:
            # Extend winder corner stringers: upper flight masters lower
            st2 = STRINGER_THICKNESS / 2
            dy_w = outer_corner_y - f1_y1
            y_ext = outer_corner_y - st2
            z_y_ext = z_corner - st2 * (z_corner - f1_z1) / dy_w if abs(dy_w) > 1e-9 else z_corner
            if flight1_treads > 0:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(outer_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))
                meshes.append(_stringer_flight_y(outer_x, f1_y1, f1_z1, y_ext, z_y_ext))
            else:
                # Merge wall extension into winder Y-piece
                yp_slope = (z_corner - f1_z1) / (outer_corner_y - f1_y1) if abs(outer_corner_y - f1_y1) > 1e-9 else 0
                yp_y_start = f1_y1 - WALL_STRINGER_EXTENSION
                yp_z_start = f1_z1 - WALL_STRINGER_EXTENSION * yp_slope
                meshes.append(_stringer_flight_y(outer_x, yp_y_start, yp_z_start, y_ext, z_y_ext, clip_z_min=0))
            x_ext = (outer_x + st2) if turn_dir == "left" else (outer_x - st2)
            dx_w = f2_x0 - outer_x
            z_x_ext = z_corner + (x_ext - outer_x) * (f2_z0 - z_corner) / dx_w if abs(dx_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y, x_ext, z_x_ext, f2_x0, f2_z0))
            if flight2_treads > 0:
                meshes.append(_stringer_flight_x_notched(outer_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl, ftf, thresh_back, tread_t))

    # --- Newel posts (top = 150mm above highest abutting handrail) ---
    NEWEL_CAP = 150.0
    hr_rise = p["handrail_rise"]
    nzs_hr = rise * nosing / going
    inner_x = corner_x
    outer_x = width - corner_x
    outer_y_pos = landing_y + width

    # Inner newel posts
    if render_inner:
        if flight1_treads > 0:
            hr_bot = rise + nzs_hr + hr_rise
            bot_h = hr_bot + NEWEL_CAP
            meshes.append(_box_mesh(inner_x, bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355"))
        hr_c_f1 = (flight1_treads + 1) * rise + nzs_hr + hr_rise
        hr_c_f2 = flight2_start_riser * rise + nzs_hr + hr_rise
        c_h = max(hr_c_f1, hr_c_f2) + NEWEL_CAP
        meshes.append(_box_mesh(inner_x, landing_y, c_h / 2, c_ns, c_ns, c_h, "#8B7355"))
        if flight2_treads > 0:
            # Top newel extends FROM cutting plane (150mm below stringer bottom) UPWARD
            pitch_line_top = (flight2_start_riser + flight2_treads) * rise + nzs_hr
            newel_bottom = pitch_line_top - 400.0
            newel_top = pitch_line_top + hr_rise + NEWEL_CAP
            top_h = newel_top - newel_bottom
            top_z_center = (newel_bottom + newel_top) / 2
            meshes.append(_box_mesh(top_post_x, landing_y, top_z_center, ns, ns, top_h, "#8B7355"))
    else:
        # Wall condition on inner side: add stub newel at corner (no stringers)
        # Stub: 50mm below F1 stringer bottom, 50mm above F2 stringer top
        pitch_f1 = (flight1_treads + 1) * rise + nzs_hr
        pitch_f2 = flight2_start_riser * rise + nzs_hr
        f1_stringer_bottom = pitch_f1 - (STRINGER_HEIGHT - STRINGER_PITCH_OFFSET)
        f2_stringer_top    = pitch_f2 + STRINGER_PITCH_OFFSET
        stub_bottom = f1_stringer_bottom - 50.0
        stub_top    = f2_stringer_top    + 50.0
        stub_h = stub_top - stub_bottom
        stub_z_center = (stub_top + stub_bottom) / 2
        meshes.append(_box_mesh(inner_x, landing_y, stub_z_center, ns, ns, stub_h, "#8B7355"))
        # Note: Stub stringers removed - they were causing green artifacts

    # Outer newel posts (bottom, pitch-change at f1_y1, outer corner, pitch-change at f2_x0, top)
    if render_outer:
        nzs_w = rise * nosing / going
        if flight1_treads > 0:
            hr_bot = rise + nzs_w + hr_rise
            bot_h = hr_bot + NEWEL_CAP
            meshes.append(_box_mesh(outer_x, bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355"))
        # Pitch-change newel where flight 1 meets winder/landing on outer wall
        f1_y1_val = flight1_treads * going + flight1_shift_y
        hr_pc1 = (flight1_treads + 1) * rise + nzs_w + hr_rise
        pc1_h = hr_pc1 + NEWEL_CAP
        meshes.append(_box_mesh(outer_x, f1_y1_val, pc1_h / 2, ns, ns, pc1_h, "#8B7355"))
        # Outer corner newel (where Y-run meets X-run)
        oc_hr = max(hr_pc1, flight2_start_riser * rise + nzs_w + hr_rise)
        oc_h = oc_hr + NEWEL_CAP
        meshes.append(_box_mesh(outer_x, outer_y_pos, oc_h / 2, ns, ns, oc_h, "#8B7355"))
        # Pitch-change newel where winder/landing meets flight 2 on outer wall
        f2_x0_val = (-winder_offset - nosing - riser_t / 2) if turn_dir == "left" \
            else (width + winder_offset + nosing + riser_t / 2)
        hr_pc2 = flight2_start_riser * rise + nzs_w + hr_rise
        pc2_h = hr_pc2 + NEWEL_CAP
        meshes.append(_box_mesh(f2_x0_val, outer_y_pos, pc2_h / 2, ns, ns, pc2_h, "#8B7355"))
        # Top newel - extends FROM cutting plane (150mm below stringer bottom) UPWARD
        if flight2_treads > 0:
            pitch_line_top = (flight2_start_riser + flight2_treads) * rise + nzs_w
            newel_bottom = pitch_line_top - 400.0
            newel_top = pitch_line_top + hr_rise + NEWEL_CAP
            top_h = newel_top - newel_bottom
            top_z_center = (newel_bottom + newel_top) / 2
            meshes.append(_box_mesh(top_post_x, outer_y_pos, top_z_center, ns, ns, top_h, "#8B7355"))

    return meshes




def _preview_y_shaped(p):
    """Y-shaped stair: Flight 1 goes +Y, then a flat landing, with two departure flights
    springing symmetrically — Flight 2L going -X from x=0 and Flight 2R going +X from x=width.
    No winders; always a flat landing. No mirror or winder toggle applicable.
    """
    meshes = []
    width = p["stair_width"] - STRINGER_THICKNESS
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]

    hr_kw = {"hr_width": p["handrail_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"]}
    br_kw = {"br_width": p["baserail_width"], "br_height": p["baserail_height"]}
    sp_kw = {"spindle_size": p["spindle_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"], "br_height": p["baserail_height"]}

    # left_condition controls F1 left side (x=0) + F2L outer (y=outer_corner_y)
    # right_condition controls F1 right side (x=width) + F2R outer (y=outer_corner_y)
    render_left  = p["left_condition"]  == "balustrade"
    render_right = p["right_condition"] == "balustrade"

    # Always flat landing — split treads between F1 and F2
    straight_treads = num_treads
    f1_ov, f2_ov = p.get("flight1_steps", -1), p.get("flight2_steps", -1)
    if f1_ov >= 0 and f2_ov >= 0 and f1_ov + f2_ov == straight_treads:
        flight1_treads = f1_ov
        flight2_treads = f2_ov
    else:
        flight1_treads = straight_treads // 2
        flight2_treads = straight_treads - flight1_treads

    ns = p["newel_size"]
    hp = ns / 2.0
    flight1_shift_y = 0.0
    bottom_post_y = -nosing

    # ── Flight 1 treads (+Y) ──────────────────────────────────────────────
    for i in range(flight1_treads):
        tread_y = i * going - nosing
        tread_z = (i + 1) * rise - tread_t
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c"
        ))

    riser_h = rise - tread_t
    for i in range(flight1_treads + 1):
        if riser_t > 0:
            meshes.append(_box_mesh(
                width / 2, i * going + riser_t / 2, i * rise + riser_h / 2,
                width, riser_t, riser_h, "#e8dcc8"
            ))

    winder_start_riser = flight1_treads + 1
    corner_y = flight1_treads * going        # top riser Y of F1
    outer_corner_y = corner_y + width        # far edge of landing

    # ── Landing tread (flat, extends both sides) ──────────────────────────
    landing_z = winder_start_riser * rise - tread_t
    ext = nosing + riser_t
    meshes.append(_box_mesh(
        width / 2, corner_y + width / 2, landing_z + tread_t / 2,
        width + 2 * ext, width, tread_t, "#c8a87c",
        name="Landing", ifc_type="landing",
    ))

    # Landing consumes 1 rise; adjust flight 2
    flight2_start_riser = winder_start_riser + 1
    flight2_treads = max(0, flight2_treads - 1)

    winder_offset = 0.0
    flight2_shift = nosing + riser_t / 2

    # ── Departure flight coordinates ─────────────────────────────────────
    # F2L goes -X from x=0;  F2R goes +X from x=width
    f2L_x0 = -(nosing + riser_t / 2)
    f2L_x1 = -(flight2_treads * going + nosing + riser_t / 2)
    f2R_x0 =  width + nosing + riser_t / 2
    f2R_x1 =  width + flight2_treads * going + nosing + riser_t / 2

    nzs = rise * nosing / going
    f2_z0 = flight2_start_riser * rise + nzs
    f2_z1 = (flight2_start_riser + flight2_treads) * rise + nzs

    # ── F2L treads ────────────────────────────────────────────────────────
    for i in range(flight2_treads):
        tread_z = (flight2_start_riser + i) * rise - tread_t
        tread_x = -(i * going) - going / 2 + nosing / 2 - flight2_shift
        meshes.append(_box_mesh(
            tread_x, corner_y + width / 2, tread_z + tread_t / 2,
            going + nosing + riser_t, width, tread_t, "#c8a87c"
        ))

    # ── F2R treads ────────────────────────────────────────────────────────
    for i in range(flight2_treads):
        tread_z = (flight2_start_riser + i) * rise - tread_t
        tread_x = width + i * going + going / 2 - nosing / 2 + flight2_shift
        meshes.append(_box_mesh(
            tread_x, corner_y + width / 2, tread_z + tread_t / 2,
            going + nosing + riser_t, width, tread_t, "#c8a87c"
        ))

    # ── F2L risers ────────────────────────────────────────────────────────
    if riser_t > 0:
        for i in range(flight2_treads + 1):
            riser_z = (flight2_start_riser + i - 1) * rise + riser_h / 2
            riser_x = -(i * going + nosing + riser_t / 2)
            meshes.append(_box_mesh(
                riser_x, corner_y + width / 2, riser_z,
                riser_t, width, riser_h, "#e8dcc8"
            ))

    # ── F2R risers ────────────────────────────────────────────────────────
    if riser_t > 0:
        for i in range(flight2_treads + 1):
            riser_z = (flight2_start_riser + i - 1) * rise + riser_h / 2
            riser_x = width + i * going + nosing + riser_t / 2
            meshes.append(_box_mesh(
                riser_x, corner_y + width / 2, riser_z,
                riser_t, width, riser_h, "#e8dcc8"
            ))

    # ── Threshold strips ──────────────────────────────────────────────────
    ftf = (num_treads + 1) * rise
    threshold_d = p["threshold_depth"]
    thresh_front_L = -(flight2_treads * going) + nosing
    thresh_back_L  = thresh_front_L - threshold_d
    thresh_front_R =  width + flight2_treads * going - nosing
    thresh_back_R  = thresh_front_R + threshold_d
    meshes.append(_box_mesh(
        (thresh_front_L + thresh_back_L) / 2, corner_y + width / 2, ftf - tread_t / 2,
        threshold_d, width, tread_t, "#c8a87c",
        name="Threshold L", ifc_type="threshold",
    ))
    meshes.append(_box_mesh(
        (thresh_front_R + thresh_back_R) / 2, corner_y + width / 2, ftf - tread_t / 2,
        threshold_d, width, tread_t, "#c8a87c",
        name="Threshold R", ifc_type="threshold",
    ))

    # ── Stringer setup ───────────────────────────────────────────────────
    st2 = STRINGER_THICKNESS / 2
    landing_z_base = winder_start_riser * rise
    land_top = landing_z_base + STRINGER_DROP
    z_ext = land_top - STRINGER_PITCH_OFFSET

    # F1 pitch-line coordinates
    f1_y0 = 0.0
    f1_y1 = flight1_treads * going
    f1_z0 = rise + nzs
    f1_z1 = (flight1_treads + 1) * rise + nzs
    dy1 = f1_y1 - f1_y0

    # Extend pitch line to landing elevation (for wall condition)
    f1_y1_ext = f1_y1 + (z_ext - f1_z1) * dy1 / (f1_z1 - f1_z0) if abs(f1_z1 - f1_z0) > 1e-9 else f1_y1

    # F2 pitch-line coordinates
    dx_L = f2L_x1 - f2L_x0
    dz_L = f2_z1 - f2_z0
    dx_R = f2R_x1 - f2R_x0
    dz_R = f2_z1 - f2_z0
    f2L_x0_ext = f2L_x0 + (z_ext - f2_z0) * dx_L / dz_L if abs(dz_L) > 1e-9 else f2L_x0
    f2R_x0_ext = f2R_x0 + (z_ext - f2_z0) * dx_R / dz_R if abs(dz_R) > 1e-9 else f2R_x0

    bot_face_y = bottom_post_y + hp

    # ── Flight 1 stringers ────────────────────────────────────────────────
    if flight1_treads > 0:
        # Trim top of stringer/balustrade at pitch-change newel face
        pc_face_y = f1_y1 - hp
        if abs(dy1) > 1e-9:
            t_top = (pc_face_y - f1_y0) / dy1
            f1_y1_trim = pc_face_y
            f1_z1_trim = f1_z0 + t_top * (f1_z1 - f1_z0)
        else:
            f1_y1_trim = f1_y1
            f1_z1_trim = f1_z1

        # Clip balustrade start at bottom-post face
        def _clip_start(y0, z0, y1, z1):
            if abs(y1 - y0) > 1e-9 and bot_face_y > y0:
                t = min(1.0, (bot_face_y - y0) / (y1 - y0))
                return y0 + t * (y1 - y0), z0 + t * (z1 - z0)
            return y0, z0

        f1_y0_c, f1_z0_c = _clip_start(f1_y0, f1_z0, f1_y1, f1_z1)
        # Stringer starts at rear face of bottom post
        f1_y0_str = bot_face_y
        if abs(f1_y1 - f1_y0) > 1e-9:
            t_str = (bot_face_y - f1_y0) / (f1_y1 - f1_y0)
            f1_z0_str = f1_z0 + t_str * (f1_z1 - f1_z0)
        else:
            f1_z0_str = f1_z0

        _slope_f1 = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0

        # Left side (x=0)
        if render_left:
            meshes.append(_stringer_flight_y(0, f1_y0_str, f1_z0_str, f1_y1_trim, f1_z1_trim, clip_z_min=0))
            meshes.append(_handrail_flight_y(0, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **hr_kw))
            meshes.append(_baserail_flight_y(0, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **br_kw))
            meshes.extend(_spindles_flight_y(0, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **sp_kw))
        else:
            f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
            f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope_f1
            meshes.append(_stringer_flight_y(0, f1_y0_w, f1_z0_w, f1_y1_ext, z_ext, clip_z_min=0))

        # Right side (x=width)
        if render_right:
            meshes.append(_stringer_flight_y(width, f1_y0_str, f1_z0_str, f1_y1_trim, f1_z1_trim, clip_z_min=0))
            meshes.append(_handrail_flight_y(width, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **hr_kw))
            meshes.append(_baserail_flight_y(width, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **br_kw))
            meshes.extend(_spindles_flight_y(width, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **sp_kw))
        else:
            f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
            f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope_f1
            meshes.append(_stringer_flight_y(width, f1_y0_w, f1_z0_w, f1_y1_ext, z_ext, clip_z_min=0))

    # ── Landing stringers ─────────────────────────────────────────────────
    # Y-direction landing stringers at x=0 and x=width removed — not required
    # for the Y-shaped stair; the departure flight inner/outer stringers frame
    # each branch directly.  X-direction stringers also not needed.

    # Landing handrails / baserails / spindles
    # Y-direction side balustrades (x=0 and x=width) removed — not required at the landing sides.
    if render_left:
        meshes.append(_handrail_landing_x(outer_corner_y, f2L_x0 + hp, 0 - hp, landing_z_base, **hr_kw))
        meshes.append(_baserail_landing_x(outer_corner_y, f2L_x0 + hp, 0 - hp, landing_z_base, **br_kw))
        meshes.extend(_spindles_landing_x(outer_corner_y, f2L_x0 + hp, 0 - hp, landing_z_base, **sp_kw))

    if render_right:
        meshes.append(_handrail_landing_x(outer_corner_y, width + hp, f2R_x0 - hp, landing_z_base, **hr_kw))
        meshes.append(_baserail_landing_x(outer_corner_y, width + hp, f2R_x0 - hp, landing_z_base, **br_kw))
        meshes.extend(_spindles_landing_x(outer_corner_y, width + hp, f2R_x0 - hp, landing_z_base, **sp_kw))

    # ── Departure flight stringers ────────────────────────────────────────
    if flight2_treads > 0:
        z_fl = riser_t * rise / (2 * going)
        f2L_x1_fl = f2L_x1 - riser_t / 2
        f2L_z1_fl = f2_z1 + z_fl
        f2R_x1_fl = f2R_x1 + riser_t / 2
        f2R_z1_fl = f2_z1 + z_fl

        # Inner corner face positions for trimming balustrade start
        c_ns = max(ns, 100.0) if (flight1_treads == 0 or flight2_treads == 0) else ns
        c_hp = c_ns / 2.0
        c_face_x_L = 0     - c_hp   # -X face of inner corner at x=0
        c_face_x_R = width + c_hp   # +X face of inner corner at x=width
        top_face_x_L = thresh_front_L + hp   # end-post face toward F2L
        top_face_x_R = thresh_front_R - hp   # end-post face toward F2R

        def _trim_x(x0, z0, x1, z1, face, clamp=True):
            dx = x1 - x0
            if abs(dx) < 1e-9:
                return x0, z0
            t = (face - x0) / dx
            if clamp:
                t = max(0.0, min(1.0, t))
            return x0 + t * dx, z0 + t * (z1 - z0)

        # F2L inner (y=corner_y) — balustrade moved here from outer side
        f2L_x0_ic, f2L_z0_ic = _trim_x(f2L_x0, f2_z0, f2L_x1, f2_z1, c_face_x_L)
        f2L_x1_ic, f2L_z1_ic = _trim_x(f2L_x0, f2_z0, f2L_x1_fl, f2L_z1_fl, top_face_x_L)
        f2L_x1_hr, f2L_z1_hr = _trim_x(f2L_x0, f2_z0, f2L_x1,    f2_z1,     top_face_x_L)
        if render_left:
            meshes.append(_stringer_flight_x(corner_y, f2L_x0_ic, f2L_z0_ic, f2L_x1_ic, f2L_z1_ic))
            meshes.append(_handrail_flight_x(corner_y, f2L_x0_ic, f2L_z0_ic, f2L_x1_hr, f2L_z1_hr, **hr_kw))
            meshes.append(_baserail_flight_x(corner_y, f2L_x0_ic, f2L_z0_ic, f2L_x1_ic, f2L_z1_ic, **br_kw))
            meshes.extend(_spindles_flight_x(corner_y, f2L_x0_ic, f2L_z0_ic, f2L_x1_ic, f2L_z1_ic, **sp_kw))

        # F2L outer (y=outer_corner_y) — wall stringer, starts at Y-stringer face for clean join
        meshes.append(_stringer_flight_x_notched(outer_corner_y, -st2, z_ext,
                                                 f2L_x1_fl, f2L_z1_fl, ftf, thresh_back_L, tread_t))

        # F2R outer (y=outer_corner_y) — notched wall stringer from Y-stringer face for clean join
        meshes.append(_stringer_flight_x_notched(outer_corner_y, width + st2, z_ext,
                                                 f2R_x1_fl, f2R_z1_fl, ftf, thresh_back_R, tread_t))
        if render_right:
            pc2_face_x_R  = f2R_x0 - hp          # pitch-change newel -X face
            out_top_x_R   = thresh_front_R + hp   # top newel +X face
            f2R_x0_oc, f2R_z0_oc = _trim_x(f2R_x0, f2_z0, f2R_x1, f2_z1, pc2_face_x_R)
            f2R_x1_oc, f2R_z1_oc = _trim_x(f2R_x0, f2_z0, f2R_x1, f2_z1, out_top_x_R)
            meshes.append(_handrail_flight_x(outer_corner_y, f2R_x0_oc, f2R_z0_oc, f2R_x1_oc, f2R_z1_oc, **hr_kw))
            meshes.append(_baserail_flight_x(outer_corner_y, f2R_x0_oc, f2R_z0_oc, f2R_x1_oc, f2R_z1_oc, **br_kw))
            meshes.extend(_spindles_flight_x(outer_corner_y, f2R_x0_oc, f2R_z0_oc, f2R_x1_oc, f2R_z1_oc, **sp_kw))

    # ── Newel posts ───────────────────────────────────────────────────────
    NEWEL_CAP = 150.0
    hr_rise = p["handrail_rise"]
    nzs_hr = nzs

    # Bottom posts (foot of F1)
    if flight1_treads > 0:
        hr_bot = rise + nzs_hr + hr_rise
        bot_h = hr_bot + NEWEL_CAP
        if render_left:
            meshes.append(_box_mesh(0,     bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355"))
        if render_right:
            meshes.append(_box_mesh(width, bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355"))

    # Pitch-change posts at top of F1 (= start of landing)
    f1_y1_val = float(flight1_treads * going)
    hr_pc1 = (flight1_treads + 1) * rise + nzs_hr + hr_rise
    pc1_h = hr_pc1 + NEWEL_CAP
    if render_left:
        meshes.append(_box_mesh(0,     f1_y1_val, pc1_h / 2, ns, ns, pc1_h, "#8B7355"))
    if render_right:
        meshes.append(_box_mesh(width, f1_y1_val, pc1_h / 2, ns, ns, pc1_h, "#8B7355"))

    # Outer corner posts at (0, outer_corner_y) and (width, outer_corner_y)
    oc_hr = max(hr_pc1, flight2_start_riser * rise + nzs_hr + hr_rise)
    oc_h = oc_hr + NEWEL_CAP
    if render_left:
        meshes.append(_box_mesh(0,     outer_corner_y, oc_h / 2, ns, ns, oc_h, "#8B7355"))
    if render_right:
        meshes.append(_box_mesh(width, outer_corner_y, oc_h / 2, ns, ns, oc_h, "#8B7355"))

    # Pitch-change posts at departure starts (on outer_corner_y line)
    hr_pc2 = flight2_start_riser * rise + nzs_hr + hr_rise
    pc2_h = hr_pc2 + NEWEL_CAP
    if render_left:
        meshes.append(_box_mesh(f2L_x0, outer_corner_y, pc2_h / 2, ns, ns, pc2_h, "#8B7355"))
    if render_right:
        meshes.append(_box_mesh(f2R_x0, outer_corner_y, pc2_h / 2, ns, ns, pc2_h, "#8B7355"))

    # Top posts (end of departure flights)
    if flight2_treads > 0:
        pitch_top = (flight2_start_riser + flight2_treads) * rise + nzs_hr
        newel_bot = pitch_top - 400.0
        newel_top_z = pitch_top + hr_rise + NEWEL_CAP
        top_h = newel_top_z - newel_bot
        top_zc = (newel_bot + newel_top_z) / 2
        # Inner top posts (always)
        meshes.append(_box_mesh(thresh_front_L, corner_y,       top_zc, ns, ns, top_h, "#8B7355"))
        meshes.append(_box_mesh(thresh_front_R, corner_y,       top_zc, ns, ns, top_h, "#8B7355"))
        # Outer top posts
        if render_left:
            meshes.append(_box_mesh(thresh_front_L, outer_corner_y, top_zc, ns, ns, top_h, "#8B7355"))
        if render_right:
            meshes.append(_box_mesh(thresh_front_R, outer_corner_y, top_zc, ns, ns, top_h, "#8B7355"))

    return meshes




def _preview_double_winder(p):
    import math
    meshes = []
    width = p["stair_width"] - STRINGER_THICKNESS
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    winders1 = p["turn1_winders"]
    winders2 = p["turn2_winders"]
    turn1_dir = p["turn1_direction"]
    turn2_dir = p["turn2_direction"]
    turn1_enabled = p.get("turn1_enabled", True)
    turn2_enabled = p.get("turn2_enabled", True)

    # Balustrade keyword dicts (passed to handrail/baserail/spindle helpers)
    hr_kw = {"hr_width": p["handrail_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"]}
    br_kw = {"br_width": p["baserail_width"], "br_height": p["baserail_height"]}
    sp_kw = {"spindle_size": p["spindle_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"], "br_height": p["baserail_height"]}

    # Map left/right conditions to inner/outer based on turn1 direction
    if turn1_dir == "left":
        render_inner = p["left_condition"] == "balustrade"
        render_outer = p["right_condition"] == "balustrade"
    else:
        render_inner = p["right_condition"] == "balustrade"
        render_outer = p["left_condition"] == "balustrade"

    actual_winders1 = winders1 if turn1_enabled else 0
    actual_winders2 = winders2 if turn2_enabled else 0
    total_winders = actual_winders1 + actual_winders2
    straight_treads = num_treads - total_winders
    # Use custom flight distribution if provided and valid
    f1_ov = p.get("flight1_steps", -1)
    f2_ov = p.get("flight2_steps", -1)
    f3_ov = p.get("flight3_steps", -1)
    if f1_ov >= 0 and f2_ov >= 0 and f3_ov >= 0 and f1_ov + f2_ov + f3_ov == straight_treads:
        flight1_treads = f1_ov
        flight2_treads = f2_ov
        flight3_treads = f3_ov
    else:
        flight1_treads = straight_treads // 3
        flight2_treads = straight_treads // 3
        flight3_treads = straight_treads - flight1_treads - flight2_treads

    # Step 3: Calculate offset and half-post
    ns = p["newel_size"]
    hp = ns / 2.0
    wg = compute_winder_geometry(ns, width)
    offset = wg["offset"]
    wx = p["winder_x"]
    wy = p["winder_y"]
    wx2 = p["winder_x2"]
    wy2 = p["winder_y2"]

    riser_idx = 0
    flight1_shift_y = (hp - wx - wy + nosing) if actual_winders1 > 0 else 0.0

    # Flight 1 (offset by X+Y from internal corner)
    for i in range(flight1_treads):
        tread_y = i * going - nosing + flight1_shift_y
        tread_z = (i + 1) * rise - tread_t
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c",
            name=f"Flight 1 Tread {i+1}", ifc_type="tread",
        ))

    riser_h = rise - tread_t
    for i in range(flight1_treads + 1):
        if riser_t > 0:
            # No offset needed - landing will be positioned to overhang naturally
            landing_riser_offset = 0.0
            meshes.append(_box_mesh(
                width / 2, i * going + riser_t / 2 + flight1_shift_y + landing_riser_offset, i * rise + riser_h / 2,
                width, riser_t, riser_h, "#e8dcc8",
                name=f"Riser F1-{i+1}", ifc_type="riser",
            ))

    riser_idx = flight1_treads + 1

    # Turn 1 winders — construction-based profiles
    corner1_y = flight1_treads * going
    corner1_x = 0 if turn1_dir == "left" else width

    # Landing 1 position — shifted forward by nosing when flat landing replaces winders
    # This ensures the landing overhangs the last flight 1 riser correctly
    landing1_y = corner1_y - nosing if actual_winders1 == 0 else corner1_y

    turn1_winder_start = riser_idx
    for i in range(actual_winders1):
        winder_z = (riser_idx + i) * rise - tread_t
        profile = _winder_profiles_from_construction(
            corner1_x, corner1_y, ns, width,
            turn1_dir, i, actual_winders1,
            riser_extension=riser_t + nosing,
            flight_extension=wx + wy - 2 * hp,
            winder_x=wx)
        meshes.append({
            "type": "winder_polygon",
            "profile": [[pt[0], pt[1]] for pt in profile],
            "z": winder_z,
            "thickness": tread_t,
            "color": "#d4a574",
            "name": f"Turn1 Winder {i+1}",
            "ifc_type": "winder_tread",
        })

    # Turn 1 winder risers
    meshes.extend(_winder_riser_meshes(
        corner1_x, corner1_y, ns, width, turn1_dir,
        actual_winders1, turn1_winder_start, rise, tread_t, riser_t,
        nosing=nosing, winder_x=wx))

    # Newel post at turn 1 — placed at end with handrail-based height

    # Bottom newel post (foot of staircase, centred on first tread nosing line)
    bottom_post_y = flight1_shift_y - nosing

    # Turn 1 landing tread when winders are off
    if actual_winders1 == 0:
        landing1_z = turn1_winder_start * rise - tread_t
        # Landing extends asymmetrically to reach back face of flight 2's first riser
        # Extends by nosing + riser_t on the wall side only
        hp = ns / 2
        landing1_w = width + nosing + riser_t
        if turn1_dir == "right":
            landing1_cx = (width + nosing + riser_t) / 2
        else:  # left turn
            landing1_cx = (width - nosing - riser_t) / 2
        landing1_depth = width + nosing
        landing1_cy = landing1_y + landing1_depth / 2
        meshes.append(_box_mesh(
            landing1_cx,
            landing1_cy,
            landing1_z + tread_t / 2,
            landing1_w, landing1_depth, tread_t, "#c8a87c",
            name="Landing 1", ifc_type="landing",
        ))

    riser_idx += actual_winders1
    # When turn 1 winders are off, the landing consumes 1 rise — shift flight 2 up
    if actual_winders1 == 0:
        riser_idx += 1
        flight2_treads = max(0, flight2_treads - 1)
    flight2_riser_start = riser_idx

    # Flight 2 Y center position — matches landing center when flat landing is used
    flight2_y_center = landing1_y + (width + nosing) / 2 if actual_winders1 == 0 else landing1_y + width / 2

    # Flight 2 (perpendicular, offset by X+Y from internal corner)
    winder_offset1 = (wx + wy - hp) if actual_winders1 > 0 else 0.0
    flight2_shift = winder_offset1 + nosing + riser_t / 2
    for i in range(flight2_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        if turn1_dir == "left":
            tread_x = -(i * going) - going / 2 + nosing / 2 - flight2_shift
        else:
            tread_x = width + i * going + going / 2 - nosing / 2 + flight2_shift
        meshes.append(_box_mesh(
            tread_x, flight2_y_center, tread_z + tread_t / 2,
            going + nosing + riser_t, width, tread_t, "#c8a87c",
            name=f"Flight 2 Tread {i+1}", ifc_type="tread",
        ))

    # Flight 2 risers
    if riser_t > 0:
        for i in range(flight2_treads + 1):
            riser_z = (flight2_riser_start + i - 1) * rise + riser_h / 2
            if turn1_dir == "left":
                riser_x = -(i * going) - winder_offset1 - nosing - riser_t / 2
            else:
                riser_x = width + i * going + winder_offset1 + nosing + riser_t / 2
            meshes.append(_box_mesh(
                riser_x, flight2_y_center, riser_z,
                riser_t, width, riser_h, "#e8dcc8",
                name=f"Riser F2-{i+1}", ifc_type="riser",
            ))

    riser_idx += flight2_treads

    # Turn 2 winders — corner2 links flight 2 top riser (offset1) to turn 2 entry (offset2)
    winder_offset2 = (wx2 + wy2 - hp) if actual_winders2 > 0 else 0.0
    if turn1_dir == "left":
        corner2_x = -(flight2_treads * going) - winder_offset1 - winder_offset2
    else:
        corner2_x = width + flight2_treads * going + winder_offset1 + winder_offset2
    # Corner 2 Y position matches landing1_y to maintain alignment when corner 1 is a flat landing
    corner2_y = landing1_y

    # Turn 2 rotation: flight 2 approaches along -X (left) or +X (right)
    turn2_rotation = 90 if turn1_dir == "left" else -90

    turn2_winder_start = riser_idx
    for i in range(actual_winders2):
        winder_z = (riser_idx + i) * rise - tread_t
        profile = _winder_profiles_from_construction(
            corner2_x, corner2_y, ns, width,
            turn2_dir, i, actual_winders2,
            rotation=turn2_rotation,
            riser_extension=riser_t + nosing,
            flight_extension=wx2 + wy2 - 2 * hp,
            winder_x=wx2)
        meshes.append({
            "type": "winder_polygon",
            "profile": [[pt[0], pt[1]] for pt in profile],
            "z": winder_z,
            "thickness": tread_t,
            "color": "#d4a574",
            "name": f"Turn2 Winder {i+1}",
            "ifc_type": "winder_tread",
        })

    # Turn 2 winder risers
    meshes.extend(_winder_riser_meshes(
        corner2_x, corner2_y, ns, width, turn2_dir,
        actual_winders2, turn2_winder_start, rise, tread_t, riser_t,
        nosing=nosing, rotation=turn2_rotation, winder_x=wx2))

    # Newel post at turn 2 — placed at end with handrail-based height

    riser_idx += actual_winders2
    # When turn 2 winders are off, the landing consumes 1 rise — shift flight 3 up
    if actual_winders2 == 0:
        riser_idx += 1
        flight3_treads = max(0, flight3_treads - 1)
    flight3_riser_start = riser_idx

    if turn1_dir == "left" and turn2_dir == "left":
        flight3_start_x = corner2_x - width
        flight3_start_y = corner2_y
    elif turn1_dir == "right" and turn2_dir == "right":
        flight3_start_x = corner2_x
        flight3_start_y = corner2_y
    elif turn1_dir == "left" and turn2_dir == "right":
        flight3_start_x = corner2_x
        flight3_start_y = corner2_y + width
    else:
        flight3_start_x = corner2_x - width
        flight3_start_y = corner2_y + width

    # Turn 2 landing tread when winders are off
    if actual_winders2 == 0:
        landing2_z = turn2_winder_start * rise - tread_t
        hp = ns / 2
        # Landing extends asymmetrically to reach back face of flight 3's first riser
        # Extends by nosing + riser_t on the wall side only (in -Y direction for flight 3)
        landing2_cx = flight3_start_x + width / 2
        landing2_depth = width + 2 * nosing + riser_t
        landing2_cy = corner2_y + (width - riser_t) / 2
        meshes.append(_box_mesh(
            landing2_cx,
            landing2_cy,
            landing2_z + tread_t / 2,
            width, landing2_depth, tread_t, "#c8a87c",
            name="Landing 2", ifc_type="landing",
        ))

    # Flight 3 shift — nosing centred on post when winders off
    if actual_winders2 > 0:
        flight3_shift_y = -(winder_offset2 + riser_t)
    else:
        flight3_shift_y = -(flight3_start_y - corner2_y) - riser_t

    for i in range(flight3_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        tread_y = flight3_start_y - (i + 1) * going - nosing + flight3_shift_y
        tread_length = going + nosing + riser_t
        meshes.append(_box_mesh(
            flight3_start_x + width / 2, tread_y + tread_length / 2, tread_z + tread_t / 2,
            width, tread_length, tread_t, "#c8a87c",
            name=f"Flight 3 Tread {i+1}", ifc_type="tread",
        ))

    # Flight 3 risers (going in -Y direction)
    if riser_t > 0:
        for i in range(flight3_treads + 1):
            riser_z = (flight3_riser_start + i - 1) * rise + riser_h / 2
            riser_y = flight3_start_y - i * going - nosing + riser_t / 2 + flight3_shift_y
            meshes.append(_box_mesh(
                flight3_start_x + width / 2, riser_y, riser_z,
                width, riser_t, riser_h, "#e8dcc8",
                name=f"Riser F3-{i+1}", ifc_type="riser",
            ))

    # --- Landing threshold strip (flight 3 top) ---
    ftf = (num_treads + 1) * rise
    threshold_d = p["threshold_depth"]
    thresh_riser_y = flight3_start_y - flight3_treads * going + flight3_shift_y
    thresh_front_y = thresh_riser_y + nosing
    thresh_back_y = thresh_front_y - threshold_d
    meshes.append(_box_mesh(
        flight3_start_x + width / 2,
        (thresh_front_y + thresh_back_y) / 2,
        ftf - tread_t / 2,
        width, threshold_d, tread_t, "#c8a87c",
        name="Threshold", ifc_type="threshold",
    ))

    # Top newel post y position (centred on threshold nosing line)
    top_post_y = thresh_front_y

    # Corner / end post half-sizes (auto-enlarged to 100mm when absorbing
    # a 0-tread flight's newel)
    c1_ns = max(ns, 100.0) if flight1_treads == 0 else ns
    c2_ns = max(ns, 100.0) if flight3_treads == 0 else ns
    c1_hp = c1_ns / 2.0
    c2_hp = c2_ns / 2.0

    # --- Stringers (only for flat landings) ---
    if actual_winders1 == 0 or actual_winders2 == 0:
        # Stringer X positions: inner (newel side) and outer (wall side)
        # Flight 1 inner = corner1_x, outer = width - corner1_x
        f1_inner_x = corner1_x          # 0 for left, width for right
        f1_outer_x = width - corner1_x  # width for left, 0 for right
        f2_x_last_ext = None  # set below if flight 2 outer extends to landing 2
        nzs = rise * nosing / going  # nosing z-shift: pitch line offset at nosing vs riser

        if actual_winders1 == 0:
            # === Flight 1 coordinates ===
            f1_y0 = flight1_shift_y
            f1_y1 = flight1_treads * going + flight1_shift_y
            f1_z0 = rise + nzs
            f1_z1 = (flight1_treads + 1) * rise + nzs

            landing1_z = turn1_winder_start * rise
            land1_top = landing1_z + STRINGER_DROP
            # Flight 1 outer extension along pitch
            z_ext1 = land1_top - STRINGER_PITCH_OFFSET
            dy1 = f1_y1 - f1_y0
            dz1 = f1_z1 - f1_z0
            f1_y1_ext = f1_y1 + (z_ext1 - f1_z1) * dy1 / dz1 if abs(dz1) > 1e-9 else f1_y1

            # === Flight 2 coordinates + extensions (computed before landing stringers) ===
            f2_inner_y = landing1_y
            f2_outer_y = landing1_y + width
            if turn1_dir == "left":
                f2_x_first = -winder_offset1 - nosing - riser_t / 2
                f2_x_last = -(flight2_treads * going) - winder_offset1 - nosing - riser_t / 2
            else:
                f2_x_first = width + winder_offset1 + nosing + riser_t / 2
                f2_x_last = width + flight2_treads * going + winder_offset1 + nosing + riser_t / 2
            f2_z_first = flight2_riser_start * rise + nzs
            f2_z_last = (flight2_riser_start + flight2_treads) * rise + nzs
            # Save unclipped positions for balustrade newel face calculations
            f2_x_last_unclipped = f2_x_last
            f2_z_last_unclipped = f2_z_last
            # Clip far end at corner2 post centre if turn 2 also has a landing
            if actual_winders2 == 0 and flight2_treads > 0:
                dx = f2_x_last - f2_x_first
                if abs(dx) > 1e-9:
                    t_clip = (corner2_x - f2_x_first) / dx
                    t_clip = max(0.0, min(1.0, t_clip))
                    f2_x_last = f2_x_first + t_clip * dx
                    f2_z_last = f2_z_first + t_clip * (f2_z_last - f2_z_first)
            # Flight 2 outer extensions
            f2_dx = f2_x_last - f2_x_first
            f2_dz = f2_z_last - f2_z_first
            f2_x_first_ext, f2_z_first_ext = f2_x_first, f2_z_first
            f2_x_last_ext_v, f2_z_last_ext = f2_x_last, f2_z_last
            if abs(f2_dz) > 1e-9:
                z_ext_s = land1_top - STRINGER_PITCH_OFFSET
                f2_x_first_ext = f2_x_first + (z_ext_s - f2_z_first) * f2_dx / f2_dz
                f2_z_first_ext = z_ext_s
            if actual_winders2 == 0 and abs(f2_dz) > 1e-9:
                land2_top_pre = turn2_winder_start * rise + STRINGER_DROP
                z_ext_e = land2_top_pre - STRINGER_PITCH_OFFSET
                f2_x_last_ext_v = f2_x_last + (z_ext_e - f2_z_last) * f2_dx / f2_dz
                f2_z_last_ext = z_ext_e
            f2_x_last_ext = f2_x_last_ext_v  # share with turn 2 section

            # === Flight 1 stringers ===
            bot_face_y = bottom_post_y + hp
            dy1 = f1_y1 - f1_y0
            # Calculate trimmed top position at pitch-change newel face
            pc_face_y_f1 = f1_y1 - hp
            if abs(dy1) > 1e-9:
                t_top = (pc_face_y_f1 - f1_y0) / dy1
                f1_y1_trim = pc_face_y_f1
                f1_z1_trim = f1_z0 + t_top * (f1_z1 - f1_z0)
            else:
                f1_y1_trim = f1_y1
                f1_z1_trim = f1_z1

            if render_inner:
                f1_y0_c, f1_z0_c = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_c = f1_y0 + t_c * dy1
                    f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
                # Stringer terminates at rear face of bottom post (no extension for balustrade)
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_stringer = bot_face_y
                if abs(f1_y1 - f1_y0) > 1e-9:
                    t_stringer = (bot_face_y - f1_y0) / (f1_y1 - f1_y0)
                    f1_z0_stringer = f1_z0 + t_stringer * (f1_z1 - f1_z0)
                else:
                    f1_z0_stringer = f1_z0
                meshes.append(_stringer_flight_y(f1_inner_x, f1_y0_stringer, f1_z0_stringer, f1_y1_trim, f1_z1_trim, clip_z_min=0))
                meshes.append(_handrail_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **hr_kw))
                meshes.append(_baserail_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **br_kw))
                meshes.extend(_spindles_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1_trim, f1_z1_trim, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(f1_inner_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))
            if render_outer:
                f1_y0_oc, f1_z0_oc = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_oc = f1_y0 + t_c * dy1
                    f1_z0_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
                # Stringer terminates at rear face of bottom post (no extension for balustrade)
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_stringer_outer = bot_face_y
                if abs(f1_y1 - f1_y0) > 1e-9:
                    t_stringer = (bot_face_y - f1_y0) / (f1_y1 - f1_y0)
                    f1_z0_stringer_outer = f1_z0 + t_stringer * (f1_z1 - f1_z0)
                else:
                    f1_z0_stringer_outer = f1_z0
                meshes.append(_stringer_flight_y(f1_outer_x, f1_y0_stringer_outer, f1_z0_stringer_outer, f1_y1_trim, f1_z1_trim, clip_z_min=0))
                meshes.append(_handrail_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1_trim, f1_z1_trim, **hr_kw))
                meshes.append(_baserail_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1_trim, f1_z1_trim, **br_kw))
                # Spindles: from bottom post face to pitch-change newel face
                meshes.extend(_spindles_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1_trim, f1_z1_trim, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(f1_outer_x, f1_y0_w, f1_z0_w, f1_y1_ext, z_ext1, clip_z_min=0))

            # === Turn 1 landing stringers — outer endpoints linked to extensions ===
            st2 = STRINGER_THICKNESS / 2
            # Outer corner newel position
            outer1_corner_y = landing1_y + width
            # Landing stringer endpoints: use newel face when balustrade present, extended position otherwise
            if turn1_dir == "left":
                f2_landing_x_end = f2_x_first + hp if render_outer else f2_x_first_ext
            else:
                f2_landing_x_start = f2_x_first - hp if render_outer else f2_x_first_ext
            # Y-direction landing stringer masters the X stringer: extends through the full X
            # stringer thickness to its rear edge (+st2 past the X stringer centre).
            # Handrail/baserail/spindles still terminate at the newel post face (hp).
            f1_landing_y_start = (f1_y1 + hp) if render_outer else f1_y1_ext
            f1_landing_y_end = outer1_corner_y + st2
            # In wall condition, drop landing stringers to align top edge with flight stringers
            landing1_z_stringer = landing1_z if render_outer else (landing1_z - STRINGER_PITCH_OFFSET)
            if turn1_dir == "left":
                meshes.append(_stringer_landing_x(landing1_y, f2_x_first, f1_inner_x, landing1_z))
                # Outer landing stringers - Y runs newel-to-newel, X stops flush with Y stringer face
                meshes.append(_stringer_landing_y(f1_outer_x, f1_landing_y_start, f1_landing_y_end, landing1_z_stringer))
                meshes.append(_stringer_landing_x(outer1_corner_y, f2_landing_x_end, f1_outer_x - st2, landing1_z_stringer))
                if render_outer:
                    # Add handrails and baserails for landing when balustrade is present
                    # Run from newel post face to newel post face to eliminate gaps
                    meshes.append(_handrail_landing_y(f1_outer_x, f1_y1 + hp, landing1_y + width - hp, landing1_z, **hr_kw))
                    meshes.append(_handrail_landing_x(landing1_y + width, f2_x_first + hp, f1_outer_x - hp, landing1_z, **hr_kw))
                    meshes.append(_baserail_landing_y(f1_outer_x, f1_y1 + hp, landing1_y + width - hp, landing1_z, **br_kw))
                    meshes.append(_baserail_landing_x(landing1_y + width, f2_x_first + hp, f1_outer_x - hp, landing1_z, **br_kw))
                    # Add spindles for landing
                    meshes.extend(_spindles_landing_y(f1_outer_x, f1_y1 + hp, landing1_y + width - hp, landing1_z, **sp_kw))
                    meshes.extend(_spindles_landing_x(landing1_y + width, f2_x_first + hp, f1_outer_x - hp, landing1_z, **sp_kw))
            else:
                meshes.append(_stringer_landing_x(landing1_y, f1_inner_x, f2_x_first, landing1_z))
                # Outer landing stringers - Y runs newel-to-newel, X stops flush with Y stringer face
                meshes.append(_stringer_landing_y(f1_outer_x, f1_landing_y_start, f1_landing_y_end, landing1_z_stringer))
                meshes.append(_stringer_landing_x(outer1_corner_y, f1_outer_x + st2, f2_landing_x_start, landing1_z_stringer))
                if render_outer:
                    # Add handrails and baserails for landing when balustrade is present
                    # Run from newel post face to newel post face to eliminate gaps
                    meshes.append(_handrail_landing_y(f1_outer_x, f1_y1 + hp, landing1_y + width - hp, landing1_z, **hr_kw))
                    meshes.append(_handrail_landing_x(landing1_y + width, f1_outer_x + hp, f2_x_first - hp, landing1_z, **hr_kw))
                    meshes.append(_baserail_landing_y(f1_outer_x, f1_y1 + hp, landing1_y + width - hp, landing1_z, **br_kw))
                    meshes.append(_baserail_landing_x(landing1_y + width, f1_outer_x + hp, f2_x_first - hp, landing1_z, **br_kw))
                    # Add spindles for landing
                    meshes.extend(_spindles_landing_y(f1_outer_x, f1_y1 + hp, landing1_y + width - hp, landing1_z, **sp_kw))
                    meshes.extend(_spindles_landing_x(landing1_y + width, f1_outer_x + hp, f2_x_first - hp, landing1_z, **sp_kw))

            # === Flight 2 stringers — trim inner to corner newel faces ===
            f2_dx = f2_x_last - f2_x_first
            if render_inner:
                if abs(f2_dx) > 1e-9:
                    if turn1_dir == "left":
                        c1_face_x = corner1_x - c1_hp
                        c2_face_x = corner2_x + c2_hp
                    else:
                        c1_face_x = corner1_x + c1_hp
                        c2_face_x = corner2_x - c2_hp
                    t0 = (c1_face_x - f2_x_first) / f2_dx
                    t1 = (c2_face_x - f2_x_first) / f2_dx
                    f2_ic_z0 = f2_z_first + t0 * (f2_z_last - f2_z_first)
                    f2_ic_z1 = f2_z_first + t1 * (f2_z_last - f2_z_first)
                    meshes.append(_stringer_flight_x(f2_inner_y, c1_face_x, f2_ic_z0, c2_face_x, f2_ic_z1))
                    meshes.append(_handrail_flight_x(f2_inner_y, c1_face_x, f2_ic_z0, c2_face_x, f2_ic_z1, **hr_kw))
                    meshes.append(_baserail_flight_x(f2_inner_y, c1_face_x, f2_ic_z0, c2_face_x, f2_ic_z1, **br_kw))
                    meshes.extend(_spindles_flight_x(f2_inner_y, c1_face_x, f2_ic_z0, c2_face_x, f2_ic_z1, **sp_kw))
                else:
                    meshes.append(_stringer_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))
                    meshes.append(_handrail_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **hr_kw))
                    meshes.append(_baserail_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **br_kw))
                    meshes.extend(_spindles_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **sp_kw))
            else:
                meshes.append(_stringer_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))
            if render_outer:
                # Outer flight 2: clipped at pitch-change newel faces
                if turn1_dir == "left":
                    pc1_face_x = f2_x_first + hp  # +X face of pitch-change newel at f2 start
                    # Use unclipped position for flat landing to extend to actual newel face
                    pc2_face_x = f2_x_last - hp if actual_winders2 > 0 else f2_x_last_unclipped - hp  # face toward f2
                else:
                    pc1_face_x = f2_x_first - hp
                    # Use unclipped position for flat landing to extend to actual newel face
                    pc2_face_x = f2_x_last + hp if actual_winders2 > 0 else f2_x_last_unclipped + hp
                f2_x0_oc, f2_z0_oc = f2_x_first, f2_z_first
                # Use unclipped position for flat landing at turn 2
                f2_x1_oc = f2_x_last_unclipped if actual_winders2 == 0 else f2_x_last
                f2_z1_oc = f2_z_last_unclipped if actual_winders2 == 0 else f2_z_last
                if abs(f2_dx) > 1e-9:
                    # For flat landing at turn 2, calculate using unclipped positions for both ends
                    if actual_winders2 == 0:
                        dx_full = f2_x_last_unclipped - f2_x_first
                        dz_full = f2_z_last_unclipped - f2_z_first
                        if abs(dx_full) > 1e-9:
                            t_c0 = (pc1_face_x - f2_x_first) / dx_full
                            f2_x0_oc = f2_x_first + t_c0 * dx_full
                            f2_z0_oc = f2_z_first + t_c0 * dz_full
                            t_c2 = (pc2_face_x - f2_x_first) / dx_full
                            f2_x1_oc = f2_x_first + t_c2 * dx_full
                            f2_z1_oc = f2_z_first + t_c2 * dz_full
                    else:
                        t_c = max(0.0, min(1.0, (pc1_face_x - f2_x_first) / f2_dx))
                        f2_x0_oc = f2_x_first + t_c * f2_dx
                        f2_z0_oc = f2_z_first + t_c * (f2_z_last - f2_z_first)
                        t_c2 = max(0.0, min(1.0, (pc2_face_x - f2_x_first) / f2_dx))
                        f2_x1_oc = f2_x_first + t_c2 * f2_dx
                        f2_z1_oc = f2_z_first + t_c2 * (f2_z_last - f2_z_first)
                meshes.append(_stringer_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc))
                meshes.append(_handrail_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **hr_kw))
                meshes.append(_baserail_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **br_kw))
                meshes.extend(_spindles_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **sp_kw))
            else:
                meshes.append(_stringer_flight_x(f2_outer_y, f2_x_first_ext, f2_z_first_ext,
                                                 f2_x_last_ext_v, f2_z_last_ext))

        if actual_winders2 == 0:
            # When turn 1 uses winders, f2 variables haven't been set yet — compute them
            if actual_winders1 > 0:
                nzs = rise * nosing / going
                if turn1_dir == "left":
                    f2_x_first = -winder_offset1 - nosing - riser_t / 2
                    f2_x_last = -(flight2_treads * going) - winder_offset1 - nosing - riser_t / 2
                else:
                    f2_x_first = width + winder_offset1 + nosing + riser_t / 2
                    f2_x_last = width + flight2_treads * going + winder_offset1 + nosing + riser_t / 2
                f2_z_first = flight2_riser_start * rise + nzs
                f2_z_last = (flight2_riser_start + flight2_treads) * rise + nzs
                f2_x_last_unclipped = f2_x_last
                f2_z_last_unclipped = f2_z_last
                # Clip far end at corner2 post centre
                if flight2_treads > 0:
                    dx = f2_x_last - f2_x_first
                    if abs(dx) > 1e-9:
                        t_clip = max(0.0, min(1.0, (corner2_x - f2_x_first) / dx))
                        f2_x_last = f2_x_first + t_clip * dx
                        f2_z_last = f2_z_first + t_clip * (f2_z_last - f2_z_first)
                f2_inner_y = landing1_y
                f2_outer_y = landing1_y + width
                f1_outer_x = width - corner1_x
                f2_x_last_ext = None

            landing2_z = turn2_winder_start * rise
            land2_top = landing2_z + STRINGER_DROP

            # Flight 3: outer = wall side, inner = newel side
            # f3_wall_x is the outer (wall) edge — inner/outer are swapped vs flight 1
            if turn1_dir == turn2_dir:
                f3_outer_x = flight3_start_x + corner1_x        # wall side
                f3_inner_x = flight3_start_x + width - corner1_x  # newel side
            else:
                f3_outer_x = flight3_start_x + width - corner1_x  # wall side
                f3_inner_x = flight3_start_x + corner1_x          # newel side

            # Flight 3 coordinates + clipping + outer extension
            f3_y_first = flight3_start_y - nosing + riser_t / 2 + flight3_shift_y
            f3_y_first_unclipped = f3_y_first  # Save for newel post face calculations
            f3_y_last = flight3_start_y - flight3_treads * going - nosing + riser_t / 2 + flight3_shift_y
            f3_z_first = flight3_riser_start * rise + nzs
            f3_z_last = (flight3_riser_start + flight3_treads) * rise + nzs
            # Clip near end at corner2 post centre Y
            if flight3_treads > 0:
                dy = f3_y_last - f3_y_first
                if abs(dy) > 1e-9:
                    t_clip = (corner2_y - f3_y_first) / dy
                    t_clip = max(0.0, min(1.0, t_clip))
                    f3_y_first = f3_y_first + t_clip * dy if t_clip > 0 else f3_y_first
                    f3_z_first = f3_z_first + t_clip * (f3_z_last - f3_z_first) if t_clip > 0 else f3_z_first
            # Flight 3 outer extension along pitch
            f3_y_first_ext, f3_z_first_ext = f3_y_first, f3_z_first
            f3_dy = f3_y_last - f3_y_first
            f3_dz = f3_z_last - f3_z_first
            if abs(f3_dz) > 1e-9:
                z_ext3 = land2_top - STRINGER_PITCH_OFFSET
                f3_y_first_ext = f3_y_first + (z_ext3 - f3_z_first) * f3_dy / f3_dz
                f3_z_first_ext = z_ext3

            # === Turn 2 landing stringers — outer endpoints linked to extensions ===
            st2 = STRINGER_THICKNESS / 2
            # Outer corner newel position
            outer2_corner_y = corner2_y + width
            # Y-direction landing stringer masters the X stringer: extends through the full X
            # stringer thickness to its rear edge (+st2 past the X stringer centre).
            f3_landing_y_start = outer2_corner_y + st2
            f3_landing_y_end = f3_y_first_unclipped + hp if render_outer else f3_y_first_ext
            # In wall condition, drop landing stringers to align top edge with flight stringers
            landing2_z_stringer = landing2_z if render_outer else (landing2_z - STRINGER_PITCH_OFFSET)
            # Outer landing stringers - Y runs newel-to-newel, X stops flush with Y stringer face
            meshes.append(_stringer_landing_y(f3_outer_x, f3_landing_y_start, f3_landing_y_end, landing2_z_stringer))
            x_inner_end = f2_x_last_ext if f2_x_last_ext is not None else corner2_x
            if f3_outer_x < x_inner_end:
                # X stringer approaching from right, stop at right face of Y stringer
                meshes.append(_stringer_landing_x(outer2_corner_y, x_inner_end, f3_outer_x + st2, landing2_z_stringer))
                if render_outer:
                    # Run from newel post face to newel post face to eliminate gaps
                    meshes.append(_handrail_landing_x(outer2_corner_y, f2_x_last - hp, f3_outer_x + hp, landing2_z, **hr_kw))
                    meshes.append(_baserail_landing_x(outer2_corner_y, f2_x_last - hp, f3_outer_x + hp, landing2_z, **br_kw))
                    meshes.extend(_spindles_landing_x(outer2_corner_y, f2_x_last - hp, f3_outer_x + hp, landing2_z, **sp_kw))
            else:
                # X stringer approaching from left, stop at left face of Y stringer
                meshes.append(_stringer_landing_x(outer2_corner_y, x_inner_end, f3_outer_x - st2, landing2_z_stringer))
                if render_outer:
                    # Run from newel post face to newel post face to eliminate gaps
                    meshes.append(_handrail_landing_x(outer2_corner_y, f2_x_last + hp, f3_outer_x - hp, landing2_z, **hr_kw))
                    meshes.append(_baserail_landing_x(outer2_corner_y, f2_x_last + hp, f3_outer_x - hp, landing2_z, **br_kw))
                    meshes.extend(_spindles_landing_x(outer2_corner_y, f2_x_last + hp, f3_outer_x - hp, landing2_z, **sp_kw))
            if render_outer:
                # Add Y-direction landing handrail, baserail, and spindles
                # Run from newel post face to newel post face to eliminate gaps
                meshes.append(_handrail_landing_y(f3_outer_x, corner2_y + width - hp, f3_y_first_unclipped + hp, landing2_z, **hr_kw))
                meshes.append(_baserail_landing_y(f3_outer_x, corner2_y + width - hp, f3_y_first_unclipped + hp, landing2_z, **br_kw))
                meshes.extend(_spindles_landing_y(f3_outer_x, corner2_y + width - hp, f3_y_first_unclipped + hp, landing2_z, **sp_kw))

            # === Flight 3 stringers (notched for threshold, flush with riser back) ===
            z_fl = riser_t * rise / (2 * going)
            f3_y_last_fl = f3_y_last - riser_t / 2
            f3_z_last_fl = f3_z_last + z_fl
            top_face_y = top_post_y + hp
            dy3h = f3_y_last - f3_y_first
            if render_inner:
                dy3s = f3_y_last_fl - f3_y_first
                f3_y_end_c, f3_z_end_c = f3_y_last_fl, f3_z_last_fl
                if abs(dy3s) > 1e-9 and top_face_y > f3_y_last_fl:
                    t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3s))
                    f3_y_end_c = f3_y_first + t_c * dy3s
                    f3_z_end_c = f3_z_first + t_c * (f3_z_last_fl - f3_z_first)
                f3_y_hr_c, f3_z_hr_c = f3_y_last, f3_z_last
                if abs(dy3h) > 1e-9 and top_face_y > f3_y_last:
                    t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3h))
                    f3_y_hr_c = f3_y_first + t_c * dy3h
                    f3_z_hr_c = f3_z_first + t_c * (f3_z_last - f3_z_first)
                # Trim start at corner2 newel face
                c2_face_f3 = (corner2_y + c2_hp) if f3_y_first_unclipped > corner2_y else (corner2_y - c2_hp)
                dy3_full = f3_y_last - f3_y_first
                if abs(dy3_full) > 1e-9:
                    t_c2f = (c2_face_f3 - f3_y_first) / dy3_full
                    f3_z_c2 = f3_z_first + t_c2f * (f3_z_last - f3_z_first)
                else:
                    f3_z_c2 = f3_z_first
                if abs(dy3s) > 1e-9:
                    t_c2fs = (c2_face_f3 - f3_y_first) / dy3s
                    f3_z_c2s = f3_z_first + t_c2fs * (f3_z_last_fl - f3_z_first)
                else:
                    f3_z_c2s = f3_z_first
                meshes.append(_stringer_flight_y(f3_inner_x, c2_face_f3, f3_z_c2s,
                                                 f3_y_end_c, f3_z_end_c))
                meshes.append(_handrail_flight_y(f3_inner_x, c2_face_f3, f3_z_c2,
                                                 f3_y_hr_c, f3_z_hr_c, **hr_kw))
                meshes.append(_baserail_flight_y(f3_inner_x, c2_face_f3, f3_z_c2s,
                                                 f3_y_end_c, f3_z_end_c, **br_kw))
                meshes.extend(_spindles_flight_y(f3_inner_x, c2_face_f3, f3_z_c2,
                                                 f3_y_hr_c, f3_z_hr_c, **sp_kw))
            else:
                meshes.append(_stringer_flight_y_notched(f3_inner_x, f3_y_first, f3_z_first,
                                                         f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))
            if render_outer:
                # Outer flight 3: from pitch-change newel face to top newel face
                pc_face_f3 = f3_y_first - hp  # -Y face (toward flight)
                top_face_y_out = top_post_y + hp  # +Y face (toward flight)
                f3_y0_oc, f3_z0_oc = f3_y_first, f3_z_first
                f3_y1_oc, f3_z1_oc = f3_y_last, f3_z_last
                if abs(dy3h) > 1e-9:
                    t_c0 = max(0.0, min(1.0, (pc_face_f3 - f3_y_first) / dy3h))
                    f3_y0_oc = f3_y_first + t_c0 * dy3h
                    f3_z0_oc = f3_z_first + t_c0 * (f3_z_last - f3_z_first)
                    t_c1 = max(0.0, min(1.0, (top_face_y_out - f3_y_first) / dy3h))
                    f3_y1_oc = f3_y_first + t_c1 * dy3h
                    f3_z1_oc = f3_z_first + t_c1 * (f3_z_last - f3_z_first)
                meshes.append(_stringer_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc))
                meshes.append(_handrail_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc, **hr_kw))
                meshes.append(_baserail_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc, **br_kw))
                meshes.extend(_spindles_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc, **sp_kw))
            else:
                meshes.append(_stringer_flight_y_notched(f3_outer_x, f3_y_first_ext, f3_z_first_ext,
                                                         f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))

    # --- Pitched stringers for winder flights ---
    if actual_winders1 > 0:
        nzs = rise * nosing / going
        f1_inner_x = corner1_x
        f1_outer_x = width - corner1_x

        # Flight 1 stringers
        f1_y0 = flight1_shift_y
        f1_y1 = flight1_treads * going + flight1_shift_y
        f1_z0 = rise + nzs
        f1_z1 = (flight1_treads + 1) * rise + nzs
        bot_face_y = bottom_post_y + hp
        dy1 = f1_y1 - f1_y0
        if flight1_treads > 0:
            if render_inner:
                f1_y0_c, f1_z0_c = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_c = f1_y0 + t_c * dy1
                    f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
                # Stringer terminates at rear face of bottom post (no extension for balustrade)
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_stringer = bot_face_y
                if abs(f1_y1 - f1_y0) > 1e-9:
                    t_stringer = (bot_face_y - f1_y0) / (f1_y1 - f1_y0)
                    f1_z0_stringer = f1_z0 + t_stringer * (f1_z1 - f1_z0)
                else:
                    f1_z0_stringer = f1_z0
                # Trim top end at corner1 newel -Y face
                c1_face_y_f1 = corner1_y - c1_hp
                if abs(dy1) > 1e-9:
                    t_top = max(0.0, min(1.0, (c1_face_y_f1 - f1_y0) / dy1))
                    f1_y1_ic = f1_y0 + t_top * dy1
                    f1_z1_ic = f1_z0 + t_top * (f1_z1 - f1_z0)
                else:
                    f1_y1_ic, f1_z1_ic = f1_y1, f1_z1
                meshes.append(_stringer_flight_y(f1_inner_x, f1_y0_stringer, f1_z0_stringer, f1_y1_ic, f1_z1_ic, clip_z_min=0))
                meshes.append(_handrail_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1_ic, f1_z1_ic, **hr_kw))
                meshes.append(_baserail_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1_ic, f1_z1_ic, **br_kw))
                meshes.extend(_spindles_flight_y(f1_inner_x, f1_y0_c, f1_z0_c, f1_y1_ic, f1_z1_ic, **sp_kw))
            else:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(f1_inner_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))

        # Turn 1 winder outer stringer geometry
        outer_corner_y1 = landing1_y + width
        f2_inner_y = landing1_y
        f2_outer_y = landing1_y + width
        if turn1_dir == "left":
            f2_x_first = -winder_offset1 - nosing - riser_t / 2
            f2_x_last = -(flight2_treads * going) - winder_offset1 - nosing - riser_t / 2
        else:
            f2_x_first = width + winder_offset1 + nosing + riser_t / 2
            f2_x_last = width + flight2_treads * going + winder_offset1 + nosing + riser_t / 2
        f2_z_first = flight2_riser_start * rise + nzs
        f2_z_last = (flight2_riser_start + flight2_treads) * rise + nzs
        wy_len = abs(outer_corner_y1 - f1_y1)
        wx_len = abs(f1_outer_x - f2_x_first)
        total_path = wy_len + wx_len
        z_winder = f2_z_first - f1_z1
        z_corner = f1_z1 + z_winder * wy_len / total_path if total_path > 1e-9 else f1_z1

        if render_outer:
            if flight1_treads > 0:
                # Outer flight 1: clipped at bottom and pitch-change newel faces
                f1_y0_oc, f1_z0_oc = f1_y0, f1_z0
                if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
                    t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
                    f1_y0_oc = f1_y0 + t_c * dy1
                    f1_z0_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
                # Stringer terminates at rear face of bottom post (no extension for balustrade)
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_stringer_outer = bot_face_y
                if abs(f1_y1 - f1_y0) > 1e-9:
                    t_stringer = (bot_face_y - f1_y0) / (f1_y1 - f1_y0)
                    f1_z0_stringer_outer = f1_z0 + t_stringer * (f1_z1 - f1_z0)
                else:
                    f1_z0_stringer_outer = f1_z0
                meshes.append(_stringer_flight_y(f1_outer_x, f1_y0_stringer_outer, f1_z0_stringer_outer, f1_y1, f1_z1, clip_z_min=0))
                meshes.append(_handrail_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **hr_kw))
                meshes.append(_baserail_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **br_kw))
                meshes.extend(_spindles_flight_y(f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1, f1_z1, **sp_kw))
            # Winder Y-piece: handrail/baserail/spindles from pitch-change newel to outer corner newel
            # Terminate Y-piece flush with front face of X-piece stringer (X-piece masters)
            st2 = STRINGER_THICKNESS / 2
            dy_w = outer_corner_y1 - f1_y1
            y_ext = outer_corner_y1 - st2
            z_y_ext = z_corner - st2 * (z_corner - f1_z1) / dy_w if abs(dy_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_y(f1_outer_x, f1_y1, f1_z1, y_ext, z_y_ext,
                                             clip_z_min=0 if flight1_treads == 0 else None))
            pc1_face_y_end = f1_y1 + hp
            oc_face_y = outer_corner_y1 - hp
            if abs(dy_w) > 1e-9:
                t_oc_y = (oc_face_y - f1_y1) / dy_w
                z_oc_y = f1_z1 + t_oc_y * (z_corner - f1_z1)
            else:
                z_oc_y = z_corner
            meshes.append(_handrail_flight_y(f1_outer_x, pc1_face_y_end, f1_z1, oc_face_y, z_oc_y, **hr_kw))
            meshes.append(_baserail_flight_y(f1_outer_x, pc1_face_y_end, f1_z1, oc_face_y, z_oc_y, **br_kw))
            meshes.extend(_spindles_flight_y(f1_outer_x, pc1_face_y_end, f1_z1, oc_face_y, z_oc_y, **sp_kw))
            # Winder X-piece: handrail/baserail/spindles from outer corner newel to pitch-change newel
            # X-piece extends to Y-piece outer face so upper flight masters at corner
            dx_w = f2_x_first - f1_outer_x
            x_ext = (f1_outer_x + st2) if turn1_dir == "left" else (f1_outer_x - st2)
            z_x_ext = z_corner + (x_ext - f1_outer_x) * (f2_z_first - z_corner) / dx_w if abs(dx_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y1, x_ext, z_x_ext, f2_x_first, f2_z_first))
            if turn1_dir == "left":
                oc_face_x = f1_outer_x - hp
                pc2_face_x = f2_x_first + hp
            else:
                oc_face_x = f1_outer_x + hp
                pc2_face_x = f2_x_first - hp
            if abs(dx_w) > 1e-9:
                t_oc = (oc_face_x - f1_outer_x) / dx_w
                z_oc = z_corner + t_oc * (f2_z_first - z_corner)
                t_pc = (pc2_face_x - f1_outer_x) / dx_w
                z_pc = z_corner + t_pc * (f2_z_first - z_corner)
            else:
                z_oc, z_pc = z_corner, f2_z_first
            meshes.append(_handrail_flight_x(outer_corner_y1, oc_face_x, z_oc, pc2_face_x, z_pc, **hr_kw))
            meshes.append(_baserail_flight_x(outer_corner_y1, oc_face_x, z_oc, pc2_face_x, z_pc, **br_kw))
            meshes.extend(_spindles_flight_x(outer_corner_y1, oc_face_x, z_oc, pc2_face_x, z_pc, **sp_kw))
            # Outer flight 2: from pitch-change newel to next pitch-change/top newel
            f2_dx = f2_x_last - f2_x_first
            if turn1_dir == "left":
                pc2_start_x = f2_x_first - hp
                pc2_end_x = f2_x_last + hp if actual_winders2 > 0 else f2_x_last + hp
            else:
                pc2_start_x = f2_x_first + hp
                pc2_end_x = f2_x_last - hp if actual_winders2 > 0 else f2_x_last - hp
            f2_x0_oc, f2_z0_oc = f2_x_first, f2_z_first
            f2_x1_oc, f2_z1_oc = f2_x_last, f2_z_last
            if abs(f2_dx) > 1e-9:
                t_c = max(0.0, min(1.0, (pc2_start_x - f2_x_first) / f2_dx))
                f2_x0_oc = f2_x_first + t_c * f2_dx
                f2_z0_oc = f2_z_first + t_c * (f2_z_last - f2_z_first)
                t_c2 = max(0.0, min(1.0, (pc2_end_x - f2_x_first) / f2_dx))
                f2_x1_oc = f2_x_first + t_c2 * f2_dx
                f2_z1_oc = f2_z_first + t_c2 * (f2_z_last - f2_z_first)
            meshes.append(_stringer_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc))
            meshes.append(_handrail_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **hr_kw))
            meshes.append(_baserail_flight_x(f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc, **br_kw))
            if abs(f2_dx) > 1e-9:
                meshes.extend(_spindles_flight_x(f2_outer_y, pc2_start_x, f2_z0_oc, pc2_end_x, f2_z1_oc, **sp_kw))
        else:
            # Extend winder corner stringers: upper flight masters lower
            st2 = STRINGER_THICKNESS / 2
            dy_w = outer_corner_y1 - f1_y1
            y_ext = outer_corner_y1 - st2
            z_y_ext = z_corner - st2 * (z_corner - f1_z1) / dy_w if abs(dy_w) > 1e-9 else z_corner
            if flight1_treads > 0:
                _slope = (f1_z1 - f1_z0) / (f1_y1 - f1_y0) if abs(f1_y1 - f1_y0) > 1e-9 else 0
                f1_y0_w = f1_y0 - WALL_STRINGER_EXTENSION
                f1_z0_w = f1_z0 - WALL_STRINGER_EXTENSION * _slope
                meshes.append(_stringer_flight_y(f1_outer_x, f1_y0_w, f1_z0_w, f1_y1, f1_z1, clip_z_min=0))
                meshes.append(_stringer_flight_y(f1_outer_x, f1_y1, f1_z1, y_ext, z_y_ext))
            else:
                # Merge wall extension into winder Y-piece
                yp_slope = (z_corner - f1_z1) / (outer_corner_y1 - f1_y1) if abs(outer_corner_y1 - f1_y1) > 1e-9 else 0
                yp_y_start = f1_y1 - WALL_STRINGER_EXTENSION
                yp_z_start = f1_z1 - WALL_STRINGER_EXTENSION * yp_slope
                meshes.append(_stringer_flight_y(f1_outer_x, yp_y_start, yp_z_start, y_ext, z_y_ext, clip_z_min=0))
            dx_w = f2_x_first - f1_outer_x
            x_ext = (f1_outer_x + st2) if turn1_dir == "left" else (f1_outer_x - st2)
            z_x_ext = z_corner + (x_ext - f1_outer_x) * (f2_z_first - z_corner) / dx_w if abs(dx_w) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y1, x_ext, z_x_ext, f2_x_first, f2_z_first))
            meshes.append(_stringer_flight_x(f2_outer_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))

        # Flight 2 inner stringers — trim to corner newel faces
        if render_inner:
            f2_dx = f2_x_last - f2_x_first
            if abs(f2_dx) > 1e-9:
                if turn1_dir == "left":
                    c1_face_x = corner1_x - c1_hp
                    c2_face_x = corner2_x + c2_hp
                else:
                    c1_face_x = corner1_x + c1_hp
                    c2_face_x = corner2_x - c2_hp
                t0 = (c1_face_x - f2_x_first) / f2_dx
                t1 = (c2_face_x - f2_x_first) / f2_dx
                f2_ic_z0 = f2_z_first + t0 * (f2_z_last - f2_z_first)
                f2_ic_z1 = f2_z_first + t1 * (f2_z_last - f2_z_first)
                meshes.append(_stringer_flight_x(f2_inner_y, c1_face_x, f2_ic_z0, c2_face_x, f2_ic_z1))
                meshes.append(_handrail_flight_x(f2_inner_y, c1_face_x, f2_ic_z0, c2_face_x, f2_ic_z1, **hr_kw))
                meshes.append(_baserail_flight_x(f2_inner_y, c1_face_x, f2_ic_z0, c2_face_x, f2_ic_z1, **br_kw))
                meshes.extend(_spindles_flight_x(f2_inner_y, c1_face_x, f2_ic_z0, c2_face_x, f2_ic_z1, **sp_kw))
            else:
                meshes.append(_stringer_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))
                meshes.append(_handrail_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **hr_kw))
                meshes.append(_baserail_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **br_kw))
                meshes.extend(_spindles_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **sp_kw))
        else:
            meshes.append(_stringer_flight_x(f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))

    if actual_winders2 > 0:
        nzs = rise * nosing / going
        # Flight 3 X positions
        if turn1_dir == turn2_dir:
            f3_outer_x = flight3_start_x + corner1_x
            f3_inner_x = flight3_start_x + width - corner1_x
        else:
            f3_outer_x = flight3_start_x + width - corner1_x
            f3_inner_x = flight3_start_x + corner1_x

        # Flight 3 coordinates
        f3_y_first = flight3_start_y - nosing + riser_t / 2 + flight3_shift_y
        f3_y_last = flight3_start_y - flight3_treads * going - nosing + riser_t / 2 + flight3_shift_y
        f3_z_first = flight3_riser_start * rise + nzs
        f3_z_last = (flight3_riser_start + flight3_treads) * rise + nzs
        z_fl = riser_t * rise / (2 * going)
        f3_y_last_fl = f3_y_last - riser_t / 2
        f3_z_last_fl = f3_z_last + z_fl
        top_face_y = top_post_y + hp
        dy3h = f3_y_last - f3_y_first

        if flight3_treads > 0:
            if render_inner:
                dy3s = f3_y_last_fl - f3_y_first
                f3_y_end_c, f3_z_end_c = f3_y_last_fl, f3_z_last_fl
                if abs(dy3s) > 1e-9 and top_face_y > f3_y_last_fl:
                    t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3s))
                    f3_y_end_c = f3_y_first + t_c * dy3s
                    f3_z_end_c = f3_z_first + t_c * (f3_z_last_fl - f3_z_first)
                f3_y_hr_c, f3_z_hr_c = f3_y_last, f3_z_last
                if abs(dy3h) > 1e-9 and top_face_y > f3_y_last:
                    t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3h))
                    f3_y_hr_c = f3_y_first + t_c * dy3h
                    f3_z_hr_c = f3_z_first + t_c * (f3_z_last - f3_z_first)
                # Trim start at corner2 newel face
                c2_face_f3 = (corner2_y + c2_hp) if f3_y_first > corner2_y else (corner2_y - c2_hp)
                dy3_full = f3_y_last - f3_y_first
                if abs(dy3_full) > 1e-9:
                    t_c2f = (c2_face_f3 - f3_y_first) / dy3_full
                    f3_z_c2 = f3_z_first + t_c2f * (f3_z_last - f3_z_first)
                else:
                    f3_z_c2 = f3_z_first
                if abs(dy3s) > 1e-9:
                    t_c2fs = (c2_face_f3 - f3_y_first) / dy3s
                    f3_z_c2s = f3_z_first + t_c2fs * (f3_z_last_fl - f3_z_first)
                else:
                    f3_z_c2s = f3_z_first
                meshes.append(_stringer_flight_y(f3_inner_x, c2_face_f3, f3_z_c2s,
                                                 f3_y_end_c, f3_z_end_c))
                meshes.append(_handrail_flight_y(f3_inner_x, c2_face_f3, f3_z_c2,
                                                 f3_y_hr_c, f3_z_hr_c, **hr_kw))
                meshes.append(_baserail_flight_y(f3_inner_x, c2_face_f3, f3_z_c2s,
                                                 f3_y_end_c, f3_z_end_c, **br_kw))
                meshes.extend(_spindles_flight_y(f3_inner_x, c2_face_f3, f3_z_c2,
                                                 f3_y_hr_c, f3_z_hr_c, **sp_kw))
            else:
                meshes.append(_stringer_flight_y_notched(f3_inner_x, f3_y_first, f3_z_first,
                                                         f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))

        # Turn 2 winder outer stringer geometry
        if turn1_dir == "left":
            f2_x_end = -(flight2_treads * going) - winder_offset1 - nosing - riser_t / 2
        else:
            f2_x_end = width + flight2_treads * going + winder_offset1 + nosing + riser_t / 2
        f2_z_end = (flight2_riser_start + flight2_treads) * rise + nzs
        outer_corner_y2 = corner2_y + width
        wx_len = abs(f3_outer_x - f2_x_end)
        wy_len = abs(outer_corner_y2 - f3_y_first)
        total_path = wx_len + wy_len
        z_winder = f3_z_first - f2_z_end
        z_corner = f2_z_end + z_winder * wx_len / total_path if total_path > 1e-9 else f2_z_end

        if render_outer:
            # Winder X-piece with balustrade (from pitch-change newel at f2 end to outer corner)
            # Extend stringer past corner by STRINGER_THICKNESS/2 to fill gap
            st2 = STRINGER_THICKNESS / 2
            dx_w2 = f3_outer_x - f2_x_end
            x_ext2 = f3_outer_x + (-st2 if dx_w2 > 0 else st2) if abs(dx_w2) > 1e-9 else f3_outer_x
            z_x_ext2 = z_corner - st2 * (z_corner - f2_z_end) / abs(dx_w2) if abs(dx_w2) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y2, f2_x_end, f2_z_end, x_ext2, z_x_ext2))
            if turn1_dir == "left":
                pc_f2end_face_x = f2_x_end - hp  # -X face toward X-piece
                oc2_face_x = f3_outer_x + hp  # +X face of outer corner newel
            else:
                pc_f2end_face_x = f2_x_end + hp
                oc2_face_x = f3_outer_x - hp
            if abs(dx_w2) > 1e-9:
                t_pc2 = (pc_f2end_face_x - f2_x_end) / dx_w2
                z_pc2 = f2_z_end + t_pc2 * (z_corner - f2_z_end)
                t_oc2 = (oc2_face_x - f2_x_end) / dx_w2
                z_oc2 = f2_z_end + t_oc2 * (z_corner - f2_z_end)
            else:
                z_pc2, z_oc2 = f2_z_end, z_corner
            meshes.append(_handrail_flight_x(outer_corner_y2, pc_f2end_face_x, z_pc2, oc2_face_x, z_oc2, **hr_kw))
            meshes.append(_baserail_flight_x(outer_corner_y2, pc_f2end_face_x, z_pc2, oc2_face_x, z_oc2, **br_kw))
            meshes.extend(_spindles_flight_x(outer_corner_y2, pc_f2end_face_x, z_pc2, oc2_face_x, z_oc2, **sp_kw))
            # Winder Y-piece with balustrade (from outer corner to pitch-change newel at f3 start)
            # Extend stringer past corner by STRINGER_THICKNESS/2 to fill gap
            dy_w2 = f3_y_first - outer_corner_y2
            y_ext2 = outer_corner_y2 + st2
            z_y_ext2 = z_x_ext2  # match X-piece end height so top surfaces align at corner
            meshes.append(_stringer_flight_y(f3_outer_x, y_ext2, z_y_ext2, f3_y_first, f3_z_first))
            oc2_face_y = outer_corner_y2 - hp  # -Y face of outer corner newel
            pc_f3_face_y = f3_y_first + hp  # +Y face of pitch-change newel
            if abs(dy_w2) > 1e-9:
                t_pc3 = (pc_f3_face_y - outer_corner_y2) / dy_w2
                z_pc3 = z_corner + t_pc3 * (f3_z_first - z_corner)
            else:
                z_pc3 = f3_z_first
            meshes.append(_handrail_flight_y(f3_outer_x, oc2_face_y, z_corner, pc_f3_face_y, z_pc3, **hr_kw))
            meshes.append(_baserail_flight_y(f3_outer_x, oc2_face_y, z_corner, pc_f3_face_y, z_pc3, **br_kw))
            meshes.extend(_spindles_flight_y(f3_outer_x, oc2_face_y, z_corner, pc_f3_face_y, z_pc3, **sp_kw))
            if flight3_treads > 0:
                # Outer flight 3: from pitch-change newel face to top newel face
                pc_face_f3 = f3_y_first - hp
                top_face_y_out = top_post_y + hp
                f3_y0_oc, f3_z0_oc = f3_y_first, f3_z_first
                f3_y1_oc, f3_z1_oc = f3_y_last, f3_z_last
                if abs(dy3h) > 1e-9:
                    t_c0 = max(0.0, min(1.0, (pc_face_f3 - f3_y_first) / dy3h))
                    f3_y0_oc = f3_y_first + t_c0 * dy3h
                    f3_z0_oc = f3_z_first + t_c0 * (f3_z_last - f3_z_first)
                    t_c1 = max(0.0, min(1.0, (top_face_y_out - f3_y_first) / dy3h))
                    f3_y1_oc = f3_y_first + t_c1 * dy3h
                    f3_z1_oc = f3_z_first + t_c1 * (f3_z_last - f3_z_first)
                meshes.append(_stringer_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc))
                meshes.append(_handrail_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc, **hr_kw))
                meshes.append(_baserail_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc, **br_kw))
                meshes.extend(_spindles_flight_y(f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc, **sp_kw))
        else:
            # Extend winder corner stringers by STRINGER_THICKNESS/2 to fill gap
            st2 = STRINGER_THICKNESS / 2
            dx_w2 = f3_outer_x - f2_x_end
            x_ext2 = f3_outer_x + (-st2 if dx_w2 > 0 else st2) if abs(dx_w2) > 1e-9 else f3_outer_x
            z_x_ext2 = z_corner - st2 * (z_corner - f2_z_end) / abs(dx_w2) if abs(dx_w2) > 1e-9 else z_corner
            meshes.append(_stringer_flight_x(outer_corner_y2, f2_x_end, f2_z_end, x_ext2, z_x_ext2))
            dy_w2 = f3_y_first - outer_corner_y2
            y_ext2 = outer_corner_y2 + st2
            z_y_ext2 = z_x_ext2  # match X-piece end height so top surfaces align at corner
            if flight3_treads == 0:
                # Merge Y-piece with threshold notch into one stringer
                meshes.append(_stringer_flight_y_notched(f3_outer_x, y_ext2, z_y_ext2,
                                                         f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))
            else:
                meshes.append(_stringer_flight_y(f3_outer_x, y_ext2, z_y_ext2, f3_y_first, f3_z_first))
                meshes.append(_stringer_flight_y_notched(f3_outer_x, f3_y_first, f3_z_first,
                                                         f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))

    # --- Newel posts (top = 150mm above highest abutting handrail) ---
    NEWEL_CAP = 150.0
    hr_rise = p["handrail_rise"]
    nzs_hr = rise * nosing / going

    # Inner newel posts
    if render_inner:
        if flight1_treads > 0:
            hr_bot = rise + nzs_hr + hr_rise
            bot_h = hr_bot + NEWEL_CAP
            meshes.append(_box_mesh(corner1_x, bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355"))
        hr_c1_f1 = (flight1_treads + 1) * rise + nzs_hr + hr_rise
        hr_c1_f2 = flight2_riser_start * rise + nzs_hr + hr_rise
        c1_h = max(hr_c1_f1, hr_c1_f2) + NEWEL_CAP
        meshes.append(_box_mesh(corner1_x, landing1_y, c1_h / 2, c1_ns, c1_ns, c1_h, "#8B7355"))
        hr_c2_f2 = (flight2_riser_start + flight2_treads) * rise + nzs_hr + hr_rise
        hr_c2_f3 = flight3_riser_start * rise + nzs_hr + hr_rise
        c2_h = max(hr_c2_f2, hr_c2_f3) + NEWEL_CAP
        meshes.append(_box_mesh(corner2_x, corner2_y, c2_h / 2, c2_ns, c2_ns, c2_h, "#8B7355"))
        if flight3_treads > 0:
            # Top newel extends FROM cutting plane (150mm below stringer bottom) UPWARD
            pitch_line_top = (flight3_riser_start + flight3_treads) * rise + nzs_hr
            newel_bottom = pitch_line_top - 400.0
            newel_top = pitch_line_top + hr_rise + NEWEL_CAP
            top_h = newel_top - newel_bottom
            top_z_center = (newel_bottom + newel_top) / 2
            meshes.append(_box_mesh(corner2_x, top_post_y, top_z_center, ns, ns, top_h, "#8B7355"))
    else:
        # Wall condition on inner side: add stub newels at corners (no stringers)
        # Corner 1: 50mm below F1 stringer bottom, 50mm above F2 stringer top
        pitch_c1_f1 = (flight1_treads + 1) * rise + nzs_hr
        pitch_c1_f2 = flight2_riser_start * rise + nzs_hr
        f1_stringer_bottom_c1 = pitch_c1_f1 - (STRINGER_HEIGHT - STRINGER_PITCH_OFFSET)
        f2_stringer_top_c1    = pitch_c1_f2 + STRINGER_PITCH_OFFSET
        stub_bottom_c1 = f1_stringer_bottom_c1 - 50.0
        stub_top_c1    = f2_stringer_top_c1    + 50.0
        stub_h_c1 = stub_top_c1 - stub_bottom_c1
        stub_z_center_c1 = (stub_top_c1 + stub_bottom_c1) / 2
        meshes.append(_box_mesh(corner1_x, landing1_y, stub_z_center_c1, ns, ns, stub_h_c1, "#8B7355"))
        # Corner 2: 50mm below F2 stringer bottom, 50mm above F3 stringer top
        pitch_c2_f2 = (flight2_riser_start + flight2_treads) * rise + nzs_hr
        pitch_c2_f3 = flight3_riser_start * rise + nzs_hr
        f2_stringer_bottom_c2 = pitch_c2_f2 - (STRINGER_HEIGHT - STRINGER_PITCH_OFFSET)
        f3_stringer_top_c2    = pitch_c2_f3 + STRINGER_PITCH_OFFSET
        stub_bottom_c2 = f2_stringer_bottom_c2 - 50.0
        stub_top_c2    = f3_stringer_top_c2    + 50.0
        stub_h_c2 = stub_top_c2 - stub_bottom_c2
        stub_z_center_c2 = (stub_top_c2 + stub_bottom_c2) / 2
        meshes.append(_box_mesh(corner2_x, corner2_y, stub_z_center_c2, ns, ns, stub_h_c2, "#8B7355"))
        # Note: Stub stringers removed - they were causing green artifacts

    # Outer newel posts
    if render_outer:
        nzs_w = rise * nosing / going
        outer_x = width - corner1_x
        outer_y_pos = landing1_y + width
        if turn1_dir == turn2_dir:
            f3_outer_x_val = flight3_start_x + corner1_x
        else:
            f3_outer_x_val = flight3_start_x + width - corner1_x
        if turn1_dir == "left":
            f2_x0_val = -winder_offset1 - nosing - riser_t / 2
            f2_x_end_val = -(flight2_treads * going) - winder_offset1 - nosing - riser_t / 2
        else:
            f2_x0_val = width + winder_offset1 + nosing + riser_t / 2
            f2_x_end_val = width + flight2_treads * going + winder_offset1 + nosing + riser_t / 2
        f1_y1_val = flight1_treads * going + flight1_shift_y
        f3_y_first_val = flight3_start_y - nosing + riser_t / 2 + flight3_shift_y

        # Bottom newel
        if flight1_treads > 0:
            hr_bot = rise + nzs_w + hr_rise
            bot_h = hr_bot + NEWEL_CAP
            meshes.append(_box_mesh(outer_x, bottom_post_y, bot_h / 2, ns, ns, bot_h, "#8B7355"))

        # Turn 1 pitch-change at flight 1 end
        hr_pc1 = (flight1_treads + 1) * rise + nzs_w + hr_rise
        pc1_h = hr_pc1 + NEWEL_CAP
        meshes.append(_box_mesh(outer_x, f1_y1_val, pc1_h / 2, ns, ns, pc1_h, "#8B7355"))

        if actual_winders1 > 0:
            # Outer corner 1 - match stub newel pattern (no hr_rise, just pitch line)
            oc1_pitch = max((flight1_treads + 1) * rise + nzs_w,
                           flight2_riser_start * rise + nzs_w)
            oc1_h = oc1_pitch + STRINGER_PITCH_OFFSET + hr_rise + NEWEL_CAP - 350.0
            meshes.append(_box_mesh(outer_x, outer_y_pos, oc1_h / 2, ns, ns, oc1_h, "#8B7355"))
            # Pitch-change at flight 2 start
            hr_pc_f2s = flight2_riser_start * rise + nzs_w + hr_rise
            pc_f2s_h = hr_pc_f2s + NEWEL_CAP
            meshes.append(_box_mesh(f2_x0_val, outer_y_pos, pc_f2s_h / 2, ns, ns, pc_f2s_h, "#8B7355"))
        else:
            # Flat landing at turn 1 - match height of pitch-change newel (pc1)
            oc1_h = pc1_h  # Same height as pitch-change newel at flight 1 end
            meshes.append(_box_mesh(outer_x, outer_y_pos, oc1_h / 2, ns, ns, oc1_h, "#8B7355"))
            hr_pc_f2s = flight2_riser_start * rise + nzs_w + hr_rise
            pc_f2s_h = hr_pc_f2s + NEWEL_CAP
            meshes.append(_box_mesh(f2_x0_val, outer_y_pos, pc_f2s_h / 2, ns, ns, pc_f2s_h, "#8B7355"))

        if actual_winders2 > 0:
            # Pitch-change at flight 2 end
            hr_pc_f2e = (flight2_riser_start + flight2_treads) * rise + nzs_w + hr_rise
            pc_f2e_h = hr_pc_f2e + NEWEL_CAP
            outer_corner_y2_val = corner2_y + width
            meshes.append(_box_mesh(f2_x_end_val, outer_corner_y2_val, pc_f2e_h / 2, ns, ns, pc_f2e_h, "#8B7355"))
            # Outer corner 2 - match stub newel pattern
            oc2_pitch = max((flight2_riser_start + flight2_treads) * rise + nzs_w,
                           flight3_riser_start * rise + nzs_w)
            oc2_h = oc2_pitch + STRINGER_PITCH_OFFSET + hr_rise + NEWEL_CAP - 350.0
            meshes.append(_box_mesh(f3_outer_x_val, outer_corner_y2_val, oc2_h / 2, ns, ns, oc2_h, "#8B7355"))
            # Pitch-change at flight 3 start
            hr_pc_f3s = flight3_riser_start * rise + nzs_w + hr_rise
            pc_f3s_h = hr_pc_f3s + NEWEL_CAP
            meshes.append(_box_mesh(f3_outer_x_val, f3_y_first_val, pc_f3s_h / 2, ns, ns, pc_f3s_h, "#8B7355"))
        else:
            # Flat landing at turn 2 - match height of pitch-change newel (pc_t2a)
            outer_corner_y2_val = corner2_y + width
            hr_pc_t2a = (flight2_riser_start + flight2_treads) * rise + nzs_w + hr_rise
            pc_t2a_h = hr_pc_t2a + NEWEL_CAP
            meshes.append(_box_mesh(f2_x_end_val, outer_corner_y2_val, pc_t2a_h / 2, ns, ns, pc_t2a_h, "#8B7355"))
            # Outer corner 2 - same height as pitch-change newel at flight 2 end
            oc2_h = pc_t2a_h  # Match height of pc_t2a
            meshes.append(_box_mesh(f3_outer_x_val, outer_corner_y2_val, oc2_h / 2, ns, ns, oc2_h, "#8B7355"))
            # Pitch-change at flight 3 start
            hr_pc_t2b = flight3_riser_start * rise + nzs_w + hr_rise
            pc_t2b_h = hr_pc_t2b + NEWEL_CAP
            meshes.append(_box_mesh(f3_outer_x_val, f3_y_first_val, pc_t2b_h / 2, ns, ns, pc_t2b_h, "#8B7355"))

        # Top newel - extends FROM cutting plane (150mm below stringer bottom) UPWARD
        if flight3_treads > 0:
            pitch_line_top = (flight3_riser_start + flight3_treads) * rise + nzs_w
            newel_bottom = pitch_line_top - 400.0
            newel_top = pitch_line_top + hr_rise + NEWEL_CAP
            top_h = newel_top - newel_bottom
            top_z_center = (newel_bottom + newel_top) / 2
            meshes.append(_box_mesh(f3_outer_x_val, top_post_y, top_z_center, ns, ns, top_h, "#8B7355"))

    return meshes




