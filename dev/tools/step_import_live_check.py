r"""Operator-run live check of the browser STEP import leg; default is a pure local plan.

Lifecycle: maintained development tool (not a one-off). It exists so the human part of the import leg's
acceptance — the half that needs a signed-in browser — is **one command with a paste-back block**, instead of
hand-driving an MCP tool and transcribing fields. Everything the offline tests cannot prove is printed as
`unproven` with the reason, and nothing is claimed on the tool's own authority.

Windows checkout (no installation performed by this script)::

    .\.venv\Scripts\python.exe dev\tools\step_import_live_check.py --source C:\path\to\handoff.step
    .\.venv\Scripts\python.exe dev\tools\step_import_live_check.py --source ... --confirm-browser ^
        --document-id <did> --workspace-id <wid> --register trial-1

Two modes, and the default is the safe one:

* **no `--confirm-browser`** — no browser is started, no page is touched. It measures the source file, checks
  the declared digest (or the handoff manifest) and prints the import plan. This half is what the ledger's
  `I6` can be closed with.
* **`--confirm-browser`** — uses the **resident** browser profile (so a human sign-in is not spent), runs the
  real import against the document/workspace ids you pass, and optionally registers the result as an
  `import-manifest.json`. It never creates a document, never chooses an address, and never releases the
  session: residency is the whole reason the login survives.

Exit codes: ``0`` every check the run could evaluate passed; ``1`` a check failed; ``2`` the run could not
happen (bad arguments, unreadable source, browser/page unavailable) — kept distinct so "could not check" is
never read as "checked and fine".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CHECKS = ("I1", "I2", "I3", "I4", "I5", "I6")


def _fail(message: str, code: int = 2) -> int:
    print(f"cannot run: {message}", file=sys.stderr)
    return code


def _plan(args: argparse.Namespace) -> tuple[dict[str, Any] | None, int]:
    from onshape_browser_mode import step_import

    try:
        plan = step_import.plan_browser_step_import(
            source_path=args.source,
            expect_sha256=args.expect_sha256 or "",
            handoff_manifest=args.handoff or "",
            mode=args.mode,
            target_tab=args.target_tab or "",
            document_id=args.document_id or "",
            workspace_id=args.workspace_id or "",
            expect_feature_name=args.expect_feature_name or "",
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"the source cannot be imported as addressed: {exc}", file=sys.stderr)
        return None, 1
    return plan, 0


def _print_plan(plan: dict[str, Any]) -> None:
    source = plan["source"]
    print("source")
    print(f"  path        : {source['path']}")
    print(f"  sha256      : {source['sha256']}")
    print(f"  addressed by: {source['addressedBy']}"
          + (f" (declared {source['expectedSha256']}, matches={source['matchesExpected']})"
             if source["expectedSha256"] else ""))
    if source.get("handoff"):
        handoff = source["handoff"]
        print(f"  handoff     : schema={handoff.get('handoffSchema') or '-'} "
              f"units={handoff.get('handoffUnits') or '-'} "
              f"rule={handoff.get('handoffIdentityRule') or '-'}")
    print(f"  format      : {source['formatName']} ({source['byteCount']} bytes)")
    print(f"  digest note : {source['sha256Note']}")
    configuration = plan.get("configuration") or {}
    if configuration:
        print(f"  entry       : {json.dumps(configuration, ensure_ascii=False)}")
    print("\ntarget")
    print(f"  mode        : {plan['mode']}")
    print(f"  document    : {plan['target'].get('documentId') or '(current page)'}")
    print(f"  workspace   : {plan['target'].get('workspaceId') or '(current page)'}")
    print(f"  tab         : {plan['target'].get('tab') or '(none named)'}")
    print("\nlanding proof rule")
    print(f"  {plan['landingProof']['rule']}")
    print(f"  reads       : {plan['landingProof']['reads']}")
    print(f"  imported=true requires: {plan['landingProof']['importedTrueRequires']}")
    print("\nrefusal rules this leg enforces")
    for rule in plan.get("refusalRules") or []:
        print(f"  - {rule}")
    print(f"\nnetwork: {plan['network']} | estimated REST requests: {plan['estimatedApiRequests']} "
          f"| mutating: {plan['mutating']}")
    entry = (plan.get("selectors") or {}).get("importEntry") or {}
    if entry:
        print("import entry (MEASURED live 2026-10-03, so not an untrusted constant):")
        print(f"  item        : {entry.get('item', '')}   label observed: {entry.get('observedLabel', '')}")
        print(f"  menu        : {entry.get('menu', '')}   how: {entry.get('how', '')}")
    print("selectors this leg is NOT allowed to trust yet:")
    for selector in plan["liveAcceptance"]["unverifiedSelectors"]:
        print(f"  - {selector}")


def _report(result: dict[str, Any]) -> tuple[list[tuple[str, str, str]], int]:
    """Turn one live import result into the ledger's check rows. Only observed facts get `pass`."""
    rows: list[tuple[str, str, str]] = []
    failures = 0

    entry = result.get("importEntry") or {}
    if entry.get("clicked"):
        rows.append(("I1", "pass", f"import entry clicked via a visible label: {entry.get('label') or entry.get('route') or '(route unrecorded)'}"))
    else:
        rows.append(("I1", "fail", f"the import entry was not found: {result.get('detail') or result.get('reason')}"))
        failures += 1

    facts = result.get("pageFacts") or {}
    rows.append(("I2", "observed" if facts.get("tabNames") else "unproven",
                 f"tab names read from the page: {facts.get('tabNames') or '(none read)'}"))

    if result.get("imported"):
        rows.append(("I3", "pass", f"exactly one new row: {[row.get('name') for row in result.get('newRows') or []]}"))
    else:
        rows.append(("I3", "fail", f"no landed element: reason={result.get('reason')} "
                                    f"translationCompleted={result.get('translationCompleted')}"))
        failures += 1

    selectors = result.get("selectorsUsed") or {}
    rows.append(("I4", "observed" if selectors else "unproven",
                 f"selectors actually used: {json.dumps(selectors)[:400]}"))

    unverified = result.get("unverifiedSelectors") or []
    rows.append(("I5", "observed", f"{len(unverified)} selector(s) still unverified by this leg: {unverified}"))

    source = result.get("source") or {}
    if source.get("addressedBy") == "sha256":
        rows.append(("I6", "pass", f"the import was addressed by digest {source['sha256']} "
                                   f"(declared {source['expectedSha256']}, matches={source['matchesExpected']})"))
    else:
        rows.append(("I6", "unproven", "no digest was declared for this run: the delivery was addressed by path only"))
    return rows, failures


def run_plan_only(args: argparse.Namespace) -> int:
    plan, code = _plan(args)
    if plan is None:
        return code
    print(f"DRY RUN — no browser, no page, no cloud mutation ({args.source})\n")
    _print_plan(plan)
    print("\nverdict      : PASS (the plan was produced and the addressing was checked)")
    print("next         : this half closes ledger check I6's offline part; the live half needs "
          "--confirm-browser with a signed-in resident browser.")
    return 0


def run_live(args: argparse.Namespace) -> int:
    if not args.document_id or not args.workspace_id:
        return _fail("a real import needs --document-id and --workspace-id (this tool never creates a document)")
    plan, code = _plan(args)
    if plan is None:
        return code

    print(f"LIVE IMPORT — browser session, 0 REST requests ({args.source})\n")
    _print_plan(plan)
    print()

    from onshape_browser_mode import actions, step_import
    from onshape_browser_mode.guard import get_guard
    from onshape_browser_mode.session import get_session

    session = get_session()
    page = session.start()
    session._enforce_single_working_page(page)
    actions.reconnect_if_needed(page)
    get_guard().pace()

    result = step_import.import_browser_step(
        page,
        source_path=args.source,
        expect_sha256=args.expect_sha256 or "",
        handoff_manifest=args.handoff or "",
        mode=args.mode,
        target_tab=args.target_tab or "",
        document_id=args.document_id,
        workspace_id=args.workspace_id,
        expect_feature_name=args.expect_feature_name or "",
        timeout_ms=args.timeout_ms,
    )

    rows, failures = _report(result)
    print("ledger checks")
    for check, verdict, detail in rows:
        print(f"  {check}: {verdict:<8} {detail}")

    if not result.get("imported"):
        print("\nthe element did NOT land, so nothing is registered; paste this whole output back.")
        return 1

    if args.register:
        try:
            registered = step_import.register_imported_browser_step(
                import_id=args.register, result=result,
                document_id=args.document_id, workspace_id=args.workspace_id,
            )
        except ValueError as exc:
            print(f"\nregistration refused: {exc}")
            return 1
        print(f"\nregistered: {registered['manifestPath']}")

    print("\nNOT proven by this run (state it, do not round it up):")
    print("  - that the landed element corresponds to the artifact beyond the digest recorded above")
    print("  - that the four dialog selectors this leg lists as unverified are the right ones")
    print("  - that a translation which only finished later would still be found by this read")
    print("\nverdict      : " + ("FAIL (a check above failed)" if failures else "PASS for the checks shown"))
    print("paste this whole output back; the four UNVERIFIED selectors are the point of the exercise.")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="local .step/.stp file to import")
    parser.add_argument("--expect-sha256", default="",
                        help="the digest this delivery must hash to (the address, not the path)")
    parser.add_argument("--handoff", default="", help="handoff manifest declaring the digest to resolve")
    parser.add_argument("--mode", default="new-tab", choices=("new-tab", "into-part-studio"))
    parser.add_argument("--target-tab", default="", help="target tab name for into-part-studio")
    parser.add_argument("--expect-feature-name", default="", help="feature name the landed row must carry")
    parser.add_argument("--document-id", default="", help="target document id (required for a real import)")
    parser.add_argument("--workspace-id", default="", help="target workspace id (required for a real import)")
    parser.add_argument("--register", default="", help="import id to register the live result under")
    parser.add_argument("--timeout-ms", type=int, default=120_000, help="bounded wait for the landing read")
    parser.add_argument("--confirm-browser", action="store_true",
                        help="actually start the browser session and perform the import")
    args = parser.parse_args(argv)
    return run_live(args) if args.confirm_browser else run_plan_only(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
