#!/usr/bin/env python3
"""Cross-read per-piece identity: what addresses a piece in each plane's real record?

Objective (1) asks *by path or by sha256* a piece is addressed. This tool reads the three planes'
**real** records and measures how each one actually answers that, instead of restating a preference:

* this plane's handoff manifest -- per-part `mesh.sha256` + `sha256_stable` + `sha256_evidence`
  (the digest recorded twice), a file *name* (not a path) beside it, `label: null` explicitly;
* CadQ's three-plane manifest -- per-solid `sha256` / `sha256_stable` / `sha256_stable_basis`, a
  `path`, `label` (null for all 70), and `signature_note` stating a signature is a filter, not identity;
* MeshQ's `meshq_result.json` -- a digest per **export artifact** (`outputs[].sha256` +
  `objects: [...]` declaring which objects it covers), object keys as names, and an absolute host path.

Read-only and offline. ``--check`` exits 0 only if every rule holds; a FAIL is a measured interface gap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

MESHQ_RESULT = pathlib.Path("/home/lijq/code/MeshQ/artifacts/contract-slice/work_slice_clean/meshq_result.json")
CADQ_MANIFEST = pathlib.Path(
    "/home/lijq/code/CadQ/cad_agent/output/three-plane/gf-storage-v25-U-two-legs-lin0.05-ang0.1/manifest.json"
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
#: Keys that *state an addressing rule*. `produced_by.identity` is a producer name, not an address, so a
#: bare "identity" match was a false positive -- measured the first time this tool ran.
ADDRESS_WORDS = ("address", "addressing", "address_rule", "addressRule", "signature_note", "sha256Note", "sha256_note")


def _digest_keys(node: Any, out: list[tuple[str, Any]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if "sha256" in str(key) or "digest" in str(key):
                out.append((str(key), value))
            _digest_keys(value, out)
    elif isinstance(node, list):
        for value in node:
            _digest_keys(value, out)


def _address_statements(node: Any, out: list[str], path: str = "") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if key in ADDRESS_WORDS and isinstance(value, str):
                out.append(f"{here}: {value[:160]}")
            _address_statements(value, out, here)
    elif isinstance(node, list):
        for index, value in enumerate(node[:80]):
            _address_statements(value, out, f"{path}[{index}]")


def _paths(node: Any, out: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "path" and isinstance(value, str):
                out.append(value)
            _paths(value, out)
    elif isinstance(node, list):
        for value in node:
            _paths(value, out)


def _labels(node: Any, out: list[Any]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("label", "name"):
                out.append(value)
            _labels(value, out)
    elif isinstance(node, list):
        for value in node:
            _labels(value, out)


def meshq_facts() -> dict[str, Any]:
    data = json.loads(MESHQ_RESULT.read_text(encoding="utf-8"))
    outputs = data.get("outputs") or []
    digests: list[tuple[str, Any]] = []
    _digest_keys(outputs, digests)
    statements: list[str] = []
    _address_statements(data.get("inspection", {}), statements)
    _address_statements({k: v for k, v in data.items() if k != "inspection"}, statements)
    paths: list[str] = []
    _paths(outputs, paths)
    labels: list[Any] = []
    _labels(data["inspection"].get("objects") or {}, labels)
    return {
        "objects": sorted((data["inspection"].get("objects") or {})),
        "output_digests": [(k, v) for k, v in digests if isinstance(v, str) and HEX64.match(v)],
        "output_stability": [o.get("sha256_stable") for o in outputs],
        "declared_coverage": [o.get("objects") for o in outputs],
        "address_statements": statements,
        "paths": paths,
        "absolute_paths": [p for p in paths if p.startswith("/")],
        "declared_labels": labels,
    }


def cadq_facts() -> dict[str, Any]:
    data = json.loads(CADQ_MANIFEST.read_text(encoding="utf-8"))
    solids = data.get("solids") or []
    statements: list[str] = []
    _address_statements(data, statements)
    return {
        "solids": len(solids),
        "per_solid_digests": sum(1 for s in solids if isinstance(s.get("sha256"), str)),
        "per_solid_stability": sorted({str(s.get("sha256_stable")) for s in solids}),
        "stability_basis": sorted({str(s.get("sha256_stable_basis")) for s in solids}),
        "labels_null": sum(1 for s in solids if s.get("label") is None),
        "labels_present": sum(1 for s in solids if "label" in s),
        "paths": [s.get("path") for s in solids[:3] if s.get("path")],
        "address_statements": statements,
    }


def our_facts() -> dict[str, Any]:
    """Read this plane's own record shape from the code that writes it (the schema is the source)."""
    source = (pathlib.Path(__file__).resolve().parents[2] / "fdm_analysis" / "conversion" / "step_tessellation.py").read_text(encoding="utf-8")
    return {
        "per_piece_digest": '"sha256": measured["sha256"]' in source,
        "per_piece_stability": '"sha256_stable": same_bytes' in source,
        "digest_evidence": '"sha256_evidence": evidence' in source,
        "label_is_explicit_null": '"label": None' in source,
        "path_is_a_name_not_a_path": '"path": Path(measured["path"]).name' in source,
    }


def facts() -> dict[str, Any]:
    meshq, cadq, own = meshq_facts(), cadq_facts(), our_facts()
    rules: list[dict[str, Any]] = []

    def rule(rule_id: str, ok: bool, detail: str) -> None:
        rules.append({"rule": rule_id, "passed": bool(ok), "detail": detail})

    rule("every-piece-is-reachable-from-a-content-digest",
         own["per_piece_digest"] and cadq["per_solid_digests"] == cadq["solids"] and bool(meshq["output_digests"]),
         f"this plane: per-part digest; CadQ: {cadq['per_solid_digests']}/{cadq['solids']} solids carry one; "
         f"MeshQ: {len(meshq['output_digests'])} digest(s) in `outputs[]` covering {meshq['declared_coverage']}")
    rule("the-digest-declares-whether-it-is-stable",
         own["per_piece_stability"] and own["digest_evidence"] and cadq["per_solid_stability"] not in ("['False']", "['None']")
         and all(value is not None for value in meshq["output_stability"]),
         f"this plane: `sha256_stable` + the digest recorded twice as evidence; CadQ: {cadq['per_solid_stability']} "
         f"(basis {cadq['stability_basis']}); MeshQ: {meshq['output_stability']}")
    rule("a-piece-names-its-label-or-says-null-explicitly",
         own["label_is_explicit_null"] and cadq["labels_present"] == cadq["solids"] and bool(meshq["declared_labels"]),
         f"this plane: `label: null` (an explicit absence); CadQ: {cadq['labels_present']}/{cadq['solids']} carry "
         f"the field, {cadq['labels_null']} of them null; MeshQ: no `label`/`name` field at all -- a piece's only "
         f"human-facing name is its object key {meshq['objects']}, so it has to be inferred from a dict key")
    rule("no-piece-is-addressed-by-a-path-alone",
         own["path_is_a_name_not_a_path"],
         f"this plane reduces the path to a file name; MeshQ publishes an ABSOLUTE path "
         f"({meshq['absolute_paths'][:1]}) beside its digest, so the digest must be the address")
    rule("the-record-states-which-address-is-authoritative",
         bool(cadq["address_statements"]) and bool(meshq["address_statements"]),
         f"CadQ: {cadq['address_statements'][:1] or 'none'}; MeshQ: {meshq['address_statements'] or 'none'}")
    return {"meshq": meshq, "cadq": cadq, "thisPlane": own, "rules": rules, "ok": all(r["passed"] for r in rules)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--facts", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not (args.facts or args.check or args.json):
        parser.error("one of --facts/--check/--json is required")
    for label, path in (("MeshQ", MESHQ_RESULT), ("CadQ", CADQ_MANIFEST)):
        if not path.is_file():
            print(f"cannot read {label} record at {path}", file=sys.stderr)
            return 2
    report = facts()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1
    if args.facts:
        print(f"this plane: {report['thisPlane']}")
        print(f"CadQ: {report['cadq']}")
        print(f"MeshQ: {report['meshq']}")
    if args.check:
        for item in report["rules"]:
            print(f"{'PASS' if item['passed'] else 'FAIL'} {item['rule']}: {item['detail']}")
        passed = sum(1 for item in report["rules"] if item["passed"])
        print(f"{passed}/{len(report['rules'])} rules passed")
        return 0 if report["ok"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
