"""
Stair Preview Engine — balustrade primitive helpers.

All stringer/handrail/baserail/spindle building blocks used by the flight
builders.  These helpers return mesh dicts; they do not append to any list.
"""

import math

from stair_constants import (
    STRINGER_THICKNESS, STRINGER_HEIGHT, STRINGER_PITCH_OFFSET, STRINGER_DROP,
    WALL_STRINGER_EXTENSION, STRINGER_COLOR,
    HANDRAIL_WIDTH, HANDRAIL_HEIGHT, HANDRAIL_RISE, HANDRAIL_COLOR,
    SPINDLE_SIZE, SPINDLE_MAX_GAP,
)


def _stringer_flight_y(x_pos, y_start, z_start, y_end, z_end, name="Stringer", ifc_type="stringer", clip_z_min=None):
    """Stringer along a flight that runs in the Y direction.

    Returns a stringer mesh dict.  The profile is a parallelogram in the
    Y-Z plane, extruded by STRINGER_THICKNESS in X centred on *x_pos*.

    If *clip_z_min* is set the profile is clipped so nothing extends below
    that Z value (e.g. ground-floor level = 0).
    """
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off
    pts = [
        [y_start, z_start - drop],
        [y_end,   z_end - drop],
        [y_end,   z_end + off],
        [y_start, z_start + off],
    ]
    if clip_z_min is not None:
        clipped = []
        n = len(pts)
        for i in range(n):
            curr = pts[i]
            nxt = pts[(i + 1) % n]
            c_in = curr[1] >= clip_z_min
            n_in = nxt[1] >= clip_z_min
            if c_in:
                clipped.append(curr)
            if c_in != n_in:
                dy = nxt[0] - curr[0]
                dz = nxt[1] - curr[1]
                if abs(dz) > 1e-9:
                    t = (clip_z_min - curr[1]) / dz
                    clipped.append([curr[0] + t * dy, clip_z_min])
        if clipped:
            pts = clipped
    profile = pts
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }


def _stringer_flight_x(y_pos, x_start, z_start, x_end, z_end, name="Stringer", ifc_type="stringer"):
    """Stringer along a flight that runs in the X direction.

    Profile is in the X-Z plane, extruded by STRINGER_THICKNESS in Y
    centred on *y_pos*.
    """
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off
    profile = [
        [x_start, z_start - drop],
        [x_end,   z_end - drop],
        [x_end,   z_end + off],
        [x_start, z_start + off],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }


def _stringer_landing_y(x_pos, y_start, y_end, z, name="Landing Stringer", ifc_type="stringer"):
    """Flat (horizontal) stringer across a landing, running in Y.

    The stringer top sits at base rail bottom (to support it properly).
    """
    z_top = z + STRINGER_DROP + STRINGER_PITCH_OFFSET
    z_bot = z_top - STRINGER_HEIGHT
    profile = [
        [y_start, z_bot],
        [y_end,   z_bot],
        [y_end,   z_top],
        [y_start, z_top],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }


def _stringer_landing_x(y_pos, x_start, x_end, z, name="Landing Stringer", ifc_type="stringer"):
    """Flat (horizontal) stringer across a landing, running in X.

    The stringer top sits at base rail bottom (to support it properly).
    """
    z_top = z + STRINGER_DROP + STRINGER_PITCH_OFFSET
    z_bot = z_top - STRINGER_HEIGHT
    profile = [
        [x_start, z_bot],
        [x_end,   z_bot],
        [x_end,   z_top],
        [x_start, z_top],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }


def _handrail_flight_y(x_pos, y_start, z_start, y_end, z_end, name="Handrail", **kw):
    """Pitched handrail along Y.  z_start/z_end are nosing pitch-line z values."""
    w = kw.get("hr_width", HANDRAIL_WIDTH)
    h = kw.get("hr_height", HANDRAIL_HEIGHT)
    r = kw.get("hr_rise", HANDRAIL_RISE)
    profile = [
        [y_start, z_start + r - h],
        [y_end,   z_end + r - h],
        [y_end,   z_end + r],
        [y_start, z_start + r],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "handrail",
    }


def _handrail_flight_x(y_pos, x_start, z_start, x_end, z_end, name="Handrail", **kw):
    """Pitched handrail along X.  z_start/z_end are nosing pitch-line z values."""
    w = kw.get("hr_width", HANDRAIL_WIDTH)
    h = kw.get("hr_height", HANDRAIL_HEIGHT)
    r = kw.get("hr_rise", HANDRAIL_RISE)
    profile = [
        [x_start, z_start + r - h],
        [x_end,   z_end + r - h],
        [x_end,   z_end + r],
        [x_start, z_start + r],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "handrail",
    }


def _baserail_flight_y(x_pos, y_start, z_start, y_end, z_end, name="Baserail", **kw):
    """Base rail along Y sitting on top of the inner stringer."""
    w = kw.get("br_width", HANDRAIL_WIDTH)
    h = kw.get("br_height", HANDRAIL_HEIGHT)
    bot = STRINGER_PITCH_OFFSET
    top = STRINGER_PITCH_OFFSET + h
    profile = [
        [y_start, z_start + bot],
        [y_end,   z_end + bot],
        [y_end,   z_end + top],
        [y_start, z_start + top],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "baserail",
    }


def _baserail_flight_x(y_pos, x_start, z_start, x_end, z_end, name="Baserail", **kw):
    """Base rail along X sitting on top of the inner stringer."""
    w = kw.get("br_width", HANDRAIL_WIDTH)
    h = kw.get("br_height", HANDRAIL_HEIGHT)
    bot = STRINGER_PITCH_OFFSET
    top = STRINGER_PITCH_OFFSET + h
    profile = [
        [x_start, z_start + bot],
        [x_end,   z_end + bot],
        [x_end,   z_end + top],
        [x_start, z_start + top],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "baserail",
    }


def _handrail_landing_y(x_pos, y_start, y_end, z, name="Landing Handrail", **kw):
    """Flat (horizontal) handrail across a landing, running in Y.

    z is the landing tread plane height.
    Handrail sits at landing_stringer_top + handrail_rise.
    """
    w = kw.get("hr_width", HANDRAIL_WIDTH)
    h = kw.get("hr_height", HANDRAIL_HEIGHT)
    r = kw.get("hr_rise", HANDRAIL_RISE)
    # Landing stringer top is at z + STRINGER_DROP
    z_hr_bot = z + STRINGER_DROP + r - h
    z_hr_top = z + STRINGER_DROP + r
    profile = [
        [y_start, z_hr_bot],
        [y_end, z_hr_bot],
        [y_end, z_hr_top],
        [y_start, z_hr_top],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "handrail",
    }


def _handrail_landing_x(y_pos, x_start, x_end, z, name="Landing Handrail", **kw):
    """Flat (horizontal) handrail across a landing, running in X.

    z is the landing tread plane height.
    Handrail sits at landing_stringer_top + handrail_rise.
    """
    w = kw.get("hr_width", HANDRAIL_WIDTH)
    h = kw.get("hr_height", HANDRAIL_HEIGHT)
    r = kw.get("hr_rise", HANDRAIL_RISE)
    # Landing stringer top is at z + STRINGER_DROP
    z_hr_bot = z + STRINGER_DROP + r - h
    z_hr_top = z + STRINGER_DROP + r
    profile = [
        [x_start, z_hr_bot],
        [x_end, z_hr_bot],
        [x_end, z_hr_top],
        [x_start, z_hr_top],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "handrail",
    }


def _baserail_landing_y(x_pos, y_start, y_end, z, name="Landing Baserail", **kw):
    """Flat (horizontal) baserail across a landing, running in Y."""
    w = kw.get("br_width", HANDRAIL_WIDTH)
    h = kw.get("br_height", HANDRAIL_HEIGHT)
    z_top = z + STRINGER_DROP
    bot = STRINGER_PITCH_OFFSET
    top = STRINGER_PITCH_OFFSET + h
    profile = [
        [y_start, z_top + bot],
        [y_end, z_top + bot],
        [y_end, z_top + top],
        [y_start, z_top + top],
    ]
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "baserail",
    }


def _baserail_landing_x(y_pos, x_start, x_end, z, name="Landing Baserail", **kw):
    """Flat (horizontal) baserail across a landing, running in X."""
    w = kw.get("br_width", HANDRAIL_WIDTH)
    h = kw.get("br_height", HANDRAIL_HEIGHT)
    z_top = z + STRINGER_DROP
    bot = STRINGER_PITCH_OFFSET
    top = STRINGER_PITCH_OFFSET + h
    profile = [
        [x_start, z_top + bot],
        [x_end, z_top + bot],
        [x_end, z_top + top],
        [x_start, z_top + top],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - w / 2,
        "thickness": w,
        "color": HANDRAIL_COLOR,
        "name": name,
        "ifc_type": "baserail",
    }


def _spindles_flight_y(x_pos, y_start, z_start, y_end, z_end, name_prefix="Spindle", **kw):
    """Spindles along a Y-direction flight with pitched top/bottom surfaces.

    Gaps between spindles (and between spindles and newel post faces at each
    end) are all equal and as close to 99 mm as possible without exceeding it.
    Each spindle is a parallelogram in the Y-Z plane (sloped to match pitch),
    extruded by spindle_size in X.
    """
    meshes = []
    sp = kw.get("spindle_size", SPINDLE_SIZE)
    br_h = kw.get("br_height", HANDRAIL_HEIGHT)
    hr_h = kw.get("hr_height", HANDRAIL_HEIGHT)
    hr_r = kw.get("hr_rise", HANDRAIL_RISE)
    br_top_off = STRINGER_PITCH_OFFSET + br_h
    hr_bot_off = hr_r - hr_h
    dy = y_end - y_start
    length = abs(dy)
    if length < 1e-9:
        return meshes
    # k spindles produce k+1 equal gaps: gap = (L - k*sp) / (k+1)
    # We need gap <= 99, so k >= ceil((L - 99) / (99 + sp))
    k = max(0, math.ceil((length - SPINDLE_MAX_GAP) / (SPINDLE_MAX_GAP + sp)))
    if k == 0:
        return meshes
    gap = (length - k * sp) / (k + 1)
    first_centre = gap + sp / 2
    centre_step = gap + sp
    slope = (z_end - z_start) / dy  # dz/dy — pitch slope
    dz_half = slope * sp / 2
    for i in range(k):
        pos = first_centre + i * centre_step
        t = pos / length
        y = y_start + t * dy
        z = z_start + t * (z_end - z_start)
        z_bot = z + br_top_off
        z_top = z + hr_bot_off
        if z_top - z_bot > sp:
            meshes.append({
                "type": "stringer",
                "profile": [
                    [y - sp / 2, z_bot - dz_half],
                    [y + sp / 2, z_bot + dz_half],
                    [y + sp / 2, z_top + dz_half],
                    [y - sp / 2, z_top - dz_half],
                ],
                "x": x_pos - sp / 2,
                "thickness": sp,
                "color": HANDRAIL_COLOR,
                "name": f"{name_prefix} {i+1}",
                "ifc_type": "spindle",
            })
    return meshes


def _spindles_flight_x(y_pos, x_start, z_start, x_end, z_end, name_prefix="Spindle", **kw):
    """Spindles along an X-direction flight with pitched top/bottom surfaces."""
    meshes = []
    sp = kw.get("spindle_size", SPINDLE_SIZE)
    br_h = kw.get("br_height", HANDRAIL_HEIGHT)
    hr_h = kw.get("hr_height", HANDRAIL_HEIGHT)
    hr_r = kw.get("hr_rise", HANDRAIL_RISE)
    br_top_off = STRINGER_PITCH_OFFSET + br_h
    hr_bot_off = hr_r - hr_h
    dx = x_end - x_start
    length = abs(dx)
    if length < 1e-9:
        return meshes
    k = max(0, math.ceil((length - SPINDLE_MAX_GAP) / (SPINDLE_MAX_GAP + sp)))
    if k == 0:
        return meshes
    gap = (length - k * sp) / (k + 1)
    first_centre = gap + sp / 2
    centre_step = gap + sp
    slope = (z_end - z_start) / dx  # dz/dx — pitch slope
    dz_half = slope * sp / 2
    for i in range(k):
        pos = first_centre + i * centre_step
        t = pos / length
        x = x_start + t * dx
        z = z_start + t * (z_end - z_start)
        z_bot = z + br_top_off
        z_top = z + hr_bot_off
        if z_top - z_bot > sp:
            meshes.append({
                "type": "stringer",
                "profile": [
                    [x - sp / 2, z_bot - dz_half],
                    [x + sp / 2, z_bot + dz_half],
                    [x + sp / 2, z_top + dz_half],
                    [x - sp / 2, z_top - dz_half],
                ],
                "y": y_pos - sp / 2,
                "thickness": sp,
                "axis": "y",
                "color": HANDRAIL_COLOR,
                "name": f"{name_prefix} {i+1}",
                "ifc_type": "spindle",
            })
    return meshes


def _spindles_landing_y(x_pos, y_start, y_end, z, name_prefix="Landing Spindle", **kw):
    """Vertical spindles along a Y-direction landing (flat/horizontal).

    Spindles run from base rail top to handrail bottom.
    z is the landing tread plane height.
    """
    meshes = []
    sp = kw.get("spindle_size", SPINDLE_SIZE)
    br_h = kw.get("br_height", HANDRAIL_HEIGHT)
    hr_h = kw.get("hr_height", HANDRAIL_HEIGHT)
    hr_r = kw.get("hr_rise", HANDRAIL_RISE)

    # Baserail and handrail use z + STRINGER_DROP as reference
    z_ref = z + STRINGER_DROP
    # Spindle bottom overlaps baserail top by 1mm to ensure proper connection
    z_bot = z_ref + STRINGER_PITCH_OFFSET + br_h - 1.0  # base rail top with 1mm overlap
    z_top = z_ref + hr_r - hr_h  # handrail bottom

    dy = y_end - y_start
    length = abs(dy)
    if length < 1e-9 or z_top - z_bot < sp:
        return meshes

    # Calculate number of spindles to keep gaps <= 99mm
    k = max(0, math.ceil((length - SPINDLE_MAX_GAP) / (SPINDLE_MAX_GAP + sp)))
    if k == 0:
        return meshes

    gap = (length - k * sp) / (k + 1)
    first_centre = gap + sp / 2
    centre_step = gap + sp

    for i in range(k):
        pos = first_centre + i * centre_step
        if dy >= 0:
            y = y_start + pos
        else:
            y = y_start - pos

        meshes.append({
            "type": "stringer",
            "profile": [
                [y - sp / 2, z_bot],
                [y + sp / 2, z_bot],
                [y + sp / 2, z_top],
                [y - sp / 2, z_top],
            ],
            "x": x_pos - sp / 2,
            "thickness": sp,
            "color": HANDRAIL_COLOR,
            "name": f"{name_prefix} {i+1}",
            "ifc_type": "spindle",
        })
    return meshes


def _spindles_landing_x(y_pos, x_start, x_end, z, name_prefix="Landing Spindle", **kw):
    """Vertical spindles along an X-direction landing (flat/horizontal).

    Spindles run from base rail top to handrail bottom.
    z is the landing tread plane height.
    """
    meshes = []
    sp = kw.get("spindle_size", SPINDLE_SIZE)
    br_h = kw.get("br_height", HANDRAIL_HEIGHT)
    hr_h = kw.get("hr_height", HANDRAIL_HEIGHT)
    hr_r = kw.get("hr_rise", HANDRAIL_RISE)

    # Baserail and handrail use z + STRINGER_DROP as reference
    z_ref = z + STRINGER_DROP
    # Spindle bottom overlaps baserail top by 1mm to ensure proper connection
    z_bot = z_ref + STRINGER_PITCH_OFFSET + br_h - 1.0  # base rail top with 1mm overlap
    z_top = z_ref + hr_r - hr_h  # handrail bottom

    dx = x_end - x_start
    length = abs(dx)
    if length < 1e-9 or z_top - z_bot < sp:
        return meshes

    # Calculate number of spindles to keep gaps <= 99mm
    k = max(0, math.ceil((length - SPINDLE_MAX_GAP) / (SPINDLE_MAX_GAP + sp)))
    if k == 0:
        return meshes

    gap = (length - k * sp) / (k + 1)
    first_centre = gap + sp / 2
    centre_step = gap + sp

    for i in range(k):
        pos = first_centre + i * centre_step
        if dx >= 0:
            x = x_start + pos
        else:
            x = x_start - pos

        meshes.append({
            "type": "stringer",
            "axis": "y",
            "profile": [
                [x - sp / 2, z_bot],
                [x + sp / 2, z_bot],
                [x + sp / 2, z_top],
                [x - sp / 2, z_top],
            ],
            "y": y_pos - sp / 2,
            "thickness": sp,
            "color": HANDRAIL_COLOR,
            "name": f"{name_prefix} {i+1}",
            "ifc_type": "spindle",
        })
    return meshes


def _stringer_flight_y_notched(x_pos, y_start, z_start, y_end, z_end, ftf, y_back, tread_t,
                               name="Stringer", ifc_type="stringer", clip_z_min=None):
    """Pitched stringer along Y with a notch at the top for landing threshold.

    The stringer bottom continues at pitch to y_end (riser back face), then a
    vertical cut rises to ftf - tread_t (threshold underside).  The overrun
    extends to y_back with its top flush with the pitched stringer surface.

    If *clip_z_min* is set the profile is clipped so nothing extends below
    that Z value (e.g. ground-floor level = 0).
    """
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off
    overrun_bot = ftf - tread_t
    # Extend pitch line to y_back so overrun top is flush with stringer surface
    dy = y_end - y_start
    slope = (z_end - z_start) / dy if dy != 0 else 0
    z_back_top = z_end + off + slope * (y_back - y_end)
    profile = [
        [y_start, z_start - drop],      # 0  bottom at start
        [y_end,   z_end - drop],         # 1  bottom at riser back
        [y_end,   overrun_bot],          # 2  vertical cut to threshold underside
        [y_back,  overrun_bot],          # 3  horizontal to threshold back
        [y_back,  z_back_top],           # 4  up to pitch line at threshold back
        [y_start, z_start + off],        # 5  pitch line back to start
    ]
    if clip_z_min is not None:
        clipped = []
        n = len(profile)
        for i in range(n):
            curr = profile[i]
            nxt = profile[(i + 1) % n]
            c_in = curr[1] >= clip_z_min
            n_in = nxt[1] >= clip_z_min
            if c_in:
                clipped.append(curr)
            if c_in != n_in:
                _dy = nxt[0] - curr[0]
                _dz = nxt[1] - curr[1]
                if abs(_dz) > 1e-9:
                    t = (clip_z_min - curr[1]) / _dz
                    clipped.append([curr[0] + t * _dy, clip_z_min])
        if clipped:
            profile = clipped
    return {
        "type": "stringer",
        "profile": profile,
        "x": x_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }


def _stringer_flight_x_notched(y_pos, x_start, z_start, x_end, z_end, ftf, x_back, tread_t,
                               name="Stringer", ifc_type="stringer"):
    """Pitched stringer along X with a notch at the top for landing threshold."""
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off
    overrun_bot = ftf - tread_t
    dx = x_end - x_start
    slope = (z_end - z_start) / dx if dx != 0 else 0
    z_back_top = z_end + off + slope * (x_back - x_end)
    profile = [
        [x_start, z_start - drop],
        [x_end,   z_end - drop],
        [x_end,   overrun_bot],
        [x_back,  overrun_bot],
        [x_back,  z_back_top],
        [x_start, z_start + off],
    ]
    return {
        "type": "stringer",
        "axis": "y",
        "profile": profile,
        "y": y_pos - STRINGER_THICKNESS / 2,
        "thickness": STRINGER_THICKNESS,
        "color": STRINGER_COLOR,
        "name": name,
        "ifc_type": ifc_type,
    }
