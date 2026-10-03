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
        directed_edges: dict[tuple[Point, Point], list[tuple[int, int]]] = {}
        contact_area = 0.0
        surface_area = 0.0
        contact_points: list[tuple[float, float]] = []
        overhang_area = 0.0
        overhang_triangles = 0
        contact_triangles = 0
        faces_without_normal = 0
        signed_volume = 0.0
        center_weight = [0.0, 0.0, 0.0]
        normal_z_limit = -math.sin(math.radians(self.overhang_from_vertical_degrees))

        for index, (a, b, c) in enumerate(triangles):
            rounded = [tuple(round(value, 9) for value in point) for point in (a, b, c)]
            for start, end in ((rounded[0], rounded[1]), (rounded[1], rounded[2]), (rounded[2], rounded[0])):
                key = tuple(sorted((start, end)))
                edges[key] += 1
                # +1 when the traversal runs low -> high in sorted order, -1 the other way. A
                # consistently oriented closed mesh meets each shared edge once per direction; two
                # traversals in the SAME direction mean one of the two faces is wound inward.
                directed_edges.setdefault(key, []).append((index, 1 if start <= end else -1))
            cross = _cross(_sub(b, a), _sub(c, a))
            double_area = math.sqrt(_dot(cross, cross))
            if double_area <= tolerance * tolerance:
                # Counted, never silently dropped: a face with no usable normal cannot be judged, and
                # "not measured" must not read as "self-supporting".
                faces_without_normal += 1
                continue
            area = double_area / 2.0
            surface_area += area
            normal_z = cross[2] / double_area
            if normal_z < normal_z_limit:
                overhang_area += area
                overhang_triangles += 1
            if all(abs(point[2] - mins[2]) <= tolerance for point in (a, b, c)):
                contact_area += area
                contact_triangles += 1
                contact_points.extend((a[:2], b[:2], c[:2]))
            tetra_volume = _dot(a, _cross(b, c)) / 6.0
            signed_volume += tetra_volume
            for axis in range(3):
                center_weight[axis] += tetra_volume * (a[axis] + b[axis] + c[axis]) / 4.0

        watertight = bool(edges) and all(count == 2 for count in edges.values())
        non_manifold_edges = sum(1 for count in edges.values() if count > 2)
        inconsistent_pairs = 0
        inconsistent_faces: set[int] = set()
        for usages in directed_edges.values():
            if len(usages) != 2:
                continue
            (first_index, first_direction), (second_index, second_direction) = usages
            if first_direction == second_direction:
                inconsistent_pairs += 1
                inconsistent_faces.update((first_index, second_index))
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
            # The denominator of every ratio. Published because "26.67 % of the surface is overhanging"
            # is unreadable without it, and because the same policy read at another threshold
            # (`bedContactAreaMm2`) is only comparable when the total is the same number.
            "surfaceAreaMm2": round(surface_area, 9),
            # Counted/total, published as a ratio rather than leaving two isolated numbers: "132" and
            # "1044" cannot be judged without their quotient, and MeshQ asked for exactly this.
            "overhangTriangleRatio": (round(overhang_triangles / len(triangles), 12)
                                      if triangles else None),
            "bedContactTriangleRatio": (round(contact_triangles / len(triangles), 12)
                                        if triangles else None),
            "printHeightMm": round(dimensions[2], 9),
            "overhangAreaMm2": round(overhang_area, 9),
            # Counts are published next to the areas because a bare `faces` field is two different
            # units across implementations: this analyzer counts triangles, a mesh kernel may count
            # merged planar or quad faces of the same mesh (measured: one cube face is 2 here and 1
            # there, one sphere band is 960 here and 512 there, with the area agreeing to 1e-9).
            "overhangTriangleCount": overhang_triangles,
            "bedContactTriangleCount": contact_triangles,
            "facesWithoutNormal": faces_without_normal,
            # The evidence vocabulary is MeshQ's (its `inspection.grade_tiers`, message 161), adopted
            # verbatim so the same word means the same thing in both repositories:
            #   reliable  = derived from the artifact's own bytes by a stated method (a threshold that is
            #               declared does not make a reading heuristic -- MeshQ grades `overhang` reliable);
            #   heuristic = depends on a policy choice this plane cannot settle from the artifact;
            #   visual    = needs a reviewer, a slicer or a printer; this plane computes none of it;
            #   unknown   = not computed here, and therefore DECLARED ABSENT rather than omitted.
            # The last line is what answers "who judges printability": the geometry readings are reliable,
            # and every printability VERDICT below is visual, because no slicer is installed on this host.
            "gradeTiers": {
                "reliable": [
                    "triangleCount", "boundsMm", "volumeMm3", "surfaceAreaMm2", "printHeightMm",
                    "bedContactAreaMm2", "bedContactTriangleCount",
                    "overhangAreaMm2", "overhangTriangleCount", "orientation", "outwardOriented",
                ],
                "heuristic": [],
                "visual": [
                    "will a counted overhang warp, curl or delaminate (needs a slicer + a printer)",
                    "how long the print takes and where the supports actually go (slicer output)",
                    "is the wall thick enough for the load case (needs a thickness analyzer + the load case)",
                    "is the part printable on a given machine (needs a declared envelope and a verdict the "
                    "consumer owns)",
                ],
                "unknown": ["minWallMm (no thickness analyzer is installed on this host)"],
                "vocabulary": "MeshQ inspection.grade_tiers (reliable/heuristic/visual/unknown)",
                "gradeNote": ("reliable means derived from this artifact's bytes by the stated method, not "
                              "that the reading is the truth about the physical part"),
            },
            "orientation": {
                # `consistent` is meaningful only on a closed edge graph: on an open or degenerate mesh
                # every surviving shared edge can be used once in each direction while the graph is
                # shredded, so `consistent: true` there is VACUOUSLY true and must not be read as a
                # verified winding (measured on a real degenerate piece: watertight=false,
                # nonManifoldEdges=1, consistent=true). `applicable` says whether this reading means
                # anything at all; the counts are published either way so the reason is auditable.
                "consistent": inconsistent_pairs == 0,
                "applicable": watertight,
                "reason": None if watertight else (
                    "the edge graph is not a closed 2-manifold, so a winding check over it proves "
                    "nothing: the surviving pairs can all be consistent while the mesh is open, "
                    "non-manifold or degenerate"
                ),
                "inconsistentEdgePairs": inconsistent_pairs,
                # Locatable, not just counted: a bare count cannot be acted on.
                "inconsistentFaceIndices": sorted(inconsistent_faces),
                "nonManifoldEdges": non_manifold_edges,
                "checkedEdges": len(edges),
            },
            "centerOfMassStable": stable,
            "centerOfMassMm": [round(value, 9) for value in center] if center else None,
            "volumeMm3": round(abs(signed_volume), 9),
            # MeshQ 176 §2b and CadQ 171 on my own field: `outwardOriented` does NOT check "every face
            # points away from the solid" -- it checks `signed_volume > 0`, which is the SAME computation
            # as the volume and therefore not independent evidence of it. Two consequences, both taken:
            #   * the gate is now `orientation.consistent` (not merely `watertight`): a closed mesh with an
            #     inconsistent winding has no meaningful global "outward" at all;
            #   * the basis is published beside it, so a consumer cannot mistake the name for a check the
            #     number did not perform. Renaming the published key would silently break consumers of the
            #     0.4-draft shape, so the name stays and the scope travels with it.
            "outwardOriented": (signed_volume > 0) if (watertight and inconsistent_pairs == 0
                                                       and abs(signed_volume) > tolerance ** 3) else None,
            "outwardBasis": "signed_volume_positive",
            "outwardBasisNote": ("computed from the signed volume, so it is the same measurement as "
                                 "volumeMm3 rather than independent evidence of it; null unless the mesh is "
                                 "closed AND the winding is consistent"),
            "outwardIndependentOfVolume": False,
            "triangleCount": len(triangles),
            "wallThicknessMm": None,
            "orientationMatrix": list(matrix),
            "analyzer": self.capabilities(),
        }
