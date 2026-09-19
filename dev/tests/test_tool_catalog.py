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

    def test_every_tool_exposes_conservative_concurrency_contract(self):
        for tool in server.TOOLS:
            contract = tool["cost"]["concurrency"]
            self.assertEqual(contract["contractVersion"], "1", tool["name"])
            self.assertEqual(contract["workflowIsolation"], "none", tool["name"])
            self.assertIn(
                contract["access"],
                {"shared_read", "connection_local", "exclusive_workflow"},
                tool["name"],
            )
            self.assertIn(
                contract["scope"],
                {
                    "none",
                    "connection",
                    "browser_profile",
                    "explicit_document",
                    "explicit_target",
                    "registration",
                    "registration_target_state",
                },
                tool["name"],
            )
            self.assertIsInstance(contract["scopeKeyPaths"], list, tool["name"])
            self.assertIsInstance(contract["coordinationScopes"], list, tool["name"])
            self.assertIn(
                contract["scopeKeyCoverage"],
                {"none", "optional", "non_document_target_required", "document_id_required"},
                tool["name"],
            )
            self.assertIsInstance(contract["dependsOnCurrentBrowserPage"], bool, tool["name"])
            self.assertIsInstance(contract["sharedTargetState"], str, tool["name"])
            self.assertIsInstance(contract["sharedLocalState"], str, tool["name"])
            self.assertIsInstance(
                contract["requiresExplicitTargetForConcurrentUse"], bool, tool["name"]
            )
            self.assertIsInstance(contract["safeDuringMutationWorkflow"], bool, tool["name"])
            self.assertIsInstance(
                contract["safeDuringMutationWorkflowWhenExplicitTarget"],
                bool,
                tool["name"],
            )
            self.assertFalse(contract["conditionEvaluatedAtRuntime"], tool["name"])
            self.assertIsInstance(
                contract["callerMustVerifyScopeKeyPresence"], bool, tool["name"]
            )
            self.assertFalse(
                contract["configuredDefaultTargetAllowedDuringConcurrentUse"],
                tool["name"],
            )
            if tool["cost"]["mutating"]:
                self.assertFalse(contract["safeDuringMutationWorkflow"], tool["name"])
                self.assertFalse(
                    contract["safeDuringMutationWorkflowWhenExplicitTarget"],
                    tool["name"],
                )
            if (
                contract["dependsOnCurrentBrowserPage"]
                or contract["sharedTargetState"] != "none"
                or contract["sharedLocalState"] != "none"
            ):
                self.assertFalse(contract["safeDuringMutationWorkflow"], tool["name"])

    def test_concurrency_contract_classifies_shared_state_and_page_dependencies(self):
        describe = lambda name: self.index.describe(
            {"name": name}, visible_names=self.all_names
        )["tool"]["concurrency"]

        docs = describe("docs_search")
        self.assertEqual(docs["access"], "shared_read")
        self.assertEqual(docs["scope"], "none")
        self.assertTrue(docs["safeDuringMutationWorkflow"])

        conditional_live = describe("fs_check_version")
        self.assertEqual(conditional_live["scope"], "registration_target_state")
        self.assertEqual(conditional_live["sharedTargetState"], "read")
        self.assertEqual(conditional_live["sharedLocalState"], "read")
        self.assertFalse(conditional_live["safeDuringMutationWorkflow"])

        reference_read = describe("fs_get_function")
        self.assertEqual(reference_read["scope"], "registration")
        self.assertEqual(reference_read["sharedLocalState"], "read")
        self.assertFalse(reference_read["safeDuringMutationWorkflow"])

        quota_read = describe("onshape_api_quota")
        self.assertEqual(quota_read["sharedLocalState"], "read")
        self.assertFalse(quota_read["safeDuringMutationWorkflow"])

        reference_write = describe("fs_update_reference")
        self.assertEqual(reference_write["access"], "exclusive_workflow")
        self.assertEqual(reference_write["sharedLocalState"], "write")

        page_read = describe("browser_get_fs_compile_status")
        self.assertEqual(page_read["access"], "exclusive_workflow")
        self.assertEqual(page_read["scope"], "browser_profile")
        self.assertTrue(page_read["dependsOnCurrentBrowserPage"])
        self.assertFalse(page_read["safeDuringMutationWorkflow"])

        browser_export = describe("browser_export_step")
        self.assertEqual(browser_export["scope"], "browser_profile")
        self.assertIn(
            "params.arguments.document_id", browser_export["scopeKeyPaths"]
        )
        self.assertEqual(
            browser_export["coordinationScopes"],
            ["browser_profile", "explicit_document"],
        )

        rest_export = describe("onshape_export_step")
        self.assertEqual(rest_export["access"], "exclusive_workflow")
        self.assertEqual(rest_export["scope"], "explicit_document")
        self.assertFalse(rest_export["requiresExplicitTargetForConcurrentUse"])

        optional_target = describe("onshape_check_model")
        self.assertEqual(optional_target["scope"], "explicit_target")
        self.assertTrue(optional_target["requiresExplicitTargetForConcurrentUse"])
        self.assertFalse(optional_target["safeDuringMutationWorkflow"])
        self.assertTrue(
            optional_target["safeDuringMutationWorkflowWhenExplicitTarget"]
        )
        self.assertTrue(optional_target["callerMustVerifyScopeKeyPresence"])
        self.assertFalse(optional_target["conditionEvaluatedAtRuntime"])
        self.assertFalse(
            optional_target["configuredDefaultTargetAllowedDuringConcurrentUse"]
        )

        shared_state = describe("browser_sync_rest_state")
        self.assertEqual(shared_state["access"], "exclusive_workflow")
        self.assertEqual(shared_state["scope"], "registration_target_state")
        self.assertEqual(shared_state["sharedTargetState"], "write")

        connection = describe("mcp_tool_view")
        self.assertEqual(connection["access"], "connection_local")
        self.assertEqual(connection["scope"], "connection")

    def test_catalog_status_declares_no_workflow_isolation(self):
        status = self.index.status(visible_names=self.all_names)
        self.assertEqual(status["concurrencyPolicy"]["workflowIsolation"], "none")
        self.assertEqual(
            status["concurrencyPolicy"]["productionMutationMode"],
            "single_modifying_agent",
        )
        summary = self.index.search(
            {"query": "browser_get_fs_compile_status"},
            visible_names=self.all_names,
        )["results"][0]
        self.assertEqual(summary["concurrency"]["access"], "exclusive_workflow")
        self.assertEqual(summary["concurrency"]["scope"], "browser_profile")
        self.assertEqual(summary["concurrency"]["workflowIsolation"], "none")
        self.assertTrue(summary["concurrency"]["classificationOnly"])

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
            "action": "describe", "name": "onshape_geometry_status"
        })[0]["result"]["structuredContent"]
        second = self.call(geometry, 2, "mcp_tool_catalog", {
            "action": "describe", "name": "onshape_geometry_status"
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
