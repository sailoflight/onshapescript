FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-error  — op* 的 definition 是 map；传标量应为类型错误。
annotation { "Feature Type Name" : "Bad definition type" }
export const badDefinition = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        isLength(definition.baseHeight, { (millimeter) : [14, 18, 28] } as LengthBoundSpec);
    }
    {
        opExtrude(context, id + "x", 5);
    });
