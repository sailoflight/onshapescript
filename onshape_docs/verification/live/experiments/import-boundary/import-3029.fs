FeatureScript 3029;
import(path : "onshape/std/geometry.fs", version : "3029.0");

// Cross-version import boundary probe (lower bound). The precondition uses a
// BOUND SPEC: a feature emits a parameter spec only when a precondition
// parameter carries one (a bare isLength yields specCount 0 for any version —
// symbol-sweep 2026-08-14, body irrelevant). So specCount==1 means "version
// imported fine"; 0 + errorType means "rejected". Mirrors scripts/live_symbol_sweep.py.
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
