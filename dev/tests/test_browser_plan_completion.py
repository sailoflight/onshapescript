#!/usr/bin/env python3
"""Offline tests for the completed browser development plan."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main.win.mcp import browser_tools, server  # noqa: E402
from onshape_browser_mode import interaction, listener, project, semantic  # noqa: E402
from onshape_browser_mode.pages import (  # noqa: E402
    AmbiguousFrameError,
    AssemblyPage,
    DocumentsPage,
    DrawingPage,
    FeatureStudioPage,
    FrameNotFoundError,
    PartStudioPage,
    resolve_scope,
    scope_url,
)
from onshape_rest_api_mode import operations  # noqa: E402


class FakeLocator:
    def __init__(self, count: int = 1) -> None:
        self._count = count
        self.wait_calls = []
        self.press_calls = []
        self.type_calls = []
        self.click_calls = []
        self.filter_text = None

    @property
    def first(self):
        return self

    def nth(self, _index):
        return self

    def filter(self, has_text=""):
        self.filter_text = has_text
        return self

    def count(self):
        return self._count

    def wait_for(self, **kwargs):
        self.wait_calls.append(kwargs)

    def click(self, **kwargs):
        self.click_calls.append(kwargs)

    def press(self, key):
        self.press_calls.append(key)

    def press_sequentially(self, text, **kwargs):
        self.type_calls.append((text, kwargs))

    def evaluate(self, _script):
        return {"tag": "input", "text": "", "aria": "", "title": "", "id": "x", "cls": ""}

    def screenshot(self, path, full_page=False):
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\nfake-png-bytes")
        return {"bytes": 21, "fullPage": full_page}


class FakeScope:
    def __init__(self, url="https://cad.onshape.com/documents/d/w/w/e/e") -> None:
        self.url = url
        self.target = FakeLocator()
        self.evaluate_calls = []
        self.load_calls = []
        self.function_calls = []

    def locator(self, _selector):
        return self.target

    def get_by_text(self, _text, exact=False):
        return self.target

    def evaluate(self, expression, *args):
        self.evaluate_calls.append((expression, args))
        return {"scope": self.url}

    def wait_for_load_state(self, state, **kwargs):
        self.load_calls.append((state, kwargs))

    def wait_for_function(self, expression, arg, **kwargs):
        self.function_calls.append((expression, arg, kwargs))


class FakePage(FakeScope):
    def __init__(self, frames=None):
        super().__init__()
        self.frames = frames or []
        self.url_calls = []

    def wait_for_url(self, pattern, **kwargs):
        self.url_calls.append((pattern, kwargs))


class FakeSession:
    def __init__(self, page):
        self.page = page
        self.start_calls = 0

    def start(self):
        self.start_calls += 1
        return self.page

    def _enforce_single_working_page(self, _page):
        return None


class PageObjectAndFrameTest(unittest.TestCase):
    def test_tooltip_sensitive_selectors_accept_bootstrap_relocation(self):
        from onshape_browser_mode import selectors
        self.assertIn("data-bs-original-title", selectors.ASM_INSERT_BUTTON)
        self.assertIn("data-bs-original-title", selectors.PS_WORKSPACE_CUSTOM_FEATURE_BTN)
        evidence = json.loads((ROOT / "dev/button-map/scan-assembly-instances.json").read_text(encoding="utf-8"))
        self.assertEqual(selectors.ASM_INSTANCE_ROW, evidence["instanceRowSelector"])
        self.assertEqual(selectors.ASM_INSERT_ROW, evidence["insertSourceRowSelector"])
        self.assertIn(evidence["insertDialogSelector"], selectors.ASM_INSERT_DIALOG)
        self.assertEqual(selectors.ASM_INSERT_ACCEPT, evidence["insertAcceptSelector"])

    def test_all_planned_page_objects_exist(self):
        for cls in (DocumentsPage, FeatureStudioPage, PartStudioPage, AssemblyPage):
            self.assertIsNotNone(cls(FakePage()).scope)

    def test_frame_resolution_is_unique_and_drawing_defaults_to_drawing_frame(self):
        drawing = FakeScope("https://production-drawing-us.onshape.com/editor")
        page = FakePage([FakeScope("https://cad.onshape.com"), drawing])
        self.assertIs(resolve_scope(page, "production-drawing-"), drawing)
        self.assertIs(DrawingPage(page).scope, drawing)
        drawing.url += "?userId=secret#fragment"
        self.assertEqual(scope_url(drawing), "https://production-drawing-us.onshape.com/editor")
        with self.assertRaises(FrameNotFoundError):
            resolve_scope(page, "missing-frame")
        duplicate = FakeScope("https://production-drawing-eu.onshape.com/editor")
        with self.assertRaises(AmbiguousFrameError):
            resolve_scope(FakePage([drawing, duplicate]), "production-drawing-")

    def test_existing_eval_routes_to_requested_frame(self):
        frame = FakeScope("https://production-drawing-us.onshape.com/editor")
        page = FakePage([frame])
        session = FakeSession(page)
        guard = mock.Mock()
        with mock.patch("onshape_browser_mode.session.get_session", return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard):
            result = server._browser_eval({
                "expression": "() => 1", "frame_url": "production-drawing-",
                "confirm_mutation": True,
            })
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["scope"], frame.url)
        self.assertEqual(len(frame.evaluate_calls), 1)

    def test_frame_inspect_preserves_main_page_url(self):
        frame = FakeScope("https://production-drawing-us.onshape.com/editor")
        frame.evaluate = mock.Mock(return_value={
            "url": frame.url, "title": "Drawing", "elements": [],
        })
        page = FakePage([frame])
        page.url = "https://cad.onshape.com/documents/d/w/w/e/e"
        session = FakeSession(page)
        session.status = mock.Mock(return_value={"pages": []})
        session._load_saved_app_url = mock.Mock(return_value=None)
        with mock.patch("onshape_browser_mode.session.get_session", return_value=session):
            result = server._browser_inspect({"frame_url": "production-drawing-"})
        self.assertEqual(result["pageUrl"], page.url)
        self.assertEqual(result["frameUrl"], frame.url)


class GenericInteractionTest(unittest.TestCase):
    def test_wait_conditions_are_bounded_and_frame_aware(self):
        frame = FakeScope("https://production-drawing-us.onshape.com/editor")
        page = FakePage([frame])
        result = interaction.wait_for_condition(
            page, condition="visible", selector="#dimension", frame_url="production-drawing-", timeout_ms=500,
        )
        self.assertTrue(result["waited"])
        self.assertEqual(frame.target.wait_calls, [{"state": "visible", "timeout": 500}])

    def test_press_and_type_use_trusted_locator_input(self):
        page = FakePage()
        pressed = interaction.press_key(page, key="Enter", selector="#name")
        typed = interaction.type_text(page, text="42 mm", selector="#value", clear=True, delay_ms=10)
        self.assertTrue(pressed["pressed"])
        self.assertTrue(typed["typed"])
        self.assertIn("Enter", page.target.press_calls)
        self.assertIn("Control+A", page.target.press_calls)
        self.assertEqual(page.target.type_calls[-1], ("42 mm", {"delay": 10}))

    def test_mutating_tools_require_confirmation_before_session(self):
        calls = {
            "browser_press_key": {"key": "Enter", "selector": "#x"},
            "browser_type": {"text": "x", "selector": "#x"},
            "browser_sync_rest_state": {"action": "from_args", "document_id": "d", "workspace_id": "w"},
            "browser_insert_assembly_instances": {"instance_names": ["A"], "instance_selector": ".ns-tree-root .ns-assembly-instance-row.is-instance"},
            "browser_fix_instances": {"instance_names": ["A"], "instance_selector": ".ns-tree-root .ns-assembly-instance-row.is-instance"},
            "browser_group_instances": {"instance_names": ["A"], "instance_selector": ".ns-tree-root .ns-assembly-instance-row.is-instance"},
            "browser_create_drawing": {"source_tab": "Part Studio 1"},
            "browser_add_drawing_dimension": {"tool_selector": "#dim", "geometry_selectors": ["#edge"], "verification_selector": "#dimension-node"},
            "browser_delete_element": {"element_id": "e1"},
            "browser_deploy_and_apply_featurescript": {"script": "FeatureScript 1;", "feature_name": "F"},
            "browser_build_part": {"feature_name": "F"},
            "browser_assemble": {"instance_names": ["A"], "instance_selector": ".ns-tree-root .ns-assembly-instance-row.is-instance"},
            "browser_draw_part": {"source_tab": "Part Studio 1"},
            "browser_run_project": {},
        }
        with mock.patch.object(browser_tools, "_page", side_effect=AssertionError("session started")):
            for name, args in calls.items():
                with self.subTest(name=name), self.assertRaises(ValueError):
                    browser_tools.BROWSER_HANDLERS[name](args)

    def test_all_mutating_dry_runs_are_pure_local(self):
        samples = {
            "browser_press_key": {"key": "Enter", "selector": "#x"},
            "browser_type": {"text": "x", "selector": "#x"},
            "browser_sync_rest_state": {"action": "from_args", "document_id": "d", "workspace_id": "w"},
            "browser_insert_assembly_instances": {"instance_names": ["A"], "instance_selector": ".ns-tree-root .ns-assembly-instance-row.is-instance"},
            "browser_fix_instances": {"instance_names": ["A"], "instance_selector": ".ns-tree-root .ns-assembly-instance-row.is-instance"},
            "browser_group_instances": {"instance_names": ["A"], "instance_selector": ".ns-tree-root .ns-assembly-instance-row.is-instance"},
            "browser_create_drawing": {"source_tab": "PS"},
            "browser_add_drawing_dimension": {"tool_selector": "#dim", "geometry_selectors": ["#edge"], "verification_selector": "#dimension-node"},
            "browser_delete_element": {"element_id": "e1"},
            "browser_deploy_and_apply_featurescript": {"script": "FeatureScript 1;", "feature_name": "F"},
            "browser_build_part": {"feature_name": "F"},
            "browser_assemble": {"instance_names": ["A"], "instance_selector": ".ns-tree-root .ns-assembly-instance-row.is-instance"},
            "browser_draw_part": {"source_tab": "PS"},
            "browser_run_project": {},
        }
        with mock.patch.object(browser_tools, "_page", side_effect=AssertionError("session started")):
            for name, args in samples.items():
                with self.subTest(name=name):
                    result = browser_tools.BROWSER_HANDLERS[name]({**args, "dry_run": True})
                    self.assertTrue(result["dryRun"])


class StateSyncTest(unittest.TestCase):
    def test_browser_ids_merge_without_clobbering_rest_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "onshape-state.json"
            path.write_text(json.dumps({"apiQuota": {"annualLimit": 10}, "featureStudioId": "keep"}), encoding="utf-8")
            with mock.patch.object(operations, "STATE_PATH", path):
                result = operations.sync_browser_state(
                    document_id="d1", workspace_id="w1", element_id="p1",
                    element_name="Part Studio 1", element_type="PART_STUDIO",
                    tabs=[{"id": "f1", "name": "Feature Studio 1", "elementType": "FEATURE_STUDIO"}],
                )
            state = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(result["synced"])
        self.assertEqual(state["partStudioId"], "p1")
        self.assertEqual(state["featureStudioId"], "keep")
        self.assertEqual(state["apiQuota"]["annualLimit"], 10)
        self.assertEqual({item["id"] for item in state["elements"]}, {"p1", "f1"})


class SemanticOperationTest(unittest.TestCase):
    def test_part_summary_normalizes_count_and_names(self):
        result = semantic.parse_part_summary("零件数 (2)\nFixed wall (rail)\nModule block (groove)")
        self.assertEqual(result["parts"], 2)
        self.assertEqual(result["partNames"], ["Fixed wall (rail)", "Module block (groove)"])

    def test_collapsed_multi_part_text_does_not_invent_names(self):
        result = semantic.parse_part_summary("零件数 (2) Fixed wall Module block")
        self.assertEqual(result["parts"], 2)
        self.assertEqual(result["partNames"], [])
        self.assertFalse(result["partNamesParsed"])

    def test_create_drawing_dialog_path_still_requires_frame(self):
        page = mock.Mock()
        page.url = "https://cad.onshape.com/documents/d/w/w/e/e"
        page.frames = []
        dialog = mock.Mock()
        dialog.count.return_value = 1
        source = mock.Mock()
        source.count.return_value = 1
        dialog.get_by_text.return_value = source
        accept = mock.Mock()
        accept.count.return_value = 1
        dialog.locator.return_value = accept
        page.locator.return_value = dialog
        with mock.patch("onshape_browser_mode.actions.create_document_tab", return_value={
            "created": False, "triggered": True,
        }), mock.patch("onshape_browser_mode.actions.list_document_tabs", return_value={
            "tabs": [{"name": "Drawing 1"}],
        }):
            result = semantic.create_drawing(page, "Part Studio 1")
        self.assertFalse(result["created"])

    def test_canvas_dimension_dry_run_needs_no_session(self):
        with mock.patch.object(browser_tools, "_page", side_effect=AssertionError("session started")):
            result = browser_tools.browser_add_drawing_dimension({
                "tool_key": "d",
                "geometry_points": [{"x": 10, "y": 20}, {"x": 30, "y": 40}],
                "placement_point": {"x": 50, "y": 60},
                "dry_run": True,
            })
        self.assertTrue(result["dryRun"])

    def test_draw_part_rejects_incomplete_dimension_before_session(self):
        with mock.patch.object(browser_tools, "_page", side_effect=AssertionError("session started")):
            with self.assertRaises(ValueError):
                browser_tools.browser_draw_part({
                    "source_tab": "PS",
                    "dimensions": [{"tool_selector": "#dim", "geometry_selectors": ["#edge"]}],
                    "confirm_mutation": True,
                })

    def test_deploy_requires_commit_acceptance_not_only_click(self):
        with mock.patch("onshape_browser_mode.actions.read_featurescript_editor", side_effect=["old", "new"]), \
             mock.patch("onshape_browser_mode.actions.write_featurescript_editor", return_value={"ok": True, "length": 3}), \
             mock.patch("onshape_browser_mode.actions.click_commit", return_value={
                 "clicked": True, "before": {"disabled": False}, "after": {"disabled": False},
             }):
            result = semantic.deploy_featurescript(mock.Mock(), "new")
        self.assertFalse(result["deployed"])
        self.assertTrue(result["verified"])
        self.assertFalse(result["commitAccepted"])

    def test_deploy_requires_enabled_to_disabled_commit_transition(self):
        with mock.patch("onshape_browser_mode.actions.read_featurescript_editor", side_effect=["old", "new"]), \
             mock.patch("onshape_browser_mode.actions.write_featurescript_editor", return_value={"ok": True, "length": 3}), \
             mock.patch("onshape_browser_mode.actions.click_commit", return_value={
                 "clicked": True, "before": {"disabled": False}, "after": {"disabled": True},
             }):
            result = semantic.deploy_featurescript(mock.Mock(), "new")
        self.assertTrue(result["deployed"])
        self.assertTrue(result["commitAccepted"])

    def test_insert_assembly_separates_source_and_expected_names(self):
        assembly = mock.Mock()
        assembly.insert_row.side_effect = lambda name: mock.Mock(
            count=mock.Mock(return_value=1), click=mock.Mock(), source=name
        )
        page = mock.Mock()
        page.url = "https://cad.onshape.com/documents/d/w/w/e/e"
        with mock.patch("onshape_browser_mode.semantic.AssemblyPage", return_value=assembly), \
             mock.patch("onshape_browser_mode.semantic.read_instance_visibility", return_value={
                 "visibleInstances": ["Part A", "Part B"], "missingInstances": [],
             }):
            result = semantic.insert_assembly_instances(
                page, ["Part A", "Part B"],
                source_names=["PS-A", "PS-B"],
            )
        self.assertTrue(result["inserted"])
        self.assertEqual(assembly.insert_row.call_args_list, [mock.call("PS-A"), mock.call("PS-B")])
        self.assertEqual(result["selected"], ["PS-A", "PS-B"])

    def test_build_rejects_stale_parts_without_target_user_feature(self):
        features = {
            "partsText": "零件数 (1) Old part",
            "features": [{"name": "Old feature", "isUserFeature": True}],
        }
        with mock.patch("onshape_browser_mode.actions.insert_custom_feature", return_value={
            "inserted": True, "features": features,
        }):
            result = semantic.build_part(mock.Mock(), "New feature")
        self.assertFalse(result["built"])
        self.assertFalse(result["featurePresent"])

    def test_create_drawing_does_not_claim_ready_without_frame(self):
        page = mock.Mock()
        page.url = "https://cad.onshape.com/documents/d/w/w/e/e"
        page.frames = []
        with mock.patch("onshape_browser_mode.actions.create_document_tab", return_value={
            "created": True, "triggered": True,
        }):
            result = semantic.create_drawing(page, "Part Studio 1")
        self.assertFalse(result["created"])
        self.assertIn("not ready", result["reason"])

    def test_canvas_dimension_requires_screenshot_change(self):
        canvas = mock.Mock()
        canvas.nth.return_value = canvas
        canvas.screenshot.side_effect = [b"before", b"after", b"after"]
        body = mock.Mock()
        scope = mock.Mock()
        scope.locator.side_effect = lambda selector: body if selector == "body" else canvas
        drawing = mock.Mock(scope=scope, url="https://production-drawing.example/editor")
        drawing.state.return_value = {"readable": True}
        page = mock.Mock()
        with mock.patch("onshape_browser_mode.semantic.DrawingPage", return_value=drawing):
            result = semantic.add_drawing_dimension(
                page, tool_key="d", canvas_selector="canvas", canvas_index=1,
                geometry_points=[{"x": 10, "y": 20}, {"x": 30, "y": 40}],
                placement_point={"x": 50, "y": 60},
            )
        self.assertTrue(result["dimensionAdded"])
        self.assertEqual(result["verification"], "stable-canvas-screenshot-changed")
        self.assertEqual(canvas.click.call_count, 3)
        canvas.focus.assert_called_once_with()
        canvas.press.assert_has_calls([mock.call("d"), mock.call("Escape")])
        page.mouse.move.assert_called_once_with(1, 1)
        self.assertTrue(result["postRenderStable"])

    def test_drawing_dimension_requires_observed_count_increase(self):
        frame = mock.Mock()
        frame.url = "https://production-drawing-us.onshape.com/editor"
        verification = mock.Mock()
        verification.count.side_effect = [0, 1]
        clickable = mock.Mock()
        clickable.first = clickable
        def locate(selector):
            return verification if selector == ".dimension-node" else clickable
        frame.locator.side_effect = locate
        frame.evaluate.return_value = {"svgCount": 1}
        page = mock.Mock()
        page.frames = [frame]
        result = semantic.add_drawing_dimension(
            page, tool_selector="#dimension", geometry_selectors=["#edge"],
            verification_selector=".dimension-node",
        )
        self.assertTrue(result["dimensionAdded"])
        self.assertEqual((result["beforeCount"], result["afterCount"]), (0, 1))

    def test_project_fixture_is_complete_and_secret_free(self):
        loaded = project.load_project("module-interface-verification")
        self.assertEqual(len(loaded["steps"]), 6)
        self.assertEqual(loaded["steps"][-1]["tool"], "browser_draw_part")


class WatchAndProjectTest(unittest.TestCase):
    def test_watch_rejects_path_shaped_workflow_before_session(self):
        with mock.patch("onshape_browser_mode.session.get_session") as get_session:
            with self.assertRaises(ValueError):
                server._browser_watch({"action": "start", "workflow": "../escape"})
        get_session.assert_not_called()

    def test_watch_verify_requires_explicit_template(self):
        with self.assertRaises(ValueError):
            server._browser_watch({"action": "verify"})

    def test_watch_start_resets_tracked_pages(self):
        from types import SimpleNamespace
        cfg = SimpleNamespace(listener=SimpleNamespace(
            record_dom_snippets=False, record_network=False, output_dir="dev/watch-sessions",
        ))
        recorder = listener.WatchRecorder(cfg)
        old_page = mock.Mock()
        recorder.pages[id(old_page)] = old_page
        page = mock.Mock()
        page.url = "https://cad.onshape.com/documents"
        recorder.start(page, None, "sample")
        self.assertEqual(set(recorder.pages), {id(page)})
        self.assertEqual(recorder._attached.get(id(page)), page)
        self.assertNotIn(id(old_page), recorder._attached)

    def test_watch_sequence_verifier(self):
        template = json.loads((ROOT / "dev/fixtures-capture/watch/fs-edit-submit.template.json").read_text(encoding="utf-8"))
        events = [
            {"kind": "url_change", "tag": "documents"},
            {"kind": "dom", "action": "click", "text": "Feature Studio 1"},
            {"kind": "dom", "action": "input"},
            {"kind": "dom", "action": "click", "text": "提交"},
            {"kind": "network", "tag": "featurestudio", "status": 204},
        ]
        self.assertTrue(listener.verify_watch_recording(events, template)["ok"])
        self.assertFalse(listener.verify_watch_recording(events[:2], template)["ok"])
        self.assertEqual(listener.sanitize_url("https://example.test/path?token=secret#x"), "https://example.test/path")

    def test_project_failure_checkpoint_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "fixtures"
            checkpoints = root / "runs"
            projects.mkdir()
            fixture = {
                "name": "sample",
                "steps": [
                    {"id": "one", "tool": "browser_build_part", "args": {}},
                    {"id": "two", "tool": "browser_assemble", "args": {"prior": "{{result.one.value}}"}},
                ],
            }
            (projects / "sample.json").write_text(json.dumps(fixture), encoding="utf-8")
            calls = []
            def failing(tool, args):
                calls.append((tool, args))
                return {"ok": True, "value": "v1"} if tool == "browser_build_part" else {"ok": False}
            failed = project.run_project("sample", executor=failing, projects_dir=projects, checkpoint_dir=checkpoints)
            self.assertEqual(failed["completed"], ["one"])
            self.assertEqual(failed["failed"]["id"], "two")
            resumed_calls = []
            def succeeding(tool, args):
                resumed_calls.append((tool, args))
                return {"ok": True}
            resumed = project.run_project("sample", executor=succeeding, resume=True, projects_dir=projects, checkpoint_dir=checkpoints)
            self.assertTrue(resumed["ok"])
            self.assertEqual(resumed_calls, [("browser_assemble", {"prior": "v1"})])

    def test_project_rejects_unregistered_step_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixtures = Path(tmp)
            (fixtures / "bad.json").write_text(json.dumps({
                "name": "bad", "steps": [{"id": "x", "tool": "browser_eval", "args": {}}],
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                project.load_project("bad", fixtures)

    def test_resume_rejects_changed_project_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures = root / "fixtures"
            runs = root / "runs"
            fixtures.mkdir()
            fixture = {
                "name": "changed",
                "steps": [{"id": "one", "tool": "browser_build_part", "args": {}}],
            }
            path = fixtures / "changed.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            project.run_project(
                "changed", executor=lambda _tool, _args: {"ok": True},
                projects_dir=fixtures, checkpoint_dir=runs,
            )
            fixture["description"] = "new plan"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            with self.assertRaises(ValueError):
                project.run_project(
                    "changed", executor=lambda _tool, _args: {"ok": True},
                    resume=True, projects_dir=fixtures, checkpoint_dir=runs,
                )

    def test_project_dry_run_needs_no_executor_or_checkpoint(self):
        result = project.run_project("module-interface-verification", dry_run=True)
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["stepCount"], 6)


class HandlerCompositionTest(unittest.TestCase):
    def test_sync_from_args_never_starts_browser(self):
        with mock.patch("onshape_rest_api_mode.operations.sync_browser_state", return_value={"synced": True}) as sync, \
             mock.patch.object(browser_tools, "_page", side_effect=AssertionError("browser started")):
            result = browser_tools.browser_sync_rest_state({
                "action": "from_args", "document_id": "d1", "workspace_id": "w1",
                "confirm_mutation": True,
            })
        self.assertTrue(result["synced"])
        sync.assert_called_once()

    def test_deploy_apply_composes_version_and_build(self):
        page = mock.Mock()
        guard = mock.Mock()
        with mock.patch.object(browser_tools, "_page", return_value=(page, guard)), \
             mock.patch.object(browser_tools, "_ensure_tab", side_effect=[{"created": True}, {"created": True}]), \
             mock.patch("onshape_browser_mode.semantic.deploy_featurescript", return_value={"deployed": True, "verified": True}), \
             mock.patch("onshape_browser_mode.semantic.build_part", return_value={"built": True, "parts": 1, "partNames": ["Part"]}), \
             mock.patch("onshape_browser_mode.actions.open_insert_custom_feature_dialog"), \
             mock.patch("onshape_browser_mode.actions.read_insert_dialog", return_value={"promptSaveVersion": True}), \
             mock.patch("onshape_browser_mode.actions.create_document_version", return_value={"created": True}) as version:
            result = browser_tools.browser_deploy_and_apply_featurescript({
                "script": "FeatureScript 1;", "feature_name": "F",
                "confirm_mutation": True, "create_version": True,
            })
        self.assertTrue(result["deployed"])
        self.assertTrue(result["built"])
        self.assertEqual(result["parts"], 1)
        version.assert_called_once()
        self.assertGreaterEqual(guard.pace.call_count, 4)

    def test_assemble_and_draw_delegate_to_semantic_layer(self):
        page = mock.Mock()
        guard = mock.Mock()
        with mock.patch.object(browser_tools, "_page", return_value=(page, guard)), \
             mock.patch.object(browser_tools, "_ensure_tab", return_value={"created": True}), \
             mock.patch("onshape_browser_mode.semantic.assemble", return_value={"assembled": True}) as assemble, \
             mock.patch("onshape_browser_mode.semantic.draw_part", return_value={"drawn": True}) as draw:
            assembled = browser_tools.browser_assemble({
                "instance_names": ["A", "B"], "instance_selector": ".ns-tree-root .ns-assembly-instance-row.is-instance", "confirm_mutation": True,
            })
            drawn = browser_tools.browser_draw_part({
                "source_tab": "PS", "confirm_mutation": True,
            })
        self.assertTrue(assembled["assembled"])
        self.assertTrue(drawn["drawn"])
        assemble.assert_called_once()
        draw.assert_called_once()

    def test_watch_save_is_bounded_and_header_free(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            cfg = SimpleNamespace(listener=SimpleNamespace(
                record_dom_snippets=True, record_network=True, output_dir=tmp,
            ))
            recorder = listener.WatchRecorder(cfg)
            recorder.workflow = "sample"
            recorder.events = [{"kind": "network", "url": "https://example", "status": 200}]
            saved = recorder.save()
            payload = Path(saved["path"]).read_text(encoding="utf-8")
        lowered = payload.lower()
        self.assertNotIn("authorization", lowered)
        self.assertNotIn("cookie", lowered)
        self.assertNotIn("requestbody", lowered)
        listener_source = (ROOT / "onshape_browser_mode/listener.py").read_text(encoding="utf-8")
        self.assertNotIn("el.value", listener_source)
        self.assertIn("<CHAR>", listener_source)
        with self.assertRaises(ValueError):
            recorder.save("../escape.json")


class PlannedMetadataTest(unittest.TestCase):
    def test_registry_and_cost_contract(self):
        by_name = {tool["name"]: tool for tool in server.TOOLS}
        self.assertEqual(len(by_name), 68)
        before = len(server.TOOLS)
        browser_tools.install(server.TOOLS, server.HANDLERS)
        self.assertEqual(len(server.TOOLS), before)
        for name in ("browser_inspect", "browser_scroll", "browser_click", "browser_eval"):
            self.assertIn("frame_url", by_name[name]["inputSchema"]["properties"])
        for name in browser_tools.BROWSER_HANDLERS:
            tool = by_name[name]
            self.assertEqual(tool["cost"]["estimated_api_requests"], 0)
            self.assertEqual(tool["cost"]["max_api_requests"], 0)
        # Read-only browser tools need no mutation confirmation and are marked
        # read-only; all other browser handlers are mutating and must gate on it.
        for name in browser_tools.BROWSER_HANDLERS:
            if name in {"browser_wait", "browser_capture_screenshot"}:
                self.assertNotIn("confirm_mutation", by_name[name]["inputSchema"]["properties"])
                self.assertTrue(by_name[name]["annotations"]["readOnlyHint"])
                continue
            self.assertIn("confirm_mutation", by_name[name]["inputSchema"]["properties"])
            self.assertFalse(by_name[name]["annotations"]["readOnlyHint"])

        capture = by_name["browser_capture_screenshot"]
        self.assertEqual(capture["cost"]["estimated_requests"], 0)
        self.assertTrue(capture["annotations"]["openWorldHint"])
        self.assertTrue(capture["annotations"]["readOnlyHint"])
        self.assertFalse(capture["annotations"]["destructiveHint"])
        self.assertIn("dry_run", capture["inputSchema"]["properties"])
        self.assertIn("output_dir", capture["inputSchema"]["properties"])


class ScreenshotToolTest(unittest.TestCase):
    def test_dry_run_is_pure_local(self):
        with mock.patch.object(browser_tools, "_page", side_effect=AssertionError("session started")):
            result = browser_tools.browser_capture_screenshot({
                "selector": ".features-title", "dry_run": True,
            })
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["estimatedApiRequests"], 0)
        self.assertIn("outputPath", result)

    def test_relative_output_dir_must_stay_in_repo_root(self):
        with self.assertRaises(ValueError):
            browser_tools.browser_capture_screenshot({
                "output_dir": "../escape", "filename": "x.png", "dry_run": True,
            })

    def test_handler_persists_png_and_returns_sha(self):
        import hashlib as hl
        payload = b"\x89PNG\r\n\x1a\nfake-png-bytes"
        page = FakePage()
        page.screenshot = lambda path, full_page=False: Path(path).write_bytes(payload)
        page.target.screenshot = lambda path, full_page=False: Path(path).write_bytes(payload)
        page.target.wait_for = lambda **kw: None
        session = FakeSession(page)
        guard = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            # Patch _repo_root so the screenshot lands inside the temporary root.
            with mock.patch.object(browser_tools, "_repo_root", return_value=Path(tmp)), \
                 mock.patch("onshape_browser_mode.session.get_session", return_value=session), \
                 mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
                 mock.patch.object(browser_tools, "_page", return_value=(page, guard)):
                out_dir = Path(tmp) / "dev" / "screenshots"
                out_dir.mkdir(parents=True)
                result = browser_tools.browser_capture_screenshot({
                    "selector": ".features-title", "output_dir": "dev/screenshots",
                    "filename": "shot", "data_url": True,
                })
                # The persisted file must be readable by vision/read_image tools.
                persisted = (out_dir / "shot.png").read_bytes()
            self.assertTrue(result["captured"])
            self.assertEqual(result["fileName"], "shot.png")
            self.assertEqual(result["bytes"], len(payload))
            self.assertEqual(result["sha256"], hl.sha256(payload).hexdigest())
            self.assertTrue(result["dataUrl"].startswith("data:image/png;base64,"))
            self.assertEqual(persisted, payload)


if __name__ == "__main__":
    unittest.main()
