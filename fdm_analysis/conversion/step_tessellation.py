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
    # `applicable` is derived, never assumed: a calibrated quantity is only readable when the shell is
    # closed AND the winding was checked, because an inverted face can hide from a volume.
    readable = bool(reading["watertight"]) and bool(orientation["consistent"])
    reason = None
    if not readable:
        reason = ("not watertight" if not reading["watertight"]
                  else "the winding is inconsistent, so a signed quantity is not physically meaningful")
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
        "bedContactAreaMm2": reading["bedContactAreaMm2"],
        "bedContactTriangleCount": reading["bedContactTriangleCount"],
        "facesWithoutNormal": reading["facesWithoutNormal"],
        "orientation": orientation,
        "outwardOriented": reading["outwardOriented"],
        "applicable": {
            "volumeMm3": readable,
            "areaMm2": readable,
            "outwardOriented": readable,
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
    parts = [str(facts["cadquery"] or "unknown"), str(facts["occt"] or "OCCT-unknown")]
    facts["version"] = "+".join(parts)
    return facts


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
        cq.exporters.export(
            shape,
            str(path),
            exportType="STL",
            tolerance=linear_tolerance_mm,
            angularTolerance=angular_tolerance_rad,
        )
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"STL export produced no artifact for solid {index}")
        try:
            volume = float(shape.Volume())
        except Exception:
            volume = None
        try:
            box = shape.BoundingBox()
            bounds = {
                "min": [box.xmin, box.ymin, box.zmin],
                "max": [box.xmax, box.ymax, box.zmax],
            }
            bounds["size"] = _size(bounds)
        except Exception:
            bounds = None
        parts.append({"index": index, "path": str(path), "brepVolumeMm3": volume, "brepBoundsMm": bounds})
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
            "sort_by": ["brepVolumeMm3", "bounds_mm"],
            "compare": "relative",
            "precision": 1e-6,
            "equivalence_tolerance": 1e-6,
            "reference_point": INTEGRATION_REFERENCE,
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
    bounds = raw.get("brepBoundsMm") or measured.get("meshBoundsMm")
    mesh_bounds = measured.get("meshBoundsMm")
    bounds_delta = None
    if raw.get("brepBoundsMm") and mesh_bounds:
        exact, tessellated = raw["brepBoundsMm"], mesh_bounds
        bounds_delta = max(
            abs(exact[side][axis] - tessellated[side][axis])
            for side in ("min", "max") for axis in range(3)
        )
    record: dict[str, Any] = {
        "index": raw["index"],
        "name": Path(raw["path"]).stem,
        "label": None,
        "bounds_mm": bounds,
        # An independent signal, not a formula: a mesh that does not span its exact bounds is a
        # tessellation defect, and 0.0 is the expected value at any declared tolerance.
        "boundsDeltaMm": bounds_delta,
        "meshBoundsMm": mesh_bounds,
        "volume_mm3": measured["volumeMm3"] if measured["applicable"]["volumeMm3"] else None,
        "area_mm2": measured["areaMm2"] if measured["applicable"]["areaMm2"] else None,
        "applicable": measured["applicable"],
        "brep": {"measure_kind": "brep_exact", "volume_mm3": raw.get("brepVolumeMm3"),
                 "bounds_mm": raw.get("brepBoundsMm")},
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
            "overhangAreaMm2": measured["overhangAreaMm2"],
            "overhangTriangleCount": measured["overhangTriangleCount"],
            "bedContactAreaMm2": measured["bedContactAreaMm2"],
            "bedContactTriangleCount": measured["bedContactTriangleCount"],
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
        {"brepVolumeMm3": record["brep"]["volume_mm3"], "bounds_mm": record["brep"]["bounds_mm"]}
        for record in records
    ]
    canonical.sort(key=lambda item: (str(item["brepVolumeMm3"]), json.dumps(item["bounds_mm"], sort_keys=True)))
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
        records.append(
            _piece_record(raw, measured=measured, second=second_measured, export_id=export_id)
        )

    used = first.get("used") or {}
    used_linear = used.get("linear_tolerance_mm", linear_tolerance_mm)
    used_angular = used.get("angular_tolerance_rad", angular_tolerance_rad)
    matches = (float(used_linear) == float(linear_tolerance_mm)
               and float(used_angular) == float(angular_tolerance_rad))
    kernel = first.get("kernel") or {}
    totals = {
        "triangleCount": sum(record["mesh"]["triangleCount"] for record in records),
        "overhangAreaMm2": sum(record["mesh"]["overhangAreaMm2"] for record in records),
        "areaMm2": sum(record["mesh"]["overhangAreaMm2"] for record in records) * 0.0
        + sum(record["area_mm2"] or 0.0 for record in records),
        "bedContactAreaMm2": sum(record["mesh"]["bedContactAreaMm2"] for record in records),
        "byteCount": sum(record["mesh"]["byteCount"] for record in records),
    }
    totals["overhangRatio"] = (totals["overhangAreaMm2"] / totals["areaMm2"]) if totals["areaMm2"] else None
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
                "sha256_stable_evidence": (None if unstable else
                                           ["per-piece digests in mesh.sha256_evidence"]),
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
                    "sort_by": plan["identityRule"]["sort_by"],
                    "compare": "relative",
                    "precision": 1e-6,
                    "equivalence_tolerance": 1e-6,
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
