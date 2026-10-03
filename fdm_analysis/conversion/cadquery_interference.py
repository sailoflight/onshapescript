"""Pinned CadQuery/OCP interference report for one STEP file.

This is the geometry-leg half of the interference check and it is deliberately
the *second* step converter: `cadquery_step_to_stl.py` turns a STEP into a mesh
for FDM analysis, this one turns a STEP into a set of pairwise intersection
volumes. Both are launched by the configured geometry backend (the Windows MCP
process starts ``wsl.exe`` and this script runs under the pinned CadQuery venv),
so the module contract is the same one: absolute host paths, argparse, no import
of the repository, and a single artefact written to ``--output``.

Why this exists
---------------
Part counts, error features, a stable STEP sha256 and green FeatureScript
assertions cannot prove that two solids do not interfere: every one of those can
be true while two bodies overlap. The only primitive that *disproves* it is the
volume of the boolean intersection, which is what ``BRepAlgoAPI_Common`` returns
here. An axis-aligned bounding-box overlap is reported too, but only as a cheap
candidate filter: boxes that overlap may be a designed interlock, so a candidate
is not a finding.

Two modes:

``aabb``
    Report candidate pairs from the bounding boxes alone. Never a verdict.
``boolean``
    For every candidate pair, build the common shape and measure its volume.
    A pair whose intersection volume is at or below the contact floor counts as
    a touching pair rather than an interference.

Failure is explicit: a missing input, an unreadable STEP, a STEP with no solid,
or a write that cannot happen prints one line to stderr and exits non-zero
WITHOUT leaving an output file. A caller therefore never has to distinguish "no
interference" from "the check never ran".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path


_WINDOWS_PATH = re.compile(r"^([A-Za-z]):[\\/](.*)$")

#: Contact floor: an intersection at or below this volume is a touch (shared
#: face/edge/vertex), not an overlap. ``tolerance_mm ** 3`` is the cube of the
#: linear tolerance, so a 0.05 mm tolerance means a 1.25e-4 mm^3 floor; the hard
#: 1e-6 mm^3 term keeps a very small tolerance from turning numeric noise into a
#: finding.
_MIN_VOLUME_MM3 = 1e-6

#: Hard cap on candidate pairs that get a boolean evaluation. A STEP with many
#: bodies has a quadratic candidate space, and this script must not run
#: unbounded. Truncation is reported in ``counts.pairs_truncated`` so no caller
#: can mistake a partial run for a complete one.
MAX_PAIRS_CAP = 20_000


def host_path(value: str) -> Path:
    """Return the WSL path for an absolute Windows or WSL path.

    The geometry backend runs under Windows and hands ``wsl.exe`` Windows paths,
    while this script runs inside the WSL distribution. Refusing a relative path
    keeps the conversion directory-independent.
    """

    match = _WINDOWS_PATH.fullmatch(value)
    if match:
        drive, rest = match.groups()
        return Path("/mnt") / drive.lower() / rest.replace("\\", "/")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("converter paths must be absolute Windows or WSL paths")
    return path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bbox(shape: object) -> list[float]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    if box.IsVoid():
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    return [float(value) for value in box.Get()]


def _volume_mm3(shape: object) -> float:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass())


def _overlap_mm(first: list[float], second: list[float]) -> list[float] | None:
    """Return the per-axis overlap of two bounding boxes, or None when disjoint."""

    overlap = [
        min(first[3], second[3]) - max(first[0], second[0]),
        min(first[4], second[4]) - max(first[1], second[1]),
        min(first[5], second[5]) - max(first[2], second[2]),
    ]
    if any(value <= 0.0 for value in overlap):
        return None
    return [float(value) for value in overlap]


def _part_name(index: int, label: str | None) -> str:
    return f"solid_{index:02d}"


def _selected(name: str, index: int, label: str | None, wanted: frozenset[str]) -> bool:
    if not wanted:
        return True
    candidates = {name, str(index), name.replace("solid_", "solid")}
    if label:
        candidates.add(label)
    return bool(candidates & wanted)


def _common_volume(first: object, second: object) -> tuple[float, list[float]]:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

    operation = BRepAlgoAPI_Common(first, second)
    operation.Build()
    common = operation.Shape()
    return _volume_mm3(common), _bbox(common)


def build_report(
    *,
    input_path: Path,
    mode: str,
    tolerance_mm: float,
    wanted_parts: frozenset[str] = frozenset(),
    max_pairs: int = 4_000,
) -> dict[str, object]:
    """Measure one STEP file and return the report body (no file is written)."""

    import cadquery as cq  # noqa: F401  (imported here so the module stays importable)

    if mode not in {"aabb", "boolean"}:
        raise ValueError("mode must be 'aabb' or 'boolean'")
    if not (tolerance_mm > 0.0):
        raise ValueError("linear tolerance must be positive")
    if not input_path.is_file():
        raise ValueError(f"STEP input is missing: {input_path}")
    if max_pairs < 1 or max_pairs > MAX_PAIRS_CAP:
        raise ValueError(f"--max-pairs must be between 1 and {MAX_PAIRS_CAP}")

    imported = cq.importers.importStep(str(input_path))
    solids = list(imported.solids().vals())
    if not solids:
        raise ValueError(f"STEP carries no solid to check: {input_path}")

    parts: list[dict[str, object]] = []
    for index, solid in enumerate(solids, start=1):
        label = getattr(solid, "label", None) or None
        name = _part_name(index, label)
        parts.append(
            {
                "index": index,
                "name": name,
                "label": label,
                "selected": _selected(name, index, label, wanted_parts),
                "bbox_mm": _bbox(solid.wrapped),
                "volume_mm3": _volume_mm3(solid.wrapped),
            }
        )

    selected = [part for part in parts if part["selected"]]
    if wanted_parts and len(selected) < 2:
        raise ValueError(
            f"--part selected {len(selected)} of {len(parts)} solids; two are needed for a pair"
        )

    contact_floor = max(_MIN_VOLUME_MM3, float(tolerance_mm) ** 3)
    pairs: list[dict[str, object]] = []
    candidates = 0
    truncated = False
    interfering = 0
    touching = 0

    for left_index, left in enumerate(selected):
        for right in selected[left_index + 1 :]:
            overlap = _overlap_mm(left["bbox_mm"], right["bbox_mm"])  # type: ignore[arg-type]
            if overlap is None:
                continue
            candidates += 1
            if len(pairs) >= max_pairs:
                truncated = True
                continue
            pair: dict[str, object] = {
                "a": left["name"],
                "b": right["name"],
                "a_index": left["index"],
                "b_index": right["index"],
                "overlap_mm": overlap,
                "intersection_volume_mm3": None,
                "intersection_bbox_mm": None,
                "zero_volume_contact": None,
            }
            if mode == "boolean":
                volume, bbox = _common_volume(
                    solids[int(left["index"]) - 1].wrapped,
                    solids[int(right["index"]) - 1].wrapped,
                )
                is_contact = volume <= contact_floor
                pair["intersection_volume_mm3"] = volume
                pair["intersection_bbox_mm"] = bbox
                pair["zero_volume_contact"] = bool(is_contact)
                if is_contact:
                    touching += 1
                else:
                    interfering += 1
            pairs.append(pair)

    return {
        "schema": "onshapescript.interference/1",
        "mode": mode,
        "input": str(input_path),
        "input_sha256": file_sha256(input_path),
        "tolerance_mm": float(tolerance_mm),
        "contact_floor_mm3": contact_floor,
        "parts": parts,
        "pairs": pairs,
        "counts": {
            "parts": len(parts),
            "selected_parts": len(selected),
            "candidate_pairs": candidates,
            "checked_pairs": len(pairs) if mode == "boolean" else 0,
            "interfering": interfering,
            "touching": touching,
            "pairs_truncated": truncated,
        },
        "failures": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report pairwise interference for the solids of one STEP file."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=("aabb", "boolean"), default="boolean")
    parser.add_argument("--linear-tolerance-mm", type=float, required=True)
    parser.add_argument(
        "--part",
        action="append",
        default=[],
        help="Restrict the check to these part names, labels or 1-based indexes. Repeatable.",
    )
    parser.add_argument(
        "--parts",
        default="",
        help=(
            "Comma-separated equivalent of --part, because a configured argv template can "
            "only expand one placeholder per argument. An empty value means every solid."
        ),
    )
    parser.add_argument("--max-pairs", type=int, default=4_000)
    args = parser.parse_args()

    try:
        input_path = host_path(args.input)
        # "--output -" prints the report to stdout instead of writing a file. The
        # reading side uses that form so a pure check leaves nothing on disk; a
        # caller that wants the report kept passes a real path.
        to_stdout = args.output.strip() == "-"
        output_path = None if to_stdout else host_path(args.output)
        if not math.isfinite(args.linear_tolerance_mm) or args.linear_tolerance_mm <= 0:
            raise ValueError("linear tolerance must be a positive finite number")
        report = build_report(
            input_path=input_path,
            mode=args.mode,
            tolerance_mm=args.linear_tolerance_mm,
            wanted_parts=frozenset(
                name.strip()
                for name in [*args.part, *args.parts.split(",")]
                if name.strip()
            ),
            max_pairs=args.max_pairs,
        )
    except Exception as error:  # noqa: BLE001 - one readable line, then exit
        print(f"cadquery_interference: {type(error).__name__}: {error}", file=sys.stderr)
        return 2

    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if output_path is None:
        sys.stdout.write(payload)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
