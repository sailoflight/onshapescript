"""Offline-safe FeatureScript diagnostic enrichment and persistence.

The browser writes diagnostics for two consumers:

* a human reading the MCP result, who needs the message, its location, and the
  offending source line in one place;
* the local analyzer, which needs a stable grouping key instead of free prose,
  plus a retained, labeled corpus of (source, diagnostics, server conclusion).

`normalize_diagnostic` always labels the basis of the code it returns:

``errorstringenum``
    The text contains a token the vendored ``ErrorStringEnum`` defines, so the
    code is server-defined.
``errorstringenumDescription``
    The whole message equals an ``ErrorStringEnum`` description that exactly one
    code owns, so the code is server-defined.
``compilerMessage``
    A FeatureScript compiler message family observed in
    ``dev/button-map/scan-fs-notices.json``. This is our own label, not a server
    code, and is reported as unstable.
``unclassified``
    Nothing matched. The message is kept verbatim and counted as unclassified
    rather than forced into a family.

The enum table is read from the vendored standard library because the generated
FsDoc index drops ``ErrorStringEnum`` (the upstream module marks it
``@internal``); the raw module is the only local source for those codes. When it
is absent the loader reports ``available: false`` and normalization degrades to
the compiler families instead of failing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs" / "fs_diagnostics"

#: Environment override for the vendored ``ErrorStringEnum`` module. Useful when
#: the MCP host lays the repository out differently from this checkout.
FS_ERROR_ENUM_ENV = "ONSHAPE_FS_ERROR_ENUM"
FS_ERROR_ENUM_RELATIVE = Path(
    "onshape_docs/reference/raw/std-library/errorstringenum.gen.fs"
)

DIAGNOSTIC_SCHEMA_VERSION = 1

# Bounds keep a hostile or unexpectedly large notice pane from producing an
# unbounded MCP payload. Every truncation is reported, never silent.
MAX_SOURCE_LINE_LENGTH = 400
MAX_GROUP_MESSAGES = 5
MAX_GROUP_LOCATIONS = 10
MAX_GROUPS = 50
MAX_INLINE_GROUPS = 20
MAX_INLINE_MESSAGES = 3
MAX_RETAINED_READS = 200

_ENUM_DECLARATION = re.compile(r"^\s*(?:export\s+)?enum\s+ErrorStringEnum\b", re.M)
#: The last enum value has no trailing comma, so the comma is optional.
_ENUM_VALUE = re.compile(r"^\s+(?P<name>[A-Z][A-Z0-9_]*)\s*,?\s*$", re.M)
_ENUM_COMMENT_VALUE = re.compile(
    r"/\*(?P<description>[^*]*)\*/\s*\n\s*(?P<name>[A-Z][A-Z0-9_]*)\s*,?"
)
_CODE_TOKEN = re.compile(r"\b[A-Z][A-Z0-9_]{3,}\b")
_LOCATION_PREFIX = re.compile(
    r"^\s*[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[[^\]]*\])*\s*:\s*"
)

# Compiler message families. Each pattern is anchored on a notice text recorded
# in dev/button-map/scan-fs-notices.json; nothing here is guessed from memory.
_COMPILER_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("FS_PRECONDITION_ANALYSIS_FAILED", re.compile(r"precondition analysis failed", re.I)),
    ("FS_UNRESOLVED_NAME", re.compile(r"\bnot found\b", re.I)),
    ("FS_EXPECTED_TYPE", re.compile(r"\bexpected\b", re.I)),
)

_STABLE_BASES = frozenset({"errorstringenum", "errorstringenumDescription"})


class ErrorStringEnumIndex(NamedTuple):
    """A bounded, immutable view of the vendored ``ErrorStringEnum`` module."""

    path: str
    available: bool
    reason: str
    codes: frozenset[str]
    #: normalized description -> code, only for descriptions exactly one code owns
    descriptions: dict[str, str]
    ambiguous_descriptions: frozenset[str]
    described_count: int
    commentless_count: int


_EMPTY_INDEX = ErrorStringEnumIndex(
    path="",
    available=False,
    reason="vendored ErrorStringEnum module not found",
    codes=frozenset(),
    descriptions={},
    ambiguous_descriptions=frozenset(),
    described_count=0,
    commentless_count=0,
)


def _normalize_message(text: str) -> str:
    """Lowercase and strip punctuation so prose variants compare equal."""
    return re.sub(r"[^a-z0-9 ]", "", " ".join(text.split()).lower())


def _enum_body(source: str) -> str:
    declaration = _ENUM_DECLARATION.search(source)
    if declaration is None:
        return ""
    end = source.find("\n}", declaration.end())
    return source[declaration.end() : end if end != -1 else len(source)]


@lru_cache(maxsize=8)
def _parse_error_string_enum(path: str) -> ErrorStringEnumIndex:
    try:
        source = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return _EMPTY_INDEX._replace(
            path=path, reason=f"cannot read {path}: {type(exc).__name__}: {exc}"
        )
    body = _enum_body(source)
    if not body:
        return _EMPTY_INDEX._replace(
            path=path, reason=f"no ErrorStringEnum declaration in {path}"
        )
    codes = frozenset(match.group("name") for match in _ENUM_VALUE.finditer(body))
    described: dict[str, set[str]] = {}
    documented: set[str] = set()
    for match in _ENUM_COMMENT_VALUE.finditer(body):
        description = _normalize_message(match.group("description"))
        name = match.group("name")
        documented.add(name)
        if not description:
            continue
        described.setdefault(description, set()).add(name)
        codes = codes | {name}
    unique = {key: next(iter(value)) for key, value in described.items() if len(value) == 1}
    ambiguous = frozenset(key for key, value in described.items() if len(value) > 1)
    return ErrorStringEnumIndex(
        path=path,
        available=True,
        reason="",
        codes=codes,
        descriptions=unique,
        ambiguous_descriptions=ambiguous,
        described_count=len(described),
        commentless_count=len(codes - documented),
    )


def error_string_enum_path() -> Path | None:
    """Locate the vendored ``ErrorStringEnum`` module without guessing."""
    candidates: list[Path] = []
    override = os.environ.get(FS_ERROR_ENUM_ENV)
    if override:
        candidates.append(Path(override))
    candidates.append(Path(__file__).resolve().parents[1] / FS_ERROR_ENUM_RELATIVE)
    candidates.append(Path.cwd() / FS_ERROR_ENUM_RELATIVE)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def error_string_enum_index(path: str | Path | None = None) -> ErrorStringEnumIndex:
    """Return the cached enum index, honoring an explicit path for tests."""
    if path is None:
        located = error_string_enum_path()
        if located is None:
            return _EMPTY_INDEX
        return _parse_error_string_enum(str(located))
    return _parse_error_string_enum(str(Path(path)))


def code_table_status(index: ErrorStringEnumIndex | None = None) -> dict[str, Any]:
    """Describe the code table so a consumer can weight the normalization."""
    resolved = index if index is not None else error_string_enum_index()
    return {
        "available": resolved.available,
        "path": resolved.path,
        "codeCount": len(resolved.codes),
        "describedCount": resolved.described_count,
        "ambiguousDescriptionCount": len(resolved.ambiguous_descriptions),
        "commentlessCount": resolved.commentless_count,
        **({"reason": resolved.reason} if resolved.reason else {}),
    }


def normalize_diagnostic(
    text: str, index: ErrorStringEnumIndex | None = None
) -> dict[str, Any]:
    """Split one free-prose diagnostic into a stable, self-labeled code."""
    message = text if isinstance(text, str) else str(text)
    table = index if index is not None else error_string_enum_index()

    stripped = _LOCATION_PREFIX.sub("", message)
    for token in _CODE_TOKEN.findall(message):
        if token in table.codes:
            return {
                "code": token,
                "codeBasis": "errorstringenum",
                "codeStable": True,
                "codeEvidence": token,
            }

    normalized = _normalize_message(message)
    if normalized and normalized in table.descriptions:
        code = table.descriptions[normalized]
        return {
            "code": code,
            "codeBasis": "errorstringenumDescription",
            "codeStable": True,
            "codeEvidence": code,
        }

    for code, pattern in _COMPILER_FAMILIES:
        match = pattern.search(stripped)
        if match:
            return {
                "code": code,
                "codeBasis": "compilerMessage",
                "codeStable": False,
                "codeEvidence": match.group(0),
            }

    return {
        "code": "UNCLASSIFIED",
        "codeBasis": "unclassified",
        "codeStable": False,
        "codeEvidence": "",
    }


def _caret_prefix(line: str, column: int) -> str:
    """Spaces up to ``column``, preserving tabs so the caret keeps its column."""
    return "".join("\t" if char == "\t" else " " for char in line[:column])


def diagnostic_source_context(
    source: str | None, row: Any, column: Any = None
) -> dict[str, Any]:
    """Attach the offending source line so a diagnostic is self-contained."""
    if not isinstance(source, str) or not source:
        return {"available": False, "reason": "source text unavailable"}
    lines = source.split("\n")
    if not isinstance(row, int) or isinstance(row, bool) or not 0 <= row < len(lines):
        return {
            "available": False,
            "reason": f"row {row!r} outside 0..{len(lines) - 1}",
            "lineCount": len(lines),
        }
    line = lines[row]
    truncated = len(line) > MAX_SOURCE_LINE_LENGTH
    shown = line[:MAX_SOURCE_LINE_LENGTH]
    context: dict[str, Any] = {
        "available": True,
        "lineNumber": row + 1,
        "sourceLine": shown,
        "truncated": truncated,
        "lineCount": len(lines),
    }
    if isinstance(column, int) and not isinstance(column, bool) and column >= 0:
        context["caret"] = _caret_prefix(shown, min(column, len(shown)))
    return context


def _diagnostic_messages(item: dict[str, Any]) -> list[str]:
    raw = item.get("messages")
    messages = [str(entry) for entry in raw if str(entry).strip()] if isinstance(raw, list) else []
    if not messages:
        text = item.get("text")
        if text is not None and str(text).strip():
            messages = [str(text)]
    return messages


def _diagnostic_severity(item: dict[str, Any]) -> str:
    return str(item.get("type", item.get("severity", "warning"))).strip().lower() or "warning"


def summarize_diagnostics(
    compile_status: Any,
    source: str | None = None,
    index: ErrorStringEnumIndex | None = None,
) -> dict[str, Any]:
    """Normalize, enrich, and group one compile-status observation.

    Grouping deduplicates the same defect reported by both the Ace annotation API
    and the notice pane: the group records every contributing source and every
    distinct location, so a frequency count is a defect count, not a channel
    count.
    """
    status = compile_status if isinstance(compile_status, dict) else {}
    table = index if index is not None else error_string_enum_index()
    raw_items = [item for item in status.get("errors", []) if isinstance(item, dict)]
    entries: list[dict[str, Any]] = []
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []

    for item in raw_items:
        messages = _diagnostic_messages(item)
        severity = _diagnostic_severity(item)
        normalized = normalize_diagnostic(messages[0] if messages else "", table)
        row = item.get("row")
        column = item.get("col")
        entry = {
            "source": str(item.get("source", "unknown")),
            "severity": severity,
            "code": normalized["code"],
            "codeBasis": normalized["codeBasis"],
            "codeStable": normalized["codeStable"],
            "text": messages[0] if messages else "",
            "messages": messages,
            "line": item.get("line"),
            "column": item.get("column"),
            "row": row,
            "col": column,
            "tabName": str(item.get("tabName", "")),
            "sourceContext": diagnostic_source_context(source, row, column),
        }
        entries.append(entry)

        key = (normalized["code"], severity, " ".join((messages[0] if messages else "").split()))
        group = groups.get(key)
        if group is None:
            group = {
                "code": normalized["code"],
                "codeBasis": normalized["codeBasis"],
                "codeStable": normalized["codeStable"],
                "severity": severity,
                "count": 0,
                "sources": [],
                "messages": [],
                "locations": [],
                "messagesTruncated": False,
                "locationsTruncated": False,
            }
            groups[key] = group
            order.append(key)
        group["count"] += 1
        if entry["source"] not in group["sources"]:
            group["sources"].append(entry["source"])
        for message in messages:
            if message in group["messages"]:
                continue
            if len(group["messages"]) >= MAX_GROUP_MESSAGES:
                group["messagesTruncated"] = True
                break
            group["messages"].append(message)
        location = {
            "line": item.get("line"),
            "column": item.get("column"),
            "row": row,
            "col": column,
            "tabName": entry["tabName"],
        }
        if location not in group["locations"]:
            if len(group["locations"]) >= MAX_GROUP_LOCATIONS:
                group["locationsTruncated"] = True
            else:
                group["locations"].append(location)

    ordered_groups = [groups[key] for key in order]
    severity_counts = {"error": 0, "warning": 0, "info": 0}
    for entry in entries:
        severity_counts[entry["severity"]] = severity_counts.get(entry["severity"], 0) + 1
    return {
        "schemaVersion": DIAGNOSTIC_SCHEMA_VERSION,
        "entryCount": len(entries),
        "groupCount": len(ordered_groups),
        "groupsTruncated": len(ordered_groups) > MAX_GROUPS,
        "unclassifiedCount": sum(
            1 for entry in entries if entry["codeBasis"] == "unclassified"
        ),
        "unstableCodeCount": sum(1 for entry in entries if not entry["codeStable"]),
        "severityCounts": severity_counts,
        "codeBasisCounts": _count_basis(entries),
        "entries": entries,
        "groups": ordered_groups[:MAX_GROUPS],
    }


def _count_basis(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        basis = str(entry.get("codeBasis", "unclassified"))
        counts[basis] = counts.get(basis, 0) + 1
    return counts


def inline_diagnostic_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Bound one summary for an MCP tool result that a human also reads."""
    groups = []
    for group in summary.get("groups", [])[:MAX_INLINE_GROUPS]:
        groups.append(
            {
                **group,
                "messages": group.get("messages", [])[:MAX_INLINE_MESSAGES],
                "messagesTruncated": bool(group.get("messagesTruncated"))
                or len(group.get("messages", [])) > MAX_INLINE_MESSAGES,
                "locations": group.get("locations", [])[:MAX_GROUP_LOCATIONS],
            }
        )
    return {
        "schemaVersion": summary.get("schemaVersion", DIAGNOSTIC_SCHEMA_VERSION),
        "entryCount": summary.get("entryCount", 0),
        "groupCount": summary.get("groupCount", 0),
        "unclassifiedCount": summary.get("unclassifiedCount", 0),
        "unstableCodeCount": summary.get("unstableCodeCount", 0),
        "severityCounts": summary.get("severityCounts", {}),
        "codeBasisCounts": summary.get("codeBasisCounts", {}),
        "groupsTruncated": bool(summary.get("groupsTruncated"))
        or len(summary.get("groups", [])) > MAX_INLINE_GROUPS,
        "groups": groups,
    }


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _capture_directory(output_root: Path, captured_at: str, source_sha256: str) -> tuple[str, Path]:
    stamp = re.sub(r"[^0-9A-Za-z]+", "", captured_at)
    base_id = f"{stamp}-{source_sha256[:12]}"
    root = output_root.resolve()
    for suffix in range(100):
        capture_id = base_id if suffix == 0 else f"{base_id}-{suffix}"
        destination = root / capture_id
        try:
            destination.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return capture_id, destination
    raise FileExistsError("could not allocate a unique FeatureScript diagnostic capture directory")


def save_featurescript_diagnostic(
    *,
    source: str,
    compile_status: dict[str, Any],
    page_url: str,
    phase: str,
    output_root: Path = OUTPUT_ROOT,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """Persist one browser-observed FeatureScript source and compile result.

    ``compile-result.json`` stays the verbatim browser observation;
    ``diagnostics.json`` holds the normalized, source-annotated view, and the
    returned ``corpusEntry`` is the bounded form the local analyzer consumes
    without filesystem access to the MCP host.
    """
    if not isinstance(source, str):
        raise TypeError("source must be a string")
    if not isinstance(compile_status, dict):
        raise TypeError("compile_status must be an object")
    if not isinstance(page_url, str):
        raise TypeError("page_url must be a string")
    if not isinstance(phase, str) or not phase.strip():
        raise ValueError("phase must be a non-empty string")

    observed_at = captured_at or datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    source_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    capture_id, destination = _capture_directory(output_root, observed_at, source_sha256)
    source_path = destination / "featurescript.fs"
    result_path = destination / "compile-result.json"
    diagnostics_path = destination / "diagnostics.json"
    manifest_path = destination / "manifest.json"

    summary = summarize_diagnostics(compile_status, source)
    code_table = code_table_status()

    manifest = {
        "schemaVersion": 1,
        "artifactType": "featurescript-compile-diagnostic",
        "captureId": capture_id,
        "capturedAt": observed_at,
        "phase": phase.strip(),
        "pageUrl": page_url,
        "sourceFile": source_path.name,
        "compileResultFile": result_path.name,
        "diagnosticsFile": diagnostics_path.name,
        "sourceSha256": source_sha256,
        "sourceLength": len(source),
        "lineCount": source.count("\n") + 1,
        "diagnosticCount": summary["entryCount"],
        "diagnosticGroupCount": summary["groupCount"],
        "unclassifiedCount": summary["unclassifiedCount"],
        "unstableCodeCount": summary["unstableCodeCount"],
        "codeTableAvailable": code_table["available"],
    }
    diagnostics_document = {
        "schemaVersion": DIAGNOSTIC_SCHEMA_VERSION,
        "artifactType": "featurescript-diagnostic-summary",
        "captureId": capture_id,
        "capturedAt": observed_at,
        "phase": phase.strip(),
        "pageUrl": page_url,
        "sourceSha256": source_sha256,
        "serverConclusion": _server_conclusion(compile_status),
        "codeTable": code_table,
        "summary": summary,
    }
    _atomic_write_text(source_path, source)
    _atomic_write_text(
        result_path,
        json.dumps(compile_status, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write_text(
        diagnostics_path,
        json.dumps(diagnostics_document, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write_text(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return {
        "captured": True,
        "captureId": capture_id,
        "captureDirectory": str(destination),
        "sourcePath": str(source_path),
        "compileResultPath": str(result_path),
        "diagnosticsPath": str(diagnostics_path),
        "manifestPath": str(manifest_path),
        "sourceSha256": source_sha256,
        "sourceLength": len(source),
        "lineCount": source.count("\n") + 1,
        "diagnosticCount": summary["entryCount"],
        "diagnosticGroupCount": summary["groupCount"],
        "unclassifiedCount": summary["unclassifiedCount"],
        "unstableCodeCount": summary["unstableCodeCount"],
        "codeTable": code_table,
        "diagnosticSummary": inline_diagnostic_summary(summary),
        "corpusEntry": {
            "schemaVersion": DIAGNOSTIC_SCHEMA_VERSION,
            "kind": "featurescript-compile-corpus-entry",
            "captureId": capture_id,
            "capturedAt": observed_at,
            "phase": phase.strip(),
            "pageUrl": page_url,
            "sourceSha256": source_sha256,
            "sourceLength": len(source),
            "lineCount": source.count("\n") + 1,
            "serverConclusion": _server_conclusion(compile_status),
            "diagnostics": inline_diagnostic_summary(summary),
        },
    }


def _server_conclusion(compile_status: dict[str, Any]) -> dict[str, Any]:
    """The authoritative part of a capture: what the server said, unedited."""
    return {
        "compiled": bool(compile_status.get("compiled")),
        "found": bool(compile_status.get("found")),
        "noticeReadComplete": bool(compile_status.get("noticeReadComplete")),
        "annotationCount": int(compile_status.get("annotationCount", 0) or 0),
        "noticeCount": int(compile_status.get("noticeCount", 0) or 0),
        "errorCount": int(compile_status.get("errorCount", 0) or 0),
        "warningCount": int(compile_status.get("warningCount", 0) or 0),
    }


def load_retained_diagnostics(
    output_root: Path = OUTPUT_ROOT, limit: int = 20
) -> dict[str, Any]:
    """Read retained captures newest-first for the local analyzer.

    Reads are bounded and report truncation, so a growing capture directory can
    never surprise a caller with an unbounded payload.
    """
    root = Path(output_root)
    if limit < 1:
        raise ValueError("limit must be a positive integer")
    if not root.is_dir():
        return {"found": False, "count": 0, "truncated": False, "entries": [],
                "reason": f"no diagnostic captures under {root}"}
    directories = sorted(
        (item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name, reverse=True
    )
    scanned = directories[:MAX_RETAINED_READS]
    entries: list[dict[str, Any]] = []
    legacy = 0
    skipped = 0
    for directory in scanned:
        document = _read_json(directory / "diagnostics.json")
        if isinstance(document, dict):
            entries.append(
                {
                    "captureId": document.get("captureId", directory.name),
                    "capturedAt": document.get("capturedAt", ""),
                    "phase": document.get("phase", ""),
                    "pageUrl": document.get("pageUrl", ""),
                    "sourceSha256": document.get("sourceSha256", ""),
                    "serverConclusion": document.get("serverConclusion", {}),
                    "diagnostics": document.get("summary", {}),
                    "normalized": True,
                    "captureDirectory": str(directory),
                }
            )
        else:
            # A capture written before the normalized summary existed still names
            # its source and server result; keep it, and say it is not normalized.
            manifest = _read_json(directory / "manifest.json")
            if not isinstance(manifest, dict):
                skipped += 1
                continue
            legacy += 1
            entries.append(
                {
                    "captureId": manifest.get("captureId", directory.name),
                    "capturedAt": manifest.get("capturedAt", ""),
                    "phase": manifest.get("phase", ""),
                    "pageUrl": manifest.get("pageUrl", ""),
                    "sourceSha256": manifest.get("sourceSha256", ""),
                    "serverConclusion": {},
                    "diagnostics": {},
                    "normalized": False,
                    "captureDirectory": str(directory),
                }
            )
        if len(entries) >= limit:
            break
    return {
        "found": bool(entries),
        "count": len(entries),
        "scannedCount": len(scanned),
        "legacyCount": legacy,
        "skippedCount": skipped,
        "truncated": len(directories) > len(scanned) or len(entries) < len(directories),
        "outputRoot": str(root),
        "entries": entries,
    }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
