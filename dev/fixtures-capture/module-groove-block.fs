FeatureScript 3029;
import(path : "onshape/std/geometry.fs", version : "3029.0");

// Module interface verification -- Part B: module block with five trapezoidal grooves.
//
// Fidelity-test geometry (do NOT optimise or add any feature):
//   block    : 40 (X) x 6 (Y) x 40 (Z)
//   grooves  : run along Z, centred at X = 4, 12, 20, 28, 36, cut into the
//              face Y = 0 toward +Y
//   groove   : matches the rail cross-section with 0.05 mm single-side
//              clearance on the 45 deg flanks (measured normal to the flank)
//              and a 0.10 mm top non-contact allowance (depth 1.30 vs rail
//              height 1.20). Flank angle stays 45 deg.
//   entry    : 0.5 mm 45 deg chamfer on each groove opening top edge at Z = 40.
//
// Derived groove cross-section (X-Y plane):
//   clearance horizontal component = slopeClearance / sin(45 deg) = 0.0707107 mm
//   groove opening half width      = railRootWidth / 2 + clearanceHoriz
//   groove bottom half width       = openingHalf - grooveDepth * tan(45 deg)
//   -> opening width 4.1414214, bottom width 1.5414214, depth 1.30.
// At the rail-tip depth (1.20) the groove half width equals the rail top half
// width plus the 0.05 mm normal clearance, so the 0.10 mm top allowance is the
// only non-contact gap (rail top at depth 1.20, groove bottom at 1.30).

const BLOCK_LENGTH_X_BOUNDS = { (millimeter) : [40, 40, 40] } as LengthBoundSpec;
const BLOCK_HEIGHT_Z_BOUNDS = { (millimeter) : [40, 40, 40] } as LengthBoundSpec;
const BLOCK_THICKNESS_Y_BOUNDS = { (millimeter) : [6, 6, 6] } as LengthBoundSpec;
const GROOVE_COUNT_BOUNDS = { (unitless) : [5, 5, 5] } as IntegerBoundSpec;
const GROOVE_FIRST_CENTER_X_BOUNDS = { (millimeter) : [4, 4, 4] } as LengthBoundSpec;
const GROOVE_PITCH_X_BOUNDS = { (millimeter) : [8, 8, 8] } as LengthBoundSpec;
const RAIL_ROOT_WIDTH_BOUNDS = { (millimeter) : [4.0, 4.0, 4.0] } as LengthBoundSpec;
const RAIL_TOP_WIDTH_BOUNDS = { (millimeter) : [1.6, 1.6, 1.6] } as LengthBoundSpec;
const RAIL_HEIGHT_BOUNDS = { (millimeter) : [1.2, 1.2, 1.2] } as LengthBoundSpec;
const RAIL_FLANK_ANGLE_BOUNDS = { (degree) : [45, 45, 45] } as AngleBoundSpec;
const SLOPE_CLEARANCE_BOUNDS = { (millimeter) : [0.05, 0.05, 0.05] } as LengthBoundSpec;
const GROOVE_DEPTH_BOUNDS = { (millimeter) : [1.30, 1.30, 1.30] } as LengthBoundSpec;
const GROOVE_ENTRY_CHAMFER_BOUNDS = { (millimeter) : [0.5, 0.5, 0.5] } as LengthBoundSpec;

function grooveCenterX(definition is map, index is number)
{
    return definition.grooveFirstCenterX + index * definition.groovePitchX;
}

function makeBlock(context is Context, id is Id, definition is map) returns Id
{
    const sketchId = id + "blockSketch";
    // Sketch plane (normal +Y, x = +X): local y = cross(+Y, +X) = -Z, so the
    // rectangle spans +Z via a negative local y at its first corner.
    var sketch = newSketchOnPlane(context, sketchId, {
                "sketchPlane" : plane(vector(0, 0, 0) * millimeter, Y_DIRECTION, X_DIRECTION)
            });
    skRectangle(sketch, "blockRect", {
                "firstCorner" : vector(0 * millimeter, -definition.blockHeightZ),
                "secondCorner" : vector(definition.blockLengthX, 0 * millimeter)
            });
    skSolve(sketch);

    const extrudeId = id + "blockExtrude";
    opExtrude(context, extrudeId, {
                "entities" : qSketchRegion(sketchId, true),
                "direction" : Y_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.blockThicknessY
            });
    opDeleteBodies(context, id + "deleteBlockSketch", {
                "entities" : qCreatedBy(sketchId, EntityType.BODY)
            });
    return extrudeId;
}

function makeGrooveCutters(context is Context, id is Id, definition is map,
                           openingHalf is ValueWithUnits, bottomHalf is ValueWithUnits) returns Id
{
    const sketchId = id + "grooveCutterSketch";
    var sketch = newSketchOnPlane(context, sketchId, {
                "sketchPlane" : plane(vector(0, 0, 0) * millimeter, Z_DIRECTION, X_DIRECTION)
            });

    for (var i = 0; i < definition.grooveCount; i += 1)
    {
        const cx = grooveCenterX(definition, i);
        skPolyline(sketch, "groove" ~ i, {
                    "points" : [
                        vector(cx - openingHalf, 0 * millimeter),
                        vector(cx - bottomHalf, definition.grooveDepth),
                        vector(cx + bottomHalf, definition.grooveDepth),
                        vector(cx + openingHalf, 0 * millimeter),
                        vector(cx - openingHalf, 0 * millimeter)
                    ]
                });
    }
    skSolve(sketch);

    const extrudeId = id + "grooveCutterExtrude";
    opExtrude(context, extrudeId, {
                "entities" : qCreatedBy(sketchId, EntityType.FACE),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.blockHeightZ
            });
    opDeleteBodies(context, id + "deleteGrooveCutterSketch", {
                "entities" : qCreatedBy(sketchId, EntityType.BODY)
            });
    return extrudeId;
}

function grooveEntryChamferEdges(context is Context, blockExtrudeId is Id, definition is map,
                                 openingHalf is ValueWithUnits) returns Query
{
    // SUBTRACTION keeps the target (block) body; query that body's edges, not
    // qCreatedBy(cutId) — a boolean feature does not own a new body.
    const edgeQuery = qOwnedByBody(qCreatedBy(blockExtrudeId, EntityType.BODY), EntityType.EDGE);
    var edges = [];
    for (var edge in evaluateQuery(context, edgeQuery))
    {
        const line = evEdgeTangentLine(context, { "edge" : edge, "parameter" : 0.5 });
        const dir = normalize(line.direction);
        const p = line.origin;

        // At the entry end (Z=blockHeightZ) the groove opening is bounded by two
        // 45 deg diagonal flank edges (the "top edges" of the opening) plus a
        // horizontal floor edge at Y=grooveDepth. The opening's very top lies in
        // the Y=0 face as a gap (material removed), so the chamferable opening
        // edges are the two diagonal flanks. Select edges that are diagonal in
        // X-Y (|dx| = |dy| = cos45), inside the opening, and below the face.
        if (abs(dir[2]) > 0.01)
            continue;
        if (abs(abs(dir[0]) - 0.7071067811865476) > 0.02)
            continue;
        if (abs(abs(dir[1]) - 0.7071067811865476) > 0.02)
            continue;
        if (p[1] < -0.05 * millimeter || p[1] > definition.grooveDepth + 0.05 * millimeter)
            continue;
        if (abs(p[2] - definition.blockHeightZ) > 0.05 * millimeter)
            continue;

        var insideOpening = false;
        for (var i = 0; i < definition.grooveCount; i += 1)
        {
            const cx = grooveCenterX(definition, i);
            if (p[0] >= cx - openingHalf - 0.01 * millimeter &&
                p[0] <= cx + openingHalf + 0.01 * millimeter)
            {
                insideOpening = true;
                break;
            }
        }
        if (insideOpening)
            edges = append(edges, edge);
    }
    if (size(edges) == 0)
        return qNothing();
    return qUnion(edges);
}

annotation { "Feature Type Name" : "Module groove block" }
export const moduleGrooveBlock = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Block length X" }
        isLength(definition.blockLengthX, BLOCK_LENGTH_X_BOUNDS);

        annotation { "Name" : "Block height Z" }
        isLength(definition.blockHeightZ, BLOCK_HEIGHT_Z_BOUNDS);

        annotation { "Name" : "Block thickness Y" }
        isLength(definition.blockThicknessY, BLOCK_THICKNESS_Y_BOUNDS);

        annotation { "Name" : "Groove count" }
        isInteger(definition.grooveCount, GROOVE_COUNT_BOUNDS);

        annotation { "Name" : "Groove first center X" }
        isLength(definition.grooveFirstCenterX, GROOVE_FIRST_CENTER_X_BOUNDS);

        annotation { "Name" : "Groove pitch X" }
        isLength(definition.groovePitchX, GROOVE_PITCH_X_BOUNDS);

        annotation { "Name" : "Rail root width" }
        isLength(definition.railRootWidth, RAIL_ROOT_WIDTH_BOUNDS);

        annotation { "Name" : "Rail top width" }
        isLength(definition.railTopWidth, RAIL_TOP_WIDTH_BOUNDS);

        annotation { "Name" : "Rail height" }
        isLength(definition.railHeight, RAIL_HEIGHT_BOUNDS);

        annotation { "Name" : "Rail flank angle" }
        isAngle(definition.railFlankAngle, RAIL_FLANK_ANGLE_BOUNDS);

        annotation { "Name" : "Slope single-side clearance" }
        isLength(definition.slopeClearance, SLOPE_CLEARANCE_BOUNDS);

        annotation { "Name" : "Groove depth" }
        isLength(definition.grooveDepth, GROOVE_DEPTH_BOUNDS);

        annotation { "Name" : "Groove entry chamfer" }
        isLength(definition.grooveEntryChamfer, GROOVE_ENTRY_CHAMFER_BOUNDS);
    }
    {
        // 45 deg consistency guard for the reference rail cross-section.
        const expectedHalfOffset = definition.railHeight * tan(definition.railFlankAngle);
        const givenHalfOffset = (definition.railRootWidth - definition.railTopWidth) / 2;
        if (abs(givenHalfOffset - expectedHalfOffset) > 1e-6 * millimeter)
            throw regenError("Rail flank angle is inconsistent with root width, top width and height.",
                             ["railFlankAngle", "railRootWidth", "railTopWidth", "railHeight"]);

        // Groove cross-section derived from the rail + 0.05 mm normal clearance.
        const clearanceHoriz = definition.slopeClearance / sin(definition.railFlankAngle);
        const openingHalf = definition.railRootWidth / 2 + clearanceHoriz;
        const bottomHalf = openingHalf - definition.grooveDepth * tan(definition.railFlankAngle);
        if (bottomHalf <= 0 * millimeter)
            throw regenError("Groove depth would close the groove cross-section.",
                             ["grooveDepth", "slopeClearance"]);

        const blockExtrudeId = makeBlock(context, id, definition);
        const cutterExtrudeId = makeGrooveCutters(context, id, definition, openingHalf, bottomHalf);

        const cutId = id + "cutGrooves";
        opBoolean(context, cutId, {
                    "targets" : qCreatedBy(blockExtrudeId, EntityType.BODY),
                    "tools" : qCreatedBy(cutterExtrudeId, EntityType.BODY),
                    "operationType" : BooleanOperationType.SUBTRACTION,
                    "keepTools" : false
                });

        opChamfer(context, id + "grooveEntryChamfer", {
                    "entities" : grooveEntryChamferEdges(context, blockExtrudeId, definition, openingHalf),
                    "chamferType" : ChamferType.EQUAL_OFFSETS,
                    "width" : definition.grooveEntryChamfer,
                    "tangentPropagation" : false
                });

        setProperty(context, {
                    "entities" : qCreatedBy(blockExtrudeId, EntityType.BODY),
                    "propertyType" : PropertyType.NAME,
                    "value" : "Module block (groove)"
                });
    });
