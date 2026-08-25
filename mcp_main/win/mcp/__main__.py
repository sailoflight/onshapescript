#!/usr/bin/env python3
"""Full stdio MCP server entry (the MCP *body*).

NOTE: in the WSL/Windows split this is NOT the WSL entry point. The WSL DSH
must run only the thin relay `mcp_main/wsl/facade/mcp_tcp_bridge.py`; the body
runs on Windows inside `mcp_main/win/bridge/bridge_server.py`, which owns the
browser session. Running this `__main__` on WSL would start the full server
whose browser tools depend on the Windows Playwright/Edge session.
"""

from mcp_main.win.mcp.server import serve


if __name__ == "__main__":
    serve()
