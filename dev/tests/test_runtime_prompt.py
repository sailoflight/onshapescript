#!/usr/bin/env python3
"""Canonical MCP runtime-prompt and generated DSH companion checks."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import unittest
from pathlib import Path

from mcp_main.win.mcp.identity import SERVER_VERSION
from mcp_main.win.mcp.runtime_prompt import (
    RUNTIME_PROMPT,
    RUNTIME_PROMPT_POLICY_REVISION,
    RUNTIME_PROMPT_REVISION,
)

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "mcp_main" / "wsl" / "dsh" / "build_runtime_prompt_companion.py"
COMPANION = ROOT / "mcp_main" / "wsl" / "dsh" / "runtime-prompt-companion.js"


class RuntimePromptTest(unittest.TestCase):
    def test_policy_is_bounded_actionable_and_versioned(self) -> None:
        self.assertEqual(
            RUNTIME_PROMPT_REVISION,
            f"{SERVER_VERSION}/{RUNTIME_PROMPT_POLICY_REVISION}",
        )
        self.assertLess(len(RUNTIME_PROMPT), 2400)
        for required in (
            "Role router:",
            "Production / User:",
            "Production / Operator:",
            "Transitions and authority:",
            "structured role choice",
            "schema-defined confirmation",
            "backup or recovery point",
            "permissions never merge",
        ):
            self.assertIn(required, RUNTIME_PROMPT)
        self.assertNotIn("fs_search", RUNTIME_PROMPT)
        self.assertNotIn("browser_session", RUNTIME_PROMPT)

    def test_generated_companion_is_current(self) -> None:
        env = os.environ.copy()
        env.pop("LIVE_API_ENABLED", None)
        process = subprocess.run(
            ["python3", str(BUILDER), "--check"],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("is current", process.stdout)

    def test_wsl_facade_forwards_initialize_response_bytes(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        request = b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
        response = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"instructions": RUNTIME_PROMPT},
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        observed: list[bytes] = []

        def engine() -> None:
            connection, _ = listener.accept()
            with connection:
                chunks = bytearray()
                while True:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    chunks.extend(chunk)
                observed.append(bytes(chunks))
                connection.sendall(response)
            listener.close()

        thread = threading.Thread(target=engine, daemon=True)
        thread.start()
        process = subprocess.run(
            [
                "python3",
                str(ROOT / "mcp_main" / "wsl" / "facade" / "mcp_tcp_bridge.py"),
                str(port),
            ],
            cwd=ROOT,
            input=request,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        self.assertEqual(process.stderr, b"")
        self.assertEqual(observed, [request])
        self.assertEqual(process.stdout, response)

    def test_dsh_companion_registers_exact_namespaced_prompt(self) -> None:
        script = f"""
import {{ apply, runtimePromptRevision }} from {json.dumps(COMPANION.as_uri())};
let section;
apply({{ systemPrompt: {{ section(value) {{ section = value; }} }} }});
console.log(JSON.stringify({{ section, runtimePromptRevision }}));
"""
        process = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        observed = json.loads(process.stdout)
        self.assertEqual(observed["runtimePromptRevision"], RUNTIME_PROMPT_REVISION)
        self.assertEqual(observed["section"]["name"], "mcp:onshape:runtime-policy")
        self.assertEqual(observed["section"]["text"], RUNTIME_PROMPT)
        self.assertEqual(observed["section"]["order"], 45)


if __name__ == "__main__":
    unittest.main()
