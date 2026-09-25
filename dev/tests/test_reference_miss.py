#!/usr/bin/env python3
"""Reference-miss structure and reference-schema plumbing tests for the MCP surface.

Everything here is offline: no browser launch and no Onshape REST request. A
``ReferenceMiss`` is a reference-layer ``ValueError`` that carries near-miss
``suggestions`` and a ``nextCall`` hint. The JSON-RPC boundary must preserve that
structure as ``error.data`` instead of flattening it into the message, while a
plain ``ValueError`` keeps the old flattened shape with no ``data``.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main.win.mcp import server  # noqa: E402
from mcp_main.win.mcp.tool_views import ToolViewState  # noqa: E402
from onshape_docs.query.fs_reference import ReferenceMiss  # noqa: E402


def _a_miss() -> ReferenceMiss:
    return ReferenceMiss(
        "No function named 'extrde' in module 'GEOMETRY'.",
        name="extrde",
        kind="function",
        module="GEOMETRY",
        suggestions=[{"name": "extrude", "module": "GEOMETRY", "kind": "function"}],
        nextCall='fs_search(query="extrude")',
    )


def _connection() -> server.McpConnection:
    # static lists the whole registry, so the schema assertions read the exact
    # advertised shape without depending on a view profile.
    return server.McpConnection(
        ToolViewState(tools=server.TOOLS, mode="static", profile="all")
    )


class ReferenceMissBoundaryTest(unittest.TestCase):
    def test_reference_miss_becomes_a_jsonrpc_error_with_structured_data(self) -> None:
        miss = _a_miss()

        def raising(_arguments: dict) -> dict:
            raise miss

        with mock.patch.dict(server.HANDLERS, {"fs_get_function": raising}):
            response = _connection().dispatch_messages({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "fs_get_function", "arguments": {"name": "extrde"}},
            })[0]

        self.assertIn("error", response)
        self.assertNotIn("result", response)
        error = response["error"]
        # The code and the message are unchanged; only data is added.
        self.assertEqual(error["code"], -32602)
        self.assertEqual(
            error["message"], "No function named 'extrde' in module 'GEOMETRY'."
        )
        data = error["data"]
        self.assertEqual(
            data["suggestions"],
            [{"name": "extrude", "module": "GEOMETRY", "kind": "function"}],
        )
        self.assertEqual(data["nextCall"], 'fs_search(query="extrude")')

    def test_a_real_reference_miss_reaches_the_boundary_with_data(self) -> None:
        # End to end through the real handler, so the whole chain is pinned:
        # fs_get_function raises, tool_result passes it through, the connection
        # boundary attaches error.data. Offline and local.
        response = _connection().dispatch_messages({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "fs_get_function", "arguments": {"name": "opCylinder"}},
        })[0]
        self.assertIn("error", response)
        error = response["error"]
        self.assertEqual(error["code"], -32602)
        self.assertTrue(error["message"].startswith("No function named 'opCylinder'"))
        data = error["data"]
        self.assertIn(
            {"name": "cylinder", "module": "surfaceGeometry.fs", "kind": "function"},
            data["suggestions"],
        )
        self.assertEqual(data["nextCall"], 'fs_search(query="cylinder")')

    def test_a_plain_value_error_keeps_the_flattened_shape_without_data(self) -> None:
        view = ToolViewState(tools=server.TOOLS, mode="static", profile="all")
        connection = server.McpConnection(view)
        with mock.patch.object(view, "apply", side_effect=ValueError("plain refusal")):
            response = connection.dispatch_messages({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "mcp_tool_view", "arguments": {"action": "set"}},
            })[0]
        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(response["error"]["message"], "plain refusal")
        self.assertNotIn("data", response["error"])

    def test_the_boundary_helper_is_silent_for_an_ordinary_value_error(self) -> None:
        self.assertIsNone(
            server._reference_miss_error_data(ValueError("No function named 'x'"))
        )

    def test_the_boundary_helper_reports_the_documented_attributes(self) -> None:
        data = server._reference_miss_error_data(_a_miss())
        self.assertEqual(
            data["suggestions"],
            [{"name": "extrude", "module": "GEOMETRY", "kind": "function"}],
        )
        self.assertEqual(data["nextCall"], 'fs_search(query="extrude")')


class ReferenceSchemaTest(unittest.TestCase):
    def by_name(self) -> dict:
        listed = _connection().dispatch_messages({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        })[0]["result"]
        return {tool["name"]: tool for tool in listed["tools"]}

    def test_fs_get_function_passes_full_through_to_the_reference(self) -> None:
        from onshape_docs.query import fs_reference

        with mock.patch.object(fs_reference, "get_function",
                               return_value={"name": "x"}) as get_function:
            response = _connection().dispatch_messages({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "fs_get_function",
                    "arguments": {"name": "x", "full": True},
                },
            })[0]
        self.assertIn("result", response)
        self.assertIs(get_function.call_args.kwargs["full"], True)

    def test_fs_get_function_defaults_full_to_false(self) -> None:
        from onshape_docs.query import fs_reference

        with mock.patch.object(fs_reference, "get_function",
                               return_value={"name": "x"}) as get_function:
            _connection().dispatch_messages({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "fs_get_function", "arguments": {"name": "x"}},
            })
        self.assertIs(get_function.call_args.kwargs["full"], False)

    def test_fs_get_function_full_restores_a_truncated_description(self) -> None:
        # The reference decides which entries exceed its default bound; find one
        # dynamically so the assertion survives a reference refresh.
        from onshape_docs.query import fs_reference

        truncated_name = ""
        for entry in fs_reference.list_functions(limit=500):
            name = entry["name"]
            try:
                detail = fs_reference.get_function(name=name)
            except ValueError:
                continue
            if detail.get("descriptionTruncated") or "descriptionTruncated" in str(detail):
                truncated_name = name
                break
        self.assertTrue(truncated_name, "the reference exposed no truncated entry")

        def structure(full: bool) -> dict:
            arguments = {"name": truncated_name}
            if full:
                arguments["full"] = True
            return _connection().dispatch_messages({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "fs_get_function", "arguments": arguments},
            })[0]["result"]["structuredContent"]

        default = structure(full=False)
        complete = structure(full=True)
        self.assertIn("descriptionTruncated", json.dumps(default))
        self.assertNotIn("descriptionTruncated", json.dumps(complete))

    def test_fs_get_function_schema_exposes_full(self) -> None:
        tool = self.by_name()["fs_get_function"]
        full = tool["inputSchema"]["properties"]["full"]
        self.assertEqual(full["type"], "boolean")
        self.assertFalse(full["default"])
        self.assertIn("descriptionTruncated", full["description"])
        self.assertIn("full=true", tool["description"])


if __name__ == "__main__":
    unittest.main()
