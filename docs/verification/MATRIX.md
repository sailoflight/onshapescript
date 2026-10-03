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
| Expression-resolve wait (deterministic facts, not clocks) | `test_browser_apply_path` `DialogFieldResolveWaitTest`: the wait publishes `reads` (how many dialog reads it took) because `elapsedMs` is a real-clock measurement and three tests asserting `elapsedMs == 0` flaked under load (measured: `1 != 0`, twice, full suite only). The settle-it-on-the-first-read tests assert `reads == 1` and only BOUND the clock; the refusal-without-a-read path asserts `reads == 0` AND `elapsedMs == 0`, which is literal there |
| Tolerances derived from the reader spread (third-party referee) | `interop-join-vs-cadq-2026-10-03.md` §4: MeshQ's independent `fsum` recomputation puts this repository at 9.8e-13 area / 1.08e-12 volume / 0.0 bounds (70/70 bitwise), CadQ's volume at 2.41e-06 and MeshQ's own area at 3.39e-06; `equivalence_tolerance` + `equivalence_tolerance_basis` + `readings_basis` in `step_tessellation.py`, pinned by `test_each_tolerance_carries_the_measurement_that_derived_it`; the 70-piece set signature stays `7f427106…` |
| "An empty probe is a phenomenon, not evidence" (peer-found, third instance) | Contract §8 section + practice 17: a `grep` truncated by `head` against a guessed path returned empty for a file that exists, and empty read as non-existence. Family now has three internal instances recorded with their measurements: the virtualised Part Studio feature read publishing `headerCount`/`ready`/`rowsComplete` (`mcp_main/win/mcp/server.py:3388`), the import leg's `before_read_failed` refusing rather than judging landing against an empty row list (`dev/tests/test_browser_step_import.py::test_a_failed_before_read_refuses_before_touching_the_page`, which asserts nothing was clicked), and `_solid_count` returning `grade: "unknown"` + reason instead of 0 on an unreadable artifact |
| Handoff checker closes its exit code | `dev/tools/check_handoff.py` (maintained tool) + `dev/tests/test_check_handoff_tool.py` (8 subprocess tests): runs `check_print_basis` and `check_identity_against` over a peer's manifest and **exits 1 on any refusal, 2 when the input cannot be read**; real 70-piece handoff → 0 with "no consumer readings supplied → not_provided rather than agreement"; threshold 181 → 141 refusals, deleted `orientation` → 70, stripped vintage → 1, caller printing elsewhere → rule 5, missing file → 2 |
| Threshold range + "failures must close" (adversarial round 3) | `check_print_basis` refuses a threshold outside `0 < threshold_deg <= 180` at both levels (`0`/`181`/`1e9`/`-45`/`180.5`/`inf` refused, `0.001`/`45`/`90`/`180` accepted, real 70-piece manifest still 0 refusals); contract §8 records the peer's `run`-exit-0-while-`verdicts`-say-fail measurement, the general rule (one judgement, every entry point), practice 16, and this repository's self-audit (the docs-index digest checked by two entry points but implemented once — both failed together on one stale digest) |
| Import addresses by digest, resolves by path | `onshape_browser_mode/step_import.py` + `dev/tests/test_browser_step_import.py` (23 tests): `expect_sha256` / `handoff_manifest` (reads `declaration.identity.sha256` or `artifact.sha256`), mismatch refused in the OFFLINE plan before any click, a handoff that cannot name its bytes refused by name, and `addressedBy`/`expectedSha256`/`matchesExpected` recorded even when no digest was declared; live ledger check I6 |
| Type-level hardening (adversarial round 2) + tolerance vintage | `dev/tests/test_print_basis.py` (13 tests): rule 2 demands a *literally* true winding verdict (`applicable: 0`/`"false"`/`1`/`[]` refused; honest `false` gets the vacuously-consistent reason), raw direction/threshold values validated before conversion (`["0","0","1"]`, `[0,0,True]`, `[0,0,inf]`, `[0,0,NaN]`, `[0,0]` refused) — real 70-piece manifest still 0 refusals, `applicable: 0` against it gives 70; `equivalence_tolerance_vintage` (readers/date/witness/re-derive) required and echoed by `check_identity_against` |
| Consumer-side identity check (the import leg's gate) | `fdm_analysis/conversion/identity_check.py` + `dev/tests/test_identity_check.py` (8 tests): units mismatch refused before any comparison, tolerance read from the manifest with its `equivalence_tolerance_basis` required, `identity_rule.version` mismatch returns `not_comparable`, per-piece maximum plus worst piece index, bounds compared only inside the declared `bounds_family`; against the real 70-piece handoff it compares 70/70 with 0 outside, and a 0.1 % volume shift is caught on all 70 with the worst piece named |
| Absent-field hardening of the print-basis guard (adversarial review) | `dev/tests/test_print_basis.py`: MeshQ's ten variants as tests — `test_the_field_is_absent_paths_are_as_loud_as_the_false_ones` (the four silent passes: deleted `orientation`, `applicable: null`, silent `unknown`, null reference points) and `test_the_ten_adversarial_variants_have_the_outcomes_meshq_measured` (six blocked, A accepted); the real 70-piece manifest still passes with 0 refusals, variant D against it gives 70 refusals; contract rule 18 |
| Print-fit refusals implemented (the consumer's "no") | `fdm_analysis/conversion/print_basis.py` `check_print_basis()` + `dev/tests/test_print_basis.py` (7 tests): print-fit §4 rules 1–5 enforced from the consumer side; run against the real 70-piece manifest it accepts with 0 refusals, and refuses a caller printing in `[0, 1, 0]` with rule 5; it returns readings, never a verdict |
| Print basis emitted by the producer (injection point 2, implemented) | `fdm_analysis/conversion/step_tessellation.py` `_print_block()` + `parts[].mesh.at`; pinned by `test_no_direction_derived_reading_lacks_its_direction` and `test_the_print_block_names_the_owner_of_the_gate_it_does_not_own`; regenerated 70-piece manifest keeps its readings and `set_signature_sha256` `7f427106…` unchanged, and the byte join still reads 70/70 identical with exact volumes 70/70 |
| Print-fit split and its injection points | `docs/roadmap/PRINT_FIT_INTERFACE_DRAFT.md`: what each plane can measure today (path by path), the producer / measuring-plane / consumer split, the `print` + `readings` shape, six refusal rules, the three injection points, and the open questions; the shared evidence vocabulary is MeshQ's `grade_tiers`, adopted verbatim in `StlGeometryAnalyzer` as `gradeTiers` (`test_stl_geometry`) |
| Does the handoff need a router? | `docs/roadmap/THREE_PLANE_HANDOFF_SCHEMA_DRAFT.md` §9: no router, from this repository's own paid precedent (`browser_invoke_discovered` demoted for adding "a hop and no capability" while `mcp_tool_invoke` was kept for buying one), plus the three conditions that would justify one and the field-by-field schema ownership table |
| Cross-plane collaboration practice | `docs/roadmap/THREE_PLANE_HANDOFF_SCHEMA_DRAFT.md` §10: thirteen practices, each with its incident (three levels of independence and why both sides record `independent_kernel: false`; per-piece max over aggregate; family/algorithm per field; the state a reading was taken in; the bytes as referee; counts and denominators; retractions as deliverables; no competing delivery; the peer's vocabulary adopted verbatim; honest fixture provenance; rule versioning; delivery vs ack; refusals as the interface) |
| Cross-plane identity/addressability join (70 pieces, byte-refereed) | `onshape_docs/verification/interop-join-vs-cadq-2026-10-03.md`: index vs volume vs identity tuple vs digest; STL bytes identical 70/70; the mesh box field that disagrees with its own bytes (1.2207e-05 mm on 16/70) vs the one that matches 70/70; 14 duplicate volume groups covering 60/70 pieces (largest 8); multiset equality 70/70; mesh volume differing 2.41e-6 relative on identical bytes. Refusal rule 17 (the bytes are the referee) and the 'a reading declares the state it was taken in' rule are pinned in the draft |
| Cross-plane tessellation handoff (70 solids) | `test_step_tessellation` (12 offline tests, no CadQuery: the plan's refusals; the v0.4 manifest shape per piece -- `bounds_mm`, `brep`, `mesh`, `cross_plane_ref`, `selectors`; the set digest taken over **exact** readings only, so two triangulations of one geometry keep one digest; `sha256_stable` carrying **two digests as evidence** and `unstablePieces` naming the ones that differ; the reproducibility mirror being created by the producer, because a CadQuery export into a missing directory writes nothing silently; an inconsistent winding nulling `volume_mm3`/`area_mm2` with `applicable: false` instead of caveating them; the exact-vs-mesh bounds cross-check; an empty tessellation refused; a misdeclared kernel recording `matches_declaration: false` with a reason; and the kernel never claimed independent by accident) | `onshape_docs/verification/interop-70piece-tessellation-2026-10-03.md`: the real 70-solid handoff, read independently by two measurement implementations (0/70 triangle-count mismatches, 0/70 winding disagreements, overhang-area aggregate agreeing to 1.31e-7) and by CadQ's own per-piece count (617748). The tessellation itself ran on CadQ's OCCT build, so the manifest declares `independent_kernel: false` -- a rule-level reproduction, not a second kernel's verdict |
| STEP import, registered tool | `test_browser_import_tool` (6 offline tests): the handler is a boundary, so the tests are about the boundary -- a dry run never touches the page (the patch raises if it does), `confirm_mutation` is required before any page work, a `no_new_element` verdict passes through untouched (a running translation is not a failure), registration happens only for an `imported` truthy result, and bad arguments are refused before any work; plus the registry entry's own gates (dry_run default true, `source_path` required, 0 REST requests, and a description that names the UNVERIFIED selectors and the pending ledger) |
| STEP import, browser leg | `test_browser_step_import` (17 stub-page tests: the plan's shape, its declared 0 Onshape API requests and its mutating flag; the unverified-selector set is exactly the four dialog constants and **excludes** the two live-observed proof anchors; source facts measured locally with `sha256Stable: false`; argument refusals; and every verdict path -- one new tab row is a proven import, an unchanged row list is `no_new_element` with `translationCompleted=unknown`, two new rows are refused as ambiguous, a failed after-read is `element_read_failed`, a failed before-read refuses **before any click**, and `into-part-studio` without a matching `expect_feature_name` answers `imported=None`) | `onshape_docs/verification/pending-live-verification-step-import-2026-10-03.json` I1-I5 / S1-S6: the Import dialog has never been opened by this code, so its four selector constants are UNVERIFIED. The verdict does not depend on them -- it reads the live-observed tab bar and user-feature rows -- so an unverified entry point cannot produce a false success |
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
