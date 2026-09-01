from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fdm_analysis.conversion.command import subprocess_platform_kwargs


_PROBE = (
    "import json; from importlib import metadata, util; "
    "assert util.find_spec('cadquery') is not None and util.find_spec('OCP') is not None; "
    "print(json.dumps({'cadqueryVersion': metadata.version('cadquery'), "
    "'ocpVersion': metadata.version('cadquery-ocp')}))"
)
_DISTRO = re.compile(r"^[A-Za-z0-9._-]+$")
_MAX_SIBLINGS = 32
_MAX_PYTHON_CANDIDATES = 8
_MAX_DISTROS = 2


def windows_to_wsl_path(value: str) -> str:
    match = re.fullmatch(r"([A-Za-z]):[\\/](.*)", value)
    if not match:
        raise ValueError("Windows path must use an absolute drive path")
    drive, rest = match.groups()
    return f"/mnt/{drive.lower()}/{rest.replace(chr(92), '/')}"


def parse_wsl_distributions(output: str) -> list[str]:
    normalized = output.replace("\x00", "")
    result: list[str] = []
    for line in normalized.splitlines():
        name = line.strip().lstrip("* ").strip()
        if name and _DISTRO.fullmatch(name) and name not in result:
            result.append(name)
        if len(result) >= _MAX_DISTROS:
            break
    return result


def _candidate_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:20]


def _python_candidates(search_parent: Path) -> list[tuple[str, Path, str]]:
    candidates: list[tuple[str, Path, str]] = []
    if search_parent.is_dir():
        siblings = sorted(
            (item for item in search_parent.iterdir() if item.is_dir()),
            key=lambda item: item.name.lower(),
        )[:_MAX_SIBLINGS]
        for sibling in siblings:
            for relative in (
                Path(".venv/bin/python"),
                Path("venv/bin/python"),
                Path(".venv/Scripts/python.exe"),
                Path("venv/Scripts/python.exe"),
            ):
                candidate = sibling / relative
                if candidate.is_file():
                    candidates.append(("sibling", candidate.absolute(), sibling.name))
    global_paths = [Path(sys.executable)]
    for name in ("python3", "python"):
        resolved = shutil.which(name)
        if resolved:
            global_paths.append(Path(resolved))
    seen = {str(path) for _, path, _ in candidates}
    for candidate in global_paths:
        try:
            resolved = candidate.absolute()
        except OSError:
            continue
        if resolved.is_file() and str(resolved) not in seen:
            candidates.append(("global", resolved, resolved.name))
            seen.add(str(resolved))
    return candidates[:_MAX_PYTHON_CANDIDATES]


def probe_python(
    executable: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, str] | None:
    try:
        process = runner(
            [str(executable), "-c", _PROBE],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3,
            **subprocess_platform_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if process.returncode != 0:
        return None
    try:
        payload = json.loads((process.stdout or "").strip())
    except json.JSONDecodeError:
        return None
    cadquery_version = payload.get("cadqueryVersion")
    ocp_version = payload.get("ocpVersion")
    if not isinstance(cadquery_version, str) or not cadquery_version:
        return None
    if not isinstance(ocp_version, str) or not ocp_version:
        return None
    return {"cadqueryVersion": cadquery_version, "ocpVersion": ocp_version}


def discover_local_candidates(
    *,
    search_parent: Path,
    converter_cli: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[dict[str, Any]]:
    if not converter_cli.is_file():
        raise ValueError("CadQuery converter CLI is missing")
    result: list[dict[str, Any]] = []
    for scope, executable, project_name in _python_candidates(search_parent):
        versions = probe_python(executable, runner=runner)
        if versions is None:
            continue
        candidate_id = _candidate_id(
            "local", scope, str(executable), versions["cadqueryVersion"], versions["ocpVersion"]
        )
        result.append({
            "candidateId": candidate_id,
            "provider": "cadquery-ocp",
            "host": "local",
            "scope": scope,
            "projectName": project_name,
            **versions,
            "command": {
                "executable": str(executable),
                "argumentTemplate": [
                    str(converter_cli.resolve()),
                    "--input", "{input}",
                    "--output", "{output}",
                    "--linear-tolerance-mm", "{linear_tolerance_mm}",
                    "--angular-tolerance-degrees", "{angular_tolerance_degrees}",
                ],
            },
        })
    return result


def _sanitized(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in candidate.items() if key != "command"}


def _deduplicate(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for candidate in candidates:
        candidate_id = candidate["candidateId"]
        if candidate_id not in seen:
            result.append(candidate)
            seen.add(candidate_id)
    return result


def _discover_wsl_candidates(
    *,
    repo_root: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> list[dict[str, Any]]:
    wsl = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wsl.exe"
    if not wsl.is_file():
        resolved = shutil.which("wsl.exe")
        if not resolved:
            return []
        wsl = Path(resolved)
    try:
        listed = runner(
            [str(wsl), "-l", "-q"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            **subprocess_platform_kwargs("nt"),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if listed.returncode != 0:
        return []
    script = windows_to_wsl_path(str((repo_root / "fdm_analysis" / "dependency_probe.py").resolve()))
    converter_cli = windows_to_wsl_path(
        str((repo_root / "fdm_analysis" / "conversion" / "cadquery_step_to_stl.py").resolve())
    )
    result: list[dict[str, Any]] = []
    for distro in parse_wsl_distributions(listed.stdout or ""):
        try:
            probed = runner(
                [
                    str(wsl), "-d", distro, "--exec", "/usr/bin/python3", script,
                    "--raw-json", "--converter-cli", converter_cli,
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                **subprocess_platform_kwargs("nt"),
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probed.returncode != 0:
            continue
        try:
            payload = json.loads((probed.stdout or "").strip())
        except json.JSONDecodeError:
            continue
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("pythonPath"), str):
                continue
            versions = {
                "cadqueryVersion": item.get("cadqueryVersion"),
                "ocpVersion": item.get("ocpVersion"),
            }
            if not all(isinstance(value, str) and value for value in versions.values()):
                continue
            candidate_id = _candidate_id(
                "wsl", distro, item["pythonPath"], versions["cadqueryVersion"], versions["ocpVersion"]
            )
            result.append({
                "candidateId": candidate_id,
                "provider": "cadquery-ocp",
                "host": "wsl",
                "scope": f"wsl-{item.get('scope', 'unknown')}",
                "projectName": item.get("projectName") or "unknown",
                "distribution": distro,
                **versions,
                "command": {
                    "executable": str(wsl),
                    "argumentTemplate": [
                        "-d", distro, "--exec", item["pythonPath"], converter_cli,
                        "--input", "{input}",
                        "--output", "{output}",
                        "--linear-tolerance-mm", "{linear_tolerance_mm}",
                        "--angular-tolerance-degrees", "{angular_tolerance_degrees}",
                    ],
                },
            })
    return result


def discover_geometry_dependencies(
    repo_root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    platform_name: str | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    local = discover_local_candidates(
        search_parent=root.parent,
        converter_cli=root / "fdm_analysis" / "conversion" / "cadquery_step_to_stl.py",
        runner=runner,
    )
    candidates = list(local)
    if (platform_name or os.name) == "nt":
        candidates.extend(_discover_wsl_candidates(repo_root=root, runner=runner))
    candidates = _deduplicate(candidates)
    if candidates:
        return {
            "state": "reusable_candidates_found",
            "automaticInstall": False,
            "candidates": [_sanitized(candidate) for candidate in candidates],
            "nextAction": {
                "kind": "configure_existing",
                "requiresUserConfirmation": True,
                "candidateIds": [candidate["candidateId"] for candidate in candidates],
            },
            "_candidates": candidates,
        }
    return {
        "state": "not_found",
        "automaticInstall": False,
        "candidates": [],
        "nextAction": {
            "kind": "ask_before_install",
            "requiresUserConfirmation": True,
            "question": (
                "No compatible CadQuery/OCP dependency was found in sibling project virtual environments, "
                "global Python environments, or the configured Windows/WSL counterpart. Ask the user whether "
                "to install one; do not install automatically."
            ),
            "options": ["keep_geometry_backend_unavailable", "install_cadquery_ocp"],
        },
        "_candidates": [],
    }


def configure_geometry_dependency(
    config_path: Path,
    *,
    repo_root: Path,
    candidate_id: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    platform_name: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    discovery = discover_geometry_dependencies(
        repo_root,
        runner=runner,
        platform_name=platform_name,
    )
    candidate = next(
        (item for item in discovery["_candidates"] if item["candidateId"] == candidate_id),
        None,
    )
    if candidate is None:
        raise ValueError("candidate_id is not present in the current bounded dependency scan")
    base = json.loads(config_path.read_text(encoding="utf-8"))
    command = candidate["command"]
    configured = {
        **base,
        "enabled": True,
        "provider": "command",
        "name": f"cadquery-ocp-{candidate['host']}",
        "version": f"cadquery-{candidate['cadqueryVersion']}+OCP-{candidate['ocpVersion']}",
        "executable": command["executable"],
        "argumentTemplate": command["argumentTemplate"],
    }
    if dry_run:
        return {
            "dryRun": True,
            "configured": False,
            "candidate": _sanitized(candidate),
            "wouldWriteConfig": True,
            "automaticInstall": False,
        }
    temporary = config_path.with_suffix(config_path.suffix + ".tmp")
    temporary.write_text(json.dumps(configured, indent=2) + "\n", encoding="utf-8")
    temporary.replace(config_path)
    return {
        "configured": True,
        "candidate": _sanitized(candidate),
        "configPath": str(config_path),
        "automaticInstall": False,
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-json", action="store_true")
    parser.add_argument("--converter-cli", required=True)
    arguments = parser.parse_args()
    search_parent = Path.home() / "code"
    if not search_parent.is_dir():
        search_parent = Path.home()
    candidates = discover_local_candidates(
        search_parent=search_parent,
        converter_cli=Path(arguments.converter_cli),
    )
    raw = [
        {
            **_sanitized(candidate),
            "pythonPath": candidate["command"]["executable"],
        }
        for candidate in candidates
    ]
    print(json.dumps(raw, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
