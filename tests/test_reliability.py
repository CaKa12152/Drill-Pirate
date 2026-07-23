from __future__ import annotations

import errno
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication

from drill_writer.core.animation import interpolate_project
from drill_writer.core.project_io import (
    PROJECT_JSON_FILES,
    PROJECT_SCHEMA_HISTORY,
    PROJECT_SCHEMA_VERSION,
    SAVE_TRANSACTION_DIR_NAME,
    ProjectLoadError,
    ProjectSaveError,
    load_project,
    save_project,
)
from drill_writer.core.user_errors import actionable_error_message
from drill_writer.export.exporters import (
    Mp4ExportOptions,
    PrintTemplateOptions,
    export_coordinate_csv,
    export_coordinate_summary_pdf,
    export_dot_book_pdf,
    export_drill_sheet_pdf,
    export_mp4,
    export_project_zip,
    export_staff_packet_pdf,
    render_mp4_frame,
    video_encoder_args,
)
from drill_writer.ui.field_view import FieldView
from drill_writer.ui.main_window import MainWindow
from reliability_fixtures import export_project, playback_project, regression_projects
from soak_playback import exercise_playback_frames


class PlaybackSoakTests(unittest.TestCase):
    def test_playback_matrix_handles_200_to_500_performers(self) -> None:
        for performer_count in (200, 300, 400, 500):
            with self.subTest(performers=performer_count):
                result = exercise_playback_frames(performer_count, 480)
                self.assertEqual(result.frames, 480)
                self.assertGreater(result.elapsed_seconds, 0)
                self.assertGreaterEqual(result.maximum_frame_ms, 0)

    def test_every_set_boundary_is_position_continuous(self) -> None:
        for performer_count in (200, 300, 400, 500):
            project = playback_project(performer_count)
            for set_index in range(1, len(project.sets)):
                previous = project.sets[set_index - 1]
                current = project.sets[set_index]
                previous_end = interpolate_project(project, set_index - 1, previous.end_count)
                current_start = interpolate_project(project, set_index, current.start_count)
                for dot_id in previous_end:
                    self.assertAlmostEqual(previous_end[dot_id][0], current_start[dot_id][0], places=6)
                    self.assertAlmostEqual(previous_end[dot_id][1], current_start[dot_id][1], places=6)


class RegressionProjectFixtureTests(unittest.TestCase):
    def test_high_risk_projects_round_trip_without_losing_features(self) -> None:
        for fixture_name, project in regression_projects().items():
            with self.subTest(fixture=fixture_name), tempfile.TemporaryDirectory() as temp:
                project_dir = Path(temp) / fixture_name
                save_project(project_dir, project, backup=False)
                restored = load_project(project_dir)
                self.assertEqual(restored.metadata.show_title, project.metadata.show_title)
                self.assertEqual(len(restored.dots), len(project.dots))
                self.assertEqual(len(restored.sets), len(project.sets))
                self.assertEqual(restored.workflow.get("regression_fixture"), fixture_name)

                if fixture_name == "large_svg":
                    positions = list(restored.sets[-1].dot_positions.values())
                    self.assertEqual(len({(round(x, 5), round(y, 5)) for x, y in positions}), len(positions))
                elif fixture_name == "follow_leader":
                    self.assertTrue(restored.sets[1].motion_ribbons)
                    self.assertTrue(restored.sets[1].motion_ribbons[0].face_direction)
                    self.assertEqual(restored.sets[1].continuity[0].direction, "follow_the_leader")
                elif fixture_name == "props":
                    self.assertEqual(len(restored.props), 1)
                    self.assertEqual(restored.prop_attachments[0].rotation_behavior, "direction_of_travel")
                    self.assertEqual(restored.sets[1].prop_positions["window"]["rotation"], 90.0)
                elif fixture_name == "choreography":
                    self.assertEqual({event.event_type for event in restored.choreography}, {"equipment_change", "toss", "visual"})
                elif fixture_name == "tempo_map":
                    self.assertEqual([event.event_type for event in restored.timing_events], ["anchor", "tempo", "ritardando", "fermata", "tempo"])
                elif fixture_name == "custom_surface":
                    self.assertEqual(restored.surface.surface_type, "indoor")
                    self.assertFalse(restored.surface.show_yard_numbers)


class ProjectMigrationAndRecoveryTests(unittest.TestCase):
    def test_every_published_schema_migrates_to_current(self) -> None:
        for schema_version in PROJECT_SCHEMA_HISTORY:
            with self.subTest(schema=schema_version), tempfile.TemporaryDirectory() as temp:
                project_dir = Path(temp) / f"schema_{schema_version}"
                project = export_project()
                save_project(project_dir, project, backup=False)
                show_path = project_dir / "show.json"
                show = json.loads(show_path.read_text(encoding="utf-8"))
                show["schema_version"] = schema_version
                show["version"] = schema_version
                if schema_version < PROJECT_SCHEMA_VERSION:
                    for key in (
                        "guides",
                        "workflow",
                        "imported_score",
                        "music_phrases",
                        "storyboard",
                        "surface",
                        "choreography",
                        "prop_attachments",
                        "physical_limits",
                    ):
                        show.pop(key, None)
                    sets = json.loads((project_dir / "sets.json").read_text(encoding="utf-8"))
                    for drill_set in sets["sets"]:
                        for key in (
                            "dot_facings",
                            "prop_positions",
                            "path_anchors",
                            "path_controls",
                            "count_positions",
                            "count_facings",
                            "move_timings",
                            "movement_styles",
                            "continuity",
                            "motion_ribbons",
                            "transition",
                        ):
                            drill_set.pop(key, None)
                    (project_dir / "sets.json").write_text(json.dumps(sets), encoding="utf-8")
                if schema_version == 1:
                    show_path.unlink()
                    (project_dir / "props.json").unlink()
                else:
                    show_path.write_text(json.dumps(show), encoding="utf-8")

                restored = load_project(project_dir)
                migrated_show = json.loads((project_dir / "show.json").read_text(encoding="utf-8"))
                self.assertEqual(migrated_show["schema_version"], PROJECT_SCHEMA_VERSION)
                self.assertEqual(restored.metadata.show_title, project.metadata.show_title)
                self.assertEqual(len(restored.sets), 2)
                if schema_version < PROJECT_SCHEMA_VERSION:
                    self.assertTrue(list((project_dir / ".drill_pirate_backups").glob("*_migration.zip")))

    def test_low_disk_during_staging_preserves_every_project_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "low_disk"
            project = export_project()
            save_project(project_dir, project, backup=False)
            before = {name: (project_dir / name).read_bytes() for name in PROJECT_JSON_FILES}
            project.metadata.show_title = "Unsaved Change"
            with patch(
                "drill_writer.core.project_io._write_bytes_durable",
                side_effect=OSError(errno.ENOSPC, "No space left on device"),
            ):
                with self.assertRaisesRegex(ProjectSaveError, "restored the previous project files"):
                    save_project(project_dir, project, backup=False)
            after = {name: (project_dir / name).read_bytes() for name in PROJECT_JSON_FILES}
            self.assertEqual(before, after)
            self.assertFalse((project_dir / SAVE_TRANSACTION_DIR_NAME).exists())

    def test_interrupted_commit_is_rolled_back_on_next_open(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "interrupted"
            project = export_project()
            save_project(project_dir, project, backup=False)
            metadata_path = project_dir / "metadata.json"
            original = metadata_path.read_bytes()
            transaction = project_dir / SAVE_TRANSACTION_DIR_NAME
            (transaction / "old").mkdir(parents=True)
            (transaction / "new").mkdir()
            (transaction / "old" / "metadata.json").write_bytes(original)
            changed = json.loads(original.decode("utf-8"))
            changed["show_title"] = "Partially Committed Title"
            metadata_path.write_text(json.dumps(changed), encoding="utf-8")
            (transaction / "manifest.json").write_text(
                json.dumps({"files": ["metadata.json"], "existed": {"metadata.json": True}}),
                encoding="utf-8",
            )

            restored = load_project(project_dir)
            self.assertEqual(restored.metadata.show_title, project.metadata.show_title)
            self.assertEqual(metadata_path.read_bytes(), original)
            self.assertFalse(transaction.exists())

    def test_completed_transaction_marker_keeps_new_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "completed"
            project = export_project()
            save_project(project_dir, project, backup=False)
            metadata_path = project_dir / "metadata.json"
            original = metadata_path.read_bytes()
            updated = json.loads(original.decode("utf-8"))
            updated["show_title"] = "Committed New Title"
            metadata_path.write_text(json.dumps(updated), encoding="utf-8")
            transaction = project_dir / SAVE_TRANSACTION_DIR_NAME
            (transaction / "old").mkdir(parents=True)
            (transaction / "old" / "metadata.json").write_bytes(original)
            (transaction / "committed.json").write_text("{}", encoding="utf-8")

            restored = load_project(project_dir)
            self.assertEqual(restored.metadata.show_title, "Committed New Title")
            self.assertFalse(transaction.exists())

    def test_damaged_json_reports_recovery_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "damaged"
            save_project(project_dir, export_project(), backup=False)
            (project_dir / "sets.json").write_text('{"sets": [', encoding="utf-8")
            with self.assertRaisesRegex(ProjectLoadError, "corrupt or unreadable") as caught:
                load_project(project_dir)
            message = actionable_error_message("open the project", caught.exception, location=project_dir)
            self.assertIn("Restore Previous Save", message)
            self.assertIn("Export Bug Report Bundle", message)


class DeterministicExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def pdf_page_digest(self, path: Path) -> tuple[int, str]:
        document = QPdfDocument()
        document.load(str(path))
        self.assertGreater(document.pageCount(), 0)
        image = document.render(0, QSize(900, 700))
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        result = (document.pageCount(), hashlib.sha256(bytes(data)).hexdigest())
        document.close()
        return result

    def test_every_pdf_profile_is_visually_deterministic(self) -> None:
        project = export_project()
        profiles = {
            "drill_sheet": lambda path: export_drill_sheet_pdf(path, project),
            "dot_book": lambda path: export_dot_book_pdf(path, project),
            "dot_book_section": lambda path: export_dot_book_pdf(
                path, project, options=PrintTemplateOptions(section_filter="Guard", compact=True)
            ),
            "staff_packet": lambda path: export_staff_packet_pdf(
                path, project, options=PrintTemplateOptions(include_warnings=True)
            ),
            "section_packet": lambda path: export_staff_packet_pdf(
                path, project, options=PrintTemplateOptions(title="Guard Packet", section_filter="Guard")
            ),
            "coordinate_summary": lambda path: export_coordinate_summary_pdf(path, project),
            "coordinate_summary_section": lambda path: export_coordinate_summary_pdf(
                path, project, options=PrintTemplateOptions(section_filter="Guard", compact=True)
            ),
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, exporter in profiles.items():
                with self.subTest(profile=name):
                    first = root / f"{name}_1.pdf"
                    second = root / f"{name}_2.pdf"
                    exporter(first)
                    exporter(second)
                    self.assertEqual(self.pdf_page_digest(first), self.pdf_page_digest(second))

    def test_csv_and_project_zip_are_byte_deterministic(self) -> None:
        project = export_project()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project_dir = root / "project"
            save_project(project_dir, project, backup=False)
            csv_one = root / "one.csv"
            csv_two = root / "two.csv"
            export_coordinate_csv(csv_one, project)
            export_coordinate_csv(csv_two, project)
            self.assertEqual(csv_one.read_bytes(), csv_two.read_bytes())

            zip_one = root / "one.zip"
            zip_two = root / "two.zip"
            export_project_zip(project_dir, zip_one, project)
            export_project_zip(project_dir, zip_two, project)
            self.assertEqual(hashlib.sha256(zip_one.read_bytes()).digest(), hashlib.sha256(zip_two.read_bytes()).digest())
            with zipfile.ZipFile(zip_one) as archive:
                self.assertNotIn("one.zip", archive.namelist())
                self.assertEqual(archive.namelist(), sorted(archive.namelist(), key=str.lower))

    def test_mp4_render_and_encoding_profiles_are_deterministic(self) -> None:
        project = export_project()
        profiles = [
            ("high_1080", 18, "slow", "auto", False),
            ("very_high_1440", 14, "slow", "libx264", True),
            ("draft_4k", 24, "medium", "mpeg4", False),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project_dir = root / "project"
            save_project(project_dir, project, backup=False)
            field = FieldView()
            field.set_project(project, project_dir)

            def fake_encode(frames_dir, output_path, frame_result, **kwargs) -> None:
                options = kwargs["options"]
                digest = hashlib.sha256()
                for frame in sorted(Path(frames_dir).glob("frame_*.png")):
                    digest.update(frame.read_bytes())
                digest.update(
                    f"{frame_result.total_frames}|{options.crf}|{options.preset}|{options.video_encoder}|{options.title_splash}".encode()
                )
                Path(output_path).write_bytes(b"FAKE_MP4\0" + digest.digest())

            with patch("drill_writer.export.exporters.encode_mp4_frames", side_effect=fake_encode):
                for name, crf, preset, encoder, splash in profiles:
                    with self.subTest(profile=name):
                        options = Mp4ExportOptions(
                            fps=2,
                            size=QSize(320, 180),
                            crf=crf,
                            preset=preset,
                            video_encoder=encoder,
                            title_splash=splash,
                            title_splash_seconds=0.5,
                        )
                        first = root / f"{name}_1.mp4"
                        second = root / f"{name}_2.mp4"
                        export_mp4(field, project_dir, first, project, options=options)
                        export_mp4(field, project_dir, second, project, options=options)
                        self.assertEqual(first.read_bytes(), second.read_bytes())
                        self.assertTrue(first.read_bytes().startswith(b"FAKE_MP4\0"))

            for encoder in ("libx264", "mpeg4"):
                for crf in (14, 18, 24):
                    args = video_encoder_args(encoder, Mp4ExportOptions(crf=crf))
                    self.assertIn("-c:v", args)
                    self.assertIn(encoder, args)

            field.set_positions(project.sets[0].dot_positions)
            for size in (QSize(1920, 1080), QSize(2560, 1440), QSize(3840, 2160)):
                image = render_mp4_frame(field, size)
                self.assertEqual(image.size(), size)
                self.assertFalse(image.isNull())


class ActionableErrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_disk_full_and_ffmpeg_errors_have_next_steps(self) -> None:
        disk_message = actionable_error_message(
            "save the project",
            OSError(errno.ENOSPC, "No space left on device"),
            location="C:/Shows/Test",
        )
        self.assertIn("Free disk space", disk_message)
        self.assertIn("previous project files were preserved", disk_message)
        ffmpeg_message = actionable_error_message(
            "encode the MP4",
            RuntimeError("ffmpeg failed: Unknown encoder 'libx264'"),
        )
        self.assertIn("Set ffmpeg.exe", ffmpeg_message)
        self.assertIn("Auto encoder", ffmpeg_message)

    def test_save_and_autosave_failures_are_caught_by_the_ui(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = Path(temp) / "project"
            save_project(project_dir, export_project(), backup=False)
            window = MainWindow(project_dir)
            failure = ProjectSaveError(project_dir, "No space left on device")
            with patch("drill_writer.ui.main_window.save_project", side_effect=failure), patch(
                "drill_writer.ui.main_window.QMessageBox.warning"
            ) as warning:
                self.assertFalse(window.save())
                self.assertFalse(window.autosave())
                self.assertFalse(window.autosave())
                self.assertEqual(warning.call_count, 2)
                self.assertIn("What you can do", warning.call_args_list[0].args[2])
            window.close()
            window.deleteLater()


if __name__ == "__main__":
    unittest.main()
