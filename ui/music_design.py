from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from drill_writer.core.models import DrillProject, MusicPhrase, StoryboardScene
from drill_writer.core.music_design import (
    ScoreImportError,
    detect_music_phrases,
    generate_sets_from_phrases,
    import_score,
    storyboard_from_phrases,
    suggest_show_design,
    synchronize_score_timing,
)


class ScoreImportWorker(QThread):
    score_ready = Signal(object, str)
    import_failed = Signal(str)

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = Path(path)

    def run(self) -> None:  # type: ignore[override]
        try:
            score = import_score(self.path)
        except ScoreImportError as exc:
            self.import_failed.emit(str(exc))
            return
        if not self.isInterruptionRequested():
            self.score_ready.emit(score, str(self.path))


class MusicDesignPanel(QWidget):
    studio_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)
        title = QLabel("Music Design")
        title.setStyleSheet("font-size: 14px; font-weight: 750;")
        description = QLabel("Import a score, map phrases to sets, plan visual pacing, and storyboard the production.")
        description.setWordWrap(True)
        self.summary = QLabel("No score imported")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("ToolHintLabel")
        root.addWidget(title)
        root.addWidget(description)
        root.addWidget(self.summary)

        score_group = QGroupBox("Score")
        score_layout = QVBoxLayout(score_group)
        score_button = QPushButton("Score…")
        score_button.setToolTip("Import MusicXML, compressed MXL, or MIDI and inspect measures, meter, tempo, and rehearsal marks.")
        score_button.clicked.connect(lambda: self.studio_requested.emit("score"))
        phrase_button = QPushButton("Phrases…")
        phrase_button.setToolTip("Detect musical phrases and generate count-accurate set boundaries with transition suggestions.")
        phrase_button.clicked.connect(lambda: self.studio_requested.emit("phrases"))
        score_layout.addWidget(score_button)
        score_layout.addWidget(phrase_button)
        root.addWidget(score_group)

        show_group = QGroupBox("Show Plan")
        show_layout = QVBoxLayout(show_group)
        storyboard_button = QPushButton("Scenes…")
        storyboard_button.setToolTip("Plan movements, scenes, production notes, and visual pacing by count range.")
        storyboard_button.clicked.connect(lambda: self.studio_requested.emit("storyboard"))
        suggestions_button = QPushButton("Suggestions…")
        suggestions_button.setToolTip("Analyze musical phrases against existing forms and recommend readable set and transition choices.")
        suggestions_button.clicked.connect(lambda: self.studio_requested.emit("suggestions"))
        show_layout.addWidget(storyboard_button)
        show_layout.addWidget(suggestions_button)
        root.addWidget(show_group)
        root.addStretch()
        self.setMinimumWidth(0)
        for label in self.findChildren(QLabel):
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        for button in self.findChildren(QPushButton):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_project(self, project: DrillProject) -> None:
        if project.imported_score is None:
            self.summary.setText("No score imported. Existing audio and drill are unchanged.")
            return
        score = project.imported_score
        self.summary.setText(
            f"{score.title}\n{len(score.measures)} measures · {score.total_counts:g} counts · "
            f"{len(project.music_phrases)} phrases · {len(project.storyboard)} scenes"
        )


class MusicDesignStudioDialog(QDialog):
    TAB_NAMES = {"score": 0, "phrases": 1, "storyboard": 2, "suggestions": 3}

    def __init__(self, project: DrillProject, project_dir: Path, initial_tab: str = "score", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Music & Show Design Studio")
        self.setMinimumSize(780, 520)
        available = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        self.resize(min(1180, max(780, available.width() - 80)), min(760, max(520, available.height() - 100)))
        self.project = deepcopy(project)
        self.project_dir = Path(project_dir)
        self._updating_phrases = False
        self._updating_storyboard = False
        self._score_worker: ScoreImportWorker | None = None
        self._import_progress: QProgressDialog | None = None
        self.suggestions = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("Music & Show Design")
        title.setStyleSheet("font-size: 18px; font-weight: 800;")
        self.status = QLabel("Changes remain in this studio until you click Save Changes.")
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status.setWordWrap(True)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status, 1)
        root.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.build_score_page()
        self.build_phrase_page()
        self.build_storyboard_page()
        self.build_suggestions_page()
        root.addWidget(self.tabs, 1)
        self.tabs.setCurrentIndex(self.TAB_NAMES.get(initial_tab, 0))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save Changes")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.refresh_all()

    def build_score_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 8, 6, 6)
        row = QHBoxLayout()
        import_button = QPushButton("Import MusicXML / MIDI…")
        import_button.clicked.connect(self.import_score_file)
        clear_button = QPushButton("Remove Imported Score")
        clear_button.clicked.connect(self.clear_score)
        row.addWidget(import_button)
        row.addWidget(clear_button)
        row.addStretch()
        layout.addLayout(row)
        self.score_summary = QLabel()
        self.score_summary.setWordWrap(True)
        layout.addWidget(self.score_summary)
        self.measure_table = QTableWidget(0, 7)
        self.measure_table.setHorizontalHeaderLabels(
            ["Measure", "Start Count", "Duration", "Meter", "Tempo", "Rehearsal", "Phrase Boundary"]
        )
        self.measure_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.measure_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.measure_table.verticalHeader().setVisible(False)
        header = self.measure_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.measure_table, 1)
        self.score_warnings = QLabel()
        self.score_warnings.setWordWrap(True)
        self.score_warnings.setObjectName("ToolHintLabel")
        layout.addWidget(self.score_warnings)
        self.tabs.addTab(page, "Score Import")

    def build_phrase_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 8, 6, 6)
        controls = QHBoxLayout()
        self.measures_per_phrase = QSpinBox()
        self.measures_per_phrase.setRange(1, 32)
        self.measures_per_phrase.setValue(4)
        self.measures_per_phrase.setSuffix(" measures")
        detect_button = QPushButton("Detect Phrases")
        detect_button.clicked.connect(self.detect_phrases)
        add_button = QPushButton("Add Phrase")
        add_button.clicked.connect(self.add_phrase)
        delete_button = QPushButton("Delete Selected")
        delete_button.clicked.connect(self.delete_phrases)
        controls.addWidget(QLabel("Default grouping"))
        controls.addWidget(self.measures_per_phrase)
        controls.addWidget(detect_button)
        controls.addWidget(add_button)
        controls.addWidget(delete_button)
        controls.addStretch()
        layout.addLayout(controls)
        self.phrase_table = QTableWidget(0, 7)
        self.phrase_table.setHorizontalHeaderLabels(
            ["Phrase", "Start", "End", "Measures", "Rehearsal", "Intensity", "Design Notes"]
        )
        self.phrase_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.phrase_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.phrase_table.verticalHeader().setVisible(False)
        self.phrase_table.itemChanged.connect(self.commit_phrase_table)
        phrase_header = self.phrase_table.horizontalHeader()
        phrase_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        phrase_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.phrase_table, 1)

        generator = QGroupBox("Phrase-Based Multi-Set Generation")
        generator_layout = QGridLayout(generator)
        self.target_counts = QSpinBox()
        self.target_counts.setRange(1, 64)
        self.target_counts.setValue(max(1, self.project.metadata.default_counts_per_set))
        self.target_counts.setSuffix(" counts")
        self.motion_profile = QComboBox()
        self.motion_profile.addItem("Preserve existing drill", "preserve")
        self.motion_profile.addItem("Gentle musical response", "gentle")
        self.motion_profile.addItem("Dynamic musical response", "dynamic")
        self.motion_profile.addItem("Maximum visual response", "maximum")
        generate_button = QPushButton("Generate Set Plan")
        generate_button.setToolTip("Replace the working set list with phrase-aligned sets. Cancel the studio to discard the plan.")
        generate_button.clicked.connect(self.generate_set_plan)
        generator_layout.addWidget(QLabel("Target length"), 0, 0)
        generator_layout.addWidget(self.target_counts, 0, 1)
        generator_layout.addWidget(QLabel("Transition planning"), 1, 0)
        generator_layout.addWidget(self.motion_profile, 1, 1)
        generator_layout.addWidget(generate_button, 2, 0, 1, 2)
        layout.addWidget(generator)
        self.tabs.addTab(page, "Phrase & Set Planner")

    def build_storyboard_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 8, 6, 6)
        row = QHBoxLayout()
        auto_button = QPushButton("Build From Phrases")
        auto_button.clicked.connect(self.auto_storyboard)
        add_button = QPushButton("Add Scene")
        add_button.clicked.connect(self.add_scene)
        delete_button = QPushButton("Delete Selected")
        delete_button.clicked.connect(self.delete_scenes)
        up_button = QPushButton("Move Up")
        up_button.clicked.connect(lambda: self.move_scene(-1))
        down_button = QPushButton("Move Down")
        down_button.clicked.connect(lambda: self.move_scene(1))
        row.addWidget(auto_button)
        row.addWidget(add_button)
        row.addWidget(delete_button)
        row.addStretch()
        row.addWidget(up_button)
        row.addWidget(down_button)
        layout.addLayout(row)
        self.storyboard_table = QTableWidget(0, 7)
        self.storyboard_table.setHorizontalHeaderLabels(
            ["Scene", "Movement", "Start", "End", "Visual Pacing", "Production Notes", "Color"]
        )
        self.storyboard_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.storyboard_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.storyboard_table.verticalHeader().setVisible(False)
        self.storyboard_table.itemChanged.connect(self.commit_storyboard_table)
        storyboard_header = self.storyboard_table.horizontalHeader()
        storyboard_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        storyboard_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.storyboard_table, 1)
        hint = QLabel("Storyboard scenes are production notes only. They never create performers or alter paths until you explicitly generate a set plan.")
        hint.setWordWrap(True)
        hint.setObjectName("ToolHintLabel")
        layout.addWidget(hint)
        self.tabs.addTab(page, "Storyboard")

    def build_suggestions_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 8, 6, 6)
        row = QHBoxLayout()
        analyze_button = QPushButton("Analyze Phrases + Existing Forms")
        analyze_button.clicked.connect(self.refresh_suggestions)
        apply_button = QPushButton("Apply Suggested Set Plan")
        apply_button.clicked.connect(self.generate_set_plan)
        row.addWidget(analyze_button)
        row.addWidget(apply_button)
        row.addStretch()
        layout.addLayout(row)
        self.suggestion_table = QTableWidget(0, 6)
        self.suggestion_table.setHorizontalHeaderLabels(
            ["Phrase / Set", "Counts", "Length", "Existing Travel", "Recommendation", "Confidence"]
        )
        self.suggestion_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.suggestion_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.suggestion_table.verticalHeader().setVisible(False)
        self.suggestion_table.currentCellChanged.connect(self.show_suggestion_detail)
        suggestion_header = self.suggestion_table.horizontalHeader()
        suggestion_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        suggestion_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.suggestion_table, 1)
        self.suggestion_detail = QLabel("Import a score and detect phrases to receive design suggestions.")
        self.suggestion_detail.setWordWrap(True)
        self.suggestion_detail.setMinimumHeight(54)
        self.suggestion_detail.setObjectName("ToolHintLabel")
        layout.addWidget(self.suggestion_detail)
        self.tabs.addTab(page, "Automated Suggestions")

    def import_score_file(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import MusicXML or MIDI",
            str(self.project_dir),
            "Music Scores (*.musicxml *.xml *.mxl *.mid *.midi);;MusicXML (*.musicxml *.xml *.mxl);;MIDI (*.mid *.midi)",
        )
        if not filename:
            return
        if self._score_worker and self._score_worker.isRunning():
            return
        self._import_progress = QProgressDialog("Reading score structure and timing…", "Cancel", 0, 0, self)
        self._import_progress.setWindowTitle("Import Score")
        self._import_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._import_progress.setMinimumDuration(0)
        self._score_worker = ScoreImportWorker(Path(filename), self)
        self._score_worker.score_ready.connect(self.finish_score_import)
        self._score_worker.import_failed.connect(self.fail_score_import)
        self._score_worker.finished.connect(self.finish_score_worker)
        self._import_progress.canceled.connect(self.cancel_score_import)
        self._score_worker.start()

    def cancel_score_import(self) -> None:
        if self._score_worker and self._score_worker.isRunning():
            self._score_worker.requestInterruption()
            self.status.setText("Canceling score import safely…")

    def finish_score_import(self, score, filename: str) -> None:
        self.project.imported_score = score
        self.project.music_phrases = detect_music_phrases(
            self.project.imported_score,
            self.measures_per_phrase.value(),
        )
        synchronize_score_timing(self.project)
        self.status.setText(f"Imported {Path(filename).name}. Review phrases and click Save Changes.")
        self.refresh_all()

    def fail_score_import(self, message: str) -> None:
        QMessageBox.warning(self, "Score Import Failed", message)

    def finish_score_worker(self) -> None:
        if self._import_progress:
            self._import_progress.close()
            self._import_progress.deleteLater()
            self._import_progress = None
        if self._score_worker:
            self._score_worker.deleteLater()
            self._score_worker = None

    def clear_score(self) -> None:
        if self.project.imported_score is None:
            return
        if QMessageBox.question(self, "Remove Imported Score", "Remove score, detected phrases, and score-created timing markers?") != QMessageBox.StandardButton.Yes:
            return
        self.project.imported_score = None
        self.project.music_phrases.clear()
        self.project.timing_events = [event for event in self.project.timing_events if not event.label.startswith("[Score]")]
        self.project.markers = [marker for marker in self.project.markers if not marker.label.startswith("[Score]")]
        self.refresh_all()

    def detect_phrases(self) -> None:
        if self.project.imported_score is None:
            QMessageBox.information(self, "Phrase Detection", "Import MusicXML or MIDI first.")
            return
        self.project.music_phrases = detect_music_phrases(self.project.imported_score, self.measures_per_phrase.value())
        self.status.setText(f"Detected {len(self.project.music_phrases)} phrase(s).")
        self.refresh_phrases()
        self.refresh_suggestions()

    def add_phrase(self) -> None:
        self.commit_phrase_table()
        start = max((phrase.end_count for phrase in self.project.music_phrases), default=0) + 1
        end = start + max(1, self.target_counts.value()) - 1
        index = len(self.project.music_phrases) + 1
        self.project.music_phrases.append(MusicPhrase(f"phrase-manual-{index}", f"Phrase {index}", start, end))
        self.refresh_phrases()
        self.phrase_table.selectRow(self.phrase_table.rowCount() - 1)

    def delete_phrases(self) -> None:
        rows = {index.row() for index in self.phrase_table.selectionModel().selectedRows()}
        if not rows:
            return
        self.project.music_phrases = [phrase for index, phrase in enumerate(self.project.music_phrases) if index not in rows]
        self.refresh_phrases()
        self.refresh_suggestions()

    def commit_phrase_table(self, *_args) -> None:
        if self._updating_phrases:
            return
        for row, phrase in enumerate(self.project.music_phrases):
            try:
                phrase.name = self.phrase_table.item(row, 0).text().strip() or phrase.name
                phrase.start_count = float(self.phrase_table.item(row, 1).text())
                phrase.end_count = max(phrase.start_count, float(self.phrase_table.item(row, 2).text()))
                phrase.rehearsal_mark = self.phrase_table.item(row, 4).text().strip()
                phrase.intensity = max(0.0, min(1.0, float(self.phrase_table.item(row, 5).text())))
                phrase.notes = self.phrase_table.item(row, 6).text().strip()
            except (AttributeError, ValueError):
                continue

    def generate_set_plan(self) -> None:
        self.commit_phrase_table()
        if self.project.imported_score is None or not self.project.music_phrases:
            QMessageBox.information(self, "Set Plan", "Import a score and detect at least one phrase first.")
            return
        generated = generate_sets_from_phrases(
            self.project,
            self.project.music_phrases,
            self.target_counts.value(),
            str(self.motion_profile.currentData()),
        )
        if not generated:
            QMessageBox.warning(self, "Set Plan", "No valid set boundaries could be generated.")
            return
        self.project.sets = generated
        self.project.ensure_set_positions()
        self.status.setText(f"Working plan contains {len(generated)} phrase-aligned sets. Save Changes to apply it.")
        self.refresh_suggestions()

    def auto_storyboard(self) -> None:
        self.commit_phrase_table()
        if not self.project.music_phrases:
            QMessageBox.information(self, "Storyboard", "Detect or add phrases first.")
            return
        self.project.storyboard = storyboard_from_phrases(self.project.music_phrases)
        self.refresh_storyboard()

    def add_scene(self) -> None:
        self.commit_storyboard_table()
        start = max((scene.end_count for scene in self.project.storyboard), default=0) + 1
        end = start + max(1, self.target_counts.value()) - 1
        index = len(self.project.storyboard) + 1
        self.project.storyboard.append(
            StoryboardScene(f"scene-manual-{index}", f"Scene {index}", start, end, f"Movement {index}")
        )
        self.refresh_storyboard()
        self.storyboard_table.selectRow(self.storyboard_table.rowCount() - 1)

    def delete_scenes(self) -> None:
        rows = {index.row() for index in self.storyboard_table.selectionModel().selectedRows()}
        if not rows:
            return
        self.project.storyboard = [scene for index, scene in enumerate(self.project.storyboard) if index not in rows]
        self.refresh_storyboard()

    def move_scene(self, direction: int) -> None:
        row = self.storyboard_table.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= len(self.project.storyboard):
            return
        self.commit_storyboard_table()
        self.project.storyboard[row], self.project.storyboard[target] = self.project.storyboard[target], self.project.storyboard[row]
        self.refresh_storyboard()
        self.storyboard_table.selectRow(target)

    def commit_storyboard_table(self, *_args) -> None:
        if self._updating_storyboard:
            return
        for row, scene in enumerate(self.project.storyboard):
            try:
                scene.name = self.storyboard_table.item(row, 0).text().strip() or scene.name
                scene.movement = self.storyboard_table.item(row, 1).text().strip()
                scene.start_count = float(self.storyboard_table.item(row, 2).text())
                scene.end_count = max(scene.start_count, float(self.storyboard_table.item(row, 3).text()))
                scene.visual_pacing = self.storyboard_table.item(row, 4).text().strip() or "Moderate"
                scene.production_notes = self.storyboard_table.item(row, 5).text().strip()
                color = self.storyboard_table.item(row, 6).text().strip()
                scene.color = QColor(color).name() if QColor(color).isValid() else scene.color
            except (AttributeError, ValueError):
                continue

    def refresh_all(self) -> None:
        self.refresh_score()
        self.refresh_phrases()
        self.refresh_storyboard()
        self.refresh_suggestions()

    def refresh_score(self) -> None:
        score = self.project.imported_score
        self.measure_table.setRowCount(0)
        if score is None:
            self.score_summary.setText("No score imported. MusicXML, compressed MXL, and standard MIDI format 0/1 are supported.")
            self.score_warnings.clear()
            return
        composer = f" · {score.composer}" if score.composer else ""
        self.score_summary.setText(
            f"<b>{score.title}</b>{composer}<br>{len(score.measures)} measures · {score.total_counts:g} counts · "
            f"{len(score.tempo_changes)} tempo changes · source: {score.source_format.upper()}"
        )
        self.measure_table.setRowCount(len(score.measures))
        for row, measure in enumerate(score.measures):
            values = (
                measure.number,
                f"{measure.start_count:g}",
                f"{measure.duration_counts:g}",
                measure.time_signature,
                f"{measure.tempo:g}" if measure.tempo > 0 else "—",
                measure.rehearsal_mark,
                "Yes" if measure.phrase_boundary else "",
            )
            for column, value in enumerate(values):
                self.measure_table.setItem(row, column, QTableWidgetItem(value))
        self.score_warnings.setText("\n".join(f"• {warning}" for warning in score.warnings))

    def refresh_phrases(self) -> None:
        self._updating_phrases = True
        try:
            self.phrase_table.setRowCount(len(self.project.music_phrases))
            for row, phrase in enumerate(self.project.music_phrases):
                values = (
                    phrase.name,
                    f"{phrase.start_count:g}",
                    f"{phrase.end_count:g}",
                    f"{phrase.start_measure or '?'}–{phrase.end_measure or '?'}",
                    phrase.rehearsal_mark,
                    f"{phrase.intensity:.2f}",
                    phrase.notes,
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 3:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.phrase_table.setItem(row, column, item)
        finally:
            self._updating_phrases = False

    def refresh_storyboard(self) -> None:
        self._updating_storyboard = True
        try:
            self.storyboard_table.setRowCount(len(self.project.storyboard))
            for row, scene in enumerate(self.project.storyboard):
                values = (
                    scene.name,
                    scene.movement,
                    f"{scene.start_count:g}",
                    f"{scene.end_count:g}",
                    scene.visual_pacing,
                    scene.production_notes,
                    scene.color,
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 6:
                        item.setBackground(QColor(scene.color))
                        item.setForeground(QColor("#ffffff") if QColor(scene.color).lightness() < 128 else QColor("#111111"))
                    self.storyboard_table.setItem(row, column, item)
        finally:
            self._updating_storyboard = False

    def refresh_suggestions(self) -> None:
        self.commit_phrase_table()
        self.suggestions = suggest_show_design(
            self.project,
            self.project.music_phrases,
            self.target_counts.value(),
        )
        self.suggestion_table.setRowCount(len(self.suggestions))
        for row, suggestion in enumerate(self.suggestions):
            values = (
                suggestion.phrase_name,
                f"{suggestion.start_count}–{suggestion.end_count}",
                str(suggestion.set_count),
                f"{suggestion.existing_motion_yards:.2f} yd",
                suggestion.motion,
                f"{suggestion.confidence * 100:.0f}%",
            )
            for column, value in enumerate(values):
                self.suggestion_table.setItem(row, column, QTableWidgetItem(value))
        if self.suggestions:
            self.suggestion_table.setCurrentCell(0, 0)
        else:
            self.suggestion_detail.setText("Import a score and detect phrases to receive design suggestions.")

    def show_suggestion_detail(self, row: int, _column: int, _previous_row: int, _previous_column: int) -> None:
        if 0 <= row < len(self.suggestions):
            suggestion = self.suggestions[row]
            self.suggestion_detail.setText(
                f"<b>{suggestion.motion}</b> · {suggestion.rationale} "
                f"This recommendation preserves authored transitions whenever existing travel is already present."
            )

    def accept(self) -> None:  # type: ignore[override]
        if self._score_worker and self._score_worker.isRunning():
            QMessageBox.information(self, "Score Import", "Wait for the score import to finish or cancel it first.")
            return
        self.commit_phrase_table()
        self.commit_storyboard_table()
        if self.project.imported_score is not None:
            synchronize_score_timing(self.project)
        super().accept()

    def reject(self) -> None:  # type: ignore[override]
        if self._score_worker and self._score_worker.isRunning():
            self.cancel_score_import()
            return
        super().reject()
