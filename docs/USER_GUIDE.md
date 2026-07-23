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
| Marchers | Number of performers to create in the starting block when no instrumentation roster is entered. |
| Roster | Optional lines like `Flute=5` or `Trumpet \| Brass = 5`. Instrument is the specific assignment, while Section is the broader selectable group. Generated performers use compact labels like `F1`, `T1`, `TR1`, and `M1`. |
| Front Ensemble Props | Optional movable front ensemble props placed in front of the field. |
| Drum Major Stands | Optional movable drum major stand props placed in front of the field. |
| Save Location | Root folder where the project folder is created. |

New projects start with red performers in a centered block that is optimized to fit on the field. Front ensemble and drum major stand items are props, so they can be moved independently through sets.

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
| Focus Field | `Ctrl+Alt+5` | Larger field view with condensed side and timeline panels still visible. |
| Music Design Workspace | `Ctrl+Alt+6` | Score import, phrase planning, storyboarding, and automated set suggestions. |
| Specialized Design Workspace | `Ctrl+Alt+7` | Custom surfaces, guard choreography, performer-linked props, and physical-limit analysis. |

## Music and Show Design

Open the **Music** workspace or use `Tools > Music & Show Design`.

1. Import `.musicxml`, `.xml`, `.mxl`, `.mid`, or `.midi` from **Score Import**.
2. Review imported measures, pickups, meter, tempo, rehearsal marks, and warnings.
3. Use **Phrase & Set Planner** to detect phrases and edit their ranges, intensity, and design notes.
4. Choose a target set length and transition profile, then generate a working set plan. Existing authored movement is preserved by default.
5. Use **Storyboard** to organize movements, scenes, production notes, and visual pacing.
6. Review **Automated Suggestions** for explainable recommendations based on phrase energy and existing form travel.
7. Click **Save Changes** to apply everything as one undoable project edit, or Cancel to discard the working plan.

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

### Custom Surfaces

Open `Tools > Specialized Design > Surface & Parade Route` or the **Specialized** workspace.

- Load College, High School, Indoor, Parade, or Staging presets, then customize dimensions and grid spacing.
- Football surfaces support college, high-school, custom, or hidden hashes plus configurable end zones and yard numbers.
- Parade surfaces use reorderable route points and a route-width corridor.
- Optional surface and line colors are saved with the project and appear in the editor, minimap, home cards, set thumbnails, PDFs, and MP4 exports.
- Indoor/staging coordinates export as centered X/Y values. Parade coordinates export as route station and left/right offset.
- Keyboard coordinate entry accepts `T1 X 4.5, Y -2` on any surface.

### Guard and Choreography

Select one or more performers, then open `Tools > Specialized Design > Guard Choreography Tracks`.

1. Choose choreography, toss, equipment change, spin, or dance/body.
2. Enter its count range and optional equipment, toss revolutions/height, and teaching notes.
3. Add the event; select a row and use **Update Selected Event** to revise it.
4. Review all events in the studio lane view or the bottom **Choreography** timeline.

Equipment changes update the performer's active equipment after the event's ending count. Overlapping toss/equipment-change assignments are blocked when saving.

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

### Moving During Set 1

Set 1 can have movement. Drill Pirate treats each marcher’s base `dots.json` position as the opening picture, then moves into Set 1’s stored position.

Use:

- Build the opening form on the field.
- Run `Tools > Set Opening Positions From Current View` or press `Ctrl+Alt+Shift+H`.
- Move the same marchers into the Set 1 ending form.
- Playback Set 1; marchers move from the captured opening form into the Set 1 form.

When the timeline is on Count 1 of Set 1, dragging marchers edits the opening picture. Scrub later in Set 1, or to the end count, to edit the Set 1 destination picture.

If marchers are selected, only selected marchers update their opening positions. If nothing is selected, all marchers update.

### Search and Batch Edit

Use the searchable marcher list to find performers by ID, name, section, instrument, rank, equipment, or layer. Select visible search results, then batch-edit metadata such as section, color, layer, instrument, rank, or equipment.

For selections of two or more marchers, toggle compact on-field transform handles with `Ctrl+Shift+T`, `View > Transform Handles`, the Selection inspector, or the field context menu. Handles are off by default. Drag corners to scale, the cyan handle to rotate, the white handle to move the pivot, or the yellow handle to move the form. Exact stretch/skew values remain in the Selection inspector. Arrow keys nudge by one 8-to-5 step; hold Shift for a half-step, Ctrl for one yard, or Alt for five yards.

Use `F4` to repeat the latest transform or other repeatable edit on the current selection.

## Props

Props are imported or designed visual objects that can move through sets like marchers.

Use:

- `Tools > Import Prop Image`.
- `Tools > Open Prop Designer`.
- Left panel `Prop Designer` tab.
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

The in-app **Prop Studio** is a layered, field-scaled design workspace. Set the prop's real width and height first, then use yard rulers, adjustable snapping, rectangles, ellipses, lines, freehand paths, text, and imported images. Selected layers have direct resize and rotation handles plus exact X/Y/width/height, rotation, opacity, fill, stroke, lock, alignment, duplicate, and ordering controls.

The **Field Preview** tab renders the actual design—not a placeholder—at its real field dimensions and initial position. Switch among White, Inverted, and Grass fields and use full-field, 60-yard, 30-yard, or 20-yard detail ranges. A six-foot performer reference appears beside the prop for scale.

Prop Studio supports undo/redo, keyboard nudging, multi-layer selection, visibility and locking, zoom-to-fit, and high-resolution transparent output. Saving creates both the PNG used by the show and an editable `.dpprop.json` document in the project `props\` folder. Use `Open` in Prop Studio to continue editing a saved source document.

Use `Fit Form to Selected Prop` to scale selected marchers to fit a selected prop while preserving the selected form shape.

To attach a prop to performers, select the prop and its carriers/pushers before opening `Tools > Specialized Design > Performer Prop Attachments`. Choose Carry, Push, or Rotate; set a count range, leader/handle, local offset, and rotation behavior. Drill Pirate initializes the offset from the prop's current location to avoid a jump when the link begins. During playback and export, the prop follows the interpolated performer positions.

Use the **Physical Limits & Warnings** page to review instrument defaults, save performer-specific overrides, and analyze the current set for travel, backward/lateral movement, turning, toss/recovery, surface-boundary, and parade-route risks.

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
- Director's Notes describing visual intent or rehearsal priorities.

Use the set list to add, remove, copy, rename, reorder, and edit counts/tempo. If a set does not specify its own tempo, it uses the project tempo or timing-map tempo active at that count.

Enter **Director's Notes** at the bottom of `Inspector > Sets > Set Details`. Notes save with the selected set, support application-level undo/redo, appear in the set-list tooltip, and print above that set's field chart in Drill Sheet and Staff Packet PDFs. Use this area for visual descriptions, staging intent, production cues, or rehearsal focus rather than performer-specific coordinate instructions.

The Ripple Edit Scope controls whether marcher edits affect only the current set, all following sets, a selected set range, sets until the next keyframe, or every set containing the same normalized formation. The same scope is honored by transforms, movement timing, facing, movement styles, path edits, and the property paintbrush.

Open the bottom panel's Movement Lanes tab to edit transition timing visually. Drag a bar edge to create a hold or change when a section starts/finishes. Drag the whole bar to move its timing window. The displayed yards-per-count value updates as the movement window changes.

Use the Beat-to-Set Generator from the timeline or Tools menu to turn musical markers into set boundaries. Drill Pirate samples the existing animation at each generated destination and leaves tempo events, ritardandos, fermatas, and audio anchors attached to their counts.

The Smart Transition Composer compares shortest-travel, rank-preserving, section-preserving, clockwise, counterclockwise, follow-leader, and lowest-conflict assignments. Review the distance and conflict scores, preview any row, then apply the preferred assignment.

The Property Paintbrush copies only the categories you select: relative form position, path geometry, facing, movement style, move timing, appearance metadata, and constraints. Copy from one marcher or an equal-sized form, select the targets, then paint with `Ctrl+Shift+V`.

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
| Circle / Oval | Places selected marchers on a hollow or solid round form. |
| Rectangle / Triangle / Diamond | Places selected marchers on hollow or solid common shapes. |
| Polygon / Star | Builds configurable hollow or solid polygons and stars. |
| Lasso | Freehand multi-select. |
| Scale Form | Scales the selected form larger/smaller without changing its shape identity. |
| Warp/Bend | Bends an existing form into waves or multi-bend shapes using draggable handles. |
| Rotate | Rotates a selected form with preview before applying. |
| Spiral | Places selected marchers on a spiral. |
| Block/Grid | Builds block and grid layouts. |
| SVG Shape | Imports and places selected marchers along an SVG outline or inside closed SVG paths. |

Tool controls only appear when that tool is active. Advanced tools also expose on-field handles when available.
Shape tools include a `Fill` control. Use `Hollow` for outlines and `Solid` for filled-in forms.

## Path Editing

Paths describe how a marcher travels from one set to the next.

To edit a path:

1. Select one or more marchers.
2. Make sure their yellow next-set path is visible.
3. Right-click the yellow path to add a red anchor.
4. Drag the red anchor to bend the path.
5. Drag cyan tangent handles for Bezier-style control.

Use `Clear Selected Paths` to remove custom path anchors/controls from selected marchers.

## Follow the Leader

Use `Follow the Leader...` or `Ctrl+Alt+F` when selected performers should trace one shared route instead of cutting directly between spots. Every follower retains its distance behind the marcher ahead, including through multiple curves and angle changes.

## Group Motion and CAD Drafting

Open the `Motion` tab for transition-level design tools:

- `Group Motion Ribbon` creates one shared curved route for the selected rank or section. Drag red route nodes or cyan tangent handles; hold `Alt` to mirror the opposite tangent. Marcher movement is locked while handles are active, and each drag creates one undo step.
- `Formation Morph` previews a coordinated blend into the current set picture with assignment, coherence, section/rank preservation, precision, and travel-facing options.
- `Continuity Designer` writes count-ranged step size, direction, body/horn facing, and performer instructions. These instructions appear in dot books and coordinate CSV exports.
- `Construction Guides` creates permanent draggable geometry. Lock finished guides to prevent accidental movement. No-go circles and rectangles are included in path warnings and the conflict timeline.
- `CAD Path Toolkit` operates on the active ribbon, selected guides, or selected marcher paths. Transition endpoints remain exact after CAD edits.

This is useful for:

- Circles.
- Squares.
- Stars.
- Conveyor-belt visuals.
- Custom plugin or SVG shapes where performers should preserve outline order.

The preview dialog supports incoming or current-form routes, automatic/open/closed topology, smooth curves or sharp corners, forward/reverse travel, roster or spatial order, and separate routes by disconnected form, row, file, or section. The red line is the shared route, gold dots are destinations, and the labeled gold handle identifies each leader.

Enable `Face the direction of travel throughout the move` to create per-count facing changes. Triangle marcher symbols continuously turn with the route tangent; `Facing Offset` adds an intentional visual orientation without changing the travel path.

## Snapping and Alignment

### Drill Grid & Snap

Use the always-visible `Grid Off` / `Grid 8:5` control in the top editor toolbar, the `Drill Grid & Snap` card at the top of the **Forms** tab, or `Tools > Configure Drill Grid...`.

- `8-to-5` creates eight equal marching steps in each 5-yard interval: `0.625 yd` or `22.5 in` per step.
- Standard presets include 6-to-5, 8-to-5, 12-to-5, and 16-to-5.
- Custom grids can use different horizontal and vertical step spacing plus an offset origin.
- When enabled, a clean purple snap-point lattice replaces the normal drafting subdivisions while official field markings remain visible. A full-line grid remains available in the grid dialog.
- Marcher drags, multi-selection moves, transform handles, draggable formation handles, and generated form spots snap to exact nodes.
- Formation handles remain attached to the previewed form. Curve draggers sit on the actual curve instead of floating at invisible Bezier control points.
- Built-in forms, SVG forms, and plugin forms use unique grid nodes so enabled snapping never stacks multiple marchers on one point.
- Official football front/back hashes remain exact priority snap rows at both 8-to-5 and 16-to-5, even though college hash offsets are not whole center-origin grid intervals.
- Dot-card and coordinate-sheet instructions always use standard 8-to-5 steps, even when a different construction grid is displayed.
- Grid settings are saved with the project and are undoable.

Use `Ctrl+Shift+G` to configure the grid and `Ctrl+Alt+Shift+N` to toggle it.

### Smart Alignment Guides

Enable **Smart Alignment Guides** when dragging marchers to show temporary purple alignment guides. This is separate from the exact drill-step grid.

Snap targets include:

- Yard-line alignment.
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

### Previous-Set Ghost

Enable **Ghost Previous Set** in the **View** tab to show the previous set as a faint, non-editable formation behind the current picture. The ghost updates when changing sets or crossing playback boundaries and follows the selected marcher-symbol and field-theme settings.

## Path Safety

Path analysis warns about:

- Close spacing.
- Crossing paths.
- High travel speed.
- Conflict-heavy counts in the timeline.

Optimize Selected Spot Assignment keeps every destination coordinate in place and changes only which selected marcher owns each spot. The solver evaluates synchronized spacing, crossing risk, travel outliers, movement windows, speed limits, and unselected marchers. It does not create path anchors or alter the destination picture. Review unresolved warnings when the fixed start and destination pictures make a conflict unavoidable.

## Large-Show Accelerators

Open `Tools > Large-Show Accelerators` or use the `Large Show` tab in the left panel.

### Import a roster

1. Choose `Import Roster CSV`.
2. Select a CSV containing any common combination of name, ID, instrument, section, rank, color, layer, or equipment columns.
3. Choose Merge to update matching IDs or Append to guarantee new IDs.
4. Review the generated IDs, colors, and layers before importing.

### Build and lock a hierarchy

Use `Hierarchy & Linked Formations`, then choose `Build From Roster` to create Ensemble → instrument family → section → rank groups. Double-click a group to select its members. Group transforms use numeric move, rotate, and scale values. Locked parent groups lock every descendant member.

### Link repeated or mirrored forms

Create equal-size groups for the master and each copy. Select the master group, choose `Link Groups`, then choose whether the instance is repeated or mirrored. Corresponding marcher edits remain connected until `Detach` is selected.

### Replace or swap performers

- Select one marcher to replace roster information at that drill spot.
- Select exactly two marchers to swap their roster identities.

Coordinates, paths, timing windows, facings, and set data remain assigned to the original drill spots.

### Clean a formation

Select a form and open `Automatic Form Cleanup`. Configure spacing, strength, and cleanup passes. Drill Pirate previews the proposed result and reports overlaps and average interval before applying it.

### Compare and save alternatives

- `Compare Sets` displays two field views and sortable difference vectors.
- `Formation Variations` stores selected or full-set alternatives without duplicating the project.

### Work across projects

Use `File > Open Project in New Tab` (`Ctrl+Shift+O`). Tabs can be reordered and closed independently. `File > Copy From Open Project Tab` copies a source formation, timing map, or props into the current project and supports undo.

## Exporting

Open `File > Export` or press `Ctrl+E`.

Export options:

- MP4 Video.
- Drill Sheet PDF.
- Dot Book PDF.
- Staff Packet PDF.
- Section Packet PDF.
- Coordinate Summary PDF.
- Coordinate CSV.
- Project ZIP.

Choose **PDF Layout Designer** in the Export window, or choose **Customize PDF Layout** inside any PDF's options. Layouts support movable/resizable text, images, field views, data tables, rectangles, and lines; portrait/landscape Letter, Legal, A4, and A3 pages; colors, typography, opacity, borders, image fitting, layers, locking, dynamic project tokens, and reusable presets. Use `{director_notes}` to place the active set's notes in a custom Drill Sheet or Staff Packet layout. Project images are copied into `print_assets`, and each PDF type keeps its own project layout.

See [Exports](EXPORTS.md) for details.

## Settings

Open settings with:

- `Settings > Preferences`.
- `Ctrl+,`.
- Home-screen settings button.

Tabs:

| Tab | Purpose |
| --- | --- |
| General | Switch Dark/Light Mode, choose White/Inverted/Grass field mode, choose marcher symbol style, toggle tooltips, and choose Stable Releases or Beta / Pre-Releases update channel. |
| Appearance | Customize UI font size plus app background, panels, surfaces, inputs, buttons, text, borders, accent, and selection colors. |
| Field Logo | Show or hide center-field branding, upload a custom PNG/JPG/WebP image, restore the Drill Pirate logo, and adjust opacity and size. |
| Devices | Choose Windows Default or a specific audio output device. |

Use `Refresh` in the Devices tab after plugging in headphones or changing audio hardware.
Use `Load Defaults For Selected Theme` in Appearance to return to clean Dark or Light colors.
Uploaded field logos are copied into Drill Pirate's local app data, so the original image can be moved afterward. Transparent PNG files produce the cleanest field result. Custom logos use full color on Grass fields, shaded grayscale on White fields, and inverted grayscale on Inverted fields.

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
2. Import the roster and build the ensemble hierarchy.
3. Build the opening form, then capture opening positions if Set 1 should move.
4. Add Set 2 and shape the next form.
5. Preview selected paths.
6. Add path anchors or follow-leader motion where needed.
7. Analyze paths for warnings.
8. Add markers and timing anchors to match music.
9. Rehearse playback by set and full show.
10. Export project ZIP, PDFs, CSV, and MP4 as needed.
