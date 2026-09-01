#!/usr/bin/env python3
"""Offline acceptance tests for the planned browser-tool registry."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from mcp_main.win.mcp import browser_tools, server
from onshape_browser_mode import modeling_transactions, project, selectors, semantic, transactions
from onshape_docs.scripts.fs_local_check import check_file


PLANNED_NAMES = {
    "browser_fs_goto_definition",
    "browser_fs_insert_snippet",
    "browser_fs_insert_parameter",
    "browser_fs_toggle_fold",
    "browser_edit_feature_parameters",
    "browser_fs_watch_part_studio",
    "browser_drawing_insert_views",
    "browser_draw_part_with_views",
    "browser_print_orientation_check",
    "browser_wall_thickness_report",
    "browser_apply_blend",
    "browser_print_optimize_part",
    "browser_open_doc_menu",
    "browser_set_panel_filter",
    "browser_toggle_left_panel",
    "browser_read_selection_preview",
    "browser_element_context_menu",
    "browser_duplicate_element",
    "browser_notifications_status",
    "browser_share_document",
    "browser_view_orientation",
    "browser_spiral_ridge",
}

READ_ONLY_NAMES = {
    "browser_fs_goto_definition",
    "browser_fs_toggle_fold",
    "browser_print_orientation_check",
    "browser_print_optimize_part",
    "browser_wall_thickness_report",
    "browser_set_panel_filter",
    "browser_toggle_left_panel",
    "browser_read_selection_preview",
    "browser_element_context_menu",
    "browser_notifications_status",
    "browser_share_document",
    "browser_view_orientation",
}

OFFLINE_NAMES = {
    "browser_print_orientation_check",
    "browser_print_optimize_part",
}


MUTATING_CALLS = {
    "browser_fs_insert_snippet": {"row": 10, "column": 4},
    "browser_fs_insert_parameter": {},
    "browser_edit_feature_parameters": {"feature_name": "Feature", "parameters": {"length": "5 mm"}},
    "browser_fs_watch_part_studio": {"part_studio": "Part Studio 1"},
    "browser_drawing_insert_views": {"part_name": "Part 1"},
    "browser_draw_part_with_views": {
        "part_name": "Part 1",
        "dimensions": [{
            "tool_selector": "#dimension-tool",
            "geometry_selectors": ["#edge-1"],
            "verification_selector": "#dimension-1",
        }],
    },
    "browser_apply_blend": {"targets": ["Edge 1"], "amount": "2 mm"},
    "browser_open_doc_menu": {"command": "工作区属性…"},
    "browser_duplicate_element": {"element_id": "e1"},
    "browser_spiral_ridge": {
        "base_radius_mm": 50,
        "pitch_mm": 12.7,
        "ridge_width_mm": 3,
        "ridge_height_mm": 2,
        "length_mm": 75,
    },
}


class PlannedRegistryTest(unittest.TestCase):
    def test_app_shell_selectors_match_live_evidence(self):
        root = Path(__file__).resolve().parents[2]
        evidence = json.loads((root / "dev/button-map/scan-app-shell.json").read_text(encoding="utf-8"))["verifiedSelectors"]
        self.assertEqual(selectors.DOC_NAME, evidence["documentName"])
        self.assertEqual(selectors.DOC_MENU, evidence["documentMenu"])
        self.assertEqual(selectors.PANEL_ROOT, evidence["panelRoot"])
        self.assertEqual(selectors.PANEL_FILTER, evidence["panelFilter"])
        self.assertEqual(selectors.PANEL_CONTENT, evidence["panelContent"])
        self.assertEqual(selectors.PANEL_SPLITTERS, evidence["panelSplitters"])
        self.assertEqual(selectors.DOCUMENTS_NOTIFICATION, evidence["notifications"])
        self.assertEqual(selectors.SHARE_BUTTON, evidence["shareButton"])
        self.assertEqual(selectors.SHARE_DIALOG, evidence["shareDialog"])
        self.assertEqual(selectors.VIEW_CUBE, evidence["viewCube"])
        self.assertEqual(selectors.DRAFT_ANALYSIS_DIALOG, evidence["draftAnalysisDialog"])
        self.assertEqual(selectors.DRAFT_DIRECTION, evidence["draftDirection"])
        self.assertEqual(selectors.DRAFT_MINIMUM_ANGLE, evidence["draftMinimumAngle"])
        self.assertEqual(selectors.PS_PART_ROW, evidence["partRow"])
        fs_evidence = json.loads((root / "dev/button-map/scan-fs-editor.json").read_text(encoding="utf-8"))["selectors"]
        self.assertEqual(selectors.FS_WATCH_CONFIG_MENU, fs_evidence["watchMenu"])
        self.assertEqual(selectors.FS_WATCH_CONFIG_OPEN, fs_evidence["watchMenuOpen"])
        self.assertEqual(selectors.FS_WATCH_CONFIG_CURRENT, fs_evidence["watchCurrent"])
        self.assertEqual(selectors.FS_WATCH_CONFIG_ITEM, fs_evidence["watchItems"])

    def test_all_planned_names_are_registered_once(self):
        names = [tool["name"] for tool in server.TOOLS]
        self.assertEqual(len(server.TOOLS), 104)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(PLANNED_NAMES.issubset(names))
        self.assertTrue(PLANNED_NAMES.issubset(server.HANDLERS))

    def test_planned_only_registry_has_no_tool_rows(self):
        root = Path(__file__).resolve().parents[2]
        roadmap = (root / "docs/roadmap/BROWSER_PLANNED_TOOLS.md").read_text(encoding="utf-8")
        self.assertIn("no unimplemented browser-tool rows", roadmap)
        self.assertFalse(any(line.startswith("| `browser_") for line in roadmap.splitlines()))

    def test_cost_and_confirmation_metadata_match_behavior(self):
        by_name = {tool["name"]: tool for tool in server.TOOLS}
        for name in PLANNED_NAMES:
            tool = by_name[name]
            self.assertEqual(
                tool["cost"]["network"],
                "offline" if name in OFFLINE_NAMES else "browser",
            )
            self.assertEqual(tool["cost"]["max_api_requests"], 0)
            self.assertEqual(tool["annotations"]["readOnlyHint"], name in READ_ONLY_NAMES)
            properties = tool["inputSchema"]["properties"]
            if name in READ_ONLY_NAMES:
                self.assertNotIn("confirm_mutation", properties, name)
            else:
                self.assertIn("confirm_mutation", properties, name)
                self.assertIn("dry_run", properties, name)

    def test_high_level_schemas_hide_raw_code_css_and_coordinates(self):
        by_name = {tool["name"]: tool for tool in server.TOOLS}
        self.assertNotIn("snippet", by_name["browser_fs_insert_snippet"]["inputSchema"]["properties"])
        self.assertNotIn("parameter_source", by_name["browser_fs_insert_parameter"]["inputSchema"]["properties"])
        self.assertNotIn("point", by_name["browser_view_orientation"]["inputSchema"]["properties"])
        self.assertNotIn("selector", by_name["browser_read_selection_preview"]["inputSchema"]["properties"])
        self.assertNotIn("frame_url", by_name["browser_drawing_insert_views"]["inputSchema"]["properties"])
        self.assertNotIn("frame_url", by_name["browser_draw_part_with_views"]["inputSchema"]["properties"])
        self.assertNotIn("menu_item", by_name["browser_fs_watch_part_studio"]["inputSchema"]["properties"])
        self.assertEqual(by_name["browser_element_context_menu"]["inputSchema"]["required"], ["element_id"])

    def test_all_mutating_dry_runs_are_pure_local(self):
        with mock.patch.object(browser_tools, "_page", side_effect=AssertionError("session started")):
            for name, args in MUTATING_CALLS.items():
                result = browser_tools.BROWSER_HANDLERS[name]({**args, "dry_run": True})
                self.assertTrue(result["dryRun"], name)
                self.assertEqual(result["estimatedApiRequests"], 0, name)

    def test_all_mutating_calls_gate_before_session(self):
        with mock.patch.object(browser_tools, "_page", side_effect=AssertionError("session started")):
            for name, args in MUTATING_CALLS.items():
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError, "confirm_mutation"):
                        browser_tools.BROWSER_HANDLERS[name](args)


class TransactionAcceptanceTest(unittest.TestCase):
    def test_blank_png_has_no_view_ink_evidence(self):
        def chunk(kind: bytes, payload: bytes) -> bytes:
            return struct.pack(">I", len(payload)) + kind + payload + b"\0\0\0\0"

        blank = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\xff\xff\xff"))
            + chunk(b"IEND", b"")
        )
        metrics = modeling_transactions._png_ink_metrics(blank)
        self.assertTrue(metrics["readable"])
        self.assertLess(metrics["interiorInkRatio"], 0.008)
        self.assertLess(metrics["peakToMedianInk"], 2.0)

    def test_real_drawing_view_fixture_has_pixel_acceptance_evidence(self):
        root = Path(__file__).resolve().parents[2]
        evidence = json.loads((root / "dev/button-map/scan-app-shell.json").read_text(encoding="utf-8"))
        observed = evidence["observations"]["drawingCanvasEvidence"]
        metrics = modeling_transactions._png_ink_metrics((root / observed["file"]).read_bytes())
        self.assertTrue(metrics["readable"])
        self.assertGreaterEqual(metrics["interiorInkRatio"], 0.008)
        self.assertGreaterEqual(metrics["peakToMedianInk"], 2.0)
        self.assertAlmostEqual(metrics["interiorInkRatio"], observed["interiorInkRatio"])

    def test_project_runner_requires_tool_specific_outcome(self):
        self.assertTrue(project._step_ok("browser_drawing_insert_views", {"viewsInserted": True}))
        self.assertFalse(project._step_ok("browser_drawing_insert_views", {"drawn": True}))
        self.assertFalse(project._step_ok("browser_unknown", {"ok": True}))

    def test_fold_returns_normalized_acceptance(self):
        page = mock.Mock()
        page.evaluate.return_value = {
            "foldChanged": True,
            "action": "toggle",
            "row": 10,
            "beforeFolds": [],
            "foldedRanges": [{"startRow": 10, "endRow": 20}],
            "foldCount": 1,
        }
        result = transactions.fs_toggle_fold(page, row=10)
        self.assertTrue(result["foldChanged"])
        self.assertEqual(result["foldedRanges"][0]["endRow"], 20)

    def test_draw_workflow_rejects_empty_dimensions_before_mutation(self):
        with mock.patch.object(modeling_transactions, "drawing_insert_views") as insert_views, \
             mock.patch.object(semantic, "add_drawing_dimension") as add_dimension:
            result = modeling_transactions.draw_part_with_views(
                mock.Mock(), part_name="Part 1", view_layout="four", dimensions=[]
            )
        self.assertFalse(result["drawn"])
        self.assertFalse(result["browserActionPerformed"])
        insert_views.assert_not_called()
        add_dimension.assert_not_called()

    def test_legacy_draw_part_rejects_empty_dimensions_before_mutation(self):
        page = mock.Mock()
        with mock.patch.object(semantic, "create_drawing") as create_drawing:
            result = semantic.draw_part(page, source_tab="Part Studio 1", dimensions=[])
        self.assertFalse(result["drawn"])
        self.assertFalse(result["browserActionPerformed"])
        create_drawing.assert_not_called()

    def test_print_orientation_rejects_draft_analysis_without_browser_action(self):
        page = mock.Mock()
        result = modeling_transactions.print_orientation_check(
            page,
            body_name="Part 1",
            build_direction="+z",
            max_overhang_angle_degrees=45,
        )
        self.assertFalse(result["orientationChecked"])
        self.assertFalse(result["assessable"])
        self.assertFalse(result["fdmCapable"])
        self.assertEqual(result["semanticValidity"], "invalid")
        self.assertEqual(result["risk"], "unknown")
        self.assertFalse(result["browserActionPerformed"])
        page.assert_not_called()

    def test_print_optimize_stops_before_browser_or_blend(self):
        args = {
            "body_name": "Part 1",
            "blend": {"operation": "fillet", "targets": ["Edge 1"], "amount": "2 mm"},
            "orientation": {"build_direction": "+z", "max_overhang_angle_degrees": 45},
            "wall": {"minimum_allowed_mm": 1.2, "samples": ["Face 1"]},
        }
        with mock.patch.object(browser_tools, "_page", side_effect=AssertionError("session started")), \
             mock.patch.object(modeling_transactions, "apply_blend", side_effect=AssertionError("blend attempted")):
            result = browser_tools.browser_print_optimize_part(args)
        self.assertFalse(result["optimized"])
        self.assertEqual(result["semanticValidity"], "invalid")
        self.assertFalse(result["mutationAttempted"])
        self.assertEqual(result["failedStage"], "orientation")

    def test_watch_target_accepts_exact_already_configured_readback(self):
        page = mock.Mock()
        root = mock.Mock()
        current = mock.Mock()
        root.count.return_value = 1
        current.count.return_value = 1
        current.first = current
        current.inner_text.return_value = "监控 PS-PartA-wall"
        page.locator.side_effect = lambda selector: current if selector == selectors.FS_WATCH_CONFIG_CURRENT else root
        with mock.patch.object(transactions.actions, "read_featurescript_compile_status", return_value={"compiled": True}):
            result = transactions.fs_watch_part_studio(page, "PS-PartA-wall", mode="watch")
        self.assertTrue(result["watchConfigured"])
        self.assertTrue(result["alreadyConfigured"])
        self.assertFalse(result["changed"])

    def test_wall_report_requires_explicit_samples(self):
        page = mock.Mock()
        row = mock.Mock()
        row.count.return_value = 1
        row.first = row
        row.filter.return_value = row
        page.locator.return_value = row
        result = modeling_transactions.wall_thickness_report(
            page, body_name="Part 1", minimum_allowed_mm=1.2, samples=[]
        )
        self.assertFalse(result["wallThicknessMeasured"])
        self.assertEqual(result["coverage"], "unknown")
        self.assertFalse(result["globalMinimumVerified"])

    def test_quantity_parser_normalizes_sample_units(self):
        parsed = modeling_transactions._quantities("distance 1.2 mm, angle 47 deg, width 0.1 in")
        self.assertEqual(parsed[0], {"value": 1.2, "unit": "mm"})
        self.assertEqual(parsed[1], {"value": 47.0, "unit": "deg"})
        self.assertEqual(parsed[2], {"value": 0.1, "unit": "in"})

    def test_spiral_rejects_self_intersecting_profile_before_session(self):
        args = dict(MUTATING_CALLS["browser_spiral_ridge"])
        args["ridge_width_mm"] = args["pitch_mm"]
        with mock.patch.object(browser_tools, "_page", side_effect=AssertionError("session started")):
            with self.assertRaisesRegex(ValueError, "smaller than pitch"):
                browser_tools.browser_spiral_ridge({**args, "confirm_mutation": True})

    def test_spiral_script_passes_local_static_checker(self):
        source = modeling_transactions.generate_spiral_ridge_script(
            base_radius_mm=50,
            pitch_mm=12.7,
            ridge_width_mm=3,
            ridge_height_mm=2,
            length_mm=75,
            clockwise=True,
        )
        self.assertIn("opHelix", source)
        self.assertIn("opSweep", source)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spiralRidge.fs"
            path.write_text(source, encoding="utf-8")
            checked = check_file(path)
        self.assertEqual(checked.errors, [])


if __name__ == "__main__":
    unittest.main()
