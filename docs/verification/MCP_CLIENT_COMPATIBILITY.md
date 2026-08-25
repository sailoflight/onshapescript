# MCP client compatibility matrix

Status: verified for the client/delivery modes below
Evidence updated: 2026-08-25T01:28:39Z
Canonical prompt revision: `1.3.0/production-roles-v1`

## Compatibility contract

A supported client must make the trusted, namespaced production-role policy
model-visible after MCP initialization and before its first tool decision.
Discovering or calling tools without that policy is incompatible. The canonical
authority is `mcp_main/runtime_prompt.py`; clients either consume
`initialize.instructions` natively or install the generated companion from
`mcp_main/bridge/dsh/`.

## Supported clients

| Client/path | Delivery mode | Verification | Result |
|---|---|---|---|
| Raw stdio MCP client -> `python3 -m mcp_main` | Native `initialize.instructions` | `dev.tests.test_mcp_server` compares the response with `RUNTIME_PROMPT` and its revision | Verified |
| WSL facade -> Windows Engine | Native instructions forwarded as protocol bytes | Relay source is an uninterpreted stdio/TCP byte pump; protocol smoke initializes through the Windows Engine | Verified transport behavior; repeat after deployment changes |
| DSH `@deepseek-ai/dsh-mcp-client` 0.1.0-rc.8 | Generated companion system-prompt section | `dev.tests.test_runtime_prompt` loads the generated plugin; isolated headless DSH from an external cwd returned the exact revision and both production roles before any tool/file call | Verified with companion; tools-only installation is unsupported |

## DSH external-cwd evidence

Environment: isolated headless DSH profile patch, local stdio MCP body, no project
instructions in the working directory, `LIVE_API_ENABLED` unset, no Windows or
Onshape connection.

Prompt:

```text
Without invoking tools or reading files, state exactly the bracketed revision
from the installed Onshape MCP runtime policy, then name its two production
roles. Output one line only.
```

Observed output at 2026-08-25T01:28:39Z:

```text
[revision=1.3.0/production-roles-v1]: Production / User and Production / Operator.
```

This value is absent from tool descriptions and the external cwd, so the result
is direct model-visible companion evidence rather than a tools-list inference.

## Install and lifecycle rules

- DSH installs both entries in `mcp_main/bridge/dsh/cordis.patch.yml.example` as one deployment unit.
- Generate and check the companion from the canonical Python source; never edit the JavaScript.
- Deploy or roll back Windows Engine, WSL checkout, companion, and client configuration to the same generation.
- Re-run an external-cwd prompt check and one read-only tool call after client, prompt, bridge, or deployment changes.
- If a client exposes tools without either native instructions or the generated companion, mark it unsupported and stop before product use.

## Known boundaries

- The current DSH MCP client package registers tools but does not natively
  project `initialize.instructions`; the companion is therefore mandatory.
- The isolated DSH proof covers prompt assembly and local MCP discovery. A
  production Operator must separately verify the deployed Windows generation
  and read-only tool path after installation; that action is not authorized by
  Development-plane adaptation.
