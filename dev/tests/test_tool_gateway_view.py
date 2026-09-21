#!/usr/bin/env python3
"""Gate for the `gateway` exposure mode (roadmap G5, token compression).

The promise of this mode is narrow and must stay measurable:

* the advertised surface collapses to a fixed, tiny set (`mcp_tool_catalog` plus
  the view status);
* NOTHING becomes unreachable -- a hidden tool still dispatches to its own
  handler by its exact registered name, so its confirmation, cost, dry-run and
  acceptance gates are untouched;
* discovery still indexes the COMPLETE registry, because that is how a caller
  finds the exact name to call.

The size claim is asserted here as a ratio against the same registry rendered the
same way, so a future edit that quietly re-expands the gateway surface fails
rather than silently costing every caller context.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from mcp_main.win.mcp import server
from mcp_main.win.mcp.tool_views import GATEWAY_TOOL_NAMES, ToolViewState

#: The complete registry is ~211 kB of JSON; the gateway surface is ~4.6 kB
#: (measured 2026-09-21). A ratio this loose still fails loudly if the mode stops
#: compressing.
MIN_COMPRESSION_RATIO = 40


def _rendered_size(tools: list[dict]) -> int:
    return len(json.dumps({"tools": tools}, ensure_ascii=False, separators=(",", ":")))


class GatewayViewSelectionTest(unittest.TestCase):
    def gateway(self) -> ToolViewState:
        with mock.patch.dict(
            os.environ, {"ONSHAPE_MCP_TOOL_EXPOSURE": "gateway"}
        ):
            return ToolViewState.from_environment(server.TOOLS)

    def test_gateway_lists_only_the_compressed_entry_points(self):
        state = self.gateway()
        self.assertEqual(state.mode, "gateway")
        listed = {tool["name"] for tool in state.listed_tools()}
        self.assertEqual(listed, set(GATEWAY_TOOL_NAMES))
        self.assertEqual(listed, {"mcp_tool_catalog", "mcp_tool_view"})
        self.assertEqual(state.status()["toolCount"], 2)
        self.assertEqual(state.status()["registryCount"], len(server.TOOLS))

    def test_gateway_surface_is_much_smaller_than_the_registry(self):
        state = self.gateway()
        gateway = _rendered_size(state.listed_tools())
        complete = _rendered_size(server.TOOLS)
        self.assertGreater(complete / gateway, MIN_COMPRESSION_RATIO)
        # The measured sizes are the point of the mode, so a regression reports
        # both numbers instead of only a failed comparison.
        self.assertLess(gateway, 5000, f"gateway tool JSON is {gateway} bytes")

    def test_every_registered_name_remains_callable_from_the_gateway_view(self):
        state = self.gateway()
        self.assertTrue(state.status()["hiddenNamesStillCallable"])
        self.assertTrue(state.status()["knownNameCallsRemainAvailable"])
        # A hidden tool is not special-cased away: it is simply not advertised.
        listed = {tool["name"] for tool in state.listed_tools()}
        hidden = [tool["name"] for tool in server.TOOLS if tool["name"] not in listed]
        self.assertEqual(len(hidden), len(server.TOOLS) - 2)
        for name in hidden:
            self.assertIn(name, server.HANDLERS)

    def test_gateway_reports_its_listed_names_and_rejects_switching(self):
        state = self.gateway()
        self.assertEqual(
            state.status()["listedNames"], ["mcp_tool_view", "mcp_tool_catalog"]
        )
        self.assertFalse(state.switching_available)
        self.assertFalse(state.list_changed_capability)
        with self.assertRaisesRegex(ValueError, "requires ONSHAPE_MCP_TOOL_EXPOSURE=dynamic"):
            state.apply({"action": "set", "profile": "browser"})


class GatewayConnectionTest(unittest.TestCase):
    def connection(self) -> server.McpConnection:
        with mock.patch.dict(
            os.environ, {"ONSHAPE_MCP_TOOL_EXPOSURE": "gateway"}
        ):
            return server.McpConnection(ToolViewState.from_environment(server.TOOLS))

    def call(self, connection, request_id, name, arguments):
        return connection.dispatch_messages({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })

    def test_tools_list_advertises_two_tools_and_explains_itself(self):
        listed = self.connection().dispatch_messages({
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}
        })[0]["result"]
        self.assertEqual(listed["exposureMode"], "gateway")
        self.assertEqual(len(listed["tools"]), 2)
        view = listed["toolView"]
        self.assertEqual(view["toolCount"], 2)
        self.assertTrue(view["conventionOnly"])
        self.assertFalse(view["authorityChanged"])

    def test_a_hidden_tool_dispatches_to_its_own_handler(self):
        connection = self.connection()
        outgoing = self.call(connection, 1, "onshape_get_parameter_set", {"name": "preview"})
        self.assertEqual(len(outgoing), 1)
        self.assertNotIn("error", outgoing[0])
        self.assertFalse(outgoing[0]["result"]["isError"])
        structured = outgoing[0]["result"]["structuredContent"]
        self.assertIn("parameters", structured)
        # The handler's own gate is what answered: the gateway adds no permission.
        self.assertFalse(structured["parameters"]["detailedStrands"])

    def test_an_unknown_name_still_fails_the_same_way(self):
        outgoing = self.call(self.connection(), 1, "no_such_tool", {})
        self.assertEqual(outgoing[0]["error"]["code"], -32602)
        self.assertIn("Unknown tool", outgoing[0]["error"]["message"])

    def test_catalog_still_indexes_the_whole_registry_and_marks_hidden_entries(self):
        connection = self.connection()
        search = self.call(connection, 1, "mcp_tool_catalog", {
            "action": "search", "query": "insert custom feature", "limit": 5
        })
        structured = search[0]["result"]["structuredContent"]
        self.assertGreater(structured["totalMatches"], 0)
        by_name = {item["name"]: item for item in structured["results"]}
        self.assertIn("browser_insert_custom_feature", by_name)
        self.assertFalse(by_name["browser_insert_custom_feature"]["visibleInCurrentView"])
        describe = self.call(connection, 2, "mcp_tool_catalog", {
            "action": "describe", "name": "browser_insert_custom_feature"
        })
        tool = describe[0]["result"]["structuredContent"]["tool"]
        self.assertIn("inputSchema", tool)
        self.assertFalse(tool["visibleInCurrentView"])
        # The catalog already promised this before the gateway mode existed, so
        # the mode adds no new authority claim: it only stops advertising.
        self.assertTrue(tool["knownNameCallAvailable"])


if __name__ == "__main__":
    unittest.main()
