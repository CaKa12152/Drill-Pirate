from __future__ import annotations

import json
import os
import platform
import sys
import threading
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Any


def app_data_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    base = Path(root) if root else Path.home() / "AppData" / "Local"
    path = base / "Drill Pirate"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pending_release_notes_file() -> Path:
    return app_data_dir() / "pending_release_notes.json"


def log_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
    *,
    context: str = "Unhandled exception",
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    log_path = logs_dir() / f"crash_{timestamp}.log"
    payload = [
        f"{context}",
        f"Timestamp: {timestamp}",
        f"Python: {sys.version}",
        f"Executable: {sys.executable}",
        f"Frozen: {bool(getattr(sys, 'frozen', False))}",
        f"Platform: {platform.platform()}",
        "",
        "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
    ]
    log_path.write_text("\n".join(payload), encoding="utf-8")
    prune_logs()
    return log_path


def prune_logs(max_logs: int = 25) -> None:
    files = sorted(logs_dir().glob("crash_*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files[max_logs:]:
        try:
            path.unlink()
        except OSError:
            pass


def install_exception_hook() -> None:
    previous_hook = sys.excepthook

    def handle_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            previous_hook(exc_type, exc_value, exc_traceback)
            return
        log_path = log_exception(exc_type, exc_value, exc_traceback)
        show_crash_dialog(log_path, str(exc_value))

    sys.excepthook = handle_exception

    if hasattr(threading, "excepthook"):
        previous_thread_hook = threading.excepthook

        def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
            log_path = log_exception(
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
                context=f"Unhandled thread exception in {args.thread.name if args.thread else 'thread'}",
            )
            show_crash_dialog(log_path, str(args.exc_value))
            previous_thread_hook(args)

        threading.excepthook = handle_thread_exception


def show_crash_dialog(log_path: Path, message: str) -> None:
    try:
        from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    except Exception:
        return

    app = QApplication.instance()
    if app is None:
        return

    dialog = QMessageBox()
    dialog.setWindowTitle("Drill Pirate Error")
    dialog.setIcon(QMessageBox.Icon.Critical)
    dialog.setText("Drill Pirate hit an unexpected error.")
    dialog.setInformativeText(
        f"{message}\n\nA crash log was saved to:\n{log_path}\n\n"
        "You can export a bug report bundle now."
    )
    export_button = dialog.addButton("Export Bug Report", QMessageBox.ButtonRole.AcceptRole)
    dialog.addButton("Close", QMessageBox.ButtonRole.RejectRole)
    dialog.exec()
    if dialog.clickedButton() == export_button:
        path, _ = QFileDialog.getSaveFileName(
            None,
            "Export Bug Report Bundle",
            str(Path.home() / "drill_pirate_bug_report.zip"),
            "Zip (*.zip)",
        )
        if path:
            export_bug_report_bundle(Path(path))


def export_bug_report_bundle(
    output_path: Path,
    *,
    project_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    settings = settings_snapshot()
    plugins = plugin_snapshot()
    diagnostics = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "frozen": bool(getattr(sys, "frozen", False)),
        "project_dir": str(project_dir) if project_dir else "",
        "settings_keys": sorted(settings),
        "plugins": {
            "root": plugins.get("root", ""),
            "active": plugins.get("active", {}),
            "manifest_count": len(plugins.get("manifests", [])),
        },
        "extra": extra or {},
    }
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.json", json.dumps(diagnostics, indent=2))
        archive.writestr("settings.json", json.dumps(settings, indent=2, sort_keys=True))
        archive.writestr("plugins.json", json.dumps(plugins, indent=2, sort_keys=True))
        for log_path in sorted(logs_dir().glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)[:10]:
            archive.write(log_path, f"logs/{log_path.name}")
        plugin_error_log = Path(str(plugins.get("root", ""))) / "plugin_errors.log" if plugins.get("root") else None
        if plugin_error_log and plugin_error_log.exists():
            archive.write(plugin_error_log, f"plugins/{plugin_error_log.name}")
        if project_dir and project_dir.exists():
            add_project_to_archive(archive, project_dir)
    return output_path


def settings_snapshot() -> dict[str, Any]:
    try:
        from PySide6.QtCore import QSettings
    except Exception:
        return {}
    settings = QSettings("OpenAI", "DrillWriter")
    snapshot: dict[str, Any] = {}
    for key in settings.allKeys():
        value = settings.value(key)
        if any(secret in key.lower() for secret in ("token", "password", "secret", "key")):
            snapshot[key] = "<redacted>"
        else:
            snapshot[key] = str(value)
    return snapshot


def plugin_snapshot() -> dict[str, Any]:
    try:
        from drill_writer.core.plugin_manager import PLUGIN_STATE_FILE, plugin_library_dir
    except Exception:
        return {}
    root = plugin_library_dir()
    state_path = root / PLUGIN_STATE_FILE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except Exception:
        state = {"error": "Could not read plugin state."}
    manifests: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob("*/plugin.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            payload = {"id": manifest_path.parent.name, "error": str(exc)}
        payload["folder"] = manifest_path.parent.name
        manifests.append(payload)
    return {
        "root": str(root),
        "state": state,
        "active": state.get("active", {}) if isinstance(state, dict) else {},
        "trusted": state.get("trusted", {}) if isinstance(state, dict) else {},
        "manifests": manifests,
    }


def add_project_to_archive(archive: zipfile.ZipFile, project_dir: Path) -> None:
    skip_dirs = {".drill_pirate_backups", "__pycache__"}
    for path in project_dir.rglob("*"):
        if any(part in skip_dirs for part in path.relative_to(project_dir).parts):
            continue
        if path.is_file():
            archive.write(path, f"project/{path.relative_to(project_dir).as_posix()}")


def write_pending_release_notes(payload: dict[str, Any]) -> None:
    pending_release_notes_file().write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_pending_release_notes() -> dict[str, Any]:
    path = pending_release_notes_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def clear_pending_release_notes_file() -> None:
    try:
        pending_release_notes_file().unlink()
    except FileNotFoundError:
        pass
