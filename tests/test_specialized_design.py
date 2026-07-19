from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from drill_writer.core.animation import interpolate_props
from drill_writer.core.coordinates import format_surface_coordinate
from drill_writer.core.models import (
    ChoreographyEvent,
    Dot,
    DrillProject,
    DrillSet,
    PerformerPhysicalLimits,
    ProjectMetadata,
    Prop,
    PropAttachment,
)
from drill_writer.core.project_io import PROJECT_SCHEMA_VERSION, create_project_folder, load_project, save_project
from drill_writer.core.specialized_design import (
    analyze_specialized_safety,
    closest_route_position,
    equipment_for_dot_at_count,
    physical_limits_for_dot,
    set_physical_limits,
    surface_contains_point,
    surface_preset,
    validate_choreography,
)
from drill_writer.ui.field_view import FieldView
from drill_writer.ui.main_window import MainWindow
from drill_writer.ui.specialized_design import SpecializedDesignStudioDialog


def specialized_project() -> DrillProject:
    dots = [
        Dot("TU1", "TU1", -4, 0, instrument="Tuba", section="Brass"),
        Dot("G1", "G1", 4, 0, instrument="Guard", section="Guard", equipment="Flag"),
    ]
    prop = Prop("prop1", "Rolling Wall", "", 0, -2, 6, 3)
    project = DrillProject(
        ProjectMetadata("Specialized", 120, 8, "4/4"),
        dots=dots,
        props=[prop],
        sets=[
            DrillSet("Set 1", 1, 8, dot_positions={"TU1": (-4, 0), "G1": (4, 0)}, prop_positions={"prop1": {"x": 0, "y": -2, "width": 6, "height": 3, "rotation": 0}}),
            DrillSet("Set 2", 9, 16, dot_positions={"TU1": (16, 0), "G1": (8, 0)}, prop_positions={"prop1": {"x": 0, "y": -2, "width": 6, "height": 3, "rotation": 0}}),
        ],
    )
    project.ensure_set_positions()
    return project


class SurfaceAndCoordinateTests(unittest.TestCase):
    def test_surface_presets_cover_football_indoor_parade_and_staging(self) -> None:
        college = surface_preset("college")
        high_school = surface_preset("high_school")
        indoor = surface_preset("indoor")
        parade = surface_preset("parade")
        staging = surface_preset("staging")
        self.assertAlmostEqual(college.front_hash_yards, -6.6665)
        self.assertAlmostEqual(high_school.front_hash_yards, -8.8888)
        self.assertEqual(indoor.surface_type, "indoor")
        self.assertGreaterEqual(len(parade.route_points), 2)
        self.assertEqual(staging.surface_type, "staging")

    def test_custom_surface_bounds_and_coordinates_are_surface_aware(self) -> None:
        indoor = surface_preset("indoor")
        self.assertTrue(surface_contains_point(indoor, (14.9, 9.9)))
        self.assertFalse(surface_contains_point(indoor, (16, 0)))
        self.assertEqual(format_surface_coordinate(indoor, 2.5, -3), ("X +2.50 yd from center", "Y -3.00 yd from center"))
        football = surface_preset("high_school")
        self.assertEqual(format_surface_coordinate(football, 0, football.front_hash_yards), ("On 50", "On FH"))

    def test_parade_coordinates_report_station_and_route_side(self) -> None:
        parade = surface_preset("parade")
        station, side, nearest = closest_route_position(parade, (-30, 2))
        self.assertGreater(station, 20)
        self.assertGreater(abs(side), 0)
        self.assertEqual(len(nearest), 2)
        coordinate = format_surface_coordinate(parade, -30, 2)
        self.assertTrue(coordinate[0].startswith("Station "))
        self.assertIn("route", coordinate[1])


class ChoreographyAndAttachmentTests(unittest.TestCase):
    def test_equipment_changes_persist_as_a_count_based_track(self) -> None:
        project = specialized_project()
        project.choreography.append(ChoreographyEvent("change", "Flag to Rifle", "equipment_change", ["G1"], 5, 6, "Flag", "Rifle"))
        self.assertEqual(equipment_for_dot_at_count(project, "G1", 5), "Flag")
        self.assertEqual(equipment_for_dot_at_count(project, "G1", 6), "Rifle")
        self.assertEqual(validate_choreography(project), [])

    def test_invalid_and_overlapping_guard_events_are_rejected(self) -> None:
        project = specialized_project()
        project.choreography.extend(
            [
                ChoreographyEvent("a", "Toss", "toss", ["G1"], 4, 6, revolutions=5),
                ChoreographyEvent("b", "Change", "equipment_change", ["G1"], 5, 7),
            ]
        )
        errors = validate_choreography(project)
        self.assertTrue(any("destination equipment" in error for error in errors))
        self.assertTrue(any("overlaps" in error for error in errors))

    def test_carry_attachment_tracks_performer_through_playback(self) -> None:
        project = specialized_project()
        project.prop_attachments.append(PropAttachment("link", "Carry Wall", "prop1", ["TU1"], 9, 16, "carry", "TU1", 1, -1))
        state = interpolate_props(project, 1, 12.5)["prop1"]
        self.assertAlmostEqual(state["x"], 7.0, places=2)
        self.assertAlmostEqual(state["y"], -1.0, places=2)

    def test_direction_of_travel_rotates_attached_prop(self) -> None:
        project = specialized_project()
        project.sets[1].dot_positions["G1"] = (4, -12)
        project.prop_attachments.append(
            PropAttachment("link", "Push", "prop1", ["G1"], 9, 16, "push", "G1", rotation_behavior="direction_of_travel")
        )
        state = interpolate_props(project, 1, 12)["prop1"]
        self.assertLess(abs(state["rotation"]), 1.0)


class PhysicalLimitTests(unittest.TestCase):
    def test_instrument_profiles_and_performer_overrides_resolve(self) -> None:
        project = specialized_project()
        tuba = physical_limits_for_dot(project, "TU1")
        guard = physical_limits_for_dot(project, "G1")
        self.assertLess(tuba.max_yards_per_count, guard.max_yards_per_count)
        set_physical_limits(project, PerformerPhysicalLimits("TU1", max_yards_per_count=2.25))
        self.assertEqual(physical_limits_for_dot(project, "TU1").max_yards_per_count, 2.25)

    def test_analysis_flags_instrument_speed_toss_and_recovery(self) -> None:
        project = specialized_project()
        project.choreography.extend(
            [
                ChoreographyEvent("toss", "Seven", "toss", ["G1"], 10, 12, revolutions=8),
                ChoreographyEvent("spin", "Immediate Spin", "spin", ["G1"], 12, 13),
            ]
        )
        warnings = analyze_specialized_safety(project, 1, samples=12)
        rules = {warning.rule for warning in warnings}
        self.assertIn("speed", rules)
        self.assertIn("toss", rules)
        self.assertIn("recovery", rules)


class SpecializedPersistenceAndUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_schema_six_round_trips_specialized_design(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Special Save", None, 120, 8, "4/4", 2)
            project = load_project(project_dir)
            project.surface = surface_preset("parade")
            project.choreography = [ChoreographyEvent("event", "Toss", "toss", [project.dots[0].id], 1, 3, revolutions=3)]
            prop = Prop("prop", "Carry", "")
            project.props.append(prop)
            project.ensure_set_positions()
            project.prop_attachments = [PropAttachment("link", "Carry", "prop", [project.dots[0].id], 1, 8)]
            project.physical_limits = [PerformerPhysicalLimits(project.dots[0].id, max_yards_per_count=1.1)]
            save_project(project_dir, project, backup=False)
            restored = load_project(project_dir)
            self.assertEqual(PROJECT_SCHEMA_VERSION, 6)
            self.assertEqual(restored.surface, project.surface)
            self.assertEqual(restored.choreography, project.choreography)
            self.assertEqual(restored.prop_attachments, project.prop_attachments)
            self.assertEqual(restored.physical_limits, project.physical_limits)
            show = json.loads((project_dir / "show.json").read_text(encoding="utf-8"))
            self.assertEqual(show["schema_version"], 6)

    def test_old_project_migrates_with_default_surface_and_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Migration", None, 120, 8, "4/4", 2)
            show_path = project_dir / "show.json"
            show = json.loads(show_path.read_text(encoding="utf-8"))
            for key in ("surface", "choreography", "prop_attachments", "physical_limits"):
                show.pop(key, None)
            show["schema_version"] = 5
            show["version"] = 5
            show_path.write_text(json.dumps(show), encoding="utf-8")
            restored = load_project(project_dir)
            self.assertEqual(restored.surface.surface_type, "football")
            self.assertEqual(restored.choreography, [])

    def test_field_view_and_studio_support_specialized_surfaces(self) -> None:
        project = specialized_project()
        project.surface = surface_preset("indoor")
        field = FieldView()
        dialog = SpecializedDesignStudioDialog(project, ["G1"], ["prop1"], 1, "props")
        try:
            field.set_project(project)
            scene_rect = field.scene.sceneRect()
            self.assertGreater(scene_rect.width(), project.surface.width_yards * field.scale_factor)
            self.assertEqual(dialog.tabs.count(), 4)
            self.assertEqual(dialog.tabs.currentIndex(), 2)
            self.assertLessEqual(dialog.minimumSizeHint().width(), 1100)
        finally:
            dialog.close()
            field.close()

    def test_main_window_exposes_specialized_workspace_and_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Special UI", None, 120, 8, "4/4", 4)
            window = MainWindow(project_dir)
            try:
                labels = [window.tools_tabs.tabText(index) for index in range(window.tools_tabs.count())]
                self.assertIn("Specialized", labels)
                window.apply_workspace("specialized")
                self.assertIs(window.tools_tabs.currentWidget(), window.specialized_tab)
                self.assertIs(window.choreography_timeline.project, window.project)
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
