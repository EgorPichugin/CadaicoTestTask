from app.models.extraction import ExtractionResult
from app.services.geometry.state import CalculationState, Coordinate, GeometryConflict, TOLERANCE


def check_difference_cycles(extraction: ExtractionResult) -> None:
    """Detect contradictory distance loops even if their coordinates are unknown.

    Temporary offsets are relative to an arbitrary vertex in each component;
    they are consistency checks, not coordinates to put in the output.
    """
    links: dict[Coordinate, list[tuple[Coordinate, float, str]]] = {}

    def connect(start: str, end: str, axis: str, delta: float, target: str) -> None:
        before, after = (start, axis), (end, axis)
        links.setdefault(before, []).append((after, delta, target))
        links.setdefault(after, []).append((before, -delta, target))

    for dimension in extraction.dimensions:
        if dimension.type == "distance" and dimension.value is not None:
            connect(dimension.from_, dimension.to, dimension.axis.lower(), dimension.value, dimension.id)
    for edge in extraction.edges:
        if edge.type == "line" and edge.direction is not None:
            connect(edge.from_, edge.to, "y" if edge.direction[1] == "X" else "x", 0, edge.id)

    offsets: dict[Coordinate, float] = {}
    for origin in links:
        if origin in offsets:
            continue
        offsets[origin] = 0
        pending = [origin]
        while pending:
            current = pending.pop()
            for neighbor, delta, target in links[current]:
                expected = offsets[current] + delta
                if neighbor not in offsets:
                    offsets[neighbor] = expected
                    pending.append(neighbor)
                elif abs(offsets[neighbor] - expected) > TOLERANCE:
                    raise GeometryConflict(target, "The distances and straight-line constraints form a contradictory loop.")


def apply_difference(state: CalculationState, start: str, end: str,
                     axis: str, distance: float, target: str) -> None:
    """Use end[axis] - start[axis] = distance in either direction."""
    before, after = state.get(start, axis), state.get(end, axis)
    if before is not None:
        state.set(end, axis, before + distance, target)
    elif after is not None:
        state.set(start, axis, after - distance, target)


def apply_dimensions(state: CalculationState) -> None:
    for dimension in state.extraction.dimensions:
        if dimension.value is None:
            continue
        if dimension.type == "diameter":
            state.set(dimension.vertex, "y", dimension.value / 2, dimension.id)
        else:
            apply_difference(state, dimension.from_, dimension.to,
                             dimension.axis.lower(), dimension.value, dimension.id)


def apply_lines(state: CalculationState) -> None:
    for edge in state.extraction.edges:
        if edge.type != "line" or edge.direction is None:
            continue
        moving_axis = edge.direction[1].lower()
        fixed_axis = "y" if moving_axis == "x" else "x"
        apply_difference(state, edge.from_, edge.to, fixed_axis, 0, edge.id)
        before, after = state.get(edge.from_, moving_axis), state.get(edge.to, moving_axis)
        if before is not None and after is not None:
            sign = 1 if edge.direction[0] == "+" else -1
            if sign * (after - before) <= TOLERANCE:
                raise GeometryConflict(edge.id, "The line has zero length or contradicts its direction.")


def check_upper_half(state: CalculationState) -> None:
    for vertex in state.extraction.vertices:
        y = state.get(vertex.id, "y")
        if y is not None and y < -TOLERANCE:
            raise GeometryConflict(vertex.id, "An upper-profile vertex lies below the symmetry axis.")
    end_x = state.get(state.extraction.vertices[-1].id, "x")
    if end_x is not None and end_x <= TOLERANCE:
        raise GeometryConflict(state.extraction.vertices[-1].id, "The right axis endpoint must lie to the right of the origin.")


def propagate_linear(state: CalculationState) -> None:
    while True:
        revision = state.revision
        apply_dimensions(state)
        apply_lines(state)
        check_upper_half(state)
        if state.revision == revision:
            return
