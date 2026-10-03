#!/usr/bin/env python3
"""Offline tests for the STEP tessellation handoff producer.

No CadQuery, no kernel, no browser: the tessellator is injected, so everything tested here is the
producer's own contract -- the plan's refusals, the per-piece record, and the claims the manifest
makes about itself (a digest that is not polluted by triangulation, a `sha256_stable` that carries
evidence, and an `applicable` gate that nulls a quantity rather than caveating it).
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fdm_analysis.conversion import step_tessellation as st  # noqa: E402

#: A closed 10 mm cube, and a 10x10x2 slab: exactly the shapes a handoff carries.
CUBE = [
    ((0, 0, 0), (0, 10, 0), (10, 10, 0)), ((0, 0, 0), (10, 10, 0), (10, 0, 0)),
    ((0, 0, 10), (10, 10, 10), (0, 10, 10)), ((0, 0, 10), (10, 0, 10), (10, 10, 10)),
    ((0, 0, 0), (10, 0, 0), (10, 0, 10)), ((0, 0, 0), (10, 0, 10), (0, 0, 10)),
    ((10, 0, 0), (10, 10, 0), (10, 10, 10)), ((10, 0, 0), (10, 10, 10), (10, 0, 10)),
    ((10, 10, 0), (0, 10, 0), (0, 10, 10)), ((10, 10, 0), (0, 10, 10), (10, 10, 10)),
    ((0, 10, 0), (0, 0, 0), (0, 0, 10)), ((0, 10, 0), (0, 0, 10), (0, 10, 10)),
]


def write_stl(path: Path, triangles) -> None:
    lines = ["solid test"]
    for a, b, c in triangles:
        lines.append("facet normal 0 0 0")
        lines.append("  outer loop")
        for point in (a, b, c):
            lines.append(f"    vertex {point[0]} {point[1]} {point[2]}")
        lines.append("  endloop")
        lines.append("endfacet")
    lines.append("endsolid test")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def cube_with_inverted_face():
    triangles = list(CUBE)
    triangles[0] = (triangles[0][0], triangles[0][2], triangles[0][1])
    return triangles


class FakeTessellator:
    """Writes real STL bytes; can deliberately differ between runs and never creates the directory."""

    def __init__(self, *, solids=None, vary_second_run=False, empty=False):
        self.solids = solids if solids is not None else [CUBE, CUBE]
        self.vary_second_run = vary_second_run
        self.empty = empty
        self.calls = 0

    def __call__(self, step_path, output_dir, *, linear_tolerance_mm, angular_tolerance_rad, **_):
        self.calls += 1
        output_dir = Path(output_dir)
        # The producer, not the tessellator, must create the directory (a real CadQuery export into a
        # missing directory writes NOTHING and reports no error).
        assert output_dir.is_dir(), "producer must create the tessellator's output directory"
        if self.empty:
            return {"parts": [], "kernel": {"name": "fake", "version": "1"}, "used": {}}
        parts = []
        for index, triangles in enumerate(self.solids):
            if self.vary_second_run and self.calls > 1:
                triangles = triangles + [((0, 0, 0), (0, 0, 0), (0, 0, 0))]
            path = output_dir / f"part-{index:04d}.stl"
            write_stl(path, triangles)
            parts.append({
                "index": index,
                "path": str(path),
                "brepVolumeMm3": 1000.0 - index,
                "brepBoundsMm": {"min": [0.0, 0.0, 0.0], "max": [10.0, 10.0, 10.0],
                                 "size": [10.0, 10.0, 10.0]},
            })
        return {
            "parts": parts,
            "kernel": {"name": "fake-kernel", "version": "1.2.3"},
            "used": {"linear_tolerance_mm": linear_tolerance_mm,
                     "angular_tolerance_rad": angular_tolerance_rad},
            "call": f"fake(tolerance={linear_tolerance_mm}, angularTolerance={angular_tolerance_rad})",
        }


class PlanTest(unittest.TestCase):
    def _step(self, tmp: Path) -> Path:
        path = tmp / "handoff.step"
        path.write_bytes(b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n")
        return path

    def test_plan_reads_the_source_without_a_kernel(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._step(Path(tmp))
            plan = st.plan_step_tessellation(
                step_path=path, output_dir=Path(tmp) / "out", declared_by="cadq", used_by="meshq"
            )
            size = path.stat().st_size
        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["schema"], st.SCHEMA)
        self.assertEqual(plan["source"]["byteCount"], size)
        self.assertFalse(plan["source"]["sha256Stable"])
        self.assertEqual(plan["tessellation"]["declared"]["linear_tolerance_mm"],
                         st.DEFAULT_LINEAR_TOLERANCE_MM)
        self.assertIn("never silently", " ".join(plan["refusalRules"]))

    def test_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._step(Path(tmp))
            base = {"step_path": path, "output_dir": Path(tmp) / "out"}
            with self.assertRaisesRegex(ValueError, "missing"):
                st.plan_step_tessellation(**{**base, "step_path": Path(tmp) / "no.step",
                                             "declared_by": "a", "used_by": "b"})
            other = Path(tmp) / "x.igs"
            other.write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "step or .stp"):
                st.plan_step_tessellation(**{**base, "step_path": other, "declared_by": "a", "used_by": "b"})
            with self.assertRaisesRegex(ValueError, "tolerances must be positive"):
                st.plan_step_tessellation(**base, declared_by="a", used_by="b", linear_tolerance_mm=0)
            with self.assertRaisesRegex(ValueError, "declared_by is required"):
                st.plan_step_tessellation(**base, declared_by=" ", used_by="b")
            with self.assertRaisesRegex(ValueError, "used_by is required"):
                st.plan_step_tessellation(**base, declared_by="a", used_by="")


class ManifestTest(unittest.TestCase):
    def _run(self, tmp: Path, tessellator=None, **kwargs):
        step = tmp / "handoff.step"
        step.write_bytes(b"ISO-10303-21;\n")
        return st.tessellate_step(
            step_path=step,
            output_dir=tmp / "out",
            declared_by="cadq",
            used_by="meshq",
            export_id="run-1",
            tessellator=tessellator or FakeTessellator(),
            now="2026-10-03T00:00:00+00:00",
            quota_remaining=2380,
            **kwargs,
        )

    def test_the_manifest_carries_the_agreed_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._run(Path(tmp))
        declaration = manifest["declaration"]
        self.assertEqual(manifest["schema"], st.SCHEMA)
        self.assertEqual(declaration["geometry"]["solid_count"], 2)
        self.assertEqual(len(declaration["geometry"]["parts"]), 2)
        piece = declaration["geometry"]["parts"][0]
        for key in ("index", "bounds_mm", "volume_mm3", "applicable", "brep", "mesh",
                    "cross_plane_ref", "selectors"):
            self.assertIn(key, piece)
        self.assertEqual(piece["mesh"]["representation"], "stl_triangulation")
        self.assertEqual(piece["mesh"]["triangleCount"], 12)
        self.assertEqual(piece["cross_plane_ref"]["export_id"], "run-1")
        self.assertEqual(declaration["tessellation"]["kernel"],
                         {"name": "fake-kernel", "version": "1.2.3"})
        self.assertTrue(declaration["tessellation"]["matches_declaration"])
        self.assertIsNone(declaration["tessellation"]["deviation_reason"])
        self.assertEqual(manifest["cost"]["where"]["estimated_requests"], 0)
        self.assertEqual(manifest["cost"]["where"]["spent_quota"], 0)
        self.assertEqual(manifest["units"], "mm")

    def test_the_set_digest_is_over_exact_readings_only(self):
        """Two triangulations of one geometry must not change the digest (CadQ's rule)."""
        with tempfile.TemporaryDirectory() as tmp:
            first = self._run(Path(tmp), tessellator=FakeTessellator(vary_second_run=True))
        with tempfile.TemporaryDirectory() as tmp:
            second = self._run(Path(tmp), tessellator=FakeTessellator(vary_second_run=True))
        # The mesh bytes differ between the two runs of each call, so triangle counts differ...
        self.assertNotEqual(first["totals"]["triangleCount"], 0)
        # ...while the exact readings are identical, so the set digest is identical.
        self.assertEqual(first["declaration"]["identity"]["sha256"],
                         second["declaration"]["identity"]["sha256"])
        self.assertEqual(first["declaration"]["identity"]["sha256"],
                         first["declaration"]["geometry"]["identity_rule"]["set_signature_sha256"])

    def test_sha256_stability_is_evidence_not_an_assumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            stable = self._run(Path(tmp))
        with tempfile.TemporaryDirectory() as tmp:
            unstable = self._run(Path(tmp), tessellator=FakeTessellator(vary_second_run=True))
        piece = stable["declaration"]["geometry"]["parts"][0]["mesh"]
        self.assertTrue(piece["sha256_stable"])
        self.assertEqual(len(piece["sha256_evidence"]), 2)
        self.assertEqual(piece["sha256_evidence"][0], piece["sha256"])
        self.assertTrue(stable["declaration"]["identity"]["sha256_stable"])
        self.assertEqual(stable["reproducibility"]["unstablePieces"], [])
        self.assertFalse(unstable["declaration"]["identity"]["sha256_stable"])
        self.assertEqual(unstable["reproducibility"]["unstablePieces"], [0, 1])

    def test_the_reproducibility_mirror_is_created_by_the_producer(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._run(Path(tmp))
            self.assertTrue((Path(tmp) / "out" / "reproducibility").is_dir())

    def test_an_inconsistent_winding_nulls_only_the_winding_dependent_readings(self):
        """The gate is by NATURE. MeshQ disproved the first version of this rule with three variants.

        Area is Sigma|A_i|, so the winding never enters it: their clean cube, the same cube with two
        bottom faces flipped, and that mesh shifted +Z 50 all report `surface_area_mm2 = 2400.0`. A
        rule that turned the area off would reject a number that is still perfectly usable. What DOES
        depend on winding: the signed volume, `outwardOriented`, and every direction-derived reading.
        """
        tessellator = FakeTessellator(solids=[cube_with_inverted_face(), CUBE])
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._run(Path(tmp), tessellator=tessellator)
        piece = manifest["declaration"]["geometry"]["parts"][0]
        self.assertFalse(piece["mesh"]["orientation"]["consistent"])
        # winding-dependent -> null, with the flag
        self.assertFalse(piece["applicable"]["volumeMm3"])
        self.assertIsNone(piece["volume_mm3"])
        self.assertFalse(piece["applicable"]["overhangAreaMm2"])
        self.assertIsNone(piece["mesh"]["overhangAreaMm2"])
        self.assertIsNone(piece["mesh"]["overhangTriangleCount"])
        self.assertIsNone(piece["mesh"]["overhangTriangleRatio"])
        self.assertIn("direction-derived", piece["mesh"]["notApplicableReason"])
        # winding-INDEPENDENT -> still readable, and it must stay readable
        self.assertEqual(piece["area_mm2"], 600.0)
        self.assertTrue(piece["applicable"]["areaMm2"])
        self.assertEqual(piece["mesh"]["triangleCount"], 12)
        self.assertEqual(piece["mesh"]["orientation"]["inconsistentEdgePairs"], 3)
        # ...and the clean piece is unaffected: the gate is per piece, not global.
        other = manifest["declaration"]["geometry"]["parts"][1]
        self.assertIsNotNone(other["volume_mm3"])
        self.assertIsNotNone(other["mesh"]["overhangAreaMm2"])
        self.assertEqual(other["mesh"]["overhangTriangleRatio"], round(2 / 12, 12))

    def test_every_total_states_how_many_pieces_contributed(self):
        tessellator = FakeTessellator(solids=[cube_with_inverted_face(), CUBE])
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._run(Path(tmp), tessellator=tessellator)
        totals = manifest["totals"]
        self.assertEqual(totals["pieces"], 2)
        self.assertEqual(totals["contributingPieces"]["areaMm2"], 2)
        self.assertEqual(totals["contributingPieces"]["overhang"], 1)
        self.assertEqual(totals["triangleCount"], 24)
        self.assertEqual(totals["overhangTriangleRatio"], round(2 / 24, 12))

    def test_the_mesh_is_cross_checked_against_the_exact_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._run(Path(tmp))
        piece = manifest["declaration"]["geometry"]["parts"][0]
        self.assertEqual(piece["boundsDeltaMm"], 0.0)
        self.assertEqual(piece["bounds_mm"], piece["brep"]["bounds_mm"])
        self.assertEqual(manifest["declaration"]["mesh"]["pieces"][0]["path"], "part-0000.stl")

    def test_an_empty_tessellation_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "no parts"):
                self._run(Path(tmp), tessellator=FakeTessellator(empty=True))

    def test_a_misdeclared_kernel_is_recorded_not_hidden(self):
        class Lying(FakeTessellator):
            def __call__(self, *args, **kwargs):
                built = super().__call__(*args, **kwargs)
                built["used"] = {"linear_tolerance_mm": 0.02, "angular_tolerance_rad": 0.1}
                return built

        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._run(Path(tmp), tessellator=Lying())
        record = manifest["declaration"]["tessellation"]
        self.assertFalse(record["matches_declaration"])
        self.assertIsNotNone(record["deviation_reason"])
        self.assertEqual(record["declared"]["linear_tolerance_mm"], 0.05)
        self.assertEqual(record["used"]["linear_tolerance_mm"], 0.02)

    def test_the_kernel_is_never_claimed_independent_by_accident(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._run(Path(tmp))
        record = manifest["declaration"]["tessellation"]
        self.assertFalse(record["independent_kernel"])
        self.assertIn("NOT an independent kernel", record["kernel_note"])
        with tempfile.TemporaryDirectory() as tmp:
            owned = self._run(Path(tmp), independent_kernel=True)
        self.assertTrue(owned["declaration"]["tessellation"]["independent_kernel"])

    def test_writing_the_manifest_produces_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._run(Path(tmp))
            path = st.write_handoff_manifest(manifest, Path(tmp) / "out" / "manifest.json")
            reloaded = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(reloaded["schema"], st.SCHEMA)
        self.assertEqual(reloaded["declaration"]["geometry"]["solid_count"], 2)


if __name__ == "__main__":
    unittest.main()
