from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fdm_analysis.dependency_probe import (
    configure_geometry_dependency,
    discover_geometry_dependencies,
    discover_local_candidates,
    parse_wsl_distributions,
    windows_to_wsl_path,
)


class GeometryDependencyProbeTest(unittest.TestCase):
    def _layout(self, root: Path):
        repo = root / "onshapescript"
        converter = repo / "fdm_analysis" / "conversion" / "cadquery_step_to_stl.py"
        converter.parent.mkdir(parents=True)
        converter.write_text("# fixture\n", encoding="ascii")
        python = root / "CadQ" / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("fixture", encoding="ascii")
        return repo, converter, python

    def _runner(self, accepted: Path | None):
        def run(command, **kwargs):
            if accepted is not None and Path(command[0]) == accepted:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps({"cadqueryVersion": "2.8.0", "ocpVersion": "7.9.3.1"}),
                    stderr="",
                )
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="missing")
        return run

    def _config(self, path: Path):
        path.write_text(json.dumps({
            "enabled": False,
            "provider": "command",
            "name": "",
            "version": "",
            "executable": "",
            "argumentTemplate": [],
            "timeoutSeconds": 300,
            "linearToleranceMm": 0.05,
            "angularToleranceDegrees": 5.0,
            "overhangFromVerticalDegrees": 45.0,
        }) + "\n", encoding="utf-8")

    def test_sibling_candidate_is_versioned_sanitized_and_precedes_global(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, converter, python = self._layout(Path(tmp))
            candidates = discover_local_candidates(
                search_parent=repo.parent,
                converter_cli=converter,
                runner=self._runner(python),
            )
            resolution = discover_geometry_dependencies(
                repo,
                runner=self._runner(python),
                platform_name="posix",
            )
        self.assertEqual(candidates[0]["scope"], "sibling")
        self.assertEqual(candidates[0]["projectName"], "CadQ")
        self.assertEqual(candidates[0]["cadqueryVersion"], "2.8.0")
        self.assertEqual(candidates[0]["ocpVersion"], "7.9.3.1")
        self.assertEqual(resolution["state"], "reusable_candidates_found")
        self.assertFalse(resolution["automaticInstall"])
        self.assertNotIn("command", resolution["candidates"][0])
        self.assertTrue(resolution["nextAction"]["requiresUserConfirmation"])

    def test_missing_dependency_requires_ask_before_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, _, _ = self._layout(Path(tmp))
            resolution = discover_geometry_dependencies(
                repo,
                runner=self._runner(None),
                platform_name="posix",
            )
        self.assertEqual(resolution["state"], "not_found")
        self.assertEqual(resolution["nextAction"]["kind"], "ask_before_install")
        self.assertTrue(resolution["nextAction"]["requiresUserConfirmation"])
        self.assertFalse(resolution["automaticInstall"])
        self.assertIn("do not install automatically", resolution["nextAction"]["question"])

    def test_configure_accepts_only_rescanned_candidate_and_supports_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, _, python = self._layout(root)
            config = root / "geometry.json"
            self._config(config)
            resolution = discover_geometry_dependencies(
                repo,
                runner=self._runner(python),
                platform_name="posix",
            )
            candidate_id = resolution["candidates"][0]["candidateId"]
            preview = configure_geometry_dependency(
                config,
                repo_root=repo,
                candidate_id=candidate_id,
                runner=self._runner(python),
                platform_name="posix",
                dry_run=True,
            )
            self.assertFalse(json.loads(config.read_text(encoding="utf-8"))["enabled"])
            result = configure_geometry_dependency(
                config,
                repo_root=repo,
                candidate_id=candidate_id,
                runner=self._runner(python),
                platform_name="posix",
            )
            configured = json.loads(config.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "candidate_id"):
                configure_geometry_dependency(
                    config,
                    repo_root=repo,
                    candidate_id="not-current",
                    runner=self._runner(python),
                    platform_name="posix",
                )
        self.assertTrue(preview["dryRun"])
        self.assertFalse(preview["automaticInstall"])
        self.assertTrue(result["configured"])
        self.assertTrue(configured["enabled"])
        self.assertEqual(configured["version"], "cadquery-2.8.0+OCP-7.9.3.1")
        self.assertEqual(configured["executable"], str(python.resolve()))

    def test_probe_script_bootstraps_repo_when_executed_by_path(self):
        script = Path(__file__).resolve().parents[2] / "fdm_analysis" / "dependency_probe.py"
        process = subprocess.run(
            [sys.executable, str(script), "--help"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("--converter-cli", process.stdout)

    def test_candidate_probe_count_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, converter, _ = self._layout(root)
            for index in range(40):
                python = root / f"Sibling{index:02d}" / ".venv" / "bin" / "python"
                python.parent.mkdir(parents=True)
                python.write_text("fixture", encoding="ascii")
            calls = []

            def missing(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="missing")

            candidates = discover_local_candidates(
                search_parent=repo.parent,
                converter_cli=converter,
                runner=missing,
            )
        self.assertEqual(candidates, [])
        self.assertLessEqual(len(calls), 8)

    def test_windows_wsl_parsing_is_bounded_and_deterministic(self):
        self.assertEqual(
            windows_to_wsl_path(r"C:\MCP\onshapescript\probe.py"),
            "/mnt/c/MCP/onshapescript/probe.py",
        )
        self.assertEqual(
            parse_wsl_distributions("Ubuntu-24.04\x00\n* Debian\x00\ninvalid name\n"),
            ["Ubuntu-24.04", "Debian"],
        )


if __name__ == "__main__":
    unittest.main()
