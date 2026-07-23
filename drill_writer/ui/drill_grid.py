from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from drill_writer.core.drill_grid import DrillGridSettings


GRID_PRESETS = (
    ("8-to-5 (standard)", 8.0),
    ("6-to-5", 6.0),
    ("12-to-5", 12.0),
    ("16-to-5", 16.0),
)


class DrillGridPreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = DrillGridSettings(enabled=True)
        self.setMinimumHeight(150)

    def set_settings(self, settings: DrillGridSettings) -> None:
        self.settings = settings
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#11151b"))
        field = QRectF(22, 18, max(40, self.width() - 44), max(40, self.height() - 48))
        painter.fillRect(field, QColor("#f6f9f6"))
        painter.setPen(QPen(QColor("#303944"), 2))
        painter.drawRect(field)
        painter.setPen(QPen(QColor(139, 111, 255, 120), 1))
        if self.settings.display_style == "lines":
            for index in range(1, max(1, round(self.settings.steps_per_five_x))):
                x = field.left() + field.width() * index / self.settings.steps_per_five_x
                painter.drawLine(int(x), int(field.top()), int(x), int(field.bottom()))
            for index in range(1, max(1, round(self.settings.steps_per_five_y))):
                y = field.top() + field.height() * index / self.settings.steps_per_five_y
                painter.drawLine(int(field.left()), int(y), int(field.right()), int(y))
        else:
            point_pen = QPen(QColor(124, 82, 220, 185), 2)
            point_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(point_pen)
            for index_x in range(max(1, round(self.settings.steps_per_five_x)) + 1):
                x = field.left() + field.width() * index_x / self.settings.steps_per_five_x
                for index_y in range(max(1, round(self.settings.steps_per_five_y)) + 1):
                    y = field.top() + field.height() * index_y / self.settings.steps_per_five_y
                    painter.drawPoint(int(x), int(y))
        painter.setPen(QColor("#d9dfea"))
        painter.setFont(QFont("Arial", 9, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(12, self.height() - 28, self.width() - 24, 20),
            Qt.AlignmentFlag.AlignCenter,
            f"One 5-yard interval • {self.settings.description}",
        )


class DrillGridDialog(QDialog):
    def __init__(self, settings: DrillGridSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Drill Grid & Snap")
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        heading = QLabel("Build formations on exact marching step intervals")
        heading.setStyleSheet("font-size: 16px; font-weight: 750;")
        layout.addWidget(heading)
        explanation = QLabel(
            "An 8-to-5 grid places eight equal steps inside every 5-yard interval. "
            "When enabled, marcher drags, on-form preview handles, and generated formation spots "
            "snap to the same visible grid."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("secondaryText")
        layout.addWidget(explanation)

        self.enabled = QCheckBox("Enable drill grid and snapping")
        self.enabled.setChecked(settings.enabled)
        self.enabled.setStyleSheet("font-weight: 700;")
        layout.addWidget(self.enabled)

        settings_group = QGroupBox("Grid Spacing")
        form = QFormLayout(settings_group)
        self.preset = QComboBox()
        for label, value in GRID_PRESETS:
            self.preset.addItem(label, value)
        self.preset.addItem("Custom", None)
        self.steps_x = self.step_spin(settings.steps_per_five_x)
        self.steps_y = self.step_spin(settings.steps_per_five_y)
        self.origin_x = self.origin_spin(settings.origin_x)
        self.origin_y = self.origin_spin(settings.origin_y)
        self.show_overlay = QCheckBox("Show snap overlay on the field")
        self.show_overlay.setChecked(settings.show_overlay)
        self.display_style = QComboBox()
        self.display_style.addItem("Snap points (recommended)", "points")
        self.display_style.addItem("Full grid lines", "lines")
        self.display_style.setCurrentIndex(max(0, self.display_style.findData(settings.display_style)))
        form.addRow("Preset", self.preset)
        form.addRow("Horizontal steps per 5 yd", self.steps_x)
        form.addRow("Vertical steps per 5 yd", self.steps_y)
        form.addRow("Horizontal origin (yd)", self.origin_x)
        form.addRow("Vertical origin (yd)", self.origin_y)
        form.addRow("Overlay style", self.display_style)
        form.addRow("Overlay", self.show_overlay)
        layout.addWidget(settings_group)

        self.details = QLabel()
        self.details.setObjectName("secondaryText")
        layout.addWidget(self.details)
        self.preview = DrillGridPreview()
        layout.addWidget(self.preview)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply Grid")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.preset.currentIndexChanged.connect(self.apply_preset)
        self.steps_x.valueChanged.connect(self.spacing_changed)
        self.steps_y.valueChanged.connect(self.spacing_changed)
        self.origin_x.valueChanged.connect(self.values_changed)
        self.origin_y.valueChanged.connect(self.values_changed)
        self.enabled.toggled.connect(self.values_changed)
        self.show_overlay.toggled.connect(self.values_changed)
        self.display_style.currentIndexChanged.connect(self.values_changed)
        self.select_matching_preset()
        self.values_changed()

    @staticmethod
    def step_spin(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(1.0, 32.0)
        spin.setDecimals(2)
        spin.setSingleStep(1.0)
        spin.setValue(value)
        spin.setSuffix(" steps")
        return spin

    @staticmethod
    def origin_spin(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-100.0, 100.0)
        spin.setDecimals(3)
        spin.setSingleStep(0.125)
        spin.setValue(value)
        spin.setSuffix(" yd")
        return spin

    def select_matching_preset(self) -> None:
        matching = next(
            (
                index
                for index, (_label, value) in enumerate(GRID_PRESETS)
                if abs(self.steps_x.value() - value) < 1e-6
                and abs(self.steps_y.value() - value) < 1e-6
            ),
            self.preset.count() - 1,
        )
        self.preset.setCurrentIndex(matching)

    def apply_preset(self, index: int) -> None:
        value = self.preset.itemData(index)
        if value is None:
            return
        self.steps_x.blockSignals(True)
        self.steps_y.blockSignals(True)
        self.steps_x.setValue(float(value))
        self.steps_y.setValue(float(value))
        self.steps_x.blockSignals(False)
        self.steps_y.blockSignals(False)
        self.values_changed()

    def spacing_changed(self, *_args) -> None:
        matching = next(
            (
                index
                for index, (_label, value) in enumerate(GRID_PRESETS)
                if abs(self.steps_x.value() - value) < 1e-6
                and abs(self.steps_y.value() - value) < 1e-6
            ),
            self.preset.count() - 1,
        )
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(matching)
        self.preset.blockSignals(False)
        self.values_changed()

    def values_changed(self, *_args) -> None:
        settings = self.selected_settings()
        inches_x = settings.spacing_x * 36.0
        inches_y = settings.spacing_y * 36.0
        self.details.setText(
            f"Exact spacing: X {settings.spacing_x:.3f} yd ({inches_x:.1f} in)  •  "
            f"Y {settings.spacing_y:.3f} yd ({inches_y:.1f} in)"
        )
        self.preview.set_settings(settings)

    def selected_settings(self) -> DrillGridSettings:
        return DrillGridSettings(
            enabled=self.enabled.isChecked(),
            steps_per_five_x=self.steps_x.value(),
            steps_per_five_y=self.steps_y.value(),
            origin_x=self.origin_x.value(),
            origin_y=self.origin_y.value(),
            show_overlay=self.show_overlay.isChecked(),
            display_style=str(self.display_style.currentData() or "points"),
        )
