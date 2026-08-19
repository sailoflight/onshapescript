FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");

// EXPECT: compile-ok   — array 参数类型被接受（size() 内建）。
annotation { "Feature Type Name" : "Array parameter" }
export const arrayParameter = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        isLength(definition.baseHeight, { (millimeter) : [14, 18, 28] } as LengthBoundSpec);
        annotation { "Name" : "Names" }
        isArray(definition.names);
    }
    {
        var n = size(definition.names);
        if (n == 0)
        {
            opExtrude(context, id + "extrude", {
                    "entities" : qCreatedBy(id, EntityType.BODY),
                    "direction" : Z_DIRECTION,
                    "endBound" : BoundingType.BLIND,
                    "endDepth" : definition.baseHeight
                });
        }
    });
