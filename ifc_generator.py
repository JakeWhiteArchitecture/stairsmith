"""
IFC Staircase Generator

Generates valid IFC 2x3 files for straight, single-winder (L-shaped),
and double-winder (U-shaped) staircases using IfcOpenShell.
"""

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.owner.settings
import math
import tempfile
import os


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

