#!/usr/bin/env python3
"""Cross-read the print-fit boundary: who declares an envelope, and can a judgement be re-checked?

Objective (2) of the three-plane negotiation asks two questions: **who decides printability**, and
**where are travel and placement declared**. This plane's answer is already in its own contract
(`fdm_analysis/conversion/print_basis.py` refuses an envelope declared by anyone but the consumer, and
refuses a producer-stamped `printable` verdict; `step_tessellation.py` ships
`envelope.declared_by = "consumer"` with null x/y/z and an explicit note). This tool measures what the
**other two planes' records actually contain**, so the boundary is compared with data rather than
restated:

* does any producer record declare an envelope, a bed, travel or a placement? (expected: none)
* does a print-fit judgement ship the inputs of its own criterion? (CadQ's overhang table: yes)
* can that judgement be **recomputed** from the shipped columns? (CadQ's: no -- measured)
* does a declared fit target name its owner? (CadQ's `target_mm`: no)

Read-only, offline: it reads other planes' files and writes nothing.

    python dev/tools/print_fit_cross_read.py --facts
    python dev/tools/print_fit_cross_read.py --check    # exit 0 only if every rule holds
    python dev/tools/print_fit_cross_read.py --json
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from collections import defaultdict
from typing import Any, Iterable

CADQ_PRINT = pathlib.Path("/home/lijq/code/CadQ/cad_agent/output/print-adaptation")
MESHQ_ARTIFACTS = pathlib.Path("/home/lijq/code/MeshQ/artifacts")

#: Names that would mean "a machine state was stamped by a producer". An envelope is consumer state:
#: our own contract refuses `envelope.declared_by != "consumer"` and a producer `printable` verdict.
ENVELOPE_NAMES = (
    "envelope", "bed", "bed_size", "bed_size_mm", "build_volume", "build_volume_mm",
    "print_volume", "travel", "travel_mm", "placement", "printer", "machine",
    "printable", "printability",
)
MAX_FILES = 400


def _walk_keys(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            out.add(str(key))
            _walk_keys(value, out)
    elif isinstance(node, list):
        for value in node[:200]:
            _walk_keys(value, out)


def scan_declarations(roots: Iterable[pathlib.Path]) -> dict[str, Any]:
    """Look for a producer-stamped machine state anywhere in the peer record trees."""
    hits: list[dict[str, str]] = []
    scanned = 0
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.json")):
            if scanned >= MAX_FILES:
                break
            scanned += 1
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            keys: set[str] = set()
            _walk_keys(data, keys)
            for name in ENVELOPE_NAMES:
                if name in keys:
                    hits.append({"file": str(path), "key": name})
    return {"files_scanned": scanned, "hits": hits}


def cadq_overhang_facts() -> dict[str, Any]:
    path = CADQ_PRINT / "overhang-vs-r7d.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    inputs = ("normal_z", "worst_drop_mm", "area_mm2")
    missing = [i for i, row in enumerate(rows) if any(row.get(key, "") == "" for key in inputs)]
    mapping: dict[float, set[str]] = defaultdict(set)
    for row in rows:
        mapping[float(row["worst_drop_mm"])].add(row["needs_support"])
    contradictory = {drop: sorted(values) for drop, values in mapping.items() if len(values) > 1}
    return {
        "path": str(path),
        "columns": list(rows[0]) if rows else [],
        "rows": len(rows),
        "parts": len({row["part"] for row in rows}),
        "rows_missing_a_criterion_input": missing,
        "judgements": sorted({row["needs_support"] for row in rows}),
        "drop_to_judgement_contradictions": contradictory,
        "has_owner_column": any("own" in c.lower() or "declar" in c.lower() for c in (rows[0] if rows else [])),
    }


def cadq_fit_gap_facts() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in ("fit-gap-r17.json", "fit-gap-all-r22.json"):
        path = CADQ_PRINT / name
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = {key for row in (data.get("rows") or [])[:1] for key in row}
        out[name] = {
            "target_mm": data.get("target_mm"),
            "row_columns": sorted(keys),
            "declares_its_owner": any("own" in k.lower() or "declar" in k.lower() for k in keys)
            or any("own" in k.lower() or "declar" in k.lower() for k in data),
            "actions": sorted({row.get("action") for row in (data.get("rows") or [])}),
        }
    return out


def print_basis_rules() -> dict[str, Any]:
    """Our own contract's print rules, quoted from the code that enforces them, not from prose."""
    source = (pathlib.Path(__file__).resolve().parents[2] / "fdm_analysis" / "conversion" / "print_basis.py").read_text(encoding="utf-8")
    return {
        "refuses_a_producer_envelope": "an envelope is machine state: only the consumer declares it" in source,
        "refuses_a_producer_printability_verdict": "the producer stamped a printability verdict" in source,
    }


def facts() -> dict[str, Any]:
    overhang = cadq_overhang_facts()
    fit_gap = cadq_fit_gap_facts()
    scan = scan_declarations([MESHQ_ARTIFACTS, CADQ_PRINT])
    rules: list[dict[str, Any]] = []

    def rule(rule_id: str, ok: bool, detail: str) -> None:
        rules.append({"rule": rule_id, "passed": bool(ok), "detail": detail})

    rule("cadq-overhang-judgement-carries-its-inputs",
         not overhang["rows_missing_a_criterion_input"],
         f"{overhang['rows']} rows over {overhang['parts']} parts, columns {overhang['columns']}; "
         f"rows missing an input: {len(overhang['rows_missing_a_criterion_input'])}")
    rule("cadq-overhang-judgement-recomputable-from-shipped-columns",
         not overhang["drop_to_judgement_contradictions"],
         "same shipped input, two different judgements: "
         f"{overhang['drop_to_judgement_contradictions'] or 'none'}")
    rule("cadq-fit-gap-target-has-an-owner",
         all(item["declares_its_owner"] for item in fit_gap.values()),
         "; ".join(f"{name}: target_mm={item['target_mm']} owner={item['declares_its_owner']}"
                   for name, item in fit_gap.items()))
    rule("no-plane-stamps-a-machine-state",
         not scan["hits"],
         f"scanned {scan['files_scanned']} JSON files under the peer trees; stamps found: "
         f"{[h['key'] for h in scan['hits']] or 'none'}")
    own = print_basis_rules()
    rule("this-planes-contract-refuses-to-stamp-either",
         all(own.values()), json.dumps(own))
    return {"overhang": overhang, "fitGap": fit_gap, "declarationScan": scan,
            "ownContract": own, "rules": rules, "ok": all(r["passed"] for r in rules)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--facts", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not (args.facts or args.check or args.json):
        parser.error("one of --facts/--check/--json is required")
    if not CADQ_PRINT.is_dir():
        print(f"cannot read {CADQ_PRINT}: not a directory", file=sys.stderr)
        return 2
    report = facts()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1
    if args.facts:
        o, f = report["overhang"], report["fitGap"]
        print(f"CadQ overhang table: {o['rows']} rows / {o['parts']} parts, columns {o['columns']}")
        print(f"  judgements: {o['judgements']} | rows missing an input: {len(o['rows_missing_a_criterion_input'])}")
        print(f"  same shipped input, two judgements: {o['drop_to_judgement_contradictions']}")
        print(f"  owner column: {o['has_owner_column']}")
        for name, item in f.items():
            print(f"CadQ {name}: target_mm={item['target_mm']} columns={item['row_columns']} owner={item['declares_its_owner']}")
        print(f"declaration scan: {report['declarationScan']}")
        print(f"this plane's contract: {report['ownContract']}")
    if args.check:
        for item in report["rules"]:
            print(f"{'PASS' if item['passed'] else 'FAIL'} {item['rule']}: {item['detail']}")
        passed = sum(1 for item in report["rules"] if item["passed"])
        print(f"{passed}/{len(report['rules'])} rules passed"
              + ("" if report["ok"] else " -- the gaps above are measured interface defects"))
        return 0 if report["ok"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
