"""The refusing half of the print-fit interface: what a consumer checks before it trusts a handoff.

A shared contract that cannot say "no" is a convention, not a boundary. This module implements the
consumer side of `docs/roadmap/PRINT_FIT_INTERFACE_DRAFT.md` §4: it reads a handoff manifest and either
accepts its print basis or refuses it, naming the rule, the place, and what the producer must supply.

It computes no geometry and reads no kernel. Every rule below is a rule the draft states and the producer
either satisfies structurally (the `print` block and the per-piece `at` it now emits) or does not:

* rule 1 — a direction-derived reading without the basis it was taken at is not comparable with anything;
* rule 2 — no reading on a mesh whose `orientation.applicable` is false (the vacuously-consistent gate);
* rule 3 — the acceptance gate belongs to the consumer: a producer-stamped envelope/verdict is refused;
* rule 4 — a thickness reading claimed while the producer declares no analyzer is a contradiction;
* rule 5 — a caller printing in another build direction must re-take the readings, not reuse them.

The guard deliberately returns the READINGS and never a verdict: "printable" is the caller's comparison
against its own envelope, and this module has no envelope of its own.
"""

from __future__ import annotations

from typing import Any

#: The fields that are functions of the face normals (print-fit draft §3/§4 rule 1).
DIRECTION_DERIVED = (
    "overhangAreaMm2",
    "overhangTriangleCount",
    "overhangTriangleRatio",
    "bedContactAreaMm2",
    "bedContactTriangleCount",
    "bedContactTriangleRatio",
)


def _refusal(rule: int, where: str, problem: str, required: str) -> dict[str, str]:
    return {"rule": f"print-fit §4 rule {rule}", "where": where, "problem": problem,
            "required_fix": required}


def check_print_basis(
    manifest: dict[str, Any],
    *,
    build_direction: list[float] | None = None,
    require_at: bool = True,
) -> dict[str, Any]:
    """Check a handoff manifest's print basis. Returns ``{"ok": bool, "refusals": [...], "basis": {...}}``.

    ``build_direction`` is the direction the CALLER intends to print in. When it is given and differs from
    the artifact's declared one, the readings are stale for that purpose and the guard refuses them rather
    than letting them be reused (rule 5).
    """
    declaration = manifest.get("declaration") or {}
    block = declaration.get("print") or {}
    parts = ((declaration.get("geometry") or {}).get("parts")) or []
    refusals: list[dict[str, str]] = []

    if not block:
        refusals.append(_refusal(
            1, "declaration.print", "the manifest declares no print basis at all",
            "publish build_direction, threshold_deg and reference_point with the readings"))
    declared_direction = [float(v) for v in (block.get("build_direction") or [])]
    declared_threshold = block.get("threshold_deg")

    # --- rule 3: the gate this plane does not own
    envelope = block.get("envelope") or {}
    owner = envelope.get("declared_by")
    if owner not in (None, "consumer"):
        refusals.append(_refusal(
            3, "declaration.print.envelope", f"the envelope is declared by {owner!r}",
            "an envelope is machine state: only the consumer declares it, and no producer stamps a "
            "printability verdict"))
    verdict = block.get("printable")
    if verdict is not None:
        refusals.append(_refusal(
            3, "declaration.print.printable", "the producer stamped a printability verdict",
            "return the readings and let the consumer compare them against its own envelope"))

    # --- rule 1 + rule 2, per piece
    if require_at:
        for piece in parts:
            mesh = piece.get("mesh") or {}
            index = piece.get("index")
            at = mesh.get("at")
            has_reading = any(mesh.get(field) is not None for field in DIRECTION_DERIVED)
            if not at:
                # Checked even when every reading is null, deliberately: a null reading must still say
                # WHERE it would have been taken, or a consumer cannot tell "not applicable" from
                # "taken somewhere else".
                refusals.append(_refusal(
                    1, f"parts[{index}].mesh.at",
                    "direction-derived readings carry no basis",
                    "publish the build direction, threshold and reference point beside them"))
                continue
            if [float(v) for v in (at.get("build_direction") or [])] != declared_direction or \
                    at.get("threshold_deg") != declared_threshold:
                refusals.append(_refusal(
                    1, f"parts[{index}].mesh.at",
                    "the per-piece basis contradicts the declaration-level one",
                    "one basis per artifact: make the per-piece `at` and declaration.print agree"))
            if mesh.get("orientation", {}).get("applicable") is False and has_reading:
                refusals.append(_refusal(
                    2, f"parts[{index}].mesh",
                    "a direction-derived reading is published on a mesh whose winding verdict is not "
                    "applicable (edge graph not closed)",
                    "null those readings and say why, as the vacuously-consistent rule requires"))

    # --- rule 4: a thickness reading without an analyzer
    min_wall = block.get("min_wall") or {}
    if min_wall.get("value_mm") is not None and min_wall.get("grade") == "unknown":
        refusals.append(_refusal(
            4, "declaration.print.min_wall",
            "a thickness value is claimed while its own grade says `unknown`",
            "declare the reading absent with a reason, or ship the analyzer that produced it"))

    # --- rule 5: a caller printing in another direction cannot reuse these readings
    if build_direction is not None:
        wanted = [float(v) for v in build_direction]
        if wanted != declared_direction:
            refusals.append(_refusal(
                5, "declaration.print.build_direction",
                f"the caller intends {wanted} while the readings were taken at {declared_direction}",
                "re-take the direction-derived readings at the caller's build direction; they are "
                "functions of it and must not be reused across a re-orientation"))

    return {
        "ok": not refusals,
        "refusals": refusals,
        "basis": {"build_direction": declared_direction, "threshold_deg": declared_threshold,
                  "reference_point": block.get("reference_point"),
                  "envelope_declared_by": owner},
        "readings": {field: mesh_field(parts, field) for field in DIRECTION_DERIVED},
        "note": ("this guard returns readings, never a verdict: printability is the caller's comparison "
                 "against an envelope the caller declares"),
    }


def mesh_field(parts: list[dict[str, Any]], field: str) -> dict[str, Any]:
    """The per-piece values of one direction-derived field, so a consumer can see what it is reusing."""
    values = {}
    for piece in parts:
        mesh = piece.get("mesh") or {}
        values[str(piece.get("index"))] = mesh.get(field)
    return values
