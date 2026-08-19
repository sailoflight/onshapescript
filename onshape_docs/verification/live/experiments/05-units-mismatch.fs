FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-error  — 量纲不匹配（长度 + 无量纲）应为编译错误。
annotation { "Feature Type Name" : "Units mismatch" }
export const unitsMismatch = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        isLength(definition.baseHeight, { (millimeter) : [14, 18, 28] } as LengthBoundSpec);
    }
    {
        var len = 5 * millimeter + 2;
        opExtrude(context, id + "extrude", {
                "entities" : qCreatedBy(id, EntityType.BODY),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : len
            });
    });
