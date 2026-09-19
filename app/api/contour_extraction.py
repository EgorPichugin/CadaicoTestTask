from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.drawing_upload import read_uploaded_drawing
from app.dependencies import get_drawing_processing_service
from app.models.drawing import DrawingImage
from app.models.geometry import GeometryResult
from app.services.drawing_processing import DrawingProcessingService

router = APIRouter(prefix="/extractions", tags=["contour extraction"])


@router.post(
    "",
    response_model=GeometryResult,
    status_code=status.HTTP_200_OK,
    summary="Extract a contour and calculate its geometry",
)
async def extract_drawing_contour(
    drawing: Annotated[DrawingImage, Depends(read_uploaded_drawing)],
    service: Annotated[
        DrawingProcessingService,
        Depends(get_drawing_processing_service),
    ],
) -> GeometryResult:
    return await service.process(drawing)
