"""Human-operation listener for Onshape browser sessions.

The listener records what a human does in the Onshape UI so we can learn button
meaning from observed behavior rather than from brittle guesses:

- page open / close / URL changes
- network responses (URL pattern, method, status, content type)
- JS dialogs
- (optionally) click/input events when page-side event capture is wired up

Recordings are kept in memory for the lifetime of the MCP server process. The
`browser_watch` MCP tool exposes start / status / stop / report actions.
"""

from __future__ import annotations

import time
from typing import Any

from onshape_browser_mode.config import load_browser_config

MAX_EVENTS = 2000

_URL_TAG_RULES = (
    ("signin", ("/signin", "login.onshape.com")),
    ("featurestudio", ("/featurestudios/", "featurestudio")),
    ("partstudio", ("/partstudios/", "partstudio")),
    ("documents", ("/documents/", "/documents?")),
    ("other", ()),
)


def classify_url(url: str) -> str:
    lowered = (url or "").lower()
    for tag, hints in _URL_TAG_RULES:
        for hint in hints:
            if hint and hint in lowered:
                return tag
    return "other"


class WatchRecorder:
    """Record and aggregate browser watch events."""

    def __init__(self, config: Any = None) -> None:
        self.config = config or load_browser_config()
        self.events: list[dict[str, Any]] = []
        self.pages: dict[int, Any] = {}
        self.started_at: float | None = None
        self.running = False
        self._attached: set[int] = set()
        self._context_attached = False

    # -- event recording ------------------------------------------------------
    def _add(self, kind: str, **fields: Any) -> None:
        event = {
            "t": round(time.monotonic() - (self.started_at or time.monotonic()), 2),
            "kind": kind,
            **fields,
        }
        self.events.append(event)
        if len(self.events) > MAX_EVENTS:
            self.events = self.events[-MAX_EVENTS:]

    def record_event(self, kind: str, **fields: Any) -> None:
        self._add(kind, **fields)

    # -- page / context wiring -------------------------------------------------
    def attach(self, page: Any, context: Any) -> None:
        """Attach native Playwright events to one page and the context.

        Safe to call multiple times: each page/context is attached at most once.
        When Playwright is not installed, `browser_watch` never reaches this
        code path (start() raises before attach is attempted).
        """
        page_id = id(page)
        if page_id not in self._attached:
            self._attached.add(page_id)
            self.pages[page_id] = page
            try:
                page.on("framenavigated", self._on_frame_navigated)
            except Exception:
                pass
            try:
                page.on("response", self._on_response)
            except Exception:
                pass
            try:
                page.on("dialog", self._on_dialog)
            except Exception:
                pass
        if context is not None and not self._context_attached:
            try:
                context.on("page", self._on_context_page)
                self._context_attached = True
            except Exception:
                pass

    def start(self, page: Any, context: Any) -> dict[str, Any]:
        self.started_at = time.monotonic()
        self.running = True
        self._add("watch_started", url=getattr(page, "url", ""))
        self.attach(page, context)
        return self.status()

    def _on_context_page(self, page: Any) -> None:
        self._add("page_opened", page_id=id(page), url=getattr(page, "url", ""))
        self.attach(page, None)

    def _on_frame_navigated(self, frame: Any) -> None:
        # Only the main frame represents a visible URL change.
        try:
            if getattr(frame, "parent_frame", None) is not None:
                return
        except Exception:
            pass
        page = getattr(frame, "page", None)
        self._add(
            "url_change",
            page_id=id(page) if page is not None else None,
            url=getattr(page, "url", "") if page is not None else "",
            tag=classify_url(getattr(page, "url", "") if page is not None else ""),
        )

    def _on_response(self, response: Any) -> None:
        try:
            url = response.url
            status = response.status
            headers = response.headers
            content_type = headers.get("content-type", "") if headers else ""
        except Exception:
            return
        if not self.config.listener.record_network:
            return
        self._add(
            "network",
            url=url[:240],
            status=status,
            content_type=content_type[:80],
            tag=classify_url(url),
        )

    def _on_dialog(self, dialog: Any) -> None:
        try:
            message = getattr(dialog, "message", "")[:240]
        except Exception:
            message = ""
        self._add("dialog", message=message)

    # -- status / report -------------------------------------------------------
    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "startedAt": self.started_at,
            "eventCount": len(self.events),
            "pagesTracked": len(self.pages),
        }

    def stop(self) -> dict[str, Any]:
        self.running = False
        if self.started_at is not None:
            self._add("watch_stopped")
        return self.report()

    def report(self) -> dict[str, Any]:
        urls: list[str] = []
        endpoints: list[dict[str, Any]] = []
        dialogs: list[str] = []
        for event in self.events:
            if event.get("kind") == "url_change" and event.get("url"):
                if event["url"] not in urls:
                    urls.append(event["url"])
            elif event.get("kind") == "network" and event.get("url"):
                endpoints.append({
                    "url": event.get("url"),
                    "status": event.get("status"),
                    "contentType": event.get("content_type"),
                    "tag": event.get("tag"),
                })
            elif event.get("kind") == "dialog":
                dialogs.append(event.get("message", ""))
        # Keep the report bounded: unique URLs, last 50 endpoints, first 20 dialogs.
        unique_endpoints = []
        seen_endpoints = set()
        for endpoint in endpoints:
            key = (endpoint["url"], endpoint["status"])
            if key not in seen_endpoints:
                seen_endpoints.add(key)
                unique_endpoints.append(endpoint)
        return {
            "running": self.running,
            "eventCount": len(self.events),
            "pagesTracked": len(self.pages),
            "uniqueUrls": urls,
            "urlTags": sorted({classify_url(url) for url in urls}),
            "endpoints": unique_endpoints[:50],
            "dialogs": dialogs[:20],
            "note": (
                "Recorded from human browser operation. Use button-map review in dev/ "
                "to convert observed URL/network patterns into selector-based actions."
            ),
        }


_recorder: WatchRecorder | None = None


def get_recorder() -> WatchRecorder:
    """Return the process-wide watch recorder singleton."""
    global _recorder
    if _recorder is None:
        _recorder = WatchRecorder()
    return _recorder
