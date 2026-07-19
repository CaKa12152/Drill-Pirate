from __future__ import annotations

import os
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from drill_writer.core.models import (
    Dot,
    DrillProject,
    DrillSet,
    ImportedScore,
    MusicPhrase,
    ProjectMetadata,
    ScoreMeasure,
    ScoreTempoChange,
)
from drill_writer.core.music_design import (
    detect_music_phrases,
    generate_sets_from_phrases,
    import_score,
    parse_midi_score,
    parse_musicxml_score,
    storyboard_from_phrases,
    suggest_show_design,
    synchronize_score_timing,
)
from drill_writer.core.project_io import (
    PROJECT_SCHEMA_VERSION,
    create_project_folder,
    load_project,
    save_project,
)
from drill_writer.ui.main_window import MainWindow
from drill_writer.ui.music_design import MusicDesignStudioDialog


MUSICXML_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <work><work-title>Production Test</work-title></work>
  <identification><creator type="composer">Drill Composer</creator></identification>
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1">
    <measure number="0" implicit="yes">
      <attributes><divisions>2</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <direction><direction-type><rehearsal>A</rehearsal><metronome><per-minute>120</per-minute></metronome></direction-type></direction>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration></note>
    </measure>
    <measure number="1">
      <note><rest/><duration>8</duration></note>
      <barline location="right"><bar-style>light-light</bar-style></barline>
    </measure>
    <measure number="2">
      <attributes><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
      <direction><direction-type><rehearsal>B</rehearsal></direction-type><sound tempo="144"/></direction>
      <note><rest/><duration>6</duration></note>
    </measure>
    <measure number="3"><note><rest/><duration>6</duration></note></measure>
  </part>
</score-partwise>
"""


def variable_length(value: int) -> bytes:
    values = [value & 0x7F]
    value >>= 7
    while value:
        values.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(values))


def meta(delta: int, event_type: int, payload: bytes) -> bytes:
    return variable_length(delta) + bytes((0xFF, event_type)) + variable_length(len(payload)) + payload


def midi_fixture() -> bytes:
    track = b"".join(
        [
            meta(0, 0x03, b"MIDI Production"),
            meta(0, 0x58, bytes((4, 2, 24, 8))),
            meta(0, 0x51, (500_000).to_bytes(3, "big")),
            meta(0, 0x06, b"Intro"),
            variable_length(0) + bytes((0x90, 60, 90)),
            variable_length(480) + bytes((0x80, 60, 0)),
            meta(1440, 0x2F, b""),
        ]
    )
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480) + b"MTrk" + struct.pack(">I", len(track)) + track


class ScoreImportTests(unittest.TestCase):
    def test_musicxml_imports_pickup_measures_meter_tempo_and_rehearsal_marks(self) -> None:
        score = parse_musicxml_score(MUSICXML_FIXTURE)
        self.assertEqual(score.title, "Production Test")
        self.assertEqual(score.composer, "Drill Composer")
        self.assertEqual(len(score.measures), 4)
        self.assertEqual(score.measures[0].duration_counts, 1.0)
        self.assertEqual(score.measures[1].start_count, 2.0)
        self.assertEqual(score.measures[2].time_signature, "3/4")
        self.assertEqual(score.measures[2].rehearsal_mark, "B")
        self.assertTrue(score.measures[2].phrase_boundary)
        self.assertEqual([(change.count, change.tempo) for change in score.tempo_changes], [(1.0, 120.0), (6.0, 144.0)])

    def test_compressed_mxl_import_uses_container_rootfile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "show.mxl"
            container = b"""<container><rootfiles><rootfile full-path="scores/main.musicxml"/></rootfiles></container>"""
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("META-INF/container.xml", container)
                archive.writestr("scores/main.musicxml", MUSICXML_FIXTURE)
            score = import_score(path)
            self.assertEqual(score.source_format, "musicxml")
            self.assertEqual(score.title, "Production Test")

    def test_score_timewise_musicxml_is_normalized(self) -> None:
        score = parse_musicxml_score(
            b"""<score-timewise version="4.0"><part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list><measure number="1"><part id="P1"><attributes><divisions>1</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes><direction><direction-type><rehearsal>A</rehearsal></direction-type><sound tempo="132"/></direction><note><rest/><duration>3</duration></note></part></measure></score-timewise>"""
        )
        self.assertEqual(len(score.measures), 1)
        self.assertEqual(score.measures[0].time_signature, "3/4")
        self.assertEqual(score.measures[0].rehearsal_mark, "A")
        self.assertEqual(score.tempo_changes[0].tempo, 132)

    def test_midi_imports_measure_tempo_meter_title_and_marker(self) -> None:
        score = parse_midi_score(midi_fixture())
        self.assertEqual(score.title, "MIDI Production")
        self.assertEqual(score.source_format, "midi")
        self.assertEqual(len(score.measures), 1)
        self.assertEqual(score.measures[0].time_signature, "4/4")
        self.assertEqual(score.measures[0].rehearsal_mark, "Intro")
        self.assertAlmostEqual(score.tempo_changes[0].tempo, 120.0)


class PhraseAndShowDesignTests(unittest.TestCase):
    def score(self) -> ImportedScore:
        return ImportedScore(
            title="Phrase Test",
            measures=[
                ScoreMeasure(str(index + 1), index * 4 + 1, 4, "4/4", 120 if index < 2 else 156, "A" if index == 0 else "B" if index == 2 else "", index in {0, 2})
                for index in range(4)
            ],
            tempo_changes=[ScoreTempoChange(1, 120), ScoreTempoChange(9, 156)],
        )

    def project(self) -> DrillProject:
        dots = [Dot("A", "A", -2, 0), Dot("B", "B", 2, 0)]
        project = DrillProject(
            ProjectMetadata("Show", 120, 4, "4/4"),
            dots=dots,
            sets=[
                DrillSet("Set 1", 1, 8, dot_positions={"A": (-2, 0), "B": (2, 0)}),
                DrillSet("Set 2", 9, 16, dot_positions={"A": (-2, 0), "B": (2, 0)}),
            ],
            imported_score=self.score(),
        )
        project.ensure_set_positions()
        return project

    def test_phrase_detection_prefers_rehearsal_boundaries(self) -> None:
        phrases = detect_music_phrases(self.score(), measures_per_phrase=4)
        self.assertEqual([phrase.name for phrase in phrases], ["A", "B"])
        self.assertEqual([(phrase.start_count, phrase.end_count) for phrase in phrases], [(1, 8), (9, 16)])
        self.assertGreater(phrases[1].intensity, phrases[0].intensity)

    def test_storyboard_builds_scene_pacing_from_phrases(self) -> None:
        phrases = detect_music_phrases(self.score(), measures_per_phrase=4)
        scenes = storyboard_from_phrases(phrases)
        self.assertEqual(len(scenes), 2)
        self.assertEqual(scenes[0].name, "A")
        self.assertEqual(scenes[1].movement, "Movement 2")
        self.assertNotEqual(scenes[0].color, scenes[1].color)

    def test_phrase_set_generation_aligns_measures_and_preserves_authored_forms(self) -> None:
        project = self.project()
        project.music_phrases = detect_music_phrases(project.imported_score, measures_per_phrase=4)
        generated = generate_sets_from_phrases(project, target_counts=4, motion_profile="preserve")
        self.assertEqual([(item.start_count, item.end_count) for item in generated], [(1, 4), (5, 8), (9, 12), (13, 16)])
        self.assertEqual([item.tempo for item in generated], [120, 120, 156, 156])
        self.assertTrue(all(item.dot_positions == {"A": (-2, 0), "B": (2, 0)} for item in generated))

    def test_automated_suggestions_respect_existing_motion(self) -> None:
        project = self.project()
        project.music_phrases = detect_music_phrases(project.imported_score, measures_per_phrase=4)
        suggestions = suggest_show_design(project, target_counts=8)
        self.assertEqual(len(suggestions), 2)
        self.assertTrue(all(suggestion.confidence >= 0.7 for suggestion in suggestions))
        project.sets[1].dot_positions = {"A": (8, 0), "B": (12, 0)}
        moving = suggest_show_design(project, target_counts=8)
        self.assertEqual(moving[1].motion, "Preserve authored transition")

    def test_score_timing_sync_is_idempotent(self) -> None:
        project = self.project()
        synchronize_score_timing(project)
        first_counts = (len(project.timing_events), len(project.markers))
        synchronize_score_timing(project)
        self.assertEqual((len(project.timing_events), len(project.markers)), first_counts)
        self.assertEqual(project.metadata.initial_tempo, 120)
        self.assertTrue(any(marker.label == "[Score] B" for marker in project.markers))


class MusicDesignPersistenceAndUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_current_schema_round_trips_score_phrases_and_storyboard(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Score Save", None, 120, 8, "4/4", 2)
            project = load_project(project_dir)
            project.imported_score = parse_musicxml_score(MUSICXML_FIXTURE)
            project.music_phrases = detect_music_phrases(project.imported_score, 2)
            project.storyboard = storyboard_from_phrases(project.music_phrases)
            save_project(project_dir, project, backup=False)
            restored = load_project(project_dir)
            self.assertEqual(PROJECT_SCHEMA_VERSION, 6)
            self.assertEqual(restored.imported_score, project.imported_score)
            self.assertEqual(restored.music_phrases, project.music_phrases)
            self.assertEqual(restored.storyboard, project.storyboard)

    def test_main_window_exposes_music_workspace_and_studio_tabs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project_dir = create_project_folder(Path(temp), "Music UI", None, 120, 8, "4/4", 4)
            window = MainWindow(project_dir)
            dialog = MusicDesignStudioDialog(window.project, project_dir, "storyboard", window)
            try:
                labels = [window.tools_tabs.tabText(index) for index in range(window.tools_tabs.count())]
                self.assertIn("Music", labels)
                window.apply_workspace("music")
                self.assertIs(window.tools_tabs.currentWidget(), window.music_tab)
                self.assertEqual(dialog.tabs.count(), 4)
                self.assertEqual(dialog.tabs.currentIndex(), 2)
                self.assertLessEqual(dialog.minimumSizeHint().width(), 1100)
            finally:
                dialog.close()
                window.close()


if __name__ == "__main__":
    unittest.main()
