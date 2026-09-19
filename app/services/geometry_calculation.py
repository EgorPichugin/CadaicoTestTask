from collections.abc import Sequence

from app.models.extraction import ExtractionResult
from app.models.geometry import GeometryEdge, GeometryIssue, GeometryResult, GeometryStatus, GeometryVertex
from app.services.geometry.arcs import ArcCandidate, apply_arcs
from app.services.geometry.contour import build_contour, validate_contour
from app.services.geometry.linear import check_difference_cycles, propagate_linear
from app.services.geometry.remaining import solve_remaining
from app.services.geometry.state import CalculationState, GeometryConflict, TOLERANCE, validate_input


MAX_SEARCH_STATES = 256


def propagate(state: CalculationState) -> dict[str, list[ArcCandidate]]:
    """Repeat the same rules until a whole pass adds no new values."""
    while True:
        revision = state.revision
        propagate_linear(state)
        choices = apply_arcs(state)
        if state.revision == revision:
            return choices


def missing_input(extraction: ExtractionResult) -> list[GeometryIssue]:
    issues = [GeometryIssue(target=item.target, reason=item.reason) for item in extraction.unresolved]
    for dimension in extraction.dimensions:
        if dimension.value is None:
            issues.append(GeometryIssue(target=dimension.id, reason="The stated dimension value is unknown."))
    for edge in extraction.edges:
        fields = ("direction",) if edge.type == "line" else ("radius", "clockwise", "shape")
        for field in fields:
            if getattr(edge, field) is None:
                issues.append(GeometryIssue(target=edge.id, reason=f"The extracted {field} is unknown."))
        if edge.type == "arc" and edge.center_constraint == "unknown":
            issues.append(GeometryIssue(target=edge.id, reason="The circle center constraint is unknown."))
    return issues


class GeometryCalculationService:
    """Calculate a verified closed contour without changing the extraction."""

    def calculate(self, extraction: ExtractionResult) -> GeometryResult:
        def result(
            status: GeometryStatus,
            issues: Sequence[GeometryIssue] = (),
            vertices: Sequence[GeometryVertex] = (),
            edges: Sequence[GeometryEdge] = (),
        ) -> GeometryResult:
            return GeometryResult(
                status=status, units=extraction.units, profile=extraction.profile.model_copy(deep=True),
                is_closed=status == GeometryStatus.SUCCESS,
                vertices=list(vertices), edges=list(edges), issues=list(issues),
            )

        try:
            validate_input(extraction)
            check_difference_cycles(extraction)
            initial = CalculationState.from_extraction(extraction)
            propagate(initial)
        except GeometryConflict as error:
            return result(GeometryStatus.INVALID, [error.issue])
        except (OverflowError, ZeroDivisionError):
            return result(GeometryStatus.UNRESOLVED, [GeometryIssue(
                reason="The supplied dimensions exceed the supported numerical range."
            )])

        # Uncertainty can concern a wrong attachment, not just a missing number.
        input_issues = missing_input(extraction)

        pending = [initial]
        solutions = []
        conflicts, unresolved = [], []
        visited = 0
        while pending and len(solutions) < 2:
            if visited >= MAX_SEARCH_STATES:
                unresolved.append(GeometryIssue(reason="The limit for checking geometric alternatives was reached."))
                break
            state = pending.pop()
            visited += 1
            try:
                choices = propagate(state)
                coordinates = state.coordinates()
                arc_count = sum(edge.type == "arc" for edge in extraction.edges)
                if len(coordinates) == len(extraction.vertices) and len(state.arcs) == arc_count:
                    vertices, edges = build_contour(extraction, coordinates, state.arcs)
                    issues = validate_contour(vertices, edges, TOLERANCE)
                    if issues:
                        conflicts.extend(issues)
                    else:
                        candidate = result(GeometryStatus.SUCCESS, vertices=vertices, edges=edges)
                        if not any(same_geometry(candidate, previous) for previous in solutions):
                            solutions.append(candidate)
                elif choices:
                    # Branch on analytic alternatives, never on guessed coordinates.
                    for candidate in min(choices.values(), key=len):
                        branch = state.copy()
                        candidate.apply(branch)
                        pending.append(branch)
                else:
                    joint = solve_remaining(state)
                    pending.extend(joint.states)
                    if joint.issue:
                        unresolved.append(joint.issue)
            except GeometryConflict as error:
                conflicts.append(error.issue)
            except (OverflowError, ZeroDivisionError):
                unresolved.append(GeometryIssue(reason="The supplied dimensions exceed the supported numerical range."))

        if len(solutions) > 1:
            return result(GeometryStatus.AMBIGUOUS, [GeometryIssue(
                reason="More than one closed contour satisfies the supplied constraints."
            ), *input_issues])
        if unresolved:
            return result(GeometryStatus.UNRESOLVED, [*input_issues, *unresolved][:10])
        if solutions:
            if input_issues:
                return result(GeometryStatus.UNRESOLVED, input_issues)
            return solutions[0]
        return result(GeometryStatus.INVALID, conflicts[:10] or [GeometryIssue(
            reason="No valid closed contour satisfies the supplied constraints."
        )])


def same_geometry(first: GeometryResult, second: GeometryResult) -> bool:
    for left, right in zip(first.vertices, second.vertices):
        if abs(left.x - right.x) > TOLERANCE or abs(left.y - right.y) > TOLERANCE:
            return False
    for left, right in zip(first.edges, second.edges):
        if left.type == "arc" and (
            abs(left.center.x - right.center.x) > TOLERANCE
            or abs(left.center.y - right.center.y) > TOLERANCE
            or left.clockwise != right.clockwise
            or left.arc_size != right.arc_size
        ):
            return False
    return True
