# FeatureScript assistance guide

The reference tools give an LLM agent the same material a human developer
works from: the official function/type reference, the language guide, and the
actual standard library implementation. Everything is vendored under
`onshape_docs/reference/` and served offline, so there are no network round trips and the
answers are deterministic.

## Why this matters

FeatureScript is a small, Onshape-specific language. Its standard library is
almost entirely absent from general LLM training corpora, so an agent that
"knows" how to extrude in another CAD context will confidently invent wrong
signatures here. The tools below exist to replace guessing with lookup.

## Suggested workflow

1. **Orient** — `fs_quick_reference` returns the distilled cheat-sheet (a few
   KB) so you can anchor the language model, feature anatomy, and the module
   map before looking anything up.
2. **Gate on version** — `fs_check_version` (add `check_latest` to probe the
   mirror) and confirm the vendored reference covers the FeatureScript version
   you are coding against. It warns `docs-behind` when your target (or your
   Feature Studio, with `include_live`) is newer than the vendored snapshot,
   and reports whether the JSON indexes are consistent with the raw pages.
   If `updateAvailable` is true (or you hit a real `docs-behind`), run
   `fs_update_reference` to refresh the corpus — see "Updating vs diffing"
   below.
3. **Find the right name** — `fs_search` with plain-language keywords when you
   don't know the exact function ("create sketch region", "sweep along path",
   "fillet the edge between faces").
4. **Read the exact API** — `fs_get_function` for the signature and every
   parameter's type, requirement, description, and example. `fs_get_type` for
   the enum/type a parameter expects (e.g. what values `BoundingType` allows).
5. **Understand the concept** — `fs_guide_section` for language-level guidance:
   `feature-types`, `uispec` (feature UI), `modeling`, `top-level`
   (preconditions, lambdas), `syntax`, `tables`.
6. **See how Onshape writes it** — `fs_library_source` for the real
   implementation of a module or function, e.g. how `fCylinder` is built from
   `opExtrude`-style primitives or how `qCreatedBy` constructs a query.
7. **Breadth before depth** — `fs_list_modules` to see the module layout and
   `fs_list_functions` (with `prefix`) when you remember part of a name.
8. **Project docs** — `docs_list` / `docs_section` / `docs_search` read the
   project's own documentation (README, `onshape_docs/guide/mcp-server.md`, the verified
   `llm-experience-*` lessons, example docs) on demand from `onshape_docs/index.json`.
   Use these for tool-catalog, workflow, and verification-lesson questions that
   are not in the vendored reference.

## Updating vs diffing

For the caller, an **update tool is strictly more context-efficient than a diff
tool**:

- A **diff tool** streams the actual delta (every added/changed signature and
  description) into context. For a real version gap that delta is unbounded,
  it is repeated on every call, and it does not fix the underlying staleness —
  the corpus stays old, so lookups keep returning stale data and the caller
  must keep the delta in context to compensate.
- An **update tool** returns only a bounded change summary (version before/after
  + added/removed/changed *counts* + a sample of names). It is a one-time cost,
  and afterwards every `fs_*` lookup serves the fresh corpus, so the delta never
  needs to be held in context at all.

`fs_update_reference` implements the update approach and reports
`updated: false` (plus zero counts) when the upstream material is unchanged.
`fs_check_version(check_latest=true)` is the cheap read-only probe that tells
you *whether* to update before paying for the download.

## Reference data

Vendored material lives in `onshape_docs/reference/`, in three tiers by reading order:

- `onshape_docs/reference/raw/` — **build inputs, never read by the tools**: the official
  FsDoc pages (`raw/fsdoc/`, including the 1.7 MB `library.html`), the standard
  library source (`raw/std-library/`, mirrored from
  `github.com/javawizard/onshape-std-library-mirror`, MIT), the live OpenAPI
  spec (`raw/onshape-api/openapi.json`), and the OAuth2 / API-key / error /
  limits pages (`onshape_docs/reference/raw/onshape-api-docs/`). Kept for provenance and sha256
  staleness checks only.
- `onshape_docs/reference/quick/` — **the cheap first read** (tier 1): `quick.json` (one
  line per entry: name, kind, module, category, one-line summary across the
  whole reference plus the guide section titles), `api_quick.json` (one line
  per endpoint). Auto-regenerated on every build.
- `onshape_docs/reference/index/` — **on-demand full detail** (tier 2): `fsdoc/index.json`
  (modules, functions, types, constants, predicates, parameters, descriptions;
  built by `onshape_docs/scripts/build_fsdoc_index.py`), `fsdoc/guide.json` (every
  guide/tutorial page parsed into heading sections with typed blocks —
  paragraph, code, table, list — what `fs_guide_section` reads and what
  `fs_search kind=guide` searches), `onshape-api/api_index.json`,
  `onshape-api-docs/api_docs.json`.
- `onshape_docs/reference/quick-reference.md` — the curated, distilled cheat-sheet (the
  `fs_quick_reference` tool); authored alongside the docs rather than generated.
- `onshape_docs/index.json` — the project's own documentation (`onshape_docs/guide/*.md`,
  the quick-reference, example docs; README.md is the human landing page and is
  intentionally not indexed) parsed into the same typed-block schema as
  `guide.json`; served by `docs_list` / `docs_section` / `docs_search`. Built
  by `onshape_docs/scripts/build_docs_index.py`; the `.md` files remain the originals.

The indexes record `librarySha256` / per-page `sha256` so you can tell whether
the docs and indexes are in sync. Rebuild after re-fetching:

```bash
python3 onshape_docs/scripts/fetch_reference.py
python3 onshape_docs/scripts/build_fsdoc_index.py
```

## Version checks

`fs_check_version` compares the vendored reference version (parsed from
`onshape_docs/reference/raw/std-library/featurescriptversionnumber.gen.fs`) against the version
you intend to compile with:

```text
fs_check_version(target="3029.0")
  -> vendoredVersion: 2960, status: "docs-behind",
     warnings: ["Target FeatureScript version 3029 is newer than the vendored reference (2960); ..."]
```

- `status: "current"` — the reference covers your version.
- `status: "docs-behind"` — you are targeting a newer version; APIs introduced
  since the vendored snapshot are not documented. Re-fetch before relying on it.
- `status: "unknown"` — the version constant could not be parsed from the
  vendored library.
- `include_live: true` adds your Onshape Feature Studio's reported version
  (requires credentials; read-only). Pass the same version you would use in a
  FeatureScript `import(path : "onshape/std/geometry.fs", version : "...")`.

## Tool examples

```text
fs_search(query="sketch region", limit=5)
  -> {kind, name, module, signature, score, snippet} ranked by relevance

fs_get_function(name="opExtrude")
  -> signature, module, parameters (with requirement/example), description

fs_get_type(name="BoundingType")
  -> kind: enum, values: BLIND, UP_TO_NEXT, ...

fs_guide_section(page="feature-types", section="Defining feature types")
  -> the narrowed section text (or the whole page + heading outline)

fs_library_source(module="primitives", function="fCylinder")
  -> the definition window from the real std library source

onshape_api_search(query="list document elements")
  -> {method: GET, path: /documents/d/{did}/{wvm}/{wvmid}/elements,
      operationId: getElementsInDocument, summary, score}

onshape_api_endpoint(path="/documents/d/{did}/{wvm}/{wvmid}/elements", method="get")
  -> every parameter (did, wvm with its enum, ...) and the response schema ref

onshape_api_schema(name="BTDocumentElementInfo")
  -> properties of the response type referenced by the endpoint above

onshape_api_auth()
  -> the OAuth2 authorization-code workflow (6 steps) + API-key usage
     (pass section="3: Exchange the code for an access token" for detail)

onshape_api_error_codes(status=429)
  -> Too Many Requests, category Client Error (4xx), description + next steps,
     plus the X-Rate-Limit-Remaining / Retry-After header semantics
```

## Disambiguation

Some names exist in several modules (`extrude` in `extrude.fs` and elsewhere).
`fs_get_function` and `fs_get_type` return a clear error listing the modules
when a name is ambiguous; pass `module` to pick one. Functions like
`opExtrude(context, id, definition)` document only the `definition` map fields
in the parameter table — `context` and `id` are the standard arguments present
in every operation and are not repeated per function.
