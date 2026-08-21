# dev/ — development lab

Development, test, and exploration workspace. Nothing here is imported by
`mcp_main` at runtime; tests, probes, and capture scripts run only when invoked.

| Path | Purpose |
|---|---|
| `watch-sessions/` | Listener recordings of human-operated Onshape sessions (gitignored). |
| `button-map/` | Human-reviewed button/action semantics derived from watch sessions. Committed once verified. |
| `probes/` | Zero-API-quota probes: login state, selector discovery, editor type, page structure. |
| `fixtures-capture/` | Scripts that record redacted DOM/HAR fixtures for offline tests. |
| `spike/` | Throwaway experiments (e.g. Monaco editor strategy). Gitignored. |
| `tests/` | Offline unit, protocol, static-guard, and bridge-script tests. |
| `tools/` | Manually invoked development probes. |
| `DEVELOPMENT.md` | 开发经验与下一步计划。 |

## Browser setup

Browser automation runs on Windows, not Linux. The Linux side is stdlib-only and
only runs the stdio↔TCP relay; the Windows side owns Playwright, Chrome/Edge,
and the persistent login profile.

- Windows install + run: see `mcp_main/bridge/windows/README.md`
- Linux MCP client config points at `mcp_main/bridge/mcp_tcp_bridge.py`

```json
{
  "mcpServers": {
    "onshape-featurescript": {
      "command": "python3",
      "args": ["/home/<user>/code/onshapescript/mcp_main/bridge/mcp_tcp_bridge.py", "8766"],
      "cwd": "/home/<user>/code/onshapescript"
    }
  }
}
```

Do not install `playwright` on Linux; the Linux bridge has zero third-party
dependencies.
