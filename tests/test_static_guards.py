#!/usr/bin/env python3
"""Offline tests for the zero-cost static/guard checks.

Covers the local FeatureScript checker (onshape_docs/scripts/fs_local_check.py)
— specifically that a dangling `Feature Type Name` annotation is detected even
though string masking hides its marker, and that an unreplaced {{PLACEHOLDER}} is
a structural error — plus the rate-limit re-raise ordering in live_gap_probe and
the singleton-attribution safety in live_is_probe. No Onshape API call is ever
made: live scripts are driven through mocks only.
"""

from __future__ import annotations

import contextlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "onshape_docs" / "scripts"
for path in (str(ROOT), str(SCRIPTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import fs_local_check  # noqa: E402  (onshape_docs/scripts/ is not a package)
import live_gap_probe  # noqa: E402
import live_is_probe  # noqa: E402

_HEADER = (
    'FeatureScript 3044;\n'
    'import(path : "onshape/std/geometry.fs", version : "3044.0");\n\n'
)

_VALID_FEATURE = _HEADER + (
    'annotation { "Feature Type Name" : "MyFeature" }\n'
    "export const myFeature = defineFeature(function(context is Context, id is Id, definition is map)\n"
    "    precondition\n"
    "    {\n"
    '        annotation { "Name" : "Size" }\n'
    "        isLength(definition.size, { (millimeter) : [1, 2, 3] } as LengthBoundSpec);\n"
    "    }\n"
    "    {\n"
    "        opExtrude(context, id + \"e\", { \"entities\" : qCreatedBy(id, EntityType.BODY), \"direction\" : Z_DIRECTION, \"endBound\" : BoundingType.BLIND, \"endDepth\" : definition.size });\n"
    "    });\n"
)


def check_text(text: str) -> fs_local_check.FsFile:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "check.fs"
        path.write_text(text, encoding="utf-8")
        return fs_local_check.check_file(path)


class DanglingAnnotationTest(unittest.TestCase):
    def test_correct_annotation_is_not_flagged(self) -> None:
        fs = check_text(_VALID_FEATURE)
        self.assertEqual(fs.errors, [])

    def test_dangling_annotation_is_a_structural_error(self) -> None:
        # No `export const ... = defineFeature(...)` after the annotation, so it
        # dangles. This was previously invisible: string masking blanked the
        # "Feature Type Name" marker before the annotation scan ran.
        fs = check_text(_HEADER + 'annotation { "Feature Type Name" : "Orphan" }\n')
        self.assertTrue(any("dangling" in e for e in fs.errors), fs.errors)

    def test_commented_out_annotation_is_not_flagged(self) -> None:
        # Comments are masked, so an annotation that lives only in a comment must
        # not count as a dangling annotation.
        fs = check_text(_HEADER + '// annotation { "Feature Type Name" : "Commented out" }\n')
        self.assertFalse(any("dangling" in e for e in fs.errors), fs.errors)

    def test_annotation_in_string_literal_is_not_flagged(self) -> None:
        # A string containing the marker text is not an annotation.
        fs = check_text(
            _HEADER
            + 'const s = "annotation { \\"Feature Type Name\\" : not-an-annotation }";\n'
        )
        self.assertFalse(any("dangling" in e for e in fs.errors), fs.errors)


class PlaceholderTest(unittest.TestCase):
    def test_unreplaced_placeholder_is_a_structural_error(self) -> None:
        # The header regex tolerates {{MAJOR}} as a version, but the placeholder
        # check must still hard-stop: a template is not uploadable as-is.
        fs = check_text(
            'FeatureScript {{MAJOR}};\n'
            'import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");\n'
        )
        self.assertTrue(any("PLACEHOLDER" in e for e in fs.errors), fs.errors)

    def test_no_placeholder_no_error(self) -> None:
        fs = check_text(_VALID_FEATURE)
        self.assertFalse(any("PLACEHOLDER" in e for e in fs.errors), fs.errors)


def _fake_gap_guard(client):
    guard = mock.Mock()
    guard.client = client
    guard.budget = 22
    guard.spent = 0
    guard.exceeded.return_value = False
    guard.summary.return_value = {
        "budget": 22, "spent": 0, "remaining": 22, "annualRemaining": 100,
    }
    return guard


@contextlib.contextmanager
def _gap_env(guard, render):
    patches = [
        mock.patch.object(sys, "argv", ["live_gap_probe.py"]),
        mock.patch.object(live_gap_probe, "live_api_enabled", return_value=True),
        mock.patch.object(live_gap_probe, "rate_limit_reason", return_value=None),
        mock.patch.object(live_gap_probe, "BudgetGuard", return_value=guard),
        mock.patch.object(live_gap_probe, "eval_featurescript",
                          return_value={"errors": [], "result": [],
                                        "featureScriptVersion": "3044.0"}),
        render,
        mock.patch.object(live_gap_probe, "OUT",
                          Path(tempfile.mkdtemp()) / "gap-probe-results.json"),
    ]
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        yield


class LiveGapProbeRateLimitTest(unittest.TestCase):
    """429 must propagate out of main(), never be swallowed as a generic error."""

    def test_render_branch_reraise_rate_limited(self) -> None:
        client = mock.Mock()
        client.state = {"documentId": "did", "workspaceId": "wid"}
        guard = _fake_gap_guard(client)
        render = mock.patch.object(
            live_gap_probe, "render_preview",
            side_effect=live_gap_probe.RateLimited("429: retry after 72910s"),
        )
        with _gap_env(guard, render):
            with self.assertRaises(live_gap_probe.RateLimited):
                live_gap_probe.main()

    def test_rest_read_branch_reraise_rate_limited(self) -> None:
        client = mock.Mock()
        client.state = {"documentId": "did", "workspaceId": "wid"}
        client.request.side_effect = live_gap_probe.RateLimited("429: retry after 72910s")
        guard = _fake_gap_guard(client)
        render = mock.patch.object(live_gap_probe, "render_preview", return_value={
            "view": "iso", "width": 300, "height": 300,
            "mediaType": "image/png", "byteCount": 0, "sha256": "abc",
        })
        with _gap_env(guard, render):
            with self.assertRaises(live_gap_probe.RateLimited):
                live_gap_probe.main()


class LiveIsProbeSingletonTest(unittest.TestCase):
    def test_singleton_unattributable_error_is_recorded_not_recursive(self) -> None:
        guard = mock.Mock()
        guard.client = mock.Mock()
        guard.exceeded.return_value = False
        guard.summary.return_value = {"budget": 40, "spent": 1, "remaining": 39,
                                      "annualRemaining": 100}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "live-is-probe.json"
            probe = live_is_probe.Probe(guard, "psid", out)
            probe.pending = [("isFake", "isFake(1)")]
            with mock.patch.object(
                live_is_probe, "eval_featurescript",
                return_value={"errors": ["Attempt to dereference non-container 5"]},
            ):
                # Would recurse forever on the singleton before the fix; must
                # instead record the failure and drain the pending list.
                probe.probe(probe.pending)
        self.assertEqual(probe.pending, [])
        self.assertIn("isFake", probe.results)
        self.assertEqual(probe.results["isFake"]["verdict"], "FAILED")


if __name__ == "__main__":
    unittest.main()
