from app.models.extraction import StrictModel
from app.models.geometry import GeometryResult


class DrawingArtifacts(StrictModel):
    """Calculated geometry and its ready-to-download CAD representation."""

    geometry: GeometryResult
    dxf: str | None
