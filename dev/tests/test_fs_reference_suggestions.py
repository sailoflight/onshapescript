#!/usr/bin/env python3
"""Near-miss suggestions from the FeatureScript reference lookup (issue #9).

Motivation, measured: users naturally guess ``opCylinder`` / ``opBox``, but the
FeatureScript primitives are ``fCylinder`` / ``fCuboid`` / ``fCone``. Before this,
a miss said nothing about the name's neighbourhood, so the caller spent a whole
extra ``fs_search`` round trip. The fix is a ``ReferenceMiss`` (still a
``ValueError``) carrying structured ``suggestions`` and a copy-pasteable
``nextCall``.

Fully offline: the vendored index is the fixture. No network, no browser, no
Onshape REST call.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_docs.query import fs_reference  # noqa: E402


class ReferenceMissTest(unittest.TestCase):
    """A miss raises a ValueError subclass that also carries the advice."""

    def test_unknown_function_raises_reference_miss_with_advice(self) -> None:
        with self.assertRaises(ValueError) as caught:
            fs_reference.get_function("opCylinder")
        self.assertIsInstance(caught.exception, fs_reference.ReferenceMiss)
        message = str(caught.exception)
        self.assertIn("No function named 'opCylinder'", message)
        self.assertIn("fCylinder", message)
        self.assertIn('fs_search(query="cylinder")', message)
        self.assertRegex(
            message,
            r"^No function named 'opCylinder'\. Did you mean '.+'\?",
        )

    def test_the_exception_carries_the_structured_payload(self) -> None:
        with self.assertRaises(fs_reference.ReferenceMiss) as caught:
            fs_reference.get_function("opCylinder")
        error = caught.exception
        self.assertEqual(error.name, "opCylinder")
        self.assertEqual(error.kind, "function")
        self.assertIsNone(error.module)
        self.assertTrue(error.suggestions)
        for suggestion in error.suggestions:
            self.assertEqual(set(suggestion), {"name", "module", "kind"})
        self.assertIn("fCylinder", [item["name"] for item in error.suggestions])
        self.assertEqual(error.nextCall, 'fs_search(query="cylinder")')
        data = error.to_dict()
        self.assertEqual(data["suggestions"], error.suggestions)
        self.assertEqual(data["nextCall"], error.nextCall)

    def test_an_explicit_module_is_echoed_in_the_message(self) -> None:
        with self.assertRaises(fs_reference.ReferenceMiss) as caught:
            fs_reference.get_function("opCylinder", module="nope.fs")
        self.assertIn("in module 'nope.fs'", str(caught.exception))
        self.assertEqual(caught.exception.module, "nope.fs")

    def test_suggestions_are_capped_at_three(self) -> None:
        # `Cylinder` has many near/containing names in the corpus, so the cap is
        # what bounds the answer; a query that naturally overshoots is the point.
        suggestions = fs_reference.suggest_entries("Cylinder", kinds=("function",))
        self.assertLessEqual(len(suggestions), fs_reference.SUGGESTION_LIMIT)
        self.assertEqual(len(suggestions), 3)

    def test_suggestions_have_no_duplicate_names(self) -> None:
        for query in ("opCylinder", "opBox", "Querry"):
            with self.subTest(query=query):
                suggestions = fs_reference.suggest_entries(query)
                folded = [item["name"].casefold() for item in suggestions]
                self.assertEqual(len(folded), len(set(folded)), suggestions)

    def test_a_wild_guess_stays_quiet(self) -> None:
        """Below the documented cutoff nothing is offered, but the next call is."""
        with self.assertRaises(fs_reference.ReferenceMiss) as caught:
            fs_reference.get_function("zzzqqqxyz")
        self.assertEqual(caught.exception.suggestions, [])
        self.assertIn('fs_search(query="zzzqqqxyz")', str(caught.exception))
        self.assertNotIn("Did you mean", str(caught.exception))

    def test_type_miss_suggests_a_near_type(self) -> None:
        with self.assertRaises(ValueError) as caught:
            fs_reference.get_type("BoundingTyp")
        error = caught.exception
        self.assertIsInstance(error, fs_reference.ReferenceMiss)
        self.assertIn("No type named 'BoundingTyp'", str(error))
        self.assertIn("BoundingType", str(error))
        self.assertIn("BoundingType", [item["name"] for item in error.suggestions])
        self.assertIn("fs_search(query=", error.nextCall)

    def test_a_cross_module_clash_lists_candidate_names(self) -> None:
        # `ceil` is a genuine clash in the vendored index (math.fs, units.fs).
        with self.assertRaises(fs_reference.ReferenceMiss) as caught:
            fs_reference.get_function("ceil")
        message = str(caught.exception)
        self.assertIn("exists in 2 modules", message)
        self.assertIn("Candidates:", message)
        self.assertIn("ceil (math.fs)", message)
        self.assertIn("ceil (units.fs)", message)
        self.assertTrue(caught.exception.nextCall.startswith("fs_get_function("))


class SuccessShapeTest(unittest.TestCase):
    """A hit must keep exactly the shape it had before the suggestion work."""

    def test_single_function_shape_is_unchanged(self) -> None:
        entry = fs_reference.get_function("opExtrude")
        self.assertEqual(
            set(entry),
            {
                "kind", "name", "module", "category", "signature",
                "returnType", "parameters", "description", "anchor",
            },
        )
        self.assertEqual(entry["name"], "opExtrude")
        self.assertEqual(entry["module"], "geomOperations.fs")

    def test_overloaded_function_aggregation_is_unchanged(self) -> None:
        # `qEverything` is one of the 115 genuinely overloaded names.
        entry = fs_reference.get_function("qEverything")
        self.assertIn("overloadCount", entry)
        self.assertIn("overloads", entry)
        self.assertIn("note", entry)
        self.assertEqual(entry["overloadCount"], len(entry["overloads"]))

    def test_search_keeps_its_public_shape_and_does_not_raise(self) -> None:
        """`search` returns a list, so it has no dict key to add.

        The miss advice lives on `get_function`/`get_type` only; the shape of
        `search` (and therefore of the `fs_search` MCP result) is untouched.
        """
        empty = fs_reference.search("zzzqqqxyz")
        self.assertEqual(empty, [])
        self.assertIsInstance(empty, list)
        hits = fs_reference.search("cylinder", limit=3)
        self.assertIsInstance(hits, list)
        for hit in hits:
            self.assertEqual(
                set(hit),
                {"kind", "name", "module", "category", "signature", "score", "snippet"},
            )


if __name__ == "__main__":
    unittest.main()
