#!/usr/bin/env python3
"""A-tier existence sweep: every constants/types/predicates/non-Context function
in the vendored FsDoc mirror against the deployed FeatureScript runtime, plus
the cross-version import boundary (the named remaining unknown).

Oracle & cost model (proven by scripts/live_is_probe.py):
- A bundle of VALID expressions compiles clean in 1 eval -> every symbol in it
  exists (PASS). The compiler stops at the first error, so a failing bundle
  reveals ONE symbol per eval; it is dropped and the rest re-evaluated until
  the bundle is clean.
- Verdicts from the error text: "Call X(...) does not match X(...)" => X exists
  (my arg was wrong); "Function X with N argument(s) not found" => drift
  candidate (the mirror documents X but the runtime has no such overload — the
  isUvVector signal); "Could not resolve symbol X" / "Variable X not found" =>
  MISSING.
- Functions taking a Context cannot be dummy-called (Context is server-built),
  so they are excluded from the batch sweep (the zero-cost mirror already
  validates them; they are not batch-sweepable by eval).

Sections run in priority order and the run stops at --budget (default 99) via
onshape_fs_mcp.budget.BudgetGuard:
  1. import boundary  (upload probes, ~9 calls) — the named unknown
  2. constants        (129 bare values, bundles of 12)
  3. predicates       (115 arity-matched calls, bundles of 8)
  4. types            (270 bare names; feasibility probe decides)
  5. functions        (non-Context, arity+type-matched calls, bundles of 5)

Results -> docs/verification/live/live-symbol-sweep.json
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from onshape_fs_mcp.budget import BudgetGuard  # noqa: E402
from onshape_fs_mcp.operations import eval_featurescript  # noqa: E402

DEFAULT_PART_STUDIO_ID = "cb487527c6e1880fc1e64db8"  # cached live target
EXPERIMENT_FS_ID = "7a4dedcaeb022728fa37722f"        # expendable "FS live verification" studio
INDEX_PATH = ROOT / "reference" / "index" / "fsdoc" / "index.json"
OUT = ROOT / "docs" / "verification" / "live" / "live-symbol-sweep.json"

# Dummy arg expression per FS parameter type. Anything not listed falls back to
# "5" -> "Call X(...) does not match" -> EXISTS (arg mismatch), still confirms
# existence, at the cost of one split per wrong call.
DUMMY = {
    "map": "{}",
    "Query": "qEverything(EntityType.BODY)",
    "Vector": "vector(1, 2, 3)",
    "number": "5",
    "Real": "5",
    "integer": "5",
    "value": "5",
    "val": "5",
    "string": "\"x\"",
    "Id": "\"x\"",
    "boolean": "true",
    "array": "[1]",
    "ValueWithUnits": "1 * millimeter",
    "length": "1 * millimeter",
    "angle": "1 * degree",
    "Plane": "plane(vector(1, 2, 3), vector(0, 0, 1))",
    "EntityType": "EntityType.BODY",
    "BodyType": "BodyType.SOLID",
}

# Error-text -> verdict. Order matters: the specific "with N arg(s) not found"
# (drift flag) must beat the generic "Function X with" (exists).
_MISSING = re.compile(r"Could not resolve symbol ([A-Za-z_]\w*)|Variable ([A-Za-z_]\w*) not found")
_DRIFT = re.compile(r"Function ([A-Za-z_]\w*) with \d+ argument\(s\) not found")
_EXISTS = re.compile(r"Call ([A-Za-z_]\w*)\(|Cannot reference function ([A-Za-z_]\w*)|Function ([A-Za-z_]\w*) with")
_RUNTIME = re.compile(r"Attempt to dereference non-container|Runtime exception|Cannot .* non-container")
_NAME = re.compile(r"([A-Za-z_]\w*)")


def parse_signature(sig: str) -> list[tuple[str, str]]:
    """Return [(param_name, type)] from a signature string like
    'f(a is number, b is map @optional)'.  Unparseable params get type '?'."""
    m = re.match(r"[\w.]+\s*\((.*)\)\s*$", sig or "")
    if not m or not (m.group(1) or "").strip():
        return []
    out = []
    for p in m.group(1).split(","):
        p = p.strip()
        if not p:
            continue
        mm = re.match(r"(\w+)\s+is\s+([\w.]+)", p)
        out.append((mm.group(1), mm.group(2)) if mm else (p, "?"))
    return out


def gen_call(f: dict) -> str | None:
    """A valid-ish call expression for f, or None if f takes a Context (not
    batch-sweepable: Context is server-built)."""
    ps = parse_signature(f.get("signature"))
    if not ps:
        return f"{f['name']}()" if f.get("signature", "").endswith("()") else None
    if any(t == "Context" for _, t in ps):
        return None
    args = [DUMMY.get(t, "5") for _, t in ps]
    return f"{f['name']}({', '.join(args)})"


class Sweep:
    def __init__(self, guard: BudgetGuard, part_studio_id: str, results: dict, out: Path):
        self.guard = guard
        self.part_studio_id = part_studio_id
        self.results = results
        self.symbols = results["symbols"]
        self.out = out
        self.budget_stopped = False

    def save(self) -> None:
        """Write current state to disk. Called after every record so a crash or
        a budget stop never loses verified symbols (the first run crashed and
        lost all 61 calls' results — it only wrote at the end)."""
        self.results["final"] = self.guard.summary()
        self.results["budgetStopped"] = self.budget_stopped
        self.out.write_text(json.dumps(self.results, ensure_ascii=False, indent=1) + "\n")

    def run_bundle(self, section: str, names: list[tuple[str, str]]) -> list[str]:
        body = ", ".join(expr for _, expr in names)
        script = f"function(context is Context, id is Id) {{ return [{body}]; }}"
        time.sleep(0.2)  # stay under the Onshape rate limit (429 in the first run)
        r = eval_featurescript(script, part_studio_id=self.part_studio_id,
                               client=self.guard.client)
        return r["errors"]

    def attribute(self, err: str, names: list[tuple[str, str]]) -> str | None:
        pool = {n for n, _ in names}
        for pat in (_MISSING, _DRIFT, _EXISTS):
            m = pat.search(err)
            if m:
                found = next((g for g in m.groups() if g), None)
                if found and found in pool:
                    return found
        for n, _ in names:
            if re.search(rf"\b{re.escape(n)}\b", err):
                return n
        return None

    def verdict(self, err: str) -> str:
        if _MISSING.search(err):
            return "MISSING"
        if _DRIFT.search(err):
            return "DRIFT-CANDIDATE"
        if _RUNTIME.search(err):
            return "RUNTIME-ERROR"
        return "EXISTS (arg mismatch)"

    def record(self, name, call, verdict, err) -> None:
        self.symbols[name] = {"call": call, "verdict": verdict,
                              "error": err[:220] if err else None}
        print(f"[{verdict}] {name}: {(err or '')[:110]}", flush=True)
        self.save()

    def probe(self, section: str, bundle: list[tuple[str, str]]) -> None:
        if not bundle:
            return
        if self.guard.exceeded():
            self.budget_stopped = True
            print(f"[budget] spent {self.guard.spent}/{self.guard.budget}; "
                  f"{section} left {len(bundle)} unverified", flush=True)
            self.save()
            return
        errors = self.run_bundle(section, bundle)
        if not errors:
            for name, call in bundle:
                self.record(name, call, "PASS", "")
            return
        err = errors[0]
        victim = self.attribute(err, bundle)
        if victim is None:
            if len(bundle) == 1:
                # A single call that still names no symbol (e.g. a runtime error
                # like "Attempt to dereference non-container 5"). Record it and
                # STOP — the first run recursed forever here (bundle[0:] == the
                # same bundle) and 429'd. The symbol is known (it is the bundle)
                # and the error text says why it could not be verified.
                self.record(bundle[0][0], bundle[0][1], self.verdict(err), err)
                return
            mid = len(bundle) // 2
            print(f"[split] {section} unattributable: {err[:90]}", flush=True)
            self.probe(section, bundle[:mid])
            self.probe(section, bundle[mid:])
            return
        self.record(victim, dict(bundle)[victim], self.verdict(err), err)
        self.probe(section, [b for b in bundle if b[0] != victim])

    def sweep(self, section: str, names: list[tuple[str, str]], size: int) -> None:
        if self.guard.exceeded():
            self.budget_stopped = True
            return
        print(f"--- {section}: {len(names)} symbols @ {size}/bundle "
              f"(spent {self.guard.spent}/{self.guard.budget})")
        for i in range(0, len(names), size):
            self.probe(section, names[i:i + size])
            if self.guard.exceeded():
                break


def import_boundary(guard: BudgetGuard, did: str, wid: str) -> dict:
    """Cross-version import probes (fixed definition-reading body, see
    docs/verification/live/experiments/import-boundary/)."""
    def probe(version: str) -> dict:
        source = (
            f"FeatureScript {version};\n"
            f'import(path : "onshape/std/geometry.fs", version : "{version}.0");\n\n'
            'annotation { "Feature Type Name" : "ImportBoundaryProbe" }\n'
            "export const importBoundaryProbe = defineFeature(function(context is Context, id is Id, definition is map)\n"
            "    precondition\n"
            "    {\n"
            "        isLength(definition.size);\n"
            "    }\n"
            "    {\n"
            "        opExtrude(context, id + \"extrude\", {\n"
            '                "entities" : qCreatedBy(id, EntityType.BODY),\n'
            '                "direction" : Z_DIRECTION,\n'
            '                "endBound" : BoundingType.BLIND,\n'
            '                "endDepth" : definition.size\n'
            "            });\n"
            "    }\n"
        )
        path = f"/api/featurestudios/d/{did}/w/{wid}/e/{EXPERIMENT_FS_ID}"
        current = guard.client.request("GET", path)
        try:
            updated = guard.client.request(
                "POST", path,
                {
                    "btType": "BTFeatureStudioContents-2239",
                    "contents": source,
                    "libraryVersion": current.get("libraryVersion", 0),
                    "serializationVersion": current.get("serializationVersion"),
                    "sourceMicroversion": current.get("sourceMicroversion"),
                    "rejectMicroversionSkew": True,
                },
                timeout=300,
            )
        except RuntimeError as exc:
            return {"declared": version, "postError": str(exc)[:150]}
        specs = guard.client.request("GET", path + "/featurespecs", timeout=300)
        feature_specs = specs.get("featureSpecs", [])
        lang_version = None
        for item in feature_specs:
            lang_version = (item.get("message") or {}).get("languageVersion") or lang_version
        return {
            "declared": version, "specCount": len(feature_specs),
            "compile": "ok" if feature_specs else "empty",
            "errorType": specs.get("errorType"),
            "errorMessages": specs.get("errorMessages"),
            "languageVersion": lang_version,
            "microversionSkew": updated.get("microversionSkew"),
        }

    results = {}
    for version in ("3029", "3044"):
        if guard.exceeded():
            break
        results[version] = probe(version)
        print(f"[import:{version}] {json.dumps(results[version])[:160]}")
    if not guard.exceeded():
        if results.get("3044", {}).get("compile") == "ok":
            results["3050"] = probe("3050")   # expect rejection -> upper bound
        else:
            results["3035"] = probe("3035")   # bisect the failure
        print(f"[import:bisect] {json.dumps(results[list(results)[-1]])[:160]}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=99,
                        help="max ledgered API calls this run (default 99)")
    parser.add_argument("--part-studio-id", default=DEFAULT_PART_STUDIO_ID)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    guard = BudgetGuard(args.budget, "symbol existence sweep")
    client = guard.client
    did, wid = client.state["documentId"], client.state["workspaceId"]

    idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    funcs: dict[str, dict] = {}
    for f in idx["functions"]:
        funcs.setdefault(f["name"], f)
    preds: dict[str, dict] = {}
    for p in idx["predicates"]:
        preds.setdefault(p["name"], p)
    consts = sorted({c["name"] for c in idx["constants"]})
    types = sorted({t["name"] for t in idx["types"]})

    all_callable = {**funcs, **preds}
    no_ctx = [n for n, f in all_callable.items() if gen_call(f) is not None]
    print(f"sweeping {len(consts)} constants, {len(types)} types, "
          f"{len(preds)} predicates, {len(no_ctx)}/{len(all_callable)} "
          f"callables (no Context); import boundary first. "
          f"preflight OK, annual remaining {guard.summary()['annualRemaining']}")

    results = {"budget": guard.summary(), "importBoundary": {}, "symbols": {}}
    sweep = Sweep(guard, args.part_studio_id, results, args.out)

    results["importBoundary"] = import_boundary(guard, did, wid)
    sweep.save()  # the import boundary is the named unknown; never lose it

    sweep.sweep("constants", [(c, c) for c in consts], 12)
    sweep.sweep("predicates", [(p, gen_call(preds[p])) for p in sorted(preds)], 8)
    # types: bare type names are value expressions if the runtime allows it.
    if not guard.exceeded():
        sweep.probe("types-feasibility", [("Context", "Context")])
    if not guard.exceeded() and sweep.symbols.get("Context", {}).get("verdict") == "PASS":
        sweep.sweep("types", [(t, t) for t in types if t != "Context"], 10)
    elif not guard.exceeded():
        print("--- types skipped: bare type names are not value expressions", flush=True)

    sweep.sweep("functions", [(n, gen_call(all_callable[n])) for n in sorted(no_ctx)], 5)

    sweep.save()
    verdicts = {}
    for r in results["symbols"].values():
        v = r["verdict"]
        verdicts[v] = verdicts.get(v, 0) + 1
    print(f"\nspent {guard.spent}/{guard.budget} ledgered calls; verdicts={verdicts}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
