import asyncio

import pytest

from app.models.drawing import DrawingImage
from app.models.extraction import ExtractionResult
from app.models.geometry import GeometryResult
from app.services.drawing_processing import DrawingProcessingService
from app.services.geometry_calculation import GeometryCalculationService
from tests.services.test_contour_extraction import VALID_RESULT


GEOMETRY = {
    "units": "mm",
    "profile": VALID_RESULT["profile"],
    "status": "Success",
    "is_closed": True,
    "issues": [],
    "vertices": [
        {"id": "p0", "x": 0, "y": 0},
        {"id": "p1", "x": 0, "y": 5},
        {"id": "p2", "x": 10, "y": 5},
        {"id": "p3", "x": 10, "y": 0},
        {"id": "p4", "x": 10, "y": -5},
        {"id": "p5", "x": 0, "y": -5},
    ],
    "edges": [
        {"id": "e1", "type": "line", "from": "p0", "to": "p1", "length": 5},
        {"id": "e2", "type": "line", "from": "p1", "to": "p2", "length": 10},
        {"id": "e3", "type": "line", "from": "p2", "to": "p3", "length": 5},
        {"id": "e4", "type": "line", "from": "p3", "to": "p4", "length": 5},
        {"id": "e5", "type": "line", "from": "p4", "to": "p5", "length": 10},
        {"id": "e6", "type": "line", "from": "p5", "to": "p0", "length": 5},
    ],
}
DRAWING = DrawingImage(content=b"image", filename="drawing.png", media_type="image/png")


def test_pipeline_passes_extraction_to_calculator_and_returns_geometry():
    calls = []
    extraction = ExtractionResult.model_validate(VALID_RESULT)
    original = extraction.model_dump()
    geometry = GeometryResult.model_validate(GEOMETRY)

    class Validator:
        def validate(self, drawing):
            calls.append("validate")

    class Extractor:
        async def extract(self, drawing):
            calls.append("extract")
            return extraction

    class Calculator:
        def calculate(self, value):
            calls.append("calculate")
            assert value is extraction
            return geometry

    service = DrawingProcessingService(Validator(), Extractor(), Calculator())
    assert asyncio.run(service.process(DRAWING)) is geometry
    assert calls == ["validate", "extract", "calculate"]
    assert extraction.model_dump() == original


@pytest.mark.parametrize("failed_stage", ["validate", "extract"])
def test_pipeline_stops_before_calculation_on_upstream_failure(failed_stage):
    calls = []

    class Validator:
        def validate(self, drawing):
            calls.append("validate")
            if failed_stage == "validate":
                raise ValueError("validation failed")

    class Extractor:
        async def extract(self, drawing):
            calls.append("extract")
            raise ValueError("extraction failed")

    class Calculator:
        def calculate(self, value):
            pytest.fail("Calculation must not run after an upstream failure")

    with pytest.raises(ValueError):
        asyncio.run(DrawingProcessingService(Validator(), Extractor(), Calculator()).process(DRAWING))
    assert calls == (["validate"] if failed_stage == "validate" else ["validate", "extract"])


def test_calculation_reports_unresolved_without_modifying_input():
    extraction = ExtractionResult.model_validate(VALID_RESULT)
    original = extraction.model_dump()

    result = GeometryCalculationService().calculate(extraction)

    assert result.status == "Unresolved"
    assert result.is_closed is False
    assert result.vertices == []
    assert result.edges == []
    assert result.issues
    assert extraction.model_dump() == original
