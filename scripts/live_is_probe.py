#!/usr/bin/env python3
"""Live existence probe for every is* predicate in the vendored FsDoc mirror,
plus the 4 the mirror omits (isQuery/isString/isArray/isType), against the
deployed FeatureScript runtime (eval libraryVersion).

Cost: (1 + number_of_failures) evals, one ledger call each (part_studio_id
passed explicitly so resolution is skipped). Compiler stops at the first error,
so bundling reveals ONE failure per eval; each failure is dropped and the rest
re-evaluated until the bundle is clean.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from onshape_fs_mcp.operations import eval_featurescript  # noqa: E402

OUT = ROOT / "outputs" / "live-is-predicates.json"
PART_STUDIO_ID = "cb487527c6e1880fc1e64db8"  # cached live target from the ledger

CANDIDATES = [
    ("isLength", "isLength(1)"),
    ("isAngle", "isAngle(1)"),
    ("isAnything", "isAnything(5)"),
    ("isReal", "isReal(1, {})"),
    ("isAcceleration", "isAcceleration(1)"),
    ("isAngularVelocity", "isAngularVelocity(1)"),
    ("isArea", "isArea(1)"),
    ("isButton", "isButton(5)"),
    ("isDensity", "isDensity(1)"),
    ("isEnergy", "isEnergy(1)"),
    ("isForce", "isForce(1)"),
    ("isFrequency", "isFrequency(1)"),
    ("isInteger", "isInteger(1)"),
    ("isLengthVector", "isLengthVector(vector(1,2,3))"),
    ("isMoment", "isMoment(1)"),
    ("isNonNegativeInteger", "isNonNegativeInteger(1)"),
    ("isPositiveInteger", "isPositiveInteger(1)"),
    ("isPressure", "isPressure(1)"),
    ("isSquare", "isSquare(1)"),
    ("isTableValue", "isTableValue(1)"),
    ("isToleranceInfoOrUndefined", "isToleranceInfoOrUndefined(1)"),
    ("isTopLevelId", "isTopLevelId(1)"),
    ("isUndefinedOrEmptyString", "isUndefinedOrEmptyString(1)"),
    ("isUnitlessVector", "isUnitlessVector(vector(1,2,3))"),
    ("isUvVector", "isUvVector(vector(1,2,3))"),
    ("isVolume", "isVolume(1)"),
    ("isWrapCone", "isWrapCone(1)"),
    ("isWrapCylinder", "isWrapCylinder(1)"),
    ("isWrapPlane", "isWrapPlane(1)"),
    # mirror-absent; the lesson calls these out as ambiguous:
    ("isQuery", "isQuery(qEverything(EntityType.BODY))"),
    ("isString", "isString(\"x\")"),
    ("isArray", "isArray([1])"),
    ("isType", "isType(5, {})"),
]

_NAME_RE = re.compile(
    r"Function ([A-Za-z_][A-Za-z0-9_]*) with|"
    r"Could not resolve symbol ([A-Za-z_][A-Za-z0-9_]*)|"
    r"Cannot reference function ([A-Za-z_][A-Za-z0-9_]*)"
)


def run_bundle(names: list[tuple[str, str]]) -> list[str]:
    body = ", ".join(call for _, call in names)
    script = f"function(context is Context, id is Id) {{ return [{body}]; }}"
    r = eval_featurescript(script, part_studio_id=PART_STUDIO_ID)
    return r["errors"]


def attribute(error: str, names: list[tuple[str, str]]) -> str | None:
    m = _NAME_RE.search(error)
    if m:
        found = next((g for g in m.groups() if g), None)
        return found
    for name, _ in names:
        if name in error:
            return name
    return None


results: dict[str, dict] = {}
pending = list(CANDIDATES)


def save() -> None:
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n")


def probe(bundle: list[tuple[str, str]]) -> None:
    global pending
    if not bundle:
        return
    errors = run_bundle(bundle)
    if not errors:
        for name, call in bundle:
            results.setdefault(name, {"call": call, "verdict": "PASS (callable)", "errors": []})
        pending = [c for c in pending if c[0] not in {n for n, _ in bundle}]
        save()
        return
    err = errors[0]
    victim = attribute(err, bundle)
    if victim is None or victim not in {n for n, _ in bundle}:
        # Unattributable error (e.g. type error that does not name the call):
        # binary-split the bundle so each half is attributed on its own.
        mid = len(bundle) // 2
        print(f"[split] unattributable: {err[:90]}")
        probe(bundle[:mid])
        probe(bundle[mid:])
        return
    results.setdefault(victim, {"call": dict(bundle)[victim], "verdict": "FAILED", "errors": [err]})
    pending = [c for c in pending if c[0] != victim]
    remaining = [c for c in bundle if c[0] != victim]
    save()
    print(f"[fail] {victim}: {err[:80]}")
    probe(remaining)


print(f"probing {len(CANDIDATES)} candidates against deployed runtime...")
probe(pending)
print("done; results written to", OUT)
