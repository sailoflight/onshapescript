"""Offline FeatureScript reference queries over the vendored official material.

Everything here is local and deterministic: it reads `reference/fsdoc/index.json`
(built by scripts/build_fsdoc_index.py), the raw FsDoc guide pages under
`reference/fsdoc/`, and the standard library source under `reference/std-library/`.
No network request is ever made, so these queries are safe to call freely from
the MCP server.

Naming mirrors the reference site:
  modules     - the standard library files, grouped into categories
  functions   - FeatureScript functions (name, signature, parameters, description)
  types       - type/enum definitions (BoundingType, Query, ...)
  constants   - const values (ANY_ID, Z_DIRECTION, ...)
  predicates  - typecheck predicates (canBeContext, isLength, ...)
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "reference" / "fsdoc" / "index.json"
GUIDE_PATH = ROOT / "reference" / "fsdoc" / "guide.json"
QUICK_REFERENCE_PATH = ROOT / "reference" / "quick-reference.md"
FSDOC_DIR = ROOT / "reference" / "fsdoc"
STD_LIB_DIR = ROOT / "reference" / "std-library"

KINDS = ("function", "type", "const", "predicate")
INDEX_KEYS = {
    "function": "functions",
    "type": "types",
    "const": "constants",
    "predicate": "predicates",
}
# Guide/tutorial pages available through fs_guide_section (see GUIDE_PATH).
PAGES = [
    "intro",
    "feature-types",
    "uispec",
    "output",
    "variables",
    "modeling",
    "tables",
    "computed-part-properties",
    "imports",
    "debugging-in-feature-studios",
    "tokens",
    "type-tags",
    "top-level",
    "syntax",
    "annotations",
    "exceptions",
    "relational",
    "tutorial-slot",
]

_index: dict[str, Any] | None = None
_guide: dict[str, Any] | None = None


def _load_index() -> dict[str, Any]:
    global _index
    if _index is None:
        _index = _load_json(INDEX_PATH)
    return _index


def _load_guide() -> dict[str, Any]:
    global _guide
    if _guide is None:
        _guide = _load_json(GUIDE_PATH)
    return _guide


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def reload() -> None:
    """Drop the cached indexes (useful after they are rebuilt)."""
    global _index, _guide
    _index = None
    _guide = None


# --------------------------------------------------------------------------
# modules
# --------------------------------------------------------------------------

def list_modules(category: str | None = None) -> list[dict[str, Any]]:
    modules = _load_index()["modules"]
    if category:
        modules = [m for m in modules if m["category"].lower() == category.lower()]
    return modules


def list_categories() -> list[dict[str, Any]]:
    """Return the sidebar categories with module counts."""
    counts: dict[str, int] = {}
    for module in _load_index()["modules"]:
        counts[module["category"]] = counts.get(module["category"], 0) + 1
    return [{"category": name, "moduleCount": count} for name, count in sorted(counts.items())]


# --------------------------------------------------------------------------
# lookups
# --------------------------------------------------------------------------

def _matches_module(item: dict[str, Any], module: str | None) -> bool:
    if not module:
        return True
    module_name = item.get("module", "")
    if module_name.lower() == module.lower():
        return True
    return module_name[:-3].lower() == module.lower() if module_name.endswith(".fs") else False


def _all_entries() -> list[dict[str, Any]]:
    index = _load_index()
    out: list[dict[str, Any]] = []
    for kind in KINDS:
        for entry in index.get(INDEX_KEYS[kind], []):
            # Preserve the parser's finer kind (e.g. enum vs type) as `subkind`.
            item = {**entry, "kind": kind, "subkind": entry.get("kind")}
            out.append(item)
    return out


def list_functions(
    module: str | None = None,
    category: str | None = None,
    kind: str | None = None,
    prefix: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    selected = [e for e in _all_entries() if e["kind"] == (kind or "function")]
    result = []
    for entry in selected:
        if not _matches_module(entry, module):
            continue
        if category and entry.get("category", "").lower() != category.lower():
            continue
        if prefix and not entry["name"].lower().startswith(prefix.lower()):
            continue
        result.append({
            "kind": entry["kind"],
            "name": entry["name"],
            "module": entry.get("module", ""),
            "category": entry.get("category", ""),
            "signature": entry.get("signature", ""),
            "summary": _summary(entry.get("description", "")),
        })
    result.sort(key=lambda e: (e["module"], e["name"]))
    return result[:limit]


def get_function(
    name: str,
    module: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """Return the full detail of a function (or const/predicate when kind given)."""
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    candidates = [e for e in _all_entries() if e["kind"] == (kind or "function")]
    matches = [
        e for e in candidates
        if e["name"] == name and _matches_module(e, module)
    ]
    if not matches:
        raise ValueError(
            f"No {kind or 'function'} named '{name}'"
            + (f" in module '{module}'" if module else "")
            + ". Check the name or omit module to see all matches."
        )
    if len(matches) > 1:
        raise ValueError(
            f"'{name}' exists in {len(matches)} modules: "
            + ", ".join(m["module"] for m in matches)
            + ". Pass module to disambiguate."
        )
    entry = matches[0]
    return {
        "kind": entry["kind"],
        "name": entry["name"],
        "module": entry.get("module", ""),
        "category": entry.get("category", ""),
        "signature": entry.get("signature", ""),
        "returnType": entry.get("returnType"),
        "parameters": entry.get("parameters", []),
        "description": entry.get("description", ""),
        "anchor": entry.get("anchor", ""),
    }


def get_type(name: str, module: str | None = None) -> dict[str, Any]:
    candidates = [e for e in _all_entries() if e["kind"] in ("type", "const")]
    matches = [e for e in candidates if e["name"] == name and _matches_module(e, module)]
    if not matches:
        raise ValueError(f"No type named '{name}'")
    if len(matches) > 1:
        raise ValueError(
            f"'{name}' exists in {len(matches)} modules: "
            + ", ".join(m["module"] for m in matches)
            + ". Pass module to disambiguate."
        )
    entry = matches[0]
    return {
        "kind": entry.get("subkind") or entry["kind"],
        "name": entry["name"],
        "module": entry.get("module", ""),
        "category": entry.get("category", ""),
        "description": entry.get("description", ""),
        "values": entry.get("values", []),
        "anchor": entry.get("anchor", ""),
    }


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

def _summary(text: str, length: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def _snippet(text: str, tokens: Iterable[str], width: int = 90) -> str:
    """Return the region of text that best hits the query tokens."""
    text = " ".join(text.split())
    if not text:
        return ""
    lowered = text.lower()
    best = (0, 0)
    for token in tokens:
        pos = lowered.find(token)
        if pos >= 0:
            start = max(0, pos - width // 3)
            end = min(len(text), pos + width)
            if end - start > best[1] - best[0]:
                best = (start, end)
    if best[1] <= best[0]:
        return _summary(text, width)
    return "…" + text[best[0] : best[1]] + "…"


def search(
    query: str,
    module: str | None = None,
    category: str | None = None,
    kind: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if kind is not None and kind not in KINDS and kind != "guide":
        raise ValueError(f"kind must be one of {', '.join(KINDS)} or 'guide'")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]
    if not tokens:
        raise ValueError("query must contain a searchable word")

    def score(entry: dict[str, Any]) -> float:
        name = entry["name"].lower()
        signature = entry.get("signature", "").lower()
        description = entry.get("description", "").lower()
        type_names = " ".join(
            p.get("type", "") for p in entry.get("parameters", [])
        ).lower()
        total = 0.0
        for token in tokens:
            if token in name:
                total += 10 if name == token else (8 if name.startswith(token) else 6)
            if token in signature:
                total += 4
            if token in type_names:
                total += 3
            if token in description:
                total += 1
        return total

    corpus = list(_all_entries())
    if kind in (None, "guide"):
        corpus.extend(_all_guide_sections())

    results = []
    for entry in corpus:
        if kind and entry["kind"] != kind:
            continue
        if not _matches_module(entry, module):
            continue
        if category and entry.get("category", "").lower() != category.lower():
            continue
        total = score(entry)
        if total <= 0:
            continue
        results.append((total, entry))
    results.sort(key=lambda pair: (-pair[0], pair[1]["name"]))

    ranked: list[dict[str, Any]] = []
    for total, entry in results[:limit]:
        ranked.append({
            "kind": entry["kind"],
            "name": entry["name"],
            "module": entry.get("module", ""),
            "category": entry.get("category", ""),
            "signature": entry.get("signature", ""),
            "score": round(total, 1),
            "snippet": _snippet(
                (entry.get("signature", "") + " " + entry.get("description", "")),
                tokens,
            ),
        })
    return ranked


# --------------------------------------------------------------------------
# guide pages (structured JSON -> text)
# --------------------------------------------------------------------------

def _render_block(block: dict[str, Any]) -> list[str]:
    kind = block["type"]
    if kind == "para":
        return [block["text"]]
    if kind == "code":
        return [f"```{block.get('language', 'fs')}\n{block['text']}\n```"]
    if kind == "list":
        return ["- " + item for item in block["items"]]
    if kind == "table":
        return ["| " + " | ".join(row) + " |" for row in block["rows"]]
    return []


def _render_sections(sections: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for section in sections:
        lines = ["#" * section["level"] + " " + section["title"]]
        for block in section["blocks"]:
            lines.extend(_render_block(block))
        parts.append("\n".join(lines))
    return "\n\n".join(parts).strip()


def _find_page(page: str) -> dict[str, Any]:
    if page not in PAGES:
        raise ValueError(f"page must be one of: {', '.join(PAGES)}")
    for entry in _load_guide().get("pages", []):
        if entry["page"] == page:
            return entry
    raise ValueError(
        f"guide page '{page}' is not indexed; run `python3 scripts/build_fsdoc_index.py`"
    )


def guide_section(page: str, section: str | None = None) -> dict[str, Any]:
    """Return a guide page as text, optionally narrowed to one heading section.

    Reads the structured reference/fsdoc/guide.json, so page and section lookup
    is index-driven and on demand; the large HTML is never parsed at query time.
    """
    entry = _find_page(page)
    sections = entry["sections"]
    if section:
        target = section.lower()
        candidates = [s for s in sections if target in s["title"].lower()]
        if not candidates:
            raise ValueError(
                f"No section matching '{section}' in '{page}'. Available: "
                + "; ".join(s["title"] for s in sections[:20])
            )
        picked = candidates[0]
        # Include nested subsections up to the next heading of the same level.
        selected = [picked]
        for later in sections[sections.index(picked) + 1:]:
            if later["level"] <= picked["level"]:
                break
            selected.append(later)
        return {"page": page, "section": picked["title"], "text": _render_sections(selected)}
    return {
        "page": page,
        "section": None,
        "headings": [s["title"] for s in sections],
        "text": _render_sections(sections),
    }


def _all_guide_sections() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in _load_guide().get("pages", []):
        for section in entry["sections"]:
            out.append({
                "kind": "guide",
                "name": section["title"],
                "module": entry["page"],
                "category": "guide",
                "signature": "",
                "description": _render_sections([section]),
            })
    return out


# --------------------------------------------------------------------------
# standard library source
# --------------------------------------------------------------------------

def _source_lines(module: str) -> list[str]:
    if module.endswith(".fs"):
        module = module[:-3]
    path = STD_LIB_DIR / f"{module}.fs"
    if not path.is_file():
        raise ValueError(
            f"standard library module '{module}' not vendored under reference/std-library"
        )
    return path.read_text(encoding="utf-8").splitlines()


def library_source(module: str, function: str | None = None) -> dict[str, Any]:
    """Return the standard library source for a module.

    With `function`, returns the window around the first definition of that name
    so the tool does not dump a whole module. The exact name is also matched as
    an identifier to locate usages.
    """
    lines = _source_lines(module)
    name = module[:-3] if module.endswith(".fs") else module
    source = "\n".join(lines)
    if not function:
        return {"module": name, "byteCount": len(source), "lineCount": len(lines), "source": source}

    function = function.rstrip("()")
    usage_lines = [
        i + 1 for i, line in enumerate(lines)
        if re.search(rf"\b{re.escape(function)}\b", line)
    ]
    # Prefer a definition site: `function <name>(` or an operator export.
    definition = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"function {function}(") or stripped == f"function {function}(":
            definition = i
            break
    if definition is None:
        # fall back to the first usage line
        definition = usage_lines[0] - 1 if usage_lines else 0
    start = max(0, definition - 3)
    end = min(len(lines), definition + 3)
    for i in range(definition + 1, len(lines)):
        stripped = lines[i].strip()
        if re.match(r"^(function |export |annotation |const |predicate |type )", stripped):
            end = i
            break
    excerpt = "\n".join(lines[start:end])
    return {
        "module": name,
        "function": function,
        "lineRange": [start + 1, end],
        "definitionLine": definition + 1,
        "usageLines": usage_lines,
        "source": excerpt,
    }


# --------------------------------------------------------------------------
# version verification
# --------------------------------------------------------------------------

VERSION_SOURCE = STD_LIB_DIR / "featurescriptversionnumber.gen.fs"


def vendored_version() -> dict[str, Any]:
    """Parse the FeatureScript version baked into the vendored std library."""
    version: int | None = None
    label: str | None = None
    if VERSION_SOURCE.is_file():
        text = VERSION_SOURCE.read_text(encoding="utf-8")
        match = re.search(
            r"FeatureScriptVersionNumberCurrent[^\n]*V(\d+)_([A-Za-z0-9_]+)\s*;",
            text,
        )
        if match:
            version = int(match.group(1))
            label = f"V{version}_{match.group(2)}"
    return {"version": version, "label": label, "source": VERSION_SOURCE.name}


def _coerce_version(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _reference_health() -> dict[str, Any]:
    """Check the vendored corpus for internal consistency."""
    health: dict[str, Any] = {
        "indexConsistent": False,
        "guideConsistent": False,
        "functionsIndexed": 0,
        "guideSectionsIndexed": 0,
        "stdLibraryFiles": 0,
    }
    try:
        index = _load_index()
        actual = hashlib.sha256((FSDOC_DIR / "library.html").read_bytes()).hexdigest()
        health["indexConsistent"] = index.get("librarySha256") == actual
        health["functionsIndexed"] = len(index.get("functions", []))
    except (OSError, ValueError):
        pass
    try:
        guide = _load_guide()
        stale = []
        for entry in guide.get("pages", []):
            path = FSDOC_DIR / entry.get("path", "")
            if not path.is_file():
                stale.append(entry["page"])
            elif hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
                stale.append(entry["page"])
        health["guideConsistent"] = not stale
        health["guideSectionsIndexed"] = sum(
            len(p.get("sections", [])) for p in guide.get("pages", [])
        )
    except (OSError, ValueError):
        pass
    health["stdLibraryFiles"] = len(list(STD_LIB_DIR.glob("*.fs")))
    return health


def check_version(target: Any = None, live_version: Any = None) -> dict[str, Any]:
    """Compare the vendored reference version against a target and/or live version.

    target        - the FeatureScript version the caller intends to compile against
                    (e.g. from the import statement or a feature studio).
    live_version  - the version reported by the configured Onshape Feature Studio,
                    if the caller fetched it (the check itself stays offline).
    """
    vendored = vendored_version()
    target_version = _coerce_version(target)
    live = _coerce_version(live_version)

    status = "unknown"
    warnings: list[str] = []
    refresh_hint = (
        "Run `python3 scripts/fetch_reference.py` then "
        "`python3 scripts/build_fsdoc_index.py` to refresh."
    )
    v = vendored["version"]

    if v is not None:
        status = "current"
        if target_version is not None and target_version > v:
            status = "docs-behind"
            warnings.append(
                f"Target FeatureScript version {target_version} is newer than the vendored "
                f"reference ({v}); APIs added since version {v} are not documented here. "
                f"{refresh_hint}"
            )
        if live is not None and live > v:
            status = "docs-behind" if status != "docs-behind" else status
            warnings.append(
                f"Your Onshape Feature Studio reports version {live}, newer than the vendored "
                f"reference ({v}); APIs added since version {v} are not documented here. "
                f"{refresh_hint}"
            )
        if target_version is not None and target_version < v:
            warnings.append(
                f"Target version {target_version} is older than the vendored reference ({v}); "
                f"some documented APIs may not exist in that older version."
            )

    health = _reference_health()
    if not health["indexConsistent"]:
        warnings.append(
            "reference/fsdoc/index.json is out of date relative to library.html; rebuild the index."
        )
    if not health["guideConsistent"]:
        warnings.append(
            "reference/fsdoc/guide.json is out of date relative to the guide pages; rebuild the index."
        )

    return {
        "vendoredVersion": v,
        "vendoredVersionLabel": vendored["label"],
        "targetVersion": target_version,
        "featureStudioVersion": live,
        "status": status,
        "warnings": warnings,
        "referenceHealth": health,
    }


# --------------------------------------------------------------------------
# reference maintenance (the only network path) and quick digest
# --------------------------------------------------------------------------

MIRROR_VERSION_URL = (
    "https://raw.githubusercontent.com/javawizard/onshape-std-library-mirror/"
    "without-versions/featurescriptversionnumber.gen.fs"
)


def fetch_latest_mirror_version(timeout: int = 30) -> dict[str, Any]:
    """Probe the mirror for the newest FeatureScript version (network call).

    Downloads only the small version constant file, so the probe is cheap. This
    is the sole network-requiring function in this module.
    """
    with urllib.request.urlopen(MIRROR_VERSION_URL, timeout=timeout) as response:
        text = response.read().decode("utf-8", "replace")
    match = re.search(
        r"FeatureScriptVersionNumberCurrent[^\n]*V(\d+)_([A-Za-z0-9_]+)\s*;",
        text,
    )
    if not match:
        raise ValueError("could not parse FeatureScriptVersionNumberCurrent from the mirror")
    version = int(match.group(1))
    return {
        "version": version,
        "label": f"V{version}_{match.group(2)}",
        "source": "mirror (network probe)",
    }


def current_versions() -> dict[str, Any]:
    """Snapshot of the vendored corpus versions/sizes (offline)."""
    index = _load_index()
    guide = _load_guide()
    return {
        "vendoredVersion": vendored_version()["version"],
        "librarySha256": index.get("librarySha256"),
        "functionsCount": len(index.get("functions", [])),
        "guideSectionsCount": sum(
            len(p.get("sections", [])) for p in guide.get("pages", [])
        ),
    }


def _function_key(entry: dict[str, Any]) -> tuple[str, str]:
    return (entry.get("name", ""), entry.get("module", ""))


def reference_change_summary(
    old_functions: list[dict[str, Any]],
    new_functions: list[dict[str, Any]],
    preview: int = 20,
) -> dict[str, Any]:
    """Compare two generations of the function index, bounded for context."""
    old = {_function_key(e): e for e in old_functions}
    new = {_function_key(e): e for e in new_functions}

    def signature_of(entry: dict[str, Any]) -> tuple[Any, Any]:
        return (entry.get("signature"), entry.get("description"))

    added = sorted(set(new) - set(old), key=lambda k: k[0])
    removed = sorted(set(old) - set(new), key=lambda k: k[0])
    changed = sorted(
        (k for k in set(old) & set(new) if signature_of(old[k]) != signature_of(new[k])),
        key=lambda k: k[0],
    )

    def names(items: list[tuple[str, str]]) -> list[str]:
        return [name for name, _ in items]

    return {
        "addedCount": len(added),
        "removedCount": len(removed),
        "changedCount": len(changed),
        "added": names(added[:preview]),
        "removed": names(removed[:preview]),
        "changed": names(changed[:preview]),
        "truncated": max(len(added), len(removed), len(changed)) > preview,
    }


def update_reference(timeout: int = 600) -> dict[str, Any]:
    """Fetch the latest docs and rebuild the JSON indexes (mutates reference/).

    Returns a bounded change summary so the caller does not have to hold the
    delta in context; afterwards the query functions serve the fresh corpus.
    """
    import subprocess
    import sys

    old_functions = _load_index().get("functions", [])
    before = current_versions()
    fetch = subprocess.run(
        [sys.executable, "scripts/fetch_reference.py", "--quiet"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout,
    )
    build = subprocess.run(
        [sys.executable, "scripts/build_fsdoc_index.py"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout,
    )
    reload()
    new_functions = _load_index().get("functions", [])
    after = current_versions()
    changes = reference_change_summary(old_functions, new_functions)

    notes: list[str] = []
    if fetch.returncode != 0:
        notes.append("fetch_reference.py exited nonzero (some downloads failed): "
                     + fetch.stderr.strip()[:200])
    if build.returncode != 0:
        notes.append("build_fsdoc_index.py exited nonzero: " + build.stderr.strip()[:200])

    updated = (
        before.get("librarySha256") != after.get("librarySha256")
        or changes["addedCount"] > 0
        or changes["removedCount"] > 0
        or changes["changedCount"] > 0
    )
    return {
        "versionBefore": before.get("vendoredVersion"),
        "versionAfter": after.get("vendoredVersion"),
        "updated": updated,
        "changes": changes,
        "notes": notes,
    }


def quick_reference() -> dict[str, Any]:
    """Return the curated quick-reference digest (reference/quick-reference.md)."""
    if not QUICK_REFERENCE_PATH.is_file():
        raise ValueError(
            "reference/quick-reference.md is missing; it is authored alongside the vendored docs."
        )
    text = QUICK_REFERENCE_PATH.read_text(encoding="utf-8")
    return {"path": str(QUICK_REFERENCE_PATH), "bytes": len(text), "text": text}
