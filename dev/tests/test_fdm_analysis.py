from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fdm_analysis import (
    FdmBackends,
    MeshArtifact,
    SliceArtifact,
    SliceProfile,
    StepArtifact,
    WindowsToWslDelivery,
    WorkspaceDeliveryTarget,
    WslLocalDelivery,
    build_fdm_package,
)
from fdm_analysis.conversion import UnavailableStepConverter
from fdm_analysis.slicers import BambuStudioBackend, ReplayExecution, WslWindowsExecution
from onshape_browser_mode.fdm_adapter import step_artifact_from_browser_export
from onshape_rest_api_mode.fdm_adapter import step_artifact_from_rest_export


class FakeConverter:
    def capabilities(self):
        return {"available": True, "name": "fake-step", "version": "1"}

    def convert(self, step, *, output_path, linear_tolerance_mm, angular_tolerance_degrees):
        output_path.write_bytes(b"solid fixture\nendsolid fixture\n")
        return MeshArtifact.from_path(
            output_path,
            units="mm",
            triangle_count=12,
            converter={
                "name": "fake-step",
                "linearToleranceMm": linear_tolerance_mm,
                "angularToleranceDegrees": angular_tolerance_degrees,
            },
        )


class FakeAnalyzer:
    def capabilities(self):
        return {"available": True, "name": "fake-geometry", "version": "1"}

    def analyze(self, mesh, *, orientation_matrix):
        return {
            "watertight": True,
            "dimensionsMm": [20.0, 30.0, 40.0],
            "bedContactAreaMm2": 300.0,
            "printHeightMm": 40.0,
            "overhangAreaMm2": 12.0,
            "centerOfMassStable": True,
            "orientationMatrix": list(orientation_matrix),
        }


class FakeSlicer:
    def capabilities(self):
        return {"available": True, "name": "fake-slicer", "version": "1"}

    def slice(self, mesh, *, profile, output_path, sliced_data_path):
        output_path.write_bytes(b"PK\x03\x04fixture-3mf")
        sliced_data_path.mkdir(parents=True, exist_ok=True)
        (sliced_data_path / "plate.json").write_text("{}\n", encoding="utf-8")
        return SliceArtifact.from_path(
            output_path,
            backend=self.capabilities(),
            metrics={
                "layerCount": 200,
                "estimatedTimeSeconds": 3600,
                "filamentGrams": 18.5,
                "supportRequired": False,
            },
            sliced_data_path=sliced_data_path,
        )


class FdmAnalysisTest(unittest.TestCase):
    def _files(self, root: Path):
        step = root / "source.step"
        step.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="ascii")
        machine = root / "machine.json"
        process = root / "process.json"
        filament = root / "filament.json"
        for path in (machine, process, filament):
            path.write_text("{}\n", encoding="ascii")
        profile = SliceProfile(machine=machine, process=process, filaments=(filament,))
        return step, profile

    def test_browser_and_rest_adapters_share_canonical_step_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            step_path, _ = self._files(Path(tmp))
            browser = step_artifact_from_browser_export(
                step_path,
                page_url="https://cad.onshape.com/documents/d/w/w/e/e",
                document_id="d",
                workspace_id="w",
                element_id="e",
            )
            rest = step_artifact_from_rest_export(
                step_path,
                document_id="d",
                wv="w",
                wvid="w",
                element_id="e",
                translation_id="t",
            )
        self.assertIsInstance(browser, StepArtifact)
        self.assertEqual(browser.sha256, rest.sha256)
        self.assertEqual(browser.media_type, rest.media_type)
        self.assertEqual(browser.units, rest.units)
        self.assertEqual(browser.source["mode"], "browser")
        self.assertEqual(rest.source["mode"], "rest")

    def test_build_package_writes_reports_and_l6_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_path, profile = self._files(root)
            step = StepArtifact.from_path(
                step_path,
                source={"mode": "browser", "reference": "page", "identifiers": {"elementId": "e"}},
            )
            result = build_fdm_package(
                step,
                output_dir=root / "package",
                profile=profile,
                backends=FdmBackends(FakeConverter(), FakeAnalyzer(), FakeSlicer()),
            )
            manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
        self.assertTrue(result["packaged"])
        self.assertEqual(result["assessment"]["state"], "assessable")
        self.assertIsNone(result["assessment"]["pass"])
        self.assertEqual(manifest["semanticLevel"], "L6")
        self.assertEqual(manifest["deliverableType"], "fdm-package")
        self.assertEqual(
            {item["name"] for item in manifest["artifacts"]},
            {"model.step", "model.stl", "sliced-project.3mf", "report.json", "report.md"},
        )
        self.assertTrue(all(len(item["sha256"]) == 64 for item in manifest["artifacts"]))

    def test_missing_converter_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_path, profile = self._files(root)
            step = StepArtifact.from_path(step_path, source={"mode": "browser", "reference": "page"})
            with self.assertRaisesRegex(RuntimeError, "backend is unavailable"):
                build_fdm_package(
                    step,
                    output_dir=root / "package",
                    profile=profile,
                    backends=FdmBackends(UnavailableStepConverter(), FakeAnalyzer(), FakeSlicer()),
                )

    def test_secret_shaped_provenance_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_path, profile = self._files(root)
            step = StepArtifact.from_path(
                step_path,
                source={"mode": "browser", "authorization": "forbidden"},
            )
            with self.assertRaisesRegex(ValueError, "secret-shaped provenance key"):
                build_fdm_package(
                    step,
                    output_dir=root / "package",
                    profile=profile,
                    backends=FdmBackends(FakeConverter(), FakeAnalyzer(), FakeSlicer()),
                )

    def test_workspace_delivery_copies_and_reverifies_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_path, profile = self._files(root)
            step = StepArtifact.from_path(step_path, source={"mode": "browser", "reference": "page"})
            package = build_fdm_package(
                step,
                output_dir=root / "windows-staging",
                profile=profile,
                backends=FdmBackends(FakeConverter(), FakeAnalyzer(), FakeSlicer()),
            )
            target = WorkspaceDeliveryTarget(
                workspace_path=Path(root / "workspace"),
                allowed_workspace_root=Path(root),
                relative_dir=Path("outputs/fdm/job-1"),
                wsl_distribution="Ubuntu",
            )
            result = WslLocalDelivery().deliver(Path(package["manifestPath"]).parent, target)
            delivered_manifest = Path(str(target.destination)) / "manifest.json"
            delivered = json.loads(delivered_manifest.read_text(encoding="utf-8"))
        self.assertTrue(result["delivered"])
        self.assertEqual(result["delivery"], "wsl-local-copy")
        self.assertEqual(delivered["semanticLevel"], "L6")
        self.assertTrue(all(len(item["sha256"]) == 64 for item in result["artifacts"]))

    def test_windows_delivery_maps_wsl_workspace_to_unc(self):
        target = WorkspaceDeliveryTarget(
            workspace_path=Path("/home/user/code/onshapescript"),
            allowed_workspace_root=Path("/home/user/code"),
            relative_dir=Path("outputs/fdm/job-1"),
            wsl_distribution="Ubuntu-24.04",
        )
        unc = WindowsToWslDelivery.unc_path(target.destination, target.wsl_distribution)
        self.assertEqual(
            str(unc),
            r"\\wsl.localhost\Ubuntu-24.04\home\lijq\code\onshapescript\outputs\fdm\job-1",
        )
        with self.assertRaisesRegex(ValueError, "outside the configured allowed root"):
            WorkspaceDeliveryTarget(
                workspace_path=Path("/tmp/escape"),
                allowed_workspace_root=Path("/home/user/code"),
                relative_dir=Path("outputs"),
                wsl_distribution="Ubuntu",
            )

    def test_wsl_execution_maps_only_shared_drive_paths(self):
        execution = WslWindowsExecution()
        self.assertEqual(
            execution.encode_path(Path("/mnt/c/MCP/job/model.stl")),
            r"C:\MCP\job\model.stl",
        )
        self.assertEqual(
            execution.encode_path(Path("/mnt/d/FDM Profiles/process.json")),
            r"D:\FDM Profiles\process.json",
        )
        with self.assertRaisesRegex(ValueError, "requires paths under /mnt"):
            execution.encode_path(Path("/home/user/model.stl"))

    def test_bambu_command_uses_documented_stl_flow_and_argument_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_path, profile = self._files(root)
            executable = root / "bambu-studio"
            executable.write_text("fixture", encoding="ascii")
            mesh_path = root / "mesh.stl"
            mesh_path.write_text("solid fixture\nendsolid fixture\n", encoding="ascii")
            mesh = MeshArtifact.from_path(
                mesh_path,
                units="mm",
                triangle_count=12,
                converter={"name": "fake"},
            )
            backend = BambuStudioBackend(executable, version="fixture-1", execution=ReplayExecution())
            command = backend.build_command(
                mesh,
                profile=profile,
                output_path=root / "out.3mf",
                sliced_data_path=root / "slice-data",
            )
        self.assertIsInstance(command, list)
        self.assertIn("--load-settings", command)
        self.assertIn("--load-filaments", command)
        self.assertIn("--slice", command)
        self.assertIn("--export-3mf", command)
        self.assertIn("--export-slicedata", command)
        self.assertTrue(command[-1].endswith("mesh.stl"))
        self.assertFalse(any(item.endswith(".step") for item in command))


if __name__ == "__main__":
    unittest.main()
