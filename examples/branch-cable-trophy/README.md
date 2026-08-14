# Branch Cable Trophy — example FeatureScript model

A parametric Onshape FeatureScript model of a trophy-style branching cable
display, built from a single reference image. It is the worked example that the
MCP server's REST tools validate: this Feature Studio is the configured target
in `config/onshape-state.json`.

The model is a stylistic approximation, not a dimensionally accurate reverse
engineering.

## Contents

- `branchCableTrophyDisplay.fs` — the standalone custom feature (`FeatureScript 3029`).
- `08041125_00.png` — source reference image.
- `scripts/` — CLI entry points for the upload/instantiate/validate/render loop.
- `docs/` — feature parameters, validation contract, visual-review and setup notes.
- `outputs/` — rendered previews and the latest model-check report.

The parameter sets and target document state are shared with the MCP server and
live in the project root `config/` (`model.default.json`, `model.preview.json`,
`onshape-state.json`).

## Verified model

- FeatureScript version: `3029` — compile/spec and regeneration status: OK
- Detailed part count: 132 (1 base, 1 plaque insert, 12 root collars,
  84 swept strands, 17 corner connectors, 17 terminals)
- Preview part count: 65 (single coarse strand per cable)
- Bounds within the validation contract (X ±65 mm, Y ±45 mm, Z 0–115 mm)

## Quick validation

With `onshape-credentials.json` present at the project root:

```bash
cd scripts
python3 validate_pipeline.py
```

The full pipeline creates a new validation Part Studio on every run, then
uploads, instantiates, verifies, and renders the model. For a non-creating
recheck of the current result, run `python3 check_model.py` and
`python3 render_previews.py`.

See `docs/setup.md` and `docs/onshape-api-workflow.md` for details, and
`docs/feature-parameters.md` for the parameter reference.
