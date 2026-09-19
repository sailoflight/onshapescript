"""Executable gates for the FeatureScript validation strategy.

`docs/architecture/FS_VALIDATION_STRATEGY.md` makes four claims that a test can
hold it to:

1. the offline checker and the browser diagnostic normalizer stay local -- no
   network, no subprocess, no third-party runtime import;
2. the reuse survey is a survey: every candidate carries a link, and every
   candidate is recorded as *not* wired in rather than as adopted;
3. the decision keeps `fs_check` as the offline pass and names the
   reuse-on-detection mechanism;
4. the backlog marks which items are reachable offline, so a doc-only claim
   cannot quietly become a capability claim.

Nothing here executes an external tool, touches the network, or reads a checker
other than the two in-repository modules.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "architecture" / "FS_VALIDATION_STRATEGY.md"

# The two offline passes whose locality this strategy depends on.
LOCAL_MODULES = (
    ROOT / "onshape_docs" / "query" / "fs_check.py",
    ROOT / "onshape_browser_mode" / "diagnostics.py",
)

# Standard-library modules the local path is allowed to use. The list is
# deliberately short: a new import has to be justified here.
_ALLOWED_STDLIB = {
    "abc", "ast", "dataclasses", "datetime", "difflib", "enum", "functools",
    "hashlib", "io", "json", "os", "pathlib", "re", "shutil", "sys",
    "tempfile", "textwrap", "typing", "unicodedata", "collections", "itertools",
    "__future__", "json.decoder",
}

_FORBIDDEN = {
    "socket", "http", "urllib", "requests", "httpx", "aiohttp", "ssl",
    "subprocess", "multiprocessing", "asyncio", "playwright", "selenium",
}


def _imported_roots(path: Path) -> tuple[set[str], set[str]]:
    """Split a module's imports into stdlib and in-repository package roots."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    stdlib: set[str] = set()
    project: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                stdlib.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import inside the project
                project.add("." * node.level + (node.module or ""))
                continue
            root = (node.module or "").split(".")[0]
            if (ROOT / root / "__init__.py").exists():
                project.add(root)
            elif root:
                stdlib.add(root)
    return stdlib, project


class LocalityTest(unittest.TestCase):
    def test_local_passes_import_no_network_or_process_module(self) -> None:
        for path in LOCAL_MODULES:
            with self.subTest(module=path.name):
                stdlib, project = _imported_roots(path)
                self.assertFalse(
                    (stdlib | project) & _FORBIDDEN,
                    f"{path.name} imports a network/process module",
                )

    def test_every_new_dependency_is_an_explicit_decision(self) -> None:
        for path in LOCAL_MODULES:
            with self.subTest(module=path.name):
                stdlib, _ = _imported_roots(path)
                unexpected = stdlib - _ALLOWED_STDLIB
                self.assertEqual(
                    unexpected, set(),
                    f"{path.name} gained a dependency that this strategy has not reviewed",
                )

    def test_the_checker_is_importable_and_does_not_shell_out(self) -> None:
        """The offline pass must be usable in-process, as the deploy path uses it."""
        from onshape_docs.query import fs_check

        source = "FeatureScript 3044;\n"
        result = fs_check.check_source(fs_check.FsFile.from_text(source, name="probe.fs")).as_result()
        self.assertEqual(set(result), {"name", "checked", "clear", "errorCount", "warningCount", "errors", "warnings"})
        self.assertGreater(result["errorCount"], 0)  # the import line is genuinely missing


class SurveyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = DOC.read_text(encoding="utf-8")

    def test_doc_exists_and_is_routed(self) -> None:
        self.assertTrue(DOC.exists())
        index = (ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("architecture/FS_VALIDATION_STRATEGY.md", index)

    def test_every_candidate_carries_a_link_and_a_not_wired_status(self) -> None:
        survey = self.text.split("## 3. External reuse survey", 1)[1].split("## 4.", 1)[0]
        rows = [line for line in survey.splitlines() if line.startswith("|") and "https://" in line]
        self.assertGreaterEqual(len(rows), 4, "the survey lost its candidates")
        for row in rows:
            with self.subTest(row=row[:40]):
                self.assertRegex(row, r"\[[^\]]+\]\(https://[^)]+\)")
        # Every candidate row must record non-adoption, not an unexplained silence.
        for row in rows:
            with self.subTest(row=row[:40]):
                self.assertRegex(row, r"\| *(Not wired|None found)[^|]*\|? *$")

    def test_the_survey_is_labelled_as_unexecuted(self) -> None:
        self.assertIn("nothing was downloaded, installed, or executed", self.text)
        self.assertIn("search-level evidence", self.text)

    def test_the_decision_names_the_reuse_on_detection_mechanism(self) -> None:
        decision = self.text.split("## 4. Decision", 1)[1].split("## 5.", 1)[0]
        self.assertIn("Reuse on detection, never on installation", decision)
        self.assertIn("fdm_analysis/dependency_probe.py", decision)
        self.assertIn("advisory", decision)

    def test_the_backlog_separates_offline_from_machine_work(self) -> None:
        backlog = self.text.split("## 5. Backlog", 1)[1].split("## 6.", 1)[0]
        self.assertIn("**No**", backlog)
        self.assertIn("browser compiler's job", backlog)
        self.assertIn("Zero false positives", backlog)

    def test_the_ladder_labels_the_advisory_rule(self) -> None:
        self.assertIn("All local findings are advisory", self.text)
        self.assertIn("browser compiler is the authority", self.text)


if __name__ == "__main__":
    unittest.main()
