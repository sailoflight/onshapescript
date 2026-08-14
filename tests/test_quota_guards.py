#!/usr/bin/env python3
"""Offline unit tests for the quota-protection gates.

Covers the single-gate design in onshape_fs_mcp.budget (LIVE_API_ENABLED opt-in,
rate-limit hold, annual-quota preflight), the shared request builder's secret
redaction, the no-implicit-lookup resolver, zero-network dry runs, and the MCP
cost-metadata <-> gate consistency. No real Onshape API call is ever made.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_fs_mcp import budget as budget_module  # noqa: E402
from onshape_fs_mcp import client as client_module  # noqa: E402
from onshape_fs_mcp import operations  # noqa: E402


def fake_client(state: dict | None = None, usage: dict | None = None) -> client_module.OnshapeClient:
    """A client that never reads credentials or touches the network."""
    cl = object.__new__(client_module.OnshapeClient)
    cl.base_url = "https://cad.onshape.com"
    cl.authorization = "Bearer a-secret-access-token"
    cl.state = state if state is not None else {
        "documentId": "did",
        "workspaceId": "wid",
        "featureStudioId": "fsid",
        "partStudioId": "psid",
    }
    cl._usage = usage if usage is not None else {
        "consumed": 0,
        "calls": [],
        "lastRateLimitRemaining": None,
        "lastRetryAfter": None,
        "last402At": None,
    }
    return cl


def _now_utc() -> str:
    """A fresh element-mirror timestamp in the state file's format."""
    return operations.time.strftime("%Y-%m-%dT%H:%M:%SZ", operations.time.gmtime())


def invoke(messages: list[dict], live_flag: str) -> tuple[list[dict], str]:
    """Drive mcp_server.py over stdio with a forced LIVE_API_ENABLED value."""
    wire = "".join(json.dumps(message, separators=(",", ":")) + "\n" for message in messages)
    env = os.environ.copy()
    env["LIVE_API_ENABLED"] = live_flag
    process = subprocess.run(
        ["python3", "mcp_server.py"],
        input=wire,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
        env=env,
        timeout=30,
        check=True,
    )
    return [json.loads(line) for line in process.stdout.splitlines() if line], process.stderr


def pipeline_client() -> client_module.OnshapeClient:
    return fake_client(state={
        "documentId": "did",
        "workspaceId": "wid",
        "featureStudioId": "fsid",
        "partStudioId": "psid",
        "featureScriptFile": "examples/branch-cable-trophy/branchCableTrophyDisplay.fs",
    })


class RateLimitReasonTest(unittest.TestCase):
    def test_hold_detection_rules(self) -> None:
        # remaining 0 + Retry-After > 60s -> hold.
        self.assertIn("rate-limited", budget_module.rate_limit_reason(
            {"lastRateLimitRemaining": "0", "lastRetryAfter": "72910"}))
        # Short Retry-After or remaining above 0 -> no hold.
        self.assertIsNone(budget_module.rate_limit_reason(
            {"lastRateLimitRemaining": "0", "lastRetryAfter": "30"}))
        self.assertIsNone(budget_module.rate_limit_reason(
            {"lastRateLimitRemaining": "5", "lastRetryAfter": "999"}))
        self.assertIsNone(budget_module.rate_limit_reason(
            {"lastRateLimitRemaining": None, "lastRetryAfter": None}))

    def test_missing_ledger_is_no_hold(self) -> None:
        with mock.patch.object(client_module, "load_json", side_effect=FileNotFoundError):
            self.assertIsNone(budget_module.rate_limit_reason())


class DescribeRedactionTest(unittest.TestCase):
    def test_describe_builds_request_and_redacts_secret(self) -> None:
        cl = fake_client()
        described = cl.describe("POST", "/api/foo", {"a": 1}, {"q": "x y"})
        self.assertEqual(described["method"], "POST")
        self.assertIn("/api/foo?q=x+y", described["url"])
        self.assertEqual(described["headers"]["Authorization"], "<REDACTED>")
        self.assertEqual(described["body"], {"a": 1})
        self.assertNotIn("a-secret-access-token", json.dumps(described))


class LiveBlockerTest(unittest.TestCase):
    def test_flag_is_the_first_gate(self) -> None:
        # Unset/empty flag blocks even when the account would otherwise be fine.
        with mock.patch.dict(os.environ, {"LIVE_API_ENABLED": ""}):
            blocker = budget_module.live_blocker(3, "probe")
        self.assertIn("LIVE_API_ENABLED", blocker or "")

    def test_hold_then_preflight_when_enabled(self) -> None:
        with mock.patch.dict(os.environ, {"LIVE_API_ENABLED": "1"}):
            with mock.patch.object(
                budget_module, "rate_limit_reason", return_value="Onshape rate-limited: hold"
            ):
                cl = fake_client(state={"apiQuota": {"accountType": "professional"}})
                blocker = budget_module.live_blocker(3, "probe", client=cl)
        self.assertIn("rate-limited", blocker)

        with mock.patch.dict(os.environ, {"LIVE_API_ENABLED": "1"}):
            with mock.patch.object(budget_module, "rate_limit_reason", return_value=None):
                ok = fake_client(state={"apiQuota": {"accountType": "professional"}})
                self.assertIsNone(budget_module.live_blocker(3, "probe", client=ok))
                tight = fake_client(state={"apiQuota": {"accountType": "professional"}})
                tight._usage = {"consumed": 4999, "calls": []}  # only 1 call left
                blocker = budget_module.live_blocker(3, "probe", client=tight)
        self.assertIn("only 1 remain", blocker or "")


class BudgetGuardTest(unittest.TestCase):
    def test_disabled_hold_and_ok_paths(self) -> None:
        with mock.patch.dict(os.environ, {"LIVE_API_ENABLED": ""}):
            with self.assertRaises(budget_module.LiveApiDisabled):
                budget_module.BudgetGuard(10, "probe", client=fake_client())

        with mock.patch.dict(os.environ, {"LIVE_API_ENABLED": "1"}):
            held = fake_client()
            held._usage = {
                "consumed": 0, "calls": [],
                "lastRateLimitRemaining": "0", "lastRetryAfter": "72910",
            }
            with self.assertRaises(client_module.RateLimitedHold):
                budget_module.BudgetGuard(10, "probe", client=held)

            ok = fake_client(state={"apiQuota": {"accountType": "professional"}})
            guard = budget_module.BudgetGuard(10, "probe", client=ok)
            self.assertEqual(guard.remaining, 10)

            tight = fake_client(state={"apiQuota": {"accountType": "professional"}})
            tight._usage = {"consumed": 4950, "calls": []}  # 50 left, budget 60
            with self.assertRaises(budget_module.BudgetExceeded):
                budget_module.BudgetGuard(60, "too big", client=tight)


class ResolvePartStudioIdTest(unittest.TestCase):
    def test_never_walks_the_document(self) -> None:
        cl = pipeline_client()
        cl.request = mock.Mock(side_effect=AssertionError("resolve must not request"))
        self.assertEqual(operations.resolve_part_studio_id(cl, "explicit-id"),
                         ("did", "wid", "explicit-id"))
        # Falls back to the cached id only.
        self.assertEqual(operations.resolve_part_studio_id(cl, None), ("did", "wid", "psid"))
        cl.state.pop("partStudioId", None)
        with self.assertRaises(RuntimeError):
            operations.resolve_part_studio_id(cl, None)
        cl.request.assert_not_called()


class DryRunZeroNetworkTest(unittest.TestCase):
    def test_dry_runs_make_no_requests(self) -> None:
        cl = pipeline_client()
        cl.request = mock.Mock(side_effect=AssertionError("dry run must not request"))
        with mock.patch.object(operations, "save_state") as save:
            self.assertEqual(operations.upload_feature_studio(client=cl, dry_run=True)["estimatedRequests"], 3)
            self.assertEqual(operations.create_validation_part_studio(client=cl, dry_run=True)["estimatedRequests"], 1)
            self.assertEqual(
                operations.instantiate_feature(part_studio_id="psid", client=cl, dry_run=True)["estimatedRequests"],
                2,
            )
            run = operations.run_validation_pipeline(client=cl, dry_run=True)
            run_off = operations.run_validation_pipeline(client=cl, dry_run=True, render=False)
            save.assert_not_called()
        cl.request.assert_not_called()
        # The pipeline estimate must equal the sum of its steps, render on/off.
        self.assertEqual(run["estimatedRequests"], 13)
        self.assertEqual(run_off["estimatedRequests"], 8)

    def test_pipeline_estimate_matches_actual_calls(self) -> None:
        # upload:3 + create:1 + instantiate:1 (microversion threaded from upload)
        # + check_model:3 + render:5 = 13.
        self.assertEqual(operations.PIPELINE_ESTIMATE, {True: 13, False: 8})
        self.assertEqual(3 + 1 + 1 + 3 + 5, operations.PIPELINE_ESTIMATE[True])
        self.assertEqual(3 + 1 + 1 + 3, operations.PIPELINE_ESTIMATE[False])


class ElementCacheTest(unittest.TestCase):
    def test_list_prefers_cache_zero_network(self) -> None:
        cl = fake_client(state={
            "documentId": "did", "workspaceId": "wid",
            "featureStudioId": "fsid", "partStudioId": "psid",
            "elements": [{"id": "fsid", "name": "FS", "elementType": "FEATURE_STUDIO", "microversionId": "m1"}],
        })
        cl.request = mock.Mock(side_effect=AssertionError("cache hit must not request"))
        result = operations.list_document_elements(client=cl)
        self.assertEqual(result["source"], "cache")
        self.assertEqual(result["elements"][0]["microversionId"], "m1")
        cl.request.assert_not_called()

    def test_list_cold_cache_returns_empty_with_note(self) -> None:
        cl = fake_client()
        cl.request = mock.Mock(side_effect=AssertionError("cold cache must not request"))
        result = operations.list_document_elements(client=cl)
        self.assertEqual(result["source"], "cache")
        self.assertEqual(result["elements"], [])
        self.assertIn("refresh", result.get("note", ""))
        cl.request.assert_not_called()

    def test_list_refresh_writes_cache(self) -> None:
        cl = fake_client()
        cl.request = mock.Mock(return_value=[
            {"id": "fsid", "name": "FS", "elementType": "FEATURE_STUDIO", "microversionId": "m9"},
        ])
        with mock.patch.object(operations, "save_state") as save, \
             mock.patch.object(operations, "_read_state_file", return_value={}):
            result = operations.list_document_elements(client=cl, refresh=True)
        self.assertEqual(result["source"], "live")
        self.assertEqual(result["elements"][0]["microversionId"], "m9")
        save.assert_called_once()
        self.assertEqual(cl.state["elements"][0]["id"], "fsid")

    def test_instantiate_skips_elements_get_when_cached(self) -> None:
        cl = fake_client(state={
            "documentId": "did", "workspaceId": "wid",
            "featureStudioId": "fsid", "partStudioId": "psid",
            "elementsUpdatedAt": _now_utc(),
            "elements": [{"id": "fsid", "name": "FS", "elementType": "FEATURE_STUDIO", "microversionId": "m123"}],
        })
        cl.request = mock.Mock(return_value={
            "featureState": {"featureStatus": "OK"},
            "feature": {"featureId": "f1", "featureType": "branchCableTrophyDisplay", "namespace": "e fsid :: m m123"},
            "sourceMicroversion": "m123",
        })
        summary = operations.instantiate_feature(part_studio_id="psid", client=cl)
        self.assertEqual(summary["featureStatus"], "OK")
        # Only the POST feature call; no GET /elements for the microversion.
        self.assertEqual(cl.request.call_count, 1)
        self.assertIn("/features", cl.request.call_args[0][1])
        self.assertNotIn("/elements", cl.request.call_args[0][1])
        self.assertIn("m123", cl.request.call_args[0][2]["feature"]["namespace"])

    def test_instantiate_refetches_when_mirror_stale(self) -> None:
        # A cached microversion older than the freshness window must NOT be
        # trusted for a mutation: re-read the element list instead of pinning
        # the stale snapshot.
        cl = fake_client(state={
            "documentId": "did", "workspaceId": "wid",
            "featureStudioId": "fsid", "partStudioId": "psid",
            "elementsUpdatedAt": "2020-01-01T00:00:00Z",
            "elements": [{"id": "fsid", "name": "FS", "elementType": "FEATURE_STUDIO", "microversionId": "mSTALE"}],
        })
        cl.request = mock.Mock(side_effect=[
            [{"id": "fsid", "name": "FS", "elementType": "FEATURE_STUDIO", "microversionId": "mCURRENT"}],
            {
                "featureState": {"featureStatus": "OK"},
                "feature": {"featureId": "f1", "featureType": "branchCableTrophyDisplay", "namespace": "e fsid :: m mCURRENT"},
                "sourceMicroversion": "mCURRENT",
            },
        ])
        summary = operations.instantiate_feature(part_studio_id="psid", client=cl)
        self.assertEqual(summary["featureStatus"], "OK")
        # GET /elements first, then the POST feature call.
        self.assertEqual(cl.request.call_count, 2)
        self.assertIn("/elements", cl.request.call_args_list[0][0][1])
        # The POST namespaces to the freshly re-read microversion, not the cache.
        self.assertIn("mCURRENT", cl.request.call_args_list[1][0][2]["feature"]["namespace"])

    def test_instantiate_falls_back_to_get_when_cold(self) -> None:
        cl = fake_client()
        cl.request = mock.Mock(side_effect=AssertionError("dry run must not request"))
        dry = operations.instantiate_feature(part_studio_id="psid", client=cl, dry_run=True)
        self.assertEqual(dry["estimatedRequests"], 2)


class McpCostMetadataTest(unittest.TestCase):
    def test_live_tools_carry_consistent_cost_metadata(self) -> None:
        import mcp_server  # imported here: spawns no server, constructs no client

        by_name = {tool["name"]: tool for tool in mcp_server.TOOLS}
        live = {name for name, tool in by_name.items()
                if (tool.get("cost") or {}).get("network") == "live"}
        self.assertEqual(live, {
            "fs_check_version",
            "onshape_eval_featurescript",
            "onshape_list_document_elements",
            "onshape_get_feature_studio_status",
            "onshape_check_model",
            "onshape_render_preview",
            "onshape_upload_feature_studio",
            "onshape_create_validation_part_studio",
            "onshape_instantiate_feature",
            "onshape_run_validation_pipeline",
        })
        for name in live:
            cost = by_name[name]["cost"]
            self.assertGreater(cost["max_requests"], 0, name)
            self.assertLessEqual(cost["estimated_requests"], cost["max_requests"], name)
        for name, tool in by_name.items():
            cost = tool.get("cost")
            if cost and cost["network"] == "offline":
                self.assertEqual(cost["estimated_requests"], 0, name)
        # The pipeline cost entries must track the real operation count.
        pipe = by_name["onshape_run_validation_pipeline"]["cost"]
        self.assertEqual(pipe["estimated_requests"], operations.PIPELINE_ESTIMATE[False])
        self.assertEqual(pipe["max_requests"], operations.PIPELINE_ESTIMATE[True])
        # fs_check_version is live-capable (include_live / check_latest).
        self.assertEqual(by_name["fs_check_version"]["cost"]["network"], "live")
        self.assertEqual(by_name["fs_check_version"]["cost"]["max_requests"], 3)
        # fs_update_reference: offline default, at most 1 live call.
        self.assertEqual(by_name["fs_update_reference"]["cost"]["network"], "offline")
        self.assertEqual(by_name["fs_update_reference"]["cost"]["max_requests"], 1)


class McpLiveGateTest(unittest.TestCase):
    def test_live_tool_blocked_without_flag_zero_network(self) -> None:
        responses, _ = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "onshape_list_document_elements", "arguments": {"refresh": True}},
            },
        ], live_flag="")
        self.assertTrue(responses[0]["result"]["isError"])
        self.assertIn("LIVE_API_ENABLED", responses[0]["result"]["content"][0]["text"])

    def test_list_elements_cached_default_works_without_flag(self) -> None:
        # The cached (refresh=false) list is offline: it succeeds without the
        # live flag and makes no network request.
        responses, _ = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "onshape_list_document_elements", "arguments": {}},
            },
        ], live_flag="")
        result = responses[0]["result"]
        self.assertFalse(result.get("isError"))
        self.assertEqual(result["structuredContent"]["source"], "cache")

    def test_dry_run_still_works_while_live_disabled(self) -> None:
        responses, stderr = invoke([
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "onshape_upload_feature_studio",
                    "arguments": {"confirm_mutation": True, "dry_run": True},
                },
            },
        ], live_flag="")
        self.assertEqual(stderr, "")
        result = responses[0]["result"]
        self.assertFalse(result.get("isError"))
        content = result["structuredContent"]
        self.assertTrue(content["dryRun"])
        self.assertEqual(content["estimatedRequests"], 3)
        self.assertIn("<REDACTED>", result["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
