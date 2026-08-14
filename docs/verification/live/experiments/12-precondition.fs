FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-ok   — precondition（is* 谓词）编译通过；运行时类型错误是红 feature，
// 不是编译错误（探针 F 已验证同结构）。
annotation { "Feature Type Name" : "Precondition compiles" }
export const preconditionCompiles = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Base height" }
        isLength(definition.baseHeight, { (millimeter) : [14, 18, 28] } as LengthBoundSpec);
    }
    {
        opExtrude(context, id + "extrude", {
                "entities" : qCreatedBy(id, EntityType.BODY),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.baseHeight
            });
    });
