FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-ok   — 官方文档引用 GBTErrorStringEnum 但无定义块；
// 本实验验证该枚举在当前版本存在、值是可枚举标识符。
// 若枚举在当前版本不存在，会 FAIL —— 那本身就是有效发现。
annotation { "Feature Type Name" : "GBT error enum" }
export const gbtErrorEnum = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Error code" }
        isType(definition.errorCode, GBTErrorStringEnum);
    }
    {
        var e : GBTErrorStringEnum = definition.errorCode;
        opExtrude(context, id + "extrude", {
                "entities" : qCreatedBy(id, EntityType.BODY),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : 1 * millimeter
            });
    });
