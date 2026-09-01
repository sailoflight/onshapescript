# Onshape ordinary stdio MCP runbook

Audience: Production / Operator

This runbook covers installation, process/profile ownership, client adaptation,
health, restart, and recovery. It does not authorize production Onshape calls,
credential access, or model/cloud mutations.

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

## Preconditions

- Deployment copy on the browser/REST host, conventionally `C:\MCP\onshapescript`.
- Python and installed Chrome/Edge.
- Interactive desktop access for initial Onshape SSO/2FA.
- Credentials only in module-owned ignored configuration.
- Recovery point for browser profile, local config, REST state/credentials,
  quota ledger, outputs, and client profile/package state.

## Install

```powershell
cd C:\MCP\onshapescript
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r onshape_browser_mode\requirements-windows.txt
```

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
python3 mcp_main/dsh/build_runtime_prompt_companion.py --check
python3 -m unittest dev.tests.test_runtime_prompt -v
```

Back up profile patch/package state before changes. Verify model-visible policy,
not merely listed tools. Compatibility evidence is in
`../verification/MCP_CLIENT_COMPATIBILITY.md`.

## Initial login

An authorized MCP User invokes `browser_session(action=login)`. A human completes
SSO/2FA in the visible browser. Never automate SSO/2FA or place credentials in
client arguments, prompts, tool calls, logs, or fixtures.

## Health

Healthy means:

- one MCP process generation owns the profile;
- initialize returns expected identity and runtime-policy revision;
- tools/list and read-only status calls succeed with protocol-clean stdout;
- browser status is sane and credentials are not exposed;
- REST quota/state guards remain intact;
- any external bridge reports its own registry/nodes/link healthy.

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

For rollback, restore the source and preserved local state from the recovery
point, then restart one owner. Do not delete browser profiles or ledgers as
cleanup. If the external bridge fails, follow its runbook; never reactivate the
retired project relay under `docs/history/legacy/`.
