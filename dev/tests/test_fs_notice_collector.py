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

    def test_other_element_notices_are_kept_and_flagged(self) -> None:
        result = self.collect("other-element-notice-kept")
        self.assertEqual(result["activeTabName"], "Feature Studio 1")
        self.assertEqual(result["noticeCount"], 2)
        self.assertEqual(result["activeTabNoticeCount"], 1)
        self.assertEqual(result["otherElementNoticeCount"], 1)
        self.assertEqual(result["containerTitles"], ["Part Studio 1", "Feature Studio 1"])
        by_tab = {notice["tabName"]: notice for notice in result["notices"]}
        regenerated = by_tab["Part Studio 1"]
        self.assertFalse(regenerated["isActiveTab"])
        self.assertEqual(regenerated["severity"], "error")
        self.assertEqual(regenerated["messages"], [
            "GF Socket Pockets 1 failed to regenerate",
            "Plate width is not an integer multiple of the cell pitch",
        ])
        self.assertEqual(regenerated["line"], 100)
        self.assertEqual(regenerated["column"], 9)
        self.assertTrue(by_tab["Feature Studio 1"]["isActiveTab"])

    def test_an_error_marker_inside_a_table_outranks_an_info_icon(self) -> None:
        # A Part Studio console row can carry an info-styled gutter icon next to
        # the error text; labelling it info hid a real regeneration error.
        notice = self.collect("error-marker-wins-over-info-icon")["notices"][0]
        self.assertEqual(notice["severity"], "error")
        self.assertEqual(notice["text"], "throw boom")
        self.assertEqual(notice["line"], 100)
        self.assertEqual(notice["tabName"], "Part Studio 1")

    def test_out_of_date_rows_are_read_and_flagged_not_dropped(self) -> None:
        # Live-measured shape: the container for a Part Studio whose custom
        # feature failed to regenerate carries `notices-out-of-date` on its
        # header AND the real error. Dropping it hid the failure.
        result = self.collect("out-of-date-container-read-and-flagged")
        self.assertEqual([notice["text"] for notice in result["notices"]],
                         ["stale result", "fresh result"])
        self.assertTrue(result["notices"][0]["outOfDate"])
        self.assertFalse(result["notices"][1]["outOfDate"])
        # Both containers produced a row, so there is no silent element to report.
        self.assertNotIn("unstructuredContainers", result)

    def test_an_untitled_container_counts_as_the_active_tab(self) -> None:
        result = self.collect("untitled-container-counts-as-active")
        self.assertEqual(result["activeTabNoticeCount"], 1)
        self.assertTrue(result["notices"][0]["isActiveTab"])
        self.assertEqual(result["containerTitles"], [])

    def test_a_listed_element_without_notice_tables_is_still_reported(self) -> None:
        # This is the shape that separates "the pane said nothing" from "the
        # pane listed an element whose failure is not a notice table".
        result = self.collect("element-without-notice-tables")
        self.assertEqual(result["notices"], [])
        self.assertEqual(result["noticeCount"], 0)
        self.assertEqual(result["containerCount"], 1)
        self.assertEqual(result["containerTitles"], ["Part Studio 1"])
        structure = result["unstructuredContainers"]
        self.assertEqual(len(structure), 1)
        listed = structure[0]
        self.assertEqual(listed["tabName"], "Part Studio 1")
        self.assertIn("element-notice-set-container", listed["classes"])
        self.assertIn("GF Socket Pockets 1 failed to regenerate", listed["text"])
        self.assertIn("element-log-container", result["paneClassNames"])

    def test_a_pane_with_tables_carries_no_structure_noise(self) -> None:
        result = self.collect("pane-open-multi-message")
        self.assertNotIn("unstructuredContainers", result)

    def test_a_table_without_messages_is_not_a_notice(self) -> None:
        result = self.collect("message-less-table-skipped")
        self.assertEqual(result["noticeCount"], 0)
        self.assertEqual(result["notices"], [])
        # A message-less table is the same "listed but silent" shape as a
        # missing table: the container is reported structurally, not dropped.
        self.assertEqual(len(result["unstructuredContainers"]), 1)

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

    def test_the_probe_snapshot_is_demoted_by_the_python_reader(self) -> None:
        # The exact production string's own output, fed to the Python reader: the
        # stale row the collector deliberately keeps (dropping it once hid a real
        # failure) must still be demoted out of the current bucket by default.
        raw = self.collect("out-of-date-container-read-and-flagged")
        page = mock.Mock()
        page.evaluate.return_value = raw
        result = actions.read_featurescript_notices(page)
        self.assertEqual([notice["text"] for notice in result["notices"]], ["fresh result"])
        self.assertEqual([notice["text"] for notice in result["staleNotices"]],
                         ["stale result"])
        self.assertEqual(result["staleErrorCount"], 1)


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

    def test_raw_notice_fields_are_kept_and_gain_a_staleness_marker(self) -> None:
        # The observation layer keeps every raw field the browser actually saw and
        # adds only the documented ``stale``/``bucket`` markers; codes and
        # summaries still belong to the derived compile status.
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
        returned = result["notices"][0]
        for key, value in notice.items():
            self.assertEqual(returned[key], value, key)
        self.assertFalse(returned["stale"])
        self.assertEqual(returned["bucket"], "currentActiveTab")
        self.assertNotIn("code", returned)

    @staticmethod
    def _snapshot(*notices: dict) -> dict:
        """A raw collector snapshot carrying exactly these notice rows."""
        return {
            "found": True,
            "indicatorPresent": True,
            "paneOpen": True,
            "activeTabName": "Feature Studio 1",
            "noticeCount": len(notices),
            "notices": list(notices),
        }

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
        self.assertTrue(result["documentClean"])
        self.assertNotIn("diagnosticSummary", result)
        self.assertEqual(result["elementNotices"], [])
        self.assertEqual(result["elementErrorCount"], 0)

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

    def test_another_elements_regeneration_error_never_fails_the_editor_verdict(self) -> None:
        """A broken Part Studio must not turn a clean commit into a failed one."""
        result = self._compile_status([
            {"severity": "info", "text": "informational", "line": 1, "column": 1,
             "row": 0, "col": 0, "tabName": "Feature Studio 1", "isActiveTab": True},
            {"severity": "error",
             "text": "GF Socket Pockets 1 failed to regenerate",
             "messages": ["GF Socket Pockets 1 failed to regenerate",
                          "Plate width is not an integer multiple of the cell pitch"],
             "line": 100, "column": 9, "row": 99, "col": 8,
             "tabName": "Part Studio 1", "isActiveTab": False},
        ])
        # Editor-scoped: what deployment acceptance reads.
        self.assertTrue(result["compiled"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["activeTabNoticeCount"], 1)
        # Document-scoped: the same observation, attributed per element.
        self.assertFalse(result["documentClean"])
        self.assertEqual(result["noticeCount"], 2)
        self.assertEqual(result["elementNoticeCount"], 1)
        self.assertEqual(result["elementErrorCount"], 1)
        element_error = result["elementErrors"][0]
        self.assertEqual(element_error["text"], "GF Socket Pockets 1 failed to regenerate")
        self.assertEqual(element_error["messages"], [
            "GF Socket Pockets 1 failed to regenerate",
            "Plate width is not an integer multiple of the cell pitch",
        ])
        self.assertEqual(element_error["tabName"], "Part Studio 1")
        self.assertFalse(element_error["isActiveTab"])
        self.assertEqual(element_error["type"], "error")
        self.assertEqual(result["elementDiagnosticSummary"]["severityCounts"]["error"], 1)

    def test_an_out_of_date_element_error_is_still_reported_with_its_call_stack(self) -> None:
        """The live-measured shape: the Part Studio container is out of date.

        The stale row used to be returned in the OTHER-ELEMENT bucket, so
        ``staleErrorCount`` legitimately read 0 while the stale row still read as
        current. ``outOfDate`` now wins over ``isActiveTab`` in the split.
        """
        result = self._compile_status([{
            "severity": "error",
            "text": "throw Plate width is not an integer multiple of the cell pitch; "
                    "expected a Gridfinity plate",
            "messages": [
                "throw Plate width is not an integer multiple of the cell pitch; "
                "expected a Gridfinity plate",
            ],
            "line": 100, "column": 9, "row": 99, "col": 8,
            "tabName": "Part Studio 1", "isActiveTab": False, "outOfDate": True,
        }])
        # The editor still compiles, so deployment acceptance is untouched.
        self.assertTrue(result["compiled"])
        self.assertEqual(result["errors"], [])
        # ... and the actual error text is returned in the STALE bucket, not the
        # current element bucket and not swallowed.
        self.assertFalse(result["documentClean"])
        self.assertEqual(result["elementErrorCount"], 0)
        self.assertEqual(result["elementErrors"], [])
        self.assertEqual(result["staleErrorCount"], 1)
        reported = result["staleErrors"][0]
        self.assertEqual(reported["tabName"], "Part Studio 1")
        self.assertTrue(reported["outOfDate"])
        self.assertTrue(reported["stale"])
        self.assertIn("not an integer multiple of the cell pitch", reported["text"])

    def test_stale_rows_are_demoted_across_tabs_by_default(self) -> None:
        stale = {
            "severity": "error", "text": "stale result", "messages": ["stale result"],
            "line": 156, "column": 9, "row": 155, "col": 8,
            "tabName": "Part Studio 1", "isActiveTab": False, "outOfDate": True,
        }
        current = {
            "severity": "error", "text": "fresh result", "messages": ["fresh result"],
            "line": 4, "column": 1, "row": 3, "col": 0,
            "tabName": "Feature Studio 1", "isActiveTab": True, "outOfDate": False,
        }
        page = mock.Mock()
        page.evaluate.return_value = self._snapshot(stale, current)
        result = actions.read_featurescript_notices(page)
        # The stale cross-tab row is not in the current notice bucket ...
        self.assertEqual([notice["text"] for notice in result["notices"]], ["fresh result"])
        self.assertEqual([notice["text"] for notice in result["staleNotices"]],
                         ["stale result"])
        # ... but its true count is reported regardless of tab.
        self.assertEqual(result["staleErrorCount"], 1)
        self.assertEqual(result["staleNoticeCount"], 1)
        self.assertEqual(result["currentNoticeCount"], 1)
        self.assertFalse(result["includeStale"])
        self.assertIn("notices-out-of-date", result["staleErrorCountBasis"])
        self.assertEqual(result["notices"][0]["bucket"], "currentActiveTab")
        self.assertEqual(result["staleNotices"][0]["bucket"], "stale")
        self.assertTrue(result["staleNotices"][0]["stale"])
        self.assertNotEqual(result["notices"][0]["bucket"],
                            result["staleNotices"][0]["bucket"])

    def test_include_stale_restores_the_stale_row(self) -> None:
        stale = {
            "severity": "error", "text": "stale result", "messages": ["stale result"],
            "line": 156, "column": 9, "row": 155, "col": 8,
            "tabName": "Part Studio 1", "isActiveTab": False, "outOfDate": True,
        }
        current = {
            "severity": "warning", "text": "fresh result", "messages": ["fresh result"],
            "line": 4, "column": 1, "row": 3, "col": 0,
            "tabName": "Feature Studio 1", "isActiveTab": True, "outOfDate": False,
        }
        page = mock.Mock()
        page.evaluate.return_value = self._snapshot(stale, current)
        result = actions.read_featurescript_notices(page, includeStale=True)
        self.assertTrue(result["includeStale"])
        self.assertEqual([notice["text"] for notice in result["notices"]],
                         ["stale result", "fresh result"])
        by_text = {notice["text"]: notice for notice in result["notices"]}
        self.assertEqual(by_text["stale result"]["bucket"], "stale")
        self.assertTrue(by_text["stale result"]["stale"])
        self.assertEqual(by_text["fresh result"]["bucket"], "currentActiveTab")
        self.assertEqual(result["staleErrorCount"], 1)

    def test_compile_status_asks_the_notice_reader_to_keep_stale_rows(self) -> None:
        # The derived status has its own staleErrors bucket, so it must opt back
        # in to the rows the raw reader demotes by default.
        page = mock.Mock()
        page.evaluate.return_value = {"found": True, "annotationCount": 0, "errors": []}
        with mock.patch.object(actions, "read_featurescript_notices", return_value={
            "found": True, "complete": True, "noticeCount": 0, "notices": [],
        }) as reader:
            actions.read_featurescript_compile_status(page)
        reader.assert_called_once_with(page, includeStale=True)

    def test_an_out_of_date_row_on_the_active_tab_never_fails_a_fresh_commit(self) -> None:
        result = self._compile_status([{
            "severity": "error",
            "text": "stale error from the previous compile",
            "line": 4, "column": 9, "row": 3, "col": 8,
            "tabName": "Feature Studio 1", "isActiveTab": True, "outOfDate": True,
        }])
        self.assertTrue(result["compiled"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["staleErrorCount"], 1)
        self.assertEqual(result["staleErrors"][0]["outOfDate"], True)
        self.assertEqual(result["staleNotices"][0]["text"],
                         "stale error from the previous compile")
        self.assertFalse(result["documentClean"])

    def test_the_pane_structure_evidence_reaches_the_compile_status(self) -> None:
        # A listed element that produced no notice table is exactly where a
        # regeneration failure hides; its structure must survive into the
        # derived status instead of being swallowed.
        page = mock.Mock()
        page.evaluate.return_value = {"found": True, "annotationCount": 0, "errors": []}
        with mock.patch.object(actions, "read_featurescript_notices", return_value={
            "found": True,
            "complete": True,
            "noticeCount": 0,
            "notices": [],
            "containerTitles": ["Part Studio 1"],
            "unstructuredContainers": [{
                "tabName": "Part Studio 1",
                "classes": "element-notice-set-container",
                "text": "Part Studio 1 GF Socket Pockets 1 failed to regenerate",
            }],
            "paneClassNames": ["notices-content", "element-log-container"],
        }):
            result = actions.read_featurescript_compile_status(page)
        self.assertEqual(result["noticeContainerTitles"], ["Part Studio 1"])
        structure = result["noticePaneStructure"]
        self.assertEqual(structure["unstructuredContainers"][0]["tabName"], "Part Studio 1")
        self.assertIn("element-log-container", structure["paneClassNames"])

    def test_an_unreadable_notice_pane_never_claims_the_document_is_clean(self) -> None:
        page = mock.Mock()
        page.evaluate.return_value = {"found": True, "annotationCount": 0, "errors": []}
        with mock.patch.object(actions, "read_featurescript_notices", return_value={
            "found": True,
            "complete": False,
            "noticeCount": 0,
            "notices": [],
            "reason": "notice pane unavailable",
        }):
            result = actions.read_featurescript_compile_status(page)
        self.assertFalse(result["compiled"])
        self.assertFalse(result["documentClean"])
        self.assertEqual(result["reason"], "notice pane unavailable")


if __name__ == "__main__":
    unittest.main()
