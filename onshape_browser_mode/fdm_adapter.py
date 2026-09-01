"""Browser-owned adapter from a downloaded STEP file to shared FDM contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fdm_analysis import FdmBackends, SliceProfile, StepArtifact, build_fdm_package


def step_artifact_from_browser_export(
    path: str | Path,
    *,
    page_url: str,
    document_id: str,
    workspace_id: str,
    element_id: str,
    units: str = "from-step",
) -> StepArtifact:
    parsed = urlsplit(page_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("page_url must be a credential-free HTTPS browser URL without query or fragment")
    identifiers = {
        "documentId": document_id,
        "workspaceId": workspace_id,
        "elementId": element_id,
    }
    if any(not value for value in identifiers.values()):
        raise ValueError("browser STEP provenance requires document/workspace/element IDs")
    return StepArtifact.from_path(
        path,
        units=units,
        source={
            "mode": "browser",
            "reference": page_url,
            "identifiers": identifiers,
        },
    )


def build_browser_fdm_package(
    step: StepArtifact,
    *,
    output_dir: str | Path,
    profile: SliceProfile,
    backends: FdmBackends,
    **options: Any,
) -> dict[str, Any]:
    if step.source.get("mode") != "browser":
        raise ValueError("browser FDM adapter requires browser-owned STEP provenance")
    return build_fdm_package(
        step,
        output_dir=output_dir,
        profile=profile,
        backends=backends,
        **options,
    )
