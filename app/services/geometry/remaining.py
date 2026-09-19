"""Solve coupled equations after the inexpensive rules stop making progress."""

from dataclasses import dataclass, field
from math import isfinite

import sympy as sp
from sympy.polys.polyerrors import PolynomialError, UnsolvableFactorError

from app.models.extraction import Arc
from app.models.geometry import GeometryIssue
from app.services.geometry.state import CalculationState, Coordinate, TOLERANCE


# Symbolic elimination can grow rapidly. Exceeding a limit is Unresolved, never Invalid.
MAX_JOINT_VARIABLES = 4
MAX_JOINT_EQUATIONS = 16

CoordinateExpressions = dict[Coordinate, sp.Expr]


@dataclass
class JointResult:
    states: list[CalculationState] = field(default_factory=list)
    issue: GeometryIssue | None = None


@dataclass
class EquationSystem:
    coordinates: CoordinateExpressions
    linear: list[sp.Expr] = field(default_factory=list)
    circular: list[sp.Expr] = field(default_factory=list)
    largest_radius: float = 0


class UnresolvedSystem(ValueError):
    """The supported symbolic method cannot finish this system reliably."""


def solve_remaining(state: CalculationState) -> JointResult:
    """Return finite endpoint candidates for the regular geometry rules to check.

    Symbolic failure is not proof that no solution exists within numerical
    tolerance. Direction, arc category and contour validity are checked later.
    """
    try:
        system = build_equations(state)
        coordinates, substitutions = eliminate_linear(system)
        trial = apply_constant_coordinates(state, coordinates)
        if trial.revision > state.revision:
            return JointResult(states=[trial])

        equations = reduce_circles(system, substitutions)
        variables, roots = solve_polynomials(coordinates, equations)
        states = endpoint_candidates(state, coordinates, variables, roots)
        if not states:
            raise UnresolvedSystem(
                "The joint solver did not establish finite real endpoint coordinates."
            )
        return JointResult(states=states)
    except UnresolvedSystem as error:
        return JointResult(issue=unresolved_issue(state, str(error)))


def unresolved_issue(state: CalculationState, reason: str) -> GeometryIssue:
    unknown = [(vertex.id, axis) for vertex in state.extraction.vertices
               for axis in ("x", "y") if state.get(vertex.id, axis) is None]
    if not unknown:
        return GeometryIssue(reason=reason)
    names = ", ".join(f"{vertex}.{axis}" for vertex, axis in unknown[:8])
    if len(unknown) > 8:
        names += ", ..."
    return GeometryIssue(
        target=unknown[0][0], reason=f"{reason} Unknown coordinates: {names}."
    )


def build_equations(state: CalculationState) -> EquationSystem:
    coordinates = {}
    for vertex in state.extraction.vertices:
        for axis in ("x", "y"):
            value = state.get(vertex.id, axis)
            coordinates[(vertex.id, axis)] = (
                sp.Symbol(f"{vertex.id}_{axis}", real=True) if value is None
                else sp.Rational(str(value))
            )
    system = EquationSystem(coordinates)
    add_dimension_equations(system, state)
    for edge in state.extraction.edges:
        if edge.type == "line":
            if edge.direction is not None:
                axis = "y" if edge.direction[1] == "X" else "x"
                system.linear.append(
                    coordinates[(edge.to, axis)] - coordinates[(edge.from_, axis)]
                )
        elif edge.id not in state.arcs and edge.radius is not None:
            add_circle_equations(system, edge)
    return system


def add_dimension_equations(system: EquationSystem, state: CalculationState) -> None:
    for dimension in state.extraction.dimensions:
        if dimension.value is None:
            continue
        value = sp.Rational(str(dimension.value))
        if dimension.type == "diameter":
            equation = system.coordinates[(dimension.vertex, "y")] - value / 2
        else:
            axis = dimension.axis.lower()
            equation = (system.coordinates[(dimension.to, axis)]
                        - system.coordinates[(dimension.from_, axis)] - value)
        system.linear.append(equation)


def add_circle_equations(system: EquationSystem, edge: Arc) -> None:
    start = tuple(system.coordinates[(edge.from_, axis)] for axis in ("x", "y"))
    end = tuple(system.coordinates[(edge.to, axis)] for axis in ("x", "y"))
    cx = sp.Symbol(f"{edge.id}_cx", real=True)
    cy = (sp.Integer(0) if edge.center_constraint == "on_symmetry_axis"
          else sp.Symbol(f"{edge.id}_cy", real=True))
    radius = sp.Rational(str(edge.radius))
    system.largest_radius = max(system.largest_radius, edge.radius)
    for x, y in (start, end):
        system.circular.append((x - cx) ** 2 + (y - cy) ** 2 - radius ** 2)
    if edge.arc_size == "semicircle":
        system.linear.extend([2 * cx - start[0] - end[0], 2 * cy - start[1] - end[1]])


def free_symbols(expressions) -> list[sp.Symbol]:
    return sorted(set().union(*(expression.free_symbols for expression in expressions)), key=str)


def eliminate_linear(system: EquationSystem):
    # Already-known coordinates may contain harmless floating-point rounding.
    linear = [equation for equation in system.linear
              if equation.free_symbols or abs(float(equation)) > TOLERANCE]
    symbols = free_symbols([*system.coordinates.values(), *linear, *system.circular])
    if not symbols:
        raise UnresolvedSystem(
            "No additional coordinates can be calculated from the remaining conditions."
        )
    solution = sp.linsolve(linear, symbols) if linear else sp.FiniteSet(tuple(symbols))
    if solution is sp.EmptySet:
        raise UnresolvedSystem("The remaining linear conditions could not be solved consistently.")
    substitutions = dict(zip(symbols, next(iter(solution))))
    coordinates = {
        key: expression.subs(substitutions, simultaneous=True)
        for key, expression in system.coordinates.items()
    }
    return coordinates, substitutions


def apply_constant_coordinates(state: CalculationState,
                               coordinates: CoordinateExpressions) -> CalculationState:
    trial = state.copy()
    for (vertex, axis), expression in coordinates.items():
        if not expression.free_symbols:
            trial.set(vertex, axis, float(expression), vertex)
    return trial


def reduce_circles(system: EquationSystem, substitutions) -> list[sp.Expr]:
    residual_tolerance = TOLERANCE * max(1.0, 2 * system.largest_radius)
    equations = []
    for equation in system.circular:
        reduced = sp.expand(equation.subs(substitutions, simultaneous=True))
        if reduced.free_symbols:
            equations.append(reduced)
        elif abs(float(reduced)) > residual_tolerance:
            raise UnresolvedSystem("The remaining circle equations could not be solved consistently.")
    return equations


def solve_polynomials(coordinates: CoordinateExpressions, equations: list[sp.Expr]):
    variables = free_symbols([*coordinates.values(), *equations])
    constrained = set(free_symbols(equations))
    if not equations or any(variable not in constrained for variable in variables):
        raise UnresolvedSystem(
            "Some coordinates remain free; additional geometric constraints are needed."
        )
    if len(variables) > MAX_JOINT_VARIABLES or len(equations) > MAX_JOINT_EQUATIONS:
        raise UnresolvedSystem(
            "The remaining coupled system exceeds the supported symbolic calculation limit."
        )
    try:
        roots = sp.solve_poly_system(equations, *variables, strict=True)
    except (NotImplementedError, PolynomialError, UnsolvableFactorError) as error:
        raise UnresolvedSystem(
            "The remaining coupled equations have free parameters or cannot be solved by the supported method."
        ) from error
    if not roots:
        raise UnresolvedSystem(
            "No exact joint solution was found; this does not prove impossibility within numerical tolerance."
        )
    return variables, roots


def real_coordinates(coordinates: CoordinateExpressions, values) -> dict[Coordinate, float] | None:
    result = {}
    for key, expression in coordinates.items():
        numeric = complex(expression.subs(values).evalf())
        if abs(numeric.imag) > 1e-12 or not isfinite(numeric.real):
            return None
        result[key] = numeric.real
    return result


def endpoint_candidates(state: CalculationState, coordinates: CoordinateExpressions,
                        variables, roots) -> list[CalculationState]:
    states = []
    for root in roots:
        values = real_coordinates(coordinates, dict(zip(variables, root)))
        if values is None:
            continue
        candidate = state.copy()
        for (vertex, axis), value in values.items():
            candidate.set(vertex, axis, value, vertex)
        if candidate.revision == state.revision:
            continue
        duplicate = any(
            all(abs(previous.values[key] - value) <= TOLERANCE
                for key, value in candidate.values.items()) for previous in states
        )
        if not duplicate:
            states.append(candidate)
    return states
