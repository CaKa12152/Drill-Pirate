from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from drill_writer.core.models import (
    ChoreographyEvent,
    DrillProject,
    PerformerPhysicalLimits,
    PropAttachment,
)
from drill_writer.core.specialized_design import (
    analyze_specialized_safety,
    normalized_surface,
    physical_limits_for_dot,
    set_physical_limits,
    surface_preset,
    surface_presets,
    validate_choreography,
)


class SpecializedDesignPanel(QWidget):
    studio_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: DrillProject | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)
        title = QLabel("Specialized Design")
        title.setStyleSheet("font-size: 14px; font-weight: 750;")
        description = QLabel(
            "Configure the performance surface, guard choreography, performer-linked props, and instrument-aware safety limits."
        )
        description.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(description)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName("ToolHintLabel")
        layout.addWidget(self.summary)
        buttons = QGridLayout()
        for index, (label, page, tip) in enumerate(
            (
                ("Surface & Route", "surface", "Edit field, floor, staging, or parade-route dimensions."),
                ("Guard Tracks", "choreography", "Create toss, equipment-change, and choreography count ranges."),
                ("Prop Attachments", "props", "Link props to performers for carrying, pushing, and rotation."),
                ("Physical Limits", "safety", "Set performer limits and analyze instrument-aware movement risk."),
            )
        ):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, value=page: self.studio_requested.emit(value))
            buttons.addWidget(button, index // 2, index % 2)
        layout.addLayout(buttons)
        open_button = QPushButton("Open Specialized Design Studio…")
        open_button.clicked.connect(lambda: self.studio_requested.emit("surface"))
        layout.addWidget(open_button)
        layout.addStretch()

    def set_project(self, project: DrillProject) -> None:
        self.project = project
        surface = project.surface
        self.summary.setText(
            f"{surface.name} · {surface.width_yards:g} × {surface.height_yards:g} yd\n"
            f"{len(project.choreography)} choreography event(s) · "
            f"{len(project.prop_attachments)} prop link(s) · "
            f"{len(project.physical_limits)} performer override(s)"
        )


class ChoreographyTimelineWidget(QWidget):
    event_selected = Signal(str)

    EVENT_COLORS = {
        "toss": "#f59e0b",
        "equipment_change": "#ef4444",
        "spin": "#8b5cf6",
        "dance": "#ec4899",
        "choreography": "#06b6d4",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: DrillProject | None = None
        self.current_count = 1.0
        self.setMinimumHeight(110)
        self.setMouseTracking(True)

    def set_project(self, project: DrillProject | None) -> None:
        self.project = project
        self.setMinimumWidth(max(520, 120 + 110 * len(project.choreography))) if project else None
        self.update()

    def set_current_count(self, count: float) -> None:
        self.current_count = float(count)
        self.update()

    def count_bounds(self) -> tuple[float, float]:
        if not self.project or not self.project.sets:
            return 1.0, 16.0
        return float(self.project.sets[0].start_count), float(self.project.sets[-1].end_count)

    def event_rects(self) -> list[tuple[QRectF, ChoreographyEvent]]:
        if not self.project:
            return []
        start, end = self.count_bounds()
        span = max(1.0, end - start + 1.0)
        content = QRectF(116, 24, max(1, self.width() - 126), max(1, self.height() - 34))
        result: list[tuple[QRectF, ChoreographyEvent]] = []
        for lane, event in enumerate(self.project.choreography):
            y = content.top() + lane * 27
            x = content.left() + (event.start_count - start) / span * content.width()
            width = max(8.0, (event.end_count - event.start_count + 1.0) / span * content.width())
            result.append((QRectF(x, y, width, 21), event))
        return result

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#151922"))
        painter.setPen(QColor("#e5e7eb"))
        painter.drawText(8, 17, "Guard / Choreography")
        if not self.project or not self.project.choreography:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(QRectF(8, 30, self.width() - 16, 50), Qt.AlignmentFlag.AlignCenter, "No choreography events")
            return
        required_height = 34 + len(self.project.choreography) * 27
        if self.minimumHeight() != required_height:
            self.setMinimumHeight(required_height)
        start, end = self.count_bounds()
        span = max(1.0, end - start + 1.0)
        content_left = 116.0
        content_width = max(1.0, self.width() - 126.0)
        painter.setPen(QPen(QColor("#303746"), 1))
        for count in range(int(start), int(end) + 1):
            if count % 4:
                continue
            x = content_left + (count - start) / span * content_width
            painter.drawLine(int(x), 20, int(x), self.height() - 5)
            painter.setPen(QColor("#7d8797"))
            painter.drawText(int(x + 3), 17, str(count))
            painter.setPen(QPen(QColor("#303746"), 1))
        for lane, (rect, event) in enumerate(self.event_rects()):
            painter.setPen(QColor("#cbd5e1"))
            painter.drawText(QRectF(8, rect.top(), 102, rect.height()), Qt.AlignmentFlag.AlignVCenter, event.name)
            color = QColor(self.EVENT_COLORS.get(event.event_type, "#06b6d4"))
            painter.setPen(QPen(color.lighter(125), 1))
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(rect.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, f"{event.start_count:g}–{event.end_count:g}")
        playhead_x = content_left + (self.current_count - start) / span * content_width
        painter.setPen(QPen(QColor("#f8d568"), 2))
        painter.drawLine(int(playhead_x), 20, int(playhead_x), self.height() - 5)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        for rect, choreography_event in self.event_rects():
            if rect.contains(event.position()):
                self.event_selected.emit(choreography_event.id)
                event.accept()
                return
        super().mousePressEvent(event)


class SpecializedDesignStudioDialog(QDialog):
    TAB_NAMES = {"surface": 0, "choreography": 1, "props": 2, "safety": 3}

    def __init__(
        self,
        project: DrillProject,
        selected_dot_ids: list[str],
        selected_prop_ids: list[str],
        set_index: int,
        initial_tab: str = "surface",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Specialized Design Studio")
        self.resize(1060, 720)
        self.setMinimumSize(780, 560)
        self.project = deepcopy(project)
        self.selected_dot_ids = [dot_id for dot_id in selected_dot_ids if self.project.dot_by_id(dot_id)]
        self.selected_prop_ids = [prop_id for prop_id in selected_prop_ids if self.project.prop_by_id(prop_id)]
        self.set_index = max(0, min(set_index, len(self.project.sets) - 1)) if self.project.sets else 0
        root = QVBoxLayout(self)
        header = QLabel("Specialized Design")
        header.setStyleSheet("font-size: 18px; font-weight: 800;")
        root.addWidget(header)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.build_surface_page()
        self.build_choreography_page()
        self.build_prop_page()
        self.build_safety_page()
        self.tabs.setCurrentIndex(self.TAB_NAMES.get(initial_tab, 0))
        root.addWidget(self.tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save Changes")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def build_surface_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        top = QHBoxLayout()
        self.surface_preset_combo = QComboBox()
        self.surface_preset_combo.addItem("Current / Custom", "custom")
        for key, preset in surface_presets().items():
            self.surface_preset_combo.addItem(preset.name, key)
        apply_preset = QPushButton("Load Preset")
        apply_preset.clicked.connect(self.load_surface_preset)
        top.addWidget(QLabel("Preset"))
        top.addWidget(self.surface_preset_combo, 1)
        top.addWidget(apply_preset)
        layout.addLayout(top)
        details = QGroupBox("Surface Geometry")
        form = QFormLayout(details)
        self.surface_name = QLineEdit()
        self.surface_type = QComboBox()
        for label, value in (("Football Field", "football"), ("Indoor Floor", "indoor"), ("Parade Route", "parade"), ("Staging Surface", "staging")):
            self.surface_type.addItem(label, value)
        self.surface_width = self.decimal_spin(2, 5000, " yd")
        self.surface_height = self.decimal_spin(2, 1000, " yd")
        self.grid_spacing = self.decimal_spin(0.25, 25, " yd")
        self.hash_style = QComboBox()
        for label, value in (("College", "college"), ("High School", "high_school"), ("Custom", "custom"), ("No Hashes", "none")):
            self.hash_style.addItem(label, value)
        self.front_hash = self.decimal_spin(-500, 500, " yd")
        self.back_hash = self.decimal_spin(-500, 500, " yd")
        self.endzone_depth = self.decimal_spin(0, 100, " yd")
        self.route_width = self.decimal_spin(0.5, 100, " yd")
        self.surface_background = QLineEdit()
        self.surface_background.setPlaceholderText("Theme default or #RRGGBB")
        self.surface_lines = QLineEdit()
        self.surface_lines.setPlaceholderText("Theme default or #RRGGBB")
        self.show_numbers = QCheckBox("Show yard numbers")
        self.show_endzones = QCheckBox("Show end zones")
        form.addRow("Name", self.surface_name)
        form.addRow("Type", self.surface_type)
        form.addRow("Length / width", self.surface_width)
        form.addRow("Depth / height", self.surface_height)
        form.addRow("Grid spacing", self.grid_spacing)
        form.addRow("Hash style", self.hash_style)
        form.addRow("Front hash (Y)", self.front_hash)
        form.addRow("Back hash (Y)", self.back_hash)
        form.addRow("End-zone depth", self.endzone_depth)
        form.addRow("Parade route width", self.route_width)
        form.addRow("Surface color", self.surface_background)
        form.addRow("Line color", self.surface_lines)
        form.addRow(self.show_numbers)
        form.addRow(self.show_endzones)
        layout.addWidget(details)
        route_group = QGroupBox("Parade Route Control Points")
        route_layout = QVBoxLayout(route_group)
        self.route_table = QTableWidget(0, 2)
        self.route_table.setHorizontalHeaderLabels(["X (yd)", "Y (yd)"])
        self.route_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.route_table.verticalHeader().setVisible(False)
        route_layout.addWidget(self.route_table)
        route_buttons = QHBoxLayout()
        add_point = QPushButton("Add Point")
        add_point.clicked.connect(self.add_route_point)
        remove_point = QPushButton("Remove Selected")
        remove_point.clicked.connect(self.remove_route_points)
        move_up = QPushButton("Move Up")
        move_up.clicked.connect(lambda: self.move_route_point(-1))
        move_down = QPushButton("Move Down")
        move_down.clicked.connect(lambda: self.move_route_point(1))
        route_buttons.addWidget(add_point)
        route_buttons.addWidget(remove_point)
        route_buttons.addWidget(move_up)
        route_buttons.addWidget(move_down)
        route_buttons.addStretch()
        route_layout.addLayout(route_buttons)
        layout.addWidget(route_group, 1)
        self.add_scrolled_tab(page, "Surface & Route")
        self.load_surface_controls()

    def build_choreography_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        selection = QLabel(
            f"New events apply to {len(self.selected_dot_ids)} performer(s) selected on the field before opening this studio."
        )
        selection.setWordWrap(True)
        layout.addWidget(selection)
        form_group = QGroupBox("New Guard / Choreography Event")
        grid = QGridLayout(form_group)
        self.event_name = QLineEdit("Choreography")
        self.event_type = QComboBox()
        for label, value in (("Choreography", "choreography"), ("Toss", "toss"), ("Equipment Change", "equipment_change"), ("Spin", "spin"), ("Dance / Body", "dance")):
            self.event_type.addItem(label, value)
        self.event_start = self.count_spin()
        self.event_end = self.count_spin()
        if self.project.sets:
            self.event_start.setValue(self.project.sets[self.set_index].start_count)
            self.event_end.setValue(self.project.sets[self.set_index].end_count)
        self.equipment_from = QLineEdit()
        self.equipment_to = QLineEdit()
        self.event_revolutions = self.decimal_spin(0, 20)
        self.event_height = self.decimal_spin(0, 20, " yd")
        self.event_notes = QLineEdit()
        add_button = QPushButton("Add Event for Selected Performers")
        add_button.clicked.connect(self.add_choreography_event)
        update_button = QPushButton("Update Selected Event")
        update_button.clicked.connect(self.update_choreography_event)
        fields = (
            ("Name", self.event_name), ("Type", self.event_type), ("Start", self.event_start), ("End", self.event_end),
            ("Equipment from", self.equipment_from), ("Equipment to", self.equipment_to),
            ("Revolutions", self.event_revolutions), ("Height", self.event_height), ("Notes", self.event_notes),
        )
        for index, (label, widget) in enumerate(fields):
            row, column = divmod(index, 3)
            grid.addWidget(QLabel(label), row * 2, column)
            grid.addWidget(widget, row * 2 + 1, column)
        grid.addWidget(add_button, 6, 0, 1, 2)
        grid.addWidget(update_button, 6, 2)
        layout.addWidget(form_group)
        self.choreography_timeline = ChoreographyTimelineWidget()
        timeline_scroll = QScrollArea()
        timeline_scroll.setWidgetResizable(True)
        timeline_scroll.setWidget(self.choreography_timeline)
        timeline_scroll.setMinimumHeight(150)
        layout.addWidget(timeline_scroll)
        self.choreography_table = QTableWidget(0, 7)
        self.choreography_table.setHorizontalHeaderLabels(["Event", "Type", "Performers", "Start", "End", "Equipment", "Notes"])
        self.choreography_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.choreography_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.choreography_table.verticalHeader().setVisible(False)
        self.choreography_table.itemSelectionChanged.connect(self.load_selected_choreography_event)
        header = self.choreography_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.choreography_table, 1)
        delete_button = QPushButton("Delete Selected Events")
        delete_button.clicked.connect(self.delete_choreography_events)
        layout.addWidget(delete_button)
        self.add_scrolled_tab(page, "Guard & Choreography")
        self.refresh_choreography()

    def build_prop_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        form_group = QGroupBox("Attach Prop to Selected Performers")
        form = QFormLayout(form_group)
        self.attachment_name = QLineEdit("Performer Prop Link")
        self.attachment_prop = QComboBox()
        for prop in self.project.props:
            self.attachment_prop.addItem(prop.name, prop.id)
        if self.selected_prop_ids:
            selected_index = self.attachment_prop.findData(self.selected_prop_ids[0])
            if selected_index >= 0:
                self.attachment_prop.setCurrentIndex(selected_index)
        self.attachment_mode = QComboBox()
        for label, value in (("Carry", "carry"), ("Push", "push"), ("Rotate around performer", "rotate")):
            self.attachment_mode.addItem(label, value)
        self.attachment_leader = QComboBox()
        for dot_id in self.selected_dot_ids:
            dot = self.project.dot_by_id(dot_id)
            self.attachment_leader.addItem(dot.name if dot else dot_id, dot_id)
        self.attachment_start = self.count_spin()
        self.attachment_end = self.count_spin()
        if self.project.sets:
            self.attachment_start.setValue(self.project.sets[self.set_index].start_count)
            self.attachment_end.setValue(self.project.sets[self.set_index].end_count)
        self.attachment_offset_x = self.decimal_spin(-200, 200, " yd")
        self.attachment_offset_y = self.decimal_spin(-200, 200, " yd")
        self.rotation_behavior = QComboBox()
        for label, value in (("Keep authored rotation", "fixed"), ("Match performer facing", "performer_facing"), ("Face direction of travel", "direction_of_travel")):
            self.rotation_behavior.addItem(label, value)
        self.rotation_offset = self.decimal_spin(-360, 360, "°")
        self.rotation_rate = self.decimal_spin(-720, 720, "°/count")
        self.attachment_enabled = QCheckBox("Enabled")
        self.attachment_enabled.setChecked(True)
        form.addRow("Name", self.attachment_name)
        form.addRow("Prop", self.attachment_prop)
        form.addRow("Interaction", self.attachment_mode)
        form.addRow("Leader / handle", self.attachment_leader)
        form.addRow("Start count", self.attachment_start)
        form.addRow("End count", self.attachment_end)
        form.addRow("Local offset X", self.attachment_offset_x)
        form.addRow("Local offset Y", self.attachment_offset_y)
        form.addRow("Rotation", self.rotation_behavior)
        form.addRow("Rotation offset", self.rotation_offset)
        form.addRow("Rotation rate", self.rotation_rate)
        form.addRow(self.attachment_enabled)
        add_button = QPushButton("Create Attachment")
        add_button.clicked.connect(self.add_prop_attachment)
        update_button = QPushButton("Update Selected Attachment")
        update_button.clicked.connect(self.update_prop_attachment)
        attachment_buttons = QHBoxLayout()
        attachment_buttons.addWidget(add_button)
        attachment_buttons.addWidget(update_button)
        form.addRow(attachment_buttons)
        layout.addWidget(form_group)
        self.attachment_table = QTableWidget(0, 7)
        self.attachment_table.setHorizontalHeaderLabels(["Name", "Prop", "Mode", "Performers", "Counts", "Rotation", "Enabled"])
        self.attachment_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.attachment_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.attachment_table.verticalHeader().setVisible(False)
        self.attachment_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.attachment_table.itemSelectionChanged.connect(self.load_selected_prop_attachment)
        layout.addWidget(self.attachment_table, 1)
        delete_button = QPushButton("Delete Selected Attachments")
        delete_button.clicked.connect(self.delete_prop_attachments)
        layout.addWidget(delete_button)
        self.add_scrolled_tab(page, "Prop Attachments")
        self.refresh_prop_attachments()
        self.initialize_attachment_offset()

    def build_safety_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        override_group = QGroupBox("Performer-Specific Physical Limits")
        form = QFormLayout(override_group)
        self.limit_dot = QComboBox()
        dot_ids = self.selected_dot_ids or [dot.id for dot in self.project.dots]
        for dot_id in dot_ids:
            dot = self.project.dot_by_id(dot_id)
            self.limit_dot.addItem(f"{dot.name if dot else dot_id} ({dot.instrument or dot.section or 'General'})", dot_id)
        self.limit_profile = QLabel()
        self.limit_profile.setWordWrap(True)
        self.limit_speed = self.decimal_spin(0.1, 10, " yd/count")
        self.limit_backward = self.decimal_spin(0.1, 10, " yd/count")
        self.limit_lateral = self.decimal_spin(0.1, 10, " yd/count")
        self.limit_rotation = self.decimal_spin(1, 720, "°/count")
        self.limit_toss = self.decimal_spin(0, 20, " rev")
        self.limit_recovery = self.decimal_spin(0, 32, " counts")
        self.limit_carry = self.decimal_spin(0.1, 1.0, "×")
        self.limit_notes = QLineEdit()
        self.limit_dot.currentIndexChanged.connect(self.load_limit_profile)
        apply_selected = QPushButton("Apply Limits to Listed Performer")
        apply_selected.clicked.connect(self.apply_physical_limit)
        apply_all = QPushButton("Apply Same Limits to Field Selection")
        apply_all.clicked.connect(self.apply_physical_limits_to_selection)
        form.addRow("Performer", self.limit_dot)
        form.addRow("Instrument profile", self.limit_profile)
        form.addRow("Maximum travel", self.limit_speed)
        form.addRow("Maximum backward", self.limit_backward)
        form.addRow("Maximum lateral", self.limit_lateral)
        form.addRow("Maximum turn rate", self.limit_rotation)
        form.addRow("Maximum toss", self.limit_toss)
        form.addRow("Minimum recovery", self.limit_recovery)
        form.addRow("Prop carry multiplier", self.limit_carry)
        form.addRow("Notes", self.limit_notes)
        action_row = QHBoxLayout()
        action_row.addWidget(apply_selected)
        action_row.addWidget(apply_all)
        form.addRow(action_row)
        layout.addWidget(override_group)
        analyze_row = QHBoxLayout()
        analyze_button = QPushButton("Analyze Current Set")
        analyze_button.clicked.connect(self.run_safety_analysis)
        self.analysis_scope = QLabel("Uses performer instrument/equipment profiles, choreography, facings, and prop attachments.")
        self.analysis_scope.setWordWrap(True)
        analyze_row.addWidget(analyze_button)
        analyze_row.addWidget(self.analysis_scope, 1)
        layout.addLayout(analyze_row)
        self.safety_table = QTableWidget(0, 6)
        self.safety_table.setHorizontalHeaderLabels(["Severity", "Performer", "Count", "Rule", "Warning", "Suggested Fix"])
        self.safety_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.safety_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.safety_table.verticalHeader().setVisible(False)
        safety_header = self.safety_table.horizontalHeader()
        safety_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        safety_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        safety_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.safety_table, 1)
        self.add_scrolled_tab(page, "Physical Limits & Warnings")
        self.load_limit_profile()

    def add_scrolled_tab(self, page: QWidget, label: str) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, label)

    @staticmethod
    def decimal_spin(minimum: float, maximum: float, suffix: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setSingleStep(0.25)
        spin.setSuffix(suffix)
        return spin

    def count_spin(self) -> QDoubleSpinBox:
        maximum = max((drill_set.end_count for drill_set in self.project.sets), default=10000)
        spin = self.decimal_spin(0, max(10000, maximum))
        spin.setDecimals(2)
        spin.setSingleStep(1)
        return spin

    def load_surface_controls(self) -> None:
        surface = self.project.surface
        self.surface_name.setText(surface.name)
        self.surface_type.setCurrentIndex(max(0, self.surface_type.findData(surface.surface_type)))
        self.surface_width.setValue(surface.width_yards)
        self.surface_height.setValue(surface.height_yards)
        self.grid_spacing.setValue(surface.grid_spacing_yards)
        self.hash_style.setCurrentIndex(max(0, self.hash_style.findData(surface.hash_style)))
        self.front_hash.setValue(surface.front_hash_yards)
        self.back_hash.setValue(surface.back_hash_yards)
        self.endzone_depth.setValue(surface.endzone_depth_yards)
        self.route_width.setValue(surface.route_width_yards)
        self.surface_background.setText(surface.background_color)
        self.surface_lines.setText(surface.line_color)
        self.show_numbers.setChecked(surface.show_yard_numbers)
        self.show_endzones.setChecked(surface.show_end_zones)
        self.route_table.setRowCount(len(surface.route_points))
        for row, point in enumerate(surface.route_points):
            self.route_table.setItem(row, 0, QTableWidgetItem(f"{point[0]:g}"))
            self.route_table.setItem(row, 1, QTableWidgetItem(f"{point[1]:g}"))

    def load_surface_preset(self) -> None:
        key = str(self.surface_preset_combo.currentData())
        if key == "custom":
            return
        self.project.surface = surface_preset(key)
        self.load_surface_controls()

    def add_route_point(self) -> None:
        row = self.route_table.rowCount()
        self.route_table.insertRow(row)
        previous_x = float(self.route_table.item(row - 1, 0).text()) if row and self.route_table.item(row - 1, 0) else 0.0
        previous_y = float(self.route_table.item(row - 1, 1).text()) if row and self.route_table.item(row - 1, 1) else 0.0
        self.route_table.setItem(row, 0, QTableWidgetItem(f"{previous_x + 10:g}"))
        self.route_table.setItem(row, 1, QTableWidgetItem(f"{previous_y:g}"))

    def remove_route_points(self) -> None:
        for row in sorted({index.row() for index in self.route_table.selectedIndexes()}, reverse=True):
            self.route_table.removeRow(row)

    def move_route_point(self, direction: int) -> None:
        rows = sorted({index.row() for index in self.route_table.selectedIndexes()})
        if len(rows) != 1:
            return
        row = rows[0]
        target = row + direction
        if not 0 <= target < self.route_table.rowCount():
            return
        values = [self.route_table.takeItem(row, column) for column in range(2)]
        target_values = [self.route_table.takeItem(target, column) for column in range(2)]
        for column in range(2):
            self.route_table.setItem(row, column, target_values[column])
            self.route_table.setItem(target, column, values[column])
        self.route_table.selectRow(target)

    def commit_surface(self) -> None:
        route_points: list[tuple[float, float]] = []
        for row in range(self.route_table.rowCount()):
            try:
                route_points.append((float(self.route_table.item(row, 0).text()), float(self.route_table.item(row, 1).text())))
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(f"Route point {row + 1} must contain numeric X and Y values.") from exc
        surface = deepcopy(self.project.surface)
        surface.name = self.surface_name.text().strip() or "Performance Surface"
        surface.surface_type = str(self.surface_type.currentData())
        surface.width_yards = self.surface_width.value()
        surface.height_yards = self.surface_height.value()
        surface.grid_spacing_yards = self.grid_spacing.value()
        surface.hash_style = str(self.hash_style.currentData())
        surface.front_hash_yards = self.front_hash.value()
        surface.back_hash_yards = self.back_hash.value()
        surface.endzone_depth_yards = self.endzone_depth.value()
        surface.route_width_yards = self.route_width.value()
        surface.route_points = route_points
        surface.background_color = self.surface_background.text().strip()
        surface.line_color = self.surface_lines.text().strip()
        surface.show_yard_numbers = self.show_numbers.isChecked()
        surface.show_end_zones = self.show_endzones.isChecked()
        if surface.surface_type == "parade" and len(route_points) < 2:
            raise ValueError("Parade routes require at least two route control points.")
        for color in (surface.background_color, surface.line_color):
            if color and not QColor(color).isValid():
                raise ValueError(f"'{color}' is not a valid surface color.")
        self.project.surface = normalized_surface(surface)

    def add_choreography_event(self) -> None:
        if not self.selected_dot_ids:
            QMessageBox.information(self, "Guard Choreography", "Select one or more performers on the field before opening the studio.")
            return
        start = self.event_start.value()
        end = max(start, self.event_end.value())
        event = ChoreographyEvent(
            id=f"choreo_{uuid4().hex[:10]}",
            name=self.event_name.text().strip() or self.event_type.currentText(),
            event_type=str(self.event_type.currentData()),
            dot_ids=list(self.selected_dot_ids),
            start_count=start,
            end_count=end,
            equipment_from=self.equipment_from.text().strip(),
            equipment_to=self.equipment_to.text().strip(),
            revolutions=self.event_revolutions.value(),
            height_yards=self.event_height.value(),
            notes=self.event_notes.text().strip(),
        )
        self.project.choreography.append(event)
        self.refresh_choreography()

    def selected_choreography_event(self) -> ChoreographyEvent | None:
        rows = {index.row() for index in self.choreography_table.selectedIndexes()}
        if len(rows) != 1:
            return None
        item = self.choreography_table.item(next(iter(rows)), 0)
        event_id = str(item.data(Qt.ItemDataRole.UserRole)) if item else ""
        return next((event for event in self.project.choreography if event.id == event_id), None)

    def load_selected_choreography_event(self) -> None:
        event = self.selected_choreography_event()
        if event is None:
            return
        self.event_name.setText(event.name)
        self.event_type.setCurrentIndex(max(0, self.event_type.findData(event.event_type)))
        self.event_start.setValue(event.start_count)
        self.event_end.setValue(event.end_count)
        self.equipment_from.setText(event.equipment_from)
        self.equipment_to.setText(event.equipment_to)
        self.event_revolutions.setValue(event.revolutions)
        self.event_height.setValue(event.height_yards)
        self.event_notes.setText(event.notes)

    def update_choreography_event(self) -> None:
        event = self.selected_choreography_event()
        if event is None:
            QMessageBox.information(self, "Guard Choreography", "Select exactly one event to update.")
            return
        event.name = self.event_name.text().strip() or self.event_type.currentText()
        event.event_type = str(self.event_type.currentData())
        event.start_count = self.event_start.value()
        event.end_count = max(event.start_count, self.event_end.value())
        event.equipment_from = self.equipment_from.text().strip()
        event.equipment_to = self.equipment_to.text().strip()
        event.revolutions = self.event_revolutions.value()
        event.height_yards = self.event_height.value()
        event.notes = self.event_notes.text().strip()
        self.refresh_choreography()

    def refresh_choreography(self) -> None:
        events = sorted(self.project.choreography, key=lambda item: (item.start_count, item.end_count, item.name))
        self.choreography_table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = (
                event.name,
                event.event_type.replace("_", " ").title(),
                str(len(event.dot_ids)),
                f"{event.start_count:g}",
                f"{event.end_count:g}",
                f"{event.equipment_from or '—'} → {event.equipment_to or '—'}",
                event.notes,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, event.id)
                self.choreography_table.setItem(row, column, item)
        self.choreography_timeline.set_project(self.project)

    def delete_choreography_events(self) -> None:
        event_ids = {
            self.choreography_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in {index.row() for index in self.choreography_table.selectedIndexes()}
            if self.choreography_table.item(row, 0)
        }
        self.project.choreography = [event for event in self.project.choreography if event.id not in event_ids]
        self.refresh_choreography()

    def add_prop_attachment(self) -> None:
        if not self.project.props:
            QMessageBox.information(self, "Prop Attachment", "Import or design a prop first.")
            return
        if not self.selected_dot_ids:
            QMessageBox.information(self, "Prop Attachment", "Select the performers who carry or push the prop before opening the studio.")
            return
        start = self.attachment_start.value()
        attachment = PropAttachment(
            id=f"attachment_{uuid4().hex[:10]}",
            name=self.attachment_name.text().strip() or "Prop Attachment",
            prop_id=str(self.attachment_prop.currentData()),
            dot_ids=list(self.selected_dot_ids),
            start_count=start,
            end_count=max(start, self.attachment_end.value()),
            mode=str(self.attachment_mode.currentData()),
            leader_dot_id=str(self.attachment_leader.currentData() or self.selected_dot_ids[0]),
            offset_x=self.attachment_offset_x.value(),
            offset_y=self.attachment_offset_y.value(),
            rotation_behavior=str(self.rotation_behavior.currentData()),
            rotation_offset=self.rotation_offset.value(),
            rotation_rate=self.rotation_rate.value(),
            enabled=self.attachment_enabled.isChecked(),
        )
        self.project.prop_attachments = [
            item
            for item in self.project.prop_attachments
            if not (item.prop_id == attachment.prop_id and item.enabled and attachment.start_count <= item.end_count and attachment.end_count >= item.start_count)
        ]
        self.project.prop_attachments.append(attachment)
        self.refresh_prop_attachments()

    def initialize_attachment_offset(self) -> None:
        if not self.project.props or not self.selected_dot_ids or not self.project.sets:
            return
        prop_id = str(self.attachment_prop.currentData() or "")
        state = self.project.sets[self.set_index].prop_positions.get(prop_id)
        positions = [
            self.project.sets[self.set_index].dot_positions[dot_id]
            for dot_id in self.selected_dot_ids
            if dot_id in self.project.sets[self.set_index].dot_positions
        ]
        if state and positions:
            center_x = sum(point[0] for point in positions) / len(positions)
            center_y = sum(point[1] for point in positions) / len(positions)
            self.attachment_offset_x.setValue(float(state.get("x", 0)) - center_x)
            self.attachment_offset_y.setValue(float(state.get("y", 0)) - center_y)

    def selected_prop_attachment(self) -> PropAttachment | None:
        rows = {index.row() for index in self.attachment_table.selectedIndexes()}
        if len(rows) != 1:
            return None
        item = self.attachment_table.item(next(iter(rows)), 0)
        attachment_id = str(item.data(Qt.ItemDataRole.UserRole)) if item else ""
        return next((attachment for attachment in self.project.prop_attachments if attachment.id == attachment_id), None)

    def load_selected_prop_attachment(self) -> None:
        attachment = self.selected_prop_attachment()
        if attachment is None:
            return
        self.attachment_name.setText(attachment.name)
        self.attachment_prop.setCurrentIndex(max(0, self.attachment_prop.findData(attachment.prop_id)))
        self.attachment_mode.setCurrentIndex(max(0, self.attachment_mode.findData(attachment.mode)))
        leader_index = self.attachment_leader.findData(attachment.leader_dot_id)
        if leader_index >= 0:
            self.attachment_leader.setCurrentIndex(leader_index)
        self.attachment_start.setValue(attachment.start_count)
        self.attachment_end.setValue(attachment.end_count)
        self.attachment_offset_x.setValue(attachment.offset_x)
        self.attachment_offset_y.setValue(attachment.offset_y)
        self.rotation_behavior.setCurrentIndex(max(0, self.rotation_behavior.findData(attachment.rotation_behavior)))
        self.rotation_offset.setValue(attachment.rotation_offset)
        self.rotation_rate.setValue(attachment.rotation_rate)
        self.attachment_enabled.setChecked(attachment.enabled)

    def update_prop_attachment(self) -> None:
        attachment = self.selected_prop_attachment()
        if attachment is None:
            QMessageBox.information(self, "Prop Attachment", "Select exactly one attachment to update.")
            return
        attachment.name = self.attachment_name.text().strip() or "Prop Attachment"
        attachment.prop_id = str(self.attachment_prop.currentData())
        attachment.mode = str(self.attachment_mode.currentData())
        attachment.leader_dot_id = str(self.attachment_leader.currentData() or attachment.leader_dot_id)
        attachment.start_count = self.attachment_start.value()
        attachment.end_count = max(attachment.start_count, self.attachment_end.value())
        attachment.offset_x = self.attachment_offset_x.value()
        attachment.offset_y = self.attachment_offset_y.value()
        attachment.rotation_behavior = str(self.rotation_behavior.currentData())
        attachment.rotation_offset = self.rotation_offset.value()
        attachment.rotation_rate = self.rotation_rate.value()
        attachment.enabled = self.attachment_enabled.isChecked()
        self.refresh_prop_attachments()

    def refresh_prop_attachments(self) -> None:
        attachments = sorted(self.project.prop_attachments, key=lambda item: (item.start_count, item.prop_id, item.name))
        self.attachment_table.setRowCount(len(attachments))
        for row, attachment in enumerate(attachments):
            prop = self.project.prop_by_id(attachment.prop_id)
            values = (
                attachment.name,
                prop.name if prop else attachment.prop_id,
                attachment.mode.title(),
                str(len(attachment.dot_ids)),
                f"{attachment.start_count:g}–{attachment.end_count:g}",
                attachment.rotation_behavior.replace("_", " ").title(),
                "Yes" if attachment.enabled else "No",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, attachment.id)
                self.attachment_table.setItem(row, column, item)

    def delete_prop_attachments(self) -> None:
        attachment_ids = {
            self.attachment_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in {index.row() for index in self.attachment_table.selectedIndexes()}
            if self.attachment_table.item(row, 0)
        }
        self.project.prop_attachments = [item for item in self.project.prop_attachments if item.id not in attachment_ids]
        self.refresh_prop_attachments()

    def load_limit_profile(self) -> None:
        dot_id = str(self.limit_dot.currentData() or "")
        if not dot_id:
            return
        limits = physical_limits_for_dot(self.project, dot_id)
        self.limit_profile.setText(limits.profile_name)
        self.limit_speed.setValue(limits.max_yards_per_count)
        self.limit_backward.setValue(limits.max_backward_yards_per_count)
        self.limit_lateral.setValue(limits.max_lateral_yards_per_count)
        self.limit_rotation.setValue(limits.max_rotation_degrees_per_count)
        self.limit_toss.setValue(limits.max_toss_revolutions)
        self.limit_recovery.setValue(limits.minimum_recovery_counts)
        self.limit_carry.setValue(limits.carry_speed_multiplier)
        override = next((item for item in self.project.physical_limits if item.dot_id == dot_id), None)
        self.limit_notes.setText(override.notes if override else "")

    def current_physical_limit(self, dot_id: str) -> PerformerPhysicalLimits:
        return PerformerPhysicalLimits(
            dot_id=dot_id,
            max_yards_per_count=self.limit_speed.value(),
            max_backward_yards_per_count=self.limit_backward.value(),
            max_lateral_yards_per_count=self.limit_lateral.value(),
            max_rotation_degrees_per_count=self.limit_rotation.value(),
            max_toss_revolutions=self.limit_toss.value(),
            minimum_recovery_counts=self.limit_recovery.value(),
            carry_speed_multiplier=self.limit_carry.value(),
            notes=self.limit_notes.text().strip(),
        )

    def apply_physical_limit(self) -> None:
        dot_id = str(self.limit_dot.currentData() or "")
        if dot_id:
            set_physical_limits(self.project, self.current_physical_limit(dot_id))
            self.limit_profile.setText(f"{physical_limits_for_dot(self.project, dot_id).profile_name} (saved)")

    def apply_physical_limits_to_selection(self) -> None:
        dot_ids = self.selected_dot_ids or [str(self.limit_dot.currentData() or "")]
        for dot_id in dot_ids:
            if dot_id:
                set_physical_limits(self.project, self.current_physical_limit(dot_id))
        self.limit_profile.setText(f"Applied to {len([item for item in dot_ids if item])} performer(s)")

    def run_safety_analysis(self) -> None:
        dot_ids = self.selected_dot_ids or None
        warnings = analyze_specialized_safety(self.project, self.set_index, dot_ids=dot_ids)
        self.safety_table.setRowCount(len(warnings))
        for row, warning in enumerate(warnings):
            values = (warning.severity.title(), warning.dot_id, f"{warning.count:g}", warning.rule.title(), warning.message, warning.suggestion)
            for column, value in enumerate(values):
                self.safety_table.setItem(row, column, QTableWidgetItem(value))
        self.analysis_scope.setText(f"{len(warnings)} specialized warning(s) found in {self.project.sets[self.set_index].name if self.project.sets else 'project'}.")

    def accept(self) -> None:  # type: ignore[override]
        try:
            self.commit_surface()
        except ValueError as exc:
            self.tabs.setCurrentIndex(0)
            QMessageBox.warning(self, "Invalid Surface", str(exc))
            return
        errors = validate_choreography(self.project)
        if errors:
            self.tabs.setCurrentIndex(1)
            QMessageBox.warning(self, "Choreography Conflicts", "\n".join(errors[:12]))
            return
        self.project.ensure_set_positions()
        super().accept()
