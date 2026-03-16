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

    # Attach StairSmith disclaimer property set to IfcProject (raw entities
    # to avoid pset template lookup which fails in Pyodide/WASM)
    _DISCLAIMER = ("StairSmith \u2014 Preliminary design aid only. "
                   "User must verify all outputs before use.")
    _attach_disclaimer_pset(ifc, project, _DISCLAIMER)

    # Add 3D text annotation for the disclaimer
    _add_disclaimer_annotation(ifc, body, storey, p)

    # Set the Authorization field in the IFC file header
    ifc.wrapped_data.header.file_name.authorization = (
        "User must verify all outputs before use."
    )

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
    p["turn1_winders"] = 3  # Building regs: 90° corners must be triple winder or flat landing
    p["turn2_direction"] = params.get("turn2_direction", "left")
    p["turn2_winders"] = 3  # Building regs: 90° corners must be triple winder or flat landing
    p["turn1_enabled"] = bool(params.get("turn1_enabled", True))
    p["turn2_enabled"] = bool(params.get("turn2_enabled", True))
    p["newel_size"] = float(params.get("newel_size", 90))
    # Winder X: distance from internal corner of newel along post face (min 25, max newel_size)
    raw_x = float(params.get("winder_x", 25))
    p["winder_x"] = max(25.0, min(p["newel_size"], raw_x))
    # Winder Y: going from X endpoint toward flight (min 50)
    raw_y = float(params.get("winder_y", 50))
    p["winder_y"] = max(50.0, raw_y)
    # Same X/Y applies to both turns
    p["winder_x2"] = p["winder_x"]
    p["winder_y2"] = p["winder_y"]
    p["threshold_depth"] = float(params.get("threshold_depth", 100))
    # Flight distribution overrides (-1 = auto / equal split)
    p["flight1_steps"] = int(params.get("flight1_steps", -1))
    p["flight2_steps"] = int(params.get("flight2_steps", -1))
    p["flight3_steps"] = int(params.get("flight3_steps", -1))
    # Balustrade dimensions
    p["handrail_width"] = float(params.get("handrail_width", 70))
    p["handrail_height"] = float(params.get("handrail_height", 40))
    p["handrail_rise"] = float(params.get("handrail_rise", 900))
    p["baserail_width"] = float(params.get("baserail_width", 50))
    p["baserail_height"] = float(params.get("baserail_height", 30))
    p["spindle_width"] = float(params.get("spindle_width", 32))
    p["left_condition"] = params.get("left_condition", "balustrade")
    p["right_condition"] = params.get("right_condition", "wall")

    # Derived
    p["rise"] = p["floor_to_floor"] / p["num_risers"]
    p["num_treads"] = p["num_risers"] - 1  # one fewer tread than risers

    return p


def _create_extruded_solid(ifc, context, profile_coords, extrusion_depth, position_xyz,
                           direction=(0.0, 0.0, 1.0), axis=None, ref_direction=None):
    """
    Create an IfcExtrudedAreaSolid from a list of 2D profile coordinates,
    extruded along a direction.

    axis/ref_direction: optional orientation for the placement's local
    coordinate system.  The 2D profile lives in the local XY plane defined by
    (ref_direction, axis × ref_direction).  *direction* is expressed in this
    local frame.
    """
    # Create cartesian points for the profile
    points = [ifc.createIfcCartesianPoint(coord) for coord in profile_coords]
    points.append(points[0])  # close the loop

    polyline = ifc.createIfcPolyline(points)
    profile = ifc.createIfcArbitraryClosedProfileDef("AREA", None, polyline)

    # Position of the extrusion
    location = ifc.createIfcCartesianPoint(position_xyz)
    axis_ifc = ifc.createIfcDirection(axis) if axis else None
    ref_ifc = ifc.createIfcDirection(ref_direction) if ref_direction else None
    axis2 = ifc.createIfcAxis2Placement3D(location, axis_ifc, ref_ifc)

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


def _attach_disclaimer_pset(ifc, product, text):
    """Attach a StairSmith_Disclaimer property set to a product.

    Creates the IfcPropertySet, IfcPropertySingleValue and
    IfcRelDefinesByProperties entities directly to avoid the
    pset.add_pset / pset.edit_pset API which requires template files
    not available in the Pyodide/WASM build of IfcOpenShell.
    """
    prop = ifc.createIfcPropertySingleValue(
        "Notice", None,
        ifc.create_entity("IfcText", text),
        None,
    )
    owner_history = ifc.by_type("IfcOwnerHistory")[0] if ifc.by_type("IfcOwnerHistory") else None
    pset = ifc.createIfcPropertySet(
        ifcopenshell.guid.new(),
        owner_history,
        "StairSmith_Disclaimer",
        None,
        [prop],
    )
    ifc.createIfcRelDefinesByProperties(
        ifcopenshell.guid.new(),
        owner_history,
        None, None,
        [product],
        pset,
    )


def _add_disclaimer_annotation(ifc, context, storey, p):
    """Add a 3D text annotation with the StairSmith disclaimer.

    Creates two IfcAnnotation entities (one per line) positioned to the
    right of the staircase at floor level.
    """
    width = p["stair_width"]
    going = p["going"]
    num_treads = p["num_treads"]
    total_going = num_treads * going

    # Position: to the right and below the stair footprint
    text_x = width + 100  # 100mm to the right of the stair
    line1_y = -60
    line2_y = line1_y - 80  # 80mm line spacing

    lines = [
        ("StairSmith \u2014 Preliminary design aid only.", line1_y),
        ("User must verify all outputs before use.", line2_y),
    ]

    for text, y_pos in lines:
        annotation = ifcopenshell.api.run(
            "root.create_entity", ifc,
            ifc_class="IfcAnnotation",
            name="StairSmith Disclaimer",
        )

        # Text literal with placement
        origin = ifc.createIfcCartesianPoint((0.0, 0.0))
        axis_ref = ifc.createIfcAxis2Placement2D(origin, None)
        text_literal = ifc.createIfcTextLiteralWithExtent(
            text,            # Literal
            axis_ref,        # Placement
            "LEFT",          # Path — text direction
            ifc.createIfcPlanarExtent(2000.0, 60.0),  # Extent (width, height in mm)
        )

        rep = ifc.createIfcShapeRepresentation(
            context, "Annotation", "Annotation2D", [text_literal]
        )
        prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
        annotation.Representation = prod_rep

        # Place the annotation in 3D space
        loc = ifc.createIfcCartesianPoint((text_x, y_pos, 0.0))
        placement = ifc.createIfcAxis2Placement3D(loc, None, None)
        local_placement = ifc.createIfcLocalPlacement(None, placement)
        annotation.ObjectPlacement = local_placement

        # Assign to the storey
        ifcopenshell.api.run(
            "spatial.assign_container", ifc,
            relating_structure=storey,
            products=[annotation],
        )


def _add_pset_stair_flight(ifc, flight, num_risers, num_treads, rise, going):
    """Add Pset_StairFlightCommon property set to a stair flight.

    Uses low-level IFC entity creation instead of pset.edit_pset API to avoid
    needing the Pset_IFC2X3.ifc template file (missing from the WASM wheel).
    """
    props = [
        ifc.createIfcPropertySingleValue("NumberOfRiser", None,
            ifc.create_entity("IfcCountMeasure", int(num_risers)), None),
        ifc.createIfcPropertySingleValue("NumberOfTreads", None,
            ifc.create_entity("IfcCountMeasure", int(num_treads)), None),
        ifc.createIfcPropertySingleValue("RiserHeight", None,
            ifc.create_entity("IfcPositiveLengthMeasure", float(rise)), None),
        ifc.createIfcPropertySingleValue("TreadLength", None,
            ifc.create_entity("IfcPositiveLengthMeasure", float(going)), None),
    ]
    owner_history = ifc.by_type("IfcOwnerHistory")[0] if ifc.by_type("IfcOwnerHistory") else None
    pset = ifc.createIfcPropertySet(
        ifcopenshell.guid.new(), owner_history,
        "Pset_StairFlightCommon", None, props)
    ifc.createIfcRelDefinesByProperties(
        ifcopenshell.guid.new(), owner_history,
        None, None, [flight], pset)


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

    # Landing threshold strip
    ftf = num_risers * rise
    threshold_d = p["threshold_depth"]
    threshold_y = num_treads * going - nosing
    threshold_back = threshold_y + threshold_d
    thresh_profile = [
        (0.0, threshold_y),
        (width, threshold_y),
        (width, threshold_back),
        (0.0, threshold_back),
    ]
    thresh = _create_winder_tread_from_profile(
        ifc, context, "Threshold", thresh_profile, tread_t, ftf - tread_t)
    elements.append(thresh)

    # Balustrade elements (stringers, handrails, newel posts)
    _generate_ifc_balustrade_straight(ifc, context, p, elements)

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
    Both flights shift away from the corner by the X+Y winder offset.
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

    # Custom flight distribution if provided and valid
    f1_ov, f2_ov = p.get("flight1_steps", -1), p.get("flight2_steps", -1)
    if f1_ov >= 0 and f2_ov >= 0 and f1_ov + f2_ov == straight_treads:
        flight1_treads = f1_ov
        flight2_treads = f2_ov
    else:
        flight1_treads = straight_treads // 2
        flight2_treads = straight_treads - flight1_treads

    # Step 2: Post centre at junction of inner strings
    corner_x = 0.0 if turn_dir == "left" else width
    corner_y = flight1_treads * going

    # Step 3: Calculate offset using X+Y winder geometry
    ns = p["newel_size"]
    hp = ns / 2.0
    wg = compute_winder_geometry(ns, width)
    wx = p["winder_x"]
    wy = p["winder_y"]

    # Flight 1 shift: X+Y measured from internal corner
    flight1_shift_y = (hp - wx - wy + nosing) if actual_winders > 0 else 0.0

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
            corner_x, corner_y, ns, width,
            turn_dir, i, actual_winders,
            riser_extension=riser_t + nosing,
            flight_extension=wx + wy - 2 * hp,
            winder_x=wx)
        winder = _create_winder_tread_from_profile(
            ifc, context, f"Winder {i+1}", profile_coords, tread_t, winder_z)
        elements.append(winder)

    # Winder risers (between consecutive winder treads)
    winder_riser_profiles = _ifc_winder_riser_profiles(
        corner_x, corner_y, ns, width, turn_dir,
        actual_winders, winder_start_riser, rise, tread_t, riser_t,
        nosing=nosing, winder_x=wx)
    for idx, (profile, z_base, thickness) in enumerate(winder_riser_profiles):
        riser_elem = _create_winder_tread_from_profile(
            ifc, context, f"Winder Riser {idx+1}", profile, thickness, z_base)
        elements.append(riser_elem)

    # Newel post at the corner (Step 2: fixed, never moves)
    newel = _create_newel_post(ifc, context, "Newel Post",
                                corner_x, corner_y, ns, p["floor_to_floor"])
    if newel:
        elements.append(newel)

    # Landing tread when winders are off
    if actual_winders == 0:
        landing_z = winder_start_riser * rise - tread_t
        ext = nosing + riser_t
        landing_w = width + ext
        if turn_dir == "left":
            landing_x = -ext
        else:
            landing_x = 0.0
        landing_profile = [
            (landing_x, corner_y),
            (landing_x + landing_w, corner_y),
            (landing_x + landing_w, corner_y + width),
            (landing_x, corner_y + width),
        ]
        landing = _create_winder_tread_from_profile(
            ifc, context, "Landing", landing_profile, tread_t, landing_z)
        elements.append(landing)

    # Flight 2: after the turn, perpendicular
    flight2_start_riser = winder_start_riser + actual_winders
    # When winders are off, the landing consumes 1 rise
    if actual_winders == 0:
        flight2_start_riser += 1
        flight2_treads = max(0, flight2_treads - 1)

    winder_offset = (wx + wy - hp) if actual_winders > 0 else 0.0
    flight2_shift = winder_offset + nosing + riser_t / 2

    flight2_solids = []
    for i in range(flight2_treads):
        tread_z = (flight2_start_riser + i) * rise - tread_t
        if turn_dir == "left":
            tread_x = -(i * going) - going + nosing - flight2_shift - nosing / 2
        else:
            tread_x = width + i * going - nosing + flight2_shift - going + nosing / 2
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

    # Flight 2 risers
    riser_h = rise - tread_t
    if riser_t > 0:
        for i in range(flight2_treads + 1):
            riser_z = (flight2_start_riser + i - 1) * rise
            if turn_dir == "left":
                riser_x = -(i * going) - winder_offset - nosing
            else:
                riser_x = width + i * going + winder_offset + nosing
            riser_profile = [
                (riser_x, corner_y),
                (riser_x + riser_t, corner_y),
                (riser_x + riser_t, corner_y + width),
                (riser_x, corner_y + width),
            ]
            riser_elem = _create_winder_tread_from_profile(
                ifc, context, f"Riser F2-{i+1}", riser_profile, riser_h, riser_z)
            elements.append(riser_elem)

    # Landing threshold strip
    ftf = (num_treads + 1) * rise
    threshold_d = p["threshold_depth"]
    if turn_dir == "left":
        thresh_front = -(flight2_treads * going) - winder_offset + nosing
        thresh_back = thresh_front - threshold_d
        thresh_profile = [
            (thresh_back, corner_y),
            (thresh_front, corner_y),
            (thresh_front, corner_y + width),
            (thresh_back, corner_y + width),
        ]
    else:
        thresh_front = width + flight2_treads * going + winder_offset - nosing
        thresh_back = thresh_front + threshold_d
        thresh_profile = [
            (thresh_front, corner_y),
            (thresh_back, corner_y),
            (thresh_back, corner_y + width),
            (thresh_front, corner_y + width),
        ]
    thresh_z = ftf - tread_t
    thresh = _create_winder_tread_from_profile(
        ifc, context, "Threshold", thresh_profile, tread_t, thresh_z)
    elements.append(thresh)

    # Balustrade elements
    _generate_ifc_balustrade_single_winder(
        ifc, context, p, elements, flight1_treads, flight2_treads,
        winder_start_riser, flight2_start_riser, corner_x, corner_y,
        flight1_shift_y, winder_offset, actual_winders)

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
    import math

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


def _ifc_winder_riser_profiles(corner_x, corner_y, ns, width, turn_dir,
                                num_winders, winder_start_riser, rise, tread_t,
                                riser_t, nosing=0, rotation=0, winder_x=25.0):
    """Generate winder riser profiles for IFC export.

    Returns a list of (profile_coords, z_base, thickness) tuples.
    Each profile is a 2D polygon extruded vertically by thickness.
    Mirrors _winder_riser_meshes() from app.py but returns IFC-friendly data.
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

    results = []
    post_opp_x = corner_x - x_sign * hp

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

        front_off = nosing
        back_off = nosing + riser_t

        inner_front = (inner[0] + unx * front_off, inner[1] + uny * front_off)
        inner_back = (inner[0] + unx * back_off, inner[1] + uny * back_off)

        # Clamp inner riser ends to post face
        def _clamp_to_post(pt, offset):
            ex, ey = pt
            if abs(inner[0] - pc_x) < 1e-6:
                if abs(ex - pc_x) > 1e-6 and abs(lx) > 1e-9:
                    base_x = inner[0] + offset * unx
                    base_y = inner[1] + offset * uny
                    t = (pc_x - base_x) / lx
                    ex = pc_x
                    ey = base_y + t * ly
                else:
                    ex = pc_x
                ey = min(ey, pc_y)
            elif abs(inner[1] - pc_y) < 1e-6:
                if abs(ey - pc_y) > 1e-6 and abs(ly) > 1e-9:
                    base_x = inner[0] + offset * unx
                    base_y = inner[1] + offset * uny
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
                ex = pc_x
                ey = pc_y
            return (ex, ey)

        inner_front = _clamp_to_post(inner_front, front_off)
        inner_back = _clamp_to_post(inner_back, back_off)

        # Trace outer points to wall
        def _trace_to_wall(pt):
            tf1 = (outer_f1_x - pt[0]) / lx if abs(lx) > 1e-9 else float('inf')
            tf2 = (outer_f2_y - pt[1]) / ly if abs(ly) > 1e-9 else float('inf')
            if tf1 < 0: tf1 = float('inf')
            if tf2 < 0: tf2 = float('inf')
            t = min(tf1, tf2)
            return (pt[0] + lx * t, pt[1] + ly * t)

        outer_front = _trace_to_wall(inner_front)
        outer_back = _trace_to_wall(inner_back)

        strip = [inner_back, outer_back, outer_front, inner_front]

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
        results.append((strip, z_bottom, riser_h))

    return results


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
    Both flights adjacent to each turn shift by the X+Y winder offset.
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

    # Custom flight distribution if provided and valid
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

    # Step 3: Calculate offset using X+Y winder geometry
    ns = p["newel_size"]
    hp = ns / 2.0
    wg = compute_winder_geometry(ns, width)
    wx = p["winder_x"]
    wy = p["winder_y"]
    wx2 = p["winder_x2"]
    wy2 = p["winder_y2"]

    riser_idx = 0
    riser_h = rise - tread_t

    # ─── Flight 1: along +Y (shifted by X+Y from turn 1) ───
    flight1_shift_y = (hp - wx - wy + nosing) if actual_winders1 > 0 else 0.0

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

    turn1_winder_start = riser_idx
    for i in range(actual_winders1):
        winder_z = (riser_idx + i) * rise - tread_t
        profile_coords = _winder_profiles_from_construction(
            corner1_x, corner1_y, ns, width,
            turn1_dir, i, actual_winders1,
            riser_extension=riser_t + nosing,
            flight_extension=wx + wy - 2 * hp,
            winder_x=wx)
        winder = _create_winder_tread_from_profile(
            ifc, context, f"Turn1 Winder {i+1}", profile_coords, tread_t, winder_z)
        elements.append(winder)

    # Turn 1 winder risers
    winder_riser_profiles = _ifc_winder_riser_profiles(
        corner1_x, corner1_y, ns, width, turn1_dir,
        actual_winders1, turn1_winder_start, rise, tread_t, riser_t,
        nosing=nosing, winder_x=wx)
    for idx, (profile, z_base, thickness) in enumerate(winder_riser_profiles):
        riser_elem = _create_winder_tread_from_profile(
            ifc, context, f"Turn1 Winder Riser {idx+1}", profile, thickness, z_base)
        elements.append(riser_elem)

    newel1 = _create_newel_post(ifc, context, "Newel Post 1",
                                 corner1_x, corner1_y, ns, p["floor_to_floor"])
    if newel1:
        elements.append(newel1)

    riser_idx += actual_winders1

    # Turn 1 landing tread when winders are off
    if actual_winders1 == 0:
        landing1_z = turn1_winder_start * rise - tread_t
        ext = nosing + riser_t
        landing1_w = width + ext
        if turn1_dir == "left":
            landing1_x = -ext
        else:
            landing1_x = 0.0
        landing1_profile = [
            (landing1_x, corner1_y),
            (landing1_x + landing1_w, corner1_y),
            (landing1_x + landing1_w, corner1_y + width),
            (landing1_x, corner1_y + width),
        ]
        landing1 = _create_winder_tread_from_profile(
            ifc, context, "Landing 1", landing1_profile, tread_t, landing1_z)
        elements.append(landing1)
        riser_idx += 1
        flight2_treads = max(0, flight2_treads - 1)

    flight2_riser_start = riser_idx

    # ─── Flight 2: perpendicular (shifted by X+Y from both turns) ───
    winder_offset1 = (wx + wy - hp) if actual_winders1 > 0 else 0.0
    flight2_shift = winder_offset1 + nosing + riser_t / 2

    flight2_solids = []
    for i in range(flight2_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        if turn1_dir == "left":
            tread_x = -(i * going) - going + nosing - flight2_shift - nosing / 2
        else:
            tread_x = width + i * going - nosing + flight2_shift - going + nosing / 2
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

    # Flight 2 risers
    if riser_t > 0:
        for i in range(flight2_treads + 1):
            f2_riser_z = (flight2_riser_start + i - 1) * rise
            if turn1_dir == "left":
                riser_x = -(i * going) - winder_offset1 - nosing
            else:
                riser_x = width + i * going + winder_offset1 + nosing
            riser_profile = [
                (riser_x, corner1_y),
                (riser_x + riser_t, corner1_y),
                (riser_x + riser_t, corner1_y + width),
                (riser_x, corner1_y + width),
            ]
            riser_elem = _create_winder_tread_from_profile(
                ifc, context, f"Riser F2-{i+1}", riser_profile, riser_h, f2_riser_z)
            elements.append(riser_elem)

    riser_idx += flight2_treads

    # ─── Turn 2 winders ───
    winder_offset2 = (wx2 + wy2 - hp) if actual_winders2 > 0 else 0.0
    if turn1_dir == "left":
        corner2_x = -(flight2_treads * going) - winder_offset1 - winder_offset2
    else:
        corner2_x = width + flight2_treads * going + winder_offset1 + winder_offset2
    corner2_y = corner1_y

    # Turn 2 rotation: flight 2 approaches along -X (left) or +X (right)
    turn2_rotation = 90 if turn1_dir == "left" else -90

    turn2_winder_start = riser_idx
    for i in range(actual_winders2):
        winder_z = (riser_idx + i) * rise - tread_t
        profile_coords = _winder_profiles_from_construction(
            corner2_x, corner2_y, ns, width,
            turn2_dir, i, actual_winders2,
            rotation=turn2_rotation,
            riser_extension=riser_t + nosing,
            flight_extension=wx2 + wy2 - 2 * hp,
            winder_x=wx2)
        winder = _create_winder_tread_from_profile(
            ifc, context, f"Turn2 Winder {i+1}", profile_coords, tread_t, winder_z)
        elements.append(winder)

    # Turn 2 winder risers
    winder_riser_profiles2 = _ifc_winder_riser_profiles(
        corner2_x, corner2_y, ns, width, turn2_dir,
        actual_winders2, turn2_winder_start, rise, tread_t, riser_t,
        nosing=nosing, rotation=turn2_rotation, winder_x=wx2)
    for idx, (profile, z_base, thickness) in enumerate(winder_riser_profiles2):
        riser_elem = _create_winder_tread_from_profile(
            ifc, context, f"Turn2 Winder Riser {idx+1}", profile, thickness, z_base)
        elements.append(riser_elem)

    newel2 = _create_newel_post(ifc, context, "Newel Post 2",
                                 corner2_x, corner2_y, ns, p["floor_to_floor"])
    if newel2:
        elements.append(newel2)

    riser_idx += actual_winders2

    # ─── Flight 3 start position ───
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
        ext = nosing + riser_t
        landing2_profile = [
            (flight3_start_x, corner2_y),
            (flight3_start_x + width, corner2_y),
            (flight3_start_x + width, corner2_y + width + ext),
            (flight3_start_x, corner2_y + width + ext),
        ]
        landing2 = _create_winder_tread_from_profile(
            ifc, context, "Landing 2", landing2_profile, tread_t, landing2_z)
        elements.append(landing2)
        riser_idx += 1
        flight3_treads = max(0, flight3_treads - 1)

    flight3_riser_start = riser_idx

    # ─── Flight 3: returns parallel to flight 1 but -Y ───
    if actual_winders2 > 0:
        flight3_shift_y = -(winder_offset2 + riser_t)
    else:
        flight3_shift_y = -(flight3_start_y - corner2_y) - riser_t

    flight3_solids = []
    for i in range(flight3_treads):
        tread_z = (riser_idx + i) * rise - tread_t
        tread_y = flight3_start_y - (i + 1) * going - nosing + flight3_shift_y
        profile = [
            (0.0, 0.0),
            (width, 0.0),
            (width, going + nosing + riser_t),
            (0.0, going + nosing + riser_t),
        ]

        solid = _create_extruded_solid(
            ifc, context, profile, tread_t,
            (flight3_start_x, tread_y, tread_z),
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

    # Flight 3 risers
    if riser_t > 0:
        for i in range(flight3_treads + 1):
            f3_riser_z = (flight3_riser_start + i - 1) * rise
            riser_y = flight3_start_y - i * going - nosing + riser_t / 2 + flight3_shift_y
            riser_profile = [
                (flight3_start_x, riser_y - riser_t / 2),
                (flight3_start_x + width, riser_y - riser_t / 2),
                (flight3_start_x + width, riser_y + riser_t / 2),
                (flight3_start_x, riser_y + riser_t / 2),
            ]
            riser_elem = _create_winder_tread_from_profile(
                ifc, context, f"Riser F3-{i+1}", riser_profile, riser_h, f3_riser_z)
            elements.append(riser_elem)

    # Landing threshold strip (flight 3 top)
    ftf = (num_treads + 1) * rise
    threshold_d = p["threshold_depth"]
    thresh_riser_y = flight3_start_y - flight3_treads * going + flight3_shift_y
    thresh_front_y = thresh_riser_y + nosing
    thresh_back_y = thresh_front_y - threshold_d
    thresh_profile = [
        (flight3_start_x, thresh_back_y),
        (flight3_start_x + width, thresh_back_y),
        (flight3_start_x + width, thresh_front_y),
        (flight3_start_x, thresh_front_y),
    ]
    thresh_z = ftf - tread_t
    thresh = _create_winder_tread_from_profile(
        ifc, context, "Threshold", thresh_profile, tread_t, thresh_z)
    elements.append(thresh)

    # Balustrade elements
    _generate_ifc_balustrade_double_winder(
        ifc, context, p, elements,
        flight1_treads, flight2_treads, flight3_treads,
        corner1_x, corner1_y, corner2_x, corner2_y,
        flight1_shift_y, flight3_shift_y,
        winder_offset1, winder_offset2,
        flight2_riser_start, flight3_riser_start,
        turn1_winder_start, turn2_winder_start,
        actual_winders1, actual_winders2,
        flight3_start_x, flight3_start_y)

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
# IFC BALUSTRADE ELEMENTS (stringers, handrails, baserails, spindles)
# ────────────────────────────────────────────────────────────

# Constants matching app.py preview
STRINGER_THICKNESS = 32.0
STRINGER_HEIGHT = 275.0
STRINGER_PITCH_OFFSET = 25.0
STRINGER_DROP = 75.0
STRINGER_WALL_EXTENSION = 70.0  # Extension past nosing for wall condition (no newel post)
HANDRAIL_WIDTH = 70.0
HANDRAIL_HEIGHT = 40.0
HANDRAIL_RISE = 900.0
SPINDLE_SIZE = 32.0
SPINDLE_MAX_GAP = 99.0


def _create_pitched_profile_element_y(ifc, context, name, ifc_class, profile_yz, x_pos, thickness):
    """Create an IFC element from a Y-Z profile extruded in X direction.

    profile_yz: list of (y, z) points defining the 2D profile.
    x_pos: X position of the profile start (extrusion starts here).
    thickness: extrusion depth in X.
    """
    # Orient the local CS so the 2D profile maps to the YZ plane:
    #   local X (RefDir)  = global Y  →  profile u = IFC Y
    #   local Y (Axis×Ref)= global Z  →  profile v = IFC Z (height)
    #   local Z (Axis)    = global X  →  extrusion along IFC X
    profile_coords = [(pt[0], pt[1]) for pt in profile_yz]
    solid = _create_extruded_solid(
        ifc, context, profile_coords, thickness,
        (x_pos, 0.0, 0.0),
        direction=(0.0, 0.0, 1.0),
        axis=(1.0, 0.0, 0.0),
        ref_direction=(0.0, 1.0, 0.0),
    )
    return _create_element_with_geometry(ifc, context, ifc_class, name, solid)


def _create_pitched_profile_element_x(ifc, context, name, ifc_class, profile_xz, y_pos, thickness):
    """Create an IFC element from an X-Z profile extruded in Y direction.

    profile_xz: list of (x, z) points defining the 2D profile.
    y_pos: Y position of the profile start (extrusion starts here).
    thickness: extrusion depth in Y.
    """
    # Orient the local CS so the 2D profile maps to the XZ plane:
    #   local X (RefDir)  = global X   →  profile u = IFC X
    #   local Y (Axis×Ref)= global Z   →  profile v = IFC Z (height)
    #   local Z (Axis)    = global -Y   →  extrusion direction (0,0,-1)
    #                                      in local = global +Y
    profile_coords = [(pt[0], pt[1]) for pt in profile_xz]
    solid = _create_extruded_solid(
        ifc, context, profile_coords, thickness,
        (0.0, y_pos, 0.0),
        direction=(0.0, 0.0, -1.0),
        axis=(0.0, -1.0, 0.0),
        ref_direction=(1.0, 0.0, 0.0),
    )
    return _create_element_with_geometry(ifc, context, ifc_class, name, solid)


def _ifc_stringer_flight_y(ifc, context, name, x_pos, y_start, z_start, y_end, z_end):
    """Create a pitched stringer along Y as an IFC element.
    Bottom edge is clipped at z=0 (ground level)."""
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off

    # Calculate bottom edge positions, clipped at ground level (z=0)
    z_start_bottom = max(0.0, z_start - drop)
    z_end_bottom = max(0.0, z_end - drop)

    # If bottom is clipped, adjust the profile to maintain pitch
    if z_start_bottom == 0.0 and z_start - drop < 0.0:
        # Calculate where the pitched bottom edge intersects z=0
        dz = (z_end - drop) - (z_start - drop)
        dy = y_end - y_start
        if abs(dz) > 1e-9:
            # Interpolate Y position where bottom edge reaches z=0
            t = (0.0 - (z_start - drop)) / dz
            y_start = y_start + t * dy
            z_start = z_start + t * (z_end - z_start)

    profile = [
        (y_start, z_start_bottom),
        (y_end,   z_end_bottom),
        (y_end,   z_end + off),
        (y_start, z_start + off),
    ]
    return _create_pitched_profile_element_y(
        ifc, context, name, "IfcMember", profile,
        x_pos - STRINGER_THICKNESS / 2, STRINGER_THICKNESS)


def _ifc_stringer_flight_x(ifc, context, name, y_pos, x_start, z_start, x_end, z_end):
    """Create a pitched stringer along X as an IFC element.
    Bottom edge is clipped at z=0 (ground level)."""
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off

    # Calculate bottom edge positions, clipped at ground level (z=0)
    z_start_bottom = max(0.0, z_start - drop)
    z_end_bottom = max(0.0, z_end - drop)

    # If bottom is clipped, adjust the profile to maintain pitch
    if z_start_bottom == 0.0 and z_start - drop < 0.0:
        # Calculate where the pitched bottom edge intersects z=0
        dz = (z_end - drop) - (z_start - drop)
        dx = x_end - x_start
        if abs(dz) > 1e-9:
            # Interpolate X position where bottom edge reaches z=0
            t = (0.0 - (z_start - drop)) / dz
            x_start = x_start + t * dx
            z_start = z_start + t * (z_end - z_start)

    profile = [
        (x_start, z_start_bottom),
        (x_end,   z_end_bottom),
        (x_end,   z_end + off),
        (x_start, z_start + off),
    ]
    return _create_pitched_profile_element_x(
        ifc, context, name, "IfcMember", profile,
        y_pos - STRINGER_THICKNESS / 2, STRINGER_THICKNESS)


def _ifc_stringer_flight_y_notched(ifc, context, name, x_pos, y_start, z_start, y_end, z_end,
                                    ftf, y_back, tread_t):
    """Pitched stringer along Y with a notch at the top for landing threshold."""
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off
    overrun_bot = ftf - tread_t
    dy = y_end - y_start
    slope = (z_end - z_start) / dy if dy != 0 else 0
    z_back_top = z_end + off + slope * (y_back - y_end)
    profile = [
        (y_start, z_start - drop),
        (y_end,   z_end - drop),
        (y_end,   overrun_bot),
        (y_back,  overrun_bot),
        (y_back,  z_back_top),
        (y_start, z_start + off),
    ]
    return _create_pitched_profile_element_y(
        ifc, context, name, "IfcMember", profile,
        x_pos - STRINGER_THICKNESS / 2, STRINGER_THICKNESS)


def _ifc_stringer_flight_x_notched(ifc, context, name, y_pos, x_start, z_start, x_end, z_end,
                                    ftf, x_back, tread_t):
    """Pitched stringer along X with a notch at the top for landing threshold."""
    off = STRINGER_PITCH_OFFSET
    drop = STRINGER_HEIGHT - off
    overrun_bot = ftf - tread_t
    dx = x_end - x_start
    slope = (z_end - z_start) / dx if dx != 0 else 0
    z_back_top = z_end + off + slope * (x_back - x_end)
    profile = [
        (x_start, z_start - drop),
        (x_end,   z_end - drop),
        (x_end,   overrun_bot),
        (x_back,  overrun_bot),
        (x_back,  z_back_top),
        (x_start, z_start + off),
    ]
    return _create_pitched_profile_element_x(
        ifc, context, name, "IfcMember", profile,
        y_pos - STRINGER_THICKNESS / 2, STRINGER_THICKNESS)


def _ifc_handrail_flight_y(ifc, context, name, x_pos, y_start, z_start, y_end, z_end, **kw):
    """Create a pitched handrail along Y as an IFC element."""
    w = kw.get("hr_width", HANDRAIL_WIDTH)
    h = kw.get("hr_height", HANDRAIL_HEIGHT)
    r = kw.get("hr_rise", HANDRAIL_RISE)
    profile = [
        (y_start, z_start + r - h),
        (y_end,   z_end + r - h),
        (y_end,   z_end + r),
        (y_start, z_start + r),
    ]
    return _create_pitched_profile_element_y(
        ifc, context, name, "IfcRailing", profile, x_pos - w / 2, w)


def _ifc_handrail_flight_x(ifc, context, name, y_pos, x_start, z_start, x_end, z_end, **kw):
    """Create a pitched handrail along X as an IFC element."""
    w = kw.get("hr_width", HANDRAIL_WIDTH)
    h = kw.get("hr_height", HANDRAIL_HEIGHT)
    r = kw.get("hr_rise", HANDRAIL_RISE)
    profile = [
        (x_start, z_start + r - h),
        (x_end,   z_end + r - h),
        (x_end,   z_end + r),
        (x_start, z_start + r),
    ]
    return _create_pitched_profile_element_x(
        ifc, context, name, "IfcRailing", profile, y_pos - w / 2, w)


def _ifc_baserail_flight_y(ifc, context, name, x_pos, y_start, z_start, y_end, z_end, **kw):
    """Create a base rail along Y as an IFC element."""
    w = kw.get("br_width", HANDRAIL_WIDTH)
    h = kw.get("br_height", HANDRAIL_HEIGHT)
    bot = STRINGER_PITCH_OFFSET
    top = STRINGER_PITCH_OFFSET + h
    profile = [
        (y_start, z_start + bot),
        (y_end,   z_end + bot),
        (y_end,   z_end + top),
        (y_start, z_start + top),
    ]
    return _create_pitched_profile_element_y(
        ifc, context, name, "IfcRailing", profile, x_pos - w / 2, w)


def _ifc_baserail_flight_x(ifc, context, name, y_pos, x_start, z_start, x_end, z_end, **kw):
    """Create a base rail along X as an IFC element."""
    w = kw.get("br_width", HANDRAIL_WIDTH)
    h = kw.get("br_height", HANDRAIL_HEIGHT)
    bot = STRINGER_PITCH_OFFSET
    top = STRINGER_PITCH_OFFSET + h
    profile = [
        (x_start, z_start + bot),
        (x_end,   z_end + bot),
        (x_end,   z_end + top),
        (x_start, z_start + top),
    ]
    return _create_pitched_profile_element_x(
        ifc, context, name, "IfcRailing", profile, y_pos - w / 2, w)


def _ifc_spindles_flight_y(ifc, context, name_prefix, x_pos, y_start, z_start, y_end, z_end, **kw):
    """Create spindles along a Y-direction flight. Returns list of IFC elements."""
    sp = kw.get("spindle_size", SPINDLE_SIZE)
    br_h = kw.get("br_height", HANDRAIL_HEIGHT)
    hr_h = kw.get("hr_height", HANDRAIL_HEIGHT)
    hr_r = kw.get("hr_rise", HANDRAIL_RISE)
    br_top_off = STRINGER_PITCH_OFFSET + br_h
    hr_bot_off = hr_r - hr_h
    dy = y_end - y_start
    length = abs(dy)
    if length < 1e-9:
        return []
    k = max(0, math.ceil((length - SPINDLE_MAX_GAP) / (SPINDLE_MAX_GAP + sp)))
    if k == 0:
        return []
    gap = (length - k * sp) / (k + 1)
    first_centre = gap + sp / 2
    centre_step = gap + sp
    slope = (z_end - z_start) / dy
    dz_half = slope * sp / 2
    elements = []
    for i in range(k):
        pos = first_centre + i * centre_step
        t = pos / length
        y = y_start + t * dy
        z = z_start + t * (z_end - z_start)
        z_bot = z + br_top_off
        z_top = z + hr_bot_off
        if z_top - z_bot > sp:
            profile = [
                (y - sp / 2, z_bot - dz_half),
                (y + sp / 2, z_bot + dz_half),
                (y + sp / 2, z_top + dz_half),
                (y - sp / 2, z_top - dz_half),
            ]
            elem = _create_pitched_profile_element_y(
                ifc, context, f"{name_prefix} {i+1}", "IfcMember", profile,
                x_pos - sp / 2, sp)
            elements.append(elem)
    return elements


def _ifc_spindles_flight_x(ifc, context, name_prefix, y_pos, x_start, z_start, x_end, z_end, **kw):
    """Create spindles along an X-direction flight. Returns list of IFC elements."""
    sp = kw.get("spindle_size", SPINDLE_SIZE)
    br_h = kw.get("br_height", HANDRAIL_HEIGHT)
    hr_h = kw.get("hr_height", HANDRAIL_HEIGHT)
    hr_r = kw.get("hr_rise", HANDRAIL_RISE)
    br_top_off = STRINGER_PITCH_OFFSET + br_h
    hr_bot_off = hr_r - hr_h
    dx = x_end - x_start
    length = abs(dx)
    if length < 1e-9:
        return []
    k = max(0, math.ceil((length - SPINDLE_MAX_GAP) / (SPINDLE_MAX_GAP + sp)))
    if k == 0:
        return []
    gap = (length - k * sp) / (k + 1)
    first_centre = gap + sp / 2
    centre_step = gap + sp
    slope = (z_end - z_start) / dx
    dz_half = slope * sp / 2
    elements = []
    for i in range(k):
        pos = first_centre + i * centre_step
        t = pos / length
        x = x_start + t * dx
        z = z_start + t * (z_end - z_start)
        z_bot = z + br_top_off
        z_top = z + hr_bot_off
        if z_top - z_bot > sp:
            profile = [
                (x - sp / 2, z_bot - dz_half),
                (x + sp / 2, z_bot + dz_half),
                (x + sp / 2, z_top + dz_half),
                (x - sp / 2, z_top - dz_half),
            ]
            elem = _create_pitched_profile_element_x(
                ifc, context, f"{name_prefix} {i+1}", "IfcMember", profile,
                y_pos - sp / 2, sp)
            elements.append(elem)
    return elements


def _generate_ifc_balustrade_straight(ifc, context, p, elements):
    """Generate balustrade elements for a straight staircase."""
    width = p["stair_width"]
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    num_risers = p["num_risers"]
    ns = p["newel_size"]
    hp = ns / 2.0
    ftf = num_risers * rise
    threshold_d = p["threshold_depth"]

    hr_kw = {"hr_width": p["handrail_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"]}
    br_kw = {"br_width": p["baserail_width"], "br_height": p["baserail_height"]}
    sp_kw = {"spindle_size": p["spindle_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"], "br_height": p["baserail_height"]}

    nzs = rise * nosing / going
    y0 = 0.0
    y1 = num_treads * going + riser_t / 2
    z0 = rise + nzs
    z1 = (num_treads + 1) * rise + nzs + riser_t * rise / (2 * going)

    threshold_y = num_treads * going - nosing
    threshold_back = threshold_y + threshold_d

    NEWEL_CAP = 150.0
    hr_rise_val = p["handrail_rise"]
    bottom_post_y = -nosing
    top_post_y = threshold_y

    for x_pos, condition, side in [
        (0.0, p["left_condition"], "Left"),
        (width, p["right_condition"], "Right")
    ]:
        if condition == "balustrade":
            bot_face_y = bottom_post_y + hp
            top_face_y = top_post_y - hp
            dy = y1 - y0
            y0_c, z0_c = y0, z0
            if abs(dy) > 1e-9 and bot_face_y > y0:
                t_c = min(1.0, (bot_face_y - y0) / dy)
                y0_c = y0 + t_c * dy
                z0_c = z0 + t_c * (z1 - z0)
            y1_c, z1_c = y1, z1
            if abs(dy) > 1e-9 and top_face_y < y1:
                t_c = max(0.0, (top_face_y - y0) / dy)
                y1_c = y0 + t_c * dy
                z1_c = z0 + t_c * (z1 - z0)

            elements.append(_ifc_stringer_flight_y(ifc, context, f"{side} Stringer", x_pos, y0_c, z0_c, y1_c, z1_c))
            elements.append(_ifc_handrail_flight_y(ifc, context, f"{side} Handrail", x_pos, y0_c, z0_c, y1_c, z1_c, **hr_kw))
            elements.append(_ifc_baserail_flight_y(ifc, context, f"{side} Baserail", x_pos, y0_c, z0_c, y1_c, z1_c, **br_kw))
            elements.extend(_ifc_spindles_flight_y(ifc, context, f"{side} Spindle", x_pos, bot_face_y, z0_c, top_face_y, z1_c, **sp_kw))

            # Newel posts
            hr_bot = rise + nzs + hr_rise_val
            bot_h = hr_bot + NEWEL_CAP
            newel_bot = _create_newel_post(ifc, context, f"{side} Bottom Post", x_pos, bottom_post_y, ns, bot_h)
            if newel_bot:
                elements.append(newel_bot)
            hr_top = ftf + nzs + hr_rise_val
            top_h = hr_top + NEWEL_CAP
            newel_top = _create_newel_post(ifc, context, f"{side} Top Post", x_pos, top_post_y, ns, top_h)
            if newel_top:
                elements.append(newel_top)
        else:
            # Wall: notched stringer
            elements.append(_ifc_stringer_flight_y_notched(
                ifc, context, f"{side} Stringer", x_pos, y0, z0, y1, z1,
                ftf, threshold_back, tread_t))


def _generate_ifc_balustrade_single_winder(ifc, context, p, elements, flight1_treads, flight2_treads,
                                            winder_start_riser, flight2_start_riser, corner_x, corner_y,
                                            flight1_shift_y, winder_offset, actual_winders):
    """Generate balustrade elements for a single-winder staircase."""
    width = p["stair_width"]
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    ns = p["newel_size"]
    hp = ns / 2.0
    turn_dir = p["turn1_direction"]
    ftf = (num_treads + 1) * rise
    threshold_d = p["threshold_depth"]
    bottom_post_y = flight1_shift_y - nosing
    nzs = rise * nosing / going

    hr_kw = {"hr_width": p["handrail_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"]}
    br_kw = {"br_width": p["baserail_width"], "br_height": p["baserail_height"]}
    sp_kw = {"spindle_size": p["spindle_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"], "br_height": p["baserail_height"]}
    NEWEL_CAP = 150.0
    hr_rise_val = p["handrail_rise"]

    # Determine inner/outer based on turn direction
    if turn_dir == "left":
        render_inner = p["left_condition"] == "balustrade"
        render_outer = p["right_condition"] == "balustrade"
    else:
        render_inner = p["right_condition"] == "balustrade"
        render_outer = p["left_condition"] == "balustrade"

    inner_x = corner_x
    outer_x = width - corner_x

    # Flight 1 coordinates
    f1_y0 = flight1_shift_y
    f1_y1 = flight1_treads * going + flight1_shift_y
    f1_z0 = rise + nzs
    f1_z1 = (flight1_treads + 1) * rise + nzs
    bot_face_y = bottom_post_y + hp
    dy1 = f1_y1 - f1_y0

    # Flight 1 inner stringer + balustrade
    if render_inner and flight1_treads > 0:
        f1_y0_c, f1_z0_c = f1_y0, f1_z0
        if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
            t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
            f1_y0_c = f1_y0 + t_c * dy1
            f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
        # Clip end position to corner newel post face
        c_face_y = corner_y - hp
        f1_y1_c, f1_z1_c = f1_y1, f1_z1
        if abs(dy1) > 1e-9 and c_face_y < f1_y1:
            t_c = max(0.0, (c_face_y - f1_y0) / dy1)
            f1_y1_c = f1_y0 + t_c * dy1
            f1_z1_c = f1_z0 + t_c * (f1_z1 - f1_z0)
        elements.append(_ifc_stringer_flight_y(ifc, context, "Inner F1 Stringer", inner_x, f1_y0_c, f1_z0_c, f1_y1_c, f1_z1_c))
        elements.append(_ifc_handrail_flight_y(ifc, context, "Inner F1 Handrail", inner_x, f1_y0_c, f1_z0_c, f1_y1_c, f1_z1_c, **hr_kw))
        elements.append(_ifc_baserail_flight_y(ifc, context, "Inner F1 Baserail", inner_x, f1_y0_c, f1_z0_c, f1_y1_c, f1_z1_c, **br_kw))
        elements.extend(_ifc_spindles_flight_y(ifc, context, "Inner F1 Spindle", inner_x, f1_y0_c, f1_z0_c, c_face_y, f1_z1_c, **sp_kw))
    elif not render_inner and flight1_treads > 0:
        # Wall condition: extend stringer by 70mm past nosing
        f1_y0_wall = f1_y0 - STRINGER_WALL_EXTENSION
        f1_z0_wall = f1_z0 - STRINGER_WALL_EXTENSION * (f1_z1 - f1_z0) / dy1 if abs(dy1) > 1e-9 else f1_z0
        elements.append(_ifc_stringer_flight_y(ifc, context, "Inner F1 Stringer", inner_x, f1_y0_wall, f1_z0_wall, f1_y1, f1_z1))

    # Flight 1 outer stringer + balustrade
    if render_outer and flight1_treads > 0:
        f1_y0_oc, f1_z0_oc = f1_y0, f1_z0
        if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
            t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
            f1_y0_oc = f1_y0 + t_c * dy1
            f1_z0_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
        # Clip end position to landing/post corner face
        pc_face_y = f1_y1 - hp
        f1_y1_oc, f1_z1_oc = f1_y1, f1_z1
        if abs(dy1) > 1e-9 and pc_face_y < f1_y1:
            t_c = max(0.0, (pc_face_y - f1_y0) / dy1)
            f1_y1_oc = f1_y0 + t_c * dy1
            f1_z1_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
        # Extend Flight 1 stringer to outer_y - STRINGER_THICKNESS/2 so Flight 2 can overlap
        f1_y1_extended = outer_y - STRINGER_THICKNESS / 2
        f1_z1_extended = f1_z1 + (f1_y1_extended - f1_y1) * (f1_z1 - f1_z0) / dy1 if abs(dy1) > 1e-9 else f1_z1
        elements.append(_ifc_stringer_flight_y(ifc, context, "Outer F1 Stringer", outer_x, f1_y0_oc, f1_z0_oc, f1_y1_extended, f1_z1_extended))
        elements.append(_ifc_handrail_flight_y(ifc, context, "Outer F1 Handrail", outer_x, f1_y0_oc, f1_z0_oc, f1_y1_oc, f1_z1_oc, **hr_kw))
        elements.append(_ifc_baserail_flight_y(ifc, context, "Outer F1 Baserail", outer_x, f1_y0_oc, f1_z0_oc, f1_y1_oc, f1_z1_oc, **br_kw))
        elements.extend(_ifc_spindles_flight_y(ifc, context, "Outer F1 Spindle", outer_x, f1_y0_oc, f1_z0_oc, pc_face_y, f1_z1_oc, **sp_kw))
    elif not render_outer and flight1_treads > 0:
        # Wall condition: extend stringer by 70mm past nosing at base
        f1_y0_wall = f1_y0 - STRINGER_WALL_EXTENSION
        f1_z0_wall = f1_z0 - STRINGER_WALL_EXTENSION * (f1_z1 - f1_z0) / dy1 if abs(dy1) > 1e-9 else f1_z0
        # Extend Flight 1 stringer to outer_y - STRINGER_THICKNESS/2 so Flight 2 can overlap
        f1_y1_extended = outer_y - STRINGER_THICKNESS / 2
        f1_z1_extended = f1_z1 + (f1_y1_extended - f1_y1) * (f1_z1 - f1_z0) / dy1 if abs(dy1) > 1e-9 else f1_z1
        elements.append(_ifc_stringer_flight_y(ifc, context, "Outer F1 Stringer", outer_x, f1_y0_wall, f1_z0_wall, f1_y1_extended, f1_z1_extended))

    # Flight 2 coordinates
    inner_y = corner_y
    outer_y = corner_y + width
    if turn_dir == "left":
        f2_x0 = -winder_offset - nosing - riser_t / 2
        f2_x1 = -(flight2_treads * going) - winder_offset - nosing - riser_t / 2
        thresh_front = -(flight2_treads * going) - winder_offset + nosing
        thresh_back = thresh_front - threshold_d
    else:
        f2_x0 = width + winder_offset + nosing + riser_t / 2
        f2_x1 = width + flight2_treads * going + winder_offset + nosing + riser_t / 2
        thresh_front = width + flight2_treads * going + winder_offset - nosing
        thresh_back = thresh_front + threshold_d
    f2_z0 = flight2_start_riser * rise + nzs
    f2_z1 = (flight2_start_riser + flight2_treads) * rise + nzs
    z_fl = riser_t * rise / (2 * going)
    f2_x1_fl = f2_x1 + (-riser_t / 2 if turn_dir == "left" else riser_t / 2)
    f2_z1_fl = f2_z1 + z_fl

    if turn_dir == "left":
        top_post_x = thresh_front
        top_face_x = top_post_x + hp
    else:
        top_post_x = thresh_front
        top_face_x = top_post_x - hp

    # Flight 2 inner stringer + balustrade
    if render_inner and flight2_treads > 0:
        dx_s = f2_x1_fl - f2_x0
        f2_x1_c, f2_z1_c = f2_x1_fl, f2_z1_fl
        if abs(dx_s) > 1e-9:
            t_c = max(0.0, min(1.0, (top_face_x - f2_x0) / dx_s))
            f2_x1_c = f2_x0 + t_c * dx_s
            f2_z1_c = f2_z0 + t_c * (f2_z1_fl - f2_z0)
        elements.append(_ifc_stringer_flight_x(ifc, context, "Inner F2 Stringer", inner_y, f2_x0, f2_z0, f2_x1_c, f2_z1_c))
        elements.append(_ifc_handrail_flight_x(ifc, context, "Inner F2 Handrail", inner_y, f2_x0, f2_z0, f2_x1_c, f2_z1_c, **hr_kw))
        elements.append(_ifc_baserail_flight_x(ifc, context, "Inner F2 Baserail", inner_y, f2_x0, f2_z0, f2_x1_c, f2_z1_c, **br_kw))
    elif not render_inner and flight2_treads > 0:
        elements.append(_ifc_stringer_flight_x_notched(
            ifc, context, "Inner F2 Stringer", inner_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl,
            ftf, thresh_back, tread_t))

    if render_outer and flight2_treads > 0:
        # Extend Flight 2 stringer to outer_x + STRINGER_THICKNESS/2 (left) or outer_x - STRINGER_THICKNESS/2 (right)
        f2_x0_extended = outer_x + STRINGER_THICKNESS / 2 if turn_dir == "left" else outer_x - STRINGER_THICKNESS / 2
        dx_total = f2_x1_fl - f2_x0
        f2_z0_extended = f2_z0 - (f2_x0 - f2_x0_extended) * (f2_z1_fl - f2_z0) / dx_total if abs(dx_total) > 1e-9 else f2_z0
        elements.append(_ifc_stringer_flight_x(ifc, context, "Outer F2 Stringer", outer_y, f2_x0_extended, f2_z0_extended, f2_x1_fl, f2_z1_fl))
        elements.append(_ifc_handrail_flight_x(ifc, context, "Outer F2 Handrail", outer_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl, **hr_kw))
        elements.append(_ifc_baserail_flight_x(ifc, context, "Outer F2 Baserail", outer_y, f2_x0, f2_z0, f2_x1_fl, f2_z1_fl, **br_kw))
    elif not render_outer and flight2_treads > 0:
        # Extend Flight 2 stringer to outer_x + STRINGER_THICKNESS/2 (left) or outer_x - STRINGER_THICKNESS/2 (right)
        f2_x0_extended = outer_x + STRINGER_THICKNESS / 2 if turn_dir == "left" else outer_x - STRINGER_THICKNESS / 2
        dx_total = f2_x1_fl - f2_x0
        f2_z0_extended = f2_z0 - (f2_x0 - f2_x0_extended) * (f2_z1_fl - f2_z0) / dx_total if abs(dx_total) > 1e-9 else f2_z0
        elements.append(_ifc_stringer_flight_x_notched(
            ifc, context, "Outer F2 Stringer", outer_y, f2_x0_extended, f2_z0_extended, f2_x1_fl, f2_z1_fl,
            ftf, thresh_back, tread_t))

    # Inner newel posts
    if render_inner:
        if flight1_treads > 0:
            hr_bot = rise + nzs + hr_rise_val
            bot_h = hr_bot + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Inner Bottom Post", inner_x, bottom_post_y, ns, bot_h)
            if newel:
                elements.append(newel)
        hr_c_f1 = (flight1_treads + 1) * rise + nzs + hr_rise_val
        hr_c_f2 = flight2_start_riser * rise + nzs + hr_rise_val
        c_h = max(hr_c_f1, hr_c_f2) + NEWEL_CAP
        c_ns = max(ns, 100.0) if (flight1_treads == 0 or flight2_treads == 0) else ns
        newel = _create_newel_post(ifc, context, "Inner Corner Post", inner_x, corner_y, c_ns, c_h)
        if newel:
            elements.append(newel)
        if flight2_treads > 0:
            hr_top = (flight2_start_riser + flight2_treads) * rise + nzs + hr_rise_val
            top_h = hr_top + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Inner Top Post", top_post_x, corner_y, ns, top_h)
            if newel:
                elements.append(newel)

    # Outer newel posts
    if render_outer:
        if flight1_treads > 0:
            hr_bot = rise + nzs + hr_rise_val
            bot_h = hr_bot + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Outer Bottom Post", outer_x, bottom_post_y, ns, bot_h)
            if newel:
                elements.append(newel)
        if flight2_treads > 0:
            hr_top = (flight2_start_riser + flight2_treads) * rise + nzs + hr_rise_val
            top_h = hr_top + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Outer Top Post", top_post_x, outer_y, ns, top_h)
            if newel:
                elements.append(newel)


def _generate_ifc_balustrade_double_winder(ifc, context, p, elements,
                                            flight1_treads, flight2_treads, flight3_treads,
                                            corner1_x, corner1_y, corner2_x, corner2_y,
                                            flight1_shift_y, flight3_shift_y,
                                            winder_offset1, winder_offset2,
                                            flight2_riser_start, flight3_riser_start,
                                            turn1_winder_start, turn2_winder_start,
                                            actual_winders1, actual_winders2,
                                            flight3_start_x, flight3_start_y):
    """Generate balustrade elements for a double-winder staircase."""
    width = p["stair_width"]
    going = p["going"]
    rise = p["rise"]
    tread_t = p["tread_thickness"]
    riser_t = p["riser_thickness"]
    nosing = p["nosing"]
    num_treads = p["num_treads"]
    ns = p["newel_size"]
    hp = ns / 2.0
    turn1_dir = p["turn1_direction"]
    turn2_dir = p["turn2_direction"]
    ftf = (num_treads + 1) * rise
    threshold_d = p["threshold_depth"]
    bottom_post_y = flight1_shift_y - nosing
    nzs = rise * nosing / going

    hr_kw = {"hr_width": p["handrail_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"]}
    br_kw = {"br_width": p["baserail_width"], "br_height": p["baserail_height"]}
    sp_kw = {"spindle_size": p["spindle_width"], "hr_height": p["handrail_height"],
             "hr_rise": p["handrail_rise"], "br_height": p["baserail_height"]}
    NEWEL_CAP = 150.0
    hr_rise_val = p["handrail_rise"]

    # Map left/right conditions to inner/outer based on turn1 direction
    if turn1_dir == "left":
        render_inner = p["left_condition"] == "balustrade"
        render_outer = p["right_condition"] == "balustrade"
    else:
        render_inner = p["right_condition"] == "balustrade"
        render_outer = p["left_condition"] == "balustrade"

    # Corner / end post half-sizes (auto-enlarged to 100mm when absorbing a 0-tread flight)
    c1_ns = max(ns, 100.0) if flight1_treads == 0 else ns
    c2_ns = max(ns, 100.0) if flight3_treads == 0 else ns
    c1_hp = c1_ns / 2.0
    c2_hp = c2_ns / 2.0

    f1_inner_x = corner1_x
    f1_outer_x = width - corner1_x
    f2_inner_y = corner1_y
    f2_outer_y = corner1_y + width

    # Threshold Y (flight 3 top)
    thresh_riser_y = flight3_start_y - flight3_treads * going + flight3_shift_y
    top_post_y = thresh_riser_y + nosing

    # ─── Flight 1 coordinates ───
    f1_y0 = flight1_shift_y
    f1_y1 = flight1_treads * going + flight1_shift_y
    f1_z0 = rise + nzs
    f1_z1 = (flight1_treads + 1) * rise + nzs
    bot_face_y = bottom_post_y + hp
    dy1 = f1_y1 - f1_y0

    # ─── Flight 2 coordinates ───
    if turn1_dir == "left":
        f2_x_first = -winder_offset1 - nosing - riser_t / 2
        f2_x_last = -(flight2_treads * going) - winder_offset1 - nosing - riser_t / 2
    else:
        f2_x_first = width + winder_offset1 + nosing + riser_t / 2
        f2_x_last = width + flight2_treads * going + winder_offset1 + nosing + riser_t / 2
    f2_z_first = flight2_riser_start * rise + nzs
    f2_z_last = (flight2_riser_start + flight2_treads) * rise + nzs

    # ─── Flight 3 coordinates ───
    if turn1_dir == turn2_dir:
        f3_outer_x = flight3_start_x + corner1_x
        f3_inner_x = flight3_start_x + width - corner1_x
    else:
        f3_outer_x = flight3_start_x + width - corner1_x
        f3_inner_x = flight3_start_x + corner1_x

    f3_y_first = flight3_start_y - nosing + riser_t / 2 + flight3_shift_y
    f3_y_last = flight3_start_y - flight3_treads * going - nosing + riser_t / 2 + flight3_shift_y
    f3_z_first = flight3_riser_start * rise + nzs
    f3_z_last = (flight3_riser_start + flight3_treads) * rise + nzs
    z_fl = riser_t * rise / (2 * going)
    f3_y_last_fl = f3_y_last - riser_t / 2
    f3_z_last_fl = f3_z_last + z_fl
    top_face_y = top_post_y + hp
    dy3h = f3_y_last - f3_y_first

    # ─── Flight 1 inner stringer + balustrade ───
    if render_inner and flight1_treads > 0:
        f1_y0_c, f1_z0_c = f1_y0, f1_z0
        if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
            t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
            f1_y0_c = f1_y0 + t_c * dy1
            f1_z0_c = f1_z0 + t_c * (f1_z1 - f1_z0)
        # Clip end position to corner1 newel post face
        c1_face_y = corner1_y - c1_hp
        f1_y1_c, f1_z1_c = f1_y1, f1_z1
        if abs(dy1) > 1e-9 and c1_face_y < f1_y1:
            t_c = max(0.0, (c1_face_y - f1_y0) / dy1)
            f1_y1_c = f1_y0 + t_c * dy1
            f1_z1_c = f1_z0 + t_c * (f1_z1 - f1_z0)
        elements.append(_ifc_stringer_flight_y(ifc, context, "Inner F1 Stringer", f1_inner_x, f1_y0_c, f1_z0_c, f1_y1_c, f1_z1_c))
        elements.append(_ifc_handrail_flight_y(ifc, context, "Inner F1 Handrail", f1_inner_x, f1_y0_c, f1_z0_c, f1_y1_c, f1_z1_c, **hr_kw))
        elements.append(_ifc_baserail_flight_y(ifc, context, "Inner F1 Baserail", f1_inner_x, f1_y0_c, f1_z0_c, f1_y1_c, f1_z1_c, **br_kw))
        elements.extend(_ifc_spindles_flight_y(ifc, context, "Inner F1 Spindle", f1_inner_x, f1_y0_c, f1_z0_c, c1_face_y, f1_z1_c, **sp_kw))
    elif not render_inner and flight1_treads > 0:
        # Wall condition: extend stringer by 70mm past nosing
        f1_y0_wall = f1_y0 - STRINGER_WALL_EXTENSION
        f1_z0_wall = f1_z0 - STRINGER_WALL_EXTENSION * (f1_z1 - f1_z0) / dy1 if abs(dy1) > 1e-9 else f1_z0
        elements.append(_ifc_stringer_flight_y(ifc, context, "Inner F1 Stringer", f1_inner_x, f1_y0_wall, f1_z0_wall, f1_y1, f1_z1))

    # ─── Flight 1 outer stringer + balustrade ───
    if render_outer and flight1_treads > 0:
        f1_y0_oc, f1_z0_oc = f1_y0, f1_z0
        if abs(dy1) > 1e-9 and bot_face_y > f1_y0:
            t_c = min(1.0, (bot_face_y - f1_y0) / dy1)
            f1_y0_oc = f1_y0 + t_c * dy1
            f1_z0_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
        # Clip end position to landing/post corner face
        pc_face_y = f1_y1 - hp
        f1_y1_oc, f1_z1_oc = f1_y1, f1_z1
        if abs(dy1) > 1e-9 and pc_face_y < f1_y1:
            t_c = max(0.0, (pc_face_y - f1_y0) / dy1)
            f1_y1_oc = f1_y0 + t_c * dy1
            f1_z1_oc = f1_z0 + t_c * (f1_z1 - f1_z0)
        # Extend Flight 1 stringer to f2_outer_y - STRINGER_THICKNESS/2 so Flight 2 can overlap
        f1_y1_extended = f2_outer_y - STRINGER_THICKNESS / 2
        f1_z1_extended = f1_z1 + (f1_y1_extended - f1_y1) * (f1_z1 - f1_z0) / dy1 if abs(dy1) > 1e-9 else f1_z1
        elements.append(_ifc_stringer_flight_y(ifc, context, "Outer F1 Stringer", f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1_extended, f1_z1_extended))
        elements.append(_ifc_handrail_flight_y(ifc, context, "Outer F1 Handrail", f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1_oc, f1_z1_oc, **hr_kw))
        elements.append(_ifc_baserail_flight_y(ifc, context, "Outer F1 Baserail", f1_outer_x, f1_y0_oc, f1_z0_oc, f1_y1_oc, f1_z1_oc, **br_kw))
        elements.extend(_ifc_spindles_flight_y(ifc, context, "Outer F1 Spindle", f1_outer_x, f1_y0_oc, f1_z0_oc, pc_face_y, f1_z1_oc, **sp_kw))
    elif not render_outer and flight1_treads > 0:
        # Wall condition: extend stringer by 70mm past nosing at base
        f1_y0_wall = f1_y0 - STRINGER_WALL_EXTENSION
        f1_z0_wall = f1_z0 - STRINGER_WALL_EXTENSION * (f1_z1 - f1_z0) / dy1 if abs(dy1) > 1e-9 else f1_z0
        # Extend Flight 1 stringer to f2_outer_y - STRINGER_THICKNESS/2 so Flight 2 can overlap
        f1_y1_extended = f2_outer_y - STRINGER_THICKNESS / 2
        f1_z1_extended = f1_z1 + (f1_y1_extended - f1_y1) * (f1_z1 - f1_z0) / dy1 if abs(dy1) > 1e-9 else f1_z1
        elements.append(_ifc_stringer_flight_y(ifc, context, "Outer F1 Stringer", f1_outer_x, f1_y0_wall, f1_z0_wall, f1_y1_extended, f1_z1_extended))

    # ─── Flight 2 inner stringer + balustrade ───
    f2_dx = f2_x_last - f2_x_first
    if render_inner and flight2_treads > 0:
        elements.append(_ifc_stringer_flight_x(ifc, context, "Inner F2 Stringer", f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))
        elements.append(_ifc_handrail_flight_x(ifc, context, "Inner F2 Handrail", f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **hr_kw))
        elements.append(_ifc_baserail_flight_x(ifc, context, "Inner F2 Baserail", f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last, **br_kw))
        if abs(f2_dx) > 1e-9:
            if turn1_dir == "left":
                c1_face_x = corner1_x - c1_hp
                c2_face_x = corner2_x + c2_hp
            else:
                c1_face_x = corner1_x + c1_hp
                c2_face_x = corner2_x - c2_hp
            t0 = (c1_face_x - f2_x_first) / f2_dx
            t1 = (c2_face_x - f2_x_first) / f2_dx
            f2_sp_z0 = f2_z_first + t0 * (f2_z_last - f2_z_first)
            f2_sp_z1 = f2_z_first + t1 * (f2_z_last - f2_z_first)
            elements.extend(_ifc_spindles_flight_x(ifc, context, "Inner F2 Spindle", f2_inner_y, c1_face_x, f2_sp_z0, c2_face_x, f2_sp_z1, **sp_kw))
    elif not render_inner and flight2_treads > 0:
        elements.append(_ifc_stringer_flight_x(ifc, context, "Inner F2 Stringer", f2_inner_y, f2_x_first, f2_z_first, f2_x_last, f2_z_last))

    # ─── Flight 2 outer stringer + balustrade ───
    if render_outer and flight2_treads > 0:
        if turn1_dir == "left":
            pc1_face_x = f2_x_first + hp
            pc2_face_x = f2_x_last - hp if actual_winders2 > 0 else f2_x_last + hp
        else:
            pc1_face_x = f2_x_first - hp
            pc2_face_x = f2_x_last + hp if actual_winders2 > 0 else f2_x_last - hp
        # Extend Flight 2 stringer at both ends to meet Flight 1 and Flight 3
        f2_x_start_extended = f1_outer_x + STRINGER_THICKNESS / 2 if turn1_dir == "left" else f1_outer_x - STRINGER_THICKNESS / 2
        f2_x_end_extended = f3_outer_x + STRINGER_THICKNESS / 2 if turn1_dir == turn2_dir else f3_outer_x - STRINGER_THICKNESS / 2
        f2_x0_oc, f2_z0_oc = f2_x_first, f2_z_first
        f2_x1_oc, f2_z1_oc = f2_x_last, f2_z_last
        if abs(f2_dx) > 1e-9:
            # Extend at start (corner 1)
            f2_x0_oc = f2_x_start_extended
            f2_z0_oc = f2_z_first - (f2_x_first - f2_x_start_extended) * (f2_z_last - f2_z_first) / f2_dx
            # Trim at end for balustrade post (corner 2)
            t_c2 = max(0.0, min(1.0, (pc2_face_x - f2_x_first) / f2_dx))
            f2_x1_bal = f2_x_first + t_c2 * f2_dx
            f2_z1_bal = f2_z_first + t_c2 * (f2_z_last - f2_z_first)
            # Extend at end (corner 2) for stringer only
            f2_x1_oc = f2_x_end_extended
            f2_z1_oc = f2_z_first + (f2_x_end_extended - f2_x_first) * (f2_z_last - f2_z_first) / f2_dx
        elements.append(_ifc_stringer_flight_x(ifc, context, "Outer F2 Stringer", f2_outer_y, f2_x0_oc, f2_z0_oc, f2_x1_oc, f2_z1_oc))
        # Handrail and baserail use trimmed coordinates (not extended)
        f2_x0_hr = f2_x_first + (pc1_face_x - f2_x_first) * (f2_z_first - f2_z0_oc) / (f2_z_first - f2_z0_oc) if abs(f2_z0_oc - f2_z_first) > 1e-9 else f2_x_first
        elements.append(_ifc_handrail_flight_x(ifc, context, "Outer F2 Handrail", f2_outer_y, pc1_face_x, f2_z_first, f2_x1_bal, f2_z1_bal, **hr_kw))
        elements.append(_ifc_baserail_flight_x(ifc, context, "Outer F2 Baserail", f2_outer_y, pc1_face_x, f2_z_first, f2_x1_bal, f2_z1_bal, **br_kw))
        if abs(f2_dx) > 1e-9:
            elements.extend(_ifc_spindles_flight_x(ifc, context, "Outer F2 Spindle", f2_outer_y, pc1_face_x, f2_z_first, pc2_face_x, f2_z1_bal, **sp_kw))
    elif not render_outer and flight2_treads > 0:
        # Extend Flight 2 stringer at both ends to meet Flight 1 and Flight 3
        f2_x_start_extended = f1_outer_x + STRINGER_THICKNESS / 2 if turn1_dir == "left" else f1_outer_x - STRINGER_THICKNESS / 2
        f2_x_end_extended = f3_outer_x + STRINGER_THICKNESS / 2 if turn1_dir == turn2_dir else f3_outer_x - STRINGER_THICKNESS / 2
        f2_z_start_extended = f2_z_first - (f2_x_first - f2_x_start_extended) * (f2_z_last - f2_z_first) / f2_dx if abs(f2_dx) > 1e-9 else f2_z_first
        f2_z_end_extended = f2_z_first + (f2_x_end_extended - f2_x_first) * (f2_z_last - f2_z_first) / f2_dx if abs(f2_dx) > 1e-9 else f2_z_last
        elements.append(_ifc_stringer_flight_x(ifc, context, "Outer F2 Stringer", f2_outer_y, f2_x_start_extended, f2_z_start_extended, f2_x_end_extended, f2_z_end_extended))

    # ─── Flight 3 inner stringer + balustrade ───
    if render_inner and flight3_treads > 0:
        dy3s = f3_y_last_fl - f3_y_first
        f3_y_end_c, f3_z_end_c = f3_y_last_fl, f3_z_last_fl
        if abs(dy3s) > 1e-9 and top_face_y > f3_y_last_fl:
            t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3s))
            f3_y_end_c = f3_y_first + t_c * dy3s
            f3_z_end_c = f3_z_first + t_c * (f3_z_last_fl - f3_z_first)
        elements.append(_ifc_stringer_flight_y(ifc, context, "Inner F3 Stringer", f3_inner_x, f3_y_first, f3_z_first, f3_y_end_c, f3_z_end_c))
        f3_y_hr_c, f3_z_hr_c = f3_y_last, f3_z_last
        if abs(dy3h) > 1e-9 and top_face_y > f3_y_last:
            t_c = max(0.0, min(1.0, (top_face_y - f3_y_first) / dy3h))
            f3_y_hr_c = f3_y_first + t_c * dy3h
            f3_z_hr_c = f3_z_first + t_c * (f3_z_last - f3_z_first)
        elements.append(_ifc_handrail_flight_y(ifc, context, "Inner F3 Handrail", f3_inner_x, f3_y_first, f3_z_first, f3_y_hr_c, f3_z_hr_c, **hr_kw))
        elements.append(_ifc_baserail_flight_y(ifc, context, "Inner F3 Baserail", f3_inner_x, f3_y_first, f3_z_first, f3_y_end_c, f3_z_end_c, **br_kw))
        c2_face_f3 = (corner2_y + c2_hp) if f3_y_first > corner2_y else (corner2_y - c2_hp)
        dy3_full = f3_y_last - f3_y_first
        if abs(dy3_full) > 1e-9:
            t_sp3 = (c2_face_f3 - f3_y_first) / dy3_full
            f3_sp_z0 = f3_z_first + t_sp3 * (f3_z_last - f3_z_first)
        else:
            f3_sp_z0 = f3_z_first
        elements.extend(_ifc_spindles_flight_y(ifc, context, "Inner F3 Spindle", f3_inner_x, c2_face_f3, f3_sp_z0, f3_y_hr_c, f3_z_hr_c, **sp_kw))
    elif not render_inner and flight3_treads > 0:
        thresh_back_y = top_post_y - threshold_d
        elements.append(_ifc_stringer_flight_y_notched(
            ifc, context, "Inner F3 Stringer", f3_inner_x, f3_y_first, f3_z_first,
            f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))

    # ─── Flight 3 outer stringer + balustrade ───
    if render_outer and flight3_treads > 0:
        pc_face_f3 = f3_y_first - hp
        top_face_y_out = top_post_y + hp
        # Extend Flight 3 stringer to f2_outer_y - STRINGER_THICKNESS/2 so Flight 2 can overlap        f3_y_first_extended = f2_outer_y - STRINGER_THICKNESS / 2
        f3_y0_oc, f3_z0_oc = f3_y_first, f3_z_first
        f3_y1_oc, f3_z1_oc = f3_y_last, f3_z_last
        if abs(dy3h) > 1e-9:
            # Extend at start (corner 2)
            f3_z_first_extended = f3_z_first - (f3_y_first - f3_y_first_extended) * (f3_z_last - f3_z_first) / dy3h
            f3_y0_oc = f3_y_first_extended
            f3_z0_oc = f3_z_first_extended
            # Trim for balustrade at end
            t_c1 = max(0.0, min(1.0, (top_face_y_out - f3_y_first) / dy3h))
            f3_y1_oc = f3_y_first + t_c1 * dy3h
            f3_z1_oc = f3_z_first + t_c1 * (f3_z_last - f3_z_first)
        elements.append(_ifc_stringer_flight_y(ifc, context, "Outer F3 Stringer", f3_outer_x, f3_y0_oc, f3_z0_oc, f3_y1_oc, f3_z1_oc))
        # Handrail and baserail use trimmed coordinates
        if abs(dy3h) > 1e-9:
            t_c0 = max(0.0, min(1.0, (pc_face_f3 - f3_y_first) / dy3h))
            f3_y0_hr = f3_y_first + t_c0 * dy3h
            f3_z0_hr = f3_z_first + t_c0 * (f3_z_last - f3_z_first)
        else:
            f3_y0_hr = f3_y_first
            f3_z0_hr = f3_z_first
        elements.append(_ifc_handrail_flight_y(ifc, context, "Outer F3 Handrail", f3_outer_x, f3_y0_hr, f3_z0_hr, f3_y1_oc, f3_z1_oc, **hr_kw))
        elements.append(_ifc_baserail_flight_y(ifc, context, "Outer F3 Baserail", f3_outer_x, f3_y0_hr, f3_z0_hr, f3_y1_oc, f3_z1_oc, **br_kw))
        if abs(dy3h) > 1e-9:
            elements.extend(_ifc_spindles_flight_y(ifc, context, "Outer F3 Spindle", f3_outer_x, pc_face_f3, f3_z0_hr, top_face_y_out, f3_z1_oc, **sp_kw))
    elif not render_outer and flight3_treads > 0:
        # Extend Flight 3 stringer to f2_outer_y - STRINGER_THICKNESS/2 so Flight 2 can overlap
        f3_y_first_extended = f2_outer_y - STRINGER_THICKNESS / 2
        f3_z_first_extended = f3_z_first - (f3_y_first - f3_y_first_extended) * (f3_z_last_fl - f3_z_first) / (f3_y_last_fl - f3_y_first) if abs(f3_y_last_fl - f3_y_first) > 1e-9 else f3_z_first
        thresh_back_y = top_post_y - threshold_d
        elements.append(_ifc_stringer_flight_y_notched(
            ifc, context, "Outer F3 Stringer", f3_outer_x, f3_y_first_extended, f3_z_first_extended,
            f3_y_last_fl, f3_z_last_fl, ftf, thresh_back_y, tread_t))

    # ─── Inner newel posts ───
    if render_inner:
        if flight1_treads > 0:
            hr_bot = rise + nzs + hr_rise_val
            bot_h = hr_bot + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Inner Bottom Post", corner1_x, bottom_post_y, ns, bot_h)
            if newel:
                elements.append(newel)
        hr_c1_f1 = (flight1_treads + 1) * rise + nzs + hr_rise_val
        hr_c1_f2 = flight2_riser_start * rise + nzs + hr_rise_val
        c1_h = max(hr_c1_f1, hr_c1_f2) + NEWEL_CAP
        newel = _create_newel_post(ifc, context, "Inner Corner1 Post", corner1_x, corner1_y, c1_ns, c1_h)
        if newel:
            elements.append(newel)
        hr_c2_f2 = (flight2_riser_start + flight2_treads) * rise + nzs + hr_rise_val
        hr_c2_f3 = flight3_riser_start * rise + nzs + hr_rise_val
        c2_h = max(hr_c2_f2, hr_c2_f3) + NEWEL_CAP
        newel = _create_newel_post(ifc, context, "Inner Corner2 Post", corner2_x, corner2_y, c2_ns, c2_h)
        if newel:
            elements.append(newel)
        if flight3_treads > 0:
            hr_top = (flight3_riser_start + flight3_treads) * rise + nzs + hr_rise_val
            top_h = hr_top + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Inner Top Post", corner2_x, top_post_y, ns, top_h)
            if newel:
                elements.append(newel)

    # ─── Outer newel posts ───
    if render_outer:
        outer_x = width - corner1_x
        outer_y_pos = corner1_y + width
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
        f3_y_first_val = flight3_start_y - nosing + riser_t / 2 + flight3_shift_y

        if flight1_treads > 0:
            hr_bot = rise + nzs + hr_rise_val
            bot_h = hr_bot + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Outer Bottom Post", outer_x, bottom_post_y, ns, bot_h)
            if newel:
                elements.append(newel)
        f1_y1_val = flight1_treads * going + flight1_shift_y
        hr_pc1 = (flight1_treads + 1) * rise + nzs + hr_rise_val
        pc1_h = hr_pc1 + NEWEL_CAP
        newel = _create_newel_post(ifc, context, "Outer PC F1 Post", outer_x, f1_y1_val, ns, pc1_h)
        if newel:
            elements.append(newel)

        if actual_winders1 > 0:
            oc1_hr = max(hr_pc1, flight2_riser_start * rise + nzs + hr_rise_val)
            oc1_h = oc1_hr + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Outer Corner1 Post", outer_x, outer_y_pos, ns, oc1_h)
            if newel:
                elements.append(newel)
            hr_pc_f2s = flight2_riser_start * rise + nzs + hr_rise_val
            pc_f2s_h = hr_pc_f2s + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Outer PC F2S Post", f2_x0_val, outer_y_pos, ns, pc_f2s_h)
            if newel:
                elements.append(newel)

        if actual_winders2 > 0:
            hr_pc_f2e = (flight2_riser_start + flight2_treads) * rise + nzs + hr_rise_val
            pc_f2e_h = hr_pc_f2e + NEWEL_CAP
            outer_corner_y2_val = corner2_y + width
            newel = _create_newel_post(ifc, context, "Outer PC F2E Post", f2_x_end_val, outer_corner_y2_val, ns, pc_f2e_h)
            if newel:
                elements.append(newel)
            oc2_hr = max(hr_pc_f2e, flight3_riser_start * rise + nzs + hr_rise_val)
            oc2_h = oc2_hr + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Outer Corner2 Post", f3_outer_x_val, outer_corner_y2_val, ns, oc2_h)
            if newel:
                elements.append(newel)
            hr_pc_f3s = flight3_riser_start * rise + nzs + hr_rise_val
            pc_f3s_h = hr_pc_f3s + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Outer PC F3S Post", f3_outer_x_val, f3_y_first_val, ns, pc_f3s_h)
            if newel:
                elements.append(newel)

        if flight3_treads > 0:
            hr_top = (flight3_riser_start + flight3_treads) * rise + nzs + hr_rise_val
            top_h = hr_top + NEWEL_CAP
            newel = _create_newel_post(ifc, context, "Outer Top Post", f3_outer_x_val, top_post_y, ns, top_h)
            if newel:
                elements.append(newel)


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
# MESH-TO-IFC CONVERTER
# Single source of truth: preview meshes → IFC entities
# ────────────────────────────────────────────────────────────

# IFC class mapping for each ifc_type
_IFC_TYPE_MAP = {
    "tread":        "IfcSlab",
    "riser":        "IfcPlate",
    "winder_tread": "IfcSlab",
    "winder_riser": "IfcPlate",
    "landing":      "IfcSlab",
    "threshold":    "IfcSlab",
    "newel":        "IfcColumn",
    "stringer":     "IfcMember",
    "handrail":     "IfcRailing",
    "baserail":     "IfcRailing",
    "spindle":      "IfcMember",
}


def meshes_to_ifc(meshes):
    """Convert a list of preview mesh dicts into a valid IFC 2x3 file.

    This is the single conversion point — whatever the preview generates,
    the IFC file will contain exactly the same geometry.

    Args:
        meshes: list of mesh dicts from generate_preview_geometry()
    Returns:
        str: path to the generated .ifc file
    """
    ifc = ifcopenshell.api.run("project.create_file", version="IFC2X3")

    # Owner history
    person = ifcopenshell.api.run("owner.add_person", ifc, family_name="User")
    org = ifcopenshell.api.run("owner.add_organisation", ifc,
                               identification="IFC-STAIR",
                               name="IFC Staircase Generator")
    ifcopenshell.api.run("owner.add_person_and_organisation", ifc,
                         person=person, organisation=org)
    app = ifcopenshell.api.run("owner.add_application", ifc,
                               application_developer=org,
                               version="1.0",
                               application_full_name="IFC Staircase Generator",
                               application_identifier="ifc-stair-gen")
    ifcopenshell.api.owner.settings.get_user = lambda f: f.by_type("IfcPersonAndOrganization")[0]
    ifcopenshell.api.owner.settings.get_application = lambda f: f.by_type("IfcApplication")[0]

    # Units (millimetres)
    project = ifcopenshell.api.run("root.create_entity", ifc,
                                   ifc_class="IfcProject", name="Staircase Project")
    ifcopenshell.api.run("unit.assign_unit", ifc,
                         length={"is_metric": True, "raw": "MILLIMETERS"})

    # Geometry context
    ctx = ifcopenshell.api.run("context.add_context", ifc, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", ifc,
                                context_type="Model",
                                context_identifier="Body",
                                target_view="MODEL_VIEW",
                                parent=ctx)

    # Spatial hierarchy
    site = ifcopenshell.api.run("root.create_entity", ifc,
                                ifc_class="IfcSite", name="Default Site")
    building = ifcopenshell.api.run("root.create_entity", ifc,
                                    ifc_class="IfcBuilding", name="Default Building")
    storey = ifcopenshell.api.run("root.create_entity", ifc,
                                  ifc_class="IfcBuildingStorey", name="Ground Floor")
    ifcopenshell.api.run("aggregate.assign_object", ifc,
                         relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", ifc,
                         relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", ifc,
                         relating_object=building, products=[storey])

    # Stair container
    stair = ifcopenshell.api.run("root.create_entity", ifc,
                                 ifc_class="IfcStair", name="Staircase")
    ifcopenshell.api.run("spatial.assign_container", ifc,
                         relating_structure=storey, products=[stair])

    # Convert each mesh to an IFC element
    elements = []
    counter = {}  # for auto-naming: {ifc_type: count}

    for mesh in meshes:
        ifc_type = mesh.get("ifc_type", "")
        mesh_type = mesh.get("type", "")
        name = mesh.get("name", "")

        # Auto-generate name if not provided
        if not name:
            counter[ifc_type] = counter.get(ifc_type, 0) + 1
            ifc_class = _IFC_TYPE_MAP.get(ifc_type, "IfcBuildingElementProxy")
            name = f"{ifc_type.replace('_', ' ').title()} {counter[ifc_type]}"

        ifc_class = _IFC_TYPE_MAP.get(ifc_type, "IfcBuildingElementProxy")

        elem = None
        if mesh_type == "box":
            elem = _convert_box_mesh(ifc, body, mesh, ifc_class, name)
        elif mesh_type == "stringer":
            elem = _convert_stringer_mesh(ifc, body, mesh, ifc_class, name)
        elif mesh_type == "winder_polygon":
            elem = _convert_polygon_mesh(ifc, body, mesh, ifc_class, name)

        if elem:
            elements.append(elem)

    # Aggregate under stair
    if elements:
        ifcopenshell.api.run("aggregate.assign_object", ifc,
                             relating_object=stair, products=elements)

    # Attach StairSmith disclaimer property set to IfcProject (raw entities
    # to avoid pset template lookup which fails in Pyodide/WASM)
    _DISCLAIMER = ("StairSmith \u2014 Preliminary design aid only. "
                   "User must verify all outputs before use.")
    _attach_disclaimer_pset(ifc, project, _DISCLAIMER)

    # Set the Authorization field in the IFC file header
    ifc.wrapped_data.header.file_name.authorization = (
        "User must verify all outputs before use."
    )

    # Write to temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".ifc", delete=False)
    ifc.write(tmp.name)
    return tmp.name


def _convert_box_mesh(ifc, context, mesh, ifc_class, name):
    """Convert a box mesh dict to an IFC element.

    Uses ifc_center/ifc_size (IFC Z-up native coords) to create an
    extruded rectangular profile.
    """
    cx, cy, cz = mesh["ifc_center"]
    w, d, h = mesh["ifc_size"]  # width_x, depth_y, height_z

    # Rectangular profile in XY plane, extruded in Z
    x0 = cx - w / 2.0
    y0 = cy - d / 2.0
    profile = [
        (x0, y0),
        (x0 + w, y0),
        (x0 + w, y0 + d),
        (x0, y0 + d),
    ]
    z_base = cz - h / 2.0

    solid = _create_extruded_solid(ifc, context, profile, h, (0.0, 0.0, z_base))

    element = ifcopenshell.api.run("root.create_entity", ifc,
                                   ifc_class=ifc_class, name=name)
    rep = ifc.createIfcShapeRepresentation(context, "Body", "SweptSolid", [solid])
    prod_rep = ifc.createIfcProductDefinitionShape(None, None, [rep])
    element.Representation = prod_rep

    origin = ifc.createIfcCartesianPoint((0.0, 0.0, 0.0))
    placement = ifc.createIfcAxis2Placement3D(origin, None, None)
    local_placement = ifc.createIfcLocalPlacement(None, placement)
    element.ObjectPlacement = local_placement

    return element


def _convert_stringer_mesh(ifc, context, mesh, ifc_class, name):
    """Convert a stringer-type mesh dict to an IFC element.

    Stringer meshes have a 2D profile extruded along one axis:
    - No 'axis' key: profile in Y-Z plane, extruded in X (use x, thickness)
    - axis='y': profile in X-Z plane, extruded in Y (use y, thickness)
    """
    profile = [(float(pt[0]), float(pt[1])) for pt in mesh["profile"]]
    thickness = float(mesh["thickness"])

    if mesh.get("axis") == "y":
        # X-Z profile extruded in Y
        y_pos = float(mesh["y"])
        return _create_pitched_profile_element_x(
            ifc, context, name, ifc_class, profile, y_pos, thickness)
    else:
        # Y-Z profile extruded in X
        x_pos = float(mesh["x"])
        return _create_pitched_profile_element_y(
            ifc, context, name, ifc_class, profile, x_pos, thickness)


def _convert_polygon_mesh(ifc, context, mesh, ifc_class, name):
    """Convert a winder_polygon mesh dict to an IFC element.

    Profile is in the X-Y plane, extruded in Z from z_base.
    """
    profile = [(float(pt[0]), float(pt[1])) for pt in mesh["profile"]]
    z_base = float(mesh["z"])
    thickness = float(mesh["thickness"])

    solid = _create_extruded_solid(ifc, context, profile, thickness,
                                   (0.0, 0.0, z_base))

    element = ifcopenshell.api.run("root.create_entity", ifc,
                                   ifc_class=ifc_class, name=name)
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
        rise_msg += " — Exceeds recommended maximum of 200mm"
    checks.append({"name": "Individual Rise", "status": rise_status, "message": rise_msg, "value": round(rise, 1)})

    # Individual Going: min 220mm
    going_status = "pass"
    going_msg = f"Individual going: {going:.1f}mm"
    if going < 220:
        going_status = "warn"
        going_msg += " — Below minimum 220mm"
    checks.append({"name": "Individual Going", "status": going_status, "message": going_msg, "value": round(going, 1)})

    # Pitch: max 42° for straight flights
    pitch_rad = math.atan2(rise, going)
    pitch_deg = math.degrees(pitch_rad)
    pitch_status = "pass"
    pitch_msg = f"Pitch: {pitch_deg:.1f}°"
    if pitch_deg > 42:
        pitch_status = "warn"
        pitch_msg += " — Exceeds maximum 42° for private staircase"
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

    return checks
