from __future__ import annotations

import unittest
import tempfile
import json
import zipfile
import csv
from pathlib import Path

from drill_writer.core.analysis import auto_plan_paths, build_conflict_timeline, detect_path_warnings
from drill_writer.core.animation import interpolate_dot_facings, interpolate_project
from drill_writer.core.assignment import (
    collision_aware_target_assignment,
    evaluate_assignment_quality,
    minimum_cost_target_assignment,
    minimum_synchronous_distance,
    ordered_targets,
)
from drill_writer.core.constraints import make_relative_metadata, solve_constraints
from drill_writer.core.coordinates import BACK_HASH_YARDS, FRONT_HASH_YARDS, format_drill_coordinate
from drill_writer.core.diagnostics import export_bug_report_bundle
from drill_writer.core.models import Dot, DotConstraint, DrillProject, DrillSet, Marker, ProjectMetadata
import drill_writer.core.plugin_manager as plugin_manager_module
from drill_writer.core.plugin_manager import PLUGIN_API_VERSION, PluginManifest
from drill_writer.core.project_io import (
    PROJECT_SCHEMA_VERSION,
    ProjectLoadError,
    create_project_backup,
    create_project_folder,
    default_dots,
    default_props,
    load_project,
    parse_instrumentation_roster,
    restore_project_backup,
)
from drill_writer.core.tools import bezier_curve_positions, circle_positions, distance, elliptical_arc_positions, freeform_curve_positions, path_length, rectangle_positions, sampled_spline_path, solid_paths_positions, star_positions, warped_positions
from drill_writer.core.timing import audio_ms_for_set_count, set_count_for_audio_ms, set_index_for_count
from drill_writer.core.updater import ReleaseAsset, checksum_asset_urls, choose_windows_asset, verify_downloaded_asset, write_windows_zip_update_script
from drill_writer.core.workflow import TransformParameters, assignment_for_mode, generate_sets_from_markers, ripple_set_indices, transform_positions, transition_candidates
from drill_writer.core.large_show import (
    CleanupOptions,
    cleanup_formation,
    create_group,
    create_linked_formation,
    expand_linked_position_changes,
    generate_hierarchical_groups,
    group_dot_ids,
    locked_group_dot_ids,
    parse_roster_csv,
    save_formation_variation,
    swap_performers,
    transfer_project_content,
    variation_positions,
)
from drill_writer.export.exporters import encode_mp4_frames, export_coordinate_csv, parse_ffmpeg_encoder_names, video_encoder_args, Mp4ExportOptions, Mp4FrameRenderResult


class CoordinateAuditTests(unittest.TestCase):
    def test_yardline_and_hash_language(self) -> None:
        self.assertEqual(format_drill_coordinate(5, FRONT_HASH_YARDS), ("On 45 S2", "On FH"))
        self.assertEqual(format_drill_coordinate(-5, BACK_HASH_YARDS), ("On 45 S1", "On BH"))
        self.assertEqual(format_drill_coordinate(0, 0), ("On 50", "10.75 steps behind FH"))
        self.assertEqual(
            format_drill_coordinate(5.625, FRONT_HASH_YARDS + 0.625),
            ("1 step outside 45 S2", "1 step behind FH"),
        )
        self.assertEqual(format_drill_coordinate(0, -25), ("On 50", "29.25 steps in front of FH"))
        self.assertEqual(format_drill_coordinate(0, 3), ("On 50", "5.75 steps in front of BH"))


class CollisionAwareAssignmentTests(unittest.TestCase):
    def test_reassigns_crossing_transition_without_changing_target_picture(self) -> None:
        starts = [(-5.0, -1.0), (-5.0, 1.0)]
        targets = [(5.0, 1.0), (5.0, -1.0)]
        assignment = collision_aware_target_assignment(starts, targets, move_durations=[8.0, 8.0])
        before = evaluate_assignment_quality(starts, targets, [0, 1], move_durations=[8.0, 8.0])
        after = evaluate_assignment_quality(starts, targets, assignment, move_durations=[8.0, 8.0])
        self.assertEqual(assignment, [1, 0])
        self.assertEqual(after.collisions, 0)
        self.assertLess(after.collisions, before.collisions)
        self.assertCountEqual([targets[index] for index in assignment], targets)

    def test_staggered_crossing_is_not_misreported_as_a_collision(self) -> None:
        closest = minimum_synchronous_distance(
            (-5.0, 0.0),
            (5.0, 0.0),
            (0.0, 0.45),
            (0.0, -5.0),
            (0.0, 5.0),
            (0.55, 1.0),
        )
        self.assertGreater(closest, 1.25)

    def test_eased_staggered_timing_uses_playback_curve(self) -> None:
        first_start = (-5.3779, 0.2743)
        first_target = (6.0805, 5.6914)
        second_start = (-1.9606, -7.3131)
        second_target = (-5.6339, 5.6678)
        first_window = (0.3883, 0.7937)
        second_window = (0.3665, 0.5635)
        linear = minimum_synchronous_distance(
            first_start,
            first_target,
            first_window,
            second_start,
            second_target,
            second_window,
            "linear",
        )
        eased = minimum_synchronous_distance(
            first_start,
            first_target,
            first_window,
            second_start,
            second_target,
            second_window,
            "ease_in_out",
        )
        self.assertGreater(linear, 1.25)
        self.assertLess(eased, 1.25)

    def test_stationary_obstacle_changes_destination_ownership(self) -> None:
        starts = [(-5.0, -3.0), (-5.0, 3.0)]
        targets = [(5.0, -3.0), (5.0, 3.0)]
        windows = [(0.0, 0.45), (0.55, 1.0)]
        obstacles = [((0.0, -3.0), (0.0, -3.0), (0.0, 1.0))]
        assignment = collision_aware_target_assignment(
            starts,
            targets,
            motion_windows=windows,
            move_durations=[4.0, 4.0],
            obstacles=obstacles,
        )
        before = evaluate_assignment_quality(
            starts,
            targets,
            [0, 1],
            motion_windows=windows,
            move_durations=[4.0, 4.0],
            obstacles=obstacles,
        )
        after = evaluate_assignment_quality(
            starts,
            targets,
            assignment,
            motion_windows=windows,
            move_durations=[4.0, 4.0],
            obstacles=obstacles,
        )
        self.assertLess(after.collisions, before.collisions)
        self.assertCountEqual([targets[index] for index in assignment], targets)

    def test_dense_form_assignment_preserves_all_slots_and_reduces_conflicts(self) -> None:
        count = 120
        columns = 12
        starts = [
            ((index % columns - columns / 2) * 1.7, (index // columns - 5) * 1.7)
            for index in range(count)
        ]
        targets = rectangle_positions(count, (8.0, 2.0), 46.0, 18.0, filled=True)
        baseline = list(range(count))
        assignment = collision_aware_target_assignment(
            starts,
            targets,
            move_durations=[16.0] * count,
        )
        before = evaluate_assignment_quality(starts, targets, baseline, move_durations=[16.0] * count)
        after = evaluate_assignment_quality(starts, targets, assignment, move_durations=[16.0] * count)
        self.assertLessEqual(after.collisions, before.collisions)
        self.assertEqual(after.collisions, 0)
        self.assertCountEqual([targets[index] for index in assignment], targets)

    def test_project_assignment_does_not_edit_manual_paths(self) -> None:
        dots = [Dot("a", "A", -5.0, -1.0), Dot("b", "B", -5.0, 1.0)]
        drill_set = DrillSet(
            "Set 1",
            1,
            8,
            dot_positions={"a": (5.0, 1.0), "b": (5.0, -1.0)},
            path_anchors={"a": [(0.0, 4.0)]},
        )
        project = DrillProject(ProjectMetadata("Collision Test", 160, 8, "4/4"), dots=dots, sets=[drill_set])
        before_paths = json.dumps(drill_set.path_anchors, sort_keys=True)
        positions = assignment_for_mode(
            project,
            0,
            ["a", "b"],
            [(5.0, 1.0), (5.0, -1.0)],
            "lowest_collision",
        )
        self.assertCountEqual(positions.values(), [(5.0, 1.0), (5.0, -1.0)])
        self.assertEqual(json.dumps(drill_set.path_anchors, sort_keys=True), before_paths)


class ExportEncoderTests(unittest.TestCase):
    def test_parses_ffmpeg_video_encoders(self) -> None:
        output = """
 V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC
 V..... mpeg4               MPEG-4 part 2
 A..... aac                 AAC
"""
        encoders = parse_ffmpeg_encoder_names(output)
        self.assertIn("libx264", encoders)
        self.assertIn("mpeg4", encoders)
        self.assertNotIn("aac", encoders)

    def test_mpeg4_fallback_uses_quality_scale(self) -> None:
        args = video_encoder_args("mpeg4", Mp4ExportOptions(crf=18))
        self.assertEqual(args, ["-c:v", "mpeg4", "-q:v", "3"])

    def test_ffmpeg_directory_path_reports_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "actual ffmpeg.exe"):
                encode_mp4_frames(
                    Path(temp),
                    Path(temp) / "show.mp4",
                    Mp4FrameRenderResult(total_frames=1, audio_path=None),
                    ffmpeg_path=temp,
                )


class UpdaterHardeningTests(unittest.TestCase):
    def test_checksum_assets_map_to_release_asset_names(self) -> None:
        checksums = checksum_asset_urls(
            [
                {"name": "DrillPirate-Windows.zip", "browser_download_url": "https://example/app.zip"},
                {"name": "DrillPirate-Windows.zip.sha256", "browser_download_url": "https://example/app.zip.sha256"},
            ]
        )
        self.assertEqual(checksums["DrillPirate-Windows.zip"], "https://example/app.zip.sha256")

    def test_windows_asset_prefers_windows_installer(self) -> None:
        asset = choose_windows_asset(
            [
                ReleaseAsset("DrillPirate-macos.zip", "mac"),
                ReleaseAsset("DrillPirate-Windows.exe", "win"),
            ]
        )
        self.assertIsNotNone(asset)
        assert asset is not None
        self.assertEqual(asset.name, "DrillPirate-Windows.exe")

    def test_invalid_zip_update_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "DrillPirate-Windows.zip"
            package.write_text("not a zip", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "ZIP is invalid"):
                verify_downloaded_asset(package, ReleaseAsset(package.name, "", size=package.stat().st_size))

    def test_zip_update_script_contains_rollback_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "DrillPirate-Windows.zip"
            package.write_bytes(b"placeholder")
            script = write_windows_zip_update_script(package)
            text = script.read_text(encoding="utf-8")
            self.assertIn("DrillPirateRollback_", text)
            self.assertIn("Copy-Item -Path (Join-Path $backup \"*\")", text)


class PluginManifestTests(unittest.TestCase):
    def test_manifest_defaults_to_supported_api_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plugin_dir = Path(temp)
            (plugin_dir / "plugin.json").write_text(
                json.dumps({"id": "My Plugin", "name": "My Plugin"}),
                encoding="utf-8",
            )
            manifest = PluginManifest.from_path(plugin_dir)
        self.assertIsNotNone(manifest)
        assert manifest is not None
        self.assertEqual(manifest.id, "my_plugin")
        self.assertEqual(manifest.api_version, PLUGIN_API_VERSION)
        self.assertEqual(manifest.permissions, ["ui", "project_read"])

    def test_manifest_normalizes_declared_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plugin_dir = Path(temp)
            (plugin_dir / "plugin.json").write_text(
                json.dumps(
                    {
                        "id": "perm_plugin",
                        "permissions": ["Project Write", "file-write", "network"],
                    }
                ),
                encoding="utf-8",
            )
            manifest = PluginManifest.from_path(plugin_dir)
        self.assertIsNotNone(manifest)
        assert manifest is not None
        self.assertEqual(manifest.permissions, ["project_write", "file_write", "network"])

    def test_future_api_plugin_is_skipped_not_loaded(self) -> None:
        old_root = plugin_manager_module.PLUGIN_ROOT
        with tempfile.TemporaryDirectory() as temp:
            plugin_manager_module.PLUGIN_ROOT = Path(temp)
            try:
                plugin_dir = Path(temp) / "future_plugin"
                plugin_dir.mkdir()
                (plugin_dir / "plugin.json").write_text(
                    json.dumps(
                        {
                            "id": "future_plugin",
                            "name": "Future Plugin",
                            "entry": "plugin.py",
                            "api_version": "99.0",
                            "permissions": ["ui"],
                        }
                    ),
                    encoding="utf-8",
                )
                (plugin_dir / "plugin.py").write_text("def activate(context):\n    raise RuntimeError('should not load')\n", encoding="utf-8")
                manager = plugin_manager_module.PluginManager("")
                manager.set_active("future_plugin", True)
                self.assertNotIn("future_plugin", manager.loaded_modules)
                self.assertIn("not compatible", manager.diagnostics_text())
            finally:
                plugin_manager_module.PLUGIN_ROOT = old_root


class ProjectCreationDefaultsTests(unittest.TestCase):
    def test_count_only_projects_leave_roster_fields_unassigned(self) -> None:
        dots = default_dots(4)
        self.assertTrue(all(dot.instrument == "" for dot in dots))
        self.assertTrue(all(dot.section == "" for dot in dots))

    def test_instrumentation_uses_compact_unique_labels(self) -> None:
        roster = parse_instrumentation_roster(
            "Flute=5\nTrumpet=5\nTrombone=5\nTuba=5\nMellophone=5"
        )
        dots = default_dots(25, instrumentation=roster)
        self.assertEqual([dot.name for dot in dots[:5]], ["F1", "F2", "F3", "F4", "F5"])
        self.assertEqual([dot.name for dot in dots[5:10]], ["T1", "T2", "T3", "T4", "T5"])
        self.assertEqual([dot.name for dot in dots[10:15]], ["TR1", "TR2", "TR3", "TR4", "TR5"])
        self.assertEqual([dot.name for dot in dots[15:20]], ["TU1", "TU2", "TU3", "TU4", "TU5"])
        self.assertEqual([dot.name for dot in dots[20:25]], ["M1", "M2", "M3", "M4", "M5"])

    def test_roster_can_define_instrument_and_section_separately(self) -> None:
        roster = parse_instrumentation_roster("Trumpet | Upper Brass = 3\nSnare | Battery = 2")
        dots = default_dots(5, instrumentation=roster)
        self.assertEqual([dot.instrument for dot in dots], ["Trumpet"] * 3 + ["Snare"] * 2)
        self.assertEqual([dot.section for dot in dots], ["Upper Brass"] * 3 + ["Battery"] * 2)

    def test_simple_roster_infers_broad_sections(self) -> None:
        dots = default_dots(2, instrumentation=parse_instrumentation_roster("Flute=1\nTrumpet=1"))
        self.assertEqual([(dot.instrument, dot.section) for dot in dots], [("Flute", "Woodwinds"), ("Trumpet", "Brass")])

    def test_generated_front_ensemble_and_dm_props(self) -> None:
        props = default_props(front_ensemble_count=2, drum_major_stands=1)
        self.assertEqual([prop.name for prop in props], ["FE1", "FE2", "DM Stand 1"])
        self.assertEqual(props[0].layer, "Front Ensemble")
        self.assertEqual(props[-1].layer, "Drum Major")


class ProjectSafetyTests(unittest.TestCase):
    def test_old_project_migrates_with_backup_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Old Show", None, 120, 8, "4/4", marcher_count=3)
            (project_dir / "show.json").unlink()
            (project_dir / "props.json").unlink()
            project = load_project(project_dir)
            self.assertEqual(project.metadata.show_title, "Old Show")
            show = json.loads((project_dir / "show.json").read_text(encoding="utf-8"))
            self.assertEqual(show["schema_version"], PROJECT_SCHEMA_VERSION)
            self.assertTrue(any((project_dir / ".drill_pirate_backups").glob("*_migration.zip")))

    def test_invalid_schema_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Bad Schema", None, 120, 8, "4/4", marcher_count=1)
            show = json.loads((project_dir / "show.json").read_text(encoding="utf-8"))
            show["schema_version"] = "not-a-number"
            (project_dir / "show.json").write_text(json.dumps(show), encoding="utf-8")
            with self.assertRaises(ProjectLoadError):
                load_project(project_dir)

    def test_restore_bad_backup_rolls_current_files_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Restore Safe", None, 120, 8, "4/4", marcher_count=1)
            original_metadata = (project_dir / "metadata.json").read_text(encoding="utf-8")
            bad_backup = Path(temp) / "bad_backup.zip"
            with zipfile.ZipFile(bad_backup, "w") as archive:
                archive.writestr("metadata.json", original_metadata)
                archive.writestr("dots.json", (project_dir / "dots.json").read_text(encoding="utf-8"))
                archive.writestr("sets.json", "{bad json")
            with self.assertRaises(ProjectLoadError):
                restore_project_backup(project_dir, bad_backup)
            self.assertEqual((project_dir / "metadata.json").read_text(encoding="utf-8"), original_metadata)

    def test_restore_valid_backup_recovers_previous_save(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Restore Good", None, 120, 8, "4/4", marcher_count=1)
            backup = create_project_backup(project_dir, reason="test")
            metadata = json.loads((project_dir / "metadata.json").read_text(encoding="utf-8"))
            metadata["show_title"] = "Changed"
            (project_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            assert backup is not None
            restore_project_backup(project_dir, backup)
            restored = json.loads((project_dir / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(restored["show_title"], "Restore Good")

    def test_bug_report_bundle_includes_settings_plugins_and_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Bug Bundle", None, 120, 8, "4/4", marcher_count=1)
            output = Path(temp) / "bug_report.zip"
            export_bug_report_bundle(output, project_dir=project_dir, extra={"case": "test"})
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("diagnostics.json", names)
                self.assertIn("settings.json", names)
                self.assertIn("plugins.json", names)
                self.assertIn("project/metadata.json", names)


class CoordinateExportTests(unittest.TestCase):
    def test_coordinate_csv_exports_set_one_destination_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = DrillProject(
                metadata=ProjectMetadata("Coordinates", 120, 8, "4/4"),
                dots=[Dot("a", "A", 0, 0)],
                sets=[DrillSet("Set 1", 1, 8, dot_positions={"a": (5, 0)})],
            )
            output = Path(temp) / "coordinates.csv"
            export_coordinate_csv(output, project)
            with output.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(rows[0]["x"], "5.000")
            self.assertEqual(rows[0]["yard_line_coordinate"], "On 45 S2")


class AssignmentTests(unittest.TestCase):
    def test_closed_order_assignment_rotates_to_nearest_start(self) -> None:
        starts = [(-10, 0), (-5, 0), (0, 0), (5, 0)]
        targets = [(5, 0), (0, 5), (-5, 0), (0, -5)]
        assigned = ordered_targets(starts, targets, allow_reverse=True, allow_rotation=True)
        self.assertEqual(assigned[0], (-5, 0))
        self.assertLess(
            sum((start[0] - target[0]) ** 2 + (start[1] - target[1]) ** 2 for start, target in zip(starts, assigned)),
            sum((start[0] - target[0]) ** 2 + (start[1] - target[1]) ** 2 for start, target in zip(starts, targets)),
        )

    def test_minimum_cost_assignment_considers_every_marcher(self) -> None:
        starts = [(0, 0), (2, 0), (20, 0)]
        targets = [(2, 0), (20, 0), (21, 0)]
        assignment = minimum_cost_target_assignment(starts, targets)
        assigned = [targets[index] for index in assignment]
        self.assertEqual(assigned, [(2, 0), (20, 0), (21, 0)])

    def test_minimum_cost_assignment_avoids_greedy_target_theft(self) -> None:
        starts = [(0.0, 0.0), (1.0, 0.0), (9.0, 0.0)]
        targets = [(0.9, 0.0), (2.0, 0.0), (9.0, 0.0)]
        assignment = minimum_cost_target_assignment(starts, targets)
        assigned = [targets[index] for index in assignment]
        self.assertEqual(assigned, [(0.9, 0.0), (2.0, 0.0), (9.0, 0.0)])


class FormationGeometryTests(unittest.TestCase):
    def test_warped_positions_bends_middle_without_losing_spacing_order(self) -> None:
        positions = [(0, 0), (5, 0), (10, 0)]
        anchors = [(0, 0), (5, 6), (10, 0)]
        warped = warped_positions(positions, anchors, strength=1.0)
        self.assertEqual([round(x, 3) for x, _y in warped], [0, 5, 10])
        self.assertGreater(warped[1][1], warped[0][1])
        self.assertGreater(warped[1][1], warped[2][1])

    def test_solid_circle_includes_inside_points(self) -> None:
        hollow = circle_positions(12, (0, 0), 10, filled=False)
        solid = circle_positions(12, (0, 0), 10, filled=True)
        self.assertEqual(len(solid), 12)
        self.assertTrue(all(round((x * x + y * y) ** 0.5, 3) == 10 for x, y in hollow))
        self.assertTrue(any((x * x + y * y) ** 0.5 < 5 for x, y in solid))

    def test_solid_rectangle_and_svg_path_fill(self) -> None:
        rectangle = rectangle_positions(20, (0, 0), 20, 10, filled=True)
        self.assertEqual(len(rectangle), 20)
        self.assertTrue(all(-10 <= x <= 10 and -5 <= y <= 5 for x, y in rectangle))
        square_path = [[(-10, -5), (10, -5), (10, 5), (-10, 5), (-10, -5)]]
        filled_svg = solid_paths_positions(square_path, 10)
        self.assertEqual(len(filled_svg), 10)
        self.assertTrue(all(-10 <= x <= 10 and -5 <= y <= 5 for x, y in filled_svg))

    def test_star_generation_supports_hollow_and_solid(self) -> None:
        hollow = star_positions(15, (0, 0), 12, 5, 5, filled=False)
        solid = star_positions(15, (0, 0), 12, 5, 5, filled=True)
        self.assertEqual(len(hollow), 15)
        self.assertEqual(len(solid), 15)
        self.assertTrue(any((x * x + y * y) ** 0.5 < 6 for x, y in solid))

    def test_freeform_curve_spaces_marchers_evenly_on_custom_curve(self) -> None:
        anchors = [(-30, -10), (-15, 12), (8, -8), (26, 16), (35, -2)]
        positions = freeform_curve_positions(24, anchors, closed=False)
        self.assertEqual(len(positions), 24)
        gaps = [distance(positions[index], positions[index + 1]) for index in range(len(positions) - 1)]
        average_gap = sum(gaps) / len(gaps)
        self.assertLess(max(abs(gap - average_gap) for gap in gaps), average_gap * 0.28)
        self.assertAlmostEqual(positions[0][0], anchors[0][0], delta=0.01)
        self.assertAlmostEqual(positions[-1][0], anchors[-1][0], delta=0.01)

    def test_closed_freeform_curve_creates_smooth_loop_path(self) -> None:
        anchors = [(-12, 0), (-3, 10), (9, 8), (15, -4), (2, -12)]
        path = sampled_spline_path(anchors, closed=True)
        positions = freeform_curve_positions(20, anchors, closed=True)
        self.assertEqual(len(positions), 20)
        self.assertGreater(path_length(path), 55)
        self.assertLess(distance(path[0], path[-1]), 0.001)

    def test_bezier_curve_tool_uses_even_path_spacing(self) -> None:
        positions = bezier_curve_positions(18, (-30, 0), (-18, 22), (12, -18), (30, 0))
        self.assertEqual(len(positions), 18)
        gaps = [distance(positions[index], positions[index + 1]) for index in range(len(positions) - 1)]
        average_gap = sum(gaps) / len(gaps)
        self.assertLess(max(abs(gap - average_gap) for gap in gaps), average_gap * 0.22)
        self.assertLess(min(y for _x, y in positions), -3)
        self.assertGreater(max(y for _x, y in positions), 3)

    def test_elliptical_arc_tool_spaces_evenly_and_supports_rotation(self) -> None:
        positions = elliptical_arc_positions(16, (0, 0), 50, 24, 200, 140, rotation_degrees=12)
        self.assertEqual(len(positions), 16)
        gaps = [distance(positions[index], positions[index + 1]) for index in range(len(positions) - 1)]
        average_gap = sum(gaps) / len(gaps)
        self.assertLess(max(abs(gap - average_gap) for gap in gaps), average_gap * 0.18)
        self.assertGreater(max(x for x, _y in positions) - min(x for x, _y in positions), 35)


class ConstraintTests(unittest.TestCase):
    def test_pivot_constraint_preserves_relative_offsets(self) -> None:
        positions = {"a": (0.0, 0.0), "b": (2.0, 0.0), "c": (4.0, 0.0)}
        metadata = make_relative_metadata(["a", "b", "c"], positions, pivot_id="a")
        moved = dict(positions)
        moved["a"] = (10.0, 5.0)
        solved = solve_constraints(
            moved,
            [DotConstraint("Pivot", "pivot", ["a", "b", "c"], metadata=metadata)],
            changed_dot_ids={"a"},
        )
        self.assertEqual(solved["b"], (12.0, 5.0))
        self.assertEqual(solved["c"], (14.0, 5.0))


class CollisionTimelineTests(unittest.TestCase):
    def test_detects_spacing_speed_and_crossing(self) -> None:
        project = DrillProject(
            metadata=ProjectMetadata("Test", 120, 8, "4/4"),
            dots=[
                Dot("a", "A", -5, 0),
                Dot("b", "B", 5, 0),
                Dot("c", "C", 0, 10),
            ],
            sets=[
                DrillSet(
                    "Set 1",
                    1,
                    1,
                    dot_positions={"a": (-5, 0), "b": (5, 0), "c": (0, 10)},
                ),
                DrillSet(
                    "Set 2",
                    2,
                    4,
                    dot_positions={"a": (5, 0), "b": (-5, 0), "c": (0, -10)},
                ),
            ],
        )
        project.ensure_set_positions()
        warnings = detect_path_warnings(project, 1, min_spacing=1.0, max_yards_per_count=2.0)
        self.assertTrue(any(warning.severity == "crossing" for warning in warnings))
        self.assertTrue(any(warning.severity == "speed" for warning in warnings))
        timeline = build_conflict_timeline(project, 1, min_spacing=1.0, max_yards_per_count=2.0)
        self.assertTrue(any(entry.total > 0 for entry in timeline))

    def test_set_one_movement_is_analyzed_and_auto_planned(self) -> None:
        project = DrillProject(
            metadata=ProjectMetadata("Set One Analysis", 120, 8, "4/4"),
            dots=[
                Dot("a", "A", -5, -1),
                Dot("b", "B", -5, 1),
            ],
            sets=[
                DrillSet(
                    "Set 1",
                    1,
                    8,
                    dot_positions={"a": (5, 1), "b": (5, -1)},
                ),
            ],
        )
        project.ensure_set_positions()
        warnings = detect_path_warnings(project, 0, min_spacing=1.0, max_yards_per_count=0.5)
        self.assertTrue(any(warning.severity == "crossing" for warning in warnings))
        self.assertTrue(any(warning.severity == "speed" for warning in warnings))
        timeline = build_conflict_timeline(project, 0, min_spacing=1.0, max_yards_per_count=0.5)
        self.assertTrue(any(entry.total > 0 for entry in timeline))
        self.assertEqual(auto_plan_paths(project, 0, ["a", "b"], min_spacing=1.0), 1)
        self.assertTrue(project.sets[0].path_anchors)


class PlaybackBoundaryTests(unittest.TestCase):
    def test_set_one_can_move_from_opening_positions(self) -> None:
        project = DrillProject(
            metadata=ProjectMetadata("Set One Move", 120, 8, "4/4"),
            dots=[Dot("a", "A", 0, 0)],
            sets=[
                DrillSet(
                    "Set 1",
                    1,
                    8,
                    dot_positions={"a": (8, 0)},
                    dot_facings={"a": 90},
                )
            ],
        )
        project.ensure_set_positions()
        self.assertEqual(interpolate_project(project, 0, 1)["a"], (0, 0))
        middle = interpolate_project(project, 0, 4.5)["a"]
        self.assertGreater(middle[0], 0)
        self.assertLess(middle[0], 8)
        self.assertEqual(interpolate_project(project, 0, 8)["a"], (8, 0))
        self.assertEqual(interpolate_dot_facings(project, 0, 1)["a"], 0)
        self.assertEqual(interpolate_dot_facings(project, 0, 8)["a"], 90)

    def test_set_one_move_window_can_delay_movement(self) -> None:
        project = DrillProject(
            metadata=ProjectMetadata("Set One Delayed Move", 120, 8, "4/4"),
            dots=[Dot("a", "A", 0, 0)],
            sets=[
                DrillSet(
                    "Set 1",
                    1,
                    8,
                    dot_positions={"a": (8, 0)},
                    move_timings={"a": {"start": 5.0, "end": 8.0}},
                )
            ],
        )
        project.ensure_set_positions()
        self.assertEqual(interpolate_project(project, 0, 4)["a"], (0, 0))
        middle = interpolate_project(project, 0, 6)["a"]
        self.assertGreater(middle[0], 0)
        self.assertLess(middle[0], 8)

    def test_set_boundary_has_no_position_teleport(self) -> None:
        project = DrillProject(
            metadata=ProjectMetadata("Boundary", 120, 4, "4/4"),
            dots=[Dot("a", "A", 0, 0)],
            sets=[
                DrillSet("Set 1", 1, 4, dot_positions={"a": (0, 0)}),
                DrillSet("Set 2", 5, 16, dot_positions={"a": (12, 0)}),
            ],
        )
        project.ensure_set_positions()
        before_boundary = interpolate_project(project, 0, 4.99)["a"]
        at_boundary = interpolate_project(project, 1, 5.0)["a"]
        just_after = interpolate_project(project, 1, 5.01)["a"]
        self.assertEqual(before_boundary, (0, 0))
        self.assertEqual(at_boundary, (0, 0))
        self.assertGreater(just_after[0], 0)
        self.assertLess(just_after[0], 0.02)

    def test_audio_clock_mapping_round_trips_arbitrary_timestamp(self) -> None:
        from drill_writer.core.models import TimingEvent

        project = DrillProject(
            metadata=ProjectMetadata("Timing", 120, 8, "4/4"),
            dots=[Dot("a", "A", 0, 0)],
            sets=[
                DrillSet("Set 1", 1, 8, dot_positions={"a": (0, 0)}),
                DrillSet("Set 2", 9, 16, dot_positions={"a": (8, 0)}),
            ],
            timing_events=[
                TimingEvent("anchor", 1, milliseconds=1000),
                TimingEvent("anchor", 9, milliseconds=5000),
            ],
        )
        set_index, count = set_count_for_audio_ms(project, 3000)
        self.assertEqual(set_index, 0)
        self.assertAlmostEqual(count, 5.0, places=2)
        self.assertEqual(audio_ms_for_set_count(project, set_index, count), 3000)

    def test_boundary_count_selects_next_set(self) -> None:
        project = DrillProject(
            metadata=ProjectMetadata("Boundary Index", 120, 4, "4/4"),
            dots=[Dot("a", "A", 0, 0)],
            sets=[
                DrillSet("Set 1", 1, 4, dot_positions={"a": (0, 0)}),
                DrillSet("Set 2", 5, 8, dot_positions={"a": (8, 0)}),
            ],
        )
        self.assertEqual(set_index_for_count(project, 4.99), 0)
        self.assertEqual(set_index_for_count(project, 5.0), 1)


class WorkflowAccelerationTests(unittest.TestCase):
    def workflow_project(self) -> DrillProject:
        dots = [
            Dot("t1", "T1", -6, 0, section="Trumpets", rank="R1"),
            Dot("t2", "T2", -2, 0, section="Trumpets", rank="R1"),
            Dot("m1", "M1", 2, 0, section="Mellos", rank="R2"),
            Dot("m2", "M2", 6, 0, section="Mellos", rank="R2"),
        ]
        project = DrillProject(
            metadata=ProjectMetadata("Workflow", 120, 8, "4/4"),
            dots=dots,
            sets=[
                DrillSet("Set 1", 1, 8, dot_positions={dot.id: (dot.x, dot.y) for dot in dots}),
                DrillSet(
                    "Set 2",
                    9,
                    16,
                    dot_positions={"t1": (6, 8), "t2": (2, 8), "m1": (-2, 8), "m2": (-6, 8)},
                ),
                DrillSet(
                    "Set 3",
                    17,
                    24,
                    dot_positions={"t1": (6, 12), "t2": (2, 12), "m1": (-2, 12), "m2": (-6, 12)},
                ),
            ],
        )
        project.ensure_set_positions()
        return project

    def test_unified_transform_supports_scale_rotate_and_offset(self) -> None:
        positions = {"a": (-1, 0), "b": (1, 0)}
        transformed = transform_positions(
            positions,
            TransformParameters(offset_x=2, offset_y=3, rotation_degrees=90, scale_x=2, scale_y=1),
        )
        self.assertAlmostEqual(transformed["a"][0], 2.0, places=5)
        self.assertAlmostEqual(transformed["a"][1], 1.0, places=5)
        self.assertAlmostEqual(transformed["b"][1], 5.0, places=5)

    def test_transition_composer_returns_scored_complete_assignments(self) -> None:
        project = self.workflow_project()
        ids = [dot.id for dot in project.dots]
        targets = [project.sets[1].dot_positions[dot_id] for dot_id in ids]
        candidates = transition_candidates(project, 1, ids, targets)
        keys = {candidate.key for candidate in candidates}
        self.assertIn("shortest", keys)
        self.assertIn("section", keys)
        self.assertIn("lowest_collision", keys)
        for candidate in candidates:
            self.assertEqual(set(candidate.positions), set(ids))
            self.assertGreaterEqual(candidate.score.weighted_score, 0)

    def test_ripple_scopes_find_forward_keyframe_and_matching_sets(self) -> None:
        project = self.workflow_project()
        project.sets[2].count_positions["t1"] = {20.0: (1, 1)}
        self.assertEqual(ripple_set_indices(project, 0, "forward", ["t1"]), [0, 1, 2])
        self.assertEqual(ripple_set_indices(project, 0, "until_next_keyframe", ["t1"]), [0, 1])
        project.sets[2].dot_positions = {
            dot_id: (position[0] + 20, position[1] + 4)
            for dot_id, position in project.sets[0].dot_positions.items()
        }
        self.assertEqual(ripple_set_indices(project, 0, "matching", [dot.id for dot in project.dots]), [0, 2])

    def test_beat_to_set_generator_uses_marker_boundaries_and_tempo(self) -> None:
        project = self.workflow_project()
        generated = generate_sets_from_markers(
            project,
            [Marker(1, "Opening"), Marker(9, "Impact"), Marker(17, "Release")],
        )
        self.assertEqual([(item.start_count, item.end_count) for item in generated], [(1, 8), (9, 16), (17, 24)])
        self.assertEqual([item.name for item in generated], ["Opening", "Impact", "Release"])
        self.assertTrue(all(item.tempo == 120 for item in generated))


class LargeShowAccelerationTests(unittest.TestCase):
    def project(self) -> DrillProject:
        dots = [
            Dot("t1", "Alice", 0, 0, section="Trumpets", instrument="Trumpet", rank="Rank 1", layer="Winds"),
            Dot("t2", "Bea", 2, 0, section="Trumpets", instrument="Trumpet", rank="Rank 1", layer="Winds"),
            Dot("m1", "Cam", 10, 0, section="Mellophones", instrument="Mellophone", rank="Rank 2", layer="Winds"),
            Dot("m2", "Dev", 8, 0, section="Mellophones", instrument="Mellophone", rank="Rank 2", layer="Winds"),
        ]
        positions = {dot.id: (dot.x, dot.y) for dot in dots}
        return DrillProject(
            ProjectMetadata("Large Show", 160, 8, "4/4"),
            dots=dots,
            sets=[DrillSet("Set 1", 1, 8, dot_positions=dict(positions)), DrillSet("Set 2", 9, 16, dot_positions=dict(positions))],
        )

    def test_roster_csv_generates_ids_layers_and_colors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "roster.csv"
            path.write_text(
                "Performer Name,Instrument,Section,Rank/File\n"
                "A Student,Trumpet,Trumpets,Rank 1\n"
                "B Student,Trumpet,Trumpets,Rank 1\n"
                "C Student,Snare,Battery,Rank 2\n",
                encoding="utf-8",
            )
            result = parse_roster_csv(path)
        self.assertEqual([dot.id for dot in result.dots], ["T1", "T2", "S1"])
        self.assertEqual([dot.layer for dot in result.dots], ["Winds", "Winds", "Percussion"])
        self.assertTrue(all(dot.color.startswith("#") for dot in result.dots))

    def test_roster_csv_infers_broad_section_without_copying_instrument(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "roster.csv"
            path.write_text("Performer Name,Instrument\nA Student,Trumpet\n", encoding="utf-8")
            result = parse_roster_csv(path)
        self.assertEqual(result.dots[0].instrument, "Trumpet")
        self.assertEqual(result.dots[0].section, "Brass")

    def test_hierarchical_groups_include_family_section_and_rank(self) -> None:
        project = self.project()
        groups = generate_hierarchical_groups(project)
        trumpets = next(group for group in groups if group["name"] == "Trumpets")
        self.assertEqual(group_dot_ids(project, trumpets["id"]), ["t1", "t2"])
        trumpets["locked"] = True
        self.assertEqual(locked_group_dot_ids(project), {"t1", "t2"})

    def test_linked_mirrored_group_propagates_matching_edit(self) -> None:
        project = self.project()
        master = create_group(project, "Trumpet Block", ["t1", "t2"])
        instance = create_group(project, "Mello Block", ["m1", "m2"])
        create_linked_formation(project, "Mirrored Blocks", master["id"], [instance["id"]], [instance["id"]])
        expanded = expand_linked_position_changes(project, 0, {"t1": (1, 0)})
        self.assertEqual(expanded["t1"], (1, 0))
        self.assertEqual(expanded["m1"], (9, 0))
        self.assertNotIn("m2", expanded)

    def test_swap_performers_preserves_drill_spots(self) -> None:
        project = self.project()
        before_sets = json.dumps([drill_set.to_json() for drill_set in project.sets], sort_keys=True)
        swap_performers(project.dots[0], project.dots[2])
        self.assertEqual(project.dots[0].name, "Cam")
        self.assertEqual(project.dots[2].name, "Alice")
        self.assertEqual(json.dumps([drill_set.to_json() for drill_set in project.sets], sort_keys=True), before_sets)

    def test_cleanup_removes_overlaps_without_destroying_member_count(self) -> None:
        positions = {"a": (0, 0), "b": (0, 0), "c": (2, 0), "d": (4, 0)}
        cleaned, report = cleanup_formation(
            positions,
            CleanupOptions(minimum_spacing=1.0, smooth_curvature=False, iterations=12),
        )
        self.assertEqual(set(cleaned), set(positions))
        self.assertGreater(report.overlaps_before, report.overlaps_after)
        self.assertGreater(report.moved, 0)

    def test_variations_and_cross_project_transfer(self) -> None:
        source = self.project()
        source.sets[1].dot_positions["t1"] = (12, 4)
        record = save_formation_variation(source, "Impact Option", 1, ["t1", "t2"])
        self.assertEqual(variation_positions(record)["t1"], (12.0, 4.0))
        destination = self.project()
        destination.sets[0].dot_positions["t1"] = (-20, -10)
        counts = transfer_project_content(source, destination, 1, 0, formation=True)
        self.assertEqual(counts["formation"], 4)
        self.assertEqual(destination.sets[0].dot_positions["t1"], (12, 4))


if __name__ == "__main__":
    unittest.main()
