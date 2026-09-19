from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DrawingImage:
    content: bytes
    filename: str
    media_type: str
