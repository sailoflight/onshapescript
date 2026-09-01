"""REST-owned adapter from an already downloaded STEP file to shared FDM contracts.

This module performs no HTTP request. The REST export/translation operation owns
quota, polling, and download before calling this adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fdm_analysis import FdmBackends, SliceProfile, StepArtifact, build_fdm_package


def step_artifact_from_rest_export(
    path: str | Path,
    *,
    document_id: str,
    wv: str,
    wvid: str,
    element_id: str,
    translation_id: str,
    units: str = "from-step",
) -> StepArtifact:
    if wv not in {"w", "v"}:
        raise ValueError("wv must be w or v")
    identifiers = {
        "documentId": document_id,
        "wv": wv,
        "wvid": wvid,
        "elementId": element_id,
        "translationId": translation_id,
    }
    if any(not value for value in identifiers.values()):
        raise ValueError("REST STEP provenance requires document/version/element/translation IDs")
    return StepArtifact.from_path(
        path,
        units=units,
        source={
            "mode": "rest",
            "reference": translation_id,
            "identifiers": identifiers,
        },
    )


def build_rest_fdm_package(
    step: StepArtifact,
    *,
    output_dir: str | Path,
    profile: SliceProfile,
    backends: FdmBackends,
    **options: Any,
) -> dict[str, Any]:
    if step.source.get("mode") != "rest":
        raise ValueError("REST FDM adapter requires REST-owned STEP provenance")
    return build_fdm_package(
        step,
        output_dir=output_dir,
        profile=profile,
        backends=backends,
        **options,
    )
