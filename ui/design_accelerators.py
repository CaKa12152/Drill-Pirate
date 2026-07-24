from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from drill_writer.core.accelerators import ArrayOptions, ParallelFormOptions
from drill_writer.core.models import ConstructionGuide


class AcceleratorPanel(QWidget):
    array_requested = Signal()
    parallel_requested = Signal()
    rank_file_requested = Signal()
    symmetry_requested = Signal()
    symmetry_manage_requested = Signal()
    alternating_requested = Signal()
    measurements_changed = Signal(bool, str)
    references_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)
        title = QLabel("Design Accelerators")
        title.setStyleSheet("font-size: 14px; font-weight: 750;")
        description = QLabel("Repeat, relate, inspect, and annotate forms without leaving the field workflow.")
        description.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(description)

        categories = QTabWidget()
        categories.setDocumentMode(True)
        categories.setUsesScrollButtons(True)
        root.addWidget(categories)

        patterns = QWidget()
        pattern_layout = QVBoxLayout(patterns)
        pattern_layout.setContentsMargins(4, 8, 4, 4)
        pattern_layout.setSpacing(8)
        pattern_layout.addWidget(
            self.action_group(
                "Arrays",
                "Repeat one master form in a line, grid, radial array, or along a selected guide.",
                "Open Polar / Linear Array…",
                self.array_requested.emit,
            )
        )
        pattern_layout.addWidget(
            self.action_group(
                "Parallel Forms",
                "Generate evenly spaced concentric outlines, ribbons, and offset curves.",
                "Open Parallel Form Generator…",
                self.parallel_requested.emit,
            )
        )
        pattern_layout.addWidget(
            self.action_group(
                "Ranks & Files",
                "Use a selected guide or marcher path as the master and distribute complete parallel ranks.",
                "Open Rank / File Builder…",
                self.rank_file_requested.emit,
            )
        )
        pattern_layout.addStretch()
        categories.addTab(patterns, "Patterns")

        relationships = QWidget()
        relationship_layout = QVBoxLayout(relationships)
        relationship_layout.setContentsMargins(4, 8, 4, 4)
        relationship_layout.setSpacing(8)
        symmetry_group = QGroupBox("Live Symmetry")
        symmetry_layout = QVBoxLayout(symmetry_group)
        symmetry_note = QLabel("Pair selected marchers across an axis. Drag either side and its partner mirrors continuously.")
        symmetry_note.setWordWrap(True)
        create_symmetry = QPushButton("Create Live Symmetry…")
        create_symmetry.setToolTip(symmetry_note.text())
        create_symmetry.clicked.connect(self.symmetry_requested.emit)
        manage_symmetry = QPushButton("Manage Symmetry Links…")
        manage_symmetry.setToolTip("Enable, disable, rename, or remove existing mirrored relationships.")
        manage_symmetry.clicked.connect(self.symmetry_manage_requested.emit)
        symmetry_layout.addWidget(symmetry_note)
        symmetry_layout.addWidget(create_symmetry)
        symmetry_layout.addWidget(manage_symmetry)
        relationship_layout.addWidget(symmetry_group)
        relationship_layout.addWidget(
            self.action_group(
                "Alternating Selection",
                "Select every Nth performer, odd/even ranks, endpoints, corners, or nearest performers.",
                "Open Alternating Selection…",
                self.alternating_requested.emit,
            )
        )
        relationship_layout.addStretch()
        categories.addTab(relationships, "Relationships")

        field_tools = QWidget()
        field_layout = QVBoxLayout(field_tools)
        field_layout.setContentsMargins(4, 8, 4, 4)
        field_layout.setSpacing(8)
        measurement_group = QGroupBox("On-Field Measurements")
        measurement_layout = QFormLayout(measurement_group)
        self.measurement_mode = QComboBox()
        self.measurement_mode.addItem("All Measurements", "all")
        self.measurement_mode.addItem("Intervals", "intervals")
        self.measurement_mode.addItem("Travel & Speed", "travel")
        self.measurement_mode.addItem("Angle & Radius", "geometry")
        self.measurements_enabled = QCheckBox("Show measurements for selected marchers")
        self.measurements_enabled.toggled.connect(self.emit_measurements)
        self.measurement_mode.currentIndexChanged.connect(lambda _index: self.emit_measurements())
        measurement_layout.addRow("Display", self.measurement_mode)
        measurement_layout.addRow(self.measurements_enabled)
        field_layout.addWidget(measurement_group)
        field_layout.addWidget(
            self.action_group(
                "Reference / Annotation Layer",
                "Add text, arrows, staging boxes, high-quality images, teaching notes, and production diagrams.",
                "Open Reference Layer…",
                self.references_requested.emit,
            )
        )
        field_layout.addStretch()
        categories.addTab(field_tools, "Field Notes")

    @staticmethod
    def action_group(title: str, description: str, button_text: str, callback) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        note = QLabel(description)
        note.setWordWrap(True)
        button = QPushButton(button_text)
        button.setToolTip(description)
        button.clicked.connect(callback)
        layout.addWidget(note)
        layout.addWidget(button)
        return group

    def emit_measurements(self, _checked: bool = False) -> None:
        self.measurements_changed.emit(
            self.measurements_enabled.isChecked(),
            str(self.measurement_mode.currentData() or "all"),
        )


class LivePreviewDialog(QDialog):
    settings_changed = Signal()

    def connect_preview(self, *widgets) -> None:
        for widget in widgets:
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(lambda _value: self.settings_changed.emit())
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(lambda _value: self.settings_changed.emit())
            else:
                widget.valueChanged.connect(lambda _value: self.settings_changed.emit())

    def add_buttons(self, root: QVBoxLayout) -> None:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("Apply to Selected Marchers")
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


class ArrayDialog(LivePreviewDialog):
    def __init__(self, selected_count: int, has_path: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Polar / Linear Array")
        self.resize(480, 520)
        root = QVBoxLayout(self)
        note = QLabel(
            f"{selected_count} selected. Marchers are divided into equal copies; targets use global minimum-cost assignment."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        group = QGroupBox("Array Geometry")
        self.form = QFormLayout(group)
        self.mode = QComboBox()
        self.mode.addItem("Linear", "linear")
        self.mode.addItem("Repeated Rows", "rows")
        self.mode.addItem("Polar / Radial", "polar")
        self.mode.addItem("Along Selected Guide", "path")
        if not has_path:
            self.mode.model().item(3).setEnabled(False)
        self.copies = QSpinBox()
        self.copies.setRange(1, max(1, selected_count))
        self.copies.setValue(2 if selected_count % 2 == 0 else 1)
        self.columns = QSpinBox()
        self.columns.setRange(1, 32)
        self.columns.setValue(2)
        self.spacing_x = distance_spin(0.25, 100.0, 12.0)
        self.spacing_y = distance_spin(0.25, 54.0, 8.0)
        self.angle = angle_spin(0.0)
        self.radius = distance_spin(0.0, 60.0, 18.0)
        self.sweep = angle_spin(360.0, -720.0, 720.0)
        self.rotate_copies = QCheckBox("Rotate each repeated form with the array")
        self.rotate_copies.setChecked(True)
        for label, widget in (
            ("Array type", self.mode),
            ("Copies", self.copies),
            ("Grid columns", self.columns),
            ("Copy spacing", self.spacing_x),
            ("Row spacing", self.spacing_y),
            ("Direction / start angle", self.angle),
            ("Polar radius", self.radius),
            ("Polar sweep", self.sweep),
        ):
            self.form.addRow(label, widget)
        self.form.addRow(self.rotate_copies)
        root.addWidget(group)
        preview_note = QLabel("The yellow field preview updates as values change. No marcher moves until Apply.")
        preview_note.setWordWrap(True)
        root.addWidget(preview_note)
        self.add_buttons(root)
        self.connect_preview(
            self.mode,
            self.copies,
            self.columns,
            self.spacing_x,
            self.spacing_y,
            self.angle,
            self.radius,
            self.sweep,
            self.rotate_copies,
        )
        self.mode.currentIndexChanged.connect(self.update_rows)
        self.update_rows()

    def update_rows(self, _index: int = -1) -> None:
        mode = str(self.mode.currentData())
        self.form.setRowVisible(self.columns, mode == "rows")
        self.form.setRowVisible(self.spacing_x, mode in {"linear", "rows"})
        self.form.setRowVisible(self.spacing_y, mode == "rows")
        self.form.setRowVisible(self.angle, mode in {"linear", "polar"})
        self.form.setRowVisible(self.radius, mode == "polar")
        self.form.setRowVisible(self.sweep, mode == "polar")
        self.form.setRowVisible(self.rotate_copies, mode in {"linear", "polar", "path"})
        self.adjustSize()

    def options(self) -> ArrayOptions:
        return ArrayOptions(
            mode=str(self.mode.currentData()),
            copies=self.copies.value(),
            columns=self.columns.value(),
            spacing_x=self.spacing_x.value(),
            spacing_y=self.spacing_y.value(),
            angle_degrees=self.angle.value(),
            radius=self.radius.value(),
            sweep_degrees=self.sweep.value(),
            rotate_copies=self.rotate_copies.isChecked(),
        )


class ParallelFormDialog(LivePreviewDialog):
    def __init__(self, selected_count: int, title: str = "Parallel Form Generator", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(460, 340)
        root = QVBoxLayout(self)
        note = QLabel(
            f"Build parallel paths for {selected_count} selected marchers. Counts are balanced across ranks and assignment minimizes travel."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        group = QGroupBox("Parallel Geometry")
        form = QFormLayout(group)
        self.ranks = QSpinBox()
        self.ranks.setRange(1, max(1, selected_count))
        self.ranks.setValue(2 if selected_count >= 2 else 1)
        self.interval = distance_spin(0.25, 20.0, 2.0)
        self.placement = QComboBox()
        self.placement.addItem("Centered on master", "centered")
        self.placement.addItem("Master then outward", "outward")
        self.placement.addItem("Master then inward", "inward")
        self.closed = QCheckBox("Closed outline / concentric form")
        form.addRow("Ranks / outlines", self.ranks)
        form.addRow("Perpendicular interval", self.interval)
        form.addRow("Placement", self.placement)
        form.addRow(self.closed)
        root.addWidget(group)
        self.add_buttons(root)
        self.connect_preview(self.ranks, self.interval, self.placement, self.closed)

    def options(self) -> ParallelFormOptions:
        return ParallelFormOptions(
            ranks=self.ranks.value(),
            interval=self.interval.value(),
            placement=str(self.placement.currentData()),
            closed=self.closed.isChecked(),
        )


class RankFileDialog(ParallelFormDialog):
    def __init__(self, selected_count: int, has_guide: bool, parent=None) -> None:
        super().__init__(selected_count, "Rank / File Builder", parent)
        source_group = QGroupBox("Master Path")
        form = QFormLayout(source_group)
        self.source = QComboBox()
        self.source.addItem("Selected marcher path", "selection")
        self.source.addItem("Selected construction guide", "guide")
        if not has_guide:
            self.source.model().item(1).setEnabled(False)
        form.addRow("Source", self.source)
        self.layout().insertWidget(1, source_group)
        self.connect_preview(self.source)


class LiveSymmetryDialog(QDialog):
    def __init__(self, center: tuple[float, float], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Live Symmetry")
        self.resize(440, 320)
        root = QVBoxLayout(self)
        note = QLabel("Marchers are globally paired with their closest reflected partner. Center-line performers remain constrained to the axis.")
        note.setWordWrap(True)
        root.addWidget(note)
        group = QGroupBox("Symmetry Axis")
        form = QFormLayout(group)
        self.name = QLineEdit("Live Symmetry")
        self.preset = QComboBox()
        self.preset.addItem("Vertical axis", 90.0)
        self.preset.addItem("Horizontal axis", 0.0)
        self.preset.addItem("Custom angle", None)
        self.axis_x = coordinate_spin(center[0])
        self.axis_y = coordinate_spin(center[1])
        self.angle = angle_spin(90.0)
        self.preset.currentIndexChanged.connect(self.apply_preset)
        form.addRow("Name", self.name)
        form.addRow("Axis preset", self.preset)
        form.addRow("Axis X", self.axis_x)
        form.addRow("Axis Y", self.axis_y)
        form.addRow("Axis angle", self.angle)
        root.addWidget(group)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def apply_preset(self, _index: int = -1) -> None:
        value = self.preset.currentData()
        if value is not None:
            self.angle.setValue(float(value))
        self.angle.setEnabled(value is None)


class AlternatingSelectionDialog(QDialog):
    def __init__(self, current_count: int, total_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Alternating Selection")
        self.resize(450, 360)
        root = QVBoxLayout(self)
        group = QGroupBox("Selection Rule")
        form = QFormLayout(group)
        self.scope = QComboBox()
        self.scope.addItem(f"Current selection ({current_count})", "selection")
        self.scope.addItem(f"All visible marchers ({total_count})", "all")
        self.mode = QComboBox()
        self.mode.addItem("Every Nth marcher", "every")
        self.mode.addItem("Odd ranks", "odd_ranks")
        self.mode.addItem("Even ranks", "even_ranks")
        self.mode.addItem("Endpoints", "endpoints")
        self.mode.addItem("Corners", "corners")
        self.mode.addItem("Nearest performers", "nearest")
        self.every = QSpinBox()
        self.every.setRange(2, 32)
        self.every.setValue(2)
        self.count = QSpinBox()
        self.count.setRange(1, max(1, total_count))
        self.count.setValue(min(4, max(1, total_count)))
        self.additive = QCheckBox("Add results to current selection")
        form.addRow("Search", self.scope)
        form.addRow("Rule", self.mode)
        form.addRow("Every", self.every)
        form.addRow("Result count", self.count)
        form.addRow(self.additive)
        root.addWidget(group)
        hint = QLabel("Nearest uses a single selected marcher as the anchor, or the center of the current selection.")
        hint.setWordWrap(True)
        root.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.mode.currentIndexChanged.connect(self.update_rows)
        self.update_rows()

    def update_rows(self, _index: int = -1) -> None:
        mode = str(self.mode.currentData())
        form = self.every.parentWidget().layout()
        if isinstance(form, QFormLayout):
            form.setRowVisible(self.every, mode == "every")
            form.setRowVisible(self.count, mode in {"corners", "nearest"})


class SymmetryManagerDialog(QDialog):
    def __init__(self, records: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Live Symmetry Links")
        self.resize(540, 400)
        self.records = deepcopy(records)
        root = QVBoxLayout(self)
        self.list = QListWidget()
        root.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.enabled = QCheckBox("Enabled")
        self.enabled.toggled.connect(self.update_current)
        delete_button = QPushButton("Delete Link")
        delete_button.clicked.connect(self.delete_current)
        row.addWidget(self.enabled)
        row.addStretch()
        row.addWidget(delete_button)
        root.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.list.currentRowChanged.connect(self.load_current)
        self.refresh()

    def refresh(self) -> None:
        row = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        for record in self.records:
            pairs = len(record.get("pairs", []))
            state = "active" if record.get("enabled", True) else "disabled"
            self.list.addItem(f"{record.get('name', 'Live Symmetry')}  ·  {pairs} pair(s)  ·  {state}")
        self.list.blockSignals(False)
        if self.records:
            self.list.setCurrentRow(max(0, min(row, len(self.records) - 1)))

    def load_current(self, row: int) -> None:
        self.enabled.blockSignals(True)
        self.enabled.setChecked(bool(0 <= row < len(self.records) and self.records[row].get("enabled", True)))
        self.enabled.blockSignals(False)

    def update_current(self, enabled: bool) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self.records):
            self.records[row]["enabled"] = bool(enabled)
            self.refresh()

    def delete_current(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self.records):
            self.records.pop(row)
            self.refresh()


class ReferenceAnnotationsDialog(QDialog):
    TYPES = (
        ("Text Label", "annotation_text"),
        ("Arrow", "annotation_arrow"),
        ("Staging Box", "annotation_box"),
        ("Picture / Diagram", "annotation_image"),
        ("Teaching Note", "annotation_note"),
    )

    def __init__(self, guides: list[ConstructionGuide], center: tuple[float, float], set_index: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reference / Annotation Layer")
        self.resize(880, 600)
        self.center = center
        self.set_index = set_index
        self.annotations = deepcopy([guide for guide in guides if guide.guide_type.startswith("annotation_")])
        self.active_id = ""
        self.color = "#7c3aed"
        self.fill_color = "#ede9fe"
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel("Non-performer reference objects"))
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.load_selected)
        left.addWidget(self.list, 1)
        add_row = QHBoxLayout()
        self.add_type = QComboBox()
        for label, value in self.TYPES:
            self.add_type.addItem(label, value)
        add_button = QPushButton("Add")
        add_button.clicked.connect(self.add_annotation)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.delete_annotation)
        add_row.addWidget(self.add_type, 1)
        add_row.addWidget(add_button)
        add_row.addWidget(delete_button)
        left.addLayout(add_row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        left.addWidget(buttons)
        root.addLayout(left, 1)

        editor = QGroupBox("Reference Properties")
        form = QFormLayout(editor)
        self.name = QLineEdit()
        self.type = QComboBox()
        for label, value in self.TYPES:
            self.type.addItem(label, value)
        self.text = QPlainTextEdit()
        self.text.setMaximumHeight(110)
        self.image_file = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse_image)
        self.image_row = QWidget()
        image_layout = QHBoxLayout(self.image_row)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.addWidget(self.image_file, 1)
        image_layout.addWidget(browse)
        self.coordinates = [coordinate_spin(0.0) for _ in range(4)]
        coordinate_grid = QGridLayout()
        coordinate_grid.setContentsMargins(0, 0, 0, 0)
        coordinate_grid.setHorizontalSpacing(8)
        coordinate_grid.setVerticalSpacing(6)
        for index, (label, spin) in enumerate(zip(("X1", "Y1", "X2", "Y2"), self.coordinates)):
            spin.setMaximumWidth(150)
            row, column = divmod(index, 2)
            coordinate_grid.addWidget(QLabel(label), row, column * 2)
            coordinate_grid.addWidget(spin, row, column * 2 + 1)
        coordinate_row = QWidget()
        coordinate_row.setLayout(coordinate_grid)
        self.scope = QComboBox()
        self.scope.addItem("All sets", -1)
        self.scope.addItem(f"Current set ({set_index + 1})", set_index)
        self.opacity = QSpinBox()
        self.opacity.setRange(10, 100)
        self.opacity.setValue(85)
        self.opacity.setSuffix("%")
        self.visible = QCheckBox("Visible")
        self.visible.setChecked(True)
        self.locked = QCheckBox("Locked")
        self.color_button = QPushButton()
        self.color_button.clicked.connect(lambda: self.choose_color(False))
        self.fill_button = QPushButton()
        self.fill_button.clicked.connect(lambda: self.choose_color(True))
        apply_button = QPushButton("Apply Reference Changes")
        apply_button.clicked.connect(self.update_annotation)
        hint = QLabel("Unlocked references drag directly on the field and never become performers. Double-click one to edit it.")
        hint.setWordWrap(True)
        form.addRow("Name", self.name)
        form.addRow("Type", self.type)
        form.addRow("Text / note", self.text)
        form.addRow("Picture", self.image_row)
        form.addRow("Bounds / endpoints", coordinate_row)
        form.addRow("Show on", self.scope)
        form.addRow("Line / text color", self.color_button)
        form.addRow("Fill color", self.fill_button)
        form.addRow("Opacity", self.opacity)
        form.addRow("Display", self.visible)
        form.addRow("Editing", self.locked)
        form.addRow(apply_button)
        form.addRow(hint)
        root.addWidget(editor, 2)
        self.type.currentIndexChanged.connect(self.update_type_rows)
        self.update_color_buttons()
        self.refresh_list()

    def refresh_list(self) -> None:
        selected_id = self.active_id
        self.list.clear()
        for annotation in self.annotations:
            label = annotation.name
            if not annotation.visible:
                label += " (hidden)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, annotation.id)
            self.list.addItem(item)
            if annotation.id == selected_id:
                self.list.setCurrentItem(item)

    def add_annotation(self) -> None:
        annotation_type = str(self.add_type.currentData())
        center_x, center_y = self.center
        if annotation_type in {"annotation_box", "annotation_image"}:
            points = [(center_x - 6, center_y - 3), (center_x + 6, center_y + 3)]
        elif annotation_type == "annotation_arrow":
            points = [(center_x - 5, center_y), (center_x + 5, center_y)]
        else:
            points = [(center_x, center_y), (center_x + 0.5, center_y)]
        annotation = ConstructionGuide(
            id=f"annotation-{uuid4().hex[:10]}",
            name=self.add_type.currentText(),
            guide_type=annotation_type,
            points=points,
            color=self.color,
            metadata={
                "category": "reference",
                "text": self.add_type.currentText(),
                "fill_color": self.fill_color,
                "opacity": 0.85,
                "set_index": -1,
                "image_file": "",
            },
        )
        self.annotations.append(annotation)
        self.active_id = annotation.id
        self.refresh_list()

    def load_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        annotation_id = str(current.data(Qt.ItemDataRole.UserRole))
        annotation = next((item for item in self.annotations if item.id == annotation_id), None)
        if annotation is None:
            return
        self.active_id = annotation.id
        self.name.setText(annotation.name)
        self.type.setCurrentIndex(max(0, self.type.findData(annotation.guide_type)))
        values = [coordinate for point in annotation.points[:2] for coordinate in point]
        for index, spin in enumerate(self.coordinates):
            spin.setValue(values[index] if index < len(values) else 0.0)
        self.text.setPlainText(str(annotation.metadata.get("text", "")))
        self.image_file.setText(str(annotation.metadata.get("image_file", "")))
        scope_index = self.scope.findData(int(annotation.metadata.get("set_index", -1)))
        self.scope.setCurrentIndex(max(0, scope_index))
        self.opacity.setValue(round(float(annotation.metadata.get("opacity", 0.85)) * 100))
        self.visible.setChecked(annotation.visible)
        self.locked.setChecked(annotation.locked)
        self.color = annotation.color
        self.fill_color = str(annotation.metadata.get("fill_color", "#ede9fe"))
        self.update_color_buttons()
        self.update_type_rows()

    def update_annotation(self) -> None:
        annotation = next((item for item in self.annotations if item.id == self.active_id), None)
        if annotation is None:
            return
        values = [spin.value() for spin in self.coordinates]
        annotation.name = self.name.text().strip() or "Reference"
        annotation.guide_type = str(self.type.currentData())
        annotation.points = [(values[0], values[1]), (values[2], values[3])]
        annotation.color = self.color
        annotation.visible = self.visible.isChecked()
        annotation.locked = self.locked.isChecked()
        annotation.metadata.update(
            {
                "category": "reference",
                "text": self.text.toPlainText().strip(),
                "image_file": self.image_file.text().strip(),
                "fill_color": self.fill_color,
                "opacity": self.opacity.value() / 100.0,
                "set_index": int(self.scope.currentData()),
            }
        )
        self.refresh_list()

    def delete_annotation(self) -> None:
        if not self.active_id:
            return
        self.annotations = [item for item in self.annotations if item.id != self.active_id]
        self.active_id = ""
        self.refresh_list()

    def browse_image(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose Reference Picture",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff);;All Files (*)",
        )
        if path:
            self.image_file.setText(path)

    def choose_color(self, fill: bool) -> None:
        current = self.fill_color if fill else self.color
        selected = QColorDialog.getColor(QColor(current), self, "Reference Color")
        if selected.isValid():
            if fill:
                self.fill_color = selected.name()
            else:
                self.color = selected.name()
            self.update_color_buttons()

    def update_color_buttons(self) -> None:
        self.color_button.setText(self.color)
        self.color_button.setStyleSheet(f"border-left: 18px solid {self.color};")
        self.fill_button.setText(self.fill_color)
        self.fill_button.setStyleSheet(f"border-left: 18px solid {self.fill_color};")

    def update_type_rows(self, _index: int = -1) -> None:
        annotation_type = str(self.type.currentData())
        form = self.type.parentWidget().layout()
        if not isinstance(form, QFormLayout):
            return
        form.setRowVisible(self.image_row, annotation_type == "annotation_image")

    def accept(self) -> None:  # type: ignore[override]
        if self.active_id:
            self.update_annotation()
        super().accept()


def distance_spin(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(2)
    spin.setSingleStep(0.5)
    spin.setValue(value)
    spin.setSuffix(" yd")
    return spin


def coordinate_spin(value: float) -> QDoubleSpinBox:
    return distance_spin(-120.0, 120.0, value)


def angle_spin(value: float, minimum: float = -360.0, maximum: float = 360.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(1)
    spin.setSingleStep(5.0)
    spin.setValue(value)
    spin.setSuffix("°")
    return spin
