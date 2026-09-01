from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"{label} must be a non-empty local file: {path}")
    return resolved


@dataclass(frozen=True)
class StepArtifact:
    path: Path
    sha256: str
    units: str
    source: dict[str, Any]
    media_type: str = "model/step"

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        units: str = "from-step",
        source: dict[str, Any] | None = None,
    ) -> "StepArtifact":
        resolved = _require_file(Path(path), "STEP artifact")
        if resolved.suffix.lower() not in {".step", ".stp"}:
            raise ValueError("STEP artifact must use .step or .stp")
        return cls(
            path=resolved,
            sha256=file_sha256(resolved),
            units=units,
            source=dict(source or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "units": self.units,
            "source": self.source,
            "mediaType": self.media_type,
        }


@dataclass(frozen=True)
class MeshArtifact:
    path: Path
    sha256: str
    units: str
    triangle_count: int
    converter: dict[str, Any]
    media_type: str = "model/stl"

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        units: str,
        triangle_count: int,
        converter: dict[str, Any],
    ) -> "MeshArtifact":
        resolved = _require_file(Path(path), "mesh artifact")
        if resolved.suffix.lower() not in {".stl", ".3mf"}:
            raise ValueError("mesh artifact must use .stl or .3mf")
        if triangle_count < 0:
            raise ValueError("triangle_count must be non-negative")
        return cls(
            path=resolved,
            sha256=file_sha256(resolved),
            units=units,
            triangle_count=triangle_count,
            converter=dict(converter),
            media_type="model/3mf" if resolved.suffix.lower() == ".3mf" else "model/stl",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "units": self.units,
            "triangleCount": self.triangle_count,
            "converter": self.converter,
            "mediaType": self.media_type,
        }


@dataclass(frozen=True)
class SliceProfile:
    machine: Path
    process: Path
    filaments: tuple[Path, ...]
    plate_index: int = 0
    orient: bool = False
    arrange: bool = True

    def __post_init__(self) -> None:
        if self.plate_index < 0:
            raise ValueError("plate_index must be non-negative")
        _require_file(self.machine, "machine profile")
        _require_file(self.process, "process profile")
        if not self.filaments:
            raise ValueError("at least one filament profile is required")
        for path in self.filaments:
            _require_file(path, "filament profile")

    def provenance(self) -> dict[str, Any]:
        return {
            "machine": {"path": str(self.machine.resolve()), "sha256": file_sha256(self.machine)},
            "process": {"path": str(self.process.resolve()), "sha256": file_sha256(self.process)},
            "filaments": [
                {"path": str(path.resolve()), "sha256": file_sha256(path)}
                for path in self.filaments
            ],
            "plateIndex": self.plate_index,
            "orient": self.orient,
            "arrange": self.arrange,
        }


@dataclass(frozen=True)
class SliceArtifact:
    project_path: Path
    sha256: str
    backend: dict[str, Any]
    metrics: dict[str, Any] = field(default_factory=dict)
    sliced_data_path: Path | None = None
    media_type: str = "model/3mf"

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        backend: dict[str, Any],
        metrics: dict[str, Any] | None = None,
        sliced_data_path: str | Path | None = None,
    ) -> "SliceArtifact":
        resolved = _require_file(Path(path), "sliced project")
        if resolved.suffix.lower() != ".3mf":
            raise ValueError("sliced project must use .3mf")
        data_path = Path(sliced_data_path).resolve() if sliced_data_path else None
        if data_path is not None and not data_path.is_dir():
            raise ValueError("sliced_data_path must be a directory")
        return cls(
            project_path=resolved,
            sha256=file_sha256(resolved),
            backend=dict(backend),
            metrics=dict(metrics or {}),
            sliced_data_path=data_path,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.project_path),
            "sha256": self.sha256,
            "mediaType": self.media_type,
            "backend": self.backend,
            "metrics": self.metrics,
            "slicedDataPath": str(self.sliced_data_path) if self.sliced_data_path else None,
        }
