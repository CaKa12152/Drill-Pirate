from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

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
    QWidget,
)

from drill_writer.core.analysis import auto_plan_paths, detect_path_warnings, segments_intersect
from drill_writer.core.animation import interpolate_project, sample_transition_path
from drill_writer.core.models import AudioVersion, Dot, DotConstraint, DrillProject, DrillSet, Marker, TimingEvent, Transition
from drill_writer.core.project_io import load_project, project_library_dir, safe_folder_name, save_project
from drill_writer.core.svg_import import load_svg_contours
from drill_writer.core.timing import (
    active_audio_version,
    audio_ms_for_set_count,
    describe_timing_event,
    set_active_audio_version,
    set_count_for_audio_ms,
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
    spiral_positions,
    distance,
)
from drill_writer.export.exporters import (
    ExportCancelled,
    export_coordinate_csv,
    export_dot_book_pdf,
    export_drill_sheet_pdf,
    export_mp4,
    export_project_zip,
    export_staff_packet_pdf,
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


@dataclass(slots=True)
class PluginFormTool:
    plugin_id: str
    tool_id: str
    name: str
    callback: Callable[[FormToolContext], Any]
    min_selected: int


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
        self.plugin_contribution_actions: dict[str, list[tuple[QMenu, QAction]]] = {}
        self.plugin_contribution_widgets: dict[str, list[QWidget]] = {}
        self.plugin_named_menus: dict[str, QMenu] = {}
        self.undo_stack = QUndoStack(self)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
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
        self.field.path_tangent_moved.connect(self.move_path_tangent)
        self.field.shape_anchor_toggled.connect(self.toggle_shape_line_anchor)
        self.field.set_formation_callback(self.apply_formation)
        self.setCentralWidget(self.build_layout())
        self.build_menus()
        self.refresh_audio_versions()
        self.refresh_timing_events()
        self.populate_sets()
        self.refresh_visibility_filters()
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

        playback_menu = self.menuBar().addMenu("Playback")
        self.plugin_named_menus["Playback"] = playback_menu
        playback_menu.addAction(self.menu_action("Play/Pause", self.toggle_playback, Qt.Key.Key_Space))
        playback_menu.addAction(self.menu_action("Pause", self.pause))
        playback_menu.addAction(self.menu_action("Toggle Loop Current Set", self.toggle_loop_current_set, QKeySequence("Ctrl+L")))
        playback_menu.addAction(self.menu_action("Go To Count", self.focus_count_finder, QKeySequence("Ctrl+G")))

        tools_menu = self.menuBar().addMenu("Tools")
        self.plugin_named_menus["Tools"] = tools_menu
        add_marcher_action = QAction("Add Marcher", self)
        add_marcher_action.setShortcut(QKeySequence("Ctrl+M"))
        add_marcher_action.triggered.connect(self.add_marcher)
        delete_marcher_action = QAction("Delete Selected", self)
        delete_marcher_action.setShortcut(QKeySequence("Del"))
        delete_marcher_action.triggered.connect(self.delete_selected_marchers)
        add_set_action = QAction("Add Set", self)
        add_set_action.setShortcut(QKeySequence("Ctrl+Alt+S"))
        add_set_action.triggered.connect(self.add_set)
        remove_set_action = QAction("Remove Set", self)
        remove_set_action.setShortcut(QKeySequence("Ctrl+Alt+Backspace"))
        remove_set_action.triggered.connect(self.remove_set)
        tools_menu.addActions(
            [add_marcher_action, delete_marcher_action, add_set_action, remove_set_action]
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
        tools_menu.addActions([snap_action, analyze_action, plan_action, clear_paths_action, keyframe_action, follow_action])
        self.addActions(
            [
                add_marcher_action,
                delete_marcher_action,
                add_set_action,
                remove_set_action,
                *tool_actions,
                snap_action,
                analyze_action,
                plan_action,
                clear_paths_action,
                keyframe_action,
                follow_action,
            ]
        )
        self.plugin_tools_menu = self.menuBar().addMenu("Plugin Tools")
        self.plugin_named_menus["Plugin Tools"] = self.plugin_tools_menu

    def menu_action(self, text: str, callback, shortcut=None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    def register_plugin_form_tool(
        self,
        plugin_id: str,
        name: str,
        callback: Callable[[FormToolContext], Any],
        shortcut: str | None = None,
        min_selected: int = 2,
        tooltip: str = "",
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
        )
        button = QPushButton(name)
        button.setToolTip(tooltip or f"Plugin form tool from {plugin_id}")
        button.clicked.connect(lambda _checked=False, selected=tool_id: self.apply_plugin_form_tool(selected))
        self.plugin_form_tool_layout.addWidget(button)
        self.plugin_form_tool_group.setVisible(True)
        self.plugin_contribution_widgets.setdefault(plugin_id, []).append(button)

        action = self.menu_action(
            name,
            lambda _checked=False, selected=tool_id: self.apply_plugin_form_tool(selected),
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
        for widget in list(self.plugin_contribution_widgets.get(tool.plugin_id, [])):
            if isinstance(widget, QPushButton) and widget.text() == tool.name:
                widget.setParent(None)
                widget.deleteLater()
                self.plugin_contribution_widgets[tool.plugin_id].remove(widget)
        for menu, action in list(self.plugin_contribution_actions.get(tool.plugin_id, [])):
            if action.text() == tool.name:
                menu.removeAction(action)
                self.removeAction(action)
                action.deleteLater()
                self.plugin_contribution_actions[tool.plugin_id].remove((menu, action))
        self.plugin_form_tool_group.setVisible(bool(self.plugin_form_tools))

    def apply_plugin_form_tool(self, tool_id: str) -> None:
        tool = self.plugin_form_tools.get(tool_id)
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
                action.deleteLater()
            for widget in self.plugin_contribution_widgets.pop(current_plugin_id, []):
                widget.setParent(None)
                widget.deleteLater()
            for tool_id, tool in list(self.plugin_form_tools.items()):
                if tool.plugin_id == current_plugin_id:
                    self.plugin_form_tools.pop(tool_id, None)
        self.plugin_form_tool_group.setVisible(bool(self.plugin_form_tools))
        self.plugin_panel_group.setVisible(bool(self.plugin_contribution_widgets))

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
        tabs = QTabWidget()
        layout.addWidget(tabs)

        formation_tab = QWidget()
        formation_layout = QVBoxLayout(formation_tab)
        group = QGroupBox("Formation Tools")
        tools_layout = QVBoxLayout(group)
        self.tool_buttons: dict[EditorTool, QPushButton] = {}
        for tool, label in (
            (EditorTool.SELECT, "Select"),
            (EditorTool.LINE, "Line"),
            (EditorTool.CURVE, "Curve"),
            (EditorTool.ARC, "Arc"),
            (EditorTool.CIRCLE, "Circle"),
            (EditorTool.RECTANGLE, "Rectangle"),
            (EditorTool.SPIRAL, "Spiral"),
            (EditorTool.BLOCK, "Block/Grid"),
            (EditorTool.SVG_SHAPE, "SVG Shape"),
            (EditorTool.LASSO, "Lasso Select"),
            (EditorTool.SCATTER, "Scatter"),
            (EditorTool.MIRROR, "Mirror"),
            (EditorTool.SHAPE_LINE, "Shape Line"),
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, selected=tool: self.set_tool(selected))
            tools_layout.addWidget(button)
            self.tool_buttons[tool] = button
        formation_layout.addWidget(group)

        self.plugin_form_tool_group = QGroupBox("Plugin Form Tools")
        self.plugin_form_tool_layout = QVBoxLayout(self.plugin_form_tool_group)
        self.plugin_form_tool_group.setVisible(False)
        formation_layout.addWidget(self.plugin_form_tool_group)

        self.plugin_panel_group = QGroupBox("Plugin Actions")
        self.plugin_panel_layout = QVBoxLayout(self.plugin_panel_group)
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
            self.svg_tool_group,
            self.shape_tool_group,
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
        self.micro_edit_enabled = QCheckBox("Micro Edit Dragging")
        playback_form.addRow("Playback Rate", self.playback_rate)
        playback_form.addRow(self.loop_current_set)
        playback_form.addRow("Count Finder", self.count_finder)
        playback_form.addRow(go_count_button)
        playback_form.addRow(self.micro_edit_enabled)
        playback_form.addRow(keyframe_button)
        playback_form.addRow(clear_keyframe_button)
        playback_form.addRow(beat_markers_button)
        rehearsal_layout.addWidget(playback_group)

        audio_group = QGroupBox("Audio + Timing Map")
        audio_form = QFormLayout(audio_group)
        self.audio_version_combo = QComboBox()
        self.audio_version_combo.currentIndexChanged.connect(self.switch_audio_version)
        add_audio_button = QPushButton("Add Audio Version")
        add_audio_button.clicked.connect(self.add_audio_version)
        map_anchor_button = QPushButton("Map Current Count To Audio")
        map_anchor_button.clicked.connect(self.map_current_count_to_audio)
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
        audio_form.addRow("Audio Version", self.audio_version_combo)
        audio_form.addRow(add_audio_button)
        audio_form.addRow(map_anchor_button)
        audio_form.addRow("Event Type", self.timing_event_type)
        audio_form.addRow("Tempo", self.timing_event_tempo)
        audio_form.addRow("End Count", self.timing_event_end_count)
        audio_form.addRow("End Tempo", self.timing_event_end_tempo)
        audio_form.addRow("Milliseconds", self.timing_event_ms)
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
        view_tab_layout = QVBoxLayout(view_tab)
        view_tab_layout.addWidget(view_group)
        view_tab_layout.addStretch()
        tabs.addTab(view_tab, "View")
        self.set_tool(EditorTool.SELECT)
        return panel

    def build_inspector_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        selection_tab = QWidget()
        selection_layout = QVBoxLayout(selection_tab)
        self.selection_label = QLabel("No selection")
        selection_layout.addWidget(self.selection_label)

        dot_group = QGroupBox("Dot Properties")
        form = QFormLayout(dot_group)
        self.dot_name = QLineEdit()
        self.dot_section = QLineEdit()
        self.dot_instrument = QLineEdit()
        self.dot_rank = QLineEdit()
        self.dot_equipment = QLineEdit()
        self.dot_layer = QLineEdit("Main")
        self.dot_x = QLineEdit()
        self.dot_y = QLineEdit()
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
        selection_layout.addWidget(dot_group)
        selection_layout.addStretch()
        tabs.addTab(selection_tab, "Selection")

        sets_tab = QWidget()
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
        self.svg_tool_group.setVisible(tool == EditorTool.SVG_SHAPE)
        self.shape_tool_group.setVisible(
            tool in (EditorTool.CIRCLE, EditorTool.RECTANGLE, EditorTool.SPIRAL, EditorTool.BLOCK, EditorTool.SVG_SHAPE)
        )
        self.rotate_tool_group.setVisible(False)

    def current_set(self) -> DrillSet:
        return self.project.sets[self.set_index]

    def current_positions(self) -> dict[str, tuple[float, float]]:
        return dict(self.current_set().dot_positions)

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
        self.field.dot_items[dot_id].setSelected(True)
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
        self.refresh_visibility_filters()
        self.refresh_constraints()
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
        return self.assign_targets_to_marchers(ids, new_positions, preserve_order=tool == EditorTool.SHAPE_LINE)

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
        remaining_targets = set(range(len(targets)))
        assignment: dict[str, int] = {}
        for dot_id in sorted(ids, key=lambda item: min(distance(starts[item], targets[index]) for index in remaining_targets)):
            best_target = min(remaining_targets, key=lambda index: distance(starts[dot_id], targets[index]))
            assignment[dot_id] = best_target
            remaining_targets.remove(best_target)

        for _iteration in range(3):
            changed = False
            for first_index, dot_a in enumerate(ids):
                for dot_b in ids[first_index + 1 :]:
                    target_a = targets[assignment[dot_a]]
                    target_b = targets[assignment[dot_b]]
                    current_cost = distance(starts[dot_a], target_a) + distance(starts[dot_b], target_b)
                    swapped_cost = distance(starts[dot_a], target_b) + distance(starts[dot_b], target_a)
                    crosses = segments_intersect(starts[dot_a], target_a, starts[dot_b], target_b)
                    if swapped_cost + 0.5 < current_cost or (crosses and swapped_cost <= current_cost * 1.15 + 2.0):
                        assignment[dot_a], assignment[dot_b] = assignment[dot_b], assignment[dot_a]
                        changed = True
            if not changed:
                break
        return {dot_id: targets[assignment[dot_id]] for dot_id in ids}

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
        if tool in (EditorTool.CIRCLE, EditorTool.SPIRAL):
            return {"shape_radius": (center_x + self.shape_radius.value(), center_y)}
        if tool in (EditorTool.RECTANGLE, EditorTool.SVG_SHAPE):
            return {
                "shape_width": (center_x + self.shape_width.value() / 2, center_y),
                "shape_height": (center_x, center_y + self.shape_height.value() / 2),
            }
        if tool == EditorTool.BLOCK:
            return {"block_spacing": (center_x + self.block_spacing.value(), center_y)}
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
        transition_starts = self.current_transition_start_positions()
        starts = {
            dot_id: transition_starts.get(dot_id, self.current_set().dot_positions[dot_id])
            for dot_id in targets
        }
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
        self.set_tool(EditorTool.SELECT)
        self.field.clear_preview()

    def apply_current_preview(self) -> None:
        self.apply_formation(self.field.active_tool)

    def apply_formation(self, tool: EditorTool) -> None:
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

    def context_action(self, name: str) -> None:
        mapping = {
            "Preview Line": EditorTool.LINE,
            "Preview Curve": EditorTool.CURVE,
            "Preview Arc": EditorTool.ARC,
            "Preview Circle": EditorTool.CIRCLE,
            "Preview Rectangle": EditorTool.RECTANGLE,
            "Preview Spiral": EditorTool.SPIRAL,
            "Preview Block": EditorTool.BLOCK,
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
        self.timeline.blockSignals(True)
        self.timeline.setRange(drill_set.start_count * 100, drill_set.end_count * 100)
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
        self.set_count(value / 100, seek_audio=True)

    def set_count(self, count: float, seek_audio: bool) -> None:
        drill_set = self.current_set()
        self.current_count = max(drill_set.start_count, min(count, drill_set.end_count))
        self.field.set_positions(interpolate_project(self.project, self.set_index, self.current_count))
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
        elif hasattr(self, "waveform"):
            self.waveform.set_position_ms(self.audio_position_for_count(self.set_index, self.current_count))
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
            next_set_index, next_count = self.count_for_audio_position(self.player.position())
            if self.loop_current_set.isChecked() and next_set_index != self.set_index:
                self.current_count = self.current_set().start_count
                self.player.setPosition(self.audio_position_for_count(self.set_index, self.current_count))
                self.set_count(self.current_count, seek_audio=False)
                return
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
        self.current_count += (tempo / 60) * (self.play_timer.interval() / 1000) * self.current_playback_rate()
        if self.current_count > self.current_set().end_count:
            if self.loop_current_set.isChecked():
                self.current_count = self.current_set().start_count
                if self.player.source().isValid():
                    self.player.setPosition(self.audio_position_for_count(self.set_index, self.current_count))
            elif self.set_index + 1 < len(self.project.sets):
                self.change_set(self.set_index + 1)
            else:
                self.pause()
                self.current_count = self.current_set().end_count
        self.set_count(self.current_count, seek_audio=False)

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

    def refresh_markers(self) -> None:
        self.marker_table.setRowCount(len(self.project.markers))
        for row, marker in enumerate(self.project.markers):
            self.marker_table.setItem(row, 0, QTableWidgetItem(f"{marker.count:.2f}"))
            self.marker_table.setItem(row, 1, QTableWidgetItem(marker.label))

    def sync_inspector(self) -> None:
        ids = self.field.selected_dot_ids()
        self.selection_label.setText(f"{len(ids)} selected" if ids else "No selection")
        enabled = len(ids) == 1
        for widget in (
            self.dot_name,
            self.dot_section,
            self.dot_instrument,
            self.dot_rank,
            self.dot_equipment,
            self.dot_layer,
            self.dot_x,
            self.dot_y,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            return
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

    def refresh_visibility_filters(self) -> None:
        if not hasattr(self, "section_filter"):
            return
        current_section = self.section_filter.currentText() or "All"
        current_layer = self.layer_filter.currentText() or "All"
        sections = ["All", *sorted({dot.section for dot in self.project.dots if dot.section})]
        layers = ["All", *sorted({dot.layer for dot in self.project.dots if dot.layer})]
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
            self.field.rebuild_dots()
            self.field.set_positions(self.current_set().dot_positions)
            self.refresh_visibility_filters()

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
            export_drill_sheet_pdf(Path(path), self.project, progress_callback=update_progress)
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
            export_staff_packet_pdf(Path(path), self.project, progress_callback=update_progress)
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
        self.save()
        super().closeEvent(event)
