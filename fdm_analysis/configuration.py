from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fdm_analysis.geometry_pipeline import GeometryBackends
from fdm_analysis.conversion import CommandStepConverter
from fdm_analysis.metrics import StlGeometryAnalyzer


def load_command_geometry_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"geometry backend configuration is missing: {path}")
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
