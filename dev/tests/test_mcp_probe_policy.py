#!/usr/bin/env python3
"""Deployment-generation assertions used by the live MCP probe."""

from __future__ import annotations

import unittest

from dev.tools import mcp_probe
from mcp_main.win.mcp.runtime_prompt import RUNTIME_PROMPT, RUNTIME_PROMPT_REVISION


class McpProbePolicyTest(unittest.TestCase):
    def test_accepts_current_runtime_policy(self) -> None:
        init = {"result": {"instructions": RUNTIME_PROMPT}}
        self.assertEqual(mcp_probe._validate_runtime_prompt(init), RUNTIME_PROMPT)

    def test_rejects_missing_runtime_policy(self) -> None:
        with self.assertRaisesRegex(mcp_probe.ProbeError, RUNTIME_PROMPT_REVISION):
            mcp_probe._validate_runtime_prompt({"result": {}})

    def test_rejects_stale_runtime_policy(self) -> None:
        init = {"result": {"instructions": "Onshape policy [revision=stale]"}}
        with self.assertRaisesRegex(mcp_probe.ProbeError, RUNTIME_PROMPT_REVISION):
            mcp_probe._validate_runtime_prompt(init)


if __name__ == "__main__":
    unittest.main()
