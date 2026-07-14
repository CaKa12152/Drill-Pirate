from __future__ import annotations

from PySide6.QtCore import QSettings


FIELD_MODE_OPTIONS = (
    ("white", "White Field"),
    ("inverted", "Inverted Field"),
    ("grass", "Grass Field"),
)

CUSTOM_COLOR_KEYS = (
    "background_color",
    "panel_color",
    "surface_color",
    "input_color",
    "button_color",
    "text_color",
    "muted_text_color",
    "border_color",
    "accent_color",
    "selection_color",
)

DEFAULT_THEME_TOKENS = {
    "dark": {
        "background_color": "#121419",
        "panel_color": "#171b23",
        "surface_color": "#1d222b",
        "input_color": "#20242d",
        "button_color": "#242832",
        "text_color": "#f2f4f8",
        "muted_text_color": "#aeb7c8",
        "border_color": "#303642",
        "accent_color": "#f7c94a",
        "selection_color": "#2f6fed",
        "font_size": "9.2",
    },
    "light": {
        "background_color": "#f4f6fa",
        "panel_color": "#ffffff",
        "surface_color": "#f8fbff",
        "input_color": "#ffffff",
        "button_color": "#ffffff",
        "text_color": "#18202b",
        "muted_text_color": "#5c6676",
        "border_color": "#c8d0dc",
        "accent_color": "#2f6fed",
        "selection_color": "#2f6fed",
        "font_size": "9.2",
    },
}


def normalize_theme(mode: str | None) -> str:
    return "light" if mode == "light" else "dark"


def normalize_field_mode(mode: str | None) -> str:
    return mode if mode in {value for value, _label in FIELD_MODE_OPTIONS} else "white"


def valid_color(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) not in (4, 7):
        return False
    if not value.startswith("#"):
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return True


def theme_tokens(mode: str, settings: QSettings | None = None) -> dict[str, str]:
    normalized = normalize_theme(mode)
    tokens = dict(DEFAULT_THEME_TOKENS[normalized])
    if settings is None:
        return tokens
    for key in CUSTOM_COLOR_KEYS:
        value = settings.value(f"appearance/{key}", "")
        if valid_color(value):
            tokens[key] = str(value)
    font_size = settings.value("appearance/font_size", tokens["font_size"])
    try:
        tokens["font_size"] = f"{max(7.0, min(14.0, float(font_size))):.1f}"
    except (TypeError, ValueError):
        pass
    return tokens


def reset_custom_appearance(settings: QSettings) -> None:
    for key in CUSTOM_COLOR_KEYS:
        settings.remove(f"appearance/{key}")
    settings.remove("appearance/font_size")


def custom_override_stylesheet(tokens: dict[str, str]) -> str:
    background = tokens["background_color"]
    panel = tokens["panel_color"]
    surface = tokens["surface_color"]
    input_color = tokens["input_color"]
    button = tokens["button_color"]
    text = tokens["text_color"]
    muted = tokens["muted_text_color"]
    border = tokens["border_color"]
    accent = tokens["accent_color"]
    selection = tokens["selection_color"]
    font_size = tokens["font_size"]
    return f"""
QMainWindow, QDialog, QWidget {{
    background: {background};
    color: {text};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: {font_size}pt;
}}
QLabel, QCheckBox, QRadioButton {{
    color: {text};
    background: transparent;
}}
QFrame, QStackedWidget, QScrollArea, QAbstractScrollArea, QTabWidget::pane {{
    background: {background};
    color: {text};
    border-color: {border};
}}
QGroupBox, QDockWidget {{
    background: {panel};
    color: {text};
    border-color: {border};
}}
QGroupBox {{
    border: 1px solid {border};
    border-radius: 7px;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
}}
QGroupBox::title, QDockWidget::title {{
    color: {muted};
    background: {panel};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
QMenuBar, QMenu, QToolBar, QStatusBar {{
    background: {panel};
    color: {text};
    border-color: {border};
}}
QMenuBar::item {{
    padding: 5px 9px;
    margin: 1px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background: {surface};
}}
QMenu::item:selected, QComboBox QAbstractItemView::item:selected {{
    background: {selection};
    color: white;
}}
QPushButton, QToolButton {{
    background: {button};
    color: {text};
    border: 1px solid {border};
    border-radius: 5px;
    min-height: 22px;
    padding: 3px 8px;
}}
QPushButton:hover, QToolButton:hover {{
    background: {surface};
    border-color: {accent};
}}
QPushButton:checked, QToolButton:checked {{
    background: {selection};
    color: white;
    border-color: {selection};
}}
QLineEdit, QTextEdit, QPlainTextEdit, QTextBrowser,
QSpinBox, QDoubleSpinBox, QComboBox,
QListWidget, QListView, QTreeWidget, QTreeView,
QTableWidget, QTableView {{
    background: {input_color};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    selection-background-color: {selection};
    selection-color: white;
}}
QLineEdit, QTextEdit, QPlainTextEdit, QTextBrowser,
QSpinBox, QDoubleSpinBox, QComboBox {{
    min-height: 22px;
    padding: 2px 5px;
}}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled,
QListWidget:disabled, QTreeWidget:disabled, QTableWidget:disabled,
QPushButton:disabled, QToolButton:disabled {{
    background: {surface};
    color: {muted};
    border-color: {border};
}}
QComboBox QAbstractItemView {{
    background: {input_color};
    color: {text};
    border: 1px solid {border};
}}
QHeaderView::section {{
    background: {surface};
    color: {text};
    border: 1px solid {border};
    padding: 4px 6px;
}}
QTableWidget, QTableView {{
    gridline-color: {border};
    alternate-background-color: {surface};
}}
QTabBar::tab {{
    background: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 7px;
    min-height: 22px;
    padding: 4px 10px;
}}
QTabBar::tab:selected {{
    background: {selection};
    color: white;
    border-color: {selection};
}}
QSplitter::handle, QScrollBar::handle {{
    background: {border};
}}
QScrollBar {{
    background: {surface};
    border: 0;
}}
QScrollBar:vertical {{
    width: 10px;
}}
QScrollBar:horizontal {{
    height: 10px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    min-height: 24px;
    min-width: 24px;
    border-radius: 5px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QToolTip {{
    background: {panel};
    color: {text};
    border: 1px solid {accent};
    border-radius: 5px;
    padding: 6px 8px;
}}
#SideTabs QTabBar::tab, #HomeTabs QTabBar::tab {{
    background: {surface};
    color: {text};
    border-color: {border};
}}
#SideTabs QTabBar::tab:selected, #HomeTabs QTabBar::tab:selected {{
    background: {selection};
    color: white;
    border-color: {selection};
}}
#PanelPageSwitcher {{
    background: transparent;
}}
#PanelPageSelector {{
    background: {surface};
    color: {text};
    border: 1px solid {border};
    border-left: 3px solid {accent};
    border-radius: 6px;
    min-height: 28px;
    padding: 3px 8px;
    font-weight: 650;
}}
#PanelPageSelector:hover {{
    border-color: {accent};
}}
#FieldView {{
    border: 1px solid {border};
}}
#CoordinateReadout, #ColorSwatch {{
    background: {surface};
    border: 1px solid {border};
    color: {accent};
}}
#ToolHintLabel {{
    color: {muted};
}}
#ProjectCard, #PluginCard {{
    background: {surface};
    color: {text};
    border: 1px solid {border};
}}
#ProjectCard:hover, #PluginCard:hover {{
    border-color: {accent};
}}
#HomePage {{
    background: {background};
}}
#HomeTitle {{
    color: {accent};
}}
#PluginStatusInactive {{
    background: {surface};
    color: {muted};
}}
"""

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background: #121419;
    color: #f2f4f8;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 8.8pt;
}
QMenuBar, QMenu {
    background: #121419;
    color: #f2f4f8;
}
QMenu::item:selected {
    background: #303847;
}
QToolTip {
    background: #20242d;
    color: #f2f4f8;
    border: 1px solid #f7c94a;
    border-radius: 5px;
    padding: 6px 8px;
}
QToolBar, QStatusBar {
    background: #111318;
    border: 0;
}
QToolBar#WorkspaceToolbar {
    spacing: 4px;
    padding: 3px 6px;
    border-bottom: 1px solid #252b35;
}
QDockWidget::title {
    background: #171b23;
    border: 1px solid #252b35;
    border-radius: 6px;
    padding: 4px 7px;
    text-align: left;
    color: #d8deea;
}
QPushButton, QToolButton {
    background: #242832;
    border: 1px solid #343a46;
    border-radius: 5px;
    color: #f2f4f8;
    padding: 3px 6px;
}
QPushButton:hover, QToolButton:hover {
    background: #303644;
}
QPushButton:checked, QToolButton:checked {
    background: #2f6fed;
    border-color: #5d91ff;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget, QTableWidget, QSlider {
    background: #20242d;
    border: 1px solid #353b47;
    border-radius: 4px;
    color: #f2f4f8;
    padding: 2px 3px;
}
QGroupBox {
    border: 1px solid #303642;
    border-radius: 6px;
    margin-top: 7px;
    padding-top: 7px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #b8c0d0;
}
QHeaderView::section {
    background: #242832;
    color: #cfd6e6;
    border: 0;
    padding: 3px;
}
QTableWidget {
    gridline-color: #303642;
    alternate-background-color: #1b1f27;
}
QTableWidget::item {
    padding: 1px;
}
QSplitter::handle {
    background: #0f1116;
}
#SideTabs::pane {
    border: 0;
}
#SideTabs QTabBar::tab {
    background: #1f2430;
    border: 1px solid #303847;
    border-radius: 7px;
    color: #cdd5e3;
    padding: 4px 7px;
    margin-right: 3px;
}
#SideTabs QTabBar::tab:selected {
    background: #303847;
    border-color: #58657a;
}
#FieldView {
    background: #101216;
    border: 1px solid #252b35;
}
#CoordinateReadout {
    background: #252b35;
    border: 1px solid #3a4352;
    border-radius: 5px;
    color: #f7d154;
    padding: 4px 6px;
    font-weight: 650;
}
#ColorSwatch {
    background: #252b35;
    border: 1px solid #3a4352;
    border-radius: 5px;
    color: #cdd5e3;
    padding: 3px 6px;
}
#ProjectCard {
    background: #1d222b;
    border: 1px solid #2f3744;
    border-radius: 13px;
}
#ProjectCard:hover {
    background: #242b36;
    border-color: #f7d154;
}
#HomePage {
    background: #13161c;
}
#HomeHero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #111214, stop:0.64 #181a1e, stop:1 #211b0e);
    border: 1px solid rgba(247, 201, 74, 0.34);
    border-radius: 16px;
}
#HomeTitle {
    color: #f7c94a;
}
#HomeTabs::pane {
    border: 0;
    background: transparent;
}
#HomeTabs QTabBar::tab {
    background: #202630;
    border: 1px solid #303947;
    border-radius: 9px;
    color: #cdd5e3;
    padding: 8px 18px;
    margin-right: 8px;
}
#HomeTabs QTabBar::tab:selected {
    background: #2f6fed;
    color: white;
    border-color: #5d91ff;
}
#PluginCard {
    background: #1d222b;
    border: 1px solid #2f3744;
    border-radius: 13px;
}
#PluginCard:hover {
    background: #242b36;
    border-color: #6f7f99;
}
#PluginStatusActive {
    background: #1d7f46;
    color: white;
    border-radius: 8px;
    padding: 3px 8px;
}
#PluginStatusInactive {
    background: #343b47;
    color: #cbd3e1;
    border-radius: 8px;
    padding: 3px 8px;
}
"""


LIGHT_STYLESHEET = """
QMainWindow, QWidget {
    background: #f4f6fa;
    color: #18202b;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 8.8pt;
}
QMenuBar, QMenu {
    background: #ffffff;
    color: #18202b;
}
QMenu::item:selected {
    background: #dce7ff;
}
QToolTip {
    background: #ffffff;
    color: #18202b;
    border: 1px solid #2f6fed;
    border-radius: 5px;
    padding: 6px 8px;
}
QToolBar, QStatusBar {
    background: #ffffff;
    border: 0;
}
QToolBar#WorkspaceToolbar {
    spacing: 4px;
    padding: 3px 6px;
    border-bottom: 1px solid #d9dfe8;
}
QDockWidget::title {
    background: #ffffff;
    border: 1px solid #d1d8e4;
    border-radius: 6px;
    padding: 4px 7px;
    text-align: left;
    color: #2c3544;
}
QPushButton, QToolButton {
    background: #ffffff;
    border: 1px solid #c8d0dc;
    border-radius: 5px;
    color: #18202b;
    padding: 3px 6px;
}
QPushButton:hover, QToolButton:hover {
    background: #eef3fb;
}
QPushButton:checked, QToolButton:checked {
    background: #2f6fed;
    border-color: #2559bd;
    color: white;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget, QTableWidget, QSlider {
    background: #ffffff;
    border: 1px solid #c8d0dc;
    border-radius: 4px;
    color: #18202b;
    padding: 2px 3px;
}
QGroupBox {
    border: 1px solid #d0d7e2;
    border-radius: 6px;
    margin-top: 7px;
    padding-top: 7px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #4b5565;
}
QHeaderView::section {
    background: #eef2f7;
    color: #283241;
    border: 0;
    padding: 3px;
}
QTableWidget {
    gridline-color: #d6dde8;
    alternate-background-color: #f5f8fc;
}
QTableWidget::item {
    padding: 1px;
}
QSplitter::handle {
    background: #d9dfe8;
}
#SideTabs::pane {
    border: 0;
}
#SideTabs QTabBar::tab {
    background: #ffffff;
    border: 1px solid #d1d8e4;
    border-radius: 7px;
    color: #2c3544;
    padding: 4px 7px;
    margin-right: 3px;
}
#SideTabs QTabBar::tab:selected {
    background: #e8eef8;
    border-color: #aeb9c9;
}
#FieldView {
    background: #eef2f7;
    border: 1px solid #c8d0dc;
}
#CoordinateReadout {
    background: #fff7dc;
    border: 1px solid #e0c566;
    border-radius: 5px;
    color: #6e5200;
    padding: 4px 6px;
    font-weight: 650;
}
#ColorSwatch {
    background: #ffffff;
    border: 1px solid #c8d0dc;
    border-radius: 5px;
    color: #2c3544;
    padding: 3px 6px;
}
#ProjectCard {
    background: #ffffff;
    border: 1px solid #d1d8e4;
    border-radius: 13px;
}
#ProjectCard:hover {
    background: #f8fbff;
    border-color: #2f6fed;
}
#HomePage {
    background: #f4f6fa;
}
#HomeHero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #101112, stop:0.68 #1b1d21, stop:1 #fff3c8);
    border: 1px solid #d7aa32;
    border-radius: 16px;
}
#HomeTitle {
    color: #f7c94a;
}
#HomeTabs::pane {
    border: 0;
    background: transparent;
}
#HomeTabs QTabBar::tab {
    background: #ffffff;
    border: 1px solid #d1d8e4;
    border-radius: 9px;
    color: #2c3544;
    padding: 8px 18px;
    margin-right: 8px;
}
#HomeTabs QTabBar::tab:selected {
    background: #2f6fed;
    color: white;
    border-color: #2559bd;
}
#PluginCard {
    background: #ffffff;
    border: 1px solid #d1d8e4;
    border-radius: 13px;
}
#PluginCard:hover {
    background: #f8fbff;
    border-color: #98a4b5;
}
#PluginStatusActive {
    background: #1d7f46;
    color: white;
    border-radius: 8px;
    padding: 3px 8px;
}
#PluginStatusInactive {
    background: #e4e9f1;
    color: #4b5565;
    border-radius: 8px;
    padding: 3px 8px;
}
"""


def theme_stylesheet(mode: str, settings: QSettings | None = None) -> str:
    normalized = normalize_theme(mode)
    base = LIGHT_STYLESHEET if normalized == "light" else DARK_STYLESHEET
    return base + "\n" + custom_override_stylesheet(theme_tokens(normalized, settings))


APP_STYLESHEET = DARK_STYLESHEET
