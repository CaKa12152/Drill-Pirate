from __future__ import annotations


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


def theme_stylesheet(mode: str) -> str:
    return LIGHT_STYLESHEET if mode == "light" else DARK_STYLESHEET


APP_STYLESHEET = DARK_STYLESHEET
