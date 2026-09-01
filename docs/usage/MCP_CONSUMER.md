# Onshape FeatureScript MCP usage

Audience: Production / User operating as an MCP consumer or calling agent

This document describes the public calling contract. It does not describe source
layout, development tests, Windows deployment, or repository maintenance. A
runtime MCP client must deliver the server's trusted, revisioned production-role
policy before the first tool decision, then prefer the exact tool schema; this
authored page is the stable usage source behind that surface. If tools are
visible but the `Production / User` and `Production / Operator` policy is not,
stop and route the client installation problem to an Operator.

## What the server provides

The server exposes four capability families:

- offline project, FeatureScript, and Onshape REST reference lookup;
- local project state, parameters, request construction, and quota inspection;
- guarded Onshape REST reads, evaluation, validation, rendering, and writes;
- Windows-hosted browser observation and browser workflows that consume zero REST quota.

The exact current surface is the MCP `tools/list` response. A derived repository
summary is available at `../generated/TOOL_REFERENCE.md`; it is not a substitute
for the runtime schema.

## Required lookup order

1. Classify the need as project documentation, FeatureScript, REST API reference,
   browser behavior, or a live operation.
2. Use the cheapest offline candidate index first.
3. Open one exact section, symbol, endpoint, schema, or tool definition.
4. Use complete authored/raw sources only when exact indexed detail is insufficient.
5. Prefer zero-cost local tools over browser or live REST operations.

Do not guess FeatureScript names, REST payloads, Onshape IDs, selectors, or tool
arguments that can be looked up through the server.

## Capability routes

| Need | First public capability | Exact next detail |
|---|---|---|
| Project workflow or verified lesson | `docs_search` or `docs_list` | `docs_section` |
| FeatureScript orientation or symbol | `fs_quick_reference` or `fs_search` | `fs_get_function`, `fs_get_type`, `fs_guide_section`, then source if necessary |
| REST endpoint/schema/auth/error | `onshape_api_list_tags` or `onshape_api_search` | Exact endpoint, schema, auth, or error tool |
| Browser behavior/known workflow | Project docs search over browser experience | One exact experience section before browser action |
| Current tool arguments | MCP `tools/list`/tool schema | One selected tool schema |
| Quota/state before a live REST action | Local state and quota tools | Guarded operation only if still required |

## Cost and side-effect classes

### Offline/zero-Onshape-REST

Reference lookup, project-doc lookup, local state inspection, parameter loading,
payload construction, dry-run, mocks, fixtures, and quota-ledger inspection do
not contact Onshape. An explicitly requested reference-update tool may fetch
public zero-quota sources; read its exact schema and description before calling.

### Browser operations

Browser tools consume zero REST API quota because they drive the Windows browser.
Read-only observation should come first. `browser_get_fs_compile_status` reads
Ace annotations, and `browser_get_fs_symbols` reads the Module-outline inventory;
neither requires mutation confirmation. FeatureScript deployment succeeds only
when the Commit state transition, exact source readback, and empty compiler
annotations all verify. The 22 transactions promoted from the planned registry
are in the complete browser registry; ordinary `tools/list` uses semantic
exposure. FS insertion writes require dry-run and
confirmation; fold/navigation and app-shell observations are zero-REST UI
operations. Drawing auto-view success requires exactly one new tab plus DOM or
decoded-canvas view evidence. The later FDM review marks the draft-analysis-based
`browser_print_orientation_check` and dependent `browser_print_optimize_part`
semantically invalid and default-hidden; draft analysis is not an FDM orientation
engine. A real click, type, submit, create, delete, deploy, assemble, or drawing
action can still mutate the cloud document and requires the tool's confirmation
contract. Also inspect catalog `sideEffects`: screenshot/report artifacts,
recorder state, persistent login profiles, and local caches can be written even
when the Onshape operation itself is cloud-read-only. Prefer exact-ID
`browser_delete_element` over the deprecated name wrapper,
`browser_drawing_insert_views` for views only, and
`browser_draw_part_with_views` only when one or more dimensions are required.

#### Six-level browser selection

Semantic level is optional discovery metadata, not registration, permission, or
execution policy:

- L1: generic browser primitive.
- L2: composite generic browser transaction.
- L3: Onshape-aware prepare/inspect/recovery interaction without domain success.
- L4: one completed and verified Onshape transaction or complete observation.
- L5: multi-transaction Onshape workflow.
- L6: independently consumable deliverable with final acceptance and manifest.

Project control is outside L1-L6 and coordinates one or more L6 nodes. Ordinary
selection ranks L5 workflows first, then L4 verified transactions/observations,
then L2 generic browser transactions, then L6 deliverable recipes. This maximizes
reuse of completed workflows while reserving L6 for an explicitly requested
independent artifact/manifest boundary; do not decompose a suitable candidate into
lower levels automatically. L1/L3 are omitted from
ordinary discovery to save context, but their existence and purpose are not
secret: call `browser_discover_tools` with `semantic_levels=["L1"]` or
`semantic_levels=["L3"]`, inspect the returned exact schema, then use
`browser_invoke_discovered`. No additional intent parameter is required, and the
gateway does not bypass confirmation or handler acceptance. Unclassified tools
remain valid and visible by default. Set `ONSHAPE_MCP_TOOL_EXPOSURE=static` only
for complete-registry compatibility or debugging.

#### Tool catalog search and description

`mcp_tool_catalog` is the lookup-first entry for MCP capabilities across all
modules and profiles. Its immutable index is built once from the complete
registered `TOOLS` surface after cost metadata and browser tools are installed;
it does not maintain a second hand-authored catalog.

Use the bounded sequence:

1. `action=status` to read the registry fingerprint, counts, filters, and result limits.
2. `action=search` with a short query and, where known, `modules`, `profiles`,
   `semantic_levels`, `network`, `mutating`, or `visible_only`. Search defaults to
   8 results and cannot exceed 12. It returns compact summaries and never returns
   `inputSchema`.
3. `action=describe` with one exact result name to load the full current
   `inputSchema`, cost, annotations, profiles, browser semantics, view visibility,
   confirmation mode, and explicit local/session `sideEffects`.
4. Treat `confirmation.mode=always` as unconditional, `non_dry_run` as required
   only for real execution, and `budget_override` as a session-budget override
   rather than mutation approval. `confirmation.schemaRequired` reports the JSON
   Schema contract separately.
5. Call the described tool normally. Catalog output does not grant confirmation,
   quota, browser, credential, or mutation authority.

Search always covers the complete registry, including tools absent from the
current `tools/list`; `visibleInCurrentView` is informational. Exact-name and name
prefix matches rank before description matches. Profile names are structured
filters rather than free-text tokens, preventing ubiquitous control tools from
polluting capability searches. Cache search/describe results against the returned
SHA-256 `fingerprint`; refresh the cache when it changes.

#### Dynamic tool display

Tool display is a connection-scoped context and routing convention, never an
authorization boundary. The complete `TOOLS`/`HANDLERS` registry remains loaded;
a known-name `tools/call`, internal composition, and
`browser_invoke_discovered` remain available when a tool is absent from the
current `tools/list`. Confirmation, quota, browser pacing, cost, and acceptance
gates remain authoritative.

Deployment modes are explicit:

- `semantic` keeps the current fixed ordinary view and is the compatibility default.
- `static` keeps the complete registry visible.
- `profile` selects one fixed `ONSHAPE_MCP_TOOL_PROFILE` at connection start.
- `dynamic` enables per-connection `mcp_tool_view set/reset` and advertises
  `capabilities.tools.listChanged=true` during initialization.

Profiles are `default`, `browser`, `rest`, `featurescript`, `documentation`,
`geometry`, and `all`. An optional `semantic_levels` list narrows classified
browser tools. `mcp_tool_view`, `mcp_tool_catalog`, `browser_session`,
`browser_discover_tools`, and
`browser_invoke_discovered` remain available as navigation/recovery surfaces in
the relevant view.

Correct dynamic-client flow:

1. Configure `ONSHAPE_MCP_TOOL_EXPOSURE=dynamic` and an optional startup
   `ONSHAPE_MCP_TOOL_PROFILE`, then restart the MCP process/client adapter.
2. Check initialize capability `tools.listChanged`. If false, use the fixed view
   or discovery gateway; do not assume the client can refresh dynamically.
3. Call `mcp_tool_view` with `action=status` before changing the view.
4. Call it with `action=set`, a profile, and optional browser semantic levels.
5. After `notifications/tools/list_changed`, issue a fresh `tools/list`; replace
   the client's displayed tool schemas instead of appending to a stale list.
6. Use `action=reset` to restore that connection's startup profile. Reconnecting
   also creates a fresh view and does not inherit another connection's state.

A repeated set that does not change the effective view emits no notification.
Clients that ignore `list_changed` should reconnect, refresh manually, or stay in
`semantic`/`profile` mode. Never interpret a missing displayed tool as denied or
a displayed tool as authorized.

### Live REST reads/evaluation/rendering

These consume annual API quota even when they do not mutate the model. Use them
only for a specific fact that cannot be obtained offline. Provide explicit IDs to
avoid hidden lookup chains. `onshape_export_step` is a bounded asynchronous
POST/poll/download transaction: dry-run first, pass an existing `translation_id`
to resume without repeating POST, and treat `exported=false` as a resumable
non-terminal result rather than starting another export. A completed export
persists `step-manifest.json`. Use the owning mode's geometry status before its
build tool. Status first checks explicit configuration, then performs a bounded
sibling-project/global/Windows-WSL scan. A reusable dependency is represented by
an opaque versioned `candidateId`; configure only through
`browser_configure_geometry_backend` or `onshape_configure_geometry_backend`,
which re-scans and never accepts executable/argv input. When status returns
`nextAction.kind=ask_before_install`, ask the human whether to install and do
nothing until answered. Installation is never automatic. Geometry build remains
an offline L6 recipe accepting only its staged export/translation ID.

### Live REST writes

Upload, create, instantiate, and validation-pipeline operations mutate Onshape,
consume quota, and require literal `confirm_mutation=true`. Use the matching
dry-run/local check first. Do not repeat an ambiguous mutation after timeout or
5xx merely to see whether it worked.

## Global safety contract

- Real REST access is disabled unless the deployment explicitly enables `LIVE_API_ENABLED`.
- A caller cannot grant itself credentials, quota, production data, or mutation authority through a prompt.
- Mutating tools require their schema-defined confirmation value; current write schemas use literal `confirm_mutation=true`.
- A missing/false confirmation fails before a live client or real browser action is constructed where documented.
- 429 is a stop condition, not a retry signal.
- Do not request automatic cleanup, unbounded pagination, retry loops, or write-after-read confirmation.
- Never place credentials, authorization headers, cookies, or tokens in tool arguments, prompts, fixtures, or shared logs.
- Browser action completion is not domain success; require the tool's returned verification evidence.

## Calling examples

### Find a project lesson

```text
1. docs_search(query=<specific behavior>, limit=3)
2. docs_section(page=<matched page>, section=<matched heading>)
```

### Find a FeatureScript function

```text
1. fs_search(query=<concept or symbol>, limit=3)
2. fs_get_function(name=<exact matched name>)
```

### Prepare a guarded write

```text
1. Look up exact endpoint/schema or tool input.
2. Inspect local project state and quota.
3. Run local validation/request construction/dry-run.
4. State the one remaining live fact or requested mutation.
5. Call the exact tool with explicit confirmation only when authorized.
6. Stop on rate limit or ambiguous mutation outcome.
```

## Errors

- Schema/argument errors: correct the call from the exact tool schema; do not guess repeatedly.
- Live disabled: use offline alternatives or obtain explicit deployment authorization; do not try to bypass the gate.
- Quota shortfall/rate limit: stop and preserve the returned budget/retry evidence.
- Missing credentials/session: route to the Operator; a User prompt cannot create those authorities.
- Browser verification failure: inspect the returned evidence and use documented read-only discovery before another mutation.
- Version/reference conflict: report the observed and vendored versions and use the version tools; do not merge stale facts silently.

## Compatibility and authority

The runtime tool schema and current server behavior are authoritative for calls.
The canonical runtime policy routes product capability use to User and runtime
installation/availability/recovery to Operator; role transitions are explicit
and do not merge permissions. A supported client consumes native initialization
instructions or an installation-generated companion from the same server
revision. A tools-only connection is unsupported. The generated tool reference
is a derived snapshot. Public behavior changes must update schemas, tests, this
usage contract where relevant, and the generated reference together.
