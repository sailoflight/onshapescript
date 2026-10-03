"""Print-fit boundary: this plane's contract vs what the other planes' records actually contain."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fdm_analysis.conversion.print_basis import check_print_basis  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "print_fit_cross_read", ROOT / "dev" / "tools" / "print_fit_cross_read.py"
)
cross = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cross)

_HAS_CADQ = cross.CADQ_PRINT.is_dir()


@unittest.skipUnless(_HAS_CADQ, "CadQ's print-adaptation outputs are not checked out beside this repo")
class CadQPrintFitCrossRead(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = cross.facts()

    def test_every_overhang_judgement_ships_the_inputs_of_its_criterion(self) -> None:
        overhang = self.report["overhang"]
        self.assertEqual(overhang["rows"], 340)
        self.assertEqual(overhang["parts"], 70)
        self.assertEqual(overhang["rows_missing_a_criterion_input"], [])

    def test_the_judgement_is_not_recomputable_from_the_shipped_columns(self) -> None:
        """Measured: worst_drop_mm 4.0 carries both `True` and `False`, so the criterion is missing."""
        self.assertEqual(self.report["overhang"]["drop_to_judgement_contradictions"], {4.0: ["False", "True"]})
        rule = next(r for r in self.report["rules"] if r["rule"] == "cadq-overhang-judgement-recomputable-from-shipped-columns")
        self.assertFalse(rule["passed"])

    def test_a_fit_target_is_declared_without_its_owner(self) -> None:
        for name, item in self.report["fitGap"].items():
            with self.subTest(record=name):
                self.assertEqual(item["target_mm"], 0.15)
                self.assertFalse(item["declares_its_owner"], f"{name} gained an owner field -- update the finding")

    def test_no_peer_record_stamps_a_machine_state(self) -> None:
        scan = self.report["declarationScan"]
        self.assertGreater(scan["files_scanned"], 0)
        self.assertEqual(scan["hits"], [], "a producer stamped an envelope/travel/placement/printable field")

    def test_the_tool_reports_its_own_gaps_rather_than_passing_silently(self) -> None:
        self.assertFalse(self.report["ok"])
        failing = sorted(r["rule"] for r in self.report["rules"] if not r["passed"])
        self.assertEqual(failing, [
            "cadq-fit-gap-target-has-an-owner",
            "cadq-overhang-judgement-recomputable-from-shipped-columns",
        ])
        self.assertEqual(cross.main(["--check"]), 1)


class ThisPlaneRefusesToStamp(unittest.TestCase):
    """The boundary this plane already enforces: an envelope is consumer state, printability is theirs."""

    def test_a_producer_declared_envelope_is_refused(self) -> None:
        verdict = check_print_basis({"declaration": {"print": {"envelope": {"declared_by": "cadq", "x_mm": 250.0}}}})
        self.assertFalse(verdict["ok"])
        problems = " ".join(refusal["problem"] for refusal in verdict["refusals"])
        self.assertIn("envelope", problems)

    def test_a_consumer_declared_envelope_is_accepted(self) -> None:
        verdict = check_print_basis({"declaration": {"print": {"envelope": {"declared_by": "consumer", "x_mm": 250.0}}}})
        problems = " ".join(refusal["problem"] for refusal in verdict["refusals"])
        self.assertNotIn("machine state", problems)

    def test_a_producer_stamped_printability_verdict_is_refused(self) -> None:
        verdict = check_print_basis({"declaration": {"print": {"printable": True}}})
        self.assertFalse(verdict["ok"])
        problems = " ".join(refusal["problem"] for refusal in verdict["refusals"])
        self.assertIn("printability verdict", problems)


if __name__ == "__main__":
    unittest.main()
