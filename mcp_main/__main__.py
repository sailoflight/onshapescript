#!/usr/bin/env python3
"""Full stdio MCP server entry (the MCP *body*).

NOTE: in the WSL/Windows split this is NOT the WSL entry point. The WSL DSH
must run only the thin relay `mcp_main/bridge/mcp_tcp_bridge.py`; the body
runs on Windows inside `mcp_main/bridge/bridge_server.py`, which owns the
browser session. Running `python -m mcp_main` on WSL would start the full
server whose browser tools depend on the Windows Playwright/Edge session.
"""

from mcp_main.server import serve


if __name__ == "__main__":
    serve()
