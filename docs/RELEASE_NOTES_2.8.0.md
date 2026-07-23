# Drill Pirate Alpha v2.8.0

Drill Pirate 2.8.0 is a production-workflow and reliability release. It strengthens large-show playback, drill correctness, coordinates, field construction, prop design, print customization, and project validation while adding set-level Director's Notes for staff drill books.

## Highlights

- Added a fully visual PDF layout designer for custom drill sheets, dot books, staff packets, section packets, and coordinate summaries.
- Rebuilt Prop Studio into a field-scaled layered designer with direct editing, snapping, rulers, and high-resolution output.
- Added configurable drill grids and exact snapping workflows for marchers and on-field formation handles.
- Added theme-aware center-field branding with built-in and custom logos.
- Added Director's Notes to every set and printed them on drill-sheet and staff-packet set pages.
- Hardened playback, audio recovery, project saving, migrations, collision guidance, coordinates, and deterministic exports.

## Added

### Director's Notes and Drill Books

- Every set now stores Director's Notes for visual descriptions, staging intent, production cues, and rehearsal priorities.
- Notes are edited from `Inspector > Sets > Set Details` and support application-level undo and redo.
- Set-list tooltips show a compact note preview.
- Default Drill Sheet and Staff Packet set pages print notes above the field chart.
- Custom PDF layouts can place notes anywhere with the `{director_notes}` token.

### PDF Layout Designer

- Added independent visual layouts for Drill Sheets, Dot Books, Staff Packets, Section Packets, and Coordinate Summaries.
- Added movable and resizable text, images, field views, data tables, rectangles, and lines.
- Added Letter, Legal, A4, and A3 page sizes in portrait or landscape orientation.
- Added typography, colors, borders, opacity, padding, image fitting, layer order, locking, and visibility controls.
- Added reusable presets and project-contained `print_assets` for portable branded layouts.
- Added dynamic show, set, performer, page, and Director's Notes tokens.

### Field Construction and Branding

- Added configurable 6-to-5, 8-to-5, 12-to-5, 16-to-5, and custom X/Y drill grids.
- Added clean snap-point and full-line overlay modes with a configurable origin.
- Added exact grid-node snapping for marcher drags, group movement, transform handles, and formation preview handles.
- Added official front/back hash priority rows so 8-to-5 and 16-to-5 workflows land exactly on regulation hashes.
- Added a built-in Drill Pirate center-field logo with visibility, size, and opacity controls.
- Added custom PNG/JPG/WebP field-logo import.
- Added theme-aware full-color, shaded grayscale, and inverted-grayscale logo rendering for Grass, White, and Inverted fields.

### Prop Studio

- Rebuilt the prop designer around a real-yard artboard and field-scale preview.
- Added layers, selection, locking, visibility, ordering, duplication, and multi-layer editing.
- Added rectangles, ellipses, lines, freehand paths, text, and high-quality imported images.
- Added rulers, adjustable snapping, zoom-to-fit, keyboard nudging, alignment, direct resize/rotation handles, and numeric transforms.
- Added fill, stroke, opacity, rotation, and exact geometry controls.
- Prop designs save both a high-resolution transparent PNG and an editable `.dpprop.json` source document.

## Improved

### Playback and Audio

- Added rolling FPS, dropped-deadline, adaptive-skip, render-cost, audio-clock anomaly, and cache diagnostics.
- Added automatic visual-quality reduction and recovery when large shows exceed the real-time rendering budget.
- Added loop-frame caching and throttled nonessential panel work without changing show timing.
- Strengthened pause, seek, loop, tempo-map, and set-boundary behavior under sustained UI load.
- Expanded Windows audio endpoint recovery for disconnects, default-device changes, Bluetooth stabilization, and device invalidation.
- Expanded waveform validation for long, compressed, variable-bitrate, unusual-sample-rate, multi-channel, and multiple PCM-depth files without requiring FFmpeg.

### Drill Correctness and Coordinates

- Added clearer explanations when fixed start and destination pictures make a conflict unavoidable.
- Added guided destination-swap previews with before/apply scoring while preserving the authored destination picture.
- Strengthened manually edited Bezier path and Group Motion Ribbon validation.
- Expanded biomechanical warnings for turn rate, backward/lateral movement, continuity direction, equipment, choreography, and performer-linked props.
- Standardized performer-facing coordinate output through one quarter-step formatter.
- Added reference coverage for Side 1/Side 2, yard lines, goal lines, end zones, front/back hashes, sidelines, indoor floors, parade routes, and CSV output.
- Corrected hash placement and snap alignment for standard football coordinates.
- Updated inspector X/Y and written coordinates live as marchers move.

### Field Editing and Display

- Formation preview handles now sit directly on their forms and obey the active drill grid.
- Built-in, SVG, and plugin form assignment avoids duplicate grid nodes when snapping is enabled.
- Marcher symbols are sized so performers at a one-step 8-to-5 interval remain distinct without appearing oversized.
- Previous-set Ghost Mode now renders a functional, symbol-aware, non-editable reference picture.
- Inverted-field text and markings now use the correct contrasting palette.
- Applied formations no longer revert when an individual marcher is adjusted afterward.

### Reliability and Data Confidence

- Added automated playback matrices and configurable soak testing for 200, 300, 400, and 500 performers.
- Added fixture projects for large SVG forms, Follow the Leader, moving props, choreography, tempo maps, and custom surfaces.
- Expanded save/load and migration coverage across every published project schema from v1 through v6.
- Added interrupted-write, low-disk-space, damaged-JSON, transaction rollback, and recovery regression coverage.
- Added deterministic PDF, CSV, ZIP, and MP4 profile tests.
- Audited save, autosave, project-open, recovery, updater, bug-report, shortcut, and export failures for actionable user dialogs.

## Fixed

- Fixed official hash rows being slightly misaligned with 8-to-5 and 16-to-5 snap grids.
- Fixed coordinate labels reporting inconsistent step values or failing to refresh after movement.
- Fixed form-tool snapping applying to generated geometry instead of the preview controls writers directly manipulate.
- Fixed Previous-Set Ghost appearing enabled without drawing a usable prior-set reference.
- Fixed field text remaining dark in Inverted field mode.
- Fixed custom field logos losing tonal shading in White and Inverted modes.
- Fixed custom PDF note tokens appearing literally on pages without an active set.
- Fixed set-note edits missing keyboard-triggered saves or exports while the notes editor still had focus.

## Validation

- Full automated suite: **189 tests passing**.
- The release gate includes model, UI, undo/redo, project persistence, PDF rendering, migration, recovery, playback/audio, coordinate, specialized-design, and deterministic-export coverage.

## Known Limitations

- The Windows build is currently an unsigned portable ZIP, so SmartScreen may warn on first launch.
- MP4 export requires a separately installed or selected `ffmpeg.exe`; all PDF, CSV, ZIP, waveform, and normal editing features work without FFmpeg.
- Hardware qualification is still ongoing for very large 300–500 performer shows, Bluetooth audio devices, and older integrated graphics.
- There is not yet a native macOS package or signed Windows installer.

## Tester Focus

- Build complete multi-movement shows and verify continuous playback across every set boundary.
- Compare printed coordinates with independent staff dot books and on-field expectations.
- Exercise custom PDF layouts with long Director's Notes, branding images, portrait/landscape pages, and batch export profiles.
- Test grid snapping on front/back hashes using both 8-to-5 and 16-to-5 spacing.
- Stress Prop Studio with layered images, text, freehand art, rotation, and field-scale placement.
- Report issues with `Help > Export Bug Report Bundle` and include a project ZIP when the show data is relevant.
