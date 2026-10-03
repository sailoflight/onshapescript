#!/usr/bin/env python3
"""The registered `browser_import_step` handler: gates, forwarding, and what it must NOT do.

The handler is thin on purpose, so these tests are about the boundary: a dry run is local, a real call
needs `confirm_mutation`, the module's verdict passes through untouched (including `no_new_element`,
which is not a failure), and registration happens only for a **proven** import.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ImportToolTest(unittest.TestCase):
    def _arguments(self, **overrides):
        arguments = {
            "source_path": "/tmp/handoff.step",
            "mode": "new-tab",
            "target_tab": "",
            "document_id": "doc-1",
            "workspace_id": "ws-1",
            "expect_feature_name": "",
            "timeout_ms": 120_000,
        }
        arguments.update(overrides)
        return arguments

    def test_dry_run_stays_local_and_never_touches_the_page(self):
        from mcp_main.win.mcp import browser_tools

        with mock.patch.object(browser_tools, "_page",
                               side_effect=AssertionError("a dry run must not touch the page")), \
             mock.patch("onshape_browser_mode.step_import.plan_browser_step_import",
                        return_value={"dryRun": True, "source": {"sha256": "abc"}}) as plan:
            result = browser_tools.browser_import_step(self._arguments(dry_run=True))
        self.assertTrue(result["dryRun"])
        plan.assert_called_once()
        self.assertEqual(plan.call_args.kwargs["source_path"], "/tmp/handoff.step")
        self.assertEqual(plan.call_args.kwargs["timeout_ms"], 120_000)

    def test_a_real_import_requires_confirmation(self):
        from mcp_main.win.mcp import browser_tools

        with mock.patch.object(browser_tools, "_page",
                               side_effect=AssertionError("no page work before the gate")):
            with self.assertRaisesRegex(ValueError, "confirm_mutation=true"):
                browser_tools.browser_import_step(self._arguments())
            with self.assertRaisesRegex(ValueError, "confirm_mutation=true"):
                browser_tools.browser_import_step(self._arguments(confirm_mutation=False))

    def test_the_verdict_passes_through_untouched(self):
        from mcp_main.win.mcp import browser_tools

        verdict = {"imported": False, "reason": "no_new_element", "translationCompleted": "unknown"}
        with mock.patch.object(browser_tools, "_page", return_value=(object(), None)), \
             mock.patch("onshape_browser_mode.step_import.import_browser_step",
                        return_value=verdict) as run:
            result = browser_tools.browser_import_step(
                self._arguments(confirm_mutation=True, mode="into-part-studio",
                                expect_feature_name="gf-storage")
            )
        self.assertEqual(result, verdict)
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["mode"], "into-part-studio")
        self.assertEqual(run.call_args.kwargs["expect_feature_name"], "gf-storage")

    def test_only_a_proven_import_is_registered(self):
        from mcp_main.win.mcp import browser_tools

        with mock.patch.object(browser_tools, "_page", return_value=(object(), None)), \
             mock.patch("onshape_browser_mode.step_import.import_browser_step",
                        return_value={"imported": False, "reason": "no_new_element"}), \
             mock.patch("onshape_browser_mode.step_import.register_imported_browser_step") as register:
            result = browser_tools.browser_import_step(
                self._arguments(confirm_mutation=True, register_as="step-import-1")
            )
        self.assertNotIn("registered", result)
        register.assert_not_called()

        with mock.patch.object(browser_tools, "_page", return_value=(object(), None)), \
             mock.patch("onshape_browser_mode.step_import.import_browser_step",
                        return_value={"imported": True, "reason": "new_element"}), \
             mock.patch("onshape_browser_mode.step_import.register_imported_browser_step",
                        return_value={"registered": True}) as register:
            result = browser_tools.browser_import_step(
                self._arguments(confirm_mutation=True, register_as="step-import-1")
            )
        self.assertTrue(result["registered"])
        self.assertEqual(register.call_args.kwargs["import_id"], "step-import-1")
        self.assertEqual(register.call_args.kwargs["document_id"], "doc-1")

    def test_bad_arguments_are_refused_before_any_work(self):
        from mcp_main.win.mcp import browser_tools

        with mock.patch.object(browser_tools, "_page",
                               side_effect=AssertionError("no page work for bad arguments")):
            with self.assertRaisesRegex(ValueError, "source_path is required"):
                browser_tools.browser_import_step({"source_path": "  "})
            with self.assertRaisesRegex(ValueError, "mode must be"):
                browser_tools.browser_import_step(self._arguments(mode="teleport"))

    def test_the_registered_entry_exposes_the_gates(self):
        from mcp_main.win.mcp import server

        tool = next(t for t in server.TOOLS if t["name"] == "browser_import_step")
        properties = tool["inputSchema"]["properties"]
        self.assertTrue(properties["dry_run"]["default"])
        self.assertIn("confirm_mutation", properties)
        self.assertEqual(tool["inputSchema"].get("required"), ["source_path"])
        self.assertEqual(tool["cost"]["estimated_requests"], 0)
        self.assertEqual(tool["cost"]["network"], "browser")
        self.assertFalse(tool["annotations"]["readOnlyHint"])
        # The description must name the unverified selectors rather than implying a verified flow.
        self.assertIn("UNVERIFIED", tool["description"])
        self.assertIn("pending-live-verification-step-import", tool["description"])


if __name__ == "__main__":
    unittest.main()
