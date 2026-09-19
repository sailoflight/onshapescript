"""Offline smoke-runner control flow using real BrowserSession/SyncSession.

PYTHONPATH=temp/browser-common-site python3 -m unittest dev.tests.test_browser_common_smoke -v
Only native resources come from the existing integration fakes. No browser starts.
"""
from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import gc
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from dev.tests.test_browser_common_integration import (
    NativeContext, NativeManager, NativePage, SECRET,
)
from dev.tools import browser_common_smoke as smoke
from onshape_browser_mode.session import BrowserSession
from onshape_browser_mode.settings import BrowserCfg, BrowserConfig, ListenerCfg, PacingCfg


class LocalLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    def fill(self, text):
        self.page.input_text = text

    def click(self):
        self.page.result_text = self.page.input_text

    def text_content(self):
        return self.page.result_text


class LocalPage(NativePage):
    def set_content(self, html, **kwargs):
        if html != smoke.HTML or self.url != "about:blank":
            raise AssertionError("Only fixed local HTML allowed")
        self.input_text = self.result_text = ""

    def locator(self, selector):
        return LocalLocator(self, selector)


class LocalContext(NativeContext):
    def __init__(self):
        super().__init__(())
        self.pages = [LocalPage(self)]
        self.browser.version = "fake-native-version"
        self.routes = []

    def new_page(self):
        self.new_page_calls += 1
        page = LocalPage(self)
        self.pages.append(page)
        self.emit("page", page)
        return page

    def set_default_timeout(self, milliseconds):
        self.timeout = milliseconds

    def route(self, pattern, handler):
        self.routes.append((pattern, handler))


class BrowserCommonSmokeTest(unittest.TestCase):
    def setUp(self):
        self.contexts = [LocalContext() for _ in range(3)]
        self.manager = NativeManager(*self.contexts)
        self.sessions = []
        self.temporary_dirs = []
        stack = self.enterContext(ExitStack())
        existing = BrowserConfig(BrowserCfg(
            channel="msedge", user_data_dir="production-profile-must-not-be-used",
            proxy_server=SECRET, headless=True,
        ), PacingCfg(), ListenerCfg())
        stack.enter_context(mock.patch("onshape_browser_mode.settings.load_browser_config", return_value=existing))
        stack.enter_context(mock.patch.object(smoke, "native_types", return_value=(LocalPage, LocalContext, LocalLocator)))
        stack.enter_context(mock.patch.object(BrowserSession, "playwright_available", side_effect=AssertionError("Real browser forbidden")))
        # These methods must never read or write production application state.
        stack.enter_context(mock.patch.object(BrowserSession, "_load_saved_app_url", side_effect=AssertionError("State read forbidden")))
        stack.enter_context(mock.patch.object(BrowserSession, "_save_app_url", side_effect=AssertionError("State write forbidden")))

        def factory(config):
            session = BrowserSession(config, playwright_factory=lambda: self.manager)
            self.sessions.append(session)
            return session

        stack.enter_context(mock.patch("onshape_browser_mode.session.BrowserSession", side_effect=factory))
        native_temporary = tempfile.TemporaryDirectory

        def temporary_factory(**kwargs):
            self.assertFalse(kwargs["delete"])
            directory = native_temporary(dir=smoke.ROOT / "temp", **kwargs)
            self.temporary_dirs.append(directory)
            return directory

        stack.enter_context(mock.patch.object(smoke.tempfile, "TemporaryDirectory", side_effect=temporary_factory))
        self.addCleanup(self.cleanup_fakes)

    def cleanup_fakes(self):
        # Test-owned fakes only: clear injected failures, release, then remove.
        for context in self.contexts:
            context.close_outcomes.clear()
            context.browser.close_outcomes.clear()
        self.manager.driver.stop_outcomes.clear()
        for session in self.sessions:
            self.assertTrue(session.release()["profileReleased"])
        for directory in self.temporary_dirs:
            directory.cleanup()

    def test_default_plan_has_no_session_dependencies_config_or_profile(self):
        with mock.patch.object(smoke, "make_session", side_effect=AssertionError), mock.patch.object(smoke, "versions", side_effect=AssertionError):
            report = smoke.run_smoke()
        self.assertEqual(report["status"], "planned")
        self.assertTrue(all(item["passed"] is None for item in report["checks"]))
        self.assertFalse(self.sessions or self.temporary_dirs)
        self.assertEqual(self.manager.start_calls, 0)

    def test_confirmation_cannot_be_abbreviated(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            smoke.main(["--confirm-b"])
        self.assertEqual(caught.exception.code, 2)
        self.assertFalse(self.sessions or self.temporary_dirs)

    def test_startup_failure_still_releases_and_removes_isolated_profile(self):
        self.manager.driver.launch_outcomes = [RuntimeError(SECRET) for _ in range(3)]
        with mock.patch("onshape_browser_mode.session.time.sleep"):
            report = smoke.run_smoke(confirm_browser=True)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["error_type"], "BrowserLaunchError")
        self.assertTrue(report["releases"][-1]["complete"])
        self.assertTrue(report["profile_cleanup"]["complete"])
        self.assertFalse(Path(self.temporary_dirs[0].name).exists())
        self.assertNotIn(SECRET, json.dumps(report))

    def test_success_exercises_real_owners_and_complete_cleanup(self):
        report = smoke.run_smoke(confirm_browser=True)
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(tuple(item["name"] for item in report["checks"]), smoke.CHECKS)
        self.assertTrue(all(item["passed"] for item in report["checks"]))
        self.assertTrue(all(item["complete"] for item in report["scope_cleanup"]))
        self.assertEqual(len(report["scope_cleanup"]), 3)
        self.assertTrue(all(item["complete"] for item in report["releases"]))
        self.assertEqual(len(self.sessions), 1)
        self.assertEqual(self.manager.start_calls, 3)
        self.assertEqual(self.manager.driver.stop_calls, 3)
        self.assertEqual(len(self.manager.driver.launch_calls), 3)
        for launch in self.manager.driver.launch_calls:
            self.assertEqual(launch["channel"], "msedge")
            self.assertFalse(launch["headless"])
            self.assertNotIn("proxy", launch)
            self.assertEqual(Path(launch["user_data_dir"]), Path(self.temporary_dirs[0].name) / "profile")
        for context in self.contexts:
            self.assertEqual(context.routes[0][0], "**/*")
            route = mock.Mock()
            context.routes[0][1](route)
            route.abort.assert_called_once_with()
        self.assertTrue(report["profile_cleanup"]["complete"])
        self.assertFalse(Path(self.temporary_dirs[0].name).exists())
        serialized = json.dumps(report)
        self.assertNotIn(SECRET, serialized)
        self.assertNotIn("production-profile", serialized)
        self.assertNotIn("previousPageUrl", serialized)
        self.assertNotIn("profileDir", serialized)

    def test_nullable_context_browser_does_not_fail_acceptance(self):
        with mock.patch.object(self.contexts[0], "browser", None):
            report = smoke.run_smoke(confirm_browser=True)
        self.assertEqual(report["status"], "passed", report)
        self.assertIsNone(report["versions"]["browser"])
        self.assertNotIn("browser_error_type", report["versions"])
        self.assertTrue(all(item["complete"] for item in report["releases"]))
        self.assertTrue(report["profile_cleanup"]["complete"])

    def test_optional_browser_version_failure_is_redacted_and_nonfatal(self):
        browser_type = type(self.contexts[0].browser)
        with mock.patch.object(browser_type, "version", new_callable=mock.PropertyMock,
                               create=True, side_effect=RuntimeError(SECRET)):
            report = smoke.run_smoke(confirm_browser=True)
        self.assertEqual(report["status"], "passed", report)
        self.assertIsNone(report["versions"]["browser"])
        self.assertEqual(report["versions"]["browser_error_type"], "RuntimeError")
        self.assertTrue(all(item["complete"] for item in report["releases"]))
        self.assertTrue(report["profile_cleanup"]["complete"])
        self.assertNotIn(SECRET, json.dumps(report))

    def test_config_preserves_executable_priority_and_headless_opt_in(self):
        existing = BrowserConfig(BrowserCfg(channel="msedge", executable_path="C:/Existing Edge/msedge.exe"), PacingCfg(), ListenerCfg())
        with mock.patch("onshape_browser_mode.settings.load_browser_config", return_value=existing):
            report = smoke.run_smoke(confirm_browser=True, headless=True)
        self.assertEqual(report["status"], "passed", report)
        self.assertFalse(report["headed"])
        for launch in self.manager.driver.launch_calls:
            self.assertEqual(launch["executable_path"], existing.browser.executable_path)
            self.assertNotIn("channel", launch)
            self.assertTrue(launch["headless"])

    def test_failure_releases_before_profile_cleanup_and_redacts_exception(self):
        def fail_fill(*args):
            raise RuntimeError(SECRET)

        with mock.patch.object(LocalLocator, "fill", fail_fill):
            report = smoke.run_smoke(confirm_browser=True)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["error_type"], "RuntimeError")
        self.assertEqual(report["checks"][-1]["name"], "native_locator")
        self.assertTrue(report["releases"][-1]["complete"])
        self.assertEqual(self.manager.driver.stop_calls, 1)
        self.assertFalse(Path(self.temporary_dirs[0].name).exists())
        self.assertNotIn(SECRET, json.dumps(report))

    def test_incomplete_release_preserves_profile_after_gc(self):
        self.contexts[0].close_outcomes = [RuntimeError(SECRET)]
        self.contexts[0].browser.close_outcomes = [RuntimeError(SECRET)]
        with mock.patch.object(LocalLocator, "fill", side_effect=RuntimeError(SECRET)):
            report = smoke.run_smoke(confirm_browser=True)
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["profile_cleanup"]["complete"])
        self.assertFalse(report["releases"][-1]["complete"])
        retained = Path(report["profile_cleanup"]["retained_directory"])
        self.temporary_dirs.clear()  # exercise real TemporaryDirectory GC policy
        gc.collect()
        self.assertTrue(retained.is_dir())
        self.assertEqual(self.manager.driver.stop_calls, 0)
        self.assertNotIn(SECRET, json.dumps(report))
        # The fake owner is recoverable; deletion only follows its successful retry.
        self.assertTrue(self.sessions[0].release()["profileReleased"])
        import shutil
        shutil.rmtree(retained)

    def test_release_exception_preserves_profile(self):
        with mock.patch.object(smoke, "exercise", side_effect=KeyboardInterrupt(SECRET)), mock.patch.object(BrowserSession, "release", side_effect=RuntimeError(SECRET)):
            report = smoke.run_smoke(confirm_browser=True)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["error_type"], "KeyboardInterrupt")
        self.assertEqual(report["cleanup_error_type"], "RuntimeError")
        self.assertTrue(Path(report["profile_cleanup"]["retained_directory"]).is_dir())
        self.assertNotIn(SECRET, json.dumps(report))

    def test_scope_cleanup_failure_cannot_pass_even_if_release_succeeds(self):
        def failing_scope(session, report):
            session.start()
            with smoke.scope_check(session, report, "injected_failure") as scope:
                page = scope.track(session.context.new_page())
                page.close_outcomes = [RuntimeError(SECRET)]

        with mock.patch.object(smoke, "exercise", failing_scope):
            report = smoke.run_smoke(confirm_browser=True)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["error_type"], "PageCleanupError")
        self.assertFalse(report["scope_cleanup"][0]["complete"])
        self.assertTrue(report["releases"][-1]["complete"])
        self.assertTrue(report["profile_cleanup"]["complete"])
        self.assertNotIn(SECRET, json.dumps(report))

    def test_profile_cleanup_failure_cannot_pass(self):
        original_cleanup = tempfile.TemporaryDirectory  # already patched factory
        # Inject only the directory cleanup method, not its constructor.
        def factory(**kwargs):
            directory = original_cleanup(**kwargs)
            self.addCleanup(directory.cleanup)
            directory.cleanup = mock.Mock(side_effect=PermissionError(SECRET))
            return directory

        with mock.patch.object(smoke.tempfile, "TemporaryDirectory", side_effect=factory):
            report = smoke.run_smoke(confirm_browser=True)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["profile_cleanup"]["error_type"], "PermissionError")
        self.assertTrue(report["releases"][-1]["complete"])
        self.assertNotIn(SECRET, json.dumps(report))
        # Restore explicit cleanup for the test's own teardown.
        for directory in self.temporary_dirs:
            del directory.cleanup

    def test_cli_output_and_write_failure_are_sanitized(self):
        output = smoke.ROOT / "temp" / "browser-common-smoke-test-plan.json"
        self.addCleanup(output.unlink, missing_ok=True)
        with redirect_stdout(io.StringIO()):
            code = smoke.main(["--output", str(output)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.read_text())["status"], "planned")
        with mock.patch.object(Path, "write_text", side_effect=OSError(SECRET)), redirect_stdout(io.StringIO()) as stdout:
            code = smoke.main(["--output", str(output)])
        report = json.loads(stdout.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(report["output_error_type"], "OSError")
        self.assertNotIn(SECRET, stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
