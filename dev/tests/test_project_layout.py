#!/usr/bin/env python3
"""Offline contracts for module-owned configuration and runtime paths."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main.bridge import bridge_server  # noqa: E402
from onshape_browser_mode import settings as browser_settings  # noqa: E402
from onshape_browser_mode.session import BrowserSession  # noqa: E402
from onshape_docs.query import project_docs  # noqa: E402
from onshape_rest_api_mode import client as rest_client  # noqa: E402


class ProjectLayoutTest(unittest.TestCase):
    def test_browser_runtime_is_owned_by_browser_module(self) -> None:
        browser_root = ROOT / "onshape_browser_mode"
        self.assertEqual(
            browser_settings.DEFAULT_CONFIG_PATH,
            browser_root / "config" / "browser.toml",
        )
        self.assertEqual(
            browser_settings.LOCAL_CONFIG_PATH,
            browser_root / "config" / "browser.local.toml",
        )
        self.assertEqual(
            BrowserSession._state_path(),
            browser_root / "config" / "browser-state.json",
        )
        self.assertEqual(
            BrowserSession().profile_dir(),
            browser_root / "user_data" / "onshape_profile",
        )

    def test_rest_runtime_is_owned_by_rest_module(self) -> None:
        rest_root = ROOT / "onshape_rest_api_mode"
        self.assertEqual(
            rest_client.CREDENTIALS_PATH,
            rest_root / "config" / "onshape-credentials.json",
        )
        self.assertEqual(
            rest_client.STATE_PATH,
            rest_root / "config" / "onshape-state.json",
        )
        self.assertEqual(rest_client.USAGE_PATH, rest_root / "config" / "api-usage.json")
        self.assertEqual(rest_client.OUTPUTS_DIR, rest_root / "outputs")
        self.assertEqual(
            rest_client.PARAMETERS_DIR,
            ROOT / "examples" / "branch-cable-trophy" / "config",
        )

    def test_bridge_runtime_is_owned_by_mcp_module(self) -> None:
        self.assertEqual(
            bridge_server.LOG_PATH,
            ROOT / "mcp_main" / "bridge" / "logs" / "bridge-server.log",
        )

    def test_legacy_root_directories_do_not_return(self) -> None:
        for name in ("config", "tools", "tests", "user_data", "outputs", "mcp_server.py"):
            self.assertFalse((ROOT / name).exists(), name)

    def test_documentation_index_preserves_semantic_ownership(self) -> None:
        project_docs.reload()
        listed = project_docs.list_pages()
        self.assertEqual(
            set(listed["categories"]),
            {"guide", "experience", "verification", "reference", "example"},
        )
        self.assertGreaterEqual(listed["categories"]["guide"], 4)
        self.assertGreaterEqual(listed["categories"]["experience"], 4)
        for page in listed["pages"]:
            path = page["path"]
            category = page["category"]
            if category == "experience":
                self.assertTrue(path.startswith("onshape_docs/experience/"), path)
            if category == "verification":
                self.assertTrue(path.startswith("onshape_docs/verification/"), path)
        self.assertIn("Index first", listed["note"])

    def test_browser_experience_is_found_through_index(self) -> None:
        found = project_docs.search("persistent profile login recovery", limit=5)
        self.assertTrue(found["results"])
        first = found["results"][0]
        self.assertEqual(first["page"], "browser-automation")
        self.assertEqual(first["category"], "experience")
        section = project_docs.section(first["page"], first["sectionTitle"])
        self.assertEqual(section["category"], "experience")
        self.assertIn("profile", section["text"])

    def test_agent_instructions_require_index_before_reasoning(self) -> None:
        instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        index_step = instructions.index("Search the cheapest index first")
        exact_step = instructions.index("Open the smallest exact entry")
        source_step = instructions.index("complete authored or raw source")
        reason_step = instructions.index("Reason, plan, and edit only after")
        self.assertLess(index_step, exact_step)
        self.assertLess(exact_step, source_step)
        self.assertLess(source_step, reason_step)
        self.assertIn("Do not open generated JSON indexes directly", instructions)

    def test_large_indexes_require_search_and_bounded_reads(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        docs_map = (ROOT / "onshape_docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("159 KiB", agents)
        self.assertIn("`grep`/`rg`", agents)
        self.assertIn("bounded window", agents)
        self.assertIn("159 KiB", claude)
        self.assertIn("有界行窗口", claude)
        self.assertIn("Never print or ingest the complete generated JSON index", docs_map)

    def test_retired_documentation_paths_do_not_return(self) -> None:
        retired = (
            "onshape_docs/guide/fs-assistant.md",
            "onshape_docs/guide/onshape-api.md",
            "onshape_docs/verification/llm-experience-",
            "dev/experience/",
        )
        files = [ROOT / "AGENTS.md", ROOT / "CLAUDE.md", ROOT / "README.md"]
        for directory in (
            "mcp_main",
            "onshape_browser_mode",
            "onshape_rest_api_mode",
            "onshape_docs",
            "examples",
        ):
            owner = ROOT / directory
            files.extend(owner.rglob("*.py"))
            files.extend(owner.rglob("*.md"))
        found = []
        for path in files:
            text = path.read_text(encoding="utf-8")
