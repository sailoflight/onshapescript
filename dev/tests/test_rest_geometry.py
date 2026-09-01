from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from dev.tests.test_command_step_converter import SCRIPT
from dev.tests.test_step_export import FakeClient
from onshape_rest_api_mode.geometry import (
    build_rest_geometry_package,
    geometry_backend_status,
    plan_rest_geometry_package,
)
from onshape_rest_api_mode.step_export import export_step


class RestGeometryPackageTest(unittest.TestCase):
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

    def _stage_step(self, root: Path):
        client = FakeClient([
            {"id": "translation1", "requestState": "DONE", "documentId": "doc1", "resultExternalDataIds": ["external1"]},
            b"ISO-10303-21;\nEND-ISO-10303-21;\n",
        ])
        return export_step(
            document_id="doc1",
            wv="w",
            wvid="workspace1",
            element_id="element1",
            max_polls=1,
            poll_interval_seconds=5,
            client=client,
            output_root=root,
            sleeper=lambda _: None,
        )

    def test_default_disabled_configuration_reports_unavailable_without_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = geometry_backend_status(self._config(root, enabled=False))
        self.assertFalse(status["configured"])
        self.assertFalse(status["ready"])
        self.assertFalse(status["bambuIncluded"])
        self.assertNotIn("executable", json.dumps(status).lower())
        self.assertTrue(status["analyzer"]["available"])

    def test_dry_run_reports_source_backend_and_destination_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_root = root / "step"
            self._stage_step(step_root)
            plan = plan_rest_geometry_package(
                "translation1",
                config_path=self._config(root, enabled=False),
                step_output_root=step_root,
                output_root=root / "geometry",
            )
        self.assertTrue(plan["dryRun"])
        self.assertTrue(plan["sourceManifestPresent"])
        self.assertFalse(plan["backend"]["ready"])
        self.assertFalse(plan["ready"])
        self.assertEqual(plan["estimatedApiRequests"], 0)

    def test_configured_fixture_builds_rest_owned_l6_package_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_root = root / "step"
            self._stage_step(step_root)
            config = self._config(root, enabled=True, executable=self._executable(root))
            result = build_rest_geometry_package(
                "translation1",
                config_path=config,
                step_output_root=step_root,
                output_root=root / "geometry",
            )
            manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
        self.assertTrue(result["packaged"])
        self.assertEqual(result["semanticLevel"], "L6")
        self.assertEqual(result["sourceTranslationId"], "translation1")
        self.assertEqual(result["apiRequests"], 0)
        self.assertFalse(result["bambuIncluded"])
        self.assertEqual(manifest["sourceMode"], "rest")

    def test_disabled_backend_and_corrupt_staging_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_root = root / "step"
            staged = self._stage_step(step_root)
            with self.assertRaisesRegex(RuntimeError, "converter backend is unavailable"):
                build_rest_geometry_package(
                    "translation1",
                    config_path=self._config(root, enabled=False),
                    step_output_root=step_root,
                    output_root=root / "geometry",
                )
            Path(staged["step"]["path"]).write_text("corrupt", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "hash verification failed"):
                build_rest_geometry_package(
                    "translation1",
                    config_path=self._config(root, enabled=True, executable=self._executable(root)),
                    step_output_root=step_root,
                    output_root=root / "geometry-two",
                )


if __name__ == "__main__":
    unittest.main()
