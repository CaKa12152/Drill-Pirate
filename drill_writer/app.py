from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QStackedWidget

from drill_writer.core.plugin_manager import PluginManager
from drill_writer.ui.main_window import MainWindow
from drill_writer.ui.startup import SplashPage, StartupPage
from drill_writer.ui.theme import APP_STYLESHEET


class DrillWriterApp(QStackedWidget):
    def __init__(self) -> None:
        super().__init__()
        self.plugin_manager = PluginManager(APP_STYLESHEET)
        self.splash = SplashPage()
        self.startup = StartupPage(self.plugin_manager)
        self.startup.project_ready.connect(self.open_project)
        self.addWidget(self.splash)
        self.addWidget(self.startup)
        self.setWindowTitle("Drill Pirate")
        self.resize(1120, 760)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            self.plugin_manager.register_app(app, self.startup)
        QTimer.singleShot(1300, self.show_home)

    def show_home(self) -> None:
        self.setCurrentWidget(self.startup)

    def open_project(self, project_dir: Path) -> None:
        window = MainWindow(project_dir)
        window.return_home_requested.connect(lambda selected_window=window: self.return_home(selected_window))
        self.addWidget(window)
        self.plugin_manager.register_main_window(window)
        self.setCurrentWidget(window)
        self.resize(1500, 900)

    def return_home(self, window: MainWindow) -> None:
        self.startup.refresh_projects()
        self.plugin_manager.unregister_main_window(window)
        self.setCurrentWidget(self.startup)
        self.removeWidget(window)
        window.deleteLater()
        self.resize(1120, 760)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = DrillWriterApp()
    window.show()
    return app.exec()
