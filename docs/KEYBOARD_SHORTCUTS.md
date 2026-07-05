# Keyboard Shortcuts

Drill Pirate includes built-in shortcuts and a shortcut editor.

Open the shortcut editor with:

```text
Edit > Keyboard Shortcuts
Ctrl+Alt+,
```

Open the command palette with:

```text
Edit > Command Palette
Ctrl+Shift+P
```

## File and Edit

| Command | Shortcut |
| --- | --- |
| Save | `Ctrl+S` |
| Save As | `Ctrl+Shift+S` |
| Export | `Ctrl+E` |
| Undo | `Ctrl+Z` |
| Redo | `Ctrl+Y` |
| Command Palette | `Ctrl+Shift+P` |
| Keyboard Shortcuts | `Ctrl+Alt+,` |

## Settings and Playback

| Command | Shortcut |
| --- | --- |
| Preferences | `Ctrl+,` |
| Toggle Loop Current Set | `Ctrl+L` |
| Go To Count | `Ctrl+G` |

## Workspace Presets

| Command | Shortcut |
| --- | --- |
| Design Workspace | `Ctrl+Alt+1` |
| Forms Workspace | `Ctrl+Alt+2` |
| Rehearse Workspace | `Ctrl+Alt+3` |
| Print Workspace | `Ctrl+Alt+4` |
| Focus Field | `Ctrl+Alt+5` |

## Roster and Sets

| Command | Shortcut |
| --- | --- |
| Add Marcher | `Ctrl+M` |
| Delete Selected | `Del` |
| Import Prop Image | `Ctrl+Alt+I` |
| Add Set | `Ctrl+Alt+S` |
| Remove Set | `Ctrl+Alt+Backspace` |

## Tools

| Command | Shortcut |
| --- | --- |
| Select Tool | `Alt+1` |
| Line Tool | `Alt+2` |
| Curve Tool | `Alt+3` |
| Arc Tool | `Alt+4` |
| Scatter Tool | `Alt+5` |
| Mirror Tool | `Alt+6` |
| Shape Line Tool | `Alt+7` |
| Circle Tool | `Alt+8` |
| Rectangle Tool | `Alt+9` |
| Lasso Tool | `Alt+0` |
| Scale Form Tool | `Ctrl+Alt+X` |
| Spiral Tool | `Ctrl+Alt+P` |
| Block/Grid Tool | `Ctrl+Alt+B` |
| SVG Shape Tool | `Ctrl+Alt+V` |

## Path, Form, and Rehearsal Commands

| Command | Shortcut |
| --- | --- |
| Toggle Snap Align | `Ctrl+Alt+N` |
| Analyze Paths | `Ctrl+Alt+A` |
| Auto Plan Selected Paths | `Ctrl+Alt+R` |
| Clear Selected Paths | `Ctrl+Alt+Shift+R` |
| Set Count Keyframe | `Ctrl+Alt+K` |
| Follow-Leader Conveyor | `Ctrl+Alt+F` |
| Fit Form to Selected Prop | `Ctrl+Alt+Shift+X` |

## Plugin Shortcuts

Plugins can register their own shortcuts. They appear in the command palette and shortcut editor after the plugin is enabled.

The default starter form-tool plugin registers:

| Command | Shortcut |
| --- | --- |
| Diamond Form | `Ctrl+Alt+D` |

## Shortcut Editing Notes

- Search by command name or shortcut.
- Select a command.
- Press the new key sequence in the shortcut editor.
- Apply/reset as needed.
- Custom shortcuts are saved in user settings.

If two commands use the same shortcut, Qt may trigger only one depending on focus and command context. Avoid duplicate shortcuts for core editing tools.
