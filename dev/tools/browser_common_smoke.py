r"""Isolated browser_common acceptance for an already provisioned browser host.

From the checkout root (PowerShell, use the host's existing Python environment):
  .\.venv\Scripts\python.exe dev/tools/browser_common_smoke.py --output smoke-plan.json
  .\.venv\Scripts\python.exe dev/tools/browser_common_smoke.py --confirm-browser --output smoke-result.json

Default: local plan only, without loading browser configuration or dependencies.
Confirmed: actual BrowserSession + SyncSession + native synchronous Playwright;
headed unless --headless is explicit. Existing channel/executable selection is
reused; profile, proxy and recorder settings are never reused. No profile argument,
login, saved app URL, MCP, REST, dependency installation or background job exists.
Only about:blank and fixed set_content HTML are exercised. Page requests are
aborted after each context starts; this is not an OS/browser telemetry firewall.

Requires Python >=3.12 (TemporaryDirectory(delete=False)); target is Windows
Python 3.14.6 / existing Edge. Paths are pathlib paths, independent of shell/cwd.
Exit 0 means plan generated or all checks AND cleanup passed; 1 means failure.
On incomplete release, preserve the temporary directory and report its recovery
path. Do not delete a retained profile until an Operator verifies owner shutdown.
Owned-handle release is not an independent OS profile-lock check. No exception
messages, traceback, config dump, environment, URLs, cookies or page HTML are
included in JSON. Only a retained temporary recovery path is reported.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import tempfile

# Direct script execution must work from an external cwd, with the library
# installed normally (or through PYTHONPATH pointing to an installed wheel).
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CHECKS = (
    "start_reuse_one_owner", "native_locator", "scope_protection_and_adopt",
    "temporary_page_cleanup", "closed_page_scope_guard", "closed_page_recovery",
    "release", "release_idempotent", "restart", "context_close_recovery",
)
HTML = """<!doctype html><meta http-equiv="Content-Security-Policy"
content="default-src 'none'; script-src 'unsafe-inline'">
<label>Probe<input id="probe"></label>
<button id="apply" onclick="document.querySelector('#result').textContent =
document.querySelector('#probe').value">Apply</button><output id="result"></output>"""


class SmokeCheckError(RuntimeError):
    """A named acceptance check failed; no native diagnostic text is copied."""


def require(condition):
    if not condition:
        raise SmokeCheckError()


def versions():
    result = {"python": platform.python_version()}
    for distribution in ("lijq-browser-common", "playwright"):
        try:
            result[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            result[distribution] = None
    return result


def make_session(profile, *, headless):
    from onshape_browser_mode.session import BrowserSession
    from onshape_browser_mode.settings import (
        BrowserCfg, BrowserConfig, ListenerCfg, PacingCfg, load_browser_config,
    )

    existing = load_browser_config().browser
    isolated = BrowserCfg(
        channel=existing.channel, executable_path=existing.executable_path,
        user_data_dir=str(profile), headless=headless,
    )
    config = BrowserConfig(isolated, PacingCfg(), ListenerCfg(
        enabled=False, record_dom_snippets=False, record_network=False,
    ))
    return BrowserSession(config)


def native_types():
    from playwright.sync_api import BrowserContext, Locator, Page
    return Page, BrowserContext, Locator


@contextmanager
def check(report, name):
    item = {"name": name, "passed": False}
    report["checks"].append(item)
    try:
        yield
    except BaseException as exc:
        item["error_type"] = type(exc).__name__
        raise
    else:
        item["passed"] = True


def cleanup_result(result):
    # Never serialize native page references, exception messages or URLs.
    return {
        "complete": result.complete,
        "error_types": [item.error_type for item in result.items if item.error_type],
    }


@contextmanager
def scope_check(session, report, name):
    scope = None
    try:
        with session.temporary_pages() as scope:
            yield scope
    finally:
        if scope is not None and scope.report is not None:
            report["scope_cleanup"].append({"name": name, **cleanup_result(scope.report)})
    require(scope is not None and scope.report is not None and scope.report.complete)


def release(session, report, name):
    entry = {"name": name, "complete": False}
    report["releases"].append(entry)
    try:
        result = session.release()
        for key in ("released", "alreadyReleased", "profileReleased", "contextClosed",
                    "playwrightStopped"):
            entry[key] = result[key]
        owner_report = session._resources.last_release_report if session._resources else None
        entry["error_types"] = [failure.error_type for failure in owner_report.failures] if owner_report else []
        entry["complete"] = result["profileReleased"] is True
        if owner_report is not None:
            entry["context_status"] = owner_report.context_status
            entry["driver_status"] = owner_report.driver_status
            entry["browser_fallback_used"] = owner_report.browser_fallback_used
    except BaseException as exc:
        entry["error_type"] = type(exc).__name__
        raise
    return entry


def prepare_local(page):
    require(page.url == "about:blank")
    page.set_content(HTML, wait_until="domcontentloaded", timeout=10000)


def secure_context(context):
    context.set_default_timeout(10000)
    context.route("**/*", lambda route: route.abort())


def exercise(session, report):
    from browser_common import SessionStateError, SyncSession
    from onshape_browser_mode.errors import BrowserLaunchError

    Page, BrowserContext, Locator = native_types()
    with check(report, "start_reuse_one_owner"):
        page = session.start()
        owner = session._resources
        context = session.context
        secure_context(context)
        prepare_local(page)
        generation = owner.snapshot().generation
        require(isinstance(owner, SyncSession))
        require(isinstance(page, Page) and isinstance(context, BrowserContext))
        require(page is session.page is owner.page)
        require(page.context is context is owner.context)
        require(session.start() is page and session._resources is owner)
        require(session.context is context and owner.snapshot().generation == generation)
        require(len(context.pages) == 1)
        report["native_identity"] = {
            "owner": type(owner).__module__ + "." + type(owner).__qualname__,
            "page": type(page).__module__ + "." + type(page).__qualname__,
            "context": type(context).__module__ + "." + type(context).__qualname__,
            "page_is_owner_page": True, "context_is_owner_context": True,
        }
        # Playwright declares BrowserContext.browser as Browser | None.
        # Optional version diagnostics must not gate lifecycle acceptance.
        report["versions"]["browser"] = None
        try:
            browser = context.browser
            if browser is not None:
                report["versions"]["browser"] = browser.version
        except Exception as exc:
            report["versions"]["browser_error_type"] = type(exc).__name__

    with check(report, "native_locator"):
        locator = page.locator("#probe")
        require(isinstance(locator, Locator))
        locator.fill("local-smoke")
        page.locator("#apply").click()
        require(page.locator("#result").text_content() == "local-smoke")
        report["native_identity"]["locator"] = type(locator).__module__ + "." + type(locator).__qualname__

    with check(report, "scope_protection_and_adopt"):
        with scope_check(session, report, "adoption") as scope:
            temporary = scope.track(context.new_page())
            prepare_local(temporary)
            stray = context.new_page()
            require(session.start() is page)
            require(not temporary.is_closed() and stray.is_closed())
            try:
                session.release()
            except SessionStateError as exc:
                report["checks"][-1]["expected_error_type"] = type(exc).__name__
            else:
                raise SmokeCheckError()
            require(session.context is context and session.page is page)
            require(not page.is_closed() and not temporary.is_closed())
            session.adopt_page(temporary)
            require(session.page is temporary and session.start() is temporary)
            require(page.is_closed())
        require(not temporary.is_closed() and session.page is temporary)
        require(len(context.pages) == 1)

    with check(report, "temporary_page_cleanup"):
        with scope_check(session, report, "temporary") as scope:
            disposable = scope.track(context.new_page())
            prepare_local(disposable)
        require(disposable.is_closed() and not temporary.is_closed())
        require(session.page is temporary and len(context.pages) == 1)

    with check(report, "closed_page_scope_guard"):
        with scope_check(session, report, "closed_current_adoption") as scope:
            replacement = scope.track(context.new_page())
            prepare_local(replacement)
            temporary.close()
            try:
                session.start()
            except BrowserLaunchError as exc:
                report["checks"][-1]["expected_error_type"] = type(exc).__name__
            else:
                raise SmokeCheckError()
            require(session.page is None and session.context is context)
            require(not replacement.is_closed() and session._resources is owner)
            require(owner.snapshot().generation == generation)
            session.adopt_page(replacement)
            require(session.start() is replacement)
        require(not replacement.is_closed() and session.page is replacement)

    with check(report, "closed_page_recovery"):
        # Keep one blank tab alive: closing a browser's last tab may also close
        # its window/context, a separate recovery scenario tested below.
        survivor = context.new_page()
        replacement.close()
        require(session.page is None)
        recovered = session.start()
        require(recovered is survivor and recovered is session.page)
        require(session.context is context and session._resources is owner)
        require(owner.snapshot().generation == generation and len(context.pages) == 1)
        prepare_local(recovered)

    with check(report, "release"):
        require(release(session, report, "first")["complete"])
        require(session.page is None and session.context is None)
    with check(report, "release_idempotent"):
        second = release(session, report, "idempotent")
        require(second["complete"] and second["alreadyReleased"] and not second["released"])
        require(owner.snapshot().generation == generation)
    with check(report, "restart"):
        restarted = session.start()
        second_context = session.context
        secure_context(second_context)
        prepare_local(restarted)
        require(session._resources is owner and second_context is not context)
        require(owner.snapshot().generation == generation + 1)
        require(isinstance(restarted, Page) and restarted is owner.page)
        require(len(second_context.pages) == 1)

    with check(report, "context_close_recovery"):
        second_context.close()
        require(owner.snapshot().state == "invalidated")
        require(session.context is None and session.page is None)
        restored = session.start()
        third_context = session.context
        secure_context(third_context)
        prepare_local(restored)
        require(session._resources is owner and third_context is not second_context)
        require(owner.snapshot().generation == generation + 2)
        # The facade releases the invalidated generation before restarting.
        require(owner.last_release_report is not None and owner.last_release_report.complete)
        invalidated_release = owner.last_release_report
        report["releases"].append({
            "name": "invalidated_generation", "complete": invalidated_release.complete,
            "context_status": invalidated_release.context_status,
            "driver_status": invalidated_release.driver_status,
            "browser_fallback_used": invalidated_release.browser_fallback_used,
            "error_types": [failure.error_type for failure in invalidated_release.failures],
        })
        require(isinstance(third_context, BrowserContext) and restored is owner.page)
        require(len(third_context.pages) == 1)


def run_smoke(*, confirm_browser=False, headless=False):
    report = {
        "mode": "browser" if confirm_browser else "plan", "status": "planned",
        "headed": not headless, "checks": [], "scope_cleanup": [], "releases": [],
        "profile_cleanup": {"created": False, "complete": True},
    }
    if not confirm_browser:
        report["checks"] = [{"name": name, "passed": None} for name in CHECKS]
        return report

    temporary = None
    session = None
    released = True
    report["status"] = "failed"
    try:
        report["versions"] = versions()
        # No context-manager/GC deletion: failed release MUST retain the profile.
        temporary = tempfile.TemporaryDirectory(prefix="browser-common-smoke-", delete=False)
        profile = (Path(temporary.name) / "profile").resolve()
        report["profile_cleanup"] = {"created": True, "complete": False}
        session = make_session(profile, headless=headless)
        require(session.profile_dir() == profile)
        released = False
        exercise(session, report)
        require(tuple(item["name"] for item in report["checks"]) == CHECKS)
        require(all(item["passed"] for item in report["checks"]))
        report["status"] = "passed"
    except BaseException as exc:
        report["error_type"] = type(exc).__name__
    finally:
        if session is not None:
            try:
                released = release(session, report, "finally")["complete"]
            except BaseException as exc:
                released = False
                report["cleanup_error_type"] = type(exc).__name__
        if temporary is not None:
            if released:
                try:
                    temporary.cleanup()
                    require(not Path(temporary.name).exists())
                    report["profile_cleanup"]["complete"] = True
                except BaseException as exc:
                    report["profile_cleanup"]["error_type"] = type(exc).__name__
            if not report["profile_cleanup"]["complete"]:
                report["profile_cleanup"]["retained_directory"] = temporary.name
                report["profile_cleanup"]["retained_profile"] = str(Path(temporary.name) / "profile")
        if (not released or not report["profile_cleanup"]["complete"]
                or any(not entry["complete"] for entry in report["releases"])
                or any(not entry["complete"] for entry in report["scope_cleanup"])):
            report["status"] = "failed"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    parser.add_argument("--confirm-browser", action="store_true", help="Explicitly launch the isolated local browser acceptance")
    parser.add_argument("--headless", action="store_true", help="Opt out of the default headed run")
    parser.add_argument("--output", type=Path, help="Write sanitized JSON to this file (also printed to stdout)")
    args = parser.parse_args(argv)
    report = run_smoke(confirm_browser=args.confirm_browser, headless=args.headless)
    if args.output is not None:
        try:
            args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report["status"] = "failed"
            report["output_error_type"] = type(exc).__name__
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
