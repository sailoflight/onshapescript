from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from fdm_analysis.contracts import MeshArtifact, SliceArtifact, SliceProfile


class SlicerBackend(Protocol):
    """Create a profile-bound sliced project from a normalized mesh."""

    def capabilities(self) -> dict[str, Any]: ...

    def slice(
        self,
        mesh: MeshArtifact,
        *,
        profile: SliceProfile,
        output_path: Path,
        sliced_data_path: Path,
    ) -> SliceArtifact: ...
