# `onshape_browser_mode` module contract

Status: verified

## Owns

- Browser defaults/local state, persistent Windows browser profile, session lifecycle, and single-working-page enforcement.
- Page objects, selector/frame resolution, trusted browser inputs, waits, observations, and browser workflows.
- Browser project checkpoints and browser-observed state.
- Local FeatureScript source/compile diagnostic packages captured by browser tools.
- Zero-REST-quota UI transactions and their browser-level verification evidence.

## Does not own

- MCP JSON-RPC registry/dispatch: `mcp_main` (browser adapters live in `mcp_main/win/mcp/browser_tools.py`).
- REST credentials, quota, transport, or stable target-state authority: `onshape_rest_api_mode`.
- Reusable browser behavior documentation and verification reports: `onshape_docs`.
- Capture/test scripts and fixtures: `dev/`.

## Entrypoints

| Kind | Path or symbol | Purpose |
|---|---|---|
| Session | `onshape_browser_mode/session.py` | Browser lifecycle, profile, pages, single-page invariant |
| Configuration | `onshape_browser_mode/settings.py` | Browser config paths and defaults |
| Page objects | `onshape_browser_mode/pages/` | Page/frame/locator semantics |
| Selectors | `onshape_browser_mode/selectors.py` | Shared observed selectors |
| Project workflows | `onshape_browser_mode/project.py` | Fixture-driven project execution and checkpoints |
| MCP adapters | `mcp_main/win/mcp/browser_tools.py` | Public browser tool schemas and handler installation |
| Module tests | `dev/tests/test_browser_mode.py` | Session, selectors, configuration, and browser behavior with mocks |
| Workflow tests | `dev/tests/test_browser_plan_completion.py` | Tool coverage, dry-run, fixtures, checkpoints, and completion contracts |

## Contracts and invariants

Browser semantics are layered:

```text
Project control plane (one or more L6 nodes)
  -> L6 independently consumable deliverable recipes
  -> L5 multi-transaction Onshape workflows
  -> L4 completed and verified Onshape transactions/observations
  -> L3 Onshape-aware prepare/inspect/recovery interactions
  -> L2 generic browser transactions
  -> L1 generic browser primitives
  -> selectors, page objects, frames, and waits
```

- A lower layer never calls a higher layer; same-level composition is allowed when it remains inside the same public contract and is acyclic.
- Semantic levels are optional discovery metadata, not registration, execution, or permission gates.
- Default semantic exposure omits L1/L3; `browser_discover_tools` with an explicit `semantic_levels` filter reveals exact schemas and `browser_invoke_discovered` routes them through the original handler gates. `ONSHAPE_MCP_TOOL_EXPOSURE=static` retains complete-list compatibility. Ordinary ranking is L5 workflow, L4 verified transaction/observation, L2 generic browser transaction, then L6 deliverable recipe.
- `ONSHAPE_MCP_TOOL_EXPOSURE=profile|dynamic` adds fixed or per-connection views. Dynamic `mcp_tool_view` changes only `tools/list`, emits `notifications/tools/list_changed`, and never blocks a known-name handler call; it is a context convention, not authority.
- Selectors and frame/locator resolution do not appear as duplicated literals in high-level tools.
- The Windows process owns Playwright, Edge, the persistent profile, and logged-in session.
- `browser_session(action="release")` is idempotent cooperative cleanup for the current process only; it never starts a browser, never releases another process's owner, and may require login state to be refreshed later.
- A persistent browser profile has one process owner; client reconnect does not own session teardown.
- Generic observation does not claim business success. High-level operations verify the relevant state, part count, feature history, DOM increment, or canvas change.
- New write tools perform a pure-local dry run where supported and require explicit mutation confirmation for real UI actions.
- FeatureScript compile acceptance combines Ace annotations with active-tab rows from the FeatureScript notice pane; a visible notice indicator that cannot be read fails closed.
- Every committed FeatureScript deployment writes a module-owned local diagnostic package containing the full browser-visible source and compile result; these ignored artifacts may contain proprietary code.
- Browser tools consume zero REST quota, but real UI actions can still mutate cloud data.
- `browser_export_step` owns the UI/download half of canonical STEP acquisition:
  it uses live-observed export-dialog selectors, matches the active Part Studio URL
  to explicit IDs, saves a single AP242 millimeter STEP in browser staging, and
  persists SHA/provenance. `browser_geometry_status` first checks explicit config,
  then bounded sibling/global/Windows-WSL reusable dependencies.
  `browser_configure_geometry_backend` accepts only a re-discovered opaque
  candidate ID; no executable/argv or automatic installation is exposed.
  `browser_build_geometry_package` owns the subsequent
  offline L6 package and accepts only an export ID; its executable remains in
  disabled-by-default browser module configuration.
- `browser_sync_rest_state` is an explicit boundary operation: it may merge observed IDs into REST-owned local state but does not take ownership of quota or credentials.
- Project checkpoints bind plans/fixtures and referenced sources; resume rejects incompatible changes.
- Project schema v1 keeps legacy flat `steps/assertions`. Schema v2 separates
  optional `setup` from a DAG of one or more `deliverables`; every L6 node owns
  non-empty final assertions, declared outputs, an acceptance manifest, and an
  independent completed-deliverable checkpoint boundary. The runner remains the
  Project control plane rather than an L6 tool.

## Dependencies

- Allowed: Windows Playwright/Edge runtime, module-owned page objects/selectors/settings, explicit REST state synchronization boundary, and development fixtures.
- Forbidden: installing browser dependencies on a client-only host; silently issuing REST calls; storing credentials in selectors, captures, checkpoints, or tool results; claiming success from click completion alone.

## Data, configuration, and generated files

| Item | Owner | Behavior | Source of truth |
|---|---|---|---|
| Browser defaults | `onshape_browser_mode/config/browser.toml` | Committed defaults | Settings loader |
| Geometry backend | `onshape_browser_mode/config/geometry-backend.json` | Disabled-by-default pinned executable/argv/tolerances | Browser mode owner |
| STEP and geometry staging | `onshape_browser_mode/outputs/{step_exports,geometry_packages}/` | Runtime artifacts with verified manifests | Browser export/geometry transactions |
| FeatureScript diagnostics | `onshape_browser_mode/outputs/fs_diagnostics/` | Ignored full-source, compile-result, and manifest packages | FeatureScript deploy/capture tools |
| Local config/state | `onshape_browser_mode/config/` | Ignored local/runtime writes where applicable | Browser settings/session |
| Persistent profile | `onshape_browser_mode/user_data/onshape_profile/` | Windows persistent runtime | Browser session |
| Project checkpoints | `onshape_browser_mode/user_data/project-runs/` | Atomic runtime writes | Project runner |
| Shared selectors | `onshape_browser_mode/selectors.py` | Maintained from verified observations | Code plus linked experience/evidence |
| Captures and project fixtures | `dev/fixtures-capture/`, `dev/button-map/` | Development evidence/input | Redacted committed fixture or ignored capture |

## Verification

| Change | Required verification |
|---|---|
| Session, page object, selector, settings | `python3 -m unittest dev.tests.test_browser_mode -v` |
| Tool schema, dry-run, semantic workflow, project/checkpoint | `python3 -m unittest dev.tests.test_browser_plan_completion dev.tests.test_mcp_server -v` |
| Configuration/path ownership | `python3 -m unittest dev.tests.test_project_layout -v` |
| Host/external-adapter integration | Ordinary stdio tests first; use the Operator runbook and the adapter's own acceptance suite for an authorized smoke test |
| Any Python change | Matching tests plus `python3 -m py_compile onshape_browser_mode/*.py mcp_main/win/mcp/browser_tools.py` |

Offline regression does not start a real browser, edit a cloud document, or enable `LIVE_API_ENABLED`.

## Documentation triggers

- Selector, frame, login, recovery, or page behavior conclusions update browser experience and link evidence.
- Public browser tool schema or side effects update the MCP User contract and generated tool reference.
- Session/process/deployment changes update architecture and the Operator runbook.
- New L2/L3/L4 semantics update this contract when ownership or invariants change.
- Unimplemented dynamic exposure and native-modeling plans remain roadmap content.

## Unknowns

- A selector or workflow not covered by committed fixture/mock evidence remains unverified until a read-only inspection or explicitly authorized browser evaluation provides evidence.
- Future dynamic tool exposure compatibility remains outside the current browser contract.
