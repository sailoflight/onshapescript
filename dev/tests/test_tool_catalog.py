from __future__ import annotations

import json
import unittest

from mcp_main.win.mcp import server
from mcp_main.win.mcp.tool_catalog import ToolCatalogIndex
from mcp_main.win.mcp.tool_views import ToolViewState, VALID_PROFILES, select_view_tools


class ToolCatalogIndexTest(unittest.TestCase):
    def setUp(self):
        self.index = server.TOOL_CATALOG
        self.all_names = {tool["name"] for tool in server.TOOLS}

    def test_index_builds_once_from_complete_authoritative_registry(self):
        status = self.index.status(visible_names=self.all_names)
        rebuilt = ToolCatalogIndex(server.TOOLS)
        self.assertEqual(status["registryCount"], len(server.TOOLS))
        self.assertEqual(status["indexedCount"], len(server.HANDLERS))
        self.assertEqual(status["buildCount"], 1)
        self.assertEqual(status["fingerprint"], rebuilt.fingerprint)
        self.assertEqual(len(status["fingerprint"]), 64)
        self.assertEqual(status["schemaPolicy"], "exact-describe-only")
        self.assertTrue(status["conventionOnly"])
        self.assertFalse(status["authorityChanged"])

    def test_search_is_bounded_compact_and_never_returns_schema(self):
        result = self.index.search({"query": "browser", "limit": 12}, visible_names=self.all_names)
        serialized = json.dumps(result, separators=(",", ":"))
        self.assertEqual(result["returnedCount"], 12)
        self.assertTrue(result["truncated"])
        self.assertFalse(result["schemaIncluded"])
        self.assertNotIn("inputSchema", serialized)
        self.assertLess(len(serialized), 16000)
        self.assertTrue(all(len(item["description"]) <= 180 for item in result["results"]))
        with self.assertRaisesRegex(ValueError, "1 through 12"):
            self.index.search({"limit": 13}, visible_names=self.all_names)

    def test_exact_name_and_prefix_ranking_are_stable(self):
        exact = self.index.search({"query": "browser_export_step"}, visible_names=self.all_names)
        prefix = self.index.search({"query": "browser export"}, visible_names=self.all_names)
        self.assertEqual(exact["results"][0]["name"], "browser_export_step")
        self.assertEqual(exact["results"][0]["matchScore"], 0)
        self.assertEqual(prefix["results"][0]["name"], "browser_export_step")

    def test_filters_cover_module_profile_level_network_mutation_and_visibility(self):
        visible_names = {
            tool["name"]
            for tool in select_view_tools(
                server.TOOLS,
                profile="documentation",
                semantic_levels=None,
            )
        }
        hidden_geometry = self.index.search({
            "query": "geometry",
            "profiles": ["geometry"],
            "network": "offline",
            "visible_only": False,
        }, visible_names=visible_names)
        self.assertGreater(hidden_geometry["totalMatches"], 0)
        self.assertTrue(any(not item["visibleInCurrentView"] for item in hidden_geometry["results"]))
        visible_geometry = self.index.search({
            "query": "geometry",
            "profiles": ["geometry"],
            "visible_only": True,
        }, visible_names=visible_names)
        self.assertEqual(visible_geometry["totalMatches"], 0)

        l5 = self.index.search({
            "modules": ["browser"],
            "semantic_levels": ["L5"],
            "mutating": True,
            "limit": 12,
        }, visible_names=self.all_names)
        self.assertGreater(l5["totalMatches"], 0)
        self.assertTrue(all(item["module"] == "browser" for item in l5["results"]))
        self.assertTrue(all(item["semanticLevel"] == "L5" for item in l5["results"]))
        self.assertTrue(all(item["mutating"] for item in l5["results"]))

    def test_describe_requires_exact_name_and_is_only_schema_path(self):
        result = self.index.describe({"name": "browser_export_step"}, visible_names=set())
        tool = result["tool"]
        self.assertTrue(result["schemaIncluded"])
        self.assertIn("inputSchema", tool)
        self.assertIn("cost", tool)
        self.assertIn("annotations", tool)
        self.assertIn("semantic", tool)
        self.assertFalse(tool["visibleInCurrentView"])
        self.assertTrue(tool["knownNameCallAvailable"])
        self.assertTrue(tool["conventionOnly"])
        self.assertFalse(tool["authorityChanged"])
        with self.assertRaisesRegex(ValueError, "exactly match"):
            self.index.describe({"name": "export step"}, visible_names=self.all_names)

    def test_quota_operation_is_not_misclassified_as_reference_documentation(self):
        status = self.index.status(visible_names=self.all_names)
        quota = self.index.describe({"name": "onshape_api_quota"}, visible_names=self.all_names)["tool"]
        self.assertEqual(quota["module"], "rest")
        self.assertIn("rest", quota["profiles"])
        self.assertNotIn("documentation", quota["profiles"])
        self.assertEqual(status["modules"]["rest_reference"], 6)

    def test_confirmation_modes_distinguish_execution_from_budget_override(self):
        create = self.index.describe({"name": "browser_create_document"}, visible_names=self.all_names)["tool"]
        export = self.index.describe({"name": "browser_export_step"}, visible_names=self.all_names)["tool"]
        eval_tool = self.index.describe({"name": "onshape_eval_featurescript"}, visible_names=self.all_names)["tool"]
        self.assertEqual(create["confirmation"]["mode"], "always")
        self.assertTrue(create["confirmation"]["schemaRequired"])
        self.assertEqual(export["confirmation"]["mode"], "non_dry_run")
        self.assertTrue(export["confirmation"]["requiredForRealCall"])
        self.assertEqual(eval_tool["confirmation"]["mode"], "budget_override")
        self.assertFalse(eval_tool["confirmation"]["requiredForRealCall"])

    def test_local_side_effects_and_offline_geometry_are_explicit(self):
        screenshot = self.index.search({"query": "browser_capture_screenshot"}, visible_names=self.all_names)["results"][0]
        status = self.index.search({"query": "browser_geometry_status"}, visible_names=self.all_names)["results"][0]
        self.assertIn("local_file", screenshot["sideEffects"])
        self.assertEqual(status["network"], "offline")
        self.assertFalse(status["requiresBrowserSession"])
        self.assertIsNone(status["semanticLevel"])

    def test_watch_action_schema_and_description_are_defined_together(self):
        watch = self.index.describe({"name": "browser_watch"}, visible_names=self.all_names)["tool"]
        actions = watch["inputSchema"]["properties"]["action"]["enum"]
        for action in actions:
            self.assertIn(action, watch["description"])

    def test_catalog_tool_is_visible_in_every_profile(self):
        for profile in VALID_PROFILES:
            names = {
                tool["name"]
                for tool in select_view_tools(server.TOOLS, profile=profile, semantic_levels=None)
            }
            self.assertIn("mcp_tool_catalog", names, profile)
            self.assertIn("mcp_tool_view", names, profile)


class ConnectionCatalogTest(unittest.TestCase):
    def call(self, connection, request_id, name, arguments):
        return connection.dispatch_messages({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })

    def test_connections_share_index_but_compute_visibility_per_view(self):
        documentation = server.McpConnection(ToolViewState(
            tools=server.TOOLS,
            mode="dynamic",
            profile="documentation",
        ))
        geometry = server.McpConnection(ToolViewState(
            tools=server.TOOLS,
            mode="dynamic",
            profile="geometry",
        ))
        self.assertIs(documentation.catalog, geometry.catalog)
        first = self.call(documentation, 1, "mcp_tool_catalog", {
            "action": "describe", "name": "browser_geometry_status"
        })[0]["result"]["structuredContent"]
        second = self.call(geometry, 2, "mcp_tool_catalog", {
            "action": "describe", "name": "browser_geometry_status"
        })[0]["result"]["structuredContent"]
        self.assertFalse(first["tool"]["visibleInCurrentView"])
        self.assertTrue(second["tool"]["visibleInCurrentView"])
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_catalog_searches_hidden_registry_without_changing_view_or_emitting_notification(self):
        connection = server.McpConnection(ToolViewState(
            tools=server.TOOLS,
            mode="dynamic",
            profile="documentation",
        ))
        before = connection.view.status()
        outgoing = self.call(connection, 1, "mcp_tool_catalog", {
            "action": "search",
            "query": "build geometry package",
            "profiles": ["geometry"],
        })
        self.assertEqual(len(outgoing), 1)
        result = outgoing[0]["result"]["structuredContent"]
        self.assertGreater(result["totalMatches"], 0)
        self.assertTrue(any(not item["visibleInCurrentView"] for item in result["results"]))
        self.assertEqual(connection.view.status(), before)


if __name__ == "__main__":
    unittest.main()
