"""Persistent Playwright browser session for Onshape.

The session owns a persistent Chrome profile so a human can log in once and
later browser_* calls reuse the cookies. Playwright is imported lazily: the MCP
server and every offline tool must run without it installed.
"""

from __future__ import annotations

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

    def start(self):
        """Launch (or reuse) the persistent browser context and return its page."""
        if self._page is not None and not self._page.is_closed():
            try:
                self._page.evaluate("1 + 1")
                return self._page
            except Exception:
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

        self._playwright = sync_playwright().start()
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

        try:
            self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as exc:
            self._stop_playwright()
            raise BrowserLaunchError(
                f"Could not launch browser (channel={browser_cfg.channel!r}): {exc}. "
                "Use the Windows host's existing Chrome/Edge (no browser download); "
                "set channel/executable_path in config/browser.local.toml. See "
                "tools/windows/README.md."
            ) from exc

        self._context.add_init_script(_STEALTH_JS)
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._status = "started"
        return self._page

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
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
        page_url = None
        if self._page is not None and not self._page.is_closed():
            try:
                page_url = self._page.url
            except Exception:
                page_url = None
        return {
            "playwrightInstalled": self.playwright_available(),
            "configured": True,
            "profileDir": str(self.profile_dir()),
            "sessionStatus": self._status,
            "pageUrl": page_url,
            "headless": self.config.browser.headless,
            "humanActionRequired": self.human_action_required,
            "loginConfirmed": self.login_confirmed,
        }

    def open_login_page(self) -> dict[str, Any]:
        """Open Onshape sign-in in the persistent, headed browser.

        Login itself is always a human action: SSO, 2FA, and risk checks are
        deliberately never automated.
        """
        page = self.start()
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
