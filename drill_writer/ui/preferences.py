from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
        current_update_channel: str = "stable",
        current_tooltips_enabled: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.current_audio_device_id = normalize_audio_output_device_id(current_audio_device_id)

        layout = QVBoxLayout(self)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search settings...")
        self.search_status = QLabel("")
        self.search_status.setWordWrap(True)
        tabs = QTabWidget()
        self.tabs = tabs
        layout.addWidget(self.search_input)
        layout.addWidget(self.search_status)
        layout.addWidget(tabs)

        preferences_tab = QWidget()
        form = QFormLayout(preferences_tab)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark Mode", "dark")
        self.theme_combo.addItem("Light Mode", "light")
        self.theme_combo.setCurrentIndex(1 if current_theme == "light" else 0)
        self.update_channel_combo = QComboBox()
        self.update_channel_combo.addItem("Stable Releases", "stable")
        self.update_channel_combo.addItem("Beta / Pre-Releases", "beta")
        self.update_channel_combo.setCurrentIndex(1 if current_update_channel == "beta" else 0)
        self.tooltips_checkbox = QCheckBox("Show hover tooltips and tool hints")
        self.tooltips_checkbox.setChecked(current_tooltips_enabled)
        note = QLabel("Changes apply immediately and are saved for the next launch.")
        note.setWordWrap(True)
        form.addRow("Appearance", self.theme_combo)
        form.addRow("Tooltips", self.tooltips_checkbox)
        form.addRow("Update Channel", self.update_channel_combo)
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
        self.search_input.textChanged.connect(self.filter_settings)

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

    def filter_settings(self, text: str) -> None:
        query = text.strip().lower()
        if not query:
            self.search_status.setText("")
            return
        preferences_terms = (
            "appearance",
            "theme",
            "dark",
            "light",
            "update",
            "stable",
            "beta",
            "release",
            "tooltip",
            "tooltips",
            "hint",
            "hints",
            "help",
        )
        device_terms = (
            "audio",
            "device",
            "output",
            "speaker",
            "headphone",
            "windows",
            "default",
        )
        if any(term in query or query in term for term in preferences_terms):
            self.tabs.setCurrentIndex(0)
            self.search_status.setText("Showing matching settings in Preferences.")
            return
        if any(term in query or query in term for term in device_terms):
            self.tabs.setCurrentIndex(1)
            self.search_status.setText("Showing matching settings in Devices.")
            return
        self.search_status.setText("No direct setting match. Try theme, update, audio, device, or output.")

    def selected_theme(self) -> str:
        return str(self.theme_combo.currentData() or "dark")

    def selected_audio_output_device_id(self) -> str:
        return normalize_audio_output_device_id(self.audio_output_combo.currentData())

    def selected_update_channel(self) -> str:
        return "beta" if self.update_channel_combo.currentData() == "beta" else "stable"

    def selected_tooltips_enabled(self) -> bool:
        return self.tooltips_checkbox.isChecked()

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
        update_handler = getattr(parent, "apply_update_channel", None)
        if callable(update_handler):
            update_handler(self.selected_update_channel())
        tooltip_handler = getattr(parent, "apply_tooltips_enabled", None)
        if callable(tooltip_handler):
            tooltip_handler(self.selected_tooltips_enabled())
        audio_handler = getattr(parent, "apply_audio_output_device", None)
        if callable(audio_handler):
            self.current_audio_device_id = self.selected_audio_output_device_id()
            audio_handler(self.current_audio_device_id)

    def accept(self) -> None:
        self.apply_clicked()
        super().accept()
