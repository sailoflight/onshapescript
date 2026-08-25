"""Extended browser MCP tools kept separate from the core protocol module."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _confirm(arguments: dict[str, Any]) -> None:
    if arguments.get("confirm_mutation") is not True:
        raise ValueError("This operation may mutate Onshape cloud data; set confirm_mutation=true")


def _page(*, pace: bool = True) -> tuple[Any, Any]:
    from onshape_browser_mode import actions
    from onshape_browser_mode.guard import get_guard
    from onshape_browser_mode.session import get_session

    session = get_session()
    page = session.start()
    session._enforce_single_working_page(page)
    actions.reconnect_if_needed(page)
    guard = get_guard()
    if pace:
        guard.pace()
    return page, guard


def _strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{name} must be a non-empty array of non-empty strings")
    return [item.strip() for item in value]


def _dry(tool: str, **fields: Any) -> dict[str, Any]:
    return {
        "dryRun": True,
        "tool": tool,
        "estimatedApiRequests": 0,
        **fields,
    }


def browser_wait(arguments: dict[str, Any]) -> dict[str, Any]:
    condition = arguments.get("condition", "visible")
    timeout_ms = arguments.get("timeout_ms", 30_000)
    if not isinstance(timeout_ms, int) or not 1 <= timeout_ms <= 60_000:
        raise ValueError("timeout_ms must be an integer from 1 through 60000")
    if condition not in {"visible", "hidden", "attached", "detached", "text", "url", "network_idle", "frame"}:
        raise ValueError("unsupported wait condition")
    selector = arguments.get("selector", "")
    text = arguments.get("text", "")
    frame_url = arguments.get("frame_url", "")
    if condition in {"visible", "hidden", "attached", "detached"} and not selector:
        raise ValueError(f"selector is required for condition={condition!r}")
    if condition == "text" and (not selector or not text):
        raise ValueError("selector and text are required for condition='text'")
    if condition == "url" and not text:
        raise ValueError("text is required for condition='url'")
    if condition == "frame" and not frame_url:
        raise ValueError("frame_url is required for condition='frame'")
    if not all(isinstance(value, str) for value in (selector, text, frame_url)):
        raise ValueError("selector, text, and frame_url must be strings")
    page, _ = _page(pace=False)
    from onshape_browser_mode.interaction import wait_for_condition
    return wait_for_condition(
        page,
        condition=condition,
        selector=selector,
        text=text,
        frame_url=frame_url,
        timeout_ms=timeout_ms,
    )


def browser_press_key(arguments: dict[str, Any]) -> dict[str, Any]:
    key = arguments.get("key", "")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("key must be a non-empty Playwright key chord")
    if not arguments.get("selector") and not arguments.get("target_text"):
        raise ValueError("Provide selector or target_text")
    index = arguments.get("index", 0)
    frame_url = arguments.get("frame_url", "")
    if not isinstance(index, int) or index < 0:
        raise ValueError("index must be a non-negative integer")
    if not isinstance(frame_url, str):
        raise ValueError("frame_url must be a string")
    if arguments.get("dry_run"):
        return _dry("browser_press_key", key=key, selector=arguments.get("selector", ""), targetText=arguments.get("target_text", ""), frameUrl=arguments.get("frame_url", ""))
    _confirm(arguments)
    page, _ = _page()
    from onshape_browser_mode.interaction import press_key
    return press_key(page, key=key, selector=arguments.get("selector", ""), target_text=arguments.get("target_text", ""), index=arguments.get("index", 0), frame_url=arguments.get("frame_url", ""))


def browser_type(arguments: dict[str, Any]) -> dict[str, Any]:
    text = arguments.get("text", "")
    delay = arguments.get("delay_ms", 25)
    if not isinstance(text, str) or not text:
        raise ValueError("text must be non-empty")
    if not isinstance(delay, int) or not 0 <= delay <= 1000:
        raise ValueError("delay_ms must be an integer from 0 through 1000")
    if not arguments.get("selector") and not arguments.get("target_text"):
        raise ValueError("Provide selector or target_text")
    index = arguments.get("index", 0)
    frame_url = arguments.get("frame_url", "")
    if not isinstance(index, int) or index < 0:
        raise ValueError("index must be a non-negative integer")
    if not isinstance(frame_url, str):
        raise ValueError("frame_url must be a string")
    if arguments.get("dry_run"):
        return _dry("browser_type", characterCount=len(text), selector=arguments.get("selector", ""), targetText=arguments.get("target_text", ""), frameUrl=arguments.get("frame_url", ""), clear=bool(arguments.get("clear")))
    _confirm(arguments)
    page, _ = _page()
    from onshape_browser_mode.interaction import type_text
    return type_text(page, text=text, selector=arguments.get("selector", ""), target_text=arguments.get("target_text", ""), index=arguments.get("index", 0), frame_url=arguments.get("frame_url", ""), delay_ms=delay, clear=bool(arguments.get("clear")))


def browser_sync_rest_state(arguments: dict[str, Any]) -> dict[str, Any]:
    action = arguments.get("action", "page")
    if action not in {"page", "from_args"}:
        raise ValueError("action must be page or from_args")
    if action == "from_args" and (not arguments.get("document_id") or not arguments.get("workspace_id")):
        raise ValueError("document_id and workspace_id are required for action='from_args'")
    if arguments.get("dry_run"):
        return _dry(
            "browser_sync_rest_state", action=action,
            documentIdProvided=bool(arguments.get("document_id")),
            workspaceIdProvided=bool(arguments.get("workspace_id")),
            note="No browser session or local state write was performed.",
        )
    if arguments.get("confirm_mutation") is not True:
        raise ValueError("This operation writes REST-owned local state; set confirm_mutation=true")
    from onshape_rest_api_mode.operations import sync_browser_state
    if action == "from_args":
        return sync_browser_state(
            document_id=arguments.get("document_id", ""),
            workspace_id=arguments.get("workspace_id", ""),
            element_id=arguments.get("element_id") or None,
            element_name=arguments.get("element_name", ""),
            element_type=arguments.get("element_type", ""),
        )
    page, _ = _page(pace=False)
    from onshape_browser_mode import actions
    ids = actions.parse_document_url(page.url)
    if not ids.get("documentId") or not ids.get("workspaceId"):
        return {
            "synced": False,
            "reason": "current page URL does not contain document and workspace ids",
            **ids,
        }
    tabs = actions.list_document_tabs(page).get("tabs", [])
    return sync_browser_state(
        document_id=ids.get("documentId") or "",
        workspace_id=ids.get("workspaceId") or "",
        element_id=arguments.get("element_id") or ids.get("elementId"),
        element_name=arguments.get("element_name", ""),
        element_type=arguments.get("element_type", ""),
        tabs=tabs,
    )


def _mutation_plan(name: str, arguments: dict[str, Any], steps: list[str]) -> dict[str, Any] | None:
    if arguments.get("dry_run"):
        return _dry(name, steps=steps, arguments={key: value for key, value in arguments.items() if key not in {"script", "confirm_mutation"}}, sourceLength=len(arguments.get("script", "")))
    _confirm(arguments)
    return None


def browser_insert_assembly_instances(arguments: dict[str, Any]) -> dict[str, Any]:
    names = _strings(arguments.get("instance_names"), "instance_names")
    instance_selector = arguments.get("instance_selector", "")
    if not isinstance(instance_selector, str) or not instance_selector:
        raise ValueError("instance_selector is required")
    source_names = _strings(arguments.get("source_names", names), "source_names")
    if len(source_names) != len(names):
        raise ValueError("source_names and instance_names must have equal length")
    preview = _mutation_plan("browser_insert_assembly_instances", arguments, ["open assembly", "open insert dialog", "select sources", "confirm"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.semantic import insert_assembly_instances
    return insert_assembly_instances(page, names, arguments.get("assembly_tab", ""), instance_selector, source_names)


def _instance_action(arguments: dict[str, Any], action: str) -> dict[str, Any]:
    names = _strings(arguments.get("instance_names"), "instance_names")
    instance_selector = arguments.get("instance_selector", "")
    if not isinstance(instance_selector, str) or not instance_selector:
        raise ValueError("instance_selector is required")
    preview = _mutation_plan(f"browser_{action}_instances", arguments, ["open assembly", "multi-select instances", action])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode import semantic
    return getattr(semantic, f"{action}_instances")(page, names, arguments.get("assembly_tab", ""), instance_selector)


def browser_fix_instances(arguments: dict[str, Any]) -> dict[str, Any]:
    return _instance_action(arguments, "fix")


def browser_group_instances(arguments: dict[str, Any]) -> dict[str, Any]:
    return _instance_action(arguments, "group")


def browser_create_drawing(arguments: dict[str, Any]) -> dict[str, Any]:
    source = arguments.get("source_tab", "")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source_tab is required")
    preview = _mutation_plan("browser_create_drawing", arguments, ["open drawing creation", "select source", "select template", "confirm", "read drawing frame"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.semantic import create_drawing
    return create_drawing(page, source.strip(), arguments.get("template", ""))


def _normalize_dimension(arguments: dict[str, Any], label: str = "dimension") -> dict[str, Any]:
    points = arguments.get("geometry_points") or []
    if points:
        if not isinstance(points, list) or not all(isinstance(point, dict) for point in points):
            raise ValueError(f"{label}.geometry_points must be an array of point objects")
        placement = arguments.get("placement_point")
        for point_label, point in [(f"geometry_points[{index}]", point) for index, point in enumerate(points)] + [("placement_point", placement)]:
            if not isinstance(point, dict) or not all(isinstance(point.get(axis), (int, float)) for axis in ("x", "y")):
                raise ValueError(f"{label}.{point_label} requires numeric x and y")
        tool_key = arguments.get("tool_key", "")
        if not isinstance(tool_key, str) or not tool_key:
            raise ValueError(f"{label}.tool_key is required for canvas mode")
        canvas_selector = arguments.get("canvas_selector", "canvas")
        canvas_index = arguments.get("canvas_index", 0)
        if not isinstance(canvas_selector, str) or not canvas_selector or not isinstance(canvas_index, int) or canvas_index < 0:
            raise ValueError(f"{label}.canvas_selector and non-negative canvas_index are required")
        return {
            "tool_key": tool_key, "canvas_selector": canvas_selector,
            "canvas_index": canvas_index, "geometry_points": points,
            "placement_point": placement,
            "frame_url": arguments.get("frame_url", "production-drawing-"),
        }

    tool_selector = arguments.get("tool_selector", "")
    geometry = _strings(arguments.get("geometry_selectors"), f"{label}.geometry_selectors")
    verification_selector = arguments.get("verification_selector", "")
    if not isinstance(tool_selector, str) or not tool_selector or not isinstance(verification_selector, str) or not verification_selector:
        raise ValueError(f"{label} requires either canvas points + tool_key or DOM tool/geometry/verification selectors")
    return {
        "tool_selector": tool_selector, "geometry_selectors": geometry,
        "placement_selector": arguments.get("placement_selector", ""),
        "verification_selector": verification_selector,
        "frame_url": arguments.get("frame_url", "production-drawing-"),
    }


def browser_add_drawing_dimension(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_dimension(arguments)
    preview = _mutation_plan("browser_add_drawing_dimension", arguments, ["resolve drawing frame", "trigger dimension tool", "select geometry", "place dimension", "verify drawing change"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.semantic import add_drawing_dimension
    return add_drawing_dimension(page, **normalized)


def browser_delete_element(arguments: dict[str, Any]) -> dict[str, Any]:
    element_id = arguments.get("element_id", "")
    if not isinstance(element_id, str) or not element_id.strip():
        raise ValueError("element_id is required")
    preview = _mutation_plan("browser_delete_element", arguments, ["locate visible tab by data-id", "open context menu", "delete", "verify absence"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.semantic import delete_element
    return delete_element(page, element_id.strip())


def _ensure_tab(page: Any, tab_name: str, tab_type: str) -> dict[str, Any]:
    from onshape_browser_mode import actions, selectors

    def wait_ready() -> dict[str, Any]:
        ready_selector = {
            "Feature Studio": selectors.ACE_EDITOR,
            "Part Studio": selectors.PS_FEATURES_HEADER,
            "Assembly": selectors.ASM_INSERT_BUTTON,
        }.get(tab_type)
        if not ready_selector:
            return {"ready": True}
        try:
            page.locator(ready_selector).first.wait_for(state="visible", timeout=30_000)
            return {"ready": True}
        except Exception as exc:
            return {"ready": False, "reason": f"{tab_type} did not become ready: {exc}"}

    tabs = actions.list_document_tabs(page)
    exact = [tab for tab in tabs.get("tabs", []) if tab.get("name") == tab_name]
    if exact:
        tab_id = exact[0].get("id", "")
        locator = page.locator(
            f'{selectors.TAB_BAR_TAB}[data-id="{tab_id}"]' if tab_id else selectors.TAB_BAR_TAB
        )
        if not tab_id:
            locator = locator.filter(has_text=tab_name)
        locator.first.click()
        return {"created": False, "name": tab_name, **wait_ready()}
    created = actions.create_document_tab(page, tab_type)
    if not created.get("created"):
        return created
    generated = (created.get("newTabs") or [{}])[0].get("name", "")
    renamed = None
    if tab_name and generated and generated != tab_name:
        renamed = actions.rename_tab(page, generated, tab_name)
    return {
        "created": True,
        "name": tab_name or generated,
        "rename": renamed,
        **wait_ready(),
    }


def browser_deploy_and_apply_featurescript(arguments: dict[str, Any]) -> dict[str, Any]:
    script = arguments.get("script", "")
    feature_name = arguments.get("feature_name", "")
    if not isinstance(script, str) or not script.strip() or not feature_name:
        raise ValueError("script and feature_name are required")
    preview = _mutation_plan("browser_deploy_and_apply_featurescript", arguments, ["ensure Feature Studio", "write and commit source", "ensure Part Studio", "create version if prompted", "apply feature", "read parts"])
    if preview:
        return preview
    page, guard = _page()
    from onshape_browser_mode import actions
    from onshape_browser_mode.semantic import build_part, deploy_featurescript
    fs_tab = arguments.get("feature_studio_tab", "Feature Studio 1")
    ps_tab = arguments.get("part_studio_tab", "Part Studio 1")
    fs_state = _ensure_tab(page, fs_tab, "Feature Studio")
    if not fs_state.get("ready", fs_state.get("created", False)):
        return {"deployed": False, "reason": fs_state.get("reason", "Feature Studio unavailable")}
    guard.pace()
    deployed = deploy_featurescript(page, script)
    if not deployed.get("deployed"):
        return deployed
    if not arguments.get("apply", True):
        return {"applied": False, **deployed, "featureStudio": fs_state}
    guard.pace()
    ps_state = _ensure_tab(page, ps_tab, "Part Studio")
    if not ps_state.get("ready", ps_state.get("created", False)):
        return {**deployed, "built": False, "reason": ps_state.get("reason", "Part Studio unavailable")}
    version = None
    if arguments.get("create_version", True):
        guard.pace()
        actions.open_insert_custom_feature_dialog(page)
        dialog = actions.read_insert_dialog(page)
        if dialog.get("promptSaveVersion"):
            guard.pace()
            version = actions.create_document_version(page, arguments.get("version_name", ""))
        else:
            version = {"created": False, "reason": "version prompt not present"}
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
    guard.pace()
    built = build_part(page, feature_name, ps_tab)
    return {**deployed, **built, "featureStudio": fs_state, "partStudio": ps_state, "version": version}


def browser_build_part(arguments: dict[str, Any]) -> dict[str, Any]:
    feature_name = arguments.get("feature_name", "")
    if not feature_name:
        raise ValueError("feature_name is required")
    preview = _mutation_plan("browser_build_part", arguments, ["ensure Part Studio", "apply feature", "read part count and names"])
    if preview:
        return preview
    page, guard = _page()
    part_tab = arguments.get("part_studio_tab", "Part Studio 1")
    tab_state = _ensure_tab(page, part_tab, "Part Studio")
    if not tab_state.get("ready", tab_state.get("created", False)):
        return {"built": False, "reason": tab_state.get("reason", "Part Studio unavailable")}
    guard.pace()
    from onshape_browser_mode.semantic import build_part
    return {**build_part(page, feature_name, part_tab), "partStudio": tab_state}


def browser_assemble(arguments: dict[str, Any]) -> dict[str, Any]:
    names = _strings(arguments.get("instance_names"), "instance_names")
    instance_selector = arguments.get("instance_selector", "")
    if not isinstance(instance_selector, str) or not instance_selector:
        raise ValueError("instance_selector is required")
    source_names = _strings(arguments.get("source_names", names), "source_names")
    if len(source_names) != len(names):
        raise ValueError("source_names and instance_names must have equal length")
    preview = _mutation_plan("browser_assemble", arguments, ["ensure Assembly", "insert sources", "fix/group", "read visible instances"])
    if preview:
        return preview
    page, guard = _page()
    assembly_tab = arguments.get("assembly_tab", "Assembly 1")
    tab_state = _ensure_tab(page, assembly_tab, "Assembly")
    if not tab_state.get("ready", tab_state.get("created", False)):
        return {"assembled": False, "reason": tab_state.get("reason", "Assembly unavailable")}
    guard.pace()
    from onshape_browser_mode.semantic import assemble
    return {**assemble(page, names, assembly_tab, bool(arguments.get("fix")), bool(arguments.get("group")), instance_selector, source_names), "assembly": tab_state}


def browser_draw_part(arguments: dict[str, Any]) -> dict[str, Any]:
    source = arguments.get("source_tab", "")
    if not source:
        raise ValueError("source_tab is required")
    dimensions = arguments.get("dimensions", [])
    if not isinstance(dimensions, list):
        raise ValueError("dimensions must be an array")
    normalized_dimensions = []
    for index, dimension in enumerate(dimensions):
        if not isinstance(dimension, dict):
            raise ValueError(f"dimensions[{index}] must be an object")
        normalized_dimensions.append(
            _normalize_dimension(dimension, f"dimensions[{index}]")
        )
    preview = _mutation_plan("browser_draw_part", arguments, ["create drawing", "select source/template", "add dimensions", "read frame state"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.semantic import draw_part
    return draw_part(page, source_tab=source, template=arguments.get("template", ""), dimensions=normalized_dimensions)


def browser_run_project(arguments: dict[str, Any]) -> dict[str, Any]:
    from onshape_browser_mode.project import run_project
    project_name = arguments.get("project", "module-interface-verification")
    if arguments.get("dry_run"):
        return run_project(project_name, dry_run=True)
    _confirm(arguments)

    def execute(tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool == "browser_create_document":
            page, _ = _page()
            from onshape_browser_mode.actions import create_document
            return create_document(page, args.get("name", ""))
        handler = BROWSER_HANDLERS.get(tool)
        if handler is None or tool == "browser_run_project":
            raise ValueError(f"Project tool is not allowed: {tool}")
        return handler({**args, "confirm_mutation": True})

    return run_project(project_name, executor=execute, resume=bool(arguments.get("resume")))


def _repo_root() -> Path:
    """Repository root as seen by whichever side runs this handler.

    Browser handlers execute in the Windows persistent MCP body
    (``C:\\MCP\\onshapescript``); the file path returned by a screenshot is a
    Windows path that the Linux/WSL side reads through the ``/mnt/c`` mount.
    """
    # This module lives at mcp_main/win/mcp/browser_tools.py; the repository
    # root is three parents up (mcp_main/win/mcp -> mcp_main/win -> mcp_main -> repo).
    return Path(__file__).resolve().parents[3]


def browser_capture_screenshot(arguments: dict[str, Any]) -> dict[str, Any]:
    """Capture the current browser page (or a scoped element) to a PNG file.

    This is an L1 generic read operation: it drives the live Browser viewport
    and persists a PNG that the caller (or the visual tools ``read_image``,
    ``vision_glance``, ``vision_ground``) can inspect. It does not configure or
    confirm an Onshape feature, so it needs no mutation confirmation; it does
    spend one real browser action (subject to the pacing guard).

    ``selector`` scopes the capture to one element's bounding box instead of
    the whole viewport. ``frame_url`` targets a cross-origin frame (e.g.
    ``production-drawing-``) by substring. ``full_page`` captures the whole
    scrollable page. ``output_dir`` is relative to the repository root and must
    stay inside it; ``filename`` is the PNG basename (a timestamp is appended
    when omitted). ``data_url`` additionally returns the base64 data URL.
    """
    from onshape_browser_mode.pages import resolve_scope, scope_url

    frame_url = arguments.get("frame_url", "")
    selector = arguments.get("selector", "")
    if not isinstance(frame_url, str) or not isinstance(selector, str):
        raise ValueError("frame_url and selector must be strings")
    full_page = bool(arguments.get("full_page", False))
    index = arguments.get("index", 0)
    if not isinstance(index, int) or index < 0:
        raise ValueError("index must be a non-negative integer")

    output_dir = arguments.get("output_dir", "dev/screenshots")
    if not isinstance(output_dir, str) or not output_dir.strip():
        raise ValueError("output_dir must be a non-empty string")
    root = _repo_root()

    def _resolve_target(value: str) -> Path:
        candidate = Path(value)
        if candidate.is_absolute():
            target = candidate.resolve()
            if target != root.resolve() and root.resolve() not in target.parents:
                raise ValueError("output_dir must be inside the repository root")
            return target
        return (root / candidate).resolve()

    target_dir = _resolve_target(output_dir)
    if root.resolve() not in target_dir.parents:
        raise ValueError("output_dir must be inside the repository root")
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = arguments.get("filename", "")
    if not isinstance(filename, str):
        raise ValueError("filename must be a string")
    if not filename:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"screenshot-{stamp}.png"
    elif not filename.endswith(".png"):
        filename = f"{filename}.png"
    out_path = target_dir / filename

    if arguments.get("dry_run"):
        return {
            "dryRun": True,
            "tool": "browser_capture_screenshot",
            "estimatedApiRequests": 0,
            "selector": selector,
            "frameUrl": frame_url,
            "fullPage": full_page,
            "outputPath": str(out_path),
            "note": "No browser session or file write was performed.",
        }

    page, _ = _page(pace=True)
    try:
        scope = resolve_scope(page, frame_url)
        if selector:
            locator = scope.locator(selector).nth(index)
            locator.wait_for(state="visible", timeout=15_000)
            # Element screenshots are clipped to the element's bounding box;
            # Playwright's locator.screenshot() does not accept full_page.
            locator.screenshot(path=str(out_path))
        else:
            scope.screenshot(path=str(out_path), full_page=full_page)
    except Exception as exc:  # noqa: BLE001 - structured browser failure
        return {
            "captured": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "outputPath": str(out_path),
            "frameUrl": scope_url(scope) if frame_url else None,
        }

    data = out_path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    result: dict[str, Any] = {
        "captured": True,
        "outputPath": str(out_path),
        "relativePath": str(out_path.relative_to(root)),
        "fileName": out_path.name,
        "sha256": sha256,
        "bytes": len(data),
        "selector": selector,
        "frameUrl": scope_url(scope) if frame_url else None,
        "pageUrl": page.url,
    }
    if arguments.get("data_url"):
        result["dataUrl"] = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    return result


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


_CONFIRM = {"type": "boolean", "description": "Required true for a real cloud-mutating browser action."}
_DRY = {"type": "boolean", "default": False}
_FRAME = {"type": "string", "default": "", "description": "Substring of the target Playwright frame URL; empty means the main page."}
_STRING_ARRAY = {"type": "array", "items": {"type": "string"}, "minItems": 1}


def _tool(name: str, description: str, properties: dict[str, Any], *, mutating: bool, seconds: int, required: list[str] | None = None, destructive: bool = False, network: str = "browser") -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "cost": {
            "backend": "browser",
            "network": network,
            "estimated_requests": 0,
            "max_requests": 0,
            "estimated_api_requests": 0,
            "max_api_requests": 0,
            "estimated_seconds": seconds,
            "requires_browser_session": network == "browser",
            "mutating": mutating,
            "cacheable": False,
        },
        "inputSchema": _schema(properties, required),
        "annotations": {
            "readOnlyHint": not mutating,
            "destructiveHint": destructive,
            "idempotentHint": not mutating,
            "openWorldHint": network == "browser",
        },
    }


_POINT = {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}}, "required": ["x", "y"], "additionalProperties": False}
_DIMENSION_PROPERTIES = {"tool_selector": {"type": "string", "default": ""}, "geometry_selectors": {**_STRING_ARRAY, "default": []}, "placement_selector": {"type": "string", "default": ""}, "verification_selector": {"type": "string", "default": ""}, "tool_key": {"type": "string", "default": ""}, "canvas_selector": {"type": "string", "default": "canvas"}, "canvas_index": {"type": "integer", "default": 0, "minimum": 0}, "geometry_points": {"type": "array", "items": _POINT, "default": []}, "placement_point": _POINT, "frame_url": {"type": "string", "default": "production-drawing-"}}


BROWSER_TOOLS = [
    _tool("browser_wait", "Wait up to 60 seconds for an element, text, URL, network-idle, or frame condition. Read-only and zero REST API quota.", {"condition": {"type": "string", "enum": ["visible", "hidden", "attached", "detached", "text", "url", "network_idle", "frame"], "default": "visible"}, "selector": {"type": "string", "default": ""}, "text": {"type": "string", "default": ""}, "frame_url": _FRAME, "timeout_ms": {"type": "integer", "default": 30000, "minimum": 1, "maximum": 60000}}, mutating=False, seconds=60),
    _tool("browser_press_key", "Send one trusted Playwright key press to a main-page or frame target. Zero REST API quota.", {"selector": {"type": "string", "default": ""}, "target_text": {"type": "string", "default": ""}, "index": {"type": "integer", "default": 0, "minimum": 0}, "key": {"type": "string"}, "frame_url": _FRAME, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=5, required=["key"]),
    _tool("browser_type", "Type text with trusted sequential keyboard events into a main-page or frame target. Zero REST API quota.", {"selector": {"type": "string", "default": ""}, "target_text": {"type": "string", "default": ""}, "index": {"type": "integer", "default": 0, "minimum": 0}, "text": {"type": "string"}, "frame_url": _FRAME, "delay_ms": {"type": "integer", "default": 25, "minimum": 0, "maximum": 1000}, "clear": {"type": "boolean", "default": False}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=10, required=["text"]),
    _tool("browser_sync_rest_state", "Explicitly cache browser-observed document/workspace/element ids in REST-owned local state. Performs local file I/O only and no REST request.", {"action": {"type": "string", "enum": ["page", "from_args"], "default": "page"}, "document_id": {"type": "string", "default": ""}, "workspace_id": {"type": "string", "default": ""}, "element_id": {"type": "string", "default": ""}, "element_name": {"type": "string", "default": ""}, "element_type": {"type": "string", "default": ""}, "dry_run": _DRY, "confirm_mutation": {"type": "boolean", "description": "Required true before writing local REST state."}}, mutating=True, seconds=2),
    _tool("browser_insert_assembly_instances", "Insert named Part Studio or Assembly sources through the Assembly insert dialog.", {"instance_names": _STRING_ARRAY, "source_names": {**_STRING_ARRAY, "description": "Insert-dialog source names; defaults to instance_names."}, "assembly_tab": {"type": "string", "default": ""}, "instance_selector": {"type": "string", "description": "CSS selector scoped to Assembly instance rows."}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=35, required=["instance_names", "instance_selector"]),
    _tool("browser_fix_instances", "Multi-select named Assembly instances and invoke the 固定 context action.", {"instance_names": _STRING_ARRAY, "assembly_tab": {"type": "string", "default": ""}, "instance_selector": {"type": "string", "description": "CSS selector scoped to Assembly instance rows."}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=20, required=["instance_names", "instance_selector"]),
    _tool("browser_group_instances", "Multi-select named Assembly instances and invoke the 分组 toolbar action.", {"instance_names": _STRING_ARRAY, "assembly_tab": {"type": "string", "default": ""}, "instance_selector": {"type": "string", "description": "CSS selector scoped to Assembly instance rows."}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=20, required=["instance_names", "instance_selector"]),
    _tool("browser_create_drawing", "Create a Drawing from a named Part Studio or Assembly, select an optional template, and verify the drawing frame.", {"source_tab": {"type": "string"}, "template": {"type": "string", "default": ""}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=45, required=["source_tab"]),
    _tool("browser_add_drawing_dimension", "Run a DOM-selector or canvas-coordinate dimension gesture inside the cross-origin Drawing frame and verify a selector-count or canvas-image change.", {**_DIMENSION_PROPERTIES, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=20),
    _tool("browser_delete_element", "Delete a visible document element by its tab data-id and verify that the tab disappears.", {"element_id": {"type": "string"}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=20, required=["element_id"], destructive=True),
    _tool("browser_deploy_and_apply_featurescript", "Ensure Feature/Part Studios, deploy and verify source, apply the named custom feature, and return part acceptance data.", {"script": {"type": "string"}, "feature_name": {"type": "string"}, "feature_studio_tab": {"type": "string", "default": "Feature Studio 1"}, "part_studio_tab": {"type": "string", "default": "Part Studio 1"}, "apply": {"type": "boolean", "default": True}, "create_version": {"type": "boolean", "default": True}, "version_name": {"type": "string", "default": ""}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=90, required=["script", "feature_name"], destructive=True),
    _tool("browser_build_part", "Ensure a Part Studio, apply a custom feature, and return normalized part count and names.", {"feature_name": {"type": "string"}, "part_studio_tab": {"type": "string", "default": "Part Studio 1"}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=45, required=["feature_name"]),
    _tool("browser_assemble", "Ensure an Assembly, insert named instances, optionally fix/group them, and return visibility state.", {"instance_names": _STRING_ARRAY, "source_names": {**_STRING_ARRAY, "description": "Insert-dialog source names; defaults to instance_names."}, "assembly_tab": {"type": "string", "default": "Assembly 1"}, "instance_selector": {"type": "string", "description": "CSS selector scoped to Assembly instance rows."}, "fix": {"type": "boolean", "default": False}, "group": {"type": "boolean", "default": False}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=75, required=["instance_names", "instance_selector"]),
    _tool("browser_draw_part", "Create a Drawing from a named source, add configured dimensions in its frame, and return frame/view state.", {"source_tab": {"type": "string"}, "template": {"type": "string", "default": ""}, "dimensions": {"type": "array", "items": {"type": "object", "properties": _DIMENSION_PROPERTIES, "additionalProperties": False}, "default": []}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=90, required=["source_tab"]),
    _tool("browser_run_project", "Execute a validated fixture-driven browser modeling project with per-step checkpoints and resume support.", {"project": {"type": "string", "default": "module-interface-verification"}, "resume": {"type": "boolean", "default": False}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=600),
    _tool("browser_capture_screenshot", "Capture the current browser page (or a scoped element) to a PNG file so the caller or the visual tools (read_image / vision_glance / vision_ground) can inspect it. Read-only; zero REST API quota; consumes one real browser action subject to the pacing guard.", {"selector": {"type": "string", "default": "", "description": "CSS selector scoped to one element's bounding box; empty captures the whole viewport."}, "frame_url": _FRAME, "index": {"type": "integer", "default": 0, "minimum": 0}, "full_page": {"type": "boolean", "default": False, "description": "Capture the whole scrollable page instead of the viewport."}, "output_dir": {"type": "string", "default": "dev/screenshots", "description": "Relative (or repo-rooted) output directory; must stay inside the repository root."}, "filename": {"type": "string", "default": "", "description": "PNG basename; a UTC timestamp is appended when empty."}, "data_url": {"type": "boolean", "default": False, "description": "Also return the image as a base64 data URL."}, "dry_run": _DRY}, mutating=False, seconds=10),
]

BROWSER_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "browser_wait": browser_wait,
    "browser_press_key": browser_press_key,
    "browser_type": browser_type,
    "browser_sync_rest_state": browser_sync_rest_state,
    "browser_insert_assembly_instances": browser_insert_assembly_instances,
    "browser_fix_instances": browser_fix_instances,
    "browser_group_instances": browser_group_instances,
    "browser_create_drawing": browser_create_drawing,
    "browser_add_drawing_dimension": browser_add_drawing_dimension,
    "browser_delete_element": browser_delete_element,
    "browser_deploy_and_apply_featurescript": browser_deploy_and_apply_featurescript,
    "browser_build_part": browser_build_part,
    "browser_assemble": browser_assemble,
    "browser_draw_part": browser_draw_part,
    "browser_run_project": browser_run_project,
    "browser_capture_screenshot": browser_capture_screenshot,
}


def install(tools: list[dict[str, Any]], handlers: dict[str, Callable[..., Any]]) -> None:
    """Install extended definitions and augment existing frame/watch schemas."""
    existing = {tool["name"] for tool in tools}
    tools.extend(tool for tool in BROWSER_TOOLS if tool["name"] not in existing)
    handlers.update(BROWSER_HANDLERS)
    by_name = {tool["name"]: tool for tool in tools}
    for name in ("browser_inspect", "browser_scroll", "browser_click", "browser_eval"):
        by_name[name]["inputSchema"]["properties"]["frame_url"] = _FRAME
    by_name["browser_sync_rest_state"]["annotations"]["idempotentHint"] = True
    watch_action = by_name["browser_watch"]["inputSchema"]["properties"]["action"]
    watch_action["enum"] = ["start", "status", "stop", "report", "save", "verify", "workflows"]
    by_name["browser_watch"]["inputSchema"]["properties"].update({
        "workflow": {"type": "string", "description": "Recording/template name; required for verify."},
        "filename": {"type": "string", "default": ""},
    })
