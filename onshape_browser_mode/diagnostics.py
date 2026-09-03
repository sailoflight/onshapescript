from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs" / "fs_diagnostics"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _capture_directory(output_root: Path, captured_at: str, source_sha256: str) -> tuple[str, Path]:
    stamp = re.sub(r"[^0-9A-Za-z]+", "", captured_at)
    base_id = f"{stamp}-{source_sha256[:12]}"
    root = output_root.resolve()
    for suffix in range(100):
        capture_id = base_id if suffix == 0 else f"{base_id}-{suffix}"
        destination = root / capture_id
        try:
            destination.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return capture_id, destination
    raise FileExistsError("could not allocate a unique FeatureScript diagnostic capture directory")


def save_featurescript_diagnostic(
    *,
    source: str,
    compile_status: dict[str, Any],
    page_url: str,
    phase: str,
    output_root: Path = OUTPUT_ROOT,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """Persist one browser-observed FeatureScript source and compile result."""
    if not isinstance(source, str):
        raise TypeError("source must be a string")
    if not isinstance(compile_status, dict):
        raise TypeError("compile_status must be an object")
    if not isinstance(page_url, str):
        raise TypeError("page_url must be a string")
    if not isinstance(phase, str) or not phase.strip():
        raise ValueError("phase must be a non-empty string")

    observed_at = captured_at or datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    source_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    capture_id, destination = _capture_directory(output_root, observed_at, source_sha256)
    source_path = destination / "featurescript.fs"
    result_path = destination / "compile-result.json"
    manifest_path = destination / "manifest.json"

    manifest = {
        "schemaVersion": 1,
        "artifactType": "featurescript-compile-diagnostic",
        "captureId": capture_id,
        "capturedAt": observed_at,
        "phase": phase.strip(),
        "pageUrl": page_url,
        "sourceFile": source_path.name,
        "compileResultFile": result_path.name,
        "sourceSha256": source_sha256,
        "sourceLength": len(source),
        "lineCount": source.count("\n") + 1,
    }
    _atomic_write_text(source_path, source)
    _atomic_write_text(
        result_path,
        json.dumps(compile_status, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write_text(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return {
        "captured": True,
        "captureId": capture_id,
        "captureDirectory": str(destination),
        "sourcePath": str(source_path),
        "compileResultPath": str(result_path),
        "manifestPath": str(manifest_path),
        "sourceSha256": source_sha256,
        "sourceLength": len(source),
        "lineCount": source.count("\n") + 1,
    }
