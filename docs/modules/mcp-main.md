# `mcp_main` module contract

Status: verified

## Owns

- MCP identity, initialization, canonical runtime prompt, JSON-RPC dispatch,
  tool schemas/handlers, browser-tool installation, and result formatting.
- The complete ordinary stdio entry `python -m mcp_main.win.mcp`.
- Generated DSH runtime-policy companion and external-adapter configuration example.
- Protocol-clean stdout and bounded diagnostics on stderr.

## Does not own

- FeatureScript/REST/project documentation content and indexes: `onshape_docs`.
- REST credentials, quota policy, state, transport, outputs: `onshape_rest_api_mode`.
- Browser session, selectors, page/workflow state: `onshape_browser_mode`.
- Cross-host relay, registry, listeners, supervision, reconnect, or scheduled tasks:
  independently installed bridge infrastructure.
- Tests/probes/fixtures: `dev/`.

## Entrypoints

| Kind | Path or symbol | Purpose |
|---|---|---|
| Ordinary MCP | `mcp_main/win/mcp/__main__.py` | complete stdio server |
| Identity | `mcp_main/win/mcp/identity.py` | name/version/protocol |
| Runtime prompt | `mcp_main/win/mcp/runtime_prompt.py` | canonical User/Operator policy |
| Registry/dispatch | `mcp_main/win/mcp/server.py` | schemas, handlers, serve loop |
| Browser registration | `mcp_main/win/mcp/browser_tools.py` | browser schema/handler adapters |
| DSH generator | `mcp_main/dsh/build_runtime_prompt_companion.py` | namespaced prompt plugin |
| DSH example | `mcp_main/dsh/cordis.patch.yml.example` | external registered-bridge client + companion |
| Protocol tests | `dev/tests/test_mcp_server.py` | initialize/list/local calls and guards |
| Stdio probe | `dev/tools/mcp_probe.py` | identity/prompt/list/status/idle/EOF |

## Contracts

- Tool names are unique and each externally callable schema has a handler.
- Known-name dispatch authority and safety gates do not change with tool views.
- Runtime prompt, server identity, schema, handler, and DSH companion deploy as one revisioned generation.
- Native clients consume `initialize.instructions`; DSH 0.1.0-rc.8 requires the generated companion.
- Tool results never expose REST credential values.
- Browser dependencies are host-local and the configured profile has one MCP process owner.
- This repository contains no `mcp_main/wsl`, `mcp_main/win/bridge`, or
  `mcp_main/bridge` runtime tree. Reintroducing them is an architecture change.
- An external bridge may launch the ordinary command, but its command registry,
  listener ports, process lifecycle, and peer metadata remain external contracts.

## Verification

Run with `LIVE_API_ENABLED` unset:

```bash
python3 -m unittest dev.tests.test_mcp_server dev.tests.test_runtime_prompt \
  dev.tests.test_project_layout dev.tests.test_mcp_probe_policy -v
python3 mcp_main/dsh/build_runtime_prompt_companion.py --check
python3 dev/tools/mcp_probe.py
```

Current client compatibility is `../verification/MCP_CLIENT_COMPATIBILITY.md`.
Retired relay rationale is mapped by `../history/TRACEABILITY.md` and is not
current runtime authority.
