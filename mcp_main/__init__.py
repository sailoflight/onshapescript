"""Onshape MCP protocol package.

``mcp_main.win.mcp`` is the ordinary stdio MCP server. It owns identity,
initialization, schemas, handlers, and protocol-clean stdout. ``mcp_main.dsh``
contains only the generated DSH runtime-policy companion and its installation
example.

Cross-host transport, registries, listeners, process supervision, and reconnect
behavior belong to an independently installed bridge. This repository ships no
WSL facade, TCP listener, scheduled-task launcher, or project-specific relay.
Browser profiles, browser configuration, REST credentials, and runtime state
remain owned by their domain modules on the host running the ordinary MCP.
"""
