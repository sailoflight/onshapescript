#!/usr/bin/env python3
"""Parse the vendored Onshape REST API OpenAPI spec into structured JSON indexes.

reference/raw/onshape-api/openapi.json is the live OpenAPI 3.0 definition served by
Onshape at /api/openapi (fetched by scripts/fetch_onshape_api.py). This script
flattens it so the MCP onshape_api_* tools can answer REST questions offline:

Outputs (all data is vendored; nothing is fetched here):
  reference/index/onshape-api/api_index.json  - {tags, endpoints, schemas} with every
                   operation's path, method, parameters, responses, and shallow
                   schema shapes (tier 2: full detail, read on demand)
  reference/quick/onshape-api/api_quick.json  - compact one-line-per-entry surface
                   index for cheap machine indexing (tier 1: first look)
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "reference" / "raw"
ONSHAPE_API_DIR = RAW_DIR / "onshape-api"
OPENAPI_PATH = ONSHAPE_API_DIR / "openapi.json"
INDEX_PATH = ROOT / "reference" / "index" / "onshape-api" / "api_index.json"
QUICK_PATH = ROOT / "reference" / "quick" / "onshape-api" / "api_quick.json"

# HTTP methods materialized in a path item; "parameters" and other keys are skipped.
HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_ref(ref: str | None) -> str | None:
    """'#/components/schemas/BTThing' -> 'BTThing'."""
    return ref.split("/")[-1] if ref else None


def schema_brief(schema: dict[str, Any]) -> dict[str, Any]:
    """Flatten a schema node to the fields a caller needs to see at a glance."""
    if not schema:
        return {}
    if "$ref" in schema:
        return {"type": None, "ref": resolve_ref(schema["$ref"])}
    out: dict[str, Any] = {"type": schema.get("type")}
    for key in ("format", "enum", "default", "minimum", "maximum"):
        if key in schema:
            out[key] = schema[key]
    items = schema.get("items")
    if schema.get("type") == "array" and isinstance(items, dict):
        if "$ref" in items:
            out["itemsRef"] = resolve_ref(items["$ref"])
        elif "type" in items:
            out["itemsType"] = items["type"]
    return out


def parse_parameter(param: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": param.get("name"),
        "in": param.get("in"),
        "required": bool(param.get("required")),
        "description": param.get("description", ""),
        "schema": schema_brief(param.get("schema")),
    }


def parse_response(code: str, response: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"code": code, "description": response.get("description", "")}
    content = response.get("content") or {}
    if content:
        # Prefer the JSON representation when several are offered.
        chosen = next((k for k in content if "json" in k), next(iter(content)))
        schema = content[chosen].get("schema")
        if schema:
            if "$ref" in schema:
                out["schemaRef"] = resolve_ref(schema["$ref"])
            else:
                out["schema"] = schema_brief(schema)
    return out


def inline_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Flatten an inline (non-ref) schema — same shape as parse_schema output."""
    out: dict[str, Any] = {
        "type": schema.get("type"),
        "description": schema.get("description", ""),
    }
    if schema.get("required"):
        out["required"] = schema["required"]
    props = schema.get("properties")
    if props:
        out["properties"] = []
        for key, prop in props.items():
            item = {
                "name": key,
                "type": prop.get("type"),
                "ref": resolve_ref(prop.get("$ref")),
                "description": prop.get("description", ""),
            }
            if prop.get("enum"):
                item["enum"] = prop["enum"]
            items = prop.get("items")
            if isinstance(items, dict):
                if "$ref" in items:
                    item["itemsRef"] = resolve_ref(items["$ref"])
                elif "type" in items:
                    item["itemsType"] = items["type"]
            out["properties"].append(item)
    return out


def parse_request_body(op: dict[str, Any]) -> dict[str, Any] | None:
    body = op.get("requestBody")
    if not body:
        return None
    out: dict[str, Any] = {
        "required": bool(body.get("required")),
        "description": body.get("description", ""),
    }
    content = body.get("content") or {}
    if content:
        chosen = next((k for k in content if "json" in k), next(iter(content)))
        schema = content[chosen].get("schema")
        if schema:
            if "$ref" in schema:
                out["schemaRef"] = resolve_ref(schema["$ref"])
            else:
                out["schema"] = inline_schema(schema)
    return out


def _security_brief(scheme: dict[str, Any]) -> dict[str, Any]:
    brief: dict[str, Any] = {
        "type": scheme.get("type"),
        "description": scheme.get("description", ""),
    }
    flows = scheme.get("flows")
    if flows:
        brief["flows"] = {}
        for name, flow in flows.items():
            brief["flows"][name] = {
                key: value for key, value in flow.items()
                if key in ("authorizationUrl", "tokenUrl")
            }
            scopes = flow.get("scopes") or {}
            if scopes:
                brief["flows"][name]["scopes"] = list(scopes.keys())
    return brief


def parse_schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": name,
        "type": schema.get("type"),
        "description": schema.get("description", ""),
    }
    if schema.get("required"):
        out["required"] = schema["required"]
    if "enum" in schema:
        out["enum"] = schema["enum"]
    props = schema.get("properties")
    if props:
        out["properties"] = []
        for key, prop in props.items():
            item = {
                "name": key,
                "type": prop.get("type"),
                "ref": resolve_ref(prop.get("$ref")),
                "description": prop.get("description", ""),
            }
            if prop.get("enum"):
                item["enum"] = prop["enum"]
            items = prop.get("items")
            if isinstance(items, dict):
                if "$ref" in items:
                    item["itemsRef"] = resolve_ref(items["$ref"])
                elif "type" in items:
                    item["itemsType"] = items["type"]
            out["properties"].append(item)
    items = schema.get("items")
    if isinstance(items, dict):
        if "$ref" in items:
            out["itemsRef"] = resolve_ref(items["$ref"])
        elif "type" in items:
            out["itemsType"] = items["type"]
    return out


def build() -> dict[str, Any]:
    with OPENAPI_PATH.open(encoding="utf-8") as stream:
        spec = json.load(stream)

    info = spec.get("info", {})
    tags = [
        {"name": tag.get("name"), "description": tag.get("description", "")}
        for tag in spec.get("tags", [])
    ]

    endpoints: list[dict[str, Any]] = []
    global_security = spec.get("security", [])
    for path, item in spec.get("paths", {}).items():
        path_params = [parse_parameter(p) for p in item.get("parameters", [])] if item else []
        for method in HTTP_METHODS:
            op = item.get(method) if item else None
            if not op:
                continue
            params = path_params + [parse_parameter(p) for p in op.get("parameters", [])]
            endpoints.append({
                "path": path,
                "method": method,
                "operationId": op.get("operationId", ""),
                "summary": op.get("summary", ""),
                "description": op.get("description", ""),
                "tags": list(op.get("tags", [])),
                "deprecated": bool(op.get("deprecated")),
                "security": [
                    list(scheme.keys())[0] for scheme in op.get("security", global_security)
                ],
                "requestBody": parse_request_body(op),
                "parameters": params,
                "responses": [
                    parse_response(code, resp)
                    for code, resp in (op.get("responses") or {}).items()
                ],
            })
    endpoints.sort(key=lambda e: (e["path"], e["method"]))

    schemas = [
        parse_schema(name, body)
        for name, body in sorted((spec.get("components") or {}).get("schemas", {}).items())
    ]

    components = spec.get("components") or {}
    return {
        "sourceUrl": "https://cad.onshape.com/api/openapi",
        "openapiVersion": spec.get("openapi"),
        "specVersion": info.get("version"),
        "specTitle": info.get("title"),
        "baseUrl": (spec.get("servers") or [{}])[0].get("url", ""),
        "sourceSha256": sha256_of(OPENAPI_PATH),
        "securitySchemes": {
            name: _security_brief(scheme)
            for name, scheme in (components.get("securitySchemes") or {}).items()
        },
        "globalSecurity": [list(scheme.keys())[0] for scheme in global_security],
        "tags": tags,
        "endpoints": endpoints,
        "schemas": schemas,
    }


def build_quick(index: dict[str, Any]) -> dict[str, Any]:
    return {
        "specVersion": index["specVersion"],
        "tags": index["tags"],
        "endpoints": [
            {
                "path": e["path"],
                "method": e["method"],
                "operationId": e["operationId"],
                "summary": e["summary"],
                "tags": e["tags"],
                "deprecated": e["deprecated"],
                "hasRequestBody": bool(e["requestBody"]),
            }
            for e in index["endpoints"]
        ],
        "schemas": [
            {
                "name": s["name"],
                "type": s["type"],
                "itemsRef": s.get("itemsRef"),
                "description": s.get("description", ""),
            }
            for s in index["schemas"]
        ],
    }


def main() -> int:
    index = build()
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    quick = build_quick(index)
    QUICK_PATH.write_text(
        json.dumps(quick, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"  ok   api_index.json ({len(index['endpoints'])} endpoints, "
          f"{len(index['schemas'])} schemas, {len(index['tags'])} tags)")
    print(f"  ok   api_quick.json ({len(quick['endpoints'])} endpoints)")
    print(f"  spec version {index['specVersion']}")
    print(f"  consistency: sourceSha256 matches openapi.json = "
          f"{index['sourceSha256'] == sha256_of(OPENAPI_PATH)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
