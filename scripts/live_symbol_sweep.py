#!/usr/bin/env python3
"""A-tier existence sweep: constants/types/predicates/non-Context functions in
the vendored FsDoc mirror against the deployed FeatureScript runtime, plus the
cross-version import boundary (the named remaining unknown).

Oracle & cost model (proven by scripts/live_is_probe.py):
- A bundle of VALID expressions compiles clean in 1 eval -> every symbol in it
  exists (PASS). The compiler stops at the first error, so a failing bundle
  reveals ONE symbol per eval; it is dropped and the rest re-evaluated.
- Verdicts from the error text: "Call X(...) does not match X(...)" => X exists
  (arg mismatch); "Function X with N argument(s) not found" => drift candidate
  (the isUvVector signal); "Could not resolve symbol X"/"Variable X not found"
  => MISSING. A bundle reduced to 1 symbol whose error still names nothing
  (e.g. "Attempt to dereference non-container 5") is recorded as RUNTIME-ERROR
  and NOT split further (bounded — an unbounded split recursed forever and 429'd
  the first run).
- Functions taking a Context cannot be dummy-called (Context is server-built),
  so they are excluded from the batch sweep.

Resume & budget (user 2026-08-14): results are SAVED AFTER EVERY RECORD (a
crash keeps everything verified so far), every log line carries a timestamp,
symbols already recorded are skipped on re-run, and --budget 0 (default) sizes
the run from the UNVERIFIED remainder instead of a flat 99 each time.

Rate limit: 2s baseline throttle (matches the is*/gap probes ~1 req/s that ran
clean) plus a single 30s cooldown+retry on 429 (the client already retries
1s/2s/4s internally; a second rapid retry loop just adds to the flood).

Sections in priority order: import boundary (corrected bound-spec probe,
control 3044 -> upper bound 3050), constants, predicates, types, functions.

Results -> docs/verification/live/live-symbol-sweep.json
"""
import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from onshape_fs_mcp.budget import BudgetGuard  # noqa: E402
from onshape_fs_mcp.client import RateLimited  # noqa: E402
from onshape_fs_mcp.operations import eval_featurescript  # noqa: E402

DEFAULT_PART_STUDIO_ID = "cb487527c6e1880fc1e64db8"  # cached live target
EXPERIMENT_FS_ID = "7a4dedcaeb022728fa37722f"        # expendable "FS live verification" studio
INDEX_PATH = ROOT / "reference" / "index" / "fsdoc" / "index.json"
OUT = ROOT / "docs" / "verification" / "live" / "live-symbol-sweep.json"

# Dummy arg expression per FS parameter type. Anything not listed falls back to
# "5" -> "Call X(...) does not match" -> EXISTS (arg mismatch).
DUMMY = {
    "map": "{}",
    "Query": "qEverything(EntityType.BODY)",
    "Vector": "vector(1, 2, 3)",
    "number": "5",
    "Real": "5",
    "integer": "5",
    # A vector, not 5: value-typed predicates that inspect structure
    # (is2dDirection, isLengthVector, isUnitlessVector, ...) do `value[0]` and
    # deref a bare number at runtime ("Attempt to dereference non-container 5").
    "value": "vector(1, 2, 3)",
    "val": "vector(1, 2, 3)",
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

_MISSING = re.compile(r"Could not resolve symbol ([A-Za-z_]\w*)|Variable ([A-Za-z_]\w*) not found")
_DRIFT = re.compile(r"Function ([A-Za-z_]\w*) with \d+ argument\(s\) not found")
_EXISTS = re.compile(r"Call ([A-Za-z_]\w*)\(|Cannot reference function ([A-Za-z_]\w*)|Function ([A-Za-z_]\w*) with")
_RUNTIME = re.compile(r"Attempt to dereference non-container|Runtime exception|Cannot .* non-container")


def ts() -> str:
    return time.strftime("%H:%M:%S")


def rate_limited() -> str | None:
    """Return a reason string if the account is under a long rate-limit hold,
    else None. Onshape's Retry-After landed at 73094s (~20h) on 2026-08-14, so
    a run would only burn futile retries; abort before the first call instead."""
    usage = ROOT / "config" / "api-usage.json"
    try:
        d = json.loads(usage.read_text(encoding="utf-8"))
    except Exception:
        return None
    retry_after = int(d.get("lastRetryAfter") or 0)
    remaining = str(d.get("lastRateLimitRemaining") or "")
    if remaining == "0" and retry_after > 60:
        return (f"Onshape rate-limited: Retry-After {retry_after}s "
                f"(~{retry_after // 3600}h), rate-limit remaining 0")
    return None


def parse_signature(sig: str) -> list[tuple[str, str]]:
    """Return [(param_name, type)] from a signature string. Unparseable -> '?'."""
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
    batch-sweepable)."""
    ps = parse_signature(f.get("signature"))
    if not ps:
        return f"{f['name']}()" if f.get("signature", "").endswith("()") else None
    if any(t == "Context" for _, t in ps):
        return None
    args = [DUMMY.get(t, "5") for _, t in ps]
    return f"{f['name']}({', '.join(args)})"


class Sweep:
    def __init__(self, guard: BudgetGuard, part_studio_id: str, results: dict,
                 out: Path, done: set):
        self.guard = guard
        self.part_studio_id = part_studio_id
        self.results = results
        self.symbols = results["symbols"]
        self.out = out
        self.done = done
        self.budget_stopped = False

    def save(self) -> None:
        """Write current state to disk after every record so a crash, a budget
        stop, or a 429 never loses already-verified symbols."""
        self.results["final"] = self.guard.summary()
        self.results["budgetStopped"] = self.budget_stopped
        self.out.write_text(json.dumps(self.results, ensure_ascii=False, indent=1) + "\n")

    def run_bundle(self, section: str, names: list[tuple[str, str]]) -> list[str]:
        body = ", ".join(expr for _, expr in names)
        script = f"function(context is Context, id is Id) {{ return [{body}]; }}"
        time.sleep(2.0)  # global throttle; matches the is*/gap probes ~1 req/s
        # NO 429 retry: the client raises RateLimited immediately with the wait
        # time; main() writes it to the results and exits. Never skip onward.
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
        print(f"[{ts()}] [{verdict}] {name}: {(err or '')[:110]}", flush=True)
        self.save()

    def probe(self, section: str, bundle: list[tuple[str, str]]) -> None:
        if not bundle:
            return
        if self.guard.exceeded():
            self.budget_stopped = True
            print(f"[{ts()}] [budget] spent {self.guard.spent}/{self.guard.budget}; "
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
                # Single call whose error names no symbol (e.g. a runtime error).
                # Record and STOP — never recurse on a 1-element bundle (the
                # first run did and 429'd in an infinite split).
                self.record(bundle[0][0], bundle[0][1], self.verdict(err), err)
                return
            mid = len(bundle) // 2
            print(f"[{ts()}] [split] {section} unattributable: {err[:90]}", flush=True)
            self.probe(section, bundle[:mid])
            self.probe(section, bundle[mid:])
            return
        self.record(victim, dict(bundle)[victim], self.verdict(err), err)
        self.probe(section, [b for b in bundle if b[0] != victim])

    def sweep(self, section: str, names: list[tuple[str, str]], size: int) -> None:
        todo = [(n, e) for n, e in names if n not in self.done]
        if not todo:
            print(f"[{ts()}] --- {section}: all verified, skipping", flush=True)
            return
        print(f"[{ts()}] --- {section}: {len(todo)} unverified @ {size}/bundle "
              f"(spent {self.guard.spent}/{self.guard.budget})", flush=True)
        for i in range(0, len(todo), size):
            self.probe(section, todo[i:i + size])
            if self.guard.exceeded():
                break


def import_boundary(guard: BudgetGuard, did: str, wid: str) -> dict:
    """Cross-version import probes with the CORRECTED precondition (annotation +
    bound spec, mirroring experiments/01-three-layer.fs exactly — a bare
    isLength yields specCount 0 for any version, so the earlier runs' 0-spec
    results could not discriminate acceptance). Always re-probes the CONTROL
    3044 (the deployed runtime — it cannot be rejected, so 1 spec confirms the
    probe now emits specs) before probing the upper bound 3050."""
    def probe(version: str) -> dict:
        source = (
            f"FeatureScript {version};\n"
            f'import(path : "onshape/std/geometry.fs", version : "{version}.0");\n\n'
            'annotation { "Feature Type Name" : "ImportBoundaryProbe" }\n'
            "export const importBoundaryProbe = defineFeature(function(context is Context, id is Id, definition is map)\n"
            "    precondition\n"
            "    {\n"
            '        annotation { "Name" : "Size" }\n'
            "        isLength(definition.size, { (millimeter) : [14, 18, 28] } as LengthBoundSpec);\n"
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
        time.sleep(2.0)
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
        except RateLimited:
            raise  # never swallow a rate limit; main() writes it and exits
        except RuntimeError as exc:
            return {"declared": version, "postError": str(exc)[:150]}
        time.sleep(2.0)
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

    # Hard budget: each version probe costs 3 ledgered calls (GET+POST+
    # featurespecs); never start one unless all 3 fit in the remaining budget.
    def afford() -> bool:
        return guard.remaining >= 3

    results = {}
    if afford():
        control = probe("3044")                     # control: deployed runtime, must accept
        results["3044"] = control
        print(f"[{ts()}] [import:3044] {json.dumps(control)[:160]}", flush=True)
        if control.get("compile") == "ok" and afford():
            results["3050"] = probe("3050")         # upper bound: expect rejection
            print(f"[{ts()}] [import:3050] {json.dumps(results['3050'])[:160]}", flush=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=0,
                        help="max ledgered calls; 0 (default) sizes from the "
                             "unverified remainder instead of a flat 99")
    parser.add_argument("--part-studio-id", default=DEFAULT_PART_STUDIO_ID)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    rl = rate_limited()
    if rl:
        print(f"[{ts()}] aborting before any call: {rl}", flush=True)
        return 0

    # Resume: keep everything already verified; the budget then only covers the
    # remainder, so a re-run after progress is cheap instead of 99 each time.
    prev: dict = {}
    if args.out.exists():
        try:
            prev = json.loads(args.out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    symbols = prev.get("symbols", {})
    done = set(symbols)

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

    if args.budget <= 0:
        unv = {
            "constants": sum(1 for c in consts if c not in done),
            "predicates": sum(1 for p in preds if p not in done),
            "types": sum(1 for t in types if t != "Context" and t not in done),
            "functions": sum(1 for n in no_ctx if n not in done),
        }
        auto = 6  # import control + boundary
        auto += math.ceil(unv["constants"] / 12)
        auto += math.ceil(unv["predicates"] / 8)
        auto += math.ceil(unv["types"] / 10) + 1  # + feasibility probe
        auto += math.ceil(unv["functions"] / 5)
        args.budget = min(99, int(auto * 1.4) + 8)
        print(f"[{ts()}] auto budget: {auto} est -> {args.budget} "
              f"(unverified {unv})", flush=True)

    guard = BudgetGuard(args.budget, "symbol existence sweep")
    did, wid = guard.client.state["documentId"], guard.client.state["workspaceId"]
    print(f"[{ts()}] preflight OK, annual remaining "
          f"{guard.summary()['annualRemaining']}; import boundary first",
          flush=True)

    results = {"budget": {}, "importBoundary": prev.get("importBoundary", {}),
               "symbols": symbols}
    sweep = None
    try:
        guard = BudgetGuard(args.budget, "symbol existence sweep")
        did, wid = guard.client.state["documentId"], guard.client.state["workspaceId"]
        print(f"[{ts()}] preflight OK, annual remaining "
              f"{guard.summary()['annualRemaining']}; import boundary first",
              flush=True)
        results["budget"] = guard.summary()
        sweep = Sweep(guard, args.part_studio_id, results, args.out, done)

        results["importBoundary"].update(import_boundary(guard, did, wid))
        sweep.save()

        sweep.sweep("constants", [(c, c) for c in consts], 12)
        sweep.sweep("predicates", [(p, gen_call(preds[p])) for p in sorted(preds)], 8)
        # types: bare type names are value expressions if the runtime allows it.
        if "Context" not in done and not guard.exceeded():
            sweep.probe("types-feasibility", [("Context", "Context")])
        if not guard.exceeded() and sweep.symbols.get("Context", {}).get("verdict") == "PASS":
            sweep.sweep("types", [(t, t) for t in types if t != "Context"], 10)
        elif not guard.exceeded():
            print(f"[{ts()}] --- types skipped: bare type names are not value expressions", flush=True)

        sweep.sweep("functions", [(n, gen_call(all_callable[n])) for n in sorted(no_ctx)], 5)

        sweep.save()
        verdicts = {}
        for r in results["symbols"].values():
            v = r["verdict"]
            verdicts[v] = verdicts.get(v, 0) + 1
        print(f"[{ts()}] spent {guard.spent}/{guard.budget} ledgered calls; "
              f"total symbols verified {len(results['symbols'])}, verdicts={verdicts}")
        print(f"[{ts()}] wrote {args.out}")
        return 0
    except RateLimited as exc:
        # 429 is NEVER retried and never skipped: record the wait time, save,
        # and exit. Resume later once the limit clears.
        results["error"] = str(exc)
        if sweep is not None:
            try:
                sweep.save()
            except Exception:
                pass
        print(f"[{ts()}] [rate-limited] {exc}", flush=True)
        print(f"[{ts()}] exiting now — no retry, no skip; results preserved at {args.out}",
              flush=True)
        return 1
    except Exception as exc:
        results["error"] = f"{type(exc).__name__}: {exc}"
        if sweep is not None:
            try:
                sweep.save()
            except Exception:
                pass
        print(f"[{ts()}] [error] {results['error']}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
