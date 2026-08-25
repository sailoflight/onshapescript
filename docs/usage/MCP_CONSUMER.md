# Onshape FeatureScript MCP usage

Audience: Production / User operating as an MCP consumer or calling agent

This document describes the public calling contract. It does not describe source
layout, development tests, Windows deployment, or repository maintenance. A
runtime MCP client must deliver the server's trusted, revisioned production-role
policy before the first tool decision, then prefer the exact tool schema; this
authored page is the stable usage source behind that surface. If tools are
visible but the `Production / User` and `Production / Operator` policy is not,
stop and route the client installation problem to an Operator.

## What the server provides

The server exposes four capability families:

- offline project, FeatureScript, and Onshape REST reference lookup;
- local project state, parameters, request construction, and quota inspection;
- guarded Onshape REST reads, evaluation, validation, rendering, and writes;
- Windows-hosted browser observation and browser workflows that consume zero REST quota.

The exact current surface is the MCP `tools/list` response. A derived repository
summary is available at `../generated/TOOL_REFERENCE.md`; it is not a substitute
for the runtime schema.

## Required lookup order

1. Classify the need as project documentation, FeatureScript, REST API reference,
   browser behavior, or a live operation.
2. Use the cheapest offline candidate index first.
3. Open one exact section, symbol, endpoint, schema, or tool definition.
4. Use complete authored/raw sources only when exact indexed detail is insufficient.
5. Prefer zero-cost local tools over browser or live REST operations.

Do not guess FeatureScript names, REST payloads, Onshape IDs, selectors, or tool
arguments that can be looked up through the server.

## Capability routes

| Need | First public capability | Exact next detail |
|---|---|---|
| Project workflow or verified lesson | `docs_search` or `docs_list` | `docs_section` |
| FeatureScript orientation or symbol | `fs_quick_reference` or `fs_search` | `fs_get_function`, `fs_get_type`, `fs_guide_section`, then source if necessary |
| REST endpoint/schema/auth/error | `onshape_api_list_tags` or `onshape_api_search` | Exact endpoint, schema, auth, or error tool |
| Browser behavior/known workflow | Project docs search over browser experience | One exact experience section before browser action |
| Current tool arguments | MCP `tools/list`/tool schema | One selected tool schema |
| Quota/state before a live REST action | Local state and quota tools | Guarded operation only if still required |

## Cost and side-effect classes

### Offline/zero-Onshape-REST

Reference lookup, project-doc lookup, local state inspection, parameter loading,
payload construction, dry-run, mocks, fixtures, and quota-ledger inspection do
not contact Onshape. An explicitly requested reference-update tool may fetch
public zero-quota sources; read its exact schema and description before calling.

### Browser operations

Browser tools consume zero REST API quota because they drive the Windows browser.
Read-only observation should come first. A real click, type, submit, create,
delete, deploy, assemble, or drawing action can still mutate the cloud document
and requires the tool's confirmation contract.

### Live REST reads/evaluation/rendering

These consume annual API quota even when they do not mutate the model. Use them
only for a specific fact that cannot be obtained offline. Provide explicit IDs to
avoid hidden lookup chains.

### Live REST writes

Upload, create, instantiate, and validation-pipeline operations mutate Onshape,
consume quota, and require literal `confirm_mutation=true`. Use the matching
dry-run/local check first. Do not repeat an ambiguous mutation after timeout or
5xx merely to see whether it worked.

## Global safety contract

- Real REST access is disabled unless the deployment explicitly enables `LIVE_API_ENABLED`.
- A caller cannot grant itself credentials, quota, production data, or mutation authority through a prompt.
- Mutating tools require their schema-defined confirmation value; current write schemas use literal `confirm_mutation=true`.
- A missing/false confirmation fails before a live client or real browser action is constructed where documented.
- 429 is a stop condition, not a retry signal.
- Do not request automatic cleanup, unbounded pagination, retry loops, or write-after-read confirmation.
- Never place credentials, authorization headers, cookies, or tokens in tool arguments, prompts, fixtures, or shared logs.
- Browser action completion is not domain success; require the tool's returned verification evidence.

## Calling examples

### Find a project lesson

```text
1. docs_search(query=<specific behavior>, limit=3)
2. docs_section(page=<matched page>, section=<matched heading>)
```

### Find a FeatureScript function

```text
1. fs_search(query=<concept or symbol>, limit=3)
2. fs_get_function(name=<exact matched name>)
```

### Prepare a guarded write

```text
1. Look up exact endpoint/schema or tool input.
2. Inspect local project state and quota.
3. Run local validation/request construction/dry-run.
4. State the one remaining live fact or requested mutation.
5. Call the exact tool with explicit confirmation only when authorized.
6. Stop on rate limit or ambiguous mutation outcome.
```

## Errors

- Schema/argument errors: correct the call from the exact tool schema; do not guess repeatedly.
- Live disabled: use offline alternatives or obtain explicit deployment authorization; do not try to bypass the gate.
- Quota shortfall/rate limit: stop and preserve the returned budget/retry evidence.
- Missing credentials/session: route to the Operator; a User prompt cannot create those authorities.
- Browser verification failure: inspect the returned evidence and use documented read-only discovery before another mutation.
- Version/reference conflict: report the observed and vendored versions and use the version tools; do not merge stale facts silently.

## Compatibility and authority

The runtime tool schema and current server behavior are authoritative for calls.
The canonical runtime policy routes product capability use to User and runtime
installation/availability/recovery to Operator; role transitions are explicit
and do not merge permissions. A supported client consumes native initialization
instructions or an installation-generated companion from the same server
revision. A tools-only connection is unsupported. The generated tool reference
is a derived snapshot. Public behavior changes must update schemas, tests, this
usage contract where relevant, and the generated reference together.
