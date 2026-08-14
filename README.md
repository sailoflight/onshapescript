# Branch Cable Trophy Display

Parametric Onshape FeatureScript model based on the supplied single-view reference image. The model is a stylistic approximation, not a dimensionally accurate reverse engineering.

## Deliverables

- `branchCableTrophyDisplay.fs` — standalone custom feature; no runtime dependency outside Onshape's standard library.
- `08041125_00.png` — source reference image.
- `docs/` — setup, API workflow, feature parameters, validation, and visual-review notes.
- `scripts/` — reusable deployment and validation entry points.
- `mcp_server.py` — local stdio MCP server exposing credential-safe Onshape tools.
- `onshape_tools/` — standard-library-only Python support code for Onshape REST calls and reusable operations.
- `config/` — non-secret document state and model parameter sets.
- `outputs/previews/` — rendered validation views.
- `temp/` — disposable development artifacts and compatibility wrappers.

## Current verified model

- FeatureScript version: `3029`
- Feature Studio compile/spec status: OK
- Part Studio regeneration status: OK
- Detailed default part count: 132
- 12 root collars
- 17 cable bundles
- 84 detailed swept strands (4/5/6 repeating)
- 17 corner connectors
- 17 terminals
- 1 cylindrical base and 1 blank plaque insert

## Quick validation

With `onshape-credentials.json` present at the project root:

```bash
python3 scripts/validate_pipeline.py
```

> The full pipeline creates a new validation Part Studio on every run and then
> uploads, instantiates, verifies, and renders the model. For a non-creating
> recheck of the currently recorded result, run `python3 scripts/check_model.py`
> and `python3 scripts/render_previews.py`.

See `docs/setup.md` and `docs/onshape-api-workflow.md` for details.

## MCP server

The project includes a dependency-free stdio MCP server around the same reusable
operations as the command-line scripts:

```bash
python3 mcp_server.py
```

Configure an MCP client with an absolute command/path, for example:

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

Read-only tools inspect state, Feature Studio compilation, model invariants, and
shaded previews. Cloud-mutating tools require `confirm_mutation=true`. Credential
values are never returned. See `docs/mcp-server.md` for the complete tool list,
security boundary, and test commands.
