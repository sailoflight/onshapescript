#!/usr/bin/env python3
"""Instantiation-level verification: body errors only surface at instantiation.

The signature layer (featurespecs) accepts bodies that call undefined
functions, annotate undefined types, pass scalars to op* and mix units. This
script proves body errors are exposed when the feature is POSTed into a Part
Studio, and records what status/error the server returns.

Per feature (each gets a fresh Part Studio for isolation):
    upload (GET+POST+featurespecs)  -> signature-layer verdict
    create Part Studio              -> target element
    POST feature (instantiate)      -> body-layer verdict (featureStatus)

Budget guard mirrors run_live_tests.py. 4xx responses (body compile errors
rejected at instantiation) do not count toward the ledger.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from onshape_fs_mcp.client import OnshapeClient, compact_feature_response  # noqa: E402

LIVE_DIR = Path(__file__).resolve().parent
EXPERIMENTS_DIR = LIVE_DIR / "experiments"
FS_ID_PATH = LIVE_DIR / ".fs-id.json"
RESULTS_PATH = LIVE_DIR / "instance-results.json"
MAX_BUDGET = 100

INSTANCE_TESTS = [
    {"file": "01-three-layer.fs", "featureType": "threeLayerProbe",
     "params": {"baseHeight": "18 millimeter"},
     "question": "does a valid body actually instantiate (featureStatus OK), or does qCreatedBy(id) find nothing and error?"},
    {"file": "02-definition-must-be-map.fs", "featureType": "badDefinition",
     "params": {"baseHeight": "18 millimeter"},
     "question": "opExtrude(context, id, 5) accepted at save — what error at instantiation?"},
    {"file": "05-units-mismatch.fs", "featureType": "unitsMismatch",
     "params": {"baseHeight": "18 millimeter"},
     "question": "5*mm + 2 accepted at save — what error at instantiation?"},
    {"file": "08-unknown-function.fs", "featureType": "unknownFunction",
     "params": {"baseHeight": "18 millimeter"},
     "question": "qDoesNotExist in body accepted at save — body compile error at instantiation?"},
    {"file": "15-unknown-type.fs", "featureType": "unknownType",
     "params": {"baseHeight": "18 millimeter"},
     "question": "var x is NotARealType accepted at save — body compile error at instantiation?"},
]


def resolve_version() -> tuple[str, str]:
    trophy = ROOT / "examples" / "branch-cable-trophy" / "branchCableTrophyDisplay.fs"
    match = re.search(r"^FeatureScript (\d+)", trophy.read_text(encoding="utf-8"), re.MULTILINE)
    major = match.group(1)
    return major, f"{major}.0"


def upload_signature(client, did, wid, eid, source, library_version=0):
    path = f"/api/featurestudios/d/{did}/w/{wid}/e/{eid}"
    current = client.request("GET", path)
    try:
        client.request("POST", path, {
            "btType": "BTFeatureStudioContents-2239",
            "contents": source,
            "libraryVersion": library_version,
            "serializationVersion": current.get("serializationVersion"),
            "sourceMicroversion": current.get("sourceMicroversion"),
            "rejectMicroversionSkew": True,
        }, timeout=300)
    except RuntimeError as error:
        return {"ok": False, "detail": f"upload rejected: {str(error)[:200]}"}
    specs = client.request("GET", path + "/featurespecs", timeout=300)
    n = len(specs.get("featureSpecs") or [])
    return {"ok": n > 0, "detail": f"{n} spec(s)", "specs": specs}


def instantiate(client, did, wid, fs_id, microversion, ps_id, feature_type, name, params):
    namespace = f"e{fs_id}::m{microversion}"
    body = {
        "btType": "BTFeatureDefinitionCall-1406",
        "feature": {
            "btType": "BTMFeature-134",
            "featureType": feature_type,
            "name": name,
            "namespace": namespace,
            "parameters": [
                {
                    "btType": "BTMParameterQuantity-147",
                    "parameterId": key,
                    "expression": str(value),
                    "isInteger": False,
                }
                for key, value in params.items()
            ],
            "suppressed": False,
        },
    }
    try:
        response = client.request(
            "POST",
            f"/api/v9/partstudios/d/{did}/w/{wid}/e/{ps_id}/features",
            body,
            timeout=900,
        )
        summary = compact_feature_response(response)
        status = summary["featureStatus"]
        return {"ok": status == "OK", "detail": f"featureStatus={status}"}
    except RuntimeError as error:
        return {"ok": False, "detail": f"rejected at instantiation: {str(error)[:300]}"}


def main() -> int:
    client = OnshapeClient()
    did, wid = client.state["documentId"], client.state["workspaceId"]
    eid = json.loads(FS_ID_PATH.read_text(encoding="utf-8"))["featureStudioId"]
    start = int(client._usage.get("consumed", 0))
    major, version = resolve_version()

    results = []
    for spec in INSTANCE_TESTS:
        spent = int(client._usage.get("consumed", 0)) - start
        if spent >= MAX_BUDGET:
            results.append({"file": spec["file"], "skipped": "budget"})
            continue
        src = (EXPERIMENTS_DIR / spec["file"]).read_text(encoding="utf-8")
        src = src.replace("{{MAJOR}}", major).replace("{{VERSION}}", version)

        sig = upload_signature(client, did, wid, eid, src)
        microversion = None
        if sig.get("specs"):
            microversion = sig["specs"].get("sourceMicroversion")
        # Fresh Part Studio for isolation.
        try:
            ps = client.request(
                "POST", f"/api/partstudios/d/{did}/w/{wid}", {"name": f"instance {spec['file']}"}
            )
            ps_id = ps["id"]
        except RuntimeError as error:
            results.append({"file": spec["file"], "signature": sig,
                            "error": f"create PS failed: {str(error)[:200]}"})
            continue

        if not sig["ok"] or microversion is None:
            results.append({"file": spec["file"], "signature": sig,
                            "note": "signature layer failed; skipped instantiation"})
            continue

        inst = instantiate(client, did, wid, eid, microversion, ps_id,
                           spec["featureType"], f"Inst {spec['file']}", spec["params"])
        results.append({
            "file": spec["file"],
            "question": spec["question"],
            "signatureOk": sig["ok"],
            "instantiation": inst,
        })
        print(f"[{spec['file']}] signature={sig['ok']} instantiation={inst['ok']}")
        print(f"    {spec['question']}")
        print(f"    {inst['detail']}")

    total = int(client._usage.get("consumed", 0)) - start
    outcome = {"startLedger": start, "endLedger": int(client._usage.get("consumed", 0)),
               "callsSpent": total, "budget": MAX_BUDGET, "results": results}
    RESULTS_PATH.write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    print(f"\nspent {total} ledgered calls (budget {MAX_BUDGET})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
