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
    Generate a single-winder (L-shaped) staircase.
    Flight 1 goes along Y axis, then 3 winder treads turn 90°, then Flight 2 continues.
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

    # Distribute treads: winders in the middle, remaining split between flights
    straight_treads = num_treads - winders
    flight1_treads = straight_treads // 2
    flight2_treads = straight_treads - flight1_treads

    # Flight 1: straight along +Y axis
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
            start_xyz=(0.0, 0.0, 0.0),
            rotation=None,
        )
        _add_pset_stair_flight(ifc, flight1, flight1_treads + 1, flight1_treads, rise, going)
        elements.append(flight1)

    # Risers for flight 1
    for i in range(flight1_treads + 1):
        riser_z = i * rise
        riser_y = i * going
        riser = _create_riser(ifc, context, f"Riser F1-{i+1}", width, rise, riser_t, tread_t,
                              position=(0.0, riser_y, riser_z))
        if riser:
            elements.append(riser)

    # Winder treads
    winder_start_riser = flight1_treads + 1
    turn1_enabled = p.get("turn1_enabled", True)

    # If winders disabled, redistribute those treads to flights
    if not turn1_enabled:
        flight1_treads += winders // 2
        flight2_treads += winders - winders // 2
        winders = 0

    # Pivot at the internal corner of the stair (where inner strings meet)
    corner_y = flight1_treads * going  # end of flight 1
    corner_x = 0.0 if turn_dir == "left" else width
    half_post = p["newel_size"] / 2.0

    angle_per_winder = (math.pi / 2) / max(winders, 1)

    for i in range(winders):
        winder_z = (winder_start_riser + i) * rise - tread_t
        winder_elements = _create_winder_tread(
            ifc, context, f"Winder {i+1}",
            width=width,
            tread_thickness=tread_t,
            angle_start=i * angle_per_winder,
            angle_end=(i + 1) * angle_per_winder,
            rise=rise,
            corner_x=corner_x,
            corner_y=corner_y,
            z_base=winder_z,
            turn_direction=turn_dir,
            half_post=half_post,
        )
        elements.append(winder_elements)

    # Newel post at the corner
    newel = _create_newel_post(ifc, context, "Newel Post",
                                corner_x, corner_y, p["newel_size"], p["floor_to_floor"])
    if newel:
        elements.append(newel)

    # Flight 2: after the turn
    flight2_start_riser = winder_start_riser + winders

    # Flight 2 runs perpendicular, Y range = [corner_y, corner_y + width]
    flight2_solids = []
    for i in range(flight2_treads):
        tread_z = (flight2_start_riser + i) * rise - tread_t
        if turn_dir == "left":
            tread_x = -(i * going) - going + nosing
        else:
            tread_x = width + i * going - nosing
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
    Generate a double-winder (U-shaped) staircase.
    Flight 1 along +Y, Turn 1 (90°), Flight 2 along +/-X, Turn 2 (90°), Flight 3 along -Y.
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

    # If winders disabled, redistribute those treads to flights
    actual_winders1 = winders1 if turn1_enabled else 0
    actual_winders2 = winders2 if turn2_enabled else 0
    total_winders = actual_winders1 + actual_winders2
    straight_treads = num_treads - total_winders
    # Distribute: flight1, flight2 (middle), flight3
    flight1_treads = straight_treads // 3
    flight2_treads = straight_treads // 3
    flight3_treads = straight_treads - flight1_treads - flight2_treads

    riser_idx = 0

    # ─── Flight 1: along +Y ───
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
            start_xyz=(0.0, 0.0, 0.0),
            rotation=None,
        )
        _add_pset_stair_flight(ifc, flight1, flight1_treads + 1, flight1_treads, rise, going)
        elements.append(flight1)

    # Risers for flight 1
    for i in range(flight1_treads + 1):
        riser = _create_riser(ifc, context, f"Riser F1-{i+1}", width, rise, riser_t, tread_t,
                              position=(0.0, i * going, i * rise))
        if riser:
            elements.append(riser)

    riser_idx = flight1_treads + 1

    # ─── Turn 1 winders ───
    # Pivot at the internal corner (end of flight 1)
    corner1_y = flight1_treads * going
    corner1_x = 0.0 if turn1_dir == "left" else width
    half_post = p["newel_size"] / 2.0

    if actual_winders1 > 0:
        angle_per = (math.pi / 2) / actual_winders1
        for i in range(actual_winders1):
            winder_z = (riser_idx + i) * rise - tread_t
            winder = _create_winder_tread(
                ifc, context, f"Turn1 Winder {i+1}",
                width=width,
                tread_thickness=tread_t,
                angle_start=i * angle_per,
                angle_end=(i + 1) * angle_per,
                rise=rise,
                corner_x=corner1_x,
                corner_y=corner1_y,
                z_base=winder_z,
                turn_direction=turn1_dir,
                half_post=half_post,
            )
            elements.append(winder)

    # Newel post at turn 1 corner
    newel1 = _create_newel_post(ifc, context, "Newel Post 1",
                                 corner1_x, corner1_y, p["newel_size"], p["floor_to_floor"])
    if newel1:
        elements.append(newel1)

    riser_idx += actual_winders1

    # ─── Flight 2: perpendicular segment ───
    # Flight 2 runs perpendicular, Y range = [corner1_y, corner1_y + width]
    flight2_solids = []
    for i in range(flight2_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        if turn1_dir == "left":
            tread_x = -(i * going) - going + nosing
        else:
            tread_x = width + i * going - nosing
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
        flight2_end_x = -(flight2_treads * going)
    else:
        flight2_end_x = width + flight2_treads * going

    riser_idx += flight2_treads

    # ─── Turn 2 winders ───
    # Pivot at the internal corner of turn 2 (end of flight 2)
    corner2_x = flight2_end_x
    corner2_y = corner1_y  # same Y as turn 1 pivot (inner wall of F2)

    if actual_winders2 > 0:
        angle_per2 = (math.pi / 2) / actual_winders2
        for i in range(actual_winders2):
            winder_z = (riser_idx + i) * rise - tread_t
            winder = _create_winder_tread_turn2(
                ifc, context, f"Turn2 Winder {i+1}",
                width=width,
                tread_thickness=tread_t,
                angle_start=i * angle_per2,
                angle_end=(i + 1) * angle_per2,
                rise=rise,
                corner_x=corner2_x,
                corner_y=corner2_y,
                z_base=winder_z,
                turn1_direction=turn1_dir,
                turn2_direction=turn2_dir,
                half_post=half_post,
            )
            elements.append(winder)

    # Newel post at turn 2 corner
    newel2 = _create_newel_post(ifc, context, "Newel Post 2",
                                 corner2_x, corner2_y, p["newel_size"], p["floor_to_floor"])
    if newel2:
        elements.append(newel2)

    riser_idx += actual_winders2

    # ─── Flight 3: returns parallel to flight 1 but in -Y direction ───
    # Flight 3 goes -Y, spanning x from corner2_x to corner2_x + width (or - width)
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

    # Winder going at narrow end: min 50mm
    has_winders = (p["staircase_type"] in ("single_winder", "double_winder")
                   and (p.get("turn1_enabled", True) or p.get("turn2_enabled", True)))
    if has_winders:
        # Each turn is 90°. Winders per turn determines the angle per winder.
        winders_per_turn = p["turn1_winders"]  # use turn 1 as representative
        angle_per_winder = (math.pi / 2) / winders_per_turn

        # Narrow end going: at the inner string (near the newel post).
        newel_radius = p["newel_size"] / 2.0  # half of newel post
        narrow_going = newel_radius * angle_per_winder
        narrow_status = "pass"
        narrow_msg = f"Winder narrow end going: ~{narrow_going:.0f}mm (at {newel_radius}mm inner radius)"
        if narrow_going < 50:
            narrow_status = "warn"
            narrow_msg += " — Below minimum 50mm at inner string"
        checks.append({"name": "Winder Narrow Going", "status": narrow_status, "message": narrow_msg,
                       "value": round(narrow_going, 0)})

        # Walking line going: min 220mm measured 270mm from inner edge
        walking_radius = 270  # mm from inner edge for stairs < 1000mm wide
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
