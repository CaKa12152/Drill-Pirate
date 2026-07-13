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
    QStyle,
)

from drill_writer.core.coordinates import (
    BACK_HASH_YARDS,
    FIELD_HALF_HEIGHT_YARDS,
    FIELD_HALF_WIDTH_YARDS,
    FRONT_HASH_YARDS,
)
from drill_writer.core.models import Dot, DrillProject, Prop, prop_default_state
from drill_writer.ui.appearance import draw_dot_symbol, generated_prop_pixmap, normalize_dot_symbol, preferred_dot_symbol
from drill_writer.ui.theme import normalize_field_mode


class EditorTool(str, Enum):
    SELECT = "select"
    LINE = "line"
    CURVE = "curve"
    FREE_CURVE = "free_curve"
    ARC = "arc"
    SCATTER = "scatter"
    MIRROR = "mirror"
    SHAPE_LINE = "shape_line"
    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    RECTANGLE = "rectangle"
    TRIANGLE = "triangle"
    DIAMOND = "diamond"
    POLYGON = "polygon"
    STAR = "star"
    SPIRAL = "spiral"
    BLOCK = "block"
    SCALE = "scale"
    WARP = "warp"
    ROTATE = "rotate"
    LASSO = "lasso"
    SVG_SHAPE = "svg_shape"
    PLUGIN_FORM = "plugin_form"


class DotItem(QGraphicsEllipseItem):
    def __init__(self, dot: Dot, scale: float, symbol: str) -> None:
        radius = 0.34 * scale
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.dot_id = dot.id
        self.symbol = normalize_dot_symbol(symbol)
        self.facing_degrees = 0.0
        self.scale_factor = scale
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

    def set_symbol(self, symbol: str) -> None:
        self.symbol = normalize_dot_symbol(symbol)
        self.update()

    def set_facing_degrees(self, facing_degrees: float) -> None:
        self.facing_degrees = float(facing_degrees) % 360.0
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        draw_dot_symbol(
            painter,
            self.rect().center(),
            self.rect().width() / 2,
            self.brush().color(),
            self.symbol,
            rotation_degrees=self.facing_degrees,
            outline_color=self.pen().color(),
            outline_width=max(0.7, self.pen().widthF()),
            selected=selected,
        )


class DotSymbolPreviewItem(QGraphicsEllipseItem):
    def __init__(
        self,
        radius: float,
        color: QColor,
        symbol: str,
        outline_color: QColor,
        outline_width: float,
    ) -> None:
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.symbol = normalize_dot_symbol(symbol)
        self.preview_color = color
        self.outline_color = outline_color
        self.outline_width = outline_width
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(9)

    def paint(self, painter: QPainter, _option, _widget=None) -> None:  # type: ignore[override]
        draw_dot_symbol(
            painter,
            self.rect().center(),
            self.rect().width() / 2,
            self.preview_color,
            self.symbol,
            outline_color=self.outline_color,
            outline_width=self.outline_width,
        )


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
    dot_edit_requested = Signal(str)
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
        self.locked_sections: set[str] = set()
        self.locked_layers: set[str] = set()
        self.dot_symbol = preferred_dot_symbol()
        self.field_mode = "white"
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

    def set_field_mode(self, mode: str) -> None:
        normalized = normalize_field_mode(mode)
        if normalized == self.field_mode and self.scene.items():
            return
        selected_dot_ids = self.selected_dot_ids()
        selected_prop_ids = self.selected_prop_ids()
        current_positions = {
            dot_id: self.scene_to_field(item.pos())
            for dot_id, item in self.dot_items.items()
        }
        current_prop_states = {
            prop_id: item.current_state(self.scene_to_field)
            for prop_id, item in self.prop_items.items()
        }
        self.field_mode = normalized
        self.draw_field()
        if self.project is not None:
            self.rebuild_props()
            self.rebuild_dots()
            if current_positions:
                self.set_positions(current_positions)
            if current_prop_states:
                self.set_prop_states(current_prop_states)
            for dot_id in selected_dot_ids:
                item = self.dot_items.get(dot_id)
                if item:
                    item.setSelected(True)
            for prop_id in selected_prop_ids:
                item = self.prop_items.get(prop_id)
                if item:
                    item.setSelected(True)
        self.selection_changed.emit(self.selected_dot_ids())

    def field_palette(self) -> dict[str, str]:
        if self.field_mode == "inverted":
            return {
                "field_fill": "#050607",
                "endzone_fill": "#101216",
                "field_border": "#ffffff",
                "perimeter": "#cfd6df",
                "micro": "#2c3138",
                "minor": "#444b55",
                "yard": "#e7edf4",
                "heavy": "#ffffff",
                "hash": "#ffffff",
                "tick": "#eef3f8",
                "restraining": "#cfd6df",
                "center": "#606a75",
                "label": "#f7f9fc",
                "label_muted": "#d8e0ea",
                "label_heavy": "#ffffff",
                "bench": "#eef3f8",
            }
        if self.field_mode == "grass":
            return {
                "field_fill": "#2f7d3b",
                "endzone_fill": "#276b33",
                "field_border": "#f4fff4",
                "perimeter": "#d4ead3",
                "micro": "#479455",
                "minor": "#66a96e",
                "yard": "#f1fff0",
                "heavy": "#ffffff",
                "hash": "#ffffff",
                "tick": "#ffffff",
                "restraining": "#e4f4e3",
                "center": "#93c795",
                "label": "#ffffff",
                "label_muted": "#ecf8eb",
                "label_heavy": "#ffffff",
                "bench": "#f1fff0",
            }
        return {
            "field_fill": "#f9fbf7",
            "endzone_fill": "#edf3ef",
            "field_border": "#89939a",
            "perimeter": "#747e85",
            "micro": "#e2e9e7",
            "minor": "#d3dcda",
            "yard": "#66717a",
            "heavy": "#28313a",
            "hash": "#20262d",
            "tick": "#313a42",
            "restraining": "#929aa0",
            "center": "#bbc4c8",
            "label": "#3f464c",
            "label_muted": "#333a40",
            "label_heavy": "#05070a",
            "bench": "#565f66",
        }

    def set_dot_symbol(self, symbol: str) -> None:
        normalized = normalize_dot_symbol(symbol)
        if normalized == self.dot_symbol:
            return
        selected_ids = self.selected_dot_ids()
        current_positions = {
            dot_id: self.scene_to_field(item.pos())
            for dot_id, item in self.dot_items.items()
        }
        current_facings = {
            dot_id: item.facing_degrees
            for dot_id, item in self.dot_items.items()
        }
        self.dot_symbol = normalized
        self.rebuild_dots()
        if current_positions:
            self.set_positions(current_positions)
        if current_facings:
            self.set_facings(current_facings)
        for dot_id in selected_ids:
            item = self.dot_items.get(dot_id)
            if item:
                item.setSelected(True)
        self.selection_changed.emit(self.selected_dot_ids())

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
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                tool == EditorTool.SELECT and not self.dot_locked(item.dot_id),
            )
        for item in self.prop_items.values():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, tool == EditorTool.SELECT)

    def set_snap_enabled(self, enabled: bool) -> None:
        self.snap_enabled = enabled
        if not enabled:
            self.clear_snap_guides()

    def set_locked_filters(self, sections: set[str], layers: set[str]) -> None:
        self.locked_sections = set(sections)
        self.locked_layers = set(layers)
        for item in self.dot_items.values():
            locked = self.dot_locked(item.dot_id)
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self.active_tool == EditorTool.SELECT and not locked,
            )
            item.setOpacity(0.45 if locked else 1.0)

    def dot_locked(self, dot_id: str) -> bool:
        if not self.project:
            return False
        dot = self.project.dot_by_id(dot_id)
        if not dot:
            return False
        return bool(dot.section and dot.section in self.locked_sections) or bool(
            dot.layer and dot.layer in self.locked_layers
        )

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

    def set_facings(self, facings: dict[str, float]) -> None:
        for dot_id, facing in facings.items():
            item = self.dot_items.get(dot_id)
            if item:
                item.set_facing_degrees(facing)

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
            target_item = DotSymbolPreviewItem(
                radius,
                preview_fill,
                self.dot_symbol,
                QColor("#fff2a6"),
                0.12 * self.scale_factor,
            )
            target_item.setPos(self.field_to_scene(*target))
            self.scene.addItem(target_item)
            self.preview_items.append(target_item)
        for kind, position in (handles or {}).items():
            handle = PreviewHandleItem(kind, self.scale_factor)
            self.style_preview_handle(handle)
            handle.setPos(self.field_to_scene(*position))
            self.scene.addItem(handle)
            self.add_preview_handle_label(handle, self.preview_handle_label(kind))
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
            self.add_preview_handle_label(handle, "anchor")
            self.preview_items.append(handle)
        radius = 0.35 * self.scale_factor
        for target in targets.values():
            target_item = DotSymbolPreviewItem(
                radius,
                QColor(247, 209, 84, 130),
                self.dot_symbol,
                QColor("#fff2a6"),
                0.1 * self.scale_factor,
            )
            target_item.setPos(self.field_to_scene(*target))
            self.scene.addItem(target_item)
            self.preview_items.append(target_item)

    def show_curve_path_preview(
        self,
        path_points: list[tuple[float, float]],
        starts: dict[str, tuple[float, float]],
        targets: dict[str, tuple[float, float]],
        handles: dict[str, tuple[float, float]],
    ) -> None:
        self.clear_preview()
        if len(path_points) > 1:
            painter_path = self.make_painter_path(path_points)
            item = ShapeLineItem(painter_path, self.scale_factor)
            self.scene.addItem(item)
            self.preview_items.append(item)
        preview_pen = QPen(QColor("#f7d154"), 0.12 * self.scale_factor, Qt.PenStyle.DashLine)
        radius = 0.35 * self.scale_factor
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
            target_item = DotSymbolPreviewItem(
                radius,
                QColor(247, 209, 84, 135),
                self.dot_symbol,
                QColor("#fff2a6"),
                0.1 * self.scale_factor,
            )
            target_item.setPos(self.field_to_scene(*target))
            self.scene.addItem(target_item)
            self.preview_items.append(target_item)
        for kind, position in handles.items():
            handle = PreviewHandleItem(kind, self.scale_factor)
            self.style_preview_handle(handle)
            handle.setPos(self.field_to_scene(*position))
            self.scene.addItem(handle)
            self.add_preview_handle_label(handle, self.preview_handle_label(kind))
            self.preview_items.append(handle)

    def clear_preview(self) -> None:
        for item in self.preview_items:
            self.scene.removeItem(item)
        self.preview_items.clear()

    def preview_handle_label(self, kind: str) -> str:
        labels = {
            "form_center": "move form",
            "line_start": "start",
            "line_end": "end",
            "curve_bend": "bend",
            "curve_start": "start",
            "curve_control_1": "curve",
            "curve_control_2": "curve",
            "curve_end": "end",
            "arc_radius": "radius",
            "arc_width": "width",
            "arc_height": "height",
            "arc_start": "start",
            "arc_end": "end",
            "arc_sweep": "sweep",
            "shape_radius": "radius",
            "shape_width": "width",
            "shape_height": "height",
            "block_spacing": "spacing",
            "scale_width": "width",
            "scale_height": "height",
            "rotate_angle": "rotate",
            "scatter_radius": "spread",
            "mirror_axis": "axis",
        }
        if kind.startswith("plugin_setting:"):
            return kind.split(":", 1)[1].replace("_", " ")
        if kind.startswith("shape_anchor:"):
            return "anchor"
        if kind.startswith("free_curve_anchor:"):
            return "curve"
        if kind.startswith("warp_anchor:"):
            return "bend"
        return labels.get(kind, kind.replace("_", " "))

    def style_preview_handle(self, handle: PreviewHandleItem) -> None:
        kind = handle.kind
        if kind == "form_center":
            handle.setBrush(QColor("#b057ff"))
            handle.setPen(QPen(QColor("#ffffff"), 0.16 * self.scale_factor))
        elif "width" in kind or "height" in kind or "radius" in kind or "spacing" in kind:
            handle.setBrush(QColor("#f7d154"))
            handle.setPen(QPen(QColor("#20242b"), 0.14 * self.scale_factor))
        elif kind in {
            "line_start",
            "line_end",
            "curve_bend",
            "curve_start",
            "curve_control_1",
            "curve_control_2",
            "curve_end",
            "arc_sweep",
            "arc_start",
            "arc_end",
            "rotate_angle",
        }:
            handle.setBrush(QColor("#66d9ef"))
            handle.setPen(QPen(QColor("#0b1d24"), 0.14 * self.scale_factor))
        elif kind.startswith("warp_anchor:"):
            handle.setBrush(QColor("#b057ff"))
            handle.setPen(QPen(QColor("#ffffff"), 0.14 * self.scale_factor))
        elif kind.startswith("free_curve_anchor:"):
            handle.setBrush(QColor("#e53935"))
            handle.setPen(QPen(QColor("#ffffff"), 0.14 * self.scale_factor))

    def add_preview_handle_label(self, handle: PreviewHandleItem, text: str) -> None:
        if not text:
            return
        label = QGraphicsTextItem(text, handle)
        label.setDefaultTextColor(QColor("#111318"))
        label.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        label.setScale(0.085 * self.scale_factor)
        label.setPos(0.8 * self.scale_factor, -1.6 * self.scale_factor)
        label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        label.setZValue(1)

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
            item = DotItem(dot, self.scale_factor, self.dot_symbol)
            item.setPos(self.field_to_scene(dot.x, dot.y))
            item.label.setVisible(self.show_labels)
            locked = self.dot_locked(dot.id)
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self.active_tool == EditorTool.SELECT and not locked,
            )
            item.setOpacity(0.45 if locked else 1.0)
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
        if not prop.image_file:
            return generated_prop_pixmap(prop.name, prop.layer)
        if not path.is_absolute() and self.project_dir is not None:
            path = self.project_dir / prop.image_file
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            return pixmap
        return generated_prop_pixmap(prop.name, prop.layer)

    def draw_field(self) -> None:
        self.scene.clear()
        self.dot_items.clear()
        self.prop_items.clear()
        self.preview_items.clear()
        self.path_items.clear()
        self.snap_items.clear()
        scale = self.scale_factor
        palette = self.field_palette()
        field_half_width = FIELD_HALF_WIDTH_YARDS
        field_half_height = FIELD_HALF_HEIGHT_YARDS
        width = field_half_width * 2 * scale
        height = field_half_height * 2 * scale

        def scene_x(x_yards: float) -> float:
            return x_yards * scale

        def scene_y(y_yards: float) -> float:
            return -y_yards * scale

        def add_line(
            x1: float,
            y1: float,
            x2: float,
            y2: float,
            pen: QPen,
            z_value: float = -12,
        ) -> QGraphicsLineItem:
            item = self.scene.addLine(scene_x(x1), scene_y(y1), scene_x(x2), scene_y(y2), pen)
            item.setZValue(z_value)
            return item

        def add_rect(
            x1: float,
            y1: float,
            x2: float,
            y2: float,
            pen: QPen,
            brush: QColor | Qt.BrushStyle,
            z_value: float = -18,
        ) -> QGraphicsRectItem:
            item = QGraphicsRectItem(scene_x(x1), scene_y(y2), (x2 - x1) * scale, (y2 - y1) * scale)
            item.setPen(pen)
            item.setBrush(brush)
            item.setZValue(z_value)
            self.scene.addItem(item)
            return item

        def add_label(
            text: str,
            x: float,
            y: float,
            size: int = 8,
            color: str = "#2b3138",
            rotation: float = 0,
            weight: QFont.Weight = QFont.Weight.DemiBold,
            z_value: float = -7,
        ) -> QGraphicsTextItem:
            label = self.scene.addText(text, QFont("Arial", size, weight))
            label.setDefaultTextColor(QColor(color))
            bounds = label.boundingRect()
            label.setTransformOriginPoint(bounds.center())
            label.setRotation(rotation)
            label.setPos(scene_x(x) - bounds.width() / 2, scene_y(y) - bounds.height() / 2)
            label.setZValue(z_value)
            return label

        turf_pen = QPen(QColor(palette["field_border"]), 0.16 * scale)
        add_rect(-field_half_width, -field_half_height, field_half_width, field_half_height, turf_pen, QColor(palette["field_fill"]), -24)
        add_rect(-60, -field_half_height, -50, field_half_height, QPen(QColor(palette["yard"]), 0.06 * scale), QColor(palette["endzone_fill"]), -23)
        add_rect(50, -field_half_height, 60, field_half_height, QPen(QColor(palette["yard"]), 0.06 * scale), QColor(palette["endzone_fill"]), -23)

        perimeter_pen = QPen(QColor(palette["perimeter"]), 0.08 * scale, Qt.PenStyle.DashLine)
        add_rect(-65, -31.5, 65, 31.5, perimeter_pen, Qt.BrushStyle.NoBrush, -25)

        micro_pen = QPen(QColor(palette["micro"]), 0.018 * scale)
        minor_pen = QPen(QColor(palette["minor"]), 0.034 * scale)
        yard_pen = QPen(QColor(palette["yard"]), 0.08 * scale)
        heavy_pen = QPen(QColor(palette["heavy"]), 0.14 * scale)
        hash_pen = QPen(QColor(palette["hash"]), 0.12 * scale)
        sideline_tick_pen = QPen(QColor(palette["tick"]), 0.085 * scale)
        restraining_pen = QPen(QColor(palette["restraining"]), 0.055 * scale, Qt.PenStyle.DashLine)

        for yard in range(-59, 60):
            if yard % 5 == 0:
                continue
            add_line(yard, -field_half_height, yard, field_half_height, micro_pen if yard % 2 else minor_pen, -19)
        horizontal_y = -26
        while horizontal_y <= 26:
            if abs(horizontal_y - FRONT_HASH_YARDS) > 0.08 and abs(horizontal_y - BACK_HASH_YARDS) > 0.08:
                add_line(-60, horizontal_y, 60, horizontal_y, micro_pen, -20)
            horizontal_y += 1

        for yard in range(-60, 61, 5):
            pen = heavy_pen if abs(yard) in (50, 60) else yard_pen
            add_line(yard, -field_half_height, yard, field_half_height, pen, -13)

        add_line(-60, -field_half_height, 60, -field_half_height, heavy_pen, -12)
        add_line(-60, field_half_height, 60, field_half_height, heavy_pen, -12)
        add_line(-60, 0, 60, 0, QPen(QColor(palette["center"]), 0.045 * scale, Qt.PenStyle.DashLine), -18)

        hash_half_length = 1 / 3
        sideline_tick_length = 0.9
        for yard in range(-49, 50):
            if yard % 5 == 0:
                continue
            add_line(yard, FRONT_HASH_YARDS - hash_half_length, yard, FRONT_HASH_YARDS + hash_half_length, hash_pen, -10)
            add_line(yard, BACK_HASH_YARDS - hash_half_length, yard, BACK_HASH_YARDS + hash_half_length, hash_pen, -10)
            add_line(yard, -field_half_height, yard, -field_half_height + sideline_tick_length, sideline_tick_pen, -10)
            add_line(yard, field_half_height, yard, field_half_height - sideline_tick_length, sideline_tick_pen, -10)

        for hash_y, label_text in ((BACK_HASH_YARDS, "BACK HASH"), (FRONT_HASH_YARDS, "FRONT HASH")):
            add_line(-50, hash_y, 50, hash_y, QPen(QColor(palette["restraining"]), 0.045 * scale, Qt.PenStyle.DashLine), -17)
            add_label(label_text, 66.5, hash_y, 7, palette["label_muted"], 0, QFont.Weight.Bold, -6)

        for yard in range(-50, 51, 10):
            if abs(yard) == 50:
                label_text = "G"
            elif yard == 0:
                label_text = "50"
            else:
                label_text = str(50 - abs(yard))
            add_label(label_text, yard, -21.4, 9, palette["label"], 0, QFont.Weight.Bold, -6)
            add_label(label_text, yard, 21.4, 9, palette["label"], 180, QFont.Weight.Bold, -6)

        add_label("END ZONE", -55, 0, 10, palette["label"], -90, QFont.Weight.Bold, -6)
        add_label("END ZONE", 55, 0, 10, palette["label"], 90, QFont.Weight.Bold, -6)
        add_label("FRONT", 0, -42.5, 14, palette["label_heavy"], 0, QFont.Weight.Black, -6)
        add_label("BACK", 0, 42.5, 14, palette["label_heavy"], 0, QFont.Weight.Black, -6)
        add_label("SIDE\nONE", -76, 0, 12, palette["label_heavy"], 0, QFont.Weight.Black, -6)
        add_label("SIDE\nTWO", 76, 0, 12, palette["label_heavy"], 0, QFont.Weight.Black, -6)
        add_label("BACK SIDELINE", 70.5, field_half_height, 7, palette["label_heavy"], 0, QFont.Weight.Bold, -6)
        add_label("FRONT SIDELINE", 70.5, -field_half_height, 7, palette["label_heavy"], 0, QFont.Weight.Bold, -6)

        for side, y_start, y_end, label_y, label_rotation in (
            ("BACK", field_half_height + 3, field_half_height + 7.5, field_half_height + 5.2, 0),
            ("FRONT", -field_half_height - 7.5, -field_half_height - 3, -field_half_height - 5.2, 0),
        ):
            add_line(-50, y_start, 50, y_start, restraining_pen, -15)
            add_line(-50, y_end, 50, y_end, restraining_pen, -15)
            add_line(-50, y_start, -50, y_end, restraining_pen, -15)
            add_line(50, y_start, 50, y_end, restraining_pen, -15)
            add_label("COACHES AREA", 0, label_y, 7, palette["label_muted"], label_rotation, QFont.Weight.Bold, -6)
            bench_y1 = field_half_height + 8.2 if side == "BACK" else -field_half_height - 11.8
            bench_y2 = field_half_height + 11.8 if side == "BACK" else -field_half_height - 8.2
            add_rect(-30, bench_y1, 30, bench_y2, QPen(QColor(palette["bench"]), 0.08 * scale), Qt.BrushStyle.NoBrush, -15)
            add_label("BENCH", 0, (bench_y1 + bench_y2) / 2, 7, palette["label_muted"], 0, QFont.Weight.Bold, -6)
            add_label("TEAM\nBOX", 34, (bench_y1 + bench_y2) / 2, 6, palette["label_muted"], 0, QFont.Weight.Bold, -6)

        self.scene.setSceneRect(QRectF(-width / 2 - 300, -height / 2 - 210, width + 600, height + 420))

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
        if event.button() == Qt.MouseButton.LeftButton and isinstance(clicked_item, PathCurveItem):
            self.preserve_selection()
            self.restore_preserved_selection()
            event.accept()
            return
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

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        clicked_item = self.normalized_item(self.itemAt(event.position().toPoint()))
        if self.active_tool == EditorTool.SELECT and isinstance(clicked_item, DotItem):
            self.dot_edit_requested.emit(clicked_item.dot_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

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
            event.accept()
            return
        if self.active_tool == EditorTool.SHAPE_LINE and isinstance(clicked_item, DotItem):
            self.shape_anchor_toggled.emit(clicked_item.dot_id)
            event.accept()
            return
        menu = QMenu(self)
        actions: list[tuple[str, QAction]] = []
        if self.active_tool != EditorTool.SELECT:
            for name in ("Apply Preview", "Clear Preview", "Radial Tool Menu", "Focus Field", "Select Tool"):
                action = menu.addAction(name)
                actions.append((name, action))
            selected = menu.exec(event.globalPos())
            if selected:
                for name, action in actions:
                    if action == selected:
                        self.context_action.emit(name)
                        break
            event.accept()
            return
        selected_dot_count = len(self.selected_dot_ids())
        selected_prop_count = len(self.selected_prop_ids())
        if isinstance(clicked_item, DotItem):
            action = menu.addAction("Select Same Section")
            actions.append(("Select Same Section", action))
        if selected_dot_count:
            for name in (
                "Save Selection Set",
                "Save Formation Preset",
                "Carry Selected Forward",
                "Start Selected Move Here",
                "Set Opening Positions From Current View",
                "Face Front",
                "Face Back",
                "Rotate Facing -45",
                "Rotate Facing +45",
                "Lock Selected Sections",
                "Unlock Selected Sections",
            ):
                action = menu.addAction(name)
                actions.append((name, action))
            if selected_prop_count:
                action = menu.addAction("Fit Form to Selected Prop")
                actions.append(("Fit Form to Selected Prop", action))
            menu.addSeparator()
        action = menu.addAction("Radial Tool Menu")
        actions.append(("Radial Tool Menu", action))
        menu.addSeparator()
        for name in (
            "Preview Line",
            "Preview Curve",
            "Preview Arc",
            "Preview Circle",
            "Preview Oval",
            "Preview Rectangle",
            "Preview Triangle",
            "Preview Diamond",
            "Preview Polygon",
            "Preview Star",
            "Preview Spiral",
            "Preview Block",
            "Preview Scale Form",
            "Preview Warp Form",
            "Preview Rotate",
            "Preview SVG Shape",
            "Preview Scatter",
            "Preview Mirror",
            "Preview Shape Line",
        ):
            action = menu.addAction(name)
            actions.append((name, action))
        menu.addSeparator()
        for name in ("Focus Field", "Apply Preview", "Clear Preview"):
            action = menu.addAction(name)
            actions.append((name, action))
        selected = menu.exec(event.globalPos())
        if selected:
            for name, action in actions:
                if action == selected:
                    self.context_action.emit(name)
                    break
        event.accept()
