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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main.win.mcp import server  # noqa: E402
from onshape_browser_mode import actions, selectors  # noqa: E402
from onshape_browser_mode.guard import ActionGuard, ActionRateExceeded  # noqa: E402
from onshape_browser_mode.session import (  # noqa: E402
    BrowserSession,
    _browser_launch_error_message,
)


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
        self.click_kwargs: list[dict] = []
        self.dblclick_kwargs: list[dict] = []
        self.scroll_calls = 0
        self.evaluate_calls: list[object] = []
        self.nth_calls: list[int] = []
        self.fill_calls: list[str] = []

    def fill(self, value: str) -> None:
        self.fill_calls.append(value)

    def dblclick(self, **kwargs) -> None:
        self.dblclick_calls += 1
        self.dblclick_kwargs.append(kwargs)

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

    def click(self, **kwargs) -> None:
        self.click_calls += 1
        self.click_kwargs.append(kwargs)


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
        self.release_calls = 0

    def start(self) -> FakePage:
        self.start_calls += 1
        return self.page

    def _enforce_single_working_page(self, page) -> None:
        self.enforce_calls += 1

    def release(self) -> dict:
        self.release_calls += 1
        return {
            "released": True,
            "alreadyReleased": False,
            "sessionStatus": "closed",
            "profileReleased": True,
        }


class FakeGuard:
    def __init__(self) -> None:
        self.pace_calls = 0
        self.raise_on_pace: Exception | None = None

    def pace(self) -> None:
        self.pace_calls += 1
        if self.raise_on_pace is not None:
            raise self.raise_on_pace


# ---------------------------------------------------------------------------
# BrowserSession lifecycle (no Playwright import or browser launch)
# ---------------------------------------------------------------------------

class BrowserSessionReleaseTest(unittest.TestCase):
    def started_session(self):
        # Exercise the actual shared owner via its native factory protocol.
        import tempfile
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        context = mock.Mock()
        page = mock.Mock()
        page.url = "https://cad.onshape.com/documents/d/w/w/e/e"
        page.context = context
        page.is_closed.return_value = False
        context.pages = [page]
        playwright = mock.Mock()
        playwright.chromium.launch_persistent_context.return_value = context
        manager = mock.Mock()
        manager.start.return_value = playwright
        session = BrowserSession(playwright_factory=lambda: manager)
        with mock.patch.object(session, "profile_dir", return_value=Path(directory.name)):
            session.start()
        return session, context, playwright, page

    def test_release_closes_context_stops_playwright_and_resets_state(self) -> None:
        session, context, playwright, page = self.started_session()
        session.login_confirmed = True
        session.human_action_required = True

        result = session.release()

        context.close.assert_called_once_with()
        playwright.stop.assert_called_once_with()
        self.assertTrue(result["released"])
        self.assertTrue(result["profileReleased"])
        self.assertFalse(result["alreadyReleased"])
        self.assertEqual(result["previousSessionStatus"], "started")
        self.assertEqual(result["previousPageUrl"], page.url)
        self.assertEqual(result["sessionStatus"], "closed")
        self.assertIsNone(session.context)
        self.assertIsNone(session.page)
        self.assertFalse(session.login_confirmed)
        self.assertFalse(session.human_action_required)

    def test_release_is_idempotent_before_browser_start(self) -> None:
        session = BrowserSession()

        result = session.release()

        self.assertFalse(result["released"])
        self.assertTrue(result["alreadyReleased"])
        self.assertTrue(result["profileReleased"])
        self.assertEqual(result["previousSessionStatus"], "uninitialized")
        self.assertEqual(result["sessionStatus"], "closed")

    def test_release_falls_back_to_browser_close(self) -> None:
        session, context, playwright, page = self.started_session()
        browser = mock.Mock()
        context.close.side_effect = RuntimeError("context close failed")
        context.browser = browser

        result = session.release()

        browser.close.assert_called_once_with()
        self.assertTrue(result["released"])
        self.assertEqual(result["releaseMethod"], "browser.close-fallback")
        self.assertEqual("context.close failed: RuntimeError", result["warnings"][0])

    def test_release_does_not_claim_profile_released_when_close_fails(self) -> None:
        session, context, playwright, page = self.started_session()
        browser = mock.Mock()
        browser.close.side_effect = RuntimeError("browser close failed")
        context.close.side_effect = [RuntimeError("context close failed"), None]
        context.browser = browser

        first = session.release()

        self.assertFalse(first["released"])
        self.assertFalse(first["profileReleased"])
        self.assertEqual(first["sessionStatus"], "release_failed")
        self.assertIs(session.context, context)
        self.assertEqual(len(first["warnings"]), 2)
        self.assertIn("request Operator recovery", first["message"])

        second = session.release()
        self.assertTrue(second["released"])
        self.assertTrue(second["profileReleased"])
        self.assertFalse(second["alreadyReleased"])
        self.assertEqual(second["sessionStatus"], "closed")

    def test_launch_error_points_to_owner_release_and_bridge_enforcement(self) -> None:
        message = _browser_launch_error_message(
            channel="msedge",
            profile_dir=Path(r"C:\MCP\onshapescript\onshape_browser_mode\user_data\onshape_profile"),
            error=RuntimeError("Target page, context or browser has been closed"),
        )
        self.assertIn("another mcp/browser process may own", message.lower())
        self.assertIn("browser_session(action='release')", message)
        self.assertIn("multiProcessAllowed=false", message)
        self.assertIn("Do not delete profile lock files", message)

    def test_stdio_shutdown_still_closes_started_owner(self) -> None:
        import onshape_browser_mode.session as session_module

        owned = mock.Mock()
        owned._status = "started"
        with mock.patch.object(session_module, "_session", owned):
            server._shutdown_browser_session()
        owned.close.assert_called_once_with()

    def test_stdio_shutdown_closes_partial_uninitialized_owner(self) -> None:
        import onshape_browser_mode.session as session_module

        partial = mock.Mock()
        partial._status = "uninitialized"
        with mock.patch.object(session_module, "_session", partial):
            server._shutdown_browser_session()
        partial.close.assert_called_once_with()

    def test_browser_session_release_handler_does_not_start_browser(self) -> None:
        session = FakeSession(FakePage())
        with mock.patch("onshape_browser_mode.session.get_session", return_value=session):
            result = server._browser_session({"action": "release"})
        self.assertTrue(result["released"])
        self.assertEqual(session.release_calls, 1)
        self.assertEqual(session.start_calls, 0)

    def test_browser_session_rejects_unknown_action_with_release_guidance(self) -> None:
        with self.assertRaisesRegex(ValueError, "status, login, release, reconnect, or reload"):
            server._browser_session({"action": "close"})

    def test_session_reconnect_action_runs_the_absorbed_core(self) -> None:
        session = FakeSession(FakePage())
        guard = FakeGuard()
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.reconnect_if_needed",
                        return_value={"reconnected": True}) as reconnect:
            result = server._browser_session({"action": "reconnect"})
        self.assertTrue(result["reconnected"])
        reconnect.assert_called_once()
        self.assertEqual(session.start_calls, 1)
        self.assertEqual(guard.pace_calls, 1)

    def test_absorbed_session_names_keep_their_contract_and_say_where_they_went(self) -> None:
        """A merge keeps the old name callable: same behaviour, plus a pointer."""
        for name, action in (("browser_reconnect", "reconnect"), ("browser_reload", "reload")):
            with self.subTest(tool=name):
                with mock.patch.object(
                    server, "_browser_session", return_value={"reloaded": True}
                ) as session:
                    result = server.HANDLERS[name]({})
                session.assert_called_once_with({"action": action})
                self.assertTrue(result["deprecated"])
                self.assertEqual(result["useInstead"], "browser_session")
                self.assertEqual(result["sessionAction"], action)
                self.assertTrue(result["reloaded"])


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
            result = server._browser_click({
                "selector": ".os-primary", "double": True,
                "modifiers": ["Shift"], "dry_run": True,
            })
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["wouldClick"]["tag"], "button")
        self.assertEqual(result["matchCount"], 1)
        self.assertTrue(result["double"])
        self.assertEqual(result["modifiers"], ["Shift"])
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

    def test_modifiers_are_forwarded_to_single_and_double_clicks(self) -> None:
        patches = (
            mock.patch("onshape_browser_mode.session.get_session", return_value=self.session),
            mock.patch("onshape_browser_mode.guard.get_guard", return_value=self.guard),
        )
        with patches[0], patches[1]:
            server._browser_click({
                "selector": ".os-primary", "modifiers": ["Control"],
                "confirm_mutation": True,
            })
            server._browser_click({
                "selector": ".os-primary", "double": True, "modifiers": ["Shift"],
                "confirm_mutation": True,
            })
        self.assertEqual(self.locator.click_kwargs, [{"modifiers": ["Control"]}])
        self.assertEqual(self.locator.dblclick_kwargs, [{"modifiers": ["Shift"]}])

    def test_invalid_modifiers_fail_before_starting_session(self) -> None:
        with mock.patch("onshape_browser_mode.session.get_session", return_value=self.session):
            with self.assertRaises(ValueError):
                server._browser_click({
                    "selector": ".os-primary", "modifiers": ["Ctrl"],
                    "confirm_mutation": True,
                })
        self.assertEqual(self.session.start_calls, 0)

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
        # The local check is free and side-effect-free, so it runs even in a
        # pure preview and never touches the browser.
        self.assertTrue(result["localCheck"]["checked"])
        self.assertTrue(result["localCheck"]["advisory"])
        get_session.assert_not_called()          # no session import/start/actions
        self.assertEqual(session.start_calls, 0)

    def test_deploy_preview_surfaces_local_check_findings(self) -> None:
        # The preview reports a defect the live server accepts at save time (a
        # non-map third argument to an op* call), so it is visible before any
        # commit is spent. The finding is advisory, so the preview still runs.
        script = (
            'FeatureScript 3044;\n'
            'import(path : "onshape/std/geometry.fs", version : "3044.0");\n'
            'export const f = defineFeature(function(context is Context, id is Id, definition is map)\n'
            '    precondition { annotation { "Name" : "F" } }\n'
            '    {\n'
            '        opExtrude(context, id + "e", 5);\n'
            '    });\n'
        )
        seen = server._browser_deploy_featurescript({"script": script, "dry_run": True})
        self.assertTrue(seen["dryRun"])
        self.assertEqual(seen["localCheck"]["errorCount"], 0)   # advisory, not a gate
        self.assertGreaterEqual(seen["localCheck"]["warningCount"], 1)
        self.assertIn("opExtrude", " ".join(seen["localCheck"]["warnings"]))

    def test_deploy_preview_still_reports_structural_local_errors(self) -> None:
        result = server._browser_deploy_featurescript(
            {"script": "FeatureScript 3044;\nvar x = 1;", "dry_run": True})
        self.assertFalse(result["localCheck"]["clear"])
        self.assertGreaterEqual(result["localCheck"]["errorCount"], 1)

    def test_deploy_asks_once_for_structural_local_findings(self) -> None:
        """A local finding warns and asks again; it never blocks the write."""
        session = FakeSession(FakePage())
        script = "FeatureScript 3044;\nvar x = 1;"
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session) as get_session, \
             mock.patch("onshape_browser_mode.guard.get_guard",
                        side_effect=AssertionError("must not touch the guard")), \
             mock.patch("onshape_browser_mode.actions.write_featurescript_editor",
                        side_effect=AssertionError("must not write before acknowledgement")):
            result = server._browser_deploy_featurescript(
                {"script": script, "dry_run": False, "confirm_mutation": True})
        self.assertTrue(result["acknowledgementRequired"])
        self.assertEqual(result["tool"], "browser_deploy_featurescript")
        self.assertGreaterEqual(len(result["localFindings"]), 1)
        self.assertEqual(result["nextCall"]["arguments"]["acknowledge_local_findings"], True)
        self.assertTrue(result["nextCall"]["arguments"]["confirm_mutation"])
        self.assertEqual(result["nextCall"]["arguments"]["script"], script)
        self.assertIn("advisory", result["note"])
        get_session.assert_not_called()
        self.assertEqual(session.start_calls, 0)

    def test_deploy_warnings_alone_do_not_ask_for_confirmation(self) -> None:
        """Only error-level findings buy the second confirmation."""
        session = FakeSession(FakePage())
        guard = FakeGuard()
        # opExtrude(context, id, 5) is warning-level: the real server accepts it
        # at save time, so demanding a confirmation would be noise.
        warning_script = (
            'FeatureScript 3044;\n'
            'import(path : "onshape/std/geometry.fs", version : "3044.0");\n'
            'export const f = defineFeature(function(context is Context, id is Id, definition is map)\n'
            '    precondition { annotation { "Name" : "F" } }\n'
            '    {\n'
            '        opExtrude(context, id + "e", 5);\n'
            '    });\n'
        )
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.read_featurescript_editor",
                        side_effect=["old source", warning_script]), \
             mock.patch("onshape_browser_mode.actions.write_featurescript_editor",
                        return_value={"ok": True, "length": len(warning_script), "lineCount": 7}), \
             mock.patch("onshape_browser_mode.actions.click_commit",
                        return_value={"clicked": True,
                                      "before": {"disabled": False},
                                      "after": {"disabled": True}}), \
             mock.patch("onshape_browser_mode.actions.read_featurescript_compile_status",
                        return_value={"compiled": True, "annotationCount": 0,
                                      "noticeCount": 0, "errors": []}), \
             mock.patch("onshape_browser_mode.diagnostics.save_featurescript_diagnostic",
                        return_value={"captured": True, "captureId": "capture-warn"}):
            result = server._browser_deploy_featurescript(
                {"script": warning_script, "dry_run": False, "confirm_mutation": True})
        self.assertEqual(result["localCheck"]["errorCount"], 0)
        self.assertGreaterEqual(result["localCheck"]["warningCount"], 1)
        self.assertNotIn("acknowledgementRequired", result)
        self.assertTrue(result["deployed"])

    def test_deploy_preview_reports_the_acknowledgement_it_would_need(self) -> None:
        bad = server._browser_deploy_featurescript(
            {"script": "FeatureScript 3044;\nvar x = 1;", "dry_run": True})
        self.assertTrue(bad["acknowledgementRequired"])
        acknowledged = server._browser_deploy_featurescript(
            {"script": "FeatureScript 3044;\nvar x = 1;", "dry_run": True,
             "acknowledge_local_findings": True})
        self.assertFalse(acknowledged["acknowledgementRequired"])

    def test_deploy_commits_with_confirmation_and_paces(self) -> None:
        session = FakeSession(FakePage())
        guard = FakeGuard()
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.read_featurescript_editor",
                        side_effect=["old source", "feature X {}"]), \
             mock.patch("onshape_browser_mode.actions.write_featurescript_editor",
                        return_value={"ok": True, "length": 12, "lineCount": 1}) as write, \
             mock.patch("onshape_browser_mode.actions.click_commit",
                        return_value={
                            "clicked": True,
                            "before": {"disabled": False},
                            "after": {"disabled": True},
                        }) as commit, \
             mock.patch("onshape_browser_mode.actions.read_featurescript_compile_status",
                        return_value={"compiled": True, "annotationCount": 0, "noticeCount": 0, "errors": []}), \
             mock.patch("onshape_browser_mode.diagnostics.save_featurescript_diagnostic",
                        return_value={"captured": True, "captureId": "capture-ok"}) as capture:
            result = server._browser_deploy_featurescript(
                {"script": "feature X {}", "dry_run": False, "confirm_mutation": True,
                 "acknowledge_local_findings": True})
        self.assertTrue(result["deployed"])
        self.assertTrue(result["verified"])
        self.assertTrue(result["compiled"])
        self.assertFalse(result["dryRun"])
        self.assertEqual(session.start_calls, 1)
        write.assert_called_once()
        commit.assert_called_once()
        capture.assert_called_once()
        self.assertEqual(result["diagnosticCapture"]["captureId"], "capture-ok")
        # The free local check is attached to the real path too.
        self.assertTrue(result["localCheck"]["checked"])
        # Pacing enforced before the editor write and before the Commit click
        # (the editor is already on screen, so no navigation pacing is added).
        self.assertEqual(guard.pace_calls, 2)

    def test_deploy_rejects_compiler_annotations(self) -> None:
        session = FakeSession(FakePage())
        guard = FakeGuard()
        compile_error = {
            "compiled": False,
            "annotationCount": 1,
            "errors": [{"row": 1, "col": 0, "text": "bad token", "type": "error"}],
        }
        with mock.patch("onshape_browser_mode.session.get_session", return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.read_featurescript_editor",
                        side_effect=["old", "new"]), \
             mock.patch("onshape_browser_mode.actions.write_featurescript_editor",
                        return_value={"ok": True, "length": 3}), \
             mock.patch("onshape_browser_mode.actions.click_commit", return_value={
                 "clicked": True,
                 "before": {"disabled": False},
                 "after": {"disabled": True},
             }), \
             mock.patch("onshape_browser_mode.actions.read_featurescript_compile_status",
                        return_value=compile_error), \
             mock.patch("onshape_browser_mode.diagnostics.save_featurescript_diagnostic",
                        return_value={"captured": True, "captureId": "capture-error"}):
            result = server._browser_deploy_featurescript({
                "script": "new", "dry_run": False, "confirm_mutation": True,
                "acknowledge_local_findings": True,
            })
        self.assertFalse(result["deployed"])
        self.assertTrue(result["commitAccepted"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["errors"], compile_error["errors"])
        self.assertEqual(result["diagnosticCapture"]["captureId"], "capture-error")


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


class BrowserCreateTabTest(unittest.TestCase):
    def test_create_tab_requires_confirmation(self) -> None:
        session = FakeSession(FakePage())
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session) as get_session, \
             mock.patch("onshape_browser_mode.actions.create_document_tab",
                        side_effect=AssertionError("must not create tab before confirmation")):
            with self.assertRaises(ValueError) as ctx:
                server._browser_create_tab({"tab_type": "Feature Studio"})
        self.assertIn("confirm_mutation", str(ctx.exception))
        get_session.assert_not_called()
        self.assertEqual(session.start_calls, 0)

    def test_create_tab_rejects_unknown_type_without_session(self) -> None:
        session = FakeSession(FakePage())
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session) as get_session:
            with self.assertRaises(ValueError) as ctx:
                server._browser_create_tab({"tab_type": "Bogus", "confirm_mutation": True})
        self.assertIn("tab_type", str(ctx.exception))
        get_session.assert_not_called()
        self.assertEqual(session.start_calls, 0)

    def test_confirmed_create_tab_delegates_and_paces(self) -> None:
        session = FakeSession(FakePage())
        guard = FakeGuard()
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.create_document_tab",
                        return_value={"created": True, "tabType": "Feature Studio"}) as create_tab:
            result = server._browser_create_tab(
                {"tab_type": "Feature Studio", "confirm_mutation": True})
        self.assertTrue(result["created"])
        create_tab.assert_called_once()
        self.assertEqual(session.start_calls, 1)
        self.assertEqual(guard.pace_calls, 1)


    def test_action_verifies_assembly_tab_appears(self) -> None:
        page = mock.Mock()
        page.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        page.evaluate.side_effect = [
            {"tabs": [{"name": "Part Studio 1", "active": True}]},
            {"clicked": True, "text": "创建装配体"},
            {"tabs": [
                {"name": "Part Studio 1", "active": False},
                {"name": "装配体 1", "active": True},
            ]},
        ]
        result = actions.create_document_tab(page, "Assembly")
        self.assertTrue(result["triggered"])
        self.assertTrue(result["created"])
        self.assertEqual(result["newTabs"][0]["name"], "装配体 1")
        self.assertEqual(page.evaluate.call_args_list[1].args[1], "创建装配体")

    def test_action_reports_not_triggered_when_menu_item_is_missing(self) -> None:
        page = mock.Mock()
        page.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        page.evaluate.side_effect = [
            {"tabs": [{"name": "Part Studio 1", "active": True}]},
            {"clicked": False, "reason": "dropdown item not found"},
        ]
        result = actions.create_document_tab(page, "Assembly")
        self.assertFalse(result["triggered"])
        self.assertFalse(result["created"])
        self.assertEqual(result["tabType"], "Assembly")

    def test_action_does_not_claim_created_when_prior_tabs_are_unreadable(self) -> None:
        page = mock.Mock()
        page.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        page.evaluate.side_effect = [
            RuntimeError("context rebuilding"),
            {"clicked": True, "text": "创建 Part Studio"},
            {"tabs": [{"name": "Part Studio 2", "active": True}]},
        ]
        result = actions.create_document_tab(page, "Part Studio")
        self.assertTrue(result["triggered"])
        self.assertFalse(result["created"])
        self.assertFalse(result["beforeTabsReadable"])
        self.assertIn("unverified", result["reason"])

    def test_action_does_not_claim_drawing_created_while_dialog_is_pending(self) -> None:
        page = mock.Mock()
        page.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        unchanged = {"tabs": [{"name": "Part Studio 1", "active": True}]}
        page.evaluate.side_effect = [
            unchanged,
            {"clicked": True, "text": "创建工程图…"},
            unchanged,
        ]
        result = actions.create_document_tab(page, "Drawing")
        self.assertTrue(result["triggered"])
        self.assertFalse(result["created"])
        self.assertIn("open dialog", result["reason"])
        self.assertEqual(page.evaluate.call_args_list[1].args[1], "创建工程图")
    def test_public_handler_rejects_nonterminal_drawing_flow_before_session(self) -> None:
        with mock.patch("onshape_browser_mode.session.get_session") as get_session:
            with self.assertRaisesRegex(ValueError, "browser_create_drawing"):
                server._browser_create_tab({"tab_type": "Drawing", "confirm_mutation": True})
        get_session.assert_not_called()


class BrowserRenameTabTest(unittest.TestCase):
    def test_rename_requires_confirmation(self) -> None:
        session = FakeSession(FakePage())
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session) as get_session, \
             mock.patch("onshape_browser_mode.actions.rename_tab",
                        side_effect=AssertionError("must not rename before confirmation")):
            with self.assertRaises(ValueError) as ctx:
                server._browser_rename_tab({"name": "Part Studio 2", "new_name": "PS2"})
        self.assertIn("confirm_mutation", str(ctx.exception))
        get_session.assert_not_called()
        self.assertEqual(session.start_calls, 0)

    def test_confirmed_rename_delegates_and_paces(self) -> None:
        session = FakeSession(FakePage())
        guard = FakeGuard()
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.rename_tab",
                        return_value={"renamed": True}) as rename_tab:
            result = server._browser_rename_tab(
                {"name": "Part Studio 2", "new_name": "PS2", "confirm_mutation": True})
        self.assertTrue(result["renamed"])
        rename_tab.assert_called_once()
        self.assertEqual(session.start_calls, 1)
        self.assertEqual(guard.pace_calls, 1)


class BrowserDeleteTabTest(unittest.TestCase):
    def test_delete_requires_confirmation(self) -> None:
        session = FakeSession(FakePage())
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session) as get_session, \
             mock.patch("onshape_browser_mode.actions.delete_tab",
                        side_effect=AssertionError("must not delete before confirmation")):
            with self.assertRaises(ValueError) as ctx:
                server._browser_delete_tab({"name": "Part Studio 2"})
        self.assertIn("confirm_mutation", str(ctx.exception))
        get_session.assert_not_called()
        self.assertEqual(session.start_calls, 0)

    def test_confirmed_delete_delegates_and_paces(self) -> None:
        session = FakeSession(FakePage())
        guard = FakeGuard()
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.delete_tab",
                        return_value={"deleted": True}) as delete_tab:
            result = server._browser_delete_tab(
                {"name": "Part Studio 2", "confirm_mutation": True})
        self.assertTrue(result["deleted"])
        delete_tab.assert_called_once()
        self.assertEqual(session.start_calls, 1)
        self.assertEqual(guard.pace_calls, 1)

    def test_name_wrapper_requires_exact_unique_match(self) -> None:
        page = mock.Mock(url="https://cad.onshape.com/documents/d1/w/w1/e/e1")
        tabs = {
            "tabs": [
                {"name": "Part Studio 1", "id": "e1"},
                {"name": "Part Studio 2", "id": "e2"},
            ]
        }
        with mock.patch("onshape_browser_mode.actions.list_document_tabs", return_value=tabs), \
             mock.patch("onshape_browser_mode.actions.delete_element_by_id") as delete_by_id:
            result = actions.delete_tab(page, "Part")
        self.assertFalse(result["deleted"])
        self.assertEqual(result["matchCount"], 0)
        delete_by_id.assert_not_called()

    def test_name_wrapper_delegates_exact_name_to_shared_id_core(self) -> None:
        page = mock.Mock(url="https://cad.onshape.com/documents/d1/w/w1/e/e1")
        tabs = {"tabs": [{"name": "Part Studio 2", "id": "e2"}]}
        with mock.patch("onshape_browser_mode.actions.list_document_tabs", return_value=tabs), \
             mock.patch("onshape_browser_mode.actions.delete_element_by_id", return_value={"deleted": True, "elementId": "e2"}) as delete_by_id:
            result = actions.delete_tab(page, "Part Studio 2")
        self.assertTrue(result["deleted"])
        self.assertTrue(result["compatibilityWrapper"])
        delete_by_id.assert_called_once_with(page, "e2")


class WaitForTabRemovedTest(unittest.TestCase):
    """A tab removal is judged by its data-id, never by its position.

    Measured live 2026-09-20: ``locator.nth(i).wait_for(state="detached")`` timed
    out after 30 s on a tab that HAD in fact been deleted, and the very next read
    of the tab strip no longer listed it. The tab strip is an ``ng-repeat`` list,
    so removing a tab renumbers the remaining nodes and ``nth(i)`` re-resolves to
    the tab that just moved into the freed slot — which is attached. The wait could
    therefore never be satisfied, and the exception became ``deleted: false``.
    """

    @staticmethod
    def _page(*, removes: bool) -> mock.Mock:
        page = mock.Mock(url="https://cad.onshape.com/documents/d1/w/w1/e/e1")
        calls: list[dict] = []

        def wait_for_function(expression, *, arg=None, timeout=None, polling=None):
            calls.append({"expression": expression, "arg": arg, "timeout": timeout})
            if not removes:
                raise TimeoutError("tab is still attached")
            return True

        page.wait_for_function.side_effect = wait_for_function
        page.removal_calls = calls
        return page

    def test_the_wait_is_addressed_by_data_id_not_by_position(self):
        page = self._page(removes=True)
        result = actions.wait_for_tab_removed(page, "e9")
        self.assertTrue(result["waited"])
        self.assertEqual(result["condition"], "tab_removed_or_hidden")
        self.assertEqual(result["elementId"], "e9")
        self.assertEqual(result["timeoutMs"], actions.TAB_DELETE_TIMEOUT_MS)
        self.assertGreaterEqual(result["elapsedMs"], 0)
        self.assertNotIn("error", result)
        (call,) = page.removal_calls
        self.assertEqual(call["expression"], actions._TAB_REMOVED_PREDICATE)
        self.assertEqual(call["arg"], {"selector": selectors.TAB_BAR_TAB, "id": "e9"})
        self.assertEqual(call["timeout"], actions.TAB_DELETE_TIMEOUT_MS)

    def test_the_predicate_accepts_the_hidden_marker_as_removed(self):
        # A removed tab is marked hidden before it detaches, so an "absent only"
        # predicate would still miss the state the position wait missed.
        self.assertIn("'hidden'", actions._TAB_REMOVED_PREDICATE)
        self.assertIn("nodes.length === 0", actions._TAB_REMOVED_PREDICATE)

    def test_a_timeout_is_returned_as_evidence_not_raised(self):
        page = self._page(removes=False)
        result = actions.wait_for_tab_removed(page, "e9", timeout_ms=1234)
        self.assertFalse(result["waited"])
        self.assertEqual(result["timeoutMs"], 1234)
        self.assertIn("TimeoutError", result["error"])


class DeleteElementVerdictTest(unittest.TestCase):
    """The delete verdict is the data-id wait, not the raw tab-strip read.

    Live, the raw read no longer listed the tab while the positional wait had
    already timed out, so the two can disagree in that direction; the tool must
    believe the wait and return the raw read for diagnosis only.
    """

    @staticmethod
    def _page() -> mock.Mock:
        page = mock.Mock(url="https://cad.onshape.com/documents/d1/w/w1/e/e1")
        menu = mock.Mock()
        menu.count.return_value = 1
        item = mock.Mock()
        item.is_visible.return_value = True
        item.inner_text.return_value = "删除"
        menu.nth.return_value = item
        confirm = mock.Mock()
        confirm.count.return_value = 1
        page.locator.side_effect = (
            lambda selector: menu if selector == selectors.TAB_CONTEXT_MENU_ITEM else confirm
        )
        page.menu_item = item
        return page

    def test_a_removed_tab_is_not_reported_live_again_by_a_stale_raw_read(self):
        page = self._page()
        tab = mock.Mock()
        with mock.patch.object(actions, "_tab_locators_by_id", return_value=[tab]), \
             mock.patch.object(actions, "dismiss_stale_context_menu"), \
             mock.patch.object(actions, "wait_for_tab_removed",
                               return_value={"waited": True, "elapsedMs": 412}), \
             mock.patch.object(actions, "list_document_tabs",
                               return_value={"tabs": [{"name": "Feature Studio 1", "id": "e9"}]}):
            result = actions.delete_element_by_id(page, "e9")
        self.assertTrue(result["deleted"], "the data-id wait is the verdict")
        self.assertEqual(result["stillListedIds"], ["e9"], "the raw read is reported, not obeyed")
        self.assertNotIn("reason", result)
        tab.click.assert_called_once_with(button="right")
        page.menu_item.click.assert_called_once()

    def test_a_tab_that_never_leaves_is_reported_with_its_timeout(self):
        page = self._page()
        tab = mock.Mock()
        with mock.patch.object(actions, "_tab_locators_by_id", return_value=[tab]), \
             mock.patch.object(actions, "dismiss_stale_context_menu"), \
             mock.patch.object(actions, "wait_for_tab_removed",
                               return_value={"waited": False, "elapsedMs": 30001,
                                             "timeoutMs": 30000}), \
             mock.patch.object(actions, "list_document_tabs", return_value={"tabs": []}):
            result = actions.delete_element_by_id(page, "e9")
        self.assertFalse(result["deleted"])
        self.assertEqual(result["stillListedIds"], [])
        self.assertIn("still a visible document tab", result["reason"])
        self.assertIn("30001", result["reason"])


class FakeTabLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    @property
    def first(self):
        return self

    def click(self):
        self.page.clicks.append(self.selector)

    def wait_for(self, state=None, timeout=None):
        self.page.wait_calls.append({"selector": self.selector, "state": state, "timeout": timeout})
        if self.selector == selectors.PS_FEATURES_HEADER and not self.page.header:
            raise TimeoutError("features title never appeared")
        return True


class FakeTabPage:
    """Page double for activate_tab: a tab strip plus the two readiness waits."""

    def __init__(self, tabs, *, activates=True, rows=1, header=True):
        self.tabs = [dict(tab) for tab in tabs]
        self.activates = activates
        self.rows = rows
        self.header = header
        self.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        self.clicks: list[str] = []
        self.wait_calls: list[dict] = []
        self.wait_function_calls: list[dict] = []

    def evaluate(self, expression, *args):
        if "os-tab-bar-tab" in expression:
            return {"tabs": self.tabs, "hasDocumentTabsToolButton": True}
        # dismiss_stale_context_menu: no blocking layer in the double.
        return {"present": False, "blocking": False}

    def locator(self, selector):
        return FakeTabLocator(self, selector)

    def wait_for_function(self, expression, *, arg=None, timeout=None, polling=None):
        self.wait_function_calls.append(
            {"expression": expression, "arg": arg, "timeout": timeout}
        )
        if expression == actions._TAB_ACTIVE_PREDICATE:
            wanted = str((arg or {}).get("id", ""))
            if self.activates:
                # Onshape moves the active class; the double mirrors that, so the
                # verdict really is read back rather than assumed.
                self.tabs = [
                    {**tab, "active": tab.get("id") == wanted} for tab in self.tabs
                ]
                return True
            raise TimeoutError(f"tab {wanted!r} never became active")
        minimum = int((arg or {}).get("minimum", 1))
        if self.rows >= minimum:
            return True
        raise TimeoutError("no feature row rendered")


class ActivateTabTest(unittest.TestCase):
    """One existing tab can be made active, and the verdict is that tab's class.

    Measured live 2026-09-20: `browser_rename_tab` double-clicks a tab name yet the
    previously active tab stays active, and read tools plus the dialog-edit
    transaction act on whatever tab is active. That is why a small-element end-to-end
    run could not be substituted for an 11-feature element.
    """

    TABS = (
        {"id": "e0", "name": "Feature Studio 1", "active": True},
        {"id": "e1", "name": "Part Studio 1", "active": False},
        {"id": "e2", "name": "Part Studio 2", "active": False},
    )

    def test_it_switches_by_data_id_and_reads_the_active_class_back(self):
        page = FakeTabPage(self.TABS)
        result = actions.activate_tab(page, name="Part Studio 1")
        self.assertTrue(result["activated"])
        self.assertFalse(result["alreadyActive"])
        self.assertTrue(result["clicked"])
        self.assertEqual(result["elementId"], "e1")
        self.assertEqual(result["activeBefore"], "e0")
        self.assertEqual(result["activeAfter"], "e1")
        self.assertEqual(page.clicks, [f'{selectors.TAB_BAR_TAB}[data-id="e1"]'])
        self.assertEqual(result["wait"]["condition"], "tab_active_class")
        self.assertEqual(result["wait"]["timeoutMs"], actions.TAB_ACTIVATE_TIMEOUT_MS)
        self.assertTrue(result["wait"]["waited"])
        # By data-id, never by position: the tab strip renumbers.
        (call,) = page.wait_function_calls
        self.assertEqual(call["arg"], {"selector": selectors.TAB_BAR_TAB, "id": "e1"})

    def test_an_already_active_tab_is_not_clicked(self):
        page = FakeTabPage(self.TABS)
        result = actions.activate_tab(page, element_id="e0")
        self.assertTrue(result["activated"])
        self.assertTrue(result["alreadyActive"])
        self.assertFalse(result["clicked"])
        self.assertEqual(page.clicks, [])

    def test_an_ambiguous_or_missing_name_is_refused_without_a_click(self):
        page = FakeTabPage(
            (
                {"id": "e0", "name": "Part Studio 1", "active": True},
                {"id": "e1", "name": "Part Studio 1", "active": False},
            )
        )
        ambiguous = actions.activate_tab(page, name="Part Studio 1")
        self.assertFalse(ambiguous["activated"])
        self.assertEqual(ambiguous["matchCount"], 2)
        self.assertIn("exactly one", ambiguous["reason"])
        missing = actions.activate_tab(page, name="Part Studio 9")
        self.assertFalse(missing["activated"])
        self.assertEqual(missing["matchCount"], 0)
        self.assertEqual(page.clicks, [], "never click an unproven target")

    def test_a_tab_that_never_becomes_active_is_reported_not_assumed(self):
        page = FakeTabPage(self.TABS, activates=False)
        result = actions.activate_tab(page, name="Part Studio 2")
        self.assertFalse(result["activated"])
        self.assertFalse(result["wait"]["waited"])
        self.assertIn("TimeoutError", result["wait"]["error"])
        self.assertEqual(result["activeAfter"], "e0", "the re-read decides, not the click")
        self.assertIn("is not the active tab", result["reason"])

    def test_partstudio_content_waits_for_the_title_and_the_rows(self):
        page = FakeTabPage(self.TABS, rows=3)
        result = actions.activate_tab(page, name="Part Studio 1", content="partstudio")
        self.assertTrue(result["activated"])
        self.assertTrue(result["contentReady"]["headerVisible"])
        self.assertTrue(result["contentReady"]["rows"]["waited"])
        self.assertEqual(result["contentReady"]["rows"]["condition"], "partstudio_row_count")
        self.assertIn(
            selectors.PS_FEATURES_HEADER,
            [call["selector"] for call in page.wait_calls],
            "a switched-to Part Studio renders in stages: the title is waited for",
        )

    def test_a_panel_that_never_renders_rows_is_evidence_not_a_refusal(self):
        page = FakeTabPage(self.TABS, rows=0)
        result = actions.activate_tab(page, name="Part Studio 1", content="partstudio")
        self.assertTrue(result["activated"], "the switch happened; the read wait is evidence")
        self.assertFalse(result["contentReady"]["rows"]["waited"])
        self.assertIn("TimeoutError", result["contentReady"]["rows"]["error"])

    def test_the_arguments_are_validated(self):
        page = FakeTabPage(self.TABS)
        with self.assertRaises(ValueError):
            actions.activate_tab(page)
        with self.assertRaises(ValueError):
            actions.activate_tab(page, name="Part Studio 1", content="assembly")


class BrowserReloadTest(unittest.TestCase):
    def test_reload_is_read_only_and_paces(self) -> None:
        session = FakeSession(FakePage())
        guard = FakeGuard()
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.reconnect_if_needed", return_value={"reconnected": False}) as reconnect, \
             mock.patch("onshape_browser_mode.actions.reload_page",
                        return_value={"reloaded": True}) as reload_page:
            result = server._browser_reload({})
        self.assertTrue(result["reloaded"])
        reconnect.assert_called_once()
        reload_page.assert_called_once()
        self.assertEqual(session.start_calls, 1)
        self.assertEqual(guard.pace_calls, 1)


    def test_reload_action_uses_bounded_waits_and_reads_tabs(self) -> None:
        page = mock.Mock()
        page.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        page.evaluate.return_value = {"tabs": [{"name": "Drawing 1", "active": True}]}
        result = actions.reload_page(page)
        page.reload.assert_called_once_with(wait_until="commit", timeout=15000)
        page.wait_for_load_state.assert_called_once_with("domcontentloaded", timeout=15000)
        self.assertTrue(result["reloaded"])
        self.assertTrue(result["tabsReadable"])
        self.assertEqual(result["warnings"], [])

    def test_reload_action_returns_partial_state_on_timeouts(self) -> None:
        page = mock.Mock()
        type(page).url = mock.PropertyMock(side_effect=RuntimeError("url unavailable"))
        page.reload.side_effect = TimeoutError("stuck")
        page.wait_for_load_state.side_effect = TimeoutError("still loading")
        page.evaluate.side_effect = RuntimeError("context rebuilding")
        result = actions.reload_page(page)
        self.assertFalse(result["reloaded"])
        self.assertFalse(result["tabsReadable"])
        self.assertIsNone(result["pageUrl"])
        self.assertIsNone(result["hasDocumentTabsToolButton"])
        self.assertEqual(len(result["warnings"]), 4)


class BrowserOpenInsertFeatureDialogTest(unittest.TestCase):
    def test_open_dialog_is_read_only_and_paces(self) -> None:
        session = FakeSession(FakePage())
        guard = FakeGuard()
        with mock.patch("onshape_browser_mode.session.get_session",
                        return_value=session), \
             mock.patch("onshape_browser_mode.guard.get_guard", return_value=guard), \
             mock.patch("onshape_browser_mode.actions.open_insert_custom_feature_dialog",
                        return_value={"clicked": True, "dialog": {"present": True}}) as open_dialog:
            result = server._browser_open_insert_feature_dialog({})
        self.assertTrue(result["clicked"])
        self.assertTrue(result["dialog"]["present"])
        open_dialog.assert_called_once()
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

    def test_browser_session_exposes_cooperative_release(self) -> None:
        tool = self.by_name["browser_session"]
        action = tool["inputSchema"]["properties"]["action"]
        self.assertEqual(
            action["enum"], ["status", "login", "release", "reconnect", "reload"]
        )
        self.assertIn("release", action["description"])
        self.assertIn("browser_process_release", tool["cost"]["side_effects"])
        self.assertIn("another MCP process", tool["description"])

    def test_create_tab_mutating_and_dialog_opener_read_only(self) -> None:
        tab_tool = self.by_name["browser_create_tab"]
        self.assertTrue(tab_tool["cost"]["mutating"])
        self.assertEqual(tab_tool["cost"]["estimated_requests"], 0)
        self.assertFalse(tab_tool["annotations"]["readOnlyHint"])
        self.assertIn("confirm_mutation", tab_tool["inputSchema"]["properties"])

        dialog_tool = self.by_name["browser_open_insert_feature_dialog"]
        self.assertFalse(dialog_tool["cost"]["mutating"])
        self.assertTrue(dialog_tool["annotations"]["readOnlyHint"])
        self.assertEqual(dialog_tool["cost"]["estimated_requests"], 0)
        self.assertNotIn("confirm_mutation", dialog_tool["inputSchema"]["properties"])

    def test_tab_management_tools_are_mutating(self) -> None:
        for name in ("browser_rename_tab", "browser_delete_tab"):
            tool = self.by_name[name]
            self.assertTrue(tool["cost"]["mutating"], name)
            self.assertEqual(tool["cost"]["estimated_requests"], 0, name)
            self.assertFalse(tool["annotations"]["readOnlyHint"], name)
            self.assertIn("confirm_mutation", tool["inputSchema"]["properties"], name)
        self.assertTrue(self.by_name["browser_delete_tab"]["annotations"]["destructiveHint"])

    def test_tool_count_unchanged(self) -> None:
        # 106 since the two print-analysis stubs were archived on 2026-09-19
        # (docs/history/legacy/ARCHIVED_BROWSER_PRINT_TOOLS.md); 109 since the
        # read-only browser_read_feature_parameters probe was added on 2026-09-20;
        # 110 since browser_delete_feature was added on 2026-09-21 (the feature-row
        # delete no other tool performed, needed to undo a row a refused or
        # timed-out insert left behind).
        # This number is a tripwire: it must only move when a tool is deliberately
        # added or removed.
        self.assertEqual(len(server.TOOLS), 110)


if __name__ == "__main__":
    unittest.main()
