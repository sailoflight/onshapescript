# Documentation map

This directory separates instructions, reusable experience, verification
evidence, and upstream reference material. Use indexes before full originals.

## Lookup order

1. Classify the question with the table below.
2. Search or list the relevant index.
3. Read one exact section, symbol, endpoint, or schema.
4. Open a complete authored/raw source only if indexed detail is insufficient.
5. Start reasoning or editing after collecting that evidence.

Generated JSON indexes are tool inputs, not reading material; use the matching
`docs_*`, `fs_*`, or `onshape_api_*` query tool instead of opening them directly.

| Need | Start here | Then read |
|---|---|---|
| Project workflow or known lesson | `docs_search` / `docs_list` | One `docs_section` |
| FeatureScript language or symbol | `fs_quick_reference` / `fs_search` | Function, type, guide section, then source if needed |
| REST operation, schema, auth, or error | `onshape_api_list_tags` / `onshape_api_search` | Endpoint, schema, auth, or error detail |
| Browser automation behavior | `docs_search` over `browser-automation` / `browser-modeling` | One experience section, then source or fixture |
| Evidence behind a conclusion | Find the experience conclusion first | Its linked verification record |

## Directory ownership

| Directory | Owns | Does not own |
|---|---|---|
| `guide/` | Task instructions and supported workflows | Historical observations or raw evidence |
| `experience/` | Reusable verified FeatureScript, REST, and browser lessons | Experiment logs and generated reports |
| `verification/` | Integrity reports, live manifests, and evidence | Canonical usage guidance |
| `reference/quick/` | Cheap candidate indexes | Full descriptions |
| `reference/index/` | Structured exact details used by tools | Upstream raw pages |
| `reference/raw/` | Vendored provenance and index build input | Normal first reads |
| `query/` and `scripts/` | Offline readers plus fetch/build/check entry points | Authored guidance |

## Authored and generated files

Markdown files are authored originals. `onshape_docs/index.json` is the
generated project-doc index; rebuild and verify it after authored changes:

```bash
python3 onshape_docs/scripts/build_docs_index.py
python3 onshape_docs/verification/verify_docs.py
```
