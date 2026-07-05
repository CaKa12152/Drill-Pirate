# Plugin Development

Drill Pirate plugins are folders that can change the home screen, project windows, UI styling, commands, and formation tools.

Plugins live in:

```text
Documents\Drill Pirate Plugins
```

Each plugin folder needs:

```text
plugin.json
plugin.py
```

## Important Runtime Detail

Packaged Drill Pirate builds already include a Python runtime through PyInstaller. Users do not need to install Python to run normal `.py` plugins.

Works well:

- Normal plugin `.py` files.
- Pure-Python helper files placed beside `plugin.py`.
- Imports from Drill Pirate.
- PySide6 UI code already bundled with the app.
- Libraries already packaged with Drill Pirate.

Limited:

- Third-party packages not bundled with Drill Pirate.
- Native `.pyd` or `.dll` dependencies unless explicitly packaged and compatible.
- Plugins that expect a system-wide `python.exe`.

## Security Model

Plugins are trusted Python code. They can modify the UI, projects, files, colors, menus, tools, and app behavior.

Only install plugins from people you trust.

## Folder Layout

```text
Documents\Drill Pirate Plugins\
  my_plugin\
    plugin.json
    plugin.py
    geometry_helpers.py
```

Helper modules can be imported normally:

```python
from geometry_helpers import make_shape_points
```

## Manifest

`plugin.json` describes the plugin.

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

Manifest fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | Yes | Unique ID using letters, numbers, and underscores. |
| `name` | Yes | Display name shown in the Plugins tab. |
| `version` | Recommended | Plugin version. |
| `author` | Recommended | Plugin author. |
| `description` | Recommended | Short explanation. |
| `entry` | Yes | Python file to load, usually `plugin.py`. |

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

| Hook | When It Runs |
| --- | --- |
| `activate(context)` | When the plugin is enabled or reloaded. |
| `deactivate(context)` | When the plugin is disabled or plugins reload. |
| `apply_startup(context)` | When the home screen is available. |
| `apply_main_window(context)` | For each opened project window. |

## Context Object

The hook receives a `context` object.

Common properties:

| Property | Meaning |
| --- | --- |
| `context.app` | Active `QApplication`. |
| `context.startup_page` | Home screen widget when available. |
| `context.main_window` | Current project window when available. |
| `context.plugin_dir` | Plugin folder path. |
| `context.manifest` | Parsed plugin metadata. |

Common helper methods:

| Method | Purpose |
| --- | --- |
| `context.append_stylesheet(css)` | Appends global Qt stylesheet CSS. |
| `context.register_form_tool(...)` | Adds a custom formation tool with preview/settings support. |
| `context.add_menu_action(...)` | Adds a menu action without manually wiring Qt menus. |
| `context.add_panel_button(...)` | Adds a button to the plugin actions panel. |

## Custom Form Tools

This is the recommended API for new form tools.

Drill Pirate handles:

- Tool button.
- Menu action.
- Optional keyboard shortcut.
- Selection lookup.
- Minimum selection count.
- Live preview.
- Adjustable settings UI.
- Draggable width/height/radius handles.
- Undo integration.
- Applying the generated positions.
- Cleaning stale keyframes/path data for changed endpoints.

### Basic Example

```python
from drill_writer.core.tools import positions_along_path


def apply_main_window(context):
    def triangle(tool_context):
        count = len(tool_context.dot_ids)
        center_x, center_y = tool_context.center
        width = float(tool_context.settings.get("width", tool_context.bounds_width or 24))
        height = float(tool_context.settings.get("height", tool_context.bounds_height or 18))
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
        settings=[
            {
                "name": "width",
                "label": "Width",
                "type": "float",
                "default": 24,
                "min": 2,
                "max": 120,
                "suffix": " yd",
                "handle": "width"
            },
            {
                "name": "height",
                "label": "Height",
                "type": "float",
                "default": 18,
                "min": 2,
                "max": 54,
                "suffix": " yd",
                "handle": "height"
            }
        ]
    )
```

## Form Tool Context

The form callback receives `tool_context`.

| Field | Meaning |
| --- | --- |
| `tool_context.window` | Active project window. |
| `tool_context.project` | Full project model. |
| `tool_context.set_index` | Current set index. |
| `tool_context.dot_ids` | Selected marcher IDs in formation order. |
| `tool_context.positions` | Selected positions in the same order. |
| `tool_context.center` | Selection center as `(x, y)`. |
| `tool_context.bounds_width` | Selection bounding-box width in yards. |
| `tool_context.bounds_height` | Selection bounding-box height in yards. |
| `tool_context.settings` | Current user setting values by setting name. |

`tool_context.settings` is the plugin argument system. Add settings to `register_form_tool(...)`, and Drill Pirate shows controls for them in the UI. The callback reads the current user values from `tool_context.settings`.

## Setting Types

Supported setting definitions:

| Type | UI Control |
| --- | --- |
| `float` | Decimal spin box. |
| `int` | Whole-number spin box. |
| `bool` | Checkbox. |
| `choice` | Dropdown with `options`. |
| `text` | Text field. |

Common setting keys:

| Key | Meaning |
| --- | --- |
| `name` | Setting key used in `tool_context.settings`. |
| `label` | User-facing label. |
| `type` | One of `float`, `int`, `bool`, `choice`, `text`. |
| `default` | Default value. |
| `min` | Numeric minimum. |
| `max` | Numeric maximum. |
| `suffix` | Optional display suffix such as `yd` or `deg`. |
| `options` | List of choices for `choice`. |
| `handle` | Optional draggable handle mapping. |

Supported handles:

| Handle | Behavior |
| --- | --- |
| `width` | Adds a draggable width handle on the field. |
| `height` | Adds a draggable height handle on the field. |
| `radius` | Adds a draggable radius handle on the field. |

## Return Values

Return either a list of positions:

```python
return [(0, 0), (5, 0), (10, 0)]
```

Or a dictionary keyed by dot ID:

```python
return {
    "dot001": (0, 0),
    "dot002": (5, 0),
    "dot003": (10, 0)
}
```

The number of returned positions should match the selected dot count.

## Example: Menu Action

```python
def apply_main_window(context):
    context.add_menu_action(
        "Plugin Tools",
        "Analyze From Plugin",
        lambda: context.main_window.analyze_paths(),
        shortcut="Ctrl+Alt+H"
    )
```

## Example: Panel Button

```python
def apply_main_window(context):
    context.add_panel_button(
        "Say Hello",
        lambda: context.main_window.statusBar().showMessage("Hello from plugin", 3000),
        tooltip="Shows a status message."
    )
```

## Example: Change the UI Theme

```python
def activate(context):
    context.append_stylesheet("""
    #HomePage {
        background: #080b10;
    }
    #ProjectCard {
        border-color: #f5b82e;
    }
    QPushButton {
        border-radius: 10px;
    }
    """)
```

## Default Plugins

Drill Pirate creates default plugins the first time the plugin folder is scanned.

| Plugin | Purpose |
| --- | --- |
| `pirate_gold_theme` | Demonstrates stylesheet customization. |
| `starter_form_tools` | Demonstrates `context.register_form_tool(...)` with an adjustable Diamond form. |

## Starter Diamond Plugin Behavior

The starter Diamond tool demonstrates:

- A custom form tool.
- Adjustable width.
- Adjustable height.
- Rotation setting.
- Live preview.
- Draggable field handles.
- Keyboard shortcut registration.

Use it as the simplest template for new shape tools.

## Development Tips

- Keep plugin geometry deterministic.
- Preserve `tool_context.dot_ids` order unless your tool intentionally remaps performers.
- Expose user-adjustable values through `settings`.
- Use handles for common size/radius controls.
- Avoid slow work inside the form callback because it runs during live preview.
- Test with small and large selections.
- Include a safe `deactivate(context)` if your plugin modifies long-lived UI state.

## Debugging

If a plugin breaks the app:

1. Disable it from the home screen `Plugins` tab.
2. If the app cannot open, move the plugin folder out of `Documents\Drill Pirate Plugins`.
3. Restart Drill Pirate.

During development, start Drill Pirate from a terminal so Python exceptions are visible.
