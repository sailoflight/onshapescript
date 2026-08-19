"""Reusable Onshape operations shared by scripts and the MCP server."""

from __future__ import annotations

import base64
import hashlib
import time
from datetime import datetime, timezone
from typing import Any

from onshape_rest_api_mode.client import (
    DEFAULT_PARAMETERS_PATH,
    PARAMETERS_DIR,
    PREVIEW_DIR,
    ROOT,
    STATE_PATH,
    OnshapeClient,
    compact_feature_response,
    load_json,
    parameter_payload,
    save_state,
)

FEATURE_TYPE = "branchCableTrophyDisplay"
FEATURE_NAME = "Branch cable trophy display"
PARAMETER_PATHS = {
    "default": DEFAULT_PARAMETERS_PATH,
    "preview": PARAMETERS_DIR / "model.preview.json",
}
# A cached element-mirror microversion is only trustworthy for a MUTATION if the
# mirror was synced recently. Onshape has no free way to query a Feature
# Studio's current microversion, and a stale one silently pins an OLD definition
# (microversions are immutable snapshots, so the instantiate POST succeeds
# against the old content instead of failing). Instantiate re-fetches the
# element list when the mirror is older than this window.
MICROVERSION_CACHE_MAX_AGE_SECONDS = 300
REQUIRED_PREFIXES = [
    "base",
    "plaqueInsert_blank",
    "rootCollars_",
    "blackStrands_",
    "yellowStrands_",
    "cornerConnectors_",
    "terminals_",
]
BOUNDS_LIMITS = {
    "lowX": -0.065,
    "highX": 0.065,
    "lowY": -0.045,
    "highY": 0.045,
    "lowZ": -0.001,
    "highZ": 0.115,
}
VIEW_MATRICES = {
    "front": "front",
    "right": "right",
    "top": "top",
    "iso": "0.612,0.612,0,0,-0.354,0.354,0.707,0,0.707,-0.707,0.707,0",
    "reference_like": "0.82,0.45,0,0,-0.25,0.46,0.85,0,0.38,-0.70,0.53,0",
}


def public_state(state: dict[str, Any], redact_ids: bool = False) -> dict[str, Any]:
    """Return the non-secret project state, optionally masking Onshape IDs."""
    result = {
        key: state.get(key)
        for key in (
            "baseUrl",
            "documentId",
            "workspaceId",
            "featureStudioId",
            "partStudioId",
            "featureScriptFile",
        )
    }
    if redact_ids:
        for key in ("documentId", "workspaceId", "featureStudioId", "partStudioId"):
            value = result.get(key)
            if value:
                result[key] = f"{str(value)[:4]}…{str(value)[-4:]}"
    return result


def load_parameter_set(name: str) -> dict[str, Any]:
    try:
        path = PARAMETER_PATHS[name]
    except KeyError as error:
        raise ValueError(f"Unknown parameter set: {name}") from error
    return load_json(path)


def merged_parameters(name: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = load_parameter_set(name)
    if overrides:
        unknown = sorted(set(overrides) - set(parameters))
        if unknown:
            raise ValueError(f"Unknown FeatureScript parameters: {', '.join(unknown)}")
        for key, value in overrides.items():
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError(f"Parameter {key} must be a string, number, or boolean")
            parameters[key] = value
    return parameters


def resolve_part_studio_id(
    client: OnshapeClient,
    part_studio_id: str | None = None,
) -> tuple[str, str, str]:
    """Resolve a usable Part Studio id WITHOUT any implicit network walk.

    Onshape IDs are cached in config/onshape-state.json (constraint: cache
    stable metadata; refresh is an explicit action). Walking the document
    (GET elements -> GET parts per studio) is the exact ~10-call trap the quota
    policy forbids, so this only ever returns the explicit id or the cached
    one. If neither is present, it raises and tells the caller to pass the id —
    it never silently re-discovers elements.
    """
    state = client.state
    did, wid = state["documentId"], state["workspaceId"]
    eid = part_studio_id or state.get("partStudioId")
    if not eid:
        raise RuntimeError(
            "No Part Studio id available: pass part_studio_id explicitly, or set "
            "partStudioId in config/onshape-state.json. Implicit document walking "
            "is disabled to protect API quota."
        )
    return did, wid, eid


def _elements_from_state(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract the cached element table from a state dict, keyed by element id."""
    return {
        item.get("id"): dict(item)
        for item in state.get("elements", [])
        if isinstance(item, dict) and item.get("id")
    }


def _read_state_file() -> dict[str, Any]:
    try:
        return load_json(STATE_PATH)
    except Exception:
        return {}


def _merge_state_to_disk(updates: dict[str, Any]) -> None:
    """Merge `updates` onto the on-disk state file, preserving keys edited
    externally since a client loaded its in-memory snapshot. Only the given keys
    are written; hand-maintained keys (partStudioId, featureStudioId,
    apiQuota.alreadyConsumed, ...) are never clobbered by a stale in-memory
    snapshot."""
    disk = _read_state_file()
    disk.update(updates)
    save_state(disk)


def _elements_cache(client: OnshapeClient) -> dict[str, dict[str, Any]]:
    """Return the cached element table (config/onshape-state.json "elements"),
    keyed by element id. The table is the local mirror of the workspace's
    elements: id/name/type are stable (refresh is an explicit action), while
    microversionId is the one mutable field, rolled forward from mutation and
    status responses so later operations don't re-query it."""
    return _elements_from_state(client.state)


def _cache_age_seconds(state: dict[str, Any]) -> float | None:
    """Seconds since the element mirror was last synced, or None if never/unknown."""
    timestamp = state.get("elementsUpdatedAt")
    if not timestamp:
        return None
    try:
        cached_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - cached_at).total_seconds()


def _fresh_cached_fs_microversion(client: OnshapeClient, state: dict[str, Any]) -> Any:
    """Return the cached Feature Studio microversion only when the element mirror
    was synced recently enough to trust for a mutation; else None (caller
    re-fetches it via GET /elements).

    A stale cached microversion silently pins an OLD Feature Studio definition:
    microversions are immutable snapshots, so the POST succeeds against the old
    content instead of failing. Only a recently-synced mirror is trusted; a
    microversion threaded from a just-finished upload is authoritative regardless
    (it is same-run, not a cache read).
    """
    age = _cache_age_seconds(state)
    if age is None or age > MICROVERSION_CACHE_MAX_AGE_SECONDS:
        return None
    return (_elements_cache(client).get(state["featureStudioId"]) or {}).get("microversionId")


def _save_elements_cache(client: OnshapeClient, by_id: dict[str, dict[str, Any]]) -> None:
    state = client.state
    state["elements"] = [by_id[key] for key in sorted(by_id)]
    state["elementsUpdatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _merge_state_to_disk({
        "elements": state["elements"],
        "elementsUpdatedAt": state["elementsUpdatedAt"],
    })


def _upsert_element_microversion(
    client: OnshapeClient,
    element_id: str,
    microversion: Any,
    element_type: str | None = None,
) -> None:
    """Roll an element's one mutable field (microversionId) forward in the cache.

    The stable id/name/type are preserved; when the table has never been
    refreshed (no entry yet), a minimal {id, elementType, microversionId} entry
    is seeded and its name is filled by the next explicit list refresh."""
    if not microversion:
        return
    by_id = _elements_cache(client)
    row = by_id.get(element_id)
    if row is None:
        row = {"id": element_id}
        by_id[element_id] = row
    row["microversionId"] = microversion
    if element_type and not row.get("elementType"):
        row["elementType"] = element_type
    _save_elements_cache(client, by_id)


def list_document_elements(
    client: OnshapeClient | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """List the workspace's elements, preferring the cached table (zero quota).

    The cached table is the local mirror of the workspace (see _elements_cache):
    id/name/type are stable and refresh is an explicit action; microversionId
    rolls forward from upload/create/status responses. Pass refresh=True to make
    the one live GET /elements and repopulate the cache. The cached read needs
    only the local state file, not credentials.
    """
    if not refresh:
        state = client.state if client is not None else _read_state_file()
        cache = _elements_from_state(state)
        result: dict[str, Any] = {
            "elements": [cache[key] for key in sorted(cache)],
            "source": "cache",
            "cacheTimestamp": state.get("elementsUpdatedAt"),
            "documentId": state.get("documentId"),
            "workspaceId": state.get("workspaceId"),
        }
        if not cache:
            result["note"] = (
                "No cached element table yet. Pass refresh=true to fetch the "
                "live workspace elements (1 API call)."
            )
        return result
    client = client or OnshapeClient()
    state = client.state
    elements = client.request(
        "GET",
        f"/api/documents/d/{state['documentId']}/w/{state['workspaceId']}/elements",
    )
    by_id = {
        item.get("id"): {
            "id": item.get("id"),
            "name": item.get("name"),
            "elementType": item.get("elementType"),
            "microversionId": item.get("microversionId"),
        }
        for item in elements
        if item.get("id")
    }
    _save_elements_cache(client, by_id)
    return {
        "elements": [by_id[key] for key in sorted(by_id)],
        "source": "live",
        "cacheTimestamp": client.state.get("elementsUpdatedAt"),
        "documentId": state["documentId"],
        "workspaceId": state["workspaceId"],
    }


def _feature_specs_summary(specs: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "featureType": item.get("message", {}).get("featureType"),
            "featureTypeName": item.get("message", {}).get("featureTypeName"),
            "parameterCount": len(item.get("message", {}).get("parameters", [])),
        }
        for item in specs.get("featureSpecs", [])
    ]


def _first_language_version(specs: dict[str, Any]) -> Any:
    # Live verification showed the FS GET reports libraryVersion=0 always; the
    # version the content is compiled at appears as languageVersion on each
    # feature spec (e.g. 3029). The deployed runtime version (3044) comes from
    # an eval response's libraryVersion instead — see eval_featurescript.
    for item in specs.get("featureSpecs", []):
        lv = (item.get("message") or {}).get("languageVersion")
        if lv:
            return lv
    return None


def feature_studio_status(client: OnshapeClient | None = None) -> dict[str, Any]:
    client = client or OnshapeClient()
    state = client.state
    path = (
        f"/api/featurestudios/d/{state['documentId']}"
        f"/w/{state['workspaceId']}/e/{state['featureStudioId']}"
    )
    current = client.request("GET", path)
    specs = client.request("GET", path + "/featurespecs", timeout=300)
    summary = _feature_specs_summary(specs)
    language_version = _first_language_version(specs)
    record_observed_version(language_version=language_version, client=client)
    _upsert_element_microversion(
        client,
        state["featureStudioId"],
        current.get("microversionId") or specs.get("sourceMicroversion"),
        element_type="FEATURE_STUDIO",
    )
    return {
        "featureStudioId": state["featureStudioId"],
        "microversionId": current.get("microversionId"),
        "sourceMicroversion": current.get("sourceMicroversion"),
        "libraryVersion": current.get("libraryVersion"),  # always 0; see languageVersion
        "languageVersion": language_version,
        "featureSpecs": summary,
        "expectedFeatureAvailable": any(item["featureType"] == FEATURE_TYPE for item in summary),
    }


def record_observed_version(
    language_version: Any = None,
    library_version: Any = None,
    client: OnshapeClient | None = None,
) -> None:
    """Persist a FeatureScript version seen in an already-costly response.

    Never spend a dedicated call just to learn the server's FeatureScript
    version. Whenever a workflow response carries one, record it here (local,
    zero quota) so `fs_check_version` can report the last observed version for
    free. `languageVersion` is the version the Feature Studio content compiles
    at (from featurespecs); `libraryVersion` is the deployed runtime version
    (from eval). Writes the state file only when a value changes.
    """
    client = client or OnshapeClient()
    state = client.state
    observed = state.setdefault("observedServerVersion", {})
    changed = False
    for key, value in (("languageVersion", language_version), ("libraryVersion", library_version)):
        if value and observed.get(key) != value:
            observed[key] = value
            changed = True
    if changed:
        _merge_state_to_disk({"observedServerVersion": state["observedServerVersion"]})


def _dry_run(requests: list[dict[str, Any]], note: str | None = None) -> dict[str, Any]:
    """Shape the zero-network dry-run result for a mutating operation."""
    return {
        "dryRun": True,
        "estimatedRequests": len(requests),
        "requests": requests,
        "note": note,
    }


def upload_feature_studio(
    client: OnshapeClient | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    client = client or OnshapeClient()
    state = client.state
    source = (ROOT / state.get("featureScriptFile", "branchCableTrophyDisplay.fs")).resolve()
    if ROOT not in source.parents or source.suffix != ".fs":
        raise ValueError("featureScriptFile must resolve to a .fs file inside the project")
    path = (
        f"/api/featurestudios/d/{state['documentId']}"
        f"/w/{state['workspaceId']}/e/{state['featureStudioId']}"
    )
    # The POST body needs the current element's serialization/source microversion
    # and libraryVersion to reject microversion skew, so a live upload is
    # GET (read those) + POST + GET featurespecs (confirm compilation) = 3 calls.
    if dry_run:
        return _dry_run(
            [
                {
                    **client.describe("GET", path),
                    "note": "read libraryVersion/serializationVersion/sourceMicroversion for the POST below",
                },
                {
                    **client.describe("POST", path, {
                        "btType": "BTFeatureStudioContents-2239",
                        "contents": source.read_text(encoding="utf-8"),
                        "libraryVersion": "<from GET>",
                        "serializationVersion": "<from GET>",
                        "sourceMicroversion": "<from GET>",
                        "rejectMicroversionSkew": True,
                    }),
                    "note": "three version fields are filled from the GET response",
                },
                {
                    **client.describe("GET", path + "/featurespecs"),
                    "note": f"confirm the {FEATURE_TYPE} feature spec actually compiled",
                },
            ],
            note=(
                "3 API calls (GET + POST + GET featurespecs). Run scripts/fs_local_check.py "
                "on the source first — a syntactically bad upload still costs quota."
            ),
        )
    current = client.request("GET", path)
    updated = client.request(
        "POST",
        path,
        {
            "btType": "BTFeatureStudioContents-2239",
            "contents": source.read_text(encoding="utf-8"),
            "libraryVersion": current.get("libraryVersion", 0),
            "serializationVersion": current.get("serializationVersion"),
            "sourceMicroversion": current.get("sourceMicroversion"),
            "rejectMicroversionSkew": True,
        },
        timeout=300,
    )
    specs = client.request("GET", path + "/featurespecs", timeout=300)
    summary = _feature_specs_summary(specs)
    if not any(item["featureType"] == FEATURE_TYPE for item in summary):
        raise RuntimeError(f"Expected feature spec {FEATURE_TYPE} was not compiled")
    record_observed_version(language_version=_first_language_version(specs), client=client)
    # The featurespecs response's sourceMicroversion is the Feature Studio's
    # microversion AFTER this upload (the value an instantiate namespace must
    # pin). Cache it so a follow-on instantiate skips its GET /elements.
    feature_studio_microversion = specs.get("sourceMicroversion")
    _upsert_element_microversion(
        client,
        state["featureStudioId"],
        feature_studio_microversion,
        element_type="FEATURE_STUDIO",
    )
    return {
        "featureStudioMicroversion": feature_studio_microversion,
        "featureSpecs": summary,
    }


def create_validation_part_studio(
    name: str = "Cable trophy model validation",
    save_to_project_state: bool = True,
    client: OnshapeClient | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    client = client or OnshapeClient()
    state = client.state
    path = f"/api/partstudios/d/{state['documentId']}/w/{state['workspaceId']}"
    body = {"name": name}
    if dry_run:
        return _dry_run(
            [client.describe("POST", path, body)],
            note="save_to_project_state also rewrites config/onshape-state.json (local, zero quota)",
        )
    created = client.request("POST", path, body)
    if save_to_project_state:
        state["partStudioId"] = created["id"]
        _merge_state_to_disk({"partStudioId": created["id"]})
    # Append the newly created element to the cached table so later
    # instantiate/list calls don't re-discover it.
    by_id = _elements_cache(client)
    by_id[created["id"]] = {
        "id": created["id"],
        "name": created.get("name"),
        "elementType": "PARTSTUDIO",
        "microversionId": created.get("microversionId"),
    }
    _save_elements_cache(client, by_id)
    return {
        "partStudioId": created.get("id"),
        "name": created.get("name"),
        "microversionId": created.get("microversionId"),
        "savedToProjectState": save_to_project_state,
    }


def _instantiate_body(parameters: dict[str, Any], namespace: str) -> dict[str, Any]:
    """The explicit custom-feature POST body, shared by live + dry_run."""
    return {
        "btType": "BTFeatureDefinitionCall-1406",
        "feature": {
            "btType": "BTMFeature-134",
            "featureType": FEATURE_TYPE,
            "name": FEATURE_NAME,
            "namespace": namespace,
            "parameters": parameter_payload(parameters),
            "returnAfterSubfeatures": False,
            "suppressed": False,
        },
    }


def instantiate_feature(
    parameter_set: str = "default",
    overrides: dict[str, Any] | None = None,
    part_studio_id: str | None = None,
    feature_studio_microversion: Any = None,
    client: OnshapeClient | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    client = client or OnshapeClient()
    state = client.state
    did, wid, eid = resolve_part_studio_id(client, part_studio_id)
    elements_path = f"/api/documents/d/{did}/w/{wid}/elements"
    features_path = f"/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/features"
    parameters = merged_parameters(parameter_set, overrides)
    # The namespace pins the Feature Studio's microversion. Prefer an explicit
    # value (threaded from a just-finished upload), then a cached element-table
    # microversion only when the mirror was synced recently; only fall back to a
    # live GET /elements when neither is available.
    namespace_microversion = feature_studio_microversion or _fresh_cached_fs_microversion(client, state)
    needs_elements_get = namespace_microversion is None
    if dry_run:
        requests: list[dict[str, Any]] = []
        if needs_elements_get:
            requests.append({
                **client.describe("GET", elements_path),
                "note": "read the Feature Studio's current microversionId to build the namespace (no cached microversion)",
            })
            placeholder = "<microversionId>"
        else:
            placeholder = str(namespace_microversion)
        requests.append({
            **client.describe("POST", features_path, _instantiate_body(
                parameters, f"e{state['featureStudioId']}::m{placeholder}",
            )),
            "note": (
                "namespace microversion taken from cache/upload (no GET needed)"
                if not needs_elements_get else
                "namespace microversion is filled from the GET above"
            ),
        })
        return _dry_run(
            requests,
            note=(
                "1 API call (POST feature) when the Feature Studio microversion is "
                f"threaded from an upload or from an element mirror synced within the "
                f"last {MICROVERSION_CACHE_MAX_AGE_SECONDS}s; 2 (GET elements + POST "
                "feature) when the mirror is stale or empty."
            ),
        )
    if needs_elements_get:
        elements = client.request("GET", elements_path)
        feature_studio = next(
            (item for item in elements if item.get("id") == state["featureStudioId"]),
            None,
        )
        if feature_studio is None:
            raise RuntimeError("Configured Feature Studio is not present in the workspace")
        namespace_microversion = feature_studio["microversionId"]
    namespace = f"e{state['featureStudioId']}::m{namespace_microversion}"
    response = client.request("POST", features_path, _instantiate_body(parameters, namespace), timeout=900)
    summary = compact_feature_response(response)
    if summary["featureStatus"] != "OK":
        raise RuntimeError(
            f"Feature regeneration failed with status {summary['featureStatus'] or 'unknown'}"
        )
    return summary


def check_model(
    mode: str = "detailed",
    part_studio_id: str | None = None,
    client: OnshapeClient | None = None,
) -> dict[str, Any]:
    if mode not in {"detailed", "simplified"}:
        raise ValueError("mode must be detailed or simplified")
    client = client or OnshapeClient()
    did, wid, eid = resolve_part_studio_id(client, part_studio_id)
    features = client.request(
        "GET", f"/api/partstudios/d/{did}/w/{wid}/e/{eid}/features", timeout=600
    )
    boxes = client.request(
        "GET", f"/api/partstudios/d/{did}/w/{wid}/e/{eid}/boundingboxes", timeout=600
    )
    parts = client.request(
        "GET", f"/api/parts/d/{did}/w/{wid}/e/{eid}", timeout=600
    )
    states = {
        item["key"]: item.get("value", {}).get("message", {}).get("featureStatus")
        for item in features.get("featureStates", [])
    }
    custom_features = [item.get("message", {}) for item in features.get("features", [])]
    custom_ids = [item.get("featureId") for item in custom_features]
    part_names = [part.get("name", "") for part in parts]
    errors: list[str] = []
    if not custom_ids or any(states.get(feature_id) != "OK" for feature_id in custom_ids):
        errors.append(f"custom feature state is not OK: {states}")
    expected_part_count = 132 if mode == "detailed" else 65
    if len(parts) != expected_part_count:
        errors.append(f"expected {expected_part_count} parts, got {len(parts)}")
    for prefix in REQUIRED_PREFIXES:
        if not any(name.startswith(prefix) for name in part_names):
            errors.append(f"missing part name prefix: {prefix}")
    for key, limit in BOUNDS_LIMITS.items():
        value = boxes.get(key)
        exceeds = value is None
        if value is not None:
            exceeds = key.startswith("low") and value < limit
            exceeds = exceeds or (key.startswith("high") and value > limit)
        if exceeds:
            errors.append(f"bounding box {key}={value} exceeds {limit}")
    return {
        "documentId": did,
        "workspaceId": wid,
        "partStudioId": eid,
        "mode": mode,
        "featureStates": states,
        "partCount": len(parts),
        "boundingBoxes": boxes,
        "requiredPrefixes": REQUIRED_PREFIXES,
        "errors": errors,
        "ok": not errors,
    }


def render_preview(
    view: str,
    width: int = 900,
    height: int = 900,
    save: bool = True,
    part_studio_id: str | None = None,
    client: OnshapeClient | None = None,
) -> dict[str, Any]:
    if view not in VIEW_MATRICES:
        raise ValueError(f"Unknown view: {view}")
    if not 64 <= width <= 2000 or not 64 <= height <= 2000:
        raise ValueError("width and height must each be between 64 and 2000 pixels")
    client = client or OnshapeClient()
    did, wid, eid = resolve_part_studio_id(client, part_studio_id)
    payload = client.request(
        "GET",
        f"/api/partstudios/d/{did}/w/{wid}/e/{eid}/shadedviews",
        query={
            "viewMatrix": VIEW_MATRICES[view],
            "outputWidth": width,
            "outputHeight": height,
            "pixelSize": 0,
            "edges": "show",
            "showAllParts": "true",
            "includeSurfaces": "false",
            "includeWires": "false",
            "useAntiAliasing": "true",
        },
        timeout=900,
    )
    images = payload.get("images", [])
    if not images:
        raise RuntimeError(f"No shaded image returned for {view}")
    encoded = "".join(images[0]) if isinstance(images[0], list) else images[0]
    image = base64.b64decode(encoded, validate=True)
    if len(image) < 1000:
        raise RuntimeError(f"Rendered image is unexpectedly small: {len(image)} bytes")
    path = None
    if save:
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        target = PREVIEW_DIR / f"{view}.png"
        target.write_bytes(image)
        path = str(target)
    return {
        "view": view,
        "width": width,
        "height": height,
        "mediaType": "image/png",
        "byteCount": len(image),
        "sha256": hashlib.sha256(image).hexdigest(),
        "savedPath": path,
        "base64": base64.b64encode(image).decode("ascii"),
    }


def render_all_previews(
    width: int = 900,
    height: int = 900,
    part_studio_id: str | None = None,
    client: OnshapeClient | None = None,
) -> list[dict[str, Any]]:
    client = client or OnshapeClient()
    results = []
    for view in VIEW_MATRICES:
        result = render_preview(view, width, height, True, part_studio_id, client)
        result.pop("base64", None)
        results.append(result)
    return results


def eval_featurescript(
    script: str,
    part_studio_id: str | None = None,
    client: OnshapeClient | None = None,
) -> dict[str, Any]:
    """Evaluate a FeatureScript snippet on the live server (1 API call).

    The script must evaluate to a two-argument anonymous function, e.g.
    ``function(context is Context, id is Id) { return 5; }`` — the server calls
    it with (context, id) and returns the result. This is the only way to probe
    real version-specific (e.g. 3044) semantics the vendored 2960 docs do not
    cover, and its notices give detailed compile errors that instantiation does
    not. Callers should gate this behind preflight() — it costs 1 quota call.
    """
    client = client or OnshapeClient()
    state = client.state
    did, wid, eid = resolve_part_studio_id(client, part_studio_id)
    response = client.request(
        "POST",
        f"/api/partstudios/d/{did}/w/{wid}/e/{eid}/featurescript",
        {"script": script},
        timeout=300,
    )
    notices = response.get("notices") or []
    errors = [
        n.get("message", {}).get("message")
        for n in notices
        if n.get("message", {}).get("level") == "ERROR"
    ]
    warnings = [
        n.get("message", {}).get("message")
        for n in notices
        if n.get("message", {}).get("level") == "WARNING"
    ]

    def _flatten(value: Any) -> Any:
        # BTFSValue* envelopes: {"type": ..., "message": {"value": ...}}.
        if isinstance(value, dict) and "message" in value:
            return value.get("message", {}).get("value")
        return value

    # The eval response's libraryVersion is the deployed runtime version
    # (3044 at time of writing) — capture it so fs_check_version reports it free.
    record_observed_version(library_version=response.get("libraryVersion"), client=client)
    return {
        "featureScriptVersion": response.get("libraryVersion"),
        "console": response.get("console"),
        "errors": errors,
        "warnings": warnings,
        "result": _flatten(response.get("result")),
        "raw": response,
    }


# Official annual API-call limits (see onshape_api_error_codes / limits page).
ANNUAL_LIMITS = {
    "enterprise": 10000,   # per full user in company
    "professional": 5000,  # per user in company
    "standard": 2500,      # per user
}
# Per-run API call estimate for run_validation_pipeline, counted from the
# actual operations it performs (upload: 3, create: 1, instantiate: 1 — the
# Feature Studio microversion is threaded from the upload, so no GET /elements,
# check_model: 3, plus 5 render views when render is on).
PIPELINE_ESTIMATE = {True: 13, False: 8}


def api_usage(client: OnshapeClient | None = None) -> dict[str, Any]:
    """Report the API-quota budget: configured annual limit, local ledger
    consumed so far, remaining, and how many pipeline runs fit.

    The ledger is passive (costs zero extra API calls): 2xx/3xx responses count
    toward the annual limit, and each response's X-Rate-Limit-Remaining header
    is captured. Onshape has no public quota-query endpoint.
    """
    client = client or OnshapeClient()
    usage = client._usage or {}
    quota = client.state.get("apiQuota", {}) or {}
    account_type = quota.get("accountType")
    annual_limit: int | None = None
    if quota.get("annualLimit"):
        annual_limit = int(quota["annualLimit"])
    elif account_type in ANNUAL_LIMITS:
        annual_limit = ANNUAL_LIMITS[account_type]
    # alreadyConsumed is the server's real year-to-date usage (read from the
    # Onshape UI's My Account -> Developer), used to seed the passive ledger.
    baseline = int(quota.get("alreadyConsumed", 0) or 0)
    consumed = baseline + int(usage.get("consumed", 0))
    result: dict[str, Any] = {
        "accountType": account_type,
        "annualLimit": annual_limit,
        "baselineConsumed": baseline,
        "consumed": consumed,
        "ledgerConsumed": int(usage.get("consumed", 0)),
        "lastRateLimitRemaining": usage.get("lastRateLimitRemaining"),
        "lastRetryAfter": usage.get("lastRetryAfter"),
        "last402At": usage.get("last402At"),
        "recentCalls": list(reversed((usage.get("calls") or [])[-5:])),
    }
    if annual_limit is None:
        result["configured"] = False
        result["remaining"] = None
        result["estimatedPipelineRuns"] = None
        result["note"] = (
            'No annual quota configured. Add "apiQuota": {"accountType": '
            '"professional"} (enterprise/professional/standard) or '
            '{"annualLimit": N} to config/onshape-state.json to enable the '
            "annual budget. Rate-limit headers are still captured."
        )
    else:
        result["configured"] = True
        result["remaining"] = max(0, annual_limit - consumed)
        result["remainingRatio"] = round(result["remaining"] / annual_limit, 3)
        result["estimatedPipelineRuns"] = {
            "withRender": result["remaining"] // PIPELINE_ESTIMATE[True],
            "withoutRender": result["remaining"] // PIPELINE_ESTIMATE[False],
        }
    return result


def preflight(
    estimate_calls: int,
    label: str,
    client: OnshapeClient | None = None,
) -> dict[str, Any]:
    """Guard any operation estimated at estimate_calls API calls against the
    annual quota budget. canProceed is False only when a budget is configured
    and the remaining calls would be exceeded. Zero network cost."""
    usage = api_usage(client)
    result: dict[str, Any] = {
        "estimateCalls": estimate_calls,
        "label": label,
        "canProceed": True,
        "details": usage,
    }
    if usage.get("configured") and usage["remaining"] < estimate_calls:
        result["canProceed"] = False
        result["blockedReason"] = (
            f"{label} needs ~{estimate_calls} API calls but only "
            f"{usage['remaining']} remain in the configured annual budget "
            f"({usage['annualLimit']}). Raise annualLimit, wait for the annual "
            "reset, or reduce the work."
        )
    return result


def preflight_run(
    parameter_set: str = "default",
    render: bool = True,
    client: OnshapeClient | None = None,
) -> dict[str, Any]:
    """Estimate this pipeline run's API cost and check the annual budget before
    any mutating call is made."""
    estimate = PIPELINE_ESTIMATE[bool(render)]
    result = preflight(
        estimate,
        f"validation pipeline (render={'on' if render else 'off'})",
        client,
    )
    result["estimateDescription"] = (
        f"~{estimate} API calls (render={'on' if render else 'off'})"
    )
    if result.get("blockedReason"):
        result["blockedReason"] += (
            f" render_previews=false reduces the cost to ~{PIPELINE_ESTIMATE[False]}."
        )
    return result


def run_validation_pipeline(
    parameter_set: str = "default",
    render: bool = True,
    client: OnshapeClient | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the mutating upload/create/instantiate/check/render pipeline."""
    if parameter_set not in PARAMETER_PATHS:
        raise ValueError(f"Unknown parameter set: {parameter_set}")
    client = client or OnshapeClient()
    if dry_run:
        # Describe the full sequence without any network request. The
        # instantiate + check + render steps target the Part Studio the create
        # step would return, so their ids are placeholders here.
        return {
            "dryRun": True,
            "estimatedRequests": PIPELINE_ESTIMATE[bool(render)],
            "steps": {
                "upload": upload_feature_studio(client, dry_run=True),
                "createPartStudio": create_validation_part_studio(client=client, dry_run=True),
                "instantiate": instantiate_feature(
                    parameter_set,
                    part_studio_id="<id from create>",
                    feature_studio_microversion="<from upload>",
                    client=client,
                    dry_run=True,
                ),
                "checkModel": "3 GET (features + boundingboxes + parts) on the new Part Studio",
                "render": "5 GET shadedviews (one per view)" if render else "skipped",
            },
        }
    result: dict[str, Any] = {}
    result["upload"] = upload_feature_studio(client)
    result["partStudio"] = create_validation_part_studio(client=client)
    new_id = result["partStudio"]["partStudioId"]
    result["feature"] = instantiate_feature(
        parameter_set,
        part_studio_id=new_id,
        feature_studio_microversion=result["upload"].get("featureStudioMicroversion"),
        client=client,
    )
    mode = "detailed" if parameter_set == "default" else "simplified"
    result["modelCheck"] = check_model(mode, new_id, client)
    if not result["modelCheck"]["ok"]:
        raise RuntimeError("Model validation failed: " + "; ".join(result["modelCheck"]["errors"]))
    if render:
        result["previews"] = render_all_previews(part_studio_id=new_id, client=client)
    return result
