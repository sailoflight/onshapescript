# Windows Onshape page launch field evaluation

Mode: scenario-validation
Environment: development
Data: approved-real-data-copy (approved existing test identity; no account data read)
Evaluated at: 2026-08-24T09:47:06Z
Version/range: Onshape MCP server 1.3.0; MCP protocol 2025-06-18; Windows/WSL bridge on port 8766

## Traceability

| Scenario/requirement | Contract/usage source | Acceptance or exploration question |
|---|---|---|
| Launch a visible Onshape page through the real Windows bridge | `../usage/MCP_CONSUMER.md` browser-operation boundary; `evidence/windows-onshape-page-20260824.json` | Can the WSL facade reach the Windows Engine, start visible Edge, and load an Onshape page without REST calls or cloud writes? |

## Permission boundary

The user explicitly approved Field Evaluator use of the existing Windows browser
identity for this scenario. Network access to the public Onshape page was
allowed. Onshape REST calls, document inspection, credential output, automated
login, clicks, typing, cloud writes, and irreversible actions were forbidden.
The request budget was zero REST API calls and zero cloud mutations.

## Setup and procedure

1. Started an MCP client against `mcp_main/bridge/mcp_tcp_bridge.py` on port 8766.
2. Initialized MCP protocol version 2025-06-18.
3. Called `browser_session(action="status")`.
4. Called `browser_session(action="login")`, whose contract only reuses a valid session, tries the saved Onshape entry URL, or opens the public sign-in page.
5. Called `browser_session(action="status")` again and reported only sanitized page/session classification.

No step invoked an Onshape REST tool or a browser click/type/eval mutation.

## Observations and evidence

| Step/time | Input/action | Observed output/effect | Evidence reference |
|---|---|---|---|
| 2026-08-24T09:47:06Z | MCP initialize through WSL relay | Windows Engine returned server `onshape-branch-cable-trophy` 1.3.0 and protocol 2025-06-18 | `evidence/windows-onshape-page-20260824.json` server/transport fields |
| 2026-08-24T09:47:06Z | `browser_session(login)` | Visible headed Edge opened `cad.onshape.com/signin`; status became `awaiting_login` | Same evidence, `browserObservation` |
| 2026-08-24T09:47:06Z | Side-effect accounting | No login automation, document access, REST tool, browser mutation tool, or cloud write action was invoked | Same evidence, `invocationAccounting`; this is transcript-derived, not a server-side audit log |

## Findings

| Finding | Class | Evidence | Impact/follow-up role |
|---|---|---|---|
| WSL relay, Windows Engine, Playwright, visible Edge, and public Onshape page loading worked together | environment | Successful initialized session and sanitized browser status | Operator may use the runbook for deployment health |
| Account-page/session restoration was not verified because the browser stopped at manual sign-in | test gap | `login_confirmed=false`, `human_action_required=true` | A separately approved Field Evaluator scenario may verify post-login state |
| Page launch success does not authorize document or model mutation | test gap | Permission boundary and zero-write result | Production / User must obtain separate mutation authority and confirmation |

## Cleanup, limitations, and residual risk

No test documents or cloud resources were created, so no data cleanup was
required. The visible browser was later closed during a separately authorized
Operator bridge restart. This scenario proves browser-host availability only;
it does not prove login persistence, document access, browser selectors, or any
product mutation workflow.
