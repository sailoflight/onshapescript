from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTROL_TOOL_NAME = "mcp_tool_view"
CATALOG_TOOL_NAME = "mcp_tool_catalog"
INVOKE_TOOL_NAME = "mcp_tool_invoke"
#: The gateway/control surface: discovery, view status, and the generic entry
#: point. These three are listed under EVERY profile, because a profile that
#: hides a name it cannot route is a dead end for a client that refuses names
#: absent from `tools/list` (measured live 2026-09-21, see below).
CONTROL_TOOL_NAMES = frozenset(
    {CONTROL_TOOL_NAME, CATALOG_TOOL_NAME, INVOKE_TOOL_NAME}
)
VALID_EXPOSURE_MODES = ("semantic", "static", "profile", "dynamic", "gateway")

#: `dynamic` is a collapse/expand CONTROL, orthogonal to which display set is
#: shown once it is expanded. A fresh dynamic connection starts `collapsed`
#: (control/discovery entry points only) and an unqualified `expand` opens the
#: `gateway` set; `expanded_view` may instead select any of these sets.
VALID_EXPANDED_VIEWS = ("static", "semantic", "gateway", "profile")
#: The view control's actions. `set` is kept as the compatibility alias for
#: `expand` because older callers selected a profile with it.
VALID_VIEW_ACTIONS = ("status", "set", "reset", "expand", "collapse")

#: Host-local switch for the exposure mode, in the same shape as the other
#: module-local configurations (`<name>.toml` in the module's `config/`
#: directory, overridden by a gitignored `<name>.local.toml`). It exists because
#: the ordinary deployment is launched by an external bridge whose registration
#: owns the child environment: a mode an operator cannot set without editing
#: someone else's registry is not really configurable. Precedence is explicit
#: argument, then `ONSHAPE_MCP_TOOL_EXPOSURE`, then this file, then `gateway`.
CONFIG_DIR = Path(__file__).resolve().parent / "config"
LOCAL_CONFIG_PATH = CONFIG_DIR / "tool_views.local.toml"

#: The `gateway` mode's always-listed core, in listing order. Identical to
#: `CONTROL_TOOL_NAMES` by design: the profile views and the gateway view must
#: agree on what a caller can always reach, or a mode switch would silently
#: remove the only door to a hidden name.
#:
#: `mcp_tool_invoke` exists because "hidden known-name calls remain" is a
#: property of the SERVER, not of every client: measured live 2026-09-21, a real
#: MCP client refused `docs_list` with "unknown tool" once the gateway view no
#: longer advertised it, while the server would have dispatched it happily. A
#: compressed surface whose lookup leads to an uncallable name is worse than no
#: compression, so the mode ships one generic entry that forwards to the SAME
#: handler (and therefore to the same confirmation, cost, dry-run and acceptance
#: gates). This is not the merged `browser_invoke_discovered`: that wrapper added a
#: hop for a client that could already call unadvertised names, whereas this one is
#: the only route for a client that cannot.
GATEWAY_CORE_TOOL_NAMES = CONTROL_TOOL_NAMES

#: The `gateway` mode's curated representatives, one or two per category. The
#: point of listing these is that retrieval is NOT cheap: a three-result catalog
#: `search` measures ~6,800 characters and one modelling `describe` ~10,500,
#: because a summary carries its full concurrency and confirmation contract. So a
#: mode that listed only search would make the common case (build or inspect a
#: model) pay a lookup it does not need. These names cover the ordinary work;
#: `category` keeps two or more of a kind reachable by exact name.
#:
#: Nothing here narrows authority: every entry is an ordinary registered tool
#: whose own confirmation, cost, dry-run and acceptance gates still answer.
#:
#: Sizing rule (measured 2026-09-21, `dev/tools/lookup_depth.py`,
#: `docs/roadmap/LOOKUP_DEPTH_RESEARCH.md`): one lookup round costs the whole
#: prefix (~20.8k estimated tokens at the documented defaults) while an entry
#: rents 427-1,000 tokens per remaining step, so an entry pays for itself at an
#: expected use of roughly 60%-140% of sessions. Two consequences shape this
#: list. First, a PRESCRIBED chain must be listed completely or not at all --
#: listing `docs_search`/`fs_search`/`onshape_api_search` without their second
#: step made the product's own documented workflow pay a hidden-name round every
#: time. Second, the interactive parameter workflow and the tab/cleanup steps the
#: recorded sessions actually drove are listed, because a round between two legs
#: of one edit is pure waste. Rarer families (document setup, capability runs)
#: stay behind `mcp_tool_invoke`, which adds no rent.
GATEWAY_CURATED_TOOL_NAMES = (
    # session and observation
    "browser_session",
    "browser_get_page_tabs",
    "browser_create_tab",
    "browser_activate_tab",
    # read and write the model
    "browser_get_partstudio_features",
    "browser_insert_custom_feature",
    "browser_delete_feature",
    # the parameter workflow: edit, confirm, and the write-free read-back
    "browser_edit_feature_parameters",
    "browser_verify_feature_parameters",
    "browser_read_feature_parameters",
    # FeatureScript and the runner
    "browser_deploy_featurescript",
    "browser_run_project",
    # discovered capabilities and deliverables
    "browser_discover_tools",
    "browser_export_step",
    # offline references, with BOTH steps of each prescribed chain
    "docs_search",
    "docs_section",
    "fs_search",
    "fs_get_function",
    "onshape_api_search",
    "onshape_api_endpoint",
    # cost and host state
    "onshape_api_quota",
    "onshape_geometry_status",
)

GATEWAY_TOOL_NAMES = GATEWAY_CORE_TOOL_NAMES | set(GATEWAY_CURATED_TOOL_NAMES)

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
    "onshape_update_feature_list",
    "onshape_upload_feature_studio",
}

# Names absorbed by a merge that stay registered so an existing caller keeps
# working, but are no longer advertised. Browser-namespace wrappers are hidden by
# their own `default_exposure=False` semantics record; this set covers absorbed
# names outside that namespace, which have no semantics record to consult. Only
# the complete `all` registry view lists them (or `mcp_tool_catalog` by exact
# name), because a compatibility path must not look like a normal choice.
ABSORBED_COMPATIBILITY_TOOLS = frozenset({
    "fs_list_modules",
})


def local_config() -> dict[str, Any]:
    """The optional host-local overrides, or {} when the file is absent.

    A malformed file is a real configuration error and raises: silently falling
    back to the default would leave an operator believing the switch took effect.
    """
    if not LOCAL_CONFIG_PATH.is_file():
        return {}
    with LOCAL_CONFIG_PATH.open("rb") as handle:
        document = tomllib.load(handle)
    if not isinstance(document, dict):
        raise ValueError(f"{LOCAL_CONFIG_PATH} must contain a TOML table")
    return document


def _local_section(name: str) -> dict[str, Any]:
    section = local_config().get(name, {})
    if not isinstance(section, dict):
        raise ValueError(f"{LOCAL_CONFIG_PATH}: [{name}] must be a table")
    return section


def exposure_mode(value: str | None = None) -> str:
    if value is not None:
        mode = value
    elif "ONSHAPE_MCP_TOOL_EXPOSURE" in os.environ:
        mode = os.environ["ONSHAPE_MCP_TOOL_EXPOSURE"]
    else:
        mode = _local_section("exposure").get("mode", "gateway")
    if not isinstance(mode, str):
        raise ValueError("the exposure mode must be a string")
    mode = mode.strip().lower()
    if mode not in VALID_EXPOSURE_MODES:
        allowed = ", ".join(VALID_EXPOSURE_MODES)
        raise ValueError(f"ONSHAPE_MCP_TOOL_EXPOSURE must be one of: {allowed}")
    return mode


def startup_profile(value: str | None = None) -> str:
    if value is not None:
        profile = value
    elif "ONSHAPE_MCP_TOOL_PROFILE" in os.environ:
        profile = os.environ["ONSHAPE_MCP_TOOL_PROFILE"]
    else:
        profile = _local_section("exposure").get("profile", "default")
    if not isinstance(profile, str):
        raise ValueError("the startup profile must be a string")
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
        if name in ABSORBED_COMPATIBILITY_TOOLS and profile != "all":
            continue
        record = _semantic_record(name)
        if name in _ALWAYS_VISIBLE_BROWSER_TOOLS:
            result.append(tool)
            continue
        if name.startswith("browser_"):
            # Hidden-ness for a browser name comes from its semantics record:
            # `default_exposure=False` removes it from the ordinary list while an
            # explicit semantic_levels query still reaches it by level. There is
            # deliberately no second, maturity-based hiding path, because that
            # would make a recorded name unreachable even when asked for.
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
    """One connection's tool-display state.

    SCOPE: this state is CONNECTION-scoped, never conversation-scoped. A stdio
    server sees a connection and the messages on it, not the conversations a
    client multiplexes over it. If a client reuses or shares one connection, an
    expand performed for one conversation is therefore observed by EVERY
    conversation on that connection. That limitation is stated plainly instead
    of claiming a per-conversation isolation the server cannot see.

    Collapse is pure in-memory state: it writes nothing anywhere and is NOT the
    same as exiting the browser or revoking a permission. Hidden tools remain
    callable by exact registered name and every confirmation, quota, pacing and
    acceptance gate still answers.

    A cold start built by `from_environment` enters `dynamic` COLLAPSED, with
    `gateway` remembered as the set an unqualified expand opens. The field
    defaults below describe a directly constructed state instead: it preserves
    the legacy explicit-profile expansion (`collapsed=False` over
    `expanded_view`), which is what embedding code and tests have used.
    """

    tools: list[dict[str, Any]]
    mode: str
    profile: str
    semantic_levels: tuple[str, ...] | None = None
    initial_profile: str | None = None
    collapsed: bool = False
    expanded_view: str = "profile"

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
            # `semantic` is the bounded ordinary view; `gateway` ignores the
            # profile entirely because its listed surface is fixed above.
            profile = "default"
        return cls(
            tools=tools,
            mode=mode,
            profile=profile,
            # A fresh `dynamic` connection advertises NO domain-tool schema: it
            # starts collapsed on the three control/discovery entry points and
            # remembers `gateway` as the default expanded display set.
            # static/semantic/profile/gateway have no collapse state and list
            # their own fixed set.
            collapsed=mode == "dynamic",
            expanded_view="gateway",
        )

    @property
    def switching_available(self) -> bool:
        return self.mode == "dynamic"

    @property
    def list_changed_capability(self) -> bool:
        return self.switching_available

    @property
    def state(self) -> str:
        return "collapsed" if self.mode == "dynamic" and self.collapsed else "expanded"

    def _control_tools(self) -> list[dict[str, Any]]:
        by_name = {tool["name"]: tool for tool in self.tools}
        return [
            by_name[name]
            for name in (CATALOG_TOOL_NAME, CONTROL_TOOL_NAME, INVOKE_TOOL_NAME)
        ]

    def _gateway_tools(self) -> list[dict[str, Any]]:
        # The core plus the curated representatives, in the order they are
        # declared here rather than registry order: the list is a routing
        # surface, and grouping it by what a caller does next is the whole
        # reason it is small. Every OTHER registered name stays reachable by
        # exact name (`tools/call` resolves through `HANDLERS` with no view
        # filter, pinned by `test_hidden_known_name_tool_remains_callable`),
        # and `mcp_tool_catalog action=index` maps the complete registry in
        # bounded lines, so nothing is lost or made unfindable -- hiding is
        # context routing, never authority.
        by_name = {tool["name"]: tool for tool in self.tools}
        ordered = (
            (CATALOG_TOOL_NAME, CONTROL_TOOL_NAME, INVOKE_TOOL_NAME)
            + GATEWAY_CURATED_TOOL_NAMES
        )
        return [by_name[name] for name in ordered if name in by_name]

    def listed_tools(self) -> list[dict[str, Any]]:
        if self.mode == "static":
            return self.tools
        if self.mode == "gateway":
            return self._gateway_tools()
        if self.mode == "dynamic":
            if self.collapsed:
                # Collapsed lists ONLY the control/discovery entry points. The
                # gateway's domain representatives are deliberately not
                # resident here; they arrive when the caller expands.
                return self._control_tools()
            if self.expanded_view == "static":
                return self.tools
            if self.expanded_view == "gateway":
                return self._gateway_tools()
            if self.expanded_view == "semantic":
                # A fixed display set, independent of the startup profile:
                # `semantic` means the bounded ordinary `default` view.
                return select_view_tools(
                    self.tools,
                    profile="default",
                    semantic_levels=self.semantic_levels,
                )
            return select_view_tools(
                self.tools,
                profile=self.profile,
                semantic_levels=self.semantic_levels,
            )
        listed = select_view_tools(
            self.tools,
            profile=self.profile,
            semantic_levels=self.semantic_levels,
        )
        # The invoker is listed in EVERY mode (static returns the raw registry,
        # which already contains it). Hiding it outside gateway was the tempting
        # design -- an ordinary view looks like it already lists what it would
        # forward to -- but it was measured wrong: a real client (2026-09-21)
        # refuses a name that is absent from tools/list with `unknown tool`, so a
        # hidden name is reachable ONLY while some advertised door exists.
        # Listing it costs 2,207 chars on the semantic view (+1.4%) and is the
        # sole route to the names that view hides.
        return listed

    def status(self) -> dict[str, Any]:
        listed = self.listed_tools()
        return {
            "exposureMode": self.mode,
            # `state`/`expandedView`/`scope` describe the collapse/expand
            # control. `scope` says outright that this state belongs to the
            # CONNECTION: a shared or reused connection shows the same view to
            # every conversation on it.
            "state": self.state,
            "expandedView": self.expanded_view,
            "scope": "connection",
            "profile": self.profile,
            "semanticLevels": list(self.semantic_levels or ()),
            "toolCount": len(listed),
            "registryCount": len(self.tools),
            "listedNames": [tool["name"] for tool in listed],
            "hiddenNamesStillCallable": True,
            "gateway": {
                "core": sorted(GATEWAY_CORE_TOOL_NAMES),
                "curated": list(GATEWAY_CURATED_TOOL_NAMES),
                "reason": (
                    "Curated representatives are listed because retrieval is not "
                    "free (a 3-result search ~6.8 kB, a modelling describe ~10.5 kB); "
                    "everything else is reached by exact name or by "
                    "mcp_tool_catalog action=index."
                ),
            },
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

    def _effective_state(self) -> tuple[Any, ...]:
        """Everything whose change actually alters what `tools/list` returns."""
        return (self.collapsed, self.expanded_view, self.profile, self.semantic_levels)

    def apply(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        action = arguments.get("action", "status")
        if action not in VALID_VIEW_ACTIONS:
            raise ValueError("action must be status, set, reset, expand, or collapse")
        if action == "status":
            return {**self.status(), "changed": False, "refreshRequired": False}, False
        if not self.switching_available:
            raise ValueError(
                "tool view switching requires ONSHAPE_MCP_TOOL_EXPOSURE=dynamic; "
                "the current mode is a fixed compatibility view"
            )
        before = self._effective_state()
        if action == "reset":
            # Back to a cold start: collapsed, gateway, and the connection's
            # original startup profile.
            self.collapsed = True
            self.expanded_view = "gateway"
            self.profile = self.initial_profile or "default"
            self.semantic_levels = None
        elif action == "collapse":
            # Pure in-memory state: nothing is written locally or remotely, and
            # no browser session or permission is touched.
            self.collapsed = True
        else:
            # `expand` opens a display set; `set` is its compatibility alias
            # and, like the action it replaces, defaults to the startup-profile
            # view and resolves the level filter from its own arguments.
            requested_view = arguments.get("expanded_view")
            if requested_view is None:
                requested_view = "profile" if action == "set" else self.expanded_view
            if (
                not isinstance(requested_view, str)
                or requested_view not in VALID_EXPANDED_VIEWS
            ):
                allowed = ", ".join(VALID_EXPANDED_VIEWS)
                raise ValueError(f"expanded_view must be one of: {allowed}")
            self.expanded_view = requested_view
            profile = arguments.get("profile")
            if profile is not None:
                if not isinstance(profile, str) or profile not in VALID_PROFILES:
                    allowed = ", ".join(VALID_PROFILES)
                    raise ValueError(f"profile must be one of: {allowed}")
                self.profile = profile
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
                self.semantic_levels = tuple(
                    sorted(levels, key=VALID_SEMANTIC_LEVELS.index)
                )
            elif action == "set":
                # Legacy `set` always resolved its filter from the call, so an
                # omitted level list meant "no level filter" rather than "keep".
                self.semantic_levels = None
            self.collapsed = False
        changed = before != self._effective_state()
        return {
            **self.status(),
            "changed": changed,
            "refreshRequired": changed,
            "notification": "notifications/tools/list_changed" if changed else None,
        }, changed
