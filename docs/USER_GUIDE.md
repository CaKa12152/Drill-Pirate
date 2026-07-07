# User Guide

This guide explains the full Drill Pirate workflow from creating a project to exporting production materials.

## Home Screen

When Drill Pirate opens, it shows a branded splash screen and then the home screen.

The home screen has:

- A project gallery from `Documents\Drill Pirate Projects`.
- Field-preview cards for existing projects.
- A large create-project card with a plus button.
- A `Plugins` tab for enabling and disabling plugin folders.
- Settings access for preferences and audio output devices.

Click a project card to open that show. Click the create-project card to start a new show.

## Create a Project

The project dialog creates the project folder and initial data files.

Fields:

| Field | Meaning |
| --- | --- |
| Show Title | Project display name and default folder name. |
| Audio Upload | Optional MP3/WAV file copied into the project `audio\` folder. |
| Initial Tempo | Universal/default BPM for the show. |
| Default Counts Per Set | Count length used when new sets are created. |
| Time Signature | Display metadata for the project. |
| Marchers | Number of performers to create in the starting block. |
| Save Location | Root folder where the project folder is created. |

New projects start with red performers in a centered block that is optimized to fit on the field.

## Main Interface

The main window is organized around the field:

| Area | Purpose |
| --- | --- |
| Center Field | Primary editing canvas for marchers, props, forms, paths, and field coordinates. |
| Left Docks | Marcher list, tool controls, formation tools, visibility filters, and plugin actions. |
| Right Dock | Inspector for selected marcher, set, coordinate, color, section, and metadata editing. |
| Bottom Dock | Timeline, waveform, markers, audio/timing controls, and rehearsal tools. |
| Top Menus | File, Edit, View, Playback, Tools, Settings, and plugin-added menus. |

Panels can be docked, floated, closed, and restored from `View > Panels`.

## Workspaces

Use workspaces to reduce panel crowding.

| Workspace | Shortcut | Best For |
| --- | --- | --- |
| Design Workspace | `Ctrl+Alt+1` | General drill writing. |
| Forms Workspace | `Ctrl+Alt+2` | Formation tools and shape editing. |
| Rehearse Workspace | `Ctrl+Alt+3` | Playback, timing, waveform, markers, and movement styles. |
| Print Workspace | `Ctrl+Alt+4` | Export and staff/performer review. |
| Focus Field | `Ctrl+Alt+5` | Maximum field space with minimal panels. |

## Field and Coordinates

The field uses real field units rather than screen pixels.

- Horizontal field coordinates are stored in yards from the 50-yard line.
- Vertical field coordinates are stored in yards from midfield.
- The display includes yard lines, hashes, sidelines, grid lines, and readable drill labels.
- Performer coordinates are translated into drill-sheet language such as `On 45 S2`, `2 steps inside 40 S1`, or `6 steps in front of FH`.

Coordinate references:

| Term | Meaning |
| --- | --- |
| `S1` | Side 1 / left side from the audience perspective. |
| `S2` | Side 2 / right side from the audience perspective. |
| `FS` | Front sideline. |
| `BS` | Back sideline. |
| `FH` | Front hash. |
| `BH` | Back hash. |
| `Mid` | Midfield front-to-back center line. |

## Marchers

Marchers are editable performers.

Each marcher stores:

- ID.
- Name.
- X/Y field position.
- Color.
- Section.
- Instrument.
- Rank.
- Equipment.
- Layer.
- Per-set positions.
- Optional path anchors and Bezier controls.
- Optional count-level keyframes.
- Optional movement style for a set.

Default marchers are red unless changed manually or by group color tools.

### Add or Delete Marchers

Use:

- `Tools > Add Marcher`.
- `Tools > Delete Selected`.
- `Ctrl+M` to add.
- `Del` to delete selected marchers.

Add/delete is intended for Set 1 so the roster stays consistent across the show.

### Search and Batch Edit

Use the searchable marcher list to find performers by ID, name, section, instrument, rank, equipment, or layer. Select visible search results, then batch-edit metadata such as section, color, layer, instrument, rank, or equipment.

## Props

Props are imported image objects that can move through sets like marchers.

Use:

- `Tools > Import Prop Image`.
- `Ctrl+Alt+I`.

Props store:

- ID.
- Name.
- Image file.
- X/Y position.
- Width.
- Height.
- Rotation.
- Layer.

Imported images are copied into the project `props\` folder. Props are included in project previews and export images.

Use `Fit Form to Selected Prop` to scale selected marchers to fit a selected prop while preserving the selected form shape.

## Selection

Supported selection methods:

- Click a marcher.
- Drag a rectangle around marchers.
- Hold `Shift` and click dots to add or remove selection.
- Use the lasso tool for freehand selection.
- Search marchers and select visible results.

Selected marchers show yellow transition paths:

- In edit mode, the path points toward the next set.
- During playback, the path represents the active transition.

## Sets and Counts

A show is divided into sets.

Each set contains:

- Name.
- Start count.
- End count.
- Optional tempo override.
- Dot positions.
- Prop positions.
- Path anchors.
- Count-level keyframes.
- Movement styles.
- Transition mode.

Use the set list to add, remove, copy, rename, reorder, and edit counts/tempo. If a set does not specify its own tempo, it uses the project tempo or timing-map tempo active at that count.

## Timeline and Playback

Audio is the main playback source when loaded.

Timeline features:

- Play/pause.
- Scrub by count or waveform position.
- Go to count.
- Loop current set.
- Slow/fast rehearsal playback rates.
- Count markers.
- Auto hit-marker detection from waveform peaks.
- Count-level micro editing.

Use `Ctrl+G` to focus the count finder.

## Audio and Timing Map

The audio/timing panel supports:

- Active audio playback.
- Waveform analysis without ffmpeg.
- Reload audio.
- Multiple audio versions.
- Timing anchors that map counts to exact audio timestamps.
- Tempo events.
- Ritardandos.
- Fermatas.
- Pickup offsets.
- Auto detected hit markers.

Use timing anchors when the music does not line up perfectly with a single fixed BPM.

## Movement Styles

Movement styles can be assigned to selected marchers for the current set:

- Normal.
- Half Time.
- Double Time.
- Jazz Run.
- At Halt.
- Visual.

These values appear in performer/staff export materials and help communicate intent. They are set-based metadata for selected marchers.

## Formation Tools

Formation tools work on selected marchers and show previews before committing changes.

Built-in tools:

| Tool | Purpose |
| --- | --- |
| Select | Normal selection and movement. |
| Line | Evenly spaces marchers on a straight line. |
| Curve | Bends a selected line with a draggable control. |
| Arc | Places selected marchers on a circle segment. |
| Scatter | Creates organized circle, square, or rectangle scatter layouts with spacing. |
| Mirror | Mirrors selected performers across an axis. |
| Shape Line | Uses selected marchers as anchors for straight/curved line segments. |
| Circle | Places selected marchers on a full circle. |
| Rectangle | Places selected marchers on a rectangle perimeter. |
| Lasso | Freehand multi-select. |
| Scale Form | Scales the selected form larger/smaller without changing its shape identity. |
| Spiral | Places selected marchers on a spiral. |
| Block/Grid | Builds block and grid layouts. |
| SVG Shape | Imports and places selected marchers along an SVG path. |

Tool controls only appear when that tool is active. Advanced tools also expose on-field handles when available.

## Path Editing

Paths describe how a marcher travels from one set to the next.

To edit a path:

1. Select one or more marchers.
2. Make sure their yellow next-set path is visible.
3. Right-click the yellow path to add a red anchor.
4. Drag the red anchor to bend the path.
5. Drag cyan tangent handles for Bezier-style control.

Use `Clear Selected Paths` to remove custom path anchors/controls from selected marchers.

## Follow-Leader Conveyor

Use `Follow-Leader Conveyor` when selected performers should rotate or travel around a shape instead of cutting directly across it.

This is useful for:

- Circles.
- Squares.
- Stars.
- Conveyor-belt visuals.
- Custom plugin or SVG shapes where performers should preserve outline order.

## Snapping and Alignment

Enable Snap Align when dragging marchers to show purple snap guides.

Snap targets include:

- Yard-line/grid alignment.
- Horizontal alignment with performers.
- Vertical alignment with performers.

Alignment tools include:

- Horizontal align.
- Vertical align.
- Interval spacing.
- Center to field.
- Fit form to prop.
- Scale form.

Constraint tools include:

- Create Line Constraint.
- Create Pivot Constraint.
- Create Arc Constraint.
- Create Block Constraint.
- Apply Constraints.

Active constraints are enforced while constrained marchers are moved.

## Path Safety

Path analysis warns about:

- Close spacing.
- Crossing paths.
- High travel speed.
- Conflict-heavy counts in the timeline.

Auto-plan selected paths can add basic route anchors, but it is not a full commercial-grade collision solver yet. Review all automated results visually before relying on them.

## Exporting

Open `File > Export` or press `Ctrl+E`.

Export options:

- MP4 Video.
- Drill Sheet PDF.
- Dot Book PDF.
- Staff Packet PDF.
- Coordinate CSV.
- Project ZIP.

See [Exports](EXPORTS.md) for details.

## Settings

Open settings with:

- `Settings > Preferences`.
- `Ctrl+,`.
- Home-screen settings button.

Tabs:

| Tab | Purpose |
| --- | --- |
| Preferences | Switch Dark/Light Mode and choose Stable Releases or Beta / Pre-Releases update channel. |
| Devices | Choose Windows Default or a specific audio output device. |

Use `Refresh` in the Devices tab after plugging in headphones or changing audio hardware.

## Plugins

Open the home screen `Plugins` tab to enable or disable plugins.

Plugin folders live in:

```text
Documents\Drill Pirate Plugins
```

Plugins can add form tools, commands, buttons, styles, and UI changes. See [Plugin Development](PLUGIN_DEVELOPMENT.md).

## Data Safety and Recovery

Drill Pirate protects project data with:

- Atomic JSON saves.
- Versioned save/autosave backups.
- Project schema migrations.
- Corrupt-project detection.
- Recovery cards on the home screen.
- `File > Restore Previous Save`.

If a project cannot open, Drill Pirate offers to restore the newest backup or export a bug report bundle.

## Crash Reports

Use:

```text
Help > Export Bug Report Bundle
```

The bundle includes recent crash logs, diagnostics, and the current project folder. Send this ZIP when reporting project-specific bugs.

## Recommended Workflow

1. Create project with audio, BPM, default counts, and starting marcher count.
2. Rename/set up performers by section.
3. Build Set 1.
4. Add Set 2 and shape the next form.
5. Preview selected paths.
6. Add path anchors or follow-leader motion where needed.
7. Analyze paths for warnings.
8. Add markers and timing anchors to match music.
9. Rehearse playback by set and full show.
10. Export project ZIP, PDFs, CSV, and MP4 as needed.
