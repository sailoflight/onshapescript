FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-ok   — 三层 q/op/ev 模型。独立最小文件实测通过（探针 F）。
annotation { "Feature Type Name" : "Three layer probe" }
export const threeLayerProbe = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Base height" }
        isLength(definition.baseHeight, { (millimeter) : [14, 18, 28] } as LengthBoundSpec);
    }
    {
        var q = qCreatedBy(id, EntityType.BODY);
        opExtrude(context, id + "extrude", {
                "entities" : q,
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.baseHeight
            });
    });
