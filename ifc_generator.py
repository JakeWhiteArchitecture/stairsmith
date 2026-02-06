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

    # Winder offset geometry — calculated for each turn
    if p["staircase_type"] in ("single_winder", "double_winder"):
        p["turn1_offset"] = compute_winder_offset(p["newel_size"], p["turn1_winders"])
        p["turn1_narrow_going"] = compute_narrow_going(p["newel_size"], p["turn1_winders"])
    if p["staircase_type"] == "double_winder":
        p["turn2_offset"] = compute_winder_offset(p["newel_size"], p["turn2_winders"])
        p["turn2_narrow_going"] = compute_narrow_going(p["newel_size"], p["turn2_winders"])

    return p


def compute_winder_offset(newel_size, num_winders):
    """Calculate the offset from the internal corner to the winder centre point.

    The winder centre is a separate point from the newel post centre.
    The newel post centre is at the internal corner (intersection of inner
    string axes). The winder centre is offset from this corner so that the
    division lines create ≥ 50mm going where they cross the post faces.

    For a line at angle α from the winder centre at distance d from the
    post face at hp from corner:
        - The line crosses the post face (at x=hp) at y = cy + (hp - cx) * tan(α)
        - Flanking winder going along post face = (d - hp) * tan(θ)
          where d is the distance from corner to winder centre

    Setting going ≥ 50: d ≥ hp + g_min / tan(θ)

    Returns the offset distance d from internal corner to winder centre.
    """
    g_min = 50.0  # mm, Building Regs minimum
    theta = (math.pi / 2.0) / max(num_winders, 1)
    hp = newel_size / 2.0
    # d must satisfy: (d - hp) * tan(θ) ≥ g_min
    d = hp + g_min / math.tan(theta)
    return d


def compute_narrow_going(newel_size, num_winders):
    """Calculate the actual narrow-end going at the post face for flanking winders.

    The going is the chord length along the newel post face between
    adjacent winder division lines:
        going = (d - hp) * tan(θ)
    where d = winder centre offset, hp = post half-width.
    """
    theta = (math.pi / 2.0) / max(num_winders, 1)
    d = compute_winder_offset(newel_size, num_winders)
    hp = newel_size / 2.0
    return (d - hp) * math.tan(theta)


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
    Generate a single-winder (L-shaped) staircase.
    Flight 1 goes along Y axis, then winder treads turn 90°, then Flight 2 continues.

    The winder centre point is offset from the internal corner to ensure
    50mm minimum narrow-end going at the newel post face. Both flights
    shift their plan position to align with the offset winder geometry.
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

    straight_treads = num_treads - winders
    flight1_treads = straight_treads // 2
    flight2_treads = straight_treads - flight1_treads

    turn1_enabled = p.get("turn1_enabled", True)
    if not turn1_enabled:
        flight1_treads += winders // 2
        flight2_treads += winders - winders // 2
        winders = 0

    hp = p["newel_size"] / 2.0
    d = p.get("turn1_offset", hp) if winders > 0 else 0.0
    inner_r = d - hp   # distance from winder centre to post face
    outer_r = width + hp - d  # distance from winder centre to outer string

    # Flight shift: inner strings align with post faces (at hp from corner)
    # For left turn: flight 1 inner at x=hp, outer at x=hp+width
    # For right turn: flight 1 inner at x=width-hp, outer at x=-hp... rethink
    if turn_dir == "left":
        f1_x = hp  # inner string at x=hp (post face)
    else:
        f1_x = 0.0  # outer string at x=0, inner at x=width

    # Flight 1: straight along +Y
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
            start_xyz=(f1_x, 0.0, 0.0),
            rotation=None,
        )
        _add_pset_stair_flight(ifc, flight1, flight1_treads + 1, flight1_treads, rise, going)
        elements.append(flight1)

    for i in range(flight1_treads + 1):
        riser = _create_riser(ifc, context, f"Riser F1-{i+1}", width, rise, riser_t, tread_t,
                              position=(f1_x, i * going, i * rise))
        if riser:
            elements.append(riser)

    winder_start_riser = flight1_treads + 1
    corner_y_int = flight1_treads * going  # internal corner Y

    # Winder centre: offset from internal corner INTO the stairwell
    # Internal corner for left turn is at (0, corner_y_int)
    # Post centre is at (0, corner_y_int), post faces at (hp, *) and (*, corner_y_int+hp)
    if turn_dir == "left":
        cx = d               # offset into stairwell in X
        cy = corner_y_int + d  # offset into stairwell in Y
    else:
        cx = width - d
        cy = corner_y_int + d

    # Newel post centred at internal corner (NOT at winder centre)
    post_cx = 0.0 if turn_dir == "left" else width
    post_cy = corner_y_int
    newel = _create_newel_post(ifc, context, "Newel Post",
                                post_cx, post_cy, p["newel_size"], p["floor_to_floor"])
    if newel:
        elements.append(newel)

    angle_per = (math.pi / 2) / max(winders, 1)
    for i in range(winders):
        winder_z = (winder_start_riser + i) * rise - tread_t
        winder_el = _create_winder_tread(
            ifc, context, f"Winder {i+1}",
            outer_r=outer_r,
            inner_r=inner_r,
            tread_thickness=tread_t,
            angle_start=i * angle_per,
            angle_end=(i + 1) * angle_per,
            rise=rise,
            corner_x=cx,
            corner_y=cy,
            z_base=winder_z,
            turn_direction=turn_dir,
        )
        elements.append(winder_el)

    # Flight 2: perpendicular, inner string at post face
    flight2_start_riser = winder_start_riser + winders
    # Flight 2 inner string at y = corner_y_int + hp (post face)
    # Flight 2 Y-range: [corner_y_int + hp, corner_y_int + hp + width]
    f2_y = corner_y_int + hp
    flight2_solids = []
    for i in range(flight2_treads):
        tread_z = (flight2_start_riser + i) * rise - tread_t
        if turn_dir == "left":
            tread_x = hp - (i * going) - going + nosing
        else:
            tread_x = (width - hp) + i * going - nosing
        tread_y = f2_y

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


def _winder_kite_profile(cx, cy, outer_r, inner_r, angle_start, angle_end, turn_direction):
    """Compute winder tread profile for turn 1 with offset winder centre.

    The winder centre (cx, cy) is offset from the internal corner.
    Division lines radiate from the centre. The tread extends:
      - OUTWARD from centre to the outer string (distance outer_r)
      - INWARD from centre to the newel post face (distance inner_r)

    The outer bounding box is at outer_r from centre (clipped to flight outer strings).
    The inner bounding box is at inner_r BEHIND the centre (toward the post).

    Args:
        cx, cy: winder centre point (absolute coordinates)
        outer_r: distance from centre to outer string
        inner_r: distance from centre to post face (backward from centre)
        angle_start, angle_end: sweep angles (0 to π/2)
        turn_direction: "left" or "right"
    """
    quarter = math.pi / 4
    eps = 1e-9
    x_sign = 1.0 if turn_direction == "left" else -1.0

    # Outer edge: forward from centre toward the outer string
    def _outer(angle):
        if angle < eps:
            return (cx + x_sign * outer_r, cy)
        if angle > math.pi / 2 - eps:
            return (cx, cy + outer_r)
        if angle < quarter:
            return (cx + x_sign * outer_r, cy + outer_r * math.tan(angle))
        else:
            return (cx + x_sign * outer_r / math.tan(angle), cy + outer_r)

    # Inner edge: backward from centre toward the post face
    # At angle α, backward point = (cx - x_sign * inner_r * cos(α), cy - inner_r * sin(α))
    # Clipped to post face bounding box at inner_r from centre
    def _inner(angle):
        if angle < eps:
            return (cx - x_sign * inner_r, cy)
        if angle > math.pi / 2 - eps:
            return (cx, cy - inner_r)
        if angle < quarter:
            return (cx - x_sign * inner_r, cy - inner_r * math.tan(angle))
        else:
            return (cx - x_sign * inner_r / math.tan(angle), cy - inner_r)

    outer_straddles = angle_start < quarter - eps and angle_end > quarter + eps
    inner_straddles = angle_start < quarter - eps and angle_end > quarter + eps

    profile = []
    # Inner start
    profile.append(_inner(angle_start))
    # Outer start
    profile.append(_outer(angle_start))
    # Outer corner (if straddles 45°)
    if outer_straddles:
        profile.append((cx + x_sign * outer_r, cy + outer_r))
    # Outer end
    profile.append(_outer(angle_end))
    # Inner end
    profile.append(_inner(angle_end))
    # Inner corner (if straddles 45°)
    if inner_straddles:
        profile.append((cx - x_sign * inner_r, cy - inner_r))

    return profile


def _winder_kite_profile_turn2(cx, cy, outer_r, inner_r, angle_start, angle_end,
                                turn1_direction, turn2_direction):
    """Compute winder tread profile for turn 2 with offset winder centre.

    Turn 2 radial directions are rotated 90° from turn 1. The first division
    line (0°) points along flight 2's perpendicular direction.

    Args:
        cx, cy: winder centre point (absolute coordinates)
        outer_r: distance from centre to outer string
        inner_r: distance from centre to post face (backward from centre)
        angle_start, angle_end: sweep angles (0 to π/2)
        turn1_direction, turn2_direction: turn directions
    """
    quarter = math.pi / 4
    eps = 1e-9
    if (turn1_direction == "left" and turn2_direction == "left") or \
       (turn1_direction == "right" and turn2_direction == "left"):
        x_sign = -1.0
    else:
        x_sign = 1.0

    # Outer edge: toward outer string (turn 2 uses rotated axes)
    def _outer(angle):
        if angle < eps:
            return (cx, cy + outer_r)
        if angle > math.pi / 2 - eps:
            return (cx + x_sign * outer_r, cy)
        if angle < quarter:
            return (cx + x_sign * outer_r * math.tan(angle), cy + outer_r)
        else:
            return (cx + x_sign * outer_r, cy + outer_r / math.tan(angle))

    # Inner edge: backward toward post face
    def _inner(angle):
        if angle < eps:
            return (cx, cy - inner_r)
        if angle > math.pi / 2 - eps:
            return (cx - x_sign * inner_r, cy)
        if angle < quarter:
            return (cx - x_sign * inner_r * math.tan(angle), cy - inner_r)
        else:
            return (cx - x_sign * inner_r, cy - inner_r / math.tan(angle))

    straddles = angle_start < quarter - eps and angle_end > quarter + eps

    profile = []
    profile.append(_inner(angle_start))
    profile.append(_outer(angle_start))
    if straddles:
        profile.append((cx + x_sign * outer_r, cy + outer_r))
    profile.append(_outer(angle_end))
    profile.append(_inner(angle_end))
    if straddles:
        profile.append((cx - x_sign * inner_r, cy - inner_r))
    return profile


def _create_winder_tread(ifc, context, name, outer_r, inner_r, tread_thickness, angle_start, angle_end,
                          rise, corner_x, corner_y, z_base, turn_direction):
    """Create a single winder tread as an IfcSlab with offset kite profile."""
    profile_coords = _winder_kite_profile(
        corner_x, corner_y, outer_r, inner_r, angle_start, angle_end, turn_direction)

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
    Generate a double-winder (U-shaped) staircase with offset winder geometry.
    Flight 1 along +Y, Turn 1 (90°), Flight 2 along +/-X, Turn 2 (90°), Flight 3 along -Y.

    Each turn's winder centre is offset from its internal corner to ensure
    50mm minimum narrow-end going. Flights shift on plan to align.
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

    hp = p["newel_size"] / 2.0
    d1 = p.get("turn1_offset", hp) if actual_winders1 > 0 else 0.0
    d2 = p.get("turn2_offset", hp) if actual_winders2 > 0 else 0.0
    inner_r1 = d1 - hp
    outer_r1 = width + hp - d1
    inner_r2 = d2 - hp
    outer_r2 = width + hp - d2

    riser_idx = 0

    # ─── Flight 1: along +Y, inner string at post face ───
    if turn1_dir == "left":
        f1_x = hp
    else:
        f1_x = 0.0

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
            start_xyz=(f1_x, 0.0, 0.0),
            rotation=None,
        )
        _add_pset_stair_flight(ifc, flight1, flight1_treads + 1, flight1_treads, rise, going)
        elements.append(flight1)

    for i in range(flight1_treads + 1):
        riser = _create_riser(ifc, context, f"Riser F1-{i+1}", width, rise, riser_t, tread_t,
                              position=(f1_x, i * going, i * rise))
        if riser:
            elements.append(riser)

    riser_idx = flight1_treads + 1

    # ─── Turn 1 ───
    corner1_y_int = flight1_treads * going  # internal corner Y
    # Post centre at internal corner
    post1_cx = 0.0 if turn1_dir == "left" else width
    post1_cy = corner1_y_int
    # Winder centre offset from internal corner
    if turn1_dir == "left":
        cx1 = d1
        cy1 = corner1_y_int + d1
    else:
        cx1 = width - d1
        cy1 = corner1_y_int + d1

    newel1 = _create_newel_post(ifc, context, "Newel Post 1",
                                 post1_cx, post1_cy, p["newel_size"], p["floor_to_floor"])
    if newel1:
        elements.append(newel1)

    if actual_winders1 > 0:
        angle_per1 = (math.pi / 2) / actual_winders1
        for i in range(actual_winders1):
            winder_z = (riser_idx + i) * rise - tread_t
            winder = _create_winder_tread(
                ifc, context, f"Turn1 Winder {i+1}",
                outer_r=outer_r1,
                inner_r=inner_r1,
                tread_thickness=tread_t,
                angle_start=i * angle_per1,
                angle_end=(i + 1) * angle_per1,
                rise=rise,
                corner_x=cx1,
                corner_y=cy1,
                z_base=winder_z,
                turn_direction=turn1_dir,
            )
            elements.append(winder)

    riser_idx += actual_winders1

    # ─── Flight 2: perpendicular, inner string at post face ───
    f2_y = corner1_y_int + hp
    flight2_solids = []
    for i in range(flight2_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        if turn1_dir == "left":
            tread_x = hp - (i * going) - going + nosing
        else:
            tread_x = (width - hp) + i * going - nosing
        tread_y = f2_y

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

    # Flight 2 end X
    if turn1_dir == "left":
        flight2_end_x = hp - (flight2_treads * going)
    else:
        flight2_end_x = (width - hp) + flight2_treads * going

    riser_idx += flight2_treads

    # ─── Turn 2 ───
    # Internal corner of turn 2
    corner2_x_int = flight2_end_x
    corner2_y_int = corner1_y_int  # same Y as turn 1 (inner wall of F2 before shift)
    # Post centre at turn 2 internal corner
    if turn1_dir == "left" and turn2_dir == "left":
        post2_cx = corner2_x_int
        post2_cy = corner2_y_int
        cx2 = corner2_x_int - d2
        cy2 = corner2_y_int - d2
    elif turn1_dir == "left" and turn2_dir == "right":
        post2_cx = corner2_x_int
        post2_cy = corner2_y_int + width
        cx2 = corner2_x_int - d2
        cy2 = corner2_y_int + width + d2
    elif turn1_dir == "right" and turn2_dir == "right":
        post2_cx = corner2_x_int
        post2_cy = corner2_y_int
        cx2 = corner2_x_int + d2
        cy2 = corner2_y_int - d2
    else:  # right-left
        post2_cx = corner2_x_int
        post2_cy = corner2_y_int + width
        cx2 = corner2_x_int + d2
        cy2 = corner2_y_int + width + d2

    newel2 = _create_newel_post(ifc, context, "Newel Post 2",
                                 post2_cx, post2_cy, p["newel_size"], p["floor_to_floor"])
    if newel2:
        elements.append(newel2)

    if actual_winders2 > 0:
        angle_per2 = (math.pi / 2) / actual_winders2
        for i in range(actual_winders2):
            winder_z = (riser_idx + i) * rise - tread_t
            winder = _create_winder_tread_turn2(
                ifc, context, f"Turn2 Winder {i+1}",
                outer_r=outer_r2,
                inner_r=inner_r2,
                tread_thickness=tread_t,
                angle_start=i * angle_per2,
                angle_end=(i + 1) * angle_per2,
                rise=rise,
                corner_x=cx2,
                corner_y=cy2,
                z_base=winder_z,
                turn1_direction=turn1_dir,
                turn2_direction=turn2_dir,
            )
            elements.append(winder)

    riser_idx += actual_winders2

    # ─── Flight 3: returns parallel to flight 1 but in -Y direction ───
    # Flight 3 inner string at post 2 face, outer = inner + width
    if turn1_dir == "left" and turn2_dir == "left":
        flight3_start_x = post2_cx - hp - width
        flight3_start_y = post2_cy - hp
    elif turn1_dir == "right" and turn2_dir == "right":
        flight3_start_x = post2_cx + hp
        flight3_start_y = post2_cy - hp
    elif turn1_dir == "left" and turn2_dir == "right":
        flight3_start_x = post2_cx - hp
        flight3_start_y = post2_cy + hp
    else:  # right-left
        flight3_start_x = post2_cx + hp - width
        flight3_start_y = post2_cy + hp

    flight3_solids = []
    for i in range(flight3_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        tread_x = flight3_start_x
        tread_y = flight3_start_y - (i + 1) * going - nosing
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


def _create_winder_tread_turn2(ifc, context, name, outer_r, inner_r, tread_thickness, angle_start, angle_end,
                                rise, corner_x, corner_y, z_base, turn1_direction, turn2_direction):
    """Create a winder tread for the second turn with offset kite profile."""
    profile_coords = _winder_kite_profile_turn2(
        corner_x, corner_y, outer_r, inner_r, angle_start, angle_end, turn1_direction, turn2_direction)

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

    # Winder offset and narrow going checks
    has_winders = (p["staircase_type"] in ("single_winder", "double_winder")
                   and (p.get("turn1_enabled", True) or p.get("turn2_enabled", True)))
    if has_winders:
        newel = p["newel_size"]
        hp = newel / 2.0

        # Winder centre offset
        d = p.get("turn1_offset", hp)
        inner_r = d - hp
        outer_r = width + hp - d

        # Narrow going at post face (guaranteed ≥ 50mm by offset calculation)
        narrow = p.get("turn1_narrow_going", 50.0)
        narrow_status = "pass"
        narrow_msg = f"Winder narrow going at post face: {narrow:.0f}mm (offset {d:.0f}mm)"
        if narrow < 50:
            narrow_status = "fail"
            narrow_msg += " — Below minimum 50mm at newel face"
        checks.append({"name": "Winder Narrow Going", "status": narrow_status, "message": narrow_msg,
                       "value": round(narrow, 0)})

        # Effective width at turn: outer_r represents the winder reach from centre
        eff_width = outer_r + inner_r  # total tread width at the winders
        ew_status = "pass"
        ew_msg = f"Effective width at turn: {eff_width:.0f}mm"
        if eff_width < 600:
            ew_status = "warn"
            ew_msg += " — Below minimum 600mm at turn zone"
        checks.append({"name": "Effective Width at Turn", "status": ew_status, "message": ew_msg,
                       "value": round(eff_width, 0)})

        # Flight shift warning (> 25% of stair width)
        shift = hp  # flight shift = half post width
        shift_pct = (shift / width) * 100
        if shift_pct > 25:
            checks.append({"name": "Flight Shift", "status": "warn",
                           "message": f"Flight shift {shift:.0f}mm ({shift_pct:.0f}% of width) — consider increasing stair width",
                           "value": round(shift, 0)})

        # Walking line going: min 220mm measured 270mm from inner edge
        winders_per_turn = p["turn1_winders"]
        angle_per_winder = (math.pi / 2) / winders_per_turn
        walking_radius = 270 + inner_r  # 270mm from inner edge of winder = from post face
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
