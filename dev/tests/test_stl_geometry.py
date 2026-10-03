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

    def test_counts_are_published_next_to_the_areas(self):
        """A bare `faces` field is two units across implementations; publish both readings."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cube.stl"
            write_ascii_stl(path)
            result = StlGeometryAnalyzer().analyze(
                self._mesh(path),
                orientation_matrix=(1, 0, 0, 0, 1, 0, 0, 0, 1),
            )
        # The 10 mm cube's bottom face is 2 triangles here and 1 planar face in a mesh kernel.
        self.assertEqual(result["bedContactTriangleCount"], 2)
        self.assertEqual(result["overhangTriangleCount"], 2)
        self.assertEqual(result["triangleCount"], 12)
        self.assertEqual(result["facesWithoutNormal"], 0)
        self.assertEqual(
            result["orientation"],
            {
                "consistent": True,
                "inconsistentEdgePairs": 0,
                "inconsistentFaceIndices": [],
                "nonManifoldEdges": 0,
                "checkedEdges": 18,
            },
        )
        self.assertTrue(result["outwardOriented"])

    def test_orientation_check_locates_an_inverted_face(self):
        """Watertight and outward are not the same as consistently wound.

        Measured live on a cross-plane face-off: an analyzer without this check read an
        inward-wound sloped face as an overhang and returned 965.19 mm2 where the geometry
        has no overhang face at all. The check must name the faces, because a bare count
        cannot be acted on.
        """
        triangles = list(CUBE_TRIANGLES)
        triangles[0] = (triangles[0][0], triangles[0][2], triangles[0][1])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inverted.stl"
            write_ascii_stl(path, triangles)
            result = StlGeometryAnalyzer().analyze(
                self._mesh(path),
                orientation_matrix=(1, 0, 0, 0, 1, 0, 0, 0, 1),
            )
        self.assertTrue(result["watertight"], "a consistently wound mesh becomes an inconsistent one, not an open one")
        self.assertFalse(result["orientation"]["consistent"])
        self.assertEqual(result["orientation"]["inconsistentEdgePairs"], 3)
        self.assertEqual(result["orientation"]["inconsistentFaceIndices"], [0, 1, 7, 9])
        # ... and the volume is blind to it *here*: that face lies in the z=0 plane, so its tetrahedron
        # with the origin is degenerate. The blindness is CONDITIONAL, not general -- MeshQ measured
        # the same defect on a cube at +Z 50 mm as 21333.333333, matching 8000 - 2*c_f exactly. So the
        # rule is "the observability of a defect depends on where the part sits", and orientation state
        # must never be inferred from a volume. This is why an orientation check must exist next to a
        # volume, and why `outwardOriented` alone is not enough (it only sees a globally flipped mesh,
        # which this is not).
        self.assertEqual(result["volumeMm3"], 1000.0)
        self.assertTrue(result["outwardOriented"])

    def test_a_face_without_a_usable_normal_is_counted_not_dropped(self):
        triangles = list(CUBE_TRIANGLES) + [((0, 0, 0), (1, 0, 0), (2, 0, 0))]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "degenerate.stl"
            write_ascii_stl(path, triangles)
            result = StlGeometryAnalyzer().analyze(
                self._mesh(path, count=len(triangles)),
                orientation_matrix=(1, 0, 0, 0, 1, 0, 0, 0, 1),
            )
        # "not measured" must not read as "self-supporting": the face is reported, not skipped.
        self.assertEqual(result["facesWithoutNormal"], 1)
        self.assertEqual(result["overhangTriangleCount"], 2)
        self.assertFalse(result["watertight"])

    def test_outward_orientation_is_null_when_it_cannot_be_judged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "triangle.stl"
            write_ascii_stl(path, [CUBE_TRIANGLES[0]])
            result = StlGeometryAnalyzer().analyze(
                self._mesh(path, count=1),
                orientation_matrix=(1, 0, 0, 0, 1, 0, 0, 0, 1),
            )
        self.assertFalse(result["watertight"])
        self.assertIsNone(result["outwardOriented"], "an open mesh cannot be called outward-oriented")
        self.assertEqual(result["orientation"]["checkedEdges"], 3)
        self.assertEqual(result["bedContactTriangleCount"], 1)


if __name__ == "__main__":
    unittest.main()
