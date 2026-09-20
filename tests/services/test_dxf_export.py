from copy import deepcopy

import pytest

from app.models.geometry import GeometryResult
from app.services.dxf_export import DxfExportError, DxfExportService


GEOMETRY = {
    "status": "Success",
    "units": "mm",
    "profile": {
        "view": "test",
        "half": "upper",
        "symmetry_axis": "X",
        "origin_vertex": "p0",
    },
    "is_closed": True,
    "vertices": [
        {"id": "p0", "x": 1, "y": 0},
        {"id": "p1", "x": 0, "y": 1},
    ],
    "edges": [
        {
            "id": "e1",
            "type": "arc",
            "from": "p0",
            "to": "p1",
            "center": {"x": 0, "y": 0},
            "radius": 1,
            "clockwise": True,
            "sweep_angle_degrees": 270,
            "shape": "out",
            "arc_size": "major",
        },
        {
            "id": "e2",
            "type": "line",
            "from": "p1",
            "to": "p0",
            "length": 2**0.5,
        },
    ],
    "issues": [],
}


def pairs(text: str) -> list[tuple[int, str]]:
    lines = text.strip().splitlines()
    return [(int(lines[index]), lines[index + 1]) for index in range(0, len(lines), 2)]


def arc_angles(text: str) -> tuple[float, float]:
    values = pairs(text)
    start = next(float(value) for code, value in values if code == 50)
    end = next(float(value) for code, value in values if code == 51)
    return start, end


def test_dxf_uses_mm_and_native_line_and_arc_entities() -> None:
    values = pairs(DxfExportService().export(GeometryResult.model_validate(GEOMETRY)))
    units_index = values.index((9, "$INSUNITS"))

    assert values[units_index + 1] == (70, "4")
    assert [
        value
        for code, value in values
        if code == 0 and value in {"LINE", "ARC"}
    ] == ["ARC", "LINE"]
    assert (0, "TEXT") not in values
    assert (0, "POINT") not in values
    assert values[-1] == (0, "EOF")


def test_clockwise_major_arc_preserves_its_full_sweep() -> None:
    start, end = arc_angles(
        DxfExportService().export(GeometryResult.model_validate(GEOMETRY))
    )

    assert start == 90
    assert end == 0
    assert (end - start + 360) % 360 == 270


def test_counterclockwise_minor_arc_preserves_world_angles() -> None:
    data = deepcopy(GEOMETRY)
    data["edges"][0].update(
        clockwise=False,
        sweep_angle_degrees=90,
        arc_size="minor",
    )

    assert arc_angles(
        DxfExportService().export(GeometryResult.model_validate(data))
    ) == (0, 90)


def test_unsolved_geometry_cannot_be_exported() -> None:
    data = deepcopy(GEOMETRY)
    data.update(status="Unresolved", is_closed=False, vertices=[], edges=[])

    with pytest.raises(DxfExportError):
        DxfExportService().export(GeometryResult.model_validate(data))
