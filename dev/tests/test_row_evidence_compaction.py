#!/usr/bin/env python3
"""Gate for the mutation-response row-evidence projection (roadmap G5).

A mutation answer used to repeat the same Feature List several times: a delete
returned the enumeration rows, the pre-state names, the post-state names AND the
resolver's own resolved list -- four copies of the same 22 names -- and an insert
returned the pre-insert rows, the post-insert rows and the whole read object
(measured 2026-09-21: 18,529 of 49,935 and 40,315 of 91,878 characters of row
evidence).

What must hold:

* the compact answer keeps ONE canonical row list plus the counts of what it
  replaced, so the two counts that used to look like a disagreement are still
  both visible as numbers;
* no information a verdict depends on is lost -- the read object keeps its
  readiness scalars (`headerCount`/`rowsComplete`/`ready`) and the names of any
  row in ERROR;
* the projection happens ONLY at the MCP response boundary, so the handler's own
  return value (which the project runner and the offline tests read) is byte
  identical, and `include_row_evidence=true` restores it for the caller.
"""

from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

from mcp_main.win.mcp import server
from mcp_main.win.mcp.browser_tools import ROW_EVIDENCE_ARGUMENT, compact_row_evidence


def _row(index: int) -> dict:
    return {
        "name": f"TS Thin Sketch Rectangle {index}",
        "isUserFeature": True,
        "isDefault": False,
        "className": "os-list-item ns-user-feature",
        "hasError": index == 3,
        "iconCls": "os-list-item-icon os-feature-type-icon os-custom-feature",
    }


ROWS = [_row(index) for index in range(1, 23)]
NAMES = [row["name"] for row in ROWS]


def _insert_result() -> dict:
    return {
        "inserted": True,
        "applyState": "verified",
        "baselineRows": NAMES[:21],
        "featureRows": NAMES + ["TS 底脚平面 35.6 mm x 35.6 mm"],
        "createdRows": ["TS 底脚平面 35.6 mm x 35.6 mm"],
        "features": {
            "pageUrl": "https://cad.onshape.com/documents/x",
            "headerText": "特征 (27)",
            "headerCount": 27,
            "rowsComplete": False,
            "ready": True,
            "partsText": "零件数 (4) Part 1",
            "partItems": ["Part 1"],
            "features": ROWS,
        },
        "commit": {"verified": True, "survived": True},
        "insertedRows": 1,
    }


def _delete_result() -> dict:
    return {
        "deleted": True,
        "matchedName": NAMES[0],
        "matchedRows": [NAMES[0]],
        "featureRows": NAMES,
        "beforeRows": NAMES,
        "afterRows": NAMES[1:],
        "rowCountBefore": len(NAMES),
        "rowCountAfter": len(NAMES) - 1,
        "stillListedNames": [],
        "rowScroll": {
            "found": True,
            "index": 0,
            "matches": 1,
            "scrolled": False,
            "steps": 0,
            "reason": "",
            "rendered": NAMES,
        },
        "removal": {"waited": True, "condition": "user_feature_row_absent", "elapsedMs": 1629},
    }


class InsertProjectionTest(unittest.TestCase):
    def compact(self) -> dict:
        return compact_row_evidence(
            "browser_insert_custom_feature", _insert_result(), {}
        )

    def test_the_pre_state_list_becomes_its_count(self):
        result = self.compact()
        self.assertNotIn("baselineRows", result)
        self.assertEqual(result["baselineRowCount"], 21)
        # The canonical post-insert list and the delta are kept: they are what a
        # caller checks a verdict against.
        self.assertEqual(result["featureRows"], NAMES + ["TS 底脚平面 35.6 mm x 35.6 mm"])
        self.assertEqual(result["createdRows"], ["TS 底脚平面 35.6 mm x 35.6 mm"])

    def test_the_read_object_keeps_its_readiness_and_its_error_signal(self):
        read = self.compact()["features"]
        self.assertNotIn("features", read)
        self.assertEqual(read["featureCount"], len(ROWS))
        self.assertEqual(read["headerCount"], 27)
        self.assertFalse(read["rowsComplete"])
        self.assertTrue(read["ready"])
        self.assertEqual(read["headerText"], "特征 (27)")
        self.assertEqual(read["erroredRows"], [NAMES[2]])

    def test_the_projection_is_announced_and_never_silent(self):
        result = self.compact()
        self.assertTrue(result["rowEvidence"]["compacted"])
        self.assertIn("baselineRows", result["rowEvidence"]["replaced"])
        self.assertIn("features.features", result["rowEvidence"]["replaced"])
        self.assertIn(ROW_EVIDENCE_ARGUMENT, result["rowEvidence"]["note"])

    def test_it_is_opt_out_not_lossy(self):
        original = _insert_result()
        snapshot = copy.deepcopy(original)
        self.assertEqual(
            compact_row_evidence(
                "browser_insert_custom_feature", original, {ROW_EVIDENCE_ARGUMENT: True}
            ),
            snapshot,
        )
        self.assertEqual(original, snapshot, "the handler's value must not be mutated")


class DeleteProjectionTest(unittest.TestCase):
    def compact(self) -> dict:
        return compact_row_evidence("browser_delete_feature", _delete_result(), {})

    def test_the_four_copies_collapse_to_one_with_both_counts(self):
        result = self.compact()
        self.assertNotIn("featureRows", result)
        self.assertNotIn("beforeRows", result)
        self.assertEqual(result["enumeratedRowCount"], len(NAMES))
        self.assertEqual(result["beforeRowCount"], len(NAMES))
        self.assertEqual(result["afterRows"], NAMES[1:])
        # Both counts the duplicates used to demonstrate are still numbers.
        self.assertEqual(result["rowCountBefore"], len(NAMES))
        self.assertEqual(result["rowCountAfter"], len(NAMES) - 1)

    def test_the_resolver_evidence_keeps_its_diagnostic_fields(self):
        scroll = self.compact()["rowScroll"]
        self.assertNotIn("rendered", scroll)
        for key in ("found", "index", "matches", "scrolled", "steps", "reason"):
            self.assertIn(key, scroll)
        self.assertEqual(self.compact()["removal"]["elapsedMs"], 1629)

    def test_the_required_judgement_fields_survive(self):
        result = self.compact()
        self.assertTrue(result["deleted"])
        self.assertEqual(result["matchedName"], NAMES[0])
        self.assertEqual(result["matchedRows"], [NAMES[0]])
        self.assertEqual(result["stillListedNames"], [])


class ProjectionScopeTest(unittest.TestCase):
    def test_a_tool_without_a_policy_is_returned_untouched(self):
        value = {"features": ROWS, "featureRows": NAMES}
        for name in (
            "browser_get_partstudio_features",
            "browser_verify_feature_parameters",
            "browser_export_step",
        ):
            self.assertIs(compact_row_evidence(name, value, {}), value)

    def test_a_non_dict_answer_is_returned_untouched(self):
        self.assertEqual(
            compact_row_evidence("browser_delete_feature", "not a dict", {}), "not a dict"
        )

    def test_the_boundary_applies_it_once_and_the_opt_in_bypasses_it(self):
        full = _delete_result()
        with mock.patch.dict(server.HANDLERS, {"browser_delete_feature": lambda _: full}):
            compact = server.tool_result("browser_delete_feature", {"feature_name": NAMES[0]})
            verbose = server.tool_result(
                "browser_delete_feature",
                {"feature_name": NAMES[0], ROW_EVIDENCE_ARGUMENT: True},
            )
        self.assertNotIn("featureRows", compact["structuredContent"])
        self.assertIn("enumeratedRowCount", compact["structuredContent"])
        self.assertEqual(verbose["structuredContent"], full)
        self.assertLess(
            len(json.dumps(compact["structuredContent"], ensure_ascii=False)),
            len(json.dumps(verbose["structuredContent"], ensure_ascii=False)) * 0.75,
        )

    def test_the_documented_schemas_expose_the_opt_in(self):
        for name in ("browser_insert_custom_feature", "browser_delete_feature"):
            tool = next(tool for tool in server.TOOLS if tool["name"] == name)
            field = tool["inputSchema"]["properties"][ROW_EVIDENCE_ARGUMENT]
            self.assertIs(field["default"], False, name)
            self.assertEqual(field["type"], "boolean", name)
            # The description must say what the default costs less of, because a
            # caller who cannot tell why the field exists will set it to true.
            self.assertIn("compact", field["description"], name)


if __name__ == "__main__":
    unittest.main()
