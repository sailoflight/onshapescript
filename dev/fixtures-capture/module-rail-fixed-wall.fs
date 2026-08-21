FeatureScript 3029;
import(path : "onshape/std/geometry.fs", version : "3029.0");

// Module interface verification -- Part A: fixed wall with five trapezoidal rails.
//
// Fidelity-test geometry (do NOT optimise or add any feature):
//   wall      : 40 (X) x 3.5 (Y) x 40 (Z)
//   rails     : run along Z, centred at X = 4, 12, 20, 28, 36
//   rail sec  : root width 4.0, top width 1.6, height 1.2, flank angle 45 deg
//               (trapezoid in the X-Y plane; rail protrudes +Y from wall face)
//   entry     : 1.2 mm 45 deg lead-in chamfer at Z = 40 on each rail's free
//               end edges (tip edge + two flank edges; the rail-root edge is
//               deliberately NOT chamfered).
//
// Rail centres are expressed parametrically as firstCentre + i * pitch, which
// reproduces exactly 4, 12, 20, 28, 36 for count = 5.

const WALL_LENGTH_X_BOUNDS = { (millimeter) : [40, 40, 40] } as LengthBoundSpec;
const WALL_HEIGHT_Z_BOUNDS = { (millimeter) : [40, 40, 40] } as LengthBoundSpec;
const WALL_THICKNESS_Y_BOUNDS = { (millimeter) : [3.5, 3.5, 3.5] } as LengthBoundSpec;
const RAIL_COUNT_BOUNDS = { (unitless) : [5, 5, 5] } as IntegerBoundSpec;
const RAIL_FIRST_CENTER_X_BOUNDS = { (millimeter) : [4, 4, 4] } as LengthBoundSpec;
const RAIL_PITCH_X_BOUNDS = { (millimeter) : [8, 8, 8] } as LengthBoundSpec;
const RAIL_ROOT_WIDTH_BOUNDS = { (millimeter) : [4.0, 4.0, 4.0] } as LengthBoundSpec;
const RAIL_TOP_WIDTH_BOUNDS = { (millimeter) : [1.6, 1.6, 1.6] } as LengthBoundSpec;
const RAIL_HEIGHT_BOUNDS = { (millimeter) : [1.2, 1.2, 1.2] } as LengthBoundSpec;
const RAIL_FLANK_ANGLE_BOUNDS = { (degree) : [45, 45, 45] } as AngleBoundSpec;
const RAIL_LEAD_IN_LENGTH_BOUNDS = { (millimeter) : [1.2, 1.2, 1.2] } as LengthBoundSpec;

function railCenterX(definition is map, index is number)
{
    return definition.railFirstCenterX + index * definition.railPitchX;
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
                "firstCorner" : vector(0 * millimeter, -definition.wallHeightZ),
                "secondCorner" : vector(definition.wallLengthX, 0 * millimeter)
            });
    skSolve(sketch);

    const extrudeId = id + "wallExtrude";
    opExtrude(context, extrudeId, {
                "entities" : qSketchRegion(sketchId, true),
                "direction" : Y_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.wallThicknessY
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

    const halfRoot = definition.railRootWidth / 2;
    const halfTop = definition.railTopWidth / 2;
    const baseY = definition.wallThicknessY;
    const tipY = baseY + definition.railHeight;
    // The rail profile includes a rectangular plug below the wall face so the
    // boolean union has real overlap with the wall. After the union the plug
    // is absorbed inside the wall and the protruding geometry keeps the exact
    // spec cross-section (root width at Y = wallThicknessY, height 1.2).
    const plugDepth = 0.5 * millimeter;
    const plugY = baseY - plugDepth;

    for (var i = 0; i < definition.railCount; i += 1)
    {
        const cx = railCenterX(definition, i);
        skPolyline(sketch, "rail" ~ i, {
                    "points" : [
                        vector(cx - halfRoot, plugY),
                        vector(cx - halfRoot, baseY),
                        vector(cx - halfTop, tipY),
                        vector(cx + halfTop, tipY),
                        vector(cx + halfRoot, baseY),
                        vector(cx + halfRoot, plugY),
                        vector(cx - halfRoot, plugY)
                    ]
                });
    }
    skSolve(sketch);

    const extrudeId = id + "railExtrude";
    opExtrude(context, extrudeId, {
                "entities" : qCreatedBy(sketchId, EntityType.FACE),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.wallHeightZ
            });
    opDeleteBodies(context, id + "deleteRailSketch", {
                "entities" : qCreatedBy(sketchId, EntityType.BODY)
            });
    return extrudeId;
}

function railLeadInEdges(context is Context, railExtrudeId is Id, baseY is ValueWithUnits) returns Query
{
    const capFaces = qCapEntity(railExtrudeId, CapType.END, EntityType.FACE);
    var edges = [];
    for (var face in evaluateQuery(context, capFaces))
    {
        for (var edge in evaluateQuery(context, qLoopEdges(face)))
        {
            const line = evEdgeTangentLine(context, { "edge" : edge, "parameter" : 0.5 });
            if (line.origin[1] > baseY + 0.05 * millimeter)
                edges = append(edges, edge);
        }
    }
    if (size(edges) == 0)
        return qNothing();
    return qUnion(edges);
}

annotation { "Feature Type Name" : "Module rail fixed wall" }
export const moduleRailFixedWall = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Wall length X" }
        isLength(definition.wallLengthX, WALL_LENGTH_X_BOUNDS);

        annotation { "Name" : "Wall height Z" }
        isLength(definition.wallHeightZ, WALL_HEIGHT_Z_BOUNDS);

        annotation { "Name" : "Wall thickness Y" }
        isLength(definition.wallThicknessY, WALL_THICKNESS_Y_BOUNDS);

        annotation { "Name" : "Rail count" }
        isInteger(definition.railCount, RAIL_COUNT_BOUNDS);

        annotation { "Name" : "Rail first center X" }
        isLength(definition.railFirstCenterX, RAIL_FIRST_CENTER_X_BOUNDS);

        annotation { "Name" : "Rail pitch X" }
        isLength(definition.railPitchX, RAIL_PITCH_X_BOUNDS);

        annotation { "Name" : "Rail root width" }
        isLength(definition.railRootWidth, RAIL_ROOT_WIDTH_BOUNDS);

        annotation { "Name" : "Rail top width" }
        isLength(definition.railTopWidth, RAIL_TOP_WIDTH_BOUNDS);

        annotation { "Name" : "Rail height" }
        isLength(definition.railHeight, RAIL_HEIGHT_BOUNDS);

        annotation { "Name" : "Rail flank angle" }
        isAngle(definition.railFlankAngle, RAIL_FLANK_ANGLE_BOUNDS);

        annotation { "Name" : "Rail entry lead-in length" }
        isLength(definition.railLeadInLength, RAIL_LEAD_IN_LENGTH_BOUNDS);
    }
    {
        // 45 deg consistency guard: (root - top) / 2 must equal height * tan(angle).
        const expectedHalfOffset = definition.railHeight * tan(definition.railFlankAngle);
        const givenHalfOffset = (definition.railRootWidth - definition.railTopWidth) / 2;
        if (abs(givenHalfOffset - expectedHalfOffset) > 1e-6 * millimeter)
            throw regenError("Rail flank angle is inconsistent with root width, top width and height.",
                             ["railFlankAngle", "railRootWidth", "railTopWidth", "railHeight"]);

        const wallExtrudeId = makeWall(context, id, definition);
        const railExtrudeId = makeRails(context, id, definition);

        opChamfer(context, id + "railLeadIn", {
                    "entities" : railLeadInEdges(context, railExtrudeId, definition.wallThicknessY),
                    "chamferType" : ChamferType.EQUAL_OFFSETS,
                    "width" : definition.railLeadInLength,
                    "tangentPropagation" : false
                });

        const unionId = id + "unionWallRails";
        opBoolean(context, unionId, {
                    "tools" : qUnion([
                        qCreatedBy(wallExtrudeId, EntityType.BODY),
                        qCreatedBy(railExtrudeId, EntityType.BODY)
                    ]),
                    "operationType" : BooleanOperationType.UNION,
                    "keepTools" : false
                });

        // A UNION preserves the identity of the earliest tool body, so the
        // merged body is still owned by the wall extrude — query that body
        // (NOT qCreatedBy(unionId)) when naming the result.
        setProperty(context, {
                    "entities" : qCreatedBy(wallExtrudeId, EntityType.BODY),
                    "propertyType" : PropertyType.NAME,
                    "value" : "Fixed wall (rail)"
                });
    });
