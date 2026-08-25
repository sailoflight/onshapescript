# `onshape_browser_mode` module contract

Status: verified

## Owns

- Browser defaults/local state, persistent Windows browser profile, session lifecycle, and single-working-page enforcement.
- Page objects, selector/frame resolution, trusted browser inputs, waits, observations, and browser workflows.
- Browser project checkpoints and browser-observed state.
- Zero-REST-quota UI transactions and their browser-level verification evidence.

## Does not own

- MCP JSON-RPC registry/dispatch: `mcp_main` (browser adapters live in `mcp_main/browser_tools.py`).
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
| MCP adapters | `mcp_main/browser_tools.py` | Public browser tool schemas and handler installation |
| Module tests | `dev/tests/test_browser_mode.py` | Session, selectors, configuration, and browser behavior with mocks |
| Workflow tests | `dev/tests/test_browser_plan_completion.py` | Tool coverage, dry-run, fixtures, checkpoints, and completion contracts |

## Contracts and invariants

Browser semantics are layered:

```text
L4 fixture-driven projects
  -> L3 multi-transaction workflows
  -> L2 user-intent transactions
  -> L1 generic browser actions
  -> selectors, page objects, frames, and waits
```

- A lower layer never calls a higher layer.
- Selectors and frame/locator resolution do not appear as duplicated literals in high-level tools.
- The Windows process owns Playwright, Edge, the persistent profile, and logged-in session.
- A persistent browser profile has one process owner; client reconnect does not own session teardown.
- Generic observation does not claim business success. High-level operations verify the relevant state, part count, feature history, DOM increment, or canvas change.
- New write tools perform a pure-local dry run where supported and require explicit mutation confirmation for real UI actions.
- Browser tools consume zero REST quota, but real UI actions can still mutate cloud data.
- `browser_sync_rest_state` is an explicit boundary operation: it may merge observed IDs into REST-owned local state but does not take ownership of quota or credentials.
- Project checkpoints bind plans/fixtures and referenced sources; resume rejects incompatible changes.

## Dependencies

- Allowed: Windows Playwright/Edge runtime, module-owned page objects/selectors/settings, explicit REST state synchronization boundary, and development fixtures.
- Forbidden: installing browser dependencies into the WSL relay; silently issuing REST calls; storing credentials in selectors, captures, checkpoints, or tool results; claiming success from click completion alone.

## Data, configuration, and generated files

| Item | Owner | Behavior | Source of truth |
|---|---|---|---|
| Browser defaults | `onshape_browser_mode/config/browser.toml` | Committed defaults | Settings loader |
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
| Windows bridge integration | Offline bridge tests first; use the Operator runbook for an explicitly authorized Windows smoke test |
| Any Python change | Matching tests plus `python3 -m py_compile onshape_browser_mode/*.py mcp_main/browser_tools.py` |

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
