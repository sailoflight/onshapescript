"""Browser-mode exceptions."""

from __future__ import annotations


class BrowserModeError(RuntimeError):
    """Base class for browser-mode failures."""


class PlaywrightNotInstalled(BrowserModeError):
    """Raised when a browser_* tool needs Playwright but it is not installed."""


class BrowserLaunchError(BrowserModeError):
    """Raised when the persistent browser context cannot be launched."""


class LoginRequired(BrowserModeError):
    """Raised when an action needs a logged-in Onshape session but none is present."""
