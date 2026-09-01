from __future__ import annotations

from pathlib import Path
from typing import Any

from fdm_analysis.contracts import MeshArtifact, SliceArtifact, SliceProfile
from fdm_analysis.slicers.execution import BambuExecution, default_execution


class BambuStudioBackend:
    """Version-bound Bambu Studio CLI adapter using argument arrays, never shell."""

    def __init__(
        self,
        executable: str | Path,
        *,
        version: str,
        execution: BambuExecution | None = None,
        timeout_seconds: int = 900,
    ) -> None:
        if not version.strip():
            raise ValueError("a pinned Bambu Studio version is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.executable = Path(executable)
        self.version = version.strip()
        self.execution = execution or default_execution()
        self.timeout_seconds = timeout_seconds

    def capabilities(self) -> dict[str, Any]:
        return {
            "available": self.execution.available(self.executable),
            "name": "bambu-studio",
            "version": self.version,
            "execution": self.execution.metadata(),
            "documentedInputs": ["3mf", "stl"],
            "stepInput": False,
            "supports": [
                "orient",
                "arrange",
                "load-settings",
                "load-filaments",
                "slice",
                "export-3mf",
                "export-slicedata",
            ],
        }

    def build_command(
        self,
        mesh: MeshArtifact,
        *,
        profile: SliceProfile,
        output_path: Path,
        sliced_data_path: Path,
    ) -> list[str]:
        suffix = mesh.path.suffix.lower()
        if suffix not in {".stl", ".3mf"}:
            raise ValueError("Bambu Studio CLI input must be STL or 3MF")
        settings = f"{self.execution.encode_path(profile.machine)};{self.execution.encode_path(profile.process)}"
        filaments = ";".join(self.execution.encode_path(path) for path in profile.filaments)
        command = [self.execution.command_path(self.executable)]
        if profile.orient:
            command.append("--orient")
        command.extend([
            "--arrange",
            "1" if profile.arrange else "0",
            "--load-settings",
            settings,
            "--load-filaments",
            filaments,
            "--slice",
            str(profile.plate_index),
            "--debug",
            "2",
            "--export-3mf",
            self.execution.encode_path(output_path),
            "--export-slicedata",
            self.execution.encode_path(sliced_data_path),
            self.execution.encode_path(mesh.path),
        ])
        return command

    def slice(
        self,
        mesh: MeshArtifact,
        *,
        profile: SliceProfile,
        output_path: Path,
        sliced_data_path: Path,
    ) -> SliceArtifact:
        if not self.execution.available(self.executable):
            raise RuntimeError(f"Bambu Studio is unavailable for {self.execution.name}: {self.executable}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sliced_data_path.mkdir(parents=True, exist_ok=True)
        command = self.build_command(
            mesh,
            profile=profile,
            output_path=output_path,
            sliced_data_path=sliced_data_path,
        )
        process = self.execution.run(command, timeout=self.timeout_seconds)
        if process.returncode != 0:
            stderr = (process.stderr or "").strip()
            raise RuntimeError(f"Bambu Studio slicing failed with code {process.returncode}: {stderr[:500]}")
        return SliceArtifact.from_path(
            output_path,
            backend={
                "name": "bambu-studio",
                "version": self.version,
                "command": command,
                "metricsParser": "unavailable",
            },
            metrics={
                "assessment": "unknown",
                "reason": "version-bound sliced metrics parser has no verified fixture",
            },
            sliced_data_path=sliced_data_path,
        )
