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

## Project Creation

| Feature | Description |
| --- | --- |
| Show title | Names the project and generated folder. |
| Audio import | Copies selected audio into the project `audio\` folder. |
| Initial tempo | Sets the universal/default BPM. |
| Default counts | Sets the default count length for new sets. |
| Time signature | Stores display metadata. |
| Marcher count | Creates a starting block with the requested number of performers. |
| Optimized starting block | Fits the initial performer block inside the field. |

## Main Window

| Feature | Description |
| --- | --- |
| Dockable panels | Tools, inspector, list, and timeline panels can dock, float, close, and reattach. |
| Workspace presets | Design, Forms, Rehearse, Print, and Focus Field layouts. |
| Command palette | Search and run commands from the keyboard. |
| Shortcut editor | Search commands and assign custom keyboard shortcuts. |
| Dark/light themes | Switch themes in Settings while the field remains readable. |
| Less panel crowding | Workspaces and floating docks allow large-show layouts on smaller screens. |

## Field View

| Feature | Description |
| --- | --- |
| Natural field rendering | Light field/grid presentation designed for drill readability. |
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
| Set positions | Every set stores positions for every marcher. |
| Count keyframes | Optional per-count position overrides within a set. |
| Movement styles | Normal, half time, double time, jazz run, halt, and visual. |

## Props

| Feature | Description |
| --- | --- |
| Image import | Imports a prop image into the project `props\` folder. |
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
| Circle | Places selected marchers around a circle. |
| Rectangle | Places selected marchers around a rectangle. |
| Scale Form | Expands/contracts selected form spacing while preserving the form shape. |
| Spiral | Places selected marchers on a spiral. |
| Block/Grid | Generates block or grid formations. |
| SVG Shape | Imports SVG paths and distributes performers along them. |
| Plugin Form | Runs custom form tools supplied by enabled plugins. |

## Advanced Editing

| Feature | Description |
| --- | --- |
| Live previews | Formation tools show ghosts and travel lines before applying. |
| Contextual controls | Only the active tool's settings are shown. |
| On-field handles | Drag tool handles directly on the field when supported. |
| Stable dot ordering | Tools try to preserve local selected order to avoid chaotic remapping. |
| Center selected | Moves selected formation to the field center. |
| Rotate selected | Rotates selected form as a group. |
| Follow-leader conveyor | Builds ordered motion around an outline instead of direct cross-form travel. |
| Fit to prop | Scales selected formation to a selected prop footprint. |
| Snap align | Shows purple horizontal/vertical snap guides while dragging. |
| Interval tools | Align and normalize spacing for selected marchers. |

## Path Editing and Safety

| Feature | Description |
| --- | --- |
| Yellow selected paths | Shows selected marcher travel to the next set or active playback target. |
| Red anchors | Add path anchors by right-clicking a yellow path. |
| Bezier handles | Drag cyan tangent handles for curved routes. |
| Clear selected paths | Remove custom anchors/controls from selected marchers. |
| Path analysis | Warns for close spacing, crossing paths, and high travel speed. |
| Auto-plan paths | Adds basic anchors for selected paths; results should be reviewed. |

## Visibility and Large Shows

| Feature | Description |
| --- | --- |
| Section filters | Hide or show sections. |
| Layer filters | Hide or show layers. |
| Label toggles | Reduce visual clutter on dense charts. |
| Searchable performer list | Faster navigation in 150+ performer projects. |
| Floating panels | Move panels to a second monitor or temporary workspace. |

## Export System

| Export | Description |
| --- | --- |
| MP4 Video | Renders show animation and audio through ffmpeg. |
| Project ZIP | Packages project data, audio, props, and JSON for sharing/backup. |
| Drill Sheet PDF | Landscape set pages with field images and set details. |
| Dot Book PDF | Performer coordinate packet. |
| Staff Packet PDF | Summary, warnings, and large set pages for staff review. |
| Coordinate CSV | All performer coordinates for every set. |

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
| Trusted execution | Plugins run with normal Python access and should be installed only from trusted sources. |

## Update System

| Feature | Description |
| --- | --- |
| Latest release check | Checks GitHub latest release after startup. |
| Install | Downloads and launches/replaces with the latest release asset. |
| Skip | Hides one release until a newer version exists. |
| Ignore | Dismisses the prompt for the current launch. |
| Release-log popup | Shows the new release description after successful update. |

## Current Alpha Limits

- Auto-planning is not yet a full multi-performer collision-avoidance solver.
- Constraint tools are useful but not equivalent to commercial CAD-style constraint solving.
- Movement styles are set metadata and printed communication; they are not yet a full biomechanics engine.
- Printed packets exist but still need deeper customization for different staff/performer formats.
- The Windows app is not yet signed with a publisher certificate.
- Plugins are trusted Python code, not sandboxed extensions.
