from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from drill_writer.core.analysis import transition_start_positions
from drill_writer.core.animation import distance, motion_window_for_dot
from drill_writer.core.models import DrillProject, Marker
from drill_writer.core.workflow import TransitionCandidate


@dataclass(slots=True)
class MovementLane:
    label: str
    dot_ids: list[str]
    start: float
    end: float
    speed: float


class TransitionTimelineWidget(QWidget):
    move_window_changed = Signal(list, float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: DrillProject | None = None
        self.set_index = 0
        self.selected_ids: list[str] = []
        self.group_mode = "Sections"
        self.lanes: list[MovementLane] = []
        self.label_width = 132
        self.row_height = 30
        self.header_height = 26
        self._drag_lane = -1
        self._drag_part = ""
        self._drag_origin = QPointF()
        self._drag_start = 0.0
        self._drag_end = 0.0
        self.setMouseTracking(True)
        self.setMinimumHeight(150)
        self.setToolTip("Drag bar edges to change movement start/end. Drag the bar to move the whole window.")

    def set_context(
        self,
        project: DrillProject,
        set_index: int,
        selected_ids: list[str],
        group_mode: str | None = None,
    ) -> None:
        self.project = project
        self.set_index = max(0, min(set_index, len(project.sets) - 1)) if project.sets else 0
        self.selected_ids = list(selected_ids)
        if group_mode is not None:
            self.group_mode = group_mode
        self.rebuild_lanes()

    def rebuild_lanes(self) -> None:
        self.lanes = []
        if not self.project or not self.project.sets:
            self.update()
            return
        drill_set = self.project.sets[self.set_index]
        starts = transition_start_positions(self.project, self.set_index)
        groups: dict[str, list[str]] = {}
        if self.group_mode == "Selected Marchers" and self.selected_ids:
            for dot_id in self.selected_ids:
                dot = self.project.dot_by_id(dot_id)
                if dot:
                    groups[dot.name or dot.id] = [dot_id]
        else:
            target_ids = [dot.id for dot in self.project.dots]
            for dot_id in target_ids:
                dot = self.project.dot_by_id(dot_id)
                if dot:
                    groups.setdefault(dot.section or "Unassigned", []).append(dot_id)
        for label, dot_ids in sorted(groups.items()):
            windows = [motion_window_for_dot(drill_set, dot_id) for dot_id in dot_ids]
            start = min((window[0] for window in windows), default=float(drill_set.start_count))
            end = max((window[1] for window in windows), default=float(drill_set.end_count))
            longest_move = max(
                (
                    distance(starts.get(dot_id, drill_set.dot_positions.get(dot_id, (0.0, 0.0))), drill_set.dot_positions.get(dot_id, (0.0, 0.0)))
                    for dot_id in dot_ids
                ),
                default=0.0,
            )
            self.lanes.append(MovementLane(label, dot_ids, start, end, longest_move / max(0.001, end - start)))
        content_rows = max(3, len(self.lanes))
        self.setMinimumHeight(self.header_height + content_rows * self.row_height + 8)
        self.setMinimumWidth(520)
        self.update()

    def timeline_rect(self) -> QRectF:
        return QRectF(
            self.label_width,
            self.header_height,
            max(40, self.width() - self.label_width - 12),
            max(20, self.height() - self.header_height - 8),
        )

    def count_to_x(self, count: float) -> float:
        if not self.project or not self.project.sets:
            return float(self.label_width)
        drill_set = self.project.sets[self.set_index]
        rect = self.timeline_rect()
        progress = (count - drill_set.start_count) / max(1.0, drill_set.end_count - drill_set.start_count)
        return rect.left() + max(0.0, min(1.0, progress)) * rect.width()

    def x_to_count(self, x: float) -> float:
        if not self.project or not self.project.sets:
            return 1.0
        drill_set = self.project.sets[self.set_index]
        rect = self.timeline_rect()
        progress = max(0.0, min(1.0, (x - rect.left()) / max(1.0, rect.width())))
        count = drill_set.start_count + progress * (drill_set.end_count - drill_set.start_count)
        return round(count * 2) / 2

    def lane_rect(self, index: int) -> QRectF:
        top = self.header_height + index * self.row_height + 5
        lane = self.lanes[index]
        left = self.count_to_x(lane.start)
        right = self.count_to_x(lane.end)
        return QRectF(left, top, max(8.0, right - left), self.row_height - 10)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())
        if not self.project or not self.project.sets:
            painter.setPen(palette.text().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No transition selected")
            return
        drill_set = self.project.sets[self.set_index]
        rect = self.timeline_rect()
        painter.setPen(QPen(palette.mid().color(), 1))
        for count in range(drill_set.start_count, drill_set.end_count + 1):
            x = self.count_to_x(float(count))
            painter.drawLine(int(x), int(rect.top() - self.header_height + 4), int(x), int(rect.bottom()))
            painter.setPen(palette.text().color())
            painter.drawText(QRectF(x - 16, 2, 32, 20), Qt.AlignmentFlag.AlignCenter, str(count))
            painter.setPen(QPen(palette.mid().color(), 1))
        accent = self.palette().highlight().color()
        for index, lane in enumerate(self.lanes):
            y = self.header_height + index * self.row_height
            painter.setPen(palette.text().color())
            painter.drawText(QRectF(6, y, self.label_width - 12, self.row_height), Qt.AlignmentFlag.AlignVCenter, lane.label)
            bar = self.lane_rect(index)
            fill = QColor(accent)
            fill.setAlpha(190)
            painter.setBrush(fill)
            painter.setPen(QPen(accent.lighter(135), 1.2))
            painter.drawRoundedRect(bar, 5, 5)
            painter.setBrush(QColor("#f7d154"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(bar.left(), bar.center().y()), 4, 4)
            painter.drawEllipse(QPointF(bar.right(), bar.center().y()), 4, 4)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(bar.adjusted(7, 0, -7, 0), Qt.AlignmentFlag.AlignCenter, f"{lane.start:g}-{lane.end:g}  {lane.speed:.2f} yd/count")
        painter.end()

    def hit_test(self, point: QPointF) -> tuple[int, str]:
        for index in range(len(self.lanes)):
            bar = self.lane_rect(index)
            if abs(point.x() - bar.left()) <= 7 and bar.adjusted(-7, -4, 7, 4).contains(point):
                return index, "start"
            if abs(point.x() - bar.right()) <= 7 and bar.adjusted(-7, -4, 7, 4).contains(point):
                return index, "end"
            if bar.contains(point):
                return index, "bar"
        return -1, ""

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton:
            return
        lane_index, part = self.hit_test(event.position())
        if lane_index < 0:
            return
        lane = self.lanes[lane_index]
        self._drag_lane = lane_index
        self._drag_part = part
        self._drag_origin = event.position()
        self._drag_start = lane.start
        self._drag_end = lane.end
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_lane < 0 or not self.project:
            lane_index, part = self.hit_test(event.position())
            self.setCursor(
                Qt.CursorShape.SizeHorCursor if part in {"start", "end", "bar"} else Qt.CursorShape.ArrowCursor
            )
            return
        drill_set = self.project.sets[self.set_index]
        lane = self.lanes[self._drag_lane]
        current_count = self.x_to_count(event.position().x())
        origin_count = self.x_to_count(self._drag_origin.x())
        if self._drag_part == "start":
            lane.start = max(float(drill_set.start_count), min(current_count, lane.end))
        elif self._drag_part == "end":
            lane.end = min(float(drill_set.end_count), max(current_count, lane.start))
        else:
            delta = current_count - origin_count
            duration = self._drag_end - self._drag_start
            lane.start = max(float(drill_set.start_count), min(self._drag_start + delta, float(drill_set.end_count) - duration))
            lane.end = lane.start + duration
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_lane < 0:
            return
        lane = self.lanes[self._drag_lane]
        self.move_window_changed.emit(list(lane.dot_ids), lane.start, lane.end)
        self._drag_lane = -1
        self._drag_part = ""
        event.accept()


class SmartTransitionDialog(QDialog):
    def __init__(
        self,
        candidates: list[TransitionCandidate],
        preview_callback: Callable[[TransitionCandidate], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.candidates = candidates
        self.preview_callback = preview_callback
        self.setWindowTitle("Smart Transition Composer")
        self.resize(760, 430)
        layout = QVBoxLayout(self)
        note = QLabel("Compare complete marcher assignments. Lower scores indicate less travel and fewer predicted conflicts.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(len(candidates), 6)
        self.table.setHorizontalHeaderLabels(["Strategy", "Total yd", "Longest", "Crossings", "Spacing", "Score"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        for row, candidate in enumerate(candidates):
            values = (
                candidate.label,
                f"{candidate.score.total_distance:.1f}",
                f"{candidate.score.maximum_distance:.1f}",
                str(candidate.score.crossings),
                str(candidate.score.spacing_conflicts),
                f"{candidate.score.weighted_score:.1f}",
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self.table.itemSelectionChanged.connect(self.preview_selected)
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply)
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("Apply Assignment")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if candidates:
            self.table.selectRow(0)

    def preview_selected(self) -> None:
        candidate = self.selected_candidate()
        if candidate:
            self.preview_callback(candidate)

    def selected_candidate(self) -> TransitionCandidate | None:
        row = self.table.currentRow()
        return self.candidates[row] if 0 <= row < len(self.candidates) else None


class PropertyBrushDialog(QDialog):
    PROPERTIES = (
        ("position", "Position / relative form"),
        ("path", "Path anchors and Bezier handles"),
        ("facing", "Facing"),
        ("movement_style", "Movement style"),
        ("timing", "Movement timing window"),
        ("appearance", "Color and metadata"),
        ("constraints", "Constraints"),
    )

    def __init__(self, checked: set[str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Property Paintbrush")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose exactly which properties the brush copies and paints."))
        self.checkboxes: dict[str, QCheckBox] = {}
        selected = checked or {"position", "path", "facing", "movement_style", "timing"}
        for key, label in self.PROPERTIES:
            checkbox = QCheckBox(label)
            checkbox.setChecked(key in selected)
            self.checkboxes[key] = checkbox
            layout.addWidget(checkbox)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_properties(self) -> set[str]:
        return {key for key, checkbox in self.checkboxes.items() if checkbox.isChecked()}


class MacroReplayDialog(QDialog):
    def __init__(self, defaults: dict[str, object] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        defaults = defaults or {}
        self.setWindowTitle("Parameterized Macro Replay")
        layout = QFormLayout(self)
        self.repeat_count = QSpinBox()
        self.repeat_count.setRange(1, 999)
        self.repeat_count.setValue(int(defaults.get("repeat_count", 1)))
        self.advance_sets = QCheckBox("Advance one set after each run")
        self.advance_sets.setChecked(bool(defaults.get("advance_sets", False)))
        self.restore_selection = QCheckBox("Use selection recorded with each step")
        self.restore_selection.setChecked(bool(defaults.get("restore_selection", False)))
        self.restore_values = QCheckBox("Restore recorded tool values and count")
        self.restore_values.setChecked(bool(defaults.get("restore_values", True)))
        layout.addRow("Repeat", self.repeat_count)
        layout.addRow(self.advance_sets)
        layout.addRow(self.restore_selection)
        layout.addRow(self.restore_values)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict[str, object]:
        return {
            "repeat_count": self.repeat_count.value(),
            "advance_sets": self.advance_sets.isChecked(),
            "restore_selection": self.restore_selection.isChecked(),
            "restore_values": self.restore_values.isChecked(),
        }


class BeatSetGeneratorDialog(QDialog):
    def __init__(self, markers: list[Marker], selected_rows: set[int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.markers = markers
        self.setWindowTitle("Beat-to-Set Generator")
        self.resize(520, 480)
        layout = QVBoxLayout(self)
        note = QLabel("Choose musical markers that should become set boundaries. Existing tempo, ritardando, fermata, and audio timing events remain attached to their counts.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.marker_list = QListWidget()
        for index, marker in enumerate(markers):
            item = QListWidgetItem(f"Count {marker.count:g}  —  {marker.label}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if not selected_rows or index in selected_rows else Qt.CheckState.Unchecked
            )
            self.marker_list.addItem(item)
        layout.addWidget(self.marker_list, 1)
        options = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_all.clicked.connect(lambda: self.set_all_markers(Qt.CheckState.Checked))
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self.set_all_markers(Qt.CheckState.Unchecked))
        options.addWidget(select_all)
        options.addWidget(clear)
        options.addStretch()
        layout.addLayout(options)
        self.replace_sets = QCheckBox("Replace the existing set structure (undoable)")
        self.replace_sets.setChecked(True)
        layout.addWidget(self.replace_sets)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Generate Sets")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_all_markers(self, state: Qt.CheckState) -> None:
        for row in range(self.marker_list.count()):
            self.marker_list.item(row).setCheckState(state)

    def selected_markers(self) -> list[Marker]:
        return [
            marker
            for row, marker in enumerate(self.markers)
            if self.marker_list.item(row).checkState() == Qt.CheckState.Checked
        ]
