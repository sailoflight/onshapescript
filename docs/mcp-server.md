# Local MCP server

`mcp_server.py` exposes the validated Onshape workflow as a local Model Context
Protocol server. It uses newline-delimited JSON-RPC over standard input/output,
so local MCP clients can launch it as a subprocess. The server and Onshape client
use only Python's standard library; there is no package-install step.

## Configure a client

Use an absolute script path so launch does not depend on the client's working
directory:

```json
{
  "mcpServers": {
    "onshape-branch-cable-trophy": {
      "command": "python3",
      "args": ["/home/lijq/code/onshapescript/mcp_server.py"],
      "cwd": "/home/lijq/code/onshapescript"
    }
  }
}
```

The default configuration files are:

- Non-secret state: `config/onshape-state.json`
- Credentials: `onshape-credentials.json`
- Detailed parameters: `config/model.default.json`
- Simplified parameters: `config/model.preview.json`

Override the first two paths for another deployment with `ONSHAPE_STATE` and
`ONSHAPE_CREDENTIALS`. Do not place credentials in MCP arguments, environment
configuration committed to source control, prompts, or tool input.

## Tool catalog

### FeatureScript reference tools — local and offline

These read the vendored reference under `reference/` and never contact Onshape
or the network. They are the primary FeatureScript lookup tools. See
`docs/fs-assistant.md` for the recommended workflow.

| Tool | Behavior |
|---|---|
| `fs_check_version` | Reports the vendored reference version (parsed from the std library) and warns `docs-behind` when a `target` and/or the Feature Studio version is newer. The last observed real versions (`languageVersion` + `libraryVersion`) are reported **for free** — cached from workflow responses (`feature_studio_status` / `eval`), never a dedicated call; `include_live` refreshes the Feature Studio's declared version (1 read-only call). Also verifies the JSON indexes are consistent with the raw pages and reports `onshapeApiSpecVersion` (the vendored REST API spec version + health). With `check_latest` it probes the mirror (one small network call) plus the live REST spec (1 call) for the newest versions. |
| `fs_update_reference` | Mutating (requires `confirm_mutation=true`): re-fetches the FsDoc pages + std library and rebuilds the indexes; with `include_onshape_api` it also refreshes the REST API OpenAPI spec (needs credentials). Returns a bounded change summary (version before/after, added/removed/changed counts) so the delta never needs to live in the caller's context. |
| `fs_quick_reference` | Returns the curated distilled cheat-sheet (`reference/quick-reference.md`), small enough to load in one call for orientation. |
| `fs_list_modules` | Lists standard library modules grouped by category (optional filter). |
| `fs_list_functions` | Lists functions/types/constants/predicates with signatures and summaries, filtered by module/category/kind/prefix. |
| `fs_get_function` | Full entry: signature, parameters (type, requirement, description, example), return type, module. |
| `fs_get_type` | Type/enum definition with every allowed value. |
| `fs_search` | Ranked keyword search across the entire reference and the guide (`kind=guide`). |
| `fs_guide_section` | One FsDoc guide page, or a section of it, as plain text with fenced code blocks. |
| `fs_library_source` | The real standard library implementation source, optionally the window around one function. |

### Project docs tools — local and offline

The project's own documentation (README, `docs/*.md`, `reference/quick-reference.md`,
example docs) is parsed into `docs/index.json` by `scripts/build_docs_index.py`
with the same typed-block schema as the FsDoc guide, so it is searchable and
readable on demand — the authored `.md` files remain the originals. These tools
cover the project's own knowledge (tool catalog, workflows, verified lessons),
distinct from the vendored Onshape reference above.

| Tool | Behavior |
|---|---|
| `docs_list` | Every indexed page with its title, source path, and heading-section outline. |
| `docs_section` | A page as plain text, or one heading section (page + optional section; matching is case-insensitive substring). |
| `docs_search` | Ranked keyword search across every section of the project docs; pass `page` to restrict. |

### Onshape REST API reference tools — local and offline

These answer questions about the Onshape REST API surface from the live OpenAPI
definition vendored under `reference/onshape-api/`. Like the FeatureScript
tools they are offline; only `fs_check_version`/`fs_update_reference` (above)
and the Onshape REST tools touch the network. See `docs/onshape-api.md` for the
data, coverage, and the remaining documentation gaps for real operations.

| Tool | Behavior |
|---|---|
| `onshape_api_list_tags` | The 42 REST domain groups (Account, Assembly, Document, FeatureStudio, PartStudio, ...) with descriptions; reports the spec version they describe. |
| `onshape_api_search` | Ranked keyword search over every REST endpoint (method/path/operationId/summary), optional tag filter. |
| `onshape_api_endpoint` | Full definition of one operation: parameters (name, path/query/header, required, type, enum/default, description), response codes and their schema references. |
| `onshape_api_schema` | A response/request schema (e.g. `BTDocumentElementInfo`) and its properties/required fields. |
| `onshape_api_auth` | The OAuth2 authorization-code workflow (6 steps: register app → authorize → exchange → use → refresh → grant) and API-key usage; distilled by default, full section text (incl. code) via `section`. |
| `onshape_api_error_codes` | All documented HTTP response codes with category/description/next steps, plus rate and annual call limits (429 `X-Rate-Limit-Remaining` / `Retry-After`); `status` narrows to one code. |

`fs_check_version` also reports `onshapeApiSpecVersion` (the vendored REST API
spec version + index health), and `fs_update_reference` accepts
`include_onshape_api: true` to refresh the REST spec and the auth/error docs
alongside the FeatureScript reference — the spec re-fetch needs
onshape-credentials.json and is skipped with a note when it is absent.

### Local and read-only

| Tool | Behavior |
|---|---|
| `onshape_get_project_state` | Reads non-secret local state and credential-file presence. It never reads or returns credential values. |
| `onshape_api_quota` | Reports the local API-quota budget: configured annual limit, calls consumed (passive ledger of 2xx/3xx responses), remaining, and how many validation-pipeline runs fit. Zero network cost — no extra API call. |
| `onshape_get_parameter_set` | Reads the maintained detailed or simplified parameter map. |
| `onshape_build_parameter_payload` | Converts local values into explicit Onshape custom-feature parameter blocks. |

### Authenticated read-only Onshape tools

| Tool | Behavior |
|---|---|
| `onshape_list_document_elements` | Lists elements and current microversions in the configured workspace. |
| `onshape_get_feature_studio_status` | Reads Feature Studio metadata and compiled feature specifications. |
| `onshape_check_model` | Checks feature state, 132/65 part count, required names, and bounds without writing the report file. |
| `onshape_render_preview` | Returns one shaded PNG as MCP image content; `save=true` additionally writes `outputs/previews/<view>.png`. |
| `onshape_eval_featurescript` | Evaluates a FeatureScript snippet on the live server (1 quota call; script must evaluate to a two-argument anonymous function `function(context is Context, id is Id) {...}`). Document-first guarded: a 10-call/session budget plus `confirm_mutation=true` to exceed it, preflighted against the quota budget, and every response reports the session/eval/quota counters. Use it to confirm version-specific semantics the vendored 2960 docs lack, and to get the deployed `libraryVersion` (3044) cached for `fs_check_version`. |

Note: every tool in this table is read-only with respect to the model, but
`onshape_eval_featurescript` spends 1 quota call per invocation and the render
tool spends ~1; the plain status/check tools are the cheap reads.

### Mutating tools

Every mutating tool requires the literal boolean `confirm_mutation=true`. A
missing or false value returns an MCP tool error before an Onshape client is
constructed or a remote request is sent.

| Tool | Mutation |
|---|---|
| `onshape_upload_feature_studio` | Overwrites configured Feature Studio contents and compiles the feature spec. |
| `onshape_create_validation_part_studio` | Creates a cloud Part Studio; by default updates local `partStudioId`. |
| `onshape_instantiate_feature` | Adds a custom feature to a Part Studio. Repeated calls add additional features. |
| `onshape_run_validation_pipeline` | Uploads, creates, instantiates, validates, and optionally renders. It creates a new Part Studio on every call. |

**Every mutating tool also preflights against the annual quota budget before
any remote call** — upload ~4 calls, create 1, instantiate 2, pipeline ~15 with
render / ~10 without. When the configured budget would be exceeded the tool
blocks with the shortfall instead of spending API calls.

The quota ledger (`config/api-usage.json`, gitignored) is passive: every 2xx/3xx
response counts toward the annual limit and each response's
`X-Rate-Limit-Remaining` header is captured — **zero extra API calls**, because
Onshape has no public quota-query endpoint. Configure the annual budget in
`config/onshape-state.json` under `apiQuota` (`{"accountType": "professional"}`
maps to the official 5000/year, or set `{"annualLimit": N}` directly). Seed it
with your real year-to-date usage — `{"accountType": "standard",
"alreadyConsumed": 119}` — read from the Onshape UI (My Account → Developer);
the local ledger is added on top (`consumed = alreadyConsumed + ledgerConsumed`).
After any other client spends quota, re-read the UI total and set
`alreadyConsumed = UI_total - ledgerConsumed` to recalibrate. A 402 response is
the server's real "annual limit exhausted" signal. Without an `apiQuota` config
the tools degrade to rate-limit-only reporting.

The confirmation field is defense in depth for autonomous MCP clients. It does
not replace the MCP host's own approval UI. Configure the host to ask before
mutating tools whenever it supports per-tool permissions.

## Credential and error boundary

- `onshape-credentials.json` remains ignored by `.gitignore`.
- Tool responses never include the Basic/Bearer authorization header, access key,
  secret key, access token, or credential-file contents.
- Network errors return endpoint status/details from Onshape but not request
  headers. Server tracebacks go to standard error, never the MCP protocol stream.
- Document/workspace/element IDs are operational identifiers rather than API
  secrets. Use `redact_ids=true` on `onshape_get_project_state` when sharing logs.
- The server writes only JSON-RPC messages to standard output. Do not add regular
  `print()` calls to stdout; diagnostics belong on stderr.

## Tests

Local protocol and mutation-guard tests do not contact Onshape:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile mcp_server.py onshape_fs_mcp/*.py scripts/*.py examples/branch-cable-trophy/scripts/*.py
```

A credentialed read-only integration smoke test was run against the configured
workspace. It verified:

- MCP initialization and 32-tool discovery;
- the compiled `branchCableTrophyDisplay` spec with 21 parameters;
- Part Studio custom-feature status `OK` and exactly 132 parts;
- bounds within the validation contract;
- a non-empty 300 x 300 `reference_like` PNG returned as MCP image content;
- no credential material in stdout/tool results.

The integration test uses only GET endpoints and does not create or update cloud
resources. The mutating tools were tested at their confirmation boundary only;
the existing validated CLI/API workflow remains the implementation beneath them.
