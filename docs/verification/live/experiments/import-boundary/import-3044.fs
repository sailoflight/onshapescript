FeatureScript 3044;
import(path : "onshape/std/geometry.fs", version : "3044.0");

// Cross-version import boundary probe (equal to runtime). See import-3029.fs
// for why the precondition carries a BOUND SPEC: specCount==1 means the
// version imported; 0 + errorType means rejection. Mirrors scripts/live_symbol_sweep.py.
annotation { "Feature Type Name" : "ImportBoundaryProbe" }
export const importBoundaryProbe = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        isLength(definition.size, { (millimeter) : [1, 2, 3] } as LengthBoundSpec);
    }
    {
        opExtrude(context, id + "extrude", {
                "entities" : qCreatedBy(id, EntityType.BODY),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.size
            });
    });
