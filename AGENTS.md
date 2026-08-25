# Repository agent instructions

## Mandatory lookup-first protocol

For any repository, FeatureScript, Onshape API, or browser-automation question,
do not start from memory or speculation. Use this order:

1. **Classify the question** as project workflow, FeatureScript, REST API, browser experience, or source code.
2. **Search the cheapest index first** and inspect its candidate list or heading outline.
3. **Open the smallest exact entry**: one documentation section, function, type, endpoint, schema, or matched source region.
4. **Read a complete authored or raw source only when the indexed detail cannot answer the question.**
5. **Reason, plan, and edit only after the lookup evidence is collected.**

Do not skip directly from a vague question to a large original file. Do not
guess an Onshape name, signature, payload, selector, or workflow that can be
looked up locally.

## Domain routing

| Question | Index first | Exact detail second | Full source last |
|---|---|---|---|
| Project workflow or known lesson | `docs_search` or `docs_list` | `docs_section` for one section | Authored `.md` file |
| FeatureScript concept or symbol | `fs_quick_reference`, then `fs_search` | `fs_get_function`, `fs_get_type`, or `fs_guide_section` | `fs_library_source`, then `reference/raw/` only if needed |
| Onshape REST API | `onshape_api_list_tags` or `onshape_api_search` | `onshape_api_endpoint`, `onshape_api_schema`, `onshape_api_auth`, or `onshape_api_error_codes` | Vendored OpenAPI or raw developer page only if needed |
| Browser behavior | `docs_search` over `browser-automation` / `browser-modeling` | `docs_section` for the matched lesson | Browser source/fixture after the documented behavior |
| Repository implementation | File/content search | Read the matched function and its tests | Whole module only when local context is insufficient |

`onshape_docs/reference/raw/` is provenance and build input, not the first read.
The normal read order is quick index -> structured detail -> exact original.
Do not open generated JSON indexes directly; use their query tools.

## Large index protection

`onshape_docs/index.json` is a generated index of roughly 191 KiB; its size varies
after rebuild. Never load the whole file into model context to answer one
question. Prefer `docs_search` or `docs_list`, then retrieve one exact section
with `docs_section`.
If those query tools are unavailable, use `grep`/`rg` only to locate candidate
keywords, page ids, paths, or headings, then read a bounded window around the
match from the authored Markdown. Do not print or ingest the complete JSON
index. Apply the same candidate-first, bounded-read rule to other large indexes
and raw sources.

## Source precedence

1. Current code and offline tests define implemented behavior.
2. `onshape_docs/experience/` records reusable verified behavior and operational lessons.
3. `onshape_docs/verification/` holds evidence, reports, and experiment records behind those lessons.
4. `onshape_docs/reference/` holds vendored upstream material and its generated indexes.

When sources disagree, identify version/date scope and report the conflict. Do
not silently combine stale experience with current behavior.

## API quota safety

- Keep `LIVE_API_ENABLED` off by default.
- Use local docs, indexes, code, tests, mocks, fixtures, replay, and dry-run before considering a live request.
- Never use the real Onshape API for trial-and-error debugging.
- A live request requires one explicit unresolved fact and a hard request budget.

Detailed quota, retry, fixture, and mutation constraints are in `CLAUDE.md` and
apply to every agent, not only Claude.

## Change discipline

- Preserve concurrent user or agent edits and re-read shared files before changing them.
- Keep runtime data and configuration with the module that owns it.
- Rebuild `onshape_docs/index.json` after changing indexed documentation.
- Run offline tests with `LIVE_API_ENABLED` unset; never enable it for regression verification.
<!-- agent-project-guides:routing:start -->
## Agent routing

Package adaptation: status=adapted; package_revision=1.4.2; verified_at=2026-08-25T01:49:04Z; scope=repo; reason=none

1. Trigger is active only if this injected root has both managed marker names `agent-project-guides:adapter-trigger:start` and `agent-project-guides:adapter-trigger:end`. Routing/state and `pending/stale` are not triggers; bootstrap is template-only. If absent, never re-read/search; route now.
2. Before pwd/list/glob/read, an assigned compatible role/mode wins: content-grep its exact quoted `id` or literal label across `agent-project-guides/routing/*.roles.jsonl`; use one record. No fuzzy regex, discovery, planes/full registries, re-asking or rediscovery.
3. Only when unassigned read two-line `agent-project-guides/routing/planes.jsonl`; if unclear use the structured question tool (DSH: `ask_user_question`) and wait.
4. In that registry grep one exact role. If unclear, use the same tool and wait before its guide.
5. Blocking questions use stable IDs, 2–4 exclusive choices and impacts, not prose lists; free text only if choices mislead; ask directly only without a tool.
6. Resolve record `guide`/`procedure_by_mode` under `agent-project-guides/`, never relative to registry/cwd. Read only those paths; a failure is package integrity, not permission to glob.
7. Without a trigger, ask adapt-now vs continue only if intent is unclear and state is not `adapted`; explicit adaptation needs no question. Installer owns `pending/stale`; initialize/readapt records `partial/adapted/blocked`.
8. Roles never grant production credentials, real data, cost or destructive actions.

Subagents receive explicit role/mode, scope, writable paths, environment/data permissions and deliverable; missing/conflicting authority goes to parent/captain, never end user or self-expansion.
<!-- agent-project-guides:routing:end -->
