from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from drill_writer.core.coordinates import BACK_HASH_YARDS, FRONT_HASH_YARDS, format_drill_coordinate
from drill_writer.core.drill_grid import (
    DrillGridSettings,
    grid_axis_values,
    snap_positions_to_grid,
)
from drill_writer.core.models import Dot
from drill_writer.core.project_io import create_project_folder, load_project, save_project
from drill_writer.core.tools import cubic_bezier_point
from drill_writer.ui.appearance import (
    EIGHT_TO_FIVE_STEP_YARDS,
    FIELD_DOT_GAP_AT_EIGHT_TO_FIVE_YARDS,
    FIELD_DOT_OUTLINE_YARDS,
    FIELD_DOT_RADIUS_YARDS,
    FIELD_DOT_VISUAL_DIAMETER_YARDS,
)
from drill_writer.ui.field_view import DotItem, EditorTool, FieldView
from drill_writer.ui.main_window import MainWindow


class DrillGridCoreTests(unittest.TestCase):
    def test_standard_eight_to_five_spacing_and_serialization(self) -> None:
        settings = DrillGridSettings(enabled=True, steps_per_five_x=8, steps_per_five_y=8)
        self.assertAlmostEqual(settings.spacing_x, 0.625)
        self.assertAlmostEqual(settings.spacing_y, 0.625)
        self.assertEqual(settings.preset_label, "8:5")
        self.assertEqual(settings.snap_point((0.34, -1.02)), (0.625, -1.25))
        self.assertEqual(DrillGridSettings.from_json(settings.to_json()), settings)

    def test_college_hashes_are_priority_snap_rows_at_eight_and_sixteen_to_five(self) -> None:
        for steps_per_five in (8, 16):
            settings = DrillGridSettings(
                enabled=True,
                steps_per_five_x=steps_per_five,
                steps_per_five_y=steps_per_five,
            )
            for hash_y in (FRONT_HASH_YARDS, BACK_HASH_YARDS):
                snapped = settings.snap_point((3.17, hash_y), reference_y=(FRONT_HASH_YARDS, BACK_HASH_YARDS))
                self.assertEqual(snapped[1], hash_y)
                self.assertNotEqual(settings.snap_point((3.17, hash_y))[1], hash_y)
            snapped_line = snap_positions_to_grid(
                [(-1.2, FRONT_HASH_YARDS), (0.0, FRONT_HASH_YARDS), (1.2, FRONT_HASH_YARDS)],
                settings,
                reference_y=(FRONT_HASH_YARDS, BACK_HASH_YARDS),
            )
            self.assertTrue(all(y == FRONT_HASH_YARDS for _x, y in snapped_line))
            self.assertEqual(len(set(snapped_line)), len(snapped_line))

    def test_axis_values_respect_custom_origin(self) -> None:
        values = grid_axis_values(-1.0, 2.0, 0.25, 0.5)
        self.assertEqual(values, [-0.75, -0.25, 0.25, 0.75, 1.25, 1.75])

    def test_dense_form_snapping_never_stacks_marchers(self) -> None:
        settings = DrillGridSettings(enabled=True, steps_per_five_x=8, steps_per_five_y=8)
        snapped = snap_positions_to_grid([(0.1, 0.1)] * 20, settings)
        self.assertEqual(len(snapped), 20)
        self.assertEqual(len(set(snapped)), 20)
        for x, y in snapped:
            self.assertAlmostEqual(x / settings.spacing_x, round(x / settings.spacing_x))
            self.assertAlmostEqual(y / settings.spacing_y, round(y / settings.spacing_y))

    def test_grid_settings_persist_with_project_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Grid Persistence", None, 160, 8, "4/4", 4)
            project = load_project(project_dir)
            settings = DrillGridSettings(enabled=True, steps_per_five_x=12, steps_per_five_y=8)
            project.workflow["drill_grid"] = settings.to_json()
            save_project(project_dir, project, backup=False)
            loaded = load_project(project_dir)
            self.assertEqual(DrillGridSettings.from_json(loaded.workflow["drill_grid"]), settings)


class DrillGridUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_field_overlay_and_direct_marcher_snap(self) -> None:
        field = FieldView()
        try:
            self.assertTrue(field.drafting_grid_items)
            self.assertTrue(all(item.isVisible() for item in field.drafting_grid_items))
            settings = DrillGridSettings(enabled=True, steps_per_five_x=8, steps_per_five_y=8)
            field.set_drill_grid(settings)
            self.assertEqual(len(field.drill_grid_items), 1)
            self.assertTrue(all(not item.isVisible() for item in field.drafting_grid_items))
            for index, position in enumerate(((0.2, 0.2), (0.3, 0.3)), start=1):
                dot = Dot(f"dot{index}", f"D{index}", *position)
                item = DotItem(dot, field.scale_factor, "dot")
                item.setPos(field.field_to_scene(*position))
                item.setSelected(True)
                field.scene.addItem(item)
                field.dot_items[dot.id] = item
            field.apply_snap_to_selected()
            positions = [field.scene_to_field(item.pos()) for item in field.dot_items.values()]
            self.assertEqual(len(set(positions)), 2)
            for x, y in positions:
                self.assertAlmostEqual(x / settings.spacing_x, round(x / settings.spacing_x))
                self.assertAlmostEqual(y / settings.spacing_y, round(y / settings.spacing_y))
            field.set_drill_grid(DrillGridSettings(enabled=False))
            self.assertTrue(all(item.isVisible() for item in field.drafting_grid_items))
        finally:
            field.close()

    def test_field_dots_fit_side_by_side_at_one_eight_to_five_step(self) -> None:
        self.assertAlmostEqual(EIGHT_TO_FIVE_STEP_YARDS, 0.625)
        self.assertAlmostEqual(FIELD_DOT_VISUAL_DIAMETER_YARDS, 0.525)
        self.assertAlmostEqual(FIELD_DOT_GAP_AT_EIGHT_TO_FIVE_YARDS, 0.1)
        dot = Dot("dot1", "D1", 0.0, 0.0)
        item = DotItem(dot, 10.0, "circle")
        rendered_diameter = (item.rect().width() + item.pen().widthF()) / 10.0
        self.assertAlmostEqual(rendered_diameter, FIELD_DOT_VISUAL_DIAMETER_YARDS)
        self.assertGreater(EIGHT_TO_FIVE_STEP_YARDS - rendered_diameter, 0.09)
        self.assertAlmostEqual(item.rect().width() / 20.0, FIELD_DOT_RADIUS_YARDS)
        self.assertAlmostEqual(item.pen().widthF() / 10.0, FIELD_DOT_OUTLINE_YARDS)

    def test_grid_snaps_form_handles_and_generated_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Grid Forms", None, 160, 8, "4/4", 8)
            window = MainWindow(project_dir)
            try:
                window.select_dot_ids([dot.id for dot in window.project.dots])
                settings = DrillGridSettings(enabled=True, steps_per_five_x=8, steps_per_five_y=8)
                window.update_drill_grid_settings(settings, "Test Drill Grid")
                self.assertEqual(
                    window.field.snap_drill_grid_point((0.12, FRONT_HASH_YARDS)),
                    (0.0, FRONT_HASH_YARDS),
                )
                window.set_tool(EditorTool.CIRCLE)
                targets = window.formation_targets(EditorTool.CIRCLE)
                self.assertEqual(len(targets), len(window.project.dots))
                self.assertEqual(len(set(targets.values())), len(targets))
                self.assertTrue(all(settings.snap_point(point) == point for point in targets.values()))
                window.set_tool(EditorTool.LINE)
                snapped_endpoint = settings.snap_point((13.18, 4.82))
                window.preview_handle_moved("line_end", *snapped_endpoint)
                handles = window.formation_handles(EditorTool.LINE)
                self.assertEqual(handles["line_end"], snapped_endpoint)
                line_targets = window.formation_targets(EditorTool.LINE)
                self.assertTrue(all(settings.snap_point(point) == point for point in line_targets.values()))
                self.assertEqual(len(set(line_targets.values())), len(line_targets))
                window.line_endpoints = [(-10.0, FRONT_HASH_YARDS), (10.0, FRONT_HASH_YARDS)]
                hash_line_targets = window.formation_targets(EditorTool.LINE)
                self.assertTrue(all(y == FRONT_HASH_YARDS for _x, y in hash_line_targets.values()))
                window.imported_shape_points = [
                    (-0.5, -0.5),
                    (0.5, -0.5),
                    (0.5, 0.5),
                    (-0.5, 0.5),
                    (-0.5, -0.5),
                ]
                window.imported_shape_contours = []
                for tool in (
                    EditorTool.FREE_CURVE,
                    EditorTool.ARC,
                    EditorTool.ELLIPSE,
                    EditorTool.RECTANGLE,
                    EditorTool.TRIANGLE,
                    EditorTool.DIAMOND,
                    EditorTool.POLYGON,
                    EditorTool.STAR,
                    EditorTool.SPIRAL,
                    EditorTool.BLOCK,
                    EditorTool.SVG_SHAPE,
                    EditorTool.SCALE,
                    EditorTool.ROTATE,
                    EditorTool.WARP,
                    EditorTool.SCATTER,
                    EditorTool.MIRROR,
                    EditorTool.SHAPE_LINE,
                ):
                    window.set_tool(tool)
                    tool_targets = window.formation_targets(tool)
                    self.assertEqual(len(tool_targets), len(window.project.dots), tool.value)
                    self.assertEqual(len(set(tool_targets.values())), len(tool_targets), tool.value)
                    self.assertTrue(
                        all(settings.snap_point(point) == point for point in tool_targets.values()),
                        tool.value,
                    )
                plugin_targets = window.snap_form_mapping_to_grid(
                    {"plugin_a": (0.1, 0.1), "plugin_b": (0.15, 0.15)}
                )
                self.assertEqual(len(set(plugin_targets.values())), 2)
                self.assertTrue(all(settings.snap_point(point) == point for point in plugin_targets.values()))
                window.set_tool(EditorTool.CURVE)
                curve_handles = window.formation_handles(EditorTool.CURVE)
                self.assertIn("curve_on_1", curve_handles)
                self.assertIn("curve_on_2", curve_handles)
                self.assertNotIn("curve_control_1", curve_handles)
                raw_curve_handles = window.offset_curve_handles(*window.preview_center_offset)
                self.assertEqual(
                    curve_handles["curve_on_1"],
                    cubic_bezier_point(
                        raw_curve_handles["curve_start"],
                        raw_curve_handles["curve_control_1"],
                        raw_curve_handles["curve_control_2"],
                        raw_curve_handles["curve_end"],
                        1 / 3,
                    ),
                )
                self.assertEqual(
                    curve_handles["curve_on_2"],
                    cubic_bezier_point(
                        raw_curve_handles["curve_start"],
                        raw_curve_handles["curve_control_1"],
                        raw_curve_handles["curve_control_2"],
                        raw_curve_handles["curve_end"],
                        2 / 3,
                    ),
                )
                self.assertTrue(window.drill_grid_panel_toggle.isChecked())
                self.assertIn("8:5", window.drill_grid_toolbar_toggle.text())
                self.assertFalse(window.set_thumbnail(0).isNull())
                window.undo_stack.undo()
                self.assertFalse(window.field.drill_grid.enabled)
                window.undo_stack.redo()
                self.assertTrue(window.field.drill_grid.enabled)
            finally:
                window.close()

    def test_dot_card_coordinates_always_use_eight_to_five_steps(self) -> None:
        self.assertEqual(
            format_drill_coordinate(5.625, FRONT_HASH_YARDS + 0.625),
            ("1 step outside 45 S2", "1 step behind FH"),
        )
        self.assertEqual(
            format_drill_coordinate(-4.375, FRONT_HASH_YARDS - 0.625),
            ("1 step inside 45 S1", "1 step in front of FH"),
        )

    def test_set_one_form_then_drag_stays_committed_and_undoable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Set One Drag", None, 160, 8, "4/4", 8)
            window = MainWindow(project_dir)
            try:
                dot_ids = [dot.id for dot in window.project.dots]
                window.select_dot_ids(dot_ids)
                window.update_drill_grid_settings(DrillGridSettings(enabled=True), "Test Drill Grid")
                window.set_tool(EditorTool.CIRCLE)
                window.apply_formation(EditorTool.CIRCLE)
                dot_id = dot_ids[0]
                form_position = window.current_set().dot_positions[dot_id]
                dot = window.project.dot_by_id(dot_id)
                self.assertIsNotNone(dot)
                self.assertEqual((dot.x, dot.y), form_position)

                window.select_dot_ids([dot_id])
                moved_position = (form_position[0] + 0.625, form_position[1])
                window.field.dot_items[dot_id].setPos(window.field.field_to_scene(*moved_position))
                window.preview_dot_coordinates({dot_id: moved_position})
                self.assertEqual(window.dot_x.text(), window.inspector_coordinate_text(moved_position[0]))
                window.dot_moved(dot_id, *moved_position)
                self.assertEqual(window.current_set().dot_positions[dot_id], moved_position)
                self.assertEqual((dot.x, dot.y), moved_position)
                self.assertEqual(
                    window.field.scene_to_field(window.field.dot_items[dot_id].pos()),
                    moved_position,
                )

                window.undo_stack.undo()
                self.assertEqual(window.current_set().dot_positions[dot_id], form_position)
                window.undo_stack.redo()
                self.assertEqual(window.current_set().dot_positions[dot_id], moved_position)
            finally:
                window.close()

    def test_inspector_tracks_interpolated_playback_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Live Coordinates", None, 160, 8, "4/4", 4)
            window = MainWindow(project_dir)
            try:
                dot_id = window.project.dots[0].id
                opening = (window.project.dots[0].x, window.project.dots[0].y)
                window.current_set().dot_positions[dot_id] = (opening[0] + 5.0, opening[1] + 2.5)
                window.select_dot_ids([dot_id])
                midpoint = (window.current_set().start_count + window.current_set().end_count) / 2
                window.set_count(midpoint, seek_audio=False)
                displayed = window.field.scene_to_field(window.field.dot_items[dot_id].pos())
                self.assertEqual(window.dot_x.text(), window.inspector_coordinate_text(displayed[0]))
                self.assertEqual(window.dot_y.text(), window.inspector_coordinate_text(displayed[1]))
                self.assertEqual(
                    (window.dot_yardline.text(), window.dot_hash.text()),
                    format_drill_coordinate(*displayed),
                )
            finally:
                window.close()

    def test_previous_set_ghost_toggle_renders_and_hides_ghost_layer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Ghost Sets", None, 160, 8, "4/4", 6)
            project = load_project(project_dir)
            first_set = project.sets[0]
            second_set = type(first_set)(
                "Set 2",
                first_set.end_count + 1,
                first_set.end_count + first_set.duration_counts,
                dot_positions={
                    dot_id: (position[0] + 8.0, position[1])
                    for dot_id, position in first_set.dot_positions.items()
                },
            )
            project.sets.append(second_set)
            save_project(project_dir, project, backup=False)
            window = MainWindow(project_dir)
            try:
                window.set_ghosts_enabled(True)
                window.set_index = 1
                window.set_count(second_set.start_count, seek_audio=False)
                self.assertEqual(len(window.field.ghost_items), len(project.dots))
                ghost_positions = {
                    window.field.scene_to_field(item.pos())
                    for item in window.field.ghost_items
                }
                self.assertEqual(ghost_positions, set(first_set.dot_positions.values()))
                window.set_ghosts_enabled(False)
                self.assertFalse(window.field.ghost_items)
                window.set_ghosts_enabled(True)
                self.assertEqual(len(window.field.ghost_items), len(project.dots))
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
