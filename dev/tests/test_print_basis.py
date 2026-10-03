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

    def test_the_field_is_absent_paths_are_as_loud_as_the_false_ones(self):
        """MeshQ 182 ran ten adversarial variants against the first version of this guard: six were
        blocked, four passed SILENTLY, and all four were one family -- *field absent, rule evaporates*.
        The fixture in this file helped hide it: `piece()` always filled every field, so the absence path
        had never been constructed. These are its four variants, each now refused.
        """
        # D: the whole orientation block deleted, direction-derived readings kept.
        deleted = piece(0)
        deleted["mesh"].pop("orientation")
        result = check_print_basis(manifest(pieces=[deleted]))
        self.assertFalse(result["ok"], "a deleted orientation verdict must be as loud as a false one")
        self.assertEqual(result["refusals"][0]["rule"], "print-fit §4 rule 2")
        self.assertIn("undeclared is not OK", result["refusals"][0]["required_fix"])

        # E: applicable = null ("unknown" read as "nothing to complain about").
        unknown = piece(0)
        unknown["mesh"]["orientation"] = {"applicable": None, "consistent": None}
        self.assertFalse(check_print_basis(manifest(pieces=[unknown]))["ok"])

        # F: a silent `unknown` -- a skipped reading with no stated reason.
        silent = copy.deepcopy(manifest()["declaration"]["print"])
        silent["min_wall"] = {"value_mm": None, "grade": "unknown"}
        self.assertFalse(check_print_basis(manifest(block=silent))["ok"])
        noisy = copy.deepcopy(silent)
        noisy["min_wall"]["reason"] = "no thickness analyzer is installed on this host"
        self.assertTrue(check_print_basis(manifest(block=noisy))["ok"])

        # K: both reference points null -- the reference point decides whether a direction defect is
        # observable at all, so a null one is an incomplete basis, not a neutral default.
        no_ref = copy.deepcopy(manifest()["declaration"]["print"])
        no_ref["reference_point"] = None
        result = check_print_basis(manifest(block=no_ref))
        self.assertFalse(result["ok"])
        self.assertIn("observable", result["refusals"][0]["required_fix"])

    def test_a_truthy_substitute_does_not_pass_for_a_winding_verdict(self):
        """MeshQ 187: `applicable: 0` and `applicable: "false"` passed the previous version.

        The first version refused absence and `null` in one branch and a literal `False` in another, so
        every value in between -- including a JSON 0 and the string "false", both natural for a non-Python
        producer -- read as agreement. That is the rule inverted by a type: a producer declaring "not
        applicable" obtained a pass. The verdict must be *literally* true.
        """
        for substitute in (0, "false", "no", 1, "true", [], {}):
            with self.subTest(applicable=substitute):
                substituted = piece(0)
                substituted["mesh"]["orientation"] = {"applicable": substitute, "consistent": True}
                result = check_print_basis(manifest(pieces=[substituted]))
                self.assertFalse(result["ok"], f"{substitute!r} must not read as a winding verdict")
                self.assertEqual(result["refusals"][0]["rule"], "print-fit §4 rule 2")
                self.assertIn("not literally true", result["refusals"][0]["problem"])
            # and the same for a substituted `consistent`
            with self.subTest(consistent=substitute):
                substituted = piece(0)
                substituted["mesh"]["orientation"] = {"applicable": True, "consistent": substitute}
                self.assertFalse(check_print_basis(manifest(pieces=[substituted]))["ok"])

    def test_an_honest_false_is_still_told_the_truth_about_its_own_fix(self):
        """A literal false is a different failure from a wrong type, and must say so."""
        honest = piece(0)
        honest["mesh"]["orientation"] = {"applicable": False, "consistent": False}
        result = check_print_basis(manifest(pieces=[honest]))
        self.assertFalse(result["ok"])
        self.assertIn("vacuously-consistent", result["refusals"][0]["required_fix"])

    def test_the_raw_value_is_validated_before_it_is_converted(self):
        """MeshQ 187: converting first and validating afterwards made the finiteness half dead code.

        `[float(v) for v in raw]` then `isinstance(v, (int, float))` over the conversion's own output can
        never fail, so strings and bools passed and finiteness was never checked at all. Reported honestly:
        MeshQ also said its NaN probe was itself unclean (it reused one list object, where CPython's
        comparison takes an identity fast path), so NaN is tested here rather than assumed.
        """
        bad_directions = (["0", "0", "1"], [0, 0, True], [0, 0, float("inf")], [0, 0, float("nan")],
                          [0, 0], [0, 0, 1, 0], "0,0,1", None)
        for bad in bad_directions:
            with self.subTest(direction=bad):
                block = copy.deepcopy(manifest()["declaration"]["print"])
                block["build_direction"] = bad
                result = check_print_basis(manifest(block=block))
                self.assertFalse(result["ok"], f"{bad!r} is not a direction")
                self.assertIn("three finite JSON numbers", result["refusals"][0]["problem"])

        # A non-finite threshold is refused as itself, not as a per-piece mismatch.
        block = copy.deepcopy(manifest()["declaration"]["print"])
        block["threshold_deg"] = float("nan")
        result = check_print_basis(manifest(block=block))
        self.assertFalse(result["ok"])
        self.assertIn("threshold", result["refusals"][0]["where"])

        # A valid direction expressed as numbers still passes (no false positive).
        block = copy.deepcopy(manifest()["declaration"]["print"])
        block["build_direction"] = [0, 0, 1]
        self.assertTrue(check_print_basis(manifest(block=block))["ok"])

    def test_a_threshold_outside_its_only_meaningful_range_is_refused(self):
        """MeshQ 189 §3: `0`, `181`, `1e9` and `-45` all passed the first version of this guard.

        An overhang threshold is an angle from the build direction, so it lives in `(0, 180]`; outside that
        the reading is not looser or stricter, it is meaningless — and "an empty reading looks like a healthy
        certificate". The peer plane already enforced this; the guard now does too, at both levels.
        """
        for bad in (0, 181, 1e9, -45, 180.5, float("inf")):
            with self.subTest(threshold=bad):
                block = copy.deepcopy(manifest()["declaration"]["print"])
                block["threshold_deg"] = bad
                result = check_print_basis(manifest(block=block))
                self.assertFalse(result["ok"], f"threshold {bad!r} must be refused")
                self.assertIn("threshold", result["refusals"][0]["where"])

        # The endpoints that DO mean something still pass.
        for good in (0.001, 45, 90, 180):
            with self.subTest(threshold=good):
                block = copy.deepcopy(manifest()["declaration"]["print"])
                block["threshold_deg"] = good
                pieces = [piece(0)]
                pieces[0]["mesh"]["at"]["threshold_deg"] = good
                self.assertTrue(check_print_basis(manifest(block=block, pieces=pieces))["ok"])

        # A per-piece threshold outside the range is refused as itself, not as a mismatch.
        odd = piece(0)
        odd["mesh"]["at"]["threshold_deg"] = 181
        result = check_print_basis(manifest(pieces=[odd]))
        self.assertFalse(result["ok"])
        self.assertIn("one range for one kind of reading", result["refusals"][0]["required_fix"])

    def test_a_per_piece_basis_with_the_wrong_kind_of_value_is_refused_as_such(self):
        odd = piece(0)
        odd["mesh"]["at"]["build_direction"] = ["0", "0", "1"]
        result = check_print_basis(manifest(pieces=[odd]))
        self.assertFalse(result["ok"])
        self.assertEqual(result["refusals"][0]["rule"], "print-fit §4 rule 1")
        self.assertIn("not finite", result["refusals"][0]["problem"])

        nonfinite = piece(1)
        nonfinite["mesh"]["at"]["threshold_deg"] = float("inf")
        self.assertFalse(check_print_basis(manifest(pieces=[nonfinite]))["ok"])

    def test_the_ten_adversarial_variants_have_the_outcomes_meshq_measured(self):
        """The whole variant set, so the guard cannot regress into "six of ten" again."""
        blocked = {}

        blocked["A_real"] = check_print_basis(manifest())["ok"]
        blocked["B_other_direction"] = check_print_basis(manifest(), build_direction=[0.0, 1.0, 0.0])["ok"]

        null_block = {key: None for key in manifest()["declaration"]["print"]}
        blocked["C_null_print_block"] = check_print_basis(manifest(block=null_block))["ok"]
        blocked["I_empty_print_block"] = check_print_basis(manifest(block={}))["ok"]
        self.assertFalse(blocked["C_null_print_block"])
        self.assertFalse(blocked["I_empty_print_block"])

        stamped = copy.deepcopy(manifest()["declaration"]["print"])
        stamped["printable"] = True
        blocked["G_producer_verdict"] = check_print_basis(manifest(block=stamped))["ok"]

        foreign = copy.deepcopy(manifest()["declaration"]["print"])
        foreign["envelope"]["declared_by"] = "cadq"
        blocked["J_foreign_envelope"] = check_print_basis(manifest(block=foreign))["ok"]

        no_at = piece(0)
        no_at["mesh"].pop("at")
        blocked["H_no_at"] = check_print_basis(manifest(pieces=[no_at]))["ok"]

        # A passes; every other variant must be refused.
        self.assertTrue(blocked.pop("A_real"))
        self.assertEqual(set(blocked), {"B_other_direction", "C_null_print_block", "G_producer_verdict",
                                        "H_no_at", "I_empty_print_block", "J_foreign_envelope"})
        self.assertFalse(any(blocked.values()), blocked)

    def test_a_direction_derived_reading_on_a_non_applicable_winding_is_refused(self):
        result = check_print_basis(manifest(pieces=[piece(0, applicable=False)]))
        self.assertFalse(result["ok"])
        self.assertEqual(result["refusals"][0]["rule"], "print-fit §4 rule 2")
        self.assertIn("vacuously-consistent", result["refusals"][0]["required_fix"])


if __name__ == "__main__":
    unittest.main()
