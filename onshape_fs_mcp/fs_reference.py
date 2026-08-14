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

import html as html_module
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "reference" / "fsdoc" / "index.json"
FSDOC_DIR = ROOT / "reference" / "fsdoc"
STD_LIB_DIR = ROOT / "reference" / "std-library"

KINDS = ("function", "type", "const", "predicate")
INDEX_KEYS = {
    "function": "functions",
    "type": "types",
    "const": "constants",
    "predicate": "predicates",
}
PAGES = [
    "index",
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
    "library",
]

_index: dict[str, Any] | None = None


def _load_index() -> dict[str, Any]:
    global _index
    if _index is None:
        _index = json_load(INDEX_PATH)
    return _index


def json_load(path: Path) -> dict[str, Any]:
    import json

    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def reload() -> None:
    """Drop the cached index (useful after the index is rebuilt)."""
    global _index
    _index = None


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
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
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

    results = []
    for entry in _all_entries():
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
# guide pages (HTML -> text)
# --------------------------------------------------------------------------

class _GuideParser(HTMLParser):
    """Convert one FsDoc guide page into structured plain text.

    Emits headings as '#'-prefixed lines, fenced code blocks, bulleted lists,
    and skips the sidebar navigation.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.in_body = False
        self.body_depth = 0
        self.skip_depth = 0
        self.pre = 0
        self.code: list[str] = []
        self.para: list[str] = []
        self.list_item: list[str] | None = None
        self.in_heading: int = 0
        self.heading: list[str] = []
        self.in_cell: list[str] | None = None
        self.table_rows: list[list[str]] = []

    def _flush_para(self) -> None:
        if self.para:
            text = " ".join("".join(self.para).split())
            if text:
                self.lines.append(text)
            self.para = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        classes = set(a.get("class", "").split())

        if tag == "div" and "fs-doc-body" in classes:
            self.in_body = True
            self.body_depth = 1
            return
        if tag == "div" and self.in_body:
            self.body_depth += 1
            return
        if not self.in_body:
            return
        if tag in ("script", "style"):
            self.skip_depth += 1
            return

        if self.skip_depth:
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_para()
            self.in_heading = int(tag[1])
            self.heading = []
            return
        if tag == "pre":
            self._flush_para()
            self.pre += 1
            self.code = []
            return
        if tag == "p":
            self._flush_para()
            self.para = []
            return
        if tag == "br":
            self.para.append("\n")
            return
        if tag == "li":
            self._flush_para()
            self.list_item = []
            return
        if tag == "tr":
            self.table_rows.append([])
            return
        if tag == "td" or tag == "th":
            self.in_cell = []
            return
        if tag == "hr":
            self.lines.append("---")

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self.in_body:
            self.body_depth -= 1
            if self.body_depth == 0:
                self.in_body = False
                self._flush_para()
            return
        if not self.in_body:
            return
        if tag in ("script", "style") and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = " ".join("".join(self.heading).split())
            if text:
                self.lines.append("#" * self.in_heading + " " + text)
            self.in_heading = 0
            return
        if tag == "pre":
            self.pre = max(0, self.pre - 1)
            if self.pre == 0:
                self.lines.append("```fs\n" + "\n".join(self.code).strip() + "\n```")
                self.code = []
            return
        if tag == "p":
            self._flush_para()
            return
        if tag == "li":
            text = " ".join("".join(self.list_item).split()) if self.list_item else ""
            if text:
                self.lines.append("- " + text)
            self.list_item = None
            return
        if tag == "td" or tag == "th":
            if self.in_cell is not None and self.table_rows:
                self.table_rows[-1].append(" ".join("".join(self.in_cell).split()))
            self.in_cell = None
            return
        if tag == "table":
            for row in self.table_rows:
                self.lines.append("| " + " | ".join(row) + " |")
            self.table_rows = []
            return

    def handle_data(self, data: str) -> None:
        if not self.in_body or self.skip_depth:
            return
        if self.pre:
            self.code.append(data)
        elif self.in_heading:
            self.heading.append(data)
        elif self.in_cell is not None:
            self.in_cell.append(data)
        elif self.list_item is not None:
            self.list_item.append(data)
        else:
            self.para.append(data)


def guide_text(page: str) -> str:
    if page not in PAGES:
        raise ValueError(f"page must be one of: {', '.join(PAGES)}")
    path = FSDOC_DIR / f"{page}.html"
    if not path.is_file():
        raise ValueError(f"guide page not vendored: {page}.html")
    parser = _GuideParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return "\n\n".join(line for line in parser.lines if line).strip()


def guide_section(page: str, section: str | None = None) -> dict[str, Any]:
    """Return a guide page as text, optionally narrowed to one heading section."""
    full = guide_text(page)
    headings = re.findall(r"^(#+)\s+(.+)$", full, flags=re.MULTILINE)

    if section:
        target = section.lower()
        candidates = [
            (marker, title) for marker, title in headings if target in title.lower()
        ]
        if not candidates:
            raise ValueError(f"No section matching '{section}'. Available: " +
                             "; ".join(title for _, title in headings[:20]))
        marker, title = candidates[0]
        index = full.find("#" * len(marker) + " " + title)
        next_index = len(full)
        for later_marker, later_title in headings:
            pos = full.find("#" * len(later_marker) + " " + later_title, index + len(marker) + 2)
            if pos > index:
                next_index = pos
                break
        body = full[index:next_index].strip()
        return {"page": page, "section": title, "text": body}

    return {"page": page, "section": None, "headings": [t for _, t in headings], "text": full}


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
