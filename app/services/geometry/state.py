from copy import deepcopy
from dataclasses import dataclass, field
from math import isfinite

from app.models.extraction import ExtractionResult
from app.models.geometry import GeometryArc, GeometryIssue


# Absolute computational tolerance in mm, unrelated to manufacturing tolerances.
TOLERANCE = 1e-7
Coordinate = tuple[str, str]


class GeometryConflict(ValueError):
    def __init__(self, target: str | None, reason: str):
        super().__init__(reason)
        self.issue = GeometryIssue(target=target, reason=reason)


@dataclass
class CalculationState:
    extraction: ExtractionResult
    values: dict[Coordinate, float] = field(default_factory=dict)
    arcs: dict[str, GeometryArc] = field(default_factory=dict)
    revision: int = 0

    @classmethod
    def from_extraction(cls, extraction: ExtractionResult) -> "CalculationState":
        state = cls(extraction)
        for vertex in extraction.vertices:
            for axis in ("x", "y"):
                value = getattr(vertex, axis)
                if value is not None:
                    state.set(vertex.id, axis, float(value), vertex.id)
        return state

    def get(self, vertex: str, axis: str) -> float | None:
        return self.values.get((vertex, axis))

    def set(self, vertex: str, axis: str, value: float, target: str) -> None:
        if not isfinite(value):
            raise GeometryConflict(target, "A calculated coordinate is not finite.")
        key = (vertex, axis)
        previous = self.values.get(key)
        if previous is not None:
            if abs(previous - value) > TOLERANCE:
                raise GeometryConflict(
                    target, f"Conflicting values for {vertex}.{axis}: {previous:g} and {value:g}."
                )
            return
        self.values[key] = value
        self.revision += 1

    def point(self, vertex: str) -> tuple[float, float] | None:
        x, y = self.get(vertex, "x"), self.get(vertex, "y")
        return None if x is None or y is None else (x, y)

    def copy(self) -> "CalculationState":
        # Extraction is read-only; only the working values and arcs are copied.
        return CalculationState(self.extraction, self.values.copy(), deepcopy(self.arcs), self.revision)

    def coordinates(self) -> dict[str, tuple[float, float]]:
        return {v.id: point for v in self.extraction.vertices if (point := self.point(v.id)) is not None}


def validate_input(extraction: ExtractionResult) -> None:
    vertices, edges = extraction.vertices, extraction.edges
    objects = [*vertices, *edges, *extraction.dimensions]
    ids = [item.id for item in objects]
    if len(ids) != len(set(ids)):
        raise GeometryConflict(None, "Vertex, edge and dimension IDs must be unique.")
    vertex_ids = {v.id for v in vertices}
    if len(edges) != len(vertices) - 1:
        raise GeometryConflict(None, "The upper profile must be one open chain with N - 1 edges.")
    for start, edge, end in zip(vertices, edges, vertices[1:]):
        if edge.from_ != start.id or edge.to != end.id:
            raise GeometryConflict(edge.id, "The edge must connect consecutive listed vertices.")
        if edge.type == "arc" and edge.radius is not None and not isfinite(edge.radius):
            raise GeometryConflict(edge.id, "The radius must be finite.")
        if (edge.type == "arc" and edge.shape is not None and edge.clockwise is not None
                and edge.clockwise != (edge.shape == "out")):
            raise GeometryConflict(edge.id, "Arc shape and traversal disagree with material on the right of the upper chain.")
    if extraction.profile.origin_vertex != vertices[0].id:
        raise GeometryConflict(vertices[0].id, "The origin must be the first vertex.")
    if (vertices[0].x, vertices[0].y) != (0, 0) or vertices[-1].y != 0:
        raise GeometryConflict(None, "The origin must be (0, 0) and both chain ends must lie on the X axis.")
    for dimension in extraction.dimensions:
        references = ([dimension.vertex] if dimension.type == "diameter"
                      else [dimension.from_, dimension.to])
        if any(reference not in vertex_ids for reference in references):
            raise GeometryConflict(dimension.id, "The dimension references a missing vertex.")
        if dimension.type == "distance" and dimension.from_ == dimension.to:
            raise GeometryConflict(dimension.id, "A distance must reference two different vertices.")
        if dimension.value is not None and not isfinite(dimension.value):
            raise GeometryConflict(dimension.id, "The dimension must be finite.")
    for issue in extraction.unresolved:
        if issue.target is not None and issue.target not in ids:
            raise GeometryConflict(issue.target, "An unresolved issue references a missing object.")
