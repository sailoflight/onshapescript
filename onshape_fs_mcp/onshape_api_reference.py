#!/usr/bin/env python3
"""Query helpers for the vendored Onshape REST API OpenAPI index.

The MCP onshape_api_* tools read the flattened index built by
scripts/build_onshape_api_index.py (api_index.json / api_quick.json) and answer
REST questions offline. Nothing here contacts the network or Onshape.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ONSHAPE_API_DIR = ROOT / "reference" / "onshape-api"
OPENAPI_PATH = ONSHAPE_API_DIR / "openapi.json"
API_INDEX_PATH = ONSHAPE_API_DIR / "api_index.json"
API_QUICK_PATH = ONSHAPE_API_DIR / "api_quick.json"

_index: dict[str, Any] | None = None
_quick: dict[str, Any] | None = None


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _load_index() -> dict[str, Any]:
    global _index
    if _index is None:
        if not API_INDEX_PATH.is_file():
            raise FileNotFoundError(
                f"{API_INDEX_PATH} is missing; run scripts/fetch_onshape_api.py and "
                "scripts/build_onshape_api_index.py to vendor the reference."
            )
        _index = _load_json(API_INDEX_PATH)
    return _index


def _load_quick() -> dict[str, Any]:
    global _quick
    if _quick is None:
        if not API_QUICK_PATH.is_file():
            raise FileNotFoundError(
                f"{API_QUICK_PATH} is missing; run scripts/build_onshape_api_index.py."
            )
        _quick = _load_json(API_QUICK_PATH)
    return _quick


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reload() -> None:
    """Drop cached indexes so a re-fetch + rebuild is visible immediately."""
    global _index, _quick
    _index = None
    _quick = None


def spec_version() -> dict[str, str]:
    """Report the vendored REST API spec version and index health."""
    index = _load_index()
    consistent = (
        index.get("sourceSha256") == _sha256(OPENAPI_PATH)
        if OPENAPI_PATH.is_file()
        else False
    )
    return {
        "specVersion": index.get("specVersion", ""),
        "openapiVersion": index.get("openapiVersion", ""),
        "sourceUrl": index.get("sourceUrl", ""),
        "endpoints": len(index.get("endpoints", [])),
        "schemas": len(index.get("schemas", [])),
        "indexConsistent": consistent,
    }


def list_tags() -> dict[str, Any]:
    index = _load_index()
    return {
        "specVersion": index.get("specVersion", ""),
        "count": len(index.get("tags", [])),
        "tags": index.get("tags", []),
    }


def _matches_tag(endpoint: dict[str, Any], tag: str) -> bool:
    return any(t.lower() == tag.lower() for t in endpoint["tags"])


def search(
    query: str,
    tag: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]
    if not tokens:
        raise ValueError("query must contain a searchable word")

    def score(endpoint: dict[str, Any]) -> float:
        path = endpoint["path"].lower()
        operation_id = endpoint["operationId"].lower()
        summary = endpoint["summary"].lower()
        description = endpoint["description"].lower()
        total = 0.0
        for token in tokens:
            if token in operation_id:
                total += 6 if operation_id == token else 4
            if token in path:
                total += 4
            if token in summary:
                total += 3
            if token in description:
                total += 1
        return total

    results: list[tuple[float, dict[str, Any]]] = []
    for endpoint in _load_index()["endpoints"]:
        if tag and not _matches_tag(endpoint, tag):
            continue
        total = score(endpoint)
        if total <= 0:
            continue
        results.append((total, endpoint))
    results.sort(key=lambda pair: (-pair[0], pair[1]["path"], pair[1]["method"]))

    return [
        {
            "method": endpoint["method"].upper(),
            "path": endpoint["path"],
            "operationId": endpoint["operationId"],
            "summary": endpoint["summary"],
            "tags": endpoint["tags"],
            "deprecated": endpoint["deprecated"],
            "score": round(total, 1),
        }
        for total, endpoint in results[:limit]
    ]


def _normalize_path(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "", path)


def get_endpoint(path: str, method: str | None = None) -> dict[str, Any]:
    """Return one operation, or (without a method) the methods on one path."""
    index = _load_index()
    if method:
        method = method.lower()

    matches = [e for e in index["endpoints"] if e["path"] == path]
    if not matches:
        norm = _normalize_path(path)
        candidates = [e for e in index["endpoints"] if norm in _normalize_path(e["path"])]
        if not candidates:
            raise ValueError(
                f"no endpoint with path {path!r}; use onshape_api_search to find it"
            )
        paths = sorted({e["path"] for e in candidates})
        raise ValueError(
            f"path {path!r} was not exact; candidates:\n" + "\n".join(paths[:10])
        )

    if method:
        available = {e["method"].upper() for e in matches}
        matches = [e for e in matches if e["method"] == method]
        if not matches:
            raise ValueError(
                f"no {method.upper()} method on {path}; available: "
                + ", ".join(sorted(available))
            )
    if len(matches) == 1:
        e = matches[0]
        return {
            "method": e["method"].upper(),
            "path": e["path"],
            "operationId": e["operationId"],
            "summary": e["summary"],
            "description": e["description"],
            "tags": e["tags"],
            "deprecated": e["deprecated"],
            "parameters": e["parameters"],
            "responses": e["responses"],
            "specVersion": index.get("specVersion", ""),
        }
    # path exists with several methods and no method filter
    return {
        "path": path,
        "specVersion": index.get("specVersion", ""),
        "note": "pass method=<name> to get the full definition of one operation",
        "methods": [
            {
                "method": e["method"].upper(),
                "operationId": e["operationId"],
                "summary": e["summary"],
            }
            for e in sorted(matches, key=lambda e: e["method"])
        ],
    }


def get_schema(name: str) -> dict[str, Any]:
    index = _load_index()
    for schema in index["schemas"]:
        if schema["name"].lower() == name.lower():
            return {**schema, "specVersion": index.get("specVersion", "")}
    matches = [s["name"] for s in index["schemas"] if name.lower() in s["name"].lower()]
    if matches:
        raise ValueError(
            f"schema {name!r} was not exact; candidates: " + ", ".join(matches[:10])
        )
    raise ValueError(
        f"no schema named {name!r}; use onshape_api_search to find related endpoints"
    )
