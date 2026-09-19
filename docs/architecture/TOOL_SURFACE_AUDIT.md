# Tool surface audit (P5)

Verdict for every registered tool: what it is for, whether it earns its place in
the ordinary model-facing surface, and what should happen to it next. Phase one
was a **classification only** -- no tool was renamed, merged or removed to produce
it. The verdicts are authored judgment, and
`dev/tests/test_tool_surface_audit.py` is the gate: it re-parses the table below
and fails if a registered tool is unclassified, a verdict is not one of the five,
a `Merge` verdict does not name a registered tool, or a reason is missing.

**Status 2026-09-19.** Two follow-ups have since been executed. First, the two
print-analysis stubs were archived by owner decision, so they no longer occupy a
row and the table now covers the 106 registered tools; the archive record is
`history/legacy/ARCHIVED_BROWSER_PRINT_TOOLS.md`, and `browser_delete_tab` and
`browser_draw_part` were reclassified from `Remove` to `Internal-only` in the same
pass because the owner corrected the reason they are hidden (rule 4). Second, all
eight `Merge` rows were executed: each absorbed name still works as a deprecation
wrapper, exactly the way `browser_delete_tab` did, and each row is now
`Internal-only` because "deliberately-preserved compatibility path" is what it
honestly is. Nothing was unregistered, so the registry count stays at 106 while the
ordinary semantic `tools/list` drops from 80 to 72.

## How to read a verdict

| Verdict | Meaning |
|---|---|
| `Keep` | Earns its place as an ordinary model-facing tool at its current level. |
| `Capability` | The real value is a whole-feature or whole-document job. It belongs behind a capability card (roadmap P2/P4), not as a step a caller assembles by hand. |
| `Merge` | Overlaps another tool enough that one entry point should absorb it. The target column names the survivor; the verdict says so explicitly rather than silently dropping a name. |
| `Internal-only` | Needed for composition, recovery, or a deliberately-preserved compatibility path, but it should not be a default model choice. In most cases the semantics record already marks it default-hidden for the same reason. |
| `Remove` | Deprecated or semantically invalid, or superseded by a verified path. Deleting it is a follow-up refactor, not part of this phase. Currently no row carries this verdict. |

Four rules produced the non-obvious verdicts:

1. **A click is not a result.** Single-step UI affordances (`Internal-only`) are
   kept out of the ordinary surface so callers go through typed tools that verify
   domain state instead of reporting that an interaction completed.
2. **A workflow is not a tool name.** Anything whose honest description is
   "ensure X, then apply Y, then verify Z" is a `Capability`, because a caller
   that has to sequence the steps is also the caller that can silently skip one.
3. **Duplicated backends collapse at the entry point.** The browser and REST
   geometry backends keep separate implementations, but status and configuration
   are one question and one decision each, so those entry points merge while the
   other two paths stay distinct.
4. **Default-hidden is not one reason.** A tool can be out of the ordinary list
   because it is high-risk (`browser_delete_tab` is destructive,
   `browser_draw_part` invites an unverified path), because it is an absorbed
   compatibility wrapper whose capability now lives under a surviving name, or
   because it does not do its job at all (the two archived print stubs). The first
   two kinds stay and are classified `Internal-only`; only the third is worth
   removing. The `Internal-only` reason must therefore say *why* the name is
   preserved, not merely that it is hidden.

## Coverage

The table covers every registered tool, including deprecated and
semantically-invalid entries that the default view already hides: an audit that
skips the hidden tools cannot decide whether they should still exist.

## Verdicts

| Verdict | Tools |
|---|---|
| `Keep` | 59 |
| `Capability` | 11 |
| `Merge` | 0 |
| `Internal-only` | 36 |
| `Remove` | 0 |
| **total** | **106** |

| Tool | Verdict | Merge target | Reason |
|---|---|---|---|
| `browser_add_drawing_dimension` | `Internal-only` | - | Deprecated compatibility wrapper kept for older callers; it is the dimensions stage of `browser_draw_part_with_views`, which owns the transaction and its acceptance evidence. Hidden because a dimension placed on nothing is not independently verifiable, not because the gesture is useless, so it stays reachable by exact name. |
| `browser_apply_blend` | `Capability` | - | Applies fillet/chamfer/draft to semantic targets: a designed whole-feature job that the capability layer (P2/P4) should own rather than a raw tool. |
| `browser_assemble` | `Capability` | - | Ensure an Assembly and insert named instances; the multi-step assembly job belongs behind one capability entry point. |
| `browser_build_geometry_package` | `Capability` | - | The L6 deliverable recipe for the browser backend; the capability layer should expose one package entry point across backends. |
| `browser_build_part` | `Capability` | - | Ensure a Part Studio, apply a feature, report the geometry; a whole-feature capability with a domain acceptance test. |
| `browser_capture_screenshot` | `Internal-only` | - | Composition primitive for evidence capture; useful inside a workflow, noise as an ordinary model choice. |
| `browser_click` | `Internal-only` | - | Composition primitive. Keeping it internal forces callers through typed tools that verify the result instead of reporting a click. |
| `browser_configure_geometry_backend` | `Internal-only` | - | Deprecated compatibility wrapper kept for older callers; it is the browser half of `onshape_configure_geometry_backend`, which states the backend explicitly because candidate ids are not backend-specific. Hidden as a deployment decision the operator role owns, not because configuring a backend is useless; reachable by exact name. |
| `browser_create_document` | `Keep` | - | Creates the container document for zero REST quota; a clean starting point for a new job. |
| `browser_create_document_version` | `Keep` | - | Creates a version checkpoint; the cheap way to make cloud mutations recoverable. |
| `browser_create_drawing` | `Keep` | - | Creates a Drawing from a named source and template; a complete, self-contained document step. |
| `browser_create_tab` | `Keep` | - | Creates Feature Studio/Part Studio/Assembly tabs; the composition step every browser workflow needs. |
| `browser_delete_element` | `Keep` | - | Deletes a document element by tab id; the general cleanup path that supersedes browser_delete_tab. |
| `browser_delete_tab` | `Internal-only` | - | Deprecated compatibility wrapper kept for older callers; `browser_delete_element` covers the same job through the current path. Hidden because it is destructive, not because it is useless, so it stays reachable by exact name. |
| `browser_deploy_and_apply_featurescript` | `Capability` | - | End-to-end deploy-and-apply with verification; the capability a caller actually wants, not its five constituent steps. |
| `browser_deploy_featurescript` | `Keep` | - | Deploy through the UI at zero REST quota, with the local check attached; the browser leg's core operation. |
| `browser_discover_tools` | `Keep` | - | The only view that exposes hidden L1/L3 tools together with their semantic levels; mcp_tool_catalog does not carry those levels. |
| `browser_draw_part` | `Internal-only` | - | Deprecated compatibility workflow superseded by the verified draw-part path; hidden because keeping the name visible invites use of the unverified one, not because the capability is worthless. Reachable by exact name and by an explicit `L5` query. |
| `browser_draw_part_with_views` | `Capability` | - | Whole drawing job (views plus dimensions and verification) that deserves a capability card with its own acceptance criteria. |
| `browser_drawing_insert_views` | `Internal-only` | - | Deprecated compatibility wrapper kept for older callers; it is the views stage of `browser_draw_part_with_views`, which now spans views and dimensions in one verified job. Hidden so a caller cannot pick half a drawing job by name; reachable by exact name. |
| `browser_duplicate_element` | `Keep` | - | Duplicates an id-addressed element; a safe way to iterate without touching the original. |
| `browser_edit_feature_parameters` | `Keep` | - | Edits scalar parameters of an existing custom feature; the cheapest way to explore a design space without redeploying source. |
| `browser_element_context_menu` | `Internal-only` | - | Opens an element-tab context menu for the next command; the command, not the menu, is the useful unit. |
| `browser_eval` | `Internal-only` | - | Arbitrary JavaScript in the page. Reachable at an explicit level for diagnosis, but never a default choice: it would bypass every typed wrapper. |
| `browser_export_step` | `Keep` | - | Deliverable export through the UI at zero REST quota, with explicit tab targeting. |
| `browser_fix_instances` | `Internal-only` | - | Multi-select plus the fixed-gesture; meaningful only inside the assembly workflow that establishes the selection context. |
| `browser_fs_capture_diagnostic` | `Internal-only` | - | Persists full source plus diagnostics for offline analysis. Experimental, default-hidden, and called by the diagnostic loop rather than chosen on its own. |
| `browser_fs_goto_definition` | `Internal-only` | - | Editor navigation micro-command; part of the authoring flow, not a task a caller should start from. |
| `browser_fs_insert_parameter` | `Internal-only` | - | Parameter-template insertion at the caret; a step inside authoring, with its own place in the editor flow. |
| `browser_fs_insert_snippet` | `Internal-only` | - | Verified context-menu insertion used by the authoring flow; the workflow, not the menu item, is the entry point. |
| `browser_fs_read_notices` | `Internal-only` | - | Reads the notice pane for the diagnostic loop; the composed capture path calls it, and an explicit level still reaches it directly. |
| `browser_fs_toggle_fold` | `Internal-only` | - | Code-folding affordance used to make outlines readable; it changes the view, not the document. |
| `browser_fs_watch_part_studio` | `Keep` | - | Selects the watched Part Studio explicitly, which is what makes later reads deterministic instead of guessing the active tab. |
| `browser_geometry_status` | `Internal-only` | - | Deprecated compatibility wrapper kept for older callers; `onshape_geometry_status` now reports every configured backend in one answer. Hidden so readiness is never read from half the picture; reachable by exact name. |
| `browser_get_fs_compile_status` | `Keep` | - | Reads Ace annotations and the compile indicator; the browser-side compile check that costs no quota. |
| `browser_get_fs_symbols` | `Keep` | - | Symbol outline read; how a caller learns what a Feature Studio actually defines before editing it. |
| `browser_get_page_tabs` | `Keep` | - | Tab inventory; cheap orientation that later steps address by id. |
| `browser_get_partstudio_features` | `Keep` | - | Feature tree and part list read; the domain-state check that distinguishes a listed feature from computed geometry. |
| `browser_group_instances` | `Internal-only` | - | Multi-select plus the group-gesture; the same context dependence as the fix gesture. |
| `browser_insert_assembly_instances` | `Keep` | - | Inserts named sources into an Assembly; usable on its own and the building block of the assemble workflow. |
| `browser_insert_custom_feature` | `Keep` | - | The apply operation, now waiting on real conditions and reporting whether the feature is listed instead of whether a click landed. |
| `browser_inspect` | `Internal-only` | - | Composition primitive: composed tools and a supervisor use it to locate elements. Its semantics record already marks it default-hidden and explicit-level-required. |
| `browser_invoke_discovered` | `Internal-only` | - | Deprecated compatibility wrapper kept for older callers; any registered tool is callable by the exact name `mcp_tool_catalog` returns, so this envelope adds a hop and no capability. Hidden so discovery is not mistaken for an execution route; reachable by exact name. |
| `browser_notifications_status` | `Internal-only` | - | Notification badge read; diagnostic plumbing used when a flow seems stuck. |
| `browser_open_doc_menu` | `Internal-only` | - | Document menu inventory; a composed flow or a supervisor opens it, and it is worth a call only right before another step. |
| `browser_open_document` | `Keep` | - | Smallest useful navigation step; everything else assumes a specific document is open. |
| `browser_open_insert_feature_dialog` | `Internal-only` | - | The dialog-open step inside browser_insert_custom_feature; separate exposure invites half-finished sequences. |
| `browser_press_key` | `Internal-only` | - | Composition primitive for keyboard input; typed tools own the trusted-event details. |
| `browser_read_featurescript` | `Keep` | - | Reads the editor buffer, which is the only way to see unsaved source that never reached the server. |
| `browser_read_selection_preview` | `Internal-only` | - | Reads a panel selection or preview card; meaningful only inside a flow that then acts on the selection. |
| `browser_reconnect` | `Internal-only` | - | Deprecated compatibility wrapper kept for older callers; `browser_session(action='reconnect')` owns the same timeout recovery transition. Hidden so session recovery has one entry point; reachable by exact name. |
| `browser_reload` | `Internal-only` | - | Deprecated compatibility wrapper kept for older callers; `browser_session(action='reload')` owns the same bounded reload. Hidden so session recovery has one entry point; reachable by exact name. |
| `browser_rename_tab` | `Keep` | - | Names the artifact a workflow just created, which is what makes it findable for later steps. |
| `browser_run_project` | `Capability` | - | Validated project runner with checkpoints: the top-level capability entry point that composes the L5 workflows. |
| `browser_scroll` | `Internal-only` | - | Composition primitive for reaching off-screen elements; a model-visible default would put raw viewport mechanics in the ordinary surface. |
| `browser_session` | `Keep` | - | Session lifecycle prerequisite for every browser tool; the human-in-the-loop login step lives here. |
| `browser_set_panel_filter` | `Internal-only` | - | Left-panel filter that prepares a selection step; exposing it invites filters that nothing then uses. |
| `browser_share_document` | `Internal-only` | - | Sharing dialog inventory; an access-control step that a human should confirm, not a modeling tool. |
| `browser_spiral_ridge` | `Capability` | - | Generate, deploy and apply a whole helical feature; it is the accepted Thread workaround and the first real capability-card proof (P6). |
| `browser_sync_rest_state` | `Keep` | - | The explicit cache-refresh action the REST policy requires; without it, state refresh would have to be implicit, which the quota rules forbid. |
| `browser_toggle_left_panel` | `Internal-only` | - | Layout affordance; it affects the screenshot a workflow takes, not the model. |
| `browser_type` | `Internal-only` | - | Composition primitive for text entry; dialog tools own field targeting and verification. |
| `browser_view_orientation` | `Keep` | - | Reads or sets the standard view; makes screenshots and geometry reads comparable over time. |
| `browser_wait` | `Internal-only` | - | Composition primitive for synchronization; ordinary tools now wait on conditions internally rather than exposing waits as steps. |
| `browser_wall_thickness_report` | `Keep` | - | Sampled measurement report for a named body; a concrete verification step for print-oriented jobs. |
| `browser_watch` | `Keep` | - | Turns a human-operated session into recorded steps, which is how new workflows get learned instead of guessed. |
| `docs_list` | `Keep` | - | Page inventory for the project's own documentation; the root of the docs lookup order. |
| `docs_search` | `Keep` | - | Keyword entry point across guide, experience and verification pages. |
| `docs_section` | `Keep` | - | Exact-section read; the bounded middle step that keeps large pages out of context. |
| `fs_check_script` | `Keep` | - | Zero-cost pre-upload gate and the only FS linter reachable from the model; prevents the quota-burning upload of a script that cannot compile. |
| `fs_check_version` | `Keep` | - | Cheap availability/version check for the vendored reference; live only when the caller asks, so it never spends quota by itself. |
| `fs_get_function` | `Keep` | - | The exact-entry step of the lookup-first order for functions; the reason the model never has to guess a signature. |
| `fs_get_type` | `Keep` | - | Same exact-entry step for types and enums, which carry the field names that payloads depend on. |
| `fs_guide_section` | `Keep` | - | The language guide is a different tree from project docs, so it cannot merge into docs_section without losing the FS-specific indexing. |
| `fs_library_source` | `Keep` | - | Last-resort full source read, bounded to the requested module rather than the whole library. |
| `fs_list_functions` | `Keep` | - | Enumeration by module and kind is how an unfamiliar area is browsed; keyword search alone cannot answer "what is in this module". |
| `fs_list_modules` | `Internal-only` | - | Deprecated compatibility wrapper kept for older callers; `fs_quick_reference` returns the same category map and, on request, the exact module rows. Hidden from every ordinary profile because a compatibility path must not look like a normal choice; reachable by exact name and in the complete `all` registry view. |
| `fs_quick_reference` | `Keep` | - | One call that answers most orientation questions (module list, counts, idioms) before any deep lookup. |
| `fs_search` | `Keep` | - | Keyword entry point across 929 functions and 270 types; the first step for any FS question. |
| `fs_update_reference` | `Internal-only` | - | Re-vendors upstream reference material. That is repository maintenance with a live fetch attached, not a design step; it belongs to an operator-invoked refresh. |
| `mcp_tool_catalog` | `Keep` | - | Authoritative registry search plus the escape hatch when a view hides a tool that the task actually needs. |
| `mcp_tool_view` | `Keep` | - | The only way to widen or narrow the visible surface for one connection without a restart; discovery plumbing the model needs before it can route. |
| `onshape_api_auth` | `Keep` | - | Authentication reference; read-only and small, and the first thing a new client setup needs. |
| `onshape_api_endpoint` | `Keep` | - | Exact operation definition (parameters, body, responses); the evidence step before any live request. |
| `onshape_api_error_codes` | `Keep` | - | HTTP code and limit semantics; what makes a 429 or 402 actionable instead of mysterious. |
| `onshape_api_list_tags` | `Keep` | - | The 42-tag map is the cheapest way to find the right API domain before searching endpoints. |
| `onshape_api_quota` | `Keep` | - | The annual-budget ledger read that must happen before any live decision; zero cost. |
| `onshape_api_schema` | `Keep` | - | Schema resolution needed to build a request body without inventing field names. |
| `onshape_api_search` | `Keep` | - | Keyword search across 302 endpoints; prevents endpoint guessing and the 400-then-guess loop the quota policy forbids. |
| `onshape_build_geometry_package` | `Capability` | - | Produces the analysis package (the actual deliverable) through the REST backend; the capability layer should expose one package entry point across backends. |
| `onshape_build_parameter_payload` | `Keep` | - | Pure local conversion to Onshape's explicit parameter payload, sharing the builder the live path uses. |
| `onshape_check_model` | `Keep` | - | Read-only model validation (features + bounding boxes); the domain check after a mutation. |
| `onshape_configure_geometry_backend` | `Internal-only` | - | Environment configuration from an opaque candidate id; a deployment decision that the operator role owns, not a modeling step. |
| `onshape_create_validation_part_studio` | `Keep` | - | Creates a throwaway Part Studio so validation never mutates a real model; one call. |
| `onshape_eval_featurescript` | `Keep` | - | The only way to test FeatureScript semantics on the real evaluator, and it costs exactly one call. |
| `onshape_export_step` | `Keep` | - | Canonical downstream deliverable, with an explicit bounded poll budget instead of open-ended polling. |
| `onshape_geometry_status` | `Keep` | - | Read-only readiness report; tells the caller whether a geometry backend exists before anything is promised. |
| `onshape_get_feature_studio_status` | `Keep` | - | Feature Studio metadata and compiled spec list; the check that a deploy actually produced the expected spec. |
| `onshape_get_parameter_set` | `Keep` | - | Reads a maintained parameter set so a human can review the exact inputs before an instantiate call. |
| `onshape_get_project_state` | `Keep` | - | Cached document/workspace/element ids at zero cost; the policy's substitute for implicit document walking. |
| `onshape_instantiate_feature` | `Capability` | - | Hard-wired to one feature type and one maintained parameter set; its real value is "place this designed feature", which is a capability card, not an operation name. |
| `onshape_list_document_elements` | `Keep` | - | Element table read, cached by default; the zero-cost path that keeps id discovery out of the request budget. |
| `onshape_render_preview` | `Keep` | - | One shaded view as evidence a feature produced geometry rather than merely listing in the tree. |
| `onshape_run_validation_pipeline` | `Capability` | - | An 8-13 call end-to-end job (upload, create studio, instantiate, verify, render). A model should invoke the capability, not orchestrate seven tools in the right order. |
| `onshape_update_feature_list` | `Keep` | - | Generic Feature-List editor (suppress, unsuppress, delete, rollback, replace) with one request per call; the undo path for a bad deploy. |
| `onshape_upload_feature_studio` | `Keep` | - | The deploy primitive: local check first, then GET/POST/GET with the microversion pinning that avoids silently instantiating an old definition. |

## What this audit changes next

The original phase was classification only: nothing was renamed, merged or hidden
to produce the table above. The verdicts pointed at five follow-up jobs. Job 1 has
since been resolved; the other four keep their original order.

1. **Print-stub archive (was: "Removals (4)"). — Done 2026-09-19.** The caller
   inventory had already been measured: no project fixture under
   `dev/fixtures-capture/` or `examples/` routed to any of the four rows, so their
   only remaining references were the registry, the permissive
   `ALLOWED_PROJECT_TOOLS` / `TOOL_OUTCOME_KEYS` tables in
   `onshape_browser_mode/project.py`, this page, and tests.
   `browser_print_orientation_check` and its dependent
   `browser_print_optimize_part` were fail-closed stubs that returned a
   `semantically invalid` compatibility result without doing the work their names
   promise, so the owner directed that those two be archived rather than kept
   fail-closed forever under the Bambu exclusion (that earlier position in
   `BROWSER_SIX_LEVEL_SEMANTICS_AND_FDM_PLAN.md` is now superseded). They are
   removed from the registry, the dispatch table, the semantics catalog, the
   project tables and `modeling_transactions`, and recorded in
   `history/legacy/ARCHIVED_BROWSER_PRINT_TOOLS.md` with their source, so a future
   print-analysis module can recover the intent without restoring a misleading
   tool name. `browser_delete_tab` and `browser_draw_part` were **not** removed:
   the same decision corrected their verdict to `Internal-only` (rule 4). The
   registered surface went from 108 to 106 tools.
2. **Hidden-by-default gaps (2). — Done.** `browser_fix_instances` and
   `browser_group_instances` were classified `Internal-only` but were still
   default-exposed (L4, `default_exposure=True`), unlike every other
   `Internal-only` browser tool. They are now hidden: reachable by exact name and
   by an explicit `semantic_levels=["L4"]` query, but absent from the ordinary
   list, which drops the semantic `tools/list` from 82 to 80. Folding them into
   `browser_assemble` remains the alternative and is not done, because that is a
   browser-side behaviour change no offline test can prove.
3. **Merges (8 rows, 6 targets). — Done.** `fs_list_modules` ->
   `fs_quick_reference` (optional `category` / `include_modules`, so the ordinary
   orientation read stays the small digest); `browser_reconnect` and
   `browser_reload` -> `browser_session` (new `action='reconnect'` and
   `action='reload'`); `browser_invoke_discovered` -> `mcp_tool_catalog`;
   `browser_drawing_insert_views` and `browser_add_drawing_dimension` ->
   `browser_draw_part_with_views` (`part_name` and `dimensions` each select a
   stage, and supplying neither is a refusal);
   `browser_geometry_status` -> `onshape_geometry_status` (one combined report for
   every backend); `browser_configure_geometry_backend` ->
   `onshape_configure_geometry_backend` (the surviving command takes
   `backend='rest'|'browser'`). Every absorbed name still works as a deprecation
   wrapper the way `browser_delete_tab` did: same result contract plus
   `deprecated` and `useInstead`. Each wrapper is removed from the ordinary views
   (browser wrappers via `default_exposure=False`, `fs_list_modules` via
   `ABSORBED_COMPATIBILITY_TOOLS` in `tool_views.py`) while remaining callable by
   exact name, and the eight rows became `Internal-only`.
   *Measured correction:* the opaque geometry candidate ids come from one shared
   dependency scan and are therefore **not** backend-specific, so an explicit
   `backend` argument is required instead of inferring the target from the
   candidate.
4. **Capability extraction (11).** The `Capability` rows are the input to the
   card layer (roadmap P4) and the first whole-feature proofs (P2, P6). The
   starting set is the four FS/geometry jobs
   (`browser_spiral_ridge`, `browser_build_part`,
   `browser_deploy_and_apply_featurescript`, `onshape_instantiate_feature`) plus
   the pipeline and drawing jobs.
5. **No action (59).** The `Keep` rows are the ordinary surface as it should be:
   lookup-first reference tools, zero-cost local reads, and the typed operations
   that report domain state rather than interaction success.

This page is referenced from `docs/INDEX.md` and from the P5 section of
`docs/roadmap/FS_FIRST_CONTROLLING_ROUTE.md`; keep the three consistent rather
than duplicating the table.
