FeatureScript 3050;
import(path : "onshape/std/geometry.fs", version : "3050.0");

// Cross-version import boundary probe (upper bound, NOT yet run live — the
// earlier runs' probes had no bound spec, so every version read specCount 0).
// Expected to be REJECTED if the deployed runtime is < 3050: with a bound-spec
// precondition, rejection surfaces as specCount==0 + errorType/errorMessages
// (or a 4xx on upload). Mirrors scripts/live_symbol_sweep.py's probe("3050").
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
