# Dynamic MCP tool discovery roadmap

Status: semantic/static/profile/dynamic exposure and connection-scoped replacement implemented

The optional six-level catalog, bounded browser discovery, hidden-tool invocation
gateway, semantic default exposure, static compatibility mode, fixed startup
profiles, and connection-scoped `listChanged` replacement are implemented.
Dynamic display is explicitly a context-routing convention rather than an
execution or authorization constraint.

> The concrete FS script-mode transactions (compile-status, symbols, parameter
> edit) and their Part-Studio coupling points (part context-menu drawing
> auto-views) are itemized in `BROWSER_FS_SEMANTIC_TOOLS.md`, with live-browser
> evidence. Native feature-mode transactions remain Phase D of this roadmap and
> are currently out of the FS-mode plan's scope.

## Problem

As browser and native-modeling tools grow, returning every tool description and
input schema in every MCP context increases tool-schema and routing cost. The
target is progressive discovery without deleting complete capabilities.

```text
small fixed MCP entry
  -> module
  -> capability/submodule
  -> optional semantic level
  -> bounded candidate tools
  -> exact schema only when selected
```

## Classification model

Keep three independent axes:

```text
(module, submodule/capability, semantic_level?)
```

- `module`: runtime, code, and safety owner; required.
- `submodule`: capability family inside a module; required where the module has submodules.
- `semantic_level`: optional L1-L6 discovery metadata, not a registration or permission gate.

Initial modules proposed by the legacy plan:

1. `documentation`
2. `featurescript`
3. `rest_api`
4. `browser`

Browser capability families proposed:

```text
session | document | featurescript | partstudio | assembly | drawing |
native_modeling | project
```

Semantic levels:

- L1 `browser_primitive`: one generic browser mechanism without Onshape semantics.
- L2 `browser_transaction`: a composite generic browser flow with a terminal generic postcondition.
- L3 `onshape_interaction`: an Onshape-aware prepare/inspect/recovery interaction that does not claim a completed domain transaction.
- L4 `onshape_transaction`: one completed and verified Onshape domain mutation or complete domain observation.
- L5 `onshape_workflow`: multiple independent L4 operations composed into one non-deliverable goal.
- L6 `deliverable_recipe`: an independently consumable result with final acceptance, manifest, provenance, and a retry/resume boundary.

These levels are optional discovery conventions, not execution permissions. The
project runner is a separate control plane over one or more L6 deliverables. See
`BROWSER_SIX_LEVEL_SEMANTICS_AND_FDM_PLAN.md` for atomicity, same-level
composition, exposure, and migration rules.

Ordinary discovery omits L1 and L3 to reduce context cost. They remain documented
and are returned when the caller explicitly filters `semantic_level=L1` or
`semantic_level=L3`; no additional intent or permission parameter is required.
For ordinary stable operations, discovery ranks L5 workflows, L4 verified Onshape
transactions/observations, L2 generic browser transactions, then L6 deliverable
recipes. This reuses completed workflows first and reserves L6 for an explicitly
requested artifact/manifest boundary instead of decomposing candidates into
L3/L1 interactions.

## Implemented exposure architecture

The authoritative handler registry is never dynamically added to or removed
from. The current server keeps:

```text
TOOLS / HANDLERS
  -> one-build mcp_tool_catalog index (all tools)
  -> optional six-level TOOL_SEMANTICS
  -> semantic/profile/dynamic tools/list views
  -> browser_discover_tools + browser_invoke_discovered
```

`ONSHAPE_MCP_TOOL_EXPOSURE=semantic` is the fixed default. `static` exposes the
complete registry, `profile` fixes one startup profile, and `dynamic` owns one
view per connection and advertises listChanged. Direct known-name dispatch and
internal composition remain available in every mode, so exposure is not an
execution or permission gate.

The implemented catalog derives module, profile, network, mutating, dry-run,
confirmation, required-parameter, and browser semantic metadata from the final
registry. `mcp_tool_catalog search` is bounded to 8/12 compact summaries and
`describe` returns a schema only for one exact name. Richer intent/keyword metadata
remains an optional relevance extension, not a separate source of truth.

The universal catalog searches all registered tools independently of the current
view. An external caller uses compact search, exact describe, then normal
known-name invocation. Internal L5/L6 composition may use hidden lower-level
handlers but must still pass confirmation, budget, pacing, and verification gates.

### Historical gateway candidates

The original development record proposed four fixed entries named
`mcp_documentation`, `mcp_featurescript`, `mcp_rest_api`, and `mcp_browser`, with
an `overview | search | open | status | reset` action family. It also proposed a
candidate result limit of 8 with a hard cap of 12 and required clarification when
an L1-L6 semantic level was omitted instead of guessing a default.

The four broad module-entry names remain historical design inputs that are not accepted schemas or defaults.
The browser implementation instead exposes `browser_discover_tools` and
`browser_invoke_discovered`, uses default limit 8/hard cap 12, and allows an
ordinary no-level query that deliberately omits L1/L3. Exact L1/L3 discovery
requires only `semantic_levels`, with no intent or permission parameter.

The project control-plane contract is now partially implemented: legacy v1 flat
fixtures remain supported, while schema v2 accepts `setup` plus a dependency DAG
of one or more L6 deliverables. Each deliverable requires final assertions and
manifest outputs and receives an independent checkpoint/manifest record. This
does not make the runner itself L6. Semantic discovery/invocation, fixed profiles,
and connection-scoped dynamic replacement are implemented without changing the
complete handler registry.

## Compatibility modes

The plan must not assume every MCP client handles dynamic tool-list replacement.
Preserve explicit modes:

- `semantic` (implemented default): fixed bounded ordinary browser exposure plus
  discovery/invocation gateways.
- `static` (implemented): complete registry for debugging and compatibility.
- `profile` (implemented): fixed `ONSHAPE_MCP_TOOL_PROFILE` selected at connection startup.
- `dynamic` (implemented): per-connection `mcp_tool_view` state plus
  `notifications/tools/list_changed` after an effective set/reset.

The fixed gateway remains the compatibility baseline for clients that do not
refresh tool lists. Dynamic mode advertises `tools.listChanged=true`; semantic,
static, and profile modes advertise false. None of these views rejects a known-name
call or changes authority.

## Native modeling placement

The proposal keeps native modeling under `browser.native_modeling` while it
shares the browser session, Playwright input, pacing, confirmation, page objects,
selectors, recordings, and checkpoints. Re-evaluate it as a separate module only
if it gains an independent runtime, state/safety boundary, deployment lifecycle,
or implementation that no longer primarily depends on the browser layer.

## Phases

### Phase A: catalog metadata and baseline — implemented

- Derive normalized module/profile/safety/browser-semantic metadata from every
  tool after final registration and cost completion.
- Validate unique names, complete index coverage, network values, and stable
  fingerprinting.
- Expose `mcp_tool_catalog status/search/describe`: search defaults to 8 and caps
  at 12 compact schema-free results; exact describe is the only schema path.
- Use one immutable index across connections while computing current-view
  visibility per connection.

### Phase B: fixed exposure — implemented

- Filter exposure through deterministic profiles and optional browser semantic levels.
- Preserve the complete internal handler registry and known-name dispatch.
- Test every fixed profile and optional semantic-level filter.
- Demonstrate reduced initial schema size without changing safety gates.

### Phase C: connection-scoped dynamic exposure — implemented

- Added `mcp_tool_view` with status/set/reset and one view state per MCP connection.
- Implemented `tools.listChanged`, response-then-notification ordering, replacement,
  reset-to-startup-profile, and reconnect reset behavior.
- Kept unexposed known-name calls available by contract; display is guidance, not
  an execution constraint, while internal composition remains unchanged.
- Tested connection isolation, stdio wire behavior, fixed-client compatibility,
  and Windows bridge connection ownership.

### Phase D: browser native modeling

- Collect read-only toolbar/dialog/history-tree evidence first.
- Implement selected L4 Onshape transactions with dry-run, confirmation, failure stop, and history readback.
- Add an L5 part workflow and an L6 deliverable recipe with assertions, manifest, and checkpoint/resume.
- Exercise the separate project control plane with one and multiple L6 deliverables.
- Demonstrate that tool growth does not linearly grow ordinary context.

Concrete L4/L5 capability gaps identified by a real modeling round are tracked
in `BROWSER_MODELING_GAPS.md`: spiral/screw-on ridge generation, 3D-print
optimization transactions, and drawing auto-view insertion from a part's
context-menu "创建工程图".

## Completion criteria

This roadmap is implemented only when:

- the ordinary root view is bounded and resettable;
- candidate search is bounded and exact schemas are loaded on demand;
- module/capability ownership and optional semantic levels are validated;
- static/profile/dynamic/gateway compatibility boundaries are tested and documented;
- external exposure cannot bypass safety while internal composition still works;
- real REST remains disabled by default;
- native-modeling workflows verify readable feature history and geometry outcomes;
- current static mode remains available for compatibility and debugging.

The exposure/discovery completion criteria now pass. Phase D native-modeling work is
tracked separately and does not change the implemented display contract.

## Provenance

The full historical plan and completed development narrative are preserved under
`../history/legacy/DEV_DEVELOPMENT.md`. That archive is evidence of prior planning,
not a current contract.
