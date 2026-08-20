"""Persistent Playwright browser session for Onshape.

The session owns a persistent Chrome profile so a human can log in once and
later browser_* calls reuse the cookies. Playwright is imported lazily: the MCP
server and every offline tool must run without it installed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from onshape_browser_mode.config import BrowserConfig, load_browser_config
from onshape_browser_mode.errors import BrowserLaunchError, PlaywrightNotInstalled

ROOT = Path(__file__).resolve().parents[1]

# Keep the automation-controlled flag deterministic across pages. Onshape does
# not appear to hard-block automation, but this removes one fingerprint that is
# under our control. No credential or captcha logic lives here.
_STEALTH_JS = "Object.defineProperty(navigator, 'webdriver', {get: () => false});"

_SIGNIN_URL = "https://cad.onshape.com/signin"


def _is_onshape_app_url(url: str | None) -> bool:
    """True when ``url`` is an authenticated Onshape application page.

    ``launch_persistent_context`` restores the previous session's tabs. A
    restored tab such as ``https://cad.onshape.com/documents?...nodeId=...``
    already carries the login session, so it must be treated as logged in
    instead of being thrown away and replaced with the /signin page.
    """
    if not url:
        return False
    lowered = url.lower()
    if "about:blank" in lowered:
        return False
    if "cad.onshape.com" not in lowered:
        return False
    if "/signin" in lowered or "login.onshape.com" in lowered:
        return False
    return True


class BrowserSession:
    """Lazy singleton-style holder for the persistent context and working page."""

    def __init__(self, config: BrowserConfig | None = None) -> None:
        self.config = config or load_browser_config()
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._status = "uninitialized"
        self.human_action_required = False
        self.login_confirmed = False

    @property
    def context(self):
        """The persistent Playwright context, or None before start()."""
        return self._context

    @property
    def page(self):
        """The working page, or None before start()."""
        return self._page

    @staticmethod
    def playwright_available() -> bool:
        """True when the Playwright package can be imported.

        The import check does NOT launch a browser or verify a browser binary;
        that happens in start() and failures surface as BrowserLaunchError.
        """
        try:
            import playwright.sync_api  # noqa: F401
            return True
        except Exception:
            return False

    def profile_dir(self) -> Path:
        raw = Path(self.config.browser.user_data_dir).expanduser()
        if raw.is_absolute():
            return raw.resolve()
        return (ROOT / raw).resolve()

    @staticmethod
    def _state_path() -> Path:
        return ROOT / "config" / "browser-state.json"

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
            path.write_text(
                json.dumps({"lastAppUrl": url}, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _enforce_single_working_page(self, keep_page: Any) -> None:
        """Close every page in the context except ``keep_page``.

        Deterministic tab management (the "single working page" rule, same as
        taobao-mcp): the automation never relies on Chromium's session-restore
        or the human's tab layout. Popups, restored tabs, and tabs the human
        opened while logging in are all closed so the active page cannot drift
        into a stale tab.
        """
        if self._context is None:
            return
        for page in list(self._context.pages or []):
            if page is keep_page:
                continue
            try:
                if not page.is_closed():
                    page.close()
            except Exception:
                pass

    def start(self):
        """Launch (or reuse) the persistent browser context and return its page.

        Never treats a transient ``evaluate`` failure as "browser dead": a page
        that is mid-navigation throws "Execution context was destroyed" for a
        moment, and reacting with a full relaunch would kill a human's
        logged-in browser session. A fresh launch only happens when the context
        is truly gone or unreachable.
        """
        # 1. Reuse an existing responsive page from the live context, preferring
        #    an already-logged-in Onshape app page (the human may have logged in
        #    a different tab than the one we last held).
        if self._context is not None:
            pages = list(self._context.pages or [])

            for page in pages:
                try:
                    if not page.is_closed() and _is_onshape_app_url(page.url):
                        page.evaluate("1 + 1")
                        self._page = page
                        self.login_confirmed = True
                        self.human_action_required = False
                        page.bring_to_front()
                        self._enforce_single_working_page(page)
                        return page
                except Exception:
                    continue

            candidates: list[Any] = []
            if self._page is not None:
                candidates.append(self._page)
            for page in pages:
                if page is not self._page:
                    candidates.append(page)
            for page in candidates:
                try:
                    if not page.is_closed():
                        page.evaluate("1 + 1")
                        self._page = page
                        page.bring_to_front()
                        self._enforce_single_working_page(page)
                        return page
                except Exception:
                    continue

            # Context exists but no page is responsive: open a fresh page on it.
            try:
                self._page = self._context.new_page()
                self._page.bring_to_front()
                self._enforce_single_working_page(self._page)
                self._status = "started"
                return self._page
            except Exception:
                # The context itself is dead; fall through to a full relaunch.
                self.close()

        if not self.playwright_available():
            raise PlaywrightNotInstalled(
                "Playwright is not installed on the Windows browser host. See "
                "tools/windows/README.md for setup, or run: "
                "C:\\path\\to\\onshapescript\\.venv\\Scripts\\python.exe -m pip install "
                "-r tools\\windows\\requirements-browser.txt"
            )

        from playwright.sync_api import sync_playwright

        browser_cfg = self.config.browser
        profile = self.profile_dir()
        profile.mkdir(parents=True, exist_ok=True)

        launch_kwargs: dict[str, Any] = {
            "user_data_dir": str(profile),
            "headless": browser_cfg.headless,
            "locale": browser_cfg.locale,
            "timezone_id": browser_cfg.timezone,
            "viewport": {"width": 1280, "height": 800},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if browser_cfg.executable_path:
            launch_kwargs["executable_path"] = browser_cfg.executable_path
        elif browser_cfg.channel:
            launch_kwargs["channel"] = browser_cfg.channel
        if browser_cfg.proxy_server:
            launch_kwargs["proxy"] = {"server": browser_cfg.proxy_server}

        # A previous Edge may still be releasing the profile lock; retry briefly
        # instead of failing on the first "browser has been closed" race.
        last_exc: Exception | None = None
        for attempt in range(3):
            self._playwright = sync_playwright().start()
            try:
                self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
                break
            except Exception as exc:
                last_exc = exc
                self._stop_playwright()
                if attempt < 2:
                    time.sleep(2.0)
        else:
            raise BrowserLaunchError(
                f"Could not launch browser (channel={browser_cfg.channel!r}): {last_exc}. "
                "Use the Windows host's existing Chrome/Edge (no browser download); "
                "set channel/executable_path in config/browser.local.toml. See "
                "tools/windows/README.md."
            ) from last_exc

        self._context.add_init_script(_STEALTH_JS)

        # Residual-tab cleanup (same fix taobao-mcp landed 2026-08-20):
        # launch_persistent_context restores every tab left over from the last
        # session. Those stale pages make the active page drift during popup /
        # navigation flows and can trigger risk checks, so on every fresh
        # launch keep exactly ONE working page and close the rest.
        #
        # IMPORTANT Onshape nuance: prefer a restored tab that is already an
        # authenticated app page (e.g. /documents?...nodeId=...) — it carries
        # the login session. Only fall back to a blank/signin page when no
        # logged-in tab was restored.
        restored = list(self._context.pages or [])
        self._page = None

        # 1. Prefer a restored, already-logged-in app page.
        for page in restored:
            try:
                if _is_onshape_app_url(page.url):
                    self._page = page
                    break
            except Exception:
                continue

        # 2. Otherwise keep the first live page.
        if self._page is None:
            for page in restored:
                try:
                    if not page.is_closed():
                        self._page = page
                        break
                except Exception:
                    continue

        if self._page is None or self._page.is_closed():
            try:
                self._page = self._context.new_page()
            except Exception:
                self._page = self._context.pages[0] if self._context.pages else None

        # 3. Deterministic single-page rule: close every other tab.
        if self._page is not None:
            self._enforce_single_working_page(self._page)
        if self._page is not None:
            try:
                self._page.bring_to_front()
            except Exception:
                pass

        if _is_onshape_app_url(self._page.url if self._page is not None else None):
            self.login_confirmed = True
            self.human_action_required = False
        self._status = "started"
        return self._page

    def close(self) -> None:
        context = self._context
        if context is not None:
            try:
                context.close()
            except Exception:
                # context.close() can fail mid-navigation; fall back to the
                # browser handle so the profile lock is actually released.
                try:
                    browser = getattr(context, "browser", None)
                    if browser is not None:
                        browser.close()
                except Exception:
                    pass
        self._stop_playwright()
        self._context = None
        self._page = None
        self._status = "closed"

    def _stop_playwright(self) -> None:
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None

    def status(self) -> dict[str, Any]:
        # Report the most useful page, not blindly the last one we held: the
        # human may have logged in another tab while we were idle.
        page_url = None
        if self._context is not None:
            for page in list(self._context.pages or []):
                try:
                    if page.is_closed():
                        continue
                    url = page.url
                except Exception:
                    continue
                if _is_onshape_app_url(url):
                    page_url = url
                    self._page = page
                    break
                if page_url is None and page is self._page:
                    page_url = url
            if page_url is None and self._page is not None:
                try:
                    if not self._page.is_closed():
                        page_url = self._page.url
                except Exception:
                    page_url = None
        elif self._page is not None:
            try:
                if not self._page.is_closed():
                    page_url = self._page.url
            except Exception:
                page_url = None

        login_confirmed = bool(self.login_confirmed or _is_onshape_app_url(page_url))
        if login_confirmed:
            self.login_confirmed = True
            self.human_action_required = False
            if page_url:
                self._save_app_url(page_url)
        return {
            "playwrightInstalled": self.playwright_available(),
            "configured": True,
            "profileDir": str(self.profile_dir()),
            "sessionStatus": self._status,
            "pageUrl": page_url,
            "headless": self.config.browser.headless,
            "humanActionRequired": self.human_action_required,
            "loginConfirmed": login_confirmed,
        }

    def open_login_page(self) -> dict[str, Any]:
        """Open Onshape sign-in in the persistent, headed browser.

        Login itself is always a human action: SSO, 2FA, and risk checks are
        deliberately never automated. If the persistent profile restored an
        already-logged-in Onshape page, do NOT navigate to /signin — that
        would discard the working session.
        """
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

        # The profile may hold valid cookies but launch_persistent_context does
        # not reliably auto-restore the previous tabs. Try the last known
        # logged-in Onshape URL first: cookies + entry URL restore the session
        # without a human re-login.
        saved_url = self._load_saved_app_url()
        if saved_url:
            try:
                page.goto(saved_url, wait_until="domcontentloaded", timeout=60_000)
                # Onshape is a SPA: the requested documents URL can flash before
                # the client router redirects an unauthenticated session to
                # /signin. Wait for the router to settle, then judge by the
                # FINAL url — never by the URL right after domcontentloaded.
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
                        "message": (
                            "Logged in via saved Onshape entry URL "
                            f"({page.url})."
                        ),
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
