FeatureScript 3029;
import(path : "onshape/std/geometry.fs", version : "3029.0");

// Trophy-style branching cable display stand.
// Coordinate convention:
//   XY = base bottom plane, +Z = up, X = left/right, Y = front/back.
//   The visible front and the blank plaque are on the -Y side.
//   The two discrete S-shaped root rows run mainly along Y.
//   The terminal array runs mainly along X, approximately perpendicular in top view.

const BASE_RADIUS_BOUNDS = { (millimeter) : [32, 39, 50] } as LengthBoundSpec;
const BASE_HEIGHT_BOUNDS = { (millimeter) : [14, 18, 28] } as LengthBoundSpec;
const BASE_FILLET_BOUNDS = { (millimeter) : [0.5, 2.4, 4.5] } as LengthBoundSpec;
const S_CENTER_Y_BOUNDS = { (millimeter) : [-10, -2, 10] } as LengthBoundSpec;
const S_LENGTH_BOUNDS = { (millimeter) : [28, 42, 58] } as LengthBoundSpec;
const S_AMPLITUDE_BOUNDS = { (millimeter) : [3, 7.5, 13] } as LengthBoundSpec;
const ROOT_ROW_SPACING_BOUNDS = { (millimeter) : [2, 5, 10] } as LengthBoundSpec;
const TERMINAL_SPREAD_BOUNDS = { (unitless) : [0.9, 1.22, 1.5] } as RealBoundSpec;
const TERMINAL_HEIGHT_SCALE_BOUNDS = { (unitless) : [0.85, 1.06, 1.25] } as RealBoundSpec;
const STRAND_RADIUS_BOUNDS = { (millimeter) : [0.20, 0.38, 0.48] } as LengthBoundSpec;

const PLAQUE_WIDTH_BOUNDS = { (millimeter) : [14, 20.5, 28] } as LengthBoundSpec;
const PLAQUE_HEIGHT_BOUNDS = { (millimeter) : [4, 6.7, 10] } as LengthBoundSpec;
const PLAQUE_DEPTH_BOUNDS = { (millimeter) : [0.7, 1.2, 1.8] } as LengthBoundSpec;
const TERMINAL_WIDTH_BOUNDS = { (millimeter) : [5, 7.4, 10] } as LengthBoundSpec;
const TERMINAL_DEPTH_BOUNDS = { (millimeter) : [4, 6.0, 8] } as LengthBoundSpec;
const TERMINAL_LENGTH_BOUNDS = { (millimeter) : [3.5, 5.2, 8] } as LengthBoundSpec;
const ROOT_COLLAR_RADIUS_BOUNDS = { (millimeter) : [1.5, 2.2, 3] } as LengthBoundSpec;
const ROOT_COLLAR_HEIGHT_BOUNDS = { (millimeter) : [1.2, 2.2, 4] } as LengthBoundSpec;
const CONNECTOR_RADIUS_BOUNDS = { (millimeter) : [0.8, 1.15, 1.6] } as LengthBoundSpec;
const CONNECTOR_LENGTH_BOUNDS = { (millimeter) : [2, 3.2, 5] } as LengthBoundSpec;

// Format: rawX, endY, rawZ, rootIndex, lateralBend.
// The rootIndex sequence is exactly:
// [0,0,1,2,2,3,4,5,5,6,7,8,8,9,10,10,11].
const TERMINAL_DATA = [
    { "rawX" : -43, "endY" : -4, "rawZ" : 65, "rootIndex" : 0,  "lateralBend" : -8 },
    { "rawX" : -39, "endY" :  2, "rawZ" : 76, "rootIndex" : 0,  "lateralBend" : -7 },
    { "rawX" : -34, "endY" : -3, "rawZ" : 84, "rootIndex" : 1,  "lateralBend" : -6 },
    { "rawX" : -29, "endY" :  4, "rawZ" : 70, "rootIndex" : 2,  "lateralBend" : -5 },
    { "rawX" : -24, "endY" : -2, "rawZ" : 88, "rootIndex" : 2,  "lateralBend" : -4 },
    { "rawX" : -18, "endY" :  3, "rawZ" : 78, "rootIndex" : 3,  "lateralBend" : -3 },
    { "rawX" : -12, "endY" : -4, "rawZ" : 92, "rootIndex" : 4,  "lateralBend" : -3 },
    { "rawX" :  -6, "endY" :  2, "rawZ" : 82, "rootIndex" : 5,  "lateralBend" : -2 },
    { "rawX" :   0, "endY" : -3, "rawZ" : 89, "rootIndex" : 5,  "lateralBend" :  0 },
    { "rawX" :   6, "endY" :  3, "rawZ" : 79, "rootIndex" : 6,  "lateralBend" :  1 },
    { "rawX" :  12, "endY" : -3, "rawZ" : 91, "rootIndex" : 7,  "lateralBend" :  2 },
    { "rawX" :  18, "endY" :  3, "rawZ" : 83, "rootIndex" : 8,  "lateralBend" :  3 },
    { "rawX" :  24, "endY" : -3, "rawZ" : 88, "rootIndex" : 8,  "lateralBend" :  4 },
    { "rawX" :  29, "endY" :  4, "rawZ" : 76, "rootIndex" : 9,  "lateralBend" :  5 },
    { "rawX" :  34, "endY" : -2, "rawZ" : 84, "rootIndex" : 10, "lateralBend" :  6 },
    { "rawX" :  39, "endY" :  3, "rawZ" : 74, "rootIndex" : 10, "lateralBend" :  7 },
    { "rawX" :  43, "endY" : -4, "rawZ" : 65, "rootIndex" : 11, "lateralBend" :  8 }
];

const ROOT_COUNT = 12;
const ROOTS_PER_ROW = 6;
const CABLE_COUNT = 17;

const ROOT_T_VALUES = [-1.0, -0.6, -0.2, 0.2, 0.6, 1.0];
const STRAND_OFFSET_X_MM = [0.00, 0.68, -0.68, 0.00, 0.00, 0.48];
const STRAND_OFFSET_Y_MM = [0.00, 0.00, 0.00, 0.68, -0.68, 0.48];

function mmVector(x is number, y is number, z is number) returns Vector
{
    return vector(x, y, z) * millimeter;
}

function setBodyNameAndAppearance(context is Context, bodies is Query,
                                   bodyName is string, appearance is Color)
{
    setProperty(context, {
                "entities" : bodies,
                "propertyType" : PropertyType.NAME,
                "value" : bodyName
            });
    setProperty(context, {
                "entities" : bodies,
                "propertyType" : PropertyType.APPEARANCE,
                "value" : appearance
            });
}

function baseColor() returns Color
{
    return color(0.025, 0.028, 0.032);
}

function blackCableColor() returns Color
{
    // Deliberately lighter than the base so black strands remain readable
    // against both the stand and Onshape's dark shaded-view background.
    return color(0.070, 0.078, 0.090);
}

function yellowCableColor() returns Color
{
    return color(0.92, 0.53, 0.055);
}

function brassColor() returns Color
{
    return color(0.45, 0.27, 0.075);
}

function ivoryColor() returns Color
{
    return color(0.96, 0.93, 0.82);
}

function normalFrame(axis is Vector) returns map
{
    var xAxis = cross(Z_DIRECTION, axis);
    if (norm(xAxis) < 0.01)
        xAxis = X_DIRECTION;
    xAxis = normalize(xAxis);
    var yAxis = normalize(cross(axis, xAxis));
    return { "x" : xAxis, "y" : yAxis };
}

function rootPosition(definition is map, rootIndex is number) returns Vector
{
    var rowOffset = -definition.rootRowSpacing / 2;
    var inRowIndex = rootIndex;
    if (rootIndex >= ROOTS_PER_ROW)
    {
        rowOffset = definition.rootRowSpacing / 2;
        inRowIndex = rootIndex - ROOTS_PER_ROW;
    }

    const t = ROOT_T_VALUES[inRowIndex];
    const x = definition.sAmplitude * sin(t * 180 * degree) + rowOffset;
    const y = definition.sCenterY + t * definition.sLength / 2;
    const collarBottomZ = definition.baseHeight - 0.2 * millimeter;
    return vector(x, y, collarBottomZ + definition.rootCollarHeight);
}

function sharedRootBranchOffset(cableIndex is number)
{
    if (cableIndex == 0 || cableIndex == 3 || cableIndex == 7 ||
        cableIndex == 11 || cableIndex == 14)
        return -0.45 * millimeter;
    if (cableIndex == 1 || cableIndex == 4 || cableIndex == 8 ||
        cableIndex == 12 || cableIndex == 15)
        return 0.45 * millimeter;
    return 0 * millimeter;
}

function strandOffset(strandIndex is number, frame is map) returns Vector
{
    return frame.x * (STRAND_OFFSET_X_MM[strandIndex] * millimeter) +
           frame.y * (STRAND_OFFSET_Y_MM[strandIndex] * millimeter);
}

function validateDesign(definition is map)
{
    if (definition.edgeFillet >= definition.baseHeight / 2)
        throw regenError("Edge fillet must be less than half the base height.",
                         ["edgeFillet", "baseHeight"]);

    if (definition.plaqueWidth >= definition.baseRadius * 1.6)
        throw regenError("Plaque width is too large for the cylindrical base.",
                         ["plaqueWidth", "baseRadius"]);

    if (definition.plaqueHeight / 2 >= 8 * millimeter ||
        8 * millimeter + definition.plaqueHeight / 2 >= definition.baseHeight)
        throw regenError("Plaque height does not fit around the 8 mm center height.",
                         ["plaqueHeight", "baseHeight"]);

    if (definition.connectorRadius >= definition.terminalWidth / 2 ||
        definition.connectorRadius >= definition.terminalDepth / 2)
        throw regenError("Connector radius must fit inside the terminal rear face.",
                         ["connectorRadius", "terminalWidth", "terminalDepth"]);

    for (var rootIndex = 0; rootIndex < ROOT_COUNT; rootIndex += 1)
    {
        const p = rootPosition(definition, rootIndex);
        const radialDistance = norm(vector(p[0], p[1]));
        if (radialDistance + definition.rootCollarRadius >=
            definition.baseRadius - definition.edgeFillet * 0.35)
            throw regenError("An S-row root collar lies outside the usable base top.",
                             ["sCenterY", "sLength", "sAmplitude",
                              "rootRowSpacing", "rootCollarRadius", "baseRadius"]);
    }
}

function makeBase(context is Context, id is Id, definition is map) returns Id
{
    const sketchId = id + "profile";
    var sketch = newSketchOnPlane(context, sketchId, {
                "sketchPlane" : plane(mmVector(0, 0, 0), Z_DIRECTION, X_DIRECTION)
            });
    skCircle(sketch, "baseCircle", {
                "center" : vector(0, 0) * millimeter,
                "radius" : definition.baseRadius
            });
    skSolve(sketch);

    const extrudeId = id + "extrude";
    opExtrude(context, extrudeId, {
                "entities" : qSketchRegion(sketchId, true),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.baseHeight
            });

    opDeleteBodies(context, id + "deleteProfile", {
                "entities" : qCreatedBy(sketchId, EntityType.BODY)
            });

    // Stable design-intent query: only the start/end cap boundary circles.
    opFillet(context, id + "topBottomFillet", {
                "entities" : qCapEntity(extrudeId, CapType.EITHER, EntityType.EDGE),
                "radius" : definition.edgeFillet,
                "tangentPropagation" : true
            });

    setBodyNameAndAppearance(context,
        qCreatedBy(extrudeId, EntityType.BODY), "base", baseColor());
    return extrudeId;
}

function makePlaque(context is Context, id is Id, definition is map,
                    baseExtrudeId is Id)
{
    const plaqueCenterZ = 8 * millimeter;
    const recessWidth = definition.plaqueWidth + 1.5 * millimeter;
    const recessHeight = definition.plaqueHeight + 1.3 * millimeter;
    const recessDepth = definition.plaqueDepth + 0.8 * millimeter;

    const cutterId = id + "recessCutter";
    fCuboid(context, cutterId, {
                "corner1" : vector(-recessWidth / 2,
                                   -definition.baseRadius - 1 * millimeter,
                                   plaqueCenterZ - recessHeight / 2),
                "corner2" : vector(recessWidth / 2,
                                   -definition.baseRadius + recessDepth,
                                   plaqueCenterZ + recessHeight / 2)
            });

    opBoolean(context, id + "cutRecess", {
                "targets" : qCreatedBy(baseExtrudeId, EntityType.BODY),
                "tools" : qCreatedBy(cutterId, EntityType.BODY),
                "operationType" : BooleanOperationType.SUBTRACTION,
                "keepTools" : false
            });

    // Tangent planar insert: slightly proud at the front and embedded at the rear.
    const insertId = id + "insert";
    fCuboid(context, insertId, {
                "corner1" : vector(-definition.plaqueWidth / 2,
                                   -definition.baseRadius - 0.12 * millimeter,
                                   plaqueCenterZ - definition.plaqueHeight / 2),
                "corner2" : vector(definition.plaqueWidth / 2,
                                   -definition.baseRadius + definition.plaqueDepth + 0.35 * millimeter,
                                   plaqueCenterZ + definition.plaqueHeight / 2)
            });

    setBodyNameAndAppearance(context,
        qCreatedBy(insertId, EntityType.BODY), "plaqueInsert_blank", ivoryColor());
}

function makeRootCollars(context is Context, id is Id, definition is map)
{
    const bottomZ = definition.baseHeight - 0.2 * millimeter;
    for (var rootIndex = 0; rootIndex < ROOT_COUNT; rootIndex += 1)
    {
        const top = rootPosition(definition, rootIndex);
        const cylinderId = id + ("rootCollar" ~ rootIndex);
        fCylinder(context, cylinderId, {
                    "bottomCenter" : vector(top[0], top[1], bottomZ),
                    "topCenter" : top,
                    "radius" : definition.rootCollarRadius
                });
        setBodyNameAndAppearance(context,
            qCreatedBy(cylinderId, EntityType.BODY),
            "rootCollars_" ~ rootIndex, brassColor());
    }
}

function cableSpec(definition is map, cableIndex is number) returns map
{
    const data = TERMINAL_DATA[cableIndex];
    const root = rootPosition(definition, data.rootIndex);
    const terminalCenter = vector(
                data.rawX * definition.terminalSpread * millimeter,
                data.endY * millimeter,
                definition.baseHeight +
                    (data.rawZ - 16) * definition.terminalHeightScale * millimeter);

    // Axis points from the cable toward the terminal. It has a strong upward
    // component but varies with each cable's lateral and fore/aft displacement.
    const axis = normalize(vector(
                (terminalCenter[0] - root[0]) * 0.18,
                (terminalCenter[1] - root[1]) * 0.14,
                18 * millimeter));
    const frame = normalFrame(axis);
    const rearCenter = terminalCenter - axis * (definition.terminalLength / 2);

    var signX = 1;
    if (cableIndex % 2 == 0)
        signX = -1;
    var signY = 1;
    if (cableIndex % 4 < 2)
        signY = -1;

    // The cable enters near a rear-face corner, not at the face center.
    const terminalCorner = rearCenter +
        frame.x * (signX * definition.terminalWidth * 0.304) +
        frame.y * (signY * definition.terminalDepth * 0.275);
    const connectorStart = terminalCorner - axis * definition.connectorLength;

    return {
        "data" : data,
        "root" : root,
        "terminalCenter" : terminalCenter,
        "axis" : axis,
        "frame" : frame,
        "rearCenter" : rearCenter,
        "terminalCorner" : terminalCorner,
        "connectorStart" : connectorStart
    };
}

function makeSweptStrand(context is Context, id is Id, points is array,
                         startDirection is Vector, endDirection is Vector,
                         radius, cableIndex is number, strandIndex is number,
                         makeYellow is boolean)
{
    const pathId = id + "path";
    opFitSpline(context, pathId, {
                "points" : points,
                "startDerivative" : startDirection * (18 * millimeter),
                "endDerivative" : endDirection * (18 * millimeter)
            });

    const profileId = id + "profile";
    const profileFrame = normalFrame(startDirection);
    var profile = newSketchOnPlane(context, profileId, {
                "sketchPlane" : plane(points[0], startDirection, profileFrame.x)
            });
    skCircle(profile, "strandCircle", {
                "center" : vector(0, 0) * millimeter,
                "radius" : radius
            });
    skSolve(profile);

    const sweepId = id + "sweep";
    opSweep(context, sweepId, {
                "profiles" : qSketchRegion(profileId, true),
                "path" : qCreatedBy(pathId, EntityType.EDGE),
                "keepProfileOrientation" : false
            });

    var strandName = "blackStrands_" ~ cableIndex ~ "_" ~ strandIndex;
    var strandColor = baseColor();
    if (makeYellow)
    {
        strandName = "yellowStrands_" ~ cableIndex ~ "_" ~ strandIndex;
        strandColor = yellowCableColor();
    }
    else
    {
        strandColor = blackCableColor();
    }
    setBodyNameAndAppearance(context,
        qCreatedBy(sweepId, EntityType.BODY), strandName, strandColor);

    opDeleteBodies(context, id + "deleteSweepInputs", {
                "entities" : qUnion([
                    qCreatedBy(pathId, EntityType.BODY),
                    qCreatedBy(profileId, EntityType.BODY)
                ])
            });
}

function makeCable(context is Context, id is Id, definition is map,
                   cableIndex is number, spec is map)
{
    const data = spec.data;
    const branch = sharedRootBranchOffset(cableIndex);
    const branchOffset = spec.frame.x * branch;
    const centerStart = spec.root + branchOffset;

    // Pull the lower cable field inward before the terminal fan opens. This
    // creates the dense, intertwined trophy-like cluster seen near the roots.
    // Small deterministic fore/aft offsets keep the spray organic in 3D.
    const organicX = ((cableIndex % 4) - 1.5) * 0.7 * millimeter;
    const organicY = ((cableIndex % 5) - 2) * 0.85 * millimeter;
    const firstControl = centerStart +
        X_DIRECTION * (data.lateralBend * 0.45 * millimeter -
                       centerStart[0] * 0.38 + organicX) +
        Y_DIRECTION * ((spec.terminalCenter[1] - centerStart[1]) * 0.18 -
                       centerStart[1] * 0.26 + organicY) +
        Z_DIRECTION * (13.5 * millimeter);

    const secondControl = spec.connectorStart - spec.axis * (18 * millimeter) +
        X_DIRECTION * (data.lateralBend * 0.18 * millimeter - organicX * 0.55) +
        Y_DIRECTION * (organicY * 0.65);

    if (definition.detailedStrands)
    {
        const count = 4 + cableIndex % 3;
        for (var strandIndex = 0; strandIndex < count; strandIndex += 1)
        {
            const offset = strandOffset(strandIndex, spec.frame);
            const p0 = centerStart + offset;
            const p1 = firstControl + offset;
            const p2 = secondControl + offset * 0.70;
            const p3 = spec.connectorStart + offset * 0.34;
            const startDirection = normalize(p1 - p0);
            const makeYellow = (strandIndex + cableIndex) % 2 == 1;

            makeSweptStrand(context,
                id + ("strand" ~ strandIndex),
                [p0, p1, p2, p3],
                startDirection, spec.axis, definition.strandRadius,
                cableIndex, strandIndex, makeYellow);
        }
    }
    else
    {
        const startDirection = normalize(firstControl - centerStart);
        const makeYellow = cableIndex % 2 == 1;
        makeSweptStrand(context,
            id + "previewCable",
            [centerStart, firstControl, secondControl, spec.connectorStart],
            startDirection, spec.axis, definition.strandRadius * 2.4,
            cableIndex, 0, makeYellow);
    }
}

function makeCornerConnector(context is Context, id is Id, definition is map,
                             cableIndex is number, spec is map)
{
    const connectorId = id + "cornerConnector";
    fCylinder(context, connectorId, {
                "bottomCenter" : spec.connectorStart - spec.axis * (0.15 * millimeter),
                "topCenter" : spec.terminalCorner + spec.axis * (0.25 * millimeter),
                "radius" : definition.connectorRadius
            });
    setBodyNameAndAppearance(context,
        qCreatedBy(connectorId, EntityType.BODY),
        "cornerConnectors_" ~ cableIndex, brassColor());
}

function makeTerminal(context is Context, id is Id, definition is map,
                      cableIndex is number, spec is map)
{
    const profileId = id + "terminalProfile";
    var profile = newSketchOnPlane(context, profileId, {
                "sketchPlane" : plane(spec.rearCenter, spec.axis, spec.frame.x)
            });
    skRectangle(profile, "terminalRectangle", {
                "firstCorner" : vector(-definition.terminalWidth / 2,
                                       -definition.terminalDepth / 2),
                "secondCorner" : vector(definition.terminalWidth / 2,
                                        definition.terminalDepth / 2)
            });
    skSolve(profile);

    const extrudeId = id + "terminalExtrude";
    opExtrude(context, extrudeId, {
                "entities" : qSketchRegion(profileId, true),
                "direction" : spec.axis,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.terminalLength
            });

    opDeleteBodies(context, id + "deleteTerminalProfile", {
                "entities" : qCreatedBy(profileId, EntityType.BODY)
            });

    // Small edge softening only; dimensions guarantee this radius is conservative.
    opFillet(context, id + "terminalEdgeFillet", {
                "entities" : qCreatedBy(extrudeId, EntityType.EDGE),
                "radius" : 0.30 * millimeter,
                "tangentPropagation" : true
            });

    setBodyNameAndAppearance(context,
        qCreatedBy(extrudeId, EntityType.BODY),
        "terminals_" ~ cableIndex, ivoryColor());
}

annotation { "Feature Type Name" : "Branch cable trophy display" }
export const branchCableTrophyDisplay = defineFeature(function(context is Context,
                                                               id is Id,
                                                               definition is map)
    precondition
    {
        annotation { "Name" : "Base radius" }
        isLength(definition.baseRadius, BASE_RADIUS_BOUNDS);

        annotation { "Name" : "Base height" }
        isLength(definition.baseHeight, BASE_HEIGHT_BOUNDS);

        annotation { "Name" : "Edge fillet" }
        isLength(definition.edgeFillet, BASE_FILLET_BOUNDS);

        annotation { "Name" : "S center Y" }
        isLength(definition.sCenterY, S_CENTER_Y_BOUNDS);

        annotation { "Name" : "S length" }
        isLength(definition.sLength, S_LENGTH_BOUNDS);

        annotation { "Name" : "S amplitude" }
        isLength(definition.sAmplitude, S_AMPLITUDE_BOUNDS);

        annotation { "Name" : "Root row spacing" }
        isLength(definition.rootRowSpacing, ROOT_ROW_SPACING_BOUNDS);

        annotation { "Name" : "Terminal spread" }
        isReal(definition.terminalSpread, TERMINAL_SPREAD_BOUNDS);

        annotation { "Name" : "Terminal height scale" }
        isReal(definition.terminalHeightScale, TERMINAL_HEIGHT_SCALE_BOUNDS);

        annotation { "Name" : "Strand radius" }
        isLength(definition.strandRadius, STRAND_RADIUS_BOUNDS);

        annotation { "Name" : "Detailed strands", "Default" : true }
        definition.detailedStrands is boolean;

        annotation { "Name" : "Plaque width" }
        isLength(definition.plaqueWidth, PLAQUE_WIDTH_BOUNDS);

        annotation { "Name" : "Plaque height" }
        isLength(definition.plaqueHeight, PLAQUE_HEIGHT_BOUNDS);

        annotation { "Name" : "Plaque depth" }
        isLength(definition.plaqueDepth, PLAQUE_DEPTH_BOUNDS);

        annotation { "Name" : "Terminal width" }
        isLength(definition.terminalWidth, TERMINAL_WIDTH_BOUNDS);

        annotation { "Name" : "Terminal depth" }
        isLength(definition.terminalDepth, TERMINAL_DEPTH_BOUNDS);

        annotation { "Name" : "Terminal length" }
        isLength(definition.terminalLength, TERMINAL_LENGTH_BOUNDS);

        annotation { "Name" : "Root collar radius" }
        isLength(definition.rootCollarRadius, ROOT_COLLAR_RADIUS_BOUNDS);

        annotation { "Name" : "Root collar height" }
        isLength(definition.rootCollarHeight, ROOT_COLLAR_HEIGHT_BOUNDS);

        annotation { "Name" : "Connector radius" }
        isLength(definition.connectorRadius, CONNECTOR_RADIUS_BOUNDS);

        annotation { "Name" : "Connector length" }
        isLength(definition.connectorLength, CONNECTOR_LENGTH_BOUNDS);
    }
    {
        validateDesign(definition);

        const baseExtrudeId = makeBase(context, id + "base", definition);
        makePlaque(context, id + "plaque", definition, baseExtrudeId);
        makeRootCollars(context, id + "rootCollars", definition);

        // Fixed design constraint: exactly 17 bundles and 17 terminals.
        for (var cableIndex = 0; cableIndex < CABLE_COUNT; cableIndex += 1)
        {
            const spec = cableSpec(definition, cableIndex);
            const cableId = id + ("cable" ~ cableIndex);
            makeCable(context, cableId, definition, cableIndex, spec);
            makeCornerConnector(context, cableId, definition, cableIndex, spec);
            makeTerminal(context, cableId, definition, cableIndex, spec);
        }
    });
