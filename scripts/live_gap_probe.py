#!/usr/bin/env python3
"""Close the highest-value unverified doc gaps in a fixed ledger budget.

Covers the audit's unverified items (docs/verification/live/README.md + the
llm-experience docs). Every section logs its real ledger cost and the run stops
at --budget (default 22), gated by onshape_fs_mcp.budget.BudgetGuard.

  A. quick-reference language features via eval      (~3 calls)
     ~ concat, unit arithmetic, sin(degree), for-in, while, lambda, map
     iteration, Query type-check — all never individually live-tested.
  B. render_preview end-to-end                        (1 call)
     The only tool with zero real-call history; proves a shaded view renders.
  D. REST read endpoints never called live            (3 calls)
     getDocument / getDocumentVersions / getDocumentWorkspaces on the known doc.
     Runs BEFORE the experimental import probes so the guaranteed-value reads
     always complete even when the budget runs out mid-section-C.
  C. cross-version import boundary (upload probes)    (~3 probes x 3 calls)
     Control (3029) -> 3044 -> 3050, or a midpoint if 3044 fails, against the
     expendable experiment Feature Studio. Each probe uploads a feature whose
     body READS definition.size so a successful import emits exactly 1 spec —
     an empty body yields 0 specs for any version (gap-probe 2026-08-14) and
     cannot detect the boundary.

Results -> docs/verification/live/gap-probe-results.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from onshape_fs_mcp.budget import BudgetGuard  # noqa: E402
from onshape_fs_mcp.operations import (  # noqa: E402
    eval_featurescript,
    render_preview,
)

EXPERIMENT_FS_ID = "7a4dedcaeb022728fa37722f"  # expendable "FS live verification" studio
PART_STUDIO_ID = "cb487527c6e1880fc1e64db8"    # trophy model part studio (from state)
OUT = ROOT / "docs" / "verification" / "live" / "gap-probe-results.json"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=22,
                        help="max ledgered API calls this run (default 22)")
    args = parser.parse_args()

    guard = BudgetGuard(args.budget, "gap-closure probe")
    client = guard.client
    did, wid = client.state["documentId"], client.state["workspaceId"]
    results: dict = {"budget": guard.summary()}
    spent_at = {}
    last = guard.spent

    def log(section: str, payload: dict) -> None:
        nonlocal last
        now = guard.spent
        payload["ledgerCalls"] = now - last
        last = now
        results[section] = payload
        print(f"[{section}] {json.dumps(payload, ensure_ascii=False)[:220]}")

    # ---- A. Language features via eval (1 call each) ---------------------
    lang_scripts = {
        "concat_units_trig": (
            'function(context is Context, id is Id) { return ["part" ~ 3, '
            '(5 * millimeter) / 2, sin(90 * degree), 10 * inch + 1 * inch]; }'
        ),
        "control_flow": (
            "function(context is Context, id is Id) {\n"
            "    var s = 0;\n"
            "    for (var x in [1, 2, 3]) { s = s + x; }\n"
            "    var i = 0; while (i < 3) { s = s + i; i = i + 1; }\n"
            "    var acc = 0; for (var k, v in { a : 1, b : 2 }) { acc = acc + v; }\n"
            "    var double = function(x) { return x * 2; };\n"
            "    return [s, double(21), acc];\n"
            "}"
        ),
        "query_typecheck": (
            "function(context is Context, id is Id) {\n"
            "    var q = qCreatedBy(id, EntityType.BODY);\n"
            "    return [q is Query, qNthElement(q, 0)];\n"
            "}"
        ),
    }
    for name, script in lang_scripts.items():
        r = eval_featurescript(script, part_studio_id=PART_STUDIO_ID, client=client)
        log(f"lang:{name}", {"errors": r["errors"], "result": r["result"],
                             "deployedVersion": r["featureScriptVersion"]})
        if guard.exceeded():
            break

    # ---- B. render_preview end-to-end (1 call) ---------------------------
    if not guard.exceeded():
        try:
            r = render_preview("iso", 300, 300, save=False,
                               part_studio_id=PART_STUDIO_ID, client=client)
            log("render", {k: r[k] for k in ("view", "width", "height", "mediaType",
                                             "byteCount", "sha256")})
        except RuntimeError as exc:
            log("render", {"error": str(exc)[:150]})

    # ---- D. REST read endpoints never called live ------------------------
    # Cheap, guaranteed-value reads. Kept before the experimental import probes
    # so they always complete within budget.
    for label, path in (
        ("rest:getDocument", f"/api/documents/{did}"),
        ("rest:getDocumentVersions", f"/api/documents/d/{did}/versions"),
        ("rest:getDocumentWorkspaces", f"/api/documents/d/{did}/workspaces"),
    ):
        if guard.exceeded():
            break
        try:
            body = client.request("GET", path, timeout=60)
            count = len(body) if isinstance(body, list) else None
            keys = sorted(body.keys())[:8] if isinstance(body, dict) else None
            log(label, {"status": "ok", "topKeys": keys, "listCount": count})
        except RuntimeError as exc:
            log(label, {"status": "error", "error": str(exc)[:120]})

    # ---- C. Cross-version import boundary (upload probes) ----------------
    def import_probe(version: str) -> dict:
        # The body must READ definition.size: featurespecs are emitted per
        # definition.* field the body uses (gap-probe 2026-08-14). A feature
        # with an empty body — or a body that never reads `definition` — yields
        # 0 specs for any import version, indistinguishable from a version-
        # boundary rejection. Mirror the proven 1-spec shape of
        # experiments/01-three-layer.fs so a rejected import is the ONLY way
        # to get specCount 0 (plus errorType/errorMessages).
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
        fs_path = f"/api/featurestudios/d/{did}/w/{wid}/e/{EXPERIMENT_FS_ID}"
        current = client.request("GET", fs_path)
        try:
            updated = client.request(
                "POST", fs_path,
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
        specs = client.request("GET", fs_path + "/featurespecs", timeout=300)
        feature_specs = specs.get("featureSpecs", [])
        language_version = None
        for item in feature_specs:
            language_version = (item.get("message") or {}).get("languageVersion") or language_version
        return {
            "declared": version,
            "specCount": len(feature_specs),
            "compile": "ok" if feature_specs else "empty",
            "errorType": specs.get("errorType"),
            "errorMessages": specs.get("errorMessages"),
            "languageVersion": language_version,
            "microversionSkew": updated.get("microversionSkew"),
        }

    if not guard.exceeded():
        log("import:3029", import_probe("3029"))
    if not guard.exceeded():
        log("import:3044", import_probe("3044"))
    if not guard.exceeded():
        c3044 = results.get("import:3044", {})
        if c3044.get("compile") == "ok":
            log("import:3050", import_probe("3050"))     # expect rejection -> upper bound
        else:
            log("import:3035", import_probe("3035"))     # bisect the failure

    # ---- write + summarize ------------------------------------------------
    results["final"] = guard.summary()
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n")
    print(f"\nwrote {OUT}")
    print(f"spent {guard.spent} of budget {guard.budget} ledgered calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
