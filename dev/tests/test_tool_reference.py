#!/usr/bin/env python3
"""Offline contracts for the generated MCP tool reference."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main.win.mcp import server  # noqa: E402


class ToolReferenceTest(unittest.TestCase):
    def test_registered_tools_and_handlers_match(self) -> None:
        tool_names = [tool["name"] for tool in server.TOOLS]
        self.assertEqual(len(tool_names), len(set(tool_names)))
        self.assertEqual(set(tool_names), set(server.HANDLERS))

    def test_registered_tools_have_explicit_network_cost(self) -> None:
        for tool in server.TOOLS:
            cost = tool["cost"]
            self.assertIn(cost["network"], {"offline", "browser", "live"}, tool["name"])
            if cost["network"] == "offline":
                self.assertEqual(cost["max_api_requests"], 0, tool["name"])
            if cost["network"] == "live":
                self.assertEqual(
                    cost["max_api_requests"], cost["max_requests"], tool["name"]
                )

    def test_generated_reference_is_current(self) -> None:
        env = os.environ.copy()
        env.pop("LIVE_API_ENABLED", None)
        process = subprocess.run(
            ["python3", "onshape_docs/scripts/build_tool_reference.py", "--check"],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("Tool reference is current", process.stdout)

    def test_generated_reference_records_current_registry(self) -> None:
        text = (ROOT / "docs" / "generated" / "TOOL_REFERENCE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(f"Registered tools: **{len(server.TOOLS)}**", text)
        for tool in server.TOOLS:
            self.assertEqual(text.count(f"| `{tool['name']}` |"), 1, tool["name"])


if __name__ == "__main__":
    unittest.main()
