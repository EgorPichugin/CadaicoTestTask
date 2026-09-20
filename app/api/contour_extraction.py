from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.drawing_upload import read_uploaded_drawing
from app.dependencies import get_drawing_processing_service, get_dxf_export_service
from app.models.artifacts import DrawingArtifacts
from app.models.drawing import DrawingImage
from app.models.geometry import GeometryStatus
from app.services.drawing_processing import DrawingProcessingService
from app.services.dxf_export import DxfExportService

router = APIRouter(prefix="/extractions", tags=["contour extraction"])


@router.post(
    "",
    response_model=DrawingArtifacts,
    status_code=status.HTTP_200_OK,
    summary="Extract a contour and calculate its geometry",
)
async def extract_drawing_contour(
    drawing: Annotated[DrawingImage, Depends(read_uploaded_drawing)],
    service: Annotated[
        DrawingProcessingService,
        Depends(get_drawing_processing_service),
    ],
    dxf_exporter: Annotated[
        DxfExportService,
        Depends(get_dxf_export_service),
    ],
) -> DrawingArtifacts:
    geometry = await service.process(drawing)
    dxf = (
        dxf_exporter.export(geometry)
        if geometry.status == GeometryStatus.SUCCESS
        else None
    )
    return DrawingArtifacts(geometry=geometry, dxf=dxf)
