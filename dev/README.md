# dev/ — development lab

Development and exploration workspace for the browser-automation layer. Nothing
in this directory is imported by `mcp_main` at runtime; probes and capture
scripts are run manually.

| Path | Purpose |
|---|---|
| `watch-sessions/` | Listener recordings of human-operated Onshape sessions (gitignored). |
| `button-map/` | Human-reviewed button/action semantics derived from watch sessions. Committed once verified. |
| `probes/` | Zero-API-quota probes: login state, selector discovery, editor type, page structure. |
| `fixtures-capture/` | Scripts that record redacted DOM/HAR fixtures for offline tests. |
| `spike/` | Throwaway experiments (e.g. Monaco editor strategy). Gitignored. |

## Browser setup

```bash
python3 -m pip install -r requirements-browser.txt
python3 -m playwright install chrome
```

Then copy `config/browser.local.toml.example` to `config/browser.local.toml`
for machine-local overrides if needed.
