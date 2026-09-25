from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from fdm_analysis.geometry_pipeline import GeometryBackends
from fdm_analysis.conversion import CommandStepConverter
from fdm_analysis.metrics import StlGeometryAnalyzer


#: The shipped default: a command backend that has a shape but is disabled.
#:
#: This is also what a checkout or install with NO live file gets. The live
#: `config/geometry-backend.json` is machine-local operator state (the selected
#: executable, argument template and tolerances), so the release artifact
#: deliberately does not carry it and an upgrade must never write it; absence
#: therefore has to mean "never configured", not "broken install". The matching
#: `geometry-backend.json.example` in each owning mode ships this exact object,
#: and `dev/tests/test_geometry_backend_default.py` pins the two together so the
#: example cannot drift away from the default.
DEFAULT_COMMAND_GEOMETRY_CONFIG: dict[str, Any] = {
    "enabled": False,
    "provider": "command",
    "name": "",
    "version": "",
    "executable": "",
    "argumentTemplate": [],
    "timeoutSeconds": 300,
    "linearToleranceMm": 0.05,
    "angularToleranceDegrees": 5.0,
    "overhangFromVerticalDegrees": 45.0,
}


def default_command_geometry_config() -> dict[str, Any]:
    """A fresh copy of the disabled default, safe for a caller to edit."""
    return copy.deepcopy(DEFAULT_COMMAND_GEOMETRY_CONFIG)


def load_command_geometry_config(path: Path) -> dict[str, Any]:
    """The configured command backend; a MISSING file means the default.

    Absence is not an error. The live file is operator-owned state that the
    release artifact excludes (see `docs/operations/RELEASE.md`), so an install
    that was never configured has no file and must report a disabled backend
    instead of raising. A file that EXISTS but is malformed still raises: that is
    an operator mistake, and silently substituting a default would hide it.
    """
    if not path.is_file():
        return default_command_geometry_config()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("geometry backend configuration must be an object")
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("geometry backend enabled must be a boolean")
    if payload.get("provider") != "command":
        raise ValueError("geometry backend provider must be command")
    for key in ("linearToleranceMm", "angularToleranceDegrees", "overhangFromVerticalDegrees"):
        value = payload.get(key)
        if not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"geometry backend {key} must be positive")
    timeout = payload.get("timeoutSeconds")
    if not isinstance(timeout, int) or not 1 <= timeout <= 3600:
        raise ValueError("geometry backend timeoutSeconds must be from 1 through 3600")
    if enabled:
        if not isinstance(payload.get("name"), str) or not payload["name"].strip():
            raise ValueError("enabled geometry backend requires name")
        if not isinstance(payload.get("version"), str) or not payload["version"].strip():
            raise ValueError("enabled geometry backend requires pinned version")
        executable = payload.get("executable")
        if not isinstance(executable, str) or not Path(executable).is_absolute():
            raise ValueError("enabled geometry backend requires an absolute executable path")
        template = payload.get("argumentTemplate")
        if not isinstance(template, list) or not template or not all(isinstance(item, str) for item in template):
            raise ValueError("enabled geometry backend requires a string argumentTemplate")
    return payload


def configured_geometry_backends(config: dict[str, Any]) -> GeometryBackends | None:
    if not config["enabled"]:
        return None
    converter = CommandStepConverter(
        config["executable"],
        name=config["name"],
        version=config["version"],
        argument_template=tuple(config["argumentTemplate"]),
        timeout_seconds=config["timeoutSeconds"],
    )
    analyzer = StlGeometryAnalyzer(
        overhang_from_vertical_degrees=float(config["overhangFromVerticalDegrees"]),
    )
    return GeometryBackends(converter, analyzer)


def command_geometry_status(config: dict[str, Any]) -> dict[str, Any]:
    backends = configured_geometry_backends(config)
    converter_status = (
        backends.converter.capabilities()
        if backends is not None
        else {
            "available": False,
            "name": None,
            "version": None,
            "execution": "argv-no-shell",
            "reason": "geometry backend is disabled in module-owned configuration",
        }
    )
    converter_status.pop("executable", None)
    analyzer = (
        backends.analyzer
        if backends is not None
        else StlGeometryAnalyzer(
            overhang_from_vertical_degrees=float(config["overhangFromVerticalDegrees"]),
        )
    )
    return {
        "configured": config["enabled"],
        "ready": bool(converter_status.get("available")),
        "provider": config["provider"],
        "converter": converter_status,
        "analyzer": analyzer.capabilities(),
        "tessellation": {
            "linearToleranceMm": config["linearToleranceMm"],
            "angularToleranceDegrees": config["angularToleranceDegrees"],
        },
        "bambuIncluded": False,
    }
