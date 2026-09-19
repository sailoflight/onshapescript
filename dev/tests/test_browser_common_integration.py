"""Offline adapter contracts against the distributed browser_common wheel.

Run with PYTHONPATH=temp/browser-common-site python3 -m unittest
 dev.tests.test_browser_common_integration -v. Only native Playwright resources
are faked; BrowserSession and SyncSession execute their real lifecycle logic.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from onshape_browser_mode import session as session_module
from onshape_browser_mode.errors import BrowserLaunchError
from onshape_browser_mode.session import BrowserSession
from onshape_browser_mode.settings import BrowserCfg, BrowserConfig, ListenerCfg, PacingCfg

try:
    import browser_common
    from browser_common import ExecutionContextError, PageCleanupError, SyncSession
except ImportError as exc:
    raise ImportError(
        "Browser integration tests require the pinned lijq-browser-common 0.1.0.dev2 wheel. "
        "From the repository root run: python3 -m pip install --no-deps "
        "--target temp/browser-common-site "
        "onshape_browser_mode/wheels/lijq_browser_common-0.1.0.dev2-py3-none-any.whl; "
        "then run tests with PYTHONPATH=temp/browser-common-site. "
        "See docs/development/START.md."
    ) from exc

ROOT = Path(__file__).resolve().parents[2]
WHEEL = ROOT / "onshape_browser_mode/wheels/lijq_browser_common-0.1.0.dev2-py3-none-any.whl"
WHEEL_SHA256 = "c1763265aa5c968032e7d18116d07e18ddbdbd873a4d6c7db033686a58913cc8"
APP = "https://cad.onshape.com/documents/test/w/workspace/e/studio"
SIGNIN = "https://cad.onshape.com/signin"
SECRET = "synthetic-cookie=do-not-expose-this-value"


def outcome(queue, default=None):
    value = queue.pop(0) if queue else default
    if isinstance(value, BaseException):
        raise value
    return value


class NativeEvents:
    def __init__(self):
        self.listeners = {}

    def on(self, event, callback):
        self.listeners.setdefault(event, []).append(callback)

    def remove_listener(self, event, callback):
        self.listeners[event].remove(callback)

    def emit(self, event, *args):
        for callback in list(self.listeners.get(event, [])):
            callback(*args)


class NativePage(NativeEvents):
    def __init__(self, context, url="about:blank"):
        super().__init__()
        self.context = context
        self.url = url
        self.closed = False
        self.close_calls = 0
        self.close_outcomes = []
        self.evaluate_outcomes = []
        self.title_outcomes = []
        self.title_calls = 0
        # Manual navigation is not visible through cached properties until a
        # native RPC pumps the synchronous Playwright dispatcher.
        self.pending_url = None
        self.front_calls = 0
        self.locator_result = object()

    def is_closed(self):
        return self.closed

    def close(self):
        self.close_calls += 1
        outcome(self.close_outcomes)
        self.closed = True
        if self in self.context.pages:
            self.context.pages.remove(self)
        self.emit("close", self)

    def evaluate(self, expression):
        return outcome(self.evaluate_outcomes, 2)

    def title(self):
        self.title_calls += 1
        # Dispatch may update cached URL even when the read subsequently fails
        # because its execution context was destroyed during navigation.
        if self.pending_url is not None:
            self.url = self.pending_url
            self.pending_url = None
        return outcome(self.title_outcomes, "Synthetic page title")

    def bring_to_front(self):
        self.front_calls += 1

    def locator(self, selector):
        return self.locator_result


class NativeBrowser:
    def __init__(self, context):
        self.context = context
        self.close_outcomes = []
        self.close_calls = 0

    def close(self):
        self.close_calls += 1
        outcome(self.close_outcomes)
        self.context.invalidate()


class NativeContext(NativeEvents):
    def __init__(self, urls=(APP,)):
        super().__init__()
        self.pages = [NativePage(self, url) for url in urls]
        self.browser = NativeBrowser(self)
        self.closed = False
        self.close_outcomes = []
        self.new_page_outcomes = []
        self.close_calls = 0
        self.new_page_calls = 0

    def new_page(self):
        self.new_page_calls += 1
        outcome(self.new_page_outcomes)
        page = NativePage(self)
        self.pages.append(page)
        self.emit("page", page)
        return page

    def invalidate(self):
        self.closed = True
        for page in self.pages:
            page.closed = True
        self.pages = []
        self.emit("close", self)

    def close(self):
        self.close_calls += 1
        outcome(self.close_outcomes)
        self.invalidate()


class NativeDriver:
    def __init__(self, launch_outcomes):
        self.chromium = self
        self.launch_outcomes = list(launch_outcomes)
        self.launch_calls = []
        self.stop_outcomes = []
        self.stop_calls = 0

    def launch_persistent_context(self, **kwargs):
        self.launch_calls.append(kwargs)
        if not self.launch_outcomes:
            raise AssertionError("Unexpected extra browser launch")
        return outcome(self.launch_outcomes)

    def stop(self):
        self.stop_calls += 1
        outcome(self.stop_outcomes)


class NativeManager:
    def __init__(self, *launch_outcomes):
        self.driver = NativeDriver(launch_outcomes)
        self.start_calls = 0
        self.exit_calls = 0

    def start(self):
        self.start_calls += 1
        return self.driver

    def __exit__(self, *args):
        self.exit_calls += 1


class BrowserCommonIntegrationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="onshape-common-contract-")
        self.addCleanup(temporary.cleanup)
        self.profile = Path(temporary.name) / "profile"
        save_url = mock.patch.object(BrowserSession, "_save_app_url")
        self.save_url = save_url.start()
        self.addCleanup(save_url.stop)
        # Any missed injection must fail before importing/starting real Playwright.
        availability = mock.patch.object(
            BrowserSession, "playwright_available", return_value=False
        )
        self.availability = availability.start()
        self.addCleanup(availability.stop)

    def session(self, manager, **options):
        options.setdefault("user_data_dir", str(self.profile))
        config = BrowserConfig(BrowserCfg(**options), PacingCfg(), ListenerCfg())
        session = BrowserSession(config, playwright_factory=lambda: manager)
        self.addCleanup(session.release)
        return session

    def test_native_identity_lazy_owner_and_app_restore_preference(self):
        context = NativeContext(("about:blank", SIGNIN, APP))
        blank, signin, app = context.pages
        manager = NativeManager(context)
        session = self.session(manager)
        self.assertIsNone(session._resources)
        self.assertIsNone(session.page)
        self.assertIsNone(session.context)
        self.assertFalse(self.profile.exists())
        self.assertIs(session.start(), app)
        self.assertIsInstance(session._resources, SyncSession)
        owner = session._resources
        self.assertIs(session.page, owner.page)
        self.assertIs(session.context, context)
        self.assertIs(session.context, owner.context)
        self.assertIs(session.page.locator("button"), app.locator_result)
        self.assertTrue(blank.closed)
        self.assertTrue(signin.closed)
        self.assertTrue(session.login_confirmed)
        self.assertIs(session.start(), app)
        self.assertIs(session._resources, owner)
        self.assertEqual(manager.start_calls, 1)
        self.assertEqual(len(manager.driver.launch_calls), 1)
        self.availability.assert_not_called()
        released = session.release()
        self.assertTrue(released["released"])
        self.assertTrue(released["profileReleased"])
        self.assertIsNone(session.page)
        self.assertIsNone(session.context)
        self.assertFalse(session.release()["released"])

    def test_launch_config_preserves_executable_priority_and_relative_profile(self):
        manager = NativeManager(NativeContext())
        session = self.session(
            manager, user_data_dir="relative/profile", executable_path="/fake/edge",
            channel="chrome", headless=False, locale="en-GB", timezone="Europe/London",
            proxy_server="http://127.0.0.1:8123",
        )
        # Use a synthetic module root; never touch the real login profile.
        with mock.patch.object(session_module, "PACKAGE_ROOT", self.profile.parent):
            expected = (self.profile.parent / "relative/profile").resolve()
            self.assertEqual(session.profile_dir(), expected)
            session.start()
        kwargs = manager.driver.launch_calls[0]
        self.assertEqual(kwargs["user_data_dir"], str(expected))
        self.assertEqual(kwargs["executable_path"], "/fake/edge")
        self.assertNotIn("channel", kwargs)
        self.assertEqual(kwargs["locale"], "en-GB")
        self.assertEqual(kwargs["timezone_id"], "Europe/London")
        self.assertEqual(kwargs["proxy"], {"server": "http://127.0.0.1:8123"})
        self.assertEqual(kwargs["viewport"], {"width": 1280, "height": 800})
        self.assertFalse(kwargs["headless"])

    def test_closed_working_page_recovers_new_native_page_without_relaunch(self):
        context = NativeContext()
        manager = NativeManager(context)
        session = self.session(manager)
        old = session.start()
        old.close()
        self.assertIsNone(session.page)
        fresh = session.start()
        self.assertIs(fresh, session.page)
        self.assertIs(fresh.context, context)
        self.assertFalse(fresh.closed)
        self.assertEqual(context.new_page_calls, 1)
        self.assertEqual(manager.start_calls, 1)

    def test_temporary_scope_protects_popup_and_explicit_adoption_transfers_ownership(self):
        context = NativeContext((SIGNIN,))
        session = self.session(NativeManager(context))
        main = session.start()
        with session.temporary_pages() as scope:
            popup = scope.track(context.new_page())
            popup.url = APP
            stray = context.new_page()
            self.assertIs(session.start(), main)
            self.assertFalse(popup.closed)
            self.assertTrue(stray.closed)
            self.assertIs(session.page, main)
            session.adopt_page(popup)
            self.assertIs(session.page, popup)
            session._enforce_single_working_page(popup)
            self.assertTrue(main.closed)
        self.assertTrue(scope.report.complete)
        self.assertFalse(popup.closed)
        self.assertIs(session.page, popup)
        with session.temporary_pages() as second_scope:
            temporary = second_scope.track(context.new_page())
        self.assertTrue(temporary.closed)
        self.assertFalse(popup.closed)

    def test_closed_working_page_inside_scope_requires_explicit_adoption(self):
        context = NativeContext((SIGNIN,))
        manager = NativeManager(context)
        session = self.session(manager)
        main = session.start()
        owner = session._resources
        with session.temporary_pages() as scope:
            popup = scope.track(context.new_page())
            popup.url = APP
            main.close()
            with self.assertRaisesRegex(BrowserLaunchError, "explicitly adopt"):
                session.start()
            self.assertIsNone(session.page)
            self.assertIs(session.context, context)
            self.assertIs(session._resources, owner)
            self.assertFalse(popup.closed)
            self.assertEqual(context.new_page_calls, 1)
            self.assertEqual(manager.start_calls, 1)
            session.adopt_page(popup)
            self.assertIs(session.start(), popup)
        self.assertTrue(scope.report.complete)
        self.assertFalse(popup.closed)
        self.assertIs(session.page, popup)

    def test_status_reports_application_page_without_adopting_it(self):
        context = NativeContext((SIGNIN,))
        session = self.session(NativeManager(context))
        main = session.start()
        app = context.new_page()
        app.url = APP
        status = session.status()
        self.assertEqual(status["pageUrl"], APP)
        self.assertIs(session.page, main)
        self.assertFalse(main.closed)
        self.assertFalse(app.closed)
        self.assertIs(session.start(), app)
        self.assertTrue(main.closed)

    def test_status_refreshes_cached_manual_login_without_preparing_pages(self):
        context = NativeContext((SIGNIN,))
        manager = NativeManager(context)
        session = self.session(manager)
        main = session.start()
        owner = session._resources
        session._status = "awaiting_login"
        session.human_action_required = True
        main.pending_url = APP
        self.assertEqual(main.url, SIGNIN)
        front_calls = main.front_calls
        with mock.patch.object(session, "start", side_effect=AssertionError("status must not start")), \
             mock.patch.object(session, "adopt_page", side_effect=AssertionError("status must not adopt")), \
             mock.patch.object(session, "_enforce_single_working_page", side_effect=AssertionError("status must not clean tabs")):
            status = session.status()
        self.assertEqual(main.title_calls, 1)
        self.assertEqual(status["pageUrl"], APP)
        self.assertEqual(status["pages"], [{"url": APP}])
        self.assertEqual(status["sessionStatus"], "started")
        self.assertTrue(status["loginConfirmed"])
        self.assertTrue(session.login_confirmed)
        self.assertFalse(status["humanActionRequired"])
        self.save_url.assert_called_once_with(APP)
        self.assertIs(session._resources, owner)
        self.assertIs(session.page, main)
        self.assertEqual(main.front_calls, front_calls)
        self.assertEqual(context.new_page_calls, 0)
        self.assertEqual(context.close_calls, 0)
        self.assertEqual(manager.start_calls, 1)

    def test_status_signin_refresh_clears_sticky_login_confirmation(self):
        context = NativeContext()
        session = self.session(NativeManager(context))
        main = session.start()
        self.assertTrue(session.login_confirmed)
        main.pending_url = SIGNIN + "?redirect=documents"
        self.assertEqual(main.url, APP)
        status = session.status()
        self.assertEqual(main.title_calls, 1)
        self.assertEqual(status["pageUrl"], SIGNIN + "?redirect=documents")
        self.assertFalse(status["loginConfirmed"])
        self.assertFalse(session.login_confirmed)
        self.assertTrue(status["humanActionRequired"])
        self.assertEqual(status["sessionStatus"], "awaiting_login")
        self.save_url.assert_not_called()

    def test_status_native_read_failure_preserves_login_state_without_relaunch(self):
        for logged_in in (False, True):
            with self.subTest(logged_in=logged_in):
                context = NativeContext((APP if logged_in else SIGNIN,))
                manager = NativeManager(context)
                session = self.session(manager)
                main = session.start()
                owner = session._resources
                session._status = "started" if logged_in else "awaiting_login"
                session.human_action_required = not logged_in
                main.pending_url = SIGNIN if logged_in else APP
                main.title_outcomes = [RuntimeError("Execution context was destroyed: " + SECRET)]
                with mock.patch.object(session, "start", side_effect=AssertionError("status must not restart")):
                    status = session.status()
                self.assertEqual(main.title_calls, 1)
                self.assertEqual(status["loginConfirmed"], logged_in)
                self.assertEqual(status["humanActionRequired"], not logged_in)
                self.assertEqual(status["sessionStatus"], "started" if logged_in else "awaiting_login")
                self.assertNotIn(SECRET, json.dumps(status))
                self.assertIs(session._resources, owner)
                self.assertIs(session.page, main)
                self.assertEqual(context.close_calls, 0)
                self.assertEqual(context.new_page_calls, 0)
                self.assertEqual(manager.driver.stop_calls, 0)
                self.assertEqual(manager.start_calls, 1)
                self.save_url.assert_not_called()
                recovered = session.status()
                self.assertEqual(recovered["loginConfirmed"], not logged_in)
                self.save_url.reset_mock()

    def test_status_refreshes_existing_page_when_working_page_closed_without_adoption(self):
        context = NativeContext((SIGNIN,))
        session = self.session(NativeManager(context))
        main = session.start()
        app = context.new_page()
        app.url = SIGNIN
        app.pending_url = APP
        main.close()
        status = session.status()
        self.assertEqual(app.title_calls, 1)
        self.assertEqual(status["pageUrl"], APP)
        self.assertTrue(status["loginConfirmed"])
        self.assertIsNone(session.page)
        self.assertFalse(app.closed)
        self.assertEqual(context.new_page_calls, 1)

    def test_status_native_execution_context_error_is_not_swallowed(self):
        context = NativeContext()
        session = self.session(NativeManager(context))
        main = session.start()
        main.title_outcomes = [ExecutionContextError("Wrong execution thread")]
        with self.assertRaises(ExecutionContextError):
            session.status()
        self.assertEqual(main.title_calls, 1)
        self.assertTrue(session.login_confirmed)
        self.assertEqual(context.close_calls, 0)

    def test_navigation_evaluate_failure_does_not_relaunch(self):
        context = NativeContext()
        manager = NativeManager(context)
        session = self.session(manager)
        app = session.start()
        app.evaluate_outcomes = [RuntimeError("Execution context was destroyed")]
        self.assertIs(session.start(), app)
        self.assertEqual(manager.start_calls, 1)
        self.assertEqual(context.new_page_calls, 0)

    def test_incomplete_reconcile_raises_type_only_error_and_retains_owner(self):
        context = NativeContext()
        session = self.session(NativeManager(context))
        main = session.start()
        owner = session._resources
        stray = context.new_page()
        stray.close_outcomes = [RuntimeError(SECRET)]
        with self.assertRaises(PageCleanupError) as caught:
            session._enforce_single_working_page(main)
        self.assertFalse(caught.exception.report.complete)
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertIs(session._resources, owner)
        self.assertIs(session.page, main)
        self.assertFalse(stray.closed)
        session._enforce_single_working_page(main)
        self.assertTrue(stray.closed)

    def test_startup_partial_cleanup_failure_stops_retry_and_preserves_owner(self):
        context = NativeContext(())
        context.new_page_outcomes = [RuntimeError(SECRET)]
        context.close_outcomes = [RuntimeError(SECRET)]
        context.browser.close_outcomes = [RuntimeError(SECRET)]
        manager = NativeManager(context)
        session = self.session(manager)
        with mock.patch.object(session_module.time, "sleep") as sleep:
            with self.assertRaises(BrowserLaunchError) as caught:
                session.start()
            owner = session._resources
            self.assertNotIn(SECRET, str(caught.exception))
            self.assertFalse(owner.last_release_report.complete)
            self.assertEqual(owner.last_release_report.driver_status, "skipped")
            self.assertEqual(manager.driver.stop_calls, 0)
            with self.assertRaisesRegex(BrowserLaunchError, "release is incomplete"):
                session.start()
            sleep.assert_not_called()
        self.assertIs(session._resources, owner)
        self.assertEqual(manager.start_calls, 1)
        self.assertTrue(session.release()["profileReleased"])

    def test_cleaned_launch_failures_retry_three_times_with_same_owner(self):
        manager = NativeManager(*(RuntimeError(SECRET) for _ in range(3)))
        session = self.session(manager)
        with mock.patch.object(session_module.time, "sleep") as sleep, \
             mock.patch.object(session, "_make_resources", wraps=session._make_resources) as make_owner:
            with self.assertRaises(BrowserLaunchError) as caught:
                session.start()
        make_owner.assert_called_once_with()
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertEqual(manager.start_calls, 3)
        self.assertEqual(manager.driver.stop_calls, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertTrue(session._resources.last_release_report.complete)
        self.assertIsInstance(session._resources, SyncSession)

    def test_driver_stop_failure_retries_only_retained_driver_and_redacts_report(self):
        context = NativeContext()
        manager = NativeManager(context)
        manager.driver.stop_outcomes = [RuntimeError(SECRET)]
        session = self.session(manager)
        session.start()
        owner = session._resources
        first = session.release()
        self.assertFalse(first["profileReleased"])
        self.assertFalse(first["playwrightStopped"])
        self.assertTrue(first["contextClosed"])
        self.assertEqual(first["sessionStatus"], "release_failed")
        self.assertNotIn(SECRET, json.dumps(first))
        self.assertIn("RuntimeError", json.dumps(first["warnings"]))
        with self.assertRaisesRegex(BrowserLaunchError, "release is incomplete"):
            session.start()
        self.assertIs(session._resources, owner)
        second = session.release()
        self.assertTrue(second["released"])
        self.assertTrue(second["profileReleased"])
        self.assertEqual(context.close_calls, 1)
        self.assertEqual(manager.driver.stop_calls, 2)
        self.assertEqual(manager.start_calls, 1)

    def test_native_page_inspection_failure_does_not_prevent_release(self):
        context = NativeContext()
        manager = NativeManager(context)
        session = self.session(manager)
        page = session.start()
        with mock.patch.object(page, "is_closed", side_effect=RuntimeError(SECRET)):
            released = session.release()
        self.assertTrue(released["released"])
        self.assertTrue(released["profileReleased"])
        self.assertTrue(released["contextClosed"])
        self.assertTrue(released["playwrightStopped"])
        self.assertIsNone(released["previousPageUrl"])
        self.assertNotIn(SECRET, json.dumps(released))
        self.assertEqual(context.close_calls, 1)
        self.assertEqual(manager.driver.stop_calls, 1)
        self.assertIsNone(session.page)
        self.assertIsNone(session.context)

    def test_browser_fallback_success_maps_complete_not_clean(self):
        context = NativeContext()
        context.close_outcomes = [RuntimeError(SECRET)]
        session = self.session(NativeManager(context))
        session.start()
        result = session.release()
        self.assertTrue(result["profileReleased"])
        self.assertTrue(result["released"])
        self.assertEqual(result["releaseMethod"], "browser.close-fallback")
        self.assertFalse(session._resources.last_release_report.clean)
        self.assertNotIn(SECRET, json.dumps(result))

    def test_native_context_invalidation_restarts_same_owner_with_new_generation(self):
        first_context = NativeContext()
        second_context = NativeContext()
        manager = NativeManager(first_context, second_context)
        session = self.session(manager)
        session.start()
        owner = session._resources
        business_close = mock.Mock()
        first_context.on("close", business_close)
        generation = owner.snapshot().generation
        first_context.invalidate()
        self.assertIsNone(session.page)
        self.assertIsNone(session.context)
        self.assertEqual(owner.snapshot().state, "invalidated")
        self.assertIs(session.start(), second_context.pages[0])
        self.assertIs(session._resources, owner)
        self.assertEqual(owner.snapshot().generation, generation + 1)
        self.assertEqual(manager.start_calls, 2)
        self.assertEqual(manager.driver.stop_calls, 1)
        self.assertIn(business_close, first_context.listeners["close"])
        business_close.assert_called_once()

    def test_cross_thread_access_and_release_fail_without_mutating_native_resources(self):
        context = NativeContext()
        manager = NativeManager(context)
        session = self.session(manager)
        main = session.start()
        errors = []

        def other_thread():
            for operation in (lambda: session.page, lambda: session.context, session.start, session.status, session.release):
                try:
                    operation()
                except BaseException as error:
                    errors.append(error)
                else:
                    errors.append(None)

        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 5)
        self.assertEqual(main.title_calls, 0)
        for error in errors:
            self.assertIsInstance(error, ExecutionContextError)
        self.assertIs(session.page, main)
        self.assertEqual(manager.start_calls, 1)
        self.assertEqual(context.close_calls, 0)
        self.assertEqual(manager.driver.stop_calls, 0)

    def test_wheel_hash_version_and_executed_owner_match_distributed_artifact(self):
        self.assertEqual(hashlib.sha256(WHEEL.read_bytes()).hexdigest(), WHEEL_SHA256)
        self.assertEqual(importlib.metadata.version("lijq-browser-common"), "0.1.0.dev2")
        package = Path(browser_common.__file__).resolve().parent
        with zipfile.ZipFile(WHEEL) as archive:
            for name in ("sync_session.py", "_core.py", "config.py", "results.py", "errors.py"):
                self.assertEqual((package / name).read_bytes(), archive.read("browser_common/" + name), name)
            guide = archive.read("browser_common/docs/ADAPTATION_GUIDE.md").decode("utf-8")
            self.assertIn("0.1.0.dev2", guide)


class BrowserOptionalDependencyContractTest(unittest.TestCase):
    """Verify product offline behavior independently of development dependencies."""

    def without_browser_dependencies(self, source, messages=()):
        bootstrap = textwrap.dedent("""
            import importlib.abc
            import sys
            from pathlib import Path

            attempts = []
            class BlockBrowserDependencies(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname.split('.')[0] in {'browser_common', 'playwright'}:
                        attempts.append(fullname)
                        raise ModuleNotFoundError('Blocked optional dependency: ' + fullname, name=fullname)
                    return None

            assert not any(n.split('.')[0] in {'browser_common', 'playwright'} for n in sys.modules)
            sys.meta_path.insert(0, BlockBrowserDependencies())
            profile = Path(sys.argv[1]) / 'never-created-profile'
        """)
        env = os.environ.copy()
        for name in ("LIVE_API_ENABLED", "PYTHONPATH", "PYTHONOPTIMIZE", "PYTHONHOME"):
            env.pop(name, None)
        env["PYTHONPATH"] = str(ROOT)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        with tempfile.TemporaryDirectory(prefix="onshape-no-browser-deps-") as temporary:
            process = subprocess.run(
                [sys.executable, "-S", "-c", bootstrap + textwrap.dedent(source), temporary],
                input="".join(json.dumps(item) + "\n" for item in messages),
                text=True, encoding="utf-8", capture_output=True, timeout=30,
                cwd=temporary, env=env,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stderr, "")
            self.assertFalse((Path(temporary) / "never-created-profile").exists())
        return process.stdout

    def test_facade_import_status_release_and_early_errors_with_both_dependencies_blocked(self):
        output = self.without_browser_dependencies("""
            import json
            from onshape_browser_mode.session import BrowserSession
            from onshape_browser_mode.settings import BrowserCfg, BrowserConfig, ListenerCfg, PacingCfg
            from onshape_browser_mode.errors import BrowserLaunchError, PlaywrightNotInstalled
            assert not attempts, attempts
            config = BrowserConfig(BrowserCfg(user_data_dir=str(profile)), PacingCfg(), ListenerCfg())
            session = BrowserSession(config)
            assert session._resources is None
            assert session.page is None and session.context is None
            assert session.profile_dir() == profile.resolve()
            status = session.status()
            assert status['playwrightInstalled'] is False
            assert status['sessionStatus'] == 'uninitialized'
            first = session.release()
            assert first['alreadyReleased'] and first['profileReleased'] and not first['released']
            assert session.release()['alreadyReleased']
            assert session._resources is None and not profile.exists()
            try:
                session.start()
            except PlaywrightNotInstalled as error:
                assert 'Playwright is not installed' in str(error)
            else:
                raise AssertionError('Missing Playwright did not fail before startup')
            assert session._resources is None and not profile.exists()

            def forbidden_factory():
                raise AssertionError('Native factory must never run without browser_common')

            injected = BrowserSession(config, playwright_factory=forbidden_factory)
            try:
                injected.start()
            except BrowserLaunchError as error:
                assert 'lijq-browser-common 0.1.0.dev2 is required' in str(error)
            else:
                raise AssertionError('Missing shared wheel did not fail before startup')
            assert injected._resources is None and not profile.exists()
            assert any(name.startswith('playwright') for name in attempts)
            assert 'browser_common' in attempts
            assert not any(n.split('.')[0] in {'browser_common', 'playwright'} for n in sys.modules)
            print(json.dumps({'offline': True, 'profileCreated': profile.exists()}))
        """)
        self.assertEqual(json.loads(output), {"offline": True, "profileCreated": False})

    def test_stdio_local_tools_and_eof_with_both_dependencies_blocked(self):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "no-browser-dependencies", "version": "1"},
            }},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        for index, (tool, action) in enumerate((
            ("browser_session", "status"), ("browser_session", "release"),
            ("browser_watch", "status"), ("browser_watch", "report"),
        ), start=3):
            messages.append({"jsonrpc": "2.0", "id": index, "method": "tools/call",
                             "params": {"name": tool, "arguments": {"action": action}}})
        output = self.without_browser_dependencies("""
            import runpy
            runpy.run_module('mcp_main.win.mcp', run_name='__main__')
            assert not any(n.split('.')[0] in {'browser_common', 'playwright'} for n in sys.modules)
            import onshape_browser_mode.session as module
            assert module._session is not None
            assert module._session._resources is None
        """, messages)
        responses = [json.loads(line) for line in output.splitlines()]
        self.assertEqual([item["id"] for item in responses], list(range(1, 7)))
        for item in responses:
            self.assertNotIn("error", item)
            self.assertFalse(item["result"].get("isError", False), item)
        self.assertFalse(responses[2]["result"]["structuredContent"]["playwrightInstalled"])
        released = responses[3]["result"]["structuredContent"]
        self.assertTrue(released["alreadyReleased"])
        self.assertTrue(released["profileReleased"])
        self.assertFalse(released["released"])


if __name__ == "__main__":
    unittest.main()
