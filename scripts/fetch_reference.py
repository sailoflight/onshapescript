#!/usr/bin/env python3
"""Vendor the official Onshape FeatureScript reference material into reference/raw/.

Downloads and extracts (raw tier 0 — build inputs, never served to callers):
  reference/raw/fsdoc/        - the FsDoc documentation pages from cad.onshape.com
                            (function/type reference, language guide, tutorials)
  reference/raw/std-library/  - the FeatureScript standard library source, mirrored
                            from github.com/javawizard/onshape-std-library-mirror
                            (MIT-licensed, auto-updating mirror of the library)

Only the Python standard library is used. The script is idempotent: files are
overwritten in place, and re-running after a change re-syncs the vendored copy.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = ROOT / "reference"
FSDOC_DIR = REFERENCE_DIR / "raw" / "fsdoc"
STD_LIB_DIR = REFERENCE_DIR / "raw" / "std-library"

FSDOC_BASE = "https://cad.onshape.com/FsDoc/"

# Every FsDoc page. library.html is the full function/type reference; the rest
# are language guide pages and the tutorial.
FSDOC_PAGES = [
    "index.html",
    "intro.html",
    "feature-types.html",
    "uispec.html",
    "output.html",
    "variables.html",
    "modeling.html",
    "tables.html",
    "computed-part-properties.html",
    "imports.html",
    "debugging-in-feature-studios.html",
    "tokens.html",
    "type-tags.html",
    "top-level.html",
    "syntax.html",
    "annotations.html",
    "exceptions.html",
    "relational.html",
    "library.html",
    "tutorials/create-a-slot-feature.html",
]

MIRROR_OWNER = "javawizard"
MIRROR_REPO = "onshape-std-library-mirror"
MIRROR_BRANCH = "without-versions"
MIRROR_TARBALL = (
    f"https://codeload.github.com/{MIRROR_OWNER}/{MIRROR_REPO}/tar.gz/refs/heads/{MIRROR_BRANCH}"
)
MIRROR_LICENSE_URL = f"https://raw.githubusercontent.com/{MIRROR_OWNER}/{MIRROR_REPO}/{MIRROR_BRANCH}/LICENSE.txt"
MIRROR_README_URL = f"https://raw.githubusercontent.com/{MIRROR_OWNER}/{MIRROR_REPO}/{MIRROR_BRANCH}/README.md"


def fetch_bytes(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def write(path: Path, data: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


def fetch_fsdoc(quiet: bool = False) -> tuple[int, int]:
    written = failed = 0
    for page in FSDOC_PAGES:
        url = FSDOC_BASE + page
        target = FSDOC_DIR / page
        try:
            data = fetch_bytes(url)
        except Exception as error:  # keep going; report at the end
            failed += 1
            print(f"  FAIL {url}: {error}", file=sys.stderr)
            continue
        size = write(target, data)
        written += size
        if not quiet:
            print(f"  ok   {page}  ({size} bytes)")
    return written, failed


def fetch_std_library(quiet: bool = False) -> tuple[int, int]:
    """Download the tarball and extract the .fs sources plus license/readme."""
    written = failed = 0
    try:
        archive = fetch_bytes(MIRROR_TARBALL)
    except Exception as error:
        print(f"  FAIL {MIRROR_TARBALL}: {error}", file=sys.stderr)
        return 0, 1
    if not quiet:
        print(f"  ok   {MIRROR_REPO} tarball ({len(archive)} bytes)")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        prefix = None
        for member in tar.getmembers():
            if not member.isfile():
                continue
            parts = member.name.split("/", 1)
            if len(parts) != 2 or not parts[0]:
                continue
            prefix = prefix or parts[0]
            relpath = parts[1]
            if not (relpath.endswith(".fs") or relpath in {"LICENSE.txt", "README.md"}):
                continue
            content = tar.extractfile(member).read()
            size = write(STD_LIB_DIR / relpath, content)
            written += size
            if not quiet:
                print(f"  ok   {relpath}  ({size} bytes)")
    # Pin the source version for reproducible attribution.
    write(REFERENCE_DIR / "raw" / "std-library-VERSION.txt", (MIRROR_BRANCH + "\n").encode())
    return written, failed


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_attribution() -> None:
    doc_count = len(list(FSDOC_DIR.rglob("*.html"))) if FSDOC_DIR.exists() else 0
    lib_count = len(list(STD_LIB_DIR.glob("*.fs"))) if STD_LIB_DIR.exists() else 0
    readme = REFERENCE_DIR / "README.md"
    lines = [
        "# Vendored reference corpus",
        "",
        "Fetched by `scripts/fetch_reference.py` (FsDoc + std library) and the",
        "`scripts/fetch_onshape_api*.py` fetchers. Onshape/third-party material, vendored",
        "so the local MCP tools answer without a network round trip. Three tiers, in",
        "reading order:",
        "",
        "| Tier | Directory | Contents | Who reads it |",
        "|---|---|---|---|",
        "| 0 | `raw/` | build inputs: FsDoc HTML, std-library `.fs`, OpenAPI spec, dev-doc HTML | fetch/build scripts only; `verify_docs.py` sha256-pins them; tools never read |",
        "| 1 | `quick/` | compact distilled indexes (`quick.json`, `api_quick.json`) | `fs_search`, `onshape_api_find` — the cheap first look for candidates |",
        "| 2 | `index/` | full-detail indexes (`index.json`, `guide.json`, `api_index.json`, `api_docs.json`) | `fs_get_function`, `fs_guide_section`, `onshape_api_*` — on-demand deep read |",
        "",
        "## raw/fsdoc/",
        "",
        f"- {doc_count} official documentation pages from `{FSDOC_BASE}` (the",
        "  FeatureScript function/type reference, the language guide, and the tutorial).",
        "  © Onshape. Used for local reference; see the Onshape terms of service.",
        "",
        "## raw/std-library/",
        "",
        f"- {lib_count} FeatureScript standard library source files, mirrored from",
        f"  `https://github.com/{MIRROR_OWNER}/{MIRROR_REPO}` (branch `{MIRROR_BRANCH}`).",
        "  The mirror auto-updates from Onshape and is MIT-licensed; `LICENSE.txt` is",
        "  vendored alongside the sources.",
        "",
        "## raw/onshape-api/ + raw/onshape-api-docs/",
        "",
        "- `raw/onshape-api/openapi.json` — the live Onshape REST API OpenAPI",
        "  definition, fetched from `https://cad.onshape.com/api/openapi` with the",
        "  local credentials by `scripts/fetch_onshape_api.py` (always the current",
        "  server version). `index/onshape-api/api_index.json` and",
        "  `quick/onshape-api/api_quick.json` are flattened from it by",
        "  `scripts/build_onshape_api_index.py`.",
        "- `raw/onshape-api-docs/` — the OAuth2 / API-key / error-code / rate-limit",
        "  pages (public GitHub Pages, zero API-token cost), parsed into",
        "  `index/onshape-api-docs/api_docs.json`.",
        "",
        "## Project docs",
        "",
        "The project's own LLM-facing documentation (`docs/*.md`,",
        "`reference/quick-reference.md`, example docs; README.md is the human landing",
        "page and intentionally not indexed) is indexed by",
        "`scripts/build_docs_index.py` into `docs/index.json` (same typed-block",
        "schema as `guide.json`) and served by the `docs_*` tools. The markdown",
        "files stay the authored originals.",
        "",
        "## Reading order for callers",
        "",
        "Never read `raw/` — it exists only as build input and is sha256-pinned by",
        "`docs/verification/verify_docs.py`. For a question: start with a `quick/`",
        "index (cheap candidate lists), then pull the one entry you need from `index/`",
        "at full detail. That ordering is exactly what the MCP tools already do",
        "(`fs_search` → `fs_get_function`); `docs/index.json` mirrors the project's own",
        "markdown the same way (see `docs/mcp-server.md`).",
        "",
        "## Updating",
        "",
        "Re-run the fetch scripts to re-sync each raw tree, then the index builders",
        "(which parse `raw/fsdoc/library.html` into `index/fsdoc/index.json`, the guide",
        "pages into `index/fsdoc/guide.json`, both into the compact",
        "`quick/fsdoc/quick.json`, and the OpenAPI spec into the onshape-api indexes —",
        "all record source sha256 for staleness checks):",
        "",
        "```bash",
        "python3 scripts/fetch_reference.py",
        "python3 scripts/build_fsdoc_index.py",
        "python3 scripts/fetch_onshape_api.py   # needs onshape-credentials.json",
        "python3 scripts/build_onshape_api_index.py",
        "```",
        "",
        "`reference/quick-reference.md` is a curated cheat-sheet authored alongside",
        "these files; refresh it by hand when a major version bump changes the API.",
    ]
    write(REFERENCE_DIR / "README.md", ("\n".join(lines) + "\n").encode())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-docs", action="store_true", help="skip the FsDoc pages")
    parser.add_argument("--skip-library", action="store_true", help="skip the standard library source")
    parser.add_argument("--quiet", action="store_true", help="only print failures and totals")
    args = parser.parse_args()

    print(f"Fetching into {REFERENCE_DIR}")
    total = 0
    failed_total = 0
    if not args.skip_docs:
        print("  FsDoc pages:")
        n, failed = fetch_fsdoc(args.quiet)
        total += n
        failed_total += failed
        print(f"    {n} bytes written, {failed} failed")
    if not args.skip_library:
        print("  Standard library source:")
        n, failed = fetch_std_library(args.quiet)
        total += n
        failed_total += failed
        print(f"    {n} bytes written, {failed} failed")
    write_attribution()
    print(f"Total {total} bytes in {REFERENCE_DIR}")

    docs_sha = sha256_of(FSDOC_DIR / "library.html")
    print(f"  fsdoc/library.html sha256 = {docs_sha}")
    # Nonzero exit lets callers (e.g. the MCP update tool) detect partial failures.
    return 1 if failed_total else 0


if __name__ == "__main__":
    sys.exit(main())
