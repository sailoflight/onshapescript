#!/usr/bin/env python3
"""Build the consumer Release artifact for this checkout.

Decisions this tool implements (owner direction 2026-09-25, "prepare the
release"; see `docs/operations/RELEASE.md` for the reasoning and the items that
stay open):

* **format: zip** -- the consumer is native Windows with no Git, APG or WSL, so
  the artifact must be extractable and runnable with what Windows already has.
  A wheel would need pip and would not carry the offline docs tree; zipapp and
  PyInstaller add a build toolchain and hide the file list the manifest exists to
  publish.
* **contents: exactly `consumer_release_spec.plan()`** -- one source of truth.
  This tool never invents a file list; if the plan violates its own invariants,
  nothing is written.
* **no wrapper directory** -- the archive root IS the install root, so
  "extract into an empty directory" is the whole install. Upgrade into a new
  directory and carry the denylisted state paths over; `release-manifest.json`
  names them under `excludedPaths`.
* **unsigned** -- code signing needs a certificate and stays an open decision.
  Integrity is the SHA-256 sidecar, verified before install.

The build is reproducible: fixed zip entry timestamps, sorted entry order, fixed
compression level, and the same tree yields byte-identical output. Nothing is
downloaded, and no network is touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dev.tools import consumer_release_spec as spec  # noqa: E402

#: Fixed timestamp for every entry, so the archive is reproducible. ZIP cannot
#: store anything before 1980.
_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
#: Fixed external attributes: regular file, 0644.
_ZIP_EXTERNAL_ATTR = 0o644 << 16

RELEASE_NOTES_NAME = "RELEASE-NOTES.md"
#: The archive's own digest lives OUTSIDE it, next to the artifact.
OUTER_CHECKSUM_SUFFIX = ".sha256"


def revision(root: Path | None = None) -> str:
    """Release revision: the source revision this artifact was built from."""
    import subprocess

    base = Path(root or ROOT)
    try:
        completed = subprocess.run(
            ["git", "-C", str(base), "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except Exception:
        return "unknown"
    value = completed.stdout.strip()
    if not value:
        return "unknown"
    try:
        dirty = subprocess.run(
            ["git", "-C", str(base), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()
    except Exception:
        dirty = ""
    return f"{value}-dirty" if dirty else value


def artifact_name(version: str, rev: str) -> str:
    return f"onshapescript-mcp-{version}-{rev}.zip"


def release_notes(
    *, version: str, governance: str, rev: str, plan: spec.ReleasePlan, artifact: str
) -> str:
    excluded = "\n".join(f"- `{entry}`" for entry in plan.excluded) or "- （无）"
    return f"""# Onshape MCP consumer release {version}-{rev}

Artifact: `{artifact}`
MCP server version: `{version}` (never borrows the governance version `{governance}`)
Built from source revision: `{rev}`
Build: unsigned. Verify `{artifact}{OUTER_CHECKSUM_SUFFIX}` before installing.

## What this artifact is

An extract-and-run tree for a native Windows consumer: no Git, no APG and no WSL
are needed, and the only Python entry point is the ordinary stdio MCP server
(`python -m mcp_main.win.mcp`). Live Onshape REST stays off unless
`LIVE_API_ENABLED` is explicitly set.

## Contents

| item | value |
|---|---|
| files | {len(plan.files)} |
| uncompressed bytes | {sum(entry.bytes for entry in plan.files)} |
| `release-manifest.json` | one entry per file: path, bytes, SHA-256 |
| `SHA256SUMS` | `sha256sum -c` input covering exactly the files above |

## Install

1. Create an empty directory; the archive root IS the install root.
2. Verify the artifact digest, then extract.
3. Follow `docs/usage/MCP_CONSUMER.md` to register the server with DSH.

## Upgrade / rollback

Extract the new release into a **new** directory, carry the preserved state
paths below over from the old install, and switch the DSH registration. Rollback
is switching it back. Neither step deletes state by default.

## Preserved state (NOT in this artifact, never deleted by upgrade)

{excluded}

## Open items (unchanged by this artifact)

- Publication location and distribution channel.
- Code signing (this artifact is unsigned).
- The native-Windows acceptance run on a clean consumer environment.
"""


def build(
    *,
    root: Path | None = None,
    destination: Path,
    version: str | None = None,
    rev: str | None = None,
) -> dict[str, Path]:
    """Build the artifact and return the written paths.

    Refuses a destination inside the checkout (it would change the tree the plan
    was computed from) and refuses to write anything when an invariant fails.
    """
    base = Path(root or ROOT).resolve()
    destination = Path(destination).resolve()
    if destination == base or base in destination.parents:
        raise ValueError(
            "refusing to build inside the checkout: the artifact would change the "
            "tree its own manifest describes"
        )
    problems = spec.validate(base)
    if problems:
        raise ValueError(
            "refusing to build: the release spec has invariant violations: "
            + "; ".join(problems)
        )

    current = spec.plan(base)
    server_version = version or spec.MCP_SERVER_VERSION
    source_revision = rev or revision(base)
    name = artifact_name(server_version, source_revision)
    destination.mkdir(parents=True, exist_ok=True)
    artifact_path = destination / name

    manifest = {
        "artifactStatus": "built",
        "artifactFormat": "zip",
        "artifactName": name,
        "mcpServerVersion": server_version,
        "governanceRelease": spec.GOVERNANCE_RELEASE,
        "sourceRevision": source_revision,
        "signed": False,
        "fileCount": len(current.files),
        "totalBytes": sum(entry.bytes for entry in current.files),
        "checksumSidecar": spec.CHECKSUM_SIDECAR_NAME,
        "checksumSidecarVerification": (
            f"extract, then: cd <install-dir> && sha256sum -c "
            f"{spec.CHECKSUM_SIDECAR_NAME}"
        ),
        "excludedPaths": list(current.excluded),
        "pendingDecision": list(current.pending_decision),
        "files": [
            {"path": entry.path, "bytes": entry.bytes, "sha256": entry.sha256}
            for entry in current.files
        ],
    }

    def _write(archive: zipfile.ZipFile, entry_name: str, payload: bytes) -> None:
        info = zipfile.ZipInfo(entry_name, date_time=_ZIP_DATE_TIME)
        info.external_attr = _ZIP_EXTERNAL_ATTR
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, payload)

    with zipfile.ZipFile(artifact_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in current.files:
            _write(archive, entry.path, (base / entry.path).read_bytes())
        # Written last and outside the checksum sidecar: the manifest describes
        # the tree, and the sidecar must cover exactly the shipped files.
        _write(archive, spec.CHECKSUM_SIDECAR_NAME, _checksums(current))
        _write(
            archive,
            spec.MANIFEST_NAME,
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        )
        _write(
            archive,
            RELEASE_NOTES_NAME,
            release_notes(
                version=server_version,
                governance=spec.GOVERNANCE_RELEASE,
                rev=source_revision,
                plan=current,
                artifact=name,
            ).encode(),
        )

    outer = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    checksum_path = destination / (name + OUTER_CHECKSUM_SUFFIX)
    checksum_path.write_text(f"{outer}  {name}\n", encoding="utf-8")
    return {
        "artifact": artifact_path,
        "outerChecksum": checksum_path,
        "manifest": destination / spec.MANIFEST_NAME,
    }


def _checksums(current: spec.ReleasePlan) -> bytes:
    return "".join(
        f"{entry.sha256}  {entry.path}\n" for entry in current.files
    ).encode()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the consumer Release artifact (zip) for this checkout."
    )
    parser.add_argument("--root", default=str(ROOT), help="workspace root to package")
    parser.add_argument(
        "--out",
        required=True,
        help="destination directory OUTSIDE the checkout (it is created if absent)",
    )
    parser.add_argument(
        "--version", default=None, help=f"MCP server version (default {spec.MCP_SERVER_VERSION})"
    )
    parser.add_argument(
        "--revision", default=None, help="release revision (default: git short HEAD)"
    )
    args = parser.parse_args(argv)

    try:
        written = build(
            root=Path(args.root),
            destination=Path(args.out),
            version=args.version,
            rev=args.revision,
        )
    except ValueError as exc:
        print(f"refused: {exc}")
        return 1
    print(f"wrote {written['artifact']} ({written['artifact'].stat().st_size} bytes)")
    print(f"wrote {written['outerChecksum']}")
    print("unsigned; verify the sidecar before installing")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
