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

The browser layer runs from the project virtualenv so the MCP server core stays
stdlib-only:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-browser.txt
PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/ms-playwright" .venv/bin/playwright install chromium
# On a normal desktop/workstation with sudo:
sudo .venv/bin/playwright install-deps chromium
```

Then copy `config/browser.local.toml.example` to `config/browser.local.toml`
and set `channel = ""` to use the bundled Chromium (the committed default uses
`channel = "chrome"` for a real Google Chrome install).
