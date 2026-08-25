# Project documentation index

This is the repository-level routing map. Read one role or task entry, then the
smallest exact module or verification section. Domain knowledge remains under
`onshape_docs/` and should be queried through its indexes before full sources.

## Read by role

| Role | Start here | Do not preload |
|---|---|---|
| Developer | `development/START.md` | Production usage, operations, evidence, and raw reference material |
| Maintainer | `development/START.md` or one matched module contract | Production usage, operations, and package-adaptation material after adaptation |
| Reviewer | `verification/MATRIX.md`, the target diff, and its module contract | Production instructions and unrelated modules |
| Field Evaluator | one approved scenario under `evaluation/` | Production operations, credentials, and repository source beyond evidence needs |
| Production / User (MCP consumer) | `usage/MCP_CONSUMER.md` or the MCP tool schemas | Development, internal architecture, operations, and roadmap |
| Operator | `operations/MCP_RUNBOOK.md` | Development detail, User prompts, and roadmap |

## Read by task

| Need | First read | Next exact detail |
|---|---|---|
| Modify repository code | `development/START.md` | One file under `modules/`, then matched code and tests |
| Understand system boundaries | `architecture/OVERVIEW.md` | One module contract or linked bridge architecture |
| Select verification | `verification/MATRIX.md` | Exact test, checker, fixture, or script |
| Verify MCP client prompt compatibility | `verification/MCP_CLIENT_COMPATIBILITY.md` | Canonical prompt source, generated companion, then one external-cwd smoke |
| Evaluate a non-production browser scenario | one approved file under `evaluation/` | Matching public usage contract and sanitized evidence only |
| Use the MCP server | `usage/MCP_CONSUMER.md` | One tool schema or generated tool entry |
| Deploy, restart, or recover the bridge | `operations/MCP_RUNBOOK.md` | Exact Windows bridge document or script |
| Query FeatureScript, REST, or browser knowledge | `../onshape_docs/README.md` | One indexed section, symbol, endpoint, schema, or evidence record |
| Trace an old development decision or log | `history/TRACEABILITY.md` | Current owning architecture, module, experience, verification, operations, or roadmap section |
| Work in the development lab | `development/LAB.md` | One test, probe, capture fixture, or tool under `dev/` |
| Inspect the generated tool surface | `generated/TOOL_REFERENCE.md` | Authoritative schema and handler in `mcp_main` |

## Project-level ownership

| Area | Owns | Does not own |
|---|---|---|
| `development/` | Repository-wide development entry and the `dev/` executable-lab map | Tests, probes, fixtures, or historical plans themselves |
| `architecture/` | Current cross-module boundaries and invariants | Future plans and experiment logs |
| `modules/` | Module responsibilities, exclusions, entrypoints, and verification | Per-file narration or generated API tables |
| `verification/` | Change type to real offline/sandbox/live validation and supported-client compatibility | Historical test output |
| `evaluation/` | Approved non-production scenario procedure, sanitized observations, and limitations | Product contract, production authority, or unsanitized evidence |
| `usage/` | Stable MCP User contract | Internal implementation and deployment steps |
| `operations/` | Operator deployment, health, restart, and recovery | User product workflows and development plans |
| `history/` | Archived development records and their migration/provenance map | Current behavior, operations, or future capability claims |
| `generated/` | Derived tool reference | Hand-authored authority for schemas or handlers |

## Existing domain documentation

`onshape_docs/README.md` remains the routing and ownership map for FeatureScript,
REST API, browser experience, verification evidence, and vendored reference
material. `development/LAB.md` is the directory contract for tests, probes,
fixtures, recordings, and development-only experiments. This project index
links those owners instead of duplicating their contents.

## Source precedence

1. Current code and offline tests define implemented behavior.
2. Public tool schemas and registries define the callable MCP surface.
3. This directory defines current project and module boundaries.
4. `onshape_docs/experience/` records reusable verified behavior.
5. `onshape_docs/verification/` records evidence.
6. Roadmaps and plans do not define current behavior.

When sources conflict, report the version and date scope instead of silently
combining them.
