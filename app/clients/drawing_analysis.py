from dataclasses import dataclass
from typing import Any, Protocol

from app.models.extraction import ExtractionResponse


@dataclass(frozen=True, slots=True)
class DrawingAnalysisRequest:
    image: bytes
    media_type: str
    prompt: str
    response_model: type[ExtractionResponse]


class DrawingAnalysisClient(Protocol):
    """Analyze a drawing and return the provider's structured response."""

    async def analyze(
        self,
        request: DrawingAnalysisRequest,
    ) -> dict[str, Any]: ...


class DrawingAnalysisClientError(RuntimeError):
    """Base error raised by a drawing analysis provider adapter."""


class DrawingAnalysisConfigurationError(DrawingAnalysisClientError):
    """The analysis provider has not been configured."""


class DrawingAnalysisTimeoutError(DrawingAnalysisClientError):
    """The provider did not return a response before the timeout."""


class DrawingAnalysisProviderError(DrawingAnalysisClientError):
    """The provider rejected or failed to process the request."""
