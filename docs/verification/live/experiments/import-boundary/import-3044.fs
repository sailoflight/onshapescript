FeatureScript 3044;
import(path : "onshape/std/geometry.fs", version : "3044.0");

// Cross-version import boundary probe (equal to runtime). See import-3029.fs
// for why the body reads definition.size: specCount==1 means the version
// imported; 0 + errorType means rejection. Mirrors scripts/live_gap_probe.py.
annotation { "Feature Type Name" : "ImportBoundaryProbe" }
export const importBoundaryProbe = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        isLength(definition.size);
    }
    {
        opExtrude(context, id + "extrude", {
                "entities" : qCreatedBy(id, EntityType.BODY),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.size
            });
    });
