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

## Live verification findings (real server, budget 200 calls)

Verifying the corpus against a real Feature Studio exposed mechanisms the
reference does not document. Full run log: `live/README.md` (15 experiments,
8/15 matched expectation).

- **`featurespecs` compiles only the signature/precondition, not the body.**
  A feature whose body calls an undefined function (`qDoesNotExist(...)`),
  annotates an undefined type (`var x is NotARealType = 5`), mixes units
  (`5*mm + 2`), or passes a scalar to `opExtrude` all still return **1 spec**.
  Those errors are deferred until the feature is *instantiated* (POST to a Part
  Studio). A spec ≠ working body — it only proves the `annotation` + `precondition`
  signature layer is valid.
- **Signature-layer errors give 0 specs.** Dropping `context` from the
  `defineFeature` function signature, importing an older std version than the
  Feature Studio (`2960.0` vs `3029.0`), or referencing an absent symbol in a
  `precondition` (`GBTErrorStringEnum`, `isString`, `isArray`) all fail at save
  time with `featureSpecs` empty.
- **`featureSpecs` empty is ambiguous.** A file of plain functions (compiles
  fine) also returns empty; only annotated export features appear. No error
  field exists on `featurespecs`, the Feature Studio GET, or the document
  elements list.
- **`GBTErrorStringEnum` does not exist at the live version.** The official
  reference links it in `ev*` signatures without a definition block; the live
  server rejects it at the signature layer too. The same for `isString` /
  `isArray` in `precondition` (the real `is*` predicate set differs from the
  vendored mirror — see below).
- **POST 200 + `microversionSkew:false` ≠ compile success.** The contents save,
  the compile may still fail; `featurespecs` reflects the compile, not the save.
- **`libraryVersion` is always 0** (on both a long-lived Feature Studio and a
  freshly created one). The FeatureScript version is declared by the uploaded
  `.fs` header (`FeatureScript 3029;` + `import version`), and there is no API
  to query a Feature Studio's current version.
- **Feature definitions must be** `export const NAME = defineFeature(function(
  context is Context, id is Id, definition is map) precondition { ... }
  { ...body... });` — confirmed by live probes and the trophy file. The
  `precondition` block is followed directly by the body block inside one
  `defineFeature(...)` call ending `});`. Closing the paren after
  `precondition {...}` and putting the body outside is a syntax error that
  silently yields 0 specs.
- **The vendored predicates index is incomplete for `is*`.** `isQuery`,
  `isString`, `isArray`, `isType` are absent from the mirror; live runs showed
  some of these (`isString`, `isArray`) genuinely absent from the live
  `precondition` layer too, while `isLength` is real. Treat an `is*` lookup
  miss as "mirror gap OR version drift" — verify against the live server.
- **Because the server does not compile bodies at save time, the local static
  checker is the only body-level guard.** Run `scripts/fs_local_check.py`
  before any upload: it catches structural errors (hard) and flags body symbols
  the server would silently accept at save (`qDoesNotExist`, `NotARealType`).

### Instantiation layer (live, 5 features POSTed into Part Studios)

- **Body errors surface as `featureStatus=ERROR` on the `POST
  .../features` call.** Features whose bodies call an undefined function
  (`qDoesNotExist`), annotate an undefined type (`NotARealType`), pass a
  scalar to `opExtrude`, or mix units all return ERROR at instantiation even
  though the save (signature) layer accepted them. So: signature pass + spec
  ≠ working body; only instantiation proves the body.
- **ERROR carries no detail.** The POST response `featureState` contains only
  `featureStatus` — no message, no line, no symbol. The feature is still saved
  into the Part Studio (it appears in `GET .../features`) and `featureStates`
  entries do not surface the message either. An agent cannot read the actual
  compile/runtime error text from the API; it must infer it.
- **A valid signature AND a syntactically valid body can still ERROR at
  runtime.** The three-layer probe (valid `defineFeature`, `qCreatedBy` +
  `opExtrude` body) returned ERROR on first instantiation because
  `qCreatedBy(id, EntityType.BODY)` finds no body yet and `opExtrude` gets an
  empty query. `featureStatus=ERROR` alone cannot distinguish a body compile
  error from a runtime/empty-query error — treat ERROR as "the body did not
  complete", then reason about why.
- This is why instantiation is the real cost: ~5 calls per feature
  (upload 3-4 + create Part Studio 1 + POST feature 1), and it is the only
  layer that exercises the body.

### `evalfeaturescript` as the live-doc tool (live, verified)

The server's `POST .../featurescript` (via `onshape_eval_featurescript`) is the
only cheap way to confirm real semantics the 2960 docs lack:

- **The script must evaluate to a two-argument anonymous function.** The server
  calls it with `(context, id)`; anything else fails with "script does not
  evaluate to a function" or an arity error. Working shape:
  `function(context is Context, id is Id) { return 5; }` → result `5`.
- **Its `notices` carry detailed compile errors** (`level`, `type: PARSE`,
  message, stack location) — far more diagnostic than instantiation's bare
  `featureStatus=ERROR`. Use eval to find *why* a body fails before spending
  instantiation calls.
- **The eval response's `libraryVersion` is the live deployment version** —
  **3044** at the time of writing, ahead of both the vendored 2960 and the
  trophy's 3029 header. (The featurespecs `languageVersion` reflects the
  content's declared version; eval's `libraryVersion` reports the server's.)
  `fs_check_version` reports the **last observed** of both for free — they are
  cached from workflow responses (`feature_studio_status` / `eval`), never
  fetched by a dedicated call. `include_live` (1 call) only refreshes the
  Feature Studio's declared version; eval is the way to see the true deployed
  one, and its result is cached too.

### The verification ladder (spend quota only where it earns you something)

Confirmed by ~310 live calls. Cost-per-step below is real API calls:

| Step | Cost | What it proves |
|---|---|---|
| `scripts/fs_local_check.py` | 0 | Structure (hard) + body symbols absent from the vendored index (warning) |
| `featurespecs` (via upload / `onshape_get_feature_studio_status`) | ~4 / 1 | **Signature + precondition only.** Body is not compiled at save |
| `onshape_eval_featurescript` | 1 | Any semantics the 2960 docs lack, with detailed compile errors in `notices`. Cheapest way to learn *why* a body fails |
| Instantiate (`POST .../features`) | 2 | The only layer that executes the body — but ERROR is opaque (no message) |

Rules that save quota:

- **Never compile-probe with uploads.** A bad body costs the same ~4 calls as a
  good one and returns nothing (0 specs is ambiguous — plain functions also give
  0). Use eval for body semantics; it returns real error text.
- **A version mismatch is a save-time (signature-layer) error** — check
  `fs_check_version` (free, uses cached observed versions) *before* writing an
  `import` line. Vendored 2960 → real Feature Studio 3029 is exactly the
  mismatch that fails at save.
- **ERROR on instantiation is not a compile error** — it also fires for
  runtime/empty-query conditions (e.g. `qCreatedBy(id)` finds nothing on first
  run). Distinguish by reasoning, not by the API.
- **Do not batch-verify what a real task will verify on demand.** The remaining
  unknowns (exact `is*` set at 3044, cross-version `import` boundary vs the
  deployed runtime) are cheap to answer inside the specific task that needs
  them, via eval — not by another bulk run.

