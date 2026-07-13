from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtCore import QSettings


DOT_SYMBOL_SETTING = "ui/dot_symbol"
DEFAULT_DOT_SYMBOL = "circle"
DOT_SYMBOL_OPTIONS: tuple[tuple[str, str], ...] = (
    ("circle", "Filled Circle"),
    ("hollow_circle", "Hollow Circle"),
    ("x", "X Mark"),
    ("plus", "Plus"),
    ("square", "Square"),
    ("diamond", "Diamond"),
    ("triangle", "Triangle"),
)


def normalize_dot_symbol(value: object) -> str:
    text = str(value or DEFAULT_DOT_SYMBOL).strip().lower()
    valid = {key for key, _label in DOT_SYMBOL_OPTIONS}
    return text if text in valid else DEFAULT_DOT_SYMBOL


def preferred_dot_symbol(settings: QSettings | None = None) -> str:
    source = settings or QSettings("OpenAI", "DrillWriter")
    return normalize_dot_symbol(source.value(DOT_SYMBOL_SETTING, DEFAULT_DOT_SYMBOL))


def dot_symbol_label(symbol: object) -> str:
    normalized = normalize_dot_symbol(symbol)
    return dict(DOT_SYMBOL_OPTIONS).get(normalized, "Filled Circle")


def draw_dot_symbol(
    painter: QPainter,
    center: QPointF,
    radius: float,
    color: QColor | str,
    symbol: object,
    *,
    rotation_degrees: float = 0.0,
    outline_color: QColor | str = "#1d2128",
    outline_width: float = 1.0,
    selected: bool = False,
) -> None:
    normalized = normalize_dot_symbol(symbol)
    fill = QColor(color)
    outline = QColor(outline_color)
    radius = max(0.5, float(radius))
    outline_width = max(0.35, float(outline_width))
    rect = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if normalized == "circle":
        painter.setPen(QPen(outline, outline_width))
        painter.setBrush(fill)
        painter.drawEllipse(rect)
    elif normalized == "hollow_circle":
        painter.setPen(QPen(fill, max(outline_width * 1.65, radius * 0.28)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect.adjusted(radius * 0.16, radius * 0.16, -radius * 0.16, -radius * 0.16))
    elif normalized in {"x", "plus"}:
        inset = radius * 0.3
        line_width = max(outline_width * 2.2, radius * 0.42)
        shadow_width = line_width + max(0.6, outline_width * 1.2)
        if normalized == "x":
            lines = (
                (QPointF(rect.left() + inset, rect.top() + inset), QPointF(rect.right() - inset, rect.bottom() - inset)),
                (QPointF(rect.left() + inset, rect.bottom() - inset), QPointF(rect.right() - inset, rect.top() + inset)),
            )
        else:
            lines = (
                (QPointF(center.x(), rect.top() + inset), QPointF(center.x(), rect.bottom() - inset)),
                (QPointF(rect.left() + inset, center.y()), QPointF(rect.right() - inset, center.y())),
            )
        painter.setPen(QPen(outline, shadow_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for start, end in lines:
            painter.drawLine(start, end)
        painter.setPen(QPen(fill, line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for start, end in lines:
            painter.drawLine(start, end)
    elif normalized == "square":
        painter.setPen(QPen(outline, outline_width))
        painter.setBrush(fill)
        painter.drawRect(rect.adjusted(radius * 0.12, radius * 0.12, -radius * 0.12, -radius * 0.12))
    elif normalized == "diamond":
        path = QPainterPath()
        path.moveTo(center.x(), rect.top())
        path.lineTo(rect.right(), center.y())
        path.lineTo(center.x(), rect.bottom())
        path.lineTo(rect.left(), center.y())
        path.closeSubpath()
        painter.setPen(QPen(outline, outline_width))
        painter.setBrush(fill)
        painter.drawPath(path)
    elif normalized == "triangle":
        painter.translate(center)
        painter.rotate(float(rotation_degrees))
        painter.translate(-center)
        path = QPainterPath()
        path.moveTo(center.x(), rect.bottom())
        path.lineTo(rect.right(), rect.top())
        path.lineTo(rect.left(), rect.top())
        path.closeSubpath()
        painter.setPen(QPen(outline, outline_width))
        painter.setBrush(fill)
        painter.drawPath(path)

    if selected:
        painter.setPen(QPen(QColor("#2f6fed"), max(0.7, outline_width * 1.5), Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect.adjusted(-radius * 0.35, -radius * 0.35, radius * 0.35, radius * 0.35))

    painter.restore()


def generated_prop_pixmap(name: str, layer: str, width: int = 240, height: int = 120) -> QPixmap:
    layer_text = str(layer or "").lower()
    name_text = str(name or "Prop")
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    try:
        rect = QRectF(6, 6, width - 12, height - 12)
        if "front ensemble" in layer_text or name_text.upper().startswith("FE"):
            painter.setPen(QPen(QColor("#1d232b"), 3))
            painter.setBrush(QColor("#414a54"))
            painter.drawRoundedRect(rect, 12, 12)
            key_rect = rect.adjusted(12, 18, -12, -44)
            painter.setPen(QPen(QColor("#11151a"), 1.3))
            painter.setBrush(QColor("#f4f0df"))
            painter.drawRoundedRect(key_rect, 5, 5)
            key_count = 14
            for index in range(1, key_count):
                x = key_rect.left() + key_rect.width() * index / key_count
                painter.drawLine(int(x), int(key_rect.top()), int(x), int(key_rect.bottom()))
            painter.setBrush(QColor("#11151a"))
            black_key_width = key_rect.width() / key_count * 0.52
            black_key_height = key_rect.height() * 0.58
            for index in range(key_count):
                if index % 7 in (0, 1, 3, 4, 5):
                    x = key_rect.left() + key_rect.width() * (index + 0.68) / key_count
                    painter.drawRoundedRect(QRectF(x, key_rect.top(), black_key_width, black_key_height), 2, 2)
            painter.setPen(QColor("#f7d154"))
            painter.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
            painter.drawText(rect.adjusted(0, rect.height() - 36, 0, -4), Qt.AlignmentFlag.AlignCenter, name_text)
        elif "drum major" in layer_text or name_text.upper().startswith("DM"):
            painter.setPen(QPen(QColor("#1d232b"), 4))
            painter.setBrush(QColor("#d9dee6"))
            platform = rect.adjusted(30, 20, -30, -42)
            painter.drawRoundedRect(platform, 8, 8)
            painter.setPen(QPen(QColor("#5e6874"), 5))
            painter.drawLine(int(platform.left() + 18), int(platform.bottom()), int(rect.left() + 38), int(rect.bottom() - 6))
            painter.drawLine(int(platform.right() - 18), int(platform.bottom()), int(rect.right() - 38), int(rect.bottom() - 6))
            painter.drawLine(int(platform.left() + 20), int(platform.bottom()), int(platform.right() - 20), int(platform.bottom()))
            painter.setPen(QPen(QColor("#1d232b"), 2))
            painter.setBrush(QColor("#f7d154"))
            painter.drawRoundedRect(platform.adjusted(18, 12, -18, -12), 5, 5)
            painter.setPen(QColor("#1d232b"))
            painter.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
            painter.drawText(rect.adjusted(0, rect.height() - 36, 0, -4), Qt.AlignmentFlag.AlignCenter, "DM")
        else:
            painter.setPen(QPen(QColor("#7b2530"), 3))
            painter.setBrush(QColor(255, 58, 58, 210))
            painter.drawRoundedRect(rect, 10, 10)
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, name_text[:16])
    finally:
        painter.end()
    return pixmap
