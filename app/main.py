from fastapi import FastAPI

from app.api.contour_extraction import router as contour_extraction_router
from app.api.error_handlers import (
    contour_extraction_error_handler,
    contour_not_extracted_error_handler,
    drawing_image_validation_error_handler,
)
from app.services.contour_extraction import ContourExtractionError, ContourNotExtractedError
from app.services.image_validation import DrawingImageValidationError

app = FastAPI(
    title="CADAICO CAD Builder API",
    description="A minimal FastAPI application.",
    version="0.1.0",
)

app.include_router(contour_extraction_router, prefix="/api/v1")
app.add_exception_handler(ContourExtractionError, contour_extraction_error_handler)
app.add_exception_handler(ContourNotExtractedError, contour_not_extracted_error_handler)
app.add_exception_handler(
    DrawingImageValidationError,
    drawing_image_validation_error_handler,
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello, FastAPI!"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
