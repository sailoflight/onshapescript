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
        self.assertEqual(len(responses[1]["result"]["tools"]), 19)
        state = responses[2]["result"]["structuredContent"]["state"]
        self.assertIn("…", state["documentId"])
        parameters = responses[3]["result"]["structuredContent"]["parameters"]
        self.assertIs(parameters["detailedStrands"], False)
        self.assertNotIn("accessKey", json.dumps(responses))
        self.assertNotIn("secretKey", json.dumps(responses))

    def test_check_version_reports_docs_behind(self) -> None:
        responses, stderr = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "fs_check_version",
                    "arguments": {"target": "9999.0"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "fs_check_version",
                    "arguments": {},
                },
            },
        ])
        self.assertEqual(stderr, "")
        behind = responses[0]["result"]["structuredContent"]
        self.assertEqual(behind["status"], "docs-behind")
        self.assertTrue(behind["warnings"])
        self.assertTrue(behind["referenceHealth"]["indexConsistent"])
        current = responses[1]["result"]["structuredContent"]
        self.assertEqual(current["status"], "current")
        self.assertGreater(current["vendoredVersion"], 0)

    def test_feature_script_reference_tools(self) -> None:
        responses, stderr = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "fs_get_function",
                    "arguments": {"name": "opExtrude"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "fs_get_type",
                    "arguments": {"name": "BoundingType"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "fs_search",
                    "arguments": {"query": "sketch region", "limit": 3},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "fs_list_modules",
                    "arguments": {"category": "Math"},
                },
            },
        ])
        self.assertEqual(stderr, "")
        op = responses[0]["result"]["structuredContent"]
        self.assertEqual(op["name"], "opExtrude")
        self.assertEqual(op["module"], "geomOperations.fs")
        self.assertIn("context is Context", op["signature"])
        self.assertTrue(op["parameters"])
        bounding = responses[1]["result"]["structuredContent"]
        self.assertEqual(bounding["kind"], "enum")
        self.assertTrue(bounding["values"])
        search = responses[2]["result"]["structuredContent"]["results"]
        self.assertTrue(search)
        self.assertTrue(all("score" in result for result in search))
        modules = responses[3]["result"]["structuredContent"]["modules"]
        self.assertTrue(modules)
        self.assertTrue(all(m["category"] == "Math" for m in modules))

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
