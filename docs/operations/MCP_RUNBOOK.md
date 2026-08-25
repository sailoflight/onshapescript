# Windows/WSL MCP bridge runbook

Audience: Production Operator

This runbook covers deployment, process health, restart, and recovery. It does
not authorize MCP Users or Development agents to access credentials, production
data, or mutate Onshape.

## Runtime contract

```text
WSL MCP client
  -> mcp_main/wsl/facade/mcp_tcp_bridge.py (stdio <-> 127.0.0.1:8766)
  -> Windows mcp_main/win/bridge/bridge_server.py (persistent dispatch)
  -> mcp_main.win.mcp.server
  -> onshape_browser_mode -> visible Edge browser
```

- The internal transport is loopback-only and must not listen on a public interface.
- The WSL relay is Python stdlib-only and owns no credentials or browser state.
- The Windows body owns Playwright, Edge, the persistent login profile, runtime configuration, credentials, and logs.
- One persistent browser profile may be owned by one process; the bridge permits one client at a time.
- Client socket disconnect/reconnect does not close the Windows browser. Stopping the bridge does.

The detailed deployment scripts remain authoritative in
`../../mcp_main/win/bridge/windows/README.md`.

## Preconditions and access

- Windows deployment copy, conventionally `C:\MCP\onshapescript`.
- Python on Windows and permission to create a virtual environment/task schedule.
- Installed Microsoft Edge or an explicitly configured browser executable.
- Interactive Windows desktop access for initial Onshape login/SSO/2FA.
- Credentials stored only in module-owned ignored configuration files.
- Optional local HTTP proxy configured in ignored
  `onshape_browser_mode\config\browser.local.toml`.

Never place credentials in MCP client arguments, committed environment files,
prompts, tool arguments, logs, or fixtures.

## One-time Windows installation

```powershell
cd C:\MCP\onshapescript
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r mcp_main\bridge\windows\requirements-browser.txt
```

The default browser channel is the installed Edge (`msedge`); the setup does not
need to download another browser.

## Start

Hidden background start:

```powershell
cd C:\MCP\onshapescript
wscript.exe .\mcp_main\bridge\windows\start-bridge-hidden.vbs 8766
```

Foreground diagnosis:

```powershell
.\.venv\Scripts\python.exe mcp_main\bridge\bridge_server.py 8766
```

Expected success signals:

- one bridge process owns loopback port `8766`;
- `mcp_main\bridge\logs\bridge-server.log` records normal startup without a second-profile owner;
- the WSL probe can initialize and list tools;
- browser session status can be inspected without exposing credentials.

## WSL client configuration

The MCP client launches the relay, not the full MCP body:

```json
{
  "mcpServers": {
    "onshape-featurescript": {
      "command": "python3",
      "args": ["/home/<user>/code/onshapescript/mcp_main/wsl/facade/mcp_tcp_bridge.py", "8766"],
      "cwd": "/home/<user>/code/onshapescript"
    }
  }
}
```

Do not use `python3 -m mcp_main.win.mcp` as the WSL browser entry and do not install
Playwright in the WSL relay environment. Initialization must also deliver the
revisioned `Production / User` and `Production / Operator` runtime policy before
the first model tool decision; a client that only lists tools is not healthy.

### DSH client companion

DSH `@deepseek-ai/dsh-mcp-client` 0.1.0-rc.8 registers tools but does not
natively project `initialize.instructions`. Install the MCP client and both
entries in `mcp_main/wsl/dsh/cordis.patch.yml.example`, replacing `<repo>`
with the WSL checkout path. The second entry loads the generated namespaced
prompt companion.

Before changing a DSH profile:

```bash
python3 mcp_main/wsl/dsh/build_runtime_prompt_companion.py --check
python3 -m unittest dev.tests.test_runtime_prompt -v
```

Back up the profile patch/package lock first. Treat the Windows Engine, WSL
checkout, generated companion, and DSH profile as one deployment generation.
The current delivery modes and external-cwd evidence are recorded in
`../verification/MCP_CLIENT_COMPATIBILITY.md`.

## Initial login

Invoke the public browser-session login action from an authorized MCP User. A
visible Edge window opens on Windows; a human completes login, including SSO or
2FA. The dedicated profile is stored under
`onshape_browser_mode\user_data\onshape_profile`.

A client reconnect does not require login while the Windows bridge/browser stays
alive. A Windows reboot or bridge termination closes the browser and can require
an interactive login again.

## Autostart

Use the repository setup entry:

```powershell
mcp_main\bridge\windows\setup-autostart.bat
```

Equivalent PowerShell registration:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\mcp_main\bridge\windows\register-bridge-task.ps1
```

The scheduled task is `OnshapeMCPBridge`. It starts at login and is configured to
restart after failure. Remove it with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\mcp_main\bridge\windows\register-bridge-task.ps1 -Uninstall
```

## Health and observability

Check in this order:

1. `mcp_main\bridge\logs\bridge-server.log`.
2. One bridge process and one automation Edge/profile owner.
3. Loopback port `8766` from the shared Windows/WSL networking model.
4. WSL probe:

```bash
python3 dev/tools/mcp_probe.py
```

5. Read-only MCP initialization, exact runtime-prompt revision, tool listing, and browser-session status.
6. For DSH, an external-cwd model check that returns the prompt revision and both production roles before any tool call.

Protocol stdout must contain JSON-RPC only. Diagnostics belong in stderr or the
bridge log.

## Passive annual-quota calibration

Onshape has no public API that returns annual usage. The local quota report adds
an operator-supplied year-to-date baseline to successful calls observed by the
passive ledger:

```text
consumed = apiQuota.alreadyConsumed + api-usage.json consumed
```

Read the current total from Onshape **My Account -> Developer** without exposing
credentials. When calibrating after the passive ledger already contains calls,
set the baseline in `onshape_rest_api_mode/config/onshape-state.json` to:

```text
apiQuota.alreadyConsumed = UI year-to-date total - ledgerConsumed
```

Set `apiQuota.accountType` (`enterprise`, `professional`, or `standard`) or an
explicit `apiQuota.annualLimit`. Then run the local `onshape_api_quota` report and
confirm `baselineConsumed`, `ledgerConsumed`, `consumed`, and `remaining` agree.
This check performs no network request. Do not copy a historical ledger total
from development logs, and do not send a live request merely to recalibrate the
ledger.

## Recovery

For a stuck bridge, use the hidden restart entry:

```powershell
wscript.exe .\mcp_main\bridge\windows\restart-bridge-hidden.vbs
```

Foreground diagnostic recovery:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\mcp_main\bridge\windows\restart-bridge.ps1
```

The restart procedure terminates the automation Edge/profile owner and old
bridge before starting a new one. Do not start a second bridge against the same
profile. Re-check logs, port, probe, and session status after restart.

## Deployment update

The WSL repository is the development source. Before updating the Windows copy:

1. keep `LIVE_API_ENABLED` unset and run the matching offline tests;
2. verify generated docs/tool reference and the runtime-prompt companion when their authorities changed;
3. back up the Windows code and client profile/configuration as separate rollback points;
4. synchronize only intended source/deployment files, preserving ignored Windows local configuration, credentials, profiles, logs, and runtime state;
5. update the MCP client and generated companion from the same checkout generation;
6. restart the Windows bridge once and reload the client profile once;
7. run read-only initialize/prompt/tools/browser health checks plus the external-cwd prompt check;
8. require separate User authorization for any cloud mutation.

## Failure guide

| Symptom | Check | Action |
|---|---|---|
| WSL relay times out | Windows bridge and port `8766` | Start/restart bridge; do not replace it with a WSL body |
| Second profile/process error | Existing bridge/Edge owner | Stop duplicate; preserve single-owner invariant |
| Hidden start fails | Bridge log | Run foreground diagnostic command |
| Tools list but production-role policy is absent | Client prompt delivery mode and companion revision | Stop product use; install/reload the generated companion from the Engine generation, then repeat external-cwd verification |
| Tools list but browser unavailable | Browser dependency/config/session | Check Windows venv, Edge channel/path, local proxy, then session status |
| Login lost after reboot/restart | Visible Edge session | Perform authorized interactive login again |
| REST live operation blocked | Live gate/quota/config | Keep blocked unless a separately authorized, budgeted live task exists |
| Rate limit | Returned retry/budget evidence | Stop; never retry 429 |

## Destructive and sensitive actions

- Restarting the bridge terminates its Edge process and can end the active Onshape session.
- Browser mutation and live REST mutation require the public tool confirmation contract; Operator access alone does not imply product-mutation approval.
- Never retry an ambiguous mutating timeout/5xx.
- Preserve ignored credentials, browser profile, state, and quota ledger during sync/rollback.
- Do not expose the loopback service publicly.
- Do not inspect or share credential values while diagnosing availability.
