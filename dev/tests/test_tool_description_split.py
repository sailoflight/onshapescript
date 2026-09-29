"""The description split: short on the wire, complete on demand.

This is the tripwire for the change that moves narrative out of ``tools/list``:
the advertised payload must carry every contract phrase the existing suite
asserts (those tests are unchanged and must keep passing against
``server.TOOLS``), while ``mcp_tool_catalog action=describe`` must still return
the complete original text for every tool.
"""

from __future__ import annotations

import unittest

from mcp_main.win.mcp import server
from mcp_main.win.mcp.tool_catalog import ToolCatalogIndex
from mcp_main.win.mcp.tool_descriptions import (
    REQUIRED_PHRASES,
    recorded_details,
    split_sentences,
    summarize_tool_description,
)


class DescriptionSplitTest(unittest.TestCase):
    def setUp(self):
        self.names = {tool["name"] for tool in server.TOOLS}
        self.payload = {tool["name"]: tool for tool in server.TOOLS}
        self.details = server.TOOL_DETAILS

    def describe(self, name, index=None):
        catalog = index or server.TOOL_CATALOG
        return catalog.describe({"name": name}, visible_names=self.names)["tool"]

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

    def test_the_visible_text_still_carries_every_asserted_phrase(self):
        for name, phrases in REQUIRED_PHRASES.items():
            self.assertIn(name, self.names)
            advertised = self.payload[name]["description"]
            for phrase in phrases:
                self.assertIn(phrase, advertised, f"{name}: {phrase!r}")

    def test_the_summary_rule_is_deterministic_and_only_shrinks(self):
        for name in sorted(self.names):
            original = self.details[name]
            first = summarize_tool_description(name, original)
            self.assertEqual(first, summarize_tool_description(name, original), name)
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
