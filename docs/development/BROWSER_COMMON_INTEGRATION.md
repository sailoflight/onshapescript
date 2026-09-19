# browser_common Python library integration

## Dependency and provenance

`onshape_browser_mode/session.py` composes `browser_common.SyncSession` from
`lijq-browser-common==0.1.0.dev2` (Python >=3.11). The original artifact is
`/home/lijq/code/pythonpubliclib/dist/lijq_browser_common-0.1.0.dev2-py3-none-any.whl`.
An unchanged copy is shipped in `onshape_browser_mode/wheels/`; the sibling
checkout is not needed at runtime and no sibling source path is added to Python.

SHA-256: `c1763265aa5c968032e7d18116d07e18ddbdbd873a4d6c7db033686a58913cc8`.
The wheel includes `browser_common/docs/ADAPTATION_GUIDE.md` and declares
`playwright>=1.40,<2`. Neither the library nor this adapter installs a browser.
The Windows requirements file pins the library version and resolves `./wheels`
relative to that file. Normal host installation may retrieve Playwright from the
configured package index; only the shared-library artifact is bundled here.

## Ownership and compatibility

- `SyncSession` exclusively owns the native manager/driver/context/current page,
  startup cleanup, page registrations, context invalidation and release retries.
  The Onshape facade does not copy those handles or subclass Playwright objects.
- The facade retains module-relative profile/config paths, headed/headless and
  executable/channel/proxy settings, login and saved application URL behavior,
  existing application-URL heuristic, explicit page recovery and MCP responses.
- The common owner's initial live-page choice supplies a fallback. Before the
  first cleanup, the facade explicitly adopts the first restored Onshape app
  page using the legacy business predicate. Restored-page cleanup is disabled
  in common configuration so it cannot discard that page prematurely.
- Reuse prefers the current app page; outside temporary scopes, another live app
  page can still be selected after human login. A transient evaluate failure
  keeps a live page rather than relaunching the browser. Three launch attempts
  remain, but only after the preceding startup cleanup completed. Incomplete
  cleanup retains the owner and requires release before another start.
- `page` and `context` return the native objects or `None` when unavailable.
  Imports, unstarted status and release need neither browser dependency. These
  accessors never launch or reconcile pages. Wrong-thread errors propagate.
- `adopt_page()` explicitly transfers page ownership. `temporary_pages()` delegates
  tracking/cleanup to the shared scope; the facade only suspends implicit recovery
  during that business workflow. Scope exit closes tracked temporary pages unless
  explicitly adopted. Nested scopes restore the business recovery policy on exit.
- `_enforce_single_working_page()` is retained at existing tool preparation
  boundaries and reconciles an explicit page snapshot. Active scopes and the
  current page are protected. Incomplete cleanup now raises `PageCleanupError`
  rather than silently claiming the single-page invariant.
- `status()` reports application-page observations without silently adopting a
  page or removing its temporary cleanup responsibility.
- Release keeps the existing response keys. `complete`, not `clean`, maps to
  `profileReleased`; successful browser fallback still counts as released.
  Warnings contain operation/error types rather than raw exception text.
  Context plus browser fallback failure skips driver stop and retains it for
  retry; driver-stop failure also retains the remaining resource. A release
  attempt during an active scope fails before destroying resources.
- `profileReleased` describes this process's owned-handle release, not an OS
  profile-lock probe. Cross-process ownership and MCP workflow serialization
  remain host/application responsibilities.

## Login status refresh correction

The reported target-host sequence was manual login followed by repeated stale
`signin` / `awaiting_login` / `loginConfirmed=false` status responses. Public
`browser_inspect` then observed the documents DOM, after which status reported
`started` / `loginConfirmed=true`, without another login or restart. This source
correction does not repeat that real-browser acceptance or deploy to Windows.

Read-only inspection of the installed Windows Playwright implementation under
`C:/MCP/onshapescript/.venv/Lib/site-packages/playwright/` establishes the mechanism:

- `_impl/_page.py:539` delegates URL to the main frame; `_impl/_frame.py:517`
  returns cached `_url`, updated by `_on_frame_navigated` at line 130.
- `_impl/_page.py:869` returns cached `_is_closed`, and
  `_impl/_browser_context.py:312` copies cached `_pages`.
- `sync_api/_generated.py:10891` implements `Page.title()` through `_sync()`;
  `_impl/_sync_base.py:97` schedules the coroutine and switches the dispatcher
  fiber until completion. `_impl/_frame.py:943` sends the native `title` request.
- The MCP `_browser_session` status branch calls only `session.status()`. In
  contrast, `_browser_inspect` first calls `start()`, whose existing-page path
  executes `evaluate("1 + 1")`, then evaluates the DOM. Those native calls pump
  events; the status-only cached-property path previously did not.

`status()` now makes at most one read-only `title()` RPC on an existing working
page, or an existing live page when the working page is unavailable, before
observing cached URLs. It does not start, navigate, focus, adopt, or clean pages.
On a successful read, app evidence clears human-action state and transitions
`awaiting_login` to `started`. An explicit refreshed Onshape `/signin` URL
(including query/fragment/trailing slash variants) clears sticky login history
and transitions `started` to `awaiting_login`. Other URLs retain the last login
state; this remains the existing URL heuristic, not server-side authentication
validation. Application-page preference across existing tabs remains unchanged.

A transient native read failure retains the business login flags and session
status and neither restarts nor releases resources. Cached URLs may still change
while that failed call dispatches events, but are not used to establish login or
logout until a successful read. `ExecutionContextError` propagates. Unstarted
status/release still work with both optional dependencies blocked.

The integration fake now queues a manual-navigation URL and exposes it only
when native `title()` runs, including the case where dispatch updates the URL
before the read fails. Five added regressions plus the extended cross-thread
case cover login, sticky logout, read failure/recovery, an unavailable working
page, and explicit execution-context rejection. Old code failed the new tests
(six failures including two failure-state subtests). Fixed code passed:

- Linux targeted integration/browser tests: **79 tests**.
- Linux full offline discovery: **348 tests**.
- Existing Windows Python, loading this WSL checkout and the installed
  `temp/browser-common-site` wheel through `sys.path`: **23 fake integration
  tests**, including dependency-blocked subprocess checks.
- Changed Python syntax and `git diff --check` passed. All regressions ran with
  `LIVE_API_ENABLED` unset and `PYTHONDONTWRITEBYTECODE=1`; no dependency install,
  browser launch, production-window operation, or deployment was performed.

Pre-edit copies of the facade, existing integration tests, and this note are in
`temp/login-status-refresh-backup/`, retaining their repository-relative paths.
The existing Windows `encoding="utf-8"` and `profile.resolve()` test corrections
are preserved. Final file digests are supplied with the handoff rather than
embedded here, so this document can also have a stable digest.

## Offline verification

The isolated setup used for development changes only ignored project files:

```bash
.venv/bin/python -m pip install --no-index --no-deps \
  --target temp/browser-common-site \
  onshape_browser_mode/wheels/lijq_browser_common-0.1.0.dev2-py3-none-any.whl
env -u LIVE_API_ENABLED PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=temp/browser-common-site python3 -m unittest \
  dev.tests.test_browser_common_integration dev.tests.test_browser_mode -v
env -u LIVE_API_ENABLED PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=temp/browser-common-site python3 -m unittest discover -s dev/tests -v
```

This is an installed wheel directory, not a shared-source import workaround.
The tests drive the actual shared owner through a fake native Playwright factory;
no Playwright package, browser, account or REST requests are required. For an
activated development virtual environment, install the same wheel with
`--no-index --no-deps` without `--target`, then use the usual test commands.

Verified in the isolated wheel environment: all **330** offline project tests
passed, including **18** shared-library integration/optional-dependency tests.
The browser-module syntax check and `git diff --check` also passed. The first
full run exposed a pre-existing FDM fixture mismatch: its `/home/user/...` input
was compared against `/home/lijq/...`. Only that expected path was corrected in
`dev/tests/test_fdm_analysis.py`, with its original saved in the same backup;
FDM production behavior was unchanged. No target
Windows installation, real browser smoke or Onshape operation is implied by
these offline tests. A future authorized smoke should use an isolated profile
and local HTML first, and confirm start/reuse/adopt/temporary cleanup/release
before any business-site evaluation.

## Existing limits outside this integration

The recorder binds native page/context events at its explicit watch start.
Automatic recorder rebinding after context recreation was absent before this
change and remains unverified; restart the watch workflow explicitly after
resource recreation. The ordinary process shutdown currently attempts close
once; it does not implement an Operator recovery loop for a failed cleanup.
These limitations are not resolved by the common library's lifecycle lock.

## Backup and rollback

The task's pre-edit file copies, complete pre-existing tracked diff and status
are preserved under ignored `temp/browser-common-backup/`. That directory keeps
user changes present before integration, including shared architecture/module/
operations documents. Runtime profile, local configuration and browser state
were not modified for this integration.

For this checkout, compare the current files with the corresponding backup
copies and reverse only integration changes; do not overwrite later concurrent
edits or run a repository-wide reset. Remove the newly added integration test,
this note and the bundled wheel only when no retained change needs them. The
isolated `temp/browser-common-site` install can be discarded with this test
setup. Keep the backup until review is complete.

For an approved host deployment, save its own source/dependency generation first.
Rollback the facade and requirement manifest together to that generation, stop
only its owning process through the existing Operator procedure, and preserve
its profile/config/state. No production deployment or restart was performed by
this source integration.
