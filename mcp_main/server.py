#!/usr/bin/env python3
"""Local stdio MCP server for the Branch Cable Trophy Onshape workflow."""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from onshape_docs.query import fs_reference, onshape_api_reference, onshape_api_docs, project_docs
from onshape_rest_api_mode.budget import live_blocker
from onshape_rest_api_mode.client import CREDENTIALS_PATH, STATE_PATH, load_json, parameter_payload
from onshape_rest_api_mode.operations import (
    api_usage,
    check_model,
    create_validation_part_studio,
    eval_featurescript,
    feature_studio_status,
    instantiate_feature,
    list_document_elements,
    load_parameter_set,
    PIPELINE_ESTIMATE,
    public_state,
    render_preview,
    run_validation_pipeline,
    upload_feature_studio,
)

SERVER_NAME = "onshape-branch-cable-trophy"
SERVER_VERSION = "1.3.0"
PROTOCOL_VERSION = "2025-06-18"


def object_schema(
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def mutating_confirmation() -> dict[str, Any]:
    return {
        "type": "boolean",
        "const": True,
        "description": "Must be true. This explicitly acknowledges the documented remote mutation.",
    }


PARAMETER_VALUE_SCHEMA = {
    "description": "A FeatureScript expression string, number, or boolean.",
    "oneOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "boolean"},
    ],
}
PARAMETER_SET_SCHEMA = {
    "type": "string",
    "enum": ["default", "preview"],
    "description": "default is detailed (132 parts); preview is simplified (65 parts).",
}
VIEW_SCHEMA = {
    "type": "string",
    "enum": ["front", "right", "top", "iso", "reference_like"],
}
MODE_SCHEMA = {"type": "string", "enum": ["detailed", "simplified"]}
FS_KIND_SCHEMA = {
    "type": "string",
    "enum": ["function", "type", "const", "predicate", "guide"],
    "description": (
        "function = callable FeatureScript function; type = type/enum definitions; "
        "const = named constant values; predicate = typecheck predicates; "
        "guide = language-guide sections (valid for fs_search only)."
    ),
}
GUIDE_PAGE_SCHEMA = {
    "type": "string",
    "enum": fs_reference.PAGES,
    "description": "One of the vendored FsDoc guide pages (intro, feature-types, modeling, ...).",
}


def _check_version(arguments: dict[str, Any]) -> dict[str, Any]:
    """Version check is offline; the live/latest probes are optional."""
    note = None
    # Free last-observed versions, captured from already-costly workflow
    # responses (feature specs' languageVersion, eval's libraryVersion). So the
    # docs-behind check works with ZERO quota until the caller opts into a
    # fresh live probe. See operations.record_observed_version.
    observed: dict[str, Any] = {}
    try:
        observed = load_json(STATE_PATH).get("observedServerVersion") or {}
    except Exception:
        pass
    live_version = observed.get("languageVersion")
    if arguments.get("include_live"):
        if not CREDENTIALS_PATH.is_file():
            note = "live check skipped: no credentials configured"
        else:
            blocker = live_blocker(2, "fs_check_version include_live")
            if blocker:
                note = f"live check skipped: {blocker}"
            else:
                try:
                    # Refreshes the cached version too (feature_studio_status records
                    # what it reads). languageVersion is the Feature Studio content's
                    # version; the deployed runtime (3044) is observed via eval.
                    live_version = feature_studio_status().get("languageVersion")
                except Exception as error:
                    note = f"live check failed: {type(error).__name__}: {error}"
    result = fs_reference.check_version(
        target=arguments.get("target"), live_version=live_version
    )
    result["lastObservedServerVersion"] = observed
    try:
        result["onshapeApiSpecVersion"] = onshape_api_reference.spec_version()
    except Exception as error:
        result["onshapeApiSpecVersion"] = {
            "note": f"REST API spec not indexed: {type(error).__name__}: {error}"
        }
    try:
        result["projectDocsHealth"] = project_docs.index_health()
    except Exception as error:
        result["projectDocsHealth"] = {
            "note": f"project docs index not built: {type(error).__name__}: {error}"
        }
    if arguments.get("check_latest"):
        try:
            latest = fs_reference.fetch_latest_mirror_version()
            result["latestAvailableVersion"] = latest["version"]
            result["latestAvailableLabel"] = latest["label"]
            vendored = result.get("vendoredVersion")
            result["updateAvailable"] = vendored is not None and latest["version"] > vendored
        except Exception as error:
            result["latestCheckNote"] = f"latest check failed: {type(error).__name__}: {error}"
        # REST API spec version probe (cheap /api/build call, needs credentials)
        if not CREDENTIALS_PATH.is_file():
            result["onshapeApiLatestCheckNote"] = (
                "REST spec latest check skipped: no credentials configured"
            )
        else:
            blocker = live_blocker(1, "fs_check_version check_latest REST probe")
            if blocker:
                result["onshapeApiLatestCheckNote"] = (
                    f"REST spec latest check skipped: {blocker}"
                )
            else:
                try:
                    rest_latest = onshape_api_reference.fetch_latest_version()
                    result["onshapeApiLatestVersion"] = rest_latest["version"]
                    vendored_rest = result.get("onshapeApiSpecVersion", {}).get("specVersion")
                    result["onshapeApiUpdateAvailable"] = (
                        bool(vendored_rest)
                        and onshape_api_reference.version_is_newer(
                            rest_latest["version"], vendored_rest
                        )
                    )
                except Exception as error:
                    result["onshapeApiLatestCheckNote"] = (
                        f"REST spec latest check failed: {type(error).__name__}: {error}"
                    )
    if note:
        result["liveCheckNote"] = note
    return result


def _update_reference(arguments: dict[str, Any]) -> dict[str, Any]:
    _confirm(arguments)
    include_api = bool(arguments.get("include_onshape_api", False))
    if include_api:
        # Re-fetching the live OpenAPI spec (onshape_docs/scripts/fetch_onshape_api.py)
        # costs 1 quota call; gate it like any other live request.
        _require_live(1, "fs_update_reference include_onshape_api")
    return fs_reference.update_reference(include_onshape_api=include_api)


def _local_state(arguments: dict[str, Any]) -> dict[str, Any]:
    state = load_json(STATE_PATH)
    return {
        "state": public_state(state, bool(arguments.get("redact_ids", False))),
        "credentialsConfigured": CREDENTIALS_PATH.is_file(),
    }


def _parameter_set(arguments: dict[str, Any]) -> dict[str, Any]:
    name = arguments["name"]
    return {"name": name, "parameters": load_parameter_set(name)}


def _parameter_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    parameters = arguments["parameters"]
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")
    return {"parameters": parameter_payload(parameters)}


def _render_preview(arguments: dict[str, Any]) -> dict[str, Any]:
    _require_live(1, "render_preview")
    result = render_preview(
        view=arguments["view"],
        width=int(arguments.get("width", 900)),
        height=int(arguments.get("height", 900)),
        save=bool(arguments.get("save", False)),
        part_studio_id=arguments.get("part_studio_id"),
    )
    include_image = bool(arguments.get("include_image", True))
    if not include_image:
        result.pop("base64", None)
    return result


def _confirm(arguments: dict[str, Any]) -> None:
    if arguments.get("confirm_mutation") is not True:
        raise ValueError("confirm_mutation must be true for this mutating tool")


def _require_live(estimate_calls: int, label: str) -> None:
    """Refuse a live request when the account is rate-limit held or the annual
    quota would be exceeded. The single gate every live tool checks BEFORE its
    first request."""
    blocker = live_blocker(estimate_calls, label)
    if blocker:
        raise ValueError(blocker)


def _preflight_or_raise(estimate_calls: int, label: str) -> None:
    _require_live(estimate_calls, label)


def _list_document_elements(arguments: dict[str, Any]) -> dict[str, Any]:
    """List workspace elements: cached (zero quota) by default, live on refresh."""
    refresh = bool(arguments.get("refresh", False))
    if refresh:
        _require_live(1, "list_document_elements")
    return list_document_elements(refresh=refresh)


def _upload(arguments: dict[str, Any]) -> dict[str, Any]:
    _confirm(arguments)
    if arguments.get("dry_run"):
        return upload_feature_studio(dry_run=True)
    _preflight_or_raise(3, "upload_feature_studio")
    return upload_feature_studio()


def _create_part_studio(arguments: dict[str, Any]) -> dict[str, Any]:
    _confirm(arguments)
    if arguments.get("dry_run"):
        return create_validation_part_studio(dry_run=True)
    _preflight_or_raise(1, "create_validation_part_studio")
    return create_validation_part_studio(
        name=arguments.get("name", "Cable trophy model validation"),
        save_to_project_state=bool(arguments.get("save_to_project_state", True)),
    )


def _instantiate(arguments: dict[str, Any]) -> dict[str, Any]:
    _confirm(arguments)
    overrides = arguments.get("overrides")
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("overrides must be an object")
    if arguments.get("dry_run"):
        return instantiate_feature(
            parameter_set=arguments.get("parameter_set", "default"),
            overrides=overrides,
            part_studio_id=arguments.get("part_studio_id"),
            dry_run=True,
        )
    _preflight_or_raise(2, "instantiate_feature")
    return instantiate_feature(
        parameter_set=arguments.get("parameter_set", "default"),
        overrides=overrides,
        part_studio_id=arguments.get("part_studio_id"),
    )


def _pipeline(arguments: dict[str, Any]) -> dict[str, Any]:
    _confirm(arguments)
    parameter_set = arguments.get("parameter_set", "default")
    render = bool(arguments.get("render_previews", True))
    if arguments.get("dry_run"):
        return run_validation_pipeline(
            parameter_set=parameter_set, render=render, dry_run=True,
        )
    _require_live(
        PIPELINE_ESTIMATE[render],
        f"validation pipeline (render={'on' if render else 'off'})",
    )
    return run_validation_pipeline(parameter_set=parameter_set, render=render)


def _browser_watch(arguments: dict[str, Any]) -> dict[str, Any]:
    """Record a human-operated Onshape browser session.

    Zero API quota. This tool manages an in-memory recorder that observes URL
    changes, page opens, network responses, and dialogs while the human clicks
    through the Onshape UI; the report helps turn observed behavior into a
    selector/action map.
    """
    from onshape_browser_mode.listener import get_recorder
    from onshape_browser_mode.session import get_session

    recorder = get_recorder()
    action = arguments.get("action", "status")
    if action == "status":
        return recorder.status()
    if action == "start":
        session = get_session()
        page = session.start()
        return recorder.start(page, session.context)
    if action == "stop":
        return recorder.stop()
    if action == "report":
        return recorder.report()
    raise ValueError("action must be 'start', 'status', 'stop', or 'report'")


def _browser_session(arguments: dict[str, Any]) -> dict[str, Any]:
    """Browser session status/login.

    This tool deliberately does NOT spend Onshape API quota. It starts or
    inspects the persistent Playwright browser profile; Playwright is imported
    lazily so the server still runs when the optional browser extra is missing.
    """
    from onshape_browser_mode.session import get_session

    action = arguments.get("action", "status")
    session = get_session()
    if action == "login":
        return session.open_login_page()
    if action == "status":
        return session.status()
    raise ValueError("action must be 'status' or 'login'")


def _browser_inspect(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read-only DOM inventory of the current Onshape page.

    Zero Onshape API quota: this only reads the live page's DOM through the
    persistent browser session. It lists visible interactive elements so a
    caller (or the dev/button-map workflow) can choose stable selectors without
    guessing, before any click/navigation is attempted.
    """
    from onshape_browser_mode.session import _is_onshape_app_url, get_session

    session = get_session()
    page = session.start()
    session._enforce_single_working_page(page)

    # If the working page is a leftover blank tab (not signin, not an app
    # page), try the saved Onshape entry URL before inspecting: cookies + entry
    # URL restore the logged-in page when the session is still valid.
    try:
        current_url = page.url
    except Exception:
        current_url = None
    if current_url and "about:blank" in current_url.lower():
        saved_url = session._load_saved_app_url()
        if saved_url:
            try:
                page.goto(saved_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(4000)
            except Exception:
                pass

    max_elements = arguments.get("max_elements", 100)
    if not isinstance(max_elements, int) or max_elements < 1:
        max_elements = 100
    max_elements = min(max_elements, 300)

    inventory = page.evaluate(
        """
        (maxElements) => {
          const selector = [
            'a', 'button', 'input', 'select', 'textarea', 'summary',
            '[role="button"]', '[role="link"]', '[role="menuitem"]',
            '[role="tab"]', '[role="treeitem"]', '[contenteditable="true"]',
            '[data-testid]', '[data-test]', '[aria-label]'
          ].join(',');
          const nodes = Array.from(document.querySelectorAll(selector));
          const out = [];
          const seen = new Set();
          for (const el of nodes) {
            const rect = el.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) continue;
            const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
            const item = {
              tag: el.tagName.toLowerCase(),
              text,
              type: el.getAttribute('type') || '',
              href: el.getAttribute('href') || '',
              aria: el.getAttribute('aria-label') || '',
              title: el.getAttribute('title') || '',
              role: el.getAttribute('role') || '',
              id: el.id || '',
              cls: (typeof el.className === 'string' ? el.className : '').slice(0, 120),
              dataTest: el.getAttribute('data-testid') || el.getAttribute('data-test') || ''
            };
            const key = JSON.stringify(item);
            if (seen.has(key)) continue;
            seen.add(key);
            out.push(item);
            if (out.length >= maxElements) break;
          }
          return {url: location.href, title: document.title, elements: out};
        }
        """,
        max_elements,
    )

    return {
        "pageUrl": inventory.get("url"),
        "title": inventory.get("title"),
        "elementCount": len(inventory.get("elements", [])),
        "elements": inventory.get("elements", []),
        "sessionPages": session.status().get("pages", []),
        "note": (
            "Read-only DOM inventory of the visible interactive elements. "
            "Prefer stable id/data-test/aria attributes over text or class "
            "when building selectors."
        ),
    }


def _browser_eval(arguments: dict[str, Any]) -> dict[str, Any]:
    """Run an arbitrary JavaScript expression in the current page.

    ``page.evaluate`` cannot be guaranteed read-only, so execution requires
    ``confirm_mutation=true``. ``dry_run=true`` (no confirmation needed) returns
    expression metadata without evaluating anything in the page.
    """
    expression = arguments.get("expression", "")
    if not expression:
        raise ValueError("Provide a JavaScript `expression`")

    if bool(arguments.get("dry_run", False)):
        return {
            "dryRun": True,
            "evaluated": False,
            "expressionLength": len(expression),
            "expressionHead": expression.strip()[:120],
            "argProvided": arguments.get("arg") is not None,
            "note": (
                "dry_run: the expression was NOT evaluated in the page. "
                "Set confirm_mutation=true (and omit dry_run) to actually run it."
            ),
        }

    # Execution is a possible remote UI mutation: require explicit confirmation.
    _confirm(arguments)

    from onshape_browser_mode.guard import get_guard
    from onshape_browser_mode.session import get_session

    session = get_session()
    page = session.start()
    session._enforce_single_working_page(page)

    get_guard().pace()

    arg = arguments.get("arg")
    try:
        result = page.evaluate(expression, arg) if arg is not None else page.evaluate(expression)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "result": result}


def _browser_scroll(arguments: dict[str, Any]) -> dict[str, Any]:
    """Scroll the current page (read-only; no Onshape API quota)."""
    from onshape_browser_mode.guard import get_guard
    from onshape_browser_mode.session import get_session

    session = get_session()
    page = session.start()
    session._enforce_single_working_page(page)

    direction = arguments.get("direction", "down")
    amount = arguments.get("amount", 800)
    selector = arguments.get("selector", "")
    if not isinstance(amount, (int, float)) or amount <= 0:
        amount = 800
    signed = -abs(amount) if direction == "up" else abs(amount)

    # A scroll is a real browser action: shape it through the same pacing gate
    # as clicks and eval (per-minute cap + randomized delay).
    get_guard().pace()

    result = page.evaluate(
        """
        ({selector, amount}) => {
          const el = selector ? document.querySelector(selector) : null;
          if (el) {
            const before = el.scrollTop;
            el.scrollTop += amount;
            return {
              target: 'element',
              scrolledBy: el.scrollTop - before,
              scrollTop: el.scrollTop,
              scrollHeight: el.scrollHeight,
              clientHeight: el.clientHeight,
            };
          }
          const before = window.scrollY;
          window.scrollBy(0, amount);
          return {
            target: 'window',
            scrolledBy: window.scrollY - before,
            scrollY: window.scrollY,
            scrollHeight: document.documentElement.scrollHeight,
            clientHeight: window.innerHeight,
          };
        }
        """,
        {"selector": selector, "amount": signed},
    )
    try:
        page.wait_for_timeout(400)
    except Exception:
        pass
    result["direction"] = direction
    result["pageUrl"] = page.url
    return result


def _browser_click(arguments: dict[str, Any]) -> dict[str, Any]:
    """Click a visible element by stable selector or text.

    A click may navigate or trigger a remote mutation in the Onshape document,
    so an actual click requires ``confirm_mutation=true``. ``dry_run=true`` may
    inspect the target without confirmation and reports what would be clicked
    without any click/scroll side effect. Always scrolls the target into view
    first on a real click.
    """
    from onshape_browser_mode.guard import get_guard
    from onshape_browser_mode.session import get_session

    selector = arguments.get("selector", "")
    text = arguments.get("text", "")
    index = arguments.get("index", 0)
    dry_run = bool(arguments.get("dry_run", False))
    if not isinstance(index, int) or index < 0:
        index = 0

    if not selector and not text:
        raise ValueError("Provide 'selector' or 'text' to click")

    # Dry-run inspection is allowed without confirmation; an actual click is a
    # possible remote UI mutation and must be explicitly acknowledged first.
    if not dry_run:
        _confirm(arguments)

    session = get_session()
    page = session.start()
    session._enforce_single_working_page(page)

    if text:
        locator = page.get_by_text(text, exact=False)
    else:
        locator = page.locator(selector)

    try:
        count = locator.count()
    except Exception:
        count = 0
    if count == 0:
        return {
            "clicked": False,
            "reason": "no matching element",
            "selector": selector,
            "text": text,
            "matchCount": 0,
            "pageUrl": page.url,
        }

    if index >= count:
        return {
            "clicked": False,
            "reason": f"index {index} >= matchCount {count}",
            "selector": selector,
            "text": text,
            "matchCount": count,
            "pageUrl": page.url,
        }

    target = locator.nth(index)
    try:
        info = target.evaluate(
            """el => ({
              tag: el.tagName.toLowerCase(),
              text: (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80),
              href: el.getAttribute('href') || '',
              aria: el.getAttribute('aria-label') || '',
              id: el.id || '',
              cls: (typeof el.className === 'string' ? el.className : '').slice(0, 100),
            })"""
        )
    except Exception as exc:
        return {
            "clicked": False,
            "reason": f"could not read target: {exc}",
            "matchCount": count,
            "pageUrl": page.url,
        }

    if dry_run:
        return {
            "dryRun": True,
            "wouldClick": info,
            "matchCount": count,
            "pageUrl": page.url,
        }

    # Pacing gate: enforce the per-minute cap and sleep a randomized delay
    # before the real click (no side effect on the dry-run path above).
    get_guard().pace()

    try:
        target.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        target.click()
        page.wait_for_timeout(2500)
    except Exception as exc:
        return {
            "clicked": False,
            "reason": f"click failed: {exc}",
            "element": info,
            "matchCount": count,
            "pageUrl": page.url,
        }

    try:
        current_url = page.url
    except Exception:
        current_url = None
    return {
        "clicked": True,
        "element": info,
        "matchCount": count,
        "pageUrl": current_url,
    }


def _browser_deploy_featurescript(arguments: dict[str, Any]) -> dict[str, Any]:
    """Deploy a FeatureScript script through the browser UI (0 Onshape API quota).

    ``dry_run=true`` is a pure local preview: it measures ONLY the submitted
    ``script`` argument and performs no browser-module import, session start,
    navigation, editor read/write, pacing, or click — so a dry run can never
    launch a browser or touch the page. ``dry_run=false`` (requires
    ``confirm_mutation=true``) opens the target document if needed, writes the
    Ace editor content, and clicks the FeatureScript Commit button — no REST API
    call is spent, and every real navigation/write/commit is shaped through the
    browser action guard's pacing gate.
    """
    script = arguments.get("script", "")
    if not isinstance(script, str) or not script.strip():
        raise ValueError("Provide a non-empty `script` string")
    document_name = arguments.get(
        "document_name", "Branch Cable Trophy Display - FeatureScript"
    )
    source_length = len(script)
    line_count = script.count("\n") + 1
    dry_run = bool(arguments.get("dry_run", False))

    # Pure local preview, returned before any browser import/session/action.
    if dry_run:
        return {
            "dryRun": True,
            "deployed": False,
            "documentName": document_name,
            "sourceLength": source_length,
            "lineCount": line_count,
            "note": (
                "dry_run: pure local preview — no browser session, navigation, "
                "editor read/write, pacing, or Commit click was performed. Set "
                "confirm_mutation=true with dry_run=false to deploy."
            ),
        }

    # Committing through the UI mutates the cloud document; require explicit
    # confirmation before any browser side effect — including the lazy browser
    # imports below, which a refused call must not even load.
    _confirm(arguments)

    from onshape_browser_mode import actions
    from onshape_browser_mode.guard import get_guard
    from onshape_browser_mode.session import get_session

    session = get_session()
    page = session.start()
    session._enforce_single_working_page(page)
    guard = get_guard()

    # A timed-out Onshape session shows a reconnect dialog over the editor;
    # recover first so the read/write below targets the live document.
    actions.reconnect_if_needed(page)

    before = actions.read_featurescript_editor(page)

    # If the FeatureScript editor is not on screen, open the target document.
    if before is None:
        guard.pace()  # navigation is a real browser action
        try:
            page.goto(
                session._load_saved_app_url() or "https://cad.onshape.com/documents",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            page.wait_for_timeout(4000)
        except Exception:
            pass
        if actions.read_featurescript_editor(page) is None and document_name:
            guard.pace()  # documents-list click is a real navigation action
            try:
                page.get_by_text(document_name, exact=False).first.click()
                page.wait_for_timeout(5000)
            except Exception:
                pass
        before = actions.read_featurescript_editor(page)

    if before is None:
        return {
            "deployed": False,
            "dryRun": False,
            "reason": "FeatureScript editor not found on the current page",
            "pageUrl": page.url,
        }

    guard.pace()  # the editor write is the actual remote mutation
    written = actions.write_featurescript_editor(page, script)
    if not written.get("ok"):
        return {
            "deployed": False,
            "dryRun": False,
            "reason": written.get("error", "could not write editor"),
            "pageUrl": page.url,
        }

    guard.pace()  # the Commit click finalizes the remote mutation
    commit = actions.click_commit(page)
    return {
        "deployed": bool(commit.get("clicked")),
        "dryRun": False,
        "pageUrl": page.url,
        "beforeLength": len(before),
        "afterLength": written.get("length"),
        "commit": commit,
    }


def _browser_reconnect(arguments: dict[str, Any]) -> dict[str, Any]:
    """Click the Onshape '重新连接' link if the session-timeout dialog is up."""
    from onshape_browser_mode import actions
    from onshape_browser_mode.guard import get_guard
    from onshape_browser_mode.session import get_session

    session = get_session()
    page = session.start()
    session._enforce_single_working_page(page)
    get_guard().pace()
    return actions.reconnect_if_needed(page)


def _browser_open_document(arguments: dict[str, Any]) -> dict[str, Any]:
    """Open a document from the documents list by name (read-only navigation)."""
    from onshape_browser_mode import actions
    from onshape_browser_mode.guard import get_guard
    from onshape_browser_mode.session import get_session

    document_name = arguments.get(
        "document_name", "Branch Cable Trophy Display - FeatureScript"
    )
    session = get_session()
    page = session.start()
    session._enforce_single_working_page(page)
    get_guard().pace()
    actions.reconnect_if_needed(page)
    return actions.open_document_by_name(
        page, document_name, session._load_saved_app_url()
    )


def _browser_read_featurescript(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read the current FeatureScript editor source (read-only, 0 quota)."""
    from onshape_browser_mode import actions
    from onshape_browser_mode.session import get_session

    session = get_session()
    page = session.start()
    session._enforce_single_working_page(page)
    actions.reconnect_if_needed(page)
    source = actions.read_featurescript_editor(page)
    if source is None:
        return {
            "read": False,
            "reason": "FeatureScript editor not open on the current page; use browser_open_document first",
            "pageUrl": page.url,
        }
    return {
        "read": True,
        "source": source,
        "length": len(source),
        "lineCount": source.count("\n") + 1,
        "pageUrl": page.url,
        **actions.parse_document_url(page.url),
    }


def _shutdown_browser_session() -> None:
    """Close the browser session, if one was started, when stdio disconnects.

    Each bridge connection gets a fresh MCP server child. On stdin EOF (the MCP
    client disconnected) that child must release the persistent Chrome profile,
    otherwise the next connection fails with a "profile is in use" lock. The
    import is lazy and the failure is swallowed: this must never turn a normal
    shutdown into a non-zero exit or extra protocol output.
    """
    try:
        import onshape_browser_mode.session as browser_session

        session = getattr(browser_session, "_session", None)
        if session is not None and session._status not in ("closed", "uninitialized"):
            session.close()
    except Exception:
        pass


# Session guard for the quota-costly eval tool: documents-first, eval sparingly.
EVAL_BUDGET_MAX = 10
_eval_budget_used = 0


def _eval_featurescript(arguments: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a FeatureScript snippet on the live server.

    Costs 1 API call every time. Guarded by (1) the rate-limit + quota
    preflight gate, (2) a per-session call budget (confirm_mutation=true to
    exceed it), and (3) a cost report in the response so the caller sees each
    call's quota impact.
    """
    global _eval_budget_used
    script = arguments.get("script")
    if not script or not isinstance(script, str) or not script.strip():
        raise ValueError("script must be a non-empty string")
    _require_live(1, "eval_featurescript")
    if _eval_budget_used >= EVAL_BUDGET_MAX and arguments.get("confirm_mutation") is not True:
        raise ValueError(
            f"eval has used {_eval_budget_used}/{EVAL_BUDGET_MAX} calls this session; "
            "pass confirm_mutation=true to spend beyond the session budget"
        )
    outcome = eval_featurescript(
        script,
        part_studio_id=arguments.get("part_studio_id"),
    )
    _eval_budget_used += 1
    usage = api_usage()
    return {
        "result": outcome,
        "evalCallsThisSession": _eval_budget_used,
        "evalBudgetMax": EVAL_BUDGET_MAX,
        "quota": {
            "consumed": usage.get("consumed"),
            "remaining": usage.get("remaining"),
            "annualLimit": usage.get("annualLimit"),
        },
    }


ToolHandler = Callable[[dict[str, Any]], Any]
TOOLS: list[dict[str, Any]] = [
    # --- FeatureScript reference tools (local, offline) ---------------------
    {
        "name": "fs_check_version",
        "cost": {"network": "live", "estimated_requests": 0, "max_requests": 3, "mutating": False, "cacheable": True},
        "description": (
            "Verify the vendored FeatureScript reference version and warn when it may be behind the "
            "version you are coding against. Reports the vendored reference version (parsed from the "
            "standard library), your target version, and the last FeatureScript version observed from "
            "already-costly workflow responses (free - captured from featurespecs languageVersion and "
            "eval libraryVersion, so no dedicated call). Pass include_live to refresh that from your "
            "Feature Studio (2 read-only calls, requires credentials). Returns a 'docs-behind' warning "
            "whenever a newer version is targeted, plus reference-health consistency checks. With "
            "check_latest it also probes the mirror (one small network call) for the newest available "
            "FeatureScript version and the live REST API spec version (needs credentials). Use it "
            "before writing code against a specific FeatureScript version. Also reports the health of "
            "the project-docs index (onshape_docs/index.json) vs its markdown sources."
        ),
        "inputSchema": object_schema({
            "target": {
                "type": "string",
                "description": "FeatureScript version you plan to compile against, e.g. '3029.0'.",
            },
            "include_live": {
                "type": "boolean",
                "default": False,
                "description": "Also refresh the observed FeatureScript version from the configured Feature Studio (read-only, requires credentials).",
            },
            "check_latest": {
                "type": "boolean",
                "default": False,
                "description": "Probe the mirror for the newest FeatureScript version and the live REST API spec version (needs credentials).",
            },
        }),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "fs_update_reference",
        "cost": {"network": "offline", "estimated_requests": 0, "max_requests": 1, "mutating": True, "cacheable": False},
        "description": (
            "Update the vendored FeatureScript reference from FREE sources only - the official FsDoc pages "
            "and the standard-library mirror (both public HTTP/GitHub, ZERO Onshape API quota). Re-fetches "
            "them and rebuilds index.json / guide.json / quick.json. Returns only a compact change summary "
            "(version before/after, counts and sample names of added/removed/changed functions) so the "
            "caller does not have to hold the delta in context - afterwards all fs_* lookup tools serve the "
            "fresh corpus. With include_onshape_api it also re-fetches the live Onshape REST API OpenAPI "
            "spec and the auth/error docs and rebuilds the onshape_api_* indexes (that REST fetch needs "
            "credentials and costs 1 quota call; without it that part is skipped with a note). "
            "Note: it does NOT detect the live FeatureScript server version - that check costs quota, so it "
            "lives in fs_check_version's include_live (which already spends a call), not here. "
            "This performs network downloads and overwrites files under onshape_docs/reference/, so it requires "
            "confirm_mutation=true."
        ),
        "inputSchema": object_schema({
            "confirm_mutation": mutating_confirmation(),
            "include_onshape_api": {
                "type": "boolean",
                "default": False,
                "description": "Also refresh the Onshape REST API OpenAPI spec (needs credentials).",
            },
        }, ["confirm_mutation"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "fs_quick_reference",
        "description": (
            "Return the curated FeatureScript quick-reference digest (onshape_docs/reference/quick-reference.md): a "
            "distilled cheat-sheet covering the language model, feature anatomy, parameters, queries, the "
            "standard library map, common patterns, and pitfalls. Small enough to load into context in one "
            "call; use it to orient before drilling into fs_get_function/fs_guide_section. Local and offline."
        ),
        "inputSchema": object_schema(),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "fs_list_modules",
        "description": (
            "List the FeatureScript standard library modules (geometry.fs, query.fs, sweep.fs, ...), "
            "grouped by the reference site's categories (Modeling, Math, Onshape features, Utilities, "
            "enums). Optionally filter to one category. Local and offline; useful before looking up "
            "functions so you know which module to search."
        ),
        "inputSchema": object_schema({
            "category": {"type": "string", "description": "Optional category filter (exact case-insensitive)."},
        }),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "fs_list_functions",
        "description": (
            "List FeatureScript functions (or types/constants/predicates when kind is set), each with its "
            "module, signature, and one-line summary. Filter by module, category, kind, or a name prefix, "
            "and cap the result with limit. Local and offline."
        ),
        "inputSchema": object_schema({
            "module": {"type": "string", "description": "Optional module file (e.g. 'sweep' or 'sweep.fs')."},
            "category": {"type": "string"},
            "kind": FS_KIND_SCHEMA,
            "prefix": {"type": "string", "description": "Only names starting with this prefix (case-insensitive)."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
        }),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "fs_get_function",
        "description": (
            "Return the full reference entry for one FeatureScript function: exact signature, every "
            "parameter with its type, requirement (Optional / Required), description and example, plus the "
            "return type and module. FeatureScript overloads a name with several signatures — when the "
            "name has multiple signatures in one module, ALL of them are returned as an 'overloads' list "
            "(each with parameters/description) so you can pick by exact signature. Constants and "
            "typecheck predicates are also addressable via kind. Local and offline."
        ),
        "inputSchema": object_schema({
            "name": {"type": "string"},
            "module": {"type": "string", "description": "Disambiguate when the name exists in several modules."},
            "kind": FS_KIND_SCHEMA,
        }, ["name"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "fs_get_type",
        "description": (
            "Return the full definition of a FeatureScript type or enum (for example BoundingType, Query, "
            "EntityType): its kind, description, and each allowed value with type and description. Use it "
            "when a function parameter references a type you need to understand. Local and offline."
        ),
        "inputSchema": object_schema({
            "name": {"type": "string"},
            "module": {"type": "string"},
        }, ["name"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "fs_search",
        "description": (
            "Keyword search across every FeatureScript function, type, constant, predicate, and "
            "language-guide section in the vendored reference. Results are ranked by how strongly the "
            "query tokens match the name, signature, parameter types, and description. Use this when you "
            "know roughly what you want but not the exact name (for example 'sketch region extrude'). "
            "Local and offline."
        ),
        "inputSchema": object_schema({
            "query": {"type": "string"},
            "module": {"type": "string"},
            "category": {"type": "string"},
            "kind": FS_KIND_SCHEMA,
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        }, ["query"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "fs_guide_section",
        "description": (
            "Return a section of the official FeatureScript language guide as plain text, with code blocks "
            "fenced. Omit 'section' to get the whole page plus its heading outline; pass a section title to "
            "narrow to one heading (matching is case-insensitive substring). Use this for language concepts "
            "(feature types, the UI specification, queries, modeling) rather than individual functions. "
            "Local and offline."
        ),
        "inputSchema": object_schema({
            "page": GUIDE_PAGE_SCHEMA,
            "section": {"type": "string", "description": "Optional heading to narrow to."},
        }, ["page"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "fs_library_source",
        "description": (
            "Return the actual FeatureScript standard library source for a module (for example 'geometry', "
            "'query', 'sweep') from the vendored mirror. With 'function' set, returns only the window "
            "around that function's definition plus its usage line numbers. The real implementation is the "
            "highest-fidelity reference for how Onshape writes FeatureScript. Local and offline."
        ),
        "inputSchema": object_schema({
            "module": {"type": "string"},
            "function": {"type": "string", "description": "Optional; extract the definition window for this function."},
        }, ["module"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    # --- Project docs tools (local, offline; the project's own LLM docs) ---
    {
        "name": "docs_list",
        "description": (
            "List every page in the project's own structured documentation index (onshape_docs/index.json, built "
            "from onshape_docs/guide/*.md, onshape_docs/reference/quick-reference.md, and the example docs; the root README is the "
            "human landing page and is intentionally not indexed): each page's "
            "title, source path, and heading-section outline. Use it to see what project docs exist and "
            "their section titles, then read one with docs_section. This is separate from the vendored "
            "Onshape reference (fs_* / onshape_api_* tools). Local and offline."
        ),
        "inputSchema": object_schema(),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "docs_section",
        "description": (
            "Read the project's own documentation (onshape_docs/guide/mcp-server.md, onshape_docs/guide/fs-assistant.md, the "
            "verified LLM-experience docs, the example docs) as plain text. Pass page=<page> and optionally "
            "section=<heading> to narrow to one section; without section you get the whole page plus its "
            "heading outline. This is how the project's own knowledge (tool catalog, workflows, live "
            "verification lessons) is read on demand from onshape_docs/index.json. Local and offline."
        ),
        "inputSchema": object_schema({
            "page": {"type": "string", "description": "A project doc page, e.g. 'llm-experience-fs', 'mcp-server', 'quick-reference'. See docs_list for the full list."},
            "section": {"type": "string", "description": "Optional heading to narrow to (case-insensitive substring)."},
        }, ["page"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "docs_search",
        "description": (
            "Keyword search across every section of the project's own documentation (onshape_docs/guide/*, "
            "onshape_docs/reference/quick-reference.md, example docs). Results are ranked by how well the query tokens "
            "match the page/section titles and body text. Use this to find which project doc answers a "
            "question (e.g. 'quota', 'eval budget', 'defineFeature'), then read the full section with "
            "docs_section. Local and offline."
        ),
        "inputSchema": object_schema({
            "query": {"type": "string"},
            "page": {"type": "string", "description": "Optional: restrict the search to one page (see docs_list)."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        }, ["query"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    # --- Onshape REST API reference tools (local, offline) -----------------
    {
        "name": "onshape_api_list_tags",
        "description": (
            "List every domain group (tag) in the Onshape REST API with its one-line description: "
            "Account, Assembly, Document, Element, FeatureStudio, PartStudio, ... Use it to orient "
            "before onshape_api_search so you can narrow by tag. Local and offline (reads the vendored "
            "OpenAPI index); reports the REST API spec version it describes."
        ),
        "inputSchema": object_schema(),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_api_search",
        "description": (
            "Keyword search across every Onshape REST API endpoint (method + path + operationId + "
            "summary + description), ranked by match strength. Returns method, path, operationId, and "
            "summary so you can pick the endpoint that does what you want, then drill in with "
            "onshape_api_endpoint. Optionally filter to one tag (see onshape_api_list_tags). Local and "
            "offline."
        ),
        "inputSchema": object_schema({
            "query": {"type": "string", "description": "e.g. 'list document elements', 'create part studio', 'get mass properties'."},
            "tag": {"type": "string", "description": "Optional tag filter (case-insensitive, e.g. 'Document')."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        }, ["query"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_api_endpoint",
        "description": (
            "Return the full definition of one Onshape REST API operation: method, path, operationId, "
            "summary, description, every parameter (name, location path/query/header, required, type, "
            "enum/default, description), and the response status codes with their schema references. "
            "Pass method to pick one operation on a path; without it, the path's methods are listed. "
            "Schema references in parameters/responses (e.g. 'BTDocumentElementInfo') are looked up "
            "with onshape_api_schema. Local and offline."
        ),
        "inputSchema": object_schema({
            "path": {"type": "string", "description": "Exact endpoint path, e.g. '/documents/d/{did}/{wvm}/{wvmid}/elements'."},
            "method": {"type": "string", "description": "Optional: get / post / put / delete / patch. Omit to list methods on the path."},
        }, ["path"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_api_schema",
        "description": (
            "Return a schema definition from the Onshape REST API (a response or request type, e.g. "
            "BTDocumentElementInfo, BTMassProperties, BTObjectId): its type, description, required "
            "fields, and each property with its type/ref/description. Use it after onshape_api_endpoint "
            "tells you a parameter or response references this schema. Local and offline."
        ),
        "inputSchema": object_schema({
            "name": {"type": "string", "description": "Schema name, e.g. 'BTDocumentElementInfo'."},
        }, ["name"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_api_auth",
        "description": (
            "Onshape authentication reference: the OAuth2 authorization-code workflow (register app, "
            "authorize, exchange code for token, use, refresh) and API-key usage (Basic auth). Without a "
            "section it returns a distilled summary - workflow step titles with their opening summaries - "
            "plus the API-key steps. Pass section=<title> to get the full text of one step, including code. "
            "Local and offline (from vendored official docs)."
        ),
        "inputSchema": object_schema({
            "section": {"type": "string", "description": "Optional: a step/section title, e.g. '3: Exchange the code for an access token'."},
        }),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_api_error_codes",
        "description": (
            "Onshape REST HTTP response codes and API call limits: every code (200-503) with its category, "
            "description and recommended next steps, plus the rate-limit / annual-limit semantics (including "
            "the X-Rate-Limit-Remaining and Retry-After headers on 429). Pass status=<code> to narrow to one "
            "error. Use it when an onshape_* REST call returns a non-2xx. Local and offline."
        ),
        "inputSchema": object_schema({
            "status": {"type": "integer", "description": "Optional: one status code to expand, e.g. 429."},
        }),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_get_project_state",
        "description": (
            "Read the project's non-secret Onshape document/workspace/element configuration and report "
            "whether a credentials file is configured. This is a local operation: it does not read or "
            "return credential values and makes no network request. Use it to understand which existing "
            "Feature Studio and Part Studio subsequent tools target."
        ),
        "inputSchema": object_schema({
            "redact_ids": {
                "type": "boolean",
                "default": False,
                "description": "Mask most characters of document, workspace, and element IDs.",
            }
        }),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_get_parameter_set",
        "description": (
            "Read one maintained local parameter set for the Branch Cable Trophy FeatureScript. "
            "The default set produces the detailed 132-part model; preview produces the simplified "
            "65-part model. This does not read credentials or contact Onshape."
        ),
        "inputSchema": object_schema({"name": PARAMETER_SET_SCHEMA}, ["name"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_build_parameter_payload",
        "description": (
            "Convert a local parameter mapping into Onshape's explicit custom-feature parameter blocks. "
            "Booleans become BTMParameterBoolean values; strings and numbers become quantity expressions. "
            "This deterministic local helper makes no network request and does not validate FeatureScript bounds."
        ),
        "inputSchema": object_schema({
            "parameters": {
                "type": "object",
                "additionalProperties": PARAMETER_VALUE_SCHEMA,
                "description": "FeatureScript parameter IDs mapped to expressions or booleans.",
            }
        }, ["parameters"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_api_quota",
        "cost": {"network": "offline", "estimated_requests": 0, "max_requests": 0, "mutating": False, "cacheable": True},
        "description": (
            "Report the local API-quota budget: the annual call limit (from apiQuota in "
            "config/onshape-state.json), calls consumed so far (local ledger of 2xx/3xx responses), the "
            "remaining budget, and how many full validation-pipeline runs that fits (with and without "
            "rendering). Also surfaces the latest X-Rate-Limit-Remaining header and any 402 "
            "(annual-limit-exhausted) signal. Zero network cost: Onshape has no public quota endpoint, so "
            "this is passive bookkeeping from responses already received - it does not spend API quota. "
            "Use it before onshape_run_validation_pipeline, which blocks if the budget is insufficient."
        ),
        "inputSchema": object_schema(),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_eval_featurescript",
        "cost": {"network": "live", "estimated_requests": 1, "max_requests": 1, "mutating": False, "cacheable": True},
        "description": (
            "Evaluate a FeatureScript snippet on the live Onshape server. ⚠️ Each call spends 1 API call "
            "of the annual quota. Document-first discipline: BEFORE calling this, use the free local tools "
            "(fs_get_function, fs_search, fs_library_source, fs_quick_reference) which answer from the "
            "vendored docs at zero cost; call this only when (a) the vendored docs lack the symbol, "
            "(b) a documented signature conflicts with what you need, or (c) you must confirm version-"
            "specific behavior the 2960 docs do not cover (the live server is currently FeatureScript "
            "3044). The script MUST evaluate to a two-argument anonymous function the server calls with "
            "(context, id), e.g. 'function(context is Context, id is Id) { return 5; }'. Three guards: "
            "the rate-limit + annual-quota gate blocks when the account is rate-limit held or quota is low; "
            "a 10-call-per-session budget (confirm_mutation=true to exceed); and the response reports "
            "consumed/remaining so the cost of every call is visible. "
            "Returns console output, compile errors/warnings, and the flattened result value."
        ),
        "inputSchema": object_schema({
            "script": {
                "type": "string",
                "description": "FeatureScript snippet evaluating to a two-argument anonymous function, e.g. 'function(context is Context, id is Id) { return evBoundingBox(context, qEverything(EntityType.BODY)); }'",
            },
            "part_studio_id": {
                "type": "string",
                "description": "Optional Part Studio element id to evaluate against; defaults to the configured partStudioId.",
            },
            "confirm_mutation": {
                "type": "boolean",
                "description": "set true to allow spending beyond the 10-call-per-session eval budget.",
            },
        }, ["script"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_list_document_elements",
        "cost": {"network": "live", "estimated_requests": 0, "max_requests": 1, "mutating": False, "cacheable": True},
        "description": (
            "List elements in the configured Onshape workspace (names, element types, IDs, microversions). "
            "By default it returns the locally cached element table at ZERO API cost — that table is populated "
            "and kept current by upload/create/status operations and by explicit refreshes. Pass refresh=true "
            "to make one authenticated read-only GET /elements and repopulate the cache. Use this to inspect "
            "workspace state before choosing a Feature Studio or Part Studio operation. "
            "Returns {source: 'cache'|'live', elements: [...], cacheTimestamp, documentId, workspaceId}; "
            "source is 'cache' whenever no network call was made (an empty elements list with a note means "
            "the mirror is not populated yet)."
        ),
        "inputSchema": object_schema({
            "refresh": {
                "type": "boolean",
                "default": False,
                "description": "Re-fetch the live workspace elements (1 API call) and update the local cache. Default false returns the cached table at zero cost.",
            },
        }),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "onshape_get_feature_studio_status",
        "cost": {"network": "live", "estimated_requests": 2, "max_requests": 2, "mutating": False, "cacheable": False},
        "description": (
            "Read the configured Feature Studio metadata and compiled feature specifications. It reports "
            "whether branchCableTrophyDisplay is exposed and how many parameters its compiled specification "
            "contains. This uses authenticated read-only Onshape requests and does not upload source. It also "
            "rolls the Feature Studio's current microversion into the local element mirror (a zero-quota local "
            "write), which is what keeps the cached element table trustworthy for follow-up operations."
        ),
        "inputSchema": object_schema(),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "onshape_check_model",
        "cost": {"network": "live", "estimated_requests": 3, "max_requests": 3, "mutating": False, "cacheable": False},
        "description": (
            "Validate an existing Part Studio through read-only Onshape requests. The result checks custom "
            "feature status, exact part count, required part-name prefixes, and bounding limits; it returns "
            "all invariant errors without changing the Part Studio or writing the project report file."
        ),
        "inputSchema": object_schema({
            "mode": {**MODE_SCHEMA, "default": "detailed"},
            "part_studio_id": {
                "type": "string",
                "description": "Optional target override; defaults to config/onshape-state.json.",
            },
        }),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "onshape_render_preview",
        "cost": {"network": "live", "estimated_requests": 1, "max_requests": 1, "mutating": False, "cacheable": True},
        "description": (
            "Request one shaded PNG rendering of the existing configured Part Studio from Onshape. The remote "
            "operation is read-only but may consume rendering resources. By default it returns the image as MCP "
            "image content without writing a file; set save=true to also write outputs/previews/<view>.png."
        ),
        "inputSchema": object_schema({
            "view": VIEW_SCHEMA,
            "width": {"type": "integer", "minimum": 64, "maximum": 2000, "default": 900},
            "height": {"type": "integer", "minimum": 64, "maximum": 2000, "default": 900},
            "include_image": {
                "type": "boolean",
                "default": True,
                "description": "Return the PNG as MCP image content in addition to metadata.",
            },
            "save": {
                "type": "boolean",
                "default": False,
                "description": "Also save the PNG under outputs/previews; this is a local file write.",
            },
            "part_studio_id": {"type": "string"},
        }, ["view"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "onshape_upload_feature_studio",
        "cost": {"network": "live", "estimated_requests": 3, "max_requests": 3, "mutating": True, "cacheable": False},
        "description": (
            "Upload branchCableTrophyDisplay.fs to the configured Feature Studio and require the compiled "
            "branchCableTrophyDisplay specification. This overwrites cloud Feature Studio contents and may "
            "fail on microversion skew; call only when the user intends that remote mutation. Costs 3 API "
            "calls (GET + POST + GET featurespecs); run onshape_docs/scripts/fs_local_check.py on the source first. "
            "Pass dry_run=true to see the exact requests without sending them."
        ),
        "inputSchema": object_schema({
            "confirm_mutation": mutating_confirmation(),
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "Construct and return the exact requests (method/URL/body) without sending them.",
            },
        }, ["confirm_mutation"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "onshape_create_validation_part_studio",
        "cost": {"network": "live", "estimated_requests": 1, "max_requests": 1, "mutating": True, "cacheable": False},
        "description": (
            "Create a new Part Studio in the configured Onshape document. Each call creates another cloud "
            "element; by default it also changes config/onshape-state.json to target the new element. This is "
            "not a read-only inspection tool and requires explicit mutation confirmation."
        ),
        "inputSchema": object_schema({
            "confirm_mutation": mutating_confirmation(),
            "name": {"type": "string", "default": "Cable trophy model validation"},
            "save_to_project_state": {"type": "boolean", "default": True},
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "Construct and return the exact request (method/URL/body) without sending it.",
            },
        }, ["confirm_mutation"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    },
    {
        "name": "onshape_instantiate_feature",
        "cost": {"network": "live", "estimated_requests": 1, "max_requests": 2, "mutating": True, "cacheable": False},
        "description": (
            "Add the Branch Cable Trophy custom feature to a target Part Studio using a maintained explicit "
            "parameter set and optional known-parameter overrides. Repeated calls add additional cloud features; "
            "this requires explicit mutation confirmation and returns the regeneration status. Costs 1 call when "
            "the Feature Studio microversion is threaded from a just-finished upload or read from an element "
            "mirror synced within the last 5 minutes; 2 when the mirror is stale or empty and the current "
            "microversion must be re-read from the element list. A stale microversion silently instantiates the "
            "OLD Feature Studio definition, so tell the human not to edit the Feature Studio in the Onshape UI "
            "between an upload/status and this call; prefer the pipeline, which threads the fresh microversion."
        ),
        "inputSchema": object_schema({
            "confirm_mutation": mutating_confirmation(),
            "parameter_set": {**PARAMETER_SET_SCHEMA, "default": "default"},
            "overrides": {
                "type": "object",
                "additionalProperties": PARAMETER_VALUE_SCHEMA,
                "description": "Optional overrides; unknown parameter IDs are rejected.",
            },
            "part_studio_id": {"type": "string"},
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "Construct and return the exact requests (method/URL/body) without sending them.",
            },
        }, ["confirm_mutation"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    },
    {
        "name": "onshape_run_validation_pipeline",
        "cost": {"network": "live", "estimated_requests": 8, "max_requests": 13, "mutating": True, "cacheable": False},
        "description": (
            "Run the complete remote validation pipeline: upload FeatureScript, create a new Part Studio, save "
            "that ID to local project state, instantiate the feature, validate invariants, and optionally render "
            "five PNG previews. This performs several cloud and local mutations and requires explicit confirmation. "
            "Before any call is made it checks the local API-quota budget (~13 calls with render, ~8 without; see "
            "onshape_api_quota) and blocks with the shortfall if the annual limit would be exceeded."
        ),
        "inputSchema": object_schema({
            "confirm_mutation": mutating_confirmation(),
            "parameter_set": {**PARAMETER_SET_SCHEMA, "default": "default"},
            "render_previews": {"type": "boolean", "default": True},
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "Describe the full pipeline's requests (method/URL/body) without sending them.",
            },
        }, ["confirm_mutation"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    },
    {
        "name": "browser_session",
        "cost": {
            "backend": "browser",
            "network": "browser",
            "estimated_requests": 0,
            "max_requests": 0,
            "estimated_api_requests": 0,
            "max_api_requests": 0,
            "estimated_seconds": 15,
            "requires_browser_session": True,
            "mutating": False,
            "cacheable": False,
        },
        "description": (
            "Inspect or establish the persistent Onshape browser session used by the browser_* tools. "
            "action='status' reports whether Playwright is installed, the persistent profile directory, "
            "the browser session state, and the current page URL — zero Onshape API quota. "
            "action='login' opens the visible browser at the Onshape sign-in page and asks the human to "
            "complete login (SSO/2FA are never automated); the resulting profile is reused by later "
            "browser_* calls. The browser runs on the Windows host (see tools/windows/README.md); the "
            "Linux side only relays MCP stdio over the loopback bridge. If Playwright is not installed "
            "on the Windows host, this tool returns a clear setup error instead of failing the MCP server."
        ),
        "inputSchema": object_schema({
            "action": {
                "type": "string",
                "enum": ["status", "login"],
                "default": "status",
                "description": "status = read-only session report; login = open Onshape sign-in for the human.",
            },
        }),
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "browser_watch",
        "cost": {
            "backend": "browser",
            "network": "browser",
            "estimated_requests": 0,
            "max_requests": 0,
            "estimated_api_requests": 0,
            "max_api_requests": 0,
            "estimated_seconds": 10,
            "requires_browser_session": True,
            "mutating": False,
            "cacheable": False,
        },
        "description": (
            "Record a human-operated Onshape browser session to learn what UI actions do, without spending "
            "Onshape API quota. action='start' opens the persistent browser and begins recording page opens, "
            "URL changes, network responses (URL pattern/method/status/content-type), and dialogs; "
            "action='status' reports the recorder state; action='stop' stops recording and returns the report; "
            "action='report' returns the aggregated report. The report is the input for building the "
            "dev/button-map selector/action mapping — combine it with onshape_docs/guide documentation before "
            "adding a selector to onshape_browser_mode/selectors.py. The browser runs on the Windows host; "
            "if Playwright is missing there, action='start' returns a clear setup error."
        ),
        "inputSchema": object_schema({
            "action": {
                "type": "string",
                "enum": ["start", "status", "stop", "report"],
                "default": "status",
                "description": "start = begin recording; status = recorder state; stop = stop and report; report = aggregated report.",
            },
        }),
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "browser_inspect",
        "cost": {
            "backend": "browser",
            "network": "browser",
            "estimated_requests": 0,
            "max_requests": 0,
            "estimated_api_requests": 0,
            "max_api_requests": 0,
            "estimated_seconds": 10,
            "requires_browser_session": True,
            "mutating": False,
            "cacheable": False,
        },
        "description": (
            "Read-only inventory of the visible interactive elements on the current Onshape browser page: "
            "links, buttons, inputs, menus, tabs, and anything with an aria-label / data-testid. Returns the "
            "page URL/title and up to `max_elements` elements with their tag, text, href, aria, title, role, "
            "id, class, and data-test attributes. Zero Onshape API quota — this only reads the live DOM. "
            "Use it to discover what is clickable before adding selectors to dev/button-map."
        ),
        "inputSchema": object_schema({
            "max_elements": {
                "type": "integer",
                "default": 100,
                "description": "Maximum number of unique visible interactive elements to return (1-300).",
            },
        }),
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "browser_scroll",
        "cost": {
            "backend": "browser",
            "network": "browser",
            "estimated_requests": 0,
            "max_requests": 0,
            "estimated_api_requests": 0,
            "max_api_requests": 0,
            "estimated_seconds": 5,
            "requires_browser_session": True,
            "mutating": False,
            "cacheable": False,
        },
        "description": (
            "Scroll the current Onshape browser page up/down, either the whole window or a specific element "
            "matched by a CSS selector. Returns how far it actually scrolled plus the container's scroll "
            "geometry. Zero Onshape API quota — this only drives the visible browser viewport, which is "
            "needed to discover documents/rows below the fold (Onshape lazy-renders long lists)."
        ),
        "inputSchema": object_schema({
            "direction": {
                "type": "string",
                "enum": ["down", "up"],
                "default": "down",
                "description": "Scroll direction.",
            },
            "amount": {
                "type": "integer",
                "default": 800,
                "description": "Pixels to scroll (positive; direction chooses the sign).",
            },
            "selector": {
                "type": "string",
                "default": "",
                "description": "Optional CSS selector of the scrollable container; empty scrolls the window.",
            },
        }),
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "browser_click",
        "cost": {
            "backend": "browser",
            "network": "browser",
            "estimated_requests": 0,
            "max_requests": 0,
            "estimated_api_requests": 0,
            "max_api_requests": 0,
            "estimated_seconds": 10,
            "requires_browser_session": True,
            "mutating": True,
            "remote_ui_mutation": "possible",
            "cacheable": False,
        },
        "description": (
            "Click a visible element in the Onshape browser by CSS selector or by visible text (optionally "
            "`index` to pick among matches). Scrolls the target into view first. A click may navigate or "
            "trigger a remote mutation in the Onshape document, so an actual click requires "
            "confirm_mutation=true. With `dry_run=true` (no confirmation needed) it only inspects and "
            "reports what WOULD be clicked without any click/scroll side effect. Drives the browser UI "
            "only — it never calls the Onshape REST API (0 developer API requests) — but the clicked "
            "control may itself change the cloud document."
        ),
        "inputSchema": object_schema({
            "selector": {
                "type": "string",
                "default": "",
                "description": "CSS selector to click; used when `text` is empty.",
            },
            "text": {
                "type": "string",
                "default": "",
                "description": "Visible text of the element to click; used when `selector` is empty.",
            },
            "index": {
                "type": "integer",
                "default": 0,
                "description": "Which matching element to click (0-based).",
            },
            "confirm_mutation": mutating_confirmation(),
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "Report the target without actually clicking; needs no confirm_mutation.",
            },
        }),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    },
    {
        "name": "browser_eval",
        "cost": {
            "backend": "browser",
            "network": "browser",
            "estimated_requests": 0,
            "max_requests": 0,
            "estimated_api_requests": 0,
            "max_api_requests": 0,
            "estimated_seconds": 5,
            "requires_browser_session": True,
            "mutating": True,
            "remote_ui_mutation": "possible",
            "cacheable": False,
        },
        "description": (
            "Evaluate an arbitrary JavaScript expression in the current Onshape page and return its "
            "JSON-serializable result. page.evaluate cannot be guaranteed read-only, so actual execution "
            "requires confirm_mutation=true; with `dry_run=true` (no confirmation needed) it only returns "
            "expression metadata (length / preview / argument presence) WITHOUT evaluating anything in the "
            "page. Zero Onshape REST API requests — the expression runs in the page context and may mutate "
            "the document the same way any UI action could."
        ),
        "inputSchema": object_schema({
            "expression": {
                "type": "string",
                "description": "JavaScript expression to evaluate in the page (e.g. a function that returns data).",
            },
            "arg": {
                "description": "Optional JSON value passed to the expression as its argument.",
            },
            "confirm_mutation": mutating_confirmation(),
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "Return expression metadata without evaluating anything in the page.",
            },
        }, ["expression"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "browser_deploy_featurescript",
        "cost": {
            "backend": "browser",
            "network": "browser",
            "estimated_requests": 0,
            "max_requests": 0,
            "estimated_api_requests": 0,
            "max_api_requests": 0,
            "estimated_seconds": 30,
            "requires_browser_session": True,
            "mutating": True,
            "cacheable": False,
        },
        "description": (
            "Deploy a FeatureScript script through the browser UI, spending ZERO Onshape API quota. "
            "An actual deploy (dry_run=false, requires confirm_mutation=true) opens the target document "
            "if needed, writes the Ace editor content, and clicks the FeatureScript Commit button, pacing "
            "each real navigation/write/commit through the browser action guard. "
            "With `dry_run=true` (no confirmation needed) it is a pure local preview: it starts no browser "
            "session and performs no navigation, editor read/write, or click — it only reports the "
            "submitted source length/line count. "
            "The FeatureScript source is the browser-visible code; no credentials or API calls are involved."
        ),
        "inputSchema": object_schema({
            "script": {
                "type": "string",
                "description": "Full FeatureScript source to deploy.",
            },
            "document_name": {
                "type": "string",
                "default": "Branch Cable Trophy Display - FeatureScript",
                "description": "Documents-list name of the document to open when the editor is not already on screen.",
            },
            "confirm_mutation": mutating_confirmation(),
            "dry_run": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Pure local preview: report the submitted source length/line count without starting a "
                    "browser session, navigating, reading/writing the editor, or clicking. Needs no "
                    "confirm_mutation."
                ),
            },
        }, ["script"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    },
    {
        "name": "browser_open_document",
        "cost": {
            "backend": "browser",
            "network": "browser",
            "estimated_requests": 0,
            "max_requests": 0,
            "estimated_api_requests": 0,
            "max_api_requests": 0,
            "estimated_seconds": 20,
            "requires_browser_session": True,
            "mutating": False,
            "cacheable": False,
        },
        "description": (
            "Open a document from the Onshape documents list by its visible name. Read-only navigation: "
            "it goes to the documents list and clicks the matching document link, then returns the resulting "
            "document/workspace/element ids parsed from the URL. Zero Onshape API quota. Does not create or "
            "modify any cloud data."
        ),
        "inputSchema": object_schema({
            "document_name": {
                "type": "string",
                "default": "Branch Cable Trophy Display - FeatureScript",
                "description": "Visible document name in the 'owned by me' documents list.",
            },
        }),
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "browser_read_featurescript",
        "cost": {
            "backend": "browser",
            "network": "browser",
            "estimated_requests": 0,
            "max_requests": 0,
            "estimated_api_requests": 0,
            "max_api_requests": 0,
            "estimated_seconds": 10,
            "requires_browser_session": True,
            "mutating": False,
            "cacheable": False,
        },
        "description": (
            "Read the FeatureScript source currently open in the browser's Ace editor and return it together "
            "with the document/workspace/element ids parsed from the page URL. Read-only, zero Onshape API "
            "quota. If no FeatureScript editor is open it returns read=false and suggests "
            "browser_open_document first."
        ),
        "inputSchema": object_schema({}),
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "browser_reconnect",
        "cost": {
            "backend": "browser",
            "network": "browser",
            "estimated_requests": 0,
            "max_requests": 0,
            "estimated_api_requests": 0,
            "max_api_requests": 0,
            "estimated_seconds": 10,
            "requires_browser_session": True,
            "mutating": False,
            "cacheable": False,
        },
        "description": (
            "Detect the Onshape session-timeout dialog ('您的 Onshape 会话已超时…单击此处重新连接。') and click "
            "the reconnect link to restore the live session. Read-only session recovery — it does not create or "
            "modify cloud data. Also runs automatically inside browser_open_document, browser_read_featurescript, "
            "and browser_deploy_featurescript so a timed-out session recovers before the requested action."
        ),
        "inputSchema": object_schema({}),
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },

]

HANDLERS: dict[str, ToolHandler] = {
    "browser_session": _browser_session,
    "browser_watch": _browser_watch,
    "browser_inspect": _browser_inspect,
    "browser_scroll": _browser_scroll,
    "browser_click": _browser_click,
    "browser_eval": _browser_eval,
    "browser_deploy_featurescript": _browser_deploy_featurescript,
    "browser_open_document": _browser_open_document,
    "browser_read_featurescript": _browser_read_featurescript,
    "browser_reconnect": _browser_reconnect,
    "onshape_get_project_state": _local_state,
    "onshape_api_quota": lambda _: {"quota": api_usage()},
    "onshape_eval_featurescript": _eval_featurescript,
    "onshape_get_parameter_set": _parameter_set,
    "onshape_build_parameter_payload": _parameter_payload,
    "onshape_list_document_elements": _list_document_elements,
    "onshape_get_feature_studio_status": lambda _: (
        _require_live(2, "get_feature_studio_status") or
        feature_studio_status()
    ),
    "onshape_check_model": lambda arguments: (
        _require_live(3, "check_model") or
        check_model(
            mode=arguments.get("mode", "detailed"),
            part_studio_id=arguments.get("part_studio_id"),
        )
    ),
    "onshape_render_preview": _render_preview,
    "onshape_upload_feature_studio": _upload,
    "onshape_create_validation_part_studio": _create_part_studio,
    "onshape_instantiate_feature": _instantiate,
    "onshape_run_validation_pipeline": _pipeline,
    # FeatureScript reference tools (local, offline)
    "fs_check_version": _check_version,
    "fs_update_reference": _update_reference,
    "fs_quick_reference": lambda _: fs_reference.quick_reference(),
    "fs_list_modules": lambda arguments: {
        "categories": fs_reference.list_categories(),
        "modules": fs_reference.list_modules(category=arguments.get("category")),
    },
    "fs_list_functions": lambda arguments: {
        "functions": fs_reference.list_functions(
            module=arguments.get("module"),
            category=arguments.get("category"),
            kind=arguments.get("kind"),
            prefix=arguments.get("prefix"),
            limit=arguments.get("limit", 50),
        ),
    },
    "fs_get_function": lambda arguments: fs_reference.get_function(
        name=arguments["name"],
        module=arguments.get("module"),
        kind=arguments.get("kind"),
    ),
    "fs_get_type": lambda arguments: fs_reference.get_type(
        name=arguments["name"],
        module=arguments.get("module"),
    ),
    "fs_search": lambda arguments: {
        "results": fs_reference.search(
            query=arguments["query"],
            module=arguments.get("module"),
            category=arguments.get("category"),
            kind=arguments.get("kind"),
            limit=arguments.get("limit", 20),
        ),
    },
    "fs_guide_section": lambda arguments: fs_reference.guide_section(
        page=arguments["page"],
        section=arguments.get("section"),
    ),
    "fs_library_source": lambda arguments: fs_reference.library_source(
        module=arguments["module"],
        function=arguments.get("function"),
    ),
    # Project docs tools (local, offline)
    "docs_list": lambda _: project_docs.list_pages(),
    "docs_section": lambda arguments: project_docs.section(
        page=arguments["page"],
        section_name=arguments.get("section"),
    ),
    "docs_search": lambda arguments: project_docs.search(
        query=arguments["query"],
        page=arguments.get("page"),
        limit=arguments.get("limit", 20),
    ),
    # Onshape REST API reference tools (local, offline)
    "onshape_api_list_tags": lambda _: onshape_api_reference.list_tags(),
    "onshape_api_search": lambda arguments: {
        "results": onshape_api_reference.search(
            query=arguments["query"],
            tag=arguments.get("tag"),
            limit=arguments.get("limit", 20),
        ),
    },
    "onshape_api_endpoint": lambda arguments: onshape_api_reference.get_endpoint(
        path=arguments["path"],
        method=arguments.get("method"),
    ),
    "onshape_api_schema": lambda arguments: onshape_api_reference.get_schema(
        name=arguments["name"],
    ),
    "onshape_api_auth": lambda arguments: onshape_api_docs.auth(
        section=arguments.get("section"),
    ),
    "onshape_api_error_codes": lambda arguments: onshape_api_docs.error_codes(
        status=arguments.get("status"),
    ),
}


def _json_text(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def tool_result(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        handler = HANDLERS[name]
    except KeyError as error:
        raise ValueError(f"Unknown tool: {name}") from error
    try:
        value = handler(arguments)
        if name == "onshape_render_preview" and value.get("base64"):
            encoded = value.pop("base64")
            return {
                "content": [
                    {"type": "text", "text": _json_text(value)},
                    {"type": "image", "data": encoded, "mimeType": "image/png"},
                ],
                "structuredContent": value,
                "isError": False,
            }
        return {
            "content": [{"type": "text", "text": _json_text(value)}],
            "structuredContent": value,
            "isError": False,
        }
    except Exception as error:
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        safe_error = f"{type(error).__name__}: {error}"
        return {
            "content": [{"type": "text", "text": safe_error}],
            "isError": True,
        }


def response(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


def dispatch(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        return response(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "This server assists with writing Onshape FeatureScript and with testing it in Onshape. "
                "For FeatureScript questions, use the offline reference tools first (fs_search, "
                "fs_get_function, fs_get_type, fs_guide_section, fs_library_source): the standard library "
                "is rarely present in language-model training data, so look up exact signatures before "
                "writing code. Read order: start with a search/find tool (cheap candidate list), then "
                "fs_get_function or fs_guide_section for the one entry you need (full detail) — the "
                "vendored corpus is tiered (onshape_docs/reference/quick/ then onshape_docs/reference/index/; onshape_docs/reference/raw/ is "
                "build input and never read). The project's own documentation (tool catalog, verified "
                "experience/lessons, example docs) is served by docs_list / docs_section / docs_search. "
                "Use read-only inspection tools unless the user explicitly requests a cloud "
                "mutation; mutating tools require confirm_mutation=true and never return credentials."
            ),
        })
    if method == "ping":
        return response(request_id, {})
    if method == "tools/list":
        return response(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return response(request_id, error={"code": -32602, "message": "Invalid tools/call parameters"})
        try:
            return response(request_id, tool_result(name, arguments))
        except ValueError as error:
            return response(request_id, error={"code": -32602, "message": str(error)})
    return response(request_id, error={"code": -32601, "message": f"Method not found: {method}"})


def serve() -> None:
    """Serve newline-delimited JSON-RPC over stdin/stdout.

    Reads/writes raw UTF-8 bytes on ``sys.stdin.buffer``/``sys.stdout.buffer``
    instead of the locale-dependent text streams. On a Chinese-locale Windows
    host the text streams default to GBK, so any response containing a
    non-GBK character (e.g. ``⚠`` in a tool description) would raise
    ``UnicodeEncodeError`` and kill the bridge child. Byte-level UTF-8 keeps
    the protocol bytes identical on every platform.
    """
    stdin_buffer = sys.stdin.buffer
    stdout_buffer = sys.stdout.buffer
    for raw in stdin_buffer:
        if not raw.strip():
            continue
        try:
            message = json.loads(raw.decode("utf-8"))
            if not isinstance(message, dict):
                raise ValueError("Message must be a JSON object")
            outgoing = dispatch(message)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            outgoing = response(None, error={"code": -32700, "message": f"Parse error: {error}"})
        if outgoing is not None:
            payload = json.dumps(outgoing, separators=(",", ":"), ensure_ascii=False)
            stdout_buffer.write(payload.encode("utf-8") + b"\n")
            stdout_buffer.flush()

    # stdin EOF = the stdio client (bridge relay) disconnected. Release the
    # browser profile so the next connection can open it again.
    _shutdown_browser_session()


if __name__ == "__main__":
    serve()
