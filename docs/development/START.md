# Development start

This is the repository-wide development entry. The `dev/` directory itself is
reserved for tests, probes, fixtures, capture scripts, and other executable
development material; its directory map is documented in `LAB.md`.

## Prerequisites and platform boundary

- Python 3 is required for the MCP server, offline indexes, tests, and WSL relay.
- WSL/Linux is the development repository and offline-test environment.
- The WSL relay `mcp_main/wsl/facade/mcp_tcp_bridge.py` is stdlib-only.
- The persistent MCP body, Playwright, Edge, credentials, and browser profile run
  in the Windows deployment copy.
- Do not install Playwright into the WSL relay environment.
- Keep `LIVE_API_ENABLED` unset for development and regression verification.

## Entrypoints

| Purpose | Entrypoint | Boundary |
|---|---|---|
| Full stdio MCP body | `python3 -m mcp_main.win.mcp` | Windows runtime entry; browser tools need the Windows session |
| WSL MCP facade | `python3 mcp_main/wsl/facade/mcp_tcp_bridge.py 8766` | Thin stdio-to-loopback relay; no tool implementation |
| Windows persistent body | `python mcp_main/win/bridge/bridge_server.py` | Owns MCP dispatch and persistent browser resources |
| Offline test suite | `python3 -m unittest discover -s dev/tests -v` | Must run with `LIVE_API_ENABLED` unset |
| Python syntax check | `python3 -m py_compile mcp_main/*.py mcp_main/win/*.py mcp_main/win/mcp/*.py mcp_main/win/bridge/*.py mcp_main/wsl/*.py mcp_main/wsl/facade/*.py mcp_main/wsl/dsh/*.py onshape_browser_mode/*.py onshape_docs/query/*.py onshape_docs/scripts/*.py onshape_rest_api_mode/*.py examples/branch-cable-trophy/scripts/*.py` | Offline |
| Project-doc index | `python3 onshape_docs/scripts/build_docs_index.py` | Rebuild after changing indexed authored docs |
| Project-doc verification | `python3 onshape_docs/verification/verify_docs.py` | Offline integrity check |
| FeatureScript local guard | `python3 onshape_docs/scripts/fs_local_check.py <file-or-directory>` | Run before any upload; zero API calls |
| Generated tool reference | `python3 onshape_docs/scripts/build_tool_reference.py` | Derived from the registered MCP schemas |
| DSH runtime-prompt companion | `python3 mcp_main/wsl/dsh/build_runtime_prompt_companion.py` | Derived from `mcp_main/win/mcp/runtime_prompt.py`; check with `--check` |

There is no root packaging or build-system manifest. Python modules and the
Windows browser dependency file are the current executable sources of truth.

## Development workflow

1. Start at `../INDEX.md` and select one task route.
2. Read one matching module contract under `../modules/`.
3. Search for the exact implementation and its tests; do not read the whole module by default.
4. Form a short task card covering goal, scope, non-goals, evidence, risk, and verification.
5. Keep real REST and cloud mutations disabled unless a separately authorized production task requires them.
6. Run the matching row in `../verification/MATRIX.md`.
7. Rebuild derived references, prompt companions, and indexes when their authored sources change.
8. Check whether the change affects usage, operations, architecture, module contracts, client compatibility, or verified experience.

## Configuration and data ownership

| Item | Owner | Committed | Rule |
|---|---|---|---|
| Browser defaults | `onshape_browser_mode/config/browser.toml` | Yes | Browser module owns browser behavior |
| Browser local overrides/state | `onshape_browser_mode/config/` | No where ignored | Never move into repository root |
| Persistent browser profile | `onshape_browser_mode/user_data/` | No | Windows runtime resource |
| REST target state | `onshape_rest_api_mode/config/onshape-state.json` | Yes | REST module owns stable target metadata |
| REST credentials and quota ledger | `onshape_rest_api_mode/config/` | No where secret/runtime | Never expose values in prompts, fixtures, or logs |
| REST generated outputs | `onshape_rest_api_mode/outputs/` | Runtime | REST module owns output lifecycle |
| Example parameter sets | `examples/branch-cable-trophy/config/` | Yes | The example owns its model inputs |
| Bridge logs | `mcp_main/win/bridge/logs/` | Runtime | Windows MCP body owns them |
| Tests/probes/fixtures | `dev/` | Mixed | See `LAB.md`; no project documentation is owned there |
| Authored domain docs | `onshape_docs/` and `docs/` | Yes | Rebuild `onshape_docs/index.json` after indexed changes |

## Existing development material

- `LAB.md` maps the executable contents under `dev/`.
- `../architecture/OVERVIEW.md` records current cross-module architecture.
- `../roadmap/DYNAMIC_TOOL_DISCOVERY.md` records unimplemented tool-exposure plans.
- `../roadmap/BROWSER_MODELING_GAPS.md` records concrete browser modeling capability gaps by semantic level.
- `../roadmap/BROWSER_FS_SEMANTIC_TOOLS.md` records the four-level FS-mode semantic tool surface focused on the **FS script mode** (deploy/compile-status/symbols/parameter-edit) plus its Part-Studio coupling points (part context-menu drawing auto-views), and improvement suggestions for existing browser tools (live-browser evidence 2026-08-25). Native feature-mode transactions are explicitly out of scope there.
- `../roadmap/BROWSER_GENERIC_L2_SEMANTICS.md` records the app-generic L2 semantics of the document shell (top navbar, left panel + icon rail, bottom tab bar, viewport chrome), the regions that do not change with Studio type, with live screenshot + DOM evidence (2026-08-25).
- `../roadmap/BROWSER_PLANNED_TOOLS.md` is the deduped single-source registry of every planned-but-not-implemented browser tool (FS script mode, drawing, print, app-generic shell), consolidating the above roadmaps and `BROWSER_MODELING_GAPS.md` so the same tool is not restated.
- `../history/TRACEABILITY.md` maps every preserved development record to its current authority.
- `../history/legacy/DEV_DEVELOPMENT.md` preserves the former mixed browser/MCP development record as historical evidence.
- `../../onshape_docs/experience/` owns reusable verified behavior.
- `../../onshape_docs/verification/` owns supporting evidence.

## Common failures

| Symptom | Cheapest check | Exact detail |
|---|---|---|
| WSL relay cannot connect | Confirm the Windows bridge process and loopback port `8766` | `../operations/MCP_RUNBOOK.md` |
| Browser tools fail on WSL | Confirm only the relay is running on WSL | `../../mcp_main/bridge/README.md` |
| A REST operation is blocked | Keep it blocked during development; inspect the local quota guard and state | `../verification/MATRIX.md` and REST module contract |
| Project docs report stale | Rebuild the project-doc index, then run its verifier | `../../onshape_docs/README.md` |
| Browser selector or workflow is uncertain | Search indexed browser experience before source or live UI work | `../../onshape_docs/experience/browser-automation.md` |

## Documentation triggers

- Public tool/schema behavior: update the User contract and regenerate the tool reference.
- Canonical runtime prompt or client adapter: regenerate the DSH companion and update client compatibility evidence plus User/Operator boundaries.
- Module ownership or dependency direction: update architecture and the affected module contract.
- Windows/WSL deployment, configuration, or recovery: update the Operator runbook.
- Reusable verified behavior: update `onshape_docs/experience/` and link evidence.
- New or moved development log: classify its durable items and update
  `../history/TRACEABILITY.md`; the archive must not become a competing current contract.
- Future work only: update the roadmap, never current architecture.
