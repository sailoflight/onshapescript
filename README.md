# Onshape FeatureScript MCP server

A local Model Context Protocol server that helps an LLM agent write **Onshape
FeatureScript** and verify it in a real Feature Studio. The standard library is
barely present in language-model training data, so this project vendors the
official reference material and exposes it as offline query tools, alongside
credential-safe Onshape REST tools for compiling and validating your code.

```
mcp_server.py          stdio MCP server (JSON-RPC over stdin/stdout)
onshape_fs_mcp/        Python package: REST client, Onshape operations, FS reference queries
reference/             vendored official material (fsdoc/ pages + std-library/ source)
scripts/               reference fetch + index build entry points
examples/              the Branch Cable Trophy model as a worked FeatureScript example
config/                non-secret target state + parameter sets for the current FeatureScript
docs/                  server and tool documentation
tests/                 offline protocol tests (no Onshape contact)
```

## MCP tools (25)

**FeatureScript reference — local, offline** (the core value):

| Tool | Purpose |
|---|---|
| `fs_check_version` | Verify the vendored reference version; warn `docs-behind` for newer targets, plus index-consistency health, the REST API spec version, and an optional latest-version probe (`check_latest`) |
| `fs_update_reference` | Re-fetch the official docs + std library and rebuild the indexes; returns a compact change summary (version before/after, added/removed/changed counts). Optionally also refreshes the REST API spec (`include_onshape_api`). Mutating: requires `confirm_mutation=true` |
| `fs_quick_reference` | The curated distilled cheat-sheet (reference/quick-reference.md), small enough to load in one call |
| `fs_list_modules` | Standard library modules grouped by category |
| `fs_list_functions` | Functions/types/constants/predicates with signatures, filtered |
| `fs_get_function` | Full entry: signature, parameters, requirements, examples, return type |
| `fs_get_type` | Type/enum definition and allowed values |
| `fs_search` | Ranked keyword search across the whole reference and the guide |
| `fs_guide_section` | FeatureScript language guide pages/sections as plain text |
| `fs_library_source` | Real standard library implementation source for a module/function |

**Onshape REST API reference — local, offline** (the Onshape REST surface, served
from the live OpenAPI definition vendored under `reference/onshape-api/`):

| Tool | Purpose |
|---|---|
| `onshape_api_list_tags` | The 42 REST domain groups (Account, Assembly, Document, FeatureStudio, PartStudio, ...) with descriptions |
| `onshape_api_search` | Ranked keyword search across every REST endpoint (method/path/operationId/summary) |
| `onshape_api_endpoint` | Full definition of one operation: parameters, responses, schema references |
| `onshape_api_schema` | A REST response/request schema (e.g. `BTDocumentElementInfo`) and its properties |

**Onshape REST — inspect and validate your FeatureScript** (existing tools, kept):
read-only `onshape_get_project_state`, `onshape_get_parameter_set`,
`onshape_build_parameter_payload`, `onshape_list_document_elements`,
`onshape_get_feature_studio_status`, `onshape_check_model`,
`onshape_render_preview`; mutating (require `confirm_mutation=true`)
`onshape_upload_feature_studio`, `onshape_create_validation_part_studio`,
`onshape_instantiate_feature`, `onshape_run_validation_pipeline`.

See `docs/mcp-server.md` for the complete catalog, security boundary, and tests.

## The vendored reference

`scripts/fetch_reference.py` downloads, and `scripts/build_fsdoc_index.py`
indexes, the official FeatureScript material into `reference/`:

- `reference/fsdoc/` — the FsDoc pages from `cad.onshape.com` (function/type
  reference, language guide, tutorial) plus `index.json` (every function, type,
  parameter, and description as structured text), `guide.json` (the guide pages
  parsed into heading sections with typed blocks — paragraphs, code, tables,
  lists), and `quick.json` (one line per entry for cheap context loading).
- `reference/std-library/` — the standard library source mirrored from
  `github.com/javawizard/onshape-std-library-mirror` (MIT), because the real
  implementation is the highest-fidelity reference.
- `reference/quick-reference.md` — a curated, distilled cheat-sheet synthesized
  from the docs (served by `fs_quick_reference`).

`scripts/fetch_onshape_api.py` downloads the **live** Onshape REST API OpenAPI
definition from `https://cad.onshape.com/api/openapi` (authenticated) into
`reference/onshape-api/openapi.json`, and `scripts/build_onshape_api_index.py`
flattens it into `api_index.json` (302 endpoints, 1226 schemas) +
`api_quick.json` for the `onshape_api_*` tools. Because it is pulled live from
the server, it always reflects the running deployment — no stale snapshot.

Everything prose-shaped is a JSON index; the large source stays as files read
on demand. Both indexes record the source sha256 so `fs_check_version` can
report when a re-fetch left them stale.

Re-sync after an upstream change:

```bash
python3 scripts/fetch_reference.py
python3 scripts/build_fsdoc_index.py
python3 scripts/fetch_onshape_api.py      # needs onshape-credentials.json
python3 scripts/build_onshape_api_index.py
```

See `docs/fs-assistant.md` for usage guidance and the tool workflows.

## Running the MCP server

```bash
python3 mcp_server.py
```

Configure an MCP client with an absolute command/path, for example:

```json
{
  "mcpServers": {
    "onshape-featurescript": {
      "command": "python3",
      "args": ["/home/lijq/code/onshapescript/mcp_server.py"],
      "cwd": "/home/lijq/code/onshapescript"
    }
  }
}
```

Non-secret state (`config/onshape-state.json`) and credentials
(`onshape-credentials.json`, gitignored) configure which Onshape document the
REST tools target. `ONSHAPE_STATE`, `ONSHAPE_CREDENTIALS`,
`ONSHAPE_PARAMETERS_DIR`, and `ONSHAPE_OUTPUTS_DIR` override the paths.

## Example: Branch Cable Trophy

`examples/branch-cable-trophy/` is a complete, validated FeatureScript model
that demonstrates the language (features, sketches, sweeps, patterns, fillets,
appearance/name properties) and the workflow. It doubles as the live testbed for
the REST tools: its Feature Studio is the configured target. See
`examples/branch-cable-trophy/README.md`.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile mcp_server.py onshape_fs_mcp/*.py scripts/*.py examples/branch-cable-trophy/scripts/*.py
```
