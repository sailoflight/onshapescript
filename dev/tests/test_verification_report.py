"""Tests for the three-plane verification-report contract (reference implementation).

The contract's own admission gate is applied to this package as well: every rule must have
a negative control, and every rule must name a *measured* basis -- a rule whose basis is
the author's imagination is not admissible.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "dev" / "verification_report" / "fixtures"
SCHEMA = ROOT / "dev" / "verification_report" / "schema" / "verification_report_v1.schema.json"

sys.path.insert(0, str(ROOT))
from dev.verification_report import adapters, rules as R, runner  # noqa: E402

GOOD_REPORT = json.loads((FIXTURES / "good__vertical_slice.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((FIXTURES / "expected_verdicts.json").read_text(encoding="utf-8"))


class GoodSlice(unittest.TestCase):
    def test_good_slice_passes_and_every_rule_ran(self) -> None:
        verdict = runner.check_report(GOOD_REPORT)
        self.assertTrue(verdict["ok"], verdict["refusals"])
        self.assertEqual(verdict["rulesNotRun"], [])
        self.assertEqual(sorted(verdict["rulesRun"]), sorted(R.RULE_IDS))

    def test_cli_exit_zero_on_the_good_slice(self) -> None:
        self.assertEqual(runner.main(["--report", str(FIXTURES / "good__vertical_slice.json"), "--json"]), 0)


class NegativeControls(unittest.TestCase):
    def test_each_bad_fixture_fires_exactly_its_rule(self) -> None:
        for name, expected in sorted(EXPECTED.items()):
            if expected is None:
                continue
            with self.subTest(fixture=name):
                report = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
                verdict = runner.check_report(report)
                self.assertFalse(verdict["ok"], f"{name} was accepted")
                fired = sorted({refusal["rule"] for refusal in verdict["refusals"]})
                self.assertEqual(fired, [expected], f"{name} fired {fired}")
                self.assertEqual(verdict["rulesNotRun"], [])

    def test_coverage_both_ways(self) -> None:
        covered = {rule for rule in EXPECTED.values() if rule}
        self.assertEqual([rule["id"] for rule in R.RULES], list(R.RULE_IDS))
        self.assertEqual(len(set(R.RULE_IDS)), len(R.RULE_IDS), "duplicate rule ids")
        for rule_id in R.RULE_IDS:
            self.assertIn(rule_id, covered, f"{rule_id} has no negative control")
        for rule_id in covered:
            self.assertIn(rule_id, R.RULE_IDS)
        for name in EXPECTED:
            self.assertTrue((FIXTURES / name).exists(), f"{name} is missing on disk")

    def test_every_rule_names_a_measured_basis_and_an_existing_fixture(self) -> None:
        for rule in R.RULES:
            with self.subTest(rule=rule["id"]):
                basis = rule.get("measured_basis") or ""
                self.assertGreater(len(basis), 80, f"{rule['id']} basis is too thin to be an incident")
                self.assertTrue(
                    any(party.lower() in basis.lower() for party in ("onshapescript", "cadq", "meshq", "coordinator", "agent-infra", "ewf")),
                    f"{rule['id']} does not name which plane measured the incident",
                )
                self.assertIn(rule["layer"], ("geometry", "topology", "morphology"))
                self.assertTrue((FIXTURES / rule["negative_control"]).exists(), rule["negative_control"])

    def test_one_mutation_per_rule_is_declared(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("build_fixtures", ROOT / "dev" / "tools" / "build_verification_fixtures.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        declared = {rule_id for rule_id, _slug, _fn in module.MUTATIONS}
        self.assertEqual(declared, set(R.RULE_IDS))


class Generator(unittest.TestCase):
    def test_fixtures_on_disk_match_the_generator(self) -> None:
        proc = subprocess.run(
            [sys.executable, "dev/tools/build_verification_fixtures.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class SchemaAgreement(unittest.TestCase):
    def test_schema_is_valid_json_and_agrees_with_the_runner(self) -> None:
        document = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(document.get("$schema"), "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(set(document["required"]), set(R.REQUIRED_TOP_LEVEL))
        for key in document["required"]:
            self.assertIn(key, GOOD_REPORT, f"the good slice does not carry the required key {key}")
        self.assertEqual(document["properties"]["schema"]["properties"]["version"]["const"], R.SCHEMA_VERSION)
        self.assertEqual(document["properties"]["schema"]["properties"]["id"]["const"], R.SCHEMA_ID)


class UnevaluatedIsLoud(unittest.TestCase):
    def test_a_rule_that_did_not_run_fails_the_report(self) -> None:
        def exploding(_report, _fail):
            raise RuntimeError("simulated rule failure")

        with mock.patch.dict(runner._CHECKS, {"R4": exploding}):
            verdict = runner.check_report(GOOD_REPORT)
        self.assertFalse(verdict["ok"], "a rule that never ran must be as loud as a refusal")
        self.assertIn("R4", verdict["rulesNotRun"])
        self.assertIn("R4", {refusal["rule"] for refusal in verdict["refusals"]})


class BoundsFamilyDualName(unittest.TestCase):
    def test_read_under_the_other_name(self) -> None:
        family, keys, conflicting = runner.declared_bounds_family({"boundsAlgorithm": {"value": "fam"}})
        self.assertEqual((family, keys, conflicting), ("fam", ["boundsAlgorithm"], False))

    def test_two_names_that_disagree_are_a_contradiction(self) -> None:
        claim = {"bounds_family": "fam_a", "boundsAlgorithm": "fam_b"}
        family, keys, conflicting = runner.declared_bounds_family(claim)
        self.assertTrue(conflicting)
        self.assertIsNone(family)
        self.assertEqual(sorted(keys), ["boundsAlgorithm", "bounds_family"])
        verdict = runner.check_report(
            {**json.loads(json.dumps(GOOD_REPORT)), "claims": [dict(GOOD_REPORT["claims"][1], **claim)]}
        )
        refusal = [r for r in verdict["refusals"] if r["rule"] == "R7"]
        self.assertTrue(refusal)
        self.assertIn("fam_a", refusal[0]["problem"])
        self.assertIn("fam_b", refusal[0]["problem"])

    def test_no_declaration_names_both_looked_for_paths(self) -> None:
        report = json.loads((FIXTURES / "bad__R7__family_undeclared.json").read_text(encoding="utf-8"))
        verdict = runner.check_report(report)
        problem = next(r["problem"] for r in verdict["refusals"] if r["rule"] == "R7")
        self.assertIn("bounds_family", problem)
        self.assertIn("boundsAlgorithm", problem)


class CsvProjection(unittest.TestCase):
    def test_projection_is_excel_safe_and_round_trips(self) -> None:
        text = runner.project_csv(GOOD_REPORT)
        self.assertTrue(text.startswith("\ufeff"), "a delivered CSV needs a UTF-8 BOM")
        for row in runner.read_projection_csv(text):
            for cell in row.values():
                with self.subTest(cell=cell):
                    self.assertFalse(cell.startswith(("=", "+", "-", "@")), "Excel would treat this as a formula")
                    self.assertIsNone(re.search(r"^\d{1,2}-\d{1,2}$", cell), "Excel would treat this as a date")
                    self.assertIsNone(re.search(r"^\d{16,}$", cell), "Excel would lose precision")
        rows = runner.read_projection_csv(text)
        expected = [
            str(reading["value"])
            for claim in GOOD_REPORT["claims"]
            for reading in claim["readings"]
        ]
        self.assertEqual([row["value"] for row in rows], expected)

    def test_the_guard_fires_on_hostile_cells(self) -> None:
        hostile = {
            "claims": [
                {
                    "id": "c",
                    "quantity": "=cmd",
                    "readings": [{"value": -18.68, "unit": "mm^3", "family": "9-15", "algorithm": "12345678901234567"}],
                }
            ]
        }
        rows = runner.read_projection_csv(runner.project_csv(hostile))
        self.assertEqual(rows[0]["quantity"], "=cmd")  # read back unchanged
        self.assertEqual(rows[0]["value"], "-18.68")
        raw = runner.project_csv(hostile)
        self.assertIn("'=cmd", raw)
        self.assertIn("'-18.68", raw)
        self.assertIn("'9-15", raw)
        self.assertIn("'12345678901234567", raw)


class Adapters(unittest.TestCase):
    def _synthetic_manifest(self) -> pathlib.Path:
        path = pathlib.Path(tempfile.mkdtemp()) / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "onshapescript.handoff/0.4-draft",
                    "produced_by": {"plane": "onshapescript", "identity": "RoseElm", "tool": "x", "at": "2026-10-04"},
                    "source": {"kind": "step"},
                    "units": "mm",
                    "totals": {"pieces": 70, "contributingPieces": 70, "triangleCount": 1, "areaMm2": 2.0},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_extraction_returns_fields_only(self) -> None:
        extracted = adapters.extract_onshapescript_manifest(self._synthetic_manifest())
        self.assertEqual(extracted["piece_count"], 70)
        self.assertEqual(extracted["units"], "mm")
        self.assertFalse(set(extracted) & adapters.JUDGEMENT_KEYS, "an adapter never judges")

    @unittest.skipUnless(adapters.REAL_MANIFEST.exists(), "the real 70-piece handoff is not in the drop directory")
    def test_extraction_on_the_real_handoff(self) -> None:
        extracted = adapters.extract_onshapescript_manifest(adapters.REAL_MANIFEST)
        self.assertEqual(extracted["piece_count"], 70)
        self.assertEqual(extracted["units"], "mm")
        self.assertFalse(set(extracted) & adapters.JUDGEMENT_KEYS)


class Cli(unittest.TestCase):
    def test_missing_and_malformed_inputs_exit_two(self) -> None:
        self.assertEqual(runner.main(["--report", str(FIXTURES / "does-not-exist.json")]), 2)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{not json")
            broken = handle.name
        self.assertEqual(runner.main(["--report", broken]), 2)

    def test_bad_fixture_exits_one(self) -> None:
        self.assertEqual(runner.main(["--report", str(FIXTURES / "bad__R4__no_units.json")]), 1)


if __name__ == "__main__":
    unittest.main()
