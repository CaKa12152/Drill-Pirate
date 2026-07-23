from __future__ import annotations

import json
import re
import shutil
import tempfile
import traceback
import base64
import hashlib
from time import perf_counter
from uuid import uuid4
from copy import deepcopy
from dataclasses import dataclass
from math import atan2, cos, degrees, pi, radians, sin
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QByteArray, QElapsedTimer, QEvent, QPoint, QPointF, QRectF, QSettings, QSize, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QUndoCommand, QUndoStack
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
try:
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
except Exception:  # pragma: no cover - optional Qt module
    QOpenGLWidget = None  # type: ignore[assignment]
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QGraphicsView,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QApplication,
    QPushButton,
    QPlainTextEdit,
    QProgressDialog,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QToolBar,
    QWidget,
)

from drill_writer.core.analysis import build_conflict_timeline, detect_path_warnings, segments_intersect
from drill_writer.core.accelerators import (
    alternating_selection,
    array_target_points,
    assign_targets_minimum_cost,
    create_live_symmetry_record,
    expand_live_symmetry_changes,
    parallel_form_target_points,
    rank_file_target_points,
    spatial_id_order,
)
from drill_writer.core.animation import distance, dot_facing_at_set, interpolate_dot_facings, interpolate_project, interpolate_props, sample_transition_path
from drill_writer.core.assignment import ordered_targets
from drill_writer.core.constraints import (
    make_arc_metadata,
    make_block_metadata,
    make_relative_metadata,
    solve_constraints,
)
from drill_writer.core.cad_paths import (
    cad_extend,
    cad_fillet,
    cad_join,
    cad_offset,
    cad_reverse,
    cad_simplify,
    cad_smooth,
    cad_split,
    cad_trim,
    path_to_bezier_nodes,
)
from drill_writer.core.design_tools import (
    MorphOptions,
    create_motion_ribbon,
    guide_path,
    motion_ribbon_by_id,
    plan_formation_morph,
    plan_motion_ribbon,
    sample_motion_ribbon,
)
from drill_writer.core.drill_grid import DrillGridSettings, snap_position_mapping, snap_positions_to_grid
from drill_writer.core.follow_leader import (
    FollowLeaderOptions,
    FollowLeaderPlan,
    plan_follow_leader,
    split_follow_leader_groups,
)
from drill_writer.core.coordinates import STEPS_PER_YARD, format_surface_coordinate
from drill_writer.core.models import AudioVersion, ConstructionGuide, Dot, DotConstraint, DrillProject, DrillSet, Marker, MotionRibbon, MovementStyle, Prop, TimingEvent, Transition, prop_default_state
from drill_writer.core.large_show import (
    cleanup_formation,
    expand_linked_position_changes,
    generate_hierarchical_groups,
    locked_group_dot_ids,
    merge_roster,
    swap_performers,
    transfer_project_content,
    variation_positions,
    workflow_records as large_show_workflow_records,
)
from drill_writer.core.diagnostics import export_bug_report_bundle
from drill_writer.core.user_errors import actionable_error_message
from drill_writer.core.project_io import (
    list_project_backups,
    load_project,
    project_library_dir,
    restore_project_backup,
    safe_folder_name,
    save_project,
)
from drill_writer.core.audio_recovery import (
    AudioRecoveryPolicy,
    is_recoverable_audio_device_error,
    recommended_audio_resume_delay_ms,
)
from drill_writer.core.playback import FrameScheduler, PlaybackFrameCache, PlaybackQuality
from drill_writer.core.svg_import import load_svg_contours
from drill_writer.core.specialized_design import surface_contains_point
from drill_writer.core.timing import (
    active_audio_version,
    audio_ms_for_set_count,
    describe_timing_event,
    playback_bounds_for_set,
    set_active_audio_version,
    set_count_for_audio_ms,
    set_index_for_count,
)
from drill_writer.core.workflow import (
    TransformParameters,
    assignment_for_mode,
    collision_aware_assignment_for_project,
    generate_sets_from_markers,
    project_assignment_quality,
    ripple_set_indices,
    selection_center,
    transform_positions,
    transition_candidates,
)
from drill_writer.core.tools import (
    arc_positions,
    block_positions,
    bezier_curve_positions,
    circle_positions,
    centered_positions,
    cubic_bezier_point,
    curve_positions,
    ellipse_positions,
    elliptical_arc_path,
    elliptical_arc_positions,
    freeform_curve_positions,
    line_positions,
    mirror_positions,
    polygon_positions,
    positions_along_path,
    positions_along_paths,
    positions_along_paths_spaced,
    rectangle_positions,
    relax_close_positions,
    rotate_positions,
    sampled_shape_path,
    sampled_cubic_bezier_path,
    sampled_spline_path,
    scatter_positions,
    scaled_positions_to_size,
    solid_paths_positions,
    spiral_positions,
    star_positions,
    triangle_positions,
    warped_positions,
    distance,
)
from drill_writer.resources import app_icon_path
from drill_writer.export.exporters import (
    ExportCancelled,
    Mp4ExportOptions,
    PrintTemplateOptions,
    encode_mp4_frames,
    export_coordinate_csv,
    export_coordinate_summary_pdf,
    export_dot_book_pdf,
    export_drill_sheet_pdf,
    export_project_zip,
    export_staff_packet_pdf,
    render_mp4_frames,
)
from drill_writer.ui.pdf_preview import PdfPreviewDialog
from drill_writer.ui.pdf_layout_designer import PdfLayoutDesignerDialog
from drill_writer.ui.audio_devices import (
    AUDIO_OUTPUT_DEVICE_SETTING,
    DEFAULT_AUDIO_OUTPUT_DEVICE_ID,
    audio_device_id,
    audio_output_devices,
    audio_output_for_id,
    audio_output_label_for_id,
    normalize_audio_output_device_id,
)
from drill_writer.ui.advanced_design_tools import (
    CadPathDialog,
    ConstructionGuidesDialog,
    ContinuityDesignerDialog,
    FormationMorphDialog,
    MotionRibbonDialog,
)
from drill_writer.ui.design_accelerators import (
    AcceleratorPanel,
    AlternatingSelectionDialog,
    ArrayDialog,
    LiveSymmetryDialog,
    ParallelFormDialog,
    RankFileDialog,
    ReferenceAnnotationsDialog,
    SymmetryManagerDialog,
)
from drill_writer.ui.drill_grid import DrillGridDialog
from drill_writer.ui.appearance import draw_dot_symbol, scaled_field_dot_metrics
from drill_writer.ui.music_design import MusicDesignPanel, MusicDesignStudioDialog
from drill_writer.ui.specialized_design import ChoreographyTimelineWidget, SpecializedDesignPanel, SpecializedDesignStudioDialog
from drill_writer.ui.surface_preview import draw_surface_preview, field_to_rect, rect_to_field, size_to_rect
from drill_writer.ui.field_view import EditorTool, FieldView
from drill_writer.ui.field_logo import field_logo_enabled
from drill_writer.ui.prop_designer import CreatedPropDesign, PropDesignerDialog
from drill_writer.ui.theme import theme_tokens
from drill_writer.ui.waveform import WaveformWidget
from drill_writer.ui.workflow_tools import (
    BeatSetGeneratorDialog,
    MacroReplayDialog,
    PropertyBrushDialog,
    SmartTransitionDialog,
    TransitionTimelineWidget,
)
from drill_writer.ui.large_show_tools import (
    CleanupDialog,
    ConflictHeatmapWidget,
    ConflictHeatmapWorker,
    FormationVariationsDialog,
    GroupManagerDialog,
    PerformerReplacementDialog,
    RosterImportDialog,
    SetComparisonDialog,
)


@dataclass(slots=True)
class FormToolContext:
    window: "MainWindow"
    project: DrillProject
    set_index: int
    dot_ids: list[str]
    positions: list[tuple[float, float]]
    center: tuple[float, float]
    bounds_width: float
    bounds_height: float
    settings: dict[str, Any]


@dataclass(slots=True)
class PluginFormTool:
    plugin_id: str
    tool_id: str
    name: str
    callback: Callable[[FormToolContext], Any]
    min_selected: int
    settings: list[dict[str, Any]]


class Mp4EncodeThread(QThread):
    progress_changed = Signal(str, int, int)
    export_completed = Signal()
    export_cancelled = Signal()
    export_failed = Signal(str)

    def __init__(
        self,
        frames_dir: Path,
        output_path: Path,
        frame_result: Any,
        ffmpeg_path: str,
        options: Mp4ExportOptions,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.frames_dir = frames_dir
        self.output_path = output_path
        self.frame_result = frame_result
        self.ffmpeg_path = ffmpeg_path
        self.options = options
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:  # type: ignore[override]
        try:
            encode_mp4_frames(
                self.frames_dir,
                self.output_path,
                self.frame_result,
                ffmpeg_path=self.ffmpeg_path,
                options=self.options,
                progress_callback=self.progress_changed.emit,
                cancel_callback=lambda: self._cancel_requested,
            )
        except ExportCancelled:
            self.export_cancelled.emit()
        except Exception as exc:
            self.export_failed.emit(str(exc))
        else:
            self.export_completed.emit()


def refresh_ancestor_layouts(widget: QWidget) -> None:
    current: QWidget | None = widget
    scroll_area: QScrollArea | None = None
    for _depth in range(10):
        if current is None:
            break
        if isinstance(current, QScrollArea):
            scroll_area = current
        layout = current.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        current.updateGeometry()
        current = current.parentWidget()
    if scroll_area is not None and scroll_area.widget() is not None:
        content = scroll_area.widget()
        content.updateGeometry()
        scroll_area.updateGeometry()
        if not scroll_area.widgetResizable():
            minimum = content.minimumSizeHint()
            content.resize(
                max(1, scroll_area.viewport().width()),
                max(scroll_area.viewport().height(), minimum.height()),
            )


class ResponsivePanelWidget(QWidget):
    """Expose the live child-layout size to a wrapping QScrollArea."""

    def sizeHint(self) -> QSize:  # type: ignore[override]
        layout = self.layout()
        return layout.sizeHint() if layout is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:  # type: ignore[override]
        layout = self.layout()
        return layout.minimumSize() if layout is not None else super().minimumSizeHint()


class CommitPlainTextEdit(QPlainTextEdit):
    editingStarted = Signal()
    editingFinished = Signal()

    def focusInEvent(self, event) -> None:  # type: ignore[override]
        super().focusInEvent(event)
        self.editingStarted.emit()

    def focusOutEvent(self, event) -> None:  # type: ignore[override]
        super().focusOutEvent(event)
        self.editingFinished.emit()


class AdaptivePanelScrollArea(QScrollArea):
    """Keep side-panel content full-width and scroll vertically without compression."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.form_wrap_threshold = 300
        self._forms_wrapped: bool | None = None
        self._content_resize_timer = QTimer(self)
        self._content_resize_timer.setSingleShot(True)
        self._content_resize_timer.timeout.connect(self.refresh_content_size)
        self.verticalScrollBar().rangeChanged.connect(self.schedule_content_resize)

    def schedule_content_resize(self, *_args) -> None:
        self._content_resize_timer.start(0)

    def refresh_content_size(self) -> None:
        content = self.widget()
        if content is None:
            return
        wrap_all = self.viewport().width() < self.form_wrap_threshold
        if wrap_all != self._forms_wrapped:
            self._forms_wrapped = wrap_all
            policy = (
                QFormLayout.RowWrapPolicy.WrapAllRows
                if wrap_all
                else QFormLayout.RowWrapPolicy.WrapLongRows
            )
            for form_layout in content.findChildren(QFormLayout):
                form_layout.setRowWrapPolicy(policy)
                form_layout.invalidate()
            content_layout = content.layout()
            if content_layout is not None:
                content_layout.invalidate()
                content_layout.activate()
            content.updateGeometry()
        content.updateGeometry()
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.schedule_content_resize()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.schedule_content_resize()


class CurrentPageStack(QStackedWidget):
    def sizeHint(self) -> QSize:  # type: ignore[override]
        current = self.currentWidget()
        if current is None:
            return QSize(220, 320)
        preferred = current.sizeHint()
        minimum = current.minimumSizeHint()
        return QSize(max(180, min(280, preferred.width())), max(320, minimum.height()))

    def minimumSizeHint(self) -> QSize:  # type: ignore[override]
        current = self.currentWidget()
        if current is None:
            return QSize(180, 120)
        hint = current.minimumSizeHint()
        return QSize(180, max(120, hint.height()))

    def hasHeightForWidth(self) -> bool:  # type: ignore[override]
        current = self.currentWidget()
        return bool(current and current.hasHeightForWidth())

    def heightForWidth(self, width: int) -> int:  # type: ignore[override]
        current = self.currentWidget()
        if current is None:
            return 320
        if current.hasHeightForWidth():
            return max(current.minimumSizeHint().height(), current.heightForWidth(max(1, width)))
        return max(current.minimumSizeHint().height(), current.sizeHint().height())

    def setCurrentIndex(self, index: int) -> None:  # type: ignore[override]
        super().setCurrentIndex(index)
        current = self.currentWidget()
        if current is not None:
            current.updateGeometry()
        refresh_ancestor_layouts(self)


class CompactTabWidget(QTabWidget):
    """Keep dock tabs responsive instead of sizing to their widest hidden page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.currentChanged.connect(self.refresh_current_page_geometry)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        current = self.currentWidget()
        if current is None:
            return QSize(260, 240)
        preferred = current.sizeHint()
        minimum = current.minimumSizeHint()
        tab_height = self.tabBar().sizeHint().height()
        return QSize(max(220, min(360, preferred.width())), max(240, minimum.height() + tab_height))

    def minimumSizeHint(self) -> QSize:  # type: ignore[override]
        current = self.currentWidget()
        if current is None:
            return QSize(200, 120)
        hint = current.minimumSizeHint()
        return QSize(200, max(120, hint.height() + self.tabBar().minimumSizeHint().height()))

    def hasHeightForWidth(self) -> bool:  # type: ignore[override]
        current = self.currentWidget()
        return bool(current and current.hasHeightForWidth())

    def heightForWidth(self, width: int) -> int:  # type: ignore[override]
        current = self.currentWidget()
        if current is None:
            return 240
        page_height = (
            current.heightForWidth(max(1, width))
            if current.hasHeightForWidth()
            else max(current.minimumSizeHint().height(), current.sizeHint().height())
        )
        chrome_height = self.tabBar().sizeHint().height() + 18
        return max(self.minimumSizeHint().height(), page_height + chrome_height)

    def refresh_current_page_geometry(self, _index: int = -1) -> None:
        current = self.currentWidget()
        if current is not None:
            current.updateGeometry()
        refresh_ancestor_layouts(self)
        QTimer.singleShot(0, lambda: refresh_ancestor_layouts(self))


class PanelPageSwitcher(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PanelPageSwitcher")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.selector = QComboBox()
        self.selector.setObjectName("PanelPageSelector")
        self.selector.setToolTip("Choose which tool panel is shown.")
        self.stack = CurrentPageStack()
        self.selector.currentIndexChanged.connect(self._set_current_index)
        layout.addWidget(self.selector)
        layout.addWidget(self.stack, 1)

    def addTab(self, widget: QWidget, label: str) -> int:
        index = self.stack.addWidget(widget)
        self.selector.addItem(label)
        return index

    def count(self) -> int:
        return self.stack.count()

    def widget(self, index: int) -> QWidget | None:
        return self.stack.widget(index)

    def indexOf(self, widget: QWidget) -> int:
        return self.stack.indexOf(widget)

    def currentIndex(self) -> int:
        return self.stack.currentIndex()

    def currentWidget(self) -> QWidget | None:
        return self.stack.currentWidget()

    def setCurrentIndex(self, index: int) -> None:
        if not 0 <= index < self.count():
            return
        self.selector.setCurrentIndex(index)
        self.stack.setCurrentIndex(index)

    def setCurrentWidget(self, widget: QWidget) -> None:
        self.setCurrentIndex(self.indexOf(widget))

    def tabText(self, index: int) -> str:
        return self.selector.itemText(index)

    def setPageOrder(self, pages: list[tuple[QWidget, str]]) -> None:
        current = self.currentWidget()
        self.selector.blockSignals(True)
        self.selector.clear()
        for index, (widget, label) in enumerate(pages):
            existing_index = self.stack.indexOf(widget)
            if existing_index >= 0:
                self.stack.removeWidget(widget)
            self.stack.insertWidget(index, widget)
            self.selector.addItem(label)
        target_index = self.stack.indexOf(current) if current is not None else 0
        target_index = max(0, target_index)
        self.selector.setCurrentIndex(target_index)
        self.stack.setCurrentIndex(target_index)
        self.selector.blockSignals(False)
        refresh_ancestor_layouts(self)

    def _set_current_index(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.stack.updateGeometry()
        refresh_ancestor_layouts(self)
        QTimer.singleShot(0, lambda: refresh_ancestor_layouts(self))
        self.currentChanged.emit(index)


class AnalysisWorker(QThread):
    analysis_completed = Signal(list, list)
    analysis_failed = Signal(str)

    def __init__(
        self,
        project: DrillProject,
        min_spacing: float,
        max_yards_per_count: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.project = deepcopy(project)
        self.min_spacing = min_spacing
        self.max_yards_per_count = max_yards_per_count

    def run(self) -> None:  # type: ignore[override]
        try:
            all_warnings = []
            timeline_entries = []
            for set_index in range(len(self.project.sets)):
                if self.isInterruptionRequested():
                    return
                all_warnings.extend(
                    detect_path_warnings(
                        self.project,
                        set_index,
                        min_spacing=self.min_spacing,
                        max_yards_per_count=self.max_yards_per_count,
                        cancel_callback=self.isInterruptionRequested,
                    )
                )
                if self.isInterruptionRequested():
                    return
                timeline_entries.extend(
                    build_conflict_timeline(
                        self.project,
                        set_index,
                        min_spacing=self.min_spacing,
                        max_yards_per_count=self.max_yards_per_count,
                        fast_crossings=True,
                        cancel_callback=self.isInterruptionRequested,
                    )
                )
            self.analysis_completed.emit(all_warnings, timeline_entries)
        except Exception as exc:
            self.analysis_failed.emit(str(exc))


class RadialToolMenu(QWidget):
    def __init__(self, window: "MainWindow", tools: list[EditorTool]) -> None:
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.window = window
        self.tools = tools
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(320, 320)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.buttons: list[QPushButton] = []
        tokens = theme_tokens(str(window.settings.value("appearance/theme", "dark")), window.settings)
        button_style = f"""
QPushButton {{
    background: {tokens["button_color"]};
    color: {tokens["text_color"]};
    border: 1px solid {tokens["accent_color"]};
    border-radius: 9px;
    padding: 4px 6px;
}}
QPushButton:hover {{
    background: {tokens["accent_color"]};
    color: {tokens["background_color"]};
}}
"""
        center = QPoint(self.width() // 2, self.height() // 2)
        radius = 118
        for index, tool in enumerate(tools):
            button = QPushButton(self.tool_label(tool), self)
            button.setFixedSize(76, 34)
            button.setStyleSheet(button_style)
            angle = -pi / 2 + (2 * pi * index / max(1, len(tools)))
            button.move(
                int(center.x() + cos(angle) * radius - button.width() / 2),
                int(center.y() + sin(angle) * radius - button.height() / 2),
            )
            button.clicked.connect(lambda _checked=False, selected=tool: self.choose_tool(selected))
            self.buttons.append(button)

    def tool_label(self, tool: EditorTool) -> str:
        labels = {
            EditorTool.SELECT: "Select",
            EditorTool.LASSO: "Lasso",
            EditorTool.LINE: "Line",
            EditorTool.CURVE: "Curve",
            EditorTool.FREE_CURVE: "Free Curve",
            EditorTool.ARC: "Arc",
            EditorTool.CIRCLE: "Circle",
            EditorTool.RECTANGLE: "Rect",
            EditorTool.SVG_SHAPE: "SVG",
            EditorTool.SCALE: "Scale",
            EditorTool.WARP: "Warp",
            EditorTool.ROTATE: "Rotate",
            EditorTool.MIRROR: "Mirror",
            EditorTool.SHAPE_LINE: "Shape",
            EditorTool.SCATTER: "Scatter",
        }
        return labels.get(tool, tool.value.replace("_", " ").title())

    def choose_tool(self, tool: EditorTool) -> None:
        self.window.set_tool(tool)
        self.close()

    def show_at(self, global_pos: QPoint) -> None:
        self.move(global_pos - QPoint(self.width() // 2, self.height() // 2))
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        tokens = theme_tokens(str(self.window.settings.value("appearance/theme", "dark")), self.window.settings)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(tokens["accent_color"]), 1.4))
        painter.setBrush(QColor(tokens["surface_color"]))
        outer = QRectF(8, 8, self.width() - 16, self.height() - 16)
        painter.drawEllipse(outer)
        painter.setPen(QPen(QColor(tokens["border_color"]), 1.0))
        painter.drawEllipse(QRectF(102, 102, 116, 116))
        painter.setPen(QColor(tokens["text_color"]))
        painter.drawText(QRectF(112, 136, 96, 48), Qt.AlignmentFlag.AlignCenter, "Tools\nQ / Right-click")
        painter.end()


TOOL_HINTS: dict[EditorTool, str] = {
    EditorTool.SELECT: "Select, drag, shift-click, or box-select marchers and props.",
    EditorTool.LINE: "Select marchers, drag the red handles, then Apply to distribute them on a line.",
    EditorTool.CURVE: "Select a line of marchers, drag the curve handle, then Apply to bend the form.",
    EditorTool.FREE_CURVE: "Build any smooth curved form with draggable anchors and even spacing along the curve.",
    EditorTool.ARC: "Use center/radius handles to shape an arc before applying.",
    EditorTool.CIRCLE: "Set size and rotation, preview the circle, then Apply.",
    EditorTool.ELLIPSE: "Preview an oval/ellipse; choose Hollow or Solid before applying.",
    EditorTool.RECTANGLE: "Set width/height and preview a rectangle around the selected group.",
    EditorTool.TRIANGLE: "Create a triangle outline or filled triangle from the selected marchers.",
    EditorTool.DIAMOND: "Create a diamond outline or filled diamond from the selected marchers.",
    EditorTool.POLYGON: "Create configurable regular polygons with hollow or solid placement.",
    EditorTool.STAR: "Create star forms with configurable point count and hollow or solid placement.",
    EditorTool.SPIRAL: "Adjust turns and radius to preview a spiral form.",
    EditorTool.BLOCK: "Create block/grid spacing from the current selection.",
    EditorTool.SCALE: "Scale the selected form without changing its overall shape.",
    EditorTool.WARP: "Bend an existing selected form with multiple draggable wave handles.",
    EditorTool.ROTATE: "Rotate the selected form with live preview and a draggable angle handle.",
    EditorTool.SVG_SHAPE: "Import an SVG shape, adjust handles, then map selected marchers onto it.",
    EditorTool.LASSO: "Draw around marchers to select; hold Shift to add to selection.",
    EditorTool.SCATTER: "Create organized scatter shapes with minimum spacing.",
    EditorTool.MIRROR: "Drag the mirror axis handle to reflect selected marchers.",
    EditorTool.SHAPE_LINE: "Right-click selected marchers to make anchors; drag anchors to shape the line.",
}


class DraggableFieldHud(QFrame):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window.field.viewport())
        self.window = window
        self._drag_start_global: QPoint | None = None
        self._drag_start_pos: QPoint | None = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip(
            "Tool HUD. Drag to move it, double-click to reset its position, or hide it from View > Show Tool HUD."
        )

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_global = event.globalPosition().toPoint()
            self._drag_start_pos = self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_start_global is not None and self._drag_start_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_start_global
            self.window.move_field_hud_to(self._drag_start_pos + delta, persist=False)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_start_global is not None:
            self.window.save_field_hud_position()
            self._drag_start_global = None
            self._drag_start_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        self.window.reset_field_hud_position()
        event.accept()


class FieldMiniMap(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window.field.viewport())
        self.window = window
        self.setFixedSize(204, 112)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("FieldMiniMap")
        self.setMouseTracking(True)
        self.setToolTip("Field minimap. Click or drag inside it to pan the main field view.")

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = theme_tokens(str(self.window.settings.value("appearance/theme", "dark")), self.window.settings)
        field_palette = self.window.field.field_palette()
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rect = self.map_rect().adjusted(0.5, 0.5, -0.5, -0.5)

        panel = QColor(tokens["panel_color"])
        panel.setAlpha(238)
        painter.setPen(QPen(QColor(tokens["border_color"]), 1))
        painter.setBrush(panel)
        painter.drawRoundedRect(outer, 10, 10)

        title_rect = QRectF(outer.left() + 8, outer.top() + 3, outer.width() - 16, 17)
        painter.setPen(QColor(tokens["muted_text_color"]))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Minimap")

        draw_surface_preview(
            painter,
            rect,
            self.window.project.surface,
            field_palette,
            self.window.field.field_mode,
            self.window.field.show_field_logo,
        )

        drill_set = self.window.current_set() if self.window.project.sets else None
        if drill_set:
            for prop_id, prop_state in drill_set.prop_positions.items():
                prop = self.window.project.prop_by_id(prop_id)
                point = self.field_to_minimap(
                    rect,
                    float(prop_state.get("x", 0.0)),
                    float(prop_state.get("y", 0.0)),
                )
                raw_width, raw_height = size_to_rect(
                    rect,
                    self.window.project.surface,
                    float(prop_state.get("width", 3.0)),
                    float(prop_state.get("height", 3.0)),
                )
                width = max(3.0, raw_width)
                height = max(2.0, raw_height)
                prop_color = QColor("#e53935" if not prop else "#e53935")
                prop_color.setAlpha(150)
                painter.setPen(QPen(QColor(tokens["border_color"]), 0.5))
                painter.setBrush(prop_color)
                painter.drawRoundedRect(QRectF(point.x() - width / 2, point.y() - height / 2, width, height), 2, 2)

            selected_ids = set(self.window.field.selected_dot_ids())
            pixels_per_yard = min(
                rect.width() / max(1.0, self.window.project.surface.width_yards),
                rect.height() / max(1.0, self.window.project.surface.height_yards),
            )
            radius, outline_width = scaled_field_dot_metrics(pixels_per_yard)
            for dot in self.window.project.dots:
                dot_item = self.window.field.dot_items.get(dot.id)
                if dot_item is not None:
                    x, y = self.window.field.scene_to_field(dot_item.pos())
                else:
                    x, y = drill_set.dot_positions.get(dot.id, (dot.x, dot.y))
                screen = self.field_to_minimap(rect, x, y)
                draw_dot_symbol(
                    painter,
                    screen,
                    radius,
                    QColor(dot.color or "#e53935"),
                    self.window.field.dot_symbol,
                    rotation_degrees=dot_item.facing_degrees if dot_item is not None else 0.0,
                    outline_color=QColor(tokens["background_color"]),
                    outline_width=outline_width,
                    selected=dot.id in selected_ids,
                )
        visible = self.visible_field_rect(rect)
        painter.setPen(QPen(QColor(tokens["selection_color"]), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(visible, 3, 3)

    def map_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(8, 23, -8, -8)

    def field_to_minimap(self, rect: QRectF, x: float, y: float) -> QPointF:
        return field_to_rect(rect, self.window.project.surface, x, y)

    def minimap_to_field(self, point: QPointF) -> tuple[float, float]:
        rect = self.map_rect()
        clamped_x = max(rect.left(), min(rect.right(), point.x()))
        clamped_y = max(rect.top(), min(rect.bottom(), point.y()))
        return rect_to_field(rect, self.window.project.surface, QPointF(clamped_x, clamped_y))

    def point_inside_map(self, point: QPointF) -> bool:
        return self.map_rect().contains(point)

    def visible_field_rect(self, rect: QRectF) -> QRectF:
        field = self.window.field
        viewport_rect = field.viewport().rect()
        corners = [
            field.scene_to_field(field.mapToScene(viewport_rect.topLeft())),
            field.scene_to_field(field.mapToScene(viewport_rect.bottomRight())),
        ]
        left = min(corners[0][0], corners[1][0])
        right = max(corners[0][0], corners[1][0])
        bottom = min(corners[0][1], corners[1][1])
        top = max(corners[0][1], corners[1][1])
        top_left = self.field_to_minimap(rect, left, top)
        bottom_right = self.field_to_minimap(rect, right, bottom)
        return QRectF(top_left, bottom_right).intersected(rect)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton or not self.point_inside_map(event.position()):
            event.accept()
            return
        self.pan_to(event.position())
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.pan_to(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        event.accept()

    def pan_to(self, point: QPointF) -> None:
        x, y = self.minimap_to_field(point)
        self.window.field.centerOn(self.window.field.field_to_scene(x, y))
        self.update()


class MoveDotsCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        set_index: int,
        before: dict[str, tuple[float, float]],
        after: dict[str, tuple[float, float]],
        label: str,
        before_path_anchors: dict[str, list[tuple[float, float]]] | None = None,
        after_path_anchors: dict[str, list[tuple[float, float]]] | None = None,
        before_path_controls: dict[str, list[dict[str, tuple[float, float]]]] | None = None,
        after_path_controls: dict[str, list[dict[str, tuple[float, float]]]] | None = None,
        before_count_positions: dict[str, dict[float, tuple[float, float]]] | None = None,
        after_count_positions: dict[str, dict[float, tuple[float, float]]] | None = None,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.set_index = set_index
        self.before = before
        self.after = after
        self.before_path_anchors = before_path_anchors
        self.after_path_anchors = after_path_anchors
        self.before_path_controls = before_path_controls
        self.after_path_controls = after_path_controls
        self.before_count_positions = before_count_positions
        self.after_count_positions = after_count_positions

    def redo(self) -> None:
        if self.after_path_anchors is not None:
            self.window.apply_path_geometry(
                self.set_index,
                self.after_path_anchors,
                self.after_path_controls,
                self.after_count_positions,
            )
        self.window.apply_positions(self.after, push_undo=False, set_index=self.set_index)

    def undo(self) -> None:
        if self.before_path_anchors is not None:
            self.window.apply_path_geometry(
                self.set_index,
                self.before_path_anchors,
                self.before_path_controls,
                self.before_count_positions,
            )
        self.window.apply_positions(self.before, push_undo=False, set_index=self.set_index)


class MovePropsCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        set_index: int,
        before: dict[str, dict[str, float]],
        after: dict[str, dict[str, float]],
        label: str,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.set_index = set_index
        self.before = before
        self.after = after

    def redo(self) -> None:
        self.window.apply_prop_states(self.after, push_undo=False, set_index=self.set_index)

    def undo(self) -> None:
        self.window.apply_prop_states(self.before, push_undo=False, set_index=self.set_index)


class KeyframeDotsCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        set_index: int,
        count: float,
        before: dict[str, tuple[float, float] | None],
        after: dict[str, tuple[float, float] | None],
        label: str,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.set_index = set_index
        self.count = count
        self.before = before
        self.after = after

    def redo(self) -> None:
        self.window.apply_count_keyframes(
            self.set_index,
            self.count,
            self.after,
            push_undo=False,
        )

    def undo(self) -> None:
        self.window.apply_count_keyframes(
            self.set_index,
            self.count,
            self.before,
            push_undo=False,
        )


class DotAppearanceCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        before: dict[str, dict[str, str]],
        after: dict[str, dict[str, str]],
        label: str,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.before = before
        self.after = after

    def redo(self) -> None:
        self.window.apply_dot_appearance(self.after)

    def undo(self) -> None:
        self.window.apply_dot_appearance(self.before)


class PathGeometryCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        set_index: int,
        before_anchors: dict[str, list[tuple[float, float]]],
        after_anchors: dict[str, list[tuple[float, float]]],
        before_controls: dict[str, list[dict[str, tuple[float, float]]]],
        after_controls: dict[str, list[dict[str, tuple[float, float]]]],
        before_count_positions: dict[str, dict[float, tuple[float, float]]],
        after_count_positions: dict[str, dict[float, tuple[float, float]]],
        label: str,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.set_index = set_index
        self.before_anchors = before_anchors
        self.after_anchors = after_anchors
        self.before_controls = before_controls
        self.after_controls = after_controls
        self.before_count_positions = before_count_positions
        self.after_count_positions = after_count_positions

    def redo(self) -> None:
        self.window.apply_path_geometry(
            self.set_index,
            self.after_anchors,
            self.after_controls,
            self.after_count_positions,
        )

    def undo(self) -> None:
        self.window.apply_path_geometry(
            self.set_index,
            self.before_anchors,
            self.before_controls,
            self.before_count_positions,
        )


class SetSnapshotCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        before_sets: list[DrillSet],
        after_sets: list[DrillSet],
        before_index: int,
        after_index: int,
        before_count: float,
        after_count: float,
        label: str,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.before_sets = deepcopy(before_sets)
        self.after_sets = deepcopy(after_sets)
        self.before_index = before_index
        self.after_index = after_index
        self.before_count = before_count
        self.after_count = after_count

    def redo(self) -> None:
        self.window.apply_set_snapshot(self.after_sets, self.after_index, self.after_count)

    def undo(self) -> None:
        self.window.apply_set_snapshot(self.before_sets, self.before_index, self.before_count)


class ProjectContentCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        before_dots: list[Dot],
        after_dots: list[Dot],
        before_props: list[Prop],
        after_props: list[Prop],
        before_sets: list[DrillSet],
        after_sets: list[DrillSet],
        before_dot_selection: list[str],
        after_dot_selection: list[str],
        before_prop_selection: list[str],
        after_prop_selection: list[str],
        label: str,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.before_dots = deepcopy(before_dots)
        self.after_dots = deepcopy(after_dots)
        self.before_props = deepcopy(before_props)
        self.after_props = deepcopy(after_props)
        self.before_sets = deepcopy(before_sets)
        self.after_sets = deepcopy(after_sets)
        self.before_dot_selection = list(before_dot_selection)
        self.after_dot_selection = list(after_dot_selection)
        self.before_prop_selection = list(before_prop_selection)
        self.after_prop_selection = list(after_prop_selection)

    def redo(self) -> None:
        self.window.apply_project_content(
            self.after_dots,
            self.after_props,
            self.after_sets,
            self.after_dot_selection,
            self.after_prop_selection,
        )

    def undo(self) -> None:
        self.window.apply_project_content(
            self.before_dots,
            self.before_props,
            self.before_sets,
            self.before_dot_selection,
            self.before_prop_selection,
        )


class WorkflowStateCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        before_dots: list[Dot],
        after_dots: list[Dot],
        before_sets: list[DrillSet],
        after_sets: list[DrillSet],
        before_constraints: list[DotConstraint],
        after_constraints: list[DotConstraint],
        selected_ids: list[str],
        label: str,
        before_workflow: dict[str, Any] | None = None,
        after_workflow: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.before_dots = deepcopy(before_dots)
        self.after_dots = deepcopy(after_dots)
        self.before_sets = deepcopy(before_sets)
        self.after_sets = deepcopy(after_sets)
        self.before_constraints = deepcopy(before_constraints)
        self.after_constraints = deepcopy(after_constraints)
        self.selected_ids = list(selected_ids)
        self.before_workflow = deepcopy(before_workflow) if before_workflow is not None else None
        self.after_workflow = deepcopy(after_workflow) if after_workflow is not None else None

    def redo(self) -> None:
        self.window.apply_workflow_state(
            self.after_dots,
            self.after_sets,
            self.after_constraints,
            self.selected_ids,
            self.after_workflow,
        )

    def undo(self) -> None:
        self.window.apply_workflow_state(
            self.before_dots,
            self.before_sets,
            self.before_constraints,
            self.selected_ids,
            self.before_workflow,
        )


class WorkflowMetadataCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        before: dict[str, Any],
        after: dict[str, Any],
        label: str,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.before = deepcopy(before)
        self.after = deepcopy(after)

    def redo(self) -> None:
        self.window.apply_workflow_metadata(self.after)

    def undo(self) -> None:
        self.window.apply_workflow_metadata(self.before)


class ProjectSnapshotCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        before: DrillProject,
        after: DrillProject,
        label: str,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.before = deepcopy(before)
        self.after = deepcopy(after)

    def redo(self) -> None:
        self.window.apply_project_snapshot(self.after)

    def undo(self) -> None:
        self.window.apply_project_snapshot(self.before)


class MainWindow(QMainWindow):
    return_home_requested = Signal()

    def __init__(self, project_dir: Path) -> None:
        super().__init__()
        self.project_dir = project_dir
        self.project = load_project(project_dir)
        self.settings = QSettings("OpenAI", "DrillWriter")
        self.set_index = 0
        self.current_count = self.project.sets[0].start_count if self.project.sets else 1
        self.shape_line_anchors: list[tuple[float, float]] = []
        self.shape_line_anchor_dot_ids: set[str] = set()
        self.shape_line_anchor_positions: dict[str, tuple[float, float]] = {}
        self.line_endpoints: list[tuple[float, float]] = []
        self.warp_anchors: list[tuple[float, float]] = []
        self.imported_shape_points: list[tuple[float, float]] = []
        self.imported_shape_contours: list[list[tuple[float, float]]] = []
        self.imported_shape_name = ""
        self.mirror_axis = 0.0
        self.plugin_form_tools: dict[str, PluginFormTool] = {}
        self.plugin_form_tool_buttons: dict[str, QPushButton] = {}
        self.plugin_form_tool_setting_widgets: dict[str, dict[str, QWidget]] = {}
        self.plugin_contribution_actions: dict[str, list[tuple[QMenu, QAction]]] = {}
        self.plugin_contribution_widgets: dict[str, list[QWidget]] = {}
        self.plugin_named_menus: dict[str, QMenu] = {}
        self.active_plugin_form_tool_id = ""
        self.active_motion_ribbon_id = ""
        self._motion_ribbon_drag_before_sets: list[DrillSet] | None = None
        self.plugin_manager: Any = None
        self.preview_center_offset = (0.0, 0.0)
        self.preview_transform_pivot: tuple[float, float] | None = None
        self.formation_assignment_cache: dict[tuple[Any, ...], list[int]] = {}
        self.field_hud_buttons: dict[EditorTool, QPushButton] = {}
        self.field_focus_active = False
        self.free_curve_anchors: list[tuple[float, float]] = []
        self.curve_handles: dict[str, tuple[float, float]] = {}
        self.field_hud_custom_position = self.settings.value("view/field_hud_custom_position", False, type=bool)
        self.macro_recording = False
        self.macro_replaying = False
        self.current_macro_actions: list[dict[str, Any]] = []
        self.last_repeat_action: dict[str, Any] | None = None
        self.property_brush_payload: dict[str, Any] | None = None
        self.property_brush_properties: set[str] = {"position", "path", "facing", "movement_style", "timing"}
        self._invoking_command_id = ""
        self.favorite_toolbar: QToolBar | None = None
        self._responsive_layout_bucket = ""
        self.thumbnail_cache: dict[str, QPixmap] = {}
        self._ghost_set_index = -1
        self.analysis_worker: AnalysisWorker | None = None
        self.conflict_heatmap_worker: ConflictHeatmapWorker | None = None
        self.conflict_heatmap_generation = 0
        self.conflict_heatmap_pending = False
        self.conflict_heatmap_timer = QTimer(self)
        self.conflict_heatmap_timer.setSingleShot(True)
        self.conflict_heatmap_timer.setInterval(450)
        self.conflict_heatmap_timer.timeout.connect(self.run_live_conflict_analysis)
        self._opengl_renderer_active = False
        self.radial_tool_menu: RadialToolMenu | None = None
        self.measurements_enabled = False
        self.measurement_mode = "all"
        self.command_actions: dict[str, QAction] = {}
        self.command_defaults: dict[str, str] = {}
        self.tooltip_widgets: list[QWidget] = []
        self.tooltip_actions: list[QAction] = []
        self.dock_widgets: dict[str, QDockWidget] = {}
        self.undo_stack = QUndoStack(self)
        self.playback_scheduler = FrameScheduler(
            adaptive=self.settings.value("performance/adaptive_playback", True, type=bool)
        )
        self.playback_frame_cache: PlaybackFrameCache[tuple[dict, dict, dict]] = PlaybackFrameCache(
            max_frames=720
        )
        self.playback_auxiliary_frame = 0
        self._last_playback_diagnostics_update_ms = 0.0
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_recovery_policy = AudioRecoveryPolicy()
        self.audio_recovery_resume_requested = False
        self.audio_recovery_position_ms = 0
        self.requested_audio_output_device_id = ""
        self.applied_audio_output_physical_id = ""
        self.audio_device_refresh_timer = QTimer(self)
        self.audio_device_refresh_timer.setSingleShot(True)
        self.audio_device_refresh_timer.setInterval(700)
        self.audio_device_refresh_timer.timeout.connect(self.recover_saved_audio_output_device)
        self.media_devices = QMediaDevices(self)
        self.media_devices.audioOutputsChanged.connect(self.schedule_audio_output_refresh)
        self.player.setAudioOutput(self.audio_output)
        self.apply_saved_audio_output_device()
        self.player.durationChanged.connect(self.audio_duration_changed)
        self.player.positionChanged.connect(self.audio_position_changed)
        self.player.errorOccurred.connect(self.audio_playback_error)
        self.audio_health_timer = QTimer(self)
        self.audio_health_timer.setInterval(1000)
        self.audio_health_timer.timeout.connect(self.check_audio_output_health)
        self.audio_health_timer.start()
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(16)
        self.play_timer.timeout.connect(self.tick_playback)
        self.playback_clock = QElapsedTimer()
        self.last_playback_audio_ms = 0
        self.autosave_timer = QTimer(self)
        self._last_autosave_error = ""
        self.autosave_timer.setInterval(8000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()

        self.setWindowTitle(f"Drill Pirate - {self.project.metadata.show_title}")
        self.setWindowIcon(QIcon(str(app_icon_path())))
        self.resize(1500, 900)
        self.field = FieldView()
        self.field.set_project(self.project, self.project_dir)
        self.field.set_drill_grid(self.drill_grid_settings())
        self.field.set_facings(self.facings_for_set())
        self.apply_field_renderer()
        self.field.selection_changed.connect(self.selection_changed)
        self.field.dot_moved.connect(self.dot_moved)
        self.field.dots_moved.connect(self.dots_moved)
        self.field.dots_drag_preview.connect(self.preview_live_symmetry)
        self.field.dots_drag_preview.connect(self.preview_dot_coordinates)
        self.field.prop_moved.connect(self.prop_moved)
        self.field.props_moved.connect(self.props_moved)
        self.field.guide_moved.connect(self.move_construction_guide)
        self.field.guide_edit_requested.connect(self.edit_construction_guide)
        self.field.context_action.connect(self.context_action)
        self.field.dot_edit_requested.connect(self.edit_dot_from_field)
        self.field.preview_handle_moved_detailed.connect(self.preview_handle_moved)
        self.field.preview_handle_dragged.connect(self.preview_handle_dragged)
        self.field.path_anchor_added.connect(self.add_path_anchor)
        self.field.path_anchor_moved_detailed.connect(self.move_path_anchor)
        self.field.path_tangent_moved_detailed.connect(self.move_path_tangent)
        self.field.shape_anchor_toggled.connect(self.toggle_shape_line_anchor)
        self.field.transform_gizmo_applied.connect(self.apply_gizmo_transform)
        self.field.precision_nudge_requested.connect(self.precision_nudge_selected)
        self.field.temporary_tool_requested.connect(self.temporary_tool_requested)
        self.field.direct_edit_requested.connect(self.direct_edit_field_item)
        self.field.apply_requested.connect(self.apply_current_preview)
        self.field.cancel_requested.connect(self.clear_formation_preview)
        self.field.set_tool_value_provider(self.tool_value_text)
        self.field.set_formation_callback(self.apply_formation)
        central_widget = self.build_layout()
        self.setCentralWidget(central_widget)
        self.polish_editor_layouts()
        self.build_field_hud()
        self.minimap = FieldMiniMap(self)
        self.field.viewport().installEventFilter(self)
        self.field.horizontalScrollBar().valueChanged.connect(lambda _value: self.position_minimap())
        self.field.verticalScrollBar().valueChanged.connect(lambda _value: self.position_minimap())
        self.minimap.setVisible(self.minimap_visible())
        self.position_minimap()
        self.apply_visual_theme(theme_tokens(str(self.settings.value("appearance/theme", "dark")), self.settings))
        self.build_menus()
        self.apply_tooltips_enabled(self.tooltips_enabled())
        self.migrate_editor_layout()
        self.restore_ui_layout()
        self.refresh_audio_versions()
        self.refresh_timing_events()
        self.populate_sets()
        self.refresh_marcher_table()
        self.refresh_prop_table()
        self.refresh_visibility_filters()
        self.refresh_selection_sets()
        self.refresh_tool_presets()
        self.refresh_formation_presets()
        self.refresh_lock_controls()
        self.apply_locks_to_field()
        self.refresh_appearance_groups()
        self.refresh_constraints()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=False)
        self.sync_inspector()
        self.load_audio()
        self.schedule_live_conflict_analysis()

    def build_menus(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.clear()
        file_menu = menu_bar.addMenu("File")
        edit_menu = menu_bar.addMenu("Edit")
        view_menu = menu_bar.addMenu("View")
        tools_menu = menu_bar.addMenu("Tools")
        playback_menu = menu_bar.addMenu("Playback")
        self.plugin_tools_menu = menu_bar.addMenu("Plugins")
        settings_menu = menu_bar.addMenu("Settings")
        help_menu = menu_bar.addMenu("Help")
        self.plugin_named_menus.update(
            {
                "File": file_menu,
                "Edit": edit_menu,
                "View": view_menu,
                "Tools": tools_menu,
                "Playback": playback_menu,
                "Plugin Tools": self.plugin_tools_menu,
                "Settings": settings_menu,
                "Help": help_menu,
            }
        )
        save_action = self.menu_action("Save", self.save, QKeySequence.StandardKey.Save)
        save_as_action = self.menu_action("Save As", self.save_as, QKeySequence.StandardKey.SaveAs)
        restore_action = self.menu_action("Restore Previous Save", self.restore_previous_save)
        export_action = self.menu_action("Export", self.show_export_dialog, QKeySequence("Ctrl+E"))
        open_tab_action = self.menu_action("Open Project in New Tab", self.open_project_tab, QKeySequence("Ctrl+Shift+O"))
        copy_tab_action = self.menu_action("Copy From Open Project Tab", self.copy_from_project_tab, QKeySequence("Ctrl+Shift+Alt+O"))
        home_action = self.menu_action("Return to Home Screen", self.return_home)
        file_menu.addActions([save_action, save_as_action, restore_action, export_action])
        file_menu.addSeparator()
        file_menu.addAction(open_tab_action)
        file_menu.addAction(copy_tab_action)
        file_menu.addAction(home_action)

        edit_menu.addAction(self.menu_action("Undo", self.undo_stack.undo, QKeySequence.StandardKey.Undo))
        edit_menu.addAction(self.menu_action("Redo", self.undo_stack.redo, QKeySequence.StandardKey.Redo))
        edit_menu.addAction(self.menu_action("Repeat Last Action", self.repeat_last_action, QKeySequence("F4")))
        edit_menu.addSeparator()
        edit_menu.addAction(self.menu_action("Command Palette", self.show_command_palette, QKeySequence("Ctrl+Shift+P")))
        edit_menu.addAction(self.menu_action("Keyboard Shortcuts", self.show_shortcut_editor, QKeySequence("Ctrl+Alt+,")))
        macros_menu = edit_menu.addMenu("Macros")
        macros_menu.addAction(self.menu_action("Start Macro Recording", self.start_macro_recording, QKeySequence("Ctrl+Alt+Shift+[")))
        macros_menu.addAction(self.menu_action("Stop Macro Recording", self.stop_macro_recording, QKeySequence("Ctrl+Alt+Shift+.")))
        macros_menu.addAction(self.menu_action("Save Recorded Macro", self.save_recorded_macro))
        macros_menu.addAction(self.menu_action("Replay Macro", self.replay_macro, QKeySequence("Ctrl+Alt+Shift+Enter")))
        macros_menu.addAction(self.menu_action("Delete Macro", self.delete_macro))

        playback_menu.addAction(self.menu_action("Play/Pause", self.toggle_playback, Qt.Key.Key_Space))
        playback_menu.addAction(self.menu_action("Pause", self.pause))
        playback_menu.addAction(self.menu_action("Toggle Loop Current Set", self.toggle_loop_current_set, QKeySequence("Ctrl+L")))
        playback_menu.addAction(self.menu_action("Go To Count", self.focus_count_finder, QKeySequence("Ctrl+G")))
        playback_menu.addSeparator()
        playback_menu.addAction(self.menu_action("Reset Playback Diagnostics", self.reset_playback_diagnostics))

        settings_menu.addAction(self.menu_action("Preferences", self.open_preferences, QKeySequence("Ctrl+,")))

        help_menu.addAction(self.menu_action("Export Bug Report Bundle", self.export_bug_report_bundle))

        self.minimap_action = self.menu_action("Show Field Minimap", self.set_minimap_visible)
        self.minimap_action.setCheckable(True)
        self.minimap_action.setChecked(self.minimap_visible())
        view_menu.addAction(self.minimap_action)
        self.field_hud_action = self.menu_action("Show Tool HUD", self.set_field_hud_enabled)
        self.field_hud_action.setCheckable(True)
        self.field_hud_action.setChecked(self.field_hud_enabled())
        view_menu.addAction(self.field_hud_action)
        self.transform_gizmo_action = self.menu_action(
            "Transform Handles",
            self.set_transform_gizmo_visible,
            QKeySequence("Ctrl+Shift+T"),
        )
        self.transform_gizmo_action.setCheckable(True)
        self.transform_gizmo_action.setChecked(self.transform_gizmo_visible())
        view_menu.addAction(self.transform_gizmo_action)
        self.field.set_transform_gizmo_enabled(self.transform_gizmo_visible())
        self.set_thumbnails_action = self.menu_action("Show Set Thumbnails", self.set_set_thumbnails_enabled)
        self.set_thumbnails_action.setCheckable(True)
        self.set_thumbnails_action.setChecked(self.set_thumbnails_enabled())
        view_menu.addAction(self.set_thumbnails_action)
        self.opengl_action = self.menu_action("Use OpenGL Field Renderer", self.set_opengl_renderer_enabled)
        self.opengl_action.setCheckable(True)
        self.opengl_action.setChecked(self.opengl_renderer_enabled())
        view_menu.addAction(self.opengl_action)
        view_menu.addSeparator()
        panels_menu = view_menu.addMenu("Panels")
        for title, dock in self.dock_widgets.items():
            action = dock.toggleViewAction()
            action.setText(dock.windowTitle())
            panels_menu.addAction(action)
        workspace_menu = view_menu.addMenu("Workspaces")
        for workspace_name, label, shortcut in (
            ("design", "Design Workspace", "Ctrl+Alt+1"),
            ("forms", "Forms Workspace", "Ctrl+Alt+2"),
            ("rehearse", "Rehearse Workspace", "Ctrl+Alt+3"),
            ("print", "Print Workspace", "Ctrl+Alt+4"),
            ("focus", "Focus Field", "Ctrl+Alt+5"),
            ("music", "Music Design Workspace", "Ctrl+Alt+6"),
            ("specialized", "Specialized Design Workspace", "Ctrl+Alt+7"),
        ):
            workspace_menu.addAction(
                self.menu_action(
                    label,
                    lambda _checked=False, name=workspace_name: self.apply_workspace(name),
                    QKeySequence(shortcut),
                )
            )
        workspace_menu.addSeparator()
        workspace_menu.addAction(self.menu_action("Toggle Field Focus", self.toggle_field_focus, QKeySequence("F11")))
        workspace_menu.addAction(self.menu_action("Reset Panels", self.reset_panel_layout, QKeySequence("Ctrl+Alt+0")))
        workspace_menu.addAction(self.menu_action("Save Current Workspace", self.save_custom_workspace, QKeySequence("Ctrl+Alt+Shift+S")))
        workspace_menu.addAction(self.menu_action("Restore Saved Workspace", self.restore_custom_workspace, QKeySequence("Ctrl+Alt+Shift+W")))
        workspace_menu.addSeparator()
        workspace_menu.addAction(self.menu_action("Save Workspace Profile", self.save_workspace_profile))
        workspace_menu.addAction(self.menu_action("Load Workspace Profile", self.load_workspace_profile))
        workspace_menu.addAction(self.menu_action("Delete Workspace Profile", self.delete_workspace_profile))

        add_marcher_action = self.menu_action("Add Marcher", self.add_marcher, QKeySequence("Ctrl+M"))
        delete_marcher_action = self.menu_action("Delete Selected", self.delete_selected_marchers, QKeySequence("Del"))
        import_prop_action = self.menu_action("Import Prop Image", self.import_prop_image, QKeySequence("Ctrl+Alt+I"))
        design_prop_action = self.menu_action("Open Prop Designer", self.open_prop_designer, QKeySequence("Ctrl+Alt+Shift+P"))
        add_front_ensemble_action = self.menu_action("Add Front Ensemble Prop", self.add_front_ensemble_prop, QKeySequence("Ctrl+Alt+E"))
        add_drum_major_stand_action = self.menu_action("Add Drum Major Stand", self.add_drum_major_stand, QKeySequence("Ctrl+Alt+Shift+L"))
        add_set_action = self.menu_action("Add Set", self.add_set, QKeySequence("Ctrl+Alt+S"))
        remove_set_action = self.menu_action("Remove Set", self.remove_set, QKeySequence("Ctrl+Alt+Backspace"))
        copy_set_action = self.menu_action("Copy Current Set", self.copy_set, QKeySequence("Ctrl+Alt+C"))
        select_instrument_action = self.menu_action(
            "Select Same Instrument",
            self.select_same_instrument,
            QKeySequence("Ctrl+Alt+Shift+U"),
        )
        select_section_action = self.menu_action("Select Same Section", self.select_same_section, QKeySequence("Ctrl+Alt+Shift+A"))
        invert_selection_action = self.menu_action("Invert Selection", self.invert_selection, QKeySequence("Ctrl+Alt+Shift+I"))
        select_moving_action = self.menu_action("Select Moving This Set", self.select_moving_this_set, QKeySequence("Ctrl+Alt+Shift+M"))
        carry_forward_action = self.menu_action("Carry Selected Forward", self.carry_selected_forward, QKeySequence("Ctrl+Alt+Shift+F"))
        start_move_here_action = self.menu_action("Start Selected Move Here", self.start_selected_move_at_current_count, QKeySequence("Ctrl+Alt+H"))
        capture_opening_action = self.menu_action(
            "Set Opening Positions From Current View",
            self.capture_opening_positions_from_current_view,
            QKeySequence("Ctrl+Alt+Shift+H"),
        )
        face_front_action = self.menu_action("Face Selected Front", lambda: self.set_selected_facing(0), QKeySequence("Ctrl+Alt+Up"))
        face_back_action = self.menu_action("Face Selected Back", lambda: self.set_selected_facing(180), QKeySequence("Ctrl+Alt+Down"))
        rotate_facing_left_action = self.menu_action("Rotate Selected Facing Left 45", lambda: self.rotate_selected_facing(-45), QKeySequence("Ctrl+Alt+Left"))
        rotate_facing_right_action = self.menu_action("Rotate Selected Facing Right 45", lambda: self.rotate_selected_facing(45), QKeySequence("Ctrl+Alt+Right"))
        tools_menu.addActions(
            [
                add_marcher_action,
                delete_marcher_action,
                import_prop_action,
                design_prop_action,
                add_front_ensemble_action,
                add_drum_major_stand_action,
                add_set_action,
                remove_set_action,
                copy_set_action,
                select_instrument_action,
                select_section_action,
                invert_selection_action,
                select_moving_action,
                carry_forward_action,
                start_move_here_action,
                capture_opening_action,
                face_front_action,
                face_back_action,
                rotate_facing_left_action,
                rotate_facing_right_action,
            ]
        )
        tools_menu.addSeparator()
        tool_shortcuts = (
            ("Select Tool", EditorTool.SELECT, "Alt+1"),
            ("Line Tool", EditorTool.LINE, "Alt+2"),
            ("Curve Tool", EditorTool.CURVE, "Alt+3"),
            ("Arc Tool", EditorTool.ARC, "Alt+4"),
            ("Scatter Tool", EditorTool.SCATTER, "Alt+5"),
            ("Mirror Tool", EditorTool.MIRROR, "Alt+6"),
            ("Shape Line Tool", EditorTool.SHAPE_LINE, "Alt+7"),
            ("Circle Tool", EditorTool.CIRCLE, "Alt+8"),
            ("Rectangle Tool", EditorTool.RECTANGLE, "Alt+9"),
            ("Lasso Tool", EditorTool.LASSO, "Alt+0"),
            ("Ellipse/Oval Tool", EditorTool.ELLIPSE, "Ctrl+Alt+O"),
            ("Triangle Tool", EditorTool.TRIANGLE, "Ctrl+Alt+T"),
            ("Diamond Tool", EditorTool.DIAMOND, "Ctrl+Alt+J"),
            ("Polygon Tool", EditorTool.POLYGON, "Ctrl+Alt+Y"),
            ("Star Tool", EditorTool.STAR, "Ctrl+Alt+Shift+G"),
            ("Scale Form Tool", EditorTool.SCALE, "Ctrl+Alt+X"),
            ("Warp Form Tool", EditorTool.WARP, "Ctrl+Alt+W"),
            ("Rotate Form Tool", EditorTool.ROTATE, "Ctrl+Alt+Shift+O"),
            ("Spiral Tool", EditorTool.SPIRAL, "Ctrl+Alt+P"),
            ("Block/Grid Tool", EditorTool.BLOCK, "Ctrl+Alt+B"),
            ("SVG Shape Tool", EditorTool.SVG_SHAPE, "Ctrl+Alt+V"),
            ("Free Curve Tool", EditorTool.FREE_CURVE, "Ctrl+Alt+U"),
        )
        tool_actions: list[QAction] = []
        for label, tool, shortcut in tool_shortcuts:
            action = self.menu_action(label, lambda _checked=False, selected=tool: self.set_tool(selected), QKeySequence(shortcut))
            tools_menu.addAction(action)
            tool_actions.append(action)
        tools_menu.addSeparator()
        snap_action = self.menu_action("Toggle Snap Align", self.toggle_snap_align, QKeySequence("Ctrl+Alt+N"))
        self.drill_grid_enable_action = self.menu_action(
            "Enable Drill Grid Snapping",
            self.set_drill_grid_enabled,
            QKeySequence("Ctrl+Alt+Shift+N"),
        )
        self.drill_grid_enable_action.setCheckable(True)
        self.drill_grid_enable_action.setChecked(self.drill_grid_settings().enabled)
        drill_grid_configure_action = self.menu_action(
            "Configure Drill Grid...",
            self.show_drill_grid_dialog,
            QKeySequence("Ctrl+Shift+G"),
        )
        analyze_action = self.menu_action("Analyze Paths", self.analyze_paths, QKeySequence("Ctrl+Alt+A"))
        plan_action = self.menu_action(
            "Optimize Selected Spot Assignment",
            self.optimize_selected_spot_assignment,
            QKeySequence("Ctrl+Alt+R"),
        )
        clear_paths_action = self.menu_action("Clear Selected Paths", self.clear_selected_paths, QKeySequence("Ctrl+Alt+Shift+R"))
        keyframe_action = self.menu_action("Set Count Keyframe", self.add_micro_keyframe, QKeySequence("Ctrl+Alt+K"))
        follow_action = self.menu_action("Follow the Leader...", self.follow_leader_rotate, QKeySequence("Ctrl+Alt+F"))
        motion_ribbon_action = self.menu_action("Group Motion Ribbon...", self.create_group_motion_ribbon, QKeySequence("Ctrl+Shift+F1"))
        group_handles_action = self.menu_action("Edit Group Path Handles", self.edit_group_path_handles, QKeySequence("Ctrl+Shift+F2"))
        continuity_action = self.menu_action("Continuity Designer...", self.show_continuity_designer, QKeySequence("Ctrl+Shift+F3"))
        guides_action = self.menu_action("Construction Guides...", self.show_construction_guides, QKeySequence("Ctrl+Shift+F4"))
        cad_action = self.menu_action("CAD Path Toolkit...", self.show_cad_path_toolkit, QKeySequence("Ctrl+Shift+F5"))
        morph_action = self.menu_action("Formation Morph...", self.show_formation_morph, QKeySequence("Ctrl+Shift+F12"))
        fit_prop_action = self.menu_action("Fit Form to Selected Prop", self.fit_selected_form_to_prop, QKeySequence("Ctrl+Alt+Shift+X"))
        composer_action = self.menu_action("Guided Destination Repair...", self.show_smart_transition_composer, QKeySequence("Ctrl+Alt+Shift+C"))
        section_fit_action = self.menu_action("Section-Aware Form Fit", self.apply_section_aware_form_fit, QKeySequence("Ctrl+Alt+Shift+J"))
        copy_properties_action = self.menu_action("Copy With Property Paintbrush", self.copy_property_brush, QKeySequence("Ctrl+Shift+C"))
        paint_properties_action = self.menu_action("Paint Copied Properties", self.paint_property_brush, QKeySequence("Ctrl+Shift+V"))
        beat_sets_action = self.menu_action("Beat-to-Set Generator", self.show_beat_set_generator, QKeySequence("Ctrl+Alt+G"))
        radial_action = self.menu_action("Radial Tool Menu", self.show_radial_tool_menu, QKeySequence("Q"))
        duplicate_next_action = self.menu_action("Duplicate Form To Next Set", self.duplicate_form_to_next_set, QKeySequence("Ctrl+D"))
        duplicate_rotate_action = self.menu_action("Duplicate Rotate To Next Set", self.duplicate_rotate_to_next_set, QKeySequence("Ctrl+Shift+D"))
        duplicate_scale_action = self.menu_action("Duplicate Scale To Next Set", self.duplicate_scale_to_next_set, QKeySequence("Ctrl+Alt+D"))
        duplicate_mirror_action = self.menu_action("Duplicate Mirror To Next Set", self.duplicate_mirror_to_next_set, QKeySequence("Ctrl+Alt+Shift+D"))
        apply_preview_action = self.menu_action("Apply Current Preview", self.apply_current_preview, QKeySequence("Ctrl+Return"))
        clear_preview_action = self.menu_action("Clear Current Preview", self.clear_formation_preview, QKeySequence("Esc"))
        tools_menu.addActions([snap_action, self.drill_grid_enable_action, drill_grid_configure_action])
        tools_menu.addSeparator()
        tools_menu.addActions([analyze_action, plan_action, clear_paths_action, keyframe_action, follow_action, motion_ribbon_action, group_handles_action, continuity_action, guides_action, cad_action, morph_action, fit_prop_action])
        tools_menu.addSeparator()
        tools_menu.addActions([composer_action, section_fit_action, copy_properties_action, paint_properties_action, beat_sets_action, radial_action])
        quick_duplicate_menu = tools_menu.addMenu("Quick Duplicate/Transform")
        quick_duplicate_menu.addActions([duplicate_next_action, duplicate_rotate_action, duplicate_scale_action, duplicate_mirror_action])
        design_accelerators_menu = tools_menu.addMenu("Design Accelerators")
        design_accelerators_menu.addAction(
            self.menu_action("Polar / Linear Array", self.show_polar_linear_array, QKeySequence("Ctrl+Alt+Shift+1"))
        )
        design_accelerators_menu.addAction(
            self.menu_action("Parallel Form Generator", self.show_parallel_form_generator, QKeySequence("Ctrl+Alt+Shift+2"))
        )
        design_accelerators_menu.addAction(
            self.menu_action("Rank / File Builder", self.show_rank_file_builder, QKeySequence("Ctrl+Alt+Shift+3"))
        )
        design_accelerators_menu.addSeparator()
        design_accelerators_menu.addAction(
            self.menu_action("Create Live Symmetry", self.create_live_symmetry, QKeySequence("Ctrl+Alt+Shift+4"))
        )
        design_accelerators_menu.addAction(
            self.menu_action("Manage Live Symmetry", self.manage_live_symmetry)
        )
        design_accelerators_menu.addAction(
            self.menu_action("Alternating Selection", self.show_alternating_selection, QKeySequence("Ctrl+Alt+Shift+5"))
        )
        design_accelerators_menu.addSeparator()
        design_accelerators_menu.addAction(
            self.menu_action("Toggle On-Field Measurements", self.toggle_measurement_overlay, QKeySequence("Ctrl+Alt+Shift+6"))
        )
        design_accelerators_menu.addAction(
            self.menu_action("Reference / Annotation Layer", self.show_reference_annotations, QKeySequence("Ctrl+Alt+Shift+7"))
        )
        music_design_menu = tools_menu.addMenu("Music & Show Design")
        music_studio_action = self.menu_action(
            "Open Music Design Studio",
            self.show_music_design_studio,
            QKeySequence("Ctrl+Alt+Shift+8"),
        )
        music_import_action = self.menu_action(
            "Import MusicXML / MIDI",
            lambda: self.show_music_design_studio("score"),
            QKeySequence("Ctrl+Alt+Shift+9"),
        )
        music_phrase_action = self.menu_action(
            "Phrase & Set Planner",
            lambda: self.show_music_design_studio("phrases"),
        )
        music_storyboard_action = self.menu_action(
            "Show Storyboard",
            lambda: self.show_music_design_studio("storyboard"),
            QKeySequence("Ctrl+Alt+Shift+0"),
        )
        music_suggestions_action = self.menu_action(
            "Automated Musical Set Suggestions",
            lambda: self.show_music_design_studio("suggestions"),
        )
        music_design_menu.addActions(
            [
                music_studio_action,
                music_import_action,
                music_phrase_action,
                music_storyboard_action,
                music_suggestions_action,
            ]
        )
        specialized_menu = tools_menu.addMenu("Specialized Design")
        specialized_menu.addAction(
            self.menu_action("Open Specialized Design Studio", self.show_specialized_design_studio, QKeySequence("Ctrl+Shift+F12"))
        )
        specialized_menu.addAction(self.menu_action("Surface & Parade Route", lambda: self.show_specialized_design_studio("surface")))
        specialized_menu.addAction(self.menu_action("Guard Choreography Tracks", lambda: self.show_specialized_design_studio("choreography")))
        specialized_menu.addAction(self.menu_action("Performer Prop Attachments", lambda: self.show_specialized_design_studio("props")))
        specialized_menu.addAction(self.menu_action("Physical Limits & Warnings", lambda: self.show_specialized_design_studio("safety")))
        tools_menu.addSeparator()
        tools_menu.addActions([apply_preview_action, clear_preview_action])
        large_show_menu = tools_menu.addMenu("Large-Show Accelerators")
        import_roster_action = self.menu_action("Import Roster CSV", self.import_roster_csv, QKeySequence("Ctrl+Shift+F6"))
        groups_action = self.menu_action("Hierarchy & Linked Formations", self.show_group_manager, QKeySequence("Ctrl+Shift+F7"))
        replace_action = self.menu_action("Replace / Swap Performer", self.replace_or_swap_performer, QKeySequence("Ctrl+Shift+F8"))
        cleanup_action = self.menu_action("Automatic Form Cleanup", self.automatic_form_cleanup, QKeySequence("Ctrl+Shift+F9"))
        compare_action = self.menu_action("Compare Sets", self.show_set_comparison, QKeySequence("Ctrl+Shift+F10"))
        variations_action = self.menu_action("Formation Variations", self.show_formation_variations, QKeySequence("Ctrl+Shift+F11"))
        large_show_menu.addActions(
            [
                import_roster_action,
                groups_action,
                replace_action,
                cleanup_action,
                compare_action,
                variations_action,
                music_studio_action,
                music_import_action,
                music_phrase_action,
                music_storyboard_action,
                music_suggestions_action,
            ]
        )
        favorites_menu = tools_menu.addMenu("Favorites")
        favorites_menu.addAction(self.menu_action("Add Favorite Command", self.add_favorite_command))
        favorites_menu.addAction(self.menu_action("Remove Favorite Command", self.remove_favorite_command))
        self.addActions(
            [
                add_marcher_action,
                delete_marcher_action,
                import_prop_action,
                design_prop_action,
                add_front_ensemble_action,
                add_drum_major_stand_action,
                add_set_action,
                remove_set_action,
                start_move_here_action,
                face_front_action,
                face_back_action,
                rotate_facing_left_action,
                rotate_facing_right_action,
                *tool_actions,
                snap_action,
                self.drill_grid_enable_action,
                drill_grid_configure_action,
                analyze_action,
                plan_action,
                clear_paths_action,
                keyframe_action,
                follow_action,
                motion_ribbon_action,
                group_handles_action,
                continuity_action,
                guides_action,
                cad_action,
                morph_action,
                fit_prop_action,
                composer_action,
                section_fit_action,
                copy_properties_action,
                paint_properties_action,
                beat_sets_action,
                radial_action,
                duplicate_next_action,
                duplicate_rotate_action,
                duplicate_scale_action,
                duplicate_mirror_action,
                apply_preview_action,
                clear_preview_action,
                import_roster_action,
                groups_action,
                replace_action,
                cleanup_action,
                compare_action,
                variations_action,
            ]
        )
        self.build_workspace_toolbar()

    def menu_action(self, text: str, callback, shortcut=None) -> QAction:
        action = QAction(text, self)
        self.register_action_tooltip(action, text)
        command_id = self.unique_command_id(text)
        default_shortcut = self.shortcut_text(shortcut)
        action.setProperty("command_id", command_id)
        action.setProperty("default_shortcut", default_shortcut)
        self.command_actions[command_id] = action
        self.command_defaults[command_id] = default_shortcut
        action.triggered.connect(lambda checked=False, cid=command_id, cb=callback: self.invoke_command(cid, cb, checked))
        saved_shortcut = self.settings.value(f"shortcuts/{command_id}", None)
        if saved_shortcut is not None:
            action.setShortcut(QKeySequence(str(saved_shortcut)))
        elif shortcut:
            action.setShortcut(shortcut)
        return action

    def invoke_command(self, command_id: str, callback, checked: bool = False) -> None:
        if (
            self.macro_recording
            and not self.macro_replaying
            and command_id not in self.macro_control_command_ids()
        ):
            self.current_macro_actions.append(
                {
                    "command_id": command_id,
                    "context": self.macro_context_snapshot(),
                }
            )
            self.statusBar().showMessage(f"Recording macro: {len(self.current_macro_actions)} action(s)", 1200)
        previous_command_id = self._invoking_command_id
        self._invoking_command_id = command_id
        try:
            try:
                callback(checked)
            except TypeError as original_error:
                try:
                    callback()
                except TypeError:
                    raise original_error
        finally:
            self._invoking_command_id = previous_command_id

    def macro_control_command_ids(self) -> set[str]:
        return {
            "start_macro_recording",
            "stop_macro_recording",
            "save_recorded_macro",
            "replay_macro",
            "delete_macro",
            "add_favorite_command",
            "remove_favorite_command",
            "radial_tool_menu",
            "command_palette",
            "keyboard_shortcuts",
            "repeat_last_action",
        }

    def tool_command_id(self, tool: EditorTool) -> str:
        return {
            EditorTool.SELECT: "select_tool",
            EditorTool.LINE: "line_tool",
            EditorTool.CURVE: "curve_tool",
            EditorTool.FREE_CURVE: "free_curve_tool",
            EditorTool.ARC: "arc_tool",
            EditorTool.SCATTER: "scatter_tool",
            EditorTool.MIRROR: "mirror_tool",
            EditorTool.SHAPE_LINE: "shape_line_tool",
            EditorTool.CIRCLE: "circle_tool",
            EditorTool.RECTANGLE: "rectangle_tool",
            EditorTool.LASSO: "lasso_tool",
            EditorTool.ELLIPSE: "ellipse_oval_tool",
            EditorTool.TRIANGLE: "triangle_tool",
            EditorTool.DIAMOND: "diamond_tool",
            EditorTool.POLYGON: "polygon_tool",
            EditorTool.STAR: "star_tool",
            EditorTool.SCALE: "scale_form_tool",
            EditorTool.WARP: "warp_form_tool",
            EditorTool.ROTATE: "rotate_form_tool",
            EditorTool.SPIRAL: "spiral_tool",
            EditorTool.BLOCK: "block_grid_tool",
            EditorTool.SVG_SHAPE: "svg_shape_tool",
        }.get(tool, "")

    def load_json_setting(self, key: str, fallback):
        raw = self.settings.value(key, "")
        if not raw:
            return fallback
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError:
            return fallback
        return value

    def save_json_setting(self, key: str, value: Any) -> None:
        self.settings.setValue(key, json.dumps(value, indent=2, sort_keys=True))
        self.settings.sync()

    def macro_context_snapshot(self) -> dict[str, Any]:
        return {
            "selected_dot_ids": self.field.selected_dot_ids(),
            "selected_prop_ids": self.field.selected_prop_ids(),
            "count": self.current_count,
            "tool_settings": self.current_tool_settings() if hasattr(self, "curve_bend") else {},
        }

    def restore_macro_context(self, context: dict[str, Any], options: dict[str, object]) -> None:
        if bool(options.get("restore_selection", False)):
            selected_dots = set(str(value) for value in context.get("selected_dot_ids", []))
            selected_props = set(str(value) for value in context.get("selected_prop_ids", []))
            for dot_id, item in self.field.dot_items.items():
                item.setSelected(dot_id in selected_dots)
            for prop_id, item in self.field.prop_items.items():
                item.setSelected(prop_id in selected_props)
        if bool(options.get("restore_values", True)):
            settings = context.get("tool_settings", {})
            if isinstance(settings, dict):
                self.apply_tool_settings(settings)
            count = context.get("count")
            if isinstance(count, (int, float)):
                start, end = playback_bounds_for_set(self.project, self.set_index)
                if start <= float(count) <= end:
                    self.set_count(float(count), seek_audio=False)

    def macro_library(self) -> dict[str, dict[str, Any]]:
        raw = self.load_json_setting("macros/library", {})
        if not isinstance(raw, dict):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for name, payload in raw.items():
            if isinstance(payload, list):
                steps = [
                    {"command_id": str(command_id), "context": {}}
                    for command_id in payload
                    if str(command_id) in self.command_actions
                ]
                result[str(name)] = {"steps": steps, "options": {}}
                continue
            if not isinstance(payload, dict):
                continue
            steps: list[dict[str, Any]] = []
            for step in payload.get("steps", []):
                if not isinstance(step, dict):
                    continue
                command_id = str(step.get("command_id", ""))
                if command_id in self.command_actions:
                    steps.append(
                        {
                            "command_id": command_id,
                            "context": dict(step.get("context", {})) if isinstance(step.get("context", {}), dict) else {},
                        }
                    )
            result[str(name)] = {
                "steps": steps,
                "options": dict(payload.get("options", {})) if isinstance(payload.get("options", {}), dict) else {},
            }
        return result

    def start_macro_recording(self) -> None:
        self.current_macro_actions = []
        self.macro_recording = True
        self.statusBar().showMessage("Macro recording started", 2400)

    def stop_macro_recording(self) -> None:
        self.macro_recording = False
        self.statusBar().showMessage(f"Macro recording stopped: {len(self.current_macro_actions)} action(s)", 3000)

    def save_recorded_macro(self) -> None:
        if self.macro_recording:
            self.stop_macro_recording()
        if not self.current_macro_actions:
            QMessageBox.information(self, "Command Macros", "Record at least one command first.")
            return
        name, accepted = QInputDialog.getText(self, "Save Macro", "Macro name:", text="New Macro")
        if not accepted or not name.strip():
            return
        macros = self.macro_library()
        macros[name.strip()] = {"steps": deepcopy(self.current_macro_actions), "options": {}}
        self.save_json_setting("macros/library", macros)
        self.statusBar().showMessage(f"Saved macro '{name.strip()}'", 2400)

    def replay_macro(self) -> None:
        macros = self.macro_library()
        if not macros:
            QMessageBox.information(self, "Command Macros", "No saved macros yet.")
            return
        name, accepted = QInputDialog.getItem(self, "Replay Macro", "Macro:", sorted(macros), 0, False)
        if not accepted or not name:
            return
        payload = macros.get(name, {})
        dialog = MacroReplayDialog(dict(payload.get("options", {})), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.values()
        payload["options"] = options
        macros[name] = payload
        self.save_json_setting("macros/library", macros)
        self.macro_replaying = True
        try:
            for repeat_index in range(int(options.get("repeat_count", 1))):
                for step in payload.get("steps", []):
                    if not isinstance(step, dict):
                        continue
                    self.restore_macro_context(dict(step.get("context", {})), options)
                    action = self.command_actions.get(str(step.get("command_id", "")))
                    if action:
                        action.trigger()
                if bool(options.get("advance_sets", False)) and repeat_index + 1 < int(options.get("repeat_count", 1)):
                    if self.set_index + 1 < len(self.project.sets):
                        self.change_set(self.set_index + 1)
        finally:
            self.macro_replaying = False
        self.statusBar().showMessage(f"Replayed macro '{name}'", 2400)

    def delete_macro(self) -> None:
        macros = self.macro_library()
        if not macros:
            return
        name, accepted = QInputDialog.getItem(self, "Delete Macro", "Macro:", sorted(macros), 0, False)
        if not accepted or not name:
            return
        macros.pop(name, None)
        self.save_json_setting("macros/library", macros)
        self.statusBar().showMessage(f"Deleted macro '{name}'", 2200)

    def favorite_command_ids(self) -> list[str]:
        raw = self.load_json_setting("favorites/commands", [])
        if not isinstance(raw, list):
            return []
        return [str(command_id) for command_id in raw if str(command_id) in self.command_actions]

    def save_favorite_command_ids(self, values: list[str]) -> None:
        deduped: list[str] = []
        for command_id in values:
            if command_id in self.command_actions and command_id not in deduped:
                deduped.append(command_id)
        self.save_json_setting("favorites/commands", deduped)

    def refresh_favorites_toolbar(self) -> None:
        if self.favorite_toolbar is None:
            return
        self.favorite_toolbar.clear()
        favorite_ids = self.favorite_command_ids()
        if not favorite_ids:
            self.favorite_toolbar.setVisible(False)
            return
        self.favorite_toolbar.setVisible(True)
        for command_id in favorite_ids:
            source = self.command_actions.get(command_id)
            if not source:
                continue
            action = QAction(source.text(), self.favorite_toolbar)
            action.setToolTip(source.toolTip())
            action.triggered.connect(lambda _checked=False, source=source: source.trigger())
            self.favorite_toolbar.addAction(action)
        self.favorite_toolbar.addSeparator()
        add_action = QAction("+", self.favorite_toolbar)
        add_action.setToolTip("Pin another command to Favorites.")
        add_action.triggered.connect(self.add_favorite_command)
        self.favorite_toolbar.addAction(add_action)

    def add_favorite_command(self) -> None:
        commands = sorted(
            (action.text(), command_id)
            for command_id, action in self.command_actions.items()
            if command_id not in self.macro_control_command_ids()
        )
        labels = [label for label, _command_id in commands]
        label, accepted = QInputDialog.getItem(self, "Add Favorite Command", "Command:", labels, 0, False)
        if not accepted or not label:
            return
        command_id = next(command_id for item_label, command_id in commands if item_label == label)
        values = self.favorite_command_ids()
        values.append(command_id)
        self.save_favorite_command_ids(values)
        self.refresh_favorites_toolbar()

    def remove_favorite_command(self) -> None:
        favorites = self.favorite_command_ids()
        if not favorites:
            return
        labels = [self.command_actions[command_id].text() for command_id in favorites]
        label, accepted = QInputDialog.getItem(self, "Remove Favorite Command", "Command:", labels, 0, False)
        if not accepted or not label:
            return
        remove_id = favorites[labels.index(label)]
        self.save_favorite_command_ids([command_id for command_id in favorites if command_id != remove_id])
        self.refresh_favorites_toolbar()

    def show_radial_tool_menu(self, *_args) -> None:
        if self.radial_tool_menu is not None:
            self.radial_tool_menu.close()
            self.radial_tool_menu.deleteLater()
            self.radial_tool_menu = None
        tools = [
            EditorTool.SELECT,
            EditorTool.LASSO,
            EditorTool.LINE,
            EditorTool.CURVE,
            EditorTool.FREE_CURVE,
            EditorTool.ARC,
            EditorTool.CIRCLE,
            EditorTool.RECTANGLE,
            EditorTool.SVG_SHAPE,
            EditorTool.SCALE,
            EditorTool.WARP,
            EditorTool.ROTATE,
            EditorTool.MIRROR,
            EditorTool.SHAPE_LINE,
            EditorTool.SCATTER,
        ]
        menu = RadialToolMenu(self, tools)
        menu.destroyed.connect(lambda _obj=None: setattr(self, "radial_tool_menu", None))
        self.radial_tool_menu = menu
        menu.show_at(QCursor.pos())

    def opengl_renderer_enabled(self) -> bool:
        return self.settings.value("performance/opengl_field_renderer", False, type=bool)

    def set_opengl_renderer_enabled(self, enabled: bool = True) -> None:
        active = bool(enabled)
        if active and QOpenGLWidget is None:
            QMessageBox.warning(self, "OpenGL Renderer", "Qt OpenGL support is not available in this build.")
            active = False
        self.settings.setValue("performance/opengl_field_renderer", active)
        self.settings.sync()
        if hasattr(self, "opengl_action"):
            self.opengl_action.blockSignals(True)
            self.opengl_action.setChecked(active)
            self.opengl_action.blockSignals(False)
        self.apply_field_renderer()

    def apply_field_renderer(self) -> None:
        active = self.opengl_renderer_enabled() and QOpenGLWidget is not None
        if active:
            if self._opengl_renderer_active:
                return
            self.field.setViewport(QOpenGLWidget())
            self.field.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
            self.statusBar().showMessage("OpenGL field renderer enabled", 2200)
            self._opengl_renderer_active = True
        elif self._opengl_renderer_active:
            self.field.setViewport(QWidget())
            self.field.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
            self._opengl_renderer_active = False
        else:
            self.field.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.field.viewport().installEventFilter(self)
        if hasattr(self, "field_hud"):
            self.field_hud.setParent(self.field.viewport())
            self.field_hud.show()
            self.update_field_hud_visibility()
        if hasattr(self, "minimap"):
            self.minimap.setParent(self.field.viewport())
            self.minimap.setVisible(self.minimap_visible())
            self.position_minimap()

    def tooltips_enabled(self) -> bool:
        return self.settings.value("ui/tooltips_enabled", True, type=bool)

    def register_tooltip(self, widget: QWidget, text: str) -> None:
        widget.setProperty("drill_tooltip_text", text)
        widget.setToolTipDuration(12000)
        widget.setToolTip(text if self.tooltips_enabled() else "")
        if widget not in self.tooltip_widgets:
            self.tooltip_widgets.append(widget)

    def register_action_tooltip(self, action: QAction, text: str) -> None:
        action.setProperty("drill_tooltip_text", text)
        action.setToolTip(text if self.tooltips_enabled() else "")
        action.setStatusTip(text)
        if action not in self.tooltip_actions:
            self.tooltip_actions.append(action)

    def apply_tooltips_enabled(self, enabled: bool | None = None) -> None:
        active = self.tooltips_enabled() if enabled is None else bool(enabled)
        for widget in self.findChildren(QWidget):
            try:
                text = widget.property("drill_tooltip_text")
                if text is None and widget.toolTip():
                    text = widget.toolTip()
                    widget.setProperty("drill_tooltip_text", text)
                    if widget not in self.tooltip_widgets:
                        self.tooltip_widgets.append(widget)
                if text is not None:
                    widget.setToolTip(str(text) if active else "")
                    widget.setToolTipDuration(12000)
            except RuntimeError:
                continue
        valid_actions: list[QAction] = []
        for action in self.tooltip_actions:
            try:
                text = action.property("drill_tooltip_text")
                if text is not None:
                    action.setToolTip(str(text) if active else "")
                valid_actions.append(action)
            except RuntimeError:
                continue
        self.tooltip_actions = valid_actions
        if hasattr(self, "tool_hint_label"):
            self.tool_hint_label.setVisible(active)

    def apply_dot_symbol(self, symbol: str) -> None:
        self.field.set_dot_symbol(symbol)
        self.set_count(self.current_count, seek_audio=False)
        self.refresh_selected_paths()

    def unique_command_id(self, text: str) -> str:
        base = "".join(char.lower() if char.isalnum() else "_" for char in text).strip("_")
        base = base or "command"
        command_id = base
        suffix = 2
        while command_id in self.command_actions:
            command_id = f"{base}_{suffix}"
            suffix += 1
        return command_id

    def shortcut_text(self, shortcut) -> str:
        if not shortcut:
            return ""
        return QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.NativeText)

    def sorted_command_actions(self) -> list[tuple[str, QAction]]:
        return sorted(
            (
                (command_id, action)
                for command_id, action in self.command_actions.items()
                if action.text().strip()
            ),
            key=lambda item: item[1].text().lower(),
        )

    def configure_command_table(self, table: QTableWidget) -> None:
        table.setHorizontalHeaderLabels(["Command", "Shortcut"])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(1, 250)
        table.setMinimumWidth(720)

    def shortcut_conflicts(self, command_id: str, shortcut: QKeySequence) -> list[str]:
        portable = shortcut.toString(QKeySequence.SequenceFormat.PortableText)
        if not portable:
            return []
        conflicts: list[str] = []
        for other_id, action in self.command_actions.items():
            if other_id == command_id:
                continue
            other_shortcut = action.shortcut().toString(QKeySequence.SequenceFormat.PortableText)
            if other_shortcut == portable:
                conflicts.append(action.text())
        return conflicts

    def show_command_palette(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Command Palette")
        dialog.resize(900, 540)
        layout = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText("Search commands...")
        table = QTableWidget(0, 2)
        self.configure_command_table(table)
        layout.addWidget(search)
        layout.addWidget(table, 1)
        hint = QLabel("Enter runs the selected command. Shortcuts are shown in a separate column.")
        layout.addWidget(hint)

        def refresh() -> None:
            query = search.text().strip().lower()
            rows = [
                (command_id, action)
                for command_id, action in self.sorted_command_actions()
                if not query
                or query in action.text().lower()
                or query in action.shortcut().toString(QKeySequence.SequenceFormat.NativeText).lower()
            ]
            table.setRowCount(len(rows))
            for row, (command_id, action) in enumerate(rows):
                command_item = QTableWidgetItem(action.text())
                command_item.setData(Qt.ItemDataRole.UserRole, command_id)
                shortcut_text = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
                shortcut_item = QTableWidgetItem(shortcut_text)
                shortcut_item.setToolTip(shortcut_text)
                shortcut_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, 0, command_item)
                table.setItem(row, 1, shortcut_item)
            if rows:
                table.selectRow(0)

        def run_selected() -> None:
            row = table.currentRow()
            if row < 0 and table.rowCount():
                row = 0
            item = table.item(row, 0) if row >= 0 else None
            if not item:
                return
            command_id = str(item.data(Qt.ItemDataRole.UserRole))
            action = self.command_actions.get(command_id)
            if not action:
                return
            dialog.accept()
            action.trigger()

        search.textChanged.connect(refresh)
        search.returnPressed.connect(run_selected)
        table.itemDoubleClicked.connect(lambda _item: run_selected())
        refresh()
        search.setFocus()
        dialog.exec()

    def show_shortcut_editor(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Keyboard Shortcuts")
        dialog.resize(920, 600)
        layout = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText("Search commands...")
        table = QTableWidget(0, 2)
        self.configure_command_table(table)
        sequence_editor = QKeySequenceEdit()
        if hasattr(sequence_editor, "setClearButtonEnabled"):
            sequence_editor.setClearButtonEnabled(True)
        button_row = QGridLayout()
        apply_button = QPushButton("Apply Shortcut")
        clear_button = QPushButton("Clear")
        reset_button = QPushButton("Reset Selected")
        reset_all_button = QPushButton("Reset All")
        import_button = QPushButton("Import")
        export_button = QPushButton("Export")
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        for column, button in enumerate((apply_button, clear_button, reset_button, reset_all_button)):
            button_row.addWidget(button, 0, column)
        button_row.addWidget(import_button, 1, 0)
        button_row.addWidget(export_button, 1, 1)
        button_row.setColumnStretch(2, 1)
        button_row.addWidget(close_button, 1, 3)
        layout.addWidget(search)
        layout.addWidget(table, 1)
        layout.addWidget(QLabel("New Shortcut"))
        layout.addWidget(sequence_editor)
        layout.addLayout(button_row)

        def refresh() -> None:
            query = search.text().strip().lower()
            rows = [
                (command_id, action)
                for command_id, action in self.sorted_command_actions()
                if not query
                or query in action.text().lower()
                or query in action.shortcut().toString(QKeySequence.SequenceFormat.NativeText).lower()
            ]
            table.setRowCount(len(rows))
            for row, (command_id, action) in enumerate(rows):
                command_item = QTableWidgetItem(action.text())
                command_item.setData(Qt.ItemDataRole.UserRole, command_id)
                shortcut_text = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
                shortcut_item = QTableWidgetItem(shortcut_text)
                shortcut_item.setToolTip(shortcut_text)
                shortcut_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, 0, command_item)
                table.setItem(row, 1, shortcut_item)
            if rows:
                table.selectRow(0)
                update_editor()

        def selected_command_id() -> str:
            row = table.currentRow()
            item = table.item(row, 0) if row >= 0 else None
            return str(item.data(Qt.ItemDataRole.UserRole)) if item else ""

        def update_editor() -> None:
            action = self.command_actions.get(selected_command_id())
            sequence_editor.setKeySequence(action.shortcut() if action else QKeySequence())

        def set_shortcut(command_id: str, shortcut: QKeySequence, persist: bool = True) -> None:
            action = self.command_actions.get(command_id)
            if not action:
                return
            conflicts = self.shortcut_conflicts(command_id, shortcut)
            if conflicts:
                QMessageBox.warning(
                    dialog,
                    "Shortcut Conflict",
                    f"{shortcut.toString(QKeySequence.SequenceFormat.NativeText)} is already assigned to "
                    f"{', '.join(conflicts)}. Clear that command first or choose another shortcut.",
                )
                return
            action.setShortcut(shortcut)
            if persist:
                self.settings.setValue(
                    f"shortcuts/{command_id}",
                    shortcut.toString(QKeySequence.SequenceFormat.PortableText),
                )
            self.settings.sync()
            refresh()

        def export_shortcuts() -> None:
            path, _ = QFileDialog.getSaveFileName(
                dialog,
                "Export Keyboard Shortcuts",
                str(Path.home() / "drill_pirate_shortcuts.json"),
                "JSON Files (*.json);;All Files (*)",
            )
            if not path:
                return
            data = {
                command_id: action.shortcut().toString(QKeySequence.SequenceFormat.PortableText)
                for command_id, action in self.command_actions.items()
            }
            try:
                Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception as exc:
                QMessageBox.warning(
                    dialog,
                    "Shortcut Export Failed",
                    actionable_error_message("export keyboard shortcuts", exc, location=path),
                )
                return
            self.statusBar().showMessage("Keyboard shortcuts exported", 2400)

        def import_shortcuts() -> None:
            path, _ = QFileDialog.getOpenFileName(
                dialog,
                "Import Keyboard Shortcuts",
                str(Path.home()),
                "JSON Files (*.json);;All Files (*)",
            )
            if not path:
                return
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception as exc:
                QMessageBox.warning(
                    dialog,
                    "Shortcut Import Failed",
                    actionable_error_message("import keyboard shortcuts", exc, location=path),
                )
                return
            if not isinstance(data, dict):
                QMessageBox.warning(dialog, "Import Failed", "Shortcut file must be a JSON object.")
                return
            imported = 0
            skipped: list[str] = []
            for command_id, shortcut_text_value in data.items():
                action = self.command_actions.get(str(command_id))
                if not action:
                    continue
                shortcut = QKeySequence(str(shortcut_text_value))
                conflicts = self.shortcut_conflicts(str(command_id), shortcut)
                if conflicts:
                    skipped.append(action.text())
                    continue
                action.setShortcut(shortcut)
                self.settings.setValue(
                    f"shortcuts/{command_id}",
                    shortcut.toString(QKeySequence.SequenceFormat.PortableText),
                )
                imported += 1
            self.settings.sync()
            refresh()
            message = f"Imported {imported} shortcut(s)."
            if skipped:
                message += f" Skipped conflicts: {', '.join(skipped[:6])}"
                if len(skipped) > 6:
                    message += f" and {len(skipped) - 6} more."
            QMessageBox.information(dialog, "Keyboard Shortcuts", message)

        def apply_selected() -> None:
            command_id = selected_command_id()
            if command_id:
                set_shortcut(command_id, sequence_editor.keySequence())

        def clear_selected() -> None:
            command_id = selected_command_id()
            if command_id:
                set_shortcut(command_id, QKeySequence())

        def reset_selected() -> None:
            command_id = selected_command_id()
            if not command_id:
                return
            self.settings.remove(f"shortcuts/{command_id}")
            default = self.command_defaults.get(command_id, "")
            set_shortcut(command_id, QKeySequence(default), persist=False)

        def reset_all() -> None:
            for command_id, action in self.command_actions.items():
                self.settings.remove(f"shortcuts/{command_id}")
                action.setShortcut(QKeySequence(self.command_defaults.get(command_id, "")))
            self.settings.sync()
            refresh()

        search.textChanged.connect(refresh)
        table.itemSelectionChanged.connect(update_editor)
        apply_button.clicked.connect(apply_selected)
        clear_button.clicked.connect(clear_selected)
        reset_button.clicked.connect(reset_selected)
        reset_all_button.clicked.connect(reset_all)
        import_button.clicked.connect(import_shortcuts)
        export_button.clicked.connect(export_shortcuts)
        refresh()
        dialog.exec()

    def open_preferences(self) -> None:
        handler = getattr(self.window(), "show_preferences", None)
        if callable(handler):
            handler()

    def saved_audio_output_device_id(self) -> str:
        return normalize_audio_output_device_id(
            self.settings.value(AUDIO_OUTPUT_DEVICE_SETTING, DEFAULT_AUDIO_OUTPUT_DEVICE_ID)
        )

    def schedule_audio_output_refresh(self) -> None:
        self.audio_device_refresh_timer.start()

    def apply_saved_audio_output_device(self) -> None:
        self.apply_audio_output_device(self.saved_audio_output_device_id(), show_status=False)

    def recover_saved_audio_output_device(self) -> None:
        self.schedule_audio_recovery("Windows audio outputs changed")

    def replace_audio_output(self, device) -> None:
        volume = self.audio_output.volume()
        previous_output = self.audio_output
        replacement = QAudioOutput(self)
        replacement.setVolume(volume)
        replacement.setDevice(device)
        self.player.setAudioOutput(replacement)
        self.audio_output = replacement
        previous_output.deleteLater()

    def apply_audio_output_device(
        self,
        device_id: str,
        show_status: bool = True,
        *,
        force_recreate: bool = False,
    ) -> bool:
        if not force_recreate:
            self.audio_recovery_policy.reset()
        normalized = normalize_audio_output_device_id(device_id)
        device = audio_output_for_id(normalized)
        if device.isNull():
            if show_status:
                self.statusBar().showMessage("No audio output devices available", 3000)
            return False

        target_physical_id = audio_device_id(device)
        current_device = self.audio_output.device()
        current_physical_id = "" if current_device.isNull() else audio_device_id(current_device)
        already_requested = self.requested_audio_output_device_id == normalized
        already_on_target = (
            current_physical_id == target_physical_id
            and self.applied_audio_output_physical_id == target_physical_id
        )
        if already_requested and already_on_target and not force_recreate:
            if show_status:
                self.statusBar().showMessage(f"Audio output: {audio_output_label_for_id(normalized)}", 3000)
            return True
        if current_physical_id == target_physical_id and not force_recreate:
            self.requested_audio_output_device_id = normalized
            self.applied_audio_output_physical_id = target_physical_id
            if show_status:
                self.statusBar().showMessage(f"Audio output: {audio_output_label_for_id(normalized)}", 3000)
            return True

        was_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        position = self.player.position()
        if was_playing:
            self.player.pause()
        self.replace_audio_output(device)
        self.requested_audio_output_device_id = normalized
        self.applied_audio_output_physical_id = target_physical_id
        if self.player.source().isValid():
            self.player.setPosition(position)
        if was_playing:
            QTimer.singleShot(recommended_audio_resume_delay_ms(device.description()), self.player.play)
        if show_status:
            self.statusBar().showMessage(f"Audio output: {audio_output_label_for_id(normalized)}", 3000)
        return True

    def audio_playback_error(self, _error, message: str) -> None:
        if is_recoverable_audio_device_error(message):
            self.schedule_audio_recovery(message)
            return
        if message:
            self.statusBar().showMessage(f"Audio playback error: {message}", 5000)

    def schedule_audio_recovery(self, reason: str) -> None:
        delay = self.audio_recovery_policy.schedule(reason)
        if delay is None:
            return
        if self.play_timer.isActive() or self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.audio_recovery_resume_requested = True
            self.audio_recovery_position_ms = max(self.player.position(), self.last_playback_audio_ms)
            self.play_timer.stop()
            self.player.pause()
        elif not self.audio_recovery_resume_requested:
            self.audio_recovery_position_ms = self.player.position()
        self.statusBar().showMessage("Audio device changed; reconnecting safely…", 3000)
        QTimer.singleShot(delay, self.recover_audio_output)

    def recover_audio_output(self) -> None:
        requested = self.saved_audio_output_device_id()
        success = self.apply_audio_output_device(
            requested,
            show_status=False,
            force_recreate=True,
        )
        self.audio_recovery_policy.completed(success)
        if not success:
            self.statusBar().showMessage("Audio output unavailable; waiting for Windows…", 4000)
            QTimer.singleShot(500, lambda: self.schedule_audio_recovery("No usable audio output"))
            return
        if self.player.source().isValid():
            self.player.setPosition(self.audio_recovery_position_ms)
        resume = self.audio_recovery_resume_requested
        self.audio_recovery_resume_requested = False
        if resume:
            device = self.audio_output.device()
            delay = recommended_audio_resume_delay_ms(device.description() if not device.isNull() else "")
            QTimer.singleShot(delay, self.resume_after_audio_recovery)
        self.statusBar().showMessage(f"Audio output restored: {audio_output_label_for_id(requested)}", 3500)

    def resume_after_audio_recovery(self) -> None:
        if self.player.source().isValid():
            self.player.play()
        self.playback_clock.restart()
        self.play_timer.start()

    def check_audio_output_health(self) -> None:
        requested = self.saved_audio_output_device_id()
        target = audio_output_for_id(requested)
        current = self.audio_output.device()
        if target.isNull():
            if not current.isNull():
                return
            self.schedule_audio_recovery("No Windows audio output is available")
            return
        target_id = audio_device_id(target)
        current_id = "" if current.isNull() else audio_device_id(current)
        available_ids = {audio_device_id(device) for device in audio_output_devices()}
        current_missing = bool(current_id) and current_id not in available_ids
        if current.isNull() or current_missing or target_id != current_id:
            self.schedule_audio_recovery("Audio output disconnected or Windows default changed")

    def register_plugin_form_tool(
        self,
        plugin_id: str,
        name: str,
        callback: Callable[[FormToolContext], Any],
        shortcut: str | None = None,
        min_selected: int = 2,
        tooltip: str = "",
        settings: list[dict[str, Any]] | None = None,
    ) -> str:
        safe_name = "".join(char if char.isalnum() else "_" for char in name.lower()).strip("_")
        tool_id = f"{plugin_id}:{safe_name or 'tool'}"
        if tool_id in self.plugin_form_tools:
            self.remove_plugin_form_tool(tool_id)

        self.plugin_form_tools[tool_id] = PluginFormTool(
            plugin_id=plugin_id,
            tool_id=tool_id,
            name=name,
            callback=callback,
            min_selected=max(1, int(min_selected)),
            settings=self.normalize_plugin_settings(settings or []),
        )
        button = QPushButton(name)
        button.setCheckable(True)
        self.register_tooltip(button, tooltip or f"Plugin form tool from {plugin_id}")
        button.setMaximumHeight(28)
        button.clicked.connect(lambda _checked=False, selected=tool_id: self.activate_plugin_form_tool(selected))
        self.plugin_form_tool_buttons[tool_id] = button
        self.plugin_form_tool_layout.addWidget(button)
        self.plugin_form_tool_group.setVisible(True)
        self.plugin_contribution_widgets.setdefault(plugin_id, []).append(button)

        action = self.menu_action(
            name,
            lambda _checked=False, selected=tool_id: self.activate_plugin_form_tool(selected),
            QKeySequence(shortcut) if shortcut else None,
        )
        if tooltip:
            self.register_action_tooltip(action, tooltip)
        self.plugin_tools_menu.addAction(action)
        self.addAction(action)
        self.plugin_contribution_actions.setdefault(plugin_id, []).append((self.plugin_tools_menu, action))
        return tool_id

    def remove_plugin_form_tool(self, tool_id: str) -> None:
        tool = self.plugin_form_tools.pop(tool_id, None)
        if tool is None:
            return
        if self.active_plugin_form_tool_id == tool_id:
            self.active_plugin_form_tool_id = ""
            self.set_tool(EditorTool.SELECT)
        for widget in list(self.plugin_contribution_widgets.get(tool.plugin_id, [])):
            if isinstance(widget, QPushButton) and widget.text() == tool.name:
                if widget in self.tooltip_widgets:
                    self.tooltip_widgets.remove(widget)
                widget.setParent(None)
                widget.deleteLater()
                self.plugin_contribution_widgets[tool.plugin_id].remove(widget)
        self.plugin_form_tool_buttons.pop(tool_id, None)
        for widget in self.plugin_form_tool_setting_widgets.pop(tool_id, {}).values():
            if widget in self.tooltip_widgets:
                self.tooltip_widgets.remove(widget)
            widget.deleteLater()
        for menu, action in list(self.plugin_contribution_actions.get(tool.plugin_id, [])):
            if action.text() == tool.name:
                menu.removeAction(action)
                self.removeAction(action)
                command_id = action.property("command_id")
                if command_id:
                    self.command_actions.pop(str(command_id), None)
                    self.command_defaults.pop(str(command_id), None)
                if action in self.tooltip_actions:
                    self.tooltip_actions.remove(action)
                action.deleteLater()
                self.plugin_contribution_actions[tool.plugin_id].remove((menu, action))
        self.plugin_form_tool_group.setVisible(bool(self.plugin_form_tools))

    def activate_plugin_form_tool(self, tool_id: str) -> None:
        tool = self.plugin_form_tools.get(tool_id)
        if tool is None:
            return
        self.active_plugin_form_tool_id = tool_id
        self.field.set_tool(EditorTool.PLUGIN_FORM)
        self.preview_center_offset = (0.0, 0.0)
        for button_tool_id, button in self.plugin_form_tool_buttons.items():
            button.setChecked(button_tool_id == tool_id)
        for button in self.tool_buttons.values():
            button.setChecked(False)
        for button in self.field_hud_buttons.values():
            button.setChecked(False)
        if hasattr(self, "field_hud_hint"):
            self.field_hud_hint.setText(tool.name)
            self.field_hud_hint.setToolTip(f"{tool.name}: drag handles · Ctrl+Enter apply · Esc clear")
        self.rebuild_plugin_tool_options(tool)
        self.update_tool_edit_visibility()
        self.update_field_hud_visibility()
        self.update_formation_preview()

    def apply_plugin_form_tool(self, tool_id: str) -> None:
        self.activate_plugin_form_tool(tool_id)

    def record_plugin_error(self, plugin_id: str, message: str, detail: str = "") -> None:
        manager = getattr(self, "plugin_manager", None)
        manifest = manager.manifest_for_id(plugin_id) if manager and hasattr(manager, "manifest_for_id") else None
        if manifest and hasattr(manager, "record_diagnostic"):
            manager.record_diagnostic(manifest, "error", message, detail)

    def apply_active_plugin_form_tool_preview(self) -> None:
        tool = self.plugin_form_tools.get(self.active_plugin_form_tool_id)
        if tool is None:
            return
        ids, positions = self.selected_positions()
        if len(ids) < tool.min_selected:
            QMessageBox.information(
                self,
                "Plugin Form Tool",
                f"Select at least {tool.min_selected} marcher(s) for {tool.name}.",
            )
            return
        center = (
            sum(x for x, _y in positions) / len(positions),
            sum(y for _x, y in positions) / len(positions),
        )
        bounds_width = max(x for x, _y in positions) - min(x for x, _y in positions)
        bounds_height = max(y for _x, y in positions) - min(y for _x, y in positions)
        context = FormToolContext(
            window=self,
            project=self.project,
            set_index=self.set_index,
            dot_ids=ids,
            positions=positions,
            center=center,
            bounds_width=bounds_width,
            bounds_height=bounds_height,
            settings=self.plugin_setting_values(tool.tool_id),
        )
        try:
            result = tool.callback(context)
        except Exception as exc:
            self.record_plugin_error(tool.plugin_id, f"{tool.name} failed while applying", traceback.format_exc())
            QMessageBox.warning(self, "Plugin Tool Failed", f"{tool.name} failed:\n{exc}")
            return
        targets = self.snap_form_mapping_to_grid(self.normalize_plugin_targets(ids, result))
        if not targets:
            return
        self.apply_plugin_targets(tool.name, targets)
        self.active_plugin_form_tool_id = ""
        self.field.clear_preview()
        self.preview_center_offset = (0.0, 0.0)
        self.set_tool(EditorTool.SELECT)

    def normalize_plugin_targets(
        self,
        ids: list[str],
        result: Any,
    ) -> dict[str, tuple[float, float]]:
        if result is None:
            return {}
        if isinstance(result, dict):
            targets: dict[str, tuple[float, float]] = {}
            for dot_id, position in result.items():
                if dot_id in ids and isinstance(position, (tuple, list)) and len(position) >= 2:
                    targets[str(dot_id)] = (float(position[0]), float(position[1]))
            return targets
        if isinstance(result, (list, tuple)):
            if len(result) != len(ids):
                QMessageBox.warning(
                    self,
                    "Plugin Tool Failed",
                    f"Plugin returned {len(result)} positions for {len(ids)} selected marchers.",
                )
                return {}
            target_points: list[tuple[float, float]] = []
            for position in result:
                if not isinstance(position, (tuple, list)) or len(position) < 2:
                    return {}
                target_points.append((float(position[0]), float(position[1])))
            return self.assign_targets_to_marchers(ids, target_points)
        QMessageBox.warning(self, "Plugin Tool Failed", "Plugin must return a dict or list of positions.")
        return {}

    def normalize_plugin_settings(self, settings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        used_names: set[str] = set()
        for index, setting in enumerate(settings):
            if not isinstance(setting, dict):
                continue
            raw_name = str(setting.get("name") or setting.get("id") or f"setting_{index + 1}")
            name = "".join(char if char.isalnum() or char == "_" else "_" for char in raw_name).strip("_")
            if not name:
                name = f"setting_{index + 1}"
            base_name = name
            suffix = 2
            while name in used_names:
                name = f"{base_name}_{suffix}"
                suffix += 1
            used_names.add(name)
            setting_type = str(setting.get("type") or "float").lower()
            if setting_type in {"number", "double"}:
                setting_type = "float"
            if setting_type in {"integer"}:
                setting_type = "int"
            if setting_type in {"select", "combo"}:
                setting_type = "choice"
            normalized.append(
                {
                    **setting,
                    "name": name,
                    "label": str(setting.get("label") or name.replace("_", " ").title()),
                    "type": setting_type,
                }
            )
        return normalized

    def rebuild_plugin_tool_options(self, tool: PluginFormTool) -> None:
        if not hasattr(self, "plugin_tool_form"):
            return
        while self.plugin_tool_form.rowCount():
            self.plugin_tool_form.removeRow(0)
        self.plugin_form_tool_setting_widgets.setdefault(tool.tool_id, {})
        self.plugin_tool_group.setTitle(tool.name)
        if not tool.settings:
            note = QLabel("This plugin has no adjustable settings.")
            note.setWordWrap(True)
            self.plugin_tool_form.addRow(note)
            return
        self.plugin_form_tool_setting_widgets[tool.tool_id] = {}
        for setting in tool.settings:
            widget = self.create_plugin_setting_widget(tool.tool_id, setting)
            self.plugin_form_tool_setting_widgets[tool.tool_id][setting["name"]] = widget
            self.plugin_tool_form.addRow(setting["label"], widget)

    def create_plugin_setting_widget(self, tool_id: str, setting: dict[str, Any]) -> QWidget:
        setting_type = str(setting.get("type", "float"))
        default = setting.get("default")
        if setting_type == "int":
            widget = QSpinBox()
            widget.setRange(int(setting.get("min", -9999)), int(setting.get("max", 9999)))
            widget.setSingleStep(int(setting.get("step", 1)))
            widget.setValue(int(default if default is not None else setting.get("min", 0)))
            if setting.get("suffix"):
                widget.setSuffix(str(setting["suffix"]))
            widget.valueChanged.connect(self.update_formation_preview)
            return widget
        if setting_type in {"bool", "checkbox"}:
            widget = QCheckBox(str(setting.get("text") or "Enabled"))
            widget.setChecked(bool(default))
            widget.toggled.connect(self.update_formation_preview)
            return widget
        if setting_type == "choice":
            widget = QComboBox()
            options = setting.get("options") or []
            for option in options:
                if isinstance(option, dict):
                    widget.addItem(str(option.get("label", option.get("value", ""))), option.get("value"))
                else:
                    widget.addItem(str(option), option)
            if default is not None:
                index = widget.findData(default)
                if index < 0:
                    index = widget.findText(str(default))
                if index >= 0:
                    widget.setCurrentIndex(index)
            widget.currentIndexChanged.connect(self.update_formation_preview)
            return widget
        if setting_type == "text":
            widget = QLineEdit(str(default or ""))
            widget.textChanged.connect(self.update_formation_preview)
            return widget

        widget = QDoubleSpinBox()
        widget.setRange(float(setting.get("min", -9999.0)), float(setting.get("max", 9999.0)))
        widget.setDecimals(int(setting.get("decimals", 2)))
        widget.setSingleStep(float(setting.get("step", 0.5)))
        widget.setValue(float(default if default is not None else setting.get("min", 0.0)))
        if setting.get("suffix"):
            widget.setSuffix(str(setting["suffix"]))
        widget.valueChanged.connect(self.update_formation_preview)
        return widget

    def plugin_setting_values(self, tool_id: str) -> dict[str, Any]:
        values: dict[str, Any] = {}
        tool = self.plugin_form_tools.get(tool_id)
        if not tool:
            return values
        widgets = self.plugin_form_tool_setting_widgets.get(tool_id, {})
        for setting in tool.settings:
            name = setting["name"]
            widget = widgets.get(name)
            if isinstance(widget, QDoubleSpinBox):
                values[name] = widget.value()
            elif isinstance(widget, QSpinBox):
                values[name] = widget.value()
            elif isinstance(widget, QCheckBox):
                values[name] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                data = widget.currentData()
                values[name] = data if data is not None else widget.currentText()
            elif isinstance(widget, QLineEdit):
                values[name] = widget.text()
            else:
                values[name] = setting.get("default")
        return values

    def plugin_formation_targets(self) -> dict[str, tuple[float, float]]:
        tool = self.plugin_form_tools.get(self.active_plugin_form_tool_id)
        if tool is None:
            return {}
        ids, positions = self.selected_positions()
        if len(ids) < tool.min_selected:
            return {}
        center = (
            sum(x for x, _y in positions) / len(positions),
            sum(y for _x, y in positions) / len(positions),
        )
        bounds_width = max(x for x, _y in positions) - min(x for x, _y in positions)
        bounds_height = max(y for _x, y in positions) - min(y for _x, y in positions)
        context = FormToolContext(
            window=self,
            project=self.project,
            set_index=self.set_index,
            dot_ids=ids,
            positions=positions,
            center=center,
            bounds_width=bounds_width,
            bounds_height=bounds_height,
            settings=self.plugin_setting_values(tool.tool_id),
        )
        try:
            return self.normalize_plugin_targets(ids, tool.callback(context))
        except Exception as exc:
            self.record_plugin_error(tool.plugin_id, f"{tool.name} preview failed", traceback.format_exc())
            self.statusBar().showMessage(f"{tool.name} preview failed: {exc}", 4000)
            return {}

    def plugin_formation_handles(self) -> dict[str, tuple[float, float]]:
        tool = self.plugin_form_tools.get(self.active_plugin_form_tool_id)
        if tool is None:
            return {}
        _ids, positions = self.selected_positions()
        if len(positions) < 2:
            return {}
        center_x = sum(x for x, _y in positions) / len(positions)
        center_y = sum(y for _x, y in positions) / len(positions)
        values = self.plugin_setting_values(tool.tool_id)
        handles: dict[str, tuple[float, float]] = {}
        for setting in tool.settings:
            handle = str(setting.get("handle") or "").lower()
            if not handle:
                continue
            name = setting["name"]
            try:
                value = float(values.get(name, setting.get("default", 0)))
            except (TypeError, ValueError):
                continue
            if handle == "width":
                handles[f"plugin_setting:{name}"] = (center_x + value / 2, center_y)
            elif handle == "height":
                handles[f"plugin_setting:{name}"] = (center_x, center_y + value / 2)
            elif handle == "radius":
                handles[f"plugin_setting:{name}"] = (center_x + value, center_y)
        return handles

    def update_plugin_setting_from_handle(self, name: str, x: float, y: float) -> bool:
        tool = self.plugin_form_tools.get(self.active_plugin_form_tool_id)
        if tool is None:
            return False
        widget = self.plugin_form_tool_setting_widgets.get(tool.tool_id, {}).get(name)
        setting = next((item for item in tool.settings if item["name"] == name), None)
        if setting is None or not isinstance(widget, (QDoubleSpinBox, QSpinBox)):
            return False
        _ids, positions = self.selected_positions()
        if len(positions) < 2:
            return False
        center_x = sum(pos_x for pos_x, _pos_y in positions) / len(positions)
        center_y = sum(pos_y for _pos_x, pos_y in positions) / len(positions)
        handle = str(setting.get("handle") or "").lower()
        if handle == "width":
            value = abs(x - center_x) * 2
        elif handle == "height":
            value = abs(y - center_y) * 2
        elif handle == "radius":
            value = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
        else:
            return False
        widget.setValue(value)
        return True

    def apply_plugin_targets(self, name: str, targets: dict[str, tuple[float, float]]) -> None:
        if self.editing_set_one_opening():
            self.apply_opening_positions(
                targets,
                sync_unchanged_set_one_endpoints=True,
                label=f"Plugin Tool: {name}",
            )
            return
        before = self.current_positions()
        after = dict(before)
        after.update(targets)
        before_anchors = self.clone_path_anchors(self.set_index)
        before_controls = self.clone_path_controls(self.set_index)
        before_counts = self.clone_count_positions(self.set_index)
        after_anchors = self.clone_path_anchors(self.set_index)
        after_controls = self.clone_path_controls(self.set_index)
        after_counts = self.clone_count_positions(self.set_index)
        for dot_id in targets:
            after_anchors.pop(dot_id, None)
            after_controls.pop(dot_id, None)
            after_counts.pop(dot_id, None)
        self.undo_stack.push(
            MoveDotsCommand(
                self,
                self.set_index,
                before,
                after,
                f"Plugin Tool: {name}",
                before_anchors,
                after_anchors,
                before_controls,
                after_controls,
                before_counts,
                after_counts,
            )
        )
        self.refresh_selected_paths()

    def add_plugin_menu_action(
        self,
        plugin_id: str,
        menu_name: str,
        text: str,
        callback: Callable[[], Any],
        shortcut: str | None = None,
    ) -> None:
        menu = self.plugin_named_menus.get(menu_name)
        if menu is None:
            menu = self.menuBar().addMenu(menu_name)
            self.plugin_named_menus[menu_name] = menu
        action = self.menu_action(text, callback, QKeySequence(shortcut) if shortcut else None)
        menu.addAction(action)
        self.addAction(action)
        self.plugin_contribution_actions.setdefault(plugin_id, []).append((menu, action))

    def add_plugin_panel_button(
        self,
        plugin_id: str,
        text: str,
        callback: Callable[[], Any],
        tooltip: str = "",
    ) -> None:
        button = QPushButton(text)
        if tooltip:
            self.register_tooltip(button, tooltip)
        button.setMaximumHeight(28)
        button.clicked.connect(callback)
        self.plugin_panel_layout.addWidget(button)
        self.plugin_panel_group.setVisible(True)
        self.plugin_contribution_widgets.setdefault(plugin_id, []).append(button)

    def remove_plugin_contributions(self, plugin_id: str | None = None) -> None:
        plugin_ids = [plugin_id] if plugin_id else list(
            set(self.plugin_contribution_actions) | set(self.plugin_contribution_widgets)
        )
        for current_plugin_id in plugin_ids:
            for menu, action in self.plugin_contribution_actions.pop(current_plugin_id, []):
                menu.removeAction(action)
                self.removeAction(action)
                command_id = action.property("command_id")
                if command_id:
                    self.command_actions.pop(str(command_id), None)
                    self.command_defaults.pop(str(command_id), None)
                if action in self.tooltip_actions:
                    self.tooltip_actions.remove(action)
                action.deleteLater()
            for widget in self.plugin_contribution_widgets.pop(current_plugin_id, []):
                if widget in self.tooltip_widgets:
                    self.tooltip_widgets.remove(widget)
                widget.setParent(None)
                widget.deleteLater()
            for tool_id, tool in list(self.plugin_form_tools.items()):
                if tool.plugin_id == current_plugin_id:
                    self.remove_plugin_form_tool(tool_id)
        self.plugin_form_tool_group.setVisible(bool(self.plugin_form_tools))
        self.plugin_panel_group.setVisible(bool(self.plugin_contribution_widgets))

    def build_layout(self) -> QWidget:
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )
        self.create_dock(
            "tools",
            "Design",
            self.scroll_panel(self.build_tools_panel(), 270),
            Qt.DockWidgetArea.LeftDockWidgetArea,
            minimum_width=250,
        )
        self.create_dock(
            "inspector",
            "Inspector",
            self.scroll_panel(self.build_inspector_panel(), 310),
            Qt.DockWidgetArea.RightDockWidgetArea,
            minimum_width=290,
        )
        self.create_dock(
            "timeline",
            "Timeline",
            self.build_timeline_panel(),
            Qt.DockWidgetArea.BottomDockWidgetArea,
            minimum_height=170,
        )
        self.resizeDocks(
            [self.dock_widgets["tools"], self.dock_widgets["inspector"]],
            [285, 330],
            Qt.Orientation.Horizontal,
        )
        self.resizeDocks([self.dock_widgets["timeline"]], [210], Qt.Orientation.Vertical)
        return self.field

    def polish_editor_layouts(self) -> None:
        """Apply shared spacing and wrapping rules to docked editor panels."""
        for key, dock in self.dock_widgets.items():
            dock_widget = dock.widget()
            if dock_widget is None:
                continue
            content_root = dock_widget.widget() if isinstance(dock_widget, QScrollArea) else dock_widget
            if content_root is None:
                continue
            for combo in content_root.findChildren(QComboBox):
                combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                combo.setMinimumContentsLength(8)
                combo.setSizePolicy(QSizePolicy.Policy.Expanding, combo.sizePolicy().verticalPolicy())
            for control_type in (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton, QToolButton, QCheckBox):
                for control in content_root.findChildren(control_type):
                    if isinstance(control, QLineEdit) and isinstance(control.parentWidget(), QAbstractSpinBox):
                        continue
                    comfortable_height = max(22, min(32, control.sizeHint().height()))
                    control.setMinimumHeight(max(control.minimumHeight(), comfortable_height))
            self.polish_panel_layout(
                content_root.layout(),
                wrap_all_forms=False,
            )
            for form_layout in content_root.findChildren(QFormLayout):
                self.polish_panel_layout(
                    form_layout,
                    wrap_all_forms=False,
                )
            for grid_layout in content_root.findChildren(QGridLayout):
                self.polish_panel_layout(
                    grid_layout,
                    wrap_all_forms=False,
                )
            for tab_widget in content_root.findChildren(QTabWidget):
                tab_widget.setDocumentMode(True)
                tab_widget.setUsesScrollButtons(True)
                tab_widget.setMinimumWidth(0)
                tab_widget.tabBar().setExpanding(False)
                tab_widget.tabBar().setElideMode(Qt.TextElideMode.ElideRight)
            for label in content_root.findChildren(QLabel):
                if (
                    len(label.text()) > 48
                    and " " in label.text()
                    and label.objectName() not in {"CoordinateReadout", "FieldHud"}
                ):
                    label.setWordWrap(True)
            if isinstance(dock_widget, AdaptivePanelScrollArea):
                dock_widget.schedule_content_resize()

    def polish_panel_layout(self, layout: QLayout | None, wrap_all_forms: bool = False) -> None:
        if layout is None:
            return
        if isinstance(layout, QFormLayout):
            layout.setRowWrapPolicy(
                QFormLayout.RowWrapPolicy.WrapAllRows
                if wrap_all_forms
                else QFormLayout.RowWrapPolicy.WrapLongRows
            )
            layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            layout.setHorizontalSpacing(8)
            layout.setVerticalSpacing(6)
        elif isinstance(layout, QGridLayout):
            layout.setHorizontalSpacing(max(6, layout.horizontalSpacing()))
            layout.setVerticalSpacing(max(5, layout.verticalSpacing()))
        for index in range(layout.count()):
            item = layout.itemAt(index)
            child_layout = item.layout() if item is not None else None
            if child_layout is not None:
                self.polish_panel_layout(child_layout, wrap_all_forms=wrap_all_forms)
            child_widget = item.widget() if item is not None else None
            if child_widget is not None and child_widget.layout() is not None:
                self.polish_panel_layout(child_widget.layout(), wrap_all_forms=wrap_all_forms)

    def build_field_hud(self) -> None:
        hud = DraggableFieldHud(self)
        hud.setObjectName("FieldHud")
        hud.setStyleSheet(self.field_hud_stylesheet())
        layout = QHBoxLayout(hud)
        layout.setContentsMargins(7, 4, 7, 4)
        layout.setSpacing(4)
        self.field_hud_hint = QLabel("Select")
        self.field_hud_hint.setMinimumWidth(74)
        self.field_hud_hint.setMaximumWidth(130)
        self.field_hud_hint.setToolTip(
            "Current field tool. Use the side panel, right-click field menu, or shortcuts to switch tools."
        )
        layout.addWidget(self.field_hud_hint)
        apply_button = QPushButton("Apply")
        apply_button.setToolTip("Apply the current preview. Shortcut: Ctrl+Enter.")
        apply_button.clicked.connect(self.apply_current_preview)
        clear_button = QPushButton("Clear")
        clear_button.setToolTip("Clear the current preview. Shortcut: Esc.")
        clear_button.clicked.connect(self.clear_formation_preview)
        self.field_hud_apply_button = apply_button
        self.field_hud_clear_button = clear_button
        layout.addWidget(apply_button)
        layout.addWidget(clear_button)
        self.field_hud = hud
        hud.adjustSize()
        hud.raise_()
        self.update_field_hud_visibility()
        QTimer.singleShot(0, self.position_field_hud)

    def field_hud_stylesheet(self) -> str:
        tokens = theme_tokens(str(self.settings.value("appearance/theme", "dark")), self.settings)
        panel = tokens["panel_color"]
        button = tokens["button_color"]
        text = tokens["text_color"]
        border = tokens["border_color"]
        accent = tokens["accent_color"]
        return f"""
            #FieldHud {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            #FieldHud QPushButton {{
                background: {button};
                color: {text};
                border: 1px solid {border};
                min-height: 20px;
                padding: 2px 7px;
            }}
            #FieldHud QPushButton:hover {{
                border-color: {accent};
            }}
            #FieldHud QLabel {{
                color: {text};
            }}
            """

    def apply_visual_theme(self, tokens: dict[str, str] | None = None) -> None:
        current_tokens = tokens or theme_tokens(str(self.settings.value("appearance/theme", "dark")), self.settings)
        if hasattr(self, "waveform"):
            self.waveform.set_theme_tokens(current_tokens)
        if hasattr(self, "transition_timeline"):
            self.transition_timeline.update()
        if hasattr(self, "conflict_heatmap"):
            self.conflict_heatmap.set_theme_tokens(current_tokens)
        if hasattr(self, "field_hud"):
            self.field_hud.setStyleSheet(self.field_hud_stylesheet())
        if hasattr(self, "minimap"):
            self.minimap.update()
        if hasattr(self, "set_list"):
            self.refresh_set_thumbnails()

    def minimap_visible(self) -> bool:
        return self.settings.value("view/show_minimap", True, type=bool)

    def set_minimap_visible(self, visible: bool = True) -> None:
        active = bool(visible)
        self.settings.setValue("view/show_minimap", active)
        self.settings.sync()
        if hasattr(self, "minimap_action"):
            self.minimap_action.blockSignals(True)
            self.minimap_action.setChecked(active)
            self.minimap_action.blockSignals(False)
        if hasattr(self, "show_minimap_checkbox"):
            self.show_minimap_checkbox.blockSignals(True)
            self.show_minimap_checkbox.setChecked(active)
            self.show_minimap_checkbox.blockSignals(False)
        if hasattr(self, "minimap"):
            self.minimap.setVisible(active)
            self.position_minimap()

    def field_hud_enabled(self) -> bool:
        return self.settings.value("view/show_field_hud", True, type=bool)

    def set_field_hud_enabled(self, visible: bool = True) -> None:
        active = bool(visible)
        self.settings.setValue("view/show_field_hud", active)
        self.settings.sync()
        if hasattr(self, "field_hud_action"):
            self.field_hud_action.blockSignals(True)
            self.field_hud_action.setChecked(active)
            self.field_hud_action.blockSignals(False)
        if hasattr(self, "show_field_hud_checkbox"):
            self.show_field_hud_checkbox.blockSignals(True)
            self.show_field_hud_checkbox.setChecked(active)
            self.show_field_hud_checkbox.blockSignals(False)
        self.update_field_hud_visibility()

    def transform_gizmo_visible(self) -> bool:
        migration_key = "view/transform_handles_opt_in_v2"
        if not self.settings.value(migration_key, False, type=bool):
            self.settings.setValue(migration_key, True)
            self.settings.setValue("view/show_transform_gizmo", False)
            self.settings.sync()
            return False
        return self.settings.value("view/show_transform_gizmo", False, type=bool)

    def set_transform_gizmo_visible(self, visible: bool = True) -> None:
        active = bool(visible)
        self.settings.setValue("view/show_transform_gizmo", active)
        self.settings.sync()
        if hasattr(self, "transform_gizmo_action"):
            self.transform_gizmo_action.blockSignals(True)
            self.transform_gizmo_action.setChecked(active)
            self.transform_gizmo_action.blockSignals(False)
        if hasattr(self, "transform_handles_button"):
            self.transform_handles_button.blockSignals(True)
            self.transform_handles_button.setChecked(active)
            self.transform_handles_button.setText(
                "Hide On-Field Handles" if active else "Show On-Field Handles"
            )
            self.transform_handles_button.blockSignals(False)
        self.field.set_transform_gizmo_enabled(active)
        self.sync_transform_handle_controls()
        if active and len(self.field.selected_dot_ids()) < 2:
            self.statusBar().showMessage("Select at least two marchers to show transform handles", 2600)

    def sync_transform_handle_controls(self) -> None:
        if not hasattr(self, "transform_handles_button"):
            return
        selected_count = len(self.field.selected_dot_ids())
        active = self.transform_gizmo_visible()
        self.transform_handles_button.blockSignals(True)
        self.transform_handles_button.setEnabled(selected_count >= 2)
        self.transform_handles_button.setChecked(active)
        self.transform_handles_button.setText(
            "Hide On-Field Handles" if active else "Show On-Field Handles"
        )
        self.transform_handles_button.setToolTip(
            "Select two or more marchers, then toggle compact move/rotate/scale handles. "
            "Shortcut: Ctrl+Shift+T."
        )
        self.transform_handles_button.blockSignals(False)

    def update_field_hud_visibility(self) -> None:
        if not hasattr(self, "field_hud"):
            return
        active_tool = getattr(self.field, "active_tool", EditorTool.SELECT)
        should_show = self.field_hud_enabled() and (
            active_tool != EditorTool.SELECT or bool(self.active_plugin_form_tool_id)
        )
        if hasattr(self, "field_hud_apply_button"):
            self.field_hud_apply_button.setVisible(True)
            self.field_hud_clear_button.setVisible(True)
            self.field_hud_hint.setText(active_tool.value.replace("_", " ").title())
            self.field_hud.adjustSize()
        self.field_hud.setVisible(should_show)
        if should_show:
            self.position_field_hud()

    def show_numeric_transform_controls(self) -> None:
        if hasattr(self, "inspector_tabs") and hasattr(self, "selection_tab"):
            self.inspector_tabs.setCurrentWidget(self.selection_tab)
        dock = self.dock_widgets.get("inspector")
        if dock:
            dock.show()
            dock.raise_()
        if hasattr(self, "transform_offset_x"):
            self.transform_offset_x.setFocus()
            self.transform_offset_x.selectAll()

    def move_field_hud_to(self, position: QPoint, persist: bool = True) -> None:
        if not hasattr(self, "field_hud"):
            return
        margin = 6
        max_x = max(margin, self.field.viewport().width() - self.field_hud.width() - margin)
        max_y = max(margin, self.field.viewport().height() - self.field_hud.height() - margin)
        x = max(margin, min(max_x, position.x()))
        y = max(margin, min(max_y, position.y()))
        self.field_hud.move(x, y)
        self.field_hud.raise_()
        if persist:
            self.save_field_hud_position()

    def save_field_hud_position(self) -> None:
        if not hasattr(self, "field_hud"):
            return
        self.field_hud_custom_position = True
        self.settings.setValue("view/field_hud_custom_position", True)
        self.settings.setValue("view/field_hud_x", self.field_hud.x())
        self.settings.setValue("view/field_hud_y", self.field_hud.y())
        self.settings.sync()

    def reset_field_hud_position(self) -> None:
        self.field_hud_custom_position = False
        self.settings.setValue("view/field_hud_custom_position", False)
        self.settings.remove("view/field_hud_x")
        self.settings.remove("view/field_hud_y")
        self.settings.sync()
        self.position_field_hud()

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        if hasattr(self, "field") and watched is self.field.viewport():
            if event.type() in (
                QEvent.Type.Resize,
                QEvent.Type.Wheel,
                QEvent.Type.Show,
                QEvent.Type.Hide,
            ):
                QTimer.singleShot(0, self.position_field_hud)
                QTimer.singleShot(0, self.position_minimap)
        return super().eventFilter(watched, event)

    def position_field_hud(self) -> None:
        if not hasattr(self, "field_hud"):
            return
        if not self.field_hud.isVisible():
            return
        self.field_hud.setMinimumWidth(0)
        self.field_hud.setMaximumWidth(16777215)
        self.field_hud.adjustSize()
        margin = 10
        max_width = max(180, self.field.viewport().width() - margin * 2)
        if self.field_hud.width() > max_width:
            self.field_hud.setFixedWidth(max_width)
        if self.field_hud_custom_position:
            x = int(self.settings.value("view/field_hud_x", margin))
            y = int(self.settings.value("view/field_hud_y", margin))
            self.move_field_hud_to(QPoint(x, y), persist=False)
            return
        x = max(margin, self.field.viewport().width() - self.field_hud.width() - margin)
        y = max(margin, self.field.viewport().height() - self.field_hud.height() - margin)
        self.field_hud.move(x, y)
        self.field_hud.raise_()

    def position_minimap(self) -> None:
        if not hasattr(self, "minimap"):
            return
        if not self.minimap.isVisible():
            return
        margin = 12
        viewport_width = max(1, self.field.viewport().width())
        viewport_height = max(1, self.field.viewport().height())
        width = min(220, max(150, int(viewport_width * 0.18)))
        width = min(width, max(96, viewport_width - margin * 2))
        height = max(88, int(width * 0.55))
        if height > viewport_height - margin * 2:
            height = max(64, viewport_height - margin * 2)
            width = max(118, int(height / 0.55))
            width = min(width, max(96, viewport_width - margin * 2))
        self.minimap.setFixedSize(width, height)
        x = margin
        y = max(margin, viewport_height - self.minimap.height() - margin)
        self.minimap.move(x, y)
        self.minimap.raise_()
        self.minimap.update()

    def toggle_field_focus(self) -> None:
        if not self.field_focus_active:
            self.apply_workspace("focus")
        else:
            self.apply_workspace("forms")

    def create_dock(
        self,
        key: str,
        title: str,
        widget: QWidget,
        area: Qt.DockWidgetArea,
        minimum_width: int = 0,
        minimum_height: int = 0,
    ) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"{key}Dock")
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        if minimum_width:
            dock.setMinimumWidth(minimum_width)
        if minimum_height:
            dock.setMinimumHeight(minimum_height)
        self.addDockWidget(area, dock)
        self.dock_widgets[key] = dock
        return dock

    def build_workspace_toolbar(self) -> None:
        toolbar = QToolBar("Editor Context", self)
        toolbar.setObjectName("PrimaryToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        project_title = QLabel(self.project.metadata.show_title)
        project_title.setObjectName("ProjectContextTitle")
        project_title.setMaximumWidth(260)
        project_title.setToolTip(self.project.metadata.show_title)
        toolbar.addWidget(project_title)
        toolbar.addSeparator()
        workspace_label = QLabel("Workspace")
        workspace_label.setObjectName("ToolbarCaption")
        toolbar.addWidget(workspace_label)
        self.workspace_selector = QComboBox()
        self.workspace_selector.setObjectName("WorkspaceSelector")
        self.workspace_selector.setMaximumWidth(150)
        for workspace_name, label in (
            ("design", "Design"),
            ("forms", "Form Editing"),
            ("rehearse", "Rehearsal"),
            ("music", "Music Design"),
            ("specialized", "Specialized"),
            ("print", "Print & Export"),
            ("focus", "Field Focus"),
        ):
            self.workspace_selector.addItem(label, workspace_name)
        self.workspace_selector.currentIndexChanged.connect(
            lambda index: self.apply_workspace(str(self.workspace_selector.itemData(index)))
        )
        toolbar.addWidget(self.workspace_selector)
        set_label = QLabel("Set")
        set_label.setObjectName("ToolbarCaption")
        toolbar.addWidget(set_label)
        self.toolbar_set_selector = QComboBox()
        self.toolbar_set_selector.setObjectName("ToolbarSetSelector")
        self.toolbar_set_selector.setMinimumContentsLength(12)
        self.toolbar_set_selector.setMaximumWidth(250)
        self.toolbar_set_selector.currentIndexChanged.connect(self.change_set_from_toolbar)
        toolbar.addWidget(self.toolbar_set_selector)
        toolbar.addSeparator()
        self.drill_grid_toolbar_toggle = QToolButton()
        self.drill_grid_toolbar_toggle.setCheckable(True)
        self.drill_grid_toolbar_toggle.setMinimumWidth(86)
        self.drill_grid_toolbar_toggle.setToolTip(
            "Snap marcher movement, on-form preview handles, and generated formations to exact drill-step spacing."
        )
        self.drill_grid_toolbar_toggle.toggled.connect(self.set_drill_grid_enabled)
        toolbar.addWidget(self.drill_grid_toolbar_toggle)
        self.drill_grid_toolbar_configure = QToolButton()
        self.drill_grid_toolbar_configure.setText("Grid Settings...")
        self.drill_grid_toolbar_configure.setToolTip(
            "Choose 8-to-5, 6-to-5, 12-to-5, 16-to-5, or a custom drill grid."
        )
        self.drill_grid_toolbar_configure.clicked.connect(self.show_drill_grid_dialog)
        toolbar.addWidget(self.drill_grid_toolbar_configure)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addAction(self.command_actions["command_palette"])
        favorites = QToolBar("Favorites", self)
        favorites.setObjectName("FavoritesToolbar")
        favorites.setMovable(True)
        favorites.setFloatable(False)
        favorites.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, favorites)
        self.favorite_toolbar = favorites
        self.refresh_favorites_toolbar()
        self.sync_drill_grid_controls()

    def restore_ui_layout(self) -> None:
        state = self.settings.value("main_window/dock_state")
        if state:
            self.restoreState(state)
        QTimer.singleShot(0, self.apply_responsive_layout)

    def migrate_editor_layout(self) -> None:
        layout_version = int(self.settings.value("main_window/layout_version", 0) or 0)
        if layout_version >= 3:
            return
        self.settings.remove("main_window/dock_state")
        self.settings.setValue("main_window/layout_version", 3)
        self.settings.sync()

    def reset_panel_layout(self) -> None:
        self.settings.remove("main_window/dock_state")
        for dock in self.dock_widgets.values():
            dock.setFloating(False)
            dock.show()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_widgets["tools"])
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_widgets["inspector"])
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock_widgets["timeline"])
        self.apply_workspace("design")
        self.apply_responsive_layout()
        self.statusBar().showMessage("Panel layout reset", 2200)

    def save_custom_workspace(self) -> None:
        self.settings.setValue("main_window/custom_workspace_state", self.saveState())
        self.settings.sync()
        self.statusBar().showMessage("Workspace saved", 2200)

    def restore_custom_workspace(self) -> None:
        state = self.settings.value("main_window/custom_workspace_state")
        if not state:
            self.statusBar().showMessage("No saved workspace yet", 2200)
            return
        self.restoreState(state)
        self.apply_responsive_layout()
        self.statusBar().showMessage("Saved workspace restored", 2200)

    def workspace_profiles(self) -> dict[str, str]:
        raw = self.settings.value("main_window/workspace_profiles", "{}")
        if not raw:
            return {}
        try:
            profiles = json.loads(str(raw))
        except json.JSONDecodeError:
            return {}
        return {str(key): str(value) for key, value in profiles.items()} if isinstance(profiles, dict) else {}

    def save_workspace_profiles(self, profiles: dict[str, str]) -> None:
        self.settings.setValue("main_window/workspace_profiles", json.dumps(profiles, indent=2, sort_keys=True))
        self.settings.sync()

    def save_workspace_profile(self) -> None:
        name, accepted = QInputDialog.getText(self, "Save Workspace Profile", "Profile name:")
        if not accepted or not name.strip():
            return
        profiles = self.workspace_profiles()
        profiles[name.strip()] = base64.b64encode(bytes(self.saveState())).decode("ascii")
        self.save_workspace_profiles(profiles)
        self.statusBar().showMessage(f"Workspace profile '{name.strip()}' saved", 2200)

    def load_workspace_profile(self) -> None:
        profiles = self.workspace_profiles()
        if not profiles:
            self.statusBar().showMessage("No saved workspace profiles", 2200)
            return
        name, accepted = QInputDialog.getItem(self, "Load Workspace Profile", "Profile:", sorted(profiles), 0, False)
        if not accepted or not name:
            return
        state = QByteArray(base64.b64decode(profiles[name]))
        if not self.restoreState(state):
            QMessageBox.warning(self, "Workspace Profile", "Could not restore that workspace profile.")
            return
        self.apply_responsive_layout()
        self.statusBar().showMessage(f"Workspace profile '{name}' loaded", 2200)

    def delete_workspace_profile(self) -> None:
        profiles = self.workspace_profiles()
        if not profiles:
            self.statusBar().showMessage("No saved workspace profiles", 2200)
            return
        name, accepted = QInputDialog.getItem(self, "Delete Workspace Profile", "Profile:", sorted(profiles), 0, False)
        if not accepted or not name:
            return
        profiles.pop(name, None)
        self.save_workspace_profiles(profiles)
        self.statusBar().showMessage(f"Workspace profile '{name}' deleted", 2200)

    def apply_responsive_layout(self) -> None:
        tools = self.dock_widgets.get("tools")
        inspector = self.dock_widgets.get("inspector")
        timeline = self.dock_widgets.get("timeline")
        if not tools or not inspector or not timeline:
            return
        available_width = max(0, self.width())
        available_height = max(0, self.height())
        if available_width < 1250 or available_height < 760:
            bucket = "compact"
            tools_width, inspector_width, timeline_height = 250, 290, 150
            tools_minimum, inspector_minimum, timeline_minimum = 235, 275, 130
        elif available_width < 1550 or available_height < 900:
            bucket = "laptop"
            tools_width, inspector_width, timeline_height = 270, 315, 175
            tools_minimum, inspector_minimum, timeline_minimum = 250, 290, 145
        else:
            bucket = "desktop"
            tools_width, inspector_width, timeline_height = 290, 340, 205
            tools_minimum, inspector_minimum, timeline_minimum = 265, 310, 155

        tools.setMinimumWidth(tools_minimum)
        inspector.setMinimumWidth(inspector_minimum)
        timeline.setMinimumHeight(timeline_minimum)
        if bucket == self._responsive_layout_bucket:
            return
        self._responsive_layout_bucket = bucket
        if tools.isVisible() and inspector.isVisible() and not tools.isFloating() and not inspector.isFloating():
            self.resizeDocks([tools, inspector], [tools_width, inspector_width], Qt.Orientation.Horizontal)
        if timeline.isVisible() and not timeline.isFloating():
            self.resizeDocks([timeline], [timeline_height], Qt.Orientation.Vertical)

    def apply_workspace(self, name: str) -> None:
        if hasattr(self, "workspace_selector"):
            selector_index = self.workspace_selector.findData(name)
            if selector_index >= 0 and selector_index != self.workspace_selector.currentIndex():
                self.workspace_selector.blockSignals(True)
                self.workspace_selector.setCurrentIndex(selector_index)
                self.workspace_selector.blockSignals(False)
        for dock in self.dock_widgets.values():
            dock.show()
        self.field_focus_active = False
        if name == "focus":
            tools_index = self.tools_tabs.indexOf(self.formation_tab)
            inspector_index = self.inspector_tabs.indexOf(self.selection_tab)
            if tools_index >= 0:
                self.tools_tabs.setCurrentIndex(tools_index)
            if inspector_index >= 0:
                self.inspector_tabs.setCurrentIndex(inspector_index)
            self.resizeDocks(
                [self.dock_widgets["tools"], self.dock_widgets["inspector"]],
                [240, 270],
                Qt.Orientation.Horizontal,
            )
            self.resizeDocks([self.dock_widgets["timeline"]], [130], Qt.Orientation.Vertical)
            self.field_focus_active = True
            self.position_field_hud()
            self.statusBar().showMessage("Focus workspace: panels kept visible, field expanded", 2200)
            return

        tools_index = 0
        inspector_index = 0
        if name == "forms":
            tools_index = self.tools_tabs.indexOf(self.formation_tab)
            inspector_index = self.inspector_tabs.indexOf(self.selection_tab)
            self.dock_widgets["timeline"].hide()
        elif name == "rehearse":
            tools_index = self.tools_tabs.indexOf(self.rehearsal_tab)
            inspector_index = self.inspector_tabs.indexOf(self.sets_tab)
        elif name == "music":
            tools_index = self.tools_tabs.indexOf(self.music_tab)
            inspector_index = self.inspector_tabs.indexOf(self.sets_tab)
        elif name == "specialized":
            tools_index = self.tools_tabs.indexOf(self.specialized_tab)
            inspector_index = self.inspector_tabs.indexOf(self.selection_tab)
        elif name == "print":
            tools_index = self.tools_tabs.indexOf(self.analysis_tab)
            inspector_index = self.inspector_tabs.indexOf(self.sets_tab)
            self.dock_widgets["timeline"].hide()
        else:
            tools_index = self.tools_tabs.indexOf(self.marchers_tab)
            inspector_index = self.inspector_tabs.indexOf(self.selection_tab)

        if tools_index >= 0:
            self.tools_tabs.setCurrentIndex(tools_index)
        if inspector_index >= 0:
            self.inspector_tabs.setCurrentIndex(inspector_index)
        self.position_field_hud()
        self.statusBar().showMessage(f"{name.title()} workspace applied", 2200)

    def scroll_panel(self, widget: QWidget, minimum_width: int) -> QScrollArea:
        scroll = AdaptivePanelScrollArea()
        scroll.setWidget(widget)
        scroll.setMinimumWidth(0)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setProperty("preferredPanelWidth", minimum_width)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        def page_changed(_index: int) -> None:
            scroll.verticalScrollBar().setValue(0)
            scroll.schedule_content_resize()

        for switcher in widget.findChildren(PanelPageSwitcher):
            switcher.currentChanged.connect(page_changed)
        for tab_widget in widget.findChildren(CompactTabWidget):
            tab_widget.currentChanged.connect(page_changed)
        scroll.schedule_content_resize()
        return scroll

    def build_tools_panel(self) -> QWidget:
        panel = ResponsivePanelWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        tabs = PanelPageSwitcher()
        self.tools_tabs = tabs
        layout.addWidget(tabs)

        marchers_tab = QWidget()
        self.marchers_tab = marchers_tab
        marchers_layout = QVBoxLayout(marchers_tab)
        marchers_layout.setContentsMargins(4, 4, 4, 4)
        marchers_header = QHBoxLayout()
        marchers_title = QLabel("Marchers")
        marchers_title.setStyleSheet("font-size: 14px; font-weight: 750;")
        add_button = QPushButton("Add")
        add_button.clicked.connect(self.add_marcher)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.delete_selected_marchers)
        marchers_header.addWidget(marchers_title)
        marchers_header.addStretch()
        marchers_header.addWidget(add_button)
        marchers_header.addWidget(delete_button)
        marchers_layout.addLayout(marchers_header)
        self.marcher_search = QLineEdit()
        self.marcher_search.setPlaceholderText("Search marchers...")
        self.marcher_search.textChanged.connect(self.filter_marcher_table)

        filter_group = QGroupBox("Filter & Select")
        filter_layout = QVBoxLayout(filter_group)
        filter_layout.setContentsMargins(6, 6, 6, 6)
        filter_layout.setSpacing(5)
        filter_layout.addWidget(self.marcher_search)
        filter_form = QFormLayout()
        filter_form.setContentsMargins(0, 0, 0, 0)
        self.marcher_filter_field = QComboBox()
        self.marcher_filter_field.addItem("All fields", "all")
        self.marcher_filter_field.addItem("Instrument", "instrument")
        self.marcher_filter_field.addItem("Section", "section")
        self.marcher_filter_field.addItem("Layer", "layer")
        self.marcher_filter_field.currentIndexChanged.connect(self.refresh_marcher_filter_values)
        self.marcher_filter_value = QComboBox()
        self.marcher_filter_value.currentIndexChanged.connect(self.filter_marcher_table)
        filter_form.addRow("By", self.marcher_filter_field)
        filter_form.addRow("Value", self.marcher_filter_value)
        filter_layout.addLayout(filter_form)
        select_visible_button = QPushButton("Select Shown")
        select_visible_button.setToolTip("Select every marcher currently shown by the search and filter.")
        select_visible_button.clicked.connect(self.select_visible_marchers)
        clear_selection_button = QPushButton("Clear Selection")
        clear_selection_button.clicked.connect(self.clear_marcher_selection)
        search_actions = QHBoxLayout()
        search_actions.addWidget(select_visible_button)
        search_actions.addWidget(clear_selection_button)
        filter_layout.addLayout(search_actions)
        self.marcher_filter_status = QLabel("0 shown • 0 selected")
        self.marcher_filter_status.setStyleSheet("color: #9da4ad; font-size: 11px;")
        filter_layout.addWidget(self.marcher_filter_status)
        marchers_layout.addWidget(filter_group)

        self.marcher_table = QTableWidget(0, 4)
        self.marcher_table.setHorizontalHeaderLabels(["", "Label", "Instrument", "Section"])
        self.marcher_table.setToolTip("Use Ctrl-click or Shift-click to select multiple marchers.")
        self.marcher_table.verticalHeader().setVisible(False)
        self.marcher_table.verticalHeader().setDefaultSectionSize(26)
        self.marcher_table.setAlternatingRowColors(True)
        self.marcher_table.setShowGrid(False)
        self.marcher_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.marcher_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.SelectedClicked
        )
        self.marcher_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.marcher_table.horizontalHeader().setMinimumSectionSize(44)
        self.marcher_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.marcher_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.marcher_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.marcher_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.marcher_table.setColumnWidth(0, 18)
        self.marcher_table.setColumnWidth(1, 72)
        self.marcher_table.setMinimumHeight(280)
        self.marcher_table.itemSelectionChanged.connect(self.select_marchers_from_table)
        self.marcher_table.cellDoubleClicked.connect(self.edit_marcher_table_cell)
        self.marcher_table.itemChanged.connect(self.update_marcher_from_table)
        marchers_layout.addWidget(self.marcher_table, 1)

        selection_set_group = QGroupBox("Selection Sets")
        selection_set_layout = QVBoxLayout(selection_set_group)
        selection_set_layout.setContentsMargins(6, 6, 6, 6)
        self.selection_set_combo = QComboBox()
        self.selection_set_combo.setToolTip("Named selections such as Trumpets, Battery, Guard Rifles.")
        selection_set_buttons = QHBoxLayout()
        save_selection_set_button = QPushButton("Save")
        save_selection_set_button.clicked.connect(self.save_selection_set)
        load_selection_set_button = QPushButton("Load")
        load_selection_set_button.clicked.connect(self.load_selection_set)
        delete_selection_set_button = QPushButton("Delete")
        delete_selection_set_button.clicked.connect(self.delete_selection_set)
        selection_set_buttons.addWidget(save_selection_set_button)
        selection_set_buttons.addWidget(load_selection_set_button)
        selection_set_buttons.addWidget(delete_selection_set_button)
        selection_set_layout.addWidget(self.selection_set_combo)
        selection_set_layout.addLayout(selection_set_buttons)
        marchers_layout.addWidget(selection_set_group)
        tabs.addTab(marchers_tab, "Marchers")

        large_show_tab = QWidget()
        large_show_layout = QVBoxLayout(large_show_tab)
        large_show_layout.setContentsMargins(6, 6, 6, 6)
        large_show_title = QLabel("Large-Show Accelerators")
        large_show_title.setStyleSheet("font-size: 14px; font-weight: 750;")
        large_show_note = QLabel(
            "Roster, hierarchy, linked forms, cleanup, comparisons, and alternatives for large ensembles."
        )
        large_show_note.setWordWrap(True)
        large_show_layout.addWidget(large_show_title)
        large_show_layout.addWidget(large_show_note)
        for label, tooltip, callback in (
            ("Import Roster CSV", "Build or update the roster with automatic IDs, colors, sections, and layers.", self.import_roster_csv),
            ("Hierarchy & Linked Forms", "Create nested groups, lock them, transform them, and keep repeated blocks linked.", self.show_group_manager),
            ("Replace / Swap Performer", "Change roster identity while every drill spot, path, and coordinate stays intact.", self.replace_or_swap_performer),
            ("Automatic Form Cleanup", "Normalize spacing, smooth curves, repair corners, and remove overlaps.", self.automatic_form_cleanup),
            ("Compare Two Sets", "View two sets side-by-side with difference vectors and travel measurements.", self.show_set_comparison),
            ("Formation Variations", "Save and compare alternate versions of a formation inside this project.", self.show_formation_variations),
        ):
            button = QPushButton(label)
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            large_show_layout.addWidget(button)
        large_show_layout.addStretch()
        tabs.addTab(large_show_tab, "Large Show")

        props_tab = QWidget()
        self.props_tab = props_tab
        props_layout = QVBoxLayout(props_tab)
        props_layout.setContentsMargins(4, 4, 4, 4)
        props_title = QLabel("Props")
        props_title.setStyleSheet("font-size: 14px; font-weight: 750;")
        import_prop_button = QPushButton("Import")
        import_prop_button.clicked.connect(self.import_prop_image)
        design_prop_button = QPushButton("Design")
        design_prop_button.setToolTip("Open Prop Studio for field-scaled layered prop design.")
        design_prop_button.clicked.connect(self.open_prop_designer)
        front_ensemble_button = QPushButton("Add Pit")
        front_ensemble_button.setToolTip("Add a movable front ensemble prop at the front sideline.")
        front_ensemble_button.clicked.connect(self.add_front_ensemble_prop)
        drum_major_button = QPushButton("Add DM")
        drum_major_button.setToolTip("Add a movable drum major stand prop.")
        drum_major_button.clicked.connect(self.add_drum_major_stand)
        delete_prop_button = QPushButton("Delete")
        delete_prop_button.clicked.connect(self.delete_selected_props)
        props_actions = QGridLayout()
        props_actions.addWidget(import_prop_button, 0, 0)
        props_actions.addWidget(design_prop_button, 0, 1)
        props_actions.addWidget(delete_prop_button, 0, 2)
        props_actions.addWidget(front_ensemble_button, 1, 0, 1, 2)
        props_actions.addWidget(drum_major_button, 1, 2)
        props_layout.addWidget(props_title)
        props_layout.addLayout(props_actions)
        self.prop_table = QTableWidget(0, 3)
        self.prop_table.setHorizontalHeaderLabels(["#", "Name", "Layer"])
        self.prop_table.verticalHeader().setVisible(False)
        self.prop_table.verticalHeader().setDefaultSectionSize(20)
        self.prop_table.setAlternatingRowColors(True)
        self.prop_table.setShowGrid(False)
        self.prop_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.prop_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.prop_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.prop_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.prop_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.prop_table.cellClicked.connect(self.select_prop_from_table)
        props_layout.addWidget(self.prop_table, 1)
        tabs.addTab(props_tab, "Props")

        prop_designer_tab = QWidget()
        designer_layout = QVBoxLayout(prop_designer_tab)
        designer_layout.setContentsMargins(8, 8, 8, 8)
        designer_title = QLabel("Prop Studio")
        designer_title.setStyleSheet("font-size: 14px; font-weight: 750;")
        designer_note = QLabel(
            "Build field-ready props on a real-yard artboard with layers, images, text, pen and shape tools, "
            "snapping, direct resize/rotation handles, undo history, and a live field-scale preview."
        )
        designer_note.setWordWrap(True)
        designer_note.setStyleSheet("color: #aeb7c8;")
        open_designer_button = QPushButton("Open Prop Studio")
        open_designer_button.clicked.connect(self.open_prop_designer)
        designer_layout.addWidget(designer_title)
        designer_layout.addWidget(designer_note)
        designer_layout.addWidget(open_designer_button)
        designer_layout.addStretch(1)
        tabs.addTab(prop_designer_tab, "Prop Designer")

        formation_tab = QWidget()
        self.formation_tab = formation_tab
        formation_layout = QVBoxLayout(formation_tab)
        formation_layout.setContentsMargins(4, 4, 4, 4)
        group = QGroupBox("Formation Tools")
        tools_layout = QVBoxLayout(group)
        tools_layout.setSpacing(6)
        self.tool_buttons: dict[EditorTool, QPushButton] = {}
        tool_categories = (
            (
                "Select",
                (
                    (EditorTool.SELECT, "Select"),
                    (EditorTool.LASSO, "Lasso"),
                ),
            ),
            (
                "Build Forms",
                (
                    (EditorTool.LINE, "Line"),
                    (EditorTool.CURVE, "Curve"),
                    (EditorTool.FREE_CURVE, "Free Curve"),
                    (EditorTool.ARC, "Arc"),
                    (EditorTool.CIRCLE, "Circle"),
                    (EditorTool.ELLIPSE, "Oval"),
                    (EditorTool.RECTANGLE, "Rectangle"),
                    (EditorTool.TRIANGLE, "Triangle"),
                    (EditorTool.DIAMOND, "Diamond"),
                    (EditorTool.POLYGON, "Polygon"),
                    (EditorTool.STAR, "Star"),
                    (EditorTool.SPIRAL, "Spiral"),
                    (EditorTool.BLOCK, "Block/Grid"),
                    (EditorTool.SVG_SHAPE, "SVG Shape"),
                ),
            ),
            (
                "Modify Forms",
                (
                    (EditorTool.SCALE, "Scale Form"),
                    (EditorTool.WARP, "Warp/Bend"),
                    (EditorTool.ROTATE, "Rotate"),
                    (EditorTool.MIRROR, "Mirror"),
                    (EditorTool.SHAPE_LINE, "Shape Line"),
                    (EditorTool.SCATTER, "Scatter"),
                ),
            ),
        )
        for category_name, category_tools in tool_categories:
            category_label = QLabel(category_name)
            category_label.setStyleSheet("color: #f7d154; font-size: 11px; font-weight: 750;")
            tools_layout.addWidget(category_label)
            category_grid = QGridLayout()
            category_grid.setSpacing(4)
            for index, (tool, label) in enumerate(category_tools):
                button = QPushButton(label)
                button.setCheckable(True)
                self.register_tooltip(
                    button,
                    TOOL_HINTS.get(tool, "Use this formation tool with the selected marchers."),
                )
                button.clicked.connect(lambda _checked=False, selected=tool: self.set_tool(selected))
                category_grid.addWidget(button, index // 2, index % 2)
                self.tool_buttons[tool] = button
            tools_layout.addLayout(category_grid)
        drill_grid_group = QGroupBox("Drill Grid & Snap")
        drill_grid_layout = QVBoxLayout(drill_grid_group)
        drill_grid_layout.setContentsMargins(8, 8, 8, 8)
        drill_grid_layout.setSpacing(5)
        drill_grid_row = QHBoxLayout()
        self.drill_grid_panel_toggle = QCheckBox("Enable")
        self.drill_grid_panel_toggle.setToolTip(
            "Show an exact marching-step grid and snap marcher drags, on-form handles, and formation spots to it."
        )
        self.drill_grid_panel_toggle.toggled.connect(self.set_drill_grid_enabled)
        drill_grid_row.addWidget(self.drill_grid_panel_toggle)
        self.drill_grid_panel_status = QLabel()
        self.drill_grid_panel_status.setObjectName("secondaryText")
        drill_grid_row.addWidget(self.drill_grid_panel_status, 1)
        drill_grid_configure = QPushButton("Configure...")
        drill_grid_configure.setToolTip(
            "Set standard 8-to-5 spacing or make a custom horizontal and vertical drill grid."
        )
        drill_grid_configure.clicked.connect(self.show_drill_grid_dialog)
        drill_grid_row.addWidget(drill_grid_configure)
        drill_grid_layout.addLayout(drill_grid_row)
        drill_grid_hint = QLabel("Draggers and generated formation spots lock to unique grid points.")
        drill_grid_hint.setWordWrap(True)
        drill_grid_hint.setObjectName("secondaryText")
        drill_grid_layout.addWidget(drill_grid_hint)
        follow_group = QGroupBox("Animate Formation")
        follow_layout = QVBoxLayout(follow_group)
        follow_layout.setContentsMargins(8, 8, 8, 8)
        follow_layout.setSpacing(5)
        self.follow_leader_button = QPushButton("Follow the Leader...")
        self.follow_leader_button.setMinimumHeight(34)
        self.follow_leader_button.setToolTip(
            "Select two or more marchers, then build a shared route with complex turns, "
            "fixed follower spacing, and optional direction-of-travel facing. Shortcut: Ctrl+Alt+F."
        )
        self.follow_leader_button.clicked.connect(self.follow_leader_rotate)
        follow_layout.addWidget(self.follow_leader_button)
        follow_shortcut_row = QHBoxLayout()
        follow_hint = QLabel("Shared-route motion for lines, loops, SVGs, and custom shapes")
        follow_hint.setWordWrap(True)
        follow_hint.setObjectName("secondaryText")
        follow_shortcut = QLabel("Ctrl+Alt+F")
        follow_shortcut.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        follow_shortcut.setStyleSheet("color: #f7d154; font-weight: 700;")
        follow_shortcut_row.addWidget(follow_hint, 1)
        follow_shortcut_row.addWidget(follow_shortcut)
        follow_layout.addLayout(follow_shortcut_row)
        formation_layout.addWidget(drill_grid_group)
        formation_layout.addWidget(group)
        formation_layout.addWidget(follow_group)

        self.tool_hint_label = QLabel(TOOL_HINTS[EditorTool.SELECT])
        self.tool_hint_label.setWordWrap(True)
        self.tool_hint_label.setObjectName("ToolHintLabel")
        self.tool_hint_label.setStyleSheet("color: #9ca3af; padding: 4px 2px;")
        formation_layout.addWidget(self.tool_hint_label)
        formation_layout.addWidget(QLabel("Assignment strategy"))
        assignment_row = QHBoxLayout()
        self.assignment_strategy_combo = QComboBox()
        self.assignment_strategy_combo.addItem("Collision-safe automatic", "automatic")
        self.assignment_strategy_combo.addItem("Section-aware", "section")
        self.assignment_strategy_combo.addItem("Preserve ranks / files", "rank")
        self.assignment_strategy_combo.addItem("Shortest total travel", "shortest")
        self.assignment_strategy_combo.addItem("Clockwise", "clockwise")
        self.assignment_strategy_combo.addItem("Counterclockwise", "counterclockwise")
        self.assignment_strategy_combo.addItem("Preserve form order", "follow_leader")
        self.assignment_strategy_combo.addItem("Collision-safe spot assignment", "lowest_collision")
        self.assignment_strategy_combo.setToolTip(
            "Reassigns marchers to the exact generated spots without changing the target picture or adding path bends."
        )
        self.assignment_strategy_combo.currentIndexChanged.connect(self.update_formation_preview)
        assignment_row.addWidget(self.assignment_strategy_combo, 1)
        composer_button = QPushButton("Compare")
        composer_button.clicked.connect(self.show_smart_transition_composer)
        assignment_row.addWidget(composer_button)
        formation_layout.addLayout(assignment_row)

        presets_group = QGroupBox("Presets")
        presets_layout = QVBoxLayout(presets_group)
        presets_layout.setContentsMargins(6, 6, 6, 6)
        self.tool_preset_combo = QComboBox()
        self.tool_preset_combo.setToolTip("Saved tool settings, like a 16-count solid arc.")
        save_tool_preset_button = QPushButton("Save")
        save_tool_preset_button.clicked.connect(self.save_tool_preset)
        load_tool_preset_button = QPushButton("Load")
        load_tool_preset_button.clicked.connect(self.load_tool_preset)
        delete_tool_preset_button = QPushButton("Delete")
        delete_tool_preset_button.clicked.connect(self.delete_tool_preset)
        tool_preset_buttons = QHBoxLayout()
        tool_preset_buttons.addWidget(save_tool_preset_button)
        tool_preset_buttons.addWidget(load_tool_preset_button)
        tool_preset_buttons.addWidget(delete_tool_preset_button)
        self.formation_preset_combo = QComboBox()
        self.formation_preset_combo.setToolTip("Reusable saved forms that can be applied to selected marchers.")
        save_formation_preset_button = QPushButton("Save")
        save_formation_preset_button.clicked.connect(self.save_formation_preset)
        load_formation_preset_button = QPushButton("Apply")
        load_formation_preset_button.clicked.connect(self.apply_formation_preset)
        delete_formation_preset_button = QPushButton("Delete")
        delete_formation_preset_button.clicked.connect(self.delete_formation_preset)
        formation_preset_buttons = QHBoxLayout()
        formation_preset_buttons.addWidget(save_formation_preset_button)
        formation_preset_buttons.addWidget(load_formation_preset_button)
        formation_preset_buttons.addWidget(delete_formation_preset_button)
        presets_layout.addWidget(QLabel("Tool settings"))
        presets_layout.addWidget(self.tool_preset_combo)
        presets_layout.addLayout(tool_preset_buttons)
        presets_layout.addWidget(QLabel("Saved formations"))
        presets_layout.addWidget(self.formation_preset_combo)
        presets_layout.addLayout(formation_preset_buttons)
        formation_layout.addWidget(presets_group)

        self.plugin_form_tool_group = QGroupBox("Plugin Form Tools")
        self.plugin_form_tool_layout = QVBoxLayout(self.plugin_form_tool_group)
        self.plugin_form_tool_layout.setContentsMargins(6, 6, 6, 6)
        self.plugin_form_tool_layout.setSpacing(4)
        self.plugin_form_tool_group.setVisible(False)
        formation_layout.addWidget(self.plugin_form_tool_group)

        self.plugin_panel_group = QGroupBox("Plugin Actions")
        self.plugin_panel_layout = QVBoxLayout(self.plugin_panel_group)
        self.plugin_panel_layout.setContentsMargins(6, 6, 6, 6)
        self.plugin_panel_layout.setSpacing(4)
        self.plugin_panel_group.setVisible(False)
        formation_layout.addWidget(self.plugin_panel_group)

        align_group = QGroupBox("Align")
        align_layout = QVBoxLayout(align_group)
        for text, callback in (
            ("Horizontal", self.align_horizontal),
            ("Vertical", self.align_vertical),
            ("Even Spacing", self.align_spacing),
            ("Center Field", self.center_selection),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            align_layout.addWidget(button)

        quick_group = QGroupBox("Quick Workflow")
        quick_layout = QVBoxLayout(quick_group)
        for text, callback in (
            ("Select Same Instrument", self.select_same_instrument),
            ("Select Same Section", self.select_same_section),
            ("Invert Selection", self.invert_selection),
            ("Select Moving", self.select_moving_this_set),
            ("Carry Forward", self.carry_selected_forward),
            ("Set Opening Positions", self.capture_opening_positions_from_current_view),
            ("Copy Current Set", self.copy_set),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            quick_layout.addWidget(button)
        formation_layout.addWidget(quick_group)

        self.tool_edit_group = QGroupBox("Tool Edit")
        edit_layout = QVBoxLayout(self.tool_edit_group)
        self.tool_edit_layout = edit_layout

        self.plugin_tool_group = QGroupBox("Plugin Tool")
        self.plugin_tool_form = QFormLayout(self.plugin_tool_group)
        self.plugin_tool_group.setVisible(False)

        self.line_tool_group = QGroupBox("Line")
        line_layout = QVBoxLayout(self.line_tool_group)
        line_layout.addWidget(QLabel("Preview evenly spaces selected marchers between the first and last selected dot."))

        self.curve_tool_group = QGroupBox("Curve")
        curve_form = QFormLayout(self.curve_tool_group)
        self.curve_bend = QDoubleSpinBox()
        self.curve_bend.setRange(-40, 40)
        self.curve_bend.setValue(12)
        self.curve_bend.setSuffix(" yd")
        self.curve_bend.setToolTip("Default bend used when resetting curve handles from the selected line.")
        reset_curve_button = QPushButton("Reset Handles From Bend")
        reset_curve_button.clicked.connect(self.reset_curve_handles)
        self.curve_bend.valueChanged.connect(self.reset_curve_handles)
        curve_note = QLabel(
            "Drag start, end, and two blue curve handles directly on the field. "
            "Spacing stays even along the curve path."
        )
        curve_note.setWordWrap(True)
        curve_form.addRow("Default Bend", self.curve_bend)
        curve_form.addRow(reset_curve_button)
        curve_form.addRow("", curve_note)

        self.free_curve_tool_group = QGroupBox("Free Curve")
        free_curve_form = QFormLayout(self.free_curve_tool_group)
        self.free_curve_anchor_count = QSpinBox()
        self.free_curve_anchor_count.setRange(3, 16)
        self.free_curve_anchor_count.setValue(5)
        self.free_curve_anchor_count.setToolTip("Number of draggable control anchors used to draw the custom curve.")
        self.free_curve_closed = QCheckBox("Closed Loop")
        self.free_curve_closed.setToolTip("Connect the last anchor back to the first for loops, circles, or enclosed curves.")
        self.free_curve_curved = QCheckBox("Smooth Curve")
        self.free_curve_curved.setChecked(True)
        self.free_curve_curved.setToolTip("Turn off for straight segments between anchors, like a clean zig-zag.")
        reset_free_curve_button = QPushButton("Reset Anchors From Selection")
        reset_free_curve_button.clicked.connect(self.reset_free_curve_anchors)
        free_curve_note = QLabel(
            "Drag the red anchors directly on the field. Marchers are evenly spaced along the exact curve path."
        )
        free_curve_note.setWordWrap(True)
        self.free_curve_anchor_count.valueChanged.connect(self.reset_free_curve_anchors)
        self.free_curve_closed.toggled.connect(self.update_formation_preview)
        self.free_curve_curved.toggled.connect(self.update_formation_preview)
        free_curve_form.addRow("Anchors", self.free_curve_anchor_count)
        free_curve_form.addRow(self.free_curve_closed)
        free_curve_form.addRow(self.free_curve_curved)
        free_curve_form.addRow(reset_free_curve_button)
        free_curve_form.addRow("", free_curve_note)

        self.arc_tool_group = QGroupBox("Arc")
        arc_form = QFormLayout(self.arc_tool_group)
        self.arc_radius = QDoubleSpinBox()
        self.arc_radius.setRange(1, 80)
        self.arc_radius.setValue(18)
        self.arc_radius.setSuffix(" yd")
        self.arc_width = QDoubleSpinBox()
        self.arc_width.setRange(1, 120)
        self.arc_width.setValue(36)
        self.arc_width.setSuffix(" yd")
        self.arc_width.setToolTip("Overall width of the arc/arch.")
        self.arc_height = QDoubleSpinBox()
        self.arc_height.setRange(1, 54)
        self.arc_height.setValue(24)
        self.arc_height.setSuffix(" yd")
        self.arc_height.setToolTip("Overall height of the arc/arch.")
        self.arc_start_angle = QDoubleSpinBox()
        self.arc_start_angle.setRange(-720, 720)
        self.arc_start_angle.setValue(200)
        self.arc_start_angle.setSuffix(" deg")
        self.arc_start_angle.setToolTip("Where the arc begins around its oval.")
        self.arc_sweep = QDoubleSpinBox()
        self.arc_sweep.setRange(-360, 360)
        self.arc_sweep.setValue(140)
        self.arc_sweep.setSuffix(" deg")
        self.arc_rotation = QDoubleSpinBox()
        self.arc_rotation.setRange(-360, 360)
        self.arc_rotation.setValue(0)
        self.arc_rotation.setSuffix(" deg")
        self.arc_rotation.setToolTip("Rotate the whole arc shape on the field.")
        arc_note = QLabel(
            "Drag the width, height, start, and end handles on the field. "
            "The tool now spaces marchers evenly by actual arc length."
        )
        arc_note.setWordWrap(True)
        arc_form.addRow("Width", self.arc_width)
        arc_form.addRow("Height", self.arc_height)
        arc_form.addRow("Start", self.arc_start_angle)
        arc_form.addRow("Sweep", self.arc_sweep)
        arc_form.addRow("Rotate", self.arc_rotation)
        arc_form.addRow("", arc_note)

        self.scatter_tool_group = QGroupBox("Scatter")
        scatter_form = QFormLayout(self.scatter_tool_group)
        self.scatter_radius = QDoubleSpinBox()
        self.scatter_radius.setRange(0, 40)
        self.scatter_radius.setValue(8)
        self.scatter_radius.setSuffix(" yd")
        self.scatter_shape = QComboBox()
        self.scatter_shape.addItems(["Circle", "Square", "Rectangle"])
        self.scatter_spacing = QDoubleSpinBox()
        self.scatter_spacing.setRange(0.75, 6)
        self.scatter_spacing.setValue(1.8)
        self.scatter_spacing.setSuffix(" yd")
        self.scatter_shape.currentTextChanged.connect(self.update_formation_preview)
        scatter_form.addRow("Radius", self.scatter_radius)
        scatter_form.addRow("Shape", self.scatter_shape)
        scatter_form.addRow("Min Spacing", self.scatter_spacing)

        self.mirror_tool_group = QGroupBox("Mirror")
        mirror_layout = QVBoxLayout(self.mirror_tool_group)
        mirror_layout.addWidget(QLabel("Preview mirrors selected marchers across midfield."))

        self.shape_line_tool_group = QGroupBox("Shape Line")
        shape_line_form = QFormLayout(self.shape_line_tool_group)
        self.shape_line_curved = QCheckBox("Curved Segments")
        self.shape_line_curved.setChecked(True)
        self.shape_line_curved.toggled.connect(self.update_formation_preview)
        shape_line_form.addRow(self.shape_line_curved)

        self.svg_tool_group = QGroupBox("SVG Shape")
        svg_layout = QVBoxLayout(self.svg_tool_group)
        self.svg_shape_label = QLabel("No SVG imported")
        import_svg_button = QPushButton("Import SVG Shape")
        import_svg_button.clicked.connect(self.import_svg_shape)
        svg_form = QFormLayout()
        self.svg_min_spacing = QDoubleSpinBox()
        self.svg_min_spacing.setRange(0.25, 8)
        self.svg_min_spacing.setValue(1.25)
        self.svg_min_spacing.setSingleStep(0.25)
        self.svg_min_spacing.setSuffix(" yd")
        self.svg_min_spacing.setToolTip("Minimum spacing used to prevent SVG self-crossings and corners from stacking marchers.")
        svg_form.addRow("Min Spacing", self.svg_min_spacing)
        svg_note = QLabel("For self-crossing SVGs like infinity symbols, increase Min Spacing or scale the shape larger if dots still crowd.")
        svg_note.setWordWrap(True)
        svg_layout.addWidget(self.svg_shape_label)
        svg_layout.addWidget(import_svg_button)
        svg_layout.addLayout(svg_form)
        svg_layout.addWidget(svg_note)

        self.shape_tool_group = QGroupBox("Shape")
        shape_form = QFormLayout(self.shape_tool_group)
        self.shape_tool_form = shape_form
        self.shape_radius = QDoubleSpinBox()
        self.shape_radius.setRange(1, 80)
        self.shape_radius.setValue(18)
        self.shape_radius.setSuffix(" yd")
        self.shape_width = QDoubleSpinBox()
        self.shape_width.setRange(1, 120)
        self.shape_width.setValue(30)
        self.shape_width.setSuffix(" yd")
        self.shape_height = QDoubleSpinBox()
        self.shape_height.setRange(1, 54)
        self.shape_height.setValue(18)
        self.shape_height.setSuffix(" yd")
        self.shape_fill_mode = QComboBox()
        self.shape_fill_mode.addItems(["Hollow", "Solid"])
        self.shape_fill_mode.currentTextChanged.connect(self.update_formation_preview)
        self.polygon_sides = QSpinBox()
        self.polygon_sides.setRange(3, 16)
        self.polygon_sides.setValue(5)
        self.star_points = QSpinBox()
        self.star_points.setRange(4, 12)
        self.star_points.setValue(5)
        self.star_inner_percent = QSpinBox()
        self.star_inner_percent.setRange(20, 90)
        self.star_inner_percent.setValue(45)
        self.star_inner_percent.setSuffix("%")
        self.spiral_turns = QDoubleSpinBox()
        self.spiral_turns.setRange(0.25, 6)
        self.spiral_turns.setValue(2)
        self.spiral_turns.setSingleStep(0.25)
        self.block_columns = QSpinBox()
        self.block_columns.setRange(1, 50)
        self.block_columns.setValue(6)
        self.block_spacing = QDoubleSpinBox()
        self.block_spacing.setRange(0.25, 8)
        self.block_spacing.setValue(2)
        self.block_spacing.setSuffix(" yd")
        shape_form.addRow("Radius", self.shape_radius)
        shape_form.addRow("Width", self.shape_width)
        shape_form.addRow("Height", self.shape_height)
        shape_form.addRow("Fill", self.shape_fill_mode)
        shape_form.addRow("Polygon Sides", self.polygon_sides)
        shape_form.addRow("Star Points", self.star_points)
        shape_form.addRow("Star Inner", self.star_inner_percent)
        shape_form.addRow("Spiral Turns", self.spiral_turns)
        shape_form.addRow("Block Columns", self.block_columns)
        shape_form.addRow("Block Spacing", self.block_spacing)

        self.scale_tool_group = QGroupBox("Scale Form")
        scale_form = QFormLayout(self.scale_tool_group)
        self.scale_width = QDoubleSpinBox()
        self.scale_width.setRange(0.1, 120)
        self.scale_width.setValue(30)
        self.scale_width.setSuffix(" yd")
        self.scale_height = QDoubleSpinBox()
        self.scale_height.setRange(0.1, 54)
        self.scale_height.setValue(18)
        self.scale_height.setSuffix(" yd")
        self.scale_lock_aspect = QCheckBox("Lock aspect ratio")
        self.scale_fit_padding = QDoubleSpinBox()
        self.scale_fit_padding.setRange(0, 20)
        self.scale_fit_padding.setValue(0.5)
        self.scale_fit_padding.setSuffix(" yd")
        fit_prop_button = QPushButton("Fit Selected Prop")
        fit_prop_button.clicked.connect(self.fit_selected_form_to_prop)
        scale_note = QLabel("Select marchers plus a prop, then fit or drag the field handles.")
        scale_note.setWordWrap(True)
        scale_form.addRow("Target Width", self.scale_width)
        scale_form.addRow("Target Height", self.scale_height)
        scale_form.addRow(self.scale_lock_aspect)
        scale_form.addRow("Prop Padding", self.scale_fit_padding)
        scale_form.addRow(fit_prop_button)
        scale_form.addRow("", scale_note)

        self.warp_tool_group = QGroupBox("Warp / Bend Form")
        warp_form = QFormLayout(self.warp_tool_group)
        self.warp_anchor_count = QSpinBox()
        self.warp_anchor_count.setRange(3, 9)
        self.warp_anchor_count.setValue(5)
        self.warp_strength = QDoubleSpinBox()
        self.warp_strength.setRange(0.0, 2.0)
        self.warp_strength.setValue(1.0)
        self.warp_strength.setSingleStep(0.1)
        self.warp_anchor_count.valueChanged.connect(self.reset_warp_anchors)
        warp_note = QLabel(
            "Drag the purple/gold handles to bend the selected form into waves. "
            "The outer handles pin the form edges; middle handles create bends."
        )
        warp_note.setWordWrap(True)
        warp_form.addRow("Handles", self.warp_anchor_count)
        warp_form.addRow("Strength", self.warp_strength)
        warp_form.addRow("", warp_note)

        self.rotate_tool_group = QGroupBox("Rotate")
        rotate_form = QFormLayout(self.rotate_tool_group)
        self.rotation_degrees = QDoubleSpinBox()
        self.rotation_degrees.setRange(-360, 360)
        self.rotation_degrees.setValue(15)
        self.rotation_degrees.setSuffix(" deg")
        rotate_form.addRow("Rotation Degrees", self.rotation_degrees)
        follow_button = QPushButton("Follow the Leader...")
        follow_button.setToolTip(
            "Move a selected line or shape along one shared route with fixed follower spacing, complex turns, and optional travel-facing."
        )
        follow_button.clicked.connect(self.follow_leader_rotate)
        rotate_form.addRow(follow_button)
        for editor in (
            self.curve_bend,
            self.arc_radius,
            self.arc_width,
            self.arc_height,
            self.arc_start_angle,
            self.arc_sweep,
            self.arc_rotation,
            self.scatter_radius,
            self.scatter_spacing,
            self.rotation_degrees,
            self.shape_radius,
            self.shape_width,
            self.shape_height,
            self.polygon_sides,
            self.star_points,
            self.star_inner_percent,
            self.spiral_turns,
            self.block_columns,
            self.block_spacing,
            self.scale_width,
            self.scale_height,
            self.scale_fit_padding,
            self.warp_strength,
            self.svg_min_spacing,
        ):
            editor.valueChanged.connect(self.update_formation_preview)
        self.scale_lock_aspect.toggled.connect(self.update_formation_preview)
        apply_button = QPushButton("Apply Preview")
        apply_button.clicked.connect(self.apply_current_preview)
        clear_button = QPushButton("Clear Preview")
        clear_button.clicked.connect(self.clear_formation_preview)
        rotate_button = QPushButton("Rotate Selection")
        rotate_button.clicked.connect(self.rotate_selection)
        rotate_form.addRow(rotate_button)
        for group_widget in (
            self.plugin_tool_group,
            self.line_tool_group,
            self.curve_tool_group,
            self.free_curve_tool_group,
            self.arc_tool_group,
            self.scatter_tool_group,
            self.mirror_tool_group,
            self.shape_line_tool_group,
            self.svg_tool_group,
            self.shape_tool_group,
            self.scale_tool_group,
            self.warp_tool_group,
            self.rotate_tool_group,
        ):
            edit_layout.addWidget(group_widget)
        apply_row = QHBoxLayout()
        apply_row.addWidget(apply_button)
        apply_row.addWidget(clear_button)
        edit_layout.addLayout(apply_row)
        formation_layout.addWidget(self.tool_edit_group)
        formation_layout.addStretch()
        tabs.addTab(formation_tab, "Form")

        accelerator_tab = QWidget()
        self.accelerator_tab = accelerator_tab
        accelerator_layout = QVBoxLayout(accelerator_tab)
        accelerator_layout.setContentsMargins(0, 0, 0, 0)
        self.accelerator_panel = AcceleratorPanel()
        self.accelerator_panel.array_requested.connect(self.show_polar_linear_array)
        self.accelerator_panel.parallel_requested.connect(self.show_parallel_form_generator)
        self.accelerator_panel.rank_file_requested.connect(self.show_rank_file_builder)
        self.accelerator_panel.symmetry_requested.connect(self.create_live_symmetry)
        self.accelerator_panel.symmetry_manage_requested.connect(self.manage_live_symmetry)
        self.accelerator_panel.alternating_requested.connect(self.show_alternating_selection)
        self.accelerator_panel.measurements_changed.connect(self.set_measurement_overlay)
        self.accelerator_panel.references_requested.connect(self.show_reference_annotations)
        accelerator_layout.addWidget(self.accelerator_panel)
        tabs.addTab(accelerator_tab, "Accelerate")

        music_tab = QWidget()
        self.music_tab = music_tab
        music_layout = QVBoxLayout(music_tab)
        music_layout.setContentsMargins(0, 0, 0, 0)
        self.music_design_panel = MusicDesignPanel()
        self.music_design_panel.studio_requested.connect(self.show_music_design_studio)
        self.music_design_panel.set_project(self.project)
        music_layout.addWidget(self.music_design_panel)
        tabs.addTab(music_tab, "Music")

        specialized_tab = QWidget()
        self.specialized_tab = specialized_tab
        specialized_layout = QVBoxLayout(specialized_tab)
        specialized_layout.setContentsMargins(0, 0, 0, 0)
        self.specialized_design_panel = SpecializedDesignPanel()
        self.specialized_design_panel.studio_requested.connect(self.show_specialized_design_studio)
        self.specialized_design_panel.set_project(self.project)
        specialized_layout.addWidget(self.specialized_design_panel)
        tabs.addTab(specialized_tab, "Specialized")

        motion_tab = QWidget()
        self.motion_tab = motion_tab
        motion_layout = QVBoxLayout(motion_tab)
        motion_layout.setContentsMargins(4, 4, 4, 4)
        motion_layout.setSpacing(8)
        motion_title = QLabel("Group Motion & Drafting")
        motion_title.setStyleSheet("font-size: 14px; font-weight: 750;")
        motion_note = QLabel(
            "Design transitions as shared geometry, write performer continuity, and keep permanent CAD-style guides on the field."
        )
        motion_note.setWordWrap(True)
        motion_layout.addWidget(motion_title)
        motion_layout.addWidget(motion_note)

        ribbon_group = QGroupBox("Group Motion Ribbons")
        ribbon_layout = QVBoxLayout(ribbon_group)
        self.motion_ribbon_list = QListWidget()
        self.motion_ribbon_list.setMinimumHeight(88)
        self.motion_ribbon_list.itemDoubleClicked.connect(lambda _item: self.edit_group_path_handles())
        ribbon_layout.addWidget(self.motion_ribbon_list)
        ribbon_actions = QGridLayout()
        create_ribbon_button = QPushButton("Create Ribbon")
        create_ribbon_button.setToolTip("Create one curved transition ribbon for the selected rank or section.")
        create_ribbon_button.clicked.connect(self.create_group_motion_ribbon)
        edit_ribbon_button = QPushButton("Edit Handles")
        edit_ribbon_button.setToolTip("Show shared Bézier nodes and tangent handles directly on the field.")
        edit_ribbon_button.clicked.connect(self.edit_group_path_handles)
        add_ribbon_node_button = QPushButton("Add Node")
        add_ribbon_node_button.clicked.connect(self.add_motion_ribbon_node)
        remove_ribbon_node_button = QPushButton("Remove Node")
        remove_ribbon_node_button.clicked.connect(self.remove_motion_ribbon_node)
        ribbon_settings_button = QPushButton("Ribbon Settings")
        ribbon_settings_button.clicked.connect(self.edit_motion_ribbon_settings)
        delete_ribbon_button = QPushButton("Delete Ribbon")
        delete_ribbon_button.clicked.connect(self.delete_motion_ribbon)
        ribbon_actions.addWidget(create_ribbon_button, 0, 0)
        ribbon_actions.addWidget(edit_ribbon_button, 0, 1)
        ribbon_actions.addWidget(add_ribbon_node_button, 1, 0)
        ribbon_actions.addWidget(remove_ribbon_node_button, 1, 1)
        ribbon_actions.addWidget(ribbon_settings_button, 2, 0)
        ribbon_actions.addWidget(delete_ribbon_button, 2, 1)
        ribbon_layout.addLayout(ribbon_actions)
        motion_layout.addWidget(ribbon_group)

        transition_group = QGroupBox("Transition Design")
        transition_layout = QVBoxLayout(transition_group)
        morph_button = QPushButton("Formation Morph…")
        morph_button.setToolTip("Blend one form into another while preserving sections, intervals, and neighbors.")
        morph_button.clicked.connect(self.show_formation_morph)
        continuity_button = QPushButton("Continuity Designer…")
        continuity_button.setToolTip("Assign step size, direction, facings, and written instructions by count range.")
        continuity_button.clicked.connect(self.show_continuity_designer)
        transition_layout.addWidget(morph_button)
        transition_layout.addWidget(continuity_button)
        motion_layout.addWidget(transition_group)

        drafting_group = QGroupBox("Construction & CAD")
        drafting_layout = QVBoxLayout(drafting_group)
        guides_button = QPushButton("Construction Guides…")
        guides_button.setToolTip("Add draggable lines, circles, arcs, grids, rulers, centers, and no-go regions.")
        guides_button.clicked.connect(self.show_construction_guides)
        cad_button = QPushButton("CAD Path Toolkit…")
        cad_button.setToolTip("Join, split, trim, extend, offset, simplify, smooth, reverse, or fillet path geometry.")
        cad_button.clicked.connect(self.show_cad_path_toolkit)
        drafting_layout.addWidget(guides_button)
        drafting_layout.addWidget(cad_button)
        motion_layout.addWidget(drafting_group)
        motion_layout.addStretch(1)
        tabs.addTab(motion_tab, "Motion")

        align_tab = QWidget()
        self.align_tab = align_tab
        align_tab_layout = QVBoxLayout(align_tab)
        align_tab_layout.addWidget(align_group)
        interval_group = QGroupBox("Interval Intelligence")
        interval_form = QFormLayout(interval_group)
        self.interval_spacing = QDoubleSpinBox()
        self.interval_spacing.setRange(0.25, 8)
        self.interval_spacing.setValue(2)
        self.interval_spacing.setSuffix(" yd")
        interval_form.addRow("Target Interval", self.interval_spacing)
        normalize_button = QPushButton("Normalize Interval")
        normalize_button.clicked.connect(self.normalize_selected_interval)
        constraint_button = QPushButton("Line Constraint")
        constraint_button.clicked.connect(self.create_line_constraint)
        pivot_constraint_button = QPushButton("Pivot Constraint")
        pivot_constraint_button.clicked.connect(self.create_pivot_constraint)
        arc_constraint_button = QPushButton("Arc Constraint")
        arc_constraint_button.clicked.connect(self.create_arc_constraint)
        block_constraint_button = QPushButton("Block Constraint")
        block_constraint_button.clicked.connect(self.create_block_constraint)
        apply_constraints_button = QPushButton("Apply Constraints")
        apply_constraints_button.clicked.connect(self.apply_constraints)
        self.constraint_list = QListWidget()
        interval_form.addRow(normalize_button)
        interval_form.addRow(constraint_button)
        interval_form.addRow(pivot_constraint_button)
        interval_form.addRow(arc_constraint_button)
        interval_form.addRow(block_constraint_button)
        interval_form.addRow(apply_constraints_button)
        interval_form.addRow("Constraints", self.constraint_list)
        align_tab_layout.addWidget(interval_group)
        align_tab_layout.addStretch()
        tabs.addTab(align_tab, "Align")

        analysis_tab = QWidget()
        self.analysis_tab = analysis_tab
        analysis_layout = QVBoxLayout(analysis_tab)
        analysis_group = QGroupBox("Path Safety")
        analysis_form = QFormLayout(analysis_group)
        self.min_spacing = QDoubleSpinBox()
        self.min_spacing.setRange(0.25, 8)
        self.min_spacing.setValue(1.25)
        self.min_spacing.setSuffix(" yd")
        self.max_yards_per_count = QDoubleSpinBox()
        self.max_yards_per_count.setRange(0.5, 12)
        self.max_yards_per_count.setValue(4)
        self.max_yards_per_count.setSuffix(" yd/count")
        analyze_button = QPushButton("Analyze All Paths")
        analyze_button.clicked.connect(self.analyze_paths)
        auto_plan_button = QPushButton("Optimize Selected Spots")
        auto_plan_button.setToolTip(
            "Keeps the current form exactly the same while reassigning which marcher owns each destination spot."
        )
        auto_plan_button.clicked.connect(self.optimize_selected_spot_assignment)
        guided_repair_button = QPushButton("Guided Destination Repair...")
        guided_repair_button.setToolTip(
            "Compare destination swaps with live field previews, conflict scores, and an exact list of changed spot owners before applying."
        )
        guided_repair_button.clicked.connect(self.show_smart_transition_composer)
        clear_paths_button = QPushButton("Clear Selected Paths")
        clear_paths_button.clicked.connect(self.clear_selected_paths)
        cleanup_conflicts_button = QPushButton("Clean Selected Form")
        cleanup_conflicts_button.clicked.connect(self.automatic_form_cleanup)
        self.conflict_heatmap = ConflictHeatmapWidget()
        self.conflict_heatmap.set_theme_tokens(theme_tokens(str(self.settings.value("appearance/theme", "dark")), self.settings))
        self.conflict_heatmap.count_clicked.connect(lambda count: self.set_count(count, seek_audio=True))
        self.warning_list = QListWidget()
        self.warning_list.itemClicked.connect(self.jump_to_conflict_warning)
        self.min_spacing.valueChanged.connect(self.schedule_live_conflict_analysis)
        self.max_yards_per_count.valueChanged.connect(self.schedule_live_conflict_analysis)
        analysis_form.addRow("Min Spacing", self.min_spacing)
        analysis_form.addRow("Max Speed", self.max_yards_per_count)
        analysis_form.addRow(self.conflict_heatmap)
        analysis_form.addRow(analyze_button)
        analysis_form.addRow(guided_repair_button)
        analysis_form.addRow(auto_plan_button)
        analysis_form.addRow(cleanup_conflicts_button)
        analysis_form.addRow(clear_paths_button)
        analysis_form.addRow("Warnings", self.warning_list)
        analysis_layout.addWidget(analysis_group)
        analysis_layout.addStretch()
        tabs.addTab(analysis_tab, "Safety")

        rehearsal_tab = QWidget()
        self.rehearsal_tab = rehearsal_tab
        rehearsal_layout = QVBoxLayout(rehearsal_tab)
        playback_group = QGroupBox("Rehearsal")
        playback_form = QFormLayout(playback_group)
        self.playback_rate = QComboBox()
        self.playback_rate.addItems(["0.25x", "0.5x", "0.75x", "1x", "1.5x", "2x"])
        self.playback_rate.setCurrentText("1x")
        self.playback_rate.currentTextChanged.connect(self.update_playback_rate)
        self.loop_current_set = QCheckBox("Loop Current Set")
        self.count_finder = QDoubleSpinBox()
        self.count_finder.setRange(1, 9999)
        self.count_finder.setDecimals(2)
        go_count_button = QPushButton("Go")
        go_count_button.clicked.connect(self.go_to_requested_count)
        keyframe_button = QPushButton("Set Count Keyframe")
        keyframe_button.clicked.connect(self.add_micro_keyframe)
        clear_keyframe_button = QPushButton("Clear Keyframe")
        clear_keyframe_button.clicked.connect(self.clear_micro_keyframe)
        beat_markers_button = QPushButton("Mark Every Count")
        beat_markers_button.clicked.connect(self.add_count_markers_for_set)
        auto_hit_button = QPushButton("Detect Hit Markers")
        auto_hit_button.clicked.connect(self.auto_detect_hit_markers)
        self.micro_edit_enabled = QCheckBox("Micro Edit Dragging")
        playback_form.addRow("Playback Rate", self.playback_rate)
        playback_form.addRow(self.loop_current_set)
        playback_form.addRow("Count Finder", self.count_finder)
        playback_form.addRow(go_count_button)
        playback_form.addRow(self.micro_edit_enabled)
        playback_form.addRow(keyframe_button)
        playback_form.addRow(clear_keyframe_button)
        playback_form.addRow(beat_markers_button)
        playback_form.addRow(auto_hit_button)
        rehearsal_layout.addWidget(playback_group)

        movement_group = QGroupBox("Marcher Movement Style")
        movement_form = QFormLayout(movement_group)
        self.movement_style_combo = QComboBox()
        for label, style in (
            ("Normal", MovementStyle.NORMAL),
            ("Half Time", MovementStyle.HALF_TIME),
            ("Double Time", MovementStyle.DOUBLE_TIME),
            ("Jazz Run", MovementStyle.JAZZ_RUN),
            ("At Halt", MovementStyle.HALT),
            ("Visual", MovementStyle.VISUAL),
        ):
            self.movement_style_combo.addItem(label, style.value)
        apply_movement_button = QPushButton("Apply to Selection")
        apply_movement_button.clicked.connect(self.apply_movement_style_to_selected)
        clear_movement_button = QPushButton("Clear Style")
        clear_movement_button.clicked.connect(self.clear_movement_style_for_selected)
        self.move_start_count = QDoubleSpinBox()
        self.move_start_count.setRange(1, 9999)
        self.move_start_count.setDecimals(2)
        self.move_start_count.setSingleStep(1)
        self.move_end_count = QDoubleSpinBox()
        self.move_end_count.setRange(1, 9999)
        self.move_end_count.setDecimals(2)
        self.move_end_count.setSingleStep(1)
        apply_move_timing_button = QPushButton("Apply Move Window")
        apply_move_timing_button.clicked.connect(self.apply_move_timing_to_selected)
        start_now_button = QPushButton("Start Now")
        start_now_button.clicked.connect(self.start_selected_move_at_current_count)
        clear_move_timing_button = QPushButton("Use Full Set Timing")
        clear_move_timing_button.clicked.connect(self.clear_move_timing_for_selected)
        self.facing_degrees = QDoubleSpinBox()
        self.facing_degrees.setRange(0, 359.9)
        self.facing_degrees.setDecimals(1)
        self.facing_degrees.setSingleStep(15)
        self.facing_degrees.setSuffix("°")
        self.facing_degrees.setToolTip("Facing angle for triangle symbols. 0° faces front field, 180° faces back field.")
        apply_facing_button = QPushButton("Apply Facing")
        apply_facing_button.clicked.connect(self.apply_facing_to_selected)
        face_front_button = QPushButton("Face Front")
        face_front_button.clicked.connect(lambda: self.set_selected_facing(0))
        face_back_button = QPushButton("Face Back")
        face_back_button.clicked.connect(lambda: self.set_selected_facing(180))
        rotate_left_button = QPushButton("Rotate -45°")
        rotate_left_button.clicked.connect(lambda: self.rotate_selected_facing(-45))
        rotate_right_button = QPushButton("Rotate +45°")
        rotate_right_button.clicked.connect(lambda: self.rotate_selected_facing(45))
        facing_buttons = QWidget()
        facing_layout = QGridLayout(facing_buttons)
        facing_layout.setContentsMargins(0, 0, 0, 0)
        facing_layout.addWidget(rotate_left_button, 0, 0)
        facing_layout.addWidget(rotate_right_button, 0, 1)
        facing_layout.addWidget(face_front_button, 1, 0)
        facing_layout.addWidget(face_back_button, 1, 1)
        self.movement_style_status = QLabel("Select marchers to set style for this set.")
        self.movement_style_status.setWordWrap(True)
        self.facing_status = QLabel("Triangle symbol uses this as performer facing direction.")
        self.facing_status.setWordWrap(True)
        movement_form.addRow("Style", self.movement_style_combo)
        movement_form.addRow(apply_movement_button)
        movement_form.addRow(clear_movement_button)
        movement_form.addRow("Move Start", self.move_start_count)
        movement_form.addRow("Move End", self.move_end_count)
        movement_form.addRow(apply_move_timing_button)
        movement_form.addRow(start_now_button)
        movement_form.addRow(clear_move_timing_button)
        movement_form.addRow("Facing", self.facing_degrees)
        movement_form.addRow(apply_facing_button)
        movement_form.addRow(facing_buttons)
        movement_form.addRow("", self.facing_status)
        movement_form.addRow("", self.movement_style_status)
        self.move_timing_widgets = [
            self.move_start_count,
            self.move_end_count,
            apply_move_timing_button,
            start_now_button,
            clear_move_timing_button,
        ]
        self.facing_widgets = [
            self.facing_degrees,
            apply_facing_button,
            rotate_left_button,
            rotate_right_button,
            face_front_button,
            face_back_button,
        ]
        rehearsal_layout.addWidget(movement_group)

        audio_group = QGroupBox("Audio + Timing Map")
        audio_form = QFormLayout(audio_group)
        self.base_tempo = QDoubleSpinBox()
        self.base_tempo.setRange(40, 320)
        self.base_tempo.setValue(self.project.metadata.initial_tempo)
        self.base_tempo.setDecimals(1)
        self.base_tempo.setSuffix(" BPM")
        self.base_tempo.valueChanged.connect(self.update_base_tempo)
        self.audio_version_combo = QComboBox()
        self.audio_version_combo.currentIndexChanged.connect(self.switch_audio_version)
        add_audio_button = QPushButton("Add Audio Version")
        add_audio_button.clicked.connect(self.add_audio_version)
        reload_audio_button = QPushButton("Reload Audio")
        reload_audio_button.clicked.connect(self.reload_audio)
        map_anchor_button = QPushButton("Map Current Count To Audio")
        map_anchor_button.clicked.connect(self.map_current_count_to_audio)
        tempo_here_button = QPushButton("Set Tempo At Current Count")
        tempo_here_button.clicked.connect(self.add_tempo_change_at_current_count)
        self.timing_event_type = QComboBox()
        self.timing_event_type.addItems(["anchor", "tempo", "ritard", "fermata", "pickup"])
        self.timing_event_tempo = QDoubleSpinBox()
        self.timing_event_tempo.setRange(0, 320)
        self.timing_event_tempo.setValue(self.project.metadata.initial_tempo)
        self.timing_event_tempo.setSuffix(" BPM")
        self.timing_event_end_count = QDoubleSpinBox()
        self.timing_event_end_count.setRange(1, 9999)
        self.timing_event_end_count.setDecimals(2)
        self.timing_event_end_tempo = QDoubleSpinBox()
        self.timing_event_end_tempo.setRange(0, 320)
        self.timing_event_end_tempo.setValue(self.project.metadata.initial_tempo)
        self.timing_event_end_tempo.setSuffix(" BPM")
        self.timing_event_ms = QDoubleSpinBox()
        self.timing_event_ms.setRange(-60000, 60000)
        self.timing_event_ms.setDecimals(0)
        self.timing_event_ms.setSuffix(" ms")
        add_timing_button = QPushButton("Add Timing Event")
        add_timing_button.clicked.connect(self.add_timing_event)
        clear_timing_button = QPushButton("Clear Timing Events")
        clear_timing_button.clicked.connect(self.clear_timing_events)
        self.timing_event_list = QListWidget()
        audio_form.addRow("Base Tempo", self.base_tempo)
        audio_form.addRow("Audio Version", self.audio_version_combo)
        audio_form.addRow(add_audio_button)
        audio_form.addRow(reload_audio_button)
        audio_form.addRow(map_anchor_button)
        audio_form.addRow("Event Type", self.timing_event_type)
        audio_form.addRow("Tempo", self.timing_event_tempo)
        audio_form.addRow("End Count", self.timing_event_end_count)
        audio_form.addRow("End Tempo", self.timing_event_end_tempo)
        audio_form.addRow("Milliseconds", self.timing_event_ms)
        audio_form.addRow(tempo_here_button)
        audio_form.addRow(add_timing_button)
        audio_form.addRow(clear_timing_button)
        audio_form.addRow("Timing Events", self.timing_event_list)
        rehearsal_layout.addWidget(audio_group)
        rehearsal_layout.addStretch()
        tabs.addTab(rehearsal_tab, "Rehearse")

        view_group = QGroupBox("View")
        view_layout = QVBoxLayout(view_group)
        labels = QCheckBox("Labels")
        labels.setChecked(True)
        labels.toggled.connect(self.field.update_labels)
        self.ghost_previous_set = QCheckBox("Ghost Previous Set")
        self.ghost_previous_set.setChecked(
            self.settings.value("view/ghost_previous_set", True, type=bool)
        )
        self.ghost_previous_set.setToolTip(
            "Shows the previous set as a faint, non-editable formation behind the current set."
        )
        self.ghost_previous_set.toggled.connect(self.set_ghosts_enabled)
        self.field.set_ghosts_visible(self.ghost_previous_set.isChecked())
        self.show_minimap_checkbox = QCheckBox("Field Minimap")
        self.show_minimap_checkbox.setChecked(self.minimap_visible())
        self.show_minimap_checkbox.toggled.connect(self.set_minimap_visible)
        self.show_field_hud_checkbox = QCheckBox("Tool HUD")
        self.show_field_hud_checkbox.setChecked(self.field_hud_enabled())
        self.show_field_hud_checkbox.setToolTip("Shows Apply/Clear only while a formation tool is active. Drag it to move.")
        self.show_field_hud_checkbox.toggled.connect(self.set_field_hud_enabled)
        self.snap_align = QCheckBox("Smart Alignment Guides")
        self.snap_align.setToolTip(
            "Temporarily align selections to yard lines, hashes, centers, and nearby marchers. "
            "Use Drill Grid & Snap in the Forms tab for exact step intervals."
        )
        self.snap_align.toggled.connect(self.field.set_snap_enabled)
        view_layout.addWidget(labels)
        view_layout.addWidget(self.ghost_previous_set)
        view_layout.addWidget(self.show_minimap_checkbox)
        view_layout.addWidget(self.show_field_hud_checkbox)
        view_layout.addWidget(self.snap_align)
        view_tab = QWidget()
        self.view_tab = view_tab
        view_tab_layout = QVBoxLayout(view_tab)
        view_tab_layout.addWidget(view_group)
        view_tab_layout.addStretch()
        tabs.addTab(view_tab, "View")
        tabs.setPageOrder(
            [
                (marchers_tab, "Marchers"),
                (formation_tab, "Forms"),
                (motion_tab, "Motion"),
                (align_tab, "Align"),
                (accelerator_tab, "Accelerate"),
                (props_tab, "Props"),
                (prop_designer_tab, "Prop Designer"),
                (music_tab, "Music"),
                (specialized_tab, "Specialized"),
                (large_show_tab, "Large Show"),
                (analysis_tab, "Safety"),
                (rehearsal_tab, "Rehearse"),
                (view_tab, "Display"),
            ]
        )
        tabs.selector.setToolTip(
            "Pages are ordered by workflow: roster, design, production, show planning, review, and display."
        )
        self.set_tool(EditorTool.SELECT)
        return panel

    def build_inspector_panel(self) -> QWidget:
        panel = ResponsivePanelWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        tabs = CompactTabWidget()
        tabs.setObjectName("SideTabs")
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(True)
        tabs.setMinimumWidth(0)
        tabs.tabBar().setExpanding(False)
        tabs.tabBar().setElideMode(Qt.TextElideMode.ElideRight)
        self.inspector_tabs = tabs
        layout.addWidget(tabs)

        selection_tab = QWidget()
        self.selection_tab = selection_tab
        selection_layout = QVBoxLayout(selection_tab)
        self.selection_label = QLabel("No selection")
        selection_layout.addWidget(self.selection_label)

        dot_group = QGroupBox("Dot Properties")
        self.dot_properties_group = dot_group
        form = QFormLayout(dot_group)
        self.dot_name = QLineEdit()
        self.dot_section = QLineEdit()
        self.dot_instrument = QLineEdit()
        self.dot_rank = QLineEdit()
        self.dot_equipment = QLineEdit()
        self.dot_layer = QLineEdit("Main")
        self.dot_x = QLineEdit()
        self.dot_y = QLineEdit()
        self.dot_yardline = QLabel("-")
        self.dot_hash = QLabel("-")
        self.dot_yardline.setObjectName("CoordinateReadout")
        self.dot_hash.setObjectName("CoordinateReadout")
        for editor in (
            self.dot_name,
            self.dot_section,
            self.dot_instrument,
            self.dot_rank,
            self.dot_equipment,
            self.dot_layer,
        ):
            editor.editingFinished.connect(self.update_selected_dot)
        self.dot_x.editingFinished.connect(self.update_selected_dot_position)
        self.dot_y.editingFinished.connect(self.update_selected_dot_position)
        form.addRow("Name", self.dot_name)
        form.addRow("Section", self.dot_section)
        form.addRow("Instrument", self.dot_instrument)
        form.addRow("Rank", self.dot_rank)
        form.addRow("Equipment", self.dot_equipment)
        form.addRow("Layer", self.dot_layer)
        form.addRow("X", self.dot_x)
        form.addRow("Y", self.dot_y)
        form.addRow("Yard Line", self.dot_yardline)
        form.addRow("Hash", self.dot_hash)
        selection_layout.addWidget(dot_group)

        coordinate_group = QGroupBox("Keyboard Drill Entry")
        coordinate_layout = QVBoxLayout(coordinate_group)
        coordinate_note = QLabel('Type: "T1 on 45 s2, 4 in front FH"')
        coordinate_note.setWordWrap(True)
        self.coordinate_entry = QLineEdit()
        self.coordinate_entry.setPlaceholderText("T1 on 45 s2, 4 in front FH")
        self.coordinate_entry.returnPressed.connect(self.apply_coordinate_entry)
        coordinate_apply = QPushButton("Apply Coordinate")
        coordinate_apply.clicked.connect(self.apply_coordinate_entry)
        coordinate_layout.addWidget(coordinate_note)
        coordinate_layout.addWidget(self.coordinate_entry)
        coordinate_layout.addWidget(coordinate_apply)
        selection_layout.addWidget(coordinate_group)

        appearance_group = QGroupBox("Appearance")
        appearance_form = QFormLayout(appearance_group)
        self.selected_color_swatch = QLabel("No selection")
        self.selected_color_swatch.setObjectName("ColorSwatch")
        self.selected_color_swatch.setMinimumWidth(90)
        self.selected_color_swatch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        selected_color_button = QPushButton("Choose")
        selected_color_button.clicked.connect(self.choose_selected_dot_color)
        selected_color_row = QWidget()
        selected_color_layout = QHBoxLayout(selected_color_row)
        selected_color_layout.setContentsMargins(0, 0, 0, 0)
        selected_color_layout.addWidget(self.selected_color_swatch, 1)
        selected_color_layout.addWidget(selected_color_button)
        self.selected_color_button = selected_color_button

        self.bulk_section = QLineEdit()
        self.bulk_section.setPlaceholderText("winds, brass, woodwinds...")
        bulk_section_button = QPushButton("Apply")
        bulk_section_button.clicked.connect(self.assign_selected_section)
        bulk_section_row = QWidget()
        bulk_section_layout = QHBoxLayout(bulk_section_row)
        bulk_section_layout.setContentsMargins(0, 0, 0, 0)
        bulk_section_layout.addWidget(self.bulk_section, 1)
        bulk_section_layout.addWidget(bulk_section_button)
        self.bulk_section_button = bulk_section_button

        self.bulk_instrument = QLineEdit()
        self.bulk_instrument.setPlaceholderText("Trumpet, flute, snare...")
        self.bulk_rank = QLineEdit()
        self.bulk_rank.setPlaceholderText("Rank / file")
        self.bulk_equipment = QLineEdit()
        self.bulk_equipment.setPlaceholderText("Flag, rifle, prop...")
        self.bulk_layer = QLineEdit()
        self.bulk_layer.setPlaceholderText("Main, Brass, Guard...")
        batch_button = QPushButton("Apply Batch Metadata")
        batch_button.clicked.connect(self.apply_batch_dot_metadata)
        self.batch_metadata_button = batch_button

        self.section_color_combo = QComboBox()
        section_color_button = QPushButton("Color")
        section_color_button.clicked.connect(self.choose_section_color)
        section_color_row = QWidget()
        section_color_layout = QHBoxLayout(section_color_row)
        section_color_layout.setContentsMargins(0, 0, 0, 0)
        section_color_layout.addWidget(self.section_color_combo, 1)
        section_color_layout.addWidget(section_color_button)
        self.section_color_button = section_color_button

        appearance_form.addRow("Selected", selected_color_row)
        appearance_form.addRow("Set Section", bulk_section_row)
        appearance_form.addRow("Instrument", self.bulk_instrument)
        appearance_form.addRow("Rank", self.bulk_rank)
        appearance_form.addRow("Equipment", self.bulk_equipment)
        appearance_form.addRow("Layer", self.bulk_layer)
        appearance_form.addRow(batch_button)
        appearance_form.addRow("Section Color", section_color_row)
        selection_layout.addWidget(appearance_group)

        facing_group = QGroupBox("Triangle Facing / Visual Turn")
        facing_form = QFormLayout(facing_group)
        facing_note = QLabel("Visible when marcher symbol preference is Triangle. Select marchers, then set their facing for this set.")
        facing_note.setWordWrap(True)
        self.selection_facing_degrees = QDoubleSpinBox()
        self.selection_facing_degrees.setRange(0, 359.9)
        self.selection_facing_degrees.setDecimals(1)
        self.selection_facing_degrees.setSingleStep(15)
        self.selection_facing_degrees.setSuffix("°")
        self.selection_facing_degrees.setToolTip("0° faces front field. 90° points Side Two. 180° faces back field. 270° points Side One.")
        selection_apply_facing = QPushButton("Apply Facing")
        selection_apply_facing.clicked.connect(lambda: self.set_selected_facing(self.selection_facing_degrees.value()))
        selection_face_front = QPushButton("Front")
        selection_face_front.clicked.connect(lambda: self.set_selected_facing(0))
        selection_face_back = QPushButton("Back")
        selection_face_back.clicked.connect(lambda: self.set_selected_facing(180))
        selection_rotate_left = QPushButton("-45°")
        selection_rotate_left.clicked.connect(lambda: self.rotate_selected_facing(-45))
        selection_rotate_right = QPushButton("+45°")
        selection_rotate_right.clicked.connect(lambda: self.rotate_selected_facing(45))
        facing_button_row = QWidget()
        facing_button_layout = QGridLayout(facing_button_row)
        facing_button_layout.setContentsMargins(0, 0, 0, 0)
        facing_button_layout.addWidget(selection_rotate_left, 0, 0)
        facing_button_layout.addWidget(selection_rotate_right, 0, 1)
        facing_button_layout.addWidget(selection_face_front, 1, 0)
        facing_button_layout.addWidget(selection_face_back, 1, 1)
        self.selection_facing_status = QLabel("Select marchers to set facing.")
        self.selection_facing_status.setWordWrap(True)
        facing_form.addRow("", facing_note)
        facing_form.addRow("Facing", self.selection_facing_degrees)
        facing_form.addRow(selection_apply_facing)
        facing_form.addRow(facing_button_row)
        facing_form.addRow("", self.selection_facing_status)
        self.selection_facing_widgets = [
            self.selection_facing_degrees,
            selection_apply_facing,
            selection_face_front,
            selection_face_back,
            selection_rotate_left,
            selection_rotate_right,
        ]
        selection_layout.addWidget(facing_group)

        transform_group = QGroupBox("Unified Transform")
        transform_layout = QGridLayout(transform_group)
        self.transform_offset_x = QDoubleSpinBox()
        self.transform_offset_y = QDoubleSpinBox()
        self.transform_rotation = QDoubleSpinBox()
        self.transform_scale_x = QDoubleSpinBox()
        self.transform_scale_y = QDoubleSpinBox()
        self.transform_skew_x = QDoubleSpinBox()
        self.transform_skew_y = QDoubleSpinBox()
        self.transform_pivot_x = QDoubleSpinBox()
        self.transform_pivot_y = QDoubleSpinBox()
        for editor in (self.transform_offset_x, self.transform_offset_y, self.transform_pivot_x, self.transform_pivot_y):
            editor.setRange(-120, 120)
            editor.setDecimals(3)
            editor.setSingleStep(0.625)
            editor.setSuffix(" yd")
        self.transform_rotation.setRange(-360, 360)
        self.transform_rotation.setDecimals(1)
        self.transform_rotation.setSuffix(" deg")
        for editor in (self.transform_scale_x, self.transform_scale_y):
            editor.setRange(-12, 12)
            editor.setDecimals(3)
            editor.setSingleStep(0.05)
            editor.setValue(1.0)
        for editor in (self.transform_skew_x, self.transform_skew_y):
            editor.setRange(-80, 80)
            editor.setDecimals(1)
            editor.setSuffix(" deg")
        compact_fields = (
            ("Move X", self.transform_offset_x),
            ("Move Y", self.transform_offset_y),
            ("Rotate", self.transform_rotation),
            ("Scale X", self.transform_scale_x),
            ("Scale Y", self.transform_scale_y),
            ("Skew X", self.transform_skew_x),
            ("Skew Y", self.transform_skew_y),
            ("Pivot X", self.transform_pivot_x),
            ("Pivot Y", self.transform_pivot_y),
        )
        for row, (label, editor) in enumerate(compact_fields):
            transform_layout.addWidget(QLabel(label), row, 0)
            transform_layout.addWidget(editor, row, 1)
        center_pivot_button = QPushButton("Pivot = Selection Center")
        center_pivot_button.clicked.connect(self.center_numeric_transform_pivot)
        self.transform_custom_pivot = QCheckBox("Use exact pivot")
        apply_transform_button = QPushButton("Apply Transform")
        apply_transform_button.clicked.connect(self.apply_numeric_transform)
        reset_transform_button = QPushButton("Reset")
        reset_transform_button.clicked.connect(self.reset_numeric_transform)
        self.transform_handles_button = QPushButton("Show On-Field Handles")
        self.transform_handles_button.setCheckable(True)
        self.transform_handles_button.clicked.connect(self.set_transform_gizmo_visible)
        transform_layout.setColumnStretch(1, 1)
        transform_layout.addWidget(center_pivot_button, 9, 0, 1, 2)
        transform_layout.addWidget(self.transform_custom_pivot, 10, 0, 1, 2)
        transform_layout.addWidget(apply_transform_button, 11, 0, 1, 2)
        transform_layout.addWidget(reset_transform_button, 12, 0, 1, 2)
        transform_layout.addWidget(self.transform_handles_button, 13, 0, 1, 2)
        self.sync_transform_handle_controls()
        selection_layout.addWidget(transform_group)

        bulk_group = QGroupBox("Bulk Property Editor")
        bulk_form = QFormLayout(bulk_group)
        self.bulk_offset_x = QDoubleSpinBox()
        self.bulk_offset_x.setRange(-120, 120)
        self.bulk_offset_x.setDecimals(2)
        self.bulk_offset_x.setSuffix(" yd")
        self.bulk_offset_y = QDoubleSpinBox()
        self.bulk_offset_y.setRange(-54, 54)
        self.bulk_offset_y.setDecimals(2)
        self.bulk_offset_y.setSuffix(" yd")
        self.bulk_path_action = QComboBox()
        self.bulk_path_action.addItems(["Leave Paths", "Clear Selected Paths", "Carry Positions Forward"])
        bulk_apply = QPushButton("Apply Bulk Edit")
        bulk_apply.clicked.connect(self.apply_bulk_property_editor)
        bulk_form.addRow("Offset X", self.bulk_offset_x)
        bulk_form.addRow("Offset Y", self.bulk_offset_y)
        bulk_form.addRow("Path Action", self.bulk_path_action)
        bulk_form.addRow(bulk_apply)
        selection_layout.addWidget(bulk_group)

        prop_group = QGroupBox("Prop Properties")
        self.prop_properties_group = prop_group
        prop_form = QFormLayout(prop_group)
        self.prop_name = QLineEdit()
        self.prop_layer = QLineEdit("Props")
        self.prop_x = QDoubleSpinBox()
        self.prop_x.setRange(-80, 80)
        self.prop_x.setDecimals(2)
        self.prop_y = QDoubleSpinBox()
        self.prop_y.setRange(-40, 40)
        self.prop_y.setDecimals(2)
        self.prop_width = QDoubleSpinBox()
        self.prop_width.setRange(0.25, 80)
        self.prop_width.setDecimals(2)
        self.prop_width.setSuffix(" yd")
        self.prop_height = QDoubleSpinBox()
        self.prop_height.setRange(0.25, 54)
        self.prop_height.setDecimals(2)
        self.prop_height.setSuffix(" yd")
        self.prop_rotation = QDoubleSpinBox()
        self.prop_rotation.setRange(-360, 360)
        self.prop_rotation.setDecimals(1)
        self.prop_rotation.setSuffix(" deg")
        self.prop_name.editingFinished.connect(self.update_selected_prop_metadata)
        self.prop_layer.editingFinished.connect(self.update_selected_prop_metadata)
        for editor in (self.prop_x, self.prop_y, self.prop_width, self.prop_height, self.prop_rotation):
            editor.valueChanged.connect(self.update_selected_prop_state)
        prop_form.addRow("Name", self.prop_name)
        prop_form.addRow("Layer", self.prop_layer)
        prop_form.addRow("X", self.prop_x)
        prop_form.addRow("Y", self.prop_y)
        prop_form.addRow("Width", self.prop_width)
        prop_form.addRow("Height", self.prop_height)
        prop_form.addRow("Rotation", self.prop_rotation)
        selection_layout.addWidget(prop_group)
        selection_layout.addStretch()
        tabs.addTab(selection_tab, "Selection")

        sets_tab = QWidget()
        self.sets_tab = sets_tab
        sets_layout = QVBoxLayout(sets_tab)
        set_group = QGroupBox("Sets")
        set_layout = QVBoxLayout(set_group)
        self.set_search = QLineEdit()
        self.set_search.setPlaceholderText("Search sets...")
        self.set_search.textChanged.connect(self.filter_set_list)
        set_layout.addWidget(self.set_search)
        self.set_thumbnail_toggle = QCheckBox("Show Set Thumbnails")
        self.set_thumbnail_toggle.setChecked(self.set_thumbnails_enabled())
        self.set_thumbnail_toggle.setToolTip("Turn off for a compact scrolling set list on smaller screens.")
        self.set_thumbnail_toggle.toggled.connect(self.set_set_thumbnails_enabled)
        set_layout.addWidget(self.set_thumbnail_toggle)
        self.set_list = QListWidget()
        self.set_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.set_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.set_list.setAlternatingRowColors(False)
        self.set_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.set_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.set_list.setMinimumHeight(170)
        self.set_list.currentRowChanged.connect(self.change_set)
        self.set_list.model().rowsMoved.connect(self.reorder_sets_from_list)
        self.configure_set_list_view()
        set_layout.addWidget(self.set_list)
        buttons = QHBoxLayout()
        add_button = QPushButton("+")
        add_button.clicked.connect(self.add_set)
        remove_button = QPushButton("-")
        remove_button.clicked.connect(self.remove_set)
        copy_button = QPushButton("Copy")
        copy_button.clicked.connect(self.copy_set)
        buttons.addWidget(add_button)
        buttons.addWidget(remove_button)
        buttons.addWidget(copy_button)
        set_layout.addLayout(buttons)
        details = QGroupBox("Set Details")
        details_form = QFormLayout(details)
        self.set_name = QLineEdit()
        self.set_start_count = QSpinBox()
        self.set_start_count.setRange(1, 9999)
        self.set_count_length = QSpinBox()
        self.set_count_length.setRange(1, 512)
        self.set_end_count = QSpinBox()
        self.set_end_count.setRange(1, 9999)
        self.set_tempo = QDoubleSpinBox()
        self.set_tempo.setRange(0, 300)
        self.set_tempo.setDecimals(1)
        self.set_tempo.setSpecialValueText("Show BPM")
        self.set_tempo.setSuffix(" BPM")
        self.transition_combo = QComboBox()
        self.transition_combo.addItems([transition.value for transition in Transition])
        self.set_director_notes = CommitPlainTextEdit()
        self.set_director_notes.setPlaceholderText(
            "Describe the visual, staging intent, production cue, or rehearsal focus for this set."
        )
        self.set_director_notes.setToolTip(
            "Saved with this set and printed above its field chart in drill sheets and staff packets."
        )
        self.set_director_notes.setAccessibleName("Director's Notes")
        self.set_director_notes.setTabChangesFocus(True)
        self.set_director_notes.setMinimumHeight(84)
        self.set_director_notes.setMaximumHeight(132)
        self.set_name.editingFinished.connect(self.update_set_details)
        self.set_start_count.valueChanged.connect(self.update_set_details)
        self.set_count_length.valueChanged.connect(self.update_set_length)
        self.set_end_count.valueChanged.connect(self.update_set_details)
        self.set_tempo.valueChanged.connect(self.update_set_details)
        self.transition_combo.currentTextChanged.connect(self.update_transition)
        self.set_director_notes.editingStarted.connect(self.begin_set_director_notes_edit)
        self.set_director_notes.textChanged.connect(self.preview_set_director_notes_edit)
        self.set_director_notes.editingFinished.connect(self.finish_set_director_notes_edit)
        details_form.addRow("Name", self.set_name)
        details_form.addRow("Start", self.set_start_count)
        details_form.addRow("Counts", self.set_count_length)
        details_form.addRow("End", self.set_end_count)
        details_form.addRow("Tempo", self.set_tempo)
        details_form.addRow("Transition", self.transition_combo)
        details_form.addRow(QLabel("Director's Notes"))
        details_form.addRow(self.set_director_notes)
        set_layout.addWidget(details)
        multi_group = QGroupBox("Ripple Edit Scope")
        multi_form = QFormLayout(multi_group)
        self.edit_scope_combo = QComboBox()
        self.edit_scope_combo.addItem("Current set only", "current")
        self.edit_scope_combo.addItem("From current set forward", "forward")
        self.edit_scope_combo.addItem("Selected set range", "selected_range")
        self.edit_scope_combo.addItem("Until next keyframe", "until_next_keyframe")
        self.edit_scope_combo.addItem("Every matching formation", "matching")
        self.edit_scope_combo.setToolTip("Choose where marcher transforms, timing, facing, paths, and painted properties are applied.")
        self.multi_set_start = QSpinBox()
        self.multi_set_start.setRange(1, max(1, len(self.project.sets)))
        self.multi_set_end = QSpinBox()
        self.multi_set_end.setRange(1, max(1, len(self.project.sets)))
        self.multi_set_end.setValue(max(1, len(self.project.sets)))
        multi_form.addRow("Apply edits to", self.edit_scope_combo)
        multi_form.addRow("Start Set", self.multi_set_start)
        multi_form.addRow("End Set", self.multi_set_end)
        set_layout.addWidget(multi_group)
        sets_layout.addWidget(set_group, 1)
        tabs.addTab(sets_tab, "Sets")

        visibility_tab = QWidget()
        self.visibility_tab = visibility_tab
        visibility_layout = QVBoxLayout(visibility_tab)
        visibility_group = QGroupBox("Visibility")
        visibility_form = QFormLayout(visibility_group)
        self.section_filter = QComboBox()
        self.layer_filter = QComboBox()
        self.section_filter.currentTextChanged.connect(self.apply_visibility_filters)
        self.layer_filter.currentTextChanged.connect(self.apply_visibility_filters)
        visibility_form.addRow("Section", self.section_filter)
        visibility_form.addRow("Layer", self.layer_filter)
        visibility_layout.addWidget(visibility_group)
        locks_group = QGroupBox("Locks")
        locks_layout = QFormLayout(locks_group)
        locks_layout.setVerticalSpacing(6)
        self.lock_section_combo = QComboBox()
        self.lock_layer_combo = QComboBox()
        lock_section_row = QHBoxLayout()
        lock_section_button = QPushButton("Lock")
        lock_section_button.clicked.connect(self.lock_current_section)
        unlock_section_button = QPushButton("Unlock")
        unlock_section_button.clicked.connect(self.unlock_current_section)
        lock_section_row.addWidget(lock_section_button)
        lock_section_row.addWidget(unlock_section_button)
        lock_layer_row = QHBoxLayout()
        lock_layer_button = QPushButton("Lock")
        lock_layer_button.clicked.connect(self.lock_current_layer)
        unlock_layer_button = QPushButton("Unlock")
        unlock_layer_button.clicked.connect(self.unlock_current_layer)
        lock_layer_row.addWidget(lock_layer_button)
        lock_layer_row.addWidget(unlock_layer_button)
        selected_lock_grid = QGridLayout()
        lock_selected_button = QPushButton("Lock Sel.")
        lock_selected_button.setToolTip("Lock the sections represented by the selected marchers.")
        lock_selected_button.clicked.connect(self.lock_selected_sections)
        unlock_selected_button = QPushButton("Unlock Sel.")
        unlock_selected_button.setToolTip("Unlock the sections represented by the selected marchers.")
        unlock_selected_button.clicked.connect(self.unlock_selected_sections)
        clear_locks_button = QPushButton("Clear")
        clear_locks_button.setToolTip("Clear all section and layer locks.")
        clear_locks_button.clicked.connect(self.clear_section_locks)
        selected_lock_grid.addWidget(lock_selected_button, 0, 0)
        selected_lock_grid.addWidget(unlock_selected_button, 0, 1)
        selected_lock_grid.addWidget(clear_locks_button, 0, 2)
        self.lock_status_label = QLabel("No locked sections or layers")
        self.lock_status_label.setWordWrap(True)
        locks_layout.addRow("Section", self.lock_section_combo)
        locks_layout.addRow(lock_section_row)
        locks_layout.addRow("Layer", self.lock_layer_combo)
        locks_layout.addRow(lock_layer_row)
        locks_layout.addRow(selected_lock_grid)
        locks_layout.addRow(self.lock_status_label)
        visibility_layout.addWidget(locks_group)
        visibility_layout.addStretch()
        tabs.addTab(visibility_tab, "Visibility")
        return panel

    def build_timeline_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 4, 6, 4)
        tabs = CompactTabWidget()
        tabs.setObjectName("TimelineTabs")
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(True)
        tabs.tabBar().setExpanding(False)
        audio_page = QWidget()
        audio_layout = QVBoxLayout(audio_page)
        audio_layout.setContentsMargins(4, 4, 4, 4)
        self.waveform = WaveformWidget()
        self.waveform.setMinimumHeight(64)
        self.waveform.set_project(self.project)
        self.waveform.position_selected.connect(self.seek_audio_position)
        self.waveform.load_finished.connect(self.waveform_load_finished)
        audio_layout.addWidget(self.waveform)
        row = QHBoxLayout()
        self.count_label = QLabel("Count 1")
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.valueChanged.connect(self.scrub)
        self.marker_button = QPushButton("Add Marker")
        self.marker_button.clicked.connect(self.add_marker)
        row.addWidget(self.count_label)
        row.addWidget(self.timeline, 1)
        row.addWidget(self.marker_button)
        generate_sets_button = QPushButton("Generate Sets")
        generate_sets_button.setToolTip("Create set boundaries from selected musical markers.")
        generate_sets_button.clicked.connect(self.show_beat_set_generator)
        row.addWidget(generate_sets_button)
        audio_layout.addLayout(row)
        diagnostics_row = QHBoxLayout()
        self.playback_diagnostics_label = QLabel("Playback diagnostics: ready")
        self.playback_diagnostics_label.setObjectName("ToolHintLabel")
        self.playback_diagnostics_label.setToolTip(
            "Measured field frame rate, deadline misses, adaptive skips, render cost, and cache use."
        )
        reset_diagnostics_button = QPushButton("Reset Stats")
        reset_diagnostics_button.setMaximumWidth(96)
        reset_diagnostics_button.clicked.connect(self.reset_playback_diagnostics)
        diagnostics_row.addWidget(self.playback_diagnostics_label, 1)
        diagnostics_row.addWidget(reset_diagnostics_button)
        audio_layout.addLayout(diagnostics_row)
        self.marker_table = QTableWidget(0, 2)
        self.marker_table.setHorizontalHeaderLabels(["Count", "Marker"])
        self.marker_table.setMinimumHeight(52)
        self.marker_table.setMaximumHeight(72)
        self.marker_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.marker_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        audio_layout.addWidget(self.marker_table)
        tabs.addTab(audio_page, "Audio & Counts")

        movement_page = QWidget()
        movement_layout = QVBoxLayout(movement_page)
        movement_layout.setContentsMargins(4, 4, 4, 4)
        movement_header = QHBoxLayout()
        movement_header.addWidget(QLabel("Movement lanes"))
        self.transition_timeline_mode = QComboBox()
        self.transition_timeline_mode.addItems(["Sections", "Selected Marchers"])
        self.transition_timeline_mode.currentTextChanged.connect(self.refresh_transition_timeline)
        movement_header.addWidget(self.transition_timeline_mode)
        movement_header.addStretch()
        movement_hint = QLabel("Drag edges for holds/staggers; shorter bars move faster")
        movement_layout.addLayout(movement_header)
        movement_hint.setWordWrap(True)
        movement_hint.setObjectName("ToolHintLabel")
        movement_layout.addWidget(movement_hint)
        timeline_scroll = QScrollArea()
        timeline_scroll.setWidgetResizable(True)
        timeline_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        timeline_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.transition_timeline = TransitionTimelineWidget()
        self.transition_timeline.move_window_changed.connect(self.apply_timeline_move_window)
        timeline_scroll.setWidget(self.transition_timeline)
        movement_layout.addWidget(timeline_scroll, 1)
        tabs.addTab(movement_page, "Movement Lanes")

        choreography_page = QWidget()
        choreography_layout = QVBoxLayout(choreography_page)
        choreography_layout.setContentsMargins(4, 4, 4, 4)
        choreography_hint = QLabel("Guard tosses, equipment changes, and choreography ranges. Edit them in Tools → Specialized Design.")
        choreography_hint.setWordWrap(True)
        choreography_hint.setObjectName("ToolHintLabel")
        choreography_layout.addWidget(choreography_hint)
        choreography_scroll = QScrollArea()
        choreography_scroll.setWidgetResizable(True)
        choreography_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        choreography_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.choreography_timeline = ChoreographyTimelineWidget()
        self.choreography_timeline.set_project(self.project)
        choreography_scroll.setWidget(self.choreography_timeline)
        choreography_layout.addWidget(choreography_scroll, 1)
        tabs.addTab(choreography_page, "Choreography")
        layout.addWidget(tabs)
        return panel

    def load_audio(self) -> None:
        audio = active_audio_version(self.project)
        audio_file = audio.audio_file if audio else self.project.metadata.audio_file
        audio_path = self.project_dir / audio_file if audio_file else None
        if audio_path and audio_path.exists():
            self.player.setSource(QUrl.fromLocalFile(str(audio_path)))
            if hasattr(self, "waveform"):
                self.waveform.load_audio(audio_path)
        elif hasattr(self, "waveform"):
            self.waveform.load_audio(None)

    def reload_audio(self) -> None:
        was_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        position = self.player.position()
        self.load_audio()
        if self.player.source().isValid():
            self.player.setPosition(position)
            if was_playing:
                self.player.play()
        self.statusBar().showMessage("Reloading waveform in the background…", 2200)

    def waveform_load_finished(self, success: bool, message: str) -> None:
        if success:
            self.statusBar().showMessage(message or "Audio waveform loaded", 2600)
        else:
            self.statusBar().showMessage(message or "Audio waveform could not be loaded", 5000)

    def audio_duration_changed(self, duration_ms: int) -> None:
        if hasattr(self, "waveform"):
            self.waveform.set_duration_ms(duration_ms)

    def audio_position_changed(self, position_ms: int) -> None:
        if hasattr(self, "waveform"):
            self.waveform.set_position_ms(position_ms)

    def refresh_audio_versions(self) -> None:
        if not hasattr(self, "audio_version_combo"):
            return
        self.audio_version_combo.blockSignals(True)
        self.audio_version_combo.clear()
        if not self.project.audio_versions and self.project.metadata.audio_file:
            self.project.audio_versions.append(
                AudioVersion("Main Audio", self.project.metadata.audio_file, True)
            )
        for audio in self.project.audio_versions:
            self.audio_version_combo.addItem(audio.name, audio.audio_file)
        active = active_audio_version(self.project)
        if active:
            index = self.audio_version_combo.findData(active.audio_file)
            self.audio_version_combo.setCurrentIndex(max(0, index))
        self.audio_version_combo.blockSignals(False)

    def add_audio_version(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Add Audio Version",
            str(Path.home()),
            "Audio Files (*.mp3 *.wav *.aiff *.flac)",
        )
        if not path:
            return
        source = Path(path)
        destination = self.project_dir / "audio" / source.name
        destination.parent.mkdir(exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        relative = str(destination.relative_to(self.project_dir))
        for audio in self.project.audio_versions:
            audio.active = False
        self.project.audio_versions.append(
            AudioVersion(source.stem, relative, True)
        )
        set_active_audio_version(self.project, relative)
        self.refresh_audio_versions()
        self.load_audio()

    def switch_audio_version(self, *_args) -> None:
        if not hasattr(self, "audio_version_combo"):
            return
        audio_file = self.audio_version_combo.currentData()
        if not audio_file:
            return
        set_active_audio_version(self.project, str(audio_file))
        self.load_audio()

    def map_current_count_to_audio(self) -> None:
        milliseconds = self.player.position() if self.player.source().isValid() else 0
        self.project.timing_events.append(
            TimingEvent(
                event_type="anchor",
                count=round(self.current_count, 2),
                milliseconds=float(milliseconds),
                label=f"Count {self.current_count:.2f}",
            )
        )
        self.refresh_timing_events()
        self.statusBar().showMessage("Timing anchor added", 2000)

    def update_base_tempo(self, value: float) -> None:
        self.project.metadata.initial_tempo = value
        self.timing_event_tempo.blockSignals(True)
        self.timing_event_end_tempo.blockSignals(True)
        if self.timing_event_tempo.value() <= 0:
            self.timing_event_tempo.setValue(value)
        if self.timing_event_end_tempo.value() <= 0:
            self.timing_event_end_tempo.setValue(value)
        self.timing_event_tempo.blockSignals(False)
        self.timing_event_end_tempo.blockSignals(False)
        self.populate_sets()
        self.sync_timeline()
        if hasattr(self, "waveform"):
            self.waveform.update()

    def add_tempo_change_at_current_count(self) -> None:
        tempo = self.timing_event_tempo.value() or self.project.metadata.initial_tempo
        self.project.timing_events.append(
            TimingEvent(
                event_type="tempo",
                count=round(self.current_count, 2),
                tempo=tempo,
                label=f"Tempo {tempo:g} BPM",
            )
        )
        self.refresh_timing_events()
        self.populate_sets()
        self.statusBar().showMessage(f"Tempo change added at count {self.current_count:.2f}", 2200)

    def add_timing_event(self) -> None:
        event_type = self.timing_event_type.currentText()
        milliseconds = self.timing_event_ms.value()
        if event_type == "anchor" and self.player.source().isValid():
            milliseconds = self.player.position()
        end_count = self.timing_event_end_count.value()
        if event_type == "ritard" and end_count <= self.current_count:
            end_count = min(self.current_set().end_count, self.current_count + 4)
        self.project.timing_events.append(
            TimingEvent(
                event_type=event_type,
                count=round(self.current_count, 2),
                milliseconds=milliseconds,
                tempo=self.timing_event_tempo.value(),
                end_count=end_count,
                end_tempo=self.timing_event_end_tempo.value(),
            )
        )
        self.refresh_timing_events()

    def clear_timing_events(self) -> None:
        self.project.timing_events.clear()
        self.refresh_timing_events()

    def refresh_timing_events(self) -> None:
        if hasattr(self, "timing_event_list"):
            self.timing_event_list.clear()
            for event in sorted(self.project.timing_events, key=lambda item: (item.count, item.event_type)):
                self.timing_event_list.addItem(describe_timing_event(event))
        if hasattr(self, "waveform"):
            self.waveform.update()

    def seek_audio_position(self, position_ms: int) -> None:
        self.set_index, self.current_count = set_count_for_audio_ms(self.project, position_ms)
        self.populate_sets()
        self.sync_timeline()
        if self.player.source().isValid():
            self.player.setPosition(position_ms)
        self.set_count(self.current_count, seek_audio=False)

    def saved_ffmpeg_path(self) -> str:
        value = self.settings.value("ffmpeg_path", "")
        return value if isinstance(value, str) else ""

    def choose_ffmpeg_exe(self) -> None:
        current_path = self.saved_ffmpeg_path()
        start_dir = str(Path(current_path).parent) if current_path else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Locate ffmpeg.exe",
            start_dir,
            "ffmpeg.exe (ffmpeg.exe);;Executable (*.exe);;All Files (*)",
        )
        if path:
            self.settings.setValue("ffmpeg_path", path)
            self.settings.sync()
            self.statusBar().showMessage("ffmpeg.exe saved", 2500)

    def resolve_ffmpeg_path(self) -> str | None:
        saved_path = self.saved_ffmpeg_path()
        if saved_path:
            saved = Path(saved_path)
            if saved.is_file():
                return str(saved)
            if saved.is_dir() and (saved / "ffmpeg.exe").is_file():
                ffmpeg_exe = saved / "ffmpeg.exe"
                self.settings.setValue("ffmpeg_path", str(ffmpeg_exe))
                self.settings.sync()
                return str(ffmpeg_exe)
        discovered = shutil.which("ffmpeg")
        if discovered:
            return discovered
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Locate ffmpeg.exe",
            str(Path.home()),
            "ffmpeg.exe (ffmpeg.exe);;Executable (*.exe);;All Files (*)",
        )
        if path:
            self.settings.setValue("ffmpeg_path", path)
            self.settings.sync()
            return path
        return None

    def set_tool(self, tool: EditorTool) -> None:
        previous_tool = self.field.active_tool
        if self.active_motion_ribbon_id:
            self.active_motion_ribbon_id = ""
            self._motion_ribbon_drag_before_sets = None
            self.field.set_motion_path_editing(False)
        if self.macro_recording and not self.macro_replaying and not self._invoking_command_id:
            command_id = self.tool_command_id(tool)
            if command_id and command_id in self.command_actions:
                self.current_macro_actions.append(
                    {"command_id": command_id, "context": self.macro_context_snapshot()}
                )
        if self.field.active_tool != tool:
            self.preview_center_offset = (0.0, 0.0)
        if tool != EditorTool.PLUGIN_FORM:
            self.active_plugin_form_tool_id = ""
            for button in self.plugin_form_tool_buttons.values():
                button.setChecked(False)
        self.field.set_tool(tool)
        for key, button in self.tool_buttons.items():
            button.setChecked(key == tool)
        for key, button in self.field_hud_buttons.items():
            button.setChecked(key == tool)
        hint = TOOL_HINTS.get(tool, "Adjust the visible tool controls, preview the result, then Apply.")
        if hasattr(self, "tool_hint_label"):
            self.tool_hint_label.setText(hint)
        if hasattr(self, "field_hud_hint"):
            tool_name = tool.value.replace("_", " ").title()
            self.field_hud_hint.setText(tool_name)
            self.field_hud_hint.setToolTip(f"{tool_name}: drag handles · Ctrl+Enter apply · Esc clear")
        if self.tooltips_enabled():
            self.statusBar().showMessage(hint, 3500)
        self.update_tool_edit_visibility()
        self.update_field_hud_visibility()
        _ids, positions = self.selected_positions()
        if tool in (EditorTool.ROTATE, EditorTool.SCALE) and (
            previous_tool != tool or self.preview_transform_pivot is None
        ) and positions:
            self.preview_transform_pivot = selection_center(positions)
        elif tool not in (EditorTool.ROTATE, EditorTool.SCALE):
            self.preview_transform_pivot = None
        if tool == EditorTool.LINE and len(positions) >= 2:
            self.line_endpoints = [positions[0], positions[-1]]
        elif tool == EditorTool.CURVE and len(positions) >= 2:
            self.initialize_curve_tool(positions)
        elif tool == EditorTool.SHAPE_LINE:
            self.initialize_shape_line_anchors(_ids, positions)
        elif tool == EditorTool.MIRROR and positions:
            self.mirror_axis = sum(x for x, _y in positions) / len(positions)
        elif tool == EditorTool.SCALE and positions:
            self.initialize_scale_tool(positions)
        elif tool == EditorTool.WARP and positions:
            self.initialize_warp_tool(positions)
        elif tool == EditorTool.FREE_CURVE and positions:
            self.initialize_free_curve_tool(positions)
        self.update_formation_preview()

    def temporary_tool_requested(self, tool: EditorTool, active: bool, commit: bool) -> None:
        if active:
            self.set_tool(tool)
            self.statusBar().showMessage(
                f"Temporary {tool.value.replace('_', ' ').title()}: drag on-field handles, then release the key",
                2500,
            )
            return
        if commit and self.field.active_tool not in (EditorTool.SELECT, EditorTool.LASSO):
            self.apply_current_preview()
        elif self.field.active_tool != EditorTool.SELECT:
            self.clear_formation_preview()
        self.field.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def direct_edit_field_item(self, kind: str, item_id: str) -> None:
        if kind == "path":
            item = self.field.dot_items.get(item_id)
            if item:
                item.setSelected(True)
            self.selection_changed()
            self.statusBar().showMessage(
                "Path editing active: right-click the yellow path for an anchor; drag red anchors or cyan tangents",
                4500,
            )
            return
        if kind == "prop":
            for dot_item in self.field.dot_items.values():
                dot_item.setSelected(False)
            for prop_id, prop_item in self.field.prop_items.items():
                prop_item.setSelected(prop_id == item_id)
            self.selection_changed()
            self.statusBar().showMessage("Prop selected for direct position, size, and rotation editing", 3000)
            return
        if kind == "preview":
            self.update_tool_edit_visibility()
            self.update_field_hud_visibility()
            self.field.setFocus(Qt.FocusReason.MouseFocusReason)
            self.statusBar().showMessage(
                "Direct formation edit active: drag visible handles; Enter applies and Esc cancels",
                3500,
            )
            return
        if kind == "formation":
            selected_ids = sorted(self.field.selected_dot_ids())
            signature = ",".join(selected_ids)
            key = f"{self.set_index}:{signature}"
            settings = self.workflow_bucket("formation_edit_descriptors").get(key)
            if isinstance(settings, dict):
                self.apply_tool_settings(deepcopy(settings))
                self.statusBar().showMessage(
                    "Formation reopened with its last tool settings; drag handles, then Enter or Esc",
                    4000,
                )
            else:
                self.set_tool(EditorTool.SELECT)
                self.statusBar().showMessage(
                    "Formation has no saved tool recipe; use the on-field transform gizmo and editable pivot",
                    4000,
                )

    def tool_value_text(self, kind: str, x: float, y: float, modifiers: int) -> str:
        shift = bool(modifiers & int(Qt.KeyboardModifier.ShiftModifier.value))
        alt = bool(modifiers & int(Qt.KeyboardModifier.AltModifier.value))
        suffix = ""
        if shift:
            suffix += "  · constrained"
        if alt:
            suffix += "  · symmetric"
        values = {
            "arc_width": f"Arc width  {self.arc_width.value():.2f} yd",
            "arc_height": f"Arc height  {self.arc_height.value():.2f} yd",
            "arc_start": f"Arc start  {self.arc_start_angle.value():.1f}°",
            "arc_end": f"Arc sweep  {self.arc_sweep.value():.1f}°",
            "shape_radius": f"Radius  {self.shape_radius.value():.2f} yd",
            "shape_width": f"Width  {self.shape_width.value():.2f} yd",
            "shape_height": f"Height  {self.shape_height.value():.2f} yd",
            "scale_width": f"Width  {self.scale_width.value():.2f} yd",
            "scale_height": f"Height  {self.scale_height.value():.2f} yd",
            "rotate_angle": f"Rotation  {self.rotation_degrees.value():.1f}°",
            "scatter_radius": f"Spread  {self.scatter_radius.value():.2f} yd",
            "block_spacing": f"Interval  {self.block_spacing.value():.2f} yd",
            "mirror_axis": f"Mirror axis  X {self.mirror_axis:.2f}",
        }
        if kind == "form_center":
            return f"Form center  X {x:.2f}  Y {y:.2f}{suffix}"
        if kind == "transform_pivot":
            return f"Transform pivot  X {x:.2f}  Y {y:.2f}{suffix}"
        if kind.startswith("path_"):
            return f"{kind.replace('_', ' ').title()}  X {x:.2f}  Y {y:.2f}{suffix}"
        if kind.startswith("motion_ribbon_node:"):
            return f"Ribbon node  X {x:.2f}  Y {y:.2f}{suffix}"
        if kind.startswith("motion_ribbon_tangent:"):
            return f"Ribbon tangent  X {x:.2f}  Y {y:.2f}{suffix}"
        return f"{values.get(kind, kind.replace('_', ' ').title() + f'  X {x:.2f}  Y {y:.2f}')}{suffix}"

    def set_form_row_visible(self, widget: QWidget, visible: bool) -> None:
        widget.setVisible(visible)
        label = self.shape_tool_form.labelForField(widget)
        if label:
            label.setVisible(visible)

    def update_tool_edit_visibility(self) -> None:
        tool = self.field.active_tool
        plugin_active = bool(self.active_plugin_form_tool_id)
        self.tool_edit_group.setVisible(tool != EditorTool.SELECT or plugin_active)
        self.plugin_tool_group.setVisible(plugin_active)
        self.line_tool_group.setVisible(tool == EditorTool.LINE)
        self.curve_tool_group.setVisible(tool == EditorTool.CURVE)
        self.free_curve_tool_group.setVisible(tool == EditorTool.FREE_CURVE)
        self.arc_tool_group.setVisible(tool == EditorTool.ARC)
        self.scatter_tool_group.setVisible(tool == EditorTool.SCATTER)
        self.mirror_tool_group.setVisible(tool == EditorTool.MIRROR)
        self.shape_line_tool_group.setVisible(tool == EditorTool.SHAPE_LINE)
        self.svg_tool_group.setVisible(tool == EditorTool.SVG_SHAPE)
        shape_tools = {
            EditorTool.CIRCLE,
            EditorTool.ELLIPSE,
            EditorTool.RECTANGLE,
            EditorTool.TRIANGLE,
            EditorTool.DIAMOND,
            EditorTool.POLYGON,
            EditorTool.STAR,
            EditorTool.SPIRAL,
            EditorTool.BLOCK,
            EditorTool.SVG_SHAPE,
        }
        self.shape_tool_group.setVisible(
            tool in shape_tools
        )
        needs_radius = tool in {EditorTool.CIRCLE, EditorTool.POLYGON, EditorTool.STAR, EditorTool.SPIRAL}
        needs_size = tool in {
            EditorTool.ELLIPSE,
            EditorTool.RECTANGLE,
            EditorTool.TRIANGLE,
            EditorTool.DIAMOND,
            EditorTool.SVG_SHAPE,
        }
        needs_fill = tool in {
            EditorTool.CIRCLE,
            EditorTool.ELLIPSE,
            EditorTool.RECTANGLE,
            EditorTool.TRIANGLE,
            EditorTool.DIAMOND,
            EditorTool.POLYGON,
            EditorTool.STAR,
            EditorTool.SVG_SHAPE,
        }
        self.set_form_row_visible(self.shape_radius, needs_radius)
        self.set_form_row_visible(self.shape_width, needs_size)
        self.set_form_row_visible(self.shape_height, needs_size)
        self.set_form_row_visible(self.shape_fill_mode, needs_fill)
        self.set_form_row_visible(self.polygon_sides, tool == EditorTool.POLYGON)
        self.set_form_row_visible(self.star_points, tool == EditorTool.STAR)
        self.set_form_row_visible(self.star_inner_percent, tool == EditorTool.STAR)
        self.set_form_row_visible(self.spiral_turns, tool == EditorTool.SPIRAL)
        self.set_form_row_visible(self.block_columns, tool == EditorTool.BLOCK)
        self.set_form_row_visible(self.block_spacing, tool == EditorTool.BLOCK)
        self.scale_tool_group.setVisible(tool == EditorTool.SCALE)
        self.warp_tool_group.setVisible(tool == EditorTool.WARP)
        self.rotate_tool_group.setVisible(tool == EditorTool.ROTATE)

    def initialize_scale_tool(self, positions: list[tuple[float, float]]) -> None:
        min_position_x = min(position_x for position_x, _position_y in positions)
        max_position_x = max(position_x for position_x, _position_y in positions)
        min_position_y = min(position_y for _position_x, position_y in positions)
        max_position_y = max(position_y for _position_x, position_y in positions)
        self.scale_width.blockSignals(True)
        self.scale_height.blockSignals(True)
        self.scale_width.setValue(max(0.1, max_position_x - min_position_x))
        self.scale_height.setValue(max(0.1, max_position_y - min_position_y))
        self.scale_width.blockSignals(False)
        self.scale_height.blockSignals(False)

    def reset_curve_handles(self, *_args) -> None:
        _ids, positions = self.selected_positions()
        self.initialize_curve_tool(positions)
        self.update_formation_preview()

    def initialize_curve_tool(self, positions: list[tuple[float, float]]) -> None:
        if len(positions) < 2:
            self.curve_handles = {}
            return
        start = positions[0]
        end = positions[-1]
        delta_x = end[0] - start[0]
        delta_y = end[1] - start[1]
        length = max(0.001, (delta_x * delta_x + delta_y * delta_y) ** 0.5)
        normal_x = -delta_y / length
        normal_y = delta_x / length
        bend = self.curve_bend.value()
        self.curve_handles = {
            "curve_start": start,
            "curve_control_1": (
                start[0] + delta_x / 3 + normal_x * bend,
                start[1] + delta_y / 3 + normal_y * bend,
            ),
            "curve_control_2": (
                start[0] + delta_x * 2 / 3 + normal_x * bend,
                start[1] + delta_y * 2 / 3 + normal_y * bend,
            ),
            "curve_end": end,
        }

    def offset_curve_handles(self, offset_x: float, offset_y: float) -> dict[str, tuple[float, float]]:
        return {
            key: (point[0] + offset_x, point[1] + offset_y)
            for key, point in self.curve_handles.items()
        }

    def curve_on_form_handles(self, offset_x: float, offset_y: float) -> dict[str, tuple[float, float]]:
        handles = self.offset_curve_handles(offset_x, offset_y)
        start = handles["curve_start"]
        control_1 = handles["curve_control_1"]
        control_2 = handles["curve_control_2"]
        end = handles["curve_end"]
        return {
            "curve_start": start,
            "curve_on_1": cubic_bezier_point(start, control_1, control_2, end, 1 / 3),
            "curve_on_2": cubic_bezier_point(start, control_1, control_2, end, 2 / 3),
            "curve_end": end,
        }

    def set_curve_on_form_points(
        self,
        point_1: tuple[float, float],
        point_2: tuple[float, float],
    ) -> None:
        start = self.curve_handles["curve_start"]
        end = self.curve_handles["curve_end"]
        coefficient_11 = 4 / 9
        coefficient_12 = 2 / 9
        coefficient_21 = 2 / 9
        coefficient_22 = 4 / 9
        determinant = coefficient_11 * coefficient_22 - coefficient_12 * coefficient_21
        endpoint_weights = ((8 / 27, 1 / 27), (1 / 27, 8 / 27))
        controls: list[tuple[float, float]] = []
        for coordinate in range(2):
            value_1 = point_1[coordinate] - endpoint_weights[0][0] * start[coordinate] - endpoint_weights[0][1] * end[coordinate]
            value_2 = point_2[coordinate] - endpoint_weights[1][0] * start[coordinate] - endpoint_weights[1][1] * end[coordinate]
            control_1 = (value_1 * coefficient_22 - coefficient_12 * value_2) / determinant
            control_2 = (coefficient_11 * value_2 - coefficient_21 * value_1) / determinant
            controls.append((control_1, control_2))
        self.curve_handles["curve_control_1"] = (controls[0][0], controls[1][0])
        self.curve_handles["curve_control_2"] = (controls[0][1], controls[1][1])

    def arc_point(
        self,
        center_x: float,
        center_y: float,
        angle_degrees: float,
    ) -> tuple[float, float]:
        radius_x = max(0.05, self.arc_width.value() / 2)
        radius_y = max(0.05, self.arc_height.value() / 2)
        angle = pi * angle_degrees / 180
        rotation = pi * self.arc_rotation.value() / 180
        local_x = cos(angle) * radius_x
        local_y = sin(angle) * radius_y
        return (
            center_x + local_x * cos(rotation) - local_y * sin(rotation),
            center_y + local_x * sin(rotation) + local_y * cos(rotation),
        )

    def arc_angle_from_point(self, center_x: float, center_y: float, x: float, y: float) -> float:
        rotation = -pi * self.arc_rotation.value() / 180
        delta_x = x - center_x
        delta_y = y - center_y
        local_x = delta_x * cos(rotation) - delta_y * sin(rotation)
        local_y = delta_x * sin(rotation) + delta_y * cos(rotation)
        return degrees(
            atan2(
                local_y / max(0.05, self.arc_height.value() / 2),
                local_x / max(0.05, self.arc_width.value() / 2),
            )
        )

    @staticmethod
    def signed_angle_delta(start: float, end: float, current_sweep: float) -> float:
        delta = (end - start + 540) % 360 - 180
        if current_sweep < 0 and delta > 0:
            delta -= 360
        elif current_sweep >= 0 and delta < 0:
            delta += 360
        return max(-360, min(360, delta))

    def initialize_warp_tool(self, positions: list[tuple[float, float]]) -> None:
        if len(positions) < 2:
            self.warp_anchors = []
            return
        anchor_count = max(3, int(self.warp_anchor_count.value()))
        min_x = min(position_x for position_x, _position_y in positions)
        max_x = max(position_x for position_x, _position_y in positions)
        center_y = sum(position_y for _position_x, position_y in positions) / len(positions)
        if max_x - min_x <= 0.001:
            min_y = min(position_y for _position_x, position_y in positions)
            max_y = max(position_y for _position_x, position_y in positions)
            center_x = sum(position_x for position_x, _position_y in positions) / len(positions)
            self.warp_anchors = [
                (center_x, min_y + (max_y - min_y) * index / max(1, anchor_count - 1))
                for index in range(anchor_count)
            ]
            return
        self.warp_anchors = [
            (min_x + (max_x - min_x) * index / max(1, anchor_count - 1), center_y)
            for index in range(anchor_count)
        ]

    def reset_warp_anchors(self) -> None:
        _ids, positions = self.selected_positions()
        self.initialize_warp_tool(positions)
        self.update_formation_preview()

    def reset_free_curve_anchors(self, *_args) -> None:
        _ids, positions = self.selected_positions()
        self.initialize_free_curve_tool(positions)
        self.update_formation_preview()

    def initialize_free_curve_tool(self, positions: list[tuple[float, float]]) -> None:
        if len(positions) < 2:
            self.free_curve_anchors = []
            return
        anchor_count = max(3, int(self.free_curve_anchor_count.value()))
        base_path = list(positions)
        if self.free_curve_closed.isChecked() and len(base_path) > 2:
            base_path = [*base_path, base_path[0]]
        self.free_curve_anchors = positions_along_path(base_path, anchor_count)

    def current_set(self) -> DrillSet:
        return self.project.sets[self.set_index]

    def facings_for_set(self, set_index: int | None = None) -> dict[str, float]:
        if not self.project.sets:
            return {}
        target_index = self.set_index if set_index is None else max(0, min(set_index, len(self.project.sets) - 1))
        return {
            dot.id: dot_facing_at_set(self.project, target_index, dot.id)
            for dot in self.project.dots
        }

    def workflow_bucket(self, key: str) -> dict[str, Any]:
        bucket = self.project.workflow.setdefault(key, {})
        if not isinstance(bucket, dict):
            bucket = {}
            self.project.workflow[key] = bucket
        return bucket

    def workflow_list(self, key: str) -> list[Any]:
        values = self.project.workflow.setdefault(key, [])
        if not isinstance(values, list):
            values = []
            self.project.workflow[key] = values
        return values

    def drill_grid_settings(self) -> DrillGridSettings:
        payload = self.project.workflow.get("drill_grid", {})
        return DrillGridSettings.from_json(payload if isinstance(payload, dict) else {})

    def update_drill_grid_settings(self, settings: DrillGridSettings, label: str) -> None:
        before = deepcopy(self.project.workflow)
        after = deepcopy(before)
        after["drill_grid"] = settings.to_json()
        if before == after:
            self.sync_drill_grid_controls()
            return
        self.undo_stack.push(WorkflowMetadataCommand(self, before, after, label))

    def set_drill_grid_enabled(self, enabled: bool) -> None:
        settings = self.drill_grid_settings()
        settings.enabled = bool(enabled)
        self.update_drill_grid_settings(settings, "Toggle Drill Grid")

    def show_drill_grid_dialog(self, *_args) -> None:
        dialog = DrillGridDialog(self.drill_grid_settings(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.sync_drill_grid_controls()
            return
        self.update_drill_grid_settings(dialog.selected_settings(), "Configure Drill Grid")

    def sync_drill_grid_controls(self) -> None:
        settings = self.drill_grid_settings()
        self.field.set_drill_grid(settings)
        toggle_controls = (
            getattr(self, "drill_grid_panel_toggle", None),
            getattr(self, "drill_grid_toolbar_toggle", None),
            getattr(self, "drill_grid_enable_action", None),
        )
        for control in toggle_controls:
            if control is None:
                continue
            control.blockSignals(True)
            control.setChecked(settings.enabled)
            control.blockSignals(False)
        if hasattr(self, "drill_grid_panel_status"):
            self.drill_grid_panel_status.setText(settings.description)
        if hasattr(self, "drill_grid_toolbar_toggle"):
            self.drill_grid_toolbar_toggle.setText(
                f"Grid {settings.preset_label}" if settings.enabled else "Grid Off"
            )
        if hasattr(self, "drill_grid_toolbar_configure"):
            self.drill_grid_toolbar_configure.setText(f"{settings.preset_label} Settings...")

    def load_global_library(self, key: str) -> dict[str, Any]:
        raw = self.settings.value(f"workflow/{key}", "{}")
        if not raw:
            return {}
        try:
            values = json.loads(str(raw))
        except json.JSONDecodeError:
            return {}
        return values if isinstance(values, dict) else {}

    def save_global_library(self, key: str, values: dict[str, Any]) -> None:
        self.settings.setValue(f"workflow/{key}", json.dumps(values, indent=2, sort_keys=True))
        self.settings.sync()

    def open_project_tab(self) -> None:
        handler = getattr(self.window(), "open_project_tab_dialog", None)
        if callable(handler):
            handler()

    def copy_from_project_tab(self) -> None:
        handler = getattr(self.window(), "copy_from_project_tab_dialog", None)
        if callable(handler):
            handler(self)

    def transfer_from_project(
        self,
        source_project: DrillProject,
        source_project_dir: Path,
        source_set_index: int,
        destination_set_index: int,
        *,
        formation: bool,
        timing_map: bool,
        props: bool,
    ) -> dict[str, int]:
        before = deepcopy(self.project)
        previous_prop_count = len(self.project.props)
        counts = transfer_project_content(
            source_project,
            self.project,
            source_set_index,
            destination_set_index,
            formation=formation,
            timing_map=timing_map,
            props=props,
        )
        if props and counts["props"]:
            destination_props_dir = self.project_dir / "props"
            destination_props_dir.mkdir(parents=True, exist_ok=True)
            transferred_props = self.project.props[previous_prop_count:]
            for source_prop, destination_prop in zip(source_project.props, transferred_props):
                source_path = Path(source_prop.image_file)
                if not source_path.is_absolute():
                    source_path = source_project_dir / source_path
                if not source_path.exists() or not source_prop.image_file:
                    continue
                destination_path = destination_props_dir / source_path.name
                suffix = 2
                while destination_path.exists() and destination_path.resolve() != source_path.resolve():
                    destination_path = destination_props_dir / f"{source_path.stem}_{suffix}{source_path.suffix}"
                    suffix += 1
                if source_path.resolve() != destination_path.resolve():
                    shutil.copy2(source_path, destination_path)
                destination_prop.image_file = str(destination_path.relative_to(self.project_dir))
        after = deepcopy(self.project)
        self.apply_project_snapshot(before)
        self.undo_stack.push(ProjectSnapshotCommand(self, before, after, "Copy From Project Tab"))
        return counts

    def apply_project_snapshot(self, project: DrillProject) -> None:
        self.project = deepcopy(project)
        self.project.ensure_set_positions()
        self.set_index = max(0, min(self.set_index, len(self.project.sets) - 1))
        self.current_count = max(
            self.current_set().start_count,
            min(self.current_count, self.current_set().end_count),
        )
        self.field.clear_preview()
        self.field.clear_paths()
        self.field.set_project(self.project, self.project_dir)
        self.sync_drill_grid_controls()
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=False)
        self.refresh_marcher_table()
        self.refresh_prop_table()
        self.refresh_visibility_filters()
        self.refresh_selection_sets()
        self.refresh_appearance_groups()
        self.refresh_constraints()
        self.refresh_timing_events()
        self.refresh_music_design_panel()
        self.refresh_specialized_design()
        self.refresh_selected_paths()
        self.apply_locks_to_field()
        self.selection_changed()
        self.schedule_live_conflict_analysis()

    def refresh_music_design_panel(self) -> None:
        if hasattr(self, "music_design_panel"):
            self.music_design_panel.set_project(self.project)

    def refresh_specialized_design(self) -> None:
        if hasattr(self, "specialized_design_panel"):
            self.specialized_design_panel.set_project(self.project)
        if hasattr(self, "choreography_timeline"):
            self.choreography_timeline.set_project(self.project)
            self.choreography_timeline.set_current_count(self.current_count)

    def select_dot_ids(self, dot_ids: list[str], center: bool = False) -> None:
        selected = set(dot_ids)
        for dot_id, item in self.field.dot_items.items():
            item.setSelected(dot_id in selected)
        for item in self.field.prop_items.values():
            item.setSelected(False)
        if center and selected:
            first_id = next((dot_id for dot_id in dot_ids if dot_id in self.field.dot_items), "")
            if first_id:
                self.field.centerOn(self.field.dot_items[first_id])
        self.selection_changed()

    def import_roster_csv(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import Roster CSV",
            str(self.project_dir),
            "Roster CSV (*.csv);;All Files (*.*)",
        )
        if not filename:
            return
        try:
            dialog = RosterImportDialog(Path(filename), [dot.id for dot in self.project.dots], self)
        except Exception as exc:
            QMessageBox.warning(self, "Roster Import Failed", str(exc))
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before_dots = deepcopy(self.project.dots)
        before_sets = deepcopy(self.project.sets)
        before_constraints = deepcopy(self.project.constraints)
        before_workflow = deepcopy(self.project.workflow)
        selected_ids = self.field.selected_dot_ids()
        result = dialog.selected_result()
        updated, added = merge_roster(self.project, result.dots, mode="merge")
        if not large_show_workflow_records(self.project, "hierarchical_groups"):
            generate_hierarchical_groups(self.project)
        after_dots = deepcopy(self.project.dots)
        after_sets = deepcopy(self.project.sets)
        after_constraints = deepcopy(self.project.constraints)
        after_workflow = deepcopy(self.project.workflow)
        self.apply_workflow_state(
            before_dots,
            before_sets,
            before_constraints,
            selected_ids,
            before_workflow,
        )
        self.undo_stack.push(
            WorkflowStateCommand(
                self,
                before_dots,
                after_dots,
                before_sets,
                after_sets,
                before_constraints,
                after_constraints,
                selected_ids,
                "Import Roster CSV",
                before_workflow,
                after_workflow,
            )
        )
        self.statusBar().showMessage(f"Roster imported: {added} added, {updated} updated", 3500)

    def show_group_manager(self) -> None:
        before = deepcopy(self.project.workflow)
        dialog = GroupManagerDialog(self.project, self.field.selected_dot_ids, self)
        dialog.select_requested.connect(lambda ids: self.select_dot_ids(list(ids)))
        dialog.transform_requested.connect(self.transform_group)
        dialog.project_changed.connect(self.group_workflow_changed)
        dialog.exec()
        after = deepcopy(self.project.workflow)
        if before != after:
            self.undo_stack.push(WorkflowMetadataCommand(self, before, after, "Edit Group Hierarchy"))

    def group_workflow_changed(self) -> None:
        self.apply_locks_to_field()
        self.refresh_visibility_filters()
        self.statusBar().showMessage("Group hierarchy updated", 1600)

    def transform_group(self, dot_ids: list[str], parameters: TransformParameters) -> None:
        self.select_dot_ids(list(dot_ids))
        self.apply_transform_to_selected(parameters, "Transform Group")

    def replace_or_swap_performer(self) -> None:
        selected_ids = self.ordered_dot_ids(self.field.selected_dot_ids())
        if len(selected_ids) == 2:
            answer = QMessageBox.question(
                self,
                "Swap Performers",
                f"Swap the roster identities assigned to {selected_ids[0]} and {selected_ids[1]}?\n\n"
                "Their drill spots, coordinates, paths, timing, and facings will not move.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            first = self.project.dot_by_id(selected_ids[0])
            second = self.project.dot_by_id(selected_ids[1])
            if not first or not second:
                return
            before = {dot_id: self.dot_appearance_fields(self.project.dot_by_id(dot_id)) for dot_id in selected_ids}
            swap_performers(first, second)
            after = {dot_id: self.dot_appearance_fields(self.project.dot_by_id(dot_id)) for dot_id in selected_ids}
            self.apply_dot_appearance(before)
            self.undo_stack.push(DotAppearanceCommand(self, before, after, "Swap Performers"))
            return
        if len(selected_ids) != 1:
            QMessageBox.information(
                self,
                "Replace / Swap Performer",
                "Select one marcher to replace their roster identity, or exactly two marchers to swap them.",
            )
            return
        dot = self.project.dot_by_id(selected_ids[0])
        if not dot:
            return
        dialog = PerformerReplacementDialog(dot, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before = {dot.id: self.dot_appearance_fields(dot)}
        after = {dot.id: dialog.fields()}
        self.undo_stack.push(DotAppearanceCommand(self, before, after, "Replace Performer"))

    def automatic_form_cleanup(self) -> None:
        selected_ids = self.ordered_dot_ids(self.field.selected_dot_ids())
        if len(selected_ids) < 2:
            QMessageBox.information(self, "Automatic Form Cleanup", "Select at least two marchers first.")
            return
        dialog = CleanupDialog(len(selected_ids), self)
        if hasattr(self, "min_spacing"):
            dialog.minimum_spacing.setValue(self.min_spacing.value())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source = {
            dot_id: self.current_set().dot_positions[dot_id]
            for dot_id in selected_ids
            if dot_id in self.current_set().dot_positions and not self.is_dot_locked(dot_id)
        }
        targets, report = cleanup_formation(source, dialog.options())
        if not report.moved:
            self.statusBar().showMessage("Formation already satisfies the selected cleanup rules", 2600)
            return
        self.field.show_preview(source, targets)
        answer = QMessageBox.question(
            self,
            "Apply Form Cleanup?",
            f"Previewing {report.moved} adjusted marchers.\n\n"
            f"Overlaps: {report.overlaps_before} → {report.overlaps_after}\n"
            f"Average interval: {report.average_interval_before:.2f} → {report.average_interval_after:.2f} yd\n\n"
            "Apply this cleanup?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.apply_positions(targets)
            self.statusBar().showMessage(f"Cleaned {report.moved} marcher positions", 3000)
        else:
            self.field.clear_preview()

    def show_set_comparison(self) -> None:
        if len(self.project.sets) < 2:
            QMessageBox.information(self, "Compare Sets", "Add at least two sets first.")
            return
        dialog = SetComparisonDialog(self.project, self.project_dir, self)
        dialog.select_requested.connect(lambda ids: self.select_dot_ids(list(ids)))
        dialog.exec()

    def show_formation_variations(self) -> None:
        before_workflow = deepcopy(self.project.workflow)
        dialog = FormationVariationsDialog(
            self.project,
            self.set_index,
            self.ordered_dot_ids(self.field.selected_dot_ids()),
            self,
        )
        dialog.apply_requested.connect(self.apply_formation_variation)
        dialog.exec()
        after_workflow = deepcopy(self.project.workflow)
        if before_workflow != after_workflow:
            self.undo_stack.push(
                WorkflowMetadataCommand(self, before_workflow, after_workflow, "Edit Formation Variations")
            )

    def apply_formation_variation(self, record: dict[str, Any]) -> None:
        positions = variation_positions(record)
        if not positions:
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        drill_set = self.current_set()
        drill_set.dot_positions.update(self.editable_positions(positions))
        selected = set(positions)
        for dot_id in selected:
            drill_set.dot_facings.pop(dot_id, None)
            drill_set.count_facings.pop(dot_id, None)
            drill_set.path_anchors.pop(dot_id, None)
            drill_set.path_controls.pop(dot_id, None)
            drill_set.count_positions.pop(dot_id, None)
            drill_set.move_timings.pop(dot_id, None)
            drill_set.movement_styles.pop(dot_id, None)
        drill_set.dot_facings.update(
            {str(dot_id): float(value) for dot_id, value in dict(record.get("dot_facings", {})).items() if dot_id in selected}
        )
        drill_set.count_facings.update(
            {
                str(dot_id): {float(count): float(facing) for count, facing in dict(keyframes).items()}
                for dot_id, keyframes in dict(record.get("count_facings", {})).items()
                if dot_id in selected and isinstance(keyframes, dict)
            }
        )
        drill_set.count_positions.update(
            {
                str(dot_id): {
                    float(count): (float(position[0]), float(position[1]))
                    for count, position in dict(keyframes).items()
                    if isinstance(position, (list, tuple)) and len(position) >= 2
                }
                for dot_id, keyframes in dict(record.get("count_positions", {})).items()
                if dot_id in selected and isinstance(keyframes, dict)
            }
        )
        drill_set.path_anchors.update(
            {
                str(dot_id): [(float(point[0]), float(point[1])) for point in anchors]
                for dot_id, anchors in dict(record.get("path_anchors", {})).items()
                if dot_id in selected
            }
        )
        drill_set.path_controls.update(deepcopy(dict(record.get("path_controls", {}))))
        drill_set.move_timings.update(deepcopy(dict(record.get("move_timings", {}))))
        for dot_id, style in dict(record.get("movement_styles", {})).items():
            if dot_id in selected and str(style) in MovementStyle._value2member_map_:
                drill_set.movement_styles[str(dot_id)] = MovementStyle(str(style))
        self.set_count(self.current_count, seek_audio=False)
        self.push_set_snapshot(before_sets, before_index, before_count, "Apply Formation Variation")
        self.statusBar().showMessage(f"Applied variation '{record.get('name', 'Variation')}'", 2800)

    def selected_set_indices_for_edit(
        self,
        dot_ids: list[str] | None = None,
        base_index: int | None = None,
    ) -> list[int]:
        scope = "current"
        if hasattr(self, "edit_scope_combo"):
            scope = str(self.edit_scope_combo.currentData() or "current")
        return ripple_set_indices(
            self.project,
            self.set_index if base_index is None else base_index,
            scope,
            dot_ids or self.field.selected_dot_ids(),
            self.multi_set_start.value() if hasattr(self, "multi_set_start") else None,
            self.multi_set_end.value() if hasattr(self, "multi_set_end") else None,
        ) or [self.set_index]

    def ordered_dot_ids(self, dot_ids: list[str]) -> list[str]:
        selected = set(dot_ids)
        return [dot.id for dot in self.project.dots if dot.id in selected]

    def remember_repeat_action(self, payload: dict[str, Any]) -> None:
        if getattr(self, "_repeating_last_action", False):
            return
        self.last_repeat_action = deepcopy(payload)

    def remember_transform_action(
        self,
        parameters: TransformParameters,
        source_positions: dict[str, tuple[float, float]],
        label: str,
    ) -> None:
        center = selection_center(source_positions.values())
        pivot = parameters.pivot or center
        self.remember_repeat_action(
            {
                "type": "transform",
                "label": label,
                "parameters": {
                    "offset_x": parameters.offset_x,
                    "offset_y": parameters.offset_y,
                    "rotation_degrees": parameters.rotation_degrees,
                    "scale_x": parameters.scale_x,
                    "scale_y": parameters.scale_y,
                    "skew_x_degrees": parameters.skew_x_degrees,
                    "skew_y_degrees": parameters.skew_y_degrees,
                    "pivot_offset": (pivot[0] - center[0], pivot[1] - center[1]),
                },
            }
        )

    def repeat_last_action(self) -> None:
        payload = deepcopy(self.last_repeat_action)
        if not payload:
            self.statusBar().showMessage("No repeatable edit yet", 2200)
            return
        self._repeating_last_action = True
        try:
            action_type = str(payload.get("type", ""))
            if action_type == "transform":
                ids, positions = self.selected_positions()
                if not ids:
                    return
                values = dict(payload.get("parameters", {}))
                center = selection_center(positions)
                pivot_offset = values.pop("pivot_offset", (0.0, 0.0))
                pivot = (center[0] + float(pivot_offset[0]), center[1] + float(pivot_offset[1]))
                parameters = TransformParameters(pivot=pivot, **values)
                self.apply_transform_to_selected(parameters, f"Repeat {payload.get('label', 'Transform')}", remember=False)
            elif action_type == "formation":
                settings = payload.get("settings", {})
                if isinstance(settings, dict):
                    self.apply_tool_settings(settings)
                    self.apply_formation(self.field.active_tool)
            elif action_type == "metadata":
                fields = dict(payload.get("fields", {}))
                ids = self.field.selected_dot_ids()
                updates = {dot_id: fields for dot_id in ids}
                if updates:
                    before = {
                        dot_id: self.dot_appearance_fields(self.project.dot_by_id(dot_id))
                        for dot_id in ids
                        if self.project.dot_by_id(dot_id)
                    }
                    self.undo_stack.push(DotAppearanceCommand(self, before, updates, "Repeat Metadata Edit"))
            elif action_type == "set":
                if payload.get("action") == "add":
                    self.add_set(remember=False)
                elif payload.get("action") == "copy":
                    self.copy_set(remember=False)
            elif action_type == "property_brush":
                self.paint_property_brush()
        finally:
            self._repeating_last_action = False

    def apply_transform_to_selected(
        self,
        parameters: TransformParameters,
        label: str,
        *,
        remember: bool = True,
    ) -> None:
        ids, positions = self.selected_positions()
        source = dict(zip(ids, positions))
        source = self.editable_positions(source)
        if not source:
            return
        transformed = transform_positions(source, parameters)
        after = self.current_positions()
        after.update(transformed)
        self.apply_positions(after)
        pivot = parameters.pivot or selection_center(source.values())
        self.field.set_transform_pivot(
            (pivot[0] + parameters.offset_x, pivot[1] + parameters.offset_y)
        )
        if remember:
            self.remember_transform_action(parameters, source, label)
        self.statusBar().showMessage(f"{label} applied to {len(source)} marcher(s)", 1800)

    def apply_gizmo_transform(
        self,
        before: dict[str, tuple[float, float]],
        after_selected: dict[str, tuple[float, float]],
        descriptor: dict[str, Any],
    ) -> None:
        editable_after = self.editable_positions(after_selected)
        if not editable_after:
            self.set_count(self.current_count, seek_audio=False)
            return
        after = self.current_positions()
        after.update(editable_after)
        self.apply_positions(after)
        pivot_value = descriptor.get("pivot")
        pivot = tuple(pivot_value) if isinstance(pivot_value, (list, tuple)) and len(pivot_value) >= 2 else None
        parameters = TransformParameters(
            offset_x=float(descriptor.get("offset_x", 0.0)),
            offset_y=float(descriptor.get("offset_y", 0.0)),
            rotation_degrees=float(descriptor.get("rotation_degrees", 0.0)),
            scale_x=float(descriptor.get("scale_x", 1.0)),
            scale_y=float(descriptor.get("scale_y", 1.0)),
            skew_x_degrees=float(descriptor.get("skew_x_degrees", 0.0)),
            skew_y_degrees=float(descriptor.get("skew_y_degrees", 0.0)),
            pivot=pivot,
        )
        self.remember_transform_action(parameters, before, str(descriptor.get("kind", "Transform")).replace("_", " ").title())

    def precision_nudge_selected(self, delta_x: float, delta_y: float, step_label: str) -> None:
        parameters = TransformParameters(offset_x=delta_x, offset_y=delta_y)
        self.apply_transform_to_selected(parameters, f"Nudge {step_label}")

    def center_numeric_transform_pivot(self) -> None:
        _ids, positions = self.selected_positions()
        if not positions:
            return
        center_x, center_y = selection_center(positions)
        self.transform_pivot_x.setValue(center_x)
        self.transform_pivot_y.setValue(center_y)
        self.transform_custom_pivot.setChecked(True)

    def numeric_transform_parameters(self) -> TransformParameters:
        pivot = None
        if self.transform_custom_pivot.isChecked():
            pivot = (self.transform_pivot_x.value(), self.transform_pivot_y.value())
        return TransformParameters(
            offset_x=self.transform_offset_x.value(),
            offset_y=self.transform_offset_y.value(),
            rotation_degrees=self.transform_rotation.value(),
            scale_x=self.transform_scale_x.value(),
            scale_y=self.transform_scale_y.value(),
            skew_x_degrees=self.transform_skew_x.value(),
            skew_y_degrees=self.transform_skew_y.value(),
            pivot=pivot,
        )

    def apply_numeric_transform(self) -> None:
        self.apply_transform_to_selected(self.numeric_transform_parameters(), "Numeric Transform")

    def reset_numeric_transform(self) -> None:
        self.transform_offset_x.setValue(0)
        self.transform_offset_y.setValue(0)
        self.transform_rotation.setValue(0)
        self.transform_scale_x.setValue(1)
        self.transform_scale_y.setValue(1)
        self.transform_skew_x.setValue(0)
        self.transform_skew_y.setValue(0)
        self.transform_custom_pivot.setChecked(False)

    def apply_assignment_candidate(self, positions: dict[str, tuple[float, float]], label: str) -> None:
        positions = self.editable_positions(positions)
        if not positions:
            return
        before = self.current_positions()
        after = dict(before)
        after.update(positions)
        before_anchors = self.clone_path_anchors(self.set_index)
        before_controls = self.clone_path_controls(self.set_index)
        before_counts = self.clone_count_positions(self.set_index)
        after_anchors = self.clone_path_anchors(self.set_index)
        after_controls = self.clone_path_controls(self.set_index)
        after_counts = self.clone_count_positions(self.set_index)
        for dot_id in positions:
            after_anchors.pop(dot_id, None)
            after_controls.pop(dot_id, None)
            after_counts.pop(dot_id, None)
        self.undo_stack.push(
            MoveDotsCommand(
                self,
                self.set_index,
                before,
                after,
                label,
                before_anchors,
                after_anchors,
                before_controls,
                after_controls,
                before_counts,
                after_counts,
            )
        )
        self.refresh_selected_paths()

    def show_smart_transition_composer(self) -> None:
        ids = self.ordered_dot_ids(self.field.selected_dot_ids())
        if len(ids) < 2:
            QMessageBox.information(self, "Guided Destination Repair", "Select at least two marchers whose destination slots should be reassigned.")
            return
        targets = [self.current_set().dot_positions[dot_id] for dot_id in ids]
        candidates = transition_candidates(self.project, self.set_index, ids, targets)
        if not candidates:
            return
        starts_source = self.current_transition_start_positions()
        starts = {dot_id: starts_source.get(dot_id, self.current_set().dot_positions[dot_id]) for dot_id in ids}

        def preview(candidate) -> None:
            self.field.show_preview(starts, candidate.positions)

        dialog = SmartTransitionDialog(candidates, preview, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        candidate = dialog.selected_candidate()
        self.field.clear_preview()
        if accepted and candidate:
            self.apply_assignment_candidate(candidate.positions, f"Transition: {candidate.label}")
            self.statusBar().showMessage(
                f"Applied {candidate.label}: {candidate.changed_marchers} owner change(s), "
                f"{candidate.score.spacing_conflicts} spacing conflict(s), {candidate.score.crossings} crossing(s)",
                3200,
            )
        else:
            self.set_count(self.current_count, seek_audio=False)

    def apply_section_aware_form_fit(self) -> None:
        ids = self.ordered_dot_ids(self.field.selected_dot_ids())
        if len(ids) < 2:
            return
        targets = [self.current_set().dot_positions[dot_id] for dot_id in ids]
        positions = assignment_for_mode(self.project, self.set_index, ids, targets, "section")
        self.apply_assignment_candidate(positions, "Section-Aware Form Fit")

    def dot_appearance_fields(self, dot: Dot | None) -> dict[str, str]:
        if dot is None:
            return {}
        return {
            "color": dot.color,
            "name": dot.name,
            "section": dot.section,
            "instrument": dot.instrument,
            "rank": dot.rank,
            "equipment": dot.equipment,
            "layer": dot.layer,
        }

    def copy_property_brush(self) -> None:
        source_ids = self.ordered_dot_ids(self.field.selected_dot_ids())
        if not source_ids:
            QMessageBox.information(self, "Property Paintbrush", "Select the source marcher or form first.")
            return
        dialog = PropertyBrushDialog(self.property_brush_properties, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        properties = dialog.selected_properties()
        if not properties:
            return
        self.property_brush_properties = properties
        drill_set = self.current_set()
        source_positions = {dot_id: drill_set.dot_positions[dot_id] for dot_id in source_ids}
        center = selection_center(source_positions.values())
        per_dot: dict[str, dict[str, Any]] = {}
        for dot_id in source_ids:
            dot = self.project.dot_by_id(dot_id)
            per_dot[dot_id] = {
                "position": source_positions[dot_id],
                "relative_position": (
                    source_positions[dot_id][0] - center[0],
                    source_positions[dot_id][1] - center[1],
                ),
                "path_anchors": deepcopy(drill_set.path_anchors.get(dot_id, [])),
                "path_controls": deepcopy(drill_set.path_controls.get(dot_id, [])),
                "facing": drill_set.dot_facings.get(dot_id),
                "movement_style": drill_set.movement_styles.get(dot_id, MovementStyle.NORMAL).value,
                "timing": deepcopy(drill_set.move_timings.get(dot_id)),
                "appearance": self.dot_appearance_fields(dot),
            }
        source_set = set(source_ids)
        constraints = [
            deepcopy(constraint)
            for constraint in self.project.constraints
            if set(constraint.dot_ids).issubset(source_set)
        ]
        self.property_brush_payload = {
            "source_ids": source_ids,
            "properties": sorted(properties),
            "per_dot": per_dot,
            "constraints": constraints,
            "source_set_start": drill_set.start_count,
            "source_set_end": drill_set.end_count,
        }
        self.statusBar().showMessage(f"Property brush copied from {len(source_ids)} marcher(s). Select targets and press Ctrl+Shift+V.", 3500)

    def paint_property_brush(self) -> None:
        payload = self.property_brush_payload
        target_ids = self.ordered_dot_ids(self.field.selected_dot_ids())
        if not payload:
            QMessageBox.information(self, "Property Paintbrush", "Copy properties from a source marcher or form first.")
            return
        source_ids = list(payload.get("source_ids", []))
        if not target_ids:
            QMessageBox.information(self, "Property Paintbrush", "Select one or more target marchers first.")
            return
        if len(source_ids) != len(target_ids) and len(source_ids) != 1:
            QMessageBox.warning(self, "Property Paintbrush", "Select the same number of targets as source marchers, or copy from one marcher to many targets.")
            return
        mapping = {
            target_id: source_ids[index] if len(source_ids) > 1 else source_ids[0]
            for index, target_id in enumerate(target_ids)
        }
        properties = set(str(value) for value in payload.get("properties", []))
        per_dot = dict(payload.get("per_dot", {}))
        before_dots = deepcopy(self.project.dots)
        before_sets = deepcopy(self.project.sets)
        before_constraints = deepcopy(self.project.constraints)

        for set_index in self.selected_set_indices_for_edit(target_ids):
            drill_set = self.project.sets[set_index]
            target_center = selection_center(
                drill_set.dot_positions[target_id]
                for target_id in target_ids
                if target_id in drill_set.dot_positions
            )
            for target_id, source_id in mapping.items():
                source_data = dict(per_dot.get(source_id, {}))
                old_target_position = drill_set.dot_positions.get(target_id, (0.0, 0.0))
                source_position = tuple(source_data.get("position", (0.0, 0.0)))
                if "position" in properties:
                    if len(source_ids) == len(target_ids) and len(source_ids) > 1:
                        relative = tuple(source_data.get("relative_position", (0.0, 0.0)))
                        drill_set.dot_positions[target_id] = (target_center[0] + relative[0], target_center[1] + relative[1])
                    elif len(target_ids) == 1:
                        drill_set.dot_positions[target_id] = source_position
                if "path" in properties:
                    delta_x = old_target_position[0] - source_position[0]
                    delta_y = old_target_position[1] - source_position[1]
                    anchors = [
                        (float(point[0]) + delta_x, float(point[1]) + delta_y)
                        for point in source_data.get("path_anchors", [])
                    ]
                    if anchors:
                        drill_set.path_anchors[target_id] = anchors
                    else:
                        drill_set.path_anchors.pop(target_id, None)
                    controls = []
                    for control_set in source_data.get("path_controls", []):
                        controls.append(
                            {
                                name: (float(point[0]) + delta_x, float(point[1]) + delta_y)
                                for name, point in control_set.items()
                            }
                        )
                    if controls:
                        drill_set.path_controls[target_id] = controls
                    else:
                        drill_set.path_controls.pop(target_id, None)
                if "facing" in properties:
                    drill_set.count_facings.pop(target_id, None)
                    facing = source_data.get("facing")
                    if facing is None:
                        drill_set.dot_facings.pop(target_id, None)
                    else:
                        drill_set.dot_facings[target_id] = float(facing)
                if "movement_style" in properties:
                    style_value = str(source_data.get("movement_style", MovementStyle.NORMAL.value))
                    style = MovementStyle(style_value) if style_value in MovementStyle._value2member_map_ else MovementStyle.NORMAL
                    if style == MovementStyle.NORMAL:
                        drill_set.movement_styles.pop(target_id, None)
                    else:
                        drill_set.movement_styles[target_id] = style
                if "timing" in properties:
                    timing = source_data.get("timing")
                    if isinstance(timing, dict):
                        source_start = float(payload.get("source_set_start", self.current_set().start_count))
                        source_end = float(payload.get("source_set_end", self.current_set().end_count))
                        source_span = max(1.0, source_end - source_start)
                        start_progress = (float(timing.get("start", source_start)) - source_start) / source_span
                        end_progress = (float(timing.get("end", source_end)) - source_start) / source_span
                        target_span = max(1.0, drill_set.end_count - drill_set.start_count)
                        drill_set.move_timings[target_id] = self.normalized_move_timing(
                            drill_set,
                            drill_set.start_count + start_progress * target_span,
                            drill_set.start_count + end_progress * target_span,
                        )
                    else:
                        drill_set.move_timings.pop(target_id, None)

        if "appearance" in properties:
            for target_id, source_id in mapping.items():
                dot = self.project.dot_by_id(target_id)
                appearance = dict(per_dot.get(source_id, {}).get("appearance", {}))
                if dot:
                    for field_name in ("color", "section", "instrument", "rank", "equipment", "layer"):
                        if field_name in appearance:
                            setattr(dot, field_name, str(appearance[field_name]))
        if "constraints" in properties:
            target_set = set(target_ids)
            self.project.constraints = [
                constraint
                for constraint in self.project.constraints
                if not set(constraint.dot_ids).issubset(target_set)
            ]
            for source_constraint in payload.get("constraints", []):
                if not isinstance(source_constraint, DotConstraint):
                    continue
                mapped_ids = [
                    target_id
                    for source_id in source_constraint.dot_ids
                    for target_id, mapped_source in mapping.items()
                    if mapped_source == source_id
                ]
                if len(mapped_ids) < 2:
                    continue
                metadata: dict[str, Any] = {}
                if source_constraint.constraint_type == "pivot":
                    metadata = make_relative_metadata(mapped_ids, self.current_positions(), pivot_id=mapped_ids[0])
                elif source_constraint.constraint_type == "arc":
                    metadata = make_arc_metadata(mapped_ids, self.current_positions())
                elif source_constraint.constraint_type == "block":
                    metadata = make_block_metadata(mapped_ids, self.current_positions(), source_constraint.spacing)
                self.project.constraints.append(
                    DotConstraint(
                        name=f"{source_constraint.name} Copy",
                        constraint_type=source_constraint.constraint_type,
                        dot_ids=mapped_ids,
                        spacing=source_constraint.spacing,
                        metadata=metadata,
                    )
                )

        after_dots = deepcopy(self.project.dots)
        after_sets = deepcopy(self.project.sets)
        after_constraints = deepcopy(self.project.constraints)
        self.apply_workflow_state(before_dots, before_sets, before_constraints, target_ids)
        self.undo_stack.push(
            WorkflowStateCommand(
                self,
                before_dots,
                after_dots,
                before_sets,
                after_sets,
                before_constraints,
                after_constraints,
                target_ids,
                "Paint Properties",
            )
        )
        self.remember_repeat_action({"type": "property_brush", "label": "Paint Properties"})
        self.statusBar().showMessage(f"Painted {', '.join(sorted(properties))} onto {len(target_ids)} marcher(s)", 3200)

    def show_music_design_studio(self, initial_tab: str = "score") -> None:
        before = deepcopy(self.project)
        dialog = MusicDesignStudioDialog(self.project, self.project_dir, initial_tab, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        after = deepcopy(dialog.project)
        score = after.imported_score
        if score and score.source_file:
            source = Path(score.source_file)
            if not source.is_absolute():
                source = self.project_dir / source
            if source.is_file():
                score_dir = self.project_dir / "score"
                score_dir.mkdir(exist_ok=True)
                try:
                    relative = source.resolve().relative_to(self.project_dir.resolve())
                    score.source_file = str(relative)
                except ValueError:
                    destination = score_dir / source.name
                    suffix = 2
                    while destination.exists() and destination.read_bytes() != source.read_bytes():
                        destination = score_dir / f"{source.stem}_{suffix}{source.suffix}"
                        suffix += 1
                    if not destination.exists():
                        shutil.copy2(source, destination)
                    score.source_file = str(destination.relative_to(self.project_dir))
        if before == after:
            return
        self.apply_project_snapshot(before)
        self.undo_stack.push(ProjectSnapshotCommand(self, before, after, "Edit Music & Show Design"))
        self.statusBar().showMessage(
            f"Music design updated: {len(after.music_phrases)} phrase(s), {len(after.storyboard)} scene(s)",
            3500,
        )

    def show_specialized_design_studio(self, initial_tab: str = "surface") -> None:
        before = deepcopy(self.project)
        dialog = SpecializedDesignStudioDialog(
            self.project,
            self.field.selected_dot_ids(),
            self.field.selected_prop_ids(),
            self.set_index,
            initial_tab,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        after = deepcopy(dialog.project)
        if before == after:
            return
        self.apply_project_snapshot(before)
        self.undo_stack.push(ProjectSnapshotCommand(self, before, after, "Edit Specialized Design"))
        self.statusBar().showMessage(
            f"Specialized design updated: {after.surface.name}, {len(after.choreography)} choreography event(s), {len(after.prop_attachments)} prop link(s)",
            4000,
        )

    def show_beat_set_generator(self) -> None:
        if not self.project.markers:
            QMessageBox.information(self, "Beat-to-Set Generator", "Add or detect musical markers first.")
            return
        selected_rows = {index.row() for index in self.marker_table.selectionModel().selectedRows()} if hasattr(self, "marker_table") else set()
        dialog = BeatSetGeneratorDialog(self.project.markers, selected_rows, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        markers = dialog.selected_markers()
        if not markers:
            QMessageBox.warning(self, "Beat-to-Set Generator", "Select at least one marker.")
            return
        if not dialog.replace_sets.isChecked():
            existing_boundaries = [Marker(float(drill_set.start_count), drill_set.name) for drill_set in self.project.sets]
            markers = existing_boundaries + markers
        generated = generate_sets_from_markers(self.project, markers)
        if not generated:
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        self.project.sets = generated
        self.project.ensure_set_positions()
        self.set_index = 0
        self.current_count = generated[0].start_count
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=True)
        self.push_set_snapshot(before_sets, before_index, before_count, "Generate Sets From Musical Markers")
        self.statusBar().showMessage(f"Generated {len(generated)} sets from musical markers", 3000)

    def locked_sections(self) -> set[str]:
        return set(str(value) for value in self.workflow_list("locked_sections") if value)

    def locked_layers(self) -> set[str]:
        return set(str(value) for value in self.workflow_list("locked_layers") if value)

    def is_dot_locked(self, dot_id: str) -> bool:
        dot = self.project.dot_by_id(dot_id)
        if not dot:
            return False
        return (
            dot_id in locked_group_dot_ids(self.project)
            or bool(dot.section and dot.section in self.locked_sections())
            or bool(dot.layer and dot.layer in self.locked_layers())
        )

    def editable_positions(self, positions: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
        return {dot_id: position for dot_id, position in positions.items() if not self.is_dot_locked(dot_id)}

    def apply_locks_to_field(self) -> None:
        if hasattr(self.field, "set_locked_filters"):
            self.field.set_locked_filters(self.locked_sections(), self.locked_layers(), locked_group_dot_ids(self.project))
        if hasattr(self, "lock_status_label"):
            sections = sorted(self.locked_sections())
            layers = sorted(self.locked_layers())
            group_count = sum(
                bool(group.get("locked", False))
                for group in large_show_workflow_records(self.project, "hierarchical_groups")
            )
            parts: list[str] = []
            if sections:
                parts.append("Sections: " + ", ".join(sections))
            if layers:
                parts.append("Layers: " + ", ".join(layers))
            if group_count:
                parts.append(f"Groups: {group_count}")
            self.lock_status_label.setText(" | ".join(parts) if parts else "No locked sections or layers")

    def refresh_lock_controls(self) -> None:
        if not hasattr(self, "lock_section_combo"):
            return
        sections = sorted({dot.section for dot in self.project.dots if dot.section})
        layers = sorted({dot.layer for dot in self.project.dots if dot.layer})
        for combo, values in ((self.lock_section_combo, sections), (self.lock_layer_combo, layers)):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(values)
            if current:
                index = combo.findText(current)
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.blockSignals(False)
        self.apply_locks_to_field()

    def lock_current_section(self) -> None:
        section = self.lock_section_combo.currentText().strip() if hasattr(self, "lock_section_combo") else ""
        if not section:
            return
        values = self.workflow_list("locked_sections")
        if section not in values:
            values.append(section)
        self.apply_locks_to_field()

    def unlock_current_section(self) -> None:
        section = self.lock_section_combo.currentText().strip() if hasattr(self, "lock_section_combo") else ""
        self.project.workflow["locked_sections"] = [
            value for value in self.workflow_list("locked_sections") if value != section
        ]
        self.apply_locks_to_field()

    def lock_current_layer(self) -> None:
        layer = self.lock_layer_combo.currentText().strip() if hasattr(self, "lock_layer_combo") else ""
        if not layer:
            return
        values = self.workflow_list("locked_layers")
        if layer not in values:
            values.append(layer)
        self.apply_locks_to_field()

    def unlock_current_layer(self) -> None:
        layer = self.lock_layer_combo.currentText().strip() if hasattr(self, "lock_layer_combo") else ""
        self.project.workflow["locked_layers"] = [
            value for value in self.workflow_list("locked_layers") if value != layer
        ]
        self.apply_locks_to_field()

    def lock_selected_sections(self) -> None:
        selected_ids = self.field.selected_dot_ids()
        sections = {
            dot.section
            for dot in self.project.dots
            if dot.id in selected_ids and dot.section
        }
        values = self.workflow_list("locked_sections")
        for section in sorted(sections):
            if section not in values:
                values.append(section)
        self.apply_locks_to_field()
        if sections:
            self.statusBar().showMessage(f"Locked {len(sections)} section(s)", 2200)

    def unlock_selected_sections(self) -> None:
        selected_ids = self.field.selected_dot_ids()
        sections = {
            dot.section
            for dot in self.project.dots
            if dot.id in selected_ids and dot.section
        }
        self.project.workflow["locked_sections"] = [
            value for value in self.workflow_list("locked_sections") if value not in sections
        ]
        self.apply_locks_to_field()
        if sections:
            self.statusBar().showMessage(f"Unlocked {len(sections)} section(s)", 2200)

    def clear_section_locks(self) -> None:
        self.project.workflow["locked_sections"] = []
        self.project.workflow["locked_layers"] = []
        self.apply_locks_to_field()
        self.statusBar().showMessage("All section/layer locks cleared", 2200)

    def refresh_selection_sets(self) -> None:
        if not hasattr(self, "selection_set_combo"):
            return
        current = self.selection_set_combo.currentText()
        self.selection_set_combo.blockSignals(True)
        self.selection_set_combo.clear()
        self.selection_set_combo.addItems(sorted(self.workflow_bucket("selection_sets").keys()))
        if current:
            index = self.selection_set_combo.findText(current)
            if index >= 0:
                self.selection_set_combo.setCurrentIndex(index)
        self.selection_set_combo.blockSignals(False)

    def save_selection_set(self) -> None:
        selected_ids = self.field.selected_dot_ids()
        if not selected_ids:
            self.statusBar().showMessage("Select marchers before saving a selection set", 2600)
            return
        default_name = ", ".join(sorted({self.project.dot_by_id(dot_id).section for dot_id in selected_ids if self.project.dot_by_id(dot_id) and self.project.dot_by_id(dot_id).section})[:2])
        name, accepted = QInputDialog.getText(self, "Save Selection Set", "Name:", text=default_name or "Selection")
        if not accepted or not name.strip():
            return
        self.workflow_bucket("selection_sets")[name.strip()] = list(selected_ids)
        self.refresh_selection_sets()
        self.statusBar().showMessage(f"Selection set '{name.strip()}' saved", 2200)

    def load_selection_set(self) -> None:
        name = self.selection_set_combo.currentText().strip() if hasattr(self, "selection_set_combo") else ""
        ids = self.workflow_bucket("selection_sets").get(name, [])
        if not name or not isinstance(ids, list):
            return
        selected = set(str(dot_id) for dot_id in ids)
        for item in self.field.dot_items.values():
            item.setSelected(item.dot_id in selected)
        for item in self.field.prop_items.values():
            item.setSelected(False)
        self.refresh_selected_paths()
        self.sync_inspector()
        self.statusBar().showMessage(f"Loaded selection set '{name}'", 2200)

    def delete_selection_set(self) -> None:
        name = self.selection_set_combo.currentText().strip() if hasattr(self, "selection_set_combo") else ""
        if not name:
            return
        self.workflow_bucket("selection_sets").pop(name, None)
        self.refresh_selection_sets()
        self.statusBar().showMessage(f"Selection set '{name}' deleted", 2200)

    def refresh_tool_presets(self) -> None:
        if not hasattr(self, "tool_preset_combo"):
            return
        presets = self.load_global_library("tool_presets")
        current = self.tool_preset_combo.currentText()
        self.tool_preset_combo.blockSignals(True)
        self.tool_preset_combo.clear()
        self.tool_preset_combo.addItems(sorted(presets.keys()))
        if current:
            index = self.tool_preset_combo.findText(current)
            if index >= 0:
                self.tool_preset_combo.setCurrentIndex(index)
        self.tool_preset_combo.blockSignals(False)

    def current_tool_settings(self) -> dict[str, Any]:
        return {
            "tool": self.field.active_tool.value,
            "curve_bend": self.curve_bend.value(),
            "arc_radius": self.arc_radius.value(),
            "arc_width": self.arc_width.value(),
            "arc_height": self.arc_height.value(),
            "arc_start_angle": self.arc_start_angle.value(),
            "arc_sweep": self.arc_sweep.value(),
            "arc_rotation": self.arc_rotation.value(),
            "free_curve_anchor_count": self.free_curve_anchor_count.value(),
            "free_curve_closed": self.free_curve_closed.isChecked(),
            "free_curve_curved": self.free_curve_curved.isChecked(),
            "scatter_radius": self.scatter_radius.value(),
            "scatter_shape": self.scatter_shape.currentText(),
            "scatter_spacing": self.scatter_spacing.value(),
            "shape_radius": self.shape_radius.value(),
            "shape_width": self.shape_width.value(),
            "shape_height": self.shape_height.value(),
            "shape_fill_mode": self.shape_fill_mode.currentText(),
            "polygon_sides": self.polygon_sides.value(),
            "star_points": self.star_points.value(),
            "star_inner_percent": self.star_inner_percent.value(),
            "spiral_turns": self.spiral_turns.value(),
            "block_columns": self.block_columns.value(),
            "block_spacing": self.block_spacing.value(),
            "svg_min_spacing": self.svg_min_spacing.value(),
            "scale_width": self.scale_width.value(),
            "scale_height": self.scale_height.value(),
            "scale_lock_aspect": self.scale_lock_aspect.isChecked(),
            "scale_fit_padding": self.scale_fit_padding.value(),
            "warp_anchor_count": self.warp_anchor_count.value(),
            "warp_strength": self.warp_strength.value(),
            "rotation_degrees": self.rotation_degrees.value(),
            "shape_line_curved": self.shape_line_curved.isChecked(),
            "count_length": self.set_count_length.value() if hasattr(self, "set_count_length") else self.project.metadata.default_counts_per_set,
            "preview_center_offset": list(self.preview_center_offset),
            "line_endpoints": [list(point) for point in self.line_endpoints],
            "curve_handles": {name: list(point) for name, point in self.curve_handles.items()},
            "free_curve_anchors": [list(point) for point in self.free_curve_anchors],
            "warp_anchors": [list(point) for point in self.warp_anchors],
            "mirror_axis": self.mirror_axis,
            "shape_line_anchor_dot_ids": sorted(self.shape_line_anchor_dot_ids),
            "shape_line_anchor_positions": {
                dot_id: list(point)
                for dot_id, point in self.shape_line_anchor_positions.items()
            },
            "preview_transform_pivot": (
                list(self.preview_transform_pivot)
                if self.preview_transform_pivot is not None
                else None
            ),
        }

    def apply_tool_settings(self, settings: dict[str, Any]) -> None:
        def set_combo(combo: QComboBox, value: Any) -> None:
            index = combo.findText(str(value))
            if index >= 0:
                combo.setCurrentIndex(index)

        for attr in (
            "curve_bend",
            "arc_radius",
            "arc_width",
            "arc_height",
            "arc_start_angle",
            "arc_sweep",
            "arc_rotation",
            "free_curve_anchor_count",
            "scatter_radius",
            "scatter_spacing",
            "shape_radius",
            "shape_width",
            "shape_height",
            "polygon_sides",
            "star_points",
            "star_inner_percent",
            "spiral_turns",
            "block_columns",
            "block_spacing",
            "svg_min_spacing",
            "scale_width",
            "scale_height",
            "scale_fit_padding",
            "warp_anchor_count",
            "warp_strength",
            "rotation_degrees",
        ):
            if attr in settings and hasattr(self, attr):
                getattr(self, attr).setValue(settings[attr])
        if "scatter_shape" in settings:
            set_combo(self.scatter_shape, settings["scatter_shape"])
        if "shape_fill_mode" in settings:
            set_combo(self.shape_fill_mode, settings["shape_fill_mode"])
        if "scale_lock_aspect" in settings:
            self.scale_lock_aspect.setChecked(bool(settings["scale_lock_aspect"]))
        if "shape_line_curved" in settings:
            self.shape_line_curved.setChecked(bool(settings["shape_line_curved"]))
        if "free_curve_closed" in settings:
            self.free_curve_closed.setChecked(bool(settings["free_curve_closed"]))
        if "free_curve_curved" in settings:
            self.free_curve_curved.setChecked(bool(settings["free_curve_curved"]))
        if "count_length" in settings and hasattr(self, "set_count_length"):
            self.set_count_length.setValue(int(settings["count_length"]))
        if "tool" in settings:
            try:
                self.set_tool(EditorTool(str(settings["tool"])))
            except ValueError:
                pass
        if "preview_center_offset" in settings:
            value = settings["preview_center_offset"]
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                self.preview_center_offset = (float(value[0]), float(value[1]))
        if "line_endpoints" in settings:
            values = settings["line_endpoints"]
            if isinstance(values, list) and len(values) == 2:
                self.line_endpoints = [(float(point[0]), float(point[1])) for point in values]
        if "curve_handles" in settings and isinstance(settings["curve_handles"], dict):
            self.curve_handles = {
                str(name): (float(point[0]), float(point[1]))
                for name, point in settings["curve_handles"].items()
                if isinstance(point, (list, tuple)) and len(point) >= 2
            }
        for key, attribute in (
            ("free_curve_anchors", "free_curve_anchors"),
            ("warp_anchors", "warp_anchors"),
        ):
            values = settings.get(key)
            if isinstance(values, list):
                setattr(
                    self,
                    attribute,
                    [
                        (float(point[0]), float(point[1]))
                        for point in values
                        if isinstance(point, (list, tuple)) and len(point) >= 2
                    ],
                )
        if "mirror_axis" in settings:
            self.mirror_axis = float(settings["mirror_axis"])
        if isinstance(settings.get("shape_line_anchor_dot_ids"), list):
            self.shape_line_anchor_dot_ids = {
                str(dot_id) for dot_id in settings["shape_line_anchor_dot_ids"]
            }
        if isinstance(settings.get("shape_line_anchor_positions"), dict):
            self.shape_line_anchor_positions = {
                str(dot_id): (float(point[0]), float(point[1]))
                for dot_id, point in settings["shape_line_anchor_positions"].items()
                if isinstance(point, (list, tuple)) and len(point) >= 2
            }
        pivot = settings.get("preview_transform_pivot")
        if isinstance(pivot, (list, tuple)) and len(pivot) >= 2:
            self.preview_transform_pivot = (float(pivot[0]), float(pivot[1]))
        self.update_formation_preview()

    def save_tool_preset(self) -> None:
        name, accepted = QInputDialog.getText(self, "Save Tool Preset", "Preset name:")
        if not accepted or not name.strip():
            return
        presets = self.load_global_library("tool_presets")
        presets[name.strip()] = self.current_tool_settings()
        self.save_global_library("tool_presets", presets)
        self.refresh_tool_presets()
        self.tool_preset_combo.setCurrentText(name.strip())
        self.statusBar().showMessage(f"Tool preset '{name.strip()}' saved", 2200)

    def load_tool_preset(self) -> None:
        name = self.tool_preset_combo.currentText().strip() if hasattr(self, "tool_preset_combo") else ""
        settings = self.load_global_library("tool_presets").get(name)
        if not isinstance(settings, dict):
            return
        self.apply_tool_settings(settings)
        self.statusBar().showMessage(f"Tool preset '{name}' loaded", 2200)

    def delete_tool_preset(self) -> None:
        name = self.tool_preset_combo.currentText().strip() if hasattr(self, "tool_preset_combo") else ""
        presets = self.load_global_library("tool_presets")
        if not name or name not in presets:
            return
        presets.pop(name, None)
        self.save_global_library("tool_presets", presets)
        self.refresh_tool_presets()
        self.statusBar().showMessage(f"Tool preset '{name}' deleted", 2200)

    def refresh_formation_presets(self) -> None:
        if not hasattr(self, "formation_preset_combo"):
            return
        presets = self.load_global_library("formation_presets")
        current = self.formation_preset_combo.currentText()
        self.formation_preset_combo.blockSignals(True)
        self.formation_preset_combo.clear()
        self.formation_preset_combo.addItems(sorted(presets.keys()))
        if current:
            index = self.formation_preset_combo.findText(current)
            if index >= 0:
                self.formation_preset_combo.setCurrentIndex(index)
        self.formation_preset_combo.blockSignals(False)

    def save_formation_preset(self) -> None:
        ids, positions = self.selected_positions()
        if len(ids) < 2:
            self.statusBar().showMessage("Select at least two marchers before saving a formation preset", 2600)
            return
        center_x = sum(x for x, _y in positions) / len(positions)
        center_y = sum(y for _x, y in positions) / len(positions)
        sections = sorted({self.project.dot_by_id(dot_id).section for dot_id in ids if self.project.dot_by_id(dot_id) and self.project.dot_by_id(dot_id).section})
        name, accepted = QInputDialog.getText(
            self,
            "Save Formation Preset",
            "Preset name:",
            text=(sections[0] + " Form") if sections else "Formation",
        )
        if not accepted or not name.strip():
            return
        points = [(x - center_x, y - center_y) for x, y in positions]
        presets = self.load_global_library("formation_presets")
        presets[name.strip()] = {
            "points": points,
            "count": len(points),
            "sections": sections,
            "width": max(x for x, _y in points) - min(x for x, _y in points),
            "height": max(y for _x, y in points) - min(y for _x, y in points),
        }
        self.save_global_library("formation_presets", presets)
        self.refresh_formation_presets()
        self.formation_preset_combo.setCurrentText(name.strip())
        self.statusBar().showMessage(f"Formation preset '{name.strip()}' saved", 2200)

    def apply_formation_preset(self) -> None:
        name = self.formation_preset_combo.currentText().strip() if hasattr(self, "formation_preset_combo") else ""
        preset = self.load_global_library("formation_presets").get(name)
        ids, current = self.selected_positions()
        if not isinstance(preset, dict) or not ids or not current:
            return
        raw_points = preset.get("points", [])
        points = [
            (float(point[0]), float(point[1]))
            for point in raw_points
            if isinstance(point, (list, tuple)) and len(point) >= 2
        ]
        if not points:
            return
        center_x = sum(x for x, _y in current) / len(current)
        center_y = sum(y for _x, y in current) / len(current)
        if len(points) != len(ids):
            sampled = positions_along_path(points, len(ids))
        else:
            sampled = points
        sampled = ordered_targets(current, [(center_x + x, center_y + y) for x, y in sampled])
        targets = sampled
        after = self.current_positions()
        after.update(dict(zip(ids, targets)))
        self.apply_positions(after)
        self.statusBar().showMessage(f"Formation preset '{name}' applied", 2200)

    def delete_formation_preset(self) -> None:
        name = self.formation_preset_combo.currentText().strip() if hasattr(self, "formation_preset_combo") else ""
        presets = self.load_global_library("formation_presets")
        if not name or name not in presets:
            return
        presets.pop(name, None)
        self.save_global_library("formation_presets", presets)
        self.refresh_formation_presets()
        self.statusBar().showMessage(f"Formation preset '{name}' deleted", 2200)

    def current_positions(self) -> dict[str, tuple[float, float]]:
        return dict(self.current_set().dot_positions)

    def current_prop_states(self) -> dict[str, dict[str, float]]:
        return {prop_id: dict(state) for prop_id, state in self.current_set().prop_positions.items()}

    def current_transition_start_positions(self) -> dict[str, tuple[float, float]]:
        if self.set_index > 0:
            return self.project.sets[self.set_index - 1].dot_positions
        return {dot.id: (dot.x, dot.y) for dot in self.project.dots}

    def select_same_attribute(self, attribute: str, label: str) -> None:
        selected_ids = self.field.selected_dot_ids()
        dots_by_id = {dot.id: dot for dot in self.project.dots}
        if selected_ids:
            selected_dot = dots_by_id.get(selected_ids[0])
            value = str(getattr(selected_dot, attribute, "")) if selected_dot else ""
        else:
            values = sorted({str(getattr(dot, attribute, "")) for dot in self.project.dots if getattr(dot, attribute, "")})
            if not values:
                return
            value, accepted = QInputDialog.getItem(self, f"Select {label}", label, values, 0, False)
            if not accepted:
                return
        matching = [
            dot.id
            for dot in self.project.dots
            if str(getattr(dot, attribute, "")).casefold() == value.casefold()
        ]
        self.select_dot_ids(matching)
        display_value = value or "Unassigned"
        self.statusBar().showMessage(f"Selected {len(matching)} marcher(s) in {label.lower()} {display_value}", 2200)

    def select_same_instrument(self) -> None:
        self.select_same_attribute("instrument", "Instrument")

    def select_same_section(self) -> None:
        self.select_same_attribute("section", "Section")

    def invert_selection(self) -> None:
        for item in self.field.dot_items.values():
            item.setSelected(not item.isSelected())
        for item in self.field.prop_items.values():
            item.setSelected(False)
        self.refresh_selected_paths()
        self.sync_inspector()

    def select_moving_this_set(self) -> None:
        previous = self.current_transition_start_positions()
        current = self.current_set().dot_positions
        for dot_id, item in self.field.dot_items.items():
            start = previous.get(dot_id)
            end = current.get(dot_id)
            item.setSelected(bool(start and end and distance(start, end) > 0.01))
        self.refresh_selected_paths()
        self.sync_inspector()

    def editing_set_one_opening(self) -> bool:
        return (
            self.set_index == 0
            and bool(self.project.sets)
            and self.current_count <= float(self.current_set().start_count) + 0.001
        )

    @staticmethod
    def positions_match(a: tuple[float, float], b: tuple[float, float]) -> bool:
        return abs(a[0] - b[0]) <= 0.001 and abs(a[1] - b[1]) <= 0.001

    def apply_opening_positions(
        self,
        positions: dict[str, tuple[float, float]],
        sync_unchanged_set_one_endpoints: bool = False,
        label: str = "Edit Opening Positions",
    ) -> None:
        if not positions:
            return
        before_dots = deepcopy(self.project.dots)
        before_props = deepcopy(self.project.props)
        before_sets = deepcopy(self.project.sets)
        before_dot_selection = self.field.selected_dot_ids()
        before_prop_selection = self.field.selected_prop_ids()
        changed = 0
        set_one = self.project.sets[0] if self.project.sets else None
        for dot_id, (x, y) in positions.items():
            dot = self.project.dot_by_id(dot_id)
            if not dot or self.is_dot_locked(dot_id):
                continue
            old_position = (dot.x, dot.y)
            new_position = (float(x), float(y))
            if sync_unchanged_set_one_endpoints and set_one is not None:
                endpoint = set_one.dot_positions.get(dot_id, old_position)
                if self.positions_match(endpoint, old_position):
                    set_one.dot_positions[dot_id] = new_position
            if not self.positions_match(old_position, new_position):
                dot.x, dot.y = new_position
                changed += 1
        if not changed:
            self.set_count(self.current_count, seek_audio=False)
            return
        self.set_count(self.current_count, seek_audio=False)
        self.refresh_marcher_table()
        self.refresh_selected_paths()
        self.sync_inspector()
        self.push_project_content_snapshot(
            before_dots,
            before_props,
            before_sets,
            before_dot_selection,
            before_prop_selection,
            label,
        )

    def capture_opening_positions_from_current_view(self) -> None:
        if not self.project.dots:
            return
        selected_ids = self.field.selected_dot_ids()
        target_ids = selected_ids or [dot.id for dot in self.project.dots]
        positions: dict[str, tuple[float, float]] = {}
        for dot_id in target_ids:
            item = self.field.dot_items.get(dot_id)
            if not item:
                continue
            positions[dot_id] = self.field.scene_to_field(item.pos())
        before_positions = {dot.id: (dot.x, dot.y) for dot in self.project.dots}
        self.apply_opening_positions(positions, sync_unchanged_set_one_endpoints=False)
        if all(self.positions_match(before_positions.get(dot_id, positions[dot_id]), positions[dot_id]) for dot_id in positions):
            self.statusBar().showMessage("Opening positions already match the current view.", 2400)
            return
        scope = "selected marchers" if selected_ids else "all marchers"
        self.statusBar().showMessage(
            f"Opening positions captured for {scope}. Set 1 can now move from this form.",
            3600,
        )

    def carry_selected_forward(self) -> None:
        selected_ids = self.field.selected_dot_ids()
        if not selected_ids or self.set_index >= len(self.project.sets) - 1:
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        source_positions = self.current_set().dot_positions
        for drill_set in self.project.sets[self.set_index + 1:]:
            for dot_id in selected_ids:
                if dot_id in source_positions:
                    drill_set.dot_positions[dot_id] = source_positions[dot_id]
                    drill_set.path_anchors.pop(dot_id, None)
                    drill_set.path_controls.pop(dot_id, None)
                    drill_set.count_positions.pop(dot_id, None)
                    drill_set.count_facings.pop(dot_id, None)
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=False)
        self.push_set_snapshot(before_sets, before_index, before_count, "Carry Selected Forward")

    def dot_moved(self, dot_id: str, x: float, y: float) -> None:
        if self.is_dot_locked(dot_id):
            self.field.set_positions(self.current_set().dot_positions)
            self.field.set_facings(self.facings_for_set())
            self.statusBar().showMessage("That marcher is in a locked section/layer", 2200)
            return
        if self.micro_edit_enabled.isChecked():
            self.store_micro_edit_positions({dot_id: (x, y)})
            return
        if self.editing_set_one_opening():
            self.apply_opening_positions({dot_id: (x, y)}, sync_unchanged_set_one_endpoints=True)
            return
        before = self.current_positions()
        after = dict(before)
        after[dot_id] = (x, y)
        self.apply_positions(after)
        start = before.get(dot_id, (x, y))
        self.remember_transform_action(
            TransformParameters(offset_x=x - start[0], offset_y=y - start[1]),
            {dot_id: start},
            "Move Marcher",
        )

    def dots_moved(self, positions: dict[str, tuple[float, float]]) -> None:
        positions = self.editable_positions(positions)
        if not positions:
            self.field.set_positions(self.current_set().dot_positions)
            self.field.set_facings(self.facings_for_set())
            self.statusBar().showMessage("Selected marchers are locked", 2200)
            return
        if self.micro_edit_enabled.isChecked():
            self.store_micro_edit_positions(positions)
            return
        if self.editing_set_one_opening():
            self.apply_opening_positions(positions, sync_unchanged_set_one_endpoints=True)
            return
        before = self.current_positions()
        after = dict(before)
        after.update(positions)
        self.apply_positions(after)
        source = {dot_id: before[dot_id] for dot_id in positions if dot_id in before}
        if source:
            delta_x = sum(positions[dot_id][0] - source[dot_id][0] for dot_id in source) / len(source)
            delta_y = sum(positions[dot_id][1] - source[dot_id][1] for dot_id in source) / len(source)
            self.remember_transform_action(
                TransformParameters(offset_x=delta_x, offset_y=delta_y),
                source,
                "Move Form",
            )

    def prop_moved(self, prop_id: str, state: dict[str, float]) -> None:
        before = self.current_prop_states()
        after = {key: dict(value) for key, value in before.items()}
        after[prop_id] = dict(state)
        self.apply_prop_states(after)

    def props_moved(self, states: dict[str, dict[str, float]]) -> None:
        before = self.current_prop_states()
        after = {key: dict(value) for key, value in before.items()}
        for prop_id, state in states.items():
            after[prop_id] = dict(state)
        self.apply_prop_states(after)

    def next_dot_id(self) -> str:
        used_numbers = []
        for dot in self.project.dots:
            if dot.id.startswith("dot") and dot.id[3:].isdigit():
                used_numbers.append(int(dot.id[3:]))
        next_number = max(used_numbers, default=0) + 1
        return f"dot{next_number:03d}"

    def add_marcher(self) -> None:
        if self.set_index != 0:
            QMessageBox.information(self, "Add Marcher", "Add marchers from Set 1.")
            return
        before_dots = deepcopy(self.project.dots)
        before_props = deepcopy(self.project.props)
        before_sets = deepcopy(self.project.sets)
        before_dot_selection = self.field.selected_dot_ids()
        before_prop_selection = self.field.selected_prop_ids()
        dot_id = self.next_dot_id()
        dot = self.project.dot_by_id(dot_id)
        if dot:
            return
        new_dot = Dot(
            id=dot_id,
            name=f"Dot {len(self.project.dots) + 1}",
            x=0,
            y=0,
            color="#e53935",
            section="",
            instrument="",
            rank="",
            equipment="",
            layer="Main",
        )
        self.project.dots.append(new_dot)
        for drill_set in self.project.sets:
            drill_set.dot_positions[dot_id] = (new_dot.x, new_dot.y)
        self.field.rebuild_dots()
        self.field.set_positions(self.current_set().dot_positions)
        self.field.set_facings(self.facings_for_set())
        self.field.set_prop_states(self.current_set().prop_positions)
        self.field.dot_items[dot_id].setSelected(True)
        self.refresh_marcher_table()
        self.refresh_visibility_filters()
        self.selection_changed()
        self.push_project_content_snapshot(
            before_dots,
            before_props,
            before_sets,
            before_dot_selection,
            before_prop_selection,
            "Add Marcher",
        )

    def delete_selected_marchers(self) -> None:
        if self.set_index != 0:
            QMessageBox.information(self, "Delete Marchers", "Delete marchers from Set 1.")
            return
        selected = set(self.field.selected_dot_ids())
        if not selected:
            return
        before_dots = deepcopy(self.project.dots)
        before_props = deepcopy(self.project.props)
        before_sets = deepcopy(self.project.sets)
        before_dot_selection = self.field.selected_dot_ids()
        before_prop_selection = self.field.selected_prop_ids()
        self.project.dots = [dot for dot in self.project.dots if dot.id not in selected]
        for drill_set in self.project.sets:
            for dot_id in selected:
                drill_set.dot_positions.pop(dot_id, None)
                drill_set.path_anchors.pop(dot_id, None)
                drill_set.path_controls.pop(dot_id, None)
                drill_set.count_positions.pop(dot_id, None)
                drill_set.count_facings.pop(dot_id, None)
        self.field.clear_preview()
        self.field.clear_paths()
        self.field.rebuild_dots()
        self.field.set_positions(self.current_set().dot_positions)
        self.field.set_facings(self.facings_for_set())
        self.field.set_prop_states(self.current_set().prop_positions)
        self.refresh_marcher_table()
        self.refresh_visibility_filters()
        self.refresh_constraints()
        self.sync_inspector()
        self.push_project_content_snapshot(
            before_dots,
            before_props,
            before_sets,
            before_dot_selection,
            before_prop_selection,
            "Delete Marchers",
        )

    def next_prop_id(self) -> str:
        used_numbers = []
        for prop in self.project.props:
            if prop.id.startswith("prop") and prop.id[4:].isdigit():
                used_numbers.append(int(prop.id[4:]))
        next_number = max(used_numbers, default=0) + 1
        return f"prop{next_number:03d}"

    def import_prop_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Prop Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not path:
            return
        before_dots = deepcopy(self.project.dots)
        before_props = deepcopy(self.project.props)
        before_sets = deepcopy(self.project.sets)
        before_dot_selection = self.field.selected_dot_ids()
        before_prop_selection = self.field.selected_prop_ids()
        source = Path(path)
        prop_id = self.next_prop_id()
        props_dir = self.project_dir / "props"
        props_dir.mkdir(exist_ok=True)
        destination = props_dir / f"{prop_id}{source.suffix.lower() or '.png'}"
        shutil.copy2(source, destination)

        pixmap = QPixmap(str(destination))
        aspect = pixmap.width() / pixmap.height() if not pixmap.isNull() and pixmap.height() else 2.0
        width = 8.0
        height = max(1.0, width / max(0.1, aspect))
        prop = Prop(
            id=prop_id,
            name=source.stem,
            image_file=str(destination.relative_to(self.project_dir)),
            x=0.0,
            y=0.0,
            width=width,
            height=height,
            rotation=0.0,
            layer="Props",
        )
        self.project.props.append(prop)
        for drill_set in self.project.sets:
            drill_set.prop_positions[prop.id] = prop_default_state(prop)
        self.field.rebuild_props()
        self.field.set_prop_states(self.current_set().prop_positions)
        for item in self.field.scene.selectedItems():
            item.setSelected(False)
        self.field.prop_items[prop.id].setSelected(True)
        self.refresh_prop_table()
        self.refresh_visibility_filters()
        self.selection_changed()
        self.statusBar().showMessage(f"Imported prop {prop.name}", 3000)
        self.push_project_content_snapshot(
            before_dots,
            before_props,
            before_sets,
            before_dot_selection,
            before_prop_selection,
            "Import Prop",
        )

    def open_prop_designer(self) -> None:
        dialog = PropDesignerDialog(self.project_dir, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.created_design:
            return
        self.add_designed_prop(dialog.created_design)

    def add_designed_prop(self, design: CreatedPropDesign) -> None:
        before_dots = deepcopy(self.project.dots)
        before_props = deepcopy(self.project.props)
        before_sets = deepcopy(self.project.sets)
        before_dot_selection = self.field.selected_dot_ids()
        before_prop_selection = self.field.selected_prop_ids()
        prop = Prop(
            id=self.next_prop_id(),
            name=design.name,
            image_file=design.image_file,
            x=design.x,
            y=design.y,
            width=design.width,
            height=design.height,
            rotation=0.0,
            layer=design.layer or "Props",
        )
        self.project.props.append(prop)
        for drill_set in self.project.sets:
            drill_set.prop_positions[prop.id] = prop_default_state(prop)
        self.field.rebuild_props()
        self.field.set_prop_states(self.current_set().prop_positions)
        for item in self.field.scene.selectedItems():
            item.setSelected(False)
        self.field.prop_items[prop.id].setSelected(True)
        self.refresh_prop_table()
        self.refresh_visibility_filters()
        self.selection_changed()
        self.statusBar().showMessage(f"Added designed prop {prop.name}", 2600)
        self.push_project_content_snapshot(
            before_dots,
            before_props,
            before_sets,
            before_dot_selection,
            before_prop_selection,
            "Add Designed Prop",
        )

    def add_front_ensemble_prop(self) -> None:
        count = 1 + sum(1 for prop in self.project.props if prop.layer == "Front Ensemble")
        x_position = self.next_open_front_ensemble_x(count)
        self.add_generated_prop(
            name=f"FE{count}",
            layer="Front Ensemble",
            x=x_position,
            y=-31.5,
            width=5.0,
            height=2.4,
            label="Add Front Ensemble Prop",
        )

    def add_drum_major_stand(self) -> None:
        count = 1 + sum(1 for prop in self.project.props if prop.layer == "Drum Major")
        offsets = [0.0, -24.0, 24.0, -40.0, 40.0]
        x_position = offsets[count - 1] if count <= len(offsets) else 0.0
        self.add_generated_prop(
            name=f"DM Stand {count}",
            layer="Drum Major",
            x=x_position,
            y=-37.0,
            width=3.0,
            height=3.0,
            label="Add Drum Major Stand",
        )

    def next_open_front_ensemble_x(self, count: int) -> float:
        if count <= 1:
            return 0.0
        spacing = 7.0
        existing = [
            prop.x
            for prop in self.project.props
            if prop.layer == "Front Ensemble"
        ]
        candidate = ((count - 1) // 2 + 1) * spacing
        if count % 2 == 0:
            candidate = -candidate
        while any(abs(candidate - value) < 1.0 for value in existing):
            candidate += spacing
        return candidate

    def add_generated_prop(
        self,
        name: str,
        layer: str,
        x: float,
        y: float,
        width: float,
        height: float,
        label: str,
    ) -> None:
        before_dots = deepcopy(self.project.dots)
        before_props = deepcopy(self.project.props)
        before_sets = deepcopy(self.project.sets)
        before_dot_selection = self.field.selected_dot_ids()
        before_prop_selection = self.field.selected_prop_ids()
        prop = Prop(
            id=self.next_prop_id(),
            name=name,
            image_file="",
            x=x,
            y=y,
            width=width,
            height=height,
            rotation=0.0,
            layer=layer,
        )
        self.project.props.append(prop)
        for drill_set in self.project.sets:
            drill_set.prop_positions[prop.id] = prop_default_state(prop)
        self.field.rebuild_props()
        self.field.set_prop_states(self.current_set().prop_positions)
        for item in self.field.scene.selectedItems():
            item.setSelected(False)
        self.field.prop_items[prop.id].setSelected(True)
        self.refresh_prop_table()
        self.refresh_visibility_filters()
        self.selection_changed()
        self.statusBar().showMessage(f"Added {name}", 2500)
        self.push_project_content_snapshot(
            before_dots,
            before_props,
            before_sets,
            before_dot_selection,
            before_prop_selection,
            label,
        )

    def delete_selected_props(self) -> None:
        selected = set(self.field.selected_prop_ids())
        if not selected:
            return
        before_dots = deepcopy(self.project.dots)
        before_props = deepcopy(self.project.props)
        before_sets = deepcopy(self.project.sets)
        before_dot_selection = self.field.selected_dot_ids()
        before_prop_selection = self.field.selected_prop_ids()
        self.project.props = [prop for prop in self.project.props if prop.id not in selected]
        for drill_set in self.project.sets:
            for prop_id in selected:
                drill_set.prop_positions.pop(prop_id, None)
        self.field.rebuild_props()
        self.field.set_prop_states(self.current_set().prop_positions)
        self.refresh_prop_table()
        self.refresh_visibility_filters()
        self.sync_inspector()
        self.push_project_content_snapshot(
            before_dots,
            before_props,
            before_sets,
            before_dot_selection,
            before_prop_selection,
            "Delete Props",
        )

    def apply_prop_states(
        self,
        states: dict[str, dict[str, float]],
        push_undo: bool = True,
        set_index: int | None = None,
    ) -> None:
        target_set_index = self.set_index if set_index is None else set_index
        normalized = {prop_id: dict(state) for prop_id, state in states.items()}
        target_before = {
            prop_id: dict(state)
            for prop_id, state in self.project.sets[target_set_index].prop_positions.items()
        }
        changed_prop_ids = {
            prop_id
            for prop_id, state in normalized.items()
            if target_before.get(prop_id) != state
        }
        if push_undo and set_index is None:
            multi_indices = self.selected_set_indices_for_edit()
            if len(multi_indices) > 1 and changed_prop_ids:
                before_sets = deepcopy(self.project.sets)
                before_index = self.set_index
                before_count = self.current_count
                for edit_index in multi_indices:
                    drill_set = self.project.sets[edit_index]
                    for prop_id in changed_prop_ids:
                        if prop_id in normalized:
                            drill_set.prop_positions[prop_id] = dict(normalized[prop_id])
                            if edit_index == 0:
                                prop = self.project.prop_by_id(prop_id)
                                if prop:
                                    state = normalized[prop_id]
                                    prop.x = float(state.get("x", prop.x))
                                    prop.y = float(state.get("y", prop.y))
                                    prop.width = float(state.get("width", prop.width))
                                    prop.height = float(state.get("height", prop.height))
                                    prop.rotation = float(state.get("rotation", prop.rotation))
                self.populate_sets()
                self.sync_timeline()
                self.set_count(self.current_count, seek_audio=False)
                self.push_set_snapshot(before_sets, before_index, before_count, "Multi-Set Prop Move")
                return
        if push_undo:
            self.undo_stack.push(
                MovePropsCommand(
                    self,
                    target_set_index,
                    target_before,
                    normalized,
                    "Move Props",
                )
            )
            return
        self.project.sets[target_set_index].prop_positions.update(normalized)
        for prop in self.project.props:
            if prop.id in normalized and target_set_index == 0:
                state = normalized[prop.id]
                prop.x = float(state.get("x", prop.x))
                prop.y = float(state.get("y", prop.y))
                prop.width = float(state.get("width", prop.width))
                prop.height = float(state.get("height", prop.height))
                prop.rotation = float(state.get("rotation", prop.rotation))
        if target_set_index == self.set_index:
            self.field.set_prop_states(self.current_set().prop_positions)
            self.refresh_prop_table()
            self.sync_inspector()
            if hasattr(self, "minimap"):
                self.minimap.update()

    def apply_positions(
        self,
        positions: dict[str, tuple[float, float]],
        push_undo: bool = True,
        set_index: int | None = None,
    ) -> None:
        target_set_index = self.set_index if set_index is None else set_index
        target_before = dict(self.project.sets[target_set_index].dot_positions)
        positions = dict(positions)
        if push_undo:
            locked_ids = {
                dot.id
                for dot in self.project.dots
                if self.is_dot_locked(dot.id)
            }
            positions = expand_live_symmetry_changes(
                self.project.workflow.get("live_symmetry", []),
                target_before,
                positions,
                locked_ids,
            )
            positions = expand_linked_position_changes(
                self.project,
                target_set_index,
                positions,
                locked_group_dot_ids(self.project),
            )
        for dot_id in list(positions):
            if self.is_dot_locked(dot_id):
                positions[dot_id] = target_before.get(dot_id, positions[dot_id])
        changed_dot_ids = {
            dot_id
            for dot_id, position in positions.items()
            if target_before.get(dot_id) != position
        }
        if push_undo and set_index is None:
            multi_indices = self.selected_set_indices_for_edit(list(changed_dot_ids))
            if len(multi_indices) > 1 and changed_dot_ids:
                before_sets = deepcopy(self.project.sets)
                before_index = self.set_index
                before_count = self.current_count
                deltas = {
                    dot_id: (
                        positions[dot_id][0] - target_before.get(dot_id, positions[dot_id])[0],
                        positions[dot_id][1] - target_before.get(dot_id, positions[dot_id])[1],
                    )
                    for dot_id in changed_dot_ids
                    if dot_id in positions
                }
                for edit_index in multi_indices:
                    drill_set = self.project.sets[edit_index]
                    for dot_id in changed_dot_ids:
                        if self.is_dot_locked(dot_id):
                            continue
                        if dot_id in positions and dot_id in deltas:
                            if edit_index == self.set_index:
                                drill_set.dot_positions[dot_id] = positions[dot_id]
                            else:
                                old_x, old_y = drill_set.dot_positions.get(dot_id, target_before.get(dot_id, (0.0, 0.0)))
                                delta_x, delta_y = deltas[dot_id]
                                drill_set.dot_positions[dot_id] = (old_x + delta_x, old_y + delta_y)
                            drill_set.path_anchors.pop(dot_id, None)
                            drill_set.path_controls.pop(dot_id, None)
                            drill_set.count_positions.pop(dot_id, None)
                            drill_set.count_facings.pop(dot_id, None)
                self.populate_sets()
                self.sync_timeline()
                self.set_count(self.current_count, seek_audio=False)
                self.push_set_snapshot(before_sets, before_index, before_count, "Ripple Edit Dots")
                return
        if changed_dot_ids and target_set_index == self.set_index:
            positions = self.constrain_positions(dict(positions), changed_dot_ids)
        if push_undo:
            self.undo_stack.push(
                MoveDotsCommand(
                    self,
                    target_set_index,
                    target_before,
                    positions,
                    "Move Dots",
                )
            )
            return
        self.project.sets[target_set_index].dot_positions.update(positions)
        if target_set_index == self.set_index:
            self.field.set_positions(self.current_set().dot_positions)
            self.field.set_facings(self.facings_for_set())
            self.field.set_prop_states(self.current_set().prop_positions)
            self.update_formation_preview()
            self.refresh_selected_paths()
            self.sync_inspector()
            self.refresh_measurements()
            if hasattr(self, "minimap"):
                self.minimap.update()
            self.schedule_live_conflict_analysis()

    def constrain_positions(
        self,
        positions: dict[str, tuple[float, float]],
        changed_dot_ids: set[str],
    ) -> dict[str, tuple[float, float]]:
        if not self.project.constraints:
            return positions
        return solve_constraints(
            positions,
            self.project.constraints,
            changed_dot_ids=changed_dot_ids,
            fallback_spacing=self.interval_spacing.value() if hasattr(self, "interval_spacing") else 2.0,
        )

    def clone_path_anchors(self, set_index: int) -> dict[str, list[tuple[float, float]]]:
        return {
            dot_id: list(anchors)
            for dot_id, anchors in self.project.sets[set_index].path_anchors.items()
        }

    def clone_path_controls(self, set_index: int) -> dict[str, list[dict[str, tuple[float, float]]]]:
        return {
            dot_id: [dict(controls) for controls in control_sets]
            for dot_id, control_sets in self.project.sets[set_index].path_controls.items()
        }

    def clone_count_positions(self, set_index: int) -> dict[str, dict[float, tuple[float, float]]]:
        return {
            dot_id: dict(keyframes)
            for dot_id, keyframes in self.project.sets[set_index].count_positions.items()
        }

    def apply_path_geometry(
        self,
        set_index: int,
        anchors: dict[str, list[tuple[float, float]]],
        controls: dict[str, list[dict[str, tuple[float, float]]]] | None = None,
        count_positions: dict[str, dict[float, tuple[float, float]]] | None = None,
    ) -> None:
        self.project.sets[set_index].path_anchors = {
            dot_id: list(anchor_list)
            for dot_id, anchor_list in anchors.items()
        }
        self.project.sets[set_index].path_controls = {
            dot_id: [dict(control_set) for control_set in control_sets]
            for dot_id, control_sets in (controls or {}).items()
        }
        if count_positions is not None:
            self.project.sets[set_index].count_positions = {
                dot_id: dict(keyframes)
                for dot_id, keyframes in count_positions.items()
            }
        if set_index == self.set_index or set_index == self.path_display_set_index():
            self.refresh_selected_paths()
            self.schedule_live_conflict_analysis()

    def push_path_geometry_snapshot(
        self,
        set_index: int,
        before_anchors: dict[str, list[tuple[float, float]]],
        before_controls: dict[str, list[dict[str, tuple[float, float]]]],
        before_count_positions: dict[str, dict[float, tuple[float, float]]],
        label: str,
    ) -> None:
        after_anchors = self.clone_path_anchors(set_index)
        after_controls = self.clone_path_controls(set_index)
        after_count_positions = self.clone_count_positions(set_index)
        if (
            before_anchors == after_anchors
            and before_controls == after_controls
            and before_count_positions == after_count_positions
        ):
            self.refresh_selected_paths()
            return
        self.apply_path_geometry(set_index, before_anchors, before_controls, before_count_positions)
        self.undo_stack.push(
            PathGeometryCommand(
                self,
                set_index,
                before_anchors,
                after_anchors,
                before_controls,
                after_controls,
                before_count_positions,
                after_count_positions,
                label,
            )
        )

    def push_set_snapshot(
        self,
        before_sets: list[DrillSet],
        before_index: int,
        before_count: float,
        label: str,
    ) -> None:
        after_sets = deepcopy(self.project.sets)
        after_index = self.set_index
        after_count = self.current_count
        if before_sets == after_sets and before_index == after_index and before_count == after_count:
            return
        self.apply_set_snapshot(before_sets, before_index, before_count)
        self.undo_stack.push(
            SetSnapshotCommand(
                self,
                before_sets,
                after_sets,
                before_index,
                after_index,
                before_count,
                after_count,
                label,
            )
        )

    def apply_set_snapshot(self, sets: list[DrillSet], set_index: int, count: float) -> None:
        if not sets:
            return
        self.project.sets = deepcopy(sets)
        self.project.ensure_set_positions()
        self.set_index = max(0, min(set_index, len(self.project.sets) - 1))
        drill_set = self.current_set()
        self.current_count = max(drill_set.start_count, min(count, drill_set.end_count))
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=False)
        self.refresh_constraints()
        self.refresh_timing_events()
        self.sync_inspector()
        self.schedule_live_conflict_analysis()

    def push_project_content_snapshot(
        self,
        before_dots: list[Dot],
        before_props: list[Prop],
        before_sets: list[DrillSet],
        before_dot_selection: list[str],
        before_prop_selection: list[str],
        label: str,
    ) -> None:
        after_dots = deepcopy(self.project.dots)
        after_props = deepcopy(self.project.props)
        after_sets = deepcopy(self.project.sets)
        after_dot_selection = self.field.selected_dot_ids()
        after_prop_selection = self.field.selected_prop_ids()
        if before_dots == after_dots and before_props == after_props and before_sets == after_sets:
            return
        self.apply_project_content(
            before_dots,
            before_props,
            before_sets,
            before_dot_selection,
            before_prop_selection,
        )
        self.undo_stack.push(
            ProjectContentCommand(
                self,
                before_dots,
                after_dots,
                before_props,
                after_props,
                before_sets,
                after_sets,
                before_dot_selection,
                after_dot_selection,
                before_prop_selection,
                after_prop_selection,
                label,
            )
        )

    def apply_project_content(
        self,
        dots: list[Dot],
        props: list[Prop],
        sets: list[DrillSet],
        dot_selection: list[str] | None = None,
        prop_selection: list[str] | None = None,
    ) -> None:
        if not sets:
            return
        self.project.dots = deepcopy(dots)
        self.project.props = deepcopy(props)
        self.project.sets = deepcopy(sets)
        self.project.ensure_set_positions()
        self.set_index = max(0, min(self.set_index, len(self.project.sets) - 1))
        drill_set = self.current_set()
        self.current_count = max(drill_set.start_count, min(self.current_count, drill_set.end_count))
        self.field.clear_preview()
        self.field.clear_paths()
        self.field.set_project(self.project, self.project_dir)
        self.sync_drill_grid_controls()
        for item in self.field.scene.selectedItems():
            item.setSelected(False)
        for dot_id in dot_selection or []:
            item = self.field.dot_items.get(dot_id)
            if item:
                item.setSelected(True)
        for prop_id in prop_selection or []:
            item = self.field.prop_items.get(prop_id)
            if item:
                item.setSelected(True)
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=False)
        self.refresh_marcher_table()
        self.refresh_prop_table()
        self.refresh_visibility_filters()
        self.refresh_appearance_groups()
        self.refresh_constraints()
        self.refresh_timing_events()
        self.refresh_selected_paths()
        self.selection_changed()
        self.schedule_live_conflict_analysis()

    def apply_workflow_state(
        self,
        dots: list[Dot],
        sets: list[DrillSet],
        constraints: list[DotConstraint],
        selected_ids: list[str],
        workflow: dict[str, Any] | None = None,
    ) -> None:
        if not sets:
            return
        self.project.dots = deepcopy(dots)
        self.project.sets = deepcopy(sets)
        self.project.constraints = deepcopy(constraints)
        if workflow is not None:
            self.project.workflow = deepcopy(workflow)
        self.project.ensure_set_positions()
        self.set_index = max(0, min(self.set_index, len(self.project.sets) - 1))
        drill_set = self.current_set()
        self.current_count = max(drill_set.start_count, min(self.current_count, drill_set.end_count))
        self.field.clear_preview()
        self.field.clear_paths()
        self.field.set_project(self.project, self.project_dir)
        self.sync_drill_grid_controls()
        for dot_id, item in self.field.dot_items.items():
            item.setSelected(dot_id in selected_ids)
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=False)
        self.refresh_marcher_table()
        self.refresh_visibility_filters()
        self.refresh_appearance_groups()
        self.refresh_constraints()
        self.refresh_lock_controls()
        self.apply_locks_to_field()
        self.refresh_selected_paths()
        self.selection_changed()
        self.schedule_live_conflict_analysis()

    def apply_workflow_metadata(self, workflow: dict[str, Any]) -> None:
        self.project.workflow = deepcopy(workflow)
        self.formation_assignment_cache.clear()
        self.sync_drill_grid_controls()
        self.refresh_selection_sets()
        self.refresh_lock_controls()
        self.apply_locks_to_field()
        self.refresh_visibility_filters()
        self.refresh_selected_paths()
        self.schedule_live_conflict_analysis()
        if self.field.active_tool != EditorTool.SELECT:
            self.update_formation_preview()

    def normalized_count_key(self, count: float | None = None) -> float:
        return round(self.current_count if count is None else count, 2)

    def apply_count_keyframes(
        self,
        set_index: int,
        count: float,
        positions: dict[str, tuple[float, float] | None],
        push_undo: bool = True,
    ) -> None:
        count_key = round(count, 2)
        drill_set = self.project.sets[set_index]
        before: dict[str, tuple[float, float] | None] = {}
        for dot_id in positions:
            before[dot_id] = drill_set.count_positions.get(dot_id, {}).get(count_key)
        if push_undo:
            self.undo_stack.push(
                KeyframeDotsCommand(
                    self,
                    set_index,
                    count_key,
                    before,
                    positions,
                    "Edit Count Keyframes",
                )
            )
            return

        for dot_id, position in positions.items():
            keyframes = drill_set.count_positions.setdefault(dot_id, {})
            if position is None:
                keyframes.pop(count_key, None)
            else:
                keyframes[count_key] = position
            if not keyframes:
                drill_set.count_positions.pop(dot_id, None)
        if set_index == self.set_index:
            self.set_count(self.current_count, seek_audio=False)
            self.refresh_selected_paths()
            self.schedule_live_conflict_analysis()

    def store_micro_edit_positions(self, positions: dict[str, tuple[float, float]]) -> None:
        count_key = self.normalized_count_key()
        drill_set = self.current_set()
        if count_key <= drill_set.start_count or count_key >= drill_set.end_count:
            self.apply_positions({**self.current_positions(), **positions})
            return
        self.apply_count_keyframes(self.set_index, count_key, positions)
        self.statusBar().showMessage(f"Stored keyframe at count {count_key:g}", 2000)

    def add_micro_keyframe(self) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            return
        positions = {
            dot_id: self.field.scene_to_field(self.field.dot_items[dot_id].pos())
            for dot_id in ids
            if dot_id in self.field.dot_items
        }
        self.store_micro_edit_positions(positions)

    def clear_micro_keyframe(self) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            return
        count_key = self.normalized_count_key()
        self.apply_count_keyframes(self.set_index, count_key, {dot_id: None for dot_id in ids})
        self.statusBar().showMessage(f"Cleared keyframe at count {count_key:g}", 2000)

    def selected_positions(self) -> tuple[list[str], list[tuple[float, float]]]:
        ids = self.ordered_selected_dot_ids()
        positions = [self.current_set().dot_positions[dot_id] for dot_id in ids]
        return ids, positions

    def positions_center(self, positions: list[tuple[float, float]]) -> tuple[float, float]:
        if not positions:
            return 0.0, 0.0
        return (
            sum(x for x, _y in positions) / len(positions),
            sum(y for _x, y in positions) / len(positions),
        )

    def preview_center_for_positions(self, positions: list[tuple[float, float]]) -> tuple[float, float]:
        center_x, center_y = self.positions_center(positions)
        offset_x, offset_y = self.preview_center_offset
        return center_x + offset_x, center_y + offset_y

    def shifted_preview_positions(self, positions: list[tuple[float, float]]) -> list[tuple[float, float]]:
        offset_x, offset_y = self.preview_center_offset
        if abs(offset_x) < 0.001 and abs(offset_y) < 0.001:
            return positions
        return [(x + offset_x, y + offset_y) for x, y in positions]

    def ordered_selected_dot_ids(self) -> list[str]:
        ids = self.field.selected_dot_ids()
        positions = [(dot_id, self.current_set().dot_positions[dot_id]) for dot_id in ids]
        if len(positions) < 2:
            return ids
        spread_x = max(x for _dot_id, (x, _y) in positions) - min(x for _dot_id, (x, _y) in positions)
        spread_y = max(y for _dot_id, (_x, y) in positions) - min(y for _dot_id, (_x, y) in positions)
        if spread_x >= spread_y:
            positions.sort(key=lambda item: (item[1][0], item[1][1]))
        else:
            positions.sort(key=lambda item: (item[1][1], item[1][0]))
        return [dot_id for dot_id, _position in positions]

    def formation_targets(self, tool: EditorTool) -> dict[str, tuple[float, float]]:
        if tool == EditorTool.PLUGIN_FORM:
            return self.snap_form_mapping_to_grid(self.plugin_formation_targets())
        ids, positions = self.selected_positions()
        if len(ids) < 2 and tool not in (EditorTool.SCATTER, EditorTool.MIRROR):
            return {}
        if not ids:
            return {}
        center_x, center_y = self.preview_center_for_positions(positions)
        offset_x, offset_y = self.preview_center_offset
        shifted_positions = self.shifted_preview_positions(positions)
        filled_shape = self.shape_fill_mode.currentText().lower() == "solid"
        if tool == EditorTool.LINE:
            if len(self.line_endpoints) != 2:
                self.line_endpoints = [positions[0], positions[-1]]
            new_positions = line_positions(
                len(ids),
                (self.line_endpoints[0][0] + offset_x, self.line_endpoints[0][1] + offset_y),
                (self.line_endpoints[1][0] + offset_x, self.line_endpoints[1][1] + offset_y),
            )
        elif tool == EditorTool.CURVE:
            if not self.curve_handles:
                self.initialize_curve_tool(positions)
            handles = self.offset_curve_handles(offset_x, offset_y)
            new_positions = bezier_curve_positions(
                len(ids),
                handles["curve_start"],
                handles["curve_control_1"],
                handles["curve_control_2"],
                handles["curve_end"],
            )
        elif tool == EditorTool.FREE_CURVE:
            if len(self.free_curve_anchors) != int(self.free_curve_anchor_count.value()):
                self.initialize_free_curve_tool(positions)
            anchors = [
                (anchor_x + offset_x, anchor_y + offset_y)
                for anchor_x, anchor_y in self.free_curve_anchors
            ]
            new_positions = freeform_curve_positions(
                len(ids),
                anchors,
                closed=self.free_curve_closed.isChecked(),
                curved=self.free_curve_curved.isChecked(),
            )
        elif tool == EditorTool.ARC:
            new_positions = elliptical_arc_positions(
                len(ids),
                (center_x, center_y),
                self.arc_width.value(),
                self.arc_height.value(),
                self.arc_start_angle.value(),
                self.arc_sweep.value(),
                self.arc_rotation.value(),
            )
        elif tool == EditorTool.CIRCLE:
            new_positions = circle_positions(
                len(ids),
                (center_x, center_y),
                self.shape_radius.value(),
                filled=filled_shape,
            )
        elif tool == EditorTool.ELLIPSE:
            new_positions = ellipse_positions(
                len(ids),
                (center_x, center_y),
                self.shape_width.value(),
                self.shape_height.value(),
                filled=filled_shape,
            )
        elif tool == EditorTool.RECTANGLE:
            new_positions = rectangle_positions(
                len(ids),
                (center_x, center_y),
                self.shape_width.value(),
                self.shape_height.value(),
                filled=filled_shape,
            )
        elif tool == EditorTool.TRIANGLE:
            new_positions = triangle_positions(
                len(ids),
                (center_x, center_y),
                self.shape_width.value(),
                self.shape_height.value(),
                filled=filled_shape,
            )
        elif tool == EditorTool.DIAMOND:
            new_positions = polygon_positions(
                len(ids),
                (center_x, center_y),
                min(self.shape_width.value(), self.shape_height.value()) / 2,
                4,
                rotation_degrees=-90,
                filled=filled_shape,
            )
            if self.shape_width.value() != self.shape_height.value():
                base = min(self.shape_width.value(), self.shape_height.value()) or 1
                new_positions = [
                    (
                        center_x + (x - center_x) * self.shape_width.value() / base,
                        center_y + (y - center_y) * self.shape_height.value() / base,
                    )
                    for x, y in new_positions
                ]
        elif tool == EditorTool.POLYGON:
            new_positions = polygon_positions(
                len(ids),
                (center_x, center_y),
                self.shape_radius.value(),
                self.polygon_sides.value(),
                filled=filled_shape,
            )
        elif tool == EditorTool.STAR:
            new_positions = star_positions(
                len(ids),
                (center_x, center_y),
                self.shape_radius.value(),
                self.shape_radius.value() * self.star_inner_percent.value() / 100,
                self.star_points.value(),
                filled=filled_shape,
            )
        elif tool == EditorTool.SPIRAL:
            new_positions = spiral_positions(
                len(ids),
                (center_x, center_y),
                self.shape_radius.value(),
                self.spiral_turns.value(),
            )
        elif tool == EditorTool.BLOCK:
            new_positions = block_positions(
                len(ids),
                (center_x, center_y),
                self.block_columns.value(),
                self.block_spacing.value(),
            )
        elif tool == EditorTool.SVG_SHAPE:
            if not self.imported_shape_points and not self.imported_shape_contours:
                return {}
            if self.imported_shape_contours:
                scaled_contours = [
                    [
                        (
                            center_x + point[0] * self.shape_width.value(),
                            center_y + point[1] * self.shape_height.value(),
                        )
                        for point in contour
                    ]
                    for contour in self.imported_shape_contours
                ]
                if filled_shape:
                    new_positions = relax_close_positions(
                        solid_paths_positions(scaled_contours, len(ids)),
                        self.svg_min_spacing.value(),
                    )
                else:
                    new_positions = positions_along_paths_spaced(
                        scaled_contours,
                        len(ids),
                        self.svg_min_spacing.value(),
                    )
            else:
                scaled_path = [
                    (
                        center_x + point[0] * self.shape_width.value(),
                        center_y + point[1] * self.shape_height.value(),
                    )
                    for point in self.imported_shape_points
                ]
                if filled_shape:
                    new_positions = relax_close_positions(
                        solid_paths_positions([scaled_path], len(ids)),
                        self.svg_min_spacing.value(),
                    )
                else:
                    new_positions = positions_along_paths_spaced(
                        [scaled_path],
                        len(ids),
                        self.svg_min_spacing.value(),
                    )
        elif tool == EditorTool.SCALE:
            pivot = self.preview_transform_pivot or self.positions_center(positions)
            preview_pivot = (pivot[0] + offset_x, pivot[1] + offset_y)
            new_positions = scaled_positions_to_size(
                shifted_positions,
                self.scale_width.value(),
                self.scale_height.value(),
                self.scale_lock_aspect.isChecked(),
                preview_pivot,
            )
        elif tool == EditorTool.ROTATE:
            pivot = self.preview_transform_pivot or self.positions_center(positions)
            preview_pivot = (pivot[0] + offset_x, pivot[1] + offset_y)
            new_positions = rotate_positions(
                shifted_positions,
                self.rotation_degrees.value(),
                preview_pivot,
            )
        elif tool == EditorTool.WARP:
            if len(self.warp_anchors) != int(self.warp_anchor_count.value()):
                self.initialize_warp_tool(positions)
            anchors = [
                (anchor_x + offset_x, anchor_y + offset_y)
                for anchor_x, anchor_y in self.warp_anchors
            ]
            new_positions = warped_positions(shifted_positions, anchors, self.warp_strength.value())
        elif tool == EditorTool.SCATTER:
            new_positions = scatter_positions(
                shifted_positions,
                self.scatter_radius.value(),
                shape=self.scatter_shape.currentText(),
                min_spacing=self.scatter_spacing.value(),
            )
        elif tool == EditorTool.MIRROR:
            new_positions = mirror_positions(positions, "vertical", self.mirror_axis)
        elif tool == EditorTool.SHAPE_LINE:
            if len(ids) < 2:
                return {}
            anchors = self.current_shape_line_anchors(ids, positions)
            path = sampled_shape_path(anchors, self.shape_line_curved.isChecked())
            new_positions = positions_along_path(path, len(ids))
        else:
            return {}
        new_positions = self.snap_form_positions_to_grid(new_positions)
        preserve_order = tool in {
            EditorTool.SCALE,
            EditorTool.ROTATE,
            EditorTool.WARP,
            EditorTool.MIRROR,
        }
        closed_order = tool in {
            EditorTool.CIRCLE,
            EditorTool.ELLIPSE,
            EditorTool.RECTANGLE,
            EditorTool.TRIANGLE,
            EditorTool.DIAMOND,
            EditorTool.POLYGON,
            EditorTool.STAR,
        } and not filled_shape
        if tool == EditorTool.FREE_CURVE and self.free_curve_closed.isChecked():
            closed_order = True
        return self.assign_targets_to_marchers(
            ids,
            new_positions,
            preserve_order=preserve_order,
            closed_order=closed_order,
        )

    def snap_form_positions_to_grid(
        self,
        positions: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        if not self.field.drill_grid.enabled:
            return positions
        return snap_positions_to_grid(
            positions,
            self.field.drill_grid,
            unique=True,
            reference_y=self.field.drill_grid_reference_rows(),
        )

    def snap_form_mapping_to_grid(
        self,
        positions: dict[str, tuple[float, float]],
    ) -> dict[str, tuple[float, float]]:
        if not positions or not self.field.drill_grid.enabled:
            return positions
        return snap_position_mapping(
            positions,
            self.field.drill_grid,
            reference_y=self.field.drill_grid_reference_rows(),
        )

    def assign_targets_to_marchers(
        self,
        ids: list[str],
        targets: list[tuple[float, float]],
        preserve_order: bool = False,
        closed_order: bool = False,
    ) -> dict[str, tuple[float, float]]:
        if len(ids) != len(targets):
            return {dot_id: targets[index] for index, dot_id in enumerate(ids[: len(targets)])}
        strategy = (
            str(self.assignment_strategy_combo.currentData() or "automatic")
            if hasattr(self, "assignment_strategy_combo")
            else "automatic"
        )
        if strategy == "automatic" and preserve_order:
            return {dot_id: targets[index] for index, dot_id in enumerate(ids)}
        if strategy in {"automatic", "lowest_collision"}:
            starts_source = self.current_transition_start_positions()
            start_signature = tuple(
                (
                    dot_id,
                    round(starts_source.get(dot_id, self.current_set().dot_positions[dot_id])[0], 3),
                    round(starts_source.get(dot_id, self.current_set().dot_positions[dot_id])[1], 3),
                )
                for dot_id in ids
            )
            topology = (
                self.field.active_tool.value,
                self.active_plugin_form_tool_id,
                bool(closed_order),
                self.scatter_shape.currentText() if hasattr(self, "scatter_shape") else "",
                self.imported_shape_name if self.field.active_tool == EditorTool.SVG_SHAPE else "",
            )
            cache_key = (
                self.set_index,
                tuple(ids),
                strategy,
                topology,
                start_signature,
                round(self.min_spacing.value() if hasattr(self, "min_spacing") else 1.25, 3),
                round(self.max_yards_per_count.value() if hasattr(self, "max_yards_per_count") else 4.0, 3),
            )
            assignment = self.formation_assignment_cache.get(cache_key)
            if assignment is None or len(assignment) != len(targets):
                assignment = collision_aware_assignment_for_project(
                    self.project,
                    self.set_index,
                    ids,
                    targets,
                    min_spacing=self.min_spacing.value() if hasattr(self, "min_spacing") else 1.25,
                    max_yards_per_count=(
                        self.max_yards_per_count.value()
                        if hasattr(self, "max_yards_per_count")
                        else 4.0
                    ),
                )
                self.formation_assignment_cache[cache_key] = assignment
                quality = project_assignment_quality(
                    self.project,
                    self.set_index,
                    ids,
                    targets,
                    assignment,
                    min_spacing=self.min_spacing.value() if hasattr(self, "min_spacing") else 1.25,
                    max_yards_per_count=(
                        self.max_yards_per_count.value()
                        if hasattr(self, "max_yards_per_count")
                        else 4.0
                    ),
                )
                if quality.collisions:
                    self.statusBar().showMessage(
                        f"Collision-safe assignment found {quality.collisions} unresolved spacing conflict(s). "
                        "The fixed start/destination pictures or surrounding marchers may make them unavoidable.",
                        5200,
                    )
                else:
                    self.statusBar().showMessage(
                        f"Collision-safe assignment: 0 synchronized spacing conflicts, "
                        f"{quality.total_distance:.1f} yd total travel.",
                        2800,
                    )
                while len(self.formation_assignment_cache) > 24:
                    self.formation_assignment_cache.pop(next(iter(self.formation_assignment_cache)))
            return {
                dot_id: targets[assignment[index]]
                for index, dot_id in enumerate(ids)
            }
        return assignment_for_mode(
            self.project,
            self.set_index,
            ids,
            targets,
            strategy,
            min_spacing=self.min_spacing.value() if hasattr(self, "min_spacing") else 1.25,
            max_yards_per_count=(
                self.max_yards_per_count.value()
                if hasattr(self, "max_yards_per_count")
                else 4.0
            ),
        )

    def formation_handles(self, tool: EditorTool) -> dict[str, tuple[float, float]]:
        if tool == EditorTool.PLUGIN_FORM:
            return self.plugin_formation_handles()
        _ids, positions = self.selected_positions()
        if len(positions) < 2:
            return {}
        center_x, center_y = self.preview_center_for_positions(positions)
        offset_x, offset_y = self.preview_center_offset
        handles: dict[str, tuple[float, float]] = {}
        if tool not in (EditorTool.MIRROR, EditorTool.SHAPE_LINE):
            handles["form_center"] = (center_x, center_y)
        if tool == EditorTool.LINE:
            if len(self.line_endpoints) != 2:
                self.line_endpoints = [positions[0], positions[-1]]
            handles.update(
                {
                    "line_start": (self.line_endpoints[0][0] + offset_x, self.line_endpoints[0][1] + offset_y),
                    "line_end": (self.line_endpoints[1][0] + offset_x, self.line_endpoints[1][1] + offset_y),
                }
            )
            return handles
        if tool == EditorTool.CURVE:
            if not self.curve_handles:
                self.initialize_curve_tool(positions)
            handles.update(self.curve_on_form_handles(offset_x, offset_y))
            return handles
        if tool == EditorTool.FREE_CURVE:
            if len(self.free_curve_anchors) != int(self.free_curve_anchor_count.value()):
                self.initialize_free_curve_tool(positions)
            handles.update(
                {
                    f"free_curve_anchor:{index}": (anchor_x + offset_x, anchor_y + offset_y)
                    for index, (anchor_x, anchor_y) in enumerate(self.free_curve_anchors)
                }
            )
            return handles
        if tool == EditorTool.ARC:
            start_angle = self.arc_start_angle.value()
            end_angle = start_angle + self.arc_sweep.value()
            handles.update(
                {
                    "arc_width": (center_x + cos(pi * self.arc_rotation.value() / 180) * self.arc_width.value() / 2, center_y + sin(pi * self.arc_rotation.value() / 180) * self.arc_width.value() / 2),
                    "arc_height": (center_x - sin(pi * self.arc_rotation.value() / 180) * self.arc_height.value() / 2, center_y + cos(pi * self.arc_rotation.value() / 180) * self.arc_height.value() / 2),
                    "arc_start": self.arc_point(center_x, center_y, start_angle),
                    "arc_end": self.arc_point(center_x, center_y, end_angle),
                }
            )
            return handles
        if tool == EditorTool.SHAPE_LINE:
            ids, positions = self.selected_positions()
            return {
                f"shape_anchor:{dot_id}": anchor
                for dot_id, anchor in self.current_shape_line_anchor_items(ids, positions)
            }
        if tool in (EditorTool.CIRCLE, EditorTool.POLYGON, EditorTool.STAR, EditorTool.SPIRAL):
            handles["shape_radius"] = (center_x + self.shape_radius.value(), center_y)
            return handles
        if tool in (EditorTool.ELLIPSE, EditorTool.RECTANGLE, EditorTool.TRIANGLE, EditorTool.DIAMOND, EditorTool.SVG_SHAPE):
            handles.update(
                {
                    "shape_width": (center_x + self.shape_width.value() / 2, center_y),
                    "shape_height": (center_x, center_y + self.shape_height.value() / 2),
                }
            )
            return handles
        if tool == EditorTool.BLOCK:
            handles["block_spacing"] = (center_x + self.block_spacing.value(), center_y)
            return handles
        if tool == EditorTool.SCALE:
            pivot = self.preview_transform_pivot or self.positions_center(positions)
            handles["transform_pivot"] = (pivot[0] + offset_x, pivot[1] + offset_y)
            handles.update(
                {
                    "scale_width": (center_x + self.scale_width.value() / 2, center_y),
                    "scale_height": (center_x, center_y + self.scale_height.value() / 2),
                }
            )
            return handles
        if tool == EditorTool.ROTATE:
            pivot = self.preview_transform_pivot or self.positions_center(positions)
            handles["transform_pivot"] = (pivot[0] + offset_x, pivot[1] + offset_y)
            radius = max(
                5.0,
                max((((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5 for x, y in positions), default=5.0),
            )
            angle = self.rotation_degrees.value() * pi / 180
            handles["rotate_angle"] = (
                pivot[0] + offset_x + cos(angle) * radius,
                pivot[1] + offset_y + sin(angle) * radius,
            )
            return handles
        if tool == EditorTool.WARP:
            if len(self.warp_anchors) != int(self.warp_anchor_count.value()):
                self.initialize_warp_tool(positions)
            handles.update(
                {
                    f"warp_anchor:{index}": (anchor_x + offset_x, anchor_y + offset_y)
                    for index, (anchor_x, anchor_y) in enumerate(self.warp_anchors)
                }
            )
            return handles
        if tool == EditorTool.SCATTER:
            handles["scatter_radius"] = (center_x + self.scatter_radius.value(), center_y)
            return handles
        if tool == EditorTool.MIRROR:
            return {"mirror_axis": (self.mirror_axis, center_y)}
        return {}

    def update_formation_preview(self) -> None:
        if self.field.active_tool == EditorTool.SELECT and not self.active_plugin_form_tool_id:
            self.field.clear_preview()
            return
        targets = self.formation_targets(self.field.active_tool)
        if self.field.active_tool == EditorTool.SHAPE_LINE:
            ids, positions = self.selected_positions()
            anchor_items = self.current_shape_line_anchor_items(ids, positions)
            anchors = [position for _dot_id, position in anchor_items]
            path = sampled_shape_path(anchors, self.shape_line_curved.isChecked())
            self.field.show_shape_line_preview(path, anchor_items, targets)
            return
        transition_starts = self.current_transition_start_positions()
        starts = {
            dot_id: transition_starts.get(dot_id, self.current_set().dot_positions[dot_id])
            for dot_id in targets
        }
        if self.field.active_tool == EditorTool.FREE_CURVE:
            _ids, positions = self.selected_positions()
            if len(self.free_curve_anchors) != int(self.free_curve_anchor_count.value()):
                self.initialize_free_curve_tool(positions)
            offset_x, offset_y = self.preview_center_offset
            anchors = [
                (anchor_x + offset_x, anchor_y + offset_y)
                for anchor_x, anchor_y in self.free_curve_anchors
            ]
            path = sampled_spline_path(
                anchors,
                curved=self.free_curve_curved.isChecked(),
                closed=self.free_curve_closed.isChecked(),
            )
            self.field.show_curve_path_preview(path, starts, targets, self.formation_handles(EditorTool.FREE_CURVE))
            return
        if self.field.active_tool == EditorTool.CURVE:
            _ids, positions = self.selected_positions()
            if not self.curve_handles:
                self.initialize_curve_tool(positions)
            handles = self.offset_curve_handles(*self.preview_center_offset)
            path = sampled_cubic_bezier_path(
                handles["curve_start"],
                handles["curve_control_1"],
                handles["curve_control_2"],
                handles["curve_end"],
            )
            self.field.show_curve_path_preview(path, starts, targets, self.formation_handles(EditorTool.CURVE))
            return
        if self.field.active_tool == EditorTool.ARC:
            _ids, positions = self.selected_positions()
            center_x, center_y = self.preview_center_for_positions(positions)
            path = elliptical_arc_path(
                (center_x, center_y),
                self.arc_width.value(),
                self.arc_height.value(),
                self.arc_start_angle.value(),
                self.arc_sweep.value(),
                self.arc_rotation.value(),
            )
            self.field.show_curve_path_preview(path, starts, targets, self.formation_handles(EditorTool.ARC))
            return
        self.field.show_preview(starts, targets, self.formation_handles(self.field.active_tool))

    def preview_handle_moved(
        self,
        kind: str,
        x: float,
        y: float,
        modifiers: int = 0,
        commit: bool = True,
    ) -> None:
        if self.move_motion_ribbon_handle(kind, x, y, modifiers, commit):
            return
        shift = bool(modifiers & int(Qt.KeyboardModifier.ShiftModifier.value))
        alt = bool(modifiers & int(Qt.KeyboardModifier.AltModifier.value))
        if kind.startswith("plugin_setting:"):
            if self.update_plugin_setting_from_handle(kind.split(":", 1)[1], x, y):
                self.update_formation_preview()
            return
        _ids, positions = self.selected_positions()
        if len(positions) < 2:
            return
        base_center_x, base_center_y = self.positions_center(positions)
        offset_x, offset_y = self.preview_center_offset
        center_x, center_y = base_center_x + offset_x, base_center_y + offset_y
        if kind == "form_center":
            self.preview_center_offset = (x - base_center_x, y - base_center_y)
        elif kind == "transform_pivot":
            self.preview_transform_pivot = (x - offset_x, y - offset_y)
        elif kind == "curve_bend":
            self.curve_bend.setValue(y - center_y)
        elif kind in {"curve_start", "curve_end"}:
            if not self.curve_handles:
                self.initialize_curve_tool(positions)
            self.curve_handles[kind] = (x - offset_x, y - offset_y)
            if alt:
                opposite_names = {
                    "curve_start": "curve_end",
                    "curve_end": "curve_start",
                    "curve_control_1": "curve_control_2",
                    "curve_control_2": "curve_control_1",
                }
                opposite = opposite_names[kind]
                self.curve_handles[opposite] = (
                    center_x * 2 - x - offset_x,
                    center_y * 2 - y - offset_y,
                )
        elif kind in {"curve_on_1", "curve_on_2"}:
            if not self.curve_handles:
                self.initialize_curve_tool(positions)
            on_form = self.curve_on_form_handles(0.0, 0.0)
            point_1 = on_form["curve_on_1"]
            point_2 = on_form["curve_on_2"]
            dragged = (x - offset_x, y - offset_y)
            if kind == "curve_on_1":
                point_1 = dragged
                if alt:
                    point_2 = (base_center_x * 2 - dragged[0], base_center_y * 2 - dragged[1])
            else:
                point_2 = dragged
                if alt:
                    point_1 = (base_center_x * 2 - dragged[0], base_center_y * 2 - dragged[1])
            self.set_curve_on_form_points(point_1, point_2)
        elif kind.startswith("free_curve_anchor:"):
            try:
                index = int(kind.split(":", 1)[1])
            except ValueError:
                return
            if 0 <= index < len(self.free_curve_anchors):
                self.free_curve_anchors[index] = (x - offset_x, y - offset_y)
                if alt:
                    opposite_index = len(self.free_curve_anchors) - 1 - index
                    self.free_curve_anchors[opposite_index] = (
                        center_x * 2 - x - offset_x,
                        center_y * 2 - y - offset_y,
                    )
        elif kind == "line_start":
            if len(self.line_endpoints) != 2:
                self.line_endpoints = [positions[0], positions[-1]]
            self.line_endpoints[0] = (x - offset_x, y - offset_y)
            if alt:
                self.line_endpoints[1] = (
                    center_x * 2 - x - offset_x,
                    center_y * 2 - y - offset_y,
                )
        elif kind == "line_end":
            if len(self.line_endpoints) != 2:
                self.line_endpoints = [positions[0], positions[-1]]
            self.line_endpoints[1] = (x - offset_x, y - offset_y)
            if alt:
                self.line_endpoints[0] = (
                    center_x * 2 - x - offset_x,
                    center_y * 2 - y - offset_y,
                )
        elif kind == "arc_radius":
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            self.arc_radius.setValue(max(1, distance))
            self.arc_width.setValue(max(1, distance * 2))
            self.arc_height.setValue(max(1, distance * 2))
        elif kind == "arc_width":
            aspect = self.arc_height.value() / max(0.001, self.arc_width.value())
            new_width = max(1, ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5 * 2)
            self.arc_width.setValue(new_width)
            if shift:
                self.arc_height.setValue(max(1, new_width * aspect))
            self.arc_rotation.setValue(degrees(atan2(y - center_y, x - center_x)))
        elif kind == "arc_height":
            aspect = self.arc_width.value() / max(0.001, self.arc_height.value())
            new_height = max(1, ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5 * 2)
            self.arc_height.setValue(new_height)
            if shift:
                self.arc_width.setValue(max(1, new_height * aspect))
            self.arc_rotation.setValue(degrees(atan2(y - center_y, x - center_x)) - 90)
        elif kind == "arc_start":
            angle = self.arc_angle_from_point(center_x, center_y, x, y)
            self.arc_start_angle.setValue(round(angle / 15) * 15 if shift else angle)
        elif kind == "arc_end":
            end_angle = self.arc_angle_from_point(center_x, center_y, x, y)
            if shift:
                end_angle = round(end_angle / 15) * 15
            self.arc_sweep.setValue(self.signed_angle_delta(self.arc_start_angle.value(), end_angle, self.arc_sweep.value()))
        elif kind == "arc_sweep":
            distance = abs(x - center_x)
            radius = max(1, self.arc_width.value() / 2)
            self.arc_sweep.setValue(max(10, min(360, distance / radius * 180)))
        elif kind.startswith("shape_anchor:"):
            dot_id = kind.split(":", 1)[1]
            self.shape_line_anchor_positions[dot_id] = (x, y)
            if alt:
                anchor_ids = [
                    selected_id
                    for selected_id in _ids
                    if selected_id in self.shape_line_anchor_dot_ids
                ]
                if dot_id in anchor_ids:
                    opposite_id = anchor_ids[len(anchor_ids) - 1 - anchor_ids.index(dot_id)]
                    self.shape_line_anchor_positions[opposite_id] = (
                        center_x * 2 - x,
                        center_y * 2 - y,
                    )
        elif kind == "shape_radius":
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            self.shape_radius.setValue(max(1, distance))
        elif kind == "shape_width":
            aspect = self.shape_height.value() / max(0.001, self.shape_width.value())
            new_width = max(1, abs(x - center_x) * 2)
            self.shape_width.setValue(new_width)
            if shift:
                self.shape_height.setValue(max(1, new_width * aspect))
        elif kind == "shape_height":
            aspect = self.shape_width.value() / max(0.001, self.shape_height.value())
            new_height = max(1, abs(y - center_y) * 2)
            self.shape_height.setValue(new_height)
            if shift:
                self.shape_width.setValue(max(1, new_height * aspect))
        elif kind == "block_spacing":
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            self.block_spacing.setValue(max(0.25, distance))
        elif kind == "scale_width":
            aspect = self.scale_height.value() / max(0.001, self.scale_width.value())
            new_width = max(0.1, abs(x - center_x) * 2)
            self.scale_width.setValue(new_width)
            if shift:
                self.scale_height.setValue(max(0.1, new_width * aspect))
        elif kind == "scale_height":
            aspect = self.scale_width.value() / max(0.001, self.scale_height.value())
            new_height = max(0.1, abs(y - center_y) * 2)
            self.scale_height.setValue(new_height)
            if shift:
                self.scale_width.setValue(max(0.1, new_height * aspect))
        elif kind == "rotate_angle":
            pivot = self.preview_transform_pivot or (base_center_x, base_center_y)
            pivot_x, pivot_y = pivot[0] + offset_x, pivot[1] + offset_y
            angle = degrees(atan2(y - pivot_y, x - pivot_x))
            self.rotation_degrees.setValue(round(angle / 15) * 15 if shift else angle)
        elif kind.startswith("warp_anchor:"):
            try:
                index = int(kind.split(":", 1)[1])
            except ValueError:
                return
            if 0 <= index < len(self.warp_anchors):
                self.warp_anchors[index] = (x - offset_x, y - offset_y)
                if alt:
                    opposite_index = len(self.warp_anchors) - 1 - index
                    self.warp_anchors[opposite_index] = (
                        center_x * 2 - x - offset_x,
                        center_y * 2 - y - offset_y,
                    )
        elif kind == "scatter_radius":
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            self.scatter_radius.setValue(max(0, distance))
        elif kind == "mirror_axis":
            self.mirror_axis = x
        self.update_formation_preview()

    def import_svg_shape(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import SVG Shape",
            str(Path.home()),
            "SVG Files (*.svg)",
        )
        if not path:
            return
        try:
            self.imported_shape_contours = load_svg_contours(Path(path))
            self.formation_assignment_cache.clear()
            self.imported_shape_points = [
                point
                for contour in self.imported_shape_contours
                for point in contour
            ]
        except Exception as exc:
            QMessageBox.warning(self, "SVG Import Failed", str(exc))
            return
        self.imported_shape_name = Path(path).name
        self.svg_shape_label.setText(
            f"{self.imported_shape_name} ({len(self.imported_shape_points)} pts, {len(self.imported_shape_contours)} shape(s))"
        )
        self.set_tool(EditorTool.SVG_SHAPE)

    def initialize_shape_line_anchors(self, ids: list[str], positions: list[tuple[float, float]]) -> None:
        self.shape_line_anchor_dot_ids.clear()
        self.shape_line_anchor_positions.clear()
        if len(ids) < 2:
            self.shape_line_anchors = []
            return
        for dot_id, position in ((ids[0], positions[0]), (ids[-1], positions[-1])):
            self.shape_line_anchor_dot_ids.add(dot_id)
            self.shape_line_anchor_positions[dot_id] = position
        self.shape_line_anchors = self.current_shape_line_anchors(ids, positions)

    def current_shape_line_anchor_items(
        self,
        ids: list[str],
        positions: list[tuple[float, float]],
    ) -> list[tuple[str, tuple[float, float]]]:
        if len(ids) < 2:
            return []
        valid_ids = set(ids)
        self.shape_line_anchor_dot_ids.intersection_update(valid_ids)
        self.shape_line_anchor_dot_ids.update({ids[0], ids[-1]})
        position_by_id = dict(zip(ids, positions))
        items: list[tuple[str, tuple[float, float]]] = []
        for dot_id in ids:
            if dot_id in self.shape_line_anchor_dot_ids:
                self.shape_line_anchor_positions.setdefault(dot_id, position_by_id[dot_id])
                items.append((dot_id, self.shape_line_anchor_positions[dot_id]))
        return items

    def current_shape_line_anchors(
        self,
        ids: list[str],
        positions: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        self.shape_line_anchors = [
            position
            for _dot_id, position in self.current_shape_line_anchor_items(ids, positions)
        ]
        return self.shape_line_anchors

    def toggle_shape_line_anchor(self, dot_id: str) -> None:
        if self.field.active_tool != EditorTool.SHAPE_LINE:
            return
        ids, positions = self.selected_positions()
        if dot_id not in ids or len(ids) < 2:
            return
        if dot_id in (ids[0], ids[-1]):
            return
        if dot_id in self.shape_line_anchor_dot_ids:
            self.shape_line_anchor_dot_ids.remove(dot_id)
            self.shape_line_anchor_positions.pop(dot_id, None)
        else:
            self.shape_line_anchor_dot_ids.add(dot_id)
            self.shape_line_anchor_positions[dot_id] = self.current_set().dot_positions[dot_id]
        self.update_formation_preview()

    def clear_formation_preview(self) -> None:
        self.preview_center_offset = (0.0, 0.0)
        self.active_motion_ribbon_id = ""
        self._motion_ribbon_drag_before_sets = None
        self.field.set_motion_path_editing(False)
        self.active_plugin_form_tool_id = ""
        for button in self.plugin_form_tool_buttons.values():
            button.setChecked(False)
        self.set_tool(EditorTool.SELECT)
        self.field.clear_preview()

    def apply_current_preview(self) -> None:
        if self.active_plugin_form_tool_id:
            self.apply_active_plugin_form_tool_preview()
            return
        self.apply_formation(self.field.active_tool)

    def remember_formation_edit_descriptor(
        self,
        dot_ids: list[str] | tuple[str, ...] | set[str] | dict[str, Any],
        settings: dict[str, Any],
    ) -> None:
        signature = ",".join(sorted(str(dot_id) for dot_id in dot_ids))
        if not signature:
            return
        bucket = self.workflow_bucket("formation_edit_descriptors")
        for set_index in self.selected_set_indices_for_edit(list(dot_ids)):
            bucket[f"{set_index}:{signature}"] = deepcopy(settings)

    def apply_formation(self, tool: EditorTool) -> None:
        if tool == EditorTool.PLUGIN_FORM:
            self.apply_active_plugin_form_tool_preview()
            return
        repeat_settings = deepcopy(self.current_tool_settings())
        targets = self.formation_targets(tool)
        if not targets:
            return
        targets = self.editable_positions(targets)
        if not targets:
            self.statusBar().showMessage("Selected marchers are locked", 2200)
            return
        before = self.current_positions()
        after = dict(before)
        after.update(targets)
        self.remember_formation_edit_descriptor(targets, repeat_settings)
        if self.editing_set_one_opening():
            self.apply_opening_positions(
                targets,
                sync_unchanged_set_one_endpoints=True,
                label=f"Apply {tool.value.title()}",
            )
            self.field.clear_preview()
            self.preview_center_offset = (0.0, 0.0)
            self.set_tool(EditorTool.SELECT)
            self.refresh_selected_paths()
            self.remember_repeat_action(
                {"type": "formation", "settings": repeat_settings, "label": f"Apply {tool.value.title()}"}
            )
            return
        if len(self.selected_set_indices_for_edit()) > 1:
            self.apply_positions(after)
            self.field.clear_preview()
            self.preview_center_offset = (0.0, 0.0)
            self.set_tool(EditorTool.SELECT)
            self.refresh_selected_paths()
            self.remember_repeat_action({"type": "formation", "settings": repeat_settings, "label": f"Apply {tool.value.title()}"})
            return
        before_anchors = self.clone_path_anchors(self.set_index)
        before_controls = self.clone_path_controls(self.set_index)
        before_counts = self.clone_count_positions(self.set_index)
        after_anchors = self.clone_path_anchors(self.set_index)
        after_controls = self.clone_path_controls(self.set_index)
        after_counts = self.clone_count_positions(self.set_index)
        for dot_id in targets:
            after_anchors.pop(dot_id, None)
            after_controls.pop(dot_id, None)
            after_counts.pop(dot_id, None)

        self.undo_stack.push(
            MoveDotsCommand(
                self,
                self.set_index,
                before,
                after,
                f"Apply {tool.value.title()}",
                before_anchors,
                after_anchors,
                before_controls,
                after_controls,
                before_counts,
                after_counts,
            )
        )
        self.field.clear_preview()
        self.preview_center_offset = (0.0, 0.0)
        self.set_tool(EditorTool.SELECT)
        self.refresh_selected_paths()
        self.remember_repeat_action({"type": "formation", "settings": repeat_settings, "label": f"Apply {tool.value.title()}"})

    def fit_selected_form_to_prop(self) -> None:
        dot_ids, positions = self.selected_positions()
        prop_ids = self.field.selected_prop_ids()
        if len(dot_ids) < 2:
            QMessageBox.information(self, "Scale Form", "Select two or more marchers first.")
            return
        if not prop_ids:
            QMessageBox.information(self, "Scale Form", "Select a prop along with the marchers you want to scale.")
            return

        prop_id = prop_ids[0]
        prop_state = self.current_set().prop_positions.get(prop_id)
        if not prop_state:
            QMessageBox.information(self, "Scale Form", "The selected prop does not have a position in this set.")
            return

        padding = self.scale_fit_padding.value()
        target_width = max(0.1, float(prop_state.get("width", 0.0)) - padding * 2)
        target_height = max(0.1, float(prop_state.get("height", 0.0)) - padding * 2)
        prop_center = (float(prop_state.get("x", 0.0)), float(prop_state.get("y", 0.0)))
        scaled = scaled_positions_to_size(
            positions,
            target_width,
            target_height,
            self.scale_lock_aspect.isChecked(),
        )
        fitted = centered_positions(scaled, prop_center)
        targets = {dot_id: fitted[index] for index, dot_id in enumerate(dot_ids)}
        targets = self.editable_positions(targets)
        if not targets:
            self.statusBar().showMessage("Selected marchers are locked", 2200)
            return

        self.scale_width.blockSignals(True)
        self.scale_height.blockSignals(True)
        self.scale_width.setValue(target_width)
        self.scale_height.setValue(target_height)
        self.scale_width.blockSignals(False)
        self.scale_height.blockSignals(False)

        before = self.current_positions()
        after = dict(before)
        after.update(targets)
        if len(self.selected_set_indices_for_edit()) > 1:
            self.apply_positions(after)
            self.update_formation_preview()
            self.refresh_selected_paths()
            return
        before_anchors = self.clone_path_anchors(self.set_index)
        before_controls = self.clone_path_controls(self.set_index)
        before_counts = self.clone_count_positions(self.set_index)
        after_anchors = self.clone_path_anchors(self.set_index)
        after_controls = self.clone_path_controls(self.set_index)
        after_counts = self.clone_count_positions(self.set_index)
        for dot_id in targets:
            after_anchors.pop(dot_id, None)
            after_controls.pop(dot_id, None)
            after_counts.pop(dot_id, None)

        self.undo_stack.push(
            MoveDotsCommand(
                self,
                self.set_index,
                before,
                after,
                "Fit Form to Prop",
                before_anchors,
                after_anchors,
                before_controls,
                after_controls,
                before_counts,
                after_counts,
            )
        )
        self.update_formation_preview()
        self.update_field_hud_visibility()
        self.refresh_selected_paths()

    def context_action(self, name: str) -> None:
        if name == "Apply Preview":
            self.apply_current_preview()
            return
        if name == "Clear Preview":
            self.clear_formation_preview()
            return
        if name == "Focus Field":
            self.toggle_field_focus()
            return
        if name == "Select Tool":
            self.set_tool(EditorTool.SELECT)
            return
        if name == "Radial Tool Menu":
            self.show_radial_tool_menu()
            return
        if name == "Toggle Transform Handles":
            self.set_transform_gizmo_visible(not self.transform_gizmo_visible())
            return
        if name == "Group Motion Ribbon":
            self.create_group_motion_ribbon()
            return
        if name == "Edit Group Path Handles":
            self.edit_group_path_handles()
            return
        if name == "Formation Morph":
            self.show_formation_morph()
            return
        if name == "Polar / Linear Array":
            self.show_polar_linear_array()
            return
        if name == "Parallel Form Generator":
            self.show_parallel_form_generator()
            return
        if name == "Rank / File Builder":
            self.show_rank_file_builder()
            return
        if name == "Create Live Symmetry":
            self.create_live_symmetry()
            return
        if name == "Alternating Selection":
            self.show_alternating_selection()
            return
        if name == "Toggle Measurements":
            enabled = not self.measurements_enabled
            self.accelerator_panel.measurements_enabled.setChecked(enabled)
            self.set_measurement_overlay(enabled, self.measurement_mode)
            return
        if name == "Continuity Designer":
            self.show_continuity_designer()
            return
        if name in {"Construction Guides", "Edit Construction Guides"}:
            selected_guides = self.field.selected_guide_ids()
            self.show_construction_guides(selected_guides[0] if selected_guides else "")
            return
        if name == "Reference / Annotation Layer":
            self.show_reference_annotations()
            return
        if name == "CAD Path Toolkit":
            self.show_cad_path_toolkit()
            return
        if name == "Save Selection Set":
            self.save_selection_set()
            return
        if name in {"Smart Transition Composer", "Guided Destination Repair"}:
            self.show_smart_transition_composer()
            return
        if name == "Section-Aware Form Fit":
            self.apply_section_aware_form_fit()
            return
        if name == "Copy With Property Paintbrush":
            self.copy_property_brush()
            return
        if name == "Paint Copied Properties":
            self.paint_property_brush()
            return
        if name == "Save Formation Preset":
            self.save_formation_preset()
            return
        if name == "Select Same Instrument":
            self.select_same_instrument()
            return
        if name == "Select Same Section":
            self.select_same_section()
            return
        if name == "Carry Selected Forward":
            self.carry_selected_forward()
            return
        if name == "Start Selected Move Here":
            self.start_selected_move_at_current_count()
            return
        if name == "Set Opening Positions From Current View":
            self.capture_opening_positions_from_current_view()
            return
        if name == "Face Front":
            self.set_selected_facing(0)
            return
        if name == "Face Back":
            self.set_selected_facing(180)
            return
        if name == "Rotate Facing -45":
            self.rotate_selected_facing(-45)
            return
        if name == "Rotate Facing +45":
            self.rotate_selected_facing(45)
            return
        if name == "Fit Form to Selected Prop":
            self.fit_selected_form_to_prop()
            return
        if name == "Lock Selected Sections":
            self.lock_selected_sections()
            return
        if name == "Unlock Selected Sections":
            self.unlock_selected_sections()
            return
        mapping = {
            "Preview Line": EditorTool.LINE,
            "Preview Curve": EditorTool.CURVE,
            "Preview Free Curve": EditorTool.FREE_CURVE,
            "Preview Arc": EditorTool.ARC,
            "Preview Circle": EditorTool.CIRCLE,
            "Preview Oval": EditorTool.ELLIPSE,
            "Preview Rectangle": EditorTool.RECTANGLE,
            "Preview Triangle": EditorTool.TRIANGLE,
            "Preview Diamond": EditorTool.DIAMOND,
            "Preview Polygon": EditorTool.POLYGON,
            "Preview Star": EditorTool.STAR,
            "Preview Spiral": EditorTool.SPIRAL,
            "Preview Block": EditorTool.BLOCK,
            "Preview Scale Form": EditorTool.SCALE,
            "Preview Warp Form": EditorTool.WARP,
            "Preview Rotate": EditorTool.ROTATE,
            "Preview SVG Shape": EditorTool.SVG_SHAPE,
            "Preview Scatter": EditorTool.SCATTER,
            "Preview Mirror": EditorTool.MIRROR,
            "Preview Shape Line": EditorTool.SHAPE_LINE,
        }
        if name in mapping:
            self.set_tool(mapping[name])

    def align_horizontal(self) -> None:
        ids, positions = self.selected_positions()
        if len(ids) < 2:
            return
        average_y = sum(y for _x, y in positions) / len(positions)
        after = self.current_positions()
        after.update({dot_id: (positions[index][0], average_y) for index, dot_id in enumerate(ids)})
        self.apply_positions(after)

    def align_vertical(self) -> None:
        ids, positions = self.selected_positions()
        if len(ids) < 2:
            return
        average_x = sum(x for x, _y in positions) / len(positions)
        after = self.current_positions()
        after.update({dot_id: (average_x, positions[index][1]) for index, dot_id in enumerate(ids)})
        self.apply_positions(after)

    def align_spacing(self) -> None:
        ids, positions = self.selected_positions()
        if len(ids) < 2:
            return
        sorted_pairs = sorted(zip(ids, positions), key=lambda pair: pair[1][0])
        new_positions = line_positions(len(ids), sorted_pairs[0][1], sorted_pairs[-1][1])
        after = self.current_positions()
        after.update({dot_id: new_positions[index] for index, (dot_id, _pos) in enumerate(sorted_pairs)})
        self.apply_positions(after)

    def normalize_selected_interval(self) -> None:
        ids, positions = self.selected_positions()
        if len(ids) < 2:
            return
        start = positions[0]
        end = positions[-1]
        vector = (end[0] - start[0], end[1] - start[1])
        length = (vector[0] ** 2 + vector[1] ** 2) ** 0.5 or 1.0
        direction = (vector[0] / length, vector[1] / length)
        spacing = self.interval_spacing.value()
        center = (
            sum(x for x, _y in positions) / len(positions),
            sum(y for _x, y in positions) / len(positions),
        )
        first_offset = -spacing * (len(ids) - 1) / 2
        new_positions = [
            (
                center[0] + direction[0] * (first_offset + spacing * index),
                center[1] + direction[1] * (first_offset + spacing * index),
            )
            for index in range(len(ids))
        ]
        after = self.current_positions()
        after.update({dot_id: new_positions[index] for index, dot_id in enumerate(ids)})
        self.apply_positions(after)

    def create_line_constraint(self) -> None:
        ids, _positions = self.selected_positions()
        if len(ids) < 2:
            return
        constraint = DotConstraint(
            name=f"Line {len(self.project.constraints) + 1}",
            constraint_type="line",
            dot_ids=ids,
            spacing=self.interval_spacing.value(),
        )
        self.project.constraints.append(constraint)
        self.refresh_constraints()
        self.statusBar().showMessage("Line constraint created", 2000)

    def create_pivot_constraint(self) -> None:
        ids, _positions = self.selected_positions()
        if len(ids) < 2:
            return
        constraint = DotConstraint(
            name=f"Pivot {len(self.project.constraints) + 1}",
            constraint_type="pivot",
            dot_ids=ids,
            spacing=self.interval_spacing.value(),
            metadata=make_relative_metadata(ids, self.current_positions(), pivot_id=ids[0]),
        )
        self.project.constraints.append(constraint)
        self.refresh_constraints()
        self.statusBar().showMessage("Pivot constraint created", 2000)

    def create_arc_constraint(self) -> None:
        ids, _positions = self.selected_positions()
        if len(ids) < 3:
            QMessageBox.information(self, "Arc Constraint", "Select at least three marchers first.")
            return
        constraint = DotConstraint(
            name=f"Arc {len(self.project.constraints) + 1}",
            constraint_type="arc",
            dot_ids=ids,
            spacing=self.interval_spacing.value(),
            metadata=make_arc_metadata(ids, self.current_positions()),
        )
        self.project.constraints.append(constraint)
        self.refresh_constraints()
        self.statusBar().showMessage("Arc constraint created", 2000)

    def create_block_constraint(self) -> None:
        ids, _positions = self.selected_positions()
        if len(ids) < 4:
            QMessageBox.information(self, "Block Constraint", "Select at least four marchers first.")
            return
        constraint = DotConstraint(
            name=f"Block {len(self.project.constraints) + 1}",
            constraint_type="block",
            dot_ids=ids,
            spacing=self.interval_spacing.value(),
            metadata=make_block_metadata(ids, self.current_positions(), self.interval_spacing.value()),
        )
        self.project.constraints.append(constraint)
        self.refresh_constraints()
        self.statusBar().showMessage("Block constraint created", 2000)

    def refresh_constraints(self) -> None:
        if not hasattr(self, "constraint_list"):
            return
        self.constraint_list.clear()
        for constraint in self.project.constraints:
            self.constraint_list.addItem(
                f"{constraint.name}: {constraint.constraint_type}, {len(constraint.dot_ids)} dots, {constraint.spacing:g} yd"
            )

    def apply_constraints(self) -> None:
        if not self.project.constraints:
            return
        before = self.current_positions()
        constrained_ids = {dot_id for constraint in self.project.constraints for dot_id in constraint.dot_ids}
        after = self.constrain_positions(dict(before), constrained_ids)
        if after != before:
            self.apply_positions(after)

    def rotate_selection(self) -> None:
        ids, positions = self.selected_positions()
        if len(ids) < 2:
            return
        new_positions = rotate_positions(positions, self.rotation_degrees.value())
        after = self.current_positions()
        after.update({dot_id: new_positions[index] for index, dot_id in enumerate(ids)})
        self.undo_stack.push(
            MoveDotsCommand(self, self.set_index, self.current_positions(), after, "Rotate Form")
        )

    def duplicate_form_to_next_set(self) -> None:
        self.duplicate_transform_to_next_set("copy")

    def duplicate_rotate_to_next_set(self) -> None:
        self.duplicate_transform_to_next_set("rotate")

    def duplicate_scale_to_next_set(self) -> None:
        self.duplicate_transform_to_next_set("scale")

    def duplicate_mirror_to_next_set(self) -> None:
        self.duplicate_transform_to_next_set("mirror")

    def duplicate_transform_to_next_set(self, mode: str) -> None:
        ids, positions = self.selected_positions()
        if not ids:
            QMessageBox.information(self, "Quick Duplicate", "Select a form first.")
            return
        if self.set_index >= len(self.project.sets) - 1:
            QMessageBox.information(self, "Quick Duplicate", "Add a next set before duplicating the form.")
            return
        transformed = list(positions)
        if mode == "rotate" and len(positions) >= 2:
            transformed = rotate_positions(positions, self.rotation_degrees.value())
        elif mode == "scale" and len(positions) >= 2:
            transformed = scaled_positions_to_size(
                positions,
                self.scale_width.value(),
                self.scale_height.value(),
                self.scale_lock_aspect.isChecked(),
            )
        elif mode == "mirror":
            axis = sum(x for x, _y in positions) / max(1, len(positions))
            transformed = mirror_positions(positions, "vertical", axis)

        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        next_index = self.set_index + 1
        next_set = self.project.sets[next_index]
        for dot_id, position in zip(ids, transformed):
            next_set.dot_positions[dot_id] = position
            next_set.path_anchors.pop(dot_id, None)
            next_set.path_controls.pop(dot_id, None)
            next_set.count_positions.pop(dot_id, None)
            next_set.count_facings.pop(dot_id, None)
        self.set_index = next_index
        self.current_count = self.current_set().start_count
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=True)
        self.push_set_snapshot(before_sets, before_index, before_count, f"Duplicate {mode.title()} To Next Set")

    def follow_leader_rotate(self) -> None:
        ids = [
            dot_id
            for dot_id in self.ordered_dot_ids(self.field.selected_dot_ids())
            if not self.is_dot_locked(dot_id)
        ]
        if len(ids) < 2:
            QMessageBox.information(self, "Follow the Leader", "Select at least two unlocked marchers first.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Follow the Leader")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)
        description = QLabel(
            "Marchers travel on the same ordered route and retain their distance behind the marcher ahead. "
            "Use a shaped line, free curve, SVG outline, or any existing form as the route."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        route_source = QComboBox()
        route_source.addItem("Incoming formation (recommended)", "incoming")
        route_source.addItem("Current set form", "current")
        group_mode = QComboBox()
        group_mode.addItem("Auto-detect separate forms", "auto")
        group_mode.addItem("One continuous route", "single")
        group_mode.addItem("Separate rows", "rows")
        group_mode.addItem("Separate files", "files")
        group_mode.addItem("Separate sections", "sections")
        topology = QComboBox()
        topology.addItem("Auto-detect", "auto")
        topology.addItem("Open line / path", "open")
        topology.addItem("Closed loop", "closed")
        order_mode = QComboBox()
        order_mode.addItem("Automatic spatial order", "automatic")
        order_mode.addItem("Roster order", "roster")
        order_mode.addItem("Left to right", "horizontal")
        order_mode.addItem("Front to back", "vertical")
        turn_style = QComboBox()
        turn_style.addItem("Smooth curves", True)
        turn_style.addItem("Straight segments / sharp corners", False)
        direction = QComboBox()
        direction.addItem("Forward along preview", 1)
        direction.addItem("Reverse along preview", -1)
        advance = QDoubleSpinBox()
        advance.setRange(0.0, max(2.0, len(ids) * 4.0))
        advance.setDecimals(2)
        advance.setSingleStep(0.25)
        advance.setValue(1.0)
        advance.setSuffix(" spots")
        face_direction = QCheckBox("Face the direction of travel throughout the move")
        facing_offset = QDoubleSpinBox()
        facing_offset.setRange(-180.0, 180.0)
        facing_offset.setDecimals(1)
        facing_offset.setSuffix(" deg")
        facing_offset.setToolTip(
            "Adds an optional visual offset to the route tangent. "
            "Zero points triangle symbols into the travel direction."
        )
        precision = QComboBox()
        precision.addItem("Normal (2 samples/count)", 2)
        precision.addItem("Smooth (4 samples/count)", 4)
        precision.addItem("High (8 samples/count)", 8)
        precision.setCurrentIndex(1)

        form.addRow("Route Source", route_source)
        form.addRow("Route Groups", group_mode)
        form.addRow("Route Topology", topology)
        form.addRow("Marcher Order", order_mode)
        form.addRow("Direction Changes", turn_style)
        form.addRow("Travel Direction", direction)
        form.addRow("Advance", advance)
        form.addRow(face_direction)
        form.addRow("Facing Offset", facing_offset)
        form.addRow("Playback Precision", precision)
        layout.addLayout(form)
        preview_status = QLabel()
        preview_status.setWordWrap(True)
        preview_status.setObjectName("secondaryText")
        layout.addWidget(preview_status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply Follow the Leader")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        plans: list[FollowLeaderPlan] = []

        def build_plans() -> list[FollowLeaderPlan]:
            if route_source.currentData() == "incoming":
                if self.set_index > 0:
                    route_positions = self.project.sets[self.set_index - 1].dot_positions
                else:
                    route_positions = {dot.id: (dot.x, dot.y) for dot in self.project.dots}
            else:
                route_positions = self.current_set().dot_positions
            selected_positions = {dot_id: route_positions[dot_id] for dot_id in ids if dot_id in route_positions}
            sections = {
                dot_id: (self.project.dot_by_id(dot_id).section if self.project.dot_by_id(dot_id) else "Unassigned")
                for dot_id in ids
            }
            groups = split_follow_leader_groups(
                ids,
                selected_positions,
                str(group_mode.currentData() or "auto"),
                sections,
            )
            options = FollowLeaderOptions(
                advance_spots=advance.value(),
                direction=int(direction.currentData() or 1),
                topology=str(topology.currentData() or "auto"),
                order_mode=str(order_mode.currentData() or "automatic"),
                curved=bool(turn_style.currentData()),
                samples_per_count=int(precision.currentData() or 4),
                face_direction=face_direction.isChecked(),
                facing_offset=facing_offset.value(),
            )
            return [
                plan_follow_leader(
                    group,
                    selected_positions,
                    self.current_set().start_count,
                    self.current_set().end_count,
                    options,
                )
                for group in groups
                if len(group) >= 2
            ]

        def update_preview() -> None:
            nonlocal plans
            try:
                plans = build_plans()
                targets = {dot_id: position for plan in plans for dot_id, position in plan.end_positions.items()}
                leaders = [
                    (plan.leader_id, plan.end_positions[plan.leader_id])
                    for plan in plans
                    if plan.leader_id in plan.end_positions
                ]
                self.field.show_follow_leader_preview([plan.route for plan in plans], targets, leaders)
                closed_count = sum(1 for plan in plans if plan.route_closed)
                preview_status.setText(
                    f"{len(plans)} route(s), {closed_count} closed, {len(targets)} marchers. "
                    f"Red = shared route; gold = destination; labeled handle = leader."
                )
                buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(plans))
            except ValueError as exc:
                plans = []
                self.field.clear_preview()
                preview_status.setText(str(exc))
                buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

        for widget in (route_source, group_mode, topology, order_mode, turn_style, direction, precision):
            widget.currentIndexChanged.connect(update_preview)
        advance.valueChanged.connect(update_preview)
        face_direction.toggled.connect(update_preview)
        facing_offset.valueChanged.connect(update_preview)
        facing_offset.setEnabled(False)
        face_direction.toggled.connect(facing_offset.setEnabled)
        update_preview()

        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self.field.clear_preview()
        if not accepted or not plans:
            self.refresh_selected_paths()
            return

        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        drill_set = self.current_set()
        changed_ids: set[str] = set()
        for plan in plans:
            for dot_id, position in plan.end_positions.items():
                drill_set.dot_positions[dot_id] = position
                drill_set.path_anchors.pop(dot_id, None)
                drill_set.path_controls.pop(dot_id, None)
                drill_set.count_positions[dot_id] = dict(plan.count_positions.get(dot_id, {}))
                drill_set.count_facings.pop(dot_id, None)
                if dot_id in plan.count_facings:
                    drill_set.count_facings[dot_id] = dict(plan.count_facings[dot_id])
                    drill_set.dot_facings[dot_id] = plan.end_facings[dot_id]
                changed_ids.add(dot_id)
        self.current_count = drill_set.start_count
        self.set_count(self.current_count, seek_audio=False)
        self.push_set_snapshot(before_sets, before_index, before_count, "Follow the Leader")
        self.select_dot_ids(self.ordered_dot_ids(list(changed_ids)))
        self.refresh_selected_paths()
        facing_text = " with direction-of-travel facing" if face_direction.isChecked() else ""
        self.statusBar().showMessage(
            f"Built {len(plans)} shared Follow-the-Leader route(s) for {len(changed_ids)} marchers{facing_text}",
            3600,
        )

    def refresh_motion_ribbon_list(self) -> None:
        if not hasattr(self, "motion_ribbon_list") or not self.project.sets:
            return
        current_id = self.active_motion_ribbon_id
        self.motion_ribbon_list.blockSignals(True)
        self.motion_ribbon_list.clear()
        for ribbon in self.current_set().motion_ribbons:
            item = QListWidgetItem(f"{ribbon.name}  •  {len(ribbon.dot_ids)} marchers")
            item.setData(Qt.ItemDataRole.UserRole, ribbon.id)
            item.setToolTip("Double-click to show shared Bézier nodes and tangent handles on the field.")
            self.motion_ribbon_list.addItem(item)
            if ribbon.id == current_id:
                self.motion_ribbon_list.setCurrentItem(item)
        self.motion_ribbon_list.blockSignals(False)

    def selected_motion_ribbon(self) -> MotionRibbon | None:
        ribbon_id = self.active_motion_ribbon_id
        if hasattr(self, "motion_ribbon_list") and self.motion_ribbon_list.currentItem() is not None:
            ribbon_id = str(self.motion_ribbon_list.currentItem().data(Qt.ItemDataRole.UserRole) or ribbon_id)
        ribbon = motion_ribbon_by_id(self.current_set().motion_ribbons, ribbon_id)
        if ribbon is not None:
            return ribbon
        selected = set(self.field.selected_dot_ids())
        candidates = [
            item
            for item in self.current_set().motion_ribbons
            if selected and (selected <= set(item.dot_ids) or set(item.dot_ids) <= selected)
        ]
        return min(candidates, key=lambda item: len(set(item.dot_ids) ^ selected)) if candidates else None

    def create_group_motion_ribbon(self) -> None:
        dot_ids = [
            dot_id
            for dot_id in self.ordered_dot_ids(self.field.selected_dot_ids())
            if not self.is_dot_locked(dot_id)
        ]
        if len(dot_ids) < 2:
            QMessageBox.information(self, "Group Motion Ribbon", "Select at least two unlocked marchers first.")
            return
        dialog = MotionRibbonDialog(len(dot_ids), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        starts_source = self.current_transition_start_positions()
        starts = {dot_id: starts_source[dot_id] for dot_id in dot_ids if dot_id in starts_source}
        ends = {dot_id: self.current_set().dot_positions[dot_id] for dot_id in dot_ids}
        try:
            ribbon = create_motion_ribbon(
                f"ribbon-{uuid4().hex[:10]}",
                dialog.name.text().strip() or "Group Motion Ribbon",
                dot_ids,
                starts,
                ends,
                bend=dialog.bend.value(),
                orient_to_path=dialog.orient_to_path.isChecked(),
                face_direction=dialog.face_direction.isChecked(),
                samples_per_count=dialog.precision.value(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Group Motion Ribbon", str(exc))
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        self.current_set().motion_ribbons.append(ribbon)
        self.apply_motion_ribbon_plan(ribbon)
        self.active_motion_ribbon_id = ribbon.id
        self.push_set_snapshot(before_sets, before_index, before_count, "Create Group Motion Ribbon")
        self.select_dot_ids(ribbon.dot_ids)
        self.refresh_motion_ribbon_list()
        self.show_motion_ribbon_editor(ribbon)
        self.statusBar().showMessage(
            "Group Motion Ribbon created. Drag red route nodes or cyan tangent handles on the field.",
            4200,
        )

    def apply_motion_ribbon_plan(self, ribbon: MotionRibbon, refresh_field: bool = True):
        starts_source = self.current_transition_start_positions()
        starts = {dot_id: starts_source[dot_id] for dot_id in ribbon.dot_ids if dot_id in starts_source}
        ends = {
            dot_id: self.current_set().dot_positions[dot_id]
            for dot_id in ribbon.dot_ids
            if dot_id in self.current_set().dot_positions
        }
        plan = plan_motion_ribbon(
            ribbon,
            starts,
            ends,
            self.current_set().start_count,
            self.current_set().end_count,
        )
        drill_set = self.current_set()
        for dot_id in ribbon.dot_ids:
            drill_set.path_anchors.pop(dot_id, None)
            drill_set.path_controls.pop(dot_id, None)
            drill_set.count_positions[dot_id] = dict(plan.count_positions.get(dot_id, {}))
            drill_set.count_facings.pop(dot_id, None)
            if dot_id in plan.count_facings:
                drill_set.count_facings[dot_id] = dict(plan.count_facings[dot_id])
                drill_set.dot_facings[dot_id] = plan.end_facings[dot_id]
        if refresh_field:
            self.set_count(self.current_count, seek_audio=False)
        return plan

    def show_motion_ribbon_editor(self, ribbon: MotionRibbon | None = None) -> None:
        ribbon = ribbon or self.selected_motion_ribbon()
        if ribbon is None:
            QMessageBox.information(self, "Group Path Handles", "Select a ribbon from the Motion tab first.")
            return
        try:
            plan = self.apply_motion_ribbon_plan(ribbon, refresh_field=False)
        except ValueError as exc:
            QMessageBox.warning(self, "Group Path Handles", str(exc))
            return
        self.active_motion_ribbon_id = ribbon.id
        self.field.set_motion_path_editing(True)
        self.field.show_motion_ribbon_preview(
            plan.center_path,
            plan.left_edge,
            plan.right_edge,
            plan.paths,
            ribbon.id,
            ribbon.nodes,
        )
        self.refresh_motion_ribbon_list()

    def edit_group_path_handles(self) -> None:
        self.show_motion_ribbon_editor()

    def edit_motion_ribbon_settings(self) -> None:
        ribbon = self.selected_motion_ribbon()
        if ribbon is None:
            return
        dialog = MotionRibbonDialog(len(ribbon.dot_ids), ribbon, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        ribbon.name = dialog.name.text().strip() or ribbon.name
        ribbon.orient_to_path = dialog.orient_to_path.isChecked()
        ribbon.face_direction = dialog.face_direction.isChecked()
        ribbon.samples_per_count = dialog.precision.value()
        self.apply_motion_ribbon_plan(ribbon)
        self.push_set_snapshot(before_sets, before_index, before_count, "Edit Motion Ribbon Settings")
        self.show_motion_ribbon_editor(self.selected_motion_ribbon())

    def preview_handle_dragged(self, kind: str, x: float, y: float, modifiers: int = 0) -> None:
        self.preview_handle_moved(kind, x, y, modifiers, commit=False)

    def move_motion_ribbon_handle(
        self,
        kind: str,
        x: float,
        y: float,
        modifiers: int,
        commit: bool,
    ) -> bool:
        if not kind.startswith("motion_ribbon_"):
            return False
        parts = kind.split(":")
        if len(parts) < 3:
            return True
        ribbon = motion_ribbon_by_id(self.current_set().motion_ribbons, parts[1])
        if ribbon is None:
            return True
        try:
            index = int(parts[2])
        except ValueError:
            return True
        if not 0 <= index < len(ribbon.nodes):
            return True
        if self._motion_ribbon_drag_before_sets is None:
            self._motion_ribbon_drag_before_sets = deepcopy(self.project.sets)
        node = ribbon.nodes[index]
        if kind.startswith("motion_ribbon_node:"):
            old_point = node["point"]
            delta = (x - old_point[0], y - old_point[1])
            node["point"] = (x, y)
            for control_name in ("in", "out"):
                if control_name in node:
                    control = node[control_name]
                    node[control_name] = (control[0] + delta[0], control[1] + delta[1])
        elif kind.startswith("motion_ribbon_tangent:") and len(parts) >= 4:
            control_name = parts[3]
            if control_name not in {"in", "out"}:
                return True
            node[control_name] = (x, y)
            alt = bool(modifiers & int(Qt.KeyboardModifier.AltModifier.value))
            if alt:
                opposite = "out" if control_name == "in" else "in"
                point = node["point"]
                node[opposite] = (point[0] * 2 - x, point[1] * 2 - y)
        try:
            plan = self.apply_motion_ribbon_plan(ribbon)
        except ValueError:
            return True
        self.field.show_motion_ribbon_preview(
            plan.center_path,
            plan.left_edge,
            plan.right_edge,
            plan.paths,
            ribbon.id,
            ribbon.nodes,
        )
        if commit and self._motion_ribbon_drag_before_sets is not None:
            before_sets = self._motion_ribbon_drag_before_sets
            self._motion_ribbon_drag_before_sets = None
            before_index = self.set_index
            before_count = self.current_count
            self.push_set_snapshot(before_sets, before_index, before_count, "Edit Group Path Handles")
            ribbon = motion_ribbon_by_id(self.current_set().motion_ribbons, self.active_motion_ribbon_id)
            if ribbon is not None:
                self.show_motion_ribbon_editor(ribbon)
        return True

    def add_motion_ribbon_node(self) -> None:
        ribbon = self.selected_motion_ribbon()
        if ribbon is None:
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        sampled = sample_motion_ribbon(ribbon, 32)
        first, second = cad_split(sampled, 0.5)
        first = cad_simplify(first, 0.75)
        second = cad_simplify(second, 0.75)
        combined = [*first, *second[1:]] if second else first
        ribbon.nodes = path_to_bezier_nodes(combined)
        self.apply_motion_ribbon_plan(ribbon)
        self.push_set_snapshot(before_sets, before_index, before_count, "Add Motion Ribbon Node")
        self.show_motion_ribbon_editor(self.selected_motion_ribbon())

    def remove_motion_ribbon_node(self) -> None:
        ribbon = self.selected_motion_ribbon()
        if ribbon is None or len(ribbon.nodes) <= 2:
            self.statusBar().showMessage("A motion ribbon must retain at least two route nodes.", 2600)
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        ribbon.nodes.pop(len(ribbon.nodes) // 2)
        self.apply_motion_ribbon_plan(ribbon)
        self.push_set_snapshot(before_sets, before_index, before_count, "Remove Motion Ribbon Node")
        self.show_motion_ribbon_editor(self.selected_motion_ribbon())

    def delete_motion_ribbon(self) -> None:
        ribbon = self.selected_motion_ribbon()
        if ribbon is None:
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        self.current_set().motion_ribbons = [item for item in self.current_set().motion_ribbons if item.id != ribbon.id]
        for dot_id in ribbon.dot_ids:
            self.current_set().count_positions.pop(dot_id, None)
            self.current_set().count_facings.pop(dot_id, None)
        self.active_motion_ribbon_id = ""
        self.field.clear_preview()
        self.field.set_motion_path_editing(False)
        self.set_count(self.current_count, seek_audio=False)
        self.push_set_snapshot(before_sets, before_index, before_count, "Delete Group Motion Ribbon")
        self.refresh_motion_ribbon_list()

    def accelerator_selection(self) -> tuple[list[str], dict[str, tuple[float, float]]]:
        positions = self.current_set().dot_positions
        selected = [
            dot_id
            for dot_id in self.field.selected_dot_ids()
            if dot_id in positions and not self.is_dot_locked(dot_id)
        ]
        return spatial_id_order(selected, positions), positions

    def selected_design_guide_path(self) -> list[tuple[float, float]]:
        selected = set(self.field.selected_guide_ids())
        guide = next(
            (
                item
                for item in self.project.guides
                if item.id in selected and not item.guide_type.startswith("annotation_")
            ),
            None,
        )
        return guide_path(guide) if guide is not None else []

    def apply_accelerator_targets(
        self,
        targets: dict[str, tuple[float, float]],
        label: str,
    ) -> bool:
        if not targets:
            return False
        outside = [
            dot_id
            for dot_id, (x, y) in targets.items()
            if not surface_contains_point(self.project.surface, (x, y))
        ]
        if outside:
            answer = QMessageBox.question(
                self,
                f"{label}: Spots Outside Field",
                f"{len(outside)} target spot(s) are outside the playable field. Apply anyway?",
                QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Apply:
                return False
        self.field.clear_preview()
        self.apply_positions(targets)
        self.select_dot_ids(list(targets))
        self.refresh_measurements()
        self.statusBar().showMessage(f"{label} applied to {len(targets)} marcher(s)", 3000)
        return True

    def show_polar_linear_array(self) -> None:
        dot_ids, positions = self.accelerator_selection()
        if len(dot_ids) < 2:
            QMessageBox.information(self, "Polar / Linear Array", "Select at least two unlocked marchers first.")
            return
        path = self.selected_design_guide_path()
        dialog = ArrayDialog(len(dot_ids), bool(path), self)

        def targets_for_dialog() -> dict[str, tuple[float, float]]:
            source = [positions[dot_id] for dot_id in dot_ids]
            target_points = array_target_points(source, len(dot_ids), dialog.options(), path)
            return assign_targets_minimum_cost(dot_ids, positions, target_points)

        def preview() -> None:
            try:
                targets = targets_for_dialog()
            except ValueError as exc:
                self.field.clear_preview()
                self.statusBar().showMessage(str(exc), 2600)
                return
            self.field.show_preview({dot_id: positions[dot_id] for dot_id in dot_ids}, targets)

        dialog.settings_changed.connect(preview)
        preview()
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self.field.clear_preview()
        if not accepted:
            self.refresh_selected_paths()
            return
        try:
            targets = targets_for_dialog()
        except ValueError as exc:
            QMessageBox.warning(self, "Array Cannot Be Applied", str(exc))
            return
        self.apply_accelerator_targets(targets, "Polar / Linear Array")

    def parallel_master_path(
        self,
        dot_ids: list[str],
        positions: dict[str, tuple[float, float]],
        prefer_guide: bool = False,
    ) -> list[tuple[float, float]]:
        guide = self.selected_design_guide_path()
        if prefer_guide and len(guide) >= 2:
            return guide
        return [positions[dot_id] for dot_id in spatial_id_order(dot_ids, positions)]

    def show_parallel_form_generator(self) -> None:
        dot_ids, positions = self.accelerator_selection()
        if len(dot_ids) < 2:
            QMessageBox.information(self, "Parallel Form Generator", "Select at least two unlocked marchers first.")
            return
        dialog = ParallelFormDialog(len(dot_ids), parent=self)

        def targets_for_dialog() -> dict[str, tuple[float, float]]:
            master_path = self.parallel_master_path(dot_ids, positions)
            target_points = parallel_form_target_points(master_path, len(dot_ids), dialog.options())
            return assign_targets_minimum_cost(dot_ids, positions, target_points)

        def preview() -> None:
            try:
                targets = targets_for_dialog()
            except ValueError as exc:
                self.field.clear_preview()
                self.statusBar().showMessage(str(exc), 2600)
                return
            self.field.show_preview({dot_id: positions[dot_id] for dot_id in dot_ids}, targets)

        dialog.settings_changed.connect(preview)
        preview()
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self.field.clear_preview()
        if not accepted:
            self.refresh_selected_paths()
            return
        try:
            targets = targets_for_dialog()
        except ValueError as exc:
            QMessageBox.warning(self, "Parallel Form Cannot Be Applied", str(exc))
            return
        self.apply_accelerator_targets(targets, "Parallel Form Generator")

    def show_rank_file_builder(self) -> None:
        dot_ids, positions = self.accelerator_selection()
        if len(dot_ids) < 2:
            QMessageBox.information(self, "Rank / File Builder", "Select at least two unlocked marchers first.")
            return
        guide = self.selected_design_guide_path()
        dialog = RankFileDialog(len(dot_ids), bool(guide), self)

        def targets_for_dialog() -> dict[str, tuple[float, float]]:
            use_guide = str(dialog.source.currentData()) == "guide"
            master_path = self.parallel_master_path(dot_ids, positions, prefer_guide=use_guide)
            target_points = rank_file_target_points(
                master_path,
                len(dot_ids),
                dialog.ranks.value(),
                dialog.interval.value(),
                centered=str(dialog.placement.currentData()) == "centered",
                closed=dialog.closed.isChecked(),
            )
            return assign_targets_minimum_cost(dot_ids, positions, target_points)

        def preview() -> None:
            try:
                targets = targets_for_dialog()
            except ValueError as exc:
                self.field.clear_preview()
                self.statusBar().showMessage(str(exc), 2600)
                return
            self.field.show_preview({dot_id: positions[dot_id] for dot_id in dot_ids}, targets)

        dialog.settings_changed.connect(preview)
        preview()
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self.field.clear_preview()
        if not accepted:
            self.refresh_selected_paths()
            return
        try:
            targets = targets_for_dialog()
        except ValueError as exc:
            QMessageBox.warning(self, "Rank / File Builder", str(exc))
            return
        self.apply_accelerator_targets(targets, "Rank / File Builder")

    def create_live_symmetry(self) -> None:
        dot_ids, positions = self.accelerator_selection()
        if len(dot_ids) < 2:
            QMessageBox.information(self, "Live Symmetry", "Select marchers on both sides of the desired axis.")
            return
        center = self.positions_center([positions[dot_id] for dot_id in dot_ids])
        dialog = LiveSymmetryDialog(center, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            record = create_live_symmetry_record(
                dot_ids,
                positions,
                (dialog.axis_x.value(), dialog.axis_y.value()),
                dialog.angle.value(),
                name=dialog.name.text(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Live Symmetry", str(exc))
            return
        before = deepcopy(self.project)
        self.project.workflow.setdefault("live_symmetry", []).append(record)
        angle = radians(float(record["axis_angle"]))
        center_x, center_y = record["axis_point"]
        extent = 70.0
        direction = (cos(angle), sin(angle))
        self.project.guides.append(
            ConstructionGuide(
                id=f"{record['id']}-axis",
                name=f"{record['name']} Axis",
                guide_type="line",
                points=[
                    (center_x - direction[0] * extent, center_y - direction[1] * extent),
                    (center_x + direction[0] * extent, center_y + direction[1] * extent),
                ],
                color="#18b8d8",
                visible=True,
                locked=True,
                metadata={"category": "live_symmetry", "symmetry_id": record["id"]},
            )
        )
        after = deepcopy(self.project)
        self.apply_project_snapshot(before)
        self.undo_stack.push(ProjectSnapshotCommand(self, before, after, "Create Live Symmetry"))
        self.statusBar().showMessage(f"Live symmetry created with {len(record['pairs'])} mirrored pair(s)", 3200)

    def manage_live_symmetry(self) -> None:
        records = list(self.project.workflow.get("live_symmetry", []))
        if not records:
            QMessageBox.information(self, "Live Symmetry", "No live symmetry links exist in this project yet.")
            return
        dialog = SymmetryManagerDialog(records, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before = deepcopy(self.project)
        surviving_ids = {str(record.get("id", "")) for record in dialog.records}
        self.project.workflow["live_symmetry"] = deepcopy(dialog.records)
        self.project.guides = [
            guide
            for guide in self.project.guides
            if guide.metadata.get("category") != "live_symmetry"
            or str(guide.metadata.get("symmetry_id", "")) in surviving_ids
        ]
        enabled = {
            str(record.get("id", "")): bool(record.get("enabled", True))
            for record in dialog.records
        }
        for guide in self.project.guides:
            if guide.metadata.get("category") == "live_symmetry":
                guide.visible = enabled.get(str(guide.metadata.get("symmetry_id", "")), False)
        after = deepcopy(self.project)
        if before == after:
            return
        self.apply_project_snapshot(before)
        self.undo_stack.push(ProjectSnapshotCommand(self, before, after, "Manage Live Symmetry"))

    def preview_live_symmetry(self, proposed: dict[str, tuple[float, float]]) -> None:
        records = self.project.workflow.get("live_symmetry", [])
        if not records or not proposed:
            return
        expanded = expand_live_symmetry_changes(
            records,
            self.current_set().dot_positions,
            proposed,
            {
                dot.id
                for dot in self.project.dots
                if self.is_dot_locked(dot.id)
            },
        )
        for dot_id, position in expanded.items():
            if dot_id in proposed:
                continue
            item = self.field.dot_items.get(dot_id)
            if item:
                item.setPos(self.field.field_to_scene(*position))

    def preview_dot_coordinates(self, proposed: dict[str, tuple[float, float]]) -> None:
        self.update_selected_coordinate_readout(proposed)

    @staticmethod
    def inspector_coordinate_text(value: float) -> str:
        text = f"{float(value):.3f}".rstrip("0").rstrip(".")
        return "0" if text in {"", "-0"} else text

    def update_selected_coordinate_readout(
        self,
        positions: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        if not hasattr(self, "dot_x"):
            return
        ids = self.field.selected_dot_ids()
        if len(ids) != 1 or self.field.selected_prop_ids():
            self.dot_yardline.setText("-")
            self.dot_hash.setText("-")
            return
        dot_id = ids[0]
        position = positions.get(dot_id) if positions else None
        if position is None:
            item = self.field.dot_items.get(dot_id)
            if item is not None:
                position = self.field.scene_to_field(item.pos())
        if position is None:
            position = self.current_set().dot_positions.get(dot_id, (0.0, 0.0))
        if not self.dot_x.hasFocus():
            self.dot_x.setText(self.inspector_coordinate_text(position[0]))
        if not self.dot_y.hasFocus():
            self.dot_y.setText(self.inspector_coordinate_text(position[1]))
        yard_text, hash_text = format_surface_coordinate(self.project.surface, position[0], position[1])
        self.dot_yardline.setText(yard_text)
        self.dot_hash.setText(hash_text)

    def show_alternating_selection(self) -> None:
        current = self.field.selected_dot_ids()
        visible = [
            dot_id
            for dot_id, item in self.field.dot_items.items()
            if item.isVisible() and not self.is_dot_locked(dot_id)
        ]
        dialog = AlternatingSelectionDialog(len(current), len(visible), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        candidates = current if str(dialog.scope.currentData()) == "selection" and current else visible
        positions = self.current_set().dot_positions
        current_points = [positions[dot_id] for dot_id in current if dot_id in positions]
        anchor = self.positions_center(current_points) if current_points else None
        if len(current) == 1 and current[0] in positions:
            anchor = positions[current[0]]
        ranks = {
            dot.id: dot.rank
            for dot in self.project.dots
        }
        selected = alternating_selection(
            candidates,
            positions,
            str(dialog.mode.currentData()),
            every=dialog.every.value(),
            ranks=ranks,
            count=dialog.count.value(),
            anchor=anchor,
        )
        if dialog.additive.isChecked():
            selected = list(dict.fromkeys([*current, *selected]))
        self.select_dot_ids(selected)
        self.statusBar().showMessage(f"Selected {len(selected)} marcher(s)", 2200)

    def set_measurement_overlay(self, enabled: bool, mode: str = "all") -> None:
        self.measurements_enabled = bool(enabled)
        self.measurement_mode = str(mode or "all")
        self.refresh_measurements()

    def toggle_measurement_overlay(self) -> None:
        enabled = not self.measurements_enabled
        if hasattr(self, "accelerator_panel"):
            self.accelerator_panel.measurements_enabled.setChecked(enabled)
        self.set_measurement_overlay(enabled, self.measurement_mode)

    def refresh_measurements(self) -> None:
        if not self.measurements_enabled:
            self.field.clear_measurements()
            return
        selected = self.field.selected_dot_ids()
        current_positions = {
            dot_id: self.field.scene_to_field(self.field.dot_items[dot_id].pos())
            for dot_id in selected
            if dot_id in self.field.dot_items
        }
        ordered_ids = spatial_id_order(list(current_positions), current_positions)
        ordered_points = [(dot_id, current_positions[dot_id]) for dot_id in ordered_ids]
        starts = self.current_transition_start_positions()
        drill_set = self.current_set()
        paths: dict[str, list[tuple[float, float]]] = {}
        for dot_id in ordered_ids:
            start = starts.get(dot_id)
            end = drill_set.dot_positions.get(dot_id)
            if start is None or end is None:
                continue
            keyframes = drill_set.count_positions.get(dot_id, {})
            if keyframes:
                paths[dot_id] = [
                    start,
                    *[
                        point
                        for count, point in sorted(keyframes.items())
                        if drill_set.start_count < count < drill_set.end_count
                    ],
                    end,
                ]
            else:
                paths[dot_id] = sample_transition_path(
                    start,
                    end,
                    drill_set.path_anchors.get(dot_id, []),
                    drill_set.path_controls.get(dot_id, []),
                )
        self.field.show_measurements(
            ordered_points,
            paths,
            max(1.0, float(drill_set.duration_counts)),
            self.measurement_mode,
        )

    def show_reference_annotations(self, selected_id: str = "") -> None:
        center_scene = self.field.mapToScene(self.field.viewport().rect().center())
        center = self.field.scene_to_field(center_scene)
        dialog = ReferenceAnnotationsDialog(self.project.guides, center, self.set_index, self)
        if selected_id:
            dialog.active_id = selected_id
            dialog.refresh_list()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before = deepcopy(self.project)
        references_dir = self.project_dir / "references"
        references_dir.mkdir(parents=True, exist_ok=True)
        annotations = deepcopy(dialog.annotations)
        for annotation in annotations:
            if annotation.guide_type != "annotation_image":
                continue
            image_value = str(annotation.metadata.get("image_file", ""))
            if not image_value:
                continue
            source = Path(image_value)
            if not source.is_absolute():
                source = self.project_dir / source
            if not source.exists():
                continue
            try:
                source.relative_to(self.project_dir)
                inside_project = True
            except ValueError:
                inside_project = False
            if inside_project:
                annotation.metadata["image_file"] = str(source.relative_to(self.project_dir))
                continue
            destination = references_dir / source.name
            suffix = 2
            while destination.exists() and destination.read_bytes() != source.read_bytes():
                destination = references_dir / f"{source.stem}_{suffix}{source.suffix}"
                suffix += 1
            if not destination.exists():
                shutil.copy2(source, destination)
            annotation.metadata["image_file"] = str(destination.relative_to(self.project_dir))
        construction = [guide for guide in self.project.guides if not guide.guide_type.startswith("annotation_")]
        self.project.guides = [*construction, *annotations]
        after = deepcopy(self.project)
        if before == after:
            return
        self.apply_project_snapshot(before)
        self.undo_stack.push(ProjectSnapshotCommand(self, before, after, "Edit Reference Layer"))
        self.statusBar().showMessage(f"Reference layer updated: {len(annotations)} object(s)", 2800)

    def show_continuity_designer(self) -> None:
        selected_ids = self.ordered_dot_ids(self.field.selected_dot_ids())
        dialog = ContinuityDesignerDialog(
            self.current_set().continuity,
            selected_ids,
            self.current_set().start_count,
            self.current_set().end_count,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        self.current_set().continuity = deepcopy(dialog.instructions)
        for instruction in self.current_set().continuity:
            if instruction.body_facing is None:
                continue
            for dot_id in instruction.dot_ids:
                keys = self.current_set().count_facings.setdefault(dot_id, {})
                keys[float(instruction.start_count)] = float(instruction.body_facing)
                keys[float(instruction.end_count)] = float(instruction.body_facing)
                if instruction.end_count >= self.current_set().end_count:
                    self.current_set().dot_facings[dot_id] = float(instruction.body_facing)
        self.set_count(self.current_count, seek_audio=False)
        self.push_set_snapshot(before_sets, before_index, before_count, "Edit Continuity")
        self.statusBar().showMessage(f"Saved {len(self.current_set().continuity)} continuity instruction(s).", 2800)

    def show_construction_guides(self, selected_guide_id: str = "") -> None:
        center_scene = self.field.mapToScene(self.field.viewport().rect().center())
        center = self.field.scene_to_field(center_scene)
        dialog = ConstructionGuidesDialog(self.project.guides, center, self)
        if selected_guide_id:
            for row in range(dialog.list.count()):
                item = dialog.list.item(row)
                if str(item.data(Qt.ItemDataRole.UserRole)) == selected_guide_id:
                    dialog.list.setCurrentRow(row)
                    break
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before = deepcopy(self.project)
        self.project.guides = deepcopy(dialog.guides)
        after = deepcopy(self.project)
        if before == after:
            return
        self.apply_project_snapshot(before)
        self.undo_stack.push(ProjectSnapshotCommand(self, before, after, "Edit Construction Guides"))
        self.statusBar().showMessage(f"Updated {len(self.project.guides)} construction guide(s).", 2600)

    def edit_construction_guide(self, guide_id: str) -> None:
        guide = next((item for item in self.project.guides if item.id == guide_id), None)
        if guide is not None and guide.guide_type.startswith("annotation_"):
            self.show_reference_annotations(guide_id)
            return
        self.show_construction_guides(guide_id)

    def move_construction_guide(self, guide_id: str, delta_x: float, delta_y: float) -> None:
        guide = next((item for item in self.project.guides if item.id == guide_id), None)
        if guide is None or guide.locked:
            self.field.rebuild_guides()
            return
        before = deepcopy(self.project)
        guide.points = [(x + delta_x, y + delta_y) for x, y in guide.points]
        after = deepcopy(self.project)
        self.apply_project_snapshot(before)
        self.undo_stack.push(ProjectSnapshotCommand(self, before, after, "Move Construction Guide"))

    def show_formation_morph(self) -> None:
        dot_ids = [
            dot_id
            for dot_id in self.ordered_dot_ids(self.field.selected_dot_ids())
            if not self.is_dot_locked(dot_id)
        ]
        if len(dot_ids) < 2:
            QMessageBox.information(self, "Formation Morph", "Select at least two unlocked marchers first.")
            return
        dialog = FormationMorphDialog(len(dot_ids), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        starts_source = self.current_transition_start_positions()
        starts = {dot_id: starts_source[dot_id] for dot_id in dot_ids if dot_id in starts_source}
        target_points = [self.current_set().dot_positions[dot_id] for dot_id in dot_ids]
        assignment_mode = str(dialog.assignment.currentData())
        if assignment_mode == "keep":
            ends = {dot_id: point for dot_id, point in zip(dot_ids, target_points)}
        else:
            mode = {
                "shortest": "shortest",
                "section": "section",
                "collision": "lowest_collision",
            }.get(assignment_mode, "shortest")
            ends = assignment_for_mode(
                self.project,
                self.set_index,
                dot_ids,
                target_points,
                mode,
                min_spacing=self.min_spacing.value() if hasattr(self, "min_spacing") else 1.25,
                max_yards_per_count=self.max_yards_per_count.value() if hasattr(self, "max_yards_per_count") else 4.0,
            )
        sections = {}
        for dot_id in dot_ids:
            dot = self.project.dot_by_id(dot_id)
            section = dot.section if dot else ""
            rank = dot.rank if dot else ""
            sections[dot_id] = " :: ".join(value for value in (section, rank) if value) or "Unassigned"
        try:
            plan = plan_formation_morph(
                dot_ids,
                starts,
                ends,
                sections,
                self.current_set().start_count,
                self.current_set().end_count,
                MorphOptions(
                    coherence=dialog.coherence.value() / 100.0,
                    section_strength=dialog.section_strength.value() / 100.0,
                    samples_per_count=dialog.precision.value(),
                    face_direction=dialog.face_direction.isChecked(),
                ),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Formation Morph", str(exc))
            return
        self.field.show_paths(plan.paths, {})
        answer = QMessageBox.question(
            self,
            "Apply Formation Morph?",
            "Yellow paths preview the coordinated morph. Apply this transition?",
            QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Apply,
        )
        self.field.clear_paths()
        if answer != QMessageBox.StandardButton.Apply:
            self.refresh_selected_paths()
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        drill_set = self.current_set()
        for dot_id in dot_ids:
            drill_set.dot_positions[dot_id] = ends[dot_id]
            drill_set.path_anchors.pop(dot_id, None)
            drill_set.path_controls.pop(dot_id, None)
            drill_set.count_positions[dot_id] = dict(plan.count_positions.get(dot_id, {}))
            drill_set.count_facings.pop(dot_id, None)
            if dot_id in plan.count_facings:
                drill_set.count_facings[dot_id] = dict(plan.count_facings[dot_id])
                drill_set.dot_facings[dot_id] = plan.end_facings[dot_id]
        selected_set = set(dot_ids)
        drill_set.motion_ribbons = [
            ribbon for ribbon in drill_set.motion_ribbons if not selected_set.intersection(ribbon.dot_ids)
        ]
        self.set_count(self.current_count, seek_audio=False)
        self.push_set_snapshot(before_sets, before_index, before_count, "Formation Morph")
        self.select_dot_ids(dot_ids)
        self.refresh_selected_paths()

    @staticmethod
    def apply_cad_path_operation(
        path: list[tuple[float, float]],
        operation: str,
        value_a: float,
        value_b: float,
        iterations: int,
    ) -> list[tuple[float, float]]:
        if operation == "split":
            first, second = cad_split(path, value_a)
            return [*first, *second[1:]] if second else first
        if operation == "trim":
            return cad_trim(path, value_a, value_b)
        if operation == "extend":
            return cad_extend(path, max(0.0, value_a), max(0.0, value_b))
        if operation == "offset":
            return cad_offset(path, value_a)
        if operation == "simplify":
            return cad_simplify(path, max(0.001, abs(value_a)))
        if operation == "smooth":
            return cad_smooth(path, iterations)
        if operation == "reverse":
            return cad_reverse(path)
        if operation == "fillet":
            return cad_fillet(path, max(0.001, abs(value_a)), max(2, iterations))
        return list(path)

    @staticmethod
    def preserve_transition_path_endpoints(
        original: list[tuple[float, float]],
        processed: list[tuple[float, float]],
        operation: str,
    ) -> list[tuple[float, float]]:
        if len(original) < 2:
            return processed
        if operation == "reverse":
            return [original[0], *list(reversed(original[1:-1])), original[-1]]
        result = list(processed)
        if not result:
            return [original[0], original[-1]]
        if distance(result[0], original[0]) > 0.0001:
            result.insert(0, original[0])
        else:
            result[0] = original[0]
        if distance(result[-1], original[-1]) > 0.0001:
            result.append(original[-1])
        else:
            result[-1] = original[-1]
        return result

    def show_cad_path_toolkit(self) -> None:
        ribbon = self.selected_motion_ribbon()
        guide_ids = self.field.selected_guide_ids()
        dot_ids = self.ordered_dot_ids(self.field.selected_dot_ids())
        if ribbon is not None:
            target_description = f"motion ribbon '{ribbon.name}'"
            target_kind = "ribbon"
        elif guide_ids:
            target_description = f"{len(guide_ids)} selected construction guide(s)"
            target_kind = "guides"
        elif dot_ids:
            target_description = f"{len(dot_ids)} selected marcher path(s)"
            target_kind = "dots"
        else:
            QMessageBox.information(
                self,
                "CAD Path Toolkit",
                "Select a motion ribbon, construction guide, or marcher path first.",
            )
            return
        dialog = CadPathDialog(target_description, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        operation = str(dialog.operation.currentData())
        value_a = dialog.value_a.value()
        value_b = dialog.value_b.value()
        iterations = dialog.iterations.value()
        if target_kind == "guides":
            before = deepcopy(self.project)
            selected_guides = [guide for guide in self.project.guides if guide.id in set(guide_ids)]
            if operation == "join":
                if len(selected_guides) < 2:
                    QMessageBox.information(self, "CAD Join", "Select at least two construction guides.")
                    return
                joined = cad_join(
                    [guide_path(guide) for guide in selected_guides],
                    tolerance=max(0.0, value_a),
                )
                primary = selected_guides[0]
                primary.guide_type = "polyline"
                primary.points = joined
                removed = {guide.id for guide in selected_guides[1:]}
                self.project.guides = [guide for guide in self.project.guides if guide.id not in removed]
            elif operation == "split":
                if not selected_guides:
                    return
                primary = selected_guides[0]
                first, second = cad_split(guide_path(primary), value_a)
                primary.guide_type = "polyline"
                primary.points = first
                if second:
                    duplicate = deepcopy(primary)
                    duplicate.id = f"guide-{uuid4().hex[:10]}"
                    duplicate.name = f"{primary.name} Split"
                    duplicate.points = second
                    self.project.guides.append(duplicate)
            else:
                for guide in selected_guides:
                    guide.points = self.apply_cad_path_operation(
                        guide_path(guide), operation, value_a, value_b, iterations
                    )
                    guide.guide_type = "polyline"
            after = deepcopy(self.project)
            self.apply_project_snapshot(before)
            self.undo_stack.push(ProjectSnapshotCommand(self, before, after, f"CAD {operation.title()} Guides"))
            return

        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        if target_kind == "ribbon" and ribbon is not None:
            if operation == "join":
                QMessageBox.information(self, "CAD Join", "Join is available when two or more construction guides are selected.")
                return
            original = sample_motion_ribbon(ribbon, 32)
            if operation == "split":
                first, second = cad_split(original, value_a)
                first = cad_simplify(first, 0.3)
                second = cad_simplify(second, 0.3)
                processed = [*first, *second[1:]] if second else first
            else:
                processed = self.apply_cad_path_operation(
                    original, operation, value_a, value_b, iterations
                )
                processed = self.preserve_transition_path_endpoints(original, processed, operation)
                processed = cad_simplify(processed, 0.3)
            ribbon.nodes = path_to_bezier_nodes(processed)
            self.apply_motion_ribbon_plan(ribbon)
        else:
            if operation == "join":
                QMessageBox.information(self, "CAD Join", "Individual marcher transitions remain independent; create a Group Motion Ribbon to join them.")
                return
            starts = self.current_transition_start_positions()
            drill_set = self.current_set()
            for dot_id in dot_ids:
                if dot_id not in starts or dot_id not in drill_set.dot_positions:
                    continue
                original = [starts[dot_id], *drill_set.path_anchors.get(dot_id, []), drill_set.dot_positions[dot_id]]
                processed = self.apply_cad_path_operation(original, operation, value_a, value_b, iterations)
                processed = self.preserve_transition_path_endpoints(original, processed, operation)
                drill_set.path_anchors[dot_id] = processed[1:-1]
                drill_set.path_controls.pop(dot_id, None)
                drill_set.count_positions.pop(dot_id, None)
        self.set_count(self.current_count, seek_audio=False)
        self.push_set_snapshot(before_sets, before_index, before_count, f"CAD {operation.title()} Paths")
        if target_kind == "ribbon":
            self.show_motion_ribbon_editor(self.selected_motion_ribbon())
        else:
            self.refresh_selected_paths()

    def center_selection(self) -> None:
        ids, positions = self.selected_positions()
        if not ids:
            return
        new_positions = centered_positions(positions)
        after = self.current_positions()
        after.update({dot_id: new_positions[index] for index, dot_id in enumerate(ids)})
        self.undo_stack.push(
            MoveDotsCommand(self, self.set_index, self.current_positions(), after, "Center Form")
        )

    def set_thumbnails_enabled(self) -> bool:
        return self.settings.value("sets/show_thumbnails", True, type=bool)

    def set_set_thumbnails_enabled(self, enabled: bool = True) -> None:
        active = bool(enabled)
        self.settings.setValue("sets/show_thumbnails", active)
        self.settings.sync()
        if hasattr(self, "set_thumbnail_toggle"):
            self.set_thumbnail_toggle.blockSignals(True)
            self.set_thumbnail_toggle.setChecked(active)
            self.set_thumbnail_toggle.blockSignals(False)
        if hasattr(self, "set_thumbnails_action"):
            self.set_thumbnails_action.blockSignals(True)
            self.set_thumbnails_action.setChecked(active)
            self.set_thumbnails_action.blockSignals(False)
        self.configure_set_list_view()
        self.populate_sets()

    def configure_set_list_view(self) -> None:
        if not hasattr(self, "set_list"):
            return
        thumbnails = self.set_thumbnails_enabled()
        self.set_list.setViewMode(QListView.ViewMode.IconMode if thumbnails else QListView.ViewMode.ListMode)
        self.set_list.setIconSize(QSize(118, 64) if thumbnails else QSize(0, 0))
        self.set_list.setGridSize(QSize(142, 98) if thumbnails else QSize())
        self.set_list.setSpacing(6 if thumbnails else 1)
        self.set_list.setWordWrap(thumbnails)
        self.set_list.setWrapping(thumbnails)
        self.set_list.setFlow(QListView.Flow.LeftToRight if thumbnails else QListView.Flow.TopToBottom)
        self.set_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.set_list.setMovement(QListView.Movement.Snap if thumbnails else QListView.Movement.Static)
        self.set_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.set_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.set_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def refresh_set_thumbnails(self) -> None:
        if hasattr(self, "set_list"):
            self.populate_sets()

    def apply_field_logo_visible(self, visible: bool) -> None:
        self.field.set_field_logo_visible(visible)
        self.thumbnail_cache.clear()
        self.refresh_set_thumbnails()
        if hasattr(self, "minimap"):
            self.minimap.update()

    def apply_field_logo_appearance(self) -> None:
        self.field.refresh_field_logo()
        self.thumbnail_cache.clear()
        self.refresh_set_thumbnails()
        if hasattr(self, "minimap"):
            self.minimap.update()

    def set_thumbnail_cache_key(self, set_index: int) -> str:
        drill_set = self.project.sets[set_index]
        payload = {
            "set": drill_set.to_json(),
            "field_mode": getattr(self.field, "field_mode", "white"),
            "theme": self.settings.value("appearance/theme", "dark"),
            "dot_symbol": self.field.dot_symbol if hasattr(self.field, "dot_symbol") else "",
            "field_logo": field_logo_enabled(self.settings),
            "colors": {dot.id: dot.color for dot in self.project.dots},
            "surface": self.project.surface.to_json(),
        }
        return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def set_thumbnail(self, set_index: int) -> QPixmap:
        cache_key = self.set_thumbnail_cache_key(set_index)
        cached = self.thumbnail_cache.get(cache_key)
        if cached is not None and not cached.isNull():
            return QPixmap(cached)
        pixmap = QPixmap(118, 64)
        tokens = theme_tokens(str(self.settings.value("appearance/theme", "dark")), self.settings)
        palette = self.field.field_palette()
        pixmap.fill(QColor(tokens["panel_color"]))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        margin = 4
        field_rect = QRectF(margin, margin, pixmap.width() - margin * 2, pixmap.height() - margin * 2)
        draw_surface_preview(
            painter,
            field_rect,
            self.project.surface,
            palette,
            self.field.field_mode,
            self.field.show_field_logo,
        )
        drill_set = self.project.sets[set_index]
        pixels_per_yard = min(
            field_rect.width() / max(1.0, self.project.surface.width_yards),
            field_rect.height() / max(1.0, self.project.surface.height_yards),
        )
        dot_radius, dot_outline_width = scaled_field_dot_metrics(pixels_per_yard)
        for prop_state in drill_set.prop_positions.values():
            point = field_to_rect(field_rect, self.project.surface, float(prop_state.get("x", 0)), float(prop_state.get("y", 0)))
            x, y = point.x(), point.y()
            raw_width, raw_height = size_to_rect(field_rect, self.project.surface, float(prop_state.get("width", 3)), float(prop_state.get("height", 3)))
            width = max(2.0, raw_width)
            height = max(2.0, raw_height)
            painter.setPen(QPen(QColor(tokens["border_color"]), 0.5))
            painter.setBrush(QColor(229, 57, 53, 155))
            painter.drawRoundedRect(QRectF(x - width / 2, y - height / 2, width, height), 1.5, 1.5)
        for dot_id, position in drill_set.dot_positions.items():
            dot = self.project.dot_by_id(dot_id)
            point = field_to_rect(field_rect, self.project.surface, position[0], position[1])
            draw_dot_symbol(
                painter,
                point,
                dot_radius,
                QColor(dot.color if dot else "#e53935"),
                self.field.dot_symbol,
                rotation_degrees=dot_facing_at_set(self.project, set_index, dot_id),
                outline_color=QColor(tokens["background_color"]),
                outline_width=dot_outline_width,
            )
        painter.end()
        self.thumbnail_cache[cache_key] = QPixmap(pixmap)
        if len(self.thumbnail_cache) > 160:
            for key in list(self.thumbnail_cache)[:40]:
                self.thumbnail_cache.pop(key, None)
        return pixmap

    def populate_sets(self) -> None:
        self._populating_sets = True
        self.set_list.blockSignals(True)
        self.set_list.clear()
        if hasattr(self, "toolbar_set_selector"):
            self.toolbar_set_selector.blockSignals(True)
            self.toolbar_set_selector.clear()
        thumbnails = self.set_thumbnails_enabled()
        for index, drill_set in enumerate(self.project.sets):
            tempo = self.project.active_tempo(index)
            item = QListWidgetItem(
                QIcon(self.set_thumbnail(index)) if thumbnails else QIcon(),
                (
                    f"{drill_set.name}\n{drill_set.start_count}-{drill_set.end_count} | {tempo:g} BPM"
                    if thumbnails
                    else f"{drill_set.name}  ({drill_set.start_count}-{drill_set.end_count}, {tempo:g} BPM)"
                ),
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            tooltip = f"{drill_set.name}: counts {drill_set.start_count}-{drill_set.end_count}, {tempo:g} BPM"
            if drill_set.director_notes.strip():
                note_preview = " ".join(drill_set.director_notes.split())
                ellipsis = "..." if len(note_preview) > 180 else ""
                tooltip += f"\nDirector's Notes: {note_preview[:180]}{ellipsis}"
            item.setToolTip(tooltip)
            self.set_list.addItem(item)
            if hasattr(self, "toolbar_set_selector"):
                self.toolbar_set_selector.addItem(
                    f"{drill_set.name} · {drill_set.start_count}-{drill_set.end_count}",
                    index,
                )
        if hasattr(self, "multi_set_start"):
            for spin in (self.multi_set_start, self.multi_set_end):
                spin.blockSignals(True)
                spin.setRange(1, max(1, len(self.project.sets)))
                spin.blockSignals(False)
        self.set_list.setCurrentRow(self.set_index)
        self.set_list.blockSignals(False)
        if hasattr(self, "toolbar_set_selector"):
            self.toolbar_set_selector.setCurrentIndex(self.set_index)
            self.toolbar_set_selector.blockSignals(False)
        self._populating_sets = False
        self.filter_set_list()
        self.refresh_motion_ribbon_list()

    def change_set(self, index: int) -> None:
        if index < 0:
            return
        item = self.set_list.item(index) if hasattr(self, "set_list") else None
        mapped_index = int(item.data(Qt.ItemDataRole.UserRole)) if item and item.data(Qt.ItemDataRole.UserRole) is not None else index
        if mapped_index < 0 or mapped_index >= len(self.project.sets):
            return
        self.set_index = mapped_index
        if hasattr(self, "toolbar_set_selector") and self.toolbar_set_selector.currentIndex() != mapped_index:
            self.toolbar_set_selector.blockSignals(True)
            self.toolbar_set_selector.setCurrentIndex(mapped_index)
            self.toolbar_set_selector.blockSignals(False)
        self.active_motion_ribbon_id = ""
        self._motion_ribbon_drag_before_sets = None
        self.field.set_motion_path_editing(False)
        self.current_count = self.current_set().start_count
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=True)
        self.sync_inspector()
        self.schedule_live_conflict_analysis()

    def change_set_from_toolbar(self, index: int) -> None:
        if index < 0 or getattr(self, "_populating_sets", False):
            return
        if hasattr(self, "set_list"):
            self.set_list.setCurrentRow(index)
        else:
            self.change_set(index)

    def filter_set_list(self) -> None:
        if not hasattr(self, "set_list"):
            return
        query = self.set_search.text().strip().lower() if hasattr(self, "set_search") else ""
        for row in range(self.set_list.count()):
            item = self.set_list.item(row)
            item.setHidden(bool(query and query not in item.text().lower()))

    def reorder_sets_from_list(self, *_args) -> None:
        if getattr(self, "_populating_sets", False):
            return
        order = [
            int(self.set_list.item(row).data(Qt.ItemDataRole.UserRole))
            for row in range(self.set_list.count())
            if self.set_list.item(row).data(Qt.ItemDataRole.UserRole) is not None
        ]
        if sorted(order) != list(range(len(self.project.sets))):
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        current_set_object = self.current_set()
        self.project.sets = [self.project.sets[index] for index in order]
        self.set_index = next(
            (index for index, drill_set in enumerate(self.project.sets) if drill_set is current_set_object),
            min(before_index, len(self.project.sets) - 1),
        )
        self.current_count = self.current_set().start_count
        self.push_set_snapshot(before_sets, before_index, before_count, "Reorder Sets")
        self.statusBar().showMessage("Sets reordered", 2200)

    def add_set(self, _checked: bool = False, *, remember: bool = True) -> None:
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        previous = self.project.sets[-1]
        start = previous.end_count + 1
        drill_set = DrillSet(
            name=f"Set {len(self.project.sets) + 1}",
            start_count=start,
            end_count=start + self.project.metadata.default_counts_per_set - 1,
            tempo=None,
            dot_positions=dict(previous.dot_positions),
            prop_positions={prop_id: dict(state) for prop_id, state in previous.prop_positions.items()},
        )
        self.project.sets.append(drill_set)
        self.set_index = len(self.project.sets) - 1
        self.current_count = drill_set.start_count
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=True)
        self.push_set_snapshot(before_sets, before_index, before_count, "Add Set")
        if remember:
            self.remember_repeat_action({"type": "set", "action": "add", "label": "Add Set"})

    def copy_set(self, _checked: bool = False, *, remember: bool = True) -> None:
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        source = self.current_set()
        copied = DrillSet(
            name=f"{source.name} Copy",
            start_count=source.end_count + 1,
            end_count=source.end_count + source.duration_counts,
            tempo=source.tempo,
            dot_positions=dict(source.dot_positions),
            dot_facings=dict(source.dot_facings),
            prop_positions={prop_id: dict(state) for prop_id, state in source.prop_positions.items()},
            path_anchors={dot_id: list(anchors) for dot_id, anchors in source.path_anchors.items()},
            path_controls={
                dot_id: [dict(control_set) for control_set in control_sets]
                for dot_id, control_sets in source.path_controls.items()
            },
            count_positions={
                dot_id: dict(keyframes)
                for dot_id, keyframes in source.count_positions.items()
            },
            count_facings={
                dot_id: dict(keyframes)
                for dot_id, keyframes in source.count_facings.items()
            },
            move_timings={
                dot_id: dict(timing)
                for dot_id, timing in source.move_timings.items()
            },
            transition=source.transition,
            movement_styles=dict(source.movement_styles),
            continuity=deepcopy(source.continuity),
            motion_ribbons=deepcopy(source.motion_ribbons),
        )
        self.project.sets.insert(self.set_index + 1, copied)
        self.set_index += 1
        self.current_count = copied.start_count
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=True)
        self.push_set_snapshot(before_sets, before_index, before_count, "Copy Set")
        if remember:
            self.remember_repeat_action({"type": "set", "action": "copy", "label": "Copy Set"})

    def remove_set(self) -> None:
        if len(self.project.sets) <= 1:
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        self.project.sets.pop(self.set_index)
        self.set_index = max(0, self.set_index - 1)
        self.populate_sets()
        self.change_set(self.set_index)
        self.push_set_snapshot(before_sets, before_index, before_count, "Remove Set")

    def update_transition(self, value: str) -> None:
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        transition = Transition(value)
        if self.current_set().transition == transition:
            return
        self.current_set().transition = transition
        self.push_set_snapshot(before_sets, before_index, before_count, "Edit Transition")

    def update_set_length(self, count_length: int) -> None:
        self.set_end_count.blockSignals(True)
        self.set_end_count.setValue(self.set_start_count.value() + count_length - 1)
        self.set_end_count.blockSignals(False)
        self.update_set_details()

    def begin_set_director_notes_edit(self) -> None:
        self._director_notes_edit_before = (
            deepcopy(self.project.sets),
            self.set_index,
            self.current_count,
        )

    def preview_set_director_notes_edit(self) -> None:
        if not self.project.sets:
            return
        self.current_set().director_notes = self.set_director_notes.toPlainText().strip()

    def finish_set_director_notes_edit(self) -> None:
        before = getattr(self, "_director_notes_edit_before", None)
        self._director_notes_edit_before = None
        if before is None:
            return
        before_sets, before_index, before_count = before
        self.current_set().director_notes = self.set_director_notes.toPlainText().strip()
        self.populate_sets()
        self.push_set_snapshot(before_sets, before_index, before_count, "Edit Director's Notes")

    def update_set_details(self) -> None:
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        drill_set = self.current_set()
        old_start = drill_set.start_count
        old_end = drill_set.end_count
        start = self.set_start_count.value()
        end = max(start, self.set_end_count.value())
        if end != self.set_end_count.value():
            self.set_end_count.blockSignals(True)
            self.set_end_count.setValue(end)
            self.set_end_count.blockSignals(False)
        drill_set.name = self.set_name.text().strip() or drill_set.name
        drill_set.start_count = start
        drill_set.end_count = end
        drill_set.tempo = self.set_tempo.value() or None
        drill_set.director_notes = self.set_director_notes.toPlainText().strip()
        if old_start != drill_set.start_count or old_end != drill_set.end_count:
            self.ripple_following_sets()
        self.current_count = max(drill_set.start_count, min(self.current_count, drill_set.end_count))
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=True)
        self.push_set_snapshot(before_sets, before_index, before_count, "Edit Set")

    def ripple_following_sets(self) -> None:
        next_start = self.current_set().end_count + 1
        for drill_set in self.project.sets[self.set_index + 1 :]:
            duration = drill_set.duration_counts
            drill_set.start_count = next_start
            drill_set.end_count = next_start + duration - 1
            next_start = drill_set.end_count + 1

    def sync_set_editor(self) -> None:
        drill_set = self.current_set()
        for widget in (
            self.set_name,
            self.set_start_count,
            self.set_count_length,
            self.set_end_count,
            self.set_tempo,
            self.transition_combo,
            self.set_director_notes,
        ):
            widget.blockSignals(True)
        self.set_name.setText(drill_set.name)
        self.set_start_count.setValue(drill_set.start_count)
        self.set_count_length.setValue(drill_set.duration_counts)
        self.set_end_count.setValue(drill_set.end_count)
        self.set_tempo.setValue(drill_set.tempo or 0)
        self.transition_combo.setCurrentText(drill_set.transition.value)
        self.set_director_notes.setPlainText(drill_set.director_notes)
        for widget in (
            self.set_name,
            self.set_start_count,
            self.set_count_length,
            self.set_end_count,
            self.set_tempo,
            self.transition_combo,
            self.set_director_notes,
        ):
            widget.blockSignals(False)

    def sync_timeline(self) -> None:
        drill_set = self.current_set()
        start_count, end_count = playback_bounds_for_set(self.project, self.set_index)
        self.timeline.blockSignals(True)
        self.timeline.setRange(int(start_count * 100), int(end_count * 100))
        self.timeline.setValue(int(self.current_count * 100))
        self.timeline.blockSignals(False)
        if hasattr(self, "count_finder"):
            self.count_finder.blockSignals(True)
            self.count_finder.setRange(1, max(1, self.project.sets[-1].end_count))
            self.count_finder.setValue(self.current_count)
            self.count_finder.blockSignals(False)
        self.sync_set_editor()
        self.count_label.setText(f"Count {self.current_count:.2f}")
        self.refresh_markers()
        self.refresh_transition_timeline()
        self.refresh_specialized_design()

    def refresh_transition_timeline(self, *_args) -> None:
        if not hasattr(self, "transition_timeline"):
            return
        mode = self.transition_timeline_mode.currentText() if hasattr(self, "transition_timeline_mode") else "Sections"
        self.transition_timeline.set_context(
            self.project,
            self.set_index,
            self.field.selected_dot_ids(),
            mode,
        )

    def apply_timeline_move_window(self, dot_ids: list[str], start: float, end: float) -> None:
        if not dot_ids:
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        source = self.current_set()
        source_span = max(1.0, float(source.end_count - source.start_count))
        start_progress = (start - source.start_count) / source_span
        end_progress = (end - source.start_count) / source_span
        for index in self.selected_set_indices_for_edit(dot_ids):
            drill_set = self.project.sets[index]
            target_span = max(1.0, float(drill_set.end_count - drill_set.start_count))
            timing = self.normalized_move_timing(
                drill_set,
                drill_set.start_count + target_span * start_progress,
                drill_set.start_count + target_span * end_progress,
            )
            for dot_id in dot_ids:
                if self.is_full_set_move_timing(drill_set, timing):
                    drill_set.move_timings.pop(dot_id, None)
                else:
                    drill_set.move_timings[dot_id] = dict(timing)
        self.set_count(self.current_count, seek_audio=False)
        self.push_set_snapshot(before_sets, before_index, before_count, "Edit Movement Lane")
        self.refresh_transition_timeline()

    def scrub(self, value: int) -> None:
        count = value / 100
        target_set_index = set_index_for_count(self.project, count)
        if target_set_index != self.set_index:
            self.set_index = target_set_index
            self.populate_sets()
            self.sync_timeline()
            self.refresh_selected_paths()
        self.set_count(count, seek_audio=True)

    def set_count(
        self,
        count: float,
        seek_audio: bool = False,
        update_waveform: bool = True,
        refresh_paths: bool = True,
        playback_optimized: bool = False,
    ) -> None:
        start_count, end_count = playback_bounds_for_set(self.project, self.set_index)
        self.current_count = max(start_count, min(count, end_count))
        self.field.set_reference_set_index(self.set_index)
        positions, facings, prop_states = self.playback_frame_state(
            self.set_index,
            self.current_count,
            use_cache=playback_optimized,
        )
        self.field.set_positions(positions)
        self.field.set_facings(facings)
        self.field.set_prop_states(prop_states)
        self.update_selected_coordinate_readout(positions)
        if not playback_optimized or self._ghost_set_index != self.set_index:
            self.refresh_previous_set_ghosts()
        self.count_label.setText(f"Count {self.current_count:.2f}")
        if hasattr(self, "count_finder"):
            self.count_finder.blockSignals(True)
            self.count_finder.setValue(self.current_count)
            self.count_finder.blockSignals(False)
        self.timeline.blockSignals(True)
        self.timeline.setValue(int(self.current_count * 100))
        self.timeline.blockSignals(False)
        if seek_audio and self.player.source().isValid():
            target_position = self.audio_position_for_count(self.set_index, self.current_count)
            self.last_playback_audio_ms = target_position
            self.player.setPosition(target_position)
        elif update_waveform and hasattr(self, "waveform"):
            self.waveform.set_position_ms(self.audio_position_for_count(self.set_index, self.current_count))
        if refresh_paths:
            self.refresh_selected_paths()
        self.playback_auxiliary_frame += 1
        auxiliary_stride = self.playback_scheduler.quality.auxiliary_stride if playback_optimized else 1
        if not playback_optimized or self.playback_auxiliary_frame % auxiliary_stride == 0:
            self.refresh_measurements()
            if hasattr(self, "minimap"):
                self.minimap.update()
            if hasattr(self, "choreography_timeline"):
                self.choreography_timeline.set_current_count(self.current_count)

    def playback_frame_state(
        self,
        set_index: int,
        count: float,
        *,
        use_cache: bool,
    ) -> tuple[dict, dict, dict]:
        cache_enabled = self.settings.value("performance/playback_cache", True, type=bool)
        key = self.playback_frame_cache.key(set_index, count, self.playback_scheduler.quality)
        if use_cache and cache_enabled:
            cached = self.playback_frame_cache.get(key)
            if cached is not None:
                return cached
        frame = (
            interpolate_project(self.project, set_index, count),
            interpolate_dot_facings(self.project, set_index, count),
            interpolate_props(self.project, set_index, count),
        )
        if use_cache and cache_enabled:
            self.playback_frame_cache.put(key, frame)
        return frame

    def reset_playback_diagnostics(self) -> None:
        self.playback_scheduler.reset(perf_counter() * 1000.0)
        self.playback_frame_cache.clear()
        self.refresh_playback_diagnostics(force=True)

    def refresh_playback_diagnostics(self, *, force: bool = False) -> None:
        if not hasattr(self, "playback_diagnostics_label"):
            return
        now_ms = perf_counter() * 1000.0
        if not force and now_ms - self._last_playback_diagnostics_update_ms < 250:
            return
        self._last_playback_diagnostics_update_ms = now_ms
        snapshot = self.playback_scheduler.snapshot()
        cache_total = self.playback_frame_cache.hits + self.playback_frame_cache.misses
        cache_percent = int(round(self.playback_frame_cache.hits / cache_total * 100)) if cache_total else 0
        self.playback_diagnostics_label.setText(
            f"{snapshot.displayed_fps:4.1f} FPS  |  Dropped {snapshot.dropped_frames} "
            f"(late {snapshot.missed_deadlines}, adaptive {snapshot.adaptive_skips})  |  "
            f"{snapshot.average_render_ms:.1f} ms avg / {snapshot.p95_render_ms:.1f} p95  |  "
            f"{snapshot.quality.label}  |  Cache {cache_percent}%"
        )

    def finish_playback_frame(self, render_started: float) -> None:
        render_ms = (perf_counter() - render_started) * 1000.0
        measured_ms = render_ms + max(0.0, self.field.last_paint_duration_ms)
        self.playback_scheduler.record_render(measured_ms, perf_counter() * 1000.0)
        quality = self.playback_scheduler.consume_quality_change()
        if quality is not None:
            self.field.set_playback_quality(quality.name.lower(), len(self.project.dots))
            self.statusBar().showMessage(
                f"Playback quality changed to {quality.label} to maintain real-time timing.",
                3500,
            )
        self.refresh_playback_diagnostics()

    def play(self) -> None:
        if self.play_timer.isActive():
            return
        self.audio_recovery_resume_requested = False
        self.playback_scheduler.set_adaptive(
            self.settings.value("performance/adaptive_playback", True, type=bool)
        )
        self.playback_scheduler.reset(perf_counter() * 1000.0)
        self.playback_frame_cache.clear()
        self.playback_auxiliary_frame = 0
        self.field.set_playback_quality("full", len(self.project.dots))
        if self.player.source().isValid():
            self.last_playback_audio_ms = self.audio_position_for_count(self.set_index, self.current_count)
            self.player.setPosition(self.last_playback_audio_ms)
            self.player.setPlaybackRate(self.current_playback_rate())
        self.playback_clock.restart()
        self.field.set_transform_gizmo_suspended(True)
        self.play_timer.start()
        if self.player.source().isValid():
            self.player.play()
        self.refresh_selected_paths()
        self.refresh_playback_diagnostics(force=True)

    def pause(self) -> None:
        self.audio_recovery_resume_requested = False
        self.play_timer.stop()
        if self.player.source().isValid():
            self.player.pause()
        self.field.set_playback_quality("full", len(self.project.dots))
        self.field.set_transform_gizmo_suspended(False)
        self.refresh_selected_paths()
        self.refresh_playback_diagnostics(force=True)

    def toggle_playback(self) -> None:
        if self.play_timer.isActive():
            self.pause()
        else:
            self.play()

    def tick_playback(self) -> None:
        callback_ms = perf_counter() * 1000.0
        if not self.playback_scheduler.should_render(callback_ms):
            self.refresh_playback_diagnostics()
            return
        render_started = perf_counter()
        if self.player.source().isValid():
            audio_position = self.player.position()
            if audio_position + 80 < self.last_playback_audio_ms:
                audio_position = self.last_playback_audio_ms
            else:
                self.last_playback_audio_ms = audio_position
            self.playback_scheduler.record_audio_clock(audio_position)
            loop_start_count, loop_end_count = playback_bounds_for_set(self.project, self.set_index)
            loop_start_ms = self.audio_position_for_count(self.set_index, loop_start_count)
            loop_end_ms = self.audio_position_for_count(self.set_index, loop_end_count)
            if self.loop_current_set.isChecked() and audio_position >= max(loop_start_ms, loop_end_ms - 2):
                self.current_count = loop_start_count
                self.last_playback_audio_ms = loop_start_ms
                self.playback_scheduler.record_audio_clock(loop_start_ms, seeking=True)
                self.player.setPosition(loop_start_ms)
                self.set_count(
                    self.current_count,
                    seek_audio=False,
                    update_waveform=False,
                    refresh_paths=False,
                    playback_optimized=True,
                )
                self.finish_playback_frame(render_started)
                return
            next_set_index, next_count = self.count_for_audio_position(audio_position)
            if hasattr(self, "waveform"):
                self.waveform.set_position_ms(audio_position)
            if next_set_index != self.set_index:
                self.set_index = next_set_index
                self.current_count = next_count
                self.populate_sets()
                self.sync_timeline()
                self.refresh_selected_paths()
            else:
                self.current_count = next_count
            last_set_index = max(0, len(self.project.sets) - 1)
            _show_start, show_end_count = playback_bounds_for_set(self.project, last_set_index)
            show_end_ms = self.audio_position_for_count(last_set_index, show_end_count)
            reached_show_end = self.set_index == last_set_index and audio_position >= max(0, show_end_ms - 2)
            if reached_show_end:
                self.current_count = show_end_count
            self.set_count(
                self.current_count,
                seek_audio=False,
                update_waveform=False,
                refresh_paths=False,
                playback_optimized=True,
            )
            self.finish_playback_frame(render_started)
            if reached_show_end:
                self.pause()
            return

        tempo = self.project.active_tempo(self.set_index)
        elapsed_ms = self.playback_clock.restart() if self.playback_clock.isValid() else self.play_timer.interval()
        elapsed_ms = max(1, elapsed_ms)
        self.current_count += (tempo / 60) * (elapsed_ms / 1000) * self.current_playback_rate()
        reached_show_end = False
        _start_count, playback_end_count = playback_bounds_for_set(self.project, self.set_index)
        if self.current_count > playback_end_count:
            if self.loop_current_set.isChecked():
                self.current_count = self.current_set().start_count
                if self.player.source().isValid():
                    self.last_playback_audio_ms = self.audio_position_for_count(self.set_index, self.current_count)
                    self.player.setPosition(self.last_playback_audio_ms)
            elif self.set_index + 1 < len(self.project.sets):
                overflow = self.current_count - playback_end_count
                self.set_index += 1
                self.current_count = self.current_set().start_count + overflow
                self.populate_sets()
                self.sync_timeline()
                self.refresh_selected_paths()
            else:
                reached_show_end = True
                self.current_count = self.current_set().end_count
        self.set_count(
            self.current_count,
            seek_audio=False,
            refresh_paths=False,
            playback_optimized=True,
        )
        self.finish_playback_frame(render_started)
        if reached_show_end:
            self.pause()

    def current_playback_rate(self) -> float:
        if not hasattr(self, "playback_rate"):
            return 1.0
        return float(self.playback_rate.currentText().replace("x", ""))

    def update_playback_rate(self) -> None:
        if self.player.source().isValid():
            self.player.setPlaybackRate(self.current_playback_rate())

    def apply_playback_performance_settings(self, adaptive: bool, cache_enabled: bool) -> None:
        self.playback_scheduler.set_adaptive(bool(adaptive))
        if not cache_enabled:
            self.playback_frame_cache.clear()
        if not self.play_timer.isActive():
            self.field.set_playback_quality("full", len(self.project.dots))
        self.refresh_playback_diagnostics(force=True)
        self.statusBar().showMessage(
            f"Playback optimization: {'adaptive' if adaptive else 'full quality'}, "
            f"cache {'on' if cache_enabled else 'off'}",
            3000,
        )

    def toggle_loop_current_set(self) -> None:
        self.loop_current_set.setChecked(not self.loop_current_set.isChecked())

    def focus_count_finder(self) -> None:
        self.count_finder.setFocus()
        self.count_finder.selectAll()

    def go_to_requested_count(self) -> None:
        target = self.count_finder.value()
        for index, drill_set in enumerate(self.project.sets):
            if drill_set.start_count <= target <= drill_set.end_count:
                self.set_index = index
                self.populate_sets()
                self.sync_timeline()
                self.set_count(target, seek_audio=True)
                return
        self.set_count(target, seek_audio=True)

    def audio_position_for_count(self, set_index: int, count: float) -> int:
        return audio_ms_for_set_count(self.project, set_index, count)

    def count_for_audio_position(self, position_ms: int) -> tuple[int, float]:
        return set_count_for_audio_ms(self.project, position_ms)

    def add_marker(self) -> None:
        self.project.markers.append(Marker(count=self.current_count, label=f"Hit {len(self.project.markers) + 1}"))
        self.refresh_markers()

    def add_count_markers_for_set(self) -> None:
        drill_set = self.current_set()
        existing = {(round(marker.count, 2), marker.label) for marker in self.project.markers}
        for count in range(drill_set.start_count, drill_set.end_count + 1):
            marker = Marker(count=float(count), label=f"{drill_set.name} Count {count}")
            key = (round(marker.count, 2), marker.label)
            if key not in existing:
                self.project.markers.append(marker)
        self.refresh_markers()
        self.statusBar().showMessage("Count markers added", 2000)

    def auto_detect_hit_markers(self) -> None:
        if not hasattr(self, "waveform") or self.waveform.duration_ms <= 0:
            QMessageBox.information(self, "Auto Hit Markers", "Load audio before detecting hit markers.")
            return
        hit_moments = self.waveform.detect_hit_moments()
        if not hit_moments:
            QMessageBox.information(self, "Auto Hit Markers", "No clear hit moments were detected in the waveform.")
            return
        existing_counts = [round(marker.count, 2) for marker in self.project.markers]
        added = 0
        for hit_ms in hit_moments:
            _set_index, count = set_count_for_audio_ms(self.project, hit_ms)
            rounded_count = round(count, 2)
            if any(abs(rounded_count - existing_count) < 0.18 for existing_count in existing_counts):
                continue
            self.project.markers.append(Marker(count=rounded_count, label=f"Auto Hit {added + 1}"))
            existing_counts.append(rounded_count)
            added += 1
        self.refresh_markers()
        if hasattr(self, "waveform"):
            self.waveform.update()
        self.statusBar().showMessage(f"Added {added} auto hit marker(s)", 2500)

    def apply_movement_style_to_selected(self) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            QMessageBox.information(self, "Movement Style", "Select one or more marchers first.")
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        style = MovementStyle(str(self.movement_style_combo.currentData() or MovementStyle.NORMAL.value))
        for index in self.selected_set_indices_for_edit(ids):
            drill_set = self.project.sets[index]
            for dot_id in ids:
                if style == MovementStyle.NORMAL:
                    drill_set.movement_styles.pop(dot_id, None)
                else:
                    drill_set.movement_styles[dot_id] = style
        self.sync_movement_style_controls()
        self.push_set_snapshot(before_sets, before_index, before_count, "Apply Movement Style")
        self.statusBar().showMessage(f"Applied {self.movement_style_combo.currentText()} to {len(ids)} marcher(s)", 2400)

    def clear_movement_style_for_selected(self) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        for index in self.selected_set_indices_for_edit(ids):
            for dot_id in ids:
                self.project.sets[index].movement_styles.pop(dot_id, None)
        self.sync_movement_style_controls()
        self.push_set_snapshot(before_sets, before_index, before_count, "Clear Movement Style")
        self.statusBar().showMessage(f"Cleared movement style for {len(ids)} marcher(s)", 2200)

    def normalized_move_timing(self, drill_set: DrillSet, start: float, end: float) -> dict[str, float]:
        set_start = float(drill_set.start_count)
        set_end = float(drill_set.end_count)
        move_start = max(set_start, min(float(start), set_end))
        move_end = max(move_start, min(float(end), set_end))
        return {"start": move_start, "end": move_end}

    def is_full_set_move_timing(self, drill_set: DrillSet, timing: dict[str, float]) -> bool:
        return (
            abs(float(timing.get("start", drill_set.start_count)) - float(drill_set.start_count)) < 0.0001
            and abs(float(timing.get("end", drill_set.end_count)) - float(drill_set.end_count)) < 0.0001
        )

    def apply_move_timing_to_selected(self) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            QMessageBox.information(self, "Move Window", "Select one or more marchers first.")
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        source_set = self.current_set()
        timing = self.normalized_move_timing(source_set, self.move_start_count.value(), self.move_end_count.value())
        source_span = max(1.0, source_set.end_count - source_set.start_count)
        start_progress = (timing["start"] - source_set.start_count) / source_span
        end_progress = (timing["end"] - source_set.start_count) / source_span
        for index in self.selected_set_indices_for_edit(ids):
            drill_set = self.project.sets[index]
            target_span = max(1.0, drill_set.end_count - drill_set.start_count)
            target_timing = self.normalized_move_timing(
                drill_set,
                drill_set.start_count + start_progress * target_span,
                drill_set.start_count + end_progress * target_span,
            )
            for dot_id in ids:
                if self.is_full_set_move_timing(drill_set, target_timing):
                    drill_set.move_timings.pop(dot_id, None)
                else:
                    drill_set.move_timings[dot_id] = dict(target_timing)
        self.sync_movement_style_controls()
        self.set_count(self.current_count, seek_audio=False)
        self.push_set_snapshot(before_sets, before_index, before_count, "Set Marcher Move Window")
        self.statusBar().showMessage(
            f"Move window {timing['start']:g}-{timing['end']:g} applied to {len(ids)} marcher(s)",
            2600,
        )

    def start_selected_move_at_current_count(self) -> None:
        if not self.field.selected_dot_ids():
            QMessageBox.information(self, "Move Window", "Select one or more marchers first.")
            return
        drill_set = self.current_set()
        timing = self.normalized_move_timing(drill_set, self.current_count, drill_set.end_count)
        self.move_start_count.setValue(timing["start"])
        self.move_end_count.setValue(timing["end"])
        self.apply_move_timing_to_selected()

    def clear_move_timing_for_selected(self) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        changed = False
        for index in self.selected_set_indices_for_edit(ids):
            drill_set = self.project.sets[index]
            for dot_id in ids:
                changed = dot_id in drill_set.move_timings or changed
                drill_set.move_timings.pop(dot_id, None)
        if not changed:
            return
        self.sync_movement_style_controls()
        self.set_count(self.current_count, seek_audio=False)
        self.push_set_snapshot(before_sets, before_index, before_count, "Clear Marcher Move Window")
        self.statusBar().showMessage(f"Full-set timing restored for {len(ids)} marcher(s)", 2200)

    def normalize_facing(self, angle: float) -> float:
        return float(angle) % 360.0

    def apply_facing_to_selected(self) -> None:
        self.set_selected_facing(self.facing_degrees.value())

    def set_selected_facing(self, angle: float) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            QMessageBox.information(self, "Marcher Facing", "Select one or more marchers first.")
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        facing = self.normalize_facing(angle)
        for index in self.selected_set_indices_for_edit(ids):
            drill_set = self.project.sets[index]
            for dot_id in ids:
                drill_set.dot_facings[dot_id] = facing
                drill_set.count_facings.pop(dot_id, None)
        self.set_count(self.current_count, seek_audio=False)
        self.sync_facing_controls()
        self.push_set_snapshot(before_sets, before_index, before_count, "Set Marcher Facing")
        self.statusBar().showMessage(f"Facing {facing:g}° applied to {len(ids)} marcher(s)", 2400)

    def rotate_selected_facing(self, delta_degrees: float) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            QMessageBox.information(self, "Marcher Facing", "Select one or more marchers first.")
            return
        before_sets = deepcopy(self.project.sets)
        before_index = self.set_index
        before_count = self.current_count
        for index in self.selected_set_indices_for_edit(ids):
            drill_set = self.project.sets[index]
            for dot_id in ids:
                drill_set.dot_facings[dot_id] = self.normalize_facing(
                    dot_facing_at_set(self.project, index, dot_id) + delta_degrees
                )
                drill_set.count_facings.pop(dot_id, None)
        self.set_count(self.current_count, seek_audio=False)
        self.sync_facing_controls()
        self.push_set_snapshot(before_sets, before_index, before_count, "Rotate Marcher Facing")
        self.statusBar().showMessage(f"Rotated facing by {delta_degrees:g}° for {len(ids)} marcher(s)", 2200)

    def sync_facing_controls(self) -> None:
        if not hasattr(self, "facing_degrees"):
            return
        ids = self.field.selected_dot_ids()
        has_selection = bool(ids)
        for widget in [*getattr(self, "facing_widgets", []), *getattr(self, "selection_facing_widgets", [])]:
            widget.setEnabled(has_selection)
        if not has_selection:
            self.facing_degrees.setValue(0)
            if hasattr(self, "selection_facing_degrees"):
                self.selection_facing_degrees.setValue(0)
            self.facing_status.setText("Select marchers to set triangle facing direction.")
            if hasattr(self, "selection_facing_status"):
                self.selection_facing_status.setText("Select marchers to set facing.")
            return
        facings = [round(dot_facing_at_set(self.project, self.set_index, dot_id), 1) for dot_id in ids]
        unique_facings = set(facings)
        value = facings[0] if len(unique_facings) == 1 else 0
        for spin_box in (self.facing_degrees, getattr(self, "selection_facing_degrees", None)):
            if spin_box is None:
                continue
            spin_box.blockSignals(True)
            spin_box.setValue(value)
            spin_box.blockSignals(False)
        if len(unique_facings) == 1:
            self.facing_status.setText(f"{len(ids)} selected: facing {facings[0]:g}°.")
            if hasattr(self, "selection_facing_status"):
                self.selection_facing_status.setText(f"{len(ids)} selected: facing {facings[0]:g}°.")
        else:
            self.facing_status.setText(f"{len(ids)} selected: mixed facing directions. Apply sets one shared direction; rotate keeps relative directions.")
            if hasattr(self, "selection_facing_status"):
                self.selection_facing_status.setText(f"{len(ids)} selected: mixed facing. Apply sets one shared direction.")

    def sync_movement_style_controls(self) -> None:
        if not hasattr(self, "movement_style_status"):
            return
        ids = self.field.selected_dot_ids()
        has_selection = bool(ids)
        self.movement_style_combo.setEnabled(has_selection)
        for widget in getattr(self, "move_timing_widgets", []):
            widget.setEnabled(has_selection)
        drill_set = self.current_set()
        self.move_start_count.setRange(drill_set.start_count, drill_set.end_count)
        self.move_end_count.setRange(drill_set.start_count, drill_set.end_count)
        if not has_selection:
            self.move_start_count.setValue(drill_set.start_count)
            self.move_end_count.setValue(drill_set.end_count)
            self.movement_style_status.setText("Select marchers to set style for this set.")
            return
        styles = [
            drill_set.movement_styles.get(dot_id, MovementStyle.NORMAL)
            for dot_id in ids
        ]
        timings = [
            self.normalized_move_timing(
                drill_set,
                drill_set.move_timings.get(dot_id, {}).get("start", drill_set.start_count),
                drill_set.move_timings.get(dot_id, {}).get("end", drill_set.end_count),
            )
            for dot_id in ids
        ]
        timing_pairs = {(round(timing["start"], 2), round(timing["end"], 2)) for timing in timings}
        if len(timing_pairs) == 1:
            timing = timings[0]
            self.move_start_count.blockSignals(True)
            self.move_end_count.blockSignals(True)
            self.move_start_count.setValue(timing["start"])
            self.move_end_count.setValue(timing["end"])
            self.move_start_count.blockSignals(False)
            self.move_end_count.blockSignals(False)
            timing_text = f"move counts {timing['start']:g}-{timing['end']:g}"
        else:
            self.move_start_count.blockSignals(True)
            self.move_end_count.blockSignals(True)
            self.move_start_count.setValue(drill_set.start_count)
            self.move_end_count.setValue(drill_set.end_count)
            self.move_start_count.blockSignals(False)
            self.move_end_count.blockSignals(False)
            timing_text = "mixed move windows"
        unique_styles = set(styles)
        if len(unique_styles) == 1:
            style = styles[0]
            index = self.movement_style_combo.findData(style.value)
            if index >= 0:
                self.movement_style_combo.blockSignals(True)
                self.movement_style_combo.setCurrentIndex(index)
                self.movement_style_combo.blockSignals(False)
            self.movement_style_status.setText(
                f"{len(ids)} selected: {self.movement_style_combo.currentText()}, {timing_text} for {self.current_set().name}."
            )
        else:
            self.movement_style_status.setText(
                f"{len(ids)} selected: mixed movement styles, {timing_text} for {self.current_set().name}."
            )

    def refresh_markers(self) -> None:
        self.marker_table.setRowCount(len(self.project.markers))
        for row, marker in enumerate(self.project.markers):
            self.marker_table.setItem(row, 0, QTableWidgetItem(f"{marker.count:.2f}"))
            self.marker_table.setItem(row, 1, QTableWidgetItem(marker.label))

    def refresh_marcher_table(self) -> None:
        if not hasattr(self, "marcher_table"):
            return
        self.marcher_table.blockSignals(True)
        self.marcher_table.clearSelection()
        self.marcher_table.setRowCount(len(self.project.dots))
        for row, dot in enumerate(self.project.dots):
            color_item = QTableWidgetItem("")
            name_item = QTableWidgetItem(dot.name)
            instrument_item = QTableWidgetItem(dot.instrument or "-")
            section_item = QTableWidgetItem(dot.section or "-")
            color_item.setBackground(QColor(dot.color or "#e53935"))
            color_item.setToolTip(f"{dot.name}: {dot.color or '#e53935'}")
            name_item.setToolTip(f"Internal ID: {dot.id}")
            instrument_item.setToolTip(dot.instrument or "No instrument assigned")
            section_item.setToolTip(dot.section or "No section assigned")
            for item in (color_item, name_item, instrument_item, section_item):
                item.setData(Qt.ItemDataRole.UserRole, dot.id)
            color_item.setFlags(color_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.marcher_table.setItem(row, 0, color_item)
            self.marcher_table.setItem(row, 1, name_item)
            self.marcher_table.setItem(row, 2, instrument_item)
            self.marcher_table.setItem(row, 3, section_item)
        self.marcher_table.blockSignals(False)
        self.refresh_marcher_filter_values()
        self.filter_marcher_table()
        self.sync_marcher_table_selection()

    def refresh_marcher_filter_values(self) -> None:
        if not hasattr(self, "marcher_filter_value") or not hasattr(self, "marcher_filter_field"):
            return
        field_name = str(self.marcher_filter_field.currentData() or "all")
        previous = self.marcher_filter_value.currentData()
        self.marcher_filter_value.blockSignals(True)
        self.marcher_filter_value.clear()
        self.marcher_filter_value.addItem("All values", "")
        if field_name != "all":
            values = sorted(
                {str(getattr(dot, field_name, "")).strip() for dot in self.project.dots if getattr(dot, field_name, "")},
                key=str.casefold,
            )
            if any(not str(getattr(dot, field_name, "")).strip() for dot in self.project.dots):
                self.marcher_filter_value.addItem("(Unassigned)", "__unassigned__")
            for value in values:
                self.marcher_filter_value.addItem(value, value)
        matched_index = self.marcher_filter_value.findData(previous)
        self.marcher_filter_value.setCurrentIndex(max(0, matched_index))
        self.marcher_filter_value.setEnabled(field_name != "all")
        self.marcher_filter_value.blockSignals(False)
        self.filter_marcher_table()

    def filter_marcher_table(self) -> None:
        if not hasattr(self, "marcher_table"):
            return
        query = self.marcher_search.text().strip().casefold() if hasattr(self, "marcher_search") else ""
        field_name = str(self.marcher_filter_field.currentData() or "all") if hasattr(self, "marcher_filter_field") else "all"
        filter_value = self.marcher_filter_value.currentData() if hasattr(self, "marcher_filter_value") else ""
        shown = 0
        for row in range(self.marcher_table.rowCount()):
            values: list[str] = []
            for column in range(self.marcher_table.columnCount()):
                item = self.marcher_table.item(row, column)
                if item:
                    values.append(item.text())
            item = self.marcher_table.item(row, 0)
            dot_id = str(item.data(Qt.ItemDataRole.UserRole)) if item else ""
            dot = self.project.dot_by_id(dot_id) if dot_id else None
            if dot:
                values.extend([dot.instrument, dot.rank, dot.equipment, dot.layer])
            haystack = " ".join(values).casefold()
            matches_search = not query or query in haystack
            matches_filter = True
            if dot and field_name != "all" and filter_value:
                attribute_value = str(getattr(dot, field_name, "")).strip()
                matches_filter = (
                    not attribute_value
                    if filter_value == "__unassigned__"
                    else attribute_value.casefold() == str(filter_value).casefold()
                )
            hidden = not (matches_search and matches_filter)
            self.marcher_table.setRowHidden(row, hidden)
            if not hidden:
                shown += 1
        self.update_marcher_filter_status(shown)

    def update_marcher_filter_status(self, shown: int | None = None) -> None:
        if not hasattr(self, "marcher_filter_status") or not hasattr(self, "marcher_table"):
            return
        if shown is None:
            shown = sum(not self.marcher_table.isRowHidden(row) for row in range(self.marcher_table.rowCount()))
        selected = len(self.field.selected_dot_ids()) if hasattr(self, "field") else 0
        self.marcher_filter_status.setText(f"{shown} shown • {selected} selected")

    def sync_marcher_table_selection(self) -> None:
        if not hasattr(self, "marcher_table") or not hasattr(self, "field"):
            return
        selected_ids = set(self.field.selected_dot_ids())
        self.marcher_table.blockSignals(True)
        self.marcher_table.clearSelection()
        for row in range(self.marcher_table.rowCount()):
            item = self.marcher_table.item(row, 0)
            dot_id = str(item.data(Qt.ItemDataRole.UserRole)) if item else ""
            if dot_id in selected_ids:
                for column in range(self.marcher_table.columnCount()):
                    cell = self.marcher_table.item(row, column)
                    if cell:
                        cell.setSelected(True)
        self.marcher_table.blockSignals(False)
        self.update_marcher_filter_status()

    def select_visible_marchers(self) -> None:
        if not hasattr(self, "marcher_table"):
            return
        selected_ids: list[str] = []
        for row in range(self.marcher_table.rowCount()):
            if self.marcher_table.isRowHidden(row):
                continue
            item = self.marcher_table.item(row, 0)
            if item:
                selected_ids.append(str(item.data(Qt.ItemDataRole.UserRole)))
        self.select_dot_ids(selected_ids)
        self.statusBar().showMessage(f"Selected {len(selected_ids)} visible marcher(s)", 2000)

    def clear_marcher_selection(self) -> None:
        self.select_dot_ids([])

    def refresh_prop_table(self) -> None:
        if not hasattr(self, "prop_table"):
            return
        selected = set(self.field.selected_prop_ids()) if hasattr(self, "field") else set()
        self.prop_table.blockSignals(True)
        self.prop_table.clearSelection()
        self.prop_table.setRowCount(len(self.project.props))
        for row, prop in enumerate(self.project.props):
            id_item = QTableWidgetItem(prop.id)
            name_item = QTableWidgetItem(prop.name)
            layer_item = QTableWidgetItem(prop.layer or "Props")
            for item in (id_item, name_item, layer_item):
                item.setData(Qt.ItemDataRole.UserRole, prop.id)
            self.prop_table.setItem(row, 0, id_item)
            self.prop_table.setItem(row, 1, name_item)
            self.prop_table.setItem(row, 2, layer_item)
            if prop.id in selected:
                self.prop_table.selectRow(row)
        self.prop_table.blockSignals(False)

    def select_marchers_from_table(self) -> None:
        if not hasattr(self, "marcher_table"):
            return
        selected_ids: list[str] = []
        for index in self.marcher_table.selectionModel().selectedRows(0):
            item = self.marcher_table.item(index.row(), 0)
            if item:
                selected_ids.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
        self.select_dot_ids([dot_id for dot_id in selected_ids if dot_id])

    def edit_marcher_table_cell(self, row: int, column: int) -> None:
        item = self.marcher_table.item(row, 0)
        if not item:
            return
        dot_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        dot = self.project.dot_by_id(dot_id)
        if not dot:
            return
        if column == 0:
            color = QColorDialog.getColor(QColor(dot.color or "#e53935"), self, f"Choose {dot.id} Color")
            if not color.isValid():
                return
            before = {dot_id: {"color": dot.color or "#e53935"}}
            after = {dot_id: {"color": color.name()}}
            self.undo_stack.push(DotAppearanceCommand(self, before, after, f"Color {dot.id}"))
            return
        if column in (1, 2, 3):
            edit_item = self.marcher_table.item(row, column)
            if edit_item:
                self.marcher_table.editItem(edit_item)

    def update_marcher_from_table(self, item: QTableWidgetItem) -> None:
        if not item or item.column() not in (1, 2, 3):
            return
        dot_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        dot = self.project.dot_by_id(dot_id)
        if not dot:
            return
        field_name = {1: "name", 2: "instrument", 3: "section"}[item.column()]
        value = item.text().strip()
        if field_name in {"instrument", "section"} and value == "-":
            value = ""
        old_value = str(getattr(dot, field_name))
        if value == old_value:
            return
        before = {dot_id: {field_name: old_value}}
        after = {dot_id: {field_name: value}}
        self.undo_stack.push(DotAppearanceCommand(self, before, after, f"Edit {dot.id}"))

    def edit_dot_from_field(self, dot_id: str) -> None:
        dot = self.project.dot_by_id(dot_id)
        if not dot:
            return
        name, accepted = QInputDialog.getText(self, "Edit Marcher Label", "Name:", text=dot.name)
        if not accepted:
            return
        name = name.strip()
        if not name or name == dot.name:
            return
        before = {dot_id: {"name": dot.name}}
        after = {dot_id: {"name": name}}
        self.undo_stack.push(DotAppearanceCommand(self, before, after, f"Rename {dot.id}"))

    def select_prop_from_table(self, row: int, _column: int) -> None:
        item = self.prop_table.item(row, 0)
        if not item:
            return
        prop_id = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
        for dot_item in self.field.dot_items.values():
            dot_item.setSelected(False)
        for prop_item in self.field.prop_items.values():
            prop_item.setSelected(False)
        if prop_id in self.field.prop_items:
            self.field.prop_items[prop_id].setSelected(True)
            self.field.centerOn(self.field.prop_items[prop_id])
        self.selection_changed()

    def selected_dot_colors(self, ids: list[str]) -> list[str]:
        colors: list[str] = []
        for dot_id in ids:
            dot = self.project.dot_by_id(dot_id)
            if dot:
                colors.append(dot.color or "#e53935")
        return colors

    def update_selected_color_swatch(self, ids: list[str]) -> None:
        if not hasattr(self, "selected_color_swatch"):
            return
        colors = self.selected_dot_colors(ids)
        if not colors:
            self.selected_color_swatch.setText("No selection")
            self.selected_color_swatch.setStyleSheet("")
            return
        unique_colors = sorted(set(colors))
        if len(unique_colors) == 1:
            color = QColor(unique_colors[0])
            text_color = "#101419" if color.lightness() > 145 else "#ffffff"
            self.selected_color_swatch.setText(unique_colors[0])
            self.selected_color_swatch.setStyleSheet(
                f"background: {unique_colors[0]}; color: {text_color}; "
                "border: 1px solid #4c5566; border-radius: 5px; padding: 3px 6px; font-weight: 650;"
            )
            return
        self.selected_color_swatch.setText("Mixed")
        self.selected_color_swatch.setStyleSheet(
            "background: #252b35; color: #f7d154; border: 1px solid #4c5566; "
            "border-radius: 5px; padding: 3px 6px; font-weight: 650;"
        )

    def refresh_appearance_groups(self) -> None:
        if not hasattr(self, "section_color_combo"):
            return
        current_section = self.section_color_combo.currentText()
        selected_sections = [
            dot.section
            for dot_id in self.field.selected_dot_ids()
            if (dot := self.project.dot_by_id(dot_id)) and dot.section
        ]
        sections = sorted({dot.section for dot in self.project.dots if dot.section})
        preferred_section = (
            current_section
            if current_section in sections
            else selected_sections[0]
            if selected_sections
            else sections[0]
            if sections
            else ""
        )
        self.section_color_combo.blockSignals(True)
        self.section_color_combo.clear()
        self.section_color_combo.addItems(sections)
        if preferred_section:
            self.section_color_combo.setCurrentText(preferred_section)
        self.section_color_combo.blockSignals(False)
        has_sections = bool(sections)
        self.section_color_combo.setEnabled(has_sections)
        self.section_color_button.setEnabled(has_sections)

    def choose_selected_dot_color(self) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            QMessageBox.information(self, "Dot Color", "Select one or more marchers first.")
            return
        colors = self.selected_dot_colors(ids)
        initial = QColor(colors[0] if colors else "#e53935")
        color = QColorDialog.getColor(initial, self, "Choose Selected Marcher Color")
        if not color.isValid():
            return
        before: dict[str, dict[str, str]] = {}
        after: dict[str, dict[str, str]] = {}
        for dot_id in ids:
            dot = self.project.dot_by_id(dot_id)
            if not dot:
                continue
            before[dot_id] = {"color": dot.color or "#e53935"}
            after[dot_id] = {"color": color.name()}
        if after:
            self.undo_stack.push(DotAppearanceCommand(self, before, after, "Color Selected Marchers"))

    def choose_section_color(self) -> None:
        section = self.section_color_combo.currentText().strip()
        if not section:
            QMessageBox.information(self, "Section Color", "Create or choose a section first.")
            return
        target_dots = [dot for dot in self.project.dots if dot.section == section]
        if not target_dots:
            return
        color = QColorDialog.getColor(
            QColor(target_dots[0].color or "#e53935"),
            self,
            f"Choose {section} Color",
        )
        if not color.isValid():
            return
        before = {dot.id: {"color": dot.color or "#e53935"} for dot in target_dots}
        after = {dot.id: {"color": color.name()} for dot in target_dots}
        self.undo_stack.push(DotAppearanceCommand(self, before, after, f"Color {section} Section"))

    def assign_selected_section(self) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            QMessageBox.information(self, "Set Section", "Select one or more marchers first.")
            return
        section = self.bulk_section.text().strip()
        if not section:
            QMessageBox.information(self, "Set Section", "Enter a section name first.")
            return
        before: dict[str, dict[str, str]] = {}
        after: dict[str, dict[str, str]] = {}
        for dot_id in ids:
            dot = self.project.dot_by_id(dot_id)
            if not dot:
                continue
            before[dot_id] = {"section": dot.section}
            after[dot_id] = {"section": section}
        if after:
            self.undo_stack.push(DotAppearanceCommand(self, before, after, "Assign Selected Section"))

    def apply_batch_dot_metadata(self) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            QMessageBox.information(self, "Batch Edit", "Select one or more marchers first.")
            return
        fields = {
            "section": self.bulk_section.text().strip(),
            "instrument": self.bulk_instrument.text().strip(),
            "rank": self.bulk_rank.text().strip(),
            "equipment": self.bulk_equipment.text().strip(),
            "layer": self.bulk_layer.text().strip(),
        }
        updates = {key: value for key, value in fields.items() if value}
        if not updates:
            QMessageBox.information(self, "Batch Edit", "Enter at least one metadata value.")
            return
        before: dict[str, dict[str, str]] = {}
        after: dict[str, dict[str, str]] = {}
        for dot_id in ids:
            dot = self.project.dot_by_id(dot_id)
            if not dot:
                continue
            before[dot_id] = {key: str(getattr(dot, key)) for key in updates}
            after[dot_id] = dict(updates)
        if after:
            self.undo_stack.push(DotAppearanceCommand(self, before, after, "Batch Edit Marchers"))
            self.remember_repeat_action({"type": "metadata", "fields": updates, "label": "Batch Edit Marchers"})
            self.statusBar().showMessage(f"Updated {len(after)} marcher(s)", 2200)

    def apply_bulk_property_editor(self) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            QMessageBox.information(self, "Bulk Property Editor", "Select one or more marchers first.")
            return
        offset_x = self.bulk_offset_x.value()
        offset_y = self.bulk_offset_y.value()
        if abs(offset_x) > 0.001 or abs(offset_y) > 0.001:
            after = self.current_positions()
            for dot_id in ids:
                x, y = after.get(dot_id, (0.0, 0.0))
                after[dot_id] = (x + offset_x, y + offset_y)
            self.apply_positions(after)
        action = self.bulk_path_action.currentText()
        if action == "Clear Selected Paths":
            self.clear_selected_paths()
        elif action == "Carry Positions Forward":
            self.carry_selected_forward()
        self.bulk_offset_x.setValue(0)
        self.bulk_offset_y.setValue(0)
        self.statusBar().showMessage(f"Bulk edit applied to {len(ids)} marcher(s)", 2200)

    def apply_coordinate_entry(self) -> None:
        text = self.coordinate_entry.text().strip()
        if not text:
            return
        try:
            dot_id, position = self.parse_coordinate_entry(text)
        except ValueError as exc:
            QMessageBox.warning(self, "Coordinate Entry", str(exc))
            return
        dot = self.project.dot_by_id(dot_id)
        if dot is None:
            dot = next((candidate for candidate in self.project.dots if candidate.name.lower() == dot_id.lower()), None)
        if dot is None:
            QMessageBox.warning(self, "Coordinate Entry", f"No marcher found for '{dot_id}'.")
            return
        after = self.current_positions()
        after[dot.id] = position
        self.apply_positions(after)
        if dot.id in self.field.dot_items:
            for item in self.field.dot_items.values():
                item.setSelected(item.dot_id == dot.id)
        self.coordinate_entry.clear()
        coordinate = format_surface_coordinate(self.project.surface, *position)
        self.statusBar().showMessage(f"{dot.name} moved to {coordinate[0]}, {coordinate[1]}", 2600)

    def parse_coordinate_entry(self, text: str) -> tuple[str, tuple[float, float]]:
        normalized = re.sub(r"\s+", " ", text.strip().lower().replace("infront", "in front"))
        if "," not in normalized:
            raise ValueError("Use a comma between yardline and hash coordinates.")
        left, right = [part.strip() for part in normalized.split(",", 1)]
        match = re.match(r"(?P<label>[a-z0-9_-]+)\s+(?P<yard>.+)", left)
        if not match:
            raise ValueError('Start with a marcher label, like "T1 on 45 s2".')
        label = match.group("label")
        direct_x = re.fullmatch(r"x\s*([+-]?[0-9]+(?:\.[0-9]+)?)\s*(?:yd|yards?)?", match.group("yard"))
        direct_y = re.fullmatch(r"y\s*([+-]?[0-9]+(?:\.[0-9]+)?)\s*(?:yd|yards?)?", right)
        if direct_x and direct_y:
            return label, (float(direct_x.group(1)), float(direct_y.group(1)))
        x = self.parse_yardline_text(match.group("yard"))
        y = self.parse_hash_text(right)
        return label, (x, y)

    def parse_yardline_text(self, text: str) -> float:
        normalized = text.strip().lower()
        on_match = re.match(r"on\s+(?P<yard>50|[1-4]0|[1-4]5|[0-9]+)(?:\s+(?P<side>s1|s2))?", normalized)
        if on_match:
            yard = int(on_match.group("yard"))
            if yard == 50:
                return 0.0
            side = on_match.group("side")
            if side not in {"s1", "s2"}:
                raise ValueError("Yard lines other than 50 need S1 or S2.")
            value = 50 - yard
            return -float(value) if side == "s1" else float(value)
        offset_match = re.match(
            r"(?P<steps>[0-9]+(?:\.[0-9]+)?)\s+steps?\s+(?P<direction>inside|outside)\s+(?P<yard>[0-9]+)\s+(?P<side>s1|s2)",
            normalized,
        )
        if offset_match:
            base = self.parse_yardline_text(f"on {offset_match.group('yard')} {offset_match.group('side')}")
            offset = float(offset_match.group("steps")) / STEPS_PER_YARD
            direction = offset_match.group("direction")
            if direction == "inside":
                return base + offset if base < 0 else base - offset
            return base - offset if base < 0 else base + offset
        raise ValueError(f"Could not parse yardline coordinate: '{text}'.")

    def parse_hash_text(self, text: str) -> float:
        normalized = text.strip().lower().replace("of ", "")
        references = {
            "fs": -self.project.surface.half_height,
            "fh": self.project.surface.front_hash_yards,
            "mid": 0.0,
            "bh": self.project.surface.back_hash_yards,
            "bs": self.project.surface.half_height,
        }
        on_match = re.match(r"on\s+(?P<ref>fs|fh|mid|bh|bs)", normalized)
        if on_match:
            return references[on_match.group("ref")]
        offset_match = re.match(
            r"(?P<steps>[0-9]+(?:\.[0-9]+)?)(?:\s+steps?)?\s+(?P<direction>in front|behind|outside)\s+(?P<ref>fs|fh|mid|bh|bs)",
            normalized,
        )
        if not offset_match:
            raise ValueError(f"Could not parse hash coordinate: '{text}'.")
        reference = references[offset_match.group("ref")]
        offset = float(offset_match.group("steps")) / STEPS_PER_YARD
        direction = offset_match.group("direction")
        if direction == "in front":
            return reference - offset
        if direction == "behind":
            return reference + offset
        return reference + offset if reference < 0 else reference - offset

    def apply_dot_appearance(self, updates: dict[str, dict[str, str]]) -> None:
        for dot_id, fields in updates.items():
            dot = self.project.dot_by_id(dot_id)
            if not dot:
                continue
            if "color" in fields:
                dot.color = fields["color"] or "#e53935"
            if "name" in fields:
                dot.name = fields["name"]
            if "section" in fields:
                dot.section = fields["section"]
            if "instrument" in fields:
                dot.instrument = fields["instrument"]
            if "rank" in fields:
                dot.rank = fields["rank"]
            if "equipment" in fields:
                dot.equipment = fields["equipment"]
            if "layer" in fields:
                dot.layer = fields["layer"] or "Main"
            item = self.field.dot_items.get(dot_id)
            if item:
                item.setBrush(QColor(dot.color or "#e53935"))
                item.label.setPlainText(dot.name)
        self.refresh_marcher_table()
        self.refresh_visibility_filters()
        self.refresh_lock_controls()
        self.refresh_appearance_groups()
        self.sync_inspector()

    def sync_inspector(self) -> None:
        ids = self.field.selected_dot_ids()
        prop_ids = self.field.selected_prop_ids()
        selected_total = len(ids) + len(prop_ids)
        self.selection_label.setText(f"{selected_total} selected" if selected_total else "No selection")
        self.sync_marcher_table_selection()
        self.refresh_prop_table()
        self.refresh_appearance_groups()
        self.sync_movement_style_controls()
        self.sync_facing_controls()
        self.update_selected_color_swatch(ids)
        has_selection = bool(ids)
        for widget in (
            self.selected_color_button,
            self.bulk_section,
            self.bulk_section_button,
            self.bulk_instrument,
            self.bulk_rank,
            self.bulk_equipment,
            self.bulk_layer,
            self.batch_metadata_button,
        ):
            widget.setEnabled(has_selection)
        if has_selection:
            selected_sections = [
                dot.section
                for dot_id in ids
                if (dot := self.project.dot_by_id(dot_id)) and dot.section
            ]
            self.bulk_section.setText(
                selected_sections[0] if selected_sections and len(set(selected_sections)) == 1 else ""
            )
            for field_name, editor in (
                ("instrument", self.bulk_instrument),
                ("rank", self.bulk_rank),
                ("equipment", self.bulk_equipment),
                ("layer", self.bulk_layer),
            ):
                values = [
                    getattr(dot, field_name)
                    for dot_id in ids
                    if (dot := self.project.dot_by_id(dot_id)) and getattr(dot, field_name)
                ]
                editor.setText(values[0] if values and len(set(values)) == 1 else "")
        enabled = len(ids) == 1 and not prop_ids
        self.dot_properties_group.setVisible(enabled)
        self.prop_properties_group.setVisible(len(prop_ids) == 1 and not ids)
        for widget in (
            self.dot_name,
            self.dot_section,
            self.dot_instrument,
            self.dot_rank,
            self.dot_equipment,
            self.dot_layer,
            self.dot_x,
            self.dot_y,
            self.dot_yardline,
            self.dot_hash,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            self.dot_yardline.setText("-")
            self.dot_hash.setText("-")
        else:
            dot = self.project.dot_by_id(ids[0])
            if dot:
                self.dot_name.setText(dot.name)
                self.dot_section.setText(dot.section)
                self.dot_instrument.setText(dot.instrument)
                self.dot_rank.setText(dot.rank)
                self.dot_equipment.setText(dot.equipment)
                self.dot_layer.setText(dot.layer)
                self.update_selected_coordinate_readout()

        prop_enabled = len(prop_ids) == 1 and not ids
        for widget in (
            self.prop_name,
            self.prop_layer,
            self.prop_x,
            self.prop_y,
            self.prop_width,
            self.prop_height,
            self.prop_rotation,
        ):
            widget.setEnabled(prop_enabled)
        if not prop_enabled:
            return
        prop = self.project.prop_by_id(prop_ids[0])
        state = self.current_set().prop_positions.get(prop_ids[0])
        if prop and state:
            self.prop_name.blockSignals(True)
            self.prop_layer.blockSignals(True)
            self.prop_name.setText(prop.name)
            self.prop_layer.setText(prop.layer)
            self.prop_name.blockSignals(False)
            self.prop_layer.blockSignals(False)
            for editor, key in (
                (self.prop_x, "x"),
                (self.prop_y, "y"),
                (self.prop_width, "width"),
                (self.prop_height, "height"),
                (self.prop_rotation, "rotation"),
            ):
                editor.blockSignals(True)
                editor.setValue(float(state.get(key, prop_default_state(prop)[key])))
                editor.blockSignals(False)

    def refresh_visibility_filters(self) -> None:
        if not hasattr(self, "section_filter"):
            return
        current_section = self.section_filter.currentText() or "All"
        current_layer = self.layer_filter.currentText() or "All"
        sections = ["All", *sorted({dot.section for dot in self.project.dots if dot.section})]
        layers = [
            "All",
            *sorted(
                {dot.layer for dot in self.project.dots if dot.layer}
                | {prop.layer for prop in self.project.props if prop.layer}
            ),
        ]
        self.section_filter.blockSignals(True)
        self.layer_filter.blockSignals(True)
        self.section_filter.clear()
        self.layer_filter.clear()
        self.section_filter.addItems(sections)
        self.layer_filter.addItems(layers)
        self.section_filter.setCurrentText(current_section if current_section in sections else "All")
        self.layer_filter.setCurrentText(current_layer if current_layer in layers else "All")
        self.section_filter.blockSignals(False)
        self.layer_filter.blockSignals(False)
        self.refresh_lock_controls()
        self.apply_visibility_filters()

    def apply_visibility_filters(self) -> None:
        if not hasattr(self, "section_filter"):
            return
        self.field.set_visibility_filters(
            self.section_filter.currentText() or "All",
            self.layer_filter.currentText() or "All",
        )
        self.apply_locks_to_field()

    def set_ghosts_enabled(self, enabled: bool) -> None:
        self.settings.setValue("view/ghost_previous_set", bool(enabled))
        self.settings.sync()
        self.field.set_ghosts_visible(bool(enabled))
        self._ghost_set_index = -1
        self.refresh_previous_set_ghosts()

    def refresh_previous_set_ghosts(self) -> None:
        if not self.field.show_ghosts or self.set_index <= 0 or not self.project.sets:
            self.field.clear_ghosts()
            self._ghost_set_index = self.set_index
            return
        previous_index = self.set_index - 1
        previous_set = self.project.sets[previous_index]
        self.field.set_ghost_positions(
            previous_set.dot_positions,
            self.facings_for_set(previous_index),
        )
        self._ghost_set_index = self.set_index

    def toggle_snap_align(self) -> None:
        self.snap_align.setChecked(not self.snap_align.isChecked())

    def schedule_live_conflict_analysis(self, *_args) -> None:
        if not hasattr(self, "conflict_heatmap_timer") or not hasattr(self, "conflict_heatmap"):
            return
        self.conflict_heatmap_generation += 1
        self.conflict_heatmap_timer.start()

    def run_live_conflict_analysis(self) -> None:
        if not hasattr(self, "conflict_heatmap") or not self.project.sets:
            return
        if self.conflict_heatmap_worker is not None and self.conflict_heatmap_worker.isRunning():
            self.conflict_heatmap_pending = True
            return
        generation = self.conflict_heatmap_generation
        worker = ConflictHeatmapWorker(
            self.project,
            self.set_index,
            self.min_spacing.value(),
            self.max_yards_per_count.value(),
            generation,
            self,
        )
        self.conflict_heatmap_worker = worker

        def completed(entries: list[Any], completed_generation: int) -> None:
            if completed_generation != self.conflict_heatmap_generation or not self.project.sets:
                return
            drill_set = self.current_set()
            self.conflict_heatmap.set_entries(entries, drill_set.start_count, drill_set.end_count)

        def failed(_message: str, _failed_generation: int) -> None:
            if self.project.sets:
                drill_set = self.current_set()
                self.conflict_heatmap.set_entries([], drill_set.start_count, drill_set.end_count)

        def finished() -> None:
            self.conflict_heatmap_worker = None
            worker.deleteLater()
            if self.conflict_heatmap_pending or generation != self.conflict_heatmap_generation:
                self.conflict_heatmap_pending = False
                self.conflict_heatmap_timer.start(180)

        worker.completed.connect(completed)
        worker.failed.connect(failed)
        worker.finished.connect(finished)
        worker.start()

    def jump_to_conflict_warning(self, item: QListWidgetItem) -> None:
        text = item.text()
        count_match = re.search(r"Count\s+([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
        if count_match:
            self.set_count(float(count_match.group(1)), seek_audio=True)
        mentioned = [dot.id for dot in self.project.dots if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(dot.id)}(?![A-Za-z0-9_-])", text)]
        if mentioned:
            self.select_dot_ids(mentioned, center=True)

    def analyze_paths(self) -> None:
        if not hasattr(self, "warning_list"):
            return
        if self.analysis_worker is not None and self.analysis_worker.isRunning():
            self.statusBar().showMessage("Path analysis is already running", 2200)
            return
        self.warning_list.clear()
        self.warning_list.addItem("Analyzing paths in background...")
        worker = AnalysisWorker(
            self.project,
            self.min_spacing.value(),
            self.max_yards_per_count.value(),
            self,
        )
        self.analysis_worker = worker

        def complete_analysis(all_warnings: list[Any], timeline_entries: list[Any]) -> None:
            self.warning_list.clear()
            for entry in timeline_entries[:80]:
                self.warning_list.addItem(
                    f"TIMELINE | {entry.set_name} | Count {entry.count:.2f} | "
                    f"{entry.total} conflict(s): spacing {entry.spacing_conflicts}, "
                    f"speed {entry.speed_conflicts}, crossing {entry.crossing_conflicts}, "
                    f"no-go {entry.no_go_conflicts} | "
                    f"worst {entry.worst_spacing:.2f} yd, fastest {entry.fastest_yards_per_count:.2f} yd/count"
                )
            for warning in all_warnings:
                repairability = (
                    "UNAVOIDABLE WITH FIXED PICTURES"
                    if warning.avoidable is False
                    else "REPAIRABLE"
                    if warning.avoidable is True
                    else "CHECK"
                )
                item = QListWidgetItem(
                    f"{warning.severity.upper()} | {repairability} | {warning.set_name} | "
                    f"Count {warning.count:.2f} | {warning.message}"
                )
                item.setToolTip(
                    "\n".join(
                        value
                        for value in (
                            warning.explanation,
                            f"Suggested repair: {warning.suggestion}" if warning.suggestion else "",
                        )
                        if value
                    )
                )
                self.warning_list.addItem(item)
            self.statusBar().showMessage(
                f"{len(all_warnings)} path warnings, {len(timeline_entries)} conflict timeline entries",
                3000,
            )
            if self.project.sets:
                drill_set = self.current_set()
                current_entries = [entry for entry in timeline_entries if entry.set_index == self.set_index]
                self.conflict_heatmap.set_entries(current_entries, drill_set.start_count, drill_set.end_count)
            self.analysis_worker = None

        def fail_analysis(message: str) -> None:
            self.warning_list.clear()
            self.warning_list.addItem(f"Analysis failed: {message}")
            self.statusBar().showMessage("Path analysis failed", 3000)
            self.analysis_worker = None

        worker.analysis_completed.connect(complete_analysis)
        worker.analysis_failed.connect(fail_analysis)
        worker.start()
        self.statusBar().showMessage("Path analysis running in background", 2200)

    def optimize_selected_spot_assignment(self) -> None:
        selected = [dot_id for dot_id in self.ordered_dot_ids(self.field.selected_dot_ids()) if not self.is_dot_locked(dot_id)]
        if len(selected) < 2:
            QMessageBox.information(
                self,
                "Optimize Spot Assignment",
                "Select at least two unlocked marchers in the destination form.",
            )
            return
        targets = [self.current_set().dot_positions[dot_id] for dot_id in selected]
        assignment = collision_aware_assignment_for_project(
            self.project,
            self.set_index,
            selected,
            targets,
            min_spacing=self.min_spacing.value(),
            max_yards_per_count=self.max_yards_per_count.value(),
        )
        before_quality = project_assignment_quality(
            self.project,
            self.set_index,
            selected,
            targets,
            list(range(len(selected))),
            min_spacing=self.min_spacing.value(),
            max_yards_per_count=self.max_yards_per_count.value(),
        )
        after_quality = project_assignment_quality(
            self.project,
            self.set_index,
            selected,
            targets,
            assignment,
            min_spacing=self.min_spacing.value(),
            max_yards_per_count=self.max_yards_per_count.value(),
        )
        changed = sum(target_index != index for index, target_index in enumerate(assignment))
        if not changed:
            self.statusBar().showMessage(
                "No safer spot reassignment was found without changing the destination picture.",
                4000,
            )
            self.schedule_live_conflict_analysis()
            return
        before = self.current_positions()
        after = dict(before)
        after.update(
            {
                dot_id: targets[assignment[index]]
                for index, dot_id in enumerate(selected)
            }
        )
        self.undo_stack.push(
            MoveDotsCommand(
                self,
                self.set_index,
                before,
                after,
                "Optimize Spot Assignment",
            )
        )
        self.refresh_selected_paths()
        self.schedule_live_conflict_analysis()
        self.statusBar().showMessage(
            f"Reassigned {changed} marcher(s) while preserving every form spot: "
            f"collisions {before_quality.collisions}→{after_quality.collisions}, "
            f"crossings {before_quality.crossings}→{after_quality.crossings}.",
            5200,
        )

    def auto_plan_selected_paths(self) -> None:
        self.optimize_selected_spot_assignment()

    def clear_selected_paths(self) -> None:
        target_index = self.path_display_set_index()
        if target_index is None or target_index <= 0:
            QMessageBox.information(self, "Clear Paths", "Select a moving transition before clearing paths.")
            return
        selected = self.field.selected_dot_ids()
        if not selected:
            QMessageBox.information(self, "Clear Paths", "Select one or more marchers first.")
            return

        scoped_indices = self.selected_set_indices_for_edit(selected, base_index=target_index)
        if len(scoped_indices) > 1 or scoped_indices[0] != target_index:
            before_sets = deepcopy(self.project.sets)
            before_index = self.set_index
            before_count = self.current_count
            removed = 0
            for index in scoped_indices:
                drill_set = self.project.sets[index]
                for dot_id in selected:
                    removed += len(drill_set.path_anchors.get(dot_id, [])) + len(drill_set.count_positions.get(dot_id, {}))
                    drill_set.path_anchors.pop(dot_id, None)
                    drill_set.path_controls.pop(dot_id, None)
                    drill_set.count_positions.pop(dot_id, None)
                    drill_set.count_facings.pop(dot_id, None)
            self.set_count(self.current_count, seek_audio=False)
            self.push_set_snapshot(before_sets, before_index, before_count, "Ripple Clear Selected Paths")
            self.statusBar().showMessage(f"Cleared paths across {len(scoped_indices)} set(s), {removed} point(s)", 3000)
            return

        before_anchors = self.clone_path_anchors(target_index)
        before_controls = self.clone_path_controls(target_index)
        before_counts = self.clone_count_positions(target_index)
        after_anchors = self.clone_path_anchors(target_index)
        after_controls = self.clone_path_controls(target_index)
        after_counts = self.clone_count_positions(target_index)
        removed = 0
        for dot_id in selected:
            removed += len(after_anchors.get(dot_id, [])) + len(after_counts.get(dot_id, {}))
            after_anchors.pop(dot_id, None)
            after_controls.pop(dot_id, None)
            after_counts.pop(dot_id, None)

        positions = dict(self.project.sets[target_index].dot_positions)
        self.undo_stack.push(
            MoveDotsCommand(
                self,
                target_index,
                positions,
                positions,
                "Clear Selected Paths",
                before_anchors,
                after_anchors,
                before_controls,
                after_controls,
                before_counts,
                after_counts,
            )
        )
        self.refresh_selected_paths()
        self.statusBar().showMessage(f"Cleared path edits for {len(selected)} marcher(s), {removed} point(s)", 3000)

    def selection_changed(self, *_args) -> None:
        self.sync_inspector()
        self.sync_transform_handle_controls()
        if hasattr(self, "transform_custom_pivot") and not self.transform_custom_pivot.isChecked():
            _ids, positions = self.selected_positions()
            if positions:
                center_x, center_y = selection_center(positions)
                self.transform_pivot_x.blockSignals(True)
                self.transform_pivot_y.blockSignals(True)
                self.transform_pivot_x.setValue(center_x)
                self.transform_pivot_y.setValue(center_y)
                self.transform_pivot_x.blockSignals(False)
                self.transform_pivot_y.blockSignals(False)
        self.update_formation_preview()
        self.update_field_hud_visibility()
        self.refresh_selected_paths()
        self.refresh_transition_timeline()
        self.refresh_measurements()

    def path_display_set_index(self) -> int | None:
        if self.play_timer.isActive():
            return self.set_index if self.set_index > 0 else None
        if self.set_index + 1 < len(self.project.sets):
            return self.set_index + 1
        return self.set_index if self.set_index > 0 else None

    def refresh_selected_paths(self) -> None:
        selected = self.field.selected_dot_ids()
        target_index = self.path_display_set_index()
        if not selected or target_index is None:
            self.field.clear_paths()
            return

        target_set = self.project.sets[target_index]
        if target_index > 0:
            start_positions = self.project.sets[target_index - 1].dot_positions
        else:
            start_positions = {dot.id: (dot.x, dot.y) for dot in self.project.dots}
        paths: dict[str, list[tuple[float, float]]] = {}
        anchors: dict[str, list[tuple[float, float]]] = {}
        controls: dict[str, list[dict[str, tuple[float, float]]]] = {}
        for dot_id in selected:
            start = start_positions.get(dot_id)
            end = target_set.dot_positions.get(dot_id)
            if start is None or end is None:
                continue
            dot_anchors = target_set.path_anchors.get(dot_id, [])
            dot_controls = self.ensure_path_controls(target_index, dot_id, start, end)
            keyframes = target_set.count_positions.get(dot_id, {})
            if keyframes:
                paths[dot_id] = [
                    start,
                    *[
                        position
                        for _count, position in sorted(keyframes.items())
                        if target_set.start_count < _count < target_set.end_count
                    ],
                    end,
                ]
            else:
                paths[dot_id] = sample_transition_path(start, end, dot_anchors, dot_controls)
            anchors[dot_id] = dot_anchors
            controls[dot_id] = dot_controls
        self.field.show_paths(paths, anchors, controls)

    def ensure_path_controls(
        self,
        set_index: int,
        dot_id: str,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> list[dict[str, tuple[float, float]]]:
        drill_set = self.project.sets[set_index]
        anchors = drill_set.path_anchors.get(dot_id, [])
        controls = drill_set.path_controls.setdefault(dot_id, [])
        while len(controls) < len(anchors):
            index = len(controls)
            anchor = anchors[index]
            previous_point = start if index == 0 else anchors[index - 1]
            next_point = end if index == len(anchors) - 1 else anchors[index + 1]
            controls.append(
                {
                    "in": (
                        anchor[0] - (anchor[0] - previous_point[0]) / 3,
                        anchor[1] - (anchor[1] - previous_point[1]) / 3,
                    ),
                    "out": (
                        anchor[0] + (next_point[0] - anchor[0]) / 3,
                        anchor[1] + (next_point[1] - anchor[1]) / 3,
                    ),
                }
            )
        if len(controls) > len(anchors):
            del controls[len(anchors) :]
        return controls

    def transition_midpoint(self, set_index: int, dot_id: str) -> tuple[float, float]:
        drill_set = self.project.sets[set_index]
        end = drill_set.dot_positions.get(dot_id, (0.0, 0.0))
        if set_index > 0:
            start = self.project.sets[set_index - 1].dot_positions.get(dot_id, end)
        else:
            dot = self.project.dot_by_id(dot_id)
            start = (dot.x, dot.y) if dot else end
        return ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)

    def add_path_anchor(self, dot_id: str, x: float, y: float) -> None:
        target_index = self.path_display_set_index()
        if target_index is None:
            return
        scoped_indices = self.selected_set_indices_for_edit([dot_id], base_index=target_index)
        if len(scoped_indices) > 1 or scoped_indices[0] != target_index:
            before_sets = deepcopy(self.project.sets)
            before_index = self.set_index
            before_count = self.current_count
            source_midpoint = self.transition_midpoint(target_index, dot_id)
            offset = (x - source_midpoint[0], y - source_midpoint[1])
            for index in scoped_indices:
                midpoint = self.transition_midpoint(index, dot_id)
                self.project.sets[index].path_anchors.setdefault(dot_id, []).append(
                    (midpoint[0] + offset[0], midpoint[1] + offset[1])
                )
                self.project.sets[index].path_controls.setdefault(dot_id, [])
            self.push_set_snapshot(before_sets, before_index, before_count, "Ripple Add Path Anchor")
            return
        before_anchors = self.clone_path_anchors(target_index)
        before_controls = self.clone_path_controls(target_index)
        before_count_positions = self.clone_count_positions(target_index)
        self.project.sets[target_index].path_anchors.setdefault(dot_id, []).append((x, y))
        self.project.sets[target_index].path_controls.setdefault(dot_id, [])
        self.push_path_geometry_snapshot(
            target_index,
            before_anchors,
            before_controls,
            before_count_positions,
            "Add Path Anchor",
        )

    def move_path_anchor(
        self,
        dot_id: str,
        anchor_index: int,
        x: float,
        y: float,
        modifiers: int = 0,
    ) -> None:
        target_index = self.path_display_set_index()
        if target_index is None:
            return
        symmetric = bool(modifiers & int(Qt.KeyboardModifier.AltModifier.value))

        def move_anchor(set_index: int, new_position: tuple[float, float]) -> bool:
            anchors = self.project.sets[set_index].path_anchors.get(dot_id, [])
            if not 0 <= anchor_index < len(anchors):
                return False
            controls = self.project.sets[set_index].path_controls.setdefault(dot_id, [])

            def set_anchor(index: int, position: tuple[float, float]) -> None:
                old_position = anchors[index]
                anchors[index] = position
                if index < len(controls):
                    delta_x = position[0] - old_position[0]
                    delta_y = position[1] - old_position[1]
                    for control_name in ("in", "out"):
                        if control_name in controls[index]:
                            control_x, control_y = controls[index][control_name]
                            controls[index][control_name] = (
                                control_x + delta_x,
                                control_y + delta_y,
                            )

            set_anchor(anchor_index, new_position)
            opposite_index = len(anchors) - 1 - anchor_index
            if symmetric and opposite_index != anchor_index:
                midpoint = self.transition_midpoint(set_index, dot_id)
                set_anchor(
                    opposite_index,
                    (
                        midpoint[0] * 2 - new_position[0],
                        midpoint[1] * 2 - new_position[1],
                    ),
                )
            return True

        scoped_indices = self.selected_set_indices_for_edit([dot_id], base_index=target_index)
        source_anchors = self.project.sets[target_index].path_anchors.get(dot_id, [])
        if (len(scoped_indices) > 1 or scoped_indices[0] != target_index) and 0 <= anchor_index < len(source_anchors):
            before_sets = deepcopy(self.project.sets)
            before_index = self.set_index
            before_count = self.current_count
            old_x, old_y = source_anchors[anchor_index]
            delta_x, delta_y = x - old_x, y - old_y
            for index in scoped_indices:
                anchors = self.project.sets[index].path_anchors.get(dot_id, [])
                if not 0 <= anchor_index < len(anchors):
                    continue
                anchor_x, anchor_y = anchors[anchor_index]
                move_anchor(index, (anchor_x + delta_x, anchor_y + delta_y))
            self.push_set_snapshot(before_sets, before_index, before_count, "Ripple Move Path Anchor")
            return
        before_anchors = self.clone_path_anchors(target_index)
        before_controls = self.clone_path_controls(target_index)
        before_count_positions = self.clone_count_positions(target_index)
        anchors = self.project.sets[target_index].path_anchors.setdefault(dot_id, [])
        if 0 <= anchor_index < len(anchors):
            move_anchor(target_index, (x, y))
            self.push_path_geometry_snapshot(
                target_index,
                before_anchors,
                before_controls,
                before_count_positions,
                "Move Path Anchor",
            )
            return
        self.refresh_selected_paths()

    def move_path_tangent(
        self,
        dot_id: str,
        anchor_index: int,
        control_name: str,
        x: float,
        y: float,
        modifiers: int = 0,
    ) -> None:
        target_index = self.path_display_set_index()
        if target_index is None:
            return
        symmetric = bool(modifiers & int(Qt.KeyboardModifier.AltModifier.value))
        opposite_name = "out" if control_name == "in" else "in"
        scoped_indices = self.selected_set_indices_for_edit([dot_id], base_index=target_index)
        source_controls = self.project.sets[target_index].path_controls.get(dot_id, [])
        if (len(scoped_indices) > 1 or scoped_indices[0] != target_index) and anchor_index < len(source_controls):
            old = source_controls[anchor_index].get(control_name, (x, y))
            delta_x, delta_y = x - old[0], y - old[1]
            before_sets = deepcopy(self.project.sets)
            before_index = self.set_index
            before_count = self.current_count
            for index in scoped_indices:
                controls = self.project.sets[index].path_controls.setdefault(dot_id, [])
                while len(controls) <= anchor_index:
                    controls.append({})
                existing = controls[anchor_index].get(control_name, old)
                moved = (existing[0] + delta_x, existing[1] + delta_y)
                controls[anchor_index][control_name] = moved
                anchors = self.project.sets[index].path_anchors.get(dot_id, [])
                if symmetric and anchor_index < len(anchors):
                    anchor = anchors[anchor_index]
                    controls[anchor_index][opposite_name] = (
                        anchor[0] * 2 - moved[0],
                        anchor[1] * 2 - moved[1],
                    )
            self.push_set_snapshot(before_sets, before_index, before_count, "Ripple Move Path Tangent")
            return
        before_anchors = self.clone_path_anchors(target_index)
        before_controls = self.clone_path_controls(target_index)
        before_count_positions = self.clone_count_positions(target_index)
        controls = self.project.sets[target_index].path_controls.setdefault(dot_id, [])
        while len(controls) <= anchor_index:
            controls.append({})
        controls[anchor_index][control_name] = (x, y)
        anchors = self.project.sets[target_index].path_anchors.get(dot_id, [])
        if symmetric and anchor_index < len(anchors):
            anchor = anchors[anchor_index]
            controls[anchor_index][opposite_name] = (
                anchor[0] * 2 - x,
                anchor[1] * 2 - y,
            )
        self.push_path_geometry_snapshot(
            target_index,
            before_anchors,
            before_controls,
            before_count_positions,
            "Move Path Tangent",
        )

    def update_selected_dot(self) -> None:
        ids = self.field.selected_dot_ids()
        if len(ids) != 1:
            return
        dot = self.project.dot_by_id(ids[0])
        if dot:
            dot.name = self.dot_name.text()
            dot.section = self.dot_section.text()
            dot.instrument = self.dot_instrument.text()
            dot.rank = self.dot_rank.text()
            dot.equipment = self.dot_equipment.text()
            dot.layer = self.dot_layer.text().strip() or "Main"
            self.field.preserve_selection()
            self.field.rebuild_dots()
            self.field.set_positions(self.current_set().dot_positions)
            self.field.set_facings(self.facings_for_set())
            self.field.set_prop_states(self.current_set().prop_positions)
            self.field.restore_preserved_selection()
            self.refresh_marcher_table()
            self.refresh_visibility_filters()
            self.refresh_appearance_groups()

    def update_selected_dot_position(self) -> None:
        ids = self.field.selected_dot_ids()
        if len(ids) != 1:
            return
        try:
            x = float(self.dot_x.text())
            y = float(self.dot_y.text())
        except ValueError:
            return
        if self.editing_set_one_opening():
            self.apply_opening_positions(
                {ids[0]: (x, y)},
                sync_unchanged_set_one_endpoints=True,
                label="Edit Marcher Coordinate",
            )
            return
        after = self.current_positions()
        after[ids[0]] = (x, y)
        self.apply_positions(after)

    def update_selected_prop_metadata(self) -> None:
        prop_ids = self.field.selected_prop_ids()
        if len(prop_ids) != 1:
            return
        prop = self.project.prop_by_id(prop_ids[0])
        if not prop:
            return
        prop.name = self.prop_name.text().strip() or prop.id
        prop.layer = self.prop_layer.text().strip() or "Props"
        self.refresh_prop_table()
        self.refresh_visibility_filters()

    def update_selected_prop_state(self) -> None:
        prop_ids = self.field.selected_prop_ids()
        if len(prop_ids) != 1:
            return
        prop_id = prop_ids[0]
        before = self.current_prop_states()
        after = {key: dict(value) for key, value in before.items()}
        after[prop_id] = {
            "x": self.prop_x.value(),
            "y": self.prop_y.value(),
            "width": self.prop_width.value(),
            "height": self.prop_height.value(),
            "rotation": self.prop_rotation.value(),
        }
        self.apply_prop_states(after)

    def show_operation_failure(
        self,
        title: str,
        action: str,
        error: BaseException,
        *,
        location: Path | str | None = None,
    ) -> None:
        QMessageBox.warning(
            self,
            title,
            actionable_error_message(action, error, location=location),
        )

    def save(self) -> bool:
        try:
            save_project(self.project_dir, self.project, backup_reason="manual")
        except Exception as exc:
            self.show_operation_failure("Save Failed", "save the project", exc, location=self.project_dir)
            return False
        self.statusBar().showMessage("Project saved", 2500)
        return True

    def save_as(self) -> None:
        title, accepted = QInputDialog.getText(
            self,
            "Save Project As",
            "Project title:",
            text=f"{self.project.metadata.show_title} Copy",
        )
        if not accepted or not title.strip():
            return

        if not self.save():
            return
        target_dir = self.unique_project_dir(project_library_dir(), safe_folder_name(title))
        previous_title = self.project.metadata.show_title
        try:
            shutil.copytree(self.project_dir, target_dir)
            self.project.metadata.show_title = title.strip()
            save_project(target_dir, self.project, backup_reason="save_as")
        except Exception as exc:
            self.project.metadata.show_title = previous_title
            self.show_operation_failure("Save As Failed", "create the project copy", exc, location=target_dir)
            return
        self.project_dir = target_dir
        self.setWindowTitle(f"Drill Pirate - {self.project.metadata.show_title}")
        self.statusBar().showMessage(f"Saved as {target_dir.name}", 3000)

    def unique_project_dir(self, root: Path, folder_name: str) -> Path:
        candidate = root / folder_name
        suffix = 2
        while candidate.exists():
            candidate = root / f"{folder_name}_{suffix}"
            suffix += 1
        return candidate

    def return_home(self) -> None:
        self.pause()
        if self.save():
            self.return_home_requested.emit()

    def autosave(self) -> bool:
        try:
            save_project(
                self.project_dir,
                self.project,
                backup_reason="autosave",
                backup_min_interval_seconds=60,
            )
        except Exception as exc:
            message = actionable_error_message("autosave the project", exc, location=self.project_dir)
            self.statusBar().showMessage("Autosave failed — project files were preserved", 6000)
            if message != self._last_autosave_error:
                self._last_autosave_error = message
                QMessageBox.warning(self, "Autosave Failed", message)
            return False
        self._last_autosave_error = ""
        self.statusBar().showMessage("Autosaved", 1500)
        return True

    def restore_previous_save(self) -> None:
        backups = list_project_backups(self.project_dir)
        if not backups:
            QMessageBox.information(self, "Restore Previous Save", "No project backups were found yet.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Restore Previous Save")
        dialog.setModal(True)
        dialog.resize(620, 420)
        layout = QVBoxLayout(dialog)
        label = QLabel("Choose a backup to restore. Drill Pirate will create a pre-restore backup first.")
        label.setWordWrap(True)
        backup_list = QListWidget()
        for backup in backups:
            backup_list.addItem(backup.label)
            backup_list.item(backup_list.count() - 1).setData(Qt.ItemDataRole.UserRole, str(backup.path))
        if backup_list.count():
            backup_list.setCurrentRow(0)
        buttons = QHBoxLayout()
        restore_button = QPushButton("Restore")
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(dialog.reject)
        restore_button.clicked.connect(dialog.accept)
        buttons.addStretch()
        buttons.addWidget(cancel_button)
        buttons.addWidget(restore_button)
        layout.addWidget(label)
        layout.addWidget(backup_list, 1)
        layout.addLayout(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted or not backup_list.currentItem():
            return
        path = Path(str(backup_list.currentItem().data(Qt.ItemDataRole.UserRole)))
        confirm = QMessageBox.question(
            self,
            "Restore Previous Save",
            "Restore this backup? Current project files will be backed up first.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.pause()
        try:
            restore_project_backup(self.project_dir, path)
            self.reload_project_from_disk()
        except Exception as exc:
            self.show_operation_failure("Restore Failed", "restore the selected backup", exc, location=path)
            return
        self.statusBar().showMessage("Previous save restored", 3500)

    def reload_project_from_disk(self) -> None:
        self.project = load_project(self.project_dir)
        self.set_index = 0
        self.current_count = self.project.sets[0].start_count if self.project.sets else 1
        self.field.set_project(self.project, self.project_dir)
        self.sync_drill_grid_controls()
        self.populate_sets()
        self.refresh_marcher_table()
        self.refresh_prop_table()
        self.refresh_visibility_filters()
        self.refresh_appearance_groups()
        self.refresh_constraints()
        self.refresh_audio_versions()
        self.refresh_timing_events()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=False)
        self.sync_inspector()
        self.load_audio()

    def export_bug_report_bundle(self) -> None:
        self.pause()
        try:
            save_project(self.project_dir, self.project, backup_reason="bug_report")
        except Exception as exc:
            self.show_operation_failure("Bug Report Failed", "prepare the project for a bug report", exc, location=self.project_dir)
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Bug Report Bundle",
            str(self.project_dir / f"{self.project_dir.name}_bug_report.zip"),
            "Zip (*.zip)",
        )
        if not path:
            return
        try:
            export_bug_report_bundle(Path(path), project_dir=self.project_dir)
        except Exception as exc:
            self.show_operation_failure("Bug Report Failed", "export the bug report bundle", exc, location=path)
            return
        self.statusBar().showMessage("Bug report bundle exported", 3500)

    def show_export_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Export")
        dialog.setModal(True)
        dialog.setMinimumWidth(640)
        layout = QVBoxLayout(dialog)

        title = QLabel("Choose Export Type")
        title.setStyleSheet("font-size: 18px; font-weight: 650;")
        layout.addWidget(title)

        mp4_button = QPushButton("MP4 Video")
        mp4_button.setToolTip("Render a high-quality show video with ffmpeg, cancel support, and optional title splash.")
        pdf_button = QPushButton("Drill Sheet PDF")
        pdf_button.setToolTip("Preview and save one clean landscape set chart per set.")
        dot_book_button = QPushButton("Dot Book PDF")
        dot_book_button.setToolTip("Preview and save one coordinate packet page per performer.")
        staff_packet_button = QPushButton("Staff Packet PDF")
        staff_packet_button.setToolTip("Preview and save a staff packet with show summary, warnings, and large set pages.")
        section_packet_button = QPushButton("Section Packet PDF")
        section_packet_button.setToolTip("Preview and save a packet filtered to one section.")
        coordinate_summary_button = QPushButton("Coordinate Summary PDF")
        coordinate_summary_button.setToolTip("Preview and save a readable coordinate table for all sets.")
        coordinate_button = QPushButton("Coordinate CSV")
        coordinate_button.setToolTip("Export all performer coordinates for every set.")
        zip_button = QPushButton("Project Zip")
        zip_button.setToolTip("Package the project folder for backup or sharing.")
        batch_button = QPushButton("Batch: Staff + Dot Books + CSV + ZIP")
        batch_button.setToolTip("Run the standard export package in one folder.")
        layout_designer_button = QPushButton("PDF Layout Designer…")
        layout_designer_button.setToolTip("Visually design reusable PDF pages with movable text, images, fields, and tables.")
        ffmpeg_button = QPushButton("Set ffmpeg.exe")
        ffmpeg_button.setToolTip("Choose a local ffmpeg executable for MP4 export.")

        grid = QGridLayout()
        buttons = [
            mp4_button,
            pdf_button,
            dot_book_button,
            staff_packet_button,
            section_packet_button,
            coordinate_summary_button,
            coordinate_button,
            zip_button,
            batch_button,
            layout_designer_button,
        ]
        for index, button in enumerate(buttons):
            button.setMinimumHeight(42)
            grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(grid)

        layout.addSpacing(8)
        layout.addWidget(ffmpeg_button)

        close_row = QHBoxLayout()
        close_button = QPushButton("Cancel")
        close_button.clicked.connect(dialog.reject)
        close_row.addStretch()
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

        mp4_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_video))
        pdf_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_drill_sheet_pdf))
        dot_book_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_dot_book_pdf))
        staff_packet_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_staff_packet_pdf))
        section_packet_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_section_packet_pdf))
        coordinate_summary_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_coordinate_summary_pdf))
        coordinate_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_coordinate_csv))
        zip_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_zip))
        batch_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_batch_profile))
        layout_designer_button.clicked.connect(lambda: self.open_pdf_layout_designer_from_export(dialog))
        ffmpeg_button.clicked.connect(self.choose_ffmpeg_exe)
        dialog.exec()

    def accept_export_choice(self, dialog: QDialog, callback) -> None:
        dialog.accept()
        callback()

    def export_zip(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Project", str(self.project_dir) + ".zip", "Zip (*.zip)")
        if not path:
            return
        try:
            export_project_zip(self.project_dir, Path(path), self.project)
        except Exception as exc:
            self.show_operation_failure("Project ZIP Failed", "export the project ZIP", exc, location=path)
            return
        self.statusBar().showMessage("Project zip exported", 3000)

    def export_coordinate_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Coordinate CSV",
            str(self.project_dir / "coordinates.csv"),
            "CSV (*.csv)",
        )
        if not path:
            return
        try:
            export_coordinate_csv(Path(path), self.project)
        except Exception as exc:
            self.show_operation_failure("Coordinate Export Failed", "export the coordinate CSV", exc, location=path)
            return
        self.statusBar().showMessage("Coordinate CSV exported", 3000)

    @staticmethod
    def pdf_layout_profiles() -> list[tuple[str, str]]:
        return [
            ("Drill Sheet", "drill_sheet"),
            ("Dot Book", "dot_book"),
            ("Staff Packet", "staff_packet"),
            ("Section Packet", "section_packet"),
            ("Coordinate Summary", "coordinate_summary"),
        ]

    def stored_pdf_layout(self, profile: str) -> dict:
        payload = self.workflow_bucket("pdf_layouts").get(profile, {})
        return deepcopy(payload) if isinstance(payload, dict) else {}

    def edit_pdf_layout(self, profile: str, initial_layout: dict | None = None) -> dict | None:
        dialog = PdfLayoutDesignerDialog(
            profile,
            self.project_dir,
            initial_layout if initial_layout is not None else self.stored_pdf_layout(profile),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        payload = dialog.layout_json()
        self.workflow_bucket("pdf_layouts")[profile] = deepcopy(payload)
        self.autosave()
        self.statusBar().showMessage(f"Saved {profile.replace('_', ' ')} PDF layout", 2600)
        return payload

    def open_pdf_layout_designer_from_export(self, export_dialog: QDialog) -> None:
        export_dialog.accept()
        labels = [label for label, _profile in self.pdf_layout_profiles()]
        label, accepted = QInputDialog.getItem(self, "PDF Layout Designer", "Layout type", labels, 0, False)
        if not accepted or not label:
            return
        profile = dict(self.pdf_layout_profiles())[label]
        self.edit_pdf_layout(profile)

    def print_template_options(
        self,
        title: str,
        profile: str,
        default_title: str = "",
        allow_section: bool = False,
        force_section: str = "",
        include_warning_option: bool = False,
    ) -> PrintTemplateOptions | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        title_input = QLineEdit(default_title)
        compact_check = QCheckBox("Compact table spacing")
        warnings_check = QCheckBox("Include conflict warnings")
        warnings_check.setChecked(True)
        section_combo = QComboBox()
        layout_payload = self.stored_pdf_layout(profile)
        layout_status = QLabel("Custom layout saved" if layout_payload else "Using Drill Pirate default layout")
        layout_status.setObjectName("secondaryText")
        customize_layout_button = QPushButton("Customize PDF Layout…")
        reset_layout_button = QPushButton("Use Default")

        def customize_layout() -> None:
            nonlocal layout_payload
            edited = self.edit_pdf_layout(profile, layout_payload)
            if edited is not None:
                layout_payload = edited
                layout_status.setText("Custom layout saved")

        def reset_layout() -> None:
            nonlocal layout_payload
            layout_payload = {}
            layout_status.setText("Using Drill Pirate default layout")

        customize_layout_button.clicked.connect(customize_layout)
        reset_layout_button.clicked.connect(reset_layout)
        layout_buttons_widget = QWidget()
        layout_buttons_row = QHBoxLayout(layout_buttons_widget)
        layout_buttons_row.setContentsMargins(0, 0, 0, 0)
        layout_buttons_row.addWidget(customize_layout_button)
        layout_buttons_row.addWidget(reset_layout_button)
        section_combo.addItem("All")
        for section in sorted({dot.section for dot in self.project.dots if dot.section}):
            section_combo.addItem(section)
        if force_section:
            index = section_combo.findText(force_section)
            if index >= 0:
                section_combo.setCurrentIndex(index)
            section_combo.setEnabled(False)
        form.addRow("Template Title", title_input)
        if allow_section or force_section:
            form.addRow("Section", section_combo)
        form.addRow("Compact", compact_check)
        if include_warning_option:
            form.addRow("Warnings", warnings_check)
        form.addRow("PDF Layout", layout_buttons_widget)
        form.addRow("", layout_status)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        preview_button = QPushButton("Preview")
        cancel_button.clicked.connect(dialog.reject)
        preview_button.clicked.connect(dialog.accept)
        buttons.addStretch()
        buttons.addWidget(cancel_button)
        buttons.addWidget(preview_button)
        layout.addLayout(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        if layout_payload:
            self.workflow_bucket("pdf_layouts")[profile] = deepcopy(layout_payload)
        else:
            self.workflow_bucket("pdf_layouts").pop(profile, None)
        return PrintTemplateOptions(
            title=title_input.text().strip(),
            section_filter=section_combo.currentText(),
            include_warnings=warnings_check.isChecked(),
            compact=compact_check.isChecked(),
            layout=deepcopy(layout_payload),
        )

    def preview_pdf_export(
        self,
        title: str,
        default_name: str,
        progress_max: int,
        export_callback: Callable[[Path, Callable[[str, int, int], None]], None],
    ) -> None:
        progress = QProgressDialog(f"Preparing {title}...", None, 0, max(1, progress_max), self)
        progress.setWindowTitle(f"Exporting {title}")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

        def update_progress(stage: str, current: int, total: int) -> None:
            progress.setLabelText(stage)
            progress.setMaximum(max(1, total))
            progress.setValue(min(current, total))
            QApplication.processEvents()

        temp_dir = tempfile.TemporaryDirectory(prefix="drill_pirate_pdf_preview_")
        preview_path = Path(temp_dir.name) / default_name
        try:
            export_callback(preview_path, update_progress)
        except Exception as exc:
            self.show_operation_failure("Export Failed", f"prepare the {title}", exc, location=preview_path)
            temp_dir.cleanup()
            return
        finally:
            progress.close()
        preview = PdfPreviewDialog(preview_path, self.project_dir / default_name, self)
        try:
            if preview.exec() == QDialog.DialogCode.Accepted and preview.saved_path:
                self.statusBar().showMessage(f"{title} saved", 3000)
        finally:
            temp_dir.cleanup()

    def export_drill_sheet_pdf(self) -> None:
        options = self.print_template_options(
            "Drill Sheet Options",
            "drill_sheet",
            default_title="",
        )
        if not options:
            return
        self.preview_pdf_export(
            "Drill Sheet PDF",
            "drill_sheet.pdf",
            len(self.project.sets),
            lambda path, progress_callback: export_drill_sheet_pdf(
                path,
                self.project,
                self.project_dir,
                progress_callback=progress_callback,
                options=options,
            ),
        )

    def export_dot_book_pdf(self) -> None:
        options = self.print_template_options(
            "Dot Book Options",
            "dot_book",
            default_title="",
            allow_section=True,
        )
        if not options:
            return
        dot_count = len([dot for dot in self.project.dots if options.section_filter == "All" or dot.section == options.section_filter])
        self.preview_pdf_export(
            "Dot Book PDF",
            "dot_book.pdf",
            max(1, dot_count),
            lambda path, progress_callback: export_dot_book_pdf(
                path,
                self.project,
                progress_callback=progress_callback,
                options=options,
                project_dir=self.project_dir,
            ),
        )

    def export_staff_packet_pdf(self) -> None:
        options = self.print_template_options(
            "Staff Packet Options",
            "staff_packet",
            default_title="",
            include_warning_option=True,
        )
        if not options:
            return
        self.preview_pdf_export(
            "Staff Packet PDF",
            "staff_packet.pdf",
            len(self.project.sets) + 2,
            lambda path, progress_callback: export_staff_packet_pdf(
                path,
                self.project,
                self.project_dir,
                progress_callback=progress_callback,
                options=options,
            ),
        )

    def export_section_packet_pdf(self) -> None:
        sections = sorted({dot.section for dot in self.project.dots if dot.section})
        if not sections:
            QMessageBox.information(self, "No Sections", "No section names are assigned to marchers yet.")
            return
        section, ok = QInputDialog.getItem(self, "Section Packet", "Section", sections, 0, False)
        if not ok or not section:
            return
        options = self.print_template_options(
            "Section Packet Options",
            "section_packet",
            default_title=f"{section} Section Packet",
            force_section=section,
            include_warning_option=True,
        )
        if not options:
            return
        safe_section = "".join(character if character.isalnum() else "_" for character in section).strip("_") or "section"
        self.preview_pdf_export(
            "Section Packet PDF",
            f"{safe_section}_packet.pdf",
            len(self.project.sets) + 2,
            lambda path, progress_callback: export_staff_packet_pdf(
                path,
                self.project,
                self.project_dir,
                progress_callback=progress_callback,
                options=options,
            ),
        )

    def export_coordinate_summary_pdf(self) -> None:
        options = self.print_template_options(
            "Coordinate Summary Options",
            "coordinate_summary",
            default_title=f"{self.project.metadata.show_title} - Coordinate Summary",
            allow_section=True,
        )
        if not options:
            return
        self.preview_pdf_export(
            "Coordinate Summary PDF",
            "coordinate_summary.pdf",
            max(1, len(self.project.sets)),
            lambda path, progress_callback: export_coordinate_summary_pdf(
                path,
                self.project,
                progress_callback=progress_callback,
                options=options,
                project_dir=self.project_dir,
            ),
        )

    def export_batch_profile(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Export Batch Profile", str(self.project_dir))
        if not folder:
            return
        output_dir = Path(folder)
        progress = QProgressDialog("Starting batch export...", None, 0, 5, self)
        progress.setWindowTitle("Batch Export")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

        def set_step(label: str, value: int) -> None:
            progress.setLabelText(label)
            progress.setValue(value)
            QApplication.processEvents()

        try:
            set_step("Exporting staff packet...", 0)
            export_staff_packet_pdf(
                output_dir / "staff_packet.pdf",
                self.project,
                self.project_dir,
                options=PrintTemplateOptions(layout=self.stored_pdf_layout("staff_packet")),
            )
            set_step("Exporting dot books...", 1)
            export_dot_book_pdf(
                output_dir / "dot_book.pdf",
                self.project,
                options=PrintTemplateOptions(compact=True, layout=self.stored_pdf_layout("dot_book")),
                project_dir=self.project_dir,
            )
            set_step("Exporting coordinate summary...", 2)
            export_coordinate_summary_pdf(
                output_dir / "coordinate_summary.pdf",
                self.project,
                options=PrintTemplateOptions(compact=True, layout=self.stored_pdf_layout("coordinate_summary")),
                project_dir=self.project_dir,
            )
            set_step("Exporting coordinate CSV...", 3)
            export_coordinate_csv(output_dir / "coordinates.csv", self.project)
            set_step("Exporting project zip...", 4)
            export_project_zip(self.project_dir, output_dir / f"{self.project_dir.name}.zip", self.project)
            set_step("Batch export complete", 5)
        except Exception as exc:
            self.show_operation_failure("Batch Export Failed", "complete the batch export", exc, location=output_dir)
            return
        finally:
            progress.close()
        self.statusBar().showMessage("Batch export complete", 3500)

    def choose_mp4_options(self) -> Mp4ExportOptions | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("MP4 Export Options")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        resolution_combo = QComboBox()
        for label, width, height in (
            ("1080p - 1920 x 1080", 1920, 1080),
            ("1440p - 2560 x 1440", 2560, 1440),
            ("4K - 3840 x 2160", 3840, 2160),
        ):
            resolution_combo.addItem(label, (width, height))
        quality_combo = QComboBox()
        for label, crf, preset in (
            ("High quality (CRF 18)", 18, "slow"),
            ("Very high quality (CRF 14)", 14, "slow"),
            ("Draft / faster (CRF 24)", 24, "medium"),
        ):
            quality_combo.addItem(label, (crf, preset))
        encoder_combo = QComboBox()
        encoder_combo.addItem("Auto - best available", "auto")
        encoder_combo.addItem("H.264 - libx264", "libx264")
        encoder_combo.addItem("MPEG-4 - compatibility fallback", "mpeg4")
        fps_input = QSpinBox()
        fps_input.setRange(24, 60)
        fps_input.setValue(30)
        title_splash = QCheckBox("Show title splash at start")
        form.addRow("Resolution", resolution_combo)
        form.addRow("Quality", quality_combo)
        form.addRow("Video Encoder", encoder_combo)
        form.addRow("Frames Per Second", fps_input)
        form.addRow("Title Splash", title_splash)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        export_button = QPushButton("Export")
        cancel_button.clicked.connect(dialog.reject)
        export_button.clicked.connect(dialog.accept)
        buttons.addStretch()
        buttons.addWidget(cancel_button)
        buttons.addWidget(export_button)
        layout.addLayout(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        width, height = resolution_combo.currentData()
        crf, preset = quality_combo.currentData()
        return Mp4ExportOptions(
            fps=fps_input.value(),
            size=QSize(width, height),
            crf=crf,
            preset=preset,
            video_encoder=str(encoder_combo.currentData()),
            title_splash=title_splash.isChecked(),
        )

    def export_video(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export MP4", str(self.project_dir / "show.mp4"), "MP4 (*.mp4)")
        if not path:
            return
        ffmpeg_path = self.resolve_ffmpeg_path()
        if not ffmpeg_path:
            QMessageBox.warning(self, "Export Failed", "Select ffmpeg.exe first.")
            return
        options = self.choose_mp4_options()
        if not options:
            return
        previous_set_index = self.set_index
        previous_count = self.current_count
        progress = QProgressDialog("Preparing MP4 export...", "Cancel", 0, 1000, self)
        progress.setWindowTitle("Exporting MP4")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

        def update_progress(stage: str, current: int, total: int) -> None:
            progress.setLabelText(stage)
            progress.setMaximum(max(1, total))
            progress.setValue(min(current, total))
            QApplication.processEvents()

        temp_dir = tempfile.TemporaryDirectory(prefix="drill_pirate_mp4_frames_")
        frames_dir = Path(temp_dir.name)
        try:
            frame_result = render_mp4_frames(
                self.field,
                self.project_dir,
                frames_dir,
                self.project,
                options=options,
                progress_callback=update_progress,
                cancel_callback=progress.wasCanceled,
            )
        except ExportCancelled:
            progress.close()
            temp_dir.cleanup()
            self.statusBar().showMessage("MP4 export cancelled", 3000)
            return
        except Exception as exc:
            progress.close()
            temp_dir.cleanup()
            self.show_operation_failure("Export Failed", "render MP4 frames", exc, location=path)
            return
        finally:
            self.set_index = min(previous_set_index, len(self.project.sets) - 1)
            self.populate_sets()
            self.sync_timeline()
            self.set_count(previous_count, seek_audio=False)
        if progress.wasCanceled():
            progress.close()
            temp_dir.cleanup()
            self.statusBar().showMessage("MP4 export cancelled", 3000)
            return

        thread = Mp4EncodeThread(frames_dir, Path(path), frame_result, ffmpeg_path, options, self)
        self._active_mp4_thread = thread
        self._active_mp4_temp_dir = temp_dir
        self._active_mp4_progress = progress
        progress.canceled.connect(thread.request_cancel)
        thread.progress_changed.connect(update_progress)

        def cleanup_mp4_export() -> None:
            progress.close()
            if getattr(self, "_active_mp4_temp_dir", None) is temp_dir:
                temp_dir.cleanup()
                self._active_mp4_temp_dir = None
            if getattr(self, "_active_mp4_thread", None) is thread:
                self._active_mp4_thread = None
            if getattr(self, "_active_mp4_progress", None) is progress:
                self._active_mp4_progress = None
            thread.deleteLater()

        def complete_mp4_export() -> None:
            cleanup_mp4_export()
            self.statusBar().showMessage("MP4 exported", 3000)

        def cancel_mp4_export() -> None:
            cleanup_mp4_export()
            self.statusBar().showMessage("MP4 export cancelled", 3000)

        def fail_mp4_export(message: str) -> None:
            cleanup_mp4_export()
            self.show_operation_failure("Export Failed", "encode the MP4", RuntimeError(message), location=path)

        thread.export_completed.connect(complete_mp4_export)
        thread.export_cancelled.connect(cancel_mp4_export)
        thread.export_failed.connect(fail_mp4_export)
        thread.start()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.position_field_hud()
        self.position_minimap()
        QTimer.singleShot(0, self.apply_responsive_layout)

    def release_media_resources(self) -> None:
        try:
            self.play_timer.stop()
            self.audio_health_timer.stop()
            self.audio_device_refresh_timer.stop()
            self.conflict_heatmap_timer.stop()
            if hasattr(self, "waveform"):
                self.waveform.cancel_loading()
            if self.player.source().isValid():
                self.player.stop()
                self.player.setSource(QUrl())
        except RuntimeError:
            pass
        active_thread = getattr(self, "_active_mp4_thread", None)
        if active_thread is not None and active_thread.isRunning():
            active_thread.request_cancel()
        conflict_worker = getattr(self, "conflict_heatmap_worker", None)
        if conflict_worker is not None and conflict_worker.isRunning():
            conflict_worker.requestInterruption()
            conflict_worker.wait(5000)
        analysis_worker = getattr(self, "analysis_worker", None)
        if analysis_worker is not None and analysis_worker.isRunning():
            analysis_worker.requestInterruption()
            analysis_worker.wait(5000)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.release_media_resources()
        self.settings.setValue("main_window/dock_state", self.saveState())
        self.settings.sync()
        self.save()
        super().closeEvent(event)
