from typing import Annotated

from fastapi import File, UploadFile

from app.config import MAX_DRAWING_IMAGE_SIZE_BYTES
from app.models.drawing import DrawingImage


async def read_uploaded_drawing(
    file: Annotated[
        UploadFile,
        File(description="Engineering drawing in JPEG, PNG, or WebP format"),
    ],
) -> DrawingImage:
    """Adapt FastAPI's upload type to an application model.

    Reading at most one byte over the limit keeps an oversized upload from being
    copied into application memory in full. Validation is done by the validator.
    """
    content = await file.read(MAX_DRAWING_IMAGE_SIZE_BYTES + 1)
    return DrawingImage(
        content=content,
        filename=file.filename or "drawing",
        media_type=(file.content_type or "").lower(),
    )
