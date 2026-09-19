from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from app.models.extraction import ExtractionResponse

RESOURCE_DIRECTORY = Path(__file__).resolve().parent.parent / "resources"


@dataclass(frozen=True, slots=True)
class ContourExtractionContract:
    prompt: str
    response_model: type[ExtractionResponse] = ExtractionResponse


@lru_cache(maxsize=1)
def load_contour_extraction_contract() -> ContourExtractionContract:
    prompt = (RESOURCE_DIRECTORY / "contour_extraction_prompt.md").read_text(
        encoding="utf-8"
    )
    return ContourExtractionContract(prompt=prompt)
