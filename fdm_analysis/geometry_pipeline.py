from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fdm_analysis.contracts import MeshArtifact, StepArtifact, file_sha256
from fdm_analysis.conversion import StepConverter
from fdm_analysis.metrics import GeometryAnalyzer


_REQUIRED_GEOMETRY = {
    "watertight",
    "dimensionsMm",
    "bedContactAreaMm2",
    "printHeightMm",
    "overhangAreaMm2",
    "centerOfMassStable",
}
_SECRET_KEYS = {"authorization", "cookie", "token", "secret", "password", "accesskey", "secretkey"}


@dataclass(frozen=True)
class GeometryBackends:
    converter: StepConverter
    analyzer: GeometryAnalyzer


def _reject_secrets(value: Any, path: str = "source") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).replace("_", "").replace("-", "").lower()
            if normalized in _SECRET_KEYS:
                raise ValueError(f"secret-shaped provenance key is forbidden: {path}.{key}")
            _reject_secrets(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_secrets(child, f"{path}[{index}]")


def _require_under(path: Path, root: Path, label: str) -> None:
    resolved = path.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"{label} must stay inside the geometry package directory")


def _artifact(path: Path, root: Path, name: str, media_type: str) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path.resolve().relative_to(root.resolve())),
        "mediaType": media_type,
        "byteCount": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _write_markdown(path: Path, geometry: dict[str, Any], assessment: dict[str, Any]) -> None:
    lines = [
        "# Geometry analysis report",
        "",
        f"- State: `{assessment['state']}`",
        f"- Pass: `{assessment['pass']}`",
        f"- Watertight: `{geometry.get('watertight')}`",
        f"- Dimensions (mm): `{geometry.get('dimensionsMm')}`",
        f"- Print height (mm): `{geometry.get('printHeightMm')}`",
        f"- Bed contact area (mm^2): `{geometry.get('bedContactAreaMm2')}`",
        f"- Downward overhang area (mm^2): `{geometry.get('overhangAreaMm2')}`",
        f"- Center of mass stable: `{geometry.get('centerOfMassStable')}`",
        f"- Wall thickness (mm): `{geometry.get('wallThicknessMm')}`",
        "",
        "No pass/fail conclusion is emitted without a reviewed threshold policy.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_geometry_package(
    step: StepArtifact,
    *,
    output_dir: str | Path,
    backends: GeometryBackends,
    orientation_matrix: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    linear_tolerance_mm: float = 0.05,
    angular_tolerance_degrees: float = 5.0,
) -> dict[str, Any]:
    destination = Path(output_dir).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("geometry package output directory must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    _reject_secrets(step.source)
    if file_sha256(step.path) != step.sha256:
        raise ValueError("STEP source hash no longer matches its contract")

    converter_capabilities = backends.converter.capabilities()
    analyzer_capabilities = backends.analyzer.capabilities()
    if not converter_capabilities.get("available"):
        raise RuntimeError("STEP converter backend is unavailable")
    if not analyzer_capabilities.get("available"):
        raise RuntimeError("geometry analyzer backend is unavailable")

    packaged_step_path = destination / "model.step"
    shutil.copy2(step.path, packaged_step_path)
    packaged_step = StepArtifact.from_path(
        packaged_step_path,
        units=step.units,
        source=step.source,
    )
    mesh = backends.converter.convert(
        packaged_step,
        output_path=destination / "model.stl",
        linear_tolerance_mm=linear_tolerance_mm,
        angular_tolerance_degrees=angular_tolerance_degrees,
    )
    _require_under(mesh.path, destination, "mesh artifact")
    geometry = backends.analyzer.analyze(mesh, orientation_matrix=orientation_matrix)
    missing = sorted(key for key in _REQUIRED_GEOMETRY if geometry.get(key) is None)
    assessment = {
        "state": "complete" if not missing else "unknown",
        "missingGeometryMetrics": missing,
        "pass": None,
        "reason": "threshold policy is not defined" if not missing else "required geometry metrics are unavailable",
    }

    report = {
        "schemaVersion": 1,
        "reportType": "geometry-analysis",
        "source": packaged_step.as_dict(),
        "mesh": mesh.as_dict(),
        "geometry": geometry,
        "assessment": assessment,
        "backends": {
            "converter": converter_capabilities,
            "analyzer": analyzer_capabilities,
        },
    }
    report_json = destination / "report.json"
    report_md = destination / "report.md"
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_markdown(report_md, geometry, assessment)

    artifacts = [
        _artifact(packaged_step_path, destination, "model.step", "model/step"),
        _artifact(mesh.path, destination, "model.stl", mesh.media_type),
        _artifact(report_json, destination, "report.json", "application/json"),
        _artifact(report_md, destination, "report.md", "text/markdown"),
    ]
    manifest = {
        "schemaVersion": 1,
        "semanticLevel": "L6",
        "semanticName": "deliverable_recipe",
        "deliverableType": "geometry-analysis-package",
        "sourceMode": step.source.get("mode"),
        "sourceSha256": step.sha256,
        "orientationMatrix": list(orientation_matrix),
        "tessellation": {
            "linearToleranceMm": linear_tolerance_mm,
            "angularToleranceDegrees": angular_tolerance_degrees,
        },
        "acceptance": assessment,
        "backends": report["backends"],
        "artifacts": artifacts,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "packaged": True,
        "semanticLevel": "L6",
        "deliverableType": "geometry-analysis-package",
        "outputDir": str(destination),
        "manifestPath": str(manifest_path),
        "reportPath": str(report_json),
        "assessment": assessment,
        "geometry": geometry,
    }
