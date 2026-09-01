from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from fdm_analysis.contracts import MeshArtifact, StepArtifact


class StepConverter(Protocol):
    """Tessellate canonical STEP with explicit, recorded tolerances."""

    def capabilities(self) -> dict[str, Any]: ...

    def convert(
        self,
        step: StepArtifact,
        *,
        output_path: Path,
        linear_tolerance_mm: float,
        angular_tolerance_degrees: float,
    ) -> MeshArtifact: ...


class UnavailableStepConverter:
    """Fail-closed placeholder until OCCT/FreeCAD/backend selection is approved."""

    def capabilities(self) -> dict[str, Any]:
        return {
            "available": False,
            "name": "unavailable",
            "reason": "no production STEP tessellation backend has been selected",
        }

    def convert(
        self,
        step: StepArtifact,
        *,
        output_path: Path,
        linear_tolerance_mm: float,
        angular_tolerance_degrees: float,
    ) -> MeshArtifact:
        del step, output_path, linear_tolerance_mm, angular_tolerance_degrees
        raise RuntimeError("STEP tessellation backend is unavailable")
