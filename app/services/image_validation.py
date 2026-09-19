from app.config import (
    ALLOWED_DRAWING_IMAGE_TYPES,
    MAX_DRAWING_IMAGE_SIZE_BYTES,
)
from app.models.drawing import DrawingImage


class DrawingImageValidationError(ValueError):
    """Base error for an invalid uploaded drawing image."""


class UnsupportedImageTypeError(DrawingImageValidationError):
    pass


class EmptyDrawingImageError(DrawingImageValidationError):
    pass


class ImageTooLargeError(DrawingImageValidationError):
    pass


class ImageContentMismatchError(DrawingImageValidationError):
    pass


class DrawingImageValidator:
    def validate(self, drawing: DrawingImage) -> None:
        if drawing.media_type not in ALLOWED_DRAWING_IMAGE_TYPES:
            raise UnsupportedImageTypeError(
                "Supported image types: JPEG, PNG, and WebP."
            )
        if not drawing.content:
            raise EmptyDrawingImageError("The uploaded image is empty.")
        if len(drawing.content) > MAX_DRAWING_IMAGE_SIZE_BYTES:
            raise ImageTooLargeError("The uploaded image exceeds the 10 MB limit.")
        if not self._content_matches_media_type(drawing):
            raise ImageContentMismatchError(
                "The file content does not match its declared image type."
            )

    @staticmethod
    def _content_matches_media_type(drawing: DrawingImage) -> bool:
        content = drawing.content
        matches = {
            "image/jpeg": content.startswith(b"\xff\xd8\xff"),
            "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": (
                len(content) >= 12
                and content.startswith(b"RIFF")
                and content[8:12] == b"WEBP"
            ),
        }
        return matches.get(drawing.media_type, False)
