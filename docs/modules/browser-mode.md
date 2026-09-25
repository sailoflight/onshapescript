# `onshape_browser_mode` module contract

Status: verified

## Owns

- Browser defaults/local state, persistent Windows browser profile, and the Onshape session facade. `browser_common.SyncSession` owns native driver/context/current-page lifecycle and scoped page cleanup; the facade owns login, recovery selection and tool-boundary single-working-page enforcement.
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
- Default browser discovery omits L1/L3; `browser_discover_tools` with an explicit `semantic_levels` filter reveals exact schemas, and a candidate is then called by its exact registered name, which still passes through its original handler gates. Ordinary ranking is L5 workflow, L4 verified transaction/observation, L2 generic browser transaction, then L6 deliverable recipe.
- A query that names a CAD feature also carries the matching whole-feature capability cards in the same result (`capabilities`), built by `onshape_browser_mode/capabilities.py`. Cards are contracts, not implementations: adding one adds no tool and widens no exposure level.
- Tool exposure defaults to `gateway` (25 advertised tools). `static`, `semantic`, and `profile` are fixed views; `dynamic` is the collapse/expand control (a cold start is collapsed on the three control/discovery entry points and `expand` opens `gateway` by default). `mcp_tool_view` changes only `tools/list`, emits `notifications/tools/list_changed` when the effective view changes, and never blocks a known-name handler call; it is a context convention, not authority. The view state is CONNECTION-scoped, not conversation-scoped.
- Selectors and frame/locator resolution do not appear as duplicated literals in high-level tools.
- The Windows process owns Playwright, Edge, the persistent profile, and logged-in session. The browser is a real Edge channel (`channel = "msedge"`) with a persistent, checkout-local profile (`user_data_dir`); it does not reuse the OS Edge primary profile, but a Microsoft-account machine signs a fresh profile in automatically, so the window is not anonymous. `isolated_user_data_dir` selects a separate profile directory (a directory choice only; `--guest` is not implemented).
- A browser session is kept at the end of a task by default. `browser_session(action="release")` is idempotent cooperative cleanup for the current process only and CLOSES the window, so it can drop the persistent login state; `browser_session(action="detach")` keeps the window but is supported only in resident/attached mode and reports `detached=false`/`supported=false` otherwise. Neither releases another process's owner.
- `browser_session action=status` reports the last `pageSelection` (`considered`/`discarded` with reason `closed` or `browserInternal`/`selected`), plus `verdict`/`recommendedAction`/`verdictNote`. `start()` never adopts a closed page: it skips closed pages, advances past an adopt failure, and falls back to a new page; when no page is usable the error recommends `browser_session action=login`, and `action=login` itself reports `alreadyAuthenticated` or `needsHumanLogin`.
- A persistent browser profile has one process owner; client reconnect does not own session teardown.
- Clients sharing that backend also share its login state, current page, active Studio, dialogs, and in-memory browser state. Request serialization does not isolate a multi-call workflow, so every tool requiring the browser session is classified `exclusive_workflow/browser_profile`.
- Until scoped document leases are accepted end to end, only one agent may perform a modifying Onshape workflow; other clients are limited to registry-classified safe reads.
- Generic observation does not claim business success. High-level operations verify the relevant state, part count, feature history, DOM increment, or canvas change.
- New write tools perform a pure-local dry run where supported and require explicit mutation confirmation for real UI actions.
- FeatureScript compile acceptance combines Ace annotations with active-tab rows from the FeatureScript notice pane; a visible notice indicator that cannot be read fails closed.
- Every committed FeatureScript deployment writes a module-owned local diagnostic package containing the full browser-visible source and compile result; these ignored artifacts may contain proprietary code.
- Browser tools consume zero REST quota, but real UI actions can still mutate cloud data.
- `browser_export_step` owns the UI/download half of canonical STEP acquisition:
  it uses live-observed export-dialog selectors, matches the active Part Studio URL
  to explicit IDs, saves a single AP242 millimeter STEP in browser staging, and
  persists SHA/provenance. A staging failure after the save/download tail is
  reported as a STRUCTURED result (`exported: false`, `failure:{phase,error}`,
  `stagedArtifacts`, `stagingComplete`, `alreadyStaged`, `browserAliveBefore/After`,
  and a LIST `recovery`) rather than raised; the tab/URL/dialog-config and
  non-STEP pre-flight failures still raise. A failure at `wait_for_dialog_hidden`
  with `stagingComplete: true` is not a download failure — the STEP and its
  manifest are on disk and reusable, and a same-`export_id` retry returns
  `alreadyStaged` success. `overwrite=true` lets a retry reuse a partial staging
  directory; a complete staging requires manifest + artifact + matching sha256.
  `onshape_geometry_status` reports every configured
  backend in one answer and, per backend, first checks explicit config and then
  bounded sibling/global/Windows-WSL reusable dependencies.
  `onshape_configure_geometry_backend` accepts only a re-discovered opaque
  candidate ID plus an explicit `backend='rest'|'browser'` (the shared scan's ids
  are not backend-specific); no executable/argv or automatic installation is
  exposed. The former browser-only status/configure names remain callable as
  deprecated wrappers that delegate to the surviving commands.
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

- Allowed: Python >=3.11, pinned `lijq-browser-common==0.1.0.dev2` from the module's bundled wheel, Windows Playwright/Edge runtime, module-owned page objects/selectors/settings, explicit REST state synchronization boundary, and development fixtures.
- `BrowserSession` lazily composes a single shared owner and delegates native page/context access; imports, offline status and unstarted release work without browser dependencies. It never adds sibling source paths to `sys.path`.
- Single-page reconciliation runs at explicit preparation boundaries, protects active temporary scopes, and raises on incomplete cleanup. Status observes an app page without adopting it. Release preserves existing response fields, records operation/type-only warnings, and retains the driver when context/browser closure fails so another release can retry.
- The adapter preserves business app-URL preference, launch options and three-attempt launch retry only after complete cleanup. See `../development/BROWSER_COMMON_INTEGRATION.md` for package provenance, offline checks and rollback.
- Forbidden: installing browser dependencies on a client-only host; silently issuing REST calls; storing credentials in selectors, captures, checkpoints, or tool results; claiming success from click completion alone.

## Data, configuration, and generated files

| Item | Owner | Behavior | Source of truth |
|---|---|---|---|
| Browser defaults | `onshape_browser_mode/config/browser.toml` | Committed defaults; `resident = true` since 2026-09-26 so the login survives a child restart (opt out per deployment in `browser.local.toml`) | Settings loader |
| Geometry backend | `onshape_browser_mode/config/geometry-backend.json` | Disabled-by-default pinned executable/argv/tolerances; machine-local operator state the artifact excludes (`.example` ships, a missing file reads as the disabled default) | Browser mode owner |
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
| Session, page object, selector, settings | `python -m unittest dev.tests.test_browser_mode dev.tests.test_browser_common_integration -v` (install the bundled wheel first; no Playwright/browser needed for fakes) |
| Tool schema, dry-run, semantic workflow, project/checkpoint | `python -m unittest dev.tests.test_browser_plan_completion dev.tests.test_mcp_server -v` |
| Configuration/path ownership | `python -m unittest dev.tests.test_project_layout -v` |
| Host/external-adapter integration | Ordinary stdio tests first; use the Operator runbook and the adapter's own acceptance suite for an authorized smoke test |
| Any Python change | Matching tests plus `python -m py_compile onshape_browser_mode/*.py mcp_main/win/mcp/browser_tools.py` |

Offline regression does not start a real browser, edit a cloud document, or enable `LIVE_API_ENABLED`.

## Documentation triggers

- Selector, frame, login, recovery, or page behavior conclusions update browser experience and link evidence.
- Public browser tool schema or side effects update the MCP User contract and generated tool reference.
- Session/process/deployment changes update architecture and the Operator runbook.
- New L2/L3/L4 semantics update this contract when ownership or invariants change.
- Native-modeling plans remain roadmap content; dynamic tool exposure is implemented and owned by `mcp_main`.

## Unknowns

- A selector or workflow not covered by committed fixture/mock evidence remains unverified until a read-only inspection or explicitly authorized browser evaluation provides evidence.
- Dynamic exposure is implemented for `semantic`/`static`/`profile`/`dynamic`/`gateway`; a client that cannot refresh `tools/list` should use a fixed view.
