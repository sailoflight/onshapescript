#!/usr/bin/env python3
"""Local verification of every vendored document corpus.

Zero network, zero API-quota cost: checks that the JSON indexes are consistent
with their raw sources, that the structures are complete, and that
cross-references resolve. Writes report.json and prints a human summary.

Corpora verified:
  FS reference   reference/fsdoc/{index,guide}.json  vs the raw FsDoc HTML
  REST API       reference/onshape-api/api_index.json vs openapi.json
  Auth/errors    reference/onshape-api-docs/api_docs.json vs the raw HTML
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
FSDOC = ROOT / "reference" / "fsdoc"
REST = ROOT / "reference" / "onshape-api"
AUTH = ROOT / "reference" / "onshape-api-docs"

checks: list[dict[str, Any]] = []
stats: dict[str, Any] = {}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append({"name": name, "ok": ok, "detail": detail[:400]})


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_fs() -> None:
    idx = load(FSDOC / "index.json")
    guide = load(FSDOC / "guide.json")

    # Source sha256 pinning.
    lib_sha = sha256_of(FSDOC / "library.html")
    check("FS index.json librarySha256 matches library.html",
          idx.get("librarySha256") == lib_sha,
          f"index={idx.get('librarySha256')} html={lib_sha}")
    missing = [
        (p["page"], p["sha256"])
        for p in guide["pages"]
        if not (FSDOC / p["path"]).is_file()
        or sha256_of(FSDOC / p["path"]) != p["sha256"]
    ]
    check("FS guide.json page sha256 all match", not missing,
          f"{len(missing)} mismatch(es)" if missing else f"{len(guide['pages'])} pages ok")

    # Structural completeness.
    def all_have(entries, fields, label):
        bad = [e.get("name") for e in entries
               if not all(f in e and e.get(f) not in (None, "", []) for f in fields)]
        check(f"FS {label} entries have {fields}", not bad,
              f"{len(bad)} missing: {bad[:5]}" if bad else f"{len(entries)} ok")

    all_have(idx["functions"], ["name", "signature", "module"], "function")
    all_have(idx["types"], ["name", "kind"], "type")
    all_have(idx["constants"], ["name"], "constant")
    all_have(idx["predicates"], ["name", "signature"], "predicate")

    # Operator overloads must not have empty names (fixed once before).
    empty_ops = [
        e["name"] for e in idx["functions"]
        if not e.get("name") and re.match(r"^[^A-Za-z0-9]", e.get("anchor", ""))
    ]
    check("FS operator overloads have non-empty names", not empty_ops,
          f"{len(empty_ops)} empty: {empty_ops[:5]}")

    # Cross-reference: parameter types that look like library types exist.
    # GBTErrorStringEnum is a known *official* FsDoc gap: referenced 19 times
    # as GBTErrorStringEnum.VALUE by the ev* query error parameters, but never
    # defined in library.html. Treated as a known gap, not a failure.
    KNOWN_FS_DANGLING = {"GBTErrorStringEnum"}
    known_types = {t["name"] for t in idx["types"]}
    known_modules = {m for m in idx["modules"] if isinstance(m, str)} or \
        {m.get("name") if isinstance(m, dict) else None for m in idx["modules"]}
    dangling = []
    for fn in idx["functions"]:
        for param in fn.get("parameters", []):
            ptype = param.get("type", "")
            refs = re.findall(r"[A-Z][A-Za-z0-9_]*", ptype)
            for ref in refs:
                if ref in known_types or ref in known_modules:
                    continue
                if ref.isupper():
                    continue  # enum value / constant, not a type reference
                dangling.append((fn["name"], ref))
    real_dangling = [d for d in dangling if d[1] not in KNOWN_FS_DANGLING]
    check("FS function parameter type refs resolve to a type/module",
          not real_dangling,
          f"{len(real_dangling)} dangling refs (first 5): "
          + ", ".join(f"{a}->{b}" for a, b in real_dangling[:5]) if real_dangling else "ok")
    stats["knownOfficialGaps"] = {
        "fsDanglingEnumRefs": sorted({d[1] for d in dangling}),
    }

    stats["fs"] = {
        "functions": len(idx["functions"]),
        "types": len(idx["types"]),
        "constants": len(idx["constants"]),
        "predicates": len(idx["predicates"]),
        "modules": len(idx["modules"]),
        "guidePages": len(guide["pages"]),
    }
    # Naming-prefix statistics for the FS experience doc.
    prefixes: Counter[str] = Counter()
    for fn in idx["functions"]:
        name = fn.get("name") or ""
        if name:
            prefixes[name.split("_")[0]] += 1
    stats["fsFunctionPrefixes"] = prefixes.most_common(15)
    # Parameter-type distribution.
    param_types: Counter[str] = Counter()
    for fn in idx["functions"]:
        for param in fn.get("parameters", []):
            ptype = (param.get("type") or "").split(" ")[0].split("?")[0]
            if ptype:
                param_types[ptype] += 1
    stats["fsParameterTypes"] = param_types.most_common(12)


def verify_rest() -> None:
    idx = load(REST / "api_index.json")
    quick = load(REST / "api_quick.json")
    openapi_sha = sha256_of(REST / "openapi.json")

    check("REST api_index.json sourceSha256 matches openapi.json",
          idx.get("sourceSha256") == openapi_sha,
          f"index={idx.get('sourceSha256')} openapi={openapi_sha}")
    check("REST api_quick.json specVersion matches", quick.get("specVersion") == idx.get("specVersion"))

    schemas = {s["name"] for s in idx["schemas"]}
    schemes = set(idx.get("securitySchemes", {}))
    bad = []
    empty_summary: list[tuple[str, str]] = []
    for e in idx["endpoints"]:
        if not all(e.get(k) for k in ("method", "path", "operationId")):
            bad.append(("missing-fields", e.get("path"), e.get("method")))
        if not e.get("summary"):
            empty_summary.append((e["path"], e["method"]))
        for p in e.get("parameters", []):
            if not p.get("name") or not p.get("in"):
                bad.append(("param", e["path"], p.get("name")))
        for s in e.get("security", []):
            if s not in schemes:
                bad.append(("security", e["path"], s))
        rb = e.get("requestBody") or {}
        ref = rb.get("schemaRef")
        if ref and ref not in schemas:
            bad.append(("requestBody-ref", e["path"], ref))
        for r in e.get("responses", []):
            ref = r.get("schemaRef")
            if ref and ref not in schemas:
                bad.append(("response-ref", e["path"], ref))
    check("REST endpoints well-formed, security + schema refs resolve",
          not bad, f"{len(bad)} issues (first 5): {bad[:5]}" if bad else f"{len(idx['endpoints'])} ok")
    stats.setdefault("knownOfficialGaps", {})["restEmptySummary"] = empty_summary

    # quick.json surface must match api_index.json.
    quick_keys = {(q["path"], q["method"]) for q in quick["endpoints"]}
    idx_keys = {(e["path"], e["method"]) for e in idx["endpoints"]}
    check("REST api_quick.json surface matches api_index.json",
          quick_keys == idx_keys,
          f"quick-only {len(quick_keys - idx_keys)}, index-only {len(idx_keys - quick_keys)}")

    stats["rest"] = {
        "endpoints": len(idx["endpoints"]),
        "schemas": len(idx["schemas"]),
        "tags": len(idx["tags"]),
        "specVersion": idx.get("specVersion"),
        "baseUrl": idx.get("baseUrl"),
        "methods": dict(Counter(e["method"] for e in idx["endpoints"])),
        "withRequestBody": sum(1 for e in idx["endpoints"] if e["requestBody"]),
        "requestBodyRequired": sum(
            1 for e in idx["endpoints"]
            if e["requestBody"] and e["requestBody"].get("required")
        ),
        "paramLocations": dict(Counter(
            p["in"] for e in idx["endpoints"] for p in e["parameters"]
        )),
        "security": dict(Counter(
            s for e in idx["endpoints"] for s in e["security"]
        )),
        "deprecated": sum(1 for e in idx["endpoints"] if e["deprecated"]),
    }


def verify_auth() -> None:
    docs = load(AUTH / "api_docs.json")
    missing = [
        p["page"] for p in docs["pages"]
        if not (AUTH / f"{p['page']}.html").is_file()
        or sha256_of(AUTH / f"{p['page']}.html") != p["sha256"]
    ]
    check("Auth docs sha256 all match", not missing,
          f"mismatch: {missing}" if missing else f"{len(docs['pages'])} pages ok")
    codes = docs["errorCodes"]
    bad = [c for c in codes if not all(c.get(k) for k in ("code", "name", "category"))]
    check("Auth errorCodes well-formed", not bad,
          f"{len(bad)} bad" if bad else f"{len(codes)} codes ok")
    stats["auth"] = {
        "pages": [p["page"] for p in docs["pages"]],
        "errorCodes": len(codes),
        "codes": [c["code"] for c in codes],
    }


def main() -> int:
    verify_fs()
    verify_rest()
    verify_auth()
    failed = [c for c in checks if not c["ok"]]
    report = {
        "checkedAt": None,  # no clock in the repo; stamp after running if wanted
        "summary": {"total": len(checks), "passed": len(checks) - len(failed),
                    "failed": len(failed)},
        "checks": checks,
        "stats": stats,
    }
    (ROOT / "docs" / "verification" / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"verification: {len(checks) - len(failed)}/{len(checks)} checks passed\n")
    for c in checks:
        mark = "ok " if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['name']}" + (f" — {c['detail']}" if c["detail"] else ""))
    if failed:
        print(f"\n{len(failed)} check(s) FAILED")
        return 1
    print("\nall checks passed; stats:")
    for key, value in stats.items():
        print(f"  {key}: {json.dumps(value, ensure_ascii=False)[:300]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
