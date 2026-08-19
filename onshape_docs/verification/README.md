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
| `live/` | The raw live-verification record: experiment `.fs` files, `results.json`, `instance-results.json`, and `README.md` with the budget ledger. |

The four corpora verified here are: the vendored FS reference, the vendored
REST API spec, the vendored auth/error docs, and **the project's own
documentation index** (`onshape_docs/index.json`, built by
`onshape_docs/scripts/build_docs_index.py` from the authored markdown; README.md is the human
landing page and intentionally not indexed). The markdown files are the
originals and are kept; `onshape_docs/index.json` is a derived, structured copy served
on demand by the `docs_*` tools (see `onshape_docs/guide/mcp-server.md`).

## Run

```bash
python3 onshape_docs/verification/verify_docs.py
```

The 16 checks verify consistency and integrity of all four corpora:

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

## Purpose

Green checks are not the goal. The goal is turning verification findings into
**experience an LLM agent can act on** — so the reference corpus becomes
self-correcting guidance. The two `llm-experience-*.md` documents are that
output, and (like every project doc) they are indexed into `onshape_docs/index.json`
and read on demand through `docs_section` / `docs_search` alongside the
`fs_*` / `onshape_api_*` reference tools.
