"""Part Studio Feature List mutations: update, delete, rollback, batch update.

Pure request builders and response parsers for the four documented operations
that had no handler in this repository before. Keeping them free of client and
state access means every payload here is testable offline, byte for byte, with
no network and no credentials -- the dry-run path and the live path build the
SAME body through the SAME function, so a test that proves the body proves the
request that would be sent.

Lookup evidence (vendored OpenAPI, `onshape_docs/reference/raw/onshape-api/openapi.json`):

| operation | method | path | request body | response schema |
|---|---|---|---|---|
| `updatePartStudioFeature` | POST | `/partstudios/d/{did}/w/{wid}/e/{eid}/features/featureid/{fid}` | `BTFeatureDefinitionCall-1406` | `BTFeatureDefinitionResponse-1617` |
| `deletePartStudioFeature` | DELETE | same as above | none | `BTFeatureApiBase-1430` |
| `updateRollback` | POST | `.../features/rollback` | documented as `{ "rollbackIndex": integer }` | `BTSetFeatureRollbackResponse-1042` |
| `updateFeatures` | POST | `.../features/updates` | `BTUpdateFeaturesCall-1748` | `BTUpdateFeaturesResponse-1333` |

Two facts come from the spec's own prose rather than its schema, because the
schema for the rollback body is only `{"type": "string"}` and would be wrong to
trust:

* the rollback body is `{ "rollbackIndex": integer }`, and `-1` moves the bar to
  the end of the list;
* `updateFeatures` "does not fully redefine the features; it updates only the
  parameters supplied in the top-level feature structure, and optionally can
  update feature suppression attributes".

The second is why suppression uses `updateFeatures` with a minimal feature
(`featureId` + `suppressed`) instead of re-posting a full definition through
`updatePartStudioFeature`: it is one call with a body measured in bytes, and it
cannot clobber parameters the caller did not mean to touch.

Nothing here has been executed against the real API. See
`dev/tests/fixtures/onshape/feature-list/README.md` for what is and is not
recorded evidence.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from onshape_rest_api_mode.client import compact_feature_response

# btType discriminators, taken verbatim from the vendored spec.
FEATURE_DEFINITION_CALL = "BTFeatureDefinitionCall-1406"
FEATURE = "BTMFeature-134"
UPDATE_FEATURES_CALL = "BTUpdateFeaturesCall-1748"

# `-1` is documented ("Set to `-1` to move the rollback bar to the end of the
# list"); anything below that is not a position.
ROLLBACK_END = -1

# Summarised feature fields. Each is nullable in the API, so every parser below
# returns None rather than inventing a value, and never raises on a partial body.
_FEATURE_FIELDS = (
    "featureId",
    "name",
    "featureType",
    "namespace",
    "suppressed",
    "suppressionConfigured",
)
_STATE_FIELDS = ("featureStatus", "inactive")


def _segment(value: Any, label: str) -> str:
    """A required non-empty path segment, or a ValueError naming the offender."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if "/" in value or "?" in value or "#" in value:
        raise ValueError(f"{label} must not contain '/', '?' or '#': {value!r}")
    return value


def feature_list_path(document_id: str, workspace_id: str, element_id: str) -> str:
    return (
        f"/api/v9/partstudios/d/{_segment(document_id, 'document_id')}"
        f"/w/{_segment(workspace_id, 'workspace_id')}"
        f"/e/{_segment(element_id, 'element_id')}/features"
    )


def feature_path(
    document_id: str,
    workspace_id: str,
    element_id: str,
    feature_id: str,
) -> str:
    """The `featureid` sub-resource: POST replaces, DELETE removes."""
    return feature_list_path(document_id, workspace_id, element_id) + (
        f"/featureid/{_segment(feature_id, 'feature_id')}"
    )


def rollback_path(document_id: str, workspace_id: str, element_id: str) -> str:
    return feature_list_path(document_id, workspace_id, element_id) + "/rollback"


def updates_path(document_id: str, workspace_id: str, element_id: str) -> str:
    return feature_list_path(document_id, workspace_id, element_id) + "/updates"


def validate_rollback_index(value: Any) -> int:
    """Accept only an integer position. `bool` is an `int` in Python and a
    `true` in JSON is never a position, so it is rejected explicitly rather than
    coerced to 1."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("rollback_index must be an integer (-1 moves the bar to the end)")
    if value < ROLLBACK_END:
        raise ValueError(f"rollback_index must be >= {ROLLBACK_END}, got {value}")
    return value


def validate_feature_ids(values: Any) -> list[str]:
    """A non-empty, duplicate-free list of feature ids, order preserved."""
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ValueError("feature_ids must be a list of feature id strings")
    checked: list[str] = []
    for item in values:
        feature_id = _segment(item, "feature_id")
        if feature_id in checked:
            # A duplicate is almost always a copy-paste slip, and the API would
            # apply the same update twice; say so instead of silently deduping.
            raise ValueError(f"feature_ids contains a duplicate: {feature_id!r}")
        checked.append(feature_id)
    if not checked:
        raise ValueError("feature_ids must contain at least one feature id")
    return checked


def feature_definition_call(feature: dict[str, Any]) -> dict[str, Any]:
    """The `BTFeatureDefinitionCall-1406` envelope shared by add + update."""
    if not isinstance(feature, dict):
        raise ValueError("feature must be an object")
    return {"btType": FEATURE_DEFINITION_CALL, "feature": feature}


def feature(
    feature_id: str,
    *,
    suppressed: bool | None = None,
    name: str | None = None,
    namespace: str | None = None,
    feature_type: str | None = None,
    parameters: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A minimal `BTMFeature-134`. Only supplied keys are emitted, because
    `updateFeatures` treats an omitted field as "leave it alone"."""
    body: dict[str, Any] = {
        "btType": FEATURE,
        "featureId": _segment(feature_id, "feature_id"),
    }
    if feature_type is not None:
        body["featureType"] = _segment(feature_type, "feature_type")
    if name is not None:
        body["name"] = _segment(name, "name")
    if namespace is not None:
        body["namespace"] = _segment(namespace, "namespace")
    if suppressed is not None:
        if not isinstance(suppressed, bool):
            raise ValueError("suppressed must be a boolean")
        body["suppressed"] = suppressed
    if parameters is not None:
        body["parameters"] = list(parameters)
    return body


def update_features_body(
    features: Sequence[dict[str, Any]],
    *,
    update_suppression_attributes: bool = False,
    source_microversion: str | None = None,
) -> dict[str, Any]:
    """`BTUpdateFeaturesCall-1748`: update only what is supplied."""
    if isinstance(features, (str, bytes)) or not isinstance(features, Sequence):
        raise ValueError("features must be a list of feature objects")
    checked = list(features)
    if not checked:
        raise ValueError("features must contain at least one feature")
    for item in checked:
        if not isinstance(item, dict) or not item.get("btType"):
            raise ValueError("each feature must be an object with a btType")
    body: dict[str, Any] = {
        "btType": UPDATE_FEATURES_CALL,
        "features": checked,
        "updateSuppressionAttributes": bool(update_suppression_attributes),
    }
    if source_microversion:
        body["sourceMicroversion"] = source_microversion
    return body


def suppression_body(feature_ids: Any, suppressed: bool) -> dict[str, Any]:
    """Suppress or unsuppress existing features in ONE call.

    This is the cheap path: no parameter payload, no full definition, and the
    suppression attributes flag is on (without it the API ignores `suppressed`).
    """
    if not isinstance(suppressed, bool):
        raise ValueError("suppressed must be a boolean")
    ids = validate_feature_ids(feature_ids)
    return update_features_body(
        [feature(feature_id, suppressed=suppressed) for feature_id in ids],
        update_suppression_attributes=True,
    )


def rollback_body(rollback_index: Any) -> dict[str, Any]:
    """The documented rollback payload, NOT the spec's `{"type": "string"}`."""
    return {"rollbackIndex": validate_rollback_index(rollback_index)}


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def summarize_feature(payload: Any) -> dict[str, Any]:
    """Per-feature state, nullable throughout. `suppressionKind` is the btType
    discriminator of `BTMSuppressionState-*`: `ParentSuppressed` means an
    ancestor is suppressed, not that this feature was suppressed directly."""
    feature = _object(payload)
    state = _object(feature.get("suppressionState"))
    summary: dict[str, Any] = {field: feature.get(field) for field in _FEATURE_FIELDS}
    summary["suppressionKind"] = state.get("btType")
    return summary


def summarize_feature_state(payload: Any) -> dict[str, Any]:
    state = _object(payload)
    return {field: state.get(field) for field in _STATE_FIELDS}


def summarize_feature_definition(payload: Any) -> dict[str, Any]:
    """`BTFeatureDefinitionResponse-1617` (POST featureid)."""
    summary = compact_feature_response(_object(payload))
    summary["feature"] = summarize_feature(_object(payload).get("feature"))
    return summary


def summarize_feature_api_base(payload: Any) -> dict[str, Any]:
    """`BTFeatureApiBase-1430` (DELETE featureid): only versioning metadata."""
    base = _object(payload)
    return {
        "btType": base.get("btType"),
        "sourceMicroversion": base.get("sourceMicroversion"),
        "serializationVersion": base.get("serializationVersion"),
        "libraryVersion": base.get("libraryVersion"),
    }


def summarize_rollback(payload: Any) -> dict[str, Any]:
    """`BTSetFeatureRollbackResponse-1042`: where the bar ended up."""
    base = _object(payload)
    microversion = _object(base.get("microversionId"))
    return {
        "rollbackIndex": base.get("rollbackIndex"),
        "sourceMicroversion": base.get("sourceMicroversion"),
        "microversionId": microversion.get("theId"),
    }


def summarize_update_features(payload: Any) -> dict[str, Any]:
    """`BTUpdateFeaturesResponse-1333`: the updated features plus their states.

    `featureStates` is an untyped map (featureId -> `BTFeatureState-1688`), so it
    is normalised to a sorted list to keep the summary deterministic.
    """
    base = _object(payload)
    features = base.get("features")
    features = features if isinstance(features, list) else []
    states = _object(base.get("featureStates"))
    return {
        "features": [summarize_feature(item) for item in features],
        "featureCount": len(features),
        "featureStates": [
            {"featureId": feature_id, **summarize_feature_state(states[feature_id])}
            for feature_id in sorted(states)
        ],
        "sourceMicroversion": base.get("sourceMicroversion"),
    }
