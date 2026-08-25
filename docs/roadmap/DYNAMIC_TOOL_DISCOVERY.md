# Dynamic MCP tool discovery roadmap

Status: proposed, not implemented

This roadmap distills the unimplemented work from the archived browser/MCP
development plan. Current behavior remains the static registered tool surface
described by `../architecture/OVERVIEW.md` and generated from `mcp_main`.

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
- `semantic_level`: optional L1-L4 discovery metadata, not a registration or permission gate.

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

- L1: generic observation/input/wait primitives.
- L2: one verified user-intent transaction.
- L3: a workflow composed from L2 transactions.
- L4: fixture-driven projects with assertions, checkpoints, and resume.

## Proposed exposure architecture

Do not dynamically add/remove the authoritative handler registry. Keep:

```text
ALL_TOOLS / HANDLERS
  -> TOOL_CATALOG
  -> connection-scoped EXPOSURE_VIEW
```

Proposed catalog metadata includes:

```text
name, module, submodule?, effectiveSubmodule, semanticLevel?, intent, keywords,
risk, confirmationRequired, dryRun, dependencies, schemaRef
```

A future external caller may invoke fixed module entries or tools in its current
exposure view. Internal L3/L4 composition may use hidden lower-level handlers but
must still pass confirmation, budget, pacing, and verification gates.

### Historical gateway candidates

The original development record proposed four fixed entries named
`mcp_documentation`, `mcp_featurescript`, `mcp_rest_api`, and `mcp_browser`, with
an `overview | search | open | status | reset` action family. It also proposed a
candidate result limit of 8 with a hard cap of 12 and required clarification when
an L1-L4 semantic level was omitted instead of guessing a default.

These values are preserved design inputs, not accepted schemas or defaults. A
future implementation must revalidate names, bounds, client compatibility,
runtime-prompt delivery, risk metadata, and confirmation behavior before any of
them becomes public contract.

## Compatibility modes

The plan must not assume every MCP client handles dynamic tool-list replacement.
Evaluate and preserve explicit modes:

- `profile`: fixed module/capability selected at startup.
- `dynamic`: bounded exposure plus `notifications/tools/list_changed`.
- `gateway`: fixed module entries describe/execute long-tail tools.
- `static`: full current registry for debugging and compatibility.

Recommended implementation order remains profile, then dynamic, then a gateway
fallback based on client evidence.

## Native modeling placement

The proposal keeps native modeling under `browser.native_modeling` while it
shares the browser session, Playwright input, pacing, confirmation, page objects,
selectors, recordings, and checkpoints. Re-evaluate it as a separate module only
if it gains an independent runtime, state/safety boundary, deployment lifecycle,
or implementation that no longer primarily depends on the browser layer.

## Phases

### Phase A: catalog metadata and baseline

- Add module, intent, and risk metadata for every current tool.
- Add capability/submodule metadata where required; keep semantic level optional.
- Validate unique names, resolvable schema references, and allowed dependencies.
- Record current `tools/list` count, JSON size, and estimated tokens.
- Add bounded catalog search/describe without returning all schemas.

### Phase B: fixed profiles

- Filter exposure by `module[:submodule][:level]`.
- Preserve the complete internal handler registry.
- Test every module/browser capability and optional semantic-level filter.
- Demonstrate reduced initial schema size without changing safety gates.

### Phase C: dynamic exposure

- Add fixed module entries and a connection-scoped exposure view.
- Implement `tools.listChanged`, notifications, replacement, reset, and reconnect behavior.
- Reject external calls to unexposed tools without breaking internal composition.
- Test concurrent isolation, Windows bridge persistence, and supported MCP clients.

### Phase D: browser native modeling

- Collect read-only toolbar/dialog/history-tree evidence first.
- Implement selected L2 feature transactions with dry-run, confirmation, failure stop, and history readback.
- Add an L3 part workflow and L4 project with assertions and checkpoint/resume.
- Demonstrate that tool growth does not linearly grow ordinary context.

Concrete L2/L3 capability gaps identified by a real modeling round are tracked
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

Until these conditions pass, project documentation must continue describing the
current static registry rather than this roadmap as implemented behavior.

## Provenance

The full historical plan and completed development narrative are preserved under
`../history/legacy/DEV_DEVELOPMENT.md`. That archive is evidence of prior planning,
not a current contract.
