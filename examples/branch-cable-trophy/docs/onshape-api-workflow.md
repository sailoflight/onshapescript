# Onshape API workflow

The automation uses only documented Onshape REST endpoints and Python's standard library.

## Resource state

`config/onshape-state.json` records non-secret IDs:

- `documentId`
- `workspaceId`
- `featureStudioId`
- active validation `partStudioId`
- FeatureScript source path

## Pipeline

Run:

```bash
python3 scripts/validate_pipeline.py
```

The stages are:

1. **Upload Feature Studio**
   - `GET /api/featurestudios/d/{did}/w/{wid}/e/{eid}`
   - Preserve serialization/source-microversion metadata.
   - `POST` the complete FeatureScript contents.
   - `GET .../featurespecs` and require the expected feature type.
2. **Create a clean validation Part Studio**
   - `POST /api/partstudios/d/{did}/w/{wid}`.
   - Save the returned element ID in state.
3. **Resolve the workspace namespace**
   - Read document elements.
   - Build `e<FeatureStudioId>::m<FeatureStudioMicroversion>`.
4. **Instantiate the custom feature**
   - Use the versioned `/api/v9/partstudios/.../features` endpoint.
   - Send all quantity and Boolean parameters explicitly; REST creation does not safely infer FeatureScript UI defaults from an empty parameter list.
5. **Validate**
   - Require custom feature status `OK`.
   - Require 132 detailed-mode parts.
   - Check names and model bounds.
6. **Render**
   - Call the Part Studio shaded-view endpoint.
   - Write front, right, top, isometric, and reference-like PNG files.

## Individual commands

```bash
python3 scripts/upload_feature_studio.py
python3 scripts/create_validation_part_studio.py
python3 scripts/instantiate_feature.py
python3 scripts/check_model.py
python3 scripts/render_previews.py
```

## Safety

The scripts create/update tabs in the configured private Onshape document. They do not delete documents, share resources, publish versions, create releases, or perform Git remote writes.
