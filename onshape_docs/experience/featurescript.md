# Verified experience: FeatureScript

What an agent needs to write and diagnose FeatureScript correctly. Scope: vendored
reference 2960, authored Feature Studio 3029, observed runtime 3044, with live
evidence through 2026-08-14. Backed by the
verified corpus (`onshape_docs/verification/report.json`, collected by `verify_docs.py`
against FsDoc: 929 functions, 270 types, 129 constants, 133 predicates,
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
  - 35 operator overload entries (symbols like `-`, `+`), the `-Id-string` style
    names are the operators. (Count is deduplicated: the official page lists some
    operator overloads several times under the same anchor; the index folds them.)
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
reference does not document. Full run log: `onshape_docs/verification/live/README.md` (15 experiments;
the 7 rows that surprised the original expectations are now absorbed into the
corrected manifest, and a live reconfirm on 2026-08-14 matched 15/15 — see
`onshape_docs/verification/live/reconfirm-2026-08-14.json`).

- **`featurespecs` compiles only the signature/precondition, not the body.**
  A feature whose body calls an undefined function (`qDoesNotExist(...)`),
  annotates an undefined type (`var x is NotARealType = 5`), mixes units
  (`5*mm + 2`), or passes a scalar to `opExtrude` all still return **1 spec**.
  Those errors are deferred until the feature is *instantiated* (POST to a Part
  Studio). A spec ≠ working body — it only proves the `annotation` + `precondition`
  signature layer is valid.
- **Signature-layer errors give 0 specs.** Dropping `context` from the
  `defineFeature` function signature, or referencing an absent symbol in a
  `precondition` (`GBTErrorStringEnum`, `isString`, `isArray`), fails at save
  time with `featureSpecs` empty. The earlier "stale import (`2960.0`)" example
  is now **confounded**: `featurespecs` are only emitted for precondition
  params carrying a bound spec (e.g. `{ (millimeter) : [...] } as
  LengthBoundSpec`); a bare `isLength` emits no spec regardless of body —
  symbol-sweep 2026-08-14 proved this by uploading a definition-reading body
  and still getting `specCount 0`. So experiment 06 (no precondition at all)
  needs a bound-spec probe to test version behavior; `onshape_docs/scripts/live_gap_probe.py`
  and `onshape_docs/scripts/live_symbol_sweep.py` carry the corrected probe.
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
- **The vendored `is*` predicate set is accurate except `isUvVector`.**
  Live-verified against the deployed runtime (eval `libraryVersion` 3044;
  budgeted probe in `onshape_docs/verification/live/live-is-predicates.json`, script
  `onshape_docs/scripts/live_is_probe.py`): all 29 mirror `is*` predicates resolve except
  **`isUvVector`**, which the 2960 docs list but the 3044 runtime no longer
  defines (version drift — use `isUnitlessVector` instead; treat any `is*`
  lookup miss as "mirror gap OR version drift" and verify live).
  `isQuery`/`isString`/`isArray`/`isType` are **not** std predicates at 3044
  (probe: "Variable not found") — the correct precondition form is the
  `is <Type>` syntax (`definition.x is length`), not an `isX()` call. The
  2-arg bound forms are real and keep their 2960 signatures:
  `isReal(value, boundSpec)`, `isSquare(matrix)`, `isTopLevelId(id)`,
  `isWrap{Cone,Cylinder,Plane}(context, val)` — the 1-arg form of these does
  not exist.
- **Because the server does not compile bodies at save time, the local static
  checker is the only body-level guard.** Run `onshape_docs/scripts/fs_local_check.py`
  before any upload: it catches structural errors (hard) and flags body symbols
  the server would silently accept at save (`qDoesNotExist`, `NotARealType`).
- **A literal `opBoolean` map that passes both `"tools"` and `"targets"` for
  `UNION`/`INTERSECTION` must also pass `"targetsAndToolsNeedGrouping" : true`.**
  The checker warns about that shape (`check_op_boolean_grouping`) on a *literal*
  third argument only, and like every rule there the warning never blocks the
  write. The measured failure, the reason it is a real mistake rather than a
  style choice, and the alternative to the flag are all stated once, in the
  `opBoolean` grouping section below.

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
  (upload 3 + create Part Studio 1 + POST feature 1), and it is the only
  layer that exercises the body.

### Annotation strings are ASCII-only; body strings are not (live, browser leg)

Measured 2026-09-20 through the browser FeatureScript editor (deploy → read the
notice pane → commit), which costs **0 REST quota** per probe. Four deploys of
the same feature, varying only the strings:

| Deploy | `"Feature Type Name"` | parameter `"Name"` labels | body `setProperty` value | result |
|---|---|---|---|---|
| 1 | `螺旋凸棱` | Chinese | Chinese | `compiled: false` — "Nonconforming feature function 'spiralRidgeCn': Invalid character in 'Feature Type Name' annotation: only printable ASCII allowed" |
| 2 | `Spiral ridge CN` | Chinese | Chinese | `compiled: false` — "precondition analysis failed" + "Invalid character in 'Name' annotation" for **all five** parameters |
| 3 | `Spiral ridge` | ASCII | ASCII | `compiled: true`, 0 notices |
| 4 | `Spiral ridge` | ASCII | `螺旋凸棱柱` | `compiled: true`, 0 notices; the parts list showed `螺旋凸棱柱` |

So the gate is **annotations only**, and it applies to every annotation string
value, not just `"Feature Type Name"`:

- **A non-ASCII annotation value kills the whole feature.** Deploy 2 kept a
  valid ASCII type name and still emitted zero feature specs, so a single
  Chinese parameter label is enough to lose the feature — and the message names
  the key, not the line, so a long precondition needs a per-parameter scan.
- **Non-ASCII string *values* in the body are legal.** The vendored standard
  library already relies on this (`holeTable.fs:160` passes `"⌀"` to
  `tolerancedValueToString`, and `holetables.gen.fs:35277` has `"S™/SS™/CLS™"`
  as a table-map value), and deploy 4 both compiled clean and displayed the
  Chinese name in the part list. The name shown next to a body therefore does
  not have to match the ASCII UI label.
- **A Chinese *UI* label is impossible**, so a localized custom feature gets an
  ASCII `"Feature Type Name"` and ASCII `"Name"` labels; only model/part names
  can carry the Chinese text. The local checker warns about this shape
  (`fs_check.check_annotation_ascii`) rather than failing the deploy.

### `opBoolean` with both `tools` and `targets` needs the grouping flag (live, browser leg)

Measured by the reporter (issue #11) and reproduced by the local checker: an
`opBoolean` call whose **literal** definition map carries both `"tools"` and
`"targets"`, an `operationType` of `UNION`/`INTERSECTION`, and **no**
`"targetsAndToolsNeedGrouping"` fails at *regeneration* with the misleading
`@opBoolean: BOOLEAN_BAD_INPUT` / "布尔运算操作至少需要两个零件或曲面", which cost
five deployments.

- **The requirement:** pass `"targetsAndToolsNeedGrouping" : true` whenever both
  `tools` and `targets` are supplied. The vendored standard library writes the
  flag whenever it passes both fields (`boolean.fs`:
  `"targetsAndToolsNeedGrouping" : targets != undefined`).
- **Do not "fix" it by dropping `targets` unless `tools` already holds two
  bodies.** `UNION` only merges the `tools` among themselves, so with a single
  tool the same `BOOLEAN_BAD_INPUT` comes back — the reporter's own form A
  (tools-only, one entity) failed exactly that way. Adding the flag is the
  repair that always works.
- **The server text is misleading here.** "至少需要两个零件或曲面" names the symptom,
  not the missing field. It is the Onshape server's own message and is **not ours
  to change**, which is exactly why the local rule warns earlier.
- **The local rule is WARNING-level and never blocks an upload.** The vendored
  index can lag the live server, so
  `onshape_docs/query/fs_check.py:check_op_boolean_grouping` only warns; it fires
  on a *literal* third argument (the same gate as `check_op_definitions`), so a
  map held in a variable is never second-guessed. The false-positive gate is the
  vendored library itself (`test_static_guards.OpBooleanGroupingTest`).
- **The `targets` requirement text shown by `fs_get_function opBoolean` (or
  `fs_get_type`) comes from the generated/vendored index and is not hand-edited.**

### A precondition is what makes a generated feature look official (live)

The first version of the generated spiral declared an **empty precondition**, so
it published zero parameters. Onshape then showed the feature's internals
(`fCylinder` → an "extrude", `opHelix`, sketch+sweep, `opBoolean`) read-only
with nothing editable — visually nothing like a standard feature even though the
history row was a valid custom feature. Adding one

```featurescript
annotation { "Name" : "Base radius" }
isLength(definition.baseRadius, { (millimeter) : [12.5, 50, 200] } as LengthBoundSpec);
```

per dimension produces a real parameter dialog (`Base radius 10 mm / Pitch 6 mm
/ Ridge width 2 mm / Ridge height 2 mm / Length 30 mm` in the measured run), and
editing two of those fields applied and persisted:

- **The requested value belongs in the bound spec's middle slot** (the
  `LengthBoundSpec` literal is `[min, default, max]`), and the body must then
  read `definition.*` — a baked constant makes the dialog disagree with the
  geometry, e.g. a helix whose revolution count no longer follows `pitch`.
- **`setProperty(..., PropertyType.NAME)` is where a non-ASCII part name goes**,
  not the annotation.
- The measured dialog read `10 mm / 6 mm / 2 mm / 2 mm / 30 mm` for the
  requested `10/6/2/2/30`, i.e. the default slot is honored verbatim.

### `evalfeaturescript` as the live-doc tool (live, verified)

The server's `POST .../featurescript` (via `onshape_eval_featurescript`) is the
only cheap way to confirm real semantics the 2960 docs lack:

- **The script must evaluate to a two-argument anonymous function.** The server
  calls it with `(context, id)`; anything else fails with "script does not
  evaluate to a function" or an arity error. Working shape:
  `function(context is Context, id is Id) { return 5; }` → result `5`.
- **Pass `part_studio_id` explicitly in probe loops.** The resolver no longer
  walks the document: it returns the explicit id or the cached
  `onshape_rest_api_mode/config/onshape-state.json` `partStudioId`, and raises if neither is present
  (the old ~10-call implicit walk is disabled). With it, one eval is exactly
  1 call.
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
  fetched by a dedicated call. `include_live` (2 calls) only refreshes the
  Feature Studio's declared version; eval is the way to see the true deployed
  one, and its result is cached too.

### The verification ladder (spend quota only where it earns you something)

Confirmed by ~310 live calls. Cost-per-step below is real API calls:

| Step | Cost | What it proves |
|---|---|---|
| `fs_check_script` tool / `onshape_docs/query/fs_check.py` | 0 | Structure (reported as errors) + deferred-failure rules and unknown symbols (warnings). Importable in-process, so it runs before any upload; the CLI in `onshape_docs/scripts/fs_local_check.py` is the same analysis |
| Browser notice read (0 REST, needs a login and an open Feature Studio) | 0 | The compile result the UI already shows, incl. every message paragraph and a normalized code; `browser_deploy_featurescript` also runs the local check for free |
| `featurespecs` (via upload / `onshape_get_feature_studio_status`) | ~3 / 2 | **Signature + precondition only.** Body is not compiled at save |
| `onshape_eval_featurescript` | 1 | Any semantics the 2960 docs lack, with detailed compile errors in `notices`. Cheapest way to learn *why* a body fails |
| Instantiate (`POST .../features`) | 1 (cached) / 2 (cold) | The only layer that executes the body — but ERROR is opaque (no message) |

All local findings are **advisory**: they never block an upload, because the
vendored reference can lag the live server. Error-level findings still cost one
deliberate second confirmation — the first call returns `acknowledgementRequired`
with the findings, having written nothing, and the caller re-issues with
`acknowledge_local_findings: true`; warnings never ask. The rule lives once in
`onshape_docs/query/fs_check.py` and covers the browser deploy legs, the REST
upload and the validation pipeline's upload step. Measured against the real standard
library, an argument-count check produced 30 false positives and a field-name
check 73, so neither shipped; the two rules that did (non-map third argument to a
definition-map call, dimensioned arithmetic mixed with a plain number) had zero.
The gate that keeps them honest is `dev/tools/fs_corpus_check.py`, which scores
the checker against the live-labeled instance corpus.

Measured and rejected: a duplicate-`export` check. 34 of the 271 vendored files
declare the same export name twice, which is legal because FeatureScript overloads
by parameter types (`vector(x, y)` and `vector(x, y, z)`), so the rule would be
noise on correct code.

Import paths are checked too: an `onshape/std/...` module the vendored library
does not contain is a warning, measured at **zero** false positives over the 1717
import statements in that library plus this repository's own FeatureScript. The
comparison is against the 271 vendored *files*, not the 210-entry documented
module index — using the index produced 99 false positives for modules that exist
but are undocumented. Only the `onshape/std/` prefix is checked, so importing
another Feature Studio is never flagged.

False positives are also fixed, not just avoided. The symbol scan now reads the
masked text, so a word inside an annotation string — `"Planar face (drill
direction)"` — no longer reports a call to `face(`, and a commented-out example no
longer reports its own types; `test_static_guards` pins both directions, including
that a genuine unknown call or enum member is still warned.

One rule came from a failure the local pass used to miss *entirely*, and the live
evidence is still visible in the scratch document: the `gate check` Feature Studio
carries the yellow/red notice from 2026-09-19, because the server saved and then
rejected

    isLength(definition.depth, { (0) * millimeter, (100) * millimeter } as LengthBoundSpec);

with five notices ("no viable alternative at input '(0) * millimeter,'",
"missing TOP_SEMI at 'function'", "extraneous input ')' expecting {…, TOP_SEMI}").
`{ … }` in expression position is a **map**, so every top-level entry needs
`key : value`, and a positional entry is a syntax error — but the checker reported
only the unrelated undefined-symbol warning next to it. It now warns
`map literal at line 8 has an entry without 'key : value'`, on the same line the
server pointed at. Because it is text-level, it needed its own false-positive gate
against the whole mirror: the first version flagged `cplane.fs`'s lambda body
`(x is number) returns boolean =>{ … }`, which is why `>` is excluded from the
expression-position set (no reading of FeatureScript puts a map literal to the
right of `>`). After that exclusion all 265 vendored modules are clean, and the
gate test asserts that class stays clean. Warning-level like every new rule: it is
never the reason a deploy stops, and a source it flags still needs the server's
own verdict.

Rules that save quota:

- **Never compile-probe with uploads.** A bad body costs the same ~3 calls as a
  good one and returns nothing (0 specs is ambiguous — plain functions also give
  0). Use eval for body semantics; it returns real error text.
- **A version mismatch is a save-time (signature-layer) error** — check
  `fs_check_version` (free, uses cached observed versions) *before* writing an
  `import` line. Vendored 2960 → real Feature Studio 3029 is exactly the
  mismatch that fails at save.
- **ERROR on instantiation is not a compile error** — it also fires for
  runtime/empty-query conditions (e.g. `qCreatedBy(id)` finds nothing on first
  run). Distinguish by reasoning, not by the API.
- **Do not infer an exact cross-version `import` boundary from the existing
  probes.** Historical 3029 experiments emitted a spec while a later narrative
  reported 3044 probes with zero specs, but the persisted corrected probes do
  not contain an unconfounded same-shape 3029-accept/3050-reject pair. Spec
  emission itself depends on an `annotation { "Name" }` plus bound-spec
  precondition, so zero specs alone is not rejection evidence. The exact import
  boundary is therefore **unknown**, not `3029 < version <= 3044`. Only run a
  new paired probe when a real task requires that one fact and separately
  authorizes its live budget; persist every call as evidence.
- **429 is never retried (user policy 2026-08-14).** Onshape's Retry-After hit
  about 20 hours with Rate-Limit-Remaining 0 during the recorded incident. `client.request` raises
  `RateLimited` immediately (wait time persisted to `onshape_rest_api_mode/config/api-usage.json`);
  every quota script re-raises it, writes the error to its results file, and
  exits — no retry, no skipping to the next task. Hard budgets everywhere: a
  `--budget` total cap preflighted against the annual quota, plus per-operation
  checks (e.g. an import version probe costs 3 calls and is only started if all
  3 fit the remaining budget).
- **Quota tests: minimize the unit whose crash is total; bundle only what is
  free to bundle.** A bundled eval is 1 call whether it holds 1 symbol or 10
  (clean bundles PASS in bulk), so large bundles are efficient — but a failing
  bundle binary-splits at 1 call per revealed symbol, so over-bundling symbols
  likely to fail is costly. More importantly, a quota run must **save
  incrementally**: `onshape_docs/scripts/live_symbol_sweep.py` first run only wrote at the
  end and a single unattributable runtime error (a value-typed predicate
  deref'ing a `5` dummy: "Attempt to dereference non-container 5") recursed its
  binary split forever until the API 429'd — losing all 61 calls' results.
  Fixes: save after every recorded symbol; stop splitting at a 1-element bundle
  (record UNATTRIBUTABLE and move on); pass a `vector(1,2,3)` dummy for
  `value`-typed params, not `5`, so structural predicates (is2dDirection,
  isLengthVector, …) don't deref the dummy at runtime.

## Composing a thin feature from the standard library (live, browser leg, 0 REST quota)

A "thin" feature carries no geometry math of its own: it exposes a few numbers and
calls the SAME standard-library routine Onshape's own toolbar feature calls. The
point is the feature tree — a two-to-five number row a human edits like a native
modeling step, instead of a fat domain feature that hides the whole model.
Measured 2026-09-20 on `dev/fixtures-capture/thin-native-features.fs`
(`Thin Sketch Rectangle`, `Thin Extrude`).

**Calling a feature from inside a feature is upstream practice, not a trick.**
`sketch.fs`'s own module docstring gives the canonical form —
`newSketch`/`newSketchOnPlane` → `skRectangle` → `skSolve` →
`extrude(context, id + "extrude1", { "entities" : qSketchRegion(id + "sketch1"), … })`
— and `cylinderCast.fs:245` and `sectionpart.fs:1005` really do call
`extrude(context, id, definition)` from inside another feature. So a thin wrapper
is a composition the standard library already relies on.

**A type in a precondition is part of the module interface, so it needs an
`export import`.** A plain `import` of the defining module is not enough, and the
message names the parameter, not the import:

| Server message | Cause | Fix |
|---|---|---|
| `definition.operation: Enum used as parameter type must be exported` | `definition.operation is NewBodyOperationType` in the precondition, with `tool.fs` (where `tool.fs:66` declares `export enum NewBodyOperationType`) merely imported | `export import(path : "onshape/std/tool.fs", …)` — the same reason `extrude.fs` re-exports `tool.fs` in its own "Imports used in interface" block. A type used only in the *body* needs no export import |
| `Cannot assign to constant extrusion.` | a FeatureScript map bound with `const` rejects a field assignment, so `extrusion.hasDraft = true` after the literal fails | build the map in one expression, with the conditional entry computed as a value. Passing the draft keys unconditionally is safe because `draftAngle` is `@requiredif {hasDraft is true}` (`extrude.fs:102`) and the documented default is `hasDraft: false` (`extrude.fs:410`) |
| `Nonconforming feature function 'thinExtrude': precondition analysis failed` | secondary: the precondition itself was rejected, so the whole feature loses its spec | fix the primary diagnostic |

**A bound spec's second element is the dialog default, not the midpoint.** A
sketch plane origin declared with the *size* spec
`{ (millimeter) : [0.1, 84, 5000] }` therefore opened every new sketch at
`(84, 84, 84)` — verified by reading the inserted row back with
`browser_read_feature_parameters`, which returned `"origin_x": "84 mm",
"origin_y": "84 mm", "origin_z": "84 mm"` plus `"width": "84 mm"`. Give a
quantity that must default to zero its own symmetric spec, e.g.
`{ (millimeter) : [-10000, 0, 10000] }`. This is invisible in the model until
something measures it: the extrude still succeeded and still produced a part.

**Read the compile verdict from `compiled`, not from the click.** A rejected
deploy still reports `commitAccepted: true`, `verified: true` and a matching
`verifiedLength`, because the Commit button really was clicked and the editor
really was written — only the server's diagnostics disagree. Every iteration in
this loop spent 0 REST quota and returned the server's own `row`/`col`/`message`,
and the accepted attempt also wrote a diagnostic package (source + compile result)
under `onshape_browser_mode/outputs/fs_diagnostics/<captureId>/`.

**A new feature in the workspace dropdown needs no document version.** Both thin
features were offered by the custom-feature toolbar dropdown of a scratch Part
Studio immediately after the Feature Studio commit, and
`browser_insert_custom_feature` accepted each row and confirmed it survived a
reload (`commit.verified: true`, `committed: true`). The pair produced a real
solid (`零件数 (1) Part 1`), so a human can add and edit these rows exactly like a
native step. The ASCII rule above still applies: a localised custom feature is
impossible because `"Feature Type Name"` and every parameter `"Name"` must be
printable ASCII.

## Driving a thin feature's dialog: what actually commits (live, browser leg)

A chain of thin rows only reproduces a model if every dialog value it opens with
really reaches the part. Two measured traps make the model silently wrong while
every readback says otherwise. Both were found on the 14-row Gridfinity rebuild
(`dev/fixtures-capture/gridfinity-thin-plate.json`).

**The dialog commits on `change`, so the last field you fill is the one that is
lost.** `Locator.fill` fires an `input` event only; the browser fires `change`
when the field loses focus, and Onshape's parameter directive commits on `change`.
The dialog's OWN readback therefore shows the typed text while the model keeps the
previous value — a corner radius typed as `4 mm` persisted as `0 mm`, and a draft
angle typed as `45 deg` persisted as `0 deg`. The feature list stayed green, the
extrude still produced a solid, and the plate came out with sharp corners and no
draft anywhere. Fix: blur after every fill
(`onshape_browser_mode/actions.py::_commit_field`).

**Only geometry or a re-opened dialog is evidence of persistence.** The
`fill_dialog_fields` result now distinguishes `committed` from `uncommitted` and
refuses the insert when a field did not commit, because `after` (the dialog's own
readback) was exactly the reading that lied. The same rule killed an earlier
plausibility check: a mesh report of `watertight: true` at
`[84, 84, 10] mm` was produced by a model whose bottom face area was
`7056.0000 mm²` (= 84², sharp corners) with no conical face anywhere. A B-rep face
inventory is what separates R4 from sharp and 45 deg from a straight wall; the
acceptance evidence is in
`onshape_docs/verification/thin-feature-rebuild-brep-2026-09-21.md`.

**A quantity widget resolves a `#variable` ASYNCHRONOUSLY, so the read taken
straight after the fill is stale.** Filling `#gf_pitch * 2` into a thin row's Value
field and reading it back immediately returned `0 mm` — the field's own default,
with no error — and the accept that followed committed that `0 mm` as the
variable's value. The same dialog read the typed expression back verbatim once the
widget had resolved it (~1.5 s later). A `#` value therefore has to be waited for,
and the evidence is the DIALOG's readback after the wait, never the read taken right
after the fill: `actions.wait_for_dialog_fields` polls `dialog_values` for at most
20 s (1 s poll) and its verdict IS the fill verdict.

**The settled readback is either the typed expression OR the evaluated number, so
waiting for the text alone is not enough.** Measured live 2026-09-21, same session,
two fields, opposite outcomes: the `Thin Variable` Value field settled to the typed
`#gf_pitch * 2` verbatim, while a `Thin Sketch Rectangle` dimension settled to the
resolved `36.3 mm` for a typed `#gf_socket` (the typed text appeared only in a read
taken ~4 ms after the fill; 20 s later the widget read `36.3 mm`). A wait that
accepts only the typed text therefore ended in a **false refusal**: the socket
clearance sketch reported "parameter(s) cell_pitch, width, height, corner_radius
hold an Onshape expression that the dialog never read back" after
`elapsedMs: 20312`, with `parameters.uncommitted: []`, for a dialog that was in fact
correct. The caller now states what each expression must EVALUATE to —
`expect_values` (parameter id -> value, e.g. `{"width": "36.3 mm"}`) — and, for a key
it states, that value is the **only** accepted settle signal; a key with no stated
value is satisfied by the typed expression. Both are compared by
`actions.quantities_match` (whitespace-collapsed text, unit must match, numbers
within a relative 1e-9). A caller that states nothing for a *dimension* still gets
the refusal, which is why every expression-bearing step of the rebuild fixture
carries `expect_values`.

That is what lets a geometry-style thin step — a `Thin Sketch Rectangle` whose
`cell_pitch`/`width` are all variables, and whose feature has no name template and
therefore no row text to check — be inserted at all, which the earlier "an
expression must come with `expect_row`" rule made impossible. `expect_row` remains
the alternative for a feature that writes its numbers into the row text.

**A row can report `inserted: true` and still hold its dialog DEFAULTS.** Measured
live 2026-09-21 by reading the rows back with `browser_read_feature_parameters`
instead of trusting the insert result: in the variable-driven tab every
`Thin Sketch Rectangle` created by the **insert** path had stored the dialog's
defaults for its three expression fields, while its literal fields were correct.
`TS Thin Sketch Rectangle 1` (the plate outline) read `width 100 mm`,
`height 100 mm`, `corner_radius 0 mm` instead of `#gf_plate_size` = 84 mm and
`#gf_plate_corner` = 4 mm, while `origin_z`/`grid_x`/`grid_y` were right. The
literal-valued sibling of the same thin feature in the same document read
`84 mm / 84 mm / 4 mm`, which is what made the two readings decisive. Cause: the
settle gate accepted the typed `#variable` text, and the accept that followed
committed the widget's previous value; the fill's own `after` readback confirmed the
text, so the call could honestly report success. Consequences worth keeping:

- **An insert's own `inserted` is not proof of the numbers.** Read the row back
  (`browser_read_feature_parameters`) or measure the geometry; on this tab the
  "verified" plate outline was a silent 100 mm default.
- It is the same defect class as the `0 mm` variable above, so the fix belongs in
  one place: `actions.wait_for_dialog_fields` now ignores the typed text for any key
  the caller states in `expect_values`.
- A literal-only chain is immune (there is no expression to race), which is why the
  literal thin build passed B-rep acceptance while the variable-driven one silently
  did not.

**A `Feature Name Template` row cannot be addressed by its feature name.** A row
rendered from a template shows the computed values, not the feature type:
`TV #gf_pitch = 42 mm`, not `Thin Variable`. A name-matched row filter therefore
matches ZERO rows for exactly the features that carry a name template, and the
commit check has to count user rows and identify the created one by set difference
against the pre-insert names (`actions.user_feature_rows`,
`verify_insert_committed(baseline_names=…)`). The template is still the best place
to read an expression's EVALUATED value, so `expect_row` is the strongest check for
such a row and is optional only for a feature whose row states no numbers.

**A styled checkbox is not clickable at the `input`.** A boolean parameter renders
as `<input type="checkbox" class="os-param-checkbox-input" data-parameter-value="false">`
that is not visible, so `Locator.click()` blocks for the full 30 s timeout
("element is not visible"). The visible hit target is an ancestor. Walk
`xpath=..`, `xpath=../..`, `xpath=ancestor::label[1]`,
`xpath=ancestor::*[contains(@class,'checkbox')][1]` with a short per-candidate
timeout (2500 ms) and judge by the resulting state, not by the click returning
(`_click_boolean`); verified by the parameter reading back `"true"`.

**Keep every thin parameter a number, a string, or a boolean.** Enum controls are
neither fillable nor readable through this dialog mechanism: the `axis` parameter
of the sketch thin feature reads back `""` whatever is chosen, so a select-style
parameter cannot be driven or verified. A thin feature that needs to choose
between cases should take a number or a boolean instead.

**A refused insert still leaves a row, and the refused dialog stays OPEN — which is
how to repair it.** The dropdown click creates the feature row *before* any
parameter is filled, so a refusal (missing field, uncommitted field, or a failed
readback) leaves a real default-valued row that survives a reload. Measured live
2026-09-21: the row `TS Thin Sketch Rectangle 2` was left behind by the false
refusal above, and `browser_read_feature_parameters` then reported `read: false`
with "a Parameter dialog is already open" — the fill had already committed every
field (its `uncommitted` list was empty), only the accept had been withheld. So
there is no need to delete the row and rebuild the Part Studio (this connection has
no tool that deletes a feature row anyway): reopen the row with
`browser_edit_feature_parameters` — the same fill then runs against the open dialog,
`before` already showing the intended values — accept, and confirm with
`browser_verify_feature_parameters` (`parametersApplied: true`, `regenerationOk`,
`persistenceOk`). That keeps the row *in its original tree position*, which matters
when the row sits between two steps of an ordered chain, and it costs one
transaction pair instead of a rebuild.

**The payoff: 14 rows reproduced the domain feature exactly.** With those rules in
place, a chain of `Thin Sketch Rectangle` / `Thin Sketch Circle` / `Thin Extrude`
rows produced a solid whose exact B-rep is identical to the three-row domain
baseline built from the verified FeatureScript: volume `39547.5903 mm³`, surface
area `20002.2154 mm²`, 194 faces, delta `0` in every one of those measures, and
the same nine face families (4 x R4 outer corners, 16 cones at exactly 45.0 deg in
each of three bands, and the 1.15 / 1.85 / 3.25 mm cylinders). Two independent
construction paths agreeing to the last digit is the strongest evidence available
that a feature tree mirrors the intended modelling steps.

**The same plate rebuilt parameter-driven: 23 rows, nine of them variables.** The
literal chain states every number in the row that uses it; the variable-driven chain
first creates nine `Thin Variable` rows (`gf_pitch` 42 mm, `gf_plate_size` as
`#gf_pitch * 2`, …) and then refers to them as Onshape expressions
(`dev/fixtures-capture/gridfinity-thin-plate.json`). The consumed values are the
same, so the same B-rep fingerprint is the acceptance test: export the tab to STEP
and diff it against `gridfinity-domain-baseline-20260921`. This rebuild is the first
place the count-based commit gate and the expression resolve wait are exercised
together, on every one of its steps. The measured result of that comparison is in
`onshape_docs/verification/thin-feature-rebuild-brep-2026-09-21.md`.

