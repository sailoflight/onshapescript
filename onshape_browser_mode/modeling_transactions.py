"""Drawing, printability, native-feature, and modeling workflow transactions."""

from __future__ import annotations

import re
import struct
import zlib
from typing import Any

from onshape_browser_mode import actions, selectors, semantic
from onshape_browser_mode.pages import DrawingPage


PART_ROW = selectors.PS_PART_ROW
DRAWING_DIALOG = selectors.DRAWING_CREATE_DIALOG
DRAWING_VIEW_NODES = selectors.DRAWING_VIEW_NODES
ANALYSIS_DIALOG = selectors.ANALYSIS_DIALOG
QUANTITY_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(mm|cm|m|in|inch|deg|°)?", re.I)


def _exact_visible_text(locator: Any, choices: list[str]) -> Any | None:
    normalized = {item.strip() for item in choices}
    matches = []
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible() and candidate.inner_text().strip() in normalized:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _png_ink_metrics(data: bytes) -> dict[str, Any]:
    """Decode an 8-bit Playwright PNG and measure ink away from sheet chrome."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return {"readable": False, "reason": "not a PNG"}
    offset = 8
    width = height = bit_depth = color_type = interlace = 0
    compressed = bytearray()
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if not width or not height or bit_depth != 8 or channels is None or interlace:
        return {"readable": False, "reason": "unsupported PNG encoding", "width": width, "height": height}
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        return {"readable": False, "reason": f"PNG inflate failed: {exc}"}
    stride = width * channels
    expected = height * (stride + 1)
    if len(raw) != expected:
        return {"readable": False, "reason": "unexpected PNG scanline size", "width": width, "height": height}

    rows: list[bytearray] = []
    cursor = 0
    prior = bytearray(stride)
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        encoded = raw[cursor:cursor + stride]
        cursor += stride
        decoded = bytearray(stride)
        for index, value in enumerate(encoded):
            left = decoded[index - channels] if index >= channels else 0
            up = prior[index]
            upper_left = prior[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                estimate = left + up - upper_left
                distances = (abs(estimate - left), abs(estimate - up), abs(estimate - upper_left))
                predictor = (left, up, upper_left)[distances.index(min(distances))]
            else:
                return {"readable": False, "reason": f"unsupported PNG filter {filter_type}"}
            decoded[index] = (value + predictor) & 0xFF
        rows.append(decoded)
        prior = decoded

    x0, x1 = int(width * 0.05), int(width * 0.95)
    y0, y1 = int(height * 0.05), int(height * 0.78)
    tiles_x, tiles_y = 6, 3
    tile_counts = [0] * (tiles_x * tiles_y)
    ink = 0
    pixels = max(1, (x1 - x0) * (y1 - y0))
    for y in range(y0, y1):
        row = rows[y]
        tile_y = min(tiles_y - 1, (y - y0) * tiles_y // max(1, y1 - y0))
        for x in range(x0, x1):
            index = x * channels
            if color_type in {0, 4}:
                red = green = blue = row[index]
                alpha = row[index + 1] if channels == 2 else 255
            else:
                red, green, blue = row[index:index + 3]
                alpha = row[index + 3] if channels == 4 else 255
            if alpha > 0 and max(red, green, blue) < 190:
                ink += 1
                tile_x = min(tiles_x - 1, (x - x0) * tiles_x // max(1, x1 - x0))
                tile_counts[tile_y * tiles_x + tile_x] += 1
    tile_pixels = pixels / (tiles_x * tiles_y)
    active_tiles = sum(count >= max(20, int(tile_pixels * 0.0007)) for count in tile_counts)
    sorted_tiles = sorted(tile_counts)
    median_tile = sorted_tiles[len(sorted_tiles) // 2] if sorted_tiles else 0
    peak_to_median = max(tile_counts, default=0) / max(1, median_tile)
    return {
        "readable": True,
        "width": width,
        "height": height,
        "interiorInkPixels": ink,
        "interiorInkRatio": ink / pixels,
        "activeInkTiles": active_tiles,
        "medianTileInk": median_tile,
        "peakToMedianInk": peak_to_median,
        "tileInkCounts": tile_counts,
    }


def _open_named_tab(page: Any, name: str) -> bool:
    if not name:
        return True
    tabs = actions.list_document_tabs(page).get("tabs", [])
    match = next((item for item in tabs if item.get("name") == name), None)
    if not match:
        return False
    tab_id = match.get("id", "")
    tab = page.locator(f'{selectors.TAB_BAR_TAB}[data-id="{tab_id}"]') if tab_id else page.locator(selectors.TAB_BAR_TAB).filter(has_text=name)
    actions.dismiss_stale_context_menu(page)
    tab.first.click()
    page.wait_for_timeout(250)
    return True


def _drawing_state(page: Any, frame_url: str) -> dict[str, Any]:
    try:
        drawing = DrawingPage(page, frame_url)
        state = drawing.state()
        view_count = drawing.scope.locator(DRAWING_VIEW_NODES).count()
        canvas_bytes = []
        canvas_metrics = []
        canvases = drawing.scope.locator("canvas")
        for index in range(min(canvases.count(), 8)):
            try:
                screenshot = canvases.nth(index).screenshot()
                canvas_bytes.append(len(screenshot))
                canvas_metrics.append(_png_ink_metrics(screenshot))
            except Exception as exc:  # noqa: BLE001 - one protected/WebGL canvas is allowed
                canvas_bytes.append(0)
                canvas_metrics.append({"readable": False, "reason": f"{type(exc).__name__}: {exc}"})
        main_metrics = canvas_metrics[0] if canvas_metrics else {"readable": False, "reason": "no canvas"}
        return {
            "readable": True,
            "frameUrl": drawing.url,
            "viewNodeCount": view_count,
            "canvasScreenshotBytes": canvas_bytes,
            "canvasMetrics": canvas_metrics,
            "mainCanvasMetrics": main_metrics,
            **state,
        }
    except Exception as exc:  # noqa: BLE001
        return {"readable": False, "reason": f"{type(exc).__name__}: {exc}"}


def drawing_insert_views(
    page: Any,
    *,
    part_name: str,
    view_layout: str,
    part_studio_tab: str = "",
    template: str = "",
    frame_url: str = selectors.DRAWING_FRAME_URL_PREFIX,
) -> dict[str, Any]:
    """Create a drawing from a part-row context menu and require view evidence."""
    if part_studio_tab and not _open_named_tab(page, part_studio_tab):
        return {"viewsInserted": False, "reason": f"Part Studio tab {part_studio_tab!r} not found"}
    part = page.locator(PART_ROW).filter(has_text=part_name)
    if part.count() == 0:
        return {"viewsInserted": False, "reason": f"part {part_name!r} not found"}
    before_tabs = actions.list_document_tabs(page).get("tabs", [])
    part.first.click(button="right")
    item = _exact_visible_text(
        page.locator(selectors.TAB_CONTEXT_MENU_ITEM),
        [
            f"创建 {part_name} 的工程图…",
            f"创建 {part_name} 的工程图...",
            f"Create drawing of {part_name}…",
            f"Create drawing of {part_name}...",
        ],
    )
    if item is None:
        return {"viewsInserted": False, "reason": "exact part drawing context command not found"}
    item.click()
    dialog = page.locator(DRAWING_DIALOG).first
    try:
        dialog.wait_for(state="visible", timeout=10_000)
    except Exception as exc:  # noqa: BLE001
        return {"viewsInserted": False, "reason": f"drawing dialog did not open: {exc}"}
    layout_labels = {
        "four": ["四个视图", "Four views"],
        "single": ["单个视图", "Single view"],
        "iso": ["等轴测", "Isometric"],
    }[view_layout]
    layout_selected = False
    for label in layout_labels:
        option = dialog.get_by_text(label, exact=False)
        if option.count() > 0:
            option.first.click()
            layout_selected = True
            break
    if template:
        option = dialog.get_by_text(template, exact=False)
        if option.count() > 0:
            option.first.click()
    accept = dialog.locator(selectors.DIALOG_ACCEPT)
    if accept.count() == 0:
        accept = page.locator(selectors.DIALOG_ACCEPT)
    if accept.count() == 0:
        return {"viewsInserted": False, "layoutSelected": layout_selected, "reason": "drawing dialog accept button not found"}
    accept.first.click()
    page.wait_for_timeout(3_000)
    state = _drawing_state(page, frame_url)
    after_tabs = actions.list_document_tabs(page).get("tabs", [])
    before_ids = {item.get("id") for item in before_tabs if item.get("id")}
    new_tabs = [item for item in after_tabs if item.get("id") and item.get("id") not in before_ids]
    tab_evidence = len(new_tabs) == 1 and len(after_tabs) == len(before_tabs) + 1
    metrics = state.get("mainCanvasMetrics", {})
    pixel_evidence = bool(
        metrics.get("readable")
        and metrics.get("interiorInkRatio", 0) >= 0.008
        and metrics.get("peakToMedianInk", 0) >= 2.0
    )
    dom_evidence = state.get("viewNodeCount", 0) > 0
    view_evidence = dom_evidence or pixel_evidence
    return {
        "viewsInserted": bool(layout_selected and tab_evidence and state.get("readable") and view_evidence),
        "partName": part_name,
        "viewLayout": view_layout,
        "layoutSelected": layout_selected,
        "newTabs": new_tabs,
        "tabEvidence": tab_evidence,
        "viewEvidence": view_evidence,
        "viewEvidenceMethod": "dom" if dom_evidence else ("pixel-ink-distribution" if pixel_evidence else "none"),
        "drawingState": state,
    }


def draw_part_with_views(
    page: Any,
    *,
    part_name: str,
    view_layout: str,
    part_studio_tab: str = "",
    template: str = "",
    frame_url: str = selectors.DRAWING_FRAME_URL_PREFIX,
    dimensions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Insert verified drawing views, then add every required dimension."""
    if not dimensions:
        return {
            "drawn": False,
            "browserActionPerformed": False,
            "reason": "at least one dimension is required; use drawing_insert_views for views only",
            "views": None,
            "dimensions": [],
        }
    views = drawing_insert_views(
        page,
        part_name=part_name,
        view_layout=view_layout,
        part_studio_tab=part_studio_tab,
        template=template,
        frame_url=frame_url,
    )
    if not views.get("viewsInserted"):
        return {"drawn": False, "views": views, "dimensions": []}
    dimension_results = [semantic.add_drawing_dimension(page, **item) for item in dimensions or []]
    dimensions_ok = all(bool(item.get("dimensionAdded")) for item in dimension_results)
    return {
        "drawn": bool(views.get("viewsInserted")) and dimensions_ok,
        "viewsInserted": True,
        "views": views,
        "dimensions": dimension_results,
        "dimensionsRequested": len(dimensions or []),
        "dimensionsAdded": sum(bool(item.get("dimensionAdded")) for item in dimension_results),
    }


def _select_body(page: Any, body_name: str) -> bool:
    row = page.locator(PART_ROW).filter(has_text=body_name)
    if row.count() != 1:
        return False
    row.first.click()
    return True


def _read_visible_analysis(page: Any) -> dict[str, Any]:
    result = page.evaluate(
        """
        (selector) => {
          const dialogs = Array.from(document.querySelectorAll(selector)).filter(el => el.offsetParent);
          const measurements = Array.from(document.querySelectorAll('.element-measurement-area, .primary-measurements'))
            .filter(el => el.offsetParent);
          const text = [...dialogs, ...measurements].map(el => (el.innerText || el.textContent || '').trim()).filter(Boolean).join('\n');
          return {text: text.slice(0, 4000), dialogCount: dialogs.length, measurementCount: measurements.length};
        }
        """,
        ANALYSIS_DIALOG,
    )
    return result if isinstance(result, dict) else {"text": "", "dialogCount": 0, "measurementCount": 0}


def _quantities(text: str) -> list[dict[str, Any]]:
    values = []
    for match in QUANTITY_RE.finditer(text or ""):
        values.append({"value": float(match.group(1)), "unit": (match.group(2) or "").lower()})
    return values


def draft_angle_proxy(
    page: Any,
    *,
    body_name: str,
    build_direction: str,
    max_overhang_angle_degrees: float,
) -> dict[str, Any]:
    """Read Onshape draft-analysis UI as a manufacturing-angle proxy only."""
    if not _select_body(page, body_name):
        return {"draftAngleObserved": False, "assessable": False, "reason": f"body {body_name!r} not found"}
    button = page.locator("button.analysis-button")
    if button.count() != 1:
        return {"draftAngleObserved": False, "assessable": False, "reason": "surface analysis button not found uniquely"}
    button.first.click()
    popup = page.locator(selectors.ANALYSIS_POPUP).first
    try:
        popup.wait_for(state="visible", timeout=5_000)
    except Exception as exc:  # noqa: BLE001
        return {"draftAngleObserved": False, "assessable": False, "reason": f"analysis menu did not open: {exc}"}
    command = _exact_visible_text(
        page.locator(selectors.TAB_CONTEXT_MENU_ITEM),
        ["拔模分析…", "拔模分析...", "Draft analysis…", "Draft analysis..."],
    )
    if command is None:
        return {"draftAngleObserved": False, "assessable": False, "reason": "exact draft-analysis command not found"}
    command.click()
    dialog = page.locator(selectors.DRAFT_ANALYSIS_DIALOG).first
    try:
        dialog.wait_for(state="visible", timeout=5_000)
    except Exception as exc:  # noqa: BLE001
        return {"draftAngleObserved": False, "assessable": False, "reason": f"draft-analysis dialog did not open: {exc}"}
    state = page.evaluate(
        """
        (selector) => {
          const root = document.querySelector(selector);
          if (!root) return {present: false};
          const ids = Array.from(root.querySelectorAll('[data-parameter-id]'))
            .map(el => el.getAttribute('data-parameter-id')).filter((value, index, all) => value && all.indexOf(value) === index);
          const angle = root.querySelector('[data-parameter-id="minimumDraftAngle"] input');
          const legends = Array.from(document.querySelectorAll('.draft-analysis-key-color')).filter(el => el.offsetParent)
            .map(el => ({className: String(el.className || ''), color: getComputedStyle(el).backgroundColor}));
          return {present: true, parameterIds: ids, minimumAngleValue: angle ? angle.value : '', legends};
        }
        """,
        selectors.DRAFT_ANALYSIS_DIALOG,
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    restored = page.locator(selectors.DRAFT_ANALYSIS_DIALOG).count() == 0
    return {
        "draftAngleObserved": True,
        "fdmCapable": False,
        "assessable": False,
        "bodyName": body_name,
        "buildDirection": build_direction,
        "maxOverhangAngleDegrees": max_overhang_angle_degrees,
        "maximumObservedAngleDegrees": None,
        "risk": "unknown",
        "measurements": [],
        "analysisState": state,
        "restored": restored,
        "reason": "draft-analysis direction and part queries were not inferred from viewport selection",
        "assumption": "viewport selection is not treated as print build orientation",
    }


def print_orientation_check(
    page: Any,
    *,
    body_name: str,
    build_direction: str,
    max_overhang_angle_degrees: float,
) -> dict[str, Any]:
    """Fail closed until the shared STEP-based FDM analyzer is available."""
    del page
    return {
        "orientationChecked": False,
        "assessable": False,
        "fdmCapable": False,
        "semanticValidity": "invalid",
        "deprecated": True,
        "bodyName": body_name,
        "buildDirection": build_direction,
        "maxOverhangAngleDegrees": max_overhang_angle_degrees,
        "maximumObservedAngleDegrees": None,
        "risk": "unknown",
        "measurements": [],
        "browserActionPerformed": False,
        "reason": "Onshape draft analysis is not an FDM orientation analysis",
        "replacement": "shared STEP conversion and slicer-backed fdm_analysis pipeline",
    }


def wall_thickness_report(
    page: Any,
    *,
    body_name: str,
    minimum_allowed_mm: float,
    samples: list[str] | None = None,
) -> dict[str, Any]:
    """Read sampled measurements and never claim a global minimum without evidence."""
    if not _select_body(page, body_name):
        return {"wallThicknessMeasured": False, "reason": f"body {body_name!r} not found"}
    if not samples:
        return {
            "wallThicknessMeasured": False,
            "bodyName": body_name,
            "coverage": "unknown",
            "globalMinimumVerified": False,
            "reason": "explicit semantic sample names are required",
        }
    selected_samples = []
    missing_samples = []
    for sample in samples or []:
        target = page.get_by_text(sample, exact=True)
        if target.count() == 1:
            target.first.click(modifiers=[] if not selected_samples else ["Control"])
            selected_samples.append(sample)
        else:
            missing_samples.append(sample)
    button = page.locator("button.measure-button")
    if button.count() != 1:
        return {
            "wallThicknessMeasured": False,
            "bodyName": body_name,
            "coverage": "unknown",
            "globalMinimumVerified": False,
            "reason": "measure button not found uniquely",
        }
    button.first.click()
    page.wait_for_timeout(250)
    state = _read_visible_analysis(page)
    quantities = _quantities(state.get("text", ""))
    millimeters = []
    factors = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "inch": 25.4}
    for item in quantities:
        if item["unit"] in factors:
            millimeters.append(item["value"] * factors[item["unit"]])
    minimum = min(millimeters) if millimeters else None
    return {
        "wallThicknessMeasured": minimum is not None,
        "bodyName": body_name,
        "minimumAllowedMm": minimum_allowed_mm,
        "minimumObservedMm": minimum,
        "passesSampledMinimum": minimum is not None and minimum >= minimum_allowed_mm,
        "coverage": "sampled" if minimum is not None else "unknown",
        "globalMinimumVerified": False,
        "selectedSamples": selected_samples,
        "missingSamples": missing_samples,
        "measurements": quantities,
        "analysisState": state,
    }


def apply_blend(
    page: Any,
    *,
    operation: str,
    targets: list[str],
    amount: str,
) -> dict[str, Any]:
    """Apply fillet/chamfer/draft through native UI and require a new history row."""
    before = actions.read_partstudio_features(page)
    selected = []
    missing = []
    for target_name in targets:
        target = page.get_by_text(target_name, exact=True)
        if target.count() != 1:
            missing.append(target_name)
            continue
        target.first.click(modifiers=[] if not selected else ["Control"])
        selected.append(target_name)
    if missing:
        return {"blendApplied": False, "selected": selected, "missing": missing, "reason": "one or more semantic targets were not visible"}
    labels = {
        "fillet": ["圆角", "Fillet"],
        "chamfer": ["倒角", "Chamfer"],
        "draft": ["拔模", "Draft"],
    }[operation]
    tool = _exact_visible_text(page.locator(selectors.PS_TOOL_BUTTON), labels)
    if tool is None:
        return {"blendApplied": False, "reason": f"exact {operation} toolbar item not found"}
    tool.click()
    dialog = page.locator(selectors.PS_FEATURE_DIALOG).first
    try:
        dialog.wait_for(state="visible", timeout=10_000)
    except Exception as exc:  # noqa: BLE001
        return {"blendApplied": False, "reason": f"blend dialog did not open: {exc}"}
    amount_labels = {
        "fillet": ["半径", "Radius"],
        "chamfer": ["距离", "Distance"],
        "draft": ["角度", "Angle"],
    }[operation]
    field = None
    for label in amount_labels:
        container = dialog.locator(".parameter-item, .feature-parameter, .form-group").filter(has_text=label)
        candidate = container.locator("input:visible")
        if candidate.count() == 1:
            field = candidate.first
            break
    if field is None:
        candidates = dialog.locator("input:visible")
        if candidates.count() == 1:
            field = candidates.first
    if field is None:
        return {"blendApplied": False, "reason": "blend amount input not found uniquely"}
    field.fill(amount)
    readback = field.input_value()
    accept = dialog.locator(selectors.PS_FEATURE_DIALOG_ACCEPT)
    if accept.count() == 0:
        accept = page.locator(selectors.PS_FEATURE_DIALOG_ACCEPT)
    if accept.count() == 0:
        return {"blendApplied": False, "reason": "blend accept button not found"}
    accept.first.click()
    page.wait_for_timeout(500)
    after = actions.read_partstudio_features(page)
    before_names = [item.get("name") for item in before.get("features", [])]
    new_features = [item for item in after.get("features", []) if item.get("name") not in before_names]
    error_rows = [
        item for item in new_features
        if item.get("hasError") or re.search(r"error|错误|未计算", str(item.get("name", "")), re.I)
    ]
    return {
        "blendApplied": bool(new_features) and not error_rows and readback == amount,
        "operation": operation,
        "selected": selected,
        "amount": amount,
        "amountReadback": readback,
        "newFeatures": new_features,
        "errorRows": error_rows,
        "beforeFeatureCount": len(before.get("features", [])),
        "afterFeatureCount": len(after.get("features", [])),
    }


def print_optimize_part(
    page: Any,
    *,
    body_name: str,
    blend: dict[str, Any] | None,
    orientation: dict[str, Any],
    wall: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed before mutation while the FDM orientation dependency is invalid."""
    orientation_result = print_orientation_check(
        page,
        body_name=body_name,
        build_direction=orientation["build_direction"],
        max_overhang_angle_degrees=float(orientation["max_overhang_angle_degrees"]),
    )
    if not orientation_result.get("orientationChecked") or not orientation_result.get("assessable"):
        return {
            "optimized": False,
            "failedStage": "orientation",
            "semanticValidity": "invalid",
            "fdmCapable": False,
            "mutationAttempted": False,
            "blend": None,
            "orientation": orientation_result,
            "reason": "FDM assessment is unavailable; no geometry change was attempted",
        }
    blend_result = None
    if blend:
        blend_result = apply_blend(page, operation=blend["operation"], targets=blend["targets"], amount=blend["amount"])
        if not blend_result.get("blendApplied"):
            return {"optimized": False, "failedStage": "blend", "blend": blend_result}
    wall_result = wall_thickness_report(
        page,
        body_name=body_name,
        minimum_allowed_mm=float(wall["minimum_allowed_mm"]),
        samples=wall.get("samples", []),
    )
    optimized = bool(
        orientation_result.get("assessable")
        and orientation_result.get("risk") == "pass"
        and wall_result.get("wallThicknessMeasured")
        and wall_result.get("passesSampledMinimum")
    )
    return {
        "optimized": optimized,
        "failedStage": "" if optimized else "verification",
        "blend": blend_result,
        "orientation": orientation_result,
        "wall": wall_result,
    }


def generate_spiral_ridge_script(
    *,
    base_radius_mm: float,
    pitch_mm: float,
    ridge_width_mm: float,
    ridge_height_mm: float,
    length_mm: float,
    clockwise: bool,
) -> str:
    """Generate a bounded FeatureScript helix+sweep feature with no raw code input."""
    revolutions = length_mm / pitch_mm
    clockwise_literal = "true" if clockwise else "false"
    return f'''FeatureScript 3044;
import(path : "onshape/std/geometry.fs", version : "3044.0");

annotation {{ "Feature Type Name" : "Spiral ridge" }}
export const spiralRidge = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {{
    }}
    {{
        const baseRadius = {base_radius_mm:.9g} * millimeter;
        const pitch = {pitch_mm:.9g} * millimeter;
        const ridgeWidth = {ridge_width_mm:.9g} * millimeter;
        const ridgeHeight = {ridge_height_mm:.9g} * millimeter;
        const length = {length_mm:.9g} * millimeter;
        const baseId = id + "base";
        fCylinder(context, baseId, {{
                "bottomCenter" : vector(0, 0, 0) * millimeter,
                "topCenter" : vector(0 * millimeter, 0 * millimeter, length),
                "radius" : baseRadius
        }});
        const startPoint = vector(baseRadius, 0 * millimeter, 0 * millimeter);
        const tangent = normalize(vector(0 * millimeter, 2 * PI * baseRadius, pitch));
        opHelix(context, id + "helix", {{
                "direction" : vector(0, 0, 1),
                "axisStart" : vector(0, 0, 0) * millimeter,
                "startPoint" : startPoint,
                "interval" : [0, {revolutions:.12g}],
                "clockwise" : {clockwise_literal},
                "helicalPitch" : pitch,
                "spiralPitch" : 0 * millimeter
        }});
        const profile = newSketchOnPlane(context, id + "profile", {{
                "sketchPlane" : plane(startPoint, tangent, X_DIRECTION)
        }});
        skRectangle(profile, "ridge", {{
                "firstCorner" : vector(-ridgeHeight / 2, -ridgeWidth / 2),
                "secondCorner" : vector(ridgeHeight / 2, ridgeWidth / 2)
        }});
        skSolve(profile);
        opSweep(context, id + "sweep", {{
                "profiles" : qSketchRegion(id + "profile"),
                "path" : qCreatedBy(id + "helix", EntityType.EDGE)
        }});
        opBoolean(context, id + "union", {{
                "tools" : qUnion([
                    qCreatedBy(baseId, EntityType.BODY),
                    qCreatedBy(id + "sweep", EntityType.BODY)
                ]),
                "operationType" : BooleanOperationType.UNION,
                "keepTools" : false
        }});
        setProperty(context, {{
                "entities" : qCreatedBy(baseId, EntityType.BODY),
                "propertyType" : PropertyType.NAME,
                "value" : "Spiral ridge cylinder"
        }});
    }});
'''
