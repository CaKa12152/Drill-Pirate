from __future__ import annotations


APP_STYLESHEET = """
QMainWindow, QWidget {
    background: #16181d;
    color: #f2f4f8;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}
QToolBar, QStatusBar {
    background: #111318;
    border: 0;
}
QPushButton, QToolButton {
    background: #242832;
    border: 1px solid #343a46;
    border-radius: 5px;
    color: #f2f4f8;
    padding: 6px 9px;
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
    padding: 4px;
}
QGroupBox {
    border: 1px solid #303642;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 12px;
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
    padding: 4px;
}
QSplitter::handle {
    background: #0f1116;
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
    background: #1a1f28;
    border: 1px solid #2d3542;
    border-radius: 16px;
}
#HomeTitle {
    color: #f2f4f8;
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
