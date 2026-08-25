# Browser FS-mode semantic tool plan (roadmap)

Status: proposed, not implemented.

This roadmap records the four-level semantic tool surface the browser
**FS 脚本模式** (FeatureScript script-authoring) workflow needs, based on a
live read-only browser exploration of a real Feature Studio and its coupled
Part Studio (2026-08-25). It is a plan, not current behavior: current behavior
is the static registry described by `../architecture/OVERVIEW.md` and generated
from `mcp_main`.

Scope note: the focus is **FS script mode** — authoring/deploying FeatureScript,
creating versions, applying custom features, and driving their parameters —
**not** native feature mode (the Part Studio sketch/extrude toolbar). Native
feature transactions are explicitly out of current scope; the few places where
FS mode couples to the Part Studio UI (e.g. drawing auto-views via the part
context menu) are treated as coupling points and listed under §4.

Follow the four-level semantics defined in `DYNAMIC_TOOL_DISCOVERY.md`:

- L1: generic observation/input/wait primitives.
- L2: one verified user-intent transaction with its own acceptance evidence.
- L3: a workflow composed from L2 transactions.
- L4: fixture-driven projects with assertions, checkpoints, and resume.

Ownership stays with the `browser` module (`onshape_browser_mode` +
`mcp_main/browser_tools.py`). Nothing in this document is implemented yet.

## 1. Live-browser evidence (2026-08-25)

### 1.1 Feature Studio (FS script editor)

Exploration of `module-interface-verification` / `FS-PartA-wall` (document
`05c7c78fc59c0fb5f8d66fcb`, element `3a65192600dc6f974ab29830`) confirmed the
FS script editor surface:

- **Ace editor** (`.ace_editor`): full source read-back works through the
  existing `browser_read_featurescript` (10284 chars / 223 lines returned
  intact). Code-folding widgets `ace_fold-widget` present (4 in the sample).
- **Ace annotation API is available**: `editor.session.getAnnotations()`
  returns the compiler annotation list (0 for a clean script). This is the
  cheapest verified signal that a committed script **compiled successfully** —
  the current `browser_deploy_featurescript` only checks the Commit button
  went disabled and the source read back identically; it does **not** read
  annotations, so a script with a compile error that still commits would pass.
- **FS toolbar** (`.tool.is-activatable.is-button`): `Length parameter`,
  `提交` (Commit), `Module outline` (`.top-level-symbols-button`), ref-nav
  back/forward, plus `命令搜索` (`.command-search-trigger`, alt/⌥c).
- **Module outline** (`.top-level-symbols-toolbar`): opens a symbol list
  `16 symbols` with icon-prefixed entries `C <CONST>` (constants) and
  `ƒ <name>` (functions); selectors `.top-level-symbol-item`,
  `.top-level-symbol-icon`, `.top-level-symbol-name`,
  `.top-level-symbol-count`. This is the script's own symbol/feature inventory.
- **Ace editor right-click menu** (`.context-menu-list`): `粘贴` / `转至定义`
  / `插入代码段`. `转至定义` is the FS symbol jump-to-definition action;
  `插入代码段` opens the FS snippet/template insertion surface (its dialog did
  not open in the read-only scan — see §4.2 capture task).
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

## 2. Current four-level surface (implemented)

The static registry already implements the following FS-mode semantic layers.
They are the base the missing tools compose on top of.

- **L1 generic**: `browser_click`, `browser_scroll`, `browser_inspect`,
  `browser_eval`, `browser_wait`, `browser_press_key`, `browser_type`,
  `browser_reload`, `browser_session`, `browser_watch` (frame-aware, dry-run,
  confirmation gates).
- **L2 transactions**: `browser_create_document`, `browser_open_document`,
  `browser_create_tab`, `browser_rename_tab`, `browser_delete_tab`,
  `browser_delete_element`, `browser_get_page_tabs`, `browser_sync_rest_state`,
  `browser_insert_assembly_instances`, `browser_fix_instances`,
  `browser_group_instances`, `browser_create_drawing`,
  `browser_add_drawing_dimension`; FS-specific:
  `browser_deploy_featurescript`, `browser_create_document_version`,
  `browser_insert_custom_feature`, `browser_open_insert_feature_dialog`,
  `browser_read_featurescript`, `browser_get_partstudio_features`.
- **L3 workflows**: `browser_deploy_and_apply_featurescript`,
  `browser_build_part`, `browser_assemble`, `browser_draw_part`.
- **L4 projects**: `browser_run_project` (fixture-driven, checkpoint/resume;
  `ALLOWED_PROJECT_TOOLS` gates which L2/L3 tools a fixture may call).

## 3. Missing FS script-mode tools (L2, priority order)

### 3.1 `browser_get_fs_compile_status` (L2, read) — highest priority

Read the Ace editor annotations (`editor.session.getAnnotations()`) and report
`{compiled, errors: [{row, col, text, type}], annotationCount}`. Wire it into
`browser_deploy_featurescript` / `browser_deploy_and_apply_featurescript` so a
commit is only reported `deployed: true` when **both** the button went disabled
**and** annotations are empty. This closes the current gap where a compiling
error script could still be reported as deployed.

### 3.2 `browser_get_fs_symbols` (L2, read)

Open `Module outline` and read the symbol inventory:
`{symbolCount, symbols: [{kind: "const"|"function", name}]}`. This gives a
machine-readable inventory of the script's exported constants/features —
directly useful for verifying that a deployed script defines the expected
feature names before applying it.

### 3.3 `browser_fs_goto_definition` (L2)

Drive the Ace editor right-click → `转至定义` on a selected symbol and read
the resulting cursor position / jump target. Foundational for FS code
navigation inside the editor.

### 3.4 `browser_fs_insert_snippet` (L2)

Drive the Ace editor right-click → `插入代码段` to insert a FeatureScript
template/boilerplate (defineFeature skeleton, parameter blocks, etc.). Requires
the §4.2 dialog-DOM capture before selectors can be written.

### 3.5 `browser_fs_insert_parameter` (L2)

Drive the `Length parameter` toolbar button (the FS script editor's own
parameter-insertion control) and accept the resulting insertion, so a script
can be extended with a typed parameter without hand-writing the line.

### 3.6 `browser_fs_toggle_fold` (L1/L2)

Read/click `ace_fold-widget` entries to fold/unfold code regions; return the
folded row ranges. Minor but cheap and useful for navigating long scripts.

### 3.7 `browser_edit_feature_parameters` (L2, coupling)

After a custom feature is applied (or selected in the feature tree), open its
`.feature-dialog`, read the current parameter fields, set non-default values,
and accept. This is what lets a parametric FS feature (e.g.
`fanDuctAdapter.fs`) be driven to non-default dimensions from the browser.
Currently `browser_build_part` only applies with the dialog's default values.
Also add an optional `parameters` argument on the apply path.

### 3.8 FS source update (L2 improvement to `browser_deploy_featurescript`)

Add an incremental update path (read current source, apply a targeted edit
through the Ace API, commit) so re-deploying a large script does not require
rewriting the whole file each round.

## 4. Coupling points (FS ↔ Part Studio UI)

These are the places where FS mode must reach into the Part Studio (or drawing)
UI. Each is a distinct transaction; none is a native-modeling feature.

### 4.1 `browser_drawing_insert_views` (L2, coupling — drawing auto-views)

The verified entry point is the **part context menu** item
`创建 <part name> 的工程图…`, not the generic drawing dialog. Transaction:
select a part row in `.part-list-container` → right-click →
`创建 <name> 的工程图…` → complete the drawing dialog (source/template/view
layout) → verify the drawing frame gained geometry (canvas-image or DOM change),
matching the `browser_draw_part` frame-verification contract.

### 4.2 Part context-menu capture (Phase-A evidence, coupling)

Before writing 4.1 and 3.4, capture the part context-menu and the
feature/snippet dialog DOM into `dev/button-map/scan-part-context-menu.json`
and `dev/button-map/scan-fs-dialog.json` using `browser_watch` +
`browser_inspect` (read-only), following the assembly-scan discipline
(`dev/button-map/scan-assembly-instances.json`). This also covers the other
verified part context-menu actions (rename/properties/material/appearance/
copy/export/hide/isolate/transparent/comment/zoom/delete) that FS-mode
workflows may need to call on produced parts.

### 4.3 `browser_fs_watch_part_studio` (L2, coupling)

Drive the `监控 <part studio>` / `配置文件 <part studio>` menu (`.os-menu-tool`)
that couples a Feature Studio to its live-regen Part Studio, and read the
regen/compile state. This is the FS ↔ PS live-regeneration coupling control.

## 5. 3D-print-oriented FS tools (from `BROWSER_MODELING_GAPS.md`)

These are read/verify transactions over a produced part, in scope for FS-mode
workflows (the part came from an applied FS feature, not from native modeling):

- `browser_print_orientation_check` (L2, read) — read the current view +
  measure surface (`measure-button`, `mass-properties`) and report overhang /
  wall-thickness / print-orientation risk against configured thresholds.
- `browser_wall_thickness_report` (L2, read) — sample/verify min wall thickness
  on a body, the core 3D-print rule.
- `browser_apply_blend` (L2, write) — fillet/chamfer/draft on selected
  edges/faces. **Boundary note:** this is the one place a native-modeling
  action (fillet/chamfer on a produced part) is needed; implement it by
  driving the Part Studio fillet/chamfer tool on the FS-produced body, or
  defer it if native-mode operations stay out of scope.
- L3 `browser_print_optimize_part` — order: build/apply → blend (optional) →
  orientation/wall report → drawing with views; verifies each step's history
  node and part count.

## 6. Improvement suggestions for existing tools

### 6.1 `browser_deploy_featurescript` / `browser_deploy_and_apply_featurescript`

- Read Ace annotations after commit and require `annotationCount == 0` for
  `deployed: true` (see §3.1). A commit that leaves compiler annotations must
  be reported as failed with the error list.
- `semantic.build_part`'s `feature_name` match is a loose case-insensitive
  substring; suggest exact-name match with an `ambiguousCandidates` report when
  more than one user feature row matches.

### 6.2 `browser_get_partstudio_features` / `parse_part_summary`

- Return the raw part-name list with a `namesTrusted` flag; include the
  rollback-bar position (`ns-rollbackbar-hol`) as a first-class field so
  callers detect an interrupted/not-computed feature state.
- Expose a per-row classification (default/user/native) so L2 verification can
  assert "expected count of user rows + parts".

### 6.3 `browser_create_drawing` / `browser_draw_part`

- They complete the source/template dialog but never select the view layout, so
  the sheet can stay blank (documented in `BROWSER_MODELING_GAPS.md`). The fix
  is `browser_drawing_insert_views` (§4.1); `browser_draw_part` should accept a
  `view_layout` option and delegate to it instead of reporting `drawn` for a
  blank sheet.

### 6.4 `browser_run_project` / `project.py`

- `ALLOWED_PROJECT_TOOLS` is a closed set and `_step_ok` only knows the current
  outcome keys. Add the new FS-mode outcome keys (`compiled`, `symbolCount`,
  `featureCreated`, `parametersApplied`) and validate the fixture tool set
  against the live registry so a fixture cannot silently call an unregistered
  tool.
- Consider a per-step `timeout_s` and a `rollback` action for resumable FS
  workflows so a failed fixture can restore a clean history.

### 6.5 Generic L1 hardening

- `browser_inspect` is whole-page; add an optional `selector` scope so a
  dialog's local controls (`.feature-dialog`, `.command-search`,
  `.top-level-symbols-toolbar`) can be inventoried without scanning the whole
  DOM. Serves the §4.2 capture tasks directly.

## 7. Sequencing

| Phase | Work | Gate |
|---|---|---|
| A | Selector evidence: `browser_watch` + `browser_inspect` capture of the FS right-click menu, `.feature-dialog`, part context menu, and snippet dialog into `dev/button-map/` (scan-fs-editor.json, scan-part-context-menu.json, scan-fs-dialog.json) | Read-only; no cloud mutation |
| B | Compile-status + symbol transactions: `browser_get_fs_compile_status`, `browser_get_fs_symbols`; wire annotations into the existing deploy path | Offline mock/fixture tests; then authorized Windows smoke |
| C | FS editor transactions: `browser_fs_goto_definition`, `browser_fs_insert_snippet`, `browser_fs_insert_parameter`, `browser_fs_toggle_fold`, incremental source update | Same gates |
| D | Apply/parameter + coupling: `browser_edit_feature_parameters`, `browser_fs_watch_part_studio` | Same gates |
| E | Drawing + print + L4: `browser_drawing_insert_views`, `browser_draw_part_with_views`, printability tools, extended `ALLOWED_PROJECT_TOOLS`, FS-mode project fixture | Full offline suite + authorized Windows smoke |

## 8. Completion criteria

- Every FS-mode L2 transaction returns a verified acceptance signal: compile
  status reads real Ace annotations, symbol reads real Module-outline entries,
  parameter edits read real `.feature-dialog` fields — never click-only success.
- `browser_deploy_featurescript` reports a compile-error script as failed.
- Drawing auto-views land on the sheet via the part context menu and are
  verified by frame geometry change, not blank-sheet `drawn`.
- L4 projects can run FS deploy → apply → parameter → print-check → drawing
  steps with checkpoint/resume and fixture/SHA binding.
- All new write tools keep dry-run and confirmation; all read tools stay
  zero-REST.

## Out of scope (current)

- Native feature-mode transactions (sketch/extrude/revolve/fillet via the Part
  Studio toolbar) are NOT part of this plan. They remain the Phase D work of
  `DYNAMIC_TOOL_DISCOVERY.md`. The only native action retained is `apply_blend`
  on an FS-produced part (§5), and it may be deferred.

## Provenance

- Live-browser evidence: read-only `browser_inspect`/`browser_eval`/
  `browser_read_featurescript`/`browser_click` on `module-interface-verification`
  (FS-PartA-wall + PS-PartA-wall), 2026-08-25. No script source was modified
  during exploration (verified: 10284-byte source unchanged).
- Existing modeling-task sources: `branch-cable-trophy`,
  `module-interface-verification`, and `examples/duct-fan-adapter/fanDuctAdapter.fs`.
- Related roadmaps: `DYNAMIC_TOOL_DISCOVERY.md` (four-level taxonomy, Phase D)
  and `BROWSER_MODELING_GAPS.md` (spiral/screw-on ridge, 3D-print optimization,
  drawing auto-views).
