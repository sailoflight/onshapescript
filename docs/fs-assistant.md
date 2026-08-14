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

1. **Find the right name** — `fs_search` with plain-language keywords when you
   don't know the exact function ("create sketch region", "sweep along path",
   "fillet the edge between faces").
2. **Read the exact API** — `fs_get_function` for the signature and every
   parameter's type, requirement, description, and example. `fs_get_type` for
   the enum/type a parameter expects (e.g. what values `BoundingType` allows).
3. **Understand the concept** — `fs_guide_section` for language-level guidance:
   `feature-types`, `uispec` (feature UI), `modeling`, `top-level`
   (preconditions, lambdas), `syntax`, `tables`.
4. **See how Onshape writes it** — `fs_library_source` for the real
   implementation of a module or function, e.g. how `fCylinder` is built from
   `opExtrude`-style primitives or how `qCreatedBy` constructs a query.
5. **Breadth before depth** — `fs_list_modules` to see the module layout and
   `fs_list_functions` (with `prefix`) when you remember part of a name.

## Reference data

- `reference/fsdoc/library.html` — the raw official reference (1.7 MB HTML).
- `reference/fsdoc/index.json` — the same content parsed into structured JSON
  (modules, functions, types, constants, predicates, parameters). Built by
  `scripts/build_fsdoc_index.py`.
- `reference/fsdoc/<page>.html` — guide and tutorial pages, converted to text
  by `fs_guide_section`.
- `reference/std-library/<module>.fs` — the standard library source, mirrored
  from `github.com/javawizard/onshape-std-library-mirror` (MIT).

The index records `librarySha256` so you can tell whether the docs and index are
in sync. Rebuild after re-fetching:

```bash
python3 scripts/fetch_reference.py
python3 scripts/build_fsdoc_index.py
```

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
