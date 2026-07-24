from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from drill_writer.resources import field_logo_path
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
        current_adaptive_playback: bool = True,
        current_playback_cache: bool = True,
        current_show_field_logo: bool = True,
        current_field_logo_custom_path: str = "",
        current_field_logo_opacity: float = 1.0,
        current_field_logo_scale: float = 1.0,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumSize(640, 430)
        self.resize(760, 560)
        self.current_audio_device_id = normalize_audio_output_device_id(current_audio_device_id)
        self.current_theme = normalize_theme(current_theme)
        self.current_appearance_tokens = dict(current_appearance_tokens or theme_tokens(self.current_theme))
        self.color_buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search settings...")
        self.search_status = QLabel("")
        self.search_status.setWordWrap(True)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(True)
        tabs.tabBar().setExpanding(False)
        self.tabs = tabs
        layout.addWidget(self.search_input)
        layout.addWidget(self.search_status)
        layout.addWidget(tabs)

        preferences_tab = QWidget()
        form = QFormLayout(preferences_tab)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)
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
        self.field_logo_checkbox = QCheckBox("Show a logo at field center")
        self.field_logo_checkbox.setChecked(bool(current_show_field_logo))
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
        appearance_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        appearance_form.setHorizontalSpacing(12)
        appearance_form.setVerticalSpacing(9)
        self.font_size_spin = QDoubleSpinBox()
        self.font_size_spin.setRange(7.0, 14.0)
        self.font_size_spin.setSingleStep(0.2)
        self.font_size_spin.setValue(float(self.current_appearance_tokens.get("font_size", "9.2")))
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
            button.setMinimumWidth(104)
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

        field_logo_tab = QWidget()
        field_logo_layout = QVBoxLayout(field_logo_tab)
        field_logo_layout.setContentsMargins(16, 14, 16, 14)
        field_logo_layout.setSpacing(10)
        self.pending_field_logo_path = str(current_field_logo_custom_path or "").strip()
        self.field_logo_uses_default = not bool(self.pending_field_logo_path)
        self.field_logo_preview = QLabel()
        self.field_logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.field_logo_preview.setFixedHeight(170)
        self.field_logo_preview.setMinimumWidth(260)
        self.field_logo_preview.setStyleSheet("border: 1px solid palette(mid); border-radius: 6px;")
        self.field_logo_source_label = QLabel()
        self.field_logo_source_label.setWordWrap(True)
        self.field_logo_source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        upload_logo_button = QPushButton("Upload Image...")
        upload_logo_button.clicked.connect(self.choose_field_logo)
        default_logo_button = QPushButton("Use Drill Pirate Logo")
        default_logo_button.clicked.connect(self.use_default_field_logo)
        logo_button_row = QHBoxLayout()
        logo_button_row.addWidget(upload_logo_button)
        logo_button_row.addWidget(default_logo_button)
        logo_button_row.addStretch(1)

        logo_form = QFormLayout()
        logo_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        logo_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.field_logo_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.field_logo_opacity_slider.setRange(5, 100)
        self.field_logo_opacity_slider.setValue(round(max(0.05, min(1.0, current_field_logo_opacity)) * 100))
        self.field_logo_opacity_value = QLabel()
        opacity_row = QWidget()
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.addWidget(self.field_logo_opacity_slider, 1)
        opacity_layout.addWidget(self.field_logo_opacity_value)
        self.field_logo_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.field_logo_size_slider.setRange(25, 250)
        self.field_logo_size_slider.setValue(round(max(0.25, min(2.5, current_field_logo_scale)) * 100))
        self.field_logo_size_value = QLabel()
        size_row = QWidget()
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.addWidget(self.field_logo_size_slider, 1)
        size_layout.addWidget(self.field_logo_size_value)
        logo_form.addRow("Visibility", self.field_logo_checkbox)
        logo_form.addRow("Opacity", opacity_row)
        logo_form.addRow("Size", size_row)
        logo_note = QLabel(
            "Uploaded images are copied into Drill Pirate's app data and automatically adapt to "
            "the Grass, White, and Inverted field modes. PNG images with transparency work best."
        )
        logo_note.setWordWrap(True)
        field_logo_layout.addWidget(self.field_logo_preview)
        field_logo_layout.addWidget(self.field_logo_source_label)
        field_logo_layout.addLayout(logo_button_row)
        field_logo_layout.addLayout(logo_form)
        field_logo_layout.addWidget(logo_note)
        field_logo_layout.addStretch(1)
        tabs.addTab(field_logo_tab, "Field Logo")
        self.field_logo_opacity_slider.valueChanged.connect(self.update_field_logo_values)
        self.field_logo_size_slider.valueChanged.connect(self.update_field_logo_values)
        self.update_field_logo_preview()
        self.update_field_logo_values()

        devices_tab = QWidget()
        devices_layout = QVBoxLayout(devices_tab)
        devices_form = QFormLayout()
        devices_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        devices_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        devices_form.setHorizontalSpacing(12)
        devices_form.setVerticalSpacing(9)
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

        performance_tab = QWidget()
        performance_layout = QVBoxLayout(performance_tab)
        performance_form = QFormLayout()
        performance_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        performance_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.adaptive_playback_checkbox = QCheckBox(
            "Automatically reduce render detail when playback misses its frame budget"
        )
        self.adaptive_playback_checkbox.setChecked(bool(current_adaptive_playback))
        self.playback_cache_checkbox = QCheckBox(
            "Cache evaluated playback frames for loops and repeated previews"
        )
        self.playback_cache_checkbox.setChecked(bool(current_playback_cache))
        performance_note = QLabel(
            "Timing and audio remain authoritative. Adaptive mode only reduces visual detail and "
            "nonessential panel refreshes; it never changes marcher positions or show timing."
        )
        performance_note.setWordWrap(True)
        performance_form.addRow("Adaptive Quality", self.adaptive_playback_checkbox)
        performance_form.addRow("Frame Cache", self.playback_cache_checkbox)
        performance_layout.addLayout(performance_form)
        performance_layout.addWidget(performance_note)
        performance_layout.addStretch(1)
        tabs.addTab(performance_tab, "Playback")
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
            "logo",
            "center field",
            "emblem",
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
        playback_terms = (
            "playback",
            "performance",
            "adaptive",
            "quality",
            "cache",
            "frame",
            "fps",
            "dropped",
        )
        logo_terms = ("logo", "center field", "emblem", "branding", "transparency", "opacity", "size")
        if any(term in query or query in term for term in logo_terms):
            self.tabs.setCurrentIndex(2)
            self.search_status.setText("Showing matching settings in Field Logo.")
            return
        if any(term in query or query in term for term in preferences_terms):
            appearance_terms = ("field", "white", "inverted", "grass", "custom", "color", "colors", "background", "panel", "accent", "font")
            self.tabs.setCurrentIndex(1 if any(term in query or query in term for term in appearance_terms) else 0)
            self.search_status.setText("Showing matching settings in General or Appearance.")
            return
        if any(term in query or query in term for term in device_terms):
            self.tabs.setCurrentIndex(3)
            self.search_status.setText("Showing matching settings in Devices.")
            return
        if any(term in query or query in term for term in playback_terms):
            self.tabs.setCurrentIndex(4)
            self.search_status.setText("Showing matching settings in Playback.")
            return
        self.search_status.setText("No direct setting match. Try theme, audio, device, playback, cache, or quality.")

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

    def selected_field_logo_visible(self) -> bool:
        return self.field_logo_checkbox.isChecked()

    def selected_field_logo_custom_path(self) -> str:
        return "" if self.field_logo_uses_default else self.pending_field_logo_path

    def selected_field_logo_opacity(self) -> float:
        return self.field_logo_opacity_slider.value() / 100.0

    def selected_field_logo_scale(self) -> float:
        return self.field_logo_size_slider.value() / 100.0

    def choose_field_logo(self) -> None:
        start = self.pending_field_logo_path or str(Path.home() / "Pictures")
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose Center-Field Logo",
            start,
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not selected:
            return
        preview = QPixmap(selected)
        if preview.isNull():
            QMessageBox.warning(self, "Invalid Logo", "The selected file is not a supported or readable image.")
            return
        self.pending_field_logo_path = selected
        self.field_logo_uses_default = False
        self.update_field_logo_preview()

    def use_default_field_logo(self) -> None:
        self.pending_field_logo_path = ""
        self.field_logo_uses_default = True
        self.update_field_logo_preview()

    def update_field_logo_preview(self) -> None:
        source = field_logo_path() if self.field_logo_uses_default else Path(self.pending_field_logo_path)
        preview = QPixmap(str(source))
        if preview.isNull():
            self.field_logo_preview.setText("Image preview unavailable")
        else:
            canvas = QPixmap(250, 160)
            canvas.fill(Qt.GlobalColor.transparent)
            size_multiplier = self.field_logo_size_slider.value() / 100.0
            scaled = preview.scaled(
                min(240, round(105 * size_multiplier)),
                min(150, round(105 * size_multiplier)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter = QPainter(canvas)
            painter.setOpacity(self.field_logo_opacity_slider.value() / 100.0)
            painter.drawPixmap(
                round((canvas.width() - scaled.width()) / 2),
                round((canvas.height() - scaled.height()) / 2),
                scaled,
            )
            painter.end()
            self.field_logo_preview.setPixmap(canvas)
        self.field_logo_source_label.setText(
            "Current image: Drill Pirate default"
            if self.field_logo_uses_default
            else f"Current image: {source.name}\n{source}"
        )

    def update_field_logo_values(self) -> None:
        self.field_logo_opacity_value.setText(f"{self.field_logo_opacity_slider.value()}%")
        self.field_logo_size_value.setText(f"{self.field_logo_size_slider.value()}%")
        self.update_field_logo_preview()

    def selected_adaptive_playback(self) -> bool:
        return self.adaptive_playback_checkbox.isChecked()

    def selected_playback_cache(self) -> bool:
        return self.playback_cache_checkbox.isChecked()

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
        self.font_size_spin.setValue(float(defaults.get("font_size", "9.2")))
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
        field_logo_handler = getattr(parent, "apply_field_logo_visible", None)
        if callable(field_logo_handler):
            self.call_parent_handler(field_logo_handler, self.selected_field_logo_visible())
        field_logo_appearance_handler = getattr(parent, "apply_field_logo_appearance", None)
        if callable(field_logo_appearance_handler):
            self.call_parent_handler(
                field_logo_appearance_handler,
                self.selected_field_logo_custom_path(),
                self.field_logo_uses_default,
                self.selected_field_logo_opacity(),
                self.selected_field_logo_scale(),
            )
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
        playback_handler = getattr(parent, "apply_playback_performance_settings", None)
        if callable(playback_handler):
            self.call_parent_handler(
                playback_handler,
                self.selected_adaptive_playback(),
                self.selected_playback_cache(),
            )

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
