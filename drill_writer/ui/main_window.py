from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QSettings, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPixmap, QUndoCommand, QUndoStack
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QApplication,
    QPushButton,
    QProgressDialog,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QToolBar,
    QWidget,
)

from drill_writer.core.analysis import auto_plan_paths, detect_path_warnings, segments_intersect
from drill_writer.core.animation import interpolate_project, interpolate_props, sample_transition_path
from drill_writer.core.coordinates import format_drill_coordinate
from drill_writer.core.models import AudioVersion, Dot, DotConstraint, DrillProject, DrillSet, Marker, MovementStyle, Prop, TimingEvent, Transition, prop_default_state
from drill_writer.core.project_io import load_project, project_library_dir, safe_folder_name, save_project
from drill_writer.core.svg_import import load_svg_contours
from drill_writer.core.timing import (
    active_audio_version,
    audio_ms_for_set_count,
    describe_timing_event,
    playback_bounds_for_set,
    set_active_audio_version,
    set_count_for_audio_ms,
    set_index_for_count,
)
from drill_writer.core.tools import (
    arc_positions,
    block_positions,
    circle_positions,
    centered_positions,
    conveyor_follow_positions,
    curve_positions,
    line_positions,
    mirror_positions,
    positions_along_path,
    positions_along_paths,
    rectangle_positions,
    rotate_positions,
    sampled_shape_path,
    scatter_positions,
    scaled_positions_to_size,
    spiral_positions,
    distance,
)
from drill_writer.resources import app_icon_path
from drill_writer.export.exporters import (
    ExportCancelled,
    export_coordinate_csv,
    export_dot_book_pdf,
    export_drill_sheet_pdf,
    export_mp4,
    export_project_zip,
    export_staff_packet_pdf,
)
from drill_writer.ui.audio_devices import (
    AUDIO_OUTPUT_DEVICE_SETTING,
    DEFAULT_AUDIO_OUTPUT_DEVICE_ID,
    audio_device_id,
    audio_output_for_id,
    audio_output_label_for_id,
    normalize_audio_output_device_id,
)
from drill_writer.ui.field_view import EditorTool, FieldView
from drill_writer.ui.waveform import WaveformWidget


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
        self.command_actions: dict[str, QAction] = {}
        self.command_defaults: dict[str, str] = {}
        self.dock_widgets: dict[str, QDockWidget] = {}
        self.undo_stack = QUndoStack(self)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.requested_audio_output_device_id = ""
        self.applied_audio_output_physical_id = ""
        self.audio_device_refresh_timer = QTimer(self)
        self.audio_device_refresh_timer.setSingleShot(True)
        self.audio_device_refresh_timer.setInterval(700)
        self.audio_device_refresh_timer.timeout.connect(self.apply_saved_audio_output_device)
        self.media_devices = QMediaDevices(self)
        self.media_devices.audioOutputsChanged.connect(self.schedule_audio_output_refresh)
        self.player.setAudioOutput(self.audio_output)
        self.apply_saved_audio_output_device()
        self.player.durationChanged.connect(self.audio_duration_changed)
        self.player.positionChanged.connect(self.audio_position_changed)
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(16)
        self.play_timer.timeout.connect(self.tick_playback)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(8000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()

        self.setWindowTitle(f"Drill Pirate - {self.project.metadata.show_title}")
        self.setWindowIcon(QIcon(str(app_icon_path())))
        self.resize(1500, 900)
        self.field = FieldView()
        self.field.set_project(self.project, self.project_dir)
        self.field.selection_changed.connect(self.selection_changed)
        self.field.dot_moved.connect(self.dot_moved)
        self.field.dots_moved.connect(self.dots_moved)
        self.field.prop_moved.connect(self.prop_moved)
        self.field.props_moved.connect(self.props_moved)
        self.field.context_action.connect(self.context_action)
        self.field.preview_handle_moved.connect(self.preview_handle_moved)
        self.field.path_anchor_added.connect(self.add_path_anchor)
        self.field.path_anchor_moved.connect(self.move_path_anchor)
        self.field.path_tangent_moved.connect(self.move_path_tangent)
        self.field.shape_anchor_toggled.connect(self.toggle_shape_line_anchor)
        self.field.set_formation_callback(self.apply_formation)
        self.setCentralWidget(self.build_layout())
        self.build_menus()
        self.restore_ui_layout()
        self.refresh_audio_versions()
        self.refresh_timing_events()
        self.populate_sets()
        self.refresh_marcher_table()
        self.refresh_prop_table()
        self.refresh_visibility_filters()
        self.refresh_appearance_groups()
        self.refresh_constraints()
        self.sync_timeline()
        self.sync_inspector()
        self.load_audio()

    def build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        self.plugin_named_menus["File"] = file_menu
        save_action = self.menu_action("Save", self.save, QKeySequence.StandardKey.Save)
        save_as_action = self.menu_action("Save As", self.save_as, QKeySequence.StandardKey.SaveAs)
        export_action = self.menu_action("Export", self.show_export_dialog, QKeySequence("Ctrl+E"))
        home_action = self.menu_action("Return to Home Screen", self.return_home)
        file_menu.addActions([save_action, save_as_action, export_action])
        file_menu.addSeparator()
        file_menu.addAction(home_action)

        edit_menu = self.menuBar().addMenu("Edit")
        self.plugin_named_menus["Edit"] = edit_menu
        edit_menu.addAction(self.menu_action("Undo", self.undo_stack.undo, QKeySequence.StandardKey.Undo))
        edit_menu.addAction(self.menu_action("Redo", self.undo_stack.redo, QKeySequence.StandardKey.Redo))
        edit_menu.addSeparator()
        edit_menu.addAction(self.menu_action("Command Palette", self.show_command_palette, QKeySequence("Ctrl+Shift+P")))
        edit_menu.addAction(self.menu_action("Keyboard Shortcuts", self.show_shortcut_editor, QKeySequence("Ctrl+Alt+,")))

        playback_menu = self.menuBar().addMenu("Playback")
        self.plugin_named_menus["Playback"] = playback_menu
        playback_menu.addAction(self.menu_action("Play/Pause", self.toggle_playback, Qt.Key.Key_Space))
        playback_menu.addAction(self.menu_action("Pause", self.pause))
        playback_menu.addAction(self.menu_action("Toggle Loop Current Set", self.toggle_loop_current_set, QKeySequence("Ctrl+L")))
        playback_menu.addAction(self.menu_action("Go To Count", self.focus_count_finder, QKeySequence("Ctrl+G")))

        settings_menu = self.menuBar().addMenu("Settings")
        self.plugin_named_menus["Settings"] = settings_menu
        settings_menu.addAction(self.menu_action("Preferences", self.open_preferences, QKeySequence("Ctrl+,")))

        view_menu = self.menuBar().addMenu("View")
        self.plugin_named_menus["View"] = view_menu
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
        ):
            workspace_menu.addAction(
                self.menu_action(
                    label,
                    lambda _checked=False, name=workspace_name: self.apply_workspace(name),
                    QKeySequence(shortcut),
                )
            )
        workspace_menu.addSeparator()
        workspace_menu.addAction(self.menu_action("Reset Panels", self.reset_panel_layout))

        tools_menu = self.menuBar().addMenu("Tools")
        self.plugin_named_menus["Tools"] = tools_menu
        add_marcher_action = self.menu_action("Add Marcher", self.add_marcher, QKeySequence("Ctrl+M"))
        delete_marcher_action = self.menu_action("Delete Selected", self.delete_selected_marchers, QKeySequence("Del"))
        import_prop_action = self.menu_action("Import Prop Image", self.import_prop_image, QKeySequence("Ctrl+Alt+I"))
        add_set_action = self.menu_action("Add Set", self.add_set, QKeySequence("Ctrl+Alt+S"))
        remove_set_action = self.menu_action("Remove Set", self.remove_set, QKeySequence("Ctrl+Alt+Backspace"))
        tools_menu.addActions(
            [add_marcher_action, delete_marcher_action, import_prop_action, add_set_action, remove_set_action]
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
            ("Scale Form Tool", EditorTool.SCALE, "Ctrl+Alt+X"),
            ("Spiral Tool", EditorTool.SPIRAL, "Ctrl+Alt+P"),
            ("Block/Grid Tool", EditorTool.BLOCK, "Ctrl+Alt+B"),
            ("SVG Shape Tool", EditorTool.SVG_SHAPE, "Ctrl+Alt+V"),
        )
        tool_actions: list[QAction] = []
        for label, tool, shortcut in tool_shortcuts:
            action = self.menu_action(label, lambda _checked=False, selected=tool: self.set_tool(selected), QKeySequence(shortcut))
            tools_menu.addAction(action)
            tool_actions.append(action)
        tools_menu.addSeparator()
        snap_action = self.menu_action("Toggle Snap Align", self.toggle_snap_align, QKeySequence("Ctrl+Alt+N"))
        analyze_action = self.menu_action("Analyze Paths", self.analyze_paths, QKeySequence("Ctrl+Alt+A"))
        plan_action = self.menu_action("Auto Plan Selected Paths", self.auto_plan_selected_paths, QKeySequence("Ctrl+Alt+R"))
        clear_paths_action = self.menu_action("Clear Selected Paths", self.clear_selected_paths, QKeySequence("Ctrl+Alt+Shift+R"))
        keyframe_action = self.menu_action("Set Count Keyframe", self.add_micro_keyframe, QKeySequence("Ctrl+Alt+K"))
        follow_action = self.menu_action("Follow-Leader Conveyor", self.follow_leader_rotate, QKeySequence("Ctrl+Alt+F"))
        fit_prop_action = self.menu_action("Fit Form to Selected Prop", self.fit_selected_form_to_prop, QKeySequence("Ctrl+Alt+Shift+X"))
        tools_menu.addActions([snap_action, analyze_action, plan_action, clear_paths_action, keyframe_action, follow_action, fit_prop_action])
        self.addActions(
            [
                add_marcher_action,
                delete_marcher_action,
                import_prop_action,
                add_set_action,
                remove_set_action,
                *tool_actions,
                snap_action,
                analyze_action,
                plan_action,
                clear_paths_action,
                keyframe_action,
                follow_action,
                fit_prop_action,
            ]
        )
        self.plugin_tools_menu = self.menuBar().addMenu("Plugin Tools")
        self.plugin_named_menus["Plugin Tools"] = self.plugin_tools_menu
        self.build_workspace_toolbar()

    def menu_action(self, text: str, callback, shortcut=None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(callback)
        command_id = self.unique_command_id(text)
        default_shortcut = self.shortcut_text(shortcut)
        action.setProperty("command_id", command_id)
        action.setProperty("default_shortcut", default_shortcut)
        self.command_actions[command_id] = action
        self.command_defaults[command_id] = default_shortcut
        saved_shortcut = self.settings.value(f"shortcuts/{command_id}", None)
        if saved_shortcut is not None:
            action.setShortcut(QKeySequence(str(saved_shortcut)))
        elif shortcut:
            action.setShortcut(shortcut)
        return action

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
        table.setColumnWidth(1, 190)
        table.setMinimumWidth(620)

    def show_command_palette(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Command Palette")
        dialog.resize(760, 500)
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
        dialog.resize(800, 560)
        layout = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText("Search commands...")
        table = QTableWidget(0, 2)
        self.configure_command_table(table)
        sequence_editor = QKeySequenceEdit()
        if hasattr(sequence_editor, "setClearButtonEnabled"):
            sequence_editor.setClearButtonEnabled(True)
        button_row = QHBoxLayout()
        apply_button = QPushButton("Apply Shortcut")
        clear_button = QPushButton("Clear")
        reset_button = QPushButton("Reset Selected")
        reset_all_button = QPushButton("Reset All")
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        for button in (apply_button, clear_button, reset_button, reset_all_button):
            button_row.addWidget(button)
        button_row.addStretch()
        button_row.addWidget(close_button)
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
            action.setShortcut(shortcut)
            if persist:
                self.settings.setValue(
                    f"shortcuts/{command_id}",
                    shortcut.toString(QKeySequence.SequenceFormat.PortableText),
                )
            self.settings.sync()
            refresh()

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

    def apply_audio_output_device(self, device_id: str, show_status: bool = True) -> None:
        normalized = normalize_audio_output_device_id(device_id)
        device = audio_output_for_id(normalized)
        if device.isNull():
            if show_status:
                self.statusBar().showMessage("No audio output devices available", 3000)
            return

        target_physical_id = audio_device_id(device)
        current_device = self.audio_output.device()
        current_physical_id = "" if current_device.isNull() else audio_device_id(current_device)
        already_requested = self.requested_audio_output_device_id == normalized
        already_on_target = (
            current_physical_id == target_physical_id
            and self.applied_audio_output_physical_id == target_physical_id
        )
        if already_requested and already_on_target:
            if show_status:
                self.statusBar().showMessage(f"Audio output: {audio_output_label_for_id(normalized)}", 3000)
            return
        if current_physical_id == target_physical_id:
            self.requested_audio_output_device_id = normalized
            self.applied_audio_output_physical_id = target_physical_id
            if show_status:
                self.statusBar().showMessage(f"Audio output: {audio_output_label_for_id(normalized)}", 3000)
            return

        was_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        position = self.player.position()
        if was_playing:
            self.player.pause()
        self.audio_output.setDevice(device)
        self.requested_audio_output_device_id = normalized
        self.applied_audio_output_physical_id = target_physical_id
        if self.player.source().isValid():
            self.player.setPosition(position)
        if was_playing:
            QTimer.singleShot(80, self.player.play)
        if show_status:
            self.statusBar().showMessage(f"Audio output: {audio_output_label_for_id(normalized)}", 3000)

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
        button.setToolTip(tooltip or f"Plugin form tool from {plugin_id}")
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
        action.setToolTip(tooltip)
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
                widget.setParent(None)
                widget.deleteLater()
                self.plugin_contribution_widgets[tool.plugin_id].remove(widget)
        self.plugin_form_tool_buttons.pop(tool_id, None)
        for widget in self.plugin_form_tool_setting_widgets.pop(tool_id, {}).values():
            widget.deleteLater()
        for menu, action in list(self.plugin_contribution_actions.get(tool.plugin_id, [])):
            if action.text() == tool.name:
                menu.removeAction(action)
                self.removeAction(action)
                command_id = action.property("command_id")
                if command_id:
                    self.command_actions.pop(str(command_id), None)
                    self.command_defaults.pop(str(command_id), None)
                action.deleteLater()
                self.plugin_contribution_actions[tool.plugin_id].remove((menu, action))
        self.plugin_form_tool_group.setVisible(bool(self.plugin_form_tools))

    def activate_plugin_form_tool(self, tool_id: str) -> None:
        tool = self.plugin_form_tools.get(tool_id)
        if tool is None:
            return
        self.active_plugin_form_tool_id = tool_id
        self.field.set_tool(EditorTool.PLUGIN_FORM)
        for button_tool_id, button in self.plugin_form_tool_buttons.items():
            button.setChecked(button_tool_id == tool_id)
        for button in self.tool_buttons.values():
            button.setChecked(False)
        self.rebuild_plugin_tool_options(tool)
        self.update_tool_edit_visibility()
        self.update_formation_preview()

    def apply_plugin_form_tool(self, tool_id: str) -> None:
        self.activate_plugin_form_tool(tool_id)

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
            QMessageBox.warning(self, "Plugin Tool Failed", f"{tool.name} failed:\n{exc}")
            return
        targets = self.normalize_plugin_targets(ids, result)
        if not targets:
            return
        self.apply_plugin_targets(tool.name, targets)
        self.active_plugin_form_tool_id = ""
        self.field.clear_preview()
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
            targets = {}
            for dot_id, position in zip(ids, result):
                if not isinstance(position, (tuple, list)) or len(position) < 2:
                    return {}
                targets[dot_id] = (float(position[0]), float(position[1]))
            return targets
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
        button.setToolTip(tooltip)
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
                action.deleteLater()
            for widget in self.plugin_contribution_widgets.pop(current_plugin_id, []):
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
            "Library / Tools",
            self.scroll_panel(self.build_tools_panel(), 245),
            Qt.DockWidgetArea.LeftDockWidgetArea,
            minimum_width=245,
        )
        self.create_dock(
            "inspector",
            "Inspector",
            self.scroll_panel(self.build_inspector_panel(), 285),
            Qt.DockWidgetArea.RightDockWidgetArea,
            minimum_width=285,
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
            [270, 320],
            Qt.Orientation.Horizontal,
        )
        self.resizeDocks([self.dock_widgets["timeline"]], [210], Qt.Orientation.Vertical)
        return self.field

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
        toolbar = QToolBar("Workspaces", self)
        toolbar.setObjectName("WorkspaceToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        for workspace_name, label in (
            ("design", "Design"),
            ("forms", "Forms"),
            ("rehearse", "Rehearse"),
            ("print", "Print"),
            ("focus", "Focus"),
        ):
            toolbar.addAction(
                self.menu_action(
                    label,
                    lambda _checked=False, name=workspace_name: self.apply_workspace(name),
                )
            )
        toolbar.addSeparator()
        toolbar.addAction(self.command_actions["command_palette"])

    def restore_ui_layout(self) -> None:
        state = self.settings.value("main_window/dock_state")
        if state:
            self.restoreState(state)

    def reset_panel_layout(self) -> None:
        self.settings.remove("main_window/dock_state")
        for dock in self.dock_widgets.values():
            dock.setFloating(False)
            dock.show()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_widgets["tools"])
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_widgets["inspector"])
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock_widgets["timeline"])
        self.apply_workspace("design")
        self.statusBar().showMessage("Panel layout reset", 2200)

    def apply_workspace(self, name: str) -> None:
        for dock in self.dock_widgets.values():
            dock.show()
        if name == "focus":
            for dock in self.dock_widgets.values():
                dock.hide()
            self.statusBar().showMessage("Focus workspace: field only", 2200)
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
        self.statusBar().showMessage(f"{name.title()} workspace applied", 2200)

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
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        tabs = QTabWidget()
        tabs.setObjectName("SideTabs")
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(True)
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
        search_row = QHBoxLayout()
        self.marcher_search = QLineEdit()
        self.marcher_search.setPlaceholderText("Search name, section, instrument, rank...")
        self.marcher_search.textChanged.connect(self.filter_marcher_table)
        select_visible_button = QPushButton("Select")
        select_visible_button.setToolTip("Select all visible marchers from the current search.")
        select_visible_button.clicked.connect(self.select_visible_marchers)
        clear_search_button = QPushButton("Clear")
        clear_search_button.clicked.connect(self.marcher_search.clear)
        search_row.addWidget(self.marcher_search, 1)
        search_row.addWidget(select_visible_button)
        search_row.addWidget(clear_search_button)
        marchers_layout.addLayout(search_row)
        self.marcher_table = QTableWidget(0, 4)
        self.marcher_table.setHorizontalHeaderLabels(["", "#", "Section", "Name"])
        self.marcher_table.verticalHeader().setVisible(False)
        self.marcher_table.verticalHeader().setDefaultSectionSize(20)
        self.marcher_table.setAlternatingRowColors(True)
        self.marcher_table.setShowGrid(False)
        self.marcher_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.marcher_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.marcher_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.marcher_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.marcher_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.marcher_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.marcher_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.marcher_table.setColumnWidth(0, 18)
        self.marcher_table.cellClicked.connect(self.select_marcher_from_table)
        marchers_layout.addWidget(self.marcher_table, 1)
        tabs.addTab(marchers_tab, "Marchers")

        props_tab = QWidget()
        self.props_tab = props_tab
        props_layout = QVBoxLayout(props_tab)
        props_layout.setContentsMargins(4, 4, 4, 4)
        props_header = QHBoxLayout()
        props_title = QLabel("Props")
        props_title.setStyleSheet("font-size: 14px; font-weight: 750;")
        import_prop_button = QPushButton("Import")
        import_prop_button.clicked.connect(self.import_prop_image)
        delete_prop_button = QPushButton("Delete")
        delete_prop_button.clicked.connect(self.delete_selected_props)
        props_header.addWidget(props_title)
        props_header.addStretch()
        props_header.addWidget(import_prop_button)
        props_header.addWidget(delete_prop_button)
        props_layout.addLayout(props_header)
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

        formation_tab = QWidget()
        self.formation_tab = formation_tab
        formation_layout = QVBoxLayout(formation_tab)
        formation_layout.setContentsMargins(4, 4, 4, 4)
        group = QGroupBox("Formation Tools")
        tools_layout = QGridLayout(group)
        tools_layout.setSpacing(4)
        self.tool_buttons: dict[EditorTool, QPushButton] = {}
        for index, (tool, label) in enumerate((
            (EditorTool.SELECT, "Select"),
            (EditorTool.LINE, "Line"),
            (EditorTool.CURVE, "Curve"),
            (EditorTool.ARC, "Arc"),
            (EditorTool.CIRCLE, "Circle"),
            (EditorTool.RECTANGLE, "Rectangle"),
            (EditorTool.SPIRAL, "Spiral"),
            (EditorTool.BLOCK, "Block/Grid"),
            (EditorTool.SCALE, "Scale Form"),
            (EditorTool.SVG_SHAPE, "SVG Shape"),
            (EditorTool.LASSO, "Lasso Select"),
            (EditorTool.SCATTER, "Scatter"),
            (EditorTool.MIRROR, "Mirror"),
            (EditorTool.SHAPE_LINE, "Shape Line"),
        )):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, selected=tool: self.set_tool(selected))
            tools_layout.addWidget(button, index // 2, index % 2)
            self.tool_buttons[tool] = button
        formation_layout.addWidget(group)

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
        svg_layout.addWidget(self.svg_shape_label)
        svg_layout.addWidget(import_svg_button)

        self.shape_tool_group = QGroupBox("Shape")
        shape_form = QFormLayout(self.shape_tool_group)
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

        self.rotate_tool_group = QGroupBox("Rotate")
        rotate_form = QFormLayout(self.rotate_tool_group)
        self.rotation_degrees = QDoubleSpinBox()
        self.rotation_degrees.setRange(-360, 360)
        self.rotation_degrees.setValue(15)
        self.rotation_degrees.setSuffix(" deg")
        rotate_form.addRow("Degrees / Conveyor Shift", self.rotation_degrees)
        follow_button = QPushButton("Follow-Leader Conveyor")
        follow_button.clicked.connect(self.follow_leader_rotate)
        rotate_form.addRow(follow_button)
        for editor in (
            self.curve_bend,
            self.arc_radius,
            self.arc_sweep,
            self.scatter_radius,
            self.scatter_spacing,
            self.rotation_degrees,
            self.shape_radius,
            self.shape_width,
            self.shape_height,
            self.spiral_turns,
            self.block_columns,
            self.block_spacing,
            self.scale_width,
            self.scale_height,
            self.scale_fit_padding,
        ):
            editor.valueChanged.connect(self.update_formation_preview)
        self.scale_lock_aspect.toggled.connect(self.update_formation_preview)
        apply_button = QPushButton("Apply Preview")
        apply_button.clicked.connect(self.apply_current_preview)
        clear_button = QPushButton("Clear Preview")
        clear_button.clicked.connect(self.clear_formation_preview)
        rotate_button = QPushButton("Rotate Selection")
        rotate_button.clicked.connect(self.rotate_selection)
        for group_widget in (
            self.plugin_tool_group,
            self.line_tool_group,
            self.curve_tool_group,
            self.arc_tool_group,
            self.scatter_tool_group,
            self.mirror_tool_group,
            self.shape_line_tool_group,
            self.svg_tool_group,
            self.shape_tool_group,
            self.scale_tool_group,
            self.rotate_tool_group,
        ):
            edit_layout.addWidget(group_widget)
        apply_row = QHBoxLayout()
        apply_row.addWidget(apply_button)
        apply_row.addWidget(clear_button)
        edit_layout.addLayout(apply_row)
        edit_layout.addWidget(rotate_button)
        formation_layout.addWidget(self.tool_edit_group)
        formation_layout.addStretch()
        tabs.addTab(formation_tab, "Form")

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
        normalize_button = QPushButton("Normalize Selected Interval")
        normalize_button.clicked.connect(self.normalize_selected_interval)
        constraint_button = QPushButton("Create Line Constraint")
        constraint_button.clicked.connect(self.create_line_constraint)
        apply_constraints_button = QPushButton("Apply Constraints")
        apply_constraints_button.clicked.connect(self.apply_constraints)
        self.constraint_list = QListWidget()
        interval_form.addRow(normalize_button)
        interval_form.addRow(constraint_button)
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
        auto_plan_button = QPushButton("Auto Plan Selected Paths")
        auto_plan_button.clicked.connect(self.auto_plan_selected_paths)
        clear_paths_button = QPushButton("Clear Selected Paths")
        clear_paths_button.clicked.connect(self.clear_selected_paths)
        self.warning_list = QListWidget()
        analysis_form.addRow("Min Spacing", self.min_spacing)
        analysis_form.addRow("Max Speed", self.max_yards_per_count)
        analysis_form.addRow(analyze_button)
        analysis_form.addRow(auto_plan_button)
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
        clear_keyframe_button = QPushButton("Clear Count Keyframe")
        clear_keyframe_button.clicked.connect(self.clear_micro_keyframe)
        beat_markers_button = QPushButton("Mark Every Count In Set")
        beat_markers_button.clicked.connect(self.add_count_markers_for_set)
        auto_hit_button = QPushButton("Auto Detect Hit Markers")
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
        apply_movement_button = QPushButton("Apply To Selected Marchers")
        apply_movement_button.clicked.connect(self.apply_movement_style_to_selected)
        clear_movement_button = QPushButton("Clear Selected Style")
        clear_movement_button.clicked.connect(self.clear_movement_style_for_selected)
        self.movement_style_status = QLabel("Select marchers to set style for this set.")
        self.movement_style_status.setWordWrap(True)
        movement_form.addRow("Style", self.movement_style_combo)
        movement_form.addRow(apply_movement_button)
        movement_form.addRow(clear_movement_button)
        movement_form.addRow("", self.movement_style_status)
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
        ghost = QCheckBox("Ghost Previous Set")
        ghost.setChecked(True)
        self.snap_align = QCheckBox("Snap Align")
        self.snap_align.toggled.connect(self.field.set_snap_enabled)
        view_layout.addWidget(labels)
        view_layout.addWidget(ghost)
        view_layout.addWidget(self.snap_align)
        view_tab = QWidget()
        self.view_tab = view_tab
        view_tab_layout = QVBoxLayout(view_tab)
        view_tab_layout.addWidget(view_group)
        view_tab_layout.addStretch()
        tabs.addTab(view_tab, "View")
        self.set_tool(EditorTool.SELECT)
        return panel

    def build_inspector_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        tabs = QTabWidget()
        tabs.setObjectName("SideTabs")
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(True)
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
        visibility_layout.addStretch()
        tabs.addTab(visibility_tab, "Visibility")
        return panel

    def build_timeline_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.waveform = WaveformWidget()
        self.waveform.set_project(self.project)
        self.waveform.position_selected.connect(self.seek_audio_position)
        layout.addWidget(self.waveform)
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
        if hasattr(self, "waveform") and self.waveform.samples:
            self.statusBar().showMessage("Audio waveform reloaded", 2200)
        elif hasattr(self, "waveform") and self.waveform.load_error:
            self.statusBar().showMessage(self.waveform.load_error, 4000)

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
        if tool != EditorTool.PLUGIN_FORM:
            self.active_plugin_form_tool_id = ""
            for button in self.plugin_form_tool_buttons.values():
                button.setChecked(False)
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
        elif tool == EditorTool.SCALE and positions:
            self.initialize_scale_tool(positions)
        self.update_formation_preview()

    def update_tool_edit_visibility(self) -> None:
        tool = self.field.active_tool
        plugin_active = bool(self.active_plugin_form_tool_id)
        self.tool_edit_group.setVisible(tool != EditorTool.SELECT or plugin_active)
        self.plugin_tool_group.setVisible(plugin_active)
        self.line_tool_group.setVisible(tool == EditorTool.LINE)
        self.curve_tool_group.setVisible(tool == EditorTool.CURVE)
        self.arc_tool_group.setVisible(tool == EditorTool.ARC)
        self.scatter_tool_group.setVisible(tool == EditorTool.SCATTER)
        self.mirror_tool_group.setVisible(tool == EditorTool.MIRROR)
        self.shape_line_tool_group.setVisible(tool == EditorTool.SHAPE_LINE)
        self.svg_tool_group.setVisible(tool == EditorTool.SVG_SHAPE)
        self.shape_tool_group.setVisible(
            tool in (EditorTool.CIRCLE, EditorTool.RECTANGLE, EditorTool.SPIRAL, EditorTool.BLOCK, EditorTool.SVG_SHAPE)
        )
        self.scale_tool_group.setVisible(tool == EditorTool.SCALE)
        self.rotate_tool_group.setVisible(False)

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

    def current_set(self) -> DrillSet:
        return self.project.sets[self.set_index]

    def current_positions(self) -> dict[str, tuple[float, float]]:
        return dict(self.current_set().dot_positions)

    def current_prop_states(self) -> dict[str, dict[str, float]]:
        return {prop_id: dict(state) for prop_id, state in self.current_set().prop_positions.items()}

    def current_transition_start_positions(self) -> dict[str, tuple[float, float]]:
        if self.set_index > 0:
            return self.project.sets[self.set_index - 1].dot_positions
        return self.current_set().dot_positions

    def dot_moved(self, dot_id: str, x: float, y: float) -> None:
        if self.micro_edit_enabled.isChecked():
            self.store_micro_edit_positions({dot_id: (x, y)})
            return
        before = self.current_positions()
        after = dict(before)
        after[dot_id] = (x, y)
        self.undo_stack.push(MoveDotsCommand(self, self.set_index, before, after, "Move Dot"))

    def dots_moved(self, positions: dict[str, tuple[float, float]]) -> None:
        if self.micro_edit_enabled.isChecked():
            self.store_micro_edit_positions(positions)
            return
        before = self.current_positions()
        after = dict(before)
        after.update(positions)
        self.undo_stack.push(MoveDotsCommand(self, self.set_index, before, after, "Move Form"))

    def prop_moved(self, prop_id: str, state: dict[str, float]) -> None:
        before = self.current_prop_states()
        after = {key: dict(value) for key, value in before.items()}
        after[prop_id] = dict(state)
        self.undo_stack.push(MovePropsCommand(self, self.set_index, before, after, "Move Prop"))

    def props_moved(self, states: dict[str, dict[str, float]]) -> None:
        before = self.current_prop_states()
        after = {key: dict(value) for key, value in before.items()}
        for prop_id, state in states.items():
            after[prop_id] = dict(state)
        self.undo_stack.push(MovePropsCommand(self, self.set_index, before, after, "Move Props"))

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
        self.field.set_prop_states(self.current_set().prop_positions)
        self.field.dot_items[dot_id].setSelected(True)
        self.refresh_marcher_table()
        self.refresh_visibility_filters()
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
                drill_set.path_controls.pop(dot_id, None)
                drill_set.count_positions.pop(dot_id, None)
        self.field.clear_preview()
        self.field.clear_paths()
        self.field.rebuild_dots()
        self.field.set_positions(self.current_set().dot_positions)
        self.field.set_prop_states(self.current_set().prop_positions)
        self.refresh_marcher_table()
        self.refresh_visibility_filters()
        self.refresh_constraints()
        self.sync_inspector()

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

    def delete_selected_props(self) -> None:
        selected = set(self.field.selected_prop_ids())
        if not selected:
            return
        self.project.props = [prop for prop in self.project.props if prop.id not in selected]
        for drill_set in self.project.sets:
            for prop_id in selected:
                drill_set.prop_positions.pop(prop_id, None)
        self.field.rebuild_props()
        self.field.set_prop_states(self.current_set().prop_positions)
        self.refresh_prop_table()
        self.refresh_visibility_filters()
        self.sync_inspector()

    def apply_prop_states(
        self,
        states: dict[str, dict[str, float]],
        push_undo: bool = True,
        set_index: int | None = None,
    ) -> None:
        target_set_index = self.set_index if set_index is None else set_index
        normalized = {prop_id: dict(state) for prop_id, state in states.items()}
        if push_undo:
            self.undo_stack.push(
                MovePropsCommand(
                    self,
                    target_set_index,
                    {prop_id: dict(state) for prop_id, state in self.project.sets[target_set_index].prop_positions.items()},
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
            self.field.set_prop_states(self.current_set().prop_positions)
            self.update_formation_preview()
            self.refresh_selected_paths()
            self.sync_inspector()

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
            return self.plugin_formation_targets()
        ids, positions = self.selected_positions()
        if len(ids) < 2 and tool not in (EditorTool.SCATTER, EditorTool.MIRROR):
            return {}
        if not ids:
            return {}
        center_x = sum(x for x, _y in positions) / len(positions)
        center_y = sum(y for _x, y in positions) / len(positions)
        if tool == EditorTool.LINE:
            if len(self.line_endpoints) != 2:
                self.line_endpoints = [positions[0], positions[-1]]
            new_positions = line_positions(len(ids), self.line_endpoints[0], self.line_endpoints[1])
        elif tool == EditorTool.CURVE:
            new_positions = curve_positions(positions, (center_x, center_y + self.curve_bend.value()), 0.85)
        elif tool == EditorTool.ARC:
            new_positions = arc_positions(
                len(ids),
                (center_x, center_y),
                self.arc_radius.value(),
                270 - self.arc_sweep.value() / 2,
                self.arc_sweep.value(),
            )
        elif tool == EditorTool.CIRCLE:
            new_positions = circle_positions(len(ids), (center_x, center_y), self.shape_radius.value())
        elif tool == EditorTool.RECTANGLE:
            new_positions = rectangle_positions(
                len(ids),
                (center_x, center_y),
                self.shape_width.value(),
                self.shape_height.value(),
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
                new_positions = positions_along_paths(scaled_contours, len(ids))
            else:
                scaled_path = [
                    (
                        center_x + point[0] * self.shape_width.value(),
                        center_y + point[1] * self.shape_height.value(),
                    )
                    for point in self.imported_shape_points
                ]
                new_positions = positions_along_path(scaled_path, len(ids))
        elif tool == EditorTool.SCALE:
            new_positions = scaled_positions_to_size(
                positions,
                self.scale_width.value(),
                self.scale_height.value(),
                self.scale_lock_aspect.isChecked(),
                (center_x, center_y),
            )
        elif tool == EditorTool.SCATTER:
            new_positions = scatter_positions(
                positions,
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
        preserve_order = tool in (EditorTool.SHAPE_LINE, EditorTool.SCALE)
        return self.assign_targets_to_marchers(ids, new_positions, preserve_order=preserve_order)

    def assign_targets_to_marchers(
        self,
        ids: list[str],
        targets: list[tuple[float, float]],
        preserve_order: bool = False,
    ) -> dict[str, tuple[float, float]]:
        if preserve_order or len(ids) != len(targets) or len(ids) <= 2:
            return {dot_id: targets[index] for index, dot_id in enumerate(ids)}
        starts_source = self.current_transition_start_positions()
        starts = {dot_id: starts_source.get(dot_id, self.current_set().dot_positions[dot_id]) for dot_id in ids}
        start_list = [starts[dot_id] for dot_id in ids]
        if len(ids) > 220:
            assignment_indexes = self.shortest_pair_target_assignment(start_list, targets)
        else:
            assignment_indexes = self.auction_target_assignment(start_list, targets)
        assignment = {dot_id: assignment_indexes[index] for index, dot_id in enumerate(ids)}

        swap_iterations = 5 if len(ids) <= 220 else 2
        use_crossing_penalty = len(ids) <= 220
        for _iteration in range(swap_iterations):
            changed = False
            for first_index, dot_a in enumerate(ids):
                for dot_b in ids[first_index + 1 :]:
                    target_a = targets[assignment[dot_a]]
                    target_b = targets[assignment[dot_b]]
                    current_cost = self.assignment_cost(starts[dot_a], target_a) + self.assignment_cost(starts[dot_b], target_b)
                    swapped_cost = self.assignment_cost(starts[dot_a], target_b) + self.assignment_cost(starts[dot_b], target_a)
                    crosses = (
                        use_crossing_penalty
                        and segments_intersect(starts[dot_a], target_a, starts[dot_b], target_b)
                    )
                    if swapped_cost + 0.01 < current_cost or (crosses and swapped_cost <= current_cost * 1.08 + 1.0):
                        assignment[dot_a], assignment[dot_b] = assignment[dot_b], assignment[dot_a]
                        changed = True
            if not changed:
                break
        return {dot_id: targets[assignment[dot_id]] for dot_id in ids}

    def assignment_cost(self, start: tuple[float, float], target: tuple[float, float]) -> float:
        move_distance = distance(start, target)
        return move_distance * move_distance + move_distance * 0.05

    def auction_target_assignment(
        self,
        starts: list[tuple[float, float]],
        targets: list[tuple[float, float]],
    ) -> list[int]:
        count = len(starts)
        costs = [
            [self.assignment_cost(start, target) for target in targets]
            for start in starts
        ]
        prices = [0.0] * count
        owners: list[int | None] = [None] * count
        assignment: list[int | None] = [None] * count
        unassigned = list(range(count))
        epsilon = 1 / max(10, count)
        iterations = 0
        max_iterations = max(1000, count * count * 4)

        while unassigned and iterations < max_iterations:
            iterations += 1
            marcher_index = unassigned.pop()
            best_target = 0
            best_value = float("-inf")
            second_value = float("-inf")
            row_costs = costs[marcher_index]
            for target_index, target_cost in enumerate(row_costs):
                value = -target_cost - prices[target_index]
                if value > best_value:
                    second_value = best_value
                    best_value = value
                    best_target = target_index
                elif value > second_value:
                    second_value = value
            if second_value == float("-inf"):
                second_value = best_value - epsilon
            bid = best_value - second_value + epsilon
            prices[best_target] += bid
            previous_owner = owners[best_target]
            owners[best_target] = marcher_index
            assignment[marcher_index] = best_target
            if previous_owner is not None:
                assignment[previous_owner] = None
                unassigned.append(previous_owner)

        if any(target_index is None for target_index in assignment):
            remaining_targets = {index for index in range(count) if index not in assignment}
            for marcher_index, target_index in enumerate(assignment):
                if target_index is None:
                    best_target = min(
                        remaining_targets,
                        key=lambda index: costs[marcher_index][index],
                    )
                    assignment[marcher_index] = best_target
                    remaining_targets.remove(best_target)
        return [int(target_index) for target_index in assignment]

    def shortest_pair_target_assignment(
        self,
        starts: list[tuple[float, float]],
        targets: list[tuple[float, float]],
    ) -> list[int]:
        pairs: list[tuple[float, int, int]] = []
        for marcher_index, start in enumerate(starts):
            for target_index, target in enumerate(targets):
                pairs.append((self.assignment_cost(start, target), marcher_index, target_index))
        pairs.sort(key=lambda item: item[0])

        assignment: list[int | None] = [None] * len(starts)
        used_marchers: set[int] = set()
        used_targets: set[int] = set()
        for _cost, marcher_index, target_index in pairs:
            if marcher_index in used_marchers or target_index in used_targets:
                continue
            assignment[marcher_index] = target_index
            used_marchers.add(marcher_index)
            used_targets.add(target_index)
            if len(used_marchers) == len(starts):
                break
        remaining_targets = [index for index in range(len(targets)) if index not in used_targets]
        for marcher_index, target_index in enumerate(assignment):
            if target_index is None:
                best_target = min(
                    remaining_targets,
                    key=lambda index: self.assignment_cost(starts[marcher_index], targets[index]),
                )
                assignment[marcher_index] = best_target
                remaining_targets.remove(best_target)
        return [int(target_index) for target_index in assignment]

    def formation_handles(self, tool: EditorTool) -> dict[str, tuple[float, float]]:
        if tool == EditorTool.PLUGIN_FORM:
            return self.plugin_formation_handles()
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
        if tool in (EditorTool.CIRCLE, EditorTool.SPIRAL):
            return {"shape_radius": (center_x + self.shape_radius.value(), center_y)}
        if tool in (EditorTool.RECTANGLE, EditorTool.SVG_SHAPE):
            return {
                "shape_width": (center_x + self.shape_width.value() / 2, center_y),
                "shape_height": (center_x, center_y + self.shape_height.value() / 2),
            }
        if tool == EditorTool.BLOCK:
            return {"block_spacing": (center_x + self.block_spacing.value(), center_y)}
        if tool == EditorTool.SCALE:
            return {
                "scale_width": (center_x + self.scale_width.value() / 2, center_y),
                "scale_height": (center_x, center_y + self.scale_height.value() / 2),
            }
        if tool == EditorTool.SCATTER:
            return {"scatter_radius": (center_x + self.scatter_radius.value(), center_y)}
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
        self.field.show_preview(starts, targets, self.formation_handles(self.field.active_tool))

    def preview_handle_moved(self, kind: str, x: float, y: float) -> None:
        if kind.startswith("plugin_setting:"):
            if self.update_plugin_setting_from_handle(kind.split(":", 1)[1], x, y):
                self.update_formation_preview()
            return
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
        elif kind == "shape_radius":
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            self.shape_radius.setValue(max(1, distance))
        elif kind == "shape_width":
            self.shape_width.setValue(max(1, abs(x - center_x) * 2))
        elif kind == "shape_height":
            self.shape_height.setValue(max(1, abs(y - center_y) * 2))
        elif kind == "block_spacing":
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            self.block_spacing.setValue(max(0.25, distance))
        elif kind == "scale_width":
            self.scale_width.setValue(max(0.1, abs(x - center_x) * 2))
        elif kind == "scale_height":
            self.scale_height.setValue(max(0.1, abs(y - center_y) * 2))
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

    def apply_formation(self, tool: EditorTool) -> None:
        if tool == EditorTool.PLUGIN_FORM:
            self.apply_active_plugin_form_tool_preview()
            return
        targets = self.formation_targets(tool)
        if not targets:
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
        self.set_tool(EditorTool.SELECT)
        self.refresh_selected_paths()

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

        self.scale_width.blockSignals(True)
        self.scale_height.blockSignals(True)
        self.scale_width.setValue(target_width)
        self.scale_height.setValue(target_height)
        self.scale_width.blockSignals(False)
        self.scale_height.blockSignals(False)

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
        self.refresh_selected_paths()

    def context_action(self, name: str) -> None:
        mapping = {
            "Preview Line": EditorTool.LINE,
            "Preview Curve": EditorTool.CURVE,
            "Preview Arc": EditorTool.ARC,
            "Preview Circle": EditorTool.CIRCLE,
            "Preview Rectangle": EditorTool.RECTANGLE,
            "Preview Spiral": EditorTool.SPIRAL,
            "Preview Block": EditorTool.BLOCK,
            "Preview Scale Form": EditorTool.SCALE,
            "Preview SVG Shape": EditorTool.SVG_SHAPE,
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

    def refresh_constraints(self) -> None:
        if not hasattr(self, "constraint_list"):
            return
        self.constraint_list.clear()
        for constraint in self.project.constraints:
            self.constraint_list.addItem(
                f"{constraint.name}: {len(constraint.dot_ids)} dots, {constraint.spacing:g} yd"
            )

    def apply_constraints(self) -> None:
        if not self.project.constraints:
            return
        after = self.current_positions()
        changed = False
        for constraint in self.project.constraints:
            ids = [dot_id for dot_id in constraint.dot_ids if dot_id in after]
            if constraint.constraint_type != "line" or len(ids) < 2:
                continue
            positions = [after[dot_id] for dot_id in ids]
            start = positions[0]
            end = positions[-1]
            vector = (end[0] - start[0], end[1] - start[1])
            length = (vector[0] ** 2 + vector[1] ** 2) ** 0.5 or 1.0
            direction = (vector[0] / length, vector[1] / length)
            spacing = constraint.spacing or self.interval_spacing.value()
            center = (
                sum(x for x, _y in positions) / len(positions),
                sum(y for _x, y in positions) / len(positions),
            )
            first_offset = -spacing * (len(ids) - 1) / 2
            for index, dot_id in enumerate(ids):
                after[dot_id] = (
                    center[0] + direction[0] * (first_offset + spacing * index),
                    center[1] + direction[1] * (first_offset + spacing * index),
                )
            changed = True
        if changed:
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

    def follow_leader_rotate(self) -> None:
        ids, positions = self.selected_positions()
        if len(ids) < 2:
            return
        shift_degrees = self.rotation_degrees.value()
        new_positions, conveyor_anchors = conveyor_follow_positions(positions, shift_degrees)
        before_positions = self.current_positions()
        after_positions = dict(before_positions)
        after_positions.update({dot_id: new_positions[index] for index, dot_id in enumerate(ids)})

        before_anchors = self.clone_path_anchors(self.set_index)
        before_controls = self.clone_path_controls(self.set_index)
        before_counts = self.clone_count_positions(self.set_index)
        after_anchors = self.clone_path_anchors(self.set_index)
        after_controls = self.clone_path_controls(self.set_index)
        after_counts = self.clone_count_positions(self.set_index)
        for dot_id in ids:
            after_counts.pop(dot_id, None)

        if self.set_index > 0:
            for index, dot_id in enumerate(ids):
                if conveyor_anchors[index]:
                    after_anchors[dot_id] = conveyor_anchors[index]
                    after_controls.pop(dot_id, None)
                else:
                    after_anchors.pop(dot_id, None)
                    after_controls.pop(dot_id, None)

        self.undo_stack.push(
            MoveDotsCommand(
                self,
                self.set_index,
                before_positions,
                after_positions,
                "Follow-Leader Conveyor",
                before_anchors,
                after_anchors,
                before_controls,
                after_controls,
                before_counts,
                after_counts,
            )
        )
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

    def populate_sets(self) -> None:
        self.set_list.blockSignals(True)
        self.set_list.clear()
        for index, drill_set in enumerate(self.project.sets):
            tempo = self.project.active_tempo(index)
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

    def copy_set(self) -> None:
        source = self.current_set()
        copied = DrillSet(
            name=f"{source.name} Copy",
            start_count=source.end_count + 1,
            end_count=source.end_count + source.duration_counts,
            tempo=source.tempo,
            dot_positions=dict(source.dot_positions),
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
        seek_audio: bool,
        update_waveform: bool = True,
        refresh_paths: bool = True,
    ) -> None:
        start_count, end_count = playback_bounds_for_set(self.project, self.set_index)
        self.current_count = max(start_count, min(count, end_count))
        self.field.set_positions(interpolate_project(self.project, self.set_index, self.current_count))
        self.field.set_prop_states(interpolate_props(self.project, self.set_index, self.current_count))
        self.count_label.setText(f"Count {self.current_count:.2f}")
        if hasattr(self, "count_finder"):
            self.count_finder.blockSignals(True)
            self.count_finder.setValue(self.current_count)
            self.count_finder.blockSignals(False)
        self.timeline.blockSignals(True)
        self.timeline.setValue(int(self.current_count * 100))
        self.timeline.blockSignals(False)
        if seek_audio and self.player.source().isValid():
            self.player.setPosition(self.audio_position_for_count(self.set_index, self.current_count))
        elif update_waveform and hasattr(self, "waveform"):
            self.waveform.set_position_ms(self.audio_position_for_count(self.set_index, self.current_count))
        if refresh_paths:
            self.refresh_selected_paths()

    def play(self) -> None:
        if self.play_timer.isActive():
            return
        if self.player.source().isValid():
            self.player.setPosition(self.audio_position_for_count(self.set_index, self.current_count))
            self.player.setPlaybackRate(self.current_playback_rate())
        self.play_timer.start()
        if self.player.source().isValid():
            self.player.play()
        self.refresh_selected_paths()

    def pause(self) -> None:
        self.play_timer.stop()
        if self.player.source().isValid():
            self.player.pause()
        self.refresh_selected_paths()

    def toggle_playback(self) -> None:
        if self.play_timer.isActive():
            self.pause()
        else:
            self.play()

    def tick_playback(self) -> None:
        if self.player.source().isValid():
            audio_position = self.player.position()
            next_set_index, next_count = self.count_for_audio_position(audio_position)
            if hasattr(self, "waveform"):
                self.waveform.set_position_ms(audio_position)
            if self.loop_current_set.isChecked() and next_set_index != self.set_index:
                self.current_count = self.current_set().start_count
                self.player.setPosition(self.audio_position_for_count(self.set_index, self.current_count))
                self.set_count(self.current_count, seek_audio=False, update_waveform=False)
                return
            if next_set_index != self.set_index:
                self.set_index = next_set_index
                self.current_count = next_count
                self.populate_sets()
                self.sync_timeline()
                self.refresh_selected_paths()
            else:
                self.current_count = next_count
            self.set_count(self.current_count, seek_audio=False, update_waveform=False, refresh_paths=False)
            return

        tempo = self.project.active_tempo(self.set_index)
        self.current_count += (tempo / 60) * (self.play_timer.interval() / 1000) * self.current_playback_rate()
        _start_count, playback_end_count = playback_bounds_for_set(self.project, self.set_index)
        if self.current_count > playback_end_count:
            if self.loop_current_set.isChecked():
                self.current_count = self.current_set().start_count
                if self.player.source().isValid():
                    self.player.setPosition(self.audio_position_for_count(self.set_index, self.current_count))
            elif self.set_index + 1 < len(self.project.sets):
                self.set_index += 1
                self.current_count = self.current_set().start_count
                self.populate_sets()
                self.sync_timeline()
                self.refresh_selected_paths()
            else:
                self.pause()
                self.current_count = self.current_set().end_count
        self.set_count(self.current_count, seek_audio=False, refresh_paths=False)

    def current_playback_rate(self) -> float:
        if not hasattr(self, "playback_rate"):
            return 1.0
        return float(self.playback_rate.currentText().replace("x", ""))

    def update_playback_rate(self) -> None:
        if self.player.source().isValid():
            self.player.setPlaybackRate(self.current_playback_rate())

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
        style = MovementStyle(str(self.movement_style_combo.currentData() or MovementStyle.NORMAL.value))
        drill_set = self.current_set()
        for dot_id in ids:
            if style == MovementStyle.NORMAL:
                drill_set.movement_styles.pop(dot_id, None)
            else:
                drill_set.movement_styles[dot_id] = style
        self.sync_movement_style_controls()
        self.statusBar().showMessage(f"Applied {self.movement_style_combo.currentText()} to {len(ids)} marcher(s)", 2400)

    def clear_movement_style_for_selected(self) -> None:
        ids = self.field.selected_dot_ids()
        if not ids:
            return
        drill_set = self.current_set()
        for dot_id in ids:
            drill_set.movement_styles.pop(dot_id, None)
        self.sync_movement_style_controls()
        self.statusBar().showMessage(f"Cleared movement style for {len(ids)} marcher(s)", 2200)

    def sync_movement_style_controls(self) -> None:
        if not hasattr(self, "movement_style_status"):
            return
        ids = self.field.selected_dot_ids()
        has_selection = bool(ids)
        self.movement_style_combo.setEnabled(has_selection)
        if not has_selection:
            self.movement_style_status.setText("Select marchers to set style for this set.")
            return
        drill_set = self.current_set()
        styles = [
            drill_set.movement_styles.get(dot_id, MovementStyle.NORMAL)
            for dot_id in ids
        ]
        unique_styles = set(styles)
        if len(unique_styles) == 1:
            style = styles[0]
            index = self.movement_style_combo.findData(style.value)
            if index >= 0:
                self.movement_style_combo.blockSignals(True)
                self.movement_style_combo.setCurrentIndex(index)
                self.movement_style_combo.blockSignals(False)
            self.movement_style_status.setText(f"{len(ids)} selected: {self.movement_style_combo.currentText()} for {self.current_set().name}.")
        else:
            self.movement_style_status.setText(f"{len(ids)} selected: mixed movement styles for {self.current_set().name}.")

    def refresh_markers(self) -> None:
        self.marker_table.setRowCount(len(self.project.markers))
        for row, marker in enumerate(self.project.markers):
            self.marker_table.setItem(row, 0, QTableWidgetItem(f"{marker.count:.2f}"))
            self.marker_table.setItem(row, 1, QTableWidgetItem(marker.label))

    def refresh_marcher_table(self) -> None:
        if not hasattr(self, "marcher_table"):
            return
        selected = set(self.field.selected_dot_ids()) if hasattr(self, "field") else set()
        self.marcher_table.blockSignals(True)
        self.marcher_table.clearSelection()
        self.marcher_table.setRowCount(len(self.project.dots))
        for row, dot in enumerate(self.project.dots):
            color_item = QTableWidgetItem("")
            id_item = QTableWidgetItem(dot.id)
            section_item = QTableWidgetItem(dot.section or "-")
            name_item = QTableWidgetItem(dot.name)
            color_item.setBackground(QColor(dot.color or "#e53935"))
            color_item.setToolTip(dot.color or "#e53935")
            for item in (color_item, id_item, section_item, name_item):
                item.setData(Qt.ItemDataRole.UserRole, dot.id)
            self.marcher_table.setItem(row, 0, color_item)
            self.marcher_table.setItem(row, 1, id_item)
            self.marcher_table.setItem(row, 2, section_item)
            self.marcher_table.setItem(row, 3, name_item)
            if dot.id in selected:
                self.marcher_table.selectRow(row)
        self.marcher_table.blockSignals(False)
        self.filter_marcher_table()

    def filter_marcher_table(self) -> None:
        if not hasattr(self, "marcher_table"):
            return
        query = self.marcher_search.text().strip().lower() if hasattr(self, "marcher_search") else ""
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
            haystack = " ".join(values).lower()
            self.marcher_table.setRowHidden(row, bool(query and query not in haystack))

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
        for dot_item in self.field.dot_items.values():
            dot_item.setSelected(dot_item.dot_id in selected_ids)
        for prop_item in self.field.prop_items.values():
            prop_item.setSelected(False)
        self.selection_changed()
        self.statusBar().showMessage(f"Selected {len(selected_ids)} visible marcher(s)", 2000)

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

    def select_marcher_from_table(self, row: int, _column: int) -> None:
        item = self.marcher_table.item(row, 0)
        if not item:
            return
        dot_id = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
        for dot_item in self.field.dot_items.values():
            dot_item.setSelected(False)
        for prop_item in self.field.prop_items.values():
            prop_item.setSelected(False)
        if dot_id in self.field.dot_items:
            self.field.dot_items[dot_id].setSelected(True)
            self.field.centerOn(self.field.dot_items[dot_id])
        self.selection_changed()

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
            self.statusBar().showMessage(f"Updated {len(after)} marcher(s)", 2200)

    def apply_dot_appearance(self, updates: dict[str, dict[str, str]]) -> None:
        for dot_id, fields in updates.items():
            dot = self.project.dot_by_id(dot_id)
            if not dot:
                continue
            if "color" in fields:
                dot.color = fields["color"] or "#e53935"
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
        self.refresh_appearance_groups()
        self.sync_inspector()

    def sync_inspector(self) -> None:
        ids = self.field.selected_dot_ids()
        prop_ids = self.field.selected_prop_ids()
        selected_total = len(ids) + len(prop_ids)
        self.selection_label.setText(f"{selected_total} selected" if selected_total else "No selection")
        self.refresh_marcher_table()
        self.refresh_prop_table()
        self.refresh_appearance_groups()
        self.sync_movement_style_controls()
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
            position = self.current_set().dot_positions.get(ids[0], (0, 0))
            if dot:
                self.dot_name.setText(dot.name)
                self.dot_section.setText(dot.section)
                self.dot_instrument.setText(dot.instrument)
                self.dot_rank.setText(dot.rank)
                self.dot_equipment.setText(dot.equipment)
                self.dot_layer.setText(dot.layer)
                self.dot_x.setText(f"{position[0]:.2f}")
                self.dot_y.setText(f"{position[1]:.2f}")
                yard_text, hash_text = format_drill_coordinate(position[0], position[1])
                self.dot_yardline.setText(yard_text)
                self.dot_hash.setText(hash_text)

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
        self.apply_visibility_filters()

    def apply_visibility_filters(self) -> None:
        if not hasattr(self, "section_filter"):
            return
        self.field.set_visibility_filters(
            self.section_filter.currentText() or "All",
            self.layer_filter.currentText() or "All",
        )

    def toggle_snap_align(self) -> None:
        self.snap_align.setChecked(not self.snap_align.isChecked())

    def analyze_paths(self) -> None:
        if not hasattr(self, "warning_list"):
            return
        self.warning_list.clear()
        all_warnings = []
        for set_index in range(len(self.project.sets)):
            all_warnings.extend(
                detect_path_warnings(
                    self.project,
                    set_index,
                    min_spacing=self.min_spacing.value(),
                    max_yards_per_count=self.max_yards_per_count.value(),
                )
            )
        for warning in all_warnings:
            self.warning_list.addItem(
                f"{warning.severity.upper()} | {warning.set_name} | "
                f"Count {warning.count:.2f} | {warning.message}"
            )
        self.statusBar().showMessage(f"{len(all_warnings)} path warnings found", 3000)

    def auto_plan_selected_paths(self) -> None:
        target_index = self.path_display_set_index()
        if target_index is None:
            target_index = self.set_index if self.set_index > 0 else 1 if len(self.project.sets) > 1 else 0
        if target_index <= 0:
            QMessageBox.information(self, "Auto Plan Paths", "Add a moving set before auto-planning paths.")
            return
        selected = self.field.selected_dot_ids()
        anchors_added = auto_plan_paths(
            self.project,
            target_index,
            selected,
            min_spacing=self.min_spacing.value(),
        )
        self.refresh_selected_paths()
        if hasattr(self, "warning_list"):
            self.warning_list.clear()
            warnings = detect_path_warnings(
                self.project,
                target_index,
                min_spacing=self.min_spacing.value(),
                max_yards_per_count=self.max_yards_per_count.value(),
                dot_ids=selected or None,
                warning_limit=120,
            )
            for warning in warnings:
                self.warning_list.addItem(
                    f"{warning.severity.upper()} | {warning.set_name} | "
                    f"Count {warning.count:.2f} | {warning.message}"
            )
        self.statusBar().showMessage(f"Auto-planned {anchors_added} path anchors", 3000)

    def clear_selected_paths(self) -> None:
        target_index = self.path_display_set_index()
        if target_index is None or target_index <= 0:
            QMessageBox.information(self, "Clear Paths", "Select a moving transition before clearing paths.")
            return
        selected = self.field.selected_dot_ids()
        if not selected:
            QMessageBox.information(self, "Clear Paths", "Select one or more marchers first.")
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
        self.update_formation_preview()
        self.refresh_selected_paths()

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
        start_set = self.project.sets[target_index - 1] if target_index > 0 else target_set
        paths: dict[str, list[tuple[float, float]]] = {}
        anchors: dict[str, list[tuple[float, float]]] = {}
        controls: dict[str, list[dict[str, tuple[float, float]]]] = {}
        for dot_id in selected:
            start = start_set.dot_positions.get(dot_id)
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

    def add_path_anchor(self, dot_id: str, x: float, y: float) -> None:
        target_index = self.path_display_set_index()
        if target_index is None:
            return
        self.project.sets[target_index].path_anchors.setdefault(dot_id, []).append((x, y))
        self.project.sets[target_index].path_controls.setdefault(dot_id, [])
        self.refresh_selected_paths()

    def move_path_anchor(self, dot_id: str, anchor_index: int, x: float, y: float) -> None:
        target_index = self.path_display_set_index()
        if target_index is None:
            return
        anchors = self.project.sets[target_index].path_anchors.setdefault(dot_id, [])
        if 0 <= anchor_index < len(anchors):
            old_x, old_y = anchors[anchor_index]
            anchors[anchor_index] = (x, y)
            controls = self.project.sets[target_index].path_controls.setdefault(dot_id, [])
            if anchor_index < len(controls):
                delta_x = x - old_x
                delta_y = y - old_y
                for control_name in ("in", "out"):
                    if control_name in controls[anchor_index]:
                        control_x, control_y = controls[anchor_index][control_name]
                        controls[anchor_index][control_name] = (control_x + delta_x, control_y + delta_y)
        self.refresh_selected_paths()

    def move_path_tangent(self, dot_id: str, anchor_index: int, control_name: str, x: float, y: float) -> None:
        target_index = self.path_display_set_index()
        if target_index is None:
            return
        controls = self.project.sets[target_index].path_controls.setdefault(dot_id, [])
        while len(controls) <= anchor_index:
            controls.append({})
        controls[anchor_index][control_name] = (x, y)
        self.refresh_selected_paths()

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
        dot_book_button = QPushButton("Dot Book PDF")
        dot_book_button.setToolTip("Create one coordinate packet page per performer.")
        staff_packet_button = QPushButton("Staff Packet PDF")
        staff_packet_button.setToolTip("Create a staff packet with show summary, warnings, and large set pages.")
        coordinate_button = QPushButton("Coordinate CSV")
        coordinate_button.setToolTip("Export all performer coordinates for every set.")
        zip_button = QPushButton("Project Zip")
        zip_button.setToolTip("Package the project folder for backup or sharing.")
        ffmpeg_button = QPushButton("Set ffmpeg.exe")
        ffmpeg_button.setToolTip("Choose a local ffmpeg executable for MP4 export.")

        for button in (mp4_button, pdf_button, dot_book_button, staff_packet_button, coordinate_button, zip_button):
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
        dot_book_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_dot_book_pdf))
        staff_packet_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_staff_packet_pdf))
        coordinate_button.clicked.connect(lambda: self.accept_export_choice(dialog, self.export_coordinate_csv))
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

    def export_coordinate_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Coordinate CSV",
            str(self.project_dir / "coordinates.csv"),
            "CSV (*.csv)",
        )
        if not path:
            return
        export_coordinate_csv(Path(path), self.project)
        self.statusBar().showMessage("Coordinate CSV exported", 3000)

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
            export_drill_sheet_pdf(Path(path), self.project, self.project_dir, progress_callback=update_progress)
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))
            return
        finally:
            progress.close()
        self.statusBar().showMessage("Drill sheet PDF exported", 3000)

    def export_dot_book_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Dot Book PDF",
            str(self.project_dir / "dot_book.pdf"),
            "PDF (*.pdf)",
        )
        if not path:
            return

        progress = QProgressDialog("Preparing dot book PDF...", None, 0, max(1, len(self.project.dots)), self)
        progress.setWindowTitle("Exporting Dot Book PDF")
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
            export_dot_book_pdf(Path(path), self.project, progress_callback=update_progress)
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))
            return
        finally:
            progress.close()
        self.statusBar().showMessage("Dot book PDF exported", 3000)

    def export_staff_packet_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Staff Packet PDF",
            str(self.project_dir / "staff_packet.pdf"),
            "PDF (*.pdf)",
        )
        if not path:
            return

        progress = QProgressDialog("Preparing staff packet PDF...", None, 0, max(1, len(self.project.sets)), self)
        progress.setWindowTitle("Exporting Staff Packet PDF")
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
            export_staff_packet_pdf(Path(path), self.project, self.project_dir, progress_callback=update_progress)
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))
            return
        finally:
            progress.close()
        self.statusBar().showMessage("Staff packet PDF exported", 3000)

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
        self.settings.setValue("main_window/dock_state", self.saveState())
        self.settings.sync()
        self.save()
        super().closeEvent(event)
