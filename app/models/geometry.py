from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, FiniteFloat

from app.models.extraction import Profile, StrictModel


class Point(StrictModel):
    x: FiniteFloat
    y: FiniteFloat


class GeometryVertex(Point):
    id: str = Field(pattern=r"^p[0-9]+$")


class GeometryLine(StrictModel):
    id: str = Field(pattern=r"^e[0-9]+$")
    type: Literal["line"]
    from_: str = Field(alias="from", pattern=r"^p[0-9]+$")
    to: str = Field(pattern=r"^p[0-9]+$")
    length: FiniteFloat = Field(gt=0)


class GeometryArc(StrictModel):
    id: str = Field(pattern=r"^e[0-9]+$")
    type: Literal["arc"]
    from_: str = Field(alias="from", pattern=r"^p[0-9]+$")
    to: str = Field(pattern=r"^p[0-9]+$")
    radius: FiniteFloat = Field(gt=0)
    center: Point
    clockwise: bool
    shape: Literal["in", "out"]
    arc_size: Literal["minor", "semicircle", "major"]
    sweep_angle_degrees: FiniteFloat = Field(
        gt=0, lt=360,
        description="Positive sweep in degrees; clockwise determines traversal direction.",
    )


GeometryEdge = Annotated[GeometryLine | GeometryArc, Field(discriminator="type")]


class GeometryStatus(StrEnum):
    SUCCESS = "Success"
    UNRESOLVED = "Unresolved"
    AMBIGUOUS = "Ambiguous"
    INVALID = "Invalid"


class GeometryIssue(StrictModel):
    target: str | None = None
    reason: str = Field(min_length=1)


class GeometryResult(StrictModel):
    status: GeometryStatus
    units: Literal["mm"]
    profile: Profile = Field(
        description="Source half-profile metadata; successful vertices and edges describe the full closed contour."
    )
    is_closed: bool = False
    vertices: list[GeometryVertex] = Field(default_factory=list)
    edges: list[GeometryEdge] = Field(default_factory=list)
    issues: list[GeometryIssue] = Field(default_factory=list)
