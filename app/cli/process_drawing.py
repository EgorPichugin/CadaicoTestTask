"""Run the complete drawing pipeline without starting FastAPI."""

import argparse
import asyncio
import mimetypes
import os
import shutil
import sys
from pathlib import Path
from tempfile import mkdtemp

from dotenv import load_dotenv

from app.clients.openai_drawing_analysis import OpenAIDrawingAnalysisClient
from app.contracts.contour_extraction import load_contour_extraction_contract
from app.models.drawing import DrawingImage
from app.models.geometry import GeometryStatus
from app.services.contour_extraction import ContourExtractionError, ContourExtractionService
from app.services.drawing_processing import DrawingProcessingResult, DrawingProcessingService
from app.services.dxf_export import DxfExportService
from app.services.geometry_calculation import GeometryCalculationService
from app.services.image_validation import DrawingImageValidationError, DrawingImageValidator


PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Process a JPG, PNG or WebP drawing and save extraction JSON, geometry "
            "JSON and a DXF contour without starting the HTTP API."
        )
    )
    parser.add_argument(
        "image",
        nargs="?",
        type=Path,
        help="Path to the drawing image. Omit it to open a file picker.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="New output directory (default: <image-name>_result next to the image).",
    )
    return parser


def choose_image() -> Path | None:
    """Open the native file picker when no command-line path was supplied."""
    try:
        from tkinter import TclError, Tk, filedialog
    except ImportError as error:
        raise RuntimeError(
            "The file picker is unavailable. Pass the image path as an argument."
        ) from error

    try:
        root = Tk()
    except TclError as error:
        raise RuntimeError(
            "The file picker could not be opened. Pass the image path as an argument."
        ) from error
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            title="Select a technical drawing",
            filetypes=[
                ("Drawing images", "*.jpg *.jpeg *.png *.webp"),
                ("JPEG images", "*.jpg *.jpeg"),
                ("PNG images", "*.png"),
                ("WebP images", "*.webp"),
                ("All files", "*.*"),
            ],
        )
    finally:
        root.destroy()
    return Path(selected) if selected else None


def create_processor(api_key: str) -> DrawingProcessingService:
    extractor = ContourExtractionService(
        analysis_client=OpenAIDrawingAnalysisClient(api_key=api_key),
        contract=load_contour_extraction_contract(),
    )
    return DrawingProcessingService(
        image_validator=DrawingImageValidator(),
        contour_extractor=extractor,
        geometry_calculator=GeometryCalculationService(),
    )


def read_drawing(path: Path) -> DrawingImage:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return DrawingImage(
        content=path.read_bytes(),
        filename=path.name,
        media_type=media_type,
    )


async def run_pipeline(
    image_path: Path,
    output_directory: Path,
    processor: DrawingProcessingService,
    dxf_exporter: DxfExportService,
) -> DrawingProcessingResult:
    if output_directory.exists():
        raise FileExistsError(
            f"Output directory already exists: {output_directory}. "
            "Choose a new directory to preserve the previous run."
        )

    result = await processor.process_with_extraction(read_drawing(image_path))
    dxf = (
        dxf_exporter.export(result.geometry)
        if result.geometry.status == GeometryStatus.SUCCESS
        else None
    )
    write_artifacts(output_directory, result, dxf)
    return result


def write_artifacts(
    output_directory: Path,
    result: DrawingProcessingResult,
    dxf: str | None,
) -> None:
    """Stage all files and publish the completed directory in one rename."""
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        mkdtemp(
            prefix=f".{output_directory.name}.",
            suffix=".tmp",
            dir=output_directory.parent,
        )
    )
    try:
        (staging / "extraction_result.json").write_text(
            result.extraction.model_dump_json(by_alias=True, indent=2) + "\n",
            encoding="utf-8",
        )
        (staging / "geometry_result.json").write_text(
            result.geometry.model_dump_json(by_alias=True, indent=2) + "\n",
            encoding="utf-8",
        )
        if dxf is not None:
            (staging / "contour.dxf").write_text(dxf, encoding="ascii", newline="")
        os.replace(staging, output_directory)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        image_path = args.image or choose_image()
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    if image_path is None:
        print("No image selected.")
        return 0

    output_directory = args.output or image_path.with_name(f"{image_path.stem}_result")

    load_dotenv(PROJECT_DIRECTORY / ".env")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print(
            "Error: OPENAI_API_KEY is not configured. Set it in the environment "
            "or in backend/.env.",
            file=sys.stderr,
        )
        return 1

    try:
        result = asyncio.run(
            run_pipeline(
                image_path,
                output_directory,
                create_processor(api_key),
                DxfExportService(),
            )
        )
    except (OSError, DrawingImageValidationError, ContourExtractionError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    geometry = result.geometry
    print(f"Status: {geometry.status.value}")
    print(f"Vertices: {len(geometry.vertices)}; edges: {len(geometry.edges)}")
    print(f"Results saved: {output_directory.resolve()}")
    for issue in geometry.issues:
        print(f"{issue.target or 'Contour'}: {issue.reason}")
    return 0 if geometry.status == GeometryStatus.SUCCESS else 2


if __name__ == "__main__":
    raise SystemExit(main())
