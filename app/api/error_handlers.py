import logging
import re

from openai import APIStatusError
from pydantic import ValidationError
from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.services.contour_extraction import ContourExtractionError, ContourNotExtractedError
from app.clients.drawing_analysis import (
    DrawingAnalysisConfigurationError,
    DrawingAnalysisTimeoutError,
)

from app.services.image_validation import (
    DrawingImageValidationError,
    EmptyDrawingImageError,
    ImageContentMismatchError,
    ImageTooLargeError,
    UnsupportedImageTypeError,
)


logger = logging.getLogger(__name__)


def log_analysis_failure(error: Exception) -> None:
    """Log diagnostics without exception bodies, images, prompts or credentials."""
    chain = []
    seen: set[int] = set()
    current: BaseException | None = error
    provider_status = None
    request_id = None
    validation_count = None
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(type(current).__name__)
        if isinstance(current, APIStatusError):
            provider_status = current.status_code
            candidate = current.request_id
            if isinstance(candidate, str) and re.fullmatch(r"req_[a-zA-Z0-9_-]{1,100}", candidate):
                request_id = candidate
        if isinstance(current, ValidationError):
            validation_count = current.error_count()
        current = current.__cause__ or current.__context__
    logger.error(
        "Drawing analysis failed: chain=%s provider_status=%s request_id=%s validation_errors=%s",
        " -> ".join(chain), provider_status, request_id, validation_count,
    )


async def contour_not_extracted_error_handler(
    _request: Request,
    error: ContourNotExtractedError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": str(error)},
    )


async def contour_extraction_error_handler(
    _request: Request,
    error: ContourExtractionError,
) -> JSONResponse:
    log_analysis_failure(error)
    code = status.HTTP_502_BAD_GATEWAY
    message = "Could not obtain a valid drawing analysis result. Please try again."
    if isinstance(error.__cause__, DrawingAnalysisConfigurationError):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
        message = "Drawing analysis is not configured yet. Contact the administrator."
    elif isinstance(error.__cause__, DrawingAnalysisTimeoutError):
        code = status.HTTP_504_GATEWAY_TIMEOUT
        message = "Drawing analysis timed out. Please try again."
    return JSONResponse(status_code=code, content={"detail": message})


async def drawing_image_validation_error_handler(
    _request: Request,
    error: DrawingImageValidationError,
) -> JSONResponse:
    status_by_error = {
        UnsupportedImageTypeError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        ImageTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
        EmptyDrawingImageError: status.HTTP_400_BAD_REQUEST,
        ImageContentMismatchError: status.HTTP_400_BAD_REQUEST,
    }
    return JSONResponse(
        status_code=status_by_error.get(type(error), status.HTTP_400_BAD_REQUEST),
        content={"detail": str(error)},
    )
