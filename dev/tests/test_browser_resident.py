#!/usr/bin/env python3
"""Offline tests for resident browser mode.

Onshape's auth cookies are session cookies, so a browser death costs a human login.
Resident mode keeps one browser alive across MCP children and attaches to it over CDP
instead of launching and closing one per child.

Everything here is offline: the DevTools endpoint is a fake probe, the browser binary is
never executed, and the attach path is driven through fake Playwright objects. When the
pinned browser_common wheel is importable the real `SyncSession` release logic is also
exercised, because the adapter's whole job is to satisfy that logic: `context.close()`
must return normally (it detaches the CDP connection; measured to leave the browser and
its tabs alive) and `browser.close()` must never be reached.
"""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_browser_mode import resident, session as session_module, settings  # noqa: E402
from onshape_browser_mode.errors import BrowserLaunchError  # noqa: E402
from onshape_browser_mode.resident import (  # noqa: E402
    DEFAULT_RESIDENT_PORT,
    ResidentChromium,
    endpoint_url,
    resolve_executable,
    resident_playwright_factory,
    spawn_command,
    start_resident_browser,
    wait_for_endpoint,
)
from onshape_browser_mode.session import BrowserSession  # noqa: E402
from onshape_browser_mode.settings import BrowserCfg, BrowserConfig, ListenerCfg, PacingCfg  # noqa: E402

try:
    from browser_common import SyncSession as RealSyncSession
except ImportError:  # The wheel is optional outside the pinned integration environment.
    RealSyncSession = None

PROFILE = Path("C:/MCP/onshapescript/onshape_browser_mode/user_data/onshape_profile")
ENDPOINT = endpoint_url(DEFAULT_RESIDENT_PORT)
# A path that exists on every host, so spawn-path tests never depend on Edge.
EXECUTABLE = str(Path(sys.executable))


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakePage:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.context = None

    def is_closed(self):
        return False


class FakeContext:
    """The real context object: the adapter must hand this back untouched."""

    def __init__(self, pages=None) -> None:
        self.pages = list(pages if pages is not None else [FakePage()])
        for page in self.pages:
            page.context = self
        self.close_calls = 0
        self.listeners: dict[str, list] = {}
        self.browser = FakeBrowser(self)

    def on(self, event, callback):
        self.listeners.setdefault(event, []).append(callback)

    def remove_listener(self, event, callback):
        self.listeners.get(event, []).remove(callback)

    def new_page(self):
        page = FakePage()
        page.context = self
        self.pages.append(page)
        return page

    def close(self):
        self.close_calls += 1


class FakeBrowser:
    def __init__(self, context: FakeContext | None = None) -> None:
        self.contexts = [context] if context is not None else []
        self.close_calls = 0
        self.new_context_calls = 0

    def new_context(self):
        self.new_context_calls += 1
        context = FakeContext()
        self.contexts.append(context)
        return context

    def close(self):
        self.close_calls += 1


class FakeChromium:
    def __init__(self, context: FakeContext | None = None) -> None:
        self.context = context if context is not None else FakeContext()
        self.browser = FakeBrowser(self.context)
        self.connect_calls: list[str] = []
        self.launch_calls: list[dict] = []

    def connect_over_cdp(self, url, **kwargs):
        self.connect_calls.append(url)
        return self.browser

    def launch_persistent_context(self, *args, **kwargs):
        # Must never be reached: launching would put the browser under Playwright's
        # ownership, which is exactly what ends the session on this process's exit.
        self.launch_calls.append(kwargs)
        raise AssertionError("resident mode must attach, never launch")


def probe_hit(port: int, **kwargs):
    return {"reachable": True, "port": int(port), "url": endpoint_url(port), "browser": "Edg/153"}


def probe_miss(port: int, **kwargs):
    return {"reachable": False, "port": int(port), "url": endpoint_url(port), "error": "URLError"}


class SpawnRecorder:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command):
        self.commands.append(list(command))
        return {"pid": 4321, "command": list(command)}


class ResidentChromiumTest(unittest.TestCase):
    """The attach adapter: probe, spawn-if-absent, then attach and never own."""

    def chromium(self, *, reachable=True, **options):
        chromium = FakeChromium()
        spawn = SpawnRecorder()
        probe = probe_hit if reachable else probe_miss
        wait = mock.Mock(return_value=probe_hit(DEFAULT_RESIDENT_PORT))
        adapter = ResidentChromium(
            chromium,
            profile_dir=PROFILE,
            executable_path=EXECUTABLE,
            probe=probe,
            wait=wait,
            spawn=spawn,
            **options,
        )
        return adapter, chromium, spawn, wait

    def test_it_attaches_to_an_existing_browser_instead_of_launching(self):
        adapter, chromium, spawn, wait = self.chromium(reachable=True)
        context = adapter.launch_persistent_context(user_data_dir=str(PROFILE))

        self.assertEqual(chromium.connect_calls, [ENDPOINT])
        self.assertEqual(chromium.launch_calls, [])
        self.assertEqual(spawn.commands, [])
        wait.assert_not_called()
        # The browser's own context, unwrapped: browser_common asserts
        # `page.context is session.context` when it reconciles pages.
        self.assertIs(context, chromium.context)
        self.assertIs(context.pages[0].context, context)
        self.assertEqual(adapter.starts[0]["action"], "attached")
        self.assertTrue(adapter.starts[0]["alreadyRunning"])

    def test_it_spawns_one_detached_browser_when_nothing_answers(self):
        adapter, chromium, spawn, wait = self.chromium(
            reachable=False, proxy_server="http://127.0.0.1:10808", locale="zh-CN"
        )
        context = adapter.launch_persistent_context(
            user_data_dir=str(PROFILE), viewport={"width": 1280, "height": 800}
        )

        self.assertEqual(len(spawn.commands), 1)
        command = spawn.commands[0]
        self.assertIn(f"--user-data-dir={PROFILE}", command)
        self.assertIn(f"--remote-debugging-port={DEFAULT_RESIDENT_PORT}", command)
        self.assertIn("--remote-allow-origins=*", command)
        self.assertIn("--proxy-server=http://127.0.0.1:10808", command)
        self.assertIn("--lang=zh-CN", command)
        self.assertIn("--window-size=1280,800", command)
        self.assertEqual(chromium.connect_calls, [ENDPOINT])
        wait.assert_called_once()
        self.assertEqual(adapter.starts[0]["action"], "spawned")
        self.assertEqual(adapter.starts[0]["pid"], 4321)
        self.assertFalse(adapter.starts[0]["alreadyRunning"])
        self.assertIs(context, chromium.context)

    def test_a_browser_that_never_publishes_its_endpoint_is_a_clean_failure(self):
        chromium = FakeChromium()
        adapter = ResidentChromium(
            chromium,
            profile_dir=PROFILE,
            executable_path=EXECUTABLE,
            probe=probe_miss,
            wait=lambda port, **kwargs: probe_miss(port),
            spawn=SpawnRecorder(),
        )
        with self.assertRaises(BrowserLaunchError) as caught:
            adapter.launch_persistent_context()

        message = str(caught.exception)
        self.assertIn(ENDPOINT, message)
        self.assertIn(str(PROFILE), message)
        self.assertIn("login", message)  # names the real cost of a manual fix
        self.assertIn("--remote-debugging-port", message)
        self.assertEqual(chromium.connect_calls, [])
        self.assertEqual(adapter.starts, [])

    def test_a_browser_without_a_default_context_is_refused(self):
        chromium = FakeChromium()
        chromium.browser = FakeBrowser()
        adapter = ResidentChromium(chromium, profile_dir=PROFILE, probe=probe_hit)
        with self.assertRaises(BrowserLaunchError) as caught:
            adapter.launch_persistent_context()
        self.assertIn("no default context", str(caught.exception))
        self.assertEqual(chromium.browser.new_context_calls, 0)

    def test_the_attach_reports_what_it_could_not_apply(self):
        adapter, chromium, _spawn, _wait = self.chromium(reachable=True, locale="zh-CN")
        adapter.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
            timezone_id="Asia/Shanghai",
            viewport={"width": 1280, "height": 800},
        )
        record = adapter.starts[0]
        self.assertEqual(record["notApplied"], {"headless": False, "timezone_id": "Asia/Shanghai"})
        self.assertEqual(record["pages"], 1)
        self.assertIs(record["endpoint"]["reachable"], True)

    def test_it_prefers_the_option_profile_over_the_configured_one(self):
        adapter, _chromium, spawn, _wait = self.chromium(reachable=False)
        other = Path("C:/other/profile")
        adapter.launch_persistent_context(user_data_dir=str(other))
        self.assertIn(f"--user-data-dir={other}", spawn.commands[0])


class WindowSizeTest(unittest.TestCase):
    """The configured viewport becomes the spawn window size -- and is reported as such."""

    def launch(self, **viewport):
        spawn = SpawnRecorder()
        adapter = ResidentChromium(
            FakeChromium(),
            profile_dir=PROFILE,
            executable_path=EXECUTABLE,
            probe=probe_miss,
            spawn=spawn,
            wait=lambda port, **kwargs: probe_hit(port),
        )
        adapter.launch_persistent_context(**({"viewport": viewport} if viewport else {}))
        return adapter, spawn.commands[0]

    def test_a_configured_viewport_is_spawned_as_a_window_size(self):
        adapter, command = self.launch(width=1280, height=800)
        self.assertIn("--window-size=1280,800", command)
        self.assertEqual(command[-1], "about:blank")
        self.assertEqual(adapter.starts[0]["action"], "spawned")

    def test_an_absent_viewport_asks_for_no_window_size(self):
        _adapter, command = self.launch()
        self.assertEqual([a for a in command if a.startswith("--window-size")], [])


class ResidentOwnershipContractTest(unittest.TestCase):
    """Run the real wheel's release logic against the attach adapter."""

    def setUp(self):
        if RealSyncSession is None:
            self.skipTest("pinned lijq-browser-common wheel is not importable here")
        temporary = tempfile.TemporaryDirectory(prefix="onshape-resident-")
        self.addCleanup(temporary.cleanup)
        self.profile = Path(temporary.name) / "profile"

    def fake_playwright(self, chromium: FakeChromium):
        playwright = types.SimpleNamespace(chromium=chromium)
        manager = mock.MagicMock()  # __exit__ is the Playwright release hook
        manager.start.return_value = playwright
        sync_api = types.ModuleType("playwright.sync_api")
        sync_api.sync_playwright = lambda: manager
        package = types.ModuleType("playwright")
        package.sync_api = sync_api
        patcher = mock.patch.dict(
            sys.modules, {"playwright": package, "playwright.sync_api": sync_api}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return playwright, manager

    def test_release_detaches_without_closing_the_resident_browser(self):
        from browser_common import SessionConfig

        chromium = FakeChromium()
        _playwright, manager = self.fake_playwright(chromium)
        factory = resident_playwright_factory(
            profile_dir=self.profile, port=DEFAULT_RESIDENT_PORT, probe=probe_hit
        )
        owner = RealSyncSession(
            SessionConfig(self.profile, launch_options={"headless": False}),
            playwright_factory=factory,
        )
        self.addCleanup(owner.release)

        owner.start()
        self.assertEqual(chromium.connect_calls, [ENDPOINT])
        self.assertEqual(chromium.launch_calls, [])
        # Identity, not a look-alike: the wheel asserts it while reconciling pages.
        self.assertIs(owner.context, chromium.context)

        report = owner.release()
        self.assertTrue(report.complete)
        self.assertEqual(report.context_status, "closed")
        # The release calls context.close() exactly once -- that is the detach -- and
        # must never reach the browser.close() fallback, which would end the session.
        self.assertFalse(report.browser_fallback_used)
        self.assertEqual(report.failures, ())
        self.assertTrue(report.clean)
        self.assertEqual(chromium.context.close_calls, 1)
        self.assertEqual(chromium.browser.close_calls, 0)
        self.assertEqual(manager.__exit__.call_count, 1)  # Playwright itself is released


class PlaywrightFactoryTest(unittest.TestCase):
    def test_the_factory_hands_the_driver_a_resident_chromium_and_a_stop_hook(self):
        chromium = FakeChromium()
        playwright = types.SimpleNamespace(chromium=chromium)
        manager = mock.MagicMock()  # __exit__ is the Playwright release hook
        manager.start.return_value = playwright
        sync_api = types.ModuleType("playwright.sync_api")
        sync_api.sync_playwright = lambda: manager
        package = types.ModuleType("playwright")
        package.sync_api = sync_api
        with mock.patch.dict(sys.modules, {"playwright": package, "playwright.sync_api": sync_api}):
            build = resident_playwright_factory(profile_dir=PROFILE, probe=probe_hit)
            driver = build().start()
            self.assertIsInstance(driver.chromium, ResidentChromium)
            self.assertIs(driver.playwright, playwright)
            driver.stop()
        manager.__exit__.assert_called_once()
        # The manager is one-shot: a second stop must not release Playwright twice.
        driver.stop()
        manager.__exit__.assert_called_once()


class StartResidentBrowserTest(unittest.TestCase):
    """The spawn/report contract, with the binary substituted for this interpreter."""

    def test_it_spawns_nothing_when_the_endpoint_already_answers(self):
        spawn = SpawnRecorder()
        result = start_resident_browser(
            profile_dir=PROFILE, spawn=spawn, probe=probe_hit
        )
        self.assertTrue(result["alreadyRunning"])
        self.assertEqual(spawn.commands, [])

    def test_it_reports_a_real_spawn_with_its_command_and_pid(self):
        spawn = SpawnRecorder()
        result = start_resident_browser(
            profile_dir=PROFILE,
            channel="msedge",
            executable_path=EXECUTABLE,
            spawn=spawn,
            probe=probe_miss,
            wait=lambda port, **kwargs: probe_hit(port),
        )
        self.assertFalse(result["alreadyRunning"])
        self.assertEqual(result["pid"], 4321)
        self.assertEqual(result["command"], spawn.commands[0])

    def test_waiting_reports_how_long_it_waited_and_why_it_stopped(self):
        calls = {"count": 0}

        def flaky(port, **kwargs):
            calls["count"] += 1
            return probe_hit(port) if calls["count"] > 2 else probe_miss(port)

        status = wait_for_endpoint(9333, timeout_s=5, interval_s=0, probe=flaky)
        self.assertTrue(status["reachable"])
        self.assertEqual(calls["count"], 3)
        self.assertIn("waitedMs", status)

    def test_an_unreachable_port_is_reported_not_raised(self):
        status = resident.probe_endpoint(9, timeout_s=0.05)
        self.assertFalse(status["reachable"])
        self.assertIn("error", status)

    def test_the_probe_opener_cannot_use_a_system_proxy(self):
        """The deployment host has a system proxy; the loopback endpoint must bypass it."""
        import urllib.request

        opener = resident._direct_opener()
        # An empty ProxyHandler installs no `*_open` method, so it never enters the
        # handler chain: nothing can route this request through the host's proxy. That
        # is also why asserting the absence of the handler (not of the handler object)
        # is the honest check.
        self.assertEqual(
            [h for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)], []
        )
        self.assertFalse(hasattr(opener, "proxy_open"))
        self.assertIs(resident._direct_opener(), opener)

    def test_the_probe_reads_through_that_opener(self):
        calls = []

        class Opener:
            def open(self, url, timeout=None):
                calls.append((url, timeout))
                return FakeResponse(b'{"Browser": "Edg/153", "Protocol-Version": "1.3"}')

        with mock.patch.object(resident, "_OPENER", Opener()):
            status = resident.probe_endpoint(DEFAULT_RESIDENT_PORT)
        self.assertTrue(status["reachable"])
        self.assertEqual(status["browser"], "Edg/153")
        self.assertEqual(calls, [(ENDPOINT, resident.PROBE_TIMEOUT_S)])

    def test_the_probe_budget_exceeds_the_measured_refusal_delay(self):
        """A closed loopback port refuses only after ~2.0 s on this host (measured)."""
        self.assertGreater(resident.PROBE_TIMEOUT_S, 2.1)


class ExecutableResolutionTest(unittest.TestCase):
    def test_a_configured_path_wins_and_is_validated(self):
        with self.assertRaises(BrowserLaunchError):
            resolve_executable(executable_path="C:/definitely/missing/msedge.exe")

    def test_a_channel_without_a_known_binary_is_explained(self):
        with self.assertRaises(BrowserLaunchError) as caught:
            resolve_executable(channel="")
        self.assertIn("browser.executable_path", str(caught.exception))

    def test_the_spawn_command_is_exact_and_reproducible(self):
        command = spawn_command(
            executable="msedge.exe", profile_dir=PROFILE, port=9444
        )
        self.assertEqual(
            command,
            [
                "msedge.exe",
                f"--user-data-dir={PROFILE}",
                "--remote-debugging-port=9444",
                "--remote-allow-origins=*",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ],
        )


class ResidentWiringTest(unittest.TestCase):
    """Default ON (owner decision 2026-09-26); the switch is a config value."""

    def session(self, **options):
        options.setdefault("user_data_dir", str(PROFILE))
        config = BrowserConfig(BrowserCfg(**options), PacingCfg(), ListenerCfg())
        return BrowserSession(config)

    def test_resident_mode_is_on_by_default(self):
        # The shipped browser.toml and this dataclass default must agree, because a
        # deployment that reads either one has to get the same ownership model.
        self.assertTrue(BrowserCfg().resident)
        self.assertEqual(BrowserCfg().resident_port, DEFAULT_RESIDENT_PORT)
        self.assertIsNotNone(self.session()._make_resources()._factory)

    def test_an_explicit_false_still_opts_out(self):
        """The default decides for an unconfigured host, not against a configured one."""
        self.assertFalse(BrowserCfg(resident=False).resident)
        self.assertIsNone(self.session(resident=False)._make_resources()._factory)

    def test_the_switch_injects_only_the_spawn_time_identity(self):
        browser = self.session(resident=True, resident_port=9444, channel="msedge", locale="zh-CN")
        with mock.patch.object(
            session_module, "resident_playwright_factory", wraps=session_module.resident_playwright_factory
        ) as factory:
            resources = browser._make_resources()
        self.assertIsNotNone(resources._factory)
        kwargs = factory.call_args.kwargs
        self.assertEqual(kwargs["port"], 9444)
        self.assertEqual(kwargs["channel"], "msedge")
        self.assertEqual(kwargs["locale"], "zh-CN")
        # Per-page options belong to `launch_options` and reach the adapter through the
        # wheel's `launch_kwargs()`; duplicating them here is a TypeError, not a config.
        self.assertNotIn("viewport", kwargs)
        self.assertEqual(
            resources.config.launch_kwargs()["viewport"], {"width": 1280, "height": 800}
        )

    def test_the_adapter_accepts_exactly_the_options_the_switch_sends(self):
        """A wiring mismatch must fail here, not as a TypeError during start()."""
        browser = self.session(resident=True, resident_port=9444, channel="msedge")
        with mock.patch.object(
            session_module, "resident_playwright_factory", wraps=session_module.resident_playwright_factory
        ) as factory:
            resources = browser._make_resources()
        options = dict(factory.call_args.kwargs)
        ResidentChromium(FakeChromium(), **options)  # must not raise

    def test_an_injected_factory_still_wins_over_resident_mode(self):
        config = BrowserConfig(BrowserCfg(resident=True), PacingCfg(), ListenerCfg())
        injected = lambda: None  # noqa: E731 - the identity is the point
        resources = BrowserSession(config, playwright_factory=injected)._make_resources()
        self.assertIs(resources._factory, injected)

    def test_the_local_config_file_can_override_it(self):
        with tempfile.TemporaryDirectory(prefix="onshape-resident-config-") as temporary:
            local = Path(temporary) / "browser.local.toml"
            local.write_text(
                '[browser]\nresident = false\nresident_port = 9444\nchannel = "msedge"\n',
                encoding="utf-8",
            )
            with mock.patch.object(settings, "LOCAL_CONFIG_PATH", local):
                config = settings.load_browser_config(ROOT / "onshape_browser_mode/config/browser.toml")
        self.assertFalse(config.browser.resident)
        self.assertEqual(config.browser.resident_port, 9444)
        self.assertEqual(config.browser.channel, "msedge")

    def test_the_shipped_config_enables_it(self):
        """The artifact's own browser.toml must carry the ON default, not just the code."""
        config = settings.load_browser_config(ROOT / "onshape_browser_mode/config/browser.toml")
        self.assertTrue(config.browser.resident)


if __name__ == "__main__":
    unittest.main()
