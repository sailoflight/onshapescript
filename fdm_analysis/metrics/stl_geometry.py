from __future__ import annotations

import math
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from fdm_analysis.contracts import MeshArtifact


Point = tuple[float, float, float]
Triangle = tuple[Point, Point, Point]


def _binary_triangles(data: bytes) -> list[Triangle] | None:
    if len(data) < 84:
        return None
    count = struct.unpack_from("<I", data, 80)[0]
    if 84 + count * 50 != len(data):
        return None
    triangles = []
    offset = 84
    for _ in range(count):
        values = struct.unpack_from("<12fH", data, offset)
        triangles.append((
            (values[3], values[4], values[5]),
            (values[6], values[7], values[8]),
            (values[9], values[10], values[11]),
        ))
        offset += 50
    return triangles


def _ascii_triangles(data: bytes) -> list[Triangle]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("STL is neither valid binary nor ASCII") from exc
    vertices: list[Point] = []
    for line in text.splitlines():
        words = line.strip().split()
        if not words or words[0].lower() != "vertex":
            continue
        if len(words) != 4:
            raise ValueError("invalid ASCII STL vertex")
        try:
            vertices.append((float(words[1]), float(words[2]), float(words[3])))
        except ValueError as exc:
            raise ValueError("invalid numeric ASCII STL vertex") from exc
    if not vertices or len(vertices) % 3:
        raise ValueError("ASCII STL must contain complete triangles")
    return [tuple(vertices[index:index + 3]) for index in range(0, len(vertices), 3)]  # type: ignore[list-item]


def read_stl(path: str | Path) -> list[Triangle]:
    data = Path(path).read_bytes()
    triangles = _binary_triangles(data)
    return triangles if triangles is not None else _ascii_triangles(data)


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Point, b: Point) -> Point:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _transform(point: Point, matrix: tuple[float, ...]) -> Point:
    return (
        matrix[0] * point[0] + matrix[1] * point[1] + matrix[2] * point[2],
        matrix[3] * point[0] + matrix[4] * point[1] + matrix[5] * point[2],
        matrix[6] * point[0] + matrix[7] * point[1] + matrix[8] * point[2],
    )


def _convex_hull(points: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for point in unique:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _inside_convex(point: tuple[float, float], hull: list[tuple[float, float]], tolerance: float) -> bool:
    if len(hull) < 3:
        return False
    signs = []
    for index, a in enumerate(hull):
        b = hull[(index + 1) % len(hull)]
        cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
        if abs(cross) > tolerance:
            signs.append(cross > 0)
    return not signs or all(sign == signs[0] for sign in signs)


class StlGeometryAnalyzer:
    """Dependency-free geometry metrics for a normalized millimeter STL mesh."""

    def __init__(self, *, overhang_from_vertical_degrees: float = 45.0) -> None:
        if not 0 < overhang_from_vertical_degrees < 90:
            raise ValueError("overhang_from_vertical_degrees must be between 0 and 90")
        self.overhang_from_vertical_degrees = float(overhang_from_vertical_degrees)

    def capabilities(self) -> dict[str, Any]:
        return {
            "available": True,
            "name": "python-stl-geometry",
            "version": "1",
            "wallThickness": False,
            "overhangPolicy": {
                "kind": "downward-face-area",
                "fromVerticalDegrees": self.overhang_from_vertical_degrees,
                "bridgesExcluded": False,
            },
        }

    def analyze(
        self,
        mesh: MeshArtifact,
        *,
        orientation_matrix: tuple[float, ...],
    ) -> dict[str, Any]:
        if mesh.units != "mm":
            raise ValueError("STL geometry analyzer requires a millimeter mesh")
        matrix = tuple(float(value) for value in orientation_matrix)
        if len(matrix) != 9 or not all(math.isfinite(value) for value in matrix):
            raise ValueError("orientation_matrix must contain nine finite values")
        source = read_stl(mesh.path)
        triangles = [tuple(_transform(point, matrix) for point in triangle) for triangle in source]
        vertices = [point for triangle in triangles for point in triangle]
        mins = tuple(min(point[axis] for point in vertices) for axis in range(3))
        maxs = tuple(max(point[axis] for point in vertices) for axis in range(3))
        dimensions = tuple(maxs[axis] - mins[axis] for axis in range(3))
        scale = max((*dimensions, 1.0))
        tolerance = scale * 1e-7

        edges: Counter[tuple[Point, Point]] = Counter()
        contact_area = 0.0
        contact_points: list[tuple[float, float]] = []
        overhang_area = 0.0
        signed_volume = 0.0
        center_weight = [0.0, 0.0, 0.0]
        normal_z_limit = -math.sin(math.radians(self.overhang_from_vertical_degrees))

        for a, b, c in triangles:
            rounded = [tuple(round(value, 9) for value in point) for point in (a, b, c)]
            for start, end in ((rounded[0], rounded[1]), (rounded[1], rounded[2]), (rounded[2], rounded[0])):
                edges[tuple(sorted((start, end)))] += 1
            cross = _cross(_sub(b, a), _sub(c, a))
            double_area = math.sqrt(_dot(cross, cross))
            if double_area <= tolerance * tolerance:
                continue
            area = double_area / 2.0
            normal_z = cross[2] / double_area
            if normal_z < normal_z_limit:
                overhang_area += area
            if all(abs(point[2] - mins[2]) <= tolerance for point in (a, b, c)):
                contact_area += area
                contact_points.extend((a[:2], b[:2], c[:2]))
            tetra_volume = _dot(a, _cross(b, c)) / 6.0
            signed_volume += tetra_volume
            for axis in range(3):
                center_weight[axis] += tetra_volume * (a[axis] + b[axis] + c[axis]) / 4.0

        watertight = bool(edges) and all(count == 2 for count in edges.values())
        center = None
        stable = None
        if abs(signed_volume) > tolerance ** 3:
            center = tuple(value / signed_volume for value in center_weight)
            hull = _convex_hull(contact_points)
            stable = _inside_convex((center[0], center[1]), hull, tolerance)

        return {
            "watertight": watertight,
            "dimensionsMm": [round(value, 9) for value in dimensions],
            "bedContactAreaMm2": round(contact_area, 9),
            "printHeightMm": round(dimensions[2], 9),
            "overhangAreaMm2": round(overhang_area, 9),
            "centerOfMassStable": stable,
            "centerOfMassMm": [round(value, 9) for value in center] if center else None,
            "volumeMm3": round(abs(signed_volume), 9),
            "triangleCount": len(triangles),
            "wallThicknessMm": None,
            "orientationMatrix": list(matrix),
            "analyzer": self.capabilities(),
        }
