#!/usr/bin/env python3
"""Consumer-side check of one cross-plane handoff manifest, with a closing exit code.

Lifecycle: maintained development tool (not a one-off). It exists because this repository's two consumer
guards return *dictionaries*: a caller can hold a refusal and never act on it, and a judgement computed and
dropped reads as a green light (the rule recorded as collaboration practice 16). This tool is the closing
half for this repository's own guards — it runs them over a manifest a peer handed over and **exits non-zero
on any refusal**, so a script or a human gets a verdict the shell can see.

It is entirely offline: no browser, no network, no Onshape REST quota.

What it runs (each one is an existing guard, not a second implementation):

``print``
    ``fdm_analysis/conversion/print_basis.py::check_print_basis`` — the print-fit contract's refusal rules
    (basis completeness, threshold range, winding verdict, the consumer's own envelope).
``identity``
    ``fdm_analysis/conversion/identity_check.py::check_identity_against`` — units, declared tolerance with
    its basis and vintage, rule-before-digest. This guard compares **consumer readings** against the
    handoff, so it can only speak when readings are supplied (``--readings``): without them the tool says
    ``not_provided`` rather than inventing agreement, which is the same honesty the manifest itself is
    required to show.

Exit codes: ``0`` everything checked passed **and** every rule ran; ``1`` at least one refusal, **or a rule
that did not run** (an unevaluated check is not a pass — pass ``--build-direction`` to run the direction rule,
or ``--declaration-only`` to say out loud that a partial check is what you want); ``2`` the input could not be
read (missing/invalid file, bad JSON).

Usage::

    dev/tools/check_handoff.py <manifest.json> [--build-direction 0,0,1] [--units mm]
                              [--rule-version onshapescript.mesh-set-signature/1] [--readings r.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fdm_analysis.conversion.identity_check import check_identity_against  # noqa: E402
from fdm_analysis.conversion.print_basis import check_print_basis  # noqa: E402


def _direction(text: str) -> list[float] | None:
    if not text:
        return None
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("--build-direction needs three comma-separated numbers")
    try:
        return [float(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--build-direction is not numeric: {exc}") from exc


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _print_refusals(scope: str, refusals: list[dict[str, Any]]) -> None:
    for refusal in refusals:
        rule = refusal.get("rule") or refusal.get("where") or "?"
        where = refusal.get("where", "?")
        print(f"  [{scope}] REFUSED {rule} at {where}")
        print(f"      problem : {refusal.get('problem')}")
        print(f"      required: {refusal.get('required_fix')}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", help="path to a handoff manifest (JSON)")
    parser.add_argument("--build-direction", default="",
                        help="the direction the CALLER intends to print in, e.g. 0,0,1")
    parser.add_argument("--units", default="", help="the unit the consumer measured in (identity check)")
    parser.add_argument("--rule-version", default="",
                        help="the canonical-form version the consumer's own digest was computed under")
    parser.add_argument("--readings", default="",
                        help="JSON file of consumer readings: {\"set\": {...}, \"pieces\": [{...}]}")
    parser.add_argument("--declaration-only", action="store_true",
                        help="accept a check that could not run every rule (the direction rule needs "
                             "--build-direction); the verdict then says PARTIAL rather than PASS")
    args = parser.parse_args(argv)

    try:
        manifest = _load(args.manifest)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read the handoff manifest {args.manifest!r}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(manifest, dict):
        print(f"the handoff manifest {args.manifest!r} is not a JSON object", file=sys.stderr)
        return 2

    try:
        direction = _direction(args.build_direction)
    except argparse.ArgumentTypeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    readings: dict[str, Any] = {}
    if args.readings:
        try:
            readings = _load(args.readings)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"cannot read the readings file {args.readings!r}: {exc}", file=sys.stderr)
            return 2
        if not isinstance(readings, dict):
            print(f"the readings file {args.readings!r} is not a JSON object", file=sys.stderr)
            return 2

    declaration = manifest.get("declaration") or {}
    print(f"handoff: {args.manifest}")
    print(f"  schema     : {declaration.get('schema') or manifest.get('schema') or '(none declared)'}")
    print(f"  units      : {manifest.get('units') or declaration.get('units') or '(none declared)'}")
    print(f"  produced by: {manifest.get('produced_by') or declaration.get('producedBy') or '(undeclared)'}")

    failures = 0

    # --- the print-fit contract, from the consumer's side
    basis = check_print_basis(manifest, build_direction=direction)
    scope = ("complete" if basis.get("complete") else
             "INCOMPLETE (rule " + ", ".join(str(r["rule"]) for r in basis.get("rulesNotRun") or []) + " did not run)")
    print(f"\nprint basis  : {'ok' if basis['ok'] else 'REFUSED'} "
          f"({len(basis['refusals'])} refusal(s), rules {basis.get('rulesRun')}, {scope})")
    if basis["refusals"]:
        failures += 1
        _print_refusals("print", basis["refusals"])
    for skipped in basis.get("rulesNotRun") or []:
        # An unevaluated rule must be as loud as a refused one: `ok: true` next to a rule that never ran is
        # the "looks like all-green" shape this tool exists to prevent.
        print(f"  [print] NOT RUN rule {skipped['rule']}: {skipped['what']}")
        print(f"      why     : {skipped['why']}")
        print(f"      close it: {skipped['how_to_close']}")
        if not args.declaration_only:
            failures += 1

    # --- identity, only over readings the consumer actually took
    readings_pieces = readings.get("pieces") if isinstance(readings.get("pieces"), list) else None
    readings_set = readings.get("set") if isinstance(readings.get("set"), dict) else None
    identity = check_identity_against(
        manifest,
        units=args.units or None,
        identity_rule_version=args.rule_version or None,
        set_readings=readings_set,
        piece_readings=readings_pieces,
        set_signature_sha256=readings.get("setSignature") if isinstance(readings, dict) else None,
    )
    print(f"\nidentity     : {identity['identityLevel']} "
          f"({'ok' if identity['ok'] else 'REFUSED'}, {len(identity['refusals'])} refusal(s))")
    if identity["refusals"]:
        failures += 1
    _print_refusals("identity", identity["refusals"])
    for quantity, verdict in identity["verdicts"].items():
        status = verdict.get("status")
        detail = ""
        if status in {"within", "outside"}:
            detail = (f" — worst piece {verdict.get('worstPiece', {}).get('index')}, "
                      f"difference {verdict.get('difference', verdict.get('worstPiece', {}).get('difference')):.3e} "
                      f"against a declared {verdict.get('declaredTolerance'):.3g}")
        print(f"      {quantity:<16} {status}{detail}")
    if not readings_set and not readings_pieces:
        print("      (no consumer readings supplied: identity reports `not_provided` rather than agreement)")

    if failures == 0:
        partial = bool((basis.get("rulesNotRun") or [])) and args.declaration_only
        label = "PASS (PARTIAL, accepted by --declaration-only)" if partial else "PASS"
        print(f"\nverdict      : {label} (no refusal)")
        return 0
    print(f"\nverdict      : FAIL ({failures} item(s): a refusal or a rule that did not run)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
