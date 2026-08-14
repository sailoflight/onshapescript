# Onshape REST API reference

The MCP server answers Onshape REST questions offline from two vendored
sources: the **live OpenAPI definition** served at
`https://cad.onshape.com/api/openapi` (`reference/onshape-api/`) and the
**official developer docs** for authentication and error handling
(`reference/onshape-api-docs/`). See `docs/mcp-server.md` for the tool behavior
table; this page covers the data, its coverage, and the gaps that remain for
doing real API *operations*.

## Data

| File | Contents |
|---|---|
| `reference/onshape-api/openapi.json` | The raw OpenAPI 3.0.1 spec, pulled live from `/api/openapi` by `scripts/fetch_onshape_api.py` (authenticated). Always the running deployment's version. |
| `reference/onshape-api/api_index.json` | Flattened by `scripts/build_onshape_api_index.py`: `tags`, `endpoints` (path, method, operationId, summary, parameters, **requestBody**, **security**, responses), `schemas`, plus `specVersion`, `baseUrl`, `securitySchemes`, `globalSecurity`, `sourceSha256`. |
| `reference/onshape-api/api_quick.json` | One line per endpoint (path/method/operationId/summary/`hasRequestBody`) for cheap machine indexing. |
| `reference/onshape-api-docs/errors.html` `limits.html` `oauth.html` `apikeys.html` | Public Onshape developer docs (GitHub Pages, plain HTTP — **zero API-token cost**): response codes, rate/annual limits, the OAuth2 workflow, and API-key usage. |
| `reference/onshape-api-docs/api_docs.json` | Those pages parsed into heading sections with typed blocks, plus a flattened `errorCodes` table. |

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
| **Workflow guides** | The OpenAPI gives endpoints, not how to *combine* them (upload FeatureScript → compile → instantiate → validate). The project's own `operations.py` + `examples/` encode the worked version of this. | `onshape-public.github.io/docs/api-adv/` + local code |

### Conceptual (P2, lower urgency)

- Object model: Document → Element hierarchy, WVM (workspace/version/
  microversion) semantics, the BT* type system, units/coordinate conventions —
  partly implicit in the spec, worth a distilled cheat-sheet.
- `Changelog` (`/docs/changelog/`) to judge what changed between REST versions.

## Updating

```bash
python3 scripts/fetch_onshape_api.py          # needs onshape-credentials.json
python3 scripts/build_onshape_api_index.py
python3 scripts/fetch_onshape_api_docs.py     # public pages, no credentials
python3 scripts/build_onshape_api_docs_index.py
```

`fs_check_version(check_latest=true)` probes `/api/build` (a tiny JSON) to
report whether the vendored REST spec is behind the live server.
`fs_update_reference(confirm_mutation=true, include_onshape_api=true)` refreshes
everything — spec, auth/error docs, and all indexes — in one call.
