# Browser FS-mode semantic tool plan (roadmap)

Status: implemented 2026-08-25; retained as design and evidence history.

This roadmap records the semantic tool surface the browser
**FS 脚本模式** (FeatureScript script-authoring) workflow needs, based on a
live read-only browser exploration of a real Feature Studio and its coupled
Part Studio (2026-08-25). The planned surface is now in the complete registry
with semantic default exposure as described by `../architecture/OVERVIEW.md`;
this document retains the original rationale, verified selectors, and acceptance
boundaries.

Scope note: the focus is **FS script mode** — authoring/deploying FeatureScript,
creating versions, applying custom features, and driving their parameters —
**not** native feature mode (the Part Studio sketch/extrude toolbar). Native
feature transactions are explicitly out of current scope; the few places where
FS mode couples to the Part Studio UI (e.g. drawing auto-views via the part
context menu) are treated as coupling points and listed under §4.

Follow the optional six-level semantics defined in `DYNAMIC_TOOL_DISCOVERY.md`:

- L1/L2: generic browser primitives and composite browser transactions.
- L3: Onshape-aware prepare/inspect/recovery interactions without domain success.
- L4: one completed and verified Onshape transaction or complete observation.
- L5: a workflow composed from multiple independent L4 operations.
- L6: an independently consumable deliverable with acceptance and manifest.
- Project control: a DAG containing one or more L6 deliverables.

Ownership stays with the `browser` module (`onshape_browser_mode` +
`mcp_main/win/mcp/browser_tools.py`). The transactions in this document are
implemented; field-validation scope is called out where cloud-mutating smoke was
not authorized.

## 1. Live-browser evidence (2026-08-25)

### 1.1 Feature Studio (FS script editor)

Exploration of `module-interface-verification` / `FS-PartA-wall` (document
`05c7c78fc59c0fb5f8d66fcb`, element `3a65192600dc6f974ab29830`) confirmed the
FS script editor surface:

- **Ace editor** (`.ace_editor`): full source read-back works through the
  existing `browser_read_featurescript` (10284 chars / 223 lines returned
  intact). Code-folding widgets `ace_fold-widget` present (4 in the sample).
- **Ace annotation API is available**: `editor.session.getAnnotations()`
  returns the compiler annotation list (0 for a clean script). Deploy now
  requires this verified compiler signal in addition to Commit transition and
  exact source readback; a committed script with annotations returns
  `deployed:false`.
- **FS toolbar** (`.tool.is-activatable.is-button`): `Length parameter`,
  `提交` (Commit), `Module outline` (`.top-level-symbols-button`), ref-nav
  back/forward, plus `命令搜索` (`.command-search-trigger`, alt/⌥c).
- **Module outline** (`.top-level-symbols-toolbar`): opens a symbol list
  `16 symbols` with icon-prefixed entries `C <CONST>` (constants) and
  `ƒ <name>` (functions); selectors `.top-level-symbol-item`,
  `.top-level-symbol-icon`, `.top-level-symbol-name`,
  `.top-level-symbol-count`. This is the script's own symbol/feature inventory.
- **Ace editor right-click menu** (`.context-menu-list`): `粘贴` / `转至定义`
  / `插入代码段`. `转至定义` is the FS symbol jump-to-definition action.
  Live inspection confirmed `插入代码段` inserts directly; no separate dialog
  appeared. The edit was immediately undone and the 10284-byte source matched
  the fixture FNV-1a hash; evidence is in `dev/button-map/scan-fs-editor.json`.
- **Command search** (`.command-search`, `.command-search input`): type to
  search tools; FS mode returns "没有主体项与您的搜索匹配" for native-modeling
  tool names (expected — the FS toolbar has no sketch/extrude), confirming the
  search surface is scoped to the current tab's toolset.
- **watched / config file menu** (`.os-menu-tool`): `监控 PS-PartA-wall` /
  `配置文件 PS-PartA-wall` — the FS ↔ Part Studio live-regen coupling control.

### 1.2 Part Studio (the FS apply + verification surface)

Exploration of the coupled `PS-PartA-wall` confirmed the surfaces an applied FS
feature is verified against:

- **Feature tree** (`.os-list-item`): `默认几何图元` (Origin/Top/Front/Right),
  the applied custom feature (`ns-user-feature`, e.g. `Mr Module rail fixed
  wall 1`), `not-computed` rows, rollback bar (`ns-rollbackbar-hol`), and the
  part list `零件数 (N)`.
- **Workspace custom-feature apply** (`此工作区中的自定义特征`), the
  `.feature-dialog` parameter dialog, and the `添加自定义特征` insert dialog
  (already covered by existing tools).
- **Part context menu** (right-click a part row in `.part-list-container`):
  `重命名`, `属性…`, `指定材料…`, `编辑外观…`, `复制至此…`, `复制 <name>`,
  `创建 <name> 的工程图…`, `导出…`, `隐藏`, `隔离…`, `使之透明…`, `添加评论`,
  `放大选定对象`, `删除…`. **`创建 <name> 的工程图…` is the verified entry
  point for drawing auto-views** — it matches the coupling the earlier modeling
  round documented (auto-view drawings come from the part context menu, not the
  generic drawing dialog). Selector evidence: `.context-menu-list` +
  `.context-menu-item` (ellipsis items use `contextmenu-ellipsis-li`,
  icon rows use `context-menu-icon`).

This evidence is the basis for the missing FS-mode transactions in §3 and the
coupling-point tools in §4.

## 2. Current six-level surface (implemented tools, optional classification)

The static registry implements tools across the following discovery layers. The
metadata is advisory and does not gate registration or execution.

- **L1 browser primitives**: `browser_click`, `browser_scroll`,
  `browser_inspect`, `browser_eval`, `browser_wait`, `browser_press_key`,
  `browser_type`, and screenshot capture.
- **L2 browser transactions**: browser lifecycle, recording, reload, and
  reconnect flows that combine generic primitives without claiming a modeling
  result.
- **L3 Onshape interactions**: `browser_fs_goto_definition`,
  `browser_fs_insert_snippet`, `browser_fs_insert_parameter`,
  `browser_fs_toggle_fold`, and `browser_open_insert_feature_dialog`. These are
  default-hidden interaction/navigation capabilities and do not claim a
  committed feature result.
- **L4 Onshape transactions/observations**: FeatureScript deploy/read/status and
  symbol tools, document/tab mutations, version creation, custom-feature
  insertion, parameter editing, Part Studio feature reads, and Drawing dimension
  insertion when each operation owns one verified domain outcome.
- **L5 workflows**: `browser_deploy_and_apply_featurescript`,
  `browser_build_part`, `browser_assemble`, `browser_draw_part`, and the
  view-bearing Drawing workflows.
- **L6 deliverables**: no generic FS workflow is automatically L6. A
  design-specific, independently usable Part Studio or detailed Drawing needs
  final acceptance and an artifact manifest before it is classified L6.
- **Project control**: `browser_run_project` executes fixtures/checkpoints and is
  outside L1-L6; a future project graph contains one or more L6 deliverables.

## 3. FS script-mode tool status (L3/L4, priority order)

The consolidated (deduped) list of every planned browser tool — including the
FS items here, the drawing/print items that also appear in
`BROWSER_MODELING_GAPS.md`, and the app-generic items in
`BROWSER_GENERIC_L2_SEMANTICS.md` — is the single-source registry
`BROWSER_PLANNED_TOOLS.md`. Each item below keeps its FS-mode rationale.

### 3.1 FeatureScript notice/compile diagnostics — implemented 2026-09-02

`browser_fs_read_notices` is the L3 interaction that opens the active FeatureScript
notice pane when necessary, reads `.feature-script-notice-table` rows, and restores
the prior pane state. `browser_get_fs_compile_status` is the L4 observation that
combines those rows with Ace `editor.session.getAnnotations()` and fails closed
when a visible notice indicator cannot be read. Live evidence proved that Ace can
return zero annotations while the notice pane contains blocking precondition,
missing-variable, and bounds errors; see `dev/button-map/scan-fs-notices.json`.

Both `browser_deploy_featurescript` and
`browser_deploy_and_apply_featurescript` require the Commit button's
enabled-to-disabled transition, exact source readback, and no blocking combined
compiler evidence before returning `deployed:true`. Every committed attempt also
writes a local full-source diagnostic package. The experimental, default-hidden
`browser_fs_capture_diagnostic` creates the same package on demand.

### 3.2 `browser_get_fs_symbols` (L4, read) — implemented 2026-08-25

Opens `Module outline` and reads the symbol inventory:
`{symbolCount, symbols: [{kind: "const"|"function"|"feature", name,
displayName, rawIcon}]}`. Live inspection observed `C`, `ƒ`, and `Φ` glyphs;
`Φ` is preserved as the distinct `feature` kind. Evidence lives in
`dev/button-map/scan-fs-module-outline.json`.

### 3.3 `browser_fs_goto_definition` (L3) — implemented 2026-08-25

Uses the verified Module-outline symbol row for deterministic top-level
navigation, then reads the resulting Ace cursor and target line. This does not
claim local/imported-symbol navigation; unsupported names return
`definitionFound:false`.

### 3.4 `browser_fs_insert_snippet` (L3) — implemented 2026-08-25

Positions the Ace cursor, opens the exact context-menu command `插入代码段`,
and verifies a non-empty source delta plus Commit dirty state. Live evidence
showed direct insertion, not a separate snippet dialog.

### 3.5 `browser_fs_insert_parameter` (L3) — implemented 2026-08-25

Positions the Ace cursor and drives the verified `Length parameter` toolbar
button. V1 intentionally exposes only the observed length template; success
requires source delta and Commit dirty state.

### 3.6 `browser_fs_toggle_fold` (L3) — implemented 2026-08-25

Executes the observed Ace `fold` / `unfold` / `toggleFoldWidget` commands and
returns normalized before/after folded ranges, target state, changed state, and
idempotent already-in-state evidence.

### 3.7 `browser_edit_feature_parameters` (L4, coupling) — implemented 2026-08-25

Opens exactly one matching `.feature-dialog`, updates typed scalar controls,
reads them back, accepts, reopens to verify persistence, and rejects a feature
row with regeneration/error evidence. The public schema restricts parameter IDs
and scalar values; cloud-mutating Windows smoke remains separately authorized.

### 3.8 FS source update (L4 improvement to `browser_deploy_featurescript`)

Add an incremental update path (read current source, apply a targeted edit
through the Ace API, commit) so re-deploying a large script does not require
rewriting the whole file each round.

## 4. Coupling points (FS ↔ Part Studio UI)

These are the places where FS mode must reach into the Part Studio (or drawing)
UI. Each is a distinct transaction; none is a native-modeling feature.

### 4.1 `browser_drawing_insert_views` (L5, coupling) — implemented 2026-08-25

The verified entry point is the **part context menu** item
`创建 <part name> 的工程图…`, not the generic drawing dialog. Transaction:
select a part row in `.part-list-container` → right-click →
`创建 <name> 的工程图…` → complete the drawing dialog (source/template/view
layout) → require exactly one new drawing tab and verified frame geometry.
Drawing DOM does not expose reliable view nodes in the observed editor, so the
transaction also decodes the main canvas PNG and measures interior ink
concentration while excluding sheet chrome. The four-view live fixture and raw
metrics are stored in `dev/button-map/scan-app-shell.json` and
`scan-drawing-four-views.png`.

### 4.2 Selector evidence (completed / bounded)

`dev/button-map/scan-fs-editor.json` records the FS context menu, fold widgets,
Ace commands, toolbar item, and exact source-restoration proof.
`scan-app-shell.json` records the document shell, share dialog, part row,
analysis buttons, Drawing frame, and four-view pixel fixture. Candidates that
were not visible (`selectionPreview`, notification drawer, Drawing view DOM
nodes) remain explicitly labeled unverified and their tools return structured
absence/unknown instead of click-only success.

### 4.3 `browser_fs_watch_part_studio` (L4, coupling) — implemented 2026-08-25

Uses the visible `.watch-part-studio-menu` split control, opens
`.os-toolgroup-open-button`, chooses one exact hidden dropdown item from
`.os-tool-dropdown-content .os-menu-tool`, and verifies the visible
`.os-tool-command-name` readback. The current target and four exact
watch/configure choices are captured in `dev/button-map/scan-fs-editor.json`.

## 5. FDM-oriented tool correction (from `BROWSER_MODELING_GAPS.md`)

The original browser implementation is retained for compatibility but is not a
valid FDM conclusion chain:

- `browser_print_orientation_check` opens Onshape draft analysis. Draft analysis
  does not evaluate bed contact, support demand, bridges, stability, print
  height, layer-direction strength, build volume, or slicer-profile results. The
  six-level catalog marks the tool `semantically_invalid` and hides it from
  ordinary discovery; its current `assessable:false` / `risk:"unknown"` result
  must not be treated as an FDM orientation analysis.
- `browser_wall_thickness_report` is an L4 sampled UI observation with
  `coverage:"sampled"` and `globalMinimumVerified:false`, not a complete mesh
  wall-thickness analysis.
- `browser_apply_blend` remains one L4 Onshape transaction when it creates and
  verifies one history feature.
- `browser_print_optimize_part` is an L5 workflow, but its current dependency on
  the invalid orientation proxy and its apply-blend-before-assessment ordering
  make the workflow semantically invalid. It is hidden from ordinary discovery.

The replacement design exports canonical STEP through the owning browser or
REST mode and calls the shared, non-tool `fdm_analysis` library described in
`BROWSER_SIX_LEVEL_SEMANTICS_AND_FDM_PLAN.md`.

## 6. Improvement suggestions for existing tools

### 6.1 `browser_deploy_featurescript` / `browser_deploy_and_apply_featurescript`

- Implemented: combine Ace annotations with normalized FeatureScript notice-pane
  rows after commit and reject blocking warning/error evidence. Each committed
  attempt also records a local full-source diagnostic package for later analysis.
- `semantic.build_part`'s `feature_name` match is a loose case-insensitive
  substring; suggest exact-name match with an `ambiguousCandidates` report when
  more than one user feature row matches.

### 6.2 `browser_get_partstudio_features` / `parse_part_summary`

- Return the raw part-name list with a `namesTrusted` flag; include the
  rollback-bar position (`ns-rollbackbar-hol`) as a first-class field so
  callers detect an interrupted/not-computed feature state.
- Expose a per-row classification (default/user/native) so L4 verification can
  assert "expected count of user rows + parts".

### 6.3 `browser_create_drawing` / `browser_draw_part`

- The legacy `browser_draw_part` now rejects an empty dimension list, closing
  the former `all([])` blank-sheet false positive. New work should use
  `browser_drawing_insert_views` / `browser_draw_part_with_views`, which select
  a semantic layout and require tab plus DOM-or-pixel view evidence.

### 6.4 `browser_run_project` / `project.py`

- `ALLOWED_PROJECT_TOOLS` includes the implemented L3-L5 surface. `_step_ok`
  uses a per-tool outcome-key map and rejects unknown/missing outcomes instead
  of treating an unrecognized result as success. The module-interface fixture
  now uses `browser_draw_part_with_views`; checkpoint/SHA binding and resume
  behavior are unchanged.
- Per-step timeouts and rollback remain future project-runner improvements;
  automatic cloud cleanup is intentionally not introduced.

### 6.5 Generic L1 hardening

- `browser_inspect` is whole-page; add an optional `selector` scope so a
  dialog's local controls (`.feature-dialog`, `.command-search`,
  `.top-level-symbols-toolbar`) can be inventoried without scanning the whole
  DOM. Serves the §4.2 capture tasks directly.

## 7. Sequencing

| Phase | Work | Status / gate |
|---|---|---|
| A | Selector evidence for FS editor, Module outline, app shell, and Drawing canvas | Completed for observed surfaces; absent candidates remain labeled unverified |
| B | Combined Ace + notice-pane compile status, deploy gate, and local diagnostic capture | Implemented; offline tests + live read-only notice evidence |
| C | FS editor navigation/snippet/parameter/fold transactions | Implemented; offline tests + live selector/command evidence |
| D | Apply/parameter + FS↔PS coupling | Implemented; offline tested, cloud-mutating Windows smoke still requires explicit authorization |
| E | Drawing + print correction + L6/project + spiral ridge | Drawing implemented; invalid FDM proxy now documented/default-hidden; other cloud mutations require explicit authorization |

## 8. Completion criteria

Code/schema/offline-test completion is met. Read-only selector and Drawing pixel
smoke is recorded; cloud-mutating Windows smoke is intentionally pending an
explicit validation authorization.

- Every classified FS-mode L4 transaction returns a verified acceptance signal: compile
  status reads real Ace annotations, symbol reads real Module-outline entries,
  parameter edits read real `.feature-dialog` fields — never click-only success.
- `browser_deploy_featurescript` reports a compile-error script as failed.
- Drawing auto-views land on the sheet via the part context menu and are
  verified by frame geometry change, not blank-sheet `drawn`.
- Project control can run FS deploy → apply → parameter → drawing steps with
  checkpoint/resume and fixture/SHA binding; future projects aggregate one or
  more independently accepted L6 deliverables.
- All new write tools keep dry-run and confirmation; all read tools stay
  zero-REST.

## Out of scope (current)

- Native feature-mode transactions (sketch/extrude/revolve/fillet via the Part
  Studio toolbar) are NOT part of this plan. The browser-side implementations
  remain the Phase D work of `DYNAMIC_TOOL_DISCOVERY.md`; their use as an FS-first
  compiler backend, including Feature/Transaction IR, Custom fallback isolation,
  selection, recovery, and fork sequencing, is owned by
  `FS_HYBRID_COMPILER_INTEGRATION.md`. The only native action retained here is
  `apply_blend` on an FS-produced part (§5), and it may be deferred.

## Provenance

- Live-browser evidence: read-only `browser_inspect`/`browser_eval`/
  `browser_read_featurescript`/`browser_click` on `module-interface-verification`
  (FS-PartA-wall + PS-PartA-wall), 2026-08-25. No script source was modified
  during exploration (verified: 10284-byte source unchanged).
- Existing modeling-task sources: `branch-cable-trophy`,
  `module-interface-verification`, and `examples/duct-fan-adapter/fanDuctAdapter.fs`.
- Related roadmaps: `DYNAMIC_TOOL_DISCOVERY.md` (six-level taxonomy, Phase D)
  and `BROWSER_MODELING_GAPS.md` (spiral/screw-on ridge, 3D-print optimization,
  drawing auto-views).
