from __future__ import annotations

import os
import unittest
from unittest import mock

from mcp_main.win.mcp import server
from mcp_main.win.mcp.tool_views import (
    GATEWAY_TOOL_NAMES,
    ToolViewState,
    exposure_mode,
    select_view_tools,
)


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
        self.assertIn("onshape_geometry_status", geometry)
        self.assertIn("onshape_configure_geometry_backend", geometry)
        self.assertNotIn("browser_geometry_status", geometry)
        self.assertNotIn("browser_configure_geometry_backend", geometry)
        self.assertIn("onshape_build_geometry_package", geometry)
        self.assertNotIn("browser_create_document", geometry)
        self.assertIn("fs_search", featurescript)
        self.assertIn("onshape_eval_featurescript", featurescript)
        self.assertNotIn("fs_list_modules", featurescript)
        self.assertNotIn("onshape_geometry_status", featurescript)

    def test_browser_semantic_filter_can_reveal_l1_without_becoming_authority(self):
        names = self.names(select_view_tools(
            server.TOOLS,
            profile="browser",
            semantic_levels=("L1",),
        ))
        self.assertIn("browser_click", names)
        self.assertIn("browser_discover_tools", names)
        self.assertNotIn("browser_invoke_discovered", names)
        self.assertNotIn("browser_create_document", names)
        self.assertNotIn("browser_print_orientation_check", names)
        # The absorbed invoker is an L2 name, so its own explicit level reaches it.
        self.assertIn(
            "browser_invoke_discovered",
            self.names(select_view_tools(
                server.TOOLS,
                profile="browser",
                semantic_levels=("L2",),
            )),
        )

    def test_static_all_profile_matches_complete_registry(self):
        selected = select_view_tools(server.TOOLS, profile="all", semantic_levels=None)
        self.assertEqual(selected, server.TOOLS)

    def test_absorbed_names_stay_registered_but_are_never_advertised(self):
        """A merge keeps the old name callable without making it a normal choice.

        The exact-name registry stays authoritative, so hiding is a discovery
        convention: the wrapper is absent from every ordinary profile and present
        only in the complete `all` view.
        """
        from mcp_main.win.mcp.tool_views import ABSORBED_COMPATIBILITY_TOOLS

        registered = {tool["name"] for tool in server.TOOLS}
        self.assertTrue(ABSORBED_COMPATIBILITY_TOOLS)
        self.assertTrue(ABSORBED_COMPATIBILITY_TOOLS <= registered)
        for profile in ("default", "browser", "rest", "featurescript", "documentation", "geometry"):
            with self.subTest(profile=profile):
                names = self.names(
                    select_view_tools(server.TOOLS, profile=profile, semantic_levels=None)
                )
                self.assertEqual(ABSORBED_COMPATIBILITY_TOOLS & names, set())
        complete = self.names(select_view_tools(server.TOOLS, profile="all", semantic_levels=None))
        self.assertEqual(ABSORBED_COMPATIBILITY_TOOLS & complete, ABSORBED_COMPATIBILITY_TOOLS)

    def test_deprecated_browser_names_leave_the_ordinary_browser_view(self):
        from onshape_browser_mode.semantics import TOOL_SEMANTICS

        deprecated = {
            name for name, record in TOOL_SEMANTICS.items()
            if record.maturity == "deprecated"
        }
        self.assertTrue(deprecated)
        ordinary = self.names(
            select_view_tools(server.TOOLS, profile="browser", semantic_levels=None)
        )
        self.assertEqual(deprecated & ordinary, set())
        # An explicit level query still reaches the ones that carry a level.
        revealed = self.names(
            select_view_tools(
                server.TOOLS,
                profile="browser",
                semantic_levels=("L1", "L2", "L3", "L4", "L5", "L6"),
            )
        )
        self.assertTrue(
            {name for name in deprecated if TOOL_SEMANTICS[name].level} <= revealed
        )

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


class CollapseExpandToolViewTest(unittest.TestCase):
    """Issue #3: ordinary default is `gateway`; `dynamic` is collapse/expand.

    The display set is orthogonal to the collapse state: a fresh `dynamic`
    connection lists no domain schema at all, and expanding selects one of the
    static / semantic / gateway / profile sets.
    """

    CONTROL_NAMES = {"mcp_tool_catalog", "mcp_tool_view", "mcp_tool_invoke"}

    def names(self, tools):
        return {tool["name"] for tool in tools}

    def dynamic_connection(self, profile=None):
        environment = {"ONSHAPE_MCP_TOOL_EXPOSURE": "dynamic"}
        if profile is not None:
            environment["ONSHAPE_MCP_TOOL_PROFILE"] = profile
        with mock.patch.dict(os.environ, environment):
            return server.McpConnection(
                ToolViewState.from_environment(server.TOOLS)
            )

    def call(self, connection, request_id, arguments, name="mcp_tool_view"):
        return connection.dispatch_messages({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })

    def listed(self, connection):
        return connection.dispatch_messages({
            "jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}
        })[0]["result"]

    def test_an_empty_environment_defaults_to_the_gateway_view(self):
        from mcp_main.win.mcp import tool_views

        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(tool_views, "_local_section", lambda name: {}):
            self.assertEqual(exposure_mode(), "gateway")
            state = ToolViewState.from_environment(server.TOOLS)
        self.assertEqual(state.mode, "gateway")
        self.assertEqual(self.names(state.listed_tools()), set(GATEWAY_TOOL_NAMES))
        self.assertEqual(len(state.listed_tools()), 25)
        self.assertEqual(state.status()["state"], "expanded")

    def test_a_fresh_dynamic_connection_starts_collapsed(self):
        connection = self.dynamic_connection()
        view = connection.view
        self.assertTrue(view.collapsed)
        self.assertEqual(view.expanded_view, "gateway")
        listed = self.listed(connection)
        self.assertEqual(listed["exposureMode"], "dynamic")
        self.assertEqual(self.names(listed["tools"]), self.CONTROL_NAMES)
        self.assertEqual(listed["toolView"]["state"], "collapsed")
        self.assertEqual(listed["toolView"]["expandedView"], "gateway")
        self.assertEqual(listed["toolView"]["scope"], "connection")
        self.assertEqual(listed["toolView"]["toolCount"], 3)
        self.assertTrue(listed["toolView"]["hiddenNamesStillCallable"])
        # No domain schema is resident while collapsed: the only tool entries
        # are the three control/discovery doors.
        self.assertEqual(len(listed["tools"]), 3)

    def test_expand_without_an_argument_opens_the_default_gateway_set(self):
        connection = self.dynamic_connection()
        outgoing = self.call(connection, 1, {"action": "expand"})
        self.assertEqual(len(outgoing), 2)
        result = outgoing[0]["result"]["structuredContent"]
        self.assertTrue(result["changed"])
        self.assertEqual(result["state"], "expanded")
        self.assertEqual(result["expandedView"], "gateway")
        self.assertEqual(result["toolCount"], 25)
        self.assertEqual(set(result["listedNames"]), set(GATEWAY_TOOL_NAMES))
        self.assertEqual(outgoing[1]["method"], "notifications/tools/list_changed")

    def test_each_expanded_view_selects_its_display_set(self):
        expected = {"static": 111, "semantic": 77, "gateway": 25, "profile": 40}
        # The startup profile is `browser`, so `expanded_view=profile` is
        # distinguishable from the fixed `semantic` (= `default`) set.
        connection = self.dynamic_connection(profile="browser")
        for index, (expanded_view, count) in enumerate(expected.items(), start=1):
            with self.subTest(expanded_view=expanded_view):
                outgoing = self.call(connection, index, {
                    "action": "expand", "expanded_view": expanded_view
                })
                result = outgoing[0]["result"]["structuredContent"]
                self.assertEqual(result["expandedView"], expanded_view)
                self.assertEqual(result["toolCount"], count)
                self.assertEqual(len(connection.view.listed_tools()), count)
                self.assertEqual(outgoing[1]["method"], "notifications/tools/list_changed")

    def test_collapse_returns_to_the_three_entry_points(self):
        connection = self.dynamic_connection()
        self.call(connection, 1, {"action": "expand"})
        self.assertEqual(len(connection.view.listed_tools()), 25)
        outgoing = self.call(connection, 2, {"action": "collapse"})
        self.assertEqual(len(outgoing), 2)
        result = outgoing[0]["result"]["structuredContent"]
        self.assertTrue(result["changed"])
        self.assertEqual(result["state"], "collapsed")
        self.assertEqual(result["toolCount"], 3)
        self.assertEqual(set(result["listedNames"]), self.CONTROL_NAMES)
        self.assertEqual(connection.view.expanded_view, "gateway")

    def test_repeated_identical_actions_are_silent(self):
        connection = self.dynamic_connection()
        first = self.call(connection, 1, {
            "action": "expand", "expanded_view": "static"
        })
        self.assertEqual(len(first), 2)
        repeated = self.call(connection, 2, {
            "action": "expand", "expanded_view": "static"
        })
        self.assertEqual(len(repeated), 1)
        self.assertFalse(repeated[0]["result"]["structuredContent"]["changed"])
        collapsed = self.call(connection, 3, {"action": "collapse"})
        self.assertEqual(len(collapsed), 2)
        again = self.call(connection, 4, {"action": "collapse"})
        self.assertEqual(len(again), 1)
        self.assertFalse(again[0]["result"]["structuredContent"]["changed"])

    def test_each_effective_change_appends_list_changed(self):
        connection = self.dynamic_connection()
        opened = self.call(connection, 1, {"action": "expand", "expanded_view": "semantic"})
        self.assertEqual([message.get("method") for message in opened[1:]],
                         ["notifications/tools/list_changed"])
        switched = self.call(connection, 2, {"action": "expand", "expanded_view": "gateway"})
        self.assertEqual([message.get("method") for message in switched[1:]],
                         ["notifications/tools/list_changed"])
        reset = self.call(connection, 3, {"action": "reset"})
        self.assertEqual([message.get("method") for message in reset[1:]],
                         ["notifications/tools/list_changed"])
        self.assertEqual(reset[0]["result"]["structuredContent"]["state"], "collapsed")
        self.assertEqual(reset[0]["result"]["structuredContent"]["expandedView"], "gateway")

    def test_reset_restores_collapsed_gateway_and_the_startup_profile(self):
        connection = self.dynamic_connection(profile="documentation")
        self.call(connection, 1, {"action": "expand", "expanded_view": "static"})
        outgoing = self.call(connection, 2, {"action": "reset"})
        result = outgoing[0]["result"]["structuredContent"]
        self.assertEqual(result["state"], "collapsed")
        self.assertEqual(result["expandedView"], "gateway")
        self.assertEqual(result["profile"], "documentation")
        self.assertEqual(set(result["listedNames"]), self.CONTROL_NAMES)

    def test_a_hidden_tool_through_the_invoker_still_hits_its_own_gate(self):
        # The forwarder is advertised while collapsed, but it is not a way
        # around the target's own confirmation gate (pattern from
        # `test_tool_gateway_view.py::test_the_targets_own_confirmation_gate_still_answers`).
        connection = self.dynamic_connection()
        self.assertEqual(self.names(connection.view.listed_tools()), self.CONTROL_NAMES)
        outgoing = self.call(connection, 1, {
            "name": "browser_insert_custom_feature",
            "arguments": {"feature_name": "X"},
        }, name="mcp_tool_invoke")
        result = outgoing[0]["result"]
        self.assertTrue(result["isError"])
        self.assertIn("confirm_mutation", result["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
