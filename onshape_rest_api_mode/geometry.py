"""REST-owned non-slicer geometry package orchestration."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from fdm_analysis import StepArtifact, build_geometry_package
from fdm_analysis.configuration import (
    command_geometry_status,
    configured_geometry_backends,
    load_command_geometry_config,
)
from fdm_analysis.contracts import file_sha256
from fdm_analysis.dependency_probe import (
    configure_geometry_dependency,
    discover_geometry_dependencies,
)
from onshape_rest_api_mode.step_export import OUTPUT_ROOT as STEP_OUTPUT_ROOT


CONFIG_PATH = Path(__file__).resolve().parent / "config" / "geometry-backend.json"
REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs" / "geometry_packages"
_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _translation_id(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("translation_id must be a nonempty opaque identifier")
    return value


def load_geometry_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return load_command_geometry_config(path)


def geometry_backend_status(
    config_path: Path = CONFIG_PATH,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    status = command_geometry_status(load_geometry_config(config_path))
    if status["ready"]:
        status["dependencyResolution"] = {
            "state": "configured_backend_ready",
            "automaticInstall": False,
            "candidates": [],
            "nextAction": None,
        }
        return status
    discovery = discover_geometry_dependencies(repo_root)
    discovery.pop("_candidates", None)
    if discovery["nextAction"]["kind"] == "configure_existing":
        discovery["nextAction"]["tool"] = "onshape_configure_geometry_backend"
    status["dependencyResolution"] = discovery
    return status


def configure_rest_geometry_backend(
    candidate_id: str,
    *,
    dry_run: bool = False,
    config_path: Path = CONFIG_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    return configure_geometry_dependency(
        config_path,
        repo_root=repo_root,
        candidate_id=candidate_id,
        dry_run=dry_run,
    )


def _load_staged_step(translation_id: str, step_output_root: Path) -> StepArtifact:
    staging = step_output_root.resolve() / translation_id
    manifest_path = staging / "step-manifest.json"
    if not manifest_path.is_file():
        raise ValueError("STEP staging manifest is missing")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("translationId") != translation_id:
        raise ValueError("STEP staging manifest translationId mismatch")
    artifact = payload.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("STEP staging manifest artifact is missing")
    relative = PurePosixPath(str(artifact.get("path", "")))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("STEP staging manifest artifact path is invalid")
    source = artifact.get("source")
    if not isinstance(source, dict) or source.get("mode") != "rest":
        raise ValueError("STEP staging provenance is not REST-owned")
    identifiers = source.get("identifiers") or {}
    if identifiers.get("translationId") != translation_id:
        raise ValueError("STEP staging provenance translationId mismatch")
    path = staging.joinpath(*relative.parts)
    if not path.is_file() or file_sha256(path) != artifact.get("sha256"):
        raise ValueError("STEP staging artifact hash verification failed")
    if path.stat().st_size != artifact.get("byteCount"):
        raise ValueError("STEP staging artifact byteCount verification failed")
    return StepArtifact.from_path(
        path,
        units=str(artifact.get("units") or "from-step"),
        source=source,
    )


def plan_rest_geometry_package(
    translation_id: str,
    *,
    config_path: Path = CONFIG_PATH,
    step_output_root: Path = STEP_OUTPUT_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> dict[str, Any]:
    tid = _translation_id(translation_id)
    status = geometry_backend_status(config_path)
    source_present = (step_output_root.resolve() / tid / "step-manifest.json").is_file()
    destination = output_root.resolve() / tid
    return {
        "dryRun": True,
        "operation": "rest-step-geometry-package",
        "translationId": tid,
        "semanticLevel": "L6",
        "deliverableType": "geometry-analysis-package",
        "sourceManifestPresent": source_present,
        "backend": status,
        "destination": str(destination),
        "destinationAvailable": not destination.exists(),
        "ready": source_present and status["ready"] and not destination.exists(),
        "network": "offline",
        "estimatedApiRequests": 0,
        "bambuIncluded": False,
    }


def build_rest_geometry_package(
    translation_id: str,
    *,
    dry_run: bool = False,
    config_path: Path = CONFIG_PATH,
    step_output_root: Path = STEP_OUTPUT_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> dict[str, Any]:
    plan = plan_rest_geometry_package(
        translation_id,
        config_path=config_path,
        step_output_root=step_output_root,
        output_root=output_root,
    )
    if dry_run:
        return plan
    if not plan["sourceManifestPresent"]:
        raise RuntimeError("REST STEP staging is unavailable; export or restore it first")
    if not plan["backend"]["ready"]:
        raise RuntimeError("configured STEP converter backend is unavailable")
    if not plan["destinationAvailable"]:
        raise RuntimeError("geometry package destination already exists")

    config = load_geometry_config(config_path)
    backends = configured_geometry_backends(config)
    if backends is None:
        raise RuntimeError("configured STEP converter backend is unavailable")
    step = _load_staged_step(translation_id, step_output_root)
    result = build_geometry_package(
        step,
        output_dir=output_root.resolve() / translation_id,
        backends=backends,
        linear_tolerance_mm=float(config["linearToleranceMm"]),
        angular_tolerance_degrees=float(config["angularToleranceDegrees"]),
    )
    return {
        **result,
        "sourceTranslationId": translation_id,
        "network": "offline",
        "apiRequests": 0,
        "bambuIncluded": False,
    }
