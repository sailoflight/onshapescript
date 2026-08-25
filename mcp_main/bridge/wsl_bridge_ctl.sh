#!/usr/bin/env bash
# WSL-side one-shot control for the Windows-hosted onshapescript MCP bridge.
#
# The bridge body (mcp_main/bridge/bridge_server.py -> mcp_main.server.dispatch)
# must run on Windows so it can drive a real Edge window with the persistent
# onshape_browser_mode\user_data\onshape_profile login. This script only *triggers*
# the Windows-side hidden launchers via WSL interop; it never starts
# bridge_server.py in WSL.
#
# Ported strictly from taobao-mcp tools/wsl_bridge_ctl.sh, adjusted only for
# this project's paths: the Windows launchers live under mcp_main\bridge\windows\
# and the default bridge port is 8766.
#
# Usage:
#   mcp_main/bridge/wsl_bridge_ctl.sh start     # windowless start on Windows
#   mcp_main/bridge/wsl_bridge_ctl.sh restart   # force-kill browser+bridge, then start
#   mcp_main/bridge/wsl_bridge_ctl.sh status    # check loopback port (no Windows call)
#
# Env overrides:
#   ONSHAPE_WIN_ROOT      Windows repo root (default C:\MCP\onshapescript)
#   ONSHAPE_BRIDGE_PORT   bridge port (default 8766)

set -euo pipefail

PORT="${ONSHAPE_BRIDGE_PORT:-8766}"
WIN_ROOT="${ONSHAPE_WIN_ROOT:-C:\\MCP\\onshapescript}"
WIN_START_VBS="$WIN_ROOT\\mcp_main\\bridge\\windows\\start-bridge-hidden.vbs"
WIN_RESTART_VBS="$WIN_ROOT\\mcp_main\\bridge\\windows\\restart-bridge-hidden.vbs"

WSCRIPT="/mnt/c/Windows/System32/wscript.exe"

die() { echo "wsl_bridge_ctl: $*" >&2; exit 1; }

case "${1:-status}" in
  start)
    [ -x "$WSCRIPT" ] || die "wscript.exe not found at $WSCRIPT (WSL interop unavailable?)"
    echo "wsl_bridge_ctl: starting Windows bridge on 127.0.0.1:$PORT (windowless)"
    "$WSCRIPT" //B //Nologo "$WIN_START_VBS" "$PORT"
    ;;
  restart)
    [ -x "$WSCRIPT" ] || die "wscript.exe not found at $WSCRIPT (WSL interop unavailable?)"
    echo "wsl_bridge_ctl: force-restarting Windows bridge on 127.0.0.1:$PORT"
    "$WSCRIPT" //B //Nologo "$WIN_RESTART_VBS" "$PORT"
    ;;
  status)
    if timeout 2 bash -c "echo > /dev/tcp/127.0.0.1/$PORT" 2>/dev/null; then
      echo "bridge reachable on 127.0.0.1:$PORT"
    else
      echo "bridge NOT reachable on 127.0.0.1:$PORT"
      exit 1
    fi
    ;;
  *)
    die "unknown command '${1}'; use start|restart|status"
    ;;
esac
