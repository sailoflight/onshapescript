# Browser planned-tool registry (roadmap, deduped)

Status: proposed, not implemented.

This is the **single authoritative list** of browser tools that are planned but
not yet implemented. It consolidates the per-document tool proposals in
`BROWSER_FS_SEMANTIC_TOOLS.md` (FS script mode), `BROWSER_GENERIC_L2_SEMANTICS.md`
(app-generic shell), and `BROWSER_MODELING_GAPS.md` (modeling-round gaps), so the
same tool is described once here instead of repeated across documents.

Current behavior is the static registry described by `../architecture/OVERVIEW.md`
and generated from `mcp_main` — the already-implemented `browser_*` tools are
**not** in this list. Four-level semantics per `DYNAMIC_TOOL_DISCOVERY.md`
(L1 primitives, L2 transactions, L3 workflows, L4 projects).

## 1. Planned tools (single source of truth)

| Tool | Level | Domain | Status | Description / acceptance |
|---|---|---|---|---|
| `browser_get_fs_compile_status` | L2 read | FS script | planned | read Ace `session.getAnnotations()` → `{compiled, errors, annotationCount}`; require empty annotations for `deployed: true` |
| `browser_get_fs_symbols` | L2 read | FS script | planned | read Module outline → `{symbolCount, symbols:[{kind,name}]}` |
| `browser_fs_goto_definition` | L2 | FS script | planned | Ace context menu 转至定义 on a symbol → cursor/jump target |
| `browser_fs_insert_snippet` | L2 | FS script | planned | Ace context menu 插入代码段 to insert a FeatureScript template |
| `browser_fs_insert_parameter` | L2 | FS script | planned | `Length parameter` toolbar button → insert a typed parameter |
| `browser_fs_toggle_fold` | L1/L2 | FS script | planned | toggle `ace_fold-widget` regions; return folded ranges |
| `browser_edit_feature_parameters` | L2 | FS apply | planned | read/write a custom feature's `.feature-dialog` fields before accept |
| `browser_fs_watch_part_studio` | L2 | FS↔PS | planned | drive `监控 <part studio>`/`配置文件` and read regen state |
| `browser_drawing_insert_views` | L2 | drawing | planned | from `创建 <name> 的工程图…` context menu → pick layout → place views → verify frame geometry change. **Supersedes `browser_drawing_from_element`.** |
| `browser_draw_part_with_views` | L3 | drawing | planned | create drawing → auto-views → dimensions → return frame/view state |
| `browser_print_orientation_check` | L2 read | print | planned | read view/orientation + measure surface → overhang/wall-risk report |
| `browser_wall_thickness_report` | L2 read | print | planned | sample/verify min wall thickness on a body |
| `browser_apply_blend` | L2 write | print | planned | fillet/chamfer/draft on selected edges/faces with dry-run + history readback |
| `browser_print_optimize_part` | L3 | print | planned | build → blend (optional) → orientation/wall report → verify |
| `browser_open_doc_menu` | L2 | app shell | planned | open document-name dropdown; click a doc/workspace command |
| `browser_set_panel_filter` | L2 | app shell | planned | set left-panel filter (`按名称或类型筛选`); tree narrows |
| `browser_toggle_left_panel` | L2 | app shell | planned | collapse/expand left panel via handle / icon rail |
| `browser_read_selection_preview` | L2 | app shell | planned | read the left-panel selection preview card |
| `browser_element_context_menu` | L2 | app shell | planned | open tab context menu; return item list |
| `browser_duplicate_element` | L2 | app shell | planned | context menu 复制 → new tab appears |
| `browser_notifications_status` | L2 | app shell | planned | read `#user-notification-status` badge count / drawer |
| `browser_share_document` | L2 | app shell | planned | open `.nav-share` dialog |
| `browser_view_orientation` | L2 | app shell | planned | read/set the view cube orientation |
| `browser_spiral_ridge` | L2→L3 | native modeling | deferred | helix+sweep ridge on a cylinder (native feature-mode; deferred from FS plan) |

`browser_drawing_insert_views` is the single name for "insert drawing auto-views
from a part". `browser_drawing_from_element` (in
`BROWSER_GENERIC_L2_SEMANTICS.md`) is renamed to it. Tab-level rename/delete
already exist as `browser_rename_tab` / `browser_delete_tab` (implemented) and
are not re-planned; `browser_delete_element` (implemented) is likewise not a
plan item.

## 2. Naming / de-dup notes

- `browser_drawing_from_element` → **`browser_drawing_insert_views`** (one intent, one name).
- `browser_rename_element` → implemented as `browser_rename_tab`; no new tool.
- `browser_delete_element` → **implemented**; not a plan item.
- `browser_tools` is the Python module name, not a tool; excluded.
- Print tools (`browser_print_orientation_check`, `browser_apply_blend`,
  `browser_draw_part_with_views`, `browser_drawing_insert_views`) appear once
  here; `BROWSER_MODELING_GAPS.md` references them instead of restating.

## 3. References

Each proposal document keeps its narrative (why the gap exists) and points to
this registry for the consolidated tool list:

- `BROWSER_FS_SEMANTIC_TOOLS.md` — FS script-mode transactions (§3) and
  coupling points (§4); details the FS items here.
- `BROWSER_GENERIC_L2_SEMANTICS.md` — app-generic shell (§6 candidates); the
  renamed `browser_drawing_insert_views` and the implemented delete/rename links
  are noted there.
- `BROWSER_MODELING_GAPS.md` — the concrete modeling-round gaps; its print and
  drawing tools are listed here and cross-referenced there.
- `DYNAMIC_TOOL_DISCOVERY.md` — the four-level taxonomy and exposure model.

## Provenance

Consolidated 2026-08-25 from the three roadmap documents; the same tools were
found described in more than one of them (print/blend/drawing-views appear in
both `BROWSER_FS_SEMANTIC_TOOLS.md` and `BROWSER_MODELING_GAPS.md`, and the
drawing-views intent had two names). This registry is the deduped source.
