from pydantic import TypeAdapter, ValidationError

from app.clients.drawing_analysis import (
    DrawingAnalysisClient,
    DrawingAnalysisClientError,
    DrawingAnalysisRequest,
)
from app.contracts.contour_extraction import ContourExtractionContract
from app.models.drawing import DrawingImage
from app.models.extraction import ExtractionFailure, ExtractionResult


ANALYSIS_RESPONSE = TypeAdapter(ExtractionResult | ExtractionFailure)


class ContourExtractionError(RuntimeError):
    """The drawing could not be converted into a contour result."""


class InvalidContourResultError(ContourExtractionError):
    """The analysis provider returned data outside the extraction contract."""


class ContourNotExtractedError(ContourExtractionError):
    """The drawing cannot be extracted; the message explains why to the user."""


class ContourExtractionService:
    def __init__(
        self,
        analysis_client: DrawingAnalysisClient,
        contract: ContourExtractionContract,
    ) -> None:
        self._analysis_client = analysis_client
        self._contract = contract

    async def extract(self, drawing: DrawingImage) -> ExtractionResult:
        request = DrawingAnalysisRequest(
            image=drawing.content,
            media_type=drawing.media_type,
            prompt=self._contract.prompt,
            response_model=self._contract.response_model,
        )

        try:
            raw_result = await self._analysis_client.analyze(request)
        except DrawingAnalysisClientError as error:
            raise ContourExtractionError("Drawing analysis failed.") from error

        try:
            result = ANALYSIS_RESPONSE.validate_python(raw_result)
        except ValidationError as error:
            raise InvalidContourResultError(
                "Drawing analysis returned an invalid contour result."
            ) from error

        if isinstance(result, ExtractionFailure):
            raise ContourNotExtractedError(result.message.strip())
        return result
