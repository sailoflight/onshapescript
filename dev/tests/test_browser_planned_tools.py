#!/usr/bin/env python3
"""Offline acceptance tests for the planned browser-tool registry."""

from __future__ import annotations

import json
import re
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from mcp_main.win.mcp import browser_tools, server
from onshape_browser_mode import modeling_transactions, project, selectors, semantic, transactions
from onshape_docs.query.fs_check import check_file, findings_requiring_acknowledgement


PLANNED_NAMES = {
    "browser_fs_goto_definition",
    "browser_fs_insert_snippet",
    "browser_fs_insert_parameter",
    "browser_fs_toggle_fold",
    "browser_edit_feature_parameters",
    "browser_fs_watch_part_studio",
    "browser_drawing_insert_views",
    "browser_draw_part_with_views",
    "browser_wall_thickness_report",
    "browser_apply_blend",
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
    "browser_wall_thickness_report",
    "browser_set_panel_filter",
    "browser_toggle_left_panel",
    "browser_read_selection_preview",
    "browser_element_context_menu",
    "browser_notifications_status",
    "browser_share_document",
    "browser_view_orientation",
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
        self.assertEqual(len(server.TOOLS), 111)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(PLANNED_NAMES.issubset(names))
        self.assertTrue(PLANNED_NAMES.issubset(server.HANDLERS))

    def test_archived_print_tools_are_absent_from_every_table(self):
        """The two print stubs were archived on 2026-09-19 by owner decision.

        An archive that leaves a name behind in a registry, dispatch table,
        project allow-list or outcome map is not an archive, so this asserts
        every table lost the two names together.
        """
        from onshape_browser_mode import semantics

        for name in ("browser_print_orientation_check", "browser_print_optimize_part"):
            with self.subTest(tool=name):
                self.assertNotIn(name, [tool["name"] for tool in server.TOOLS])
                self.assertNotIn(name, server.HANDLERS)
                self.assertNotIn(name, project.ALLOWED_PROJECT_TOOLS)
                self.assertNotIn(name, project.TOOL_OUTCOME_KEYS)
                self.assertNotIn(name, semantics.TOOL_SEMANTICS)
        for function in ("print_orientation_check", "print_optimize_part", "draft_angle_proxy"):
            with self.subTest(function=function):
                self.assertFalse(hasattr(modeling_transactions, function))

    def test_planned_only_registry_lists_filed_rows_but_not_implemented(self):
        root = Path(__file__).resolve().parents[2]
        roadmap = (root / "docs/roadmap/BROWSER_PLANNED_TOOLS.md").read_text(encoding="utf-8")
        # Document inventory / whole-document delete were filed 2026-09-02 after
        # a real dual-environment incident; they are planned, not implemented.
        self.assertIn("## 1a. Planned rows filed 2026-09-02", roadmap)
        self.assertIn("browser_list_documents", roadmap)
        self.assertIn("browser_delete_document", roadmap)
        self.assertNotIn("browser_list_documents", [t["name"] for t in server.TOOLS])
        self.assertNotIn("browser_delete_document", [t["name"] for t in server.TOOLS])

    def test_cost_and_confirmation_metadata_match_behavior(self):
        by_name = {tool["name"]: tool for tool in server.TOOLS}
        for name in PLANNED_NAMES:
            tool = by_name[name]
            # Every tool promoted from the planned registry is a browser tool.
            # The last two `network=offline` rows were the print-analysis stubs,
            # archived on 2026-09-19 (docs/history/legacy/ARCHIVED_BROWSER_PRINT_TOOLS.md).
            self.assertEqual(tool["cost"]["network"], "browser")
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

    def test_draw_workflow_rejects_a_call_with_no_stage_before_mutation(self):
        with mock.patch.object(modeling_transactions, "drawing_insert_views") as insert_views, \
             mock.patch.object(semantic, "add_drawing_dimension") as add_dimension:
            result = modeling_transactions.draw_part_with_views(
                mock.Mock(), part_name="", view_layout="four", dimensions=[]
            )
        self.assertFalse(result["drawn"])
        self.assertFalse(result["browserActionPerformed"])
        insert_views.assert_not_called()
        add_dimension.assert_not_called()

    def test_views_only_stage_inserts_views_without_requesting_a_dimension(self):
        page = mock.Mock()
        with mock.patch.object(
            modeling_transactions, "drawing_insert_views",
            return_value={"viewsInserted": True},
        ) as insert_views, mock.patch.object(semantic, "add_drawing_dimension") as add_dimension:
            result = modeling_transactions.draw_part_with_views(
                page, part_name="Part 1", view_layout="four", dimensions=[]
            )
        insert_views.assert_called_once()
        add_dimension.assert_not_called()
        self.assertTrue(result["drawn"])
        self.assertTrue(result["viewsInserted"])
        self.assertEqual(result["dimensionsRequested"], 0)
        self.assertEqual(result["dimensionsAdded"], 0)

    def test_dimension_only_stage_skips_the_views_stage(self):
        page = mock.Mock()
        dimension = {"tool_selector": "#dim", "geometry_selectors": ["#e"], "verification_selector": "#v"}
        with mock.patch.object(modeling_transactions, "drawing_insert_views") as insert_views, \
             mock.patch.object(
                 semantic, "add_drawing_dimension", return_value={"dimensionAdded": True}
             ) as add_dimension:
            result = modeling_transactions.draw_part_with_views(
                page, part_name="", view_layout="four", dimensions=[dimension]
            )
        insert_views.assert_not_called()
        add_dimension.assert_called_once_with(page, **dimension)
        self.assertTrue(result["drawn"])
        self.assertFalse(result["viewsInserted"])
        self.assertIsNone(result["views"])
        self.assertEqual(result["dimensionsAdded"], 1)

    def test_a_failed_dimension_stage_fails_the_views_only_transaction(self):
        """Two stages in one job still fail as one job."""
        page = mock.Mock()
        dimension = {"tool_selector": "#dim", "geometry_selectors": ["#e"], "verification_selector": "#v"}
        with mock.patch.object(
            modeling_transactions, "drawing_insert_views",
            return_value={"viewsInserted": True},
        ), mock.patch.object(
            semantic, "add_drawing_dimension", return_value={"dimensionAdded": False}
        ):
            result = modeling_transactions.draw_part_with_views(
                page, part_name="Part 1", view_layout="four", dimensions=[dimension]
            )
        self.assertFalse(result["drawn"])
        self.assertEqual(result["dimensionsAdded"], 0)

    def test_legacy_draw_part_rejects_empty_dimensions_before_mutation(self):
        page = mock.Mock()
        with mock.patch.object(semantic, "create_drawing") as create_drawing:
            result = semantic.draw_part(page, source_tab="Part Studio 1", dimensions=[])
        self.assertFalse(result["drawn"])
        self.assertFalse(result["browserActionPerformed"])
        create_drawing.assert_not_called()

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

    def test_the_watch_switch_waits_on_the_toolbar_readback(self):
        """The wait must be ISSUED, not silently skipped.

        This call site passed its argument positionally, which playwright-python
        rejects because ``arg`` is keyword-only; the raise was swallowed by the
        surrounding ``except Exception: pass``, so the wait never happened and
        nothing said so. With a Mock page a positional call still "works", which
        is why the assertion is on ``kwargs["arg"]``: it can only pass when the
        argument really is passed by keyword.
        """
        page = mock.Mock()
        root, current, opener, items, target = (mock.Mock() for _ in range(5))
        for widget in (root, current, opener, items):
            widget.count.return_value = 1
        root.first = root
        current.first = current
        opener.first = opener
        items.first = items
        items.nth.return_value = items
        current.first.inner_text.side_effect = ["监控 Part Studio 1", "监控 PS-Part 1"]
        page.locator.side_effect = lambda selector: {
            selectors.FS_WATCH_CONFIG_MENU: root,
            selectors.FS_WATCH_CONFIG_CURRENT: current,
            selectors.FS_WATCH_CONFIG_OPEN: opener,
            selectors.FS_WATCH_CONFIG_ITEM: items,
        }[selector]
        with mock.patch.object(transactions, "_exact_text", return_value=target), \
             mock.patch.object(
                 transactions.actions, "read_featurescript_compile_status",
                 return_value={"compiled": True},
             ):
            result = transactions.fs_watch_part_studio(page, "PS-Part 1", mode="watch")
        self.assertTrue(result["watchConfigured"])
        self.assertTrue(result["changed"])
        page.wait_for_function.assert_called_once()
        call = page.wait_for_function.call_args
        self.assertEqual(
            len(call.args),
            1,
            "a positional argument means playwright raises TypeError into the swallow",
        )
        self.assertEqual(
            call.kwargs["arg"],
            {"selector": selectors.FS_WATCH_CONFIG_CURRENT, "desired": "监控 PS-Part 1"},
        )

    def test_duplicating_an_element_waits_for_exactly_one_new_tab(self):
        """Same defect, second call site: the new-tab wait is really issued."""
        page = mock.Mock()
        before = {
            "tabs": [{"id": "e1", "name": "Part Studio 1"}, {"id": "e2", "name": "Feature Studio 1"}],
            "hasDocumentTabsToolButton": True,
        }
        after = {
            "tabs": before["tabs"] + [{"id": "e3", "name": "Part Studio 1"}],
            "hasDocumentTabsToolButton": True,
        }
        page.evaluate.side_effect = [before, after]
        page.locator.return_value.count.return_value = 0
        menu_item = mock.Mock()
        with mock.patch.object(
            transactions, "element_context_menu", return_value={"contextMenuOpened": True}
        ), mock.patch.object(transactions, "_exact_text", return_value=menu_item):
            result = transactions.duplicate_element(page, element_id="e1")
        self.assertTrue(result["duplicated"])
        page.wait_for_function.assert_called_once()
        call = page.wait_for_function.call_args
        self.assertEqual(len(call.args), 1, "only the expression may be positional")
        self.assertEqual(call.kwargs["arg"], ["e1", "e2"])

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


class SpiralRidgeGeneratorTest(unittest.TestCase):
    """The generated feature must be editable, not a black box.

    Measured live 2026-09-20 (browser leg, 0 REST quota): the first generated
    spiral published an EMPTY precondition, so Onshape showed its internals
    (fCylinder -> an "extrude", opHelix, sketch+sweep, opBoolean) read-only with
    no editable field at all — visually nothing like an official feature. The
    same session measured the fix: a precondition that declares five
    ``annotation { "Name" … } isLength(definition.…, LengthBoundSpec)``
    parameters makes the custom feature open a real parameter dialog with
    ``Base radius 10 mm / Pitch 6 mm / Ridge width 2 mm / Ridge height 2 mm /
    Length 30 mm``, and editing two of them applied and persisted.

    The other measured half is the naming gate: FeatureScript refuses non-ASCII
    inside ANY annotation string ('Feature Type Name' on the first deploy, every
    ``'Name'`` label on the second), while a non-ASCII ``setProperty`` string
    VALUE compiled clean and displayed as ``螺旋凸棱柱`` in the parts list. So the
    labels are ASCII and the Chinese name lives in the body, and only there.
    """

    #: One row of the measured live dialog, in creation order.
    PARAMETERS = (
        ("Base radius", "baseRadius", 50.0),
        ("Pitch", "pitch", 12.7),
        ("Ridge width", "ridgeWidth", 3.0),
        ("Ridge height", "ridgeHeight", 2.0),
        ("Length", "length", 75.0),
    )

    _SIGNATURE = re.compile(
        r'annotation \{ "Name" : "([^"]+)" \}\s*\n'
        r"\s*isLength\(definition\.(\w+), \{ \(millimeter\) : "
        r"\[([-\d.e+]+), ([-\d.e+]+), ([-\d.e+]+)\] \} as LengthBoundSpec\);"
    )

    @classmethod
    def _source(cls, **overrides):
        values = {
            "base_radius_mm": 50,
            "pitch_mm": 12.7,
            "ridge_width_mm": 3,
            "ridge_height_mm": 2,
            "length_mm": 75,
            "clockwise": True,
        }
        values.update(overrides)
        return modeling_transactions.generate_spiral_ridge_script(**values)

    def test_the_requested_dimensions_become_the_parameter_defaults(self):
        """The default of each parameter is the number the caller asked for."""
        found = self._SIGNATURE.findall(self._source())
        self.assertEqual(
            [(label, name) for label, name, *_ in found],
            [(label, name) for label, name, _ in self.PARAMETERS],
            "the precondition must declare one isLength parameter per dimension",
        )
        for (label, name, requested), (_, _, low, default, high) in zip(self.PARAMETERS, found):
            with self.subTest(parameter=name):
                self.assertEqual(float(default), requested)
                self.assertLessEqual(float(low), requested)
                self.assertGreaterEqual(float(high), requested)

    def test_the_body_recomputes_from_the_parameters_not_from_baked_numbers(self):
        """A baked constant would make the dialog disagree with the geometry."""
        source = self._source()
        self.assertIn("const baseRadius = definition.baseRadius;", source)
        self.assertIn("const length = definition.length;", source)
        body = source.split("    }\n    {\n", 1)[1]
        self.assertIn('"radius" : baseRadius', body)
        self.assertIn('"helicalPitch" : pitch', body)
        self.assertIn("const revolutions = length / pitch;", body)
        for baked in ("50", "12.7", "75"):
            with self.subTest(constant=baked):
                self.assertNotIn(baked, body, "the requested number leaked into the body")
        # The revolution count is the one value the old generator pre-computed in
        # Python; it must stay a FeatureScript expression, or a dialog edit to
        # pitch/length would leave the helix disagreeing with the parameters.
        self.assertNotIn(repr(75 / 12.7), source)
        self.assertNotIn(f"{75 / 12.7:.6f}", source)

    def test_every_annotation_value_is_printable_ascii(self):
        """The exact gate the live server enforced on two deploys."""
        source = self._source()
        annotations = re.findall(r"annotation \{\s*\"([^\"]+)\"\s*:\s*\"([^\"]*)\"\s*\}", source)
        self.assertEqual(len(annotations), 6, "one type name plus five parameter labels")
        for key, value in annotations:
            with self.subTest(key=key):
                self.assertTrue(value, "an empty label is not a label")
                self.assertTrue(
                    all(0x20 <= ord(char) <= 0x7E for char in value),
                    f"annotation {key!r} value {value!r} is not printable ASCII",
                )

    def test_the_chinese_part_name_is_a_body_value_never_an_annotation(self):
        source = self._source()
        self.assertIn('"value" : "螺旋凸棱柱"', source)
        self.assertNotIn("螺旋", source.split("const baseId", 1)[0])
        result = check_file(self._write(source)).as_result()
        self.assertEqual([w for w in result["warnings"] if "non-ASCII" in w], [])

    def test_the_feature_type_name_is_the_stable_ascii_one_instances_use(self):
        self.assertIn(
            'annotation { "Feature Type Name" : "Spiral ridge" }', self._source()
        )

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self._scratch = Path(scratch.name)

    def _write(self, source):
        path = self._scratch / "spiralRidge.fs"
        path.write_text(source, encoding="utf-8")
        return path

    def test_the_generated_script_needs_no_second_confirmation(self):
        """A clean generated source must not trip the acknowledgement gate."""
        checked = check_file(self._write(self._source()))
        result = checked.as_result()
        self.assertEqual(result["errorCount"], 0)
        self.assertEqual(result["errors"], [])
        self.assertEqual(findings_requiring_acknowledgement(result), [])

    def test_an_off_centre_bound_range_still_contains_its_default(self):
        """Callers may pass extremes; the range is derived, never hand-tuned."""
        for label, name, definition_id, requested in (
            ("tiny", "base_radius_mm", "baseRadius", 0.1),
            ("huge", "base_radius_mm", "baseRadius", 10_000.0),
            ("long", "length_mm", "length", 100_000.0),
        ):
            with self.subTest(case=label):
                found = {
                    row[1]: row for row in self._SIGNATURE.findall(self._source(**{name: requested}))
                }
                self.assertIn(definition_id, found)
                _, _, low, default, high = found[definition_id]
                self.assertEqual(float(default), requested)
                self.assertLessEqual(float(low), requested)
                self.assertGreaterEqual(float(high), requested)


if __name__ == "__main__":
    unittest.main()
