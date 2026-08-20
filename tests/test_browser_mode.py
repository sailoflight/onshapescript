#!/usr/bin/env python3
"""Offline unit tests for the browser-mode action guard and browser_* handlers.

Everything here runs without Playwright: the handlers are driven with fake
session/page/locator objects, and the pacing guard is exercised with injected
clock / sleep / rng so no wall-clock delay or real randomness is used. No
Onshape API request and no browser launch happens anywhere in this file.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main import server  # noqa: E402
from onshape_browser_mode.guard import ActionGuard, ActionRateExceeded  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes (no Playwright import anywhere)
# ---------------------------------------------------------------------------

class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordingSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class FixedRng:
    def __init__(self, value: float) -> None:
        self.value = value

    def uniform(self, a: float, b: float) -> float:
        return self.value


class FakeLocator:
    def __init__(self, count: int = 1, info: dict | None = None,
                 evaluate_error: Exception | None = None) -> None:
        self._count = count
        self._info = info or {"tag": "button", "text": "Create", "href": "",
                              "aria": "", "id": "create", "cls": "tool"}
        self._evaluate_error = evaluate_error
        self.click_calls = 0
        self.dblclick_calls = 0
        self.scroll_calls = 0
        self.evaluate_calls: list[object] = []
        self.nth_calls: list[int] = []
        self.fill_calls: list[str] = []

    def fill(self, value: str) -> None:
        self.fill_calls.append(value)

    def dblclick(self) -> None:
        self.dblclick_calls += 1

    def count(self) -> int:
        return self._count

    def nth(self, index: int) -> "FakeLocator":
        self.nth_calls.append(index)
        return self

    def evaluate(self, js: str, *args) -> dict:
        self.evaluate_calls.append((js, args))
        if self._evaluate_error is not None:
            raise self._evaluate_error
        return dict(self._info)

    def scroll_into_view_if_needed(self) -> None:
        self.scroll_calls += 1

    def click(self) -> None:
        self.click_calls += 1


class FakePage:
    def __init__(self, url: str = "https://cad.onshape.com/documents",
                 locator: FakeLocator | None = None,
                 text_locator: FakeLocator | None = None,
                 evaluate_result: object | None = None) -> None:
        self._url = url
        self._locator = locator
        self._text_locator = text_locator
        self._evaluate_result = evaluate_result
        self.wait_for_timeout_calls: list[float] = []
        self.evaluate_calls: list[tuple] = []
        self.goto_calls: list[tuple] = []
        self.locator_selector: str | None = None
        self.get_by_text_arg: str | None = None

    @property
    def url(self) -> str:
        return self._url

    def locator(self, selector: str) -> FakeLocator:
        self.locator_selector = selector
        return self._locator if self._locator is not None else FakeLocator()

    def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
        self.get_by_text_arg = text
        return self._text_locator if self._text_locator is not None else FakeLocator()

    def goto(self, url: str, **kwargs) -> None:
        self.goto_calls.append((url, kwargs))

    def wait_for_timeout(self, ms: float) -> None:
        self.wait_for_timeout_calls.append(ms)

    def evaluate(self, js: str, *args) -> object:
        self.evaluate_calls.append((js, args))
        if self._evaluate_result is not None:
            return self._evaluate_result
        return {"target": "window", "scrolledBy": 800, "scrollY": 800,
                "scrollHeight": 3000, "clientHeight": 800}


class FakeSession:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.start_calls = 0
        self.enforce_calls = 0

    def start(self) -> FakePage:
        self.start_calls += 1
        return self.page

    def _enforce_single_working_page(self, page) -> None:
        self.enforce_calls += 1


class FakeGuard:
    def __init__(self) -> None:
        self.pace_calls = 0
        self.raise_on_pace: Exception | None = None

    def pace(self) -> None:
        self.pace_calls += 1
        if self.raise_on_pace is not None:
            raise self.raise_on_pace


# ---------------------------------------------------------------------------
# ActionGuard (direct, no Playwright)
# ---------------------------------------------------------------------------

class ActionGuardTest(unittest.TestCase):
    def make_guard(self, cap: int, clock: FakeClock, sleep: RecordingSleep,
                   rng: FixedRng | None = None, min_d: float = 0.0, max_d: float = 0.0):
        return ActionGuard(
            max_actions_per_minute=cap,
            min_delay_s=min_d,
            max_delay_s=max_d,
            clock=clock,
            sleep=sleep,
            rng=rng if rng is not None else FixedRng(0.0),
        )

    def test_rate_cap_raises_when_window_full(self) -> None:
        clock = FakeClock()
        guard = self.make_guard(2, clock, RecordingSleep())
        guard.pace()
        guard.pace()
        self.assertEqual(guard.recent_action_count(), 2)
        with self.assertRaises(ActionRateExceeded):
            guard.pace()

    def test_window_prunes_after_a_minute(self) -> None:
        clock = FakeClock()
        guard = self.make_guard(2, clock, RecordingSleep())
        guard.pace()
        guard.pace()
        with self.assertRaises(ActionRateExceeded):
            guard.pace()
        clock.advance(61.0)  # the two old actions leave the 60s window
        guard.pace()  # now allowed again
        self.assertEqual(guard.recent_action_count(), 1)

    def test_randomized_delay_is_slept_and_in_range(self) -> None:
        clock = FakeClock()
        sleep = RecordingSleep()
        guard = self.make_guard(8, clock, sleep, rng=FixedRng(1.5),
                                min_d=1.0, max_d=2.0)
        guard.pace()
        self.assertEqual(sleep.calls, [1.5])
        self.assertEqual(guard.delay_seconds(), 1.5)

    def test_zero_delay_sleeps_nothing(self) -> None:
        clock = FakeClock()
        sleep = RecordingSleep()
        guard = self.make_guard(8, clock, sleep, rng=FixedRng(0.0))
        guard.pace()
        self.assertEqual(sleep.calls, [])


# ---------------------------------------------------------------------------
# browser_click / browser_eval / browser_scroll handlers (fake session/page)
# ---------------------------------------------------------------------------

class BrowserClickTest(unittest.TestCase):
    def setUp(self) -> None:
        self.locator = FakeLocator(count=1)
        self.page = FakePage(locator=self.locator)
        self.session = FakeSession(self.page)
        self.guard = FakeGuard()

    def test_actual_click_requires_confirmation(self) -> None:
        with mock.patch("onshape_browser_mode.session.get_session", return_value=self.session):
            with self.assertRaises(ValueError) as ctx:
                server._browser_click({"selector": ".os-primary"})
        self.assertIn("confirm_mutation", str(ctx.exception))
        self.assertEqual(self.locator.click_calls, 0)
        self.assertEqual(self.session.start_calls, 0)

    def test_dry_run_inspects_without_confirmation_and_no_side_effect(self) -> None:
        with mock.patch("onshape_browser_mode.session.get_session", return_value=self.session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=self.guard):
            result = server._browser_click({"selector": ".os-primary", "dry_run": True})
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["wouldClick"]["tag"], "button")
        self.assertEqual(result["matchCount"], 1)
        # Inspection read the element, but nothing was clicked/scrolled/paced.
        self.assertTrue(self.locator.evaluate_calls)
        self.assertEqual(self.locator.click_calls, 0)
        self.assertEqual(self.locator.scroll_calls, 0)
        self.assertEqual(self.guard.pace_calls, 0)

    def test_confirmed_click_clicks_and_paces(self) -> None:
        with mock.patch("onshape_browser_mode.session.get_session", return_value=self.session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=self.guard):
            result = server._browser_click(
                {"selector": ".os-primary", "confirm_mutation": True})
        self.assertTrue(result["clicked"])
        self.assertEqual(self.locator.click_calls, 1)
        self.assertEqual(self.locator.scroll_calls, 1)
        self.assertEqual(self.guard.pace_calls, 1)

    def test_no_match_makes_no_action_or_pace(self) -> None:
        self.locator = FakeLocator(count=0)
        self.page = FakePage(locator=self.locator)
        self.session = FakeSession(self.page)
        with mock.patch("onshape_browser_mode.session.get_session", return_value=self.session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=self.guard):
            result = server._browser_click(
                {"selector": ".missing", "confirm_mutation": True})
        self.assertFalse(result["clicked"])
        self.assertEqual(result["reason"], "no matching element")
        self.assertEqual(self.guard.pace_calls, 0)
        self.assertEqual(self.locator.click_calls, 0)


class BrowserEvalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.page = FakePage()
        self.session = FakeSession(self.page)
        self.guard = FakeGuard()

    def test_execution_requires_confirmation(self) -> None:
        with mock.patch("onshape_browser_mode.session.get_session", return_value=self.session):
            with self.assertRaises(ValueError) as ctx:
                server._browser_eval({"expression": "1 + 1"})
        self.assertIn("confirm_mutation", str(ctx.exception))
        self.assertEqual(self.session.start_calls, 0)
        self.assertEqual(self.page.evaluate_calls, [])

    def test_dry_run_returns_metadata_without_evaluating(self) -> None:
        with mock.patch("onshape_browser_mode.session.get_session", return_value=self.session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=self.guard):
            result = server._browser_eval(
                {"expression": "document.title", "dry_run": True, "arg": {"x": 1}})
        self.assertTrue(result["dryRun"])
        self.assertFalse(result["evaluated"])
        self.assertEqual(result["expressionLength"], len("document.title"))
        self.assertTrue(result["argProvided"])
        self.assertEqual(self.session.start_calls, 0)
        self.assertEqual(self.page.evaluate_calls, [])
        self.assertEqual(self.guard.pace_calls, 0)

    def test_confirmed_eval_executes_and_paces(self) -> None:
        self.page = FakePage(evaluate_result=42)
        self.session = FakeSession(self.page)
        with mock.patch("onshape_browser_mode.session.get_session", return_value=self.session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=self.guard):
            result = server._browser_eval(
                {"expression": "1 + 1", "confirm_mutation": True})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], 42)
        self.assertEqual(len(self.page.evaluate_calls), 1)
        self.assertEqual(self.guard.pace_calls, 1)


class BrowserScrollTest(unittest.TestCase):
    def test_scroll_is_paced(self) -> None:
        page = FakePage()
        session = FakeSession(page)
        guard = FakeGuard()
        with mock.patch("onshape_browser_mode.session.get_session", return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard):
            result = server._browser_scroll({"direction": "down", "amount": 400})
        self.assertEqual(result["direction"], "down")
        self.assertEqual(guard.pace_calls, 1)
        self.assertEqual(len(page.evaluate_calls), 1)


class BrowserDeployTest(unittest.TestCase):
    def test_deploy_requires_confirmation_when_not_dry_run(self) -> None:
        session = FakeSession(FakePage())
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session) as get_session, \
             mock.patch("onshape_browser_mode.actions.read_featurescript_editor",
                        side_effect=AssertionError("must not read editor before confirmation")), \
             mock.patch("onshape_browser_mode.actions.write_featurescript_editor",
                        side_effect=AssertionError("must not write before confirmation")), \
             mock.patch("onshape_browser_mode.actions.click_commit",
                        side_effect=AssertionError("must not commit before confirmation")):
            with self.assertRaises(ValueError) as ctx:
                server._browser_deploy_featurescript(
                    {"script": "feature X {}", "dry_run": False})
        self.assertIn("confirm_mutation", str(ctx.exception))
        get_session.assert_not_called()          # refused before any browser import
        self.assertEqual(session.start_calls, 0)  # no session started

    def test_deploy_dry_run_is_pure_local_preview(self) -> None:
        session = FakeSession(FakePage())
        source = "feature X {}\n// two lines"
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session) as get_session, \
             mock.patch("onshape_browser_mode.guard.get_guard",
                        side_effect=AssertionError("dry run must not touch the guard")), \
             mock.patch("onshape_browser_mode.actions.read_featurescript_editor",
                        side_effect=AssertionError("dry run must not read the editor")), \
             mock.patch("onshape_browser_mode.actions.write_featurescript_editor",
                        side_effect=AssertionError("dry run must not write the editor")), \
             mock.patch("onshape_browser_mode.actions.click_commit",
                        side_effect=AssertionError("dry run must not click Commit")):
            result = server._browser_deploy_featurescript(
                {"script": source, "dry_run": True})
        self.assertTrue(result["dryRun"])
        self.assertFalse(result["deployed"])
        self.assertEqual(result["documentName"],
                         "Branch Cable Trophy Display - FeatureScript")
        self.assertEqual(result["sourceLength"], len(source))
        self.assertEqual(result["lineCount"], 2)
        self.assertIn("no browser session", result["note"])
        get_session.assert_not_called()          # no session import/start/actions
        self.assertEqual(session.start_calls, 0)

    def test_deploy_commits_with_confirmation_and_paces(self) -> None:
        session = FakeSession(FakePage())
        guard = FakeGuard()
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.read_featurescript_editor",
                        return_value="old source"), \
             mock.patch("onshape_browser_mode.actions.write_featurescript_editor",
                        return_value={"ok": True, "length": 9, "lineCount": 1}) as write, \
             mock.patch("onshape_browser_mode.actions.click_commit",
                        return_value={"clicked": True}) as commit:
            result = server._browser_deploy_featurescript(
                {"script": "feature X {}", "dry_run": False, "confirm_mutation": True})
        self.assertTrue(result["deployed"])
        self.assertFalse(result["dryRun"])
        self.assertEqual(session.start_calls, 1)
        write.assert_called_once()
        commit.assert_called_once()
        # Pacing enforced before the editor write and before the Commit click
        # (the editor is already on screen, so no navigation pacing is added).
        self.assertEqual(guard.pace_calls, 2)


class BrowserInsertCustomFeatureTest(unittest.TestCase):
    def test_insert_requires_confirmation(self) -> None:
        session = FakeSession(FakePage())
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session) as get_session, \
             mock.patch("onshape_browser_mode.actions.insert_custom_feature",
                        side_effect=AssertionError("must not insert before confirmation")):
            with self.assertRaises(ValueError) as ctx:
                server._browser_insert_custom_feature({"feature_name": "Bc"})
        self.assertIn("confirm_mutation", str(ctx.exception))
        get_session.assert_not_called()
        self.assertEqual(session.start_calls, 0)

    def test_confirmed_insert_delegates_and_paces(self) -> None:
        session = FakeSession(FakePage())
        guard = FakeGuard()
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.insert_custom_feature",
                        return_value={"inserted": True}) as insert:
            result = server._browser_insert_custom_feature(
                {"feature_name": "Bc", "part_studio_tab": "Part Studio 1",
                 "confirm_mutation": True})
        self.assertTrue(result["inserted"])
        insert.assert_called_once()
        self.assertEqual(session.start_calls, 1)
        self.assertEqual(guard.pace_calls, 1)


class BrowserCreateDocumentTest(unittest.TestCase):
    def test_create_requires_confirmation(self) -> None:
        session = FakeSession(FakePage())
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session) as get_session, \
             mock.patch("onshape_browser_mode.actions.create_document",
                        side_effect=AssertionError("must not create before confirmation")):
            with self.assertRaises(ValueError) as ctx:
                server._browser_create_document({"name": "test-doc"})
        self.assertIn("confirm_mutation", str(ctx.exception))
        get_session.assert_not_called()
        self.assertEqual(session.start_calls, 0)

    def test_confirmed_create_calls_action_and_paces(self) -> None:
        session = FakeSession(FakePage())
        guard = FakeGuard()
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.create_document",
                        return_value={"created": True, "pageUrl": "https://cad.onshape.com/documents/d1/w/w1",
                                      "documentId": "d1", "workspaceId": "w1", "elementId": None}) as create:
            result = server._browser_create_document(
                {"name": "test-doc", "confirm_mutation": True})
        self.assertTrue(result["created"])
        self.assertEqual(result["documentId"], "d1")
        self.assertEqual(result["workspaceId"], "w1")
        create.assert_called_once()
        self.assertEqual(session.start_calls, 1)
        self.assertEqual(guard.pace_calls, 1)


# ---------------------------------------------------------------------------
# Cost metadata <-> mutation behavior consistency
# ---------------------------------------------------------------------------

class BrowserMetadataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.by_name = {t["name"]: t for t in server.TOOLS}

    def test_click_and_eval_are_mutating_with_zero_api_requests(self) -> None:
        for name in ("browser_click", "browser_eval"):
            tool = self.by_name[name]
            cost = tool["cost"]
            self.assertTrue(cost["mutating"], name)
            self.assertEqual(cost["remote_ui_mutation"], "possible", name)
            self.assertEqual(cost["estimated_requests"], 0, name)
            self.assertEqual(cost["max_requests"], 0, name)
            self.assertEqual(cost["estimated_api_requests"], 0, name)
            self.assertFalse(tool["annotations"]["readOnlyHint"], name)
            self.assertIn("confirm_mutation", tool["inputSchema"]["properties"], name)

    def test_deploy_is_mutating_with_confirmation_in_schema(self) -> None:
        tool = self.by_name["browser_deploy_featurescript"]
        self.assertTrue(tool["cost"]["mutating"])
        self.assertEqual(tool["cost"]["estimated_requests"], 0)
        self.assertFalse(tool["annotations"]["readOnlyHint"])
        self.assertIn("confirm_mutation", tool["inputSchema"]["properties"])

    def test_scroll_and_inspect_stay_read_only(self) -> None:
        for name in ("browser_scroll", "browser_inspect", "browser_session"):
            tool = self.by_name[name]
            self.assertFalse(tool["cost"]["mutating"], name)
            self.assertTrue(tool["annotations"]["readOnlyHint"], name)
            self.assertEqual(tool["cost"]["estimated_requests"], 0, name)

    def test_tool_count_unchanged(self) -> None:
        self.assertEqual(len(server.TOOLS), 47)


if __name__ == "__main__":
    unittest.main()
