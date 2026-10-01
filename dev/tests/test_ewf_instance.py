#!/usr/bin/env python3
"""Offline guards for the EWF project instance in ``ewf/``.

``/home/lijq/code/ewf/docs/project-onboarding.md`` §6 lists five project-side
self-checks, all cheap and all derived from real rework. This file turns the
machine-checkable ones into tests instead of prose:

* §6-5 the README version line is a projection of ``instance.yaml``'s ``spec_version``;
* §6-1 every ``OQ-\\d{3}`` named in the README is declared in ``instance.open_questions``;
* §6-4 the README narrative and the ``FEEDBACK.md`` queue cover the same ``*-FB-NN`` ids;
* §6-2 ``execution_view_note``'s node count matches the actual ``execution.nodes``.

Plus two structural guards for decisions recorded in the README:

* the ``ewf/`` directory holds exactly the three deliverables and no code
  (onboarding §1), so the generator lives in ``dev/tools/``;
* the instance uses no private ``x-*`` extension keys (README §8).

The strongest guard is the generator's own ``--check``: it re-derives every
reading from the published archive, the release spec module and the local
verification record, and fails if ``instance.yaml`` is stale or if the source
data stopped being self-consistent. It is skipped when this machine has no
release data.

The two external EWF validators are skipped when their (read-only) repositories
are absent, and the consumer tool is additionally skipped while the EWF working
tree carries two spec versions at once -- that is a transient state of a
neighbouring repository and must not turn this project's suite red
(see ``ewf/FEEDBACK.md`` ``onshapescript-FB-13``).

No network, no live Onshape request, no writes.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EWF_DIR = ROOT / "ewf"
INSTANCE = EWF_DIR / "instance.yaml"
README = EWF_DIR / "README.md"
FEEDBACK = EWF_DIR / "FEEDBACK.md"
GENERATOR = ROOT / "dev/tools/build_ewf_instance.py"

#: Local build outputs; not part of the repository, so the freshness guard is optional.
RELEASES_DIR = Path("/home/lijq/code/onshapescript-releases")
ARCHIVE = RELEASES_DIR / "onshapescript-mcp-1.3.0-6ceacfb.zip"

#: Read-only neighbouring repositories (the two independent EWF implementations).
EWF_REPO = Path("/home/lijq/code/ewf")
EWF_TOOLS_REPO = Path("/home/lijq/code/ewf-tools")

#: The queue header is fixed word-for-word by the onboarding protocol §3.
QUEUE_COLUMNS = ("id", "类型", "事实（含原始证据）", "建议去向", "状态")

#: The three deliverables that may live in ``<project>/ewf/``.
EWF_DELIVERABLES = ["FEEDBACK.md", "README.md", "instance.yaml"]

_SEPARATOR = re.compile(r":?-+:?$")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _cells(line: str) -> tuple[str, ...] | None:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    return tuple(cell.strip() for cell in stripped.strip("|").split("|"))


def _queue_rows(text: str) -> list[dict]:
    """The one table recognised by its verbatim header, per protocol §3."""
    lines = text.splitlines()
    start = None
    for number, line in enumerate(lines):
        cells = _cells(line)
        if cells == QUEUE_COLUMNS:
            start = number
            break
    if start is None:
        raise AssertionError("FEEDBACK.md has no queue table with the verbatim header")
    rows: list[dict] = []
    for line in lines[start + 1:]:
        cells = _cells(line)
        if cells is None:
            break
        if all(_SEPARATOR.fullmatch(cell) for cell in cells):
            continue
        if len(cells) != len(QUEUE_COLUMNS):
            raise AssertionError(f"queue row has {len(cells)} cells, expected {len(QUEUE_COLUMNS)}: {line!r}")
        rows.append(dict(zip(QUEUE_COLUMNS, cells)))
    if not rows:
        raise AssertionError("FEEDBACK.md queue table is empty")
    return rows


def _execution_block(text: str) -> str:
    """Lines under ``  execution:`` up to the next key at that indent."""
    lines = text.splitlines()
    start = None
    for number, line in enumerate(lines):
        if line == "  execution:":
            start = number
            break
    if start is None:
        raise AssertionError("instance.yaml has no '  execution:' block")
    collected: list[str] = []
    for line in lines[start + 1:]:
        if re.match(r"^  \S", line):
            break
        collected.append(line)
    return "\n".join(collected)


class EwfInstanceGuardsTest(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        for path in (INSTANCE, README, FEEDBACK, GENERATOR):
            if not path.is_file():
                raise unittest.SkipTest(f"missing EWF deliverable: {path}")
        cls.instance = _read(INSTANCE)
        cls.readme = _read(README)
        cls.feedback = _read(FEEDBACK)

    def test_ewf_directory_holds_only_the_three_deliverables(self) -> None:
        """Onboarding §1: no code, no ``benchmark.yaml`` inside ``<project>/ewf/``."""
        present = sorted(entry.name for entry in EWF_DIR.iterdir() if not entry.name.startswith("."))
        self.assertEqual(present, EWF_DELIVERABLES)
        self.assertTrue(GENERATOR.is_file(), "the generator must live in dev/tools/")

    def test_instance_uses_no_private_extension_keys(self) -> None:
        """README §8 records the decision not to hide facts behind ``x-*`` keys."""
        offenders = [
            number
            for number, line in enumerate(self.instance.splitlines(), 1)
            if re.match(r"^\s*x-", line)
        ]
        self.assertEqual(offenders, [], "README §8 claims no x-* keys; either drop them or update the README")

    def test_readme_spec_version_is_a_projection_of_the_instance(self) -> None:
        """Onboarding §6-5: one source of truth, plus a machine check."""
        declared = re.search(r'^spec_version: "([^"]+)"$', self.instance, re.M)
        self.assertIsNotNone(declared, "instance.yaml has no top-level spec_version")
        projected = [
            match.group(1)
            for line in self.readme.splitlines()
            if "只是投影" in line
            for match in [re.search(r"`(\d+\.\d+\.\d+)`", line)]
            if match
        ]
        self.assertEqual(len(projected), 1, "README must carry exactly one version projection line")
        self.assertEqual(projected[0], declared.group(1))

    def test_every_oq_named_in_the_readme_is_declared_in_the_instance(self) -> None:
        """Onboarding §6-1: prose hits and the machine-readable hit set must agree."""
        block = re.search(r"^  open_questions: \[(.*)\]$", self.instance, re.M)
        self.assertIsNotNone(block, "instance.yaml has no open_questions list")
        declared = {item.strip() for item in block.group(1).split(",") if item.strip()}
        self.assertTrue(declared, "open_questions is empty")
        named = set(re.findall(r"OQ-\d{3}", self.readme))
        self.assertTrue(named, "README names no OQ at all")
        self.assertEqual(named - declared, set(), "README names an OQ that the instance does not declare")

    def test_feedback_queue_and_readme_narrative_cover_the_same_ids(self) -> None:
        """Onboarding §6-4: fixing one and forgetting the other is invisible without this."""
        queue_ids = {row["id"] for row in _queue_rows(self.feedback)}
        narrative_ids = set(re.findall(r"onshapescript-FB-\d{2}", self.readme))
        self.assertTrue(queue_ids, "the queue declares no id")
        self.assertEqual(queue_ids, narrative_ids)

    def test_feedback_queue_rows_use_the_declared_vocabulary(self) -> None:
        """The queue table is recognised by its header; the 类型 column is a closed set."""
        rows = _queue_rows(self.feedback)
        types = {row["类型"] for row in rows}
        allowed = {"OQ", "条款", "文档", "工具", "非缺口"}
        self.assertEqual(types - allowed, set(), f"unknown 类型 value in the queue: {sorted(types - allowed)}")

    def test_execution_view_note_node_count_matches_the_graph(self) -> None:
        """Onboarding §6-2: a number in prose must match the object it describes."""
        block = _execution_block(self.instance)
        nodes = re.findall(r"^      - id: (\S+)$", block, re.M)
        self.assertTrue(nodes, "no execution nodes found")
        stated = re.search(r"(\d+) 节点", block)
        self.assertIsNotNone(stated, "execution_view_note states no node count")
        self.assertEqual(int(stated.group(1)), len(nodes))

    @unittest.skipUnless(ARCHIVE.is_file(), f"no release data on this machine: {ARCHIVE}")
    def test_instance_matches_its_generator(self) -> None:
        """The generator re-derives every reading; a stale instance.yaml fails here."""
        proc = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    @unittest.skipUnless(EWF_REPO.is_dir(), f"read-only EWF repository not present: {EWF_REPO}")
    def test_official_validator_passes(self) -> None:
        """Acceptance command 1 from the onboarding §2."""
        proc = subprocess.run(
            [str(EWF_REPO / ".venv/bin/python"), "tests/validate_examples.py", "--project", str(EWF_DIR)],
            cwd=EWF_REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)

    @unittest.skipUnless(EWF_TOOLS_REPO.is_dir(), f"read-only EWF tools repository not present: {EWF_TOOLS_REPO}")
    def test_consumer_tool_passes(self) -> None:
        """Acceptance command 2 from the onboarding §2."""
        proc = subprocess.run(
            [str(EWF_TOOLS_REPO / ".venv/bin/python"), "-m", "ewf_tools.check", "--project", str(EWF_DIR)],
            cwd=EWF_TOOLS_REPO,
            capture_output=True,
            text=True,
        )
        output = proc.stdout + proc.stderr
        if "无法从 EWF schema 读出唯一 spec_version" in output:
            self.skipTest("the EWF working tree carries two spec versions at once (onshapescript-FB-13)")
        self.assertEqual(proc.returncode, 0, output)
        self.assertIn("PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
