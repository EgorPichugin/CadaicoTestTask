"""Export verified geometry as native DXF LINE and ARC entities."""

import math
from io import StringIO

import ezdxf
from ezdxf import units, zoom

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

        document = ezdxf.new("R2000", units=units.MM)
        modelspace = document.modelspace()
        points = {point.id: point for point in geometry.vertices}
        for edge in geometry.edges:
            start = points.get(edge.from_)
            end = points.get(edge.to)
            if start is None or end is None:
                raise DxfExportError("The contour references a missing vertex.")

            if edge.type == "line":
                modelspace.add_line((start.x, start.y), (end.x, end.y))
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
            modelspace.add_arc(
                center=(edge.center.x, edge.center.y),
                radius=edge.radius,
                start_angle=start_angle % 360,
                end_angle=end_angle % 360,
            )

        # Include CAD tables, layouts and ownership links, not just entity tags.
        zoom.extents(modelspace)
        stream = StringIO()
        document.write(stream)
        return stream.getvalue().replace("\n", "\r\n")
