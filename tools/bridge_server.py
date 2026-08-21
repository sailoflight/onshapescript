"""Windows-side localhost bridge: persistent in-process MCP server over TCP.

Run this on the Windows host (once, keeps running):
    C:\\MCP\\onshapescript\\.venv\\Scripts\\python.exe C:\\MCP\\onshapescript\\tools\\bridge_server.py [port]

WSL (mirrored networking) connects to 127.0.0.1:<port>. The bridge serves the
JSON-RPC protocol directly from THIS process (no per-connection child) because
Onshape's web client logs out the moment the browser closes and has no
"keep me signed in" option. The Playwright browser therefore must live in a
process that survives MCP client disconnects/reconnects:

    Linux MCP client -> tools/mcp_tcp_bridge.py -> this process
        -> mcp_main.server.dispatch() -> BrowserSession (persistent Edge)

Single-copy rule
----------------
A persistent browser profile can only be held by ONE process. The listener
accepts ONE client at a time and rejects extra connections instead of running
two browser-holding servers. Sequential reconnects share the same browser and
the same login session.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main.server import dispatch, response  # noqa: E402  (needs ROOT on sys.path)

LOG_PATH = ROOT / "outputs" / "bridge-server.log"
HOST = "127.0.0.1"
BUFFER_SIZE = 65536

# Only one live client at a time (see module docstring).
_ACTIVE_LOCK = threading.Lock()


def _log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def _console(message: str) -> None:
    """Print only when launched by console Python, never under pythonw.exe."""
    if sys.stdout is not None:
        print(message, flush=True)


def _parse_error() -> dict:
    return response(None, error={"code": -32700, "message": "Parse error"})


def _dispatch_line(line: bytes) -> dict | None:
    """Mirror mcp_main.server.serve()'s per-line protocol handling."""
    try:
        message = json.loads(line.decode("utf-8"))
        if not isinstance(message, dict):
            raise ValueError("Message must be a JSON object")
        return dispatch(message)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return _parse_error()


def _serve_client(conn: socket.socket, addr: tuple) -> None:
    """Serve newline-delimited JSON-RPC on one client connection.

    The browser session intentionally survives this function: returning here
    (client disconnect) must NOT close the browser, or Onshape logs out.
    """
    buffer = b""
    try:
        while True:
            data = conn.recv(BUFFER_SIZE)
            if not data:
                break
            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                outgoing = _dispatch_line(line)
                if outgoing is not None:
                    payload = json.dumps(
                        outgoing, separators=(",", ":"), ensure_ascii=False
                    ).encode("utf-8") + b"\n"
                    conn.sendall(payload)
    except OSError:
        pass
    finally:
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass
        _ACTIVE_LOCK.release()


def _close_browser_if_started() -> None:
    """Close the persistent browser only when the bridge itself is stopping."""
    try:
        import onshape_browser_mode.session as browser_session

        session = getattr(browser_session, "_session", None)
        if session is not None and session._status not in ("closed", "uninitialized"):
            session.close()
    except Exception:
        pass


def main(port: int | None = None) -> None:
    port = port if port is not None else int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, port))
    srv.listen(4)
    _console(f"onshape mcp bridge listening on {HOST}:{port}")
    _log(f"bridge server started on {HOST}:{port} (pid={os.getpid()})")

    while True:
        conn, addr = srv.accept()
        if not _ACTIVE_LOCK.acquire(blocking=False):
            _log(f"rejected client {addr}: another MCP session is active "
                 "(browser profile is single-tenant; close the other session first)")
            try:
                conn.close()
            except OSError:
                pass
            continue
        _log(f"client {addr} -> connected (browser session persists across reconnects)")
        # Serve this client synchronously on the main thread. We already only
        # allow one client at a time, and Playwright's SYNC API is thread-bound:
        # if the browser was started on one thread and a later client's request
        # runs on another thread, page.evaluate() fails with "Target page,
        # context or browser has been closed". Keeping every client on the main
        # thread keeps all browser operations on the thread that owns Playwright.
        _serve_client(conn, addr)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _close_browser_if_started()
        _log("bridge server stopped by user")
        raise SystemExit(0)
    except Exception as error:
        _close_browser_if_started()
        _log(f"bridge server stopped by fatal error: {type(error).__name__}: {error}")
        raise
