"""Regression checks for exact intersections, including tangencies and overlaps."""

import math

from app.models.geometry import GeometryArc, GeometryLine, GeometryVertex, Point
from app.services.geometry.contour import validate_contour


def vertices(*coordinates: tuple[float, float]) -> list[GeometryVertex]:
    return [GeometryVertex(id=f"p{index}", x=x, y=y) for index, (x, y) in enumerate(coordinates)]


def line(index: int, start: GeometryVertex, end: GeometryVertex) -> GeometryLine:
    return GeometryLine(
        id=f"e{index}", type="line", from_=start.id, to=end.id,
        length=math.hypot(end.x - start.x, end.y - start.y),
    )


def arc(
    index: int, start: GeometryVertex, end: GeometryVertex,
    center: tuple[float, float], sweep: float, clockwise: bool = True,
) -> GeometryArc:
    return GeometryArc(
        id=f"e{index}", type="arc", from_=start.id, to=end.id,
        center=Point(x=center[0], y=center[1]),
        radius=math.hypot(start.x - center[0], start.y - center[1]),
        clockwise=clockwise, shape="out" if clockwise else "in",
        sweep_angle_degrees=sweep,
        arc_size="semicircle" if sweep == 180 else "minor" if sweep < 180 else "major",
    )


def polygon_lines(points: list[GeometryVertex]) -> list[GeometryLine]:
    return [line(index, point, points[(index + 1) % len(points)]) for index, point in enumerate(points)]


def test_clockwise_rectangle_has_no_false_intersections_at_corners() -> None:
    points = vertices((0, 0), (0, 2), (3, 2), (3, 0))

    assert validate_contour(points, polygon_lines(points)) == []


def test_line_only_self_intersection_is_reported() -> None:
    points = vertices((0, 0), (2, 2), (0, 2), (2, 0))

    issues = validate_contour(points, polygon_lines(points))

    assert any("Edges e0 and e2 intersect" in issue.reason for issue in issues)


def test_adjacent_collinear_lines_may_not_overlap() -> None:
    points = vertices((0, 0), (0, 3), (3, 3), (1, 3), (3, 0))

    issues = validate_contour(points, polygon_lines(points))

    assert any("Edges e1 and e2 overlap" in issue.reason for issue in issues)


def test_adjacent_line_and_arc_may_not_intersect_a_second_time() -> None:
    points = vertices((-1, 0), (1, 0), (-2, 0.5))
    edges = [
        arc(0, points[0], points[1], (0, 0), 180),
        line(1, points[1], points[2]),
        line(2, points[2], points[0]),
    ]

    issues = validate_contour(points, edges)

    assert any("Edges e0 and e1 intersect" in issue.reason for issue in issues)


def test_adjacent_arcs_may_not_intersect_a_second_time() -> None:
    # The circles meet at (0.5, +/-sqrt(3)/2); only the lower point is shared.
    points = vertices((-1, 0), (0.5, -math.sqrt(3) / 2), (2, 0))
    edges = [
        arc(0, points[0], points[1], (0, 0), 240),
        arc(1, points[1], points[2], (1, 0), 240),
        line(2, points[2], points[0]),
    ]

    issues = validate_contour(points, edges)

    assert any("Edges e0 and e1 intersect" in issue.reason for issue in issues)


def test_nonadjacent_arc_tangency_is_a_self_intersection() -> None:
    # The inward-facing semicircles touch at (1, 0), inside both arcs.
    points = vertices((0, 1), (0, -1), (2, -1), (2, 1))
    edges = [
        arc(0, points[0], points[1], (0, 0), 180),
        line(1, points[1], points[2]),
        arc(2, points[2], points[3], (2, 0), 180),
        line(3, points[3], points[0]),
    ]

    issues = validate_contour(points, edges)

    assert any("Edges e0 and e2 intersect" in issue.reason for issue in issues)


def test_coincident_arcs_may_not_overlap_in_opposite_directions() -> None:
    points = vertices((-1, 0), (0, 1), (1, 0), (0, -1))
    edges = [
        arc(0, points[0], points[1], (0, 0), 90),
        arc(1, points[1], points[2], (0, 0), 270, clockwise=False),
        line(2, points[2], points[3]),
        line(3, points[3], points[0]),
    ]

    issues = validate_contour(points, edges)

    assert any("Edges e0 and e1 overlap" in issue.reason for issue in issues)


def test_two_semicircles_form_a_valid_circle_with_two_shared_endpoints() -> None:
    points = vertices((-1, 0), (1, 0))
    edges = [
        arc(0, points[0], points[1], (0, 0), 180),
        arc(1, points[1], points[0], (0, 0), 180),
    ]

    assert validate_contour(points, edges) == []
