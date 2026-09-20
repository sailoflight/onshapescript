"""Onshape business facade over a lazily imported browser_common resource owner.

The shared library owns native Playwright resources; login, recovery selection,
configuration and MCP response contracts remain here. Offline tools need neither
Playwright nor browser_common installed.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from onshape_browser_mode.settings import BrowserConfig, load_browser_config
from onshape_browser_mode.errors import BrowserLaunchError, PlaywrightNotInstalled
from onshape_browser_mode.resident import resident_playwright_factory

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
_SIGNIN_URL = "https://cad.onshape.com/signin"


def _is_onshape_app_url(url: str | None) -> bool:
    """Preserve the existing business heuristic for restored application URLs."""
    if not url:
        return False
    lowered = url.lower()
    if "about:blank" in lowered or "cad.onshape.com" not in lowered:
        return False
    return "/signin" not in lowered and "login.onshape.com" not in lowered


def _browser_launch_error_message(
    *, channel: str, profile_dir: Path, error: Exception | None
) -> str:
    return (
        f"Could not launch browser (channel={channel!r}): {error}. "
        f"The persistent profile is {profile_dir}. Another MCP/browser process may own "
        "this profile. The owning connection should call "
        "browser_session(action='release') after its browser work; this MCP process "
        "cannot release another process's browser. A bridge registration with "
        "multiProcessAllowed=false must reuse or serialize one business-MCP child "
        "instead of spawning concurrent profile owners. Do not delete profile lock "
        "files. If no other owner exists, verify channel/executable_path in "
        "onshape_browser_mode/config/browser.local.toml and follow "
        "docs/operations/MCP_RUNBOOK.md."
    )


class BrowserSession:
    """Business session composed with one SyncSession, with no native handle copies."""

    def __init__(self, config: BrowserConfig | None = None, *, playwright_factory: Any = None) -> None:
        self.config = config or load_browser_config()
        self._resources: Any = None
        self._playwright_factory = playwright_factory
        # Business recovery is suspended during a temporary-page workflow.
        # Page registrations and all resource handles remain solely in the owner.
        self._temporary_depth = 0
        self._status = "uninitialized"
        self.human_action_required = False
        self.login_confirmed = False

    def _resource(self, name: str):
        if self._resources is None:
            return None
        from browser_common import ResourceUnavailableError
        try:
            return getattr(self._resources, name)
        except ResourceUnavailableError:
            return None

    @property
    def context(self):
        """The owner's native context, or None when unavailable."""
        return self._resource("context")

    @property
    def page(self):
        """The owner's native working page, or None when unavailable."""
        return self._resource("page")

    def adopt_page(self, page: Any):
        """Explicitly transfer the working page to the shared resource owner."""
        if self._resources is None:
            raise BrowserLaunchError("Start the browser before adopting a page.")
        return self._resources.adopt_page(page)

    @contextmanager
    def temporary_pages(self, *, budget_ms: float | None = None):
        """Track native pages and suspend implicit business page recovery."""
        if self._resources is None:
            raise BrowserLaunchError("Start the browser before tracking temporary pages.")
        with self._resources.temporary_pages(budget_ms=budget_ms) as scope:
            self._temporary_depth += 1
            try:
                yield scope
            finally:
                self._temporary_depth -= 1

    def _make_resources(self):
        try:
            from browser_common import SessionConfig, SyncSession
        except ImportError as exc:
            raise BrowserLaunchError(
                "lijq-browser-common 0.1.0.dev2 is required on the MCP browser host. "
                "Install onshape_browser_mode/requirements-windows.txt with its bundled wheels."
            ) from exc
        browser_cfg = self.config.browser
        options: dict[str, Any] = {
            "headless": browser_cfg.headless,
            "locale": browser_cfg.locale,
            "timezone_id": browser_cfg.timezone,
            "viewport": {"width": 1280, "height": 800},
        }
        if browser_cfg.executable_path:
            options["executable_path"] = browser_cfg.executable_path
        elif browser_cfg.channel:
            options["channel"] = browser_cfg.channel
        if browser_cfg.proxy_server:
            options["proxy"] = {"server": browser_cfg.proxy_server}
        factory = self._playwright_factory
        if factory is None and browser_cfg.resident:
            # Resident mode: attach to one long-lived browser instead of launching one, so
            # the Onshape login (session cookies only) survives this child's exit. Default
            # off, and an explicitly injected factory always wins.
            factory = resident_playwright_factory(
                profile_dir=self.profile_dir(),
                port=browser_cfg.resident_port,
                channel=browser_cfg.channel,
                executable_path=browser_cfg.executable_path,
                proxy_server=browser_cfg.proxy_server,
                locale=browser_cfg.locale,
                viewport=options["viewport"],
            )
        return SyncSession(
            SessionConfig(
                self.profile_dir(), launch_options=options,
                # Onshape's legacy app predicate stays in the business facade.
                cleanup_restored=False, browser_close_fallback=True,
            ),
            playwright_factory=factory,
        )

    @staticmethod
    def playwright_available() -> bool:
        """Check import availability without launching a browser."""
        try:
            import playwright.sync_api  # noqa: F401
            return True
        except Exception:
            return False

    def profile_dir(self) -> Path:
        raw = Path(self.config.browser.user_data_dir).expanduser()
        if raw.is_absolute():
            return raw.resolve()
        return (PACKAGE_ROOT / raw).resolve()

    @staticmethod
    def _state_path() -> Path:
        return PACKAGE_ROOT / "config" / "browser-state.json"

    def _load_saved_app_url(self) -> str | None:
        try:
            data = json.loads(self._state_path().read_text(encoding="utf-8"))
            url = data.get("lastAppUrl")
            return url if isinstance(url, str) and url else None
        except Exception:
            return None

    def _save_app_url(self, url: str) -> None:
        try:
            path = self._state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"lastAppUrl": url}, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _enforce_single_working_page(self, keep_page: Any) -> None:
        """Reconcile the explicit tool-boundary snapshot, protecting active scopes."""
        context = self.context
        if context is None:
            return
        from browser_common import PageCleanupError
        if keep_page is not self.page:
            self.adopt_page(keep_page)
        report = self._resources.reconcile_pages(list(context.pages or []))
        if not report.complete:
            raise PageCleanupError(report)

    def _prepare_page(self, page: Any):
        self.adopt_page(page)
        self._enforce_single_working_page(page)
        try:
            page.bring_to_front()
        except Exception:
            pass
        if _is_onshape_app_url(page.url):
            self.login_confirmed = True
            self.human_action_required = False
        self._status = "started"
        return page

    def start(self):
        """Explicit business recovery followed by native resource startup/reuse."""
        if self._resources is not None:
            state = self._resources.snapshot().state
            if self._temporary_depth:
                current = self.page
                if current is None:
                    raise BrowserLaunchError(
                        "Working page unavailable during a temporary workflow; "
                        "explicitly adopt a live page or exit the scope before recovery."
                    )
                return self._prepare_page(current)
            if state == "release_failed":
                raise BrowserLaunchError(
                    "Browser release is incomplete; call browser_session(action='release') "
                    "before starting again."
                )
            if state == "invalidated":
                if not self.close()["profileReleased"]:
                    raise BrowserLaunchError("Invalidated browser resources could not be released.")

        context = self.context
        if context is not None:
            pages = list(context.pages or [])
            current = self.page
            # Reuse the current app page first. Do not replace it with a temporary
            # app popup merely because that popup occurs earlier in context.pages.
            ordered = ([current] if current is not None else []) + [p for p in pages if p is not current]
            live_pages = []
            for page in ordered:
                try:
                    if not page.is_closed():
                        live_pages.append(page)
                except Exception:
                    continue
            preferred = []
            for candidate in live_pages:
                try:
                    if _is_onshape_app_url(candidate.url):
                        preferred.append(candidate)
                except Exception:
                    continue
            candidates = preferred + [
                p for p in live_pages if all(p is not preferred_page for preferred_page in preferred)
            ]
            for page in candidates:
                try:
                    page.evaluate("1 + 1")
                except Exception:
                    continue
                return self._prepare_page(page)
            # A navigation-time evaluate error does not establish resource death.
            if candidates:
                return self._prepare_page(candidates[0])
            try:
                page = context.new_page()
            except Exception:
                if not self.close()["profileReleased"]:
                    raise BrowserLaunchError("Unreachable browser resources could not be released.")
            else:
                return self._prepare_page(page)

        if self._playwright_factory is None and not self.playwright_available():
            raise PlaywrightNotInstalled(
                "Playwright is not installed on the MCP browser host. Run: "
                "C:\\path\\to\\onshapescript\\.venv\\Scripts\\python.exe -m pip install "
                "-r onshape_browser_mode\\requirements-windows.txt"
            )
        if self._resources is None:
            self._resources = self._make_resources()
        profile = self.profile_dir()
        profile.mkdir(parents=True, exist_ok=True)
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                page = self._resources.start()
                break
            except Exception as exc:
                last_exc = exc
                report = self._resources.last_release_report
                if report is None or not report.complete:
                    self._status = "release_failed"
                    break
                self._status = "start_failed"
                if attempt < 2:
                    time.sleep(2.0)
        else:
            page = None
        if self._resources.snapshot().state != "ready":
            raise BrowserLaunchError(
                _browser_launch_error_message(
                    channel=self.config.browser.channel, profile_dir=profile,
                    error=RuntimeError(type(last_exc).__name__),
                )
            ) from last_exc
        # Keep legacy business preference; shared selection only supplies a live
        # fallback, and never embeds site-specific matching in the common library.
        for restored in list(self.context.pages or []):
            try:
                if not restored.is_closed() and _is_onshape_app_url(restored.url):
                    page = restored
                    break
            except Exception:
                continue
        return self._prepare_page(page)

    def release(self) -> dict[str, Any]:
        """Release this process's browser/profile ownership without starting it."""
        return self.close()

    def close(self) -> dict[str, Any]:
        previous_status = self._status
        try:
            page = self.page
            previous_page_url = page.url if page is not None else None
        except Exception:
            # Diagnostic page inspection must not prevent resource release.
            # The owner's release() still enforces the execution-thread guard.
            previous_page_url = None
        report = self._resources.release() if self._resources is not None else None
        context_status = report.context_status if report else "absent"
        driver_status = report.driver_status if report else "absent"
        had_resources = context_status != "absent" or driver_status != "absent"
        context_closed = context_status in ("absent", "closed")
        playwright_stopped = driver_status in ("absent", "stopped")
        profile_released = report.complete if report else True
        self._status = "closed" if profile_released else "release_failed"
        if profile_released:
            self.login_confirmed = False
            self.human_action_required = False
        release_method = "none"
        if context_status == "closed":
            release_method = "browser.close-fallback" if report.browser_fallback_used else "context.close"
        warnings = [f"{f.operation} failed: {f.error_type}" for f in report.failures] if report else []
        return {
            "released": had_resources and profile_released,
            "alreadyReleased": not had_resources and previous_status != "release_failed",
            "profileReleased": profile_released,
            "previousSessionStatus": previous_status,
            "previousPageUrl": previous_page_url,
            "sessionStatus": self._status,
            "profileDir": str(self.profile_dir()),
            "contextClosed": context_closed,
            "playwrightStopped": playwright_stopped,
            "releaseMethod": release_method,
            "loginStateMayNeedRefresh": had_resources,
            "warnings": warnings,
            "message": (
                "Browser/profile ownership released for this MCP process."
                if profile_released
                else "Browser/profile release could not be verified; request Operator recovery."
            ),
        }

    def status(self) -> dict[str, Any]:
        # Observe useful business state without transferring a temporary page's
        # ownership as a side effect of a status request.
        page_url = None
        pages_seen: list[dict[str, Any]] = []
        context = self.context
        current = self.page
        refreshed = False
        if context is not None:
            from browser_common import ExecutionContextError
            try:
                probe = current
                if probe is None:
                    probe = next((p for p in context.pages if not p.is_closed()), None)
                if probe is not None:
                    # Sync Playwright URL/pages/closed properties only read caches.
                    # One native read pumps pending manual-navigation events.
                    probe.title()
                    refreshed = True
            except ExecutionContextError:
                raise
            except Exception:
                # Navigation may destroy the execution context mid-read. This
                # establishes neither logout nor resource death; never recover here.
                pass
            context = self.context
            current = self.page
        if context is not None:
            for page in list(context.pages or []):
                try:
                    if page.is_closed():
                        pages_seen.append({"closed": True})
                        continue
                    url = page.url
                except Exception:
                    pages_seen.append({"closed": True})
                    continue
                pages_seen.append({"url": url})
                if _is_onshape_app_url(url):
                    page_url = url
                    break
                if page_url is None and page is current:
                    page_url = url
        if page_url is None and current is not None:
            try:
                page_url = current.url
            except Exception:
                pass
        if refreshed:
            if _is_onshape_app_url(page_url):
                self.login_confirmed = True
                self.human_action_required = False
                if self._status == "awaiting_login":
                    self._status = "started"
                self._save_app_url(page_url)
            elif (page_url or "").split("?", 1)[0].split("#", 1)[0].rstrip("/") == _SIGNIN_URL:
                # A successfully refreshed sign-in page supersedes sticky login
                # history. Unknown URLs and failed reads do not prove logout.
                self.login_confirmed = False
                self.human_action_required = True
                if self._status == "started":
                    self._status = "awaiting_login"
        return {
            "playwrightInstalled": self.playwright_available(),
            "configured": True,
            "profileDir": str(self.profile_dir()),
            "sessionStatus": self._status,
            "pageUrl": page_url,
            "pages": pages_seen,
            "headless": self.config.browser.headless,
            "humanActionRequired": self.human_action_required,
            "loginConfirmed": self.login_confirmed,
        }

    def open_login_page(self) -> dict[str, Any]:
        """Open sign-in only when restored/saved app entry cannot reuse login."""
        page = self.start()
        self._enforce_single_working_page(page)
        try:
            current_url = page.url
        except Exception:
            current_url = None
        if _is_onshape_app_url(current_url):
            self._status = "started"
            self.human_action_required = False
            self.login_confirmed = True
            self._save_app_url(current_url)
            return {
                "sessionStatus": self._status,
                "message": (
                    "Browser session is already logged in (restored Onshape "
                    "page was kept). No sign-in navigation was needed."
                ),
            }
        saved_url = self._load_saved_app_url()
        if saved_url:
            try:
                page.goto(saved_url, wait_until="domcontentloaded", timeout=60_000)
                try:
                    page.wait_for_timeout(4000)
                except Exception:
                    pass
                if _is_onshape_app_url(page.url):
                    self._status = "started"
                    self.human_action_required = False
                    self.login_confirmed = True
                    self._save_app_url(page.url)
                    return {
                        "sessionStatus": self._status,
                        "message": f"Logged in via saved Onshape entry URL ({page.url}).",
                    }
            except Exception:
                pass
        page.goto(_SIGNIN_URL, wait_until="domcontentloaded", timeout=60_000)
        self._status = "awaiting_login"
        self.human_action_required = True
        return {
            "sessionStatus": self._status,
            "message": (
                "Opened Onshape sign-in in the browser window. Complete login "
                "manually, then call browser_session(action='status')."
            ),
        }


_session: BrowserSession | None = None


def get_session(config: BrowserConfig | None = None) -> BrowserSession:
    """Return the process-wide browser session singleton."""
    global _session
    if _session is None:
        _session = BrowserSession(config)
    return _session
