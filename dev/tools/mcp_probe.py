"""Minimal end-to-end probe for the ordinary Onshape stdio MCP.

Spawns ``python -m mcp_main.win.mcp`` with the interpreter running this probe
(``sys.executable``, i.e. the active repository virtual environment), performs
the MCP handshake, calls the read-only ``browser_session(action='status')``
tool, then idles with the connection open to verify persistent stdio behavior.
Cross-host transport is an external deployment concern and is deliberately not
implemented here.

Exit code 0 means the ordinary MCP entry is healthy on the current host.

Failures are reported with a stable machine-readable class: the stderr human
line is ``FAIL [<class>]: <message>`` (unexpected errors keep their original
``FAIL (unexpected):`` wording), and a second single-line JSON object carries
``{"probe": ..., "result": "fail", "failureClass": ..., "message": ...}``. The
classes are:

- ``launcher`` — the probe could not start the MCP child (missing interpreter,
  or an immediate non-zero exit whose stderr shows no missing import).
- ``dependency`` — the child started but a Python install dependency is absent
  (``ModuleNotFoundError``/``ImportError`` on its stderr).
- ``protocol`` — the child ran but the stdio JSON-RPC contract broke (non-JSON
  line, JSON-RPC error object, response-id timeout, or a runtime prompt from
  another deployment generation).
- ``internal`` — an unexpected probe-side exception.

A missing launcher is therefore never reported as "MCP unavailable".

The bounded reader is portable: ``select`` cannot wait on a Windows pipe, so a
daemon thread pumps ``os.read`` into a queue and the consumer does its deadline
accounting with ``queue.get``.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main.win.mcp.runtime_prompt import RUNTIME_PROMPT_REVISION

TIMEOUT = 15.0
READ_CHUNK = 65536

FAILURE_LAUNCHER = "launcher"
FAILURE_DEPENDENCY = "dependency"
FAILURE_PROTOCOL = "protocol"
FAILURE_INTERNAL = "internal"

_DEPENDENCY_MARKERS = ("ModuleNotFoundError", "ImportError")


class ProbeError(RuntimeError):
    """A failed probe step, tagged with its machine-readable failure class."""

    def __init__(self, message: str, failure_class: str = FAILURE_PROTOCOL) -> None:
        super().__init__(message)
        self.failure_class = failure_class


def classify_child_stderr(stderr_text: str) -> str:
    """Classify a child that started and then exited from its captured stderr.

    A missing import is an install-dependency problem; anything else that kills
    the child before the handshake is a launcher/environment problem.
    """
    if any(marker in stderr_text for marker in _DEPENDENCY_MARKERS):
        return FAILURE_DEPENDENCY
    return FAILURE_LAUNCHER


class _StdioReader:
    """Bounded, portable reader for a blocking stdio pipe.

    One daemon thread pumps ``os.read(fd, READ_CHUNK)`` into a
    :class:`queue.Queue`, pushing a ``None`` sentinel after EOF or an
    ``OSError``. The consumer waits with ``queue.get(timeout=remaining)``
    against its own monotonic deadline, so byte-buffer/newline framing and the
    timeout/EOF semantics stay identical to a synchronous read. The thread is a
    daemon so it can never hang interpreter exit.

    Exactly one LIVE reader owns a given fd at a time (see ``_reader_for``),
    because two blocked readers on one pipe would race for the same bytes and
    silently drop a response. A reader that has already reported EOF is
    replaced rather than reused: an EOF'd pipe yields no further bytes, and a
    later child can land on the same fd number. The probe spawns one child per
    run, so this replacement is defensive in production; tests that reuse a
    pipe drop the binding explicitly with ``_release_reader``.
    """

    def __init__(self, fd: int) -> None:
        self.fd = fd
        self.chunks: queue.Queue[bytes | None] = queue.Queue()
        self.pending = b""
        self.eof = False
        self._thread = threading.Thread(
            target=self._pump, name=f"mcp-probe-reader-{fd}", daemon=True
        )
        self._thread.start()

    def _pump(self) -> None:
        while True:
            try:
                chunk = os.read(self.fd, READ_CHUNK)
            except InterruptedError:
                continue
            except OSError:
                break
            if not chunk:
                break
            self.chunks.put(chunk)
        self.eof = True
        self.chunks.put(None)

    def read_json_objects(self, until_id: int, timeout: float = TIMEOUT) -> list[dict]:
        """Read newline-delimited JSON-RPC messages until `until_id` is seen.

        Bytes that arrived past the matching line stay in ``pending`` so a later
        request served by this same reader never loses a pipelined response.
        """
        buffer = self.pending
        self.pending = b""
        deadline = time.monotonic() + timeout
        objects: list[dict] = []
        while time.monotonic() < deadline:
            if b"\n" not in buffer:
                try:
                    chunk = self.chunks.get(
                        timeout=max(0.0, deadline - time.monotonic())
                    )
                except queue.Empty:
                    break
                if chunk is None:
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
                    self.pending = buffer
                    return objects
        self.pending = buffer
        raise ProbeError(
            f"no JSON-RPC response for id={until_id} within {timeout}s; "
            f"got {len(objects)} object(s)"
        )


#: One persistent reader per stdout fd. Two readers on the same pipe would race
#: and the loser's bytes would be lost rather than delivered to this caller.
_READERS: dict[int, _StdioReader] = {}
_READERS_LOCK = threading.Lock()


def _reader_for(fd: int) -> _StdioReader:
    with _READERS_LOCK:
        reader = _READERS.get(fd)
        if reader is None or reader.eof:
            reader = _StdioReader(fd)
            _READERS[fd] = reader
        return reader


def _release_reader(fd: int) -> None:
    """Forget the reader bound to `fd` (test isolation for pipe reuse)."""
    with _READERS_LOCK:
        _READERS.pop(fd, None)


def _read_json_objects(fd: int, until_id: int, timeout: float = TIMEOUT) -> list[dict]:
    """Read newline-delimited JSON-RPC messages until `until_id` is seen."""
    return _reader_for(fd).read_json_objects(until_id, timeout)


def _validate_runtime_prompt(init: dict) -> str:
    instructions = init.get("result", {}).get("instructions") or ""
    expected_revision = f"[revision={RUNTIME_PROMPT_REVISION}]"
    if expected_revision not in instructions:
        raise ProbeError(
            "initialize runtime prompt is missing or belongs to another deployment "
            f"generation; expected {expected_revision}"
        )
    return instructions


def _child_stderr_text(proc: subprocess.Popen) -> str:
    """Drain the child's stderr. Only call this once the child has exited."""
    if proc.stderr is None:
        return ""
    try:
        raw = proc.stderr.read() or b""
    except (OSError, ValueError):
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return raw


def _child_failure(proc: subprocess.Popen, exc: ProbeError) -> ProbeError:
    """Reclassify a stdio failure when the child process already died.

    Only the failure path pays the short settle wait; while the child is still
    alive the original protocol error is returned unchanged.
    """
    if proc.poll() is None:
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            return exc
    stderr_text = _child_stderr_text(proc)
    failure_class = classify_child_stderr(stderr_text)
    detail = f"; MCP child exited rc={proc.returncode}"
    if stderr_text.strip():
        detail += f": {stderr_text.strip()[-400:]}"
    return ProbeError(f"{exc}{detail}", failure_class)


def _request(proc: subprocess.Popen, obj: dict) -> dict:
    line = json.dumps(obj, ensure_ascii=False).encode() + b"\n"
    try:
        proc.stdin.write(line)
        proc.stdin.flush()
    except OSError as exc:
        raise _child_failure(
            proc, ProbeError(f"could not write to MCP stdin: {exc}", FAILURE_LAUNCHER)
        ) from exc
    try:
        replies = _read_json_objects(proc.stdout.fileno(), obj["id"])
    except ProbeError as exc:
        raise _child_failure(proc, exc) from exc
    for reply in replies:
        if reply.get("id") == obj["id"]:
            if "error" in reply:
                raise ProbeError(f"JSON-RPC error: {reply['error']}")
            return reply
    raise ProbeError("internal probe error: matching id disappeared")


def _emit_failure(exc: ProbeError, human: str | None = None) -> None:
    """Print the human failure line plus one machine-readable JSON object."""
    print(human or f"FAIL [{exc.failure_class}]: {exc}", file=sys.stderr)
    print(
        json.dumps(
            {
                "probe": "onshape-mcp-stdio",
                "result": "fail",
                "failureClass": exc.failure_class,
                "message": str(exc),
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )


def _spawn(executable: str | None = None) -> subprocess.Popen:
    """Start the MCP child with the current interpreter (the active venv)."""
    command = [executable or sys.executable, "-m", "mcp_main.win.mcp"]
    try:
        return subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ProbeError(
            f"could not launch MCP with {command[0]!r}: {exc}", FAILURE_LAUNCHER
        ) from exc


def main() -> int:
    try:
        proc = _spawn()
    except ProbeError as exc:
        _emit_failure(exc)
        return 1

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
        _emit_failure(exc)
        if proc.poll() is None:
            proc.kill()
        return 1
    except Exception as exc:
        _emit_failure(
            ProbeError(str(exc), FAILURE_INTERNAL),
            human=f"FAIL (unexpected): {exc!r}",
        )
        if proc.poll() is None:
            proc.kill()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
