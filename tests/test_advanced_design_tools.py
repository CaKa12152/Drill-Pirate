from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGraphicsItem

from drill_writer.core.analysis import build_conflict_timeline, detect_path_warnings
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
    path_length,
)
from drill_writer.core.design_tools import (
    MorphOptions,
    create_motion_ribbon,
    guide_contains_point,
    guide_path,
    motion_ribbon_by_id,
    plan_formation_morph,
    plan_motion_ribbon,
)
from drill_writer.core.models import (
    ConstructionGuide,
    ContinuityInstruction,
    Dot,
    DrillProject,
    DrillSet,
    ProjectMetadata,
)
from drill_writer.core.project_io import create_project_folder, load_project, save_project
from drill_writer.export.exporters import move_instruction_export_label
from drill_writer.ui.main_window import MainWindow


def assert_point(test: unittest.TestCase, actual, expected, places: int = 5) -> None:
    test.assertAlmostEqual(actual[0], expected[0], places=places)
    test.assertAlmostEqual(actual[1], expected[1], places=places)


class CadPathTests(unittest.TestCase):
    def test_complete_cad_toolkit_operations(self) -> None:
        first = [(0.0, 0.0), (5.0, 0.0)]
        second = [(10.0, 5.0), (5.0, 0.0)]
        self.assertEqual(cad_join([first, second]), [(0.0, 0.0), (5.0, 0.0), (10.0, 5.0)])
        left, right = cad_split([(0.0, 0.0), (10.0, 0.0)], 0.25)
        assert_point(self, left[-1], (2.5, 0.0))
        assert_point(self, right[0], (2.5, 0.0))
        trimmed = cad_trim([(0.0, 0.0), (10.0, 0.0)], 0.2, 0.8)
        assert_point(self, trimmed[0], (2.0, 0.0))
        assert_point(self, trimmed[-1], (8.0, 0.0))
        extended = cad_extend(first, 2.0, 3.0)
        assert_point(self, extended[0], (-2.0, 0.0))
        assert_point(self, extended[-1], (8.0, 0.0))
        offset = cad_offset(first, 2.0)
        assert_point(self, offset[0], (0.0, 2.0))
        self.assertEqual(cad_reverse(first), list(reversed(first)))
        noisy = [(0.0, 0.0), (2.0, 0.03), (4.0, -0.02), (6.0, 0.0)]
        self.assertEqual(len(cad_simplify(noisy, 0.1)), 2)
        self.assertGreater(len(cad_smooth([(0.0, 0.0), (5.0, 5.0), (10.0, 0.0)], 2)), 3)
        filleted = cad_fillet([(0.0, 0.0), (5.0, 0.0), (5.0, 5.0)], 1.0, 5)
        self.assertGreater(len(filleted), 3)
        self.assertGreater(path_length(filleted), 8.0)


class MotionRibbonTests(unittest.TestCase):
    def test_group_ribbon_preserves_exact_endpoints_and_shared_curve(self) -> None:
        starts = {"A": (-2.0, 0.0), "B": (0.0, 0.0), "C": (2.0, 0.0)}
        ends = {"A": (8.0, 8.0), "B": (10.0, 8.0), "C": (12.0, 8.0)}
        ribbon = create_motion_ribbon("r1", "Brass", list(starts), starts, ends, bend=8.0)
        plan = plan_motion_ribbon(ribbon, starts, ends, 1.0, 9.0)
        for dot_id in starts:
            assert_point(self, plan.paths[dot_id][0], starts[dot_id])
            assert_point(self, plan.paths[dot_id][-1], ends[dot_id])
        midpoint = len(plan.paths["B"]) // 2
        self.assertGreater(abs(plan.paths["B"][midpoint][1] - 4.0), 2.0)
        interval = (
            (plan.paths["A"][midpoint][0] - plan.paths["B"][midpoint][0]) ** 2
            + (plan.paths["A"][midpoint][1] - plan.paths["B"][midpoint][1]) ** 2
        ) ** 0.5
        self.assertAlmostEqual(interval, 2.0, delta=0.2)
        self.assertIn(1.25, plan.count_positions["A"])

    def test_ribbon_direction_facing_changes_along_curve(self) -> None:
        starts = {"A": (-1.0, 0.0), "B": (1.0, 0.0)}
        ends = {"A": (9.0, 10.0), "B": (11.0, 10.0)}
        ribbon = create_motion_ribbon(
            "r1", "Rank", list(starts), starts, ends, bend=10.0, face_direction=True
        )
        plan = plan_motion_ribbon(ribbon, starts, ends, 1.0, 9.0)
        facings = list(plan.count_facings["A"].values())
        self.assertGreater(max(facings) - min(facings), 15.0)

    def test_400_marcher_ribbon_plans_without_ui_stall(self) -> None:
        starts = {f"D{index}": (float(index % 40), float(index // 40)) for index in range(400)}
        ends = {dot_id: (point[0] + 20.0, point[1] + 8.0) for dot_id, point in starts.items()}
        ribbon = create_motion_ribbon("big", "Full Ensemble", list(starts), starts, ends, bend=12.0)
        started = time.perf_counter()
        plan = plan_motion_ribbon(ribbon, starts, ends, 1.0, 17.0)
        self.assertLess(time.perf_counter() - started, 3.0)
        self.assertEqual(len(plan.paths), 400)


class FormationMorphTests(unittest.TestCase):
    def test_morph_preserves_picture_and_section_relationships(self) -> None:
        starts = {"T1": (-4.0, 0.0), "T2": (-2.0, 0.0), "B1": (2.0, 0.0), "B2": (4.0, 0.0)}
        ends = {"T1": (0.0, 4.0), "T2": (0.0, 6.0), "B1": (0.0, 10.0), "B2": (0.0, 12.0)}
        sections = {"T1": "Trumpets", "T2": "Trumpets", "B1": "Baritones", "B2": "Baritones"}
        plan = plan_formation_morph(
            list(starts), starts, ends, sections, 1.0, 9.0, MorphOptions(0.9, 0.8, 4, True)
        )
        for dot_id in starts:
            assert_point(self, plan.paths[dot_id][0], starts[dot_id])
            assert_point(self, plan.paths[dot_id][-1], ends[dot_id])
        midpoint = len(plan.paths["T1"]) // 2
        trumpet_interval = (
            (plan.paths["T2"][midpoint][0] - plan.paths["T1"][midpoint][0]) ** 2
            + (plan.paths["T2"][midpoint][1] - plan.paths["T1"][midpoint][1]) ** 2
        ) ** 0.5
        self.assertAlmostEqual(trumpet_interval, 2.0, delta=0.45)


class ContinuityAndGuideTests(unittest.TestCase):
    def make_project(self) -> DrillProject:
        dots = [Dot("A", "A", -4.0, 0.0), Dot("B", "B", 4.0, 0.0)]
        drill_set = DrillSet(
            "Set 1",
            1,
            8,
            dot_positions={"A": (4.0, 0.0), "B": (-4.0, 0.0)},
        )
        project = DrillProject(ProjectMetadata("Advanced", 160, 8, "4/4"), dots=dots, sets=[drill_set])
        project.ensure_set_positions()
        return project

    def test_continuity_round_trip_and_export_label(self) -> None:
        project = self.make_project()
        instruction = ContinuityInstruction(
            "c1", ["A"], 3.0, 6.0, "6-to-5", "crab_left", 90.0, 45.0, "Lift on count 5"
        )
        project.sets[0].continuity.append(instruction)
        payload = project.sets[0].to_json()
        restored = DrillSet.from_json(payload)
        self.assertEqual(restored.continuity[0], instruction)
        label = move_instruction_export_label(restored, "A")
        self.assertIn("3-6", label)
        self.assertIn("Crab Left", label)
        self.assertIn("Lift on count 5", label)

    def test_no_go_guides_are_measured_and_analyzed(self) -> None:
        project = self.make_project()
        guide = ConstructionGuide(
            "g1", "Prop Safety", "no_go_rectangle", [(-1.0, -2.0), (1.0, 2.0)]
        )
        project.guides.append(guide)
        self.assertTrue(guide_contains_point(guide, (0.0, 0.0)))
        self.assertEqual(guide_path(guide)[0], (-1.0, -2.0))
        warnings = detect_path_warnings(project, 0, samples=25)
        self.assertTrue(any(warning.severity == "no_go" for warning in warnings))
        timeline = build_conflict_timeline(project, 0, samples=25)
        self.assertTrue(any(entry.no_go_conflicts for entry in timeline))

    def test_schema_four_saves_guides_ribbons_and_continuity(self) -> None:
        project = self.make_project()
        project.guides.append(ConstructionGuide("g1", "Center", "center", [(0.0, 0.0)]))
        project.sets[0].continuity.append(ContinuityInstruction("c1", ["A"], 1, 4))
        starts = {dot.id: (dot.x, dot.y) for dot in project.dots}
        ends = project.sets[0].dot_positions
        project.sets[0].motion_ribbons.append(
            create_motion_ribbon("r1", "Pair", ["A", "B"], starts, ends)
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "audio").mkdir()
            (root / "props").mkdir()
            save_project(root, project, backup=False)
            loaded = load_project(root)
            self.assertEqual(loaded.guides[0].id, "g1")
            self.assertEqual(loaded.sets[0].continuity[0].id, "c1")
            self.assertEqual(loaded.sets[0].motion_ribbons[0].id, "r1")


class AdvancedDesignUiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_exposes_motion_tools_and_guides(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "UI Smoke", None, 160, 8, "4/4", 8)
            window = MainWindow(project_dir)
            try:
                labels = [window.tools_tabs.tabText(index) for index in range(window.tools_tabs.count())]
                self.assertIn("Motion", labels)
                self.assertTrue(hasattr(window, "motion_ribbon_list"))
                guide = ConstructionGuide("g1", "Line", "line", [(-5.0, 0.0), (5.0, 0.0)])
                window.project.guides.append(guide)
                window.field.rebuild_guides()
                self.assertIn("g1", window.field.guide_items)
            finally:
                window.close()

    def test_group_handle_drag_is_single_undoable_edit_and_locks_dot_motion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Ribbon Undo", None, 160, 8, "4/4", 4)
            window = MainWindow(project_dir)
            try:
                dot_ids = [dot.id for dot in window.project.dots]
                starts = {dot.id: (dot.x, dot.y) for dot in window.project.dots}
                for dot_id, point in starts.items():
                    window.current_set().dot_positions[dot_id] = (point[0] + 12.0, point[1] + 4.0)
                ribbon = create_motion_ribbon("r1", "Rank", dot_ids, starts, window.current_set().dot_positions, bend=4.0)
                window.current_set().motion_ribbons.append(ribbon)
                window.apply_motion_ribbon_plan(ribbon)
                window.active_motion_ribbon_id = ribbon.id
                window.show_motion_ribbon_editor(ribbon)
                movable = QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                self.assertTrue(all(not bool(item.flags() & movable) for item in window.field.dot_items.values()))
                original = tuple(ribbon.nodes[1]["point"])
                window.move_motion_ribbon_handle("motion_ribbon_node:r1:1", original[0] + 1.0, original[1] + 2.0, 0, False)
                self.assertEqual(window.undo_stack.count(), 0)
                window.move_motion_ribbon_handle("motion_ribbon_node:r1:1", original[0] + 2.0, original[1] + 3.0, 0, True)
                self.assertEqual(window.undo_stack.count(), 1)
                window.undo_stack.undo()
                restored = motion_ribbon_by_id(window.current_set().motion_ribbons, "r1")
                self.assertIsNotNone(restored)
                assert_point(self, restored.nodes[1]["point"], original)
                window.undo_stack.redo()
                redone = motion_ribbon_by_id(window.current_set().motion_ribbons, "r1")
                assert_point(self, redone.nodes[1]["point"], (original[0] + 2.0, original[1] + 3.0))
            finally:
                window.close()

    def test_inspector_scrolls_instead_of_compressing_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Panel Layout", None, 160, 8, "4/4", 30)
            window = MainWindow(project_dir)
            try:
                window.resize(1366, 768)
                window.show()
                for _ in range(6):
                    self.app.processEvents()

                inspector_scroll = window.dock_widgets["inspector"].widget()
                inspector_content = inspector_scroll.widget()
                window.field.scene.clearSelection()
                window.selection_changed()
                for _ in range(4):
                    self.app.processEvents()
                empty_height = inspector_content.height()

                next(iter(window.field.dot_items.values())).setSelected(True)
                window.selection_changed()
                for _ in range(6):
                    self.app.processEvents()

                self.assertGreater(inspector_content.height(), empty_height)
                self.assertGreater(inspector_scroll.verticalScrollBar().maximum(), 0)
                for control in (
                    window.dot_name,
                    window.dot_section,
                    window.dot_instrument,
                    window.dot_rank,
                    window.dot_equipment,
                    window.dot_layer,
                    window.dot_x,
                    window.dot_y,
                    window.transform_offset_x,
                    window.transform_offset_y,
                    window.transform_rotation,
                ):
                    self.assertGreaterEqual(control.height(), 22)

                window.inspector_tabs.setCurrentIndex(window.inspector_tabs.indexOf(window.sets_tab))
                for _ in range(4):
                    self.app.processEvents()
                self.assertGreaterEqual(window.set_list.height(), 170)
                self.assertGreaterEqual(window.set_name.height(), 22)

                window.inspector_tabs.setCurrentIndex(window.inspector_tabs.indexOf(window.visibility_tab))
                for _ in range(4):
                    self.app.processEvents()
                self.assertEqual(inspector_scroll.verticalScrollBar().maximum(), 0)
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
