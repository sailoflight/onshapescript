"""The contract is exercised against a **peer's real artifact**, not only against our own fixture.

The slice is MeshQ's contract probe (its repository, read-only for this plane). It is the
reconciliation the agreed order asked for: one delivery, end to end, judged by this plane's
runner. Two things are being measured here:

* the runner is **artifact-agnostic** (it does not only understand this plane's own manifest);
* the peer's raw output is verdict-shaped on purpose, and the contract's position is that a
  report carries **readings and grades**, so copying the peer's `pass` keys verbatim is refused.
"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dev.verification_report import adapters, rules, runner, slices  # noqa: E402

HAS_MESHQ_PROBE = (slices.MESHQ_SPHERE_COARSE / "meshq_result.json").exists()


def _flatten_keys(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _flatten_keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for value in node:
            yield from _flatten_keys(value, path)


@unittest.skipUnless(HAS_MESHQ_PROBE, "MeshQ's contract probe is not checked out beside this repo")
class PeerSlice(unittest.TestCase):
    def test_extraction_carries_readings_only(self) -> None:
        extracted = adapters.extract_meshq_result(
            slices.MESHQ_SPHERE_COARSE / "meshq_result.json",
            slices.MESHQ_SPHERE_COARSE / "meshq_job.json",
        )
        keys = set(_flatten_keys(extracted))
        self.assertFalse(keys & adapters.JUDGEMENT_KEYS, "an adapter never judges")
        self.assertNotIn("pass", keys, "the peer's verdicts stay in the peer's artifact")
        text = json.dumps(extracted)
        self.assertNotIn('"pass"', text)
        self.assertNotIn('"ok"', text)
        self.assertGreater(extracted["verdict_count"], 0, "the verdicts are counted, not silently dropped")

    def test_the_peer_slice_passes_the_runner_and_its_projection_machine_checks(self) -> None:
        report = slices.build_meshq_report()
        csv_text = runner.project_csv(report)
        self.assertTrue(slices.machine_check_projection(report, csv_text), "the CSV projection must be reproducible from the report")
        verdict = runner.check_report(report)
        self.assertTrue(verdict["ok"], verdict["refusals"])
        self.assertEqual(verdict["rulesNotRun"], [])
        self.assertEqual(len(verdict["rulesRun"]), len(rules.AGREED_RULE_IDS))

    def test_the_real_tessellation_and_spread_are_carried(self) -> None:
        report = slices.build_meshq_report()
        claims = {claim["id"]: claim for claim in report["claims"]}
        sphere = claims["c_S"]["readings"][0]
        self.assertIn("segments=12", sphere["family"])
        self.assertIn("rings=6", sphere["family"])
        self.assertEqual(sphere["achieved"]["absolute"], 2.827e-06)
        self.assertIsNotNone(sphere["achieved"]["relative"])
        self.assertTrue(all(claim.get("boundsAlgorithm") for name, claim in claims.items() if name.endswith("_bounds")))

    def test_a_report_that_copies_the_peers_verdicts_is_refused(self) -> None:
        report = slices.build_meshq_report()
        report["claims"][0]["verdicts"] = {"watertight": {"pass": True, "detail": "open_edges=0"}}
        verdict = runner.check_report(report)
        self.assertFalse(verdict["ok"], "a bare verdict field must be refused, even when it came from a real artifact")
        self.assertEqual(sorted({refusal["rule"] for refusal in verdict["refusals"]}), ["R9"])

    def test_the_peer_artifact_digest_is_the_real_file_digest(self) -> None:
        import hashlib

        report = slices.build_meshq_report()
        real = hashlib.sha256((slices.MESHQ_SPHERE_COARSE / "meshq_result.json").read_bytes()).hexdigest()
        self.assertEqual(report["artifact"]["sha256"], real)
        self.assertFalse(report["artifact"]["sha256_stable"], "the result JSON embeds timing fields, so its bytes move")
        self.assertTrue(report["artifact"]["sha256_stable_evidence"]["reason"])


if __name__ == "__main__":
    unittest.main()
