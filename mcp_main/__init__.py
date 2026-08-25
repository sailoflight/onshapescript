"""mcp_main — Onshape MCP double-side package.

The package is split by runtime side:

``win`` (the MCP Engine, runs on Windows):
  - ``win.mcp``        MCP body: identity, runtime prompt, tool schemas/handlers
                       (``server.py``, ``browser_tools.py``) and the full stdio entry.
  - ``win.bridge``     the persistent Windows bridge process (``bridge_server.py``)
                       plus its windowless start/restart self-heal scripts.

``wsl`` (the MCP Facade + DSH plugin, runs on WSL/Linux):
  - ``wsl.facade``     the pure-stdlib stdio<->loopback-TCP relay
                       (``mcp_tcp_bridge.py``).
  - ``wsl.dsh``        the DSH runtime-prompt companion generator, the namespaced
                       companion JS, and the DSH cordis.patch example.
  - ``wsl_bridge_ctl.sh``  WSL-side one-shot control (start/restart/status) that
                       triggers the Windows bridge via WSL interop.

``bridge/`` (docs only) holds the generic WIN-WSL bridge architecture template
and this project's wiring notes.

Rules: WSL keeps no browser dependency, credentials, or runtime state; the
Windows Engine owns the browser, profile, and canonical runtime prompt. The WSL
facade only relays and triggers; it never runs the MCP body.
"""
