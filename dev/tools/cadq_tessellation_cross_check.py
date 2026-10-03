#!/usr/bin/env python3
"""Independently recompute a CadQ tessellation delivery, and test the claims made about it.

Why this exists (measured 2026-10-04, round 20 of the three-plane negotiation): CadQ's manifest declares
`achieved <= 2.414e-6 relative` for its mesh volume and offers an *explanation* -- that the residual is
"naive `+=` vs `math.fsum` summation order". A reader must not accept an explanation; this tool re-reads
the delivered STL bytes with its own implementation and measures:

    1. my aggregate volume vs the declared tessellation volume;
    2. my per-part worst deviation vs the declared `achieved` bound;
    3. `+=` vs `math.fsum` on the same bytes (the proposed explanation, as a number);
    4. whether the aggregate hides the worst part (the house rule: report the per-piece maximum);
    5. whether the B-Rep signature is tolerance-independent (both tolerance variants).

Offline and read-only: it reads another plane's files and writes nothing.

    python dev/tools/cadq_tessellation_cross_check.py --facts [--dir <three-plane dir>]
    python dev/tools/cadq_tessellation_cross_check.py --check   # exit 0 = all rules passed
    python dev/tools/cadq_tessellation_cross_check.py --json
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import struct
import sys
from typing import Any

CADQ_THREE_PLANE = pathlib.Path("/home/lijq/code/CadQ/cad_agent/output/three-plane")

#: The declared bound is what the producer claims; a cross-check must not be looser than the claim.
DECLARED_ACHIEVED_RELATIVE = 2.414e-06
#: `+=` vs `fsum` must be far below the residual, or the producer's explanation would be plausible.
SUMMATION_ORDER_RELATIVE = 1e-12


def read_binary_stl_volumes(path: pathlib.Path) -> dict[str, Any]:
    """Signed tetrahedron volumes from the delivered bytes: origin-pivot naive `+=`, plus `fsum`."""
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0] if len(data) >= 84 else 0
    total, terms, far = 0.0, [], 0.0
    offset = 84
    for _ in range(count):
        v = struct.unpack_from("<12f", data, offset)
        ax, ay, az, bx, by, bz, cx, cy, cz = v[3], v[4], v[5], v[6], v[7], v[8], v[9], v[10], v[11]
        term = (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6.0
        total += term
        terms.append(term)
        far = max(far, abs(ax), abs(ay), abs(az), abs(bx), abs(by), abs(bz), abs(cx), abs(cy), abs(cz))
        offset += 50
    return {
        "triangles": count,
        "naive": abs(total),
        "fsum": abs(math.fsum(terms)),
        "farthest_mm": far,
    }


def _variant(directory: pathlib.Path) -> dict[str, Any]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    parts = []
    for solid in manifest.get("solids", []):
        measured = read_binary_stl_volumes(directory / solid["path"])
        declared = solid["tessellation"]["volume_mm3"]
        parts.append({
            "index": solid["index"],
            "declared_tessellation_mm3": declared,
            "declared_brep_mm3": solid["brep"]["volume_mm3"],
            "measured_naive_mm3": measured["naive"],
            "measured_fsum_mm3": measured["fsum"],
            "triangles": measured["triangles"],
            "farthest_mm": measured["farthest_mm"],
            "measured_vs_declared": abs(measured["naive"] - declared) / declared,
            "summation_order": abs(measured["naive"] - measured["fsum"]) / measured["fsum"],
        })
    decl_tess = sum(p["declared_tessellation_mm3"] for p in parts)
    decl_brep = sum(p["declared_brep_mm3"] for p in parts)
    measured = sum(p["measured_naive_mm3"] for p in parts)
    worst = max(parts, key=lambda p: p["measured_vs_declared"]) if parts else {}
    return {
        "directory": str(directory),
        "schema": manifest.get("schema"),
        "handoff_schema": manifest.get("handoff_schema"),
        "plane": (manifest.get("produced_by") or {}).get("plane"),
        "units": manifest.get("units"),
        "linear_tolerance_mm": manifest["declaration"]["tessellation"]["linear_tolerance_mm"],
        "angular_tolerance_rad": manifest["declaration"]["tessellation"]["angular_tolerance_rad"],
        "declared_by": manifest["declaration"]["tessellation"]["declared_by"],
        "used_by": manifest["declaration"]["tessellation"]["used_by"],
        "independent_kernel": manifest["declaration"]["tessellation"].get(
            "independent_kernel",
            (manifest["declaration"]["tessellation"].get("kernel") or {}).get("independent_kernel"),
        ),
        "signature": manifest.get("signature"),
        "triangle_count": (manifest["declaration"].get("mesh") or {}).get("triangle_count"),
        "parts": parts,
        "totals": {
            "part_count": len(parts),
            "declared_tessellation_mm3": decl_tess,
            "declared_brep_mm3": decl_brep,
            "measured_naive_mm3": measured,
            "measured_vs_declared_relative": abs(measured - decl_tess) / decl_tess,
            "measured_vs_brep_relative": abs(measured - decl_brep) / decl_brep,
            "worst_part_relative": worst.get("measured_vs_declared", 0.0),
            "worst_part_index": worst.get("index"),
            "worst_part_farthest_mm": worst.get("farthest_mm", 0.0),
            "worst_summation_order_relative": max((p["summation_order"] for p in parts), default=0.0),
        },
    }


def facts(directory: pathlib.Path = CADQ_THREE_PLANE) -> dict[str, Any]:
    variants = sorted(d for d in directory.iterdir() if (d / "manifest.json").is_file())
    result = {"variants": [_variant(v) for v in variants]}
    rules = []
    for variant in result["variants"]:
        totals = variant["totals"]
        label = pathlib.Path(variant["directory"]).name

        def rule(rule_id: str, ok: bool, detail: str) -> None:
            rules.append({"rule": rule_id, "where": label, "passed": bool(ok), "detail": detail})

        rule("aggregate-within-declared",
             totals["measured_vs_declared_relative"] <= DECLARED_ACHIEVED_RELATIVE,
             f"measured vs declared aggregate {totals['measured_vs_declared_relative']:.3e} "
             f"<= {DECLARED_ACHIEVED_RELATIVE:.3e}")
        rule("worst-part-within-declared",
             totals["worst_part_relative"] <= DECLARED_ACHIEVED_RELATIVE,
             f"worst part #{totals['worst_part_index']} {totals['worst_part_relative']:.3e} "
             f"(farthest coordinate {totals['worst_part_farthest_mm']:.1f} mm)")
        rule("declared-bound-is-not-explained-by-summation-order",
             totals["worst_summation_order_relative"] <= SUMMATION_ORDER_RELATIVE,
             f"+= vs fsum {totals['worst_summation_order_relative']:.3e} <= {SUMMATION_ORDER_RELATIVE:.0e}, "
             f"i.e. {(DECLARED_ACHIEVED_RELATIVE / max(totals['worst_summation_order_relative'], 1e-300)):.0e}x smaller "
             "than the residual")
        rule("per-piece-not-aggregate",
             totals["worst_part_relative"] > 10 * totals["measured_vs_declared_relative"],
             f"worst part {totals['worst_part_relative']:.3e} is "
             f"{totals['worst_part_relative'] / max(totals['measured_vs_declared_relative'], 1e-300):.1f}x "
             f"the aggregate {totals['measured_vs_declared_relative']:.3e}")
    if len(result["variants"]) >= 2:
        signatures = {v["signature"] for v in result["variants"]}
        triangles = {v["triangle_count"] for v in result["variants"]}
        rules.append({
            "rule": "signature-is-tolerance-independent", "where": "both variants",
            "passed": len(signatures) == 1 and len(triangles) == len(result["variants"]),
            "detail": f"{len(result['variants'])} tolerance variants, one signature={len(signatures) == 1}, "
                      f"triangle counts {sorted(triangles)}",
        })
    result["rules"] = rules
    result["ok"] = all(r["passed"] for r in rules)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", default=str(CADQ_THREE_PLANE), help="CadQ's three-plane output directory")
    parser.add_argument("--facts", action="store_true", help="print what was measured")
    parser.add_argument("--check", action="store_true", help="run the rules; exit 0 only if all passed")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.facts and not args.check and not args.json:
        parser.error("one of --facts/--check/--json is required")
    directory = pathlib.Path(args.dir)
    if not directory.is_dir():
        print(f"cannot read {directory}: not a directory", file=sys.stderr)
        return 2
    try:
        report = facts(directory)
    except (OSError, ValueError, KeyError, struct.error) as exc:
        print(f"cannot read {directory}: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1
    if args.facts:
        for variant in report["variants"]:
            totals = variant["totals"]
            print(f"{pathlib.Path(variant['directory']).name}: {variant['schema']} units={variant['units']} "
                  f"lin={variant['linear_tolerance_mm']} ang={variant['angular_tolerance_rad']} "
                  f"declared_by={variant['declared_by']} used_by={variant['used_by']} "
                  f"independent_kernel={variant['independent_kernel']}")
            print(f"  parts={totals['part_count']} triangles={variant['triangle_count']} "
                  f"signature={str(variant['signature'])[:16]}...")
            print(f"  declared tessellation total {totals['declared_tessellation_mm3']:.6f} mm^3 | "
                  f"declared B-Rep total {totals['declared_brep_mm3']:.6f} mm^3")
            print(f"  my own recomputation from the delivered bytes: {totals['measured_naive_mm3']:.6f} mm^3 "
                  f"({totals['measured_vs_declared_relative']:.3e} vs declared, "
                  f"{totals['measured_vs_brep_relative']:.3e} vs B-Rep)")
            print(f"  worst part #{totals['worst_part_index']}: {totals['worst_part_relative']:.3e} "
                  f"(farthest coordinate {totals['worst_part_farthest_mm']:.1f} mm) | "
                  f"+= vs fsum {totals['worst_summation_order_relative']:.3e}")
    if args.check:
        for rule in report["rules"]:
            print(f"{'PASS' if rule['passed'] else 'FAIL'} {rule['rule']} [{rule['where']}]: {rule['detail']}")
        print(f"{'all rules passed' if report['ok'] else 'RULE FAILED'}: "
              f"{sum(1 for r in report['rules'] if r['passed'])}/{len(report['rules'])}")
        return 0 if report["ok"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
