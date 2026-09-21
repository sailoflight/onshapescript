# FS-first controlling route (roadmap)

Status: merged controlling route for the FS-custom-feature line; filed 2026-09.
Supersedes no implemented behavior. Owns sequencing and direction only.

## 1. Purpose and authority

This page is the **single controlling route** for the FS-custom-feature line. It
merges an externally supplied research plan ("Onshape Group research plan", 16
sections, self-declared approximate numbers) with the repository's existing
roadmaps, and records the owner's binding corrections to that plan.

It reconciles and sequences. It does **not** override:

- current behavior defined by code, registered schemas, handlers, and offline
  tests;
- module ownership in `../architecture/OVERVIEW.md` and `../modules/`;
- REST quota, confirmation, retry, credential, and live-request constraints;
- browser profile ownership, pacing, mutation, and acceptance constraints.

Conflict rule:

- On **sequencing or direction**, this page wins over a subordinate roadmap.
- On **implemented behavior**, current code and offline tests win; a conflict
  with this page is reported, not silently resolved.

The review that produced this merge — real tool baseline, already-implemented
items, the `op*` coverage matrix, and the true gap list — is recorded as the
Mnemon project document *Onshape FS 自定义特征方案评审与仓库现状核对*. Its evidence
sources are `docs/generated/TOOL_REFERENCE.md`, `onshape_rest_api_mode/operations.py`,
`onshape_docs/reference/raw/onshape-api/openapi.json`,
`onshape_docs/reference/index/fsdoc/index.json`, and
`onshape_docs/experience/browser-modeling.md`.

Reconciliation of every existing document is in §10.

## 2. Owner decisions (binding)

These six decisions govern every phase below. They are not open for
reinterpretation by an implementation.

**D1 — The browser leg is primary.** Browser automation spends **zero** Onshape
REST quota, so it is the default execution leg and may be iterated freely. The
quota ledger, not convenience, decides which leg performs a mutation.

**D2 — The REST leg is thin and quota-limited.** REST is not a default execution
path. REST wrapping exists to **reduce token cost**, not because direct calls are
forbidden: with the offline reference index an Agent can construct the POST
itself. A wrapper is justified only when the indexed prepared description is
cheaper to read than the raw endpoint plus schema.

**D3 — Both legs must be independently stable.** Neither leg may be abandoned to
make the other look adequate. Browser stability is explicitly expected to
require **substantial test investment**; that cost is accepted, because browser
iterations are quota-free.

**D4 — FeatureScript gains real local validation.** The structural checker is not
sufficient. Local validation must catch more classes of error offline so that
browser iterations are not spent on defects a local pass could have found.
`architecture/FS_VALIDATION_STRATEGY.md` owns that boundary: what is offline
decidable, what only the browser compiler can answer, and the measured
false-positive gate a new rule must pass. Existing external checkers were
surveyed there and none is reusable offline; reuse happens by detection, never by
installation.

**D5 — Direct GUI button-driving is abandoned as the modeling method.** Driving
Part Studio toolbars, dialogs, and context menus to model geometry is not the
route. The browser leg narrows to: land FS source, compile and read notices,
create the version, apply the custom feature, and verify the result. Geometry
semantics belong to FeatureScript.

> **Re-tested 2026-09-21 and upheld, with the boundary made explicit.** D5 forbids
> driving the toolbar; it does not forbid building a feature tree. A thin custom
> feature calls the same standard-library routine the native dialog calls
> (`extrude(context, id, definition)`, which `extrude.fs` itself documents as the
> dialog's own path), so an ordered chain of thin rows is D5-compliant geometry
> semantics *and* a human-editable parametric tree. The native-toolbar spike was
> built, then rejected and reverted. Measured: a 14-row thin chain reproduced the
> three-row domain baseline's solid with a zero-delta B-rep fingerprint
> (`onshape_docs/verification/thin-feature-rebuild-brep-2026-09-21.md`;
> `BROWSER_MODELING_GAPS.md` §4).

**D6 — This page is the completed merge.** The plan route is controlled here.
No parallel plan document may be introduced; new work is filed as phases (§11)
or as planned rows in `BROWSER_PLANNED_TOOLS.md`.

## 3. Strategy

Custom FeatureScript features act as quasi-native features. The Agent never
drives modeling UI; it produces geometry semantics as code, validates them
locally, lands them, and verifies the applied result. The human then takes over
in the native GUI, Feature List, and parametric workflow.

```text
Agent intent
  -> capability resolution (existing bounded catalog; capability cards later)
  -> FeatureScript generation / adaptation (op* based custom feature)
  -> LOCAL validation            <-- D4, offline, zero quota, zero browser
  -> land source -> compile -> read notices        (browser leg, D1, D5)
  -> create version -> apply custom feature
  -> verify: feature row + featureStatus + part count
  -> Human takes over in the native GUI

REST leg (D2): state / metadata / operations the browser cannot do reliably,
               always quota-guarded, dry-run first, one unresolved fact per call.
```

The value preserved is Onshape's: modern GUI, full parametric workflow, Feature
List, human takeover at any point, cloud collaboration.

## 4. What is already true (do not re-research)

| Claim from the research plan | Actual state | Evidence |
|---|---|---|
| "~80 MCP tools" | **106** — `browser`=66, `rest_operations`=18, `featurescript`=11, `rest_reference`=6, `project_docs`=3, `other`=2 (108 before the 2026-09-19 print-tool archive) | `docs/generated/TOOL_REFERENCE.md` summary block |
| Capability Registry + bounded capability search (plan H3/H4) | **Implemented** | `mcp_tool_catalog` (bounded search, exact describe only, never returns every schema), `mcp_tool_view`, `browser_discover_tools` |
| Target chain `small fixed entry -> module -> capability -> level -> bounded candidates -> exact schema` | **Implemented and documented** | `DYNAMIC_TOOL_DISCOVERY.md` (Status: implemented) |
| Six-level browser semantics | **Implemented** | `BROWSER_SIX_LEVEL_SEMANTICS_AND_FDM_PLAN.md`; `L1`=8, `L2`=6, `L3`=13, `L4`=27, `L5`=7, `L6`=1 |
| REST inserts a Custom Feature instance | **Implemented and live-verified** | `onshape_rest_api_mode/operations.py` `instantiate_feature` -> POST `/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/features` + `BTFeatureDefinitionCall-1406`; refuses non-`OK` `featureStatus` |
| "Browser only as Feature Studio fallback" | **Already decided, and now strengthened by D5** | `BROWSER_FS_SEMANTIC_TOOLS.md`: native feature-mode "explicitly out of current scope" |
| "Boolean-only is not a complete CAD primitive" | Direction correct; the repository holds a more precise construction-level record | `onshape_docs/experience/browser-modeling.md` §8/§9 |
| `op*` coverage needs dedicated research | **Answerable offline in one query** (see §8) | `onshape_docs/reference/index/fsdoc/index.json` |

Construction-level Boolean facts already verified (`browser-modeling.md` §8/§9):
UNION takes **only** `tools` (`targets` is for SUBTRACTION / SUBTRACT_COMPLEMENT /
grouping); after UNION `qCreatedBy(unionId, BODY)` is **empty** — the result body
stays owned by the earliest contributing tool feature; SUBTRACTION likewise
queries the *target* body; bodies that merely share a face can already be merged.

## 5. True gaps

| # | Gap | Evidence | Blocked by |
|---|---|---|---|
| G1 | REST Feature-List CRUD: `updatePartStudioFeature`, `deletePartStudioFeature`, `updateRollback`, `updateFeatures` exist in the vendored OpenAPI — **CLOSED 2026-09-19: handlers delivered offline in P3 and all four confirmed live (200), plus the previously missing Feature List READ** | 248 paths in `onshape_docs/reference/raw/onshape-api/openapi.json`; see `onshape_rest_api_mode/feature_list.py` and `test_rest_feature_list`; recorded bodies in `dev/tests/fixtures/onshape/feature-list/` replay in `LiveReplayTest` | none (live half spent: 4 writes + the reads the run needed) |
| G2 | Browser leg stability under heavy iteration | D3; `browser-modeling.md` records the `not-computed` / part-count-0 failure mode and selector fragility | none (quota-free) |
| G3 | Local FS validation depth | `onshape_docs/scripts/fs_local_check.py` is structural (brackets, header, `defineFeature` shape, dangling annotations, symbol presence, and since 2026-09-20 map-literal entries without `key : value` **and non-ASCII annotation string values** — the gate the live server enforced across four deploys; see `onshape_docs/query/fs_check.py::check_annotation_ascii`); `FS_HYBRID_COMPILER_INTEGRATION.md` states it is "not a parser, type checker, or lowering proof". The reuse survey and the offline/machine split now live in `architecture/FS_VALIDATION_STRATEGY.md`: no offline reusable FS analyzer was found, so the structural checker stays and an external one would be a detected candidate, never an installed dependency | none |
| G4 | Business capability layer (`cad.*` cards) with a cross-backend contract | **Browser half delivered in P4**: `onshape_browser_mode/capabilities.py` (cards + bounded search) behind `browser_discover_tools`; the cross-backend contract is still open | G1–G3 |
| G5 | Token / retrieval benchmark (capability card vs docs search vs full docs) | **Offline character benchmark delivered in P4** (`test_capability_retrieval`), **extended 2026-09-19** to a three-route size benchmark with a documented token *estimate* (`dev/tools/context_cost.py`, raw output in `onshape_docs/verification/context-cost-2026-09-19.json`): 209 estimated tokens for the actionable card plan against 1106 for the reference search and 1735 for the full guide page. **Extended 2026-09-21** to the tool-list surface and delivered a compression mode: `ONSHAPE_MCP_TOOL_EXPOSURE=gateway` advertises 2 tools (4,891 chars / 1,223 estimated tokens) against 76 tools (161,938 chars / 40,525) for the default `semantic` view and 110 tools (221,956 chars / 55,546) for `static` — 45.4x and 33.1x, with every registered name still callable and no registry row added (`dev/tests/test_tool_gateway_view.py`, raw output in `onshape_docs/verification/context-cost-surfaces-2026-09-21.json`). A true tokenizer measurement is still not claimed; the only in-the-loop data point is the P6 capability run | G4 |
| G6 | Surface audit (`Keep` / `Merge` / `Internal-only` / `Capability` / `Remove`) over the then-108-tool registry, now 106 | **Delivered in P5**: `architecture/TOOL_SURFACE_AUDIT.md`, gated by `test_tool_surface_audit`; candidates were already annotated in the generated reference. Follow-ups executed 2026-09-19: the two `semantically_invalid` print stubs were archived (see `history/legacy/ARCHIVED_BROWSER_PRINT_TOOLS.md`) and the two high-risk names were reclassified `Internal-only`, so `Remove` is 0; then all eight `Merge` rows were executed as compatibility wrappers, so `Merge` is 0 and the ordinary `tools/list` is 76 of the 110 registered names (re-measured 2026-09-21; the registry grew by the G6 follow-ups and the browser-tool install) | none |
| G7 | Thread geometry is the **only** real FS coverage hole | §8; `custom.spiral_ridge` is the accepted workaround and **passed its live gate 2026-09-19** (coarse 8 mm pitch, real geometry, 0 REST calls; `onshape_docs/verification/capability-live-run-2026-09-19.md`); the general twist surface is still not claimed | none |
| G8 | Route consolidation | `FS_HYBRID_COMPILER_INTEGRATION.md` and the external plan were parallel | closed by this page |

`browser_wall_thickness_report` is superseded by the L6 FDM package but remains a
valid L4 sampled observation and **must not** be removed in G6.

## 6. Legs

### 6.1 Browser leg (primary, D1/D3/D5)

**In scope:** Feature Studio source landing; `提交` and compile/notice acceptance;
symbol outline read; document version creation; applying a custom feature from
`此工作区中的自定义特征`; parameter dialog readback; feature-tree and part-count
verification; session recovery; document/tab lifecycle.

**Out of scope (D5):** driving modeling toolbars and dialogs to create geometry —
sketch/extrude/fillet/pattern by clicking — and the `DYNAMIC_TOOL_DISCOVERY.md`
Phase D native-modeling transactions built on that premise.

**Hard-won boundaries to keep** (`browser-modeling.md`): the `添加自定义特征`
dialog double-click path yields `not-computed` rows and part count 0; the working
path is `此工作区中的自定义特征` + parameter dialog + accept, and a document
version must exist first. Deploy acceptance is the Ace `setValue()` write, the
Commit button returning to disabled, and an exact source read-back — not "the
button was clicked".

### 6.2 REST leg (thin, D2)

Keeps: request building/transport, the live gate, quota ledger, stable target
state, dry-run, replay, export, and the offline REST reference index.

Adds (G1), each quota-guarded with dry-run first: feature update, feature delete,
rollback, and batch feature update. `BTMFeature.suppressed` is already written as
`false` in `_instantiate_body`, so suppression is an update rather than new
geometry work.

REST is not a second source of truth for the Feature List. When the browser leg
can perform the same mutation, the browser leg does it (D1).

### 6.3 Local validation leg (D4)

`fs_local_check.py` runs before every real upload and is extended toward real
parse/type checking. This is the cheapest place to buy back browser iterations: it
costs no quota and no browser session. It must remain conservative — a false
"valid" is worse than an honest "unknown".

It is a **warn-then-confirm** leg, not a veto (owner decision 2026-09-19): a
finding never blocks the write, because the vendored reference can lag the live
server. An error-level finding makes the first call return
`acknowledgementRequired` with the findings and write nothing; the caller
re-issues with `acknowledge_local_findings: true`. Warning-level rules never ask,
so the shipped heuristic rules cannot train callers to pass the flag blindly. The
rule lives once in `onshape_docs/query/fs_check.py` and is applied by
`browser_deploy_featurescript`, `browser_deploy_and_apply_featurescript`,
`onshape_upload_feature_studio`, and the upload step of
`onshape_run_validation_pipeline`; `dev/tests/test_local_check_gate.py` pins the
shared contract across the four.

## 7. Capability model

Two layers, deliberately separate:

1. **Tool catalog (exists).** Bounded `mcp_tool_catalog` search, exact describe,
   per-connection views. This is the context-routing layer.
2. **Capability cards (G4, new).** Business-level identities such as
   `cad.thread`, `cad.hole`, `cad.fillet`, below the tool layer, with
   identity / contract / routing, and an implementation pointer that stays
   **out of Agent context** during normal use.

Rules:

- Tool count and CAD capability count are decoupled. Adding a capability must not
  add an MCP tool.
- A stable capability is a closed closure: `cad.thread` may internally depend on
  helix, sweep, and boolean, but normal Agent use sees only
  `thread(target, diameter, pitch, length, mode)`. Implementation is opened only
  for debugging, modification, an unsatisfied requirement, or a backend change.
- Source reuse may be layered; Agent reasoning must not recurse.
- `cad.*` is the cross-backend semantic layer; `onshape.*` and (future)
  `freecad.*` are platform layers. Sharing covers name, intent, aliases, I/O
  semantics, `use_when`, and behavioral tests — never FS source, Python,
  Feature-Tree expansion, query representation, or document model.

**Existing precedent to generalize.** `browser_spiral_ridge` already implements
the target shape: bounded numeric inputs, no raw script or CSS exposed, dry-run
and confirmation, generated `opHelix` + `opSweep` source that passes the local
checker, compile-gated deploy, and applied-feature acceptance. The capability
contract should be extracted from this precedent rather than designed from zero.

## 8. FS modeling coverage (G7)

Method (reproducible offline): `onshape_docs/reference/index/fsdoc/index.json`
holds **929** indexed functions; `onshape_docs/reference/raw/std-library/*.fs`
holds **78** unique `op*` symbols.

| CAD feature | FS implementation | Covered |
|---|---|---|
| Extrude | `opExtrude` (`geomOperations.fs`) | yes |
| Pocket | `opExtrude` + `opBoolean` | yes (composition) |
| Hole | `opHole`, `qOpHoleProfile`, `qOpHoleFace`, `qHoleFaces` | yes (first-class) |
| Boolean | `opBoolean` | yes |
| Fillet | `opFillet`, `opFullRoundFillet`, `opModifyFillet` | yes |
| Chamfer | `opChamfer` | yes |
| Pattern | `opPattern`, `applyPattern` | yes |
| Mirror | `mirror` (`mirror.fs`, feature-level, not `op*`) | yes |
| Sweep | `opSweep` | yes |
| Loft | `opLoft`, `opTessellatedLoft` | yes |
| Shell | `opShell` | yes |
| Draft | `opDraft`, `opBodyDraft` | yes |
| **Thread** | only `externalThread` + `cosmeticThreadUtils` | **no** |

**12 of 13 covered.** Thread is the only real hole, and its nature is already
recorded in `BROWSER_MODELING_GAPS.md` §1: `externalThread` handles standard
ANSI/ISO sizes and cosmetic attributes only, not a custom coarse pitch. The
accepted workaround is the `browser_spiral_ridge` generation path.

## 9. Quota and mutation discipline

- `LIVE_API_ENABLED` stays unset by default; regression verification never
  enables it.
- Browser work costs zero REST quota but a real UI write **does** mutate cloud
  data. Quota-free is not read-only: `confirm_mutation` and dry-run rules are
  unchanged, and heavy browser *testing* still stops on ambiguity.
- A live REST request still requires one unresolved fact, an explicit budget
  (`expected_live_requests = max_live_requests = 1` by default), a redacted
  fixture destination, and a stop condition; 429 is never retried, and
  POST/PATCH/DELETE are never retried on 5xx or timeout.
- New REST operations under G1 are designed, dry-run-verified, and fixture-backed
  offline first. Only a genuinely unavailable fact justifies a live call. G1's
  four mutations plus the Feature List read passed that gate and are closed; their
  recorded bodies now answer offline what used to need the server.

## 10. Reconciliation with existing documents

| Document | Disposition |
|---|---|
| `FS_HYBRID_COMPILER_INTEGRATION.md` | **Subordinate.** Keeps ownership of compiler internals (frontend, Feature IR, model bindings, partitioning, Transaction IR, ports, fork isolation). Its **Phase 3 (whole-feature Custom MVP) becomes the mainline**; **Phase 4 native Extrude proof, Phase 8 sketch compiler, and Phase 9 island extraction are deferred** under D5. Its §"Capability registry and partitioning" maturity ladder is retained. |
| `DYNAMIC_TOOL_DISCOVERY.md` | **Phases A–C stay implemented.** **Phase D (browser native modeling) is deferred** under D5; do not collect toolbar-driving evidence or implement native-modeling L4 transactions. |
| `BROWSER_FS_SEMANTIC_TOOLS.md` | **Subordinate and retained.** Its "native feature-mode explicitly out of scope" note is promoted from a scope note to binding decision D5. Its FS script-mode transactions remain the browser surface. |
| `BROWSER_MODELING_GAPS.md` | **Retained.** Its §1 `browser_spiral_ridge` resolution is promoted to the capability-contract precedent (§7). |
| `BROWSER_SIX_LEVEL_SEMANTICS_AND_FDM_PLAN.md` | **Retained, largely orthogonal.** Owns six-level semantics, L6 FDM packages, and source adapters. No change required by this route. |
| `BROWSER_PLANNED_TOOLS.md` | **Retained as the planned-tool registry.** Any new planned row from this route is filed there. |
| `BROWSER_GENERIC_L2_SEMANTICS.md` | **Historical.** No new work unless a shell gap demonstrably blocks the FS route. |
| `../../Onshape_MCP_FS_Hybrid_Compiler_Agent_Execution_Spec_v2.md` | **Design input.** Remains a source proposal; not an implemented contract. |
| External "Onshape Group research plan" | **Absorbed.** No repository file; its still-new items are G1, G4, G5, G6, and G7. |

## 11. Phases and gates

**P1 — Browser leg stability + local validation (G2, G3).** Highest value: quota-free
and it unblocks everything else.
*Gate:* the FS apply/verify loop passes repeatedly against pathological inputs
(local-checker rejects, compile errors, `not-computed` rows, stale sessions), with
recorded evidence and no silent success.

Delivered so far, all offline:

- **P1c** — `dev/tools/fs_corpus_check.py` renders the recorded instance corpus
  and scores the local checker against its live labels. Current result: 4/4 target
  samples flagged, 6/6 valid samples clean. The three version-drift samples
  (`07/11/13`) are recorded with the FS-3029-vs-3044 caveat and are excluded from
  acceptance.
- **P1a** — two advisory rules in `onshape_docs/scripts/fs_local_check.py`: a
  definition-map call whose third argument cannot be a map, and dimensioned
  arithmetic mixed with a plain number. Both had zero false positives on the real
  standard library. Argument-count and field-name checks were measured, produced
  30 and 73 false positives, and were removed rather than shipped.
- **P1b** — the browser notice read now returns every message paragraph of a
  notice table, and the capture path adds a normalized, source-annotated
  diagnostics summary plus a bounded corpus entry for the local analyzer. The
  notice collector string is exercised offline against a stub DOM with node.
- **P1d** — the apply path no longer ends in three blind sleeps: it waits on the
  dropdown, the parameter dialog, and this feature appearing in the tree, each
  with a timeout at least as long as the sleep it replaced. `inserted` now means
  the feature is listed rather than that a click landed.
- **P1e** — acceptance separates the two facts a Feature List row carries.
  `browser_build_part` and `browser_deploy_and_apply_featurescript` require
  `featurePresent`, `featureComputed` (no `not-computed`/error row) **and**
  `零件数 > 0`, and return a `reason` when any of the three fails; a
  `not-computed` row can no longer be reported as a successful build just because
  other features supplied geometry.

**Closed 2026-09-19:** the real-machine apply/verify loop over pathological input
ran after the deployment refresh — a source the local checker passes (0 errors,
1 warning) was rejected by the live compiler with 5 persisted errors,
`deployed: false`, and 0 Feature List rows. Live evidence and the two open
findings it produced are in
[`onshape_docs/verification/capability-live-run-2026-09-19.md`](../../onshape_docs/verification/capability-live-run-2026-09-19.md)
§ Post-refresh live run. The warn-then-confirm gate itself was also exercised
live there, with the independent "no browser action" check.

**P2 — Whole-feature Custom capability template.** Generalize the
`browser_spiral_ridge` precedent into a data-driven contract; land the first
capabilities (extrude/cut, hole, fillet) as whole-feature custom features.
*Gate:* each capability runs dry-run -> local check -> deploy -> apply -> verify,
and reports an explicit non-success on any failed stage.

Delivered offline: `onshape_browser_mode/capabilities.py` holds the contract
(bounded values only; queries stay inside the generated feature's precondition;
cards carry no implementation) and four capabilities — `custom.spiral_ridge`
(`live-verified`, and asserted to render exactly the precedent's source),
`custom.fillet`, `custom.extrude` (with `remove` for the cut form), and
`custom.hole` (built from the vendored `holeDefinition`/`holeProfile`
constructors). No new
tool was added: `browser_deploy_and_apply_featurescript` now accepts either a raw
`script` or a `capability` + `values`, with the two routes expressed as an
`anyOf` in the schema and enforced in the handler. The generated source is
checked three ways offline — the local structural checker, a gate that every
referenced function/enum/constant exists in the vendored reference, and the
value contract itself (`test_capabilities`).

`custom.hole` was added later in the same phase. The earlier reason to reject it
— "`holeDefinition` cannot be confirmed offline" — did not survive the lookup:
`opHole`'s fields and example are in `geomOperations.fs`, `holeDefinition(profiles)`,
`holeProfile(positionReference, position, radius)` and the "final profile radius 0"
rule are in `holeUtils.fs`, `AXIS_POINT`/`LAST_TARGET_END` are enum members of
`holepositionreference.gen.fs`, and the axis is `line(evVertexPoint(...),
-evPlane(...).normal)`. The shape is therefore a symbol-gated constructor call,
not a guessed map literal; through holes use the `LAST_TARGET_END` reference rather
than a large depth.

Still open for the P2 gate: the machine half of the gate. The 2026-09-19 live run
(record: `onshape_docs/verification/capability-live-run-2026-09-19.md`) closed
part of it and moved the boundary:

- All four generated sources now **compile on the live server** (FeatureScript
  3044, 0 errors, 0 warnings, 0 notices) with the deployed text byte-checked
  against the capability generator. `structural-only` no longer describes them;
  `server-compiled` does.
- `custom.spiral_ridge` was **applied to real geometry**: Feature List row
  `Sr Spiral ridge 1` computed, `零件数 (1)`, part `Spiral ridge cylinder`.
- `custom.fillet`, `custom.extrude` and `custom.hole` **cannot be accepted**
  without an interactive geometry pick — Onshape disables the dialog's accept
  button while their required `Query` is empty — so no geometry is claimed for
  them. This is a contract gap, not a script bug: the delivered contract lets a
  caller supply bounded values only, and a selection-bound capability needs a
  channel this layer does not have.
- The live run also found and fixed a real workspace-row matcher defect (a row's
  `innerText` is `"Bf\nBounded fillet"`, not the name), which is why this path
  had no live evidence behind it before.

**P3 — REST Feature-List CRUD (G1).** Update / delete / rollback / batch update
plus suppression, dry-run first, fixture-backed.
*Gate:* offline tests prove request construction and parsing; any live fact is
separately authorized and budgeted.

Delivered, all offline:

- `onshape_rest_api_mode/feature_list.py` holds the pure builders and parsers for
  the four operations that had no handler: `updatePartStudioFeature`,
  `deletePartStudioFeature`, `updateRollback`, `updateFeatures`.
- `operations.update_feature_list` is the one entry point (`suppress`,
  `unsuppress`, `rollback`, `delete`, `replace`); the dry run and the live call
  build their request through the same function, so a dry run cannot describe a
  request the live path would not send.
- Tool `onshape_update_feature_list` exposes it: one live request per call, always
  with `confirm_mutation`, always with `dry_run` available first. Its quota gate
  uses the plan's own `estimatedRequests` rather than a hand-written number.
- The rollback body follows the operation's described object, not the spec's
  `{"type": "string"}`; suppression uses `updateFeatures` with
  `updateSuppressionAttributes: true`, which is the documented suppression
  channel.
- Evidence: `dev/tests/test_rest_feature_list.py` (spec-path agreement by
  `operationId`, spec-derived response instances, validation, live-path parsing,
  fixture drift). `dev/tests/fixtures/onshape/feature-list/` holds the four
  constructed requests and says in each `metadata.json` that nothing was sent —
  there is deliberately no `response.json`.

Still open for the P3 gate: no live call has been made, so the payloads here are
constructed-and-reviewed, not server-confirmed. The first authorized call should
be a single suppression (1 request, cheap, reversible) with the response captured
into the existing fixture directories.

**P3 live half — CLOSED 2026-09-19.** The owner authorized one hard-budgeted run,
and it did what the paragraph above planned, in that order:

- **All four mutations were confirmed live, each 200 with the schema the spec
  declares.** Suppression (`BTUpdateFeaturesResponse-1333`, `suppressed: true`),
  in-place definition replace fed from the definition read back
  (`BTFeatureDefinitionResponse-1617`, `featureStatus: "OK"`, renamed row),
  rollback with the described `{ "rollbackIndex": -1 }` body
  (`BTSetFeatureRollbackResponse-1042`), delete (`BTFeatureApiBase-1430`).
- **The Feature List READ was captured too**, which the offline slice had left as
  the one endpoint of the family with no handler and no fixture. It returned the
  real `featureId`, the serialized definition, and the `featureStates` map.
- **Domain verification was free**: after the delete, the browser Feature List
  (0 REST quota) showed `特征 (4)` / `零件数 (0)`, and the scratch Part Studio was
  left empty.
- **Fixtures flipped from constructed to recorded.** Each
  `dev/tests/fixtures/onshape/feature-list/*/metadata.json` now says
  `"liveExecuted": true` with its status, time and target; `FixtureTest` is
  state-driven (a constructed fixture must still say so; a live one must carry a
  real status, a real time, and a builder-matching request for the ids it
  records) and the new `LiveReplayTest` pushes the real bodies through the
  production parsers.
- **The read discrepancy is resolved, reproduced, and the answer is the browser
  handoff.** The run first blamed an absent `rollbackBarIndex` for an empty
  `features` array. A three-way probe on a long-committed element (absent / `-1` /
  `0`, one run, no reload) returned identical bodies, so the argument does not
  filter the read and `rollbackIndex` is the element's real bar position. A
  controlled reproduction then showed the real cause: after a clean browser insert
  REST reported an empty list immediately **and ~4 minutes later without a
  reload**, while a page reload made the feature appear — and a REST-added feature
  on the same element appeared with no reload at all. **A browser-inserted custom
  feature is not in the workspace until the page is reloaded**, so anything that
  builds a REST mutation on a feature the browser just created must read the
  Feature List back first. Evidence:
  `onshape_docs/verification/browser-rest-handoff-2026-09-20.json`.
- **The family is complete: `addPartStudioFeature` confirmed too.** The endpoint
  `operations.instantiate_feature` has always targeted answered 200 /
  `BTFeatureDefinitionResponse-1617` / `featureStatus: "OK"` with a new
  `featureId`, using the same `BTFeatureDefinitionCall-1406` envelope as add.
- **One refusal shape is recorded too.** A `DELETE` naming an impossible feature id
  returned 404 with `{"moreInfoUrl", "message", "status", "code"}`, at a measured
  quota cost of 0 — the family's success fixtures said nothing about failure.
- **Explained, not a defect:** `"parameters": []` is correct for this feature —
  the generated `spiralRidge` spec declares no parameters and bakes the geometry
  values in as literals, so changing the geometry means deploying a new
  FeatureScript version rather than editing parameters.
- Cost: 4 mutations (as authorized) plus the reads the run needed — the run's own
  accounting is in `onshape_docs/verification/capability-live-run-2026-09-19.md`.

**P4 — Capability card layer + retrieval benchmark (G4, G5).** Above the fixed
catalog; benchmark card hit vs docs search vs full docs on Extrude, Thread, and
one complex long-tail feature.
*Gate:* a normal capability call needs no implementation source, no recursive
dependency expansion, and no FS docs search.

Delivered offline: `capabilities.search(query, limit)` returns at most five cards
ranked by identity -> alias/feature type -> `use_when` prose, and both discovery
entries — `mcp_tool_catalog` (the documented lookup-first entry) and
`browser_discover_tools` — append matching cards through one shared
`capability_section`, so a card cannot describe one invocation in one place and
another elsewhere. No new tool was added and no exposure level moved. The same
change fixed a routing failure: a non-empty query the catalog tokenizer cannot
read (Chinese) used to match all 108 tools; it now matches no tool summary and
can still resolve a card.
A single incidental prose word ("feature", "part") is not a match; one weak word
never qualifies a card on its own. Each match carries the deploy call that uses
it — `browser_deploy_and_apply_featurescript` with `capability` and the card's own
defaults as `values` — because a capability is an argument to the deploy tool,
not a registered name that any invocation route could call.

`test_capability_retrieval` is the gate. It measures the two routes over the same
indexes the server reads: for the four named queries the resolved card costs
668–1422 characters, while the reference route costs 1862–8930 characters even
before the caller reads the function body that defines the contract. A Chinese
query ("打孔") resolves `custom.hole` while the FeatureScript search returns
nothing at all. It also
asserts that a prose query ("round the edges of this part") resolves to
`custom.fillet` while the FeatureScript search ranks only query helpers and
filters, that the card payload contains no source, and that resolving a card
touches no function entry, library source or guide page.

Still open for the P4 gate: it cannot show that a caller *would* stop reading
after the card. The "one capability call = one card" claim is proven for the
offline route only.

**Measured 2026-09-19** by `dev/tools/context_cost.py`, which prints the same
three routes with a documented token *estimate* on top of the character count
(one token per CJK code point, four characters per token otherwise — an
estimate, because no tokenizer is available offline and adding one is a
dependency decision this project has not made):

| Route | chars | est. tokens |
|---|---|---|
| capability card, bounded search envelope | 1963 | 495 |
| capability card, plan only — all a caller needs to act | 827 | 209 |
| FeatureScript reference search | 4422 | 1106 |
| full guide page (`modeling`) | 6938 | 1735 |
| `圆角` → reference search | 2 | 1 (finds nothing) |

Raw output: `onshape_docs/verification/context-cost-2026-09-19.json`. The
actionable context for a capability call is the 209-token plan, not the
495-token search envelope: the generated source (a further 259 tokens) is built
on the server and never has to reach a caller, which is the specific saving the
capability contract exists to produce.

Still open, and stated as such rather than papered over: the token column is an
estimate, so "no model-in-the-loop token measurement" is narrowed, not closed.
The in-the-loop *sufficiency* half has exactly one live data point — the P6
capability run, where the card alone was enough to produce a call that worked on
the real machine first try (see
[`onshape_docs/verification/capability-live-run-2026-09-19.md`](../../onshape_docs/verification/capability-live-run-2026-09-19.md)).
A real measurement needs a tokenizer or a client that reports usage, and neither
is available here.

**P5 — Tool surface audit (G6).** Produce `Keep` / `Merge` / `Internal-only` /
`Capability` / `Remove` for all **108** tools. Classification only; no mass
refactor in this phase.
*Gate:* every tool has a classification with a reason; generated reference and
runtime prompt stay consistent.

Delivered: [`architecture/TOOL_SURFACE_AUDIT.md`](../architecture/TOOL_SURFACE_AUDIT.md)
classifies all 108 registered tools as they stood in P5 — 59 `Keep`, 26
`Internal-only`, 11 `Capability`, 8 `Merge`, 4 `Remove` — with a reason per row
and a follow-up list in the order the work should be attempted.
`test_tool_surface_audit` is the gate: it re-parses the page and fails on an
unclassified or invented tool, an unknown verdict, a `Merge` that does not name a
registered survivor, a thin or placeholder reason, counts that disagree with the
table, or a verdict that contradicts the tool's recorded exposure. The two
`Internal-only` tools that were still default-exposed (`browser_fix_instances`,
`browser_group_instances`) are named in the follow-ups rather than quietly
tolerated; follow-up 2 then hid them, and follow-up 3 (the eight merges) hid the
absorbed names too, so the semantic `tools/list` is 72 tools and every recorded
`Internal-only` tool is default-hidden.

Follow-up 1 was resolved on 2026-09-19 and the page now carries 106 rows: the two
print-analysis stubs (`browser_print_orientation_check`,
`browser_print_optimize_part`) were archived to
`history/legacy/ARCHIVED_BROWSER_PRINT_TOOLS.md` because they returned a
compatibility result instead of doing their named job, while `browser_delete_tab`
and `browser_draw_part` were reclassified `Internal-only` because the owner
corrected the reason they are hidden — high risk, not uselessness. Follow-up 3
then executed all eight `Merge` rows on the same day: every absorbed name keeps
working as a deprecation wrapper (`deprecated` + `useInstead`) and is no longer
advertised, so those rows became `Internal-only` too. Verdicts are therefore
59 `Keep`, 36 `Internal-only`, 11 `Capability`, 0 `Merge`, 0 `Remove`.

The audit phase itself was classification only; the archive and the merges above
are the follow-ups since executed, so the generated reference, the runtime prompt
and the ordinary `tools/list` changed with them.

**P6 — Thread capability (G7). Delivered 2026-09-19.** First true
capability-card proof, on the only real coverage hole.
*Gate:* custom coarse pitch produces real geometry; cosmetic-only behavior is
rejected rather than silently substituted.
*Result:* `custom.spiral_ridge` was called as a capability (bounded values only,
no script) at a coarse non-standard 8 mm pitch. It generated 2377 chars of
`fCylinder` + `opHelix` + `opSweep` + `opBoolean` source — no `externalThread`
and no cosmetic-thread call exists in the capability, so there is nothing to
substitute — compiled with 0 notices and applied to a computed Feature List row
with one solid body, at **0 REST calls**. A `dry_run` first showed the same
source text so the caller can reject a cosmetic implementation before mutating.
Evidence: `onshape_docs/verification/capability-live-run-2026-09-19.md`
§ Post-refresh live run.
*Scope limit:* only the self-contained capability is fully agent-invocable;
`custom.fillet` / `custom.extrude` / `custom.hole` still need a human geometry
pick, which that record documents.

**Deferred (D5):** native lowering of FS features to toolbar transactions, sketch
compiler, custom-island extraction, cross-backend FreeCAD implementation,
capability auto-promotion, new CAD DSL.

## 12. Verification mapping

Compose checks from `../verification/MATRIX.md`; do not invent new gates.

| Work | Required offline evidence |
|---|---|
| This roadmap and routing | project-layout tests; docs verification |
| Browser leg (P1, P2) | browser-mode tests, browser plan completion tests; real browser work only after mock/fixture/dry-run, read-only selector verification, stated cloud mutation, confirmation, domain-state verification |
| FeatureScript source (P2, P6) | `fs_local_check.py` plus `test_static_guards` (including the measured-zero-FP import rule and the masked symbol scan); `test_local_check_gate` for the warn-then-confirm rule; authorized upload/live compile only |
| REST operations (P3) | quota guards; explicitly budgeted live fact only |
| Capability cards (P4) | `test_capabilities` (contract, symbols, precedent), `test_capability_retrieval` (card-vs-reference cost, no expansion, both discovery entries, invocation shape) |
| Capability apply path | `test_browser_apply_path` (badged row, label fallback, non-match inventory, ambiguous label never guessed; waits are bounded conditions) |
| Live capability evidence | `onshape_docs/verification/capability-live-run-2026-09-19.md`; browser-only, 0 REST calls, read back with the read-only feature tools |
| Tool surface (P5) | MCP, runtime-prompt, and generated-reference `--check` |
| Tool-list compression (G5, 2026-09-21) | `test_tool_gateway_view` (advertised surface, curated coverage of every category, measured bounds, host-local switch precedence, hidden names still dispatch through their handlers, index paging and refusal) and `test_row_evidence_compaction` (one canonical row set plus counts, opt-in restores the full answer, the handler value is not mutated); `dev/tools/context_cost.py` regenerates `onshape_docs/verification/context-cost-surfaces-2026-09-21.json` |
| Idle-session health probe (2026-09-21) | `test_session_health` (every verdict reachable, one recovery action each, never starts a browser, a missing read never becomes `ok`) plus the `browser_session` action-enum assertions in `test_browser_mode` |

Never claim an unexecuted check passed.

## 13. Open decisions

1. Whether the capability card layer is data files under an existing module or a
   new module. (Phase 0-style decision; must not become a second registry.)
2. Whether `cad.*` cards are static data or generated from capability contracts.
3. How much of the `BROWSER_PLANNED_TOOLS.md` planned surface survives P5.
4. Whether the deferred native-lowering phases are permanently retired or
   revisited if a FS-only ceiling is demonstrated.
5. How a selection-bound capability reaches an automated caller: a bounded
   geometry-selector value, a semantic-target channel like the one the native
   blend path already uses, or restricting cards to self-generating geometry.
   The 2026-09-19 live run proved a caller with scalars only cannot accept
   `custom.fillet` / `custom.extrude` / `custom.hole`.
6. When to refresh the Windows deployment from this repository. The live server
   is a copy (`C:\MCP\onshapescript`) that runs behind the repository, so the
   capability layer, the not-computed guard and the row-matcher fix are not live
   yet. Refreshing is a deployment action: it restarts the server and closes the
   browser process, so it needs its own approval and must preserve the
   deployment-local `browser-state.json` / `browser.local.toml` and the
   persistent browser profile.

None of these block P1.

## Provenance

- External input: "Onshape Group research plan" (16 sections, approximate numbers),
  supplied by the owner 2026-09 with the note that the thinking, not the numbers,
  is sound.
- Owner decisions D1–D6: recorded 2026-09 in direct reply to the review.
- Repository review and evidence: Mnemon project document
  *Onshape FS 自定义特征方案评审与仓库现状核对*; sources listed in §1.
- Subordinate documents: `FS_HYBRID_COMPILER_INTEGRATION.md`,
  `DYNAMIC_TOOL_DISCOVERY.md`, `BROWSER_FS_SEMANTIC_TOOLS.md`,
  `BROWSER_MODELING_GAPS.md`, `BROWSER_SIX_LEVEL_SEMANTICS_AND_FDM_PLAN.md`,
  `BROWSER_PLANNED_TOOLS.md`, `BROWSER_GENERIC_L2_SEMANTICS.md`.
- All numbers in §4 and §8 are derived from generated indexes or vendored
  references and are reproducible offline.
