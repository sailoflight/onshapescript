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
| `fs_list_modules` | Lists standard library modules grouped by category (optional filter). |
| `fs_list_functions` | Lists functions/types/constants/predicates with signatures and summaries, filtered by module/category/kind/prefix. |
| `fs_get_function` | Full entry: signature, parameters (type, requirement, description, example), return type, module. |
| `fs_get_type` | Type/enum definition with every allowed value. |
| `fs_search` | Ranked keyword search across the entire reference. |
| `fs_guide_section` | One FsDoc guide page, or a section of it, as plain text with fenced code blocks. |
| `fs_library_source` | The real standard library implementation source, optionally the window around one function. |

### Local and read-only

| Tool | Behavior |
|---|---|
| `onshape_get_project_state` | Reads non-secret local state and credential-file presence. It never reads or returns credential values. |
| `onshape_get_parameter_set` | Reads the maintained detailed or simplified parameter map. |
| `onshape_build_parameter_payload` | Converts local values into explicit Onshape custom-feature parameter blocks. |

### Authenticated read-only Onshape tools

| Tool | Behavior |
|---|---|
| `onshape_list_document_elements` | Lists elements and current microversions in the configured workspace. |
| `onshape_get_feature_studio_status` | Reads Feature Studio metadata and compiled feature specifications. |
| `onshape_check_model` | Checks feature state, 132/65 part count, required names, and bounds without writing the report file. |
| `onshape_render_preview` | Returns one shaded PNG as MCP image content; `save=true` additionally writes `outputs/previews/<view>.png`. |

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

- MCP initialization and 18-tool discovery;
- the compiled `branchCableTrophyDisplay` spec with 21 parameters;
- Part Studio custom-feature status `OK` and exactly 132 parts;
- bounds within the validation contract;
- a non-empty 300 x 300 `reference_like` PNG returned as MCP image content;
- no credential material in stdout/tool results.

The integration test uses only GET endpoints and does not create or update cloud
resources. The mutating tools were tested at their confirmation boundary only;
the existing validated CLI/API workflow remains the implementation beneath them.
