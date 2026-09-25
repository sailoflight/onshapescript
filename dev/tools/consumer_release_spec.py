#!/usr/bin/env python3
"""Consumer Release artifact specification: whitelist, denylist, plan, invariants.

This module is a SPEC, not a packager. It never writes files, never creates an
archive, and never copies anything. ``plan()`` returns the file list that a
future packager would be allowed to emit; ``validate()`` reports invariant
violations. The release procedures live in ``docs/operations/RELEASE.md``.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fdm_analysis.contracts import file_sha256  # noqa: E402

#: MCP server version from ``mcp_main/win/mcp/identity.py`` (NOT the governance
#: package release, which is a development-plane dependency).
MCP_SERVER_VERSION = "1.3.0"
GOVERNANCE_RELEASE = "3.0.7"
MANIFEST_NAME = "release-manifest.json"
CHECKSUM_SIDECAR_NAME = "SHA256SUMS"

#: Everything a consumer artifact may contain. Directory entries end with "/".
WHITELIST: tuple[str, ...] = (
    "mcp_main/",
    "mcp_main/dsh/",  # runtime policy companion, also covered by mcp_main/
    "onshape_browser_mode/",  # includes wheels/ and requirements-windows.txt
    "onshape_rest_api_mode/",
    # onshape_docs runtime subset: what the server's offline doc tools read.
    "onshape_docs/__init__.py",
    "onshape_docs/README.md",
    "onshape_docs/index.json",
    "onshape_docs/query/",
    "onshape_docs/experience/",
    "onshape_docs/guide/",
    "onshape_docs/reference/README.md",
    "onshape_docs/reference/quick-reference.md",
    "onshape_docs/reference/index/",
    "onshape_docs/reference/quick/",
    # consumer / operator docs
    "docs/usage/MCP_CONSUMER.md",
    "docs/operations/MCP_RUNBOOK.md",
    "docs/operations/RELEASE.md",
    "docs/generated/",
)

#: Never bundled, and never deleted by upgrade or uninstall. Directory entries
#: end with "/". ``__pycache__/`` is local build noise, not release content.
DENYLIST: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
    "agent-project-guides/",
    ".agent-guides/",
    ".agent-project-guides/",
    ".agent-project-guides.json",
    "dev/",
    ".git/",
    ".venv/",
    "temp/",
    ".mnemon/",
    "__pycache__/",
    # mutable runtime state: preserved across install/upgrade/rollback
    "onshape_browser_mode/config/browser-state.json",
    "onshape_browser_mode/config/browser.local.toml",
    "onshape_browser_mode/user_data/",
    "onshape_browser_mode/outputs/",
    "onshape_rest_api_mode/config/onshape-credentials.json",
    "onshape_rest_api_mode/config/onshape-state.json",
    "onshape_rest_api_mode/config/api-usage.json",
    "onshape_rest_api_mode/outputs/",
    "mcp_main/win/mcp/config/tool_views.local.toml",
)

#: Paths whose artifact membership still needs a human decision. Neither
#: whitelisted nor denylisted; not planned by default.
PENDING_DECISION: tuple[str, ...] = (
    "onshape_docs/reference/raw/",
    "fdm_analysis/",
)


@dataclass(frozen=True)
class ArtifactEntry:
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class ReleasePlan:
    files: tuple[ArtifactEntry, ...]
    excluded: tuple[str, ...]
    pending_decision: tuple[str, ...]


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def is_denied(rel: str) -> bool:
    """True when a workspace-relative POSIX path is inside the denylist."""
    for entry in DENYLIST:
        if entry.endswith("/"):
            base = entry[:-1]
            if rel == base or rel.startswith(entry):
                return True
        elif rel == entry:
            return True
    return False


def _iter_entry_files(root: Path, entry: str):
    target = root / entry
    if target.is_file():
        yield target
        return
    if not target.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(target, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [
            name
            for name in sorted(dirnames)
            if name != "__pycache__"
            and not is_denied(_relative(root, current / name) + "/")
        ]
        for name in sorted(filenames):
            path = current / name
            if path.suffix == ".pyc":
                continue
            if is_denied(_relative(root, path)):
                continue
            yield path


def plan(root: Path | str | None = None) -> ReleasePlan:
    """Return the would-be artifact file list. Reads only; writes nothing."""
    base = Path(root or ROOT).resolve()
    entries: dict[str, ArtifactEntry] = {}
    for entry in WHITELIST:
        for path in _iter_entry_files(base, entry):
            rel = _relative(base, path)
            if rel in entries:
                continue
            entries[rel] = ArtifactEntry(
                path=rel,
                bytes=path.stat().st_size,
                sha256=file_sha256(path),
            )
    files = tuple(entries[key] for key in sorted(entries))
    excluded = tuple(
        entry for entry in DENYLIST if (base / entry.rstrip("/")).exists()
    )
    pending = tuple(
        entry for entry in PENDING_DECISION if (base / entry.rstrip("/")).exists()
    )
    return ReleasePlan(files=files, excluded=excluded, pending_decision=pending)


def validate(root: Path | str | None = None) -> list[str]:
    """Return invariant violations for the consumer Release specification."""
    base = Path(root or ROOT).resolve()
    problems: list[str] = []

    overlap = sorted(set(WHITELIST) & set(DENYLIST))
    if overlap:
        problems.append(f"whitelist and denylist overlap: {overlap}")

    for entry in WHITELIST:
        if not (base / entry.rstrip("/")).exists():
            problems.append(f"whitelisted path does not exist: {entry}")

    current = plan(base)
    excluded = set(current.excluded)
    for artifact in current.files:
        if is_denied(artifact.path):
            problems.append(f"denylisted path present in plan: {artifact.path}")

    for entry in DENYLIST:
        if (base / entry.rstrip("/")).exists() and entry not in excluded:
            problems.append(
                f"existing denylisted path not reported as excluded: {entry}"
            )

    return problems


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Consumer Release artifact specification (spec only; writes nothing)."
    )
    parser.add_argument("--root", default=str(ROOT), help="workspace root to inspect")
    parser.add_argument(
        "--check",
        action="store_true",
        help="print the summary and exit non-zero on an invariant violation",
    )
    parser.add_argument(
        "--list", action="store_true", help="also print every planned artifact file"
    )
    args = parser.parse_args(argv)

    base = Path(args.root).resolve()
    current = plan(base)
    total = sum(artifact.bytes for artifact in current.files)
    print(f"consumer release spec: MCP server {MCP_SERVER_VERSION}")
    print(f"root: {base}")
    print(f"whitelist entries: {len(WHITELIST)}")
    print(f"artifact files: {len(current.files)}; bytes: {total}")
    print(f"denylist entries: {len(DENYLIST)}; existing excluded here: {len(current.excluded)}")
    print(f"pending human decision (not planned): {list(current.pending_decision)}")
    if args.list:
        for artifact in current.files:
            print(f"{artifact.sha256}  {artifact.bytes:>9}  {artifact.path}")

    problems = validate(base)
    if problems:
        print("INVARIANT VIOLATIONS:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        "invariants OK: whitelist/denylist disjoint; no denylisted path planned; "
        "every whitelisted path exists; every existing denylisted path reported excluded"
    )
    if not args.check:
        print("(run with --check to make invariant violations fail the process)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
