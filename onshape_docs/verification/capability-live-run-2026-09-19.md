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
  browser session had to stay alive.
