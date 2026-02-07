"""
IFC Staircase Generator

Generates valid IFC 2x3 files for straight, single-winder (L-shaped),
and double-winder (U-shaped) staircases using IfcOpenShell.
"""

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import ifcopenshell.guid
import math
import time
import tempfile
import os


def create_ifc_staircase(params):
    """
    Main entry point. Takes a parameter dict and returns the path to a generated .ifc file.

    Parameters:
        params: dict with keys matching the input specification
    Returns:
        str: path to the generated .ifc file
    """
    ifc = ifcopenshell.api.run("project.create_file", version="IFC2X3")

    # Set up owner history (required by IfcOpenShell)
    person = ifcopenshell.api.run("owner.add_person", ifc, family_name="User")
    org = ifcopenshell.api.run("owner.add_organisation", ifc, identification="IFC-STAIR", name="IFC Staircase Generator")
    ifcopenshell.api.run("owner.add_person_and_organisation", ifc, person=person, organisation=org)
    app = ifcopenshell.api.run("owner.add_application", ifc, application_developer=org,
                               version="1.0", application_full_name="IFC Staircase Generator",
                               application_identifier="ifc-stair-gen")
    ifcopenshell.api.owner.settings.get_user = lambda f: f.by_type("IfcPersonAndOrganization")[0]
    ifcopenshell.api.owner.settings.get_application = lambda f: f.by_type("IfcApplication")[0]

    # Set up units (millimetres)
    project = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Staircase Project")
    ifcopenshell.api.run("unit.assign_unit", ifc, length={"is_metric": True, "raw": "MILLIMETERS"})

    # Create context for geometry
    ctx = ifcopenshell.api.run("context.add_context", ifc, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context", ifc,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx,
    )

    # Spatial hierarchy: Project -> Site -> Building -> Storey
    site = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSite", name="Default Site")
    building = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuilding", name="Default Building")
    storey = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Ground Floor")

    ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=building, products=[storey])

    # Parse parameters
    p = parse_params(params)

    # Create stair container
    stair = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcStair", name="Staircase")
    ifcopenshell.api.run("spatial.assign_container", ifc, relating_structure=storey, products=[stair])

    stair_type = p["staircase_type"]
    elements = []

    if stair_type == "straight":
        elements = generate_straight_flight(ifc, body, p)
    elif stair_type == "single_winder":
        elements = generate_single_winder(ifc, body, p)
    elif stair_type == "double_winder":
        elements = generate_double_winder(ifc, body, p)

    # Aggregate elements under the stair
    if elements:
        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=stair, products=elements)

    # Write to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".ifc", delete=False)
    ifc.write(tmp.name)
    return tmp.name


def parse_params(params):
    """Parse and validate input parameters, computing derived values."""
    p = {}
    p["floor_to_floor"] = float(params.get("floor_to_floor", 2600))
    p["stair_width"] = float(params.get("stair_width", 810))
    p["num_risers"] = int(params.get("num_risers", 13))
    p["going"] = float(params.get("going", 227))
    p["tread_thickness"] = float(params.get("tread_thickness", 22))
    p["riser_thickness"] = float(params.get("riser_thickness", 9))
    p["nosing"] = float(params.get("nosing", 16))
    p["staircase_type"] = params.get("staircase_type", "double_winder")
    p["turn1_direction"] = params.get("turn1_direction", "left")
    p["turn1_winders"] = int(params.get("turn1_winders", 3))
    p["turn2_direction"] = params.get("turn2_direction", "left")
    p["turn2_winders"] = int(params.get("turn2_winders", 3))
    p["turn1_enabled"] = bool(params.get("turn1_enabled", True))
    p["turn2_enabled"] = bool(params.get("turn2_enabled", True))
    p["newel_size"] = float(params.get("newel_size", 80))

    # Derived
    p["rise"] = p["floor_to_floor"] / p["num_risers"]
    p["num_treads"] = p["num_risers"] - 1  # one fewer tread than risers

    return p


def _create_extruded_solid(ifc, context, profile_coords, extrusion_depth, position_xyz, direction=(0.0, 0.0, 1.0)):
    """
    Create an IfcExtrudedAreaSolid from a list of 2D profile coordinates,
    extruded along a direction.
    """
    # Create cartesian points for the profile
    points = [ifc.createIfcCartesianPoint(coord) for coord in profile_coords]
    points.append(points[0])  # close the loop

    polyline = ifc.createIfcPolyline(points)
    profile = ifc.createIfcArbitraryClosedProfileDef("AREA", None, polyline)

    # Position of the extrusion
    location = ifc.createIfcCartesianPoint(position_xyz)
    axis2 = ifc.createIfcAxis2Placement3D(location, None, None)

    direction_ifc = ifc.createIfcDirection(direction)

    solid = ifc.createIfcExtrudedAreaSolid(profile, axis2, direction_ifc, extrusion_depth)

    return solid


def _create_element_with_geometry(ifc, context, ifc_class, name, solid, placement_xyz=(0.0, 0.0, 0.0),
                                   rotation=None):
    """Create an IFC element with geometry representation and local placement."""
    element = ifcopenshell.api.run("root.create_entity", ifc, ifc_class=ifc_class, name=name)

    # Create shape representation
    rep = ifc.createIfcShapeRepresentation(context, "Body", "SweptSolid", [solid])
    prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
    element.Representation = prod_rep

    # Create local placement
    origin = ifc.createIfcCartesianPoint(placement_xyz)
    if rotation is not None:
        axis = ifc.createIfcDirection((0.0, 0.0, 1.0))
        ref_dir = ifc.createIfcDirection((math.cos(rotation), math.sin(rotation), 0.0))
        placement = ifc.createIfcAxis2Placement3D(origin, axis, ref_dir)
    else:
        placement = ifc.createIfcAxis2Placement3D(origin, None, None)

    local_placement = ifc.createIfcLocalPlacement(None, placement)
    element.ObjectPlacement = local_placement

    return element


def _add_pset_stair_flight(ifc, flight, num_risers, num_treads, rise, going):
    """Add Pset_StairFlightCommon property set to a stair flight."""
    pset = ifcopenshell.api.run("pset.add_pset", ifc, product=flight, name="Pset_StairFlightCommon")
    ifcopenshell.api.run("pset.edit_pset", ifc, pset=pset, properties={
        "NumberOfRiser": num_risers,
        "NumberOfTreads": num_treads,
        "RiserHeight": rise,
        "TreadLength": going,
    })


# ────────────────────────────────────────────────────────────
# STRAIGHT FLIGHT
# ────────────────────────────────────────────────────────────

def generate_straight_flight(ifc, context, p):
    """Generate a straight flight staircase."""
    elements = []
    width = p["stair_width"]
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    num_risers = p["num_risers"]

    # Create a single stair flight element with all treads
    flight = _create_stair_flight_element(
        ifc, context, "Flight 1",
        num_treads=num_treads,
        width=width,
        going=going,
        rise=rise,
        tread_thickness=tread_t,
        riser_thickness=riser_t,
        nosing=nosing,
        start_xyz=(0.0, 0.0, 0.0),
        rotation=None,
    )
    _add_pset_stair_flight(ifc, flight, num_risers, num_treads, rise, going)
    elements.append(flight)

    # Individual risers
    for i in range(num_risers):
        riser_z = i * rise
        riser_y = i * going
        riser = _create_riser(ifc, context, f"Riser {i+1}", width, rise, riser_t, tread_t,
                              position=(0.0, riser_y, riser_z))
        elements.append(riser)

    return elements


def _create_stair_flight_element(ifc, context, name, num_treads, width, going, rise,
                                  tread_thickness, riser_thickness, nosing,
                                  start_xyz, rotation):
    """Create a stair flight as a series of treads combined into one element."""
    # We'll model each tread as part of the flight geometry
    # Profile for a single tread (in XY plane): rectangle with nosing
    # Tread extends backward by riser_thickness so the riser above sits on top
    solids = []

    for i in range(num_treads):
        tread_y = i * going - nosing
        tread_z = (i + 1) * rise - tread_thickness
        tread_length = going + nosing + riser_thickness

        profile = [
            (0.0, 0.0),
            (width, 0.0),
            (width, tread_length),
            (0.0, tread_length),
        ]

        solid = _create_extruded_solid(
            ifc, context, profile, tread_thickness,
            (start_xyz[0], start_xyz[1] + tread_y, start_xyz[2] + tread_z),
        )
        solids.append(solid)

    # Create element with first solid, add rest via mapped items
    if not solids:
        return None

    element = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcStairFlight", name=name)

    rep = ifc.createIfcShapeRepresentation(context, "Body", "SweptSolid", solids)
    prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
    element.Representation = prod_rep

    origin = ifc.createIfcCartesianPoint(start_xyz)
    if rotation is not None:
        axis = ifc.createIfcDirection((0.0, 0.0, 1.0))
        ref_dir = ifc.createIfcDirection((math.cos(rotation), math.sin(rotation), 0.0))
        placement = ifc.createIfcAxis2Placement3D(origin, axis, ref_dir)
    else:
        placement = ifc.createIfcAxis2Placement3D(origin, None, None)
    local_placement = ifc.createIfcLocalPlacement(None, placement)
    element.ObjectPlacement = local_placement

    return element


def _create_riser(ifc, context, name, width, rise, riser_thickness, tread_thickness, position):
    """Create a riser as an IfcPlate. Height is rise minus tread thickness so the
    riser meets the underside of the tread above."""
    if riser_thickness <= 0:
        return None

    riser_height = rise - tread_thickness

    profile = [
        (0.0, 0.0),
        (width, 0.0),
        (width, riser_thickness),
        (0.0, riser_thickness),
    ]

    solid = _create_extruded_solid(ifc, context, profile, riser_height, position, direction=(0.0, 0.0, 1.0))

    element = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcPlate", name=name)
    rep = ifc.createIfcShapeRepresentation(context, "Body", "SweptSolid", [solid])
    prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
    element.Representation = prod_rep

    origin = ifc.createIfcCartesianPoint((0.0, 0.0, 0.0))
    placement = ifc.createIfcAxis2Placement3D(origin, None, None)
    local_placement = ifc.createIfcLocalPlacement(None, placement)
    element.ObjectPlacement = local_placement

    return element


# ────────────────────────────────────────────────────────────
# SINGLE WINDER (L-SHAPED)
# ────────────────────────────────────────────────────────────

def generate_single_winder(ifc, context, p):
    """
    Generate a single-winder (L-shaped) staircase using the 4-step construction.
    Flight 1 along +Y, winder treads at turn, Flight 2 perpendicular.
    Both flights shift away from the corner by the calculated offset.
    """
    elements = []
    width = p["stair_width"]
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    winders = p["turn1_winders"]
    turn_dir = p["turn1_direction"]
    turn1_enabled = p.get("turn1_enabled", True)

    actual_winders = winders if turn1_enabled else 0
    straight_treads = num_treads - actual_winders
    flight1_treads = straight_treads // 2
    flight2_treads = straight_treads - flight1_treads

    # Step 2: Post centre at junction of inner strings
    corner_x = 0.0 if turn_dir == "left" else width
    corner_y = flight1_treads * going

    # Step 3: Calculate offset and shift flights
    wg = compute_winder_geometry(p["newel_size"], width)
    offset = wg["offset"]

    # Flight 1 retreats along -Y by offset
    flight1_shift_y = -offset

    # Flight 1: straight along +Y axis (shifted back by offset)
    if flight1_treads > 0:
        flight1 = _create_stair_flight_element(
            ifc, context, "Flight 1",
            num_treads=flight1_treads,
            width=width,
            going=going,
            rise=rise,
            tread_thickness=tread_t,
            riser_thickness=riser_t,
            nosing=nosing,
            start_xyz=(0.0, flight1_shift_y, 0.0),
            rotation=None,
        )
        _add_pset_stair_flight(ifc, flight1, flight1_treads + 1, flight1_treads, rise, going)
        elements.append(flight1)

    # Risers for flight 1
    for i in range(flight1_treads + 1):
        riser_z = i * rise
        riser_y = i * going + flight1_shift_y
        riser = _create_riser(ifc, context, f"Riser F1-{i+1}", width, rise, riser_t, tread_t,
                              position=(0.0, riser_y, riser_z))
        if riser:
            elements.append(riser)

    # Step 4: Winder treads using construction-based profiles
    winder_start_riser = flight1_treads + 1

    for i in range(actual_winders):
        winder_z = (winder_start_riser + i) * rise - tread_t
        profile_coords = _winder_profiles_from_construction(
            corner_x, corner_y, p["newel_size"], width,
            turn_dir, i, actual_winders)
        winder = _create_winder_tread_from_profile(
            ifc, context, f"Winder {i+1}", profile_coords, tread_t, winder_z)
        elements.append(winder)

    # Newel post at the corner (Step 2: fixed, never moves)
    newel = _create_newel_post(ifc, context, "Newel Post",
                                corner_x, corner_y, p["newel_size"], p["floor_to_floor"])
    if newel:
        elements.append(newel)

    # Flight 2: after the turn, perpendicular
    # Flight 2 retreats along its own axis by offset
    flight2_start_riser = winder_start_riser + actual_winders
    x_sign = 1.0 if turn_dir == "left" else -1.0

    flight2_solids = []
    for i in range(flight2_treads):
        tread_z = (flight2_start_riser + i) * rise - tread_t
        if turn_dir == "left":
            tread_x = -(i * going) - going + nosing - offset
        else:
            tread_x = width + i * going - nosing + offset
        tread_y = corner_y

        profile = [
            (0.0, 0.0),
            (going + nosing + riser_t, 0.0),
            (going + nosing + riser_t, width),
            (0.0, width),
        ]
        solid = _create_extruded_solid(
            ifc, context, profile, tread_t,
            (tread_x, tread_y, tread_z),
        )
        flight2_solids.append(solid)

    if flight2_treads > 0 and flight2_solids:
        flight2 = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcStairFlight", name="Flight 2")
        rep = ifc.createIfcShapeRepresentation(context, "Body", "SweptSolid", flight2_solids)
        prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
        flight2.Representation = prod_rep
        origin = ifc.createIfcCartesianPoint((0.0, 0.0, 0.0))
        placement = ifc.createIfcAxis2Placement3D(origin, None, None)
        local_placement = ifc.createIfcLocalPlacement(None, placement)
        flight2.ObjectPlacement = local_placement
        _add_pset_stair_flight(ifc, flight2, flight2_treads + 1, flight2_treads, rise, going)
        elements.append(flight2)

    return elements


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
                                         turn_direction, winder_index, num_winders=3):
    """Generate winder tread profile using the 4-step construction sequence.

    For a standard 3-winder turn:
      - Winder 0: flanking winder (flight-1 side)
      - Winder 1: kite winder (wraps around corner)
      - Winder 2: flanking winder (flight-2 side)

    Division lines are axis-aligned (horizontal and vertical), meeting at the
    winder centre point. The horizontal line passes through the 25mm mark on
    Face B (the face looking toward flight 1's outer string). The vertical line
    passes through the 25mm mark on Face A (the face looking toward flight 2's
    outer string).

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
    offset = hp - 25.0
    x_sign = 1.0 if turn_direction == "left" else -1.0

    # Post corner nearest turn interior (where Face A and Face B meet)
    pc_x = post_cx + x_sign * hp
    pc_y = post_cy + hp

    # Division lines from winder centre through 25mm marks on post faces
    div_y = pc_y - 25.0                    # horizontal line (Face B 25mm mark)
    div_x = pc_x - x_sign * 25.0          # vertical line (Face A 25mm mark)

    # Outer string positions (perpendicular to each flight's axis, unchanged by shift)
    outer_f1 = post_cx + x_sign * stair_width   # flight 1 outer string
    outer_f2 = post_cy + stair_width              # flight 2 outer string

    # Opposite post face edge (flight 2 side of post)
    opp_x = post_cx - x_sign * hp

    if num_winders == 3:
        if winder_index == 0:
            # Flanking winder (flight-1 side): rectangle from post bottom to div_y
            profile = [
                (pc_x, post_cy - hp),
                (outer_f1, post_cy - hp),
                (outer_f1, div_y),
                (pc_x, div_y),
            ]
        elif winder_index == 1:
            # Kite winder: L-shape wrapping around post corner
            profile = [
                (pc_x, div_y),
                (outer_f1, div_y),
                (outer_f1, outer_f2),
                (div_x, outer_f2),
                (div_x, pc_y),
                (pc_x, pc_y),
            ]
        elif winder_index == 2:
            # Flanking winder (flight-2 side): rectangle from div_x to post edge
            profile = [
                (div_x, pc_y),
                (div_x, outer_f2),
                (opp_x, outer_f2),
                (opp_x, pc_y),
            ]

    elif num_winders == 2:
        # No kite — diagonal through post corner divides the turn
        if winder_index == 0:
            profile = [
                (pc_x, post_cy - hp),
                (outer_f1, post_cy - hp),
                (outer_f1, outer_f2),
                (pc_x, pc_y),
            ]
        elif winder_index == 1:
            profile = [
                (pc_x, pc_y),
                (outer_f1, outer_f2),
                (opp_x, outer_f2),
                (opp_x, pc_y),
            ]

    elif num_winders == 4:
        # 2 flanking + kite subdivided by diagonal through post corner
        if winder_index == 0:
            profile = [
                (pc_x, post_cy - hp),
                (outer_f1, post_cy - hp),
                (outer_f1, div_y),
                (pc_x, div_y),
            ]
        elif winder_index == 1:
            # Half-kite (flight-1 side)
            profile = [
                (pc_x, div_y),
                (outer_f1, div_y),
                (outer_f1, outer_f2),
                (pc_x, pc_y),
            ]
        elif winder_index == 2:
            # Half-kite (flight-2 side)
            profile = [
                (pc_x, pc_y),
                (outer_f1, outer_f2),
                (div_x, outer_f2),
                (div_x, pc_y),
            ]
        elif winder_index == 3:
            profile = [
                (div_x, pc_y),
                (div_x, outer_f2),
                (opp_x, outer_f2),
                (opp_x, pc_y),
            ]
    else:
        profile = [(post_cx, post_cy)]

    return profile


def _winder_kite_profile(corner_x, corner_y, width, angle_start, angle_end, turn_direction, half_post=0.0):
    """Compute straight-edged winder kite profile for turn 1.

    Outer edges align with adjacent flight outer edges. If half_post > 0,
    the inner tip wraps around the newel post instead of meeting at a point.
    """
    quarter = math.pi / 4
    eps = 1e-9
    x_sign = 1.0 if turn_direction == "left" else -1.0

    def _outer(angle):
        if angle < eps:
            return (corner_x + x_sign * width, corner_y)
        if angle > math.pi / 2 - eps:
            return (corner_x, corner_y + width)
        if angle < quarter:
            return (corner_x + x_sign * width, corner_y + width * math.tan(angle))
        else:
            return (corner_x + x_sign * width / math.tan(angle), corner_y + width)

    straddles = angle_start < quarter - eps and angle_end > quarter + eps

    if half_post <= 0:
        profile = [(corner_x, corner_y)]
        profile.append(_outer(angle_start))
        if straddles:
            profile.append((corner_x + x_sign * width, corner_y + width))
        profile.append(_outer(angle_end))
        return profile

    hp = half_post

    def _inner(angle):
        if angle < eps:
            return (corner_x + x_sign * hp, corner_y)
        if angle > math.pi / 2 - eps:
            return (corner_x, corner_y + hp)
        if angle < quarter:
            return (corner_x + x_sign * hp, corner_y + hp * math.tan(angle))
        else:
            return (corner_x + x_sign * hp / math.tan(angle), corner_y + hp)

    profile = []
    profile.append(_inner(angle_start))
    profile.append(_outer(angle_start))
    if straddles:
        profile.append((corner_x + x_sign * width, corner_y + width))
    profile.append(_outer(angle_end))
    profile.append(_inner(angle_end))
    if straddles:
        profile.append((corner_x + x_sign * hp, corner_y + hp))
    return profile


def _winder_kite_profile_turn2(corner_x, corner_y, width, angle_start, angle_end,
                                turn1_direction, turn2_direction, half_post=0.0):
    """Compute straight-edged winder kite profile for turn 2.

    Turn 2 radial directions are rotated 90° from turn 1. If half_post > 0,
    the inner tip wraps around the newel post.
    """
    quarter = math.pi / 4
    eps = 1e-9
    if (turn1_direction == "left" and turn2_direction == "left") or \
       (turn1_direction == "right" and turn2_direction == "left"):
        x_sign = -1.0
    else:
        x_sign = 1.0

    def _outer(angle):
        if angle < eps:
            return (corner_x, corner_y + width)
        if angle > math.pi / 2 - eps:
            return (corner_x + x_sign * width, corner_y)
        if angle < quarter:
            return (corner_x + x_sign * width * math.tan(angle), corner_y + width)
        else:
            return (corner_x + x_sign * width, corner_y + width / math.tan(angle))

    straddles = angle_start < quarter - eps and angle_end > quarter + eps

    if half_post <= 0:
        profile = [(corner_x, corner_y)]
        profile.append(_outer(angle_start))
        if straddles:
            profile.append((corner_x + x_sign * width, corner_y + width))
        profile.append(_outer(angle_end))
        return profile

    hp = half_post

    def _inner(angle):
        if angle < eps:
            return (corner_x, corner_y + hp)
        if angle > math.pi / 2 - eps:
            return (corner_x + x_sign * hp, corner_y)
        if angle < quarter:
            return (corner_x + x_sign * hp * math.tan(angle), corner_y + hp)
        else:
            return (corner_x + x_sign * hp, corner_y + hp / math.tan(angle))

    profile = []
    profile.append(_inner(angle_start))
    profile.append(_outer(angle_start))
    if straddles:
        profile.append((corner_x + x_sign * width, corner_y + width))
    profile.append(_outer(angle_end))
    profile.append(_inner(angle_end))
    if straddles:
        profile.append((corner_x + x_sign * hp, corner_y + hp))
    return profile


def _create_winder_tread_from_profile(ifc, context, name, profile_coords, tread_thickness, z_base):
    """Create a winder tread as an IfcSlab from an explicit profile polygon."""
    solid = _create_extruded_solid(
        ifc, context, profile_coords, tread_thickness,
        (0.0, 0.0, z_base),
    )

    element = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSlab", name=name)
    rep = ifc.createIfcShapeRepresentation(context, "Body", "SweptSolid", [solid])
    prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
    element.Representation = prod_rep

    origin = ifc.createIfcCartesianPoint((0.0, 0.0, 0.0))
    placement = ifc.createIfcAxis2Placement3D(origin, None, None)
    local_placement = ifc.createIfcLocalPlacement(None, placement)
    element.ObjectPlacement = local_placement

    return element


def _create_winder_tread(ifc, context, name, width, tread_thickness, angle_start, angle_end,
                          rise, corner_x, corner_y, z_base, turn_direction, half_post=0.0):
    """Create a single winder tread as an IfcSlab with straight-edged kite profile."""
    profile_coords = _winder_kite_profile(
        corner_x, corner_y, width, angle_start, angle_end, turn_direction, half_post)

    solid = _create_extruded_solid(
        ifc, context, profile_coords, tread_thickness,
        (0.0, 0.0, z_base),
    )

    element = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSlab", name=name)
    rep = ifc.createIfcShapeRepresentation(context, "Body", "SweptSolid", [solid])
    prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
    element.Representation = prod_rep

    origin = ifc.createIfcCartesianPoint((0.0, 0.0, 0.0))
    placement = ifc.createIfcAxis2Placement3D(origin, None, None)
    local_placement = ifc.createIfcLocalPlacement(None, placement)
    element.ObjectPlacement = local_placement

    return element


# ────────────────────────────────────────────────────────────
# DOUBLE WINDER (U-SHAPED)
# ────────────────────────────────────────────────────────────

def generate_double_winder(ifc, context, p):
    """
    Generate a double-winder (U-shaped) staircase using the 4-step construction.
    Flight 1 along +Y, Turn 1 (90°), Flight 2 along +/-X, Turn 2 (90°), Flight 3 along -Y.
    Both flights adjacent to each turn shift by offset.
    """
    elements = []
    width = p["stair_width"]
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

    actual_winders1 = winders1 if turn1_enabled else 0
    actual_winders2 = winders2 if turn2_enabled else 0
    total_winders = actual_winders1 + actual_winders2
    straight_treads = num_treads - total_winders
    flight1_treads = straight_treads // 3
    flight2_treads = straight_treads // 3
    flight3_treads = straight_treads - flight1_treads - flight2_treads

    # Step 3: Calculate offset
    wg = compute_winder_geometry(p["newel_size"], width)
    offset = wg["offset"]

    riser_idx = 0

    # ─── Flight 1: along +Y (shifted back by offset from turn 1) ───
    flight1_shift_y = -offset if actual_winders1 > 0 else 0.0

    if flight1_treads > 0:
        flight1 = _create_stair_flight_element(
            ifc, context, "Flight 1",
            num_treads=flight1_treads,
            width=width,
            going=going,
            rise=rise,
            tread_thickness=tread_t,
            riser_thickness=riser_t,
            nosing=nosing,
            start_xyz=(0.0, flight1_shift_y, 0.0),
            rotation=None,
        )
        _add_pset_stair_flight(ifc, flight1, flight1_treads + 1, flight1_treads, rise, going)
        elements.append(flight1)

    for i in range(flight1_treads + 1):
        riser = _create_riser(ifc, context, f"Riser F1-{i+1}", width, rise, riser_t, tread_t,
                              position=(0.0, i * going + flight1_shift_y, i * rise))
        if riser:
            elements.append(riser)

    riser_idx = flight1_treads + 1

    # ─── Turn 1 winders (construction-based) ───
    corner1_y = flight1_treads * going
    corner1_x = 0.0 if turn1_dir == "left" else width

    if actual_winders1 > 0:
        for i in range(actual_winders1):
            winder_z = (riser_idx + i) * rise - tread_t
            profile_coords = _winder_profiles_from_construction(
                corner1_x, corner1_y, p["newel_size"], width,
                turn1_dir, i, actual_winders1)
            winder = _create_winder_tread_from_profile(
                ifc, context, f"Turn1 Winder {i+1}", profile_coords, tread_t, winder_z)
            elements.append(winder)

    newel1 = _create_newel_post(ifc, context, "Newel Post 1",
                                 corner1_x, corner1_y, p["newel_size"], p["floor_to_floor"])
    if newel1:
        elements.append(newel1)

    riser_idx += actual_winders1

    # ─── Flight 2: perpendicular (shifted by offset from both turns) ───
    flight2_offset_turn1 = offset if actual_winders1 > 0 else 0.0
    flight2_offset_turn2 = offset if actual_winders2 > 0 else 0.0

    flight2_solids = []
    for i in range(flight2_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        if turn1_dir == "left":
            tread_x = -(i * going) - going + nosing - flight2_offset_turn1
        else:
            tread_x = width + i * going - nosing + flight2_offset_turn1
        tread_y = corner1_y

        profile = [
            (0.0, 0.0),
            (going + nosing + riser_t, 0.0),
            (going + nosing + riser_t, width),
            (0.0, width),
        ]
        solid = _create_extruded_solid(
            ifc, context, profile, tread_t,
            (tread_x, tread_y, tread_z),
        )
        flight2_solids.append(solid)

    if flight2_treads > 0 and flight2_solids:
        flight2 = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcStairFlight", name="Flight 2")
        rep = ifc.createIfcShapeRepresentation(context, "Body", "SweptSolid", flight2_solids)
        prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
        flight2.Representation = prod_rep
        origin = ifc.createIfcCartesianPoint((0.0, 0.0, 0.0))
        placement = ifc.createIfcAxis2Placement3D(origin, None, None)
        local_placement = ifc.createIfcLocalPlacement(None, placement)
        flight2.ObjectPlacement = local_placement
        _add_pset_stair_flight(ifc, flight2, flight2_treads + 1, flight2_treads, rise, going)
        elements.append(flight2)

    if turn1_dir == "left":
        flight2_end_x = -(flight2_treads * going) - flight2_offset_turn1
    else:
        flight2_end_x = width + flight2_treads * going + flight2_offset_turn1

    riser_idx += flight2_treads

    # ─── Turn 2 winders (construction-based) ───
    corner2_x = flight2_end_x
    corner2_y = corner1_y

    if actual_winders2 > 0:
        for i in range(actual_winders2):
            winder_z = (riser_idx + i) * rise - tread_t
            profile_coords = _winder_profiles_from_construction(
                corner2_x, corner2_y, p["newel_size"], width,
                turn2_dir, i, actual_winders2)
            winder = _create_winder_tread_from_profile(
                ifc, context, f"Turn2 Winder {i+1}", profile_coords, tread_t, winder_z)
            elements.append(winder)

    newel2 = _create_newel_post(ifc, context, "Newel Post 2",
                                 corner2_x, corner2_y, p["newel_size"], p["floor_to_floor"])
    if newel2:
        elements.append(newel2)

    riser_idx += actual_winders2

    # ─── Flight 3: returns parallel to flight 1 but -Y (shifted by offset from turn 2) ───
    flight3_shift_y = offset if actual_winders2 > 0 else 0.0

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

    flight3_solids = []
    for i in range(flight3_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        tread_x = flight3_start_x
        tread_y = flight3_start_y - (i + 1) * going - nosing + flight3_shift_y
        profile = [
            (0.0, 0.0),
            (width, 0.0),
            (width, going + nosing + riser_t),
            (0.0, going + nosing + riser_t),
        ]

        solid = _create_extruded_solid(
            ifc, context, profile, tread_t,
            (tread_x, tread_y, tread_z),
        )
        flight3_solids.append(solid)

    if flight3_treads > 0 and flight3_solids:
        flight3 = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcStairFlight", name="Flight 3")
        rep = ifc.createIfcShapeRepresentation(context, "Body", "SweptSolid", flight3_solids)
        prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
        flight3.Representation = prod_rep
        origin = ifc.createIfcCartesianPoint((0.0, 0.0, 0.0))
        placement = ifc.createIfcAxis2Placement3D(origin, None, None)
        local_placement = ifc.createIfcLocalPlacement(None, placement)
        flight3.ObjectPlacement = local_placement
        _add_pset_stair_flight(ifc, flight3, flight3_treads + 1, flight3_treads, rise, going)
        elements.append(flight3)

    return elements


def _create_winder_tread_turn2(ifc, context, name, width, tread_thickness, angle_start, angle_end,
                                rise, corner_x, corner_y, z_base, turn1_direction, turn2_direction,
                                half_post=0.0):
    """Create a winder tread for the second turn with straight-edged kite profile."""
    profile_coords = _winder_kite_profile_turn2(
        corner_x, corner_y, width, angle_start, angle_end, turn1_direction, turn2_direction, half_post)

    solid = _create_extruded_solid(
        ifc, context, profile_coords, tread_thickness,
        (0.0, 0.0, z_base),
    )

    element = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSlab", name=name)
    rep = ifc.createIfcShapeRepresentation(context, "Body", "SweptSolid", [solid])
    prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
    element.Representation = prod_rep

    origin = ifc.createIfcCartesianPoint((0.0, 0.0, 0.0))
    placement = ifc.createIfcAxis2Placement3D(origin, None, None)
    local_placement = ifc.createIfcLocalPlacement(None, placement)
    element.ObjectPlacement = local_placement

    return element


# ────────────────────────────────────────────────────────────
# NEWEL POST
# ────────────────────────────────────────────────────────────

def _create_newel_post(ifc, context, name, center_x, center_y, newel_size, height):
    """Create a newel post as an IfcColumn, centered at (center_x, center_y)."""
    if newel_size <= 0:
        return None
    hs = newel_size / 2.0
    profile = [
        (center_x - hs, center_y - hs),
        (center_x + hs, center_y - hs),
        (center_x + hs, center_y + hs),
        (center_x - hs, center_y + hs),
    ]
    solid = _create_extruded_solid(ifc, context, profile, height, (0.0, 0.0, 0.0))
    element = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcColumn", name=name)
    rep = ifc.createIfcShapeRepresentation(context, "Body", "SweptSolid", [solid])
    prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
    element.Representation = prod_rep
    origin = ifc.createIfcCartesianPoint((0.0, 0.0, 0.0))
    placement = ifc.createIfcAxis2Placement3D(origin, None, None)
    local_placement = ifc.createIfcLocalPlacement(None, placement)
    element.ObjectPlacement = local_placement
    return element


# ────────────────────────────────────────────────────────────
# BUILDING REGULATIONS CHECKS
# ────────────────────────────────────────────────────────────

def check_building_regs(params):
    """
    Check parameters against Approved Document K (England & Wales) for private dwellings.
    Returns a list of check results.
    """
    p = parse_params(params)
    checks = []

    rise = p["rise"]
    going = p["going"]
    width = p["stair_width"]
    num_winders = 0
    if p["staircase_type"] in ("single_winder", "double_winder"):
        num_winders = p["turn1_winders"]
    if p["staircase_type"] == "double_winder":
        num_winders += p["turn2_winders"]

    # Individual Rise: max 200mm warn, max 220mm block
    rise_status = "pass"
    rise_msg = f"Individual rise: {rise:.1f}mm"
    if rise > 220:
        rise_status = "fail"
        rise_msg += " — Exceeds absolute maximum of 220mm"
    elif rise > 200:
        rise_status = "warn"
        rise_msg += " — Exceeds recommended maximum of 200mm (Doc K)"
    checks.append({"name": "Individual Rise", "status": rise_status, "message": rise_msg, "value": round(rise, 1)})

    # Individual Going: min 220mm
    going_status = "pass"
    going_msg = f"Individual going: {going:.1f}mm"
    if going < 220:
        going_status = "warn"
        going_msg += " — Below minimum 220mm (Doc K)"
    checks.append({"name": "Individual Going", "status": going_status, "message": going_msg, "value": round(going, 1)})

    # Pitch: max 42° for straight flights
    pitch_rad = math.atan2(rise, going)
    pitch_deg = math.degrees(pitch_rad)
    pitch_status = "pass"
    pitch_msg = f"Pitch: {pitch_deg:.1f}°"
    if pitch_deg > 42:
        pitch_status = "warn"
        pitch_msg += " — Exceeds maximum 42° for private staircase (Doc K)"
    checks.append({"name": "Pitch", "status": pitch_status, "message": pitch_msg, "value": round(pitch_deg, 1)})

    # 2R + G formula: should be 550-700mm
    two_r_g = 2 * rise + going
    formula_status = "pass"
    formula_msg = f"2R + G = {two_r_g:.0f}mm"
    if two_r_g < 550 or two_r_g > 700:
        formula_status = "warn"
        formula_msg += f" — Outside comfortable range 550-700mm"
    checks.append({"name": "2R + G", "status": formula_status, "message": formula_msg, "value": round(two_r_g, 0)})

    # Stair Width: min 600mm
    width_status = "pass"
    width_msg = f"Stair width: {width:.0f}mm"
    if width < 600:
        width_status = "warn"
        width_msg += " — Below minimum 600mm for private dwellings"
    checks.append({"name": "Stair Width", "status": width_status, "message": width_msg, "value": round(width, 0)})

    # Newel post size: min 75mm to meet 50mm + 25mm bearing requirement
    has_winders = (p["staircase_type"] in ("single_winder", "double_winder")
                   and (p.get("turn1_enabled", True) or p.get("turn2_enabled", True)))
    if has_winders:
        newel = p["newel_size"]
        newel_status = "pass"
        newel_msg = f"Newel post size: {newel:.0f}mm"
        if newel < 75:
            newel_status = "warn"
            newel_msg += " — Below 75mm minimum (50mm bearing + 25mm corner wrap)"
        checks.append({"name": "Newel Post Size", "status": newel_status, "message": newel_msg,
                       "value": round(newel, 0)})

    # Winder going at narrow end using 4-step construction geometry
    if has_winders:
        wg = compute_winder_geometry(p["newel_size"], width)

        # Construction guarantees: kite going = 50mm, flank going = 50mm
        narrow_going = min(wg["kite_going"], wg["flank_going"])
        narrow_status = "pass"
        narrow_msg = f"Winder narrow end going: {narrow_going:.0f}mm (kite: {wg['kite_going']:.0f}mm, flank: {wg['flank_going']:.0f}mm)"
        if narrow_going < 50:
            narrow_status = "warn"
            narrow_msg += " — Below minimum 50mm at inner string"
        checks.append({"name": "Winder Narrow Going", "status": narrow_status, "message": narrow_msg,
                       "value": round(narrow_going, 0)})

        # Effective width at turn (reduced by offset)
        eff_status = "pass"
        eff_msg = f"Effective width at turn: {wg['effective_width']:.0f}mm (offset: {wg['offset']:.0f}mm)"
        if wg["width_warning"]:
            eff_status = "warn"
            eff_msg += " — Below minimum 600mm at turn"
        checks.append({"name": "Effective Turn Width", "status": eff_status, "message": eff_msg,
                       "value": round(wg["effective_width"], 0)})

        # Walking line going: min 220mm measured 270mm from inner edge
        winders_per_turn = p["turn1_winders"]
        angle_per_winder = (math.pi / 2) / winders_per_turn
        walking_radius = 270
        walking_going = walking_radius * angle_per_winder
        wl_status = "pass"
        wl_msg = f"Winder walking line going: {walking_going:.0f}mm"
        if walking_going < 220:
            wl_status = "warn"
            wl_msg += " — Below minimum 220mm on walking line"
        checks.append({"name": "Walking Line Going", "status": wl_status, "message": wl_msg,
                       "value": round(walking_going, 0)})

    # Headroom: min 2000mm (informational - we don't have stairwell dimensions)
    checks.append({
        "name": "Headroom",
        "status": "info",
        "message": "Headroom: requires stairwell dimensions to calculate (min 2000mm per Doc K)",
        "value": None,
    })

    return checks
