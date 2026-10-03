#!/usr/bin/env python3
"""Generate the verification-report fixtures: one good vertical slice, one bad sample per rule.

Two classes of negative sample stay apart (interface decision §6.1):

* the **admission** sample of a rule is the real incident named in
  ``dev/verification_report/rules.py::measured_basis``;
* the files written here are **unit-test mutations** the author wrote to exercise *this*
  code. They are not admission, and a mutation is never launderable as evidence.

    python dev/tools/build_verification_fixtures.py --write
    python dev/tools/build_verification_fixtures.py --check
    python dev/tools/build_verification_fixtures.py --facts
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "dev" / "verification_report" / "fixtures"
sys.path.insert(0, str(ROOT))

from dev.verification_report import rules as R  # noqa: E402

GOOD = "good__vertical_slice.json"
EXPECTED = "expected_verdicts.json"

#: The recorded signature of the real 70-piece handoff set (three-plane session).
HANDOFF_SIGNATURE = "7f4271064f1107bebb3aaaf40944b2690285b4aed8c6a7c55ceee54728608292"
SOURCE_DIGEST = "d112de9c63dd6ceacfb0f0e0d0f2b0a3c4d5e6f708192a3b4c5d6e7f8091a2b3"


def _good_report() -> dict[str, Any]:
    """A small slice whose numbers are real where they can be.

    Numeric claims only: this plane has no renderer (``grep -rn "matplotlib|savefig|
    render_parts" onshape_module/`` is empty), so the image leg is CadQ's and is *declared
    absent* rather than faked -- a numeric-only delivery does not need an image, which is
    exactly the boundary the two R8 fixtures probe from the other side.
    """
    return {
        "schema": {"id": R.SCHEMA_ID, "version": R.SCHEMA_VERSION},
        "producer": {
            "plane": "onshapescript",
            "tool": "dev/tools/check_handoff.py",
            "revision": "75b8e4e",
        },
        "artifact": {
            "path": "/tmp/three-plane-drop/onshapescript-70piece-tessellation/manifest.json",
            "sha256": HANDOFF_SIGNATURE,
            "units": "mm",
            "sha256_stable": False,
            "sha256_stable_evidence": {
                "reason": "the STEP leg rewrites its header (timestamps) on every write, so the bytes move while the geometry does not",
                "consequence": "the digest addresses this delivery for this run; it is not a citable identity of the geometry",
            },
        },
        "claims": [
            {
                "id": "c1",
                "quantity": "brep.volume_mm3",
                "layers": ["geometry"],
                "grade": "reliable",
                "readings": [
                    {
                        "value": 4500.0,
                        "unit": "mm^3",
                        "family": "brep_solid_volume(exact)",
                        "algorithm": "closed-solid volume from the B-Rep faces; exact arithmetic on the recorded parameters",
                        "achieved": {
                            "absolute": 1e-09,
                            "relative": 0.0,
                            "basis": "three-plane recomputation of the same 70 STL byte sets: relative deviation 9.8e-13 here, 4.99e-07 CadQ, 3.39e-06 MeshQ",
                        },
                    }
                ],
                "negative_control": {
                    "fixture": "bad__R6__reading_without_achieved.json",
                    "must_reject": True,
                    "observed": "rejected",
                },
                "not_evaluated": [],
            },
            {
                "id": "c2",
                "quantity": "bounds_mm",
                "layers": ["geometry"],
                "grade": "reliable",
                "boundsAlgorithm": R.COMPARABLE_BOUNDS_FAMILY,
                "readings": [
                    {
                        "value": 40.0,
                        "unit": "mm",
                        "family": R.COMPARABLE_BOUNDS_FAMILY,
                        "algorithm": "vertex extrema of the artifact bytes (the bytes are the referee)",
                        "achieved": {
                            "absolute": 1e-12,
                            "relative": 0.0,
                            "basis": "exact in binary floating point; the box is read off the same bytes the digest covers",
                        },
                    }
                ],
                "negative_control": {
                    "fixture": "bad__R7__two_names_disagree.json",
                    "must_reject": True,
                    "observed": "rejected",
                },
                "not_evaluated": [],
            },
            {
                "id": "c3",
                "quantity": "minWallMm",
                "layers": ["geometry"],
                "grade": "unknown",
                "readings": [],
                "not_evaluated": [
                    {"key": "c3.minWallMm", "why": "this plane does not compute a minimum wall thickness (grade unknown)"}
                ],
            },
        ],
        "complete": True,
        "not_evaluated": [
            {"key": "c3.minWallMm", "why": "not computed by this plane; MeshQ grades it unknown for the same reason"}
        ],
        "tolerances": {
            "volume_mm3": {
                "absolute": 0.001,
                "declared_by": "receiver",
                "used_by": "consumer",
                "used": 0.001,
                "matches_declaration": True,
            },
            "bounds_mm": {
                "absolute": 1e-09,
                "declared_by": "sender",
                "used_by": "consumer",
                "used": 1e-09,
                "matches_declaration": True,
            },
        },
        "vintage": {
            "date": "2026-10-04",
            "readers": ["onshapescript", "cadq", "meshq"],
            "witness": "MeshQ 179",
            "re_derive_when": "any producer changes its tessellation family or its chord height",
        },
        "cost": {"network": "offline", "estimated_requests": 0, "mutating": False},
        "independence": {
            "level": "different_implementation_same_kernel",
            "of": "the 70-piece tessellation set, recomputed independently by the three planes",
        },
        "csv_projection": {"path": "pieces.csv", "checked_against": "report", "result": "match"},
    }


# ------------------------------------------------------------------ one mutation per rule


def _m_r1(report: dict) -> None:
    report["schema"]["version"] = 2


def _m_r2(report: dict) -> None:
    del report["producer"]["revision"]


def _m_r3(report: dict) -> None:
    del report["artifact"]["sha256_stable_evidence"]


def _m_r4(report: dict) -> None:
    del report["artifact"]["units"]


def _m_r5(report: dict) -> None:
    del report["tolerances"]["volume_mm3"]["declared_by"]


def _m_r6(report: dict) -> None:
    del report["claims"][0]["readings"][0]["achieved"]


def _m_r7_disagree(report: dict) -> None:
    report["claims"][1]["bounds_family"] = "bbox_of_step_brep_header"


def _m_r7_undeclared(report: dict) -> None:
    del report["claims"][1]["boundsAlgorithm"]


def _m_r8_basis(report: dict) -> None:
    report["claims"][0]["evidence"] = [
        {
            "kind": "image",
            "path": "slice.png",
            "grade": "visual",
            "basis": {
                "views": ["+Z"],
                "fit": "tight",
                "source_sha256": SOURCE_DIGEST,
                "recipe_version": "1",
            },
        }
    ]


def _m_r8_structural(report: dict) -> None:
    report["claims"][0]["layers"] = ["geometry", "topology"]


def _m_r9(report: dict) -> None:
    report["artifact"]["stable"] = True


def _m_r10(report: dict) -> None:
    report["complete"] = False


def _m_r11(report: dict) -> None:
    report["independence"]["level"] = "same_code"


def _m_r12(report: dict) -> None:
    report["csv_projection"]["result"] = "unchecked"


MUTATIONS: list[tuple[str, str, Callable[[dict], None]]] = [
    ("R1", "unknown_schema_version", _m_r1),
    ("R2", "no_revision", _m_r2),
    ("R3", "unstable_digest_without_reason", _m_r3),
    ("R4", "no_units", _m_r4),
    ("R5", "tolerance_without_owner", _m_r5),
    ("R6", "reading_without_achieved", _m_r6),
    ("R7", "two_names_disagree", _m_r7_disagree),
    ("R7", "family_undeclared", _m_r7_undeclared),
    ("R8", "image_without_basis", _m_r8_basis),
    ("R8", "structural_claim_without_image", _m_r8_structural),
    ("R9", "bare_verdict_field", _m_r9),
    ("R10", "incomplete_looks_green", _m_r10),
    ("R11", "same_code_as_evidence", _m_r11),
    ("R12", "projection_unchecked", _m_r12),
]


def fixture_name(rule_id: str, slug: str) -> str:
    return f"bad__{rule_id}__{slug}.json"


def build() -> dict[str, Any]:
    """Return ``{filename: content}`` for every fixture plus the expected verdicts."""
    good = _good_report()
    out: dict[str, Any] = {GOOD: good}
    expected: dict[str, Any] = {GOOD: None}
    for rule_id, slug, mutate in MUTATIONS:
        report = copy.deepcopy(good)
        mutate(report)
        name = fixture_name(rule_id, slug)
        out[name] = report
        expected[name] = rule_id
    out[EXPECTED] = expected
    return out


def _serialise(content: Any) -> str:
    return json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def cmd_write() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(build().items()):
        (FIXTURE_DIR / name).write_text(_serialise(content), encoding="utf-8")
        print(f"wrote {FIXTURE_DIR / name}")
    return 0


def cmd_check() -> int:
    differing: list[str] = []
    for name, content in sorted(build().items()):
        path = FIXTURE_DIR / name
        want = _serialise(content)
        have = path.read_text(encoding="utf-8") if path.exists() else None
        if have != want:
            differing.append(name)
    if differing:
        print("fixtures differ from the generator:")
        for name in differing:
            print(f"  {name}")
        return 1
    print(f"all fixtures match the generator ({len(build())} files)")
    return 0


def cmd_facts() -> int:
    fixtures = build()
    expected = fixtures.get(EXPECTED) or {}
    covered = {rule for rule in expected.values() if rule}
    missing = [rule["id"] for rule in R.RULES if rule["id"] not in covered]
    print(f"rules: {len(R.RULES)}")
    print(f"fixtures: {len([name for name in fixtures if name.startswith('bad__')])} bad + 1 good")
    print(f"rules without a negative control: {missing or 'none'}")
    print(f"admission samples (real incidents) named in the rule table: {len(R.RULES)}")
    return 0 if not missing else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the fixtures")
    parser.add_argument("--check", action="store_true", help="verify the fixtures on disk match the generator")
    parser.add_argument("--facts", action="store_true", help="print rule/fixture counts")
    args = parser.parse_args(argv)
    if args.write:
        return cmd_write()
    if args.check:
        return cmd_check()
    if args.facts:
        return cmd_facts()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
