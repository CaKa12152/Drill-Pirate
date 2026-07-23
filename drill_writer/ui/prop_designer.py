from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass
from math import atan2, degrees
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


ITEM_KIND_ROLE = 1001
ITEM_NAME_ROLE = 1002
ITEM_ID_ROLE = 1003
ITEM_LOCKED_ROLE = 1004
DESIGN_DOCUMENT_VERSION = 2


@dataclass(slots=True)
class CreatedPropDesign:
    name: str
    image_file: str
    width: float
    height: float
    layer: str
    x: float = 0.0
    y: float = -31.5
    design_file: str = ""


def color_text(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexArgb)


class PropDesignerCanvas(QGraphicsView):
    designChanged = Signal()
    selectionChangedDetailed = Signal()
    statusChanged = Signal(str)
    textRequested = Signal()
    imageRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.physical_width_yards = 8.0
        self.physical_height_yards = 4.0
        self.canvas_rect = QRectF(0, 0, 900, 450)
        self.scene.setSceneRect(self.canvas_rect.adjusted(-70, -70, 70, 70))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#0e1117"))
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tool = "select"
        self.fill_color = QColor("#f7c94a")
        self.stroke_color = QColor("#16191f")
        self.stroke_width = 4.0
        self.no_fill = False
        self.grid_visible = True
        self.snap_enabled = True
        self.snap_yards = 0.25
        self.start_point: QPointF | None = None
        self.preview_item: QGraphicsItem | None = None
        self.freehand_path: QPainterPath | None = None
        self._interaction_before: list[dict] | None = None
        self._active_handle = ""
        self._handle_item: QGraphicsItem | None = None
        self._handle_initial_rect = QRectF()
        self._handle_initial_rotation = 0.0
        self._handle_start_angle = 0.0
        self._panning = False
        self._pan_start = None
        self._restoring = False
        self._history: list[list[dict]] = [[]]
        self._history_index = 0
        self.scene.selectionChanged.connect(self._scene_selection_changed)

    def _scene_selection_changed(self) -> None:
        self.viewport().update()
        self.selectionChangedDetailed.emit()
        self.emit_status()

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag
            if tool == "select"
            else QGraphicsView.DragMode.NoDrag
        )
        self.setCursor(
            Qt.CursorShape.ArrowCursor
            if tool == "select"
            else Qt.CursorShape.CrossCursor
        )
        self.emit_status()

    def set_style(self, fill: QColor, stroke: QColor, stroke_width: float, no_fill: bool) -> None:
        self.fill_color = QColor(fill)
        self.stroke_color = QColor(stroke)
        self.stroke_width = max(0.25, float(stroke_width))
        self.no_fill = bool(no_fill)

    def set_grid_options(self, visible: bool, snap: bool, interval_yards: float) -> None:
        self.grid_visible = bool(visible)
        self.snap_enabled = bool(snap)
        self.snap_yards = max(0.05, float(interval_yards))
        self.viewport().update()

    def set_physical_size(self, width_yards: float, height_yards: float, *, rescale_items: bool = True) -> None:
        width_yards = max(0.25, float(width_yards))
        height_yards = max(0.25, float(height_yards))
        old_rect = QRectF(self.canvas_rect)
        old_width = self.physical_width_yards
        old_height = self.physical_height_yards
        ratio = width_yards / height_yards
        if ratio >= 1:
            artboard_width = 900.0
            artboard_height = max(260.0, min(680.0, artboard_width / ratio))
        else:
            artboard_height = 680.0
            artboard_width = max(300.0, min(900.0, artboard_height * ratio))
        new_rect = QRectF(0, 0, artboard_width, artboard_height)
        if rescale_items and old_rect.width() > 0 and old_rect.height() > 0:
            states = self.serialize_items()
            scale_x = new_rect.width() / old_rect.width()
            scale_y = new_rect.height() / old_rect.height()
            for item in self.design_items():
                rect = self.item_scene_rect(item)
                mapped = QRectF(
                    (rect.x() - old_rect.x()) * scale_x + new_rect.x(),
                    (rect.y() - old_rect.y()) * scale_y + new_rect.y(),
                    rect.width() * scale_x,
                    rect.height() * scale_y,
                )
                self.set_item_scene_rect(item, mapped)
            if states != self.serialize_items():
                self.commit_history()
        self.physical_width_yards = width_yards
        self.physical_height_yards = height_yards
        self.canvas_rect = new_rect
        self.scene.setSceneRect(self.canvas_rect.adjusted(-70, -70, 70, 70))
        if abs(old_width - width_yards) > 0.0001 or abs(old_height - height_yards) > 0.0001:
            self.designChanged.emit()
        self.viewport().update()
        self.emit_status()

    def fit_artboard(self) -> None:
        self.fitInView(self.canvas_rect.adjusted(-42, -42, 42, 42), Qt.AspectRatioMode.KeepAspectRatio)
        self.emit_status()

    def zoom_by(self, factor: float) -> None:
        current = abs(self.transform().m11())
        target = current * factor
        if 0.12 <= target <= 8.0:
            self.scale(factor, factor)
            self.emit_status()

    def zoom_percent(self) -> int:
        return round(abs(self.transform().m11()) * 100)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # type: ignore[override]
        painter.fillRect(rect, QColor("#0e1117"))
        checker = 20
        painter.save()
        painter.setClipRect(self.canvas_rect)
        painter.fillRect(self.canvas_rect, QColor("#f7f8fa"))
        painter.setPen(Qt.PenStyle.NoPen)
        first_column = int((rect.left() - self.canvas_rect.left()) // checker) - 1
        last_column = int((rect.right() - self.canvas_rect.left()) // checker) + 1
        first_row = int((rect.top() - self.canvas_rect.top()) // checker) - 1
        last_row = int((rect.bottom() - self.canvas_rect.top()) // checker) + 1
        painter.setBrush(QColor("#e8ebef"))
        for row in range(first_row, last_row + 1):
            for column in range(first_column, last_column + 1):
                if (row + column) % 2:
                    painter.drawRect(
                        QRectF(
                            self.canvas_rect.left() + column * checker,
                            self.canvas_rect.top() + row * checker,
                            checker,
                            checker,
                        )
                    )
        if self.grid_visible:
            self.draw_design_grid(painter)
        painter.restore()
        painter.setPen(QPen(QColor("#788394"), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.canvas_rect)
        self.draw_rulers(painter)

    def draw_design_grid(self, painter: QPainter) -> None:
        minor_pen = QPen(QColor(80, 92, 110, 55), 0.7)
        major_pen = QPen(QColor(60, 72, 90, 105), 1.0)
        x_step = self.canvas_rect.width() / self.physical_width_yards * self.snap_yards
        y_step = self.canvas_rect.height() / self.physical_height_yards * self.snap_yards
        max_lines = 500
        if x_step >= 2:
            count = min(max_lines, int(self.canvas_rect.width() / x_step) + 1)
            for index in range(count):
                yard_value = index * self.snap_yards
                painter.setPen(major_pen if abs(yard_value - round(yard_value)) < 0.001 else minor_pen)
                x_position = self.canvas_rect.left() + index * x_step
                painter.drawLine(QPointF(x_position, self.canvas_rect.top()), QPointF(x_position, self.canvas_rect.bottom()))
        if y_step >= 2:
            count = min(max_lines, int(self.canvas_rect.height() / y_step) + 1)
            for index in range(count):
                yard_value = index * self.snap_yards
                painter.setPen(major_pen if abs(yard_value - round(yard_value)) < 0.001 else minor_pen)
                y_position = self.canvas_rect.top() + index * y_step
                painter.drawLine(QPointF(self.canvas_rect.left(), y_position), QPointF(self.canvas_rect.right(), y_position))

    def draw_rulers(self, painter: QPainter) -> None:
        painter.save()
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QPen(QColor("#c9d1df"), 1))
        top_y = self.canvas_rect.top() - 18
        left_x = self.canvas_rect.left() - 18
        for yard in range(int(self.physical_width_yards) + 1):
            x_position = self.canvas_rect.left() + yard / self.physical_width_yards * self.canvas_rect.width()
            painter.drawLine(QPointF(x_position, self.canvas_rect.top() - 8), QPointF(x_position, self.canvas_rect.top()))
            painter.drawText(QRectF(x_position - 20, top_y - 12, 40, 12), Qt.AlignmentFlag.AlignCenter, str(yard))
        for yard in range(int(self.physical_height_yards) + 1):
            y_position = self.canvas_rect.top() + yard / self.physical_height_yards * self.canvas_rect.height()
            painter.drawLine(QPointF(self.canvas_rect.left() - 8, y_position), QPointF(self.canvas_rect.left(), y_position))
            painter.drawText(QRectF(left_x - 26, y_position - 7, 24, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(yard))
        painter.restore()

    def drawForeground(self, painter: QPainter, _rect: QRectF) -> None:  # type: ignore[override]
        item = self.selected_item()
        if item is None:
            return
        painter.save()
        scale = max(0.01, abs(self.transform().m11()))
        pen = QPen(QColor("#3b82f6"), 1.4 / scale)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        bounds = item.sceneBoundingRect()
        painter.drawRect(bounds)
        handle_size = 9.0 / scale
        painter.setPen(QPen(QColor("#0b1220"), 1.0 / scale))
        painter.setBrush(QColor("#ffffff"))
        for key, handle in self.selection_handles(item).items():
            if key == "rotate":
                center = QPointF(bounds.center().x(), bounds.top())
                painter.drawLine(center, handle.center())
                painter.setBrush(QColor("#f7c94a"))
                painter.drawEllipse(handle)
                painter.setBrush(QColor("#ffffff"))
            else:
                painter.drawRect(handle)
        yard_rect = self.scene_rect_to_yards(bounds)
        label = f"{yard_rect.width():.2f} × {yard_rect.height():.2f} yd   {item.rotation():.1f}°"
        text_rect = QRectF(bounds.left(), bounds.bottom() + handle_size, max(150 / scale, bounds.width()), 22 / scale)
        painter.setPen(QColor("#dbeafe"))
        painter.setFont(QFont("Segoe UI", max(1, round(8 / scale))))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, label)
        painter.restore()

    def selection_handles(self, item: QGraphicsItem) -> dict[str, QRectF]:
        bounds = item.sceneBoundingRect()
        scale = max(0.01, abs(self.transform().m11()))
        size = 9.0 / scale
        half = size / 2
        points = {
            "nw": bounds.topLeft(),
            "n": QPointF(bounds.center().x(), bounds.top()),
            "ne": bounds.topRight(),
            "e": QPointF(bounds.right(), bounds.center().y()),
            "se": bounds.bottomRight(),
            "s": QPointF(bounds.center().x(), bounds.bottom()),
            "sw": bounds.bottomLeft(),
            "w": QPointF(bounds.left(), bounds.center().y()),
            "rotate": QPointF(bounds.center().x(), bounds.top() - 26.0 / scale),
        }
        return {key: QRectF(point.x() - half, point.y() - half, size, size) for key, point in points.items()}

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        scene_point = self.mapToScene(event.position().toPoint())
        if self.tool == "select" or event.button() != Qt.MouseButton.LeftButton:
            if event.button() == Qt.MouseButton.LeftButton and self.tool == "select":
                item = self.selected_item()
                if item is not None and not self.item_locked(item):
                    for key, handle in self.selection_handles(item).items():
                        if handle.contains(scene_point):
                            self._active_handle = key
                            self._handle_item = item
                            self._handle_initial_rect = item.sceneBoundingRect()
                            self._handle_initial_rotation = item.rotation()
                            self._handle_start_angle = degrees(
                                atan2(
                                    scene_point.y() - self._handle_initial_rect.center().y(),
                                    scene_point.x() - self._handle_initial_rect.center().x(),
                                )
                            )
                            self._interaction_before = self.serialize_items()
                            event.accept()
                            return
                self._interaction_before = self.serialize_items()
            super().mousePressEvent(event)
            return
        if not self.canvas_rect.contains(scene_point):
            return
        self.start_point = self.snap_point(scene_point)
        if self.tool == "pen":
            self.freehand_path = QPainterPath(self.start_point)
            item = QGraphicsPathItem(self.freehand_path)
            self.prepare_item(item, "path", "Freehand Path")
            self.apply_style_to_item(item)
            self.preview_item = item
        else:
            self.preview_item = self.create_item_for_tool(QRectF(self.start_point, self.start_point))
        if self.preview_item:
            self.scene.clearSelection()
            self.scene.addItem(self.preview_item)
            self.preview_item.setSelected(True)
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._panning and self._pan_start is not None:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        scene_point = self.snap_point(self.mapToScene(event.position().toPoint()))
        if self._active_handle and self._handle_item is not None:
            self.resize_or_rotate_selected(scene_point, event.modifiers())
            self.selectionChangedDetailed.emit()
            self.viewport().update()
            event.accept()
            return
        if self.start_point is None or self.preview_item is None:
            super().mouseMoveEvent(event)
            return
        if self.tool == "pen" and self.freehand_path is not None:
            self.freehand_path.lineTo(scene_point)
            if isinstance(self.preview_item, QGraphicsPathItem):
                self.preview_item.setPath(self.freehand_path)
        else:
            current = scene_point
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                delta_x = current.x() - self.start_point.x()
                delta_y = current.y() - self.start_point.y()
                if self.tool in {"rectangle", "ellipse"}:
                    extent = max(abs(delta_x), abs(delta_y))
                    current = QPointF(
                        self.start_point.x() + extent * (1 if delta_x >= 0 else -1),
                        self.start_point.y() + extent * (1 if delta_y >= 0 else -1),
                    )
                elif self.tool == "line":
                    if abs(delta_x) >= abs(delta_y):
                        current.setY(self.start_point.y())
                    else:
                        current.setX(self.start_point.x())
            self.set_item_scene_rect(self.preview_item, QRectF(self.start_point, current).normalized())
        self.viewport().update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self._pan_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor if self.tool == "select" else Qt.CursorShape.CrossCursor)
            event.accept()
            return
        if self._active_handle:
            self._active_handle = ""
            self._handle_item = None
            self.commit_history()
            event.accept()
            return
        if self.start_point is not None and self.preview_item is not None:
            if self.preview_item.sceneBoundingRect().width() + self.preview_item.sceneBoundingRect().height() < 8:
                self.scene.removeItem(self.preview_item)
            else:
                self.commit_history()
            self.start_point = None
            self.preview_item = None
            self.freehand_path = None
            self.selectionChangedDetailed.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.tool == "select" and event.button() == Qt.MouseButton.LeftButton:
            self.snap_selected_items()
            self.commit_history()

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undo()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.redo()
            return
        if event.matches(QKeySequence.StandardKey.Delete) or event.key() == Qt.Key.Key_Backspace:
            self.delete_selected()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_D:
            self.duplicate_selected()
            return
        tool_keys = {
            Qt.Key.Key_V: "select",
            Qt.Key.Key_R: "rectangle",
            Qt.Key.Key_E: "ellipse",
            Qt.Key.Key_L: "line",
            Qt.Key.Key_P: "pen",
        }
        if event.key() in tool_keys and not event.modifiers():
            self.set_tool(tool_keys[event.key()])
            return
        if event.key() == Qt.Key.Key_T and not event.modifiers():
            self.textRequested.emit()
            return
        if event.key() == Qt.Key.Key_I and not event.modifiers():
            self.imageRequested.emit()
            return
        if event.key() == Qt.Key.Key_0:
            self.fit_artboard()
            return
        if event.key() in {Qt.Key.Key_Plus, Qt.Key.Key_Equal}:
            self.zoom_by(1.2)
            return
        if event.key() == Qt.Key.Key_Minus:
            self.zoom_by(1 / 1.2)
            return
        if event.key() in {Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down}:
            amount = 1.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else self.snap_yards
            delta_x = -amount if event.key() == Qt.Key.Key_Left else amount if event.key() == Qt.Key.Key_Right else 0.0
            delta_y = -amount if event.key() == Qt.Key.Key_Up else amount if event.key() == Qt.Key.Key_Down else 0.0
            self.nudge_selected(delta_x, delta_y)
            return
        super().keyPressEvent(event)

    def create_item_for_tool(self, rect: QRectF) -> QGraphicsItem | None:
        if self.tool == "rectangle":
            item = QGraphicsRectItem(rect)
            name = "Rectangle"
        elif self.tool == "ellipse":
            item = QGraphicsEllipseItem(rect)
            name = "Ellipse"
        elif self.tool == "line":
            item = QGraphicsLineItem(rect.left(), rect.top(), rect.right(), rect.bottom())
            name = "Line"
        else:
            return None
        self.prepare_item(item, self.tool, name)
        self.apply_style_to_item(item)
        return item

    def prepare_item(self, item: QGraphicsItem, kind: str, name: str, item_id: str | None = None) -> None:
        item.setData(ITEM_KIND_ROLE, kind)
        item.setData(ITEM_NAME_ROLE, name)
        item.setData(ITEM_ID_ROLE, item_id or uuid.uuid4().hex)
        item.setData(ITEM_LOCKED_ROLE, False)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setZValue(self.next_z_value())

    def next_z_value(self) -> float:
        return max((item.zValue() for item in self.design_items()), default=0.0) + 1.0

    def apply_style_to_selected(self, *, commit: bool = True) -> None:
        for item in self.scene.selectedItems():
            self.apply_style_to_item(item)
            item.update()
        if commit:
            self.commit_history()

    def apply_style_to_item(self, item: QGraphicsItem) -> None:
        pen = QPen(self.stroke_color, self.stroke_width)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        brush = Qt.BrushStyle.NoBrush if self.no_fill else self.fill_color
        if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            item.setPen(pen)
            item.setBrush(brush)
        elif isinstance(item, (QGraphicsLineItem, QGraphicsPathItem)):
            item.setPen(pen)
        elif isinstance(item, QGraphicsTextItem):
            item.setDefaultTextColor(self.fill_color)

    def selected_item(self) -> QGraphicsItem | None:
        selected = self.scene.selectedItems()
        return selected[0] if len(selected) == 1 else None

    def design_items(self) -> list[QGraphicsItem]:
        return [item for item in self.scene.items() if item.data(ITEM_ID_ROLE)]

    def item_by_id(self, item_id: str) -> QGraphicsItem | None:
        return next((item for item in self.design_items() if str(item.data(ITEM_ID_ROLE)) == item_id), None)

    @staticmethod
    def item_locked(item: QGraphicsItem) -> bool:
        return bool(item.data(ITEM_LOCKED_ROLE))

    def set_item_locked(self, item: QGraphicsItem, locked: bool, *, commit: bool = True) -> None:
        item.setData(ITEM_LOCKED_ROLE, bool(locked))
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not locked)
        if locked:
            item.setSelected(False)
        if commit:
            self.commit_history()

    def set_item_name(self, item: QGraphicsItem, name: str, *, commit: bool = True) -> None:
        item.setData(ITEM_NAME_ROLE, name.strip() or str(item.data(ITEM_KIND_ROLE)).title())
        if commit:
            self.commit_history()

    def delete_selected(self) -> None:
        changed = False
        for item in list(self.scene.selectedItems()):
            if self.item_locked(item):
                continue
            self.scene.removeItem(item)
            changed = True
        if changed:
            self.commit_history()

    def duplicate_selected(self) -> None:
        states = [self.serialize_item(item) for item in self.scene.selectedItems() if not self.item_locked(item)]
        if not states:
            return
        self.scene.clearSelection()
        for state in states:
            state["id"] = uuid.uuid4().hex
            state["name"] = f"{state.get('name', 'Layer')} copy"
            position = state.get("position", [0.0, 0.0])
            state["position"] = [float(position[0]) + 20.0, float(position[1]) + 20.0]
            clone = self.create_item_from_state(state)
            if clone is not None:
                self.scene.addItem(clone)
                clone.setSelected(True)
        self.commit_history()

    def add_text(self, text: str, font_size: int, font_family: str = "Segoe UI") -> None:
        item = QGraphicsTextItem(text)
        item.setFont(QFont(font_family, font_size, QFont.Weight.Bold))
        item.setDefaultTextColor(self.fill_color)
        item.setTextWidth(min(420.0, self.canvas_rect.width() * 0.55))
        item.setPos(self.canvas_rect.center() - QPointF(item.textWidth() / 2, 30))
        self.prepare_item(item, "text", text[:28] or "Text")
        self.scene.clearSelection()
        self.scene.addItem(item)
        item.setSelected(True)
        self.commit_history()

    def add_image(self, image_path: Path) -> bool:
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            return False
        item = QGraphicsPixmapItem(pixmap)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        maximum_width = self.canvas_rect.width() * 0.65
        maximum_height = self.canvas_rect.height() * 0.65
        image_scale = min(maximum_width / pixmap.width(), maximum_height / pixmap.height(), 1.0)
        item.setTransform(QTransform.fromScale(image_scale, image_scale))
        item.setPos(
            self.canvas_rect.center().x() - pixmap.width() * image_scale / 2,
            self.canvas_rect.center().y() - pixmap.height() * image_scale / 2,
        )
        self.prepare_item(item, "image", image_path.stem)
        self.scene.clearSelection()
        self.scene.addItem(item)
        item.setSelected(True)
        self.commit_history()
        return True

    def bring_selected_forward(self) -> None:
        for item in self.scene.selectedItems():
            item.setZValue(self.next_z_value())
        self.commit_history()

    def send_selected_backward(self) -> None:
        minimum = min((item.zValue() for item in self.design_items()), default=0.0)
        for item in self.scene.selectedItems():
            item.setZValue(minimum - 1.0)
        self.commit_history()

    def align_selected(self, alignment: str) -> None:
        selected = [item for item in self.scene.selectedItems() if not self.item_locked(item)]
        if len(selected) < 2:
            return
        bounds = [item.sceneBoundingRect() for item in selected]
        union = bounds[0]
        for rect in bounds[1:]:
            union = union.united(rect)
        for item, rect in zip(selected, bounds):
            if alignment == "left":
                item.moveBy(union.left() - rect.left(), 0)
            elif alignment == "center_x":
                item.moveBy(union.center().x() - rect.center().x(), 0)
            elif alignment == "right":
                item.moveBy(union.right() - rect.right(), 0)
            elif alignment == "top":
                item.moveBy(0, union.top() - rect.top())
            elif alignment == "center_y":
                item.moveBy(0, union.center().y() - rect.center().y())
            elif alignment == "bottom":
                item.moveBy(0, union.bottom() - rect.bottom())
        self.commit_history()

    def center_selected_on_artboard(self) -> None:
        selected = [item for item in self.scene.selectedItems() if not self.item_locked(item)]
        if not selected:
            return
        union = selected[0].sceneBoundingRect()
        for item in selected[1:]:
            union = union.united(item.sceneBoundingRect())
        delta = self.canvas_rect.center() - union.center()
        for item in selected:
            item.moveBy(delta.x(), delta.y())
        self.commit_history()

    def set_item_scene_rect(self, item: QGraphicsItem, rect: QRectF) -> None:
        rect = rect.normalized()
        rotation = item.rotation()
        item.setRotation(0)
        if isinstance(item, QGraphicsRectItem):
            item.setPos(0, 0)
            item.setRect(rect)
        elif isinstance(item, QGraphicsEllipseItem):
            item.setPos(0, 0)
            item.setRect(rect)
        elif isinstance(item, QGraphicsLineItem):
            item.setPos(0, 0)
            item.setLine(rect.left(), rect.top(), rect.right(), rect.bottom())
        elif isinstance(item, QGraphicsTextItem):
            item.setPos(rect.topLeft())
            item.setTextWidth(max(10.0, rect.width()))
            current_height = max(1.0, item.boundingRect().height())
            item.setScale(max(0.05, rect.height() / current_height))
        elif isinstance(item, QGraphicsPixmapItem):
            pixmap = item.pixmap()
            item.setPos(rect.topLeft())
            item.setTransform(
                QTransform.fromScale(
                    rect.width() / max(1, pixmap.width()),
                    rect.height() / max(1, pixmap.height()),
                )
            )
        elif isinstance(item, QGraphicsPathItem):
            path = item.path()
            old = path.boundingRect()
            if old.width() > 0 and old.height() > 0:
                transform = QTransform()
                transform.translate(rect.left(), rect.top())
                transform.scale(rect.width() / old.width(), rect.height() / old.height())
                transform.translate(-old.left(), -old.top())
                item.setPath(transform.map(path))
                item.setPos(0, 0)
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setRotation(rotation)

    def item_scene_rect(self, item: QGraphicsItem) -> QRectF:
        rotation = item.rotation()
        item.setRotation(0)
        if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            rect = item.mapRectToScene(item.rect())
        elif isinstance(item, QGraphicsLineItem):
            line = item.line()
            rect = item.mapRectToScene(
                QRectF(QPointF(line.x1(), line.y1()), QPointF(line.x2(), line.y2())).normalized()
            )
        elif isinstance(item, QGraphicsPathItem):
            rect = item.mapRectToScene(item.path().boundingRect())
        else:
            rect = item.mapRectToScene(item.boundingRect())
        item.setRotation(rotation)
        return rect

    def scene_rect_to_yards(self, rect: QRectF) -> QRectF:
        return QRectF(
            (rect.x() - self.canvas_rect.x()) / self.canvas_rect.width() * self.physical_width_yards,
            (rect.y() - self.canvas_rect.y()) / self.canvas_rect.height() * self.physical_height_yards,
            rect.width() / self.canvas_rect.width() * self.physical_width_yards,
            rect.height() / self.canvas_rect.height() * self.physical_height_yards,
        )

    def yard_rect_to_scene(self, rect: QRectF) -> QRectF:
        return QRectF(
            self.canvas_rect.x() + rect.x() / self.physical_width_yards * self.canvas_rect.width(),
            self.canvas_rect.y() + rect.y() / self.physical_height_yards * self.canvas_rect.height(),
            rect.width() / self.physical_width_yards * self.canvas_rect.width(),
            rect.height() / self.physical_height_yards * self.canvas_rect.height(),
        )

    def set_selected_yard_rect(self, rect: QRectF) -> None:
        item = self.selected_item()
        if item is None or self.item_locked(item):
            return
        self.set_item_scene_rect(item, self.yard_rect_to_scene(rect))
        self.commit_history()

    def set_selected_rotation_opacity(self, rotation: float, opacity: float) -> None:
        item = self.selected_item()
        if item is None or self.item_locked(item):
            return
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setRotation(float(rotation))
        item.setOpacity(max(0.01, min(1.0, float(opacity))))
        self.commit_history()

    def snap_point(self, point: QPointF) -> QPointF:
        if not self.snap_enabled:
            return point
        x_step = self.canvas_rect.width() / self.physical_width_yards * self.snap_yards
        y_step = self.canvas_rect.height() / self.physical_height_yards * self.snap_yards
        return QPointF(
            self.canvas_rect.left() + round((point.x() - self.canvas_rect.left()) / x_step) * x_step,
            self.canvas_rect.top() + round((point.y() - self.canvas_rect.top()) / y_step) * y_step,
        )

    def snap_selected_items(self) -> None:
        if not self.snap_enabled:
            return
        for item in self.scene.selectedItems():
            if self.item_locked(item):
                continue
            rect = self.item_scene_rect(item)
            snapped = self.snap_point(rect.topLeft())
            item.moveBy(snapped.x() - rect.left(), snapped.y() - rect.top())

    def nudge_selected(self, delta_x_yards: float, delta_y_yards: float) -> None:
        delta_x = delta_x_yards / self.physical_width_yards * self.canvas_rect.width()
        delta_y = delta_y_yards / self.physical_height_yards * self.canvas_rect.height()
        changed = False
        for item in self.scene.selectedItems():
            if self.item_locked(item):
                continue
            item.moveBy(delta_x, delta_y)
            changed = True
        if changed:
            self.commit_history()

    def resize_or_rotate_selected(self, point: QPointF, modifiers: Qt.KeyboardModifier) -> None:
        item = self._handle_item
        if item is None:
            return
        if self._active_handle == "rotate":
            center = self._handle_initial_rect.center()
            angle = degrees(atan2(point.y() - center.y(), point.x() - center.x()))
            rotation = self._handle_initial_rotation + angle - self._handle_start_angle
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                rotation = round(rotation / 15.0) * 15.0
            item.setRotation(rotation)
            return
        rect = QRectF(self._handle_initial_rect)
        key = self._active_handle
        if "w" in key:
            rect.setLeft(point.x())
        if "e" in key:
            rect.setRight(point.x())
        if "n" in key:
            rect.setTop(point.y())
        if "s" in key:
            rect.setBottom(point.y())
        if modifiers & Qt.KeyboardModifier.AltModifier:
            center = self._handle_initial_rect.center()
            if "w" in key or "e" in key:
                half_width = abs(point.x() - center.x())
                rect.setLeft(center.x() - half_width)
                rect.setRight(center.x() + half_width)
            if "n" in key or "s" in key:
                half_height = abs(point.y() - center.y())
                rect.setTop(center.y() - half_height)
                rect.setBottom(center.y() + half_height)
        if modifiers & Qt.KeyboardModifier.ShiftModifier and key not in {"n", "s", "e", "w"}:
            ratio = self._handle_initial_rect.width() / max(1.0, self._handle_initial_rect.height())
            if rect.width() / max(1.0, rect.height()) > ratio:
                rect.setHeight(rect.width() / ratio)
            else:
                rect.setWidth(rect.height() * ratio)
        if rect.width() >= 4 and rect.height() >= 4:
            self.set_item_scene_rect(item, rect.normalized())

    def serialize_items(self) -> list[dict]:
        return [self.serialize_item(item) for item in sorted(self.design_items(), key=lambda value: value.zValue())]

    def serialize_item(self, item: QGraphicsItem) -> dict:
        kind = str(item.data(ITEM_KIND_ROLE) or "shape")
        state: dict = {
            "id": str(item.data(ITEM_ID_ROLE)),
            "kind": kind,
            "name": str(item.data(ITEM_NAME_ROLE) or kind.title()),
            "position": [item.pos().x(), item.pos().y()],
            "rotation": item.rotation(),
            "opacity": item.opacity(),
            "z": item.zValue(),
            "visible": item.isVisible(),
            "locked": self.item_locked(item),
        }
        if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            rect = item.rect()
            state["rect"] = [rect.x(), rect.y(), rect.width(), rect.height()]
            state["pen"] = [color_text(item.pen().color()), item.pen().widthF()]
            state["brush"] = color_text(item.brush().color())
            state["no_fill"] = item.brush().style() == Qt.BrushStyle.NoBrush
        elif isinstance(item, QGraphicsLineItem):
            line = item.line()
            state["line"] = [line.x1(), line.y1(), line.x2(), line.y2()]
            state["pen"] = [color_text(item.pen().color()), item.pen().widthF()]
        elif isinstance(item, QGraphicsPathItem):
            path = item.path()
            state["points"] = [[path.elementAt(index).x, path.elementAt(index).y] for index in range(path.elementCount())]
            state["pen"] = [color_text(item.pen().color()), item.pen().widthF()]
        elif isinstance(item, QGraphicsTextItem):
            font = item.font()
            state["text"] = item.toPlainText()
            state["font"] = [font.family(), font.pointSizeF(), int(font.weight())]
            state["text_width"] = item.textWidth()
            state["text_color"] = color_text(item.defaultTextColor())
            state["scale"] = item.scale()
        elif isinstance(item, QGraphicsPixmapItem):
            png_bytes = self.pixmap_png_bytes(item.pixmap())
            transform = item.transform()
            state["image"] = base64.b64encode(png_bytes).decode("ascii")
            state["transform"] = [
                transform.m11(),
                transform.m12(),
                transform.m21(),
                transform.m22(),
                transform.dx(),
                transform.dy(),
            ]
        return state

    @staticmethod
    def pixmap_png_bytes(pixmap: QPixmap) -> bytes:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice

        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        buffer.close()
        return bytes(data)

    def create_item_from_state(self, state: dict) -> QGraphicsItem | None:
        kind = str(state.get("kind", "rectangle"))
        if kind == "rectangle":
            item: QGraphicsItem = QGraphicsRectItem(QRectF(*state.get("rect", [0, 0, 100, 100])))
        elif kind == "ellipse":
            item = QGraphicsEllipseItem(QRectF(*state.get("rect", [0, 0, 100, 100])))
        elif kind == "line":
            item = QGraphicsLineItem(*state.get("line", [0, 0, 100, 100]))
        elif kind == "path":
            points = state.get("points", [])
            if not points:
                return None
            path = QPainterPath(QPointF(float(points[0][0]), float(points[0][1])))
            for point in points[1:]:
                path.lineTo(float(point[0]), float(point[1]))
            item = QGraphicsPathItem(path)
        elif kind == "text":
            item = QGraphicsTextItem(str(state.get("text", "Text")))
            family, size, weight = state.get("font", ["Segoe UI", 48, int(QFont.Weight.Bold)])
            item.setFont(QFont(str(family), round(float(size)), QFont.Weight(int(weight))))
            item.setTextWidth(float(state.get("text_width", 240)))
            item.setDefaultTextColor(QColor(str(state.get("text_color", "#ff111318"))))
            item.setScale(float(state.get("scale", 1.0)))
        elif kind == "image":
            pixmap = QPixmap()
            try:
                pixmap.loadFromData(base64.b64decode(str(state.get("image", ""))))
            except (ValueError, TypeError):
                return None
            if pixmap.isNull():
                return None
            item = QGraphicsPixmapItem(pixmap)
            item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
            values = state.get("transform", [1, 0, 0, 1, 0, 0])
            item.setTransform(QTransform(*[float(value) for value in values]))
        else:
            return None
        self.prepare_item(
            item,
            kind,
            str(state.get("name", kind.title())),
            str(state.get("id", uuid.uuid4().hex)),
        )
        position = state.get("position", [0, 0])
        item.setPos(float(position[0]), float(position[1]))
        item.setOpacity(float(state.get("opacity", 1.0)))
        item.setZValue(float(state.get("z", self.next_z_value())))
        item.setVisible(bool(state.get("visible", True)))
        self.set_item_locked(item, bool(state.get("locked", False)), commit=False)
        if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
            pen_color, pen_width = state.get("pen", ["#ff16191f", 4.0])
            item.setPen(QPen(QColor(str(pen_color)), float(pen_width)))
            item.setBrush(
                Qt.BrushStyle.NoBrush
                if bool(state.get("no_fill", False))
                else QColor(str(state.get("brush", "#fff7c94a")))
            )
        elif isinstance(item, (QGraphicsLineItem, QGraphicsPathItem)):
            pen_color, pen_width = state.get("pen", ["#ff16191f", 4.0])
            pen = QPen(QColor(str(pen_color)), float(pen_width))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            item.setPen(pen)
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setRotation(float(state.get("rotation", 0.0)))
        return item

    def restore_items(self, states: list[dict], *, emit: bool = True) -> None:
        self._restoring = True
        self.scene.clear()
        for state in states:
            item = self.create_item_from_state(state)
            if item is not None:
                self.scene.addItem(item)
        self._restoring = False
        if emit:
            self.designChanged.emit()
            self.selectionChangedDetailed.emit()
        self.viewport().update()

    def commit_history(self) -> None:
        if self._restoring:
            return
        state = self.serialize_items()
        if self._history and state == self._history[self._history_index]:
            return
        self._history = self._history[: self._history_index + 1]
        self._history.append(state)
        if len(self._history) > 80:
            self._history.pop(0)
        self._history_index = len(self._history) - 1
        self.designChanged.emit()
        self.selectionChangedDetailed.emit()
        self.emit_status()

    def reset_history(self) -> None:
        self._history = [self.serialize_items()]
        self._history_index = 0

    def undo(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self.restore_items(self._history[self._history_index])
        self.emit_status()

    def redo(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self.restore_items(self._history[self._history_index])
        self.emit_status()

    def clear_design(self) -> None:
        if not self.design_items():
            return
        self.scene.clear()
        self.commit_history()

    def render_image(self, max_dimension: int = 4096) -> QImage:
        ratio = self.physical_width_yards / self.physical_height_yards
        long_dimension = min(max_dimension, max(1024, round(max(self.physical_width_yards, self.physical_height_yards) * 180)))
        if ratio >= 1:
            image_width = long_dimension
            image_height = max(1, round(long_dimension / ratio))
        else:
            image_height = long_dimension
            image_width = max(1, round(long_dimension * ratio))
        image = QImage(image_width, image_height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        selected = self.scene.selectedItems()
        self.scene.clearSelection()
        painter = QPainter(image)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.scene.render(
            painter,
            QRectF(0, 0, image.width(), image.height()),
            self.canvas_rect,
            Qt.AspectRatioMode.IgnoreAspectRatio,
        )
        painter.end()
        for item in selected:
            item.setSelected(True)
        return image

    def has_content(self) -> bool:
        return bool(self.design_items())

    def emit_status(self) -> None:
        selected = self.scene.selectedItems()
        selection_text = "No selection"
        if len(selected) == 1:
            rect = self.scene_rect_to_yards(selected[0].sceneBoundingRect())
            selection_text = f"Selected: {rect.width():.2f} × {rect.height():.2f} yd"
        elif len(selected) > 1:
            selection_text = f"{len(selected)} layers selected"
        self.statusChanged.emit(
            f"{self.physical_width_yards:g} × {self.physical_height_yards:g} yd artboard   •   "
            f"{self.zoom_percent()}%   •   {selection_text}"
        )


class PropFieldPreview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.width_yards = 8.0
        self.height_yards = 4.0
        self.field_x = 0.0
        self.field_y = -31.5
        self.field_mode = "white"
        self.view_width_yards = 120.0
        self.preview_image = QImage()
        self.setMinimumHeight(260)

    def set_preview(
        self,
        image: QImage,
        width_yards: float,
        height_yards: float,
        field_x: float,
        field_y: float,
        field_mode: str,
        view_width_yards: float = 120.0,
    ) -> None:
        self.preview_image = image
        self.width_yards = max(0.1, float(width_yards))
        self.height_yards = max(0.1, float(height_yards))
        self.field_x = float(field_x)
        self.field_y = float(field_y)
        self.field_mode = field_mode
        self.view_width_yards = max(20.0, min(120.0, float(view_width_yards)))
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        outer = QRectF(self.rect()).adjusted(10, 10, -10, -34)
        palettes = {
            "white": (QColor("#f8faf7"), QColor("#59636c"), QColor("#20262d")),
            "inverted": (QColor("#050607"), QColor("#e8edf4"), QColor("#ffffff")),
            "grass": (QColor("#2f7d3b"), QColor("#e8f8e7"), QColor("#ffffff")),
        }
        fill, line, text = palettes.get(self.field_mode, palettes["white"])
        ratio = 120 / 80
        width = outer.width()
        height = width / ratio
        if height > outer.height():
            height = outer.height()
            width = height * ratio
        stage = QRectF(outer.center().x() - width / 2, outer.center().y() - height / 2, width, height)
        painter.setPen(QPen(QColor("#606a76"), 1))
        painter.setBrush(QColor("#151a22"))
        painter.drawRoundedRect(stage, 5, 5)
        view_height_yards = self.view_width_yards / ratio
        view_center_x = 0.0 if self.view_width_yards >= 119.9 else self.field_x
        view_center_y = 0.0 if self.view_width_yards >= 119.9 else self.field_y
        view_left = view_center_x - self.view_width_yards / 2
        view_top = view_center_y + view_height_yards / 2

        def map_x(value: float) -> float:
            return stage.left() + (value - view_left) / self.view_width_yards * stage.width()

        def map_y(value: float) -> float:
            return stage.top() + (view_top - value) / view_height_yards * stage.height()

        field = QRectF(
            QPointF(map_x(-60), map_y(26.666)),
            QPointF(map_x(60), map_y(-26.666)),
        ).normalized().intersected(stage)
        painter.setPen(QPen(line, 1))
        painter.setBrush(fill)
        painter.drawRect(field)
        for yard in range(-60, 61, 5):
            x_position = map_x(yard)
            if not stage.left() <= x_position <= stage.right():
                continue
            painter.setPen(QPen(line, 1.0 if yard % 10 == 0 else 0.45))
            painter.drawLine(QPointF(x_position, field.top()), QPointF(x_position, field.bottom()))
        for hash_y in (-10.666, 10.666):
            y_position = map_y(hash_y)
            if not field.top() <= y_position <= field.bottom():
                continue
            painter.setPen(QPen(line, 0.7, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(field.left(), y_position), QPointF(field.right(), y_position))
        target = QRectF(
            map_x(self.field_x - self.width_yards / 2),
            map_y(self.field_y + self.height_yards / 2),
            self.width_yards / self.view_width_yards * stage.width(),
            self.height_yards / view_height_yards * stage.height(),
        )
        if not self.preview_image.isNull():
            painter.drawImage(target, self.preview_image)
        painter.setPen(QPen(QColor("#f7c94a"), 1.4, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(target)
        person_height = 1.9 / view_height_yards * stage.height()
        person_x = min(stage.right() - 8, target.right() + 8)
        person_y = target.bottom()
        painter.setPen(QPen(QColor("#38bdf8"), 1.6))
        painter.drawLine(QPointF(person_x, person_y), QPointF(person_x, person_y - person_height))
        painter.drawEllipse(QPointF(person_x, person_y - person_height - 2), 2, 2)
        painter.setPen(text)
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(
            QRectF(outer.left(), outer.bottom() + 5, outer.width(), 22),
            Qt.AlignmentFlag.AlignCenter,
            f"Actual field scale: {self.width_yards:g} × {self.height_yards:g} yd   •   {self.view_width_yards:g}-yard view",
        )
        painter.end()


class PropDesignerDialog(QDialog):
    def __init__(self, project_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project_dir = project_dir
        self.created_design: CreatedPropDesign | None = None
        self._syncing = False
        self._syncing_layers = False
        self.setWindowTitle("Prop Studio")
        self.setModal(True)
        self.setMinimumSize(980, 620)
        self.canvas = PropDesignerCanvas()
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(1500, round(available.width() * 0.92)), min(900, round(available.height() * 0.90)))
        else:
            self.resize(1280, 760)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(7)
        root.addWidget(self.build_top_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.build_tool_rail())
        splitter.addWidget(self.build_canvas_workspace())
        splitter.addWidget(self.build_inspector())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([92, 880, 330])
        root.addWidget(splitter, 1)
        root.addLayout(self.build_bottom_bar())

        self.canvas.scene.selectionChanged.connect(self.sync_selected_controls)
        self.canvas.selectionChangedDetailed.connect(self.refresh_layers)
        self.canvas.designChanged.connect(self.design_changed)
        self.canvas.statusChanged.connect(self.status_label.setText)
        self.canvas.textRequested.connect(self.add_text)
        self.canvas.imageRequested.connect(self.import_image)
        self.width_yards.editingFinished.connect(self.apply_design_size)
        self.height_yards.editingFinished.connect(self.apply_design_size)
        self.field_x.valueChanged.connect(self.refresh_field_preview)
        self.field_y.valueChanged.connect(self.refresh_field_preview)
        self.preview_mode.currentIndexChanged.connect(self.refresh_field_preview)
        self.preview_zoom.currentIndexChanged.connect(self.refresh_field_preview)
        self.grid_checkbox.toggled.connect(self.apply_grid_settings)
        self.snap_checkbox.toggled.connect(self.apply_grid_settings)
        self.snap_interval.valueChanged.connect(self.apply_grid_settings)
        self.layers_list.itemSelectionChanged.connect(self.layer_selection_changed)
        self.layers_list.itemChanged.connect(self.layer_item_changed)
        self.update_color_button(self.fill_button, QColor("#f7c94a"))
        self.update_color_button(self.stroke_button, QColor("#16191f"))
        self.apply_grid_settings()
        self.apply_design_size()
        self.refresh_layers()
        self.refresh_field_preview()
        QTimer.singleShot(0, self.canvas.fit_artboard)

    def build_top_toolbar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(5)
        for label, callback, tooltip in (
            ("New", self.confirm_clear, "Clear the current design"),
            ("Open", self.open_design, "Open an editable .dpprop.json document"),
            ("Undo", self.undo, "Undo (Ctrl+Z)"),
            ("Redo", self.redo, "Redo (Ctrl+Y)"),
        ):
            button = QToolButton()
            button.setText(label)
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            layout.addWidget(button)
        layout.addSpacing(10)
        self.grid_checkbox = QCheckBox("Grid")
        self.grid_checkbox.setChecked(True)
        self.snap_checkbox = QCheckBox("Snap")
        self.snap_checkbox.setChecked(True)
        self.snap_interval = QDoubleSpinBox()
        self.snap_interval.setRange(0.05, 2.0)
        self.snap_interval.setDecimals(2)
        self.snap_interval.setSingleStep(0.05)
        self.snap_interval.setValue(0.25)
        self.snap_interval.setSuffix(" yd")
        self.snap_interval.setMaximumWidth(92)
        layout.addWidget(self.grid_checkbox)
        layout.addWidget(self.snap_checkbox)
        layout.addWidget(self.snap_interval)
        layout.addStretch(1)
        for label, callback in (("−", lambda: self.canvas.zoom_by(1 / 1.2)), ("Fit", self.canvas.fit_artboard), ("+", lambda: self.canvas.zoom_by(1.2))):
            button = QToolButton()
            button.setText(label)
            button.clicked.connect(callback)
            layout.addWidget(button)
        return bar

    def build_tool_rail(self) -> QWidget:
        rail = QWidget()
        rail.setMinimumWidth(84)
        rail.setMaximumWidth(104)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(3, 4, 3, 4)
        layout.setSpacing(5)
        title = QLabel("TOOLS")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        group = QButtonGroup(self)
        group.setExclusive(True)
        self.tool_buttons: dict[str, QToolButton] = {}
        for label, tool, shortcut in (
            ("Select", "select", "V"),
            ("Rectangle", "rectangle", "R"),
            ("Ellipse", "ellipse", "E"),
            ("Line", "line", "L"),
            ("Pen", "pen", "P"),
        ):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setToolTip(f"{label} tool ({shortcut})")
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, value=tool: self.select_tool(value))
            group.addButton(button)
            layout.addWidget(button)
            self.tool_buttons[tool] = button
        self.tool_buttons["select"].setChecked(True)
        text_button = QToolButton()
        text_button.setText("Text")
        text_button.setToolTip("Add text (T)")
        text_button.clicked.connect(self.add_text)
        image_button = QToolButton()
        image_button.setText("Image")
        image_button.setToolTip("Import an image layer (I)")
        image_button.clicked.connect(self.import_image)
        layout.addWidget(text_button)
        layout.addWidget(image_button)
        layout.addStretch(1)
        return rail

    def build_canvas_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.canvas.setMinimumSize(520, 400)
        layout.addWidget(self.canvas, 1)
        self.status_label = QLabel("Artboard")
        self.status_label.setMinimumHeight(24)
        layout.addWidget(self.status_label)
        return workspace

    def build_inspector(self) -> QWidget:
        shell = QWidget()
        shell.setMinimumWidth(300)
        shell.setMaximumWidth(430)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.addTab(self.build_design_tab(), "Design")
        self.tabs.addTab(self.build_properties_tab(), "Properties")
        self.tabs.addTab(self.build_layers_tab(), "Layers")
        self.tabs.addTab(self.build_field_tab(), "Field Preview")
        layout.addWidget(self.tabs)
        return shell

    @staticmethod
    def scroll_tab(content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

    def build_design_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        metadata = QGroupBox("Prop Document")
        form = QFormLayout(metadata)
        self.name_input = QLineEdit("Designed Prop")
        self.layer_input = QLineEdit("Props")
        self.width_yards = QDoubleSpinBox()
        self.width_yards.setRange(0.25, 80)
        self.width_yards.setDecimals(2)
        self.width_yards.setValue(8.0)
        self.width_yards.setSuffix(" yd")
        self.height_yards = QDoubleSpinBox()
        self.height_yards.setRange(0.25, 40)
        self.height_yards.setDecimals(2)
        self.height_yards.setValue(4.0)
        self.height_yards.setSuffix(" yd")
        form.addRow("Name", self.name_input)
        form.addRow("Project Layer", self.layer_input)
        form.addRow("Field Width", self.width_yards)
        form.addRow("Field Height", self.height_yards)
        layout.addWidget(metadata)
        note = QLabel(
            "The artboard is measured in real yards. Rulers, grid spacing, object dimensions, "
            "and the field preview all use the exact size that will be placed in drill."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        shortcuts = QGroupBox("Fast Workflow")
        shortcuts_layout = QVBoxLayout(shortcuts)
        shortcuts_label = QLabel(
            "V Select   R Rectangle   E Ellipse   L Line   P Pen\n"
            "Ctrl+D Duplicate   Delete Remove   Arrows Nudge\n"
            "Shift+Arrow 1 yard   Ctrl+wheel Zoom   0 Fit"
        )
        shortcuts_label.setWordWrap(True)
        shortcuts_layout.addWidget(shortcuts_label)
        layout.addWidget(shortcuts)
        layout.addStretch(1)
        return self.scroll_tab(content)

    def build_properties_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        geometry = QGroupBox("Selected Layer")
        form = QFormLayout(geometry)
        self.item_name = QLineEdit()
        self.shape_x = self.yard_spin(-80, 80)
        self.shape_y = self.yard_spin(-40, 40)
        self.shape_w = self.yard_spin(0.01, 80)
        self.shape_h = self.yard_spin(0.01, 40)
        self.shape_rotation = QDoubleSpinBox()
        self.shape_rotation.setRange(-360, 360)
        self.shape_rotation.setDecimals(1)
        self.shape_rotation.setSuffix("°")
        self.shape_opacity = QSlider(Qt.Orientation.Horizontal)
        self.shape_opacity.setRange(1, 100)
        self.shape_opacity.setValue(100)
        self.shape_opacity_label = QLabel("100%")
        opacity_row = QWidget()
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.addWidget(self.shape_opacity, 1)
        opacity_layout.addWidget(self.shape_opacity_label)
        self.shape_locked = QCheckBox("Lock this layer")
        apply_geometry = QPushButton("Apply Geometry")
        apply_geometry.clicked.connect(self.apply_selected_properties)
        form.addRow("Layer Name", self.item_name)
        form.addRow("X from Left", self.shape_x)
        form.addRow("Y from Top", self.shape_y)
        form.addRow("Width", self.shape_w)
        form.addRow("Height", self.shape_h)
        form.addRow("Rotation", self.shape_rotation)
        form.addRow("Opacity", opacity_row)
        form.addRow("", self.shape_locked)
        form.addRow(apply_geometry)
        layout.addWidget(geometry)

        style = QGroupBox("Appearance")
        style_form = QFormLayout(style)
        self.fill_button = QPushButton("Fill")
        self.fill_button.clicked.connect(self.choose_fill)
        self.stroke_button = QPushButton("Stroke")
        self.stroke_button.clicked.connect(self.choose_stroke)
        self.no_fill = QCheckBox("Transparent fill")
        self.stroke_width = QDoubleSpinBox()
        self.stroke_width.setRange(0.25, 80)
        self.stroke_width.setDecimals(2)
        self.stroke_width.setValue(4.0)
        self.stroke_width.setSuffix(" px")
        apply_style = QPushButton("Apply Appearance")
        apply_style.clicked.connect(self.apply_style)
        style_form.addRow("Fill", self.fill_button)
        style_form.addRow("Stroke", self.stroke_button)
        style_form.addRow("Stroke Width", self.stroke_width)
        style_form.addRow("", self.no_fill)
        style_form.addRow(apply_style)
        layout.addWidget(style)

        align = QGroupBox("Arrange")
        grid = QGridLayout(align)
        for index, (label, value) in enumerate(
            (("Left", "left"), ("Center X", "center_x"), ("Right", "right"), ("Top", "top"), ("Center Y", "center_y"), ("Bottom", "bottom"))
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, target=value: self.canvas.align_selected(target))
            grid.addWidget(button, index // 3, index % 3)
        center_button = QPushButton("Center on Artboard")
        center_button.clicked.connect(self.canvas.center_selected_on_artboard)
        grid.addWidget(center_button, 2, 0, 1, 3)
        layout.addWidget(align)
        layout.addStretch(1)
        self.property_widgets = [
            self.item_name,
            self.shape_x,
            self.shape_y,
            self.shape_w,
            self.shape_h,
            self.shape_rotation,
            self.shape_opacity,
            self.shape_locked,
        ]
        self.shape_opacity.valueChanged.connect(lambda value: self.shape_opacity_label.setText(f"{value}%"))
        return self.scroll_tab(content)

    def build_layers_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        hint = QLabel("Top layers render in front. Uncheck a layer to hide it; double-click its name to rename it.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.layers_list = QListWidget()
        self.layers_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.layers_list, 1)
        buttons = QGridLayout()
        actions = (
            ("Up", self.canvas_bring_forward),
            ("Down", self.canvas_send_backward),
            ("Duplicate", self.canvas_duplicate),
            ("Delete", self.canvas_delete),
            ("Lock/Unlock", self.toggle_layer_lock),
        )
        for index, (label, callback) in enumerate(actions):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button, index // 2, index % 2)
        layout.addLayout(buttons)
        return content

    def build_field_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        form = QFormLayout()
        self.field_x = self.yard_spin(-60, 60)
        self.field_x.setValue(0.0)
        self.field_y = self.yard_spin(-40, 40)
        self.field_y.setValue(-31.5)
        self.preview_mode = QComboBox()
        self.preview_mode.addItem("White Field", "white")
        self.preview_mode.addItem("Inverted Field", "inverted")
        self.preview_mode.addItem("Grass Field", "grass")
        self.preview_zoom = QComboBox()
        self.preview_zoom.addItem("Full Field (120 yd)", 120.0)
        self.preview_zoom.addItem("60-yard Detail", 60.0)
        self.preview_zoom.addItem("30-yard Detail", 30.0)
        self.preview_zoom.addItem("20-yard Detail", 20.0)
        form.addRow("Initial Center X", self.field_x)
        form.addRow("Initial Center Y", self.field_y)
        form.addRow("Field Style", self.preview_mode)
        form.addRow("Preview Range", self.preview_zoom)
        layout.addLayout(form)
        self.field_preview = PropFieldPreview()
        layout.addWidget(self.field_preview, 1)
        note = QLabel(
            "The gold outline is the prop's exact field footprint. The blue figure is approximately "
            "a six-foot performer for immediate scale comparison."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        return content

    def build_bottom_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        clear_button = QPushButton("Clear Design")
        clear_button.clicked.connect(self.confirm_clear)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        save_button = QPushButton("Save Prop to Project")
        save_button.setObjectName("PrimaryButton")
        save_button.clicked.connect(self.save_design)
        layout.addWidget(clear_button)
        layout.addStretch(1)
        layout.addWidget(cancel_button)
        layout.addWidget(save_button)
        return layout

    @staticmethod
    def yard_spin(minimum: float, maximum: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setSingleStep(0.25)
        spin.setSuffix(" yd")
        return spin

    def select_tool(self, tool: str) -> None:
        self.canvas.set_tool(tool)
        button = self.tool_buttons.get(tool)
        if button is not None:
            button.setChecked(True)

    def apply_grid_settings(self) -> None:
        self.canvas.set_grid_options(
            self.grid_checkbox.isChecked(),
            self.snap_checkbox.isChecked(),
            self.snap_interval.value(),
        )

    def apply_design_size(self) -> None:
        self.canvas.set_physical_size(self.width_yards.value(), self.height_yards.value())
        self.refresh_field_preview()

    def add_text(self) -> None:
        text, accepted = QInputDialog.getText(self, "Add Text Layer", "Text:")
        if not accepted or not text.strip():
            return
        size, size_ok = QInputDialog.getInt(self, "Text Size", "Font size:", 64, 8, 320, 1)
        if size_ok:
            self.canvas.add_text(text.strip(), size)

    def import_image(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Import Image Layer",
            str(Path.home() / "Pictures"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if path and not self.canvas.add_image(Path(path)):
            QMessageBox.warning(self, "Image Import Failed", "That image could not be loaded.")

    def choose_fill(self) -> None:
        color = QColorDialog.getColor(QColor(self.fill_button.property("selected_color") or "#f7c94a"), self)
        if color.isValid():
            self.update_color_button(self.fill_button, color)

    def choose_stroke(self) -> None:
        color = QColorDialog.getColor(QColor(self.stroke_button.property("selected_color") or "#16191f"), self)
        if color.isValid():
            self.update_color_button(self.stroke_button, color)

    @staticmethod
    def update_color_button(button: QPushButton, color: QColor) -> None:
        button.setProperty("selected_color", color.name())
        text = "#101419" if color.lightness() > 150 else "#ffffff"
        button.setText(color.name())
        button.setStyleSheet(f"background:{color.name()}; color:{text};")

    def apply_style(self) -> None:
        self.canvas.set_style(
            QColor(self.fill_button.property("selected_color") or "#f7c94a"),
            QColor(self.stroke_button.property("selected_color") or "#16191f"),
            self.stroke_width.value(),
            self.no_fill.isChecked(),
        )
        self.canvas.apply_style_to_selected()

    def sync_selected_controls(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        item = self.canvas.selected_item()
        enabled = item is not None
        for widget in self.property_widgets:
            widget.setEnabled(enabled)
        if item is not None:
            rect = self.canvas.scene_rect_to_yards(self.canvas.item_scene_rect(item))
            self.item_name.setText(str(item.data(ITEM_NAME_ROLE) or "Layer"))
            for spin, value in (
                (self.shape_x, rect.x()),
                (self.shape_y, rect.y()),
                (self.shape_w, rect.width()),
                (self.shape_h, rect.height()),
                (self.shape_rotation, item.rotation()),
            ):
                spin.setValue(value)
            self.shape_opacity.setValue(round(item.opacity() * 100))
            self.shape_locked.setChecked(self.canvas.item_locked(item))
            if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
                self.update_color_button(self.fill_button, item.brush().color())
                self.update_color_button(self.stroke_button, item.pen().color())
                self.stroke_width.setValue(item.pen().widthF())
                self.no_fill.setChecked(item.brush().style() == Qt.BrushStyle.NoBrush)
            elif isinstance(item, (QGraphicsLineItem, QGraphicsPathItem)):
                self.update_color_button(self.stroke_button, item.pen().color())
                self.stroke_width.setValue(item.pen().widthF())
            elif isinstance(item, QGraphicsTextItem):
                self.update_color_button(self.fill_button, item.defaultTextColor())
        self._syncing = False
        self.refresh_layers()

    def apply_selected_properties(self) -> None:
        item = self.canvas.selected_item()
        if item is None:
            return
        was_locked = self.canvas.item_locked(item)
        if was_locked and not self.shape_locked.isChecked():
            self.canvas.set_item_locked(item, False, commit=False)
        if not self.canvas.item_locked(item):
            self.canvas.set_item_name(item, self.item_name.text(), commit=False)
            self.canvas.set_item_scene_rect(
                item,
                self.canvas.yard_rect_to_scene(
                    QRectF(
                        self.shape_x.value(),
                        self.shape_y.value(),
                        max(0.01, self.shape_w.value()),
                        max(0.01, self.shape_h.value()),
                    )
                ),
            )
            item.setRotation(self.shape_rotation.value())
            item.setOpacity(self.shape_opacity.value() / 100.0)
        self.canvas.set_item_locked(item, self.shape_locked.isChecked(), commit=False)
        self.canvas.commit_history()

    def refresh_layers(self) -> None:
        if self._syncing_layers:
            return
        self._syncing_layers = True
        selected_ids = {str(item.data(ITEM_ID_ROLE)) for item in self.canvas.scene.selectedItems()}
        self.layers_list.clear()
        for item in sorted(self.canvas.design_items(), key=lambda value: value.zValue(), reverse=True):
            name = str(item.data(ITEM_NAME_ROLE) or item.data(ITEM_KIND_ROLE) or "Layer")
            if self.canvas.item_locked(item):
                name = f"🔒 {name}"
            row = QListWidgetItem(name)
            row.setData(Qt.ItemDataRole.UserRole, str(item.data(ITEM_ID_ROLE)))
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(Qt.CheckState.Checked if item.isVisible() else Qt.CheckState.Unchecked)
            self.layers_list.addItem(row)
            row.setSelected(str(item.data(ITEM_ID_ROLE)) in selected_ids)
        self._syncing_layers = False

    def layer_selection_changed(self) -> None:
        if self._syncing_layers:
            return
        selected_ids = [
            str(row.data(Qt.ItemDataRole.UserRole))
            for row in self.layers_list.selectedItems()
        ]
        self.canvas.scene.clearSelection()
        selected_any = False
        for item_id in selected_ids:
            item = self.canvas.item_by_id(item_id)
            if item is not None and not self.canvas.item_locked(item):
                item.setSelected(True)
                selected_any = True
        if selected_any:
            self.tabs.setCurrentIndex(1)

    def layer_item_changed(self, row: QListWidgetItem) -> None:
        if self._syncing_layers:
            return
        item = self.canvas.item_by_id(str(row.data(Qt.ItemDataRole.UserRole)))
        if item is None:
            return
        item.setVisible(row.checkState() == Qt.CheckState.Checked)
        entered_name = row.text().removeprefix("🔒 ").strip()
        self.canvas.set_item_name(item, entered_name, commit=False)
        self.canvas.commit_history()

    def selected_layer_items(self) -> list[QGraphicsItem]:
        items = []
        for row in self.layers_list.selectedItems():
            item = self.canvas.item_by_id(str(row.data(Qt.ItemDataRole.UserRole)))
            if item is not None:
                items.append(item)
        return items

    def select_layer_items_on_canvas(self) -> None:
        self.canvas.scene.clearSelection()
        for item in self.selected_layer_items():
            if not self.canvas.item_locked(item):
                item.setSelected(True)

    def canvas_bring_forward(self) -> None:
        self.select_layer_items_on_canvas()
        self.canvas.bring_selected_forward()

    def canvas_send_backward(self) -> None:
        self.select_layer_items_on_canvas()
        self.canvas.send_selected_backward()

    def canvas_duplicate(self) -> None:
        self.select_layer_items_on_canvas()
        self.canvas.duplicate_selected()

    def canvas_delete(self) -> None:
        self.select_layer_items_on_canvas()
        self.canvas.delete_selected()

    def toggle_layer_lock(self) -> None:
        items = self.selected_layer_items()
        if not items:
            return
        target = not all(self.canvas.item_locked(item) for item in items)
        for item in items:
            self.canvas.set_item_locked(item, target, commit=False)
        self.canvas.commit_history()

    def design_changed(self) -> None:
        self.refresh_layers()
        self.refresh_field_preview()

    def refresh_field_preview(self) -> None:
        if not hasattr(self, "field_preview"):
            return
        image = self.canvas.render_image(max_dimension=900) if self.canvas.has_content() else QImage()
        self.field_preview.set_preview(
            image,
            self.width_yards.value(),
            self.height_yards.value(),
            self.field_x.value(),
            self.field_y.value(),
            str(self.preview_mode.currentData() or "white"),
            float(self.preview_zoom.currentData() or 120.0),
        )

    def undo(self) -> None:
        self.canvas.undo()

    def redo(self) -> None:
        self.canvas.redo()

    def confirm_clear(self) -> None:
        if not self.canvas.has_content():
            return
        if QMessageBox.question(self, "Clear Prop Design", "Remove every layer from this prop design?") == QMessageBox.StandardButton.Yes:
            self.canvas.clear_design()

    def design_document(self) -> dict:
        return {
            "schema_version": DESIGN_DOCUMENT_VERSION,
            "name": self.name_input.text().strip() or "Designed Prop",
            "project_layer": self.layer_input.text().strip() or "Props",
            "width_yards": self.width_yards.value(),
            "height_yards": self.height_yards.value(),
            "field_x": self.field_x.value(),
            "field_y": self.field_y.value(),
            "items": self.canvas.serialize_items(),
        }

    def open_design(self) -> None:
        props_dir = self.project_dir / "props"
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Open Prop Design",
            str(props_dir),
            "Drill Pirate Prop (*.dpprop.json);;JSON (*.json)",
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise ValueError("The file does not contain a valid prop design.")
            self.name_input.setText(str(payload.get("name", "Designed Prop")))
            self.layer_input.setText(str(payload.get("project_layer", "Props")))
            self.width_yards.setValue(float(payload.get("width_yards", 8.0)))
            self.height_yards.setValue(float(payload.get("height_yards", 4.0)))
            self.field_x.setValue(float(payload.get("field_x", 0.0)))
            self.field_y.setValue(float(payload.get("field_y", -31.5)))
            self.canvas.set_physical_size(self.width_yards.value(), self.height_yards.value(), rescale_items=False)
            self.canvas.restore_items(payload["items"])
            self.canvas.reset_history()
            self.canvas.fit_artboard()
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Open Prop Failed", f"Drill Pirate could not open that prop design.\n\n{exc}")

    def save_design(self) -> None:
        if not self.canvas.has_content():
            QMessageBox.information(self, "Prop Studio", "Add at least one layer before saving the prop.")
            return
        name = self.name_input.text().strip() or "Designed Prop"
        props_dir = self.project_dir / "props"
        props_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(char for char in name if char.isalnum() or char in (" ", "-", "_")).strip().replace(" ", "_")
        timestamp = int(time.time())
        base_name = f"{safe_name or 'prop'}_{timestamp}"
        image_path = props_dir / f"{base_name}.png"
        design_path = props_dir / f"{base_name}.dpprop.json"
        image = self.canvas.render_image()
        try:
            if not image.save(str(image_path), "PNG"):
                raise OSError("The PNG renderer did not save the image.")
            temporary = design_path.with_suffix(".tmp.json")
            temporary.write_text(json.dumps(self.design_document(), indent=2), encoding="utf-8")
            temporary.replace(design_path)
        except OSError as exc:
            image_path.unlink(missing_ok=True)
            QMessageBox.warning(self, "Prop Save Failed", f"Drill Pirate could not save this prop.\n\n{exc}")
            return
        self.created_design = CreatedPropDesign(
            name=name,
            image_file=str(image_path.relative_to(self.project_dir)),
            width=self.width_yards.value(),
            height=self.height_yards.value(),
            layer=self.layer_input.text().strip() or "Props",
            x=self.field_x.value(),
            y=self.field_y.value(),
            design_file=str(design_path.relative_to(self.project_dir)),
        )
        self.accept()
