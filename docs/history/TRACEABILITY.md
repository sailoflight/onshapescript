# Development-history traceability

This page maps the project's long-lived development records to the authority
that owns each conclusion now. It is a provenance and migration map, not a
second architecture, operations, or product contract.

## Reading rule

1. Start here only when tracing why a current boundary exists or where an old
   development note moved.
2. Follow the current authority for implemented behavior, reusable lessons,
   verification, operations, or future work.
3. Read the archived record only when the historical sequence or superseded
   proposal matters.
4. When the archive conflicts with current code/tests or current authority, the
   archive is historical evidence and does not win.

## Source records

| Historical record | Preserved purpose | Current status |
|---|---|---|
| `legacy/DEV_DEVELOPMENT.md` | Browser/MCP architecture decisions, completed tool work, four semantic layers, and the original dynamic-exposure plan | Distilled across architecture, browser module/experience, verification, and roadmap |
| `legacy/ROOT_README.md` | Former mixed repository landing page, configuration, tool inventory, reference layout, startup, example, and tests | Split into role-routed landing, module, generated reference, usage, operations, and verification authorities |
| `legacy/MCP_SERVER_GUIDE.md` | Former mixed User/Operator/Development bridge and tool guide | Split into MCP User contract, Operator runbook, bridge architecture, generated tool reference, and verification matrix |
| `legacy/DEV_README.md` | Former `dev/` landing page and Windows browser setup notes | Replaced by the development-lab contract and Operator runbook; documentation no longer lives in `dev/` |
| `../../onshape_docs/verification/live/README.md` and sibling JSON records | Dated live FeatureScript experiments, quota incidents, outcomes, and raw evidence | Durable conclusions live in experience/root safety authority; raw outcomes remain evidence and dated ledger narration is not current state |

## Topic-to-authority map

| Historical topic | Current authority | Classification |
|---|---|---|
| Windows Engine, WSL stdlib facade, loopback transport, persistent process/session | `../architecture/OVERVIEW.md`, `../../mcp_main/bridge/ARCHITECTURE.md`, `../modules/mcp-main.md` | Implemented architecture |
| Browser runtime ownership, single working page, reconnect persistence, page objects, selectors | `../modules/browser-mode.md`, `../../onshape_docs/experience/browser-automation.md` | Implemented contract plus reusable verified lesson |
| Four browser semantic layers L1-L4, dependency direction, checkpoint/resume, state verification | `../modules/browser-mode.md`, `../../onshape_docs/experience/browser-modeling.md`, `../verification/MATRIX.md` | Implemented contract and verification |
| Windows scheduled task, restart scripts, proxy, deployment health/recovery | `../operations/MCP_RUNBOOK.md`, `../../mcp_main/bridge/windows/README.md` | Operator contract; not development architecture |
| Static MCP schema/handler surface and historical tool counts | Current `mcp_main` schemas plus `../generated/TOOL_REFERENCE.md` | Generated current fact; historical counts are not copied into prose |
| MCP consumer lookup, cost, confirmation, credential, and error boundary | `../usage/MCP_CONSUMER.md` and public tool schemas | Production / User contract |
| REST path ownership, environment overrides, quota gate, passive ledger, state and outputs | `../modules/rest-api-mode.md`; quota calibration in `../operations/MCP_RUNBOOK.md` | Implemented module and Operator contract |
| Reference ownership, lookup-first order, generated indexes, verification | `../../onshape_docs/README.md`, `../development/START.md`, `../verification/MATRIX.md` | Current development contract |
| FeatureScript signature/body/instantiation layers, eval diagnostics, static checker | `../../onshape_docs/experience/featurescript.md`, `../../onshape_docs/verification/README.md` | Reusable conclusion plus evidence |
| 429 no-retry, quota-efficient probes, incremental evidence writes | `../../CLAUDE.md`, `../../onshape_docs/experience/featurescript.md`, `../../onshape_docs/experience/rest-api.md` | Current safety and reusable lesson |
| Dynamic catalog, profiles, bounded exposure, gateway and native modeling | `../roadmap/DYNAMIC_TOOL_DISCOVERY.md` | Proposal only; not implemented behavior |
| Concrete missing browser modeling transactions | `../roadmap/BROWSER_MODELING_GAPS.md` | Current roadmap |
| Four-level FS-mode semantic tool surface focused on FS script mode (deploy/compile-status/symbols/parameter-edit), its Part-Studio coupling points (part context-menu drawing auto-views), and improvement suggestions for existing browser tools | `../roadmap/BROWSER_FS_SEMANTIC_TOOLS.md` | Current roadmap (live-browser evidence 2026-08-25) |
| One-off convergence runs, obsolete tool counts, dated account/ledger snapshots | Archived source or raw verification evidence only | Historical context; deliberately not a current contract |

## Legacy browser/MCP record mapping

| Legacy sections | Disposition |
|---|---|
| `DEV_DEVELOPMENT.md` sections 1-2 | Architecture decisions moved to Overview/module contracts; GBK, thread, SPA login, recovery, and tab-drift lessons moved to browser experience |
| Sections 3-4 | Completed tool behavior is represented by current schemas, browser module entrypoints, generated reference, and verification; deployment details moved to the runbook |
| Section 4.1 | L1-L4 layering and success-verification rules are explicit in the browser module contract and matrix |
| Sections 5.1-5.8 | Unimplemented work is consolidated in the dynamic-discovery roadmap; historical candidate gateway names/defaults remain labeled as unaccepted design inputs |
| Section 6 | Browser zero-REST cost, read-only-first, dry-run, confirmation, and mutation boundaries are in module/User/verification contracts |

## Live verification record mapping

The live directory is evidence, not architecture. The following distinctions are
mandatory:

- The FeatureScript `is*` predicate observations, bound-spec/annotation spec
  emission rule, signature-only `featurespecs` behavior, eval diagnostics, and
  instantiation limitations are distilled into
  `../../onshape_docs/experience/featurescript.md`.
- The exact cross-version import boundary is **unresolved**. Historical results
  suggested a boundary, but persisted corrected probes do not provide an
  unconfounded paired acceptance/rejection result. It must not be stated as a
  verified current fact or re-probed without a separately authorized, budgeted
  unresolved-fact task.
- Dated `Retry-After`, remaining-quota, and campaign ledger totals are snapshots,
  not current health. Current state comes from the local quota authority and
  Operator checks.
- A command preserved in an evidence narrative is not permission to repeat a
  live experiment. Current live gates, request budgets, fixture rules, and
  approval boundaries still apply.
- Persisted JSON results take precedence over post-hoc prose arithmetic when
  they disagree.

## Superseded and retained details

- The former `dev/DEVELOPMENT.md` path is retired; its preserved content is
  `legacy/DEV_DEVELOPMENT.md`, and current development guidance is
  `../development/START.md` plus `../development/LAB.md`.
- Historical `67`-tool and earlier `32`-tool observations remain useful only as
  dated baselines. The current count and schemas are generated.
- The earlier 12-plus-Part-Studio convergence narrative is retained as history;
  current reusable workflow acceptance is fixture/checkpoint based.
- Environment overrides and passive-quota baseline calibration remain
  implemented and therefore are documented in current module/operations
  authority rather than only in the archive.

## Maintenance invariant

A development record is integrated only when each durable item is classified as
one of: current implemented authority, reusable experience, verification
evidence, historical rationale, retired detail, or future proposal. Adding or
moving a development log requires updating this matrix and the project layout
test. Archive files must never become an alternate current contract.
