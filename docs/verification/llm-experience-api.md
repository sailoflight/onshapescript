# LLM experience: Onshape REST API

What a model actually needs to know to call the Onshape REST API correctly.
Every claim below is backed by the verified corpus (`docs/verification/report.json`,
collected by `verify_docs.py` against REST API **1.219.86205**, 302 operations).

## Calling basics

- **Authentication** — two schemes, checked per operation: `OAuth2`
  (authorization-code flow: authorize → exchange → refresh) and `BasicAuth`
  (API key = `accessKey:secretKey`). Nearly every operation requires one; the
  global default is Basic. Get the full workflow from `onshape_api_auth`.
- **Base URL is versioned** — the spec's server is `https://cad.onshape.com/api/v16`,
  but unversioned `/api/...` paths (as the project client uses) also work.
- **Only GET / POST / DELETE exist.** There is no PUT or PATCH in the current
  spec. "Update" endpoints are POSTs (often full-overwrite, e.g. updating
  Feature Studio contents); "remove" is DELETE. Do not invent PUT bodies.

## The dominant parameter patterns

- **`{wvm}` is workspace/version/microversion** — many endpoints take a
  three-part path identity `.../d/{did}/{wvm}/{wvmid}/...` where `{wvm}` is the
  literal `w` | `v` | `m` and `{wvmid}` the corresponding id. This is the
  Onshape way to pin a snapshot; pass `w` + workspaceId for "current".
- **Parameter locations** (verified): path 756, query 717, header only 4. Almost
  everything is path + query; body parameters are OpenAPI `requestBody`, not
  `in: body`.
- **Request bodies** exist on 104 POSTs, **74 (71%) required**. When a POST has
  a body, read it with `onshape_api_endpoint` before writing the call — the
  schema is usually a `$ref` into the 1226 shared schemas (e.g. instantiating a
  feature uses `BTFeatureDefinitionCall-1406`).

## Errors and quota (verified against the official docs)

- **16 documented codes**, 200–503. The two that matter most in practice:
  - `429 Too Many Requests` — rate limited; honor `Retry-After` and
    `X-Rate-Limit-Remaining` (both captured live in `onshape_api_quota`).
  - `402 Payment Required` — **annual API-call limit exhausted**, not a payment
    problem; only the annual reset clears it.
- **4xx/5xx responses do not count against your API quota** — only 2xx/3xx do.
  So probing (which often gets 400/404) is cheap.
- Quota is **annual, by account type**: enterprise 10000 / professional 5000 /
  standard 2500 per user/year. There is no quota-query API; the project tracks a
  passive local ledger (`onshape_api_quota`).

## Official spec gaps to know about (found by verification)

- **Three POSTs have no `summary`/`description` in the official spec**, so the
  docs say nothing about them — infer from the path:
  - `POST /documents/d/{did}/w/{wid}/revertunchangedtorevisions`
  - `POST /documents/d/{did}/w/{wid}/syncAppElements`
  - `POST /partnumber/nextnumbers`
- Otherwise the spec is internally consistent: every endpoint's security scheme,
  request-body reference, and response schema reference resolves (verified).

## Workflow pointers

- Orient with `onshape_api_list_tags` (42 domain groups), search with
  `onshape_api_search`, then `onshape_api_endpoint` + `onshape_api_schema` for
  exact parameters and response shapes.
- Before a mutating batch (the validation pipeline is ~15 calls, ~10 without
  rendering), check `onshape_api_quota`; the pipeline itself preflights and
  blocks if the annual budget would be exceeded.
