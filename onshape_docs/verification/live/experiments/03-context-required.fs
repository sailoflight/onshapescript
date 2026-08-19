FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-error  — op* 标准签名为 (context, id, definition)；缺 context 应为编译错误。
annotation { "Feature Type Name" : "Missing context" }
export const missingContext = defineFeature(function(definition is map)
{
    opExtrude(id + "x", {
            "entities" : qCreatedBy(id, EntityType.BODY),
            "direction" : Z_DIRECTION,
            "endBound" : BoundingType.BLIND,
            "endDepth" : definition.baseHeight
        });
});
