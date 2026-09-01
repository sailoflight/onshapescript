# Verification matrix

## Defaults

- Default network: offline or mocked.
- Default production/cloud mutation: forbidden.
- Keep `LIVE_API_ENABLED` unset for regression verification.
- Prefer local indexes, unit tests, mocks, fixtures, replay, and dry-run.
- Browser tools cost zero REST quota but real UI actions can mutate cloud data.
- Click completion, request construction, or process exit alone is not domain success.

## Core commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s dev/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile mcp_main/*.py mcp_main/dsh/*.py mcp_main/win/*.py mcp_main/win/mcp/*.py onshape_browser_mode/*.py onshape_docs/query/*.py onshape_docs/scripts/*.py onshape_rest_api_mode/*.py examples/branch-cable-trophy/scripts/*.py
PYTHONDONTWRITEBYTECODE=1 python3 mcp_main/dsh/build_runtime_prompt_companion.py --check
python3 onshape_docs/scripts/build_docs_index.py
python3 onshape_docs/verification/verify_docs.py
python3 onshape_docs/scripts/build_tool_reference.py --check
```

## Change matrix

| Change | Required offline evidence | Broader condition |
|---|---|---|
| Indexed docs/routing | rebuild index, verify docs, project-layout tests | full suite for ownership changes |
| MCP protocol/schema/runtime prompt | MCP, runtime-prompt, probe-policy tests; companion `--check` | external-cwd client compatibility |
| Ordinary stdio entry | MCP + project-layout + probe-policy tests; target-host probe | one profile owner |
| DSH companion/example | generator `--check`, runtime tests, static external-adapter guard | model-visible policy smoke |
| External bridge registration | this repo's example only | bridge project's protocol/registry/lifecycle suite |
| Browser schema/workflow | browser plan + MCP tests | authorized target-host scenario after dry-run |
| Browser session/selectors | browser-mode tests | read-only inspect/watch first |
| REST/budget/operations | quota guards | explicitly budgeted live fact only |
| FeatureScript source | `fs_local_check.py` + matching static tests | authorized upload/live compile only |
| Generated references/indexes | builder and verifier `--check` | none by default |
| Secret/redaction/fixtures | static scan + fixture inspection | never validate using real secret output |

## Targeted commands

```bash
python3 -m unittest dev.tests.test_mcp_server dev.tests.test_runtime_prompt \
  dev.tests.test_project_layout dev.tests.test_mcp_probe_policy -v
python3 mcp_main/dsh/build_runtime_prompt_companion.py --check
python3 -m unittest dev.tests.test_quota_guards -v
python3 -m unittest dev.tests.test_browser_mode -v
python3 -m unittest dev.tests.test_browser_plan_completion -v
```

Generated JSON indexes, `docs/generated/TOOL_REFERENCE.md`, and
`mcp_main/dsh/runtime-prompt-companion.js` are not hand-edited.

## Negative relay guard

Outside `docs/history/legacy/` and dated evaluation evidence, current source and
docs must not restore or route to `mcp_main/wsl`, `mcp_main/win/bridge`,
`mcp_main/bridge`, `bridge_server.py`, project relay/launcher scripts, or port
8766. Cross-host verification belongs to the independently installed bridge.

## Client compatibility

`MCP_CLIENT_COMPATIBILITY.md` owns delivery modes/evidence. Native clients consume
`initialize.instructions`; DSH 0.1.0-rc.8 requires the generated companion. A
tools-only client installation fails compatibility even when tool calls work.

## Live gates

A live REST request requires a separately authorized fact, request budget,
mutation/duplicate analysis, redacted evidence path, and stop conditions. Never
retry 429 or ambiguous mutations.

A real browser workflow first passes mock/fixture/dry-run, verifies selectors
read-only, states exact cloud mutation, obtains confirmation, verifies domain
state, preserves redacted evidence, and stops on ambiguity.

Record exact commands, scope, environment, results, and skipped evidence. Never
claim an unexecuted or external check passed.
