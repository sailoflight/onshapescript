"""Offline guards for the Gridfinity 4U bin browser fixture.

`dev/fixtures-capture/gridfinity-4u-bin.json` builds the bin as 23
`browser_insert_custom_feature` rows: 7 `Thin Variable` rows, then 8
`Thin Sketch Rectangle` / `Thin Extrude` pairs. Its live acceptance is a B-rep
fingerprint (`onshape_docs/verification/gridfinity-4u-bin-2026-09-21.md`), which
needs a browser run; what CAN be checked offline is the two things that have
already cost a cloud commit:

- a parameter value containing `#` (an Onshape expression, e.g.
  `#gf_pitch - #gf_gap`) must ALSO be named in that step's `expect_values`,
  because `browser_insert_custom_feature` otherwise refuses the insert with
  `unstatedExpressionKeys`. The defect this file exists for was step 13's
  `height`, filled as `#gf_pitch - #gf_gap` with no stated evaluation;
- a thin extrude consumes the region of the MOST RECENT PRECEDING thin sketch,
  so tree ORDER is semantics: every `Thin Extrude` must sit directly after its
  own `Thin Sketch Rectangle`, and an additive extrude's end section is the next
  sketch's section.

The arithmetic is re-derived from the fixture's own numbers and the documented
profile constants, never transcribed from the JSON, so a mistyped edit fails
here instead of on the server. Everything below is offline: no browser, no REST,
no network.
"""

from __future__ import annotations

import ast
import json
import math
import re
import unittest
from pathlib import Path

from onshape_browser_mode import project

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures-capture" / "gridfinity-4u-bin.json"

# Documented profile totals (kennetek/gridfinity-rebuilt-openscad, see the fixture
# description): 4U of 7 mm base plus a 4.4 mm stacking lip.
BIN_TOP_MM = 32.4
BODY_SKETCH_Z = 4.75
FOOT_BOTTOM_MM = 35.6
FOOT_BOTTOM_RADIUS = 0.8
CAVITY_WIDTH_MM = 39.6
CAVITY_RADIUS_MM = 2.8
LIP_WIDTHS_MM = (36.3, 37.7, 37.7)
LIP_Z_MM = (28.0, 28.7, 30.5)

_REFERENCE = re.compile(r"#([A-Za-z_][A-Za-z_0-9]*)")
_QUANTITY = re.compile(r"^(-?[0-9.]+)\s*mm$")
_ANGLE = re.compile(r"^(-?[0-9.]+)\s*deg$")


def _eval_node(node: ast.AST, expression: str) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand, expression)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, expression)
        right = _eval_node(node.right, expression)
        for operator, combine in (
            (ast.Add, lambda a, b: a + b),
            (ast.Sub, lambda a, b: a - b),
            (ast.Mult, lambda a, b: a * b),
            (ast.Div, lambda a, b: a / b),
        ):
            if isinstance(node.op, operator):
                return combine(left, right)
    raise AssertionError(f"expression {expression!r} uses unsupported arithmetic")


def _evaluate_mm(expression: str, variables: dict[str, float]) -> float:
    """Resolve one millimetre quantity, following `#variable` references.

    Every length in this fixture is a single millimetre quantity, so the ` mm`
    suffixes describe the whole expression and are dropped before the arithmetic.
    The text is parsed into an AST and interpreted with a small node whitelist:
    the fixture is data, and a guard for it must not `eval` that data blindly. A
    length it cannot read is an ERROR, not a skipped assertion, so a new
    expression form forces this file to be updated rather than quietly weakened.
    """
    def substitute(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name not in variables:
            raise AssertionError(f"expression {expression!r} cites undefined #{name}")
        return repr(variables[name])

    text = _REFERENCE.sub(substitute, expression).replace("mm", "").strip()
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as error:
        raise AssertionError(f"expression {expression!r} is not a millimetre quantity") from error
    return _eval_node(tree.body, expression)


class _Fixture:
    """The fixture plus the variable table its `Thin Variable` rows create."""

    def __init__(self) -> None:
        self.document = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.steps = self.document["steps"]
        self.variables: dict[str, float] = {}
        for step in self.steps:
            if step["args"]["feature_name"] != "Thin Variable":
                continue
            parameters = step["args"]["parameters"]
            # Rows are read in tree order, so a derived value can only cite a
            # variable an earlier row already created.
            self.variables[parameters["name"]] = self.length(parameters["value"])

    def args(self, index: int) -> dict:
        return self.steps[index]["args"]

    def parameters(self, index: int) -> dict:
        return self.args(index)["parameters"]

    def feature(self, index: int) -> str:
        return self.args(index)["feature_name"]

    def length(self, expression, table: dict[str, float] | None = None) -> float:
        if not isinstance(expression, str):
            raise AssertionError(f"expected a millimetre expression, found {expression!r}")
        return _evaluate_mm(expression, self.variables if table is None else table)

    def parameter_length(self, index: int, key: str) -> float:
        return self.length(self.parameters(index)[key])

    def angle(self, index: int, key: str) -> float:
        raw = self.parameters(index)[key]
        match = _ANGLE.match(str(raw).strip())
        if not match:
            raise AssertionError(f"step {index} parameter {key} is not an angle: {raw!r}")
        return float(match.group(1))

    def raw_expect(self, index: int, key: str):
        expectations = self.args(index).get("expect_values")
        if not isinstance(expectations, dict) or key not in expectations:
            raise AssertionError(
                f"{self.steps[index]['id']} states no expect_values[{key!r}]"
            )
        return expectations[key]

    def expect(self, index: int, key: str) -> float:
        raw = self.raw_expect(index, key)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return float(raw)
        return self.length(raw)

    def expressions(self, index: int) -> dict[str, str]:
        return {
            key: value
            for key, value in self.parameters(index).items()
            if isinstance(value, str) and "#" in value
        }


class Gridfinity4UBinStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = _Fixture()

    def test_the_fixture_is_a_23_step_browser_tree_in_one_part_studio(self):
        self.assertEqual(len(self.f.steps), 23)
        tabs = set()
        ids = []
        for step in self.f.steps:
            self.assertEqual(step["tool"], "browser_insert_custom_feature", step["id"])
            args = step["args"]
            self.assertIs(args["confirm_mutation"], True, step["id"])
            self.assertTrue(args["parameters"], step["id"])
            self.assertIsInstance(args["part_studio_tab"], str, step["id"])
            tabs.add(args["part_studio_tab"])
            ids.append(step["id"])
        # One existing Part Studio holds the whole tree, and every id is unique.
        self.assertEqual(tabs, {"GF 4U 盒子"})
        self.assertEqual(len(set(ids)), len(ids))

    def test_the_first_seven_steps_create_the_variable_table(self):
        for index in range(7):
            self.assertEqual(self.f.feature(index), "Thin Variable", index)
        self.assertEqual(
            [self.f.parameters(index)["name"] for index in range(7)],
            ["gf_pitch", "gf_gap", "corner_r", "base_h", "bin_h", "lip_h", "wall_t"],
        )
        # The variable layer is created once, before anything consumes it.
        self.assertNotIn("Thin Variable", [self.f.feature(index) for index in range(7, 23)])

    def test_the_eight_sketch_and_extrude_pairs_alternate_without_a_gap(self):
        tail = self.f.steps[7:]
        self.assertEqual(len(tail), 16)
        for offset, step in enumerate(tail):
            expected = "Thin Sketch Rectangle" if offset % 2 == 0 else "Thin Extrude"
            self.assertEqual(self.f.feature(7 + offset), expected, step["id"])
        # A thin extrude consumes the region of the MOST RECENT PRECEDING thin
        # sketch, so an extrude that is not directly after its own sketch would
        # silently consume the previous pair's region.
        for index in range(8, 23, 2):
            self.assertEqual(self.f.feature(index), "Thin Extrude", index)
            self.assertEqual(self.f.feature(index - 1), "Thin Sketch Rectangle", index)

    def test_four_extrudes_add_material_and_four_cut_it(self):
        additive = [
            index for index in range(7, 23)
            if self.f.feature(index) == "Thin Extrude"
            and not self.f.parameters(index).get("subtract")
        ]
        subtract = [
            index for index in range(7, 23)
            if self.f.feature(index) == "Thin Extrude"
            and self.f.parameters(index).get("subtract") is True
        ]
        # Foot flare, foot lock, foot flare again, and the 4U body block add;
        # the cavity and the ramp/lock/flare stacking-lip cuts remove.
        self.assertEqual(additive, [8, 10, 12, 14])
        self.assertEqual(subtract, [16, 18, 20, 22])


class Gridfinity4UBinExpressionGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = _Fixture()

    def test_every_expression_parameter_states_the_value_it_must_evaluate_to(self):
        """The regression this file exists for.

        A settled quantity widget renders the EVALUATED number rather than the
        typed `#variable` (measured live 2026-09-21: `#gf_pitch * 2` was filled,
        the accept landed, and the model stored `0 mm`), so
        `browser_insert_custom_feature` refuses any `#` value that is not also
        declared in `expect_values` -- and step 13's `height` was the key that
        was missing. Every expression parameter must therefore be stated, and its
        expectation must be a readable string or number.
        """
        for index, step in enumerate(self.f.steps):
            expectations = self.f.args(index).get("expect_values", {})
            for key in self.f.expressions(index):
                self.assertIn(
                    key, expectations,
                    f"{step['id']}.{key} is an unstated expression (#... value)",
                )
                stated = expectations[key]
                self.assertIsInstance(stated, (str, int, float), f"{step['id']}.{key}")
                self.assertNotIsInstance(stated, bool, f"{step['id']}.{key}")

    def test_the_body_and_cavity_sketches_state_their_resolved_values(self):
        # Values read from the fixture, cross-checked against the variable table
        # rather than trusted as literals.
        self.assertEqual(self.f.raw_expect(13, "width"), "41.5 mm")
        self.assertEqual(self.f.raw_expect(13, "height"), "41.5 mm")
        self.assertEqual(self.f.raw_expect(13, "corner_radius"), "3.75 mm")
        self.assertEqual(self.f.raw_expect(15, "width"), "39.6 mm")
        self.assertEqual(self.f.raw_expect(15, "height"), "39.6 mm")
        self.assertEqual(self.f.raw_expect(15, "corner_radius"), "2.8 mm")

        body_width = self.f.variables["gf_pitch"] - self.f.variables["gf_gap"]
        self.assertAlmostEqual(body_width, 41.5, places=9)
        self.assertAlmostEqual(self.f.expect(13, "width"), body_width, places=9)
        self.assertAlmostEqual(self.f.expect(13, "height"), body_width, places=9)
        self.assertAlmostEqual(self.f.expect(13, "corner_radius"),
                               self.f.variables["corner_r"], places=9)
        cavity_width = body_width - 2 * self.f.variables["wall_t"]
        self.assertAlmostEqual(cavity_width, 39.6, places=9)
        self.assertAlmostEqual(self.f.expect(15, "width"), cavity_width, places=9)
        self.assertAlmostEqual(self.f.expect(15, "height"), cavity_width, places=9)
        self.assertAlmostEqual(self.f.expect(15, "corner_radius"),
                               self.f.variables["corner_r"] - self.f.variables["wall_t"],
                               places=9)

    def test_every_expect_value_names_a_parameter_of_its_step(self):
        for index, step in enumerate(self.f.steps):
            parameters = self.f.parameters(index)
            for key in self.f.args(index).get("expect_values", {}):
                self.assertIn(key, parameters, f"{step['id']} states an unknown parameter {key}")


class Gridfinity4UBinGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = _Fixture()

    def test_each_45_degree_foot_extrude_reaches_the_next_sketch_section(self):
        # The foot is built by repeated thin sketches + extrudes: a 45 deg draft
        # grows the section by tan(45) * depth per SIDE, so each additive
        # extrude's end section must be the next additive sketch's section. The
        # last additive sketch (the 4U body) has no following additive sketch,
        # so its continuity target is the z top tested separately.
        self.assertEqual(self.f.parameter_length(7, "width"), FOOT_BOTTOM_MM)
        self.assertEqual(self.f.parameter_length(7, "height"), FOOT_BOTTOM_MM)
        self.assertEqual(self.f.parameter_length(7, "corner_radius"), FOOT_BOTTOM_RADIUS)
        self.assertEqual(self.f.parameter_length(8, "depth"), 0.8)
        self.assertEqual(self.f.angle(8, "draft_angle"), 45.0)
        self.assertNotIn("draft_angle", self.f.parameters(10))
        self.assertEqual(self.f.angle(12, "draft_angle"), 45.0)

        for sketch, extrude, following in ((7, 8, 9), (9, 10, 11), (11, 12, 13)):
            depth = self.f.parameter_length(extrude, "depth")
            angle = self.f.parameters(extrude).get("draft_angle")
            growth = depth * math.tan(math.radians(self.f.angle(extrude, "draft_angle"))) \
                if angle else 0.0
            self.assertAlmostEqual(
                self.f.parameter_length(sketch, "width") + 2 * growth,
                self.f.parameter_length(following, "width"), places=9,
                msg=f"step {extrude} end width must equal sketch {following}",
            )
            self.assertAlmostEqual(
                self.f.parameter_length(sketch, "height") + 2 * growth,
                self.f.parameter_length(following, "height"), places=9,
                msg=f"step {extrude} end height must equal sketch {following}",
            )
            # A 45 deg draft grows a corner arc's radius exactly as far as it
            # grows the half-width.
            self.assertAlmostEqual(
                self.f.parameter_length(sketch, "corner_radius") + growth,
                self.f.parameter_length(following, "corner_radius"), places=9,
                msg=f"step {extrude} end radius must equal sketch {following}",
            )

    def test_the_body_extrude_reaches_the_4u_lip_top(self):
        base_h = self.f.variables["base_h"]
        bin_h = self.f.variables["bin_h"]
        lip_h = self.f.variables["lip_h"]
        self.assertAlmostEqual(base_h, 7.0, places=9)
        self.assertAlmostEqual(lip_h, 4.4, places=9)
        # The 4U height is derived, not retyped: bin_h = base_h * 4.
        self.assertEqual(self.f.parameters(4)["value"], "#base_h * 4")
        self.assertAlmostEqual(bin_h, base_h * 4, places=9)
        self.assertAlmostEqual(bin_h, 28.0, places=9)

        self.assertAlmostEqual(self.f.parameter_length(13, "origin_z"), BODY_SKETCH_Z,
                               places=9)
        self.assertAlmostEqual(self.f.parameter_length(13, "width"), 41.5, places=9)
        self.assertEqual(self.f.parameters(14)["depth"], "#bin_h + #lip_h - 4.75 mm")
        self.assertAlmostEqual(self.f.expect(14, "depth"), 27.65, places=9)

        # The body extrude must end exactly on the stacking-lip top.
        top = BODY_SKETCH_Z + self.f.parameter_length(14, "depth")
        self.assertAlmostEqual(top, bin_h + lip_h, places=9)
        self.assertAlmostEqual(top, BIN_TOP_MM, places=9)
        self.assertAlmostEqual(bin_h + lip_h, BIN_TOP_MM, places=9)

    def test_the_subtract_chain_is_the_cavity_then_ramp_lock_flare(self):
        subtract = [16, 18, 20, 22]
        for index in subtract:
            self.assertIs(self.f.parameters(index).get("subtract"), True, index)

        # Cavity: from z = base_h down the inside of the body, leaving wall_t.
        self.assertEqual(self.f.parameters(15)["origin_z"], "#base_h")
        self.assertAlmostEqual(self.f.parameter_length(15, "origin_z"),
                               self.f.variables["base_h"], places=9)
        self.assertEqual(self.f.parameters(16)["depth"], "#bin_h - #base_h")
        cavity_depth = self.f.parameter_length(16, "depth")
        self.assertAlmostEqual(cavity_depth,
                               self.f.variables["bin_h"] - self.f.variables["base_h"],
                               places=9)
        self.assertAlmostEqual(cavity_depth, 21.0, places=9)
        self.assertAlmostEqual(self.f.expect(15, "width"), CAVITY_WIDTH_MM, places=9)
        self.assertAlmostEqual(self.f.expect(15, "corner_radius"), CAVITY_RADIUS_MM,
                               places=9)

        # Three stacking-lip cuts, in order: ramp (drafted), lock (straight),
        # flare (drafted). Their z and width come from the fixture.
        lip_sketches = (17, 19, 21)
        for sketch, z_mm, width_mm in zip(lip_sketches, LIP_Z_MM, LIP_WIDTHS_MM):
            self.assertAlmostEqual(self.f.parameter_length(sketch, "origin_z"), z_mm,
                                   places=9)
            self.assertAlmostEqual(self.f.parameter_length(sketch, "width"), width_mm,
                                   places=9)
            self.assertAlmostEqual(self.f.parameter_length(sketch, "height"), width_mm,
                                   places=9)
        self.assertEqual(
            [("draft_angle" in self.f.parameters(index)) for index in subtract[1:]],
            [True, False, True],
        )
        for index in (18, 22):
            self.assertEqual(self.f.angle(index, "draft_angle"), 45.0)

        # The cuts are contiguous: the cavity reaches the lip start, and the
        # three lip bands stack to the knife-edge top.
        self.assertAlmostEqual(self.f.parameter_length(15, "origin_z") + cavity_depth,
                               self.f.variables["bin_h"], places=9)
        lip_bands = (18, 20, 22)
        for cut, next_z in zip(lip_bands, (*LIP_Z_MM[1:], BIN_TOP_MM)):
            top = self.f.parameter_length(cut - 1, "origin_z") + \
                self.f.parameter_length(cut, "depth")
            self.assertAlmostEqual(top, next_z, places=9, msg=f"step {cut} ends at {next_z}")

    def test_only_bin_h_is_derived_and_the_other_variables_are_plain_quantities(self):
        variable_steps = [index for index in range(7)
                          if self.f.feature(index) == "Thin Variable"]
        self.assertEqual(
            [self.f.parameters(index)["name"] for index in variable_steps],
            ["gf_pitch", "gf_gap", "corner_r", "base_h", "bin_h", "lip_h", "wall_t"],
        )
        # Exactly one variable is derived; the rest are direct millimetre values.
        for index in variable_steps:
            value = self.f.parameters(index)["value"]
            if self.f.parameters(index)["name"] == "bin_h":
                self.assertEqual(value, "#base_h * 4")
                self.assertEqual(self.f.raw_expect(index, "value"), "28 mm")
            else:
                self.assertRegex(value, _QUANTITY,
                                 f"{self.f.parameters(index)['name']} must be a plain quantity")
        expected = {
            "gf_pitch": 42.0,
            "gf_gap": 0.5,
            "corner_r": 3.75,
            "base_h": 7.0,
            "lip_h": 4.4,
            "wall_t": 0.95,
        }
        for name, value_mm in expected.items():
            self.assertAlmostEqual(self.f.variables[name], value_mm, places=9, msg=name)
        self.assertAlmostEqual(self.f.variables["bin_h"], 28.0, places=9)


class Gridfinity4UBinConfirmation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = _Fixture()

    def test_no_step_disables_commit_verification_without_covering_its_expressions(self):
        """`verify_commit: false` returns before the workspace keeps the row, so a
        step that uses it must already have stated every expression it fills --
        otherwise the caller has no way to prove what the row evaluated to."""
        for index, step in enumerate(self.f.steps):
            if self.f.args(index).get("verify_commit") is not False:
                continue
            expectations = self.f.args(index).get("expect_values", {})
            for key in self.f.expressions(index):
                self.assertIn(key, expectations, f"{step['id']}.{key}")

    def test_the_fixture_satisfies_the_project_loader(self):
        # The real loader is the authority on top-level keys and step shape, so
        # load the fixture through it rather than restating its rules here.
        loaded = project.load_project("gridfinity-4u-bin")
        self.assertEqual(loaded, self.f.document)
        self.assertEqual(loaded["schemaVersion"], 1)
        self.assertEqual(loaded["name"], "gridfinity-4u-bin")
        self.assertIsInstance(loaded["description"], str)
        self.assertTrue(loaded["description"].strip())
        self.assertIn("steps", loaded)
        self.assertIsInstance(loaded["steps"], list)
        self.assertTrue(loaded["steps"])


class Gridfinity4UBinChineseRowNames(unittest.TestCase):
    """Every row this fixture creates must read as Chinese in the Onshape UI.

    The mechanism is a FeatureScript `Feature Name Template`, so the parameter
    that feeds it and the template that places it are two halves of one promise:
    a missing `description` renders an empty prefix, and a template that does not
    start with `#description` buries it. Both halves are checked here, plus the
    variable row, whose value must come BEFORE its description
    (`#gf_pitch = 42 mm 格距…`) or the number is hard to read.
    """

    FS = FIXTURE.parent / "thin-native-features.fs"
    CJK = re.compile(r"[\u4e00-\u9fff]")

    @classmethod
    def setUpClass(cls):
        cls.f = _Fixture()
        cls.source = cls.FS.read_text(encoding="utf-8")

    def _template(self, type_name: str) -> str:
        match = re.search(
            r'"Feature Type Name"\s*:\s*"%s"\s*,\s*"Feature Name Template"\s*:\s*"([^"]*)"'
            % re.escape(type_name),
            self.source,
        )
        self.assertIsNotNone(match, f"no Feature Name Template for {type_name}")
        return match.group(1)

    def test_every_step_carries_a_chinese_row_description(self):
        self.assertEqual(len(self.f.steps), 23)
        for index, step in enumerate(self.f.steps):
            description = self.f.parameters(index)["description"]
            self.assertIsInstance(description, str, step["id"])
            self.assertTrue(description.strip(), step["id"])
            # The user-visible requirement is Chinese in the ROW, so the value
            # must actually contain Han characters rather than transliteration.
            self.assertRegex(description, self.CJK, step["id"])

    def test_the_geometric_rows_lead_with_the_description(self):
        for type_name in ("Thin Sketch Rectangle", "Thin Extrude", "Thin Sketch Circle"):
            self.assertTrue(
                self._template(type_name).startswith("#description"),
                type_name,
            )
        # The transition rows name the angle they cut at, which is what makes the
        # row self-describing in the tree.
        ramps = [self.f.parameters(i)["description"] for i in (8, 12, 18, 22)]
        for description in ramps:
            self.assertIn("45°", description)
            self.assertIn("面" if "斜面" in description else "切除", description)

    def test_the_variable_row_keeps_its_value_before_the_description(self):
        template = self._template("Thin Variable")
        self.assertTrue(template.startswith("###name = #value"), template)
        self.assertGreater(
            template.index("#description"), template.index("#value"), template
        )
        # A variable row that states a description must also state a value.
        for index in range(7):
            parameters = self.f.parameters(index)
            self.assertTrue(parameters.get("value"), self.f.steps[index]["id"])
            self.assertRegex(parameters["description"], self.CJK)

    def test_the_description_parameter_is_a_declared_string_in_every_definition(self):
        # An undeclared parameter id is refused by the insert dialog, so each
        # thin feature must declare `definition.description is string` exactly
        # once -- the declaration is what makes the fixture's value legal.
        self.assertEqual(
            self.source.count("definition.description is string;"),
            self.source.count("defineFeature("),
        )


if __name__ == "__main__":
    unittest.main()
