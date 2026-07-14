# Feature Reference

This page is a full reference of the major Drill Pirate features currently represented in the application and documentation.

## Project Library

| Feature | Description |
| --- | --- |
| Splash screen | Shows Drill Pirate branding and current alpha version on startup. |
| Project gallery | Scans `Documents\Drill Pirate Projects` and displays existing shows as preview cards. |
| Field previews | Shows a preview of Set 1, including marchers and props. |
| Create-project card | Large plus-card opens the project creation dialog. |
| Plugin tab | Lists plugin folders from `Documents\Drill Pirate Plugins` with activation toggles. |
| Settings access | Opens preferences and audio device settings from the home flow. |
| Recovery cards | Corrupt projects appear as recovery cards instead of disappearing from the gallery. |

## Project Creation

| Feature | Description |
| --- | --- |
| Show title | Names the project and generated folder. |
| Audio import | Copies selected audio into the project `audio\` folder. |
| Initial tempo | Sets the universal/default BPM. |
| Default counts | Sets the default count length for new sets. |
| Time signature | Stores display metadata. |
| Marcher count | Creates a starting block with the requested number of performers. |
| Instrumentation roster | Keeps specific instruments separate from broad sections, supports explicit `Instrument \| Section = Count` entries, and creates compact labels such as `F1`, `T1`, `TR1`, `TU1`, and `M1`. |
| Front ensemble props | Adds movable front ensemble props in front of the field. |
| Drum major stands | Adds movable drum major stand props. |
| Optimized starting block | Fits the initial performer block inside the field. |

## Main Window

| Feature | Description |
| --- | --- |
| Dockable panels | Tools, inspector, list, and timeline panels can dock, float, close, and reattach. |
| Workspace presets | Design, Forms, Rehearse, Print, and Focus Field layouts, with Focus Field keeping condensed panels visible. |
| Command palette | Search and run commands from the keyboard. |
| Shortcut editor | Search commands and assign custom keyboard shortcuts. |
| Dark/light/custom themes | Switch themes and customize app background, panels, inputs, buttons, text, borders, accent, selection, and font size. |
| Field modes | Choose White Field, Inverted Field, or Grass Field rendering. |
| Marcher symbols | Switch performer rendering between filled circles, hollow circles, X marks, plus marks, squares, diamonds, and triangles. |
| Update channel | Choose Stable Releases or Beta / Pre-Releases from Settings. |
| Less panel crowding | Workspaces and floating docks allow large-show layouts on smaller screens. |

## Field View

| Feature | Description |
| --- | --- |
| Field rendering modes | White, inverted black/white, and grass-style field presentations designed for drill readability. |
| Zoom and pan | Navigate the field without changing drill coordinates. |
| Yard/grid system | 5-yard references and smaller grid subdivisions. |
| Drill coordinates | Converts internal coordinates to performer-readable drill sheet language. |
| Selection overlays | Shows selected performers, ghosts, previews, paths, and handles. |
| Prop rendering | Displays scalable imported prop images. |

## Marchers

| Feature | Description |
| --- | --- |
| Editable dots | ID, name, X/Y, color, section, instrument, rank, equipment, and layer. |
| Default red color | New/default marchers use red unless changed. |
| Group color assignment | Batch color selected marchers or filtered groups. |
| Searchable list | Search marchers by identifying metadata. |
| Batch editing | Apply shared metadata to selected performers. |
| Opt-in transform handles | A compact, toggleable multi-selection gizmo provides move, rotate, corner scale, and editable pivot operations; exact stretch/skew controls remain in the inspector. |
| Exact transform entry | Enter offsets, rotation, scale, skew, and pivot coordinates from the Selection inspector or the on-field Transform HUD. |
| Precision nudging | Arrow keys move selected performers by a marching step; modifiers provide half-step, one-yard, and five-yard increments. |
| Property paintbrush | Copy and paint position/form, paths, facing, movement style, move timing, appearance metadata, and constraints independently. |
| Set positions | Every set stores positions for every marcher. |
| Set 1 movement | Set 1 can animate from captured opening positions into Set 1 positions. |
| Opening-position editing | Dragging marchers at Count 1 of Set 1 edits the opening picture; later counts edit the destination. |
| Count keyframes | Optional per-count position overrides within a set. |
| Move windows | Selected marchers can hold, start moving mid-set, or finish early inside the same set. |
| Movement lanes | A draggable transition timeline shows section or selected-marcher move windows, implied velocity, holds, and staggered entrances. |
| Facing direction | Selected marchers can store per-set facing angles for triangle-symbol visual turns. |
| Movement styles | Normal, half time, double time, jazz run, halt, and visual. |

## Props

| Feature | Description |
| --- | --- |
| Image import | Imports a prop image into the project `props\` folder. |
| In-app prop designer | Draws props with rectangles, circles/ovals, lines, text, colors, stroke controls, exact field sizing, and anchor-based shape scaling. |
| Scalable props | Props store width, height, rotation, and position. |
| Set-based prop movement | Props store per-set state like marchers. |
| Preview/export support | Props appear in home previews and printed field images. |
| Fit form to prop | Scales selected marchers to fit the selected prop footprint. |

## Selection

| Feature | Description |
| --- | --- |
| Click select | Selects individual performers. |
| Shift select | Adds/removes performers from selection without switching tools. |
| Rubber-band selection | Drag rectangle selects multiple dots. |
| Lasso selection | Freehand selection for dense forms. |
| Search select | Selects visible search results from the marcher list. |
| Path display | Selected marchers show yellow transition paths. |

## Sets

| Feature | Description |
| --- | --- |
| Add/remove sets | Create and delete drill sets. |
| Copy sets | Duplicate existing set positions and metadata. |
| Editable names | Rename sets for musical or visual moments. |
| Count ranges | Each set stores start and end count. |
| Tempo override | Set-specific BPM can override project tempo. |
| Transition mode | Linear, ease-in-out, or curved transition metadata. |
| Dot positions | Each set stores all performer endpoints. |
| Prop positions | Each set stores all prop states. |

## Timeline, Audio, and Timing

| Feature | Description |
| --- | --- |
| Audio playback | Uses Qt multimedia playback when audio is loaded. |
| Waveform display | Analyzes local audio and displays dynamics without ffmpeg. |
| Scrubbing | Click waveform/count positions to seek. |
| True timing map | Maps counts to audio timestamps with anchors and tempo events. |
| Multiple audio versions | Store alternate audio files inside the project. |
| Tempo changes | Add tempo events at arbitrary counts. |
| Ritardandos | Store gradual tempo changes over count ranges. |
| Fermatas | Store timing holds. |
| Pickup offsets | Support pickup timing before Count 1. |
| Markers | Add manual markers and count markers. |
| Auto hit markers | Detect high-energy waveform moments and create markers. |
| Beat-to-set generator | Turn selected musical markers into named set boundaries while preserving the tempo map, ritardandos, fermatas, audio anchors, and sampled drill pictures. |
| Reload audio | Re-run audio load/waveform analysis. |
| Audio devices | Choose Windows Default or a specific connected output. |

## Formation Tools

| Tool | Description |
| --- | --- |
| Line | Evenly spaces selected marchers on a straight line. |
| Curve | Bends selected marchers into a curve with field handles. |
| Arc | Places selected marchers along a circle segment. |
| Scatter | Creates organized circle, square, or rectangle scatter layouts with spacing. |
| Mirror | Mirrors selected marchers across an axis. |
| Shape Line | Uses selected performers as anchors for mixed straight/curved line segments. |
| Circle / Oval | Places selected marchers around or inside round shapes. |
| Rectangle / Triangle / Diamond | Places selected marchers around or inside common polygon shapes. |
| Polygon / Star | Builds configurable hollow or solid regular polygons and stars. |
| Scale Form | Expands/contracts selected form spacing while preserving the form shape. |
| Warp/Bend | Bends an existing selected form with multiple draggable wave handles. |
| Rotate | Rotates a selected form with live preview and a draggable angle handle. |
| Spiral | Places selected marchers on a spiral. |
| Block/Grid | Generates block or grid formations. |
| SVG Shape | Imports SVG paths and distributes performers along the outline or inside closed paths. |
| Plugin Form | Runs custom form tools supplied by enabled plugins. |

## Advanced Editing

| Feature | Description |
| --- | --- |
| Live previews | Formation tools show ghosts and travel lines before applying. |
| Contextual controls | Only the active tool's settings are shown. |
| On-field handles | Drag tool handles directly on the field when supported. |
| Stable dot ordering | Tools try to preserve local selected order to avoid chaotic remapping. |
| Deterministic assignment | Ordered form tools preserve performer order and rotate/reverse closed shapes to minimize travel. |
| Assignment strategies | Choose automatic, shortest travel, section-aware, rank/file preserving, clockwise, counterclockwise, follow-leader, or lowest-conflict matching. |
| Smart transition composer | Compare complete assignment candidates with total travel, longest move, crossing, spacing, and weighted conflict scores before applying. |
| Section-aware fitting | Keeps sections and ranks spatially related while assigning performers to SVG and complex-form targets. |
| Global SVG assignment | SVG imports use global minimum-distance matching so one nearby dot does not steal another dot's best target. |
| Center selected | Moves selected formation to the field center. |
| Rotate selected | Rotates selected form as a group. |
| Follow-leader conveyor | Builds ordered motion around an outline instead of direct cross-form travel. |
| Fit to prop | Scales selected formation to a selected prop footprint. |
| Opening positions | Capture the current field view as the Set 1 starting form without changing Set 1 endpoints. |
| Quick workflow | Select same section, invert selection, select moving marchers, copy sets, and carry selected dots forward. |
| Repeat Last Action | Press F4 to repeat the latest transform, formation, batch metadata edit, property paint, or repeatable set operation. |
| Parameterized macros | Macros capture command context, selection, tool values, and counts, then replay with repeat loops and optional set advancement. |
| Ripple edit scopes | Apply transforms, timing, facing, movement styles, paths, and painted properties to the current set, all following sets, a selected range, until the next keyframe, or every matching formation. |
| Snap align | Shows purple horizontal/vertical snap guides while dragging. |
| Interval tools | Align and normalize spacing for selected marchers. |

## Constraint System

| Feature | Description |
| --- | --- |
| Line constraints | Keep selected marchers in a straight line at the target interval. |
| Pivot constraints | Keep a group's relative offsets locked to the first selected marcher. |
| Arc constraints | Preserve a selected arc relationship while keeping the arc centered on the edited group. |
| Block constraints | Rebuild selected marchers into a consistent block/grid relationship. |
| Constraint-on-move | Active constraints are applied during dot/form movement, not just by manual cleanup. |

## Path Editing and Safety

| Feature | Description |
| --- | --- |
| Yellow selected paths | Shows selected marcher travel to the next set or active playback target. |
| Red anchors | Add path anchors by right-clicking a yellow path. |
| Bezier handles | Drag cyan tangent handles for curved routes. |
| Clear selected paths | Remove custom anchors/controls from selected marchers. |
| Path analysis | Warns for close spacing, crossing paths, and high travel speed. |
| Conflict timeline | Samples counts through each transition and summarizes conflict-heavy moments. |
| Large-show crossings | Crossing checks run on shows up to the 400+ dot range with segment broad-phase filtering. |
| Auto-plan paths | Adds basic anchors for selected paths; results should be reviewed. |

## Visibility and Large Shows

| Feature | Description |
| --- | --- |
| Section filters | Hide or show sections. |
| Layer filters | Hide or show layers. |
| Label toggles | Reduce visual clutter on dense charts. |
| Searchable performer list | Faster navigation in 150+ performer projects. |
| Floating panels | Move panels to a second monitor or temporary workspace. |
| Roster CSV import | Detects common roster columns and generates compact IDs, instrument prefixes, family colors, sections, ranks, and layers. |
| Hierarchical groups | Builds and edits Ensemble → family → section → rank trees with selection, transforms, and inherited locking. |
| Linked formations | Keeps equal-size repeated or mirrored groups synchronized until the writer explicitly detaches them. |
| Spot-safe performer replacement | Replaces or swaps performer roster identities without changing drill coordinates, paths, timing, or facings. |
| Automatic form cleanup | Removes overlaps, normalizes intervals, smooths curved segments, and preserves sharp corners. |
| Live conflict heatmap | Continuously analyzes the current set in the background; click a hot count to jump directly to it. |
| Set comparison | Shows two sets side-by-side with yellow difference vectors, travel distance, and direction. |
| Formation variations | Stores alternate selected/full-set formations inside one project and reapplies them with undo. |
| Multi-project tabs | Keeps multiple shows open and copies formations, timing maps, and props between project tabs. |

## Export System

| Export | Description |
| --- | --- |
| MP4 Video | Renders show animation and audio through ffmpeg. |
| Project ZIP | Packages project data, audio, props, and JSON for sharing/backup. |
| Drill Sheet PDF | Landscape set pages with field images and set details. |
| Dot Book PDF | Performer coordinate packet. |
| Staff Packet PDF | Summary, warnings, and large set pages for staff review. |
| Coordinate CSV | All performer coordinates for every set. |

## Data Safety

| Feature | Description |
| --- | --- |
| Atomic JSON saves | Project JSON files write through temporary files before replacing the previous version. |
| Versioned backups | Saves create timestamped JSON backup ZIPs in `.drill_pirate_backups`. |
| Autosave backups | Autosave creates retained backups with throttling to avoid uncontrolled growth. |
| Restore Previous Save | File menu command validates a selected backup, restores it atomically, and rolls current files back if restore fails. |
| Corrupt-project detection | Project load validates required files, JSON structure, schema version, and set presence. |
| Recovery prompt | Failed project opens offer restoring the newest backup or exporting a bug report bundle. |
| Schema migrations | Older project files are migrated to the current schema with a migration backup first. |

## Crash Handling

| Feature | Description |
| --- | --- |
| Crash logs | Unhandled exceptions write logs to the local Drill Pirate app data folder. |
| Error dialogs | Unexpected app errors show a user-facing dialog instead of failing silently. |
| Bug report bundle | Help menu exports logs, diagnostics, settings, plugin manifests/state, and project files into a ZIP. |

## Plugin System

| Feature | Description |
| --- | --- |
| Folder plugins | Plugins are folders under `Documents\Drill Pirate Plugins`. |
| Embedded runtime | Packaged EXE runs plugins with its bundled Python runtime. |
| Enable/disable | Home-screen plugin tab controls active plugins. |
| Startup hooks | Plugins can affect the home screen. |
| Main-window hooks | Plugins can affect project windows. |
| Custom form tools | Plugins can create tool buttons, menu actions, settings, and previews. |
| Stylesheet control | Plugins can change the UI color scheme and appearance. |
| Versioned API | Plugins declare `api_version` and compatibility warnings are shown when needed. |
| Compatibility gating | Plugins requiring a newer major API or newer app version are skipped instead of loaded unsafely. |
| Trust prompt | Plugin activation shows declared permissions before the plugin is trusted. |
| Crash isolation | Plugin load, hook, action, panel, and form-tool errors are caught and logged. |
| Diagnostics console | The Plugins tab includes an error console backed by `plugin_errors.log`. |
| Example plugins | Bundled examples cover form tools, themes, export helpers, rehearsal helpers, and panel extensions. |
| Trusted execution | Plugins run with normal Python access and should be installed only from trusted sources. |

## Update System

| Feature | Description |
| --- | --- |
| Latest release check | Checks GitHub latest release after startup. |
| Stable/beta channels | Stable checks GitHub latest; beta checks recent releases including pre-releases. |
| Install | Downloads and launches/replaces with the latest release asset. |
| Skip | Hides one release until a newer version exists. |
| Ignore | Dismisses the prompt for the current launch. |
| Release-log popup | Shows the new release description after successful update. |
| Integrity checks | Downloaded updates are size-checked, optional SHA-256 checked, and ZIP validated. |
| Rollback copy | ZIP self-update script restores the old app folder if file copy fails. |
| Release-note state | First launch after an update records whether the user dismissed or suppressed the release notes. |

## Current Alpha Limits

- Auto-planning is not yet a full multi-performer collision-avoidance solver.
- Constraint tools are useful but not equivalent to commercial CAD-style constraint solving.
- Movement styles are set metadata and printed communication; they are not yet a full biomechanics engine.
- Printed packets exist but still need deeper customization for different staff/performer formats.
- The Windows app is not yet signed with a publisher certificate.
- Plugins are trusted Python code, not sandboxed extensions.
