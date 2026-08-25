# Development lab

The repository `dev/` directory contains executable development material only.
Nothing under it is imported by `mcp_main` at runtime; tests, probes, capture
scripts, and fixtures run only when explicitly invoked.

## Directory map

| Path under `dev/` | Purpose | Persistence |
|---|---|---|
| `watch-sessions/` | Recordings of human-operated Onshape sessions | Gitignored runtime evidence |
| `button-map/` | Human-reviewed button and action semantics derived from recordings | Commit only after verification |
| `probes/` | Zero-API-quota probes for login state, selectors, editor type, and page structure | Development scripts |
| `fixtures-capture/` | Capture scripts and redacted DOM/HAR or workflow fixtures for offline tests | Scripts and selected committed fixtures |
| `spike/` | Throwaway experiments such as editor-strategy spikes | Gitignored |
| `tests/` | Offline unit, protocol, static-guard, layout, and bridge-script tests | Committed |
| `tools/` | Manually invoked development probes and helpers | Committed where reusable |

## Rules

- Project documentation belongs under `docs/` or `onshape_docs/`, not `dev/`.
- Tests must keep `LIVE_API_ENABLED` unset unless a separately authorized live procedure explicitly overrides it.
- Recordings, captures, and fixtures must not contain authorization headers,
  cookies, tokens, passwords, access keys, or secrets.
- Reusable verified browser behavior belongs in
  `onshape_docs/experience/browser-automation.md` or
  `onshape_docs/experience/browser-modeling.md`; raw evidence stays in the
  appropriate fixture, recording, or verification location.
- Throwaway spikes must not become hidden runtime dependencies.
- Windows browser dependencies and persistent runtime state must not be installed
  or stored in the WSL development lab.

## Verification entry

Run the complete offline suite from the repository root:

```bash
python3 -m unittest discover -s dev/tests -v
```

Select narrower commands through `../verification/MATRIX.md` when changing one
module or development facility.
