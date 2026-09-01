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
    "browser_fs_goto_definition",
    "browser_fs_insert_snippet",
    "browser_fs_insert_parameter",
    "browser_fs_toggle_fold",
    "browser_edit_feature_parameters",
    "browser_fs_watch_part_studio",
    "browser_drawing_insert_views",
    "browser_draw_part_with_views",
    "browser_print_orientation_check",
    "browser_wall_thickness_report",
    "browser_apply_blend",
    "browser_print_optimize_part",
    "browser_open_doc_menu",
    "browser_set_panel_filter",
    "browser_toggle_left_panel",
    "browser_read_selection_preview",
    "browser_element_context_menu",
    "browser_duplicate_element",
    "browser_notifications_status",
    "browser_share_document",
    "browser_view_orientation",
    "browser_spiral_ridge",
    "browser_export_step",
    "browser_build_geometry_package",
}

TOOL_OUTCOME_KEYS = {
    "browser_create_document": "created",
    "browser_deploy_and_apply_featurescript": "built",
    "browser_build_part": "built",
    "browser_assemble": "assembled",
    "browser_draw_part": "drawn",
    "browser_fs_goto_definition": "definitionFound",
    "browser_fs_insert_snippet": "snippetInserted",
    "browser_fs_insert_parameter": "parameterInserted",
    "browser_fs_toggle_fold": "foldStateApplied",
    "browser_edit_feature_parameters": "parametersApplied",
    "browser_fs_watch_part_studio": "watchConfigured",
    "browser_drawing_insert_views": "viewsInserted",
    "browser_draw_part_with_views": "drawn",
    "browser_print_orientation_check": "orientationChecked",
    "browser_wall_thickness_report": "wallThicknessMeasured",
    "browser_apply_blend": "blendApplied",
    "browser_print_optimize_part": "optimized",
    "browser_open_doc_menu": "menuOpened",
    "browser_set_panel_filter": "filterApplied",
    "browser_toggle_left_panel": "panelToggled",
    "browser_read_selection_preview": "previewFound",
    "browser_element_context_menu": "contextMenuOpened",
    "browser_duplicate_element": "duplicated",
    "browser_notifications_status": "notificationsRead",
    "browser_share_document": "shareOpened",
    "browser_view_orientation": "orientationRead",
    "browser_spiral_ridge": "ridgeCreated",
    "browser_export_step": "exported",
    "browser_build_geometry_package": "packaged",
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


def _validate_step(step: Any, ids: list[str], *, owner: str) -> None:
    if not isinstance(step, dict) or not step.get("id") or not step.get("tool"):
        raise ValueError(f"every {owner} step requires id and tool")
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


def _ordered_deliverables(project: dict[str, Any]) -> list[dict[str, Any]]:
    deliverables = project.get("deliverables", [])
    by_id = {item["id"]: item for item in deliverables}
    ordered: list[dict[str, Any]] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(deliverable_id: str, path: tuple[str, ...]) -> None:
        if deliverable_id in visited:
            return
        if deliverable_id in visiting:
            raise ValueError(f"deliverable dependency cycle: {' -> '.join((*path, deliverable_id))}")
        visiting.add(deliverable_id)
        item = by_id[deliverable_id]
        for dependency in item.get("depends_on", []):
            visit(dependency, (*path, deliverable_id))
        visiting.remove(deliverable_id)
        visited.add(deliverable_id)
        ordered.append(item)

    for item in deliverables:
        visit(item["id"], ())
    return ordered


def _iter_steps(project: dict[str, Any]) -> list[dict[str, Any]]:
    if project.get("schemaVersion", 1) == 1:
        return list(project["steps"])
    steps = list(project.get("setup", []))
    for deliverable in _ordered_deliverables(project):
        steps.extend(deliverable["steps"])
    return steps


def load_project(name: str, projects_dir: Path = PROJECTS_DIR) -> dict[str, Any]:
    if not name or Path(name).name != name:
        raise ValueError("project must be a simple fixture name")
    path = projects_dir / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Unknown browser project: {name}")
    project = json.loads(path.read_text(encoding="utf-8"))
    if project.get("name") != name:
        raise ValueError("project fixture name does not match its filename")
    version = project.get("schemaVersion", 1)
    if version not in {1, 2}:
        raise ValueError("project schemaVersion must be 1 or 2")
    ids: list[str] = []
    if version == 1:
        steps = project.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("project fixture requires a non-empty steps array")
        for step in steps:
            _validate_step(step, ids, owner="project")
    else:
        setup = project.get("setup", [])
        deliverables = project.get("deliverables")
        if not isinstance(setup, list):
            raise ValueError("project setup must be an array")
        if not isinstance(deliverables, list) or not deliverables:
            raise ValueError("project schema v2 requires one or more L6 deliverables")
        for step in setup:
            _validate_step(step, ids, owner="setup")
        deliverable_ids: list[str] = []
        for deliverable in deliverables:
            if not isinstance(deliverable, dict) or not deliverable.get("id") or not deliverable.get("kind"):
                raise ValueError("every deliverable requires id and kind")
            if deliverable["id"] in deliverable_ids:
                raise ValueError(f"duplicate deliverable id: {deliverable['id']}")
            deliverable_ids.append(deliverable["id"])
        known_deliverables = set(deliverable_ids)
        for deliverable in deliverables:
            dependencies = deliverable.get("depends_on", [])
            if not isinstance(dependencies, list) or any(item not in known_deliverables for item in dependencies):
                raise ValueError(f"deliverable {deliverable['id']} has an unknown dependency")
            steps = deliverable.get("steps")
            assertions = deliverable.get("assertions")
            outputs = deliverable.get("outputs")
            if not isinstance(steps, list) or not steps:
                raise ValueError(f"deliverable {deliverable['id']} requires non-empty steps")
            if not isinstance(assertions, list) or not assertions:
                raise ValueError(f"deliverable {deliverable['id']} requires final assertions")
            if not isinstance(outputs, list) or not outputs:
                raise ValueError(f"deliverable {deliverable['id']} requires manifest outputs")
            owned_steps: set[str] = set()
            for step in steps:
                _validate_step(step, ids, owner=f"deliverable {deliverable['id']}")
                owned_steps.add(step["id"])
            for assertion in assertions:
                if not isinstance(assertion, dict) or assertion.get("step") not in owned_steps or not assertion.get("key"):
                    raise ValueError(f"deliverable {deliverable['id']} has an invalid assertion")
            output_names: set[str] = set()
            for output in outputs:
                if (
                    not isinstance(output, dict)
                    or not output.get("name")
                    or output.get("step") not in owned_steps
                    or not output.get("key")
                    or not output.get("mediaType")
                ):
                    raise ValueError(f"deliverable {deliverable['id']} has an invalid output")
                if output["name"] in output_names:
                    raise ValueError(f"deliverable {deliverable['id']} has duplicate output names")
                output_names.add(output["name"])
        _ordered_deliverables(project)
    _reject_secrets(project)
    return project


def project_fingerprint(project: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(
            project, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    for step in _iter_steps(project):
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


def _step_ok(tool: str, result: dict[str, Any]) -> bool:
    if result.get("isError") or result.get("error"):
        return False
    outcome_key = TOOL_OUTCOME_KEYS.get(tool)
    if not outcome_key or outcome_key not in result:
        return False
    return bool(result[outcome_key])


def _evaluate_assertions(
    assertions: list[dict[str, Any]],
    results: dict[str, Any],
) -> list[dict[str, Any]]:
    evaluated = []
    for assertion in assertions:
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
        evaluated.append({**assertion, "ok": ok, "actual": value})
    return evaluated


def _build_deliverable_manifest(
    deliverable: dict[str, Any],
    *,
    project_name: str,
    fixture_sha256: str,
    results: dict[str, Any],
    assertions: list[dict[str, Any]],
) -> dict[str, Any]:
    outputs = []
    for output in deliverable["outputs"]:
        value = results.get(output["step"], {}).get(output["key"])
        outputs.append({
            "name": output["name"],
            "mediaType": output["mediaType"],
            "artifactKind": output.get("artifactKind", "remote"),
            "sourceStep": output["step"],
            "sourceKey": output["key"],
            "value": value,
            "present": value not in (None, "", [], {}),
        })
    return {
        "manifestVersion": 1,
        "semanticLevel": "L6",
        "semanticName": "deliverable_recipe",
        "project": project_name,
        "fixtureSha256": fixture_sha256,
        "deliverableId": deliverable["id"],
        "kind": deliverable["kind"],
        "dependsOn": list(deliverable.get("depends_on", [])),
        "accepted": all(item["ok"] for item in assertions) and all(item["present"] for item in outputs),
        "acceptedAt": datetime.now(timezone.utc).isoformat(),
        "assertions": assertions,
        "outputs": outputs,
    }


def run_project(
    name: str,
    *,
    executor: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    resume: bool = False,
    dry_run: bool = False,
    projects_dir: Path = PROJECTS_DIR,
    checkpoint_dir: Path = CHECKPOINT_DIR,
) -> dict[str, Any]:
    """Execute legacy steps or a v2 DAG of independently accepted L6 nodes."""
    project = load_project(name, projects_dir)
    schema_version = project.get("schemaVersion", 1)
    steps = _iter_steps(project)
    deliverables = _ordered_deliverables(project) if schema_version == 2 else []
    deliverable_by_id = {item["id"]: item for item in deliverables}
    step_owner = {
        step["id"]: deliverable["id"]
        for deliverable in deliverables
        for step in deliverable["steps"]
    }
    deliverable_step_ids = {
        item["id"]: [step["id"] for step in item["steps"]]
        for item in deliverables
    }
    checkpoint_path = checkpoint_dir / f"{name}.checkpoint.json"
    fixture_sha256 = project_fingerprint(project)
    if dry_run:
        return {
            "dryRun": True,
            "project": name,
            "schemaVersion": schema_version,
            "steps": steps,
            "stepCount": len(steps),
            "deliverables": [
                {
                    "id": item["id"],
                    "kind": item["kind"],
                    "dependsOn": list(item.get("depends_on", [])),
                    "stepIds": deliverable_step_ids[item["id"]],
                    "outputNames": [output["name"] for output in item["outputs"]],
                }
                for item in deliverables
            ],
            "deliverableCount": len(deliverables),
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
            "version": 2 if schema_version == 2 else 1,
            "project": name,
            "schemaVersion": schema_version,
            "fixtureSha256": fixture_sha256,
            "completed": [],
            "completedDeliverables": [],
            "stepResults": {},
            "deliverableManifests": {},
        }

    completed = list(checkpoint.get("completed", []))
    completed_deliverables = list(checkpoint.get("completedDeliverables", []))
    results = dict(checkpoint.get("stepResults", {}))
    manifests = dict(checkpoint.get("deliverableManifests", {}))
    for index, step in enumerate(steps):
        step_id = step["id"]
        if step_id in completed:
            continue
        owner = step_owner.get(step_id)
        if owner:
            missing_dependencies = [
                item for item in deliverable_by_id[owner].get("depends_on", [])
                if item not in completed_deliverables
            ]
            if missing_dependencies:
                raise ValueError(f"deliverable {owner} dependencies are not accepted: {missing_dependencies}")
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
            "completedDeliverables": completed_deliverables,
            "stepResults": results,
            "deliverableManifests": manifests,
            "pending": [item["id"] for item in steps if item["id"] not in completed],
        })
        if not _step_ok(step["tool"], result):
            _write_checkpoint(checkpoint_path, checkpoint)
            return {
                "project": name,
                "ok": False,
                "completed": completed,
                "completedDeliverables": completed_deliverables,
                "failed": {"index": index, "id": step_id, "deliverable": owner, "result": result},
                "checkpointPath": str(checkpoint_path),
                "resumeHint": "Fix the condition and run with resume=true",
            }
        completed.append(step_id)
        checkpoint["completed"] = completed
        checkpoint["pending"] = [item["id"] for item in steps if item["id"] not in completed]

        if owner and owner not in completed_deliverables and all(
            item in completed for item in deliverable_step_ids[owner]
        ):
            deliverable = deliverable_by_id[owner]
            acceptance = _evaluate_assertions(deliverable["assertions"], results)
            manifest = _build_deliverable_manifest(
                deliverable,
                project_name=name,
                fixture_sha256=fixture_sha256,
                results=results,
                assertions=acceptance,
            )
            manifests[owner] = manifest
            checkpoint["deliverableManifests"] = manifests
            if not manifest["accepted"]:
                _write_checkpoint(checkpoint_path, checkpoint)
                return {
                    "project": name,
                    "ok": False,
                    "completed": completed,
                    "completedDeliverables": completed_deliverables,
                    "failedDeliverable": {"id": owner, "manifest": manifest},
                    "checkpointPath": str(checkpoint_path),
                    "resumeHint": "Acceptance failed after successful mutations; inspect the manifest before any explicit retry",
                }
            completed_deliverables.append(owner)
            checkpoint["completedDeliverables"] = completed_deliverables
        _write_checkpoint(checkpoint_path, checkpoint)

    assertions = _evaluate_assertions(project.get("assertions", []), results)
    ok = all(item["ok"] for item in assertions) and all(
        item["id"] in completed_deliverables for item in deliverables
    )
    return {
        "project": name,
        "schemaVersion": schema_version,
        "ok": ok,
        "completed": completed,
        "completedDeliverables": completed_deliverables,
        "stepResults": results,
        "deliverableManifests": manifests,
        "assertions": assertions,
        "checkpointPath": str(checkpoint_path),
    }
