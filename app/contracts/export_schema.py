"""Regenerate documentation schemas: python -m app.contracts.export_schema."""

import json
from pathlib import Path

from pydantic import TypeAdapter

from app.models.extraction import ExtractionFailure, ExtractionResult


def export_schema() -> None:
    schema = TypeAdapter(ExtractionResult | ExtractionFailure).json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$comment"] = "Generated from app.models.extraction; do not edit manually."
    content = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
    app_directory = Path(__file__).resolve().parents[1]
    (app_directory / "resources" / "contour_extraction.schema.json").write_text(
        content, encoding="utf-8"
    )
    (app_directory.parent.parent / "extraction.schema.json").write_text(
        content, encoding="utf-8"
    )


if __name__ == "__main__":
    export_schema()
