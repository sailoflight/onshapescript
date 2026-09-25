#!/usr/bin/env python3
"""Offline contracts for the consumer Release artifact specification."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dev.tools import consumer_release_spec as spec  # noqa: E402
from fdm_analysis.contracts import file_sha256  # noqa: E402

#: Mutable runtime state that must never be bundled (from the policy denylist).
MUTABLE_STATE = (
    "onshape_browser_mode/config/browser-state.json",
    "onshape_browser_mode/config/browser.local.toml",
    "onshape_browser_mode/user_data/",
    "onshape_browser_mode/outputs/",
    "onshape_rest_api_mode/config/onshape-credentials.json",
    "onshape_rest_api_mode/config/onshape-state.json",
    "onshape_rest_api_mode/config/api-usage.json",
    "onshape_rest_api_mode/outputs/",
    "mcp_main/win/mcp/config/tool_views.local.toml",
)

#: Development/governance paths that must never appear in the plan.
NEVER_PLANNED = (
    "AGENTS.md",
    "CLAUDE.md",
    "agent-project-guides/",
    "dev/",
    ".git/",
    ".venv/",
    "temp/",
)

_SNAPSHOT_SKIP = {".git", ".venv", "__pycache__"}


def _matches(path: str, entry: str) -> bool:
    """Denylist matching: directory entries are prefixes, files must be exact."""
    if entry.endswith("/"):
        base = entry[:-1]
        return path == base or path.startswith(entry)
    return path == entry


def _tree_snapshot(root: Path) -> list[tuple[str, int, int]]:
    """Bounded (path, size, mtime_ns) listing used to detect any write."""
    rows: list[tuple[str, int, int]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        for child in sorted(current.iterdir(), key=lambda p: p.name):
            if child.name in _SNAPSHOT_SKIP:
                continue
            stat = child.lstat()
            rows.append(
                (child.relative_to(root).as_posix(), stat.st_size, stat.st_mtime_ns)
            )
            if child.is_dir() and not child.is_symlink():
                stack.append(child)
    return sorted(rows)


class ConsumerReleaseSpecTest(unittest.TestCase):
    def test_whitelist_and_denylist_are_disjoint(self) -> None:
        overlap = sorted(set(spec.WHITELIST) & set(spec.DENYLIST))
        self.assertEqual(overlap, [], f"overlap between whitelist and denylist: {overlap}")

    def test_validate_reports_no_invariant_violation(self) -> None:
        self.assertEqual(spec.validate(ROOT), [])

    def test_the_fdm_package_is_planned_and_no_decision_is_pending(self) -> None:
        # Owner decision 2026-09-25: fdm_analysis ships WITH the artifact because
        # the geometry/FDM capabilities are MCP tools of this server. Dropping it
        # from the whitelist breaks the server's own imports, so a regression here
        # is not a slim-down, it is a broken artifact.
        self.assertIn("fdm_analysis/", spec.WHITELIST)
        self.assertNotIn("fdm_analysis/", spec.DENYLIST)
        self.assertEqual(spec.PENDING_DECISION, ())
        planned = {entry.path for entry in spec.plan(ROOT).files}
        self.assertTrue(
            any(_matches(path, "fdm_analysis/") for path in planned),
            "fdm_analysis is whitelisted but nothing from it is planned",
        )

    def test_plan_contains_no_denylisted_path(self) -> None:
        release = spec.plan(ROOT)
        denied = [entry.path for entry in release.files if spec.is_denied(entry.path)]
        self.assertEqual(denied, [], f"denylisted paths planned: {denied}")

    def test_plan_excludes_development_and_governance_paths(self) -> None:
        planned = {entry.path for entry in spec.plan(ROOT).files}
        for prefix in NEVER_PLANNED:
            offenders = sorted(path for path in planned if _matches(path, prefix))
            self.assertEqual(offenders, [], f"{prefix} leaked into the plan: {offenders}")
        self.assertNotIn("AGENTS.md", planned)
        self.assertNotIn("CLAUDE.md", planned)

    def test_mutable_state_is_absent_or_reported_excluded(self) -> None:
        release = spec.plan(ROOT)
        planned = {entry.path for entry in release.files}
        excluded = set(release.excluded)
        for entry in MUTABLE_STATE:
            base = entry.rstrip("/")
            offenders = sorted(path for path in planned if _matches(path, entry))
            self.assertEqual(
                offenders, [], f"mutable state leaked into the plan: {offenders}"
            )
            if (ROOT / base).exists():
                self.assertIn(
                    entry,
                    excluded,
                    f"existing denylisted path not reported as excluded: {entry}",
                )

    def test_plan_sha256_values_recompute(self) -> None:
        released = spec.plan(ROOT)
        self.assertTrue(released.files, "the plan should not be empty")
        for entry in released.files:
            path = ROOT / entry.path
            self.assertEqual(entry.bytes, path.stat().st_size, entry.path)
            self.assertEqual(entry.sha256, file_sha256(path), entry.path)
            self.assertEqual(len(entry.sha256), 64, entry.path)

    def test_spec_performs_no_filesystem_writes(self) -> None:
        before = _tree_snapshot(ROOT)
        first = spec.plan(ROOT)
        second = spec.plan(ROOT)
        problems = spec.validate(ROOT)
        after = _tree_snapshot(ROOT)
        self.assertEqual(first, second, "plan() is not deterministic")
        self.assertEqual(problems, [], f"unexpected invariant violations: {problems}")
        self.assertEqual(before, after, "the spec module modified the workspace tree")

    def test_check_cli_exits_zero_on_clean_tree(self) -> None:
        spec_path = Path(spec.__file__)
        result = subprocess.run(
            [sys.executable, str(spec_path), "--check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("invariants OK", result.stdout)

    def test_check_cli_exits_nonzero_on_violation(self) -> None:
        spec_path = Path(spec.__file__)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "usage").mkdir(parents=True)
            (root / "docs" / "usage" / "MCP_CONSUMER.md").write_text(
                "x", encoding="utf-8"
            )
            result = subprocess.run(
                [sys.executable, str(spec_path), "--check", "--root", str(root)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0, "a missing whitelist must fail --check")
        self.assertIn("whitelisted path does not exist", result.stdout)


if __name__ == "__main__":
    unittest.main()
