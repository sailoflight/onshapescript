"""Bounded STEP import owned by REST mode — plan first, and say what is missing.

WHAT IS VERIFIED, AND WHAT IS NOT (no live call has been made for this leg):

* The request shape below is taken from the vendored OpenAPI operation
  ``createTranslation`` (``POST /api/v16/translations/d/{did}/w/{wid}``, request
  schema ``BTBTranslationRequestParams``), whose own summary is "Import or upload
  a CAD file into Onshape, and translate the data into parts or assemblies".
  Every body key this module sends is a documented property of that schema; a
  test cross-checks the two so this file cannot invent a field casually.
* The transport is the part that is **not** available here: the import body
  carries a binary ``file`` part, i.e. it is ``multipart/form-data``, while
  :meth:`OnshapeClient.request` sends JSON only. A live import is therefore
  refused with an explicit reason instead of being attempted, and the refusal
  names the two ways to close it.
* The Onshape import API is also where the *receiver's* declarations live
  (``unit``, ``yAxisIsUp``, ``flattenAssemblies``, ``onePartPerDoc``,
  ``allowFaultyParts``, ``locationElementId``/``locationPosition``). That is not
  a coincidence to be smoothed over in a handoff format: these are the fields a
  receiving plane actually declares, so the cross-plane draft in
  ``docs/roadmap/THREE_PLANE_HANDOFF_SCHEMA_DRAFT.md`` maps onto them.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from onshape_rest_api_mode.client import OnshapeClient
from onshape_rest_api_mode.step_export import _STEP_UNITS  # one definition, alongside the export leg

_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_FILENAME = re.compile(r"^[A-Za-z0-9._-]+\.(step|stp)$", re.IGNORECASE)
_IMPORT_FORMATS = {"STEP"}
_SOURCE_SUFFIXES = {".step", ".stp"}

#: Documented in ``BTBTranslationRequestParams`` but deliberately NOT sent by this
#: planner, with the reason. Keeping the list explicit is what stops a later
#: reader from treating silence as support.
UNSENT_FIELDS: dict[str, str] = {
    "uploadId": "no endpoint that produces an uploadId is documented in the vendored spec",
    "encodedFilename": "the vendored schema documents no semantics for it; not sent rather than guessed",
    "importWithinDocument": "meaning depends on Onshape document semantics not verified here",
    "splitAssembliesIntoMultipleDocuments": "changes how many documents the import creates; needs a human decision",
    "createComposite": "composite-curve behavior not verified here",
    "createDrawingIfPossible": "out of scope for a geometry handoff",
    "extractAssemblyHierarchy": "assembly hierarchy policy belongs to the receiving document, not the sender",
    "importAppearances": "appearance import is a rendering concern",
    "importMaterialDensity": "material density is not carried by this handoff",
    "useIGESImportPostProcessing": "IGES-only",
    "makePublic": "permission change; never implicit",
    "ownerId": "ownership/transfer is an operator decision",
    "parentId": "document-structure placement; use locationElementId/locationPosition instead",
    "locationGroupId": "placement inside a group is a document-structure decision, not a handoff field",
    "projectId": "project placement is an operator decision",
    "repointAppElementVersionRefs": "app-element specific",
    "versionString": "version import is a separate operator workflow",
}

#: Documented in the same schema object but listed under ``x-BTVisibility-properties``
#: as INTERNAL. Kept separate from :data:`UNSENT_FIELDS` so the two claims stay
#: distinct: one says "public field, deliberately not sent", the other says "not part
#: of the public contract at all".
INTERNAL_FIELDS: dict[str, str] = {
    "preserveSourceIds": "INTERNAL visibility in the vendored schema",
    "documentId": "INTERNAL; the target document is in the request path",
    "upgradeFeatureScriptVersion": "INTERNAL visibility in the vendored schema",
    "versionDescription": "INTERNAL visibility in the vendored schema",
    "versionId": "INTERNAL visibility in the vendored schema",
    "versionName": "INTERNAL visibility in the vendored schema",
}


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{label} must be a nonempty opaque identifier")
    return value


def build_step_import_body(
    *,
    filename: str,
    unit: str = "MILLIMETER",
    format_name: str = "STEP",
    store_in_document: bool = True,
    translate: bool = True,
    y_axis_is_up: bool = False,
    flatten_assemblies: bool = False,
    one_part_per_doc: bool = False,
    allow_faulty_parts: bool = False,
    join_adjacent_surfaces: bool = False,
    notify_user: bool = False,
    location_element_id: str | None = None,
    location_position: int | None = None,
) -> dict[str, Any]:
    """Build the documented import body. Every key is a schema property."""
    if not isinstance(filename, str) or not _FILENAME.fullmatch(filename):
        raise ValueError("filename must be a simple .step or .stp filename")
    if format_name not in _IMPORT_FORMATS:
        raise ValueError(f"format_name must be one of {sorted(_IMPORT_FORMATS)}")
    if unit not in _STEP_UNITS:
        raise ValueError(f"unit must be one of {sorted(_STEP_UNITS)}")
    body: dict[str, Any] = {
        "allowFaultyParts": bool(allow_faulty_parts),
        "flattenAssemblies": bool(flatten_assemblies),
        "formatName": format_name,
        "joinAdjacentSurfaces": bool(join_adjacent_surfaces),
        "notifyUser": bool(notify_user),
        "onePartPerDoc": bool(one_part_per_doc),
        "storeInDocument": bool(store_in_document),
        "translate": bool(translate),
        "unit": unit,
        "yAxisIsUp": bool(y_axis_is_up),
    }
    if location_element_id is not None:
        body["locationElementId"] = _identifier(location_element_id, "location_element_id")
    if location_position is not None:
        if not isinstance(location_position, int) or location_position < 0:
            raise ValueError("location_position must be a non-negative integer")
        body["locationPosition"] = location_position
    return body


def _source_facts(source_path: str | Path) -> dict[str, Any]:
    """Describe the local STEP this plan would upload: size and digest, nothing more.

    The digest is deliberately reported as download integrity rather than as an
    identity: two real exports of the same geometry were measured to differ by 34
    bytes, all of it in the STEP header's ``/* name */`` GUID and ``/* time_stamp */``.
    """
    path = Path(source_path)
    if not path.is_file():
        raise FileNotFoundError(f"source_path is not a file: {path}")
    if path.suffix.lower() not in _SOURCE_SUFFIXES:
        raise ValueError("source_path must be a .step or .stp file")
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            byte_count += len(chunk)
    return {
        "path": str(path),
        "byteCount": byte_count,
        "sha256": digest.hexdigest(),
        "sha256Stable": False,
        "sha256Note": "STEP carries a GUID and a timestamp in its header; the digest is download integrity, not content identity",
    }


def build_step_import_plan(
    *,
    document_id: str,
    workspace_id: str,
    filename: str,
    unit: str = "MILLIMETER",
    format_name: str = "STEP",
    store_in_document: bool = True,
    y_axis_is_up: bool = False,
    flatten_assemblies: bool = False,
    one_part_per_doc: bool = False,
    allow_faulty_parts: bool = False,
    join_adjacent_surfaces: bool = False,
    location_element_id: str | None = None,
    location_position: int | None = None,
    max_polls: int = 3,
    media_type: str = "model/step",
    source_path: str | Path | None = None,
    client: OnshapeClient | None = None,
) -> dict[str, Any]:
    """Describe the exact import without sending anything."""
    did = _identifier(document_id, "document_id")
    wid = _identifier(workspace_id, "workspace_id")
    if not isinstance(max_polls, int) or not 1 <= max_polls <= 5:
        raise ValueError("max_polls must be from 1 through 5")
    if not isinstance(media_type, str) or "/" not in media_type:
        raise ValueError("media_type must look like a media type")
    body = build_step_import_body(
        filename=filename,
        unit=unit,
        format_name=format_name,
        store_in_document=store_in_document,
        y_axis_is_up=y_axis_is_up,
        flatten_assemblies=flatten_assemblies,
        one_part_per_doc=one_part_per_doc,
        allow_faulty_parts=allow_faulty_parts,
        join_adjacent_surfaces=join_adjacent_surfaces,
        location_element_id=location_element_id,
        location_position=location_position,
    )
    client = client or OnshapeClient(require_credentials=False)
    described = client.describe("POST", f"/api/v16/translations/d/{did}/w/{wid}")
    parts: list[dict[str, Any]] = [
        {"name": "file", "kind": "binary", "filename": filename, "contentType": media_type},
    ]
    parts.extend(
        {"name": key, "kind": "text", "value": value} for key, value in sorted(body.items())
    )

    requests: list[dict[str, Any]] = [
        {
            **described,
            "contentType": "multipart/form-data",
            "bodyParts": parts,
            "body": body,
            "maxExecutions": 1,
            "implicitRetry": False,
            "note": "the binary `file` part is why this cannot be sent as JSON",
        },
        {
            **client.describe("GET", "/api/v16/translations/<translationId from POST>"),
            "maxExecutions": max_polls,
            "implicitRetry": False,
        },
        {
            **client.describe("GET", f"/api/v16/documents/d/{did}/w/{wid}/elements"),
            "maxExecutions": 1,
            "implicitRetry": False,
            "condition": "translation requestState == DONE; compares the element list with the pre-import list",
            "note": "landing proof: a translation can report DONE without a usable part studio",
        },
    ]
    return {
        "dryRun": True,
        "operation": "step-import",
        "transport": "multipart/form-data",
        "liveExecution": {
            "available": False,
            "reason": "multipart_transport_unavailable",
            "detail": "onshape_rest_api_mode.client sends JSON bodies only, and the import body carries a binary file part",
            "options": [
                "add a bounded multipart transport to onshape_rest_api_mode.client (new capability, needs its own tests)",
                "perform the import through the browser leg (0 REST quota, but its selectors are unverified)",
            ],
        },
        "estimatedRequests": 1 + max_polls + 1,
        "maxRequests": 1 + max_polls + 1,
        "requests": requests,
        "pollPolicy": {
            "maxPolls": max_polls,
            "states": ["ACTIVE", "DONE", "FAILED"],
            "getRetry": False,
            "repeatPost": False,
        },
        "declarations": {
            "unit": unit,
            "declaredBy": "receiver",
            "yAxisIsUp": bool(y_axis_is_up),
            "flattenAssemblies": bool(flatten_assemblies),
            "onePartPerDoc": bool(one_part_per_doc),
            "allowFaultyParts": bool(allow_faulty_parts),
            "joinAdjacentSurfaces": bool(join_adjacent_surfaces),
            "note": "these are the receiving plane's declarations, not the sender's; the sender still owes a receipt of what it used",
        },
        "artifactContract": {
            "mediaType": media_type,
            "filename": filename,
            "source": _source_facts(source_path) if source_path is not None else None,
            "landingProof": "element list before/after plus the translation state",
            "failureHonesty": "a translation that is not DONE is reported as not imported; never as an empty success",
        },
        "unverifiedFields": dict(UNSENT_FIELDS),
    }


def import_step(
    *,
    document_id: str,
    workspace_id: str,
    filename: str,
    unit: str = "MILLIMETER",
    format_name: str = "STEP",
    store_in_document: bool = True,
    y_axis_is_up: bool = False,
    flatten_assemblies: bool = False,
    one_part_per_doc: bool = False,
    allow_faulty_parts: bool = False,
    join_adjacent_surfaces: bool = False,
    location_element_id: str | None = None,
    location_position: int | None = None,
    max_polls: int = 3,
    media_type: str = "model/step",
    source_path: str | Path | None = None,
    dry_run: bool = True,
    client: OnshapeClient | None = None,
) -> dict[str, Any]:
    """Plan (default) or attempt the import.

    ``dry_run=False`` does not send anything today: it returns the structured
    refusal that says which transport is missing, because pretending to try
    would be the one outcome nobody can audit.
    """
    plan = build_step_import_plan(
        document_id=document_id,
        workspace_id=workspace_id,
        filename=filename,
        unit=unit,
        format_name=format_name,
        store_in_document=store_in_document,
        y_axis_is_up=y_axis_is_up,
        flatten_assemblies=flatten_assemblies,
        one_part_per_doc=one_part_per_doc,
        allow_faulty_parts=allow_faulty_parts,
        join_adjacent_surfaces=join_adjacent_surfaces,
        location_element_id=location_element_id,
        location_position=location_position,
        max_polls=max_polls,
        media_type=media_type,
        source_path=source_path,
        client=client,
    )
    if dry_run:
        return plan
    return {
        "imported": False,
        "requestsConsumed": 0,
        "reason": plan["liveExecution"]["reason"],
        "detail": plan["liveExecution"]["detail"],
        "requiredTransport": plan["transport"],
        "plan": plan["requests"],
        "unverifiedFields": plan["unverifiedFields"],
    }
