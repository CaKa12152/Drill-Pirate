from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from drill_writer.core.models import SurfaceDefinition
from drill_writer.core.specialized_design import normalized_surface


def field_to_rect(rect: QRectF, surface: SurfaceDefinition, x: float, y: float) -> QPointF:
    surface = normalized_surface(surface)
    return QPointF(
        rect.left() + (x + surface.half_width) / surface.width_yards * rect.width(),
        rect.top() + (surface.half_height - y) / surface.height_yards * rect.height(),
    )


def rect_to_field(rect: QRectF, surface: SurfaceDefinition, point: QPointF) -> tuple[float, float]:
    surface = normalized_surface(surface)
    x = ((point.x() - rect.left()) / max(1.0, rect.width())) * surface.width_yards - surface.half_width
    y = surface.half_height - ((point.y() - rect.top()) / max(1.0, rect.height())) * surface.height_yards
    return x, y


def size_to_rect(rect: QRectF, surface: SurfaceDefinition, width: float, height: float) -> tuple[float, float]:
    surface = normalized_surface(surface)
    return width / surface.width_yards * rect.width(), height / surface.height_yards * rect.height()


def fitted_surface_rect(outer: QRectF, surface: SurfaceDefinition, margin: float = 8.0) -> QRectF:
    surface = normalized_surface(surface)
    available = outer.adjusted(margin, margin, -margin, -margin)
    ratio = surface.width_yards / surface.height_yards
    width = available.width()
    height = width / ratio
    if height > available.height():
        height = available.height()
        width = height * ratio
    return QRectF(
        available.center().x() - width / 2,
        available.center().y() - height / 2,
        width,
        height,
    )


def draw_surface_preview(
    painter: QPainter,
    rect: QRectF,
    surface: SurfaceDefinition,
    palette: dict[str, str],
) -> None:
    surface = normalized_surface(surface)
    fill = surface.background_color or palette.get("fill", palette.get("field_fill", "#f9fbf7"))
    line = surface.line_color or palette.get("line", palette.get("yard", "#66717a"))
    micro = surface.line_color or palette.get("micro", palette.get("minor", line))
    hash_color = surface.line_color or palette.get("hash", line)
    endzone = surface.background_color or palette.get("endzone", palette.get("endzone_fill", fill))
    painter.setPen(QPen(QColor(line), 0.8))
    painter.setBrush(QColor(fill))
    painter.drawRoundedRect(rect, 3, 3)
    if surface.surface_type == "football":
        playing_half = max(5.0, surface.half_width - surface.endzone_depth_yards)
        if surface.show_end_zones and surface.endzone_depth_yards > 0:
            left = field_to_rect(rect, surface, -playing_half, 0).x()
            right = field_to_rect(rect, surface, playing_half, 0).x()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(endzone))
            painter.drawRect(QRectF(rect.left(), rect.top(), left - rect.left(), rect.height()))
            painter.drawRect(QRectF(right, rect.top(), rect.right() - right, rect.height()))
        painter.setPen(QPen(QColor(micro), 0.4))
        first_five = int(-surface.half_width // 5) * 5
        last_five = int(surface.half_width // 5) * 5
        for yard in range(first_five, last_five + 1, 5):
            if -surface.half_width <= yard <= surface.half_width:
                x = field_to_rect(rect, surface, yard, 0).x()
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        if surface.hash_style != "none":
            painter.setPen(QPen(QColor(hash_color), 0.55, Qt.PenStyle.DotLine))
            for hash_y in (surface.front_hash_yards, surface.back_hash_yards):
                y = field_to_rect(rect, surface, 0, hash_y).y()
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
    else:
        painter.setPen(QPen(QColor(micro), 0.35))
        spacing = max(0.25, surface.grid_spacing_yards)
        vertical_count = min(200, int(surface.width_yards / spacing))
        horizontal_count = min(200, int(surface.height_yards / spacing))
        for index in range(1, vertical_count):
            x = rect.left() + index / vertical_count * rect.width()
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for index in range(1, horizontal_count):
            y = rect.top() + index / horizontal_count * rect.height()
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        if surface.surface_type == "parade" and len(surface.route_points) >= 2:
            path = QPainterPath(field_to_rect(rect, surface, *surface.route_points[0]))
            for point in surface.route_points[1:]:
                path.lineTo(field_to_rect(rect, surface, *point))
            route_width = surface.route_width_yards / surface.height_yards * rect.height()
            band_pen = QPen(QColor(palette.get("route", micro)), max(2.0, route_width))
            band_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            band_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(band_pen)
            painter.drawPath(path)
            painter.setPen(QPen(QColor(line), 0.8, Qt.PenStyle.DashLine))
            painter.drawPath(path)
