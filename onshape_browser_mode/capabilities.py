"""Data-driven whole-feature capabilities: bounded inputs, generated FeatureScript.

The precedent is `browser_spiral_ridge`: bounded numeric inputs, no raw script or
CSS exposed to the caller, generated `opHelix` + `opSweep` source that passes the
local checker, compile-gated deploy, applied-feature acceptance. This module
extracts that shape into a contract so a capability is DATA plus a source
builder, not another tool implementation.

Two rules shape the contract:

* **A caller supplies values, never code.** Every exposed parameter is a bounded
  number, a boolean, or a closed enum. Queries (which face or edge to act on) are
  deliberately NOT capability values: they are declared inside the generated
  feature's precondition, so a human picks them in the Onshape dialog where the
  geometry is visible. A capability therefore cannot be asked to fillet an edge
  that does not exist yet.
* **A capability is a closed closure.** `custom.extrude` may internally use
  `opExtrude` and `opBoolean`, but its card shows only `depth` and `remove`.
  Callers never see the implementation, and adding a capability adds no tool.

Every FeatureScript identifier used by the builders is checked against the
vendored reference by `dev/tests/test_capabilities.py`; a template may only
reference symbols that actually exist in `onshape_docs/reference/`. That gate is
offline-only and does NOT prove the source compiles -- compilation and geometric
acceptance require the real machine and are not claimed here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

# The std-library version the generated sources target. Kept identical to the
# proven spiral_ridge source so every capability is deployed the same way.
FEATURESCRIPT_VERSION = "3044"

# The single import that makes the whole geometry surface reachable: geometry.fs
# re-exports common.fs (which re-exports valueBounds.fs) and the operation,
# feature, and .gen enum modules the builders below reference.
GEOMETRY_IMPORT = f'import(path : "onshape/std/geometry.fs", version : "{FEATURESCRIPT_VERSION}.0");'


class CapabilityError(ValueError):
    """A caller-supplied capability name or value that cannot be satisfied."""


@dataclass(frozen=True)
class Parameter:
    """One bounded capability input. `kind` decides the validation and the
    rendering; there is deliberately no free-form string or code kind."""

    name: str
    kind: str
    description: str
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()

    def card(self) -> dict[str, Any]:
        """Context-facing description: no source, no implementation detail."""
        payload: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "default": self.default,
        }
        if self.kind == "length":
            payload["unit"] = "mm"
            payload["range"] = [self.minimum, self.maximum]
        elif self.kind == "number":
            payload["range"] = [self.minimum, self.maximum]
        elif self.kind == "enum":
            payload["choices"] = list(self.choices)
        return payload

    def validate(self, value: Any) -> Any:
        if self.kind == "boolean":
            if not isinstance(value, bool):
                raise CapabilityError(f"{self.name} must be true or false")
            return value
        if self.kind == "enum":
            if value not in self.choices:
                raise CapabilityError(
                    f"{self.name} must be one of {', '.join(self.choices)}; got {value!r}"
                )
            return value
        # length and number share the numeric path; `bool` is an int in Python but
        # never a measurement, so it is rejected explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CapabilityError(f"{self.name} must be a number")
        numeric = float(value)
        if numeric != numeric or numeric in (float("inf"), float("-inf")):
            raise CapabilityError(f"{self.name} must be a finite number")
        if self.minimum is not None and numeric < self.minimum:
            raise CapabilityError(f"{self.name} must be >= {self.minimum}")
        if self.maximum is not None and numeric > self.maximum:
            raise CapabilityError(f"{self.name} must be <= {self.maximum}")
        return numeric

    def literal(self, value: Any) -> str:
        """The FeatureScript expression for a validated value."""
        if self.kind == "length":
            return f"{float(value):.9g} * millimeter"
        if self.kind == "boolean":
            return "true" if value else "false"
        return f"{float(value):.9g}"


@dataclass(frozen=True)
class Capability:
    """A whole-feature job: identity, contract, and the source builder."""

    id: str
    feature_type: str
    export_name: str
    use_when: str
    parameters: tuple[Parameter, ...]
    build_source: Callable[[Mapping[str, Any]], str]
    aliases: tuple[str, ...] = ()
    source_verified: str = "structural-only"
    notes: str = ""

    def card(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "featureType": self.feature_type,
            "useWhen": self.use_when,
            "aliases": list(self.aliases),
            "parameters": [parameter.card() for parameter in self.parameters],
            "sourceVerification": self.source_verified,
            "notes": self.notes,
        }

    def normalized(self, values: Mapping[str, Any] | None) -> dict[str, Any]:
        """Defaults filled in, unknown keys and out-of-range values refused."""
        supplied = dict(values or {})
        known = {parameter.name for parameter in self.parameters}
        unknown = sorted(set(supplied) - known)
        if unknown:
            raise CapabilityError(
                f"{self.id} has no parameter(s) {', '.join(unknown)}; "
                f"known parameters: {', '.join(sorted(known)) or 'none'}"
            )
        normalized: dict[str, Any] = {}
        for parameter in self.parameters:
            value = supplied.get(parameter.name, parameter.default)
            normalized[parameter.name] = parameter.validate(value)
        return normalized

    def render(self, values: Mapping[str, Any] | None = None) -> str:
        return self.build_source(self.normalized(values))


def _header(feature_type: str, export_name: str) -> str:
    return (
        f"FeatureScript {FEATURESCRIPT_VERSION};\n"
        f"{GEOMETRY_IMPORT}\n\n"
        f'annotation {{ "Feature Type Name" : "{feature_type}" }}\n'
        f"export const {export_name} = defineFeature("
        "function(context is Context, id is Id, definition is map)\n"
    )


def _build_spiral_ridge(values: Mapping[str, Any]) -> str:
    """Delegates to the proven generator so the precedent IS the capability."""
    from onshape_browser_mode.modeling_transactions import generate_spiral_ridge_script

    return generate_spiral_ridge_script(
        base_radius_mm=values["base_radius"],
        pitch_mm=values["pitch"],
        ridge_width_mm=values["ridge_width"],
        ridge_height_mm=values["ridge_height"],
        length_mm=values["length"],
        clockwise=values["clockwise"],
    )


def _build_fillet(values: Mapping[str, Any]) -> str:
    """`opFillet` with the std library's own bounds constant.

    Field names (`entities`, `radius`, `tangentPropagation`) and the
    `BLEND_BOUNDS` constant are taken from the vendored standard library: the
    `opFillet` doc comment in `geomOperations.fs`, and `valueBounds.fs` for the
    constant itself. The query stays a precondition field, so the caller cannot
    name an edge that does not exist.
    """
    return (
        _header("Bounded fillet", "boundedFillet")
        + """    precondition
    {
        annotation { "Name" : "Edges to fillet",
                    "Filter" : EntityType.EDGE && ConstructionObject.NO && SketchObject.NO && ModifiableEntityOnly.YES }
        definition.entities is Query;

        annotation { "Name" : "Radius" }
        isLength(definition.radius, BLEND_BOUNDS);

        annotation { "Name" : "Tangent propagation", "Default" : true }
        definition.tangentPropagation is boolean;
    }
    {
        const filletDefinition = {
                "entities" : definition.entities,
                "radius" : definition.radius,
                "tangentPropagation" : definition.tangentPropagation
        };
        opFillet(context, id + "fillet", filletDefinition);
    });
"""
    )


def _build_extrude(values: Mapping[str, Any]) -> str:
    """`opExtrude` (plus `opBoolean` for the cut form).

    `opExtrude` takes `entities`/`direction`/`endBound`/`endDepth` and has no
    operation type, so adding and removing material are different operations:
    the documented cut is `opExtrude` + `opBoolean` with `SUBTRACTION`. The
    direction comes from the picked face's own normal, which is the
    `evPlane(context, {"face" : entities}).normal` example in the opExtrude doc,
    so no direction parameter has to be trusted from the caller.
    """
    body = """    precondition
    {
        annotation { "Name" : "Face to extrude",
                    "Filter" : EntityType.FACE && ConstructionObject.NO && SketchObject.NO && ModifiableEntityOnly.YES,
                    "MaxNumberOfPicks" : 1 }
        definition.face is Query;

        annotation { "Name" : "Depth" }
        isLength(definition.depth, LENGTH_BOUNDS);

        annotation { "Name" : "Remove material", "Default" : false }
        definition.remove is boolean;
    }
    {
        const direction = evPlane(context, { "face" : definition.face }).normal;
        const extrudeDefinition = {
                "entities" : definition.face,
                "direction" : direction,
                "endBound" : BoundingType.BLIND,
                "endDepth" : definition.depth
        };
        opExtrude(context, id + "extrude", extrudeDefinition);
        if (definition.remove)
        {
            const cutDefinition = {
                    "tools" : qCreatedBy(id + "extrude", EntityType.BODY),
                    "targets" : qAllModifiableSolidBodies(),
                    "operationType" : BooleanOperationType.SUBTRACTION,
                    "keepTools" : false
            };
            opBoolean(context, id + "cut", cutDefinition);
        }
    });
"""
    return _header("Bounded extrude", "boundedExtrude") + body


def _build_hole(values: Mapping[str, Any]) -> str:
    """`opHole` with a `HoleDefinition` built from the documented constructors.

    Every name here is read from the vendored standard library rather than
    recalled: `opHole`'s `holeDefinition` / `axes` / `targets` fields and its
    example (`geomOperations.fs`), the single-argument
    `holeDefinition(profiles)` overload along with the `holeProfile(positionReference,
    position, radius)` constructor and the "final profile must have a radius of 0"
    rule (`holeUtils.fs`), the `AXIS_POINT` and `LAST_TARGET_END` references
    (`holepositionreference.gen.fs`), `line(origin, direction)`
    (`curveGeometry.fs`), and `evVertexPoint` / `evPlane` (`evaluate.fs`).

    The axis is the human's pick, not the caller's: a start vertex and a planar
    face whose inverted normal is the drill direction. A through hole is the same
    profile list with the cap measured from `LAST_TARGET_END`, so "through" is a
    reference the operation understands rather than a very large depth.
    """
    body = """    precondition
    {
        annotation { "Name" : "Start vertex",
                    "Filter" : EntityType.VERTEX && ConstructionObject.NO && SketchObject.NO,
                    "MaxNumberOfPicks" : 1 }
        definition.vertex is Query;

        annotation { "Name" : "Planar face (drill direction)",
                    "Filter" : EntityType.FACE && GeometryType.PLANE && ConstructionObject.NO && SketchObject.NO && ModifiableEntityOnly.YES,
                    "MaxNumberOfPicks" : 1 }
        definition.face is Query;

        annotation { "Name" : "Diameter" }
        isLength(definition.diameter, LENGTH_BOUNDS);

        annotation { "Name" : "Depth" }
        isLength(definition.depth, LENGTH_BOUNDS);

        annotation { "Name" : "Through all", "Default" : false }
        definition.through is boolean;
    }
    {
        const drillDirection = -evPlane(context, { "face" : definition.face }).normal;
        const profiles = [
                holeProfile(HolePositionReference.AXIS_POINT, 0 * millimeter, definition.diameter * 0.5),
                definition.through
                    ? holeProfile(HolePositionReference.LAST_TARGET_END, 0 * millimeter, 0 * millimeter)
                    : holeProfile(HolePositionReference.AXIS_POINT, definition.depth, 0 * millimeter)
        ];
        const holeInput = {
                "holeDefinition" : holeDefinition(profiles),
                "axes" : [line(evVertexPoint(context, { "vertex" : definition.vertex }), drillDirection)],
                "targets" : qAllModifiableSolidBodies()
        };
        opHole(context, id + "hole", holeInput);
    });
"""
    return _header("Bounded hole", "boundedHole") + body


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        id="custom.spiral_ridge",
        feature_type="Spiral ridge",
        export_name="spiralRidge",
        aliases=("spiral_ridge", "thread", "helix_ridge", "螺纹"),
        use_when=(
            "a helical ridge around a cylinder has to be real geometry, including a "
            "non-standard pitch that externalThread cannot produce"
        ),
        parameters=(
            Parameter("base_radius", "length", "cylinder radius the ridge wraps", 12.0, 0.1, 500.0),
            Parameter("pitch", "length", "axial distance per revolution", 4.0, 0.05, 500.0),
            Parameter("ridge_width", "length", "ridge width along the axis", 1.2, 0.01, 100.0),
            Parameter("ridge_height", "length", "how far the ridge stands off the cylinder", 0.8, 0.01, 100.0),
            Parameter("length", "length", "total wrapped length", 24.0, 0.1, 2000.0),
            Parameter("clockwise", "boolean", "handedness of the helix", False),
        ),
        build_source=_build_spiral_ridge,
        source_verified="live-verified",
        notes=(
            "Extracted unchanged from the browser_spiral_ridge precedent, whose source "
            "and applied feature were verified against the real workbench. This "
            "capability is the contract's proof that the retrofit is faithful."
        ),
    ),
    Capability(
        id="custom.fillet",
        feature_type="Bounded fillet",
        export_name="boundedFillet",
        aliases=("fillet", "round", "圆角"),
        use_when="a constant-radius round is needed on edges the caller would otherwise pick by hand",
        parameters=(
            Parameter("radius", "length", "fillet radius", 2.0, 0.01, 500.0),
            Parameter("tangent_propagation", "boolean", "continue onto tangent edges", True),
        ),
        build_source=_build_fillet,
        notes=(
            "The edges are picked in the Onshape dialog; the capability supplies only "
            "the bounded radius and the propagation choice."
        ),
    ),
    Capability(
        id="custom.extrude",
        feature_type="Bounded extrude",
        export_name="boundedExtrude",
        aliases=("extrude", "cut", "pocket", "拉伸", "切除"),
        use_when="a face has to grow a boss or be cut by a prism along its own normal",
        parameters=(
            Parameter("depth", "length", "extrusion depth along the picked face normal", 10.0, 0.001, 5000.0),
            Parameter("remove", "boolean", "cut the extruded body out of its targets", False),
        ),
        build_source=_build_extrude,
        notes=(
            "Add and remove are two operations in FeatureScript (opExtrude, then "
            "opBoolean SUBTRACTION); the capability hides that split behind one boolean."
        ),
    ),
    Capability(
        id="custom.hole",
        feature_type="Bounded hole",
        export_name="boundedHole",
        aliases=("hole", "drill", "bore", "孔", "打孔"),
        use_when=(
            "a cylindrical hole is needed at a picked vertex, drilled along a picked "
            "planar face's normal"
        ),
        parameters=(
            Parameter("diameter", "length", "hole diameter", 6.0, 0.1, 500.0),
            Parameter("depth", "length", "blind depth from the axis origin; ignored by a through hole", 20.0, 0.1, 2000.0),
            Parameter("through", "boolean", "drill through every target instead of stopping at depth", False),
        ),
        build_source=_build_hole,
        notes=(
            "opHole takes a HoleDefinition built by holeDefinition([holeProfile(...)]) plus "
            "an array of axes; the axis is line(vertex point, inverted face normal), so two "
            "human picks decide the geometry. A through hole uses the LAST_TARGET_END "
            "reference, not a large depth. structural-only: never compiled or applied."
        ),
    ),
)


def _index() -> dict[str, Capability]:
    table: dict[str, Capability] = {}
    for capability in CAPABILITIES:
        for name in (capability.id, capability.id.split(".", 1)[-1], *capability.aliases):
            key = name.strip().lower()
            if key in table and table[key] is not capability:
                raise CapabilityError(f"capability alias {name!r} is claimed twice")
            table[key] = capability
    return table


def resolve(name: str) -> Capability:
    """An exact id, its suffix, or an alias; never a fuzzy guess."""
    if not isinstance(name, str) or not name.strip():
        raise CapabilityError("capability must be a non-empty string")
    key = name.strip().lower()
    capability = _index().get(key)
    if capability is None:
        known = ", ".join(sorted({item.id for item in CAPABILITIES}))
        raise CapabilityError(f"unknown capability {name!r}; known capabilities: {known}")
    return capability


def cards() -> list[dict[str, Any]]:
    """Every capability card: identity, contract, routing, no implementation."""
    return [capability.card() for capability in CAPABILITIES]


# Query tokens that match nothing on their own, so a search for "make a fillet
# on this part" ranks the fillet card rather than whichever card mentions "make".
_STOP_WORDS = frozenset({
    "a", "an", "the", "on", "in", "to", "for", "this", "that", "and", "or", "with",
    "make", "add", "of", "it", "its", "is", "by", "at", "from", "into", "as",
})


def _tokens(query: str) -> list[str]:
    return [
        token for token in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", query.lower())
        if token and token not in _STOP_WORDS
    ]


def _words(text: str) -> set[str]:
    """Whole words only: "no" must not match "normal" in a card's prose."""
    return {word for word in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", text.lower()) if word}


def search(query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Bounded card search: identity, contract and routing, never implementation.

    Ranking is deliberately simple and inspectable -- an exact id or alias beats
    a `use_when` word match -- because the point of the card layer is that a
    normal call needs no implementation source and no recursive expansion.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 5:
        raise CapabilityError("limit must be an integer from 1 through 5")
    tokens = _tokens(query if isinstance(query, str) else "")
    if not tokens:
        return []
    matches: list[dict[str, Any]] = []
    for capability in CAPABILITIES:
        strong = {capability.id.lower(), capability.id.split(".", 1)[-1].lower(),
                  *(alias.lower() for alias in capability.aliases)}
        strong.discard("")
        middle_words = _words(f"{capability.feature_type} {capability.export_name}")
        middle_words.discard("")
        weak_words = _words(f"{capability.use_when} {capability.notes}")
        weak_words.discard("")
        score = 0
        strong_hits = middle_hits = weak_hits = 0
        matched: list[str] = []
        for token in tokens:
            if token in strong or (len(token) >= 4 and any(token in item for item in strong)):
                score += 6 if token in strong else 3
                strong_hits += 1
            elif token in middle_words:
                score += 2
                middle_hits += 1
            elif token in weak_words:
                score += 1
                weak_hits += 1
            else:
                continue
            matched.append(token)
        # One incidental prose word ("feature", "part") is not a match; naming a
        # capability, an alias, or its feature type is.
        if not matched or not (strong_hits or middle_hits or weak_hits >= 2):
            continue
        matches.append({"card": capability.card(), "score": score, "matchedOn": matched})
    matches.sort(key=lambda item: (-item["score"], item["card"]["id"]))
    return matches[:limit]


def plan(name: str, values: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve, validate, and render WITHOUT touching a browser or the network.

    The returned `featureName` is what applied-feature acceptance matches in the
    Part Studio Feature List (the feature type name as Onshape displays it).
    """
    capability = resolve(name)
    normalized = capability.normalized(values)
    source = capability.build_source(normalized)
    return {
        "capability": capability.card(),
        "values": normalized,
        "featureName": capability.feature_type,
        "source": source,
        "sourceLength": len(source),
        "lineCount": source.count("\n") + 1,
        "sourceVerification": capability.source_verified,
        "alias": {"requested": name, "resolved": capability.id},
    }
