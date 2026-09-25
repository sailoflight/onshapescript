#!/usr/bin/env python3
"""Offline tests for the idle-session health probe (`browser_session action=health`).

The probe exists because the browser leg's failure mode is invisible: an idle
session can be disconnected server-side while the page still looks open, and a
wedged page accepts a call and never answers. What must hold, and is checked
here with fake pages and a fake session (no browser, no network, no quota):

* every verdict is reachable from evidence, and none is invented from a missing
  read;
* the probe is a READ: it never starts a browser, navigates, or clicks;
* the timeout dialog outranks a slow round trip, because it names a state the
  caller has to clear;
* a slow first touch after idle is reported as a hint, not as a fault.
"""

from __future__ import annotations

import unittest

from onshape_browser_mode import health
from onshape_browser_mode.session import BrowserSession

APP = "https://cad.onshape.com/documents/doc1/w/workspace1/e/element1"
SIGNIN = "https://cad.onshape.com/signin"


class FakePage:
    """The two page primitives the probe uses, with a controllable outcome."""

    def __init__(self, url="https://cad.onshape.com/documents/abc", *, answers=True, read=None):
        self._url = url
        self._answers = answers
        self._read = read
        self.wait_calls: list[int] = []
        self.evaluate_calls: list[str] = []
        self.closed = False

    @property
    def url(self) -> str:
        return self._url

    def is_closed(self) -> bool:
        return self.closed

    def wait_for_function(self, js, **kwargs):
        self.wait_calls.append(kwargs.get("timeout"))
        if not self._answers:
            raise TimeoutError("Timeout 8000ms exceeded.")
        return True

    def evaluate(self, js, *args):
        self.evaluate_calls.append(js)
        return self._read if self._read is not None else {
            "timeoutDialogPresent": False,
            "documentShellReady": True,
            "title": "Document",
            "href": self._url,
        }


class ProbePageTest(unittest.TestCase):
    def test_a_healthy_page_answers_with_one_bounded_round_trip(self):
        page = FakePage()
        evidence = health.probe_page(page, timeout_ms=1234)
        self.assertTrue(evidence["responded"])
        self.assertEqual(page.wait_calls, [1234])
        self.assertEqual(len(page.evaluate_calls), 1)
        self.assertTrue(evidence["documentShellReady"])
        self.assertFalse(evidence["timeoutDialogPresent"])
        self.assertIsInstance(evidence["roundTripMs"], int)

    def test_a_timeout_is_evidence_and_never_raises(self):
        evidence = health.probe_page(FakePage(answers=False), timeout_ms=500)
        self.assertFalse(evidence["responded"])
        self.assertIn("TimeoutError", evidence["error"])
        self.assertEqual(evidence["probeTimeoutMs"], 500)
        # A page that never answered was never read, and the absence of a read
        # must not be reported as a clean document.
        self.assertNotIn("documentShellReady", evidence)

    def test_a_failed_read_after_a_good_round_trip_is_not_a_verdict(self):
        class Exploding(FakePage):
            def evaluate(self, js, *args):
                raise RuntimeError("Execution context was destroyed")

        evidence = health.probe_page(Exploding())
        self.assertTrue(evidence["responded"])
        self.assertIn("readError", evidence)
        self.assertNotIn("timeoutDialogPresent", evidence)


class ClassifyTest(unittest.TestCase):
    def classify(self, evidence, **overrides):
        arguments = {
            "session_running": True,
            "on_onshape_app": True,
            "login_confirmed": True,
            "session_status": "started",
        }
        arguments.update(overrides)
        return health.classify(evidence, **arguments)

    def test_each_verdict_has_a_recovery_action(self):
        cases = [
            (
                {"responded": None},
                {"session_running": False},
                health.BROWSER_NOT_RUNNING,
                "browser_session action=login",
            ),
            (
                {"responded": True, "timeoutDialogPresent": True, "documentShellReady": True},
                {},
                health.SESSION_TIMEOUT_DIALOG,
                "browser_session action=reconnect",
            ),
            (
                {"responded": False, "error": "TimeoutError"},
                {},
                health.PAGE_UNRESPONSIVE,
                "browser_session action=reload",
            ),
            (
                {"responded": True, "timeoutDialogPresent": False, "documentShellReady": True},
                {"on_onshape_app": False, "login_confirmed": False},
                health.LOGIN_REQUIRED,
                "browser_session action=login",
            ),
            (
                {"responded": True, "timeoutDialogPresent": False, "documentShellReady": False},
                {},
                health.INDETERMINATE,
                "browser_session action=reload",
            ),
            (
                {"responded": True, "timeoutDialogPresent": False, "documentShellReady": True},
                {},
                health.OK,
                "none",
            ),
        ]
        for evidence, overrides, verdict, action in cases:
            with self.subTest(verdict=verdict):
                result = self.classify(evidence, **overrides)
                self.assertEqual(result["verdict"], verdict)
                self.assertEqual(result["recommendedAction"], action)
                self.assertTrue(result["note"])
                self.assertIn(verdict, result["verdicts"])

    def test_the_timeout_dialog_outranks_a_slow_round_trip(self):
        result = self.classify(
            {"responded": True, "timeoutDialogPresent": True, "roundTripMs": 5000}
        )
        self.assertEqual(result["verdict"], health.SESSION_TIMEOUT_DIALOG)
        self.assertFalse(result["slowFirstTouch"])

    def test_a_slow_first_touch_is_a_hint_not_a_fault(self):
        result = self.classify(
            {"responded": True, "timeoutDialogPresent": False, "documentShellReady": True,
             "roundTripMs": health.SLOW_ROUND_TRIP_MS + 1}
        )
        self.assertEqual(result["verdict"], health.OK)
        self.assertTrue(result["slowFirstTouch"])
        self.assertIn("idle", result["note"])
        self.assertEqual(result["recommendedAction"], "none")

    def test_a_missing_read_never_becomes_a_clean_verdict(self):
        # No `documentShellReady` at all: the probe could not read the page, so
        # "ok" would be a claim the evidence does not support.
        result = self.classify({"responded": True, "timeoutDialogPresent": False})
        self.assertEqual(result["verdict"], health.INDETERMINATE)


class SessionHealthTest(unittest.TestCase):
    def session_with(self, *, page, context_available=True):
        session = BrowserSession()

        class Resources:
            def __init__(self, page):
                self.page = page
                self.context = type("Context", (), {"pages": [page]})() if context_available else None

            def __getattr__(self, name):
                from browser_common import ResourceUnavailableError
                raise ResourceUnavailableError(name)

        session._resources = Resources(page)
        return session

    def test_health_reports_a_verdict_without_starting_anything(self):
        page = FakePage()
        session = self.session_with(page=page)
        started: list[str] = []
        session.start = lambda *a, **k: started.append("start")  # type: ignore[assignment]
        result = session.health(probe_timeout_ms=1000)
        self.assertEqual(result["verdict"], health.OK)
        self.assertEqual(started, [])
        self.assertTrue(result["readOnly"])
        self.assertFalse(result["launchedBrowser"])
        self.assertEqual(result["quota"], 0)
        self.assertEqual(page.wait_calls, [1000])
        self.assertIn("https://cad.onshape.com/documents/abc", result["pageUrl"])

    def test_no_resources_is_browser_not_running_and_probes_nothing(self):
        session = BrowserSession()
        result = session.health()
        self.assertEqual(result["verdict"], health.BROWSER_NOT_RUNNING)
        self.assertIsNone(result["pageUrl"])
        self.assertEqual(result["pages"], [])
        self.assertIn("did NOT launch", result["note"])

    def test_a_downloads_page_is_never_the_probe_target(self):
        working = FakePage(url="https://cad.onshape.com/documents/work")
        downloads = FakePage(url="chrome://downloads/")
        session = BrowserSession()

        class Resources:
            def __init__(self):
                self.page = working
                self.context = type("Context", (), {"pages": [downloads, working]})()

        session._resources = Resources()
        result = session.health()
        self.assertEqual(result["verdict"], health.OK)
        self.assertTrue(
            any(item.get("browserInternal") for item in result["pages"]),
            result["pages"],
        )

    def test_the_signin_page_disproves_sticky_login_history(self):
        session = self.session_with(page=FakePage(url="https://cad.onshape.com/signin"))
        session.login_confirmed = True
        result = session.health()
        self.assertEqual(result["verdict"], health.LOGIN_REQUIRED)
        self.assertEqual(result["recommendedAction"], "browser_session action=login")
        # The probe reports; it does not rewrite the process's bookkeeping.
        self.assertTrue(session.login_confirmed)


class TimeoutDialogRecoveryTest(unittest.TestCase):
    """The dialog's two states, measured live 2026-09-21.

    After a bridge restart the dialog appeared with an EMPTY, unrendered link
    (Onshape was already auto-reconnecting): `browser_session action=reconnect`
    then burned a 30 s click timeout against an element that detached, while the
    page cleared by itself and the next probe read `ok`. The probe must name the
    right action for each state, and the reconnect action must not click a link
    that cannot be clicked.
    """

    class DialogPage:
        """A page whose dialog state is scripted, with no real clicking."""

        def __init__(self, states, *, click_raises=None):
            self._states = list(states)
            self._click_raises = click_raises
            self.url = "https://cad.onshape.com/documents/abc"
            self.waits: list[int] = []
            self.clicks = 0
            self.evaluates = 0

        def evaluate(self, js, *args):
            self.evaluates += 1
            return self._states[min(self.evaluates - 1, len(self._states) - 1)]

        def wait_for_timeout(self, ms):
            self.waits.append(ms)

        def locator(self, selector):
            if self._click_raises:
                raise self._click_raises
            outer = self

            class Locator:
                @property
                def first(self):
                    return self

                def click(self, **kwargs):
                    outer.clicks += 1

            return Locator()

    def test_a_non_actionable_dialog_recommends_a_reprobe_not_a_click(self):
        result = health.classify(
            {
                "responded": True,
                "timeoutDialogPresent": True,
                "timeoutDialogActionable": False,
                "timeoutDialogMessage": "未连接 Onshape。 正在尝试重新连接…",
                "documentShellReady": True,
            },
            session_running=True,
            on_onshape_app=True,
            login_confirmed=True,
        )
        self.assertEqual(result["verdict"], health.SESSION_TIMEOUT_DIALOG)
        self.assertEqual(result["recommendedAction"], "browser_session action=health")
        self.assertIn("automatic-reconnect", result["note"])

    def test_an_actionable_dialog_still_recommends_the_click(self):
        result = health.classify(
            {"responded": True, "timeoutDialogPresent": True, "timeoutDialogActionable": True},
            session_running=True,
            on_onshape_app=True,
            login_confirmed=True,
        )
        self.assertEqual(result["recommendedAction"], "browser_session action=reconnect")

    def test_reconnect_waits_out_a_dialog_that_clears_by_itself(self):
        page = self.DialogPage([
            {"present": True, "linkText": "", "actionable": False},
            {"present": True, "linkText": "", "actionable": False},
            {"present": False, "linkText": "", "actionable": False},
        ])
        from onshape_browser_mode.actions import reconnect_if_needed

        result = reconnect_if_needed(page)
        self.assertTrue(result["reconnected"])
        self.assertEqual(result["mode"], "automatic")
        self.assertEqual(result["waitedMs"], 2000)
        self.assertEqual(page.clicks, 0)

    def test_reconnect_does_not_click_a_link_that_cannot_be_clicked(self):
        page = self.DialogPage([{"present": True, "linkText": "", "actionable": False}])
        from onshape_browser_mode.actions import (
            AUTOMATIC_RECONNECT_WAIT_MS,
            reconnect_if_needed,
        )

        result = reconnect_if_needed(page)
        self.assertFalse(result["reconnected"])
        self.assertEqual(result["mode"], "automatic")
        self.assertEqual(result["waitedMs"], AUTOMATIC_RECONNECT_WAIT_MS)
        self.assertEqual(page.clicks, 0, "an unrendered link must never be clicked")
        self.assertEqual(result["recommendedAction"], "browser_session action=reload")
        self.assertIn("not clickable", result["reason"])

    def test_reconnect_clicks_an_actionable_link_and_reports_the_mode(self):
        page = self.DialogPage([
            {"present": True, "linkText": "重新连接", "actionable": True},
            {"present": False, "linkText": "", "actionable": False},
        ])
        from onshape_browser_mode.actions import reconnect_if_needed

        result = reconnect_if_needed(page)
        self.assertTrue(result["reconnected"])
        self.assertEqual(result["mode"], "click")
        self.assertEqual(page.clicks, 1)

    def test_a_click_that_races_a_self_clearing_dialog_is_not_a_failure(self):
        page = self.DialogPage([
            {"present": True, "linkText": "重新连接", "actionable": True},
            {"present": False, "linkText": "", "actionable": False},
        ], click_raises=TimeoutError("locator.click: Timeout 5000ms exceeded"))
        from onshape_browser_mode.actions import reconnect_if_needed

        result = reconnect_if_needed(page)
        self.assertTrue(result["reconnected"])
        self.assertEqual(result["mode"], "automatic")
        self.assertIn("cleared while", result["note"])

    def test_a_gone_dialog_is_a_no_op(self):
        page = self.DialogPage([{"present": False, "linkText": "", "actionable": False}])
        from onshape_browser_mode.actions import reconnect_if_needed

        result = reconnect_if_needed(page)
        self.assertFalse(result["reconnected"])
        self.assertEqual(result["reason"], "no timeout dialog")
        self.assertEqual(page.clicks, 0)


class LoginAwarenessTest(unittest.TestCase):
    """Issue #6 (login): the same navigation must report whether a login is needed.

    No network and no browser: the page records `goto` targets, and the saved-URL
    redirect (an expired profile landing on `/signin`) is scripted per target.
    """

    class LoginPage:
        def __init__(self, url, *, goto_result=None):
            self.url = url
            self._goto_result = dict(goto_result or {})
            self.gotos: list[str] = []
            self.waits: list[int] = []

        def goto(self, url, **kwargs):
            self.gotos.append(url)
            self.url = self._goto_result.get(url, url)

        def wait_for_timeout(self, ms):
            self.waits.append(ms)

    def login_session(self, page, *, saved_url=None):
        session = BrowserSession()
        session.start = lambda *a, **k: page  # type: ignore[assignment]
        session._enforce_single_working_page = lambda p: None  # type: ignore[assignment]
        session._save_app_url = lambda url: None  # type: ignore[assignment]
        session._load_saved_app_url = lambda: saved_url  # type: ignore[assignment]
        return session

    def test_a_restored_app_page_is_reported_as_already_authenticated(self):
        page = self.LoginPage(APP)

        result = self.login_session(page).open_login_page()

        self.assertTrue(result["alreadyAuthenticated"])
        self.assertFalse(result["needsHumanLogin"])
        self.assertEqual(page.gotos, [])
        self.assertEqual(result["sessionStatus"], "started")

    def test_a_saved_url_that_resolves_to_the_app_is_already_authenticated(self):
        page = self.LoginPage(SIGNIN)

        result = self.login_session(page, saved_url=APP).open_login_page()

        self.assertTrue(result["alreadyAuthenticated"])
        self.assertFalse(result["needsHumanLogin"])
        self.assertEqual(page.gotos, [APP])
        self.assertEqual(result["sessionStatus"], "started")

    def test_a_saved_url_that_lands_on_signin_needs_a_human(self):
        saved = "https://cad.onshape.com/documents/old"
        page = self.LoginPage(SIGNIN, goto_result={saved: SIGNIN})

        result = self.login_session(page, saved_url=saved).open_login_page()

        self.assertFalse(result["alreadyAuthenticated"])
        self.assertTrue(result["needsHumanLogin"])
        self.assertEqual(page.gotos, [saved, SIGNIN])
        self.assertEqual(result["sessionStatus"], "awaiting_login")

    def test_no_saved_url_opens_signin_and_needs_a_human(self):
        page = self.LoginPage("about:blank")

        result = self.login_session(page).open_login_page()

        self.assertFalse(result["alreadyAuthenticated"])
        self.assertTrue(result["needsHumanLogin"])
        self.assertEqual(page.gotos, [SIGNIN])

    def test_the_human_login_path_warns_that_the_page_reloads_itself(self):
        """Issue #5: the sign-in page replaces its own document while a human types.

        The server cannot prevent that or recover the input, so the honest answer
        is an advisory that stops a caller from polling the page mid-input. The
        already-authenticated paths touch no sign-in page and must NOT carry it.
        """
        page = self.LoginPage("about:blank")

        result = self.login_session(page).open_login_page()

        self.assertTrue(result["pageMaySelfReload"])
        advisory = result["humanInputAdvisory"]
        self.assertIn("reloads itself", advisory)
        self.assertIn("Do not poll", advisory)
        self.assertIn("health", advisory)

    def test_the_already_authenticated_path_carries_no_reload_advisory(self):
        page = self.LoginPage(APP)

        result = self.login_session(page).open_login_page()

        self.assertTrue(result["alreadyAuthenticated"])
        self.assertNotIn("pageMaySelfReload", result)
        self.assertNotIn("humanInputAdvisory", result)


class StatusVerdictVocabularyTest(unittest.TestCase):
    """Issue #10.4: status() and health() share one verdict vocabulary."""

    def test_status_without_resources_reports_browser_not_running(self):
        result = BrowserSession().status()

        self.assertEqual(result["verdict"], health.BROWSER_NOT_RUNNING)
        self.assertEqual(result["recommendedAction"], "browser_session action=login")
        self.assertEqual(result["sessionStatus"], "uninitialized")

    def test_held_state_classifier_shares_classify_verdicts(self):
        held = health.classify_held_state(
            session_running=True,
            on_onshape_app=True,
            login_confirmed=True,
            session_status="started",
        )

        self.assertEqual(held["verdict"], health.OK)
        self.assertEqual(held["recommendedAction"], "none")
        self.assertIn(health.OK, held["verdicts"])

    def test_held_state_classifier_needs_login_when_not_on_the_app(self):
        held = health.classify_held_state(
            session_running=True,
            on_onshape_app=False,
            login_confirmed=False,
            session_status="awaiting_login",
        )

        self.assertEqual(held["verdict"], health.LOGIN_REQUIRED)
        self.assertEqual(held["recommendedAction"], "browser_session action=login")


if __name__ == "__main__":
    unittest.main()
