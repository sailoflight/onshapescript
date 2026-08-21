# Verified experience

Experience pages contain reusable conclusions already distilled from code,
offline verification, or controlled browser/live observations. Agents should
find them through `docs_search`, read one section with `docs_section`, and only
then follow evidence links into `verification/`.

| Page | Scope |
|---|---|
| `featurescript.md` | Language shape, version behavior, compile/eval/instantiate layers, and quota-efficient diagnosis |
| `rest-api.md` | Real API parameter patterns, response limitations, microversion behavior, and call costs |
| `browser-automation.md` | Windows bridge runtime, login recovery, page structure, selectors, and session pitfalls |
| `browser-modeling.md` | Canonical zero-REST-quota workflow from new document through FeatureScript deployment and modeled parts |

An experience page must state its version/date scope when behavior may drift.
It must not present an experiment hypothesis as a current rule. Superseded
records are merged into the current page or left only as verification evidence,
not kept as competing guidance.

Task instructions belong in `guide/`; raw reports, manifests, fixtures, and
experiment logs belong in `verification/`.
