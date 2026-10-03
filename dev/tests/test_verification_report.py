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
from dev.verification_report import adapters, rules as R, runner, slices  # noqa: E402

GOOD_REPORT = json.loads((FIXTURES / "good__vertical_slice.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((FIXTURES / "expected_verdicts.json").read_text(encoding="utf-8"))
EXPECTED_PROPOSED = json.loads((FIXTURES / "expected_proposed.json").read_text(encoding="utf-8"))


class GoodSlice(unittest.TestCase):
    def test_good_slice_passes_and_every_rule_ran(self) -> None:
        verdict = runner.check_report(GOOD_REPORT)
        self.assertTrue(verdict["ok"], verdict["refusals"])
        self.assertEqual(verdict["rulesNotRun"], [])
        self.assertEqual(sorted(verdict["rulesRun"]), sorted(R.AGREED_RULE_IDS))
        self.assertEqual(verdict["rulesProposed"], list(R.PROPOSED_RULE_IDS))
        self.assertEqual(verdict["proposedRefusals"], [], "a proposed rule must not have anything to say about a good slice")

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
        covered = {rule for rule in list(EXPECTED.values()) + list(EXPECTED_PROPOSED.values()) if rule}
        self.assertEqual([rule["id"] for rule in R.RULES], list(R.RULE_IDS))
        self.assertEqual(len(set(R.RULE_IDS)), len(R.RULE_IDS), "duplicate rule ids")
        for rule_id in R.RULE_IDS:
            self.assertIn(rule_id, covered, f"{rule_id} has no negative control")
        for rule_id in covered:
            self.assertIn(rule_id, R.RULE_IDS)
        for name in list(EXPECTED) + list(EXPECTED_PROPOSED):
            self.assertTrue((FIXTURES / name).exists(), f"{name} is missing on disk")
        self.assertEqual(
            sorted(set(EXPECTED_PROPOSED.values())), sorted(R.PROPOSED_RULE_IDS), "every proposed rule needs a fixture"
        )

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
            "（无）" if reading.get("value") is None else str(reading["value"])
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


class ProposedRules(unittest.TestCase):
    """A rule that is not confirmed yet must be visible **and** harmless.

    The coordinator judged R13 admissible but said the plane that measured it has to confirm that it
    applies to this interface (mail 298 §3). So the machinery is in place, the fixture exists, and the
    rule refuses nobody -- until one word changes.
    """

    R13_FIXTURE = FIXTURES / "bad__R13__self_consistency_as_validity.json"

    def test_a_proposed_rule_refuses_nobody_but_says_what_it_would_refuse(self) -> None:
        report = json.loads(self.R13_FIXTURE.read_text(encoding="utf-8"))
        verdict = runner.check_report(report)
        self.assertTrue(verdict["ok"], "an unconfirmed rule must not reject a report")
        self.assertEqual(verdict["refusals"], [], "a proposed rule refuses nobody")
        self.assertEqual(verdict["rulesProposed"], ["R13"])
        # It still *says* what it would refuse -- that is what lets the peers judge the impact before
        # confirming it, instead of discovering it after the rule starts rejecting reports.
        self.assertEqual(
            sorted({refusal["rule"] for refusal in verdict["proposedRefusals"]}), ["R13"], verdict["proposedRefusals"]
        )
        self.assertIn("self-consistency", verdict["proposedRefusals"][0]["problem"])
        # ... and the fixture really does carry what the rule is about:
        injected = next(claim for claim in report["claims"] if claim["id"] == "c_self")
        self.assertEqual(injected["reference"], R.SELF_CONSISTENCY_REFERENCE)
        self.assertEqual(injected["grade"], "reliable")

    def test_the_proposed_rule_would_refuse_its_own_fixture_once_binding(self) -> None:
        report = json.loads(self.R13_FIXTURE.read_text(encoding="utf-8"))
        flipped = [dict(rule, status="agreed") if rule["id"] == "R13" else rule for rule in R.RULES]
        with mock.patch.object(R, "RULES", flipped), mock.patch.object(
            R, "AGREED_RULE_IDS", [rule["id"] for rule in flipped]
        ):
            verdict = runner.check_report(report)
        self.assertFalse(verdict["ok"], "the moment R13 is confirmed it must refuse this fixture")
        self.assertEqual(sorted({refusal["rule"] for refusal in verdict["refusals"]}), ["R13"])
        self.assertEqual(verdict["proposedRefusals"], [])
        self.assertIn("+14.695 %", verdict["refusals"][0]["required_fix"])

    def test_the_peer_slice_keeps_its_self_consistency_claim_honest(self) -> None:
        """The real slice grades per-shell consistency `heuristic`, so R13 has nothing to say about it."""
        report = slices.build_meshq_report()
        verdict = runner.check_report(report)
        self.assertTrue(verdict["ok"], verdict["refusals"])
        shell = next(claim for claim in report["claims"] if claim["id"] == "c_shell")
        self.assertNotEqual(shell["grade"], "reliable")
        self.assertTrue(shell["not_evaluated"], "the whole-part gap must be a declared absence")


class SelfClaims(unittest.TestCase):
    """Machine-check the claims this package makes about **its own code**.

    The coordinator reported a real case elsewhere: an implementation whose final report claimed a
    property its code did not have, while 549 of its own tests stayed green (mail 298 §5). A claim in
    one's own document is exactly as checkable as a claim in one's own report, so it is checked here.
    """

    PACKAGE = ROOT / "dev" / "verification_report"
    README = PACKAGE / "README.md"

    def test_the_package_imports_the_standard_library_only(self) -> None:
        import ast
        import sys as _sys

        # Sibling modules inside this package are not "third party": `runner.py` falls back to
        # `import rules` when it is executed as a script rather than imported as a package.
        siblings = {path.stem for path in self.PACKAGE.glob("*.py")}
        for path in sorted(self.PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:  # relative import inside the package
                        continue
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                for name in names:
                    with self.subTest(module=name, file=path.name):
                        self.assertTrue(
                            name in _sys.stdlib_module_names or name in siblings,
                            f"{path.name} imports the non-stdlib module {name}",
                        )

    def test_this_plane_still_has_no_renderer(self) -> None:
        """The README claims the image leg is CadQ's. If that changes, this test must fail loudly."""
        import re as _re

        patterns = (_re.compile(r"\bmatplotlib\b"), _re.compile(r"\bsavefig\b"), _re.compile(r"\brender_parts\b"),
                    _re.compile(r"\bimageio\b"), _re.compile(r"\bfrom PIL\b"), _re.compile(r"\bimport PIL\b"))
        offenders: list[str] = []
        for directory in ("mcp_main", "onshape_browser_mode"):
            base = ROOT / directory
            if not base.exists():
                continue
            for path in base.rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="replace")
                if any(pattern.search(text) for pattern in patterns):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(
            offenders, [],
            "this plane now renders: update dev/verification_report/README.md (and the peer slice) rather than deleting this test",
        )
        self.assertIn("has no renderer", self.README.read_text(encoding="utf-8"))

    def test_the_readme_counts_match_the_code(self) -> None:
        import re as _re

        readme = self.README.read_text(encoding="utf-8")
        rules_mentioned = _re.search(r"(\d+) rules", readme)
        self.assertIsNotNone(rules_mentioned, "the README must state the rule count")
        self.assertEqual(int(rules_mentioned.group(1)), len(R.RULES))
        self.assertEqual(len(R.AGREED_RULE_IDS) + len(R.PROPOSED_RULE_IDS), len(R.RULES))
        self.assertIn("proposed", readme, "the README must explain that a proposed rule refuses nobody")
        self.assertIn("R13", readme)

        fixtures = sorted((self.PACKAGE / "fixtures").glob("bad__*.json"))
        stated = _re.search(r"(\d+) bad \+ 1 good", readme)
        self.assertIsNotNone(stated, "the README must state the fixture counts")
        self.assertEqual(int(stated.group(1)), len(fixtures))


class SchemaFirstIngestion(unittest.TestCase):
    """Defect D1: a consumer must decide what a document is **before** judging it.

    Measured in round 17: MeshQ's extractor refused our report with
    `has no \\`inspection\\` object -- not a MeshQ record` and exit 2 -- correct behaviour for a foreign
    shape, but it left the agreed report **write-only**. The fix agreed with the coordinator (mail 301)
    is: look at `schema` first; an unrecognised shape is refused **with a reason that names an adapter**,
    never accepted by default and never reported on as if it had been checked.
    """

    GOOD = FIXTURES / "good__vertical_slice.json"
    PEER_RECORD = pathlib.Path("/home/lijq/code/MeshQ/artifacts/contract-probe/work_sphere_cap_coarse/meshq_result.json")

    def test_our_own_report_is_recognised(self) -> None:
        sniffed = runner.sniff_schema(json.loads(self.GOOD.read_text(encoding="utf-8")))
        self.assertEqual(sniffed["kind"], "report")
        self.assertEqual(sniffed["schemaId"], R.SCHEMA_ID)
        self.assertEqual(runner.main(["--ingest", str(self.GOOD)]), 0)

    def test_an_unknown_version_of_our_own_schema_is_refused(self) -> None:
        document = {"schema": {"id": R.SCHEMA_ID, "version": R.SCHEMA_VERSION + 1}}
        sniffed = runner.sniff_schema(document)
        self.assertEqual(sniffed["kind"], "unknown")
        self.assertIn("version", sniffed["reason"])

    @unittest.skipUnless(PEER_RECORD.exists(), "MeshQ's contract probe is not checked out beside this repo")
    def test_a_peers_producer_record_is_named_not_judged(self) -> None:
        document = json.loads(self.PEER_RECORD.read_text(encoding="utf-8"))
        sniffed = runner.sniff_schema(document)
        self.assertEqual(sniffed["kind"], "producer_record")
        self.assertEqual(sniffed["adapter"], "dev.verification_report.adapters.extract_meshq_result")
        self.assertIn("inspection", sniffed["reason"])
        self.assertEqual(runner.main(["--ingest", str(self.PEER_RECORD)]), 2)
        # And handing it to the checker must not produce a verdict about it at all.
        self.assertEqual(runner.main(["--report", str(self.PEER_RECORD)]), 2)

    @unittest.skipUnless(adapters.REAL_MANIFEST.exists(), "this plane's own handoff is not in the drop directory")
    def test_this_planes_own_handoff_is_named_too(self) -> None:
        sniffed = runner.sniff_schema(json.loads(adapters.REAL_MANIFEST.read_text(encoding="utf-8")))
        self.assertEqual(sniffed["kind"], "producer_record")
        self.assertEqual(sniffed["adapter"], "dev.verification_report.adapters.extract_onshapescript_manifest")

    def test_an_unrecognised_shape_says_why_silence_is_not_acceptance(self) -> None:
        sniffed = runner.sniff_schema({"hello": 1})
        self.assertEqual(sniffed["kind"], "unknown")
        self.assertIn("no error", sniffed["reason"])
        self.assertIsNone(sniffed["adapter"])
        for non_object in ([], "text", 7, None):
            with self.subTest(value=non_object):
                self.assertEqual(runner.sniff_schema(non_object)["kind"], "unknown")

    def test_the_cli_demands_one_of_report_or_ingest(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            runner.main([])
        self.assertEqual(caught.exception.code, 2)
