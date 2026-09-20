#!/usr/bin/env python3
"""Read a STEP file's exact B-rep and report its geometry fingerprint.

WHY IT EXISTS: a mesh is not a correctness proof. The geometry package this
repository builds samples triangles, and a WRONG part (sharp outer corners, no
draft anywhere) still tessellated to `watertight: true` with `[84, 84, 10] mm` and
a plausible volume. A B-rep face inventory is what actually distinguishes an R4
outer corner from a sharp one and a 45 deg cone from a flat wall, so the numbers
below come from the STEP's topology rather than from any tessellation.

WHAT IT REPORTS: volume, surface area, bounding box, face count, and the face
families grouped by kind (plane / cylinder / cone / torus / sphere) and by the
measure that matters for that kind -- radius for cylinders and tori, semi-angle for
cones -- each with its count, total area, and the face's own z interval, plus the z
levels of the horizontal planes. JSON on stdout, so two models can be diffed.

INTERPRETER: this needs an OpenCascade Python binding, which is NOT a repository
dependency and must never be installed by a tool. An adjacent CadQuery/OCP
environment is the detected candidate (this repository already field-validates
CadQuery 2.8.0 / OCP 7.9.3.1 as the STEP backend; see
`docs/roadmap/BROWSER_MODELING_GAPS.md` section 2). Point it at that interpreter:

    /path/to/cadquery-venv/bin/python onshape_docs/scripts/verify_step_brep.py model.step

Absent that interpreter, report the requirement and stop; do not install one.
Worked example with its expected fingerprint:
`onshape_docs/verification/thin-feature-rebuild-brep-2026-09-21.md`.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GeomAbs import (
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_Plane,
    GeomAbs_Sphere,
    GeomAbs_Torus,
)
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt


def load(path: str):
    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise SystemExit(f"STEP file could not be read: {path}")
    reader.TransferRoots()
    return reader.OneShape()


def face_area(face) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return props.Mass()


def face_z_span(face) -> tuple[float, float]:
    """The face's own bounding-box z range: which slice of the part this face is."""
    box = Bnd_Box()
    BRepBndLib.Add_s(face, box)
    _xmin, _ymin, zmin, _xmax, _ymax, zmax = box.Get()
    return zmin, zmax


def describe(face) -> tuple[str, float, dict]:
    surface = BRepAdaptor_Surface(face)
    kind = surface.GetType()
    if kind == GeomAbs_Plane:
        plane = surface.Plane()
        normal = plane.Axis().Direction()
        return "plane", 0.0, {
            "normal": [round(normal.X(), 6), round(normal.Y(), 6), round(normal.Z(), 6)],
        }
    if kind == GeomAbs_Cylinder:
        cylinder = surface.Cylinder()
        return "cylinder", surface.Cylinder().Radius(), {
            "axis": [
                round(cylinder.Axis().Direction().X(), 6),
                round(cylinder.Axis().Direction().Y(), 6),
                round(cylinder.Axis().Direction().Z(), 6),
            ],
        }
    if kind == GeomAbs_Cone:
        cone = surface.Cone()
        # Semi-angle from the axis: the angle a Gridfinity 45 deg ramp shows here.
        return "cone", math.degrees(cone.SemiAngle()), {
            "refRadius": round(cone.RefRadius(), 6),
        }
    if kind == GeomAbs_Torus:
        torus = surface.Torus()
        return "torus", torus.MinorRadius(), {"majorRadius": round(torus.MajorRadius(), 6)}
    if kind == GeomAbs_Sphere:
        return "sphere", surface.Sphere().Radius(), {}
    return f"other({kind})", 0.0, {}


def main() -> int:
    path = sys.argv[1]
    shape = load(path)

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    surface_props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, surface_props)
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    families: dict[tuple[str, float], dict] = {}
    z_levels: Counter = Counter()
    face_count = 0
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        face_count += 1
        kind, measure, extra = describe(face)
        area = face_area(face)
        # Cones are also split by their reference radius: a socket ramp cone and a
        # magnet mouth chamfer share the 45 deg semi-angle but nothing else.
        key = (kind, round(measure, 4), round(float(extra.get("refRadius", -1.0)), 4))
        entry = families.setdefault(
            key,
            {
                "count": 0,
                "areaMm2": 0.0,
                "measure": round(measure, 4),
                "zMin": None,
                "zMax": None,
                **extra,
            },
        )
        entry["count"] += 1
        entry["areaMm2"] = round(entry["areaMm2"] + area, 4)
        zmin_face, zmax_face = face_z_span(face)
        entry["zMin"] = zmin_face if entry["zMin"] is None else min(entry["zMin"], zmin_face)
        entry["zMax"] = zmax_face if entry["zMax"] is None else max(entry["zMax"], zmax_face)
        if kind == "plane" and abs(extra["normal"][2]) > 0.999:
            # A horizontal plane's z is read from its own face, not from the bbox.
            surface = BRepAdaptor_Surface(face)
            z_levels[round(surface.Plane().Location().Z(), 4)] += 1
        explorer.Next()

    report = {
        "step": path,
        "volumeMm3": round(props.Mass(), 4),
        "surfaceAreaMm2": round(surface_props.Mass(), 4),
        "boundingBoxMm": {
            "x": [round(xmin, 4), round(xmax, 4)],
            "y": [round(ymin, 4), round(ymax, 4)],
            "z": [round(zmin, 4), round(zmax, 4)],
        },
        "faceCount": face_count,
        "families": [
            {"kind": key[0], **entry}
            for key, entry in sorted(families.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
        ],
        "horizontalPlaneZs": sorted(z_levels),
    }
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
