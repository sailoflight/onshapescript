"""Which tools this connection advertises, and the collapse/expand control.

The mechanism here -- profile selection, absorbed compatibility names, the
six-level semantic filter, the gateway's curated set, and the connection-scoped
collapse/expand state machine -- is **not implemented in this module any more**.
It is the shared ``mcp_surface`` library (``Surface`` + ``SurfacePolicy`` +
``ToolViewState``), installed from the wheel pinned in
``onshape_browser_mode/requirements-windows.txt`` and recorded in
``docs/development/MCP_SURFACE_INTEGRATION.md``. This module is the Onshape
declaration layer: it maps this project's existing constants and the browser
semantics records onto one ``SurfacePolicy``, and it keeps the public names that
the server, the tests and the development tools import.

What stays here, deliberately:

* the deployment switch -- the host-local ``tool_views.local.toml``,
  ``ONSHAPE_MCP_TOOL_EXPOSURE``/``ONSHAPE_MCP_TOOL_PROFILE`` and the explicit
  arguments. Where a config file lives is a deployment fact, not a library fact,
  so the shared library takes the mode as a parameter and never reads a file.
* the Onshape vocabulary -- profile names and their membership rules, the
  curated gateway list, the browser semantic records, the absorbed wrapper set.

Hiding is context routing, never authority: a name absent from ``tools/list``
stays callable by exact registered name, and every confirmation, quota, pacing
and acceptance gate still answers. The three control tools
(``mcp_tool_catalog``/``mcp_tool_view``/``mcp_tool_invoke``) are listed in every
mode for the reason measured live 2026-09-21: a real client refused a name that
had left ``tools/list`` with "unknown tool", so the only route to a hidden name
is an advertised door that forwards to the SAME handler.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Callable

from mcp_surface import (
    ProfileRule,
    Surface,
    SurfacePolicy,
    SurfaceRequestError,
    ToolRecord,
    ViewSwitchUnavailable,
)
from mcp_surface import ToolViewState as _LibraryViewState
from mcp_surface import VALID_EXPOSURE_MODES, VALID_EXPANDED_VIEWS, VALID_VIEW_ACTIONS

CONTROL_TOOL_NAME = "mcp_tool_view"
CATALOG_TOOL_NAME = "mcp_tool_catalog"
INVOKE_TOOL_NAME = "mcp_tool_invoke"
#: The gateway/control surface: discovery, view status, and the generic entry
#: point. These three are listed under EVERY profile, because a profile that
#: hides a name it cannot route is a dead end for a client that refuses names
#: absent from `tools/list` (measured live 2026-09-21).
CONTROL_TOOL_NAMES = frozenset(
    {CONTROL_TOOL_NAME, CATALOG_TOOL_NAME, INVOKE_TOOL_NAME}
)
#: The declared control order the shared surface routes by, positionally:
#: catalog, view, invoke. It is what makes the gateway list lead with
#: `mcp_tool_catalog` and what `status().gateway.core` reports.
CONTROL_TOOL_ORDER = (CATALOG_TOOL_NAME, CONTROL_TOOL_NAME, INVOKE_TOOL_NAME)

# Host-local switch for the exposure mode, in the same shape as the other
# module-local configurations (`<name>.toml` in the module's `config/`
# directory, overridden by a gitignored `<name>.local.toml`). It exists because
# the ordinary deployment is launched by an external bridge whose registration
# owns the child environment: a mode an operator cannot set without editing
# someone else's registry is not really configurable. Precedence is explicit
# argument, then `ONSHAPE_MCP_TOOL_EXPOSURE`, then this file, then `semantic`.
# The default is the fixed, always-expanded ordinary view on purpose: a
# collapsed `dynamic` start requires the client to process
# `notifications/tools/list_changed`, which is a capability not every client
# has (matching `mcp_surface` dev3's `resolve_exposure` default), and the
# compressed `gateway` set is a curation decision rather than a neutral start.
# Both stay fully available as explicit choices.
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

#: The gateway `status()` reason, kept in the declared order the gateway lists
#: so an operator reads the trade rather than guessing at it. The shared library
#: ships a generic default; this project's measured figures replace it.
GATEWAY_REASON = (
    "Curated representatives are listed because retrieval is not free (a "
    "3-result search ~6.8 kB, a modelling describe ~10.5 kB); everything else "
    "is reached by exact name or by mcp_tool_catalog action=index."
)

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

#: Search tie-break order for the catalog, most useful first; `None` is a legal
#: member and means "a record with no declared level". It is declared once here
#: and read by `tool_catalog` so the ordering cannot drift from the surface.
BROWSER_LEVEL_PRIORITY_ORDER: tuple[str | None, ...] = (
    "L5", "L4", "L2", "L6", None, "L3", "L1",
)

#: The two-step lookups the product itself prescribes. A chain advertised
#: half-way costs the caller the first step's rent AND a hidden-name round, so
#: the shared surface reports the violation instead of the catalogue hiding it.
PRESCRIBED_LOOKUP_CHAINS: tuple[tuple[str, ...], ...] = (
    ("docs_search", "docs_section"),
    ("fs_search", "fs_get_function"),
    ("onshape_api_search", "onshape_api_endpoint"),
)

#: The geometry profile matches by substring, not by prefix: the surviving names
#: are spread across `browser_*`, `onshape_*` and the FDM module.
_GEOMETRY_NAME_TOKENS = ("_export_step", "_geometry_", "wall_thickness")


def _geometry_profile_includes(record: ToolRecord) -> bool:
    return any(token in record.name for token in _GEOMETRY_NAME_TOKENS)


def _semantic_record(name: str) -> Any:
    if not name.startswith("browser_"):
        return None
    from onshape_browser_mode.semantics import TOOL_SEMANTICS

    return TOOL_SEMANTICS.get(name)


def _declared_metadata(name: str) -> dict[str, Any]:
    """The view-selection facts this project declares for one tool name.

    Browser-namespace records come from `onshape_browser_mode.semantics`; a name
    with no record stays visible by default and unlevelled, which is what the
    ordinary (non-browser) registry relies on.
    """
    record = _semantic_record(name)
    return {
        "level": record.level if record is not None else None,
        "default_exposure": record.default_exposure if record is not None else True,
        "absorbed": name in ABSORBED_COMPATIBILITY_TOOLS,
    }


def surface_policy() -> SurfacePolicy:
    """This project's declaration, as the shared library's one policy object."""
    return SurfacePolicy(
        control_names=CONTROL_TOOL_ORDER,
        profiles=(
            ProfileRule(
                "browser",
                _PROFILE_DESCRIPTIONS["browser"],
                prefixes=("browser_",),
            ),
            ProfileRule(
                "rest",
                _PROFILE_DESCRIPTIONS["rest"],
                prefixes=("onshape_",),
            ),
            ProfileRule(
                "featurescript",
                _PROFILE_DESCRIPTIONS["featurescript"],
                prefixes=("fs_",),
                names=frozenset(_FEATURESCRIPT_ONSHAPE_TOOLS),
            ),
            ProfileRule(
                "documentation",
                _PROFILE_DESCRIPTIONS["documentation"],
                prefixes=("docs_", "fs_"),
                names=REST_REFERENCE_TOOL_NAMES,
            ),
            ProfileRule(
                "geometry",
                _PROFILE_DESCRIPTIONS["geometry"],
                predicate=_geometry_profile_includes,
            ),
        ),
        curated=GATEWAY_CURATED_TOOL_NAMES,
        absorbed=ABSORBED_COMPATIBILITY_TOOLS,
        always_visible=frozenset(_ALWAYS_VISIBLE_BROWSER_TOOLS),
        levels=VALID_SEMANTIC_LEVELS,
        rank_levels=BROWSER_LEVEL_PRIORITY_ORDER,
        chains=PRESCRIBED_LOOKUP_CHAINS,
        default_profile="default",
        default_expanded_view="gateway",
        gateway_reason=GATEWAY_REASON,
    )


def build_surface(
    tools: list[dict[str, Any]],
    *,
    metadata: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> Surface:
    """Wrap a registry as the shared library's validated ``Surface``.

    ``metadata`` is the extension hook: the catalog supplies the Onshape module
    taxonomy, network classification and confirmation override; the view layer
    needs none of that. Construction validates the declaration, so a curated name
    that is not registered or a level outside the vocabulary fails at build time
    instead of silently dropping a tool from one session.
    """
    records: list[ToolRecord] = []
    for tool in tools:
        name = str(tool["name"])
        fields = _declared_metadata(name)
        if metadata is not None:
            fields.update(metadata(name, tool))
        records.append(ToolRecord.from_payload(tool, **fields))
    return Surface(records, surface_policy())


#: The view layer builds its surface once per registry object. The registry is
#: immutable after `server.TOOLS` is assembled, and the strong reference to
#: ``tools`` keeps the ``id`` from being reused by a later, different list.
_VIEW_SURFACE_CACHE: dict[int, tuple[list[dict[str, Any]], Surface]] = {}


def view_surface(tools: list[dict[str, Any]]) -> Surface:
    key = id(tools)
    cached = _VIEW_SURFACE_CACHE.get(key)
    if cached is not None and cached[0] is tools:
        return cached[1]
    surface = build_surface(tools)
    _VIEW_SURFACE_CACHE[key] = (tools, surface)
    return surface


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
    """The exposure mode, defaulting to the fixed, always-expanded `semantic`.

    `dynamic` is a deliberate, explicit choice: a collapsed start is only correct
    for a client that can refresh `tools/list`. `gateway` is a curation choice,
    also explicit, not a neutral starting point.
    """
    if value is not None:
        mode = value
    elif "ONSHAPE_MCP_TOOL_EXPOSURE" in os.environ:
        mode = os.environ["ONSHAPE_MCP_TOOL_EXPOSURE"]
    else:
        mode = _local_section("exposure").get("mode", "semantic")
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


def select_view_tools(
    tools: list[dict[str, Any]],
    *,
    profile: str,
    semantic_levels: tuple[str, ...] | None,
) -> list[dict[str, Any]]:
    """The advertised subset for one profile, as raw tool payloads.

    Delegates to the shared surface's ``select``: profile membership, absorbed
    compatibility names and the two level semantics (ordinary default exposure
    versus an explicit tier query) are all the library's, so this project keeps
    no second copy of them.
    """
    if profile not in VALID_PROFILES:
        raise ValueError(f"Unknown tool profile: {profile}")
    surface = view_surface(tools)
    return [
        record.advertised()
        for record in surface.select(profile=profile, levels=semantic_levels)
    ]


class ToolViewState:
    """One connection's tool-display state, delegating to ``mcp_surface``.

    SCOPE: this state is CONNECTION-scoped, never conversation-scoped -- the
    shared state machine says so in ``status()["scope"]``. A stdio server sees a
    connection and the messages on it, not the conversations a client
    multiplexes over it, so an expand performed for one conversation is observed
    by EVERY conversation on that connection.

    Collapse is pure in-memory state: it writes nothing anywhere and is NOT the
    same as exiting the browser or revoking a permission. Hidden tools remain
    callable by exact registered name and every confirmation, quota, pacing and
    acceptance gate still answers.

    This wrapper exists to keep the project's public construction shape
    (``ToolViewState(tools=..., mode=..., profile=...)``) and its error
    vocabulary. A cold start built by `from_environment` enters `dynamic`
    COLLAPSED, with `gateway` remembered as the set an unqualified expand opens;
    the field defaults describe a directly constructed state instead, preserving
    the legacy explicit-profile expansion (`collapsed=False` over
    `expanded_view="profile"`) that embedding code and tests have used.
    """

    def __init__(
        self,
        tools: list[dict[str, Any]],
        mode: str,
        profile: str,
        semantic_levels: tuple[str, ...] | None = None,
        initial_profile: str | None = None,
        collapsed: bool = False,
        expanded_view: str = "profile",
    ) -> None:
        self.tools = tools
        try:
            self._state = _LibraryViewState(
                surface=view_surface(tools),
                mode=mode,
                profile=profile,
                semantic_levels=(
                    tuple(semantic_levels) if semantic_levels is not None else None
                ),
                initial_profile=initial_profile,
                collapsed=collapsed,
                expanded_view=expanded_view,
            )
        except SurfaceRequestError as error:
            raise ValueError(str(error)) from error

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
            # their own fixed set, so `expanded_view` is inert there: the status
            # still reports it alongside `switchingAvailable=false`.
            collapsed=mode == "dynamic",
            expanded_view="gateway",
        )

    # -- mirrored state ----------------------------------------------------

    @property
    def mode(self) -> str:
        return self._state.mode

    @property
    def profile(self) -> str:
        return self._state.profile

    @profile.setter
    def profile(self, value: str) -> None:
        self._state.profile = value

    @property
    def semantic_levels(self) -> tuple[str, ...] | None:
        return self._state.semantic_levels

    @semantic_levels.setter
    def semantic_levels(self, value: tuple[str, ...] | None) -> None:
        self._state.semantic_levels = value

    @property
    def initial_profile(self) -> str | None:
        return self._state.initial_profile

    @property
    def collapsed(self) -> bool:
        return self._state.collapsed

    @collapsed.setter
    def collapsed(self, value: bool) -> None:
        self._state.collapsed = value

    @property
    def expanded_view(self) -> str:
        return self._state.expanded_view

    @expanded_view.setter
    def expanded_view(self, value: str) -> None:
        self._state.expanded_view = value

    @property
    def switching_available(self) -> bool:
        return self._state.switching_available

    @property
    def list_changed_capability(self) -> bool:
        return self._state.list_changed_capability

    @property
    def state(self) -> str:
        return self._state.state

    # -- advertised set ----------------------------------------------------

    def listed_tools(self) -> list[dict[str, Any]]:
        return [record.advertised() for record in self._state.listed()]

    def _normalize_status(self, status: dict[str, Any]) -> dict[str, Any]:
        """Restore this project's declared status shape.

        The shared library reports the same facts, but orders the profile list
        with the reserved names first and ships its own gateway core order and
        generic reason. The gateway core order and the `name -> description`
        profile table are this project's public contract, so they are restored
        here rather than left to the library's generic defaults.
        """
        status["gateway"] = {
            "core": sorted(GATEWAY_CORE_TOOL_NAMES),
            "curated": list(GATEWAY_CURATED_TOOL_NAMES),
            "reason": GATEWAY_REASON,
        }
        status["profiles"] = [
            {"name": name, "description": _PROFILE_DESCRIPTIONS[name]}
            for name in VALID_PROFILES
        ]
        return status

    def status(self) -> dict[str, Any]:
        # `state`/`expandedView`/`scope` describe the collapse/expand control.
        # `scope` says outright that this state belongs to the CONNECTION: a
        # shared or reused connection shows the same view to every conversation.
        return self._normalize_status(self._state.status())

    def apply(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        # Request validation stays here because the messages are this project's
        # public error contract; the state transition itself is the library's.
        self._validate_arguments(arguments)
        try:
            payload, changed = self._state.apply(arguments)
        except ViewSwitchUnavailable as error:
            raise ValueError(self._switch_refusal()) from error
        except SurfaceRequestError as error:  # defensive: no path should reach it
            raise ValueError(str(error)) from error
        return self._normalize_status(payload), changed

    def _switch_refusal(self) -> str:
        return (
            "tool view switching requires ONSHAPE_MCP_TOOL_EXPOSURE=dynamic; "
            "the current mode is a fixed compatibility view"
        )

    def _validate_arguments(self, arguments: dict[str, Any]) -> None:
        action = arguments.get("action", "status")
        if action not in VALID_VIEW_ACTIONS:
            raise ValueError("action must be status, set, reset, expand, or collapse")
        if action == "status":
            return
        if not self.switching_available:
            raise ValueError(self._switch_refusal())
        if action in {"reset", "collapse"}:
            return
        # `expand` opens a display set; `set` is its compatibility alias and,
        # like the action it replaces, defaults to the startup-profile view and
        # resolves the level filter from its own arguments.
        requested_view = arguments.get("expanded_view")
        if requested_view is None:
            requested_view = "profile" if action == "set" else self.expanded_view
        if (
            not isinstance(requested_view, str)
            or requested_view not in VALID_EXPANDED_VIEWS
        ):
            allowed = ", ".join(VALID_EXPANDED_VIEWS)
            raise ValueError(f"expanded_view must be one of: {allowed}")
        profile = arguments.get("profile")
        if profile is not None:
            if not isinstance(profile, str) or profile not in VALID_PROFILES:
                allowed = ", ".join(VALID_PROFILES)
                raise ValueError(f"profile must be one of: {allowed}")
        levels = arguments.get("semantic_levels")
        if levels is not None:
            if (
                not isinstance(levels, list)
                or not levels
                or not all(
                    isinstance(level, str) and level in VALID_SEMANTIC_LEVELS
                    for level in levels
                )
            ):
                raise ValueError(
                    "semantic_levels must be a non-empty list containing L1 through L6"
                )
            if len(set(levels)) != len(levels):
                raise ValueError("semantic_levels must not contain duplicates")
