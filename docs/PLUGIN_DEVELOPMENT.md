# Drill Pirate Plugin Development

Drill Pirate plugins are folders inside:

```text
Documents\Drill Pirate Plugins
```

Each plugin folder needs a `plugin.json` manifest and a Python entry file, usually `plugin.py`.

## Runtime In The EXE

Users do **not** need to install Python. The Windows EXE is a PyInstaller app, so it already includes the Python runtime Drill Pirate uses internally. Plugin `.py` files are loaded by that embedded runtime.

What works well:

- Normal plugin `.py` files.
- Pure-Python helper files placed inside the same plugin folder.
- Imports from Drill Pirate itself, PySide6, and libraries bundled into the app.

What is limited:

- Third-party packages that are not bundled with Drill Pirate.
- Native binary dependencies such as `.pyd` / `.dll` packages unless they are specifically packaged and compatible with the EXE.
- Plugins that expect a system-wide `python.exe`.

If a plugin needs helper code, put it beside `plugin.py` and import it normally:

```text
Documents\Drill Pirate Plugins\
  my_plugin\
    plugin.json
    plugin.py
    geometry_helpers.py
```

```python
from geometry_helpers import make_heart_points
```

## Security Model

Plugins run as normal Python code inside Drill Pirate. That means a plugin can modify the UI, projects, files, colors, menus, tools, and application behavior. Only install plugins from people you trust.

## Folder Layout

```text
Documents\Drill Pirate Plugins\
  my_plugin\
    plugin.json
    plugin.py
```

## Manifest

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "What the plugin does.",
  "entry": "plugin.py"
}
```

The `id` should be unique and use letters, numbers, and underscores.

## Hook Functions

Define any of these functions in `plugin.py`:

```python
def activate(context):
    pass

def deactivate(context):
    pass

def apply_startup(context):
    pass

def apply_main_window(context):
    pass
```

- `activate(context)` runs when the plugin is enabled or reloaded.
- `deactivate(context)` runs when the plugin is disabled or plugins reload.
- `apply_startup(context)` runs for the home screen.
- `apply_main_window(context)` runs for each opened project window.

## Context Object

The hook receives a `context` object with:

- `context.app`: the `QApplication`.
- `context.startup_page`: the home screen widget, when available.
- `context.main_window`: the active project window, when available.
- `context.plugin_dir`: the plugin folder path.
- `context.manifest`: plugin metadata.
- `context.append_stylesheet(css)`: appends global Qt stylesheet CSS.
- `context.register_form_tool(...)`: adds a custom form tool button and menu action.
- `context.add_menu_action(...)`: adds a menu action without manually wiring Qt menus.
- `context.add_panel_button(...)`: adds a simple button to the left plugin actions panel.

Because these are real Qt/Python objects, a plugin can customize almost anything in the software.

## Simple Custom Form Tool

This is the recommended way to add formation tools. Drill Pirate handles the button, menu action, selection lookup, undo, and path/keyframe cleanup.

```python
from drill_writer.core.tools import positions_along_path


def apply_main_window(context):
    def triangle(tool_context):
        count = len(tool_context.dot_ids)
        center_x, center_y = tool_context.center
        width = tool_context.bounds_width or 24
        height = tool_context.bounds_height or 18
        path = [
            (center_x, center_y + height / 2),
            (center_x + width / 2, center_y - height / 2),
            (center_x - width / 2, center_y - height / 2),
            (center_x, center_y + height / 2),
        ]
        return positions_along_path(path, count)

    context.register_form_tool(
        "Triangle Form",
        triangle,
        shortcut="Ctrl+Alt+T",
        min_selected=3,
        tooltip="Places selected marchers on a triangle.",
    )
```

The form tool callback receives a `tool_context` with:

- `tool_context.window`: the active project window.
- `tool_context.project`: the full project data model.
- `tool_context.set_index`: the active set index.
- `tool_context.dot_ids`: selected marcher IDs in formation order.
- `tool_context.positions`: selected positions in the same order.
- `tool_context.center`: selection center as `(x, y)`.
- `tool_context.bounds_width` / `bounds_height`: selection bounds in yards.

Return either:

- A list of `(x, y)` positions matching `tool_context.dot_ids`, or
- A dict like `{"dot001": (x, y), "dot002": (x, y)}`.

## Simple UI Helpers

```python
def apply_main_window(context):
    context.add_menu_action(
        "Plugin Tools",
        "Say Hello",
        lambda: context.main_window.statusBar().showMessage("Hello from plugin", 3000),
        shortcut="Ctrl+Alt+H",
    )

    context.add_panel_button(
        "Analyze From Plugin",
        lambda: context.main_window.analyze_paths(),
        tooltip="Runs the built-in path analyzer.",
    )
```

## Example: Change Colors

```python
def activate(context):
    context.append_stylesheet("""
    #HomePage {
        background: #080b10;
    }
    #ProjectCard {
        border-color: #00d4ff;
    }
    QPushButton {
        border-radius: 10px;
    }
    """)
```

## Default Plugin

Drill Pirate creates default plugins the first time the plugin folder is scanned:

- `pirate_gold_theme`: demonstrates stylesheet customization.
- `starter_form_tools`: demonstrates `context.register_form_tool(...)` with a Diamond form tool.
