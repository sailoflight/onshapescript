from __future__ import annotations

from typing import Any, Protocol

from fdm_analysis.contracts import MeshArtifact


class GeometryAnalyzer(Protocol):
    """Analyze a normalized mesh without knowing its Onshape source."""

    def capabilities(self) -> dict[str, Any]: ...

    def analyze(
        self,
        mesh: MeshArtifact,
        *,
        orientation_matrix: tuple[float, ...],
    ) -> dict[str, Any]: ...


class UnavailableGeometryAnalyzer:
    def capabilities(self) -> dict[str, Any]:
        return {
            "available": False,
            "name": "unavailable",
            "reason": "no production mesh analysis backend has been selected",
        }

    def analyze(
        self,
        mesh: MeshArtifact,
        *,
        orientation_matrix: tuple[float, ...],
    ) -> dict[str, Any]:
        del mesh, orientation_matrix
        raise RuntimeError("geometry analysis backend is unavailable")
