#!/usr/bin/env python3
"""Offline contracts for the REST-leg document variable table (issue #19).

Every shape asserted here is derived from the vendored OpenAPI
(``onshape_docs/reference/raw/onshape-api/openapi.json``, tag ``Variables``:
``BTVariableTableInfo``/``BTVariableInfo``/``BTVariableParams``/
``GBTVariableType``/``GBTElementType``). **None of it is a live capture**: the
real endpoint was never called while this landed — the Windows host was offline
and the account quota is scarce — so passing tests prove request construction,
validation, normalization and refusal behavior, NOT that Onshape accepts the
payload. The live acceptance is T9 in
``onshape_docs/verification/pending-live-verification-2026-10-01.json``.

No test here touches the network: ``urlopen`` is patched and the client is built
with ``object.__new__`` so no credentials file is read.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main.win.mcp import server  # noqa: E402
from onshape_rest_api_mode import client as client_module  # noqa: E402
from onshape_rest_api_mode import operations, variables  # noqa: E402

#: A spec-shaped getVariables response: an array of BTVariableTableInfo.
SPEC_SHAPED_TABLES = [
    {
        "variableStudioReference": {"elementId": "vs1", "name": "Variable Studio 1"},
        "variables": [
            {
                "name": "plateThickness",
                "type": "LENGTH",
                "expression": "3 mm",
                "value": "3.000 mm",
                "description": "shared wall thickness",
            },
            {"name": "holeCount", "type": "NUMBER", "expression": "4", "value": "4"},
        ],
    }
]


class _Response:
    """A urlopen stand-in carrying one JSON payload."""

    def __init__(self, payload: object) -> None:
        self.status = 200
        self.headers = {"content-type": "application/json"}
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def fake_client(
    state: dict | None = None, *, authorization: str | None = "Bearer a-secret-token"
) -> client_module.OnshapeClient:
    """A client with no credentials file and an in-memory ledger."""
    cl = object.__new__(client_module.OnshapeClient)
    cl.base_url = "https://cad.onshape.com"
    cl.authorization = authorization
    cl.state = {"documentId": "did", "workspaceId": "wid", **(state or {})}
    cl.attempted = 0
    cl.before_request = None
    cl.require_credentials = False
    cl.usage_path = Path("/nonexistent/api-usage.json")
    cl._usage = {
        "consumed": 0,
        "calls": [],
        "lastRateLimitRemaining": None,
        "lastRetryAfter": None,
        "last402At": None,
    }
    cl._record_usage = lambda *args, **kwargs: None
    return cl


def urlopen_recorder(payloads: list[object]):
    """Record every request and answer with `payloads` in order (last one repeats)."""
    calls: list[dict] = []

    def fake_urlopen(request, timeout=None):  # noqa: ANN001
        calls.append(
            {
                "method": request.method,
                "url": request.full_url,
                "body": json.loads(request.data.decode()) if request.data else None,
            }
        )
        index = min(len(calls) - 1, len(payloads) - 1)
        return _Response(payloads[index])

    return calls, fake_urlopen


LIVE = mock.patch.dict(os.environ, {"LIVE_API_ENABLED": "1"})
OFFLINE = mock.patch.dict(os.environ, {}, clear=False)


class PathAndValidationTest(unittest.TestCase):
    def test_path_addresses_a_workspace_or_a_version(self) -> None:
        self.assertEqual(
            variables.variables_path("d", "w", "e"),
            "/api/variables/d/d/w/w/e/e/variables",
        )
        self.assertEqual(
            variables.variables_path("d", "w", "e", version_id="v1"),
            "/api/variables/d/d/v/v1/e/e/variables",
        )

    def test_path_requires_the_ids_it_cannot_guess(self) -> None:
        with self.assertRaises(ValueError):
            variables.variables_path("", "w", "e")
        with self.assertRaises(ValueError):
            variables.variables_path("d", "w", "")
        with self.assertRaises(ValueError):
            variables.variables_path("d", "", "e")

    def test_validation_uppercases_the_type_and_keeps_the_expression(self) -> None:
        body = variables.validate_variables(
            [{"name": "plateThickness", "type": "length", "expression": "3 mm"}]
        )
        self.assertEqual(
            body, [{"name": "plateThickness", "type": "LENGTH", "expression": "3 mm"}]
        )

    def test_validation_refuses_malformed_rows_instead_of_dropping_them(self) -> None:
        cases = {
            "empty": [],
            "not-a-list": {"name": "a", "type": "NUMBER"},
            "missing-name": [{"type": "NUMBER", "expression": "1"}],
            "bad-name": [{"name": "1leading", "type": "NUMBER", "expression": "1"}],
            "bad-name-char": [{"name": "has space", "type": "NUMBER", "expression": "1"}],
            "missing-type": [{"name": "a", "expression": "1"}],
            "unknown-type": [{"name": "a", "type": "MASS", "expression": "1"}],
            "unknown-key": [{"name": "a", "type": "NUMBER", "value": "1"}],
            "no-expression": [{"name": "a", "type": "NUMBER"}],
            "bad-expression": [{"name": "a", "type": "NUMBER", "expression": 3}],
            "bad-description": [{"name": "a", "type": "NUMBER", "description": 3}],
            "not-an-object": ["a"],
        }
        for label, payload in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    variables.validate_variables(payload)

    def test_the_type_enum_matches_the_vendored_spec(self) -> None:
        spec = json.loads(
            (ROOT / "onshape_docs/reference/raw/onshape-api/openapi.json").read_text(
                encoding="utf-8"
            )
        )
        enum = spec["components"]["schemas"]["GBTVariableType"]["enum"]
        self.assertEqual(list(variables.VARIABLE_TYPES), enum)
        element_types = spec["components"]["schemas"]["GBTElementType"]["enum"]
        self.assertIn(variables.VARIABLE_STUDIO_ELEMENT_TYPE, element_types)


class NormalizationTest(unittest.TestCase):
    def test_spec_shaped_tables_are_normalized_with_counts(self) -> None:
        summary = variables.summarize_tables(SPEC_SHAPED_TABLES)
        self.assertEqual(summary["tableCount"], 1)
        self.assertEqual(summary["variableCount"], 2)
        first = summary["tables"][0]["variables"][0]
        self.assertEqual(first["name"], "plateThickness")
        self.assertEqual(first["type"], "LENGTH")
        self.assertEqual(first["expression"], "3 mm")
        self.assertEqual(first["value"], "3.000 mm")
        self.assertEqual(first["description"], "shared wall thickness")
        self.assertEqual(
            summary["tables"][0]["variableStudioReference"]["elementId"], "vs1"
        )

    def test_a_row_without_a_value_keeps_the_key_present(self) -> None:
        summary = variables.summarize_tables([{"variables": [{"name": "a", "type": "NUMBER"}]}])
        row = summary["tables"][0]["variables"][0]
        self.assertIsNone(row["value"])
        self.assertIn("value", row)

    def test_an_empty_studio_is_a_successful_read_of_nothing(self) -> None:
        for payload in ([], None, [{"variables": []}]):
            with self.subTest(payload=payload):
                summary = variables.summarize_tables(payload)
                self.assertEqual(summary["tableCount"], len(payload or []))
                self.assertEqual(summary["variableCount"], 0)

    def test_a_single_table_object_is_accepted(self) -> None:
        summary = variables.summarize_tables(SPEC_SHAPED_TABLES[0])
        self.assertEqual(summary["tableCount"], 1)
        self.assertEqual(summary["variableCount"], 2)

    def test_an_unexpected_shape_is_reported_not_crashed(self) -> None:
        summary = variables.summarize_tables("not-a-table")
        self.assertEqual(summary["tableCount"], 0)
        self.assertIn("unexpectedShape", summary)


class ElementResolutionTest(unittest.TestCase):
    def test_an_explicit_element_id_wins_over_the_cache(self) -> None:
        cl = fake_client({"elements": [{"id": "cached", "elementType": "VARIABLESTUDIO"}]})
        self.assertEqual(
            operations.resolve_variable_studio_id(cl, "explicit")[2:],
            ("explicit", "explicit"),
        )

    def test_a_single_cached_variable_studio_is_used(self) -> None:
        cl = fake_client({
            "elements": [
                {"id": "ps", "elementType": "PARTSTUDIO"},
                {"id": "vs1", "elementType": "VARIABLESTUDIO"},
            ]
        })
        did, wid, eid, source = operations.resolve_variable_studio_id(cl)
        self.assertEqual((did, wid, eid, source), ("did", "wid", "vs1", "cache"))

    def test_no_cached_studio_refuses_and_names_the_alternative(self) -> None:
        cl = fake_client({"elements": [{"id": "ps", "elementType": "PARTSTUDIO"}]})
        with self.assertRaises(RuntimeError) as caught:
            operations.resolve_variable_studio_id(cl)
        message = str(caught.exception)
        self.assertIn("element_id", message)
        self.assertIn("onshape_list_document_elements", message)

    def test_an_ambiguous_cache_refuses_and_lists_the_candidates(self) -> None:
        cl = fake_client({
            "elements": [
                {"id": "vs1", "name": "A", "elementType": "VARIABLESTUDIO"},
                {"id": "vs2", "name": "B", "elementType": "VARIABLESTUDIO"},
            ]
        })
        with self.assertRaises(RuntimeError) as caught:
            operations.resolve_variable_studio_id(cl)
        self.assertIn("pass element_id", str(caught.exception))
        self.assertIn("vs1", str(caught.exception))
        self.assertIn("vs2", str(caught.exception))


class GetVariablesTest(unittest.TestCase):
    def test_one_get_with_the_spec_query_returns_normalized_tables(self) -> None:
        cl = fake_client()
        calls, fake = urlopen_recorder([SPEC_SHAPED_TABLES])
        with LIVE, mock.patch.object(client_module.urllib.request, "urlopen", fake):
            result = operations.get_variables(element_id="vs1", client=cl)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["method"], "GET")
        self.assertEqual(
            calls[0]["url"],
            "https://cad.onshape.com/api/variables/d/did/w/wid/e/vs1/variables"
            "?includeValuesAndReferencedVariables=True",
        )
        self.assertIsNone(calls[0]["body"])
        self.assertEqual(result["requestCount"], 1)
        self.assertEqual(result["variableCount"], 2)
        self.assertEqual(result["elementSource"], "explicit")
        self.assertEqual(result["documentId"], "did")
        self.assertEqual(result["workspaceId"], "wid")

    def test_include_values_false_omits_the_query(self) -> None:
        calls, fake = urlopen_recorder([SPEC_SHAPED_TABLES])
        with LIVE, mock.patch.object(client_module.urllib.request, "urlopen", fake):
            operations.get_variables(
                element_id="vs1", include_values=False, client=fake_client()
            )
        self.assertEqual(
            calls[0]["url"],
            "https://cad.onshape.com/api/variables/d/did/w/wid/e/vs1/variables",
        )

    def test_a_version_read_addresses_v_not_w(self) -> None:
        calls, fake = urlopen_recorder([SPEC_SHAPED_TABLES])
        with LIVE, mock.patch.object(client_module.urllib.request, "urlopen", fake):
            result = operations.get_variables(
                element_id="vs1", version_id="ver9", client=fake_client()
            )
        self.assertIn("/d/did/v/ver9/e/vs1/variables", calls[0]["url"])
        self.assertEqual(result["versionId"], "ver9")
        self.assertIsNone(result["workspaceId"])

    def test_a_disabled_live_flag_refuses_before_any_request(self) -> None:
        calls, fake = urlopen_recorder([SPEC_SHAPED_TABLES])
        with mock.patch.object(client_module.urllib.request, "urlopen", fake):
            with self.assertRaises(client_module.LiveApiDisabled):
                operations.get_variables(element_id="vs1", client=fake_client())
        self.assertEqual(calls, [])


class SetVariablesTest(unittest.TestCase):
    ROWS = [{"name": "plateThickness", "type": "LENGTH", "expression": "3 mm"}]

    def test_dry_run_needs_no_credentials_and_sends_nothing(self) -> None:
        cl = fake_client(authorization=None)
        calls, fake = urlopen_recorder([SPEC_SHAPED_TABLES])
        with mock.patch.object(client_module.urllib.request, "urlopen", fake):
            plan = operations.set_variables(
                self.ROWS, element_id="vs1", client=cl, dry_run=True
            )
        self.assertEqual(calls, [])
        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["estimatedRequests"], 1)
        described = plan["requests"][0]
        self.assertEqual(described["method"], "POST")
        self.assertIn("/api/variables/d/did/w/wid/e/vs1/variables", described["url"])
        self.assertEqual(described["body"], self.ROWS)
        self.assertNotIn("Bearer", json.dumps(described))

    def test_dry_run_with_readback_plans_both_requests(self) -> None:
        plan = operations.set_variables(
            self.ROWS, element_id="vs1", client=fake_client(), dry_run=True,
            verify_readback=True,
        )
        self.assertEqual(plan["estimatedRequests"], 2)
        self.assertEqual([r["method"] for r in plan["requests"]], ["POST", "GET"])

    def test_the_post_is_sent_once_and_never_retried(self) -> None:
        cl = fake_client()
        calls, fake = urlopen_recorder([{"httpStatus": 200}])
        with LIVE, mock.patch.object(client_module.urllib.request, "urlopen", fake):
            result = operations.set_variables(self.ROWS, element_id="vs1", client=cl)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["method"], "POST")
        self.assertEqual(calls[0]["body"], self.ROWS)
        self.assertEqual(result["requestCount"], 1)
        self.assertEqual(result["assigned"], self.ROWS)
        # The spec types this response only as a generic object, and the tool says so.
        self.assertFalse(result["responseDocumented"])
        self.assertNotIn("verified", result)

    def test_readback_verifies_matching_rows(self) -> None:
        calls, fake = urlopen_recorder([{"httpStatus": 200}, SPEC_SHAPED_TABLES])
        with LIVE, mock.patch.object(client_module.urllib.request, "urlopen", fake):
            result = operations.set_variables(
                [{"name": "plateThickness", "type": "LENGTH", "expression": "3 mm"}],
                element_id="vs1",
                client=fake_client(),
                verify_readback=True,
            )
        self.assertEqual([call["method"] for call in calls], ["POST", "GET"])
        self.assertEqual(result["requestCount"], 2)
        self.assertTrue(result["verified"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["mismatched"], [])

    def test_readback_reports_a_missing_and_a_mismatched_row(self) -> None:
        calls, fake = urlopen_recorder([{"httpStatus": 200}, SPEC_SHAPED_TABLES])
        with LIVE, mock.patch.object(client_module.urllib.request, "urlopen", fake):
            result = operations.set_variables(
                [
                    {"name": "plateThickness", "type": "LENGTH", "expression": "4 mm"},
                    {"name": "neverWritten", "type": "NUMBER", "expression": "1"},
                ],
                element_id="vs1",
                client=fake_client(),
                verify_readback=True,
            )
        self.assertFalse(result["verified"])
        self.assertEqual(result["missing"], ["neverWritten"])
        self.assertEqual(
            result["mismatched"],
            [{"name": "plateThickness", "expected": "4 mm", "readBack": "3 mm"}],
        )

    def test_a_malformed_row_is_refused_before_any_request(self) -> None:
        calls, fake = urlopen_recorder([{"httpStatus": 200}])
        with LIVE, mock.patch.object(client_module.urllib.request, "urlopen", fake):
            with self.assertRaises(ValueError):
                operations.set_variables(
                    [{"name": "bad name", "type": "NUMBER", "expression": "1"}],
                    element_id="vs1",
                    client=fake_client(),
                )
        self.assertEqual(calls, [])

    def test_a_disabled_live_flag_refuses_before_any_request(self) -> None:
        calls, fake = urlopen_recorder([{"httpStatus": 200}])
        with mock.patch.object(client_module.urllib.request, "urlopen", fake):
            with self.assertRaises(client_module.LiveApiDisabled):
                operations.set_variables(self.ROWS, element_id="vs1", client=fake_client())
        self.assertEqual(calls, [])


class RegisteredToolTest(unittest.TestCase):
    def tool(self, name: str) -> dict:
        return next(entry for entry in server.TOOLS if entry["name"] == name)

    def test_get_variables_is_registered_as_a_read_only_live_tool(self) -> None:
        entry = self.tool("onshape_get_variables")
        self.assertEqual(entry["cost"]["network"], "live")
        self.assertFalse(entry["cost"]["mutating"])
        self.assertEqual(entry["cost"]["max_requests"], 1)
        self.assertTrue(entry["annotations"]["readOnlyHint"])

    def test_set_variables_is_registered_as_mutating_and_needs_confirmation(self) -> None:
        entry = self.tool("onshape_set_variables")
        self.assertEqual(entry["cost"]["network"], "live")
        self.assertTrue(entry["cost"]["mutating"])
        self.assertEqual(entry["cost"]["max_requests"], 2)
        self.assertFalse(entry["annotations"]["readOnlyHint"])
        self.assertIn("confirm_mutation", entry["inputSchema"]["properties"])
        self.assertEqual(
            entry["inputSchema"]["properties"]["variables"]["items"]["properties"]["type"]["enum"],
            list(variables.VARIABLE_TYPES),
        )

    def test_the_handlers_are_wired(self) -> None:
        for name in ("onshape_get_variables", "onshape_set_variables"):
            with self.subTest(tool=name):
                self.assertIn(name, server.HANDLERS)

    def test_set_variables_requires_confirm_mutation(self) -> None:
        with self.assertRaises(ValueError):
            server.HANDLERS["onshape_set_variables"]({"variables": [{"name": "a", "type": "NUMBER", "expression": "1"}]})

    def test_the_read_handler_refuses_while_live_is_disabled(self) -> None:
        # The live gate is the first thing the handler does, so a caller without
        # the explicit opt-in gets the reason rather than a credentials error.
        with self.assertRaises(ValueError) as caught:
            server.HANDLERS["onshape_get_variables"]({})
        self.assertIn("LIVE_API_ENABLED", str(caught.exception))

    def test_the_handler_passes_the_arguments_through(self) -> None:
        sentinel = {"elementSource": "explicit", "tables": []}
        with mock.patch.object(server, "_require_live") as gate, mock.patch.object(
            server, "get_variables", return_value=sentinel
        ) as called:
            result = server.HANDLERS["onshape_get_variables"](
                {"element_id": "vs1", "version_id": "v2", "include_values": False}
            )
        self.assertEqual(result, sentinel)
        gate.assert_called_once_with(1, "get_variables")
        called.assert_called_once_with(element_id="vs1", version_id="v2", include_values=False)

    def test_the_write_handler_gates_on_the_planned_request_count(self) -> None:
        """The quota estimate comes from the dry-run plan, not a hand-written number."""
        with mock.patch.object(server, "_require_live") as gate, mock.patch.object(
            server, "set_variables", side_effect=[
                {"dryRun": True, "estimatedRequests": 2, "requests": []},
                {"source": "live"},
            ]
        ) as called:
            result = server.HANDLERS["onshape_set_variables"](
                {
                    "variables": [{"name": "a", "type": "NUMBER", "expression": "1"}],
                    "element_id": "vs1",
                    "verify_readback": True,
                    "confirm_mutation": True,
                }
            )
        self.assertEqual(result, {"source": "live"})
        gate.assert_called_once_with(2, "set_variables")
        self.assertEqual(called.call_count, 2)
        self.assertTrue(called.call_args.kwargs["verify_readback"])

    def test_the_write_handler_returns_the_dry_run_without_gating_live(self) -> None:
        with mock.patch.object(server, "_require_live") as gate, mock.patch.object(
            server,
            "set_variables",
            return_value={"dryRun": True, "estimatedRequests": 1, "requests": []},
        ):
            result = server.HANDLERS["onshape_set_variables"](
                {
                    "variables": [{"name": "a", "type": "NUMBER", "expression": "1"}],
                    "confirm_mutation": True,
                    "dry_run": True,
                }
            )
        self.assertTrue(result["dryRun"])
        gate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
