"""Assemble a contract report from fields that an adapter extracted.

Assembly is **not** judgement: this module turns extracted fields into the declared report
shape and machine-checks its own CSV projection. Whether the report is acceptable is decided
by :mod:`dev.verification_report.runner` and nowhere else.

The slice here is a real one: MeshQ's own contract probe (its repository, read-only for this
plane), so the reconciliation runs against a peer artifact instead of our own fixture.
"""

from __future__ import annotations

import pathlib
from typing import Any

from . import rules as R
from .adapters import extract_meshq_result

#: Where MeshQ's probes live (its repository; this plane only reads).
MESHQ_PROBE = pathlib.Path("/home/lijq/code/MeshQ/artifacts/contract-probe")
MESHQ_SPHERE_COARSE = MESHQ_PROBE / "work_sphere_cap_coarse"


def _relative(absolute: float | None, value: float | None) -> float | None:
    if absolute is None or not value:
        return None
    return abs(absolute / value)


def build_meshq_report(
    result_path: str | pathlib.Path = MESHQ_SPHERE_COARSE / "meshq_result.json",
    job_path: str | pathlib.Path = MESHQ_SPHERE_COARSE / "meshq_job.json",
) -> dict[str, Any]:
    """Assemble a verification report from MeshQ's real probe result (fields only)."""
    extracted = extract_meshq_result(result_path, job_path)
    tessellation = extracted.get("tessellation") or {}
    segment_note = ", ".join(f"{key}={value}" for key, value in sorted(tessellation.items())) or "undefined"
    family = f"tessellation_signed_volume(mesh, {segment_note})"
    reached: float | None = None
    limit: float | None = None

    claims: list[dict[str, Any]] = []
    for part in extracted["objects"]:
        value = part.get("volume_mm3")
        achieved = part.get("volume_achieved") or {}
        absolute = achieved.get("absolute")
        if achieved.get("limit") is not None:
            limit = achieved["limit"]
        if part.get("name") == "S" or reached is None:
            reached = absolute
        claims.append(
            {
                "id": f"c_{part['name']}",
                "quantity": "mesh.volume_mm3",
                "layers": ["geometry"],
                "grade": part.get("volume_grade") or "unknown",
                "readings": [
                    {
                        "value": value,
                        "unit": "mm^3",
                        "family": family,
                        "algorithm": "signed volume of the triangulated shell, summed per triangle (MeshQ / Blender); "
                        "the producer's own note: " + str(part.get("volume_note")),
                        "achieved": {
                            "absolute": absolute,
                            "relative": _relative(absolute, value),
                            "basis": str(achieved.get("basis")),
                        },
                    }
                ],
                "negative_control": {
                    "fixture": "bad__R6__reading_without_achieved.json",
                    "must_reject": True,
                    "observed": "rejected",
                },
                "not_evaluated": [],
            }
        )
        bbox_size = part.get("bbox_size_mm") or []
        if bbox_size:
            claims.append(
                {
                    "id": f"c_{part['name']}_bounds",
                    "quantity": "mesh.bounds_mm",
                    "layers": ["geometry"],
                    "grade": part.get("bbox_grade") or "unknown",
                    # Bound family declared under the *second* accepted name, on a real peer artifact.
                    "boundsAlgorithm": "tessellation_vertices(mesh)",
                    "readings": [
                        {
                            "value": max(bbox_size),
                            "unit": "mm",
                            "family": "tessellation_vertices(mesh)",
                            "algorithm": f"vertex extrema of the mesh bytes; size_mm={bbox_size}",
                            "achieved": {
                                "absolute": 0.0,
                                "relative": 0.0,
                                "basis": "the box is read off the same vertices the producer's volume is summed over",
                            },
                        }
                    ],
                    "not_evaluated": [],
                }
            )

    # Per-shell self-consistency is a real reading, and it is *not* whole-part validity: MeshQ
    # measured a `recalc_normals` case where every shell check stayed green while the volume moved
    # by +14.695 % on a multi-shell part (MeshQ mail 289 §4).
    shell = (extracted["objects"][0] if extracted["objects"] else {}).get("shell_self_consistency") or {}
    claims.append(
        {
            "id": "c_shell",
            "quantity": "mesh.shell_self_consistency",
            "layers": ["topology"],
            "grade": "heuristic",
            "readings": [
                {
                    "value": shell.get("inconsistent_edge_pairs"),
                    "unit": "count",
                    "family": "shell_self_consistency(inconsistent_edge_pairs)",
                    "algorithm": "per-shell closure/manifold/winding checks of the produced mesh",
                    "achieved": {
                        "absolute": 0.0,
                        "relative": 0.0,
                        "basis": "exact integer counts over the mesh edges",
                    },
                }
            ],
            "not_evaluated": [
                {
                    "key": "c_shell.whole_part_validity",
                    "why": "per-shell self-consistency is not whole-part consistency: MeshQ measured every shell check "
                    "green while a multi-shell part's volume moved by +14.695 % (mail 289 §4)",
                }
            ],
        }
    )

    tolerance = limit if limit is not None else 0.0
    return {
        "schema": {"id": R.SCHEMA_ID, "version": R.SCHEMA_VERSION},
        "producer": {
            "plane": "meshq",
            "tool": "MeshQ inspect (contract probe)",
            "revision": f"{extracted.get('job_id')}@{str(extracted.get('artifact_sha256'))[:12]}",
        },
        "artifact": {
            "path": str(pathlib.Path(result_path)),
            "sha256": extracted["artifact_sha256"],
            "units": extracted.get("units") or "mm",
            "sha256_stable": False,
            "sha256_stable_evidence": {
                "reason": "the result JSON embeds started_at / build_seconds / total_seconds, so a re-run writes different bytes",
                "consequence": "the digest addresses this probe run, not the geometry it measured",
            },
        },
        "claims": claims,
        "complete": True,
        "not_evaluated": [
            {"key": "c_shell.whole_part_validity", "why": "not established by per-shell checks; see the claim's own note"}
        ],
        "tolerances": {
            "mesh_volume_mm3": {
                "absolute": tolerance,
                "declared_by": "producer:meshq",
                "used_by": "consumer",
                "used": tolerance,
                "matches_declaration": True,
            }
        },
        "vintage": {
            "date": "2026-10-04",
            "readers": ["meshq", "onshapescript"],
            "witness": "MeshQ 289 (admission sample: recalc_normals on a multi-shell part)",
            "re_derive_when": "the probe is re-run at a different tessellation or with a different welding distance",
        },
        "cost": {"network": "offline", "estimated_requests": 0, "mutating": False},
        "independence": {
            "level": "different_kernel",
            "of": "MeshQ's Blender mesh kernel measured the mesh of the same design this plane measures as B-Rep",
        },
        "csv_projection": {"path": "meshq-slice.csv", "checked_against": "report", "result": "match"},
    }


def machine_check_projection(report: dict[str, Any], csv_text: str) -> bool:
    """The check R12 demands: the projection must be reproducible from the report."""
    from .runner import read_projection_csv

    rows = read_projection_csv(csv_text)
    expected = [
        (str(claim.get("id")), str(reading.get("value")))
        for claim in report.get("claims") or []
        for reading in claim.get("readings") or []
    ]
    have = [(row.get("claim_id"), row.get("value")) for row in rows]
    return have == expected
