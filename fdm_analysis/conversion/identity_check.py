"""The consumer's side of the identity rule: does the artifact I hold match the handoff I was given?

The counterpart of `print_basis.check_print_basis`, and the check the import leg needs before anything
downstream trusts a converted artifact. It answers with the DECLARED rules rather than an opinion: given a
handoff manifest and the readings a consumer took on the artifact it actually holds, do they agree inside
the manifest's declared tolerances -- and if not, which quantity, by how much, against which bound, and at
which piece?

Four properties, each from a measured incident in this negotiation:

* **Units are checked first, and a mismatch is a refusal rather than a scale factor.** An inch-vs-mm import
  is a silent 25.4x change; comparing numbers across it is how a wrong transfer looks correct.
* **The tolerance comes from the manifest, never from this module.** A bound that only fits the plane that
  wrote it fails correct peers (a `1e-6` area bound would adjudicate a correct reader as wrong: measured
  spread 9.8e-13 / 4.99e-7 / 3.39e-6), so the declared `equivalence_tolerance` and its
  `equivalence_tolerance_basis` are the authority -- and a manifest that declares neither cannot be checked.
* **The rule comes before the digest.** A digest comparison means something only under the same
  `identity_rule.version`; a mismatch there is a refusal to compare, not a difference to report.
* **Per-piece maximum and worst piece are always reported**, never only a total: one batch agreed to
  `1.31e-7` in aggregate while its worst piece disagreed by `3.39e-6`, a factor of 26 hidden by cancellation.

It reports per-quantity verdicts and never a single "identity: true", because a digest tells a consumer
nothing it can act on.
"""

from __future__ import annotations

from typing import Any

#: Quantities a consumer can compare, with the kind of comparison each needs. A `piece` quantity is
#: compared piece by piece (the manifest declares it per part); a `set` quantity is compared against the
#: manifest's `totals` block.
QUANTITIES = {
    "areaMm2": ("set", "relative"),
    "brepVolumeMm3": ("piece", "relative"),
    "bounds_mm": ("piece", "absolute_mm"),
}

#: How the identity rule's quantity names map onto the artifact's per-piece field names. The boundary has
#: two naming systems -- the rule speaks in identity terms (`brepVolumeMm3`) while the parts carry the
#: artifact's own keys (`brep.volume_mm3`) -- and this is the single mapping between them, declared here
#: instead of being guessed per call. `(parent, key)`, with `parent=None` for a top-level field.
PIECE_FIELD = {
    "brepVolumeMm3": ("brep", "volume_mm3"),
    "bounds_mm": (None, "bounds_mm"),
}

#: Bounded: every outside-tolerance piece is counted, but only this many are listed.
MAX_LISTED = 5


def _value(reading: Any) -> Any:
    return reading.get("value") if isinstance(reading, dict) else reading


def _bounds_max(bounds: Any) -> list[float] | None:
    if isinstance(bounds, dict):
        candidate = bounds.get("max")
        if isinstance(candidate, (list, tuple)) and len(candidate) == 3:
            return [float(v) for v in candidate]
    if isinstance(bounds, (list, tuple)) and len(bounds) == 3:
        return [float(v) for v in bounds]
    return None


def check_identity_against(
    handoff: dict[str, Any],
    *,
    units: str | None = None,
    identity_rule_version: str | None = None,
    set_readings: dict[str, Any] | None = None,
    piece_readings: list[dict[str, Any]] | None = None,
    set_signature_sha256: str | None = None,
) -> dict[str, Any]:
    """Compare consumer readings against a handoff's declared identity.

    ``set_readings`` maps a quantity (``areaMm2``) to the value the consumer measured over the whole
    artifact. ``piece_readings`` is a list of per-piece dicts carrying ``index`` and any of
    ``brepVolumeMm3``/``bounds_mm``. ``set_signature_sha256`` is the consumer's own digest, compared only
    when the canonical-form versions agree.
    """
    declaration = handoff.get("declaration") or {}
    geometry = declaration.get("geometry") or {}
    rule = geometry.get("identity_rule") or {}
    totals = handoff.get("totals") or {}
    parts = {piece.get("index"): piece for piece in (geometry.get("parts") or [])}
    refusals: list[dict[str, Any]] = []
    verdicts: dict[str, Any] = {}

    def refuse(where: str, problem: str, required: str) -> None:
        refusals.append({"where": where, "problem": problem, "required_fix": required})

    # --- units first: a unit mismatch is not a tolerance question
    declared_units = handoff.get("units")
    if units is not None and declared_units is not None and str(units) != str(declared_units):
        refuse("units", f"the consumer measured in {units!r} while the handoff declares {declared_units!r}",
               "convert with an explicit, recorded factor before comparing, or re-read in the declared "
               "unit: a 25.4x mismatch inside a tolerance comparison reads as a correct transfer")

    # --- the rule, before any digest
    declared_rule = rule.get("version")
    rule_comparable = True
    if identity_rule_version is not None:
        if declared_rule is None:
            rule_comparable = False
            refuse("declaration.geometry.identity_rule.version",
                   "the handoff declares no canonical-form version for its digest",
                   "publish the rule that produced the digest; a digest without its rule cannot be compared")
        elif str(identity_rule_version) != str(declared_rule):
            rule_comparable = False
            refuse("declaration.geometry.identity_rule.version",
                   f"the consumer's canonical form is {identity_rule_version!r} while the handoff declares "
                   f"{declared_rule!r}",
                   "re-derive under the declared rule before comparing digests: a digest that moved with a "
                   "rule change says nothing about the geometry")

    for quantity in QUANTITIES:
        verdicts[quantity] = {"status": "not_provided"}

    tolerances = rule.get("equivalence_tolerance") or {}
    basis = rule.get("equivalence_tolerance_basis") or {}
    if not tolerances:
        refuse("declaration.geometry.identity_rule.equivalence_tolerance",
               "the handoff declares no equivalence tolerance, so nothing here can be judged",
               "declare a per-quantity tolerance together with the measurement that derived it")
    for quantity in tolerances:
        if quantity not in basis:
            refuse(f"declaration.geometry.identity_rule.equivalence_tolerance_basis.{quantity}",
                   "a declared tolerance with no measurement behind it",
                   "state where the bound came from: a bound that only fits its author fails correct peers")
    vintage = rule.get("equivalence_tolerance_vintage") or {}
    if tolerances and not vintage:
        refuse("declaration.geometry.identity_rule.equivalence_tolerance_vintage",
               "a declared tolerance with no vintage: nothing says whom it was derived for, or when",
               "name the reader set, the date, the witness and when to re-derive: a bound frozen at one "
               "reader set goes stale silently and then admits the very reader it existed to exclude")

    # --- set-level quantities, against the declared totals
    for quantity, (scope, kind) in QUANTITIES.items():
        if scope != "set" or not set_readings or quantity not in set_readings:
            continue
        measured = _value(set_readings[quantity])
        declared = totals.get(quantity)
        tolerance = tolerances.get(quantity)
        if declared is None:
            verdicts[quantity] = {"status": "not_declared_by_handoff"}
            continue
        if tolerance is None:
            verdicts[quantity] = {"status": "no_declared_tolerance"}
            continue
        difference = abs(float(measured) - float(declared)) / abs(float(declared)) if declared else abs(float(measured))
        within = difference <= float(tolerance)
        verdicts[quantity] = {
            "status": "within" if within else "outside", "scope": "set",
            "consumerReading": measured, "handoffReading": declared,
            "difference": difference, "kind": kind, "declaredTolerance": tolerance,
            "declaredToleranceBasis": basis.get(quantity),
            "declaredToleranceVintage": vintage or None,
        }
        if not within:
            refuse(quantity,
                   f"the consumer reads {measured!r} where the handoff totals declare {declared!r} "
                   f"({difference:.3e} {kind} against a declared {tolerance:.3g})",
                   "attribute the difference before changing either number; outside the declared bound it "
                   "is a real difference, not noise")

    # --- per-piece quantities, against the declared parts, reporting the worst piece
    if piece_readings:
        for quantity, (scope, kind) in QUANTITIES.items():
            if scope != "piece":
                continue
            tolerance = tolerances.get(quantity)
            parent, key = PIECE_FIELD[quantity]
            declared_any = any(((part.get(parent) or {}).get(key) if parent else part.get(key)) is not None
                               for part in (geometry.get("parts") or []))
            if not declared_any:
                verdicts[quantity] = {"status": "not_declared_by_handoff"}
                continue
            if tolerance is None:
                verdicts[quantity] = {"status": "no_declared_tolerance"}
                continue
            outside: list[dict[str, Any]] = []
            worst = {"index": None, "difference": 0.0}
            compared = 0
            compared_any = True
            for reading in piece_readings:
                index = reading.get("index")
                part = parts.get(index)
                if part is None:
                    continue
                if quantity == "bounds_mm":
                    # Compare inside the family the RULE declares. A box read in one family cannot be
                    # compared with another family's bound (the cross-family method gap reaches 1.2e-5 mm),
                    # so an undeclared family is a refusal to compare rather than a guess.
                    family = rule.get("bounds_family")
                    if family != "tessellation_vertices(artifact_bytes)":
                        verdicts[quantity] = {
                            "status": "not_compared", "scope": "piece",
                            "reason": f"the handoff declares the bounds family {family!r}, which this "
                                      "checker cannot compare into",
                        }
                        compared_any = False
                        break
                    measured = _bounds_max(reading.get(quantity))
                    declared = _bounds_max(part.get("bounds_mm"))
                    if measured is None or declared is None:
                        continue
                    difference = max(abs(a - b) for a, b in zip(measured, declared))
                else:
                    parent, key = PIECE_FIELD[quantity]
                    measured = _value(reading.get(quantity))
                    declared = ((part.get(parent) or {}).get(key) if parent else part.get(key))
                    if measured is None or declared is None:
                        continue
                    difference = abs(float(measured) - float(declared)) / abs(float(declared)) if declared else 0.0
                compared += 1
                if difference > worst["difference"]:
                    worst = {"index": index, "difference": difference}
                if difference > float(tolerance):
                    outside.append({"index": index, "difference": difference,
                                    "declaredTolerance": tolerance})
            if not compared_any:
                continue
            verdicts[quantity] = {
                "status": ("outside" if outside else "within") if compared else "not_compared",
                "scope": "piece", "piecesCompared": compared,
                "piecesOutside": len(outside), "outsideListed": outside[:MAX_LISTED],
                "worstPiece": worst, "kind": kind, "declaredTolerance": tolerance,
                "declaredToleranceBasis": basis.get(quantity), "declaredToleranceVintage": vintage or None,
                "note": "reported as a per-piece maximum with its worst piece, never as an aggregate alone",
            }
            if outside:
                refuse(quantity,
                       f"{len(outside)} of {compared} pieces exceed the declared {kind} tolerance; worst is "
                       f"piece {worst['index']} at {worst['difference']:.3e} (bound {tolerance:.3g})",
                       "attribute the difference before changing either number, and compare within the "
                       "declared family (a cross-family comparison is a false-alarm generator)")

    # --- the digest last, and only when the rules agree
    digest = declaration.get("identity") or {}
    digest_verdict = {"status": "not_provided"}
    if set_signature_sha256 is not None:
        if not rule_comparable:
            digest_verdict = {"status": "not_comparable", "reason": "the canonical-form versions disagree"}
        elif digest.get("sha256") is None:
            digest_verdict = {"status": "not_declared_by_handoff"}
        else:
            same = str(set_signature_sha256) == str(digest["sha256"])
            digest_verdict = {"status": "equal" if same else "different",
                              "handoffDigest": digest["sha256"],
                              "note": ("equal is not identity and different is not a geometric difference: "
                                       "the digest is a fast path under ONE declared rule")}

    levels = {
        "outside": any(entry.get("status") == "outside" for entry in verdicts.values()),
        "compared": any(entry.get("status") in ("within", "outside") for entry in verdicts.values()),
    }
    return {
        "ok": not refusals,
        "identityLevel": ("quantities_outside_declared_tolerance" if levels["outside"] else
                          "quantities_within_declared_tolerance" if levels["compared"] else "not_comparable"),
        "verdicts": verdicts,
        "digest": digest_verdict,
        "refusals": refusals,
        "note": ("'within the declared tolerance' is not geometric identity: the tolerance is derived from "
                 "the measured spread across readers, so agreement means two readers of one artifact agree "
                 "as far as they can be expected to"),
    }
