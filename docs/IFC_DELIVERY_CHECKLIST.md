# IFC Delivery Checklist — StairSmith status

Audit of StairSmith's IFC4 export against the Bimvoice 14-point
delivery screening checklist. Updated as of the geometry-voids /
stable-GUID release.

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | Valid IFC model | PASS | buildingSMART validator: STEP syntax, schema and normative rules green; industry-practice warnings BLT003/GRF003 addressed. `ifcopenshell.validate` with EXPRESS rules: 0 issues for all stair types. |
| 2 | Opens in viewers | PASS | Confirmed in BIMvision; every product meshes through the IfcOpenShell geometry kernel (the engine several viewers embed). Worth spot-checking one more viewer per release. |
| 3 | Reasonable file size | PASS | 60–100 KB per staircase. |
| 4 | Clean geometry | PASS | No duplicated or floating elements. Housed joints (treads/risers/newels into stringer boards) are boolean-cut with IfcOpeningElement / IfcRelVoidsElement so no solids overlap. Treads/risers keep their newel cut-outs from the modelling stage. |
| 5 | Correct spatial structure | PASS | IfcProject > IfcSite > IfcBuilding > IfcBuildingStorey via IfcRelAggregates; the stair is contained in the storey via IfcRelContainedInSpatialStructure. (IfcSpace is optional in the IFC4 hierarchy and not meaningful for a component model.) |
| 6 | Correct entity assignment | PASS | IfcStair > IfcStairFlight (treads IfcSlab, risers IfcPlate, stringers IfcMember) + IfcRailing balustrade (members/columns) + IfcSlab landings, per the buildingSMART stair decomposition table. Stair/flight carry PredefinedType (STRAIGHT_RUN / QUARTER_WINDING / HALF_WINDING; STRAIGHT/WINDER). |
| 7 | Property sets populated | PASS | Pset_StairFlightCommon (NumberOfRiser, NumberOfTreads, RiserHeight, TreadLength — derived from the geometry), Pset_StairCommon, StairSmith_Disclaimer on the project. |
| 8 | Relevant, filtered information | PASS | Minimal by construction — no native-tool data exists to leak. |
| 9 | Materials assigned | PASS | IfcMaterial "Timber (softwood)" (category wood) associated to every element and the stair. |
| 10 | Classification references | PASS | Uniclass 2015 on every element: Ss_35_10_85_90 system code plus product codes for treads, risers, stringers, newels, spindles, handrails (verified against the published tables). |
| 11 | Correct units | PASS | Millimetres throughout via IfcSIUnit. |
| 12 | Georeferencing | N/A by design | A catalogue/component model, not a sited asset. Carries a placeholder IfcProjectedCRS + identity IfcMapConversion (satisfies GRF003) explicitly described as not surveyed. The model's plan bounding box corner is normalised to (0, 0). |
| 13 | Stable Global IDs | PASS | Deterministic GUIDs: an element's GUID derives from its name + geometry, so re-exporting the same design reproduces identical GUIDs and unchanged elements keep theirs across small design edits. Spatial containers and relationships derive from the whole-design fingerprint. Verified: two exports of the same design are GUID-identical. |
| 14 | Project information | PASS | IfcProject "StairSmith Staircase", phase "Preliminary design"; application StairSmith; organisation Jake White Architecture; disclaimer in the file header Authorization field and a project pset. No IfcApproval entities — files are explicitly unapproved. |

## Spatial structure references

- IFC spatial composition (project > site > facility > storey > space, with
  site/part/space optional): buildingSMART IFC documentation, "Spatial
  Composition" concept template and IfcBuilding/IfcSite entity definitions.
- Elements relate to exactly one spatial container via
  IfcRelContainedInSpatialStructure; assemblies decompose via
  IfcRelAggregates.
