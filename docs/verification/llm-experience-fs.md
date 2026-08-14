# LLM experience: FeatureScript language

What a model actually needs to write correct FeatureScript. Backed by the
verified corpus (`docs/verification/report.json`, collected by `verify_docs.py`
against FsDoc: 949 functions, 270 types, 129 constants, 133 predicates,
210 modules, 18 guide pages).

## How the language is shaped (verified counts)

- **The naming system is the grammar.** Function-name prefixes tell you the
  role before you look at the signature:
  - `q*` — **query construction**, 121 functions (`qEverything`, `qCreatedBy`,
    `qUnion`, `qNthElement`). Queries select entities for later operations.
  - `op*` — **operations**, 55 (`opExtrude`, `opBoolean`, `opPattern`): the
    geometry-modifying primitives that run inside a feature.
  - `ev*` — **evaluate**, 45 (`evArea`, `evApproximateCentroid`): read geometry
    back out of the model (queries in, values out).
  - `to*` — conversions (23), `is*` — typecheck predicates (13), `f*` — feature
    builders (4).
  - 55 operator overloads (symbols like `-`, `+`), the `-Id-string` style names
    are the operators.
- **The dominant parameter type is `map`** (verified: 220 uses), followed by
  `Vector` (49), `array` (45), `Query` (23), `Id` (15), `ValueWithUnits` (14).
  A feature's `definition` is a map; pass the documented keys, not a positional
  argument list.

## The three layers of a model-modifying call

1. **Query** what you act on (`qAllSolidBodies`, `qCreatedBy(id)`).
2. **Operate** with an `op*` call taking `(context, id, definition)` where
   `definition` is a map (`{"entities": ..., "operationType": ...}`).
3. **Evaluate** back (`evArea`, `evBoundingBox`) to read results, checking the
   error return where present.

`context` and `id` are the standard arguments of every operation; the reference
documents only the `definition` map fields (see `fs_get_function` on an `op*`).

## Feature anatomy

- A custom feature is a function with a `precondition` (type-checks the
  parameters: `isLength`, `isReal`, `isQuery`, ...) and typed parameters, e.g.
  `(definition is map, isLength(definition.length))`. Parameter type-checks are
  `is*` predicates; a failing precondition surfaces as a red feature, not a
  compile error.
- `annotations` (`@autocomplete`, `@groupName`, ...) control the feature UI;
  see the `annotations` guide page.
- Units: dimensional values are `ValueWithUnits` (e.g. `10 * inch`), not raw
  numbers — assign lengths/heights through unit expressions.

## Versioning (the #1 real-world failure)

- `import(path : "onshape/std/geometry.fs", version : "...")` must match the
  Feature Studio's FeatureScript version. The vendored reference documents a
  specific snapshot (currently FS 2960); check `fs_check_version` before coding
  and warn `docs-behind` when your target is newer. A version mismatch is a
  compile error, not a warning.
- The standard library is almost entirely absent from model training data —
  look up exact signatures with `fs_get_function`/`fs_library_source` instead
  of guessing.

## Official FsDoc gaps found by verification

- **`GBTErrorStringEnum` is referenced but never defined.** The `ev*` query
  error parameters use it, e.g. `evCornerType` returns
  `GBTErrorStringEnum.BAD_GEOMETRY`, `evCurveDefinition` →
  `GBTErrorStringEnum.INVALID_INPUT` / `CANNOT_RESOLVE_ENTITIES`,
  `evEdgeConvexity` → `TOO_MANY_ENTITIES_SELECTED`. The official reference
  links these values but has no definition block for the enum — when you see
  `GBTErrorStringEnum.X` in a signature, treat `X` as a discrete error value,
  not a free string.
- Every other cross-reference resolves: parameter types, predicates, constants,
  and guide pages all check out (verified).
