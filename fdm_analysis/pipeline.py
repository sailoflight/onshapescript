from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fdm_analysis.contracts import SliceProfile, StepArtifact, file_sha256
from fdm_analysis.conversion.base import StepConverter
from fdm_analysis.metrics.base import GeometryAnalyzer
from fdm_analysis.reports import write_manifest, write_reports
from fdm_analysis.slicers.base import SlicerBackend


_SECRET_KEY = re.compile(r"authorization|cookie|token|secret|password|api.?key", re.I)


def _reject_secret_keys(value: Any, path: str = "source") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _SECRET_KEY.search(str(key)):
                raise ValueError(f"secret-shaped provenance key is forbidden at {path}.{key}")
            _reject_secret_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_keys(child, f"{path}[{index}]")


def _require_under(path: Path, root: Path, label: str) -> None:
    resolved = path.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"{label} must stay inside the FDM package directory")


@dataclass(frozen=True)
class FdmBackends:
    converter: StepConverter
    analyzer: GeometryAnalyzer
    slicer: SlicerBackend


def build_fdm_package(
    step: StepArtifact,
    *,
    output_dir: str | Path,
    profile: SliceProfile,
    backends: FdmBackends,
    orientation_matrix: tuple[float, ...] = (
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ),
    linear_tolerance_mm: float = 0.05,
    angular_tolerance_degrees: float = 10.0,
) -> dict[str, Any]:
    """Build a transport-independent FDM package from canonical STEP.

    Backend selection is explicit. The function never discovers Onshape state,
    starts a browser, contacts REST, or invokes a shell.
    """
    if len(orientation_matrix) != 16:
        raise ValueError("orientation_matrix must contain 16 values")
    if linear_tolerance_mm <= 0 or angular_tolerance_degrees <= 0:
        raise ValueError("tessellation tolerances must be positive")
    _reject_secret_keys(step.source)
    if not step.path.is_file() or step.sha256 != file_sha256(step.path):
        raise ValueError("STEP artifact changed after its contract was created")
    destination = Path(output_dir).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("output_dir must be empty for a new FDM package")
    destination.mkdir(parents=True, exist_ok=True)

    packaged_step = destination / "model.step"
    shutil.copy2(step.path, packaged_step)
    packaged_source = StepArtifact.from_path(
        packaged_step,
        units=step.units,
        source=step.source,
    )
    mesh = backends.converter.convert(
        packaged_source,
        output_path=destination / "model.stl",
        linear_tolerance_mm=linear_tolerance_mm,
        angular_tolerance_degrees=angular_tolerance_degrees,
    )
    _require_under(mesh.path, destination, "mesh artifact")
    geometry = backends.analyzer.analyze(mesh, orientation_matrix=orientation_matrix)
    sliced = backends.slicer.slice(
        mesh,
        profile=profile,
        output_path=destination / "sliced-project.3mf",
        sliced_data_path=destination / "sliced-data",
    )
    _require_under(sliced.project_path, destination, "sliced project")
    if sliced.sliced_data_path is not None:
        _require_under(sliced.sliced_data_path, destination, "sliced data")
    source_dict = packaged_source.as_dict()
    mesh_dict = mesh.as_dict()
    slice_dict = sliced.as_dict()
    profile_dict = profile.provenance()
    report_json, report_markdown, report = write_reports(
        destination,
        source=source_dict,
        mesh=mesh_dict,
        geometry=geometry,
        slicing=slice_dict,
        profile=profile_dict,
        orientation_matrix=orientation_matrix,
    )
    manifest_path, manifest = write_manifest(
        destination,
        source_provenance={
            "source": step.source,
            "canonicalStepSha256": packaged_source.sha256,
            "units": packaged_source.units,
        },
        converter={
            **backends.converter.capabilities(),
            "linearToleranceMm": linear_tolerance_mm,
            "angularToleranceDegrees": angular_tolerance_degrees,
        },
        analyzer=backends.analyzer.capabilities(),
        slicer=backends.slicer.capabilities(),
        profile=profile_dict,
        assessment=report["assessment"],
        artifact_paths=[packaged_step, mesh.path, sliced.project_path, report_json, report_markdown],
    )
    return {
        "packaged": True,
        "assessment": report["assessment"],
        "step": source_dict,
        "mesh": mesh_dict,
        "slicing": slice_dict,
        "reportJson": str(report_json),
        "reportMarkdown": str(report_markdown),
        "manifestPath": str(manifest_path),
        "manifest": manifest,
    }
