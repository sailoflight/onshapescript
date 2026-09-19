"""Offline measurement of the capability retrieval route (plan H3/H4 gate).

The route under test is the one a normal caller takes:

    browser_discover_tools(query="fillet")   ->  a bounded capability card
    browser_deploy_and_apply_featurescript(capability="custom.fillet", values={...})

The alternative, without the card layer, is to search the FeatureScript
reference, read a function entry, translate it into a feature definition, then
check the symbols. This module measures both and asserts the card route is
cheaper, needs no implementation source, and expands no dependencies.

Honest scope: this is a *character* measurement over the same indexes the
server reads. It does not prove the generated feature computes geometry on a
real document -- that stays with the live half of P2.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from mcp_main.win.mcp import browser_tools
from onshape_browser_mode import capabilities
from onshape_docs.query import fs_reference, project_docs

# The three queries the plan names: two well-known features and one long tail.
_QUERIES = {
    "extrude": "extrude this face into a boss",
    "fillet": "round the edges of this part",
    "hole": "drill a hole at this vertex",
    "long-tail": "spiral ridge thread",
}


def _size(payload) -> int:
    return len(json.dumps(payload, ensure_ascii=False, default=str))


class SearchBehaviourTest(unittest.TestCase):
    def test_search_is_bounded(self) -> None:
        for limit in (1, 3, 5):
            with self.subTest(limit=limit):
                self.assertLessEqual(len(capabilities.search("round the edges", limit=limit)), limit)

    def test_limit_is_refused_outside_one_through_five(self) -> None:
        for limit in (0, 6, -1, True, 1.5, "3"):
            with self.subTest(limit=limit):
                with self.assertRaises(capabilities.CapabilityError):
                    capabilities.search("fillet", limit=limit)

    def test_empty_query_matches_nothing(self) -> None:
        self.assertEqual(capabilities.search(""), [])
        self.assertEqual(capabilities.search("the of and"), [])
        self.assertEqual(capabilities.search(None), [])

    def test_one_incidental_prose_word_is_not_a_match(self) -> None:
        """'feature' appears in every card's notes; it must not match all of them."""
        self.assertEqual(capabilities.search("feature"), [])
        self.assertEqual(capabilities.search("zzzz-no-such-feature"), [])

    def test_exact_identity_beats_a_prose_mention(self) -> None:
        matches = capabilities.search("fillet")
        self.assertTrue(matches)
        self.assertEqual(matches[0]["card"]["id"], "custom.fillet")
        self.assertIn("fillet", matches[0]["matchedOn"])

    def test_aliases_and_chinese_names_resolve(self) -> None:
        for query, expected in (
            ("cut", "custom.extrude"),
            ("圆角", "custom.fillet"),
            ("螺纹", "custom.spiral_ridge"),
            ("pocket", "custom.extrude"),
        ):
            with self.subTest(query=query):
                self.assertEqual(capabilities.search(query)[0]["card"]["id"], expected)

    def test_a_prose_query_does_not_bury_the_feature(self) -> None:
        for name, query in _QUERIES.items():
            with self.subTest(query=name):
                matches = capabilities.search(query)
                self.assertTrue(matches, f"{query!r} matched no capability")
                self.assertEqual(matches[0]["card"]["id"], {
                    "extrude": "custom.extrude",
                    "fillet": "custom.fillet",
                    "hole": "custom.hole",
                    "long-tail": "custom.spiral_ridge",
                }[name])

    def test_scores_are_ordered_and_inspectable(self) -> None:
        matches = capabilities.search("extrude cut")
        scores = [match["score"] for match in matches]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for match in matches:
            self.assertEqual(set(match), {"card", "score", "matchedOn"})
            self.assertGreater(match["score"], 0)
            self.assertTrue(match["matchedOn"])


class RetrievalCostTest(unittest.TestCase):
    """The card route must be cheaper than the reference-reading route."""

    def test_card_route_is_cheaper_than_the_reference_route(self) -> None:
        for name, query in _QUERIES.items():
            with self.subTest(query=name):
                card_route = _size(capabilities.search(query, limit=1))
                hits = fs_reference.search(query, limit=5)
                reference_route = _size(hits)
                # The reference route is not finished at the search step: the
                # caller still has to read the body that defines the contract.
                for hit in hits[:1]:
                    if hit["kind"] != "function":
                        continue
                    try:
                        entry = fs_reference.get_function(hit["name"], module=hit.get("module") or None)
                    except ValueError:
                        continue
                    reference_route += _size(entry)
                self.assertLess(
                    card_route, reference_route,
                    f"{name}: card route {card_route} chars is not cheaper than {reference_route}",
                )

    def test_a_chinese_query_resolves_a_card_the_reference_cannot_find(self) -> None:
        """The card layer carries the owner's own vocabulary; the FS index does not."""
        self.assertEqual(capabilities.search("打孔", limit=1)[0]["card"]["id"], "custom.hole")
        self.assertEqual(fs_reference.search("打孔", limit=5), [])

    def test_the_reference_search_does_not_resolve_a_prose_query(self) -> None:
        """The card layer earns its keep on intent, not just on size.

        For "round the edges of this part" the FeatureScript search ranks query
        helpers and filters -- a caller reading the top hit still has not found
        a fillet, let alone its bounded contract.
        """
        hits = fs_reference.search("round the edges of this part", limit=5)
        self.assertTrue(hits)
        self.assertNotIn("fillet", " ".join(hit["name"].lower() for hit in hits))
        card = capabilities.search("round the edges of this part", limit=1)[0]["card"]
        self.assertEqual(card["id"], "custom.fillet")

    def test_card_route_needs_no_implementation_source(self) -> None:
        for name, query in _QUERIES.items():
            with self.subTest(query=name):
                payload = json.dumps(capabilities.search(query, limit=1), ensure_ascii=False)
                for token in ("import(path", "precondition", "definition.", "annotation {",
                              "opFillet(", "opExtrude(", "opBoolean(", "\n"):
                    self.assertNotIn(token, payload)

    def test_card_route_expands_no_dependencies(self) -> None:
        """One call, one card: no module graph, no library walk, no FS docs page."""
        with mock.patch.object(
            fs_reference, "get_function", side_effect=AssertionError("expanded a function entry"),
        ), mock.patch.object(
            fs_reference, "library_source", side_effect=AssertionError("read a library source"),
        ), mock.patch.object(
            fs_reference, "guide_section", side_effect=AssertionError("read a guide page"),
        ):
            matches = capabilities.search("fillet")
        self.assertEqual(matches[0]["card"]["id"], "custom.fillet")

    def test_a_capability_call_is_one_tool_and_one_card(self) -> None:
        """The whole call shape: discover once, then deploy with values only."""
        card = capabilities.search("fillet", limit=1)[0]["card"]
        plan = capabilities.plan("custom.fillet", {"radius": 2})
        self.assertEqual(plan["capability"]["id"], "custom.fillet")
        self.assertIn("source", plan)
        self.assertLess(_size(card), len(plan["source"]))

    def test_the_audit_counts_capabilities_as_contracts_not_tools(self) -> None:
        """More capabilities must not become more tools; the audit records the split."""
        from mcp_main.win.mcp import server

        card_ids = {card["id"] for card in capabilities.cards()}
        self.assertGreaterEqual(len(card_ids), 3)
        self.assertFalse(card_ids & {str(tool["name"]) for tool in server.TOOLS})


class DiscoveryWiringTest(unittest.TestCase):
    """browser_discover_tools is the discovery entry point and carries the cards."""

    def test_a_feature_query_returns_cards_next_to_the_tool_candidates(self) -> None:
        result = browser_tools.browser_discover_tools({"query": "extrude"})
        self.assertIn("capabilities", result)
        self.assertEqual(result["capabilities"][0]["card"]["id"], "custom.extrude")
        self.assertIn("candidates", result)

    def test_a_card_carries_the_call_that_uses_it(self) -> None:
        """The gateway route in the same result is `browser_invoke_discovered`,
        which is wrong for a capability: a capability is an argument to the deploy
        tool, so the card must say so itself."""
        result = browser_tools.browser_discover_tools({"query": "fillet"})
        match = result["capabilities"][0]
        self.assertEqual(match["invocation"]["tool"], "browser_deploy_and_apply_featurescript")
        self.assertEqual(
            match["invocation"]["tool"], result["capabilityInvocationTool"],
        )
        self.assertEqual(match["invocation"]["arguments"]["capability"], "custom.fillet")
        defaults = match["invocation"]["arguments"]["values"]
        self.assertEqual(
            defaults,
            {parameter["name"]: parameter["default"] for parameter in match["card"]["parameters"]},
        )
        # The start values are exactly the card's own contract: no query, no code.
        self.assertNotIn("entities", defaults)
        self.assertNotIn("face", defaults)
        self.assertNotIn("vertex", defaults)

    def test_the_suggested_call_validates_as_written(self) -> None:
        """A suggestion that the handler would reject is worse than none."""
        from onshape_browser_mode import capabilities

        result = browser_tools.browser_discover_tools({"query": "hole"})
        call = result["capabilities"][0]["invocation"]["arguments"]
        plan = capabilities.plan(call["capability"], call["values"])
        self.assertEqual(plan["capability"]["id"], "custom.hole")
        self.assertTrue(plan["source"])

    def test_a_query_without_a_capability_match_omits_the_key(self) -> None:
        result = browser_tools.browser_discover_tools({"query": "zzzz-no-such-feature"})
        self.assertNotIn("capabilities", result)

    def test_no_query_leaves_the_tool_catalog_unchanged(self) -> None:
        result = browser_tools.browser_discover_tools({})
        self.assertNotIn("capabilities", result)
        self.assertEqual(result["candidateCount"], len(result["candidates"]))

    def test_discovery_still_ranks_tools(self) -> None:
        result = browser_tools.browser_discover_tools({"query": "build part"})
        self.assertTrue(any("build_part" in candidate["name"] for candidate in result["candidates"]))

    def test_a_default_hidden_tool_stays_hidden(self) -> None:
        """Appending cards must not widen the default six-level exposure."""
        result = browser_tools.browser_discover_tools({"query": "screenshot"})
        self.assertEqual(result["candidates"], [])


class DocsRouteComparisonTest(unittest.TestCase):
    """Sanity: the docs route exists and is the more expensive one."""

    def test_project_docs_search_is_not_a_capability_contract(self) -> None:
        result = project_docs.search("fillet", limit=5)
        payload = json.dumps(result, ensure_ascii=False)
        self.assertNotIn('"parameters"', payload)


if __name__ == "__main__":
    unittest.main()
