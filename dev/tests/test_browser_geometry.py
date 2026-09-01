from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dev.tests.test_browser_step_export import FakePage
from dev.tests.test_command_step_converter import SCRIPT
from onshape_browser_mode.geometry import (
    browser_geometry_status,
    build_browser_geometry_package,
    configure_browser_geometry_backend,
    plan_browser_geometry_package,
)
from onshape_browser_mode.project import run_project
from onshape_browser_mode.step_export import export_browser_step


class BrowserGeometryPackageTest(unittest.TestCase):
    def test_field_validation_projects_are_valid_l6_dry_runs(self):
        for name, deliverable_id in (
            ("browser-geometry-field-validation", "geometry-analysis-package"),
            ("browser-geometry-windowless-validation", "windowless-geometry-package"),
        ):
            plan = run_project(name, dry_run=True)
            self.assertTrue(plan["dryRun"])
            self.assertEqual(plan["deliverables"][0]["id"], deliverable_id)

    def _config(self, root: Path, *, enabled: bool, executable: Path | None = None):
        path = root / "geometry-backend.json"
        path.write_text(json.dumps({
            "enabled": enabled,
            "provider": "command",
            "name": "fixture-cli" if enabled else "",
            "version": "1.0" if enabled else "",
            "executable": str(executable) if executable else "",
            "argumentTemplate": ["--input", "{input}", "--output", "{output}"],
            "timeoutSeconds": 30,
            "linearToleranceMm": 0.05,
            "angularToleranceDegrees": 5.0,
            "overhangFromVerticalDegrees": 45.0,
        }, indent=2) + "\n", encoding="utf-8")
        return path

    def _executable(self, root: Path):
        path = root / "fixture converter"
        path.write_text(SCRIPT, encoding="utf-8")
        os.chmod(path, 0o755)
        return path

    def _stage(self, root: Path):
        return export_browser_step(
            FakePage(),
            source_tab="Part Studio 1",
            export_id="export1",
            document_id="doc1",
            workspace_id="workspace1",
            element_id="element1",
            output_root=root,
        )

    def test_disabled_status_is_offline_and_does_not_reveal_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = browser_geometry_status(self._config(Path(tmp), enabled=False))
        self.assertFalse(status["ready"])
        self.assertNotIn("executable", json.dumps(status).lower())
        self.assertFalse(status["bambuIncluded"])

    def test_status_routes_opaque_candidate_to_owning_configure_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            discovery = {
                "state": "reusable_candidates_found",
                "automaticInstall": False,
                "candidates": [{
                    "candidateId": "candidate1",
                    "provider": "cadquery-ocp",
                    "host": "local",
                    "scope": "sibling",
                    "projectName": "CadQ",
                    "cadqueryVersion": "2.8.0",
                    "ocpVersion": "7.9.3.1",
                }],
                "nextAction": {
                    "kind": "configure_existing",
                    "requiresUserConfirmation": True,
                    "candidateIds": ["candidate1"],
                },
                "_candidates": [{}],
            }
            with mock.patch(
                "onshape_browser_mode.geometry.discover_geometry_dependencies",
                return_value=discovery,
            ):
                status = browser_geometry_status(
                    self._config(root, enabled=False),
                    repo_root=root,
                )
        resolution = status["dependencyResolution"]
        self.assertEqual(resolution["nextAction"]["tool"], "browser_configure_geometry_backend")
        self.assertNotIn("_candidates", resolution)
        self.assertFalse(resolution["automaticInstall"])

    def test_configure_wrapper_never_accepts_executable_or_argv(self):
        with mock.patch(
            "onshape_browser_mode.geometry.configure_geometry_dependency",
            return_value={"dryRun": True, "configured": False},
        ) as configure:
            result = configure_browser_geometry_backend(
                "candidate1",
                dry_run=True,
                config_path=Path("geometry.json"),
                repo_root=Path("repo"),
            )
        self.assertTrue(result["dryRun"])
        configure.assert_called_once_with(
            Path("geometry.json"),
            repo_root=Path("repo"),
            candidate_id="candidate1",
            dry_run=True,
        )

    def test_dry_run_reports_browser_source_and_disabled_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_root = root / "step"
            self._stage(step_root)
            plan = plan_browser_geometry_package(
                "export1",
                config_path=self._config(root, enabled=False),
                step_output_root=step_root,
                output_root=root / "geometry",
            )
        self.assertTrue(plan["sourceManifestPresent"])
        self.assertFalse(plan["ready"])
        self.assertEqual(plan["semanticLevel"], "L6")
        self.assertEqual(plan["estimatedApiRequests"], 0)

    def test_configured_fixture_builds_browser_owned_l6_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_root = root / "step"
            self._stage(step_root)
            result = build_browser_geometry_package(
                "export1",
                config_path=self._config(root, enabled=True, executable=self._executable(root)),
                step_output_root=step_root,
                output_root=root / "geometry",
            )
            manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
        self.assertTrue(result["packaged"])
        self.assertEqual(result["semanticLevel"], "L6")
        self.assertEqual(result["sourceExportId"], "export1")
        self.assertEqual(result["apiRequests"], 0)
        self.assertFalse(result["bambuIncluded"])
        self.assertEqual(manifest["sourceMode"], "browser")

    def test_corrupt_browser_step_fails_hash_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_root = root / "step"
            staged = self._stage(step_root)
            Path(staged["step"]["path"]).write_text("corrupt", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "hash verification failed"):
                build_browser_geometry_package(
                    "export1",
                    config_path=self._config(root, enabled=True, executable=self._executable(root)),
                    step_output_root=step_root,
                    output_root=root / "geometry",
                )


if __name__ == "__main__":
    unittest.main()
