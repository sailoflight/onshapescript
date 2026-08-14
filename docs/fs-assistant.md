# FeatureScript assistance guide

The reference tools give an LLM agent the same material a human developer
works from: the official function/type reference, the language guide, and the
actual standard library implementation. Everything is vendored under
`reference/` and served offline, so there are no network round trips and the
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

- `reference/fsdoc/library.html` — the raw official reference (1.7 MB HTML).
- `reference/fsdoc/index.json` — the same content parsed into structured JSON
  (modules, functions, types, constants, predicates, parameters). Built by
  `scripts/build_fsdoc_index.py`.
- `reference/fsdoc/guide.json` — every guide/tutorial page parsed into heading
  sections with typed blocks (paragraph, code, table, list); this is what
  `fs_guide_section` reads and what `fs_search kind=guide` searches.
- `reference/fsdoc/quick.json` — one line per entry (name, kind, module,
  category, one-line summary) across the whole reference plus the guide section
  titles: the cheap whole-surface index for machine indexing. Auto-regenerated
  on every build.
- `reference/quick-reference.md` — the curated, distilled cheat-sheet (the
  `fs_quick_reference` tool); authored alongside the docs rather than generated.
- `reference/fsdoc/<page>.html` — the raw guide pages, kept for provenance and
  staleness checks (each page's sha256 is recorded in `guide.json`).
- `reference/std-library/<module>.fs` — the standard library source, mirrored
  from `github.com/javawizard/onshape-std-library-mirror` (MIT).

The indexes record `librarySha256` / per-page `sha256` so you can tell whether
the docs and indexes are in sync. Rebuild after re-fetching:

```bash
python3 scripts/fetch_reference.py
python3 scripts/build_fsdoc_index.py
```

## Version checks

`fs_check_version` compares the vendored reference version (parsed from
`reference/std-library/featurescriptversionnumber.gen.fs`) against the version
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

fs_guide_section(page="feature-types", section="precondition")
  -> the narrowed section text (or the whole page + heading outline)

fs_library_source(module="primitives", function="fCylinder")
  -> the definition window from the real std library source
```

## Disambiguation

Some names exist in several modules (`extrude` in `extrude.fs` and elsewhere).
`fs_get_function` and `fs_get_type` return a clear error listing the modules
when a name is ambiguous; pass `module` to pick one. Functions like
`opExtrude(context, id, definition)` document only the `definition` map fields
in the parameter table — `context` and `id` are the standard arguments present
in every operation and are not repeated per function.
