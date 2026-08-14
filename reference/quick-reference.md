# FeatureScript quick reference

A distilled cheat-sheet for writing Onshape FeatureScript, synthesized from the
vendored official docs (`reference/fsdoc/`). It is intentionally short enough to
read in one shot; drill into `index.json` / the `fs_*` tools for exact
signatures. The vendored reference currently tracks standard library version
**2960**.

## How FeatureScript works

- A Part Studio is a FeatureScript **build function**; each feature in the tree
  is a **function call** inside it. Regeneration = re-executing the build
  function when the context or a definition changes.
- The **standard library** implements the default features (`extrude`,
  `helix`, ...) as functions. Custom features are defined in **Feature Studios**.
- A **feature** runs for every instance, every regeneration, whenever its
  definition or any upstream feature changes.

## File anatomy

```fs
FeatureScript 3029;                                // language version header
import(path : "onshape/std/geometry.fs", version : "3029.0");   // module import (pinned version)

annotation { "Feature Type Name" : "My feature" }  // required to export a feature
export const myFeature = defineFeature(function(context is Context, id is Id, definition is map)
    precondition { /* parameters the user edits */ }
    { /* what the feature does */ });
```

- Everything is versioned; match `import(... version:)` and the header to the
  Feature Studio's FeatureScript version.
- `export` makes a top-level construct visible to importing modules.

## Feature parameters (precondition)

```fs
precondition
{
    annotation { "Name" : "Radius", "Default" : 3 * millimeter, "Driving question" : "..." }
    isLength(definition.radius, RADIUS_BOUNDS);          // mm value with bounds
    annotation { "Name" : "Detailed" }
    definition.detailed is boolean;                      // boolean checkbox
    isReal(definition.scale, SCALE_BOUNDS);              // unitless real
    isBoolean(definition.flag);                          // checkbox
}
```

- Bounds specs are `LengthBoundSpec` / `RealBoundSpec` / `IntegerBoundSpec`
  maps `{ (millimeter) : [min, default, max] }` — see `valueBounds.fs`.
- Precondition predicates also typecheck: `is3dLengthVector`, `isQuery`,
  `isAngle`, `isBoolean`, `isBox`, ... (see `predicates` in the index).

## Core values and types

| Type | Notes |
|---|---|
| `number`, `boolean`, `string` | primitives |
| `length`, `angle`, `mass` | quantities with units; write `3 * millimeter`, `45 * degree`, `2 * inch` |
| `vector` | `vector(x, y, z) * millimeter` |
| `map` | `{ "key" : value, ... }`; `definition.*` is a map |
| `array` | `[a, b, c]`, `array` helpers in `containers.fs` |
| `Query` | selects entities: `qEverything(EntityType.EDGE)`, `qCreatedBy(id, EntityType.BODY)` |
| `Id`, `Context` | every operation takes `(context, id, ...)`; child ids via `id + "name"` |
| `Box` | 3D bounds: `box(vector(...), vector(...))` |

- String concatenation is the `~` operator: `"part" ~ 3` → `"part3"`.
- Units carry through math; use `length / 2`, `sin(x * degree)`, etc.

## Feature body — the standard workflow

```fs
// 1. Sketch on a plane, then solve
var sketch = newSketchOnPlane(context, id + "sketch", {
            "sketchPlane" : plane(vector(0, 0, 0) * millimeter, Z_DIRECTION, X_DIRECTION) });
skCircle(sketch, "circle", { "center" : vector(0, 0) * millimeter, "radius" : definition.radius });
skSolve(sketch);

// 2. Extrude / revolve / sweep / loft the sketch region
opExtrude(context, id + "extrude", {
            "entities" : qSketchRegion(id + "sketch"),
            "direction" : Z_DIRECTION,
            "endBound" : BoundingType.BLIND, "endDepth" : definition.height });

// 3. Clean up sketch helpers you no longer need
opDeleteBodies(context, id + "deleteSketch", {
            "entities" : qCreatedBy(id + "sketch", EntityType.BODY) });

// 4. Fillet / chamfer edges, with tangent propagation
opFillet(context, id + "fillet", {
            "entities" : qCreatedBy(id + "extrude", EntityType.EDGE),
            "radius" : definition.fillet, "tangentPropagation" : true });
```

- **Primitives** (single-call solids, no sketch needed): `fCuboid`, `fCylinder`,
  `fSphere`, `fCone`, `fEllipsoid`, `fTorus` (`primitives.fs`).
- **Higher-level features** wrap an op: `extrude`, `revolve`, `sweep`, `loft`,
  `helix`, `draft`, `shell`, `mirror`, `linearPattern`, `circularPattern`.
  Prefer the `op*` operation when building a custom feature.
- **Booleans**: `opBoolean` with `BooleanOperationType.SUBTRACTION` /
  `UNION` / `INTERSECTION`; `keepTools` controls the tools' fate.
- **Queries compose**: `qUnion`, `qBodyType(qEverything(EntityType.EDGE),
  BodyType.SOLID)`, `qCreatedBy(id, EntityType.EDGE)`, `qSketchRegion(id)`.
- **Regen errors**: `throw regenError("message", ["param1", "param2"])` to
  surface validation to the user (called from the body or a helper).

## Naming and appearance

```fs
setProperty(context, {
            "entities" : qCreatedBy(id, EntityType.BODY),
            "propertyType" : PropertyType.NAME,
            "value" : "myPart" });
setProperty(context, {
            "entities" : qCreatedBy(id, EntityType.BODY),
            "propertyType" : PropertyType.APPEARANCE,
            "value" : color(0.9, 0.5, 0.05) });
```

## Standard library map (categories)

- **Modeling** — the low-level ops: `geometry`, `common`, `context`,
  `geomOperations` (`opExtrude`, `opSweep`, ...), `primitives` (`fCylinder`, ...),
  `sketch`, `query`, `evaluate`.
- **Math** — `vector`, `matrix`, `units`, `coordSystem`, `curveGeometry`,
  `surfaceGeometry`, `transform`, `splineUtils`, `math`, `box`.
- **Utilities** — `attributes`, `containers`, `debug`, `error`, `string`,
  `table`, `valueBounds`, `tolerance`, `topologyUtils`.
- **Onshape features** — one module per feature: `extrude`, `sweep`, `loft`,
  `revolve`, `fillet`, `chamfer`, `shell`, `mirror`, `pattern`, `draft`,
  `hole`, `rib`, `derive`, `decal`, `sheetMetal*`, `frame*`, `importForeign`, ...
- **enums** — generated type modules (`boundingtype.gen.fs`, `propertytype.gen.fs`,
  `curvetype.gen.fs`, ...) containing the enum values referenced by op definitions.

## Language details worth knowing

- **Preconditions run before the body** and define parameters; predicates are
  typecheck + bounds. Validate cross-parameter constraints in the body with
  `regenError`.
- **Lambdas** — `function(x) x * 2`; used by `forEach`, `array` helpers,
  `qFilter`/`qUserPoints` and pattern callbacks.
- **for-in** — `for (var x in [1, 2, 3])`, `for (var key, value in {a: 1})`,
  `while`, `if/else` as expected.
- **Id children** — child operations need distinct ids under their parent;
  ids must reflect contiguous history. Use `id + "step1"`, or
  `id + ("loop" ~ i)` inside loops.
- **Annotations** — `annotation { ... }` decorates the next declaration; for
  parameters the important keys are `"Name"`, `"Default"`, `"Driving question"`,
  `"OnlyIf"`, and for the feature itself `"Feature Type Name"`.
- **Imports** — `import(path : "onshape/std/<module>.fs", version : "X.Y");`
  always pins a version. Feature Studios can import other document tabs/modules.
- **Coordinates** — XY is the base plane, +Z up by convention; `plane(origin,
  normal, x)` and `plane(origin, normal, xAxis, yAxis)`.

## Common pitfalls

- Forgetting `context`/`id` args on every operation, or reusing a child id for
  two non-contiguous operations (history violation → error).
- Sweeping: pick a plane whose normal is not parallel to the path; consider
  `keepProfileOrientation` for twisted paths.
- Bounds: always constrain lengths (`isLength`) so the UI and regen stay valid.
- Querying the wrong entity type (`EntityType.EDGE` vs `FACE` vs `BODY`).
- Fillet radius too large vs part size — validate before `opFillet`.
- Sketch helpers leave bodies behind — `opDeleteBodies` the sketch/profile inputs.

## Using this reference

- `fs_search` → find the exact name; `fs_get_function` → exact signature +
  parameters + examples; `fs_get_type` → enum values; `fs_guide_section` →
  language concepts; `fs_library_source` → the real std library implementation.
- `fs_check_version` before relying on the corpus for a newer FeatureScript
  version than the vendored snapshot; `fs_update_reference` to refresh it.
- `reference/fsdoc/quick.json` holds this same surface as one line per entry for
  machine indexing; `reference/fsdoc/index.json` has the full detail.
