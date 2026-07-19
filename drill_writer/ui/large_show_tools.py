from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from drill_writer.core.analysis import ConflictTimelineEntry, build_conflict_timeline
from drill_writer.core.large_show import (
    CleanupOptions,
    RosterImportResult,
    compare_sets,
    create_group,
    create_linked_formation,
    detach_linked_formation,
    generate_hierarchical_groups,
    group_dot_ids,
    parse_roster_csv,
    save_formation_variation,
    variation_positions,
    workflow_records,
)
from drill_writer.core.models import DrillProject
from drill_writer.core.workflow import TransformParameters
from drill_writer.ui.field_view import EditorTool, FieldView


class RosterImportDialog(QDialog):
    def __init__(self, path: Path, existing_ids: list[str], parent=None) -> None:
        super().__init__(parent)
        self.path = path
        self.merge_result = parse_roster_csv(path)
        self.append_result = parse_roster_csv(path, existing_ids)
        self.setWindowTitle("Import Roster CSV")
        self.resize(880, 610)
        layout = QVBoxLayout(self)
        title = QLabel(f"{path.name} — {len(self.merge_result.dots)} performers")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        help_text = QLabel(
            "Columns are detected automatically. Missing IDs, colors, and layers are generated from instrument and section data."
        )
        help_text.setWordWrap(True)
        self.mode = QComboBox()
        self.mode.addItem("Merge roster / update matching IDs", "merge")
        self.mode.addItem("Append as new performers", "append")
        self.mode.currentIndexChanged.connect(self.refresh_preview)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Instrument", "Section", "Rank", "Color", "Layer", "Equipment"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import Roster")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(title)
        layout.addWidget(help_text)
        layout.addWidget(self.mode)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.warning_label)
        layout.addWidget(buttons)
        self.refresh_preview()

    def selected_result(self) -> RosterImportResult:
        return self.append_result if self.mode.currentData() == "append" else self.merge_result

    def selected_mode(self) -> str:
        return str(self.mode.currentData())

    def refresh_preview(self) -> None:
        result = self.selected_result()
        self.table.setRowCount(len(result.dots))
        for row, dot in enumerate(result.dots):
            values = (dot.id, dot.name, dot.instrument, dot.section, dot.rank, dot.color, dot.layer, dot.equipment)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 5:
                    item.setBackground(QColor(dot.color))
                self.table.setItem(row, column, item)
        mapped = ", ".join(f"{key} → {value}" for key, value in result.column_map.items())
        messages = ([f"Detected: {mapped}"] if mapped else []) + result.warnings
        self.warning_label.setText("\n".join(messages[:6]))


class PerformerReplacementDialog(QDialog):
    def __init__(self, dot, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Replace Performer At {dot.id}")
        layout = QVBoxLayout(self)
        note = QLabel(
            f"The drill spot <b>{dot.id}</b>, every coordinate, path, facing, and timing assignment will stay intact. "
            "Only performer roster information changes."
        )
        note.setWordWrap(True)
        form = QFormLayout()
        self.editors: dict[str, QLineEdit] = {}
        for field_name, label in (
            ("name", "Name"),
            ("instrument", "Instrument"),
            ("section", "Section"),
            ("rank", "Rank / File"),
            ("equipment", "Equipment"),
            ("layer", "Layer"),
            ("color", "Dot Color"),
        ):
            editor = QLineEdit(str(getattr(dot, field_name)))
            self.editors[field_name] = editor
            form.addRow(label, editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Replace Performer")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(note)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def fields(self) -> dict[str, str]:
        return {name: editor.text().strip() for name, editor in self.editors.items()}


class GroupManagerDialog(QDialog):
    select_requested = Signal(list)
    transform_requested = Signal(list, object)
    project_changed = Signal()

    def __init__(self, project: DrillProject, selected_provider: Callable[[], list[str]], parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.selected_provider = selected_provider
        self.setWindowTitle("Hierarchy & Linked Formations")
        self.resize(920, 650)
        outer = QVBoxLayout(self)
        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Ensemble Hierarchy"))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Group", "Members", "Locked"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemDoubleClicked.connect(lambda _item, _column: self.select_current_group())
        left_layout.addWidget(self.tree, 1)
        group_buttons = QHBoxLayout()
        for label, callback in (
            ("Build From Roster", self.build_from_roster),
            ("New Root", lambda: self.add_group(False)),
            ("New Child", lambda: self.add_group(True)),
            ("Delete", self.delete_group),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            group_buttons.addWidget(button)
        left_layout.addLayout(group_buttons)
        group_actions = QHBoxLayout()
        select_button = QPushButton("Select Members")
        select_button.clicked.connect(self.select_current_group)
        lock_button = QPushButton("Toggle Lock")
        lock_button.clicked.connect(self.toggle_lock)
        rename_button = QPushButton("Rename")
        rename_button.clicked.connect(self.rename_group)
        group_actions.addWidget(select_button)
        group_actions.addWidget(lock_button)
        group_actions.addWidget(rename_button)
        left_layout.addLayout(group_actions)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        transform_box = QWidget()
        transform_form = QFormLayout(transform_box)
        self.offset_x = self.transform_spin(-120, 120, 0, " yd")
        self.offset_y = self.transform_spin(-80, 80, 0, " yd")
        self.rotation = self.transform_spin(-360, 360, 0, "°")
        self.scale_x = self.transform_spin(-10, 10, 1, "×")
        self.scale_y = self.transform_spin(-10, 10, 1, "×")
        transform_form.addRow("Move X", self.offset_x)
        transform_form.addRow("Move Y", self.offset_y)
        transform_form.addRow("Rotation", self.rotation)
        transform_form.addRow("Scale X", self.scale_x)
        transform_form.addRow("Scale Y", self.scale_y)
        transform_button = QPushButton("Transform Selected Group")
        transform_button.clicked.connect(self.transform_current_group)
        transform_form.addRow(transform_button)
        right_layout.addWidget(QLabel("Group Transform"))
        right_layout.addWidget(transform_box)

        right_layout.addWidget(QLabel("Linked Formations"))
        self.link_list = QListWidget()
        right_layout.addWidget(self.link_list, 1)
        link_buttons = QHBoxLayout()
        create_link_button = QPushButton("Link Groups")
        create_link_button.clicked.connect(self.create_link)
        detach_button = QPushButton("Detach")
        detach_button.clicked.connect(self.detach_link)
        link_buttons.addWidget(create_link_button)
        link_buttons.addWidget(detach_button)
        right_layout.addLayout(link_buttons)
        link_help = QLabel(
            "Edit any attached block and corresponding marchers in repeated or mirrored blocks move with it. Detach when independent editing is needed."
        )
        link_help.setWordWrap(True)
        right_layout.addWidget(link_help)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.rejected.connect(self.reject)
        outer.addWidget(splitter, 1)
        outer.addWidget(close_buttons)
        self.refresh()

    @staticmethod
    def transform_spin(minimum: float, maximum: float, value: float, suffix: str) -> QDoubleSpinBox:
        editor = QDoubleSpinBox()
        editor.setRange(minimum, maximum)
        editor.setDecimals(3)
        editor.setValue(value)
        editor.setSuffix(suffix)
        return editor

    def current_group_id(self) -> str:
        item = self.tree.currentItem()
        return str(item.data(0, Qt.ItemDataRole.UserRole)) if item else ""

    def refresh(self) -> None:
        current_id = self.current_group_id()
        self.tree.clear()
        items: dict[str, QTreeWidgetItem] = {}
        records = workflow_records(self.project, "hierarchical_groups")
        for group in records:
            group_id = str(group.get("id", ""))
            item = QTreeWidgetItem(
                [
                    str(group.get("name", "Group")),
                    str(len(group_dot_ids(self.project, group_id))),
                    "Yes" if bool(group.get("locked", False)) else "",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, group_id)
            items[group_id] = item
        for group in records:
            group_id = str(group.get("id", ""))
            parent_id = str(group.get("parent_id", ""))
            if parent_id and parent_id in items:
                items[parent_id].addChild(items[group_id])
            else:
                self.tree.addTopLevelItem(items[group_id])
        self.tree.expandAll()
        if current_id and current_id in items:
            self.tree.setCurrentItem(items[current_id])
        self.link_list.clear()
        for record in workflow_records(self.project, "linked_formations"):
            status = "attached" if bool(record.get("attached", True)) else "detached"
            item = QListWidgetItem(f"{record.get('name', 'Linked Formation')} — {status}")
            item.setData(Qt.ItemDataRole.UserRole, str(record.get("id", "")))
            self.link_list.addItem(item)

    def build_from_roster(self) -> None:
        if workflow_records(self.project, "hierarchical_groups"):
            answer = QMessageBox.question(
                self,
                "Replace Hierarchy?",
                "Rebuild the hierarchy from roster metadata? Existing custom groups will be replaced.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        generate_hierarchical_groups(self.project)
        self.project.workflow["linked_formations"] = []
        self.project_changed.emit()
        self.refresh()

    def add_group(self, child: bool) -> None:
        selected = self.selected_provider()
        if not selected:
            QMessageBox.information(self, "Create Group", "Select one or more marchers on the field first.")
            return
        parent_id = self.current_group_id() if child else ""
        name, accepted = QInputDialog.getText(self, "Create Group", "Group name:")
        if not accepted or not name.strip():
            return
        create_group(self.project, name, selected, parent_id)
        self.project_changed.emit()
        self.refresh()

    def delete_group(self) -> None:
        group_id = self.current_group_id()
        if not group_id:
            return
        descendants = {group_id}
        changed = True
        while changed:
            changed = False
            for group in workflow_records(self.project, "hierarchical_groups"):
                if str(group.get("parent_id", "")) in descendants and str(group.get("id", "")) not in descendants:
                    descendants.add(str(group.get("id", "")))
                    changed = True
        self.project.workflow["hierarchical_groups"] = [
            group for group in workflow_records(self.project, "hierarchical_groups") if str(group.get("id", "")) not in descendants
        ]
        self.project.workflow["linked_formations"] = [
            link
            for link in workflow_records(self.project, "linked_formations")
            if str(link.get("master_group_id", "")) not in descendants
            and not any(str(instance.get("group_id", "")) in descendants for instance in link.get("instances", []) if isinstance(instance, dict))
        ]
        self.project_changed.emit()
        self.refresh()

    def rename_group(self) -> None:
        group_id = self.current_group_id()
        record = next((group for group in workflow_records(self.project, "hierarchical_groups") if group.get("id") == group_id), None)
        if not record:
            return
        name, accepted = QInputDialog.getText(self, "Rename Group", "Name:", text=str(record.get("name", "Group")))
        if accepted and name.strip():
            record["name"] = name.strip()
            self.project_changed.emit()
            self.refresh()

    def toggle_lock(self) -> None:
        group_id = self.current_group_id()
        record = next((group for group in workflow_records(self.project, "hierarchical_groups") if group.get("id") == group_id), None)
        if record:
            record["locked"] = not bool(record.get("locked", False))
            self.project_changed.emit()
            self.refresh()

    def select_current_group(self) -> None:
        group_id = self.current_group_id()
        ids = group_dot_ids(self.project, group_id)
        if ids:
            self.select_requested.emit(ids)

    def transform_current_group(self) -> None:
        ids = group_dot_ids(self.project, self.current_group_id())
        if not ids:
            return
        parameters = TransformParameters(
            offset_x=self.offset_x.value(),
            offset_y=self.offset_y.value(),
            rotation_degrees=self.rotation.value(),
            scale_x=self.scale_x.value(),
            scale_y=self.scale_y.value(),
        )
        self.transform_requested.emit(ids, parameters)

    def create_link(self) -> None:
        master_id = self.current_group_id()
        if not master_id:
            QMessageBox.information(self, "Link Groups", "Select the master group in the hierarchy first.")
            return
        groups = [group for group in workflow_records(self.project, "hierarchical_groups") if group.get("id") != master_id]
        if not groups:
            return
        labels = [f"{group.get('name', 'Group')} ({len(group_dot_ids(self.project, str(group.get('id', ''))))})" for group in groups]
        label, accepted = QInputDialog.getItem(self, "Link Groups", "Instance group:", labels, 0, False)
        if not accepted:
            return
        instance = groups[labels.index(label)]
        mirrored = QMessageBox.question(
            self,
            "Mirrored Instance",
            "Should horizontal edits be mirrored for this instance?",
        ) == QMessageBox.StandardButton.Yes
        name, accepted = QInputDialog.getText(self, "Linked Formation", "Link name:", text="Linked Blocks")
        if not accepted:
            return
        try:
            create_linked_formation(
                self.project,
                name,
                master_id,
                [str(instance.get("id", ""))],
                [str(instance.get("id", ""))] if mirrored else [],
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot Link Groups", str(exc))
            return
        self.project_changed.emit()
        self.refresh()

    def detach_link(self) -> None:
        item = self.link_list.currentItem()
        if item and detach_linked_formation(self.project, str(item.data(Qt.ItemDataRole.UserRole))):
            self.project_changed.emit()
            self.refresh()


class CleanupDialog(QDialog):
    def __init__(self, selected_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Automatic Form Cleanup")
        layout = QVBoxLayout(self)
        label = QLabel(f"Clean {selected_count} selected marchers while preserving the recognizable form.")
        label.setWordWrap(True)
        form = QFormLayout()
        self.minimum_spacing = QDoubleSpinBox()
        self.minimum_spacing.setRange(0.25, 8)
        self.minimum_spacing.setValue(1.25)
        self.minimum_spacing.setSuffix(" yd")
        self.strength = QDoubleSpinBox()
        self.strength.setRange(0.05, 1)
        self.strength.setSingleStep(0.05)
        self.strength.setValue(0.65)
        self.iterations = QDoubleSpinBox()
        self.iterations.setRange(1, 30)
        self.iterations.setDecimals(0)
        self.iterations.setValue(8)
        self.remove_overlaps = QCheckBox("Remove overlaps")
        self.remove_overlaps.setChecked(True)
        self.normalize_intervals = QCheckBox("Normalize intervals")
        self.normalize_intervals.setChecked(True)
        self.smooth_curvature = QCheckBox("Smooth curved segments")
        self.smooth_curvature.setChecked(True)
        self.repair_corners = QCheckBox("Preserve and repair corners")
        self.repair_corners.setChecked(True)
        form.addRow("Minimum spacing", self.minimum_spacing)
        form.addRow("Strength", self.strength)
        form.addRow("Passes", self.iterations)
        form.addRow(self.remove_overlaps)
        form.addRow(self.normalize_intervals)
        form.addRow(self.smooth_curvature)
        form.addRow(self.repair_corners)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Preview Cleanup")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(label)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def options(self) -> CleanupOptions:
        return CleanupOptions(
            minimum_spacing=self.minimum_spacing.value(),
            normalize_intervals=self.normalize_intervals.isChecked(),
            smooth_curvature=self.smooth_curvature.isChecked(),
            remove_overlaps=self.remove_overlaps.isChecked(),
            repair_corners=self.repair_corners.isChecked(),
            strength=self.strength.value(),
            iterations=int(self.iterations.value()),
        )


class ConflictHeatmapWidget(QWidget):
    count_clicked = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.entries: list[ConflictTimelineEntry] = []
        self.start_count = 1.0
        self.end_count = 1.0
        self.tokens = {
            "panel_color": "#171a21",
            "text_color": "#f3f5f7",
            "border_color": "#343a46",
        }
        self.setMinimumHeight(70)
        self.setMouseTracking(True)
        self.setToolTip("Live conflict heatmap. Click a warning segment to jump to that count.")

    def set_theme_tokens(self, tokens: dict[str, str]) -> None:
        self.tokens.update(tokens)
        self.update()

    def set_entries(self, entries: list[ConflictTimelineEntry], start_count: float, end_count: float) -> None:
        self.entries = list(entries)
        self.start_count = float(start_count)
        self.end_count = max(float(end_count), self.start_count + 0.001)
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(self.tokens["panel_color"]))
        area = self.rect().adjusted(8, 20, -8, -12)
        painter.setPen(QPen(QColor(self.tokens["border_color"]), 1))
        painter.drawRoundedRect(area, 4, 4)
        entry_by_slot = sorted(self.entries, key=lambda entry: entry.count)
        slot_count = max(24, len(entry_by_slot))
        width = area.width() / slot_count
        for slot in range(slot_count):
            count = self.start_count + (self.end_count - self.start_count) * slot / max(1, slot_count - 1)
            entry = min(entry_by_slot, key=lambda value: abs(value.count - count)) if entry_by_slot else None
            total = entry.total if entry and abs(entry.count - count) <= (self.end_count - self.start_count) / max(1, slot_count) * 1.5 else 0
            color = QColor("#2f9e63") if total == 0 else QColor("#f2c94c") if total <= 2 else QColor("#f2994a") if total <= 7 else QColor("#eb5757")
            painter.fillRect(QRectF(area.left() + slot * width, area.top() + 1, width + 0.5, area.height() - 1), color)
        painter.setPen(QColor(self.tokens["text_color"]))
        painter.drawText(8, 14, "Live conflict heatmap")
        painter.drawText(area.left(), self.height() - 1, f"{self.start_count:g}")
        end_text = f"{self.end_count:g}"
        painter.drawText(area.right() - painter.fontMetrics().horizontalAdvance(end_text), self.height() - 1, end_text)

    def entry_at(self, x: float) -> ConflictTimelineEntry | None:
        if not self.entries:
            return None
        ratio = max(0.0, min(1.0, (x - 8) / max(1.0, self.width() - 16)))
        count = self.start_count + (self.end_count - self.start_count) * ratio
        return min(self.entries, key=lambda entry: abs(entry.count - count))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            entry = self.entry_at(event.position().x())
            if entry:
                self.count_clicked.emit(entry.count)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        entry = self.entry_at(event.position().x())
        if entry:
            self.setToolTip(
                f"Count {entry.count:.2f}: {entry.total} conflicts — spacing {entry.spacing_conflicts}, "
                f"speed {entry.speed_conflicts}, crossings {entry.crossing_conflicts}, "
                f"no-go {entry.no_go_conflicts}"
            )
        super().mouseMoveEvent(event)


class ConflictHeatmapWorker(QThread):
    completed = Signal(list, int)
    failed = Signal(str, int)

    def __init__(
        self,
        project: DrillProject,
        set_index: int,
        minimum_spacing: float,
        maximum_speed: float,
        generation: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.project = deepcopy(project)
        self.set_index = set_index
        self.minimum_spacing = minimum_spacing
        self.maximum_speed = maximum_speed
        self.generation = generation

    def run(self) -> None:
        try:
            entries = build_conflict_timeline(
                self.project,
                self.set_index,
                min_spacing=self.minimum_spacing,
                max_yards_per_count=self.maximum_speed,
                samples=28,
                fast_crossings=True,
                cancel_callback=self.isInterruptionRequested,
            )
            if self.isInterruptionRequested():
                return
            self.completed.emit(entries, self.generation)
        except Exception as exc:
            self.failed.emit(str(exc), self.generation)


class SetComparisonDialog(QDialog):
    select_requested = Signal(list)

    def __init__(self, project: DrillProject, project_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.project_dir = project_dir
        self.setWindowTitle("Compare Sets")
        self.resize(1220, 760)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.first_set = QComboBox()
        self.second_set = QComboBox()
        for index, drill_set in enumerate(project.sets):
            label = f"{index + 1}: {drill_set.name}"
            self.first_set.addItem(label, index)
            self.second_set.addItem(label, index)
        self.first_set.setCurrentIndex(max(0, min(len(project.sets) - 1, getattr(parent, "set_index", 0) - 1)))
        self.second_set.setCurrentIndex(max(0, min(len(project.sets) - 1, getattr(parent, "set_index", 0))))
        self.first_set.currentIndexChanged.connect(self.refresh)
        self.second_set.currentIndexChanged.connect(self.refresh)
        controls.addWidget(QLabel("Set A"))
        controls.addWidget(self.first_set, 1)
        controls.addWidget(QLabel("Set B"))
        controls.addWidget(self.second_set, 1)
        field_split = QSplitter()
        self.first_field = self.read_only_field()
        self.second_field = self.read_only_field()
        field_split.addWidget(self.first_field)
        field_split.addWidget(self.second_field)
        field_split.setSizes([600, 600])
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Marcher", "Distance", "Direction", "Change"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self.emit_selected_rows)
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.rejected.connect(self.reject)
        layout.addLayout(controls)
        layout.addWidget(field_split, 3)
        layout.addWidget(QLabel("Difference vectors (largest movement first)"))
        layout.addWidget(self.table, 2)
        layout.addWidget(close_buttons)
        self.refresh()

    def read_only_field(self) -> FieldView:
        field = FieldView()
        field.set_project(self.project, self.project_dir)
        field.set_tool(EditorTool.SELECT)
        field.setInteractive(False)
        for item in field.dot_items.values():
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        field.fitInView(field.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        return field

    def refresh(self) -> None:
        first_index = int(self.first_set.currentData() or 0)
        second_index = int(self.second_set.currentData() or 0)
        first_positions = self.project.sets[first_index].dot_positions
        second_positions = self.project.sets[second_index].dot_positions
        self.first_field.clear_preview()
        self.first_field.set_positions(first_positions)
        self.second_field.set_positions(second_positions)
        self.second_field.show_preview(first_positions, second_positions)
        differences = compare_sets(self.project, first_index, second_index)
        self.table.setRowCount(len(differences))
        for row, difference in enumerate(differences):
            dot = self.project.dot_by_id(difference.dot_id)
            values = (
                f"{difference.dot_id} — {dot.name if dot else ''}",
                f"{difference.distance:.2f} yd",
                f"{difference.angle_degrees:.1f}°",
                f"({difference.end[0] - difference.start[0]:+.2f}, {difference.end[1] - difference.start[1]:+.2f})",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, difference.dot_id)
                self.table.setItem(row, column, item)

    def emit_selected_rows(self) -> None:
        ids = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item:
                ids.append(str(item.data(Qt.ItemDataRole.UserRole)))
        if ids:
            self.select_requested.emit(ids)


class FormationVariationsDialog(QDialog):
    apply_requested = Signal(object)

    def __init__(self, project: DrillProject, set_index: int, selected_ids: list[str], parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.set_index = set_index
        self.selected_ids = selected_ids
        self.setWindowTitle("Formation Variations")
        self.resize(760, 520)
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.refresh_summary)
        left.addWidget(self.list, 1)
        save_selected = QPushButton("Save Selected As Variation")
        save_selected.clicked.connect(lambda: self.save_variation(True))
        save_all = QPushButton("Save Full Set As Variation")
        save_all.clicked.connect(lambda: self.save_variation(False))
        delete_button = QPushButton("Delete Variation")
        delete_button.clicked.connect(self.delete_variation)
        left.addWidget(save_selected)
        left.addWidget(save_all)
        left.addWidget(delete_button)
        right = QVBoxLayout()
        self.summary = QLabel("Save alternate formations without duplicating the project.")
        self.summary.setWordWrap(True)
        self.preview = FieldView()
        self.preview.set_project(project)
        self.preview.setInteractive(False)
        apply_button = QPushButton("Apply Variation To Current Set")
        apply_button.clicked.connect(self.apply_current)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        right.addWidget(self.summary)
        right.addWidget(self.preview, 1)
        right.addWidget(apply_button)
        right.addWidget(close_button)
        layout.addLayout(left, 2)
        layout.addLayout(right, 3)
        self.refresh_list()

    def refresh_list(self) -> None:
        current_id = self.current_id()
        self.list.clear()
        for record in workflow_records(self.project, "formation_variations"):
            item = QListWidgetItem(
                f"{record.get('name', 'Variation')} — Set {int(record.get('set_index', 0)) + 1} — {len(record.get('dot_ids', []))} dots"
            )
            item.setData(Qt.ItemDataRole.UserRole, str(record.get("id", "")))
            self.list.addItem(item)
            if item.data(Qt.ItemDataRole.UserRole) == current_id:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)

    def current_id(self) -> str:
        item = self.list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else ""

    def current_record(self) -> dict[str, Any] | None:
        record_id = self.current_id()
        return next((record for record in workflow_records(self.project, "formation_variations") if record.get("id") == record_id), None)

    def save_variation(self, selected_only: bool) -> None:
        if selected_only and not self.selected_ids:
            QMessageBox.information(self, "Formation Variation", "Select marchers first, or save the full set.")
            return
        name, accepted = QInputDialog.getText(self, "Save Variation", "Variation name:")
        if not accepted or not name.strip():
            return
        record = save_formation_variation(
            self.project,
            name,
            self.set_index,
            self.selected_ids if selected_only else [],
        )
        self.refresh_list()
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == record["id"]:
                self.list.setCurrentRow(row)
                break

    def delete_variation(self) -> None:
        record_id = self.current_id()
        self.project.workflow["formation_variations"] = [
            record for record in workflow_records(self.project, "formation_variations") if record.get("id") != record_id
        ]
        self.refresh_list()

    def refresh_summary(self) -> None:
        record = self.current_record()
        if not record:
            return
        positions = variation_positions(record)
        base_index = max(0, min(int(record.get("set_index", self.set_index)), len(self.project.sets) - 1))
        base = self.project.sets[base_index].dot_positions
        self.preview.set_positions(base)
        self.preview.show_preview(base, positions)
        self.summary.setText(
            f"{record.get('name', 'Variation')}\n"
            f"Saved from set {base_index + 1}; {len(positions)} marcher positions. Yellow vectors show the saved alternative."
        )

    def apply_current(self) -> None:
        record = self.current_record()
        if record:
            self.apply_requested.emit(deepcopy(record))
