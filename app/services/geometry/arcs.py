from dataclasses import dataclass
from math import atan2, degrees, hypot, pi, sqrt

from app.models.extraction import Arc
from app.models.geometry import GeometryArc, Point
from app.services.geometry.linear import propagate_linear
from app.services.geometry.state import CalculationState, GeometryConflict, TOLERANCE

XY = tuple[float, float]


@dataclass(frozen=True)
class ArcCandidate:
    start: XY
    end: XY
    geometry: GeometryArc

    def apply(self, state: CalculationState) -> None:
        arc = self.geometry
        for vertex, point in ((arc.from_, self.start), (arc.to, self.end)):
            for axis, value in zip(("x", "y"), point):
                state.set(vertex, axis, value, arc.id)
        if arc.id not in state.arcs:
            state.arcs[arc.id] = arc
            state.revision += 1


def chord_centers(start: XY, end: XY, radius: float) -> list[XY]:
    dx, dy = end[0] - start[0], end[1] - start[1]
    chord = hypot(dx, dy)
    if chord <= TOLERANCE or chord > 2 * radius + TOLERANCE:
        return []
    height = sqrt(max(0, radius * radius - (chord / 2) ** 2))
    middle = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    centers = [(middle[0] - dy * height / chord, middle[1] + dx * height / chord)]
    if height > TOLERANCE:
        centers.append((middle[0] + dy * height / chord, middle[1] - dx * height / chord))
    return centers


def axis_centers(point: XY, radius: float) -> list[XY]:
    if abs(point[1]) > radius + TOLERANCE:
        return []
    offset = sqrt(max(0, radius * radius - point[1] ** 2))
    return [(point[0] - offset, 0)] if offset <= TOLERANCE else [
        (point[0] - offset, 0), (point[0] + offset, 0)
    ]


def points_on_circle(state: CalculationState, vertex: str, center: XY,
                     radius: float) -> list[XY] | None:
    x, y = state.get(vertex, "x"), state.get(vertex, "y")
    if x is not None and y is not None:
        return [(x, y)] if abs(hypot(x - center[0], y - center[1]) - radius) <= TOLERANCE else []
    if x is None and y is None:
        return None
    fixed, center_fixed = (x, center[0]) if x is not None else (y, center[1])
    distance = abs(fixed - center_fixed)
    if distance > radius + TOLERANCE:
        return []
    offset = sqrt(max(0, radius * radius - distance * distance))
    offsets = [offset] if offset <= TOLERANCE else [offset, -offset]
    if x is not None:
        return [(x, center[1] + delta) for delta in offsets]
    return [(center[0] + delta, y) for delta in offsets]


def directed_angle(start: float, end: float, clockwise: bool) -> float:
    return ((start - end) if clockwise else (end - start)) % (2 * pi)


def make_arc(edge: Arc, start: XY, end: XY, center: XY) -> GeometryArc | None:
    # A simple upper boundary followed left-to-right encloses material on its right.
    # Consequently outward curvature is clockwise, inward curvature counterclockwise.
    if edge.clockwise is None or edge.shape is None or edge.radius is None:
        return None
    if edge.clockwise != (edge.shape == "out"):
        return None
    if hypot(end[0] - start[0], end[1] - start[1]) <= TOLERANCE:
        return None
    first = atan2(start[1] - center[1], start[0] - center[0])
    last = atan2(end[1] - center[1], end[0] - center[0])
    sweep = directed_angle(first, last, edge.clockwise)
    angular_tolerance = TOLERANCE / max(edge.radius, TOLERANCE)
    if sweep <= angular_tolerance or 2 * pi - sweep <= angular_tolerance:
        return None
    size = ("semicircle" if abs(sweep - pi) <= angular_tolerance
            else "minor" if sweep < pi else "major")
    if edge.arc_size is not None and edge.arc_size != size:
        return None
    if edge.center_constraint == "on_symmetry_axis" and abs(center[1]) > TOLERANCE:
        return None
    # Check the whole arc, not just its endpoints: a major arc can cross the axis.
    minimum_y = min(start[1], end[1])
    if directed_angle(first, -pi / 2, edge.clockwise) <= sweep + angular_tolerance:
        minimum_y = min(minimum_y, center[1] - edge.radius)
    if minimum_y < -TOLERANCE:
        return None
    return GeometryArc(
        id=edge.id, type="arc", from_=edge.from_, to=edge.to,
        radius=edge.radius, center=Point(x=center[0], y=center[1]),
        clockwise=edge.clockwise, shape=edge.shape, arc_size=size,
        sweep_angle_degrees=degrees(sweep),
    )


def arc_candidates(state: CalculationState, edge: Arc) -> list[ArcCandidate] | None:
    """None means not enough data; an empty list means all constructions failed."""
    if edge.radius is None or edge.clockwise is None or edge.shape is None:
        return None
    if edge.center_constraint == "unknown":
        return None
    start, end = state.point(edge.from_), state.point(edge.to)
    if start is not None and end is not None:
        centers = chord_centers(start, end, edge.radius)
    elif edge.center_constraint == "on_symmetry_axis" and (start or end) is not None:
        centers = axis_centers(start if start is not None else end, edge.radius)
    else:
        return None

    candidates = []
    for center in centers:
        starts = points_on_circle(state, edge.from_, center, edge.radius)
        ends = points_on_circle(state, edge.to, center, edge.radius)
        if starts is None or ends is None:
            return None
        for first in starts:
            for last in ends:
                geometry = make_arc(edge, first, last, center)
                if geometry is None:
                    continue
                candidate = ArcCandidate(first, last, geometry)
                trial = state.copy()
                try:
                    candidate.apply(trial)
                    propagate_linear(trial)
                except GeometryConflict:
                    continue
                candidates.append(candidate)
    return candidates


def apply_arcs(state: CalculationState) -> dict[str, list[ArcCandidate]]:
    choices = {}
    for edge in state.extraction.edges:
        if edge.type != "arc" or edge.id in state.arcs:
            continue
        candidates = arc_candidates(state, edge)
        if candidates is None:
            continue
        if not candidates:
            raise GeometryConflict(edge.id, "No arc satisfies its radius, size, direction and profile constraints.")
        if len(candidates) == 1:
            candidates[0].apply(state)
        else:
            choices[edge.id] = candidates
    return choices
