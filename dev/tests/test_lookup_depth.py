#!/usr/bin/env python3
"""Gate for the lookup-depth cost model (`dev/tools/lookup_depth.py`).

The model answers a design question -- how many lookup layers and how many
entry points -- and a model that silently drifts is worse than no model, so what
is pinned here is the arithmetic and the measured invariants, not the numbers:

* every layer artifact is measured from a real code path and carries provenance;
* the first layer is a MAP, and it must stay the cheapest thing a caller can ask
  for (a category dump is where the model's whole budget would go);
* the two cost currencies are not mixed up: a surface is a wire size and an
  artifact is a model-facing size;
* the break-even arithmetic is monotone and recomputable;
* every tool the model recommends closing a chain with is actually registered,
  which is what makes the recommendation actionable rather than aspirational.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "temp" / "browser-common-site"))

from dev.tools import lookup_depth  # noqa: E402


class MeasureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layers = lookup_depth.measure_layers()

    def test_every_layer_artifact_is_measured_with_provenance(self):
        for key, layer in self.layers.items():
            with self.subTest(artifact=key):
                self.assertGreater(layer["chars"], 0)
                self.assertGreater(layer["wireChars"], 0)
                self.assertTrue(layer["provenance"])
                self.assertIn(layer["measured"], ("model", "wire"))

    def test_the_two_currencies_are_kept_apart(self):
        # A surface is what crosses the wire; an artifact is what the model reads
        # (pretty text) and therefore what rents in the tail. Measuring a surface
        # with the model-size helper would inflate it by ~30%.
        for key in ("surface:gateway", "surface:semantic", "surface:static"):
            self.assertEqual(self.layers[key]["measured"], "wire")
        for key in ("layer:catalog-index", "layer:docs-section"):
            self.assertEqual(self.layers[key]["measured"], "model")

    def test_discovery_stays_cheap(self):
        """The map is the way in, and no discovery answer may become a dump.

        An exact-entry read (`docs_section`, 176 tokens) is allowed to be cheaper
        than the map -- that is the whole point of the lookup-first order. What
        must hold is that DISCOVERY is cheap: the category map stays under 1,000
        tokens and no catalog answer exceeds a bounded page.
        """
        index = self.layers["layer:catalog-index"]["estimatedTokens"]
        self.assertLess(index, 1_000, "the category map is the cheap way in")
        for key, layer in self.layers.items():
            if key.startswith("layer:catalog-"):
                with self.subTest(artifact=key):
                    self.assertLess(
                        layer["estimatedTokens"], 3_000,
                        "a discovery answer must be a bounded map/page, not a dump",
                    )

    def test_the_biggest_artifact_is_flagged_for_slimming(self):
        # Whatever the model ends up measuring, the single most expensive artifact
        # must be visible in the slimming table rather than buried in a total.
        heaviest = max(
            (key for key in self.layers if key.startswith("layer:")),
            key=lambda key: self.layers[key]["estimatedTokens"],
        )
        self.assertIn(heaviest, lookup_depth.slim_potential(self.layers, n_steps=30))

    def test_the_advertised_surface_is_still_far_below_the_registry(self):
        gateway = self.layers["surface:gateway"]["estimatedTokens"]
        semantic = self.layers["surface:semantic"]["estimatedTokens"]
        static = self.layers["surface:static"]["estimatedTokens"]
        self.assertLess(gateway, semantic)
        self.assertLess(semantic, static)
        # 2.5x after the prescribed chains were completed on purpose; the point
        # of the bound is that compression still happens, not that it is extreme.
        self.assertGreater(semantic / gateway, 2)


class ModelTest(unittest.TestCase):
    def test_a_round_costs_the_whole_prefix_and_grows_with_it(self):
        cheap = lookup_depth.round_cost_tokens(
            prefix_tokens=1_000, step=1, growth_tokens=0, surface_tokens=100, artifact_tokens=10
        )
        dear = lookup_depth.round_cost_tokens(
            prefix_tokens=50_000, step=1, growth_tokens=0, surface_tokens=100, artifact_tokens=10
        )
        self.assertEqual(cheap, 1_110)
        self.assertEqual(dear, 50_110)
        self.assertGreater(dear, cheap)

    def test_artifact_rent_is_charged_for_every_remaining_step(self):
        once = lookup_depth.session_rent(
            10, prefix_tokens=0, growth_tokens=0, surface_tokens=0, artifacts=[(1, 100)]
        )
        late = lookup_depth.session_rent(
            10, prefix_tokens=0, growth_tokens=0, surface_tokens=0, artifacts=[(9, 100)]
        )
        self.assertEqual(once, 100 * 10)
        self.assertEqual(late, 100 * 2)
        self.assertGreater(once, late, "an early artifact rents longer than a late one")

    def test_the_budget_and_affordability_arithmetic_is_consistent(self):
        layers = lookup_depth.measure_layers()
        budget = lookup_depth.compression_budget(
            layers, narrower="surface:gateway", wider="surface:semantic"
        )
        self.assertEqual(
            budget["budgetTokensPerStep"],
            budget["widerSurfaceTokens"] - budget["narrowSurfaceTokens"],
        )
        self.assertEqual(lookup_depth.affordable_lookups(1_000, 250), 4.0)
        self.assertEqual(lookup_depth.affordable_lookups(1_000, 0), float("inf"))

    def test_an_entry_is_judged_by_rent_versus_the_round_it_removes(self):
        entries = lookup_depth.entry_analysis(
            n_steps=30, prefix_tokens=8_000, growth_tokens=600, surface_tokens=10_352
        )
        self.assertTrue(entries)
        for name, item in entries.items():
            with self.subTest(entry=name):
                self.assertGreater(item["schemaTokensPerStep"], 0)
                self.assertGreater(item["rentTokensOverSession"], 0)
                self.assertGreater(item["avoidedRoundTokens"], 0)
                self.assertEqual(
                    item["netTokensIfUsedOnce"],
                    item["avoidedRoundTokens"] - item["rentTokensOverSession"],
                )
                self.assertAlmostEqual(
                    item["breakEvenUseProbability"],
                    item["rentTokensOverSession"] / item["avoidedRoundTokens"],
                    places=2,
                )

    def test_widening_is_priced_in_single_name_lookups(self):
        layers = lookup_depth.measure_layers()
        widening = lookup_depth.widening_analysis(
            n_steps=30, prefix_tokens=8_000, growth_tokens=600, layers=layers
        )
        self.assertIn("surface:semantic", widening)
        semantic = widening["surface:semantic"]
        self.assertGreater(semantic["extraRentTokens"], 0)
        self.assertGreater(semantic["equivalentSingleNameLookups"], 1)
        # Widening to the complete registry must be the most expensive option.
        ratios = {key: item["equivalentSingleNameLookups"] for key, item in widening.items()}
        self.assertEqual(max(ratios, key=ratios.get), "surface:static")

    def test_the_bridge_layer_charges_one_round_and_widens_the_rest(self):
        policy = lookup_depth.bridge_policy(
            n_steps=30, prefix_tokens=8_000, growth_tokens=600, surface_tokens=15_866
        )
        policies = policy["policies"]
        # Expanding up front is the worst option when the first child call is not
        # immediate; collapsing without ever expanding is the cheapest session and
        # is only valid when no child tool is needed at all.
        self.assertGreater(policies["expanded from the start"],
                           policies["collapsed, expanded at step 2"])
        self.assertLess(policies["collapsed, never expanded"],
                        policies["collapsed, expanded at step 2"])
        self.assertEqual(policy["breakEvenExpandStep"], 2)
        # Later expansion saves more: the collapsed surface is cheaper for longer.
        curve = policy["collapseCurve"]
        self.assertLess(curve["expand at step 10"], curve["expand at step 2"])
        self.assertEqual(policy["doubleNameDoorPerHiddenName"], policy["roundTokens"])

    def test_slimming_only_flags_artifacts_above_the_threshold(self):
        layers = lookup_depth.measure_layers()
        slim = lookup_depth.slim_potential(layers, n_steps=30)
        self.assertTrue(slim)
        for key, item in slim.items():
            with self.subTest(artifact=key):
                self.assertGreater(item["tokens"], lookup_depth.SLIM_ARTIFACT_TOKENS)
                self.assertGreater(item["savingIfSlimmed"], 0)
        self.assertNotIn("layer:catalog-index", slim, "the cheap map never needs slimming")


class RecommendationTest(unittest.TestCase):
    def test_the_recorded_task_vocabulary_is_reported_with_its_gaps(self):
        result = lookup_depth.coverage()
        self.assertEqual(result["tasks"], len(lookup_depth.REAL_TASK_TOOLS))
        self.assertLessEqual(result["zeroRoundShare"], 1.0)
        # A coverage report that hides its gaps is not a measurement.
        self.assertEqual(
            len(result["zeroRoundTasks"]) + len(result["tasksNeedingALookup"]),
            result["tasks"],
        )

    def test_every_documented_chain_step_is_a_registered_tool(self):
        from mcp_main.win.mcp.server import TOOLS

        registered = {tool["name"] for tool in TOOLS}
        for name, chain in lookup_depth.DOCUMENTED_CHAINS:
            with self.subTest(chain=name):
                self.assertGreaterEqual(len(chain), 2)
                for step in chain:
                    self.assertIn(step, registered, f"{name}: {step} is not registered")

    def test_every_recommended_entry_exists_so_the_fix_is_actionable(self):
        from mcp_main.win.mcp.server import TOOLS

        registered = {tool["name"] for tool in TOOLS}
        for name in lookup_depth.CANDIDATE_ENTRIES:
            with self.subTest(entry=name):
                self.assertIn(name, registered)

    def test_the_report_is_self_consistent(self):
        result = lookup_depth.report(n_steps=20, prefix_tokens=4_000, growth_tokens=400)
        for section in (
            "surfaces", "layers", "budgetVsSemantic", "affordableLookupsInBudget",
            "noLookupSessionRentTokens", "documentedChains", "coverage", "entries",
            "widening", "slimPotential",
        ):
            with self.subTest(section=section):
                self.assertIn(section, result)
        self.assertEqual(result["session"]["steps"], 20)
        wider = result["noLookupSessionRentTokens"]["semantic"]
        narrower = result["noLookupSessionRentTokens"]["gateway"]
        self.assertGreater(wider, narrower, "a wider surface must rent more")


if __name__ == "__main__":
    os.environ.setdefault("ONSHAPE_MCP_TOOL_EXPOSURE", "gateway")
    unittest.main()
