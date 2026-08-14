#!/usr/bin/env python3
"""Live existence probe for every is* predicate in the vendored FsDoc mirror,
plus the 4 the mirror omits (isQuery/isString/isArray/isType), against the
deployed FeatureScript runtime (eval libraryVersion).

Cost: (1 + number_of_failures) evals, one ledger call each. The compiler stops
at the first error, so bundling reveals ONE failure per eval; each failure is
dropped and the rest re-evaluated until the bundle is clean.

Budget: gated by onshape_fs_mcp.budget.BudgetGuard — preflighted against the
remaining annual quota, `--budget` overrides the per-run ceiling (default 40:
33 candidates x 1 call + margin for splits), and the run stops as soon as the
budget is spent, writing whatever it has verified. Pass `--part-studio-id`
explicitly: without it each eval re-resolves the target (~10 ledger calls),
the exact trap that burned ~126 calls on the first probe run.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from onshape_fs_mcp.budget import BudgetGuard, live_api_enabled  # noqa: E402
from onshape_fs_mcp.client import rate_limit_reason  # noqa: E402
from onshape_fs_mcp.operations import eval_featurescript  # noqa: E402

DEFAULT_PART_STUDIO_ID = "cb487527c6e1880fc1e64db8"  # cached live target

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


def attribute(error: str, names: list[tuple[str, str]]) -> str | None:
    m = _NAME_RE.search(error)
    if m:
        found = next((g for g in m.groups() if g), None)
        return found
    for name, _ in names:
        if name in error:
            return name
    return None


class Probe:
    def __init__(self, guard: BudgetGuard, part_studio_id: str, out: Path):
        self.guard = guard
        self.part_studio_id = part_studio_id
        self.out = out
        self.results: dict[str, dict] = {}
        self.pending = list(CANDIDATES)
        self.budget_stopped = False

    def save(self) -> None:
        self.out.write_text(
            json.dumps(
                {"summary": self.guard.summary(), "budgetStopped": self.budget_stopped,
                 "results": self.results},
                ensure_ascii=False, indent=1,
            ) + "\n"
        )

    def run_bundle(self, names: list[tuple[str, str]]) -> list[str]:
        body = ", ".join(call for _, call in names)
        script = f"function(context is Context, id is Id) {{ return [{body}]; }}"
        r = eval_featurescript(script, part_studio_id=self.part_studio_id,
                               client=self.guard.client)
        return r["errors"]

    def probe(self, bundle: list[tuple[str, str]]) -> None:
        if not bundle:
            return
        if self.guard.exceeded():
            self.budget_stopped = True
            print(f"[budget] spent {self.guard.spent}/{self.guard.budget}; "
                  f"stopping with {len(self.pending)} candidates unverified")
            self.save()
            return
        errors = self.run_bundle(bundle)
        if not errors:
            for name, call in bundle:
                self.results.setdefault(
                    name, {"call": call, "verdict": "PASS (callable)", "errors": []})
            self.pending = [c for c in self.pending
                            if c[0] not in {n for n, _ in bundle}]
            self.save()
            return
        err = errors[0]
        victim = attribute(err, bundle)
        if victim is None or victim not in {n for n, _ in bundle}:
            # Unattributable error (e.g. type error that does not name the call):
            # binary-split the bundle so each half is attributed on its own.
            mid = len(bundle) // 2
            print(f"[split] unattributable: {err[:90]}")
            self.probe(bundle[:mid])
            self.probe(bundle[mid:])
            return
        self.results.setdefault(
            victim, {"call": dict(bundle)[victim], "verdict": "FAILED", "errors": [err]})
        self.pending = [c for c in self.pending if c[0] != victim]
        self.save()
        print(f"[fail] {victim}: {err[:80]}")
        self.probe([c for c in bundle if c[0] != victim])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=40,
                        help="max ledgered API calls this run (default 40)")
    parser.add_argument("--part-studio-id", default=DEFAULT_PART_STUDIO_ID,
                        help="target Part Studio for eval (default cached live id)")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs" / "verification" / "live" / "live-is-predicates.json",
                        help="where to write results")
    args = parser.parse_args()

    if not live_api_enabled():
        print("aborting before any call: LIVE_API_ENABLED is not set to 1 "
              "(real API requests must be explicit)")
        return 0

    rl = rate_limit_reason()
    if rl:
        print(f"aborting before any call: {rl}")
        return 0

    guard = BudgetGuard(args.budget, "is* predicate probe")
    print(f"probing {len(CANDIDATES)} candidates against deployed runtime "
          f"(budget {args.budget} ledgered calls, preflight OK, "
          f"annual remaining {guard.summary()['annualRemaining']})...")
    probe = Probe(guard, args.part_studio_id, args.out)
    probe.probe(probe.pending)
    summary = guard.summary()
    print(f"done: {len(probe.results)} verified, {summary['spent']} ledgered calls "
          f"spent of budget {summary['budget']}; results -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
