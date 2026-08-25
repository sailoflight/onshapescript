# `onshape_rest_api_mode` module contract

Status: verified

## Owns

- Onshape REST request construction, authentication boundary, transport, response parsing, and domain operations.
- The explicit `LIVE_API_ENABLED` live-request gate and quota preflight/accounting.
- Stable document/workspace/element target state, ignored credentials, passive usage ledger, and REST outputs.
- Parameter payload construction using example-owned parameter sets.
- Mock/fixture/replay/dry-run compatible operation boundaries.

## Does not own

- MCP JSON-RPC schemas and dispatch: `mcp_main`.
- Browser UI sessions and zero-REST-quota UI automation: `onshape_browser_mode`.
- Offline REST reference indexes and authored API guidance: `onshape_docs`.
- Example parameter semantics and validation contract: the example project.

## Entrypoints

| Kind | Path or symbol | Purpose |
|---|---|---|
| Client/transport | `onshape_rest_api_mode/client.py` | Paths, credentials boundary, request transport, live enablement |
| Budget policy | `onshape_rest_api_mode/budget.py` | `live_blocker`, budget guard, request-cost preflight |
| Operations | `onshape_rest_api_mode/operations.py` | Read, evaluate, upload, instantiate, validate, render workflows |
| Stable configuration | `onshape_rest_api_mode/config/onshape-state.json` | Target IDs and quota configuration |
| Guard tests | `dev/tests/test_quota_guards.py` | Live gate, budgets, retry, redaction, and failure paths |
| Layout tests | `dev/tests/test_project_layout.py` | Module-owned path contracts |

## Contracts and invariants

- Real requests are rejected unless `LIVE_API_ENABLED` is explicitly truthy.
- Regression verification never enables the live gate.
- Live requests require one unresolved fact, an expected/max request budget, and preflight.
- 429 is not retried; mutating timeout/5xx paths are not automatically retried.
- Higher-level operations must not hide unbudgeted lookup chains, pagination, cleanup, or write-after-read confirmation.
- Stable metadata uses explicit IDs, cached state, fixtures, or prior results rather than implicit discovery.
- Mutating MCP tools require explicit confirmation before constructing a live client.
- Credential values and authorization material never enter tool responses, committed fixtures, prompts, or protocol stdout.
- Runtime data and configuration stay under the REST module; example parameter files stay with the example.

## Dependencies

- Allowed: standard-library HTTP/crypto/data utilities, module-owned configuration, example parameter sets, and offline reference/query helpers where explicitly required.
- Forbidden: importing browser session ownership; bypassing `live_blocker`/budget guards; treating upstream REST as a development debugger; moving credentials or quota state to MCP arguments or repository root.

## Data, configuration, and generated files

| Item | Owner | Behavior | Source of truth |
|---|---|---|---|
| Stable target/quota config | `onshape_rest_api_mode/config/onshape-state.json` | Read and explicit updates | Committed state file |
| Credentials | `onshape_rest_api_mode/config/onshape-credentials.json` | Ignored, read only at live boundary | Local secret file |
| Passive usage ledger | `onshape_rest_api_mode/config/api-usage.json` | Ignored runtime accounting | Successful response accounting |
| REST outputs/previews | `onshape_rest_api_mode/outputs/` | Generated | Operations producing them |
| Example parameter sets | `examples/branch-cable-trophy/config/` | Read by payload builders | Example-owned JSON |
| Path overrides | `ONSHAPE_CREDENTIALS`, `ONSHAPE_STATE`, `ONSHAPE_PARAMETERS_DIR`, `ONSHAPE_OUTPUTS_DIR`, `ONSHAPE_API_USAGE` | Explicit process-local override; defaults remain module/example owned | `onshape_rest_api_mode/client.py` |
| Live fixtures | `dev/tests/fixtures/onshape/` when present | Redacted and replayable | One explicitly budgeted observation |

## Verification

| Change | Required verification |
|---|---|
| Live gate, quota, retry, redaction | `python3 -m unittest dev.tests.test_quota_guards -v` |
| State/config/output ownership | `python3 -m unittest dev.tests.test_project_layout -v` |
| MCP REST wrapper schema/dispatch | `python3 -m unittest dev.tests.test_mcp_server -v` |
| Request/response operation | Target unit/mock/replay tests; no live request for regression |
| Any Python change | Matching tests plus `python3 -m py_compile onshape_rest_api_mode/*.py` |

All verification commands run with `LIVE_API_ENABLED` unset.

## Documentation triggers

- Public REST-backed tool behavior, cost, or mutation changes update the MCP User contract and generated tool reference.
- Quota, retry, fixture, or live safety changes update root hard constraints, verification, and relevant REST experience.
- Configuration or deployment changes update the Operator runbook.
- New verified API behavior updates experience and evidence separately from upstream reference.

## Unknowns

- Live server behavior outside existing fixtures, cached observations, and versioned evidence remains unknown until one explicitly authorized and budgeted observation is necessary.
