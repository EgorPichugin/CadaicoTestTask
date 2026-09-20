import asyncio
import json
from pathlib import Path

import pytest

from app.cli.process_drawing import build_parser, run_pipeline
from app.models.extraction import ExtractionResult
from app.services.drawing_processing import DrawingProcessingResult
from app.services.dxf_export import DxfExportService
from app.services.geometry_calculation import GeometryCalculationService
from tests.services.test_contour_extraction import VALID_RESULT


class FakeProcessor:
    def __init__(self, extraction: ExtractionResult) -> None:
        self.extraction = extraction
        self.calls = 0

    async def process_with_extraction(self, drawing) -> DrawingProcessingResult:
        self.calls += 1
        assert drawing.filename == "drawing.png"
        assert drawing.media_type == "image/png"
        assert drawing.content.startswith(b"\x89PNG\r\n\x1a\n")
        geometry = GeometryCalculationService().calculate(self.extraction)
        return DrawingProcessingResult(self.extraction, geometry)


def image(path: Path) -> Path:
    path.write_bytes(b"\x89PNG\r\n\x1a\nexample")
    return path


def test_image_argument_is_optional_for_file_picker() -> None:
    assert build_parser().parse_args([]).image is None
    assert build_parser().parse_args(["drawing.jpg"]).image == Path("drawing.jpg")


def test_pipeline_writes_both_json_files_and_dxf(tmp_path: Path) -> None:
    extraction = ExtractionResult.model_validate_json(
        (Path(__file__).resolve().parents[1] / "extraction.example.json").read_text(
            encoding="utf-8"
        )
    )
    processor = FakeProcessor(extraction)
    output = tmp_path / "result"

    result = asyncio.run(
        run_pipeline(image(tmp_path / "drawing.png"), output, processor, DxfExportService())
    )

    assert result.geometry.status == "Success"
    assert processor.calls == 1
    assert json.loads((output / "extraction_result.json").read_text(encoding="utf-8"))
    assert json.loads((output / "geometry_result.json").read_text(encoding="utf-8"))[
        "is_closed"
    ] is True
    assert b"\r\nARC\r\n" in (output / "contour.dxf").read_bytes()


def test_unsolved_geometry_is_saved_without_dxf(tmp_path: Path) -> None:
    processor = FakeProcessor(ExtractionResult.model_validate(VALID_RESULT))
    output = tmp_path / "result"

    result = asyncio.run(
        run_pipeline(image(tmp_path / "drawing.png"), output, processor, DxfExportService())
    )

    assert result.geometry.status == "Unresolved"
    assert (output / "extraction_result.json").is_file()
    assert (output / "geometry_result.json").is_file()
    assert not (output / "contour.dxf").exists()


def test_existing_output_directory_is_never_replaced(tmp_path: Path) -> None:
    processor = FakeProcessor(ExtractionResult.model_validate(VALID_RESULT))
    output = tmp_path / "result"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("previous run", encoding="utf-8")

    with pytest.raises(FileExistsError):
        asyncio.run(
            run_pipeline(
                image(tmp_path / "drawing.png"),
                output,
                processor,
                DxfExportService(),
            )
        )

    assert processor.calls == 0
    assert marker.read_text(encoding="utf-8") == "previous run"
