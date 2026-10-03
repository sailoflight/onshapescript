"""Tessellate a multi-solid STEP into one STL per solid plus a v0.4 cross-plane record.

This is a **producer** module: it writes the artifacts and the manifest that the other two planes
read, so its two jobs are kept apart on purpose.

1. The **tessellator** is injected. ``cadquery_tessellator`` is the real one (it needs CadQuery and
   therefore is not imported here at module scope); tests inject a fake, so the whole manifest
   assembly is exercised offline, with no kernel and no browser.
2. The **measurement** of each written STL happens in this module, not in the tessellator: the digest,
   the triangle count, the area, the orientation check and the counted triangle sets all come from
   ``fdm_analysis.metrics.stl_geometry``. A kernel that also reported these numbers would be
   reporting its own work, which is exactly the failure mode this repository keeps re-learning.

The cross-plane rules implemented here (agreed over the agent mailbox; see
``docs/roadmap/THREE_PLANE_HANDOFF_SCHEMA_DRAFT.md`` v0.4):

* ``tessellation.declared`` vs ``.used``, with ``matches_declaration`` computed by the producer and a
  mandatory ``deviation_reason`` when they differ. A declaration with no receipt is decorative.
* ``kernel{name, version}`` — and an explicit ``independent_kernel`` flag. A reading taken with
  another plane's interpreter is a **rule-level reproduction, not an independent kernel**; saying so
  in the record is cheaper than having the reader assume otherwise (that mistake was made once).
* per-piece identity: ``bounds_mm{min,max,size}``, the exact (B-Rep) volume, and a
  ``cross_plane_ref`` index. Parts are addressed by ``identity_rule`` (sorted multiset, relative
  tolerance), never by row order, because a re-export can reorder solids silently.
* ``sha256`` per piece **with evidence** when ``sha256_stable`` is true: the digest is recorded twice
  from two independent tessellations, so the claim has a receipt rather than an assumption.
* ``applicable``: a quantity that is not physically meaningful in the reported state is emitted as
  ``null`` with ``applicable: false`` and a reason, so a reader cannot read it wrongly.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

from fdm_analysis.contracts import MeshArtifact
from fdm_analysis.metrics.stl_geometry import StlGeometryAnalyzer, read_stl

SCHEMA = "onshapescript.handoff/0.4-draft"
DEFAULT_LINEAR_TOLERANCE_MM = 0.05
DEFAULT_ANGULAR_TOLERANCE_RAD = 0.1
OVERHANG_FROM_VERTICAL_DEGREES = 45.0
#: The reference point used by a signed-volume reading. Recorded because a flipped face is invisible
#: to the volume *iff* that face's plane contains it (measured: 8000.0 -> 8000.0 at z=0, 21333.333333
#: after a +Z 50 shift). The origin is what both this repository and MeshQ use.
INTEGRATION_REFERENCE = "origin"

Tessellator = Callable[..., dict[str, Any]]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _size(bounds: dict[str, list[float]]) -> list[float]:
    return [round(bounds["max"][i] - bounds["min"][i], 9) for i in range(3)]


def measure_stl(
    path: str | Path,
    *,
    units: str = "mm",
    overhang_from_vertical_degrees: float = OVERHANG_FROM_VERTICAL_DEGREES,
) -> dict[str, Any]:
    """Measure one STL. The kernel is not consulted; the bytes are."""
    resolved = Path(path)
    payload = resolved.read_bytes()
    triangles = read_stl(resolved)
    analyzer = StlGeometryAnalyzer(overhang_from_vertical_degrees=overhang_from_vertical_degrees)
    artifact = MeshArtifact.from_path(
        resolved, units=units, triangle_count=len(triangles), converter={"name": "step_tessellation"}
    )
    reading = analyzer.analyze(artifact, orientation_matrix=(1, 0, 0, 0, 1, 0, 0, 0, 1))
    orientation = reading["orientation"]
    xs = [point[0] for triangle in triangles for point in triangle]
    ys = [point[1] for triangle in triangles for point in triangle]
    zs = [point[2] for triangle in triangles for point in triangle]
    mesh_bounds = {"min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]} if triangles else None
    if mesh_bounds is not None:
        mesh_bounds["size"] = _size(mesh_bounds)
    # `applicable` is derived BY NATURE, never by field name. Two classes, measured:
    #   * winding-DEPENDENT: a signed quantity, `outwardOriented`, and every direction-derived reading
    #     (overhang area/count, tilt). MeshQ's three variants show the volume is unchanged at z=0 and
    #     21333.333333 after a +Z 50 shift; this repository's own retracted ramp shows the counted
    #     overhang area moving 0.0 -> 565.192416792 when one slope is wound the other way.
    #   * winding-INDEPENDENT: `area_mm2` is Sigma|A_i|, so the winding never enters (MeshQ measured
    #     2400.0 on all three variants), and counts/bounds are unaffected too. Turning those off would
    #     reject numbers that are still perfectly usable -- "a field that needlessly turns itself off is
    #     waste; one that should have turned itself off and did not is an error".
    signed_readable = bool(reading["watertight"]) and bool(orientation["consistent"])
    # A winding check on a non-closed edge graph is vacuous, so `applicable` (not `consistent`) is what
    # gates the direction-derived readings too.
    direction_readable = bool(orientation.get("applicable", True)) and bool(orientation["consistent"])
    reason = None
    if not reading["watertight"]:
        reason = ("not watertight: the edge graph is not a closed 2-manifold, so a signed quantity is not "
                  "defined and a winding check over it would prove nothing")
    elif not signed_readable:
        reason = ("the winding is inconsistent, so a signed or direction-derived quantity is not "
                  "physically meaningful")
    elif not direction_readable:  # pragma: no cover - unreachable while signed_readable implies it
        reason = "the winding is inconsistent"
    return {
        "path": str(resolved),
        "sha256": _sha256_bytes(payload),
        "byteCount": len(payload),
        "triangleCount": len(triangles),
        "meshBoundsMm": mesh_bounds,
        "watertight": reading["watertight"],
        "areaMm2": reading["surfaceAreaMm2"],
        "volumeMm3": reading["volumeMm3"],
        "overhangAreaMm2": reading["overhangAreaMm2"],
        "overhangTriangleCount": reading["overhangTriangleCount"],
        "overhangTriangleRatio": reading["overhangTriangleRatio"],
        "bedContactAreaMm2": reading["bedContactAreaMm2"],
        "bedContactTriangleCount": reading["bedContactTriangleCount"],
        "bedContactTriangleRatio": reading["bedContactTriangleRatio"],
        "facesWithoutNormal": reading["facesWithoutNormal"],
        "orientation": orientation,
        "outwardOriented": reading["outwardOriented"],
        "applicable": {
            "volumeMm3": signed_readable,
            # Sigma|A_i|: always defined, and one of the few readings still usable on an
            # inconsistently wound mesh. Gating it was a contract defect, caught by MeshQ.
            "areaMm2": True,
            "outwardOriented": signed_readable,
            "overhangAreaMm2": direction_readable,
            "overhangTriangleCount": direction_readable,
            "bedContactAreaMm2": direction_readable,
            "bedContactTriangleCount": direction_readable,
            "orientation": True,
        },
        "notApplicableReason": reason,
    }


def kernel_facts() -> dict[str, Any]:
    """Probe the installed kernel. Never guesses a version: an unknown stays unknown."""
    facts: dict[str, Any] = {"name": "cadquery+OCP", "version": None, "cadquery": None, "occt": None}
    try:
        import cadquery as cq
    except Exception:
        return facts
    facts["cadquery"] = getattr(cq, "__version__", None)
    try:
        import OCP  # type: ignore

        facts["occt"] = getattr(OCP, "__version__", None)
        if facts["occt"] is None:
            from OCP.Standard import Standard_Version  # type: ignore

            facts["occt"] = Standard_Version()
    except Exception:
        facts["occt"] = None
    # One kernel, one spelling. CadQ wrote `2.8.0+OCCT-7.9.3.1`, this repository wrote
    # `2.8.0+7.9.3.1` -- and "can these two be compared at all" hangs on the kernel identity, so the
    # component is named: `<cadquery>+OCCT-<occt>`, with the prefix added when it is missing.
    occt = str(facts["occt"] or "unknown")
    occt = occt if occt.upper().startswith("OCCT") else f"OCCT-{occt}"
    facts["version"] = f"{facts.get('cadquery') or 'unknown'}+{occt}"
    facts["version_convention"] = "<cadquery-version>+OCCT-<occt-version>"
    return facts



def shape_bounds(shape: Any) -> dict[str, Any]:
    """One exact B-Rep bounding box, with the method it was read by.

    A field name may not carry numbers computed by different methods, and `bounds_mm` had exactly that
    problem: this repository, CadQ and MeshQ each published a different box for the same piece (max gap
    3.19e-2 mm) because "the bounding box" is not one measurement. This helper pins the exact reading and
    its algorithm so a consumer can tell a geometry difference from a method difference.
    """
    try:
        box = shape.BoundingBox()
        bounds = {"min": [box.xmin, box.ymin, box.zmin], "max": [box.xmax, box.ymax, box.zmax]}
        bounds["size"] = _size(bounds)
        return {"brepBoundsMm": bounds, "boundsAlgorithm": "occt_bnd_box(exact_geometry)"}
    except Exception:  # pragma: no cover - a shape that cannot report a box is reported as such
        return {"brepBoundsMm": None, "boundsAlgorithm": None}



def cadquery_tessellator(
    step_path: Path,
    output_dir: Path,
    *,
    linear_tolerance_mm: float,
    angular_tolerance_rad: float,
    name_prefix: str = "part",
) -> dict[str, Any]:
    """Export one STL per solid. The only function here that needs CadQuery."""
    import cadquery as cq

    output_dir = Path(output_dir)
    # CadQuery's exporter writes NOTHING into a missing directory (measured: the reproducibility run
    # handed it `<dir>/reproducibility`, which did not exist yet, and every export silently produced no
    # file). The producer therefore owns directory creation on both the primary and the mirror path.
    output_dir.mkdir(parents=True, exist_ok=True)
    shapes = cq.importers.importStep(str(step_path), unit="MM").vals()
    if not shapes:
        raise ValueError("STEP import produced no shapes")
    parts: list[dict[str, Any]] = []
    for index, shape in enumerate(shapes):
        path = output_dir / f"{name_prefix}-{index:04d}.stl"
        # MEASURED (2026-10-03): exporting the STL MUTATES the shape's cached bounds, so the exact
        # reading must be taken BEFORE the export or it is not the exact reading. Same shape, same
        # process: ymax 380.0000001000 -> 380.0008703904 (#0), xmin 7.5000000000 -> 7.4995117079 (#2).
        # The post-export box is the mesh-influenced one MeshQ found in no other implementation's
        # family; it is kept as `boundsAfterTessellationMm` so the mutation is visible, not hidden.
        before = shape_bounds(shape)
        cq.exporters.export(
            shape,
            str(path),
            exportType="STL",
            tolerance=linear_tolerance_mm,
            angularTolerance=angular_tolerance_rad,
        )
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"STL export produced no artifact for solid {index}")
        after = shape_bounds(shape)
        try:
            volume = float(shape.Volume())
        except Exception:
            volume = None
        parts.append({
            "index": index, "path": str(path), "brepVolumeMm3": volume,
            "brepBoundsMm": before["brepBoundsMm"],
            "boundsAlgorithm": before["boundsAlgorithm"],
            "boundsAfterTessellationMm": after["brepBoundsMm"],
            "boundsMutatedByExport": before["brepBoundsMm"] != after["brepBoundsMm"],
        })
    return {
        "parts": parts,
        "kernel": kernel_facts(),
        "used": {"linear_tolerance_mm": linear_tolerance_mm, "angular_tolerance_rad": angular_tolerance_rad},
        "call": (f"cq.exporters.export(shape, path, exportType='STL', tolerance={linear_tolerance_mm}, "
                 f"angularTolerance={angular_tolerance_rad})"),
    }


def plan_step_tessellation(
    *,
    step_path: str | Path,
    output_dir: str | Path,
    declared_by: str,
    used_by: str,
    linear_tolerance_mm: float = DEFAULT_LINEAR_TOLERANCE_MM,
    angular_tolerance_rad: float = DEFAULT_ANGULAR_TOLERANCE_RAD,
    absolute: bool = True,
    overhang_from_vertical_degrees: float = OVERHANG_FROM_VERTICAL_DEGREES,
    reproducibility_check: bool = True,
) -> dict[str, Any]:
    """The offline half: what would be written, and how it would be judged. Reads the STEP, no kernel."""
    source = Path(step_path)
    if not source.is_file():
        raise ValueError(f"STEP source is missing: {source}")
    if source.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("source must be a .step or .stp file")
    if linear_tolerance_mm <= 0 or angular_tolerance_rad <= 0:
        raise ValueError("tessellation tolerances must be positive")
    for value, label in ((declared_by, "declared_by"), (used_by, "used_by")):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} is required")
    payload = source.read_bytes()
    return {
        "dryRun": True,
        "operation": "step-tessellation-handoff",
        "schema": SCHEMA,
        "source": {
            "path": str(source),
            "fileName": source.name,
            "byteCount": len(payload),
            "sha256": _sha256_bytes(payload),
            "sha256Stable": False,
            "sha256Note": ("STEP carries a GUID and a timestamp in its header; this digest is download "
                           "integrity and is not content identity"),
        },
        "outputDir": str(Path(output_dir)),
        "tessellation": {
            "absolute": bool(absolute),
            "declared_by": declared_by,
            "used_by": used_by,
            "declared": {"linear_tolerance_mm": linear_tolerance_mm,
                         "angular_tolerance_rad": angular_tolerance_rad},
        },
        "overhangFromVerticalDegrees": overhang_from_vertical_degrees,
        "reproducibilityCheck": bool(reproducibility_check),
        "identityRule": {
            # A DIGEST MUST NAME THE RULE THAT PRODUCED IT. MeshQ 168 measured a peer's set signature
            # moving between two schema revisions while the geometry AND every delivered STL byte-set were
            # unchanged (the canonical form changed), so "same digest" is only meaningful at the same rule
            # version -- and the comparison has to start here, not at the digest. A rule change moves the
            # digest, which is why this repository's own set signature has two generations (ade4c12a... ->
            # 7f427106...) with geometry that never moved.
            "version": "onshapescript.mesh-set-signature/1",
            # Machine-readable, not just prose: a consumer must not treat this digest as proof of identity.
            "identityProof": False,
            "note": ("a candidate filter, not an identity: equal digests do not prove equal geometry and "
                     "unequal digests do not prove it differs; the verdict belongs to the declared "
                     "equivalence tolerance, per quantity"),
            "sort_by": ["brepVolumeMm3", "bounds_mm"],
            # Per-quantity quanta, because one tolerance cannot govern two quantities: the exact volume
            # agrees to ~1e-9 between implementations while `bounds_mm` disagreed by 3.19e-2 mm between
            # FAMILIES (and by ~3e-6 between two implementations of the SAME mesh family). The digest
            # therefore reads the mesh-vertex box, whose family agrees to ~3e-6 mm, quantized to 1e-3 --
            # three orders of margin. Rounding does not remove the risk of two implementations landing on
            # opposite sides of a bin boundary; it is declared here, and the digest is a convenience, not
            # an identity proof (see the two-directional refusal rule in the contract draft).
            "quanta": {"brepVolumeMm3": 1e-3, "bounds_mm": 1e-3},
            "compare": "quantized_absolute",
            "equivalence_tolerance": {"brepVolumeMm3": 1e-6, "bounds_mm": 1e-3},
            "reference_point": INTEGRATION_REFERENCE,
            "bounds_family": "tessellation_vertices(artifact_bytes)",
        },
        "refusalRules": [
            "no shapes in the STEP -> refuse, do not write an empty handoff",
            "any solid whose STL export is missing or empty -> refuse (a partially written run must not "
            "be handed over as a whole one)",
            "declared and used tolerances differ -> write it down with deviation_reason, never silently",
            "winding inconsistent on any piece -> that piece's volume/area are null with applicable=false",
        ],
    }


def _piece_record(
    raw: dict[str, Any],
    *,
    measured: dict[str, Any],
    second: dict[str, Any] | None,
    export_id: str,
) -> dict[str, Any]:
    same_bytes = None
    evidence: list[str] = [measured["sha256"]]
    if second is not None:
        evidence.append(second["sha256"])
        same_bytes = second["sha256"] == measured["sha256"]
    # `bounds_mm` is the MESH-VERTEX box, and it says so. Three implementations published three
    # different boxes for one piece (max gap 3.19e-2 mm) because "the bounding box" is not one
    # measurement: this repository read it AFTER exporting the STL, which MUTATES the cached box; CadQ
    # read the exact B-Rep before tessellation; MeshQ read the mesh. The mesh family is the one any
    # consumer can reproduce from the artifact bytes, so it is the one that travels; the exact box and
    # the post-export box travel beside it, each with its own algorithm, and the gap between families is
    # reported as a METHOD gap instead of being compared as if it were a geometric disagreement.
    mesh_bounds = measured.get("meshBoundsMm")
    exact_bounds = raw.get("brepBoundsMm")
    method_gap = None
    if exact_bounds and mesh_bounds:
        method_gap = max(
            abs(exact_bounds[side][axis] - mesh_bounds[side][axis])
            for side in ("min", "max") for axis in range(3)
        )
    record: dict[str, Any] = {
        "index": raw["index"],
        "name": Path(raw["path"]).stem,
        "label": None,
        "bounds_mm": mesh_bounds,
        "boundsAlgorithm": "tessellation_vertices(artifact_bytes)",
        # NOT a defect signal, and deliberately not named as a delta between "the same" quantity: a
        # chord cuts inside the true surface by up to the linear deflection, so a nonzero gap here is
        # the expected method difference between mesh and exact B-Rep, not a geometric disagreement.
        "boundsMethodGapMm": method_gap,
        "boundsMethodGapNote": ("mesh vertices vs exact B-Rep read before tessellation; a gap up to the "
                               "declared linear tolerance is expected, because a chord lies inside the "
                               "surface it approximates"),
        "boundsCrossRunMm": None,
        "volume_mm3": measured["volumeMm3"] if measured["applicable"]["volumeMm3"] else None,
        "area_mm2": measured["areaMm2"] if measured["applicable"]["areaMm2"] else None,
        "applicable": measured["applicable"],
        "brep": {"measure_kind": "brep_exact", "volume_mm3": raw.get("brepVolumeMm3"),
                 "bounds_mm": exact_bounds,
                 # A tessellator that does not declare a family is reported as such rather than
                 # inheriting the mesh family's name.
                 "boundsAlgorithm": raw.get("boundsAlgorithm") or "undeclared_by_tessellator",
                 "boundsAfterTessellationMm": raw.get("boundsAfterTessellationMm"),
                 "boundsMutatedByExport": raw.get("boundsMutatedByExport")},
        "mesh": {
            "path": Path(measured["path"]).name,
            "media_type": "model/stl",
            "representation": "stl_triangulation",
            "byteCount": measured["byteCount"],
            "sha256": measured["sha256"],
            "sha256_stable": same_bytes,
            "sha256_evidence": evidence if same_bytes is not None else None,
            "triangleCount": measured["triangleCount"],
            "orientation": measured["orientation"],
            "facesWithoutNormal": measured["facesWithoutNormal"],
            "outwardOriented": measured["outwardOriented"],
            "watertight": measured["watertight"],
            # direction-derived: null with `applicable` false when the winding is inconsistent,
            # because these ARE functions of the face normals.
            "overhangAreaMm2": (measured["overhangAreaMm2"]
                                if measured["applicable"]["overhangAreaMm2"] else None),
            "overhangTriangleCount": (measured["overhangTriangleCount"]
                                      if measured["applicable"]["overhangTriangleCount"] else None),
            "overhangTriangleRatio": (measured["overhangTriangleRatio"]
                                      if measured["applicable"]["overhangTriangleCount"] else None),
            "bedContactAreaMm2": (measured["bedContactAreaMm2"]
                                  if measured["applicable"]["bedContactAreaMm2"] else None),
            "bedContactTriangleCount": (measured["bedContactTriangleCount"]
                                        if measured["applicable"]["bedContactTriangleCount"] else None),
            "bedContactTriangleRatio": (measured["bedContactTriangleRatio"]
                                        if measured["applicable"]["bedContactTriangleCount"] else None),
            "notApplicableReason": measured["notApplicableReason"],
        },
        "cross_plane_ref": {"export_id": export_id, "index": raw["index"], "signature": None},
        "selectors": [],
    }
    return record


def _set_signature(records: list[dict[str, Any]], precision: int = 0) -> str:
    """Digest over the EXACT readings only, full precision.

    Deliberately not over the mesh numbers: the same geometry tessellated at two tolerances has
    different triangle counts and possibly different mesh volumes, so a mesh-derived digest would vary
    with a choice that is not part of the geometry. Digests are a fast path in both directions only.
    """
    canonical = [
        {"brepVolumeMm3": record["brep"]["volume_mm3"], "bounds_mm": record["bounds_mm"]}
        for record in records
    ]
    # Quantize with the declared quanta before ordering and hashing, so a 3e-6 mm difference between two
    # implementations of one mesh family does not move a piece in the order.
    def _quantized(item: dict[str, Any]) -> tuple[str, ...]:
        volume = item["brepVolumeMm3"]
        bounds = item["bounds_mm"] or {}
        parts = [f"{round(float(volume) / 1e-3):+d}" if volume is not None else "none"]
        for side in ("min", "max"):
            for value in bounds.get(side, []) or []:
                parts.append(f"{round(float(value) / 1e-3):+d}")
        return tuple(parts)

    canonical.sort(key=_quantized)
    text = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_bytes(text.encode("utf-8"))


def tessellate_step(
    *,
    step_path: str | Path,
    output_dir: str | Path,
    declared_by: str,
    used_by: str,
    export_id: str,
    linear_tolerance_mm: float = DEFAULT_LINEAR_TOLERANCE_MM,
    angular_tolerance_rad: float = DEFAULT_ANGULAR_TOLERANCE_RAD,
    absolute: bool = True,
    overhang_from_vertical_degrees: float = OVERHANG_FROM_VERTICAL_DEGREES,
    reproducibility_check: bool = True,
    tessellator: Tessellator | None = None,
    independent_kernel: bool = False,
    kernel_note: str = "",
    quota_remaining: int | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Produce the per-piece STLs and the v0.4 manifest for one STEP file."""
    plan = plan_step_tessellation(
        step_path=step_path,
        output_dir=output_dir,
        declared_by=declared_by,
        used_by=used_by,
        linear_tolerance_mm=linear_tolerance_mm,
        angular_tolerance_rad=angular_tolerance_rad,
        absolute=absolute,
        overhang_from_vertical_degrees=overhang_from_vertical_degrees,
        reproducibility_check=reproducibility_check,
    )
    runner = tessellator or cadquery_tessellator
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    first = runner(
        Path(step_path),
        destination,
        linear_tolerance_mm=linear_tolerance_mm,
        angular_tolerance_rad=angular_tolerance_rad,
    )
    parts = first.get("parts") or []
    if not parts:
        raise ValueError("the tessellator produced no parts; refusing to write an empty handoff")

    second_by_index: dict[int, dict[str, Any]] = {}
    second_run: dict[str, Any] | None = None
    if reproducibility_check:
        mirror = destination / "reproducibility"
        mirror.mkdir(parents=True, exist_ok=True)
        second_run = runner(
            Path(step_path),
            mirror,
            linear_tolerance_mm=linear_tolerance_mm,
            angular_tolerance_rad=angular_tolerance_rad,
        )
        for part in second_run.get("parts") or []:
            second_by_index[part["index"]] = part

    records: list[dict[str, Any]] = []
    for raw in parts:
        measured = measure_stl(raw["path"], overhang_from_vertical_degrees=overhang_from_vertical_degrees)
        twin = second_by_index.get(raw["index"])
        second_measured = None
        if twin is not None:
            second_measured = measure_stl(
                twin["path"], overhang_from_vertical_degrees=overhang_from_vertical_degrees
            )
        record = _piece_record(raw, measured=measured, second=second_measured, export_id=export_id)
        # Same family on both sides (mesh vertices vs mesh vertices), which is the only comparison that
        # can find a tessellation that does not reproduce. Comparing the mesh box with the exact box --
        # what this field used to do -- is a method gap, and a method gap can never answer this question.
        if second_measured is not None and second_measured.get("meshBoundsMm"):
            first_bounds = measured.get("meshBoundsMm") or {}
            second_bounds = second_measured["meshBoundsMm"]
            record["boundsCrossRunMm"] = max(
                abs(first_bounds[side][axis] - second_bounds[side][axis])
                for side in ("min", "max") for axis in range(3)
                if first_bounds.get(side) and second_bounds.get(side)
            ) if first_bounds.get("min") and second_bounds.get("min") else None
        records.append(record)

    used = first.get("used") or {}
    used_linear = used.get("linear_tolerance_mm", linear_tolerance_mm)
    used_angular = used.get("angular_tolerance_rad", angular_tolerance_rad)
    matches = (float(used_linear) == float(linear_tolerance_mm)
               and float(used_angular) == float(angular_tolerance_rad))
    kernel = first.get("kernel") or {}
    def _sum(key: str) -> tuple[float, int]:
        """Sum what is readable and SAY how many pieces contributed.

        A total that silently drops the pieces whose reading was gated would be a number nobody can
        audit; `contributingPieces` is what makes the total honest.
        """
        values = [record["mesh"][key] for record in records if record["mesh"][key] is not None]
        return (round(sum(values), 9), len(values))

    overhang_total, overhang_pieces = _sum("overhangAreaMm2")
    area_total = round(sum(record["area_mm2"] or 0.0 for record in records), 9)
    contact_total, contact_pieces = _sum("bedContactAreaMm2")
    counted_total, counted_pieces = _sum("overhangTriangleCount")
    piece_count = len(records)
    totals = {
        "triangleCount": sum(record["mesh"]["triangleCount"] for record in records),
        "countedOverhangTriangles": counted_total,
        "overhangAreaMm2": overhang_total,
        "areaMm2": area_total,
        "bedContactAreaMm2": contact_total,
        "byteCount": sum(record["mesh"]["byteCount"] for record in records),
        "pieces": piece_count,
        "contributingPieces": {
            "triangleCount": piece_count,
            "areaMm2": sum(1 for record in records if record["area_mm2"] is not None),
            "overhang": overhang_pieces,
            "overhangTriangles": counted_pieces,
            "bedContactAreaMm2": contact_pieces,
        },
    }
    totals["overhangRatio"] = (round(overhang_total / area_total, 12) if area_total else None)
    totals["overhangTriangleRatio"] = (round(counted_total / totals["triangleCount"], 12)
                                       if totals["triangleCount"] else None)
    unstable = [record["index"] for record in records if record["mesh"]["sha256_stable"] is False]
    manifest = {
        "schema": SCHEMA,
        "produced_by": {
            "plane": "onshape",
            "identity": "RoseElm",
            "tool": "fdm_analysis/conversion/step_tessellation.py",
            "kind": "tool",
            "at": now,
        },
        "source": {"kind": "file", "reference": plan["source"]["path"], "identifiers": {}},
        "units": "mm",
        "authority": {
            "artifact_is": "triangulation_of_exact_geometry",
            "part_authoritative_in": declared_by,
            "order": ["reference.geometry", "declaration.geometry"],
            "statement": ("the exact B-Rep reading is authoritative; every mesh number here is the result of "
                          "one triangulation at the declared tolerances"),
        },
        "declaration": {
            "artifact": {
                "role": "derived",
                "path": str(destination),
                "media_type": "model/stl",
                "byte_count": totals["byteCount"],
                "piece_count": len(records),
            },
            "identity": {
                "sha256": _set_signature(records),
                "sha256_stable": not unstable,
                "sha256_stable_evidence": (None if unstable else {
                    "kind": "per_piece_digests",
                    # Inline the two digests AND name the exact path: a prose pointer that names a path
                    # which does not exist is worse than no pointer, because a consumer follows it and
                    # finds nothing (MeshQ read `mesh.sha256_evidence` at the top level; the real path is
                    # `declaration.geometry.parts[].mesh.sha256_evidence`).
                    "where": "declaration.geometry.parts[].mesh.sha256_evidence",
                    "second_run_directory": str(Path(destination).parent / "reproducibility"),
                    "digests": {str(record["index"]): record["mesh"]["sha256_evidence"]
                                for record in records},
                }),
                "sha256_note": ("digests are a fast path in BOTH directions: a differing digest is not "
                                "proof of different geometry, and an equal digest is not proof of "
                                "identical geometry; only identity_rule + equivalence_tolerance decide"),
            },
            "geometry": {
                "measure": {
                    "kind": "tessellation",
                    "kernel": {"name": kernel.get("name"), "version": kernel.get("version")},
                    "at": {"linear_tolerance_mm": used_linear, "angular_tolerance_rad": used_angular},
                },
                "solid_count": len(records),
                "parts": records,
                "identity_rule": {
                    "version": plan["identityRule"]["version"],
                    "identityProof": plan["identityRule"]["identityProof"],
                    "sort_by": plan["identityRule"]["sort_by"],
                    "quanta": plan["identityRule"]["quanta"],
                    "compare": plan["identityRule"]["compare"],
                    "bounds_family": plan["identityRule"]["bounds_family"],
                    "equivalence_tolerance": {"brepVolumeMm3": 1e-6, "bounds_mm": 1e-3},
                    "set_signature_sha256": _set_signature(records),
                    "note": ("parts are addressed by this rule, never by row order: a re-export can reorder "
                             "solids, and this file contains identical twins"),
                },
                "producer_command": first.get("call"),
            },
            "mesh": {
                "representation": "stl_triangulation",
                "reference_point": INTEGRATION_REFERENCE,
                "pieces": [{"path": record["mesh"]["path"], "sha256": record["mesh"]["sha256"]}
                           for record in records],
            },
            "tessellation": {
                "absolute": bool(absolute),
                "declared_by": declared_by,
                "used_by": used_by,
                "declared": {"linear_tolerance_mm": linear_tolerance_mm,
                             "angular_tolerance_rad": angular_tolerance_rad},
                "used": {"linear_tolerance_mm": used_linear, "angular_tolerance_rad": used_angular},
                "matches_declaration": matches,
                "deviation_reason": None if matches else "the kernel used different tolerances than declared",
                "read_back_from": first.get("call"),
                "read_back_at": now,
                "kernel": {"name": kernel.get("name"), "version": kernel.get("version")},
                "independent_kernel": bool(independent_kernel),
                "kernel_note": kernel_note or (
                    "tessellated with this producer's own kernel" if independent_kernel else
                    "NOT an independent kernel: the tessellator ran on another plane's interpreter, so "
                    "these numbers are a rule-level reproduction, not a second kernel's verdict"
                ),
            },
        },
        "reference": None,
        "totals": totals,
        "reproducibility": {
            "checked": bool(reproducibility_check),
            "unstablePieces": unstable,
            "secondRun": second_run is not None,
        },
        "cost": {
            "where": {"network": "offline", "mutating": False, "estimated_requests": 0,
                      "spent_quota": 0, "quota_remaining": quota_remaining},
            "what": {"kind": "artifacts"},
        },
        "next_action": {
            "kind": "awaiting_peer",
            "route_to": {"plane": used_by, "reason": "read the pieces and report an independent reading"},
            "detail": (f"{len(records)} pieces written for {used_by}; the winding of every piece is "
                       f"{'consistent' if all(r['mesh']['orientation']['consistent'] for r in records) else 'NOT consistent'}"),
        },
    }
    return manifest


def write_handoff_manifest(manifest: dict[str, Any], path: str | Path) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(destination)
