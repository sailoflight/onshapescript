"""Offline proof for the whole-feature capability contract.

Three kinds of evidence, none of which needs a browser, the network, or Onshape:

1. the contract itself -- bounded values only, defaults filled, unknown names and
   out-of-range numbers refused, and no implementation in a card;
2. the generated FeatureScript references only symbols the vendored reference
   actually contains (calls, enums, and constants), which is the strongest check
   available without compiling;
3. the precedent is faithful -- `custom.spiral_ridge` renders exactly the source
   the live-verified `browser_spiral_ridge` path generates, and the generic
   deploy tool accepts a capability instead of a raw script.

What this does NOT prove: that the generated source compiles, or that the feature
computes geometry. Both need the real workbench and are recorded as open.
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from mcp_main.win.mcp import browser_tools
from onshape_browser_mode import capabilities
from onshape_browser_mode.modeling_transactions import generate_spiral_ridge_script
from onshape_docs.query import fs_check, fs_reference

# FeatureScript language keywords and built-in type names that are legitimately
# not function entries in the reference index.
_LANGUAGE_NAMES = {
    "if", "else", "for", "while", "return", "try", "silent", "function", "const",
    "var", "export", "import", "annotation", "precondition", "new", "is", "as",
    "true", "false", "not", "and", "or", "map", "array", "undefined",
    "Context", "Id", "Query", "Vector", "ValueWithUnits", "boolean", "number",
    "string", "EntityType",
}
_CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
_ENUM_MEMBER = re.compile(r"\b([A-Z][A-Za-z]*)\s*\.\s*([A-Z_][A-Z0-9_]*)")
_CONSTANT = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")


def _index_names() -> set[str]:
    names = {entry.get("name") for entry in fs_reference._all_entries()}
    # The gate is worthless if the index silently came back empty.
    assert len(names) > 1000, f"the FeatureScript index looks truncated: {len(names)} names"
    return names


class ContractTest(unittest.TestCase):
    def test_cards_carry_no_implementation(self) -> None:
        for card in capabilities.cards():
            with self.subTest(capability=card["id"]):
                self.assertEqual(
                    set(card),
                    {"id", "featureType", "useWhen", "aliases", "parameters",
                     "sourceVerification", "notes"},
                )
                for parameter in card["parameters"]:
                    self.assertIn(parameter["kind"], {"length", "number", "boolean", "enum"})
                rendered = repr(card)
                self.assertNotIn("defineFeature", rendered)
                self.assertNotIn("import(path", rendered)

    def test_no_capability_exposes_a_query(self) -> None:
        """A caller supplies values, never geometry picks: a query stays inside the
        generated feature so a human picks it where the geometry is visible, and
        never appears in the card."""
        for capability in capabilities.CAPABILITIES:
            with self.subTest(capability=capability.id):
                self.assertNotIn("query", {p.kind for p in capability.parameters})
                self.assertNotIn("Query", repr(capability.card()))

    def test_defaults_are_filled_in(self) -> None:
        plan = capabilities.plan("custom.fillet")
        self.assertEqual(plan["values"], {"radius": 2.0, "tangent_propagation": True})
        self.assertEqual(plan["featureName"], "Bounded fillet")
        self.assertEqual(plan["alias"], {"requested": "custom.fillet", "resolved": "custom.fillet"})
        self.assertGreater(plan["sourceLength"], 200)
        self.assertEqual(plan["lineCount"], plan["source"].count("\n") + 1)

    def test_unknown_parameter_names_the_known_ones(self) -> None:
        with self.assertRaisesRegex(capabilities.CapabilityError, "radius"):
            capabilities.plan("custom.fillet", {"radius": 2, "raduis": 3})

    def test_out_of_range_and_wrong_type_are_refused(self) -> None:
        cases = {
            "custom.fillet": [
                ({"radius": 0}, "radius must be >= 0.01"),
                ({"radius": 10_000}, "radius must be <= 500.0"),
                ({"radius": "3"}, "radius must be a number"),
                ({"radius": True}, "radius must be a number"),
                ({"radius": float("nan")}, "radius must be a finite number"),
                ({"tangent_propagation": "yes"}, "tangent_propagation must be true or false"),
            ],
            "custom.extrude": [
                ({"depth": 0}, "depth must be >= 0.001"),
                ({"remove": 1}, "remove must be true or false"),
            ],
        }
        for name, failures in cases.items():
            for values, message in failures:
                with self.subTest(capability=name, values=values):
                    with self.assertRaisesRegex(capabilities.CapabilityError, message):
                        capabilities.plan(name, values)

    def test_enum_parameters_are_closed(self) -> None:
        # No shipped capability uses an enum yet; the contract must still refuse
        # a value outside its choices rather than passing it through.
        parameter = capabilities.Parameter(
            name="mode", kind="enum", description="", default="a", choices=("a", "b"),
        )
        self.assertEqual(parameter.validate("b"), "b")
        with self.assertRaisesRegex(capabilities.CapabilityError, "must be one of a, b"):
            parameter.validate("c")
        self.assertEqual(parameter.card()["choices"], ["a", "b"])

    def test_aliases_resolve_and_an_unknown_name_lists_the_known_ids(self) -> None:
        self.assertIs(capabilities.resolve("fillet"), capabilities.resolve("custom.fillet"))
        self.assertIs(capabilities.resolve("圆角"), capabilities.resolve("custom.fillet"))
        self.assertIs(capabilities.resolve("CUSTOM.EXTRUDE"), capabilities.resolve("extrude"))
        with self.assertRaisesRegex(capabilities.CapabilityError, "known capabilities"):
            capabilities.resolve("custom.thread")
        with self.assertRaisesRegex(capabilities.CapabilityError, "non-empty string"):
            capabilities.resolve("")

    def test_duplicate_aliases_cannot_be_registered(self) -> None:
        """A second capability claiming an existing alias is refused, so routing
        can never become ambiguous."""
        twin = capabilities.Capability(
            id="custom.twin", feature_type="T", export_name="t", use_when="",
            parameters=(), build_source=lambda values: "", aliases=("fillet",),
        )
        with mock.patch.object(capabilities, "CAPABILITIES", (*capabilities.CAPABILITIES, twin)):
            with self.assertRaisesRegex(capabilities.CapabilityError, "claimed twice"):
                capabilities.resolve("custom.twin")

    def test_every_capability_is_reachable_by_id_suffix_and_alias(self) -> None:
        for capability in capabilities.CAPABILITIES:
            with self.subTest(capability=capability.id):
                for name in (capability.id, capability.id.split(".", 1)[-1], *capability.aliases):
                    self.assertIs(capabilities.resolve(name), capability)


class SymbolGateTest(unittest.TestCase):
    """Generated FeatureScript may only name symbols the reference contains."""

    def _sources(self) -> list[tuple[str, str]]:
        cases = [
            ("custom.spiral_ridge", None),
            ("custom.spiral_ridge", {"pitch": 1.5, "length": 6, "clockwise": True}),
            ("custom.fillet", None),
            ("custom.fillet", {"radius": 0.25, "tangent_propagation": False}),
            ("custom.extrude", None),
            ("custom.extrude", {"depth": 40, "remove": True}),
            ("custom.hole", None),
            ("custom.hole", {"diameter": 8, "depth": 12, "through": True}),
        ]
        return [(name, capabilities.plan(name, values)["source"]) for name, values in cases]

    def _code(self, source: str) -> str:
        """Code only: an annotation string is prose, not a symbol reference."""
        return fs_check.strip_strings_and_comments(source)

    def test_every_called_function_exists_in_the_reference(self) -> None:
        names = _index_names()
        for capability, source in self._sources():
            with self.subTest(capability=capability):
                called = set(_CALL.findall(self._code(source)))
                unknown = sorted(
                    name for name in called
                    if name not in names and name not in _LANGUAGE_NAMES
                )
                self.assertEqual(unknown, [], f"{capability} calls unknown symbol(s)")

    def test_every_enum_member_exists_on_its_enum(self) -> None:
        names = _index_names()
        for capability, source in self._sources():
            with self.subTest(capability=capability):
                pairs = set(_ENUM_MEMBER.findall(self._code(source)))
                self.assertTrue(pairs, "the templates are expected to use enums")
                for type_name, member in sorted(pairs):
                    # EntityType is a built-in enum in the language, not an index entry.
                    if type_name == "EntityType":
                        continue
                    self.assertIn(type_name, names, f"{type_name} is not a known type")
                    entry = fs_reference.get_type(type_name) or {}
                    values = {value.get("name") for value in entry.get("values") or []}
                    self.assertIn(member, values, f"{type_name}.{member} does not exist")

    def test_every_referenced_constant_exists_in_the_reference(self) -> None:
        names = _index_names()
        members = {member for _type, member in _ENUM_MEMBER.findall(" ".join(
            self._code(source) for _name, source in self._sources()
        ))}
        for capability, source in self._sources():
            with self.subTest(capability=capability):
                constants = {
                    name for name in _CONSTANT.findall(self._code(source))
                    if name not in members and name not in {"NO", "YES", "BLIND"}
                }
                unknown = sorted(name for name in constants if name not in names)
                self.assertEqual(unknown, [], f"{capability} references unknown constant(s)")

    def test_the_bounds_constants_are_the_standard_library_ones(self) -> None:
        fillet = capabilities.plan("custom.fillet")["source"]
        extrude = capabilities.plan("custom.extrude")["source"]
        hole = capabilities.plan("custom.hole")["source"]
        self.assertIn("isLength(definition.radius, BLEND_BOUNDS)", fillet)
        self.assertIn("isLength(definition.depth, LENGTH_BOUNDS)", extrude)
        self.assertIn("isLength(definition.diameter, LENGTH_BOUNDS)", hole)

    def test_the_hole_is_built_from_the_documented_constructors(self) -> None:
        """The hole was rejected once for a guessed `holeDefinition`; the
        vendored constructors make it checkable instead, so the shape is pinned
        here: profiles from `holeProfile`, axes from the human's two picks."""
        source = capabilities.plan("custom.hole")["source"]
        self.assertIn("holeDefinition(profiles)", source)
        self.assertIn("HolePositionReference.AXIS_POINT", source)
        self.assertIn('"axes" : [line(evVertexPoint(', source)
        self.assertIn("definition.vertex is Query", source)
        self.assertIn("definition.face is Query", source)
        self.assertIn("definition.through", source)
        self.assertIn(
            "holeProfile(HolePositionReference.LAST_TARGET_END, 0 * millimeter, 0 * millimeter)",
            source,
        )

    def test_sources_pass_the_local_structural_checker(self) -> None:
        for capability, source in self._sources():
            with self.subTest(capability=capability):
                result = fs_check.check_source(
                    fs_check.FsFile.from_text(source, name=f"<{capability}>")
                ).as_result()
                self.assertEqual(result["errors"], [], f"{capability} failed the local checker")
                self.assertTrue(result["checked"])
                self.assertTrue(result["clear"])


class PrecedentFidelityTest(unittest.TestCase):
    def test_spiral_ridge_renders_the_live_verified_source(self) -> None:
        values = {
            "base_radius": 9.5, "pitch": 2.5, "ridge_width": 0.9,
            "ridge_height": 0.6, "length": 18.0, "clockwise": True,
        }
        rendered = capabilities.plan("custom.spiral_ridge", values)["source"]
        expected = generate_spiral_ridge_script(
            base_radius_mm=9.5, pitch_mm=2.5, ridge_width_mm=0.9,
            ridge_height_mm=0.6, length_mm=18.0, clockwise=True,
        )
        self.assertEqual(rendered, expected)

    def test_the_verified_capability_says_so_and_the_others_do_not(self) -> None:
        by_id = {capability.id: capability for capability in capabilities.CAPABILITIES}
        self.assertEqual(by_id["custom.spiral_ridge"].source_verified, "live-verified")
        for capability_id in ("custom.fillet", "custom.extrude"):
            # Honest labelling: these are checked structurally, not compiled.
            self.assertEqual(by_id[capability_id].source_verified, "structural-only")
            self.assertTrue(by_id[capability_id].notes)
            self.assertTrue(by_id[capability_id].use_when)


class DeployToolCapabilityTest(unittest.TestCase):
    """The generic deploy tool accepts a capability instead of a raw script."""

    def test_script_route_still_works_and_carries_a_local_check(self) -> None:
        script, feature_name, capability_plan, local_check = browser_tools._resolve_deploy_source({
            "script": "FeatureScript 3044;\n", "feature_name": "Anything",
        })
        self.assertEqual((script, feature_name), ("FeatureScript 3044;\n", "Anything"))
        self.assertIsNone(capability_plan)
        self.assertTrue(local_check["advisory"])
        # An arbitrary caller script is reported, not corrected or blocked: this
        # one is not a valid FeatureScript module, and the verdict says so.
        self.assertEqual(local_check["errorCount"], 1)
        self.assertTrue(local_check["errors"])

    def test_capability_route_supplies_source_name_and_check(self) -> None:
        script, feature_name, capability_plan, local_check = browser_tools._resolve_deploy_source({
            "capability": "fillet", "values": {"radius": 4},
        })
        self.assertEqual(feature_name, "Bounded fillet")
        self.assertEqual(capability_plan["capability"]["id"], "custom.fillet")
        self.assertEqual(capability_plan["values"]["radius"], 4.0)
        self.assertEqual(script, capabilities.plan("custom.fillet", {"radius": 4})["source"])
        self.assertEqual(capability_plan["localCheck"]["errors"], [])
        self.assertEqual(local_check, capability_plan["localCheck"])

    def test_an_explicit_feature_name_still_wins(self) -> None:
        _script, feature_name, _plan, _check = browser_tools._resolve_deploy_source({
            "capability": "custom.extrude", "feature_name": "Bounded extrude 1",
        })
        self.assertEqual(feature_name, "Bounded extrude 1")

    def test_script_and_capability_together_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "never both"):
            browser_tools._resolve_deploy_source({
                "script": "FeatureScript 3044;\n", "capability": "custom.fillet",
            })

    def test_neither_route_names_both_options(self) -> None:
        with self.assertRaisesRegex(ValueError, "or a `capability`"):
            browser_tools._resolve_deploy_source({"feature_name": "x"})

    def test_an_invalid_capability_value_is_refused_before_any_browser_work(self) -> None:
        with self.assertRaisesRegex(capabilities.CapabilityError, "radius must be <="):
            browser_tools._resolve_deploy_source({
                "capability": "custom.fillet", "values": {"radius": 900},
            })

    def test_dry_run_previews_the_generated_source_without_a_browser(self) -> None:
        preview = browser_tools.browser_deploy_and_apply_featurescript({
            "dry_run": True,
            "confirm_mutation": True,
            "capability": "custom.extrude",
            "values": {"depth": 12, "remove": True},
        })
        self.assertTrue(preview["dryRun"])
        self.assertEqual(preview["estimatedApiRequests"], 0)
        self.assertEqual(preview["capability"]["capability"]["id"], "custom.extrude")
        self.assertEqual(preview["capability"]["values"], {"depth": 12.0, "remove": True})
        self.assertIn('"operationType" : BooleanOperationType.SUBTRACTION', preview["capability"]["source"])
        self.assertEqual(preview["localCheck"]["errorCount"], 0)
        self.assertTrue(preview["localCheck"]["advisory"])
        # The raw script never has to appear in the preview: the values and the
        # capability id are the contract.
        self.assertNotIn("script", preview["arguments"])

    def test_dry_run_does_not_require_confirmation_but_live_does(self) -> None:
        preview = browser_tools.browser_deploy_and_apply_featurescript({
            "dry_run": True, "capability": "custom.fillet",
        })
        self.assertTrue(preview["dryRun"])
        with self.assertRaisesRegex(ValueError, "confirm_mutation"):
            browser_tools.browser_deploy_and_apply_featurescript({
                "capability": "custom.fillet",
            })

    def test_the_registry_gained_no_tool_for_the_capabilities(self) -> None:
        from mcp_main.win.mcp import server

        names = [tool["name"] for tool in server.TOOLS]
        self.assertEqual(len(names), 108)
        self.assertEqual(len(capabilities.CAPABILITIES), 4)
        # The capability route lives on the existing deploy tool.
        deploy = next(tool for tool in server.TOOLS if tool["name"] == "browser_deploy_and_apply_featurescript")
        self.assertIn("capability", deploy["inputSchema"]["properties"])
        self.assertIn("values", deploy["inputSchema"]["properties"])
        # The two routes are expressed in the schema as well as enforced in the
        # handler, so a schema-aware client sees the same contract.
        self.assertEqual(deploy["inputSchema"]["anyOf"], [
            {"required": ["script", "feature_name"]},
            {"required": ["capability"]},
        ])
        self.assertNotIn("required", deploy["inputSchema"])


if __name__ == "__main__":
    unittest.main()
