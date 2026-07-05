from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QMenu,
)

from drill_writer.core.models import Dot, DrillProject, Prop, prop_default_state


class EditorTool(str, Enum):
    SELECT = "select"
    LINE = "line"
    CURVE = "curve"
    ARC = "arc"
    SCATTER = "scatter"
    MIRROR = "mirror"
    SHAPE_LINE = "shape_line"
    CIRCLE = "circle"
    RECTANGLE = "rectangle"
    SPIRAL = "spiral"
    BLOCK = "block"
    SCALE = "scale"
    LASSO = "lasso"
    SVG_SHAPE = "svg_shape"
    PLUGIN_FORM = "plugin_form"


class DotItem(QGraphicsEllipseItem):
    def __init__(self, dot: Dot, scale: float) -> None:
        radius = 0.34 * scale
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.dot_id = dot.id
        self.setBrush(QColor(dot.color))
        self.setPen(QPen(QColor("#1d2128"), 0.08 * scale))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setZValue(10)
        self.label = QGraphicsTextItem(dot.name, self)
        self.label.setFont(QFont("Arial", 8))
        self.label.setDefaultTextColor(QColor("#1c2430"))
        self.label.setScale(0.085 * scale)
        self.label.setPos(radius + 0.08 * scale, -radius - 0.04 * scale)


class PropItem(QGraphicsPixmapItem):
    def __init__(self, prop: Prop, pixmap: QPixmap, scale: float) -> None:
        super().__init__(pixmap)
        self.prop_id = prop.id
        self.scale_factor = scale
        self.source_size = pixmap.size()
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        self.setOffset(-pixmap.width() / 2, -pixmap.height() / 2)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setZValue(7)
        self.apply_state(prop_default_state(prop))

    def apply_state(self, state: dict[str, float]) -> None:
        if self.source_size.width() <= 0 or self.source_size.height() <= 0:
            return
        width_scene = max(0.1, float(state.get("width", 8.0))) * self.scale_factor
        height_scene = max(0.1, float(state.get("height", 4.0))) * self.scale_factor
        transform = QTransform()
        transform.scale(width_scene / self.source_size.width(), height_scene / self.source_size.height())
        self.setTransform(transform)
        self.setRotation(float(state.get("rotation", 0.0)))

    def current_state(self, scene_to_field) -> dict[str, float]:
        x, y = scene_to_field(self.pos())
        width = self.boundingRect().width() * self.transform().m11() / self.scale_factor
        height = self.boundingRect().height() * self.transform().m22() / self.scale_factor
        return {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "rotation": self.rotation(),
        }


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


class PathTangentItem(QGraphicsEllipseItem):
    def __init__(self, dot_id: str, index: int, control_name: str, scale: float) -> None:
        radius = 0.42 * scale
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.dot_id = dot_id
        self.index = index
        self.control_name = control_name
        self.setBrush(QColor("#66d9ef"))
        self.setPen(QPen(QColor("#ffffff"), 0.1 * scale))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setZValue(27)


class FieldView(QGraphicsView):
    selection_changed = Signal(list)
    dot_moved = Signal(str, float, float)
    dots_moved = Signal(dict)
    prop_moved = Signal(str, dict)
    props_moved = Signal(dict)
    context_action = Signal(str)
    preview_handle_moved = Signal(str, float, float)
    path_anchor_added = Signal(str, float, float)
    path_anchor_moved = Signal(str, int, float, float)
    path_tangent_moved = Signal(str, int, str, float, float)
    shape_anchor_added = Signal(float, float)
    shape_anchor_toggled = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setObjectName("FieldView")
        self.setBackgroundBrush(QColor("#111318"))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.scale_factor = 10.0
        self.project: DrillProject | None = None
        self.project_dir: Path | None = None
        self.dot_items: dict[str, DotItem] = {}
        self.prop_items: dict[str, PropItem] = {}
        self.active_tool = EditorTool.SELECT
        self.show_labels = True
        self.show_ghosts = True
        self.preview_items: list[QGraphicsItem] = []
        self.path_items: list[QGraphicsItem] = []
        self.snap_items: list[QGraphicsItem] = []
        self.snap_enabled = False
        self.snap_threshold = 0.85
        self.visible_section = "All"
        self.visible_layer = "All"
        self._formation_callback: Callable[[EditorTool], None] | None = None
        self._pan_start: QPointF | None = None
        self._drag_start_positions: dict[str, tuple[float, float]] = {}
        self._drag_start_prop_states: dict[str, dict[str, float]] = {}
        self._active_preview_handle: PreviewHandleItem | None = None
        self._active_path_anchor: PathAnchorItem | None = None
        self._active_path_tangent: PathTangentItem | None = None
        self._preserved_selection_ids: list[str] = []
        self._suppress_next_context_menu = False
        self._manual_drag_item: PreviewHandleItem | PathAnchorItem | PathTangentItem | None = None
        self._lasso_points: list[QPointF] = []
        self._lasso_item: QGraphicsPathItem | None = None
        self._lasso_additive = False
        self.draw_field()

    def set_canvas_theme(self, mode: str) -> None:
        self.setBackgroundBrush(QColor("#eef2f7" if mode == "light" else "#111318"))

    def set_project(self, project: DrillProject, project_dir: Path | None = None) -> None:
        self.project = project
        self.project_dir = project_dir
        self.rebuild_props()
        self.rebuild_dots()

    def set_tool(self, tool: EditorTool) -> None:
        self.active_tool = tool
        self.clear_snap_guides()
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag
            if tool == EditorTool.SELECT
            else QGraphicsView.DragMode.NoDrag
        )
        for item in self.dot_items.values():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, tool == EditorTool.SELECT)
        for item in self.prop_items.values():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, tool == EditorTool.SELECT)

    def set_snap_enabled(self, enabled: bool) -> None:
        self.snap_enabled = enabled
        if not enabled:
            self.clear_snap_guides()

    def set_visibility_filters(self, section: str, layer: str) -> None:
        self.visible_section = section
        self.visible_layer = layer
        self.apply_visibility_filters()

    def apply_visibility_filters(self) -> None:
        if not self.project:
            return
        for dot_id, item in self.dot_items.items():
            dot = self.project.dot_by_id(dot_id)
            if not dot:
                item.setVisible(False)
                continue
            section_visible = self.visible_section == "All" or dot.section == self.visible_section
            layer_visible = self.visible_layer == "All" or dot.layer == self.visible_layer
            item.setVisible(section_visible and layer_visible)
        for prop_id, item in self.prop_items.items():
            prop = self.project.prop_by_id(prop_id)
            if not prop:
                item.setVisible(False)
                continue
            section_visible = self.visible_section == "All"
            layer_visible = self.visible_layer == "All" or prop.layer == self.visible_layer
            item.setVisible(section_visible and layer_visible)

    def set_formation_callback(self, callback: Callable[[EditorTool], None]) -> None:
        self._formation_callback = callback

    def selected_dot_ids(self) -> list[str]:
        return [
            item.dot_id
            for item in self.scene.selectedItems()
            if isinstance(item, DotItem)
        ]

    def selected_prop_ids(self) -> list[str]:
        return [
            item.prop_id
            for item in self.scene.selectedItems()
            if isinstance(item, PropItem)
        ]

    def normalized_item(self, item: QGraphicsItem | None) -> QGraphicsItem | None:
        if isinstance(item, QGraphicsTextItem) and isinstance(item.parentItem(), DotItem):
            return item.parentItem()
        return item

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

    def set_prop_states(self, states: dict[str, dict[str, float]]) -> None:
        for prop_id, state in states.items():
            item = self.prop_items.get(prop_id)
            if item:
                item.apply_state(state)
                item.setPos(self.field_to_scene(float(state.get("x", 0)), float(state.get("y", 0))))

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
        controls: dict[str, list[dict[str, tuple[float, float]]]] | None = None,
    ) -> None:
        self.clear_paths()
        controls = controls or {}
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
                control_set = controls.get(dot_id, [])
                if index < len(control_set):
                    for control_name in ("in", "out"):
                        control_point = control_set[index].get(control_name)
                        if not control_point:
                            continue
                        line = QGraphicsLineItem()
                        anchor_scene = self.field_to_scene(*anchor)
                        control_scene = self.field_to_scene(*control_point)
                        line.setLine(anchor_scene.x(), anchor_scene.y(), control_scene.x(), control_scene.y())
                        line.setPen(QPen(QColor("#66d9ef"), 0.1 * self.scale_factor, Qt.PenStyle.DotLine))
                        line.setZValue(6)
                        line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                        self.scene.addItem(line)
                        self.path_items.append(line)

                        tangent_item = PathTangentItem(dot_id, index, control_name, self.scale_factor)
                        tangent_item.setPos(control_scene)
                        self.scene.addItem(tangent_item)
                        self.path_items.append(tangent_item)

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
        self.apply_visibility_filters()

    def rebuild_props(self) -> None:
        for item in self.prop_items.values():
            self.scene.removeItem(item)
        self.prop_items.clear()
        if not self.project:
            return
        for prop in self.project.props:
            pixmap = self.load_prop_pixmap(prop)
            item = PropItem(prop, pixmap, self.scale_factor)
            item.setPos(self.field_to_scene(prop.x, prop.y))
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self.active_tool == EditorTool.SELECT,
            )
            self.scene.addItem(item)
            self.prop_items[prop.id] = item
        self.apply_visibility_filters()

    def load_prop_pixmap(self, prop: Prop) -> QPixmap:
        path = Path(prop.image_file)
        if not path.is_absolute() and self.project_dir is not None:
            path = self.project_dir / prop.image_file
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            return pixmap
        fallback = QPixmap(160, 80)
        fallback.fill(QColor("#d7dde7"))
        return fallback

    def draw_field(self) -> None:
        self.scene.clear()
        self.dot_items.clear()
        self.prop_items.clear()
        width = 120 * self.scale_factor
        height = 53.333 * self.scale_factor
        field = QGraphicsRectItem(-width / 2, -height / 2, width, height)
        field.setBrush(QColor("#f9fbf7"))
        field.setPen(QPen(QColor("#88939a"), 0.16 * self.scale_factor))
        field.setZValue(-20)
        self.scene.addItem(field)

        micro_pen = QPen(QColor("#e3e9e8"), 0.018 * self.scale_factor)
        minor_pen = QPen(QColor("#d3dcda"), 0.035 * self.scale_factor)
        yard_pen = QPen(QColor("#5d686f"), 0.09 * self.scale_factor)
        hash_pen = QPen(QColor("#101318"), 0.16 * self.scale_factor)

        for yard in range(-60, 61):
            x = yard * self.scale_factor
            if yard % 5 == 0:
                continue
            self.scene.addLine(x, -height / 2, x, height / 2, minor_pen if yard % 2 == 0 else micro_pen)
        horizontal_index = 0
        y = -26.0
        while y <= 26.1:
            y_scene = y * self.scale_factor
            if abs(y) not in (20.0,):
                self.scene.addLine(-width / 2, y_scene, width / 2, y_scene, minor_pen if horizontal_index % 2 == 0 else micro_pen)
            y += 1.0
            horizontal_index += 1

        for yard in range(-50, 55, 5):
            x = yard * self.scale_factor
            self.scene.addLine(x, -height / 2, x, height / 2, yard_pen)
            label_text = "50" if yard == 0 else str(50 - abs(yard))
            for y_pos, rotation in ((-height / 2 + 4, 0), (height / 2 - 28, 180)):
                label = self.scene.addText(label_text, QFont("Arial", 8, QFont.Weight.DemiBold))
                label.setDefaultTextColor(QColor("#7d858a"))
                label.setScale(0.75)
                label.setRotation(rotation)
                label.setPos(x - 8, y_pos)

        for boundary_y in (-height / 2, height / 2):
            self.scene.addLine(-width / 2, boundary_y, width / 2, boundary_y, QPen(QColor("#5f6b72"), 0.11 * self.scale_factor))

        for hash_y in (-20, 20):
            y_scene = -hash_y * self.scale_factor
            for yard in range(-50, 55, 5):
                x = yard * self.scale_factor
                self.scene.addLine(x - 0.7 * self.scale_factor, y_scene, x + 0.7 * self.scale_factor, y_scene, hash_pen)
        midfield_pen = QPen(QColor("#b5bec2"), 0.05 * self.scale_factor, Qt.PenStyle.DashLine)
        self.scene.addLine(-width / 2, 0, width / 2, 0, midfield_pen)
        self.scene.setSceneRect(QRectF(-width / 2 - 65, -height / 2 - 48, width + 130, height + 96))

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
        if self.active_tool == EditorTool.LASSO and event.button() == Qt.MouseButton.LeftButton:
            self.start_lasso(event)
            return
        clicked_item = self.normalized_item(self.itemAt(event.position().toPoint()))
        self._active_preview_handle = clicked_item if isinstance(clicked_item, PreviewHandleItem) else None
        self._active_path_anchor = clicked_item if isinstance(clicked_item, PathAnchorItem) else None
        self._active_path_tangent = clicked_item if isinstance(clicked_item, PathTangentItem) else None
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
            if isinstance(clicked_item, (PreviewHandleItem, PathAnchorItem, PathTangentItem)):
                self.preserve_selection()
                self._manual_drag_item = clicked_item
                self.restore_preserved_selection()
                event.accept()
                return
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and isinstance(clicked_item, (DotItem, PropItem)):
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
            and not isinstance(clicked_item, PathTangentItem)
            and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and isinstance(
            clicked_item, (PreviewHandleItem, PathAnchorItem, PathTangentItem)
        ):
            self.preserve_selection()
            self._manual_drag_item = clicked_item
            self.restore_preserved_selection()
            event.accept()
            return

        self._drag_start_positions = {}
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.active_tool == EditorTool.SELECT
            and isinstance(clicked_item, (DotItem, PropItem))
            and not clicked_item.isSelected()
            and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            for item in self.scene.selectedItems():
                item.setSelected(False)
            clicked_item.setSelected(True)
        if event.button() == Qt.MouseButton.LeftButton:
            for item in self.scene.selectedItems():
                if isinstance(item, DotItem):
                    self._drag_start_positions[item.dot_id] = self.scene_to_field(item.pos())
                elif isinstance(item, PropItem):
                    self._drag_start_prop_states[item.prop_id] = item.current_state(self.scene_to_field)
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self.active_tool == EditorTool.SELECT:
            for item in self.scene.selectedItems():
                if isinstance(item, DotItem):
                    self._drag_start_positions.setdefault(item.dot_id, self.scene_to_field(item.pos()))
                elif isinstance(item, PropItem):
                    self._drag_start_prop_states.setdefault(
                        item.prop_id,
                        item.current_state(self.scene_to_field),
                    )

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._manual_drag_item is not None:
            self._manual_drag_item.setPos(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        if self._lasso_item is not None and self.active_tool == EditorTool.LASSO:
            self.update_lasso(event)
            return
        if self._pan_start is not None:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            return
        super().mouseMoveEvent(event)
        if (
            self.active_tool == EditorTool.SELECT
            and self.snap_enabled
            and self._drag_start_positions
        ):
            self.apply_snap_to_selected()

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
        if self._active_path_tangent is not None:
            handle = self._active_path_tangent
            x, y = self.scene_to_field(handle.pos())
            self.path_tangent_moved.emit(handle.dot_id, handle.index, handle.control_name, x, y)
            self._active_path_tangent = None
            self._manual_drag_item = None
            self.restore_preserved_selection()
            event.accept()
            return
        if self._lasso_item is not None and self.active_tool == EditorTool.LASSO:
            self.finish_lasso()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.active_tool != EditorTool.SELECT:
            self._drag_start_positions = {}
            self._drag_start_prop_states = {}
            self.selection_changed.emit(self.selected_dot_ids())
            self.clear_snap_guides()
            return
        if self.snap_enabled and self._drag_start_positions:
            self.apply_snap_to_selected()
        moved_positions: dict[str, tuple[float, float]] = {}
        for item in self.scene.selectedItems():
            if isinstance(item, DotItem):
                x, y = self.scene_to_field(item.pos())
                start = self._drag_start_positions.get(item.dot_id)
                if start is None or abs(start[0] - x) > 0.001 or abs(start[1] - y) > 0.001:
                    moved_positions[item.dot_id] = (x, y)
        moved_props: dict[str, dict[str, float]] = {}
        for item in self.scene.selectedItems():
            if isinstance(item, PropItem):
                state = item.current_state(self.scene_to_field)
                start = self._drag_start_prop_states.get(item.prop_id)
                if start is None or any(abs(start.get(key, 0) - state.get(key, 0)) > 0.001 for key in state):
                    moved_props[item.prop_id] = state
        if len(moved_positions) > 1:
            self.dots_moved.emit(moved_positions)
        elif len(moved_positions) == 1:
            dot_id, position = next(iter(moved_positions.items()))
            self.dot_moved.emit(dot_id, position[0], position[1])
        if len(moved_props) > 1:
            self.props_moved.emit(moved_props)
        elif len(moved_props) == 1:
            prop_id, state = next(iter(moved_props.items()))
            self.prop_moved.emit(prop_id, state)
        self._drag_start_positions = {}
        self._drag_start_prop_states = {}
        self.clear_snap_guides()
        self.selection_changed.emit(self.selected_dot_ids())

    def start_lasso(self, event) -> None:
        self._lasso_points = [self.mapToScene(event.position().toPoint())]
        self._lasso_additive = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self._lasso_item = QGraphicsPathItem()
        self._lasso_item.setPen(QPen(QColor("#b057ff"), 0.16 * self.scale_factor, Qt.PenStyle.DashLine))
        self._lasso_item.setBrush(QColor(176, 87, 255, 35))
        self._lasso_item.setZValue(40)
        self.scene.addItem(self._lasso_item)
        event.accept()

    def update_lasso(self, event) -> None:
        if self._lasso_item is None:
            return
        self._lasso_points.append(self.mapToScene(event.position().toPoint()))
        path = QPainterPath(self._lasso_points[0])
        for point in self._lasso_points[1:]:
            path.lineTo(point)
        self._lasso_item.setPath(path)
        event.accept()

    def finish_lasso(self) -> None:
        if self._lasso_item is None or len(self._lasso_points) < 3:
            self.clear_lasso()
            return
        path = QPainterPath(self._lasso_points[0])
        for point in self._lasso_points[1:]:
            path.lineTo(point)
        path.closeSubpath()
        if not self._lasso_additive:
            for item in self.scene.selectedItems():
                item.setSelected(False)
        for item in self.dot_items.values():
            if item.isVisible() and path.contains(item.pos()):
                item.setSelected(True)
        self.clear_lasso()
        self.selection_changed.emit(self.selected_dot_ids())

    def clear_lasso(self) -> None:
        if self._lasso_item is not None:
            self.scene.removeItem(self._lasso_item)
            self._lasso_item = None
        self._lasso_points.clear()

    def apply_snap_to_selected(self) -> None:
        selected_items = [
            item for item in self.scene.selectedItems()
            if isinstance(item, DotItem) and item.isVisible()
        ]
        if not selected_items:
            self.clear_snap_guides()
            return

        selected_ids = {item.dot_id for item in selected_items}
        candidate_x = [yard for yard in range(-50, 55, 5)]
        candidate_y = [-20.0, 0.0, 20.0]
        for dot_id, item in self.dot_items.items():
            if dot_id in selected_ids or not item.isVisible():
                continue
            x, y = self.scene_to_field(item.pos())
            candidate_x.append(x)
            candidate_y.append(y)

        best_x: tuple[float, float] | None = None
        best_y: tuple[float, float] | None = None
        for item in selected_items:
            x, y = self.scene_to_field(item.pos())
            for candidate in candidate_x:
                delta = candidate - x
                if abs(delta) < 0.001:
                    continue
                if abs(delta) <= self.snap_threshold and (
                    best_x is None or abs(delta) < abs(best_x[0])
                ):
                    best_x = (delta, candidate)
            for candidate in candidate_y:
                delta = candidate - y
                if abs(delta) < 0.001:
                    continue
                if abs(delta) <= self.snap_threshold and (
                    best_y is None or abs(delta) < abs(best_y[0])
                ):
                    best_y = (delta, candidate)

        if best_x is None and best_y is None:
            self.clear_snap_guides()
            return

        if best_y is not None and (best_x is None or abs(best_y[0]) < abs(best_x[0])):
            delta = best_y[0]
            for item in selected_items:
                x, y = self.scene_to_field(item.pos())
                item.setPos(self.field_to_scene(x, y + delta))
            self.show_snap_guide("horizontal", best_y[1])
            return

        if best_x is not None:
            delta = best_x[0]
            for item in selected_items:
                x, y = self.scene_to_field(item.pos())
                item.setPos(self.field_to_scene(x + delta, y))
            self.show_snap_guide("vertical", best_x[1])

    def show_snap_guide(self, orientation: str, value: float) -> None:
        self.clear_snap_guides()
        width = 120 * self.scale_factor
        height = 53.333 * self.scale_factor
        pen = QPen(QColor("#b057ff"), 0.12 * self.scale_factor, Qt.PenStyle.DashLine)
        if orientation == "vertical":
            x = value * self.scale_factor
            guide = QGraphicsLineItem(x, -height / 2, x, height / 2)
        else:
            y = -value * self.scale_factor
            guide = QGraphicsLineItem(-width / 2, y, width / 2, y)
        guide.setPen(pen)
        guide.setZValue(30)
        self.scene.addItem(guide)
        self.snap_items.append(guide)

    def clear_snap_guides(self) -> None:
        for item in self.snap_items:
            self.scene.removeItem(item)
        self.snap_items.clear()

    def contextMenuEvent(self, event) -> None:  # type: ignore[override]
        if self._suppress_next_context_menu:
            self._suppress_next_context_menu = False
            event.accept()
            return
        clicked_item = self.normalized_item(self.itemAt(event.pos()))
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
            "Preview Circle",
            "Preview Rectangle",
            "Preview Spiral",
            "Preview Block",
            "Preview Scale Form",
            "Preview SVG Shape",
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
