# Whole-feature capability live run (2026-09-19)

This record closes the machine half of the P2 gate in
[`docs/roadmap/FS_FIRST_CONTROLLING_ROUTE.md`](../../docs/roadmap/FS_FIRST_CONTROLLING_ROUTE.md):
it compiles the generated capability sources on the live server and applies one
of them to real geometry, entirely through the browser UI at **0 REST calls**.

It also records two things that outlive the run: the live runtime was **not**
this repository, and the workspace apply path carried a matching defect that
this run found and fixed.

## Scope and safety

- Onshape REST requests during this run: **0**. `LIVE_API_ENABLED` stayed unset;
  no REST tool was called and no quota ledger entry was produced.
- FeatureScript server version observed: **3044** (from the deployed source's
  `FeatureScript 3044;` header and the clean server compile of it).
- Mutations: one new document, four Feature Studio tabs, one Part Studio tab,
  one document version, one applied custom feature. All inside the dedicated
  verification document below, never the trophy document.
- The persistent browser session was established from the saved profile and was
  left running; nothing in this run released or restarted it.

## The runtime was a stale deployment, not this repository

The first attempt tried the capability contract the repository documents:

```
browser_deploy_and_apply_featurescript(capability="custom.fillet", dry_run=true)
-> ValueError: script and feature_name are required
```

That message exists nowhere in this repository. The running Onshape MCP server
is the Windows ordinary-stdio deployment at `C:\MCP\onshapescript`, a **copy**
(not a checkout) whose `STDIO_DEPLOYMENT.json` records `nativeStdioToolCount:
80` and `offlineTests: 51`. Measured live, read-only:

| Surface | Running deployment `C:\MCP\onshapescript` | This repository at `52d43ff` |
|---|---|---|
| registered tools (`mcp_tool_catalog status`) | 106 | 108 |
| visible tools | 80 | 80 |
| `onshape_browser_mode/capabilities.py` | **absent** | present (4 cards) |
| `browser_deploy_and_apply_featurescript` | `script` + `feature_name` only | also `capability` + `values` |
| `semantic.py` not-computed guard | **absent** | present |

The counts in that table are the measurement at `52d43ff`. The repository later
dropped to 106 as well, when the two print stubs were archived on 2026-09-19, so
the two registries now agree on the **number** while still differing in content:
live `browser`=68 / `featurescript`=10 / `rest`=17 against repository
`browser`=66 / `featurescript`=11 / `rest`=18 at archive time. The registry
`fingerprint` is therefore the discriminator — live
`754218124c1b28c4…`, repository `272cc39d6f0fa4b3…` — exactly as recorded in
`../experience/browser-modeling.md` §14.

Consequences that bound this record:

- The capability **layer** (`capability=` argument, card search, catalog
  capability route) was never exercised live and is not verified here. The run
  drove the generated sources through the deployment's raw-`script` path.
- The deployment's `build_part` accepts on `inserted AND feature-present AND
  parts > 0` without the not-computed guard, so its `built` field is not by
  itself proof of a computed row. This run therefore read the Feature List and
  part list directly with `browser_get_partstudio_features` and reports those
  reads, not the tool's verdict.
- The deployment's `deploy_featurescript` **is** byte-identical to this
  repository's, and its `deployed` flag requires commit-accepted **and**
  byte-verified source **and** `compiled`. That flag is usable evidence.

Detecting this class of problem requires no REST call: the live
`mcp_tool_catalog` registry count and a `selectors`-independent probe of one
capability-only argument are enough. Recorded as a lesson in
[`onshape_docs/experience/browser-modeling.md`](../experience/browser-modeling.md).

## Target document

Created for this run and kept as the evidence artifact:

- document `86e0af79961a09acafcdb72a`, workspace `07cea03dcf0556d0d1a8a3ac`
- `Part Studio 1` `b1d0caa1e06f62da338d0ef8`, `Assembly 1` `e96ee8c545fad133f90079ce`
- `Spiral ridge FS` `28387ea6f126e7d45ef539ac`, `Spiral ridge PS` `05406f02482e1d943d80dc3e`
- `cap fillet` `53ab31c7213e133eaf2690b0`, `cap extrude` `7b6e6e7ab8d44b00cc8e5e10`,
  `cap hole` `be1608994ebaca85c5f80d88`
- version `capability verification V1`

## Source identity

Every deployed script was re-read from the server's saved diagnostic package and
compared with the locally generated capability source. After CRLF
normalization the only difference is the trailing newline the local files carry
and the submitted script does not — **the deployed text is the capability's own
generated text**, so these compile results are about the capability sources and
not about a hand-edited copy.

| Capability | Feature Type Name | Exact source | Local check | Server compile |
|---|---|---|---|---|
| `custom.spiral_ridge` | `Spiral ridge` | 2375 chars / 58 lines, sha256 `2560b7d98008…c6b06f87` | clear | `compiled: true`, 0 errors, 0 warnings, 0 notices |
| `custom.fillet` | `Bounded fillet` | 975 chars / 25 lines, sha256 `fc27384b5778…5949fa16` | clear | `compiled: true`, 0 errors, 0 warnings, 0 notices |
| `custom.extrude` | `Bounded extrude` | 1512 chars / 38 lines, sha256 `8ce808031b8d…dfb6ca8f4` | clear | `compiled: true`, 0 errors, 0 warnings, 0 notices |
| `custom.hole` | `Bounded hole` | 1862 chars / 41 lines, sha256 `f46be53930fc…768edc05` | clear | `compiled: true`, 0 errors, 0 warnings, 0 notices |

Each deploy also produced a local diagnostic package under the deployment's
`onshape_browser_mode/outputs/fs_diagnostics/<captureId>/` holding the source,
`compile-result.json`, and a manifest. The sha256 above is the value the deploy
reported for the source it byte-verified.

`custom.spiral_ridge`'s card template was additionally confirmed against the
precedent generator: the two differ **only** in parameter values (card defaults
12 mm / 4 mm / 1.2 mm / 0.8 mm / 24 mm / anticlockwise versus the live call's
10 / 5 / 2 / 1 / 30 / clockwise), so the card renders the precedent's structure.

## Apply and compute

`custom.spiral_ridge` was applied to `Spiral ridge PS` and computed:

| Signal | Value |
|---|---|
| Feature List row | `Sr Spiral ridge 1`, `isUserFeature: true`, `hasError: false` |
| Part list | `零件数 (1)` |
| Part | `Spiral ridge cylinder` |
| Curves | `曲线数 (1)` |

That is the whole chain working end to end with no REST call: a locally
generated script is written into a Feature Studio, compiles on the server,
appears as a workspace custom feature, and builds a solid body.

A custom feature also presents in the UI exactly like a native one. Opening
`Bounded fillet` produced a real feature dialog
(`.ns-dialog-panel.feature-dialog`, header `Bounded fillet 1`) whose fields are
the precondition annotations in order — `["Edges to fillet", "Radius",
"Tangent propagation"]` — and a pending `Bf Bounded fillet 1` Feature List row.
The dialog was cancelled; the Part Studio was re-read as `特征 (5)` with only
the spiral ridge row and one part, so no pending row survived.

## Finding: a selection-bound capability cannot be accepted without a pick

`custom.fillet`, `custom.extrude` and `custom.hole` declare their target
geometry as a required `Query` in the precondition. With that query unpicked,
Onshape disables acceptance:

```
okCls: "ns-dialog-button-ok button-ok disabled", okDisabledAttr: "disabled"
```

So the contract as delivered — *caller supplies bounded values only; queries
live in the generated feature's precondition* — is **not sufficient for a
caller that cannot pick geometry**. A scripted caller can deploy, compile and
list these features, but cannot complete them; only a capability that generates
its own geometry from numbers (`custom.spiral_ridge`) is fully invocable end to
end. No geometry claim is made for `custom.fillet`, `custom.extrude` or
`custom.hole` in this record, and none should be inferred from their rows.

Carried into the roadmap as an open design item rather than silently patched:
the native-feature path already has a semantic-target selection channel
(`browser_apply_blend`), so the capability layer needs an equivalent, or
self-contained geometry, before those three cards are agent-invocable.

## Defect found and fixed: the workspace row matcher

The first apply attempt failed with
`feature 'Spiral ridge' must match exactly one workspace dropdown item`, even
though the live dropdown did contain it. Reading the live DOM:

```html
<div class="tool-icon"><div class="tool-initials-icon">Sr</div></div>
<span class="tool-label">Spiral ridge</span>
```

The row renders a two-letter Feature Studio badge before the name, so the row's
`innerText` is `"Sr\nSpiral ridge"` (measured for all four rows: `Sr`, `Bh`,
`Bf`, `Be`). `insert_custom_feature` compared that whole string to the bare
feature name with `==`, which can therefore never match a real workspace row.
The documented measured flow inserted through the *insert dialog*
(`.select-item-dialog-item-row`), so this path had no live evidence behind it.

Fixed by matching the row's name element (`CUSTOM_FEATURE_MENU_LABEL =
".os-tool-dropdown-content .tool .tool-label"`), falling back to the last
non-empty text line for a row without a label element, and reporting the
available labels on a non-match. Covered by four offline cases in
`dev/tests/test_browser_apply_path.py` including the badged row, the fallback
row, the non-match inventory, and two rows sharing one label (never guessed).
The running deployment still carries the old matcher; the fix takes effect on
the next deployment refresh.

Two further exact-text comparisons use the same shape —
`actions.py` (`"删除"` context-menu item) and `transactions.py` — and were
**not** exercised live in this run, so they are not claimed either way.

## Sequence facts worth keeping

- A custom feature is **not insertable until the document has a version**. The
  insert dialog offers a `创建一个版本` prompt on its `当前文档` tab only; the
  deployment's `create_version` step inside `deploy_and_apply` reads the dialog
  immediately after a tab switch and found `version prompt not present`,
  because the dialog had not rendered yet.
- The insert dialog's default active tab was `其他文档`, where no prompt exists.
  The prompt appears after activating `当前文档`
  (`.feature-studio-insert-dialog .os-dialog-tab`). `browser_create_document_version`
  requires the dialog to be open already; `browser_open_insert_feature_dialog`
  (L3, default-hidden) is the tool that opens it.
- A plain `element.click()` from `page.evaluate` did **not** open the toolbar's
  workspace dropdown; a real mouse click through `browser_click` did. The
  toolbar button carries its label in `data-bs-original-title`, not `title`.

## Reproduce

Read-only or 0-REST unless noted; `confirm_mutation` was required for the
mutating steps.

```text
browser_session(status)                                   # loginConfirmed: true, no human action
browser_create_document("FS capability verification")     # mutation
browser_spiral_ridge(10, 5, 2, 1, 30, clockwise=true)     # deploy + apply + part, mutation
browser_open_insert_feature_dialog()                      # L3, opens the dialog
browser_click(".feature-studio-insert-dialog .os-dialog-tab", "当前文档")
browser_create_document_version("capability verification V1")   # mutation
browser_deploy_and_apply_featurescript(script=<fillet>, feature_name="Bounded fillet",
    feature_studio_tab="cap fillet", apply=false)         # per capability, mutation
browser_get_partstudio_features()                         # read-only acceptance
```

## Boundaries

- Not verified here: the capability layer's own argument path, the catalog
  capability route, `custom.fillet` / `custom.extrude` / `custom.hole` geometry,
  any REST path, and the print/geometry backends.
- The applied spiral ridge is a live artifact, not a shipped model; the trophy
  model and its Feature Studio were untouched.
- The deployment refresh that would put this repository's capability layer,
  not-computed guard and row-matcher fix on the live server is a deployment
  action, not part of this run, and was deliberately not performed while the
  browser session had to stay alive. **Superseded the same day**: the refresh
  was performed and the capability layer then ran live — see
  [Post-refresh live run](#post-refresh-live-run-same-day) below.

## Post-refresh live run (same day)

Everything above measured a **stale** deployment. The refresh it deferred has
since been performed, so this section is the first live evidence for *this
repository's* code on the real machine.

### Runtime identity, before and after the refresh

Refresh `20260919T131425Z-tool-surface-merges` at repository commit `75c0461`:
93 files shipped, all **571** repository source files re-hashed and matching,
backup pre-images written for the 53 overwritten files, backend generation
1 → 2 with 3 client streams preserved, and **0 REST calls / 0 cloud mutations**
from the refresh itself.

| Surface (`mcp_tool_catalog status`) | Before (stale) | After | This repository |
|---|---|---|---|
| registered tools | 106 | 106 | 106 |
| ordinary `tools/list` | 80 | **72** | 72 |
| fingerprint | `754218124c1b28c4…` | `a4787372986e8eba…` | `a4787372986e8eba…` |
| modules browser / featurescript / rest | 68 / 10 / 17 | **66 / 11 / 18** | 66 / 11 / 18 |

The refresh closes every consequence the earlier section listed: the capability
layer is present, the not-computed guard is present, and the workspace row
matcher is fixed. The earlier "the runtime was not this repository" finding is
therefore resolved, not deleted — it remains the reason the freshness check
before live work exists.

The recycle terminates the browser process, and closing the browser logs the
Onshape **web** session out (the pitfall in
[`../experience/browser-automation.md`](../experience/browser-automation.md) §2),
so one human login was required afterwards. The 520 MB persistent profile
survived byte-identically (`Default/Network/Cookies` and `Default/Login Data`
present); the profile is what makes that login cheap rather than a fresh setup.

### P1 — the warn-then-confirm gate, live

The gate was exercised through the real server with `confirm_mutation: true` and
**no** acknowledgement, using the same source the offline contract tests use:

```text
browser_deploy_and_apply_featurescript(
    script="FeatureScript 3044;\nvar x = 1;", feature_name="Gate probe",
    confirm_mutation=true)
```

| Signal | Value |
|---|---|
| `acknowledgementRequired` | `true` |
| `localCheck.errorCount` / `warningCount` | 1 / 0 |
| `localFindings` | `["missing or malformed 'import(path : ..., version : ...);'"]` |
| `nextCall.arguments.acknowledge_local_findings` | `true` (same call plus the acknowledgement) |
| `browser_session(status)` after the call | `uninitialized` — **no browser action** |

The last row is the important one: it is independent, read-only evidence that a
gated call launches nothing and writes nothing, which the payload alone could
not establish. The new-schema-only arguments (`capability`, `values`,
`acknowledge_local_findings`) are also live, so the schema — not just the
fingerprint — proves the refresh landed.

### P1 — a pathological source fails closed, live

The gate deliberately stays silent for warnings, so a source that the local
checker *passes* can still be wrong. This probe makes that concrete: it has a
malformed `LengthBoundSpec` literal (the capability sources pass the named
constant `LENGTH_BOUNDS`, not an inline map) and calls an undefined symbol.

Local checker first, zero cost: **0 errors, 1 warning** — so the gate does not
fire and the call proceeds to the machine. The live result:

| Signal | Value |
|---|---|
| `deployed` | **`false`** |
| `compiled` | `false` |
| `verified` (editor text equals the submitted source) | `true` |
| `commitAccepted` (Commit button enabled → disabled) | `true` |
| server errors read back | 5, all `severity: error`, from `featureScriptNotice` |
| diagnostic package | `20260919T132740314887Z-0563066ce97b`, source sha256 `0563066ce97b…`, 457 chars / 13 lines |
| Feature List rows produced | **0** |

`deployed: false` is the fail-closed verdict, and it is the conjunction of
committed **and** byte-verified **and** compiled — the compile term is what
fails. `commitAccepted: true` is worth stating plainly rather than hiding: the
server *saves* the source and *then* rejects it, so a broken source does land in
that Feature Studio. Nothing is silently substituted for it — a Feature Studio
that does not compile emits no feature specification, so no workspace custom
feature and no Feature List row appear.

The blast radius was read independently and is contained: the only new document
element is the `gate check` Feature Studio this probe created, and the Part
Studio feature list still shows exactly the one applied spiral-ridge row.

This run therefore closes the "real-machine apply/verify loop over pathological
input" item that
[`../../docs/roadmap/FS_FIRST_CONTROLLING_ROUTE.md`](../../docs/roadmap/FS_FIRST_CONTROLLING_ROUTE.md)
left open for the P1 gate.

**Finding — a local-check blind spot (open).** The import rule accepted a source
whose bound-spec literal the live parser rejects. That is consistent with the
documented "the vendored reference can lag" limitation and is *not* a
regression, but it does mean "local check clear" is a statement about the rules
that exist, never a compile guarantee. The 5 server errors are persisted, so a
future rule can be written against the real corpus rather than a guess.

**Finding — `partNames` carries the trailing section header (open).**
`build_part`'s parsed list is `["Spiral ridge cylinder 曲线数 (1)"]` while
`partsText` is correct (`零件数 (1) Spiral ridge cylinder 曲线数 (1)`), so the
normalizer swallows the following `曲线数 (1)` header into the last part name.
`partsText` is the field to read until this is fixed.

### P6 — thread capability, live, with a coarse custom pitch

The only real FeatureScript coverage hole (roadmap §8: Thread has
`externalThread` + `cosmeticThreadUtils` only, both standard-size and cosmetic)
is served by the `custom.spiral_ridge` capability. Its gate: *custom coarse
pitch produces real geometry, and cosmetic-only behavior is rejected rather than
silently substituted.*

Called as a capability — values only, no script — through the real server:

| Input | Value |
|---|---|
| capability | `custom.spiral_ridge` |
| values | `base_radius 10`, `pitch 8` (coarse, non-standard), `ridge_width 2`, `ridge_height 1.5`, `length 32`, `clockwise true` |

A `dry_run` first confirmed the contract with no browser action: the card
validated and echoed the bounded values, generated source
2377 chars / 58 lines, and the local check reported **0 errors / 0 warnings**, so
`acknowledgementRequired` was `false`.

The generated source is the cosmetic-rejection evidence: it is built from
`fCylinder`, `opHelix`, `newSketchOnPlane` + `skRectangle` + `skSolve`,
`opSweep`, `opBoolean(UNION)` and `setProperty`. There is no `externalThread`
and no cosmetic-thread call anywhere in the capability, so a cosmetic thread
cannot be silently substituted — the 8 mm pitch is real helical geometry. The
`dry_run` source text is the observable proof, and it is what a caller can read
*before* spending a mutation.

Then the real deploy and apply:

| Signal | Value |
|---|---|
| `deployed` / `verified` / `compiled` | `true` / `true` / `true` (`commitAccepted: true`) |
| server notices | 0 errors, 0 warnings |
| applied Feature List row | `Sr Spiral ridge 1`, `isUserFeature: true`, `hasError: false` |
| `featurePresent` / `featureComputed` / `featureError` | `true` / **`true`** / `false` |
| Part list | `零件数 (1)`, part `Spiral ridge cylinder`, `曲线数 (1)` |
| Feature List header | `特征 (5)` |
| diagnostic package | `20260919T132818506620Z-a9dc2d5ee42c`, source sha256 `a9dc2d5ee42c…` |
| Onshape REST calls | **0** |

`featureComputed: true` is the not-computed guard doing its job: the guard is
part of the refreshed code, so this row is proof of a *computed* feature rather
than of a row that merely exists.

### Boundaries of this section

- Still not verified: the catalog capability route,
  `custom.fillet` / `custom.extrude` / `custom.hole` geometry (their targets are
  required `Query` picks a scripted caller cannot make), any REST path, and the
  geometry/print backends.
- Both applies used the dedicated `FS capability verification` document, never
  the trophy document.
- `LIVE_API_ENABLED` stayed unset for the whole run.

## REST Feature-List CRUD live confirmation (same day, later)

The offline P3 slice had delivered builders and parsers for four Feature-List
endpoints and the missing Feature List READ, with every payload
constructed-and-reviewed and nothing ever sent. This section records the one
authorized run that closed that gate.

### Authorization and budget

The owner authorized a hard-budgeted run under the project's `3(3)`-style rule
for live requests — a stated unique fact per call, one attempt each, no retry —
and chose the mechanism **"1 read + 4 writes"**. `BudgetGuard(5, ..., max_attempts=5)`
gated the process; `LIVE_API_ENABLED=1` was set for that one process only, never
as a default, and never in the deployed copy.

### Target

A scratch Part Studio created for the purpose, holding a single `Spiral ridge`
custom feature:

| field | value |
|---|---|
| document | `86e0af79961a09acafcdb72a` |
| workspace | `07cea03dcf0556d0d1a8a3ac` |
| element (`Part Studio 2`) | `53565f0b68cb86960a092d39` |
| feature | `F523rtc3Xx2J8UH_0` (`spiralRidge`, namespace `e28387ea6f126e7d45ef539ac::md300f71d986982a9df2b8733`) |

The script takes the three ids as required arguments and refuses to read or write
`onshape-state.json`, so it cannot mutate the trophy document by accident.

### What was sent, and what came back

Every call returned 200 with exactly the schema the vendored OpenAPI declares for
its `operationId`:

| # | call | response schema | confirmation |
|---|---|---|---|
| 1 | `GET .../features?rollbackBarIndex=-1` | `BTFeatureListResponse-2457` | returned `F523rtc3Xx2J8UH_0` with its serialized definition + `featureStates` map |
| 2 | `POST .../features/updates` (suppress) | `BTUpdateFeaturesResponse-1333` | `features[0].suppressed: true`, `featureStatus: "OK"` |
| 3 | `POST .../features/featureid/F523…` (replace, fed from #1, renamed) | `BTFeatureDefinitionResponse-1617` | `featureState.featureStatus: "OK"`, `feature.name` ends `(P3 rename)` |
| 4 | `POST .../features/rollback` body `{"rollbackIndex": -1}` | `BTSetFeatureRollbackResponse-1042` | `rollbackIndex: 1`, `microversionId.theId` present |
| 5 | `DELETE .../features/featureid/F523…` | `BTFeatureApiBase-1430` | versioning envelope only |

Domain verification cost **zero REST quota**: after the run, a browser read of the
Feature List showed `特征 (4)` (only the default geometry) and `零件数 (0)`. The
scratch Part Studio is empty.

### Cost, stated plainly

- Authorized: 5 requests (1 read + 4 writes).
- Spent: **7** — the 4 writes above, plus 3 reads: the first read was lost to a
  defect in the one-off script (it evaluated the body *before* recording it and
  exited on the empty result), and the read then had to be made twice because of
  the `rollbackBarIndex` finding below.
- The overage is **2 reads**, no writes beyond the authorization. Both extra reads
  bought recorded evidence; neither was a retry of a mutation.

### Finding (SUPERSEDED — see the follow-up section below)

> The explanation first written here was **wrong** and is kept only so the
> correction is visible. The read discrepancy was not about `rollbackBarIndex`.

Two calls to the same endpoint on the same element disagreed:

- **no `rollbackBarIndex` argument** → `"rollbackIndex": 0`, `"features": []`,
  `featureStates` covering only the four default features. The UI showed one user
  feature row (with the `edited selected` classes) and its part was present.
- **`rollbackBarIndex=-1`**, after a page reload → `"rollbackIndex": 1`,
  `features` holding that feature, `featureStates` covering it.

Either the server's effective default is not the `-1` the vendored OpenAPI
documents, or the feature only reached the workspace on the page reload between
the two calls. The body of the no-argument call is preserved as
`temp/p3_live/read-body-no-rollback-param.json`.

### Secondary observation

A custom feature's serialized definition read back with `"parameters": []` and
`"parameterLibraries": []` (the row had been inserted with its spec defaults).
Posting that definition back through `updatePartStudioFeature` was accepted and
returned `featureStatus: "OK"`, so an empty parameter array is not a rejection
condition — worth knowing before treating "empty parameters" as a corrupt read.

### Ledger evidence

The repository's passive ledger (`onshape_rest_api_mode/config/api-usage.json`)
recorded every attempt, all 2xx. The two `POST /api/a` and `/api/b` rows below it
predate this session (a ledger self-test) and are not part of the run:

| time (UTC) | method | status | path (tail) |
|---|---|---|---|
| 13:38:03 | GET | 200 | `.../e/53565f0b68cb86960a092d39/features` — the read whose body the script discarded |
| 13:39:15 | GET | 200 | `.../features` — no `rollbackBarIndex`; empty `features` |
| 13:40:53 | GET | 200 | `.../features` — with `rollbackBarIndex=-1`; returned the feature |
| 13:41:23 | POST | 200 | `.../features/updates` |
| 13:41:25 | POST | 200 | `.../features/featureid/F523rtc3Xx2J8UH_0` |
| 13:41:27 | POST | 200 | `.../features/rollback` |
| 13:41:28 | DELETE | 200 | `.../features/featureid/F523rtc3Xx2J8UH_0` |

No 4xx or 5xx was seen, so nothing was retried and no failure shape was recorded.

### Reproduce (offline — no server needed)

```
python3 -m unittest dev.tests.test_rest_feature_list
```

`LiveReplayTest` feeds the recorded bodies through the production parsers, and
`FixtureTest` asserts each `request.json` still equals the builder output for the
ids its `metadata.json` records. The one-off script
(`temp/p3_live/feature_list_live.py`) is explicitly marked one-off with its
invalidation condition and does not need to run again.

### Boundaries of this section

- Only the Feature List family was touched. No other REST endpoint was called.
- The run did not test a *failing* payload: every authorized call was expected to
  succeed, and all five did. An error-shape fixture is still unrecorded.
- `LIVE_API_ENABLED` was set for the one process; the deployed copy still has no
  live REST enabled and its ledger is untouched by this run.

## Follow-up probes: the read discrepancy, resolved

A second authorization (10 requests) went to the loose end the section above left
open, plus the failure shape the run never saw. The UTC span of the whole effort
is 2026-09-19T13:38Z to 2026-09-20T00:53Z.

### Probe 1 — is `rollbackBarIndex` filtering the read? (3 requests)

**Target:** `05406f02482e1d943d80dc3e` (`Spiral ridge PS`), whose custom feature
was committed by the P6 capability run **hours** before this probe, so nothing
here can be a pending browser insert.

**Hypothesis, written before sending:** if the no-argument read returns the
feature, the documented `-1` default is effective and the P3 discrepancy was a
browser/REST handoff; if it returns `"features": []` while `-1` does not, the
effective default is 0 and every read must pass the argument.

**Design:** three reads of the same element in one run, no browser activity and no
reload in between, differing only in the argument: absent, `-1`, `0`.

| request | HTTP | `rollbackIndex` | features | default features |
|---|---|---|---|---|
| no argument | 200 | 2 | 2 | 4 |
| `rollbackBarIndex=-1` | 200 | 2 | 2 | 4 |
| `rollbackBarIndex=0` | 200 | 2 | 2 | 4 |

**Result: identical.** The hypothesis is refuted in the informative direction:
`rollbackBarIndex` does not filter the returned list at all, the spec's documented
default is fine, and `rollbackIndex` reports the **element's own rollback-bar
position** rather than echoing the request. (The `0` read is the decisive one: a
requested top-of-list evaluation still returned a bar index of 2 and both
features.)

**Therefore** the earlier `"rollbackIndex": 0` / `"features": []` was a *true*
statement about that element at that moment, and the feature's arrival in the
workspace coincided with the page reload. The P3 write-up blamed the absent
argument; that explanation is superseded (the section above is kept, marked, so
the correction is auditable).

Raw bodies: `onshape_docs/verification/feature-list-read-probe-2026-09-20.json`.

### Probe 2 — what does a refusal look like? (1 attempt, 0 quota)

**Hypothesis:** a `DELETE` naming a feature id that cannot exist returns a 4xx
whose body is a JSON error envelope, and that envelope is otherwise unobtainable.

`DELETE .../features/featureid/P3ProbeNoSuchFeature_0` →

```
HTTP 404
{"moreInfoUrl": "", "message": "Feature not found", "status": 404, "code": 9999}
```

The probe's own ledger delta was **0**: the "4xx does not count toward the annual
limit" rule is now measured rather than cited. The envelope is *not* the
operation's declared response schema, so a caller must branch on the HTTP status;
`test_rest_feature_list.RefusalShapeTest` pins both the recorded body and the
property that the success parser returns an all-`None` summary for it, so an error
body cannot be read as a success.

Raw record: `onshape_docs/verification/feature-list-error-shape-probe-2026-09-20.json`.
Vendored fixture: `dev/tests/fixtures/onshape/feature-list/refusal-deletePartStudioFeature/`.

### What the follow-up established, in one line each

- `rollbackBarIndex` is not a filter; `rollbackIndex` is the element's real bar.
- **A browser-inserted custom feature is not in the workspace until the page is
  (re)loaded**, so its `edited selected` UI row is not evidence that REST can see
  it. This is the browser→REST handoff hazard for the FS-first route.
- A refusal is a 404 with a four-field error envelope, and it costs no quota.

### Boundaries of the follow-up

- Probe 1 read a single element with two features; it was not repeated across
  elements or against a version/microversion URL form.
- The direct reproduction the section above first listed as not-run **was** then
  run, after a human re-login — see the next section.
- The mechanism inside the Onshape client is still unknown: the run observed that
  a reload commits the pending feature, not *how*. An explicit save and a tab
  switch were not tried as alternative commit triggers.

## Reproduction: the browser→REST handoff, and the add endpoint (2026-09-20)

Probe 1 eliminated the query argument but left the handoff as an inference. A
second pass, with the owner present and re-logged-in, turned it into a controlled
reproduction on the scratch `Part Studio 2` (`53565f0b68cb86960a092d39`), which
was empty at the start. Every step below is in
`onshape_docs/verification/browser-rest-handoff-2026-09-20.json`.

| # | step | REST calls | observed |
|---|---|---|---|
| 1 | `browser_insert_custom_feature` (`Spiral ridge`) | 0 | `inserted: true`, `errored: false`, regeneration waited 7553 ms, part `Spiral ridge cylinder` present; DOM row `Sr Spiral ridge 1` with classes `related-highlight edited selected ns-user-feature` |
| 2 | `GET .../features`, no reload | 1 | **200, `rollbackIndex: 0`, `features: []`** |
| 3 | the same read ~80 s later, still no reload | 1 | **200, `rollbackIndex: 0`, `features: []`** — time alone does not commit it |
| 4 | page reload | 0 | DOM row becomes plain `os-list-item ns-user-feature`; the pending classes are gone |
| 5 | `GET .../features` | 1 | **200, `rollbackIndex: 1`, `features: [FS0ew9p43DwiUAc_0]`** |
| 6 | `POST .../features` (`addPartStudioFeature`) | 1 | 200, `BTFeatureDefinitionResponse-1617`, `featureStatus: "OK"`, new `featureId: FLs0vBdvuflFHIG_1` |
| 7 | `GET .../features` | 1 | 200, `rollbackIndex: 2`, `features: [FS0ew9p43DwiUAc_0, FLs0vBdvuflFHIG_1]` — the REST-added feature is visible **immediately**, no reload |
| 8 | cleanup: two `DELETE`s | 2 | both 200 `BTFeatureApiBase-1430`; a zero-quota browser read shows `特征 (4)` / `零件数 (0)` |

### What this establishes

1. **The read endpoint was never at fault.** `rollbackBarIndex` does not filter the
   returned list, the documented `-1` default is honoured, and `rollbackIndex`
   reports the element's own rollback-bar position.
2. **A browser-inserted custom feature is not in the workspace until the page is
   reloaded.** Step 3 rules out "it just takes a while"; step 7 is the control that
   rules out a read-side caching artefact — a REST-added feature on the *same
   element, moments later* was visible at once.
3. **`addPartStudioFeature` works with the production envelope** — the endpoint
   `operations.instantiate_feature` has always targeted now has live evidence, and
   it became the fifth recorded fixture of the family.
4. **`"parameters": []` is correct, not suspicious.** The generated `spiralRidge`
   spec has an empty `precondition` and bakes the geometry values in as literals,
   so the feature instance legitimately carries no parameters. Geometry changes
   therefore mean a new FeatureScript version, not a parameter edit.

### Cost of this pass

Ten REST attempts, exactly the authorized follow-up budget: 3 for the three-way
read probe, 1 for the refusal probe (which consumed **0** quota, 4xx being free),
3 for the handoff reads, 1 for the add, 2 for cleanup. No mutation was retried; no
4xx was seen except the deliberate refusal probe.

### Boundaries of this pass

- One document, one element, one custom-feature type. Not repeated across elements,
  documents, or the version/microversion URL form.
- **The client-side mechanism is not established.** The run shows a reload commits
  the pending feature; it does not show whether an explicit save, a tab switch, or
  simply more time past the ~4-minute mark would also do it.
- The features created for the probes were deleted; `Part Studio 2` is empty again,
  and the P6 elements were not touched.

## Fix shipped: the insert now verifies the workspace commit (2026-09-20)

The reproduction above turned a false success into a measurable one, so the apply
path was fixed rather than merely documented.

### The code change (0 REST calls to develop or test)

`onshape_browser_mode/actions.py` gains `wait_for_feature_rows` and
`verify_insert_committed`, and `insert_custom_feature` uses both:

1. the matching user-row count is read as a **baseline before any click**;
2. after the accept click, `wait_for_feature_rows(baseline + 1)` waits in-page for
   the row count to grow (regeneration), replacing a name-only visibility wait;
3. one bounded `reload_page` (the existing helper; `wait_until="commit"`, 15 s) —
   the commit check measured above;
4. `wait_for_feature_rows(baseline + 1)` again, bounded at 30 s, so the survival
   check waits for the rows rather than reading them the instant the panel title
   appears;
5. a re-read and re-match, and only then `inserted: true`.

`inserted` therefore means **the workspace kept the feature**, not that a click
landed or a row rendered. The result keeps the pre-reload evidence and adds
`baselineRows` plus a `commit` block (`verified`, `committed`, `reload`,
`survived`, `listed`, `errored`); `verified: false` is reported honestly when the
reload itself fails, and is never upgraded to success. The tool description and
`estimated_seconds` (30 → 45) in `mcp_main/win/mcp/server.py` were updated with it.

### The first version was wrong, and the live run said so

The version shipped at `202609012311Z` used a post-reload **panel wait** plus a
name-based read. Both halves failed in one live insert the same day, which is what
the count-based design above fixes:

| Step | Observed | Verdict |
|---|---|---|
| baseline read | `特征 (6)`, two `Sr Spiral ridge` rows already present | a same-named row was already on screen |
| regeneration wait | `waited: true` after **12 ms** | the old name-only wait matched an existing row — false success signal |
| insert result | `inserted: false`, `commit.verified: true`, `commit.committed: false`, `listed: false`, `特征 (0)`, `零件数 (0)` | the tool reported **not committed** |
| read again, seconds later | `特征 (7)`, `Sr Spiral ridge 3`, `零件数 (3)` | the insert **had** committed: the post-reload read raced the async feature-list render |

So the row and the part were never in doubt; the read was. The lesson is that a
reload announces itself in two stages (title, then rows) and that "a row with this
name is visible" is not a usable signal in a Part Studio that already contains a
row of that name. Both are now encoded as a count comparison against a pre-click
baseline, and both directions have offline tests
(`test_a_same_named_row_that_was_already_there_is_not_the_new_feature`,
`test_the_survival_wait_absorbs_a_slow_post_reload_render`).

### Offline verification

| Check | Result |
|---|---|
| `dev/tests/test_browser_apply_path.py` | 38 tests OK; `InsertCommitVerificationTest` (9 tests) covers both live failure directions, the post-reload read being what the result reports, a failed reload, a row that never appeared (no reload is spent), the survival wait reporting its own timeout as evidence, the verifier in isolation, and an errored row that still reports its error |
| full suite (`unittest discover -s dev/tests`) | **617 OK** (was 602 before this pair of changes); **619 OK** after the signature guard below |
| docs gates (prompt companion, index rebuild, `verify_docs`, tool reference) | all pass |

The FakePage now models the three DOM states separately (`features_before_insert`,
the post-accept `features`, `features_after_reload`) and evaluates the count
predicate itself, so a test can tell "the row this call created" from "a row that
was already there" instead of assuming a mock that always succeeds.

### The corrected path's first live run: a second false negative (2026-09-20)

The correction was deployed and run live against the scratch workbench. It
reported `inserted: false` **again** — but for a different reason, and this time
the failure is inside the fix itself rather than in what it measures.

| Field | Value |
|---|---|
| `baselineRows` | **3** (correct: 3 existing `Sr Spiral ridge` rows) |
| `waits.menu` / `waits.dialog` | waited, 17 ms / 16 ms |
| `waits.regeneration` | `waited: false`, **`elapsedMs: 0`**, `condition: user_feature_row_count`, `minimum: 4` |
| `commit.survived.error` | `TypeError: Page.wait_for_function() takes 2 positional arguments but 3 positional arguments (and 1 keyword-only argument) were given` |
| `commit.verified` / `committed` | `true` / `false` |
| ground truth, ~6 s later | `特征 (8)`, `Sr Spiral ridge 4` present, `零件数 (4)` |

So the insert **had** committed, the count baseline was right, and the tool still
answered "not committed". The wait was called as
`page.wait_for_function(predicate, {…}, timeout=…)`; in playwright-python `arg`
is keyword-only
(`…/.venv/Lib/site-packages/playwright/sync_api/_generated.py:12701`:
`def wait_for_function(self, expression: str, *, arg=None, timeout=None, polling=None)`),
so the argument bundle landed in the keyword-only slot and raised before the page
was ever polled. `elapsedMs: 0` is the signature of that: no polling time at all,
which is not what a 30 s timeout looks like.

Two things about this run are worth keeping:

- **It failed closed, again.** A defect in the *evidence* path degraded to
  `inserted: false` with the exception text in `commit.survived.error` and
  `waits.*.error`, never to a false success. The recorded defect this fix exists
  to remove is the opposite direction (a committed feature reported as applied
  when the workspace had not kept it), and that direction stayed closed.
- **The offline suite could not see it, because the double was more permissive
  than the client.** `FakePage.wait_for_function(self, expression, arg=None, **kwargs)`
  accepted the positional form, so 617 green tests proved the *logic* while the
  *call* was broken. The fix is three-part: `arg=…` in
  `onshape_browser_mode/actions.py`, a `FakePage` whose signature mirrors the real
  one exactly (`expression` positional; `arg`/`timeout`/`polling` keyword-only),
  and `dev/tests/test_static_guards.py::PlaywrightCallSignatureTest`, which
  AST-scans `actions.py` for a `wait_for_function` call with more than one
  positional argument and separately asserts the double's parameter kinds. The
  guard is not vacuous: re-parsing the source with the pre-fix call shape yields
  `positional=2 keywords=['timeout']`, against `positional=1 keywords=['arg',
  'timeout']` for the shipped form.

### The corrected path, exercised live: it holds (2026-09-20)

Third live run, on generation 5, by a scripted caller with no human in the loop
except the login. Pre-insert read: `特征 (8)`, 4 user rows `Sr Spiral ridge 1…4`.
Hypothesis, stated before the call: the baseline is counted as 4, so `minimum` is
5, the regeneration wait returns on the fifth row, and the post-reload survival
wait returns on the same fifth row, giving `inserted: true`.

| Field | Value |
|---|---|
| `baselineRows` | **4** — the four rows that already existed, counted before the toolbar click |
| `waits.menu` / `waits.dialog` | waited, 15 ms / 13 ms |
| `waits.regeneration` | `waited: true`, `minimum: 5`, **202 ms** |
| `commit.reload` | `reloaded: true`, no warnings |
| `commit.survived` | `waited: true`, `minimum: 5`, **18 431 ms** |
| `commit.verified` / `committed` / `listed` | `true` / `true` / `true` |
| `featureRows` (post-reload read) | 5 rows, `Sr Spiral ridge 1…5`, `hasError: false` on each |
| header / parts after the reload | `特征 (9)`, `零件数 (5)` |
| `inserted` | **`true`** |

The hypothesis held on every field. This is the end-to-end certificate the two
earlier runs could not give: the row the call created is distinguished from the
four rows that were already there, and it is required to survive a reload before
the tool says "applied".

One number in that table is a boundary, not a success. The survival wait needed
**18.4 s of its 30 s budget** — 19× the regeneration wait on the same insert,
because the reload re-regenerates every feature in the element and this scratch
workbench now carries five spiral features with five solid parts. The margin is
1.6×, and it shrinks as the document grows, in exactly the direction that
produces a false "not committed" for a committed feature — fail-closed, but
wrong.

That boundary was then closed rather than left as a caveat. Both post-insert
budgets now scale with the element's custom-feature count
(`onshape_browser_mode/actions.py`, `partstudio_wait_budget_ms`):

| Wait | Profile | At 0 features | At 5 | At 40 | Cap |
|---|---|---|---|---|---|
| regeneration | `PARTSTUDIO_REGENERATE_WAIT` (`baseMs` + 2 s/feature) | 30 s | 40 s | 110 s | 300 s |
| commit survival | `PARTSTUDIO_RELOAD_WAIT` (`baseMs` + 8 s/feature) | 30 s | 70 s | 350 s | 900 s |

The count comes from the same pre-insert read as the baseline row count
(`count_custom_features`, which counts `isUserFeature` rows and ignores defaults,
part rows and the `零件数`/`曲线数` markers), and an unreadable or missing count is
treated as 0 — which reproduces the previous fixed budget exactly, so the change
cannot shorten a wait. The result carries a `budgets` block
(`customFeaturesRead`, `regenerationMs`, `commitSurvivalMs`) so the caller can see
what was actually allowed. Both profiles stay capped, because a bounded tool call
that returns "not confirmed" is still better than one that never returns; the
caps are the knobs to revisit if a real model ever needs more. The 5-feature case
that measured 18 431 ms now gets 70 000 ms, a 3.8× margin.

### The `gate check` notice, reused as a local-check rule (2026-09-20)

The same day, the persistent yellow/red FeatureScript notice on the `gate check`
tab was used as a target for the offline checker. The notice is the P1 probe
source from 2026-09-19, whose capture package
(`onshape_browser_mode/outputs/fs_diagnostics/20260919T132740314887Z-0563066ce97b/`)
holds both the source and the server's answer:

| Signal | Value |
|---|---|
| server | `compiled: false`, `errorCount: 5`, all `source: featureScriptNotice` — "no viable alternative at input '(0) * millimeter,'", "missing TOP_SEMI at 'function'", "extraneous input ')' expecting {…, TOP_SEMI}", at lines 4, 8 and 12 |
| local check (before) | `0 errors, 1 warning` — only the unrelated undefined-symbol warning |
| local check (after) | the undefined symbol **and** `map literal at line 8 has an entry without 'key : value': '(0) * millimeter'` |

The rule is in `onshape_docs/query/fs_check.py::check_map_literals`: `{ … }` in
expression position is a map, so every top-level entry needs `key : value`. It is
**warning-level**, per the standing decision that a new local rule never gates a
deploy. Its false-positive gate is the whole vendored mirror: the first version
flagged `cplane.fs`'s lambda body `(x is number) returns boolean =>{ … }`, so `>`
was excluded from the expression-position set; after that, 265 modules produce zero
`map literal` warnings, and `dev/tests/test_static_guards.py` asserts both
directions plus the `gate check` source itself.

### A generated feature with an empty precondition is a black box (2026-09-20)

Owner question: "既然你能搞参数 那这个可爱的伪造特征和官方几乎没有任何区别了"
— which forced the comparison to be checked rather than asserted. It was not
close at first. `generate_spiral_ridge_script` baked the five dimensions as
constants and left the precondition **empty**, so the feature published zero
parameters and Onshape showed its *internals* read-only (`fCylinder` → an
"extrude", `opHelix`, sketch+sweep, `opBoolean`) with nothing editable. The
history row was a valid custom feature; the UI was not an official-looking one.

The rewrite emits one parameter per dimension, with the requested value in the
`LengthBoundSpec` **middle** slot (`[min, default, max]`) and the body reading
`definition.*` (including `const revolutions = length / pitch;` so a dialog edit
to pitch or length cannot leave the helix disagreeing with the parameters):

```featurescript
annotation { "Name" : "Base radius" }
isLength(definition.baseRadius, { (millimeter) : [12.5, 50, 200] } as LengthBoundSpec);
```

Measured live through the browser leg, **0 REST quota**:

| Signal | Value |
|---|---|
| dialog `before` | `baseRadius 10 mm / pitch 6 mm / ridgeWidth 2 mm / ridgeHeight 2 mm / length 30 mm` — i.e. the defaults are the requested numbers verbatim |
| edit + readback | `12 mm` / `40 mm`, `readbackOk: true` |
| after accept | `persisted` matched, `persistenceOk: true`, row `Sr Spiral ridge CN 1` error-free |

So the fake feature now opens a real parameter dialog with editable model
dimensions, which is the observable difference the owner was pointing at.

### Annotation strings are ASCII-only; four deploys measure it (2026-09-20)

The same request asked for the Chinese-name work on both sides. The first two
attempts were refused by the server, and the captures are the evidence:

| Deploy | `"Feature Type Name"` | parameter `"Name"` | body `setProperty` | server |
|---|---|---|---|---|
| `…023013883848Z-a27a2cc9dacd` | `螺旋凸棱` | Chinese | Chinese | `compiled: false` — "Nonconforming feature function 'spiralRidgeCn': Invalid character in 'Feature Type Name' annotation: only printable ASCII allowed" |
| `…023048515402Z-e9d1588d11a2` | `Spiral ridge CN` | Chinese | Chinese | `compiled: false` — "precondition analysis failed" + "Invalid character in 'Name' annotation" for all five parameters |
| `…023118489138Z-0ba0ca4040a5` | `Spiral ridge` | ASCII | ASCII | `compiled: true`, 0 notices |
| `…023534056429Z-7eb6a07048d2` | `Spiral ridge` | ASCII | `螺旋凸棱柱` | `compiled: true`, 0 notices; the parts list showed `螺旋凸棱柱` |

Two conclusions, both load-bearing for the generator:

- **A Chinese UI label is impossible.** One non-ASCII parameter label is enough
  to lose the whole feature (deploy 2 kept a valid ASCII type name and still
  emitted no spec). The message names the key, not the line, so a long
  precondition needs a per-parameter scan.
- **A Chinese *part* name is fine.** Non-ASCII string *values* in the body are
  legal — the vendored mirror already uses `"⌀"` (`holeTable.fs:160`) and
  `"S™"` (`holetables.gen.fs:35277`) — so the generator keeps ASCII labels and
  puts `"螺旋凸棱柱"` in `setProperty(..., PropertyType.NAME)`.

The rule is now local: `fs_check.check_annotation_ascii` warns per offending
annotation, **warning-level** per the standing decision. False-positive gate is
the real mirror — 2496 annotation string pairs across the 265 vendored modules
contain zero non-ASCII characters, so `test_the_library_itself_is_clean` asserts
zero such warnings in addition to the map-literal rule. The rule searches its
marker in the **masked** text: the first version searched the string-preserving
text and crashed with `KeyError: ' '` in `find_matching` when a body string
merely mentioned the word `annotation`.

### The generated parameterized feature, inserted live (2026-09-20)

One `browser_spiral_ridge` call — 0 REST quota, one cloud mutation in the draft
document — deployed the **exact** generated source and inserted it:

- the submitted script's UTF-8 sha256 was
  `378f88fca387e978f0a911cf9bb58490a43a7f9c3aadfb9edb2115f76b7a1fb1`,
  byte-identical to `generate_spiral_ridge_script(10, 6, 2, 2, 30)` in this
  repository (3 525 UTF-8 bytes / 78 lines), with `deployed: true`,
  `compiled: true`, `noticeCount: 0`, `errors: []`, `commit.clicked: true`
  (the Commit button enabled → disabled);
- a new error-free row `Sr Spiral ridge 7`, `inserted: true` — baseline 8 rows,
  the read after the reload took it to 9 with `零件数 (9)`, every part named
  `螺旋凸棱柱`;
- the diagnostic package is
  `onshape_browser_mode/outputs/fs_diagnostics/20260920T031542166113Z-378f88fca387`.
  Its on-disk `featurescript.fs` is CRLF (3 602 raw / 3 525 normalized bytes); the
  reported `sourceLength 3515` is the JS **character** count, ten fewer bytes than
  the UTF-8 length because of the five Chinese characters;
- `budgets.customFeaturesRead: 8` — the tab-switch readiness wait read a real count
  where the pre-fix run read `0` — and `panelReady.waited` / `toolbarReady.waited`
  were `true` at 5 ms / 13 ms against 30 s budgets each. The scaled budgets
  (`regenerationMs 46 000`, `commitSurvivalMs 94 000`) were generous: the live
  work took 216 ms and 7 308 ms.

Two facts came out of the same run and are reusable:

- **Re-deploying the source re-computes every existing instance.** All nine
  `Spiral ridge` rows now name their parts `螺旋凸棱柱`; the six earlier rows had
  been `Spiral ridge cylinder`. So a FeatureScript edit is a document-wide
  recompute, not just a definition change.
- **A version was not created** (`version.created: false`,
  `reason: "version prompt not present"`), which is correct for in-document
  insertion and unchanged from earlier runs.

This re-earns `source_verified="live-verified"` on `custom.spiral_ridge`: the
capability route renders through the same generator
(`capabilities._build_spiral_ridge` delegates to `generate_spiral_ridge_script`),
so one run certifies both entry points.

### The tab-switch read race, found by the parameter run (2026-09-20)

Reaching the parameter dialog meant going Feature Studio → Part Studio, which
exposed a silent false pass in `insert_custom_feature`:

- the first call after the switch returned
  `{"clicked": false, "reason": "workspace-custom-features button not found"}`;
- a second call (page already on the Part Studio) succeeded, but reported
  `budgets.customFeaturesRead: 0` on a document with **8** custom features — the
  post-navigation read hit an empty panel, so `minimum = 0 + 1 = 1` was already
  satisfied by an old on-screen row.

The fix waits for the panel to render **and** the toolbar button to be visible
before reading the baseline (`wait_for_panel_rows` 30 s, `wait_for_toolbar_button`
30 s), records both as `panelReady` / `toolbarReady`, and spends neither when no
tab switch happened. This has offline coverage only (`test_tab_switch_waits_for_the_feature_panel`,
`test_a_panel_that_never_renders_rows_is_reported_not_guessed`,
`test_without_a_tab_switch_no_readiness_wait_is_spent`); a live re-run is the
certificate and is still owed.

### `browser_edit_feature_parameters` accepted a real edit and said it did not (2026-09-20)

The live review of the accept step found the same class of defect as the insert:

- run 1 returned `accepted: false` / `parametersApplied: false` although the edit
  **had** applied — run 2's `before` already showed `12 mm` / `40 mm`;
- run 2 returned `parametersApplied: true`, `accepted: true`,
  `regenerationOk: true`, `persistenceOk: true`.

Cause: the accept step clicked ✓ and then fixed-slept 500 ms before counting
inputs. Replaced with a bounded condition wait on the dialog actually closing
(`page.wait_for_function('(selector) => document.querySelector(selector) === null', arg=PS_FEATURE_DIALOG, timeout=60_000)`),
returned as `accept: {clicked, timeoutMs, waited, waitMs}`. "The dialog closed" is
the accept-complete signal, not an elapsed duration.

### The edit path's row identification, and two silent no-op waits (2026-09-20)

The accept fix above made the accept step honest; the very next live attempt failed
one step earlier, and that failure led to a third defect class.

**Row identification by name is not a read.** Four live calls of
`browser_edit_feature_parameters` returned
`{"parametersApplied": false, "reason": "feature 'Sr Spiral ridge 7' must match
exactly one row"}` on a Part Studio whose read (`browser_get_partstudio_features`)
listed `特征 (13)` with a `Sr Spiral ridge 7` row at
`className: "os-list-item ns-user-feature"`. Ruled out as causes: transient DOM
(four attempts over minutes), whitespace/NBSP (Playwright's `hasTextEngine` uses
`normalized` text — read from the vendored driver — so NBSP is not a factor),
selector drift (deployed `PS_USER_FEATURE` is byte-identical to the repository's),
and a stale deployment (`transactions.py` line-identical). The message itself named
neither a count nor the candidate rows, so 0-vs-multiple was unmeasurable from
outside — which is why the replacement reports both counts.

`_locate_feature_row` now waits for the panel to render, identifies the row from
`read_partstudio_features`, and clicks it by its **position among the read's
user-feature rows** (`rows.nth(names.index(...))`); the two views are in step
because both are DOM order. When the read and the locator disagree it refuses to
click and reports `featureRows` / `matchedRows` / `locatorRows` plus a `reason`.
`edit_feature_parameters` carries that evidence as `featureRow` on every return,
including refusals. Ten offline tests in `dev/tests/test_browser_apply_path.py`
model the disagreement directly (the tool previously had **zero** behavioural
tests, which is how the false negative shipped).

**Two waits that never waited.** While adding the static guard for this path, the
same guard was extended to `transactions.py` and immediately failed: two
`page.wait_for_function` calls (the watch/configure toolbar readback, and the
copy-element new-tab wait) passed `arg` **positionally**, while playwright-python
declares it keyword-only (`self, expression, *, arg=None, timeout=None,
polling=None`, read from the deployed `sync_api/_generated.py`). Both calls sat
inside `except Exception: pass`, so the `TypeError` was swallowed and the wait
never happened — silently, for as long as the code existed. Both are now
`arg=…`; the guard covers `actions.py` **and** `transactions.py`, and two new Mock
page tests in `dev/tests/test_browser_planned_tools.py` assert the wait is really
issued (`len(call.args) == 1` and `call.kwargs["arg"] == …`), which a positional
call can never satisfy.

The same test then flaked once in five full-suite runs: `arg=list(set)` sent
`["e2", "e1"]` or `["e1", "e2"]` depending on the process's string hash seed. The
id list is now built in document order (membership still uses a set) so the same
call sends the same argument every run.

Everything here is offline: `653 tests OK` (up from 641), 0 REST calls, 0 cloud
mutations. **The corrected edit path still owes one live run** — it is the item
blocked by the restart.

### Deployment

Refresh `20260920T012311Z-insert-commit-verify`: **39 files** shipped (21 changed,
18 added — the REST fixture family and probe records), pre-images written for all
21 overwritten files under
`artifacts/deploy-backups/20260920T012311Z-insert-commit-verify/`, all **589**
repository source files re-hashed and matching, stale bytecode dropped for the
three touched packages, backend generation **2 → 3** with all 4 client streams
preserved, and **0 REST calls / 0 cloud mutations** from the refresh itself.
This record and the generated indexes changed after that refresh and were shipped
by a documentation-only follow-up (`20260920T…-docs`, 3 files, no runtime module,
so no second restart).

`mcp_tool_catalog status` after the restart: 106 registered, 72 ordinary,
modules 66 / 11 / 18 — unchanged. The fingerprint moved
`a4787372986e8eba…` → `1ddfc6e0086dfa8a…`, which is expected and accounted for:
the fingerprint hashes `description`, and the tool description changed. Recomputing
it from this repository's `server.TOOLS` yields the same
`1ddfc6e0086dfa8ae1a806015399be1272ed6da8c789971db6e86d27b562d863` the live
backend reports, so the restarted process is running this repository's code.

Refresh `20260920T031500Z-insert-commit-v2` ships the **correction** — the
count-based insert waits (`onshape_browser_mode/actions.py`), the reworded
`browser_insert_custom_feature` description (`estimated_seconds` 30 → 45), the
map-literal checker rule, both test modules, this record and the generated
indexes: **10 files** shipped, **579 left alone**, pre-images under
`artifacts/deploy-backups/20260920T031500Z-insert-commit-v2/`, stale bytecode
dropped for `onshape_docs/query/`, all **589** repository source files re-hashed
with **0 mismatches**, backend generation **3 → 4** with all 4 client streams
preserved (`drain` entered, `protocol-close`/`stdin-closed`, clean exit,
force-kill not needed), and again **0 REST calls / 0 cloud mutations**.

`mcp_tool_catalog status` after that restart: 106 registered, 106 indexed, 72
ordinary, modules 66 / 11 / 18 unchanged. Fingerprint
`3046c988c74b4318f3841946e6d83d759ce74618951a32b687a885d64145fab8`, recomputed
independently from this repository's `server.TOOLS` through
`ToolCatalogIndex.fingerprint` — identical, so generation 4 is running this
repository's code, and the count-based insert path is the one now reachable from
the ordinary tool surface. This paragraph and `onshape_docs/index.json` changed
after that restart, so they were shipped by a documentation-only follow-up
(`20260920T033000Z-insert-commit-v2-docs`, 2 files, no runtime module, no second
restart); its own added sentence was then carried by
`20260920T034000Z-insert-commit-v2-docs2`, 1 file, same rule.

Refresh `20260920T040500Z-wait-for-function-arg` ships the signature fix that the
live run above forced: `onshape_browser_mode/actions.py` (`arg=…`), the strict
`FakePage` signature and the new `PlaywrightCallSignatureTest` — **3 files**,
**586 left alone**, pre-images under
`artifacts/deploy-backups/20260920T040500Z-wait-for-function-arg/`, all **589**
files re-hashed with **0 mismatches**, generation **4 → 5** with the same clean
drain sequence, **0 REST calls**. No `__pycache__` exists in
`onshape_browser_mode`, so no stale bytecode could shadow the new source.

Refresh `20260920T053000Z-adaptive-wait-budget` ships the scaling itself:
`onshape_browser_mode/actions.py` (`partstudio_wait_budget_ms`,
`count_custom_features`, the two profiles, the `budgets` result block), the
reworded `browser_insert_custom_feature` description, both docs pages and the
audit row — **7 files**, **582 left alone**, pre-images under
`artifacts/deploy-backups/20260920T053000Z-adaptive-wait-budget/`, all **589**
files re-hashed with **0 mismatches**, generation **5 → 6** with the same clean
drain sequence, **0 REST calls**. `mcp_tool_catalog status` after it: 106 / 106 /
72, fingerprint `c96b564144f0599f68598be2301146332a7584ac0a9d7d226a8216286011d45b`,
recomputed identically from this repository's `ToolCatalogIndex.fingerprint`.

Refresh `20260920T073000Z-parameter-panel` ships the parameter-panel work and the
two false-negative fixes above: `onshape_browser_mode/modeling_transactions.py`
(the parameterized generator), `onshape_browser_mode/transactions.py` (the
accept-condition wait), `onshape_browser_mode/actions.py` (the tab-switch
readiness waits), `mcp_main/win/mcp/browser_tools.py` (the reworded
`browser_spiral_ridge` description), `onshape_docs/query/fs_check.py`
(`check_annotation_ascii`), the three test modules, the audit and roadmap rows,
the two experience pages, this record and the generated indexes — **16 files**,
**573 left alone**, pre-images under
`artifacts/deploy-backups/20260920T073000Z-parameter-panel/`, all **589**
repository source files re-hashed with **0 mismatches**, generation **6 → 7**
with the same clean drain sequence (`drain entered`, `protocol-close` /
`stdin-closed`, `exited`, `force-kill not-needed`), 3 client streams preserved and
3 clients notified of the tool-list change, and **0 REST calls / 0 cloud
mutations** from the refresh itself.

`mcp_tool_catalog status` after that restart: 106 registered, 106 indexed, **72
ordinary**, modules 66 / 11 / 18 unchanged. Fingerprint
`c96b564144f0599f68598be2301146332a7584ac0a9d7d226a8216286011d45b` →
`7091559fe48fdd0826369762837ddb7720e7f047e749c8d37b0251e28352aced`, which is
expected and accounted for: the fingerprint hashes `description`, and
`browser_spiral_ridge`'s description now says the generated feature is
parameterized. Recomputing it from this repository's `ToolCatalogIndex.fingerprint`
yields the same `7091559f…`, so generation 7 is running this repository's code.
The restart again terminates the browser process, so the Onshape **web** session
needs one manual login; the persistent profile survived, and this paragraph and
`onshape_docs/index.json` changed after the restart, so they were shipped by a
documentation-only follow-up (`20260920T075000Z-parameter-panel-docs`, 2 files,
no runtime module, no second restart); the two paragraphs below were then carried
by a second documentation-only refresh `20260920T075500Z-parameter-panel-docs2`
(2 files, same rule), after which `plan` reports **changed 0 / identical 589**.
The full offline suite is **641 OK** (up from 625), and all four docs gates pass.

### What is still unverified

- **The generator's output and its parameter panel are certified live** (see the
  section above: one `browser_spiral_ridge` call on the exact generated source,
  `inserted: true`, hash-equal, 0 REST). What is still owed is narrower and was
  blocked by a restart: the corrected `browser_edit_feature_parameters` path
  (row identification, `featureRow` evidence) and the tab-switch readiness waits
  have offline coverage only.
- **The corrected code path is now exercised live end to end** (third run above,
  `inserted: true` with a 4 → 5 row count across a reload), and so is the
  **scaled** budget: a fourth run on the same element read
  `budgets.customFeaturesRead: 5`, spent `208 ms` of a `40 000 ms` regeneration
  budget and `7 266 ms` of a `70 000 ms` commit-survival budget, and reported
  `inserted: true` with `特征 (10)` / `零件数 (6)`. The arithmetic is certified:
  `30 000 + 2 000 × 5 = 40 000` and `30 000 + 8 000 × 5 = 70 000`. Same-element
  survival took `18 431 ms` on one run and `7 266 ms` on another, which is why a
  fixed timeout was the wrong shape. The caps (300 s / 900 s) are still guesses
  bounded by "a tool call must return", not measurements, and are the first
  thing to revisit on a real model. The **tab-switch readiness waits** above have
  offline coverage only; one live run after the next refresh is owed.
- **The Chinese-name question is settled, and the answer is not what was asked.**
  A Chinese **UI** label is impossible — FeatureScript rejects non-ASCII in any
  annotation string, measured across four deploys — while a Chinese **part**
  name compiles clean and displays. So `"Feature Type Name"` stays
  `Spiral ridge` and the parameter labels stay ASCII; `螺旋凸棱柱` is the only
  Chinese-bearing option and lives in the body. Whether the ASCII type name
  should be renamed is the owner's call; keeping it means existing instances and
  the tool default keep working.
- The recycle again terminates the browser process, so the Onshape **web** session
  needs one manual login; the persistent profile survived.
- **`browser_build_part`'s `partNames` is still wrong.** `partsText` is correct, but
  the name split can never fire on the normalized text: `read_partstudio_features`
  collapses whitespace, while `parse_part_summary` only splits on two spaces or a
  newline, and its `count == 1` branch takes the whole remainder as one name — which
  is how `曲线数 (1)` gets swallowed. For `count > 1` it therefore returns no names
  at all. Measured on `Spiral ridge PS`: `零件数 (3) Spiral ridge cylinder Spiral
  ridge cylinder Spiral ridge cylinder 曲线数 (3)` with `partNames: []`. Unrelated to
  this fix and still open.
- **No reachable tool can read a FeatureScript notice.** `browser_fs_read_notices`,
  `browser_notifications_status` and `browser_click` are all `default_exposure:
  false`, and this deployment's shared backend rejects `mcp_tool_view` with
  `shared_view_fixed`. `browser_get_fs_compile_status` reads the pane but needs the
  Feature Studio on screen, which no visible tool can activate. The notice for the
  `gate check` tab was therefore read from the local diagnostic package it wrote
  when it was captured, not from the live UI.

## Second live session — the certificate after the host crash (2026-09-20, +0800)

A host crash took the WSL bridge node and every running agent session with it. The
working tree survived and was committed as four topical slices, tip `96390cf`.
This section is the first live evidence after the recovery, and it is deliberately
a **session-boundary certificate**: the calls below ran against generation 7 with
this repository's code, and that was established before any browser action.

### Freshness, measured before the first live call (0 REST, 0 cloud mutations)

| Signal | Value |
|---|---|
| `mcp_tool_catalog(action="status").fingerprint` | `7091559fe48fdd0826369762837ddb7720e7f047e749c8d37b0251e28352aced` |
| `ToolCatalogIndex(server.TOOLS).fingerprint` computed in this repository | identical, byte for byte |
| 651 repository files vs 556 deployed, sha256 each | every shipped code file identical; 3 differ — `onshape_browser_mode/config/geometry-backend.json` and `onshape_rest_api_mode/config/onshape-state.json` (host runtime state) and `.agent-project-guides.json` (governance, not shipped with the code) |

The fingerprint gate is the one
[`../experience/browser-modeling.md`](../experience/browser-modeling.md) §14
requires; the per-file hashes are the independent second opinion, and they are what
makes "the deployment is this repository" a statement about *content* rather than
about one number. No refresh was needed, so no restart that would have cost the
browser session.

### The tab-switch readiness waits, live (was owed)

The owed item was the pair of readiness waits that only the `part_studio_tab`
branch spends. A forced switch is required to exercise them at all, and — the
recorded gap — **no visible tool activates a tab**: only composite transactions
that take a tab argument switch the current one. `browser_create_tab` therefore
created a real Feature Studio (`Feature Studio 1`, `55194a57da634e5038073f00`) and
left it active, which is the exact from-state that produced the original failure
("workspace-custom-features button not found" plus a baseline of 0 rows on a Part
Studio holding 8 custom features). `browser_insert_custom_feature` was then called
**standalone**, with `part_studio_tab="Spiral ridge PS"`.

| Signal | Recorded failure | This run |
|---|---|---|
| `budgets.customFeaturesRead` | `0` | **`9`** |
| `panelReady` | absent | `waited: true`, `partstudio_row_count`, 19 ms |
| `toolbarReady` | `workspace-custom-features button not found` | `waited: true`, `toolbar_button_visible`, 233 ms |
| `baselineRows` | `0` | **`9`** |
| `waits.regeneration` / `commitSurvival` | — | `waited: true`, minimum 10, 188 ms / 5 616 ms |
| `budgets.regenerationMs` / `commitSurvivalMs` | fixed 30 s | `48 000` / `102 000` = `30 000 + 2 000×9` / `30 000 + 8 000×9` |
| `inserted` / `commit.committed` | — | `true` / `true` |
| row and parts | — | `Sr Spiral ridge 8`, `hasError: false`, `零件数 (9) → (10)` |

Both waits resolved in 19 ms and 233 ms, so this run certifies that the branch
**spends** them and that the baseline read is no longer 0 — it does not stress the
race the fix was written for, because the recorded failing render did not
reproduce. The honest claim is the narrow one.

### The generator's output, re-certified verbatim

`browser_spiral_ridge(base_radius_mm=10, pitch_mm=5, ridge_width_mm=2,
ridge_height_mm=1, length_mm=30, clockwise=true)` on the same document:

| Signal | Value |
|---|---|
| `diagnosticCapture.sourceSha256` | `540f71eb7867ca0d128457ee472ca22c839d108ac014afcb67564b7faeb5736d` |
| the same value computed locally from `generate_spiral_ridge_script(10, 5, 2, 1, 30, clockwise=True)` | identical — the deployed text **is** the repository's generator output, 3 516 chars / 78 lines |
| server | `deployed: true`, `verified: true`, `commitAccepted: true`, `compiled: true`, 0 errors / 0 warnings / 0 notices |
| `inserted` / `commit.committed` | `true` / `true`, `minimum: 11`, survival 6 025 ms of 110 000 ms |
| row and parts | `Sr Spiral ridge 9`, `hasError: false`, `零件数 (10) → (11)` |
| `version` | `{"created": false, "reason": "version prompt not present"}` — no new version, and none was needed: the workspace toolbar dropdown exposes the Feature Studio's current spec, which is also why the earlier run applied the feature before any version existed |

`annotationCount: 0` is not a missing-parameter signal: that counter reads the Ace
editor's diagnostic annotations, not the source's `annotation {}` blocks. The
parameter panel itself was **not** re-read this run, because the tool that reads it
refuses (below); the recorded dialog read plus the byte-identity of the deployed
source is what supports "five parameters in the default slot" here, and that is a
conjunction of one earlier observation with one measurement from this run, not a
single fresh one.

### `_locate_feature_row` refuses on every element (new, blocking)

The corrected row identification refuses to click when the read and the locator
disagree, and live they **always** disagree by exactly one:

| Element | rows the read names | `locatorRows` | call |
|---|---|---|---|
| `Spiral ridge PS` | 11 | **12** | `browser_edit_feature_parameters("Sr Spiral ridge 9", {baseRadius: "12 mm", length: "40 mm"})` |
| `Part Studio 1` | 1 | **2** | the same call on `Sr Spiral ridge 1` |

Both returns are `parametersApplied: false` with
`reason: "the read lists N custom-feature rows but the row locator sees N+1;
refusing to click a row that may be a different one"`, and the second call was
byte-identical to the first, so this is deterministic rather than a transient DOM.
A constant `+1` across elements holding 1 and 11 named rows means **one extra
`.os-list-item.ns-user-feature` node with no text is present on every Part Studio
page**. The read cannot see it: `read_partstudio_features`'s collector ends with
`.filter(f => f.name)`, which drops any row whose `innerText` and `textContent` are
both empty, while `page.locator('.os-list-item.ns-user-feature')` counts it.

The refusal is therefore **correct** — requiring two differently-derived counts to be
equal is the right instinct, because `rows.nth(index)` against a set with a member the
read did not see addresses a row the read cannot account for — but the consequence is
that the corrected `browser_edit_feature_parameters` path is unusable on any element,
and its live verification is **blocked, not passed**. (The third section below corrects
the mechanism: the nameless node is measured to sit *after* every named row, so the
index was not shifted and the refusal came from the count check itself.) The fix
direction is to make the two views the *same set* rather than to relax the guard: either
enumerate nameless rows in the read too (keeping `count_custom_features` on named
rows so the budgets do not inflate), or derive the click index in the page from the
same `querySelectorAll` the locator counts. Nothing was changed here: a source edit
invalidates the freshness certificate above, and refreshing a deployment is a
separate authorized action.

### Two smaller live findings

- **`browser_delete_element` reports a tab it did delete as not deleted.** Deleting
  `55194a57da634e5038073f00` returned `deleted: false` after timing out waiting for
  `.os-tab-bar-tab` `nth(3)` to detach, but the call log shows the node ending as
  `class="os-tab-bar-tab hidden"` (Onshape's `ng-class` sets `hidden` from
  `tab.getIsRemoved()`; the SPA does not detach the node), and
  `browser_get_page_tabs` afterwards no longer lists `Feature Studio 1`. The
  verification assumes detachment, so the verdict is inverted for every tab delete.
- **`browser_build_part` on a Part Studio with 0 custom features** returned
  `built: true`, `inserted: true`, `commit.committed: true` and, usefully,
  `budgets.customFeaturesRead: 0` with `regenerationMs: 30000` /
  `commitSurvivalMs: 30000` — the documented "an unreadable or zero count reproduces
  the previous fixed budget" floor, measured. Its `partNames` failure shows both
  branches from one call: `count == 1` → `["螺旋凸棱柱 曲线数 (1)"]`, the next section
  header swallowed into the name; `count > 1` → `[]` with `partNamesParsed: false`.


## Third live step — the deployment refresh and the unblocked re-run (2026-09-20, +0800)

This section is the first live measurement *after* the three defects above were
fixed (commit `96da187`) and shipped. It records what the fix certifies, one
correction it forces on the section above, and one new defect it exposes.

### Deployment identity

The runtime is a file-copy deployment at `C:\MCP\onshapescript`, so a fix is not
live until the files are shipped *and* the process is replaced.

| Step | Evidence |
|---|---|
| plan (read-only) | 589 repo source files: 11 changed, 0 missing, 578 identical — the drift was exactly the two fix commits |
| apply | 11 files shipped, 11 pre-images + 2 manifests written to `artifacts/deploy-backups/20260920T062942Z-browser-defect-fixes`, 0 absent-before, 0 stale bytecode dirs |
| verify (read-only) | `shippedPresent: 589`, `mismatched: []` |
| recycle | `bridge_control restart` on `onshape`: generation 3 → 4, `preservedClients: 1`, `reconnectRequired: false`, phases `drain/entered`, `protocol-close/stdin-closed`, `wait/exited`, `force-kill/not-needed` |
| tool fingerprint | `7091559fe48fdd0826369762837ddb7720e7f047e749c8d37b0251e28352aced` before **and** after, and equal to the repository |

The fingerprint row is the point: it did **not** change, because this fix moved
module *behaviour*, not the tool surface. The registry fingerprint therefore cannot
certify this class of change, and the per-file hash sweep is the only gate that
does. Treating the fingerprint as "the freshness check" would have shipped a stale
backend and reported success.

The recycle terminates the browser process and the Onshape web session ends with
it, so one human login was required (the persistent profile is what keeps that
cheap). That is unchanged from the previous refresh.

### The blocked call no longer refuses — measured directly

The re-run target was `Spiral ridge PS` (`05406f02482e1d943d80dc3e`), the element
whose nine-feature read versus twelve-node locator produced the refusal above.

Calling `browser_edit_feature_parameters` with a deliberately ambiguous name
(`"Spiral ridge"`) exercises the locate path and refuses **before any click**, so it
is a zero-mutation probe of exactly the code that was fixed. Measured:

```json
{"panelReady": {"waited": true, "condition": "partstudio_row_count", "minimum": 1,
                "timeoutMs": 30000, "elapsedMs": 16},
 "featureRows": ["Sr Spiral ridge 1", "Sr Spiral ridge 2", "Sr Spiral ridge 3",
                 "Sr Spiral ridge 4", "Sr Spiral ridge 5", "Sr Spiral ridge 6",
                 "Sr Spiral ridge CN 1", "Sr Spiral ridge CN 2", "Sr Spiral ridge 7",
                 "Sr Spiral ridge 8", "Sr Spiral ridge 9", ""],
 "matchedRows": ["Sr Spiral ridge 1", "... 11 names ..."],
 "locatorRows": 12,
 "reason": "feature 'Spiral ridge' matched 11 of 12 custom-feature rows: [...]"}
```

- `featureRows` is **12** entries and the last one is the empty string, so the
  in-page enumeration finally *includes* the nameless `ns-user-feature` node that
  the filtered read dropped and the locator counted.
- `locatorRows` is **12** and equals `len(featureRows)`: the constant +1 that made
  the two views disagree is gone, and the same number now appears on both sides.
- The refusal names both counts and the matched rows, in under a second, with no
  click and no mutation.

### Correction to the section above: the phantom is LAST, not above the target

The measurement above fixes a mechanism claim this document made when the defect was
found. Live, the nameless node sits **after** every named row. A click index derived
from a names-only list therefore still addressed the intended row — the order was
not shifted — and the refusal came from the **count-equality guard** (`seen !=
enumerated["count"]`, 12 against 11), which fired on every element and is what made
the tool unusable. The earlier `filter(has_text=...)` failure is a separate mode.

The replacement is still the right one, for a stronger reason than index shifting:
it makes identity and position come from **one** node list, so it is correct
whatever position an internal Onshape node occupies. Position is not a contract —
the phantom is last today and nothing guarantees it stays last. The old code was not
wrong about the row; it was wrong to require two differently-derived counts to be
equal, because a set difference is not a page change.

### The re-run of the real edit: no refusal, but a new transport boundary

Running the previously blocked edit for real — `browser_edit_feature_parameters(
"Sr Spiral ridge 9", {baseRadius: 12 mm, length: 40 mm}, confirm_mutation=true)` —
did **not** refuse. It ran a full transaction and the downstream produced a response
**61.7 s** later (bridge correlation `ed6e86eb…`: request 236 B, response 2499 B).
The client had already given up at 60 s with `MCP error -32001: downstream_timeout`,
so the payload was discarded.

- The old locate refusal returned in under a second with a ~618-byte payload, so a
  61.7 s transaction to a multi-kilobyte response means the call got past the locate
  step and through the dialog transaction. That is the blocked defect cleared.
- `PS_DIALOG_CLOSE_TIMEOUT_MS` is `60_000`, and Onshape re-evaluates the whole model
  before the dialog reports closed. On an element with 11 user features that wait is
  tens of seconds, so this tool's wall time can exceed the 60 s downstream limit
  even when everything works.
- **Consequence:** the caller sees a transport failure for an operation that may
  have applied. `parametersApplied` is therefore **unverified** for this call and
  the document's `Sr Spiral ridge 9` values are **unknown to the record** (most
  likely 12 mm / 40 mm, but this is an inference from the response shape, not a
  measurement). A bounded JSON-size probe over the real row names put a locate
  refusal near 618 B and a completed transaction near 1.2-2.4 kB depending on
  envelope escaping, which is consistent with a completed transaction and not with
  a refusal; it does not separate success from a late `accepted: false`.
- After the timeout the page was at `about:blank`, and the Onshape web session was
  signed out (`browser_session status` → `awaiting_login`). The cause was **not**
  established: candidate mechanisms are the relay cancelling the in-flight request
  and the browser losing its page. It is recorded as measured, not explained, and it
  is why the long transaction was not re-run a second time — a second attempt would
  have cost another human login while still not returning the payload.

### `partItems` is live and the DOM part-name path works

`browser_get_partstudio_features` on `Spiral ridge PS` returned `partItems` with 11
entries of `螺旋凸棱柱`, alongside the whitespace-folded, truncated
`partsText` (`零件数 (11) 螺旋凸棱柱 … 曲线数 (11)`). With `len(partItems) == parts`,
`parse_part_summary` now returns 11 names with `partNamesSource: "dom"` and
`partNamesParsed: true`, where the text path returned a bogus single name
(`count == 1`) or nothing (`count > 1`). The DOM path is the live-verified one.

One observation left unexplained: the same read reports `headerText: "特征 (15)"`,
while it lists 16 rows (5 default + 11 user) and the enumeration counts 12
`ns-user-feature` nodes (11 named + the nameless one). The header count matches
neither, so it is not used as a count anywhere and is not claimed to.

### The tab-removal verdict is live-certified, and the raw read is a timing-dependent witness

The third fix was exercised directly: create a throwaway Feature Studio
(`browser_create_tab` → `d8737b68e0a7840bac1d639b`, which also proves that tool's own
new-tab detection), then delete it by id.

```json
{"deleted": true, "elementId": "d8737b68e0a7840bac1d639b",
 "removal": {"waited": true, "condition": "tab_removed_or_hidden",
             "timeoutMs": 30000, "elapsedMs": 274},
 "stillListedIds": ["d8737b68e0a7840bac1d639b"],
 "tabs": [ ... 11 entries, the deleted tab present with "active": false ... ]}
```

- `deleted: true` after **274 ms**, where the previous implementation timed out for
  **30 s** and returned `deleted: false` for the same operation. The verdict now comes
  from the `data-id` wait, and it resolves as soon as the node is gone or marked
  removed.
- The same payload still lists the deleted tab in its raw `tabs` block **and** in
  `stillListedIds`. That is the exact disagreement that produced the old false
  negative, now captured as diagnosis instead of obeyed: the returned verdict is
  `true` while the raw read says the tab is still there.
- `browser_get_page_tabs` immediately afterwards lists **10** tabs and no longer
  includes the deleted id. Reason, read from the collector's source: it maps every
  `.os-tab-bar-tab` with `querySelectorAll` and **does not filter `hidden` at all**,
  so the node is still returned in the instant after deletion and stops being
  returned only once Onshape actually detaches it. "Still listed" is therefore a
  timing-dependent observation, which is the second reason it cannot be the verdict.

With this, two of the three fixes are certified live by direct evidence and the third
(the parameter-apply path) is certified as *no longer refused* with its result lost to
the transport limit described above.

### Status of the three fixes after this run

| Fix | Live status |
|---|---|
| feature-row identity from one enumeration | **verified live** — 12 = 12, phantom included, 16 ms panel wait, refusal names both counts |
| tab-removal verdict by `data-id` | **verified live** — see below |
| DOM part names (`partItems`) | **verified live** — 11 DOM names, `partNamesSource: "dom"` |
| parameter-apply path end to end | **not certified** — the call no longer refuses, but its result was lost to the 60 s transport limit |

Two openings are recorded rather than worked around: the tool's wall time against
the transport limit, and the absence of any tool that can make an existing tab the
active one (which is why a small-element end-to-end success could not be
substituted for the 11-feature element).

Both openings were then worked on in commit `1ac2cc3` (the two-stage parameter edit
and `browser_activate_tab`) and re-measured live in the fourth step below. That step
also **falsifies** the mechanism this section attributed the 61.7 s to.

## Fourth live step — both openings closed, and the close signal falsified (2026-09-20, +0800)

This is the first live measurement of the fixes in `1ac2cc3`. It certifies the
tab-activation opening as closed and the two-stage apply as correct, and it replaces
the transport explanation this document gave for the 61.7 s with a measured one.

### Deployment identity (second refresh, generation 4 → 5)

The runtime is a file-copy deployment at `C:\MCP\onshapescript`, so a fix is not live
until the files are shipped *and* the process is replaced — and this fix moved the
tool surface as well as behaviour.

| Step | Evidence |
|---|---|
| plan (read-only) | 589 repo source files: 16 changed, 0 missing, 573 identical |
| apply | 16 files shipped, pre-images + manifests written to `artifacts/deploy-backups/20260920T070919Z-two-stage-edit-and-activate-tab` |
| verify (read-only) | `shippedPresent: 589`, `mismatched: []` |
| recycle | `bridge_control restart` on `onshape`: generation **4 → 5**, `preservedClients: 1`, `force-kill/not-needed`, phases `drain/entered`, `protocol-close/stdin-closed`, `wait/exited` |
| tool fingerprint | `7091559f…` → `c51cef0179267818d5ee34022b17c0014753980a3df810109771da1523375b9c`, equal to the repository; live catalog 108 registered / 74 visible / 68 browser |

Unlike the first refresh, this fingerprint **did** move, because this change added two
tools (`browser_verify_feature_parameters`, `browser_activate_tab`). The two classes
therefore both have a live example: a behaviour-only change leaves the fingerprint
identical and needs the per-file hash sweep, a surface change moves it. The sweep
remains the only gate that covers both.

The recycle again terminated the browser process and ended the Onshape web session, so
one human login was required. That is session-cookie semantics, not an intended guard:
no logout, `atexit` or cookie-clearing exists in the code.

### The tab-activation opening is closed, live

`browser_activate_tab` was called on `Part Studio 1` while `Spiral ridge PS` was
active — the exact situation that made the read/edit tools operate on the wrong
element and had no zero-quota remedy:

```json
{"activated": true, "elementId": "b1d0caa1e06f62da338d0ef8", "name": "Part Studio 1",
 "alreadyActive": false, "clicked": true,
 "activeBefore": "05406f02482e1d943d80dc3e", "activeAfter": "b1d0caa1e06f62da338d0ef8",
 "wait": {"condition": "tab_active_class", "waited": true, "timeoutMs": 15000, "elapsedMs": 357},
 "contentReady": {"headerVisible": true,
                  "rows": {"waited": true, "condition": "partstudio_row_count", "minimum": 1, "elapsedMs": 6}}}
```

- The verdict is that tab's **own** `active` class re-read by `data-id`, not the click,
  and the two ids in `activeBefore`/`activeAfter` are different tabs.
- **357 ms** to switch. The earlier `browser_rename_tab` workaround reported
  `renamed: true` and left the previous tab active; there is now an actual selector.
- `content="partstudio"` also gated the switch on the Feature List title and its rows,
  which is what makes it usable as the readiness wait a `dblclick` needs.
- Re-called when the tab was already active, it reports `alreadyActive: true`,
  `clicked: false` and still waits (`elapsedMs` 60 and 68 in two calls), so it is both a
  switch and a readiness gate.

### The two-stage apply is correct, and the commit is real

Stage 1 of `browser_edit_feature_parameters` (`wait_for_regeneration=false`, the
default) returned with the dialog still being re-evaluated and did not lose or invent
a verdict:

```json
{"parametersApplied": null, "applyState": "pending_verification", "pendingVerification": true,
 "updated": ["baseRadius"], "missing": [], "readbackOk": true,
 "before": {"baseRadius": "10 mm", "pitch": "5 mm", "ridgeWidth": "2 mm",
            "ridgeHeight": "1 mm", "length": "30 mm"},
 "after":  {"baseRadius": "12 mm", "pitch": "5 mm", "ridgeWidth": "2 mm",
            "ridgeHeight": "1 mm", "length": "30 mm"},
 "accept": {"clicked": true, "waitMs": 0},
 "verifyWith": {"tool": "browser_verify_feature_parameters",
                "arguments": {"feature_name": "Sr Spiral ridge 1",
                              "parameters": {"baseRadius": "12 mm"}}}}
```

When the panel had closed, stage 2 proved the write end to end — twice:

```json
{"verified": true, "parametersApplied": true,
 "dialogClosed": {"waited": true, "condition": "feature_dialog_absent", "timeoutMs": 20000, "elapsedMs": 5},
 "regenerationOk": true, "persistenceOk": true, "featureState": [{"name": "Sr Spiral ridge 1", "hasError": false}],
 "persisted": {"baseRadius": "12 mm", "pitch": "5 mm", "ridgeWidth": "2 mm",
               "ridgeHeight": "1 mm", "length": "30 mm"}}
```

A second green run returned `elapsedMs: 4` with `persisted.baseRadius: "10 mm"`. So
`parametersApplied` is no longer `null` for a real edit: the edit below is the same
element and the same path, and the verdict is a measurement.

Two fields in the stage-1 payload are initialisers rather than measurements and must
not be read as data: `accept.waitMs` is `0` because the default path returns before
that wait is ever performed (it is not "waited 0 ms"), and `featureState: []` in a
not-yet-closed stage-2 payload is the empty initialiser, not "no rows were found".
Both are recorded here because reading either as a measurement is exactly the class of
false negative this pass was fixing; they are candidates for a follow-up, not part of
the shipped contract.

### The finding: after an accept that CHANGES a parameter, the panel does not report closed

The second stage can only answer once `document.querySelector('.feature-dialog') ===
null`. On this element that condition **does not become true for an edit that changes a
parameter**, while the same accept on unchanged values satisfies it in milliseconds.
Four accepts on the same feature, with the accept's own before/after as the variable:

| accept | dialog `before` → `after` | close condition observed |
|---|---|---|
| real change | `10 mm` → `12 mm` | **no** at 25 s, 25 s, 45 s (95 s total) |
| no-op | `12 mm` → `12 mm` | **yes**, `elapsedMs: 5` |
| real change | `12 mm` → `10 mm` | **no** at 20 s, 40 s (60 s total) |
| no-op (restore) | `10 mm` → `10 mm` | **yes**, `elapsedMs: 4` |

Every one of those accepts **committed**. The proof does not depend on the panel: after
each real-change accept a bounded page reload was used to discard the still-open panel,
and the next dialog — opened from a freshly loaded page — read the **new** value as its
`before` (`12 mm` after the first, `10 mm` after the third). A reload discards client UI
state; it does not undo a server-side commit. So the write had landed while the panel
was still present.

The operator's view of the same window agrees: a screenshot at **15:18:30 +0800**, inside
the 95 s of timeouts, shows the panel open with header `Spiral ridge 1`, `Base radius
12 mm`, a green ✓ and a red ✗, and `Sr Spiral ridge 1` selected in the Feature List. It
looks normal — no spinner, no error, no disabled ✓ — which is why the accept cannot be
diagnosed from the panel's appearance.

This is why a human observation was needed at all: this backend is a **fixed tool view**,
so the primitives that would have settled it in one call are not callable here —
`browser_eval` returns `unknown tool` and `mcp_tool_view(action="set")` returns
`shared_view_fixed`. The category is therefore "not answerable from the exposed tool
surface", and the human-in-the-loop report is the evidence of record.

### Correction to the section above: the 61.7 s was `PS_DIALOG_CLOSE_TIMEOUT_MS` being consumed

The section above attributes the 61.7 s to re-evaluation: "Onshape re-evaluates the
whole model before the dialog reports closed. On an element with 11 user features that
wait is tens of seconds." The measurements above do not support that.

- `61.7 s` sits one overhead above `PS_DIALOG_CLOSE_TIMEOUT_MS = 60_000`, and the
  measured close latency is not "tens of seconds" — it is **≤ 5 ms when the accept
  changes nothing** and **still unsatisfied after 95 s when it does**. A quantity that
  jumps from 4 ms to >95 s with the change/no-change variable is not a re-evaluation
  duration.
- What the 61.7 s most likely was: the old code's own 60 s bounded wait on a condition
  that a real edit does not satisfy, plus overhead. The earlier document already noted
  that `accepted = close["waited"] or count() == 0` was a fallback; this pass shows the
  fallback was load-bearing.
- The consequence for the record: "the model re-evaluation is slow" is withdrawn. The
  measured statement is narrower and more useful — **accepting an edit that changes a
  parameter commits the change in seconds and may leave `.feature-dialog` in the DOM
  past any transport-safe budget, so panel removal is not a completion signal for that
  class of edit.**

The safety half of the design held, and this is the part worth keeping: three accepts
that changed a parameter all returned `pending_verification`, and the second stage
answered `parametersApplied: null` with `retryVerify: true` instead of a verdict. No
false `applied: false` was reported, no payload was lost to the 60 s relay limit, and
the three earlier failure modes this pass was fixing are untouched.

### A discriminator that needs no human and no page eval

The panel's presence is visible in a read this tool surface *can* make. Same element,
same feature, only the panel state differing:

| panel | user-feature row `className` | part `className` |
|---|---|---|
| open | `os-list-item related-highlight edited selected ns-user-feature` | `os-list-item edited` |
| closed | `os-list-item ns-user-feature` | `os-list-item` |

The closed row is **identical to the pre-edit baseline** (`os-list-item
ns-user-feature`, part `os-list-item`), so the document was left exactly as found:
`baseRadius` back at `10 mm`, no `edited`, no `selected`. `read_partstudio_features`
already returns this field, so "is the parameter panel open" is answerable offline
without a screenshot and without the L1 primitives.

### Status after this run

| Item | Live status |
|---|---|
| `browser_activate_tab` (the second opening) | **verified live** — data-id switch in 357 ms, own-`active`-class verdict, `contentReady` gate |
| two-stage stage 1 (`pending_verification`, no false verdict) | **verified live** — 10 → 12 mm, `readbackOk: true`, `verifyWith` correct |
| two-stage stage 2 verdict when the panel closes | **verified live** — `verified: true`, `regenerationOk: true`, `persistenceOk: true`, `elapsedMs` 4-5 |
| stage 2 for an edit that **changes** a parameter | **not certifiable as designed** — the panel stays open ≥ 60-95 s after a committed change, so the close-based verdict cannot resolve inside a transport-safe call |
| the 61.7 s mechanism claim | **withdrawn** — see the correction above |
| `Sr Spiral ridge 9` values from the lost call (`Spiral ridge PS`) | still **unknown**; untouched by this pass |

The one remaining opening is therefore not the transport limit as such but the choice
of completion signal: the panel's removal is satisfied instantly by a no-op accept and
not at all (in ≥ 95 s) by a real one, while the commit in both cases is already done.

## Fifth live step — the recovery path measured, falsified, fixed, and certified (2026-09-20, +0800)

This pass closes the gap the fourth step left open, and it is the first pass whose
central finding came from running the *new* code rather than the old: the recovery path
that the fourth step's measurement justified was itself raced against the reloaded page,
returned no verdict, and had to be fixed and re-measured before it could be certified.

### Deployment identity

| | First refresh | Second refresh |
|---|---|---|
| deployment id | `20260920T073954Z-readonly-probe-and-panel-recovery` | `20260920T075034Z-recovery-render-wait` |
| files shipped | 14 | 5 |
| `verify` | 589 present / 0 mismatched | 589 present / 0 mismatched |
| bridge generation | 5 → 6 (`preservedClients: 2`) | 6 → 7 (`preservedClients: 2`) |
| phases | `drain/entered`, `protocol-close/stdin-closed`, `wait/exited`, `force-kill/not-needed` | same |
| tool fingerprint | `c51cef01…` → `bb56591d174acc25299d70794dacecaa77b826fd1f444c650eae99ca79a614b0` | **unchanged** (`bb56591d…`) |
| registry / visible / browser | 109 / 75 / 69 | 109 / 75 / 69 |

The fingerprint moved on the first refresh because the tool surface gained
`browser_read_feature_parameters` (108 → 109), and the deployed fingerprint equals the
one computed from the repository with `ToolCatalogIndex(server.TOOLS)`. It did **not**
move on the second refresh, which changed behaviour only (a new wait inside an existing
transaction) — that is the division of labour the first refresh established: the
fingerprint covers surface changes, and the per-file hash sweep (589 files) is the only
gate that covers a behaviour-only change. Both refreshes were applied over a live
deployment with a per-deployment backup under `artifacts/deploy-backups/`.

### `browser_read_feature_parameters` — certified live (read-only, 0 REST quota)

On `Part Studio 1`, feature `Sr Spiral ridge 1`:

| call | result |
|---|---|
| default (`allow_reload=false`) | `read: true`, 5 values, `dialogClosed: {waited: true, elapsedMs: 7}`, `recovery: null` |
| `allow_reload=true` | same 5 values, `dialogClosed.elapsedMs: 4`, `recovery: null` — the reload was **not** spent |

Values read: `baseRadius 10 mm`, `pitch 5 mm`, `ridgeWidth 2 mm`, `ridgeHeight 1 mm`,
`length 30 mm` (`parameterCount: 5`). Its row evidence is the same one-enumeration
contract the edit path uses: `featureRows: ["Sr Spiral ridge 1", ""]`,
`matchedRows: ["Sr Spiral ridge 1"]`, `locatorRows: 2`.

**Zero-mutation proof**: `browser_get_partstudio_features` was read before and after the
two probes and returned byte-identical row classes (`os-list-item ns-user-feature` for
the custom row, `os-list-item` for the part, no `edited`, no `selected`, no
`related-highlight`) and an identical feature/part set. The probe opens a dialog, reads
it and presses Escape; nothing is filled, and the document is unchanged.

The second row (`""`) is the nameless `ns-user-feature` node that the fourth step's
count comparison first exposed; this pass confirms it on a second element and confirms
that it is a real DOM node in the live enumeration, not a rendering artefact.

### The two-stage path — certified, then fixed, then re-certified in one call

Stage 1 (`baseRadius` 10 → 12 mm) behaved exactly as designed:
`applyState: "pending_verification"`, `parametersApplied: null`, `readbackOk: true`,
`before.baseRadius 10 mm` → `after.baseRadius 12 mm`, `accept: {clicked: true, waitMs: 0}`
(the known initialiser), and a `verifyWith` payload naming stage 2.

Stage 2 is where this pass earned its keep. **The first live call of the new recovery
path returned `retryVerify: true` instead of a verdict**, with
`regenerationOk: false`, `featureState: []`, `persisted: {}`, `featureRow: {}` and the
reason "left 0 row(s) named 'Sr Spiral ridge 1'". Its own `recovery` block shows why:

```
recoveredBy: "page_reload", recovery: {reloaded: true, tabs: [], hasDocumentTabsToolButton: false}
dialogClosed: {waited: true, elapsedMs: 151}
```

The whole recovery block finished in **151 ms** against a freshly reloaded page whose
tab strip had not rendered yet. A second call, on the settled page, answered
`verified: true` / `parametersApplied: true` / `regenerationOk: true` /
`persistenceOk: true` with `persisted.baseRadius: "12 mm"`. So the edit had committed in
the first call; the call simply read the rows before they existed. The verdict grading
held (a non-verdict after a recovery reload is `null` + `retryVerify`, never `false`),
but the path produced no answer, which is exactly what it was written to produce.

The read probe showed that waiting alone was not the fix. Called immediately after the
same kind of real edit with `allow_reload=true` (the panel was still open), it reported:

```
read: false, featureRows: [], locatorRows: 0,
panelReady: {waited: true, condition: "partstudio_row_count", elapsedMs: 2736},
recovery: {reloaded: true, tabs: [], hasDocumentTabsToolButton: false}
```

It **did** wait — 2736 ms — and still enumerated 0 rows, because the condition it waited
on counts `.os-list-item`, which the part list, the tab strip and a loading skeleton also
match. A satisfied wait that proves nothing about the list the next line enumerates.

The fix (`46cdb8f`) adds `actions.wait_for_feature_list(page, timeout, selector=...)` and
calls it with `selectors.PS_USER_FEATURE` in both recovery branches, so the condition is
the *custom-feature rows the caller is about to read*. It counts rows and never matches a
name, so the single row-matching rule is not duplicated. It is a new function rather than
a change to `wait_for_panel_rows`, whose broader condition the tab-switch callers rely on.

Re-certified live after the second refresh (generation 7), same element, same feature:

| stage | result |
|---|---|
| stage 1, 10 → 12 mm | `pending_verification`, `parametersApplied: null`, `readbackOk: true` |
| stage 2, **one call** | `verified: true`, `parametersApplied: true`, `regenerationOk: true`, `persistenceOk: true`, `persisted.baseRadius: "12 mm"`, `recoveredBy: "page_reload"`, `featureListReady: {waited: true, selector: ".os-list-item.ns-user-feature", elapsedMs: 6181}` |
| stage 1, 12 → 10 mm (restore) | `pending_verification` |
| stage 2, **one call** | `verified: true`, `persisted.baseRadius: "10 mm"`, `featureListReady.elapsedMs: 5717` |

The 6181 ms / 5717 ms wait against the earlier 151 ms read is the whole defect and the
whole fix in one number: the reloaded page needs seconds, not milliseconds, before its
custom-feature rows are enumerable. `Part Studio 1` was left exactly as found
(`baseRadius 10 mm`, `featureRows: ["Sr Spiral ridge 1", ""]`, one part `螺旋凸棱柱`).

### The two long-open questions, answered

**`Sr Spiral ridge 9` on `Spiral ridge PS`** — read back for the first time, one call,
`recovery: null`:

```
baseRadius 12 mm, pitch 5 mm, ridgeWidth 2 mm, ridgeHeight 1 mm, length 40 mm
```

The earlier suspicion (12 mm / 40 mm) was right for the two varying dimensions, and this
feature is the same family as `Part Studio 1`'s `Sr Spiral ridge 1` (5 / 2 / 1), differing
in `baseRadius` and `length`. Recorded as measured; the earlier `pitch 6 mm /
ridgeHeight 2 mm` reading for a different feature is not a default of this family.

**`特征 (15)` on `Spiral ridge PS` is accounting, not a rendering artefact.** The feature
list holds 16 *named* rows — one `默认几何图元` group row, the four default planes
(`Origin`/`Top`/`Front`/`Right`) and **11 named custom features** — plus the nameless
`ns-user-feature` node that only the DOM enumeration sees (`featureRows` ends with `""`,
`locatorRows: 12`). The header counts the real features: 4 planes + 11 custom = **15**;
the group row and the nameless node are not features. `Part Studio 1` is isomorphic:
4 planes + 1 custom = `特征 (5)`, over 6 named rows. The earlier "+1" was therefore a
comparison of two different sets (a filtered read and a counting locator), exactly as the
fourth step concluded — and the node itself is real.

### Why a login is required after every restart — measured, and not a defect of this code

The same pass tried to treat the post-restart login prompt as a false alarm. It is not.
Four measurements, all at 0 REST quota:

1. **No browser survived the restart.** Every Edge process whose command line carries
   `onshape_profile` was created at 15:50:55 or later, while the restart happened at
   15:50:34. The pre-restart browser was gone; the browser serving the session afterwards
   was launched by the session call itself.
2. **A graceful close logs out.** `browser_session(action="release")` — which is
   `releaseMethod: "context.close"`, the same close the bridge restart performs — followed
   by `browser_open_document` **without any login** gave
   `opened: false`, `error: "document not found"`, `pageUrl: https://cad.onshape.com/signin`.
   Afterwards no `onshape_profile` Edge process remained, i.e. the close really was clean.
3. **An abrupt kill logs out too.** `Stop-Process -Force` on the 8 profile processes
   (`warnings: ["context.close failed: TargetClosedError"]`, so no clean shutdown ran on
   the browser side) followed by the same read-only navigation gave `opened: false`,
   `pageUrl: /signin`. So the login is not carried by anything the profile keeps after
   either kind of death.
4. **The auth cookies are session cookies.** With the browser closed, the profile's
   `Default/Network/Cookies` was copied out and read: `.onshape.com on-session-id` and
   `cad.onshape.com _u` are both `persistent=0 has_expires=0 secure=1 httponly=1`, while
   the only persistent rows are analytics and WAF (`_ga`, `_ga_*`, `aws-waf-token`).
   Caveat kept in view: this read followed an unauthenticated visit, so the presence of an
   `on-session-id` is not evidence of a logged-in session; the **type** of the auth cookie
   is the solid half.

This matches the design note this repository already carries. Commit `e149bdf`
(2026-08-20, `tools/windows/README.md`) states it directly: *"Onshape WEB 端没有'保持登录'，
浏览器一关立即登出"* — the browser had to be owned by the **resident bridge process**,
which dispatched JSON-RPC in-process, so that a client disconnect closed only the socket
and left the browser (and the login) alone; only exiting the bridge process closed it.
The current transport spawns a **fresh MCP server child per connection**, and
`mcp_main/win/mcp/server.py` (behaviour introduced by `9394ad0`, "在断连时释放浏览器
profile") has that child close the browser on stdin EOF so the next child can take the
profile. Under that architecture any disconnect or restart kills the browser, and
"profile is in use" is precisely the symptom that motivated the close.

So: the earlier conclusion in this same document ("That is session-cookie semantics, not
an intended guard") was correct, and today's counter-hypothesis is withdrawn. The only
way to keep the login across a restart is for the browser to outlive the MCP child and
for the next child to attach to it (CDP), which the direction chosen for the next pass
implements in this repository by injecting a Playwright factory through the
`playwright_factory` hook `onshape_browser_mode/session.py` already forwards.

### Status after this run

| Item | Live status |
|---|---|
| `browser_read_feature_parameters` | **verified live** — values read, panel cancelled, zero mutation proven by before/after row classes |
| read probe `allow_reload=true` without an open panel | **verified live** — `recovery: null`, the reload is not spent |
| two-stage stage 1 | **verified live** — `pending_verification`, `parametersApplied: null` (twice) |
| two-stage stage 2, recovery path | **verified live after the fix** — one call each, `verified: true`, `persisted` == requested, `featureListReady` 6181 / 5717 ms |
| recovery path as first written (`c4c9cb6`) | **falsified live** — 151 ms, 0 rows, `retryVerify`; fixed by `46cdb8f` |
| `wait_for_panel_rows` as a post-reload gate | **falsified live** — satisfied at 2736 ms with 0 custom-feature rows on screen |
| `Sr Spiral ridge 9` values (`Spiral ridge PS`) | **answered** — 12 / 5 / 2 / 1 / 40 mm |
| `特征 (15)` vs 16 rows / 12 nodes | **answered** — 4 default planes + 11 named custom features; group row and nameless node are not features |
| login across a restart | **not preserved by design** — session cookies; needs a resident browser + attach, which is the next pass |
| resident browser (next pass) | see the sixth live step below |


## Sixth live step — resident browser: a restart no longer costs a login (2026-09-20, +0800)

The fifth step ended by naming the only way out: the browser must outlive the MCP child
and the next child must attach to it. That is implemented (commits `0a15b2d`, `d1f8b2b`,
`ac74449`) and certified here on the real machine, at **zero Onshape REST quota**
(`LIVE_API_ENABLED` unset throughout; every call below is a browser or OS-level read).

### Deployment identity

| Item | Value |
|---|---|
| Deployment | `C:\MCP\onshapescript` (file-copy refresh, not a checkout) |
| Refresh 3 | `20260920T-resident-browser` — 9 files (7 changed, 2 added), `shippedPresent: 591`, `mismatched: []` |
| Refresh 4 | `20260920T-resident-probe-fix` — 2 files, verify 591 / 0 mismatched |
| Refresh 5 | `20260920T-resident-wiring` — 2 files, verify 591 / 0 mismatched, removed `onshape_browser_mode\__pycache__` |
| Bridge generations | 7 -> 8 (ship) -> 9 (probe fix) -> 10 (wiring fix) -> 11 (no-login mechanism test) -> 12 (end-to-end certification) |
| Restart phases | `drain/entered`, `protocol-close/stdin-closed`, `wait/exited`, `force-kill/not-needed`; `reconnectRequired: false`, `preservedClients: 2` each time |
| Config | `browser.local.toml` (host-owned, `onshape_browser_mode/config/` is a preserved prefix): `resident = true`, `resident_port = 9333` |

Catalog fingerprint was **not** re-measured for these refreshes and does not need to be:
no tool name or schema changed, so it cannot move. The per-file hash sweep is the gate,
and it reported 591 shipped / 0 mismatched after each apply.

### The measurement the design rests on

`artifacts/cdp_close_probe.py` (scratch profile, port 9334, the Onshape profile never
touched) spawned Edge detached with `--remote-debugging-port`, attached over CDP, then
called the exact release call `browser_common` makes:

```
STEP1 endpoint=up   targets=[about:blank, chrome-extension://...(6 后台页)]
STEP2 connected contexts=1 connected=True  pages=1 urls=['about:blank']
STEP3 context.close() returned
STEP3 endpointAfterClose=up   targetsAfterClose=[同前，一个都没少]
STEP3 isConnectedAfterClose=False   contextsAfterClose=0
STEP4 secondAttach contexts=1 pages=[1]
STEP5 endpointAfterStop=up    targetsAfterStop=[同前]
```

`context.close()` on a CDP-attached browser **detaches the connection and leaves the
browser, its pages and its session cookies alive** — Chromium cannot dispose a browser's
default context. This falsified the assumption behind the first adapter design (a proxy
context with a no-op `close()`), and the proxy was removed: `browser_common` asserts
`page.context is session.context` in `_core._validate_pages`, which
`_enforce_single_working_page` runs at every page hand-off, so a look-alike context would
have broken real workflows. It also means `close()` must **not** raise — a raising close
makes `_release_resources` fall back to `browser.close()`.

### Two defects found live, both before any login was spent

1. **`TypeError` swallowed into the generic launch message.** `browser_open_document`
   returned `Could not launch browser (channel='msedge'): TypeError.` The traceback came
   from a deployment-side reproduction (`artifacts/resident_debug.py`):
   `ResidentChromium.__init__() got an unexpected keyword argument 'viewport'`.
   `_make_resources` duplicated a per-page launch option that already reaches the adapter
   through `launch_kwargs()`. Fixed by `ac74449`; two tests now cover it (the switch sends
   only the spawn-time identity; the adapter accepts exactly what the switch sends).
2. **The probe went through the host's system proxy.** `urllib.request.getproxies()`
   returns `http://127.0.0.1:10808` here, and `urlopen` honours it, so an absent browser
   looked like a proxy timeout. Measured on this host: a loopback connect to a *closed*
   port raises `ConnectionRefusedError` only after ~2.03 s (9333, 9334 and an unused 9399
   all 2.03 s), so the 2.0 s budget turned the refusal into a timeout. `d1f8b2b` probes
   through `ProxyHandler({})` — which registers no `*_open` method at all — and raises the
   budget to 3.0 s. Before: `URLError: <urlopen error timed out>` at 2000 ms. After:
   `URLError: [WinError 10061] 由于目标计算机积极拒绝...` at 2050 ms.

### Certification (no login spent on the mechanism test)

Baseline after the first spawn: endpoint `Edg/153.0.4234.32`, browser GUID
`693fb502-d9f7-42a2-9d30-026532eca4d6`, main `user-data-dir` process **PID 3872** created
`1789892405161`, 14 profile processes, one page at `https://cad.onshape.com/signin`.

Restart 10 -> 11 (still not logged in), then read-only:

| Probe | Before restart | After restart |
|---|---|---|
| `/json/version` | reachable, GUID `693fb502…` | **reachable, same GUID `693fb502…`** |
| main `user-data-dir` process | PID 3872, `1789892405161` | **PID 3872, `1789892405161`** |
| `/json/list` pages | `.../signin` | **`.../signin`** |
| profile processes | 14 | 9 (idle renderers/utilities exited; the browser did not) |
| MCP child reads the live page | — | `browser_get_page_tabs` -> `pageUrl: .../signin`, `tabs: []` |

A **new** MCP child attached to the **same** browser: no second `user-data-dir` process
appeared, and the browser GUID was unchanged. That is the mechanism proven with no login.

### End-to-end certification (after one human login)

The human completed SSO once in the visible window. `browser_session(action="login")`
then reported `already logged in (restored Onshape page was kept)` — the page had already
reached the app URL, so the first-branch check fired; the report was confirmed
independently rather than trusted, by reading the tabs:

`browser_get_page_tabs` -> `pageUrl .../e/b1d0caa1e06f62da338d0ef8`, 10 tabs
(`Part Studio 1` active, plus `Spiral ridge FS`, `Spiral ridge PS`, `参数化特征 FS`,
`Part Studio 2`, `gate check`, `cap fillet`, `cap extrude`, `cap hole`, `Assembly 1`),
`hasDocumentTabsToolButton: true`.

Then restart 11 -> 12 and read again, **with no login and no navigation in between**:

- `browser_get_page_tabs` -> the same document URL, the same `elementId`
  `b1d0caa1e06f62da338d0ef8`, the same 10 tab names, `hasDocumentTabsToolButton: true`;
- `browser_session(action="status")` -> `sessionStatus: "started"`,
  `humanActionRequired: false`, `loginConfirmed: true`, one page, the document URL;
- `/json/version` -> GUID `693fb502-d9f7-42a2-9d30-026532eca4d6` (unchanged), main PID
  **3872** still `1789892405161`, 9 profile processes, and the page target still the
  document URL.

So a bridge restart no longer logs the human out: the login lives in the resident
browser process, and the child that follows merely attaches. The negative control is the
previous round's: killing that process (`Stop-Process -Force`) or closing the window is
followed by a read-only navigation that lands on `/signin`.

### What this does not claim

- It does not make Onshape keep a session on its own; it removes the *self-inflicted*
  logout. One login is still required on the first run and after any real browser death.
- It does not change REST behaviour or spend REST quota; `LIVE_API_ENABLED` stayed unset.
- It does not extend to a second owner: one resident browser per profile and port. The
  DevTools endpoint is loopback-only and must never be forwarded — it is full control of
  the logged-in profile.
- `viewport` is applied as the spawn `--window-size`, not as a page viewport; `headless`
  and `timezone_id` are reported as `notApplied` in the attach record rather than
  silently ignored. Resident mode is for the headed, human-watched session.
