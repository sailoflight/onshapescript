# `mcp_main` module contract

Status: verified

## Owns

- MCP server identity, protocol initialization, canonical dual-production-role runtime prompt, JSON-RPC dispatch, tool schema registration, and handler routing.
- Installation of browser tool schemas/handlers into the complete registry.
- The full stdio MCP body and the Windows/WSL bridge facade/engine boundary.
- MCP result formatting and the rule that protocol stdout contains JSON-RPC only.

## Does not own

- FeatureScript, REST API, or project documentation content and indexes: `onshape_docs`.
- REST credentials, quota policy, target state, transport, and outputs: `onshape_rest_api_mode`.
- Browser session, page objects, selectors, and UI workflow state: `onshape_browser_mode`.
- Tests, probes, and capture fixtures: `dev/`.

## Entrypoints

| Kind | Path or symbol | Purpose |
|---|---|---|
| Runtime (Win MCP body) | `mcp_main/win/mcp/__main__.py` | Full stdio MCP body entry |
| Runtime prompt authority | `mcp_main/win/mcp/runtime_prompt.py` | Canonical revisioned User/Operator policy returned by initialize |
| Server identity | `mcp_main/win/mcp/identity.py` | `SERVER_NAME`/`SERVER_VERSION`/`PROTOCOL_VERSION` |
| DSH companion generator | `mcp_main/wsl/dsh/build_runtime_prompt_companion.py` | Generates the namespaced prompt plugin for DSH clients without native instructions projection |
| Registry/dispatch | `mcp_main/win/mcp/server.py` | Server identity, tool schemas, `TOOLS`, `HANDLERS`, dispatch, and serve loop |
| Browser registration | `mcp_main/win/mcp/browser_tools.py` | Browser tool schemas, handler adapters, and installation |
| WSL facade (relay) | `mcp_main/wsl/facade/mcp_tcp_bridge.py` | stdio-to-loopback TCP relay |
| Windows engine (bridge) | `mcp_main/win/bridge/bridge_server.py` | Persistent in-process MCP dispatch and browser ownership |
| WSL bridge control | `mcp_main/wsl/wsl_bridge_ctl.sh` | WSL-side start/restart/status trigger for the Windows bridge |
| DSH plugin wiring | `mcp_main/wsl/dsh/cordis.patch.yml.example` | Two-entry DSH profile patch (MCP client + runtime-prompt companion) |
| Generic bridge contract | `mcp_main/bridge/ARCHITECTURE.md` | Windows/WSL invariants |
| Protocol tests | `dev/tests/test_mcp_server.py` | Initialization, tool list, local calls, result and secret boundaries |
| Bridge tests | `dev/tests/test_windows_bridge_scripts.py` | Windows deployment script contracts |

## Contracts and invariants

- Tool names are unique and every externally callable registered schema has a handler.
- Browser tools are installed into the complete MCP registry through `mcp_main.win.mcp.browser_tools`.
- The protocol version, server identity, runtime production-role prompt, tool schema, and handler dispatch are defined by current code, not prose tool counts.
- The prompt contains actionable `Production / User` and `Production / Operator` routing/boundaries, not an MCP introduction, and is returned through initialization independently of repository instructions.
- Raw/relay clients use native instructions. DSH 0.1.0-rc.8 uses the generated namespaced companion; a tools-only DSH installation is unsupported.
- Prompt/schema/handler deployment and rollback use one server generation; the companion revision derives from `SERVER_VERSION`.
- Tool results never expose REST credential values.
- stdout contains JSON-RPC messages only; diagnostics use stderr or bridge logs.
- The WSL facade remains stdlib-only and does not own browser state or tool business logic.
- The Windows engine holds persistent browser resources across client reconnects.
- Current `tools/list` is static; dynamic/profile/gateway exposure is roadmap work.

## Dependencies

- Allowed: query APIs from `onshape_docs`, guarded operations from `onshape_rest_api_mode`, and browser handler installation from `mcp_main.win.mcp.browser_tools`/`onshape_browser_mode`.
- Forbidden: moving module-owned runtime state or credentials into `mcp_main`; importing Windows browser dependencies into the WSL relay; bypassing module safety gates in wrapper handlers.

## Data, configuration, and generated files

| Item | Owner | Behavior | Source of truth |
|---|---|---|---|
| Runtime production-role prompt | `mcp_main/win/mcp/runtime_prompt.py` plus `mcp_main/win/mcp/identity.py` | Returned by initialize; revisioned with deployed server behavior | Edit canonical source, then regenerate and test |
| DSH prompt companion | Generated `mcp_main/wsl/dsh/runtime-prompt-companion.js` | Contributes one namespaced system-prompt section | `python3 mcp_main/wsl/dsh/build_runtime_prompt_companion.py` |
| Tool schemas | `mcp_main/win/mcp/server.py`, `mcp_main/win/mcp/browser_tools.py` | Registered at import/startup | `TOOLS` and browser tool definitions |
| Tool handlers | Same modules | Dispatch by exact registered name | `HANDLERS` and browser handler map |
| Bridge log | `mcp_main/win/bridge/logs/bridge-server.log` | Windows runtime diagnostics | `bridge_server.LOG_PATH` |
| Generated tool reference | `docs/generated/TOOL_REFERENCE.md` | Rebuilt offline | Registered schemas and handlers |

## Verification

| Change | Required verification |
|---|---|
| Initialization identity, prompt, tool schema, handler, dispatch, or result formatting | `python3 -m unittest dev.tests.test_mcp_server dev.tests.test_runtime_prompt -v`; companion `--check`; external-client evidence when prompt/client changes |
| Browser tool registration | `python3 -m unittest dev.tests.test_browser_plan_completion dev.tests.test_mcp_server -v` |
| WSL/Windows bridge | `python3 -m unittest dev.tests.test_windows_bridge_scripts dev.tests.test_project_layout -v` |
| Any Python change | Matching tests plus the `py_compile` command in `docs/verification/MATRIX.md` |
| Tool surface change | Rebuild and verify `docs/generated/TOOL_REFERENCE.md` |

All commands run with `LIVE_API_ENABLED` unset.

## Documentation triggers

- Public tool/schema or runtime production-role prompt changes update the MCP User contract, Operator boundary where relevant, generated tool reference, and supported-client compatibility evidence.
- Bridge transport, process ownership, or restart changes update architecture and the Operator runbook.
- Registry ownership or dependency changes update this contract and the architecture overview.
- Future dynamic exposure work stays in the roadmap until implemented and tested.

## Unknowns

- Compatibility of future dynamic `tools/list_changed` behavior across MCP clients is not established by the current static implementation.
- Current DSH support depends on the generated companion because the pinned MCP
  client does not natively project instructions; re-evaluate and remove the
  companion only after a future client proves native model visibility.
