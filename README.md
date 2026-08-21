# Onshape FeatureScript MCP server

A local Model Context Protocol server that helps an LLM agent write **Onshape
FeatureScript** and verify it in a real Feature Studio. The standard library is
barely present in language-model training data, so this project vendors the
official reference material and exposes it as offline query tools, alongside
credential-safe Onshape REST tools for compiling and validating your code.

```
AGENTS.md              mandatory lookup-first instructions for every agent
mcp_main/               MCP server and the Windows/WSL bridge
onshape_browser_mode/   browser automation, settings, state, and user profile
onshape_rest_api_mode/  REST client, quota guards, state, credentials, and outputs
onshape_docs/           guides, verified experience, evidence, reference, and query indexes
examples/               worked FeatureScript models and their parameter sets
dev/tests/              offline protocol tests (no Onshape contact)
dev/tools/              development-only probes
```

Agents must follow `AGENTS.md`: classify the question, search the cheapest index,
read one exact entry, and open a full authored/raw source only when needed. The
documentation routing map is `onshape_docs/README.md`.

## Configuration ownership

Configuration and runtime data live with the code that owns them:

- `onshape_browser_mode/config/` contains browser defaults plus ignored local/state files; its persistent profile is under `onshape_browser_mode/user_data/`.
- `onshape_rest_api_mode/config/` contains committed target state plus ignored credentials and quota ledger; generated REST output stays under that module.
- Each example owns its parameter sets, such as `examples/branch-cable-trophy/config/`.
- `mcp_main` and `onshape_docs` have no synthetic configuration files because they currently expose no configurable state.

## MCP tools (52)

**FeatureScript reference — local, offline** (the core value):

| Tool | Purpose |
|---|---|
| `fs_check_version` | Verify the vendored reference version; warn `docs-behind` for newer targets, plus index-consistency health and the REST API spec version. Reports the **last observed** real FeatureScript versions (`languageVersion` + `libraryVersion`) for free — cached from workflow responses, no dedicated call. `include_live` refreshes the Feature Studio's declared version (1 call); `check_latest` probes the mirror + live REST spec |
| `fs_update_reference` | Re-fetch the official docs + std library from FREE sources (FsDoc pages + mirror, zero API quota) and rebuild the indexes; returns a compact change summary. Optionally also refreshes the REST API spec (`include_onshape_api`, 1 quota call). Live server-version detection deliberately lives in `fs_check_version include_live`, not here. Mutating: requires `confirm_mutation=true` |
| `fs_quick_reference` | The curated distilled cheat-sheet (onshape_docs/reference/quick-reference.md), small enough to load in one call |
| `fs_list_modules` | Standard library modules grouped by category |
| `fs_list_functions` | Functions/types/constants/predicates with signatures, filtered |
| `fs_get_function` | Full entry: signature, parameters, requirements, examples, return type |
| `fs_get_type` | Type/enum definition and allowed values |
| `fs_search` | Ranked keyword search across the whole reference and the guide |
| `fs_guide_section` | FeatureScript language guide pages/sections as plain text |
| `fs_library_source` | Real standard library implementation source for a module/function |

**Onshape REST API reference — local, offline** (the Onshape REST surface, served
from the live OpenAPI definition plus the official auth/error docs):

| Tool | Purpose |
|---|---|
| `onshape_api_list_tags` | The 42 REST domain groups (Account, Assembly, Document, FeatureStudio, PartStudio, ...) with descriptions |
| `onshape_api_search` | Ranked keyword search across every REST endpoint (method/path/operationId/summary) |
| `onshape_api_endpoint` | Full definition of one operation: parameters, request body, auth requirements, responses |
| `onshape_api_schema` | A REST response/request schema (e.g. `BTDocumentElementInfo`) and its properties |
| `onshape_api_auth` | OAuth2 authorization-code workflow (6 steps) and API-key usage, with full section text on demand |
| `onshape_api_error_codes` | All documented HTTP response codes + rate/annual limits (429 `Retry-After` semantics) |

**Project docs — local, offline** (categorized guide, experience, verification,
reference, and example pages in `onshape_docs/index.json`; the repository-root
README is the unindexed human landing page, while `onshape_docs/README.md` is the
indexed lookup map; authored Markdown stays canonical):

| Tool | Purpose |
|---|---|
| `docs_list` | List categorized pages and section outlines; use this to choose the smallest next read |
| `docs_section` | Read one exact indexed page or heading section after list/search |
| `docs_search` | Return ranked section candidates with category and snippet; then call `docs_section` |

**Onshape REST — inspect and validate your FeatureScript** (existing tools, kept):
read-only `onshape_get_project_state`, `onshape_get_parameter_set`,
`onshape_build_parameter_payload`, `onshape_api_quota` (API-quota budget,
zero network cost), `onshape_list_document_elements`,
`onshape_get_feature_studio_status`, `onshape_check_model`,
`onshape_render_preview`; `onshape_eval_featurescript` (evaluate a FeatureScript
snippet on the **live server** — 1 quota call each, document-first guarded, to
confirm version-specific behavior the 2960 docs lack; the live server is
currently FeatureScript **3044**); mutating (require `confirm_mutation=true`)
`onshape_upload_feature_studio`, `onshape_create_validation_part_studio`,
`onshape_instantiate_feature`, `onshape_run_validation_pipeline` — **every**
mutating tool preflights against the API-quota budget first (upload ~3 calls,
create 1, instantiate 1 when the Feature Studio microversion is cached / 2
otherwise, pipeline ~13 with render / ~8 without) and blocks with
the shortfall if the annual limit would be exceeded.

**Onshape browser — zero-quota UI driving** (20 registered tools run on the
Windows host through the loopback bridge; the table shows representative entry
points). They never touch the REST API or quota ledger, but confirmed UI actions
can still modify cloud data:

| Tool | Purpose |
|---|---|
| `browser_session` | Inspect or establish the persistent Onshape browser session (`status`/`login`) |
| `browser_watch` | Record a human-driven browser session to learn what UI actions do (`start`/`status`/`stop`/`report`) |
| `browser_inspect` | Read-only inventory of the visible interactive elements on the current page |
| `browser_scroll` | Scroll the page/viewport to discover lazy-rendered rows below the fold |
| `browser_click` | Click an element by CSS selector or visible text — an actual click requires `confirm_mutation=true`; `dry_run` only inspects the target |
| `browser_eval` | Evaluate JavaScript in the page — execution requires `confirm_mutation=true`; `dry_run` returns expression metadata without evaluating |
| `browser_reload` | Reload the current page and wait for it to settle; read-only with respect to document data |
| `browser_deploy_featurescript` | Deploy FeatureScript through the browser UI — 0 API quota (`dry_run` default) |

See `onshape_docs/guide/mcp-server.md` for the complete catalog, security boundary, and tests.
See `onshape_docs/guide/rest-api.md` for the REST reference data, coverage, and gaps.

## The vendored reference

`onshape_docs/scripts/fetch_reference.py` downloads, and `onshape_docs/scripts/build_fsdoc_index.py`
indexes, the official FeatureScript material into `onshape_docs/reference/`, split into
three tiers so a caller never reads what it does not need:

- `onshape_docs/reference/raw/` — **build inputs, never read by the tools**: the FsDoc
  pages from `cad.onshape.com` (`raw/fsdoc/`, including the 1.7 MB
  `library.html`), the standard-library source mirrored from
  `github.com/javawizard/onshape-std-library-mirror` (MIT; `raw/std-library/`,
  the real implementation is the highest-fidelity reference), and the raw
  REST / dev-doc inputs below.
- `onshape_docs/reference/quick/` — **the cheap first read** (tier 1): `quick.json` (one
  line per entry), `api_quick.json` (one line per endpoint). What the
  search/find tools consult.
- `onshape_docs/reference/index/` — **on-demand full detail** (tier 2): `index.json` (every
  function, type, parameter, and description as structured text), `guide.json`
  (the guide pages parsed into heading sections with typed blocks — paragraphs,
  code, tables, lists), `api_index.json`, `api_docs.json`.
- `onshape_docs/reference/quick-reference.md` — a curated, distilled cheat-sheet synthesized
  from the docs (served by `fs_quick_reference`).

`onshape_docs/scripts/fetch_onshape_api.py` downloads the **live** Onshape REST API OpenAPI
definition from `https://cad.onshape.com/api/openapi` (authenticated) into
`raw/onshape-api/openapi.json`, and `onshape_docs/scripts/build_onshape_api_index.py`
flattens it into `index/onshape-api/api_index.json` (302 endpoints, 1226
schemas) + `quick/onshape-api/api_quick.json` for the `onshape_api_*` tools.
Because it is pulled live from the server, it always reflects the running
deployment — no stale snapshot. `onshape_docs/scripts/fetch_onshape_api_docs.py` additionally
vendors the official OAuth2 / API-key / error-code / limits pages (public HTTP,
no API-token cost) into `raw/onshape-api-docs/` for the `onshape_api_auth` and
`onshape_api_error_codes` tools.

The project's **own** LLM-facing docs (`onshape_docs/guide/*.md`, `onshape_docs/reference/quick-reference.md`,
example docs; README.md is the human landing page and is intentionally not part
of the indexed corpus) are parsed into `onshape_docs/index.json` by
`onshape_docs/scripts/build_docs_index.py`, using the same typed-block schema as the guide.
The markdown files remain the authored originals; the index is a derived copy
for on-demand reading (`docs_list` / `docs_section` / `docs_search`) and records
each page's sha256 for staleness checks.

Everything prose-shaped is a JSON index; the large source stays as files read
on demand. Both indexes record the source sha256 so `fs_check_version` can
report when a re-fetch left them stale.

Re-sync after an upstream change:

```bash
python3 onshape_docs/scripts/fetch_reference.py
python3 onshape_docs/scripts/build_fsdoc_index.py
python3 onshape_docs/scripts/fetch_onshape_api.py      # needs onshape_rest_api_mode/config/onshape-credentials.json
python3 onshape_docs/scripts/build_onshape_api_index.py
python3 onshape_docs/scripts/fetch_onshape_api_docs.py # public pages, no credentials
python3 onshape_docs/scripts/build_onshape_api_docs_index.py
python3 onshape_docs/scripts/build_docs_index.py       # project docs -> onshape_docs/index.json
```

See `onshape_docs/guide/feature-script.md` for usage guidance and the tool workflows.

## Running the MCP server

```bash
python3 -m mcp_main
```

Configure an MCP client with the module name and repository working directory:

```json
{
  "mcpServers": {
    "onshape-featurescript": {
      "command": "python3",
      "args": ["-m", "mcp_main"],
      "cwd": "/home/lijq/code/onshapescript"
    }
  }
}
```

Non-secret state (`onshape_rest_api_mode/config/onshape-state.json`) and credentials
(`onshape_rest_api_mode/config/onshape-credentials.json`, gitignored) configure which Onshape document the
REST tools target. `ONSHAPE_STATE`, `ONSHAPE_CREDENTIALS`,
`ONSHAPE_PARAMETERS_DIR`, and `ONSHAPE_OUTPUTS_DIR` override the paths.

API-quota budgeting: set `"apiQuota"` in `onshape_rest_api_mode/config/onshape-state.json` —
`{"accountType": "professional"}` maps to the official annual limit
(enterprise 10000 / professional 5000 / standard 2500) or `{"annualLimit": N}`
directly. Seed it with your real year-to-date usage read from the Onshape UI:
`{"accountType": "standard", "alreadyConsumed": 119}`; the passive local ledger
(`onshape_rest_api_mode/config/api-usage.json`, gitignored) adds on top, so `consumed =
alreadyConsumed + ledgerConsumed`. `onshape_api_quota` reports the budget and
every mutating tool preflights before spending calls. This costs zero extra API
calls — Onshape has no public quota endpoint.

## Example: Branch Cable Trophy

`examples/branch-cable-trophy/` is a complete, validated FeatureScript model
that demonstrates the language (features, sketches, sweeps, patterns, fillets,
appearance/name properties) and the workflow. It doubles as the live testbed for
the REST tools: its Feature Studio is the configured target. See
`examples/branch-cable-trophy/README.md`.

## Tests

```bash
python3 -m unittest discover -s dev/tests -v
python3 -m py_compile mcp_main/*.py mcp_main/bridge/*.py onshape_browser_mode/*.py onshape_docs/query/*.py onshape_docs/scripts/*.py onshape_rest_api_mode/*.py examples/branch-cable-trophy/scripts/*.py
```

**Zero-cost syntax guard before any upload**: Onshape compiles FeatureScript
only on the server, and a syntactically bad upload still costs API quota while
returning no diagnostics (`featurespecs` comes back empty). Run
`onshape_docs/scripts/fs_local_check.py` first — it validates Feature Studio structure
(header, `defineFeature` form, bracket balance, dangling annotations, unreplaced
`{{PLACEHOLDER}}`s) as hard errors and flags symbols absent from the vendored
std index as warnings:

```bash
python3 onshape_docs/scripts/fs_local_check.py path/to/file.fs        # single file
python3 onshape_docs/scripts/fs_local_check.py onshape_docs/verification/live/experiments/  # directory
```
