import os
from typing import Annotated

from fastapi import Depends

from app.clients.drawing_analysis import DrawingAnalysisClient
from app.clients.openai_drawing_analysis import OpenAIDrawingAnalysisClient
from app.contracts.contour_extraction import (
    ContourExtractionContract,
    load_contour_extraction_contract,
)
from app.services.contour_extraction import ContourExtractionService
from app.services.drawing_processing import DrawingProcessingService
from app.services.dxf_export import DxfExportService
from app.services.image_validation import DrawingImageValidator
from app.services.geometry_calculation import GeometryCalculationService


def get_drawing_analysis_client() -> DrawingAnalysisClient:
    return OpenAIDrawingAnalysisClient(api_key=os.getenv("OPENAI_API_KEY"))


def get_contour_extraction_contract() -> ContourExtractionContract:
    return load_contour_extraction_contract()


def get_contour_extraction_service(
    analysis_client: Annotated[
        DrawingAnalysisClient,
        Depends(get_drawing_analysis_client),
    ],
    contract: Annotated[
        ContourExtractionContract,
        Depends(get_contour_extraction_contract),
    ],
) -> ContourExtractionService:
    return ContourExtractionService(
        analysis_client=analysis_client,
        contract=contract,
    )


def get_drawing_image_validator() -> DrawingImageValidator:
    return DrawingImageValidator()


def get_geometry_calculation_service() -> GeometryCalculationService:
    return GeometryCalculationService()


def get_dxf_export_service() -> DxfExportService:
    return DxfExportService()


def get_drawing_processing_service(
    image_validator: Annotated[
        DrawingImageValidator,
        Depends(get_drawing_image_validator),
    ],
    contour_extractor: Annotated[
        ContourExtractionService,
        Depends(get_contour_extraction_service),
    ],
    geometry_calculator: Annotated[
        GeometryCalculationService,
        Depends(get_geometry_calculation_service),
    ],
) -> DrawingProcessingService:
    return DrawingProcessingService(
        image_validator=image_validator,
        contour_extractor=contour_extractor,
        geometry_calculator=geometry_calculator,
    )
