#!/usr/bin/env python3
"""Protocol and local-tool tests for the stdio MCP server."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def invoke(messages: list[dict]) -> tuple[list[dict], str]:
    wire = "".join(json.dumps(message, separators=(",", ":")) + "\n" for message in messages)
    process = subprocess.run(
        ["python3", "mcp_server.py"],
        input=wire,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
        timeout=30,
        check=True,
    )
    return [json.loads(line) for line in process.stdout.splitlines() if line], process.stderr


class McpServerTest(unittest.TestCase):
    def test_initialize_list_and_local_tools(self) -> None:
        responses, stderr = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "unittest", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "onshape_get_project_state",
                    "arguments": {"redact_ids": True},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "onshape_get_parameter_set",
                    "arguments": {"name": "preview"},
                },
            },
        ])
        self.assertEqual(stderr, "")
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(len(responses[1]["result"]["tools"]), 11)
        state = responses[2]["result"]["structuredContent"]["state"]
        self.assertIn("…", state["documentId"])
        parameters = responses[3]["result"]["structuredContent"]["parameters"]
        self.assertIs(parameters["detailedStrands"], False)
        self.assertNotIn("accessKey", json.dumps(responses))
        self.assertNotIn("secretKey", json.dumps(responses))

    def test_mutation_requires_explicit_confirmation(self) -> None:
        responses, stderr = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "onshape_upload_feature_studio",
                    "arguments": {"confirm_mutation": False},
                },
            }
        ])
        self.assertTrue(responses[0]["result"]["isError"])
        self.assertIn("confirm_mutation", responses[0]["result"]["content"][0]["text"])
        self.assertIn("ValueError", stderr)


if __name__ == "__main__":
    unittest.main()
