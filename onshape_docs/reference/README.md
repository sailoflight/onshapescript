# Vendored reference corpus

Fetched by `onshape_docs/scripts/fetch_reference.py` (FsDoc + std library) and the
`onshape_docs/scripts/fetch_onshape_api*.py` fetchers. Onshape/third-party material, vendored
so the local MCP tools answer without a network round trip. Three tiers, in
reading order:

| Tier | Directory | Contents | Who reads it |
|---|---|---|---|
| 0 | `raw/` | build inputs: FsDoc HTML, std-library `.fs`, OpenAPI spec, dev-doc HTML | fetch/build scripts only; `verify_docs.py` sha256-pins them; tools never read |
| 1 | `quick/` | compact distilled indexes (`quick.json`, `api_quick.json`) | `fs_search`, `onshape_api_find` — the cheap first look for candidates |
| 2 | `index/` | full-detail indexes (`index.json`, `guide.json`, `api_index.json`, `api_docs.json`) | `fs_get_function`, `fs_guide_section`, `onshape_api_*` — on-demand deep read |

## raw/fsdoc/

- 20 official documentation pages from `https://cad.onshape.com/FsDoc/` (the
  FeatureScript function/type reference, the language guide, and the tutorial).
  © Onshape. Used for local reference; see the Onshape terms of service.

## raw/std-library/

- 265 FeatureScript standard library source files, mirrored from
  `https://github.com/javawizard/onshape-std-library-mirror` (branch `without-versions`).
  The mirror auto-updates from Onshape and is MIT-licensed; `LICENSE.txt` is
  vendored alongside the sources.

## raw/onshape-api/ + raw/onshape-api-docs/

- `raw/onshape-api/openapi.json` — the live Onshape REST API OpenAPI
  definition, fetched from `https://cad.onshape.com/api/openapi` with the
  local credentials by `onshape_docs/scripts/fetch_onshape_api.py` (always the current
  server version). `index/onshape-api/api_index.json` and
  `quick/onshape-api/api_quick.json` are flattened from it by
  `onshape_docs/scripts/build_onshape_api_index.py`.
- `raw/onshape-api-docs/` — the OAuth2 / API-key / error-code / rate-limit
  pages (public GitHub Pages, zero API-token cost), parsed into
  `index/onshape-api-docs/api_docs.json`.

## Project docs

The project's own LLM-facing documentation (`onshape_docs/guide/*.md`,
`onshape_docs/reference/quick-reference.md`, example docs; README.md is the human landing
page and intentionally not indexed) is indexed by
`onshape_docs/scripts/build_docs_index.py` into `onshape_docs/index.json` (same typed-block
schema as `guide.json`) and served by the `docs_*` tools. The markdown
files stay the authored originals.

## Reading order for callers

Never read `raw/` — it exists only as build input and is sha256-pinned by
`onshape_docs/verification/verify_docs.py`. For a question: start with a `quick/`
index (cheap candidate lists), then pull the one entry you need from `index/`
at full detail. That ordering is exactly what the MCP tools already do
(`fs_search` → `fs_get_function`); `onshape_docs/index.json` mirrors the project's own
markdown the same way (see `onshape_docs/guide/mcp-server.md`).

## Updating

Re-run the fetch scripts to re-sync each raw tree, then the index builders
(which parse `raw/fsdoc/library.html` into `index/fsdoc/index.json`, the guide
pages into `index/fsdoc/guide.json`, both into the compact
`quick/fsdoc/quick.json`, and the OpenAPI spec into the onshape-api indexes —
all record source sha256 for staleness checks):

```bash
python3 onshape_docs/scripts/fetch_reference.py
python3 onshape_docs/scripts/build_fsdoc_index.py
python3 onshape_docs/scripts/fetch_onshape_api.py   # needs onshape-credentials.json
python3 onshape_docs/scripts/build_onshape_api_index.py
```

`onshape_docs/reference/quick-reference.md` is a curated cheat-sheet authored alongside
these files; refresh it by hand when a major version bump changes the API.
