#!/usr/bin/env python3
"""Newline-safe digests for the JSON doc indexes (CRLF checkout regression).

The builders hash a page's decoded text (``Path.read_text`` normalizes CRLF and
lone CR to LF) while the checkers used to hash raw bytes, so a Windows clone with
``core.autocrlf=true`` reported every indexed page as stale even though nothing
had changed. Both sides now share ``onshape_docs/query/source_digest.py``; these
tests pin the recorded digests and prove the Windows case directly.

Fully offline: the vendored index files are the fixture. Nothing is written into
the repository — the CRLF copy goes to a ``tempfile.TemporaryDirectory``.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_docs.query.source_digest import text_sha256  # noqa: E402

DOCS_ROOT = ROOT / "onshape_docs"
RAW = DOCS_ROOT / "reference" / "raw"
FSDOC_RAW = RAW / "fsdoc"
REST_RAW = RAW / "onshape-api"
AUTH_RAW = RAW / "onshape-api-docs"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def as_crlf(data: bytes) -> bytes:
    """The bytes a ``core.autocrlf=true`` checkout would produce."""
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


class TextDigestTest(unittest.TestCase):
    def test_crlf_file_digest_equals_lf_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            crlf = Path(tmp) / "page.md"
            crlf.write_bytes(b"a\r\nb\r\n")
            self.assertEqual(
                text_sha256(crlf),
                hashlib.sha256("a\nb\n".encode("utf-8")).hexdigest(),
            )

    def test_lone_cr_is_normalized_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.md"
            path.write_bytes(b"a\rb\r")
            self.assertEqual(
                text_sha256(path),
                hashlib.sha256("a\nb\n".encode("utf-8")).hexdigest(),
            )


class RecordedDigestTest(unittest.TestCase):
    def test_project_docs_index_pages_match(self) -> None:
        index = load_json(DOCS_ROOT / "index.json")
        stale = [
            page["page"]
            for page in index["pages"]
            if text_sha256(ROOT / page["path"]) != page["sha256"]
        ]
        self.assertEqual(stale, [])

    def test_fsdoc_guide_pages_and_library_match(self) -> None:
        guide = load_json(DOCS_ROOT / "reference" / "index" / "fsdoc" / "guide.json")
        stale = [
            page["page"]
            for page in guide["pages"]
            if text_sha256(FSDOC_RAW / page["path"]) != page["sha256"]
        ]
        self.assertEqual(stale, [])
        index = load_json(DOCS_ROOT / "reference" / "index" / "fsdoc" / "index.json")
        library = FSDOC_RAW / index.get("builtFrom", "library.html")
        self.assertEqual(text_sha256(library), index["librarySha256"])

    def test_auth_docs_pages_match_their_raw_html(self) -> None:
        docs = load_json(DOCS_ROOT / "reference" / "index" / "onshape-api-docs" / "api_docs.json")
        stale = [
            page["page"]
            for page in docs["pages"]
            if text_sha256(AUTH_RAW / page.get("path", f"{page['page']}.html"))
            != page["sha256"]
        ]
        self.assertEqual(stale, [])

    def test_rest_api_index_source_matches_openapi(self) -> None:
        index = load_json(DOCS_ROOT / "reference" / "index" / "onshape-api" / "api_index.json")
        source = REST_RAW / index.get("builtFrom", "openapi.json")
        self.assertEqual(text_sha256(source), index["sourceSha256"])

    def test_crlf_copy_of_real_page_keeps_recorded_digest(self) -> None:
        index = load_json(DOCS_ROOT / "index.json")
        entry = next(page for page in index["pages"] if page["path"].endswith(".md"))
        source = ROOT / entry["path"]
        crlf = as_crlf(source.read_bytes())
        self.assertIn(b"\r\n", crlf)
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / source.name
            copy.write_bytes(crlf)
            self.assertEqual(text_sha256(copy), entry["sha256"])


if __name__ == "__main__":
    unittest.main()
