"""Export verified geometry as native DXF LINE and ARC entities."""

import math

from app.models.geometry import GeometryResult, GeometryStatus


class DxfExportError(ValueError):
    """The calculated geometry cannot be represented as a valid DXF contour."""


class DxfExportService:
    def export(self, geometry: GeometryResult) -> str:
        if (
            geometry.status != GeometryStatus.SUCCESS
            or not geometry.is_closed
            or not geometry.edges
        ):
            raise DxfExportError(
                "Only a successfully calculated closed contour can be exported as DXF."
            )

        values: list[str | int] = []

        def add(*items: str | int) -> None:
            values.extend(items)

        points = {point.id: point for point in geometry.vertices}
        add(
            0, "SECTION", 2, "HEADER",
            9, "$ACADVER", 1, "AC1015",
            9, "$INSUNITS", 70, 4,
            9, "$MEASUREMENT", 70, 1,
            0, "ENDSEC",
            0, "SECTION", 2, "ENTITIES",
        )

        handle = 256
        for edge in geometry.edges:
            start = points.get(edge.from_)
            end = points.get(edge.to)
            if start is None or end is None:
                raise DxfExportError("The contour references a missing vertex.")

            add(
                0, edge.type.upper(),
                5, format(handle, "X"),
                100, "AcDbEntity",
                8, "0",
            )
            handle += 1

            if edge.type == "line":
                add(
                    100, "AcDbLine",
                    10, self._number(start.x), 20, self._number(start.y), 30, 0,
                    11, self._number(end.x), 21, self._number(end.y), 31, 0,
                )
                continue

            if not 0 < edge.sweep_angle_degrees < 360:
                raise DxfExportError("The contour contains an invalid arc.")
            from_angle = math.degrees(
                math.atan2(start.y - edge.center.y, start.x - edge.center.x)
            )
            # DXF ARC entities are always counterclockwise. Reverse clockwise
            # traversal while preserving the complete sweep, including major arcs.
            if edge.clockwise:
                start_angle = from_angle - edge.sweep_angle_degrees
                end_angle = from_angle
            else:
                start_angle = from_angle
                end_angle = from_angle + edge.sweep_angle_degrees
            add(
                100, "AcDbCircle",
                10, self._number(edge.center.x),
                20, self._number(edge.center.y),
                30, 0,
                40, self._number(edge.radius),
                100, "AcDbArc",
                50, self._number(self._angle(start_angle)),
                51, self._number(self._angle(end_angle)),
            )

        add(0, "ENDSEC", 0, "EOF")
        return "\r\n".join(str(value) for value in values) + "\r\n"

    @staticmethod
    def _angle(value: float) -> float:
        return value % 360

    @staticmethod
    def _number(value: float) -> str:
        if not math.isfinite(value):
            raise DxfExportError("The contour contains an invalid numeric value.")
        if value == 0:
            return "0"
        return format(value, ".15g")
