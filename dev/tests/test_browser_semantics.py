from __future__ import annotations

import unittest

from onshape_browser_mode import semantics


class SixLevelSemanticsTest(unittest.TestCase):
    def test_stable_level_names(self):
        self.assertEqual(
            semantics.LEVEL_NAMES,
            {
                "L1": "browser_primitive",
                "L2": "browser_transaction",
                "L3": "onshape_interaction",
                "L4": "onshape_transaction",
                "L5": "onshape_workflow",
                "L6": "deliverable_recipe",
            },
        )

    def test_catalog_lint_passes(self):
        self.assertEqual(semantics.validate_catalog(), [])

    def test_ordinary_discovery_hides_l1_l3_and_invalid_fdm(self):
        names = [
            "browser_click",
            "browser_open_doc_menu",
            "browser_open_document",
            "browser_deploy_and_apply_featurescript",
            "browser_print_orientation_check",
            "future_unclassified_browser_tool",
        ]
        self.assertEqual(
            semantics.select_tool_names(names),
            [
                "browser_open_document",
                "browser_deploy_and_apply_featurescript",
                "future_unclassified_browser_tool",
            ],
        )

    def test_explicit_l1_l3_queries_reveal_hidden_tools_without_intent(self):
        names = ["browser_click", "browser_open_doc_menu", "browser_open_document"]
        self.assertEqual(
            semantics.select_tool_names(names, semantic_levels=["L1"]),
            ["browser_click"],
        )
        self.assertEqual(
            semantics.select_tool_names(names, semantic_levels=["L3"]),
            ["browser_open_doc_menu"],
        )

    def test_featurescript_notice_and_capture_dependency_chain(self):
        notices = semantics.semantic_metadata("browser_fs_read_notices")
        compile_status = semantics.semantic_metadata("browser_get_fs_compile_status")
        capture = semantics.semantic_metadata("browser_fs_capture_diagnostic")
        deploy = semantics.semantic_metadata("browser_deploy_featurescript")

        self.assertEqual(notices["semanticLevel"], "L3")
        self.assertIn("browser_fs_read_notices", compile_status["dependencies"])
        self.assertEqual(capture["semanticLevel"], "L4")
        self.assertEqual(capture["maturity"], "experimental")
        self.assertFalse(capture["defaultExposure"])
        self.assertIn("browser_fs_capture_diagnostic", deploy["dependencies"])

    def test_explicit_query_can_find_invalid_tool_for_diagnostics(self):
        self.assertEqual(
            semantics.select_tool_names(
                ["browser_print_orientation_check"],
                semantic_levels=["L4"],
            ),
            ["browser_print_orientation_check"],
        )
        metadata = semantics.semantic_metadata("browser_print_orientation_check")
        self.assertEqual(metadata["maturity"], "semantically_invalid")
        self.assertFalse(metadata["defaultExposure"])

    def test_unclassified_tools_are_valid(self):
        self.assertIsNone(semantics.semantic_metadata("future_unclassified_browser_tool"))
        self.assertEqual(
            semantics.select_tool_names(["future_unclassified_browser_tool"]),
            ["future_unclassified_browser_tool"],
        )
        self.assertEqual(
            semantics.select_tool_names(
                ["future_unclassified_browser_tool"],
                semantic_levels=["L4"],
            ),
            [],
        )

    def test_discover_tools_prefers_l5_l4_l2_l6_and_returns_exact_schema(self):
        tools = [
            {"name": "browser_build_geometry_package", "description": "build deliverable", "inputSchema": {"type": "object"}},
            {"name": "browser_session", "description": "session status", "inputSchema": {"type": "object"}},
            {"name": "browser_open_document", "description": "open document", "inputSchema": {"type": "object", "required": ["document_name"]}},
            {"name": "browser_assemble", "description": "assembly workflow", "inputSchema": {"type": "object"}},
            {"name": "browser_click", "description": "click element", "inputSchema": {"type": "object", "required": ["selector"]}},
        ]
        ordinary = semantics.discover_tools(tools, limit=5)
        self.assertEqual(
            [item["name"] for item in ordinary["candidates"]],
            [
                "browser_assemble",
                "browser_open_document",
                "browser_session",
                "browser_build_geometry_package",
            ],
        )
        explicit = semantics.discover_tools(
            tools,
            query="click",
            semantic_levels=["L1"],
            limit=3,
        )
        self.assertEqual([item["name"] for item in explicit["candidates"]], ["browser_click"])
        self.assertEqual(explicit["candidates"][0]["inputSchema"]["required"], ["selector"])
        self.assertEqual(explicit["invocationTool"], "browser_invoke_discovered")

    def test_unknown_level_is_rejected_by_discovery_helper_only(self):
        with self.assertRaisesRegex(ValueError, "unknown semantic levels"):
            semantics.select_tool_names(["browser_click"], semantic_levels=["L7"])

    def test_project_runner_is_outside_l1_l6(self):
        metadata = semantics.semantic_metadata("browser_run_project")
        self.assertIsNone(metadata["semanticLevel"])
        self.assertEqual(metadata["semanticName"], "project_control")

    def test_lint_reports_upward_dependency_and_cycles(self):
        catalog = {
            "low": semantics.ToolSemantics(
                level="L2",
                semantic_name="browser_transaction",
                composition_kind="composite",
                terminal_state=True,
                default_exposure=True,
                explicit_level_required=False,
                dependencies=("high",),
            ),
            "high": semantics.ToolSemantics(
                level="L4",
                semantic_name="onshape_transaction",
                composition_kind="composite",
                terminal_state=True,
                default_exposure=True,
                explicit_level_required=False,
                dependencies=("low",),
            ),
        }
        errors = semantics.validate_catalog(catalog)
        self.assertTrue(any("lower level depends on higher-level" in item for item in errors))
        self.assertTrue(any("dependency cycle" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
