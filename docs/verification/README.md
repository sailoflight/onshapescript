# Documentation verification

Zero-cost, local validation of every vendored document corpus. Nothing here
calls the network or consumes Onshape API quota — its purpose is to **distill
verified experience for LLM agents**.

## Contents

| File | What it is |
|---|---|
| `verify_docs.py` | Runs all checks and statistics, writes `report.json`. |
| `report.json` | Latest run: every check's pass/fail + corpus statistics + known official gaps. |
| `llm-experience-api.md` | Onshape REST API experience for LLM agents, backed by the verified corpus. |
| `llm-experience-fs.md` | FeatureScript language experience for LLM agents, backed by the verified corpus. |

## Run

```bash
python3 docs/verification/verify_docs.py
```

The 14 checks verify consistency and integrity of all three corpora:

- **FS reference** — `index.json` ↔ `library.html` sha256, guide page sha256,
  structural completeness (functions/types/constants/predicates), operator-name
  non-emptiness, and parameter-type cross-references.
- **REST API** — `api_index.json` ↔ `openapi.json` sha256, endpoint
  well-formedness, security / request-body / response schema references resolve,
  `api_quick.json` surface equals `api_index.json`.
- **Auth / errors** — page sha256, `errorCodes` well-formedness.

## Known official gaps (recorded, not failures)

Verification found defects in the **official upstream sources** themselves,
recorded in `report.json` under `knownOfficialGaps` and explained in the
experience docs:

- **FS**: `GBTErrorStringEnum` is referenced 19× (by the `ev*` query error
  parameters) but never defined in FsDoc.
- **REST**: three POST endpoints ship without `summary`/`description`
  (`revertunchangedtorevisions`, `syncAppElements`, `/partnumber/nextnumbers`).

New gaps that appear after a re-fetch will fail the run.

## Purpose

Green checks are not the goal. The goal is turning verification findings into
**experience an LLM agent can act on** — so the reference corpus becomes
self-correcting guidance. The two `llm-experience-*.md` documents are that
output: read them into context (or point a model at them) alongside the
`fs_*` / `onshape_api_*` reference tools.
