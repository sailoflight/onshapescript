# Verification matrix

## Defaults

- Default network: offline or mocked.
- Default production/cloud mutation: forbidden.
- Keep `LIVE_API_ENABLED` unset for all regression verification.
- Prefer local indexes, unit tests, mocks, fixtures, replay, and dry-run.
- Browser tools cost zero REST quota but a real UI action can still mutate cloud data.
- A successful click, request construction, or script exit is not sufficient evidence of domain success.

## Core commands

```bash
python3 -m unittest discover -s dev/tests -v
python3 -m py_compile mcp_main/*.py mcp_main/win/*.py mcp_main/win/mcp/*.py mcp_main/win/bridge/*.py mcp_main/wsl/*.py mcp_main/wsl/facade/*.py mcp_main/wsl/dsh/*.py onshape_browser_mode/*.py onshape_docs/query/*.py onshape_docs/scripts/*.py onshape_rest_api_mode/*.py examples/branch-cable-trophy/scripts/*.py
python3 mcp_main/wsl/dsh/build_runtime_prompt_companion.py --check
python3 onshape_docs/scripts/build_docs_index.py
python3 onshape_docs/verification/verify_docs.py
python3 onshape_docs/scripts/build_tool_reference.py --check
```

## Change matrix

| Change type or module | Fast check | Required tests/checks | Broader validation condition | External cost/risk |
|---|---|---|---|---|
| Project Markdown under indexed docs | Inspect links and page registration | Rebuild docs index; `verify_docs.py`; project-layout tests | Full offline suite if routing/ownership changes | 0 |
| Root `AGENTS.md` or governance routing | Governance package `check` | JSONL/marker/state checks plus project-layout tests | Cold-start routing exercise | 0 |
| `mcp_main` protocol/schema/dispatch/runtime prompt | `py_compile` target | `dev.tests.test_mcp_server`, `dev.tests.test_runtime_prompt`, companion `--check` | External-cwd client compatibility when initialization/prompt/client changes | 0 |
| DSH MCP client/companion configuration | Compose isolated profile | Generated companion test plus `MCP_CLIENT_COMPATIBILITY.md` external-cwd check | Operator deployment smoke after separately approved profile/Windows update | Offline model call; production restart/login impact |
| Browser tool registration/schema | `py_compile` target | `test_browser_plan_completion` and `test_mcp_server` | Windows smoke only when separately authorized | Offline 0; real UI may mutate cloud |
| Browser session/pages/selectors | `py_compile` target | `dev.tests.test_browser_mode` | Read-only inspect/watch before any new real selector workflow | Offline 0; real UI risk |
| Browser project/fixture/checkpoint | Fixture/static guards | `test_browser_plan_completion`, relevant browser tests | Approved sandbox/Windows scenario only after dry-run | Offline 0; real UI risk |
| REST client/budget/operations | `py_compile` target | `dev.tests.test_quota_guards` | Replay before any explicitly budgeted live fact | Live calls consume annual quota |
| REST config/path ownership | Project-layout test | `test_project_layout`, quota guards as applicable | None for path-only changes | 0 |
| FeatureScript authored source | `fs_local_check.py <path>` | Relevant example/static tests | Upload/live compile only through separately authorized workflow | Live upload consumes quota and mutates cloud |
| FeatureScript/reference query/index | Matching builder or query test | Project-layout/MCP tests plus docs verifier | Upstream refresh only when explicitly requested | Public fetch may use network; REST spec fetch costs quota |
| Windows/WSL relay/bridge scripts | `py_compile` for Python relay/body | `test_windows_bridge_scripts`, project-layout tests | Operator runbook smoke after approved deployment sync | Windows process impact |
| Generated tool reference | Run builder | Builder `--check` plus MCP protocol tests | None | 0 |
| Example parameters/scripts | Local parsing/static test | Matching example and MCP tests | No live validation by default | 0 offline |
| Secret/redaction/fixture changes | Static secret scan and fixture inspection | Quota/static/browser fixture tests | Never validate using real secret output | Credential exposure risk |

## Targeted commands

```bash
# MCP protocol, canonical runtime prompt, and registered local tools
python3 -m unittest dev.tests.test_mcp_server dev.tests.test_runtime_prompt -v
python3 mcp_main/wsl/dsh/build_runtime_prompt_companion.py --check

# REST live gates, request budgets, retry, and redaction
python3 -m unittest dev.tests.test_quota_guards -v

# Browser session/page behavior with mocks
python3 -m unittest dev.tests.test_browser_mode -v

# Browser tool schemas, workflows, dry-run, fixtures, and checkpoints
python3 -m unittest dev.tests.test_browser_plan_completion -v

# Module-owned paths and documentation routing
python3 -m unittest dev.tests.test_project_layout -v

# Windows bridge scripts
python3 -m unittest dev.tests.test_windows_bridge_scripts -v
```

## Documentation and generated references

After changing a page registered by `onshape_docs/scripts/build_docs_index.py`:

```bash
python3 onshape_docs/scripts/build_docs_index.py
python3 onshape_docs/verification/verify_docs.py
```

After changing tool schemas or handler registration:

```bash
python3 onshape_docs/scripts/build_tool_reference.py
python3 onshape_docs/scripts/build_tool_reference.py --check
python3 -m unittest dev.tests.test_mcp_server -v
```

Generated JSON indexes, `docs/generated/TOOL_REFERENCE.md`, and
`mcp_main/wsl/dsh/runtime-prompt-companion.js` are not hand-edited.

## Supported MCP clients

`MCP_CLIENT_COMPATIBILITY.md` is the authority for client delivery modes and
external-cwd evidence. Raw stdio and the Windows/WSL facade use native
`initialize.instructions`; DSH 0.1.0-rc.8 requires the generated companion.
A tools-only client installation fails compatibility even when calls succeed.

## Live REST verification gate

A live request is allowed only in a separately authorized task that states:

1. the single fact unavailable from docs, code, tests, fixture, replay, and dry-run;
2. `expected_live_requests` and a hard `max_live_requests` budget;
3. whether the request mutates data and how duplicate execution is prevented;
4. the fixture/evidence path that will permanently capture the redacted result;
5. stop behavior for 429, timeout, 5xx, or ambiguous mutation outcomes.

`LIVE_API_ENABLED` is never enabled merely to test the gate. Guard tests use
mocks. A 429 is never retried; mutating timeout/5xx outcomes are not retried.

## Real browser verification gate

Before a new real browser workflow:

1. pass the offline mock/fixture and dry-run path;
2. use read-only `browser_inspect`/`browser_watch` to verify selectors and frames;
3. state the exact cloud mutation and obtain explicit confirmation;
4. verify domain state, not only click completion;
5. preserve redacted evidence and stop on the first ambiguous result.

The Operator runbook covers deployment/process checks. Product evaluation and
cloud document mutation are not ordinary Development-plane regression tests.

## When verification cannot run

Report the exact skipped command, why it could not run, the remaining risk, and
the smallest approved next check. Never describe an unexecuted check as passed.
