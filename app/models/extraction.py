from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Profile(StrictModel):
    view: str = Field(min_length=1)
    half: Literal["upper"]
    symmetry_axis: Literal["X"]
    origin_vertex: str = Field(
        pattern=r"^p[0-9]+$",
        description=(
            "Must be p0: the first listed vertex and start of the first edge, with x = 0 "
            "and y = 0."
        ),
    )


class Vertex(StrictModel):
    id: str = Field(pattern=r"^p[0-9]+$")
    x: Literal[0] | None
    y: Literal[0] | None


class Source(StrictModel):
    view: str = Field(min_length=1)
    text: str | None = Field(
        description=(
            "Dimension label from the drawing; decimal punctuation may be normalized. "
            "Null requires an unresolved issue."
        ),
    )


class Line(StrictModel):
    id: str = Field(
        pattern=r"^e[0-9]+$",
        description=(
            "Unique edge ID in traversal order: e1, e2, ... ."
        ),
    )
    type: Literal["line"]
    from_: str = Field(
        alias="from", pattern=r"^p[0-9]+$",
        description=(
            "Existing vertex ID: start of this edge in chain order; must equal the "
            "preceding edge endpoint when present."
        ),
    )
    to: str = Field(
        pattern=r"^p[0-9]+$",
        description=(
            "Existing vertex ID: the next vertex in chain order, distinct from from; must "
            "equal the next edge start when present."
        ),
    )
    direction: Literal["+X", "-X", "+Y", "-Y"] | None


PositiveValue = Annotated[
    float,
    Field(gt=0),
    # OpenAI supports minimum; Pydantic still rejects zero on parsing.
    WithJsonSchema({"type": "number", "minimum": 0, "description": "Strictly positive nominal value in mm; never zero."}),
]


class Arc(StrictModel):
    id: str = Field(
        pattern=r"^e[0-9]+$",
        description=(
            "Unique edge ID in traversal order: e1, e2, ... ."
        ),
    )
    type: Literal["arc"]
    from_: str = Field(
        alias="from", pattern=r"^p[0-9]+$",
        description=(
            "Existing vertex ID: start of this edge in chain order; must equal the "
            "preceding edge endpoint when present."
        ),
    )
    to: str = Field(
        pattern=r"^p[0-9]+$",
        description=(
            "Existing vertex ID: the next vertex in chain order, distinct from from; must "
            "equal the next edge start when present."
        ),
    )
    radius: PositiveValue | None
    clockwise: bool | None
    shape: Literal["in", "out"] | None = Field(
        description=(
            "Direction of the convex side of the arc relative to the part material: in "
            "points into the part; out points outward. Not the center location or "
            "traversal direction. Null requires an unresolved entry targeting this arc ID "
            "with the reason."
        ),
    )
    arc_size: Literal["minor", "semicircle", "major"] | None = Field(
        description=(
            "Classify the drawn arc from from to to: minor has a sweep below 180 "
            "degrees, semicircle exactly 180 degrees, major above 180 and below 360 "
            "degrees. Independent of shape and clockwise. Do not calculate an exact "
            "angle or assume minor. Null requires an unresolved entry targeting this "
            "arc ID with the reason."
        ),
    )
    center_constraint: Literal["on_symmetry_axis", "none", "unknown"] = Field(
        description=(
            "none means no extra center constraint; it does NOT mean the center is "
            "off-axis."
        ),
    )
    source: Source


Edge = Line | Arc


class Distance(StrictModel):
    id: str = Field(pattern=r"^d[0-9]+$")
    type: Literal["distance"]
    from_: str = Field(
        alias="from", pattern=r"^p[0-9]+$",
        description=(
            "Existing vertex ID at the lower coordinate on the measurement axis; distinct "
            "from to. Need not precede to in contour traversal order."
        ),
    )
    to: str = Field(
        pattern=r"^p[0-9]+$",
        description=(
            "Existing vertex ID at the higher coordinate on the measurement axis; "
            "distinct from from. Endpoints need not be adjacent."
        ),
    )
    axis: Literal["X", "Y"] = Field(
        description=(
            "Signed projection: to[axis] - from[axis] = positive value; not Euclidean "
            "distance."
        ),
    )
    value: PositiveValue | None
    source: Source


class Diameter(StrictModel):
    id: str = Field(pattern=r"^d[0-9]+$")
    type: Literal["diameter"]
    vertex: str = Field(
        pattern=r"^p[0-9]+$",
        description=(
            "Existing vertex ID on the surface to which the stated diameter belongs."
        ),
    )
    value: PositiveValue | None
    source: Source


Dimension = Distance | Diameter


class UnresolvedIssue(StrictModel):
    target: str | None = Field(
        description=(
            "An ID of a vertex, edge or dimension actually present in this response. Use "
            "null for a global issue or unassigned annotation, including references to "
            "omitted objects."
        ),
    )
    reason: str = Field(min_length=1)


class ExtractionResult(StrictModel):
    schema_version: Literal["2.0"]
    units: Literal["mm"]
    profile: Profile
    vertices: list[Vertex] = Field(
        min_length=2,
        description=(
            "Every chain vertex exactly once in traversal order, with unique IDs p0, p1, "
            "... . No unused vertices. First vertex is the origin (0, 0); last vertex has "
            "x = null and y = 0."
        ),
    )
    edges: list[Edge] = Field(
        min_length=1,
        description=(
            "Exactly one fewer edge than vertices. Unique IDs e1, e2, ... in traversal "
            "order: e1 connects p0 to p1, e2 connects p1 to p2, etc. Each to equals the "
            "next from. No self-loops, revisited vertices, branches, gaps or closing "
            "edge."
        ),
    )
    dimensions: list[Dimension] = Field(
        description=(
            "Unique IDs d1, d2, ... . All vertex references must exist in vertices. "
            "Record each stated dimension once."
        ),
    )
    unresolved: list[UnresolvedIssue]


class ExtractionFailure(StrictModel):
    schema_version: Literal["2.0"]
    status: Literal["error"]
    message: str = Field(
        min_length=1, max_length=1000, pattern=r"\S",
        description=(
            "Plain-text English explanation for the user: why contour extraction failed "
            "and, if known, what to change. No technical details, Markdown or HTML."
        ),
    )


class ExtractionResponse(StrictModel):
    """Object envelope required by OpenAI Structured Outputs."""

    result: ExtractionResult | ExtractionFailure
