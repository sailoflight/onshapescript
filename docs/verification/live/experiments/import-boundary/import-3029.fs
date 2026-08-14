FeatureScript 3029;
import(path : "onshape/std/geometry.fs", version : "3029.0");

// Cross-version import boundary probe (lower bound). The body MUST read
// definition.size: featurespecs are emitted per definition.* field the body
// uses (gap-probe 2026-08-14). An empty body yields 0 specs for any version
// and is indistinguishable from a version-boundary rejection. With this body,
// specCount==1 means "version imported fine"; 0 + errorType means "rejected".
// Source mirrors experiments/01-three-layer.fs and scripts/live_gap_probe.py.
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
