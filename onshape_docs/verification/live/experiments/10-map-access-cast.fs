FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-ok   — map 访问 + `as` 类型断言编译期通过（运行时失败是另一回事）。
annotation { "Feature Type Name" : "Map access cast" }
export const mapAccessCast = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        isLength(definition.baseHeight, { (millimeter) : [14, 18, 28] } as LengthBoundSpec);
    }
    {
        var m = { "scale" : 2.0 };
        var scale = m["scale"] as number;
        opExtrude(context, id + "extrude", {
                "entities" : qCreatedBy(id, EntityType.BODY),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.baseHeight * scale
            });
    });
