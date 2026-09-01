from __future__ import annotations

import os
import unittest
from unittest import mock

from mcp_main.win.mcp import server
from mcp_main.win.mcp.tool_views import ToolViewState, exposure_mode, select_view_tools


class ToolViewSelectionTest(unittest.TestCase):
    def names(self, tools):
        return {tool["name"] for tool in tools}

    def test_profiles_are_bounded_and_keep_control_tool(self):
        documentation = self.names(select_view_tools(
            server.TOOLS,
            profile="documentation",
            semantic_levels=None,
        ))
        geometry = self.names(select_view_tools(
            server.TOOLS,
            profile="geometry",
            semantic_levels=None,
        ))
        featurescript = self.names(select_view_tools(
            server.TOOLS,
            profile="featurescript",
            semantic_levels=None,
        ))
        self.assertIn("mcp_tool_view", documentation)
        self.assertIn("docs_search", documentation)
        self.assertIn("fs_get_function", documentation)
        self.assertIn("onshape_api_endpoint", documentation)
        self.assertNotIn("browser_click", documentation)
        self.assertIn("browser_geometry_status", geometry)
        self.assertIn("onshape_build_geometry_package", geometry)
        self.assertNotIn("browser_create_document", geometry)
        self.assertIn("fs_search", featurescript)
        self.assertIn("onshape_eval_featurescript", featurescript)
        self.assertNotIn("onshape_geometry_status", featurescript)

    def test_browser_semantic_filter_can_reveal_l1_without_becoming_authority(self):
        names = self.names(select_view_tools(
            server.TOOLS,
            profile="browser",
            semantic_levels=("L1",),
        ))
        self.assertIn("browser_click", names)
        self.assertIn("browser_discover_tools", names)
        self.assertIn("browser_invoke_discovered", names)
        self.assertNotIn("browser_create_document", names)
        self.assertNotIn("browser_print_orientation_check", names)

    def test_static_all_profile_matches_complete_registry(self):
        selected = select_view_tools(server.TOOLS, profile="all", semantic_levels=None)
        self.assertEqual(selected, server.TOOLS)

    def test_profile_mode_reads_fixed_startup_profile(self):
        with mock.patch.dict(os.environ, {
            "ONSHAPE_MCP_TOOL_EXPOSURE": "profile",
            "ONSHAPE_MCP_TOOL_PROFILE": "documentation",
        }):
            state = ToolViewState.from_environment(server.TOOLS)
        self.assertEqual(state.mode, "profile")
        self.assertEqual(state.profile, "documentation")
        self.assertFalse(state.list_changed_capability)
        names = self.names(state.listed_tools())
        self.assertIn("docs_search", names)
        self.assertNotIn("browser_create_document", names)

    def test_invalid_exposure_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be one of"):
            exposure_mode("authority")


class ConnectionToolViewTest(unittest.TestCase):
    def connection(self, profile="default"):
        return server.McpConnection(ToolViewState(
            tools=server.TOOLS,
            mode="dynamic",
            profile=profile,
        ))

    def call(self, connection, request_id, name, arguments):
        return connection.dispatch_messages({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })

    def test_dynamic_change_returns_response_then_list_changed_notification(self):
        connection = self.connection()
        initialize = connection.dispatch_messages({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        })
        self.assertTrue(initialize[0]["result"]["capabilities"]["tools"]["listChanged"])
        outgoing = self.call(connection, 2, "mcp_tool_view", {
            "action": "set",
            "profile": "browser",
            "semantic_levels": ["L5"],
        })
        self.assertEqual(len(outgoing), 2)
        self.assertEqual(outgoing[0]["id"], 2)
        result = outgoing[0]["result"]["structuredContent"]
        self.assertTrue(result["changed"])
        self.assertTrue(result["conventionOnly"])
        self.assertFalse(result["authorityChanged"])
        self.assertEqual(outgoing[1]["method"], "notifications/tools/list_changed")

        listed = connection.dispatch_messages({
            "jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}
        })[0]["result"]
        names = {tool["name"] for tool in listed["tools"]}
        self.assertIn("browser_assemble", names)
        self.assertNotIn("browser_create_document", names)
        self.assertNotIn("onshape_get_parameter_set", names)

    def test_same_view_does_not_emit_duplicate_notification(self):
        connection = self.connection()
        arguments = {"action": "set", "profile": "browser", "semantic_levels": ["L4"]}
        self.assertEqual(len(self.call(connection, 1, "mcp_tool_view", arguments)), 2)
        repeated = self.call(connection, 2, "mcp_tool_view", arguments)
        self.assertEqual(len(repeated), 1)
        self.assertFalse(repeated[0]["result"]["structuredContent"]["changed"])

    def test_hidden_known_name_tool_remains_callable(self):
        connection = self.connection()
        self.call(connection, 1, "mcp_tool_view", {
            "action": "set", "profile": "browser", "semantic_levels": ["L5"]
        })
        outgoing = self.call(connection, 2, "onshape_get_parameter_set", {"name": "preview"})
        self.assertEqual(len(outgoing), 1)
        self.assertNotIn("error", outgoing[0])
        parameters = outgoing[0]["result"]["structuredContent"]["parameters"]
        self.assertFalse(parameters["detailedStrands"])

    def test_connections_are_isolated_and_reconnect_resets_view(self):
        first = self.connection()
        second = self.connection()
        self.call(first, 1, "mcp_tool_view", {"action": "set", "profile": "geometry"})
        self.assertEqual(first.view.profile, "geometry")
        self.assertEqual(second.view.profile, "default")
        replacement = self.connection()
        self.assertEqual(replacement.view.profile, "default")

    def test_fixed_modes_report_status_but_reject_switching(self):
        view = ToolViewState(tools=server.TOOLS, mode="profile", profile="documentation")
        connection = server.McpConnection(view)
        initialize = connection.dispatch_messages({
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}
        })
        self.assertFalse(initialize[0]["result"]["capabilities"]["tools"]["listChanged"])
        status = self.call(connection, 2, "mcp_tool_view", {"action": "status"})
        self.assertFalse(status[0]["result"]["structuredContent"]["switchingAvailable"])
        changed = self.call(connection, 3, "mcp_tool_view", {
            "action": "set", "profile": "browser"
        })
        self.assertEqual(changed[0]["error"]["code"], -32602)
        self.assertIn("requires ONSHAPE_MCP_TOOL_EXPOSURE=dynamic", changed[0]["error"]["message"])

    def test_reset_uses_connection_startup_profile(self):
        connection = self.connection("geometry")
        self.call(connection, 1, "mcp_tool_view", {"action": "set", "profile": "browser"})
        outgoing = self.call(connection, 2, "mcp_tool_view", {"action": "reset"})
        self.assertEqual(outgoing[0]["result"]["structuredContent"]["profile"], "geometry")


if __name__ == "__main__":
    unittest.main()
