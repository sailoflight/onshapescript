FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-ok   — Vector 运算符重载（+/-/*/norm）。
// 符号风险：vector()/norm() 未在 trophy 中使用（trophy 用 mmVector）。
annotation { "Feature Type Name" : "Vector operators" }
export const vectorOperators = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        isLength(definition.baseHeight, { (millimeter) : [14, 18, 28] } as LengthBoundSpec);
    }
    {
        var a = vector(1, 2, 3) * millimeter;
        var b = a - vector(0.5, 0.5, 0.5) * millimeter;
        var dir = b / norm(b);
        opExtrude(context, id + "extrude", {
                "entities" : qCreatedBy(id, EntityType.BODY),
                "direction" : dir,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.baseHeight
            });
    });
