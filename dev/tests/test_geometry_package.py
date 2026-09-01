from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dev.tests.test_stl_geometry import write_ascii_stl
from fdm_analysis import GeometryBackends, MeshArtifact, StepArtifact, build_geometry_package
from fdm_analysis.conversion import UnavailableStepConverter
from fdm_analysis.metrics import StlGeometryAnalyzer


class CubeConverter:
    def capabilities(self):
        return {"available": True, "name": "fixture-cube", "version": "1"}

    def convert(self, step, *, output_path, linear_tolerance_mm, angular_tolerance_degrees):
        write_ascii_stl(output_path)
        return MeshArtifact.from_path(
            output_path,
            units="mm",
            triangle_count=12,
            converter={
                "name": "fixture-cube",
                "linearToleranceMm": linear_tolerance_mm,
                "angularToleranceDegrees": angular_tolerance_degrees,
            },
        )


class EscapingConverter(CubeConverter):
    def __init__(self, path):
        self.path = path

    def convert(self, step, *, output_path, linear_tolerance_mm, angular_tolerance_degrees):
        return super().convert(
            step,
            output_path=self.path,
            linear_tolerance_mm=linear_tolerance_mm,
            angular_tolerance_degrees=angular_tolerance_degrees,
        )


class GeometryPackageTest(unittest.TestCase):
    def _step(self, root: Path, source=None):
        path = root / "source.step"
        path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="ascii")
        return StepArtifact.from_path(
            path,
            units="mm",
            source=source or {"mode": "rest", "reference": "translation1"},
        )

    def test_geometry_recipe_produces_independent_l6_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = build_geometry_package(
                self._step(root),
                output_dir=root / "package",
                backends=GeometryBackends(CubeConverter(), StlGeometryAnalyzer()),
            )
            manifest = json.loads(Path(result["manifestPath"]).read_text(encoding="utf-8"))
            report = json.loads(Path(result["reportPath"]).read_text(encoding="utf-8"))
        self.assertTrue(result["packaged"])
        self.assertEqual(result["semanticLevel"], "L6")
        self.assertEqual(result["deliverableType"], "geometry-analysis-package")
        self.assertEqual(result["assessment"]["state"], "complete")
        self.assertIsNone(result["assessment"]["pass"])
        self.assertEqual(manifest["semanticLevel"], "L6")
        self.assertEqual(
            {artifact["path"] for artifact in manifest["artifacts"]},
            {"model.step", "model.stl", "report.json", "report.md"},
        )
        self.assertTrue(all(len(artifact["sha256"]) == 64 for artifact in manifest["artifacts"]))
        self.assertIsNone(report["geometry"]["wallThicknessMm"])
        self.assertNotIn("slicer", manifest["backends"])

    def test_unavailable_converter_fails_closed_before_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(RuntimeError, "converter backend is unavailable"):
                build_geometry_package(
                    self._step(root),
                    output_dir=root / "package",
                    backends=GeometryBackends(UnavailableStepConverter(), StlGeometryAnalyzer()),
                )

    def test_converter_cannot_escape_package_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "inside the geometry package"):
                build_geometry_package(
                    self._step(root),
                    output_dir=root / "package",
                    backends=GeometryBackends(
                        EscapingConverter(root / "outside.stl"),
                        StlGeometryAnalyzer(),
                    ),
                )

    def test_secret_shaped_step_provenance_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "secret-shaped provenance key"):
                build_geometry_package(
                    self._step(root, {"mode": "rest", "token": "forbidden"}),
                    output_dir=root / "package",
                    backends=GeometryBackends(CubeConverter(), StlGeometryAnalyzer()),
                )


if __name__ == "__main__":
    unittest.main()
