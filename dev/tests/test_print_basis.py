"""The refusing half of the print-fit interface (docs/roadmap/PRINT_FIT_INTERFACE_DRAFT.md §4).

The producer already emits the basis (`_print_block()` + `parts[].mesh.at`); these tests pin what a
consumer does with a manifest that does NOT, because a boundary that cannot say "no" is a convention.
"""

import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from fdm_analysis.conversion.print_basis import check_print_basis  # noqa: E402


def piece(index: int, *, at: bool = True, applicable: bool = True, overhang: float | None = 1.0) -> dict:
    mesh = {"overhangAreaMm2": overhang, "bedContactAreaMm2": 2.0,
            "orientation": {"applicable": applicable, "consistent": applicable}}
    if at:
        mesh["at"] = {"build_direction": [0.0, 0.0, 1.0], "threshold_deg": 45.0,
                      "reference_point": "origin", "covers": ["overhangAreaMm2"]}
    return {"index": index, "mesh": mesh}


def manifest(*, pieces=None, block=None) -> dict:
    default_block = {
        "build_direction": [0.0, 0.0, 1.0], "declared_by": "onshapescript", "threshold_deg": 45.0,
        "reference_point": "origin",
        "envelope": {"declared_by": "consumer", "source": None, "x_mm": None, "y_mm": None, "z_mm": None},
        "min_wall": {"value_mm": None, "grade": "unknown", "reason": "no thickness analyzer here"},
    }
    return {"declaration": {"print": default_block if block is None else block,
                            "geometry": {"parts": [piece(0)] if pieces is None else pieces}}}


class PrintBasisGuardTest(unittest.TestCase):
    def test_the_producers_own_shape_passes(self):
        result = check_print_basis(manifest())
        self.assertTrue(result["ok"], result["refusals"])
        self.assertEqual(result["basis"]["build_direction"], [0.0, 0.0, 1.0])
        self.assertEqual(result["basis"]["threshold_deg"], 45.0)
        self.assertEqual(result["basis"]["envelope_declared_by"], "consumer")
        # The guard returns READINGS and never a verdict: printability is the caller's comparison.
        self.assertIn("never a verdict", result["note"])
        self.assertEqual(result["readings"]["overhangAreaMm2"], {"0": 1.0})

    def test_a_missing_basis_is_refused_even_when_every_reading_is_null(self):
        result = check_print_basis(manifest(pieces=[piece(0, at=False, overhang=None)]))
        self.assertFalse(result["ok"])
        self.assertEqual(result["refusals"][0]["rule"], "print-fit §4 rule 1")
        self.assertIn("parts[0].mesh.at", result["refusals"][0]["where"])

    def test_a_per_piece_basis_that_contradicts_the_declaration_is_refused(self):
        conflicting = piece(0)
        conflicting["mesh"]["at"]["build_direction"] = [0.0, 1.0, 0.0]
        result = check_print_basis(manifest(pieces=[conflicting]))
        self.assertFalse(result["ok"])
        self.assertIn("one basis per artifact", result["refusals"][0]["required_fix"])

    def test_a_producer_stamped_verdict_is_refused_and_so_is_a_foreign_envelope(self):
        block = copy.deepcopy(manifest()["declaration"]["print"])
        block["printable"] = True
        block["envelope"]["declared_by"] = "cadq"
        result = check_print_basis(manifest(block=block))
        rules = [r["rule"] for r in result["refusals"]]
        self.assertEqual(rules.count("print-fit §4 rule 3"), 2)

    def test_a_thickness_value_under_an_unknown_grade_is_a_contradiction(self):
        block = copy.deepcopy(manifest()["declaration"]["print"])
        block["min_wall"] = {"value_mm": 1.2, "grade": "unknown"}
        result = check_print_basis(manifest(block=block))
        self.assertFalse(result["ok"])
        self.assertEqual(result["refusals"][0]["rule"], "print-fit §4 rule 4")

    def test_reusing_readings_at_another_build_direction_is_refused(self):
        result = check_print_basis(manifest(), build_direction=[0.0, 1.0, 0.0])
        self.assertFalse(result["ok"])
        self.assertEqual(result["refusals"][0]["rule"], "print-fit §4 rule 5")
        self.assertIn("re-take", result["refusals"][0]["required_fix"])
        # ... and the caller's own direction is accepted without complaint.
        self.assertTrue(check_print_basis(manifest(), build_direction=[0.0, 0.0, 1.0])["ok"])

    def test_a_direction_derived_reading_on_a_non_applicable_winding_is_refused(self):
        result = check_print_basis(manifest(pieces=[piece(0, applicable=False)]))
        self.assertFalse(result["ok"])
        self.assertEqual(result["refusals"][0]["rule"], "print-fit §4 rule 2")
        self.assertIn("vacuously-consistent", result["refusals"][0]["required_fix"])


if __name__ == "__main__":
    unittest.main()
