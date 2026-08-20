# dev/ — development lab

Development and exploration workspace for the browser-automation layer. Nothing
in this directory is imported by `mcp_main` at runtime; probes and capture
scripts are run manually.

| Path | Purpose |
|---|---|
| `watch-sessions/` | Listener recordings of human-operated Onshape sessions (gitignored). |
| `button-map/` | Human-reviewed button/action semantics derived from watch sessions. Committed once verified. |
| `experience/` | 使用经验：页面结构、选择器、滚动容器、登录态恢复等实测结论。 |
| `probes/` | Zero-API-quota probes: login state, selector discovery, editor type, page structure. |
| `fixtures-capture/` | Scripts that record redacted DOM/HAR fixtures for offline tests. |
| `spike/` | Throwaway experiments (e.g. Monaco editor strategy). Gitignored. |
| `DEVELOPMENT.md` | 开发经验与下一步计划。 |

## Browser setup

Browser automation runs on Windows, not Linux. The Linux side is stdlib-only and
only runs the stdio↔TCP relay; the Windows side owns Playwright, Chrome/Edge,
and the persistent login profile.

- Windows install + run: see `tools/windows/README.md`
- Linux MCP client config points at `tools/mcp_tcp_bridge.py`

```json
{
  "mcpServers": {
    "onshape-featurescript": {
      "command": "python3",
      "args": ["/home/<user>/code/onshapescript/tools/mcp_tcp_bridge.py", "8766"],
      "cwd": "/home/<user>/code/onshapescript"
    }
  }
}
```

Do not install `playwright` on Linux; the Linux bridge has zero third-party
dependencies.
