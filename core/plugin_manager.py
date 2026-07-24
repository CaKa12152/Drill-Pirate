from __future__ import annotations

import importlib.util
import json
import re
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from PySide6.QtWidgets import QApplication, QWidget

from drill_writer.core.updater import CURRENT_VERSION, version_tuple


PLUGIN_ROOT = Path.home() / "Documents" / "Drill Pirate Plugins"
PLUGIN_STATE_FILE = "plugins_state.json"
PLUGIN_ERROR_LOG = "plugin_errors.log"
PLUGIN_API_VERSION = "1.0"
PLUGIN_API_MAJOR = version_tuple(PLUGIN_API_VERSION)[0]


DEFAULT_PLUGINS = [
    (
        {
            "id": "pirate_gold_theme",
            "name": "Pirate Gold Theme",
            "version": "1.0.0",
            "author": "Drill Pirate",
            "description": "Adds a warmer gold-accent UI theme and demonstrates stylesheet customization.",
            "entry": "plugin.py",
            "api_version": PLUGIN_API_VERSION,
            "min_app_version": CURRENT_VERSION,
            "permissions": ["ui", "theme"],
        },
        '''from __future__ import annotations


PLUGIN_STYLESHEET = """
QWidget {
    selection-background-color: #d6a93a;
}
#HomePage {
    background: #101217;
}
#HomeHero, #PluginCard, #ProjectCard {
    border-color: rgba(214, 169, 58, 0.42);
}
#HomeTitle {
    color: #ffd76f;
}
QPushButton:checked {
    background: #8b6a21;
    border-color: #ffd76f;
}
"""


def activate(context):
    context.append_stylesheet(PLUGIN_STYLESHEET)


def apply_startup(context):
    startup = context.startup_page
    if startup is not None and hasattr(startup, "set_plugin_banner"):
        startup.set_plugin_banner("Pirate Gold Theme active")
''',
    ),
    (
        {
            "id": "starter_form_tools",
            "name": "Starter Form Tools",
            "version": "1.0.0",
            "author": "Drill Pirate",
            "description": "Adds an example Diamond form tool using the public plugin form-tool API.",
            "entry": "plugin.py",
            "api_version": PLUGIN_API_VERSION,
            "min_app_version": CURRENT_VERSION,
            "permissions": ["ui", "project_read", "project_write"],
        },
        '''from __future__ import annotations

from math import cos, radians, sin

from drill_writer.core.tools import positions_along_path


def rotate_point(point, center, degrees):
    angle = radians(degrees)
    offset_x = point[0] - center[0]
    offset_y = point[1] - center[1]
    return (
        center[0] + offset_x * cos(angle) - offset_y * sin(angle),
        center[1] + offset_x * sin(angle) + offset_y * cos(angle),
    )


def apply_main_window(context):
    def diamond(tool_context):
        count = len(tool_context.dot_ids)
        if count < 3:
            return None
        center_x, center_y = tool_context.center
        settings = tool_context.settings
        width = float(settings.get("width", tool_context.bounds_width or 24))
        height = float(settings.get("height", tool_context.bounds_height or 18))
        rotation = float(settings.get("rotation", 0))
        center = (center_x, center_y)
        path = [
            (center_x, center_y + height / 2),
            (center_x + width / 2, center_y),
            (center_x, center_y - height / 2),
            (center_x - width / 2, center_y),
            (center_x, center_y + height / 2),
        ]
        if rotation:
            path = [rotate_point(point, center, rotation) for point in path]
        return positions_along_path(path, count)

    context.register_form_tool(
        "Diamond Form",
        diamond,
        shortcut="Ctrl+Alt+D",
        min_selected=3,
        tooltip="Plugin example: reshape the selected marchers into a diamond.",
        settings=[
            {
                "name": "width",
                "label": "Width",
                "type": "float",
                "default": 28,
                "min": 2,
                "max": 120,
                "step": 1,
                "suffix": " yd",
                "handle": "width",
            },
            {
                "name": "height",
                "label": "Height",
                "type": "float",
                "default": 18,
                "min": 2,
                "max": 54,
                "step": 1,
                "suffix": " yd",
                "handle": "height",
            },
            {
                "name": "rotation",
                "label": "Rotation",
                "type": "float",
                "default": 0,
                "min": -180,
                "max": 180,
                "step": 5,
                "suffix": " deg",
            },
        ],
    )
''',
    ),
    (
        {
            "id": "export_helper_example",
            "name": "Export Helper Example",
            "version": "1.0.0",
            "author": "Drill Pirate",
            "description": "Adds a project-summary text export command to demonstrate export helper plugins.",
            "entry": "plugin.py",
            "api_version": PLUGIN_API_VERSION,
            "min_app_version": CURRENT_VERSION,
            "permissions": ["ui", "project_read", "file_write"],
        },
        '''from __future__ import annotations


def apply_main_window(context):
    def export_summary():
        window = context.main_window
        project = window.project
        output = window.project_dir / "plugin_project_summary.txt"
        lines = [
            f"Show: {project.metadata.show_title}",
            f"Sets: {len(project.sets)}",
            f"Marchers: {len(project.dots)}",
            f"Props: {len(project.props)}",
        ]
        output.write_text("\\n".join(lines), encoding="utf-8")
        window.statusBar().showMessage(f"Plugin summary exported: {output.name}", 3500)
        context.log_info("Exported project summary", str(output))

    context.add_menu_action(
        "Plugin Tools",
        "Export Plugin Project Summary",
        export_summary,
        shortcut="Ctrl+Alt+E",
    )
''',
    ),
    (
        {
            "id": "rehearsal_helper_example",
            "name": "Rehearsal Helper Example",
            "version": "1.0.0",
            "author": "Drill Pirate",
            "description": "Adds quick rehearsal controls for looping and slow playback.",
            "entry": "plugin.py",
            "api_version": PLUGIN_API_VERSION,
            "min_app_version": CURRENT_VERSION,
            "permissions": ["ui", "project_read"],
        },
        '''from __future__ import annotations


def apply_main_window(context):
    def loop_current_set():
        window = context.main_window
        if hasattr(window, "loop_current_set"):
            window.loop_current_set.setChecked(True)
        window.statusBar().showMessage("Plugin rehearsal mode: loop current set enabled", 3500)

    def half_speed():
        window = context.main_window
        if hasattr(window, "playback_rate"):
            index = window.playback_rate.findText("0.5x")
            if index >= 0:
                window.playback_rate.setCurrentIndex(index)
        window.statusBar().showMessage("Plugin rehearsal mode: half-speed playback", 3500)

    context.add_panel_button("Loop Current Set", loop_current_set, "Plugin example rehearsal helper.")
    context.add_panel_button("Half-Speed Playback", half_speed, "Plugin example rehearsal helper.")
''',
    ),
    (
        {
            "id": "panel_extension_example",
            "name": "Panel Extension Example",
            "version": "1.0.0",
            "author": "Drill Pirate",
            "description": "Adds a panel action that reports the current selection.",
            "entry": "plugin.py",
            "api_version": PLUGIN_API_VERSION,
            "min_app_version": CURRENT_VERSION,
            "permissions": ["ui", "project_read"],
        },
        '''from __future__ import annotations


def apply_main_window(context):
    def describe_selection():
        window = context.main_window
        selected = window.field.selected_dot_ids()
        if not selected:
            window.statusBar().showMessage("Plugin panel: no marchers selected", 3500)
            return
        window.statusBar().showMessage(
            f"Plugin panel: {len(selected)} selected - {', '.join(selected[:8])}",
            4500,
        )

    context.add_panel_button(
        "Describe Selection",
        describe_selection,
        "Plugin example panel extension.",
    )
''',
    ),
]


@dataclass(slots=True)
class PluginManifest:
    id: str
    name: str
    version: str
    author: str
    description: str
    entry: str
    api_version: str
    min_app_version: str
    permissions: list[str]
    path: Path

    @classmethod
    def from_path(cls, path: Path) -> "PluginManifest | None":
        manifest_path = path / "plugin.json"
        if not manifest_path.exists():
            return None
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        plugin_id = safe_plugin_id(str(payload.get("id") or path.name))
        return cls(
            id=plugin_id,
            name=str(payload.get("name") or plugin_id.replace("_", " ").title()),
            version=str(payload.get("version") or "0.0.0"),
            author=str(payload.get("author") or "Unknown"),
            description=str(payload.get("description") or ""),
            entry=str(payload.get("entry") or "plugin.py"),
            api_version=str(payload.get("api_version") or PLUGIN_API_VERSION),
            min_app_version=str(payload.get("min_app_version") or payload.get("minimum_app_version") or ""),
            permissions=[
                safe_permission_id(str(permission))
                for permission in payload.get("permissions", ["ui", "project_read"])
                if str(permission).strip()
            ],
            path=path,
        )


@dataclass(slots=True)
class PluginDiagnostic:
    created_at: str
    plugin_id: str
    plugin_name: str
    level: str
    message: str
    detail: str = ""

    def to_text(self) -> str:
        detail = f"\n{self.detail}" if self.detail else ""
        return f"[{self.created_at}] {self.level.upper()} {self.plugin_name} ({self.plugin_id}): {self.message}{detail}"


@dataclass(slots=True)
class PluginContext:
    manager: "PluginManager"
    manifest: PluginManifest
    plugin_dir: Path
    app: QApplication | None
    startup_page: QWidget | None = None
    main_window: QWidget | None = None

    @property
    def api_version(self) -> str:
        return PLUGIN_API_VERSION

    @property
    def app_version(self) -> str:
        return CURRENT_VERSION

    @property
    def permissions(self) -> list[str]:
        return list(self.manifest.permissions)

    def log_info(self, message: str, detail: str = "") -> None:
        self.manager.record_diagnostic(self.manifest, "info", message, detail)

    def log_warning(self, message: str, detail: str = "") -> None:
        self.manager.record_diagnostic(self.manifest, "warning", message, detail)

    def log_error(self, message: str, detail: str = "") -> None:
        self.manager.record_diagnostic(self.manifest, "error", message, detail)

    def append_stylesheet(self, stylesheet: str) -> None:
        self.manager.append_stylesheet(stylesheet)

    def register_form_tool(
        self,
        name: str,
        callback: Callable[[Any], Any],
        shortcut: str | None = None,
        min_selected: int = 2,
        tooltip: str = "",
        settings: list[dict[str, Any]] | None = None,
    ) -> str:
        if self.main_window is None:
            return ""
        register = getattr(self.main_window, "register_plugin_form_tool", None)
        if not callable(register):
            return ""
        safe_callback = self.manager.wrap_plugin_callback(
            self.manifest,
            f"form tool '{name}'",
            callback,
        )
        return register(
            plugin_id=self.manifest.id,
            name=name,
            callback=safe_callback,
            shortcut=shortcut,
            min_selected=min_selected,
            tooltip=tooltip,
            settings=settings,
        )

    def add_menu_action(
        self,
        menu: str,
        text: str,
        callback: Callable[[], Any],
        shortcut: str | None = None,
    ) -> None:
        if self.main_window is None:
            return
        add_action = getattr(self.main_window, "add_plugin_menu_action", None)
        if callable(add_action):
            safe_callback = self.manager.wrap_plugin_callback(
                self.manifest,
                f"menu action '{text}'",
                callback,
            )
            add_action(self.manifest.id, menu, text, safe_callback, shortcut)

    def add_panel_button(
        self,
        text: str,
        callback: Callable[[], Any],
        tooltip: str = "",
    ) -> None:
        if self.main_window is None:
            return
        add_button = getattr(self.main_window, "add_plugin_panel_button", None)
        if callable(add_button):
            safe_callback = self.manager.wrap_plugin_callback(
                self.manifest,
                f"panel button '{text}'",
                callback,
            )
            add_button(self.manifest.id, text, safe_callback, tooltip)


class PluginManager:
    def __init__(self, base_stylesheet: str) -> None:
        self.base_stylesheet = base_stylesheet
        self.plugin_root = plugin_library_dir()
        self.state = load_plugin_state(self.plugin_root)
        self.diagnostics: list[PluginDiagnostic] = []
        self.app: QApplication | None = None
        self.startup_page: QWidget | None = None
        self.main_windows: list[QWidget] = []
        self.loaded_modules: dict[str, ModuleType] = {}
        self.active_plugin_paths: set[str] = set()
        self.ensure_default_plugins()

    def ensure_default_plugins(self) -> None:
        for manifest, code in DEFAULT_PLUGINS:
            plugin_dir = self.plugin_root / str(manifest["id"])
            plugin_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = plugin_dir / "plugin.json"
            entry_path = plugin_dir / str(manifest["entry"])
            if not manifest_path.exists():
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            else:
                try:
                    existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    existing_manifest = {}
                changed = False
                for key in ("api_version", "min_app_version", "permissions"):
                    if key not in existing_manifest and key in manifest:
                        existing_manifest[key] = manifest[key]
                        changed = True
                if changed:
                    manifest_path.write_text(json.dumps(existing_manifest, indent=2), encoding="utf-8")
            should_write_entry = not entry_path.exists()
            if entry_path.exists() and str(manifest["id"]) == "starter_form_tools":
                existing = entry_path.read_text(encoding="utf-8", errors="ignore")
                should_write_entry = (
                    "Plugin example: reshape the selected marchers into a diamond." in existing
                    or "settings=[" not in existing
                )
            if should_write_entry:
                entry_path.write_text(code, encoding="utf-8")

    def register_app(self, app: QApplication, startup_page: QWidget) -> None:
        self.app = app
        self.startup_page = startup_page
        self.reload_active_plugins()

    def register_main_window(self, window: QWidget) -> None:
        setattr(window, "plugin_manager", self)
        self.main_windows.append(window)
        self.apply_plugins_to_main_window(window)

    def unregister_main_window(self, window: QWidget) -> None:
        self.main_windows = [item for item in self.main_windows if item is not window]

    def discover(self) -> list[PluginManifest]:
        self.ensure_default_plugins()
        manifests: list[PluginManifest] = []
        for path in sorted(self.plugin_root.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_dir():
                continue
            manifest = PluginManifest.from_path(path)
            if manifest:
                manifests.append(manifest)
        return manifests

    def is_active(self, plugin_id: str) -> bool:
        return bool(self.state.get("active", {}).get(plugin_id, False))

    def manifest_for_id(self, plugin_id: str) -> PluginManifest | None:
        return next((manifest for manifest in self.discover() if manifest.id == plugin_id), None)

    def trust_key(self, manifest: PluginManifest) -> str:
        return f"{manifest.id}:{manifest.version}:{manifest.api_version}"

    def is_trusted(self, manifest: PluginManifest) -> bool:
        return bool(self.state.get("trusted", {}).get(self.trust_key(manifest), False))

    def trust_plugin(self, manifest: PluginManifest) -> None:
        self.state.setdefault("trusted", {})[self.trust_key(manifest)] = True
        save_plugin_state(self.plugin_root, self.state)

    def set_active(self, plugin_id: str, active: bool) -> None:
        self.state.setdefault("active", {})[plugin_id] = active
        save_plugin_state(self.plugin_root, self.state)
        self.reload_active_plugins()

    def compatibility_warnings(self, manifest: PluginManifest) -> list[str]:
        warnings: list[str] = []
        plugin_api = version_tuple(manifest.api_version)
        if plugin_api[0] > PLUGIN_API_MAJOR:
            warnings.append(
                f"Requires plugin API {manifest.api_version}; this app supports API {PLUGIN_API_VERSION}."
            )
        elif plugin_api[0] < PLUGIN_API_MAJOR:
            warnings.append(
                f"Uses older plugin API {manifest.api_version}; this app supports API {PLUGIN_API_VERSION}."
            )
        if manifest.min_app_version and version_tuple(manifest.min_app_version) > version_tuple(CURRENT_VERSION):
            warnings.append(f"Requires Drill Pirate {manifest.min_app_version} or newer.")
        entry_path = manifest.path / manifest.entry
        if not entry_path.exists():
            warnings.append(f"Missing entry file: {manifest.entry}.")
        return warnings

    def is_compatible(self, manifest: PluginManifest) -> bool:
        plugin_api = version_tuple(manifest.api_version)
        if plugin_api[0] > PLUGIN_API_MAJOR:
            return False
        if manifest.min_app_version and version_tuple(manifest.min_app_version) > version_tuple(CURRENT_VERSION):
            return False
        return (manifest.path / manifest.entry).exists()

    def permission_summary(self, manifest: PluginManifest) -> str:
        labels = {
            "ui": "change the UI",
            "theme": "change app styling",
            "project_read": "read the open project",
            "project_write": "modify the open project",
            "file_read": "read files from disk",
            "file_write": "write files to disk",
            "network": "use network access",
            "audio": "control audio/playback",
        }
        if not manifest.permissions:
            return "No permissions declared."
        return "\n".join(f"- {labels.get(permission, permission)}" for permission in manifest.permissions)

    def record_diagnostic(
        self,
        manifest: PluginManifest,
        level: str,
        message: str,
        detail: str = "",
    ) -> None:
        diagnostic = PluginDiagnostic(
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            plugin_id=manifest.id,
            plugin_name=manifest.name,
            level=level,
            message=message,
            detail=detail,
        )
        self.diagnostics.append(diagnostic)
        if len(self.diagnostics) > 300:
            self.diagnostics = self.diagnostics[-300:]
        try:
            with (self.plugin_root / PLUGIN_ERROR_LOG).open("a", encoding="utf-8") as file:
                file.write(diagnostic.to_text() + "\n\n")
        except OSError:
            pass

    def diagnostics_text(self) -> str:
        if not self.diagnostics:
            log_path = self.plugin_root / PLUGIN_ERROR_LOG
            if log_path.exists():
                return log_path.read_text(encoding="utf-8", errors="replace")[-20000:]
            return "No plugin diagnostics recorded."
        return "\n\n".join(diagnostic.to_text() for diagnostic in self.diagnostics)

    def clear_diagnostics(self) -> None:
        self.diagnostics.clear()
        log_path = self.plugin_root / PLUGIN_ERROR_LOG
        try:
            if log_path.exists():
                log_path.unlink()
        except OSError:
            pass

    def wrap_plugin_callback(
        self,
        manifest: PluginManifest,
        label: str,
        callback: Callable[..., Any],
    ) -> Callable[..., Any]:
        def wrapped(*args, **kwargs):
            try:
                return callback(*args, **kwargs)
            except Exception:
                self.record_diagnostic(
                    manifest,
                    "error",
                    f"Plugin callback failed: {label}",
                    traceback.format_exc(),
                )
                return None

        return wrapped

    def append_stylesheet(self, stylesheet: str) -> None:
        if self.app is not None:
            self.app.setStyleSheet(self.app.styleSheet() + "\n" + stylesheet)

    def reload_active_plugins(self) -> None:
        for manifest_id, module in list(self.loaded_modules.items()):
            manifest = next((item for item in self.discover() if item.id == manifest_id), None)
            if manifest:
                self.call_hook(module, "deactivate", self.context_for(manifest))
        self.loaded_modules.clear()
        self.remove_plugin_paths()
        for window in list(self.main_windows):
            remover = getattr(window, "remove_plugin_contributions", None)
            if callable(remover):
                remover()
        if self.app is not None:
            self.app.setStyleSheet(self.base_stylesheet)
        if self.startup_page is not None and hasattr(self.startup_page, "set_plugin_banner"):
            self.startup_page.set_plugin_banner("")

        for manifest in self.discover():
            if not self.is_active(manifest.id):
                continue
            for warning in self.compatibility_warnings(manifest):
                self.record_diagnostic(manifest, "warning", warning)
            if not self.is_compatible(manifest):
                self.record_diagnostic(
                    manifest,
                    "error",
                    "Plugin skipped because it is not compatible with this Drill Pirate build.",
                )
                continue
            module = self.load_module(manifest)
            if module is None:
                continue
            self.loaded_modules[manifest.id] = module
            self.call_hook(module, "activate", self.context_for(manifest))
            if self.startup_page is not None:
                self.call_hook(module, "apply_startup", self.context_for(manifest, startup_page=self.startup_page))
            for window in list(self.main_windows):
                self.call_hook(module, "apply_main_window", self.context_for(manifest, main_window=window))

    def apply_plugins_to_main_window(self, window: QWidget) -> None:
        for manifest in self.discover():
            if not self.is_active(manifest.id):
                continue
            for warning in self.compatibility_warnings(manifest):
                self.record_diagnostic(manifest, "warning", warning)
            if not self.is_compatible(manifest):
                self.record_diagnostic(
                    manifest,
                    "error",
                    "Plugin skipped because it is not compatible with this Drill Pirate build.",
                )
                continue
            module = self.loaded_modules.get(manifest.id) or self.load_module(manifest)
            if module is None:
                continue
            self.loaded_modules[manifest.id] = module
            self.call_hook(module, "apply_main_window", self.context_for(manifest, main_window=window))

    def context_for(
        self,
        manifest: PluginManifest,
        startup_page: QWidget | None = None,
        main_window: QWidget | None = None,
    ) -> PluginContext:
        return PluginContext(
            manager=self,
            manifest=manifest,
            plugin_dir=manifest.path,
            app=self.app,
            startup_page=startup_page or self.startup_page,
            main_window=main_window,
        )

    def load_module(self, manifest: PluginManifest) -> ModuleType | None:
        entry_path = manifest.path / manifest.entry
        if not entry_path.exists():
            return None
        module_name = f"drill_pirate_plugin_{manifest.id}"
        sys.modules.pop(module_name, None)
        self.add_plugin_path(manifest.path)
        spec = importlib.util.spec_from_file_location(module_name, entry_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            self.record_diagnostic(
                manifest,
                "error",
                "Plugin load failed",
                traceback.format_exc(),
            )
            sys.modules.pop(module_name, None)
            return None
        return module

    def add_plugin_path(self, path: Path) -> None:
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)
        self.active_plugin_paths.add(path_text)

    def remove_plugin_paths(self) -> None:
        for path_text in list(self.active_plugin_paths):
            while path_text in sys.path:
                sys.path.remove(path_text)
        self.active_plugin_paths.clear()

    def call_hook(self, module: ModuleType, hook_name: str, context: PluginContext) -> None:
        hook = getattr(module, hook_name, None)
        if not callable(hook):
            return
        try:
            hook(context)
        except Exception:
            self.record_diagnostic(
                context.manifest,
                "error",
                f"Plugin hook failed: {hook_name}",
                traceback.format_exc(),
            )


def plugin_library_dir() -> Path:
    PLUGIN_ROOT.mkdir(parents=True, exist_ok=True)
    return PLUGIN_ROOT


def load_plugin_state(plugin_root: Path) -> dict[str, Any]:
    state_path = plugin_root / PLUGIN_STATE_FILE
    if not state_path.exists():
        return {"active": {}, "trusted": {}}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"active": {}, "trusted": {}}
    if not isinstance(payload, dict):
        return {"active": {}, "trusted": {}}
    if not isinstance(payload.get("active"), dict):
        payload["active"] = {}
    if not isinstance(payload.get("trusted"), dict):
        payload["trusted"] = {}
    return payload


def save_plugin_state(plugin_root: Path, state: dict[str, Any]) -> None:
    plugin_root.mkdir(parents=True, exist_ok=True)
    (plugin_root / PLUGIN_STATE_FILE).write_text(json.dumps(state, indent=2), encoding="utf-8")


def safe_plugin_id(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    return safe or "unnamed_plugin"


def safe_permission_id(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    return safe or "unknown"
