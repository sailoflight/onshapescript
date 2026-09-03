"""Optional six-level discovery metadata for browser tools.

The authoritative tool registry and execution permissions do not depend on this
module. Missing metadata is valid: these records guide discovery, documentation,
and offline lint only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


LEVEL_NAMES = {
    "L1": "browser_primitive",
    "L2": "browser_transaction",
    "L3": "onshape_interaction",
    "L4": "onshape_transaction",
    "L5": "onshape_workflow",
    "L6": "deliverable_recipe",
}

_LEVEL_NUMBER = {level: index for index, level in enumerate(LEVEL_NAMES, start=1)}
_EXPLICIT_LEVELS = frozenset({"L1", "L3"})


@dataclass(frozen=True)
class ToolSemantics:
    """One optional discovery record; never an execution authority."""

    level: str | None
    semantic_name: str
    composition_kind: str
    terminal_state: bool
    default_exposure: bool
    explicit_level_required: bool
    dependencies: tuple[str, ...] = ()
    maturity: str = "implemented"
    note: str = ""

    def as_catalog_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["semanticLevel"] = payload.pop("level")
        payload["semanticName"] = payload.pop("semantic_name")
        payload["compositionKind"] = payload.pop("composition_kind")
        payload["terminalState"] = payload.pop("terminal_state")
        payload["defaultExposure"] = payload.pop("default_exposure")
        payload["explicitLevelRequired"] = payload.pop("explicit_level_required")
        payload["dependencies"] = list(payload["dependencies"])
        return payload


def _semantic(
    level: str | None,
    *,
    composition: str = "composite",
    terminal: bool | None = None,
    default_exposure: bool | None = None,
    dependencies: tuple[str, ...] = (),
    maturity: str = "implemented",
    note: str = "",
    semantic_name: str = "",
) -> ToolSemantics:
    if level is None:
        name = semantic_name
        explicit = False
        visible = True if default_exposure is None else default_exposure
        stable = True if terminal is None else terminal
    else:
        name = LEVEL_NAMES[level]
        explicit = level in _EXPLICIT_LEVELS
        visible = not explicit if default_exposure is None else default_exposure
        stable = level not in {"L3"} if terminal is None else terminal
    return ToolSemantics(
        level=level,
        semantic_name=name,
        composition_kind=composition,
        terminal_state=stable,
        default_exposure=visible,
        explicit_level_required=explicit,
        dependencies=dependencies,
        maturity=maturity,
        note=note,
    )


TOOL_SEMANTICS: dict[str, ToolSemantics] = {}


def _classify(names: Iterable[str], level: str, **kwargs: object) -> None:
    for name in names:
        TOOL_SEMANTICS[name] = _semantic(level, **kwargs)


_classify(
    (
        "browser_inspect",
        "browser_scroll",
        "browser_click",
        "browser_eval",
        "browser_wait",
        "browser_press_key",
        "browser_type",
        "browser_capture_screenshot",
    ),
    "L1",
    composition="atomic",
)

_classify(
    (
        "browser_session",
        "browser_watch",
        "browser_reload",
        "browser_reconnect",
        "browser_discover_tools",
        "browser_invoke_discovered",
    ),
    "L2",
)

_classify(
    (
        "browser_open_insert_feature_dialog",
        "browser_fs_goto_definition",
        "browser_fs_insert_snippet",
        "browser_fs_insert_parameter",
        "browser_fs_toggle_fold",
        "browser_fs_read_notices",
        "browser_open_doc_menu",
        "browser_set_panel_filter",
        "browser_toggle_left_panel",
        "browser_read_selection_preview",
        "browser_element_context_menu",
        "browser_notifications_status",
        "browser_share_document",
    ),
    "L3",
    terminal=False,
)

_classify(
    (
        "browser_deploy_featurescript",
        "browser_open_document",
        "browser_read_featurescript",
        "browser_get_partstudio_features",
        "browser_get_page_tabs",
        "browser_create_document",
        "browser_create_tab",
        "browser_rename_tab",
        "browser_delete_tab",
        "browser_insert_custom_feature",
        "browser_create_document_version",
        "browser_get_fs_compile_status",
        "browser_fs_capture_diagnostic",
        "browser_get_fs_symbols",
        "browser_edit_feature_parameters",
        "browser_fs_watch_part_studio",
        "browser_duplicate_element",
        "browser_view_orientation",
        "browser_wall_thickness_report",
        "browser_apply_blend",
        "browser_insert_assembly_instances",
        "browser_fix_instances",
        "browser_group_instances",
        "browser_create_drawing",
        "browser_add_drawing_dimension",
        "browser_delete_element",
        "browser_export_step",
    ),
    "L4",
)

_classify(
    (
        "browser_drawing_insert_views",
        "browser_draw_part_with_views",
        "browser_spiral_ridge",
        "browser_deploy_and_apply_featurescript",
        "browser_build_part",
        "browser_assemble",
        "browser_draw_part",
    ),
    "L5",
)

TOOL_SEMANTICS.update({
    "browser_get_fs_compile_status": _semantic(
        "L4",
        dependencies=("browser_fs_read_notices",),
        note="Combines Ace annotations with the active FeatureScript notice pane and fails closed when notice evidence is unreadable.",
    ),
    "browser_fs_capture_diagnostic": _semantic(
        "L4",
        default_exposure=False,
        dependencies=("browser_get_fs_compile_status",),
        maturity="experimental",
        note="Persists full browser-visible FeatureScript source and compile evidence to a module-owned local diagnostic package.",
    ),
    "browser_deploy_featurescript": _semantic(
        "L4",
        dependencies=("browser_fs_read_notices", "browser_fs_capture_diagnostic"),
        note="Requires commit transition, exact source readback, combined compile evidence, and records a local diagnostic package.",
    ),
    "browser_delete_tab": _semantic(
        "L4",
        default_exposure=False,
        maturity="deprecated",
        dependencies=("browser_delete_element",),
        note="Exact-name compatibility wrapper; prefer the exact data-id deletion contract.",
    ),
    "browser_geometry_status": _semantic(
        None,
        semantic_name="boundary_observation",
        note="Local owning-mode readiness and dependency discovery; no browser or Onshape transaction.",
    ),
    "browser_draw_part": _semantic(
        "L5",
        default_exposure=False,
        maturity="deprecated",
        dependencies=("browser_create_drawing", "browser_add_drawing_dimension"),
        note="Generic drawing compatibility workflow; prefer verified part-row views and required dimensions.",
    ),
    "browser_drawing_insert_views": _semantic(
        "L5",
        note="Creates a Drawing through the part-row context flow and establishes a verified view layout.",
    ),
    "browser_draw_part_with_views": _semantic(
        "L5",
        dependencies=("browser_drawing_insert_views", "browser_add_drawing_dimension"),
    ),
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
    "browser_spiral_ridge": _semantic(
        "L5",
        dependencies=("browser_deploy_and_apply_featurescript",),
    ),
    "browser_deploy_and_apply_featurescript": _semantic(
        "L5",
        dependencies=(
            "browser_deploy_featurescript",
            "browser_create_document_version",
            "browser_insert_custom_feature",
        ),
    ),
    "browser_build_part": _semantic(
        "L5",
        dependencies=("browser_create_tab", "browser_insert_custom_feature"),
    ),
    "browser_assemble": _semantic(
        "L5",
        dependencies=(
            "browser_create_tab",
            "browser_insert_assembly_instances",
            "browser_fix_instances",
            "browser_group_instances",
        ),
    ),
    "browser_configure_geometry_backend": _semantic(
        None,
        semantic_name="boundary_operation",
        note="Selects a re-discovered local dependency candidate; never installs one.",
    ),
    "browser_build_geometry_package": _semantic(
        "L6",
        dependencies=("browser_export_step", "browser_geometry_status"),
        note="Produces an independently consumable non-slicer geometry-analysis package.",
    ),
    "browser_sync_rest_state": _semantic(
        None,
        semantic_name="boundary_operation",
        note="Cross-mode local state synchronization is outside L1-L6 browser semantics.",
    ),
    "browser_run_project": _semantic(
        None,
        semantic_name="project_control",
        note="A project runner orchestrates one or more future L6 deliverables.",
    ),
})


def semantic_metadata(tool_name: str) -> dict[str, object] | None:
    """Return one catalog record, or None when a tool is intentionally unclassified."""
    record = TOOL_SEMANTICS.get(tool_name)
    return record.as_catalog_dict() if record else None


def select_tool_names(
    tool_names: Iterable[str],
    *,
    semantic_levels: Iterable[str] | None = None,
) -> list[str]:
    """Apply the optional discovery convention without changing registration.

    Ordinary discovery hides records whose default exposure is false. An
    explicit level query returns every classified record at that level, including
    L1/L3 and semantically invalid tools for diagnostics. Unclassified tools stay
    visible by default and are omitted from an explicit level query.
    """
    requested = None if semantic_levels is None else frozenset(semantic_levels)
    if requested is not None:
        unknown = requested.difference(LEVEL_NAMES)
        if unknown:
            raise ValueError(f"unknown semantic levels: {sorted(unknown)}")
    selected = []
    for name in tool_names:
        record = TOOL_SEMANTICS.get(name)
        if requested is None:
            if record is None or record.default_exposure:
                selected.append(name)
        elif record is not None and record.level in requested:
            selected.append(name)
    return selected


def discover_tools(
    tools: Iterable[Mapping[str, Any]],
    *,
    query: str = "",
    semantic_levels: Iterable[str] | None = None,
    limit: int = 8,
    include_schema: bool = True,
) -> dict[str, Any]:
    """Return bounded browser candidates from optional semantic metadata."""
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    if not isinstance(limit, int) or not 1 <= limit <= 12:
        raise ValueError("limit must be from 1 through 12")
    levels = None if semantic_levels is None else tuple(semantic_levels)
    tool_list = [tool for tool in tools if str(tool.get("name", "")).startswith("browser_")]
    allowed = set(select_tool_names(
        [str(tool["name"]) for tool in tool_list],
        semantic_levels=levels,
    ))
    terms = [term for term in query.lower().split() if term]
    level_priority = {"L5": 0, "L4": 1, "L2": 2, "L6": 3, None: 4, "L3": 5, "L1": 6}
    ranked = []
    for tool in tool_list:
        name = str(tool["name"])
        if name not in allowed:
            continue
        record = TOOL_SEMANTICS.get(name)
        metadata = record.as_catalog_dict() if record else None
        description = str(tool.get("description", ""))
        note = record.note if record else ""
        haystacks = (name.lower(), description.lower(), note.lower())
        score = 0
        for term in terms:
            if term in haystacks[0]:
                score += 20
            if term in haystacks[1]:
                score += 5
            if term in haystacks[2]:
                score += 3
        if terms and score == 0:
            continue
        if query and query.lower() == name.lower():
            score += 100
        level = record.level if record else None
        candidate = {
            "name": name,
            "description": description,
            "semantic": metadata,
            "score": score,
        }
        if include_schema:
            candidate["inputSchema"] = tool.get("inputSchema", {})
            candidate["cost"] = tool.get("cost", {})
            candidate["annotations"] = tool.get("annotations", {})
        ranked.append((score, level_priority[level], name, candidate))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    candidates = [item[3] for item in ranked[:limit]]
    return {
        "query": query,
        "semanticLevels": list(levels) if levels is not None else [],
        "explicitLevelQuery": levels is not None,
        "candidateCount": len(candidates),
        "candidates": candidates,
        "invocationTool": "browser_invoke_discovered",
        "note": "semantic level is discovery guidance, not execution authority",
    }


def validate_catalog(
    catalog: Mapping[str, ToolSemantics] = TOOL_SEMANTICS,
) -> list[str]:
    """Return lint errors without affecting tool registration or execution."""
    errors: list[str] = []
    for tool_name, record in catalog.items():
        if record.level is not None:
            if record.level not in LEVEL_NAMES:
                errors.append(f"{tool_name}: unknown level {record.level!r}")
                continue
            if record.semantic_name != LEVEL_NAMES[record.level]:
                errors.append(f"{tool_name}: semantic name does not match {record.level}")
            if record.level in _EXPLICIT_LEVELS:
                if record.default_exposure:
                    errors.append(f"{tool_name}: {record.level} must be hidden by default")
                if not record.explicit_level_required:
                    errors.append(f"{tool_name}: {record.level} must require an explicit level query")
        if record.composition_kind not in {"atomic", "composite"}:
            errors.append(f"{tool_name}: invalid composition kind {record.composition_kind!r}")
        for dependency in record.dependencies:
            child = catalog.get(dependency)
            if child is None or record.level is None or child.level is None:
                continue
            if _LEVEL_NUMBER[child.level] > _LEVEL_NUMBER[record.level]:
                errors.append(f"{tool_name}: lower level depends on higher-level {dependency}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str, path: tuple[str, ...]) -> None:
        if name in visited:
            return
        if name in visiting:
            errors.append(f"dependency cycle: {' -> '.join((*path, name))}")
            return
        visiting.add(name)
        record = catalog.get(name)
        if record is not None:
            for dependency in record.dependencies:
                if dependency in catalog:
                    visit(dependency, (*path, name))
        visiting.remove(name)
        visited.add(name)

    for tool_name in catalog:
        visit(tool_name, ())
    return errors
