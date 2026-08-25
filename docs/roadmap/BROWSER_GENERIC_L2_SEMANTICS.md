# Browser generic L2 semantics (roadmap)

Status: proposed, not implemented.

This roadmap records the **app-generic L2 semantics** of the Onshape browser
document shell — the regions that do **not** change with the Studio type
(Part Studio / Feature Studio / Assembly / Drawing). It is the complement to
`BROWSER_FS_SEMANTIC_TOOLS.md`, which covers FS-script-mode transactions, and
to the four-level semantic taxonomy in `DYNAMIC_TOOL_DISCOVERY.md` (L1 generic
primitives, L2 user-intent transactions, L3 workflows, L4 projects).

Evidence: live read-only screenshots (`read_image`/`vision_*`) plus DOM
inventories (`browser_inspect`/`browser_eval`) of a real document shell
(`module-interface-verification`, 2026-08-25). The center 3D/text viewport is
out of scope here; the focus is the persistent chrome around it.

## 1. The app shell (cross-studio chrome)

Every Studio tab shares the same document shell. It has three persistent
regions plus a context-region:

```
+-------------------------------------------------------------------+
| TOP NAVBAR (app-level, always present)                            |
+---+-----------------------------------------------------------+
| L |  CENTER viewport (Studio-specific: PS/FS/ASM/Drawing)    | R |
| E |  (out of scope here)                                     | I |
| F |                                                          | G |
| T |                                                          | H |
|   |                                                          | T |
+---+-----------------------------------------------------------+
| BOTTOM TAB BAR (document elements)                                |
+-------------------------------------------------------------------+
```

## 2. Top navbar (app-generic)

### 2.1 Left — brand, document identity, workspace
- Onshape logo; hamburger (main menu + doc actions).
- Document name (`navbar-document-name`) and workspace/version name
  (`workspace-or-version-name`, e.g. `Main`).
- The document-name dropdown opens app-generic document/workspace commands:
  `重命名文档`, `移至…`, `文档详细信息…`, `还原已删除的工作区…`,
  `复制工作区…`, `更新工作区…`, `工作区单位…`, `工作区属性…`, `打印…`,
  `关闭文档`.

### 2.2 Middle — per-tab tool (Studio-specific, not generic)
The middle toolbar (`草图`/建模 tools, `搜索工具…` command-search, `插入`)
depends on the active Studio. **Not** generic L2; noted only to exclude it.

### 2.3 Right — global actions (app-generic, always present)
- Search; `探索 Onshape`; notifications (badge count `6`); app-store / help
  (`在新窗口中将您导航到…`); `共享` share button; user `jiaqi Li`.
- `搜索工具… alt/⌥c` (`.command-search-trigger`) — the persistent command
  palette entry; its popup `.command-search` type-to-search spans the current
  tab's toolset (empty in FS for native-modeling terms).

These are app-generic and identical across Studio types. L2 semantics here
would target stable ids/aria: `#user-notification-status`, `.nav-share`,
`.command-search-trigger`, `.navbar-document-name`.

## 3. Left panel (side panel + vertical icon rail)

### 3.1 Vertical icon rail (leftmost)
A column of switches that opens different side panels. Observed roles
(icon → side panel):
- panel/tree list → document structure / feature tree,
- create/add → new element,
- comment bubble → comments,
- document/note → notes,
- history/timer → version history / timeline,
- magnifier/inspect → measure/analysis,
- checklist/properties → properties.

### 3.2 Side panel content (per active Studio — the tree is Studio-specific,
but the *shell* around it is generic)
- Filter row: funnel icon + `按名称或类型筛选` search box (`.os-search-box-input`).
- Panel header with generic action buttons: `new-folder-button`,
  `enter-delayed-regen-button`, `regen-info-button`
  (`feature-list-header-button`).
- The tree body (`os-list-item`, `ns-user-feature`, `is-instance`,
  `is-folder`) is Studio-specific; the shell (filter/header) is generic.

### 3.3 Collapse handle and preview card
- Side panel collapse/expand handle.
- A bottom preview card (`os-feature-preview`, part thumbnail) for the current
  selection.

The generic L2 target is the **panel shell**: `toggle panel`, `set panel filter`,
`collapse/expand panel`, `read selection preview`. The tree semantics belong to
the Studio-specific documents.

## 4. Bottom tab bar (document elements)

The persistent list of open document elements across the whole document:

### 4.1 Tab element (`.os-tab-bar-tab`, `.os-tab-name`)
Each tab is a document element (Feature Studio / Part Studio / Assembly /
Drawing). Active tab marked `.active`. Tab has a per-element icon
(`data-icon-src="feature-studio-element"` etc.) and a dirty/`*` marker
(`ng-hide` until changed).

### 4.2 Right-click context menu (generic element ops)
Right-clicking a tab opens app-generic element commands (verified):
`删除`, `在新浏览器页签中打开`, `重命名`, `属性…`, `复制`,
`复制到剪贴板`, `创建 <name> 的工程图…`, `选择为文档缩略图`,
`移至文档…`, `导出…`.

These are the generic L2 transactions for a document element regardless of its
Studio type. The `创建 <name> 的工程图…` item matches the coupling documented
in `BROWSER_MODELING_GAPS.md` (drawing auto-views come from the context menu,
not the generic dialog).

### 4.3 Add-tab entry (`os-add-tab-menu-divider`, `+` button)
The bottom-left `+` opens the generic "create element" menu (Create Feature
Studio / Part Studio / Assembly / Drawing / Folder / Table / Import / Paste
tab), already covered by `browser_create_tab`.

## 5. Viewport chrome (right/edge, app-generic)

- View Cube (isometric orientation gizmo, top-right of the viewport).
- Right-edge vertical tool rail (part view controls: section, measure, etc.).
- Bottom status strip: `Poor connection…` (`os-help-link`) — network health,
  app-generic.
- `measure-button`, `analysis-button`, `mass-properties`
  (`document-tabs-button`) — the read surfaces a printability/measure check
  would consume (referenced by `BROWSER_FS_SEMANTIC_TOOLS.md`).

## 6. Generic L2 transaction candidates

These are the app-generic L2 transactions (one user intent, own acceptance
evidence) that do not depend on Studio type, most reusable across the whole
document shell:

| Candidate L2 | Region | Evidence source | Verifies |
|---|---|---|---|
| `browser_open_doc_menu` | top navbar left | dropdown-menu document-dropdown-menu | menu shown; item clicked |
| `browser_set_panel_filter` | left panel | `.os-search-box-input` (+ funnel) | filter applied; tree narrows |
| `browser_toggle_left_panel` | left panel | collapse handle / icon rail | panel shown/hidden |
| `browser_read_selection_preview` | left panel | preview card | preview card visible |
| `browser_element_context_menu` | bottom tab bar | `.context-menu-list` on `.os-tab-bar-tab` | item list matches |
| `browser_rename_element` | bottom tab bar | context menu → 重命名 → `TAB_RENAME_INPUT` | tab name changed |
| `browser_duplicate_element` | bottom tab bar | context menu → 复制 | new tab appears |
| `browser_delete_element` | bottom tab bar | context menu → 删除 → confirm | tab detached |
| `browser_drawing_from_element` | bottom tab bar | context menu → 创建工程图 | drawing frame created |
| `browser_notifications_status` | top navbar right | `#user-notification-status` | badge count read |
| `browser_share_document` | top navbar right | `.nav-share` | share dialog opened |
| `browser_view_orientation` | viewport chrome | view cube | orientation read/set |

These compose on the existing L1 primitives (`browser_click`/`browser_type`/
`browser_press_key`/`browser_wait`/`browser_inspect`/`browser_eval`) and on
`browser_capture_screenshot` for visual verification, per the L1-to-L4 layering.

## 7. Selectors / frame notes

- Stable anchors: `.os-tab-bar-tab`, `.os-tab-name`, `.navbar-document-name`,
  `.command-search-trigger`, `#user-notification-status`, `.nav-share`,
  `.os-search-box-input`, `.feature-list-header-button`,
  `button.measure-button`, `button.analysis-button`, `button.mass-properties`.
- The always-present search box `.os-search-box-input` and the tab context menu
  are confirmed generic. Selector evidence should follow the established
  discipline: record into `dev/button-map/` and `onshape_browser_mode/selectors.py`
  before any automation depends on them.

## 8. Inferred high-value features (browser observation + official docs)

Cross-referencing the live shell observation with the vendored Onshape REST
reference, the following app-generic capabilities stand out as high-value
browser L2/L3 semantics. Each row gives the user intent, the browser evidence
(what the shell exposes) and the official REST endpoint that would back it.
Nothing here is implemented; it is a plan input.

| Feature | User intent | Browser evidence | Official REST reference |
|---|---|---|---|
| Tab navigation / management | switch, reorder, open-here, close tab | `.os-tab-bar-tablist`, `.os-tab-bar-tab.active`, `.os-tab-name` | `getElementsInDocument` (`/documents/d/{did}/{wvm}/{wvmid}/elements`) |
| Element context actions (rename/copy/delete/export) | one-element ops independent of Studio type | tab context menu: 重命名/复制/删除/导出… | rename/delete via document element; `export2Json` (`POST /documents/.../e/{eid}/export`), assembly/part-studio `export/step|obj|gltf` |
| Global / command search | jump to a tool or command from anywhere | `.command-search-trigger`, `.command-search` (alt/⌥c) | UI-only command palette; no REST equivalent (search is client routing) |
| History tree management | step through document/version history, compare | left rail history/timeline icon, `enter-delayed-regen-button`, `regen-info-button` | `getDocumentHistory` (`GET /documents/.../documenthistory`), `getRevisionHistory...` (`/revisions/...`), `getCurrentMicroversion` |
| Comments / annotations | add, reply, resolve, attach to a feature | left rail comment bubble; context-menu 添加评论 | `createComment`/`getComments`/`updateComment`/`deleteComment`/`addAttachment` (`/comments`) |
| Notifications | read unread count, open the notifications drawer | `#user-notification-status` badge `6`, aria 通知; `（6 个未读通知）` | UI-level; notification feed is not exposed over the documented REST surface |
| Action items | open the action-items page, triage tasks | nav action-items button (「在新窗口中将您导航到"行动项"页面。」) | UI-level; action items are not a documented REST resource |
| Assigned / review workflows | see who owns a task, hand off | navbar action-item + share icons; `协作完成`/`监控 <part-studio>` | Company/user endpoints; review state is UI-only |
| Drawing auto-views from a part | insert auto-views from a produced part | tab/part context menu `创建 <name> 的工程图…` | Drawing creation + `browser_drawing_insert_views` coupling (see `BROWSER_MODELING_GAPS.md`) |
| Workspace / version & unit control | switch workspace, set document units | doc-name menu: 工作区单位/工作区属性/更新工作区/复制工作区 | `getElementsInDocument` in a version/workspace; workspace/version endpoints |

### 8.1 Priority and sequencing

- **P0 (browser-only, no live quota)**: tab navigation/management, element
  context actions, command/global search, view orientation. These reuse existing
  L1 primitives and `browser_capture_screenshot`; they are the highest-leverage
  app-generic L2 transactions.
- **P1 (browser + a small number of read-only REST calls)**: history tree
  (document/version history), comments list/create. These map to documented
  endpoints and provide real cross-document value.
- **P2 (UI-only, may need live quota or human)**: notifications, action items,
  review workflows. These live mainly in the Onshape web app; a browser L2 that
  opens the matching page/panel is the honest scope until the REST surface is
  clarified.

### 8.2 Cost discipline

Browser L2 semantics stay zero-REST. When a feature needs backing data (history,
comments), prefer a browser panel read over a live API call, and reuse the
`onshape_check_model` / `onshape_list_document_elements` cached paths before any
live request. Any live call follows the CLAUDE.md hard budget rules (one new
fact, `expected_live_requests=1`, no retry on 429/5xx).

## Provenance

- Live evidence: `read_image`/`vision_glance` on screenshots + `browser_inspect`/
  `browser_eval` DOM inventories of `module-interface-verification`
  (PS-PartA-wall, 2026-08-25). Login via saved entry URL; no cloud mutation
  during exploration.
- Related: `BROWSER_FS_SEMANTIC_TOOLS.md` (FS-script-mode transactions),
  `BROWSER_MODELING_GAPS.md` (drawing auto-views via context menu),
  `DYNAMIC_TOOL_DISCOVERY.md` (four-level taxonomy).
