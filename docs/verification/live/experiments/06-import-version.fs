FeatureScript {{MAJOR}};
import(path : "onshape/std/geometry.fs", version : "2960.0");

// EXPECT: compile-error  — vendored 镜像版本 2960.0 落后于真实 Feature Studio
// （trophy 用 3029.0 编译成功），import 旧版本应为编译错误而非警告。
annotation { "Feature Type Name" : "Stale import version" }
export const staleImport = defineFeature(function(context is Context, id is Id, definition is map)
{
    opExtrude(context, id + "x", {
            "entities" : qCreatedBy(id, EntityType.BODY),
            "direction" : Z_DIRECTION,
            "endBound" : BoundingType.BLIND,
            "endDepth" : 1 * millimeter
        });
});
