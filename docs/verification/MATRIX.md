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
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s dev/tests -v
PYTHONDONTWRITEBYTECODE=1 python -m py_compile mcp_main/*.py mcp_main/dsh/*.py mcp_main/win/*.py mcp_main/win/mcp/*.py onshape_browser_mode/*.py onshape_docs/query/*.py onshape_docs/scripts/*.py onshape_rest_api_mode/*.py examples/branch-cable-trophy/scripts/*.py
PYTHONDONTWRITEBYTECODE=1 python mcp_main/dsh/build_runtime_prompt_companion.py --check
python onshape_docs/scripts/build_docs_index.py
python onshape_docs/verification/verify_docs.py
python onshape_docs/scripts/build_tool_reference.py --check
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
| FeatureScript source | `onshape_docs/query/fs_check.py` + `test_static_guards` (incl. the WARNING-level `opBoolean` `targetsAndToolsNeedGrouping` rule and its vendored-library false-positive gate), the `fs_check_script` protocol test, and the corpus gate | authorized upload/live compile only |
| FeatureScript reference miss | `test_reference_miss` + `test_fs_reference_suggestions` (a miss raises `ReferenceMiss` with `suggestions`/`nextCall` in `error.data`; `fs_search` still returns its normal list) | nothing; `fs_search`/module disambiguation remains the recovery |
| Windows/consumer portability | `test_probe_portability` (portable bounded pipe reader, `sys.executable`, `failureClass` classification) + `test_consumer_release` (whitelist/denylist invariants) | target-host probe on the deployment host |
| Local-check warn-then-confirm rule | `test_local_check_gate` (one argument name and one rule across the browser legs, the REST upload and the pipeline; warnings never ask) + the gate cases in `test_browser_mode` and `test_quota_guards` | nothing; a finding never blocks the write |
| FS validation boundary and checker locality | `test_fs_validation_strategy` (no network/process/third-party import in the checker or the diagnostic normalizer, survey links and non-adoption recorded, offline backlog separated from machine work) | nothing; the survey is search-level evidence, and a reused analyzer stays a detected candidate |
| Whole-feature capability contract | `test_capabilities` (bounded values, no implementation in a card, symbol gate against the vendored reference, local checker, precedent equality) | dry-run, then deploy/apply/acceptance on the target host |
| Capability discovery/retrieval (P4) | `test_capability_retrieval` (card-vs-reference cost, prose-query resolution, no dependency expansion, discovery wiring without widening exposure) + `dev/tools/context_cost.py` (three-route size benchmark with a documented token *estimate*; raw output in `onshape_docs/verification/context-cost-2026-09-19.json`) | a real tokenizer measurement; the only in-the-loop data point is the P6 live capability run |
| Tool surface (audit verdicts, merges, display views) | `test_tool_surface_audit` + `test_dynamic_tool_views` + `test_tool_gateway_view` + `test_tool_catalog` (every row classified; no `Merge`/`Remove` left open; each absorbed name registered, default-hidden, reachable by exact name and still gated; `gateway` is this project's declared default — a fixed, always-expanded curated page needing no client notification capability — with `exposure_mode()` and `SurfacePolicy.default_exposure` pinned to one constant by a drift test, and `semantic`/`dynamic` explicit with unchanged collapse/expand) + the pinned `mcp_surface` wheel 0.1.0.dev4 (`MCP_SURFACE_INTEGRATION.md`: `SurfacePolicy.default_exposure` added) | generated-reference and runtime-prompt `--check` |
| Tool description split (narrative out of `tools/list`) | `test_tool_description_split` (every tool's `describe` equals the complete pre-split text; every asserted phrase is still in the advertised payload; **no parameter name, peer tool, config knob, `action='...'` value, backticked value or uppercase negation leaves the advertised text**; the routing context is derived from the schemas and the registry, not a hand-kept list; the rule is deterministic and only shrinks; the fingerprint is equal across construction sites; `authorityChanged=false`) + the unchanged `assertIn(..., tool["description"])` tripwires in `test_browser_mode`, `test_mcp_server` and `test_reference_miss`, which keep reading `server.TOOLS` | generated-reference `--check` (33 first-180-character rows changed, so the reference and the project-doc index were regenerated); `RUNTIME_PROMPT` reads no description, so the DSH companion and its revision are unaffected |
| Generated references/indexes | builder and verifier `--check`; `test_docs_index_digests` pins every recorded page digest | index digests are content-level and newline-normalized via `onshape_docs/query/source_digest.py`, shared by builders and checkers, and `.gitattributes` pins `eol=lf` so a Windows checkout cannot renormalize the tree |
| REST document variables (read/write) | `test_rest_variables` (spec-derived paths and enums, one-GET read, element refusal when the cache is ambiguous, POST sent once, readback comparison, registration metadata, live gate) | `onshapescript_set_variables` live acceptance is still pending; the shapes are spec-derived, not live captures |
| Interference check, geometry leg | `test_rest_interference` (argv derivation from the configured geometry template and its refusal paths; the verdict map with an injected runner: `clean` only for boolean + parsed + zero interfering, `candidates_only` for every `aabb` run, `indeterminate` for converter failure / timeout / missing or unreadable report / a truncated candidate list with no finding, `unavailable` when no command can be assembled; argument validation and caps; the converter is importable and `--help`-able without CadQuery; the geometry-config fallback -- the primary config wins, a browser-mode config serves instead when this mode's is disabled, and two unusable configs report both reasons with the primary's own reason surviving) plus the four `LiveCadQuery` cases, which run the real converter and skip with a stated reason when no interpreter can import CadQuery | the same call through the deployed host (Windows -> `wsl.exe` -> the pinned CadQuery venv): `onshape_docs/verification/interference-live-acceptance-2026-10-03.json` records the deployed plan, the real-launcher run on both fixtures (24.0 mm^3 intersection -> `interference`; box overlap with zero volume -> `clean`) and the one host-state defect that stops a fully deployed run, so a live redeploy is a re-run, not a re-investigation; no Onshape REST call may be introduced by it |
| Interference check, browser leg | `test_browser_interference` (50 stub-page tests: the four verdicts; the two never-fake-clean invariants, namely a missing panel and a 0-row read with no completion proof; zero-volume-touch inclusion/exclusion; `part_names` filtering; bounded waits that terminate without an advancing clock; selector-miss diagnostics carrying the active tab name) | `onshape_docs/verification/pending-live-verification-2026-10-03.json` T1-T5: the DOM selectors are `UNVERIFIED`, so nothing live may be claimed until that ledger is answered |
| STEP import, REST leg | `test_rest_step_import` (every field the planner would send -- and every field it declares deliberately unsent -- must exist in the vendored `BTBTranslationRequestParams` schema, and the INTERNAL list must match the schema's own visibility block, so the plan cannot invent a request field; the binary `file` part leads the multipart parts and the text parts equal the body; identifiers, enums, filename shape and bounds are refused; credentials never appear; the local source digest is reported with `sha256Stable: false`; `dry_run=False` returns `multipart_transport_unavailable` while a fake client proves zero `request()` calls) | no live call has been made for this leg: the import body is `multipart/form-data`, while `onshape_rest_api_mode.client` sends JSON only, so the live path refuses instead of pretending. The tool is deliberately not registered yet -- see the import section of `roadmap/THREE_PLANE_GEOMETRY_INTEROP.md` |
| EWF project instance (`ewf/`) | `test_ewf_instance` (deliverables-only layout, no private `x-*` keys, generator `--check` freshness, README version projection, OQ hits declared in the instance, queue/narrative id agreement, execution node count) | the two external EWF validators run when their read-only repositories are present and skip otherwise; live nothing |
| Secret/redaction/fixtures | static scan + fixture inspection | never validate using real secret output |

## Targeted commands

```bash
python -m unittest dev.tests.test_mcp_server dev.tests.test_runtime_prompt \
  dev.tests.test_project_layout dev.tests.test_mcp_probe_policy -v
python mcp_main/dsh/build_runtime_prompt_companion.py --check
python -m unittest dev.tests.test_quota_guards -v
python -m unittest dev.tests.test_browser_mode -v
python -m unittest dev.tests.test_browser_plan_completion dev.tests.test_local_check_gate -v
python -m unittest dev.tests.test_tool_surface_audit dev.tests.test_dynamic_tool_views \
  dev.tests.test_tool_catalog dev.tests.test_tool_reference -v
python -m unittest dev.tests.test_fs_diagnostics dev.tests.test_fs_notice_collector -v
python -m unittest dev.tests.test_rest_feature_list dev.tests.test_capabilities \
  dev.tests.test_capability_retrieval dev.tests.test_fs_validation_strategy -v
python -m unittest dev.tests.test_rest_variables -v
python -m unittest dev.tests.test_ewf_instance -v
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
