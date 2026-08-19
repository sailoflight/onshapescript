#!/usr/bin/env python3
"""Compatibility entry point for the Onshape FeatureScript MCP server.

The real implementation now lives in `mcp_main/server.py`. This shim keeps the
well-known `python3 mcp_server.py` launch path working and re-exports the server
module's public names (e.g. TOOLS) for existing tests and tooling.
"""

from mcp_main.server import *  # noqa: F401,F403  (re-export the server's public API)
from mcp_main.server import serve


if __name__ == "__main__":
    serve()
