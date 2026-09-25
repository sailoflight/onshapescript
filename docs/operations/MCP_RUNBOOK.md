# Onshape ordinary stdio MCP runbook

Audience: Production / Operator

This runbook covers installation, process/profile ownership, client adaptation,
health, restart, and recovery. It does not authorize production Onshape calls,
credential access, or model/cloud mutations.

> **Consumer Release artifacts.** Installing, verifying, upgrading, rolling back,
> or unregistering a packaged consumer Release is specified in
> `operations/RELEASE.md`. That consumer plane needs no `apg` CLI, no
> project-governance package, no Git, and no WSL; the source-style procedures
> below are the **development-plane** path for a checkout (or for a deployment an
> operator chooses to run from source).

## Runtime contract

```text
MCP client or independently installed adapter
  -> ordinary stdio
  -> python -m mcp_main.win.mcp
  -> onshape_browser_mode -> visible Chrome/Edge
  -> onshape_rest_api_mode -> guarded REST boundary
```

The ordinary MCP process owns browser resources, profile, local configuration,
REST state, and logs. Exactly one process may own a browser profile. Client EOF
terminates that process and releases browser resources while preserving the
profile on disk. This repository opens no TCP listener and installs no task,
service, relay, or launcher.

### Browser lifetime and the login

Onshape Web has no "stay signed in": its auth cookies (`on-session-id`, `_u`) are
session cookies, so closing the browser signs the human out. In the default
configuration each bridge/MCP child launches the browser and closes it on stdin
EOF, which means **a bridge restart costs one human SSO/2FA login**. That is a
property of Onshape, not of this module.

`browser.resident = true` removes that cost. The module then spawns one detached
browser publishing a loopback-only DevTools endpoint (`127.0.0.1:<resident_port>`)
and every child attaches over CDP instead of launching; a child's exit detaches and
leaves the browser, its tabs and its session cookies alive. Consequences for an
operator:

- the browser outlives the MCP process, so client EOF does **not** clean it up;
  ending it means closing its window or stopping the browser process;
- exactly one resident browser per profile and port; a second owner hits
  `profile is in use`;
- that DevTools endpoint is a listener published by the **browser** process, on
  loopback only -- the MCP server still opens no listener. Never forward or bind it
  beyond loopback: it grants full control of the logged-in profile;
- the first run, or any run after the browser was closed, still needs one human
  login. Resident mode only stops *self-inflicted* logouts.

Three session endings are not interchangeable, and the operator should not
conflate them:

- **`browser_session(action="detach")`** is the intended "keep the window" path.
  It is truthful **only** in resident/attached mode (`browser.resident = true`);
  every other mode returns `detached=false` with `supported=false` and recommends
  release, because the pinned `browser_common` wheel ties the launched browser's
  lifetime to the Playwright connection. Treat that answer as a capability
  report, not as a bug to work around, and do not kill the browser process or
  delete lock files to force it.
- **`browser_session(action="release")`** is the close path. It closes only the
  browser/context owned by the current MCP process, releases that process's
  profile ownership, is idempotent when nothing was started, and cannot close a
  browser owned by another process.
- **A process crash or a page navigation** leaves the profile on disk and does
  not by itself cost a login, whereas an explicit release can.

`browser_session action=status` reports `verdict`, `recommendedAction`, and
`verdictNote` so an operator can read the decision rather than re-deriving it,
plus `profileDir`/`profileBytes`/`profileBytesComplete` and
`accountMarkerDetected`. The last one is a name-match boolean from Edge's own
account keys: `false` means "no marker found", **not** "anonymous", and no account
value is ever returned.

## Preconditions

- Deployment copy on the browser/REST host, conventionally `C:\MCP\onshapescript`.
- Python >=3.11 and installed Chrome/Edge.
- Interactive desktop access for initial Onshape SSO/2FA.
- Credentials only in module-owned ignored configuration.
- Recovery point for browser profile, local config, REST state/credentials,
  quota ledger, outputs, and client profile/package state.

## Install (development plane: a source checkout)

```powershell
cd C:\MCP\onshapescript
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r onshape_browser_mode\requirements-windows.txt
```

For a packaged consumer Release, use `operations/RELEASE.md` instead: that path
unpacks an artifact, verifies `SHA256SUMS`/`release-manifest.json`, and needs no
Git checkout.

Ship `onshape_browser_mode/wheels/` with the deployment. The requirements file
resolves its bundled `lijq-browser-common==0.1.0.dev2` wheel using a path relative
to that requirements file; it does not require the sibling `pythonpubliclib`
checkout. Verify its SHA-256 against
`../development/BROWSER_COMMON_INTEGRATION.md` before installation. The package
requires Python >=3.11. Source integration and offline tests do not install into
or restart the Windows deployment.

On release failure, inspect `contextClosed`, `playwrightStopped` and `warnings`.
If context and browser fallback closure fail, the shared owner keeps the driver
for a subsequent cooperative release; warnings contain operation/error types.
`profileReleased` reports owned-handle cleanup, not an independent OS lock probe.
Rollback source and its dependency manifest together; keep profile/config/state.

Use the machine's existing Chrome/Edge; do not download another browser merely
for this MCP. Install any REST/module dependencies required by the selected
capabilities using their module documentation.

## Ordinary entry

```powershell
cd C:\MCP\onshapescript
.\.venv\Scripts\python.exe -B -m mcp_main.win.mcp
```

The process speaks MCP JSON-RPC only on stdin/stdout. A client or adapter owns
its process lifecycle. Do not launch a second process against the same profile.

## Optional cross-host adapter

Register the ordinary command above with an independently installed
`win-wsl-mcp-bridge` using id `onshape`, the Windows checkout as `cwd`, and
`multiProcessAllowed=false`. Configure DSH from
`mcp_main/dsh/cordis.patch.yml.example`. The bridge owns loopback listeners,
host registries, process supervision, reconnect, redacted peer metadata, and
rollback; follow its own runbook for those concerns.

DSH `@deepseek-ai/dsh-mcp-client` 0.1.0-rc.8 registers tools but does not project
`initialize.instructions`. Install the MCP client and the generated companion as
one deployment generation:

```bash
python mcp_main/dsh/build_runtime_prompt_companion.py --check
python -m unittest dev.tests.test_runtime_prompt -v
```

Back up profile patch/package state before changes. Verify model-visible policy,
not merely listed tools. Compatibility evidence is in
`../verification/MCP_CLIENT_COMPATIBILITY.md`.

## Initial login

An authorized MCP User invokes `browser_session(action=login)`. A human completes
SSO/2FA in the visible browser. Never automate SSO/2FA or place credentials in
client arguments, prompts, tool calls, logs, or fixtures.

With `browser.resident = true` the login is completed once in the resident browser
and survives later MCP/bridge restarts. Verify the resident browser is up with a
read-only call, e.g. `browser_session(action=status)` and then
`browser_get_page_tabs`; landing on `https://cad.onshape.com/signin` instead of the
document means the browser was closed (or killed) and one login is required again.

## Restart with resident mode

The restart itself is unchanged -- deploy source, replace the process generation --
but the expected outcome is not: after enabling resident mode a restarted bridge
must reach the document tabs **without** a login. Two checks that cost no Onshape
REST quota:

- `127.0.0.1:<resident_port>/json/version` answers, and the `Browser` field names
  the running browser build;
- a read-only navigation or tab listing returns the document, not `/signin`.

Stop on: `/signin` after a restart, two browsers on one profile, or an endpoint that
answers on a non-loopback address.

## Health

Healthy means:

- one MCP process generation owns the profile;
- initialize returns expected identity and runtime-policy revision;
- tools/list and read-only status calls succeed with protocol-clean stdout;
- browser status is sane and credentials are not exposed;
- in resident mode, the DevTools endpoint is loopback-only and answers on the
  configured port, and the visible browser is the one the login lives in;
- REST quota/state guards remain intact;
- any external bridge reports its own registry/nodes/link healthy.

`registered=true`, one backend, one profile owner, and serialized calls are
necessary but do not prove document/workflow isolation. Until a scoped document
lease passes end-to-end acceptance, production mode is multiple clients for
registry-classified safe reads plus one modifying agent. That agent remains the
exclusive owner from target selection through mutation, shared target-state
synchronization, acceptance, rollback/recovery if needed, and browser release.
On `client_lease_busy`, clients wait or exit; they never bypass the adapter or
start another MCP/browser. Operators stop on concurrent modifying agents,
missing explicit target IDs, or a current-page/shared-state ownership ambiguity.

Run the ordinary target-host probe without `LIVE_API_ENABLED`:

```powershell
.\.venv\Scripts\python.exe -B dev\tools\mcp_probe.py
```

## REST quota bookkeeping

The local budget is calibrated as `apiQuota.alreadyConsumed + api-usage.json consumed`.
When calibrating from the account UI, compute
`UI year-to-date total - ledgerConsumed` before updating the baseline; do not
replace passive ledger evidence with a live quota probe. Preserve both state
sources during deploy/rollback; never reset or edit the ledger merely to make a
validation pipeline pass. Check quota locally before an authorized live
operation and stop on a 402/429 or accounting inconsistency.

## Change and recovery

1. Establish environment, identity, user/data impact, recovery point, stop
   conditions, and explicit approval.
2. Verify the new copy offline and run the ordinary probe on its target host.
3. Stop the client/adapter so the MCP and browser exit cleanly.
4. Preserve all ignored local state and secrets.
5. Replace source/dependencies without creating a second profile owner.
6. Start one client/adapter and verify identity, policy, tools, status, and logs.
7. Stop on profile-lock ambiguity, credential exposure, quota guard failure,
   unexpected cloud mutation, or unexpected external exposure.

Upgrade and rollback **replace code and never delete runtime state by default**.
Keep, from `operations/RELEASE.md`'s denylist, at least:
`onshape_browser_mode/config/browser-state.json`,
`onshape_browser_mode/config/browser.local.toml`,
`onshape_browser_mode/user_data/` (the persistent profile and its owner),
`onshape_browser_mode/outputs/`,
`onshape_rest_api_mode/config/onshape-credentials.json`,
`onshape_rest_api_mode/config/onshape-state.json`,
`onshape_rest_api_mode/config/api-usage.json` (the quota ledger),
`onshape_rest_api_mode/outputs/`, and
`mcp_main/win/mcp/config/tool_views.local.toml`. A profile, credential file,
ledger, or output directory is not "cleanup".

After any change, re-check the **deployed generation**: the generated
runtime-policy companion must report the same revision string as
`mcp_main/win/mcp/runtime_prompt.py` (`RUNTIME_PROMPT_REVISION`; the current
canonical source is `1.3.0/production-roles-v8`). The revision string is the
check; a deployment whose companion still reports an older revision lags the
checkout (`../verification/MCP_CLIENT_COMPATIBILITY.md`).

A STEP export that failed mid-wait needs no destructive cleanup. Read the
structured result before retrying: a failure whose phase is
`wait_for_dialog_hidden` with `stagingComplete: true` means the STEP and its
manifest are already on disk and reusable (for example by
`browser_build_geometry_package`); a same-`export_id` retry then reports
`alreadyStaged` success. Only pass `browser_export_step(overwrite=true)` to reuse
a staging directory a failed run left **partial**; without it a retry refuses
rather than overwriting leftovers, which is the safer default. Never delete files
under the output root by hand to force a retry, and treat `recovery` in the result
as a list of candidate next actions rather than a completed rollback.

For rollback, restore the source and preserved local state from the recovery
point, then restart one owner. Do not delete browser profiles or ledgers as
cleanup. If the external bridge fails, follow its runbook; never reactivate the
retired project relay under `docs/history/legacy/`.
