from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Protocol


_WSL_SHARED = re.compile(r"^/mnt/([a-zA-Z])(?:/(.*))?$")


class BambuExecution(Protocol):
    name: str

    def available(self, executable: Path) -> bool: ...

    def command_path(self, executable: Path) -> str: ...

    def encode_path(self, path: Path) -> str: ...

    def run(self, command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]: ...

    def metadata(self) -> dict[str, Any]: ...


class NativeWindowsExecution:
    name = "windows-native"

    def __init__(
        self,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.runner = runner

    def available(self, executable: Path) -> bool:
        return os.name == "nt" and executable.is_file()

    def command_path(self, executable: Path) -> str:
        if os.name != "nt":
            raise RuntimeError("native Windows Bambu execution requires Windows")
        return str(executable.resolve())

    def encode_path(self, path: Path) -> str:
        if os.name != "nt":
            raise RuntimeError("native Windows path encoding requires Windows")
        return str(path.resolve())

    def run(self, command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        return self.runner(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "host": "windows", "sharedPathRequired": False}


class WslWindowsExecution:
    """Run the Windows executable from WSL using only /mnt/<drive> artifacts."""

    name = "wsl-windows-interop"

    def __init__(
        self,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.runner = runner

    @staticmethod
    def _shared(path: Path) -> re.Match[str]:
        match = _WSL_SHARED.match(str(path.resolve()))
        if match is None:
            raise ValueError("WSL Bambu execution requires paths under /mnt/<drive>")
        return match

    def available(self, executable: Path) -> bool:
        return os.name != "nt" and executable.is_file() and _WSL_SHARED.match(str(executable.resolve())) is not None

    def command_path(self, executable: Path) -> str:
        self._shared(executable)
        return str(executable.resolve())

    def encode_path(self, path: Path) -> str:
        match = self._shared(path)
        drive = match.group(1).upper()
        remainder = (match.group(2) or "").split("/") if match.group(2) else []
        return str(PureWindowsPath(f"{drive}:\\", *remainder))

    def run(self, command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        return self.runner(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "host": "wsl", "target": "windows", "sharedPathRequired": True}


class ReplayExecution:
    """Offline fixture runner; never represents a production Windows capability."""

    name = "offline-replay"

    def __init__(
        self,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.runner = runner

    def available(self, executable: Path) -> bool:
        return executable.is_file()

    def command_path(self, executable: Path) -> str:
        return str(executable.resolve())

    def encode_path(self, path: Path) -> str:
        return str(path.resolve())

    def run(self, command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        if self.runner is None:
            raise RuntimeError("offline replay execution has no runner")
        return self.runner(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "production": False}


def default_execution() -> BambuExecution:
    return NativeWindowsExecution() if os.name == "nt" else WslWindowsExecution()
