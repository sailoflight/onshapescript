FeatureScript 3029;
import(path : "onshape/std/geometry.fs", version : "3029.0");
// A thin feature calls the standard library's OWN feature implementation, so the
// modules that define those implementations must be imported explicitly.
import(path : "onshape/std/sketch.fs", version : "3029.0");
import(path : "onshape/std/extrude.fs", version : "3029.0");
import(path : "onshape/std/queryVariable.fs", version : "3029.0");
import(path : "onshape/std/feature.fs", version : "3029.0");
import(path : "onshape/std/variable.fs", version : "3029.0");
// A type that appears in a precondition is part of this module's interface, and the
// compiler then requires it to be reachable through an export import: at the first
// live compile a plain import of tool.fs (where tool.fs:66 declares
// `export enum NewBodyOperationType`) made the server reject the feature with
//   "definition.operation: Enum used as parameter type must be exported"
// and it stopped emitting the whole feature ("precondition analysis failed").
// extrude.fs re-exports tool.fs for the same reason.
//
// No parameter in this file is an enum any more -- see the family rule at
// Thin Extrude's `subtract` parameter -- but the export import is kept, because it
// is what makes an enum legal in a precondition here and the rule is easy to
// re-break silently.
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
//   sketch.fs        newSketchOnPlane / skRectangle / skLineSegment / skArc /
//                    skSolve. newSketchOnPlane's own example builds the plane
//                    from numbers: plane(vector(0, 0, 0) * inch, vector(0, 0, 1))
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
const THIN_RADIUS_BOUNDS = { (millimeter) : [0, 0, 2500] } as LengthBoundSpec;
const THIN_PITCH_BOUNDS = { (millimeter) : [0.1, 42, 5000] } as LengthBoundSpec;
const THIN_GRID_BOUNDS = { (unitless) : [1, 1, 50] } as IntegerBoundSpec;
const THIN_DEPTH_BOUNDS = { (millimeter) : [0.01, 10, 5000] } as LengthBoundSpec;
const THIN_ANGLE_BOUNDS = { (degree) : [0, 0, 89.9] } as AngleBoundSpec;
const THIN_FROM_SIDE_BOUNDS = { (millimeter) : [0.1, 8, 2500] } as LengthBoundSpec;
const THIN_DIAMETER_BOUNDS = { (millimeter) : [0.1, 6.5, 2500] } as LengthBoundSpec;
const THIN_HOLES_BOUNDS = { (unitless) : [1, 2, 20] } as IntegerBoundSpec;

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

// The sketch plane for every thin sketch: a picked face when the human picked one,
// otherwise the numeric plane below. Shared so both sketch features place geometry
// the same way.
function thinSketchPlane(context is Context, definition is map) returns Plane
{
    const pickedFace = (definition.plane_face != undefined) && !isQueryEmpty(context, definition.plane_face);
    if (pickedFace)
    {
        return evPlane(context, { "face" : definition.plane_face });
    }
    const axes = thinPlaneAxes(definition.axis);
    const origin = vector(definition.origin_x, definition.origin_y, definition.origin_z);
    return plane(origin, axes.normal, axes.x);
}

// One rectangle, optionally with rounded corners, placed in sketch coordinates
// about `centre`. The corner radius is drawn explicitly because sketch.fs has no
// fillet helper (`grep fillet sketch.fs` is empty; the module's sk* exports are
// only the primitives), so a rounded rectangle is four lines plus four arcs,
// each arc tangent at both ends -- placed exactly, which is why the module's own
// docstring says constraints "are almost always unnecessary".
function thinRectangle(sketch is Sketch, prefix is string, centre is Vector,
                       halfWidth is ValueWithUnits, halfHeight is ValueWithUnits,
                       cornerRadius is ValueWithUnits)
{
    if (cornerRadius <= 0 * millimeter)
    {
        skRectangle(sketch, prefix, {
                    "firstCorner" : centre + vector(-halfWidth, -halfHeight),
                    "secondCorner" : centre + vector(halfWidth, halfHeight)
                });
        return;
    }

    const ax = halfWidth - cornerRadius;
    const ay = halfHeight - cornerRadius;
    // The midpoint of a 45 degree corner arc, i.e. radius * cos(45 deg) on both
    // axes. cos() takes a value with angle units, so this is not a magic number.
    const k = cornerRadius * cos(45 * degree);

    skLineSegment(sketch, prefix ~ "right", {
                "start" : centre + vector(halfWidth, -ay),
                "end" : centre + vector(halfWidth, ay)
            });
    skLineSegment(sketch, prefix ~ "left", {
                "start" : centre + vector(-halfWidth, ay),
                "end" : centre + vector(-halfWidth, -ay)
            });
    skLineSegment(sketch, prefix ~ "top", {
                "start" : centre + vector(ax, halfHeight),
                "end" : centre + vector(-ax, halfHeight)
            });
    skLineSegment(sketch, prefix ~ "bottom", {
                "start" : centre + vector(-ax, -halfHeight),
                "end" : centre + vector(ax, -halfHeight)
            });

    skArc(sketch, prefix ~ "arcNE", {
                "start" : centre + vector(halfWidth, ay),
                "mid" : centre + vector(ax + k, ay + k),
                "end" : centre + vector(ax, halfHeight)
            });
    skArc(sketch, prefix ~ "arcNW", {
                "start" : centre + vector(-ax, halfHeight),
                "mid" : centre + vector(-ax - k, ay + k),
                "end" : centre + vector(-halfWidth, ay)
            });
    skArc(sketch, prefix ~ "arcSW", {
                "start" : centre + vector(-halfWidth, -ay),
                "mid" : centre + vector(-ax - k, -ay - k),
                "end" : centre + vector(-ax, -halfHeight)
            });
    skArc(sketch, prefix ~ "arcSE", {
                "start" : centre + vector(ax, -halfHeight),
                "mid" : centre + vector(ax + k, -ay - k),
                "end" : centre + vector(halfWidth, -ay)
            });
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

        annotation { "Name" : "Grid count X" }
        isInteger(definition.grid_x, THIN_GRID_BOUNDS);

        annotation { "Name" : "Grid count Y" }
        isInteger(definition.grid_y, THIN_GRID_BOUNDS);

        annotation { "Name" : "Cell pitch" }
        isLength(definition.cell_pitch, THIN_PITCH_BOUNDS);

        annotation { "Name" : "Width" }
        isLength(definition.width, THIN_SIZE_BOUNDS);

        annotation { "Name" : "Height" }
        isLength(definition.height, THIN_SIZE_BOUNDS);

        annotation { "Name" : "Corner radius (0 = sharp)" }
        isLength(definition.corner_radius, THIN_RADIUS_BOUNDS);
    }
    {
        const sketch = newSketchOnPlane(context, id + "sketch", {
                    "sketchPlane" : thinSketchPlane(context, definition)
                });
        const halfWidth = definition.width / 2;
        const halfHeight = definition.height / 2;

        // The grid is centred on the plane origin, so an odd count puts a shape
        // at the origin and an even count straddles it -- the same convention a
        // human draws a symmetric pocket layout with.
        const centreX = (definition.grid_x - 1) / 2;
        const centreY = (definition.grid_y - 1) / 2;
        for (var j = 0; j < definition.grid_y; j += 1)
        {
            for (var i = 0; i < definition.grid_x; i += 1)
            {
                const centre = vector((i - centreX) * definition.cell_pitch,
                                      (j - centreY) * definition.cell_pitch);
                thinRectangle(sketch, "shape" ~ j ~ "_" ~ i, centre,
                              halfWidth, halfHeight, definition.corner_radius);
            }
        }

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

        // A boolean, not NewBodyOperationType. Every parameter in this family is a
        // number, a string, or a boolean, because those are the controls the browser
        // dialog mechanism can fill AND read back: an enum control reads back as an
        // empty string (measured — browser_read_feature_parameters returned
        // `"axis": ""` for this file's own ThinPlaneAxis picker), so an enum
        // parameter could be neither set nor verified in one transaction.
        annotation { "Name" : "Cut (subtract) instead of add" }
        definition.subtract is boolean;

        annotation { "Name" : "Opposite direction" }
        definition.opposite is boolean;

        annotation { "Name" : "Draft angle (0 = none)" }
        isAngle(definition.draft_angle, THIN_ANGLE_BOUNDS);

        annotation { "Name" : "Draft inwards" }
        definition.draft_inwards is boolean;
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
        //
        // draftPullDirection is documented at extrude.fs:105 as "false to draft
        // outwards (default), true to draft inwards", so an upward extrude with
        // draft_inwards false widens as it rises.
        const extrusion = {
            "entities" : region,
            "endBound" : BoundingType.BLIND,
            "depth" : definition.depth,
            "oppositeDirection" : definition.opposite,
            "operationType" : definition.subtract
                ? NewBodyOperationType.REMOVE
                : NewBodyOperationType.NEW,
            // The documented native default ("true to merge with all other bodies",
            // extrude.fs:145), stated rather than implied. The heuristic that fills a
            // merge scope in the UI, booleanStepEditLogicAnalysis
            // (booleanHeuristics.fs:28), runs only for a human edit -- a programmatic
            // call gets no such help, so a remove with an unresolved scope would be
            // decided somewhere this file cannot see.
            "defaultScope" : true,
            "hasDraft" : definition.draft_angle > 0 * degree,
            "draftAngle" : definition.draft_angle,
            "draftPullDirection" : definition.draft_inwards
        };
        extrude(context, id + "extrude", extrusion);
    });

annotation { "Feature Type Name" : "Thin Sketch Circle" }
export const thinSketchCircle = defineFeature(function(context is Context, id is Id, definition is map)
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

        annotation { "Name" : "Grid count X" }
        isInteger(definition.grid_x, THIN_GRID_BOUNDS);

        annotation { "Name" : "Grid count Y" }
        isInteger(definition.grid_y, THIN_GRID_BOUNDS);

        annotation { "Name" : "Cell pitch" }
        isLength(definition.cell_pitch, THIN_PITCH_BOUNDS);

        annotation { "Name" : "Holes per cell X" }
        isInteger(definition.holes_x, THIN_HOLES_BOUNDS);

        annotation { "Name" : "Holes per cell Y" }
        isInteger(definition.holes_y, THIN_HOLES_BOUNDS);

        annotation { "Name" : "Hole centre from cell side" }
        isLength(definition.hole_from_side, THIN_FROM_SIDE_BOUNDS);

        annotation { "Name" : "Diameter" }
        isLength(definition.diameter, THIN_DIAMETER_BOUNDS);
    }
    {
        const sketch = newSketchOnPlane(context, id + "sketch", {
                    "sketchPlane" : thinSketchPlane(context, definition)
                });

        // A cell's holes are placed from the CELL SIDE, not from its centre, because
        // that is how the layout is specified: the distance between a hole centre and
        // the nearest cell edge. The centre-to-hole distance is therefore
        // pitch / 2 - from_side, and the spacing between two holes in one cell is
        // twice that.
        const inset = definition.cell_pitch / 2 - definition.hole_from_side;
        if (inset <= 0 * millimeter)
        {
            throw regenError(
                "Hole centre from cell side must be less than half the cell pitch (inset " ~
                (inset / millimeter) ~ " mm)",
                ["hole_from_side"]);
        }
        const spacing = 2 * inset;
        const radius = definition.diameter / 2;
        const centreX = (definition.grid_x - 1) / 2;
        const centreY = (definition.grid_y - 1) / 2;
        const holeCentreX = (definition.holes_x - 1) / 2;
        const holeCentreY = (definition.holes_y - 1) / 2;

        for (var j = 0; j < definition.grid_y; j += 1)
        {
            for (var i = 0; i < definition.grid_x; i += 1)
            {
                const cell = vector((i - centreX) * definition.cell_pitch,
                                    (j - centreY) * definition.cell_pitch);
                for (var hy = 0; hy < definition.holes_y; hy += 1)
                {
                    for (var hx = 0; hx < definition.holes_x; hx += 1)
                    {
                        skCircle(sketch, "hole" ~ j ~ "_" ~ i ~ "_" ~ hy ~ "_" ~ hx, {
                                    "center" : cell + vector((hx - holeCentreX) * spacing,
                                                             (hy - holeCentreY) * spacing),
                                    "radius" : radius
                                });
                    }
                }
            }
        }

        skSolve(sketch);

        setQueryVariable(context, THIN_SKETCH_REGION_VARIABLE, qSketchRegion(id + "sketch"));
    });

// ===========================================================================
// Thin Variable ("薄变量"): the row that lets every later row cite a number
// instead of repeating it, so a human changes the cell pitch once.
//
// This one is a thin feature in the strictest sense available: Onshape's OWN
// Variable feature is already nothing but a wrapper, so there is no geometry to
// mirror. variable.fs:825 publishVariableValue is that feature's publisher, and
// its body is exactly
//     setVariable(context, name, value, description);
//     setFeatureComputedParameter(context, id, { "name" : "value", "value" : ... });
// which is the whole of this body. Two consequences:
//   * a variable set here IS the document variable a later feature's field cites
//     as `#name` (context.fs:setVariable -- "Attach a variable to the context,
//     which can be retrieved by another feature defined later"), and
//   * the computed parameter is what makes the Feature List row read
//     `gf_pitch = 42 mm`, because variable.fs:156 hands the NATIVE feature the
//     same "Feature Name Template" : "###name = #value".
//
// variable.fs:810 verifyVariableName is the native validation: a name must be an
// identifier and must not already be a query variable. Reusing it keeps the
// error text the user already knows from the native feature.
// ===========================================================================

// A variable's value is a quantity here, so its default is 0 and it needs the
// origin-style symmetric spec rather than a size spec (see the bound-spec note
// above: the second element is the dialog default).
export const THIN_VARIABLE_BOUNDS = { (millimeter) : [-1000000, 0, 1000000] } as LengthBoundSpec;

// The row template carries the DESCRIPTION as well as the value. `#description` is a
// string parameter, and variable.fs's own Tooltip Template -- "###name = #value
// #description" (variable.fs:157) -- is the standard-library precedent for rendering
// it. The description is the ONLY slot in this family that may hold non-ASCII text (an
// `annotation { "Name" }` containing a Chinese character kills the whole feature:
// "Invalid character in 'Name' annotation: only printable ASCII allowed"), so putting
// it in the row is what makes the Chinese visible in the Feature List itself rather
// than only inside the feature dialog. The template is applied when a feature is
// CREATED: measured live 2026-09-21, editing this annotation afterwards does NOT
// relabel rows that are already inserted -- each such row keeps the name it was born
// with, and only features inserted after the edit render the new template. Visible
// Chinese therefore requires re-insertion, which is why the Chinese plate was rebuilt
// from scratch (see onshape_docs/verification/thin-feature-chinese-ui-2026-09-21.md).
annotation { "Feature Type Name" : "Thin Variable", "Feature Name Template" : "###name = #value #description" }
export const thinVariable = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Name", "MaxLength" : 10000 }
        definition.name is string;

        annotation { "Name" : "Value" }
        isLength(definition.value, THIN_VARIABLE_BOUNDS);

        annotation { "Name" : "Description" }
        definition.description is string;
    }
    {
        verifyVariableName(context, definition.name, "name");
        setVariable(context, definition.name, definition.value,
                    (definition.description is string) ? definition.description : "");
        setFeatureComputedParameter(context, id, { "name" : "value", "value" : definition.value });
    });
