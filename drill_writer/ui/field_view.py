from __future__ import annotations

from enum import Enum
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QMenu,
)

from drill_writer.core.models import Dot, DrillProject


class EditorTool(str, Enum):
    SELECT = "select"
    LINE = "line"
    CURVE = "curve"
    ARC = "arc"
    SCATTER = "scatter"
    MIRROR = "mirror"
    SHAPE_LINE = "shape_line"


class DotItem(QGraphicsEllipseItem):
    def __init__(self, dot: Dot, scale: float) -> None:
        radius = 0.5 * scale
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.dot_id = dot.id
        self.setBrush(QColor(dot.color))
        self.setPen(QPen(QColor("#101216"), 0.1 * scale))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setZValue(10)
        self.label = QGraphicsTextItem(dot.name, self)
        self.label.setDefaultTextColor(QColor("#111318"))
        self.label.setScale(0.1 * scale)
        self.label.setPos(radius, -radius)


class PreviewHandleItem(QGraphicsEllipseItem):
    def __init__(self, kind: str, scale: float) -> None:
        radius = 0.8 * scale
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.kind = kind
        self.setBrush(QColor("#ffffff"))
        self.setPen(QPen(QColor("#f7d154"), 0.18 * scale))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(25)


class PathCurveItem(QGraphicsPathItem):
    def __init__(self, dot_id: str, path: QPainterPath, scale: float) -> None:
        super().__init__(path)
        self.dot_id = dot_id
        self.setPen(QPen(QColor("#f7d154"), 0.28 * scale, Qt.PenStyle.DashLine))
        self.setZValue(5)


class ShapeLineItem(QGraphicsPathItem):
    def __init__(self, path: QPainterPath, scale: float) -> None:
        super().__init__(path)
        self.setPen(QPen(QColor("#e53935"), 0.42 * scale))
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(8)


class PathAnchorItem(QGraphicsEllipseItem):
    def __init__(self, dot_id: str, index: int, scale: float) -> None:
        radius = 0.55 * scale
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.dot_id = dot_id
        self.index = index
        self.setBrush(QColor("#e53935"))
        self.setPen(QPen(QColor("#ffffff"), 0.12 * scale))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(26)


class FieldView(QGraphicsView):
    selection_changed = Signal(list)
    dot_moved = Signal(str, float, float)
    dots_moved = Signal(dict)
    context_action = Signal(str)
    preview_handle_moved = Signal(str, float, float)
    path_anchor_added = Signal(str, float, float)
    path_anchor_moved = Signal(str, int, float, float)
    shape_anchor_added = Signal(float, float)
    shape_anchor_toggled = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.scale_factor = 10.0
        self.project: DrillProject | None = None
        self.dot_items: dict[str, DotItem] = {}
        self.active_tool = EditorTool.SELECT
        self.show_labels = True
        self.show_ghosts = True
        self.preview_items: list[QGraphicsItem] = []
        self.path_items: list[QGraphicsItem] = []
        self._formation_callback: Callable[[EditorTool], None] | None = None
        self._pan_start: QPointF | None = None
        self._drag_start_positions: dict[str, tuple[float, float]] = {}
        self._active_preview_handle: PreviewHandleItem | None = None
        self._active_path_anchor: PathAnchorItem | None = None
        self._preserved_selection_ids: list[str] = []
        self._suppress_next_context_menu = False
        self._manual_drag_item: PreviewHandleItem | PathAnchorItem | None = None
        self.draw_field()

    def set_project(self, project: DrillProject) -> None:
        self.project = project
        self.rebuild_dots()

    def set_tool(self, tool: EditorTool) -> None:
        self.active_tool = tool
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag
            if tool == EditorTool.SELECT
            else QGraphicsView.DragMode.NoDrag
        )
        for item in self.dot_items.values():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, tool == EditorTool.SELECT)

    def set_formation_callback(self, callback: Callable[[EditorTool], None]) -> None:
        self._formation_callback = callback

    def selected_dot_ids(self) -> list[str]:
        return [
            item.dot_id
            for item in self.scene.selectedItems()
            if isinstance(item, DotItem)
        ]

    def preserve_selection(self) -> None:
        self._preserved_selection_ids = self.selected_dot_ids()

    def restore_preserved_selection(self) -> None:
        if not self._preserved_selection_ids:
            return
        for dot_id in self._preserved_selection_ids:
            item = self.dot_items.get(dot_id)
            if item:
                item.setSelected(True)

    def set_positions(self, positions: dict[str, tuple[float, float]]) -> None:
        for dot_id, position in positions.items():
            item = self.dot_items.get(dot_id)
            if item:
                item.setPos(self.field_to_scene(*position))

    def show_preview(
        self,
        starts: dict[str, tuple[float, float]],
        targets: dict[str, tuple[float, float]],
        handles: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.clear_preview()
        preview_pen = QPen(QColor("#f7d154"), 0.14 * self.scale_factor, Qt.PenStyle.DashLine)
        preview_fill = QColor(247, 209, 84, 120)
        radius = 0.42 * self.scale_factor
        for dot_id, target in targets.items():
            start = starts.get(dot_id)
            if start:
                line = QGraphicsLineItem()
                line.setLine(
                    self.field_to_scene(*start).x(),
                    self.field_to_scene(*start).y(),
                    self.field_to_scene(*target).x(),
                    self.field_to_scene(*target).y(),
                )
                line.setPen(preview_pen)
                line.setZValue(15)
                self.scene.addItem(line)
                self.preview_items.append(line)
            target_item = QGraphicsEllipseItem(-radius, -radius, radius * 2, radius * 2)
            target_item.setBrush(preview_fill)
            target_item.setPen(QPen(QColor("#fff2a6"), 0.12 * self.scale_factor))
            target_item.setPos(self.field_to_scene(*target))
            target_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            target_item.setZValue(9)
            self.scene.addItem(target_item)
            self.preview_items.append(target_item)
        for kind, position in (handles or {}).items():
            handle = PreviewHandleItem(kind, self.scale_factor)
            handle.setPos(self.field_to_scene(*position))
            self.scene.addItem(handle)
            self.preview_items.append(handle)

    def show_shape_line_preview(
        self,
        path_points: list[tuple[float, float]],
        anchors: list[tuple[str, tuple[float, float]]],
        targets: dict[str, tuple[float, float]],
    ) -> None:
        self.clear_preview()
        if len(path_points) > 1:
            painter_path = self.make_painter_path(path_points)
            item = ShapeLineItem(painter_path, self.scale_factor)
            self.scene.addItem(item)
            self.preview_items.append(item)
        for dot_id, anchor in anchors:
            handle = PreviewHandleItem(f"shape_anchor:{dot_id}", self.scale_factor)
            handle.setBrush(QColor("#e53935"))
            handle.setPen(QPen(QColor("#ffffff"), 0.14 * self.scale_factor))
            handle.setPos(self.field_to_scene(*anchor))
            self.scene.addItem(handle)
            self.preview_items.append(handle)
        radius = 0.35 * self.scale_factor
        for target in targets.values():
            target_item = QGraphicsEllipseItem(-radius, -radius, radius * 2, radius * 2)
            target_item.setBrush(QColor(247, 209, 84, 130))
            target_item.setPen(QPen(QColor("#fff2a6"), 0.1 * self.scale_factor))
            target_item.setPos(self.field_to_scene(*target))
            target_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            target_item.setZValue(9)
            self.scene.addItem(target_item)
            self.preview_items.append(target_item)

    def clear_preview(self) -> None:
        for item in self.preview_items:
            self.scene.removeItem(item)
        self.preview_items.clear()

    def show_paths(
        self,
        paths: dict[str, list[tuple[float, float]]],
        anchors: dict[str, list[tuple[float, float]]],
    ) -> None:
        self.clear_paths()
        for dot_id, points in paths.items():
            if len(points) > 1:
                item = PathCurveItem(dot_id, self.make_painter_path(points), self.scale_factor)
                self.scene.addItem(item)
                self.path_items.append(item)
            for index, anchor in enumerate(anchors.get(dot_id, [])):
                anchor_item = PathAnchorItem(dot_id, index, self.scale_factor)
                anchor_item.setPos(self.field_to_scene(*anchor))
                self.scene.addItem(anchor_item)
                self.path_items.append(anchor_item)

    def clear_paths(self) -> None:
        for item in self.path_items:
            self.scene.removeItem(item)
        self.path_items.clear()

    def make_painter_path(self, points: list[tuple[float, float]]) -> QPainterPath:
        painter_path = QPainterPath(self.field_to_scene(*points[0]))
        for point in points[1:]:
            painter_path.lineTo(self.field_to_scene(*point))
        return painter_path

    def update_labels(self, enabled: bool) -> None:
        self.show_labels = enabled
        for item in self.dot_items.values():
            item.label.setVisible(enabled)

    def rebuild_dots(self) -> None:
        for item in self.dot_items.values():
            self.scene.removeItem(item)
        self.dot_items.clear()
        if not self.project:
            return
        for dot in self.project.dots:
            item = DotItem(dot, self.scale_factor)
            item.setPos(self.field_to_scene(dot.x, dot.y))
            item.label.setVisible(self.show_labels)
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self.active_tool == EditorTool.SELECT,
            )
            self.scene.addItem(item)
            self.dot_items[dot.id] = item

    def draw_field(self) -> None:
        self.scene.clear()
        self.dot_items.clear()
        width = 120 * self.scale_factor
        height = 53.333 * self.scale_factor
        field = QGraphicsRectItem(-width / 2, -height / 2, width, height)
        field.setBrush(QColor("#5aa052"))
        field.setPen(QPen(QColor("#e8f6e6"), 0.2 * self.scale_factor))
        field.setZValue(-20)
        self.scene.addItem(field)

        yard_pen = QPen(QColor("#e8f6e6"), 0.12 * self.scale_factor)
        hash_pen = QPen(QColor("#d9edd7"), 0.08 * self.scale_factor)
        for yard in range(-50, 55, 5):
            x = yard * self.scale_factor
            self.scene.addLine(x, -height / 2, x, height / 2, yard_pen)
            label_text = "50" if yard == 0 else str(50 - abs(yard))
            label = self.scene.addText(label_text)
            label.setDefaultTextColor(QColor("#f8fff5"))
            label.setScale(0.6)
            label.setPos(x - 7, -height / 2 + 8)

        for y in (-20, 0, 20):
            self.scene.addLine(-width / 2, y * self.scale_factor, width / 2, y * self.scale_factor, hash_pen)
        self.scene.setSceneRect(QRectF(-width / 2 - 80, -height / 2 - 80, width + 160, height + 160))

    def field_to_scene(self, x: float, y: float) -> QPointF:
        return QPointF(x * self.scale_factor, -y * self.scale_factor)

    def scene_to_field(self, point: QPointF) -> tuple[float, float]:
        return (point.x() / self.scale_factor, -point.y() / self.scale_factor)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        clicked_item = self.itemAt(event.position().toPoint())
        self._active_preview_handle = clicked_item if isinstance(clicked_item, PreviewHandleItem) else None
        self._active_path_anchor = clicked_item if isinstance(clicked_item, PathAnchorItem) else None
        if event.button() == Qt.MouseButton.RightButton:
            if isinstance(clicked_item, PathCurveItem):
                x, y = self.scene_to_field(self.mapToScene(event.position().toPoint()))
                self.path_anchor_added.emit(clicked_item.dot_id, x, y)
                self._suppress_next_context_menu = True
                event.accept()
                return
            if self.active_tool == EditorTool.SHAPE_LINE and isinstance(clicked_item, DotItem):
                self.shape_anchor_toggled.emit(clicked_item.dot_id)
                self._suppress_next_context_menu = True
                event.accept()
                return
            if self.active_tool != EditorTool.SELECT:
                self._suppress_next_context_menu = True
                event.accept()
                return
        if self.active_tool != EditorTool.SELECT and event.button() == Qt.MouseButton.LeftButton:
            if isinstance(clicked_item, (PreviewHandleItem, PathAnchorItem)):
                self.preserve_selection()
                self._manual_drag_item = clicked_item
                self.restore_preserved_selection()
                event.accept()
                return
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and isinstance(clicked_item, DotItem):
                clicked_item.setSelected(not clicked_item.isSelected())
                self.selection_changed.emit(self.selected_dot_ids())
                event.accept()
                return
            event.accept()
            return
        if (
            self.active_tool != EditorTool.SELECT
            and event.button() == Qt.MouseButton.LeftButton
            and not isinstance(clicked_item, PreviewHandleItem)
            and not isinstance(clicked_item, PathAnchorItem)
            and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and isinstance(
            clicked_item, (PreviewHandleItem, PathAnchorItem)
        ):
            self.preserve_selection()
            self._manual_drag_item = clicked_item
            self.restore_preserved_selection()
            event.accept()
            return

        self._drag_start_positions = {}
        if event.button() == Qt.MouseButton.LeftButton:
            for item in self.scene.selectedItems():
                if isinstance(item, DotItem):
                    self._drag_start_positions[item.dot_id] = self.scene_to_field(item.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._manual_drag_item is not None:
            self._manual_drag_item.setPos(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        if self._pan_start is not None:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = None
            self.unsetCursor()
            return
        if event.button() == Qt.MouseButton.RightButton:
            event.accept()
            return
        if self._active_preview_handle is not None:
            handle = self._active_preview_handle
            x, y = self.scene_to_field(handle.pos())
            self.preview_handle_moved.emit(handle.kind, x, y)
            self._active_preview_handle = None
            self._manual_drag_item = None
            self.restore_preserved_selection()
            event.accept()
            return
        if self._active_path_anchor is not None:
            handle = self._active_path_anchor
            x, y = self.scene_to_field(handle.pos())
            self.path_anchor_moved.emit(handle.dot_id, handle.index, x, y)
            self._active_path_anchor = None
            self._manual_drag_item = None
            self.restore_preserved_selection()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.active_tool != EditorTool.SELECT:
            self._drag_start_positions = {}
            self.selection_changed.emit(self.selected_dot_ids())
            return
        moved_positions: dict[str, tuple[float, float]] = {}
        for item in self.scene.selectedItems():
            if isinstance(item, DotItem):
                x, y = self.scene_to_field(item.pos())
                start = self._drag_start_positions.get(item.dot_id)
                if start is None or abs(start[0] - x) > 0.001 or abs(start[1] - y) > 0.001:
                    moved_positions[item.dot_id] = (x, y)
        if len(moved_positions) > 1:
            self.dots_moved.emit(moved_positions)
        elif len(moved_positions) == 1:
            dot_id, position = next(iter(moved_positions.items()))
            self.dot_moved.emit(dot_id, position[0], position[1])
        self._drag_start_positions = {}
        self.selection_changed.emit(self.selected_dot_ids())

    def contextMenuEvent(self, event) -> None:  # type: ignore[override]
        if self._suppress_next_context_menu:
            self._suppress_next_context_menu = False
            event.accept()
            return
        clicked_item = self.itemAt(event.pos())
        if isinstance(clicked_item, PathCurveItem):
            x, y = self.scene_to_field(self.mapToScene(event.pos()))
            self.path_anchor_added.emit(clicked_item.dot_id, x, y)
            return
        if self.active_tool == EditorTool.SHAPE_LINE and isinstance(clicked_item, DotItem):
            self.shape_anchor_toggled.emit(clicked_item.dot_id)
            return
        if self.active_tool != EditorTool.SELECT:
            return
        menu = QMenu(self)
        actions: list[tuple[str, QAction]] = []
        for name in (
            "Preview Line",
            "Preview Curve",
            "Preview Arc",
            "Preview Scatter",
            "Preview Mirror",
            "Preview Shape Line",
        ):
            action = menu.addAction(name)
            actions.append((name, action))
        selected = menu.exec(event.globalPos())
        if selected:
            for name, action in actions:
                if action == selected:
                    self.context_action.emit(name)
                    break
