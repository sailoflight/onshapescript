from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from fdm_analysis.contracts import file_sha256


_DISTRO = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class WorkspaceDeliveryTarget:
    """A configured WSL workspace destination, not caller-granted authority."""

    workspace_path: PurePosixPath
    allowed_workspace_root: PurePosixPath
    relative_dir: PurePosixPath
    wsl_distribution: str

    def __post_init__(self) -> None:
        if not self.workspace_path.is_absolute() or not self.allowed_workspace_root.is_absolute():
            raise ValueError("workspace paths must be absolute POSIX paths")
        if self.relative_dir.is_absolute() or ".." in self.relative_dir.parts:
            raise ValueError("relative_dir must stay below the workspace")
        if not _DISTRO.fullmatch(self.wsl_distribution):
            raise ValueError("invalid WSL distribution name")
        try:
            self.workspace_path.relative_to(self.allowed_workspace_root)
        except ValueError as exc:
            raise ValueError("workspace_path is outside the configured allowed root") from exc

    @property
    def destination(self) -> PurePosixPath:
        return self.workspace_path / self.relative_dir


class WindowsToWslDelivery:
    name = "windows-to-wsl-unc"

    @staticmethod
    def unc_path(path: PurePosixPath, distribution: str) -> PureWindowsPath:
        if not path.is_absolute() or not _DISTRO.fullmatch(distribution):
            raise ValueError("absolute WSL path and valid distribution are required")
        return PureWindowsPath(
            "\\\\wsl.localhost",
            distribution,
            *path.parts[1:],
        )

    def deliver(self, package_dir: str | Path, target: WorkspaceDeliveryTarget) -> dict[str, Any]:
        if os.name != "nt":
            raise RuntimeError("Windows-to-WSL UNC delivery must run on Windows")
        destination = Path(self.unc_path(target.destination, target.wsl_distribution))
        return _copy_and_verify(Path(package_dir), destination, target, self.name)


class WslLocalDelivery:
    name = "wsl-local-copy"

    def deliver(self, package_dir: str | Path, target: WorkspaceDeliveryTarget) -> dict[str, Any]:
        destination = Path(str(target.destination))
        return _copy_and_verify(Path(package_dir), destination, target, self.name)


def _load_manifest(package_dir: Path) -> dict[str, Any]:
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("FDM package manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("FDM package manifest has no artifacts")
    for artifact in artifacts:
        relative = PurePosixPath(str(artifact.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts or not artifact.get("sha256"):
            raise ValueError("manifest artifact path/hash is invalid")
    return manifest


def _verify_artifacts(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    verified = []
    for artifact in manifest["artifacts"]:
        path = root / Path(*PurePosixPath(artifact["path"]).parts)
        if not path.is_file():
            raise ValueError(f"delivered artifact is missing: {artifact['path']}")
        byte_count = path.stat().st_size
        sha256 = file_sha256(path)
        if byte_count != artifact["byteCount"] or sha256 != artifact["sha256"]:
            raise ValueError(f"delivered artifact verification failed: {artifact['path']}")
        verified.append({
            "path": artifact["path"],
            "byteCount": byte_count,
            "sha256": sha256,
        })
    return verified


def _copy_and_verify(
    package_dir: Path,
    destination: Path,
    target: WorkspaceDeliveryTarget,
    delivery_name: str,
) -> dict[str, Any]:
    source = package_dir.resolve()
    if not source.is_dir():
        raise ValueError("package_dir must be a directory")
    manifest = _load_manifest(source)
    _verify_artifacts(source, manifest)
    if destination.exists():
        raise ValueError("delivery destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    verified = _verify_artifacts(destination, manifest)
    delivered_manifest = destination / "manifest.json"
    if not delivered_manifest.is_file():
        raise ValueError("delivered manifest.json is missing")
    return {
        "delivered": True,
        "delivery": delivery_name,
        "workspacePath": str(target.workspace_path),
        "deliveryPath": str(target.destination),
        "manifestPath": str(target.destination / "manifest.json"),
        "artifacts": [
            {**item, "workspacePath": str(target.destination / PurePosixPath(item["path"]))}
            for item in verified
        ],
    }
