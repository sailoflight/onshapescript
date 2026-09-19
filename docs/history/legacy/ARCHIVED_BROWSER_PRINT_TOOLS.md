# Archived browser print-analysis tools

> **Historical, non-executable record.** The two browser print tools archived
> here were removed from the runtime on 2026-09-19 by owner decision. The
> functions below no longer exist anywhere in the tree; the quoted signatures are
> not callable and their commands are unsupported. Current authority for
> additively-manufactured print analysis is the shared STEP conversion plus the
> slicer-backed `fdm_analysis/` pipeline. Archive routing is maintained in
> [`../TRACEABILITY.md`](../TRACEABILITY.md).

## Why these two were archived

Both tools were already *fail-closed stubs*: they validated their inputs and then
returned a `semantically invalid` compatibility result **without performing the
work their names promise**. `browser_print_orientation_check` never measured an
overhang angle, because Onshape's draft analysis is not an FDM orientation
analysis; `browser_print_optimize_part` therefore stopped at its `orientation`
stage every time and never reached the blend it validated.

They were classified `Remove` by the tool-surface audit, and the earlier recorded
position was to keep them fail-closed and default-hidden while the Bambu
exclusion was active. The owner reversed that on 2026-09-19:

> 这几个不对劲哦 他们是因为高风险才被隐藏 而并不是所谓没用 而打印检测倒是确实没用
> 可以拿出来归档 后面可能会单独打印分析模块

That is, the *hiding* reasons are not uniform. `browser_delete_tab` and
`browser_draw_part` are hidden because they are **high risk**, not because they are
useless, so they stay. These two print tools are hidden because they genuinely do
not do the job, so they are archived here instead of lingering as misleading
names in the registry.

## What was removed

| Where | Removed |
|---|---|
| `mcp_main/win/mcp/browser_tools.py` | two handlers, two registry `_tool(...)` entries, two handler-table entries, and the three now-unused `_ORIENTATION_STAGE` / `_WALL_STAGE` / `_BLEND_STAGE` schema fragments |
| `mcp_main/win/mcp/server.py` | nothing — browser registry and dispatch are owned by `browser_tools.py` |
| `onshape_browser_mode/semantics.py` | the two semantic records |
| `onshape_browser_mode/project.py` | the two `ALLOWED_PROJECT_TOOLS` names and their two `TOOL_OUTCOME_KEYS` outcomes |
| `onshape_browser_mode/modeling_transactions.py` | `print_orientation_check`, `print_optimize_part`, and `draft_angle_proxy` |
| tests | the two behaviour tests in `dev/tests/test_browser_planned_tools.py` and the two names in its planned/read-only/offline sets, replaced by one archive-boundary test; the name in `test_dynamic_tool_views`; the semantic case in `test_browser_semantics`; the gateway case in `test_mcp_server`; the registry contracts in `test_browser_mode`, `test_browser_plan_completion` and `test_capabilities`; the audit `Remove` rows |
| docs | the `Remove` rows and counts in `docs/architecture/TOOL_SURFACE_AUDIT.md`, the print mention in `docs/usage/MCP_CONSUMER.md`, the FDM boundary note in `onshape_docs/experience/browser-modeling.md`, the superseded status line in `onshape_docs/verification/browser-tools-2026-08-25.md`, the roadmap mentions in `docs/roadmap/BROWSER_PLANNED_TOOLS.md` / `BROWSER_SIX_LEVEL_SEMANTICS_AND_FDM_PLAN.md` / `BROWSER_MODELING_GAPS.md` / `BROWSER_FS_SEMANTIC_TOOLS.md` / `FS_FIRST_CONTROLLING_ROUTE.md`, and the regenerated `TOOL_REFERENCE.md` plus `onshape_docs/index.json` |

`draft_angle_proxy` was removed in the same pass and is listed here for honesty
about scope: it was already unreachable. It had **zero callers anywhere in the
tree** and was never a registered tool, so it was dead code that existed only to
support this retired draft-analysis print path. Its selectors
(`ANALYSIS_POPUP`, `DRAFT_ANALYSIS_DIALOG`) are kept, because they are measured
live UI facts that a future analysis module may reuse.

## What would revive this work

A separate print-analysis module, not a browser tool: the archived stubs fail
closed precisely because the measurement belongs to a slicer, not to Onshape's
draft analysis. The replacement named in the archived return values is the shared
STEP conversion plus the slicer-backed `fdm_analysis/` pipeline, which is where an
FDM orientation engine should live if it is built. Any revival must re-measure its
own UI facts and re-enter the tool surface through the audit, not by restoring
these names.

## Archived source

The code below is quoted from the tree as it stood immediately before removal.

### `mcp_main/win/mcp/browser_tools.py` — handler for `browser_print_orientation_check`

```python
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
```

### `mcp_main/win/mcp/browser_tools.py` — handler for `browser_print_optimize_part`

```python
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
```

### `mcp_main/win/mcp/browser_tools.py` — the two registry entries

```python
    _tool("browser_print_orientation_check", "Deprecated compatibility result: returns semantically invalid/unassessable without a browser action because Onshape draft analysis is not an FDM orientation engine.", {"body_name": {"type": "string"}, "build_direction": {"type": "string", "enum": ["+x", "-x", "+y", "-y", "+z", "-z"], "default": "+z"}, "max_overhang_angle_degrees": {"type": "number", "minimum": 0, "maximum": 90, "default": 45}}, mutating=False, seconds=1, required=["body_name"], network="offline"),
    _tool("browser_print_optimize_part", "Deprecated compatibility workflow: validates inputs, then stops before browser/model mutation because its draft-based FDM orientation dependency is semantically invalid.", {"body_name": {"type": "string"}, "blend": _BLEND_STAGE, "orientation": _ORIENTATION_STAGE, "wall": _WALL_STAGE, "dry_run": _DRY}, mutating=False, seconds=1, required=["body_name", "orientation", "wall"], network="offline"),
```

### `mcp_main/win/mcp/browser_tools.py` — the two handler-table entries

```python
            "tool": "browser_print_optimize_part",
    _tool("browser_print_orientation_check", "Deprecated compatibility result: returns semantically invalid/unassessable without a browser action because Onshape draft analysis is not an FDM orientation engine.", {"body_name": {"type": "string"}, "build_direction": {"type": "string", "enum": ["+x", "-x", "+y", "-y", "+z", "-z"], "default": "+z"}, "max_overhang_angle_degrees": {"type": "number", "minimum": 0, "maximum": 90, "default": 45}}, mutating=False, seconds=1, required=["body_name"], network="offline"),
    _tool("browser_print_optimize_part", "Deprecated compatibility workflow: validates inputs, then stops before browser/model mutation because its draft-based FDM orientation dependency is semantically invalid.", {"body_name": {"type": "string"}, "blend": _BLEND_STAGE, "orientation": _ORIENTATION_STAGE, "wall": _WALL_STAGE, "dry_run": _DRY}, mutating=False, seconds=1, required=["body_name", "orientation", "wall"], network="offline"),
    "browser_print_orientation_check": browser_print_orientation_check,
    "browser_print_optimize_part": browser_print_optimize_part,
```

### `onshape_browser_mode/semantics.py` — the two semantic records

```python
    "browser_print_orientation_check": _semantic(
        "L4",
        default_exposure=False,
        maturity="semantically_invalid",
        note="Current draft-analysis evidence is not an FDM orientation analysis.",
    ),
    "browser_print_optimize_part": _semantic(
        "L5",
        default_exposure=False,
        dependencies=(
            "browser_apply_blend",
            "browser_print_orientation_check",
            "browser_wall_thickness_report",
        ),
        maturity="semantically_invalid",
        note="Current workflow depends on an invalid FDM orientation proxy.",
    ),
```

### `onshape_browser_mode/project.py` — `ALLOWED_PROJECT_TOOLS` entries

```python
    "browser_print_orientation_check",
    "browser_print_optimize_part",
    "browser_print_orientation_check": "orientationChecked",
    "browser_print_optimize_part": "optimized",
```

### `onshape_browser_mode/project.py` — `TOOL_OUTCOME_KEYS` entries

```python
    "browser_print_orientation_check",
    "browser_print_optimize_part",
    "browser_print_orientation_check": "orientationChecked",
    "browser_print_optimize_part": "optimized",
```

### `onshape_browser_mode/modeling_transactions.py` — `print_orientation_check`

```python
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
```

### `onshape_browser_mode/modeling_transactions.py` — `print_optimize_part`

```python
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
```

### `onshape_browser_mode/modeling_transactions.py` — `draft_angle_proxy` (already unreachable)

```python
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
```
