# Documentation verification

Offline integrity checks and evidence for the vendored and project-authored
document corpora. The default verification command is local, deterministic, and
uses zero Onshape API quota. Reusable conclusions are published separately under
`onshape_docs/experience/`.

## Contents

| File | What it is |
|---|---|
| `verify_docs.py` | Runs all checks and statistics, writes `report.json`. |
| `report.json` | Latest run: every check's pass/fail + corpus statistics + known official gaps. |
| `browser-tools-2026-08-25.md` | Developer/tester/field-evaluator evidence and explicit live-validation boundaries for the 22 promoted browser tools. |
| `live/` | The raw live-verification record: experiment `.fs` files, `results.json`, `instance-results.json`, and `README.md` with the budget ledger. |

The four corpora verified here are: the vendored FS reference, the vendored
REST API spec, the vendored auth/error docs, and **the project's own
documentation index** (`onshape_docs/index.json`, built by
`onshape_docs/scripts/build_docs_index.py` from the authored markdown; the repository-root README.md is the human
landing page and intentionally not indexed). The markdown files are the
originals and are kept; `onshape_docs/index.json` is a derived, structured copy served
on demand by the `docs_*` tools (see `onshape_docs/guide/mcp-server.md`).

## Run

```bash
python3 onshape_docs/verification/verify_docs.py
```

The 17 checks verify consistency, semantic ownership, and integrity of all four corpora:

- **FS reference** — `index.json` ↔ `library.html` sha256, guide page sha256,
  structural completeness (functions/types/constants/predicates), operator-name
  non-emptiness, and parameter-type cross-references.
- **REST API** — `api_index.json` ↔ `openapi.json` sha256, endpoint
  well-formedness, security / request-body / response schema references resolve,
  `api_quick.json` surface equals `api_index.json`.
- **Auth / errors** — page sha256, `errorCodes` well-formedness.
- **Project docs** — `onshape_docs/index.json` page sha256 matches the authored markdown,
  sections well-formed (title + blocks).

## Known official gaps (recorded, not failures)

Verification found defects in the **official upstream sources** themselves,
recorded in `report.json` under `knownOfficialGaps` and explained in the
experience docs:

- **FS**: `GBTErrorStringEnum` is referenced 19× (by the `ev*` query error
  parameters) but never defined in FsDoc.
- **REST**: three POST endpoints ship without `summary`/`description`
  (`revertunchangedtorevisions`, `syncAppElements`, `/partnumber/nextnumbers`).

New gaps that appear after a re-fetch will fail the run.

## Relationship to experience

`verification/` answers “what evidence supports this claim?” It is not the first
read for operational questions. Start with `docs_search`, read the matched page
under `onshape_docs/experience/`, and follow its verification link only when the
evidence or version scope matters.

- FeatureScript conclusions: `onshape_docs/experience/featurescript.md`
- REST API conclusions: `onshape_docs/experience/rest-api.md`
- Browser conclusions: `onshape_docs/experience/browser-automation.md` and
  `onshape_docs/experience/browser-modeling.md`

`report.json`, live manifests, and experiment files remain evidence and are not
loaded as general guidance.
