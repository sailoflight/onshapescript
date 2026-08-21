FeatureScript 3029;
import(path : "onshape/std/geometry.fs", version : "3029.0");

// Module interface verification -- Part A: fixed wall with five trapezoidal rails.
//
// Fidelity-test geometry (no optimisation, no extra features):
//   wall  : 40 (X) x 3.5 (Y) x 40 (Z)
//   rails : run along Z (vertical), centred at X = 4, 12, 20, 28, 36
//   rail  : root width 4.0, top width 1.6, height 1.2, flank angle 45 deg,
//           protruding +Y from the wall face (Y = wallThicknessY)
//   entry : a 1.2 mm long, 45 deg longitudinal ramp at the insertion start end
//           (Z = wallHeightZ). The ramp cuts the rail top from the full rail
//           height 1.2 mm down to the wall face over 1.2 mm of rail length.
//           This is a wedge subtraction along the rail length, NOT an end
//           chamfer and NOT a cross-section reduction.

const WALL_LENGTH_X_BOUNDS = { (millimeter) : [40, 40, 40] } as LengthBoundSpec;
const WALL_HEIGHT_Z_BOUNDS = { (millimeter) : [40, 40, 40] } as LengthBoundSpec;
const WALL_THICKNESS_Y_BOUNDS = { (millimeter) : [3.5, 3.5, 3.5] } as LengthBoundSpec;
const RAIL_COUNT_BOUNDS = { (unitless) : [5, 5, 5] } as IntegerBoundSpec;
const RAIL_FIRST_CENTER_X_BOUNDS = { (millimeter) : [4, 4, 4] } as LengthBoundSpec;
const RAIL_ROOT_WIDTH_BOUNDS = { (millimeter) : [4.0, 4.0, 4.0] } as LengthBoundSpec;
const RAIL_TOP_WIDTH_BOUNDS = { (millimeter) : [1.6, 1.6, 1.6] } as LengthBoundSpec;
const RAIL_HEIGHT_BOUNDS = { (millimeter) : [1.2, 1.2, 1.2] } as LengthBoundSpec;
const RAIL_PITCH_BOUNDS = { (millimeter) : [8.0, 8.0, 8.0] } as LengthBoundSpec;
const RAIL_ANGLE_BOUNDS = { (degree) : [45, 45, 45] } as AngleBoundSpec;
const LEAD_IN_LENGTH_BOUNDS = { (millimeter) : [1.2, 1.2, 1.2] } as LengthBoundSpec;

function railCenterX(definition is map, index is number)
{
    // Explicit centres: first centre 4 mm, pitch 8 mm -> 4, 12, 20, 28, 36.
    return definition.rail_first_center_x + index * definition.rail_pitch;
}

function makeWall(context is Context, id is Id, definition is map) returns Id
{
    const sketchId = id + "wallSketch";
    // Sketch plane (normal +Y, x = +X): local y = cross(+Y, +X) = -Z, so the
    // rectangle spans +Z via a negative local y at its first corner.
    var sketch = newSketchOnPlane(context, sketchId, {
                "sketchPlane" : plane(vector(0, 0, 0) * millimeter, Y_DIRECTION, X_DIRECTION)
            });
    skRectangle(sketch, "wallRect", {
                "firstCorner" : vector(0 * millimeter, -definition.wall_height_z),
                "secondCorner" : vector(definition.wall_length_x, 0 * millimeter)
            });
    skSolve(sketch);

    const extrudeId = id + "wallExtrude";
    opExtrude(context, extrudeId, {
                "entities" : qSketchRegion(sketchId, true),
                "direction" : Y_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.wall_thickness_y
            });
    opDeleteBodies(context, id + "deleteWallSketch", {
                "entities" : qCreatedBy(sketchId, EntityType.BODY)
            });
    return extrudeId;
}

function makeRails(context is Context, id is Id, definition is map) returns Id
{
    const sketchId = id + "railSketch";
    var sketch = newSketchOnPlane(context, sketchId, {
                "sketchPlane" : plane(vector(0, 0, 0) * millimeter, Z_DIRECTION, X_DIRECTION)
            });

    const halfRoot = definition.rail_root_width / 2;
    const halfTop = definition.rail_top_width / 2;
    const baseY = definition.wall_thickness_y;
    const tipY = baseY + definition.rail_height;

    for (var i = 0; i < definition.rail_count; i += 1)
    {
        const cx = railCenterX(definition, i);
        skPolyline(sketch, "rail" ~ i, {
                    "points" : [
                        vector(cx - halfRoot, baseY),
                        vector(cx - halfTop, tipY),
                        vector(cx + halfTop, tipY),
                        vector(cx + halfRoot, baseY),
                        vector(cx - halfRoot, baseY)
                    ]
                });
    }
    skSolve(sketch);

    const extrudeId = id + "railExtrude";
    opExtrude(context, extrudeId, {
                "entities" : qCreatedBy(sketchId, EntityType.FACE),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.wall_height_z
            });
    opDeleteBodies(context, id + "deleteRailSketch", {
                "entities" : qCreatedBy(sketchId, EntityType.BODY)
            });
    return extrudeId;
}

function makeRailLeadInWedges(context is Context, id is Id, definition is map) returns Query
{
    // One wedge per rail. The wedge cross-section is drawn in the Y-Z plane at
    // X = rail centre - rootWidth/2, then extruded +X across the full root
    // width. The right-triangle cross-section (Y, Z):
    //   (wallThicknessY, wallHeightZ) -> (tipY, wallHeightZ - leadInLength) -> (tipY, wallHeightZ)
    // Its hypotenuse is the required 1.2 mm long, 45 deg ramp from the full
    // rail height down to the wall face at the insertion start end.
    const halfRoot = definition.rail_root_width / 2;
    const tipY = definition.wall_thickness_y + definition.rail_height;
    const rampStartZ = definition.wall_height_z - definition.lead_in_length;

    var wedgeBodies = [];
    for (var i = 0; i < definition.rail_count; i += 1)
    {
        const cx = railCenterX(definition, i);
        const sketchId = id + ("leadInSketch" ~ i);
        var sketch = newSketchOnPlane(context, sketchId, {
                    "sketchPlane" : plane(vector(cx - halfRoot, 0, 0) * millimeter, X_DIRECTION, Y_DIRECTION)
                });
        skPolyline(sketch, "wedge" ~ i, {
                    "points" : [
                        vector(definition.wall_thickness_y, definition.wall_height_z),
                        vector(tipY, rampStartZ),
                        vector(tipY, definition.wall_height_z),
                        vector(definition.wall_thickness_y, definition.wall_height_z)
                    ]
                });
        skSolve(sketch);

        const extrudeId = id + ("leadInExtrude" ~ i);
        opExtrude(context, extrudeId, {
                    "entities" : qCreatedBy(sketchId, EntityType.FACE),
                    "direction" : X_DIRECTION,
                    "endBound" : BoundingType.BLIND,
                    "endDepth" : definition.rail_root_width
                });
        opDeleteBodies(context, id + ("deleteLeadInSketch" ~ i), {
                    "entities" : qCreatedBy(sketchId, EntityType.BODY)
                });
        wedgeBodies = append(wedgeBodies, qCreatedBy(extrudeId, EntityType.BODY));
    }
    return qUnion(wedgeBodies);
}

annotation { "Feature Type Name" : "Module rail fixed wall" }
export const moduleRailFixedWall = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Wall length X" }
        isLength(definition.wall_length_x, WALL_LENGTH_X_BOUNDS);

        annotation { "Name" : "Wall height Z" }
        isLength(definition.wall_height_z, WALL_HEIGHT_Z_BOUNDS);

        annotation { "Name" : "Wall thickness Y" }
        isLength(definition.wall_thickness_y, WALL_THICKNESS_Y_BOUNDS);

        annotation { "Name" : "Rail count" }
        isInteger(definition.rail_count, RAIL_COUNT_BOUNDS);

        annotation { "Name" : "Rail first center X" }
        isLength(definition.rail_first_center_x, RAIL_FIRST_CENTER_X_BOUNDS);

        annotation { "Name" : "rail_root_width" }
        isLength(definition.rail_root_width, RAIL_ROOT_WIDTH_BOUNDS);

        annotation { "Name" : "rail_top_width" }
        isLength(definition.rail_top_width, RAIL_TOP_WIDTH_BOUNDS);

        annotation { "Name" : "rail_height" }
        isLength(definition.rail_height, RAIL_HEIGHT_BOUNDS);

        annotation { "Name" : "rail_pitch" }
        isLength(definition.rail_pitch, RAIL_PITCH_BOUNDS);

        annotation { "Name" : "rail_angle" }
        isAngle(definition.rail_angle, RAIL_ANGLE_BOUNDS);

        annotation { "Name" : "Lead-in length" }
        isLength(definition.lead_in_length, LEAD_IN_LENGTH_BOUNDS);
    }
    {
        // 45 deg consistency guard: (root - top) / 2 must equal height * tan(angle).
        const expectedHalfOffset = definition.rail_height * tan(definition.rail_angle);
        const givenHalfOffset = (definition.rail_root_width - definition.rail_top_width) / 2;
        if (abs(givenHalfOffset - expectedHalfOffset) > 1e-6 * millimeter)
            throw regenError("Rail flank angle is inconsistent with root width, top width and height.",
                             ["rail_angle", "rail_root_width", "rail_top_width", "rail_height"]);

        const wallExtrudeId = makeWall(context, id, definition);
        const railExtrudeId = makeRails(context, id, definition);

        // UNION merges abutting/intersecting tools; only `tools` is required
        // (targets is for SUBTRACTION). The wall body is listed first so the
        // merged body keeps the wall identity for later naming.
        const unionId = id + "unionWallRails";
        opBoolean(context, unionId, {
                    "tools" : qUnion([
                        qCreatedBy(wallExtrudeId, EntityType.BODY),
                        qCreatedBy(railExtrudeId, EntityType.BODY)
                    ]),
                    "operationType" : BooleanOperationType.UNION,
                    "keepTools" : false
                });

        // 1.2 mm longitudinal 45 deg entry ramp: subtract one wedge per rail
        // from the merged body (the merged body is still the wall body).
        opBoolean(context, id + "cutRailLeadIn", {
                    "targets" : qCreatedBy(wallExtrudeId, EntityType.BODY),
                    "tools" : makeRailLeadInWedges(context, id, definition),
                    "operationType" : BooleanOperationType.SUBTRACTION,
                    "keepTools" : false
                });

        setProperty(context, {
                    "entities" : qCreatedBy(wallExtrudeId, EntityType.BODY),
                    "propertyType" : PropertyType.NAME,
                    "value" : "Fixed wall (rail)"
                });
    });
