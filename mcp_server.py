#!/usr/bin/env python3
"""Local stdio MCP server for the Branch Cable Trophy Onshape workflow."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from onshape_tools.client import CREDENTIALS_PATH, STATE_PATH, load_json, parameter_payload
from onshape_tools.operations import (
    check_model,
    create_validation_part_studio,
    feature_studio_status,
    instantiate_feature,
    list_document_elements,
    load_parameter_set,
    public_state,
    render_preview,
    run_validation_pipeline,
    upload_feature_studio,
)

SERVER_NAME = "onshape-branch-cable-trophy"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2025-06-18"


def object_schema(
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def mutating_confirmation() -> dict[str, Any]:
    return {
        "type": "boolean",
        "const": True,
        "description": "Must be true. This explicitly acknowledges the documented remote mutation.",
    }


PARAMETER_VALUE_SCHEMA = {
    "description": "A FeatureScript expression string, number, or boolean.",
    "oneOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "boolean"},
    ],
}
PARAMETER_SET_SCHEMA = {
    "type": "string",
    "enum": ["default", "preview"],
    "description": "default is detailed (132 parts); preview is simplified (65 parts).",
}
VIEW_SCHEMA = {
    "type": "string",
    "enum": ["front", "right", "top", "iso", "reference_like"],
}
MODE_SCHEMA = {"type": "string", "enum": ["detailed", "simplified"]}


def _local_state(arguments: dict[str, Any]) -> dict[str, Any]:
    state = load_json(STATE_PATH)
    return {
        "state": public_state(state, bool(arguments.get("redact_ids", False))),
        "credentialsConfigured": CREDENTIALS_PATH.is_file(),
    }


def _parameter_set(arguments: dict[str, Any]) -> dict[str, Any]:
    name = arguments["name"]
    return {"name": name, "parameters": load_parameter_set(name)}


def _parameter_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    parameters = arguments["parameters"]
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")
    return {"parameters": parameter_payload(parameters)}


def _render_preview(arguments: dict[str, Any]) -> dict[str, Any]:
    result = render_preview(
        view=arguments["view"],
        width=int(arguments.get("width", 900)),
        height=int(arguments.get("height", 900)),
        save=bool(arguments.get("save", False)),
        part_studio_id=arguments.get("part_studio_id"),
    )
    include_image = bool(arguments.get("include_image", True))
    if not include_image:
        result.pop("base64", None)
    return result


def _confirm(arguments: dict[str, Any]) -> None:
    if arguments.get("confirm_mutation") is not True:
        raise ValueError("confirm_mutation must be true for this mutating tool")


def _upload(arguments: dict[str, Any]) -> dict[str, Any]:
    _confirm(arguments)
    return upload_feature_studio()


def _create_part_studio(arguments: dict[str, Any]) -> dict[str, Any]:
    _confirm(arguments)
    return create_validation_part_studio(
        name=arguments.get("name", "Cable trophy model validation"),
        save_to_project_state=bool(arguments.get("save_to_project_state", True)),
    )


def _instantiate(arguments: dict[str, Any]) -> dict[str, Any]:
    _confirm(arguments)
    overrides = arguments.get("overrides")
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("overrides must be an object")
    return instantiate_feature(
        parameter_set=arguments.get("parameter_set", "default"),
        overrides=overrides,
        part_studio_id=arguments.get("part_studio_id"),
    )


def _pipeline(arguments: dict[str, Any]) -> dict[str, Any]:
    _confirm(arguments)
    return run_validation_pipeline(
        parameter_set=arguments.get("parameter_set", "default"),
        render=bool(arguments.get("render_previews", True)),
    )


ToolHandler = Callable[[dict[str, Any]], Any]
TOOLS: list[dict[str, Any]] = [
    {
        "name": "onshape_get_project_state",
        "description": (
            "Read the project's non-secret Onshape document/workspace/element configuration and report "
            "whether a credentials file is configured. This is a local operation: it does not read or "
            "return credential values and makes no network request. Use it to understand which existing "
            "Feature Studio and Part Studio subsequent tools target."
        ),
        "inputSchema": object_schema({
            "redact_ids": {
                "type": "boolean",
                "default": False,
                "description": "Mask most characters of document, workspace, and element IDs.",
            }
        }),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_get_parameter_set",
        "description": (
            "Read one maintained local parameter set for the Branch Cable Trophy FeatureScript. "
            "The default set produces the detailed 132-part model; preview produces the simplified "
            "65-part model. This does not read credentials or contact Onshape."
        ),
        "inputSchema": object_schema({"name": PARAMETER_SET_SCHEMA}, ["name"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_build_parameter_payload",
        "description": (
            "Convert a local parameter mapping into Onshape's explicit custom-feature parameter blocks. "
            "Booleans become BTMParameterBoolean values; strings and numbers become quantity expressions. "
            "This deterministic local helper makes no network request and does not validate FeatureScript bounds."
        ),
        "inputSchema": object_schema({
            "parameters": {
                "type": "object",
                "additionalProperties": PARAMETER_VALUE_SCHEMA,
                "description": "FeatureScript parameter IDs mapped to expressions or booleans.",
            }
        }, ["parameters"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "onshape_list_document_elements",
        "description": (
            "List elements in the configured Onshape workspace, including names, element types, IDs, and "
            "microversions. This makes one authenticated read-only Onshape request. Use it to inspect current "
            "workspace state before choosing a Feature Studio or Part Studio operation."
        ),
        "inputSchema": object_schema(),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "onshape_get_feature_studio_status",
        "description": (
            "Read the configured Feature Studio metadata and compiled feature specifications. It reports "
            "whether branchCableTrophyDisplay is exposed and how many parameters its compiled specification "
            "contains. This uses authenticated read-only Onshape requests and does not upload source."
        ),
        "inputSchema": object_schema(),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "onshape_check_model",
        "description": (
            "Validate an existing Part Studio through read-only Onshape requests. The result checks custom "
            "feature status, exact part count, required part-name prefixes, and bounding limits; it returns "
            "all invariant errors without changing the Part Studio or writing the project report file."
        ),
        "inputSchema": object_schema({
            "mode": {**MODE_SCHEMA, "default": "detailed"},
            "part_studio_id": {
                "type": "string",
                "description": "Optional target override; defaults to config/onshape-state.json.",
            },
        }),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "onshape_render_preview",
        "description": (
            "Request one shaded PNG rendering of the existing configured Part Studio from Onshape. The remote "
            "operation is read-only but may consume rendering resources. By default it returns the image as MCP "
            "image content without writing a file; set save=true to also write outputs/previews/<view>.png."
        ),
        "inputSchema": object_schema({
            "view": VIEW_SCHEMA,
            "width": {"type": "integer", "minimum": 64, "maximum": 2000, "default": 900},
            "height": {"type": "integer", "minimum": 64, "maximum": 2000, "default": 900},
            "include_image": {
                "type": "boolean",
                "default": True,
                "description": "Return the PNG as MCP image content in addition to metadata.",
            },
            "save": {
                "type": "boolean",
                "default": False,
                "description": "Also save the PNG under outputs/previews; this is a local file write.",
            },
            "part_studio_id": {"type": "string"},
        }, ["view"]),
        "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "onshape_upload_feature_studio",
        "description": (
            "Upload branchCableTrophyDisplay.fs to the configured Feature Studio and require the compiled "
            "branchCableTrophyDisplay specification. This overwrites cloud Feature Studio contents and may "
            "fail on microversion skew; call only when the user intends that remote mutation."
        ),
        "inputSchema": object_schema({"confirm_mutation": mutating_confirmation()}, ["confirm_mutation"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "onshape_create_validation_part_studio",
        "description": (
            "Create a new Part Studio in the configured Onshape document. Each call creates another cloud "
            "element; by default it also changes config/onshape-state.json to target the new element. This is "
            "not a read-only inspection tool and requires explicit mutation confirmation."
        ),
        "inputSchema": object_schema({
            "confirm_mutation": mutating_confirmation(),
            "name": {"type": "string", "default": "Cable trophy model validation"},
            "save_to_project_state": {"type": "boolean", "default": True},
        }, ["confirm_mutation"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    },
    {
        "name": "onshape_instantiate_feature",
        "description": (
            "Add the Branch Cable Trophy custom feature to a target Part Studio using a maintained explicit "
            "parameter set and optional known-parameter overrides. Repeated calls add additional cloud features; "
            "this requires explicit mutation confirmation and returns the regeneration status."
        ),
        "inputSchema": object_schema({
            "confirm_mutation": mutating_confirmation(),
            "parameter_set": {**PARAMETER_SET_SCHEMA, "default": "default"},
            "overrides": {
                "type": "object",
                "additionalProperties": PARAMETER_VALUE_SCHEMA,
                "description": "Optional overrides; unknown parameter IDs are rejected.",
            },
            "part_studio_id": {"type": "string"},
        }, ["confirm_mutation"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    },
    {
        "name": "onshape_run_validation_pipeline",
        "description": (
            "Run the complete remote validation pipeline: upload FeatureScript, create a new Part Studio, save "
            "that ID to local project state, instantiate the feature, validate invariants, and optionally render "
            "five PNG previews. This performs several cloud and local mutations and requires explicit confirmation."
        ),
        "inputSchema": object_schema({
            "confirm_mutation": mutating_confirmation(),
            "parameter_set": {**PARAMETER_SET_SCHEMA, "default": "default"},
            "render_previews": {"type": "boolean", "default": True},
        }, ["confirm_mutation"]),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
    },
]

HANDLERS: dict[str, ToolHandler] = {
    "onshape_get_project_state": _local_state,
    "onshape_get_parameter_set": _parameter_set,
    "onshape_build_parameter_payload": _parameter_payload,
    "onshape_list_document_elements": lambda _: {"elements": list_document_elements()},
    "onshape_get_feature_studio_status": lambda _: feature_studio_status(),
    "onshape_check_model": lambda arguments: check_model(
        mode=arguments.get("mode", "detailed"),
        part_studio_id=arguments.get("part_studio_id"),
    ),
    "onshape_render_preview": _render_preview,
    "onshape_upload_feature_studio": _upload,
    "onshape_create_validation_part_studio": _create_part_studio,
    "onshape_instantiate_feature": _instantiate,
    "onshape_run_validation_pipeline": _pipeline,
}


def _json_text(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def tool_result(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        handler = HANDLERS[name]
    except KeyError as error:
        raise ValueError(f"Unknown tool: {name}") from error
    try:
        value = handler(arguments)
        if name == "onshape_render_preview" and value.get("base64"):
            encoded = value.pop("base64")
            return {
                "content": [
                    {"type": "text", "text": _json_text(value)},
                    {"type": "image", "data": encoded, "mimeType": "image/png"},
                ],
                "structuredContent": value,
                "isError": False,
            }
        return {
            "content": [{"type": "text", "text": _json_text(value)}],
            "structuredContent": value,
            "isError": False,
        }
    except Exception as error:
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        safe_error = f"{type(error).__name__}: {error}"
        return {
            "content": [{"type": "text", "text": safe_error}],
            "isError": True,
        }


def response(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


def dispatch(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        return response(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "Use read-only inspection tools unless the user explicitly requests a cloud mutation. "
                "Mutating tools require confirm_mutation=true and never return credentials."
            ),
        })
    if method == "ping":
        return response(request_id, {})
    if method == "tools/list":
        return response(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return response(request_id, error={"code": -32602, "message": "Invalid tools/call parameters"})
        try:
            return response(request_id, tool_result(name, arguments))
        except ValueError as error:
            return response(request_id, error={"code": -32602, "message": str(error)})
    return response(request_id, error={"code": -32601, "message": f"Method not found: {method}"})


def serve() -> None:
    """Serve newline-delimited JSON-RPC over stdin/stdout."""
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("Message must be a JSON object")
            outgoing = dispatch(message)
        except (json.JSONDecodeError, ValueError) as error:
            outgoing = response(None, error={"code": -32700, "message": f"Parse error: {error}"})
        if outgoing is not None:
            sys.stdout.write(json.dumps(outgoing, separators=(",", ":"), ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    serve()
