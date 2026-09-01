"""Bounded asynchronous STEP export owned by REST mode.

The live operation is explicit and resumable. It never retries a GET implicitly,
never repeats the export POST, and stores the downloaded STEP in module-owned
staging before shared FDM code sees it.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from onshape_rest_api_mode.client import OnshapeClient
from onshape_rest_api_mode.fdm_adapter import step_artifact_from_rest_export


OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs" / "step_exports"
_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_STEP_VERSIONS = {"AP242", "AP203", "AP214"}
_STEP_UNITS = {"METER", "CENTIMETER", "MILLIMETER", "INCH", "FOOT", "YARD", "UNKNOWN"}


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{label} must be a nonempty opaque identifier")
    return value


def build_step_export_body(
    *,
    destination_name: str = "model.step",
    exclude_hidden_entities: bool = True,
    step_version: str = "AP242",
    step_unit: str = "MILLIMETER",
) -> dict[str, Any]:
    if not isinstance(destination_name, str) or not re.fullmatch(r"[A-Za-z0-9._-]+\.step", destination_name):
        raise ValueError("destination_name must be a simple .step filename")
    if step_version not in _STEP_VERSIONS:
        raise ValueError(f"step_version must be one of {sorted(_STEP_VERSIONS)}")
    if step_unit not in _STEP_UNITS:
        raise ValueError(f"step_unit must be one of {sorted(_STEP_UNITS)}")
    return {
        "destinationName": destination_name,
        "excludeHiddenEntities": bool(exclude_hidden_entities),
        "grouping": True,
        "includeExportIds": False,
        "isYAxisUp": False,
        "notifyUser": False,
        "stepUnit": step_unit,
        "stepVersionString": step_version,
        "storeInDocument": False,
        "triggerAutoDownload": False,
    }


def build_step_export_plan(
    *,
    document_id: str,
    wv: str,
    wvid: str,
    element_id: str,
    translation_id: str | None = None,
    max_polls: int = 3,
    destination_name: str = "model.step",
    exclude_hidden_entities: bool = True,
    step_version: str = "AP242",
    step_unit: str = "MILLIMETER",
    client: OnshapeClient | None = None,
) -> dict[str, Any]:
    did = _identifier(document_id, "document_id")
    if wv not in {"w", "v"}:
        raise ValueError("wv must be w or v")
    resolved_wvid = _identifier(wvid, "wvid")
    eid = _identifier(element_id, "element_id")
    tid = _identifier(translation_id, "translation_id") if translation_id else None
    if not isinstance(max_polls, int) or not 1 <= max_polls <= 5:
        raise ValueError("max_polls must be from 1 through 5")
    client = client or OnshapeClient(require_credentials=False)
    body = build_step_export_body(
        destination_name=destination_name,
        exclude_hidden_entities=exclude_hidden_entities,
        step_version=step_version,
        step_unit=step_unit,
    )
    requests = []
    if tid is None:
        requests.append(client.describe(
            "POST",
            f"/api/v16/partstudios/d/{did}/{wv}/{resolved_wvid}/e/{eid}/export/step",
            body,
        ))
    requests.append({
        **client.describe("GET", f"/api/v16/translations/{tid or '<translationId from POST>'}"),
        "maxExecutions": max_polls,
        "implicitRetry": False,
    })
    requests.append({
        **client.describe(
            "GET",
            f"/api/v16/documents/d/{did}/externaldata/<resultExternalDataId from DONE translation>",
        ),
        "maxExecutions": 1,
        "implicitRetry": False,
        "condition": "requestState == DONE and exactly one resultExternalDataId",
    })
    return {
        "dryRun": True,
        "operation": "part-studio-step-export",
        "resume": tid is not None,
        "translationId": tid,
        "estimatedRequests": (0 if tid else 1) + max_polls + 1,
        "requests": requests,
        "pollPolicy": {
            "maxPolls": max_polls,
            "states": ["ACTIVE", "DONE", "FAILED"],
            "getRetry": False,
            "repeatPost": False,
        },
        "artifactContract": {
            "mediaType": "model/step",
            "units": "mm" if step_unit == "MILLIMETER" else "unknown",
            "stagingOwner": "onshape_rest_api_mode",
        },
    }


def export_step(
    *,
    document_id: str,
    wv: str,
    wvid: str,
    element_id: str,
    translation_id: str | None = None,
    max_polls: int = 3,
    poll_interval_seconds: int = 10,
    destination_name: str = "model.step",
    exclude_hidden_entities: bool = True,
    step_version: str = "AP242",
    step_unit: str = "MILLIMETER",
    dry_run: bool = False,
    client: OnshapeClient | None = None,
    output_root: Path = OUTPUT_ROOT,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if not isinstance(poll_interval_seconds, int) or not 5 <= poll_interval_seconds <= 120:
        raise ValueError("poll_interval_seconds must be from 5 through 120")
    if dry_run:
        return build_step_export_plan(
            document_id=document_id,
            wv=wv,
            wvid=wvid,
            element_id=element_id,
            translation_id=translation_id,
            max_polls=max_polls,
            destination_name=destination_name,
            exclude_hidden_entities=exclude_hidden_entities,
            step_version=step_version,
            step_unit=step_unit,
            client=client,
        )

    plan = build_step_export_plan(
        document_id=document_id,
        wv=wv,
        wvid=wvid,
        element_id=element_id,
        translation_id=translation_id,
        max_polls=max_polls,
        destination_name=destination_name,
        exclude_hidden_entities=exclude_hidden_entities,
        step_version=step_version,
        step_unit=step_unit,
        client=client or OnshapeClient(require_credentials=False),
    )
    client = client or OnshapeClient()
    did = document_id
    tid = translation_id
    request_count = 0
    state: dict[str, Any] = {}
    if tid is None:
        state = client.request(
            "POST",
            f"/api/v16/partstudios/d/{did}/{wv}/{wvid}/e/{element_id}/export/step",
            build_step_export_body(
                destination_name=destination_name,
                exclude_hidden_entities=exclude_hidden_entities,
                step_version=step_version,
                step_unit=step_unit,
            ),
        )
        request_count += 1
        if not isinstance(state, dict):
            raise ValueError("STEP export POST returned a non-object response")
        tid = _identifier(str(state.get("id", "")), "translation response id")

    for poll_index in range(max_polls):
        if state.get("requestState") in {"DONE", "FAILED"}:
            break
        sleeper(poll_interval_seconds)
        state = client.request(
            "GET",
            f"/api/v16/translations/{tid}",
            retry_get=False,
        )
        request_count += 1
        if not isinstance(state, dict):
            raise ValueError("translation poll returned a non-object response")

    request_state = state.get("requestState")
    if request_state == "FAILED":
        raise RuntimeError(f"STEP translation failed: {state.get('failureReason') or 'unknown reason'}")
    if request_state != "DONE":
        return {
            "exported": False,
            "resumable": True,
            "translationId": tid,
            "requestState": request_state or "ACTIVE",
            "requestsConsumed": request_count,
            "reason": "translation did not reach DONE within the explicit poll budget",
        }

    external_ids = state.get("resultExternalDataIds") or []
    if not isinstance(external_ids, list) or len(external_ids) != 1:
        raise ValueError("DONE translation must contain exactly one resultExternalDataId")
    external_id = _identifier(str(external_ids[0]), "resultExternalDataId")
    result_document_id = _identifier(str(state.get("documentId") or did), "result document id")
    payload = client.request(
        "GET",
        f"/api/v16/documents/d/{result_document_id}/externaldata/{external_id}",
        retry_get=False,
    )
    request_count += 1
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("STEP download returned no binary payload")

    destination_dir = output_root.resolve() / tid
    if destination_dir.exists():
        raise ValueError("STEP export staging destination already exists")
    destination_dir.mkdir(parents=True)
    destination = destination_dir / destination_name
    destination.write_bytes(payload)
    artifact = step_artifact_from_rest_export(
        destination,
        document_id=did,
        wv=wv,
        wvid=wvid,
        element_id=element_id,
        translation_id=tid,
        units="mm" if step_unit == "MILLIMETER" else "from-step",
    )
    step_payload = artifact.as_dict()
    step_manifest = {
        "schemaVersion": 1,
        "artifactType": "canonical-step",
        "translationId": tid,
        "artifact": {
            **step_payload,
            "path": destination_name,
            "byteCount": destination.stat().st_size,
        },
    }
    manifest_path = destination_dir / "step-manifest.json"
    manifest_path.write_text(
        json.dumps(step_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "exported": True,
        "resumable": False,
        "translationId": tid,
        "requestState": request_state,
        "requestsConsumed": request_count,
        "step": step_payload,
        "stepManifestPath": str(manifest_path),
        "planEstimate": plan["estimatedRequests"],
    }
