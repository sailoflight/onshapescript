"""Gate for `docs/architecture/TOOL_SURFACE_AUDIT.md` (roadmap P5).

The audit is authored judgment, so it cannot be generated and checked against
itself. What CAN be checked is that it is complete and self-consistent:

* every registered tool has exactly one verdict, and no verdict names a tool that
  is not registered;
* every verdict is one of the five, every `Merge` names a different registered
  tool as its survivor, and every other verdict leaves the column empty;
* every row carries a real reason, and the summary counts match the table;
* the verdict that makes a claim about recorded metadata -- `Internal-only` -- is
  compared against the semantics records, and the known gaps are required to be
  acknowledged in the follow-up section rather than left implicit.

An audit that silently drops a tool fails here, which is the whole point: the
hidden and deprecated entries are exactly the ones a completeness check must
cover.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from mcp_main.win.mcp import server
from onshape_browser_mode.semantics import TOOL_SEMANTICS

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs" / "architecture" / "TOOL_SURFACE_AUDIT.md"
VERDICTS = ("Keep", "Capability", "Merge", "Internal-only", "Remove")
MIN_REASON_LENGTH = 40

_ROW = re.compile(
    r"^\| `(?P<name>[a-z_0-9]+)` \| `(?P<verdict>[A-Za-z-]+)` \| "
    r"(?:`(?P<target>[a-z_0-9]+)`|(?P<empty>-)) \| (?P<reason>.+) \|$",
    re.MULTILINE,
)
_SUMMARY_ROW = re.compile(
    r"^\| `(?P<verdict>[A-Za-z-]+)` \| (?P<count>\d+) \|$", re.MULTILINE
)
_TOTAL = re.compile(r"^\| \*\*total\*\* \| \*\*(?P<count>\d+)\*\* \|$", re.MULTILINE)


def _document() -> str:
    return AUDIT.read_text(encoding="utf-8")


def _rows() -> list[dict[str, str]]:
    return [match.groupdict() for match in _ROW.finditer(_document())]


def _follow_ups() -> str:
    text = _document()
    marker = "## What this audit changes next"
    assert marker in text, "the follow-up section was renamed or removed"
    return text.split(marker, 1)[1]


class AuditDocumentTest(unittest.TestCase):
    def test_follow_up_section_exists_and_is_not_a_stub(self) -> None:
        self.assertGreater(len(_follow_ups().strip()), 400)

    def test_no_tool_is_dropped_or_invented(self) -> None:
        registered = {tool["name"] for tool in server.TOOLS}
        rows = _rows()
        names = [row["name"] for row in rows]
        self.assertEqual(len(names), len(set(names)), "a tool is listed more than once")
        self.assertEqual(set(names) - registered, set(), "verdict names an unregistered tool")
        self.assertEqual(registered - set(names), set(), "a registered tool is unclassified")

    def test_every_verdict_is_known_and_every_reason_is_real(self) -> None:
        for row in _rows():
            with self.subTest(tool=row["name"]):
                self.assertIn(row["verdict"], VERDICTS)
                reason = row["reason"].strip()
                self.assertGreaterEqual(
                    len(reason), MIN_REASON_LENGTH,
                    "the reason must say why, not restate the verdict",
                )
                self.assertNotIn("TODO", reason)
                self.assertNotIn("???", reason)

    def test_merge_targets_are_registered_and_everything_else_has_none(self) -> None:
        registered = {tool["name"] for tool in server.TOOLS}
        targets: dict[str, str] = {}
        for row in _rows():
            if row["verdict"] == "Merge":
                with self.subTest(tool=row["name"]):
                    self.assertIsNone(row["empty"])
                    self.assertIn(row["target"], registered)
                    self.assertNotEqual(row["target"], row["name"])
                    targets[row["name"]] = row["target"]
            else:
                with self.subTest(tool=row["name"]):
                    self.assertIsNone(row["target"])
                    self.assertEqual(row["empty"], "-")
        # The follow-up sentence lists exactly the merges the table declares.
        follow_ups = _follow_ups()
        for name, target in targets.items():
            self.assertIn(f"`{name}`", follow_ups)
            self.assertIn(f"`{target}`", follow_ups)
        # All eight merges were executed on 2026-09-19 and became
        # `Internal-only`; the follow-up keeps naming them so the change stays
        # traceable from this page.
        self.assertEqual(targets, {})
        for name in (
            "fs_list_modules",
            "browser_reconnect",
            "browser_reload",
            "browser_invoke_discovered",
            "browser_drawing_insert_views",
            "browser_add_drawing_dimension",
            "browser_geometry_status",
            "browser_configure_geometry_backend",
        ):
            with self.subTest(tool=name):
                self.assertIn(f"`{name}`", follow_ups)
                self.assertEqual(
                    next(item["verdict"] for item in _rows() if item["name"] == name),
                    "Internal-only",
                )

    def test_summary_counts_match_the_table(self) -> None:
        counts = {verdict: 0 for verdict in VERDICTS}
        for row in _rows():
            counts[row["verdict"]] += 1
        summarised = {
            match.group("verdict"): int(match.group("count"))
            for match in _SUMMARY_ROW.finditer(_document())
        }
        self.assertEqual(summarised, counts)
        total = _TOTAL.search(_document())
        self.assertIsNotNone(total)
        self.assertEqual(int(total.group("count")), len(server.TOOLS))
        self.assertEqual(sum(counts.values()), len(server.TOOLS))

    def test_no_remove_verdicts_remain_and_hidden_tools_are_internal_only(self) -> None:
        """A verdict that makes a claim about recorded metadata must be backed by
        it, not by taste. After the 2026-09-19 archive no row is `Remove`: the two
        stubs that genuinely did not do their job are gone, and the two tools that
        are merely high-risk are `Internal-only`, which is what their records
        already said."""
        rows = _rows()
        removed = [row["name"] for row in rows if row["verdict"] == "Remove"]
        self.assertEqual(removed, [], "`Remove` is resolved; see the archive record")
        for row in rows:
            if row["verdict"] == "Internal-only":
                continue
            with self.subTest(tool=row["name"]):
                record = TOOL_SEMANTICS.get(row["name"])
                if record is None:
                    continue
                self.assertTrue(
                    record.default_exposure,
                    f"{row['name']} is default-hidden, so only `Internal-only` is honest",
                )
        for name in ("browser_delete_tab", "browser_draw_part"):
            with self.subTest(tool=name):
                row = next(item for item in rows if item["name"] == name)
                self.assertEqual(row["verdict"], "Internal-only")
        # The archived names must still be traceable from this page.
        for name in ("browser_print_orientation_check", "browser_print_optimize_part"):
            with self.subTest(tool=name):
                self.assertIn(f"`{name}`", _follow_ups())

    def test_internal_only_claim_is_measured_not_assumed(self) -> None:
        """The doc says `Internal-only` tools are not ordinary model choices and
        stay reachable by exact name. That is measurable: every recorded one must
        have `default_exposure=False`, be absent from the ordinary list, and still
        come back from an explicit level query through the real selection path."""
        from mcp_main.win.mcp import server
        from mcp_main.win.mcp.tool_views import (
            ABSORBED_COMPATIBILITY_TOOLS,
            select_view_tools,
        )
        from onshape_browser_mode.semantics import select_tool_names

        internal = [row["name"] for row in _rows() if row["verdict"] == "Internal-only"]
        recorded = {name: TOOL_SEMANTICS[name] for name in internal if name in TOOL_SEMANTICS}
        self.assertGreaterEqual(len(recorded), 20)
        exposed = sorted(name for name, record in recorded.items() if record.default_exposure)
        self.assertEqual(
            exposed, [],
            "every Internal-only tool must be default-hidden; "
            "an exception belongs in the follow-up section, not in the ordinary list",
        )
        # The claim is about the real selection path, not just the metadata flag.
        selected = set(select_tool_names(sorted(recorded)))
        self.assertEqual(selected & set(recorded), set())
        # An absorbed compatibility wrapper outside the browser namespace has no
        # semantics record and no level; its documented route is the complete
        # registry view, so it must be listed there and nowhere ordinary.
        every_level = ("L1", "L2", "L3", "L4", "L5", "L6")
        revealed = {
            tool["name"]
            for tool in select_view_tools(
                server.TOOLS, profile="browser", semantic_levels=every_level
            )
        }
        complete = {
            tool["name"] for tool in select_view_tools(server.TOOLS, profile="all", semantic_levels=None)
        }
        for name in sorted(recorded):
            with self.subTest(tool=name):
                self.assertIn(name, revealed, f"{name} is not reachable by an explicit level query")
        for name in sorted(internal):
            if name in recorded:
                continue
            with self.subTest(tool=name):
                self.assertIn(name, complete, f"{name} is not reachable in the complete view")
                if name in ABSORBED_COMPATIBILITY_TOOLS:
                    for profile in ("default", "rest", "featurescript", "documentation", "geometry"):
                        self.assertNotIn(
                            name,
                            {tool["name"] for tool in select_view_tools(server.TOOLS, profile=profile, semantic_levels=None)},
                            f"{name} is an absorbed wrapper and must not be advertised",
                        )

    def test_capability_verdicts_are_whole_jobs(self) -> None:
        """A `Capability` verdict must describe a job, not a primitive: an L1-L3
        primitive cannot be one, an L4 transaction may be one when the reason says
        so (a fillet is one UI transaction and still a whole-feature job), and the
        REST-side jobs without a semantics record must say "job"/"capability"."""
        for row in _rows():
            if row["verdict"] != "Capability":
                continue
            with self.subTest(tool=row["name"]):
                record = TOOL_SEMANTICS.get(row["name"])
                if record is not None and record.level is not None:
                    self.assertIn(
                        record.level, {"L4", "L5", "L6"},
                        f"{row['name']} is level {record.level}, a primitive cannot be a capability",
                    )
                self.assertIn(
                    "capability",
                    row["reason"].lower(),
                    f"{row['name']} must name the capability layer it belongs to",
                )


if __name__ == "__main__":
    unittest.main()
