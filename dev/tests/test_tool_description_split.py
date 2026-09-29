"""The description split: short on the wire, complete on demand.

This is the tripwire for the change that moves narrative out of ``tools/list``:
the advertised payload must carry every contract phrase the existing suite
asserts (those tests are unchanged and must keep passing against
``server.TOOLS``), no routing token may leave the visible text, and
``mcp_tool_catalog action=describe`` must still return the complete original
text for every tool.
"""

from __future__ import annotations

import re
import unittest

from mcp_main.win.mcp import server
from mcp_main.win.mcp.tool_catalog import ToolCatalogIndex
from mcp_main.win.mcp.tool_descriptions import (
    EMPHASIS_NEGATIONS,
    REQUIRED_PHRASES,
    recorded_details,
    routing_contexts,
    split_sentences,
    summarize_tool_description,
)

_BACKTICKED = re.compile(r"`[^`]+`")
_ACTION_VALUE = re.compile(r"action\s*=\s*['\"][^'\"]+['\"]")
_CONFIG_KNOB = re.compile(r"\b(?:MCP|ONSHAPE)_[A-Z][A-Z_]*\b")
_EMPHASIS = re.compile(r"\b(?:" + "|".join(EMPHASIS_NEGATIONS) + r")\b")


class DescriptionSplitTest(unittest.TestCase):
    def setUp(self):
        self.names = {tool["name"] for tool in server.TOOLS}
        self.payload = {tool["name"]: tool for tool in server.TOOLS}
        self.details = server.TOOL_DETAILS
        self.contexts = routing_contexts(server.TOOLS)

    def describe(self, name, index=None):
        catalog = index or server.TOOL_CATALOG
        return catalog.describe({"name": name}, visible_names=self.names)["tool"]

    def routing_tokens(self, name, text):
        """Every token rule 5 protects, recomputed here from the registry."""
        tokens = set(_BACKTICKED.findall(text))
        tokens |= set(_ACTION_VALUE.findall(text))
        tokens |= set(_CONFIG_KNOB.findall(text))
        tokens |= set(_EMPHASIS.findall(text))
        parameters = self.contexts[name].parameters
        for parameter in parameters:
            if re.search(r"\b" + re.escape(parameter) + r"\b", text):
                tokens.add(parameter)
        for peer in self.names:
            if peer != name and re.search(r"\b" + re.escape(peer) + r"\b", text):
                tokens.add(peer)
        return tokens

    def test_every_tool_keeps_the_complete_original_text_reachable(self):
        self.assertEqual(set(self.details), self.names)
        self.assertEqual(dict(recorded_details()), self.details)
        for name in sorted(self.names):
            described = self.describe(name)
            self.assertEqual(described["description"], self.details[name], name)
            self.assertGreaterEqual(len(described["description"]), len(self.payload[name]["description"]), name)
            # The advertised text is a subset of whole sentences of the original,
            # so every sentence it keeps must appear verbatim in describe().
            for sentence in split_sentences(self.payload[name]["description"]):
                self.assertIn(sentence, described["description"], name)

    def test_no_routing_token_leaves_the_advertised_text(self):
        """Rule 5 is the load-bearing invariant; assert it against the registry."""
        offenders = []
        for name in sorted(self.names):
            before = self.routing_tokens(name, self.details[name])
            after = self.routing_tokens(name, self.payload[name]["description"])
            missing = sorted(before - after)
            if missing:
                offenders.append(f"{name}: {missing}")
        self.assertEqual(offenders, [])

    def test_the_routing_context_is_derived_from_the_registry_not_a_list(self):
        self.assertEqual(set(self.contexts), self.names)
        for tool in server.TOOLS:
            name = tool["name"]
            context = self.contexts[name]
            properties = (tool.get("inputSchema") or {}).get("properties") or {}
            self.assertEqual(list(context.parameters), [str(key) for key in properties], name)
            self.assertEqual(set(context.tool_names), self.names, name)

    def test_a_routing_context_matches_parameters_peers_actions_and_knobs(self):
        context = self.contexts["onshape_update_feature_list"]
        self.assertIn("dry_run", context.parameters)
        self.assertTrue(context.carries_routing("Use dry_run=true before anything is sent."))
        self.assertTrue(context.carries_routing("Call onshape_geometry_status afterwards."))
        self.assertTrue(context.carries_routing("Run it with action='reload'."))
        self.assertTrue(context.carries_routing("Set MCP_TOOL_EXPOSURE=dynamic."))
        self.assertTrue(context.carries_routing("The result carries `applyState`."))
        self.assertFalse(context.carries_routing("Measured live 2026-09-21 during a long session."))
        # The self-name is never a peer reference.
        self.assertFalse(context.carries_routing("onshape_update_feature_list"))
        # A context is a pure value: same registry, same verdicts.
        again = routing_contexts(server.TOOLS)["onshape_update_feature_list"]
        for sentence in ("Use dry_run=true.", "Measured live 2026-09-21.", "The result carries `applyState`."):
            self.assertEqual(context.carries_routing(sentence), again.carries_routing(sentence))

    def test_the_visible_text_still_carries_every_asserted_phrase(self):
        for name, phrases in REQUIRED_PHRASES.items():
            self.assertIn(name, self.names)
            advertised = self.payload[name]["description"]
            for phrase in phrases:
                self.assertIn(phrase, advertised, f"{name}: {phrase!r}")

    def test_the_summary_rule_is_deterministic_and_only_shrinks(self):
        for name in sorted(self.names):
            original = self.details[name]
            context = self.contexts[name]
            first = summarize_tool_description(name, original, context)
            self.assertEqual(first, summarize_tool_description(name, original, context), name)
            self.assertEqual(first, self.payload[name]["description"], name)
            self.assertLessEqual(len(first), len(original), name)

    def test_the_fingerprint_and_describe_do_not_depend_on_the_construction_site(self):
        rebuilt = ToolCatalogIndex(server.TOOLS)
        self.assertEqual(rebuilt.fingerprint, server.TOOL_CATALOG.fingerprint)
        described = self.describe("browser_session", index=rebuilt)
        self.assertEqual(described["description"], self.details["browser_session"])
        self.assertEqual(len(described["description"]), 4782)

    def test_authority_is_unchanged_by_the_text_split(self):
        for name in sorted(self.names):
            described = self.describe(name)
            self.assertFalse(described["authorityChanged"], name)
            self.assertTrue(described["conventionOnly"], name)
            self.assertTrue(described["knownNameCallAvailable"], name)
        status = server.TOOL_CATALOG.status(visible_names=self.names)
        self.assertFalse(status["authorityChanged"])
        self.assertFalse(status["concurrencyPolicy"]["authorityChanged"])


if __name__ == "__main__":
    unittest.main()
