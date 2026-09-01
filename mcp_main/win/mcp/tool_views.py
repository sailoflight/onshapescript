from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


CONTROL_TOOL_NAME = "mcp_tool_view"
CATALOG_TOOL_NAME = "mcp_tool_catalog"
CONTROL_TOOL_NAMES = frozenset({CONTROL_TOOL_NAME, CATALOG_TOOL_NAME})
VALID_EXPOSURE_MODES = ("semantic", "static", "profile", "dynamic")
VALID_PROFILES = (
    "default",
    "browser",
    "rest",
    "featurescript",
    "documentation",
    "geometry",
    "all",
)
VALID_SEMANTIC_LEVELS = tuple(f"L{index}" for index in range(1, 7))
REST_REFERENCE_TOOL_NAMES = frozenset({
    "onshape_api_list_tags",
    "onshape_api_search",
    "onshape_api_endpoint",
    "onshape_api_schema",
    "onshape_api_auth",
    "onshape_api_error_codes",
})

_PROFILE_DESCRIPTIONS = {
    "default": "Current bounded ordinary view: all non-browser tools plus default-visible browser tools.",
    "browser": "Browser tools with the ordinary semantic view unless semantic_levels is supplied.",
    "rest": "Onshape REST operations and REST API reference tools.",
    "featurescript": "FeatureScript reference and FeatureScript-related Onshape operations.",
    "documentation": "Project, FeatureScript, and Onshape REST API reference tools.",
    "geometry": "STEP export, geometry backend, geometry-package, and wall-thickness tools.",
    "all": "Complete tool registry for compatibility and debugging.",
}

_ALWAYS_VISIBLE_BROWSER_TOOLS = {
    "browser_session",
    "browser_discover_tools",
    "browser_invoke_discovered",
}

_FEATURESCRIPT_ONSHAPE_TOOLS = {
    "onshape_build_parameter_payload",
    "onshape_check_model",
    "onshape_create_validation_part_studio",
    "onshape_eval_featurescript",
    "onshape_get_feature_studio_status",
    "onshape_get_parameter_set",
    "onshape_instantiate_feature",
    "onshape_render_preview",
    "onshape_run_validation_pipeline",
    "onshape_upload_feature_studio",
}


def exposure_mode(value: str | None = None) -> str:
    mode = (value if value is not None else os.environ.get("ONSHAPE_MCP_TOOL_EXPOSURE", "semantic"))
    mode = mode.strip().lower()
    if mode not in VALID_EXPOSURE_MODES:
        allowed = ", ".join(VALID_EXPOSURE_MODES)
        raise ValueError(f"ONSHAPE_MCP_TOOL_EXPOSURE must be one of: {allowed}")
    return mode


def startup_profile(value: str | None = None) -> str:
    profile = (value if value is not None else os.environ.get("ONSHAPE_MCP_TOOL_PROFILE", "default"))
    profile = profile.strip().lower()
    if profile not in VALID_PROFILES:
        allowed = ", ".join(VALID_PROFILES)
        raise ValueError(f"ONSHAPE_MCP_TOOL_PROFILE must be one of: {allowed}")
    return profile


def _semantic_record(name: str) -> Any:
    if not name.startswith("browser_"):
        return None
    from onshape_browser_mode.semantics import TOOL_SEMANTICS

    return TOOL_SEMANTICS.get(name)


def _ordinary_browser_names(tools: list[dict[str, Any]]) -> set[str]:
    from onshape_browser_mode.semantics import select_tool_names

    browser_names = [tool["name"] for tool in tools if tool["name"].startswith("browser_")]
    return set(select_tool_names(browser_names))


def _profile_includes(name: str, profile: str) -> bool:
    if name in CONTROL_TOOL_NAMES:
        return True
    if profile in {"default", "all"}:
        return True
    if profile == "browser":
        return name.startswith("browser_")
    if profile == "rest":
        return name.startswith("onshape_")
    if profile == "featurescript":
        return name.startswith("fs_") or name in _FEATURESCRIPT_ONSHAPE_TOOLS
    if profile == "documentation":
        return name.startswith(("docs_", "fs_")) or name in REST_REFERENCE_TOOL_NAMES
    if profile == "geometry":
        return any(
            token in name
            for token in ("_export_step", "_geometry_", "wall_thickness")
        )
    raise ValueError(f"Unknown tool profile: {profile}")


def select_view_tools(
    tools: list[dict[str, Any]],
    *,
    profile: str,
    semantic_levels: tuple[str, ...] | None,
) -> list[dict[str, Any]]:
    if profile not in VALID_PROFILES:
        raise ValueError(f"Unknown tool profile: {profile}")
    ordinary_browser = _ordinary_browser_names(tools)
    selected_levels = set(semantic_levels or ())
    result: list[dict[str, Any]] = []
    for tool in tools:
        name = tool["name"]
        if not _profile_includes(name, profile):
            continue
        record = _semantic_record(name)
        if name in _ALWAYS_VISIBLE_BROWSER_TOOLS:
            result.append(tool)
            continue
        if name.startswith("browser_"):
            if profile != "all" and record is not None and record.maturity == "invalid":
                continue
            if semantic_levels is None:
                if profile != "all" and name not in ordinary_browser:
                    continue
            elif (
                record is not None
                and record.level is not None
                and record.level not in selected_levels
            ):
                continue
        result.append(tool)
    return result


@dataclass
class ToolViewState:
    tools: list[dict[str, Any]]
    mode: str
    profile: str
    semantic_levels: tuple[str, ...] | None = None
    initial_profile: str | None = None

    def __post_init__(self) -> None:
        if self.initial_profile is None:
            self.initial_profile = self.profile

    @classmethod
    def from_environment(cls, tools: list[dict[str, Any]]) -> "ToolViewState":
        mode = exposure_mode()
        if mode == "static":
            profile = "all"
        elif mode in {"profile", "dynamic"}:
            profile = startup_profile()
        else:
            profile = "default"
        return cls(tools=tools, mode=mode, profile=profile)

    @property
    def switching_available(self) -> bool:
        return self.mode == "dynamic"

    @property
    def list_changed_capability(self) -> bool:
        return self.switching_available

    def listed_tools(self) -> list[dict[str, Any]]:
        if self.mode == "static":
            return self.tools
        return select_view_tools(
            self.tools,
            profile=self.profile,
            semantic_levels=self.semantic_levels,
        )

    def status(self) -> dict[str, Any]:
        return {
            "exposureMode": self.mode,
            "profile": self.profile,
            "semanticLevels": list(self.semantic_levels or ()),
            "toolCount": len(self.listed_tools()),
            "registryCount": len(self.tools),
            "switchingAvailable": self.switching_available,
            "listChangedCapability": self.list_changed_capability,
            "conventionOnly": True,
            "authorityChanged": False,
            "knownNameCallsRemainAvailable": True,
            "profiles": [
                {"name": name, "description": _PROFILE_DESCRIPTIONS[name]}
                for name in VALID_PROFILES
            ],
        }

    def apply(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        action = arguments.get("action", "status")
        if action not in {"status", "set", "reset"}:
            raise ValueError("action must be status, set, or reset")
        if action == "status":
            return {**self.status(), "changed": False, "refreshRequired": False}, False
        if not self.switching_available:
            raise ValueError(
                "tool view switching requires ONSHAPE_MCP_TOOL_EXPOSURE=dynamic; "
                "the current mode is a fixed compatibility view"
            )
        before = (self.profile, self.semantic_levels)
        if action == "reset":
            self.profile = self.initial_profile or "default"
            self.semantic_levels = None
        else:
            profile = arguments.get("profile")
            if not isinstance(profile, str) or profile not in VALID_PROFILES:
                allowed = ", ".join(VALID_PROFILES)
                raise ValueError(f"profile must be one of: {allowed}")
            levels = arguments.get("semantic_levels")
            if levels is not None:
                if (
                    not isinstance(levels, list)
                    or not levels
                    or not all(isinstance(level, str) and level in VALID_SEMANTIC_LEVELS for level in levels)
                ):
                    raise ValueError("semantic_levels must be a non-empty list containing L1 through L6")
                if len(set(levels)) != len(levels):
                    raise ValueError("semantic_levels must not contain duplicates")
                normalized_levels: tuple[str, ...] | None = tuple(
                    sorted(levels, key=VALID_SEMANTIC_LEVELS.index)
                )
            else:
                normalized_levels = None
            self.profile = profile
            self.semantic_levels = normalized_levels
        changed = before != (self.profile, self.semantic_levels)
        return {
            **self.status(),
            "changed": changed,
            "refreshRequired": changed,
            "notification": "notifications/tools/list_changed" if changed else None,
        }, changed
