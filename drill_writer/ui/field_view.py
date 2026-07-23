from __future__ import annotations

from enum import Enum
from math import atan2, cos, degrees, hypot, pi, radians, sin
from pathlib import Path
from time import perf_counter
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTransform
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

from drill_writer.core.design_tools import guide_measurement_label, guide_path
from drill_writer.core.drill_grid import (
    DrillGridSettings,
    grid_axis_values,
    snap_position_mapping,
)
from drill_writer.core.models import ConstructionGuide, Dot, DrillProject, Prop, SurfaceDefinition, prop_default_state
from drill_writer.core.specialized_design import normalized_surface
from drill_writer.core.tools import path_length
from drill_writer.core.workflow import TransformParameters, selection_center, transform_positions
from drill_writer.ui.appearance import (
    FIELD_DOT_OUTLINE_YARDS,
    FIELD_DOT_RADIUS_YARDS,
    draw_dot_symbol,
    generated_prop_pixmap,
    normalize_dot_symbol,
    preferred_dot_symbol,
)
from drill_writer.ui.field_logo import (
    field_logo_dimensions_yards,
    field_logo_enabled,
    field_logo_opacity,
    field_logo_pixmap,
)
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
    def __init__(self, dot: Dot, scale: float, symbol: str, label_color: str = "#1c2430") -> None:
        radius = FIELD_DOT_RADIUS_YARDS * scale
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.dot_id = dot.id
        self.symbol = normalize_dot_symbol(symbol)
        self.facing_degrees = 0.0
        self.scale_factor = scale
        self.setBrush(QColor(dot.color))
        self.setPen(QPen(QColor("#1d2128"), FIELD_DOT_OUTLINE_YARDS * scale))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setZValue(10)
        self.label = QGraphicsTextItem(dot.name, self)
        self.label.setFont(QFont("Arial", 8))
        self.label.setDefaultTextColor(QColor(label_color))
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
        rotation_degrees: float = 0.0,
    ) -> None:
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.symbol = normalize_dot_symbol(symbol)
        self.preview_color = color
        self.outline_color = outline_color
        self.outline_width = outline_width
        self.rotation_degrees = float(rotation_degrees)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(9)

    def paint(self, painter: QPainter, _option, _widget=None) -> None:  # type: ignore[override]
        draw_dot_symbol(
            painter,
            self.rect().center(),
            self.rect().width() / 2,
            self.preview_color,
            self.symbol,
            rotation_degrees=self.rotation_degrees,
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


class ConstructionGuideItem(QGraphicsPathItem):
    def __init__(self, guide: ConstructionGuide, path: QPainterPath, scale: float) -> None:
        super().__init__(path)
        self.guide_id = guide.id
        self.guide_type = guide.guide_type
        color = QColor(guide.color)
        pen_style = (
            Qt.PenStyle.DashLine
            if guide.guide_type.startswith("no_go")
            or guide.guide_type == "annotation_note"
            or guide.metadata.get("category") == "live_symmetry"
            else Qt.PenStyle.SolidLine
        )
        width = 0.24 * scale if guide.guide_type == "annotation_arrow" else 0.16 * scale
        self.setPen(QPen(color, width, pen_style))
        if guide.guide_type.startswith("no_go"):
            fill = QColor(color)
            fill.setAlpha(38)
            self.setBrush(fill)
        elif guide.guide_type == "annotation_box":
            fill = QColor(str(guide.metadata.get("fill_color", "#ede9fe")))
            fill.setAlphaF(max(0.05, min(1.0, float(guide.metadata.get("opacity", 0.85)))) * 0.32)
            self.setBrush(fill)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not guide.locked)
        self.setCursor(Qt.CursorShape.ArrowCursor if guide.locked else Qt.CursorShape.SizeAllCursor)
        self.setToolTip(
            f"{guide_measurement_label(guide)}\n"
            + (
                "Locked reference object"
                if guide.locked and guide.guide_type.startswith("annotation_")
                else "Locked construction guide"
                if guide.locked
                else "Drag to move; double-click to edit"
            )
        )
        self.setOpacity(max(0.1, min(1.0, float(guide.metadata.get("opacity", 1.0)))))
        self.setZValue(6 if guide.guide_type.startswith("annotation_") else 4)


class TransformGizmoHandleItem(QGraphicsEllipseItem):
    def __init__(self, kind: str, scale: float) -> None:
        radius = (0.42 if kind in {"move", "rotate"} else 0.32) * scale
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.kind = kind
        colors = {
            "move": "#f7d154",
            "pivot": "#ffffff",
            "rotate": "#66d9ef",
            "scale_nw": "#8798ad",
            "scale_ne": "#8798ad",
            "scale_sw": "#8798ad",
            "scale_se": "#8798ad",
            "skew_x": "#b057ff",
            "skew_y": "#b057ff",
        }
        self.setBrush(QColor(colors.get(kind, "#e53935")))
        self.setPen(QPen(QColor("#111318"), 0.12 * scale))
        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if kind in {"move", "pivot"}
            else Qt.CursorShape.CrossCursor
        )
        self.setZValue(34)
        labels = {
            "move": "Move selection",
            "pivot": "Move transform pivot",
            "rotate": "Rotate around pivot",
            "scale_nw": "Scale width and height",
            "scale_ne": "Scale width and height",
            "scale_sw": "Scale width and height",
            "scale_se": "Scale width and height",
            "stretch_x": "Stretch horizontally",
            "stretch_y": "Stretch vertically",
            "skew_x": "Skew horizontally",
            "skew_y": "Skew vertically",
        }
        self.setToolTip(labels.get(kind, kind.replace("_", " ").title()))


class PathCurveItem(QGraphicsPathItem):
    def __init__(self, dot_id: str, path: QPainterPath, scale: float) -> None:
        super().__init__(path)
        self.dot_id = dot_id
        self.setPen(QPen(QColor("#f7d154"), 0.28 * scale, Qt.PenStyle.DashLine))
        self.setToolTip("Double-click to edit this marcher path; right-click to add an anchor")
        self.setZValue(5)


class ShapeLineItem(QGraphicsPathItem):
    def __init__(self, path: QPainterPath, scale: float, edit_kind: str = "formation") -> None:
        super().__init__(path)
        self.edit_kind = edit_kind
        self.setPen(QPen(QColor("#e53935"), 0.42 * scale))
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setToolTip("Double-click to edit this formation directly")
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


class DrillGridPointsItem(QGraphicsItem):
    def __init__(self, points: QPolygonF, bounds: QRectF, color: QColor) -> None:
        super().__init__()
        self.points = points
        self.bounds = bounds
        self.color = color
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(-18)

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return self.bounds

    def paint(self, painter: QPainter, _option, _widget=None) -> None:  # type: ignore[override]
        pen = QPen(self.color, 1.35)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPoints(self.points)


class FieldView(QGraphicsView):
    frame_painted = Signal(float)
    selection_changed = Signal(list)
    dot_moved = Signal(str, float, float)
    dots_moved = Signal(dict)
    dots_drag_preview = Signal(dict)
    prop_moved = Signal(str, dict)
    props_moved = Signal(dict)
    guide_moved = Signal(str, float, float)
    guide_edit_requested = Signal(str)
    context_action = Signal(str)
    dot_edit_requested = Signal(str)
    preview_handle_moved = Signal(str, float, float)
    preview_handle_moved_detailed = Signal(str, float, float, int)
    preview_handle_dragged = Signal(str, float, float, int)
    path_anchor_added = Signal(str, float, float)
    path_anchor_moved = Signal(str, int, float, float)
    path_anchor_moved_detailed = Signal(str, int, float, float, int)
    path_tangent_moved = Signal(str, int, str, float, float)
    path_tangent_moved_detailed = Signal(str, int, str, float, float, int)
    shape_anchor_added = Signal(float, float)
    shape_anchor_toggled = Signal(str)
    transform_gizmo_applied = Signal(object, object, object)
    precision_nudge_requested = Signal(float, float, str)
    temporary_tool_requested = Signal(object, bool, bool)
    direct_edit_requested = Signal(str, str)
    apply_requested = Signal()
    cancel_requested = Signal()

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
        self.guide_items: dict[str, ConstructionGuideItem] = {}
        self.measurement_items: list[QGraphicsItem] = []
        self.reference_set_index = 0
        self.active_tool = EditorTool.SELECT
        self.show_labels = True
        self.show_ghosts = True
        self.preview_items: list[QGraphicsItem] = []
        self.ghost_items: list[QGraphicsItem] = []
        self._ghost_positions: dict[str, tuple[float, float]] = {}
        self._ghost_facings: dict[str, float] = {}
        self.path_items: list[QGraphicsItem] = []
        self.snap_items: list[QGraphicsItem] = []
        self.drill_grid_items: list[QGraphicsItem] = []
        self.drafting_grid_items: list[QGraphicsItem] = []
        self.drill_grid = DrillGridSettings()
        self.snap_enabled = False
        self.snap_threshold = 0.85
        self.visible_section = "All"
        self.visible_layer = "All"
        self.locked_sections: set[str] = set()
        self.locked_layers: set[str] = set()
        self.locked_dot_ids: set[str] = set()
        self.dot_symbol = preferred_dot_symbol()
        self.field_mode = "white"
        self.show_field_logo = field_logo_enabled()
        self.field_logo_item: QGraphicsPixmapItem | None = None
        self._formation_callback: Callable[[EditorTool], None] | None = None
        self._pan_start: QPointF | None = None
        self._drag_start_positions: dict[str, tuple[float, float]] = {}
        self._drag_start_prop_states: dict[str, dict[str, float]] = {}
        self._active_preview_handle: PreviewHandleItem | None = None
        self._active_path_anchor: PathAnchorItem | None = None
        self._active_path_tangent: PathTangentItem | None = None
        self._active_guide_item: ConstructionGuideItem | None = None
        self._guide_drag_start_scene = QPointF()
        self._preserved_selection_ids: list[str] = []
        self._suppress_next_context_menu = False
        self._manual_drag_item: PreviewHandleItem | PathAnchorItem | PathTangentItem | None = None
        self._manual_drag_start_field: tuple[float, float] | None = None
        self._manual_drag_last_field: tuple[float, float] | None = None
        self._last_drag_modifiers = 0
        self._temporary_key: int | None = None
        self._temporary_tool_dirty = False
        self._tool_value_provider: Callable[[str, float, float, int], str] | None = None
        self._tool_value_item: QGraphicsTextItem | None = None
        self.transform_gizmo_enabled = False
        self.transform_gizmo_suspended = False
        self.motion_path_editing = False
        self.transform_gizmo_items: list[QGraphicsItem] = []
        self._transform_pivot: tuple[float, float] | None = None
        self._gizmo_selection_signature: tuple[str, ...] = ()
        self._active_transform_handle: TransformGizmoHandleItem | None = None
        self._gizmo_drag_start_positions: dict[str, tuple[float, float]] = {}
        self._gizmo_drag_handle_start = (0.0, 0.0)
        self._gizmo_drag_parameters = TransformParameters()
        self._gizmo_drag_pivot_start: tuple[float, float] | None = None
        self._lasso_points: list[QPointF] = []
        self._lasso_item: QGraphicsPathItem | None = None
        self._lasso_additive = False
        self.playback_quality = "full"
        self.last_paint_duration_ms = 0.0
        self.scene.selectionChanged.connect(self.update_transform_gizmo)
        self.draw_field()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        started = perf_counter()
        super().paintEvent(event)
        self.last_paint_duration_ms = (perf_counter() - started) * 1000.0
        self.frame_painted.emit(self.last_paint_duration_ms)

    def set_playback_quality(self, quality: str, performer_count: int = 0) -> None:
        normalized = quality if quality in {"full", "balanced", "performance"} else "full"
        if normalized == self.playback_quality and normalized != "full":
            return
        self.playback_quality = normalized
        if normalized == "full":
            hints = QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
            suppress_labels = False
        elif normalized == "balanced":
            hints = QPainter.RenderHint.Antialiasing
            suppress_labels = performer_count >= 320
        else:
            hints = QPainter.RenderHint(0)
            suppress_labels = performer_count >= 180
        self.setRenderHints(hints)
        for item in self.dot_items.values():
            item.label.setVisible(self.show_labels and not suppress_labels)
        self.viewport().update()

    def set_canvas_theme(self, mode: str) -> None:
        self.setBackgroundBrush(QColor("#eef2f7" if mode == "light" else "#111318"))

    def set_field_mode(self, mode: str) -> None:
        normalized = normalize_field_mode(mode)
        if normalized == self.field_mode and self.scene.items():
            return
        selected_dot_ids = self.selected_dot_ids()
        selected_prop_ids = self.selected_prop_ids()
        selected_guide_ids = self.selected_guide_ids()
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
            self.rebuild_guides()
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
            for guide_id in selected_guide_ids:
                item = self.guide_items.get(guide_id)
                if item:
                    item.setSelected(True)
            self.rebuild_ghosts()
        self.selection_changed.emit(self.selected_dot_ids())

    def set_field_logo_visible(self, visible: bool) -> None:
        self.show_field_logo = bool(visible)
        if self.field_logo_item is not None:
            self.field_logo_item.setVisible(self.show_field_logo)
        self.viewport().update()

    def refresh_field_logo(self) -> None:
        if self.field_logo_item is not None:
            self.scene.removeItem(self.field_logo_item)
            self.field_logo_item = None
        surface = self.surface_definition()
        if surface.surface_type == "parade":
            self.viewport().update()
            return
        logo = field_logo_pixmap(self.field_mode)
        logo_width_yards, logo_height_yards = field_logo_dimensions_yards(surface, logo)
        if logo.isNull() or logo_width_yards <= 0 or logo_height_yards <= 0:
            self.viewport().update()
            return
        logo_scale = min(
            logo_width_yards * self.scale_factor / logo.width(),
            logo_height_yards * self.scale_factor / logo.height(),
        )
        self.field_logo_item = self.scene.addPixmap(logo)
        self.field_logo_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.field_logo_item.setScale(logo_scale)
        self.field_logo_item.setPos(
            -logo.width() * logo_scale / 2,
            -logo.height() * logo_scale / 2,
        )
        self.field_logo_item.setOpacity(field_logo_opacity(self.field_mode))
        self.field_logo_item.setZValue(-21)
        self.field_logo_item.setVisible(self.show_field_logo)
        self.viewport().update()

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
                "performer_label": "#ffffff",
                "tool_label": "#ffffff",
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
                "performer_label": "#ffffff",
                "tool_label": "#ffffff",
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
            "performer_label": "#1c2430",
            "tool_label": "#111318",
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
        self.rebuild_ghosts()
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
        self.draw_field()
        self.rebuild_guides()
        self.rebuild_props()
        self.rebuild_dots()

    def surface_definition(self) -> SurfaceDefinition:
        return normalized_surface(self.project.surface) if self.project is not None else SurfaceDefinition()

    def set_reference_set_index(self, set_index: int) -> None:
        normalized = max(0, int(set_index))
        if normalized == self.reference_set_index:
            return
        selected = self.selected_guide_ids()
        self.reference_set_index = normalized
        self.rebuild_guides()
        for guide_id in selected:
            item = self.guide_items.get(guide_id)
            if item:
                item.setSelected(True)

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
                tool == EditorTool.SELECT and not self.motion_path_editing and not self.dot_locked(item.dot_id),
            )
        for item in self.prop_items.values():
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, tool == EditorTool.SELECT)
        self.update_transform_gizmo()

    def set_motion_path_editing(self, enabled: bool) -> None:
        self.motion_path_editing = bool(enabled)
        for item in self.dot_items.values():
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self.active_tool == EditorTool.SELECT
                and not self.motion_path_editing
                and not self.dot_locked(item.dot_id),
            )
        self.set_transform_gizmo_suspended(self.motion_path_editing)

    def set_transform_gizmo_enabled(self, enabled: bool) -> None:
        self.transform_gizmo_enabled = bool(enabled)
        self.update_transform_gizmo()

    def set_transform_gizmo_suspended(self, suspended: bool) -> None:
        self.transform_gizmo_suspended = bool(suspended)
        self.update_transform_gizmo()

    def set_transform_pivot(self, pivot: tuple[float, float] | None) -> None:
        self._transform_pivot = pivot
        self.update_transform_gizmo()

    def set_snap_enabled(self, enabled: bool) -> None:
        self.snap_enabled = enabled
        if not enabled:
            self.clear_snap_guides()

    def set_drill_grid(self, settings: DrillGridSettings) -> None:
        self.drill_grid = DrillGridSettings.from_json(settings.to_json())
        show_drafting_grid = not (self.drill_grid.enabled and self.drill_grid.show_overlay)
        for item in self.drafting_grid_items:
            item.setVisible(show_drafting_grid)
        self.clear_drill_grid_overlay()
        self.draw_drill_grid_overlay(self.surface_definition())
        if not self.drill_grid.enabled:
            self.clear_snap_guides()
        self.viewport().update()

    def clear_drill_grid_overlay(self) -> None:
        for item in self.drill_grid_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self.drill_grid_items.clear()

    def draw_drill_grid_overlay(self, surface: SurfaceDefinition) -> None:
        if not self.drill_grid.enabled or not self.drill_grid.show_overlay:
            return
        x_values = grid_axis_values(
            -surface.half_width,
            surface.half_width,
            self.drill_grid.origin_x,
            self.drill_grid.spacing_x,
        )
        y_values = grid_axis_values(
            -surface.half_height,
            surface.half_height,
            self.drill_grid.origin_y,
            self.drill_grid.spacing_y,
        )
        if self.drill_grid.display_style == "points":
            color = QColor("#d5b8ff" if self.field_mode in {"grass", "inverted"} else "#7651d8")
            color.setAlpha(118 if self.field_mode in {"grass", "inverted"} else 92)
            points = QPolygonF(
                [self.field_to_scene(x, y) for x in x_values for y in y_values]
            )
            bounds = QRectF(
                -surface.half_width * self.scale_factor,
                -surface.half_height * self.scale_factor,
                surface.width_yards * self.scale_factor,
                surface.height_yards * self.scale_factor,
            )
            item = DrillGridPointsItem(points, bounds, color)
            self.scene.addItem(item)
            self.drill_grid_items.append(item)
            return
        vertical_path = QPainterPath()
        horizontal_path = QPainterPath()
        for x in x_values:
            vertical_path.moveTo(self.field_to_scene(x, -surface.half_height))
            vertical_path.lineTo(self.field_to_scene(x, surface.half_height))
        for y in y_values:
            horizontal_path.moveTo(self.field_to_scene(-surface.half_width, y))
            horizontal_path.lineTo(self.field_to_scene(surface.half_width, y))

        color = QColor("#c49cff" if self.field_mode in {"grass", "inverted"} else "#7651d8")
        color.setAlpha(82 if self.field_mode in {"grass", "inverted"} else 64)
        pen = QPen(color, 1.0)
        pen.setCosmetic(True)
        for path in (vertical_path, horizontal_path):
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            item.setZValue(-18)
            self.scene.addItem(item)
            self.drill_grid_items.append(item)

    def set_locked_filters(
        self,
        sections: set[str],
        layers: set[str],
        dot_ids: set[str] | None = None,
    ) -> None:
        self.locked_sections = set(sections)
        self.locked_layers = set(layers)
        self.locked_dot_ids = set(dot_ids or ())
        for item in self.dot_items.values():
            locked = self.dot_locked(item.dot_id)
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self.active_tool == EditorTool.SELECT and not self.motion_path_editing and not locked,
            )
            item.setOpacity(0.45 if locked else 1.0)

    def dot_locked(self, dot_id: str) -> bool:
        if not self.project:
            return False
        dot = self.project.dot_by_id(dot_id)
        if not dot:
            return False
        return (
            dot_id in self.locked_dot_ids
            or bool(dot.section and dot.section in self.locked_sections)
            or bool(dot.layer and dot.layer in self.locked_layers)
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
        self.rebuild_ghosts()

    def set_formation_callback(self, callback: Callable[[EditorTool], None]) -> None:
        self._formation_callback = callback

    def set_tool_value_provider(
        self,
        callback: Callable[[str, float, float, int], str] | None,
    ) -> None:
        self._tool_value_provider = callback

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

    def selected_guide_ids(self) -> list[str]:
        return [
            item.guide_id
            for item in self.scene.selectedItems()
            if isinstance(item, ConstructionGuideItem)
        ]

    def drill_grid_reference_rows(self) -> tuple[float, ...]:
        if self.project is None or self.project.surface.surface_type != "football":
            return ()
        surface = self.project.surface
        if surface.hash_style == "none":
            return ()
        return float(surface.front_hash_yards), float(surface.back_hash_yards)

    def snap_drill_grid_point(self, point: tuple[float, float]) -> tuple[float, float]:
        return self.drill_grid.snap_point(point, reference_y=self.drill_grid_reference_rows())

    def snap_drill_grid_positions(
        self,
        positions: dict[str, tuple[float, float]],
    ) -> dict[str, tuple[float, float]]:
        return snap_position_mapping(
            positions,
            self.drill_grid,
            reference_y=self.drill_grid_reference_rows(),
        )

    def normalized_item(self, item: QGraphicsItem | None) -> QGraphicsItem | None:
        if isinstance(item, (QGraphicsTextItem, QGraphicsPixmapItem)) and isinstance(
            item.parentItem(),
            (DotItem, PreviewHandleItem, ConstructionGuideItem),
        ):
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
        if self._active_transform_handle is None:
            self.update_transform_gizmo()

    def set_ghosts_visible(self, visible: bool) -> None:
        self.show_ghosts = bool(visible)
        for item in self.ghost_items:
            item.setVisible(self.show_ghosts)
        if self.show_ghosts and not self.ghost_items and self._ghost_positions:
            self.rebuild_ghosts()
        self.viewport().update()

    def set_ghost_positions(
        self,
        positions: dict[str, tuple[float, float]],
        facings: dict[str, float] | None = None,
    ) -> None:
        self._ghost_positions = dict(positions)
        self._ghost_facings = dict(facings or {})
        self.rebuild_ghosts()

    def clear_ghosts(self, *, reset: bool = True) -> None:
        for item in self.ghost_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self.ghost_items.clear()
        if reset:
            self._ghost_positions.clear()
            self._ghost_facings.clear()

    def rebuild_ghosts(self) -> None:
        self.clear_ghosts(reset=False)
        if not self.show_ghosts or not self.project or not self._ghost_positions:
            return
        radius = FIELD_DOT_RADIUS_YARDS * self.scale_factor
        outline = QColor(self.field_palette()["performer_label"])
        outline.setAlpha(120)
        for dot in self.project.dots:
            position = self._ghost_positions.get(dot.id)
            if position is None:
                continue
            current_item = self.dot_items.get(dot.id)
            if current_item is not None and not current_item.isVisible():
                continue
            color = QColor(dot.color or "#e53935")
            color.setAlpha(78)
            item = DotSymbolPreviewItem(
                radius,
                color,
                self.dot_symbol,
                outline,
                FIELD_DOT_OUTLINE_YARDS * self.scale_factor,
                rotation_degrees=self._ghost_facings.get(dot.id, 0.0),
            )
            item.setPos(self.field_to_scene(*position))
            item.setZValue(5)
            self.scene.addItem(item)
            self.ghost_items.append(item)

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

    def clear_transform_gizmo(self) -> None:
        for item in self.transform_gizmo_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self.transform_gizmo_items.clear()

    def update_transform_gizmo(self) -> None:
        if self._active_transform_handle is not None:
            return
        self.clear_transform_gizmo()
        selected_ids = sorted(self.selected_dot_ids())
        signature = tuple(selected_ids)
        if signature != self._gizmo_selection_signature:
            self._gizmo_selection_signature = signature
            self._transform_pivot = None
        if (
            not self.transform_gizmo_enabled
            or self.transform_gizmo_suspended
            or self.active_tool != EditorTool.SELECT
            or len(selected_ids) < 2
        ):
            return
        positions = {
            dot_id: self.scene_to_field(self.dot_items[dot_id].pos())
            for dot_id in selected_ids
            if dot_id in self.dot_items
        }
        if not positions:
            return
        xs = [point[0] for point in positions.values()]
        ys = [point[1] for point in positions.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        if max_x - min_x < 1.5:
            min_x -= 0.75
            max_x += 0.75
        if max_y - min_y < 1.5:
            min_y -= 0.75
            max_y += 0.75
        center_x, center_y = selection_center(positions.values())
        self._transform_pivot = self._transform_pivot or (center_x, center_y)
        scene_left = min_x * self.scale_factor
        scene_right = max_x * self.scale_factor
        scene_top = -max_y * self.scale_factor
        scene_bottom = -min_y * self.scale_factor
        outline = QGraphicsRectItem(QRectF(scene_left, scene_top, scene_right - scene_left, scene_bottom - scene_top))
        outline.setPen(QPen(QColor("#66d9ef"), 0.07 * self.scale_factor, Qt.PenStyle.DashLine))
        outline.setBrush(Qt.BrushStyle.NoBrush)
        outline.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        outline.setZValue(31)
        self.scene.addItem(outline)
        self.transform_gizmo_items.append(outline)
        handles = {
            "scale_nw": (min_x, max_y),
            "scale_ne": (max_x, max_y),
            "scale_sw": (min_x, min_y),
            "scale_se": (max_x, min_y),
            "move": (center_x, min_y - 1.6),
            "rotate": (center_x, max_y + 2.6),
            "pivot": self._transform_pivot,
        }
        connector_pen = QPen(QColor("#66d9ef"), 0.08 * self.scale_factor, Qt.PenStyle.DotLine)
        for start, end in (
            ((center_x, max_y), handles["rotate"]),
            ((center_x, min_y), handles["move"]),
        ):
            line = QGraphicsLineItem(
                self.field_to_scene(*start).x(),
                self.field_to_scene(*start).y(),
                self.field_to_scene(*end).x(),
                self.field_to_scene(*end).y(),
            )
            line.setPen(connector_pen)
            line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            line.setZValue(32)
            self.scene.addItem(line)
            self.transform_gizmo_items.append(line)
        for kind, position in handles.items():
            handle = TransformGizmoHandleItem(kind, self.scale_factor)
            handle.setPos(self.field_to_scene(*position))
            self.scene.addItem(handle)
            self.transform_gizmo_items.append(handle)

    def transform_parameters_for_gizmo(
        self,
        kind: str,
        cursor: tuple[float, float],
        modifiers: int = 0,
    ) -> TransformParameters:
        pivot = self._transform_pivot or selection_center(self._gizmo_drag_start_positions.values())
        start_x, start_y = self._gizmo_drag_handle_start
        cursor_x, cursor_y = cursor
        parameters = TransformParameters(pivot=pivot)
        shift = bool(modifiers & int(Qt.KeyboardModifier.ShiftModifier.value))
        if kind == "move":
            parameters.offset_x = cursor_x - start_x
            parameters.offset_y = cursor_y - start_y
            if shift:
                if abs(parameters.offset_x) >= abs(parameters.offset_y):
                    parameters.offset_y = 0.0
                else:
                    parameters.offset_x = 0.0
        elif kind == "rotate":
            start_angle = atan2(start_y - pivot[1], start_x - pivot[0])
            current_angle = atan2(cursor_y - pivot[1], cursor_x - pivot[0])
            parameters.rotation_degrees = degrees(current_angle - start_angle)
            if shift:
                parameters.rotation_degrees = round(parameters.rotation_degrees / 15.0) * 15.0
        elif kind.startswith("scale_"):
            denominator_x = start_x - pivot[0]
            denominator_y = start_y - pivot[1]
            parameters.scale_x = self.safe_scale((cursor_x - pivot[0]) / denominator_x if abs(denominator_x) > 0.001 else 1.0)
            parameters.scale_y = self.safe_scale((cursor_y - pivot[1]) / denominator_y if abs(denominator_y) > 0.001 else 1.0)
            if shift:
                scale = parameters.scale_x if abs(parameters.scale_x - 1.0) >= abs(parameters.scale_y - 1.0) else parameters.scale_y
                parameters.scale_x = scale
                parameters.scale_y = scale
        elif kind == "stretch_x":
            denominator = start_x - pivot[0]
            parameters.scale_x = self.safe_scale((cursor_x - pivot[0]) / denominator if abs(denominator) > 0.001 else 1.0)
        elif kind == "stretch_y":
            denominator = start_y - pivot[1]
            parameters.scale_y = self.safe_scale((cursor_y - pivot[1]) / denominator if abs(denominator) > 0.001 else 1.0)
        elif kind == "skew_x":
            height = max(1.0, max(point[1] for point in self._gizmo_drag_start_positions.values()) - min(point[1] for point in self._gizmo_drag_start_positions.values()))
            parameters.skew_x_degrees = degrees(atan2(cursor_x - start_x, height))
            if shift:
                parameters.skew_x_degrees = round(parameters.skew_x_degrees / 5.0) * 5.0
        elif kind == "skew_y":
            width = max(1.0, max(point[0] for point in self._gizmo_drag_start_positions.values()) - min(point[0] for point in self._gizmo_drag_start_positions.values()))
            parameters.skew_y_degrees = degrees(atan2(cursor_y - start_y, width))
            if shift:
                parameters.skew_y_degrees = round(parameters.skew_y_degrees / 5.0) * 5.0
        return parameters

    @staticmethod
    def safe_scale(value: float) -> float:
        if 0 <= value < 0.05:
            return 0.05
        if -0.05 < value < 0:
            return -0.05
        return max(-12.0, min(12.0, value))

    def show_preview(
        self,
        starts: dict[str, tuple[float, float]],
        targets: dict[str, tuple[float, float]],
        handles: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.clear_preview()
        preview_pen = QPen(QColor("#f7d154"), 0.14 * self.scale_factor, Qt.PenStyle.DashLine)
        preview_fill = QColor(247, 209, 84, 120)
        radius = FIELD_DOT_RADIUS_YARDS * self.scale_factor
        if self.active_tool == EditorTool.LINE and len(targets) > 1:
            target_points = list(targets.values())
            span_x = max(point[0] for point in target_points) - min(point[0] for point in target_points)
            span_y = max(point[1] for point in target_points) - min(point[1] for point in target_points)
            target_points.sort(key=lambda point: point[0] if span_x >= span_y else point[1])
            line_item = ShapeLineItem(self.make_painter_path(target_points), self.scale_factor, "line")
            self.scene.addItem(line_item)
            self.preview_items.append(line_item)
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
                FIELD_DOT_OUTLINE_YARDS * self.scale_factor,
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
            item = ShapeLineItem(painter_path, self.scale_factor, "shape_line")
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
        radius = FIELD_DOT_RADIUS_YARDS * self.scale_factor
        for target in targets.values():
            target_item = DotSymbolPreviewItem(
                radius,
                QColor(247, 209, 84, 130),
                self.dot_symbol,
                QColor("#fff2a6"),
                FIELD_DOT_OUTLINE_YARDS * self.scale_factor,
            )
            target_item.setPos(self.field_to_scene(*target))
            self.scene.addItem(target_item)
            self.preview_items.append(target_item)

    def show_follow_leader_preview(
        self,
        routes: list[list[tuple[float, float]]],
        targets: dict[str, tuple[float, float]],
        leaders: list[tuple[str, tuple[float, float]]],
    ) -> None:
        self.clear_preview()
        for route in routes:
            if len(route) <= 1:
                continue
            item = ShapeLineItem(self.make_painter_path(route), self.scale_factor, "follow_leader")
            item.setToolTip("Shared Follow-the-Leader route")
            self.scene.addItem(item)
            self.preview_items.append(item)
        radius = FIELD_DOT_RADIUS_YARDS * self.scale_factor
        for target in targets.values():
            target_item = DotSymbolPreviewItem(
                radius,
                QColor(247, 209, 84, 145),
                self.dot_symbol,
                QColor("#fff2a6"),
                FIELD_DOT_OUTLINE_YARDS * self.scale_factor,
            )
            target_item.setPos(self.field_to_scene(*target))
            self.scene.addItem(target_item)
            self.preview_items.append(target_item)
        for leader_id, position in leaders:
            handle = PreviewHandleItem(f"follow_leader:{leader_id}", self.scale_factor)
            handle.setBrush(QColor("#f7d154"))
            handle.setPen(QPen(QColor("#111318"), 0.14 * self.scale_factor))
            handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            handle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            handle.setPos(self.field_to_scene(*position))
            self.scene.addItem(handle)
            self.add_preview_handle_label(handle, f"Leader {leader_id}")
            self.preview_items.append(handle)

    def show_motion_ribbon_preview(
        self,
        center_path: list[tuple[float, float]],
        left_edge: list[tuple[float, float]],
        right_edge: list[tuple[float, float]],
        paths: dict[str, list[tuple[float, float]]],
        ribbon_id: str,
        nodes: list[dict[str, tuple[float, float]]],
    ) -> None:
        self.clear_preview()
        for edge in (left_edge, right_edge):
            if len(edge) < 2:
                continue
            item = QGraphicsPathItem(self.make_painter_path(edge))
            item.setPen(QPen(QColor("#a855f7"), 0.18 * self.scale_factor, Qt.PenStyle.DashLine))
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            item.setZValue(12)
            self.scene.addItem(item)
            self.preview_items.append(item)
        if len(center_path) > 1:
            item = ShapeLineItem(self.make_painter_path(center_path), self.scale_factor, "motion_ribbon")
            item.setPen(QPen(QColor("#e53935"), 0.5 * self.scale_factor))
            item.setToolTip("Group Motion Ribbon — drag red nodes or cyan tangent handles")
            self.scene.addItem(item)
            self.preview_items.append(item)
        lane_pen = QPen(QColor(247, 209, 84, 155), 0.09 * self.scale_factor, Qt.PenStyle.DotLine)
        for path in paths.values():
            if len(path) < 2:
                continue
            item = QGraphicsPathItem(self.make_painter_path(path))
            item.setPen(lane_pen)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            item.setZValue(11)
            self.scene.addItem(item)
            self.preview_items.append(item)
        for index, node in enumerate(nodes):
            point = node.get("point")
            if point is None:
                continue
            node_handle = PreviewHandleItem(f"motion_ribbon_node:{ribbon_id}:{index}", self.scale_factor)
            node_handle.setBrush(QColor("#e53935"))
            node_handle.setPen(QPen(QColor("#ffffff"), 0.15 * self.scale_factor))
            node_handle.setToolTip("Drag to reshape the shared group route")
            node_handle.setPos(self.field_to_scene(*point))
            self.scene.addItem(node_handle)
            self.add_preview_handle_label(node_handle, f"P{index + 1}")
            self.preview_items.append(node_handle)
            for control_name in ("in", "out"):
                control = node.get(control_name)
                if control is None:
                    continue
                line = QGraphicsLineItem()
                node_scene = self.field_to_scene(*point)
                control_scene = self.field_to_scene(*control)
                line.setLine(node_scene.x(), node_scene.y(), control_scene.x(), control_scene.y())
                line.setPen(QPen(QColor("#66d9ef"), 0.1 * self.scale_factor, Qt.PenStyle.DotLine))
                line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                line.setZValue(13)
                self.scene.addItem(line)
                self.preview_items.append(line)
                tangent = PreviewHandleItem(
                    f"motion_ribbon_tangent:{ribbon_id}:{index}:{control_name}",
                    self.scale_factor,
                )
                tangent.setBrush(QColor("#66d9ef"))
                tangent.setPen(QPen(QColor("#0b1d24"), 0.13 * self.scale_factor))
                tangent.setToolTip("Drag tangent; hold Alt for a mirrored opposite handle")
                tangent.setPos(control_scene)
                self.scene.addItem(tangent)
                self.preview_items.append(tangent)

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
            item = ShapeLineItem(painter_path, self.scale_factor, self.active_tool.value)
            self.scene.addItem(item)
            self.preview_items.append(item)
        preview_pen = QPen(QColor("#f7d154"), 0.12 * self.scale_factor, Qt.PenStyle.DashLine)
        radius = FIELD_DOT_RADIUS_YARDS * self.scale_factor
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
                FIELD_DOT_OUTLINE_YARDS * self.scale_factor,
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
            "transform_pivot": "pivot",
            "line_start": "start",
            "line_end": "end",
            "curve_bend": "bend",
            "curve_start": "start",
            "curve_on_1": "curve",
            "curve_on_2": "curve",
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
        elif kind == "transform_pivot":
            handle.setBrush(QColor("#ffffff"))
            handle.setPen(QPen(QColor("#b057ff"), 0.18 * self.scale_factor))
        elif "width" in kind or "height" in kind or "radius" in kind or "spacing" in kind:
            handle.setBrush(QColor("#f7d154"))
            handle.setPen(QPen(QColor("#20242b"), 0.14 * self.scale_factor))
        elif kind in {
            "line_start",
            "line_end",
            "curve_bend",
            "curve_start",
            "curve_on_1",
            "curve_on_2",
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
        label.setDefaultTextColor(QColor(self.field_palette()["tool_label"]))
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
        suppress_labels = self.playback_quality == "performance" and len(self.dot_items) >= 180
        suppress_labels = suppress_labels or (
            self.playback_quality == "balanced" and len(self.dot_items) >= 320
        )
        for item in self.dot_items.values():
            item.label.setVisible(enabled and not suppress_labels)

    def rebuild_dots(self) -> None:
        for item in self.dot_items.values():
            self.scene.removeItem(item)
        self.dot_items.clear()
        if not self.project:
            return
        for dot in self.project.dots:
            item = DotItem(
                dot,
                self.scale_factor,
                self.dot_symbol,
                self.field_palette()["performer_label"],
            )
            item.setPos(self.field_to_scene(dot.x, dot.y))
            suppress_labels = self.playback_quality == "performance" and len(self.project.dots) >= 180
            suppress_labels = suppress_labels or (
                self.playback_quality == "balanced" and len(self.project.dots) >= 320
            )
            item.label.setVisible(self.show_labels and not suppress_labels)
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

    def rebuild_guides(self) -> None:
        for item in self.guide_items.values():
            self.scene.removeItem(item)
        self.guide_items.clear()
        if not self.project:
            return
        for guide in self.project.guides:
            if not guide.visible:
                continue
            scope = int(guide.metadata.get("set_index", -1))
            if guide.guide_type.startswith("annotation_") and scope not in {-1, self.reference_set_index}:
                continue
            painter_path = self.guide_painter_path(guide)
            if painter_path.isEmpty():
                continue
            item = ConstructionGuideItem(guide, painter_path, self.scale_factor)
            self.scene.addItem(item)
            self.guide_items[guide.id] = item
            if guide.guide_type.startswith("annotation_"):
                self.decorate_reference_item(item, guide, painter_path)
                continue
            label = QGraphicsTextItem(guide_measurement_label(guide), item)
            label.setDefaultTextColor(QColor(guide.color))
            label.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            label.setPos(painter_path.boundingRect().topLeft() + QPointF(5, 4))

    def decorate_reference_item(
        self,
        item: ConstructionGuideItem,
        guide: ConstructionGuide,
        painter_path: QPainterPath,
    ) -> None:
        guide_type = guide.guide_type
        text = str(guide.metadata.get("text", guide.name)).strip() or guide.name
        color = QColor(guide.color)
        if guide_type == "annotation_arrow" and len(guide.points) >= 2:
            start_scene = self.field_to_scene(*guide.points[0])
            end_scene = self.field_to_scene(*guide.points[1])
            angle = atan2(end_scene.y() - start_scene.y(), end_scene.x() - start_scene.x())
            arrow_size = 1.0 * self.scale_factor
            arrow = QPainterPath(end_scene)
            arrow.lineTo(
                end_scene
                - QPointF(cos(angle - pi / 6) * arrow_size, sin(angle - pi / 6) * arrow_size)
            )
            arrow.lineTo(
                end_scene
                - QPointF(cos(angle + pi / 6) * arrow_size, sin(angle + pi / 6) * arrow_size)
            )
            arrow.closeSubpath()
            arrow_item = QGraphicsPathItem(arrow, item)
            arrow_item.setPen(QPen(color, 0.12 * self.scale_factor))
            arrow_item.setBrush(color)
            arrow_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        elif guide_type == "annotation_image" and len(guide.points) >= 2:
            image_path = Path(str(guide.metadata.get("image_file", "")))
            if not image_path.is_absolute() and self.project_dir is not None:
                image_path = self.project_dir / image_path
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                first = self.field_to_scene(*guide.points[0])
                second = self.field_to_scene(*guide.points[1])
                target = QRectF(first, second).normalized()
                picture = QGraphicsPixmapItem(pixmap, item)
                picture.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                picture.setPos(target.topLeft())
                picture.setTransform(
                    QTransform.fromScale(
                        target.width() / max(1, pixmap.width()),
                        target.height() / max(1, pixmap.height()),
                    )
                )
                picture.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                picture.setZValue(-1)
        if guide_type != "annotation_image" or text:
            label = QGraphicsTextItem("", item)
            label.setDefaultTextColor(color)
            label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold if guide_type != "annotation_note" else QFont.Weight.Normal))
            label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            if guide_type == "annotation_note":
                safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                fill = str(guide.metadata.get("fill_color", "#ede9fe"))
                label.setHtml(f'<div style="background:{fill}; padding:6px; border:1px solid {guide.color};">{safe_text}</div>')
                label.setTextWidth(240)
            else:
                label.setPlainText(text)
            label.setPos(painter_path.boundingRect().topLeft() + QPointF(6, 5))

    def clear_measurements(self) -> None:
        for item in self.measurement_items:
            self.scene.removeItem(item)
        self.measurement_items.clear()

    def show_measurements(
        self,
        ordered_points: list[tuple[str, tuple[float, float]]],
        transition_paths: dict[str, list[tuple[float, float]]],
        duration_counts: float,
        mode: str = "all",
    ) -> None:
        self.clear_measurements()
        if not ordered_points:
            return
        normalized = mode.strip().lower()
        violet = QColor("#a855f7")
        cyan = QColor("#18b8d8")
        pen = QPen(violet, 0.12 * self.scale_factor, Qt.PenStyle.DashLine)
        if normalized in {"all", "intervals"}:
            intervals = list(zip(ordered_points, ordered_points[1:]))
            label_stride = max(1, (len(intervals) + 59) // 60)
            for index, ((_first_id, first), (_second_id, second)) in enumerate(intervals):
                first_scene = self.field_to_scene(*first)
                second_scene = self.field_to_scene(*second)
                line = QGraphicsLineItem(first_scene.x(), first_scene.y(), second_scene.x(), second_scene.y())
                line.setPen(pen)
                line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                line.setZValue(28)
                self.scene.addItem(line)
                self.measurement_items.append(line)
                yards = hypot(second[0] - first[0], second[1] - first[1])
                midpoint = ((first_scene.x() + second_scene.x()) / 2, (first_scene.y() + second_scene.y()) / 2)
                if index % label_stride == 0:
                    self.add_measurement_label(f"{yards:.2f} yd  ·  {yards * 8:.1f} steps", QPointF(*midpoint), violet)
        if normalized in {"all", "travel"}:
            travel_items = list(transition_paths.items())
            label_stride = max(1, (len(travel_items) + 59) // 60)
            for index, (dot_id, path) in enumerate(travel_items):
                if len(path) < 2:
                    continue
                yards = path_length(path)
                speed = yards / max(0.001, duration_counts)
                painter_path = self.make_painter_path(path)
                route = QGraphicsPathItem(painter_path)
                route.setPen(QPen(cyan, 0.14 * self.scale_factor, Qt.PenStyle.DotLine))
                route.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                route.setZValue(27)
                self.scene.addItem(route)
                self.measurement_items.append(route)
                midpoint = painter_path.pointAtPercent(0.5)
                if index % label_stride == 0:
                    self.add_measurement_label(
                        f"{dot_id}: {yards:.2f} yd  ·  {yards * 8:.1f} steps  ·  {speed:.2f} yd/count",
                        midpoint,
                        cyan,
                    )
        if normalized in {"all", "geometry"}:
            points = [point for _dot_id, point in ordered_points]
            center = selection_center(points)
            radii = [hypot(point[0] - center[0], point[1] - center[1]) for point in points]
            radius = sum(radii) / len(radii)
            center_scene = self.field_to_scene(*center)
            if radius > 0.01:
                circle = QGraphicsEllipseItem(
                    center_scene.x() - radius * self.scale_factor,
                    center_scene.y() - radius * self.scale_factor,
                    radius * 2 * self.scale_factor,
                    radius * 2 * self.scale_factor,
                )
                circle.setPen(QPen(violet, 0.1 * self.scale_factor, Qt.PenStyle.DotLine))
                circle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                circle.setZValue(26)
                self.scene.addItem(circle)
                self.measurement_items.append(circle)
            angle = 0.0
            if len(points) >= 2:
                angle = degrees(atan2(points[-1][1] - points[0][1], points[-1][0] - points[0][0]))
            self.add_measurement_label(
                f"Angle {angle:.1f}°  ·  Avg radius {radius:.2f} yd",
                center_scene,
                violet,
            )

    def add_measurement_label(self, text: str, position: QPointF, color: QColor) -> None:
        label = QGraphicsTextItem(text)
        label.setDefaultTextColor(color)
        label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        label.setPos(position + QPointF(4, -18))
        label.setZValue(30)
        self.scene.addItem(label)
        self.measurement_items.append(label)

    def guide_painter_path(self, guide: ConstructionGuide) -> QPainterPath:
        points = guide_path(guide)
        if not points:
            return QPainterPath()
        if guide.guide_type == "center" and len(points) >= 5:
            path = QPainterPath(self.field_to_scene(*points[0]))
            path.lineTo(self.field_to_scene(*points[1]))
            path.moveTo(self.field_to_scene(*points[3]))
            path.lineTo(self.field_to_scene(*points[4]))
            return path
        path = self.make_painter_path(points)
        if guide.guide_type == "grid" and len(guide.points) >= 2:
            first, second = guide.points[0], guide.points[1]
            spacing = max(0.25, float(guide.metadata.get("spacing", 1.0)))
            x = min(first[0], second[0]) + spacing
            while x < max(first[0], second[0]) - 0.0001:
                path.moveTo(self.field_to_scene(x, min(first[1], second[1])))
                path.lineTo(self.field_to_scene(x, max(first[1], second[1])))
                x += spacing
            y = min(first[1], second[1]) + spacing
            while y < max(first[1], second[1]) - 0.0001:
                path.moveTo(self.field_to_scene(min(first[0], second[0]), y))
                path.lineTo(self.field_to_scene(max(first[0], second[0]), y))
                y += spacing
        return path

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
        self._tool_value_item = None
        self.scene.clear()
        self.field_logo_item = None
        self.dot_items.clear()
        self.prop_items.clear()
        self.guide_items.clear()
        self.preview_items.clear()
        self.ghost_items.clear()
        self.path_items.clear()
        self.snap_items.clear()
        self.drill_grid_items.clear()
        self.drafting_grid_items.clear()
        scale = self.scale_factor
        palette = self.field_palette()
        surface = self.surface_definition()
        field_half_width = surface.half_width
        field_half_height = surface.half_height
        width = field_half_width * 2 * scale
        height = field_half_height * 2 * scale
        if surface.background_color:
            palette["field_fill"] = surface.background_color
            palette["endzone_fill"] = surface.background_color
        if surface.line_color:
            for key in ("field_border", "perimeter", "minor", "yard", "heavy", "hash", "tick", "restraining", "center", "label", "label_muted", "label_heavy", "bench"):
                palette[key] = surface.line_color

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
        self.refresh_field_logo()
        perimeter_pen = QPen(QColor(palette["perimeter"]), 0.08 * scale, Qt.PenStyle.DashLine)
        micro_pen = QPen(QColor(palette["micro"]), 0.018 * scale)
        minor_pen = QPen(QColor(palette["minor"]), 0.034 * scale)
        yard_pen = QPen(QColor(palette["yard"]), 0.08 * scale)
        heavy_pen = QPen(QColor(palette["heavy"]), 0.14 * scale)
        hash_pen = QPen(QColor(palette["hash"]), 0.12 * scale)
        sideline_tick_pen = QPen(QColor(palette["tick"]), 0.085 * scale)
        restraining_pen = QPen(QColor(palette["restraining"]), 0.055 * scale, Qt.PenStyle.DashLine)

        if surface.surface_type == "football":
            playing_half_width = max(5.0, field_half_width - surface.endzone_depth_yards)
            drill_grid_visible = self.drill_grid.enabled and self.drill_grid.show_overlay
            if surface.show_end_zones and surface.endzone_depth_yards > 0.01:
                add_rect(-field_half_width, -field_half_height, -playing_half_width, field_half_height, yard_pen, QColor(palette["endzone_fill"]), -23)
                add_rect(playing_half_width, -field_half_height, field_half_width, field_half_height, yard_pen, QColor(palette["endzone_fill"]), -23)
            add_rect(-field_half_width - 5, -field_half_height - 4.8, field_half_width + 5, field_half_height + 4.8, perimeter_pen, Qt.BrushStyle.NoBrush, -25)
            first_x = int(-field_half_width) + 1
            last_x = int(field_half_width)
            for yard in range(first_x, last_x):
                if yard % 5 != 0:
                    drafting_line = add_line(
                        yard,
                        -field_half_height,
                        yard,
                        field_half_height,
                        micro_pen if yard % 2 else minor_pen,
                        -19,
                    )
                    drafting_line.setVisible(not drill_grid_visible)
                    self.drafting_grid_items.append(drafting_line)
            horizontal_y = int(-field_half_height) + 1
            while horizontal_y < field_half_height:
                if abs(horizontal_y - surface.front_hash_yards) > 0.08 and abs(horizontal_y - surface.back_hash_yards) > 0.08:
                    drafting_line = add_line(
                        -field_half_width,
                        horizontal_y,
                        field_half_width,
                        horizontal_y,
                        micro_pen,
                        -20,
                    )
                    drafting_line.setVisible(not drill_grid_visible)
                    self.drafting_grid_items.append(drafting_line)
                horizontal_y += 1
            first_five = int(-field_half_width // 5) * 5
            last_five = int(field_half_width // 5) * 5
            for yard in range(first_five, last_five + 1, 5):
                if -field_half_width <= yard <= field_half_width:
                    pen = heavy_pen if abs(abs(yard) - playing_half_width) < 0.1 or abs(abs(yard) - field_half_width) < 0.1 else yard_pen
                    add_line(yard, -field_half_height, yard, field_half_height, pen, -13)
            add_line(-field_half_width, -field_half_height, field_half_width, -field_half_height, heavy_pen, -12)
            add_line(-field_half_width, field_half_height, field_half_width, field_half_height, heavy_pen, -12)
            add_line(-field_half_width, 0, field_half_width, 0, QPen(QColor(palette["center"]), 0.045 * scale, Qt.PenStyle.DashLine), -18)
            hash_half_length = 1 / 3
            sideline_tick_length = min(0.9, field_half_height / 8)
            for yard in range(int(-playing_half_width) + 1, int(playing_half_width)):
                if yard % 5 == 0:
                    continue
                if surface.hash_style != "none":
                    add_line(yard, surface.front_hash_yards - hash_half_length, yard, surface.front_hash_yards + hash_half_length, hash_pen, -10)
                    add_line(yard, surface.back_hash_yards - hash_half_length, yard, surface.back_hash_yards + hash_half_length, hash_pen, -10)
                add_line(yard, -field_half_height, yard, -field_half_height + sideline_tick_length, sideline_tick_pen, -10)
                add_line(yard, field_half_height, yard, field_half_height - sideline_tick_length, sideline_tick_pen, -10)
            if surface.hash_style != "none":
                for hash_y, label_text in ((surface.back_hash_yards, "BACK HASH"), (surface.front_hash_yards, "FRONT HASH")):
                    add_line(-playing_half_width, hash_y, playing_half_width, hash_y, QPen(QColor(palette["restraining"]), 0.045 * scale, Qt.PenStyle.DashLine), -17)
                    add_label(label_text, field_half_width + 6.5, hash_y, 7, palette["label_muted"], 0, QFont.Weight.Bold, -6)
            if surface.show_yard_numbers:
                label_y = max(1.0, field_half_height - 5.2)
                number_limit = int(playing_half_width // 10) * 10
                for yard in range(-number_limit, number_limit + 1, 10):
                    distance_to_goal = playing_half_width - abs(yard)
                    label_text = "G" if distance_to_goal < 0.1 else f"{distance_to_goal:g}"
                    add_label(label_text, yard, -label_y, 9, palette["label"], 0, QFont.Weight.Bold, -6)
                    add_label(label_text, yard, label_y, 9, palette["label"], 180, QFont.Weight.Bold, -6)
            if surface.show_end_zones and surface.endzone_depth_yards > 0.01:
                add_label("END ZONE", -(field_half_width + playing_half_width) / 2, 0, 10, palette["label"], -90, QFont.Weight.Bold, -6)
                add_label("END ZONE", (field_half_width + playing_half_width) / 2, 0, 10, palette["label"], 90, QFont.Weight.Bold, -6)
            outside_y = field_half_height + 15.8
            add_label("FRONT", 0, -outside_y, 14, palette["label_heavy"], 0, QFont.Weight.Black, -6)
            add_label("BACK", 0, outside_y, 14, palette["label_heavy"], 0, QFont.Weight.Black, -6)
            add_label("SIDE\nONE", -field_half_width - 16, 0, 12, palette["label_heavy"], 0, QFont.Weight.Black, -6)
            add_label("SIDE\nTWO", field_half_width + 16, 0, 12, palette["label_heavy"], 0, QFont.Weight.Black, -6)
            for side, y_start, y_end, label_y in (
                ("BACK", field_half_height + 3, field_half_height + 7.5, field_half_height + 5.2),
                ("FRONT", -field_half_height - 7.5, -field_half_height - 3, -field_half_height - 5.2),
            ):
                box_half_width = min(playing_half_width, 50.0)
                add_rect(-box_half_width, min(y_start, y_end), box_half_width, max(y_start, y_end), restraining_pen, Qt.BrushStyle.NoBrush, -15)
                add_label("COACHES AREA", 0, label_y, 7, palette["label_muted"], 0, QFont.Weight.Bold, -6)
        else:
            spacing = surface.grid_spacing_yards
            drill_grid_visible = self.drill_grid.enabled and self.drill_grid.show_overlay
            vertical_count = min(1000, int(surface.width_yards / spacing))
            horizontal_count = min(1000, int(surface.height_yards / spacing))
            for index in range(1, vertical_count):
                x = -field_half_width + index * spacing
                drafting_line = add_line(
                    x,
                    -field_half_height,
                    x,
                    field_half_height,
                    minor_pen if index % 5 else yard_pen,
                    -19,
                )
                drafting_line.setVisible(not drill_grid_visible)
                self.drafting_grid_items.append(drafting_line)
            for index in range(1, horizontal_count):
                y = -field_half_height + index * spacing
                drafting_line = add_line(
                    -field_half_width,
                    y,
                    field_half_width,
                    y,
                    minor_pen if index % 5 else yard_pen,
                    -19,
                )
                drafting_line.setVisible(not drill_grid_visible)
                self.drafting_grid_items.append(drafting_line)
            add_line(-field_half_width, 0, field_half_width, 0, QPen(QColor(palette["center"]), 0.06 * scale, Qt.PenStyle.DashLine), -17)
            add_line(0, -field_half_height, 0, field_half_height, QPen(QColor(palette["center"]), 0.06 * scale, Qt.PenStyle.DashLine), -17)
            add_label(surface.name.upper(), 0, field_half_height + 3.0, 9, palette["label_heavy"], 0, QFont.Weight.Bold, -6)
            add_label("FRONT", 0, -field_half_height - 3.2, 9, palette["label_heavy"], 0, QFont.Weight.Bold, -6)
            if surface.surface_type == "parade" and len(surface.route_points) >= 2:
                route_path = QPainterPath(self.field_to_scene(*surface.route_points[0]))
                for point in surface.route_points[1:]:
                    route_path.lineTo(self.field_to_scene(*point))
                route_band = QGraphicsPathItem(route_path)
                band_pen = QPen(QColor(palette["minor"]), surface.route_width_yards * scale)
                band_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                band_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                route_band.setPen(band_pen)
                route_band.setZValue(-16)
                self.scene.addItem(route_band)
                route_center = QGraphicsPathItem(route_path)
                center_pen = QPen(QColor(palette["heavy"]), 0.12 * scale, Qt.PenStyle.DashLine)
                route_center.setPen(center_pen)
                route_center.setZValue(-14)
                self.scene.addItem(route_center)
                add_label("START", *surface.route_points[0], 8, palette["label_heavy"], 0, QFont.Weight.Bold, -6)
                add_label("FINISH", *surface.route_points[-1], 8, palette["label_heavy"], 0, QFont.Weight.Bold, -6)

        self.draw_drill_grid_overlay(surface)

        margin_x = 30 * scale if surface.surface_type == "football" else 8 * scale
        margin_y = 21 * scale if surface.surface_type == "football" else 8 * scale
        self.scene.setSceneRect(QRectF(-width / 2 - margin_x, -height / 2 - margin_y, width + margin_x * 2, height + margin_y * 2))

    def field_to_scene(self, x: float, y: float) -> QPointF:
        return QPointF(x * self.scale_factor, -y * self.scale_factor)

    def scene_to_field(self, point: QPointF) -> tuple[float, float]:
        return (point.x() / self.scale_factor, -point.y() / self.scale_factor)

    @staticmethod
    def modifier_value(modifiers) -> int:
        return int(getattr(modifiers, "value", modifiers))

    def preview_handle_by_kind(self, kind: str) -> PreviewHandleItem | None:
        return next(
            (
                item
                for item in self.preview_items
                if isinstance(item, PreviewHandleItem) and item.kind == kind
            ),
            None,
        )

    def current_preview_pivot(self) -> tuple[float, float] | None:
        handle = self.preview_handle_by_kind("transform_pivot")
        return self.scene_to_field(handle.pos()) if handle is not None else None

    @staticmethod
    def manual_item_kind(item: QGraphicsItem) -> str:
        if isinstance(item, PreviewHandleItem):
            return item.kind
        if isinstance(item, PathAnchorItem):
            return "path_anchor"
        if isinstance(item, PathTangentItem):
            return "path_tangent"
        return "handle"

    def path_anchor_position(self, dot_id: str, index: int) -> tuple[float, float] | None:
        for item in self.path_items:
            if isinstance(item, PathAnchorItem) and item.dot_id == dot_id and item.index == index:
                return self.scene_to_field(item.pos())
        return None

    def selected_center(self) -> tuple[float, float]:
        positions = [
            self.scene_to_field(self.dot_items[dot_id].pos())
            for dot_id in self.selected_dot_ids()
            if dot_id in self.dot_items
        ]
        return selection_center(positions) if positions else (0.0, 0.0)

    def constrain_axis_point(
        self,
        start: tuple[float, float],
        cursor: tuple[float, float],
        modifiers: int,
    ) -> tuple[float, float]:
        if not modifiers & int(Qt.KeyboardModifier.ShiftModifier.value):
            return cursor
        delta_x = cursor[0] - start[0]
        delta_y = cursor[1] - start[1]
        if abs(delta_x) >= abs(delta_y):
            return cursor[0], start[1]
        return start[0], cursor[1]

    def constrained_manual_point(
        self,
        item: QGraphicsItem,
        cursor: tuple[float, float],
        modifiers: int,
    ) -> tuple[float, float]:
        if not modifiers & int(Qt.KeyboardModifier.ShiftModifier.value):
            return cursor
        origin: tuple[float, float] | None = None
        angular = False
        if isinstance(item, PathTangentItem):
            origin = self.path_anchor_position(item.dot_id, item.index)
            angular = True
        elif isinstance(item, PreviewHandleItem) and item.kind in {
            "rotate_angle",
            "arc_start",
            "arc_end",
            "curve_on_1",
            "curve_on_2",
        }:
            origin = self.current_preview_pivot() or self.selected_center()
            angular = True
        if angular and origin is not None:
            distance = hypot(cursor[0] - origin[0], cursor[1] - origin[1])
            angle = round(degrees(atan2(cursor[1] - origin[1], cursor[0] - origin[0])) / 15.0) * 15.0
            return (
                origin[0] + cos(radians(angle)) * distance,
                origin[1] + sin(radians(angle)) * distance,
            )
        return self.constrain_axis_point(self._manual_drag_start_field or cursor, cursor, modifiers)

    def add_smart_guide(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        label: str,
    ) -> None:
        start_scene = self.field_to_scene(*start)
        end_scene = self.field_to_scene(*end)
        guide = QGraphicsLineItem(start_scene.x(), start_scene.y(), end_scene.x(), end_scene.y())
        guide.setPen(QPen(QColor("#b057ff"), 0.12 * self.scale_factor, Qt.PenStyle.DashLine))
        guide.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        guide.setZValue(35)
        self.scene.addItem(guide)
        self.snap_items.append(guide)
        if label:
            text_item = QGraphicsTextItem(label)
            text_item.setDefaultTextColor(QColor("#f2dcff"))
            text_item.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            text_item.setPos((start_scene + end_scene) / 2 + QPointF(8, -18))
            text_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            text_item.setZValue(36)
            self.scene.addItem(text_item)
            self.snap_items.append(text_item)

    def show_handle_guides(
        self,
        start: tuple[float, float],
        cursor: tuple[float, float],
        kind: str,
        modifiers: int,
    ) -> None:
        self.clear_snap_guides()
        shift = bool(modifiers & int(Qt.KeyboardModifier.ShiftModifier.value))
        alt = bool(modifiers & int(Qt.KeyboardModifier.AltModifier.value))
        if shift:
            angle_tool = any(token in kind for token in ("rotate", "arc_", "control", "tangent"))
            self.add_smart_guide(start, cursor, "Matching angle 15°" if angle_tool else "Constrained")
        if alt:
            pivot = self.current_preview_pivot() or self._transform_pivot or self.selected_center()
            opposite = (pivot[0] * 2 - cursor[0], pivot[1] * 2 - cursor[1])
            self.add_smart_guide(opposite, cursor, "Symmetric about pivot")
        if abs(cursor[0]) <= self.snap_threshold:
            self.show_snap_guide("vertical", 0.0, clear=False, label="Field center")
        if abs(cursor[1]) <= self.snap_threshold:
            self.show_snap_guide("horizontal", 0.0, clear=False, label="Field center")
        if "tangent" in kind and not shift:
            self.add_smart_guide(start, cursor, "Tangent")

    def show_tool_value(self, event, text: str) -> None:
        self.hide_tool_value()
        value_item = QGraphicsTextItem()
        value_item.setHtml(
            '<div style="background:#171a21;color:#ffffff;border:1px solid #b057ff;'
            f'padding:4px 7px;font-weight:600;">{text}</div>'
        )
        value_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        value_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        value_item.setZValue(100)
        value_item.setPos(self.mapToScene(event.position().toPoint()) + QPointF(14, -34))
        self.scene.addItem(value_item)
        self._tool_value_item = value_item

    def hide_tool_value(self) -> None:
        if self._tool_value_item is not None and self._tool_value_item.scene() is self.scene:
            self.scene.removeItem(self._tool_value_item)
        self._tool_value_item = None

    @staticmethod
    def transform_value_text(kind: str, parameters: TransformParameters) -> str:
        if kind == "move":
            return f"Move  ΔX {parameters.offset_x:.2f}  ΔY {parameters.offset_y:.2f}"
        if kind == "rotate":
            return f"Rotate  {parameters.rotation_degrees:.1f}°"
        if kind.startswith("scale_") or kind.startswith("stretch_"):
            return f"Scale  X {parameters.scale_x:.3f}  Y {parameters.scale_y:.3f}"
        if kind == "skew_x":
            return f"Skew X  {parameters.skew_x_degrees:.1f}°"
        if kind == "skew_y":
            return f"Skew Y  {parameters.skew_y_degrees:.1f}°"
        return kind.replace("_", " ").title()

    def cancel_active_interaction(self) -> None:
        if self._gizmo_drag_start_positions:
            self.set_positions(self._gizmo_drag_start_positions)
        if self._gizmo_drag_pivot_start is not None:
            self._transform_pivot = self._gizmo_drag_pivot_start
        for prop_id, state in self._drag_start_prop_states.items():
            item = self.prop_items.get(prop_id)
            if item:
                item.apply_state(state)
                item.setPos(self.field_to_scene(float(state.get("x", 0.0)), float(state.get("y", 0.0))))
        if self._drag_start_positions:
            self.set_positions(self._drag_start_positions)
        self._active_transform_handle = None
        self._gizmo_drag_start_positions = {}
        self._gizmo_drag_pivot_start = None
        self._active_preview_handle = None
        self._active_path_anchor = None
        self._active_path_tangent = None
        self._manual_drag_item = None
        self._manual_drag_start_field = None
        self._manual_drag_last_field = None
        self._drag_start_positions = {}
        self._drag_start_prop_states = {}
        self.clear_lasso()
        self.clear_snap_guides()
        self.hide_tool_value()
        self.update_transform_gizmo()

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.active_tool != EditorTool.SELECT or self.preview_items:
                self._temporary_tool_dirty = False
                self.apply_requested.emit()
                event.accept()
                return
        if event.key() == Qt.Key.Key_Escape:
            self._temporary_tool_dirty = False
            self.cancel_active_interaction()
            self.cancel_requested.emit()
            event.accept()
            return
        arrow_keys = {
            Qt.Key.Key_Left: (-1.0, 0.0),
            Qt.Key.Key_Right: (1.0, 0.0),
            Qt.Key.Key_Up: (0.0, 1.0),
            Qt.Key.Key_Down: (0.0, -1.0),
        }
        modifiers = event.modifiers()
        if (
            self.active_tool == EditorTool.SELECT
            and self.selected_dot_ids()
            and event.key() in arrow_keys
            and not (
                modifiers & Qt.KeyboardModifier.ControlModifier
                and modifiers & Qt.KeyboardModifier.AltModifier
            )
        ):
            if modifiers & Qt.KeyboardModifier.AltModifier:
                amount = 5.0
                label = "5 yards"
            elif modifiers & Qt.KeyboardModifier.ControlModifier:
                amount = 1.0
                label = "1 yard"
            elif modifiers & Qt.KeyboardModifier.ShiftModifier:
                amount = 0.3125
                label = "half step"
            else:
                amount = 0.625
                label = "one 8-to-5 step"
            direction_x, direction_y = arrow_keys[event.key()]
            self.precision_nudge_requested.emit(direction_x * amount, direction_y * amount, label)
            event.accept()
            return
        temporary_tools = {
            Qt.Key.Key_R: EditorTool.ROTATE,
            Qt.Key.Key_S: EditorTool.SCALE,
            Qt.Key.Key_B: EditorTool.WARP,
            Qt.Key.Key_A: EditorTool.ARC,
            Qt.Key.Key_C: EditorTool.CURVE,
            Qt.Key.Key_L: EditorTool.LINE,
            Qt.Key.Key_M: EditorTool.MIRROR,
            Qt.Key.Key_V: EditorTool.LASSO,
        }
        blocked_modifiers = (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        if (
            event.key() in temporary_tools
            and not event.isAutoRepeat()
            and not modifiers & blocked_modifiers
            and self._temporary_key is None
        ):
            self._temporary_key = event.key()
            self._temporary_tool_dirty = False
            self.temporary_tool_requested.emit(temporary_tools[event.key()], True, False)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == self._temporary_key and not event.isAutoRepeat():
            tool = self.active_tool
            dirty = self._temporary_tool_dirty
            self._temporary_key = None
            self._temporary_tool_dirty = False
            self.temporary_tool_requested.emit(tool, False, dirty)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self.active_tool == EditorTool.LASSO and event.button() == Qt.MouseButton.LeftButton:
            self.start_lasso(event)
            return
        clicked_item = self.normalized_item(self.itemAt(event.position().toPoint()))
        self._active_guide_item = (
            clicked_item
            if event.button() == Qt.MouseButton.LeftButton
            and self.active_tool == EditorTool.SELECT
            and isinstance(clicked_item, ConstructionGuideItem)
            and bool(clicked_item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            else None
        )
        if self._active_guide_item is not None:
            self._guide_drag_start_scene = QPointF(self._active_guide_item.pos())
        self._active_transform_handle = (
            clicked_item
            if event.button() == Qt.MouseButton.LeftButton and isinstance(clicked_item, TransformGizmoHandleItem)
            else None
        )
        if event.button() == Qt.MouseButton.LeftButton and self._active_transform_handle is not None:
            selected_ids = self.selected_dot_ids()
            self._gizmo_drag_start_positions = {
                dot_id: self.scene_to_field(self.dot_items[dot_id].pos())
                for dot_id in selected_ids
                if dot_id in self.dot_items
            }
            self._gizmo_drag_handle_start = self.scene_to_field(self._active_transform_handle.pos())
            self._gizmo_drag_parameters = TransformParameters(pivot=self._transform_pivot)
            self._gizmo_drag_pivot_start = self._transform_pivot
            self._last_drag_modifiers = self.modifier_value(event.modifiers())
            event.accept()
            return
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
                self._manual_drag_start_field = self.scene_to_field(clicked_item.pos())
                self._manual_drag_last_field = self._manual_drag_start_field
                self._last_drag_modifiers = self.modifier_value(event.modifiers())
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
            self._manual_drag_start_field = self.scene_to_field(clicked_item.pos())
            self._manual_drag_last_field = self._manual_drag_start_field
            self._last_drag_modifiers = self.modifier_value(event.modifiers())
            self.restore_preserved_selection()
            event.accept()
            return

        if (
            self.motion_path_editing
            and event.button() == Qt.MouseButton.LeftButton
            and isinstance(clicked_item, DotItem)
        ):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                clicked_item.setSelected(not clicked_item.isSelected())
                self.selection_changed.emit(self.selected_dot_ids())
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
        if isinstance(clicked_item, PathCurveItem):
            self.direct_edit_requested.emit("path", clicked_item.dot_id)
            event.accept()
            return
        if isinstance(clicked_item, ShapeLineItem):
            self.direct_edit_requested.emit("preview", clicked_item.edit_kind)
            event.accept()
            return
        if self.active_tool == EditorTool.SELECT and isinstance(clicked_item, PropItem):
            self.direct_edit_requested.emit("prop", clicked_item.prop_id)
            event.accept()
            return
        if self.active_tool == EditorTool.SELECT and isinstance(clicked_item, ConstructionGuideItem):
            self.guide_edit_requested.emit(clicked_item.guide_id)
            event.accept()
            return
        if self.active_tool == EditorTool.SELECT and isinstance(clicked_item, DotItem):
            if clicked_item.isSelected() and len(self.selected_dot_ids()) > 1:
                self.direct_edit_requested.emit("formation", clicked_item.dot_id)
            else:
                self.dot_edit_requested.emit(clicked_item.dot_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._active_transform_handle is not None:
            cursor = self.scene_to_field(self.mapToScene(event.position().toPoint()))
            modifiers = self.modifier_value(event.modifiers())
            self._last_drag_modifiers = modifiers
            if self._active_transform_handle.kind == "pivot":
                cursor = self.constrain_axis_point(self._gizmo_drag_handle_start, cursor, modifiers)
                self._active_transform_handle.setPos(self.field_to_scene(*cursor))
                self._transform_pivot = cursor
                self.show_handle_guides(self._gizmo_drag_handle_start, cursor, "pivot", modifiers)
                self.show_tool_value(event, f"Pivot  X {cursor[0]:.2f}  Y {cursor[1]:.2f}")
            else:
                parameters = self.transform_parameters_for_gizmo(
                    self._active_transform_handle.kind,
                    cursor,
                    modifiers,
                )
                transformed = transform_positions(self._gizmo_drag_start_positions, parameters)
                if self.drill_grid.enabled:
                    transformed = self.snap_drill_grid_positions(transformed)
                for dot_id, position in transformed.items():
                    item = self.dot_items.get(dot_id)
                    if item:
                        item.setPos(self.field_to_scene(*position))
                self.dots_drag_preview.emit(transformed)
                self._active_transform_handle.setPos(self.mapToScene(event.position().toPoint()))
                self._gizmo_drag_parameters = parameters
                self.show_handle_guides(
                    self._gizmo_drag_handle_start,
                    cursor,
                    self._active_transform_handle.kind,
                    modifiers,
                )
                self.show_tool_value(event, self.transform_value_text(self._active_transform_handle.kind, parameters))
            event.accept()
            return
        if self._manual_drag_item is not None:
            item = self._manual_drag_item
            modifiers = self.modifier_value(event.modifiers())
            self._last_drag_modifiers = modifiers
            cursor = self.scene_to_field(self.mapToScene(event.position().toPoint()))
            cursor = self.constrained_manual_point(item, cursor, modifiers)
            if self.drill_grid.enabled:
                cursor = self.snap_drill_grid_point(cursor)
            self._manual_drag_last_field = cursor
            item.setPos(self.field_to_scene(*cursor))
            kind = self.manual_item_kind(item)
            start = self._manual_drag_start_field or cursor
            self.show_handle_guides(start, cursor, kind, modifiers)
            if isinstance(item, PreviewHandleItem):
                self._temporary_tool_dirty = True
                self.preview_handle_dragged.emit(item.kind, cursor[0], cursor[1], modifiers)
                replacement = self.preview_handle_by_kind(item.kind)
                if replacement is not None:
                    self._active_preview_handle = replacement
                    self._manual_drag_item = replacement
            value_text = (
                self._tool_value_provider(kind, cursor[0], cursor[1], modifiers)
                if self._tool_value_provider
                else f"{self.preview_handle_label(kind).title()}  X {cursor[0]:.2f}  Y {cursor[1]:.2f}"
            )
            self.show_tool_value(event, value_text)
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
            and (self.snap_enabled or self.drill_grid.enabled)
            and self._drag_start_positions
        ):
            self.apply_snap_to_selected()
        if self.active_tool == EditorTool.SELECT and self._drag_start_positions:
            self.dots_drag_preview.emit(
                {
                    dot_id: self.scene_to_field(self.dot_items[dot_id].pos())
                    for dot_id in self._drag_start_positions
                    if dot_id in self.dot_items
                }
            )

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = None
            self.unsetCursor()
            return
        if event.button() == Qt.MouseButton.RightButton:
            event.accept()
            return
        if self._active_guide_item is not None:
            item = self._active_guide_item
            super().mouseReleaseEvent(event)
            delta_scene = item.pos() - self._guide_drag_start_scene
            if abs(delta_scene.x()) > 0.001 or abs(delta_scene.y()) > 0.001:
                self.guide_moved.emit(
                    item.guide_id,
                    delta_scene.x() / self.scale_factor,
                    -delta_scene.y() / self.scale_factor,
                )
            self._active_guide_item = None
            event.accept()
            return
        if self._active_transform_handle is not None:
            handle = self._active_transform_handle
            before = dict(self._gizmo_drag_start_positions)
            if handle.kind != "pivot":
                after = {
                    dot_id: self.scene_to_field(self.dot_items[dot_id].pos())
                    for dot_id in before
                    if dot_id in self.dot_items
                }
                descriptor = {
                    "kind": handle.kind,
                    "offset_x": self._gizmo_drag_parameters.offset_x,
                    "offset_y": self._gizmo_drag_parameters.offset_y,
                    "rotation_degrees": self._gizmo_drag_parameters.rotation_degrees,
                    "scale_x": self._gizmo_drag_parameters.scale_x,
                    "scale_y": self._gizmo_drag_parameters.scale_y,
                    "skew_x_degrees": self._gizmo_drag_parameters.skew_x_degrees,
                    "skew_y_degrees": self._gizmo_drag_parameters.skew_y_degrees,
                    "pivot": self._gizmo_drag_parameters.pivot,
                }
                if before != after:
                    self.transform_gizmo_applied.emit(before, after, descriptor)
                if handle.kind == "move" and self._transform_pivot is not None:
                    self._transform_pivot = (
                        self._transform_pivot[0] + self._gizmo_drag_parameters.offset_x,
                        self._transform_pivot[1] + self._gizmo_drag_parameters.offset_y,
                    )
            self._active_transform_handle = None
            self._gizmo_drag_start_positions = {}
            self._gizmo_drag_pivot_start = None
            self.hide_tool_value()
            self.clear_snap_guides()
            self.update_transform_gizmo()
            self.selection_changed.emit(self.selected_dot_ids())
            event.accept()
            return
        if self._active_preview_handle is not None:
            handle = self._active_preview_handle
            x, y = self._manual_drag_last_field or self.scene_to_field(handle.pos())
            self.preview_handle_moved.emit(handle.kind, x, y)
            self.preview_handle_moved_detailed.emit(handle.kind, x, y, self._last_drag_modifiers)
            self._active_preview_handle = None
            self._manual_drag_item = None
            self._manual_drag_start_field = None
            self._manual_drag_last_field = None
            self.hide_tool_value()
            self.clear_snap_guides()
            self.restore_preserved_selection()
            event.accept()
            return
        if self._active_path_anchor is not None:
            handle = self._active_path_anchor
            x, y = self.scene_to_field(handle.pos())
            self.path_anchor_moved.emit(handle.dot_id, handle.index, x, y)
            self.path_anchor_moved_detailed.emit(
                handle.dot_id,
                handle.index,
                x,
                y,
                self._last_drag_modifiers,
            )
            self._active_path_anchor = None
            self._manual_drag_item = None
            self._manual_drag_start_field = None
            self._manual_drag_last_field = None
            self.hide_tool_value()
            self.clear_snap_guides()
            self.restore_preserved_selection()
            event.accept()
            return
        if self._active_path_tangent is not None:
            handle = self._active_path_tangent
            x, y = self.scene_to_field(handle.pos())
            self.path_tangent_moved.emit(handle.dot_id, handle.index, handle.control_name, x, y)
            self.path_tangent_moved_detailed.emit(
                handle.dot_id,
                handle.index,
                handle.control_name,
                x,
                y,
                self._last_drag_modifiers,
            )
            self._active_path_tangent = None
            self._manual_drag_item = None
            self._manual_drag_start_field = None
            self._manual_drag_last_field = None
            self.hide_tool_value()
            self.clear_snap_guides()
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
        if (self.snap_enabled or self.drill_grid.enabled) and self._drag_start_positions:
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
        if moved_positions:
            self._transform_pivot = None
        self.update_transform_gizmo()
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

        if self.drill_grid.enabled:
            current = {
                item.dot_id: self.scene_to_field(item.pos())
                for item in selected_items
            }
            snapped = self.snap_drill_grid_positions(current)
            for dot_id, position in snapped.items():
                item = self.dot_items.get(dot_id)
                if item is not None:
                    item.setPos(self.field_to_scene(*position))
            self.clear_snap_guides()
            guide_position = next(iter(snapped.values()))
            self.show_snap_guide(
                "vertical",
                guide_position[0],
                clear=False,
                label=f"{self.drill_grid.preset_label} drill grid",
            )
            self.show_snap_guide("horizontal", guide_position[1], clear=False)
            return

        selected_ids = {item.dot_id for item in selected_items}
        candidate_x: list[tuple[float, str]] = [(float(yard), "Yard line") for yard in range(-50, 55, 5)]
        surface = self.project.surface if self.project is not None else None
        candidate_y: list[tuple[float, str]] = [(0.0, "Field center")]
        if surface is not None and surface.surface_type == "football" and surface.hash_style != "none":
            candidate_y.extend(
                [
                    (float(surface.front_hash_yards), "Front hash"),
                    (float(surface.back_hash_yards), "Back hash"),
                ]
            )
        other_x: list[float] = []
        other_y: list[float] = []
        for dot_id, item in self.dot_items.items():
            if dot_id in selected_ids or not item.isVisible():
                continue
            x, y = self.scene_to_field(item.pos())
            candidate_x.append((x, "Align centers"))
            candidate_y.append((y, "Align centers"))
            other_x.append(x)
            other_y.append(y)

        for values, candidates in ((other_x, candidate_x), (other_y, candidate_y)):
            unique_values = sorted(set(round(value, 4) for value in values))
            for left, right in zip(unique_values, unique_values[1:]):
                candidates.append(((left + right) / 2, "Equal distance"))

        best_x: tuple[float, float, str] | None = None
        best_y: tuple[float, float, str] | None = None
        selected_points = [self.scene_to_field(item.pos()) for item in selected_items]
        selected_points.append(selection_center(selected_points))
        for x, y in selected_points:
            for candidate, label in candidate_x:
                delta = candidate - x
                if abs(delta) < 0.001:
                    continue
                if abs(delta) <= self.snap_threshold and (
                    best_x is None or abs(delta) < abs(best_x[0])
                ):
                    best_x = (delta, candidate, label)
            for candidate, label in candidate_y:
                delta = candidate - y
                if abs(delta) < 0.001:
                    continue
                if abs(delta) <= self.snap_threshold and (
                    best_y is None or abs(delta) < abs(best_y[0])
                ):
                    best_y = (delta, candidate, label)

        if best_x is None and best_y is None:
            self.clear_snap_guides()
            return

        delta_x = best_x[0] if best_x is not None else 0.0
        delta_y = best_y[0] if best_y is not None else 0.0
        for item in selected_items:
            x, y = self.scene_to_field(item.pos())
            item.setPos(self.field_to_scene(x + delta_x, y + delta_y))
        self.clear_snap_guides()
        if best_x is not None:
            self.show_snap_guide("vertical", best_x[1], clear=False, label=best_x[2])
        if best_y is not None:
            self.show_snap_guide("horizontal", best_y[1], clear=False, label=best_y[2])

    def show_snap_guide(
        self,
        orientation: str,
        value: float,
        *,
        clear: bool = True,
        label: str = "",
    ) -> None:
        if clear:
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
        if label:
            label_item = QGraphicsTextItem(label)
            label_item.setDefaultTextColor(QColor("#f2dcff"))
            label_item.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            label_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            label_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            label_item.setPos(
                QPointF(x + 8, -18) if orientation == "vertical" else QPointF(8, y - 18)
            )
            label_item.setZValue(31)
            self.scene.addItem(label_item)
            self.snap_items.append(label_item)

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
            action = menu.addAction("Select Same Instrument")
            actions.append(("Select Same Instrument", action))
            action = menu.addAction("Select Same Section")
            actions.append(("Select Same Section", action))
        if selected_dot_count:
            if selected_dot_count > 1:
                action = menu.addAction("Toggle Transform Handles")
                actions.append(("Toggle Transform Handles", action))
            for name in (
                "Group Motion Ribbon",
                "Edit Group Path Handles",
                "Formation Morph",
                "Polar / Linear Array",
                "Parallel Form Generator",
                "Rank / File Builder",
                "Create Live Symmetry",
                "Alternating Selection",
                "Toggle Measurements",
                "Continuity Designer",
                "Guided Destination Repair",
                "Section-Aware Form Fit",
                "Copy With Property Paintbrush",
                "Paint Copied Properties",
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
        if self.selected_guide_ids():
            for name in ("Edit Construction Guides", "CAD Path Toolkit"):
                action = menu.addAction(name)
                actions.append((name, action))
            menu.addSeparator()
        else:
            action = menu.addAction("Construction Guides")
            actions.append(("Construction Guides", action))
        action = menu.addAction("Reference / Annotation Layer")
        actions.append(("Reference / Annotation Layer", action))
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
