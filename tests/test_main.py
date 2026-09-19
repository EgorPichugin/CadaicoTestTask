import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_drawing_analysis_client,
    get_drawing_processing_service,
    get_geometry_calculation_service,
)
from app.main import app
from app.models.drawing import DrawingImage
from app.models.geometry import GeometryResult
from tests.test_drawing_processing import GEOMETRY
from tests.services.test_contour_extraction import VALID_RESULT


class MockDrawingAnalysisClient:
    async def analyze(self, request):
        result = deepcopy(VALID_RESULT)
        result["profile"]["view"] = "mock_view"
        return result

PNG_BYTES = b"\x89PNG\r\n\x1a\nmock-image-content"
WEBP_BYTES = b"RIFF\x0d\x00\x00\x00WEBPmock-image"

client = TestClient(app)


def test_extraction_failure_reaches_api_as_user_message() -> None:
    message = "Could not extract the contour: the image is blurred. Upload a clearer drawing."

    class FailureClient:
        async def analyze(self, request):
            return {"schema_version": "2.0", "status": "error", "message": message}

    app.dependency_overrides[get_drawing_analysis_client] = FailureClient
    try:
        response = client.post(
            "/api/v1/extractions",
            files={"file": ("drawing.png", PNG_BYTES, "image/png")},
        )
    finally:
        app.dependency_overrides.pop(get_drawing_analysis_client, None)

    assert response.status_code == 422
    assert response.json() == {"detail": message}


def test_root() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, FastAPI!"}


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_pipeline_returns_unresolved_geometry() -> None:
    app.dependency_overrides[get_drawing_analysis_client] = MockDrawingAnalysisClient
    try:
        response = client.post(
            "/api/v1/extractions",
            files={"file": ("drawing.png", PNG_BYTES, "image/png")},
        )
    finally:
        app.dependency_overrides.pop(get_drawing_analysis_client, None)

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "Unresolved"
    assert result["is_closed"] is False
    assert result["vertices"] == []
    assert result["edges"] == []
    assert result["issues"]


def test_reference_extraction_returns_closed_geometry_through_api() -> None:
    example_path = Path(__file__).resolve().parents[1] / "extraction.example.json"
    extraction = json.loads(example_path.read_text(encoding="utf-8"))

    class ReferenceDrawingAnalysisClient:
        async def analyze(self, request):
            return deepcopy(extraction)

    app.dependency_overrides[get_drawing_analysis_client] = ReferenceDrawingAnalysisClient
    try:
        response = client.post(
            "/api/v1/extractions",
            files={"file": ("drawing.png", PNG_BYTES, "image/png")},
        )
    finally:
        app.dependency_overrides.pop(get_drawing_analysis_client, None)

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "Success", result["issues"]
    assert result["is_closed"] is True
    assert result["issues"] == []
    assert len(result["vertices"]) == 16
    assert len(result["edges"]) == 16
    assert sum(edge["type"] == "arc" for edge in result["edges"]) == 4
    assert all(
        edge["to"] == following["from"]
        for edge, following in zip(
            result["edges"], result["edges"][1:] + result["edges"][:1]
        )
    )


def test_missing_openai_key_returns_user_message(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/api/v1/extractions",
        files={"file": ("drawing.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Drawing analysis is not configured yet. Contact the administrator."
    }


def test_extract_drawing_rejects_unsupported_media_type() -> None:
    response = client.post(
        "/api/v1/extractions",
        files={"file": ("drawing.txt", b"not-an-image", "text/plain")},
    )

    assert response.status_code == 415


def test_extract_drawing_rejects_empty_file() -> None:
    response = client.post(
        "/api/v1/extractions",
        files={"file": ("drawing.png", b"", "image/png")},
    )

    assert response.status_code == 400


def test_extract_drawing_rejects_mismatched_file_content() -> None:
    response = client.post(
        "/api/v1/extractions",
        files={"file": ("drawing.png", b"not-a-png", "image/png")},
    )

    assert response.status_code == 400
    assert "does not match" in response.json()["detail"]


def test_extract_drawing_rejects_file_over_10_mb() -> None:
    oversized_png = b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024)
    response = client.post(
        "/api/v1/extractions",
        files={"file": ("large.png", oversized_png, "image/png")},
    )

    assert response.status_code == 413


def test_processing_service_can_be_replaced_through_di() -> None:
    class FakeDrawingProcessingService:
        async def process(self, drawing: DrawingImage) -> GeometryResult:
            assert drawing.filename == "custom.webp"
            assert drawing.media_type == "image/webp"
            assert drawing.content == WEBP_BYTES
            return GeometryResult.model_validate(GEOMETRY)

    app.dependency_overrides[
        get_drawing_processing_service
    ] = FakeDrawingProcessingService
    try:
        response = client.post(
            "/api/v1/extractions",
            files={"file": ("custom.webp", WEBP_BYTES, "image/webp")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == GEOMETRY


def test_geometry_calculator_can_be_replaced_through_di():
    class FakeCalculator:
        def calculate(self, extraction):
            assert extraction.profile.view == "mock_view"
            return GeometryResult.model_validate(GEOMETRY)

    app.dependency_overrides[get_drawing_analysis_client] = MockDrawingAnalysisClient
    app.dependency_overrides[get_geometry_calculation_service] = FakeCalculator
    try:
        response = client.post(
            "/api/v1/extractions",
            files={"file": ("drawing.png", PNG_BYTES, "image/png")},
        )
    finally:
        app.dependency_overrides.pop(get_drawing_analysis_client, None)
        app.dependency_overrides.pop(get_geometry_calculation_service, None)
    assert response.status_code == 200
    assert response.json() == GEOMETRY
    assert "dimensions" not in response.json()


@pytest.mark.parametrize("status", ["Unresolved", "Ambiguous", "Invalid"])
def test_unsuccessful_geometry_is_returned_with_status_and_issue(status):
    issue = {"target": "p1", "reason": "The contour could not be calculated."}

    class FakeCalculator:
        def calculate(self, extraction):
            return GeometryResult(
                units=extraction.units,
                profile=extraction.profile,
                status=status,
                issues=[issue],
            )

    app.dependency_overrides[get_drawing_analysis_client] = MockDrawingAnalysisClient
    app.dependency_overrides[get_geometry_calculation_service] = FakeCalculator
    try:
        response = client.post(
            "/api/v1/extractions",
            files={"file": ("drawing.png", PNG_BYTES, "image/png")},
        )
    finally:
        app.dependency_overrides.pop(get_drawing_analysis_client, None)
        app.dependency_overrides.pop(get_geometry_calculation_service, None)

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == status
    assert result["issues"] == [issue]
    assert result["vertices"] == []
    assert result["edges"] == []
    assert result["is_closed"] is False
