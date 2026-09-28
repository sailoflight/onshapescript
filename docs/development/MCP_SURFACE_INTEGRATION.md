# `mcp_surface` shared-library integration

## Dependency and provenance

`mcp_main/win/mcp/tool_views.py` and `mcp_main/win/mcp/tool_catalog.py` no longer
implement the tool-surface mechanism. View selection, the six-level filter, the
absorbed-compatibility rule, the gateway curated set, the connection-scoped
collapse/expand state machine and the bounded-catalog engine are
`lijq-mcp-surface==0.1.0.dev2` (import name `mcp_surface`, Python >=3.11). The
original artifact is
`/home/lijq/code/pythonpubliclib/dist/lijq_mcp_surface-0.1.0.dev2-py3-none-any.whl`.
An unchanged copy ships in `onshape_browser_mode/wheels/`; the sibling
`pythonpubliclib` checkout is neither needed at runtime nor added to Python.

SHA-256: `1ea972f0a539a4487f170047e28d7a2012c3de863abce5b1aaa3d150f8784c45`.

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
  onshape_browser_mode/wheels/lijq_mcp_surface-0.1.0.dev2-py3-none-any.whl

# Full offline suite (browser_common comes from the ignored PYTHONPATH target):
env -u LIVE_API_ENABLED PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=temp/browser-common-site \
  .venv/bin/python -m unittest discover -s dev/tests -v

# Surface-cost evidence (sizes must not move silently):
.venv/bin/python dev/tools/lookup_depth.py
.venv/bin/python dev/tools/context_cost.py
```

Verified: **1115 tests**, `OK`, exit 0 (same count as the pre-change baseline);
`test_tool_gateway_view`, `test_dynamic_tool_views`, `test_tool_catalog` and
`test_tool_surface_audit` all green; `lookup_depth.py` and `context_cost.py`
produce the same surface sizes as before the change (gateway 69,953 chars /
17,488 estimated tokens; semantic 166,193 / 41,548; static 223,495 / 55,873). The
browser-optional-dependency harness in `test_browser_common_integration.py` now
puts the required `mcp_surface` location on the child's `PYTHONPATH` while still
blocking `browser_common`/`playwright` by name; its assertions are unchanged. The
isolated install is used only for offline tests; no Windows deployment, browser
launch, REST request or host restart is implied.

## Backup and rollback

The integration touched only tracked source and documentation in this checkout.
`git status` was clean before the change at commit
`174187b2452178b3457cff7b5fee11d30993ab79`, so `git checkout -- <file>` on the
changed paths (plus deleting the two added files and the bundled wheel) is a
complete rollback. Runtime profile, local configuration, REST state and the
deployed Windows copy were not modified.

A host rollback is a dependency-generation rollback: restore
`onshape_browser_mode/requirements-windows.txt` and the matching
`tool_views.py`/`tool_catalog.py` together, then reinstall from the wheels
directory. Do not remove the bundled wheel while any retained revision imports
`mcp_surface`.
