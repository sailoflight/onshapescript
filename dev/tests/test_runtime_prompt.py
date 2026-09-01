#!/usr/bin/env python3
"""Canonical MCP runtime-prompt and generated DSH companion checks."""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

from mcp_main.win.mcp.identity import SERVER_VERSION
from mcp_main.win.mcp.runtime_prompt import (
    RUNTIME_PROMPT,
    RUNTIME_PROMPT_POLICY_REVISION,
    RUNTIME_PROMPT_REVISION,
)

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "mcp_main" / "dsh" / "build_runtime_prompt_companion.py"
COMPANION = ROOT / "mcp_main" / "dsh" / "runtime-prompt-companion.js"


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
