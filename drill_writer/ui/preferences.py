from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
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
from drill_writer.ui.appearance import DOT_SYMBOL_OPTIONS, normalize_dot_symbol
from drill_writer.ui.theme import (
    CUSTOM_COLOR_KEYS,
    DEFAULT_THEME_TOKENS,
    FIELD_MODE_OPTIONS,
    normalize_field_mode,
    normalize_theme,
    theme_tokens,
)


class PreferencesDialog(QDialog):
    def __init__(
        self,
        current_theme: str,
        current_audio_device_id: str = DEFAULT_AUDIO_OUTPUT_DEVICE_ID,
        current_update_channel: str = "stable",
        current_tooltips_enabled: bool = True,
        current_dot_symbol: str = "circle",
        current_field_mode: str = "white",
        current_appearance_tokens: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(640)
        self.current_audio_device_id = normalize_audio_output_device_id(current_audio_device_id)
        self.current_theme = normalize_theme(current_theme)
        self.current_appearance_tokens = dict(current_appearance_tokens or theme_tokens(self.current_theme))
        self.color_buttons: dict[str, QPushButton] = {}

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
        self.theme_combo.currentIndexChanged.connect(self.theme_changed)
        self.field_mode_combo = QComboBox()
        for value, label in FIELD_MODE_OPTIONS:
            self.field_mode_combo.addItem(label, value)
        field_index = self.field_mode_combo.findData(normalize_field_mode(current_field_mode))
        self.field_mode_combo.setCurrentIndex(max(0, field_index))
        self.update_channel_combo = QComboBox()
        self.update_channel_combo.addItem("Stable Releases", "stable")
        self.update_channel_combo.addItem("Beta / Pre-Releases", "beta")
        self.update_channel_combo.setCurrentIndex(1 if current_update_channel == "beta" else 0)
        self.tooltips_checkbox = QCheckBox("Show hover tooltips and tool hints")
        self.tooltips_checkbox.setChecked(current_tooltips_enabled)
        self.dot_symbol_combo = QComboBox()
        for value, label in DOT_SYMBOL_OPTIONS:
            self.dot_symbol_combo.addItem(label, value)
        symbol_index = self.dot_symbol_combo.findData(normalize_dot_symbol(current_dot_symbol))
        self.dot_symbol_combo.setCurrentIndex(max(0, symbol_index))
        note = QLabel("Changes apply immediately and are saved for the next launch.")
        note.setWordWrap(True)
        form.addRow("Appearance", self.theme_combo)
        form.addRow("Field Mode", self.field_mode_combo)
        form.addRow("Marcher Symbol", self.dot_symbol_combo)
        form.addRow("Tooltips", self.tooltips_checkbox)
        form.addRow("Update Channel", self.update_channel_combo)
        form.addRow("", note)
        tabs.addTab(preferences_tab, "General")

        appearance_tab = QWidget()
        appearance_layout = QVBoxLayout(appearance_tab)
        appearance_form = QFormLayout()
        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(7.0, 14.0)
        self.font_size_spin.setSingleStep(0.2)
        self.font_size_spin.setValue(float(self.current_appearance_tokens.get("font_size", "8.8")))
        appearance_form.addRow("UI Font Size", self.font_size_spin)
        color_grid = QGridLayout()
        color_labels = {
            "background_color": "App Background",
            "panel_color": "Panel Background",
            "surface_color": "Cards / Tables",
            "input_color": "Input Background",
            "button_color": "Button Background",
            "text_color": "Text",
            "muted_text_color": "Muted Text",
            "border_color": "Borders",
            "accent_color": "Accent",
            "selection_color": "Selection",
        }
        for index, key in enumerate(CUSTOM_COLOR_KEYS):
            label = QLabel(color_labels.get(key, key.replace("_", " ").title()))
            button = QPushButton()
            button.clicked.connect(lambda _checked=False, selected_key=key: self.pick_color(selected_key))
            self.color_buttons[key] = button
            self.update_color_button(key, self.current_appearance_tokens.get(key, DEFAULT_THEME_TOKENS[self.current_theme][key]))
            color_grid.addWidget(label, index // 2, (index % 2) * 2)
            color_grid.addWidget(button, index // 2, (index % 2) * 2 + 1)
        defaults_button = QPushButton("Load Defaults For Selected Theme")
        defaults_button.clicked.connect(self.load_theme_defaults)
        appearance_note = QLabel(
            "These colors control panels, menus, buttons, text boxes, tables, tabs, cards, and command UI. "
            "Plugins may still add their own styling."
        )
        appearance_note.setWordWrap(True)
        appearance_layout.addLayout(appearance_form)
        appearance_layout.addLayout(color_grid)
        appearance_layout.addWidget(defaults_button)
        appearance_layout.addWidget(appearance_note)
        appearance_layout.addStretch(1)
        tabs.addTab(appearance_tab, "Appearance")

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
            "field",
            "white",
            "inverted",
            "grass",
            "custom",
            "color",
            "colors",
            "background",
            "panel",
            "accent",
            "font",
            "update",
            "stable",
            "beta",
            "release",
            "tooltip",
            "tooltips",
            "hint",
            "hints",
            "help",
            "marcher",
            "symbol",
            "symbols",
            "dot",
            "dots",
            "x",
            "shape",
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
            appearance_terms = ("field", "white", "inverted", "grass", "custom", "color", "colors", "background", "panel", "accent", "font")
            self.tabs.setCurrentIndex(1 if any(term in query or query in term for term in appearance_terms) else 0)
            self.search_status.setText("Showing matching settings in General or Appearance.")
            return
        if any(term in query or query in term for term in device_terms):
            self.tabs.setCurrentIndex(2)
            self.search_status.setText("Showing matching settings in Devices.")
            return
        self.search_status.setText("No direct setting match. Try theme, update, audio, device, or output.")

    def selected_theme(self) -> str:
        return normalize_theme(str(self.theme_combo.currentData() or "dark"))

    def selected_field_mode(self) -> str:
        return normalize_field_mode(str(self.field_mode_combo.currentData() or "white"))

    def selected_appearance_tokens(self) -> dict[str, str]:
        values = {
            key: str(button.property("selected_color") or DEFAULT_THEME_TOKENS[self.selected_theme()][key])
            for key, button in self.color_buttons.items()
        }
        values["font_size"] = f"{self.font_size_spin.value():.1f}"
        return values

    def selected_audio_output_device_id(self) -> str:
        return normalize_audio_output_device_id(self.audio_output_combo.currentData())

    def selected_update_channel(self) -> str:
        return "beta" if self.update_channel_combo.currentData() == "beta" else "stable"

    def selected_tooltips_enabled(self) -> bool:
        return self.tooltips_checkbox.isChecked()

    def selected_dot_symbol(self) -> str:
        return normalize_dot_symbol(self.dot_symbol_combo.currentData())

    def theme_changed(self) -> None:
        self.load_theme_defaults()

    def update_color_button(self, key: str, color: str) -> None:
        button = self.color_buttons[key]
        qcolor = QColor(color)
        text_color = "#101419" if qcolor.isValid() and qcolor.lightness() > 145 else "#ffffff"
        button.setProperty("selected_color", color)
        button.setText(color)
        button.setStyleSheet(f"background: {color}; color: {text_color};")

    def pick_color(self, key: str) -> None:
        current = str(self.color_buttons[key].property("selected_color") or DEFAULT_THEME_TOKENS[self.selected_theme()][key])
        color = QColorDialog.getColor(QColor(current), self, f"Choose {key.replace('_', ' ').title()}")
        if color.isValid():
            self.update_color_button(key, color.name())

    def load_theme_defaults(self) -> None:
        defaults = DEFAULT_THEME_TOKENS[self.selected_theme()]
        self.font_size_spin.setValue(float(defaults.get("font_size", "8.8")))
        for key in CUSTOM_COLOR_KEYS:
            self.update_color_button(key, defaults[key])

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
            self.call_parent_handler(handler, self._applied_theme)
        appearance_handler = getattr(parent, "apply_appearance_tokens", None)
        if callable(appearance_handler):
            self.call_parent_handler(appearance_handler, self.selected_appearance_tokens())
        field_handler = getattr(parent, "apply_field_mode", None)
        if callable(field_handler):
            self.call_parent_handler(field_handler, self.selected_field_mode())
        update_handler = getattr(parent, "apply_update_channel", None)
        if callable(update_handler):
            self.call_parent_handler(update_handler, self.selected_update_channel())
        tooltip_handler = getattr(parent, "apply_tooltips_enabled", None)
        if callable(tooltip_handler):
            self.call_parent_handler(tooltip_handler, self.selected_tooltips_enabled())
        dot_symbol_handler = getattr(parent, "apply_dot_symbol", None)
        if callable(dot_symbol_handler):
            self.call_parent_handler(dot_symbol_handler, self.selected_dot_symbol())
        audio_handler = getattr(parent, "apply_audio_output_device", None)
        if callable(audio_handler):
            self.current_audio_device_id = self.selected_audio_output_device_id()
            self.call_parent_handler(audio_handler, self.current_audio_device_id)

    def call_parent_handler(self, handler, *args) -> None:
        try:
            handler(*args)
        except RuntimeError as exc:
            if "already deleted" in str(exc):
                return
            raise

    def accept(self) -> None:
        self.apply_clicked()
        super().accept()
