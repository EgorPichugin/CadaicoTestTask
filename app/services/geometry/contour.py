"""Build a symmetric contour and validate its exact line/arc geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.models.extraction import ExtractionResult
from app.models.geometry import (
    GeometryArc,
    GeometryEdge,
    GeometryIssue,
    GeometryLine,
    GeometryVertex,
    Point,
)


Coordinate = tuple[float, float]
_DEFAULT_TOLERANCE = 1e-7
_TAU = 2 * math.pi


def build_contour(
    extraction: ExtractionResult,
    coordinates: dict[str, Coordinate],
    arcs: dict[str, GeometryArc],
) -> tuple[list[GeometryVertex], list[GeometryEdge]]:
    """Reflect the solved upper chain and append its reverse traversal."""
    vertices = [
        GeometryVertex(id=vertex.id, x=coordinates[vertex.id][0], y=coordinates[vertex.id][1])
        for vertex in extraction.vertices
    ]
    edges: list[GeometryEdge] = []
    for edge in extraction.edges:
        if edge.type == "arc":
            edges.append(arcs[edge.id])
        else:
            edges.append(
                GeometryLine(
                    id=edge.id,
                    type="line",
                    from_=edge.from_,
                    to=edge.to,
                    length=_distance(coordinates[edge.from_], coordinates[edge.to]),
                )
            )

    next_vertex = max(int(vertex.id[1:]) for vertex in vertices) + 1
    next_edge = max(int(edge.id[1:]) for edge in edges) + 1
    reflected: dict[str, str] = {}
    for vertex in reversed(vertices.copy()):
        if abs(vertex.y) <= _DEFAULT_TOLERANCE:
            reflected[vertex.id] = vertex.id
            continue
        reflected_id = f"p{next_vertex}"
        next_vertex += 1
        reflected[vertex.id] = reflected_id
        vertices.append(GeometryVertex(id=reflected_id, x=vertex.x, y=-vertex.y))

    for edge in reversed(edges.copy()):
        updates = {
            "id": f"e{next_edge}",
            "from_": reflected[edge.to],
            "to": reflected[edge.from_],
        }
        next_edge += 1
        if isinstance(edge, GeometryArc):
            # Reflection and reversal each flip direction, so together they retain it.
            updates["center"] = Point(x=edge.center.x, y=-edge.center.y)
        edges.append(edge.model_copy(update=updates))
    return vertices, edges


def validate_contour(
    vertices: list[GeometryVertex],
    edges: list[GeometryEdge],
    tolerance: float = _DEFAULT_TOLERANCE,
) -> list[GeometryIssue]:
    """Check a clockwise simple closed contour without discretizing its arcs."""
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Contour tolerance must be finite and positive.")
    issues: list[GeometryIssue] = []
    if not vertices or not edges:
        return [GeometryIssue(target=None, reason="The contour has no vertices or edges.")]

    points = {vertex.id: (vertex.x, vertex.y) for vertex in vertices}
    if len(points) != len(vertices):
        issues.append(GeometryIssue(target=None, reason="Contour vertex IDs are not unique."))
    if len({edge.id for edge in edges}) != len(edges):
        issues.append(GeometryIssue(target=None, reason="Contour edge IDs are not unique."))

    valid_edges: list[tuple[int, GeometryEdge]] = []
    visited: set[str] = set()
    referenced: set[str] = set()
    for index, edge in enumerate(edges):
        if edge.to != edges[(index + 1) % len(edges)].from_:
            issues.append(GeometryIssue(target=edge.id, reason="The contour chain is not closed and continuous."))
        if edge.from_ in visited:
            issues.append(GeometryIssue(target=edge.from_, reason="The contour revisits a vertex before closing."))
        visited.add(edge.from_)
        referenced.update((edge.from_, edge.to))
        if edge.from_ not in points or edge.to not in points:
            issues.append(GeometryIssue(target=edge.id, reason="An edge references a missing vertex."))
            continue
        start, end = points[edge.from_], points[edge.to]
        if _distance(start, end) <= tolerance:
            issues.append(GeometryIssue(target=edge.id, reason="An edge has coincident endpoints."))
            continue
        if isinstance(edge, GeometryArc):
            arc_issues = _validate_arc(edge, start, end, tolerance)
            issues.extend(arc_issues)
            if arc_issues:
                continue
        elif abs(edge.length - _distance(start, end)) > tolerance:
            issues.append(GeometryIssue(target=edge.id, reason="The line length does not match its endpoints."))
        valid_edges.append((index, edge))

    for vertex_id in points.keys() - referenced:
        issues.append(GeometryIssue(target=vertex_id, reason="A contour vertex is not used by any edge."))

    if len(valid_edges) == len(edges):
        area = _signed_area(edges, points)
        perimeter = sum(
            edge.radius * math.radians(edge.sweep_angle_degrees)
            if isinstance(edge, GeometryArc) else edge.length
            for edge in edges
        )
        if abs(area) <= tolerance * perimeter:
            issues.append(GeometryIssue(target=None, reason="The contour encloses no nonzero area within tolerance."))
        elif area > 0:
            issues.append(GeometryIssue(target=None, reason="The full contour must be traversed clockwise."))

    for position, (first_index, first) in enumerate(valid_edges):
        for second_index, second in valid_edges[position + 1:]:
            intersections = _intersections(first, second, points, tolerance)
            if intersections.overlap:
                issues.append(GeometryIssue(target=first.id, reason=f"Edges {first.id} and {second.id} overlap."))
                continue
            allowed: list[Coordinate] = []
            if second_index == first_index + 1 and first.to == second.from_:
                allowed.append(points[first.to])
            if first_index == 0 and second_index == len(edges) - 1 and second.to == first.from_:
                allowed.append(points[first.from_])
            if any(
                not any(_distance(point, endpoint) <= tolerance for endpoint in allowed)
                for point in intersections.points
            ):
                issues.append(
                    GeometryIssue(
                        target=first.id,
                        reason=f"Edges {first.id} and {second.id} intersect away from an allowed shared endpoint.",
                    )
                )
    return issues


def _validate_arc(
    arc: GeometryArc, start: Coordinate, end: Coordinate, tolerance: float,
) -> list[GeometryIssue]:
    issues: list[GeometryIssue] = []
    center = (arc.center.x, arc.center.y)
    if any(abs(_distance(point, center) - arc.radius) > tolerance for point in (start, end)):
        issues.append(GeometryIssue(target=arc.id, reason="An arc endpoint is not on its stated circle."))
    sweep = math.radians(arc.sweep_angle_degrees)
    actual = _directed_angle(_angle(start, center), _angle(end, center), arc.clockwise)
    if abs(actual - sweep) * arc.radius > tolerance:
        issues.append(GeometryIssue(target=arc.id, reason="The arc sweep does not match its endpoints and direction."))
    angle_tolerance = tolerance / arc.radius
    if (
        (arc.arc_size == "minor" and sweep > math.pi + angle_tolerance)
        or (arc.arc_size == "major" and sweep < math.pi - angle_tolerance)
        or (arc.arc_size == "semicircle" and abs(sweep - math.pi) > angle_tolerance)
    ):
        issues.append(GeometryIssue(target=arc.id, reason="The arc size does not match its sweep."))
    expected_shape = "out" if arc.clockwise else "in"
    if arc.shape != expected_shape:
        issues.append(GeometryIssue(target=arc.id, reason="The arc shape conflicts with material on the right of the clockwise contour."))
    return issues


def _signed_area(edges: list[GeometryEdge], points: dict[str, Coordinate]) -> float:
    # Translate near the origin to avoid cancellation for large absolute coordinates.
    origin = points[edges[0].from_]
    terms: list[float] = []
    for edge in edges:
        start, end = _subtract(points[edge.from_], origin), _subtract(points[edge.to], origin)
        if isinstance(edge, GeometryArc):
            center = _subtract((edge.center.x, edge.center.y), origin)
            sweep = math.radians(edge.sweep_angle_degrees) * (-1 if edge.clockwise else 1)
            terms.append(_cross(center, _subtract(end, start)) + edge.radius**2 * sweep)
        else:
            terms.append(_cross(start, end))
    return math.fsum(terms) / 2


@dataclass(frozen=True)
class _Intersections:
    points: tuple[Coordinate, ...] = ()
    overlap: bool = False


def _intersections(
    first: GeometryEdge,
    second: GeometryEdge,
    points: dict[str, Coordinate],
    tolerance: float,
) -> _Intersections:
    if isinstance(first, GeometryArc) and isinstance(second, GeometryArc):
        return _arc_arc(first, second, points, tolerance)
    if isinstance(first, GeometryArc):
        return _line_arc(second, first, points, tolerance)
    if isinstance(second, GeometryArc):
        return _line_arc(first, second, points, tolerance)
    return _line_line(
        points[first.from_], points[first.to], points[second.from_], points[second.to], tolerance,
    )


def _line_line(
    start: Coordinate, end: Coordinate,
    other_start: Coordinate, other_end: Coordinate,
    tolerance: float,
) -> _Intersections:
    direction, other_direction = _subtract(end, start), _subtract(other_end, other_start)
    length, other_length = math.hypot(*direction), math.hypot(*other_direction)
    offset = _subtract(other_start, start)
    denominator = _cross(direction, other_direction)
    if abs(denominator) <= tolerance * min(length, other_length):
        distances = (
            abs(_cross(direction, offset)) / length,
            abs(_cross(direction, _subtract(other_end, start))) / length,
        )
        if max(distances) <= tolerance:
            parameters = (_dot(offset, direction) / length**2,
                          _dot(_subtract(other_end, start), direction) / length**2)
            lower, upper = max(0.0, min(parameters)), min(1.0, max(parameters))
            if upper < lower - tolerance / length:
                return _Intersections()
            if (upper - lower) * length > tolerance:
                return _Intersections(overlap=True)
            parameter = max(0.0, min(1.0, (lower + upper) / 2))
            return _Intersections((_add_scaled(start, direction, parameter),))
        if denominator == 0:
            return _Intersections()
    first_parameter = _cross(offset, other_direction) / denominator
    second_parameter = _cross(offset, direction) / denominator
    if (
        -tolerance / length <= first_parameter <= 1 + tolerance / length
        and -tolerance / other_length <= second_parameter <= 1 + tolerance / other_length
    ):
        return _Intersections((_add_scaled(start, direction, first_parameter),))
    return _Intersections()


def _line_arc(
    line: GeometryLine, arc: GeometryArc,
    points: dict[str, Coordinate], tolerance: float,
) -> _Intersections:
    start, end = points[line.from_], points[line.to]
    direction = _subtract(end, start)
    length = math.hypot(*direction)
    unit = (direction[0] / length, direction[1] / length)
    offset = _subtract((arc.center.x, arc.center.y), start)
    along = _dot(offset, unit)
    perpendicular = abs(_cross(offset, unit))
    if perpendicular > arc.radius + tolerance:
        return _Intersections()
    half_chord = math.sqrt(max(0.0, (arc.radius - perpendicular) * (arc.radius + perpendicular)))
    candidates = [
        _add_scaled(start, unit, distance)
        for distance in (along - half_chord, along + half_chord)
        if -tolerance <= distance <= length + tolerance
    ]
    return _Intersections(_unique_points(
        [point for point in candidates if _on_arc(point, arc, points[arc.from_], tolerance)],
        tolerance,
    ))


def _arc_arc(
    first: GeometryArc, second: GeometryArc,
    points: dict[str, Coordinate], tolerance: float,
) -> _Intersections:
    center = (first.center.x, first.center.y)
    other_center = (second.center.x, second.center.y)
    offset = _subtract(other_center, center)
    distance = math.hypot(*offset)
    if distance <= tolerance and abs(first.radius - second.radius) <= tolerance:
        return _coincident_arcs(first, second, points, tolerance)
    if (
        distance == 0
        or distance > first.radius + second.radius + tolerance
        or distance < abs(first.radius - second.radius) - tolerance
    ):
        return _Intersections()
    along = ((first.radius - second.radius) * (first.radius + second.radius) + distance**2) / (2 * distance)
    height_squared = (first.radius - along) * (first.radius + along)
    if height_squared < -2 * tolerance * max(first.radius, second.radius):
        return _Intersections()
    height = math.sqrt(max(0.0, height_squared))
    unit = (offset[0] / distance, offset[1] / distance)
    base = _add_scaled(center, unit, along)
    perpendicular = (-unit[1], unit[0])
    candidates = (_add_scaled(base, perpendicular, height), _add_scaled(base, perpendicular, -height))
    return _Intersections(_unique_points([
        point for point in candidates
        if _on_arc(point, first, points[first.from_], tolerance)
        and _on_arc(point, second, points[second.from_], tolerance)
    ], tolerance))


def _coincident_arcs(
    first: GeometryArc, second: GeometryArc,
    points: dict[str, Coordinate], tolerance: float,
) -> _Intersections:
    for first_start, first_end in _arc_intervals(first, points[first.from_]):
        for second_start, second_end in _arc_intervals(second, points[second.from_]):
            overlap_angle = min(first_end, second_end) - max(first_start, second_start)
            if overlap_angle * min(first.radius, second.radius) > tolerance:
                return _Intersections(overlap=True)
    candidates = [points[vertex_id] for vertex_id in (first.from_, first.to, second.from_, second.to)]
    return _Intersections(_unique_points([
        point for point in candidates
        if _on_arc(point, first, points[first.from_], tolerance)
        and _on_arc(point, second, points[second.from_], tolerance)
    ], tolerance))


def _arc_intervals(arc: GeometryArc, start: Coordinate) -> list[tuple[float, float]]:
    """Represent the occupied circle angles as one or two CCW intervals."""
    angle = _angle(start, (arc.center.x, arc.center.y))
    sweep = math.radians(arc.sweep_angle_degrees)
    beginning = (angle - sweep if arc.clockwise else angle) % _TAU
    ending = beginning + sweep
    if ending <= _TAU:
        return [(beginning, ending)]
    return [(beginning, _TAU), (0.0, ending - _TAU)]


def _on_arc(point: Coordinate, arc: GeometryArc, start: Coordinate, tolerance: float) -> bool:
    center = (arc.center.x, arc.center.y)
    if abs(_distance(point, center) - arc.radius) > tolerance:
        return False
    delta = _directed_angle(_angle(start, center), _angle(point, center), arc.clockwise)
    angle_tolerance = tolerance / arc.radius
    return delta <= math.radians(arc.sweep_angle_degrees) + angle_tolerance or _TAU - delta <= angle_tolerance


def _unique_points(points: list[Coordinate], tolerance: float) -> tuple[Coordinate, ...]:
    unique: list[Coordinate] = []
    for point in points:
        if not any(_distance(point, other) <= tolerance for other in unique):
            unique.append(point)
    return tuple(unique)


def _directed_angle(start: float, end: float, clockwise: bool) -> float:
    return (start - end if clockwise else end - start) % _TAU


def _angle(point: Coordinate, center: Coordinate) -> float:
    return math.atan2(point[1] - center[1], point[0] - center[0])


def _distance(first: Coordinate, second: Coordinate) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _subtract(first: Coordinate, second: Coordinate) -> Coordinate:
    return first[0] - second[0], first[1] - second[1]


def _add_scaled(point: Coordinate, vector: Coordinate, scale: float) -> Coordinate:
    return point[0] + vector[0] * scale, point[1] + vector[1] * scale


def _cross(first: Coordinate, second: Coordinate) -> float:
    return first[0] * second[1] - first[1] * second[0]


def _dot(first: Coordinate, second: Coordinate) -> float:
    return first[0] * second[0] + first[1] * second[1]
