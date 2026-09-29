"""Digest of a *text* source, as the index builders read it.

A builder reads a page with ``Path.read_text`` (universal newlines: CRLF and
lone CR become LF) and hashes the decoded text; a checker that hashed raw bytes
instead disagreed with it on any tree whose line endings differ from the index --
a Windows clone of this repository, or a copied tree -- and reported every page
as stale although its content was unchanged.

One function, used by builder and checker alike, makes that drift impossible:
the digest identifies the text, not the line-ending convention. Binary sources
keep a raw-byte digest on purpose (``fdm_analysis.contracts.file_sha256`` and the
release manifest are byte-exact).
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def text_sha256(path: Path | str) -> str:
    """SHA-256 of the UTF-8 text of ``path``, newline-normalized.

    Byte-for-byte equivalent to
    ``hashlib.sha256(Path(path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()``,
    which is what the index builders already computed.
    """
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
