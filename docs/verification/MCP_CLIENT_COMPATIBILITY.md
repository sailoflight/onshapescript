# MCP client compatibility matrix

Status: repository delivery paths verified; external DSH model evidence is versioned below
Evidence updated: 2026-08-25T01:28:39Z
Current canonical source revision: `1.3.0/production-roles-v5`
Last external-cwd DSH evidence revision: `1.3.0/production-roles-v1`

## Compatibility contract

A supported client must make the trusted, namespaced production-role policy
model-visible after MCP initialization and before its first tool decision.
Discovering or calling tools without that policy is incompatible. The canonical
authority is `mcp_main/win/mcp/runtime_prompt.py`; clients either consume
`initialize.instructions` natively or install the generated companion from
`mcp_main/dsh/`.

## Supported clients

| Client/path | Delivery mode | Verification | Result |
|---|---|---|---|
| Raw stdio MCP client -> `python3 -m mcp_main.win.mcp` | Native `initialize.instructions` | `dev.tests.test_mcp_server` compares the response with `RUNTIME_PROMPT` and its revision | Verified |
| Independently installed cross-host adapter | Byte-transparent native instructions | Adapter project's protocol/lifecycle suite plus target-host ordinary MCP probe | External deployment evidence; not owned by this repository |
| DSH `@deepseek-ai/dsh-mcp-client` 0.1.0-rc.8 | Generated companion system-prompt section | `dev.tests.test_runtime_prompt` loads the current generated plugin; isolated headless DSH from an external cwd previously returned revision `production-roles-v1` and both production roles before any tool/file call | Delivery mechanism verified; repeat the external-cwd check after deploying the current v5 generation |

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

This historical value is absent from tool descriptions and the external cwd, so
the result is direct model-visible companion evidence rather than a tools-list
inference. It proves the delivery mechanism at v1, not that a particular
production profile has installed the current v5 companion; that remains an
Operator deployment check.

## Install and lifecycle rules

- DSH installs both entries in `mcp_main/dsh/cordis.patch.yml.example` as one deployment unit.
- Generate and check the companion from the canonical Python source; never edit the JavaScript.
- Deploy or roll back ordinary MCP, companion, client, and external-adapter registration to the same generation.
- Re-run an external-cwd prompt check and one read-only tool call after client, prompt, adapter, or deployment changes.
- If a client exposes tools without either native instructions or the generated companion, mark it unsupported and stop before product use.

## Known boundaries

- The current DSH MCP client package registers tools but does not natively
  project `initialize.instructions`; the companion is therefore mandatory.
- The isolated DSH proof covers prompt assembly and local MCP discovery. A
  Production Operator separately verifies the deployed ordinary MCP and any
  external adapter's read-only path after installation; that action is not
  authorized by Development-plane adaptation.
