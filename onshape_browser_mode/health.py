"""Bounded, zero-quota health probe for the persistent browser session.

Why this exists
---------------

The browser leg is the project's primary execution leg because it spends no
Onshape API quota, and it is deliberately long-lived: one persistent profile and
one working page are reused across calls. That longevity has a failure mode the
rest of the codebase cannot see, because it looks exactly like a healthy idle
session until something touches it:

* Onshape expires a server-side session after a period of inactivity, and the
  page then shows the timeout dialog (``您的 Onshape 会话已超时…单击此处重新连接。``).
  The dialog has TWO states, and the probe reports which one it is: with a
  rendered label the reconnect link must be clicked, while an empty/unrendered
  link means Onshape is already auto-reconnecting and clicking cannot work
  (measured live 2026-09-21: the click timed out after 30 s against an element
  that detached, and the next probe read ``ok``). Community reports agree
  that an Onshape session can require a fresh sign-in after a period away
  ([Onshape forum](https://forum.onshape.com/discussion/comment/124854#Comment_124854),
  [integrated-app session timeout](https://forum.onshape.com/discussion/comment/30109/#Comment_30109));
  no public page states a usable interval, so this module assumes **none** and
  measures instead of predicting.
* A wedged page (renderer busy, navigation in flight, or the profile owned by a
  process that stopped answering) accepts a call and never returns, so the first
  real work item pays the timeout and the caller learns nothing about why.

So the probe answers two questions in ONE bounded round trip:

1. does the page answer at all, and how long did that take (the idle-reconnect
   signature is a page that answers, slowly, after the first touch); and
2. what is it showing right now -- the session-timeout dialog, the document
   shell, or a sign-in page?

It is a read: it never launches the browser, never navigates, never clicks the
reconnect link, and never spends Onshape REST quota. Its verdict names the
recovery action; performing that action stays the caller's decision.

Honest limits
-------------

The probe is a snapshot, not a monitor. A session that is healthy now can expire
later, and a single slow round trip is not proof of a dead session -- which is
why the slow case reports a hint rather than a failure. ``roundTripMs`` is the
caller's evidence, so a verdict is never invented from a missing read.
"""

from __future__ import annotations

import time
from typing import Any

from onshape_browser_mode.selectors import (
    DOCUMENT_TABS_BUTTON,
    TIMEOUT_DIALOG,
    TIMEOUT_RECONNECT_LINK,
)

#: One bounded round trip. Long enough that a healthy page never trips it, short
#: enough that an unresponsive one is reported before a caller's own budget is
#: spent on it. Measured live 2026-09-21: a healthy Onshape document answers the
#: probe in well under a second, so this is a wedge detector, not a performance
#: gate.
DEFAULT_PROBE_TIMEOUT_MS = 8000

#: A first touch after a long idle can be slow because the session reconnects
#: while it is being read. Above this the answer is still ``ok``, but the note
#: says the latency is explained by activity rather than by page health.
SLOW_ROUND_TRIP_MS = 3000

OK = "ok"
BROWSER_NOT_RUNNING = "browser_not_running"
SESSION_TIMEOUT_DIALOG = "session_timeout_dialog"
PAGE_UNRESPONSIVE = "page_unresponsive"
LOGIN_REQUIRED = "login_required"
INDETERMINATE = "indeterminate"

_VERDICTS = (
    OK,
    BROWSER_NOT_RUNNING,
    SESSION_TIMEOUT_DIALOG,
    PAGE_UNRESPONSIVE,
    LOGIN_REQUIRED,
    INDETERMINATE,
)

_PROBE_JS = """
() => {
  const link = document.querySelector('%s');
  const dialog = document.querySelector('%s');
  const text = link ? String(link.innerText || link.textContent || '').trim().slice(0, 120) : '';
  const rendered = !!(link && link.getClientRects().length > 0);
  return {
    timeoutDialogPresent: !!link,
    timeoutDialogLinkText: text,
    // The dialog also shows while Onshape auto-reconnects, and then its link is
    // empty and unrendered, so a click cannot work. Measured live 2026-09-21.
    timeoutDialogActionable: !!(rendered && text.length > 0),
    timeoutDialogMessage: dialog ? String(dialog.innerText || dialog.textContent || '').trim().slice(0, 200) : '',
    documentShellReady: !!document.querySelector('%s'),
    title: String(document.title || '').slice(0, 120),
    href: String((window.location && window.location.href) || '').slice(0, 300),
    // Document identity. `performance.timeOrigin` is fixed for the lifetime of a
    // document and changes when the document is replaced, so comparing it across
    // two probes answers "is this still the same document?", which is how the
    // sign-in page's self-reload becomes detectable (issue #5). Reading it here
    // costs nothing extra: this evaluate already runs.
    timeOrigin: Number((window.performance && window.performance.timeOrigin) || 0),
    documentAgeMs: (window.performance && window.performance.timeOrigin)
      ? Math.round(Date.now() - window.performance.timeOrigin)
      : null,
  };
}
""" % (TIMEOUT_RECONNECT_LINK, TIMEOUT_DIALOG, DOCUMENT_TABS_BUTTON)


def probe_page(page: Any, *, timeout_ms: int = DEFAULT_PROBE_TIMEOUT_MS) -> dict[str, Any]:
    """One bounded round trip against ``page``; never raises for a bad page.

    ``wait_for_function`` is the bounded primitive: it is a real round trip
    through the same channel a modelling call uses, and it accepts the timeout
    that ``page.evaluate`` does not. A timeout is evidence, not a crash, so it is
    reported as ``responded: False`` with the elapsed time kept.
    """
    started = time.monotonic()
    responded, error = True, ""
    try:
        page.wait_for_function("() => true", timeout=timeout_ms)
    except Exception as exc:  # noqa: BLE001 - a timeout or a dead page is data here
        responded, error = False, f"{type(exc).__name__}: {exc}"
    elapsed_ms = int((time.monotonic() - started) * 1000)
    evidence: dict[str, Any] = {
        "responded": responded,
        "roundTripMs": elapsed_ms,
        "probeTimeoutMs": timeout_ms,
        "error": error,
    }
    if not responded:
        return evidence
    try:
        read = page.evaluate(_PROBE_JS)
    except Exception as exc:  # noqa: BLE001 - a failed read is unknown, not a verdict
        # The page answered the round trip but the read failed: a navigation can
        # destroy the execution context mid-read, which establishes nothing.
        evidence["readError"] = f"{type(exc).__name__}: {exc}"
        return evidence
    if not isinstance(read, dict):
        evidence["readError"] = "probe returned a non-object"
        return evidence
    evidence.update(read)
    return evidence


def classify(
    evidence: dict[str, Any],
    *,
    session_running: bool,
    on_onshape_app: bool,
    login_confirmed: bool,
    session_status: str | None = None,
) -> dict[str, Any]:
    """Turn probe evidence into one verdict plus the recovery action that fits it.

    Precedence is deliberate. A timeout dialog outranks a slow round trip because
    it names a state the caller must clear; an unresponsive page outranks a
    sign-in page because "did not answer" is strictly less information than "is
    showing the sign-in page".
    """
    verdict = INDETERMINATE
    recommended = "none"
    note = ""

    if not session_running:
        verdict = BROWSER_NOT_RUNNING
        recommended = "browser_session action=login"
        note = (
            "No browser resources are held by this MCP process. This probe did "
            "NOT launch one, so nothing about the page is known."
        )
    elif evidence.get("timeoutDialogPresent"):
        verdict = SESSION_TIMEOUT_DIALOG
        if evidence.get("timeoutDialogActionable") is False:
            # Measured live 2026-09-21: right after a restart the dialog appeared
            # with an EMPTY, unrendered link, because Onshape was already
            # auto-reconnecting. Clicking it timed out after 30 s against an
            # element that then detached, while the next probe read `ok`. When the
            # link is not actionable the honest instruction is to wait and
            # re-probe, not to click.
            recommended = "browser_session action=health"
            note = (
                "Onshape's session-timeout dialog is showing in its "
                f"automatic-reconnect state (message: {evidence.get('timeoutDialogMessage')!r}); "
                "its reconnect link has no label and is not rendered, so clicking "
                "cannot recover it. Onshape is retrying by itself -- re-probe after "
                "a short wait, and use `browser_session action=reload` only if the "
                "dialog survives."
            )
        else:
            recommended = "browser_session action=reconnect"
            note = (
                "Onshape's session-timeout dialog is showing; the session expired "
                "server-side while the browser stayed open. Its reconnect link works "
                "only when clicked, so the page will not recover by itself."
            )
    elif not evidence.get("responded"):
        verdict = PAGE_UNRESPONSIVE
        recommended = "browser_session action=reload"
        note = (
            "The page did not answer within the probe budget. This is a wedge or "
            "a navigation in flight, not proof that the session is logged out."
        )
    elif not on_onshape_app:
        if login_confirmed:
            verdict = INDETERMINATE
            recommended = "browser_session action=status"
            note = (
                "The page answers but is not an Onshape application URL while "
                "login was previously confirmed; a navigation may be in flight."
            )
        else:
            verdict = LOGIN_REQUIRED
            recommended = "browser_session action=login"
            note = "The page answers but is not signed in to an Onshape application URL."
    elif evidence.get("documentShellReady") is not True:
        # `is not True` and not falsy: a read that FAILED leaves the key absent,
        # and reporting `ok` for an unread page would be a claim the evidence
        # does not support. The app URL is right and the page answers, but the
        # shell is not proven present.
        verdict = INDETERMINATE
        recommended = "browser_session action=reload"
        note = (
            "The page answers on an Onshape URL but a rendered document shell was "
            "not read, so a modelling call taken now could see an empty document."
        )
    else:
        verdict = OK
        recommended = "none"
        note = "The page answers and is showing a rendered Onshape document."

    slow = (
        verdict == OK
        and isinstance(evidence.get("roundTripMs"), int)
        and evidence["roundTripMs"] >= SLOW_ROUND_TRIP_MS
    )
    if slow:
        note = (
            f"{note} The round trip took {evidence['roundTripMs']} ms, which is "
            "the expected first-touch latency after an idle period: the session "
            "reconnects while it is being read, so this alone is not a fault."
        )

    return {
        "verdict": verdict,
        "recommendedAction": recommended,
        "note": note,
        "slowFirstTouch": slow,
        "verdicts": list(_VERDICTS),
        "sessionStatus": session_status,
    }


def classify_held_state(
    *,
    session_running: bool,
    on_onshape_app: bool,
    login_confirmed: bool,
    session_status: str | None = None,
) -> dict[str, Any]:
    """The verdict vocabulary applied to state a process HOLDS, with no probe.

    `status()` reports ownership, not probe evidence: it reads the held page's
    URL but never performs the bounded round trip `classify` interprets. So this
    hands `classify` evidence that claims exactly what was observed -- the
    process holds a live page, and its URL is (or is not) an Onshape application
    URL -- and leaves the timeout-dialog and document-shell questions to the real
    health probe. One verdict vocabulary and one set of recommended actions stay
    shared by `status` and `health`; no `sessionStatus` value is rewritten.
    """
    evidence = {
        "responded": bool(session_running),
        "timeoutDialogPresent": False,
        # `status` reads the application URL that this facade already treats as a
        # usable Onshape session (`session._is_onshape_app_url`); it does NOT
        # re-read the rendered document shell, which stays the probe's job.
        "documentShellReady": bool(on_onshape_app),
    }
    return classify(
        evidence,
        session_running=session_running,
        on_onshape_app=on_onshape_app,
        login_confirmed=login_confirmed,
        session_status=session_status,
    )


def report(
    evidence: dict[str, Any],
    *,
    session_running: bool,
    on_onshape_app: bool,
    login_confirmed: bool,
    session_status: str | None = None,
    page_url: str | None = None,
    pages_seen: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The public health answer: probe evidence, one verdict, one next action."""
    return {
        "health": "probe",
        "quota": 0,
        "readOnly": True,
        "launchedBrowser": False,
        **classify(
            evidence,
            session_running=session_running,
            on_onshape_app=on_onshape_app,
            login_confirmed=login_confirmed,
            session_status=session_status,
        ),
        "pageUrl": page_url,
        "pages": pages_seen or [],
        "probe": evidence,
    }
