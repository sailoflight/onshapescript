#!/usr/bin/env python3
"""Consumer Release artifact specification: whitelist, denylist, plan, invariants.

This module is a SPEC, not a packager. It never writes files, never creates an
archive, and never copies anything. ``plan()`` returns the file list that a
future packager would be allowed to emit; ``validate()`` reports invariant
violations. The release procedures live in ``docs/operations/RELEASE.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
    # DECIDED (owner, 2026-09-25): fdm_analysis IS part of the artifact, shipped
    # with the server. It is not an outside concern -- the geometry and FDM
    # capabilities are exposed as MCP tools (onshape_geometry_status,
    # onshape_build_geometry_package, ...), so the package belongs to this tool
    # set. What was adjusted instead of the file list is the DEPENDENCY SHAPE:
    #   * `mcp_main/win/mcp/server.py` no longer imports the geometry/step_export
    #     modules at module scope (they reach fdm_analysis), so importing the
    #     server no longer drags the package in at all; and
    #   * `fdm_analysis/__init__.py` re-exports lazily (PEP 562), so a caller that
    #     only needs `file_sha256` from `.contracts` -- as the Onshape STEP export
    #     does -- loads 1 submodule instead of 16 (slicers/Bambu included).
    "fdm_analysis/",
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
    # Native/original Onshape documentation. DECIDED (owner, 2026-09-25): it IS
    # part of the artifact. Measured 10,258,423 bytes (~9.8 MiB) -- by far the
    # largest entry -- and it is the offline fallback the `fs_library_source` /
    # "raw source last" read order depends on, so dropping it would silently
    # degrade an advertised offline capability.
    "onshape_docs/reference/raw/",
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
#:
#: EMPTY since 2026-09-25. ``fdm_analysis/`` was the last open item and is now
#: whitelisted (see the comment there): the owner settled it as "this tool ships
#: together with the rest", so the import-graph work became a dependency-SHAPE
#: adjustment (lazy server imports + lazy package re-exports) instead of a
#: packaging split. Keep the constant so ``--check`` keeps reporting the list and
#: a future genuinely-open path has one documented home.
PENDING_DECISION: tuple[str, ...] = ()


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


def write_manifest(base: Path, destination: Path) -> dict[str, Path]:
    """Materialise this checkout's release manifest and checksum sidecar.

    Spec-only by construction, and it says so in the manifest: it writes the file
    list, sizes and SHA-256 digests plus a ``sha256sum -c`` compatible sidecar.
    It does NOT build, compress, sign, or publish anything, and the whitelist and
    dependency constraints stay in this module.

    The destination must be OUTSIDE the checkout: a file written into the tree
    would change the very tree the plan was computed from.
    """
    base = Path(base).resolve()
    destination = Path(destination).resolve()
    if destination == base or base in destination.parents:
        raise ValueError(
            "refusing to write the manifest inside the checkout: it would change "
            "the tree this plan describes"
        )
    current = plan(base)
    rows = [{"path": a.path, "bytes": a.bytes, "sha256": a.sha256} for a in current.files]
    digest = hashlib.sha256()
    for row in rows:
        digest.update(f"{row['sha256']}  {row['bytes']:>12}  {row['path']}\n".encode())
    manifest = {
        # NOT a built artifact. Anyone reading this file should be able to tell
        # that no packaging pipeline ran.
        "artifactStatus": "spec-only",
        "artifactFormat": None,
        "mcpServerVersion": MCP_SERVER_VERSION,
        "governanceRelease": GOVERNANCE_RELEASE,
        "fileCount": len(rows),
        "totalBytes": sum(row["bytes"] for row in rows),
        "planSha256": digest.hexdigest(),
        "planSha256Means": (
            "digest over the ordered (sha256, bytes, path) rows; two runs that "
            "disagree describe different file sets"
        ),
        "excludedPaths": list(current.excluded),
        "pendingDecision": list(current.pending_decision),
        "checksumSidecar": CHECKSUM_SIDECAR_NAME,
        "checksumSidecarVerification": (
            f"cd {base} && sha256sum -c <path-to>/{CHECKSUM_SIDECAR_NAME} "
            "(every listed path is relative to the checkout root)"
        ),
        "files": rows,
    }
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksum_path = destination / CHECKSUM_SIDECAR_NAME
    checksum_path.write_text(
        "".join(f"{a.sha256}  {a.path}\n" for a in current.files), encoding="utf-8"
    )
    return {"manifest": manifest_path, "checksums": checksum_path}


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
    parser.add_argument(
        "--emit",
        metavar="DIR",
        help=(
            "write release-manifest.json and a sha256sum -c compatible SHA256SUMS for "
            "this checkout into DIR (spec-only: no build, no compression, no signature); "
            "refused if DIR is inside the checkout, and skipped when an invariant fails"
        ),
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
    if args.emit:
        # Only after the invariants hold: never emit a manifest for a plan that
        # violates the spec's own rules.
        try:
            written = write_manifest(base, Path(args.emit))
        except ValueError as exc:
            print(f"refused: {exc}")
            return 1
        print(f"wrote {written['manifest']}")
        print(f"wrote {written['checksums']}")
        print(
            "spec-only: no artifact was built, compressed, signed or published; "
            "the manifest says artifactStatus=spec-only"
        )
    if not args.check:
        print("(run with --check to make invariant violations fail the process)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
