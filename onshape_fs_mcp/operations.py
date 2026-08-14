"""Reusable Onshape operations shared by scripts and the MCP server."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

from onshape_fs_mcp.client import (
    DEFAULT_PARAMETERS_PATH,
    PARAMETERS_DIR,
    PREVIEW_DIR,
    ROOT,
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
    """Resolve a usable Part Studio, recovering from stale saved element IDs."""
    state = client.state
    did, wid = state["documentId"], state["workspaceId"]
    if part_studio_id:
        return did, wid, part_studio_id
    configured = state.get("partStudioId")
    elements = client.request("GET", f"/api/documents/d/{did}/w/{wid}/elements")
    part_studios = [item for item in elements if item.get("elementType") == "PARTSTUDIO"]
    if not part_studios:
        raise RuntimeError("The configured workspace contains no Part Studio")
    candidates: list[tuple[str, int]] = []
    for item in part_studios:
        eid = item["id"]
        parts = client.request("GET", f"/api/parts/d/{did}/w/{wid}/e/{eid}", timeout=600)
        candidates.append((eid, len(parts)))
    candidate_ids = {eid for eid, _ in candidates}
    if configured in candidate_ids:
        return did, wid, configured
    expected_counts = {132, 65}
    validated = [eid for eid, part_count in candidates if part_count in expected_counts]
    if len(validated) == 1:
        return did, wid, validated[0]
    if len(part_studios) == 1:
        return did, wid, part_studios[0]["id"]
    available = ", ".join(
        f"{item.get('name', 'unnamed')} ({item.get('id')})" for item in part_studios
    )
    raise RuntimeError(
        "Configured partStudioId is stale and no unique validated model could be selected; "
        f"pass part_studio_id explicitly. Available: {available}"
    )


def list_document_elements(client: OnshapeClient | None = None) -> list[dict[str, Any]]:
    client = client or OnshapeClient()
    state = client.state
    elements = client.request(
        "GET",
        f"/api/documents/d/{state['documentId']}/w/{state['workspaceId']}/elements",
    )
    return [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "elementType": item.get("elementType"),
            "microversionId": item.get("microversionId"),
        }
        for item in elements
    ]


def feature_studio_status(client: OnshapeClient | None = None) -> dict[str, Any]:
    client = client or OnshapeClient()
    state = client.state
    path = (
        f"/api/featurestudios/d/{state['documentId']}"
        f"/w/{state['workspaceId']}/e/{state['featureStudioId']}"
    )
    current = client.request("GET", path)
    specs = client.request("GET", path + "/featurespecs", timeout=300)
    summary = [
        {
            "featureType": item.get("message", {}).get("featureType"),
            "featureTypeName": item.get("message", {}).get("featureTypeName"),
            "parameterCount": len(item.get("message", {}).get("parameters", [])),
        }
        for item in specs.get("featureSpecs", [])
    ]
    # Live verification showed the FS GET reports libraryVersion=0 always; the
    # real FeatureScript version appears as languageVersion on the feature
    # specs (e.g. 3029). Read it from there.
    language_version: Any = None
    for item in specs.get("featureSpecs", []):
        lv = (item.get("message") or {}).get("languageVersion")
        if lv:
            language_version = lv
            break
    return {
        "featureStudioId": state["featureStudioId"],
        "microversionId": current.get("microversionId"),
        "sourceMicroversion": current.get("sourceMicroversion"),
        "libraryVersion": current.get("libraryVersion"),  # always 0; see languageVersion
        "languageVersion": language_version,
        "featureSpecs": summary,
        "expectedFeatureAvailable": any(item["featureType"] == FEATURE_TYPE for item in summary),
    }


def upload_feature_studio(client: OnshapeClient | None = None) -> dict[str, Any]:
    client = client or OnshapeClient()
    state = client.state
    source = (ROOT / state.get("featureScriptFile", "branchCableTrophyDisplay.fs")).resolve()
    if ROOT not in source.parents or source.suffix != ".fs":
        raise ValueError("featureScriptFile must resolve to a .fs file inside the project")
    path = (
        f"/api/featurestudios/d/{state['documentId']}"
        f"/w/{state['workspaceId']}/e/{state['featureStudioId']}"
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
    status = feature_studio_status(client)
    if not status["expectedFeatureAvailable"]:
        raise RuntimeError(f"Expected feature spec {FEATURE_TYPE} was not compiled")
    return {
        "sourceMicroversion": updated.get("sourceMicroversion"),
        "featureSpecs": status["featureSpecs"],
    }


def create_validation_part_studio(
    name: str = "Cable trophy model validation",
    save_to_project_state: bool = True,
    client: OnshapeClient | None = None,
) -> dict[str, Any]:
    client = client or OnshapeClient()
    state = client.state
    created = client.request(
        "POST",
        f"/api/partstudios/d/{state['documentId']}/w/{state['workspaceId']}",
        {"name": name},
    )
    if save_to_project_state:
        state["partStudioId"] = created["id"]
        save_state(state)
    return {
        "partStudioId": created.get("id"),
        "name": created.get("name"),
        "microversionId": created.get("microversionId"),
        "savedToProjectState": save_to_project_state,
    }


def instantiate_feature(
    parameter_set: str = "default",
    overrides: dict[str, Any] | None = None,
    part_studio_id: str | None = None,
    client: OnshapeClient | None = None,
) -> dict[str, Any]:
    client = client or OnshapeClient()
    state = client.state
    did, wid, eid = resolve_part_studio_id(client, part_studio_id)
    elements = client.request("GET", f"/api/documents/d/{did}/w/{wid}/elements")
    feature_studio = next(
        (item for item in elements if item.get("id") == state["featureStudioId"]),
        None,
    )
    if feature_studio is None:
        raise RuntimeError("Configured Feature Studio is not present in the workspace")
    namespace = f"e{state['featureStudioId']}::m{feature_studio['microversionId']}"
    parameters = merged_parameters(parameter_set, overrides)
    body = {
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
    response = client.request(
        "POST",
        f"/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/features",
        body,
        timeout=900,
    )
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
# actual operations it performs (upload: 4, create: 1, instantiate: 2,
# check_model: 3, plus 5 render views when render is on).
PIPELINE_ESTIMATE = {True: 15, False: 10}


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
            f" render_previews=false halves the cost to ~{PIPELINE_ESTIMATE[False]}."
        )
    return result


def run_validation_pipeline(
    parameter_set: str = "default",
    render: bool = True,
    client: OnshapeClient | None = None,
) -> dict[str, Any]:
    """Run the mutating upload/create/instantiate/check/render pipeline."""
    if parameter_set not in PARAMETER_PATHS:
        raise ValueError(f"Unknown parameter set: {parameter_set}")
    client = client or OnshapeClient()
    result: dict[str, Any] = {}
    result["upload"] = upload_feature_studio(client)
    result["partStudio"] = create_validation_part_studio(client=client)
    new_id = result["partStudio"]["partStudioId"]
    result["feature"] = instantiate_feature(parameter_set, part_studio_id=new_id, client=client)
    mode = "detailed" if parameter_set == "default" else "simplified"
    result["modelCheck"] = check_model(mode, new_id, client)
    if not result["modelCheck"]["ok"]:
        raise RuntimeError("Model validation failed: " + "; ".join(result["modelCheck"]["errors"]))
    if render:
        result["previews"] = render_all_previews(part_studio_id=new_id, client=client)
    return result
