#!/usr/bin/env python3
"""Parse the vendored Onshape developer docs into structured JSON.

reference/onshape-api-docs/<page>.html are public GitHub Pages documents
(auth + error handling) fetched by scripts/fetch_onshape_api_docs.py. This
script parses each page's <main> into heading sections with typed blocks and
emits reference/onshape-api-docs/api_docs.json:

  pages:      [{page, title, url, sha256, sections: [{level, title, blocks}]}]
  errorCodes: [{code, name, category, description, nextSteps}]  (from errors)

Nothing is fetched here; each page's sha256 is recorded for staleness checks.
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
DOCS_DIR = ROOT / "reference" / "onshape-api-docs"
DOCS_PATH = DOCS_DIR / "api_docs.json"

PAGE_URLS = {
    "errors": "https://onshape-public.github.io/docs/api-adv/errors/",
    "limits": "https://onshape-public.github.io/docs/auth/limits/",
    "oauth": "https://onshape-public.github.io/docs/auth/oauth/",
    "apikeys": "https://onshape-public.github.io/docs/auth/apikeys/",
}
PAGES = tuple(PAGE_URLS.keys())

# Blocks that end an in-progress paragraph / start a new block type.
_START_BLOCK = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "pre", "ul", "ol",
                "table", "blockquote"}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DocsParser(HTMLParser):
    """Extract heading sections with typed blocks from a page's <main>."""

    def __init__(self) -> None:
        super().__init__()
        self.in_main = False
        self.main_depth = 0
        self.sections: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.block: dict[str, Any] | None = None
        self.buf: list[str] = []

    def _commit(self) -> None:
        """Attach the accumulated buffer to self.block and store it."""
        if self.current is None:
            self.block = None
            self.buf = []
            return
        block, self.block = self.block, None
        text = "".join(self.buf).strip()
        self.buf = []
        if block is None:
            return
        kind = block["type"]
        if kind in ("para", "note") and text:
            self.current["blocks"].append({"type": kind, "text": text})
        elif kind == "code" and text:
            self.current["blocks"].append({
                "type": "code", "language": block["language"], "text": text,
            })
        elif kind == "list":
            if text:
                block["items"].append(text)
            if block["items"]:
                self.current["blocks"].append({"type": "list", "items": block["items"]})
        elif kind == "table" and block["rows"]:
            self.current["blocks"].append({"type": "table", "rows": block["rows"]})

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "main":
            self.in_main = True
            self.main_depth = 1
            return
        if not self.in_main:
            return
        self.main_depth += 1
        attributes = dict(attrs)
        if tag in _START_BLOCK:
            self._commit()
            if tag[0] == "h":
                self.current = {"level": int(tag[1]), "title": "", "blocks": []}
                self.sections.append(self.current)
            elif tag == "pre":
                self.block = {"type": "code", "language": ""}
            elif tag == "p":
                self.block = {"type": "para"}
            elif tag in ("ul", "ol"):
                self.block = {"type": "list", "items": []}
            elif tag == "table":
                self.block = {"type": "table", "rows": [], "_row": []}
            elif tag == "blockquote":
                self.block = {"type": "note"}
        elif tag == "code":
            if self.block and self.block["type"] == "code":
                match = re.search(r"language-([\w+]+)", attributes.get("class", ""))
                if match:
                    self.block["language"] = match.group(1)
        elif tag == "br":
            self.buf.append("\n")

    def handle_data(self, data: str) -> None:
        if self.in_main and self.current is not None:
            self.buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "main":
            self.in_main = False
            return
        if not self.in_main:
            return
        self.main_depth -= 1
        if tag[0] == "h" and tag[1].isdigit() and self.current is not None:
            self.current["title"] = "".join(self.buf).strip()
            self.buf = []
        elif tag in ("p", "pre", "ul", "ol", "blockquote", "table"):
            if tag == "table" and self.block and self.block["type"] == "table":
                self._finish_row()
            self._commit()
        elif tag == "tr" and self.block and self.block["type"] == "table":
            self._finish_row()
        elif tag in ("td", "th") and self.block and self.block["type"] == "table":
            cell = "".join(self.buf).strip()
            self.buf = []
            if cell:
                self.block["_row"].append(cell)
        elif tag == "li" and self.block and self.block["type"] == "list":
            item = "".join(self.buf).strip()
            self.buf = []
            if item:
                self.block["items"].append(item)

    def _finish_row(self) -> None:
        if self.block and self.block["type"] == "table" and self.block["_row"]:
            self.block["rows"].append(self.block["_row"])
            self.block["_row"] = []


def extract_error_codes(page: dict[str, Any]) -> list[dict[str, Any]]:
    codes: list[dict[str, Any]] = []
    category = ""
    for section in page["sections"]:
        if section["level"] == 2:
            category = section["title"]
        elif section["level"] == 3 and category and re.match(r"^\d{3} ", section["title"]):
            paragraphs = [
                block["text"]
                for block in section["blocks"]
                if block["type"] in ("para", "note")
            ]
            codes.append({
                "code": int(section["title"][:3]),
                "name": section["title"][4:].strip(),
                "category": category,
                "description": paragraphs[0] if paragraphs else "",
                "nextSteps": paragraphs[1] if len(paragraphs) > 1 else "",
            })
    return codes


def build() -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    error_codes: list[dict[str, Any]] = []
    for page in PAGES:
        path = DOCS_DIR / f"{page}.html"
        if not path.is_file():
            raise FileNotFoundError(
                f"{path} is missing; run python3 scripts/fetch_onshape_api_docs.py"
            )
        parser = DocsParser()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        title = ""
        for section in parser.sections:
            if section["level"] == 1:
                title = section["title"]
                break
        entry = {
            "page": page,
            "title": title,
            "url": PAGE_URLS[page],
            "sha256": sha256_of(path),
            "sections": parser.sections,
        }
        pages.append(entry)
        if page == "errors":
            error_codes = extract_error_codes(entry)
    return {"pages": pages, "errorCodes": error_codes}


def main() -> int:
    index = build()
    DOCS_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    pages = ", ".join(f"{p['page']} ({len(p['sections'])} sections)" for p in index["pages"])
    print(f"  ok   api_docs.json — {pages}")
    print(f"  errorCodes: {len(index['errorCodes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
