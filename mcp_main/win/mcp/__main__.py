#!/usr/bin/env python3
"""Ordinary stdio entry for the complete Onshape MCP server.

Run this entry on the host that owns the configured browser/profile and local
REST state. Cross-host clients must connect through an independently installed
MCP bridge that launches this command; this repository does not implement that
transport.
"""

from mcp_main.win.mcp.server import serve


if __name__ == "__main__":
    serve()
