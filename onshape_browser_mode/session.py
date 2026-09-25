"""Onshape business facade over a lazily imported browser_common resource owner.

The shared library owns native Playwright resources; login, recovery selection,
configuration and MCP response contracts remain here. Offline tools need neither
Playwright nor browser_common installed.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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


# A browser-internal downloads page is not an Onshape page and never answers a
# page-level RPC. Measured live 2026-09-20: after ``browser_export_step``, Edge
# ends up on ``edge://downloads-hub/`` and a ``page.evaluate(...)`` on that
# target sits there until the MCP call fails with ``downstream_timeout`` (~32 s),
# while the target lingers in "closing" state; every later page-level tool call
# fails the same way until the target is closed. Such a page must never become
# the working page and must never be probed, so the only safe action is to close
# it, best-effort, and keep looking for the Onshape app page.
_NOISE_PAGE_SCHEMES = frozenset({"edge", "chrome"})
_NOISE_PAGE_PREFIX = "downloads"


def _is_browser_internal_noise_url(url: str | None) -> bool:
    """True for ``edge://downloads-hub/``, ``edge://downloads/`` and chrome peers.

    Chromium internal URLs carry the page name in the authority
    (``urlsplit("edge://downloads-hub/").netloc == "downloads-hub"`` and its path
    is just ``/``), so the authority is checked first and the path is only the
    fallback shape.
    """
    if not isinstance(url, str) or not url:
        return False
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    if parts.scheme.lower() not in _NOISE_PAGE_SCHEMES:
        return False
    segment = (parts.netloc or parts.path or "").strip("/").lower().split("/", 1)[0]
    return segment.startswith(_NOISE_PAGE_PREFIX)


def _safe_page_url(page: Any) -> str | None:
    """Read a page URL without raising; a failed read proves nothing about liveness."""
    try:
        url = page.url
    except Exception:
        return None
    return url if isinstance(url, str) else None


def _page_is_closed(page: Any) -> bool:
    """Read page liveness without raising; a failed read is not proof of closure.

    A candidate can close between the selection read and `adopt_page`, and
    browser_common raises `ResourceUnavailableError("Cannot adopt a closed page")`
    for such a page (``browser_common/_core.py`` adopt_page). "Cannot tell" has to
    mean "not proven closed", so that an unreadable page stays a candidate and an
    actual close is the only thing this helper skips.
    """
    try:
        return bool(page.is_closed())
    except Exception:
        return False


#: The profile-directory walk is capped so one status call cannot hang on a cold
#: multi-gigabyte profile. Chromium profiles hold tens of thousands of small
#: cache/LevelDB files, so `profileBytes` is a LOWER BOUND once the cap is hit --
#: which status reports through `profileBytesComplete` rather than hiding.
_PROFILE_WALK_FILE_CAP = 20000

#: A Chromium/Edge profile carries the signed-in account marker in one of these
#: files. Both are optional and their shape is version-dependent.
_PROFILE_ACCOUNT_FILES = (("Local State",), ("Default", "Preferences"))
#: Never parse an unbounded file on a status call. The identity blobs these keys
#: live in are small; a larger file is a different structure.
_PROFILE_ACCOUNT_FILE_MAX_BYTES = 2_000_000

#: Candidate keys that can carry an Edge/Chromium account identity. The names have
#: moved between Edge versions and NO public Edge schema pins them, so this is a
#: recursive NAME match and not a fixed JSON path. UNKNOWN: whether any one path
#: survives an Edge update. A False result therefore means "no marker found", NOT
#: "the profile is definitely anonymous". Only a boolean leaves this module --
#: account values are never read into a result, printed, or logged.
_ACCOUNT_MARKER_KEYS = frozenset({
    "edge_account_consistency",
    "edge_account_info",
    "account_info",
    "account_id",
    "gaia_id",
    "user_name",
    "signed_in",
})
_ACCOUNT_MARKER_MAX_DEPTH = 6


def _marker_value_present(value: Any) -> bool:
    """True only for a value that could actually identify a signed-in account."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, (dict, list, tuple)):
        return len(value) > 0
    return True


def _account_marker_in_json(data: Any, *, depth: int = 0) -> bool:
    if depth > _ACCOUNT_MARKER_MAX_DEPTH:
        return False
    if isinstance(data, dict):
        for key, value in data.items():
            if key in _ACCOUNT_MARKER_KEYS and _marker_value_present(value):
                return True
            if isinstance(value, (dict, list)) and _account_marker_in_json(value, depth=depth + 1):
                return True
    elif isinstance(data, (list, tuple)):
        return any(_account_marker_in_json(item, depth=depth + 1) for item in data)
    return False


def _profile_account_marker(profile_dir: Path) -> bool:
    """Whether the profile carries a candidate signed-in-account marker.

    Defensive by construction: a missing directory, a missing or malformed JSON
    file, and a read error all answer False and never raise. Only the boolean
    leaves this function.
    """
    for parts in _PROFILE_ACCOUNT_FILES:
        path = profile_dir.joinpath(*parts)
        try:
            if not path.is_file() or path.stat().st_size > _PROFILE_ACCOUNT_FILE_MAX_BYTES:
                continue
            parsed = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        try:
            if _account_marker_in_json(parsed):
                return True
        except Exception:
            continue
    return False


def _profile_dir_size_bytes(
    profile_dir: Path, *, file_cap: int | None = None
) -> tuple[int | None, bool]:
    """Bounded recursive size of ``profile_dir`` as ``(bytes, complete)``.

    ``None`` means the directory is absent (never created, or already removed).
    ``complete`` is False once the walk hits ``file_cap``, so the caller can
    report a lower bound instead of presenting it as exact. Directory symlinks
    are not followed, so a link loop cannot trap the walk. The cap is read from
    the module at call time (not bound as a default) so tests can lower it.
    """
    limit = _PROFILE_WALK_FILE_CAP if file_cap is None else int(file_cap)
    try:
        if not profile_dir.is_dir():
            return None, False
    except OSError:
        return None, False
    total = 0
    seen = 0
    stack = [profile_dir]
    while stack and seen < limit:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if seen >= limit:
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                            seen += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return total, seen < limit


# Chromium's own pages live on these schemes (a normal page is http(s) or
# about:blank). They are never handed to browser_common's page cleanup, because
# that cleanup closes every page it is given and closing an internal target is
# the one call that never returns.
_BROWSER_INTERNAL_SCHEMES = frozenset({"edge", "chrome", "devtools", "brave", "vivaldi", "opera"})


def _is_browser_internal_url(url: str | None) -> bool:
    """True for any browser-internal URL (``edge://``, ``chrome://``, ...).

    ``about:blank`` is deliberately NOT internal: a temporary popup starts there
    and must stay closable by the shared page cleanup.
    """
    if not isinstance(url, str) or not url:
        return False
    try:
        scheme = urlsplit(url.strip()).scheme.lower()
    except ValueError:
        return False
    return scheme in _BROWSER_INTERNAL_SCHEMES


def _resident_cdp_port() -> int | None:
    """The resident browser's loopback DevTools port, when residency is enabled.

    Gated on ``resident`` on purpose: ``resident_port`` has a default value, so
    without this check a non-resident deployment would still send DevTools close
    requests to whatever unrelated process happens to listen on that port.
    """
    try:
        browser = load_browser_config().browser
        if not getattr(browser, "resident", False):
            return None
        port = getattr(browser, "resident_port", None)
    except Exception:
        return None
    return port if isinstance(port, int) and port > 0 else None


def _devtools_http(port: int, path: str, timeout: float) -> str:
    """One loopback DevTools HTTP call, bounded by a socket timeout."""
    with urllib.request.urlopen(  # noqa: S310 - loopback DevTools endpoint only
        f"http://127.0.0.1:{port}{path}", timeout=timeout
    ) as response:
        return response.read().decode("utf-8", "replace")


def _devtools_page_targets(port: int, timeout: float) -> list[dict[str, Any]] | None:
    """Page targets listed by the loopback DevTools endpoint; None when unreachable.

    ``None`` and ``[]`` mean different things and callers must not conflate them:
    an unreachable endpoint proves nothing about which targets exist.
    """
    try:
        targets = json.loads(_devtools_http(port, "/json/list", timeout))
    except Exception:
        return None
    if not isinstance(targets, list):
        return None
    return [
        target
        for target in targets
        if isinstance(target, dict) and target.get("type") == "page"
    ]


def _browser_internal_targets(port: int, timeout: float) -> list[dict[str, Any]] | None:
    """Browser-internal page targets currently listed; None when unreachable."""
    targets = _devtools_page_targets(port, timeout)
    if targets is None:
        return None
    return [target for target in targets if _is_browser_internal_url(target.get("url"))]


def _close_browser_internal_page(page: Any, *, timeout: float = 2.0) -> bool:
    """Ask the browser to close one internal target WITHOUT touching Playwright.

    Measured live 2026-09-20: ``page.close()`` on Edge's ``edge://downloads-hub/``
    target never returns. The target stays in DevTools' "closing" state, so
    ``browser_common``'s cleanup - which closes every page it is handed - turns
    that page into a transport timeout (``downstream_timeout`` after ~32 s) and
    every later page-level call meets the same wedged target. This helper
    therefore never calls into Playwright: it asks the resident browser's own
    loopback DevTools endpoint to close the target, bounded by a socket timeout.

    Returns True only when the close request was ACCEPTED. That is deliberately
    weaker than "the page is gone": measured live 2026-09-20, Edge accepts the
    close of ``edge://downloads-hub/`` and keeps the target listed anyway, so a
    caller that needs the stronger fact must read it with
    ``_browser_internal_pages_remaining``.
    """
    port = _resident_cdp_port()
    url = _safe_page_url(page)
    if port is None or not url:
        return False
    targets = _browser_internal_targets(port, timeout)
    if targets is None:
        return False
    for target in targets:
        if target.get("url") != url:
            continue
        try:
            _devtools_http(port, "/json/close/" + str(target.get("id", "")), timeout)
        except Exception:
            return False
        return True
    return False


def _browser_internal_pages_remaining(*, timeout: float = 2.0) -> int | None:
    """How many browser-internal page targets are still listed, or None if unknown.

    An accepted close is not removal (measured live 2026-09-20 for Edge's
    ``edge://downloads-hub/``, which stays listed as "Target is closing"). This
    exists so callers can report what is observable instead of claiming a page was
    closed. ``None`` means the DevTools endpoint could not be reached.
    """
    port = _resident_cdp_port()
    if port is None:
        return None
    targets = _browser_internal_targets(port, timeout)
    return None if targets is None else len(targets)


def _close_browser_internal_pages(pages: Any, **kwargs: Any) -> int:
    """Request a close for every browser-internal page in ``pages``.

    Returns the number of ACCEPTED close requests, not the number of pages that
    disappeared; a browser with no reachable DevTools endpoint reports 0 and every
    failure stays silent, because leaving a stray internal tab open is harmless
    while blocking on one is not.
    """
    closed = 0
    for page in pages:
        if _is_browser_internal_url(_safe_page_url(page)) and _close_browser_internal_page(page, **kwargs):
            closed += 1
    return closed


def _cleanup_candidates(pages: Any) -> list[Any]:
    """The pages browser_common's cleanup may close: never a browser-internal one.

    ``SyncSession.reconcile_pages`` closes every page it is handed, so handing it
    ``context.pages`` verbatim is what wedged every page-level tool call. A page
    whose URL cannot be read is filtered out as well: for a routine whose only job
    is to close pages, "cannot tell" has to mean "leave it alone", while the
    selection paths below keep such a page as a fallback candidate.
    """
    candidates: list[Any] = []
    for page in pages:
        url = _safe_page_url(page)
        if not isinstance(url, str) or not url:
            continue
        if _is_browser_internal_url(url):
            continue
        candidates.append(page)
    return candidates


def _dismiss_browser_internal_pages(pages: Any) -> list[Any]:
    """Live usable pages in order, closing browser-internal noise as it is found.

    A page whose liveness cannot be read is skipped: a read error is not proof of
    closure, but it is not a usable candidate either. A page whose URL cannot be
    read is kept, because an unreadable URL is not proof of a noise page. Noise
    pages are dropped and never probed: the browser is asked to close them through
    its own loopback DevTools endpoint, never through Playwright, whose close()
    on such a target does not return.
    """
    usable: list[Any] = []
    for page in pages:
        try:
            if page.is_closed():
                continue
        except Exception:
            continue
        if _is_browser_internal_noise_url(_safe_page_url(page)):
            _close_browser_internal_page(page)
            continue
        usable.append(page)
    return usable


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
        "docs/operations/MCP_RUNBOOK.md. Once a browser is available, "
        "browser_session action=login re-establishes the Onshape session."
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
        #: Outcome of the last working-page selection performed by `start()`.
        #: `{"considered": n, "discarded": [{"url": ..., "reason": ...}],
        #: "selected": "reused" | "new" | None}`; None before the first start.
        self.last_page_selection: dict[str, Any] | None = None

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
            # Only the spawn-time identity, never the per-page launch options: those
            # reach `launch_persistent_context` through `launch_options` above, and the
            # adapter reads the viewport from there. Passing them twice is how a stray
            # `viewport` kwarg became a TypeError instead of a window size.
            factory = resident_playwright_factory(
                profile_dir=self.profile_dir(),
                port=browser_cfg.resident_port,
                channel=browser_cfg.channel,
                executable_path=browser_cfg.executable_path,
                proxy_server=browser_cfg.proxy_server,
                locale=browser_cfg.locale,
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
        # `isolated_user_data_dir` (settings.BrowserCfg) lets one deployment pick a
        # separate directory instead of the shared persistent profile. Empty, the
        # historical `user_data_dir` is used unchanged.
        configured = self.config.browser.isolated_user_data_dir or self.config.browser.user_data_dir
        raw = Path(configured).expanduser()
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
        # browser_common's cleanup CLOSES every page it is handed, and closing a
        # browser-internal target through Playwright never returns (measured live
        # 2026-09-20). Handing it the raw context.pages was what made every
        # page-level tool call time out while a stray edge://downloads-hub/
        # target existed, so internal pages are filtered out here and left to the
        # bounded DevTools request in _close_browser_internal_page.
        report = self._resources.reconcile_pages(_cleanup_candidates(list(context.pages or [])))
        if not report.complete:
            raise PageCleanupError(report)

    def _fallback_page(self, *, excluding: Any = None) -> Any:
        """First usable page in the owner's context, preferring the Onshape app."""
        context = self.context
        if context is None:
            return None
        usable = [
            page for page in _dismiss_browser_internal_pages(list(context.pages or []))
            if page is not excluding
        ]
        preferred = [page for page in usable if _is_onshape_app_url(_safe_page_url(page))]
        return (preferred or usable or [None])[0]

    def _prepare_page(self, page: Any):
        if _is_browser_internal_noise_url(_safe_page_url(page)):
            # Defensive: a downloads/hub target must never become the working
            # page. Close it and continue to a real page instead of probing it.
            _close_browser_internal_page(page)
            page = self._fallback_page(excluding=page)
            if page is None:
                raise BrowserLaunchError(
                    "Only browser-internal pages are open, so no Onshape page can "
                    "be adopted. Reopen the Onshape tab and retry, or run "
                    "browser_session action=login to sign in again."
                )
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

    @staticmethod
    def _new_page_selection(pages: Any) -> dict[str, Any]:
        """A fresh selection record for the pages about to be considered.

        `considered` counts every page handed to selection; `discarded` names the
        ones dropped before adoption and why, so a caller can see a closed tab
        instead of only its absence.
        """
        ordered = list(pages or [])
        selection: dict[str, Any] = {"considered": len(ordered), "discarded": [], "selected": None}
        for page in ordered:
            url = _safe_page_url(page)
            if _page_is_closed(page):
                selection["discarded"].append({"url": url, "reason": "closed"})
            elif _is_browser_internal_noise_url(url):
                selection["discarded"].append({"url": url, "reason": "browserInternal"})
        return selection

    @staticmethod
    def _discard_candidate(selection: dict[str, Any], page: Any, reason: str) -> None:
        selection["discarded"].append({"url": _safe_page_url(page), "reason": reason})

    def _record_selection(self, selection: dict[str, Any], selected: str | None) -> None:
        selection["selected"] = selected
        self.last_page_selection = selection

    def _adopt_candidate(self, candidates: Any, selection: dict[str, Any], *, probe: bool) -> Any:
        """Adopt the first usable candidate, or None when none can be adopted.

        Never adopts a closed page. Candidates are re-checked for liveness before
        the adopt call, and browser_common's `ResourceUnavailableError` -- raised
        when a page closed between selection and adoption -- advances to the next
        candidate instead of escaping. When `probe` is set, `page.evaluate("1 + 1")`
        is the same liveness probe the healthy path always used; a probe failure is
        NOT proof of death, so such a candidate stays in the fallback order until
        its own liveness read or adopt call says it closed.
        """
        from browser_common import ResourceUnavailableError
        fallbacks: list[Any] = []
        for candidate in candidates:
            if _page_is_closed(candidate):
                self._discard_candidate(selection, candidate, "closed")
                continue
            if probe:
                try:
                    candidate.evaluate("1 + 1")
                except Exception:
                    if _page_is_closed(candidate):
                        self._discard_candidate(selection, candidate, "closed")
                        continue
                    fallbacks.append(candidate)
                    continue
            try:
                return self._prepare_page(candidate)
            except ResourceUnavailableError:
                self._discard_candidate(selection, candidate, "closed")
                continue
        for candidate in fallbacks:
            try:
                return self._prepare_page(candidate)
            except ResourceUnavailableError:
                self._discard_candidate(selection, candidate, "closed")
                continue
        return None

    def start(self):
        """Explicit business recovery followed by native resource startup/reuse."""
        if self._resources is not None:
            state = self._resources.snapshot().state
            if self._temporary_depth:
                current = self.page
                if current is not None and _is_browser_internal_noise_url(_safe_page_url(current)):
                    # Never adopt a downloads target inside a temporary workflow;
                    # selecting a scope-owned popup instead would move ownership.
                    _close_browser_internal_page(current)
                    current = None
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
            selection = self._new_page_selection(ordered)
            live_pages = _dismiss_browser_internal_pages(ordered)
            preferred = [
                candidate for candidate in live_pages
                if _is_onshape_app_url(_safe_page_url(candidate))
            ]
            candidates = preferred + [
                p for p in live_pages if all(p is not preferred_page for preferred_page in preferred)
            ]
            chosen = self._adopt_candidate(candidates, selection, probe=True)
            if chosen is not None:
                self._record_selection(selection, "reused")
                return chosen
            # No candidate could be adopted: every one either closed during
            # selection or closed between the liveness read and adopt_page.
            # Adopting a closed page is exactly what browser_common refuses, so a
            # fresh page is the honest fallback.
            try:
                page = context.new_page()
            except Exception:
                self._record_selection(selection, None)
                if not self.close()["profileReleased"]:
                    raise BrowserLaunchError("Unreachable browser resources could not be released.")
            else:
                self._record_selection(selection, "new")
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
        # A browser-internal downloads page is closed here instead of adopted:
        # probing it with evaluate() is what wedges the page channel, and the
        # owner's restored-page fallback may well have selected it.
        ordered_pages = list(self.context.pages or [])
        selection = self._new_page_selection(ordered_pages)
        live_pages = _dismiss_browser_internal_pages(ordered_pages)
        chosen = next(
            (restored for restored in live_pages if _is_onshape_app_url(_safe_page_url(restored))),
            None,
        )
        if chosen is None and any(restored is page for restored in live_pages):
            chosen = page
        if chosen is None:
            chosen = live_pages[0] if live_pages else None
        if chosen is not None:
            # No evaluate probe here: this page came straight out of a freshly
            # started owner. Re-checking liveness and catching the adopt race is
            # still required, and a closed page falls through to a fresh one.
            adopted = self._adopt_candidate([chosen], selection, probe=False)
            if adopted is not None:
                self._record_selection(selection, "reused")
                return adopted
        self._record_selection(selection, "new")
        return self._prepare_page(self.context.new_page())

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

    def _resident_attached_mode(self) -> bool:
        """Whether this session's browser is an attached resident, not a launch.

        Residency is the ONE case where a truthful detach exists. `_make_resources`
        uses `resident_playwright_factory` only when `browser.resident` is enabled
        and no factory was injected, and that adapter ATTACHES over CDP to a
        browser a previous MCP child (or the human) already started
        (`onshape_browser_mode/resident.py`). On that connection `context.close()`
        detaches Playwright and leaves the browser, its tabs and its login running
        -- measured; see the resident module docstring -- so the single release API
        the pinned wheel exposes (`SyncSession.release()`) is already a detach.
        """
        try:
            resident = bool(getattr(self.config.browser, "resident", False))
        except Exception:
            return False
        # An explicitly injected factory wins over residency in `_make_resources`,
        # so a resident config plus an injected factory proves nothing.
        return resident and self._playwright_factory is None

    def detach(self, *, keep_browser: bool = True) -> dict[str, Any]:
        """Relinquish MCP ownership of an ATTACHED resident browser; never pretend.

        Honest cases, in order:

        * non-resident mode -- a keep-alive detach is structurally impossible
          here, and NOT merely missing from the pinned wheel (confirmed by the
          shared-library maintainers 2026-09-25). A `launch_persistent_context`
          browser is started with `--remote-debugging-pipe`, so the Playwright
          driver is its only owner: on exit the driver reaps the whole process
          tree (`killProcess()` is `taskkill /pid <pid> /T /F` on Windows,
          `process.kill(-pid, "SIGKILL")` on POSIX), and because that browser has
          no CDP endpoint it also cannot be re-attached afterwards. Nothing is
          changed and the caller is told so.
        * resident/attached mode -- `context.close()` on the adapter's attached
          default context detaches Playwright and leaves the browser, its tabs and
          its login alone. Ownership is released through the existing
          `SyncSession.release()` path, the profile is untouched, and the report
          names the browser as still running. If browser_common had to fall back to
          `browser.close()` the report says so instead of claiming survival.
        """
        if not self._resident_attached_mode():
            return {
                "detached": False,
                "supported": False,
                "keepBrowser": bool(keep_browser),
                "reason": (
                    "This MCP process launched its own browser over a DevTools "
                    "pipe, so the Playwright driver owns its whole process tree "
                    "(it reaps it with taskkill /T /F) and that browser has no CDP "
                    "endpoint to re-attach to, which makes a keep-alive detach "
                    "structurally impossible rather than merely absent from the "
                    "pinned wheel."
                ),
                "recommended": "browser_session action=release",
                "alternative": (
                    "enable browser.resident=true for a browser that survives the "
                    "MCP child (it is spawned detached with --remote-debugging-port "
                    "and ATTACHED over CDP, so releasing it is already a detach)"
                ),
                "sessionStatus": self._status,
            }
        if not keep_browser:
            return {
                "detached": False,
                "supported": False,
                "keepBrowser": False,
                "reason": (
                    "An attached resident browser outlives this MCP child by design "
                    "and the pinned wheel exposes no call that ends it from here, "
                    "so detach cannot deliver keep_browser=False."
                ),
                "recommended": "close the resident browser window (or end its process)",
                "alternative": "browser_session action=release only detaches the resident browser",
                "sessionStatus": self._status,
            }
        if self._resources is None:
            return {
                "detached": True,
                "alreadyDetached": True,
                "supported": True,
                "keepBrowser": True,
                "releaseMethod": "none",
                "contextClosed": False,
                "browserLeftRunning": None,
                "profileReleased": None,
                "previousSessionStatus": self._status,
                "sessionStatus": self._status,
                "profileDir": str(self.profile_dir()),
                "message": (
                    "This MCP process holds no browser resources, so there is no "
                    "attachment to relinquish. Whether a resident browser is still "
                    "running was NOT probed here."
                ),
            }
        report = self.close()
        fallback_used = report["releaseMethod"] == "browser.close-fallback"
        if not report["profileReleased"]:
            browser_left_running: bool | None = None
            context_closed: bool | None = None
        elif fallback_used:
            # browser_common fell back to `browser.close()`; over CDP that ends the
            # browser, so claiming it survived would be a lie.
            browser_left_running = False
            context_closed = True
        else:
            browser_left_running = True
            context_closed = False
        return {
            "detached": True,
            "supported": True,
            "keepBrowser": True,
            "releaseMethod": "detach",
            "contextClosed": context_closed,
            "browserLeftRunning": browser_left_running,
            "profileReleased": report["profileReleased"],
            "previousSessionStatus": report["previousSessionStatus"],
            "previousPageUrl": report["previousPageUrl"],
            "sessionStatus": report["sessionStatus"],
            "profileDir": report["profileDir"],
            "playwrightStopped": report["playwrightStopped"],
            "loginStateMayNeedRefresh": bool(fallback_used or not report["profileReleased"]),
            "warnings": report["warnings"],
            "message": (
                "MCP detached from the attached resident browser. The browser, its "
                "tabs and the profile's login survive; this process no longer owns "
                "them."
                if report["profileReleased"] and not fallback_used
                else "Detach was requested but browser survival could not be verified; "
                     "request Operator recovery."
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
                if _is_browser_internal_noise_url(_safe_page_url(probe)):
                    # A downloads page never answers a page-level read; probing it
                    # here would time out and prove nothing about the login state.
                    probe = None
                if probe is None:
                    probe = next(
                        (
                            p for p in context.pages
                            if not p.is_closed()
                            and not _is_browser_internal_noise_url(_safe_page_url(p))
                        ),
                        None,
                    )
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
                if _is_browser_internal_noise_url(url):
                    # Reported so the wedge is diagnosable; never a probe target.
                    pages_seen.append({"url": url, "browserInternal": True})
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
        profile = self.profile_dir()
        profile_bytes, profile_bytes_complete = _profile_dir_size_bytes(profile)
        # The same verdict vocabulary the health probe uses, applied to what this
        # process HOLDS. `sessionStatus` above is untouched; the verdict is additive.
        from onshape_browser_mode.health import classify_held_state
        held = classify_held_state(
            session_running=context is not None and any(
                not item.get("closed") for item in pages_seen
            ),
            on_onshape_app=_is_onshape_app_url(page_url),
            login_confirmed=self.login_confirmed,
            session_status=self._status,
        )
        return {
            "playwrightInstalled": self.playwright_available(),
            "configured": True,
            "profileDir": str(profile),
            "sessionStatus": self._status,
            "pageUrl": page_url,
            "pages": pages_seen,
            "headless": self.config.browser.headless,
            "humanActionRequired": self.human_action_required,
            "loginConfirmed": self.login_confirmed,
            "verdict": held["verdict"],
            "recommendedAction": held["recommendedAction"],
            "verdictNote": held["note"],
            "pageSelection": self.last_page_selection,
            # Bounded recursive size: `profileBytesComplete` is False once the file
            # cap is hit, so a capped number is never presented as exact.
            "profileBytes": profile_bytes,
            "profileBytesComplete": profile_bytes_complete,
            # Boolean only; account values are never read into the result.
            "accountMarkerDetected": _profile_account_marker(profile),
        }

    def health(self, *, probe_timeout_ms: int | None = None) -> dict[str, Any]:
        """Bounded read-only health probe; never starts, navigates, or clicks.

        `status` reports what this process HOLDS; this reports whether what it
        holds still answers, which is the question an idle session makes urgent.
        The session state fields are deliberately NOT rewritten here: a probe
        that also performs recovery cannot be used to decide whether recovery is
        needed. Findings and the fixed verdict vocabulary live in
        `onshape_browser_mode.health`.
        """
        from onshape_browser_mode.health import DEFAULT_PROBE_TIMEOUT_MS, probe_page, report

        context = self.context
        page = self.page
        pages_seen: list[dict[str, Any]] = []
        if context is not None:
            for candidate in list(context.pages or []):
                try:
                    if candidate.is_closed():
                        pages_seen.append({"closed": True})
                        continue
                    url = candidate.url
                except Exception:
                    pages_seen.append({"closed": True})
                    continue
                if _is_browser_internal_noise_url(url):
                    # A downloads page never answers a page-level read; probing it
                    # would time out and prove nothing about the login state.
                    pages_seen.append({"url": url, "browserInternal": True})
                    continue
                pages_seen.append({"url": url})
                if page is None:
                    page = candidate

        running = context is not None and page is not None
        if not running:
            evidence: dict[str, Any] = {
                "responded": None,
                "skipped": "no live working page is held by this MCP process",
            }
            page_url = None
        else:
            evidence = probe_page(
                page,
                timeout_ms=probe_timeout_ms or DEFAULT_PROBE_TIMEOUT_MS,
            )
            page_url = evidence.get("href") or _safe_page_url(page)
        normalized = (page_url or "").split("?", 1)[0].split("#", 1)[0].rstrip("/")
        on_onshape_app = _is_onshape_app_url(page_url)
        return report(
            evidence,
            session_running=running,
            on_onshape_app=on_onshape_app,
            # The sign-in page disproves sticky login history; nothing else does.
            login_confirmed=False if normalized == _SIGNIN_URL else (self.login_confirmed or on_onshape_app),
            session_status=self._status,
            page_url=page_url,
            pages_seen=pages_seen,
        )

    def open_login_page(self) -> dict[str, Any]:
        """Open sign-in only when restored/saved app entry cannot reuse login.

        Session-aware: after reusing a restored page or navigating to the saved
        last-document URL, landing on an application URL means the persistent
        profile still carried a live session, reported as
        ``alreadyAuthenticated``. Actually reaching ``/signin`` is reported as
        ``needsHumanLogin``. Both keys are additive; every existing key is kept.
        This adds no network layer -- it reuses `start()`, the saved URL and the
        same application-URL predicate the rest of the facade uses.
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
                "alreadyAuthenticated": True,
                "needsHumanLogin": False,
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
                        "alreadyAuthenticated": True,
                        "needsHumanLogin": False,
                        "message": f"Logged in via saved Onshape entry URL ({page.url}).",
                    }
            except Exception:
                pass
        page.goto(_SIGNIN_URL, wait_until="domcontentloaded", timeout=60_000)
        self._status = "awaiting_login"
        self.human_action_required = True
        return {
            "sessionStatus": self._status,
            "alreadyAuthenticated": False,
            "needsHumanLogin": True,
            # Issue #5, measured by the reporter and NOT fixable from here: the
            # Onshape sign-in page replaces its own document (`nav[0].type ==
            # "reload"`, a fresh `performance.timeOrigin`, `window` sentinels
            # gone) while the human is typing, with no agent action in between.
            # Anything typed is lost with the document, and the page's own
            # credential-step navigation (`/signin` -> `/signin?page=2&email=...`)
            # is a page-level navigation too. The server cannot prevent it or
            # recover the input, so it states the fact instead of implying that
            # reading the page while a human types is safe.
            "pageMaySelfReload": True,
            "humanInputAdvisory": (
                "Do not poll or read this page while the human types credentials or "
                "a 2FA code: the Onshape sign-in page reloads itself (measured), "
                "which discards typed input and all window-level state. Wait for the "
                "human to report completion, then use browser_session(action='health') "
                "rather than page reads to decide whether the session is live."
            ),
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
