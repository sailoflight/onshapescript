#!/usr/bin/env python3
"""Run the Onshape FeatureScript MCP server over stdio."""

from mcp_main.server import serve


if __name__ == "__main__":
    serve()
