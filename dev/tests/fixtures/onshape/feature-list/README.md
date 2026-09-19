# Feature List CRUD fixtures — constructed, never sent

These four directories cover the Part Studio Feature List mutations added in the
`feature-list-crud` slice: `updateFeatures`, `deletePartStudioFeature`,
`updateRollback`, `updatePartStudioFeature`.

**No request here has ever been sent to Onshape.** Each `metadata.json` says so
explicitly (`"liveExecuted": false`, `"status": null`) and each directory holds
only:

* `request.json` — the exact request the shared builder produces, with the
  `Authorization` header redacted. It is written by feeding the real builders
  (`onshape_rest_api_mode/feature_list.py`) through `OnshapeClient.describe`, so
  it is the request the live path would send, not a re-typed approximation.
* `metadata.json` — operation id, the OpenAPI response schema the parser targets,
  why the request exists, and the honest "not executed" record.

There is deliberately **no `response.json`**. A response body that nobody
received would be an invented artifact, and this repository treats fabricated
evidence as a defect: `test_rest_feature_list.FeatureListFixtureTest` fails if a
`response.json` appears in these directories.

Where the fixtures normally come from: `CLAUDE.md` requires every *executed* live
call to be captured as `request.json` + `response.json` + `metadata.json`. These
directories already have the first and third parts, so the day an authorized
live call is made, its response body drops in beside them and the same tests
switch from "constructed" to "replay".

What the tests prove without a network:

1. `request.json` still equals the current builder output (payload drift is a
   diff, not a surprise).
2. The built path matches the vendored OpenAPI path template for the same
   `operationId`, minus the `/api/v9` prefix the client adds.
3. The response parser reads exactly the fields the vendored OpenAPI declares for
   each response schema, and tolerates a body that omits all of them.
