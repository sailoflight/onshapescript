from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fdm_analysis.contracts import file_sha256


_REQUIRED_GEOMETRY = {
    "watertight",
    "dimensionsMm",
    "bedContactAreaMm2",
    "printHeightMm",
    "overhangAreaMm2",
    "centerOfMassStable",
}
_REQUIRED_SLICE = {
    "layerCount",
    "estimatedTimeSeconds",
    "filamentGrams",
    "supportRequired",
}


def assessment_state(geometry: dict[str, Any], slicing: dict[str, Any]) -> dict[str, Any]:
    missing_geometry = sorted(key for key in _REQUIRED_GEOMETRY if geometry.get(key) is None)
    missing_slice = sorted(key for key in _REQUIRED_SLICE if slicing.get(key) is None)
    return {
        "state": "assessable" if not missing_geometry and not missing_slice else "unknown",
        "missingGeometryMetrics": missing_geometry,
        "missingSliceMetrics": missing_slice,
        "pass": None,
        "reason": "threshold policy is not yet defined" if not missing_geometry and not missing_slice else "required metrics are unavailable",
    }


def write_reports(
    output_dir: Path,
    *,
    source: dict[str, Any],
    mesh: dict[str, Any],
    geometry: dict[str, Any],
    slicing: dict[str, Any],
    profile: dict[str, Any],
    orientation_matrix: tuple[float, ...],
) -> tuple[Path, Path, dict[str, Any]]:
    assessment = assessment_state(geometry, slicing.get("metrics", {}))
    report = {
        "reportVersion": 1,
        "domain": "fdm",
        "source": source,
        "mesh": mesh,
        "orientationMatrix": list(orientation_matrix),
        "geometry": geometry,
        "slicing": slicing,
        "profile": profile,
        "assessment": assessment,
    }
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(
        "# FDM Analysis Report\n\n"
        f"- Assessment: `{assessment['state']}`\n"
        f"- Pass: `{assessment['pass']}`\n"
        f"- Missing geometry metrics: `{', '.join(assessment['missingGeometryMetrics']) or 'none'}`\n"
        f"- Missing slice metrics: `{', '.join(assessment['missingSliceMetrics']) or 'none'}`\n"
        f"- STEP SHA-256: `{source['sha256']}`\n"
        f"- Mesh SHA-256: `{mesh['sha256']}`\n"
        f"- Sliced project SHA-256: `{slicing['sha256']}`\n",
        encoding="utf-8",
    )
    return json_path, markdown_path, report


def write_manifest(
    output_dir: Path,
    *,
    source_provenance: dict[str, Any],
    converter: dict[str, Any],
    analyzer: dict[str, Any],
    slicer: dict[str, Any],
    profile: dict[str, Any],
    assessment: dict[str, Any],
    artifact_paths: list[Path],
) -> tuple[Path, dict[str, Any]]:
    artifacts = [
        {
            "name": path.name,
            "path": str(path.resolve().relative_to(output_dir.resolve())),
            "byteCount": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in artifact_paths
    ]
    manifest = {
        "manifestVersion": 1,
        "semanticLevel": "L6",
        "semanticName": "deliverable_recipe",
        "deliverableType": "fdm-package",
        "sourceProvenance": source_provenance,
        "converter": converter,
        "analyzer": analyzer,
        "slicer": slicer,
        "profile": profile,
        "assessment": assessment,
        "artifacts": artifacts,
    }
    path = output_dir / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return path, manifest
