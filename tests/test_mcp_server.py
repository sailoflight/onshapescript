#!/usr/bin/env python3
"""Protocol and local-tool tests for the stdio MCP server."""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

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
        tools = responses[1]["result"]["tools"]
        self.assertEqual(len(tools), 32)
        self.assertIn("onshape_eval_featurescript", {t["name"] for t in tools})
        self.assertIn("docs_list", {t["name"] for t in tools})
        self.assertIn("docs_section", {t["name"] for t in tools})
        self.assertIn("docs_search", {t["name"] for t in tools})
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
        # Vendored 2960 is behind the observed real Feature Studio version
        # (3029), now known FOR FREE from cached workflow responses.
        self.assertEqual(current["status"], "docs-behind")
        self.assertTrue(current["warnings"])
        self.assertGreater(current["vendoredVersion"], 0)
        # Free last-observed version: seeded from real workflow responses (3029
        # declared, 3044 deployed) — reported with zero API calls.
        observed = current["lastObservedServerVersion"]
        self.assertEqual(observed.get("languageVersion"), 3029)
        self.assertEqual(observed.get("libraryVersion"), 3044)

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

    def test_project_docs_tools(self) -> None:
        responses, stderr = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "docs_list", "arguments": {}},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "docs_section",
                    "arguments": {"page": "mcp-server", "section": "Mutating tools"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "docs_search",
                    "arguments": {"query": "quota preflight", "limit": 5},
                },
            },
        ])
        self.assertEqual(stderr, "")
        listed = responses[0]["result"]["structuredContent"]
        self.assertGreater(listed["count"], 10)
        pages = {p["page"] for p in listed["pages"]}
        self.assertIn("mcp-server", pages)
        self.assertIn("llm-experience-fs", pages)
        self.assertTrue(all("sections" in p for p in listed["pages"]))
        section = responses[1]["result"]["structuredContent"]
        self.assertEqual(section["page"], "mcp-server")
        self.assertEqual(section["section"], "Mutating tools")
        self.assertIn("confirm_mutation", section["text"])
        search = responses[2]["result"]["structuredContent"]
        self.assertTrue(search["results"])
        self.assertTrue(all("snippet" in r for r in search["results"]))

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

    @mock.patch.dict(os.environ, {"LIVE_API_ENABLED": "1"})
    def test_budget_guard_preflights_and_tracks_spend(self) -> None:
        from onshape_fs_mcp import budget as budget_module
        from onshape_fs_mcp import client as client_module

        # Preflight gate: a per-run budget exceeding remaining annual quota blocks.
        cl = object.__new__(client_module.OnshapeClient)
        cl.state = {"apiQuota": {"accountType": "professional"}}  # annual 5000
        cl._usage = {"consumed": 4950, "calls": []}               # 50 left
        with self.assertRaises(budget_module.BudgetExceeded):
            budget_module.BudgetGuard(60, "too big", client=cl)

        # Ledger accounting: spend tracks the passive ledger, not a guess.
        cl2 = object.__new__(client_module.OnshapeClient)
        cl2.state = {"apiQuota": {"accountType": "professional"}}
        cl2._usage = {"consumed": 4900, "calls": []}              # 100 left, budget 20
        guard = budget_module.BudgetGuard(20, "tracked run", client=cl2)
        self.assertFalse(guard.exceeded())
        self.assertEqual(guard.remaining, 20)
        cl2._usage["consumed"] += 8                               # simulate 8 calls
        self.assertEqual(guard.spent, 8)
        self.assertEqual(guard.remaining, 12)
        self.assertFalse(guard.exceeded())
        cl2._usage["consumed"] += 12                              # hit the ceiling
        self.assertTrue(guard.exceeded())
        self.assertEqual(guard.remaining, 0)
        self.assertEqual(guard.summary()["annualRemaining"], 100)

    def test_record_observed_version_writes_only_on_change(self) -> None:
        import unittest.mock
        from onshape_fs_mcp import client as client_module
        from onshape_fs_mcp import operations

        cl = object.__new__(client_module.OnshapeClient)
        cl.state = {"observedServerVersion": {}}
        with unittest.mock.patch.object(operations, "save_state") as save:
            operations.record_observed_version(
                language_version=3029, library_version=3044, client=cl
            )
            save.assert_called_once()
        self.assertEqual(cl.state["observedServerVersion"], {
            "languageVersion": 3029, "libraryVersion": 3044,
        })
        # No change -> no write.
        with unittest.mock.patch.object(operations, "save_state") as save:
            operations.record_observed_version(
                language_version=3029, library_version=3044, client=cl
            )
            save.assert_not_called()

    def test_eval_requires_script_before_any_network(self) -> None:
        responses, stderr = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "onshape_eval_featurescript",
                    "arguments": {},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "onshape_eval_featurescript",
                    "arguments": {"script": "   "},
                },
            },
        ])
        for response in responses:
            self.assertTrue(response["result"]["isError"])
            self.assertIn("script must be a non-empty string",
                          response["result"]["content"][0]["text"])

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
