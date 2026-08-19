# Onshape REST API reference

The MCP server answers Onshape REST questions offline from two vendored
sources: the **live OpenAPI definition** served at
`https://cad.onshape.com/api/openapi` (raw tier 0:
`onshape_docs/reference/raw/onshape-api/`) and the **official developer docs** for
authentication and error handling (`onshape_docs/reference/raw/onshape-api-docs/`). The
tiered indexes the tools actually read are under `onshape_docs/reference/index/onshape-api/`
and `onshape_docs/reference/index/onshape-api-docs/` (see `onshape_docs/guide/mcp-server.md` for the tool
behavior table; this page covers the data, its coverage, and the gaps that
remain for doing real API *operations*).

## Data

| File | Contents |
|---|---|
| `onshape_docs/reference/raw/onshape-api/openapi.json` | The raw OpenAPI 3.0.1 spec, pulled live from `/api/openapi` by `onshape_docs/scripts/fetch_onshape_api.py` (authenticated). Always the running deployment's version. |
| `onshape_docs/reference/index/onshape-api/api_index.json` | Flattened by `onshape_docs/scripts/build_onshape_api_index.py` (tier 2): `tags`, `endpoints` (path, method, operationId, summary, parameters, **requestBody**, **security**, responses), `schemas`, plus `specVersion`, `baseUrl`, `securitySchemes`, `globalSecurity`, `sourceSha256`. |
| `onshape_docs/reference/quick/onshape-api/api_quick.json` | One line per endpoint (path/method/operationId/summary/`hasRequestBody`) for cheap machine indexing (tier 1). |
| `onshape_docs/reference/raw/onshape-api-docs/errors.html` `limits.html` `oauth.html` `apikeys.html` | Public Onshape developer docs (GitHub Pages, plain HTTP — **zero API-token cost**): response codes, rate/annual limits, the OAuth2 workflow, and API-key usage. |
| `onshape_docs/reference/index/onshape-api-docs/api_docs.json` | Those pages parsed into heading sections with typed blocks, plus a flattened `errorCodes` table. |

Current snapshot: REST API **1.219.86205**, 302 operations, 1226 schemas,
42 tags, base URL `https://cad.onshape.com/api/v16`.

## What is covered

- Every endpoint: method, path, operationId, summary, description, parameters
  (name, path/query/header location, required, type, enum/default), and
  response status codes with their schema references.
- **Request bodies** for the 104 POST operations that have one (`schemaRef` or
  an inline schema), so creating/updating resources is actionable.
- **Authentication requirements** per operation (which scheme) plus the
  `securitySchemes` details (OAuth2 authorizationCode flow URLs + scopes, Basic
  API-key auth) and the versioned base URL.
- The 1226 response/request schemas (`BTDocumentElementInfo`, ...) referenced
  by the operations.
- **Authentication procedure** (`onshape_api_auth`): the OAuth2
  authorization-code workflow in six steps (register app → authorize → exchange
  code → use → refresh → grant) and API-key usage, with full section text
  (including code) on demand.
- **HTTP errors + limits** (`onshape_api_error_codes`): all 16 documented
  response codes with category/description/next steps, plus the rate-limit and
  annual-limit semantics (429 `X-Rate-Limit-Remaining` / `Retry-After`).

## Remaining gaps

### Recommend vendoring next

| Gap | Why it matters for operations | Source |
|---|---|---|
| **Workflow guides** | The OpenAPI gives endpoints, not how to *combine* them (upload FeatureScript → compile → instantiate → validate). The project's own `onshape_rest_api_mode/operations.py` + `examples/` encode the worked version of this. | `onshape-public.github.io/docs/api-adv/` + local code |

### Conceptual (P2, lower urgency)

- Object model: Document → Element hierarchy, WVM (workspace/version/
  microversion) semantics, the BT* type system, units/coordinate conventions —
  partly implicit in the spec, worth a distilled cheat-sheet.
- `Changelog` (`/docs/changelog/`) to judge what changed between REST versions.

## API-quota budgeting

Onshape has **no public quota-query endpoint** (verified against the full
OpenAPI spec), so the budget is built passively at zero extra API cost:

- Every response is ledgered in `config/api-usage.json` (gitignored): 2xx/3xx
  count toward the annual limit, 4xx/5xx do not, and the `X-Rate-Limit-Remaining`
  header is captured each time. A 402 response is the server's real
  "annual limit exhausted" signal.
- Configure the budget in `config/onshape-state.json`:
  `"apiQuota": {"accountType": "professional"}` maps to the official annual
  limit (enterprise 10000 / professional 5000 / standard 2500), or
  `{"annualLimit": N}` directly.
- `onshape_api_quota` reports configured limit, consumed, remaining, and how
  many validation-pipeline runs fit (13 calls with render, 8 without).
- `onshape_run_validation_pipeline` runs a preflight check before mutating and
  blocks with the shortfall if the budget would be exhausted. `render_previews:
  false` drops the five render calls (13 → 8).

The ledger is an estimate — other clients and UI usage also consume the server
limit — so treat it as a budget guardrail, with 402 as the authoritative signal.

## Updating

```bash
python3 onshape_docs/scripts/fetch_onshape_api.py          # needs onshape-credentials.json
python3 onshape_docs/scripts/build_onshape_api_index.py
python3 onshape_docs/scripts/fetch_onshape_api_docs.py     # public pages, no credentials
python3 onshape_docs/scripts/build_onshape_api_docs_index.py
```

`fs_check_version(check_latest=true)` probes `/api/build` (a tiny JSON) to
report whether the vendored REST spec is behind the live server.
`fs_update_reference(confirm_mutation=true, include_onshape_api=true)` refreshes
everything — spec, auth/error docs, and all indexes — in one call.
