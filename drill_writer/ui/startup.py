from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, Property, QPropertyAnimation, QRectF, Signal, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from drill_writer.core.models import DrillProject
from drill_writer.core.project_io import (
    create_project_folder,
    discover_projects,
    load_project,
    project_library_dir,
)


class SplashPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Drill Pirate")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 46px; font-weight: 750; letter-spacing: 1px;")
        version = QLabel("Alpha Version 1.0.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("font-size: 16px; color: #aeb7c8;")
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(version)


class CreateProjectDialog(QDialog):
    project_created = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.audio_path: Path | None = None
        self.setWindowTitle("Create Project")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        header = QLabel("New Drill Pirate Project")
        header.setStyleSheet("font-size: 20px; font-weight: 650;")
        layout.addWidget(header)

        form = QFormLayout()
        self.title_input = QLineEdit("Untitled Show")
        self.tempo_input = QDoubleSpinBox()
        self.tempo_input.setRange(40, 260)
        self.tempo_input.setValue(160)
        self.tempo_input.setSuffix(" BPM")
        self.counts_input = QSpinBox()
        self.counts_input.setRange(1, 128)
        self.counts_input.setValue(16)
        self.signature_input = QLineEdit("4/4")
        self.audio_label = QLabel("No audio selected")
        form.addRow("Show Title", self.title_input)
        form.addRow("Initial Tempo", self.tempo_input)
        form.addRow("Default Counts", self.counts_input)
        form.addRow("Time Signature", self.signature_input)
        form.addRow("Audio", self.audio_row())
        layout.addLayout(form)

        controls = QHBoxLayout()
        create_button = QPushButton("Create")
        create_button.clicked.connect(self.create_project)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        controls.addStretch()
        controls.addWidget(cancel_button)
        controls.addWidget(create_button)
        layout.addLayout(controls)

    def audio_row(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        choose_button = QPushButton("Choose Audio")
        choose_button.clicked.connect(self.choose_audio)
        layout.addWidget(choose_button)
        layout.addWidget(self.audio_label, 1)
        return container

    def choose_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Audio",
            str(Path.home()),
            "Audio Files (*.mp3 *.wav *.aiff *.flac)",
        )
        if path:
            self.audio_path = Path(path)
            self.audio_label.setText(self.audio_path.name)

    def create_project(self) -> None:
        project_dir = create_project_folder(
            root=project_library_dir(),
            title=self.title_input.text(),
            audio_source=self.audio_path,
            tempo=self.tempo_input.value(),
            counts_per_set=self.counts_input.value(),
            time_signature=self.signature_input.text() or "4/4",
        )
        self.project_created.emit(project_dir)
        self.accept()


class FieldPreview(QWidget):
    def __init__(self, project: DrillProject | None = None) -> None:
        super().__init__()
        self.project = project
        self.setMinimumSize(250, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.setPen(QPen(QColor("#dfeedd"), 1))
        painter.setBrush(QColor("#5aa052"))
        painter.drawRoundedRect(rect, 6, 6)

        yard_pen = QPen(QColor("#e8f6e6"), 1)
        painter.setPen(yard_pen)
        for index in range(11):
            x = rect.left() + rect.width() * index / 10
            painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
        hash_pen = QPen(QColor("#d9edd7"), 1)
        painter.setPen(hash_pen)
        for y_ratio in (0.32, 0.5, 0.68):
            y = rect.top() + rect.height() * y_ratio
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        if not self.project:
            self.draw_empty_field(painter, QRectF(rect))
            return

        positions = self.project.sets[0].dot_positions if self.project.sets else {}
        for dot in self.project.dots:
            x, y = positions.get(dot.id, (dot.x, dot.y))
            screen_x = rect.left() + (x + 60) / 120 * rect.width()
            screen_y = rect.top() + (26.666 - y) / 53.333 * rect.height()
            painter.setPen(QPen(QColor("#300000"), 1))
            painter.setBrush(QColor(dot.color or "#e53935"))
            painter.drawEllipse(QRectF(screen_x - 3, screen_y - 3, 6, 6))

    def draw_empty_field(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(QPen(QColor("#f7d154"), 4))
        center = rect.center()
        painter.drawLine(int(center.x() - 22), int(center.y()), int(center.x() + 22), int(center.y()))
        painter.drawLine(int(center.x()), int(center.y() - 22), int(center.x()), int(center.y() + 22))


class ProjectCard(QFrame):
    clicked = Signal(Path)

    def __init__(self, project_dir: Path, project: DrillProject) -> None:
        super().__init__()
        self.project_dir = project_dir
        self.setObjectName("ProjectCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(280)
        self.setMaximumWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.preview = FieldPreview(project)
        title = QLabel(project.metadata.show_title)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 14px; font-weight: 650;")
        layout.addWidget(self.preview)
        layout.addWidget(title)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.project_dir)
            event.accept()
            return
        super().mousePressEvent(event)


class CreateProjectCard(QFrame):
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._hover_progress = 0.0
        self.animation = QPropertyAnimation(self, b"hoverProgress", self)
        self.animation.setDuration(140)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(280, 190)
        self.setMaximumWidth(340)

    def get_hover_progress(self) -> float:
        return self._hover_progress

    def set_hover_progress(self, value: float) -> None:
        self._hover_progress = value
        self.update()

    hoverProgress = Property(float, get_hover_progress, set_hover_progress)

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self.animation.stop()
        self.animation.setStartValue(self._hover_progress)
        self.animation.setEndValue(1.0)
        self.animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self.animation.stop()
        self.animation.setStartValue(self._hover_progress)
        self.animation.setEndValue(0.0)
        self.animation.start()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(10, 10, -10, -10)
        color_value = 34 + int(self._hover_progress * 24)
        painter.setBrush(QColor(color_value, color_value + 4, color_value + 12))
        painter.setPen(QPen(QColor("#f7d154"), 2 + self._hover_progress))
        painter.drawRoundedRect(rect, 8, 8)

        field_rect = rect.adjusted(14, 14, -14, -44)
        painter.setPen(QPen(QColor("#dfeedd"), 1))
        painter.setBrush(QColor("#5aa052"))
        painter.drawRoundedRect(field_rect, 6, 6)

        center = field_rect.center()
        plus_size = 24 + int(self._hover_progress * 8)
        painter.setPen(QPen(QColor("#f7d154"), 5))
        painter.drawLine(int(center.x() - plus_size), int(center.y()), int(center.x() + plus_size), int(center.y()))
        painter.drawLine(int(center.x()), int(center.y() - plus_size), int(center.x()), int(center.y() + plus_size))
        painter.setPen(QColor("#f2f4f8"))
        painter.drawText(rect.adjusted(0, rect.height() - 36, 0, -8), Qt.AlignmentFlag.AlignCenter, "Create Project")

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class StartupPage(QWidget):
    project_ready = Signal(Path)

    def __init__(self) -> None:
        super().__init__()
        self.library_dir = project_library_dir()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        header = QHBoxLayout()
        title = QLabel("Drill Pirate")
        title.setStyleSheet("font-size: 30px; font-weight: 750;")
        version = QLabel("Alpha Version 1.0.0")
        version.setStyleSheet("font-size: 12px; color: #aeb7c8;")
        header.addWidget(title)
        header.addWidget(version)
        header.addStretch()
        layout.addLayout(header)

        path_label = QLabel(str(self.library_dir))
        path_label.setStyleSheet("color: #aeb7c8;")
        layout.addWidget(path_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(18)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.grid_container)
        layout.addWidget(self.scroll, 1)
        self.refresh_projects()

    def refresh_projects(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        create_card = CreateProjectCard()
        create_card.clicked.connect(self.open_create_dialog)
        self.grid.addWidget(create_card, 0, 0)

        col_count = 3
        for index, project_dir in enumerate(discover_projects(self.library_dir), start=1):
            try:
                project = load_project(project_dir)
            except Exception:
                continue
            card = ProjectCard(project_dir, project)
            card.clicked.connect(self.project_ready.emit)
            row = index // col_count
            col = index % col_count
            self.grid.addWidget(card, row, col)

    def open_create_dialog(self) -> None:
        dialog = CreateProjectDialog(self)
        dialog.project_created.connect(self.project_ready.emit)
        dialog.exec()
        self.refresh_projects()
