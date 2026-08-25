FeatureScript 3029;
import(path : "onshape/std/geometry.fs", version : "3029.0");

// 100mm PU duct -> 12025 fan exhaust adapter (single 3D-printed part).
//
// Coordinate convention:
//   XY = fan flange plane. Fan sits on the +Z side (inside the shroud walls),
//   duct spigot extends on the -Z side. Z axis points toward the shroud top.
//
// Design intent:
//   - Square flange (120x120) mirrors the 12025 fan footprint; 4 mounting holes
//     at 105mm pitch let self-tapping screws pass through the part first and
//     then thread into the fan.
//   - A cylindrical spigot (inner dia = PU duct inner dia) on the -Z side
//     receives the 100mm PU duct (hose clamp / tape, or screw-on spiral).
//   - A square shroud wall wraps the fan body (fan thickness) and extends
//     slightly past the fan face for rain protection.

const FAN_SIZE_BOUNDS        = { (millimeter) : [100, 120, 200] } as LengthBoundSpec;
const FAN_THICKNESS_BOUNDS   = { (millimeter) : [10, 25, 60] } as LengthBoundSpec;
const MOUNT_SPACING_BOUNDS   = { (millimeter) : [80, 105, 160] } as LengthBoundSpec;
const MOUNT_HOLE_DIA_BOUNDS  = { (millimeter) : [3.0, 4.5, 8.0] } as LengthBoundSpec;
const PLATE_THICKNESS_BOUNDS = { (millimeter) : [3, 6, 15] } as LengthBoundSpec;
const DUCT_INNER_DIA_BOUNDS  = { (millimeter) : [75, 100, 150] } as LengthBoundSpec;
const DUCT_WALL_BOUNDS       = { (millimeter) : [2, 3, 8] } as LengthBoundSpec;
const DUCT_LENGTH_BOUNDS     = { (millimeter) : [20, 40, 100] } as LengthBoundSpec;
const SHROUD_WALL_BOUNDS     = { (millimeter) : [2.5, 3.5, 8] } as LengthBoundSpec;
const SHROUD_GAP_BOUNDS      = { (millimeter) : [0.1, 0.25, 1.5] } as LengthBoundSpec;
const SHROUD_EXTENSION_BOUNDS= { (millimeter) : [0, 10, 40] } as LengthBoundSpec;

annotation { "Feature Type Name" : "100mm PU duct to 12025 fan adapter" }
export const fanDuctAdapter = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Fan size", "Default" : 120 * millimeter }
        isLength(definition.fanSize, FAN_SIZE_BOUNDS);

        annotation { "Name" : "Fan thickness", "Default" : 25 * millimeter }
        isLength(definition.fanThickness, FAN_THICKNESS_BOUNDS);

        annotation { "Name" : "Mount hole spacing", "Default" : 105 * millimeter }
        isLength(definition.mountSpacing, MOUNT_SPACING_BOUNDS);

        annotation { "Name" : "Mount hole diameter", "Default" : 4.5 * millimeter }
        isLength(definition.mountHoleDia, MOUNT_HOLE_DIA_BOUNDS);

        annotation { "Name" : "Flange plate thickness", "Default" : 6 * millimeter }
        isLength(definition.plateThickness, PLATE_THICKNESS_BOUNDS);

        annotation { "Name" : "Duct inner diameter", "Default" : 100 * millimeter }
        isLength(definition.ductInnerDia, DUCT_INNER_DIA_BOUNDS);

        annotation { "Name" : "Duct spigot wall", "Default" : 3 * millimeter }
        isLength(definition.ductWall, DUCT_WALL_BOUNDS);

        annotation { "Name" : "Duct spigot length", "Default" : 40 * millimeter }
        isLength(definition.ductLength, DUCT_LENGTH_BOUNDS);

        annotation { "Name" : "Shroud wall thickness", "Default" : 3.5 * millimeter }
        isLength(definition.shroudWall, SHROUD_WALL_BOUNDS);

        annotation { "Name" : "Shroud clearance", "Default" : 0.25 * millimeter }
        isLength(definition.shroudGap, SHROUD_GAP_BOUNDS);

        annotation { "Name" : "Shroud extension", "Default" : 10 * millimeter }
        isLength(definition.shroudExtension, SHROUD_EXTENSION_BOUNDS);
    }
    {
        // All definition.* lengths are ValueWithUnits (mm). Keep unit-carrying
        // math so every vector coordinate stays a plain length.
        const fanSize       = definition.fanSize;
        const fanThickness  = definition.fanThickness;
        const mountSpacing  = definition.mountSpacing;
        const mountHoleDia  = definition.mountHoleDia;
        const plateThickness= definition.plateThickness;
        const ductInnerR    = definition.ductInnerDia / 2;
        const ductOuterR    = ductInnerR + definition.ductWall;
        const ductLength    = definition.ductLength;
        const shroudWall    = definition.shroudWall;
        const shroudGap     = definition.shroudGap;
        const shroudExt     = definition.shroudExtension;

        const halfFan      = fanSize / 2;
        const halfOuter    = halfFan + shroudWall;
        const halfInner    = halfFan + shroudGap;
        const shroudTopZ   = fanThickness + shroudExt;
        const plateBottomZ = -plateThickness;
        const ductBottomZ  = plateBottomZ - ductLength;

        // ---- Solid building blocks -------------------------------------
        // 1. Flange plate = shroud footprint (covers the shroud wall ring so
        //    the plate and the walls share material and union into one body).
        fCuboid(context, id + "plate", {
                "corner1" : vector(-halfOuter, -halfOuter, plateBottomZ),
                "corner2" : vector( halfOuter,  halfOuter, 0 * millimeter)
        });

        // 2. Shroud outer box (walls that wrap the fan + extension).
        fCuboid(context, id + "shroudOuter", {
                "corner1" : vector(-halfOuter, -halfOuter, 0 * millimeter),
                "corner2" : vector( halfOuter,  halfOuter, shroudTopZ)
        });

        // 3. Shroud inner cavity (cut out, open at top).
        fCuboid(context, id + "shroudCavity", {
                "corner1" : vector(-halfInner, -halfInner, 0.01 * millimeter),
                "corner2" : vector( halfInner,  halfInner, shroudTopZ + 0.01 * millimeter)
        });

        // 4. Duct spigot (solid cylinder on the -Z side).
        fCylinder(context, id + "spigot", {
                "topCenter"    : vector(0 * millimeter, 0 * millimeter, plateBottomZ),
                "bottomCenter" : vector(0 * millimeter, 0 * millimeter, ductBottomZ),
                "radius"       : ductOuterR
        });

        // ---- Cut tools --------------------------------------------------
        // 5. Duct through-bore (plate + spigot).
        fCylinder(context, id + "ductBore", {
                "topCenter"    : vector(0 * millimeter, 0 * millimeter, 0.5 * millimeter),
                "bottomCenter" : vector(0 * millimeter, 0 * millimeter, ductBottomZ - 0.5 * millimeter),
                "radius"       : ductInnerR
        });

        // 6. Four mounting holes (through the flange plate).
        for (var i = 0; i < 4; i += 1)
        {
            const sx = (i % 2 == 0 ? 1 : -1) * mountSpacing / 2;
            const sy = (i < 2 ? 1 : -1) * mountSpacing / 2;
            fCylinder(context, id + ("mountHole" ~ i), {
                    "topCenter"    : vector(sx, sy, 0.5 * millimeter),
                    "bottomCenter" : vector(sx, sy, plateBottomZ - 0.5 * millimeter),
                    "radius"       : mountHoleDia / 2
            });
        }

        // ---- Booleans ---------------------------------------------------
        // Union the solid shells.
        opBoolean(context, id + "union", {
                "tools" : qUnion([
                        qCreatedBy(id + "plate", EntityType.BODY),
                        qCreatedBy(id + "shroudOuter", EntityType.BODY),
                        qCreatedBy(id + "spigot", EntityType.BODY)]),
                "operationType" : BooleanOperationType.UNION
        });

        // Subtract cavities and holes.
        var cuts = qUnion([qCreatedBy(id + "shroudCavity", EntityType.BODY),
                           qCreatedBy(id + "ductBore", EntityType.BODY)]);
        for (var j = 0; j < 4; j += 1)
        {
            cuts = qUnion([cuts, qCreatedBy(id + ("mountHole" ~ j), EntityType.BODY)]);
        }
        opBoolean(context, id + "cut", {
                "tools"      : cuts,
                "targets"    : qCreatedBy(id + "plate", EntityType.BODY),
                "operationType" : BooleanOperationType.SUBTRACTION
        });

        // ---- Name the part ---------------------------------------------
        setProperty(context, {
                "entities"     : qCreatedBy(id + "plate", EntityType.BODY),
                "propertyType" : PropertyType.NAME,
                "value"        : "100mm duct fan adapter"
        });
    });
