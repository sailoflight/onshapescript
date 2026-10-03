"""Third-plane cross-read: CadQ's real delivery, read offline by this plane's own implementation."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev"))

from dev.verification_report import adapters  # noqa: E402

CADQ_DIR = adapters.CADQ_THREE_PLANE
_HAS_CADQ = CADQ_DIR.is_dir() and any(CADQ_DIR.glob("*/manifest.json"))

_spec = importlib.util.spec_from_file_location(
    "cadq_tessellation_cross_check", ROOT / "dev" / "tools" / "cadq_tessellation_cross_check.py"
)
cross_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cross_check)


@unittest.skipUnless(_HAS_CADQ, "CadQ's three-plane delivery is not checked out beside this repo")
class CadQCrossReadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = cross_check.facts(CADQ_DIR)
        cls.variants = sorted(cls.report["variants"], key=lambda v: v["angular_tolerance_rad"])

    def test_every_rule_passes_on_the_real_delivery(self) -> None:
        for rule in self.report["rules"]:
            with self.subTest(rule=rule["rule"], where=rule["where"]):
                self.assertTrue(rule["passed"], rule["detail"])
        self.assertTrue(self.report["ok"])

    def test_an_independent_recomputation_corroborates_the_declared_bound(self) -> None:
        for variant in self.variants:
            totals = variant["totals"]
            with self.subTest(variant=variant["directory"]):
                self.assertLessEqual(totals["measured_vs_declared_relative"], cross_check.DECLARED_ACHIEVED_RELATIVE)
                self.assertLessEqual(totals["worst_part_relative"], cross_check.DECLARED_ACHIEVED_RELATIVE)
                self.assertEqual(totals["part_count"], 70)

    def test_the_declared_bound_is_not_explained_by_summation_order(self) -> None:
        """CadQ's own explanation for the 2.4e-6 residual was `+=` vs `fsum`. Measured: it is not."""
        for variant in self.variants:
            with self.subTest(variant=variant["directory"]):
                self.assertLess(variant["totals"]["worst_summation_order_relative"], 1e-11)
                ratio = (cross_check.DECLARED_ACHIEVED_RELATIVE
                         / variant["totals"]["worst_summation_order_relative"])
                self.assertGreater(ratio, 1e4, "summation order must be orders of magnitude below the residual")

    def test_the_worst_part_is_the_farthest_from_the_origin(self) -> None:
        """Float32 vertices lose absolute precision with coordinate magnitude, so the worst part is far away."""
        for variant in self.variants:
            with self.subTest(variant=variant["directory"]):
                worst = max(variant["parts"], key=lambda p: p["measured_vs_declared"])
                self.assertEqual(worst["index"], variant["totals"]["worst_part_index"])
                self.assertGreater(worst["farthest_mm"], 300.0)

    def test_the_aggregate_hides_the_worst_part(self) -> None:
        for variant in self.variants:
            with self.subTest(variant=variant["directory"]):
                self.assertGreater(variant["totals"]["worst_part_relative"],
                                   10 * variant["totals"]["measured_vs_declared_relative"])

    def test_the_signature_is_tolerance_independent_and_triangles_are_not(self) -> None:
        self.assertEqual(len({v["signature"] for v in self.variants}), 1)
        counts = sorted(v["triangle_count"] for v in self.variants)
        self.assertLess(counts[0], counts[-1])

    def test_a_looser_tolerance_costs_accuracy_not_just_triangles(self) -> None:
        """`variants` is sorted by angular tolerance, so the first is the FINEST, not the coarsest."""
        fine, coarse = self.variants[0], self.variants[-1]
        self.assertLess(fine["angular_tolerance_rad"], coarse["angular_tolerance_rad"])
        self.assertGreater(fine["triangle_count"], coarse["triangle_count"])
        self.assertLess(fine["totals"]["measured_vs_brep_relative"],
                        coarse["totals"]["measured_vs_brep_relative"])


@unittest.skipUnless(_HAS_CADQ, "CadQ's three-plane delivery is not checked out beside this repo")
class CadQExtractionTest(unittest.TestCase):
    def test_extraction_reports_the_third_plane_without_judging_it(self) -> None:
        manifest = sorted(CADQ_DIR.glob("*/manifest.json"))[0]
        fields = adapters.extract_cadq_manifest(manifest)
        self.assertEqual(fields["producer_plane"], "cadq")
        self.assertEqual(fields["units"], "mm")
        self.assertEqual(fields["solid_count"], 70)
        self.assertEqual(fields["declared_solid_count"], 70)
        self.assertEqual(len(fields["source_sha256"]), 64)
        self.assertEqual(fields["tolerance_declared_by"], "cadq")
        self.assertEqual(fields["tolerance_used_by"], "meshq")
        self.assertIs(fields["independent_kernel"], False)
        self.assertEqual(len(fields["solids"]), 70)
        self.assertEqual(sum(1 for s in fields["solids"] if len(str(s["sha256"])) == 64), 70)

    def test_the_sniffer_names_the_third_plane_instead_of_this_planes_adapter(self) -> None:
        from dev.verification_report import runner
        manifest = sorted(CADQ_DIR.glob("*/manifest.json"))[0]
        sniffed = runner.sniff_schema(__import__("json").loads(manifest.read_text(encoding="utf-8")))
        self.assertEqual(sniffed["kind"], "producer_record")
        self.assertEqual(sniffed["plane"], "cadq")
        self.assertEqual(sniffed["adapter"], "dev.verification_report.adapters.extract_cadq_manifest")


if __name__ == "__main__":
    unittest.main()
