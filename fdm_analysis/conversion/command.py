from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from fdm_analysis.contracts import MeshArtifact, StepArtifact
from fdm_analysis.metrics.stl_geometry import read_stl


_ALLOWED_FIELDS = {
    "input",
    "output",
    "linear_tolerance_mm",
    "angular_tolerance_degrees",
}


_WINDOWS_CREATE_NO_WINDOW = 0x08000000


def subprocess_platform_kwargs(platform_name: str | None = None) -> dict[str, Any]:
    """Keep CLI backends invisible when the owning process runs on Windows."""
    if (platform_name or os.name) != "nt":
        return {}
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", _WINDOWS_CREATE_NO_WINDOW),
    }


class CommandStepConverter:
    """Pinned argv-only adapter for a separately selected STEP converter CLI."""

    def __init__(
        self,
        executable: str | Path,
        *,
        name: str,
        version: str,
        argument_template: tuple[str, ...],
        timeout_seconds: int = 300,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.executable = Path(executable)
        if not name.strip() or not version.strip():
            raise ValueError("converter name and pinned version are required")
        if not argument_template:
            raise ValueError("argument_template must not be empty")
        fields = set()
        for argument in argument_template:
            for field in _ALLOWED_FIELDS:
                if "{" + field + "}" in argument:
                    fields.add(field)
            residue = argument
            for field in _ALLOWED_FIELDS:
                residue = residue.replace("{" + field + "}", "")
            if "{" in residue or "}" in residue:
                raise ValueError("argument_template contains an unsupported placeholder")
        if not {"input", "output"}.issubset(fields):
            raise ValueError("argument_template must include {input} and {output}")
        if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 3600:
            raise ValueError("timeout_seconds must be from 1 through 3600")
        self.name = name.strip()
        self.version = version.strip()
        self.argument_template = tuple(argument_template)
        self.timeout_seconds = timeout_seconds
        self.runner = runner

    def capabilities(self) -> dict[str, Any]:
        return {
            "available": self.executable.is_file(),
            "name": self.name,
            "version": self.version,
            "execution": "argv-no-shell",
            "windowMode": "hidden-on-windows",
            "timeoutSeconds": self.timeout_seconds,
        }

    def build_command(
        self,
        step: StepArtifact,
        *,
        output_path: Path,
        linear_tolerance_mm: float,
        angular_tolerance_degrees: float,
    ) -> list[str]:
        if linear_tolerance_mm <= 0 or angular_tolerance_degrees <= 0:
            raise ValueError("tessellation tolerances must be positive")
        if output_path.suffix.lower() != ".stl":
            raise ValueError("command STEP converter output must use .stl")
        values = {
            "input": str(step.path.resolve()),
            "output": str(output_path.resolve()),
            "linear_tolerance_mm": str(float(linear_tolerance_mm)),
            "angular_tolerance_degrees": str(float(angular_tolerance_degrees)),
        }
        return [
            str(self.executable.resolve()),
            *(argument.format(**values) for argument in self.argument_template),
        ]

    def convert(
        self,
        step: StepArtifact,
        *,
        output_path: Path,
        linear_tolerance_mm: float,
        angular_tolerance_degrees: float,
    ) -> MeshArtifact:
        if not self.executable.is_file():
            raise RuntimeError(f"STEP converter executable is unavailable: {self.executable}")
        output = output_path.resolve()
        if output.exists():
            raise ValueError("STEP converter output already exists")
        output.parent.mkdir(parents=True, exist_ok=True)
        command = self.build_command(
            step,
            output_path=output,
            linear_tolerance_mm=linear_tolerance_mm,
            angular_tolerance_degrees=angular_tolerance_degrees,
        )
        process = self.runner(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.timeout_seconds,
            **subprocess_platform_kwargs(),
        )
        if process.returncode != 0:
            raise RuntimeError(
                f"STEP converter exited {process.returncode}: {(process.stderr or '')[-1000:]}"
            )
        triangles = read_stl(output)
        return MeshArtifact.from_path(
            output,
            units="mm",
            triangle_count=len(triangles),
            converter={
                **self.capabilities(),
                "linearToleranceMm": linear_tolerance_mm,
                "angularToleranceDegrees": angular_tolerance_degrees,
                "argumentTemplate": list(self.argument_template),
            },
        )
