#!/usr/bin/env python3
"""Gate for the `gateway` exposure mode (roadmap G5, token compression).

The promise of this mode has two halves and both are measured here:

* the advertised surface is a small, DECLARATIVE set -- a discovery core plus one
  or two curated representatives per category -- so ordinary work does not have
  to start with a lookup;
* retrieval stays cheap when it is needed: `mcp_tool_catalog action=index` maps
  the whole registry in bounded `name -- purpose` lines, because a three-result
  `search` carries three full contracts and can cost more than the list it was
  meant to replace.

And the invariant that makes both halves safe: NOTHING becomes unreachable. A
hidden tool still dispatches to its own handler by exact registered name, so its
confirmation, cost, dry-run and acceptance gates are untouched.

Sizes are asserted as bounds, not as remembered numbers, so a future edit that
quietly re-expands the surface fails here instead of costing every caller.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from mcp_main.win.mcp import server
from mcp_main.win.mcp.tool_catalog import MAX_INDEX_RESULTS, VALID_MODULES, tool_module
from mcp_main.win.mcp.tool_views import (
    GATEWAY_CORE_TOOL_NAMES,
    GATEWAY_CURATED_TOOL_NAMES,
    GATEWAY_TOOL_NAMES,
    ToolViewState,
)

#: Measured 2026-09-21 after the depth research (`LOOKUP_DEPTH_RESEARCH.md`)
#: sized the set: the gateway surface is ~63 kB against ~160 kB for the default
#: `semantic` view and ~216 kB for the complete registry. The surface grew on
#: purpose -- two more entries closed the prescribed docs/FS/REST chains, and the
#: parameter workflow stopped paying a round between its own legs -- so the bounds
#: moved with it. They stay loose enough to survive description edits and tight
#: enough to catch a mode that stops compressing.
MAX_GATEWAY_CHARS = 70_000
MIN_COMPRESSION_RATIO = 3
MAX_SEMANTIC_SHARE = 0.45
#: The category map is one line per category; it must stay far below one search.
MAX_CATEGORY_MAP_CHARS = 2_000


def _rendered_size(payload: object) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


class GatewayViewSelectionTest(unittest.TestCase):
    def gateway(self) -> ToolViewState:
        with mock.patch.dict(os.environ, {"ONSHAPE_MCP_TOOL_EXPOSURE": "gateway"}):
            return ToolViewState.from_environment(server.TOOLS)

    def semantic(self) -> ToolViewState:
        with mock.patch.dict(os.environ, {"ONSHAPE_MCP_TOOL_EXPOSURE": "semantic"}):
            return ToolViewState.from_environment(server.TOOLS)

    def test_gateway_lists_its_core_plus_the_curated_representatives(self):
        state = self.gateway()
        self.assertEqual(state.mode, "gateway")
        listed = [tool["name"] for tool in state.listed_tools()]
        self.assertEqual(set(listed), set(GATEWAY_TOOL_NAMES))
        # The core leads (catalog, view, invoker), then the curated order the mode
        # declares.
        self.assertEqual(
            listed[:3], ["mcp_tool_catalog", "mcp_tool_view", "mcp_tool_invoke"]
        )
        self.assertEqual(listed[3:], list(GATEWAY_CURATED_TOOL_NAMES))
        self.assertEqual(state.status()["toolCount"], len(GATEWAY_TOOL_NAMES))
        self.assertEqual(state.status()["registryCount"], len(server.TOOLS))

    def test_every_curated_name_is_registered_and_answers_a_real_category(self):
        registered = {tool["name"] for tool in server.TOOLS}
        for name in GATEWAY_TOOL_NAMES:
            self.assertIn(name, registered, name)
        # The point of the curated set is that no category is missing from the
        # advertised list, so an ordinary task never has to look a name up first.
        covered = {tool_module(name) for name in GATEWAY_TOOL_NAMES}
        self.assertEqual(covered, set(VALID_MODULES))

    def test_every_prescribed_lookup_chain_is_advertised_end_to_end(self):
        """A half-listed chain is the worst of both: the caller pays the front
        half's rent AND a hidden-name round to finish its own documented
        workflow. Measured 2026-09-21: three of four chains were half-listed
        (`LOOKUP_DEPTH_RESEARCH.md`, finding F2)."""
        from dev.tools.lookup_depth import DOCUMENTED_CHAINS

        listed = {tool["name"] for tool in self.gateway().listed_tools()}
        for name, chain in DOCUMENTED_CHAINS:
            with self.subTest(chain=name):
                for step in chain:
                    self.assertIn(step, listed, f"{name}: {step} is not advertised")

    def test_gateway_surface_is_much_smaller_than_the_default_view(self):
        gateway = _rendered_size({"tools": self.gateway().listed_tools()})
        semantic = _rendered_size({"tools": self.semantic().listed_tools()})
        complete = _rendered_size({"tools": server.TOOLS})
        self.assertLess(gateway, MAX_GATEWAY_CHARS, f"gateway tool JSON is {gateway} bytes")
        self.assertGreater(complete / gateway, MIN_COMPRESSION_RATIO)
        self.assertLess(gateway / semantic, MAX_SEMANTIC_SHARE)

    def test_every_other_registered_name_remains_callable(self):
        listed = {tool["name"] for tool in self.gateway().listed_tools()}
        hidden = [tool["name"] for tool in server.TOOLS if tool["name"] not in listed]
        self.assertEqual(len(hidden), len(server.TOOLS) - len(GATEWAY_TOOL_NAMES))
        for name in hidden:
            self.assertIn(name, server.HANDLERS)
        status = self.gateway().status()
        self.assertTrue(status["hiddenNamesStillCallable"])
        self.assertTrue(status["knownNameCallsRemainAvailable"])
        self.assertEqual(set(status["gateway"]["core"]), set(GATEWAY_CORE_TOOL_NAMES))

    def test_gateway_reports_its_listed_names_and_rejects_switching(self):
        state = self.gateway()
        self.assertEqual(
            state.status()["listedNames"],
            ["mcp_tool_catalog", "mcp_tool_view", "mcp_tool_invoke", *GATEWAY_CURATED_TOOL_NAMES],
        )
        self.assertFalse(state.switching_available)
        self.assertFalse(state.list_changed_capability)
        with self.assertRaisesRegex(ValueError, "requires ONSHAPE_MCP_TOOL_EXPOSURE=dynamic"):
            state.apply({"action": "set", "profile": "browser"})


class HostLocalConfigTest(unittest.TestCase):
    """The switch an operator can actually reach on a bridge-launched host."""

    def test_environment_wins_over_the_host_file_and_the_file_over_the_default(self):
        from mcp_main.win.mcp import tool_views

        with mock.patch.dict(os.environ, {"ONSHAPE_MCP_TOOL_EXPOSURE": "dynamic"}):
            self.assertEqual(tool_views.exposure_mode(), "dynamic")
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(tool_views, "_local_section", lambda name: {"mode": "gateway"}):
            self.assertEqual(tool_views.exposure_mode(), "gateway")
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(tool_views, "_local_section", lambda name: {}):
            self.assertEqual(tool_views.exposure_mode(), "semantic")

    def test_explicit_argument_still_wins(self):
        from mcp_main.win.mcp import tool_views

        with mock.patch.dict(os.environ, {"ONSHAPE_MCP_TOOL_EXPOSURE": "gateway"}):
            self.assertEqual(tool_views.exposure_mode("static"), "static")

    def test_a_missing_host_file_is_not_an_error(self):
        from mcp_main.win.mcp import tool_views

        with mock.patch.object(tool_views, "LOCAL_CONFIG_PATH", tool_views.CONFIG_DIR / "nope.toml"):
            self.assertEqual(tool_views.local_config(), {})


class CatalogIndexTest(unittest.TestCase):
    def index(self, **arguments):
        return server.TOOL_CATALOG.apply({"action": "index", **arguments}, visible_names=set())

    def test_the_category_map_is_one_cheap_line_per_category(self):
        result = self.index()
        self.assertEqual(result["index"], "categories")
        self.assertEqual(
            [item["category"] for item in result["categories"]], list(VALID_MODULES)
        )
        for item in result["categories"]:
            self.assertTrue(item["purpose"], item["category"])
        self.assertEqual(
            sum(item["toolCount"] for item in result["categories"]), len(server.TOOLS)
        )
        self.assertLess(_rendered_size(result), MAX_CATEGORY_MAP_CHARS)

    def test_a_category_page_is_bounded_ordered_and_pageable(self):
        page = self.index(category="browser", limit=10)
        self.assertEqual(page["index"], "category")
        self.assertEqual(page["returnedCount"], 10)
        self.assertEqual(page["offset"], 0)
        self.assertTrue(page["truncated"])
        self.assertEqual(page["nextOffset"], 10)
        names = [line["name"] for line in page["lines"]]
        self.assertEqual(names, sorted(names))
        self.assertTrue(all(line["purpose"] for line in page["lines"]))
        self.assertTrue(all(line["visibleInCurrentView"] is False for line in page["lines"]))
        # No contract, no schema: that is the whole point of the action.
        self.assertFalse(page["schemaIncluded"])
        self.assertNotIn("concurrency", json.dumps(page))

        second = self.index(category="browser", limit=10, offset=10)
        self.assertEqual(second["offset"], 10)
        self.assertEqual(
            {line["name"] for line in page["lines"]}
            & {line["name"] for line in second["lines"]},
            set(),
        )

    def test_the_whole_category_is_reachable_within_the_documented_cap(self):
        page = self.index(category="browser", limit=MAX_INDEX_RESULTS)
        self.assertEqual(page["returnedCount"], MAX_INDEX_RESULTS)
        rest = self.index(category="browser", limit=MAX_INDEX_RESULTS, offset=page["nextOffset"])
        self.assertEqual(page["toolCount"], page["returnedCount"] + rest["returnedCount"])
        self.assertIsNone(rest["nextOffset"])

    def test_the_map_is_cheaper_than_the_search_it_replaces(self):
        # A three-result search carries three full contracts; the map must be the
        # cheap way to ask "what exists".
        map_size = _rendered_size(self.index())
        search_size = _rendered_size(server.TOOL_CATALOG.apply(
            {"action": "search", "query": "insert custom feature", "limit": 3},
            visible_names=set(),
        ))
        self.assertLess(map_size, search_size / 3)

    def test_unknown_inputs_are_refused_rather_than_answered_broadly(self):
        with self.assertRaisesRegex(ValueError, "category must be one of"):
            self.index(category="everything")
        with self.assertRaisesRegex(ValueError, "limit must be from 1 through"):
            self.index(category="browser", limit=MAX_INDEX_RESULTS + 1)
        with self.assertRaisesRegex(ValueError, "offset must be a non-negative integer"):
            self.index(category="browser", offset=-1)
        with self.assertRaisesRegex(ValueError, "action must be status, search, describe, or index"):
            server.TOOL_CATALOG.apply({"action": "expand"}, visible_names=set())


class GatewayConnectionTest(unittest.TestCase):
    def connection(self) -> server.McpConnection:
        with mock.patch.dict(os.environ, {"ONSHAPE_MCP_TOOL_EXPOSURE": "gateway"}):
            return server.McpConnection(ToolViewState.from_environment(server.TOOLS))

    def call(self, connection, request_id, name, arguments):
        return connection.dispatch_messages({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })

    def test_tools_list_advertises_the_gateway_surface_and_explains_itself(self):
        listed = self.connection().dispatch_messages({
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}
        })[0]["result"]
        self.assertEqual(listed["exposureMode"], "gateway")
        self.assertEqual(len(listed["tools"]), len(GATEWAY_TOOL_NAMES))
        view = listed["toolView"]
        self.assertEqual(view["toolCount"], len(GATEWAY_TOOL_NAMES))
        self.assertTrue(view["conventionOnly"])
        self.assertFalse(view["authorityChanged"])
        self.assertIn("retrieval is not free", view["gateway"]["reason"])

    def test_a_hidden_tool_dispatches_to_its_own_handler(self):
        connection = self.connection()
        outgoing = self.call(connection, 1, "onshape_get_parameter_set", {"name": "preview"})
        self.assertEqual(len(outgoing), 1)
        self.assertNotIn("error", outgoing[0])
        self.assertFalse(outgoing[0]["result"]["isError"])
        structured = outgoing[0]["result"]["structuredContent"]
        self.assertIn("parameters", structured)
        # The handler's own gate answered: the gateway adds no permission.
        self.assertFalse(structured["parameters"]["detailedStrands"])

    def test_an_unknown_name_still_fails_the_same_way(self):
        outgoing = self.call(self.connection(), 1, "no_such_tool", {})
        self.assertEqual(outgoing[0]["error"]["code"], -32602)
        self.assertIn("Unknown tool", outgoing[0]["error"]["message"])

    def test_catalog_still_indexes_the_whole_registry_from_the_gateway_view(self):
        connection = self.connection()
        map_result = self.call(connection, 1, "mcp_tool_catalog", {"action": "index"})
        categories = map_result[0]["result"]["structuredContent"]["categories"]
        self.assertEqual(
            sum(item["toolCount"] for item in categories), len(server.TOOLS)
        )
        # Tools the gateway does not advertise are still indexed AND still
        # describable by exact name, which is the promised escape hatch.
        describe = self.call(connection, 2, "mcp_tool_catalog", {
            "action": "describe", "name": "browser_insert_custom_feature"
        })
        tool = describe[0]["result"]["structuredContent"]["tool"]
        self.assertIn("inputSchema", tool)
        self.assertTrue(tool["knownNameCallAvailable"])


class InvokeToolTest(unittest.TestCase):
    """`mcp_tool_invoke`: the advertised door to a name a view does not list.

    The measurement that forced this tool: a real MCP client (2026-09-21) refused
    a registered-but-unadvertised name with `unknown tool`, so "hidden known-name
    calls remain" was true of the SERVER and false of that client. The tests below
    pin both halves -- the door is always advertised, and walking through it adds
    no authority of its own.
    """

    def connection(self, mode: str = "gateway") -> server.McpConnection:
        with mock.patch.dict(os.environ, {"ONSHAPE_MCP_TOOL_EXPOSURE": mode}):
            return server.McpConnection(ToolViewState.from_environment(server.TOOLS))

    def call(self, connection, request_id, name, arguments):
        return connection.dispatch_messages({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })

    def test_the_invoker_is_advertised_in_every_view(self):
        # A hidden escape hatch is no escape hatch for the client that needs it,
        # and the semantic view hides 34 registered names of its own.
        for mode in ("semantic", "dynamic", "profile", "gateway", "static"):
            listed = [tool["name"] for tool in self.connection(mode).view.listed_tools()]
            self.assertIn("mcp_tool_invoke", listed, mode)

    def test_a_hidden_tool_answers_through_it_and_the_leg_is_named(self):
        connection = self.connection()
        listed = {tool["name"] for tool in connection.view.listed_tools()}
        self.assertNotIn("docs_list", listed)
        outgoing = self.call(connection, 1, "mcp_tool_invoke", {"name": "docs_list"})
        self.assertNotIn("error", outgoing[0])
        result = outgoing[0]["result"]
        self.assertFalse(result["isError"])
        structured = result["structuredContent"]
        self.assertEqual(structured["invokedTool"], "docs_list")
        # The target's own answer, not a summary of the forwarding.
        self.assertIn("pages", structured)
        self.assertIn("docs_list", result["content"][0]["text"])

    def test_an_unknown_target_is_refused_with_the_lookup_hint(self):
        outgoing = self.call(self.connection(), 1, "mcp_tool_invoke", {"name": "no_such_tool"})
        self.assertEqual(outgoing[0]["error"]["code"], -32602)
        self.assertIn("Unknown tool", outgoing[0]["error"]["message"])
        self.assertIn("mcp_tool_catalog", outgoing[0]["error"]["message"])

    def test_a_missing_or_non_object_target_is_refused(self):
        connection = self.connection()
        self.assertIn("name is required", self.call(
            connection, 1, "mcp_tool_invoke", {}
        )[0]["error"]["message"])
        self.assertIn("name is required", self.call(
            connection, 2, "mcp_tool_invoke", {"name": "   "}
        )[0]["error"]["message"])
        self.assertIn("must be an object", self.call(
            connection, 3, "mcp_tool_invoke", {"name": "docs_list", "arguments": []}
        )[0]["error"]["message"])

    def test_connection_scoped_targets_are_refused_rather_than_recursed(self):
        connection = self.connection()
        for target in ("mcp_tool_invoke", "mcp_tool_view", "mcp_tool_catalog"):
            outgoing = self.call(connection, 1, "mcp_tool_invoke", {"name": target})
            self.assertIn("connection-scoped", outgoing[0]["error"]["message"], target)

    def test_the_targets_own_confirmation_gate_still_answers(self):
        # A mutating tool with no confirm_mutation must refuse exactly as it does
        # when called directly: the forwarder is not a way around the gate.
        outgoing = self.call(self.connection(), 1, "mcp_tool_invoke", {
            "name": "browser_insert_custom_feature", "arguments": {"feature_name": "X"},
        })
        result = outgoing[0]["result"]
        self.assertTrue(result["isError"])
        self.assertIn("confirm_mutation", result["content"][0]["text"])

    def test_a_dry_run_through_it_still_spends_nothing(self):
        outgoing = self.call(self.connection(), 1, "mcp_tool_invoke", {
            "name": "browser_delete_feature",
            "arguments": {"feature_name": "X", "dry_run": True},
        })
        structured = outgoing[0]["result"]["structuredContent"]
        self.assertEqual(structured["invokedTool"], "browser_delete_feature")
        self.assertTrue(structured["dryRun"])
        self.assertEqual(structured["estimatedApiRequests"], 0)

    def test_the_response_boundary_still_runs_on_the_forwarded_leg(self):
        # The projection lives in `server.tool_result`, which is the one entry the
        # forwarder shares with a direct call, so forwarding cannot smuggle the
        # duplicated row echo back into a transcript -- and the target's own
        # opt-in field still restores the full evidence.
        full = {"deleted": True, "featureRows": ["a", "b"], "beforeRows": ["a", "b"]}
        with mock.patch.dict(server.HANDLERS, {"browser_delete_feature": lambda _: full}):
            compact = self.call(self.connection(), 1, "mcp_tool_invoke", {
                "name": "browser_delete_feature", "arguments": {"feature_name": "a"},
            })[0]["result"]["structuredContent"]
            verbose = self.call(self.connection(), 2, "mcp_tool_invoke", {
                "name": "browser_delete_feature",
                "arguments": {"feature_name": "a", "include_row_evidence": True},
            })[0]["result"]["structuredContent"]
        self.assertNotIn("featureRows", compact)
        self.assertEqual(compact["enumeratedRowCount"], 2)
        self.assertEqual(compact["invokedTool"], "browser_delete_feature")
        self.assertIn("featureRows", verbose)


if __name__ == "__main__":
    unittest.main()
