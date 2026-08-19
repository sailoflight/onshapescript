#!/usr/bin/env python3
"""Offline queries over the project's own structured documentation.

The project's LLM-facing markdown (docs/, README.md, examples/) is parsed by
onshape_docs/scripts/build_docs_index.py into onshape_docs/index.json with the same typed-block
schema as the vendored FsDoc guide. This module serves that index to the docs_*
MCP tools: list pages, read a page or section on demand, and search across all
of them. Everything is local and deterministic — no network, no Onshape quota.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

DOCS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_INDEX_PATH = DOCS_ROOT / "index.json"

_docs: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _docs
    if _docs is None:
        if not DOCS_INDEX_PATH.is_file():
            raise FileNotFoundError(
                f"{DOCS_INDEX_PATH} is missing; run python3 onshape_docs/scripts/build_docs_index.py"
            )
        _docs = json.loads(DOCS_INDEX_PATH.read_text(encoding="utf-8"))
    return _docs


def reload() -> None:
    """Drop the cached index so a rebuild is visible immediately."""
    global _docs
    _docs = None


def _find_page(page: str) -> dict[str, Any]:
    for entry in _load()["pages"]:
        if entry["page"] == page:
            return entry
    raise ValueError(
        f"page must be one of: {', '.join(p['page'] for p in _load()['pages'])}"
    )


# --------------------------------------------------------------------------
# listing
# --------------------------------------------------------------------------

def list_pages() -> dict[str, Any]:
    """Page outline: every indexed doc page with its heading sections."""
    pages = _load()["pages"]
    out = []
    for entry in pages:
        out.append({
            "page": entry["page"],
            "path": entry["path"],
            "title": entry["title"],
            "sectionCount": len(entry["sections"]),
            "sections": [
                {"level": s["level"], "title": s["title"]}
                for s in entry["sections"]
            ],
        })
    return {
        "count": len(out),
        "pages": out,
        "note": "Pass page=<page> to docs_section to read one on demand.",
    }


# --------------------------------------------------------------------------
# section reading
# --------------------------------------------------------------------------

def _render_block(block: dict[str, Any]) -> list[str]:
    kind = block["type"]
    if kind == "para":
        return [block["text"]]
    if kind == "code":
        return [f"```{block.get('language', '')}\n{block['text']}\n```"]
    if kind == "list":
        return [
            "  " * item["depth"] + "- " + item["text"]
            for item in block["items"]
        ]
    if kind == "table":
        rows = ["| " + " | ".join(row) + " |" for row in block["rows"]]
        if rows:
            separator = "|" + "---|" * len(block["rows"][0])
            return [rows[0], separator, *rows[1:]]
        return rows
    return []


def _render_sections(sections: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for section in sections:
        lines = ["#" * section["level"] + " " + section["title"]]
        for block in section["blocks"]:
            lines.extend(_render_block(block))
        parts.append("\n".join(lines))
    return "\n\n".join(parts).strip()


def section(page: str, section_name: str | None = None) -> dict[str, Any]:
    """Return a project doc page as text, optionally narrowed to one section.

    Reads onshape_docs/index.json (built from the .md files), so page and section
    lookup is index-driven and on demand; the large markdown is never parsed at
    query time.
    """
    entry = _find_page(page)
    sections = entry["sections"]
    if section_name:
        target = section_name.lower()
        candidates = [s for s in sections if target in s["title"].lower()]
        if not candidates:
            raise ValueError(
                f"No section matching '{section_name}' in '{page}'. Available: "
                + "; ".join(s["title"] for s in sections[:20])
            )
        picked = candidates[0]
        selected = [picked]
        for later in sections[sections.index(picked) + 1:]:
            if later["level"] <= picked["level"]:
                break
            selected.append(later)
        return {
            "page": page,
            "title": entry["title"],
            "section": picked["title"],
            "text": _render_sections(selected),
        }
    return {
        "page": page,
        "title": entry["title"],
        "section": None,
        "headings": [s["title"] for s in sections],
        "text": _render_sections(sections),
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
    return "…" + text[best[0]: best[1]] + "…"


def _all_sections() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in _load()["pages"]:
        for section in entry["sections"]:
            out.append({
                "page": entry["page"],
                "pageTitle": entry["title"],
                "sectionTitle": section["title"],
                "text": _render_sections([section]),
            })
    return out


def search(query: str, page: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Keyword search across all project doc sections, ranked."""
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]
    if not tokens:
        raise ValueError("query must contain a searchable word")

    results: list[tuple[float, dict[str, Any]]] = []
    for entry in _all_sections():
        if page and entry["page"] != page:
            continue
        title = (entry["pageTitle"] + " " + entry["sectionTitle"]).lower()
        body = entry["text"].lower()
        total = 0.0
        for token in tokens:
            if token in title:
                total += 10 if token in entry["sectionTitle"].lower() else 6
            if token in body:
                total += 2
        if total <= 0:
            continue
        results.append((total, entry))
    results.sort(key=lambda pair: (-pair[0], pair[1]["page"], pair[1]["sectionTitle"]))

    ranked: list[dict[str, Any]] = []
    for total, entry in results[:limit]:
        ranked.append({
            "page": entry["page"],
            "sectionTitle": entry["sectionTitle"],
            "score": round(total, 1),
            "snippet": _snippet(entry["text"], tokens),
        })
    return {
        "count": len(ranked),
        "totalMatches": len(results),
        "results": ranked,
        "note": "Pass page=<page> to docs_section to read the full section.",
    }


# --------------------------------------------------------------------------
# health
# --------------------------------------------------------------------------

def index_health() -> dict[str, Any]:
    """Check every indexed page's sha256 against its source markdown file."""
    stale: list[str] = []
    pages = _load()["pages"]
    for entry in pages:
        path = REPO_ROOT / entry["path"]
        if not path.is_file():
            stale.append(entry["page"])
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            stale.append(entry["page"])
    return {
        "indexConsistent": not stale,
        "stalePages": stale,
        "pagesIndexed": len(pages),
        "sectionsIndexed": sum(len(p["sections"]) for p in pages),
        "rebuildHint": "Run python3 onshape_docs/scripts/build_docs_index.py to rebuild.",
    }
