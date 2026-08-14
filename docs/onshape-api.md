# Onshape REST API reference

The MCP server answers Onshape REST questions offline from the **live OpenAPI
definition** served by Onshape at `https://cad.onshape.com/api/openapi`,
vendored under `reference/onshape-api/`. See `docs/mcp-server.md` for the tool
behavior table; this page covers the data, its coverage, and the gaps that
remain for doing real API *operations*.

## Data

| File | Contents |
|---|---|
| `reference/onshape-api/openapi.json` | The raw OpenAPI 3.0.1 spec, pulled live from `/api/openapi` by `scripts/fetch_onshape_api.py` (authenticated). Always the running deployment's version. |
| `reference/onshape-api/api_index.json` | Flattened by `scripts/build_onshape_api_index.py`: `tags`, `endpoints` (path, method, operationId, summary, parameters, **requestBody**, **security**, responses), `schemas`, plus `specVersion`, `baseUrl`, `securitySchemes`, `globalSecurity`, `sourceSha256`. |
| `reference/onshape-api/api_quick.json` | One line per endpoint (path/method/operationId/summary/`hasRequestBody`) for cheap machine indexing. |

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

## Known gaps (for completing real API operations)

### In the spec but not indexed yet

| Gap | Detail | Cost |
|---|---|---|
| Error response shapes | The spec defines a concrete 4xx/5xx body for **0 of 302** operations (282 fall back to a bare `default`), so exact error JSON is not recoverable from it. | Needs an external source. |

### Outside the spec — recommend vendoring next

| Gap | Why it matters for operations | Source (official) |
|---|---|---|
| **OAuth2 flow + API keys** | The spec lists scheme URLs but not the *procedure*: authorize → token exchange → scopes, or creating accessKey/secretKey and Basic auth. This is what a caller needs before the first API call. | `onshape-public.github.io/docs/auth/oauth/` and `/docs/auth/apikeys/` |
| **Error codes + rate limits** | `400/401/403/404/409/429/5xx` semantics, the error JSON envelope, and the `X-Rate-Limit-Remaining` / `Retry-After` 429 behavior are documented only there. | `onshape-public.github.io/docs/api-adv/errors/` and `/docs/auth/limits/` |
| **Workflow guides** | The OpenAPI gives endpoints, not how to *combine* them (upload FeatureScript → compile → instantiate → validate). The project's own `operations.py` + `examples/` encode the worked version of this. | `onshape-public.github.io/docs/api-adv/` + local code |

### Conceptual (P2, lower urgency)

- Object model: Document → Element hierarchy, WVM (workspace/version/
  microversion) semantics, the BT* type system, units/coordinate conventions —
  partly implicit in the spec, worth a distilled cheat-sheet.
- `Changelog` (`/docs/changelog/`) to judge what changed between REST versions.

## Updating

```bash
python3 scripts/fetch_onshape_api.py        # needs onshape-credentials.json
python3 scripts/build_onshape_api_index.py
```

`fs_check_version(check_latest=true)` probes `/api/build` (a tiny JSON) to
report whether the vendored REST spec is behind the live server.
`fs_update_reference(confirm_mutation=true, include_onshape_api=true)` refreshes
everything in one call.
