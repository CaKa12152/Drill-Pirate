from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from drill_writer.core.analysis import detect_path_warnings
from drill_writer.core.coordinates import (
    BACK_HASH_YARDS,
    FIELD_HALF_HEIGHT_YARDS,
    FRONT_HASH_YARDS,
    format_drill_coordinate,
    format_steps,
    format_surface_coordinate,
    format_yardline_coordinate,
)
from drill_writer.core.models import (
    ChoreographyEvent,
    ContinuityInstruction,
    Dot,
    DrillProject,
    DrillSet,
    MotionRibbon,
    MovementStyle,
    ProjectMetadata,
    Prop,
    PropAttachment,
    SurfaceDefinition,
)
from drill_writer.core.path_validation import validate_authored_paths
from drill_writer.core.specialized_design import analyze_specialized_safety, surface_preset
from drill_writer.core.workflow import transition_candidates
from drill_writer.export.exporters import export_coordinate_csv
from drill_writer.ui.workflow_tools import SmartTransitionDialog


def two_picture_project(
    starts: dict[str, tuple[float, float]],
    ends: dict[str, tuple[float, float]],
) -> DrillProject:
    dots = [Dot(dot_id, dot_id, *point) for dot_id, point in starts.items()]
    project = DrillProject(
        ProjectMetadata("Correctness Reference", 120, 8, "4/4"),
        dots=dots,
        sets=[DrillSet("Set 1", 1, 8, dot_positions=dict(ends))],
    )
    project.ensure_set_positions()
    return project


class ConflictExplanationAndRepairTests(unittest.TestCase):
    def test_fixed_destination_collision_is_explained_as_unavoidable(self) -> None:
        project = two_picture_project(
            {"A": (-4.0, 0.0), "B": (4.0, 0.0)},
            {"A": (0.0, 0.0), "B": (0.5, 0.0)},
        )
        warnings = detect_path_warnings(project, 0, min_spacing=1.25, samples=20)
        warning = next(item for item in warnings if item.code == "fixed_destination_spacing")
        self.assertFalse(warning.avoidable)
        self.assertIn("destination picture", warning.explanation.lower())
        self.assertIn("spread", warning.suggestion.lower())

    def test_intermediate_collision_is_marked_repairable(self) -> None:
        project = two_picture_project(
            {"A": (-5.0, -1.0), "B": (-5.0, 1.0)},
            {"A": (5.0, 1.0), "B": (5.0, -1.0)},
        )
        warnings = detect_path_warnings(project, 0, min_spacing=1.25, samples=20)
        warning = next(item for item in warnings if item.code == "transition_spacing")
        self.assertTrue(warning.avoidable)
        self.assertIn("guided destination repair", warning.suggestion.lower())

    def test_guided_repair_preserves_picture_and_exposes_owner_swaps(self) -> None:
        project = two_picture_project(
            {"A": (-5.0, -1.0), "B": (-5.0, 1.0)},
            {"A": (5.0, 1.0), "B": (5.0, -1.0)},
        )
        targets = [project.sets[0].dot_positions[dot_id] for dot_id in ("A", "B")]
        candidates = transition_candidates(project, 0, ["A", "B"], targets)
        recommended = candidates[0]
        self.assertTrue(recommended.recommended)
        self.assertTrue(recommended.preserves_picture)
        self.assertEqual(recommended.changed_marchers, 2)
        self.assertEqual(len(recommended.reassignment_details), 2)
        self.assertCountEqual(recommended.positions.values(), targets)
        self.assertEqual(recommended.score.spacing_conflicts, 0)


class GuidedRepairUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_shows_swap_and_safety_evidence_before_apply(self) -> None:
        project = two_picture_project(
            {"A": (-5.0, -1.0), "B": (-5.0, 1.0)},
            {"A": (5.0, 1.0), "B": (5.0, -1.0)},
        )
        targets = [project.sets[0].dot_positions[dot_id] for dot_id in ("A", "B")]
        candidates = transition_candidates(project, 0, ["A", "B"], targets)
        previews = []
        dialog = SmartTransitionDialog(candidates, previews.append)
        try:
            dialog.table.selectRow(0)
            dialog.preview_selected()
            self.app.processEvents()
            self.assertEqual(dialog.table.columnCount(), 9)
            self.assertTrue(previews)
            self.assertIn("marcher(s) reassigned", dialog.details.text())
            self.assertIn("takes", dialog.details.text())
        finally:
            dialog.close()


class AuthoredPathValidationTests(unittest.TestCase):
    def test_manual_bezier_rejects_mismatched_and_oversized_handles(self) -> None:
        project = two_picture_project({"A": (-5.0, 0.0)}, {"A": (5.0, 0.0)})
        project.sets[0].path_anchors["A"] = [(0.0, 0.0), (2.0, 1.0)]
        project.sets[0].path_controls["A"] = [
            {"in": (90.0, 80.0), "out": (-90.0, -80.0)},
        ]
        issues = validate_authored_paths(project, 0)
        codes = {issue.code for issue in issues}
        self.assertIn("control_count_mismatch", codes)
        self.assertIn("oversized_handle", codes)

    def test_motion_ribbon_rejects_missing_performers_and_unsafe_handles(self) -> None:
        project = two_picture_project(
            {"A": (-4.0, -1.0), "B": (-4.0, 1.0)},
            {"A": (4.0, -1.0), "B": (4.0, 1.0)},
        )
        project.sets[0].motion_ribbons.append(
            MotionRibbon(
                "ribbon",
                "Unsafe Ribbon",
                ["A", "B", "MISSING"],
                [
                    {"point": (-4.0, 0.0), "out": (80.0, 60.0)},
                    {"point": (4.0, 0.0), "in": (-80.0, -60.0)},
                ],
            )
        )
        issues = validate_authored_paths(project, 0)
        codes = {issue.code for issue in issues}
        self.assertIn("missing_performer", codes)
        self.assertIn("oversized_handle", codes)


class BiomechanicalModelTests(unittest.TestCase):
    def test_direction_change_backward_halt_and_continuity_are_modeled(self) -> None:
        dot = Dot("A", "A", 0.0, 0.0, equipment="Flag", section="Guard", instrument="Guard")
        drill_set = DrillSet(
            "Set 1",
            1,
            8,
            dot_positions={"A": (10.0, 10.0)},
            count_positions={"A": {4.0: (10.0, 0.0)}},
            movement_styles={"A": MovementStyle.HALT},
            continuity=[ContinuityInstruction("c", ["A"], 1, 8, direction="forward")],
        )
        project = DrillProject(ProjectMetadata("Biomechanics", 120, 8, "4/4"), dots=[dot], sets=[drill_set])
        project.ensure_set_positions()
        warnings = analyze_specialized_safety(project, 0, samples=40)
        rules = {warning.rule for warning in warnings}
        self.assertIn("direction_change", rules)
        self.assertIn("halt_motion", rules)
        self.assertIn("continuity_direction", rules)

    def test_toss_equipment_and_prop_rotation_reduce_safe_motion(self) -> None:
        dot = Dot("G1", "G1", 0.0, 0.0, equipment="Large Flag", section="Guard", instrument="Guard")
        prop = Prop("wall", "Wall", "", width=14.0, height=4.0)
        drill_set = DrillSet("Set 1", 1, 8, dot_positions={"G1": (12.0, 0.0)})
        project = DrillProject(
            ProjectMetadata("Equipment", 120, 8, "4/4"),
            dots=[dot],
            props=[prop],
            sets=[drill_set],
            choreography=[ChoreographyEvent("toss", "Toss", "toss", ["G1"], 2, 6, revolutions=4)],
            prop_attachments=[
                PropAttachment("carry", "Wall Move", "wall", ["G1"], 1, 8, "rotate", "G1", rotation_rate=100.0)
            ],
        )
        project.ensure_set_positions()
        warnings = analyze_specialized_safety(project, 0, samples=32)
        rules = {warning.rule for warning in warnings}
        self.assertIn("toss_travel", rules)
        self.assertIn("prop_rotation", rules)
        self.assertIn("prop_handlers", rules)


class CoordinateReferenceMatrixTests(unittest.TestCase):
    def test_side_to_side_yard_lines_and_tie_rounding(self) -> None:
        self.assertEqual(format_yardline_coordinate(-5.0), "On 45 S1")
        self.assertEqual(format_yardline_coordinate(5.0), "On 45 S2")
        self.assertEqual(format_yardline_coordinate(7.5), "4 steps outside 45 S2")
        self.assertEqual(format_steps(1.125), "1.25")
        self.assertEqual(format_yardline_coordinate(0.01), "On 50")

    def test_front_and_back_hashes_are_the_only_vertical_references(self) -> None:
        self.assertEqual(format_drill_coordinate(0.0, FRONT_HASH_YARDS - 0.625)[1], "1 step in front of FH")
        self.assertEqual(format_drill_coordinate(0.0, BACK_HASH_YARDS + 0.625)[1], "1 step behind BH")
        self.assertEqual(format_drill_coordinate(0.0, -FIELD_HALF_HEIGHT_YARDS)[1], "32 steps in front of FH")
        self.assertEqual(format_drill_coordinate(0.0, FIELD_HALF_HEIGHT_YARDS)[1], "32 steps behind BH")

    def test_goal_line_and_end_zone_coordinates(self) -> None:
        self.assertEqual(format_yardline_coordinate(50.0), "On G S2")
        self.assertEqual(format_yardline_coordinate(-50.0), "On G S1")
        self.assertEqual(format_yardline_coordinate(55.0), "8 steps into end zone S2")
        self.assertEqual(format_yardline_coordinate(-55.0), "8 steps into end zone S1")
        self.assertEqual(format_yardline_coordinate(50.01), "On G S2")

    def test_indoor_and_parade_reference_coordinates(self) -> None:
        indoor = surface_preset("indoor")
        self.assertEqual(
            format_surface_coordinate(indoor, 2.5, -3.0),
            ("2.50 yd Side 2 of Center Line", "3.00 yd in front of Center"),
        )
        parade = SurfaceDefinition(
            name="Straight Parade",
            surface_type="parade",
            width_yards=100,
            height_yards=20,
            endzone_depth_yards=0,
            route_points=[(0.0, 0.0), (100.0, 0.0)],
            route_width_yards=8,
        )
        self.assertEqual(
            format_surface_coordinate(parade, 25.0, 2.0),
            ("Station 25.00 yd", "2.00 yd left of route center"),
        )

    def test_csv_uses_the_same_audited_coordinate_formatter(self) -> None:
        project = two_picture_project({"A": (0.0, 0.0)}, {"A": (55.0, FRONT_HASH_YARDS)})
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "coordinates.csv"
            export_coordinate_csv(output, project)
            with output.open(newline="", encoding="utf-8") as file:
                row = next(csv.DictReader(file))
        self.assertEqual(row["yard_line_coordinate"], "8 steps into end zone S2")
        self.assertEqual(row["hash_coordinate"], "On FH")


if __name__ == "__main__":
    unittest.main()
