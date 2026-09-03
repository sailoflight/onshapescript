# Browser planned-tool registry (roadmap, deduped)

Status: implemented registry is current. Two new planned rows were filed on
2026-09-02 (whole-document inventory/delete, see §1a) after a real dual-environment
test incident exposed the gap; they are not yet implemented. The 104-tool
registry was re-audited for aliases and contract overlap after implementation;
that audit introduced no other new planned tool names.

This is the **single authoritative list** of browser tools that are planned but
not yet implemented. It consolidates the per-document tool proposals in
`BROWSER_FS_SEMANTIC_TOOLS.md` (FS script mode), `BROWSER_GENERIC_L2_SEMANTICS.md`
(app-generic shell), and `BROWSER_MODELING_GAPS.md` (modeling-round gaps), so the
same tool is described once here instead of repeated across documents.

Current behavior keeps a complete static registry but defaults `tools/list` to
the semantic exposure described by `../architecture/OVERVIEW.md`; the
already-implemented `browser_*` tools are **not** in this list. Optional six-level semantics per
`DYNAMIC_TOOL_DISCOVERY.md` range from L1 browser primitives through L6
deliverable recipes; project control is outside L1-L6.

## 1. Implemented rows that moved to the static registry (history)

The rows previously listed here moved to the static MCP registry on 2026-08-25:

- FS/script and coupling: `browser_fs_goto_definition`,
  `browser_fs_insert_snippet`, `browser_fs_insert_parameter`,
  `browser_fs_toggle_fold`, `browser_edit_feature_parameters`, and
  `browser_fs_watch_part_studio`.
- Drawing/print/modeling: `browser_drawing_insert_views`,
  `browser_draw_part_with_views`, `browser_print_orientation_check`,
  `browser_wall_thickness_report`, `browser_apply_blend`,
  `browser_print_optimize_part`, and `browser_spiral_ridge`.
- App shell: `browser_open_doc_menu`, `browser_set_panel_filter`,
  `browser_toggle_left_panel`, `browser_read_selection_preview`,
  `browser_element_context_menu`, `browser_duplicate_element`,
  `browser_notifications_status`, `browser_share_document`, and
  `browser_view_orientation`.

Their schemas and handlers are in `mcp_main/win/mcp/browser_tools.py`; L3-L5
interactions/transactions/workflows are in `onshape_browser_mode/transactions.py` and
`onshape_browser_mode/modeling_transactions.py`. Offline acceptance tests live
in `dev/tests/test_browser_planned_tools.py`. Read-only field evidence is in
`dev/button-map/scan-fs-editor.json`, `scan-fs-module-outline.json`, and
`scan-app-shell.json`. Cloud-mutating Windows smoke remains an explicit,
separately authorized validation activity; lack of that authorization is
reported as an unexecuted validation, not as an unimplemented tool.

Registry presence is distinct from semantic validity. The later six-level review
marks `browser_print_orientation_check` and its dependent
`browser_print_optimize_part` default-hidden and `semantically_invalid`: draft
analysis is not an FDM orientation engine. Their replacement belongs to the
shared STEP/converter/Bambu plan in
`BROWSER_SIX_LEVEL_SEMANTICS_AND_FDM_PLAN.md`; this does not recreate the old
planned-tool rows.

Implemented tools are intentionally absent from this registry. On 2026-08-25,
`browser_get_fs_compile_status` and `browser_get_fs_symbols` also moved to the
static MCP registry; their current contracts are defined by `mcp_main` schemas
and offline tests, while `BROWSER_FS_SEMANTIC_TOOLS.md` retains the design rationale.

`browser_drawing_insert_views` is the single name for "insert drawing auto-views
from a part". `browser_drawing_from_element` (in
`BROWSER_GENERIC_L2_SEMANTICS.md`) is renamed to it. `browser_draw_part_with_views`
is distinct only when at least one dimension is required; its public schema now
enforces that boundary. `browser_delete_element` is the preferred exact data-id
deletion contract. The name-addressed `browser_delete_tab` remains a
default-hidden deprecated compatibility wrapper that requires one exact unique
name and delegates to the same ID core. Neither compatibility name is a new plan
item.

## 1a. Planned rows filed 2026-09-02 (document inventory / whole-document delete)

**Trigger incident (2026-09-02, real dual-environment run):** DSH and CODEX both
drove the same Onshape account through the browser MCP (one migrated browser
profile). CODEX created a working document and then crashed while its
FeatureScript still had 28 compile errors; the operator needed to (a) inventory
which documents the account actually contained, and (b) delete the broken whole
document to restore the pre-test state. Neither capability exists yet in the
browser toolset: `browser_open_document` opens by exact visible name,
`browser_delete_element` deletes a document *element* (tab), and no tool lists
"owned by me" documents or deletes a whole document. Delete had to be done by
hand in the web UI.

Planned rows (names reserved; none implemented yet):

| Tool | Level | Intent | Contract boundary | Confirmation |
|---|---|---|---|---|
| `browser_list_documents` | L3 interaction (read) | Inventory the "owned by me" documents page (visible name, document id, modification time) so an agent can pick/reconcile/clean up documents. | Read-only DOM read of the documents grid (`.os-document-list-*`, `#search-box` per `browser-automation.md` §4.1); zero REST; returns a bounded list with ids. | none (read-only) |
| `browser_delete_document` | L4 transaction | Delete a whole document by document id from the documents list, after an explicit id-addressed confirmation. | Destructive and irreversible; requires one exact document id; performs the web-UI delete flow and verifies the document row disappears; never deletes by fuzzy name. | `confirm_mutation=true` + `dry_run` supported |

Notes:

- They pair with the existing `browser_create_document` /
  `browser_duplicate_element` / `browser_share_document`; no alias overlaps were
  found in the 104-tool registry audit.
- Implementation must keep zero-REST (network=browser); delete is a cloud
  mutation through the UI, so it follows the same confirmation/pacing guards as
  other browser mutations.
- Not implemented: these rows are a requirement filing only. The offline
  acceptance tests keep them out of `PLANNED_NAMES`/`server.TOOLS` until a
  Developer implements them.

## 2. Naming / de-dup notes

- `browser_drawing_from_element` → **`browser_drawing_insert_views`** (one intent, one name).
- `browser_rename_element` → implemented as `browser_rename_tab`; no new tool.
- `browser_delete_element` → **implemented and preferred**; the deprecated
  name wrapper is default-hidden and resolves only an exact unique name to this
  ID-addressed core.
- `browser_draw_part_with_views` requires one or more dimensions;
  `browser_drawing_insert_views` is the views-only contract.
- `browser_draw_part` is a default-hidden generic-drawing compatibility workflow;
  empty dimensions fail before any browser action.
- `browser_tools` is the Python module name, not a tool; excluded.
- Print tools (`browser_print_orientation_check`, `browser_apply_blend`,
  `browser_draw_part_with_views`, `browser_drawing_insert_views`) were deduped
  here before implementation; `BROWSER_MODELING_GAPS.md` retains their gap and
  resolution history.

## 3. References

Each proposal document keeps its rationale and now points to this registry's
implementation record:

- `BROWSER_FS_SEMANTIC_TOOLS.md` — FS script-mode transactions (§3) and
  coupling points (§4); details the FS items here.
- `BROWSER_GENERIC_L2_SEMANTICS.md` — app-generic shell (§6 candidates); the
  renamed `browser_drawing_insert_views` and the implemented delete/rename links
  are noted there.
- `BROWSER_MODELING_GAPS.md` — the modeling-round gaps and their implemented
  print/drawing/spiral resolutions.
- `DYNAMIC_TOOL_DISCOVERY.md` — the six-level taxonomy and exposure model.

## Provenance

Consolidated 2026-08-25 from the three roadmap documents; the same tools were
found described in more than one of them (print/blend/drawing-views appear in
both `BROWSER_FS_SEMANTIC_TOOLS.md` and `BROWSER_MODELING_GAPS.md`, and the
drawing-views intent had two names). This registry is the deduped source.
