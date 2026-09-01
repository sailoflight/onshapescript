# Architecture overview

## Scope and current status

This repository implements an MCP server for offline Onshape FeatureScript and
REST documentation lookup, guarded REST validation, and Windows-hosted browser
automation. The complete registered tool/handler surface is static, while
`tools/list` supports fixed semantic/static/profile views and an opt-in dynamic
per-connection view. A one-build `mcp_tool_catalog` index covers the complete
registry independent of the current view; bounded search returns summaries and
exact describe is the only on-demand full-schema path. Fixed browser
discovery/invocation gateways reveal
default-hidden L1/L3 tools on explicit level queries; dynamic mode emits
`notifications/tools/list_changed` after `mcp_tool_view` changes. Exposure is a
context convention only: known-name dispatch and all safety gates remain unchanged.
The ordinary stdio MCP and canonical dual-production-role runtime prompt are
implemented. Native clients receive `initialize.instructions`; DSH 0.1.0-rc.8
requires the generated namespaced companion because its MCP client registers
tools but does not project those instructions. Cross-host transport is supplied
by an independently installed bridge and is not part of this repository.

Evidence status: `verified` by the module entrypoints, registration code, offline
tests, and path-ownership tests cited by the module contracts.

## Runtime topology

```text
MCP client or independently installed adapter
  -> ordinary stdio
  -> python -m mcp_main.win.mcp
  -> identity, runtime prompt, schemas, dispatch and handlers
       -> onshape_docs query/index layer (offline)
       -> onshape_rest_api_mode (guarded live REST boundary)
       -> onshape_browser_mode (host Playwright/Edge boundary)
```

The MCP process owns its browser resources, configured profile, local REST
state, and canonical runtime prompt at `mcp_main/win/mcp/runtime_prompt.py`. A
deployment that needs WSL-to-Windows transport registers this ordinary command
with an external bridge. The bridge owns registry, listeners, process
supervision, reconnect, and redacted peer metadata; no equivalent relay or
launcher is shipped here.

Each supported client adapter projects the trusted namespaced prompt before its
first model tool decision: native instructions where supported, otherwise the
generated companion under `mcp_main/dsh/`. Registering tool schemas alone is
insufficient. One browser profile must have one ordinary MCP process owner.

The retired project relay and the shared-bridge extraction acceptance record are
preserved under `../history/legacy/`; they are historical, non-executable, and
not current deployment authority.

## Modules

| Module | Owns | Does not own | Entrypoint | Contract |
|---|---|---|---|---|
| `mcp_main` | MCP protocol, identity/runtime prompt, tool schemas, dispatch, browser-tool installation, ordinary stdio entry, DSH companion | Domain reference data, REST transport policy, browser page behavior, cross-host transport | `mcp_main/win/mcp/__main__.py`, `mcp_main.win.mcp.server.py` | `../modules/mcp-main.md` |
| `onshape_docs` | Authored domain docs, vendored reference, offline indexes, query APIs, doc verification | Credentials, live REST state, browser session | `onshape_docs/query/`, `onshape_docs/scripts/` | `../modules/onshape-docs.md` |
| `onshape_rest_api_mode` | REST request building/transport, quota and live gates, stable target state, REST outputs | MCP wire protocol, browser UI session, authored reference | `onshape_rest_api_mode/operations.py` | `../modules/rest-api-mode.md` |
| `onshape_browser_mode` | Browser configuration, persistent session, page objects, selectors, browser workflows and checkpoints | REST quota accounting, MCP wire protocol, upstream documentation | `onshape_browser_mode/session.py`, `mcp_main/win/mcp/browser_tools.py` | `../modules/browser-mode.md` |
| `examples/branch-cable-trophy` | Example FeatureScript, parameter sets, validation contract and workflow scripts | Shared runtime configuration or general MCP behavior | Example README and scripts | Existing example documentation |
| `dev` | Executable tests, probes, captures, fixtures, and development helpers | Project documentation and runtime imports | `dev/tests/`, `dev/tools/` | `../development/LAB.md` |

## Dependency direction

```text
MCP protocol/dispatch
  -> domain query or operation handlers
  -> module-owned adapters, state, reference, fixtures, and platform resources
```

Browser semantic layering is:

```text
project control (outside L1-L6)
  -> L6 independently consumable deliverable recipes
  -> L5 multi-transaction workflows
  -> L4 complete verified Onshape transactions or observations
  -> L3 Onshape-aware incomplete interactions
  -> L2 generic browser transactions
  -> L1 browser primitives with no Onshape semantics
  -> selectors and page/frame primitives
```

Rules:

- Higher semantic levels may compose lower levels; same-level composition is
  allowed when acyclic and contained within one contract.
- Selectors and frame-resolution logic stay in browser selectors/page objects, not high-level tools.
- `mcp_main` may compose module handlers but does not take ownership of module state.
- `onshape_browser_mode` may explicitly synchronize observed IDs through the REST-owned state boundary; it must not silently take ownership of quota or credentials.
- `onshape_docs/reference/raw/` is build input and provenance, not a normal query dependency.
- Cross-host transport and supervision stay outside the business MCP and must preserve byte-transparent MCP semantics.

## Data and configuration ownership

| Data/configuration | Owner | Lifecycle | Safety boundary |
|---|---|---|---|
| Browser defaults and local state | `onshape_browser_mode/config/` | Committed defaults plus ignored local/runtime state | No credentials in committed files |
| Persistent browser profile/checkpoints | `onshape_browser_mode/user_data/` | Windows persistent runtime | Single process owner; ignored |
| REST target state | `onshape_rest_api_mode/config/onshape-state.json` | Stable committed metadata | IDs are operational; redact when sharing |
| REST credentials/quota ledger | `onshape_rest_api_mode/config/` | Ignored secret/runtime state | Never return secrets; live gate required |
| REST outputs | `onshape_rest_api_mode/outputs/` | Generated runtime output | Module-owned lifecycle |
| Project-doc and reference indexes | `onshape_docs/` | Generated from authored or vendored sources | Rebuild and verify; do not hand-edit |
| Example parameters | `examples/branch-cable-trophy/config/` | Committed example input | Example-owned |
| MCP/browser logs | module-owned ignored output/log paths | MCP host runtime | Diagnostics never enter MCP stdout |
| Test fixtures and captures | `dev/` | Committed or ignored by evidence type | Redact secrets and production data |

## Current invariants

- Real REST access is disabled unless `LIVE_API_ENABLED` is explicitly enabled.
- Development and regression tests run offline and never enable the live gate.
- Mutating tools require explicit confirmation; supported writes expose dry-run where documented.
- MCP stdout contains JSON-RPC only; diagnostics go to stderr or module-owned logs.
- MCP initialization supplies an actionable, bounded dual-production-role prompt; it is not a product introduction or copied tool list.
- Production role guidance must reach supported clients in external cwd/chat environments without repository `AGENTS.md`.
- Tool/schema/handler and runtime-prompt revisions cannot silently diverge across deploy, reconnect, or rollback.
- A persistent browser profile has one ordinary MCP process owner.
- Reconnect persistence, when required, is an external supervisor contract and must not create a second profile owner.
- Current code and offline tests take precedence over prose when behavior conflicts.
- Generated indexes and the tool reference must be rebuilt from their authoritative sources.

## Current tool surface

The registered tool schemas and handlers in `mcp_main` are authoritative. The
derived summary is `../generated/TOOL_REFERENCE.md`; semantic, static, fixed
profile, and per-connection dynamic views are implemented as context-routing
conventions and do not change known-name dispatch authority.

## Decisions and history

- Retired project relay and accepted shared-bridge extraction record: `../history/legacy/SHARED_BRIDGE_MIGRATION.md`.
- Development-history migration and current-authority map: `../history/TRACEABILITY.md`.
- Reusable verified behavior: `../../onshape_docs/experience/`.

## Unknowns

- External bridge compatibility is deployment state verified by that bridge's
  own protocol, registry, lifecycle, and client tests; this repository verifies
  only the ordinary MCP contract and its DSH adapter example.
- Supported-client runtime-prompt delivery modes and current evidence are
  versioned in `../verification/MCP_CLIENT_COMPATIBILITY.md`; an individual
  production profile may lag the repository generation until an Operator deploys
  and verifies it.
