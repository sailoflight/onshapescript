from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


_WINDOWS_PATH = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def host_path(value: str) -> Path:
    match = _WINDOWS_PATH.fullmatch(value)
    if match:
        drive, rest = match.groups()
        return Path("/mnt") / drive.lower() / rest.replace("\\", "/")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("converter paths must be absolute Windows or WSL paths")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert one STEP file to STL with pinned CadQuery/OCP.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--linear-tolerance-mm", type=float, required=True)
    parser.add_argument("--angular-tolerance-degrees", type=float, required=True)
    args = parser.parse_args()
    if args.linear_tolerance_mm <= 0 or args.angular_tolerance_degrees <= 0:
        raise ValueError("tessellation tolerances must be positive")

    input_path = host_path(args.input)
    output_path = host_path(args.output)
    if not input_path.is_file():
        raise ValueError(f"STEP input is missing: {input_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import cadquery as cq

    workplane = cq.importers.importStep(str(input_path), unit="MM")
    shapes = workplane.vals()
    if not shapes:
        raise ValueError("STEP import produced no shapes")
    cq.exporters.export(
        shapes,
        str(output_path),
        exportType="STL",
        tolerance=args.linear_tolerance_mm,
        angularTolerance=math.radians(args.angular_tolerance_degrees),
    )
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise ValueError("STL export produced no artifact")
    print(json.dumps({
        "converted": True,
        "shapeCount": len(shapes),
        "byteCount": output_path.stat().st_size,
        "cadqueryVersion": cq.__version__,
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
