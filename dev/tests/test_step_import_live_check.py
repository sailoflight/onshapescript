#!/usr/bin/env python3
"""The operator-facing live check must not round anything up.

The tool exists to make one human step short. Its risk is the opposite of a normal tool's: it is read by
someone who wants to be done, so every field it prints must be labelled by what was actually observed. These
tests pin the labelling — `unproven` is a first-class verdict here, and a missing observation must never print
as a pass.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "dev" / "tools" / "step_import_live_check.py"
ENV = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "temp" / "browser-common-site"),
       "PATH": "/usr/bin:/bin"}

spec = importlib.util.spec_from_file_location("step_import_live_check", TOOL)
live_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live_check)

SOURCE = b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n"


def landed_result(**overrides):
    result = {
        "imported": True,
        "reason": "new_tab_landed",
        "translationCompleted": "assumed",
        "source": {"path": "/tmp/h.step", "sha256": "a" * 64, "addressedBy": "sha256",
                   "expectedSha256": "a" * 64, "matchesExpected": True},
        "importEntry": {"clicked": True, "label": "Import"},
        "pageFacts": {"url": "https://cad.onshape.com/x", "tabNames": ["Part Studio 1", "handoff"]},
        "newRows": [{"name": "handoff", "elementId": "eid2"}],
        "selectorsUsed": {"tabBar": ".os-tab-bar-tab"},
        "unverifiedSelectors": ["dialog", "fileInput"],
    }
    result.update(overrides)
    return result


class ReportLabellingTest(unittest.TestCase):
    def _rows(self, result):
        return dict((row[0], row[1]) for row in live_check._report(result)[0])

    def test_a_complete_landing_reports_the_checks_it_could_observe(self):
        _, failures = live_check._report(landed_result())
        rows = self._rows(landed_result())
        self.assertEqual(failures, 0)
        self.assertEqual(rows["I1"], "pass")
        self.assertEqual(rows["I3"], "pass")
        self.assertEqual(rows["I6"], "pass")

    def test_a_missing_observation_is_unproven_rather_than_a_pass(self):
        rows = self._rows(landed_result(pageFacts={}, selectorsUsed={}, source={"sha256": "a" * 64}))
        self.assertEqual(rows["I2"], "unproven", "no page facts were read, so the tab names are unproven")
        self.assertEqual(rows["I4"], "unproven")
        self.assertEqual(rows["I6"], "unproven",
                         "a run with no declared digest may not report the addressing check as passed")

    def test_an_entry_that_was_never_found_is_a_failure_with_its_reason(self):
        result = landed_result(importEntry={"clicked": False}, imported=False, reason="import_entry_missing")
        rows = self._rows(result)
        _, failures = live_check._report(result)
        # Two checks fail honestly: the entry was never found AND nothing landed. Neither is rounded up.
        self.assertEqual(failures, 2)
        self.assertEqual(rows["I1"], "fail")
        self.assertEqual(rows["I3"], "fail")

    def test_a_translation_that_only_finished_half_way_is_not_a_landing(self):
        result = landed_result(imported=False, reason=None, translationCompleted="unknown", newRows=[])
        rows = self._rows(result)
        _, failures = live_check._report(result)
        self.assertEqual(failures, 1)
        self.assertEqual(rows["I3"], "fail")
        self.assertIn("translationCompleted=unknown", dict((row[0], row[2]) for row in live_check._report(result)[0])["I3"])


class PlanOnlyPathTest(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                              env=ENV, cwd=str(ROOT), timeout=120)

    def _source(self, tmp: Path) -> Path:
        path = tmp / "handoff.step"
        path.write_bytes(SOURCE)
        return path

    def test_the_default_run_is_local_and_says_what_it_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            digest = hashlib.sha256(SOURCE).hexdigest()
            result = self._run("--source", str(source), "--expect-sha256", digest)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DRY RUN — no browser, no page, no cloud mutation", result.stdout)
        self.assertIn("addressed by: sha256", result.stdout)
        self.assertIn("estimated REST requests: 0", result.stdout)
        self.assertIn("importEntryLabels", result.stdout, "the unverified selectors are the point")
        self.assertIn("I6", result.stdout)

    def test_a_delivery_that_is_not_the_addressed_bytes_refuses_before_any_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            result = self._run("--source", str(source), "--expect-sha256", "0" * 64)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not the addressed artifact", result.stderr)

    def test_a_real_import_without_a_target_is_refused_before_the_session_starts(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            result = self._run("--source", str(source), "--confirm-browser")
        self.assertEqual(result.returncode, 2)
        self.assertIn("never creates a document", result.stderr)
        self.assertNotIn("DRY RUN", result.stdout)

    def test_a_missing_source_is_its_own_exit_code_from_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run("--source", str(Path(tmp) / "nope.step"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot be imported", result.stderr)


if __name__ == "__main__":
    unittest.main()
