FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-ok   — Id + string 拼接产生子 feature Id（探针 F 已验证 id + "extrude"）。
annotation { "Feature Type Name" : "Id concat" }
export const idConcat = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        isLength(definition.baseHeight, { (millimeter) : [14, 18, 28] } as LengthBoundSpec);
    }
    {
        var childId = id + "sub";
        opExtrude(context, childId, {
                "entities" : qCreatedBy(id, EntityType.BODY),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.baseHeight
            });
    });
