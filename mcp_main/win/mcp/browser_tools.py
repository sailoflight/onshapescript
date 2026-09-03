"""Extended browser MCP tools kept separate from the core protocol module."""

from __future__ import annotations

import base64
import hashlib
import re
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


def browser_get_fs_compile_status(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read compiler evidence from Ace and the FeatureScript notice pane."""
    page, _ = _page(pace=False)
    from onshape_browser_mode import actions

    return {
        "pageUrl": page.url,
        **actions.parse_document_url(page.url),
        **actions.read_featurescript_compile_status(page),
    }


def browser_fs_read_notices(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read active-tab FeatureScript notices and restore the pane state."""
    page, _ = _page(pace=False)
    from onshape_browser_mode import actions

    return {
        "pageUrl": page.url,
        **actions.parse_document_url(page.url),
        **actions.read_featurescript_notices(page),
    }


def browser_fs_capture_diagnostic(arguments: dict[str, Any]) -> dict[str, Any]:
    """Persist the active FeatureScript source and current compile evidence."""
    page, _ = _page(pace=False)
    from onshape_browser_mode import actions, diagnostics

    source = actions.read_featurescript_editor(page)
    if source is None:
        return {
            "captured": False,
            "reason": "FeatureScript editor not found on the current page",
            "pageUrl": page.url,
            **actions.parse_document_url(page.url),
        }
    compile_status = actions.read_featurescript_compile_status(page)
    captured = diagnostics.save_featurescript_diagnostic(
        source=source,
        compile_status=compile_status,
        page_url=page.url,
        phase="manual-capture",
    )
    return {
        **captured,
        "pageUrl": page.url,
        **actions.parse_document_url(page.url),
        "compiled": bool(compile_status.get("compiled")),
        "annotationCount": compile_status.get("annotationCount", 0),
        "noticeCount": compile_status.get("noticeCount", 0),
        "errors": compile_status.get("errors", []),
    }


def browser_get_fs_symbols(arguments: dict[str, Any]) -> dict[str, Any]:
    """Open Module outline and read the active Feature Studio symbol inventory."""
    page, _ = _page()
    from onshape_browser_mode import actions

    return {
        "pageUrl": page.url,
        **actions.parse_document_url(page.url),
        **actions.read_featurescript_symbols(page),
    }


def browser_fs_goto_definition(arguments: dict[str, Any]) -> dict[str, Any]:
    symbol = arguments.get("symbol", "")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol is required")
    page, _ = _page()
    from onshape_browser_mode.transactions import fs_goto_definition
    return fs_goto_definition(page, symbol.strip())


def browser_fs_insert_snippet(arguments: dict[str, Any]) -> dict[str, Any]:
    for name in ("row", "column"):
        value = arguments.get(name)
        if value is not None and (not isinstance(value, int) or value < 0):
            raise ValueError(f"{name} must be a non-negative integer")
    preview = _mutation_plan("browser_fs_insert_snippet", arguments, ["position Ace cursor", "open editor context menu", "click exact 插入代码段", "verify source delta and dirty state"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.transactions import fs_insert_snippet
    return fs_insert_snippet(page, row=arguments.get("row"), column=arguments.get("column"))


def browser_fs_insert_parameter(arguments: dict[str, Any]) -> dict[str, Any]:
    for name in ("row", "column"):
        value = arguments.get(name)
        if value is not None and (not isinstance(value, int) or value < 0):
            raise ValueError(f"{name} must be a non-negative integer")
    preview = _mutation_plan("browser_fs_insert_parameter", arguments, ["position FeatureScript cursor", "click verified Length parameter toolbar item", "verify source delta and dirty state"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.transactions import fs_insert_parameter
    return fs_insert_parameter(page, row=arguments.get("row"), column=arguments.get("column"))


def browser_fs_toggle_fold(arguments: dict[str, Any]) -> dict[str, Any]:
    action = arguments.get("action", "toggle")
    if action not in {"toggle", "fold", "unfold"}:
        raise ValueError("action must be toggle, fold, or unfold")
    row = arguments.get("row")
    if row is not None and (not isinstance(row, int) or row < 0):
        raise ValueError("row must be a non-negative integer")
    page, _ = _page()
    from onshape_browser_mode.transactions import fs_toggle_fold
    return fs_toggle_fold(page, row=row, action=action)


def browser_edit_feature_parameters(arguments: dict[str, Any]) -> dict[str, Any]:
    feature_name = arguments.get("feature_name", "")
    parameters = arguments.get("parameters")
    if not isinstance(feature_name, str) or not feature_name.strip():
        raise ValueError("feature_name is required")
    if not isinstance(parameters, dict) or not parameters:
        raise ValueError("parameters must be a non-empty object")
    for key, value in parameters.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", key):
            raise ValueError("parameter ids must be CSS-safe identifiers")
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError("parameter values must be strings, numbers, or booleans")
    preview = _mutation_plan("browser_edit_feature_parameters", arguments, ["open feature dialog", "update named fields", "read values back", "accept dialog", "reopen and verify persistence/regen"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.transactions import edit_feature_parameters
    return edit_feature_parameters(page, feature_name.strip(), parameters, accept=True)


def browser_fs_watch_part_studio(arguments: dict[str, Any]) -> dict[str, Any]:
    part_studio = arguments.get("part_studio", "")
    mode = arguments.get("mode", "watch")
    if not isinstance(part_studio, str) or not part_studio.strip():
        raise ValueError("part_studio is required")
    if mode not in {"watch", "configure"}:
        raise ValueError("mode must be watch or configure")
    preview = _mutation_plan("browser_fs_watch_part_studio", arguments, ["read current watch target", "open exact watch/configure dropdown", "select exact target", "verify toolbar readback"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.transactions import fs_watch_part_studio
    return fs_watch_part_studio(page, part_studio.strip(), mode=mode)


def browser_open_doc_menu(arguments: dict[str, Any]) -> dict[str, Any]:
    command = arguments.get("command", "")
    if not isinstance(command, str):
        raise ValueError("command must be a string")
    preview = _mutation_plan("browser_open_doc_menu", arguments, ["open document-name menu", "read item list", "optionally trigger exact command"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.transactions import open_doc_menu
    return open_doc_menu(page, command)


def browser_set_panel_filter(arguments: dict[str, Any]) -> dict[str, Any]:
    query = arguments.get("query", "")
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    page, _ = _page()
    from onshape_browser_mode.transactions import set_panel_filter
    return set_panel_filter(page, query)


def browser_toggle_left_panel(arguments: dict[str, Any]) -> dict[str, Any]:
    target = arguments.get("target", "toggle")
    if target not in {"toggle", "show", "hide"}:
        raise ValueError("target must be toggle, show, or hide")
    width = arguments.get("expanded_width", 200)
    if not isinstance(width, int) or not 80 <= width <= 600:
        raise ValueError("expanded_width must be an integer from 80 through 600")
    page, _ = _page()
    from onshape_browser_mode.transactions import toggle_left_panel
    return toggle_left_panel(page, target=target, expanded_width=width)


def browser_read_selection_preview(arguments: dict[str, Any]) -> dict[str, Any]:
    page, _ = _page(pace=False)
    from onshape_browser_mode.transactions import read_selection_preview
    return read_selection_preview(page)


def browser_element_context_menu(arguments: dict[str, Any]) -> dict[str, Any]:
    element_id = arguments.get("element_id", "")
    if not isinstance(element_id, str) or not element_id.strip():
        raise ValueError("element_id is required")
    page, _ = _page()
    from onshape_browser_mode.transactions import element_context_menu
    return element_context_menu(page, element_id=element_id.strip())


def browser_duplicate_element(arguments: dict[str, Any]) -> dict[str, Any]:
    element_id = arguments.get("element_id", "")
    if not isinstance(element_id, str) or not element_id.strip():
        raise ValueError("element_id is required")
    preview = _mutation_plan("browser_duplicate_element", arguments, ["open exact element-id context menu", "click exact 复制 item", "complete copy dialog", "verify exactly one new tab id"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.transactions import duplicate_element
    return duplicate_element(page, element_id=element_id.strip(), new_name=arguments.get("new_name", ""))


def browser_notifications_status(arguments: dict[str, Any]) -> dict[str, Any]:
    page, _ = _page()
    from onshape_browser_mode.transactions import notifications_status
    return notifications_status(page, open_drawer=bool(arguments.get("open_drawer", False)))


def browser_share_document(arguments: dict[str, Any]) -> dict[str, Any]:
    page, _ = _page()
    from onshape_browser_mode.transactions import share_document
    return share_document(page)


def browser_view_orientation(arguments: dict[str, Any]) -> dict[str, Any]:
    orientation = arguments.get("orientation", "current")
    if orientation not in {"current", "front", "back", "top", "bottom", "left", "right", "isometric"}:
        raise ValueError("unsupported orientation")
    page, _ = _page()
    from onshape_browser_mode.transactions import view_orientation
    return view_orientation(page, orientation="" if orientation == "current" else ("iso" if orientation == "isometric" else orientation))


def browser_drawing_insert_views(arguments: dict[str, Any]) -> dict[str, Any]:
    part_name = arguments.get("part_name", "")
    layout = arguments.get("view_layout", "four")
    if not isinstance(part_name, str) or not part_name.strip():
        raise ValueError("part_name is required")
    if layout not in {"four", "single", "iso"}:
        raise ValueError("view_layout must be four, single, or iso")
    preview = _mutation_plan("browser_drawing_insert_views", arguments, ["open exact Part Studio", "open exact part context menu", "select drawing layout", "accept", "verify drawing-view geometry"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.modeling_transactions import drawing_insert_views
    return drawing_insert_views(page, part_name=part_name.strip(), view_layout=layout, part_studio_tab=arguments.get("part_studio_tab", ""), template=arguments.get("template", ""))


def browser_draw_part_with_views(arguments: dict[str, Any]) -> dict[str, Any]:
    part_name = arguments.get("part_name", "")
    layout = arguments.get("view_layout", "four")
    if not isinstance(part_name, str) or not part_name.strip():
        raise ValueError("part_name is required")
    if layout not in {"four", "single", "iso"}:
        raise ValueError("view_layout must be four, single, or iso")
    dimensions = arguments.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("dimensions must be a non-empty array; use browser_drawing_insert_views for views only")
    normalized = []
    for index, dimension in enumerate(dimensions):
        if not isinstance(dimension, dict):
            raise ValueError(f"dimensions[{index}] must be an object")
        normalized.append(_normalize_dimension(dimension, f"dimensions[{index}]"))
    preview = _mutation_plan("browser_draw_part_with_views", arguments, ["insert verified drawing views", "add requested dimensions", "require every stage acceptance"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.modeling_transactions import draw_part_with_views
    return draw_part_with_views(page, part_name=part_name.strip(), view_layout=layout, part_studio_tab=arguments.get("part_studio_tab", ""), template=arguments.get("template", ""), dimensions=normalized)


def browser_print_orientation_check(arguments: dict[str, Any]) -> dict[str, Any]:
    body_name = arguments.get("body_name", "")
    direction = arguments.get("build_direction", "+z")
    limit = arguments.get("max_overhang_angle_degrees", 45)
    if not isinstance(body_name, str) or not body_name.strip():
        raise ValueError("body_name is required")
    if direction not in {"+x", "-x", "+y", "-y", "+z", "-z"}:
        raise ValueError("unsupported build_direction")
    if not isinstance(limit, (int, float)) or not 0 <= limit <= 90:
        raise ValueError("max_overhang_angle_degrees must be from 0 through 90")
    from onshape_browser_mode.modeling_transactions import print_orientation_check
    return print_orientation_check(None, body_name=body_name.strip(), build_direction=direction, max_overhang_angle_degrees=float(limit))


def browser_wall_thickness_report(arguments: dict[str, Any]) -> dict[str, Any]:
    body_name = arguments.get("body_name", "")
    minimum = arguments.get("minimum_allowed_mm")
    samples = arguments.get("samples", [])
    if not isinstance(body_name, str) or not body_name.strip():
        raise ValueError("body_name is required")
    if not isinstance(minimum, (int, float)) or minimum <= 0:
        raise ValueError("minimum_allowed_mm must be positive")
    if not isinstance(samples, list) or any(not isinstance(item, str) or not item.strip() for item in samples) or len(samples) > 32:
        raise ValueError("samples must contain at most 32 non-empty semantic names")
    page, _ = _page()
    from onshape_browser_mode.modeling_transactions import wall_thickness_report
    return wall_thickness_report(page, body_name=body_name.strip(), minimum_allowed_mm=float(minimum), samples=samples)


def browser_apply_blend(arguments: dict[str, Any]) -> dict[str, Any]:
    operation = arguments.get("operation", "fillet")
    targets = _strings(arguments.get("targets"), "targets")
    amount = arguments.get("amount", "")
    if operation not in {"fillet", "chamfer", "draft"}:
        raise ValueError("operation must be fillet, chamfer, or draft")
    amount_match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|m|in|inch|deg|°)\s*", amount, re.I) if isinstance(amount, str) else None
    if amount_match is None or float(amount_match.group(1)) <= 0:
        raise ValueError("amount must be a positive unit-bearing quantity")
    preview = _mutation_plan("browser_apply_blend", arguments, ["select semantic targets", f"open {operation} tool", "set amount", "accept", "verify exact new history row"])
    if preview:
        return preview
    page, _ = _page()
    from onshape_browser_mode.modeling_transactions import apply_blend
    return apply_blend(page, operation=operation, targets=targets, amount=amount.strip())


def browser_print_optimize_part(arguments: dict[str, Any]) -> dict[str, Any]:
    body_name = arguments.get("body_name", "")
    orientation = arguments.get("orientation")
    wall = arguments.get("wall")
    blend = arguments.get("blend")
    if not isinstance(body_name, str) or not body_name.strip():
        raise ValueError("body_name is required")
    if not isinstance(orientation, dict) or not isinstance(wall, dict):
        raise ValueError("orientation and wall stage objects are required")
    direction = orientation.get("build_direction")
    angle = orientation.get("max_overhang_angle_degrees")
    if direction not in {"+x", "-x", "+y", "-y", "+z", "-z"} or not isinstance(angle, (int, float)) or not 0 <= angle <= 90:
        raise ValueError("orientation requires a valid build_direction and 0..90 angle")
    minimum = wall.get("minimum_allowed_mm")
    samples = wall.get("samples", [])
    if not isinstance(minimum, (int, float)) or minimum <= 0:
        raise ValueError("wall.minimum_allowed_mm must be positive")
    if not isinstance(samples, list) or len(samples) > 32 or any(not isinstance(item, str) or not item.strip() for item in samples):
        raise ValueError("wall.samples must contain at most 32 non-empty names")
    if blend is not None:
        if not isinstance(blend, dict):
            raise ValueError("blend must be an object")
        if blend.get("operation") not in {"fillet", "chamfer", "draft"}:
            raise ValueError("blend.operation must be fillet, chamfer, or draft")
        _strings(blend.get("targets"), "blend.targets")
        amount = blend.get("amount", "")
        amount_match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|m|in|inch|deg|°)\s*", amount, re.I) if isinstance(amount, str) else None
        if amount_match is None or float(amount_match.group(1)) <= 0:
            raise ValueError("blend.amount must be a positive unit-bearing quantity")
    if arguments.get("dry_run", False):
        return {
            "dryRun": True,
            "tool": "browser_print_optimize_part",
            "semanticValidity": "invalid",
            "browserActionPlanned": False,
            "mutationPlanned": False,
            "reason": "draft analysis is not an FDM orientation engine",
        }
    from onshape_browser_mode.modeling_transactions import print_optimize_part
    return print_optimize_part(None, body_name=body_name.strip(), blend=blend, orientation=orientation, wall=wall)


def browser_spiral_ridge(arguments: dict[str, Any]) -> dict[str, Any]:
    numeric = {}
    ranges = {
        "base_radius_mm": (0.1, 10_000.0),
        "pitch_mm": (0.1, 10_000.0),
        "ridge_width_mm": (0.05, 1_000.0),
        "ridge_height_mm": (0.05, 1_000.0),
        "length_mm": (0.1, 100_000.0),
    }
    for name, (minimum, maximum) in ranges.items():
        value = arguments.get(name)
        if not isinstance(value, (int, float)) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be from {minimum} through {maximum}")
        numeric[name] = float(value)
    if numeric["length_mm"] / numeric["pitch_mm"] > 10_000:
        raise ValueError("spiral ridge may not exceed 10000 revolutions")
    if numeric["ridge_width_mm"] >= numeric["pitch_mm"]:
        raise ValueError("ridge_width_mm must be smaller than pitch_mm")
    if numeric["ridge_height_mm"] >= numeric["base_radius_mm"]:
        raise ValueError("ridge_height_mm must be smaller than base_radius_mm")
    preview = _mutation_plan("browser_spiral_ridge", arguments, ["generate bounded helix+sweep FeatureScript", "deploy with compile verification", "apply custom feature", "verify part/history result"])
    if preview:
        return {**preview, "revolutions": numeric["length_mm"] / numeric["pitch_mm"]}
    from onshape_browser_mode.modeling_transactions import generate_spiral_ridge_script
    script = generate_spiral_ridge_script(**numeric, clockwise=bool(arguments.get("clockwise", True)))
    result = browser_deploy_and_apply_featurescript({
        "script": script,
        "feature_name": "Spiral ridge",
        "feature_studio_tab": arguments.get("feature_studio_tab", "Spiral ridge FS"),
        "part_studio_tab": arguments.get("part_studio_tab", "Spiral ridge PS"),
        "create_version": bool(arguments.get("create_version", True)),
        "version_name": arguments.get("version_name", ""),
        "apply": True,
        "confirm_mutation": True,
    })
    return {"ridgeCreated": bool(result.get("deployed") and result.get("built")), "revolutions": numeric["length_mm"] / numeric["pitch_mm"], "result": result}


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
        actions.dismiss_stale_context_menu(page)
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
    dimensions = arguments.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("dimensions must be a non-empty array; use browser_drawing_insert_views for views only")
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
        definition = next((item for item in BROWSER_TOOLS if item["name"] == tool), None)
        if definition is None:
            raise ValueError(f"Project tool has no registered schema: {tool}")
        call_args = dict(args)
        if not definition["annotations"]["readOnlyHint"]:
            call_args["confirm_mutation"] = True
        return handler(call_args)

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

    filename = arguments.get("filename", "")
    if not isinstance(filename, str):
        raise ValueError("filename must be a string")
    if filename and (Path(filename).name != filename or filename in {".", ".."}):
        raise ValueError("filename must be a PNG basename without directory components")
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

    target_dir.mkdir(parents=True, exist_ok=True)
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


def browser_geometry_status(arguments: dict[str, Any]) -> dict[str, Any]:
    from onshape_browser_mode.geometry import browser_geometry_status as status

    return status()


def browser_configure_geometry_backend(arguments: dict[str, Any]) -> dict[str, Any]:
    candidate_id = arguments.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("candidate_id is required")
    from onshape_browser_mode.geometry import configure_browser_geometry_backend

    if arguments.get("dry_run"):
        return configure_browser_geometry_backend(candidate_id, dry_run=True)
    _confirm(arguments)
    return configure_browser_geometry_backend(candidate_id)


def browser_build_geometry_package(arguments: dict[str, Any]) -> dict[str, Any]:
    export_id = arguments.get("export_id")
    if not isinstance(export_id, str) or not export_id.strip():
        raise ValueError("export_id is required")
    from onshape_browser_mode.geometry import build_browser_geometry_package

    if arguments.get("dry_run"):
        return build_browser_geometry_package(export_id, dry_run=True)
    _confirm(arguments)
    return build_browser_geometry_package(export_id)


def browser_export_step(arguments: dict[str, Any]) -> dict[str, Any]:
    required = ("source_tab", "export_id", "document_id", "workspace_id", "element_id")
    if any(not isinstance(arguments.get(key), str) or not arguments[key].strip() for key in required):
        raise ValueError(f"{', '.join(required)} are required")
    from onshape_browser_mode.step_export import export_browser_step, plan_browser_step_export

    if arguments.get("dry_run"):
        return plan_browser_step_export(
            source_tab=arguments["source_tab"],
            export_id=arguments["export_id"],
        )
    _confirm(arguments)
    page, _ = _page()
    return export_browser_step(
        page,
        source_tab=arguments["source_tab"],
        export_id=arguments["export_id"],
        document_id=arguments["document_id"],
        workspace_id=arguments["workspace_id"],
        element_id=arguments["element_id"],
        timeout_ms=arguments.get("timeout_ms", 120_000),
    )


def browser_discover_tools(arguments: dict[str, Any]) -> dict[str, Any]:
    query = arguments.get("query", "")
    levels = arguments.get("semantic_levels")
    limit = arguments.get("limit", 8)
    include_schema = arguments.get("include_schema", True)
    if levels is not None and (
        not isinstance(levels, list)
        or any(level not in {"L1", "L2", "L3", "L4", "L5", "L6"} for level in levels)
    ):
        raise ValueError("semantic_levels must contain only L1 through L6")
    if not isinstance(include_schema, bool):
        raise ValueError("include_schema must be a boolean")
    from mcp_main.win.mcp import server
    from onshape_browser_mode.semantics import discover_tools

    return discover_tools(
        server.TOOLS,
        query=query,
        semantic_levels=levels,
        limit=limit,
        include_schema=include_schema,
    )


def browser_invoke_discovered(arguments: dict[str, Any]) -> dict[str, Any]:
    name = arguments.get("name", "")
    nested = arguments.get("arguments", {})
    if not isinstance(name, str) or not name.startswith("browser_"):
        raise ValueError("name must identify a browser tool")
    if name in {"browser_discover_tools", "browser_invoke_discovered"}:
        raise ValueError("discovery gateways cannot invoke themselves")
    if not isinstance(nested, dict):
        raise ValueError("arguments must be an object")
    forwarded = dict(nested)
    if "dry_run" in arguments:
        forwarded.setdefault("dry_run", arguments["dry_run"])
    if "confirm_mutation" in arguments:
        forwarded.setdefault("confirm_mutation", arguments["confirm_mutation"])
    from mcp_main.win.mcp import server

    handler = server.HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown browser tool: {name}")
    result = handler(forwarded)
    if not isinstance(result, dict):
        raise ValueError("discovered browser handler returned a non-object result")
    return {"invokedTool": name, "result": result}


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
_ORIENTATION_STAGE = {"type": "object", "properties": {"build_direction": {"type": "string", "enum": ["+x", "-x", "+y", "-y", "+z", "-z"]}, "max_overhang_angle_degrees": {"type": "number", "minimum": 0, "maximum": 90}}, "required": ["build_direction", "max_overhang_angle_degrees"], "additionalProperties": False}
_WALL_STAGE = {"type": "object", "properties": {"minimum_allowed_mm": {"type": "number", "exclusiveMinimum": 0}, "samples": {"type": "array", "items": {"type": "string"}, "maxItems": 32, "default": []}}, "required": ["minimum_allowed_mm"], "additionalProperties": False}
_BLEND_STAGE = {"type": "object", "properties": {"operation": {"type": "string", "enum": ["fillet", "chamfer", "draft"]}, "targets": _STRING_ARRAY, "amount": {"type": "string"}}, "required": ["operation", "targets", "amount"], "additionalProperties": False}


BROWSER_TOOLS = [
    _tool("browser_discover_tools", "Search the optional six-level browser catalog. Ordinary queries omit L1/L3 and semantically invalid tools; explicitly pass semantic_levels=['L1'] or ['L3'] to reveal their exact schemas. Classification guides discovery only and grants no execution authority.", {"query": {"type": "string", "default": ""}, "semantic_levels": {"type": "array", "items": {"type": "string", "enum": ["L1", "L2", "L3", "L4", "L5", "L6"]}, "uniqueItems": True, "maxItems": 6}, "limit": {"type": "integer", "minimum": 1, "maximum": 12, "default": 8}, "include_schema": {"type": "boolean", "default": True}}, mutating=False, seconds=1, network="offline"),
    _tool("browser_invoke_discovered", "Invoke one browser tool returned by browser_discover_tools. Nested tool schemas, dry-run, mutation confirmation, pacing, and acceptance checks remain authoritative; this gateway does not grant permission or bypass a handler gate.", {"name": {"type": "string"}, "arguments": {"type": "object", "additionalProperties": True}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=30, required=["name", "arguments"]),
    _tool("browser_export_step", "Export one explicit Part Studio tab through the live-observed Onshape export dialog to an AP242 millimeter STEP download, exclude hidden entities, require a single non-ZIP STEP result, and persist a browser-owned step-manifest with SHA/provenance. Zero REST quota. Actual UI/download execution requires confirm_mutation=true; dry_run is local.", {"source_tab": {"type": "string"}, "export_id": {"type": "string"}, "document_id": {"type": "string"}, "workspace_id": {"type": "string"}, "element_id": {"type": "string"}, "timeout_ms": {"type": "integer", "minimum": 30000, "maximum": 300000, "default": 120000}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=180, required=["source_tab", "export_id", "document_id", "workspace_id", "element_id"]),
    _tool("browser_geometry_status", "Report browser-mode non-slicer geometry backend readiness without starting the browser or revealing executable paths. If the configured backend is unavailable, perform a bounded search of sibling project virtual environments, global Python environments, and the Windows/WSL counterpart. Reusable versioned candidates are returned by opaque ID; when none exist, agents are instructed to ask before installation. Never installs automatically.", {}, mutating=False, seconds=90, network="offline"),
    _tool("browser_configure_geometry_backend", "Configure browser mode from one opaque candidate_id returned by browser_geometry_status. The candidate is re-discovered before writing, so callers cannot supply an executable or argv. dry_run previews the selection; actual local configuration requires confirm_mutation=true. Never installs dependencies.", {"candidate_id": {"type": "string"}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=90, required=["candidate_id"], network="offline"),
    _tool("browser_build_geometry_package", "Build an offline L6 geometry-analysis package from one browser-owned STEP export manifest. The executable and argv come only from browser module configuration; MCP may select only export_id. Re-verifies STEP provenance/SHA and writes STEP/STL/reports/manifest without browser, REST, or Bambu calls.", {"export_id": {"type": "string"}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=360, required=["export_id"], network="offline"),
    _tool("browser_get_fs_compile_status", "Read the active FeatureScript Ace annotations plus the FeatureScript notice pane and report compiled status, normalized errors, and counts. Read-only and zero REST API quota.", {}, mutating=False, seconds=10),
    _tool("browser_fs_read_notices", "Open the active Feature Studio's FeatureScript notice pane when needed, return normalized warning/error/info rows, and restore the prior pane state. Read-only UI observation and zero REST API quota.", {}, mutating=False, seconds=10),
    _tool("browser_fs_capture_diagnostic", "Persist the active full FeatureScript source and its combined Ace/FeatureScript-notice compile result as a local diagnostic package under onshape_browser_mode/outputs/fs_diagnostics. Experimental, zero REST API quota, and no cloud mutation; the local artifact may contain proprietary source code.", {}, mutating=False, seconds=10),
    _tool("browser_get_fs_symbols", "Open Module outline and return the active FeatureScript symbol inventory with normalized kinds and names. Read-only and zero REST API quota.", {}, mutating=False, seconds=10),
    _tool("browser_fs_goto_definition", "Navigate to a named top-level FeatureScript definition through Module outline and return the verified Ace cursor target.", {"symbol": {"type": "string"}}, mutating=False, seconds=10, required=["symbol"]),
    _tool("browser_fs_insert_snippet", "Invoke the verified Feature Studio 插入代码段 context command at an Ace position and verify the source delta plus Commit dirty state.", {"row": {"type": "integer", "minimum": 0}, "column": {"type": "integer", "minimum": 0}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=10),
    _tool("browser_fs_insert_parameter", "Insert the verified Length parameter template at an Ace position and verify the source delta plus Commit dirty state.", {"row": {"type": "integer", "minimum": 0}, "column": {"type": "integer", "minimum": 0}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=10),
    _tool("browser_fs_toggle_fold", "Fold, unfold, or toggle a FeatureScript Ace fold and return the resulting folded ranges.", {"action": {"type": "string", "enum": ["toggle", "fold", "unfold"], "default": "toggle"}, "row": {"type": "integer", "minimum": 0}}, mutating=False, seconds=5),
    _tool("browser_edit_feature_parameters", "Open a custom feature dialog, update named scalar fields, verify readback and persistence, accept, and require an error-free feature row.", {"feature_name": {"type": "string"}, "parameters": {"type": "object", "additionalProperties": {}}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=30, required=["feature_name", "parameters"]),
    _tool("browser_fs_watch_part_studio", "Select the exact watched/configured Part Studio through the Feature Studio toolbar dropdown and verify the toolbar readback.", {"part_studio": {"type": "string"}, "mode": {"type": "string", "enum": ["watch", "configure"], "default": "watch"}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=15, required=["part_studio"]),
    _tool("browser_open_doc_menu", "Open the document-name menu, return its item inventory, and optionally trigger one exact command.", {"command": {"type": "string", "default": ""}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=10),
    _tool("browser_set_panel_filter", "Set the left document-panel filter and verify the trusted input value and visible tree count.", {"query": {"type": "string"}}, mutating=False, seconds=10, required=["query"]),
    _tool("browser_toggle_left_panel", "Collapse, expand, or toggle the left panel through its splitter and verify the resulting width.", {"target": {"type": "string", "enum": ["toggle", "show", "hide"], "default": "toggle"}}, mutating=False, seconds=10),
    _tool("browser_read_selection_preview", "Read a visible left-panel selection or tab-preview card and return its text and labeled fields.", {}, mutating=False, seconds=5),
    _tool("browser_element_context_menu", "Open an id-addressed document-element tab context menu and return its visible item list.", {"element_id": {"type": "string"}}, mutating=False, seconds=10, required=["element_id"]),
    _tool("browser_duplicate_element", "Duplicate an id-addressed document element through its exact context-menu command and verify exactly one new tab id.", {"element_id": {"type": "string"}, "new_name": {"type": "string", "default": ""}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=30, required=["element_id"]),
    _tool("browser_notifications_status", "Read the notification badge count and optionally open and read the notification drawer.", {"open_drawer": {"type": "boolean", "default": False}}, mutating=False, seconds=10),
    _tool("browser_share_document", "Open the document share dialog and return its visible text without changing permissions.", {}, mutating=False, seconds=10),
    _tool("browser_view_orientation", "Read the current view-cube visual state or set a standard camera orientation and verify the cube state changes.", {"orientation": {"type": "string", "enum": ["current", "front", "back", "top", "bottom", "left", "right", "isometric"], "default": "current"}}, mutating=False, seconds=10),
    _tool("browser_drawing_insert_views", "Create a drawing from an exact Part Studio part row, select a semantic view layout, and require drawing-view geometry evidence.", {"part_name": {"type": "string"}, "view_layout": {"type": "string", "enum": ["four", "single", "iso"], "default": "four"}, "part_studio_tab": {"type": "string", "default": ""}, "template": {"type": "string", "default": ""}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=60, required=["part_name"]),
    _tool("browser_draw_part_with_views", "Create verified drawing views from a part, add one or more requested dimensions, and fail if any stage lacks acceptance evidence. Use browser_drawing_insert_views when dimensions are not required.", {"part_name": {"type": "string"}, "view_layout": {"type": "string", "enum": ["four", "single", "iso"], "default": "four"}, "part_studio_tab": {"type": "string", "default": ""}, "template": {"type": "string", "default": ""}, "dimensions": {"type": "array", "items": {"type": "object", "properties": _DIMENSION_PROPERTIES, "additionalProperties": False}, "minItems": 1}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=120, required=["part_name", "dimensions"]),
    _tool("browser_print_orientation_check", "Deprecated compatibility result: returns semantically invalid/unassessable without a browser action because Onshape draft analysis is not an FDM orientation engine.", {"body_name": {"type": "string"}, "build_direction": {"type": "string", "enum": ["+x", "-x", "+y", "-y", "+z", "-z"], "default": "+z"}, "max_overhang_angle_degrees": {"type": "number", "minimum": 0, "maximum": 90, "default": 45}}, mutating=False, seconds=1, required=["body_name"], network="offline"),
    _tool("browser_wall_thickness_report", "Read sampled browser measurements for a named body, report the minimum in millimeters, and never claim an unverified global minimum.", {"body_name": {"type": "string"}, "minimum_allowed_mm": {"type": "number", "exclusiveMinimum": 0}, "samples": {"type": "array", "items": {"type": "string"}, "maxItems": 32, "default": []}}, mutating=False, seconds=15, required=["body_name", "minimum_allowed_mm"]),
    _tool("browser_apply_blend", "Apply a fillet, chamfer, or draft to semantic targets and require amount readback plus an exact new error-free history row.", {"operation": {"type": "string", "enum": ["fillet", "chamfer", "draft"], "default": "fillet"}, "targets": _STRING_ARRAY, "amount": {"type": "string"}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=45, required=["targets", "amount"]),
    _tool("browser_print_optimize_part", "Deprecated compatibility workflow: validates inputs, then stops before browser/model mutation because its draft-based FDM orientation dependency is semantically invalid.", {"body_name": {"type": "string"}, "blend": _BLEND_STAGE, "orientation": _ORIENTATION_STAGE, "wall": _WALL_STAGE, "dry_run": _DRY}, mutating=False, seconds=1, required=["body_name", "orientation", "wall"], network="offline"),
    _tool("browser_spiral_ridge", "Generate bounded helix+sweep FeatureScript, deploy and apply it through the browser, and verify the resulting feature and part.", {"base_radius_mm": {"type": "number", "minimum": 0.1, "maximum": 10000}, "pitch_mm": {"type": "number", "minimum": 0.1, "maximum": 10000}, "ridge_width_mm": {"type": "number", "minimum": 0.05, "maximum": 1000}, "ridge_height_mm": {"type": "number", "minimum": 0.05, "maximum": 1000}, "length_mm": {"type": "number", "minimum": 0.1, "maximum": 100000}, "clockwise": {"type": "boolean", "default": True}, "feature_studio_tab": {"type": "string", "default": "Spiral ridge FS"}, "part_studio_tab": {"type": "string", "default": "Spiral ridge PS"}, "create_version": {"type": "boolean", "default": True}, "version_name": {"type": "string", "default": ""}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=120, required=["base_radius_mm", "pitch_mm", "ridge_width_mm", "ridge_height_mm", "length_mm"]),
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
    _tool("browser_draw_part", "Deprecated compatibility workflow: create a generic Drawing from a source tab and add one or more dimensions. It rejects empty dimensions before mutation; prefer browser_drawing_insert_views or browser_draw_part_with_views for verified part views.", {"source_tab": {"type": "string"}, "template": {"type": "string", "default": ""}, "dimensions": {"type": "array", "items": {"type": "object", "properties": _DIMENSION_PROPERTIES, "additionalProperties": False}, "minItems": 1}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=90, required=["source_tab", "dimensions"]),
    _tool("browser_run_project", "Execute a validated browser project with checkpoints and resume. Legacy v1 runs flat steps; v2 runs setup plus a DAG of one or more independently asserted L6 deliverables and records a manifest for each accepted node.", {"project": {"type": "string", "default": "module-interface-verification"}, "resume": {"type": "boolean", "default": False}, "dry_run": _DRY, "confirm_mutation": _CONFIRM}, mutating=True, seconds=600),
    _tool("browser_capture_screenshot", "Capture the current browser page (or a scoped element) to a PNG file so the caller or the visual tools (read_image / vision_glance / vision_ground) can inspect it. Read-only; zero REST API quota; consumes one real browser action subject to the pacing guard.", {"selector": {"type": "string", "default": "", "description": "CSS selector scoped to one element's bounding box; empty captures the whole viewport."}, "frame_url": _FRAME, "index": {"type": "integer", "default": 0, "minimum": 0}, "full_page": {"type": "boolean", "default": False, "description": "Capture the whole scrollable page instead of the viewport."}, "output_dir": {"type": "string", "default": "dev/screenshots", "description": "Relative (or repo-rooted) output directory; must stay inside the repository root."}, "filename": {"type": "string", "default": "", "description": "PNG basename; a UTC timestamp is appended when empty."}, "data_url": {"type": "boolean", "default": False, "description": "Also return the image as a base64 data URL."}, "dry_run": _DRY}, mutating=False, seconds=10),
]

BROWSER_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "browser_discover_tools": browser_discover_tools,
    "browser_invoke_discovered": browser_invoke_discovered,
    "browser_export_step": browser_export_step,
    "browser_geometry_status": browser_geometry_status,
    "browser_configure_geometry_backend": browser_configure_geometry_backend,
    "browser_build_geometry_package": browser_build_geometry_package,
    "browser_get_fs_compile_status": browser_get_fs_compile_status,
    "browser_fs_read_notices": browser_fs_read_notices,
    "browser_fs_capture_diagnostic": browser_fs_capture_diagnostic,
    "browser_get_fs_symbols": browser_get_fs_symbols,
    "browser_fs_goto_definition": browser_fs_goto_definition,
    "browser_fs_insert_snippet": browser_fs_insert_snippet,
    "browser_fs_insert_parameter": browser_fs_insert_parameter,
    "browser_fs_toggle_fold": browser_fs_toggle_fold,
    "browser_edit_feature_parameters": browser_edit_feature_parameters,
    "browser_fs_watch_part_studio": browser_fs_watch_part_studio,
    "browser_open_doc_menu": browser_open_doc_menu,
    "browser_set_panel_filter": browser_set_panel_filter,
    "browser_toggle_left_panel": browser_toggle_left_panel,
    "browser_read_selection_preview": browser_read_selection_preview,
    "browser_element_context_menu": browser_element_context_menu,
    "browser_duplicate_element": browser_duplicate_element,
    "browser_notifications_status": browser_notifications_status,
    "browser_share_document": browser_share_document,
    "browser_view_orientation": browser_view_orientation,
    "browser_drawing_insert_views": browser_drawing_insert_views,
    "browser_draw_part_with_views": browser_draw_part_with_views,
    "browser_print_orientation_check": browser_print_orientation_check,
    "browser_wall_thickness_report": browser_wall_thickness_report,
    "browser_apply_blend": browser_apply_blend,
    "browser_print_optimize_part": browser_print_optimize_part,
    "browser_spiral_ridge": browser_spiral_ridge,
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
