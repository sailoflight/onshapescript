from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from fdm_analysis import MeshArtifact
from fdm_analysis.metrics import StlGeometryAnalyzer


CUBE_TRIANGLES = [
    ((0, 0, 0), (0, 10, 0), (10, 10, 0)),
    ((0, 0, 0), (10, 10, 0), (10, 0, 0)),
    ((0, 0, 10), (10, 0, 10), (10, 10, 10)),
    ((0, 0, 10), (10, 10, 10), (0, 10, 10)),
    ((0, 0, 0), (10, 0, 0), (10, 0, 10)),
    ((0, 0, 0), (10, 0, 10), (0, 0, 10)),
    ((0, 10, 0), (0, 10, 10), (10, 10, 10)),
    ((0, 10, 0), (10, 10, 10), (10, 10, 0)),
    ((0, 0, 0), (0, 0, 10), (0, 10, 10)),
    ((0, 0, 0), (0, 10, 10), (0, 10, 0)),
    ((10, 0, 0), (10, 10, 0), (10, 10, 10)),
    ((10, 0, 0), (10, 10, 10), (10, 0, 10)),
]


def write_ascii_stl(path: Path, triangles=CUBE_TRIANGLES) -> None:
    lines = ["solid fixture"]
    for triangle in triangles:
        lines.extend(("facet normal 0 0 0", "outer loop"))
        lines.extend(f"vertex {x} {y} {z}" for x, y, z in triangle)
        lines.extend(("endloop", "endfacet"))
    lines.append("endsolid fixture")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


class StlGeometryAnalyzerTest(unittest.TestCase):
    def _mesh(self, path: Path, *, units="mm", count=12):
        return MeshArtifact.from_path(
            path,
            units=units,
            triangle_count=count,
            converter={"name": "fixture"},
        )

    def test_ascii_cube_metrics_are_geometric_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cube.stl"
            write_ascii_stl(path)
            result = StlGeometryAnalyzer().analyze(
                self._mesh(path),
                orientation_matrix=(1, 0, 0, 0, 1, 0, 0, 0, 1),
            )
        self.assertTrue(result["watertight"])
        self.assertEqual(result["dimensionsMm"], [10.0, 10.0, 10.0])
        self.assertEqual(result["printHeightMm"], 10.0)
        self.assertEqual(result["bedContactAreaMm2"], 100.0)
        self.assertEqual(result["overhangAreaMm2"], 100.0)
        self.assertEqual(result["volumeMm3"], 1000.0)
        self.assertEqual(result["centerOfMassMm"], [5.0, 5.0, 5.0])
        self.assertTrue(result["centerOfMassStable"])
        self.assertIsNone(result["wallThicknessMm"])
        self.assertEqual(result["analyzer"]["overhangPolicy"]["fromVerticalDegrees"], 45.0)

    def test_binary_stl_is_parsed_and_open_mesh_fails_watertight(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "triangle.stl"
            header = b"fixture".ljust(80, b"\0")
            triangle = struct.pack(
                "<12fH",
                0, 0, 1,
                0, 0, 0,
                10, 0, 0,
                0, 10, 0,
                0,
            )
            path.write_bytes(header + struct.pack("<I", 1) + triangle)
            result = StlGeometryAnalyzer().analyze(
                self._mesh(path, count=1),
                orientation_matrix=(1, 0, 0, 0, 1, 0, 0, 0, 1),
            )
        self.assertFalse(result["watertight"])
        self.assertEqual(result["triangleCount"], 1)
        self.assertIsNone(result["centerOfMassStable"])

    def test_units_matrix_and_threshold_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cube.stl"
            write_ascii_stl(path)
            analyzer = StlGeometryAnalyzer()
            with self.assertRaisesRegex(ValueError, "millimeter"):
                analyzer.analyze(
                    self._mesh(path, units="inch"),
                    orientation_matrix=(1, 0, 0, 0, 1, 0, 0, 0, 1),
                )
            with self.assertRaisesRegex(ValueError, "nine finite"):
                analyzer.analyze(self._mesh(path), orientation_matrix=(1, 0, 0))
        with self.assertRaisesRegex(ValueError, "between 0 and 90"):
            StlGeometryAnalyzer(overhang_from_vertical_degrees=90)


if __name__ == "__main__":
    unittest.main()
