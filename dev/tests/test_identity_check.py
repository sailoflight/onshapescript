"""The consumer's side of the identity rule, exercised against the REAL 70-piece handoff.

Every test here reads `/tmp/three-plane-drop/onshapescript-70piece-tessellation/manifest.json` when it is
present and skips otherwise: the point is that the checker is measured against a real artifact and not only
against a fixture this file wrote. The synthetic cases then vary ONE thing at a time (a unit, a rule
version, a scale, a family) so the failure is attributable.
"""

import copy
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from fdm_analysis.conversion.identity_check import check_identity_against  # noqa: E402

REAL = pathlib.Path("/tmp/three-plane-drop/onshapescript-70piece-tessellation/manifest.json")


def synthetic() -> dict:
    return {
        "units": "mm",
        "totals": {"areaMm2": 2796354.139889901},
        "declaration": {
            "identity": {"sha256": "abc"},
            "geometry": {
                "identity_rule": {
                    "version": "onshapescript.mesh-set-signature/1",
                    "bounds_family": "tessellation_vertices(artifact_bytes)",
                    "equivalence_tolerance": {"brepVolumeMm3": 1e-6, "bounds_mm": 1e-3, "areaMm2": 1e-5},
                    "equivalence_tolerance_basis": {"brepVolumeMm3": "bitwise", "bounds_mm": "family",
                                                    "areaMm2": "reader spread"},
                },
                "parts": [
                    {"index": 0, "brep": {"volume_mm3": 324.58775714774686},
                     "bounds_mm": {"max": [7.0, 380.0, 86.0]}},
                    {"index": 1, "brep": {"volume_mm3": 324.58775714774686},
                     "bounds_mm": {"max": [7.0, 380.0, 86.0]}},
                ],
            },
        },
    }


class IdentityCheckTest(unittest.TestCase):
    def test_a_matching_consumer_is_accepted_and_reports_the_worst_piece(self):
        result = check_identity_against(
            synthetic(),
            units="mm",
            identity_rule_version="onshapescript.mesh-set-signature/1",
            set_readings={"areaMm2": 2796354.139889901},
            piece_readings=[{"index": 0, "brepVolumeMm3": 324.58775714774686,
                             "bounds_mm": {"max": [7.0, 380.0, 86.0]}},
                            {"index": 1, "brepVolumeMm3": 324.58775714774686,
                             "bounds_mm": {"max": [7.0, 380.0, 86.0]}}],
            set_signature_sha256="abc",
        )
        self.assertTrue(result["ok"], result["refusals"])
        self.assertEqual(result["identityLevel"], "quantities_within_declared_tolerance")
        self.assertEqual(result["verdicts"]["brepVolumeMm3"]["piecesCompared"], 2)
        self.assertEqual(result["verdicts"]["brepVolumeMm3"]["worstPiece"]["difference"], 0.0)
        self.assertIn("never as an aggregate alone", result["verdicts"]["brepVolumeMm3"]["note"])
        self.assertEqual(result["digest"]["status"], "equal")
        self.assertIn("not geometric identity", result["note"])

    def test_a_unit_mismatch_is_a_refusal_not_a_scale_factor(self):
        result = check_identity_against(synthetic(), units="inch",
                                        set_readings={"areaMm2": 2796354.139889901})
        self.assertFalse(result["ok"])
        self.assertIn("25.4x", result["refusals"][0]["required_fix"])

    def test_a_rule_version_mismatch_refuses_to_compare_digests(self):
        result = check_identity_against(synthetic(), identity_rule_version="other/9",
                                        set_readings={"areaMm2": 2796354.139889901},
                                        set_signature_sha256="abc")
        self.assertFalse(result["ok"])
        self.assertEqual(result["digest"]["status"], "not_comparable")

    def test_a_scaled_reading_lands_outside_the_declared_bound(self):
        result = check_identity_against(
            synthetic(), units="mm",
            set_readings={"areaMm2": 2796354.139889901 * 1.0001},
            piece_readings=[{"index": 0, "brepVolumeMm3": 324.58775714774686}],
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["identityLevel"], "quantities_outside_declared_tolerance")
        self.assertEqual(result["verdicts"]["areaMm2"]["status"], "outside")

    def test_one_piece_outside_is_reported_with_its_index_and_count(self):
        readings = [{"index": 0, "brepVolumeMm3": 324.58775714774686},
                    {"index": 1, "brepVolumeMm3": 324.58775714774686 * 1.001}]
        result = check_identity_against(synthetic(), piece_readings=readings)
        self.assertFalse(result["ok"])
        entry = result["verdicts"]["brepVolumeMm3"]
        self.assertEqual((entry["piecesCompared"], entry["piecesOutside"]), (2, 1))
        self.assertEqual(entry["outsideListed"][0]["index"], 1)
        self.assertEqual(entry["worstPiece"]["index"], 1)

    def test_an_undeclared_bounds_family_is_refused_rather_than_guessed(self):
        handoff = synthetic()
        handoff["declaration"]["geometry"]["identity_rule"]["bounds_family"] = "some_other_box"
        result = check_identity_against(handoff, piece_readings=[{"index": 0, "bounds_mm": {"max": [7, 380, 86]}}])
        entry = result["verdicts"]["bounds_mm"]
        self.assertEqual(entry["status"], "not_compared")
        self.assertIn("some_other_box", entry["reason"])
        # and it is not reported as agreement
        self.assertEqual(result["identityLevel"], "not_comparable")

    def test_a_tolerance_without_its_measurement_is_refused(self):
        handoff = synthetic()
        del handoff["declaration"]["geometry"]["identity_rule"]["equivalence_tolerance_basis"]["areaMm2"]
        result = check_identity_against(handoff, set_readings={"areaMm2": 1.0})
        self.assertFalse(result["ok"])
        self.assertIn("fails correct peers", result["refusals"][0]["required_fix"])

    @unittest.skipUnless(REAL.exists(), "the real 70-piece handoff is not in the drop directory")
    def test_the_real_handoff_is_compared_piece_by_piece(self):
        handoff = json.loads(REAL.read_text(encoding="utf-8"))
        parts = handoff["declaration"]["geometry"]["parts"]
        result = check_identity_against(
            handoff,
            units="mm",
            identity_rule_version=handoff["declaration"]["geometry"]["identity_rule"]["version"],
            set_readings={"areaMm2": handoff["totals"]["areaMm2"]},
            piece_readings=[{"index": part["index"], "brepVolumeMm3": part["brep"]["volume_mm3"],
                             "bounds_mm": part["bounds_mm"]} for part in parts],
            set_signature_sha256=handoff["declaration"]["identity"]["sha256"],
        )
        self.assertTrue(result["ok"], result["refusals"])
        self.assertEqual(result["verdicts"]["brepVolumeMm3"]["piecesCompared"], 70)
        self.assertEqual(result["verdicts"]["brepVolumeMm3"]["piecesOutside"], 0)
        self.assertEqual(result["verdicts"]["bounds_mm"]["piecesOutside"], 0)
        self.assertEqual(result["digest"]["status"], "equal")
        # ... and a 0.1 % shift of every volume is caught, per piece, with the worst index reported.
        shifted = copy.deepcopy(parts)
        bad = [{"index": part["index"], "brepVolumeMm3": part["brep"]["volume_mm3"] * 1.001,
                "bounds_mm": part["bounds_mm"]} for part in shifted]
        caught = check_identity_against(handoff, piece_readings=bad)
        entry = caught["verdicts"]["brepVolumeMm3"]
        self.assertEqual(entry["piecesOutside"], 70)
        self.assertIsNotNone(entry["worstPiece"]["index"])


if __name__ == "__main__":
    unittest.main()
