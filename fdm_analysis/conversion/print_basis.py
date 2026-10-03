"""The refusing half of the print-fit interface: what a consumer checks before it trusts a handoff.

A shared contract that cannot say "no" is a convention, not a boundary. This module implements the
consumer side of `docs/roadmap/PRINT_FIT_INTERFACE_DRAFT.md` §4: it reads a handoff manifest and either
accepts its print basis or refuses it, naming the rule, the place, and what the producer must supply.

It computes no geometry and reads no kernel. Every rule below is a rule the draft states and the producer
either satisfies structurally (the `print` block and the per-piece `at` it now emits) or does not:

* rule 1 — a direction-derived reading without the basis it was taken at is not comparable with anything;
* rule 2 — no reading on a mesh whose `orientation.applicable` is false (the vacuously-consistent gate);
* rule 3 — the acceptance gate belongs to the consumer: a producer-stamped envelope/verdict is refused;
* rule 4 — a thickness reading claimed while the producer declares no analyzer is a contradiction,
  and an `unknown` grade without a reason is a silent gap (MeshQ 182 variant F);
* rule 1 also owns the threshold's RANGE (``0 < threshold_deg <= 180``): outside it an overhang reading has
  no meaning, and a guard that only asks for presence and finiteness admits `0`, `181`, `1e9` and `-45`
  (measured against a peer that already enforces the range — MeshQ 189 §3);
* and, across all of them, **an absent or null field must be as loud as a false one** — a rule that only
  fires when a field is present is not a gate (four of MeshQ's ten adversarial variants passed the first
  version of this guard exactly that way);
* rule 5 — a caller printing in another build direction must re-take the readings, not reuse them.

Two obligations that only show up when values are wrong in KIND rather than absent (MeshQ 187): a required
boolean must be **literally** `true` (`0`, `"false"` and `True` are not interchangeable at a gate — treating
them as such inverts the rule), and a raw JSON value must be validated **before** it is converted, because
validating after `float()` checks only the floats the validator itself produced.

The guard deliberately returns the READINGS and never a verdict: "printable" is the caller's comparison
against its own envelope, and this module has no envelope of its own.
"""

from __future__ import annotations

import math
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


#: What a "number" may be, at the JSON level: a bool is not a number even though Python lets it be one,
#: and a non-finite value is not a direction or a threshold.
_NUMBERS = (int, float)


def _direction(raw: Any) -> list[float] | None:
    """Return three finite components from a RAW JSON value, or ``None``.

    Validate first, convert second. The earlier version converted with ``float(v)`` and then ran an
    ``isinstance`` test over the conversion's own output, so that half could never fail: ``["0","0","1"]``
    and ``[0,0,True]`` both passed, and nothing ever checked finiteness even though the message claimed to
    (MeshQ 187, which also reported that its NaN probe was itself unclean — so this validator is tested for
    NaN, inf, bools and strings rather than trusted for them).
    """
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        return None
    converted: list[float] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, _NUMBERS):
            return None
        number = float(value)
        if not math.isfinite(number):
            return None
        converted.append(number)
    return converted


def _finite_number(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, _NUMBERS):
        return None
    number = float(raw)
    return number if math.isfinite(number) else None


def _refusal(rule: int, where: str, problem: str, required: str) -> dict[str, str]:
    return {"rule": f"print-fit §4 rule {rule}", "where": where, "problem": problem,
            "required_fix": required}


def check_print_basis(
    manifest: dict[str, Any],
    *,
    build_direction: list[float] | None = None,
    require_at: bool = True,
) -> dict[str, Any]:
    """Check a handoff manifest's print basis.

    Returns ``{"ok": bool, "complete": bool, "rulesRun": [...], "rulesNotRun": [...], "refusals": [...],
    "basis": {...}}``.

    ``build_direction`` is the direction the CALLER intends to print in. When it is given and differs from
    the artifact's declared one, the readings are stale for that purpose and the guard refuses them rather
    than letting them be reused (rule 5).

    **``ok`` alone is not the verdict; ``complete and ok`` is.** A rule that never ran cannot refuse, so a
    partial run would otherwise look exactly like a full pass -- and a reader treats `ok: true` as a green
    light. When the caller does not declare the direction it intends to print in, rule 5 does not run, so
    ``rulesNotRun`` names it with the reason and the way to close it, and ``complete`` is false. This is the
    same family as "an absent field must be as loud as a false one", one level up: **an unevaluated check
    must not look green.**
    """
    declaration = manifest.get("declaration") or {}
    block = declaration.get("print") or {}
    parts = ((declaration.get("geometry") or {}).get("parts")) or []
    refusals: list[dict[str, str]] = []
    rules_run: set[int] = set()
    rules_not_run: list[dict[str, Any]] = []

    if not block:
        refusals.append(_refusal(
            1, "declaration.print", "the manifest declares no print basis at all",
            "publish build_direction, threshold_deg and reference_point with the readings"))
    rules_run.add(1)  # the declaration-level basis is examined on every call
    raw_direction = block.get("build_direction")
    declared_direction = _direction(raw_direction)
    declared_threshold = _finite_number(block.get("threshold_deg"))

    # A rule that only says "what to do when a field says something" is silent when the field is absent,
    # and absence is the more dangerous case because nobody reads a field that is not there (MeshQ 182:
    # four of ten adversarial variants passed this guard exactly this way). So the basis must be COMPLETE:
    # a direction needs three finite numbers, the threshold needs a value, and the reference point is not
    # decoration -- it decides whether an orientation defect is observable at all (the blindness rule).
    if declared_direction is None:
        refusals.append(_refusal(
            1, "declaration.print.build_direction",
            f"the build direction is {raw_direction!r}, which is not three finite JSON numbers",
            "publish the direction the readings were taken at as three finite numbers: a string, a boolean "
            "or a non-finite component is not a direction, and the raw value is validated before conversion"))
        declared_direction = []
    if declared_threshold is None:
        refusals.append(_refusal(
            1, "declaration.print.threshold_deg",
            f"the overhang threshold is {block.get('threshold_deg')!r}, which is absent or not finite",
            "an overhang reading is a function of its threshold; publish the finite number it used"))
    elif not 0.0 < declared_threshold <= 180.0:
        # Measured against a peer that DOES enforce this range (MeshQ 189 §3): `0`, `181`, `1e9` and `-45`
        # all passed the first version of this guard, which only asked that the threshold be present and
        # finite. An overhang threshold outside (0, 180] is not a stricter or looser reading -- it is a
        # reading with no meaning, and "an empty reading looks like a healthy certificate".
        refusals.append(_refusal(
            1, "declaration.print.threshold_deg",
            f"the overhang threshold {declared_threshold!r} is outside the only range in which an overhang "
            "reading means anything: 0 < threshold_deg <= 180",
            "publish the angle the reading was actually taken at, in degrees from the build direction"))
    if block.get("reference_point") in (None, ""):
        refusals.append(_refusal(
            1, "declaration.print.reference_point",
            "the reference point is absent",
            "publish it: the reference point decides whether a direction defect is observable at all, so "
            "a null one is an incomplete basis rather than a neutral default"))

    # --- rule 3: the gate this plane does not own
    rules_run.add(3)
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
        rules_run.add(2)
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
            piece_direction = _direction(at.get("build_direction"))
            piece_threshold = _finite_number(at.get("threshold_deg"))
            if piece_threshold is not None and not 0.0 < piece_threshold <= 180.0:
                refusals.append(_refusal(
                    1, f"parts[{index}].mesh.at",
                    f"the per-piece overhang threshold {piece_threshold!r} is outside 0 < threshold_deg "
                    "<= 180",
                    "one range for one kind of reading: make the per-piece basis a real angle too"))
                piece_threshold = None
            if piece_direction is None or piece_threshold is None:
                refusals.append(_refusal(
                    1, f"parts[{index}].mesh.at",
                    f"the per-piece basis is incomplete or not finite ({at.get('build_direction')!r}, "
                    f"{at.get('threshold_deg')!r})",
                    "publish the same three-finite-number direction and finite threshold the declaration "
                    "publishes, so a consumer can tell a real basis from a plausible-looking one"))
            elif piece_direction != declared_direction or piece_threshold != declared_threshold or \
                    at.get("reference_point") != block.get("reference_point"):
                refusals.append(_refusal(
                    1, f"parts[{index}].mesh.at",
                    "the per-piece basis contradicts the declaration-level one (direction, threshold or "
                    "reference point)",
                    "one basis per artifact: make the per-piece `at` and declaration.print agree"))
            # Rule 2, and its absent-field half: a direction-derived reading is only meaningful when the
            # winding verdict is EXPLICITLY applicable and consistent. `is False` alone let two variants
            # through -- deleting `orientation` entirely, and setting `applicable` to null -- because
            # "undeclared" was being read as "nothing to complain about".
            orientation = mesh.get("orientation")
            if has_reading:
                applicable_value = (orientation or {}).get("applicable")
                consistent_value = (orientation or {}).get("consistent")
                if applicable_value is True and consistent_value is True:
                    pass
                elif not orientation or applicable_value is None or consistent_value is None:
                    refusals.append(_refusal(
                        2, f"parts[{index}].mesh.orientation",
                        "direction-derived readings are published with no (or an undeclared) orientation "
                        "verdict, so nothing says the winding check was even applicable",
                        "publish `applicable` and `consistent` explicitly; undeclared is not OK, and a "
                        "deleted field must be as loud as a false one"))
                elif applicable_value is False or consistent_value is False:
                    # The producer said so honestly; the fix is its own, and the reason is named as such
                    # rather than as a type problem.
                    refusals.append(_refusal(
                        2, f"parts[{index}].mesh",
                        "a direction-derived reading is published on a mesh whose winding verdict is "
                        "false (edge graph not closed), the vacuously-consistent case",
                        "null those readings and say why, as the vacuously-consistent rule requires"))
                else:
                    refusals.append(_refusal(
                        2, f"parts[{index}].mesh.orientation",
                        f"the winding verdict is not literally true ({applicable_value!r}/"
                        f"{consistent_value!r}), so a direction-derived reading has no applicable basis",
                        "a producer that means 'not applicable' must say false; a gate that accepts a "
                        "truthy substitute (0, or the string 'false') is not a gate, because that is how "
                        "the rule gets inverted by a type"))

    # --- rule 4: a thickness reading without an analyzer
    rules_run.add(4)
    min_wall = block.get("min_wall") or {}
    if min_wall and min_wall.get("grade") == "unknown" and not str(min_wall.get("reason") or "").strip():
        refusals.append(_refusal(
            4, "declaration.print.min_wall",
            "the thickness reading is declared unknown with no reason",
            "an undeclared skip reads as 'fine': state why the reading is absent"))
    if min_wall.get("value_mm") is not None and min_wall.get("grade") == "unknown":
        refusals.append(_refusal(
            4, "declaration.print.min_wall",
            "a thickness value is claimed while its own grade says `unknown`",
            "declare the reading absent with a reason, or ship the analyzer that produced it"))

    # --- rule 5: a caller printing in another direction cannot reuse these readings
    if build_direction is None:
        rules_not_run.append({
            "rule": 5,
            "what": "the caller's own build direction was not compared with the artifact's",
            "why": "this gate cannot know the direction the caller intends to print in, and a reading taken "
                   "at another direction must not be reused silently",
            "how_to_close": "call with build_direction=[x, y, z] (the direction you actually intend), or "
                            "accept a declaration-only check explicitly",
        })
    else:
        rules_run.add(5)
        wanted = [float(v) for v in build_direction]
        if wanted != declared_direction:
            refusals.append(_refusal(
                5, "declaration.print.build_direction",
                f"the caller intends {wanted} while the readings were taken at {declared_direction}",
                "re-take the direction-derived readings at the caller's build direction; they are "
                "functions of it and must not be reused across a re-orientation"))

    complete = not rules_not_run
    return {
        "ok": not refusals,
        # Named so a caller cannot read `ok` as more than it is: a rule that did not run could not refuse.
        "complete": complete,
        "rulesRun": sorted(rules_run),
        "rulesNotRun": rules_not_run,
        "refusals": refusals,
        "basis": {"build_direction": declared_direction, "threshold_deg": declared_threshold,
                  "reference_point": block.get("reference_point"),
                  "envelope_declared_by": owner},
        "readings": {field: mesh_field(parts, field) for field in DIRECTION_DERIVED},
        "note": ("this guard returns readings, never a verdict: printability is the caller's comparison "
                 "against an envelope the caller declares"
                 + ("" if complete else
                    "; INCOMPLETE: rule(s) " + ", ".join(str(r["rule"]) for r in rules_not_run)
                    + " did not run, so `ok` is not a pass")),
    }


def mesh_field(parts: list[dict[str, Any]], field: str) -> dict[str, Any]:
    """The per-piece values of one direction-derived field, so a consumer can see what it is reusing."""
    values = {}
    for piece in parts:
        mesh = piece.get("mesh") or {}
        values[str(piece.get("index"))] = mesh.get(field)
    return values
