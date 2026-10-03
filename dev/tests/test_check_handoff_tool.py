#!/usr/bin/env python3
"""The handoff checker's exit code must close (collaboration practice 16, applied to this repository).

A guard that returns a dictionary can be held and ignored; the tool exists so a shell can see the verdict.
These tests run it as a SUBPROCESS, because the property under test is the exit code of the process, not the
return value of a function — measuring it in-process would be exactly the "judgement computed and dropped"
shape this tool was written to prevent.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "dev" / "tools" / "check_handoff.py"
REAL = Path("/tmp/three-plane-drop/onshapescript-70piece-tessellation/manifest.json")

#: The tool imports the guards, which import numpy-free pure-Python modules only; the same PYTHONPATH the
#: offline suite uses is passed through so the run matches how the suite runs.
ENV = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "temp" / "browser-common-site"), "PATH": "/usr/bin:/bin"}


def minimal_handoff() -> dict:
    return {
        "units": "mm",
        "totals": {"areaMm2": 100.0},
        "declaration": {
            "schema": "onshapescript.handoff/0.4-draft",
            "identity": {"sha256": "a" * 64},
            "print": {
                "build_direction": [0.0, 0.0, 1.0],
                "threshold_deg": 45.0,
                "reference_point": "origin",
                "declared_by": "onshapescript",
                "envelope": {"declared_by": "consumer"},
                "min_wall": {"value_mm": None, "grade": "unknown", "reason": "no analyzer on this host"},
            },
            "geometry": {
                "identity_rule": {
                    "version": "onshapescript.mesh-set-signature/1",
                    "bounds_family": "tessellation_vertices(artifact_bytes)",
                    "equivalence_tolerance": {"brepVolumeMm3": 1e-6, "areaMm2": 1e-5},
                    "equivalence_tolerance_basis": {"brepVolumeMm3": "bitwise", "areaMm2": "reader spread"},
                    "equivalence_tolerance_vintage": {"readers": {"onshapescript": "9.8e-13"},
                                                      "taken": "2026-10-03", "witness": "referee",
                                                      "re_derive_when": "a reader changes"},
                },
                "parts": [{"index": 0, "brep": {"volume_mm3": 10.0},
                           "mesh": {"at": {"build_direction": [0.0, 0.0, 1.0], "threshold_deg": 45.0,
                                           "reference_point": "origin"},
                                    "orientation": {"applicable": True, "consistent": True},
                                    "overhangAreaMm2": 1.0}}],
            },
        },
    }


class CheckHandoffToolTest(unittest.TestCase):
    def _run(self, manifest: dict | None, *args: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "handoff.json"
            if manifest is not None:
                path.write_text(json.dumps(manifest), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(TOOL), str(path), *args],
                capture_output=True, text=True, env=ENV, cwd=str(ROOT), timeout=120,
            )

    def test_a_clean_handoff_exits_zero_and_says_what_it_did_not_check(self):
        result = self._run(minimal_handoff(), "--build-direction", "0,0,1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("verdict      : PASS", result.stdout)
        self.assertIn("no consumer readings supplied", result.stdout)
        self.assertIn("not_provided", result.stdout)
        self.assertIn("complete", result.stdout)

    def test_a_rule_that_did_not_run_is_not_a_pass(self):
        """MeshQ 198 §4's shape, closed here: an unevaluated rule cannot refuse, so it must fail loudly."""
        result = self._run(minimal_handoff())
        self.assertEqual(result.returncode, 1, "an incomplete check may not exit 0")
        self.assertIn("INCOMPLETE (rule 5 did not run)", result.stdout)
        self.assertIn("[print] NOT RUN rule 5", result.stdout)
        self.assertIn("close it:", result.stdout)
        self.assertIn("FAIL", result.stdout)
        self.assertNotIn("verdict      : PASS", result.stdout)

    def test_declaring_the_partial_check_is_the_only_way_it_reads_as_a_pass(self):
        result = self._run(minimal_handoff(), "--declaration-only")
        self.assertEqual(result.returncode, 0)
        self.assertIn("PASS (PARTIAL, accepted by --declaration-only)", result.stdout)

    def test_a_print_refusal_closes_the_exit_code(self):
        handoff = minimal_handoff()
        handoff["declaration"]["print"]["threshold_deg"] = 181
        handoff["declaration"]["geometry"]["parts"][0]["mesh"]["at"]["threshold_deg"] = 181
        result = self._run(handoff)
        self.assertEqual(result.returncode, 1)
        self.assertIn("REFUSED", result.stdout)
        self.assertIn("0 < threshold_deg <= 180", result.stdout)

    def test_an_identity_refusal_closes_the_exit_code(self):
        handoff = minimal_handoff()
        del handoff["declaration"]["geometry"]["identity_rule"]["equivalence_tolerance_vintage"]
        result = self._run(handoff)
        self.assertEqual(result.returncode, 1)
        self.assertIn("reader set", result.stdout)

    def test_the_caller_printing_elsewhere_is_refused_by_rule_5(self):
        result = self._run(minimal_handoff(), "--build-direction", "0,1,0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("print-fit §4 rule 5", result.stdout)

    def test_readings_that_do_not_match_are_reported_per_piece(self):
        readings = {"set": {"areaMm2": 100.0}, "pieces": [{"index": 0, "brepVolumeMm3": 10.0}]}
        with tempfile.TemporaryDirectory() as tmp:
            readings_path = Path(tmp) / "readings.json"
            readings_path.write_text(json.dumps(readings), encoding="utf-8")
            manifest_path = Path(tmp) / "handoff.json"
            manifest_path.write_text(json.dumps(minimal_handoff()), encoding="utf-8")
            ok = subprocess.run([sys.executable, str(TOOL), str(manifest_path), "--readings", str(readings_path),
                                 "--build-direction", "0,0,1"],
                                capture_output=True, text=True, env=ENV, cwd=str(ROOT), timeout=120)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            self.assertIn("quantities_within_declared_tolerance", ok.stdout)

            readings["pieces"][0]["brepVolumeMm3"] = 10.0 * 1.01
            readings_path.write_text(json.dumps(readings), encoding="utf-8")
            bad = subprocess.run([sys.executable, str(TOOL), str(manifest_path), "--readings", str(readings_path),
                                  "--build-direction", "0,0,1"],
                                 capture_output=True, text=True, env=ENV, cwd=str(ROOT), timeout=120)
            self.assertEqual(bad.returncode, 1)
            self.assertIn("outside", bad.stdout)

    def test_an_unreadable_input_is_a_different_exit_code_from_a_refusal(self):
        result = self._run(None)
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read the handoff manifest", result.stderr)

    def test_a_bad_directory_argument_is_refused_before_the_guards_run(self):
        result = self._run(minimal_handoff(), "--build-direction", "0,1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("three comma-separated numbers", result.stderr)

    @unittest.skipUnless(REAL.exists(), "the real 70-piece handoff is not in the drop directory")
    def test_the_real_handoff_passes_and_a_tampered_copy_does_not(self):
        clean = subprocess.run([sys.executable, str(TOOL), str(REAL), "--build-direction", "0,0,1"],
                               capture_output=True, text=True, env=ENV, cwd=str(ROOT), timeout=120)
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        self.assertIn("70", clean.stdout + clean.stderr)

        handoff = json.loads(REAL.read_text(encoding="utf-8"))
        tampered = copy.deepcopy(handoff)
        for piece in tampered["declaration"]["geometry"]["parts"]:
            piece["mesh"].pop("orientation", None)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tampered.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            bad = subprocess.run([sys.executable, str(TOOL), str(path), "--build-direction", "0,0,1"],
                                 capture_output=True, text=True, env=ENV, cwd=str(ROOT), timeout=120)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("rule 2", bad.stdout)


if __name__ == "__main__":
    unittest.main()
