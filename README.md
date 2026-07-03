# Drill Pirate

Drill Pirate is a Python/PySide6 desktop prototype for marching band and DCI-style drill design. It focuses on a functional professional workflow first: project library browsing, field editing, dot selection, set-based movement, count playback, formation tools, autosave, undo/redo, and export hooks.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m drill_writer
```

For MP4 export, you can either put `ffmpeg` on `PATH` or use `Set ffmpeg.exe` in the export dialog to browse to the executable directly. The app remembers that choice.

## Plugins

Plugins live in `Documents\Drill Pirate Plugins` and can be enabled from the home screen `Plugins` tab. The packaged EXE includes the Python runtime, so users do not need a separate Python install for normal `.py` plugins. Plugins can register custom form tools, menu actions, panel buttons, and stylesheets. Plugin development instructions are in `docs\PLUGIN_DEVELOPMENT.md`.

## Build Windows Executable

```powershell
.\build_exe.ps1
```

The packaged app is created at `dist\Drill Pirate\Drill Pirate.exe`. Give testers the whole `dist\Drill Pirate` folder because Qt DLLs and plugins live beside the executable. `ffmpeg` is not bundled; testers still need to install it or select their own `ffmpeg.exe` from the export dialog for MP4 export.

The build script also creates `dist\Drill Pirate Alpha 2.0.0 Windows.zip` for easier tester distribution.

## Current Features

- Startup project creation with show title, audio file, BPM, default counts, marcher count, time signature, and save folder.
- Startup splash screen with `Drill Pirate` and `Alpha Version 2.0.0`.
- Home gallery that scans `Documents\Drill Pirate Projects` and opens projects from preview cards.
- Home `Plugins` tab with folder-based plugin discovery and activation toggles.
- Top create-project card with a field preview and plus button that opens the project creation dialog.
- Project folder layout with `audio/`, `show.json`, `sets.json`, `dots.json`, and `metadata.json`.
- Dark-mode interface with a natural green field view.
- Compact menu bar for file, edit, playback, and tools commands.
- Zoomable and pannable field with 5-yard grid lines and real field coordinates.
- Editable performers with ID/name, X/Y, section, instrument, rank, equipment, layer, color, and per-set positions.
- Rubber-band multi-selection, shift selection through Qt selection behavior, drag movement, and right-click formation menu.
- Set list with add, remove, copy, editable name, tempo override, count ranges, and interpolation mode.
- Timeline scrubber with waveform display, count-level preview, micro-edit keyframes, and marker creation.
- True timing-map playback using audio anchors, tempo events, ritardandos, fermatas, pickup offsets, loop-current-set rehearsal mode, slow/fast playback rates, and count finder.
- Multiple audio-version management inside each project.
- Formation tools for line, curve, arc, circle, rectangle, spiral, block/grid, imported SVG shapes, organized scatter, mirror, horizontal align, vertical align, and interval spacing.
- Formation previews with target ghosts and travel lines before applying tool changes.
- Draggable on-field preview handles for curve bend, arc radius/sweep, shape sizing, and SVG shape sizing.
- Stable dot-to-slot ordering so selected marchers keep local order when reshaping a line into curves or arcs.
- Group move, rotate, and center-to-field tools for selected forms.
- Follow-leader rotate creates circular path anchors so selected circle forms travel around the form instead of cutting straight across.
- Snap Align mode shows a thin purple horizontal/vertical guide while dragging near grid or performer alignment.
- Path safety analysis for close spacing, crossing paths, and high travel speed, plus simple auto-planning anchors.
- Persistent line constraints and interval normalization for selected forms.
- Section/layer visibility filters for large projects.
- Lasso selection tool for freehand multi-select.
- Bezier/tangent path editing with red anchors and cyan in/out tangent handles.
- Undo/redo for dot and formation movement.
- Autosave every 8 seconds plus explicit save.
- Export dialog for ZIP projects, ffmpeg-based MP4 rendering, landscape drill-sheet PDFs, staff packet PDFs, dot-book PDFs, and coordinate CSVs.

## Design Notes

- Coordinates are stored in field units, not pixels. The graphics view maps those units to scene coordinates.
- Audio is treated as the playback source when loaded, while count interpolation remains driven by BPM and set structure.
- The renderer is Qt Graphics View for portability. The field view is isolated so it can later be swapped to OpenGL without replacing the project model.
- New projects start with the requested number of red performers in a centered block that fits inside the field.

## Shortcuts

- `Ctrl+M`: add marcher on Set 1.
- `Del`: delete selected marchers on Set 1.
- `Ctrl+Alt+S`: add set.
- `Ctrl+Alt+Backspace`: remove set.
- `Alt+1` through `Alt+9`: select, line, curve, arc, scatter, mirror, shape line, circle, rectangle.
- `Alt+0`: lasso selection.
- `Ctrl+Alt+P`: spiral tool.
- `Ctrl+Alt+B`: block/grid tool.
- `Ctrl+Alt+V`: SVG shape tool.
- `Ctrl+Alt+N`: toggle Snap Align.
- `Ctrl+Alt+A`: analyze paths.
- `Ctrl+Alt+R`: auto-plan selected paths.
- `Ctrl+Alt+K`: set count keyframe.
- `Ctrl+Alt+F`: follow-leader rotate.
- `Ctrl+L`: loop current set.
- `Ctrl+G`: focus count finder.

## Editing Notes

- Tool options are contextual. Only the active formation tool shows its edit controls.
- Hold `Shift` while using another tool to add/remove dot selections without returning to Select.
- Enable Snap Align in the View tab to show purple snap guides while dragging near yard lines, hashes, or other performers.
- Turn on Micro Edit Dragging in the Rehearse tab to store selected-dot edits at the current count instead of changing the set endpoint.
- Use Rehearse > Audio + Timing Map to add alternate audio files, map exact count/audio anchors, and add tempo, ritard, fermata, or pickup events.
- Selected marchers show yellow transition paths. In edit mode, those paths point to the next set. During playback, they show the active transition.
- Right-click a yellow path to add a red path anchor, drag the red anchor to curve the route, or drag the cyan tangent handles for Bezier-style control.
- Scatter uses circle, square, or rectangle layouts with controlled jitter and spacing instead of pure random placement.
- Import an SVG from the SVG Shape tool, then apply it to selected performers like any other formation preview.
- Use Follow-Leader Rotate on circular forms to create a rotating move around the circle.
- Shape Line starts with the two outside selected marchers as anchors. Right-click internal selected marchers to toggle them as red anchors, drag anchors to reshape the line, then apply the preview.

## Roadmap

- Collision-avoidance optimization that reasons about whole sections, not just pairwise route anchors.
- Full printed coordinate book layout customization.
- Installer, update channel, code signing, and crash reporting.
