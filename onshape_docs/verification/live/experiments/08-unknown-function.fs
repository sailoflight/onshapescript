FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-error  — q*/op*/ev* 命名即语法；拼错函数名为编译错误。
annotation { "Feature Type Name" : "Unknown function" }
export const unknownFunction = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        isLength(definition.baseHeight, { (millimeter) : [14, 18, 28] } as LengthBoundSpec);
    }
    {
        var q = qDoesNotExist(EntityType.BODY);
        opExtrude(context, id + "extrude", {
                "entities" : q,
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.baseHeight
            });
    });
