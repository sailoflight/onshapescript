"""Frame-aware generic browser interactions."""

from __future__ import annotations

import time
from typing import Any

from onshape_browser_mode.pages.base import FrameNotFoundError, resolve_scope, scope_url


def resolve_locator(
    scope: Any,
    selector: str = "",
    target_text: str = "",
    index: int = 0,
) -> Any:
    """Resolve one locator without embedding domain-specific button semantics."""
    if selector and target_text:
        locator = scope.locator(selector).filter(has_text=target_text)
    elif target_text:
        locator = scope.get_by_text(target_text, exact=False)
    elif selector:
        locator = scope.locator(selector)
    else:
        raise ValueError("Provide selector or target_text")
    return locator.nth(index)


def element_info(locator: Any) -> dict[str, Any]:
    """Return a bounded target summary for dry-run and audit output."""
    return locator.evaluate(
        """el => ({
          tag: el.tagName.toLowerCase(),
          text: (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 120),
          aria: el.getAttribute('aria-label') || '',
          title: el.getAttribute('title') || '',
          id: el.id || '',
          cls: (typeof el.className === 'string' ? el.className : '').slice(0, 120),
        })"""
    )


def wait_for_condition(
    page: Any,
    *,
    condition: str,
    selector: str = "",
    text: str = "",
    frame_url: str = "",
    timeout_ms: int = 30_000,
) -> dict[str, Any]:
    """Wait for one bounded browser condition without mutating cloud data."""
    started = time.monotonic()
    try:
        if condition == "frame":
            if not frame_url:
                raise ValueError("frame_url is required for condition='frame'")
            try:
                scope = resolve_scope(page, frame_url)
            except FrameNotFoundError:
                scope = page.wait_for_event(
                    "framenavigated",
                    predicate=lambda frame: frame_url in str(getattr(frame, "url", "")),
                    timeout=timeout_ms,
                )
        elif condition == "url":
            if not text:
                raise ValueError("text is required for condition='url'")
            page.wait_for_url(lambda url: text in str(url), timeout=timeout_ms)
            scope = page
        else:
            scope = resolve_scope(page, frame_url)
            if condition == "network_idle":
                scope.wait_for_load_state("networkidle", timeout=timeout_ms)
            elif condition == "text":
                if not selector or not text:
                    raise ValueError("selector and text are required for condition='text'")
                scope.wait_for_function(
                    """({selector, text}) => {
                      const el = document.querySelector(selector);
                      return !!el && (el.innerText || el.textContent || '').includes(text);
                    }""",
                    {"selector": selector, "text": text},
                    timeout=timeout_ms,
                )
            elif condition in ("visible", "hidden", "attached", "detached"):
                if not selector:
                    raise ValueError(f"selector is required for condition={condition!r}")
                scope.locator(selector).first.wait_for(state=condition, timeout=timeout_ms)
            else:
                raise ValueError(
                    "condition must be visible, hidden, attached, detached, text, url, network_idle, or frame"
                )
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - return timeout/navigation failures as data
        return {
            "waited": False,
            "condition": condition,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }
    return {
        "waited": True,
        "condition": condition,
        "elapsedMs": round((time.monotonic() - started) * 1000),
        "frameUrl": scope_url(scope),
    }


def press_key(
    page: Any,
    *,
    key: str,
    selector: str = "",
    target_text: str = "",
    index: int = 0,
    frame_url: str = "",
) -> dict[str, Any]:
    """Send one trusted Playwright key press to a target."""
    scope = resolve_scope(page, frame_url)
    target = resolve_locator(scope, selector, target_text, index)
    if target.count() == 0:
        return {"pressed": False, "reason": "no matching element"}
    info = element_info(target)
    target.press(key)
    return {
        "pressed": True,
        "key": key,
        "element": info,
        "frameUrl": scope_url(scope),
    }


def type_text(
    page: Any,
    *,
    text: str,
    selector: str = "",
    target_text: str = "",
    index: int = 0,
    frame_url: str = "",
    delay_ms: int = 25,
    clear: bool = False,
) -> dict[str, Any]:
    """Type text with trusted sequential keyboard events."""
    scope = resolve_scope(page, frame_url)
    target = resolve_locator(scope, selector, target_text, index)
    if target.count() == 0:
        return {"typed": False, "reason": "no matching element"}
    info = element_info(target)
    target.click()
    if clear:
        target.press("Control+A")
        target.press("Backspace")
    if hasattr(target, "press_sequentially"):
        target.press_sequentially(text, delay=delay_ms)
    else:
        target.type(text, delay=delay_ms)
    return {
        "typed": True,
        "characterCount": len(text),
        "element": info,
        "frameUrl": scope_url(scope),
    }
