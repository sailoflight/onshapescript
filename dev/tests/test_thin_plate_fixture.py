"""Offline guards for the THIN-feature Gridfinity plate fixture.

`dev/fixtures-capture/gridfinity-thin-plate.json` builds the plate as a chain of thin
custom-feature rows (variable, sketch, extrude) instead of three domain features. Its
live acceptance is a B-rep fingerprint
(`onshape_docs/verification/thin-feature-rebuild-brep-2026-09-21.md`), which needs a
browser run; what CAN be checked offline is the arithmetic a mistyped fixture edit
would break. Every value below is re-derived from the documented reference constants
(the same ones `test_gridfinity_fixture.py` pins for the domain feature) or from the
fixture's own numbers, never transcribed from the JSON.

The fixture cites repeated numbers as `#variable` instead of retyping them, so this
file resolves the variable table first and then asserts the same laws the exported
solid confirms:

- every `#reference` resolves to a variable a `Thin Variable` row actually creates;
- the four socket layers are contiguous: each sketch sits at the previous sketch's z
  plus that layer's extrude depth, and the stack ends on the plate top face;
- a 45 deg drafted layer grows the profile by its own depth per side, so the ramp
  reaches the locking square from the clearance square over 0.7 and the flare reaches
  the full cell over 2.15, which makes the socket opening flush with the cell
  boundary (the domain feature's `test_top_opening_is_flush_with_the_cell_boundary`);
- that same 45 deg draft grows a corner arc's radius exactly as far as it grows the
  half-width, so the corner radius tracks the offset (1.15 -> 1.85 -> 4.00);
- the magnet shaft ends exactly on the socket floor and the 45 mm mouth chamfer
  starts exactly one chamfer height below it;
- the chamfer's mouth radius stays inside the socket's corner arc, so the pocket
  cannot break through into the socket wall.

The resolver is deliberately strict: a length it cannot read is an ERROR, not a
skipped assertion, so a new expression form in the fixture forces this file to be
updated rather than quietly weakening the guard.
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

_LENGTH = re.compile(r"^(-?[0-9.]+)\s*mm\s*$")
_ANGLE = re.compile(r"^(-?[0-9.]+)\s*deg\s*$")
_SCALED_REF = re.compile(r"^#([A-Za-z_][A-Za-z_0-9]*)\s*\*\s*(-?[0-9.]+)\s*$")
_REF = re.compile(r"^#([A-Za-z_][A-Za-z_0-9]*)$")


class _Fixture:
    """The fixture plus the variable table its `Thin Variable` rows create."""

    def __init__(self) -> None:
        self.document = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.steps = self.document["steps"]
        # Keyed by the semantic part of the id, so a step's ordinal in the chain
        # never has to be repeated here.
        self.by_role = {step["id"].split("-", 1)[1]: step for step in self.steps}
        self.variables: dict[str, float] = {}
        for step in self.steps:
            if step["args"]["feature_name"] == "Thin Variable":
                parameters = step["args"]["parameters"]
                role = step["id"].split("-", 1)[1]
                self.variables[parameters["name"]] = self.length(role, "value", self.variables)

    def step(self, role: str) -> dict:
        if role not in self.by_role:
            raise AssertionError(f"no fixture step named {role}; have {sorted(self.by_role)}")
        return self.by_role[role]

    def raw(self, role: str, key: str):
        parameters = self.step(role)["args"]["parameters"]
        if key not in parameters:
            raise AssertionError(f"{role} has no parameter {key}: {sorted(parameters)}")
        return parameters[key]

    def length(self, role: str, key: str, variables: dict[str, float] | None = None) -> float:
        """Resolve one length parameter, following `#variable` references."""
        table = self.variables if variables is None else variables
        value = self.raw(role, key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            # A bare number is millimetres only for the fields that are counts; the
            # caller asks for lengths, so a bare number here is a fixture mistake.
            raise AssertionError(f"{role}.{key} is {value!r}, expected a length expression")
        text = str(value).strip()
        literal = _LENGTH.match(text)
        if literal:
            return float(literal.group(1))
        reference = _REF.match(text)
        if reference:
            name = reference.group(1)
            if name not in table:
                raise AssertionError(f"{role}.{key} cites undefined variable #{name}")
            return table[name]
        scaled = _SCALED_REF.match(text)
        if scaled:
            name = scaled.group(1)
            if name not in table:
                raise AssertionError(f"{role}.{key} cites undefined variable #{name}")
            return table[name] * float(scaled.group(2))
        raise AssertionError(f"{role}.{key} is not a resolvable length: {text!r}")

    def angle(self, role: str, key: str) -> float:
        match = _ANGLE.match(str(self.raw(role, key)).strip())
        if not match:
            raise AssertionError(f"{role}.{key} is not an angle: {self.raw(role, key)!r}")
        return float(match.group(1))

    def count(self, role: str, key: str) -> int:
        value = self.raw(role, key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise AssertionError(f"{role}.{key} is not a count: {value!r}")
        return value


class ThinPlateFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = _Fixture()
        cls.source = SOURCE.read_text(encoding="utf-8")

    # --- shape of the fixture itself -------------------------------------

    def test_every_step_inserts_one_thin_row_with_its_own_numbers(self):
        tabs = set()
        for step in self.f.steps:
            self.assertEqual(step["tool"], "browser_insert_custom_feature", step["id"])
            args = step["args"]
            self.assertTrue(args["confirm_mutation"], step["id"])
            # The numbers travel in the transaction that creates the row, so no row
            # is ever added with dialog defaults and edited afterwards.
            self.assertTrue(args["parameters"], step["id"])
            tabs.add(args["part_studio_tab"])
        self.assertEqual(tabs, {"GF Thin Plate"})

    def test_a_variable_description_carries_the_chinese_and_the_labels_do_not(self):
        """中文只出现在参数**值**里；注解串仍然全是 ASCII。

        Measured live 2026-09-20 (`onshape_docs/experience/featurescript.md`, the four
        deploys): a non-ASCII `annotation { "Name" }` kills the WHOLE feature ("Invalid
        character in 'Name' annotation: only printable ASCII allowed"), while a
        non-ASCII string VALUE compiles clean and shows in the UI. So the variable
        description -- a value -- carries the Chinese, and every annotated label, the
        feature type name and the row template stay printable ASCII.
        """
        cjk = re.compile(r"[\u4e00-\u9fff]")
        described = 0
        for step in self.f.steps:
            if step["args"]["feature_name"] != "Thin Variable":
                continue
            description = step["args"]["parameters"]["description"]
            self.assertIsInstance(description, str, step["id"])
            self.assertRegex(description, cjk, f"{step['id']} needs a Chinese description")
            described += 1
        self.assertEqual(described, 9, "every variable row carries a Chinese description")
        # The row template must actually RENDER the description. Without it the Chinese
        # is reachable only from inside the feature dialog and the Feature List row --
        # the thing a human reads -- stays `gf_pitch = 42 mm`. `#description` is the
        # same placeholder variable.fs's own Tooltip Template uses (variable.fs:157).
        self.assertIn(
            '"Feature Name Template" : "###name = #value #description"',
            self.source,
            "the Thin Variable row must render its Chinese description",
        )
        annotations = re.findall(
            r'"(?:Name|Feature Type Name|Feature Name Template)"\s*:\s*"([^"]*)"',
            self.source,
        )
        self.assertTrue(annotations, "the thin-feature source has no annotations to check")
        for value in annotations:
            self.assertTrue(
                value.isascii() and value.isprintable(),
                f"annotation strings must stay printable ASCII, found {value!r}",
            )

    def test_the_fixture_contains_no_source_refresh_step(self):
        # browser_deploy_and_apply_featurescript reports success as built=true, which
        # needs a computed part; a sketch-only apply cannot satisfy it. The refresh is
        # therefore its own project, proven by the compile verdict, not by a row.
        text = FIXTURE.read_text(encoding="utf-8")
        self.assertNotIn('"tool": "browser_deploy_and_apply_featurescript"', text)
        self.assertIn("thin-features-refresh-fs", text)
        self.assertIn("browser_get_partstudio_features", text)

    def test_the_source_defines_exactly_the_features_the_fixture_uses(self):
        used = {step["args"]["feature_name"] for step in self.f.steps}
        self.assertEqual(used, {"Thin Variable", "Thin Sketch Rectangle", "Thin Extrude",
                               "Thin Sketch Circle"})
        defined = set(re.findall(r'Feature Type Name"\s*:\s*"([^"]+)"', self.source))
        self.assertEqual(defined, used)

    # --- the variable layer ------------------------------------------------

    def test_every_cited_variable_is_created_before_it_is_used(self):
        created: set[str] = set()
        for step in self.f.steps:
            parameters = step["args"]["parameters"]
            if step["args"]["feature_name"] == "Thin Variable":
                self.assertNotIn(parameters["name"], created, f"{step['id']} redefines a variable")
                created.add(parameters["name"])
                continue
            for key, value in parameters.items():
                if isinstance(value, str) and value.strip().startswith("#"):
                    name = re.split(r"[^A-Za-z_0-9]", value.strip()[1:])[0]
                    self.assertIn(name, created,
                                  f"{step['id']}.{key} cites #{name} before it is created")

    def test_the_variable_table_is_the_documented_spec(self):
        self.assertEqual(self.f.variables, {
            "gf_pitch": PITCH,
            "gf_plate_size": 2 * PITCH,
            "gf_plate_corner": OUTER_DIAMETER / 2,
            "gf_socket": SOCKET_BOTTOM_SIZE,
            "gf_socket_r": 1.15,
            "gf_lock": 37.7,
            "gf_lock_r": 1.85,
            "gf_magnet_d": MAGNET_DIAMETER,
            "gf_magnet_side": MAGNET_FROM_SIDE,
        })

    def test_the_plate_size_is_derived_from_the_pitch(self):
        # The whole point of the variable layer: 84 mm is two cells, not a number a
        # human has to remember to change in a second place.
        self.assertEqual(str(self.f.raw("var-plate-size", "value")).replace(" ", ""),
                         "#gf_pitch*2")

    def test_the_derived_row_states_the_value_the_expression_must_evaluate_to(self):
        """An expression cannot be read back from the dialog, so the row carries it.

        The quantity widget renders the EVALUATED quantity, never the typed text
        (measured live 2026-09-21: the dialog read `0 mm` for `#gf_pitch * 2` while
        the row read `84 mm`), and a Variable row is the only row that prints its
        numbers. The expectation is written as the RESULT, which is what makes it a
        check: change the pitch and this line has to change with it.
        """
        step = self.f.step("var-plate-size")
        self.assertEqual(step["args"]["expect_row"],
                         f"#gf_plate_size = {2 * PITCH:g} mm")

    def test_a_cited_variable_is_confirmed_by_the_value_it_must_evaluate_to(self):
        """Every `#expression` in the fixture states the value it must resolve to.

        A settled quantity widget renders the resolved number instead of the typed
        `#gf_socket` (measured live 2026-09-21: the same field read the expression 4 ms
        after the fill and `36.3 mm` 20 s later), and the accept is refused while the
        field still shows the text. So every step that fills an expression states the
        number it must settle on -- including the derived `#gf_pitch * 2`, whose settled
        readback is `84 mm` like any other quantity. The expectation is re-derived here
        from the fixture's own constants, so a wrong constant is caught offline rather
        than by a wrong plate.
        """
        for step in self.f.steps:
            role = step["id"].split("-", 1)[1]
            parameters = step["args"]["parameters"]
            cited = {
                key for key, value in parameters.items()
                if isinstance(value, str) and "#" in value
            }
            expect_values = step["args"].get("expect_values", {})
            self.assertEqual(set(expect_values), cited,
                             f"{step['id']} must state the resolved value of each expression")
            for key in cited:
                stated = str(expect_values[key]).replace(" ", "").removesuffix("mm")
                self.assertEqual(float(stated), self.f.length(role, key),
                                 f"{step['id']}.{key} states the wrong resolved value")

    def test_only_an_expression_step_states_a_resolved_value(self):
        """`expect_values` is about the async race, so a literal step carries none."""
        for step in self.f.steps:
            parameters = step["args"]["parameters"]
            expression = any(
                isinstance(value, str) and "#" in value for value in parameters.values()
            )
            if expression:
                self.assertTrue(step["args"].get("expect_values"), step["id"])
            else:
                self.assertNotIn("expect_values", step["args"], step["id"])

    def test_only_the_derived_variable_row_carries_a_row_expectation(self):
        """Only a Variable row renders its values, so only it can state them.

        The rows whose features have no "Feature Name Template" (the sketch and
        extrude rows) display their Feature Type Name and no numbers at all: there is
        nothing in their text to check even though they cite `#variables`. A Variable
        row renders `#name = value`, which is where an expression's evaluated value
        is read -- so the expectation belongs to exactly the derived Variable row.
        """
        for step in self.f.steps:
            parameters = step["args"]["parameters"]
            derived = (
                step["args"]["feature_name"] == "Thin Variable"
                and isinstance(parameters.get("value"), str)
                and "#" in parameters["value"]
            )
            if derived:
                self.assertTrue(step["args"].get("expect_row"),
                                f"{step['id']} derives a value without expect_row")
            else:
                self.assertNotIn("expect_row", step["args"], step["id"])

    # --- the plate body ---------------------------------------------------

    def test_plate_body_is_one_rounded_rectangle_two_cells_long(self):
        size = self.f.length("plate-sketch", "width")
        self.assertEqual(size, 2 * PITCH)
        self.assertEqual(self.f.length("plate-sketch", "height"), size)
        self.assertEqual(self.f.length("plate-sketch", "corner_radius"), OUTER_DIAMETER / 2)
        self.assertEqual(self.f.length("plate-sketch", "origin_z"), 0.0)
        self.assertEqual(self.f.count("plate-sketch", "grid_x"), 1)  # one body, not per cell
        self.assertEqual(self.f.count("plate-sketch", "grid_y"), 1)
        self.assertEqual(self.f.length("plate-extrude", "depth"), 2 * SOCKET_LAYER)

    # --- the four socket layers ------------------------------------------

    def test_the_four_socket_layers_are_contiguous_and_end_on_the_top_face(self):
        layers = [
            ("socket-clearance-sketch", "socket-clearance-cut"),
            ("socket-ramp-sketch", "socket-ramp-cut"),
            ("socket-lock-sketch", "socket-lock-cut"),
            ("socket-flare-sketch", "socket-flare-cut"),
        ]
        z = SOCKET_LAYER
        for sketch_role, cut_role in layers:
            self.assertAlmostEqual(self.f.length(sketch_role, "origin_z"), z, places=9,
                                   msg=sketch_role)
            self.assertTrue(self.f.step(cut_role)["args"]["parameters"]["subtract"], cut_role)
            z += self.f.length(cut_role, "depth")
        # The stack's top must land exactly on the plate's top face.
        self.assertAlmostEqual(z, 2 * SOCKET_LAYER, places=9)

    def test_layer_depths_are_the_documented_profile(self):
        for cut_role, expected in (("socket-clearance-cut", CLEARANCE),
                                   ("socket-ramp-cut", RAMP),
                                   ("socket-lock-cut", LOCK)):
            self.assertAlmostEqual(self.f.length(cut_role, "depth"), expected, places=9)
        # The flare is whatever is left of the 5 mm socket layer.
        self.assertAlmostEqual(self.f.length("socket-flare-cut", "depth"),
                               SOCKET_LAYER - CLEARANCE - RAMP - LOCK, places=9)

    def test_socket_bottom_matches_the_reference_wire_frame(self):
        wire_half = (PITCH - OUTER_DIAMETER) / 2
        offset_bottom = SOCKET_BOTTOM_SIZE / 2 - wire_half
        self.assertAlmostEqual(offset_bottom, 1.15, places=9)
        self.assertEqual(self.f.length("socket-clearance-sketch", "width"), SOCKET_BOTTOM_SIZE)
        self.assertEqual(self.f.length("socket-clearance-sketch", "height"), SOCKET_BOTTOM_SIZE)
        # The corner arc is the reference's inner-boundary rounding.
        self.assertEqual(self.f.length("socket-clearance-sketch", "corner_radius"), 1.15)
        self.assertEqual(self.f.count("socket-clearance-sketch", "grid_x") *
                         self.f.count("socket-clearance-sketch", "grid_y"), 4)  # 2x2 cells
        self.assertEqual(self.f.length("socket-clearance-sketch", "cell_pitch"), PITCH)

    def test_a_45_degree_layer_grows_half_width_and_corner_arc_together(self):
        self.assertAlmostEqual(self.f.angle("socket-ramp-cut", "draft_angle"), 45.0, places=9)
        growth = self.f.length("socket-ramp-cut", "depth")  # 45 deg: one side grows by it
        lock = self.f.step("socket-lock-sketch")["args"]["parameters"]
        self.assertAlmostEqual(self.f.length("socket-lock-sketch", "width") / 2,
                               SOCKET_BOTTOM_SIZE / 2 + growth, places=9)
        self.assertAlmostEqual(self.f.length("socket-lock-sketch", "corner_radius"),
                               1.15 + growth, places=9)
        self.assertEqual(lock["width"], lock["height"])

    def test_the_flare_makes_the_socket_opening_flush_with_the_cell_boundary(self):
        flare = self.f.step("socket-flare-cut")["args"]["parameters"]
        self.assertAlmostEqual(self.f.angle("socket-flare-cut", "draft_angle"), 45.0, places=9)
        mouth_half = self.f.length("socket-flare-sketch", "width") / 2 + \
            self.f.length("socket-flare-cut", "depth")
        self.assertAlmostEqual(mouth_half, PITCH / 2, places=9)
        self.assertAlmostEqual(self.f.length("socket-flare-sketch", "corner_radius") +
                               self.f.length("socket-flare-cut", "depth"),
                               OUTER_DIAMETER / 2, places=9)
        self.assertTrue(flare["subtract"])

    # --- the magnet pockets ------------------------------------------------

    def test_magnet_pockets_are_four_per_cell_at_the_documented_offset(self):
        for role in ("magnet-sketch", "magnet-chamfer-sketch"):
            self.assertEqual(self.f.count(role, "holes_x") * self.f.count(role, "holes_y"), 4, role)
            self.assertEqual(self.f.length(role, "diameter"), MAGNET_DIAMETER, role)
            self.assertEqual(self.f.count(role, "grid_x") * self.f.count(role, "grid_y"), 4, role)
            self.assertEqual(self.f.length(role, "cell_pitch"), PITCH, role)
        # Documented: 8 mm in from each cell side, i.e. 13 mm from the cell centre.
        self.assertEqual(self.f.length("magnet-sketch", "hole_from_side"), MAGNET_FROM_SIDE)
        self.assertAlmostEqual(PITCH / 2 - MAGNET_FROM_SIDE, 13.0, places=9)

    def test_the_magnet_pocket_is_the_two_step_depth_the_spec_documents(self):
        """2.4 mm deep in two cuts: 1.6 straight, then a 0.8 chamfer to the floor.

        The depth is SPLIT, not repeated. Measured against the accepted baseline
        (``thin-feature-rebuild-brep-2026-09-21.md``): the magnet pocket's straight
        section is the cylinder r=3.25 over z 2.60..4.20, and its mouth is the cone
        z 4.20..5.00, which is 1.6 + 0.8 = 2.4 mm. An earlier revision of this
        fixture cut the full 2.4 mm in one step AND then cut the chamfer on top of
        it, so the chamfer removed nothing; the two steps must meet, not overlap.
        """
        shaft = self.f.length("magnet-shaft-cut", "depth")
        self.assertAlmostEqual(shaft, MAGNET_DEPTH - MAGNET_CHAMFER, places=9)
        shaft_top = self.f.length("magnet-sketch", "origin_z") + shaft
        self.assertAlmostEqual(self.f.angle("magnet-chamfer-cut", "draft_angle"), 45.0, places=9)
        self.assertAlmostEqual(self.f.length("magnet-chamfer-cut", "depth"), MAGNET_CHAMFER,
                               places=9)
        # The chamfer starts exactly where the shaft ends, and reaches the floor.
        self.assertAlmostEqual(self.f.length("magnet-chamfer-sketch", "origin_z"), shaft_top,
                               places=9)
        chamfer_top = self.f.length("magnet-chamfer-sketch", "origin_z") + \
            self.f.length("magnet-chamfer-cut", "depth")
        self.assertAlmostEqual(chamfer_top, SOCKET_LAYER, places=9)  # flush with the floor
        # And the two steps add up to the documented single depth.
        self.assertAlmostEqual(self.f.length("magnet-sketch", "origin_z") + MAGNET_DEPTH,
                               SOCKET_LAYER, places=9)

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
