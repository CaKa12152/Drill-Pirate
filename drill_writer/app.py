from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
)

from drill_writer.core.diagnostics import (
    clear_pending_release_notes_file,
    export_bug_report_bundle,
    install_exception_hook,
    log_exception,
    read_pending_release_notes,
    write_pending_release_notes,
)
from drill_writer.core.project_io import ProjectLoadError, create_tutorial_project, project_library_dir
from drill_writer.core.updater import (
    CURRENT_VERSION,
    UpdateInfo,
    fetch_release_by_tag,
    fetch_latest_release,
    fetch_latest_update,
    install_update,
    normalize_update_channel,
    version_tuple,
)
from drill_writer.core.plugin_manager import PluginManager
from drill_writer.resources import app_icon_path
from drill_writer.ui.audio_devices import (
    AUDIO_OUTPUT_DEVICE_SETTING,
    DEFAULT_AUDIO_OUTPUT_DEVICE_ID,
    audio_output_label_for_id,
    normalize_audio_output_device_id,
)
from drill_writer.ui.appearance import DOT_SYMBOL_SETTING, dot_symbol_label, preferred_dot_symbol
from drill_writer.ui.main_window import MainWindow
from drill_writer.ui.preferences import PreferencesDialog
from drill_writer.ui.startup import SplashPage, StartupPage
from drill_writer.ui.theme import CUSTOM_COLOR_KEYS, normalize_field_mode, normalize_theme, theme_stylesheet, theme_tokens


class UpdateCheckThread(QThread):
    finished_check = Signal(object)

    def __init__(self, channel: str, parent=None) -> None:
        super().__init__(parent)
        self.channel = normalize_update_channel(channel)

    def run(self) -> None:
        self.finished_check.emit(fetch_latest_update(channel=self.channel))


class ReleaseNotesThread(QThread):
    finished_notes = Signal(object)

    def __init__(self, tag: str, parent=None) -> None:
        super().__init__(parent)
        self.tag = tag

    def run(self) -> None:
        self.finished_notes.emit(fetch_release_by_tag(self.tag) or fetch_latest_release())


class DrillWriterApp(QStackedWidget):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings("OpenAI", "DrillWriter")
        self.update_thread: UpdateCheckThread | None = None
        self.release_notes_thread: ReleaseNotesThread | None = None
        self.plugin_manager = PluginManager(theme_stylesheet(self.theme_mode(), self.settings))
        self.splash = SplashPage()
        self.startup = StartupPage(self.plugin_manager)
        self.startup.project_ready.connect(self.open_project)
        self.startup.settings_requested.connect(self.show_preferences)
        self.addWidget(self.splash)
        self.addWidget(self.startup)
        self.setWindowTitle("Drill Pirate")
        self.setWindowIcon(QIcon(str(app_icon_path())))
        self.resize(1120, 760)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            self.plugin_manager.register_app(app, self.startup)
        QTimer.singleShot(1300, self.show_home)
        QTimer.singleShot(1650, self.check_pending_release_notes)
        QTimer.singleShot(2200, self.check_for_updates)
        QTimer.singleShot(3200, self.show_onboarding_if_needed)

    def show_home(self) -> None:
        self.setCurrentWidget(self.startup)

    def show_onboarding_if_needed(self) -> None:
        if self.currentWidget() is not self.startup:
            return
        if self.settings.value("onboarding/workflow_v1_seen", False, type=bool):
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Welcome to Drill Pirate")
        dialog.setModal(True)
        dialog.resize(560, 430)
        layout = QVBoxLayout(dialog)
        title = QLabel("Drill Pirate Alpha")
        title.setStyleSheet("font-size: 22px; font-weight: 800;")
        intro = QTextBrowser()
        intro.setOpenExternalLinks(True)
        intro.setHtml(
            """
            <h3>Start with a safe workflow</h3>
            <ul>
              <li>Use <b>Workspaces</b> to switch between design, forms, rehearsal, and print views.</li>
              <li>Right-click path lines to add editable anchors; drag handles to shape paths.</li>
              <li>Use <b>Ctrl+Shift+P</b> for the command palette and <b>Ctrl+Alt+,</b> for shortcuts.</li>
              <li>Autosave backups and Restore Previous Save are available from the File menu.</li>
            </ul>
            <p>The tutorial project creates a small line-to-circle move you can safely edit.</p>
            """
        )
        button_row = QHBoxLayout()
        tutorial_button = QPushButton("Create Tutorial Project")
        close_button = QPushButton("Maybe Later")
        dont_show_button = QPushButton("Don't Show Again")
        tutorial_button.clicked.connect(dialog.accept)
        close_button.clicked.connect(dialog.reject)
        dont_show_button.clicked.connect(lambda: (self.settings.setValue("onboarding/workflow_v1_seen", True), dialog.done(2)))
        button_row.addStretch()
        button_row.addWidget(close_button)
        button_row.addWidget(dont_show_button)
        button_row.addWidget(tutorial_button)
        layout.addWidget(title)
        layout.addWidget(intro, 1)
        layout.addLayout(button_row)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            self.settings.setValue("onboarding/workflow_v1_seen", True)
            self.settings.sync()
            project_dir = create_tutorial_project(project_library_dir())
            self.startup.refresh_projects()
            self.open_project(project_dir)
        elif result == 2:
            self.settings.sync()

    def open_project(self, project_dir: Path) -> None:
        try:
            window = MainWindow(project_dir)
        except ProjectLoadError as exc:
            self.show_project_open_failed(project_dir, exc)
            return
        except Exception as exc:
            log_exception(type(exc), exc, exc.__traceback__, context=f"Open project failed: {project_dir}")
            self.show_unexpected_project_error(project_dir, exc)
            return
        window.field.set_canvas_theme(self.theme_mode())
        window.field.set_field_mode(self.field_mode())
        window.return_home_requested.connect(lambda selected_window=window: self.return_home(selected_window))
        self.addWidget(window)
        self.plugin_manager.register_main_window(window)
        self.setCurrentWidget(window)
        if not self.isMaximized() and not self.isFullScreen():
            self.resize(1500, 900)
        QTimer.singleShot(0, self.refresh_current_layout)

    def theme_mode(self) -> str:
        value = self.settings.value("appearance/theme", "dark")
        return normalize_theme(str(value))

    def field_mode(self) -> str:
        return normalize_field_mode(str(self.settings.value("appearance/field_mode", "white")))

    def appearance_tokens(self) -> dict[str, str]:
        return theme_tokens(self.theme_mode(), self.settings)

    def audio_output_device_id(self) -> str:
        return normalize_audio_output_device_id(
            self.settings.value(AUDIO_OUTPUT_DEVICE_SETTING, DEFAULT_AUDIO_OUTPUT_DEVICE_ID)
        )

    def tooltips_enabled(self) -> bool:
        return self.settings.value("ui/tooltips_enabled", True, type=bool)

    def dot_symbol(self) -> str:
        return preferred_dot_symbol(self.settings)

    def update_channel(self) -> str:
        return normalize_update_channel(self.settings.value("updates/channel", "stable"))

    def show_preferences(self) -> None:
        dialog = PreferencesDialog(
            self.theme_mode(),
            self.audio_output_device_id(),
            self.update_channel(),
            self.tooltips_enabled(),
            self.dot_symbol(),
            self.field_mode(),
            self.appearance_tokens(),
            self,
        )
        dialog.exec()

    def apply_theme(self, mode: str) -> None:
        normalized = normalize_theme(mode)
        self.settings.setValue("appearance/theme", normalized)
        self.settings.sync()
        self.refresh_app_theme()

    def apply_appearance_tokens(self, values: dict[str, str]) -> None:
        for key in CUSTOM_COLOR_KEYS:
            if key in values:
                self.settings.setValue(f"appearance/{key}", values[key])
        if "font_size" in values:
            self.settings.setValue("appearance/font_size", values["font_size"])
        self.settings.sync()
        self.refresh_app_theme()

    def refresh_app_theme(self) -> None:
        stylesheet = theme_stylesheet(self.theme_mode(), self.settings)
        self.plugin_manager.base_stylesheet = stylesheet
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(stylesheet)
        self.plugin_manager.reload_active_plugins()
        for index in range(self.count()):
            widget = self.widget(index)
            handler = getattr(widget, "apply_visual_theme", None)
            if callable(handler):
                handler(self.appearance_tokens())
        self.apply_canvas_theme(self.theme_mode())

    def apply_canvas_theme(self, mode: str) -> None:
        for index in range(self.count()):
            widget = self.widget(index)
            field = getattr(widget, "field", None)
            if field is not None and hasattr(field, "set_canvas_theme"):
                field.set_canvas_theme(mode)
            if field is not None and hasattr(field, "set_field_mode"):
                field.set_field_mode(self.field_mode())
            minimap = getattr(widget, "minimap", None)
            if minimap is not None:
                minimap.update()
            set_preview_handler = getattr(widget, "refresh_set_thumbnails", None)
            if callable(set_preview_handler):
                set_preview_handler()

    def apply_field_mode(self, mode: str) -> None:
        normalized = normalize_field_mode(mode)
        self.settings.setValue("appearance/field_mode", normalized)
        self.settings.sync()
        if hasattr(self.startup, "apply_field_mode"):
            self.startup.apply_field_mode(normalized)
        self.apply_canvas_theme(self.theme_mode())
        current = self.currentWidget()
        if isinstance(current, MainWindow):
            current.statusBar().showMessage(f"Field mode: {normalized.title()}", 2200)

    def apply_audio_output_device(self, device_id: str) -> None:
        normalized = normalize_audio_output_device_id(device_id)
        self.settings.setValue(AUDIO_OUTPUT_DEVICE_SETTING, normalized)
        self.settings.sync()
        for index in range(self.count()):
            widget = self.widget(index)
            handler = getattr(widget, "apply_audio_output_device", None)
            if callable(handler):
                handler(normalized)
        current = self.currentWidget()
        if isinstance(current, MainWindow):
            current.statusBar().showMessage(f"Audio output: {audio_output_label_for_id(normalized)}", 3000)

    def apply_update_channel(self, channel: str) -> None:
        normalized = normalize_update_channel(channel)
        self.settings.setValue("updates/channel", normalized)
        self.settings.sync()
        current = self.currentWidget()
        if isinstance(current, MainWindow):
            current.statusBar().showMessage(f"Update channel: {normalized.title()}", 3000)

    def apply_tooltips_enabled(self, enabled: bool) -> None:
        self.settings.setValue("ui/tooltips_enabled", bool(enabled))
        self.settings.sync()
        for index in range(self.count()):
            widget = self.widget(index)
            handler = getattr(widget, "apply_tooltips_enabled", None)
            if callable(handler):
                handler(bool(enabled))
        current = self.currentWidget()
        if isinstance(current, MainWindow):
            state = "enabled" if enabled else "disabled"
            current.statusBar().showMessage(f"Tooltips {state}", 2200)

    def apply_dot_symbol(self, symbol: str) -> None:
        self.settings.setValue(DOT_SYMBOL_SETTING, symbol)
        self.settings.sync()
        for index in range(self.count()):
            widget = self.widget(index)
            handler = getattr(widget, "apply_dot_symbol", None)
            if callable(handler):
                handler(symbol)
        current = self.currentWidget()
        if isinstance(current, MainWindow):
            current.statusBar().showMessage(f"Marcher symbol: {dot_symbol_label(symbol)}", 2200)

    def return_home(self, window: MainWindow) -> None:
        self.startup.refresh_projects()
        self.plugin_manager.unregister_main_window(window)
        release = getattr(window, "release_media_resources", None)
        if callable(release):
            release()
        self.setCurrentWidget(self.startup)
        self.removeWidget(window)
        window.deleteLater()
        if not self.isMaximized() and not self.isFullScreen():
            self.resize(1120, 760)
        QTimer.singleShot(0, self.refresh_current_layout)

    def refresh_current_layout(self) -> None:
        current = self.currentWidget()
        if current and current.layout():
            current.layout().activate()
        self.updateGeometry()
        self.repaint()

    def check_for_updates(self) -> None:
        if self.update_thread and self.update_thread.isRunning():
            return
        self.update_thread = UpdateCheckThread(self.update_channel(), self)
        self.update_thread.finished_check.connect(self.handle_update_check)
        self.update_thread.start()

    def check_pending_release_notes(self) -> None:
        target_tag = self.pending_release_notes_tag()
        seen_tag = str(self.settings.value("updates/release_notes_seen_tag", ""))
        if not target_tag:
            self.record_running_version()
            return
        if version_tuple(target_tag) != version_tuple(CURRENT_VERSION):
            if version_tuple(target_tag) < version_tuple(CURRENT_VERSION):
                self.clear_pending_release_notes()
            self.record_running_version()
            return
        if version_tuple(seen_tag) == version_tuple(target_tag):
            self.clear_pending_release_notes()
            self.record_running_version()
            return
        if self.release_notes_thread and self.release_notes_thread.isRunning():
            return
        self.release_notes_thread = ReleaseNotesThread(target_tag, self)
        self.release_notes_thread.finished_notes.connect(self.handle_release_notes)
        self.release_notes_thread.start()

    def pending_release_notes_tag(self) -> str:
        pending_tag = str(self.settings.value("updates/pending_release_notes_tag", ""))
        if not pending_tag:
            pending_payload = read_pending_release_notes()
            pending_tag = str(pending_payload.get("tag", ""))
        last_running_version = str(self.settings.value("updates/last_running_version", ""))
        if pending_tag and version_tuple(pending_tag) == version_tuple(CURRENT_VERSION):
            return pending_tag
        if last_running_version and version_tuple(CURRENT_VERSION) > version_tuple(last_running_version):
            return CURRENT_VERSION
        return ""

    def record_running_version(self) -> None:
        self.settings.setValue("updates/last_running_version", CURRENT_VERSION)
        self.settings.sync()

    def handle_release_notes(self, release: UpdateInfo | None) -> None:
        target_tag = self.pending_release_notes_tag()
        if not target_tag:
            self.record_running_version()
            return
        info = self.release_notes_for_display(release, target_tag)
        if info is None:
            self.record_release_notes_seen(target_tag)
            self.record_running_version()
            return
        self.show_release_notes_dialog(info)
        self.record_running_version()

    def release_notes_for_display(self, release: UpdateInfo | None, target_tag: str) -> UpdateInfo | None:
        if release and version_tuple(release.tag) == version_tuple(target_tag):
            return release
        fallback_body = str(self.settings.value("updates/pending_release_notes_body", ""))
        fallback_name = str(self.settings.value("updates/pending_release_notes_name", target_tag))
        fallback_url = str(self.settings.value("updates/pending_release_notes_url", ""))
        pending_payload = read_pending_release_notes()
        if not fallback_body:
            fallback_body = str(pending_payload.get("body", ""))
        if not fallback_name or fallback_name == target_tag:
            fallback_name = str(pending_payload.get("name", fallback_name or target_tag))
        if not fallback_url:
            fallback_url = str(pending_payload.get("html_url", ""))
        if fallback_body or fallback_name:
            return UpdateInfo(
                tag=target_tag,
                name=fallback_name or target_tag,
                html_url=fallback_url,
                body=fallback_body,
                asset=None,
            )
        return UpdateInfo(
            tag=target_tag,
            name=target_tag,
            html_url="",
            body="No release description was available from GitHub.",
            asset=None,
        )

    def show_release_notes_dialog(self, release: UpdateInfo) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Drill Pirate {release.tag} Update Log")
        dialog.setModal(True)
        dialog.resize(720, 520)

        layout = QVBoxLayout(dialog)
        title = QLabel(f"Updated to Drill Pirate {release.tag}")
        title.setStyleSheet("font-size: 20px; font-weight: 750;")
        subtitle = QLabel(release.name or release.tag)
        subtitle.setStyleSheet("color: #aeb7c8;")
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        body = release.body.strip() or "No release description was provided on GitHub."
        if hasattr(notes, "setMarkdown"):
            notes.setMarkdown(body)
        else:
            notes.setPlainText(body)

        button_row = QHBoxLayout()
        ok_button = QPushButton("Ok")
        dont_show_button = QPushButton("Dont Show Again")
        button_row.addStretch()
        button_row.addWidget(dont_show_button)
        button_row.addWidget(ok_button)

        result = {"dont_show": False}
        ok_button.clicked.connect(dialog.accept)

        def dont_show_again() -> None:
            result["dont_show"] = True
            dialog.accept()

        dont_show_button.clicked.connect(dont_show_again)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(notes, 1)
        layout.addLayout(button_row)
        dialog.exec()

        self.record_release_notes_seen(release.tag, suppress=bool(result["dont_show"]))

    def record_release_notes_seen(self, tag: str, suppress: bool = False) -> None:
        self.settings.setValue("updates/release_notes_seen_tag", tag)
        if suppress:
            self.settings.setValue("updates/release_notes_suppressed_tag", tag)
        self.clear_pending_release_notes(sync=False)
        self.settings.sync()

    def clear_pending_release_notes(self, sync: bool = True) -> None:
        for key in (
            "updates/pending_release_notes_tag",
            "updates/pending_release_notes_name",
            "updates/pending_release_notes_body",
            "updates/pending_release_notes_url",
        ):
            self.settings.remove(key)
        clear_pending_release_notes_file()
        if sync:
            self.settings.sync()

    def handle_update_check(self, update: UpdateInfo | None) -> None:
        if not update:
            return
        skipped_tag = self.settings.value("updates/skipped_tag", "")
        if skipped_tag == update.tag:
            return
        message = QMessageBox(self)
        message.setWindowTitle("Drill Pirate Update Available")
        message.setIcon(QMessageBox.Icon.Information)
        channel_label = update.channel.title()
        message.setText(f"Drill Pirate {update.tag} is available on the {channel_label} channel.")
        message.setInformativeText(
            "Install downloads the selected GitHub release without requiring Git.\n"
            "Skip hides this version until a newer release is published.\n"
            "Ignore closes this prompt for now.\n\n"
            "Downloaded ZIP updates are size-checked, optionally SHA-256 verified, and installed with rollback."
        )
        install_button = message.addButton("Install", QMessageBox.ButtonRole.AcceptRole)
        skip_button = message.addButton("Skip This Version", QMessageBox.ButtonRole.DestructiveRole)
        ignore_button = message.addButton("Ignore", QMessageBox.ButtonRole.RejectRole)
        message.setDefaultButton(install_button)
        message.exec()
        clicked = message.clickedButton()
        if clicked == skip_button:
            self.settings.setValue("updates/skipped_tag", update.tag)
            self.settings.sync()
            return
        if clicked == ignore_button:
            return
        if clicked == install_button:
            self.install_update(update)

    def install_update(self, update: UpdateInfo) -> None:
        progress = QProgressDialog("Preparing update...", None, 0, 100, self)
        progress.setWindowTitle("Installing Update")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

        def update_progress(stage: str, current: int, total: int) -> None:
            progress.setLabelText(stage)
            progress.setMaximum(max(1, total))
            progress.setValue(min(current, total))
            QApplication.processEvents()

        try:
            result = install_update(update, progress_callback=update_progress)
        except Exception as exc:
            QMessageBox.warning(self, "Update Failed", str(exc))
            return
        finally:
            progress.close()

        if result in {"restart_required", "launched_installer"}:
            self.mark_pending_release_notes(update)
            current = self.currentWidget()
            if current is not None and hasattr(current, "save"):
                current.save()
            QApplication.quit()
        elif result == "downloaded_dev_mode":
            QMessageBox.information(
                self,
                "Update Downloaded",
                "The update was downloaded, but this development run cannot replace itself. The release page was opened.",
            )

    def mark_pending_release_notes(self, update: UpdateInfo) -> None:
        self.settings.setValue("updates/pending_release_notes_tag", update.tag)
        self.settings.setValue("updates/pending_release_notes_name", update.name or update.tag)
        self.settings.setValue("updates/pending_release_notes_body", update.body)
        self.settings.setValue("updates/pending_release_notes_url", update.html_url)
        write_pending_release_notes(
            {
                "tag": update.tag,
                "name": update.name or update.tag,
                "body": update.body,
                "html_url": update.html_url,
            }
        )
        self.settings.sync()

    def show_project_open_failed(self, project_dir: Path, exc: Exception) -> None:
        from drill_writer.core.project_io import list_project_backups, restore_project_backup

        backups = list_project_backups(project_dir)
        message = QMessageBox(self)
        message.setWindowTitle("Project Needs Recovery")
        message.setIcon(QMessageBox.Icon.Warning)
        message.setText(f"Drill Pirate could not open '{project_dir.name}'.")
        message.setInformativeText(
            f"{exc}\n\n"
            "You can restore the newest automatic backup or export a bug report bundle."
        )
        restore_button = None
        if backups:
            restore_button = message.addButton("Restore Latest Backup", QMessageBox.ButtonRole.AcceptRole)
        bug_button = message.addButton("Export Bug Report", QMessageBox.ButtonRole.ActionRole)
        message.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        clicked = message.clickedButton()
        if restore_button is not None and clicked == restore_button:
            try:
                restore_project_backup(project_dir, backups[0].path)
            except Exception as restore_exc:
                QMessageBox.warning(self, "Restore Failed", str(restore_exc))
                return
            self.open_project(project_dir)
        elif clicked == bug_button:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Bug Report Bundle",
                str(Path.home() / f"{project_dir.name}_bug_report.zip"),
                "Zip (*.zip)",
            )
            if path:
                export_bug_report_bundle(Path(path), project_dir=project_dir, extra={"open_error": str(exc)})

    def show_unexpected_project_error(self, project_dir: Path, exc: Exception) -> None:
        message = QMessageBox(self)
        message.setWindowTitle("Project Open Failed")
        message.setIcon(QMessageBox.Icon.Critical)
        message.setText(f"Drill Pirate hit an unexpected error while opening '{project_dir.name}'.")
        message.setInformativeText(f"{exc}\n\nExport a bug report bundle if this keeps happening.")
        bug_button = message.addButton("Export Bug Report", QMessageBox.ButtonRole.AcceptRole)
        message.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        if message.clickedButton() == bug_button:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Bug Report Bundle",
                str(Path.home() / f"{project_dir.name}_bug_report.zip"),
                "Zip (*.zip)",
            )
            if path:
                export_bug_report_bundle(Path(path), project_dir=project_dir, extra={"open_error": str(exc)})


def main() -> int:
    install_exception_hook()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(app_icon_path())))
    settings = QSettings("OpenAI", "DrillWriter")
    mode = normalize_theme(str(settings.value("appearance/theme", "dark")))
    app.setStyleSheet(theme_stylesheet(mode, settings))
    window = DrillWriterApp()
    window.show()
    return app.exec()
