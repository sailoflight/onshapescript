FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-ok   — ValueWithUnits 混合单位运算。
// 符号风险：centimeter 未在 trophy 中使用（millimeter 已验证）。
annotation { "Feature Type Name" : "Units arithmetic" }
export const unitsArithmetic = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        isLength(definition.baseHeight, { (millimeter) : [14, 18, 28] } as LengthBoundSpec);
    }
    {
        var len = 5 * millimeter + 2 * centimeter;
        opExtrude(context, id + "extrude", {
                "entities" : qCreatedBy(id, EntityType.BODY),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : len
            });
    });
