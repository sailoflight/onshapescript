#!/usr/bin/env python3
"""Offline confusion-matrix check of the local FeatureScript checker.

Lifecycle: maintained development tool (not a one-off). It exists to give the
local checker a measurable acceptance gate against live-labeled evidence.

What it does, entirely offline and at zero REST quota:

1. renders every ``onshape_docs/verification/live/experiments/*.fs`` template by
   substituting its ``{{MAJOR}}`` / ``{{VERSION}}`` placeholders (the live runner
   did the same at upload time -- an unrendered template fails the local checker
   with a spurious "unreplaced {{PLACEHOLDER}}" error);
2. runs ``onshape_docs/scripts/fs_local_check.py`` on the rendered copy;
3. compares the local verdict with the recorded live outcome in
   ``onshape_docs/verification/live/results.json`` and prints a confusion matrix.

Sample classes (derived from the recorded ``expect`` / ``pass`` pair, not from
prose):

``target``     expected ``compile-error`` but the live run returned ``compile-ok``.
               The live server accepted a defect at save time and deferred it to
               instantiation, so only a local rule can catch it. A local rule
               *should* flag these.
``valid``      expected and got ``compile-ok``. Valid code; a local rule must NOT
               flag these (false-positive control).
``rejected``   expected ``compile-error`` and got it. Intentionally invalid at the
               signature layer; the local checker is not required to catch these.
``drift``      expected ``compile-ok`` but the live run returned ``compile-error``.
               The vendored index disagrees with the live version. **Not an
               acceptance input**: these labels were recorded at FeatureScript
               3029 while the ``is*`` predicate set was only settled at 3044, so
               the disagreement may be a version artifact rather than a defect.
               Reported for provenance only.

Exit code is 0 when the acceptance criteria hold, 1 otherwise:

* every ``target`` sample is flagged (as an error or a warning -- the local
  checker is advisory by design and never blocks an upload);
* no ``valid`` sample is flagged.

Usage:
    python3 dev/tools/fs_corpus_check.py            # matrix + acceptance
    python3 dev/tools/fs_corpus_check.py --verbose   # per-sample findings
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "onshape_docs" / "scripts"
EXPERIMENTS = ROOT / "onshape_docs" / "verification" / "live" / "experiments"
RESULTS = ROOT / "onshape_docs" / "verification" / "live" / "results.json"

sys.path.insert(0, str(SCRIPTS))
import fs_local_check  # noqa: E402  (onshape_docs/scripts is not a package)


def render(template: str, version: str) -> str:
    """Substitute the live runner's template placeholders with one version.

    ``{{MAJOR}}`` is the bare major (``3044``); ``{{VERSION}}`` is the dotted
    import version (``3044.0``).
    """
    major = version.split(".")[0]
    return template.replace("{{MAJOR}}", major).replace("{{VERSION}}", version)


def classify(entry: dict) -> str:
    expect = str(entry.get("expect", ""))
    actual = str(entry.get("actual", ""))
    if expect == "compile-error" and actual == "compile-ok":
        return "target"
    if expect == "compile-ok" and actual == "compile-ok":
        return "valid"
    if expect == "compile-error" and actual == "compile-error":
        return "rejected"
    return "drift"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default=None,
        help="FeatureScript version used to render templates (default: the "
        "featureScriptVersion recorded in results.json)",
    )
    parser.add_argument("--verbose", action="store_true", help="print every finding")
    args = parser.parse_args(argv[1:])

    if not RESULTS.is_file():
        print(f"missing recorded live results: {RESULTS}", file=sys.stderr)
        return 2
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    version = args.version or f"{payload.get('featureScriptVersion', '3044')}.0"
    entries = payload.get("results", [])

    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for entry in entries:
            name = entry["file"]
            source = EXPERIMENTS / name
            if not source.is_file():
                # Nested fixtures (e.g. import-boundary/) are not part of the
                # labeled matrix.
                continue
            rendered = tmp_path / name
            rendered.write_text(
                render(source.read_text(encoding="utf-8"), version), encoding="utf-8"
            )
            checked = fs_local_check.check_file(rendered)
            flagged = bool(checked.errors or checked.warnings)
            rows.append(
                {
                    "file": name,
                    "class": classify(entry),
                    "errors": list(checked.errors),
                    "warnings": list(checked.warnings),
                    "flagged": flagged,
                }
            )

    order = {"target": 0, "valid": 1, "rejected": 2, "drift": 3}
    rows.sort(key=lambda row: (order.get(row["class"], 9), row["file"]))

    print(f"FeatureScript version used for rendering: {version}")
    print(f"corpus: {EXPERIMENTS.relative_to(ROOT)} ({len(rows)} labeled samples)\n")
    print(f"{'sample':34} {'class':9} {'local':7} findings")
    print("-" * 78)
    for row in rows:
        local = "FLAGGED" if row["flagged"] else "clean"
        detail = ""
        if row["errors"]:
            detail = f"ERROR x{len(row['errors'])}"
        elif row["warnings"]:
            first = row["warnings"][0]
            detail = f"WARN x{len(row['warnings'])}: {first[:34]}"
        print(f"{row['file']:34} {row['class']:9} {local:7} {detail}")
        if args.verbose:
            for error in row["errors"]:
                print(f"{'':34} {'':9} {'':7}   ERROR {error}")
            for warn in row["warnings"]:
                print(f"{'':34} {'':9} {'':7}   WARN  {warn}")

    targets = [row for row in rows if row["class"] == "target"]
    valid = [row for row in rows if row["class"] == "valid"]
    missed = [row["file"] for row in targets if not row["flagged"]]
    false_positives = [row["file"] for row in valid if row["flagged"]]

    print("\nacceptance")
    print(f"  target samples flagged : {len(targets) - len(missed)}/{len(targets)}")
    if missed:
        print(f"    MISSED               : {', '.join(missed)}")
    print(f"  valid samples clean    : {len(valid) - len(false_positives)}/{len(valid)}")
    if false_positives:
        print(f"    FALSE POSITIVES      : {', '.join(false_positives)}")

    drift = [row["file"] for row in rows if row["class"] == "drift"]
    if drift:
        print(
            "\nnot an acceptance input (recorded at FeatureScript "
            f"{payload.get('featureScriptVersion')}, is* settled at 3044): "
            f"{', '.join(drift)}"
        )

    ok = not missed and not false_positives
    print(f"\nresult: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
