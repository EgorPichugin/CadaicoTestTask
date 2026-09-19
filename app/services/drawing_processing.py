from typing import Protocol

from app.models.drawing import DrawingImage
from app.models.extraction import ExtractionResult
from app.models.geometry import GeometryResult


class ImageValidator(Protocol):
    def validate(self, drawing: DrawingImage) -> None: ...


class ContourExtractor(Protocol):
    async def extract(self, drawing: DrawingImage) -> ExtractionResult: ...


class GeometryCalculator(Protocol):
    def calculate(self, extraction: ExtractionResult) -> GeometryResult: ...


class DrawingProcessingService:
    """Coordinate image validation, extraction and geometry calculation."""

    def __init__(
        self,
        image_validator: ImageValidator,
        contour_extractor: ContourExtractor,
        geometry_calculator: GeometryCalculator,
    ) -> None:
        self._image_validator = image_validator
        self._contour_extractor = contour_extractor
        self._geometry_calculator = geometry_calculator

    async def process(self, drawing: DrawingImage) -> GeometryResult:
        self._image_validator.validate(drawing)
        extraction = await self._contour_extractor.extract(drawing)
        return self._geometry_calculator.calculate(extraction)
