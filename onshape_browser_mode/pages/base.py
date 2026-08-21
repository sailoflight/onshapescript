"""Shared primitives for Onshape page objects."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _url_without_query(value: Any) -> str:
    parts = urlsplit(str(value or ""))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


class FrameNotFoundError(ValueError):
    """Raised when a requested Playwright frame URL has no match."""


class AmbiguousFrameError(ValueError):
    """Raised when a requested Playwright frame URL has multiple matches."""


def resolve_scope(page: Any, frame_url: str = "") -> Any:
    """Return the main page or the unique frame whose URL contains frame_url."""
    needle = (frame_url or "").strip()
    if not needle:
        return page
    frames = list(getattr(page, "frames", []) or [])
    matches = [frame for frame in frames if needle in str(getattr(frame, "url", ""))]
    if not matches:
        available = [_url_without_query(getattr(frame, "url", "")) for frame in frames]
        raise FrameNotFoundError(
            f"No frame URL contains {needle!r}; available frames: {available}"
        )
    if len(matches) > 1:
        urls = [_url_without_query(getattr(frame, "url", "")) for frame in matches]
        raise AmbiguousFrameError(
            f"Frame URL {needle!r} is ambiguous; matching frames: {urls}"
        )
    return matches[0]


def scope_url(scope: Any) -> str | None:
    """Read a page/frame URL while dropping query metadata and fragments."""
    try:
        return _url_without_query(scope.url)
    except Exception:  # noqa: BLE001 - best effort browser metadata
        return None


class BasePage:
    """Base wrapper that resolves the main page or one cross-origin frame."""

    def __init__(self, page: Any, frame_url: str = "") -> None:
        self.page = page
        self.frame_url = frame_url
        self.scope = resolve_scope(page, frame_url)

    @property
    def url(self) -> str | None:
        return scope_url(self.scope)

    def locator(self, selector: str = "", text: str = "", index: int = 0) -> Any:
        """Resolve one locator by selector/text using the wrapped scope."""
        if selector and text:
            locator = self.scope.locator(selector).filter(has_text=text)
        elif text:
            locator = self.scope.get_by_text(text, exact=False)
        elif selector:
            locator = self.scope.locator(selector)
        else:
            raise ValueError("Provide selector or text")
        return locator.nth(index)
