FeatureScript 3029;
import(path : "onshape/std/geometry.fs", version : "3029.0");
// A thin feature calls the standard library's OWN feature implementation, so the
// modules that define those implementations must be imported explicitly.
import(path : "onshape/std/sketch.fs", version : "3029.0");
import(path : "onshape/std/extrude.fs", version : "3029.0");
import(path : "onshape/std/queryVariable.fs", version : "3029.0");
// A type that appears in a precondition is part of this module's interface, and
// the compiler requires it to be reachable through an export import: a plain
// import makes it reject the feature with
//   "definition.operation: Enum used as parameter type must be exported"
// NewBodyOperationType is declared `export enum` in tool.fs (tool.fs:66), the
// same module extrude.fs re-exports for the same reason.
export import(path : "onshape/std/tool.fs", version : "3029.0");

// ===========================================================================
// Thin native-mirroring features ("薄特征").
//
// These exist because a fat domain feature is not a row a human edits the way a
// native modeling step is. A thin feature contains NO geometry math of its own:
// it exposes a few numbers and calls the SAME standard-library routine Onshape's
// own toolbar feature calls. Verified against the vendored reference:
//
//   extrude.fs       extrude(context, id, definition)
//                    "Create an extrude, as used in Onshape's extrude feature",
//                    with the documented example qSketchRegion(id + "sketch1")
//   sketch.fs        newSketchOnPlane / skRectangle / skSolve
//                    newSketchOnPlane's own example builds the plane from
//                    numbers: plane(vector(0, 0, 0) * inch, vector(0, 0, 1))
//   queryVariable.fs setQueryVariable / getQueryVariable
//
// Two consequences that matter for a human:
//   * the sketch plane is built from numbers, so a thin sketch needs NO visual
//     selection (a picked face is still accepted when a human wants one), and
//   * a thin sketch publishes its region as a query variable, so the next thin
//     feature extrudes exactly that region without re-selecting anything.
// ===========================================================================

export const THIN_SKETCH_REGION_VARIABLE = "thin_sketch_region";

// A bound spec is [min, default, max] -- the SECOND element is the default the
// dialog opens with, not the midpoint of the range. Reusing the size spec for
// the plane origin therefore opened every new sketch at (84, 84, 84) and put the
// geometry nowhere near the origin. Verified live 2026-09-20 by reading the
// inserted row's parameters back: "origin_x": "84 mm", "origin_y": "84 mm",
// "origin_z": "84 mm". The origin gets its own spec whose default is 0.
const THIN_ORIGIN_BOUNDS = { (millimeter) : [-10000, 0, 10000] } as LengthBoundSpec;
const THIN_SIZE_BOUNDS = { (millimeter) : [0.1, 100, 5000] } as LengthBoundSpec;
const THIN_DEPTH_BOUNDS = { (millimeter) : [0.01, 10, 5000] } as LengthBoundSpec;
const THIN_ANGLE_BOUNDS = { (degree) : [0, 0, 89.9] } as AngleBoundSpec;

export enum ThinPlaneAxis
{
    annotation { "Name" : "Z (world XY plane)" }
    Z,
    annotation { "Name" : "X (world YZ plane)" }
    X,
    annotation { "Name" : "Y (world ZX plane)" }
    Y
}

function thinPlaneAxes(axis is ThinPlaneAxis) returns map
{
    // An explicit x axis as well as a normal, because plane(origin, normal)
    // documents "the x-axis ... will be an arbitrary vector perpendicular to the
    // normal", and an arbitrary axis would make the rectangle's orientation
    // unpredictable between regenerations.
    if (axis == ThinPlaneAxis.X)
    {
        return { "normal" : vector(1, 0, 0), "x" : vector(0, 1, 0) };
    }
    if (axis == ThinPlaneAxis.Y)
    {
        return { "normal" : vector(0, 1, 0), "x" : vector(0, 0, 1) };
    }
    return { "normal" : vector(0, 0, 1), "x" : vector(1, 0, 0) };
}

annotation { "Feature Type Name" : "Thin Sketch Rectangle" }
export const thinSketchRectangle = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Face (optional; empty = numeric plane below)", "Filter" : EntityType.FACE && GeometryType.PLANE, "MaxNumberOfPicks" : 1 }
        definition.plane_face is Query;

        annotation { "Name" : "Plane origin X" }
        isLength(definition.origin_x, THIN_ORIGIN_BOUNDS);

        annotation { "Name" : "Plane origin Y" }
        isLength(definition.origin_y, THIN_ORIGIN_BOUNDS);

        annotation { "Name" : "Plane origin Z" }
        isLength(definition.origin_z, THIN_ORIGIN_BOUNDS);

        annotation { "Name" : "Normal axis" }
        definition.axis is ThinPlaneAxis;

        annotation { "Name" : "Width" }
        isLength(definition.width, THIN_SIZE_BOUNDS);

        annotation { "Name" : "Height" }
        isLength(definition.height, THIN_SIZE_BOUNDS);
    }
    {
        const axes = thinPlaneAxes(definition.axis);
        const origin = vector(definition.origin_x, definition.origin_y, definition.origin_z);
        const pickedFace = (definition.plane_face != undefined) && !isQueryEmpty(context, definition.plane_face);
        const sketchPlane = pickedFace
            ? evPlane(context, { "face" : definition.plane_face })
            : plane(origin, axes.normal, axes.x);

        const sketch = newSketchOnPlane(context, id + "sketch", { "sketchPlane" : sketchPlane });
        const halfWidth = definition.width / 2;
        const halfHeight = definition.height / 2;
        skRectangle(sketch, "rectangle", {
                    "firstCorner" : vector(-halfWidth, -halfHeight),
                    "secondCorner" : vector(halfWidth, halfHeight)
                });
        // skSolve is required to generate the sketch geometry even when no
        // constraint had to be solved.
        skSolve(sketch);

        setQueryVariable(context, THIN_SKETCH_REGION_VARIABLE, qSketchRegion(id + "sketch"));
    });

annotation { "Feature Type Name" : "Thin Extrude" }
export const thinExtrude = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Region (optional; empty = the last Thin Sketch Rectangle)", "Filter" : EntityType.FACE, "MaxNumberOfPicks" : 1 }
        definition.region is Query;

        annotation { "Name" : "Depth" }
        isLength(definition.depth, THIN_DEPTH_BOUNDS);

        annotation { "Name" : "Operation" }
        definition.operation is NewBodyOperationType;

        annotation { "Name" : "Opposite direction" }
        definition.opposite is boolean;

        annotation { "Name" : "Draft angle (0 = none)" }
        isAngle(definition.draft_angle, THIN_ANGLE_BOUNDS);
    }
    {
        var region = definition.region;
        if (region == undefined || isQueryEmpty(context, region))
        {
            region = getQueryVariable(context, THIN_SKETCH_REGION_VARIABLE);
        }
        if (region == undefined || isQueryEmpty(context, region))
        {
            throw regenError(
                "Nothing to extrude: pick a region, or add a Thin Sketch Rectangle above this feature first.",
                ["region"]);
        }

        // Built in one expression rather than by adding a key afterwards: a
        // FeatureScript map is assigned to a `const`, and assigning to a field
        // of a const map is rejected ("Cannot assign to constant extrusion").
        // Passing the draft keys unconditionally is safe because extrude.fs
        // declares draftAngle @requiredif{hasDraft is true} (extrude.fs:102) and
        // its own default is hasDraft: false (extrude.fs:410).
        const extrusion = {
            "entities" : region,
            "endBound" : BoundingType.BLIND,
            "depth" : definition.depth,
            "oppositeDirection" : definition.opposite,
            "operationType" : definition.operation,
            "hasDraft" : definition.draft_angle > 0 * degree,
            "draftAngle" : definition.draft_angle
        };
        extrude(context, id + "extrude", extrusion);
    });
