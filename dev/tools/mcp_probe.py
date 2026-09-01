"""Minimal end-to-end probe for the ordinary Onshape stdio MCP.

Spawns ``python -m mcp_main.win.mcp``, performs the MCP handshake, calls the
read-only ``browser_session(action='status')`` tool, then idles with the
connection open to verify persistent stdio behavior. Cross-host transport is an
external deployment concern and is deliberately not implemented here.

Exit code 0 means the ordinary MCP entry is healthy on the current host.
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main.win.mcp.runtime_prompt import RUNTIME_PROMPT_REVISION

TIMEOUT = 15.0


class ProbeError(RuntimeError):
    pass


def _validate_runtime_prompt(init: dict) -> str:
    instructions = init.get("result", {}).get("instructions") or ""
    expected_revision = f"[revision={RUNTIME_PROMPT_REVISION}]"
    if expected_revision not in instructions:
        raise ProbeError(
            "initialize runtime prompt is missing or belongs to another deployment "
            f"generation; expected {expected_revision}"
        )
    return instructions


def _wait_readable(fd: int, timeout: float) -> bool:
    try:
        readable, _, _ = select.select([fd], [], [], timeout)
    except InterruptedError:
        return _wait_readable(fd, timeout)
    return bool(readable)


def _read_json_objects(fd: int, until_id: int, timeout: float = TIMEOUT) -> list[dict]:
    """Read newline-delimited JSON-RPC messages until `until_id` is seen."""
    buffer = b""
    deadline = time.monotonic() + timeout
    objects: list[dict] = []
    while time.monotonic() < deadline:
        if b"\n" not in buffer:
            if not _wait_readable(fd, max(0.0, deadline - time.monotonic())):
                break
            try:
                chunk = os.read(fd, 65536)
            except InterruptedError:
                continue
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProbeError(f"non-JSON line on stdio: {line[:120]!r} ({exc})")
            objects.append(obj)
            if obj.get("id") == until_id:
                return objects
    raise ProbeError(
        f"no JSON-RPC response for id={until_id} within {timeout}s; "
        f"got {len(objects)} object(s)"
    )


def _request(proc: subprocess.Popen, obj: dict) -> dict:
    line = json.dumps(obj, ensure_ascii=False).encode() + b"\n"
    try:
        proc.stdin.write(line)
        proc.stdin.flush()
    except OSError as exc:
        raise ProbeError(f"could not write to MCP stdin: {exc}")
    replies = _read_json_objects(proc.stdout.fileno(), obj["id"])
    for reply in replies:
        if reply.get("id") == obj["id"]:
            if "error" in reply:
                raise ProbeError(f"JSON-RPC error: {reply['error']}")
            return reply
    raise ProbeError("internal probe error: matching id disappeared")


def main() -> int:
    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_main.win.mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        init = _request(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "onshape_mcp_probe", "version": "1.0"},
            },
        })
        server = init.get("result", {}).get("serverInfo", {})
        print(f"initialize ok: {server.get('name')} {server.get('version')}")
        instructions = _validate_runtime_prompt(init)
        print(
            "runtime prompt delivered via initialize.instructions: "
            f"yes ({len(instructions)} chars, expected {RUNTIME_PROMPT_REVISION})"
        )

        proc.stdin.write(
            b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        )
        proc.stdin.flush()

        listing = _request(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        })
        tools = listing.get("result", {}).get("tools", [])
        names = sorted(tool["name"] for tool in tools)
        print(f"tools/list ok: {len(tools)} tools")
        for name in names:
            print(f"  - {name}")
        if "browser_session" not in names:
            raise ProbeError("browser_session tool not returned")

        status = _request(proc, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "browser_session",
                "arguments": {"action": "status"},
            },
        })
        text = status.get("result", {}).get("content", [{}])[0].get("text", "")
        print(f"tools/call browser_session status ok: {text!r}")
        if status.get("result", {}).get("isError"):
            raise ProbeError("browser_session status returned isError=true")

        # Keep stdin open across a quiet period to verify persistent stdio.
        idle_seconds = 12
        print(f"idle {idle_seconds}s with connection open...")
        time.sleep(idle_seconds)
        if proc.poll() is not None:
            raise ProbeError(
                f"MCP exited during idle (rc={proc.returncode}); "
                "persistent connection is still broken"
            )
        print(f"idle-ok: MCP stayed alive for >= {idle_seconds}s")

        # Clean shutdown through the ordinary stdin EOF path.
        proc.stdin.close()
        try:
            rc = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise ProbeError("MCP did not exit after stdin EOF")
        print(f"MCP exited cleanly after stdin EOF (rc={rc})")
        return 0
    except ProbeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        if proc.poll() is None:
            proc.kill()
        return 1
    except Exception as exc:
        print(f"FAIL (unexpected): {exc!r}", file=sys.stderr)
        if proc.poll() is None:
            proc.kill()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
