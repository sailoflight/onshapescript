#!/usr/bin/env python3
"""Offline tests for browser-internal (downloads) page handling.

Measured live 2026-09-20: after ``browser_export_step`` downloads a STEP file,
Edge leaves an ``edge://downloads-hub/`` target behind. Two calls block forever on
that target: ``page.evaluate(...)`` and ``page.close()``. The second one is the
dangerous one, because ``browser_common``'s page cleanup closes EVERY page it is
handed, so passing it ``context.pages`` verbatim made every page-level tool call
fail with ``downstream_timeout`` (~32 s). These tests use fake pages only: no
Playwright import, no browser launch, no Onshape request, and no real loopback
DevTools call (that endpoint is patched out).

``python3 dev/tests/test_browser_internal_pages.py`` runs the pure-helper tests
directly; the working-page selection tests additionally skip unless the pinned
``browser_common`` wheel is importable (the same wheel the integration tests
require), because ``BrowserSession._resource`` imports its error type.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_browser_mode import session as session_module  # noqa: E402
from onshape_browser_mode.errors import BrowserLaunchError  # noqa: E402
from onshape_browser_mode.session import (  # noqa: E402
    BrowserSession,
    _browser_internal_pages_remaining,
    _cleanup_candidates,
    _close_browser_internal_page,
    _close_browser_internal_pages,
    _dismiss_browser_internal_pages,
    _is_browser_internal_noise_url,
    _is_browser_internal_url,
)
from onshape_browser_mode.settings import (  # noqa: E402
    BrowserCfg,
    BrowserConfig,
    ListenerCfg,
    PacingCfg,
)

try:
    import browser_common  # noqa: F401
    HAVE_BROWSER_COMMON = True
except ImportError:  # pragma: no cover - depends on the test environment
    HAVE_BROWSER_COMMON = False

APP = "https://cad.onshape.com/documents/doc1/w/workspace1/e/element1"
SIGNIN = "https://cad.onshape.com/signin"
EDGE_HUB = "edge://downloads-hub/"
EDGE_DOWNLOADS = "edge://downloads/"
CHROME_DOWNLOADS = "chrome://downloads/"


class FakePage:
    """A fake native page: records every probe, URL read, and close attempt."""

    def __init__(self, url, *, close_error=None, url_error=None, closed=False,
                 evaluate_error=None, evaluate_closes=False):
        self._url = url
        self._url_error = url_error
        self._close_error = close_error
        self._evaluate_error = evaluate_error
        self._evaluate_closes = evaluate_closes
        self.closed = closed
        self.close_calls = 0
        self.evaluate_calls = []
        self.title_calls = 0
        self.front_calls = 0

    @property
    def url(self):
        if self._url_error is not None:
            raise self._url_error
        return self._url

    def is_closed(self):
        return self.closed

    def close(self):
        self.close_calls += 1
        if self._close_error is not None:
            raise self._close_error
        self.closed = True

    def evaluate(self, expression):
        self.evaluate_calls.append(expression)
        if self._evaluate_error is not None:
            # Simulates the select->adopt race: the target closes while its probe
            # is in flight, so the probe fails AND the page is afterwards closed.
            if self._evaluate_closes:
                self.closed = True
            raise self._evaluate_error
        if self._evaluate_closes:
            self.closed = True
        return 2

    def title(self):
        self.title_calls += 1
        return "Synthetic page title"

    def bring_to_front(self):
        self.front_calls += 1


class FakeContext:
    def __init__(self, pages=()):
        self.pages = list(pages)
        self.new_pages = []
        self.close_calls = 0

    def new_page(self):
        page = FakePage("about:blank")
        self.pages.append(page)
        self.new_pages.append(page)
        return page

    def close(self):
        # A resident/attached browser context is never actually closed by a
        # detach, so this counter must stay at zero on the detach path.
        self.close_calls += 1
        self.closed = True


class FakePageCleanupReport:
    def __init__(self, *, complete=True):
        self.complete = complete
        self.items = ()


class FakeReleaseReport:
    def __init__(self, *, context_status="closed", driver_status="stopped", complete=True,
                 browser_fallback_used=False):
        self.context_status = context_status
        self.driver_status = driver_status
        self.complete = complete
        self.browser_fallback_used = browser_fallback_used
        self.failures = ()


class FakeResources:
    """Minimal resource owner exposing only what page selection touches."""

    def __init__(self, context, page=None, *, release_report=None):
        self.context = context
        self.page = page
        self.adopted = []
        self.release_calls = 0
        self.release_report = release_report or FakeReleaseReport()

    def snapshot(self):
        return SimpleNamespace(state="ready")

    def adopt_page(self, page):
        # Mirror browser_common/_core.py adopt_page: a closed page is refused, and
        # a fake that accepted it would make the closed-candidate tests vacuous.
        if page.is_closed():
            from browser_common import ResourceUnavailableError
            raise ResourceUnavailableError("Cannot adopt a closed page")
        self.adopted.append(page)
        self.page = page
        return page

    def reconcile_pages(self, pages, **_kwargs):
        complete = True
        for page in pages:
            if page is self.page:
                continue
            try:
                if not page.is_closed():
                    page.close()
            except Exception:
                complete = False
        return FakePageCleanupReport(complete=complete)

    def release(self):
        self.release_calls += 1
        # A resident/attached context detaches Playwright and leaves the real
        # browser (and its context) running, so the fake context is NOT closed.
        return self.release_report


def session_with(context, page=None, *, resident=False):
    if resident:
        config = BrowserConfig(
            browser=BrowserCfg(resident=True),
            pacing=PacingCfg(),
            listener=ListenerCfg(),
        )
        session = BrowserSession(config)
    else:
        session = BrowserSession()
    session._resources = FakeResources(context, page)
    session._status = "started"
    return session


class NoiseUrlClassificationTest(unittest.TestCase):
    def test_browser_internal_downloads_urls_are_noise(self):
        for url in (
            EDGE_HUB,
            "edge://downloads-hub",
            EDGE_DOWNLOADS,
            "edge://downloads",
            CHROME_DOWNLOADS,
            "chrome://downloads",
            "chrome://downloads-hub/",
            "  EDGE://Downloads-Hub/  ",
        ):
            with self.subTest(url=url):
                self.assertTrue(_is_browser_internal_noise_url(url))

    def test_onshape_pages_and_other_internal_pages_are_not_noise(self):
        for url in (
            APP,
            SIGNIN,
            "about:blank",
            "",
            None,
            "edge://settings/",
            "edge://settings/downloads",
            "chrome://history/",
            "https://cad.onshape.com/documents/downloads",
            "not a url with spaces",
        ):
            with self.subTest(url=url):
                self.assertFalse(_is_browser_internal_noise_url(url))


class DismissInternalPagesTest(unittest.TestCase):
    def test_noise_page_is_dropped_and_never_probed(self):
        noise = FakePage(EDGE_HUB)
        app = FakePage(APP)

        usable = _dismiss_browser_internal_pages([noise, app])

        self.assertEqual(usable, [app])
        self.assertEqual(noise.evaluate_calls, [])
        self.assertEqual(noise.title_calls, 0)
        # Playwright's close() on this target never returns, so it must not be used.
        self.assertEqual(noise.close_calls, 0)
        self.assertFalse(app.closed)
        self.assertEqual(app.evaluate_calls, [])

    def test_dismiss_survives_a_failing_devtools_close(self):
        noise = FakePage(EDGE_HUB)
        app = FakePage(APP)
        with mock.patch.object(session_module, "_close_browser_internal_page", return_value=False):
            usable = _dismiss_browser_internal_pages([noise, app])

        self.assertEqual(usable, [app])
        self.assertEqual(noise.close_calls, 0)

    def test_closed_pages_are_skipped(self):
        closed = FakePage(APP, closed=True)
        live = FakePage(APP)

        self.assertEqual(_dismiss_browser_internal_pages([closed, live]), [live])

    def test_unreadable_url_keeps_the_page_as_a_fallback(self):
        # A URL read error is not proof that the page is browser-internal.
        unreadable = FakePage(APP, url_error=RuntimeError("no url"))

        self.assertEqual(_dismiss_browser_internal_pages([unreadable]), [unreadable])

    def test_close_browser_internal_pages_targets_noise_only(self):
        first = FakePage(EDGE_HUB)
        second = FakePage(CHROME_DOWNLOADS)
        app = FakePage(APP)

        with mock.patch.object(session_module, "_resident_cdp_port", return_value=None):
            # With no configured DevTools endpoint nothing can be requested, and
            # no page is ever closed through Playwright.
            self.assertEqual(_close_browser_internal_pages([first, app, second]), 0)
        for page in (first, second, app):
            self.assertEqual(page.close_calls, 0)
            self.assertFalse(page.closed)
        with mock.patch.object(session_module, "_resident_cdp_port", return_value=None):
            self.assertFalse(_close_browser_internal_page(FakePage(EDGE_HUB)))


class CleanupCandidatesTest(unittest.TestCase):
    """browser_common closes every page it is handed, so that list must be safe."""

    def test_internal_pages_are_never_handed_to_the_cleaner(self):
        hub = FakePage(EDGE_HUB)
        downloads = FakePage(EDGE_DOWNLOADS)
        chrome = FakePage(CHROME_DOWNLOADS)
        app = FakePage(APP)

        self.assertEqual(_cleanup_candidates([hub, app, downloads, chrome]), [app])

    def test_unreadable_url_is_left_alone(self):
        unreadable = FakePage(APP, url_error=RuntimeError("no url"))

        self.assertEqual(_cleanup_candidates([unreadable]), [])

    def test_about_blank_popups_stay_cleanable(self):
        popup = FakePage("about:blank")

        self.assertEqual(_cleanup_candidates([popup]), [popup])

    def test_internal_url_classification_is_scheme_based(self):
        self.assertTrue(_is_browser_internal_url(EDGE_HUB))
        self.assertTrue(_is_browser_internal_url("devtools://devtools/bundled/inspector.html"))
        self.assertFalse(_is_browser_internal_url(APP))
        self.assertFalse(_is_browser_internal_url("about:blank"))
        self.assertFalse(_is_browser_internal_url(None))


class DevtoolsTargetProbeTest(unittest.TestCase):
    """The close helper talks to DevTools directly, so its inputs must be gated.

    Every DevTools call is patched out here: these tests prove which requests the
    helpers would make, not that a browser is reachable.
    """

    def fake_listing(self, targets):
        return mock.patch.object(
            session_module, "_devtools_http", return_value=json.dumps(targets)
        )

    def test_resident_port_is_withheld_when_residency_is_disabled(self):
        # resident_port has a default value, so reading it unconditionally would
        # send DevTools close requests to whatever unrelated process listens there.
        config = SimpleNamespace(browser=SimpleNamespace(resident=False, resident_port=9333))

        with mock.patch.object(session_module, "load_browser_config", return_value=config):
            self.assertIsNone(session_module._resident_cdp_port())

    def test_resident_port_is_returned_when_residency_is_enabled(self):
        config = SimpleNamespace(browser=SimpleNamespace(resident=True, resident_port=9444))

        with mock.patch.object(session_module, "load_browser_config", return_value=config):
            self.assertEqual(session_module._resident_cdp_port(), 9444)

    def test_resident_port_is_none_when_the_config_cannot_be_read(self):
        with mock.patch.object(
            session_module, "load_browser_config", side_effect=RuntimeError("boom")
        ):
            self.assertIsNone(session_module._resident_cdp_port())

    def test_remaining_is_none_without_a_devtools_endpoint(self):
        with mock.patch.object(session_module, "_resident_cdp_port", return_value=None):
            self.assertIsNone(_browser_internal_pages_remaining())

    def test_remaining_is_none_when_the_endpoint_is_unreachable(self):
        # Unknown is reported as unknown, never as zero internal pages.
        with mock.patch.object(
            session_module, "_resident_cdp_port", return_value=9333
        ), mock.patch.object(
            session_module, "_devtools_http", side_effect=OSError("connection refused")
        ):
            self.assertIsNone(_browser_internal_pages_remaining())

    def test_remaining_counts_listed_internal_pages_only(self):
        listing = [
            {"type": "page", "id": "T1", "url": EDGE_HUB},
            {"type": "page", "id": "T2", "url": APP},
            {"type": "page", "id": "T3", "url": EDGE_DOWNLOADS},
            {"type": "service_worker", "id": "S1", "url": EDGE_HUB},
            "not a target",
        ]

        with mock.patch.object(
            session_module, "_resident_cdp_port", return_value=9333
        ), self.fake_listing(listing):
            self.assertEqual(_browser_internal_pages_remaining(), 2)

    def test_remaining_is_zero_when_nothing_internal_is_listed(self):
        with mock.patch.object(
            session_module, "_resident_cdp_port", return_value=9333
        ), self.fake_listing([{"type": "page", "id": "T2", "url": APP}]):
            self.assertEqual(_browser_internal_pages_remaining(), 0)

    def test_close_accepts_a_listed_internal_page(self):
        calls = []

        def fake_devtools(port, path, timeout):
            calls.append(path)
            return json.dumps([{"type": "page", "id": "T1", "url": EDGE_HUB}])

        with mock.patch.object(
            session_module, "_resident_cdp_port", return_value=9333
        ), mock.patch.object(session_module, "_devtools_http", side_effect=fake_devtools):
            self.assertTrue(_close_browser_internal_page(FakePage(EDGE_HUB)))

        self.assertEqual(calls, ["/json/list", "/json/close/T1"])

    def test_close_never_targets_a_page_with_a_different_url(self):
        calls = []

        def fake_devtools(port, path, timeout):
            calls.append(path)
            return json.dumps([{"type": "page", "id": "T2", "url": APP}])

        with mock.patch.object(
            session_module, "_resident_cdp_port", return_value=9333
        ), mock.patch.object(session_module, "_devtools_http", side_effect=fake_devtools):
            self.assertFalse(_close_browser_internal_page(FakePage(EDGE_HUB)))

        self.assertEqual(calls, ["/json/list"])

    def test_close_never_targets_a_non_page_target_with_the_same_url(self):
        calls = []

        def fake_devtools(port, path, timeout):
            calls.append(path)
            return json.dumps([{"type": "service_worker", "id": "S1", "url": EDGE_HUB}])

        with mock.patch.object(
            session_module, "_resident_cdp_port", return_value=9333
        ), mock.patch.object(session_module, "_devtools_http", side_effect=fake_devtools):
            self.assertFalse(_close_browser_internal_page(FakePage(EDGE_HUB)))

        self.assertEqual(calls, ["/json/list"])


@unittest.skipUnless(HAVE_BROWSER_COMMON, "browser_common wheel is not importable")
class WorkingPageSelectionTest(unittest.TestCase):
    def setUp(self):
        save_url = mock.patch.object(BrowserSession, "_save_app_url")
        self.save_url = save_url.start()
        self.addCleanup(save_url.stop)

    def test_downloads_page_first_is_dropped_and_app_page_is_chosen(self):
        noise = FakePage(EDGE_HUB)
        app = FakePage(APP)
        context = FakeContext([noise, app])
        session = session_with(context)

        page = session.start()

        self.assertIs(page, app)
        self.assertIs(session.page, app)
        self.assertEqual(noise.close_calls, 0)  # never closed through Playwright
        self.assertEqual(noise.evaluate_calls, [])
        self.assertEqual(app.evaluate_calls, ["1 + 1"])
        self.assertEqual(session._resources.adopted, [app])
        self.assertEqual(context.new_pages, [])

    def test_noise_page_does_not_displace_the_current_app_page(self):
        noise = FakePage(EDGE_HUB)
        app = FakePage(APP)
        context = FakeContext([noise, app])
        session = session_with(context, page=app)

        page = session.start()

        self.assertIs(page, app)
        self.assertEqual(noise.close_calls, 0)  # never closed through Playwright
        self.assertEqual(noise.evaluate_calls, [])
        self.assertEqual(app.evaluate_calls, ["1 + 1"])

    def test_failing_app_probe_still_reaches_the_next_live_page(self):
        # Ordering guard: the noise filter must not drop the non-preferred pages
        # that the candidate loop falls back to after a navigation-time failure.
        app = FakePage(APP, evaluate_error=RuntimeError("Execution context was destroyed"))
        signin = FakePage(SIGNIN)
        session = session_with(FakeContext([app, signin]))

        page = session.start()

        self.assertIs(page, signin)
        self.assertEqual(app.evaluate_calls, ["1 + 1"])
        self.assertEqual(signin.evaluate_calls, ["1 + 1"])

    def test_prepare_page_replaces_a_noise_working_page(self):
        noise = FakePage(EDGE_HUB)
        app = FakePage(APP)
        session = session_with(FakeContext([noise, app]))

        page = session._prepare_page(noise)

        self.assertIs(page, app)
        self.assertEqual(noise.close_calls, 0)  # never closed through Playwright
        self.assertEqual(noise.evaluate_calls, [])
        self.assertIs(session.page, app)

    def test_only_noise_pages_opens_a_fresh_usable_page(self):
        noise = FakePage(EDGE_HUB)
        context = FakeContext([noise])
        session = session_with(context)

        page = session.start()

        self.assertEqual(noise.evaluate_calls, [])
        self.assertEqual(noise.close_calls, 0)  # never closed through Playwright
        self.assertEqual(context.new_pages, [page])
        self.assertIs(session.page, page)

    def test_noise_working_page_inside_a_temporary_scope_is_not_used(self):
        noise = FakePage(EDGE_HUB)
        app = FakePage(APP)
        session = session_with(FakeContext([noise, app]), page=noise)
        session._temporary_depth = 1

        with self.assertRaisesRegex(BrowserLaunchError, "temporary workflow"):
            session.start()
        self.assertEqual(noise.close_calls, 0)  # never closed through Playwright
        self.assertEqual(noise.evaluate_calls, [])
        self.assertEqual(session._resources.adopted, [])
        self.assertFalse(app.closed)

    def test_prepare_page_refuses_when_only_noise_pages_remain(self):
        noise = FakePage(EDGE_HUB)
        session = session_with(FakeContext([noise]))

        with self.assertRaisesRegex(BrowserLaunchError, "browser-internal pages"):
            session._prepare_page(noise)
        self.assertEqual(noise.evaluate_calls, [])

    def test_single_working_page_enforcement_never_hands_over_an_internal_page(self):
        # The real reconcile_pages closes every page it is handed, and page.close()
        # on downloads-hub never returns, so the internal page must not reach it.
        # The fake resource owner closes whatever it is given, so a close here
        # would prove the filter is missing.
        noise = FakePage(EDGE_HUB)
        app = FakePage(APP)
        session = session_with(FakeContext([noise, app]))

        session._enforce_single_working_page(app)

        self.assertEqual(noise.close_calls, 0)
        self.assertFalse(noise.closed)
        self.assertEqual(app.close_calls, 0)

    def test_status_never_probes_a_noise_page(self):
        noise = FakePage(EDGE_HUB)
        app = FakePage(APP)
        session = session_with(FakeContext([noise, app]), page=noise)

        status = session.status()

        self.assertEqual(noise.title_calls, 0)
        self.assertEqual(app.title_calls, 1)
        self.assertEqual(status["pageUrl"], APP)
        self.assertIn({"url": EDGE_HUB, "browserInternal": True}, status["pages"])
        self.assertIn({"url": APP}, status["pages"])
        self.save_url.assert_called_once_with(APP)


class ProfileIsolationConfigTest(unittest.TestCase):
    """Issue #7.3: isolation is a directory choice, and the default is unchanged."""

    def test_the_default_profile_directory_is_the_shared_persistent_one(self):
        session = BrowserSession(BrowserConfig(browser=BrowserCfg(), pacing=PacingCfg(), listener=ListenerCfg()))

        self.assertEqual(
            session.profile_dir(),
            (session_module.PACKAGE_ROOT / "user_data" / "onshape_profile").resolve(),
        )

    def test_an_isolated_directory_overrides_the_shared_profile(self):
        session = BrowserSession(BrowserConfig(
            browser=BrowserCfg(isolated_user_data_dir="user_data/isolated_probe"),
            pacing=PacingCfg(),
            listener=ListenerCfg(),
        ))

        self.assertEqual(
            session.profile_dir(),
            (session_module.PACKAGE_ROOT / "user_data" / "isolated_probe").resolve(),
        )


@unittest.skipUnless(HAVE_BROWSER_COMMON, "browser_common wheel is not importable")
class ClosedCandidateTest(unittest.TestCase):
    """Issue #10: a closed candidate must never be adopted.

    browser_common's ``adopt_page`` raises ``ResourceUnavailableError`` for a closed
    page (``_core.py``). The old fallback adopted ``candidates[0]`` unconditionally,
    so a page that closed during its evaluate probe turned a recoverable selection
    into a ``Cannot adopt a closed page`` failure.
    """

    def test_a_closed_candidate_is_skipped_and_the_live_page_is_used(self):
        closed = FakePage(APP, closed=True)
        live = FakePage(APP)
        context = FakeContext([closed, live])
        session = session_with(context)

        page = session.start()

        self.assertIs(page, live)
        self.assertIs(session.page, live)
        self.assertEqual(closed.evaluate_calls, [])  # a closed page is never probed
        self.assertEqual(context.new_pages, [])
        selection = session.status()["pageSelection"]
        self.assertEqual(selection["considered"], 2)
        self.assertEqual(selection["selected"], "reused")
        self.assertIn({"url": APP, "reason": "closed"}, selection["discarded"])

    def test_a_candidate_that_closes_during_its_probe_does_not_raise(self):
        closing = FakePage(
            APP, evaluate_error=RuntimeError("Target closed"), evaluate_closes=True
        )
        live = FakePage(SIGNIN)
        session = session_with(FakeContext([closing, live]))

        page = session.start()

        self.assertIs(page, live)
        self.assertEqual(closing.evaluate_calls, ["1 + 1"])
        selection = session.last_page_selection
        self.assertIn({"url": APP, "reason": "closed"}, selection["discarded"])
        self.assertEqual(selection["selected"], "reused")

    def test_a_candidate_that_closes_between_probe_and_adopt_advances(self):
        # The probe answers, then the page closes before adopt_page runs: the
        # adopt call raises exactly as browser_common would, and selection must
        # move on instead of propagating that error.
        racing = FakePage(APP, evaluate_closes=True)
        live = FakePage(SIGNIN)
        session = session_with(FakeContext([racing, live]))

        page = session.start()

        self.assertIs(page, live)
        self.assertEqual(racing.evaluate_calls, ["1 + 1"])
        self.assertIn(
            {"url": APP, "reason": "closed"}, session.last_page_selection["discarded"]
        )

    def test_a_closed_first_fallback_hands_over_to_the_next_survivor(self):
        # The exact regression: no probe answered, and the page the old code
        # blindly adopted as `candidates[0]` had closed. The next live candidate
        # must be adopted instead of raising "Cannot adopt a closed page".
        closed_first = FakePage(
            APP, evaluate_error=RuntimeError("Target closed"), evaluate_closes=True
        )
        second = FakePage(SIGNIN, evaluate_error=RuntimeError("Execution context was destroyed"))
        session = session_with(FakeContext([closed_first, second]))

        page = session.start()

        self.assertIs(page, second)
        self.assertIs(session.page, second)
        self.assertIn(
            {"url": APP, "reason": "closed"}, session.last_page_selection["discarded"]
        )

    def test_when_every_candidate_is_closed_a_new_page_is_opened(self):
        closed = FakePage(APP, closed=True)
        context = FakeContext([closed])
        session = session_with(context)

        page = session.start()

        self.assertEqual(context.new_pages, [page])
        self.assertIs(session.page, page)
        self.assertEqual(session.last_page_selection["selected"], "new")
        self.assertIn(
            {"url": APP, "reason": "closed"}, session.last_page_selection["discarded"]
        )

    def test_the_no_usable_page_error_names_the_login_recovery(self):
        noise = FakePage(EDGE_HUB)
        session = session_with(FakeContext([noise]))

        with self.assertRaisesRegex(BrowserLaunchError, r"browser_session action=login"):
            session._prepare_page(noise)


@unittest.skipUnless(HAVE_BROWSER_COMMON, "browser_common wheel is not importable")
class DetachTest(unittest.TestCase):
    """Issue #6: detach is honest about what the pinned wheel can do."""

    def test_detach_on_an_attached_resident_leaves_the_browser_running(self):
        context = FakeContext([FakePage(APP)])
        session = session_with(context, page=context.pages[0], resident=True)

        report = session.detach()

        self.assertTrue(report["detached"])
        self.assertTrue(report["supported"])
        self.assertEqual(report["releaseMethod"], "detach")
        self.assertFalse(report["contextClosed"])
        self.assertTrue(report["browserLeftRunning"])
        self.assertTrue(report["profileReleased"])
        self.assertEqual(report["sessionStatus"], "closed")
        self.assertFalse(report["loginStateMayNeedRefresh"])
        # The adapter's context.close() is a DETACH: the real browser context
        # survives, so nothing here may close the fake native context.
        self.assertEqual(context.close_calls, 0)
        self.assertEqual(session._resources.release_calls, 1)

    def test_detach_outside_resident_mode_refuses_and_changes_nothing(self):
        context = FakeContext([FakePage(APP)])
        session = session_with(context, page=context.pages[0], resident=False)

        report = session.detach()

        self.assertFalse(report["detached"])
        self.assertFalse(report["supported"])
        self.assertEqual(report["recommended"], "browser_session action=release")
        self.assertIn("browser.resident=true", report["alternative"])
        self.assertEqual(report["reason"].count("."), 1, "one precise sentence")
        self.assertEqual(report["sessionStatus"], "started")
        self.assertEqual(context.close_calls, 0)
        self.assertEqual(session._resources.release_calls, 0)
        self.assertEqual(session._resources.adopted, [])


@unittest.skipUnless(HAVE_BROWSER_COMMON, "browser_common wheel is not importable")
class StatusProfileTest(unittest.TestCase):
    """Issue #7: the profile is persistent and non-anonymous; report booleans only."""

    def test_status_reports_profile_bytes_and_no_marker_on_an_empty_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = session_with(FakeContext([]))
            with mock.patch.object(session, "profile_dir", return_value=Path(tmp)):
                status = session.status()

        self.assertEqual(status["profileBytes"], 0)
        self.assertTrue(status["profileBytesComplete"])
        self.assertFalse(status["accountMarkerDetected"])

    def test_a_malformed_local_state_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Local State").write_text("{not json", encoding="utf-8")
            session = session_with(FakeContext([]))
            with mock.patch.object(session, "profile_dir", return_value=Path(tmp)):
                status = session.status()

        self.assertFalse(status["accountMarkerDetected"])
        self.assertIsInstance(status["profileBytes"], int)

    def test_a_missing_profile_dir_reports_an_absent_size_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            session = session_with(FakeContext([]))
            with mock.patch.object(session, "profile_dir", return_value=missing):
                status = session.status()

        self.assertIsNone(status["profileBytes"])
        self.assertFalse(status["profileBytesComplete"])
        self.assertFalse(status["accountMarkerDetected"])

    def test_an_edge_account_marker_is_reported_as_a_boolean_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Local State").write_text(
                json.dumps({"profile": {"info_cache": {"Default": {"user_name": "nobody@example.com"}}}}),
                encoding="utf-8",
            )
            session = session_with(FakeContext([]))
            with mock.patch.object(session, "profile_dir", return_value=Path(tmp)):
                status = session.status()

        self.assertIs(status["accountMarkerDetected"], True)
        # The account value itself must never leak into the payload.
        self.assertNotIn("nobody@example.com", json.dumps(status))

    def test_profile_bytes_are_capped_and_flagged_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(5):
                (Path(tmp) / f"file-{index}.bin").write_bytes(b"x" * 10)
            session = session_with(FakeContext([]))
            with mock.patch.object(session, "profile_dir", return_value=Path(tmp)), \
                    mock.patch.object(session_module, "_PROFILE_WALK_FILE_CAP", 2):
                status = session.status()

        self.assertEqual(status["profileBytes"], 20)
        self.assertFalse(status["profileBytesComplete"])


@unittest.skipUnless(HAVE_BROWSER_COMMON, "browser_common wheel is not importable")
class StatusVerdictTest(unittest.TestCase):
    """Issue #10.4: status() speaks the health verdict vocabulary additively."""

    def test_status_on_an_app_page_is_ok_and_keeps_session_status(self):
        app = FakePage(APP)
        session = session_with(FakeContext([app]), page=app)

        status = session.status()

        self.assertEqual(status["verdict"], "ok")
        self.assertEqual(status["recommendedAction"], "none")
        self.assertEqual(status["sessionStatus"], "started")

    def test_status_on_the_signin_page_recommends_login(self):
        page = FakePage(SIGNIN)
        session = session_with(FakeContext([page]), page=page)

        status = session.status()

        self.assertEqual(status["verdict"], "login_required")
        self.assertEqual(status["recommendedAction"], "browser_session action=login")
        self.assertIn("sessionStatus", status)


if __name__ == "__main__":
    unittest.main()
