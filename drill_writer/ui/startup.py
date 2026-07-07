from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, Property, QPropertyAnimation, QRectF, Signal, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from drill_writer.core.coordinates import BACK_HASH_YARDS, FIELD_HALF_HEIGHT_YARDS, FRONT_HASH_YARDS
from drill_writer.core.models import DrillProject
from drill_writer.core.plugin_manager import PluginManager, PluginManifest, plugin_library_dir
from drill_writer.core.project_io import (
    ProjectLoadError,
    create_project_folder,
    discover_projects,
    load_project,
    parse_instrumentation_roster,
    project_library_dir,
    roster_count,
)
from drill_writer.resources import app_icon_path
from drill_writer.ui.appearance import draw_dot_symbol, generated_prop_pixmap, normalize_dot_symbol, preferred_dot_symbol


class SplashPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("SplashPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            """
            #SplashPage {
                background: qradialgradient(
                    cx: 0.5, cy: 0.42, radius: 0.9,
                    fx: 0.5, fy: 0.34,
                    stop: 0 #222222,
                    stop: 0.58 #111214,
                    stop: 1 #050506
                );
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(app_icon_path()))
        if not pixmap.isNull():
            icon.setPixmap(
                pixmap.scaled(
                    190,
                    190,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        title = QLabel("Drill Pirate")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 48px; font-weight: 850; letter-spacing: 1px; color: #f7c94a;")
        version = QLabel("Alpha Version 2.4.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("font-size: 16px; color: #f4f4f1;")
        tagline = QLabel("Professional drill design for the field")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet("font-size: 12px; color: #9da4ad;")
        layout.addWidget(icon)
        layout.addSpacing(6)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(tagline)


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
        self.marcher_count_input = QSpinBox()
        self.marcher_count_input.setRange(1, 500)
        self.marcher_count_input.setValue(30)
        self.roster_input = QPlainTextEdit()
        self.roster_input.setPlaceholderText(
            "Optional roster counts, one per line:\n"
            "Flute=5\nTrumpet=5\nTrombone=5\nTuba=5\nMellophone=5"
        )
        self.roster_input.setFixedHeight(92)
        self.roster_input.textChanged.connect(self.update_marcher_count_from_roster)
        self.front_ensemble_input = QSpinBox()
        self.front_ensemble_input.setRange(0, 50)
        self.front_ensemble_input.setValue(0)
        self.drum_major_stands_input = QSpinBox()
        self.drum_major_stands_input.setRange(0, 10)
        self.drum_major_stands_input.setValue(0)
        self.signature_input = QLineEdit("4/4")
        self.audio_label = QLabel("No audio selected")
        form.addRow("Show Title", self.title_input)
        form.addRow("Initial Tempo", self.tempo_input)
        form.addRow("Default Counts", self.counts_input)
        form.addRow("Marchers", self.marcher_count_input)
        form.addRow("Instrumentation", self.roster_input)
        form.addRow("Front Ensemble Props", self.front_ensemble_input)
        form.addRow("Drum Major Stands", self.drum_major_stands_input)
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

    def update_marcher_count_from_roster(self) -> None:
        total = roster_count(parse_instrumentation_roster(self.roster_input.toPlainText()))
        if total <= 0:
            self.marcher_count_input.setEnabled(True)
            return
        self.marcher_count_input.setEnabled(False)
        self.marcher_count_input.setValue(total)

    def create_project(self) -> None:
        roster = parse_instrumentation_roster(self.roster_input.toPlainText())
        project_dir = create_project_folder(
            root=project_library_dir(),
            title=self.title_input.text(),
            audio_source=self.audio_path,
            tempo=self.tempo_input.value(),
            counts_per_set=self.counts_input.value(),
            time_signature=self.signature_input.text() or "4/4",
            marcher_count=self.marcher_count_input.value(),
            instrumentation=roster,
            front_ensemble_count=self.front_ensemble_input.value(),
            drum_major_stands=self.drum_major_stands_input.value(),
        )
        self.project_created.emit(project_dir)
        self.accept()


class FieldPreview(QWidget):
    def __init__(self, project: DrillProject | None = None, project_dir: Path | None = None) -> None:
        super().__init__()
        self.project = project
        self.project_dir = project_dir
        self.dot_symbol = preferred_dot_symbol()
        self.setMinimumSize(260, 132)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_dot_symbol(self, symbol: str) -> None:
        self.dot_symbol = normalize_dot_symbol(symbol)
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor("#2f3744"), 1))
        painter.setBrush(QColor("#101419"))
        painter.drawRoundedRect(outer, 10, 10)

        rect = self.field_rect(outer)
        painter.setPen(QPen(QColor("#88939a"), 0.55))
        painter.setBrush(QColor("#f9fbf7"))
        painter.drawRoundedRect(rect, 5, 5)

        micro_pen = QPen(QColor("#e3e9e8"), 0.16)
        painter.setPen(micro_pen)
        for index in range(49):
            x = rect.left() + rect.width() * index / 48
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
        for index in range(9):
            y = rect.top() + rect.height() * index / 8
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))

        yard_pen = QPen(QColor("#5d686f"), 0.42)
        painter.setPen(yard_pen)
        for index in range(13):
            x = rect.left() + rect.width() * index / 12
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))

        hash_pen = QPen(QColor("#1f2529"), 0.42)
        painter.setPen(hash_pen)
        for field_y in (BACK_HASH_YARDS, FRONT_HASH_YARDS):
            y = rect.top() + (FIELD_HALF_HEIGHT_YARDS - field_y) / (FIELD_HALF_HEIGHT_YARDS * 2) * rect.height()
            for index in range(25):
                x = rect.left() + rect.width() * index / 24
                painter.drawLine(int(x), int(y - 0.8), int(x), int(y + 0.8))

        painter.setPen(QPen(QColor("#6c767e"), 0.35))
        painter.setFont(QFont("Segoe UI", 4, QFont.Weight.DemiBold))
        for index, text in enumerate(("G", "10", "20", "30", "40", "50", "40", "30", "20", "10", "G")):
            x = rect.left() + rect.width() * index / 10
            painter.drawText(QRectF(x - 5, rect.bottom() - 10, 10, 6), Qt.AlignmentFlag.AlignCenter, text)
            painter.save()
            painter.translate(x, rect.top() + 7)
            painter.rotate(180)
            painter.drawText(QRectF(-5, -3, 10, 6), Qt.AlignmentFlag.AlignCenter, text)
            painter.restore()

        if not self.project:
            self.draw_empty_field(painter, rect)
            return

        first_set = self.project.sets[0] if self.project.sets else None
        self.draw_props(painter, rect, first_set.prop_positions if first_set else {})
        positions = first_set.dot_positions if first_set else {}
        dot_count = max(1, len(self.project.dots))
        radius = max(0.75, min(1.55, 7 / (dot_count**0.5)))
        for dot in self.project.dots:
            x, y = positions.get(dot.id, (dot.x, dot.y))
            screen_x = rect.left() + (x + 60) / 120 * rect.width()
            screen_y = rect.top() + (26.666 - y) / 53.333 * rect.height()
            if not rect.adjusted(-4, -4, 4, 4).contains(screen_x, screen_y):
                continue
            draw_dot_symbol(
                painter,
                QPointF(screen_x, screen_y),
                radius,
                QColor(dot.color or "#e53935"),
                self.dot_symbol,
                outline_width=0.42,
            )

    def draw_props(self, painter: QPainter, rect: QRectF, states: dict[str, dict[str, float]]) -> None:
        if not self.project:
            return
        for prop in self.project.props:
            state = states.get(prop.id, {})
            prop_x = float(state.get("x", prop.x))
            prop_y = float(state.get("y", prop.y))
            prop_width = max(0.1, float(state.get("width", prop.width)))
            prop_height = max(0.1, float(state.get("height", prop.height)))
            prop_rotation = float(state.get("rotation", prop.rotation))
            screen_x = rect.left() + (prop_x + 60) / 120 * rect.width()
            screen_y = rect.top() + (26.666 - prop_y) / 53.333 * rect.height()
            screen_width = prop_width / 120 * rect.width()
            screen_height = prop_height / 53.333 * rect.height()
            prop_rect = QRectF(-screen_width / 2, -screen_height / 2, screen_width, screen_height)

            painter.save()
            painter.translate(screen_x, screen_y)
            painter.rotate(prop_rotation)
            pixmap = self.load_prop_pixmap(prop)
            if pixmap and not pixmap.isNull():
                painter.setOpacity(0.9)
                painter.drawPixmap(prop_rect, pixmap, pixmap.rect())
                painter.setOpacity(1.0)
                painter.setPen(QPen(QColor("#7b2530"), 0.7))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(prop_rect, 2, 2)
            else:
                painter.setPen(QPen(QColor("#7b2530"), 0.7))
                painter.setBrush(QColor(255, 58, 58, 190))
                painter.drawRoundedRect(prop_rect, 2, 2)
            painter.restore()

    def load_prop_pixmap(self, prop) -> QPixmap:
        image_file = getattr(prop, "image_file", "")
        if not image_file:
            return generated_prop_pixmap(getattr(prop, "name", "Prop"), getattr(prop, "layer", "Props"))
        path = Path(image_file)
        if not path.is_absolute() and self.project_dir is not None:
            path = self.project_dir / image_file
        if path.exists():
            return QPixmap(str(path))
        return generated_prop_pixmap(getattr(prop, "name", "Prop"), getattr(prop, "layer", "Props"))

    def field_rect(self, outer: QRectF) -> QRectF:
        target_ratio = 120 / 53.333
        width = outer.width() - 18
        height = width / target_ratio
        if height > outer.height() - 14:
            height = outer.height() - 14
            width = height * target_ratio
        return QRectF(
            outer.center().x() - width / 2,
            outer.center().y() - height / 2,
            width,
            height,
        )

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
        self.setMinimumSize(300, 220)
        self.setMaximumWidth(330)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)
        self.preview = FieldPreview(project, project_dir)
        title = QLabel(project.metadata.show_title)
        title.setStyleSheet("font-size: 14px; font-weight: 700;")
        title.setWordWrap(True)
        detail = QLabel(f"{len(project.dots)} marchers · {len(project.sets)} set(s)")
        detail.setStyleSheet("color: #9da7b8; font-size: 11px;")
        layout.addWidget(self.preview)
        layout.addWidget(title)
        layout.addWidget(detail)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.project_dir)
            event.accept()
            return
        super().mousePressEvent(event)


class RecoveryProjectCard(QFrame):
    clicked = Signal(Path)

    def __init__(self, project_dir: Path, error: Exception) -> None:
        super().__init__()
        self.project_dir = project_dir
        self.setObjectName("ProjectCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(300, 220)
        self.setMaximumWidth(330)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)
        preview = FieldPreview(None, project_dir)
        title = QLabel(project_dir.name.replace("_", " "))
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #f7d154;")
        title.setWordWrap(True)
        detail = QLabel("Project needs recovery")
        detail.setStyleSheet("color: #ff9f8a; font-size: 12px; font-weight: 650;")
        message = QLabel(str(error))
        message.setStyleSheet("color: #9da7b8; font-size: 10px;")
        message.setWordWrap(True)
        message.setMaximumHeight(42)
        layout.addWidget(preview)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addWidget(message)

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
        self.setMinimumSize(300, 220)
        self.setMaximumWidth(330)

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
        rect = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        color_value = 28 + int(self._hover_progress * 18)
        painter.setBrush(QColor(color_value, color_value + 5, color_value + 14))
        painter.setPen(QPen(QColor("#f7d154"), 1.6 + self._hover_progress))
        painter.drawRoundedRect(rect, 12, 12)

        field_rect = rect.adjusted(16, 18, -16, -58)
        painter.setPen(QPen(QColor("#88939a"), 1))
        painter.setBrush(QColor("#f9fbf7"))
        painter.drawRoundedRect(field_rect, 8, 8)

        painter.setPen(QPen(QColor("#d3dcda"), 0.7))
        for index in range(11):
            x = field_rect.left() + field_rect.width() * index / 10
            painter.drawLine(int(x), int(field_rect.top()), int(x), int(field_rect.bottom()))
        for index in range(5):
            y = field_rect.top() + field_rect.height() * index / 4
            painter.drawLine(int(field_rect.left()), int(y), int(field_rect.right()), int(y))

        center = field_rect.center()
        plus_size = 20 + int(self._hover_progress * 7)
        painter.setPen(QPen(QColor("#f7d154"), 4.5))
        painter.drawLine(int(center.x() - plus_size), int(center.y()), int(center.x() + plus_size), int(center.y()))
        painter.drawLine(int(center.x()), int(center.y() - plus_size), int(center.x()), int(center.y() + plus_size))
        painter.setPen(QColor("#f2f4f8"))
        painter.drawText(rect.adjusted(0, rect.height() - 46, 0, -22), Qt.AlignmentFlag.AlignCenter, "Create Project")
        painter.setPen(QColor("#9da7b8"))
        painter.drawText(rect.adjusted(0, rect.height() - 25, 0, -6), Qt.AlignmentFlag.AlignCenter, "Start a new show")

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class StartupPage(QWidget):
    project_ready = Signal(Path)
    settings_requested = Signal()

    def __init__(self, plugin_manager: PluginManager | None = None) -> None:
        super().__init__()
        self.plugin_manager = plugin_manager
        self.setObjectName("HomePage")
        self.library_dir = project_library_dir()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("HomeHero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(18, 16, 22, 16)
        hero_icon = QLabel()
        hero_icon.setFixedSize(76, 76)
        hero_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(app_icon_path()))
        if not pixmap.isNull():
            hero_icon.setPixmap(
                pixmap.scaled(
                    74,
                    74,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        hero_layout.addWidget(hero_icon)
        title_stack = QVBoxLayout()
        title = QLabel("Drill Pirate")
        title.setObjectName("HomeTitle")
        title.setStyleSheet("font-size: 34px; font-weight: 850; color: #f7c94a;")
        version = QLabel("Alpha Version 2.4.0")
        version.setStyleSheet("font-size: 12px; color: #f1f1ee;")
        path_label = QLabel(f"Project library · {self.library_dir}")
        path_label.setStyleSheet("color: #8d98aa;")
        self.plugin_banner = QLabel("")
        self.plugin_banner.setStyleSheet("color: #f7d154; font-weight: 650;")
        title_stack.addWidget(title)
        title_stack.addWidget(version)
        title_stack.addWidget(path_label)
        title_stack.addWidget(self.plugin_banner)
        hero_layout.addLayout(title_stack, 1)
        settings_button = QPushButton("Settings")
        settings_button.clicked.connect(self.settings_requested.emit)
        new_project_button = QPushButton("New Project")
        new_project_button.clicked.connect(self.open_create_dialog)
        hero_layout.addWidget(settings_button)
        hero_layout.addWidget(new_project_button)
        layout.addWidget(hero)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("HomeTabs")
        self.tabs.addTab(self.build_projects_tab(), "Projects")
        self.tabs.addTab(self.build_plugins_tab(), "Plugins")
        layout.addWidget(self.tabs, 1)
        self.refresh_projects()
        self.refresh_plugins()

    def build_projects_tab(self) -> QWidget:
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 16, 0, 0)
        heading = QLabel("Recent Projects")
        heading.setStyleSheet("font-size: 18px; font-weight: 750;")
        tab_layout.addWidget(heading)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(18)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.grid_container)
        tab_layout.addWidget(self.scroll, 1)
        return tab

    def build_plugins_tab(self) -> QWidget:
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 16, 0, 0)
        top_row = QHBoxLayout()
        heading = QLabel("Plugins")
        heading.setStyleSheet("font-size: 18px; font-weight: 750;")
        plugin_path = QLabel(str(plugin_library_dir()))
        plugin_path.setStyleSheet("color: #8d98aa;")
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_plugins)
        top_row.addWidget(heading)
        top_row.addWidget(plugin_path, 1)
        top_row.addWidget(refresh_button)
        tab_layout.addLayout(top_row)
        note = QLabel("Plugins are folders with a plugin.json manifest and Python entry file. Only enable plugins you trust.")
        note.setStyleSheet("color: #aeb7c8;")
        note.setWordWrap(True)
        tab_layout.addWidget(note)

        self.plugin_scroll = QScrollArea()
        self.plugin_scroll.setWidgetResizable(True)
        self.plugin_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.plugin_grid_container = QWidget()
        self.plugin_grid = QGridLayout(self.plugin_grid_container)
        self.plugin_grid.setHorizontalSpacing(10)
        self.plugin_grid.setVerticalSpacing(10)
        self.plugin_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.plugin_scroll.setWidget(self.plugin_grid_container)
        tab_layout.addWidget(self.plugin_scroll, 1)
        return tab

    def set_plugin_banner(self, text: str) -> None:
        self.plugin_banner.setText(text)

    def apply_dot_symbol(self, symbol: str) -> None:
        for preview in self.findChildren(FieldPreview):
            preview.set_dot_symbol(symbol)

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
                card = ProjectCard(project_dir, project)
            except ProjectLoadError as exc:
                card = RecoveryProjectCard(project_dir, exc)
            except Exception as exc:
                card = RecoveryProjectCard(project_dir, exc)
            card.clicked.connect(self.project_ready.emit)
            row = index // col_count
            col = index % col_count
            self.grid.addWidget(card, row, col)

    def refresh_plugins(self) -> None:
        if not hasattr(self, "plugin_grid"):
            return
        while self.plugin_grid.count():
            item = self.plugin_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not self.plugin_manager:
            return

        for index, manifest in enumerate(self.plugin_manager.discover()):
            card = PluginCard(manifest, self.plugin_manager.is_active(manifest.id))
            card.toggled.connect(self.toggle_plugin)
            self.plugin_grid.addWidget(card, index // 3, index % 3)

    def toggle_plugin(self, plugin_id: str, active: bool) -> None:
        if not self.plugin_manager:
            return
        self.plugin_manager.set_active(plugin_id, active)
        self.refresh_plugins()

    def open_create_dialog(self) -> None:
        dialog = CreateProjectDialog(self)
        dialog.project_created.connect(self.project_ready.emit)
        dialog.exec()
        self.refresh_projects()


class PluginCard(QFrame):
    toggled = Signal(str, bool)

    def __init__(self, manifest: PluginManifest, active: bool) -> None:
        super().__init__()
        self.manifest = manifest
        self.active = active
        self.setObjectName("PluginCard")
        self.setMinimumSize(300, 118)
        self.setMaximumWidth(360)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(5)
        top = QHBoxLayout()
        title = QLabel(manifest.name)
        title.setStyleSheet("font-size: 15px; font-weight: 750;")
        status = QLabel("Active" if active else "Inactive")
        status.setObjectName("PluginStatusActive" if active else "PluginStatusInactive")
        top.addWidget(title, 1)
        top.addWidget(status)
        layout.addLayout(top)

        meta = QLabel(f"Version {manifest.version} · {manifest.author}")
        meta.setStyleSheet("color: #9da7b8;")
        layout.addWidget(meta)
        description = QLabel(manifest.description or "No description provided.")
        description.setWordWrap(True)
        description.setMaximumHeight(34)
        description.setStyleSheet("color: #c8cfdd;")
        layout.addWidget(description)
        path = QLabel(str(manifest.path))
        path.setStyleSheet("color: #788396; font-size: 10px;")
        path.setWordWrap(True)
        path.setMaximumHeight(28)
        layout.addWidget(path)

        self.toggle_button = QPushButton("Deactivate" if active else "Activate")
        self.toggle_button.setMaximumHeight(26)
        self.toggle_button.clicked.connect(self.emit_toggle)
        layout.addWidget(self.toggle_button, alignment=Qt.AlignmentFlag.AlignRight)

    def emit_toggle(self) -> None:
        self.toggled.emit(self.manifest.id, not self.active)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.emit_toggle()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
