from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QKeySequence, QUndoCommand, QUndoStack
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QApplication,
    QPushButton,
    QProgressDialog,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from drill_writer.core.animation import interpolate_project, sample_transition_path
from drill_writer.core.models import Dot, DrillProject, DrillSet, Marker, Transition
from drill_writer.core.project_io import load_project, project_library_dir, safe_folder_name, save_project
from drill_writer.core.tools import (
    arc_positions,
    centered_positions,
    curve_positions,
    line_positions,
    mirror_positions,
    positions_along_path,
    rotate_positions,
    sampled_shape_path,
    scatter_positions,
)
from drill_writer.export.exporters import (
    ExportCancelled,
    export_drill_sheet_pdf,
    export_mp4,
    export_project_zip,
)
from drill_writer.ui.field_view import EditorTool, FieldView


class MoveDotsCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        set_index: int,
        before: dict[str, tuple[float, float]],
        after: dict[str, tuple[float, float]],
        label: str,
    ) -> None:
        super().__init__(label)
        self.window = window
        self.set_index = set_index
        self.before = before
        self.after = after

    def redo(self) -> None:
        self.window.apply_positions(self.after, push_undo=False, set_index=self.set_index)

    def undo(self) -> None:
        self.window.apply_positions(self.before, push_undo=False, set_index=self.set_index)


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
        self.mirror_axis = 0.0
        self.undo_stack = QUndoStack(self)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(16)
        self.play_timer.timeout.connect(self.tick_playback)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(8000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()

        self.setWindowTitle(f"Drill Pirate - {self.project.metadata.show_title}")
        self.resize(1500, 900)
        self.field = FieldView()
        self.field.set_project(self.project)
        self.field.selection_changed.connect(self.selection_changed)
        self.field.dot_moved.connect(self.dot_moved)
        self.field.dots_moved.connect(self.dots_moved)
        self.field.context_action.connect(self.context_action)
        self.field.preview_handle_moved.connect(self.preview_handle_moved)
        self.field.path_anchor_added.connect(self.add_path_anchor)
        self.field.path_anchor_moved.connect(self.move_path_anchor)
        self.field.shape_anchor_toggled.connect(self.toggle_shape_line_anchor)
        self.field.set_formation_callback(self.apply_formation)
        self.setCentralWidget(self.build_layout())
        self.build_menus()
        self.populate_sets()
        self.sync_timeline()
        self.sync_inspector()
        self.load_audio()

    def build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        save_action = self.menu_action("Save", self.save, QKeySequence.StandardKey.Save)
        save_as_action = self.menu_action("Save As", self.save_as, QKeySequence.StandardKey.SaveAs)
        export_action = self.menu_action("Export", self.show_export_dialog, QKeySequence("Ctrl+E"))
        home_action = self.menu_action("Return to Home Screen", self.return_home)
        file_menu.addActions([save_action, save_as_action, export_action])
        file_menu.addSeparator()
        file_menu.addAction(home_action)

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(self.menu_action("Undo", self.undo_stack.undo, QKeySequence.StandardKey.Undo))
        edit_menu.addAction(self.menu_action("Redo", self.undo_stack.redo, QKeySequence.StandardKey.Redo))

        playback_menu = self.menuBar().addMenu("Playback")
        playback_menu.addAction(self.menu_action("Play", self.play, Qt.Key.Key_Space))
        playback_menu.addAction(self.menu_action("Pause", self.pause))

        tools_menu = self.menuBar().addMenu("Tools")
        add_marcher_action = QAction("Add Marcher", self)
        add_marcher_action.setShortcut(QKeySequence("Ctrl+M"))
        add_marcher_action.triggered.connect(self.add_marcher)
        delete_marcher_action = QAction("Delete Selected", self)
        delete_marcher_action.setShortcut(QKeySequence("Del"))
        delete_marcher_action.triggered.connect(self.delete_selected_marchers)
        add_set_action = QAction("Add Set", self)
        add_set_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        add_set_action.triggered.connect(self.add_set)
        remove_set_action = QAction("Remove Set", self)
        remove_set_action.setShortcut(QKeySequence("Ctrl+Shift+Backspace"))
        remove_set_action.triggered.connect(self.remove_set)
        tools_menu.addActions(
            [add_marcher_action, delete_marcher_action, add_set_action, remove_set_action]
        )
        self.addActions([add_marcher_action, delete_marcher_action, add_set_action, remove_set_action])

    def menu_action(self, text: str, callback, shortcut=None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    def build_layout(self) -> QWidget:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        splitter = QSplitter()
        splitter.addWidget(self.scroll_panel(self.build_tools_panel(), 300))
        splitter.addWidget(self.field)
        splitter.addWidget(self.scroll_panel(self.build_inspector_panel(), 360))
        splitter.setSizes([320, 1000, 380])
        root_layout.addWidget(splitter, 1)
        root_layout.addWidget(self.build_timeline_panel())
        return root

    def scroll_panel(self, widget: QWidget, minimum_width: int) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(minimum_width)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    def build_tools_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        group = QGroupBox("Tools")
        tools_layout = QVBoxLayout(group)
        self.tool_buttons: dict[EditorTool, QPushButton] = {}
        for tool, label in (
            (EditorTool.SELECT, "Select"),
            (EditorTool.LINE, "Line"),
            (EditorTool.CURVE, "Curve"),
            (EditorTool.ARC, "Arc"),
            (EditorTool.SCATTER, "Scatter"),
            (EditorTool.MIRROR, "Mirror"),
            (EditorTool.SHAPE_LINE, "Shape Line"),
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, selected=tool: self.set_tool(selected))
            tools_layout.addWidget(button)
            self.tool_buttons[tool] = button
        layout.addWidget(group)

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
        layout.addWidget(align_group)

        self.tool_edit_group = QGroupBox("Tool Edit")
        edit_layout = QVBoxLayout(self.tool_edit_group)

        self.line_tool_group = QGroupBox("Line")
        line_layout = QVBoxLayout(self.line_tool_group)
        line_layout.addWidget(QLabel("Preview evenly spaces selected marchers between the first and last selected dot."))

        self.curve_tool_group = QGroupBox("Curve")
        curve_form = QFormLayout(self.curve_tool_group)
        self.curve_bend = QDoubleSpinBox()
        self.curve_bend.setRange(-40, 40)
        self.curve_bend.setValue(12)
        self.curve_bend.setSuffix(" yd")
        curve_form.addRow("Bend", self.curve_bend)

        self.arc_tool_group = QGroupBox("Arc")
        arc_form = QFormLayout(self.arc_tool_group)
        self.arc_radius = QDoubleSpinBox()
        self.arc_radius.setRange(1, 80)
        self.arc_radius.setValue(18)
        self.arc_radius.setSuffix(" yd")
        self.arc_sweep = QDoubleSpinBox()
        self.arc_sweep.setRange(-360, 360)
        self.arc_sweep.setValue(120)
        self.arc_sweep.setSuffix(" deg")
        arc_form.addRow("Radius", self.arc_radius)
        arc_form.addRow("Sweep", self.arc_sweep)

        self.scatter_tool_group = QGroupBox("Scatter")
        scatter_form = QFormLayout(self.scatter_tool_group)
        self.scatter_radius = QDoubleSpinBox()
        self.scatter_radius.setRange(0, 40)
        self.scatter_radius.setValue(8)
        self.scatter_radius.setSuffix(" yd")
        scatter_form.addRow("Radius", self.scatter_radius)

        self.mirror_tool_group = QGroupBox("Mirror")
        mirror_layout = QVBoxLayout(self.mirror_tool_group)
        mirror_layout.addWidget(QLabel("Preview mirrors selected marchers across midfield."))

        self.shape_line_tool_group = QGroupBox("Shape Line")
        shape_line_form = QFormLayout(self.shape_line_tool_group)
        self.shape_line_curved = QCheckBox("Curved Segments")
        self.shape_line_curved.setChecked(True)
        self.shape_line_curved.toggled.connect(self.update_formation_preview)
        shape_line_form.addRow(self.shape_line_curved)

        self.rotate_tool_group = QGroupBox("Rotate")
        rotate_form = QFormLayout(self.rotate_tool_group)
        self.rotation_degrees = QDoubleSpinBox()
        self.rotation_degrees.setRange(-360, 360)
        self.rotation_degrees.setValue(15)
        self.rotation_degrees.setSuffix(" deg")
        rotate_form.addRow("Degrees", self.rotation_degrees)
        for editor in (
            self.curve_bend,
            self.arc_radius,
            self.arc_sweep,
            self.scatter_radius,
            self.rotation_degrees,
        ):
            editor.valueChanged.connect(self.update_formation_preview)
        apply_button = QPushButton("Apply Preview")
        apply_button.clicked.connect(self.apply_current_preview)
        clear_button = QPushButton("Clear Preview")
        clear_button.clicked.connect(self.clear_formation_preview)
        rotate_button = QPushButton("Rotate Selection")
        rotate_button.clicked.connect(self.rotate_selection)
        for group_widget in (
            self.line_tool_group,
            self.curve_tool_group,
            self.arc_tool_group,
            self.scatter_tool_group,
            self.mirror_tool_group,
            self.shape_line_tool_group,
            self.rotate_tool_group,
        ):
            edit_layout.addWidget(group_widget)
        apply_row = QHBoxLayout()
        apply_row.addWidget(apply_button)
        apply_row.addWidget(clear_button)
        edit_layout.addLayout(apply_row)
        edit_layout.addWidget(rotate_button)
        layout.addWidget(self.tool_edit_group)

        view_group = QGroupBox("View")
        view_layout = QVBoxLayout(view_group)
        labels = QCheckBox("Labels")
        labels.setChecked(True)
        labels.toggled.connect(self.field.update_labels)
        ghost = QCheckBox("Ghost Previous Set")
        ghost.setChecked(True)
        view_layout.addWidget(labels)
        view_layout.addWidget(ghost)
        layout.addWidget(view_group)
        layout.addStretch()
        self.set_tool(EditorTool.SELECT)
        return panel

    def build_inspector_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.selection_label = QLabel("No selection")
        layout.addWidget(self.selection_label)

        dot_group = QGroupBox("Dot Properties")
        form = QFormLayout(dot_group)
        self.dot_name = QLineEdit()
        self.dot_section = QLineEdit()
        self.dot_x = QLineEdit()
        self.dot_y = QLineEdit()
        self.dot_name.editingFinished.connect(self.update_selected_dot)
        self.dot_section.editingFinished.connect(self.update_selected_dot)
        self.dot_x.editingFinished.connect(self.update_selected_dot_position)
        self.dot_y.editingFinished.connect(self.update_selected_dot_position)
        form.addRow("Name", self.dot_name)
        form.addRow("Section", self.dot_section)
        form.addRow("X", self.dot_x)
        form.addRow("Y", self.dot_y)
        layout.addWidget(dot_group)

        set_group = QGroupBox("Sets")
        set_layout = QVBoxLayout(set_group)
        self.set_list = QListWidget()
        self.set_list.currentRowChanged.connect(self.change_set)
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
        self.set_name.editingFinished.connect(self.update_set_details)
        self.set_start_count.valueChanged.connect(self.update_set_details)
        self.set_count_length.valueChanged.connect(self.update_set_length)
        self.set_end_count.valueChanged.connect(self.update_set_details)
        self.set_tempo.valueChanged.connect(self.update_set_details)
        self.transition_combo.currentTextChanged.connect(self.update_transition)
        details_form.addRow("Name", self.set_name)
        details_form.addRow("Start", self.set_start_count)
        details_form.addRow("Counts", self.set_count_length)
        details_form.addRow("End", self.set_end_count)
        details_form.addRow("Tempo", self.set_tempo)
        details_form.addRow("Transition", self.transition_combo)
        set_layout.addWidget(details)
        layout.addWidget(set_group, 1)
        return panel

    def build_timeline_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        row = QHBoxLayout()
        self.count_label = QLabel("Count 1")
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.valueChanged.connect(self.scrub)
        self.marker_button = QPushButton("Add Marker")
        self.marker_button.clicked.connect(self.add_marker)
        row.addWidget(self.count_label)
        row.addWidget(self.timeline, 1)
        row.addWidget(self.marker_button)
        layout.addLayout(row)
        self.marker_table = QTableWidget(0, 2)
        self.marker_table.setHorizontalHeaderLabels(["Count", "Marker"])
        self.marker_table.setMaximumHeight(100)
        layout.addWidget(self.marker_table)
        return panel

    def load_audio(self) -> None:
        audio_path = self.project_dir / self.project.metadata.audio_file if self.project.metadata.audio_file else None
        if audio_path and audio_path.exists():
            self.player.setSource(QUrl.fromLocalFile(str(audio_path)))

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
        if saved_path and Path(saved_path).exists():
            return saved_path
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
        self.field.set_tool(tool)
        for key, button in self.tool_buttons.items():
            button.setChecked(key == tool)
        self.update_tool_edit_visibility()
        _ids, positions = self.selected_positions()
        if tool == EditorTool.LINE and len(positions) >= 2:
            self.line_endpoints = [positions[0], positions[-1]]
        elif tool == EditorTool.SHAPE_LINE:
            self.initialize_shape_line_anchors(_ids, positions)
        elif tool == EditorTool.MIRROR and positions:
            self.mirror_axis = sum(x for x, _y in positions) / len(positions)
        self.update_formation_preview()

    def update_tool_edit_visibility(self) -> None:
        tool = self.field.active_tool
        self.tool_edit_group.setVisible(tool != EditorTool.SELECT)
        self.line_tool_group.setVisible(tool == EditorTool.LINE)
        self.curve_tool_group.setVisible(tool == EditorTool.CURVE)
        self.arc_tool_group.setVisible(tool == EditorTool.ARC)
        self.scatter_tool_group.setVisible(tool == EditorTool.SCATTER)
        self.mirror_tool_group.setVisible(tool == EditorTool.MIRROR)
        self.shape_line_tool_group.setVisible(tool == EditorTool.SHAPE_LINE)
        self.rotate_tool_group.setVisible(False)

    def current_set(self) -> DrillSet:
        return self.project.sets[self.set_index]

    def current_positions(self) -> dict[str, tuple[float, float]]:
        return dict(self.current_set().dot_positions)

    def dot_moved(self, dot_id: str, x: float, y: float) -> None:
        before = self.current_positions()
        after = dict(before)
        after[dot_id] = (x, y)
        self.undo_stack.push(MoveDotsCommand(self, self.set_index, before, after, "Move Dot"))

    def dots_moved(self, positions: dict[str, tuple[float, float]]) -> None:
        before = self.current_positions()
        after = dict(before)
        after.update(positions)
        self.undo_stack.push(MoveDotsCommand(self, self.set_index, before, after, "Move Form"))

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
        )
        self.project.dots.append(new_dot)
        for drill_set in self.project.sets:
            drill_set.dot_positions[dot_id] = (new_dot.x, new_dot.y)
        self.field.rebuild_dots()
        self.field.set_positions(self.current_set().dot_positions)
        self.field.dot_items[dot_id].setSelected(True)
        self.selection_changed()

    def delete_selected_marchers(self) -> None:
        if self.set_index != 0:
            QMessageBox.information(self, "Delete Marchers", "Delete marchers from Set 1.")
            return
        selected = set(self.field.selected_dot_ids())
        if not selected:
            return
        self.project.dots = [dot for dot in self.project.dots if dot.id not in selected]
        for drill_set in self.project.sets:
            for dot_id in selected:
                drill_set.dot_positions.pop(dot_id, None)
                drill_set.path_anchors.pop(dot_id, None)
        self.field.clear_preview()
        self.field.clear_paths()
        self.field.rebuild_dots()
        self.field.set_positions(self.current_set().dot_positions)
        self.sync_inspector()

    def apply_positions(
        self,
        positions: dict[str, tuple[float, float]],
        push_undo: bool = True,
        set_index: int | None = None,
    ) -> None:
        target_set_index = self.set_index if set_index is None else set_index
        if push_undo:
            self.undo_stack.push(
                MoveDotsCommand(
                    self,
                    target_set_index,
                    dict(self.project.sets[target_set_index].dot_positions),
                    positions,
                    "Move Dots",
                )
            )
            return
        self.project.sets[target_set_index].dot_positions.update(positions)
        for dot in self.project.dots:
            if dot.id in positions and target_set_index == 0:
                dot.x, dot.y = positions[dot.id]
        if target_set_index == self.set_index:
            self.field.set_positions(self.current_set().dot_positions)
            self.update_formation_preview()
            self.refresh_selected_paths()
            self.sync_inspector()

    def selected_positions(self) -> tuple[list[str], list[tuple[float, float]]]:
        ids = self.ordered_selected_dot_ids()
        positions = [self.current_set().dot_positions[dot_id] for dot_id in ids]
        return ids, positions

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
        ids, positions = self.selected_positions()
        if len(ids) < 2 and tool not in (EditorTool.SCATTER, EditorTool.MIRROR):
            return {}
        if not ids:
            return {}
        if tool == EditorTool.LINE:
            if len(self.line_endpoints) != 2:
                self.line_endpoints = [positions[0], positions[-1]]
            new_positions = line_positions(len(ids), self.line_endpoints[0], self.line_endpoints[1])
        elif tool == EditorTool.CURVE:
            center_x = sum(x for x, _y in positions) / len(positions)
            center_y = sum(y for _x, y in positions) / len(positions)
            new_positions = curve_positions(positions, (center_x, center_y + self.curve_bend.value()), 0.85)
        elif tool == EditorTool.ARC:
            center_x = sum(x for x, _y in positions) / len(positions)
            center_y = sum(y for _x, y in positions) / len(positions)
            new_positions = arc_positions(
                len(ids),
                (center_x, center_y),
                self.arc_radius.value(),
                270 - self.arc_sweep.value() / 2,
                self.arc_sweep.value(),
            )
        elif tool == EditorTool.SCATTER:
            new_positions = scatter_positions(positions, self.scatter_radius.value())
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
        return {dot_id: new_positions[index] for index, dot_id in enumerate(ids)}

    def formation_handles(self, tool: EditorTool) -> dict[str, tuple[float, float]]:
        _ids, positions = self.selected_positions()
        if len(positions) < 2:
            return {}
        center_x = sum(x for x, _y in positions) / len(positions)
        center_y = sum(y for _x, y in positions) / len(positions)
        if tool == EditorTool.LINE:
            if len(self.line_endpoints) != 2:
                self.line_endpoints = [positions[0], positions[-1]]
            return {
                "line_start": self.line_endpoints[0],
                "line_end": self.line_endpoints[1],
            }
        if tool == EditorTool.CURVE:
            return {"curve_bend": (center_x, center_y + self.curve_bend.value())}
        if tool == EditorTool.ARC:
            return {
                "arc_radius": (center_x, center_y + self.arc_radius.value()),
                "arc_sweep": (center_x + self.arc_radius.value(), center_y),
            }
        if tool == EditorTool.SHAPE_LINE:
            ids, positions = self.selected_positions()
            return {
                f"shape_anchor:{dot_id}": anchor
                for dot_id, anchor in self.current_shape_line_anchor_items(ids, positions)
            }
        if tool == EditorTool.SCATTER:
            return {"scatter_radius": (center_x + self.scatter_radius.value(), center_y)}
        if tool == EditorTool.MIRROR:
            return {"mirror_axis": (self.mirror_axis, center_y)}
        return {}

    def update_formation_preview(self) -> None:
        if self.field.active_tool == EditorTool.SELECT:
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
        starts = {dot_id: self.current_set().dot_positions[dot_id] for dot_id in targets}
        self.field.show_preview(starts, targets, self.formation_handles(self.field.active_tool))

    def preview_handle_moved(self, kind: str, x: float, y: float) -> None:
        _ids, positions = self.selected_positions()
        if len(positions) < 2:
            return
        center_x = sum(pos_x for pos_x, _pos_y in positions) / len(positions)
        center_y = sum(pos_y for _pos_x, pos_y in positions) / len(positions)
        if kind == "curve_bend":
            self.curve_bend.setValue(y - center_y)
        elif kind == "line_start":
            if len(self.line_endpoints) != 2:
                self.line_endpoints = [positions[0], positions[-1]]
            self.line_endpoints[0] = (x, y)
        elif kind == "line_end":
            if len(self.line_endpoints) != 2:
                self.line_endpoints = [positions[0], positions[-1]]
            self.line_endpoints[1] = (x, y)
        elif kind == "arc_radius":
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            self.arc_radius.setValue(max(1, distance))
        elif kind == "arc_sweep":
            distance = abs(x - center_x)
            radius = max(1, self.arc_radius.value())
            self.arc_sweep.setValue(max(10, min(360, distance / radius * 180)))
        elif kind.startswith("shape_anchor:"):
            dot_id = kind.split(":", 1)[1]
            self.shape_line_anchor_positions[dot_id] = (x, y)
        elif kind == "scatter_radius":
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            self.scatter_radius.setValue(max(0, distance))
        elif kind == "mirror_axis":
            self.mirror_axis = x
        self.update_formation_preview()

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
        self.set_tool(EditorTool.SELECT)
        self.field.clear_preview()

    def apply_current_preview(self) -> None:
        self.apply_formation(self.field.active_tool)

    def apply_formation(self, tool: EditorTool) -> None:
        targets = self.formation_targets(tool)
        if not targets:
            return
        after = self.current_positions()
        after.update(targets)
        self.undo_stack.push(MoveDotsCommand(self, self.set_index, self.current_positions(), after, f"Apply {tool.value.title()}"))
        self.field.clear_preview()
        self.set_tool(EditorTool.SELECT)
        self.refresh_selected_paths()

    def context_action(self, name: str) -> None:
        mapping = {
            "Preview Line": EditorTool.LINE,
            "Preview Curve": EditorTool.CURVE,
            "Preview Arc": EditorTool.ARC,
            "Preview Scatter": EditorTool.SCATTER,
            "Preview Mirror": EditorTool.MIRROR,
            "Preview Shape Line": EditorTool.SHAPE_LINE,
        }
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

    def populate_sets(self) -> None:
        self.set_list.blockSignals(True)
        self.set_list.clear()
        for drill_set in self.project.sets:
            tempo = drill_set.tempo or self.project.metadata.initial_tempo
            self.set_list.addItem(
                f"{drill_set.name} ({drill_set.start_count}-{drill_set.end_count}, {tempo:g} BPM)"
            )
        self.set_list.setCurrentRow(self.set_index)
        self.set_list.blockSignals(False)

    def change_set(self, index: int) -> None:
        if index < 0:
            return
        self.set_index = index
        self.current_count = self.current_set().start_count
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=True)
        self.sync_inspector()

    def add_set(self) -> None:
        previous = self.project.sets[-1]
        start = previous.end_count + 1
        drill_set = DrillSet(
            name=f"Set {len(self.project.sets) + 1}",
            start_count=start,
            end_count=start + self.project.metadata.default_counts_per_set - 1,
            tempo=self.project.metadata.initial_tempo,
            dot_positions=dict(previous.dot_positions),
        )
        self.project.sets.append(drill_set)
        self.set_index = len(self.project.sets) - 1
        self.current_count = drill_set.start_count
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=True)

    def copy_set(self) -> None:
        source = self.current_set()
        copied = DrillSet(
            name=f"{source.name} Copy",
            start_count=source.end_count + 1,
            end_count=source.end_count + source.duration_counts,
            tempo=source.tempo,
            dot_positions=dict(source.dot_positions),
            transition=source.transition,
        )
        self.project.sets.insert(self.set_index + 1, copied)
        self.set_index += 1
        self.current_count = copied.start_count
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=True)

    def remove_set(self) -> None:
        if len(self.project.sets) <= 1:
            return
        self.project.sets.pop(self.set_index)
        self.set_index = max(0, self.set_index - 1)
        self.populate_sets()
        self.change_set(self.set_index)

    def update_transition(self, value: str) -> None:
        self.current_set().transition = Transition(value)

    def update_set_length(self, count_length: int) -> None:
        self.set_end_count.blockSignals(True)
        self.set_end_count.setValue(self.set_start_count.value() + count_length - 1)
        self.set_end_count.blockSignals(False)
        self.update_set_details()

    def update_set_details(self) -> None:
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
        if old_start != drill_set.start_count or old_end != drill_set.end_count:
            self.ripple_following_sets()
        self.current_count = max(drill_set.start_count, min(self.current_count, drill_set.end_count))
        self.populate_sets()
        self.sync_timeline()
        self.set_count(self.current_count, seek_audio=True)

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
        ):
            widget.blockSignals(True)
        self.set_name.setText(drill_set.name)
        self.set_start_count.setValue(drill_set.start_count)
        self.set_count_length.setValue(drill_set.duration_counts)
        self.set_end_count.setValue(drill_set.end_count)
        self.set_tempo.setValue(drill_set.tempo or 0)
        self.transition_combo.setCurrentText(drill_set.transition.value)
        for widget in (
            self.set_name,
            self.set_start_count,
            self.set_count_length,
            self.set_end_count,
            self.set_tempo,
            self.transition_combo,
        ):
            widget.blockSignals(False)

    def sync_timeline(self) -> None:
        drill_set = self.current_set()
        self.timeline.blockSignals(True)
        self.timeline.setRange(drill_set.start_count * 100, drill_set.end_count * 100)
        self.timeline.setValue(int(self.current_count * 100))
        self.timeline.blockSignals(False)
        self.sync_set_editor()
        self.count_label.setText(f"Count {self.current_count:.2f}")
        self.refresh_markers()

    def scrub(self, value: int) -> None:
        self.set_count(value / 100, seek_audio=True)

    def set_count(self, count: float, seek_audio: bool) -> None:
        drill_set = self.current_set()
        self.current_count = max(drill_set.start_count, min(count, drill_set.end_count))
        self.field.set_positions(interpolate_project(self.project, self.set_index, self.current_count))
        self.count_label.setText(f"Count {self.current_count:.2f}")
        self.timeline.blockSignals(True)
        self.timeline.setValue(int(self.current_count * 100))
        self.timeline.blockSignals(False)
        if seek_audio and self.player.source().isValid():
            self.player.setPosition(self.audio_position_for_count(self.set_index, self.current_count))
        self.refresh_selected_paths()

    def play(self) -> None:
        if self.player.source().isValid():
            self.player.setPosition(self.audio_position_for_count(self.set_index, self.current_count))
        self.play_timer.start()
        if self.player.source().isValid():
            self.player.play()
        self.refresh_selected_paths()

    def pause(self) -> None:
        self.play_timer.stop()
        self.player.pause()
        self.refresh_selected_paths()

    def tick_playback(self) -> None:
        if self.player.source().isValid():
            next_set_index, next_count = self.count_for_audio_position(self.player.position())
            if next_set_index != self.set_index:
                self.set_index = next_set_index
                self.current_count = next_count
                self.populate_sets()
                self.sync_timeline()
            else:
                self.current_count = next_count
            self.set_count(self.current_count, seek_audio=False)
            return

        tempo = self.project.active_tempo(self.set_index)
        self.current_count += (tempo / 60) * (self.play_timer.interval() / 1000)
        if self.current_count > self.current_set().end_count:
            if self.set_index + 1 < len(self.project.sets):
                self.change_set(self.set_index + 1)
            else:
                self.pause()
                self.current_count = self.current_set().end_count
        self.set_count(self.current_count, seek_audio=False)

    def audio_position_for_count(self, set_index: int, count: float) -> int:
        milliseconds = 0.0
        for index, drill_set in enumerate(self.project.sets):
            milliseconds_per_count = 60000 / self.project.active_tempo(index)
            if index == set_index:
                return int(milliseconds + max(0.0, count - drill_set.start_count) * milliseconds_per_count)
            milliseconds += drill_set.duration_counts * milliseconds_per_count
        return int(milliseconds)

    def count_for_audio_position(self, position_ms: int) -> tuple[int, float]:
        remaining = float(position_ms)
        for index, drill_set in enumerate(self.project.sets):
            milliseconds_per_count = 60000 / self.project.active_tempo(index)
            duration_ms = drill_set.duration_counts * milliseconds_per_count
            if remaining < duration_ms or index == len(self.project.sets) - 1:
                count = drill_set.start_count + remaining / milliseconds_per_count
                return index, min(count, drill_set.end_count)
            remaining -= duration_ms
        last_index = len(self.project.sets) - 1
        return last_index, self.project.sets[last_index].end_count

    def add_marker(self) -> None:
        self.project.markers.append(Marker(count=self.current_count, label=f"Hit {len(self.project.markers) + 1}"))
        self.refresh_markers()

    def refresh_markers(self) -> None:
        self.marker_table.setRowCount(len(self.project.markers))
        for row, marker in enumerate(self.project.markers):
            self.marker_table.setItem(row, 0, QTableWidgetItem(f"{marker.count:.2f}"))
            self.marker_table.setItem(row, 1, QTableWidgetItem(marker.label))

    def sync_inspector(self) -> None:
        ids = self.field.selected_dot_ids()
        self.selection_label.setText(f"{len(ids)} selected" if ids else "No selection")
        enabled = len(ids) == 1
        for widget in (self.dot_name, self.dot_section, self.dot_x, self.dot_y):
            widget.setEnabled(enabled)
        if not enabled:
            return
        dot = self.project.dot_by_id(ids[0])
        position = self.current_set().dot_positions.get(ids[0], (0, 0))
        if dot:
            self.dot_name.setText(dot.name)
            self.dot_section.setText(dot.section)
            self.dot_x.setText(f"{position[0]:.2f}")
            self.dot_y.setText(f"{position[1]:.2f}")

    def selection_changed(self, *_args) -> None:
        self.sync_inspector()
        self.update_formation_preview()
        self.refresh_selected_paths()

    def path_display_set_index(self) -> int | None:
        if self.play_timer.isActive():
            return self.set_index if self.set_index > 0 else None
        return self.set_index + 1 if self.set_index + 1 < len(self.project.sets) else None

    def refresh_selected_paths(self) -> None:
        selected = self.field.selected_dot_ids()
        target_index = self.path_display_set_index()
        if not selected or target_index is None:
            self.field.clear_paths()
            return

        target_set = self.project.sets[target_index]
        start_set = self.project.sets[target_index - 1] if target_index > 0 else target_set
        paths: dict[str, list[tuple[float, float]]] = {}
        anchors: dict[str, list[tuple[float, float]]] = {}
        for dot_id in selected:
            start = start_set.dot_positions.get(dot_id)
            end = target_set.dot_positions.get(dot_id)
            if start is None or end is None:
                continue
            dot_anchors = target_set.path_anchors.get(dot_id, [])
            paths[dot_id] = sample_transition_path(start, end, dot_anchors)
            anchors[dot_id] = dot_anchors
        self.field.show_paths(paths, anchors)

    def add_path_anchor(self, dot_id: str, x: float, y: float) -> None:
        target_index = self.path_display_set_index()
        if target_index is None:
            return
        self.project.sets[target_index].path_anchors.setdefault(dot_id, []).append((x, y))
        self.refresh_selected_paths()

    def move_path_anchor(self, dot_id: str, anchor_index: int, x: float, y: float) -> None:
        target_index = self.path_display_set_index()
        if target_index is None:
            return
        anchors = self.project.sets[target_index].path_anchors.setdefault(dot_id, [])
        if 0 <= anchor_index < len(anchors):
            anchors[anchor_index] = (x, y)
        self.refresh_selected_paths()

    def update_selected_dot(self) -> None:
        ids = self.field.selected_dot_ids()
        if len(ids) != 1:
            return
        dot = self.project.dot_by_id(ids[0])
        if dot:
            dot.name = self.dot_name.text()
            dot.section = self.dot_section.text()
            self.field.rebuild_dots()
            self.field.set_positions(self.current_set().dot_positions)

    def update_selected_dot_position(self) -> None:
        ids = self.field.selected_dot_ids()
        if len(ids) != 1:
            return
        try:
            x = float(self.dot_x.text())
            y = float(self.dot_y.text())
        except ValueError:
            return
        after = self.current_positions()
        after[ids[0]] = (x, y)
        self.apply_positions(after)

    def save(self) -> None:
        save_project(self.project_dir, self.project)
        self.statusBar().showMessage("Project saved", 2500)

    def save_as(self) -> None:
        title, accepted = QInputDialog.getText(
            self,
            "Save Project As",
            "Project title:",
            text=f"{self.project.metadata.show_title} Copy",
        )
        if not accepted or not title.strip():
            return

        self.save()
        target_dir = self.unique_project_dir(project_library_dir(), safe_folder_name(title))
        shutil.copytree(self.project_dir, target_dir)
        self.project_dir = target_dir
        self.project.metadata.show_title = title.strip()
        save_project(self.project_dir, self.project)
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
        self.save()
        self.return_home_requested.emit()

    def autosave(self) -> None:
        save_project(self.project_dir, self.project)
        self.statusBar().showMessage("Autosaved", 1500)

    def show_export_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Export")
        dialog.setModal(True)
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)

        title = QLabel("Choose Export Type")
        title.setStyleSheet("font-size: 18px; font-weight: 650;")
        layout.addWidget(title)

        mp4_button = QPushButton("MP4 Video")
        mp4_button.setToolTip("Render the full show animation synced with audio using ffmpeg.")
        pdf_button = QPushButton("Drill Sheet PDF")
        pdf_button.setToolTip("Create one landscape page per set with counts, tempo, and field image.")
        zip_button = QPushButton("Project Zip")
        zip_button.setToolTip("Package the project folder for backup or sharing.")
        ffmpeg_button = QPushButton("Set ffmpeg.exe")
        ffmpeg_button.setToolTip("Choose a local ffmpeg executable for MP4 export.")

        for button in (mp4_button, pdf_button, zip_button):
            button.setMinimumHeight(42)
            layout.addWidget(button)

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
        zip_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_zip))
        ffmpeg_button.clicked.connect(self.choose_ffmpeg_exe)
        dialog.exec()

    def accept_export_choice(self, dialog: QDialog, callback) -> None:
        dialog.accept()
        callback()

    def export_zip(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Project", str(self.project_dir) + ".zip", "Zip (*.zip)")
        if not path:
            return
        export_project_zip(self.project_dir, Path(path), self.project)
        self.statusBar().showMessage("Project zip exported", 3000)

    def export_drill_sheet_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Drill Sheet PDF",
            str(self.project_dir / "drill_sheet.pdf"),
            "PDF (*.pdf)",
        )
        if not path:
            return

        progress = QProgressDialog("Preparing drill sheet PDF...", None, 0, max(1, len(self.project.sets)), self)
        progress.setWindowTitle("Exporting Drill Sheet PDF")
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

        try:
            export_drill_sheet_pdf(Path(path), self.project, progress_callback=update_progress)
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))
            return
        finally:
            progress.close()
        self.statusBar().showMessage("Drill sheet PDF exported", 3000)

    def export_video(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export MP4", str(self.project_dir / "show.mp4"), "MP4 (*.mp4)")
        if not path:
            return
        ffmpeg_path = self.resolve_ffmpeg_path()
        if not ffmpeg_path:
            QMessageBox.warning(self, "Export Failed", "Select ffmpeg.exe first.")
            return
        previous_set_index = self.set_index
        previous_count = self.current_count
        progress = QProgressDialog("Preparing MP4 export...", "Cancel", 0, 100, self)
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

        try:
            export_mp4(
                self.field,
                self.project_dir,
                Path(path),
                self.project,
                ffmpeg_path=ffmpeg_path,
                progress_callback=update_progress,
                cancel_callback=progress.wasCanceled,
            )
        except ExportCancelled:
            self.statusBar().showMessage("MP4 export cancelled", 3000)
            return
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))
            return
        finally:
            progress.close()
            self.set_index = min(previous_set_index, len(self.project.sets) - 1)
            self.populate_sets()
            self.sync_timeline()
            self.set_count(previous_count, seek_audio=False)
        self.statusBar().showMessage("MP4 exported", 3000)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.save()
        super().closeEvent(event)
