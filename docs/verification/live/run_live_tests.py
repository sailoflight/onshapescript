#!/usr/bin/env python3
"""Live FeatureScript language verification against the real Onshape server.

Compiles one focused experiment file at a time in an isolated experiment
Feature Studio and records whether the real compiler accepts or rejects each
construct, plus what the error says. This turns the zero-cost corpus checks
(reference vs mirror) into verified language facts.

Budget guard: the annual quota ledger (config/api-usage.json) counts 2xx/3xx
only. This run stops once it has spent MAX_BUDGET calls beyond its start point.
A 4xx upload (e.g. a parse error) costs zero ledger calls.

Creates one dedicated "FS live verification" Feature Studio on first run and
reuses it (id cached in docs/verification/live/.fs-id.json). The configured
trophy Feature Studio is never touched.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root: .../docs/verification/live -> .../docs/verification -> .../docs -> root
sys.path.insert(0, str(ROOT))

from onshape_fs_mcp.client import OnshapeClient, load_json  # noqa: E402

LIVE_DIR = Path(__file__).resolve().parent
EXPERIMENTS_DIR = LIVE_DIR / "experiments"
MANIFEST_PATH = LIVE_DIR / "experiments.json"
RESULTS_PATH = LIVE_DIR / "results.json"
FS_ID_PATH = LIVE_DIR / ".fs-id.json"
EXPERIMENT_FS_NAME = "FS live verification"

# This run may spend at most MAX_BUDGET ledgered API calls (2xx/3xx).
# First run: 100 (exhausted diagnosing syntax). Then +50 authorized for the
# corrected-form rerun. Set to 50 (15 experiments x ~3 calls).
MAX_BUDGET = 50


def resolve_version_from_trophy() -> tuple[str, str]:
    """Read the FeatureScript version the trophy file declares in its header.

    The API reports libraryVersion=0 for every Feature Studio; the version is
    declared by the uploaded .fs content itself. The trophy file is a known-good
    compile against this workspace, so its header version is the reference.
    """
    trophy = ROOT / "examples/branch-cable-trophy/branchCableTrophyDisplay.fs"
    match = re.search(r"^FeatureScript (\d+)", trophy.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not parse FeatureScript version from {trophy}")
    major = match.group(1)
    return major, f"{major}.0"


def upload_and_compile(
    client: OnshapeClient,
    did: str,
    wid: str,
    eid: str,
    source: str,
    library_version: int,
) -> dict:
    """Upload one experiment's source and read the compile verdict.

    Returns {'ok': bool, 'detail': str}. Compile errors surface either as a 4xx
    on the upload (parse errors) or as errorType/errorMessages on the
    featurespecs readback (semantic/version errors).
    """
    path = f"/api/featurestudios/d/{did}/w/{wid}/e/{eid}"
    current = client.request("GET", path)
    try:
        client.request(
            "POST",
            path,
            {
                "btType": "BTFeatureStudioContents-2239",
                "contents": source,
                "libraryVersion": library_version,
                "serializationVersion": current.get("serializationVersion"),
                "sourceMicroversion": current.get("sourceMicroversion"),
                "rejectMicroversionSkew": True,
            },
            timeout=300,
        )
    except RuntimeError as error:
        message = str(error)
        return {"ok": False, "detail": f"upload rejected: {message}"}
    specs = client.request("GET", path + "/featurespecs", timeout=300)
    error_type = specs.get("errorType")
    error_messages = specs.get("errorMessages") or []
    if error_type or error_messages:
        detail = f"errorType={error_type}"
        if error_messages:
            detail += " | " + "; ".join(str(m) for m in error_messages)
        return {"ok": False, "detail": detail}
    # Present but no feature specs is also a compile failure.
    if not specs.get("featureSpecs"):
        return {"ok": False, "detail": f"no featureSpecs returned ({json.dumps(specs)[:200]})"}
    return {"ok": True, "detail": f"{len(specs['featureSpecs'])} feature spec(s)"}


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    client = OnshapeClient()
    did, wid = client.state["documentId"], client.state["workspaceId"]
    start_consumed = int(client._usage.get("consumed", 0))

    # Reuse or create the isolated experiment Feature Studio.
    eid = None
    if FS_ID_PATH.is_file():
        cached = json.loads(FS_ID_PATH.read_text(encoding="utf-8"))
        if cached.get("documentId") == did:
            eid = cached.get("featureStudioId")
    if eid is None:
        created = client.request(
            "POST", f"/api/featurestudios/d/{did}/w/{wid}", {"name": EXPERIMENT_FS_NAME}
        )
        eid = created["id"]
        FS_ID_PATH.write_text(
            json.dumps({"documentId": did, "featureStudioId": eid}), encoding="utf-8"
        )
        print(f"created experiment Feature Studio {eid}")

    major, version = resolve_version_from_trophy()
    print(f"compiling experiments with FeatureScript {major} (import '{version}')")

    results: list[dict] = []
    skipped_budget = 0
    for spec in manifest:
        name = spec["file"]
        spent = int(client._usage.get("consumed", 0)) - start_consumed
        if spent >= MAX_BUDGET:
            skipped_budget += 1
            results.append({"file": name, "skipped": "budget"})
            continue
        path = EXPERIMENTS_DIR / name
        source = path.read_text(encoding="utf-8")
        source = source.replace("{{MAJOR}}", major).replace("{{VERSION}}", version)
        verdict = upload_and_compile(client, did, wid, eid, source, 0)
        before = int(client._usage.get("consumed", 0))
        entry = {
            "file": name,
            "claim": spec.get("claim"),
            "expect": spec.get("expect"),
            "actual": "compile-ok" if verdict["ok"] else "compile-error",
            "detail": verdict["detail"],
            "callsUsed": int(client._usage.get("consumed", 0)) - before,
        }
        entry["pass"] = entry["actual"] == entry["expect"]
        results.append(entry)
        status = "PASS" if entry["pass"] else "FAIL"
        print(f"[{status}] {name}  expected={entry['expect']} actual={entry['actual']}")
        print(f"        {entry['detail']}")

    total_spent = int(client._usage.get("consumed", 0)) - start_consumed
    outcome = {
        "startLedgerConsumed": start_consumed,
        "endLedgerConsumed": int(client._usage.get("consumed", 0)),
        "callsSpentThisRun": total_spent,
        "skippedForBudget": skipped_budget,
        "featureScriptVersion": major,
        "importVersion": version,
        "results": results,
    }
    RESULTS_PATH.write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    passed = sum(1 for r in results if r.get("pass"))
    total = sum(1 for r in results if "skipped" not in r)
    print(f"\n{passed}/{total} experiments match expectation; this run spent "
          f"{total_spent} ledgered calls (budget {MAX_BUDGET})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
