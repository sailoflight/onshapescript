FeatureScript 3029;
import(path : "onshape/std/geometry.fs", version : "3029.0");

// ============================================================================
// Gridfinity baseplate, 2 x 2 (parametric), as three custom features that read
// like a native modeling history:
//
//   GF Base Plate Body    plate body      -- rounded rectangle, extruded to full height
//   GF Socket Pockets     socket pockets  -- per-cell socket cut, 45 deg profile
//   GF Magnet Holes       magnet holes    -- 4 x blind hole per cell, under the socket floor
//
// Geometry authority (community standard, not invented here):
//   https://gridfinity.xyz/specification/
//   kennetek/gridfinity-rebuilt-openscad
//     src/core/standard.scad            GRID_DIMENSIONS_MM, magnet/screw constants
//     src/core/gridfinity-baseplate.scad BASEPLATE_*, _BASEPLATE_PROFILE
//
// Spec numbers used below, with their source lines:
//   GRID_DIMENSIONS_MM      = 42            standard.scad:15
//   BASEPLATE_DIMENSIONS    = 42 x 42       gridfinity-baseplate.scad:19
//   BASEPLATE_HEIGHT        = 5             gridfinity-baseplate.scad:26  (socket layer)
//   BASEPLATE_OUTER_DIAMETER= 8  (R4)       gridfinity-baseplate.scad:31
//   _BASEPLATE_PROFILE      = [[0,0],[0.7,0.7],[0.7,2.5],[2.85,4.65]]
//                                           gridfinity-baseplate.scad:38
//   BASEPLATE_INNER_RADIUS  = 4 - 2.85 = 1.15
//                                           gridfinity-baseplate.scad:59
//   MAGNET_HOLE_RADIUS      = 6.5 / 2       standard.scad:28
//   MAGNET_HOLE_DEPTH       = 2 + 2*0.2 = 2.4
//                                           standard.scad:25,29
//   d_hole_from_side        = 8             standard.scad:32
//   CHAMFER_ADDITIONAL_RADIUS = 0.8         standard.scad:53
//
// The spec profile, translated by (BASEPLATE_INNER_RADIUS, clearance=0.35), is
// swept around a SHARP 34 x 34 wire (gridfinity-baseplate.scad:124,
// `inner_dimensions = size - BASEPLATE_OUTER_DIAMETER`):
//
//   (offset, z) = (1.15, 0.35) -> (1.85, 1.05) -> (1.85, 2.85) -> (4.00, 5.00)
//
// so at height z the socket is the wire DILATED by the profile offset o(z): a
// rounded square of half-extent wireHalf + o(z) and corner radius o(z). Its
// widest point, the top opening, is therefore wireHalf + 4.00 = 21.00, exactly
// half a cell -- neighbouring sockets meet in a knife edge -- and its top corner
// radius is 4.00, exactly the plate's own outer corner radius, so the outer
// sockets' corner arcs are concentric with the plate's rounded corner.
//
// The dilation of a square by o is exactly: the square itself, one bar of width
// o on each of the four sides, and four corner discs of radius o centred ON the
// square's corners (not at half-extent - o, and with radius o rather than
// o + something). The cutter therefore decomposes exactly into
//
//   one constant wire prism    (half-extent wireHalf)
//   + four corner stacks       (cylinder, 45 deg cone, cylinder, 45 deg cone)
//   + eight side bars          (four cuboids, four 45 deg drafted cuboids)
//
// which is why this file needs no sketch, no arc and no loft: fCuboid,
// fCylinder, fCone and one neutral-plane opDraft reproduce the spec exactly.
// The plate body is built the same way: two cross bars plus four corner
// cylinders, so its rounded rectangle has no sketch either.
//
// IMPORTANT design consequence, from the spec geometry itself: in a bare 5 mm
// plate the plate is void from z = 0 to z = 5 at every magnet-hole position
// (a hole sits 8 mm from two cell sides, i.e. 13 mm from the cell centre, which
// is inside the 36.3 mm wide socket opening at the bottom). A magnet hole
// therefore needs material BELOW the socket layer, which is why
//   gridfinity-rebuilt-openscad places the plate cutter at
//   `translate([0,0,additional_height+TOLLERANCE])` (top.scad:175) and the
//   magnet hole at the same additional_height (top.scad:185) -- the socket layer
//   is the TOP 5 mm (`calculate_offset(style_plate=3)` = 6.75 mm base block,
//   top.scad:223).
// This file keeps that structure and exposes the base block as a parameter.
// ============================================================================

// ---- spec constants and parameter bounds [default, min, max] ----

const GF_GRID_BOUNDS = { (unitless) : [1, 2, 30] } as IntegerBoundSpec;
const GF_PITCH_BOUNDS = { (millimeter) : [20, 42, 100] } as LengthBoundSpec;
const GF_SOCKET_LAYER_BOUNDS = { (millimeter) : [2, 5, 30] } as LengthBoundSpec;
const GF_BASE_BLOCK_BOUNDS = { (millimeter) : [0, 5, 60] } as LengthBoundSpec;
const GF_OUTER_RADIUS_BOUNDS = { (millimeter) : [0, 4, 20] } as LengthBoundSpec;
const GF_SOCKET_BOTTOM_BOUNDS = { (millimeter) : [20, 36.3, 120] } as LengthBoundSpec;
const GF_SOCKET_BOTTOM_RADIUS_BOUNDS = { (millimeter) : [0.05, 2.3, 20] } as LengthBoundSpec;
const GF_CLEARANCE_BOUNDS = { (millimeter) : [0.01, 0.35, 10] } as LengthBoundSpec;
const GF_RAMP_BOUNDS = { (millimeter) : [0.01, 0.7, 20] } as LengthBoundSpec;
const GF_LOCK_BOUNDS = { (millimeter) : [0.01, 1.8, 30] } as LengthBoundSpec;
const GF_MAGNET_DIAMETER_BOUNDS = { (millimeter) : [0.1, 6.5, 40] } as LengthBoundSpec;
const GF_MAGNET_DEPTH_BOUNDS = { (millimeter) : [0.1, 2.4, 30] } as LengthBoundSpec;
const GF_MAGNET_SIDE_BOUNDS = { (millimeter) : [0.1, 8, 30] } as LengthBoundSpec;
const GF_MAGNET_CHAMFER_BOUNDS = { (millimeter) : [0, 0.8, 5] } as LengthBoundSpec;

const GF_ZERO = 0 * millimeter;
const GF_BASEPLATE_OUTER_DIAMETER = 8 * millimeter;

// ---------------------------------------------------------------------------
// Model-derived inputs. The two cut features do not ask the user to repeat the
// grid: they read the plate the previous feature produced, so changing the grid
// in the first feature propagates down the tree.
// ---------------------------------------------------------------------------

function gfPlateBox(context is Context) returns Box3d
{
    // qEverything(EntityType.BODY) is NOT "every part": EntityType.BODY is
    // documented as "a solid, surface, wire, or point body", so it also matches
    // the Part Studio's default geometry (the default planes are sheet bodies).
    // Measured live 2026-09-20: the box of that query on an 84 mm 2x2 plate came
    // back 150 mm wide, which made the derived cell count 3.57 and failed the
    // feature. The reference states the query for every PART in a Part Studio is
    // qBodyType(qEverything(EntityType.BODY), BodyType.SOLID); that is what is
    // used here and for every boolean target below.
    return evBox3d(context, {
                "topology" : gfSolidBodies(),
                "tight" : true
            });
}

function gfSolidBodies() returns Query
{
    return qBodyType(qEverything(EntityType.BODY), BodyType.SOLID);
}

function gfMillimeters(value is ValueWithUnits) returns number
{
    return value / millimeter;
}

function gfCellCount(span is ValueWithUnits, pitch is ValueWithUnits, label is string) returns number
{
    // The count is recovered by rounding. The tolerance is deliberately loose
    // (one millimetre of span, not a fraction of the pitch): the tight bounding
    // box of a body with a rounded corner still carries a small round-off, and
    // a tight gate rejects a correct plate. The measured span, pitch and ratio
    // are reported, so a real mismatch is diagnosable from the error text alone.
    const ratio = span / pitch;
    const cellCount = round(ratio);
    const tolerance = (1 * millimeter) / pitch;
    if (cellCount < 1 || abs(ratio - cellCount) > tolerance)
    {
        throw regenError(
            label ~ " is not an integer multiple of the cell pitch (span " ~ gfMillimeters(span) ~
            " mm, pitch " ~ gfMillimeters(pitch) ~ " mm, ratio " ~ ratio ~ ")",
            ["cell_pitch"]);
    }
    return cellCount;
}

// ===========================================================================
// 1. Plate body: rounded rectangle extruded to (socket layer + base block).
// ===========================================================================

annotation { "Feature Type Name" : "GF Base Plate Body" }
export const gfBasePlate = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Grid count X" }
        isInteger(definition.grid_x, GF_GRID_BOUNDS);

        annotation { "Name" : "Grid count Y" }
        isInteger(definition.grid_y, GF_GRID_BOUNDS);

        annotation { "Name" : "Cell pitch" }
        isLength(definition.cell_pitch, GF_PITCH_BOUNDS);

        annotation { "Name" : "Socket layer height" }
        isLength(definition.socket_layer_height, GF_SOCKET_LAYER_BOUNDS);

        annotation { "Name" : "Base block height" }
        isLength(definition.base_block_height, GF_BASE_BLOCK_BOUNDS);

        annotation { "Name" : "Outer corner radius" }
        isLength(definition.outer_radius, GF_OUTER_RADIUS_BOUNDS);
    }
    {
        const plateWidth = definition.grid_x * definition.cell_pitch;
        const plateDepth = definition.grid_y * definition.cell_pitch;
        const totalHeight = definition.socket_layer_height + definition.base_block_height;
        const halfWidth = plateWidth / 2;
        const halfDepth = plateDepth / 2;
        const halfBarX = halfWidth - definition.outer_radius;
        const halfBarY = halfDepth - definition.outer_radius;
        const smallestBar = (halfBarX < halfBarY) ? halfBarX : halfBarY;

        if (smallestBar <= GF_ZERO)
        {
            throw regenError("Outer corner radius must not exceed half the plate size", ["outer_radius"]);
        }

        // Rounded rectangle = TWO cross bars + four corner cylinders, so the
        // outer corner radius is exactly the parameter (no sketch, no fillet).
        //
        // Measured live 2026-09-20 on the exported STL: the earlier version used
        // a single bar of half-extent (half - radius), which is a square with
        // four round EARS rather than a rounded rectangle. Its bottom-face area
        // was 5926.7 mm^2 instead of 7056 - 1129.1 = 5926.9 mm^2, where
        // 4 * (16 - 4 * pi) = 1129.1 mm^2 is exactly the four missing side
        // strips, and the model visible in Onshape showed a 76 x 76 square whose
        // material reached x = 42 only beside the corners -- the protruding
        // corner bosses (with the magnet-hole counterbores on top of them) that
        // started this investigation.
        fCuboid(context, id + "plateBarX", {
                    "corner1" : vector(-halfWidth, -halfBarY, GF_ZERO),
                    "corner2" : vector(halfWidth, halfBarY, totalHeight)
                });
        fCuboid(context, id + "plateBarY", {
                    "corner1" : vector(-halfBarX, -halfDepth, GF_ZERO),
                    "corner2" : vector(halfBarX, halfDepth, totalHeight)
                });

        var pieces = qUnion([qCreatedBy(id + "plateBarX", EntityType.BODY),
                             qCreatedBy(id + "plateBarY", EntityType.BODY)]);
        for (var i = 0; i < 4; i += 1)
        {
            const signX = (i < 2) ? 1 : -1;
            const signY = ((i % 2) == 0) ? 1 : -1;
            const cornerId = id + ("corner" ~ i);
            fCylinder(context, cornerId, {
                        "bottomCenter" : vector(signX * halfBarX, signY * halfBarY, GF_ZERO),
                        "topCenter" : vector(signX * halfBarX, signY * halfBarY, totalHeight),
                        "radius" : definition.outer_radius
                    });
            pieces = qUnion([pieces, qCreatedBy(cornerId, EntityType.BODY)]);
        }

        opBoolean(context, id + "fusePlate", {
                    "tools" : pieces,
                    "operationType" : BooleanOperationType.UNION
                });

        setProperty(context, {
                    "entities" : qCreatedBy(id, EntityType.BODY),
                    "propertyType" : PropertyType.NAME,
                    "value" : "Gridfinity baseplate " ~ definition.grid_x ~ "x" ~ definition.grid_y
                });
    });

// ===========================================================================
// 2. Socket pockets: the spec profile, cut once per cell.
// ===========================================================================

annotation { "Feature Type Name" : "GF Socket Pockets" }
export const gfSocketPockets = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Cell pitch" }
        isLength(definition.cell_pitch, GF_PITCH_BOUNDS);

        annotation { "Name" : "Socket layer height" }
        isLength(definition.socket_layer_height, GF_SOCKET_LAYER_BOUNDS);

        annotation { "Name" : "Base block height" }
        isLength(definition.base_block_height, GF_BASE_BLOCK_BOUNDS);

        annotation { "Name" : "Socket bottom size" }
        isLength(definition.socket_bottom_size, GF_SOCKET_BOTTOM_BOUNDS);

        annotation { "Name" : "Socket bottom radius" }
        isLength(definition.socket_bottom_radius, GF_SOCKET_BOTTOM_RADIUS_BOUNDS);

        annotation { "Name" : "Clearance height" }
        isLength(definition.clearance_height, GF_CLEARANCE_BOUNDS);

        annotation { "Name" : "Ramp height (45 deg)" }
        isLength(definition.ramp_height, GF_RAMP_BOUNDS);

        annotation { "Name" : "Lock face height" }
        isLength(definition.lock_height, GF_LOCK_BOUNDS);
    }
    {
        const plateBox = gfPlateBox(context);
        const spanX = plateBox.maxCorner[0] - plateBox.minCorner[0];
        const spanY = plateBox.maxCorner[1] - plateBox.minCorner[1];
        const gridX = gfCellCount(spanX, definition.cell_pitch, "Plate width");
        const gridY = gfCellCount(spanY, definition.cell_pitch, "Plate depth");

        // Cell centres are taken from the box CENTRE, not from minCorner: the
        // box of this symmetric body is symmetric even when its extents carry
        // round-off, so its centre is exact and the round-off cancels.
        const plateCentreX = (plateBox.minCorner[0] + plateBox.maxCorner[0]) / 2;
        const plateCentreY = (plateBox.minCorner[1] + plateBox.maxCorner[1]) / 2;
        const firstCellX = plateCentreX - (gridX - 1) * definition.cell_pitch / 2;
        const firstCellY = plateCentreY - (gridY - 1) * definition.cell_pitch / 2;

        // Spec cutter wire: the (pitch - 8) square the profile is swept around
        // (gridfinity-baseplate.scad:124). It is SHARP -- the 1.15 mm rounding
        // of the reference's inner boundary reappears below as the first profile
        // offset, which is what puts the top corner radius at exactly 4.00 mm
        // (the plate's own corner radius) instead of adding to it.
        const wireHalf = (definition.cell_pitch - GF_BASEPLATE_OUTER_DIAMETER) / 2;
        const offsetBottom = definition.socket_bottom_size / 2 - wireHalf;
        const offsetMid = offsetBottom + definition.ramp_height;

        if (offsetBottom <= 0 * millimeter)
        {
            throw regenError("Socket bottom size must be larger than the spec wire (cell pitch - 8)", ["socket_bottom_size"]);
        }

        // The reference derives its inner-boundary rounding as
        // BASEPLATE_INNER_RADIUS = OUTER_RADIUS - PROFILE[3].x = 1.15
        // (gridfinity-baseplate.scad:59), and that value IS the first profile
        // offset, so the two socket parameters are not independent: the bottom
        // opening and its corner radius must describe the same rounded square.
        // Checking the relation here keeps a half-edited parameter set from
        // silently producing a socket that does not match the spec.
        const innerRadius = definition.socket_bottom_radius - offsetBottom;
        if (abs(gfMillimeters(innerRadius) - gfMillimeters(offsetBottom)) > 0.001)
        {
            throw regenError("Socket bottom radius must be twice the profile offset (" ~
                             (2 * gfMillimeters(offsetBottom)) ~ " mm), because the bottom opening already fixes that offset",
                             ["socket_bottom_radius"]);
        }
        if (definition.base_block_height <= GF_ZERO)
        {
            throw regenError("Base block height must be greater than 0", ["base_block_height"]);
        }

        // Socket layer sits on top of the base block, exactly as the reference
        // implementation places its cutter (top.scad:175).
        const zFloor = definition.base_block_height;
        const zBottom = zFloor + definition.clearance_height;
        const zMid = zBottom + definition.ramp_height;
        const zLock = zMid + definition.lock_height;
        const zTop = zFloor + definition.socket_layer_height;
        const offsetTop = offsetMid + (zTop - zLock);

        if (zTop <= zLock)
        {
            throw regenError("Socket layer height must exceed clearance + ramp + lock face heights", ["socket_layer_height"]);
        }

        // First cell centre, from the (exact) centre of the plate box.
        const centreX = firstCellX;
        const centreY = firstCellY;

        // 1. The wire prism: constant through the whole socket layer. The
        //    dilation of the wire by any positive offset contains the wire, so
        //    this prism is the exact constant core of every band.
        fCuboid(context, id + "socketCore", {
                    "corner1" : vector(centreX - wireHalf, centreY - wireHalf, zFloor),
                    "corner2" : vector(centreX + wireHalf, centreY + wireHalf, zTop)
                });
        var cutter = qCreatedBy(id + "socketCore", EntityType.BODY);

        // 2. Four corner stacks sitting ON the wire's corners, with radius equal
        //    to the profile offset o(z): that disc is the corner of the
        //    dilation. Measured live 2026-09-20: the earlier version centred them
        //    at wireHalf - wireRadius and used wireRadius + o, which put the top
        //    corner radius at 1.15 + 4.00 = 5.15 mm -- 1.15 mm outside the
        //    plate's own 4 mm corner -- so the socket corners cut through the
        //    plate rim and the "45 deg flare" was really a bulge on the corners
        //    only, while every flat side stayed 34 mm apart for all z.
        for (var i = 0; i < 4; i += 1)
        {
            const signX = (i < 2) ? 1 : -1;
            const signY = ((i % 2) == 0) ? 1 : -1;
            const cx = centreX + signX * wireHalf;
            const cy = centreY + signY * wireHalf;

            const bottomCylinder = id + ("socketCyl" ~ i);
            fCylinder(context, bottomCylinder, {
                        "bottomCenter" : vector(cx, cy, zFloor),
                        "topCenter" : vector(cx, cy, zBottom),
                        "radius" : offsetBottom
                    });

            const rampCone = id + ("socketRamp" ~ i);
            fCone(context, rampCone, {
                        "bottomCenter" : vector(cx, cy, zBottom),
                        "bottomRadius" : offsetBottom,
                        "topCenter" : vector(cx, cy, zMid),
                        "topRadius" : offsetMid
                    });

            const lockCylinder = id + ("socketLock" ~ i);
            fCylinder(context, lockCylinder, {
                        "bottomCenter" : vector(cx, cy, zMid),
                        "topCenter" : vector(cx, cy, zLock),
                        "radius" : offsetMid
                    });

            const topCone = id + ("socketFlare" ~ i);
            fCone(context, topCone, {
                        "bottomCenter" : vector(cx, cy, zLock),
                        "bottomRadius" : offsetMid,
                        "topCenter" : vector(cx, cy, zTop),
                        "topRadius" : offsetTop
                    });

            cutter = qUnion([cutter,
                             qCreatedBy(bottomCylinder, EntityType.BODY),
                             qCreatedBy(rampCone, EntityType.BODY),
                             qCreatedBy(lockCylinder, EntityType.BODY),
                             qCreatedBy(topCone, EntityType.BODY)]);
        }

        // 3. The side strips of the dilation. Each bar spans the cell in BOTH
        //    directions of one axis, so one body carries two opposite strips. A
        //    constant band is a plain cuboid; a 45 deg band is a cuboid whose two
        //    outer faces are drafted about the band's bottom plane, which keeps
        //    the bar's other two faces vertical (a drafted extrude of a rectangle
        //    would also widen in the other axis and eat into the corner posts).
        //    Adding these bars is the fix for the missing flare: they are what
        //    makes the flat sides of the socket move out with z.
        const barBottomHalf = wireHalf + offsetBottom;
        const barLockHalf = wireHalf + offsetMid;
        fCuboid(context, id + "barClearX", {
                    "corner1" : vector(centreX - barBottomHalf, centreY - wireHalf, zFloor),
                    "corner2" : vector(centreX + barBottomHalf, centreY + wireHalf, zBottom)
                });
        fCuboid(context, id + "barClearY", {
                    "corner1" : vector(centreX - wireHalf, centreY - barBottomHalf, zFloor),
                    "corner2" : vector(centreX + wireHalf, centreY + barBottomHalf, zBottom)
                });
        fCuboid(context, id + "barLockX", {
                    "corner1" : vector(centreX - barLockHalf, centreY - wireHalf, zMid),
                    "corner2" : vector(centreX + barLockHalf, centreY + wireHalf, zLock)
                });
        fCuboid(context, id + "barLockY", {
                    "corner1" : vector(centreX - wireHalf, centreY - barLockHalf, zMid),
                    "corner2" : vector(centreX + wireHalf, centreY + barLockHalf, zLock)
                });
        fCuboid(context, id + "barRampX", {
                    "corner1" : vector(centreX - barBottomHalf, centreY - wireHalf, zBottom),
                    "corner2" : vector(centreX + barBottomHalf, centreY + wireHalf, zMid)
                });
        fCuboid(context, id + "barRampY", {
                    "corner1" : vector(centreX - wireHalf, centreY - barBottomHalf, zBottom),
                    "corner2" : vector(centreX + wireHalf, centreY + barBottomHalf, zMid)
                });
        fCuboid(context, id + "barFlareX", {
                    "corner1" : vector(centreX - barLockHalf, centreY - wireHalf, zLock),
                    "corner2" : vector(centreX + barLockHalf, centreY + wireHalf, zTop)
                });
        fCuboid(context, id + "barFlareY", {
                    "corner1" : vector(centreX - wireHalf, centreY - barLockHalf, zLock),
                    "corner2" : vector(centreX + wireHalf, centreY + barLockHalf, zTop)
                });

        // qParallelPlanes picks exactly the two faces whose normal is +-x (or
        // +-y); the other four faces of a cuboid have normals +-y/+-z and are
        // excluded, so only the outward strip faces are drafted.
        //
        // The pull vector is -z, not +z: a drafted face rotates its normal
        // TOWARD the pull direction. Measured live 2026-09-20 (slice of the
        // exported STL): with pullVec = +z the ramp bar's flat side sat at
        // 17.80 mm instead of 18.50 mm at z = 5.70, i.e. exactly 0.35 mm of
        // inward taper, and the flare bar likewise shrank; the corner cones,
        // which are separate bodies, were still exactly right, so only the pull
        // direction was wrong. Both bands must widen with z.
        opDraft(context, id + "draftRampBars", {
                    "draftType" : DraftType.REFERENCE_SURFACE,
                    "draftFaces" : qUnion([
                            qParallelPlanes(qCreatedBy(id + "barRampX", EntityType.FACE), vector(1, 0, 0), true),
                            qParallelPlanes(qCreatedBy(id + "barRampY", EntityType.FACE), vector(0, 1, 0), true)
                        ]),
                    "referenceSurface" : plane(vector(centreX, centreY, zBottom), vector(0, 0, 1)),
                    "pullVec" : vector(0, 0, -1),
                    "angle" : 45 * degree
                });
        opDraft(context, id + "draftFlareBars", {
                    "draftType" : DraftType.REFERENCE_SURFACE,
                    "draftFaces" : qUnion([
                            qParallelPlanes(qCreatedBy(id + "barFlareX", EntityType.FACE), vector(1, 0, 0), true),
                            qParallelPlanes(qCreatedBy(id + "barFlareY", EntityType.FACE), vector(0, 1, 0), true)
                        ]),
                    "referenceSurface" : plane(vector(centreX, centreY, zLock), vector(0, 0, 1)),
                    "pullVec" : vector(0, 0, -1),
                    "angle" : 45 * degree
                });

        cutter = qUnion([cutter,
                         qCreatedBy(id + "barClearX", EntityType.BODY),
                         qCreatedBy(id + "barClearY", EntityType.BODY),
                         qCreatedBy(id + "barLockX", EntityType.BODY),
                         qCreatedBy(id + "barLockY", EntityType.BODY),
                         qCreatedBy(id + "barRampX", EntityType.BODY),
                         qCreatedBy(id + "barRampY", EntityType.BODY),
                         qCreatedBy(id + "barFlareX", EntityType.BODY),
                         qCreatedBy(id + "barFlareY", EntityType.BODY)]);

        // Self-check on the drafted bars themselves (zero quota). The cutter's
        // overall box CANNOT see this defect: the corner cones reach the top
        // width on their own, so a bar drafted the wrong way leaves the cutter
        // box perfectly correct while every socket flat side tapers inwards.
        // Each bar must reach the spec offset on its drafted axis and stay at
        // wireHalf on the other axis (a bar drafted on four faces, or a drafted
        // extrude, would also widen in the other axis and eat the corner posts).
        const barReachChecks = [
            { "bar" : "barRampX", "reachX" : wireHalf + offsetMid, "reachY" : wireHalf },
            { "bar" : "barRampY", "reachX" : wireHalf, "reachY" : wireHalf + offsetMid },
            { "bar" : "barFlareX", "reachX" : wireHalf + offsetTop, "reachY" : wireHalf },
            { "bar" : "barFlareY", "reachX" : wireHalf, "reachY" : wireHalf + offsetTop }
        ];
        for (var check in barReachChecks)
        {
            const barBox = evBox3d(context, {
                        "topology" : qCreatedBy(id + check.bar, EntityType.BODY),
                        "tight" : true
                    });
            const reachX = barBox.maxCorner[0] - centreX;
            const reachY = barBox.maxCorner[1] - centreY;
            if (abs(gfMillimeters(reachX) - gfMillimeters(check.reachX)) > 0.05 ||
                abs(gfMillimeters(reachY) - gfMillimeters(check.reachY)) > 0.05)
            {
                throw regenError("Drafted side strip " ~ check.bar ~ " reaches (" ~
                                 gfMillimeters(reachX) ~ ", " ~ gfMillimeters(reachY) ~
                                 ") mm instead of (" ~ gfMillimeters(check.reachX) ~ ", " ~
                                 gfMillimeters(check.reachY) ~ ") mm; the 45 deg draft direction is wrong",
                                 ["socket_bottom_size"]);
            }
        }

        opBoolean(context, id + "fuseSocket", {
                    "tools" : cutter,
                    "operationType" : BooleanOperationType.UNION
                });

        // Query the fused cutter by THIS feature's id: after an opBoolean the
        // result body is not addressed by the boolean's own id (the working
        // precedent, examples/duct-fan-adapter/fanDuctAdapter.fs:139-156, still
        // addresses the body by the seed primitive's id, and feature 1 above
        // names its body with qCreatedBy(id, ...)).
        var tools = qCreatedBy(id, EntityType.BODY);
        const cellTotal = gridX * gridY;
        if (cellTotal > 1)
        {
            var transforms = [];
            var names = [];
            for (var j = 0; j < gridY; j += 1)
            {
                for (var i = 0; i < gridX; i += 1)
                {
                    if (i == 0 && j == 0)
                    {
                        continue;
                    }
                    transforms = append(transforms,
                        transform(vector(i * definition.cell_pitch, j * definition.cell_pitch, GF_ZERO)));
                    names = append(names, "socket" ~ j ~ "_" ~ i);
                }
            }
            opPattern(context, id + "socketPattern", {
                        "entities" : tools,
                        "transforms" : transforms,
                        "instanceNames" : names
                    });
            // Re-query by feature id so the patterned copies join the tool set.
            tools = qCreatedBy(id, EntityType.BODY);
        }

        opBoolean(context, id + "cutSockets", {
                    "targets" : qSubtraction(gfSolidBodies(), tools),
                    "tools" : tools,
                    "operationType" : BooleanOperationType.SUBTRACTION
                });
    });

// ===========================================================================
// 3. Magnet holes: four blind holes per cell, below the socket floor.
// ===========================================================================

annotation { "Feature Type Name" : "GF Magnet Holes" }
export const gfMagnetHoles = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Cell pitch" }
        isLength(definition.cell_pitch, GF_PITCH_BOUNDS);

        annotation { "Name" : "Base block height" }
        isLength(definition.base_block_height, GF_BASE_BLOCK_BOUNDS);

        annotation { "Name" : "Magnet hole diameter" }
        isLength(definition.magnet_diameter, GF_MAGNET_DIAMETER_BOUNDS);

        annotation { "Name" : "Magnet hole depth" }
        isLength(definition.magnet_depth, GF_MAGNET_DEPTH_BOUNDS);

        annotation { "Name" : "Hole center from cell side" }
        isLength(definition.magnet_from_side, GF_MAGNET_SIDE_BOUNDS);

        annotation { "Name" : "Hole mouth chamfer" }
        isLength(definition.chamfer_size, GF_MAGNET_CHAMFER_BOUNDS);
    }
    {
        const plateBox = gfPlateBox(context);
        const spanX = plateBox.maxCorner[0] - plateBox.minCorner[0];
        const spanY = plateBox.maxCorner[1] - plateBox.minCorner[1];
        const gridX = gfCellCount(spanX, definition.cell_pitch, "Plate width");
        const gridY = gfCellCount(spanY, definition.cell_pitch, "Plate depth");

        // Same exact-centre derivation as the socket feature.
        const plateCentreX = (plateBox.minCorner[0] + plateBox.maxCorner[0]) / 2;
        const plateCentreY = (plateBox.minCorner[1] + plateBox.maxCorner[1]) / 2;
        const firstCellX = plateCentreX - (gridX - 1) * definition.cell_pitch / 2;
        const firstCellY = plateCentreY - (gridY - 1) * definition.cell_pitch / 2;

        if (definition.base_block_height < 1 * millimeter)
        {
            throw regenError(
                "Magnet holes need material below the socket floor; increase Base block height",
                ["base_block_height"]);
        }

        // The magnet is inserted from the socket side and rests magnet_hole_depth below
        // the socket floor (top.scad:185 mirrors the hole to open upward).
        const zFloor = definition.base_block_height;
        const zBottom = zFloor - definition.magnet_depth;
        const holeRadius = definition.magnet_diameter / 2;
        const overshoot = 0.1 * millimeter;

        // standard.scad:32 puts a cell's four holes at the cell-local pair
        // { d_hole_from_side, l_grid - d_hole_from_side } on each axis, i.e. 8 mm
        // in from each of the cell's four sides. firstCellX / firstCellY are CELL
        // CENTRES in this file (the socket feature cuts about them), so that pair
        // is +/- holeInset about the centre.
        //
        // Measured live 2026-09-20: the previous expression added d_hole_from_side
        // (and pitch - d_hole_from_side) to the CELL CENTRE, which placed the holes
        // at x = {-13, 13, 29, 55} instead of {-34, -8, 8, 34}: seven of sixteen
        // holes fell outside the 84 mm plate and the surviving ones cut the wrong
        // material. The geometry package caught it as a 0.2058 mm centre-of-mass
        // offset on an otherwise symmetric part.
        const holeInset = definition.cell_pitch / 2 - definition.magnet_from_side;

        if (holeInset <= 0 * millimeter)
        {
            throw regenError("Magnet hole offset must be less than half the cell pitch",
                ["magnet_from_side"]);
        }

        // Reference hole: the +X/+Y corner of the first cell (standard.scad:32).
        const holeX = firstCellX + holeInset;
        const holeY = firstCellY + holeInset;

        fCylinder(context, id + "magnetShaft", {
                    "bottomCenter" : vector(holeX, holeY, zBottom),
                    "topCenter" : vector(holeX, holeY, zFloor + overshoot),
                    "radius" : holeRadius
                });
        fCone(context, id + "magnetChamfer", {
                    "bottomCenter" : vector(holeX, holeY, zFloor - definition.chamfer_size),
                    "bottomRadius" : holeRadius,
                    "topCenter" : vector(holeX, holeY, zFloor + overshoot),
                    "topRadius" : holeRadius + definition.chamfer_size + overshoot
                });

        opBoolean(context, id + "fuseHole", {
                    "tools" : qUnion([qCreatedBy(id + "magnetShaft", EntityType.BODY),
                                      qCreatedBy(id + "magnetChamfer", EntityType.BODY)]),
                    "operationType" : BooleanOperationType.UNION
                });

        var transforms = [];
        var names = [];
        for (var j = 0; j < gridY; j += 1)
        {
            for (var i = 0; i < gridX; i += 1)
            {
                for (var sy = 0; sy < 2; sy += 1)
                {
                    for (var sx = 0; sx < 2; sx += 1)
                    {
                        if (i == 0 && j == 0 && sx == 1 && sy == 1)
                        {
                            continue;
                        }
                        const cornerX = firstCellX + i * definition.cell_pitch
                            + (sx == 1 ? holeInset : -holeInset);
                        const cornerY = firstCellY + j * definition.cell_pitch
                            + (sy == 1 ? holeInset : -holeInset);
                        transforms = append(transforms,
                            transform(vector(cornerX - holeX, cornerY - holeY, GF_ZERO)));
                        names = append(names, "magnet" ~ j ~ "_" ~ i ~ "_" ~ sy ~ "_" ~ sx);
                    }
                }
            }
        }

        var tools = qCreatedBy(id, EntityType.BODY);
        if (size(transforms) > 0)
        {
            opPattern(context, id + "magnetPattern", {
                        "entities" : tools,
                        "transforms" : transforms,
                        "instanceNames" : names
                    });
            tools = qCreatedBy(id, EntityType.BODY);
        }

        opBoolean(context, id + "cutMagnets", {
                    "targets" : qSubtraction(gfSolidBodies(), tools),
                    "tools" : tools,
                    "operationType" : BooleanOperationType.SUBTRACTION
                });
    });
