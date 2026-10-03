"""Extraction-only adapters: pull fields out of an artifact, never judge it.

The three planes agreed (coordinator mail 273, 2026-10-04) that **the runner is the only
authority**: each plane's adapter may only extract fields, because an adapter that judges
would give every plane its own set of criteria. The guard test asserts that an extracted
mapping contains none of :data:`JUDGEMENT_KEYS`.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

#: Keys an adapter must never produce: judgement belongs to the runner.
JUDGEMENT_KEYS = frozenset({"ok", "verdict", "pass", "grade", "refusals", "refused", "compliant"})

#: This plane's real 70-piece handoff, dropped by the three-plane session (volatile).
REAL_MANIFEST = pathlib.Path("/tmp/three-plane-drop/onshapescript-70piece-tessellation/manifest.json")


def extract_onshapescript_manifest(path: str | pathlib.Path) -> dict[str, Any]:
    """Extract fields from this plane's handoff manifest. Fields only, no verdict."""
    data: Any = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest top level is not an object")
    produced_by = data.get("produced_by") if isinstance(data.get("produced_by"), dict) else {}
    totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    return {
        "schema": data.get("schema"),
        "producer_plane": produced_by.get("plane"),
        "producer_identity": produced_by.get("identity"),
        "tool": produced_by.get("tool"),
        "produced_at": produced_by.get("at"),
        "units": data.get("units"),
        "source_kind": source.get("kind"),
        "piece_count": totals.get("pieces"),
        "contributing_pieces": totals.get("contributingPieces"),
        "triangle_count": totals.get("triangleCount"),
        "area_mm2": totals.get("areaMm2"),
    }
