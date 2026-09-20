# Feature List REST fixtures — one authorized live run, 2026-09-19

These five directories cover the Part Studio Feature List endpoints:

| directory | operation | status |
|---|---|---|
| `getPartStudioFeatures` | `GET /partstudios/d/{did}/{wvm}/{wvmid}/e/{eid}/features` | live, 200 |
| `addPartStudioFeature` | `POST /partstudios/d/{did}/{wvm}/{wvmid}/e/{eid}/features` | live, 200 |
| `updateFeatures` | `POST .../features/updates` (suppression) | live, 200 |
| `updatePartStudioFeature` | `POST .../features/featureid/{fid}` | live, 200 |
| `updateRollback` | `POST .../features/rollback` | live, 200 |
| `deletePartStudioFeature` | `DELETE .../features/featureid/{fid}` | live, 200 |
| `refusal-deletePartStudioFeature` | the same `DELETE` against an id that cannot exist | live, **404** |

**Every directory here holds a real request and a real response**, including the one refusal (`refusal-deletePartStudioFeature/`, 404). Each
`metadata.json` records `"liveExecuted": true`, the HTTP `status`, the time, and
the `target` (document / workspace / element, plus the `featureId` where the
operation addresses one). Each `response.json` is the body the server actually
returned, unedited.

The four mutation directories were **constructed offline first** (that is what
the `P3` slice delivered: builders and parsers with no server contact). On
2026-09-19 one explicitly authorized, hard-budgeted run replaced the constructed
requests with the sent ones and added the responses. That run is recorded in
`onshape_docs/verification/capability-live-run-2026-09-19.md`; the script that
made it is `temp/p3_live/feature_list_live.py` and is **one-off** — once these
fixtures replay, re-running it buys nothing and burns quota.

## What the tests prove

1. `request.json` still equals the current builder output for the ids recorded in
   `metadata.json` — payload drift is a reviewable diff, not a surprise.
2. The built path matches the vendored OpenAPI path template for the same
   `operationId`, minus the `/api/v9` prefix the client adds.
3. Each response parser reads exactly the fields the vendored OpenAPI declares for
   its response schema, and tolerates a body that omits all of them.
4. **Replay:** the recorded live bodies parse through the same summarizers the
   live path uses, and the confirmed field values are pinned — `suppressed: true`
   after suppression, the renamed feature after the in-place replace,
   `rollbackIndex` and `microversionId` after rollback, the versioning envelope
   after delete.

## The read discrepancy, resolved (2026-09-20)

`getPartStudioFeatures` was called twice on the same element during the run and
answered differently — `"rollbackIndex": 0`, `"features": []` first, then
`"rollbackIndex": 1` with the feature. The run recorded two possible causes
(server default vs browser/REST handoff) and left them open.

**They are now separated, and the answer is the handoff.** A follow-up probe read
a different element whose feature had been committed hours earlier, three ways in
one run with no reload in between:

| request | `rollbackIndex` | features returned |
|---|---|---|
| no argument | 2 | 2 |
| `rollbackBarIndex=-1` | 2 | 2 |
| `rollbackBarIndex=0` | 2 | 2 |

Identical. So `rollbackBarIndex` does not filter the returned list, the spec's
documented `-1` default is fine, and `rollbackIndex` is a property of the
*element* (its real rollback-bar position), not an echo of the request. That makes
the earlier `"rollbackIndex": 0` a truthful statement that the element then had no
user features — and a browser-inserted custom feature only reached it when the
page was reloaded. Evidence:
`onshape_docs/verification/feature-list-read-probe-2026-09-20.json`.

**Consequence for the fixture below:** the recorded
`getPartStudioFeatures/request.json` carries `rollbackBarIndex=-1` because that is
the call that returned the list, not because the argument is required.

This was then **reproduced under control** on a scratch Part Studio: a clean
browser insert (`inserted: true`, `errored: false`, part present) left REST
reporting an empty list immediately and again ~4 minutes later with no reload;
one page reload flipped the DOM row to the plain `ns-user-feature` class and the
next read returned the feature. A REST-added feature on the same element appeared
on the very next read with no reload, which is the control that rules out a
read-side caching artefact. Full timeline:
`onshape_docs/verification/browser-rest-handoff-2026-09-20.json`.

**Consequence for anything built on a browser insert:** read the Feature List back
and confirm the feature is really in the workspace before sending a REST mutation
that names it. `dev/tests/test_rest_feature_list.py` cannot check that for you —
it is a live-state question, not a payload question.

## The recorded refusal

`refusal-deletePartStudioFeature/` is the family's only recorded failure: a
`DELETE` naming a feature id that cannot exist answered `404` with the shared
error envelope `{"moreInfoUrl", "message", "status", "code"}`. It exists because
the four success fixtures say nothing about what a refusal looks like, and because
the annual quota does not count 4xx (measured: the probe's ledger delta was 0).
