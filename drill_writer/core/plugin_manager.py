from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from PySide6.QtWidgets import QApplication, QWidget


PLUGIN_ROOT = Path.home() / "Documents" / "Drill Pirate Plugins"
PLUGIN_STATE_FILE = "plugins_state.json"


DEFAULT_PLUGINS = [
    (
        {
            "id": "pirate_gold_theme",
            "name": "Pirate Gold Theme",
            "version": "1.0.0",
            "author": "Drill Pirate",
            "description": "Adds a warmer gold-accent UI theme and demonstrates stylesheet customization.",
            "entry": "plugin.py",
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
        },
        '''from __future__ import annotations

from drill_writer.core.tools import positions_along_path


def apply_main_window(context):
    def diamond(tool_context):
        count = len(tool_context.dot_ids)
        if count < 3:
            return None
        center_x, center_y = tool_context.center
        width = tool_context.bounds_width or 24
        height = tool_context.bounds_height or 18
        path = [
            (center_x, center_y + height / 2),
            (center_x + width / 2, center_y),
            (center_x, center_y - height / 2),
            (center_x - width / 2, center_y),
            (center_x, center_y + height / 2),
        ]
        return positions_along_path(path, count)

    context.register_form_tool(
        "Diamond Form",
        diamond,
        shortcut="Ctrl+Alt+D",
        min_selected=3,
        tooltip="Plugin example: reshape the selected marchers into a diamond.",
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
            path=path,
        )


@dataclass(slots=True)
class PluginContext:
    manager: "PluginManager"
    manifest: PluginManifest
    plugin_dir: Path
    app: QApplication | None
    startup_page: QWidget | None = None
    main_window: QWidget | None = None

    def append_stylesheet(self, stylesheet: str) -> None:
        self.manager.append_stylesheet(stylesheet)

    def register_form_tool(
        self,
        name: str,
        callback: Callable[[Any], Any],
        shortcut: str | None = None,
        min_selected: int = 2,
        tooltip: str = "",
    ) -> str:
        if self.main_window is None:
            return ""
        register = getattr(self.main_window, "register_plugin_form_tool", None)
        if not callable(register):
            return ""
        return register(
            plugin_id=self.manifest.id,
            name=name,
            callback=callback,
            shortcut=shortcut,
            min_selected=min_selected,
            tooltip=tooltip,
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
            add_action(self.manifest.id, menu, text, callback, shortcut)

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
            add_button(self.manifest.id, text, callback, tooltip)


class PluginManager:
    def __init__(self, base_stylesheet: str) -> None:
        self.base_stylesheet = base_stylesheet
        self.plugin_root = plugin_library_dir()
        self.state = load_plugin_state(self.plugin_root)
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
            if not entry_path.exists():
                entry_path.write_text(code, encoding="utf-8")

    def register_app(self, app: QApplication, startup_page: QWidget) -> None:
        self.app = app
        self.startup_page = startup_page
        self.reload_active_plugins()

    def register_main_window(self, window: QWidget) -> None:
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

    def set_active(self, plugin_id: str, active: bool) -> None:
        self.state.setdefault("active", {})[plugin_id] = active
        save_plugin_state(self.plugin_root, self.state)
        self.reload_active_plugins()

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
        except Exception as exc:
            print(f"Plugin load failed for {manifest.name}: {exc}")
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
        except Exception as exc:
            print(f"Plugin hook {hook_name} failed for {context.manifest.name}: {exc}")


def plugin_library_dir() -> Path:
    PLUGIN_ROOT.mkdir(parents=True, exist_ok=True)
    return PLUGIN_ROOT


def load_plugin_state(plugin_root: Path) -> dict[str, Any]:
    state_path = plugin_root / PLUGIN_STATE_FILE
    if not state_path.exists():
        return {"active": {}}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"active": {}}
    if not isinstance(payload.get("active"), dict):
        payload["active"] = {}
    return payload


def save_plugin_state(plugin_root: Path, state: dict[str, Any]) -> None:
    plugin_root.mkdir(parents=True, exist_ok=True)
    (plugin_root / PLUGIN_STATE_FILE).write_text(json.dumps(state, indent=2), encoding="utf-8")


def safe_plugin_id(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    return safe or "unnamed_plugin"
