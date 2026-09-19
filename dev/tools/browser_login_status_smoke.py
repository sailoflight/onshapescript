r"""Operator-run status event-pump acceptance; default is a pure local plan.

From a provisioned Windows checkout (no installation performed by this script):
  .\.venv\Scripts\python.exe dev/tools/browser_login_status_smoke.py
  .\.venv\Scripts\python.exe dev/tools/browser_login_status_smoke.py --confirm-browser --channel msedge

Uses a fresh temporary headless profile and fixed route-fulfilled HTML, never
saved production login/config/profile data. All page requests after routing are
fulfilled locally; this is not an OS/browser background-traffic firewall.
Exit 0 requires both acceptance checks and complete release/temp cleanup.
An incomplete release retains the temp directory for Operator recovery.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SIGNIN = "https://cad.onshape.com/signin"
APP = "https://cad.onshape.com/documents"
HTML = """<!doctype html><meta charset="utf-8">
<title>Local login-status smoke</title><p>Fixed synthetic page</p>"""
CSP = "default-src 'none'; script-src 'unsafe-inline'; worker-src 'none'; connect-src 'none'"


def require(condition, check):
    if not condition:
        raise AssertionError(check)


def run(channel):
    # Imports and all native work are behind the explicit CLI confirmation.
    sys.path.insert(0, str(ROOT))
    from onshape_browser_mode.session import BrowserSession
    from onshape_browser_mode.settings import BrowserCfg, BrowserConfig, ListenerCfg, PacingCfg

    temporary = Path(tempfile.mkdtemp(prefix="onshape-login-status-smoke-"))
    session = None
    report = {"passed": False, "checks": [], "releaseComplete": False, "tempRemoved": False}
    phase = "construct"
    try:
        class IsolatedSession(BrowserSession):
            @staticmethod
            def _state_path():
                # status saves the observed app URL only inside the smoke temp.
                return temporary / "browser-state.json"

        session = IsolatedSession(BrowserConfig(
            BrowserCfg(channel=channel, user_data_dir=str(temporary / "profile"), headless=True),
            PacingCfg(), ListenerCfg(enabled=False, record_dom_snippets=False, record_network=False),
        ))
        phase = "start"
        page = session.start()
        context = session.context
        owner = session._resources
        generation = owner.snapshot().generation
        require(page.url == "about:blank", "fresh_profile_blank_page")
        context.set_default_timeout(10000)
        routed = []

        def fulfill(route):
            # Never continue/fetch: even an unexpected page request stays local.
            routed.append(route.request.url)
            route.fulfill(status=200, content_type="text/html", body=HTML,
                          headers={"Content-Security-Policy": CSP})

        context.route("**/*", fulfill)
        phase = "local_signin"
        page.goto(SIGNIN, wait_until="load", timeout=10000)
        require(SIGNIN in routed, "signin_fulfilled_locally")
        # Seed the business state produced by open_login_page, without reading a
        # saved app URL or invoking a second login/navigation workflow.
        session._status = "awaiting_login"
        session.login_confirmed = False
        session.human_action_required = True

        for label, before, destination, logged_in, expected_state in (
            ("login", SIGNIN, APP, True, "started"),
            ("logout", APP, SIGNIN, False, "awaiting_login"),
        ):
            phase = label + "_schedule"
            page.evaluate("path => { setTimeout(() => history.pushState({}, '', path), 20); }",
                          "/documents" if logged_in else "/signin")
            # Deliberately do not use Playwright wait_for_timeout: Python sleep
            # lets Chromium run its timer while the sync dispatcher remains idle.
            time.sleep(0.2)
            phase = label + "_stale_cache_precondition"
            cached_url = page.url
            require(cached_url == before, "cached_url_must_still_be_stale")
            phase = label + "_single_status"
            with ExitStack() as guards:
                for target, names in (
                    (session, ("start", "open_login_page", "adopt_page", "_enforce_single_working_page",
                               "_make_resources", "close", "release")),
                    (page, ("goto", "evaluate", "bring_to_front", "close")),
                    (context, ("new_page", "close")),
                ):
                    for name in names:
                        guards.enter_context(mock.patch.object(
                            target, name, side_effect=AssertionError("forbidden_status_action:" + name)))
                native_title = guards.enter_context(mock.patch.object(page, "title", wraps=page.title))
                status = session.status()  # Exactly one status; no inspect/login.
                require(native_title.call_count == 1, "exactly_one_native_title")
            require(status["pageUrl"] == destination, "fresh_status_url")
            require(status["loginConfirmed"] is logged_in, "fresh_login_flag")
            require(status["humanActionRequired"] is not logged_in, "fresh_human_flag")
            require(status["sessionStatus"] == expected_state, "fresh_session_state")
            require(session._resources is owner and session.page is page and session.context is context,
                    "same_resource_owner")
            require(owner.snapshot().generation == generation, "no_relaunch")
            require(context.pages == [page], "same_single_page")
            report["checks"].append({"name": label, "cachedUrl": cached_url,
                                     "freshUrl": status["pageUrl"], "loginConfirmed": logged_in,
                                     "sessionStatus": expected_state, "titleCalls": 1})
        report["passed"] = True
    except Exception as exc:
        # Synthetic check names are fixed; never include native exception text.
        report["failedPhase"] = phase
        report["errorType"] = type(exc).__name__
    finally:
        try:
            report["releaseComplete"] = session is None or session.release()["profileReleased"] is True
        except Exception as exc:
            report["releaseErrorType"] = type(exc).__name__
        if report["releaseComplete"]:
            try:
                shutil.rmtree(temporary)
                report["tempRemoved"] = True
            except Exception as exc:
                report["cleanupErrorType"] = type(exc).__name__
        if not report["tempRemoved"]:
            report["retainedTemp"] = str(temporary)
        report["passed"] = report["passed"] and report["releaseComplete"] and report["tempRemoved"]
        print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-browser", action="store_true", help="Operator: launch isolated headless browser")
    parser.add_argument("--channel", default="msedge", help="Existing installed browser channel (default: msedge)")
    args = parser.parse_args()
    if not args.confirm_browser:
        print(json.dumps({"mode": "plan", "browserStarted": False, "profileCreated": False,
                          "checks": ["stale_signin_to_fresh_login", "stale_app_to_fresh_logout"],
                          "execution": "Operator supplies --confirm-browser; independent temporary headless profile"}, indent=2))
        return 0
    return run(args.channel)


if __name__ == "__main__":
    raise SystemExit(main())
