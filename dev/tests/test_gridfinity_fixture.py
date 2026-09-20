"""Offline guards for the Gridfinity baseplate fixture.

The fixture is a FeatureScript source, so the model itself can only be verified
on the server (see `onshape_docs/verification/gridfinity-profile-2026-09-20.md`).
What CAN be checked offline is what has actually regressed before, and it cost a
cloud commit each time:

- the plate body must be a true rounded rectangle (two cross bars + four corner
  cylinders); the earlier single-bar form is a square with four round ears;
- both 45 deg side strips must be drafted with `pullVec = (0, 0, -1)`, because a
  drafted face rotates its normal TOWARD the pull vector (measured: +z made the
  strips taper inward, 17.80 mm instead of 18.50 mm at z = 5.70);
- the refresh project must not add a feature row.

The spec arithmetic is re-derived here from the documented reference constants so
that a parameter-set edit that breaks the profile is caught before a commit.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "dev/fixtures-capture/gridfinity-baseplate.fs"
REFRESH = REPO / "dev/fixtures-capture/gridfinity-refresh-fs.json"
LOCAL_CHECK = REPO / "onshape_docs/scripts/fs_local_check.py"

# Reference constants (kennetek/gridfinity-rebuilt-openscad, see the fixture header).
PITCH = 42.0
OUTER_DIAMETER = 8.0
OUTER_RADIUS = 4.0
SOCKET_LAYER = 5.0
CLEARANCE = 0.35
RAMP = 0.7
LOCK = 1.8
SOCKET_BOTTOM_SIZE = 36.3
SOCKET_BOTTOM_RADIUS = 2.3


class GridfinitySpecArithmetic(unittest.TestCase):
    def test_offsets_come_out_of_the_documented_parameter_set(self):
        wire_half = (PITCH - OUTER_DIAMETER) / 2
        offset_bottom = SOCKET_BOTTOM_SIZE / 2 - wire_half
        self.assertAlmostEqual(wire_half, 17.0, places=9)
        self.assertAlmostEqual(offset_bottom, 1.15, places=9)
        # The reference derives the inner-boundary rounding from the outer
        # radius and the profile's last point; the fixture's second parameter
        # must describe the same rounded square.
        inner_radius = SOCKET_BOTTOM_RADIUS - offset_bottom
        self.assertAlmostEqual(inner_radius, 1.15, places=9)

    def test_top_opening_is_flush_with_the_cell_boundary(self):
        wire_half = (PITCH - OUTER_DIAMETER) / 2
        offset_bottom = SOCKET_BOTTOM_SIZE / 2 - wire_half
        offset_top = offset_bottom + RAMP + (SOCKET_LAYER - CLEARANCE - RAMP - LOCK)
        self.assertAlmostEqual(offset_top, OUTER_RADIUS, places=9)
        self.assertAlmostEqual(wire_half + offset_top, PITCH / 2, places=9)


class GridfinityFixtureSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = FIXTURE.read_text(encoding="utf-8")

    def test_fixture_passes_the_local_structural_check(self):
        result = subprocess.run(
            [sys.executable, str(LOCAL_CHECK), str(FIXTURE)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_plate_body_is_built_as_a_true_rounded_rectangle(self):
        self.assertIn('id + "plateBarX"', self.source)
        self.assertIn('id + "plateBarY"', self.source)
        self.assertNotIn('id + "plateCore"', self.source)

    def test_45_degree_side_strips_use_the_measured_pull_direction(self):
        drafts = self.source.count("opDraft(context")
        self.assertEqual(drafts, 2, "the ramp band and the flare band each need one draft")
        self.assertEqual(self.source.count('"pullVec" : vector(0, 0, -1)'), drafts)
        self.assertNotIn('"pullVec" : vector(0, 0, 1)', self.source)
        for bar in ("barRampX", "barRampY", "barFlareX", "barFlareY"):
            self.assertIn(f'"bar" : "{bar}"', self.source,
                          f"{bar} must be asserted by the in-model reach check")

    def test_side_strips_carry_both_constant_bands(self):
        for bar in ("barClearX", "barClearY", "barLockX", "barLockY"):
            self.assertIn(f'id + "{bar}"', self.source)


class GridfinityRefreshProject(unittest.TestCase):
    def test_refresh_commits_without_applying_a_new_row(self):
        text = REFRESH.read_text(encoding="utf-8")
        self.assertIn('"apply": false', text)
        self.assertIn('"create_version": false', text)
        self.assertIn('"script_file": "dev/fixtures-capture/gridfinity-baseplate.fs"', text)


if __name__ == "__main__":
    unittest.main()
