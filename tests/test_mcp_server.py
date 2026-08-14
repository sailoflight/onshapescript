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
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "onshape_api_quota",
                    "arguments": {},
                },
            },
        ])
        self.assertEqual(stderr, "")
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(len(responses[1]["result"]["tools"]), 28)
        state = responses[2]["result"]["structuredContent"]["state"]
        self.assertIn("…", state["documentId"])
        parameters = responses[3]["result"]["structuredContent"]["parameters"]
        self.assertIs(parameters["detailedStrands"], False)
        quota = responses[4]["result"]["structuredContent"]["quota"]
        self.assertIn("configured", quota)
        self.assertIn("consumed", quota)
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
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "fs_quick_reference",
                    "arguments": {},
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
        quick = responses[4]["result"]["structuredContent"]
        self.assertTrue(quick["text"].startswith("# FeatureScript quick reference"))

    def test_onshape_api_reference_tools(self) -> None:
        responses, stderr = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "onshape_api_list_tags",
                    "arguments": {},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "onshape_api_search",
                    "arguments": {"query": "list document elements", "limit": 3},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "onshape_api_endpoint",
                    "arguments": {
                        "path": "/documents/d/{did}/{wvm}/{wvmid}/elements",
                        "method": "get",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "onshape_api_schema",
                    "arguments": {"name": "BTDocumentElementInfo"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "onshape_api_endpoint",
                    "arguments": {
                        "path": "/partstudios/d/{did}/{wvm}/{wvmid}/e/{eid}/features",
                        "method": "post",
                    },
                },
            },
        ])
        self.assertEqual(stderr, "")
        tags = responses[0]["result"]["structuredContent"]
        self.assertEqual(tags["count"], 42)
        self.assertTrue(tags["specVersion"])
        search = responses[1]["result"]["structuredContent"]["results"]
        self.assertTrue(search)
        self.assertIn("getElementsInDocument", {r["operationId"] for r in search})
        endpoint = responses[2]["result"]["structuredContent"]
        self.assertEqual(endpoint["method"], "GET")
        self.assertEqual(endpoint["operationId"], "getElementsInDocument")
        self.assertTrue(endpoint["parameters"])
        schema = responses[3]["result"]["structuredContent"]
        self.assertEqual(schema["name"], "BTDocumentElementInfo")
        self.assertEqual(schema["type"], "object")
        self.assertTrue(schema["properties"])
        post = responses[4]["result"]["structuredContent"]
        self.assertEqual(post["method"], "POST")
        self.assertEqual(post["operationId"], "addPartStudioFeature")
        self.assertTrue(post["security"])
        self.assertIn("schemaRef", post["requestBody"])

    def test_check_version_reports_rest_spec_version(self) -> None:
        responses, stderr = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "fs_check_version",
                    "arguments": {},
                },
            },
        ])
        self.assertEqual(stderr, "")
        content = responses[0]["result"]["structuredContent"]
        rest = content["onshapeApiSpecVersion"]
        self.assertEqual(rest["status"] if isinstance(rest, dict) and "status" in rest else None, None)
        self.assertTrue(rest["specVersion"])

    def test_onshape_api_auth_and_error_codes(self) -> None:
        responses, stderr = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "onshape_api_auth", "arguments": {}},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "onshape_api_auth",
                    "arguments": {"section": "3: Exchange the code for an access token"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "onshape_api_error_codes", "arguments": {}},
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "onshape_api_error_codes",
                    "arguments": {"status": 429},
                },
            },
        ])
        self.assertEqual(stderr, "")
        auth = responses[0]["result"]["structuredContent"]
        self.assertEqual(len(auth["oauthWorkflowSteps"]), 6)
        self.assertTrue(auth["apiKeySteps"])
        section = responses[1]["result"]["structuredContent"]
        self.assertEqual(section["title"], "3: Exchange the code for an access token")
        self.assertTrue(section["text"])
        codes = responses[2]["result"]["structuredContent"]
        self.assertGreaterEqual(codes["count"], 16)
        by_code = {c["code"]: c for c in codes["errorCodes"]}
        self.assertEqual(by_code[429]["name"], "Too Many Requests")
        self.assertEqual(by_code[429]["category"], "Client Error (4xx)")
        single = responses[3]["result"]["structuredContent"]
        self.assertEqual(single["count"], 1)
        self.assertEqual(single["errorCodes"][0]["code"], 429)

    def test_api_quota_accounting_and_preflight(self) -> None:
        from pathlib import Path
        import tempfile
        from onshape_fs_mcp import client as client_module
        from onshape_fs_mcp import operations

        # Passive ledger: 2xx counts, 4xx/402 do not; headers captured.
        tmp = Path(tempfile.mkdtemp()) / "usage.json"
        cl = object.__new__(client_module.OnshapeClient)
        cl.usage_path = tmp
        cl._usage = cl._load_usage()
        cl._record_usage("GET", "/api/foo", 200, {"x-rate-limit-remaining": "4998"})
        cl._record_usage("GET", "/api/foo", 404, {})
        cl._record_usage("GET", "/api/foo", 402, {})
        self.assertEqual(cl._usage["consumed"], 1)
        self.assertEqual(cl._usage["lastRateLimitRemaining"], "4998")
        self.assertTrue(cl._usage["last402At"])
        self.assertEqual(len(cl._usage["calls"]), 3)

        # Configured budget: preflight blocks when the run would exhaust it.
        cl2 = object.__new__(client_module.OnshapeClient)
        cl2.state = {"apiQuota": {"accountType": "professional"}}
        cl2._usage = {"consumed": 4990, "calls": []}
        usage = operations.api_usage(cl2)
        self.assertTrue(usage["configured"])
        self.assertEqual(usage["annualLimit"], 5000)
        self.assertEqual(usage["remaining"], 10)
        self.assertEqual(usage["estimatedPipelineRuns"]["withRender"], 0)
        pre = operations.preflight_run(client=cl2)
        self.assertFalse(pre["canProceed"])
        self.assertIn("but only 10 remain", pre["blockedReason"])

        # Baseline seeding: alreadyConsumed (real UI usage) is added to the
        # passive ledger, so consumed = baseline + ledger.
        cl4 = object.__new__(client_module.OnshapeClient)
        cl4.state = {"apiQuota": {"accountType": "standard", "alreadyConsumed": 119}}
        cl4._usage = {"consumed": 25, "calls": []}
        usage4 = operations.api_usage(cl4)
        self.assertEqual(usage4["annualLimit"], 2500)
        self.assertEqual(usage4["baselineConsumed"], 119)
        self.assertEqual(usage4["ledgerConsumed"], 25)
        self.assertEqual(usage4["consumed"], 144)
        self.assertEqual(usage4["remaining"], 2356)

        # Unconfigured: no annual budget -> proceed, with a note.
        cl3 = object.__new__(client_module.OnshapeClient)
        cl3.state = {"apiQuota": {}}
        cl3._usage = {"consumed": 0, "calls": []}
        pre3 = operations.preflight_run(client=cl3)
        self.assertTrue(pre3["canProceed"])
        self.assertIn("No annual quota configured", pre3["details"]["note"])

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
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "fs_update_reference",
                    "arguments": {"confirm_mutation": False},
                },
            },
        ])
        for response in responses:
            self.assertTrue(response["result"]["isError"])
            self.assertIn("confirm_mutation", response["result"]["content"][0]["text"])
        self.assertIn("ValueError", stderr)


if __name__ == "__main__":
    unittest.main()
