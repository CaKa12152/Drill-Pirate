from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from drill_writer.ui.audio_devices import (
    DEFAULT_AUDIO_OUTPUT_DEVICE_ID,
    audio_device_id,
    audio_device_label,
    audio_output_devices,
    normalize_audio_output_device_id,
)


class PreferencesDialog(QDialog):
    def __init__(
        self,
        current_theme: str,
        current_audio_device_id: str = DEFAULT_AUDIO_OUTPUT_DEVICE_ID,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.current_audio_device_id = normalize_audio_output_device_id(current_audio_device_id)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        preferences_tab = QWidget()
        form = QFormLayout(preferences_tab)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark Mode", "dark")
        self.theme_combo.addItem("Light Mode", "light")
        self.theme_combo.setCurrentIndex(1 if current_theme == "light" else 0)
        note = QLabel("Changes apply immediately and are saved for the next launch.")
        note.setWordWrap(True)
        form.addRow("Appearance", self.theme_combo)
        form.addRow("", note)
        tabs.addTab(preferences_tab, "Preferences")

        devices_tab = QWidget()
        devices_layout = QVBoxLayout(devices_tab)
        devices_form = QFormLayout()
        self.audio_output_combo = QComboBox()
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_audio_devices)
        audio_row = QWidget()
        audio_layout = QHBoxLayout(audio_row)
        audio_layout.setContentsMargins(0, 0, 0, 0)
        audio_layout.addWidget(self.audio_output_combo, 1)
        audio_layout.addWidget(refresh_button)
        device_note = QLabel(
            "Use Windows Default to follow the system output device. "
            "Choose a specific connected device to force Drill Pirate to use it."
        )
        device_note.setWordWrap(True)
        devices_form.addRow("Audio Output", audio_row)
        devices_layout.addLayout(devices_form)
        devices_layout.addWidget(device_note)
        devices_layout.addStretch(1)
        tabs.addTab(devices_tab, "Devices")
        self.refresh_audio_devices()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        if apply_button:
            apply_button.clicked.connect(self.apply_clicked)
        layout.addWidget(buttons)

        self._applied_theme = current_theme

    def selected_theme(self) -> str:
        return str(self.theme_combo.currentData() or "dark")

    def selected_audio_output_device_id(self) -> str:
        return normalize_audio_output_device_id(self.audio_output_combo.currentData())

    def refresh_audio_devices(self) -> None:
        selected_id = self.selected_audio_output_device_id() if hasattr(self, "audio_output_combo") else self.current_audio_device_id
        self.audio_output_combo.blockSignals(True)
        self.audio_output_combo.clear()
        self.audio_output_combo.addItem("Windows Default", DEFAULT_AUDIO_OUTPUT_DEVICE_ID)
        for device in audio_output_devices():
            self.audio_output_combo.addItem(audio_device_label(device), audio_device_id(device))
        index = self.audio_output_combo.findData(selected_id)
        if index < 0:
            index = self.audio_output_combo.findData(self.current_audio_device_id)
        self.audio_output_combo.setCurrentIndex(max(0, index))
        self.audio_output_combo.blockSignals(False)

    def apply_clicked(self) -> None:
        self._applied_theme = self.selected_theme()
        parent = self.parent()
        handler = getattr(parent, "apply_theme", None)
        if callable(handler):
            handler(self._applied_theme)
        audio_handler = getattr(parent, "apply_audio_output_device", None)
        if callable(audio_handler):
            self.current_audio_device_id = self.selected_audio_output_device_id()
            audio_handler(self.current_audio_device_id)

    def accept(self) -> None:
        self.apply_clicked()
        super().accept()
