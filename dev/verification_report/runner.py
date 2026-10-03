"""The runner: the only authority of the verification-report contract.

Division of labour, agreed with the other two planes on 2026-10-04 (coordinator mail 273):

* an **adapter** may only *extract fields* from an artifact; it must never judge;
* **judgement lives here**, once, so that three planes cannot grow three sets of criteria.

Exit codes follow the house convention (``dev/tools/check_handoff.py``): ``0`` everything
checked passed **and** every rule ran; ``1`` a refusal, **or** a rule that did not run;
``2`` the input could not be read.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import re
import sys
from typing import Any, Callable

try:  # imported as a package
    from . import rules as R
except ImportError:  # executed as a script
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import rules as R  # type: ignore[no-redef]

_HEX64 = re.compile(r"[0-9a-f]{64}")
_DATE_SHAPED = re.compile(r"^\d{1,2}-\d{1,2}$")
_LONG_NUMBER = re.compile(r"^\d{16,}$")
_EXCEL_GUARD = ("=", "+", "-", "@")


def _digest_ok(value: Any) -> bool:
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def declared_bounds_family(claim: dict) -> tuple[Any, list[str], bool]:
    """Read the bounds family under **either** declared name.

    Returns ``(family, keys_that_carried_it, conflicting)``. A checker must not pick one
    of two disagreeing declarations: that is a contradiction, and the caller refuses it.
    """
    found: list[tuple[str, Any]] = []
    for key in R.BOUNDS_FAMILY_KEYS:
        if isinstance(claim, dict) and key in claim:
            raw = claim[key]
            found.append((key, raw.get("value") if isinstance(raw, dict) else raw))
    families = {value for _, value in found}
    keys = [key for key, _ in found]
    if len(families) > 1:
        return None, keys, True
    if not found:
        return None, [], False
    return found[0][1], keys, False


def _walk(node: Any, path: str = ""):
    """Yield ``(path, key, value)`` for every key in a nested report."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            yield here, key, value
            yield from _walk(value, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def _claim_list(report: dict) -> list[dict]:
    claims = report.get("claims")
    return [claim for claim in claims if isinstance(claim, dict)] if isinstance(claims, list) else []


def _is_listed_top_level(report: dict, claim_id: Any) -> bool:
    entries = report.get("not_evaluated")
    if not isinstance(entries, list) or claim_id in (None, ""):
        return False
    for entry in entries:
        key = entry.get("key") if isinstance(entry, dict) else entry
        if isinstance(key, str) and (key == claim_id or key.startswith(f"{claim_id}.")):
            return True
    return False


# ---------------------------------------------------------------- the twelve rules


def _r1_schema(report: dict, fail) -> None:
    schema = report.get("schema") if isinstance(report.get("schema"), dict) else {}
    if schema.get("id") != R.SCHEMA_ID:
        fail("R1", "schema.id", f"unknown schema id {schema.get('id')!r}", f"declare {R.SCHEMA_ID!r}")
    if schema.get("version") != R.SCHEMA_VERSION:
        fail(
            "R1",
            "schema.version",
            f"unknown schema version {schema.get('version')!r}",
            f"declare version {R.SCHEMA_VERSION} or refuse the report as a consumer",
        )


def _r2_producer(report: dict, fail) -> None:
    producer = report.get("producer") if isinstance(report.get("producer"), dict) else {}
    for key in ("plane", "revision"):
        if not producer.get(key):
            fail("R2", f"producer.{key}", f"missing {key}", "name the plane and the revision it is answering for")


def _r3_digest(report: dict, fail) -> None:
    artifact = report.get("artifact") if isinstance(report.get("artifact"), dict) else {}
    if not _digest_ok(artifact.get("sha256")):
        fail("R3", "artifact.sha256", "missing or malformed sha256", "publish the 64-hex digest of the delivered bytes")
    if artifact.get("sha256_stable") is False:
        evidence = artifact.get(R.UNSTABLE_DIGEST) if isinstance(artifact.get(R.UNSTABLE_DIGEST), dict) else {}
        for key in ("reason", "consequence"):
            if not evidence.get(key):
                fail(
                    "R3",
                    f"artifact.{R.UNSTABLE_DIGEST}.{key}",
                    f"the digest is declared unstable but {key} is missing",
                    "say why the bytes move and what a consumer may still cite",
                )


def _r4_units(report: dict, fail) -> None:
    artifact = report.get("artifact") if isinstance(report.get("artifact"), dict) else {}
    if not artifact.get("units"):
        fail("R4", "artifact.units", "units undeclared", "declare the unit of every number in the report")


def _r5_tolerances(report: dict, fail) -> None:
    tolerances = report.get("tolerances")
    if not isinstance(tolerances, dict) or not tolerances:
        fail("R5", "tolerances", "no tolerance declared at all", "declare at least the tolerance the reader must accept")
        tolerances = {}
    for name, entry in tolerances.items():
        if not isinstance(entry, dict):
            fail("R5", f"tolerances.{name}", "tolerance is not an object", "give absolute/declared_by/used_by")
            continue
        for key in ("declared_by", "used_by"):
            if not entry.get(key):
                fail(
                    "R5",
                    f"tolerances.{name}.{key}",
                    f"tolerance has no {key}",
                    "name who declares the tolerance and who consumes it (a tolerance must have an owner)",
                )
    vintage = report.get("vintage") if isinstance(report.get("vintage"), dict) else {}
    for key in ("date", "readers", "witness", "re_derive_when"):
        if not vintage.get(key):
            fail("R5", f"vintage.{key}", f"vintage is missing {key}", "record date, readers, witness and the re-derive condition")


def _r6_readings(report: dict, fail) -> None:
    for claim in _claim_list(report):
        readings = claim.get("readings") if isinstance(claim.get("readings"), list) else []
        for index, reading in enumerate(readings):
            where = f"claims[{claim.get('id')}].readings[{index}]"
            if not isinstance(reading, dict):
                fail("R6", where, "reading is not an object", "publish value + family + algorithm + achieved")
                continue
            if "value" not in reading:
                fail(
                    "R6",
                    f"{where}.value",
                    "reading has no value key at all",
                    "always publish the value key; a declared absence is `value: null` plus a reason, a missing field is neither",
                )
            if reading.get("value") is None:
                # The canonical form of an explicit absence (measured on MeshQ's real artifact).
                if not reading.get(R.NULL_REASON_KEY):
                    fail(
                        "R6",
                        f"{where}.{R.NULL_REASON_KEY}",
                        "reading is a null value with no reason",
                        "a null reading must say why it is null; otherwise a consumer cannot tell it from a missing field",
                    )
                if reading.get("achieved"):
                    fail(
                        "R6",
                        f"{where}.achieved",
                        "a null reading declares the precision it achieved",
                        "nothing was measured, so no precision may be declared (drop achieved, keep the reason)",
                    )
                continue
            for key in ("family", "algorithm"):
                if not reading.get(key):
                    fail("R6", f"{where}.{key}", f"reading has no {key}", "same word, different method => incomparable numbers")
            achieved = reading.get("achieved") if isinstance(reading.get("achieved"), dict) else {}
            if not achieved:
                fail("R6", f"{where}.achieved", "reading does not state the precision it achieved", "publish absolute/relative/basis")
                continue
            for key in ("absolute", "relative", "basis"):
                if achieved.get(key) in (None, ""):
                    fail("R6", f"{where}.achieved.{key}", f"achieved is missing {key}", "state the precision and its basis")


def _r7_bounds_family(report: dict, fail) -> None:
    for claim in _claim_list(report):
        quantity = str(claim.get("quantity") or "")
        if "bounds" not in quantity.lower():
            continue
        which = f"claims[{claim.get('id')}]"
        family, keys, conflicting = declared_bounds_family(claim)
        if conflicting:
            quoted = ", ".join(f"{key}={claim[key]!r}" for key in keys)
            fail(
                "R7",
                which,
                f"two declared bounds families disagree ({quoted})",
                "declare one family under one name; a checker must not pick one of two",
            )
        elif family is None:
            looked_for = " / ".join(R.BOUNDS_FAMILY_KEYS)
            fail(
                "R7",
                which,
                f"bounds read but the family is undeclared (looked for {looked_for})",
                f"declare the family ({R.COMPARABLE_BOUNDS_FAMILY!r} or an equivalent) under one of those names",
            )


def _r8_image(report: dict, fail) -> None:
    for claim in _claim_list(report):
        which = f"claims[{claim.get('id')}]"
        evidence = claim.get("evidence") if isinstance(claim.get("evidence"), list) else []
        images = [item for item in evidence if isinstance(item, dict) and item.get("kind") == "image"]
        for index, image in enumerate(images):
            basis = image.get("basis") if isinstance(image.get("basis"), dict) else {}
            for key in R.IMAGE_BASIS_KEYS:
                if not basis.get(key):
                    fail(
                        "R8",
                        f"{which}.evidence[{index}].basis.{key}",
                        f"image evidence is missing {key}",
                        "an image without its basis is 'not measured', not 'passed'",
                    )
        layers = claim.get("layers") if isinstance(claim.get("layers"), list) else []
        structural = all(layer in layers for layer in R.STRUCTURAL_LAYERS)
        if structural and not images:
            fail(
                "R8",
                which,
                "claim is structural (geometry + topology) but ships no image",
                "attach a rendered view with its basis; an image falsifies structure, it cannot establish dimensions",
            )


def _r9_bare_verdict(report: dict, fail) -> None:
    for where, key, _value in _walk(report):
        if key in R.BARE_VERDICT_KEYS:
            fail(
                "R9",
                where,
                f"bare verdict field {key!r}",
                "publish the reading, the criterion and the owner of the criterion instead",
            )


def _r10_unevaluated(report: dict, fail) -> None:
    if report.get("complete") is False:
        for claim in _claim_list(report):
            claim_id = claim.get("id")
            not_evaluated = claim.get("not_evaluated") if isinstance(claim.get("not_evaluated"), list) else []
            if not not_evaluated and not _is_listed_top_level(report, claim_id):
                fail(
                    "R10",
                    f"claims[{claim_id}]",
                    "the report is incomplete but this claim looks green",
                    "a declared criterion that was not evaluated must be as loud as a refused one",
                )
    for claim in _claim_list(report):
        readings = claim.get("readings") if isinstance(claim.get("readings"), list) else []
        if claim.get("grade") == "unknown" and readings and not _is_listed_top_level(report, claim.get("id")):
            fail(
                "R10",
                f"claims[{claim.get('id')}]",
                "grade 'unknown' carries numeric readings but is not listed as not evaluated",
                "list it under not_evaluated: 'nobody computed it' must not read as 'somebody looked'",
            )


def _r11_independence(report: dict, fail) -> None:
    independence = report.get("independence") if isinstance(report.get("independence"), dict) else {}
    level = independence.get("level")
    if level == "same_code":
        fail(
            "R11",
            "independence.level",
            "two outputs of the same code are offered as evidence",
            "declare the independence level honestly; same_code is one piece of evidence, not two",
        )
    elif level and level not in R.INDEPENDENCE_LEVELS:
        fail("R11", "independence.level", f"unknown independence level {level!r}", f"use one of {R.INDEPENDENCE_LEVELS}")


def _r12_projection(report: dict, fail) -> None:
    projection = report.get("csv_projection")
    if projection is None:
        return
    if not isinstance(projection, dict):
        fail("R12", "csv_projection", "csv_projection is not an object", "give checked_against + result")
        return
    for key in ("checked_against", "result"):
        if not projection.get(key):
            fail("R12", f"csv_projection.{key}", f"csv projection does not say {key}", "a projection must be machine-checked against the report")
    if projection.get("result") not in (None, "match"):
        fail(
            "R12",
            "csv_projection.result",
            f"csv projection result is {projection.get('result')!r}",
            "the projection must match the report exactly; two shells of one dataset drift",
        )


def _r13_self_consistency(report: dict, fail) -> None:
    """Per-shell self-consistency is not whole-part validity (MeshQ's measured incident)."""
    for claim in _claim_list(report):
        which = f"claims[{claim.get('id')}]"
        declared = claim.get("reference") == R.SELF_CONSISTENCY_REFERENCE
        families = " ".join(
            str((reading or {}).get("family") or "")
            for reading in (claim.get("readings") or [])
            if isinstance(reading, dict)
        )
        via_reading = "self_consistency" in families
        if (declared or via_reading) and claim.get("grade") == "reliable":
            fail(
                "R13",
                which,
                "whole-part validity is graded reliable on per-shell self-consistency "
                f"({'declared reference' if declared else 'reading family'})",
                "a whole-part claim resting on per-shell checks must not be `reliable`: MeshQ measured every shell "
                "check green while a multi-shell part's volume moved by +14.695 %",
            )


_CHECKS: dict[str, Callable[[dict, Callable], None]] = {
    "R1": _r1_schema,
    "R2": _r2_producer,
    "R3": _r3_digest,
    "R4": _r4_units,
    "R5": _r5_tolerances,
    "R6": _r6_readings,
    "R7": _r7_bounds_family,
    "R8": _r8_image,
    "R9": _r9_bare_verdict,
    "R10": _r10_unevaluated,
    "R11": _r11_independence,
    "R12": _r12_projection,
    "R13": _r13_self_consistency,
}


def check_report(report: dict) -> dict:
    """Run every rule and collect every refusal (never stop at the first).

    Binding rules decide `ok`. A rule whose `status` is `proposed` is **reported** under
    `proposedRefusals` but never refuses anyone: it becomes binding only when the plane that measured
    the incident confirms that it applies to this interface. The fixture it names is therefore
    expected to be *accepted* while the rule is proposed -- and refused the moment its status flips.
    """
    refusals: list[dict] = []
    proposed_refusals: list[dict] = []
    rules_run: list[str] = []
    rules_not_run: list[str] = []
    rules_proposed: list[str] = []

    def record(bucket: list[dict], rule: str, where: str, problem: str, required_fix: str) -> None:
        bucket.append({"rule": rule, "where": where, "problem": problem, "required_fix": required_fix})

    for rule in R.RULES:
        rule_id = rule["id"]
        proposed = rule.get("status", "agreed") == "proposed"
        bucket = proposed_refusals if proposed else refusals

        def fail(rule, where, problem, required_fix, _bucket=bucket) -> None:  # type: ignore[no-untyped-def]
            # Same four-argument convention the checks already use; only the bucket differs, and the
            # bucket is what decides whether this refusal is binding.
            record(_bucket, rule, where, problem, required_fix)

        try:
            _CHECKS[rule_id](report, fail)
        except Exception as exc:  # a rule that did not run must be as loud as a refusal
            if proposed:
                record(bucket, rule_id, "<rule did not run>", f"{type(exc).__name__}: {exc}", "fix the input or the rule")
                rules_proposed.append(rule_id)
                continue
            rules_not_run.append(rule_id)
            record(bucket, rule_id, "<rule did not run>", f"{type(exc).__name__}: {exc}", "fix the input or the rule so it can be evaluated")
            continue
        if proposed:
            rules_proposed.append(rule_id)
        else:
            rules_run.append(rule_id)
    return {
        "ok": not refusals and not rules_not_run,
        "refusals": refusals,
        "proposedRefusals": proposed_refusals,
        "rulesRun": rules_run,
        "rulesNotRun": rules_not_run,
        "rulesProposed": rules_proposed,
    }


# ------------------------------------------------------- the CSV projection (Excel-safe)


#: An empty cell is never left blank in a delivered CSV (the owner's standing rule): a blank
#: cell is indistinguishable from a lost column, and "(无)" says "declared absent" instead.
EMPTY_CELL = "（无）"


def _cell(value: Any) -> str:
    text = EMPTY_CELL if value is None or value == "" else str(value)
    if text.startswith(_EXCEL_GUARD) or _DATE_SHAPED.fullmatch(text) or _LONG_NUMBER.fullmatch(text):
        return f"'{text}"
    return text


def project_csv(report: dict) -> str:
    """Project the per-reading table as Excel-safe CSV (the JSON stays the source)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    # `null_reason` travels in the projection too: a "(无)" cell without its reason in the same
    # row is exactly the reasoned absence lost on the way to the spreadsheet.
    writer.writerow(["claim_id", "quantity", "value", "unit", "family", "algorithm", "null_reason"])
    for claim in _claim_list(report):
        for reading in claim.get("readings") or []:
            if not isinstance(reading, dict):
                continue
            writer.writerow(
                [
                    _cell(claim.get("id")),
                    _cell(claim.get("quantity")),
                    _cell(reading.get("value")),
                    _cell(reading.get("unit")),
                    _cell(reading.get("family")),
                    _cell(reading.get("algorithm")),
                    _cell(reading.get(R.NULL_REASON_KEY)),
                ]
            )
    return "\ufeff" + buffer.getvalue()


def read_projection_csv(text: str) -> list[dict]:
    """Read a projection back, undoing the Excel guard, so it can be machine-checked."""
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows:
        return []
    header = rows[0]
    out = []
    for row in rows[1:]:
        out.append({key: (value[1:] if value.startswith("'") else value) for key, value in zip(header, row)})
    return out


# ---------------------------------------------------------------------------- the CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a three-plane verification report (the runner is the only authority).")
    parser.add_argument("--report", required=True, help="path to the report JSON")
    parser.add_argument("--json", action="store_true", help="print the verdict as JSON")
    parser.add_argument("--csv", action="store_true", help="print the Excel-safe CSV projection instead")
    args = parser.parse_args(argv)

    path = pathlib.Path(args.report)
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(report, dict):
        print(f"cannot read {path}: top level is not an object", file=sys.stderr)
        return 2

    if args.csv:
        sys.stdout.write(project_csv(report))
        return 0

    verdict = check_report(report)
    if args.json:
        print(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"rules run: {len(verdict['rulesRun'])}/{len(R.AGREED_RULE_IDS)}  refusals: {len(verdict['refusals'])}"
            f"  proposed: {len(verdict['rulesProposed'])} ({len(verdict['proposedRefusals'])} would refuse)"
        )
        for refusal in verdict["refusals"]:
            print(f"  [{refusal['rule']}] {refusal['where']}")
            print(f"      problem : {refusal['problem']}")
            print(f"      required: {refusal['required_fix']}")
        for refusal in verdict["proposedRefusals"]:
            print(f"  (proposed {refusal['rule']}, not binding) {refusal['where']}: {refusal['problem']}")
        if verdict["rulesNotRun"]:
            print(f"  rules that did not run: {', '.join(verdict['rulesNotRun'])}")
        print("verdict:", "ok" if verdict["ok"] else "REFUSED")
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
