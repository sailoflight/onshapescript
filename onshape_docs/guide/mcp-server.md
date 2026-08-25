# MCP server usage map

This indexed page is the public MCP User entry. It does not contain repository
development, Windows deployment, or internal module instructions.

## Public contract

Read `docs/usage/MCP_CONSUMER.md` for:

- the required offline-first lookup order;
- capability routing;
- REST quota and browser side-effect classes;
- confirmation, error, retry, and credential boundaries;
- minimal calling examples.

Use the revisioned runtime policy delivered by the trusted MCP installation to
select `Production / User` versus `Production / Operator` before the first tool
decision. If tools are present but that policy is absent, stop and route the
client installation to an Operator. Then use the runtime MCP tool schema for
exact arguments. The derived current summary is
`docs/generated/TOOL_REFERENCE.md`; it is generated from the registered schema
and handler maps and must not be edited by hand.

## Role boundary

- Production / User: public usage document, runtime schema, and exact indexed knowledge.
- Operator: `docs/operations/MCP_RUNBOOK.md` outside the public docs index.
- Developer/Maintainer/Reviewer: repository `AGENTS.md` and `docs/INDEX.md`.

A User prompt does not grant production credentials, quota, deployment access,
real data, or mutation authority.

## Lookup order

1. Classify the need as project docs, FeatureScript, REST reference, browser
   behavior, or a live operation.
2. Search the cheapest offline candidate index.
3. Open one exact section, symbol, endpoint, schema, or selected tool schema.
4. Use full authored/raw material only if the exact entry is insufficient.
5. Prefer zero-request capabilities; use browser/live operations only with their
   explicit safety contract.

## Deployment boundary

The Windows/WSL bridge architecture exists to host a persistent browser session,
but deployment details are intentionally excluded from this public guide. Route
availability, startup, credentials, login, and recovery issues to the Operator.
