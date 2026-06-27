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

## Current Features

- Startup project creation with show title, audio file, BPM, default counts, time signature, and save folder.
- Startup splash screen with `Drill Pirate` and `Alpha Version 1.0.0`.
- Home gallery that scans `Documents\Drill Pirate Projects` and opens projects from preview cards.
- Top create-project card with a field preview and plus button that opens the project creation dialog.
- Project folder layout with `audio/`, `show.json`, `sets.json`, `dots.json`, and `metadata.json`.
- Dark-mode interface with a natural green field view.
- Compact menu bar for file, edit, playback, and tools commands.
- Zoomable and pannable field with 5-yard grid lines and real field coordinates.
- Editable dots with ID/name, X/Y, section, color, and per-set positions.
- Rubber-band multi-selection, shift selection through Qt selection behavior, drag movement, and right-click formation menu.
- Set list with add, remove, copy, editable name, tempo override, count ranges, and interpolation mode.
- Timeline scrubber with count-level preview and marker creation.
- Playback timer targeting 60 FPS and optionally synced audio playback through QtMultimedia.
- Formation tools for line, curve, arc, scatter, mirror, horizontal align, vertical align, and interval spacing.
- Formation previews with target ghosts and travel lines before applying tool changes.
- Draggable on-field preview handles for curve bend and arc radius/sweep adjustments.
- Stable dot-to-slot ordering so selected marchers keep local order when reshaping a line into curves or arcs.
- Group move, rotate, and center-to-field tools for selected forms.
- Undo/redo for dot and formation movement.
- Autosave every 8 seconds plus explicit save.
- Export dialog for ZIP projects, ffmpeg-based MP4 rendering, and landscape drill-sheet PDFs.

## Design Notes

- Coordinates are stored in field units, not pixels. The graphics view maps those units to scene coordinates.
- Audio is treated as the playback source when loaded, while count interpolation remains driven by BPM and set structure.
- The renderer is Qt Graphics View for portability. The field view is isolated so it can later be swapped to OpenGL without replacing the project model.
- The app starts with 30 red sample dots so a new project is immediately editable.

## Shortcuts

- `Ctrl+M`: add marcher on Set 1.
- `Del`: delete selected marchers on Set 1.
- `Ctrl+Shift+S`: add set.
- `Ctrl+Shift+Backspace`: remove set.

## Editing Notes

- Tool options are contextual. Only the active formation tool shows its edit controls.
- Hold `Shift` while using another tool to add/remove dot selections without returning to Select.
- Selected marchers show yellow transition paths. In edit mode, those paths point to the next set. During playback, they show the active transition.
- Right-click a yellow path to add a red path anchor, then drag the red anchor to curve that marcher's route.
- Shape Line starts with the two outside selected marchers as anchors. Right-click internal selected marchers to toggle them as red anchors, drag anchors to reshape the line, then apply the preview.

## Roadmap

- True audio-clock position mapping for scrubbing into arbitrary audio timestamps.
- Lasso selection and richer formation handles.
- Per-count micro edits and custom Bezier path editing.
- Collision/path conflict detection.
- Layer/group visibility and section-specific tool filters.
- Cleaner print/export layouts for staff and performer handouts.
