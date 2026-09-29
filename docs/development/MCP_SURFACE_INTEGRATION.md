# `mcp_surface` shared-library integration

## Dependency and provenance

`mcp_main/win/mcp/tool_views.py` and `mcp_main/win/mcp/tool_catalog.py` no longer
implement the tool-surface mechanism. View selection, the six-level filter, the
absorbed-compatibility rule, the gateway curated set, the connection-scoped
collapse/expand state machine and the bounded-catalog engine are
`lijq-mcp-surface==0.1.0.dev3` (import name `mcp_surface`, Python >=3.11). The
original artifact is
`/home/lijq/code/pythonpubliclib/dist/lijq_mcp_surface-0.1.0.dev3-py3-none-any.whl`.
An unchanged copy ships in `onshape_browser_mode/wheels/`; the sibling
`pythonpubliclib` checkout is neither needed at runtime nor added to Python.

SHA-256: `81116952455cca78a507760625100af97aa798ce65c4997cda019f9ee858f732`
(41437 bytes). The superseded dev2 artifact (40335 bytes,
`1ea972f0a539a4487f170047e28d7a2012c3de863abce5b1aaa3d150f8784c45`) remains in
the library's `dist/` but is no longer bundled here.

## Default exposure mode: `semantic` (dev3)

`mcp_surface` dev3 changed exactly one behaviour: `resolve_exposure`'s default
mode moved from `gateway` to `semantic`, and this repo's own fallback in
`tool_views.exposure_mode` moved with it. The reason is client capability, not
taste: a collapsed `dynamic` start makes a client's useful surface depend on it
understanding a mutable `tools/list` **and** handling
`notifications/tools/list_changed`. That is a capability, and not every MCP
client has it. The compressed `gateway` view is a different trade: it is fixed
too, but its curated set is a project decision rather than a neutral starting
point. `semantic` is a fixed list that is always expanded, so a no-config
connection is correct on every client:

- default (no argument, no `ONSHAPE_MCP_TOOL_EXPOSURE`, no
  `tool_views.local.toml`): `semantic`, 77 tools, `state=expanded`,
  `switchingAvailable=false`, `listChangedCapability=false`, no notification on
  the startup path.
- `gateway` (25 tools) and `dynamic` (cold start collapsed on the three control
  tools) remain fully selectable explicitly, by argument, environment variable or
  host-local file, with unchanged semantics. `dynamic`'s unqualified `expand`
  still opens the remembered `gateway` set.
- In any fixed mode `expandedView` is the remembered, inert expand target (the
  status pairs it with `switchingAvailable=false`); it does not describe the
  fixed list. That field's behaviour is unchanged from dev2.

Precedence is unchanged: explicit argument, then `ONSHAPE_MCP_TOOL_EXPOSURE`,
then `mcp_main/win/mcp/config/tool_views.local.toml [exposure].mode`, then
`semantic`.

The wheel includes `mcp_surface/docs/ADAPTATION_GUIDE.md`, is zero-dependency, and
imports nothing (no file, environment, socket or MCP SDK) as a side effect. The
Windows requirements file pins the version and resolves `./wheels` relative to
that file.

## What is shared and what stays here

Shared (the mechanism, in one place):

- `Surface` + `SurfacePolicy`: profile membership, absorbed-name hiding, default
  exposure versus an explicit level query, always-visible names, the gateway core
  and curated order, declaration validation, `fingerprint`, `chain_violations`.
- `ToolViewState`: the `static`/`semantic`/`profile`/`gateway`/`dynamic` display
  sets and the collapse/expand/`set`/`reset` state machine, including the
  `changed` flag that gates `notifications/tools/list_changed`.
- `ToolRecord`: semantic level, default exposure, absorbed flag, confirmation
  classification from the tool's own JSON Schema, search tokens.
- `ToolCatalog`: name resolution and the unknown-name path for `describe`, plus
  the search/index caps.

Kept here (this project's facts, deliberately not library facts):

- The deployment switch: host-local `mcp_main/win/mcp/config/tool_views.local.toml`,
  `ONSHAPE_MCP_TOOL_EXPOSURE`/`ONSHAPE_MCP_TOOL_PROFILE`, explicit arguments and
  their precedence. A library that read a config file would own a deployment fact.
- The Onshape vocabulary: profile names and membership rules, the curated gateway
  list, the browser semantic records, the absorbed wrapper set and the
  `status()` shape (`gateway.core` order, profile table, reason string).
- The catalog's public contract: module taxonomy, network classification,
  mutation/concurrency rendering, the argument filters, offset paging,
  capability cards and the result key names, all layered on the shared surface.
- The three control tools' schemas and handlers stay in `server.py`; the library
  is used as the registry/selection engine beneath them, not as the transport.

### Library gap (reported, not worked around by editing the library)

The library's `ToolCatalog` cannot back this project's `mcp_tool_catalog`
contract as-is: it has no `modules`/`profiles`/`semantic_levels`/`network`/
`mutating`/`visible_only` filters, no offset paging, and it emits different result
keys (`count`/`matched` versus `totalMatches`/`returnedCount`) and no capability
cards. Replacing the rendering would change a documented, tested User contract.
So `tool_catalog.py` builds its records on the shared `Surface`/`ToolRecord`,
delegates `describe` name resolution to `ToolCatalog`, and keeps a thin
project-owned rendering/validation layer. The surface-cost tools confirm the
observable catalog output is byte-identical after the change.

## Deliberate differences from the pre-integration implementation

- **Control tools survive an explicit level filter.** This was already this
  project's behaviour (the level filter only ever applied to `browser_*` names);
  the shared library states the invariant once instead of it emerging from a
  prefix check. No observable change.
- **`chain_violations` is a report, not an exception.** The three prescribed
  two-step lookups are now declared on the policy, so a half-listed chain is
  reportable through `Surface.chain_violations`/`audit` rather than being
  invisible. The shipped gateway already lists both ends of each chain; the
  gateway test continues to pin that. No runtime change.
- **The confirmation override lives on the record.** The
  `onshape_eval_featurescript` → `budget_override` special case moved from a
  hardcoded name check in `tool_catalog._confirmation_mode` onto its
  `ToolRecord.confirmation_override`. The reported mode is identical.
- **Status and error text are unchanged.** View-argument rejection messages and
  the fixed-mode switch refusal are still this project's; the catalog fingerprint
  is unchanged (verified against the pre-change algorithm); `mcp_tool_catalog`
  output is unchanged.

## Offline verification

```bash
# Install the bundled wheel into the development environment (no network):
.venv/bin/python -m pip install --no-index --no-deps \
  onshape_browser_mode/wheels/lijq_mcp_surface-0.1.0.dev3-py3-none-any.whl

# Full offline suite (browser_common comes from the ignored PYTHONPATH target):
env -u LIVE_API_ENABLED PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=temp/browser-common-site \
  .venv/bin/python -m unittest discover -s dev/tests -v

# Surface-cost evidence (sizes must not move silently):
.venv/bin/python dev/tools/lookup_depth.py
.venv/bin/python dev/tools/context_cost.py
```

Verified (dev3 round): **1118 tests**, `OK`, exit 0 — the pre-change baseline on
the dev2/gateway-default tree (commit
`9d1b4a6b526a95cf1ec5bbbaff2187fa7126190b`) ran **1115 tests**, `OK`, exit 0, and
the three added default-mode tests are the difference;
`test_tool_gateway_view`,
`test_dynamic_tool_views`, `test_tool_catalog` and `test_tool_surface_audit` all
green. `lookup_depth.py` and `context_cost.py` are **byte-identical** to the
pre-change output: both tools ask for explicit modes (`gateway`/`semantic`/
`static`/`dynamic`) and construct states directly, so the default-mode change
does not move their numbers. The same sizes are therefore reused here, and the
registry itself is unchanged (gateway 69,953 chars / 17,488 estimated tokens;
semantic 166,193 / 41,548; static 223,495 / 55,873).

Added criteria for the default change (all offline, no host involved):

- a no-config `tools/list` is exactly the explicit `semantic` listing (same 77
  names, same order) — `test_the_no_config_list_matches_the_explicit_semantic_mode`;
- a no-config connection initializes with `tools.listChanged=false`, emits no
  `notifications/tools/list_changed` on initialize/`tools/list`, and a refused
  `mcp_tool_view` call adds none — `test_a_no_config_start_emits_no_list_changed`;
- explicit `gateway` (25 names) and `dynamic` (collapsed 3, expand → gateway +
  one notification) still behave as before —
  `test_explicit_gateway_and_dynamic_remain_selectable`;
- the pre-existing default assertion assumed `gateway`; it was changed to
  `semantic` (not deleted or weakened) in `test_dynamic_tool_views.py`,
  `test_tool_gateway_view.py` and `test_mcp_server.py`.

Cost consequence, stated plainly: adopting the `semantic` default raises the
default advertised surface from the compressed `gateway` start (17,488 estimated
tokens) to the semantic set (41,548 estimated tokens), a 2.4x larger table. That
is the deliberate trade for a default that needs no client notification
capability; `gateway` remains one explicit setting away, and the numbers above
are advertised tool-table sizes, not end-to-end task cost.

The browser-optional-dependency harness in `test_browser_common_integration.py`
puts the required `mcp_surface` location on the child's `PYTHONPATH` while still
blocking `browser_common`/`playwright` by name; its assertions are unchanged. The
isolated install is used only for offline tests; no Windows deployment, browser
launch, REST request or host restart is implied.

## Backup and rollback

The dev3 integration touched only tracked source and documentation in this
checkout plus the bundled wheel. `git status` was clean before it at commit
`9d1b4a6b526a95cf1ec5bbbaff2187fa7126190b`, so `git checkout -- <file>` on the
changed paths (and restoring the bundled dev2 wheel) is a complete rollback.
Runtime profile, local configuration, REST state and the deployed Windows copy
were not modified.

A host rollback is a dependency-generation rollback: restore
`onshape_browser_mode/requirements-windows.txt`, `tool_views.py` and the bundled
`mcp_surface` wheel together, then reinstall from the wheels directory. A
deployment that deliberately wants the old compressed start sets
`ONSHAPE_MCP_TOOL_EXPOSURE=gateway` (or the host-local file) explicitly. Do not
remove the bundled wheel while any retained revision imports `mcp_surface`.
