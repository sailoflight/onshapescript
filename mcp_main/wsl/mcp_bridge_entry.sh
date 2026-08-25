#!/usr/bin/env bash
# DSH plugin entry: ensure the Windows bridge is up, then relay stdio<->TCP.
#
# This is the command the DSH MCP client (the onshape DSH plugin) spawns for the
# `mcp-onshape-featurescript` row in `mcp_main/wsl/dsh/cordis.patch.yml`. It is
# the orchestration layer between the DSH plugin and the Windows bridge:
#
#   DSH MCP client -> this entry -> (status ? else start) -> facade relay
#
# It first asks `wsl_bridge_ctl.sh status` whether the Windows bridge is already
# reachable on the loopback port; when it is not, it calls
# `wsl_bridge_ctl.sh start` to pull the Windows bridge up (via WSL interop ->
# wscript.exe -> mcp_main/win/bridge/windows/*.vbs). Only then does it exec the
# thin stdio<->TCP relay. This fixes the "relay exits immediately because the
# Windows bridge was never started" failure mode without ever running the MCP
# body or the browser in WSL.
#
# Usage (as the DSH MCP client command):
#   mcp_main/wsl/mcp_bridge_entry.sh [port]      # default port 8766
#
# Env overrides (passed through to wsl_bridge_ctl.sh):
#   ONSHAPE_WIN_ROOT      Windows repo root (default C:\MCP\onshapescript)
#   ONSHAPE_BRIDGE_PORT   bridge port (default 8766)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PORT="${1:-${ONSHAPE_BRIDGE_PORT:-8766}}"
CTL="$ROOT/mcp_main/wsl/wsl_bridge_ctl.sh"
RELAY="$ROOT/mcp_main/wsl/facade/mcp_tcp_bridge.py"

die() { echo "mcp_bridge_entry: $*" >&2; exit 1; }

[ -x "$CTL" ] || die "wsl_bridge_ctl.sh not found or not executable: $CTL"
[ -f "$RELAY" ] || die "facade relay not found: $RELAY"

# 1. Is the Windows bridge already reachable? (pure WSL check, no Windows call)
if ONSHAPE_BRIDGE_PORT="$PORT" "$CTL" status >/dev/null 2>&1; then
    echo "mcp_bridge_entry: Windows bridge already reachable on 127.0.0.1:$PORT" >&2
else
    echo "mcp_bridge_entry: Windows bridge not reachable on 127.0.0.1:$PORT; starting it" >&2
    ONSHAPE_BRIDGE_PORT="$PORT" "$CTL" start
    # A freshly started bridge may need a moment to bind. Poll until reachable.
    for _ in $(seq 1 20); do
        if ONSHAPE_BRIDGE_PORT="$PORT" "$CTL" status >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    if ! ONSHAPE_BRIDGE_PORT="$PORT" "$CTL" status >/dev/null 2>&1; then
        die "Windows bridge did not become reachable on 127.0.0.1:$PORT after start"
    fi
fi

# 2. Relay stdio<->loopback TCP. exec keeps this process the MCP client's stdio
#    child; the Windows bridge holds the browser and persists across reconnects.
exec python3 "$RELAY" "$PORT"
