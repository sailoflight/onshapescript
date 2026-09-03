# Development start

This is the repository-wide development entry. `dev/` contains executable tests,
probes, fixtures, and capture material; its directory map is `LAB.md`.

## Platform boundary

- Python 3 is required for the ordinary MCP, offline indexes, tests, and tools.
- Run `python3 -m mcp_main.win.mcp` on the host that owns configured browser and
  local REST state.
- Install Windows browser dependencies from
  `onshape_browser_mode/requirements-windows.txt`; use the machine's existing
  Chrome/Edge rather than installing a browser into a WSL-only client.
- Cross-host transport belongs to an independently installed bridge. Do not add
  relay/listener/launcher code or fixed bridge ports to this repository.
- Keep `LIVE_API_ENABLED` unset for development and regression verification.

## Entrypoints

| Purpose | Entrypoint | Boundary |
|---|---|---|
| Ordinary stdio MCP | `python3 -m mcp_main.win.mcp` | complete protocol/tool body |
| Offline stdio probe | `python3 dev/tools/mcp_probe.py` | initialize/list/status only |
| Offline tests | `python3 -m unittest discover -s dev/tests -v` | no live REST/cloud mutation |
| Syntax | `python3 -m py_compile mcp_main/*.py mcp_main/dsh/*.py mcp_main/win/*.py mcp_main/win/mcp/*.py onshape_browser_mode/*.py onshape_docs/query/*.py onshape_docs/scripts/*.py onshape_rest_api_mode/*.py examples/branch-cable-trophy/scripts/*.py` | offline |
| Docs index | `python3 onshape_docs/scripts/build_docs_index.py` | rebuild after indexed docs change |
| Docs verification | `python3 onshape_docs/verification/verify_docs.py` | offline |
| FeatureScript local guard | `python3 onshape_docs/scripts/fs_local_check.py <path>` | zero API calls |
| Tool reference | `python3 onshape_docs/scripts/build_tool_reference.py --check` | derived schema check |
| DSH companion | `python3 mcp_main/dsh/build_runtime_prompt_companion.py --check` | generated policy adapter |

There is no root packaging manifest. Python modules, domain-owned dependency
files, and current module contracts are executable sources of truth.

## Workflow

1. Start at `../INDEX.md` and select one task route.
2. Read one matching module contract and the exact implementation/tests.
3. State goal, scope, non-goals, evidence, risk, and verification.
4. Keep real REST and browser/cloud mutations disabled unless separately authorized.
5. Run the matching row in `../verification/MATRIX.md`.
6. Rebuild derived prompt companions, references, and indexes when authored sources change.
7. Update usage, operations, architecture, module, compatibility, and history routing when ownership changes.

## Configuration and data ownership

| Item | Owner | Rule |
|---|---|---|
| Browser defaults/local state/profile | `onshape_browser_mode/` | ignored state/profile stay on MCP host |
| Browser dependency manifest | `onshape_browser_mode/requirements-windows.txt` | tracked |
| REST state/credentials/quota/output | `onshape_rest_api_mode/` | never expose secret values |
| Canonical runtime prompt | `mcp_main/win/mcp/runtime_prompt.py` | returned by initialize |
| DSH companion | `mcp_main/dsh/` | generated; deploy with same server revision |
| External bridge registry/listeners | external bridge project | not owned or tested here |
| Tests/probes/fixtures | `dev/` | executable development material only |

## Existing development material

- `LAB.md` maps `dev/`.
- `../architecture/OVERVIEW.md` records current architecture.
- `../roadmap/FS_HYBRID_COMPILER_INTEGRATION.md` owns the proposed FS-first compiler-fork integration, safety corrections, phases, and acceptance gates.
- `../roadmap/` owns future and completed-design records without overriding code.
- `../history/TRACEABILITY.md` maps preserved history to current authority.
- `../../onshape_docs/experience/` and `verification/` own reusable behavior and evidence.

## Common failures

| Symptom | First check | Authority |
|---|---|---|
| initialize/tools fail | ordinary stdio probe and MCP tests | `mcp-main` contract |
| browser unavailable | host dependency/config/profile owner | Operator runbook |
| external client cannot connect | external bridge registry/node health | bridge runbook |
| policy missing in DSH | companion revision and profile entry | client compatibility |
| live REST refusal | environment/quota/state guards | REST module contract |

## Documentation triggers

- Public schema/behavior: update User contract and generated reference.
- Runtime prompt/client adapter: regenerate companion and update compatibility evidence.
- Module ownership: update architecture and module contract.
- Deployment/recovery: update Operator runbook.
- Moved history: update `../history/TRACEABILITY.md`; archive never wins over current authority.
