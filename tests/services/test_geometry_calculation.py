import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.models.extraction import ExtractionResult
from app.models.geometry import GeometryResult
from app.services.geometry_calculation import GeometryCalculationService


EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "extraction.example.json"
SOURCE = {"view": "A-A", "text": "test dimension"}


@pytest.fixture
def example() -> dict[str, Any]:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def calculate(data: dict[str, Any]) -> GeometryResult:
    return GeometryCalculationService().calculate(ExtractionResult.model_validate(data))


def arc_profile(arc_size: str | None, radius: float = math.sqrt(2)) -> dict[str, Any]:
    """Two vertical sides topped by an arc with endpoints (0, 3), (2, 3)."""
    return {
        "schema_version": "2.0",
        "units": "mm",
        "profile": {
            "view": "A-A", "half": "upper", "symmetry_axis": "X",
            "origin_vertex": "p0",
        },
        "vertices": [
            {"id": "p0", "x": 0, "y": 0},
            {"id": "p1", "x": None, "y": None},
            {"id": "p2", "x": None, "y": None},
            {"id": "p3", "x": None, "y": 0},
        ],
        "edges": [
            {"id": "e1", "type": "line", "from": "p0", "to": "p1", "direction": "+Y"},
            {
                "id": "e2", "type": "arc", "from": "p1", "to": "p2",
                "radius": radius, "clockwise": True, "shape": "out",
                "arc_size": arc_size, "center_constraint": "none", "source": SOURCE,
            },
            {"id": "e3", "type": "line", "from": "p2", "to": "p3", "direction": "-Y"},
        ],
        "dimensions": [
            {"id": "d1", "type": "diameter", "vertex": "p1", "value": 6, "source": SOURCE},
            {"id": "d2", "type": "diameter", "vertex": "p2", "value": 6, "source": SOURCE},
            {
                "id": "d3", "type": "distance", "from": "p0", "to": "p3",
                "axis": "X", "value": 2, "source": SOURCE,
            },
        ],
        "unresolved": [],
    }


def assert_failure(result: GeometryResult, status: str) -> None:
    assert result.status == status
    assert result.is_closed is False
    assert result.vertices == []
    assert result.edges == []
    assert result.issues
    assert all(issue.reason.strip() for issue in result.issues)


def assert_geometry_consistent(result: GeometryResult) -> None:
    """Check geometric facts independently of the service's construction steps."""
    assert result.status == "Success"
    assert result.is_closed is True
    assert result.issues == []
    points = {vertex.id: vertex for vertex in result.vertices}
    assert len(points) == len(result.vertices)
    assert len({edge.id for edge in result.edges}) == len(result.edges)
    assert len(result.edges) == len(result.vertices)

    for index, edge in enumerate(result.edges):
        assert edge.to == result.edges[(index + 1) % len(result.edges)].from_
        start, end = points[edge.from_], points[edge.to]
        assert edge.from_ != edge.to
        if edge.type == "line":
            assert edge.length == pytest.approx(math.hypot(end.x - start.x, end.y - start.y))
            assert edge.length > 0
            continue

        for point in (start, end):
            assert math.hypot(point.x - edge.center.x, point.y - edge.center.y) == pytest.approx(edge.radius)
        start_angle = math.atan2(start.y - edge.center.y, start.x - edge.center.x)
        end_angle = math.atan2(end.y - edge.center.y, end.x - edge.center.x)
        angle = start_angle - end_angle if edge.clockwise else end_angle - start_angle
        assert edge.sweep_angle_degrees == pytest.approx(math.degrees(angle % math.tau))
        expected_size = "semicircle" if math.isclose(edge.sweep_angle_degrees, 180) else (
            "minor" if edge.sweep_angle_degrees < 180 else "major"
        )
        assert edge.arc_size == expected_size


def test_reference_example_coordinates_dimensions_and_closed_contour(example: dict[str, Any]) -> None:
    result = calculate(example)

    assert_geometry_consistent(result)
    assert len(result.vertices) == 16
    assert len(result.edges) == 16
    assert sum(edge.type == "arc" for edge in result.edges) == 4
    assert sum(edge.type == "line" for edge in result.edges) == 12
    points = {vertex.id: vertex for vertex in result.vertices}
    expected = [
        (0, 0), (40.5 - math.sqrt(40.5**2 - 10**2), 10), (5, 10),
        (12.5, 6), (12.5, 7.5), (25, 7.5), (25, 4.5), (31, 4.5), (31, 0),
    ]
    for index, coordinates in enumerate(expected):
        point = points[f"p{index}"]
        assert (point.x, point.y) == pytest.approx(coordinates)

    for dimension in example["dimensions"]:
        if dimension["type"] == "diameter":
            assert 2 * points[dimension["vertex"]].y == pytest.approx(dimension["value"])
        else:
            coordinate = dimension["axis"].lower()
            difference = getattr(points[dimension["to"]], coordinate) - getattr(points[dimension["from"]], coordinate)
            assert difference == pytest.approx(dimension["value"])


def test_mirrored_edges_reverse_order_and_preserve_arc_traversal(example: dict[str, Any]) -> None:
    result = calculate(example)

    assert_geometry_consistent(result)
    points = {vertex.id: vertex for vertex in result.vertices}
    half_count = len(example["edges"])
    for original, mirrored in zip(reversed(result.edges[:half_count]), result.edges[half_count:]):
        assert mirrored.type == original.type
        for original_id, mirrored_id in ((original.to, mirrored.from_), (original.from_, mirrored.to)):
            before, after = points[original_id], points[mirrored_id]
            assert (after.x, after.y) == pytest.approx((before.x, -before.y))
            if before.y == 0:
                assert mirrored_id == original_id
        if original.type == "arc":
            assert (mirrored.center.x, mirrored.center.y) == pytest.approx((original.center.x, -original.center.y))
            assert mirrored.radius == pytest.approx(original.radius)
            assert mirrored.sweep_angle_degrees == pytest.approx(original.sweep_angle_degrees)
            assert mirrored.clockwise == original.clockwise
            assert mirrored.shape == original.shape


def test_calculation_preserves_input_and_repeated_calls_are_independent(example: dict[str, Any]) -> None:
    extraction = ExtractionResult.model_validate(example)
    before = deepcopy(extraction.model_dump())
    service = GeometryCalculationService()

    first = service.calculate(extraction)
    assert_failure(service.calculate(ExtractionResult.model_validate({**example, "dimensions": []})), "Unresolved")
    second = service.calculate(extraction)

    assert extraction.model_dump() == before
    assert first.model_dump() == second.model_dump()
    assert_geometry_consistent(first)


def test_dimension_order_does_not_change_result(example: dict[str, Any]) -> None:
    expected = calculate(example)
    example["dimensions"].reverse()

    actual = calculate(example)

    assert_geometry_consistent(actual)
    assert actual.model_dump() == expected.model_dump()


def test_line_only_profile_and_signed_y_dimensions() -> None:
    data = arc_profile("minor")
    data["edges"][1] = {
        "id": "e2", "type": "line", "from": "p1", "to": "p2", "direction": "+X",
    }
    # The final vertex precedes p2 in the dimension, despite coming later in the chain.
    data["dimensions"] = [
        {
            "id": "d1", "type": "distance", "from": "p3", "to": "p2",
            "axis": "Y", "value": 3, "source": SOURCE,
        },
        {
            "id": "d2", "type": "distance", "from": "p0", "to": "p3",
            "axis": "X", "value": 2, "source": SOURCE,
        },
    ]

    result = calculate(data)

    assert_geometry_consistent(result)
    assert len(result.vertices) == 6
    assert all(edge.type == "line" for edge in result.edges)
    points = {vertex.id: vertex for vertex in result.vertices}
    assert (points["p1"].x, points["p1"].y) == pytest.approx((0, 3))
    assert (points["p2"].x, points["p2"].y) == pytest.approx((2, 3))


def test_coupled_circles_find_coordinates_when_local_rules_cannot_progress() -> None:
    # Initially neither p1 nor p2 has a known coordinate. Two radius constraints,
    # the common height and the horizontal gap together determine both points.
    data = arc_profile("minor")
    for index, start, end in ((0, "p0", "p1"), (2, "p2", "p3")):
        data["edges"][index] = {
            "id": f"e{index + 1}", "type": "arc", "from": start, "to": end,
            "radius": 5, "clockwise": True, "shape": "out", "arc_size": "minor",
            "center_constraint": "on_symmetry_axis", "source": SOURCE,
        }
    data["edges"][1] = {
        "id": "e2", "type": "line", "from": "p1", "to": "p2", "direction": "+X",
    }
    data["dimensions"] = [
        {
            "id": "d1", "type": "distance", "from": "p0", "to": "p3",
            "axis": "X", "value": 10, "source": SOURCE,
        },
        {
            "id": "d2", "type": "distance", "from": "p1", "to": "p2",
            "axis": "X", "value": 6, "source": SOURCE,
        },
    ]

    result = calculate(data)

    assert_geometry_consistent(result)
    points = {vertex.id: vertex for vertex in result.vertices}
    assert (points["p1"].x, points["p1"].y) == pytest.approx((2, 4))
    assert (points["p2"].x, points["p2"].y) == pytest.approx((8, 4))
    for arc in (edge for edge in result.edges if edge.type == "arc"):
        assert (arc.center.x, arc.center.y) == pytest.approx((5, 0))


@pytest.mark.parametrize(
    ("arc_size", "radius", "center", "sweep"),
    [
        ("minor", math.sqrt(2), (1, 2), 90),
        ("major", math.sqrt(2), (1, 4), 270),
        ("semicircle", 1, (1, 3), 180),
    ],
)
def test_arc_size_selects_correct_center_and_sweep(
    arc_size: str, radius: float, center: tuple[float, float], sweep: float,
) -> None:
    result = calculate(arc_profile(arc_size, radius))

    assert_geometry_consistent(result)
    arc = next(edge for edge in result.edges if edge.id == "e2")
    assert (arc.center.x, arc.center.y) == pytest.approx(center)
    assert arc.sweep_angle_degrees == pytest.approx(sweep)


def test_missing_arc_size_reports_genuine_geometric_ambiguity() -> None:
    assert_failure(calculate(arc_profile(None)), "Ambiguous")


def test_one_axis_semicircle_builds_a_complete_circle_without_duplicate_endpoints() -> None:
    data = arc_profile("semicircle", radius=5)
    data["vertices"] = [data["vertices"][0], {"id": "p1", "x": None, "y": 0}]
    data["edges"] = [{
        **data["edges"][1], "id": "e1", "from": "p0", "to": "p1",
        "center_constraint": "on_symmetry_axis",
    }]
    data["dimensions"] = []

    result = calculate(data)

    assert_geometry_consistent(result)
    assert len(result.vertices) == len(result.edges) == 2
    assert (result.vertices[1].x, result.vertices[1].y) == pytest.approx((10, 0))
    assert all(edge.arc_size == "semicircle" for edge in result.edges)


def test_recorded_arc_size_uncertainty_still_reports_geometric_ambiguity() -> None:
    data = arc_profile(None)
    data["unresolved"] = [{"target": "e2", "reason": "The arc size is unclear."}]

    assert_failure(calculate(data), "Ambiguous")


@pytest.mark.parametrize(("arc_size", "radius"), [("minor", 0.9), ("major", 1), ("semicircle", math.sqrt(2))])
def test_impossible_radius_or_arc_size_is_invalid(arc_size: str, radius: float) -> None:
    assert_failure(calculate(arc_profile(arc_size, radius)), "Invalid")


def test_no_progress_returns_unresolved() -> None:
    data = arc_profile("minor")
    data["dimensions"] = []

    assert_failure(calculate(data), "Unresolved")


def test_conflicting_dimension_is_invalid(example: dict[str, Any]) -> None:
    example["dimensions"].append({
        "id": "d9", "type": "diameter", "vertex": "p2", "value": 21, "source": SOURCE,
    })

    assert_failure(calculate(example), "Invalid")


def test_conflicting_distance_cycle_is_detected_without_known_coordinates() -> None:
    data = arc_profile("minor")
    data["edges"][0] = {
        "id": "e1", "type": "arc", "from": "p0", "to": "p1",
        "radius": 5, "clockwise": True, "shape": "out", "arc_size": "minor",
        "center_constraint": "on_symmetry_axis", "source": SOURCE,
    }
    data["edges"][1] = {
        "id": "e2", "type": "line", "from": "p1", "to": "p2", "direction": "+X",
    }
    # Both ends of this horizontal gap are still unknown, but 2 and 3 conflict.
    data["dimensions"] = [
        {"id": f"d{index}", "type": "distance", "from": "p1", "to": "p2",
         "axis": "X", "value": distance, "source": SOURCE}
        for index, distance in ((1, 2), (2, 3))
    ]

    assert_failure(calculate(data), "Invalid")


def test_shape_and_clockwise_must_agree_with_material_side() -> None:
    data = arc_profile("minor")
    data["edges"][1]["shape"] = "in"

    assert_failure(calculate(data), "Invalid")


def test_line_direction_conflicting_with_dimensions_is_invalid(example: dict[str, Any]) -> None:
    example["edges"][3]["direction"] = "-Y"

    assert_failure(calculate(example), "Invalid")


def test_self_crossing_upper_profile_is_invalid() -> None:
    # The vertical segment at x=2 crosses the earlier horizontal segment at y=4.
    coordinates = [(0, 0), (0, 4), (4, 4), (4, 1), (2, 1), (2, 5), (6, 5), (6, 0)]
    directions = ["+Y", "+X", "-Y", "-X", "+Y", "+X", "-Y"]
    data = arc_profile("minor")
    data["vertices"] = [
        {"id": f"p{index}", "x": 0 if index == 0 else None,
         "y": 0 if index in (0, len(coordinates) - 1) else None}
        for index in range(len(coordinates))
    ]
    data["edges"] = [
        {
            "id": f"e{index + 1}", "type": "line", "from": f"p{index}",
            "to": f"p{index + 1}", "direction": direction,
        }
        for index, direction in enumerate(directions)
    ]
    data["dimensions"] = []
    for index, (x, y) in enumerate(coordinates):
        if y:
            data["dimensions"].append({
                "id": f"d{len(data['dimensions']) + 1}", "type": "diameter",
                "vertex": f"p{index}", "value": 2 * y, "source": SOURCE,
            })
        if x:
            data["dimensions"].append({
                "id": f"d{len(data['dimensions']) + 1}", "type": "distance",
                "from": "p0", "to": f"p{index}", "axis": "X", "value": x,
                "source": SOURCE,
            })

    assert_failure(calculate(data), "Invalid")


@pytest.mark.parametrize("unknown", ["dimension", "radius", "direction", "shape", "issue"])
def test_unknown_input_does_not_become_an_invented_numeric_result(example: dict[str, Any], unknown: str) -> None:
    if unknown == "dimension":
        example["dimensions"][0]["value"] = None
    elif unknown == "radius":
        example["edges"][2]["radius"] = None
    elif unknown == "direction":
        example["edges"][1]["direction"] = None
    elif unknown == "shape":
        example["edges"][2]["shape"] = None
    else:
        example["unresolved"] = [{"target": "e3", "reason": "The drawing annotation is unclear."}]

    assert_failure(calculate(example), "Unresolved")


@pytest.mark.parametrize("malformation", ["missing_vertex", "gap", "duplicate_vertex", "duplicate_edge", "duplicate_dimension", "bad_origin"])
def test_invalid_references_and_topology_return_diagnostics(example: dict[str, Any], malformation: str) -> None:
    if malformation == "missing_vertex":
        example["dimensions"][0]["to"] = "p99"
    elif malformation == "gap":
        example["edges"][1]["from"] = "p0"
    elif malformation == "duplicate_vertex":
        example["vertices"][1]["id"] = "p0"
    elif malformation == "duplicate_edge":
        example["edges"][1]["id"] = "e1"
    elif malformation == "duplicate_dimension":
        example["dimensions"][1]["id"] = "d1"
    else:
        example["profile"]["origin_vertex"] = "p1"

    assert_failure(calculate(example), "Invalid")


def test_dimensioned_side_view_stepped_shaft_needs_no_section() -> None:
    data = {
        "schema_version": "2.0", "units": "mm",
        "profile": {"view": "Side view", "half": "upper", "symmetry_axis": "X", "origin_vertex": "p0"},
        "vertices": [
            {"id": f"p{i}", "x": 0 if i == 0 else None, "y": 0 if i in (0, 7) else None}
            for i in range(8)
        ],
        "edges": [
            {"id": f"e{i + 1}", "type": "line", "from": f"p{i}", "to": f"p{i + 1}", "direction": direction}
            for i, direction in enumerate(["+Y", "+X", "-Y", "+X", "-Y", "+X", "-Y"])
        ],
        "dimensions": [
            {"id": f"d{i + 1}", "type": "diameter", "vertex": vertex, "value": diameter,
             "source": {"view": "Side view", "text": f"Ø{diameter}"}}
            for i, (vertex, diameter) in enumerate([("p1", 20), ("p3", 14), ("p5", 10)])
        ] + [
            {"id": f"d{i + 4}", "type": "distance", "from": start, "to": end, "axis": "X", "value": 10,
             "source": {"view": "Side view", "text": "10"}}
            for i, (start, end) in enumerate([("p1", "p2"), ("p3", "p4"), ("p5", "p6")])
        ],
        "unresolved": [],
    }
    result = calculate(data)
    assert_geometry_consistent(result)
    points = {point.id: (point.x, point.y) for point in result.vertices}
    assert points['p1'] == (0, 10)
    assert points['p3'] == (10, 7)
    assert points['p5'] == (20, 5)
    assert points['p7'] == (30, 0)
    assert min(point.y for point in result.vertices) == -10
    # Real uncertainty remains blocking; a numerically solvable fit is not proof.
    data['unresolved'] = [{"target": "d2", "reason": "The diameter attachment is unclear."}]
    assert_failure(calculate(data), 'Unresolved')
