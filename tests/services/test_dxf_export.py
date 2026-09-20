from copy import deepcopy
from io import StringIO

import ezdxf
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
    arc = ezdxf.read(StringIO(text, newline=None)).modelspace().query("ARC")[0]
    return arc.dxf.start_angle, arc.dxf.end_angle


def test_export_has_complete_modelspace_structure_without_reader_repairs() -> None:
    text = DxfExportService().export(GeometryResult.model_validate(GEOMETRY))
    values = pairs(text)
    # Inspect raw output too: permissive readers can recreate missing sections.
    for section in ("TABLES", "BLOCKS", "OBJECTS"):
        assert (2, section) in values
    assert (2, "*Model_Space") in values

    document = ezdxf.read(StringIO(text, newline=None))
    modelspace = document.modelspace()
    owner = modelspace.block_record_handle
    assert len(modelspace) == 2
    assert document.units == 4
    for entity in modelspace:
        assert entity.dxf.owner == owner
        handle_index = values.index((5, entity.dxf.handle))
        assert values[handle_index + 1] == (330, owner)
    assert tuple(modelspace.query("LINE")[0].dxf.start) == (0, 1, 0)
    assert tuple(modelspace.query("LINE")[0].dxf.end) == (1, 0, 0)
    audit = document.audit()
    assert not audit.errors
    assert not audit.fixes


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
