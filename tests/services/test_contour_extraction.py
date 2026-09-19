import asyncio
from typing import Any

import pytest

from app.clients.drawing_analysis import (
    DrawingAnalysisClientError,
    DrawingAnalysisRequest,
)
from app.contracts.contour_extraction import ContourExtractionContract
from app.models.drawing import DrawingImage
from app.services.contour_extraction import (
    ContourExtractionError,
    ContourExtractionService,
    ContourNotExtractedError,
    InvalidContourResultError,
)

VALID_RESULT: dict[str, Any] = {
    "schema_version": "2.0",
    "units": "mm",
    "profile": {
        "view": "section_A_A",
        "half": "upper",
        "symmetry_axis": "X",
        "origin_vertex": "p0",
    },
    "vertices": [
        {"id": "p0", "x": 0, "y": 0},
        {"id": "p1", "x": None, "y": 0},
    ],
    "edges": [
        {
            "id": "e1",
            "type": "line",
            "from": "p0",
            "to": "p1",
            "direction": "+X",
        }
    ],
    "dimensions": [],
    "unresolved": [],
}

DRAWING = DrawingImage(
    content=b"drawing-bytes",
    filename="drawing.png",
    media_type="image/png",
)
CONTRACT = ContourExtractionContract(
    prompt="Extract the contour.",
)


def test_sends_drawing_prompt_and_schema_to_analysis_client() -> None:
    class RecordingClient:
        def __init__(self) -> None:
            self.request: DrawingAnalysisRequest | None = None

        async def analyze(
            self,
            request: DrawingAnalysisRequest,
        ) -> dict[str, Any]:
            self.request = request
            return VALID_RESULT

    client = RecordingClient()
    service = ContourExtractionService(client, CONTRACT)

    result = asyncio.run(service.extract(DRAWING))

    assert client.request is not None
    assert client.request.image == b"drawing-bytes"
    assert client.request.media_type == "image/png"
    assert client.request.prompt == "Extract the contour."
    assert client.request.response_model is CONTRACT.response_model
    assert result.profile.view == "section_A_A"


def test_rejects_result_outside_extraction_contract() -> None:
    class InvalidResultClient:
        async def analyze(
            self,
            request: DrawingAnalysisRequest,
        ) -> dict[str, Any]:
            return {"unexpected": True}

    service = ContourExtractionService(InvalidResultClient(), CONTRACT)

    with pytest.raises(InvalidContourResultError):
        asyncio.run(service.extract(DRAWING))


def test_wraps_analysis_client_error() -> None:
    class FailingClient:
        async def analyze(
            self,
            request: DrawingAnalysisRequest,
        ) -> dict[str, Any]:
            raise DrawingAnalysisClientError("provider details")

    service = ContourExtractionService(FailingClient(), CONTRACT)

    with pytest.raises(ContourExtractionError, match="Drawing analysis failed"):
        asyncio.run(service.extract(DRAWING))


def test_extraction_failure_preserves_user_message() -> None:
    message = "Could not extract the contour: the part boundaries are blurred."

    class FailureClient:
        async def analyze(self, request: DrawingAnalysisRequest) -> dict[str, Any]:
            return {"schema_version": "2.0", "status": "error", "message": message}

    with pytest.raises(ContourNotExtractedError) as error:
        asyncio.run(ContourExtractionService(FailureClient(), CONTRACT).extract(DRAWING))
    assert str(error.value) == message


@pytest.mark.parametrize(
    "response",
    [
        {"schema_version": "2.0", "status": "error"},
        {"schema_version": "2.0", "status": "error", "message": ""},
        {"schema_version": "2.0", "status": "error", "message": " \n\t"},
        {"schema_version": "2.0", "status": "error", "message": "x" * 1001},
        {"schema_version": "2.0", "status": "error", "message": 42},
        {**VALID_RESULT, "status": "error", "message": "Could not extract the contour."},
    ],
)
def test_rejects_malformed_failure(response: dict[str, Any]) -> None:
    class FailureClient:
        async def analyze(self, request: DrawingAnalysisRequest) -> dict[str, Any]:
            return response

    with pytest.raises(InvalidContourResultError):
        asyncio.run(ContourExtractionService(FailureClient(), CONTRACT).extract(DRAWING))
