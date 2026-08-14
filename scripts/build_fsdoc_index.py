#!/usr/bin/env python3
"""Parse reference/fsdoc/library.html into a structured JSON index.

library.html is the official FeatureScript function/type reference. This script
walks its DOM and emits reference/fsdoc/index.json containing every module,
function, type/enum/const/predicate, parameter, and description as plain text,
so the local MCP tools can answer FeatureScript questions offline.

Outputs (all data is vendored; nothing is fetched here):
  modules    - {file, display, category}
  functions  - {name, module, category, signature, returnType, parameters, description}
  types      - {name, module, category, kind, description, values}
  constants  - {name, module, description}
  predicates - {name, module, signature, description}
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LIBRARY_PATH = ROOT / "reference" / "fsdoc" / "library.html"
INDEX_PATH = ROOT / "reference" / "fsdoc" / "index.json"


def load_category_map(source: str) -> dict[str, str]:
    """Map module filename -> category using the sidebar group headings.

    Only the sidebar is scanned: the module headers in the body also link to
    themselves with `href="#module-..."`, which would otherwise overwrite the
    sidebar's category with whichever heading came last.
    """
    sidebar_end = re.search(r"<h2 [^>]*id=\"module-", source)
    sidebar = source if sidebar_end is None else source[: sidebar_end.start()]
    mapping: dict[str, str] = {}
    current: str = ""
    pattern = re.compile(
        r'<div class="fs-section-heading"><a href="#category-([^"]+)">([^<]+)</a></div>'
        r'|<a href="#module-([^"]+)">([^<]+)</a>'
    )
    for match in pattern.finditer(sidebar):
        if match.group(1):
            current = match.group(2)
        elif match.group(3):
            mapping[match.group(3)] = current
    return mapping


class _Cell:
    """Accumulates one table cell (name/type/description) plus markers."""

    __slots__ = ("text", "marker", "example")

    def __init__(self) -> None:
        self.text: list[str] = []
        self.marker: list[str] = []
        self.example: list[str] = []

    def desc(self) -> str:
        return " ".join("".join(self.text).split())

    def requirement(self) -> str | None:
        value = " ".join("".join(self.marker).split())
        return value or None

    def example_value(self) -> str | None:
        value = " ".join("".join(self.example).split())
        return value or None


class LibraryParser(HTMLParser):
    def __init__(self, category_map: dict[str, str]) -> None:
        super().__init__(convert_charrefs=True)
        self.categories = category_map
        self.modules: list[dict[str, Any]] = []
        self.functions: list[dict[str, Any]] = []
        self.types: list[dict[str, Any]] = []
        self.constants: list[dict[str, Any]] = []
        self.predicates: list[dict[str, Any]] = []

        self.current_module: str = ""
        self.entry: dict[str, Any] | None = None
        self.in_signature = False
        self.signature_capture: str | None = None  # name | kind | args | ret
        self.sig_bufs: dict[str, list[str]] = {"name": [], "kind": [], "args": [], "ret": []}

        self.in_doc = False
        self.doc_depth = 0
        self.paragraph = False
        self.paragraph_buf: list[str] = []
        self.description: list[str] = []
        self.skip_next_text = False

        self.in_table = False
        self.table_header: list[str] = []
        self.row: dict[str, Any] | None = None
        self.rows: list[dict[str, Any]] = []
        self.cell_kind: str | None = None  # name | type | desc
        self.cell = _Cell()
        self.in_italic = 0
        self.in_blockquote = 0

    # -- helpers ----------------------------------------------------------

    def _attributes(self, attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: (value or "") for key, value in attrs}

    def _end_signature(self) -> None:
        if not self.entry:
            return
        name = "".join(self.sig_bufs["name"]).strip()
        kind = "".join(self.sig_bufs["kind"]).strip() or None
        args = " ".join("".join(self.sig_bufs["args"]).split())
        ret = " ".join("".join(self.sig_bufs["ret"]).split())
        ret = ret[len("returns"):].strip() if ret.startswith("returns") else ret
        entry = self.entry
        entry["name"] = name
        entry["module"] = self.current_module
        entry["category"] = self.categories.get(self.current_module, "")
        if args:
            entry["signature"] = f"{name}{args}"
        if ret:
            entry["returnType"] = ret
        entry["kind"] = kind
        self.in_signature = False
        self.signature_capture = None
        self.sig_bufs = {"name": [], "kind": [], "args": [], "ret": []}

    def _end_doc(self) -> None:
        if not self.entry:
            return
        entry = self.entry
        kind = entry.get("kind")
        entry["description"] = " ".join(" ".join(self.description).split())
        if self.rows:
            detail_key = "values" if kind in ("type", "enum") else "parameters"
            entry[detail_key] = self.rows
        if kind is None:
            self.functions.append(entry)
        elif kind in ("type", "enum"):
            self.types.append(entry)
        elif kind == "const":
            self.constants.append(entry)
        else:  # predicate
            self.predicates.append(entry)
        self.entry = None
        self.in_doc = False
        self.paragraph = False
        self.description = []
        self.rows = []

    def _start_row(self, classes: set[str]) -> None:
        self.row = {
            "level": "subfield" if "subfield" in classes else "top-level",
            "name": [], "type": [], "desc": [],
        }
        self.rows.append(self.row)

    def _cell_text(self) -> list[str]:
        assert self.row is not None
        return self.row.get(self.cell_kind, [])  # type: ignore[return-value]

    # -- HTMLParser callbacks ---------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = self._attributes(attrs)
        classes = set(a.get("class", "").split())

        if tag == "h2" and a.get("id", "").startswith("module-"):
            self.current_module = a["id"][len("module-"):]
            self.modules.append({
                "file": self.current_module,
                "display": a.get("href", "").rsplit(">", 1)[-1] or self.current_module,
                "category": self.categories.get(self.current_module, ""),
            })
            return

        if tag == "p" and "node-signature" in classes:
            if self.entry:
                self._end_doc()
            self.entry = {"anchor": a.get("id", "")}
            self.in_signature = True
            return

        if self.in_signature and tag == "span":
            for key, class_name in (
                ("name", "fs-symbol-name"),
                ("kind", "fs-symbol-descriptor"),
                ("args", "fs-function-arguments"),
                ("ret", "fs-function-return"),
            ):
                if class_name in classes:
                    self.signature_capture = key
                    return
            self.signature_capture = None
            return

        if tag == "div" and "fs-doc-content" in classes and not self.in_doc:
            self.in_doc = True
            self.doc_depth = 1
            return

        if not self.in_doc:
            return

        if tag == "div":
            self.doc_depth += 1
            return

        if tag == "table":
            self.in_table = True
            self.table_header = []
            return

        if self.in_table and tag == "tr":
            self._start_row(classes)
            return

        if self.in_table and tag == "td":
            if "fs-name-column" in classes:
                self.cell_kind = "name"
            elif "fs-type-column" in classes:
                self.cell_kind = "type"
            elif "fs-description-column" in classes:
                self.cell_kind = "desc"
            else:
                self.cell_kind = None
            self.cell = _Cell()
            return

        if self.in_table and tag == "th":
            self.cell = _Cell()
            self.cell_kind = "header"
            return

        if tag == "i":
            self.in_italic += 1
            return

        if tag == "blockquote":
            self.in_blockquote += 1
            return

        if tag == "p" and "fs-example-label" in classes:
            self.skip_next_text = True
            return

        if tag == "p" and not self.in_table:
            self.paragraph = True
            self.paragraph_buf = []
            return

        if tag == "br":
            self._emit(" ")
            return

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self.in_signature:
            self._end_signature()
            return

        if self.in_doc and tag == "div":
            self.doc_depth -= 1
            if self.doc_depth == 0:
                self._end_doc()
            return

        if not self.in_doc:
            return

        if tag == "table":
            self.in_table = False
            return

        if tag == "tr":
            self.cell_kind = None
            self.row = None
            return

        if tag == "td":
            if self.cell_kind == "header":
                self.table_header.append("".join(self.cell.text))
            elif self.cell_kind and self.row is not None:
                self.row[self.cell_kind] = self.cell
            self.cell = _Cell()
            self.cell_kind = None
            return

        if tag == "th":
            self.cell_kind = None
            self.cell = _Cell()
            return

        if tag == "i":
            self.in_italic = max(0, self.in_italic - 1)
            return

        if tag == "blockquote":
            self.in_blockquote = max(0, self.in_blockquote - 1)
            return

        if tag == "p" and not self.in_table:
            if self.paragraph:
                text = " ".join("".join(self.paragraph_buf).split())
                if text:
                    self.description.append(text)
                self.paragraph = False
            return

    def handle_data(self, data: str) -> None:
        if self.skip_next_text:
            self.skip_next_text = False
            return

        if self.in_signature:
            if self.signature_capture:
                self.sig_bufs[self.signature_capture].append(data)
            return

        if not self.in_doc:
            return

        if self.in_table:
            if self.cell_kind is None or self.row is None:
                return
            if self.in_blockquote:
                self.cell.example.append(data)
            elif self.in_italic and self.cell_kind == "desc":
                self.cell.marker.append(data)
            else:
                self._emit(data)
            return

        if self.paragraph:
            self.paragraph_buf.append(data)

    def _emit(self, data: str) -> None:
        if self.cell_kind is not None and self.row is not None:
            self.row[self.cell_kind] = self.cell  # keep the cell object live
            if self.cell_kind == "name":
                self.cell.text.append(data)
            elif self.cell_kind == "type":
                self.cell.text.append(data)
            elif self.cell_kind == "desc":
                self.cell.text.append(data)


def _clean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert captured _Cell objects to plain dicts and drop empties."""
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        name_cell = row.get("name")
        type_cell = row.get("type")
        desc_cell = row.get("desc")
        entry: dict[str, Any] = {
            "level": row["level"],
            "name": " ".join("".join(name_cell.text).split()) if name_cell else "",
            "type": " ".join("".join(type_cell.text).split()) if type_cell else "",
        }
        if desc_cell:
            entry["description"] = desc_cell.desc()
            requirement = desc_cell.requirement()
            example = desc_cell.example_value()
            if requirement:
                entry["requirement"] = requirement
            if example:
                entry["example"] = example
        if entry["name"] or entry["type"] or entry.get("description"):
            cleaned.append(entry)
    return cleaned


def _nest_subfields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach subfield rows (map fields) to their top-level parameter."""
    params: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in rows:
        if row["level"] == "top-level":
            item = {key: value for key, value in row.items() if key != "level"}
            item["fields"] = []
            params.append(item)
            current = item
        else:
            if current is None:
                continue
            current["fields"].append({key: value for key, value in row.items() if key != "level"})
    return params


def build() -> dict[str, Any]:
    source = LIBRARY_PATH.read_text(encoding="utf-8")
    categories = load_category_map(source)
    parser = LibraryParser(categories)
    parser.feed(source)

    functions = []
    for entry in parser.functions:
        entry["parameters"] = _nest_subfields(_clean(entry.get("parameters", [])))
        functions.append(entry)

    types = []
    for entry in parser.types:
        entry["values"] = _clean(entry.get("values", []))
        types.append(entry)

    constants = [
        {"name": e["name"], "module": e["module"], "description": e.get("description", "")}
        for e in parser.constants
    ]
    predicates = [
        {
            "name": e["name"],
            "module": e["module"],
            "signature": e.get("signature", ""),
            "description": e.get("description", ""),
        }
        for e in parser.predicates
    ]

    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return {
        "librarySha256": digest,
        "builtFrom": "library.html",
        "modules": parser.modules,
        "functions": functions,
        "types": types,
        "constants": constants,
        "predicates": predicates,
    }


def main() -> int:
    index = build()
    INDEX_PATH.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = {
        "modules": len(index["modules"]),
        "functions": len(index["functions"]),
        "types": len(index["types"]),
        "constants": len(index["constants"]),
        "predicates": len(index["predicates"]),
    }
    print(json.dumps(counts, indent=2))
    print(f"wrote {INDEX_PATH} ({INDEX_PATH.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
