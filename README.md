# Onshape FeatureScript MCP server

A local Model Context Protocol server that helps agents look up Onshape
FeatureScript and REST references offline, construct and validate FeatureScript
workflows, and use guarded REST or Windows-hosted browser operations when local
evidence is insufficient.

The project vendors upstream reference material because the FeatureScript
standard library is poorly represented in model training data. Normal lookup is
index-first and offline. Real REST access is disabled by default and must never
be used for trial-and-error development.

## Start by role

| Role | Start here |
|---|---|
| Repository Developer/Maintainer/Reviewer | `AGENTS.md`, then `docs/INDEX.md` |
| Field Evaluator | one approved scenario under `docs/evaluation/` |
| Production / User (MCP consumer) | runtime production-role policy, `docs/usage/MCP_CONSUMER.md`, and tool schemas |
| Windows/WSL Operator | `docs/operations/MCP_RUNBOOK.md` |
| FeatureScript/REST/browser knowledge lookup | `onshape_docs/README.md` |
| Example model user | `examples/branch-cable-trophy/README.md` |

Do not load every role's documentation. The repository governance package is an
initialization/adaptation dependency, not ordinary MCP User context.

## Architecture

```text
mcp_main/               MCP protocol, registered schemas/handlers, DSH companion
onshape_docs/            offline documentation, reference, indexes, query tools
onshape_rest_api_mode/   REST transport, live/quota guards, state and outputs
onshape_browser_mode/    Windows Playwright/Edge session and UI workflows
examples/                worked FeatureScript models and their inputs
dev/                     executable tests, probes, fixtures and capture scripts
docs/                    role routing, architecture, module contracts and verification
```

Current cross-module boundaries are documented in
`docs/architecture/OVERVIEW.md`. Cross-host transport is supplied by an
independently installed `win-wsl-mcp-bridge`; this repository intentionally owns
no relay, listener, launcher, registry, or fixed bridge port.

## MCP entrypoint

Run the ordinary stdio MCP on the host that owns the configured browser/profile
and local REST state:

```bash
python3 -m mcp_main.win.mcp
```

A cross-host client registers that command with an independently installed
`win-wsl-mcp-bridge` under id `onshape`, then invokes
`win-wsl-mcp-wsl connect onshape`. See `docs/operations/MCP_RUNBOOK.md` and
`mcp_main/dsh/cordis.patch.yml.example`. The external bridge owns transport,
registry, listener, supervision, and reconnect behavior.

The MCP returns the canonical `Production / User` and `Production / Operator`
policy during initialization. Clients without native instructions projection
must install the generated companion under `mcp_main/dsh/`.

## Capabilities

- FeatureScript quick search and exact function/type/guide/source lookup.
- Offline Onshape REST endpoint, schema, auth, and error lookup.
- Indexed project workflow, verified experience, evidence, and example lookup.
- Local project state, parameters, payload construction, and quota inspection.
- Guarded REST evaluation, validation, rendering, and explicit mutations.
- Zero-REST-quota browser observation and confirmed browser workflows.

The registered schema and handler maps are authoritative. The derived current
summary is `docs/generated/TOOL_REFERENCE.md`; do not maintain a second manual
tool count here.

## Safety defaults

- Keep `LIVE_API_ENABLED` unset for development and regression tests.
- Use local docs, code, tests, mocks, fixtures, replay, and dry-run first.
- A live request needs one unresolved fact and a hard request budget.
- Mutating tools require explicit confirmation.
- Browser operations cost zero REST quota but can still modify cloud data.
- Credentials, authorization headers, cookies, and tokens never belong in
  prompts, tool inputs, committed fixtures, or protocol output.

Detailed development constraints remain in `AGENTS.md` and `CLAUDE.md`. Public
calling constraints are in the MCP User document.

## Development verification

Run offline with `LIVE_API_ENABLED` unset:

```bash
python3 -m unittest discover -s dev/tests -v
python3 -m py_compile mcp_main/*.py mcp_main/dsh/*.py mcp_main/win/*.py mcp_main/win/mcp/*.py onshape_browser_mode/*.py onshape_docs/query/*.py onshape_docs/scripts/*.py onshape_rest_api_mode/*.py examples/branch-cable-trophy/scripts/*.py
python3 mcp_main/dsh/build_runtime_prompt_companion.py --check
```

The complete change-to-check mapping is `docs/verification/MATRIX.md`.

After changing indexed public documentation:

```bash
python3 onshape_docs/scripts/build_docs_index.py
python3 onshape_docs/verification/verify_docs.py
```

After changing registered tool schemas or handlers:

```bash
python3 onshape_docs/scripts/build_tool_reference.py
python3 onshape_docs/scripts/build_tool_reference.py --check
```

## Example

`examples/branch-cable-trophy/` is the maintained FeatureScript example and local
validation fixture. Its parameter sets and validation contract belong to the
example, not to repository-root configuration.
