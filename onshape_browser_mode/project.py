"""Fixture-driven browser project runner with resumable local checkpoints."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT / "dev" / "fixtures-capture"
CHECKPOINT_DIR = ROOT / "onshape_browser_mode" / "user_data" / "project-runs"
_SECRET_KEY = re.compile(r"authorization|cookie|token|secret|password|api.?key", re.I)
_REF = re.compile(r"^\{\{result\.([^.]+)\.([^.}]+)\}\}$")
ALLOWED_PROJECT_TOOLS = {
    "browser_create_document",
    "browser_deploy_and_apply_featurescript",
    "browser_build_part",
    "browser_assemble",
    "browser_draw_part",
}


def _reject_secrets(value: Any, path: str = "fixture") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _SECRET_KEY.search(str(key)):
                raise ValueError(f"Secret-shaped key is forbidden at {path}.{key}")
            _reject_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secrets(child, f"{path}[{index}]")


def list_projects(projects_dir: Path = PROJECTS_DIR) -> list[str]:
    return sorted(path.stem for path in projects_dir.glob("*.json"))


def load_project(name: str, projects_dir: Path = PROJECTS_DIR) -> dict[str, Any]:
    if not name or Path(name).name != name:
        raise ValueError("project must be a simple fixture name")
    path = projects_dir / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown browser project: {name}")
    project = json.loads(path.read_text(encoding="utf-8"))
    if project.get("name") != name:
        raise ValueError("project fixture name does not match its filename")
    steps = project.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("project fixture requires a non-empty steps array")
    ids = []
    for step in steps:
        if not isinstance(step, dict) or not step.get("id") or not step.get("tool"):
            raise ValueError("every project step requires id and tool")
        if step["id"] in ids:
            raise ValueError(f"duplicate project step id: {step['id']}")
        if step["tool"] not in ALLOWED_PROJECT_TOOLS:
            raise ValueError(f"project tool is not allowed: {step['tool']}")
        ids.append(step["id"])
        script_file = (step.get("args") or {}).get("script_file")
        if script_file:
            source = (ROOT / script_file).resolve()
            allowed = PROJECTS_DIR.resolve()
            if allowed not in source.parents or not source.is_file():
                raise ValueError(f"script_file must exist under dev/fixtures-capture: {script_file}")
    _reject_secrets(project)
    return project


def project_fingerprint(project: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(
            project, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    for step in project.get("steps", []):
        script_file = (step.get("args") or {}).get("script_file")
        if script_file:
            source = (ROOT / script_file).resolve()
            digest.update(str(script_file).encode("utf-8"))
            digest.update(source.read_bytes())
    return digest.hexdigest()


def _resolve_refs(value: Any, results: dict[str, Any]) -> Any:
    if isinstance(value, str):
        match = _REF.match(value)
        if not match:
            return value
        step_id, key = match.groups()
        if step_id not in results or key not in results[step_id]:
            raise ValueError(f"unresolved project reference: {value}")
        return results[step_id][key]
    if isinstance(value, list):
        return [_resolve_refs(item, results) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_refs(child, results) for key, child in value.items()}
    return value


def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    _reject_secrets(payload, "checkpoint")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _step_ok(result: dict[str, Any]) -> bool:
    if result.get("isError") or result.get("error"):
        return False
    outcome_keys = (
        "created", "deployed", "built", "assembled", "drawn", "inserted",
        "fixed", "grouped", "deleted", "synced", "ok",
    )
    observed = [result[key] for key in outcome_keys if key in result]
    return all(bool(value) for value in observed) if observed else True


def run_project(
    name: str,
    *,
    executor: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    resume: bool = False,
    dry_run: bool = False,
    projects_dir: Path = PROJECTS_DIR,
    checkpoint_dir: Path = CHECKPOINT_DIR,
) -> dict[str, Any]:
    """Validate and execute project steps, checkpointing after every success."""
    project = load_project(name, projects_dir)
    checkpoint_path = checkpoint_dir / f"{name}.checkpoint.json"
    fixture_sha256 = project_fingerprint(project)
    if dry_run:
        return {
            "dryRun": True,
            "project": name,
            "steps": project["steps"],
            "stepCount": len(project["steps"]),
            "fixtureSha256": fixture_sha256,
            "checkpointPath": str(checkpoint_path),
        }
    if executor is None:
        raise ValueError("executor is required for a real project run")
    if resume:
        if not checkpoint_path.exists():
            raise ValueError("No checkpoint exists; run with resume=false first")
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("project") != name:
            raise ValueError("Checkpoint project does not match the requested project")
        if checkpoint.get("fixtureSha256") != fixture_sha256:
            raise ValueError("Project fixture changed after checkpoint creation; start a new run")
    else:
        if checkpoint_path.exists():
            raise ValueError("Checkpoint already exists; use resume=true or remove it explicitly")
        checkpoint = {
            "version": 1,
            "project": name,
            "fixtureSha256": fixture_sha256,
            "completed": [],
            "stepResults": {},
        }

    completed = list(checkpoint.get("completed", []))
    results = dict(checkpoint.get("stepResults", {}))
    for index, step in enumerate(project["steps"]):
        step_id = step["id"]
        if step_id in completed:
            continue
        try:
            args = _resolve_refs(step.get("args", {}), results)
            script_file = args.pop("script_file", None)
            if script_file:
                args["script"] = (ROOT / script_file).read_text(encoding="utf-8")
            result = executor(step["tool"], args)
        except Exception as exc:  # noqa: BLE001 - preserve resumable failure state
            result = {"error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict):
            result = {"error": "project executor returned a non-object result"}
        results[step_id] = result
        checkpoint.update({
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "completed": completed,
            "stepResults": results,
            "pending": [item["id"] for item in project["steps"] if item["id"] not in completed],
        })
        if not _step_ok(result):
            _write_checkpoint(checkpoint_path, checkpoint)
            return {
                "project": name,
                "ok": False,
                "completed": completed,
                "failed": {"index": index, "id": step_id, "result": result},
                "checkpointPath": str(checkpoint_path),
                "resumeHint": "Fix the condition and run with resume=true",
            }
        completed.append(step_id)
        checkpoint["completed"] = completed
        checkpoint["pending"] = [item["id"] for item in project["steps"] if item["id"] not in completed]
        _write_checkpoint(checkpoint_path, checkpoint)

    assertions = []
    for assertion in project.get("assertions", []):
        step_result = results.get(assertion.get("step"), {})
        key = assertion.get("key")
        value = step_result.get(key)
        ok = True
        if assertion.get("present"):
            ok = value not in (None, "", [], {})
        if assertion.get("equals") is not None:
            ok = value == assertion["equals"]
        if assertion.get("minimum") is not None:
            ok = isinstance(value, (int, float)) and value >= assertion["minimum"]
        assertions.append({**assertion, "ok": ok, "actual": value})
    ok = all(item["ok"] for item in assertions)
    return {
        "project": name,
        "ok": ok,
        "completed": completed,
        "stepResults": results,
        "assertions": assertions,
        "checkpointPath": str(checkpoint_path),
    }
