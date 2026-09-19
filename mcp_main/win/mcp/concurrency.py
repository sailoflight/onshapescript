"""Conservative concurrency contracts derived from the authoritative tool registry.

These contracts describe coordination requirements. They do not implement a
lease, grant authority, or make a multi-call workflow atomic.
"""

from __future__ import annotations

from typing import Any

CONCURRENCY_CONTRACT_VERSION = "1"

_TARGET_ARGUMENTS = (
    "document_id",
    "documentId",
    "workspace_id",
    "workspaceId",
    "element_id",
    "elementId",
    "part_studio_id",
)

_CONNECTION_LOCAL_TOOLS = {"mcp_tool_view"}
_SHARED_TARGET_STATE_READERS = {
    "fs_check_version",
    "onshape_get_project_state",
}
_SHARED_TARGET_STATE_WRITERS = {
    "browser_sync_rest_state",
    "onshape_create_validation_part_studio",
    "onshape_get_feature_studio_status",
    "onshape_list_document_elements",
    "onshape_run_validation_pipeline",
}
_SHARED_LOCAL_STATE_WRITERS = {
    "browser_configure_geometry_backend",
    "fs_update_reference",
    "onshape_configure_geometry_backend",
}
_SHARED_LOCAL_STATE_READERS = {
    "browser_geometry_status",
    "fs_check_version",
    "fs_get_function",
    "fs_get_type",
    "fs_guide_section",
    "fs_library_source",
    "fs_list_functions",
    "fs_list_modules",
    "fs_quick_reference",
    "fs_search",
    "onshape_api_auth",
    "onshape_api_endpoint",
    "onshape_api_error_codes",
    "onshape_api_list_tags",
    "onshape_api_quota",
    "onshape_api_schema",
    "onshape_api_search",
    "onshape_geometry_status",
}


def _scope_key_paths(properties: dict[str, Any]) -> list[str]:
    return [
        f"params.arguments.{name}"
        for name in _TARGET_ARGUMENTS
        if name in properties
    ]


def _shared_target_state(name: str) -> str:
    if name in _SHARED_TARGET_STATE_WRITERS:
        return "write"
    if name in _SHARED_TARGET_STATE_READERS:
        return "read"
    return "none"


def _shared_local_state(name: str) -> str:
    if name in _SHARED_LOCAL_STATE_WRITERS:
        return "write"
    if name in _SHARED_LOCAL_STATE_READERS:
        return "read"
    return "none"


def concurrency_contract(tool: dict[str, Any]) -> dict[str, Any]:
    """Return one worst-case concurrency contract for a public tool."""
    name = str(tool["name"])
    schema = tool.get("inputSchema") or {}
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or ())
    cost = tool.get("cost") or {}
    side_effects = {str(value) for value in cost.get("side_effects") or ()}
    mutating = bool(cost.get("mutating", False))
    depends_on_page = bool(cost.get("requires_browser_session", False))
    shared_target_state = _shared_target_state(name)
    shared_local_state = _shared_local_state(name)
    scope_key_paths = _scope_key_paths(properties)
    has_required_document = any(
        key in required for key in ("document_id", "documentId")
    )
    has_required_target = any(key in required for key in _TARGET_ARGUMENTS)
    has_optional_target = bool(scope_key_paths) and not has_required_target
    has_persistent_side_effect = bool(side_effects)

    if name in _CONNECTION_LOCAL_TOOLS:
        access = "connection_local"
        scope = "connection"
        reason = (
            "state is isolated to the current MCP client in dynamic mode; "
            "fixed exposure modes cannot change it"
        )
    elif shared_target_state == "write":
        access = "exclusive_workflow"
        scope = "registration_target_state"
        reason = "tool can change shared project or REST target state"
    elif shared_local_state == "write":
        access = "exclusive_workflow"
        scope = "registration"
        reason = "tool can change registration-owned local state"
    elif depends_on_page:
        access = "exclusive_workflow"
        scope = "browser_profile"
        reason = "tool depends on the shared browser profile or current page"
    elif has_required_document:
        access = "exclusive_workflow" if mutating or has_persistent_side_effect else "shared_read"
        scope = "explicit_document"
        reason = "document identity is explicit in the required arguments"
    elif scope_key_paths:
        access = "exclusive_workflow" if mutating or has_persistent_side_effect else "shared_read"
        scope = "explicit_target"
        reason = "concurrent use requires caller-supplied target arguments"
    elif mutating or has_persistent_side_effect:
        access = "exclusive_workflow"
        scope = "registration"
        reason = "no reliable document scope can be extracted from the schema"
    elif shared_target_state == "read":
        access = "shared_read"
        scope = "registration_target_state"
        reason = "tool reads the registration's shared target state"
    elif shared_local_state == "read":
        access = "shared_read"
        scope = "registration"
        reason = "tool reads registration-owned local state that another tool may update"
    else:
        access = "shared_read"
        scope = "none"
        reason = "tool is read-only and independent of browser and shared state"

    requires_explicit_target = has_optional_target
    safe_during_mutation = (
        access in {"shared_read", "connection_local"}
        and shared_target_state == "none"
        and shared_local_state == "none"
        and not depends_on_page
        and not requires_explicit_target
        and not has_persistent_side_effect
    )
    if has_required_document:
        scope_key_coverage = "document_id_required"
    elif has_required_target:
        scope_key_coverage = "non_document_target_required"
    elif scope_key_paths:
        scope_key_coverage = "optional"
    else:
        scope_key_coverage = "none"
    safe_with_explicit_target = (
        access == "shared_read"
        and requires_explicit_target
        and shared_target_state == "none"
        and shared_local_state == "none"
        and not depends_on_page
        and not has_persistent_side_effect
    )
    coordination_scopes: list[str] = []
    if scope not in {"none", "connection"}:
        coordination_scopes.append(scope)
    if scope == "browser_profile":
        if has_required_document:
            coordination_scopes.append("explicit_document")
        elif scope_key_paths:
            coordination_scopes.append("explicit_target")
    return {
        "contractVersion": CONCURRENCY_CONTRACT_VERSION,
        "workflowIsolation": "none",
        "access": access,
        "scope": scope,
        "coordinationScopes": coordination_scopes,
        "scopeKeyPaths": scope_key_paths,
        "scopeKeyCoverage": scope_key_coverage,
        "dependsOnCurrentBrowserPage": depends_on_page,
        "sharedTargetState": shared_target_state,
        "sharedLocalState": shared_local_state,
        "requiresExplicitTargetForConcurrentUse": requires_explicit_target,
        "safeDuringMutationWorkflow": safe_during_mutation,
        "safeDuringMutationWorkflowWhenExplicitTarget": safe_with_explicit_target,
        "conditionEvaluatedAtRuntime": False,
        "callerMustVerifyScopeKeyPresence": requires_explicit_target,
        "configuredDefaultTargetAllowedDuringConcurrentUse": False,
        "reason": reason,
    }


def annotate_concurrency_contracts(tools: list[dict[str, Any]]) -> None:
    """Attach derived contracts after cost and side-effect metadata is complete."""
    for tool in tools:
        cost = tool.setdefault("cost", {})
        cost["concurrency"] = concurrency_contract(tool)
