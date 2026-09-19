#!/usr/bin/env python3
"""Offline stub-DOM tests for the Feature Studio notice collector.

The collector is a JavaScript string handed to Playwright, so no Python test can
execute it. These tests run the exact production string
(``onshape_browser_mode.actions.FS_NOTICE_SNAPSHOT_JS``) against a minimal DOM
stub in node via ``dev/tools/fs_notice_collector_probe.mjs``.

No browser, no page, no Onshape REST call, and no quota: the DOM is built in the
probe, and the assertions live here. The suite skips when node is unavailable
rather than pretending the collector is covered.

The final test class covers the Python side of the same observation: that the
production string is the one actually sent to the page, that the raw notice rows
stay unedited, and that the derived compile status carries the normalized code
and the frequency summary.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_browser_mode import actions, selectors  # noqa: E402

PROBE = ROOT / "dev" / "tools" / "fs_notice_collector_probe.mjs"
NODE = shutil.which("node")

SELECTORS = {
    "toggle": selectors.FS_NOTICE_TOGGLE,
    "content": selectors.FS_NOTICE_CONTENT,
    "table": selectors.FS_NOTICE_TABLE,
    "message": selectors.FS_NOTICE_MESSAGE,
    "line": selectors.FS_NOTICE_LINE,
    "column": selectors.FS_NOTICE_COLUMN,
}


@unittest.skipUnless(NODE, "node is not available to run the stub-DOM probe")
class NoticeCollectorProbeTest(unittest.TestCase):
    maxDiff = None

    def collect(self, scenario: str) -> dict:
        """Run the production collector string against one stub scenario."""
        payload = {
            "js": actions.FS_NOTICE_SNAPSHOT_JS,
            "selectors": SELECTORS,
            "scenario": scenario,
        }
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "scenario.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            completed = subprocess.run(
                [NODE, str(PROBE), str(input_path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(completed.stdout.strip(), completed.stderr)
        parsed = json.loads(completed.stdout)
        self.assertNotIn("error", parsed, parsed.get("error"))
        self.assertEqual(parsed["scenario"], scenario)
        return parsed["result"]

    def test_empty_surface_reports_nothing_found(self) -> None:
        result = self.collect("empty-surface")
        self.assertFalse(result["found"])
        self.assertFalse(result["indicatorPresent"])
        self.assertFalse(result["paneOpen"])
        self.assertEqual(result["notices"], [])

    def test_closed_pane_still_reports_the_indicator(self) -> None:
        result = self.collect("indicator-present-pane-closed")
        self.assertTrue(result["found"])
        self.assertTrue(result["indicatorPresent"])
        self.assertFalse(result["paneOpen"])
        self.assertEqual(result["noticeCount"], 0)

    def test_invisible_toggle_is_not_reported_as_present(self) -> None:
        result = self.collect("invisible-toggle")
        self.assertTrue(result["found"])
        self.assertFalse(result["indicatorPresent"])

    def test_every_message_paragraph_of_a_table_is_returned(self) -> None:
        result = self.collect("pane-open-multi-message")
        self.assertTrue(result["paneOpen"])
        self.assertEqual(result["noticeCount"], 1)
        notice = result["notices"][0]
        self.assertEqual(len(notice["messages"]), 2)
        self.assertEqual(
            notice["messages"],
            [
                "definition.outerDiameter: Expected bounds to be a map",
                "definition.outerDiameter: Expected a range",
            ],
        )
        # `text` stays the first paragraph so older callers keep working.
        self.assertEqual(notice["text"], notice["messages"][0])
        self.assertEqual(notice["severity"], "error")
        self.assertEqual(notice["line"], 9)
        self.assertEqual(notice["column"], 44)
        self.assertEqual(notice["row"], 8)
        self.assertEqual(notice["col"], 43)
        self.assertEqual(notice["tabName"], "Feature Studio 1")

    def test_severity_and_missing_location_are_normalized(self) -> None:
        notices = self.collect("severity-and-location-variants")["notices"]
        self.assertEqual([notice["severity"] for notice in notices],
                         ["error", "info", "warning", "warning"])
        no_number = notices[3]
        self.assertIsNone(no_number["line"])
        self.assertIsNone(no_number["column"])
        self.assertEqual(no_number["row"], 0)
        self.assertEqual(no_number["col"], 0)

    def test_other_tabs_and_out_of_date_containers_are_skipped(self) -> None:
        result = self.collect("inactive-tab-skipped")
        self.assertEqual(result["activeTabName"], "Feature Studio 1")
        self.assertEqual([notice["text"] for notice in result["notices"]], ["active tab"])

        stale = self.collect("out-of-date-container-skipped")
        self.assertEqual([notice["text"] for notice in stale["notices"]], ["fresh result"])

    def test_a_table_without_messages_is_not_a_notice(self) -> None:
        result = self.collect("message-less-table-skipped")
        self.assertEqual(result["noticeCount"], 0)
        self.assertEqual(result["notices"], [])

    def test_the_probe_rejects_an_unknown_scenario(self) -> None:
        payload = {"js": actions.FS_NOTICE_SNAPSHOT_JS, "selectors": SELECTORS,
                   "scenario": "not-a-scenario"}
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "scenario.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            completed = subprocess.run(
                [NODE, str(PROBE), str(input_path)],
                capture_output=True, text=True, timeout=60, check=False,
            )
        parsed = json.loads(completed.stdout)
        self.assertIn("unknown scenario", parsed["error"])


class NoticeObservationWiringTest(unittest.TestCase):
    """The Python half of the observation: what is sent, and what is derived."""

    def test_the_snapshot_sends_the_tested_collector_and_selectors(self) -> None:
        page = mock.Mock()
        page.evaluate.return_value = {
            "found": True,
            "indicatorPresent": True,
            "paneOpen": True,
            "noticeCount": 0,
            "notices": [],
        }
        actions.read_featurescript_notices(page)
        source, sent_selectors = page.evaluate.call_args.args
        # The stub-DOM probe runs this exact string; keep them the same object.
        self.assertEqual(source, actions.FS_NOTICE_SNAPSHOT_JS)
        self.assertEqual(sent_selectors, SELECTORS)

    def test_raw_notice_rows_are_returned_unedited(self) -> None:
        # The observation layer must not annotate what the browser actually saw;
        # codes and summaries belong to the derived compile status.
        notice = {
            "severity": "warning",
            "text": "Variable A not found.",
            "messages": ["Variable A not found.", "extra detail"],
            "line": 9,
            "column": 44,
            "row": 8,
            "col": 43,
            "tabName": "Feature Studio 1",
        }
        page = mock.Mock()
        page.evaluate.return_value = {
            "found": True,
            "indicatorPresent": True,
            "paneOpen": True,
            "noticeCount": 1,
            "notices": [notice],
        }
        result = actions.read_featurescript_notices(page)
        self.assertEqual(result["notices"], [notice])
        self.assertNotIn("code", result["notices"][0])

    def _compile_status(self, notices: list[dict], **ace: object) -> dict:
        page = mock.Mock()
        page.evaluate.return_value = {"found": True, "annotationCount": 0, "errors": [], **ace}
        with mock.patch.object(actions, "read_featurescript_notices", return_value={
            "found": True,
            "complete": True,
            "noticeCount": len(notices),
            "notices": notices,
        }):
            return actions.read_featurescript_compile_status(page)

    def test_derived_errors_carry_a_labeled_code_and_every_message(self) -> None:
        result = self._compile_status([{
            "severity": "error",
            "text": "definition.outerDiameter: Expected a range",
            "messages": ["definition.outerDiameter: Expected a range", "second paragraph"],
            "line": 4,
            "column": 9,
            "row": 3,
            "col": 8,
            "tabName": "Feature Studio 1",
        }])
        error = result["errors"][0]
        self.assertEqual(error["code"], "FS_EXPECTED_TYPE")
        self.assertEqual(error["codeBasis"], "compilerMessage")
        self.assertFalse(error["codeStable"])
        self.assertEqual(error["messages"], ["definition.outerDiameter: Expected a range",
                                            "second paragraph"])
        summary = result["diagnosticSummary"]
        self.assertEqual(summary["groupCount"], 1)
        self.assertEqual(summary["groups"][0]["count"], 1)
        self.assertEqual(summary["severityCounts"]["error"], 1)

    def test_a_notice_without_a_message_list_still_reports_its_text(self) -> None:
        result = self._compile_status([{
            "severity": "warning",
            "text": "Variable POSITIVE_LENGTH_BOUNDS not found.",
            "line": 9,
            "column": 44,
            "row": 8,
            "col": 43,
            "tabName": "Feature Studio 1",
        }])
        error = result["errors"][0]
        self.assertEqual(error["messages"], ["Variable POSITIVE_LENGTH_BOUNDS not found."])
        self.assertEqual(error["code"], "FS_UNRESOLVED_NAME")

    def test_ace_failures_are_enriched_and_still_fail_closed(self) -> None:
        page = mock.Mock()
        page.evaluate.side_effect = RuntimeError("page closed")
        result = actions.read_featurescript_compile_status(page)
        self.assertFalse(result["compiled"])
        error = result["errors"][0]
        self.assertEqual(error["source"], "compileObservation")
        self.assertEqual(error["code"], "UNCLASSIFIED")
        self.assertEqual(error["messages"], [error["text"]])

    def test_a_clean_compile_carries_no_summary(self) -> None:
        result = self._compile_status([])
        self.assertTrue(result["compiled"])
        self.assertNotIn("diagnosticSummary", result)

    def test_info_notices_do_not_block_but_are_counted(self) -> None:
        result = self._compile_status([{
            "severity": "info",
            "text": "informational",
            "line": 1,
            "column": 1,
            "row": 0,
            "col": 0,
            "tabName": "Feature Studio 1",
        }])
        self.assertTrue(result["compiled"])
        self.assertEqual(result["noticeCount"], 1)
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
