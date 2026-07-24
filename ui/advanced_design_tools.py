from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from drill_writer.core.design_tools import guide_measurement_label
from drill_writer.core.models import ConstructionGuide, ContinuityInstruction, MotionRibbon


class MotionRibbonDialog(QDialog):
    def __init__(self, selected_count: int, ribbon: MotionRibbon | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Group Motion Ribbon")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        note = QLabel(
            f"Build one editable curved route for {selected_count} selected marchers. "
            "The ribbon preserves their shared spacing while every marcher receives a synchronized path."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.name = QLineEdit(ribbon.name if ribbon else "Group Motion Ribbon")
        self.bend = QDoubleSpinBox()
        self.bend.setRange(-80.0, 80.0)
        self.bend.setSuffix(" yd")
        self.bend.setValue(0.0)
        self.orient_to_path = QCheckBox("Rotate the group around curves")
        self.orient_to_path.setChecked(ribbon.orient_to_path if ribbon else True)
        self.face_direction = QCheckBox("Face direction of travel")
        self.face_direction.setChecked(ribbon.face_direction if ribbon else False)
        self.precision = QSpinBox()
        self.precision.setRange(1, 16)
        self.precision.setValue(ribbon.samples_per_count if ribbon else 4)
        self.precision.setSuffix(" samples/count")
        form.addRow("Name", self.name)
        if ribbon is None:
            form.addRow("Initial bend", self.bend)
        form.addRow("Group behavior", self.orient_to_path)
        form.addRow("Facing", self.face_direction)
        form.addRow("Playback precision", self.precision)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class FormationMorphDialog(QDialog):
    def __init__(self, selected_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Formation Morph")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        note = QLabel(
            f"Blend {selected_count} selected marchers into this set's destination while preserving "
            "neighboring relationships, section cohesion, and exact start/end pictures."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.assignment = QComboBox()
        self.assignment.addItem("Keep current dot ownership", "keep")
        self.assignment.addItem("Shortest total travel", "shortest")
        self.assignment.addItem("Section-aware / preserve neighbors", "section")
        self.assignment.addItem("Lowest collision risk", "collision")
        self.coherence = QSpinBox()
        self.coherence.setRange(0, 100)
        self.coherence.setValue(85)
        self.coherence.setSuffix(" %")
        self.section_strength = QSpinBox()
        self.section_strength.setRange(0, 100)
        self.section_strength.setValue(70)
        self.section_strength.setSuffix(" %")
        self.precision = QSpinBox()
        self.precision.setRange(1, 16)
        self.precision.setValue(4)
        self.precision.setSuffix(" samples/count")
        self.face_direction = QCheckBox("Face direction of travel")
        form.addRow("Destination assignment", self.assignment)
        form.addRow("Formation coherence", self.coherence)
        form.addRow("Section relationship", self.section_strength)
        form.addRow("Playback precision", self.precision)
        form.addRow("Facing", self.face_direction)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ContinuityDesignerDialog(QDialog):
    DIRECTIONS = (
        ("Forward march", "forward"),
        ("Backward march", "backward"),
        ("Slide left", "slide_left"),
        ("Slide right", "slide_right"),
        ("Crab left", "crab_left"),
        ("Crab right", "crab_right"),
        ("Mark time", "mark_time"),
        ("Halt", "halt"),
        ("Visual", "visual"),
    )

    def __init__(
        self,
        instructions: list[ContinuityInstruction],
        selected_dot_ids: list[str],
        start_count: float,
        end_count: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Continuity Designer")
        self.resize(860, 590)
        self.instructions = deepcopy(instructions)
        self.selected_dot_ids = list(selected_dot_ids)
        self.active_id = ""
        self._loading_editor = False
        self._editor_dirty = False
        root = QVBoxLayout(self)
        note = QLabel(
            "Write performer-facing continuity by count range. Select marchers on the field first, "
            "then add instructions for step size, travel technique, body/horn direction, and notes."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Counts", "Marchers", "Step", "Direction", "Facings", "Instructions"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.load_selected_row)
        root.addWidget(self.table, 1)

        editor = QGroupBox("Instruction")
        grid = QGridLayout(editor)
        self.start_count = self.count_spin(start_count, end_count, start_count)
        self.end_count = self.count_spin(start_count, end_count, end_count)
        self.step_size = QComboBox()
        self.step_size.addItems(["8-to-5", "6-to-5", "12-to-5", "16-to-5", "Custom"])
        self.direction = QComboBox()
        for label, value in self.DIRECTIONS:
            self.direction.addItem(label, value)
        self.body_enabled = QCheckBox("Body")
        self.body_facing = self.angle_spin()
        self.horn_enabled = QCheckBox("Horn")
        self.horn_facing = self.angle_spin()
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Written instructions shown in performer exports")
        selected_label = QLabel(f"Applies to current selection: {len(selected_dot_ids)} marcher(s)")
        selected_label.setWordWrap(True)
        grid.addWidget(QLabel("Start count"), 0, 0)
        grid.addWidget(self.start_count, 0, 1)
        grid.addWidget(QLabel("End count"), 0, 2)
        grid.addWidget(self.end_count, 0, 3)
        grid.addWidget(QLabel("Step size"), 1, 0)
        grid.addWidget(self.step_size, 1, 1)
        grid.addWidget(QLabel("Direction"), 1, 2)
        grid.addWidget(self.direction, 1, 3)
        grid.addWidget(self.body_enabled, 2, 0)
        grid.addWidget(self.body_facing, 2, 1)
        grid.addWidget(self.horn_enabled, 2, 2)
        grid.addWidget(self.horn_facing, 2, 3)
        grid.addWidget(QLabel("Instructions"), 3, 0)
        grid.addWidget(self.notes, 3, 1, 1, 3)
        grid.addWidget(selected_label, 4, 0, 1, 4)
        root.addWidget(editor)
        for widget in (self.start_count, self.end_count, self.body_facing, self.horn_facing):
            widget.valueChanged.connect(self.mark_dirty)
        for widget in (self.step_size, self.direction):
            widget.currentIndexChanged.connect(self.mark_dirty)
        for widget in (self.body_enabled, self.horn_enabled):
            widget.toggled.connect(self.mark_dirty)
        self.notes.textChanged.connect(self.mark_dirty)
        actions = QHBoxLayout()
        add_button = QPushButton("Add From Current Selection")
        add_button.clicked.connect(self.add_or_update)
        clear_button = QPushButton("New Instruction")
        clear_button.clicked.connect(self.clear_editor)
        delete_button = QPushButton("Delete Instruction")
        delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(add_button)
        actions.addWidget(clear_button)
        actions.addWidget(delete_button)
        actions.addStretch()
        root.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.refresh_table()

    @staticmethod
    def count_spin(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(2)
        spin.setValue(value)
        return spin

    @staticmethod
    def angle_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 359.99)
        spin.setDecimals(1)
        spin.setSuffix("°")
        return spin

    def refresh_table(self) -> None:
        self.table.setRowCount(len(self.instructions))
        for row, instruction in enumerate(self.instructions):
            values = (
                f"{instruction.start_count:g}-{instruction.end_count:g}",
                str(len(instruction.dot_ids)),
                instruction.step_size,
                instruction.direction.replace("_", " ").title(),
                self.facing_label(instruction),
                instruction.text,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, instruction.id)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    @staticmethod
    def facing_label(instruction: ContinuityInstruction) -> str:
        values = []
        if instruction.body_facing is not None:
            values.append(f"Body {instruction.body_facing:g}°")
        if instruction.horn_facing is not None:
            values.append(f"Horn {instruction.horn_facing:g}°")
        return ", ".join(values) or "—"

    def load_selected_row(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        instruction_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        instruction = next((item for item in self.instructions if item.id == instruction_id), None)
        if instruction is None:
            return
        self._loading_editor = True
        self.active_id = instruction.id
        self.start_count.setValue(instruction.start_count)
        self.end_count.setValue(instruction.end_count)
        self.step_size.setCurrentText(instruction.step_size)
        direction_index = self.direction.findData(instruction.direction)
        self.direction.setCurrentIndex(max(0, direction_index))
        self.body_enabled.setChecked(instruction.body_facing is not None)
        self.body_facing.setValue(instruction.body_facing or 0.0)
        self.horn_enabled.setChecked(instruction.horn_facing is not None)
        self.horn_facing.setValue(instruction.horn_facing or 0.0)
        self.notes.setText(instruction.text)
        self._loading_editor = False
        self._editor_dirty = False

    def clear_editor(self) -> None:
        self.active_id = ""
        self.table.clearSelection()
        self.notes.clear()
        self._editor_dirty = False

    def mark_dirty(self, *_args) -> None:
        if not self._loading_editor:
            self._editor_dirty = True

    def add_or_update(self) -> None:
        if not self.selected_dot_ids and not self.active_id:
            return
        existing = next((item for item in self.instructions if item.id == self.active_id), None)
        dot_ids = list(self.selected_dot_ids) if self.selected_dot_ids else list(existing.dot_ids if existing else [])
        instruction = ContinuityInstruction(
            id=self.active_id or f"continuity-{uuid4().hex[:10]}",
            dot_ids=dot_ids,
            start_count=min(self.start_count.value(), self.end_count.value()),
            end_count=max(self.start_count.value(), self.end_count.value()),
            step_size=self.step_size.currentText(),
            direction=str(self.direction.currentData()),
            body_facing=self.body_facing.value() if self.body_enabled.isChecked() else None,
            horn_facing=self.horn_facing.value() if self.horn_enabled.isChecked() else None,
            text=self.notes.text().strip(),
        )
        if existing is None:
            self.instructions.append(instruction)
        else:
            self.instructions[self.instructions.index(existing)] = instruction
        self.active_id = instruction.id
        self._editor_dirty = False
        self.refresh_table()

    def delete_selected(self) -> None:
        if not self.active_id:
            return
        self.instructions = [item for item in self.instructions if item.id != self.active_id]
        self.clear_editor()
        self.refresh_table()

    def accept(self) -> None:  # type: ignore[override]
        if self._editor_dirty and (self.selected_dot_ids or self.active_id):
            self.add_or_update()
        super().accept()


class ConstructionGuidesDialog(QDialog):
    GUIDE_TYPES = (
        ("Line", "line"),
        ("Circle", "circle"),
        ("Arc", "arc"),
        ("Center cross", "center"),
        ("Diagonal", "diagonal"),
        ("Grid", "grid"),
        ("Ruler", "ruler"),
        ("No-go rectangle", "no_go_rectangle"),
        ("No-go circle", "no_go_circle"),
    )

    def __init__(self, guides: list[ConstructionGuide], center: tuple[float, float], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Construction Guides")
        self.resize(760, 520)
        self.guides = deepcopy(guides)
        self.center = center
        self.active_id = ""
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.load_selected)
        left.addWidget(QLabel("Permanent project guides"))
        left.addWidget(self.list, 1)
        add_row = QHBoxLayout()
        self.add_type = QComboBox()
        for label, value in self.GUIDE_TYPES:
            self.add_type.addItem(label, value)
        add_button = QPushButton("Add")
        add_button.clicked.connect(self.add_guide)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.delete_guide)
        add_row.addWidget(self.add_type, 1)
        add_row.addWidget(add_button)
        add_row.addWidget(delete_button)
        left.addLayout(add_row)
        root.addLayout(left, 1)

        editor = QGroupBox("Exact Guide Geometry")
        form = QFormLayout(editor)
        self.name = QLineEdit()
        self.type = QComboBox()
        for label, value in self.GUIDE_TYPES:
            self.type.addItem(label, value)
        self.coordinates = [self.coordinate_spin() for _ in range(6)]
        point_grid = QGridLayout()
        labels = ("X1", "Y1", "X2", "Y2", "X3", "Y3")
        for index, (label, spin) in enumerate(zip(labels, self.coordinates)):
            point_grid.addWidget(QLabel(label), index // 2, (index % 2) * 2)
            point_grid.addWidget(spin, index // 2, (index % 2) * 2 + 1)
        self.spacing = QDoubleSpinBox()
        self.spacing.setRange(0.25, 20.0)
        self.spacing.setValue(1.0)
        self.spacing.setSuffix(" yd")
        self.visible = QCheckBox("Visible")
        self.visible.setChecked(True)
        self.locked = QCheckBox("Locked")
        self.color = "#a855f7"
        self.color_button = QPushButton("Choose…")
        self.color_button.clicked.connect(self.choose_color)
        update_button = QPushButton("Apply Guide Changes")
        update_button.clicked.connect(self.update_guide)
        hint = QLabel("Unlocked guides can be dragged directly on the field. No-go guides also appear in conflict analysis.")
        hint.setWordWrap(True)
        form.addRow("Name", self.name)
        form.addRow("Type", self.type)
        form.addRow("Points", point_grid)
        form.addRow("Grid spacing", self.spacing)
        form.addRow("Display", self.visible)
        form.addRow("Safety", self.locked)
        form.addRow("Color", self.color_button)
        form.addRow(update_button)
        form.addRow(hint)
        root.addWidget(editor, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        left.addWidget(buttons)
        self.refresh_list()

    @staticmethod
    def coordinate_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-120.0, 120.0)
        spin.setDecimals(2)
        spin.setSuffix(" yd")
        return spin

    def refresh_list(self) -> None:
        selected_id = self.active_id
        self.list.clear()
        for guide in self.guides:
            item = QListWidgetItem(guide_measurement_label(guide))
            item.setData(Qt.ItemDataRole.UserRole, guide.id)
            if not guide.visible:
                item.setText(f"{item.text()} (hidden)")
            self.list.addItem(item)
            if guide.id == selected_id:
                self.list.setCurrentItem(item)

    def add_guide(self) -> None:
        guide_type = str(self.add_type.currentData())
        center_x, center_y = self.center
        points = self.default_points(guide_type, center_x, center_y)
        guide = ConstructionGuide(
            id=f"guide-{uuid4().hex[:10]}",
            name=self.add_type.currentText(),
            guide_type=guide_type,
            points=points,
            metadata={"spacing": 1.0},
        )
        self.guides.append(guide)
        self.active_id = guide.id
        self.refresh_list()

    @staticmethod
    def default_points(guide_type: str, x: float, y: float) -> list[tuple[float, float]]:
        if guide_type == "arc":
            return [(x, y), (x + 8.0, y), (x, y + 8.0)]
        if guide_type == "center":
            return [(x, y)]
        if guide_type in {"circle", "no_go_circle"}:
            return [(x, y), (x + 6.0, y)]
        if guide_type in {"grid", "no_go_rectangle"}:
            return [(x - 8.0, y - 5.0), (x + 8.0, y + 5.0)]
        return [(x - 8.0, y), (x + 8.0, y)]

    def load_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        guide_id = str(current.data(Qt.ItemDataRole.UserRole))
        guide = next((item for item in self.guides if item.id == guide_id), None)
        if guide is None:
            return
        self.active_id = guide.id
        self.name.setText(guide.name)
        index = self.type.findData(guide.guide_type)
        self.type.setCurrentIndex(max(0, index))
        values = [coordinate for point in guide.points[:3] for coordinate in point]
        for coordinate_index, spin in enumerate(self.coordinates):
            spin.setValue(values[coordinate_index] if coordinate_index < len(values) else 0.0)
        self.spacing.setValue(float(guide.metadata.get("spacing", 1.0)))
        self.visible.setChecked(guide.visible)
        self.locked.setChecked(guide.locked)
        self.color = guide.color
        self.update_color_button()

    def update_guide(self) -> None:
        guide = next((item for item in self.guides if item.id == self.active_id), None)
        if guide is None:
            return
        guide.name = self.name.text().strip() or "Guide"
        guide.guide_type = str(self.type.currentData())
        point_count = 3 if guide.guide_type == "arc" else 1 if guide.guide_type == "center" else 2
        values = [spin.value() for spin in self.coordinates]
        guide.points = [(values[index * 2], values[index * 2 + 1]) for index in range(point_count)]
        guide.visible = self.visible.isChecked()
        guide.locked = self.locked.isChecked()
        guide.color = self.color
        guide.metadata["spacing"] = self.spacing.value()
        self.refresh_list()

    def delete_guide(self) -> None:
        if not self.active_id:
            return
        self.guides = [guide for guide in self.guides if guide.id != self.active_id]
        self.active_id = ""
        self.refresh_list()

    def choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.color), self, "Guide Color")
        if color.isValid():
            self.color = color.name()
            self.update_color_button()

    def update_color_button(self) -> None:
        self.color_button.setText(self.color)
        self.color_button.setStyleSheet(f"border-left: 18px solid {self.color};")

    def accept(self) -> None:  # type: ignore[override]
        if self.active_id:
            self.update_guide()
        super().accept()


class CadPathDialog(QDialog):
    OPERATIONS = (
        ("Join selected guides", "join"),
        ("Split at percentage", "split"),
        ("Trim start/end", "trim"),
        ("Extend endpoints", "extend"),
        ("Offset / parallel", "offset"),
        ("Simplify", "simplify"),
        ("Smooth", "smooth"),
        ("Reverse", "reverse"),
        ("Fillet corners", "fillet"),
    )

    def __init__(self, target_description: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("CAD Path Toolkit")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        target = QLabel(f"Target: {target_description}")
        target.setWordWrap(True)
        layout.addWidget(target)
        form = QFormLayout()
        self.operation = QComboBox()
        for label, value in self.OPERATIONS:
            self.operation.addItem(label, value)
        self.value_a = QDoubleSpinBox()
        self.value_a.setRange(-100.0, 100.0)
        self.value_a.setDecimals(3)
        self.value_a.setValue(0.5)
        self.value_b = QDoubleSpinBox()
        self.value_b.setRange(-100.0, 100.0)
        self.value_b.setDecimals(3)
        self.value_b.setValue(1.0)
        self.iterations = QSpinBox()
        self.iterations.setRange(1, 8)
        self.iterations.setValue(2)
        self.value_a_label = QLabel("Primary value")
        self.value_b_label = QLabel("Secondary value")
        self.iterations_label = QLabel("Iterations / samples")
        form.addRow("Operation", self.operation)
        form.addRow(self.value_a_label, self.value_a)
        form.addRow(self.value_b_label, self.value_b)
        form.addRow(self.iterations_label, self.iterations)
        layout.addLayout(form)
        hint = QLabel(
            "Values are context-sensitive: percentages use 0–1, distances use yards, "
            "and simplify/fillet use yard tolerances. Ribbon edits regenerate every marcher lane."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.operation.currentIndexChanged.connect(self.configure_operation)
        self.configure_operation()

    def configure_operation(self) -> None:
        operation = str(self.operation.currentData())
        settings = {
            "join": ("Join tolerance", "", 0.5, 0.0, False, False),
            "split": ("Split position", "", 0.5, 0.0, True, False),
            "trim": ("Start position", "End position", 0.0, 1.0, True, True),
            "extend": ("Extend start", "Extend end", 1.0, 1.0, True, True),
            "offset": ("Parallel offset", "", 1.0, 0.0, True, False),
            "simplify": ("Tolerance", "", 0.25, 0.0, True, False),
            "smooth": ("", "", 0.0, 0.0, False, False),
            "reverse": ("", "", 0.0, 0.0, False, False),
            "fillet": ("Corner radius", "", 1.0, 0.0, True, False),
        }
        label_a, label_b, value_a, value_b, enabled_a, enabled_b = settings.get(
            operation, ("Primary value", "Secondary value", 0.5, 1.0, True, True)
        )
        self.value_a_label.setText(label_a or "Primary value")
        self.value_b_label.setText(label_b or "Secondary value")
        self.value_a.setEnabled(enabled_a)
        self.value_b.setEnabled(enabled_b)
        self.value_a_label.setVisible(enabled_a)
        self.value_a.setVisible(enabled_a)
        self.value_b_label.setVisible(enabled_b)
        self.value_b.setVisible(enabled_b)
        self.iterations_label.setVisible(operation in {"smooth", "fillet"})
        self.iterations.setVisible(operation in {"smooth", "fillet"})
        self.value_a.setSuffix("" if operation in {"split", "trim"} else " yd")
        self.value_b.setSuffix("" if operation == "trim" else " yd")
        self.value_a.setValue(value_a)
        self.value_b.setValue(value_b)
