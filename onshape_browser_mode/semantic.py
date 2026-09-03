"""Layered semantic browser operations built on page objects."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from onshape_browser_mode import actions, diagnostics, selectors
from onshape_browser_mode.pages import AssemblyPage, DrawingPage

_PARTS_RE = re.compile(r"零件数\s*\((\d+)\)")


def parse_part_summary(parts_text: str) -> dict[str, Any]:
    """Parse the Part Studio's localized part count and visible part names."""
    match = _PARTS_RE.search(parts_text or "")
    if not match:
        return {"parts": 0, "partNames": [], "partsText": parts_text or ""}
    count = int(match.group(1))
    remainder = (parts_text or "")[match.end():].strip()
    if count == 1 and remainder:
        names = [remainder]
        names_parsed = True
    elif re.search(r"\s{2,}|\n", remainder):
        names = [name.strip() for name in re.split(r"\s{2,}|\n", remainder) if name.strip()]
        names_parsed = len(names) == count
    else:
        names = []
        names_parsed = False
    return {
        "parts": count, "partNames": names, "partNamesParsed": names_parsed,
        "partsText": parts_text,
    }


def _open_tab(page: Any, name: str) -> bool:
    if not name:
        return True
    tabs = actions.list_document_tabs(page).get("tabs", [])
    matched = next((tab for tab in tabs if tab.get("name") == name), None)
    if not matched:
        return False
    tab_id = matched.get("id", "")
    tab = page.locator(
        f'{selectors.TAB_BAR_TAB}[data-id="{tab_id}"]' if tab_id else selectors.TAB_BAR_TAB
    )
    if not tab_id:
        tab = tab.filter(has_text=name)
    if tab.count() == 0:
        return False
    actions.dismiss_stale_context_menu(page)
    tab.first.click()
    try:
        page.locator(selectors.ASM_INSERT_BUTTON).first.wait_for(
            state="visible", timeout=30_000
        )
    except Exception:
        return False
    return True


def read_instance_visibility(
    page: Any, names: list[str], instance_selector: str,
) -> dict[str, Any]:
    """Verify names only inside the caller-selected Assembly instance rows."""
    if not instance_selector:
        raise ValueError("instance_selector is required")
    visible = []
    missing = []
    rows = page.locator(instance_selector)
    for name in names:
        if rows.filter(has_text=name).count() > 0:
            visible.append(name)
        else:
            missing.append(name)
    return {
        "visibleInstances": visible, "missingInstances": missing,
        "instanceSelector": instance_selector,
    }


def insert_assembly_instances(
    page: Any,
    instance_names: list[str],
    assembly_tab: str = "",
    instance_selector: str = selectors.ASM_INSTANCE_ROW,
    source_names: list[str] | None = None,
) -> dict[str, Any]:
    """Insert named Part Studios and verify their resulting instance names."""
    if assembly_tab and not _open_tab(page, assembly_tab):
        return {"inserted": False, "reason": f"assembly tab {assembly_tab!r} not found"}
    source_names = source_names or instance_names
    if len(source_names) != len(instance_names):
        return {"inserted": False, "reason": "source_names and instance_names must have equal length"}
    assembly = AssemblyPage(page)
    try:
        assembly.insert_button().click()
        assembly.insert_dialog().wait_for(state="visible", timeout=15_000)
        selected = []
        for source_name in source_names:
            row = assembly.insert_row(source_name)
            if row.count() == 0:
                return {
                    "inserted": False,
                    "reason": f"assembly source {source_name!r} not found",
                    "selected": selected,
                }
            row.click()
            selected.append(source_name)
        assembly.accept_insert().click()
        page.wait_for_timeout(3000)
    except Exception as exc:  # noqa: BLE001 - structured browser failure
        return {"inserted": False, "reason": f"{type(exc).__name__}: {exc}"}
    visibility = read_instance_visibility(page, instance_names, instance_selector)
    return {
        "inserted": not visibility["missingInstances"],
        "selected": selected,
        **visibility,
        "pageUrl": page.url,
    }


def _select_instances(
    page: Any, names: list[str], instance_selector: str,
) -> tuple[list[str], list[str], Any | None]:
    if not instance_selector:
        raise ValueError("instance_selector is required")
    selected: list[str] = []
    missing: list[str] = []
    first = None
    rows = page.locator(instance_selector)
    for index, name in enumerate(names):
        locator = rows.filter(has_text=name)
        if locator.count() == 0:
            missing.append(name)
            continue
        target = locator.first
        target.click(modifiers=[] if index == 0 else ["Control"])
        selected.append(name)
        if first is None:
            first = target
    return selected, missing, first


def fix_instances(page: Any, instance_names: list[str], assembly_tab: str = "", instance_selector: str = selectors.ASM_INSTANCE_ROW) -> dict[str, Any]:
    """Select assembly instances and invoke the documented 固定 context action."""
    if assembly_tab and not _open_tab(page, assembly_tab):
        return {"fixed": False, "reason": f"assembly tab {assembly_tab!r} not found"}
    selected, missing, first = _select_instances(page, instance_names, instance_selector)
    if missing or first is None:
        return {"fixed": False, "selected": selected, "missing": missing}
    try:
        first.click(button="right")
        item = page.locator(selectors.TAB_CONTEXT_MENU_ITEM).filter(has_text="固定")
        if item.count() == 0:
            return {"fixed": False, "selected": selected, "reason": "固定 menu item not found"}
        item.first.click()
        page.wait_for_timeout(1500)
    except Exception as exc:  # noqa: BLE001
        return {"fixed": False, "selected": selected, "reason": str(exc)}
    return {"fixed": True, "selected": selected, "verification": "action-triggered"}


def group_instances(page: Any, instance_names: list[str], assembly_tab: str = "", instance_selector: str = selectors.ASM_INSTANCE_ROW) -> dict[str, Any]:
    """Select assembly instances and invoke the toolbar 分组 action."""
    if assembly_tab and not _open_tab(page, assembly_tab):
        return {"grouped": False, "reason": f"assembly tab {assembly_tab!r} not found"}
    selected, missing, _ = _select_instances(page, instance_names, instance_selector)
    if missing:
        return {"grouped": False, "selected": selected, "missing": missing}
    try:
        tool = page.locator(selectors.PS_TOOLBAR_ITEM).filter(has_text="分组")
        if tool.count() == 0:
            return {"grouped": False, "selected": selected, "reason": "分组 tool not found"}
        tool.first.click()
        page.wait_for_timeout(1500)
    except Exception as exc:  # noqa: BLE001
        return {"grouped": False, "selected": selected, "reason": str(exc)}
    return {"grouped": True, "selected": selected, "verification": "action-triggered"}


def create_drawing(page: Any, source_tab: str, template: str = "") -> dict[str, Any]:
    """Create a Drawing and complete the source/template dialog when exposed."""
    triggered = actions.create_document_tab(page, "Drawing")
    if triggered.get("created"):
        drawing_frames = [
            scope_url(frame) for frame in getattr(page, "frames", [])
            if selectors.DRAWING_FRAME_URL_PREFIX in str(getattr(frame, "url", ""))
        ]
        return {
            "created": bool(drawing_frames), "trigger": triggered,
            "drawingFrames": drawing_frames, "pageUrl": page.url,
            "reason": None if drawing_frames else "drawing tab exists but drawing frame is not ready",
        }
    try:
        dialog = page.locator(selectors.DRAWING_CREATE_DIALOG)
        if dialog.count() == 0:
            return {"created": False, "reason": "drawing creation dialog not found"}
        source = dialog.get_by_text(source_tab, exact=False)
        if source.count() == 0:
            return {
                "created": False,
                "triggered": triggered.get("triggered", False),
                "reason": f"drawing source {source_tab!r} not found",
                "trigger": triggered,
            }
        source.first.click()
        if template:
            choice = dialog.get_by_text(template, exact=False)
            if choice.count() == 0:
                return {"created": False, "reason": f"drawing template {template!r} not found"}
            choice.first.click()
        accept = dialog.locator(selectors.DIALOG_ACCEPT)
        if accept.count() == 0:
            return {"created": False, "reason": "drawing create confirmation not found"}
        accept.first.click()
        page.wait_for_timeout(3000)
    except Exception as exc:  # noqa: BLE001
        return {"created": False, "reason": f"{type(exc).__name__}: {exc}"}
    tabs = actions.list_document_tabs(page)
    drawing_frames = [
        scope_url(frame) for frame in getattr(page, "frames", [])
        if selectors.DRAWING_FRAME_URL_PREFIX in str(getattr(frame, "url", ""))
    ]
    return {
        "created": bool(drawing_frames),
        "sourceTab": source_tab,
        "template": template,
        "drawingFrames": drawing_frames,
        **tabs,
        "pageUrl": page.url,
    }


def add_drawing_dimension(
    page: Any,
    *,
    tool_selector: str = "",
    geometry_selectors: list[str] | None = None,
    placement_selector: str = "",
    verification_selector: str = "",
    tool_key: str = "",
    canvas_selector: str = "canvas",
    canvas_index: int = 0,
    geometry_points: list[dict[str, float]] | None = None,
    placement_point: dict[str, float] | None = None,
    frame_url: str = selectors.DRAWING_FRAME_URL_PREFIX,
) -> dict[str, Any]:
    """Drive and verify a DOM- or canvas-configured Drawing dimension gesture."""
    geometry_selectors = geometry_selectors or []
    geometry_points = geometry_points or []
    try:
        drawing = DrawingPage(page, frame_url)
        if geometry_points:
            canvas = drawing.scope.locator(canvas_selector).nth(canvas_index)
            canvas.wait_for(state="visible", timeout=30_000)
            if not tool_key or not geometry_points or placement_point is None:
                raise ValueError("canvas mode requires tool_key, geometry_points, and placement_point")
            before_sha = hashlib.sha256(canvas.screenshot()).hexdigest()
            canvas.focus()
            canvas.press(tool_key)
            page.wait_for_timeout(300)
            for point in geometry_points:
                canvas.click(position=point)
            canvas.click(position=placement_point)
            canvas.press("Escape")
            page.mouse.move(1, 1)
            page.wait_for_timeout(750)
            after_sha = hashlib.sha256(canvas.screenshot()).hexdigest()
            page.wait_for_timeout(500)
            stable_sha = hashlib.sha256(canvas.screenshot()).hexdigest()
            stable_change = before_sha != stable_sha and after_sha == stable_sha
            return {
                "dimensionAdded": stable_change,
                "actionTriggered": True,
                "toolActivation": "key-pressed-after-canvas-focus",
                "verification": "stable-canvas-screenshot-changed",
                "beforeCanvasSha256": before_sha,
                "afterCanvasSha256": stable_sha,
                "postRenderStable": after_sha == stable_sha,
                "geometryCount": len(geometry_points),
                "frameUrl": drawing.url,
                "state": drawing.state(),
            }

        before_count = drawing.scope.locator(verification_selector).count()
        drawing.scope.locator(tool_selector).first.click()
        for geometry_selector in geometry_selectors:
            drawing.scope.locator(geometry_selector).first.click()
        if placement_selector:
            drawing.scope.locator(placement_selector).first.click()
        after_count = drawing.scope.locator(verification_selector).count()
    except Exception as exc:  # noqa: BLE001
        return {"dimensionAdded": False, "reason": f"{type(exc).__name__}: {exc}"}
    return {
        "dimensionAdded": after_count > before_count,
        "actionTriggered": True,
        "verification": "selector-count-increased",
        "verificationSelector": verification_selector,
        "beforeCount": before_count,
        "afterCount": after_count,
        "geometryCount": len(geometry_selectors),
        "frameUrl": drawing.url,
        "state": drawing.state(),
    }


def delete_element(page: Any, element_id: str) -> dict[str, Any]:
    """Delete one visible document element through the shared exact-ID core."""
    return actions.delete_element_by_id(page, element_id)


def deploy_featurescript(page: Any, script: str) -> dict[str, Any]:
    """Write, commit, and verify FeatureScript in the active editor."""
    before = actions.read_featurescript_editor(page)
    if before is None:
        return {"deployed": False, "reason": "FeatureScript editor not found"}
    written = actions.write_featurescript_editor(page, script)
    if not written.get("ok"):
        return {"deployed": False, "reason": written.get("error", "editor write failed")}
    commit = actions.click_commit(page)
    verified_source = actions.read_featurescript_editor(page)
    compile_status = actions.read_featurescript_compile_status(page)
    verified = verified_source == script
    committed = (
        bool(commit.get("clicked"))
        and (commit.get("before") or {}).get("disabled") is False
        and (commit.get("after") or {}).get("disabled") is True
    )
    compiled = bool(compile_status.get("compiled"))
    try:
        diagnostic_capture = diagnostics.save_featurescript_diagnostic(
            source=verified_source if isinstance(verified_source, str) else script,
            compile_status=compile_status,
            page_url=getattr(page, "url", ""),
            phase="semantic-deploy",
        )
    except Exception as exc:  # noqa: BLE001 - deployment truth remains independent
        diagnostic_capture = {
            "captured": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    return {
        "deployed": committed and verified and compiled,
        "verified": verified,
        "commitAccepted": committed,
        "compiled": compiled,
        "annotationCount": compile_status.get("annotationCount", 0),
        "noticeCount": compile_status.get("noticeCount", 0),
        "errors": compile_status.get("errors", []),
        "notices": compile_status.get("notices", []),
        "diagnosticCapture": diagnostic_capture,
        "beforeLength": len(before),
        "afterLength": written.get("length"),
        "commit": commit,
    }


def build_part(page: Any, feature_name: str, part_studio_tab: str = "") -> dict[str, Any]:
    """Apply a custom feature and return normalized Part Studio acceptance data."""
    inserted = actions.insert_custom_feature(page, feature_name, part_studio_tab or None)
    features = inserted.get("features") or actions.read_partstudio_features(page)
    summary = parse_part_summary(str(features.get("partsText", "")))
    feature_present = any(
        item.get("isUserFeature") and feature_name.lower() in str(item.get("name", "")).lower()
        for item in features.get("features", [])
    )
    return {
        "built": bool(inserted.get("inserted")) and feature_present and summary["parts"] > 0,
        "featurePresent": feature_present,
        "insert": inserted,
        "features": features,
        **summary,
    }


def assemble(
    page: Any,
    instance_names: list[str],
    assembly_tab: str = "",
    fix: bool = False,
    group: bool = False,
    instance_selector: str = selectors.ASM_INSTANCE_ROW,
    source_names: list[str] | None = None,
) -> dict[str, Any]:
    """Insert and optionally fix/group assembly instances."""
    inserted = insert_assembly_instances(
        page, instance_names, assembly_tab, instance_selector, source_names
    )
    fixed = fix_instances(page, instance_names, assembly_tab, instance_selector) if fix and inserted.get("inserted") else None
    grouped = group_instances(page, instance_names, assembly_tab, instance_selector) if group and inserted.get("inserted") else None
    return {
        "assembled": bool(inserted.get("inserted")),
        "configurationTriggered": (not fix or bool(fixed and fixed.get("fixed"))) and (not group or bool(grouped and grouped.get("grouped"))),
        "insert": inserted,
        "fix": fixed,
        "group": grouped,
    }


def draw_part(
    page: Any,
    *,
    source_tab: str,
    template: str = "",
    dimensions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compatibility workflow for a generic drawing plus required dimensions."""
    if not dimensions:
        return {
            "drawn": False,
            "browserActionPerformed": False,
            "reason": "at least one dimension is required before creating a drawing",
            "drawing": None,
            "dimensions": [],
        }
    drawing = create_drawing(page, source_tab, template)
    if not drawing.get("created"):
        return {"drawn": False, "drawing": drawing, "dimensions": []}
    dimension_results = []
    for dimension in dimensions or []:
        dimension_results.append(add_drawing_dimension(page, **dimension))
    try:
        state = DrawingPage(page).state()
        frame_url = DrawingPage(page).url
    except Exception as exc:  # noqa: BLE001
        return {
            "drawn": False,
            "drawing": drawing,
            "dimensions": dimension_results,
            "reason": f"drawing frame unreadable: {exc}",
        }
    dimensions_ok = bool(dimension_results) and all(
        result.get("dimensionAdded") for result in dimension_results
    )
    return {
        "drawn": dimensions_ok,
        "drawing": drawing,
        "dimensions": dimension_results,
        "frameUrl": frame_url,
        "state": state,
    }
