#!/usr/bin/env python3
"""Portability contracts for the ordinary stdio probe.

Covers two Windows-compatibility fixes from issue #4:

* the bounded stdio reader in ``dev/tools/mcp_probe.py`` must work on a plain
  OS pipe (Windows ``select`` only accepts sockets). These tests drive the
  reader over a real ``os.pipe()`` and monkeypatch nothing.
* a subprocess argv must never hard-code the ``python3`` name, which a stock
  native Windows install does not provide. The scan excludes inert shebangs and
  the intentionally Linux-side WSL ``/usr/bin/python3`` path.

It also pins the failure classification that keeps a missing launcher from
being reported as "MCP unavailable".
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dev.tools import mcp_probe  # noqa: E402


class _PipeTestCase(unittest.TestCase):
    """A real OS pipe with guaranteed cleanup; no mocks anywhere."""

    def setUp(self) -> None:
        self.read_fd, self.write_fd = os.pipe()
        self.addCleanup(self._close, self.read_fd)
        self.addCleanup(self._close, self.write_fd)

    @staticmethod
    def _close(fd: int) -> None:
        try:
            os.close(fd)
        except OSError:
            pass

    def reader(self) -> mcp_probe._StdioReader:
        return mcp_probe._StdioReader(self.read_fd)


class PortableReaderTest(_PipeTestCase):
    def test_delayed_line_succeeds(self) -> None:
        def write_later() -> None:
            time.sleep(0.1)
            os.write(self.write_fd, b'{"jsonrpc":"2.0","id":7,"result":{"ok":true}}\n')

        threading.Thread(target=write_later, daemon=True).start()
        objects = self.reader().read_json_objects(7, timeout=5.0)
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0]["id"], 7)

    def test_split_chunks_are_reassembled(self) -> None:
        def write_later() -> None:
            time.sleep(0.05)
            os.write(self.write_fd, b'{"jsonrpc":"2.0","id":8,')
            time.sleep(0.05)
            os.write(self.write_fd, b'"result":{"n":1}}\n')

        threading.Thread(target=write_later, daemon=True).start()
        objects = self.reader().read_json_objects(8, timeout=5.0)
        self.assertEqual(objects, [{"jsonrpc": "2.0", "id": 8, "result": {"n": 1}}])

    def test_deadline_produces_probe_error(self) -> None:
        started = time.monotonic()
        with self.assertRaises(mcp_probe.ProbeError) as ctx:
            self.reader().read_json_objects(5, timeout=0.2)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertIn("no JSON-RPC response for id=5", str(ctx.exception))
        self.assertIn("within 0.2s", str(ctx.exception))
        self.assertEqual(ctx.exception.failure_class, mcp_probe.FAILURE_PROTOCOL)

    def test_non_json_chunk_produces_probe_error(self) -> None:
        os.write(self.write_fd, b"not json at all\n")
        with self.assertRaises(mcp_probe.ProbeError) as ctx:
            self.reader().read_json_objects(5, timeout=5.0)
        self.assertIn("non-JSON line on stdio", str(ctx.exception))

    def test_eof_produces_probe_error(self) -> None:
        os.close(self.write_fd)
        with self.assertRaises(mcp_probe.ProbeError) as ctx:
            self.reader().read_json_objects(5, timeout=5.0)
        self.assertIn("no JSON-RPC response for id=5", str(ctx.exception))

    def test_registry_reuses_one_reader_and_keeps_pipelined_leftovers(self) -> None:
        # Two responses in one chunk: the first request must return the first
        # line and the same reader must still deliver the second, because a
        # persistent queue means bytes already left the OS pipe.
        os.write(self.write_fd, b'{"id":1}\n{"id":2}\n')
        try:
            first = mcp_probe._read_json_objects(self.read_fd, 1, timeout=2.0)
            second = mcp_probe._read_json_objects(self.read_fd, 2, timeout=2.0)
        finally:
            mcp_probe._release_reader(self.read_fd)
        self.assertEqual([obj["id"] for obj in first], [1])
        self.assertEqual([obj["id"] for obj in second], [2])


class FailureClassificationTest(unittest.TestCase):
    def setUp(self) -> None:
        # Readers are keyed by fd; clear the registry so a reaped child's fd
        # number cannot leak into the next test.
        self.addCleanup(mcp_probe._READERS.clear)

    @staticmethod
    def _reap(proc: subprocess.Popen) -> None:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def test_default_probe_error_is_protocol(self) -> None:
        self.assertEqual(
            mcp_probe.ProbeError("boom").failure_class, mcp_probe.FAILURE_PROTOCOL
        )

    def test_missing_dependency_stderr_is_dependency(self) -> None:
        self.assertEqual(
            mcp_probe.classify_child_stderr(
                "Traceback (most recent call last):\n"
                "ModuleNotFoundError: No module named 'mcp_main'"
            ),
            mcp_probe.FAILURE_DEPENDENCY,
        )
        self.assertEqual(
            mcp_probe.classify_child_stderr("ImportError: cannot import name 'x'"),
            mcp_probe.FAILURE_DEPENDENCY,
        )

    def test_other_child_exit_is_launcher(self) -> None:
        self.assertEqual(
            mcp_probe.classify_child_stderr(""), mcp_probe.FAILURE_LAUNCHER
        )
        self.assertEqual(
            mcp_probe.classify_child_stderr("SyntaxError: invalid syntax"),
            mcp_probe.FAILURE_LAUNCHER,
        )

    def test_missing_interpreter_is_launcher_not_protocol(self) -> None:
        missing = str(Path(tempfile.gettempdir()) / "no-such-python-interpreter-xyz")
        with self.assertRaises(mcp_probe.ProbeError) as ctx:
            mcp_probe._spawn(missing)
        self.assertEqual(ctx.exception.failure_class, mcp_probe.FAILURE_LAUNCHER)
        self.assertNotIn("MCP unavailable", str(ctx.exception))

    def test_immediate_nonzero_exit_is_launcher(self) -> None:
        proc = subprocess.Popen(
            [sys.executable, "-c", "raise SystemExit(3)"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(self._reap, proc)
        with self.assertRaises(mcp_probe.ProbeError) as ctx:
            mcp_probe._request(
                proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
            )
        self.assertEqual(ctx.exception.failure_class, mcp_probe.FAILURE_LAUNCHER)

    def test_missing_install_dependency_is_dependency(self) -> None:
        proc = subprocess.Popen(
            [sys.executable, "-c", "import a_module_that_cannot_exist_xyz"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(self._reap, proc)
        with self.assertRaises(mcp_probe.ProbeError) as ctx:
            mcp_probe._request(
                proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
            )
        self.assertEqual(ctx.exception.failure_class, mcp_probe.FAILURE_DEPENDENCY)

    def test_launcher_failure_report_does_not_claim_mcp_unavailable(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(mcp_probe.ProbeError) as ctx:
                mcp_probe._spawn("/definitely/not/a/python")
            mcp_probe._emit_failure(ctx.exception)
        lines = [line for line in stderr.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertIn("FAIL [launcher]:", lines[0])
        payload = json.loads(lines[-1])
        self.assertEqual(payload["result"], "fail")
        self.assertEqual(payload["failureClass"], mcp_probe.FAILURE_LAUNCHER)
        self.assertNotIn("MCP unavailable", stderr.getvalue())


_ARGV_PYTHON3 = re.compile(r"""\[\s*["']python3["']""")


class NoHardCodedPython3ArgvTest(unittest.TestCase):
    def test_no_python3_subprocess_argv_literal_remains(self) -> None:
        offenders: list[str] = []
        for base in (ROOT / "dev", ROOT / "fdm_analysis"):
            for path in sorted(base.rglob("*.py")):
                relative = path.relative_to(ROOT).as_posix()
                for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1
                ):
                    if line.lstrip().startswith("#!"):
                        continue  # shebangs are inert on Windows
                    if _ARGV_PYTHON3.search(line):
                        offenders.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(
            offenders, [], "subprocess argv must use sys.executable"
        )

    def test_wsl_linux_side_interpreter_path_is_intact(self) -> None:
        source = (ROOT / "fdm_analysis" / "dependency_probe.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"--exec", "/usr/bin/python3"', source)

    def test_probe_reader_does_not_use_select(self) -> None:
        source = (ROOT / "dev" / "tools" / "mcp_probe.py").read_text(encoding="utf-8")
        self.assertNotIn("import select", source)
        self.assertNotIn("select.select", source)


class DependencyProbeInterpreterTest(unittest.TestCase):
    def test_running_interpreter_is_the_first_global_candidate(self) -> None:
        if not sys.executable:
            self.skipTest("this interpreter exposes no sys.executable")
        from fdm_analysis import dependency_probe

        with tempfile.TemporaryDirectory() as tmp:
            candidates = dependency_probe._python_candidates(Path(tmp))
        self.assertTrue(candidates)
        scope, executable, name = candidates[0]
        expected = Path(sys.executable).absolute()
        self.assertEqual(scope, "global")
        self.assertEqual(executable, expected)
        self.assertEqual(name, expected.name)


if __name__ == "__main__":
    unittest.main()
