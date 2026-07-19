from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from drill_writer.core.accelerators import (
    ArrayOptions,
    ParallelFormOptions,
    alternating_selection,
    array_target_points,
    assign_targets_minimum_cost,
    create_live_symmetry_record,
    describe_measurements,
    expand_live_symmetry_changes,
    parallel_form_target_points,
    rank_file_target_points,
)
from drill_writer.core.models import ConstructionGuide
from drill_writer.core.project_io import (
    create_project_folder,
    load_project,
    load_project_preview,
    save_project,
)
from drill_writer.ui.design_accelerators import (
    AlternatingSelectionDialog,
    ArrayDialog,
    LiveSymmetryDialog,
    ParallelFormDialog,
    RankFileDialog,
    ReferenceAnnotationsDialog,
)
from drill_writer.ui.main_window import MainWindow


def assert_point(test: unittest.TestCase, actual, expected, places: int = 5) -> None:
    test.assertAlmostEqual(actual[0], expected[0], places=places)
    test.assertAlmostEqual(actual[1], expected[1], places=places)


class AcceleratorGeometryTests(unittest.TestCase):
    def test_linear_polar_row_and_path_arrays_preserve_exact_count(self) -> None:
        source = [(-2.0, 0.0), (2.0, 0.0), (-2.0, 2.0), (2.0, 2.0), (-2.0, 4.0), (2.0, 4.0)]
        for options, path in (
            (ArrayOptions(mode="linear", copies=3, spacing_x=12.0), None),
            (ArrayOptions(mode="polar", copies=3, radius=10.0), None),
            (ArrayOptions(mode="rows", copies=3, columns=2, spacing_x=8.0, spacing_y=6.0), None),
            (ArrayOptions(mode="path", copies=3), [(-12.0, -4.0), (0.0, 4.0), (12.0, -4.0)]),
        ):
            targets = array_target_points(source, len(source), options, path)
            self.assertEqual(len(targets), len(source))
            for index in range(0, len(targets), 2):
                distance = ((targets[index + 1][0] - targets[index][0]) ** 2 + (targets[index + 1][1] - targets[index][1]) ** 2) ** 0.5
                self.assertAlmostEqual(distance, 4.0, places=4)

    def test_array_rejects_uneven_motif_counts(self) -> None:
        with self.assertRaisesRegex(ValueError, "divisible"):
            array_target_points([(float(index), 0.0) for index in range(5)], 5, ArrayOptions(copies=2))

    def test_parallel_and_rank_file_builders_balance_performers(self) -> None:
        master = [(-10.0, 0.0), (10.0, 0.0)]
        parallel = parallel_form_target_points(
            master,
            7,
            ParallelFormOptions(ranks=3, interval=2.0, placement="centered"),
        )
        self.assertEqual(len(parallel), 7)
        self.assertEqual(sorted({round(point[1], 5) for point in parallel}), [-2.0, 0.0, 2.0])
        ranks = rank_file_target_points(master, 8, 2, 3.0)
        self.assertEqual(len(ranks), 8)
        self.assertEqual(sorted({round(point[1], 5) for point in ranks}), [-1.5, 1.5])

    def test_global_assignment_uses_every_target_once(self) -> None:
        starts = {"A": (0.0, 0.0), "B": (10.0, 0.0), "C": (20.0, 0.0)}
        assignment = assign_targets_minimum_cost(list(starts), starts, [(19.0, 0.0), (1.0, 0.0), (11.0, 0.0)])
        self.assertEqual(set(assignment), set(starts))
        self.assertEqual(set(assignment.values()), {(1.0, 0.0), (11.0, 0.0), (19.0, 0.0)})
        assert_point(self, assignment["A"], (1.0, 0.0))
        assert_point(self, assignment["B"], (11.0, 0.0))
        assert_point(self, assignment["C"], (19.0, 0.0))

    def test_live_symmetry_pairs_globally_and_mirrors_edits(self) -> None:
        positions = {"L1": (-8.0, -2.0), "L2": (-4.0, 3.0), "R1": (8.0, -2.0), "R2": (4.0, 3.0), "C": (0.0, 1.0)}
        record = create_live_symmetry_record(list(positions), positions, (0.0, 0.0), 90.0)
        self.assertEqual({frozenset(pair) for pair in record["pairs"]}, {frozenset(("L1", "R1")), frozenset(("L2", "R2"))})
        self.assertEqual(record["center_ids"], ["C"])
        expanded = expand_live_symmetry_changes([record], positions, {"L2": (-6.0, 5.0), "C": (2.0, 4.0)})
        assert_point(self, expanded["R2"], (6.0, 5.0))
        assert_point(self, expanded["C"], (0.0, 4.0))

    def test_live_symmetry_keeps_explicit_pair_mirrored(self) -> None:
        before = {"L": (-2.0, 0.0), "R": (2.0, 0.0)}
        record = create_live_symmetry_record(list(before), before, (0.0, 0.0), 90.0)
        expanded = expand_live_symmetry_changes([record], before, {"L": (-5.0, 3.0), "R": (7.0, 1.0)})
        assert_point(self, expanded["L"], (-7.0, 1.0))
        assert_point(self, expanded["R"], (7.0, 1.0))

    def test_alternating_selection_modes(self) -> None:
        positions = {
            "A": (0.0, 0.0),
            "B": (10.0, 0.0),
            "C": (10.0, 10.0),
            "D": (0.0, 10.0),
            "E": (5.0, 5.0),
            "F": (6.0, 5.0),
        }
        ids = list(positions)
        self.assertEqual(len(alternating_selection(ids, positions, "every", every=2)), 3)
        self.assertEqual(len(alternating_selection(ids, positions, "endpoints")), 2)
        self.assertEqual(set(alternating_selection(ids, positions, "corners", count=4)), {"A", "B", "C", "D"})
        self.assertEqual(alternating_selection(ids, positions, "nearest", count=1, anchor=(5.0, 5.0)), ["E"])
        ranks = {"A": "1", "B": "1", "C": "2", "D": "2", "E": "3", "F": "3"}
        self.assertEqual(set(alternating_selection(ids, positions, "odd_ranks", ranks=ranks)), {"A", "B", "E", "F"})
        self.assertEqual(set(alternating_selection(ids, positions, "even_ranks", ranks=ranks)), {"C", "D"})

    def test_measurement_summary_reports_field_units(self) -> None:
        summary = describe_measurements([(0.0, 0.0), (3.0, 4.0)], [8.0, 12.0], duration_counts=6)
        self.assertAlmostEqual(summary["minimum_interval_yards"], 5.0)
        self.assertAlmostEqual(summary["total_form_length_yards"], 5.0)
        self.assertAlmostEqual(summary["maximum_travel_yards"], 12.0)
        self.assertAlmostEqual(summary["maximum_yards_per_count"], 2.0)


class AcceleratorPersistenceTests(unittest.TestCase):
    def test_reference_annotations_round_trip_and_load_in_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "References", None, 160, 8, "4/4", 4)
            project = load_project(project_dir)
            annotation = ConstructionGuide(
                "annotation-1",
                "Guard Staging",
                "annotation_box",
                [(-8.0, -4.0), (8.0, 4.0)],
                color="#7c3aed",
                metadata={
                    "category": "reference",
                    "text": "Guard entrance",
                    "fill_color": "#ddd6fe",
                    "opacity": 0.7,
                    "set_index": 0,
                },
            )
            project.guides.append(annotation)
            project.workflow["live_symmetry"] = [{"id": "sym-test", "pairs": [], "enabled": True}]
            save_project(project_dir, project, backup=False)
            restored = load_project(project_dir)
            preview = load_project_preview(project_dir)
            self.assertEqual(restored.guides[-1], annotation)
            self.assertEqual(preview.guides[-1], annotation)


class AcceleratorUiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_dialogs_fit_common_laptop_widths(self) -> None:
        dialogs = [
            ArrayDialog(12, True),
            ParallelFormDialog(12),
            RankFileDialog(12, True),
            LiveSymmetryDialog((0.0, 0.0)),
            AlternatingSelectionDialog(4, 12),
            ReferenceAnnotationsDialog([], (0.0, 0.0), 0),
        ]
        try:
            for dialog in dialogs:
                self.assertLessEqual(dialog.minimumSizeHint().width(), 1100)
        finally:
            for dialog in dialogs:
                dialog.close()

    def test_main_window_exposes_accelerators_and_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Accelerator UI", None, 160, 8, "4/4", 6)
            window = MainWindow(project_dir)
            try:
                labels = [window.tools_tabs.tabText(index) for index in range(window.tools_tabs.count())]
                self.assertIn("Accelerate", labels)
                dot_ids = [dot.id for dot in window.project.dots[:3]]
                window.select_dot_ids(dot_ids)
                window.set_measurement_overlay(True, "all")
                self.assertTrue(window.field.measurement_items)
                window.set_measurement_overlay(False, "all")
                self.assertFalse(window.field.measurement_items)
            finally:
                window.close()

    def test_reference_scope_filters_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Reference UI", None, 160, 8, "4/4", 4)
            window = MainWindow(project_dir)
            try:
                window.project.guides.extend(
                    [
                        ConstructionGuide(
                            "all-note",
                            "All Sets",
                            "annotation_note",
                            [(0.0, 0.0), (1.0, 0.0)],
                            metadata={"text": "All", "set_index": -1},
                        ),
                        ConstructionGuide(
                            "set-note",
                            "Set Two",
                            "annotation_note",
                            [(2.0, 0.0), (3.0, 0.0)],
                            metadata={"text": "Two", "set_index": 1},
                        ),
                    ]
                )
                window.field.set_reference_set_index(0)
                window.field.rebuild_guides()
                self.assertIn("all-note", window.field.guide_items)
                self.assertNotIn("set-note", window.field.guide_items)
                window.field.set_reference_set_index(1)
                self.assertIn("all-note", window.field.guide_items)
                self.assertIn("set-note", window.field.guide_items)
            finally:
                window.close()

    def test_live_symmetry_edit_is_undoable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Symmetry Undo", None, 160, 8, "4/4", 2)
            window = MainWindow(project_dir)
            try:
                first, second = [dot.id for dot in window.project.dots]
                before = dict(window.current_set().dot_positions)
                window.project.workflow["live_symmetry"] = [
                    {
                        "id": "sym-test",
                        "name": "Test",
                        "axis_point": [0.0, 0.0],
                        "axis_angle": 90.0,
                        "pairs": [[first, second]],
                        "center_ids": [],
                        "enabled": True,
                    }
                ]
                window.apply_positions({first: (-10.0, 3.0)})
                assert_point(self, window.current_set().dot_positions[first], (-10.0, 3.0))
                assert_point(self, window.current_set().dot_positions[second], (10.0, 3.0))
                window.undo_stack.undo()
                assert_point(self, window.current_set().dot_positions[first], before[first])
                assert_point(self, window.current_set().dot_positions[second], before[second])
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
