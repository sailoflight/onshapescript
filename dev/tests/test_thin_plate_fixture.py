"""Offline guards for the THIN-feature Gridfinity plate fixture.

`dev/fixtures-capture/gridfinity-thin-plate.json` builds the plate as 14 thin
custom-feature rows (sketch, extrude) instead of three domain features. Its live
acceptance is a B-rep fingerprint
(`onshape_docs/verification/thin-feature-rebuild-brep-2026-09-21.md`), which needs a
browser run; what CAN be checked offline is the arithmetic a mistyped fixture edit
would break. Every value below is re-derived from the documented reference constants
(the same ones `test_gridfinity_fixture.py` pins for the domain feature) or from the
fixture's own numbers, never transcribed from the JSON.

The laws, each of which the exported solid confirms exactly:

- the four socket layers are contiguous: each sketch sits at the previous sketch's z
  plus that layer's extrude depth, and the stack ends on the plate top face;
- a 45 deg drafted layer grows the profile by its own depth per side, so the ramp
  reaches 37.7 from 36.3 over 0.7 and the flare reaches the full 42 over 2.15, which
  makes the socket opening flush with the cell boundary (the domain feature's
  `test_top_opening_is_flush_with_the_cell_boundary`);
- that same 45 deg draft grows a corner arc's radius exactly as far as it grows the
  half-width, so the corner radius tracks the offset (1.15 -> 1.85 -> 4.00);
- the magnet shaft ends exactly on the socket floor and the 45 deg mouth chamfer
  starts exactly one chamfer height below it;
- the chamfer's mouth radius stays inside the socket's corner arc, so the pocket
  cannot break through into the socket wall.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "dev/fixtures-capture/gridfinity-thin-plate.json"
SOURCE = REPO / "dev/fixtures-capture/thin-native-features.fs"

# Reference constants, identical to test_gridfinity_fixture.py.
PITCH = 42.0
OUTER_DIAMETER = 8.0
SOCKET_LAYER = 5.0
CLEARANCE = 0.35
RAMP = 0.7
LOCK = 1.8
SOCKET_BOTTOM_SIZE = 36.3
MAGNET_DIAMETER = 6.5
MAGNET_DEPTH = 2.4
MAGNET_FROM_SIDE = 8.0
MAGNET_CHAMFER = 0.8


def _mm(text: str) -> float:
    match = re.match(r"^\s*(-?[0-9.]+)\s*mm\s*$", text)
    if not match:
        raise AssertionError(f"not a length: {text!r}")
    return float(match.group(1))


def _deg(text: str) -> float:
    match = re.match(r"^\s*(-?[0-9.]+)\s*deg\s*$", text)
    if not match:
        raise AssertionError(f"not an angle: {text!r}")
    return float(match.group(1))


class ThinPlateFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.steps = cls.document["steps"]
        cls.by_id = {step["id"]: step for step in cls.steps}
        cls.source = SOURCE.read_text(encoding="utf-8")

    def params(self, step_id: str) -> dict:
        return self.by_id[step_id]["args"]["parameters"]

    # --- shape of the fixture itself -------------------------------------

    def test_every_step_inserts_one_thin_row_with_its_own_numbers(self):
        self.assertEqual(len(self.steps), 14)
        tabs = set()
        for step in self.steps:
            self.assertEqual(step["tool"], "browser_insert_custom_feature", step["id"])
            args = step["args"]
            self.assertTrue(args["confirm_mutation"], step["id"])
            # The numbers travel in the transaction that creates the row, so no row
            # is ever added with dialog defaults and edited afterwards.
            self.assertTrue(args["parameters"], step["id"])
            self.assertIn(args["feature_name"], {"Thin Sketch Rectangle", "Thin Extrude",
                                                 "Thin Sketch Circle"}, step["id"])
            tabs.add(args["part_studio_tab"])
        self.assertEqual(tabs, {"GF Thin Plate"})

    def test_the_fixture_contains_no_source_refresh_step(self):
        # browser_deploy_and_apply_featurescript reports success as built=true, which
        # needs a computed part; a sketch-only apply cannot satisfy it. The refresh is
        # therefore a separate action, proven by the compile verdict, not by a row.
        text = FIXTURE.read_text(encoding="utf-8")
        self.assertNotIn('"tool": "browser_deploy_and_apply_featurescript"', text)
        self.assertIn("browser_get_partstudio_features", text)

    def test_the_source_defines_exactly_the_features_the_fixture_uses(self):
        used = {step["args"]["feature_name"] for step in self.steps}
        self.assertEqual(used, {"Thin Sketch Rectangle", "Thin Extrude", "Thin Sketch Circle"})
        defined = set(re.findall(r'Feature Type Name"\s*:\s*"([^"]+)"', self.source))
        self.assertEqual(defined, used)

    # --- the plate body ---------------------------------------------------

    def test_plate_body_is_one_rounded_rectangle_two_cells_long(self):
        plate = self.params("01-plate-sketch")
        self.assertEqual(_mm(plate["width"]), 2 * PITCH)
        self.assertEqual(_mm(plate["height"]), 2 * PITCH)
        self.assertEqual(_mm(plate["corner_radius"]), 4.0)
        self.assertEqual(_mm(plate["origin_z"]), 0.0)
        self.assertEqual(plate["grid_x"], 1)  # one body, not per-cell rows
        self.assertEqual(plate["grid_y"], 1)
        self.assertEqual(_mm(self.params("02-plate-extrude")["depth"]), 2 * SOCKET_LAYER)

    # --- the four socket layers ------------------------------------------

    def test_the_four_socket_layers_are_contiguous_and_end_on_the_top_face(self):
        layers = [
            ("03-socket-clearance-sketch", "04-socket-clearance-cut"),
            ("05-socket-ramp-sketch", "06-socket-ramp-cut"),
            ("07-socket-lock-sketch", "08-socket-lock-cut"),
            ("09-socket-flare-sketch", "10-socket-flare-cut"),
        ]
        z = SOCKET_LAYER
        self.assertEqual(_mm(self.params(layers[0][0])["origin_z"]), z)
        for sketch_id, cut_id in layers:
            sketch = self.params(sketch_id)
            cut = self.params(cut_id)
            self.assertAlmostEqual(_mm(sketch["origin_z"]), z, places=9, msg=sketch_id)
            self.assertTrue(cut["subtract"], cut_id)
            z += _mm(cut["depth"])
        # The stack's top must land exactly on the plate's top face.
        self.assertAlmostEqual(z, 2 * SOCKET_LAYER, places=9)

    def test_layer_depths_are_the_documented_profile(self):
        for cut_id, expected_depth in (
            ("04-socket-clearance-cut", CLEARANCE),
            ("06-socket-ramp-cut", RAMP),
            ("08-socket-lock-cut", LOCK),
        ):
            self.assertAlmostEqual(_mm(self.params(cut_id)["depth"]), expected_depth, places=9)
        # The flare is whatever is left of the 5 mm socket layer.
        self.assertAlmostEqual(
            _mm(self.params("10-socket-flare-cut")["depth"]),
            SOCKET_LAYER - CLEARANCE - RAMP - LOCK,
            places=9,
        )

    def test_socket_bottom_matches_the_reference_wire_frame(self):
        sketch = self.params("03-socket-clearance-sketch")
        wire_half = (PITCH - OUTER_DIAMETER) / 2
        offset_bottom = SOCKET_BOTTOM_SIZE / 2 - wire_half
        self.assertAlmostEqual(offset_bottom, 1.15, places=9)
        self.assertAlmostEqual(_mm(sketch["width"]), SOCKET_BOTTOM_SIZE, places=9)
        self.assertAlmostEqual(_mm(sketch["height"]), SOCKET_BOTTOM_SIZE, places=9)
        # The corner arc is the reference's inner-boundary rounding.
        self.assertAlmostEqual(_mm(sketch["corner_radius"]), 1.15, places=9)
        self.assertEqual(sketch["grid_x"] * sketch["grid_y"], 4)  # 2x2 cells
        self.assertEqual(_mm(sketch["cell_pitch"]), PITCH)

    def test_a_45_degree_layer_grows_half_width_and_corner_arc_together(self):
        ramp = self.params("06-socket-ramp-cut")
        self.assertAlmostEqual(_deg(ramp["draft_angle"]), 45.0, places=9)
        growth = _mm(ramp["depth"])  # 45 deg: one side grows by its own depth
        self.assertAlmostEqual(_mm(self.params("07-socket-lock-sketch")["width"]) / 2,
                               SOCKET_BOTTOM_SIZE / 2 + growth, places=9)
        self.assertAlmostEqual(_mm(self.params("07-socket-lock-sketch")["corner_radius"]),
                               1.15 + growth, places=9)

    def test_the_flare_makes_the_socket_opening_flush_with_the_cell_boundary(self):
        flare = self.params("10-socket-flare-cut")
        self.assertAlmostEqual(_deg(flare["draft_angle"]), 45.0, places=9)
        mouth_half = _mm(self.params("09-socket-flare-sketch")["width"]) / 2 + _mm(flare["depth"])
        self.assertAlmostEqual(mouth_half, PITCH / 2, places=9)
        self.assertAlmostEqual(_mm(self.params("09-socket-flare-sketch")["corner_radius"])
                               + _mm(flare["depth"]), OUTER_DIAMETER / 2, places=9)

    # --- the magnet pockets ------------------------------------------------

    def test_magnet_pockets_are_four_per_cell_at_the_documented_offset(self):
        for step_id in ("11-magnet-sketch", "13-magnet-chamfer-sketch"):
            sketch = self.params(step_id)
            self.assertEqual(sketch["holes_x"] * sketch["holes_y"], 4, step_id)
            self.assertEqual(_mm(sketch["diameter"]), MAGNET_DIAMETER, step_id)
            self.assertEqual(sketch["grid_x"] * sketch["grid_y"], 4, step_id)
            self.assertEqual(_mm(sketch["cell_pitch"]), PITCH, step_id)
        # Documented: 8 mm in from each cell side, i.e. 13 mm from the cell centre.
        self.assertEqual(_mm(self.params("11-magnet-sketch")["hole_from_side"]), MAGNET_FROM_SIDE)
        self.assertAlmostEqual(PITCH / 2 - MAGNET_FROM_SIDE, 13.0, places=9)

    def test_the_shaft_ends_on_the_socket_floor_and_the_chamfer_starts_inside_it(self):
        shaft_top = _mm(self.params("11-magnet-sketch")["origin_z"]) + _mm(
            self.params("12-magnet-shaft-cut")["depth"]
        )
        self.assertAlmostEqual(shaft_top, SOCKET_LAYER, places=9)  # exactly the floor
        self.assertAlmostEqual(_mm(self.params("12-magnet-shaft-cut")["depth"]), MAGNET_DEPTH, places=9)
        chamfer = self.params("14-magnet-chamfer-cut")
        self.assertAlmostEqual(_deg(chamfer["draft_angle"]), 45.0, places=9)
        self.assertAlmostEqual(_mm(chamfer["depth"]), MAGNET_CHAMFER, places=9)
        chamfer_top = _mm(self.params("13-magnet-chamfer-sketch")["origin_z"]) + _mm(chamfer["depth"])
        self.assertAlmostEqual(chamfer_top, SOCKET_LAYER, places=9)  # flush with the floor
        self.assertLess(_mm(self.params("13-magnet-chamfer-sketch")["origin_z"]), shaft_top)

    def test_the_chamfer_mouth_stays_clear_of_the_socket_corner_arc(self):
        # The exported solid confirms the mouth at r = 3.25 + 0.8 = 4.05 mm. The
        # nearest material boundary is the socket's corner arc at the floor, whose
        # centre sits at half_width - radius from the cell centre; substituting
        # half_width = 17 + 1.15 and radius = 1.15 leaves exactly the 17 mm wire
        # half-width. The magnet centre is 13 mm out, so the arc centre is 4 mm away
        # diagonally and material remains.
        half_cell = PITCH / 2
        arc_centre = half_cell - OUTER_DIAMETER / 2
        magnet_centre = half_cell - MAGNET_FROM_SIDE
        distance = ((arc_centre - magnet_centre) ** 2 * 2) ** 0.5
        mouth_radius = MAGNET_DIAMETER / 2 + MAGNET_CHAMFER
        self.assertGreater(distance, mouth_radius)
        self.assertAlmostEqual(distance - mouth_radius, 1.607, places=3)


if __name__ == "__main__":
    unittest.main()
