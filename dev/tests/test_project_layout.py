#!/usr/bin/env python3
"""Offline contracts for module-owned configuration and runtime paths."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main.win.bridge import bridge_server  # noqa: E402
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
            ROOT / "mcp_main" / "win" / "bridge" / "logs" / "bridge-server.log",
        )

    def test_legacy_root_directories_do_not_return(self) -> None:
        for name in ("config", "tools", "tests", "user_data", "outputs", "mcp_server.py"):
            self.assertFalse((ROOT / name).exists(), name)

    def test_dev_directory_contains_no_project_documentation(self) -> None:
        self.assertFalse(list((ROOT / "dev").glob("*.md")))
        self.assertTrue((ROOT / "docs" / "development" / "LAB.md").is_file())
        self.assertTrue((ROOT / "docs" / "development" / "START.md").is_file())

    def test_public_docs_index_excludes_internal_role_documents(self) -> None:
        project_docs.reload()
        listed = project_docs.list_pages()
        pages = {page["page"]: page["path"] for page in listed["pages"]}
        self.assertEqual(pages["mcp-consumer"], "docs/usage/MCP_CONSUMER.md")
        self.assertEqual(pages["mcp-tool-reference"], "docs/generated/TOOL_REFERENCE.md")
        internal_prefixes = (
            "docs/architecture/",
            "docs/development/",
            "docs/evaluation/",
            "docs/modules/",
            "docs/operations/",
            "docs/verification/",
            "docs/history/",
            "docs/roadmap/",
        )
        self.assertFalse(
            [path for path in pages.values() if path.startswith(internal_prefixes)]
        )

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
        found = project_docs.search(
            "persistent profile login recovery", page="browser-automation", limit=5
        )
        self.assertTrue(found["results"])
        first = found["results"][0]
        self.assertEqual(first["page"], "browser-automation")
        self.assertEqual(first["category"], "experience")
        section = project_docs.section(first["page"], first["sectionTitle"])
        self.assertEqual(section["category"], "experience")
        self.assertIn("profile", section["text"])

    def test_field_evaluation_has_sanitized_machine_evidence(self) -> None:
        evidence_path = (
            ROOT
            / "docs"
            / "evaluation"
            / "evidence"
            / "windows-onshape-page-20260824.json"
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertEqual(evidence["environment"], "development")
        self.assertEqual(evidence["browserObservation"]["pageClass"], "onshape-signin")
        self.assertFalse(evidence["browserObservation"]["loginConfirmed"])
        self.assertEqual(evidence["invocationAccounting"]["onshapeRestToolsInvoked"], 0)
        self.assertEqual(evidence["invocationAccounting"]["cloudWriteActionsInvoked"], 0)
        serialized = json.dumps(evidence).lower()
        for forbidden in ("authorization", "bearer ", "accesskey", "secretkey", "cookie"):
            self.assertNotIn(forbidden, serialized)

    def test_runtime_prompt_delivery_authorities_are_linked(self) -> None:
        docs_index = (ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
        architecture = (ROOT / "docs" / "architecture" / "OVERVIEW.md").read_text(
            encoding="utf-8"
        )
        module = (ROOT / "docs" / "modules" / "mcp-main.md").read_text(
            encoding="utf-8"
        )
        verification = (
            ROOT / "docs" / "verification" / "MCP_CLIENT_COMPATIBILITY.md"
        ).read_text(encoding="utf-8")
        example = (
            ROOT / "mcp_main" / "wsl" / "dsh" / "cordis.patch.yml.example"
        ).read_text(encoding="utf-8")

        self.assertIn("Field Evaluator", docs_index)
        self.assertIn("MCP_CLIENT_COMPATIBILITY.md", docs_index)
        self.assertIn("mcp_main/win/mcp/runtime_prompt.py", architecture)
        self.assertIn("mcp_main/win/mcp/runtime_prompt.py", module)
        self.assertIn("generated companion", verification)
        self.assertIn("mcp-onshape-featurescript", example)
        self.assertIn("mcp-onshape-runtime-policy", example)
        self.assertTrue(
            (ROOT / "docs" / "evaluation" / "WINDOWS_ONSHAPE_PAGE.md").is_file()
        )

    def test_development_history_is_mapped_to_current_authorities(self) -> None:
        trace = (ROOT / "docs" / "history" / "TRACEABILITY.md").read_text(
            encoding="utf-8"
        )
        legacy_dir = ROOT / "docs" / "history" / "legacy"
        for legacy in legacy_dir.glob("*.md"):
            self.assertIn(legacy.name, trace)
            self.assertIn("../TRACEABILITY.md", legacy.read_text(encoding="utf-8"))
        for classification in (
            "current implemented authority",
            "reusable experience",
            "verification evidence",
            "historical rationale",
            "retired detail",
            "future proposal",
        ):
            self.assertIn(classification, trace)
        self.assertIn("onshape_docs/verification/live/README.md", trace)

        docs_index = (ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
        development = (ROOT / "docs" / "development" / "START.md").read_text(
            encoding="utf-8"
        )
        architecture = (ROOT / "docs" / "architecture" / "OVERVIEW.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("history/TRACEABILITY.md", docs_index)
        self.assertIn("../history/TRACEABILITY.md", development)
        self.assertIn("../history/TRACEABILITY.md", architecture)
        self.assertNotIn("BROWSER_DEVELOPMENT_HISTORY.md", architecture)

        rest_contract = (ROOT / "docs" / "modules" / "rest-api-mode.md").read_text(
            encoding="utf-8"
        )
        for override in (
            "ONSHAPE_CREDENTIALS",
            "ONSHAPE_STATE",
            "ONSHAPE_PARAMETERS_DIR",
            "ONSHAPE_OUTPUTS_DIR",
            "ONSHAPE_API_USAGE",
        ):
            self.assertIn(override, rest_contract)

        runbook = (ROOT / "docs" / "operations" / "MCP_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("apiQuota.alreadyConsumed + api-usage.json consumed", runbook)
        self.assertIn("UI year-to-date total - ledgerConsumed", runbook)
        operations_source = (
            ROOT / "onshape_rest_api_mode" / "operations.py"
        ).read_text(encoding="utf-8")
        self.assertIn('quota.get("alreadyConsumed", 0)', operations_source)
        self.assertIn('consumed = baseline + int(usage.get("consumed", 0))', operations_source)

        roadmap = (ROOT / "docs" / "roadmap" / "DYNAMIC_TOOL_DISCOVERY.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("mcp_documentation", roadmap)
        self.assertIn("overview | search | open | status | reset", roadmap)
        self.assertIn("hard cap of 12", roadmap)
        self.assertIn("not accepted schemas or defaults", roadmap)

        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        experience = (
            ROOT / "onshape_docs" / "experience" / "featurescript.md"
        ).read_text(encoding="utf-8")
        live_record = (
            ROOT / "onshape_docs" / "verification" / "live" / "README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("跨版本 import 的精确边界仍 unknown", claude)
        self.assertIn("exact import", experience.lower())
        self.assertIn("import 边界（unresolved）", live_record)
        self.assertIn("Evidence interpretation", live_record)

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
        self.assertIn("191 KiB", agents)
        self.assertIn("`grep`/`rg`", agents)
        self.assertIn("bounded window", agents)
        self.assertIn("191 KiB", claude)
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
            for retired_path in retired:
                if retired_path in text:
                    found.append(f"{path.relative_to(ROOT)}: {retired_path}")
        self.assertFalse(found, f"Retired documentation paths returned: {found}")


if __name__ == "__main__":
    unittest.main()
