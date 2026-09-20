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
| Browser schema/workflow | browser plan + MCP tests; `test_browser_apply_path` for the apply waits and the `featurePresent`/`featureComputed`/`parts` acceptance rule | authorized target-host scenario after dry-run |
| Browser session/selectors | browser-mode tests | read-only inspect/watch first |
| FS diagnostic loop (notice read, code normalization, capture) | `test_fs_diagnostics` + `test_fs_notice_collector` (node stub-DOM probe) | read-only notice-pane probe on the target host |
| REST/budget/operations | quota guards | explicitly budgeted live fact only |
| REST Feature List CRUD (add/update/delete/rollback/suppress/read) | `test_rest_feature_list` (spec-path agreement, spec-derived response parsing, `request.json` drift gate against the ids each fixture records, `LiveReplayTest` replaying the four server-confirmed bodies plus the recorded Feature List read, `LiveReplayTest` also covers `addPartStudioFeature`, and `RefusalShapeTest` pins the recorded 404 envelope and that an error body cannot parse as a success) | confirmed live 2026-09-19 (successes) and 2026-09-20 (read probe + one refusal); a re-confirmation is a separately authorized, budgeted fact |
| FeatureScript source | `onshape_docs/query/fs_check.py` + `test_static_guards`, the `fs_check_script` protocol test, and the corpus gate | authorized upload/live compile only |
| Local-check warn-then-confirm rule | `test_local_check_gate` (one argument name and one rule across the browser legs, the REST upload and the pipeline; warnings never ask) + the gate cases in `test_browser_mode` and `test_quota_guards` | nothing; a finding never blocks the write |
| FS validation boundary and checker locality | `test_fs_validation_strategy` (no network/process/third-party import in the checker or the diagnostic normalizer, survey links and non-adoption recorded, offline backlog separated from machine work) | nothing; the survey is search-level evidence, and a reused analyzer stays a detected candidate |
| Whole-feature capability contract | `test_capabilities` (bounded values, no implementation in a card, symbol gate against the vendored reference, local checker, precedent equality) | dry-run, then deploy/apply/acceptance on the target host |
| Capability discovery/retrieval (P4) | `test_capability_retrieval` (card-vs-reference cost, prose-query resolution, no dependency expansion, discovery wiring without widening exposure) + `dev/tools/context_cost.py` (three-route size benchmark with a documented token *estimate*; raw output in `onshape_docs/verification/context-cost-2026-09-19.json`) | a real tokenizer measurement; the only in-the-loop data point is the P6 live capability run |
| Tool surface (audit verdicts, merges, display views) | `test_tool_surface_audit` + `test_dynamic_tool_views` + `test_tool_catalog` (every row classified; no `Merge`/`Remove` left open; each absorbed name registered, default-hidden, reachable by exact name and still gated) | generated-reference and runtime-prompt `--check` |
| Generated references/indexes | builder and verifier `--check` | none by default |
| Secret/redaction/fixtures | static scan + fixture inspection | never validate using real secret output |

## Targeted commands

```bash
python3 -m unittest dev.tests.test_mcp_server dev.tests.test_runtime_prompt \
  dev.tests.test_project_layout dev.tests.test_mcp_probe_policy -v
python3 mcp_main/dsh/build_runtime_prompt_companion.py --check
python3 -m unittest dev.tests.test_quota_guards -v
python3 -m unittest dev.tests.test_browser_mode -v
python3 -m unittest dev.tests.test_browser_plan_completion dev.tests.test_local_check_gate -v
python3 -m unittest dev.tests.test_tool_surface_audit dev.tests.test_dynamic_tool_views \
  dev.tests.test_tool_catalog dev.tests.test_tool_reference -v
python3 -m unittest dev.tests.test_fs_diagnostics dev.tests.test_fs_notice_collector -v
python3 -m unittest dev.tests.test_rest_feature_list dev.tests.test_capabilities \
  dev.tests.test_capability_retrieval dev.tests.test_fs_validation_strategy -v
```

`test_fs_notice_collector` runs the production notice-collector string against a
stub DOM with `node`; it skips when node is not installed rather than reporting
the collector as covered.

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
