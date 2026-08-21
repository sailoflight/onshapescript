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

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from onshape_browser_mode.settings import load_browser_config

MAX_EVENTS = 2000

_URL_TAG_RULES = (
    ("signin", ("/signin", "login.onshape.com")),
    ("featurestudio", ("/featurestudios/", "featurestudio")),
    ("partstudio", ("/partstudios/", "partstudio")),
    ("documents", ("/documents",)),
    ("other", ()),
)


def validate_workflow_name(name: str) -> str:
    """Validate names used to derive recording and template filenames."""
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name):
        raise ValueError("workflow must use only letters, numbers, dot, underscore, or hyphen")
    return name


def sanitize_url(url: str) -> str:
    """Remove query and fragment data before a URL reaches a recording."""
    try:
        parts = urlsplit(url or "")
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))[:240]
    except Exception:
        return ""


def classify_url(url: str) -> str:
    lowered = (url or "").lower()
    for tag, hints in _URL_TAG_RULES:
        for hint in hints:
            if hint and hint in lowered:
                return tag
    return "other"


def verify_watch_recording(events: list[dict[str, Any]], template: dict[str, Any]) -> dict[str, Any]:
    """Verify that expected event patterns occur in order in a recording."""
    cursor = 0
    steps = []
    for expected in template.get("expectedSequence", []):
        required = bool(expected.get("required", True))
        matched = None
        for index in range(cursor, len(events)):
            event = events[index]
            if expected.get("kind") and event.get("kind") != expected["kind"]:
                continue
            if expected.get("tag") and event.get("tag") != expected["tag"]:
                continue
            status = event.get("status")
            if expected.get("statusMin") is not None and (status is None or status < expected["statusMin"]):
                continue
            if expected.get("statusMax") is not None and (status is None or status > expected["statusMax"]):
                continue
            if expected.get("action") and event.get("action") != expected["action"]:
                continue
            if expected.get("textContains") and expected["textContains"] not in str(event.get("text", "")):
                continue
            matched = index
            break
        ok = matched is not None or not required
        steps.append({"name": expected.get("name", expected.get("kind", "event")), "ok": ok, "matchedIndex": matched})
        if matched is not None:
            cursor = matched + 1
    return {
        "workflow": template.get("name", ""),
        "ok": all(step["ok"] for step in steps),
        "steps": steps,
        "eventCount": len(events),
    }


class WatchRecorder:
    """Record and aggregate browser watch events."""

    def __init__(self, config: Any = None) -> None:
        self.config = config or load_browser_config()
        self.events: list[dict[str, Any]] = []
        self.pages: dict[int, Any] = {}
        self.started_at: float | None = None
        self.running = False
        self._attached: dict[int, Any] = {}
        self._attached_context: Any = None
        self.workflow = "browser-session"

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
        if self._attached.get(page_id) is not page:
            self._attached[page_id] = page
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
            self._install_dom_capture(page)
        if context is not None and self._attached_context is not context:
            try:
                context.on("page", self._on_context_page)
                self._attached_context = context
            except Exception:
                pass

    def start(self, page: Any, context: Any, workflow: str = "browser-session") -> dict[str, Any]:
        self.workflow = validate_workflow_name(workflow or "browser-session")
        self.events = []
        page_id = id(page)
        self.pages = {page_id: page}
        self._attached = (
            {page_id: page} if self._attached.get(page_id) is page else {}
        )
        self.started_at = time.monotonic()
        self.running = True
        self._add("watch_started", url=sanitize_url(getattr(page, "url", "")))
        self.attach(page, context)
        return self.status()

    def _on_context_page(self, page: Any) -> None:
        if not self.running:
            return
        self._add("page_opened", page_id=id(page), url=sanitize_url(getattr(page, "url", "")))
        self.attach(page, None)

    def _on_frame_navigated(self, frame: Any) -> None:
        if not self.running:
            return
        # Only the main frame represents a visible URL change.
        try:
            if getattr(frame, "parent_frame", None) is not None:
                return
        except Exception:
            pass
        page = getattr(frame, "page", None)
        if page is not None and id(page) not in self.pages:
            return
        self._add(
            "url_change",
            page_id=id(page) if page is not None else None,
            url=sanitize_url(getattr(page, "url", "")) if page is not None else "",
            tag=classify_url(getattr(page, "url", "") if page is not None else ""),
        )

    def _on_response(self, response: Any) -> None:
        if not self.running:
            return
        try:
            response_page = getattr(getattr(response, "frame", None), "page", None)
            if response_page is not None and id(response_page) not in self.pages:
                return
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
            url=sanitize_url(url),
            status=status,
            content_type=content_type[:80],
            tag=classify_url(url),
        )

    def _on_dialog(self, dialog: Any) -> None:
        if not self.running:
            return
        dialog_page = getattr(dialog, "page", None)
        if dialog_page is not None and id(dialog_page) not in self.pages:
            return
        try:
            message = getattr(dialog, "message", "")[:240]
        except Exception:
            message = ""
        self._add("dialog", message=message)

    def _install_dom_capture(self, page: Any) -> None:
        """Capture trusted click/input events for human workflow recordings."""
        if not self.config.listener.record_dom_snippets:
            return
        binding = "__dshRecordBrowserEvent"
        try:
            page.expose_binding(
                binding,
                lambda source, payload: self._add(
                    "dom", **(payload if isinstance(payload, dict) else {})
                ) if self.running and id(source.get("page")) in self.pages else None,
            )
        except Exception:
            pass
        script = r"""
        () => {
          if (window.__dshBrowserRecorderInstalled) return;
          window.__dshBrowserRecorderInstalled = true;
          const describe = (el) => ({
            tag: (el.tagName || '').toLowerCase(),
            id: el.id || '',
            aria: el.getAttribute && (el.getAttribute('aria-label') || ''),
            text: (el.matches && el.matches('input, textarea') ? '' : (el.innerText || el.textContent || '')).trim().replace(/\s+/g, ' ').slice(0, 160),
            inputType: (el.matches && el.matches('input')) ? (el.getAttribute('type') || 'text') : '',
            cls: (typeof el.className === 'string' ? el.className : '').slice(0, 120),
          });
          for (const type of ['click', 'input', 'change', 'keydown']) {
            document.addEventListener(type, (event) => {
              const payload = describe(event.target || document.body);
              payload.action = type;
              if (type === 'keydown') payload.key = (event.key || '').length === 1 ? '<CHAR>' : (event.key || '');
              window.__dshRecordBrowserEvent(payload).catch(() => {});
            }, true);
          }
        }
        """
        try:
            page.add_init_script(script)
            page.evaluate(script)
        except Exception:
            pass

    # -- status / report -------------------------------------------------------
    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "startedAt": self.started_at,
            "eventCount": len(self.events),
            "pagesTracked": len(self.pages),
        }

    def stop(self) -> dict[str, Any]:
        if self.started_at is not None:
            self._add("watch_stopped")
        self.running = False
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

    def save(self, filename: str | None = None) -> dict[str, Any]:
        """Persist a bounded recording under the configured output directory."""
        if filename and (Path(filename).name != filename or not filename.endswith(".json")):
            raise ValueError("filename must be a simple .json filename")
        output_dir = Path(self.config.listener.output_dir)
        if not output_dir.is_absolute():
            output_dir = Path(__file__).resolve().parents[1] / output_dir
        output = output_dir / (filename or (
            f"{self.workflow}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
        ))
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "workflow": self.workflow,
            "savedAt": datetime.now(timezone.utc).isoformat(),
            "eventCount": len(self.events),
            "events": self.events,
        }
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(output)
        return {"saved": True, "path": str(output), "eventCount": len(self.events)}

    def workflows(self) -> dict[str, Any]:
        root = Path(__file__).resolve().parents[1] / "dev" / "fixtures-capture" / "watch"
        names = sorted(path.name.removesuffix(".template.json") for path in root.glob("*.template.json"))
        return {"workflows": names}

    def verify(self, workflow: str) -> dict[str, Any]:
        workflow = validate_workflow_name(workflow)
        root = Path(__file__).resolve().parents[1] / "dev" / "fixtures-capture" / "watch"
        path = root / f"{workflow}.template.json"
        if not path.exists():
            raise ValueError(f"Unknown watch workflow: {workflow}")
        template = json.loads(path.read_text(encoding="utf-8"))
        return verify_watch_recording(self.events, template)


_recorder: WatchRecorder | None = None


def get_recorder() -> WatchRecorder:
    """Return the process-wide watch recorder singleton."""
    global _recorder
    if _recorder is None:
        _recorder = WatchRecorder()
    return _recorder
