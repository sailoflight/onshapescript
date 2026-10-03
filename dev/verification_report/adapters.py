"""Extraction-only adapters: pull fields out of an artifact, never judge it.

The three planes agreed (coordinator mail 273, 2026-10-04) that **the runner is the only
authority**: each plane's adapter may only extract fields, because an adapter that judges
would give every plane its own set of criteria. The guard test asserts that an extracted
mapping contains none of :data:`JUDGEMENT_KEYS`.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

#: Keys an adapter must never produce: judgement belongs to the runner.
JUDGEMENT_KEYS = frozenset({"ok", "verdict", "pass", "grade", "refusals", "refused", "compliant"})

#: This plane's real 70-piece handoff, dropped by the three-plane session (volatile).
REAL_MANIFEST = pathlib.Path("/tmp/three-plane-drop/onshapescript-70piece-tessellation/manifest.json")

#: MeshQ's real contract probes (its repository, read-only for this plane).
MESHQ_PROBE = pathlib.Path("/home/lijq/code/MeshQ/artifacts/contract-probe")


def extract_onshapescript_manifest(path: str | pathlib.Path) -> dict[str, Any]:
    """Extract fields from this plane's handoff manifest. Fields only, no verdict."""
    data: Any = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest top level is not an object")
    produced_by = data.get("produced_by") if isinstance(data.get("produced_by"), dict) else {}
    totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    return {
        "schema": data.get("schema"),
        "producer_plane": produced_by.get("plane"),
        "producer_identity": produced_by.get("identity"),
        "tool": produced_by.get("tool"),
        "produced_at": produced_by.get("at"),
        "units": data.get("units"),
        "source_kind": source.get("kind"),
        "piece_count": totals.get("pieces"),
        "contributing_pieces": totals.get("contributingPieces"),
        "triangle_count": totals.get("triangleCount"),
        "area_mm2": totals.get("areaMm2"),
    }


def _sha256(path: pathlib.Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_meshq_result(result_path: str | pathlib.Path, job_path: str | pathlib.Path | None = None) -> dict[str, Any]:
    """Extract fields from MeshQ's real probe result. **Fields only, no verdict.**

    MeshQ's raw result is verdict-shaped by design (`inspection.verdicts.<name>.pass`), which is
    that tool's own contract. This adapter deliberately does **not** carry those keys: the
    verification report publishes a producer's *readings and grades*, and the judgement belongs to
    the runner. The number of verdicts is carried as a count so nothing is silently hidden.
    """
    result = pathlib.Path(result_path)
    data: Any = json.loads(result.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("result top level is not an object")
    inspection = data.get("inspection") if isinstance(data.get("inspection"), dict) else {}
    objects = inspection.get("objects") if isinstance(inspection.get("objects"), dict) else {}
    verdicts = inspection.get("verdicts") if isinstance(inspection.get("verdicts"), dict) else {}
    checks = inspection.get("checks_run") if isinstance(inspection.get("checks_run"), list) else []

    tessellation: dict[str, Any] = {}
    criteria: dict[str, Any] = {}
    if job_path is not None:
        job = json.loads(pathlib.Path(job_path).read_text(encoding="utf-8"))
        rules = ((job.get("inspection") or {}).get("rules")) if isinstance(job, dict) else None
        if isinstance(rules, dict):
            criteria = dict(rules)
        for operation in job.get("operations") or []:
            spec = (operation or {}).get("spec") if isinstance(operation, dict) else None
            if isinstance(spec, dict):
                for key in ("segments", "rings", "chord_height_mm"):
                    if key in spec:
                        tessellation[key] = spec[key]

    extracted_objects = []
    for name in sorted(objects):
        payload = objects[name] if isinstance(objects.get(name), dict) else {}
        volume = payload.get("volume") if isinstance(payload.get("volume"), dict) else {}
        bbox = payload.get("bbox") if isinstance(payload.get("bbox"), dict) else {}
        topology = payload.get("topology") if isinstance(payload.get("topology"), dict) else {}
        components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
        extracted_objects.append(
            {
                "name": name,
                "volume_mm3": volume.get("abs_volume_mm3"),
                "signed_volume_mm3": volume.get("signed_volume_mm3"),
                "surface_area_mm2": volume.get("surface_area_mm2"),
                "volume_grade": volume.get("grade"),
                "volume_applicable": volume.get("applicable"),
                "volume_note": volume.get("note"),
                "volume_achieved": {
                    "absolute": volume.get("triangulation_spread_mm3"),
                    "limit": volume.get("triangulation_spread_limit_mm3"),
                    "basis": "triangulation spread of warped n-gons against the producer's own limit",
                },
                "bbox_size_mm": bbox.get("size_mm"),
                "bbox_grade": bbox.get("grade"),
                "component_count": components.get("count"),
                "shell_self_consistency": {
                    "topologically_closed": volume.get("topologically_closed"),
                    "shell_closed": volume.get("shell_closed"),
                    "inconsistent_edge_pairs": volume.get("inconsistent_edge_pairs"),
                    "outward_normals": volume.get("outward_normals"),
                    "manifold_edges": topology.get("edges_manifold"),
                    "open_edges": topology.get("edges_boundary_open"),
                },
            }
        )
    return {
        "producer_plane": "meshq",
        "job_id": data.get("job_id"),
        "units": data.get("units"),
        "artifact_sha256": _sha256(result),
        "grade_tiers": inspection.get("grade_tiers"),
        "objects": extracted_objects,
        "declared_criteria": criteria,
        "tessellation": tessellation,
        "check_count": len(checks),
        "verdict_count": len(verdicts),
        "render_count": len(data.get("renders") or []),
    }
