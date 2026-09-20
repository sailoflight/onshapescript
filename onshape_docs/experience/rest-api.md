# Verified experience: Onshape REST API

What an agent needs to call the Onshape REST API correctly. Scope: vendored REST
API 1.219.86205 and controlled live observations through 2026-08-14.
Every claim below is backed by the verified corpus (`onshape_docs/verification/report.json`,
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
- **`POST /partstudios/.../features/rollback` declares its request body as a bare
  `{"type": "string"}`, which cannot be right for a position.** The real shape is
  in the operation's own description: `{ "rollbackIndex": integer }`, with `-1`
  meaning "move the bar to the end of the list". Trust the prose here, not the
  schema. `onshape_rest_api_mode/feature_list.py` builds the object and
  `test_rest_feature_list` pins both halves of that evidence. Server-confirmed
  2026-09-19: the object was accepted (200, `BTSetFeatureRollbackResponse-1042`),
  so the prose was right and the schema is the part to distrust.
- **Suppression goes through `updateFeatures`, not a full redefinition.**
  `POST .../features/updates` (`BTUpdateFeaturesCall-1748`) "does not fully
  redefine the features; it updates only the parameters supplied in the
  top-level feature structure, and optionally can update feature suppression
  attributes". So suppress/unsuppress is one call carrying a minimal
  `BTMFeature-134` (`btType` + `featureId` + `suppressed`) plus
  `updateSuppressionAttributes: true` — without that flag the API ignores the
  suppression field. Re-posting the whole definition through
  `updatePartStudioFeature` is the wrong tool for it: anything omitted from the
  body is *not* preserved by a definition replace.
- **Feature List mutations have no domain response of their own.** The four
  responses (`BTFeatureDefinitionResponse-1617`, `BTFeatureApiBase-1430`,
  `BTSetFeatureRollbackResponse-1042`, `BTUpdateFeaturesResponse-1333`) return
  versioning metadata and, for the batch/definition cases, the new
  `featureStates`. That is "the server accepted this", not "the model changed as
  intended" — read the Feature List afterwards. All four schemas are now
  server-confirmed (see the live-verification lessons below).

## Workflow pointers

- Orient with `onshape_api_list_tags` (42 domain groups), search with
  `onshape_api_search`, then `onshape_api_endpoint` + `onshape_api_schema` for
  exact parameters and response shapes.
- Before a mutating batch (the validation pipeline is ~13 calls, ~8 without
  rendering), check `onshape_api_quota`; the pipeline itself preflights and
  blocks if the annual budget would be exceeded.

## Lessons from live verification (real server, ~310 calls)

FeatureScript save/spec/eval/instantiate behavior is canonical in
`onshape_docs/experience/featurescript.md`; read its matched section instead of
duplicating those conclusions here. This page retains REST transport, caching,
and cost behavior.

- **Per-step real cost** (counted from the actual operations): upload ~3,
  create Part Studio 1, instantiate 1 (when the Feature Studio microversion is
  cached from the upload) / 2 (cold), `evalfeaturescript` 1, validation
  pipeline 13 with render / 8 without. `check_latest` on `fs_check_version`
  costs 1 (the `/api/build` REST-spec probe); the plain version check and
  `fs_update_reference` (without `include_onshape_api`) cost **0**.
- **Instantiate against a stale Feature Studio microversion is silent, not an
  error.** Microversions are immutable snapshots, so `POST .../features` with a
  namespace pinning an old microversion succeeds and uses the OLD definition if
  the Feature Studio was edited on the server after that microversion. The
  element mirror caches the microversion from upload/status responses and stamps
  a sync time; instantiate trusts it only within 5 minutes
  (`MICROVERSION_CACHE_MAX_AGE_SECONDS`) and otherwise re-reads the element list
  (1 extra call) — but an edit made *inside* that window is undetectable. That is
  why the validation pipeline threads the microversion from the upload response
  (same-run) instead of trusting the cache, and why "upload → human edits the
  Feature Studio in the Onshape UI → instantiate" is a hazard: tell the human
  not to edit the Feature Studio between upload/status and instantiate.
- **A version mismatch on `import` is a save-time failure** — the upload
  returns fine but `featurespecs` is empty. Check `fs_check_version` (free)
  before writing `import(path : ..., version : ...)` lines.
- **Batch verification is a fixed cost with declining returns.** The remaining
  open questions after ~310 calls are narrow and version-specific; answer them
  on demand inside the task that needs them rather than spending another batch.
- **The four Feature-List mutations are server-confirmed (2026-09-19, 4 calls,
  all 200).** Each answered with exactly the schema the vendored spec declares:
  suppression → `BTUpdateFeaturesResponse-1333` with `features[0].suppressed:
  true`; in-place definition replace → `BTFeatureDefinitionResponse-1617` with
  `featureState.featureStatus: "OK"` and the new name; rollback →
  `BTSetFeatureRollbackResponse-1042`; delete → `BTFeatureApiBase-1430`. The
  recorded bodies replay through the production parsers in
  `test_rest_feature_list.LiveReplayTest`, so the offline fixtures are now
  evidence rather than construction.
- **`updateRollback` answers with the resolved position, not the sentinel.** A
  one-feature list asked for `-1` came back `"rollbackIndex": 1`. Read the
  response as "where the bar ended up".
- **`rollbackBarIndex` does not filter the Feature List read, and the documented
  default is fine.** A P3 run saw `GET .../features` answer `{"rollbackIndex": 0,
  "features": []}` and then, after a page reload, `{"rollbackIndex": 1, ...}`; the
  first write-up blamed the absent argument. A three-way probe on a
  long-committed element (absent / `-1` / `0`, one run, no reload) returned
  identical bodies — 2 features, `rollbackIndex: 2` in all three. So
  `rollbackIndex` reports the **element's real rollback-bar position**, not an
  echo of the request, and the earlier empty body was a true statement about the
  element. Evidence: `onshape_docs/verification/feature-list-read-probe-2026-09-20.json`.
- **A custom feature inserted through the browser is not in the workspace until
  the page is (re)loaded — reproduced, not inferred.** While it is pending, the UI
  shows the row with the `edited selected` classes and the model shows the part,
  but `GET .../features` truthfully answers `"features": []` /
  `"rollbackIndex": 0`. A controlled run on one scratch Part Studio: after a clean
  insert (`inserted: true`, `errored: false`, regeneration waited ~7.5 s, part
  present) REST returned an empty list immediately **and again ~4 minutes later
  without a reload**; a single page reload flipped the DOM row to the plain
  `ns-user-feature` class and the next read returned the feature. On the same
  element, a **REST-added** feature was visible on the very next read with no
  reload, which rules out a read-side caching artefact. Evidence:
  `onshape_docs/verification/browser-rest-handoff-2026-09-20.json`. The lesson for
  the FS-first route: **never build a REST mutation on a feature the browser just
  created without reading the Feature List back first**, and treat a REST
  feature-count of 0 as authoritative over what the UI is showing.
- **`addPartStudioFeature` works with the same envelope as the other four.** The
  fifth member of the family — the one `operations.instantiate_feature` has always
  targeted — was confirmed live: `POST .../features` with
  `BTFeatureDefinitionCall-1406` naming feature type `spiralRidge` and the Feature
  Studio namespace returned 200, `BTFeatureDefinitionResponse-1617`,
  `featureStatus: "OK"` and a new `featureId`. Recorded in
  `dev/tests/fixtures/onshape/feature-list/addPartStudioFeature/`.
- **A custom-feature spec may declare no parameters at all.** The `spiralRidge`
  source generated by `onshape_browser_mode.modeling_transactions` has an empty
  `precondition` and bakes the geometry values in as literals, so a feature
  instance of it carries `"parameters": []` — which is why the Feature List read,
  the in-place replace and the REST add all round-trip an empty parameter array.
  Changing the geometry of such a feature means deploying a new FeatureScript
  version, not editing parameters.
- **A refusal is a 404 carrying the shared error envelope, and it is free.**
  `DELETE .../features/featureid/{unknown}` answered
  `{"moreInfoUrl": "", "message": "Feature not found", "status": 404, "code": 9999}`
  with the HTTP status mirrored inside the body. The probe's own ledger delta was
  **0**, confirming empirically that 4xx does not count against the annual limit.
  Note the envelope is not the operation's declared response schema, so a caller
  must branch on the HTTP status, not on the presence of expected fields;
  `dev/tests/fixtures/onshape/feature-list/refusal-deletePartStudioFeature/`
  records it and pins that the success parser returns nothing for such a body.
- **A custom feature's serialized definition can carry `"parameters": []`.** The
  row read back for a custom feature inserted with its spec defaults had empty
  `parameters`, empty `parameterLibraries`, and a `namespace` shaped
  `e<featureStudioElementId>::m<microversionId>`. Posting that definition back
  through `updatePartStudioFeature` renamed the feature in place and returned
  `featureStatus: OK`, so the empty array is accepted — and the `namespace` is
  what marks the row as custom rather than standard-library.
- **Domain-verify a Feature List mutation with the browser, not another REST
  call.** The four responses only say "accepted". After the run's delete, a
  zero-REST-quota browser read of the Feature List showed `特征 (4)` and
  `零件数 (0)` — the model-level confirmation, at no quota cost.
