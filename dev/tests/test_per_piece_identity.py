"""Per-piece identity cross-read: how each plane's real record addresses a piece."""
from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "per_piece_identity_cross_read", ROOT / "dev" / "tools" / "per_piece_identity_cross_read.py"
)
cross = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cross)

_HAS_RECORDS = cross.MESHQ_RESULT.is_file() and cross.CADQ_MANIFEST.is_file()


@unittest.skipUnless(_HAS_RECORDS, "the peers' records are not checked out beside this repo")
class PerPieceIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = cross.facts()

    def test_cadq_gives_every_solid_a_digest_and_says_the_digest_is_measured_stable(self) -> None:
        cadq = self.report["cadq"]
        self.assertEqual(cadq["solids"], 70)
        self.assertEqual(cadq["per_solid_digests"], 70)
        self.assertEqual(cadq["per_solid_stability"], ["True"])
        self.assertEqual(cadq["stability_basis"], ["measured"])

    def test_cadq_ships_the_label_field_but_every_value_is_null(self) -> None:
        cadq = self.report["cadq"]
        self.assertEqual(cadq["labels_present"], cadq["solids"])
        self.assertEqual(cadq["labels_null"], cadq["solids"], "a human label appeared -- update the finding")

    def test_meshq_addresses_by_export_artifact_not_by_piece(self) -> None:
        meshq = self.report["meshq"]
        self.assertEqual(len(meshq["output_digests"]), 1)
        self.assertEqual(meshq["declared_coverage"], [["block"]], "its digest declares which objects it covers")
        self.assertEqual(meshq["output_stability"], [True])

    def test_meshq_publishes_a_host_absolute_path_beside_its_digest(self) -> None:
        meshq = self.report["meshq"]
        self.assertEqual(len(meshq["absolute_paths"]), 1)
        self.assertTrue(meshq["absolute_paths"][0].startswith("/home/"), "a portable address cannot be a host path")

    def test_the_two_measured_gaps_are_reported_rather_than_passing_silently(self) -> None:
        self.assertFalse(self.report["ok"])
        failing = sorted(r["rule"] for r in self.report["rules"] if not r["passed"])
        self.assertEqual(failing, [
            "a-piece-names-its-label-or-says-null-explicitly",
            "the-record-states-which-address-is-authoritative",
        ])
        self.assertEqual(cross.main(["--check"]), 1)

    def test_this_planes_own_record_answers_all_five_questions(self) -> None:
        own = self.report["thisPlane"]
        self.assertTrue(all(own.values()), own)


if __name__ == "__main__":
    unittest.main()
