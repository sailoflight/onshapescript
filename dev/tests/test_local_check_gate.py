#!/usr/bin/env python3
"""The one local-check rule every deploy path shares.

Owner decision 2026-09-19: a local finding warns and then requires an explicit
second confirmation. It must not block the write (the vendored reference can lag
the live server) and it must not be silently ignored either. The rule and the
argument name live in `onshape_docs.query.fs_check`; this module pins the
contract across the browser legs and the REST leg so the three cannot drift:

* every local-checked deploy tool advertises the same argument name;
* only error-level findings ask for the confirmation (warnings stay advice);
* a gated call performs no browser action and no network request, and the
  next-call hint it returns is the same call plus the acknowledgement;
* the two browser/REST gate results carry the same keys.
"""

from __future__ import annotations

import unittest
from unittest import mock

from mcp_main.win.mcp import browser_tools, server
from onshape_docs.query import fs_check
from onshape_rest_api_mode import operations

# Tools that write a locally-checked FeatureScript source to the cloud.
GATED_TOOLS = (
    "browser_deploy_featurescript",
    "browser_deploy_and_apply_featurescript",
    "onshape_upload_feature_studio",
    "onshape_run_validation_pipeline",
)

BAD_SOURCE = "FeatureScript 3044;\nvar x = 1;"
# Warning-level only: opExtrude's third argument cannot be a map, which the real
# server accepts at save time, so it must never demand a confirmation.
WARNING_SOURCE = (
    'FeatureScript 3044;\n'
    'import(path : "onshape/std/geometry.fs", version : "3044.0");\n'
    'export const f = defineFeature(function(context is Context, id is Id, definition is map)\n'
    '    precondition { annotation { "Name" : "F" } }\n'
    '    {\n'
    '        opExtrude(context, id + "e", 5);\n'
    '    });\n'
)
ACK = fs_check.ACKNOWLEDGEMENT_ARGUMENT


class SharedRuleTest(unittest.TestCase):
    def test_the_rule_is_read_from_one_place(self) -> None:
        self.assertEqual(ACK, "acknowledge_local_findings")
        bad = fs_check.check_source(fs_check.FsFile.from_text(BAD_SOURCE)).as_result()
        warn = fs_check.check_source(
            fs_check.FsFile.from_text(WARNING_SOURCE)
        ).as_result()
        self.assertTrue(fs_check.findings_requiring_acknowledgement(bad))
        self.assertEqual(fs_check.findings_requiring_acknowledgement(warn), [])
        self.assertTrue(fs_check.acknowledgement_missing(bad, {}))
        self.assertFalse(fs_check.acknowledgement_missing(bad, {ACK: True}))
        # Warnings alone never ask, even though they are reported.
        self.assertGreaterEqual(warn["warningCount"], 1)
        self.assertFalse(fs_check.acknowledgement_missing(warn, {}))

    def test_every_deploy_tool_advertises_the_same_argument(self) -> None:
        by_name = {tool["name"]: tool for tool in server.TOOLS}
        for name in GATED_TOOLS:
            with self.subTest(tool=name):
                properties = by_name[name]["inputSchema"]["properties"]
                self.assertIn(ACK, properties, name)
                self.assertEqual(properties[ACK]["default"], False, name)
                self.assertEqual(properties[ACK]["type"], "boolean", name)

    def test_gate_results_carry_one_shape(self) -> None:
        bad = fs_check.check_source(fs_check.FsFile.from_text(BAD_SOURCE)).as_result()
        request = fs_check.acknowledgement_request(
            tool="t", local_check=bad, next_call={"tool": "t", "arguments": {}},
        )
        self.assertEqual(
            sorted(request),
            [
                "acknowledgementRequired", "localCheck", "localFindings",
                "nextCall", "note", "reason", "tool",
            ],
        )
        self.assertTrue(request["acknowledgementRequired"])
        self.assertEqual(request["localFindings"], bad["errors"])
        self.assertIn("advisory", request["note"])
        self.assertIn(ACK, request["note"])


class BrowserLegTest(unittest.TestCase):
    def test_browser_deploy_gate_touches_no_browser(self) -> None:
        with mock.patch("onshape_browser_mode.session.get_session",
                        side_effect=AssertionError("session started")):
            result = server._browser_deploy_featurescript(
                {"script": BAD_SOURCE, "dry_run": False, "confirm_mutation": True})
        self.assertTrue(result["acknowledgementRequired"])
        self.assertEqual(result["nextCall"]["arguments"][ACK], True)

    def test_capability_deploy_gate_touches_no_browser(self) -> None:
        with mock.patch.object(browser_tools, "_page",
                               side_effect=AssertionError("session started")):
            result = browser_tools.browser_deploy_and_apply_featurescript({
                "script": BAD_SOURCE, "feature_name": "F", "confirm_mutation": True,
            })
        self.assertTrue(result["acknowledgementRequired"])
        self.assertEqual(result["nextCall"]["arguments"][ACK], True)
        self.assertEqual(result["nextCall"]["arguments"]["feature_name"], "F")

    def test_a_generated_capability_source_is_never_gated(self) -> None:
        """The capability cards generate checked sources, so the second
        confirmation must not become a routine tax on the capability route."""
        for capability in ("custom.fillet", "custom.extrude", "custom.hole",
                           "custom.spiral_ridge"):
            with self.subTest(capability=capability):
                arguments = {"capability": capability, "values": {}}
                plan = browser_tools._capability_request(arguments)
                self.assertEqual(plan["localCheck"]["errorCount"], 0)
                self.assertFalse(
                    fs_check.acknowledgement_missing(plan["localCheck"], arguments)
                )


class RestLegTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = mock.Mock()
        self.client.state = {
            "documentId": "did",
            "workspaceId": "wid",
            "featureStudioId": "fsid",
            "featureScriptFile": "examples/branch-cable-trophy/branchCableTrophyDisplay.fs",
        }
        self.client.request = mock.Mock(side_effect=AssertionError("must not request"))

    def test_upload_gate_sends_nothing(self) -> None:
        with mock.patch.object(operations.fs_check, "check_file",
                               return_value=_fake_check(BAD_SOURCE)):
            result = operations.upload_feature_studio(client=self.client, dry_run=False)
        self.assertTrue(result["acknowledgementRequired"])
        self.assertEqual(result["requests"], 0)
        self.client.request.assert_not_called()

    def test_pipeline_aborts_at_the_gated_upload_step(self) -> None:
        with mock.patch.object(operations.fs_check, "check_file",
                               return_value=_fake_check(BAD_SOURCE)):
            result = operations.run_validation_pipeline(
                client=self.client, render=False, acknowledge_local_findings=False,
            )
        self.assertEqual(result["abortedAt"], "upload")
        self.assertEqual(result["requests"], 0)
        self.assertIn("acknowledge_local_findings", result["reason"])
        self.assertTrue(result["upload"]["acknowledgementRequired"])
        self.client.request.assert_not_called()

    def test_the_two_legs_agree_on_the_gate_keys(self) -> None:
        with mock.patch.object(operations.fs_check, "check_file",
                               return_value=_fake_check(BAD_SOURCE)):
            rest = operations.upload_feature_studio(client=self.client, dry_run=False)
        with mock.patch("onshape_browser_mode.session.get_session",
                        side_effect=AssertionError("session started")):
            browser = server._browser_deploy_featurescript(
                {"script": BAD_SOURCE, "dry_run": False, "confirm_mutation": True})
        shared = {"acknowledgementRequired", "tool", "localCheck", "localFindings"}
        for name, result in (("rest", rest), ("browser", browser)):
            with self.subTest(leg=name):
                self.assertTrue(shared.issubset(result), sorted(result))


def _fake_check(source: str):
    """A checker verdict whose findings come from the real checker, so the two
    legs are compared on identical input rather than on a hand-written stub."""
    return fs_check.check_source(fs_check.FsFile.from_text(source))


if __name__ == "__main__":
    unittest.main()
