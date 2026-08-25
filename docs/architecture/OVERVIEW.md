# Architecture overview

## Scope and current status

This repository implements an MCP server for offline Onshape FeatureScript and
REST documentation lookup, guarded REST validation, and Windows-hosted browser
automation. The current implementation exposes a static registered tool surface;
dynamic tool discovery described in the roadmap is not implemented behavior.
The Windows/WSL tool bridge and canonical dual-production-role runtime prompt
are implemented. Raw stdio clients and the WSL facade receive native
`initialize.instructions`; DSH 0.1.0-rc.8 requires the generated namespaced
companion because its MCP client registers tools but does not project those
instructions. The companion has external-cwd model-visible evidence; whether a
particular production DSH profile has deployed that companion remains Operator
runtime state, not inferred repository behavior.

Evidence status: `verified` by the module entrypoints, registration code, offline
tests, and path-ownership tests cited by the module contracts.

## Runtime topology

```text
MCP client in WSL/Linux
  -> client adapter (tools + trusted runtime-prompt projection)
  -> mcp_main/wsl/facade/mcp_tcp_bridge.py (stdio <-> loopback TCP, stdlib only)
  -> Windows mcp_main/win/bridge/bridge_server.py (persistent MCP body)
  -> mcp_main.win.mcp.server initialization, dual-production-role prompt, dispatch and handlers
       -> onshape_docs query/index layer (offline)
       -> onshape_rest_api_mode (guarded live REST boundary)
       -> onshape_browser_mode (Windows Playwright/Edge boundary)
```

The Windows body owns persistent browser resources, credentials, and the
canonical runtime prompt in `mcp_main/win/mcp/runtime_prompt.py` for
`Production / User` and `Production / Operator`. The WSL facade forwards the
complete MCP initialization result without rewriting that prompt. Each
supported client adapter projects the trusted, namespaced prompt before its
first model tool decision: native instructions where supported, otherwise the
generated companion under `mcp_main/wsl/dsh/`. Registering tool schemas alone
is insufficient. Reconnecting the WSL facade must not destroy Windows state or
accumulate prompt generations. The full `python3 -m mcp_main.win.mcp` stdio entry exists
for the MCP body and protocol tests; it is not the WSL browser runtime entry.

The generic bridge contract and project mapping are in
`../../mcp_main/bridge/ARCHITECTURE.md`.

## Modules

| Module | Owns | Does not own | Entrypoint | Contract |
|---|---|---|---|---|
| `mcp_main` | MCP protocol, tool schemas, dispatch, browser-tool installation, WSL/Windows bridge | Domain reference data, REST transport policy, browser page behavior | `mcp_main/win/mcp/__main__.py`, `mcp_main.win.mcp.server.py` | `../modules/mcp-main.md` |
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
project fixtures (L4)
  -> workflows (L3)
  -> transaction operations (L2)
  -> generic browser actions (L1)
  -> selectors and page/frame primitives
```

Rules:

- Higher browser semantic levels may call lower levels; lower levels do not call higher levels.
- Selectors and frame-resolution logic stay in browser selectors/page objects, not high-level tools.
- `mcp_main` may compose module handlers but does not take ownership of module state.
- `onshape_browser_mode` may explicitly synchronize observed IDs through the REST-owned state boundary; it must not silently take ownership of quota or credentials.
- `onshape_docs/reference/raw/` is build input and provenance, not a normal query dependency.
- The WSL relay must remain stdlib-only and must not import Windows browser dependencies.

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
| Bridge logs | `mcp_main/win/bridge/logs/` | Windows runtime | Diagnostics never enter MCP stdout |
| Test fixtures and captures | `dev/` | Committed or ignored by evidence type | Redact secrets and production data |

## Current invariants

- Real REST access is disabled unless `LIVE_API_ENABLED` is explicitly enabled.
- Development and regression tests run offline and never enable the live gate.
- Mutating tools require explicit confirmation; supported writes expose dry-run where documented.
- MCP stdout contains JSON-RPC only; diagnostics go to stderr or the bridge log.
- MCP initialization supplies an actionable, bounded dual-production-role prompt; it is not a product introduction or copied tool list.
- Production role guidance must reach supported clients in external cwd/chat environments without repository `AGENTS.md`.
- Tool/schema/handler and runtime-prompt revisions cannot silently diverge across deploy, reconnect, or rollback.
- A persistent browser profile has one Windows process owner.
- Closing or reconnecting the WSL client does not own or destroy the Windows browser session.
- Current code and offline tests take precedence over prose when behavior conflicts.
- Generated indexes and the tool reference must be rebuilt from their authoritative sources.

## Current static tool surface

The registered tool schemas and handlers in `mcp_main` are authoritative. The
derived summary is `../generated/TOOL_REFERENCE.md`. The planned bounded dynamic
exposure architecture is explicitly future work in
`../roadmap/DYNAMIC_TOOL_DISCOVERY.md`.

## Decisions and history

- Generic Windows/WSL bridge architecture: `../../mcp_main/bridge/ARCHITECTURE.md`.
- Development-history migration and current-authority map: `../history/TRACEABILITY.md`.
- Reusable verified behavior: `../../onshape_docs/experience/`.

## Unknowns

- Dynamic/profile/gateway tool exposure remains unimplemented and must not be
  inferred from the current static registry.
- MCP client compatibility for future dynamic `tools/list_changed` behavior
  requires an explicit compatibility matrix before implementation.
- Supported-client runtime-prompt delivery modes and current evidence are
  versioned in `../verification/MCP_CLIENT_COMPATIBILITY.md`; an individual
  production profile may still lag that repository generation until an Operator
  deploys and verifies it.
