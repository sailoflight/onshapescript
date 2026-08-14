#!/usr/bin/env python3
"""Parse the project's own markdown docs into a structured JSON index.

The MCP server serves two kinds of corpora: the vendored Onshape material
(reference/) and the project's own LLM-facing docs (docs/, README.md,
examples/). The vendored docs are indexed by build_fsdoc_index.py; this script
indexes the project's own markdown into docs/index.json with the SAME schema as
reference/fsdoc/guide.json — pages -> heading sections -> typed blocks (para,
code, list, table) — so the project docs are searchable and readable on demand
through the docs_* tools, never loaded whole.

The markdown files are the authored ORIGINALS and are kept as-is; docs/index.json
is a derived, indexed copy (each page records its sha256 so staleness is
detectable). Project-generated docs (the live-verification lessons, experiments)
keep their raw files too — nothing is deleted here.

Outputs:
  docs/index.json - {pages: [{page, path, sha256, title, sections}]}
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
INDEX_PATH = DOCS_DIR / "index.json"

# Ordered slug -> project-relative markdown path. Page order is the docs_list
# outline order. Add new LLM-facing docs here and re-run the script.
#
# README.md is deliberately NOT indexed: it is the human/GitHub landing page
# and its tool catalog / reference-data / running sections are summaries of
# docs/mcp-server.md, docs/fs-assistant.md, and docs/onshape-api.md. Indexing
# it would make every docs_search return duplicated hits. The LLM-facing
# corpus is the docs/ tree + the quick-reference + the example docs.
DOC_PAGES: dict[str, str] = {
    "fs-assistant": "docs/fs-assistant.md",
    "mcp-server": "docs/mcp-server.md",
    "onshape-api": "docs/onshape-api.md",
    "verification": "docs/verification/README.md",
    "llm-experience-fs": "docs/verification/llm-experience-fs.md",
    "llm-experience-api": "docs/verification/llm-experience-api.md",
    "live-verification": "docs/verification/live/README.md",
    "quick-reference": "reference/quick-reference.md",
    "reference": "reference/README.md",
    "example": "examples/branch-cable-trophy/README.md",
    "example-setup": "examples/branch-cable-trophy/docs/setup.md",
    "example-feature-parameters": "examples/branch-cable-trophy/docs/feature-parameters.md",
    "example-api-workflow": "examples/branch-cable-trophy/docs/onshape-api-workflow.md",
    "example-validation-contract": "examples/branch-cable-trophy/docs/validation-contract.md",
    "example-visual-review": "examples/branch-cable-trophy/docs/visual-review.md",
}

_BACKTICK = re.compile(r"`([^`]*)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"\*([^*\s][^*]*)\*")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^```([a-zA-Z0-9_-]*)")
_BULLET = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_TABLE_ROW = re.compile(r"^\|")
_TABLE_SEP = re.compile(r"^(\|[\s:|-]+\|?|\|?[\s:|-]+\|)$")
_SEP_ONLY = re.compile(r"^[\s|-]+$")


def inline(text: str) -> str:
    """Strip inline markdown to plain text (backticks, bold, italic, links)."""
    text = _BACKTICK.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _BOLD.sub(r"\1", text)
    text = _ITALIC.sub(r"\1", text)
    return " ".join(text.split())


class _Parser:
    """Line-based markdown -> {title, sections:[{level, title, blocks}]}."""

    def __init__(self, page: str) -> None:
        self.page = page
        self.title = ""
        self.sections: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.pending: list[dict[str, Any]] = []
        self.para: list[str] = []
        self.in_para = False
        self.code: list[str] = []
        self.in_code = False
        self.code_lang = ""
        self.list_items: list[dict[str, Any]] = []
        self.in_list = False
        self.table_rows: list[list[str]] = []
        self.in_table = False

    # -- block assembly ------------------------------------------------------

    def _append(self, block: dict[str, Any]) -> None:
        if self.current is not None:
            self.current["blocks"].append(block)
        else:
            self.pending.append(block)

    def _flush_para(self) -> None:
        if self.para:
            text = inline(" ".join(self.para))
            self.para = []
            self.in_para = False
            if text:
                self._append({"type": "para", "text": text})

    def _flush_code(self) -> None:
        if self.code:
            text = "\n".join(self.code).strip("\n")
            self.code = []
            if text:
                self._append({"type": "code", "language": self.code_lang, "text": text})
        self.in_code = False

    def _flush_list(self) -> None:
        if self.list_items:
            self._append({"type": "list", "items": self.list_items})
            self.list_items = []
        self.in_list = False

    def _flush_table(self) -> None:
        if self.table_rows:
            self._append({"type": "table", "rows": self.table_rows})
            self.table_rows = []
        self.in_table = False

    def _flush_all(self) -> None:
        self._flush_para()
        self._flush_code()
        self._flush_list()
        self._flush_table()

    def _start_section(self, level: int, title: str) -> None:
        self._flush_all()
        self.current = {"level": level, "title": title, "blocks": []}
        if self.pending:
            self.current["blocks"].extend(self.pending)
            self.pending = []
        if not self.title:
            self.title = title
        self.sections.append(self.current)

    # -- line dispatch -------------------------------------------------------

    def feed(self, line: str) -> None:
        if self.in_code:
            if line.startswith("```"):
                self._flush_code()
            else:
                self.code.append(line)
            return

        stripped = line.strip()
        if not stripped:
            self._flush_para()
            self._flush_list()
            self._flush_table()
            return

        heading = _HEADING.match(line)
        if heading:
            self._start_section(len(heading.group(1)), inline(heading.group(2)))
            return

        if line.startswith("```"):
            self._flush_para()
            self._flush_list()
            self._flush_table()
            self.code_lang = _FENCE.match(line).group(1) if _FENCE.match(line) else ""
            self.in_code = True
            return

        # Tables are consumed wholesale in parse_markdown (header + separator +
        # data rows); feed() never sees a `|` row. Just make sure no table block
        # is left half-open here.

        bullet = _BULLET.match(line)
        if bullet:
            indent = len(bullet.group(1))
            text = inline(bullet.group(3))
            if not self.in_list:
                self._flush_para()
                self._flush_table()
                self.in_list = True
            self.list_items.append({"text": text, "depth": indent // 2})
            return

        if self.in_list:
            # A non-blank line that is not a bullet ends the list. Continuation
            # lines (indented, no marker) extend the previous item.
            if stripped and not _BULLET.match(line):
                if line[:1].isspace():
                    self.list_items[-1]["text"] += " " + inline(stripped)
                    return
                self._flush_list()
            else:
                return

        if not self.in_para:
            self.in_para = True
        self.para.append(stripped)

    def _add_table_row(self, line: str) -> None:
        cells = [inline(cell) for cell in line.strip().strip("|").split("|")]
        self.table_rows.append(cells)


def _is_separator(line: str) -> bool:
    stripped = line.strip()
    if not _TABLE_ROW.match(line):
        return False
    body = stripped.strip("|")
    return bool(body) and _SEP_ONLY.match(body) and "-" in body


def parse_markdown(text: str, page: str) -> dict[str, Any]:
    parser = _Parser(page)
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not parser.in_code and _TABLE_ROW.match(line) and i + 1 < len(lines) \
                and _is_separator(lines[i + 1]):
            # Consume the whole table (header + separator + data rows).
            parser._flush_para()
            parser._flush_list()
            parser._flush_table()
            parser.in_table = True
            parser._add_table_row(line)
            i += 2  # header + separator
            while i < len(lines) and _TABLE_ROW.match(lines[i]):
                parser._add_table_row(lines[i])
                i += 1
            parser._flush_table()
            continue

        parser.feed(line)
        i += 1
    parser._flush_all()

    title = parser.title or (parser.sections[0]["title"] if parser.sections else page)
    return {
        "title": title,
        "sections": [s for s in parser.sections if s["blocks"]],
    }


def build() -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for page, relpath in DOC_PAGES.items():
        path = ROOT / relpath
        if not path.is_file():
            print(f"  skipped (missing): {relpath}", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8")
        parsed = parse_markdown(text, page)
        pages.append({
            "page": page,
            "path": relpath,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            **parsed,
        })
    return pages


def main() -> int:
    pages = build()
    INDEX_PATH.write_text(
        json.dumps({"pages": pages}, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    counts = {
        "pages": len(pages),
        "sections": sum(len(p["sections"]) for p in pages),
        "blocks": sum(
            len(s["blocks"]) for p in pages for s in p["sections"]
        ),
    }
    print(json.dumps(counts, indent=2))
    print(f"wrote {INDEX_PATH} ({INDEX_PATH.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
