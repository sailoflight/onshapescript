"""Document variable tables (a Variable Studio's rows) — the REST leg.

Why this exists: issue #19 asks for reading and writing the document variable
table (`#name = value`). The BROWSER leg still cannot do it — the variable
table's DOM has never been recorded on a live page, and this repository does not
write selectors from memory (T7 in
``onshape_docs/verification/pending-live-verification-2026-10-01.json``). The
documented API has the complete contract, so the capability is delivered here
first, from the schema rather than from a guess.

Endpoints (vendored OpenAPI, tag ``Variables``)::

    GET  /api/variables/d/{did}/{wv}/{wvid}/e/{eid}/variables   getVariables
    POST /api/variables/d/{did}/w/{wid}/e/{eid}/variables       setVariables

Shapes come from ``onshape_docs/reference/raw/onshape-api/openapi.json``:

* ``BTVariableTableInfo`` — one table: ``variables`` (array) plus an optional
  ``variableStudioReference``;
* ``BTVariableInfo`` — one row: required ``name``/``type``/``expression``/
  ``value``, optional ``description``;
* ``BTVariableParams`` — one write row: required ``name``/``type``, plus
  ``expression``/``description`` or their ``configured*`` variants; ``name`` is
  constrained to ``^[a-zA-Z_][a-zA-Z0-9_]*$``;
* ``GBTVariableType`` — the type names (LENGTH, ANGLE, NUMBER, ANY, UNKNOWN);
* ``GBTElementType`` — ``VARIABLESTUDIO`` identifies the element to address.

**Unverified live.** No response in this module was ever captured from Onshape:
the account is a scarce shared resource and the Windows host was offline when
this landed. Every entry point is exercised offline against spec-derived shapes
(``dev/tests/test_rest_variables.py``) and the live acceptance is still pending
(T9 in the record named above). Do not read a passing offline test as proof that
the real endpoint behaves this way.
"""

from __future__ import annotations

import re
from typing import Any

#: ``GBTVariableType`` enum, in the spec's order. A write must name one of these.
VARIABLE_TYPES: tuple[str, ...] = ("LENGTH", "ANGLE", "NUMBER", "ANY", "UNKNOWN")

#: ``GBTElementType`` value that identifies a Variable Studio element.
VARIABLE_STUDIO_ELEMENT_TYPE = "VARIABLESTUDIO"

#: ``BTVariableParams.name`` pattern, verbatim from the spec.
NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

#: Row keys this module reads when normalizing a table (spec ``BTVariableInfo``).
ROW_KEYS = ("name", "type", "expression", "value", "description")

#: Keys a caller may send for one variable (spec ``BTVariableParams`` minus the
#: ``configured*`` object forms, which need a ``BTConfiguredValue`` the model
#: cannot construct from a plain argument).
WRITE_KEYS = ("name", "type", "expression", "description")


def variables_path(
    document_id: str,
    workspace_id: str,
    element_id: str,
    version_id: str | None = None,
) -> str:
    """Build the ``getVariables``/``setVariables`` path for one element.

    A write always addresses the workspace (the spec exposes ``setVariables``
    only under ``/w/{wid}/``); a read may address a version by passing
    ``version_id``, which switches the ``{wv}/{wvid}`` pair to ``v/<version>``.
    """
    if not document_id or not element_id:
        raise ValueError("document_id and element_id are required")
    if version_id:
        return (
            f"/api/variables/d/{document_id}/v/{version_id}/e/{element_id}/variables"
        )
    if not workspace_id:
        raise ValueError("workspace_id is required to address a workspace")
    return f"/api/variables/d/{document_id}/w/{workspace_id}/e/{element_id}/variables"


def validate_variables(items: Any) -> list[dict[str, Any]]:
    """Validate caller-supplied rows and return the exact ``BTVariableParams`` body.

    Refuses instead of repairing: an unknown key, a missing name, a name the
    spec's pattern rejects, a missing/unknown type, or a row carrying neither an
    expression nor (for a configured row) a description is a malformed request
    the caller must fix, not something to silently drop.
    """
    if not isinstance(items, list) or not items:
        raise ValueError("variables must be a non-empty array of {name, type, ...}")
    body: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"variables[{index}] must be an object")
        unknown = sorted(set(item) - set(WRITE_KEYS))
        if unknown:
            raise ValueError(
                f"variables[{index}] has unsupported key(s) {unknown}; "
                f"allowed: {list(WRITE_KEYS)}"
            )
        name = item.get("name")
        if not isinstance(name, str) or not NAME_PATTERN.match(name):
            raise ValueError(
                f"variables[{index}].name must match {NAME_PATTERN.pattern}; got {name!r}"
            )
        raw_type = item.get("type")
        if not isinstance(raw_type, str) or not raw_type.strip():
            raise ValueError(
                f"variables[{index}].type is required and must be one of "
                f"{list(VARIABLE_TYPES)}"
            )
        variable_type = raw_type.strip().upper()
        if variable_type not in VARIABLE_TYPES:
            raise ValueError(
                f"variables[{index}].type must be one of {list(VARIABLE_TYPES)}; "
                f"got {raw_type!r}"
            )
        row: dict[str, Any] = {"name": name, "type": variable_type}
        expression = item.get("expression")
        if expression is not None:
            if not isinstance(expression, str):
                raise ValueError(f"variables[{index}].expression must be a string")
            row["expression"] = expression
        description = item.get("description")
        if description is not None:
            if not isinstance(description, str):
                raise ValueError(f"variables[{index}].description must be a string")
            row["description"] = description
        if "expression" not in row and "description" not in row:
            raise ValueError(
                f"variables[{index}] needs an 'expression' (the value/definition) "
                "or a 'description'"
            )
        body.append(row)
    return body


def _normalize_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"raw": row}
    normalized = {key: row.get(key) for key in ROW_KEYS if key in row}
    # A read without includeValuesAndReferencedVariables may omit `value`; keep
    # the key present so callers compare shapes instead of guessing.
    normalized.setdefault("value", None)
    remainder = {k: v for k, v in row.items() if k not in ROW_KEYS}
    if remainder:
        normalized["extra"] = remainder
    return normalized


def summarize_tables(payload: Any) -> dict[str, Any]:
    """Normalize a ``getVariables`` response into tables and rows.

    The spec types the response as an array of ``BTVariableTableInfo``; a single
    object is accepted too, because a one-table element is the common case and
    the distinction is not worth a failed call. An empty document has no table
    yet — ``tables`` is then empty and ``tableCount`` 0, which is a successful
    read of "no variables", not an error.
    """
    if payload is None or payload == "":
        raw_tables: list[Any] = []
    elif isinstance(payload, dict):
        raw_tables = [payload]
    elif isinstance(payload, list):
        raw_tables = payload
    else:
        return {
            "tableCount": 0,
            "variableCount": 0,
            "tables": [],
            "unexpectedShape": repr(payload)[:200],
        }
    tables: list[dict[str, Any]] = []
    for table in raw_tables:
        rows = table.get("variables") if isinstance(table, dict) else None
        rows = rows if isinstance(rows, list) else []
        entry: dict[str, Any] = {"variables": [_normalize_row(row) for row in rows]}
        reference = table.get("variableStudioReference") if isinstance(table, dict) else None
        if reference is not None:
            entry["variableStudioReference"] = reference
        tables.append(entry)
    return {
        "tableCount": len(tables),
        "variableCount": sum(len(table["variables"]) for table in tables),
        "tables": tables,
    }


def variables_summary(payload: Any) -> dict[str, Any]:
    """Alias used by the operation layer; kept for a stable import surface."""
    return summarize_tables(payload)
